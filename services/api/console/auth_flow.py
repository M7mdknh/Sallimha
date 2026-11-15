"""Console login with brute-force protection (MFA for manager and above is added in Task 2.3).

Safe across concurrent requests and application workers: every attempt first reserves a slot with an
atomic upsert in PostgreSQL, so N parallel requests cannot all pass a check-then-insert gap. Only the
(IP, username) pair and the IP alone are hard-limited; a known username submitted from elsewhere never
blocks its owner. Responses are generic: unknown user and wrong password look identical.
"""

import ipaddress
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.utils import timezone
from rest_framework.response import Response

from console import mfa
from core.audit import audit
from core.crypto import keyed_hash
from core.models import LoginKnownNetwork
from ops.models import ROLE_RANK, Role

MAX_FAILURES = 5              # per (IP, username) within WINDOW
UNDER_ATTACK_PAIR_MAX = 2     # per (IP, username) while the account sees distributed failures
ACCOUNT_ALERT_THRESHOLD = 10  # failures for one username from other networks within WINDOW
IP_MAX_FAILURES = 30          # per IP (IPv6 /64) across usernames within WINDOW (password spraying)
WINDOW = timedelta(minutes=15)

_RESERVE = """
INSERT INTO core_loginthrottle (key_hash, window_start, failures) VALUES (%s, %s, 1)
ON CONFLICT (key_hash) DO UPDATE SET
    failures = CASE WHEN core_loginthrottle.window_start < %s THEN 1 ELSE core_loginthrottle.failures + 1 END,
    window_start = CASE WHEN core_loginthrottle.window_start < %s THEN EXCLUDED.window_start
                        ELSE core_loginthrottle.window_start END
RETURNING failures
"""


def client_ip(request) -> str:
    """REMOTE_ADDR unless a known number of trusted reverse proxies append X-Forwarded-For."""
    trusted = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    forwarded = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
    if trusted and len(forwarded) >= trusted:
        return forwarded[-trusted]
    return request.META.get("REMOTE_ADDR", "")


_NAT64 = ipaddress.ip_network("64:ff9b::/96")
KNOWN_NETWORK_TTL = timedelta(days=30)


def client_address(ip: str) -> str:
    """Canonical client address; IPv4 embedded in IPv6 (mapped, NAT64, 6to4, Teredo) is unwrapped."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if address.version == 6:
        if address.ipv4_mapped:
            return str(address.ipv4_mapped)
        if address in _NAT64:
            return str(ipaddress.IPv4Address(int(address) & 0xFFFFFFFF))
        if address.sixtofour:
            return str(address.sixtofour)
        if address.teredo:
            return str(address.teredo[1])
    return str(address)


def ip_bucket(ip: str) -> str:
    """Spraying-counter bucket: native IPv6 grouped by /64; IPv4 (including unwrapped forms) per address."""
    canonical = client_address(ip)
    try:
        address = ipaddress.ip_address(canonical)
    except ValueError:
        return canonical
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return canonical


def _pair_key(username: str, ip: str) -> str:
    return keyed_hash(f"ip:{ip}|user:{username.lower()}", "login")


def _ip_key(ip: str) -> str:
    return keyed_hash(f"ip:{ip}", "login")


def _user_key(username: str) -> str:
    return keyed_hash(f"user:{username.lower()}", "login")


def _known_key(username: str, address: str) -> str:
    return keyed_hash(f"known:{username.lower()}|{address}", "login")


def _reserve(key: str, now) -> int:
    expired_before = now - WINDOW
    with connection.cursor() as cursor:
        cursor.execute(_RESERVE, [key, now, expired_before, expired_before])
        return cursor.fetchone()[0]


def _release(key: str, *, reset: bool) -> None:
    with connection.cursor() as cursor:
        if reset:
            cursor.execute("DELETE FROM core_loginthrottle WHERE key_hash = %s", [key])
        else:
            cursor.execute("UPDATE core_loginthrottle SET failures = GREATEST(failures - 1, 0) WHERE key_hash = %s",
                           [key])


def login_step(request, data, authenticate, login):
    now = timezone.now()
    username = data["username"]
    password = data["password"]
    raw_ip = client_ip(request)
    bucket = ip_bucket(raw_ip)  # IPv4 per address (embedded forms unwrapped); native IPv6 per /64
    pair, by_ip, by_user = _pair_key(username, bucket), _ip_key(bucket), _user_key(username)
    known = _known_key(username, bucket)
    # Reserve before checking the password: concurrent attempts each consume a slot atomically.
    pair_count, ip_count, user_count = _reserve(pair, now), _reserve(by_ip, now), _reserve(by_user, now)
    # Account-level control without a lockout: failures for this username from other networks tighten the
    # per-network limit and are audited, but the owner can always try from their own network.
    under_attack = user_count - pair_count >= ACCOUNT_ALERT_THRESHOLD
    if under_attack and _reserve(keyed_hash(f"alerted:{username.lower()}", "login"), now) == 1:
        audit("auth.account_under_attack", actor_id=None, actor_label="anonymous", channel="console",
              summary={"key": by_user[:12]})
    # Networks the account recently signed in from keep the normal limit (no targeted throttling of the owner).
    trusted_network = LoginKnownNetwork.objects.filter(key_hash=known,
                                                       last_success_at__gte=now - KNOWN_NETWORK_TTL).exists()
    pair_limit = UNDER_ATTACK_PAIR_MAX if under_attack and not trusted_network else MAX_FAILURES
    if pair_count > pair_limit or ip_count > IP_MAX_FAILURES:
        audit("auth.locked", actor_id=None, actor_label="anonymous", channel="console",
              summary={"scope": "pair" if pair_count > pair_limit else "ip", "key": pair[:12]})
        return Response({"code": "too_many_attempts"}, status=429)
    user = authenticate(request, username=username, password=password)
    staff = getattr(user, "staff", None) if user else None
    if user is None or staff is None or not staff.enabled:
        return Response({"code": "invalid_credentials"}, status=400)
    if staff.rank >= ROLE_RANK[Role.MANAGER]:
        outcome = mfa.check(staff, data.get("otp") or "", now)
        if outcome == "enrol":
            return Response({"ok": False, "mfa_required": True, "mfa_enrolment": True,
                             "otpauth_uri": mfa.provisioning_uri(staff)})
        if outcome == "required":
            return Response({"ok": False, "mfa_required": True})
        if outcome == "invalid":
            return Response({"code": "mfa_invalid"}, status=400)  # the reserved attempt stays counted
    _release(pair, reset=True)
    _release(by_ip, reset=False)
    _release(by_user, reset=False)
    LoginKnownNetwork.objects.update_or_create(key_hash=known, defaults={"last_success_at": now})
    login(request, user)
    request.session["mfa_ok"] = True
    audit("auth.login", actor_id=staff.id, actor_label=f"{staff.role}:{staff.id}", channel="console")
    return Response({"ok": True, "role": staff.role})
