"""Read models for the supervisor console. Read-only: never triggers operational side effects."""

from django.db.models import Count

from core.views_health import whatsapp_status, worker_status
from ops.models import (
    LIVE_TASK_STATUSES,
    OPEN_REQUEST_STATES,
    Alert,
    EventAssignment,
    KeyOccupancy,
    Media,
    RetrievalRequest,
    Role,
    Shift,
    Staff,
    Task,
    Ticket,
)

_SEVERITY = {"critical": 0, "warning": 1}


def _t(ticket) -> str:
    return f"#{ticket.display_number:03d}"


def _vehicle(ticket) -> str:
    return " ".join(p for p in (ticket.vehicle_plate, ticket.vehicle_description) if p) or "—"


def _location(ticket) -> str:
    return f"{ticket.location_zone.code} {ticket.location_detail}".strip() if ticket.location_zone_id else ""


def _hook(ticket) -> int | None:
    occ = KeyOccupancy.objects.filter(ticket=ticket, released_at__isnull=True).first()
    return occ.hook_number if occ else None


def _outage_brief(org) -> dict | None:
    from ops.services.outage import active_whatsapp_outage

    window = active_whatsapp_outage(org)
    return {"id": window.id, "since": window.started_at, "declared_by": window.declared_by.full_name,
            "reason": window.reason} if window else None


def snapshot(event, now) -> dict:
    alerts = sorted(
        Alert.objects.filter(event=event, acknowledged_at__isnull=True).select_related("ticket"),
        key=lambda a: (_SEVERITY.get(a.severity, 2), a.created_at),
    )
    counts = dict(Ticket.objects.filter(event=event).values_list("state").annotate(n=Count("id")))
    requests = []
    for req in (RetrievalRequest.objects.filter(event=event, state__in=OPEN_REQUEST_STATES)
                .select_related("ticket", "ticket__location_zone", "current_task__assignee")
                .order_by("requested_at", "id")):
        ticket = req.ticket
        task = req.current_task
        requests.append({
            "request_id": req.id, "ticket_id": ticket.id, "ticket": _t(ticket), "vehicle": _vehicle(ticket),
            "state": req.state, "ticket_state": ticket.state, "requested_at": req.requested_at,
            "elapsed_s": int((now - req.requested_at).total_seconds()),
            "assignee": task.assignee.full_name if task and task.status in LIVE_TASK_STATUSES else None,
            "location": _location(ticket), "hook": _hook(ticket), "failed_offers": req.failed_offers,
        })
    team = []
    on_shift = set()
    for shift in Shift.objects.filter(event=event, ended_at__isnull=True).select_related("staff"):
        on_shift.add(shift.staff_id)
        task = Task.objects.filter(assignee=shift.staff, status__in=LIVE_TASK_STATUSES).select_related("ticket").first()
        if task is not None:
            status = "busy"
        elif shift.break_pending or shift.availability == Shift.Availability.UNAVAILABLE:
            status = "unavailable"
        else:
            status = "available"
        team.append({"staff_id": shift.staff_id, "shift_id": shift.id, "name": shift.staff.full_name,
                     "role": shift.staff.role, "status": status, "break_pending": shift.break_pending,
                     "task": {"type": task.type, "ticket": _t(task.ticket), "ticket_id": task.ticket_id,
                              "status": task.status} if task else None,
                     "idle_since": shift.idle_since})
    not_started = [{"staff_id": a.staff_id, "name": a.staff.full_name, "role": a.staff.role}
                   for a in EventAssignment.objects.filter(event=event).select_related("staff")
                   if a.staff_id not in on_shift and a.staff.enabled]
    assigned = EventAssignment.objects.filter(event=event).values("staff_id")
    busy = Shift.objects.filter(ended_at__isnull=True).values("staff_id")
    addable = [{"staff_id": p.id, "name": p.full_name, "role": p.role}
               for p in Staff.objects.filter(org_id=event.org_id, role=Role.VALET, enabled=True)
               .exclude(pk__in=assigned).exclude(pk__in=busy).order_by("full_name")]
    return {
        "addable": addable,
        "event": {"id": event.id, "name": event.name, "status": event.status, "venue": event.venue.name,
                  "time_zone": event.venue.timezone},
        "generated_at": now,
        "health": {"worker": worker_status(now), "whatsapp": whatsapp_status()},
        "outage": _outage_brief(event.org),
        "attention": [{"id": a.id, "kind": a.kind, "severity": a.severity, "created_at": a.created_at,
                       "ticket": _t(a.ticket) if a.ticket_id else None, "ticket_id": a.ticket_id} for a in alerts],
        "counts": counts,
        "requests": requests,
        "team": sorted(team, key=lambda m: (m["status"] != "available", m["name"])),
        "not_started": not_started,
    }


