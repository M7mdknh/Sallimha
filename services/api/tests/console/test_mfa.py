"""AT-46: admin accounts require TOTP (ADR-0011: the one consolidated privileged role); enrolment is admin-issued;
codes cannot be replayed or brute-forced; privilege changes invalidate sessions (Security Guidance, c5e863d)."""

import pyotp
from rest_framework.test import APIClient

from core.models import AuditEvent
from ops.models import Role
from ops.services import staffdir
from tests.factories import make_staff, onboard

PASSWORD = "a-strong-console-pass-77"


def _login(client, username, otp=None):
    body = {"username": username, "password": PASSWORD}
    if otp is not None:
        body["otp"] = otp
    return client.post("/api/auth/login", body, format="json")


def _manager(world, username="mgr"):
    """A second admin (the role a manager now has), added by the organisation's admin."""
    root = world.admin
    mgr = onboard(root, "Mgr", f"+96655111{len(username):04d}", Role.ADMIN, PASSWORD, username=username)
    return root, mgr


def test_login_refused_until_admin_issues_enrolment(world):
    root, mgr = _manager(world)
    client = APIClient()
    resp = _login(client, "mgr")
    assert resp.status_code == 400 and resp.json()["code"] == "mfa_enrolment_required"
    assert "otpauth_uri" not in resp.json()
    uri = staffdir.issue_mfa_enrolment(root, mgr)
    secret = pyotp.parse_uri(uri).secret
    assert _login(client, "mgr").json() == {"ok": False, "mfa_required": True}
    assert client.get("/api/auth/me").status_code == 403
    assert _login(client, "mgr", pyotp.TOTP(secret).now()).json()["ok"] is True
    assert client.get("/api/auth/me").status_code == 200
    assert AuditEvent.objects.filter(action="staff.mfa_issue").exists()


def test_enrolment_issue_requires_admin(world):
    _root, mgr = _manager(world)
    import pytest

    from core.errors import DomainError
    with pytest.raises(DomainError):
        staffdir.issue_mfa_enrolment(world.supervisor, mgr)
    with pytest.raises(DomainError):
        staffdir.issue_mfa_enrolment(mgr, mgr)  # nobody issues their own


def test_totp_code_cannot_be_replayed(world):
    root, mgr = _manager(world, "mgr2")
    secret = pyotp.parse_uri(staffdir.issue_mfa_enrolment(root, mgr)).secret
    code = pyotp.TOTP(secret).now()
    assert _login(APIClient(), "mgr2", code).status_code == 200
    replay = _login(APIClient(), "mgr2", code)
    assert replay.status_code == 400 and replay.json()["code"] == "mfa_invalid"


def test_mfa_locks_after_repeated_failures_until_admin_reset(world):
    root, mgr = _manager(world, "mgr3")
    secret = pyotp.parse_uri(staffdir.issue_mfa_enrolment(root, mgr)).secret
    for i in range(5):  # distinct networks: the per-network throttle must not be what stops this
        APIClient().post("/api/auth/login", {"username": "mgr3", "password": PASSWORD, "otp": "000000"},
                         format="json", REMOTE_ADDR=f"10.7.0.{i + 1}")
    locked = APIClient().post("/api/auth/login", {"username": "mgr3", "password": PASSWORD,
                                                  "otp": pyotp.TOTP(secret).now()}, format="json",
                              REMOTE_ADDR="10.7.1.1")
    assert locked.status_code == 400 and locked.json()["code"] == "mfa_locked"
    assert AuditEvent.objects.filter(action="auth.mfa_locked").exists()
    new_secret = pyotp.parse_uri(staffdir.issue_mfa_enrolment(root, mgr)).secret  # admin reset + new enrolment
    ok = APIClient().post("/api/auth/login", {"username": "mgr3", "password": PASSWORD,
                                              "otp": pyotp.TOTP(new_secret).now()}, format="json",
                          REMOTE_ADDR="10.7.2.1")
    assert ok.status_code == 200


def test_promotion_invalidates_existing_sessions(world):
    sup = onboard(world.admin, "Sup", "+966551110004", Role.SUPERVISOR, PASSWORD, username="sup9")
    client = APIClient()
    assert _login(client, "sup9").json()["ok"] is True
    assert client.get("/api/auth/me").status_code == 200
    admin = make_staff(world.org, Role.ADMIN)
    staffdir.change_role(admin, sup, Role.ADMIN)
    assert client.get("/api/auth/me").status_code == 403


def test_manager_session_without_mfa_is_refused(world):
    _root, mgr = _manager(world, "mgr4")
    client = APIClient()
    client.force_login(mgr.user)  # a session that never passed TOTP
    assert client.get("/api/auth/me").status_code == 403


def test_supervisor_signs_in_without_mfa(world):
    onboard(world.admin, "Sup", "+966551110005", Role.SUPERVISOR, PASSWORD, username="sup8")
    assert _login(APIClient(), "sup8").json()["ok"] is True
