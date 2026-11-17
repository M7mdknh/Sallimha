"""Explicit vehicle relocation (docs/02, ADR-0007).

A supervisor-initiated move is an *offer* to one named valet. Nothing physical is recorded until it happens:
- the valet accepts in WhatsApp (custody of car and key passes to them, as with a retrieval);
- the ticket's confirmed location and key hook change only when the move is completed, by the mover in
  WhatsApp or by a supervisor who confirmed it in person or by radio — never before acceptance;
- declined or expired offers return to the supervisor (alert) and are never reassigned automatically;
- a new retrieval waits until the movement custody is released.
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import audit
from core.context import staff_channel
from core.errors import DomainError
from messaging import outbox
from ops.models import KeyOccupancy, ParkingZone, Role, Task, Ticket
from ops.permissions import actor_label, require
from ops.services import shifts, tokens

CONFIRMED_VIA = ("in_person", "radio")


def _t(ticket) -> str:
    return f"#{ticket.display_number:03d}"


def _location(ticket) -> str:
    return f"{ticket.location_zone.code} {ticket.location_detail}".strip() if ticket.location_zone_id else "—"


def _hook(ticket) -> str:
    occ = ticket.key_occupancies.filter(released_at__isnull=True).first()
    return str(occ.hook_number) if occ else "—"


def _audit(action, actor, ticket, channel, **summary):
    audit(action, actor_id=actor.id if actor else None, actor_label=actor_label(actor) if actor else "worker",
          channel=channel, entity_type="ticket", entity_id=ticket.id, event_id=ticket.event_id, summary=summary)


def _lock(task_id: int) -> tuple[Ticket, Task]:
    """Canonical lock order (ADR-0003): ticket → task → shift → key → tokens."""
    ticket_id = Task.objects.filter(pk=task_id).values_list("ticket_id", flat=True).get()
    ticket = Ticket.objects.select_for_update(no_key=True).get(pk=ticket_id)
    task = Task.objects.select_for_update(no_key=True).get(pk=task_id)
    if task.type != Task.Type.RELOCATION:
        raise DomainError("invalid_state")
    return ticket, task


def start_relocation(actor, ticket, valet, reason: str, now=None) -> Task:
    from ops.services.dispatch import _local_time, timings
    from ops.services.holds import dispatch_blocked_ticket_ids

    now = now or timezone.now()
    require(actor, Role.SUPERVISOR, ticket.event)
    if not reason.strip():
        raise DomainError("reason_required")
    if valet.org_id != ticket.event.org_id or not shifts.is_available(valet, ticket.event):
        raise DomainError("receiver_unavailable")
    deadline = now + timedelta(seconds=timings(ticket.event)["hard_limit_s"])
    try:
        with transaction.atomic():
            ticket = Ticket.objects.select_for_update(no_key=True).get(pk=ticket.pk)
            if ticket.state != Ticket.State.PARKED:
                raise DomainError("invalid_state")
            if ticket.id in dispatch_blocked_ticket_ids(ticket.event):
                raise DomainError("hold_active")  # a movement-blocking hold also blocks moves (docs/03 rule 2)
            task = Task.objects.create(event=ticket.event, ticket=ticket, type=Task.Type.RELOCATION,
                                       status=Task.Status.OFFERED, assignee=valet, reserved_at=now,
                                       offer_sent_at=now, offer_deadline=deadline, hard_deadline=deadline)
            accept = tokens.issue("relocation_accept", staff=valet, task=task, ticket=ticket,
                                  generation=task.generation, expires_at=deadline)
            decline = tokens.issue("relocation_decline", staff=valet, task=task, ticket=ticket,
                                   generation=task.generation, expires_at=deadline)
            vehicle = " ".join(p for p in (ticket.vehicle_plate, ticket.vehicle_description) if p) or "—"
            outbox.enqueue("valet.relocation_offer", staff=valet, ticket=ticket, task=task,
                           template="valet.relocation_offer",
                           params={"ticket": _t(ticket), "vehicle": vehicle, "location": _location(ticket),
                                   "hook": _hook(ticket), "reason": reason.strip()[:120],
                                   "expires": _local_time(deadline)},
                           buttons=[(accept, "accept"), (decline, "decline")],
                           dedupe_key=f"valet.relocation_offer:{task.id}", now=now)
            _audit("relocation.offer", actor, ticket, "console", task_id=task.id, valet=valet.id,
                   reason=reason.strip()[:200], **{"from": _location(ticket), "from_hook": _hook(ticket)})
    except IntegrityError as exc:
        raise DomainError("busy") from exc
    return task


def _release(task, ticket, now, reason: str, actor=None, channel="worker") -> None:
    from ops.services.alerts import raise_alert

    task.status = Task.Status.RELEASED
    task.released_at = now
    task.release_reason = reason
    task.save(update_fields=["status", "released_at", "release_reason"])
    tokens.revoke(task=task, now=now)
    outbox.supersede(task=task, kinds=("valet.relocation_offer", "valet.relocation_accepted"), now=now)
    shifts.on_task_released(task.assignee, now)
    if reason in {"declined", "expired"}:
        raise_alert(task.event, "relocation_declined", ticket=ticket, dedupe_key=f"relocation_declined:{task.id}",
                    detail={"task_id": task.id, "valet": task.assignee_id, "outcome": reason})
    _audit(f"relocation.{reason}", actor or task.assignee, ticket, channel, task_id=task.id,
           valet=task.assignee_id)


def _resolve(staff, payload: str, purpose: str):
    token = tokens.resolve(payload, lock=False)
    if token is None or token.staff_id != staff.id or token.purpose != purpose or token.task_id is None:
        return None
    return token


def accept_relocation(staff, payload: str, now=None) -> str:
    """Returns accepted | duplicate | stale. Shift, hold and deadline are rechecked at acceptance."""
    from ops.services.holds import dispatch_blocked_ticket_ids

    now = now or timezone.now()
    token = _resolve(staff, payload, "relocation_accept")
    if token is None:
        return "stale"
    with transaction.atomic():
        ticket, task = _lock(token.task_id)
        token = type(token).objects.select_for_update(no_key=True).get(pk=token.pk)
        if token.used_at and task.status == Task.Status.ACCEPTED and task.assignee_id == staff.id:
            return "duplicate"
        if (tokens.state(token, now) != "valid" or task.status != Task.Status.OFFERED
                or task.assignee_id != staff.id or now > task.offer_deadline or not staff.enabled
                or shifts.open_shift_for(staff, task.event) is None or ticket.state != Ticket.State.PARKED
                or ticket.id in dispatch_blocked_ticket_ids(task.event)):
            return "stale"
        tokens.mark_used(token, now)
        tokens.revoke(task=task, purposes=["relocation_decline"], now=now)
        _apply_acceptance(ticket, task, staff, now)
    return "accepted"


def accept_move(staff, task_id: int, now=None) -> str:
    """Staff app: the named valet accepts the move. Returns accepted | duplicate | stale."""
    from ops.services.holds import dispatch_blocked_ticket_ids

    now = now or timezone.now()
    if not Task.objects.filter(pk=task_id, assignee=staff, type=Task.Type.RELOCATION).exists():
        return "stale"
    with transaction.atomic():
        ticket, task = _lock(task_id)
        if task.assignee_id != staff.id:
            return "stale"
        if task.status == Task.Status.ACCEPTED:
            return "duplicate"
        if (task.status != Task.Status.OFFERED or now > task.offer_deadline or not staff.enabled
                or shifts.open_shift_for(staff, task.event) is None or ticket.state != Ticket.State.PARKED
                or ticket.id in dispatch_blocked_ticket_ids(task.event)):
            return "stale"
        tokens.revoke(task=task, purposes=["relocation_accept", "relocation_decline"], now=now)
        _apply_acceptance(ticket, task, staff, now)
    return "accepted"


def decline_move(staff, task_id: int, now=None) -> str:
    """Staff app. Returns declined | stale."""
    now = now or timezone.now()
    if not Task.objects.filter(pk=task_id, assignee=staff, type=Task.Type.RELOCATION).exists():
        return "stale"
    with transaction.atomic():
        ticket, task = _lock(task_id)
        if task.status != Task.Status.OFFERED or task.assignee_id != staff.id:
            return "stale"
        _release(task, ticket, now, "declined", actor=staff, channel=staff_channel())
    return "declined"


def _apply_acceptance(ticket, task, staff, now, *, relayed_by=None, confirmed_via: str = "") -> None:
    task.status = Task.Status.ACCEPTED
    task.accepted_at = now
    task.save(update_fields=["status", "accepted_at"])
    moved = tokens.issue("relocation_moved", staff=staff, task=task, ticket=ticket, generation=task.generation)
    outbox.enqueue("valet.relocation_accepted", staff=staff, ticket=ticket, task=task,
                   template="valet.relocation_accepted", params={"ticket": _t(ticket)},
                   buttons=[(moved, "moved")], dedupe_key=f"valet.relocation_accepted:{task.id}", now=now)
    extra = {"relayed_by": relayed_by.id, "confirmed_via": confirmed_via} if relayed_by is not None else {}
    _audit("relocation.accepted", staff, ticket, "console" if relayed_by is not None else staff_channel(),
           task_id=task.id, **extra)


def accept_relayed(actor, task, confirmed_via: str, now=None) -> None:
    """WhatsApp outage (ADR-0008): the supervisor records the chosen valet's acceptance of the move."""
    from ops.services.holds import dispatch_blocked_ticket_ids

    now = now or timezone.now()
    with transaction.atomic():
        ticket, task = _lock(task.pk)
        staff = task.assignee
        if (task.status != Task.Status.OFFERED or now > task.offer_deadline or not staff.enabled
                or shifts.open_shift_for(staff, task.event) is None or ticket.state != Ticket.State.PARKED
                or ticket.id in dispatch_blocked_ticket_ids(task.event)):
            raise DomainError("stale")
        tokens.revoke(task=task, purposes=["relocation_accept", "relocation_decline"], now=now)
        _apply_acceptance(ticket, task, staff, now, relayed_by=actor, confirmed_via=confirmed_via)


