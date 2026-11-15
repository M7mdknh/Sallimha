"""Automatic, fair, atomic retrieval dispatch (docs/01 §5, docs/03, ADR-0002/0003).

There is deliberately no manual "assign this request to that valet" command: supervisors monitor and
handle exceptions; routine work is dispatched here only.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Max, Q
from django.utils import timezone

from core.audit import audit
from core.locks import lock_event
from messaging import hooks, outbox
from ops.models import (
    AssignmentAttempt,
    Event,
    RetrievalRequest,
    Shift,
    Staff,
    Task,
    Ticket,
)
from ops.permissions import actor_label
from ops.services import shifts, tokens
from ops.services.alerts import raise_alert

DEFAULT_TIMINGS = {
    "offer_window_s": 30,
    "hard_limit_s": 60,
    "send_pending_warning_s": 15,
    "attempts_before_alert": 2,
    "cooldown_s": 60,
    "wait_warning_s": 240,
    "wait_critical_s": 360,
    "accepted_warning_s": 240,
    "ready_warning_s": 300,
}
_FAILED = (AssignmentAttempt.Outcome.EXPIRED, AssignmentAttempt.Outcome.DECLINED,
           AssignmentAttempt.Outcome.SEND_FAILED)


def timings(event) -> dict:
    """Defaults ← organization configuration (admin) ← per-event overrides. Issued offers keep stored deadlines."""
    from ops.services.config import current_timings

    return {**current_timings(event.org), **(event.timings or {})}


def _t(ticket) -> str:
    return f"#{ticket.display_number:03d}"


def _local_time(value) -> str:
    return value.astimezone(ZoneInfo(settings.DISPLAY_TIME_ZONE)).strftime("%H:%M")


def eligible_requests(event):
    """Oldest first by original request time; ineligible early requests never block others."""
    from ops.services.holds import dispatch_blocked_ticket_ids

    return (RetrievalRequest.objects.filter(event=event, state=RetrievalRequest.State.QUEUED,
                                            ticket__state=Ticket.State.PARKED)
            .exclude(ticket_id__in=dispatch_blocked_ticket_ids(event))
            .exclude(ticket__tasks__status__in=["RESERVED", "OFFERED", "ACCEPTED"])  # e.g. a relocation in progress
            .filter(Q(binding__isnull=True) | Q(binding__revoked_at__isnull=True))
            .order_by("requested_at", "id"))


def candidate_pool(event) -> list[Staff]:
    """Available valets on this event's active shifts, longest idle first, stable staff-id tie-break."""
    shifts_qs = (Shift.objects.filter(event=event, ended_at__isnull=True, availability=Shift.Availability.AVAILABLE,
                                      break_pending=False, staff__enabled=True)
                 .exclude(staff__tasks__status__in=["RESERVED", "OFFERED", "ACCEPTED"])
                 .select_related("staff")
                 .order_by(F("idle_since").asc(nulls_last=True), "staff_id"))
    return [s.staff for s in shifts_qs]


def _cooling(req, now, cooldown_s: int) -> set[int]:
    since = now - timedelta(seconds=cooldown_s)
    return set(AssignmentAttempt.objects.filter(request=req, outcome__in=_FAILED, responded_at__gt=since)
               .values_list("candidate_id", flat=True))