def allowed_actions(ticket, req, binding, actor=None) -> list[str]:
    """UI hint only; every action is re-authorized and re-validated by the server. Manager-only actions are
    offered only to managers and above, so a supervisor never sees a control the server will refuse."""
    from ops.permissions import has_role
    actions = []
    if ticket.state == Ticket.State.RECEIVED and ticket.parking_started_at is None:
        actions += ["cancel", "except_intake", "intake_transfer"]
    if ticket.state == Ticket.State.RECEIVED and binding is not None and \
            ticket.contact_state != Ticket.Contact.CONFIRMED_IN_PERSON:
        actions.append("confirm_receipt")
    if req is not None and req.state in ("WAITING_FOR_PARKING", "QUEUED", "OFFERED"):
        actions.append("withdraw")
    if req is not None and req.state == "ACCEPTED":
        actions += ["withdraw_with_custody", "custody_transfer"]
    if ticket.state in (Ticket.State.RECEIVED, Ticket.State.PARKED, Ticket.State.RETRIEVING, Ticket.State.READY) \
            and binding is not None:
        actions.append("correct_phone")
    open_case = ticket.carryover_cases.exclude(status="RELEASED").first()
    move = ticket.tasks.filter(type="RELOCATION", status__in=["RESERVED", "OFFERED", "ACCEPTED"]).first()
    if ticket.state == Ticket.State.PARKED and req is None and open_case is None:
        actions += ["assisted_request", "propose_unclaimed"] + ([] if move else ["relocate_start"])
    if move is not None:
        # A move is recorded as done only after the valet accepted it (ADR-0007).
        actions += (["relocate_complete"] if move.status == "ACCEPTED" else []) + ["relocate_cancel"]
    if ticket.state == Ticket.State.READY:
        actions.append("assisted_handover")
    if open_case is not None and actor is not None and has_role(actor, Role.MANAGER):
        actions.append("approve_unclaimed" if open_case.status == "PROPOSED" else "release_carryover")
    actions += _outage_actions(ticket, actor)
    from ops.services import holds, incidents

    actions += holds.allowed_actions(ticket) + incidents.allowed_actions(ticket)
    return actions


def _outage_actions(ticket, actor) -> list[str]:
    """Relayed actions only while a WhatsApp outage is declared; reconciliation (manager+) only when a recorded
    whole-system outage in the last 30 days could contain the handover (ADR-0008)."""
    from datetime import timedelta

    from django.utils import timezone

    from ops.models import CustodyTransfer, OutageWindow
    from ops.permissions import has_role
    from ops.services.outage import active_whatsapp_outage

    actions = []
    if actor is None:
        return actions
    if active_whatsapp_outage(ticket.event.org) is not None:
        live = ticket.tasks.filter(status__in=LIVE_TASK_STATUSES).first()
        if live is not None and live.status == "OFFERED" and live.type in ("RETRIEVAL", "RELOCATION"):
            actions.append("relay_accept")
        if live is not None and live.status == "ACCEPTED" and live.type == "RETRIEVAL" and \
                ticket.state == Ticket.State.RETRIEVING:
            actions.append("relay_ready")
        if ticket.custody_transfers.filter(kind=CustodyTransfer.Kind.RETRIEVAL_TRANSFER,
                                           acknowledged_at__isnull=True).exists():
            actions.append("relay_custody_ack")
    if has_role(actor, Role.MANAGER) and ticket.state in (Ticket.State.PARKED, Ticket.State.RETRIEVING,
                                                         Ticket.State.READY) and \
            OutageWindow.objects.filter(org_id=ticket.event.org_id, kind="SYSTEM",
                                        ended_at__gte=timezone.now() - timedelta(days=30)).exists():
        actions.append("reconcile_handover")
    return actions


def ticket_detail(ticket, actor) -> dict:
    from ops.services import holds, incidents

    binding = ticket.bindings.filter(revoked_at__isnull=True).first()
    req = RetrievalRequest.objects.filter(ticket=ticket).order_by("-id").first()
    live_task = Task.objects.filter(ticket=ticket, status__in=LIVE_TASK_STATUSES).select_related("assignee").first()
    from core.models import AuditEvent

    timeline = AuditEvent.objects.filter(entity_type="ticket", entity_id=ticket.id).order_by("occurred_at")
    return {
        "id": ticket.id, "ticket": _t(ticket), "event_id": ticket.event_id, "state": ticket.state,
        "contact_state": ticket.contact_state, "phone_masked": binding.phone_masked if binding else None,
        "vehicle": _vehicle(ticket), "plate": ticket.vehicle_plate, "location": _location(ticket),
        "hook": _hook(ticket), "registered_by": ticket.registered_by.full_name,
        "parked_by": ticket.parked_by.full_name if ticket.parked_by_id else None,
        "assignee": live_task.assignee.full_name if live_task else None,
        "parking_started": ticket.parking_started_at is not None,
        "request": {"id": req.id, "state": req.state, "requested_at": req.requested_at} if req else None,
        "media": [{"id": m.id, "received_at": m.received_at, "kind": m.kind}
                  for m in Media.objects.filter(ticket=ticket, deleted_at__isnull=True).order_by("id")],
        "offered_to": live_task.assignee.full_name if live_task and live_task.status == "OFFERED" else None,
        "move": ({"status": live_task.status if live_task.status == "ACCEPTED" else "OFFERED",
                  "valet": live_task.assignee.full_name} if live_task and live_task.type == Task.Type.RELOCATION
                 else None),
        "holds": holds.brief(ticket),
        "incidents": incidents.brief(ticket),
        "timeline": [{"at": e.occurred_at, "action": e.action, "actor": e.actor_label} for e in timeline],
        "allowed_actions": allowed_actions(ticket, req if req and req.state in OPEN_REQUEST_STATES else None, binding,
                                           actor),
    }


def search(event, q: str) -> list[dict]:
    """Ticket finder for supervisors: digits ('12', '#12') match the ticket number or the plate; anything else
    matches the plate."""
    from django.db.models import Q

    q = q.strip()[:40]
    if not q:
        return []
    qs = Ticket.objects.filter(event=event).select_related("location_zone")
    number = q.lstrip("#")
    if number.isdigit() and len(number) <= 6:
        qs = qs.filter(Q(display_number=int(number)) | Q(vehicle_plate__icontains=number))
    else:
        qs = qs.filter(vehicle_plate__icontains=q)
    return [{"id": t.id, "ticket": _t(t), "state": t.state, "vehicle": _vehicle(t), "location": _location(t),
             "hook": _hook(t)} for t in qs.order_by("display_number")[:20]]
