"""Read model for the valet app (ADR-0011): one answer to "what do I do now?".

A valet sees their own shift, their own live task and that task's ticket — with the customer's number masked — and
nothing else. Everything here is derived from the same rows the services lock and change."""

from core.models import AuditEvent
from core.views_health import whatsapp_status
from ops.models import (
    CustodyTransfer,
    EventAssignment,
    KeyOccupancy,
    KeyStation,
    Media,
    ParkingZone,
    RetrievalRequest,
    Shift,
    Task,
    Ticket,
)
from ops.services import holds, intake, shifts
from ops.services.outage import active_whatsapp_outage

RECENT = 5


def _t(ticket) -> str:
    return f"#{ticket.display_number:03d}"


def _availability(shift) -> str:
    if shift.break_pending:
        return "break_pending"
    return "available" if shift.availability == Shift.Availability.AVAILABLE else "unavailable"


def _pending_transfer(staff, ticket, kind):
    return (CustodyTransfer.objects.filter(ticket=ticket, kind=kind, to_staff=staff, acknowledged_at__isnull=True)
            .select_related("from_staff").order_by("-id").first())


def _code(ticket) -> dict | None:
    code = ticket.codes.filter(consumed_at__isnull=True, revoked_at__isnull=True).first()
    if code is None:
        return None
    return {"verified": code.verified_at is not None and code.locked_at is None, "locked": code.locked_at is not None,
            "remaining": max(0, 5 - code.failed_attempts)}


def _intake_step(staff, ticket, photos: int) -> tuple[str, CustodyTransfer | None]:
    transfer = _pending_transfer(staff, ticket, CustodyTransfer.Kind.INTAKE_HANDOFF)
    if transfer is not None:
        return "custody_ack", transfer
    if ticket.parking_started_at is not None:
        return "park", None
    if photos < intake.REQUIRED_PHOTOS and not ticket.photos_exception_reason:
        return "photos", None
    binding = ticket.bindings.filter(revoked_at__isnull=True).first()
    if binding is not None and binding.receipt_answered_at is None and \
            ticket.contact_state == Ticket.Contact.UNCONFIRMED:
        return "receipt", None
    return "start_parking", None


def _retrieval_step(staff, task, ticket) -> tuple[str, CustodyTransfer | None]:
    if task.status == Task.Status.OFFERED:
        return "offer", None
    if task.status == Task.Status.RESERVED:
        return "custody_ack", _pending_transfer(staff, ticket, CustodyTransfer.Kind.RETRIEVAL_TRANSFER)
    if ticket.state == Ticket.State.READY:
        code = _code(ticket)
        return ("deliver" if code and code["verified"] else "code"), None
    return "bring", None


def _move_reason(task) -> str:
    row = AuditEvent.objects.filter(action="relocation.offer", entity_type="ticket", entity_id=task.ticket_id,
                                    summary__task_id=task.id).first()
    return (row.summary or {}).get("reason", "") if row else ""


def _task(staff, task) -> dict:
    ticket = task.ticket
    photos = Media.objects.filter(ticket=ticket, kind=Media.Kind.INTAKE, deleted_at__isnull=True).count()
    if task.type == Task.Type.INTAKE:
        step, transfer = _intake_step(staff, ticket, photos)
    elif task.type == Task.Type.RETRIEVAL:
        step, transfer = _retrieval_step(staff, task, ticket)
    else:
        step, transfer = ("offer" if task.status == Task.Status.OFFERED else "move"), None
    binding = ticket.bindings.filter(revoked_at__isnull=True).first()
    occupancy = KeyOccupancy.objects.filter(ticket=ticket, released_at__isnull=True).first()
    zone = ticket.location_zone
    deadline = None
    if task.status == Task.Status.OFFERED:
        deadline = min(d for d in (task.offer_deadline, task.hard_deadline) if d) if task.hard_deadline else None
    return {
        "id": task.id, "type": task.type, "status": task.status, "step": step, "deadline": deadline,
        "shown": task.offer_sent_at is not None,
        "reason": _move_reason(task) if task.type == Task.Type.RELOCATION else "",
        "ticket": {
            "id": ticket.id, "number": _t(ticket),
            "vehicle": " ".join(p for p in (ticket.vehicle_plate, ticket.vehicle_description) if p) or "—",
            "location": f"{zone.code} {ticket.location_detail}".strip() if zone else "",
            "hook": occupancy.hook_number if occupancy else None,
            "phone_masked": binding.phone_masked if binding else None,
            "photos": photos, "photos_required": intake.REQUIRED_PHOTOS,
            "contact_state": ticket.contact_state, "state": ticket.state,
            "early_request": RetrievalRequest.objects.filter(
                ticket=ticket, state=RetrievalRequest.State.WAITING_FOR_PARKING).exists(),
            "handover_blocked": holds.handover_blocked(ticket),
        },
        "code": _code(ticket) if task.type == Task.Type.RETRIEVAL and ticket.state == Ticket.State.READY else None,
        "custody": ({"transfer_id": transfer.id, "vehicle_location": transfer.vehicle_location,
                     "key_location": transfer.key_location,
                     "from_name": transfer.from_staff.full_name if transfer.from_staff_id else ""}
                    if transfer is not None else None),
    }


def _venue(event) -> dict:
    station = KeyStation.objects.filter(venue_id=event.venue_id).order_by("id").first()
    zones = ParkingZone.objects.filter(venue_id=event.venue_id, active=True).order_by("code")
    return {"zones": [{"code": z.code, "label_ar": z.label_ar, "label_en": z.label_en} for z in zones],
            "hook_count": station.hook_count if station else 0}


def work(staff, now) -> dict:
    shift = shifts.open_shift_for(staff)
    task = Task.objects.filter(assignee=staff, status__in=["RESERVED", "OFFERED", "ACCEPTED"]) \
        .select_related("ticket", "ticket__location_zone", "event").first()
    assigned = None
    if shift is None:
        row = (EventAssignment.objects.filter(staff=staff, event__status="OPEN").select_related("event__venue")
               .order_by("-event__starts_at").first())
        assigned = {"event": row.event.name, "venue": row.event.venue.name} if row else None
    event = shift.event if shift is not None else (task.event if task is not None else None)
    recent = []
    if shift is not None:
        done = (Task.objects.filter(assignee=staff, event=shift.event, status=Task.Status.COMPLETED,
                                    completed_at__gte=shift.started_at)
                .select_related("ticket").order_by("-completed_at")[:RECENT])
        recent = [{"ticket": _t(t.ticket), "type": t.type, "at": t.completed_at} for t in done]
    delayed = whatsapp_status() == "degraded" or active_whatsapp_outage(staff.org) is not None
    return {
        "server_time": now,
        "me": {"id": staff.id, "name": staff.full_name},
        "shift": ({"id": shift.id, "availability": _availability(shift), "assisted": shift.assisted_since is not None,
                   "event": {"id": shift.event_id, "name": shift.event.name, "venue": shift.event.venue.name}}
                  if shift is not None else None),
        "assigned": assigned,
        "venue": _venue(event) if event is not None else None,
        "customer_messages": "delayed" if delayed else "ok",
        "task": _task(staff, task) if task is not None else None,
        "recent": recent,
    }
