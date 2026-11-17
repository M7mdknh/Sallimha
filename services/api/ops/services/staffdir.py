"""People directory, role grants and account onboarding (docs/02 matrix, ADR-0011). Deactivate, never delete.

Three roles: admins manage everyone except themselves. Nobody is given a password by someone else: an admin issues a
one-time setup code and the person chooses their own password with it."""

import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import (
    CommonPasswordValidator,
    MinimumLengthValidator,
    UserAttributeSimilarityValidator,
    validate_password,
)
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from core.audit import audit
from core.crypto import constant_time_equals, keyed_hash, keyed_hash_candidates
from core.errors import DomainError
from core.phone import PhoneInvalid, parse_phone
from ops.models import LIVE_TASK_STATUSES, ROLE_RANK, AccountSetup, EventAssignment, Role, Shift, Staff, Task
from ops.permissions import actor_label, has_role
from ops.services.alerts import raise_alert

SETUP_TTL = timedelta(hours=72)
MAX_SETUP_ATTEMPTS = 5
VALET_MIN_PASSWORD = 8  # supervisors and admins keep the project-wide minimum (settings.AUTH_PASSWORD_VALIDATORS)


def _audit(action, actor, staff, **summary):
    audit(action, actor_id=actor.id if actor else None, actor_label=actor_label(actor) if actor else "anonymous",
          channel="console", entity_type="staff", entity_id=staff.id, summary=summary)


def can_grant(actor, role: str) -> bool:
    return bool(has_role(actor, Role.ADMIN) and role in Role.values)


def _may_manage(actor, target) -> bool:
    return bool(has_role(actor, Role.ADMIN) and actor.org_id == target.org_id and actor.id != target.id)


def _other_admins(staff) -> bool:
    return Staff.objects.filter(org_id=staff.org_id, role=Role.ADMIN, enabled=True).exclude(pk=staff.pk).exists()


def _ensure_user(staff, username: str | None = None):
    """Everyone signs in with their own account; the mobile number is the default sign-in name."""
    if staff.user_id:
        return staff.user
    user = get_user_model()(username=(username or staff.phone_e164).strip()[:150])
    user.set_unusable_password()  # only the person's own setup can make this account usable
    user.save()
    staff.user = user
    staff.save(update_fields=["user"])
    return user


def create_staff(actor, full_name: str, phone: str, role: str, *, username: str | None = None, event=None) -> Staff:
    """Adds a person with an account that nobody can use yet. `event` also puts them on that operation's team."""
    if role not in Role.values or not can_grant(actor, role):
        raise DomainError("forbidden")
    if not full_name.strip():
        raise DomainError("name_required")
    try:
        parsed = parse_phone(phone)
    except PhoneInvalid as exc:
        raise DomainError("phone_invalid") from exc
    if event is not None and event.org_id != actor.org_id:
        raise DomainError("forbidden")
    try:
        with transaction.atomic():
            staff = Staff.objects.create(org_id=actor.org_id, full_name=full_name.strip()[:120],
                                         phone_e164=parsed.e164, phone_hash=keyed_hash(parsed.e164, "phone"),
                                         role=role)
            _ensure_user(staff, username)
            if event is not None:
                EventAssignment.objects.create(event=event, staff=staff, assigned_by=actor)
            _audit("staff.create", actor, staff, role=role, event_id=event.id if event is not None else None)
    except IntegrityError as exc:
        raise DomainError("duplicate") from exc
    return staff


def issue_setup_code(actor, staff, now=None) -> str:
    """Returns a one-time code exactly once (first sign-in, or a password reset). Any earlier code stops working."""
    now = now or timezone.now()
    with transaction.atomic():
        staff = Staff.objects.select_for_update(no_key=True).get(pk=staff.pk)
        if not _may_manage(actor, staff):
            raise DomainError("forbidden")
        if not staff.enabled:
            raise DomainError("staff_disabled")
        try:
            with transaction.atomic():
                _ensure_user(staff)
        except IntegrityError as exc:
            raise DomainError("duplicate") from exc
        AccountSetup.objects.filter(staff=staff, used_at__isnull=True, revoked_at__isnull=True).update(revoked_at=now)
        code = f"{secrets.randbelow(10**8):08d}"
        AccountSetup.objects.create(staff=staff, code_hash=keyed_hash(f"{staff.id}:{code}", "setup"),
                                    issued_by=actor, expires_at=now + SETUP_TTL)
        _audit("staff.setup_code_issued", actor, staff)
    return code


def _password_rules(staff):
    if staff.role != Role.VALET:
        return None  # project-wide validators
    return [UserAttributeSimilarityValidator(), MinimumLengthValidator(VALET_MIN_PASSWORD), CommonPasswordValidator()]


def normalize_identifier(identifier: str) -> str:
    """A sign-in name is a mobile number (however it is typed) or a username chosen before ADR-0011."""
    identifier = (identifier or "").strip()
    try:
        return parse_phone(identifier).e164
    except PhoneInvalid:
        return identifier


def find_by_identifier(identifier: str):
    user = get_user_model().objects.filter(username__iexact=normalize_identifier(identifier)).first()
    return getattr(user, "staff", None) if user else None


