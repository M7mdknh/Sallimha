"""Reports and exports (docs/02 Reporting definitions, docs/01 Preserved capabilities).

Stage times keep original timestamps through reassignment. Hours come from actual shift start/end; breaks are
shown separately and never deducted without a policy decision. Manager exports never contain guest phones;
guest-phone exports are admin-only and audited (counts only)."""

import math
import statistics

from django.db.models import Count, F

from core.audit import audit
from core.crypto import decrypt_text
from ops.models import Incident, Rating, RetrievalRequest, Role, Shift, Ticket, UnavailablePeriod
from ops.permissions import actor_label, require


def _stat(values: list[float]) -> dict:
    values = sorted(v for v in values if v is not None and v >= 0)
    if not values:
        return {"count": 0, "median_s": None, "p95_s": None}
    p95 = values[max(0, math.ceil(0.95 * len(values)) - 1)]  # nearest-rank
    return {"count": len(values), "median_s": int(statistics.median(values)), "p95_s": int(p95)}


def _secs(start, end):
    return (end - start).total_seconds() if start and end else None


def event_report(actor, event) -> dict:
    require(actor, Role.MANAGER, event)
    tickets = Ticket.objects.filter(event=event)
    requests = RetrievalRequest.objects.filter(event=event).select_related("ticket")
    completed = [r for r in requests if r.state == "COMPLETED"]
    stages = {
        "request_to_accept": _stat([_secs(r.requested_at, r.accepted_at) for r in completed]),
        "accept_to_ready": _stat([_secs(r.accepted_at, r.ticket.ready_at) for r in completed]),
        "ready_to_delivered": _stat([_secs(r.ticket.ready_at, r.ticket.delivered_at) for r in completed]),
        "received_to_parked": _stat([_secs(t.created_at, t.parked_at) for t in tickets if t.parked_at]),
    }
    open_queue = requests.filter(state__in=["QUEUED", "OFFERED", "WAITING_FOR_PARKING"]).order_by("requested_at")
    hours = []
    for shift in Shift.objects.filter(event=event).select_related("staff").order_by("staff__full_name", "started_at"):
        worked = _secs(shift.started_at, shift.ended_at)
        breaks = sum(_secs(p.started_at, p.ended_at) or 0 for p in UnavailablePeriod.objects.filter(shift=shift))
        hours.append({"staff_id": shift.staff_id, "name": shift.staff.full_name, "started_at": shift.started_at,
                      "ended_at": shift.ended_at, "worked_s": int(worked) if worked is not None else None,
                      "break_s": int(breaks)})
    return {
        "event_id": event.id,
        "outcomes": dict(tickets.values_list("state").annotate(n=Count("id"))),
        "stages": stages,
        "oldest_queued_at": open_queue.first().requested_at if open_queue.exists() else None,
        "unresolved_incidents": Incident.objects.filter(event=event).exclude(status="RESOLVED").count(),
        "ratings": dict(Rating.objects.filter(ticket__event=event).values_list("value").annotate(n=Count("id"))),
        "hours": hours,
    }


TICKET_COLUMNS = ["ticket", "state", "plate", "zone", "created_at", "parked_at", "ready_at", "delivered_at",
                  "cancelled_at", "registered_by", "parked_by", "delivered_by", "rating"]


def ticket_rows(actor, event, *, state: str | None = None, since=None, until=None) -> list[dict]:
    """Filtered operational export. Never includes guest phone numbers (manager+)."""
    require(actor, Role.MANAGER, event)
    qs = Ticket.objects.filter(event=event).select_related("location_zone", "registered_by", "parked_by",
                                                           "delivered_by").order_by("display_number")
    if state:
        qs = qs.filter(state=state)
    if since:
        qs = qs.filter(created_at__gte=since)
    if until:
        qs = qs.filter(created_at__lt=until)
    ratings = dict(Rating.objects.filter(ticket__in=qs).values_list("ticket_id", "value"))
    rows = [{"ticket": f"#{t.display_number:03d}", "state": t.state, "plate": t.vehicle_plate,
             "zone": t.location_zone.code if t.location_zone_id else "", "created_at": t.created_at,
             "parked_at": t.parked_at, "ready_at": t.ready_at, "delivered_at": t.delivered_at,
             "cancelled_at": t.cancelled_at, "registered_by": t.registered_by.full_name,
             "parked_by": t.parked_by.full_name if t.parked_by_id else "",
             "delivered_by": t.delivered_by.full_name if t.delivered_by_id else "",
             "rating": ratings.get(t.id, "")} for t in qs]
    audit("export.tickets", actor_id=actor.id, actor_label=actor_label(actor), channel="console", entity_type="event",
          entity_id=event.id, event_id=event.id, summary={"rows": len(rows), "state": state or ""})
    return rows


def guest_phone_rows(actor, event) -> list[dict]:
    """Subject-data export (admin+ only; docs/02). Audited with the row count, never the numbers."""
    require(actor, Role.ADMIN, event)
    from ops.models import GuestBinding

    bindings = (GuestBinding.objects.filter(ticket__event=event, revoked_at__isnull=True).exclude(phone_enc="")
                .select_related("ticket").order_by(F("ticket__display_number")))
    rows = [{"ticket": f"#{b.ticket.display_number:03d}", "phone": decrypt_text(b.phone_enc),
             "consent_at": b.consent_at} for b in bindings]
    audit("export.guest_phones", actor_id=actor.id, actor_label=actor_label(actor), channel="console",
          entity_type="event", entity_id=event.id, event_id=event.id, summary={"rows": len(rows)})
    return rows
