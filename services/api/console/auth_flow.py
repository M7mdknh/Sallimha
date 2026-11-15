"""Console login. MFA for manager and above is enforced in Phase 2 (Task 2.3)."""

from rest_framework.response import Response


def login_step(request, authenticate, login):
    username = str(request.data.get("username", ""))[:150]
    password = str(request.data.get("password", ""))
    user = authenticate(request, username=username, password=password)
    staff = getattr(user, "staff", None) if user else None
    if user is None or staff is None or not staff.enabled:
        return Response({"code": "invalid_credentials"}, status=400)
    login(request, user)
    request.session["mfa_ok"] = True
    return Response({"ok": True, "role": staff.role})
