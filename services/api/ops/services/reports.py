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
    require(actor, Role.ADMIN, event)
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
    require(actor, Role.ADMIN, event)
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


def hourly_activity(event, now) -> list[dict]:
    """Cars received, requests made and cars delivered per hour of the operation, in the venue's time, from the
    recorded timestamps. Empty when nothing happened yet; at most the last 24 hours with activity."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(event.venue.timezone)

    def hour(t):
        local = t.astimezone(zone)
        return local.replace(minute=0, second=0, microsecond=0)

    series = {"received": Ticket.objects.filter(event=event).values_list("created_at", flat=True),
              "requested": RetrievalRequest.objects.filter(event=event).values_list("requested_at", flat=True),
              "delivered": Ticket.objects.filter(event=event, delivered_at__isnull=False)
              .values_list("delivered_at", flat=True)}
    counts: dict = {}
    for name, times in series.items():
        for t in times:
            counts.setdefault(hour(t), {"received": 0, "requested": 0, "delivered": 0})[name] += 1
    if not counts:
        return []
    last = max(max(counts), hour(now))
    first = max(min(counts), last - timedelta(hours=23))
    out, h = [], first
    while h <= last:
        out.append({"hour": h, **counts.get(h, {"received": 0, "requested": 0, "delivered": 0})})
        h += timedelta(hours=1)
    return out


def dashboard(actor, event, now) -> dict:
    """Admin overview of one operation, from the same rows and timestamps as the live view and the report. No scores:
    counts, one clearly defined duration and who is doing what."""
    from datetime import timedelta

    from ops.models import LIVE_TASK_STATUSES, Alert, EventAssignment, SafetyHold, Task
    from ops.services.dispatch import timings

    require(actor, Role.ADMIN, event)
    cfg = timings(event)
    states = dict(Ticket.objects.filter(event=event).values_list("state").annotate(n=Count("id")))
    requests = RetrievalRequest.objects.filter(event=event).select_related("ticket")
    waiting = [r for r in requests if r.state in ("WAITING_FOR_PARKING", "QUEUED", "OFFERED")]
    # Request-to-ready: the customer's request until the valet reported the car at the pickup point. Counted for
    # every request whose car got there (withdrawn requests are left out); reassignment never resets the start.
    reached = [r for r in requests if r.ticket.ready_at and r.ticket.ready_at >= r.requested_at
               and (r.state == "COMPLETED" or (r.state == "ACCEPTED" and r.ticket.state == "READY"))]
    alerts = Alert.objects.filter(event=event, acknowledged_at__isnull=True)
    members, tally = [], {"available": 0, "busy": 0, "unavailable": 0}
    on_shift = set()
    for shift in Shift.objects.filter(event=event, ended_at__isnull=True).select_related("staff"):
        on_shift.add(shift.staff_id)
        task = (Task.objects.filter(assignee=shift.staff, status__in=LIVE_TASK_STATUSES).select_related("ticket")
                .first())
        status = "busy" if task else (
            "unavailable" if shift.break_pending or shift.availability == Shift.Availability.UNAVAILABLE
            else "available")
        tally[status] += 1
        members.append({
            "staff_id": shift.staff_id, "name": shift.staff.full_name, "status": status,
            "task": f"#{task.ticket.display_number:03d}" if task else None,
            "parked": Ticket.objects.filter(event=event, parked_by=shift.staff).count(),
            "delivered": Ticket.objects.filter(event=event, delivered_by=shift.staff).count()})
    not_started = (EventAssignment.objects.filter(event=event, staff__enabled=True, staff__role=Role.VALET)
                   .exclude(staff_id__in=on_shift).count())
    return {
        "event": {"id": event.id, "name": event.name, "status": event.status, "venue": event.venue.name,
                  "time_zone": event.venue.timezone,
                  "period": {"start": event.starts_at, "end": event.closed_at or event.ends_at}},
        "generated_at": now,
        "activity": hourly_activity(event, now),
        "cars": {"receiving": states.get("RECEIVED", 0), "parked": states.get("PARKED", 0),
                 "retrieving": states.get("RETRIEVING", 0), "ready": states.get("READY", 0),
                 "delivered": states.get("DELIVERED", 0)},
        "waiting_requests": len(waiting),
        "delayed_requests": sum(1 for r in waiting
                                if r.requested_at <= now - timedelta(seconds=cfg["wait_warning_s"])),
        "delay_threshold_s": cfg["wait_warning_s"],
        "oldest_wait_s": int(max((now - r.requested_at).total_seconds() for r in waiting)) if waiting else None,
        "request_to_ready": _stat([_secs(r.requested_at, r.ticket.ready_at) for r in reached]),
        "problems": {"alerts": alerts.count(), "critical": alerts.filter(severity="critical").count(),
                     "incidents": Incident.objects.filter(event=event).exclude(status="RESOLVED").count(),
                     "holds": SafetyHold.objects.filter(ticket__event=event, cleared_at__isnull=True).count()},
        "team": {**tally, "not_started": not_started,
                 "members": sorted(members, key=lambda m: (m["status"] != "available", m["name"]))},
    }
