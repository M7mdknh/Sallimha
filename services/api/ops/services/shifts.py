"""Shift attendance and derived availability (docs/01 §1, docs/02 Staff availability)."""

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import audit
from core.errors import DomainError
from ops.models import LIVE_TASK_STATUSES, EventAssignment, Role, Shift, Task, UnavailablePeriod
from ops.permissions import actor_label, has_role, require


def live_task(staff):
    return Task.objects.filter(assignee=staff, status__in=LIVE_TASK_STATUSES).first()


def open_shift_for(staff, event=None, *, lock=False):
    qs = Shift.objects.filter(staff=staff, ended_at__isnull=True)
    if event is not None:
        qs = qs.filter(event=event)
    if lock:
        qs = qs.select_for_update(no_key=True)
    return qs.first()


def start_shift(actor, event, staff, now=None) -> Shift:
    now = now or timezone.now()
    require(actor, Role.SUPERVISOR, event)
    if staff.org_id != event.org_id:
        raise DomainError("forbidden")
    if not staff.enabled:
        raise DomainError("staff_disabled")
    if event.status != event.Status.OPEN:
        raise DomainError("event_closed")
    assigned = EventAssignment.objects.filter(event=event, staff=staff).exists()
    if not assigned and staff.role != Role.VALET and not has_role(actor, Role.MANAGER):
        # Adding supervisor-level staff to an event grants event scope: manager+ only.
        raise DomainError("forbidden")
    try:
        with transaction.atomic():
            if not assigned:
                EventAssignment.objects.create(event=event, staff=staff, assigned_by=actor)
            shift = Shift.objects.create(event=event, staff=staff, started_at=now, started_by=actor)
            audit("shift.start", actor_id=actor.id, actor_label=actor_label(actor), channel="console",
                  entity_type="shift", entity_id=shift.id, event_id=event.id, summary={"staff_id": staff.id})
    except IntegrityError as exc:
        raise DomainError("shift_already_open") from exc
    from messaging import notify  # local import: messaging depends on ops

    notify.shift_started(shift)
    return shift


def end_shift(actor, shift, now=None) -> Shift:
    now = now or timezone.now()
    require(actor, Role.SUPERVISOR, shift.event)
    with transaction.atomic():
        shift = Shift.objects.select_for_update(no_key=True).get(pk=shift.pk)
        if shift.ended_at is not None:
            return shift
        if live_task(shift.staff) is not None:
            raise DomainError("custody_open")
        UnavailablePeriod.objects.filter(shift=shift, ended_at__isnull=True).update(ended_at=now)
        shift.ended_at = now
        shift.ended_by = actor
        shift.save(update_fields=["ended_at", "ended_by"])
        audit("shift.end", actor_id=actor.id, actor_label=actor_label(actor), channel="console",
              entity_type="shift", entity_id=shift.id, event_id=shift.event_id, summary={"staff_id": shift.staff_id})
    return shift


def set_availability(staff, available: bool, now=None) -> str:
    """Valet preference. Returns available | unavailable | break_pending | no_shift."""
    now = now or timezone.now()
    with transaction.atomic():
        shift = open_shift_for(staff, lock=True)
        if shift is None:
            return "no_shift"
        busy = live_task(staff) is not None
        if available:
            UnavailablePeriod.objects.filter(shift=shift, ended_at__isnull=True).update(ended_at=now)
            changed = shift.availability != Shift.Availability.AVAILABLE or shift.break_pending
            shift.availability = Shift.Availability.AVAILABLE
            shift.break_pending = False
            if shift.idle_since is None or changed:
                shift.idle_since = None if busy else now
            shift.save(update_fields=["availability", "break_pending", "idle_since"])
            result = "available"
        elif busy:
            shift.break_pending = True
            shift.save(update_fields=["break_pending"])
            result = "break_pending"
        else:
            if shift.availability != Shift.Availability.UNAVAILABLE:
                UnavailablePeriod.objects.create(shift=shift, started_at=now)
            shift.availability = Shift.Availability.UNAVAILABLE
            shift.save(update_fields=["availability"])
            result = "unavailable"
        audit(f"availability.{result}", actor_id=staff.id, actor_label=actor_label(staff), channel="whatsapp",
              entity_type="shift", entity_id=shift.id, event_id=shift.event_id)
    return result


def on_task_released(staff, now=None) -> None:
    """Called inside the transaction that ends a valet's live task."""
    now = now or timezone.now()
    shift = open_shift_for(staff, lock=True)
    if shift is None:
        return
    shift.idle_since = now
    if shift.break_pending:
        shift.break_pending = False
        shift.availability = Shift.Availability.UNAVAILABLE
        UnavailablePeriod.objects.create(shift=shift, started_at=now)
    shift.save(update_fields=["idle_since", "break_pending", "availability"])


def is_available(staff, event) -> bool:
    if not staff.enabled:
        return False
    shift = open_shift_for(staff, event)
    return bool(
        shift
        and shift.availability == Shift.Availability.AVAILABLE
        and not shift.break_pending
        and live_task(staff) is None
    )