def _offer(req, staff, now, cfg) -> Task:
    generation = (req.attempts.aggregate(m=Max("generation"))["m"] or 0) + 1
    hard = now + timedelta(seconds=cfg["hard_limit_s"])
    ticket = req.ticket
    task = Task.objects.create(event=req.event, ticket=ticket, type=Task.Type.RETRIEVAL, status=Task.Status.OFFERED,
                               assignee=staff, generation=generation, request=req, reserved_at=now, hard_deadline=hard)
    AssignmentAttempt.objects.create(request=req, task=task, candidate=staff, generation=generation, offered_at=now)
    req.state = RetrievalRequest.State.OFFERED
    req.current_task = task
    req.save(update_fields=["state", "current_task"])
    accept = tokens.issue("valet_accept", staff=staff, task=task, ticket=ticket, generation=generation,
                          expires_at=hard)
    decline = tokens.issue("valet_decline", staff=staff, task=task, ticket=ticket, generation=generation,
                           expires_at=hard)
    occupancy = ticket.key_occupancies.filter(released_at__isnull=True).first()
    zone = ticket.location_zone
    vehicle = " ".join(p for p in (ticket.vehicle_plate, ticket.vehicle_description) if p) or "—"
    outbox.enqueue("valet.offer", staff=staff, ticket=ticket, task=task, template="valet.offer",
                   params={"ticket": _t(ticket), "vehicle": vehicle,
                           "location": f"{zone.code} {ticket.location_detail}".strip() if zone else "—",
                           "hook": str(occupancy.hook_number) if occupancy else "—",
                           "expires": _local_time(hard)},
                   buttons=[(accept, "accept"), (decline, "decline")], dedupe_key=f"valet.offer:{task.id}", now=now)
    audit("dispatch.offer", actor_id=None, actor_label="dispatcher", channel="worker", entity_type="ticket",
          entity_id=ticket.id, event_id=req.event_id,
          summary={"task_id": task.id, "staff_id": staff.id, "generation": generation,
                   "affinity": ticket.parked_by_id == staff.id})
    return task


def dispatch_event(event_id: int, now=None) -> list[Task]:
    now = now or timezone.now()
    created: list[Task] = []
    with transaction.atomic():
        lock_event(event_id)
        event = Event.objects.get(pk=event_id)
        if event.status != Event.Status.OPEN:
            return []
        cfg = timings(event)
        pool = candidate_pool(event)
        for req in eligible_requests(event).select_for_update(of=("self",), no_key=True).select_related("ticket"):
            if not pool:
                break
            cooling = _cooling(req, now, cfg["cooldown_s"])
            options = [s for s in pool if s.id not in cooling]
            if not options:
                continue
            affinity = next((s for s in options if s.id == req.ticket.parked_by_id), None)
            for choice in ([affinity] if affinity else []) + [s for s in options if s is not affinity]:
                try:
                    with transaction.atomic():
                        created.append(_offer(req, choice, now, cfg))
                    pool.remove(choice)
                    break
                except IntegrityError:
                    pool.remove(choice)  # took other work concurrently (e.g. intake); try the next candidate
    return created


def dispatch_all(now=None) -> int:
    now = now or timezone.now()
    event_ids = (RetrievalRequest.objects.filter(state=RetrievalRequest.State.QUEUED,
                                                 event__status=Event.Status.OPEN)
                 .values_list("event_id", flat=True).distinct())
    return sum(len(dispatch_event(event_id, now)) for event_id in list(event_ids))


def _release_offer(task, now, outcome: str, reason: str) -> None:
    """Unaccepted offer ends: release capacity, requeue without resetting age, cooldown via the attempt."""
    req = RetrievalRequest.objects.get(pk=task.request_id)  # already locked by the caller (_lock_chain)
    task.status = Task.Status.RELEASED
    task.released_at = now
    task.release_reason = reason
    task.save(update_fields=["status", "released_at", "release_reason"])
    AssignmentAttempt.objects.filter(task=task).update(outcome=outcome, responded_at=now)
    tokens.revoke(task=task, now=now)
    shifts.on_task_released(task.assignee, now)
    if req.state == RetrievalRequest.State.OFFERED and req.current_task_id == task.id:
        req.state = RetrievalRequest.State.QUEUED
        req.current_task = None
        req.failed_offers += 1
        req.save(update_fields=["state", "current_task", "failed_offers"])
        cfg = timings(req.event)
        if req.failed_offers >= cfg["attempts_before_alert"]:
            raise_alert(req.event, "offer_failures", ticket=req.ticket, dedupe_key=f"offer_failures:{req.id}",
                        detail={"failed_offers": req.failed_offers})
    audit(f"dispatch.{reason}", actor_id=task.assignee_id, actor_label=actor_label(task.assignee), channel="worker",
          entity_type="ticket", entity_id=task.ticket_id, event_id=task.event_id, summary={"task_id": task.id})


