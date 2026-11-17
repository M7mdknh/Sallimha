"""Explicit custody transfer for accepted work (docs/03): establish where the car and key are, cancel old
action authority, and require the receiving valet's acknowledgement. Never based only on "last online"."""

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import audit
from core.context import staff_channel
from core.errors import DomainError
from messaging import outbox
from ops.models import CustodyTransfer, KeyOccupancy, ParkingZone, RetrievalRequest, Role, Task, Ticket
from ops.permissions import actor_label, require
from ops.services import shifts, tokens


def _t(ticket) -> str:
    return f"#{ticket.display_number:03d}"


def _lock(task) -> tuple[Ticket, RetrievalRequest | None, Task]:
    ticket = Ticket.objects.select_for_update(no_key=True).get(pk=task.ticket_id)
    req = RetrievalRequest.objects.select_for_update(no_key=True).filter(pk=task.request_id).first()
    task = Task.objects.select_for_update(no_key=True).get(pk=task.pk)
    return ticket, req, task


def transfer_custody(actor, task, to_staff, vehicle_location: str, key_location: str, reason: str,
                     now=None) -> CustodyTransfer:
    now = now or timezone.now()
    require(actor, Role.SUPERVISOR, task.event)
    if not (vehicle_location.strip() and key_location.strip() and reason.strip()):
        raise DomainError("custody_details_required")
    if to_staff.org_id != task.event.org_id or not shifts.is_available(to_staff, task.event):
        raise DomainError("receiver_unavailable")
    try:
        with transaction.atomic():
            ticket, req, task = _lock(task)
            if task.type != Task.Type.RETRIEVAL or task.status != Task.Status.ACCEPTED:
                raise DomainError("invalid_state")
            previous = task.assignee
            task.status = Task.Status.RELEASED
            task.released_at = now
            task.release_reason = "custody_transferred"
            task.save(update_fields=["status", "released_at", "release_reason"])
            tokens.revoke(task=task, now=now)
            new_task = Task.objects.create(event=task.event, ticket=ticket, type=Task.Type.RETRIEVAL,
                                           status=Task.Status.RESERVED, assignee=to_staff,
                                           generation=task.generation + 1, request=req, reserved_at=now)
            if req is not None:
                req.current_task = new_task
                req.save(update_fields=["current_task"])
            shifts.on_task_released(previous, now)
            transfer = CustodyTransfer.objects.create(
                ticket=ticket, task=new_task, kind=CustodyTransfer.Kind.RETRIEVAL_TRANSFER, from_staff=previous,
                to_staff=to_staff, vehicle_location=vehicle_location.strip()[:160],
                key_location=key_location.strip()[:160], reason=reason.strip()[:200], initiated_by=actor)
            ack = tokens.issue("ack_retrieval_custody", staff=to_staff, ticket=ticket, task=new_task,
                               generation=new_task.generation, data={"transfer_id": transfer.id})
            outbox.enqueue("valet.custody_assigned", staff=to_staff, ticket=ticket, task=new_task,
                           template="valet.custody_assigned",
                           params={"ticket": _t(ticket), "vehicle_location": transfer.vehicle_location,
                                   "key_location": transfer.key_location},
                           buttons=[(ack, "ack_custody")], dedupe_key=f"valet.custody_assigned:{transfer.id}")
            outbox.enqueue("valet.custody_released", staff=previous, ticket=ticket, template="valet.custody_released",
                           params={"ticket": _t(ticket)}, dedupe_key=f"valet.custody_released:{transfer.id}")
            audit("custody.transfer", actor_id=actor.id, actor_label=actor_label(actor), channel="console",
                  entity_type="ticket", entity_id=ticket.id, event_id=ticket.event_id,
                  summary={"from": previous.id, "to": to_staff.id, "reason": transfer.reason})
    except IntegrityError as exc:
        raise DomainError("receiver_unavailable") from exc
    return transfer


def acknowledge_custody(staff, transfer, now=None, *, relayed_by=None, confirmed_via: str = "") -> Task:
    """The receiving valet confirms custody (or, during a declared WhatsApp outage, a supervisor records the
    valet's in-person or radio confirmation — ADR-0008)."""
    now = now or timezone.now()
    with transaction.atomic():
        transfer = CustodyTransfer.objects.select_for_update(no_key=True).get(pk=transfer.pk)
        if transfer.to_staff_id != staff.id or transfer.kind != CustodyTransfer.Kind.RETRIEVAL_TRANSFER:
            raise DomainError("forbidden")
        ticket, _req, task = _lock(transfer.task)
        if transfer.acknowledged_at is not None:
            return task
        if task.status != Task.Status.RESERVED or task.assignee_id != staff.id:
            raise DomainError("invalid_state")
        task.status = Task.Status.ACCEPTED
        task.accepted_at = now
        task.save(update_fields=["status", "accepted_at"])
        transfer.acknowledged_at = now
        transfer.acknowledged_by = staff
        transfer.save(update_fields=["acknowledged_at", "acknowledged_by"])
        if ticket.state == Ticket.State.RETRIEVING:
            ready = tokens.issue("valet_car_ready", staff=staff, task=task, ticket=ticket, generation=task.generation)
            outbox.enqueue("valet.assigned", staff=staff, ticket=ticket, task=task, template="valet.assigned",
                           params={}, buttons=[(ready, "car_ready")], dedupe_key=f"valet.assigned:{task.id}")
        summary = {"transfer": transfer.id}
        if relayed_by is not None:
            summary.update(relayed_by=relayed_by.id, confirmed_via=confirmed_via)
        audit("custody.acknowledged", actor_id=staff.id, actor_label=actor_label(staff),
              channel="console" if relayed_by is not None else staff_channel(), entity_type="ticket",
              entity_id=ticket.id, event_id=ticket.event_id, summary=summary)
    return task


