"""Explicit vehicle relocation (docs/02): a supervisor-initiated movement task with recorded old/new location;
new retrieval waits until the movement task's custody is released."""

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import audit
from core.errors import DomainError
from ops.models import LIVE_TASK_STATUSES, KeyOccupancy, ParkingZone, Role, Task, Ticket
from ops.permissions import actor_label, require
from ops.services import shifts


def start_relocation(actor, ticket, valet, reason: str, now=None) -> Task:
    now = now or timezone.now()
    require(actor, Role.SUPERVISOR, ticket.event)
    if not reason.strip():
        raise DomainError("reason_required")
    if not shifts.is_available(valet, ticket.event):
        raise DomainError("receiver_unavailable")
    try:
        with transaction.atomic():
            ticket = Ticket.objects.select_for_update(no_key=True).get(pk=ticket.pk)
            if ticket.state != Ticket.State.PARKED:
                raise DomainError("invalid_state")
            task = Task.objects.create(event=ticket.event, ticket=ticket, type=Task.Type.RELOCATION,
                                       status=Task.Status.ACCEPTED, assignee=valet, reserved_at=now, accepted_at=now)
            audit("relocation.start", actor_id=actor.id, actor_label=actor_label(actor), channel="console",
                  entity_type="ticket", entity_id=ticket.id, event_id=ticket.event_id,
                  summary={"valet": valet.id, "reason": reason.strip()[:200],
                           "from": f"{ticket.location_zone.code} {ticket.location_detail}".strip()})
    except IntegrityError as exc:
        raise DomainError("busy") from exc
    return task


def complete_relocation(actor, task, *, zone_code: str, detail: str, hook_number: int, now=None) -> Ticket:
    now = now or timezone.now()
    require(actor, Role.SUPERVISOR, task.event)
    try:
        with transaction.atomic():
            ticket = Ticket.objects.select_for_update(no_key=True).get(pk=task.ticket_id)
            task = Task.objects.select_for_update(no_key=True).get(pk=task.pk)
            if task.type != Task.Type.RELOCATION or task.status not in LIVE_TASK_STATUSES:
                raise DomainError("invalid_state")
            zone = ParkingZone.objects.filter(venue_id=ticket.event.venue_id, code__iexact=zone_code.strip(),
                                              active=True).first()
            if zone is None:
                raise DomainError("zone_invalid")
            old = KeyOccupancy.objects.select_for_update(no_key=True).filter(ticket=ticket,
                                                                             released_at__isnull=True).first()
            station = old.key_station if old else ticket.event.venue.key_stations.order_by("id").first()
            if not 1 <= int(hook_number) <= station.hook_count:
                raise DomainError("hook_invalid")
            previous = f"{ticket.location_zone.code} {ticket.location_detail}".strip()
            if old is None or old.hook_number != int(hook_number):
                if old is not None:
                    old.released_at, old.released_by, old.release_reason = now, actor, "relocated"
                    old.save(update_fields=["released_at", "released_by", "release_reason"])
                KeyOccupancy.objects.create(key_station=station, hook_number=int(hook_number), ticket=ticket,
                                            occupied_at=now, occupied_by=task.assignee)
            ticket.location_zone = zone
            ticket.location_detail = detail.strip()[:80]
            ticket.version += 1
            ticket.save(update_fields=["location_zone", "location_detail", "version"])
            task.status = Task.Status.COMPLETED
            task.completed_at = now
            task.save(update_fields=["status", "completed_at"])
            shifts.on_task_released(task.assignee, now)
            audit("relocation.complete", actor_id=actor.id, actor_label=actor_label(actor), channel="console",
                  entity_type="ticket", entity_id=ticket.id, event_id=ticket.event_id,
                  summary={"from": previous, "to": f"{zone.code} {ticket.location_detail}".strip(),
                           "hook": int(hook_number), "mover": task.assignee_id})
    except IntegrityError as exc:
        raise DomainError("hook_occupied") from exc
    return ticket
