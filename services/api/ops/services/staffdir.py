"""People directory, role grants and account onboarding (docs/02 matrix, ADR-0011, ADR-0012). Deactivate, never delete.

Three roles: admins manage everyone except themselves. Nobody is given a password by someone else: an admin issues a
one-time setup code and the person chooses their own password with it. That is routine for valets and supervisors
only. An admin's sign-in (first access, a locked second factor, a lost phone) is set up or recovered only with the
controlled procedure, `grant_admin_access`, run from the server: two named people, password and second factor reset
together, every session ended, and a record that every admin sees on the Team page. So no single admin can obtain
another admin's credentials and act as a second person."""

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
from core.models import AuditEvent
from core.phone import PhoneInvalid, parse_phone
from ops.models import LIVE_TASK_STATUSES, AccountSetup, EventAssignment, Role, Shift, Staff, Task
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
        if staff.role == Role.ADMIN:
            raise DomainError("admin_access_procedure")  # never from the app: grant_admin_access (ADR-0012)
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
        if Role.ADMIN in (before, role) and before != role:  # a code issued for another role never opens an admin
            AccountSetup.objects.filter(staff=staff, used_at__isnull=True, revoked_at__isnull=True).update(
                revoked_at=timezone.now())
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


def _admin_of(org_id, person) -> bool:
    return bool(person is not None and person.org_id == org_id and person.enabled and person.role == Role.ADMIN)


def grant_admin_access(target, *, requested_by, approved_by, reason: str, operator: str, first_admin: bool = False,
                       now=None) -> tuple[str, str]:
    """The controlled procedure for an admin's sign-in (ADR-0012): first access after promotion, a locked second
    factor, a lost phone or a suspected compromise. Run only from the server (`manage.py admin_access`), never from
    the app. Returns (setup code, second-factor URI), each shown once, for the target in person.

    Two people: an enabled admin who requests it (the target may ask for themselves) and a different enabled
    supervisor or admin who approves; neither is the operator's word alone. Only the very first admin of an
    organisation, when nobody else could approve, goes through as `first_admin`. Password and second factor are
    reset together and every session ends, so a code or factor handed out earlier is worthless afterwards."""
    from console import mfa

    now = now or timezone.now()
    reason = (reason or "").strip()
    if not reason:
        raise DomainError("reason_required")
    if not (operator or "").strip():
        raise DomainError("operator_required")
    with transaction.atomic():
        target = Staff.objects.select_for_update(no_key=True).get(pk=target.pk)
        if target.role != Role.ADMIN:
            raise DomainError("not_admin")  # valets and supervisors: the routine setup code from the Team page
        if not target.enabled:
            raise DomainError("staff_disabled")
        if first_admin:
            if requested_by is not None or approved_by is not None:
                raise DomainError("first_admin_has_no_approver")
            if _other_admins(target):
                raise DomainError("other_admins_exist")
        else:
            if not _admin_of(target.org_id, requested_by):
                raise DomainError("requester_not_admin")
            if approved_by is None or approved_by.pk in (requested_by.pk, target.pk):
                raise DomainError("approver_must_differ")
            if not (approved_by.org_id == target.org_id and approved_by.enabled and has_role(approved_by,
                                                                                             Role.SUPERVISOR)):
                raise DomainError("approver_not_authorized")
        try:
            with transaction.atomic():
                user = _ensure_user(target)
        except IntegrityError as exc:
            raise DomainError("duplicate") from exc
        user.set_unusable_password()  # whatever password existed (or someone set) stops working now
        user.save(update_fields=["password"])
        AccountSetup.objects.filter(staff=target, used_at__isnull=True, revoked_at__isnull=True).update(revoked_at=now)
        Staff.objects.filter(pk=target.pk).update(session_epoch=F("session_epoch") + 1)
        uri = mfa.issue_secret(target)  # new secret; clears enrolment, failures and any lock
        code = f"{secrets.randbelow(10**8):08d}"
        AccountSetup.objects.create(staff=target, code_hash=keyed_hash(f"{target.id}:{code}", "setup"),
                                    issued_by=approved_by or target, expires_at=now + SETUP_TTL)
        audit("staff.admin_access", actor_id=approved_by.id if approved_by else None,
              actor_label=f"server-operator:{operator.strip()[:60]}", channel="system", entity_type="staff",
              entity_id=target.id,
              summary={"requested_by": requested_by.id if requested_by else None,
                       "approved_by": approved_by.id if approved_by else None, "first_admin": bool(first_admin),
                       "operator": operator.strip()[:60], "reason": reason[:200]})
    return code, uri


def last_admin_access(staff_ids) -> dict:
    """The latest controlled-procedure record per person, for the Team page (names, not ids)."""
    rows = {}
    for row in (AuditEvent.objects.filter(action="staff.admin_access", entity_type="staff",
                                          entity_id__in=list(staff_ids)).order_by("id")):
        rows[int(row.entity_id)] = row
    names = dict(Staff.objects.filter(pk__in={v for r in rows.values() for v in (
        r.summary.get("requested_by"), r.summary.get("approved_by")) if v}).values_list("id", "full_name"))
    return {sid: {"at": r.occurred_at, "requested_by": names.get(r.summary.get("requested_by")),
                  "approved_by": names.get(r.summary.get("approved_by")),
                  "first_admin": bool(r.summary.get("first_admin")), "reason": r.summary.get("reason", "")}
            for sid, r in rows.items()}