def complete_setup(identifier: str, code: str, password: str, now=None) -> Staff:
    """The person sets their own password. Wrong codes are counted per code; every refusal looks the same."""
    now = now or timezone.now()
    staff = find_by_identifier(identifier)
    if staff is None or not staff.enabled:
        raise DomainError("setup_invalid")
    digits = "".join(ch for ch in (code or "") if ch.isdigit())
    with transaction.atomic():
        setup = (AccountSetup.objects.select_for_update(no_key=True)
                 .filter(staff=staff, used_at__isnull=True, revoked_at__isnull=True).first())
        if setup is None or setup.expires_at <= now or setup.failed_attempts >= MAX_SETUP_ATTEMPTS:
            raise DomainError("setup_invalid")
        matches = any(constant_time_equals(candidate, setup.code_hash)
                      for candidate in keyed_hash_candidates(f"{staff.id}:{digits}", "setup"))
        if matches:
            try:
                validate_password(password, staff.user, password_validators=_password_rules(staff))
            except ValidationError as exc:
                raise DomainError("weak_password") from exc
            staff.user.set_password(password)
            staff.user.save(update_fields=["password"])
            setup.used_at = now
            setup.save(update_fields=["used_at"])
            Staff.objects.filter(pk=staff.pk).update(session_epoch=F("session_epoch") + 1)
            _audit("auth.setup_completed", staff, staff)
        else:
            setup.failed_attempts += 1  # committed: the refusal is raised after this block
            setup.save(update_fields=["failed_attempts"])
            if setup.failed_attempts >= MAX_SETUP_ATTEMPTS:
                _audit("auth.setup_locked", None, staff)
    if not matches:
        raise DomainError("setup_invalid")
    staff.refresh_from_db()
    return staff


def change_role(actor, staff, role: str) -> Staff:
    if role not in Role.values or not _may_manage(actor, staff) or not can_grant(actor, role):
        raise DomainError("forbidden")
    with transaction.atomic():
        staff = Staff.objects.select_for_update(no_key=True).get(pk=staff.pk)
        if staff.role == Role.ADMIN and role != Role.ADMIN and not _other_admins(staff):
            raise DomainError("last_admin")
        if role != Role.VALET and Task.objects.filter(assignee=staff, status__in=LIVE_TASK_STATUSES).exists():
            raise DomainError("custody_open")  # finish or transfer their car before they stop being a valet
        before = staff.role
        staff.role = role
        staff.session_epoch += 1  # every existing session must sign in again with the new privileges
        if role == Role.ADMIN and before != Role.ADMIN:
            staff.mfa_secret_enc, staff.mfa_enrolled_at, staff.mfa_last_step = "", None, None  # admin must issue
        staff.save(update_fields=["role", "session_epoch", "mfa_secret_enc", "mfa_enrolled_at", "mfa_last_step"])
        _audit("staff.role", actor, staff, before=before, after=role)
    return staff


def deactivate(actor, staff, reason: str) -> Staff:
    """Blocks new access immediately; open custody becomes a supervisor exception, never a silent release."""
    if not reason.strip():
        raise DomainError("reason_required")
    if not _may_manage(actor, staff):
        raise DomainError("forbidden")
    with transaction.atomic():
        staff = Staff.objects.select_for_update(no_key=True).get(pk=staff.pk)
        if staff.role == Role.ADMIN and not _other_admins(staff):
            raise DomainError("last_admin")
        now = timezone.now()
        staff.enabled = False
        staff.deactivated_at = now
        staff.session_epoch += 1
        staff.save(update_fields=["enabled", "deactivated_at", "session_epoch"])
        if staff.user_id:
            get_user_model().objects.filter(pk=staff.user_id).update(is_active=False)
        AccountSetup.objects.filter(staff=staff, used_at__isnull=True, revoked_at__isnull=True).update(revoked_at=now)
        for task in Task.objects.filter(assignee=staff, status__in=LIVE_TASK_STATUSES).select_related("event"):
            raise_alert(task.event, "custody_exception", ticket=task.ticket, severity="critical",
                        dedupe_key=f"custody_exception:{task.id}:deactivated",
                        detail={"reason": "staff_deactivated", "staff_id": staff.id})
        _audit("staff.deactivate", actor, staff, reason=reason.strip()[:200])
    return staff


def reactivate(actor, staff) -> Staff:
    if not _may_manage(actor, staff):
        raise DomainError("forbidden")
    Staff.objects.filter(pk=staff.pk).update(enabled=True, deactivated_at=None)
    if staff.user_id:
        get_user_model().objects.filter(pk=staff.user_id).update(is_active=True)
    _audit("staff.reactivate", actor, staff)
    staff.refresh_from_db()
    return staff


def set_assignment(actor, staff, event, assigned: bool) -> None:
    """Puts a person on an operation's team or takes them off it (admins). Supervisors gain or lose that operation's
    scope with it; nobody is removed while their shift there is open."""
    if not _may_manage(actor, staff) or event.org_id != actor.org_id:
        raise DomainError("forbidden")
    with transaction.atomic():
        if assigned:
            if not staff.enabled:
                raise DomainError("staff_disabled")
            EventAssignment.objects.get_or_create(event=event, staff=staff, defaults={"assigned_by": actor})
        else:
            if Shift.objects.filter(event=event, staff=staff, ended_at__isnull=True).exists():
                raise DomainError("shift_open")
            EventAssignment.objects.filter(event=event, staff=staff).delete()
        _audit("staff.assignment", actor, staff, event_id=event.id, assigned=bool(assigned))


def issue_mfa_enrolment(actor, staff) -> str:
    """Admin-issued TOTP enrolment (or reset after a lockout). Returns the provisioning URI once, for
    out-of-band delivery; existing sessions of that person are invalidated."""
    from console import mfa

    with transaction.atomic():
        staff = Staff.objects.select_for_update(no_key=True).get(pk=staff.pk)  # fresh role and epoch
        if not _may_manage(actor, staff):
            raise DomainError("forbidden")
        if ROLE_RANK[staff.role] < ROLE_RANK[Role.ADMIN]:
            raise DomainError("mfa_not_required")
        Staff.objects.filter(pk=staff.pk).update(session_epoch=F("session_epoch") + 1)
        uri = mfa.issue_secret(staff)
        _audit("staff.mfa_issue", actor, staff)
    return uri
