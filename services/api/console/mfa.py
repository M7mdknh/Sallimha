"""TOTP second factor for manager and above (docs/01 Preserved capabilities; ADR-0001 Auth).

Secrets are stored encrypted; a code is accepted once (the last used time step is stored, so replays fail).
Enrolment happens at the first successful password login — see docs/PROGRESS risks: production should
switch to administrator-initiated enrolment."""

import pyotp
from django.db import transaction

from core.crypto import decrypt_text, encrypt_text
from ops.models import Staff

ISSUER = "Sallimha"


def _totp(staff) -> pyotp.TOTP:
    return pyotp.TOTP(decrypt_text(staff.mfa_secret_enc))


def provisioning_uri(staff) -> str:
    staff = Staff.objects.select_related("user").get(pk=staff.pk)  # the secret was saved on a locked copy
    return _totp(staff).provisioning_uri(name=staff.user.username if staff.user_id else str(staff.id),
                                         issuer_name=ISSUER)


def check(staff, code: str, now) -> str:
    """Returns ok | enrol | required | invalid."""
    with transaction.atomic():
        staff = Staff.objects.select_for_update(no_key=True).get(pk=staff.pk)
        if not staff.mfa_secret_enc:
            staff.mfa_secret_enc = encrypt_text(pyotp.random_base32())
            staff.save(update_fields=["mfa_secret_enc"])
        if not code:
            return "enrol" if staff.mfa_enrolled_at is None else "required"
        totp = _totp(staff)
        code = code.strip()
        for drift in (0, -1, 1):
            step = totp.timecode(now) + drift
            if totp.generate_otp(step) == code:
                if staff.mfa_last_step is not None and step <= staff.mfa_last_step:
                    return "invalid"  # replay of an already used (or older) code
                staff.mfa_last_step = step
                if staff.mfa_enrolled_at is None:
                    staff.mfa_enrolled_at = now
                staff.save(update_fields=["mfa_last_step", "mfa_enrolled_at"])
                return "ok"
        return "invalid"
