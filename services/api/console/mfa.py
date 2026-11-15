"""TOTP second factor for manager and above (docs/01 Preserved capabilities; ADR-0001 Auth).

Enrolment is administrator-issued (the provisioning URI is shown once to the admin for out-of-band delivery);
login never hands out a secret. Secrets are stored encrypted; each code is accepted once; 5 consecutive wrong
codes lock the factor until an admin re-issues enrolment (Security Guidance findings on c5e863d)."""

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


MAX_FAILURES = 5


def issue_secret(staff) -> str:
    """Rotate the secret (admin-issued enrolment) and return the provisioning URI exactly once."""
    secret = pyotp.random_base32()
    Staff.objects.filter(pk=staff.pk).update(mfa_secret_enc=encrypt_text(secret), mfa_enrolled_at=None,
                                             mfa_last_step=None, mfa_failures=0, mfa_locked_at=None)
    staff.refresh_from_db()
    return provisioning_uri(staff)


def check(staff, code: str, now) -> str:
    """Returns ok | required | invalid | locked | not_enrolled. Never issues a secret."""
    from core.audit import audit

    with transaction.atomic():
        staff = Staff.objects.select_for_update(no_key=True).get(pk=staff.pk)
        if staff.mfa_locked_at is not None:
            return "locked"
        if not staff.mfa_secret_enc:
            return "not_enrolled"
        if not code:
            return "required"
        totp = _totp(staff)
        code = code.strip()
        for drift in (0, -1, 1):
            step = totp.timecode(now) + drift
            if totp.generate_otp(step) == code and (staff.mfa_last_step is None or step > staff.mfa_last_step):
                staff.mfa_last_step = step
                staff.mfa_failures = 0
                if staff.mfa_enrolled_at is None:
                    staff.mfa_enrolled_at = now
                staff.save(update_fields=["mfa_last_step", "mfa_failures", "mfa_enrolled_at"])
                return "ok"
        staff.mfa_failures += 1
        fields = ["mfa_failures"]
        if staff.mfa_failures >= MAX_FAILURES:
            staff.mfa_locked_at = now
            fields.append("mfa_locked_at")
            audit("auth.mfa_locked", actor_id=staff.id, actor_label=f"{staff.role}:{staff.id}", channel="console",
                  entity_type="staff", entity_id=staff.id, summary={"failures": staff.mfa_failures})
        staff.save(update_fields=fields)
        return "locked" if staff.mfa_locked_at else "invalid"
