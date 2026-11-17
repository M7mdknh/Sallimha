"""AT-46: admin accounts require TOTP (ADR-0011: the one consolidated privileged role); enrolment and reset only by
the controlled procedure (ADR-0012), never by another admin in the app; codes cannot be replayed or brute-forced;
privilege changes invalidate sessions (Security Guidance, c5e863d)."""

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


def _controlled_access(world, staff) -> str:
    """The server procedure: the person sets their password with the new code and gets a new second factor."""
    code, uri = staffdir.grant_admin_access(staff, requested_by=world.admin, approved_by=world.supervisor,
                                            reason="identity checked in person", operator="tech")
    staffdir.complete_setup(staff.user.username, code, PASSWORD)
    return pyotp.parse_uri(uri).secret


def test_login_refused_until_the_controlled_procedure_issues_enrolment(world):
    _root, mgr = _manager(world)
    client = APIClient()
    resp = _login(client, "mgr")
    assert resp.status_code == 400 and resp.json()["code"] == "mfa_enrolment_required"
    assert "otpauth_uri" not in resp.json()
    secret = _controlled_access(world, mgr)
    assert _login(client, "mgr").json() == {"ok": False, "mfa_required": True}
    assert client.get("/api/auth/me").status_code == 403
    assert _login(client, "mgr", pyotp.TOTP(secret).now()).json()["ok"] is True
    assert client.get("/api/auth/me").status_code == 200
    assert AuditEvent.objects.filter(action="staff.admin_access").exists()


def test_totp_code_cannot_be_replayed(world):
    _root, mgr = _manager(world, "mgr2")
    secret = _controlled_access(world, mgr)
    code = pyotp.TOTP(secret).now()
    assert _login(APIClient(), "mgr2", code).status_code == 200
    replay = _login(APIClient(), "mgr2", code)
    assert replay.status_code == 400 and replay.json()["code"] == "mfa_invalid"


def test_mfa_locks_after_repeated_failures_until_the_controlled_procedure(world):
    _root, mgr = _manager(world, "mgr3")
    secret = _controlled_access(world, mgr)
    for i in range(5):  # distinct networks: the per-network throttle must not be what stops this
        APIClient().post("/api/auth/login", {"username": "mgr3", "password": PASSWORD, "otp": "000000"},
                         format="json", REMOTE_ADDR=f"10.7.0.{i + 1}")
    locked = APIClient().post("/api/auth/login", {"username": "mgr3", "password": PASSWORD,
                                                  "otp": pyotp.TOTP(secret).now()}, format="json",
                              REMOTE_ADDR="10.7.1.1")
    assert locked.status_code == 400 and locked.json()["code"] == "mfa_locked"
    assert AuditEvent.objects.filter(action="auth.mfa_locked").exists()
    new_secret = _controlled_access(world, mgr)  # two people, new password and new second factor
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