def decline_relocation(staff, payload: str, now=None) -> str:
    """Returns declined | stale."""
    now = now or timezone.now()
    token = _resolve(staff, payload, "relocation_decline")
    if token is None:
        return "stale"
    with transaction.atomic():
        ticket, task = _lock(token.task_id)
        token = type(token).objects.select_for_update(no_key=True).get(pk=token.pk)
        if tokens.state(token, now) != "valid" or task.status != Task.Status.OFFERED or task.assignee_id != staff.id:
            return "stale"
        _release(task, ticket, now, "declined", actor=staff, channel=staff_channel())
    return "declined"


def expire_offers(now=None) -> int:
    """Worker step: unanswered move offers return to the supervisor (alert); never reassigned automatically."""
    now = now or timezone.now()
    due = list(Task.objects.filter(type=Task.Type.RELOCATION, status=Task.Status.OFFERED, offer_deadline__lte=now)
               .values_list("id", flat=True))
    expired = 0
    for task_id in due:
        with transaction.atomic():
            ticket, task = _lock(task_id)
            if task.status != Task.Status.OFFERED or task.offer_deadline > now:
                continue
            _release(task, ticket, now, "expired")
            expired += 1
    return expired


def mover_task(staff, payload: str, now=None) -> Task | None:
    """The mover pressed "Moved": the task they accepted, so the conversation can ask for the new location."""
    token = _resolve(staff, payload, "relocation_moved")
    if token is None or tokens.state(token, now or timezone.now()) != "valid":
        return None
    task = Task.objects.filter(pk=token.task_id, type=Task.Type.RELOCATION, status=Task.Status.ACCEPTED,
                               assignee=staff).first()
    return task


