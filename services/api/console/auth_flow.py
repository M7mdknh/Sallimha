"""Console login with brute-force protection (MFA for manager and above is added in Task 2.3).

Safe across concurrent requests and application workers: every attempt first reserves a slot with an
atomic upsert in PostgreSQL, so N parallel requests cannot all pass a check-then-insert gap. Only the
(IP, username) pair and the IP alone are hard-limited; a known username submitted from elsewhere never
blocks its owner. Responses are generic: unknown user and wrong password look identical.
"""

from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.utils import timezone
from rest_framework.response import Response

from core.audit import audit
from core.crypto import keyed_hash

MAX_FAILURES = 5          # per (IP, username) within WINDOW
IP_MAX_FAILURES = 30      # per IP across usernames within WINDOW (password spraying)
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


def _pair_key(username: str, ip: str) -> str:
    return keyed_hash(f"ip:{ip}|user:{username.lower()}", "login")


def _ip_key(ip: str) -> str:
    return keyed_hash(f"ip:{ip}", "login")


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


def login_step(request, authenticate, login):
    now = timezone.now()
    username = str(request.data.get("username", ""))[:150]
    password = str(request.data.get("password", ""))
    ip = client_ip(request)
    pair, by_ip = _pair_key(username, ip), _ip_key(ip)
    # Reserve before checking the password: concurrent attempts each consume a slot atomically.
    pair_count, ip_count = _reserve(pair, now), _reserve(by_ip, now)
    if pair_count > MAX_FAILURES or ip_count > IP_MAX_FAILURES:
        audit("auth.locked", actor_id=None, actor_label="anonymous", channel="console",
              summary={"scope": "pair" if pair_count > MAX_FAILURES else "ip", "key": pair[:12]})
        return Response({"code": "too_many_attempts"}, status=429)
    user = authenticate(request, username=username, password=password)
    staff = getattr(user, "staff", None) if user else None
    if user is None or staff is None or not staff.enabled:
        return Response({"code": "invalid_credentials"}, status=400)
    _release(pair, reset=True)
    _release(by_ip, reset=False)
    login(request, user)
    request.session["mfa_ok"] = True
    audit("auth.login", actor_id=staff.id, actor_label=f"{staff.role}:{staff.id}", channel="console")
    return Response({"ok": True, "role": staff.role})