def _lock_chain(task_id: int) -> tuple[Ticket | None, RetrievalRequest | None, Task | None]:
    """Canonical lock order (ADR-0003): ticket → request → task → shift → key → action tokens."""
    ids = Task.objects.filter(pk=task_id).values_list("ticket_id", "request_id").first()
    if ids is None or ids[1] is None:
        return None, None, None
    ticket = Ticket.objects.select_for_update(no_key=True).get(pk=ids[0])
    req = RetrievalRequest.objects.select_for_update(no_key=True).get(pk=ids[1])
    task = Task.objects.select_for_update(no_key=True).get(pk=task_id)
    return ticket, req, task


def _lock_token(token):
    return type(token).objects.select_for_update(no_key=True).get(pk=token.pk)


def expire_offers(now=None) -> int:
    now = now or timezone.now()
    due = list(Task.objects.filter(status=Task.Status.OFFERED)
               .filter(Q(offer_deadline__lte=now) | Q(hard_deadline__lte=now)).values_list("id", flat=True))
    expired = 0
    for task_id in due:
        with transaction.atomic():
            _ticket, _req, task = _lock_chain(task_id)
            if task is None or task.status != Task.Status.OFFERED:
                continue
            deadline = min(d for d in (task.offer_deadline, task.hard_deadline) if d)
            if deadline > now:
                continue
            _release_offer(task, now, AssignmentAttempt.Outcome.EXPIRED, "expired")
            expired += 1
    return expired


def _offer_still_valid(task, token, staff, now) -> bool:
    deadline = min(d for d in (task.offer_deadline, task.hard_deadline) if d)
    shift = shifts.open_shift_for(staff, task.event)
    return (task.status == Task.Status.OFFERED and task.assignee_id == staff.id
            and task.generation == token.generation and now <= deadline and staff.enabled and shift is not None)


def accept_task(staff, payload: str, now=None) -> str:
    """Returns accepted | duplicate | stale. All rules are rechecked at acceptance (docs/03 rule 8)."""
    now = now or timezone.now()
    with transaction.atomic():
        token = tokens.resolve(payload, lock=False)
        if token is None or token.staff_id != staff.id or token.purpose != "valet_accept" or token.task_id is None:
            return "stale"
        ticket, req, task = _lock_chain(token.task_id)
        if task is None:
            return "stale"
        token = _lock_token(token)
        if token.used_at and task.status == Task.Status.ACCEPTED and task.assignee_id == staff.id:
            return "duplicate"
        if tokens.state(token, now) != "valid" or not _offer_still_valid(task, token, staff, now):
            return "stale"
        from ops.services.holds import dispatch_blocked_ticket_ids

        if req.state != RetrievalRequest.State.OFFERED or req.current_task_id != task.id or \
                ticket.state != Ticket.State.PARKED or ticket.id in dispatch_blocked_ticket_ids(task.event):
            return "stale"
        task.status = Task.Status.ACCEPTED
        task.accepted_at = now
        task.save(update_fields=["status", "accepted_at"])
        AssignmentAttempt.objects.filter(task=task).update(outcome=AssignmentAttempt.Outcome.ACCEPTED, responded_at=now)
        req.state = RetrievalRequest.State.ACCEPTED
        req.accepted_at = now
        req.save(update_fields=["state", "accepted_at"])
        ticket.state = Ticket.State.RETRIEVING
        ticket.version += 1
        ticket.save(update_fields=["state", "version"])
        tokens.mark_used(token, now)
        tokens.revoke(task=task, purposes=["valet_decline"], now=now)
        ready = tokens.issue("valet_car_ready", staff=staff, task=task, ticket=ticket, generation=task.generation)
        outbox.enqueue("valet.assigned", staff=staff, ticket=ticket, task=task, template="valet.assigned", params={},
                       buttons=[(ready, "car_ready")], dedupe_key=f"valet.assigned:{task.id}", now=now)
        binding = ticket.bindings.filter(revoked_at__isnull=True).first()
        if binding is not None:
            outbox.enqueue("guest.accepted", binding=binding, ticket=ticket, template="guest.accepted", params={},
                           dedupe_key=f"guest.accepted:{req.id}", now=now)
        audit("dispatch.accepted", actor_id=staff.id, actor_label=actor_label(staff), channel="whatsapp",
              entity_type="ticket", entity_id=ticket.id, event_id=ticket.event_id, summary={"task_id": task.id})
    return "accepted"