def complete_relocation(actor, task, *, zone_code: str, detail: str, hook_number: int, confirmed_via: str = "",
                        now=None) -> Ticket:
    """Records the move. The mover may complete their own accepted move; a supervisor may record it only after
    acceptance and only having confirmed it in person or by radio. The mover is always the accepting valet."""
    now = now or timezone.now()
    by_mover = actor.id == task.assignee_id and actor.role == Role.VALET
    if not by_mover:
        require(actor, Role.SUPERVISOR, task.event)
        if confirmed_via not in CONFIRMED_VIA:
            raise DomainError("confirmation_required")
    try:
        with transaction.atomic():
            ticket, task = _lock(task.pk)
            if task.status in (Task.Status.OFFERED, Task.Status.RESERVED):
                raise DomainError("not_accepted")
            if task.status != Task.Status.ACCEPTED or (by_mover and task.assignee_id != actor.id):
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
            previous, previous_hook = _location(ticket), (old.hook_number if old else None)
            if old is None or old.hook_number != int(hook_number):
                if old is not None:
                    old.released_at, old.released_by, old.release_reason = now, task.assignee, "relocated"
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
            tokens.revoke(task=task, now=now)
            shifts.on_task_released(task.assignee, now)
            location = _location(ticket)
            outbox.enqueue("valet.relocation_done", staff=task.assignee, ticket=ticket, task=task,
                           template="valet.relocation_done",
                           params={"ticket": _t(ticket), "location": location, "hook": str(int(hook_number))},
                           dedupe_key=f"valet.relocation_done:{task.id}", now=now)
            _audit("relocation.complete", actor, ticket, staff_channel() if by_mover else "console", task_id=task.id,
                   mover=task.assignee_id, recorded_by=actor.id, confirmed_via="mover" if by_mover else confirmed_via,
                   hook=int(hook_number), from_hook=previous_hook, accepted_at=task.accepted_at.isoformat(),
                   **{"from": previous, "to": location})
    except IntegrityError as exc:
        raise DomainError("hook_occupied") from exc
    return ticket


def cancel_relocation(actor, task, *, reason: str, car_returned: bool, now=None) -> Task:
    """An offered move can be withdrawn freely. An accepted move means a valet holds the car and key, so the
    supervisor must confirm both are back at the recorded location and hook before custody is released."""
    now = now or timezone.now()
    require(actor, Role.SUPERVISOR, task.event)
    if not reason.strip():
        raise DomainError("reason_required")
    with transaction.atomic():
        ticket, task = _lock(task.pk)
        if task.status == Task.Status.ACCEPTED and not car_returned:
            raise DomainError("custody_resolution_required")
        if task.status not in (Task.Status.OFFERED, Task.Status.ACCEPTED):
            raise DomainError("invalid_state")
        was = task.status
        _release(task, ticket, now, "cancelled", actor=actor, channel="console")
        outbox.enqueue("valet.relocation_cancelled", staff=task.assignee, ticket=ticket, task=task,
                       template="valet.relocation_cancelled", params={"ticket": _t(ticket)},
                       dedupe_key=f"valet.relocation_cancelled:{task.id}", now=now)
        _audit("relocation.cancel_detail", actor, ticket, "console", task_id=task.id, was=was,
               reason=reason.strip()[:200], car_returned=bool(car_returned), location=_location(ticket),
               hook=_hook(ticket))
    return task
