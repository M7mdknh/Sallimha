"""AT-46: privileged accounts require TOTP; codes cannot be replayed."""

import pyotp
from rest_framework.test import APIClient

from core.crypto import decrypt_text
from ops.models import Role
from ops.services import staffdir

PASSWORD = "a-strong-console-pass-77"


def _login(client, username, otp=None):
    body = {"username": username, "password": PASSWORD}
    if otp is not None:
        body["otp"] = otp
    return client.post("/api/auth/login", body, format="json")


def test_manager_login_requires_totp_enrolment_then_code(world):
    from tests.factories import make_staff
    root = make_staff(world.org, Role.SUPER_ADMIN)
    mgr = staffdir.create_staff(root, "Mgr", "+966551110002", Role.MANAGER, username="mgr", password=PASSWORD)
    client = APIClient()
    first = _login(client, "mgr").json()
    assert first == {"ok": False, "mfa_required": True, "mfa_enrolment": True, "otpauth_uri": first["otpauth_uri"]}
    assert client.get("/api/auth/me").status_code == 403  # not signed in yet
    mgr.refresh_from_db()
    totp = pyotp.TOTP(decrypt_text(mgr.mfa_secret_enc))
    assert _login(client, "mgr", "000000").status_code == 400
    assert _login(client, "mgr", totp.now()).json()["ok"] is True
    assert client.get("/api/auth/me").status_code == 200


def test_totp_code_cannot_be_replayed(world):
    from tests.factories import make_staff
    root = make_staff(world.org, Role.SUPER_ADMIN)
    mgr = staffdir.create_staff(root, "Mgr", "+966551110003", Role.MANAGER, username="mgr2", password=PASSWORD)
    client = APIClient()
    _login(client, "mgr2")
    mgr.refresh_from_db()
    code = pyotp.TOTP(decrypt_text(mgr.mfa_secret_enc)).now()
    assert _login(client, "mgr2", code).status_code == 200
    replay = _login(APIClient(), "mgr2", code)
    assert replay.status_code == 400 and replay.json()["code"] == "mfa_invalid"


def test_supervisor_signs_in_without_mfa(world):
    staffdir.create_staff(world.manager, "Sup", "+966551110004", Role.SUPERVISOR, username="sup9", password=PASSWORD)
    assert _login(APIClient(), "sup9").json()["ok"] is True