def decline_task(staff, payload: str, now=None) -> str:
    """Returns declined | stale."""
    now = now or timezone.now()
    with transaction.atomic():
        token = tokens.resolve(payload, lock=False)
        if token is None or token.staff_id != staff.id or token.purpose != "valet_decline" or token.task_id is None:
            return "stale"
        _ticket, _req, task = _lock_chain(token.task_id)
        if task is None:
            return "stale"
        token = _lock_token(token)
        if tokens.state(token, now) != "valid" or task.status != Task.Status.OFFERED:
            return "stale"
        _release_offer(task, now, AssignmentAttempt.Outcome.DECLINED, "declined")
    return "declined"


def _offer_sent(row) -> None:
    task = Task.objects.select_for_update(no_key=True).filter(pk=row.task_id).first()
    if task is None or task.status != Task.Status.OFFERED or task.offer_sent_at is not None:
        return
    cfg = timings(task.event)
    task.offer_sent_at = row.sent_at
    task.offer_deadline = min(row.sent_at + timedelta(seconds=cfg["offer_window_s"]), task.hard_deadline)
    task.save(update_fields=["offer_sent_at", "offer_deadline"])


def _offer_failed(row) -> None:
    _ticket, _req, task = _lock_chain(row.task_id) if row.task_id else (None, None, None)
    if task is not None and task.status == Task.Status.OFFERED:
        _release_offer(task, row.sent_at or timezone.now(), AssignmentAttempt.Outcome.SEND_FAILED, "send_failed")


hooks.register("valet.offer", sent=_offer_sent, failed=_offer_failed)


def raise_alerts(now=None) -> int:
    """Supervisor attention items (docs/03 timing table). Alerts only — never automatic custody changes."""
    now = now or timezone.now()
    raised = 0
    for event in Event.objects.filter(status=Event.Status.OPEN):
        cfg = timings(event)
        open_reqs = RetrievalRequest.objects.filter(
            event=event, state__in=["QUEUED", "OFFERED", "WAITING_FOR_PARKING"]).select_related("ticket")
        for req in open_reqs:
            waited = (now - req.requested_at).total_seconds()
            if waited >= cfg["wait_warning_s"]:
                raised += bool(raise_alert(event, "wait_warning", ticket=req.ticket,
                                           dedupe_key=f"wait_warning:{req.id}"))
            if waited >= cfg["wait_critical_s"]:
                raised += bool(raise_alert(event, "wait_critical", ticket=req.ticket, severity="critical",
                                           dedupe_key=f"wait_critical:{req.id}"))
        for task in Task.objects.filter(event=event, status=Task.Status.OFFERED, offer_sent_at__isnull=True,
                                        reserved_at__lte=now - timedelta(seconds=cfg["send_pending_warning_s"])):
            raised += bool(raise_alert(event, "offer_send_pending", ticket=task.ticket,
                                       dedupe_key=f"offer_send_pending:{task.id}"))
        for task in Task.objects.filter(event=event, type=Task.Type.RETRIEVAL, status=Task.Status.ACCEPTED,
                                        ticket__state=Ticket.State.RETRIEVING,
                                        accepted_at__lte=now - timedelta(seconds=cfg["accepted_warning_s"])):
            raised += bool(raise_alert(event, "accepted_overdue", ticket=task.ticket,
                                       dedupe_key=f"accepted_overdue:{task.id}"))
        for ticket in Ticket.objects.filter(event=event, state=Ticket.State.READY,
                                            ready_at__lte=now - timedelta(seconds=cfg["ready_warning_s"])):
            raised += bool(raise_alert(event, "ready_waiting", ticket=ticket, dedupe_key=f"ready_waiting:{ticket.id}"))
    return raised