def withdraw_accepted_with_custody_resolution(actor, req, *, zone_code: str, detail: str, hook_number: int,
                                              reason: str, now=None) -> CustodyTransfer:
    """Withdrawal after acceptance (ADR-0005 C2): record where the car and key are, then release explicitly."""
    now = now or timezone.now()
    require(actor, Role.SUPERVISOR, req.event)
    if not reason.strip():
        raise DomainError("reason_required")
    try:
        with transaction.atomic():
            ticket = Ticket.objects.select_for_update(no_key=True).get(pk=req.ticket_id)
            req = RetrievalRequest.objects.select_for_update(no_key=True).get(pk=req.pk)
            if req.state != RetrievalRequest.State.ACCEPTED or ticket.state not in (Ticket.State.RETRIEVING,
                                                                                    Ticket.State.READY):
                raise DomainError("invalid_state")
            task = Task.objects.select_for_update(no_key=True).get(pk=req.current_task_id)
            zone = ParkingZone.objects.filter(venue_id=ticket.event.venue_id, code__iexact=zone_code.strip(),
                                              active=True).first()
            if zone is None:
                raise DomainError("zone_invalid")
            current = KeyOccupancy.objects.select_for_update(no_key=True).filter(ticket=ticket,
                                                                                 released_at__isnull=True).first()
            if current is None or current.hook_number != int(hook_number):
                station = current.key_station if current else ticket.event.venue.key_stations.order_by("id").first()
                if not 1 <= int(hook_number) <= station.hook_count:
                    raise DomainError("hook_invalid")
                if current is not None:
                    current.released_at = now
                    current.released_by = actor
                    current.release_reason = "relocated"
                    current.save(update_fields=["released_at", "released_by", "release_reason"])
                KeyOccupancy.objects.create(key_station=station, hook_number=int(hook_number), ticket=ticket,
                                            occupied_at=now, occupied_by=actor)
            transfer = CustodyTransfer.objects.create(
                ticket=ticket, task=task, kind=CustodyTransfer.Kind.WITHDRAWAL_RESOLUTION, from_staff=task.assignee,
                vehicle_location=f"{zone.code} {detail}".strip()[:160], key_location=f"hook {int(hook_number)}",
                reason=reason.strip()[:200], initiated_by=actor, acknowledged_by=actor, acknowledged_at=now)
            task.status = Task.Status.RELEASED
            task.released_at = now
            task.release_reason = "custody_resolved"
            task.save(update_fields=["status", "released_at", "release_reason"])
            tokens.revoke(task=task, now=now)
            ticket.codes.filter(consumed_at__isnull=True, revoked_at__isnull=True).update(revoked_at=now)
            ticket.state = Ticket.State.PARKED
            ticket.location_zone = zone
            ticket.location_detail = detail.strip()[:80]
            ticket.version += 1
            ticket.save(update_fields=["state", "location_zone", "location_detail", "version"])
            req.state = RetrievalRequest.State.WITHDRAWN
            req.withdrawn_at = now
            req.withdrawn_by = actor
            req.withdraw_reason = reason.strip()[:200]
            req.save(update_fields=["state", "withdrawn_at", "withdrawn_by", "withdraw_reason"])
            shifts.on_task_released(task.assignee, now)
            outbox.enqueue("valet.custody_released", staff=task.assignee, ticket=ticket,
                           template="valet.custody_released", params={"ticket": _t(ticket)},
                           dedupe_key=f"valet.custody_released:{transfer.id}")
            binding = ticket.bindings.filter(revoked_at__isnull=True).first()
            if binding is not None:
                outbox.enqueue("guest.withdrawn", binding=binding, ticket=ticket, template="guest.withdrawn",
                               params={"ticket": _t(ticket)}, dedupe_key=f"guest.withdrawn:{req.id}")
            audit("request.withdraw_with_custody", actor_id=actor.id, actor_label=actor_label(actor),
                  channel="console", entity_type="ticket", entity_id=ticket.id, event_id=ticket.event_id,
                  summary={"zone": zone.code, "hook": int(hook_number), "reason": req.withdraw_reason})
    except IntegrityError as exc:
        raise DomainError("hook_occupied") from exc
    return transfer
