"""People directory and role grants (docs/01 Preserved capabilities, docs/02 matrix). Deactivate, never delete."""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from core.audit import audit
from core.crypto import keyed_hash
from core.errors import DomainError
from core.phone import PhoneInvalid, parse_phone
from ops.models import LIVE_TASK_STATUSES, ROLE_RANK, Role, Staff, Task
from ops.permissions import actor_label, has_role
from ops.services.alerts import raise_alert

# Highest role each grantor may assign: managers below manager, admins below admin, super admins anything.
MAX_GRANT = {Role.MANAGER: Role.SUPERVISOR, Role.ADMIN: Role.MANAGER, Role.SUPER_ADMIN: Role.SUPER_ADMIN}


def _audit(action, actor, staff, **summary):
    audit(action, actor_id=actor.id, actor_label=actor_label(actor), channel="console", entity_type="staff",
          entity_id=staff.id, summary=summary)


def can_grant(actor, role: str) -> bool:
    ceiling = MAX_GRANT.get(actor.role)
    return bool(has_role(actor, Role.MANAGER) and ceiling and ROLE_RANK[role] <= ROLE_RANK[ceiling])


def _may_manage(actor, target) -> bool:
    if actor.org_id != target.org_id or actor.id == target.id:
        return False
    return actor.role == Role.SUPER_ADMIN or ROLE_RANK[actor.role] > ROLE_RANK[target.role]


def _other_super_admins(staff) -> bool:
    return Staff.objects.filter(org_id=staff.org_id, role=Role.SUPER_ADMIN, enabled=True).exclude(pk=staff.pk).exists()


def create_staff(actor, full_name: str, phone: str, role: str, *, username: str | None = None,
                 password: str | None = None) -> Staff:
    if role not in Role.values or not can_grant(actor, role):
        raise DomainError("forbidden")
    if not full_name.strip():
        raise DomainError("name_required")
    try:
        parsed = parse_phone(phone)
    except PhoneInvalid as exc:
        raise DomainError("phone_invalid") from exc
    console = ROLE_RANK[role] >= ROLE_RANK[Role.SUPERVISOR]
    if console and not (username and password):
        raise DomainError("credentials_required")
    try:
        with transaction.atomic():
            user = None
            if console:
                user = get_user_model()(username=username.strip()[:150])
                try:
                    validate_password(password, user)
                except ValidationError as exc:
                    raise DomainError("weak_password") from exc
                user.set_password(password)
                user.save()
            staff = Staff.objects.create(org_id=actor.org_id, full_name=full_name.strip()[:120],
                                         phone_e164=parsed.e164, phone_hash=keyed_hash(parsed.e164, "phone"),
                                         role=role, user=user)
            _audit("staff.create", actor, staff, role=role, console=console)
    except IntegrityError as exc:
        raise DomainError("duplicate") from exc
    return staff


def change_role(actor, staff, role: str) -> Staff:
    if role not in Role.values or not _may_manage(actor, staff) or not can_grant(actor, role):
        raise DomainError("forbidden")
    with transaction.atomic():
        staff = Staff.objects.select_for_update(no_key=True).get(pk=staff.pk)
        if staff.role == Role.SUPER_ADMIN and role != Role.SUPER_ADMIN and not _other_super_admins(staff):
            raise DomainError("last_super_admin")
        before = staff.role
        staff.role = role
        staff.session_epoch += 1  # every existing session must sign in again with the new privileges
        if ROLE_RANK[role] >= ROLE_RANK[Role.MANAGER] and ROLE_RANK[before] < ROLE_RANK[Role.MANAGER]:
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
        if staff.role == Role.SUPER_ADMIN and not _other_super_admins(staff):
            raise DomainError("last_super_admin")
        staff.enabled = False
        staff.deactivated_at = timezone.now()
        staff.session_epoch += 1
        staff.save(update_fields=["enabled", "deactivated_at", "session_epoch"])
        if staff.user_id:
            get_user_model().objects.filter(pk=staff.user_id).update(is_active=False)
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


def issue_mfa_enrolment(actor, staff) -> str:
    """Admin-issued TOTP enrolment (or reset after a lockout). Returns the provisioning URI once, for
    out-of-band delivery; existing sessions of that person are invalidated."""
    from console import mfa

    with transaction.atomic():
        staff = Staff.objects.select_for_update(no_key=True).get(pk=staff.pk)  # fresh role and epoch
        if not has_role(actor, Role.ADMIN) or not _may_manage(actor, staff):
            raise DomainError("forbidden")
        if ROLE_RANK[staff.role] < ROLE_RANK[Role.MANAGER]:
            raise DomainError("mfa_not_required")
        Staff.objects.filter(pk=staff.pk).update(session_epoch=F("session_epoch") + 1)
        uri = mfa.issue_secret(staff)
        _audit("staff.mfa_issue", actor, staff)
    return uri
