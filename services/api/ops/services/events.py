"""Event setup and closure (docs/01 §1, §8)."""

from django.db import transaction
from django.utils import timezone

from core.audit import audit
from core.errors import DomainError
from ops.models import LIVE_TASK_STATUSES, OPEN_REQUEST_STATES, Event, Role, Shift, Task, Ticket
from ops.permissions import actor_label, require

UNRESOLVED_TICKET_STATES = [Ticket.State.RECEIVED, Ticket.State.PARKED, Ticket.State.RETRIEVING, Ticket.State.READY]


def create_event(actor, venue, name: str, starts_at, timings: dict | None = None) -> Event:
    require(actor, Role.MANAGER)
    if venue.org_id != actor.org_id or not name.strip():
        raise DomainError("invalid_input")
    from ops.services.config import current_timings

    event = Event.objects.create(org=venue.org, venue=venue, name=name.strip()[:160], starts_at=starts_at,
                                 timings=timings or current_timings(venue.org))
    audit("event.create", actor_id=actor.id, actor_label=actor_label(actor), channel="console", entity_type="event",
          entity_id=event.id, event_id=event.id)
    return event


def close_event(actor, event, now=None) -> Event:
    """Managers close the operating session only after reconciliation: no live work, open requests, open shifts or
    vehicles still in custody without an approved carryover case. Never simulate delivery to close."""
    now = now or timezone.now()
    require(actor, Role.MANAGER, event)
    with transaction.atomic():
        event = Event.objects.select_for_update(no_key=True).get(pk=event.pk)
        if event.status == Event.Status.CLOSED:
            return event
        blocking = (
            Task.objects.filter(event=event, status__in=LIVE_TASK_STATUSES).exists()
            or event.requests.filter(state__in=OPEN_REQUEST_STATES).exists()
            or Ticket.objects.filter(event=event, state__in=UNRESOLVED_TICKET_STATES).exists()
        )
        if blocking:
            raise DomainError("custody_open")
        if Shift.objects.filter(event=event, ended_at__isnull=True).exists():
            raise DomainError("shifts_open")
        event.status = Event.Status.CLOSED
        event.closed_at = now
        event.closed_by = actor
        event.save(update_fields=["status", "closed_at", "closed_by"])
        audit("event.close", actor_id=actor.id, actor_label=actor_label(actor), channel="console",
              entity_type="event", entity_id=event.id, event_id=event.id)
    return event
