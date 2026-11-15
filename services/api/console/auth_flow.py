"""Console login with lockout. MFA for manager and above is added in Task 2.3."""

from datetime import timedelta

from django.utils import timezone
from rest_framework.response import Response

from core.audit import audit
from core.crypto import keyed_hash
from core.models import LoginAttempt

MAX_FAILURES = 5
WINDOW = timedelta(minutes=15)


def _client_ip(request) -> str:
    return request.META.get("REMOTE_ADDR", "")


def _keys(username: str, ip: str) -> list[str]:
    return [keyed_hash(f"user:{username.lower()}", "login"), keyed_hash(f"ip:{ip}|user:{username.lower()}", "login")]


def _locked(keys, now) -> bool:
    since = now - WINDOW
    return any(LoginAttempt.objects.filter(key_hash=k, attempted_at__gte=since).count() >= MAX_FAILURES for k in keys)


def login_step(request, authenticate, login):
    now = timezone.now()
    username = str(request.data.get("username", ""))[:150]
    password = str(request.data.get("password", ""))
    keys = _keys(username, _client_ip(request))
    if _locked(keys, now):
        audit("auth.locked", actor_id=None, actor_label="anonymous", channel="console",
              summary={"user_key": keys[0][:12]})
        return Response({"code": "too_many_attempts"}, status=429)
    user = authenticate(request, username=username, password=password)
    staff = getattr(user, "staff", None) if user else None
    if user is None or staff is None or not staff.enabled:
        LoginAttempt.objects.bulk_create([LoginAttempt(key_hash=k) for k in keys])
        return Response({"code": "invalid_credentials"}, status=400)
    LoginAttempt.objects.filter(key_hash__in=keys).delete()
    login(request, user)
    request.session["mfa_ok"] = True
    audit("auth.login", actor_id=staff.id, actor_label=f"{staff.role}:{staff.id}", channel="console")
    return Response({"ok": True, "role": staff.role})
