"""Ready, collection-code verification and physical handover (docs/01 §6, docs/04, ADR-0006)."""

from django.db import transaction
from django.utils import timezone

from core.audit import audit
from core.context import staff_channel
from core.crypto import constant_time_equals, encrypt_text, keyed_hash, keyed_hash_candidates, new_code
from core.phone import normalize_digits
from messaging import hooks, outbox
from ops.models import CollectionCode, KeyOccupancy, RetrievalRequest, Task, Ticket
from ops.permissions import actor_label
from ops.services import shifts, tokens
from ops.services.alerts import raise_alert

MAX_CODE_ATTEMPTS = 5


def _t(ticket) -> str:
    return f"#{ticket.display_number:03d}"


def _verifier(ticket_id: int, code: str) -> str:
    return keyed_hash(f"{ticket_id}:{code}", "collection")


def _audit(action, actor, ticket, **summary):
    audit(action, actor_id=actor.id if actor else None, actor_label=actor_label(actor), channel=staff_channel(),
          entity_type="ticket", entity_id=ticket.id, event_id=ticket.event_id, summary=summary)


def issue_code(ticket, binding, now=None) -> CollectionCode:
    """New six-digit code; any previous live code is revoked. Plaintext lives only until sent."""
    now = now or timezone.now()
    ticket.codes.filter(consumed_at__isnull=True, revoked_at__isnull=True).update(revoked_at=now)
    code = new_code()
    row = CollectionCode.objects.create(ticket=ticket, binding=binding, verifier=_verifier(ticket.id, code),
                                        delivery_enc=encrypt_text(code))
    venue = ticket.event.venue
    pickup = venue.pickup_point_ar if binding.language == "ar" else venue.pickup_point_en
    outbox.enqueue("guest.ready", binding=binding, ticket=ticket, template="guest.ready",
                   params={"pickup_point": pickup, "__code_id": row.id}, dedupe_key=f"guest.ready:{row.id}", now=now)
    return row


def _wipe_code(row) -> None:
    code_id = (row.params or {}).get("__code_id")
    if code_id:
        CollectionCode.objects.filter(pk=code_id).update(delivery_enc="")


hooks.register("guest.ready", sent=_wipe_code)


def _lock_retrieval(token) -> tuple[Ticket, RetrievalRequest | None, Task]:
    """Lock order (ADR-0003): ticket → request → task."""
    ticket = Ticket.objects.select_for_update(no_key=True).get(pk=token.ticket_id)
    task = Task.objects.get(pk=token.task_id)
    req = RetrievalRequest.objects.select_for_update(no_key=True).filter(pk=task.request_id).first()
    task = Task.objects.select_for_update(no_key=True).get(pk=token.task_id)
    return ticket, req, task


def _resolve(staff, payload, purpose):
    token = tokens.resolve(payload, lock=False)
    if token is None or token.staff_id != staff.id or token.purpose != purpose or token.task_id is None:
        return None
    return token


def _current(task, staff, token) -> bool:
    return task.status == Task.Status.ACCEPTED and task.assignee_id == staff.id and task.generation == token.generation


def mark_ready(staff, payload: str, now=None) -> str:
    """Returns ready | duplicate | stale. Only the current accepted assignee can mark ready (docs/02)."""
    now = now or timezone.now()
    token = _resolve(staff, payload, "valet_car_ready")
    if token is None:
        return "stale"
    with transaction.atomic():
        ticket, req, task = _lock_retrieval(token)
        token = type(token).objects.select_for_update(no_key=True).get(pk=token.pk)
        if token.used_at and ticket.state == Ticket.State.READY and task.assignee_id == staff.id:
            return "duplicate"
        if tokens.state(token, now) != "valid" or not _current(task, staff, token) or \
                ticket.state != Ticket.State.RETRIEVING:
            return "stale"
        tokens.mark_used(token, now)
        _apply_ready(ticket, task, staff, now)
    return "ready"


def _lock_task(staff, task_id: int):
    """Staff app: the valet's own retrieval task, locked in the canonical order (ticket → request → task)."""
    ids = (Task.objects.filter(pk=task_id, assignee=staff, type=Task.Type.RETRIEVAL)
           .values_list("ticket_id", "request_id").first())
    if ids is None:
        return None, None, None
    ticket = Ticket.objects.select_for_update(no_key=True).get(pk=ids[0])
    req = RetrievalRequest.objects.select_for_update(no_key=True).filter(pk=ids[1]).first()
    task = Task.objects.select_for_update(no_key=True).get(pk=task_id)
    return ticket, req, task


def mark_ready_by(staff, task_id: int, now=None) -> str:
    """Staff app: the accepted valet reports the car at the pickup point. Returns ready | duplicate | stale."""
    now = now or timezone.now()
    with transaction.atomic():
        ticket, _req, task = _lock_task(staff, task_id)
        if task is None or task.status != Task.Status.ACCEPTED or task.assignee_id != staff.id:
            return "stale"
        if ticket.state == Ticket.State.READY:
            return "duplicate"
        if ticket.state != Ticket.State.RETRIEVING:
            return "stale"
        tokens.revoke(task=task, purposes=["valet_car_ready"], now=now)
        _apply_ready(ticket, task, staff, now)
    return "ready"


def deliver(staff, task_id: int, now=None) -> str:
    """Staff app: physical handover after the code was verified. Returns delivered | duplicate | blocked |
    unverified | stale."""
    from ops.services import holds

    now = now or timezone.now()
    with transaction.atomic():
        ticket, req, task = _lock_task(staff, task_id)
        if task is None:
            return "stale"
        if ticket.state == Ticket.State.DELIVERED and ticket.delivered_by_id == staff.id:
            return "duplicate"
        if task.status != Task.Status.ACCEPTED or task.assignee_id != staff.id or ticket.state != Ticket.State.READY:
            return "stale"
        if holds.handover_blocked(ticket):
            return "blocked"
        code = _handover_verified(ticket)
        if code is None:
            return "unverified"
        finalize_delivery(staff, ticket, req, task, now, code=code)
    return "delivered"


def _apply_ready(ticket, task, staff, now, *, relayed_by=None, confirmed_via: str = "") -> None:
    ticket.state = Ticket.State.READY
    ticket.ready_at = now
    ticket.version += 1
    ticket.save(update_fields=["state", "ready_at", "version"])
    binding = ticket.bindings.filter(revoked_at__isnull=True).first()
    if binding is not None:
        issue_code(ticket, binding, now)
    extra = {"relayed_by": relayed_by.id, "confirmed_via": confirmed_via} if relayed_by is not None else {}
    _audit("ticket.ready", staff, ticket, task_id=task.id, **extra)


def mark_ready_relayed(actor, task, confirmed_via: str, now=None) -> None:
    """WhatsApp outage (ADR-0008): the supervisor records the accepted valet's "car ready" report."""
    from core.errors import DomainError

    now = now or timezone.now()
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update(no_key=True).get(pk=task.ticket_id)
        RetrievalRequest.objects.select_for_update(no_key=True).filter(ticket=ticket,
                                                                       state=RetrievalRequest.State.ACCEPTED).first()
        task = Task.objects.select_for_update(no_key=True).get(pk=task.pk)
        if task.type != Task.Type.RETRIEVAL or task.status != Task.Status.ACCEPTED or \
                ticket.state != Ticket.State.RETRIEVING:
            raise DomainError("stale")
        tokens.revoke(task=task, purposes=["valet_car_ready"], now=now)
        _apply_ready(ticket, task, task.assignee, now, relayed_by=actor, confirmed_via=confirmed_via)


def verify_collection(staff, ticket, code_text: str, now=None) -> tuple[str, int]:
    """Returns (ok | wrong | locked | stale, remaining_attempts). Server validation is authoritative."""
    now = now or timezone.now()
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update(no_key=True).get(pk=ticket.pk)
        task = Task.objects.filter(ticket=ticket, type=Task.Type.RETRIEVAL, status=Task.Status.ACCEPTED).first()
        if ticket.state != Ticket.State.READY or task is None or task.assignee_id != staff.id:
            return "stale", 0
        code = ticket.codes.select_for_update(no_key=True).filter(consumed_at__isnull=True,
                                                                  revoked_at__isnull=True).first()
        if code is None:
            return "stale", 0
        if code.locked_at is not None:
            return "locked", 0
        if code.verified_at is not None:
            return "ok", MAX_CODE_ATTEMPTS - code.failed_attempts
        candidate = normalize_digits(code_text or "").strip().replace(" ", "")
        if candidate.isdigit() and len(candidate) == 6 and any(
                constant_time_equals(verifier, code.verifier)  # current and, mid-rotation, previous hash key
                for verifier in keyed_hash_candidates(f"{ticket.id}:{candidate}", "collection")):
            code.verified_at = now
            code.verified_by = staff
            code.save(update_fields=["verified_at", "verified_by"])
            delivered = tokens.issue("valet_delivered", staff=staff, task=task, ticket=ticket,
                                     generation=task.generation)
            vehicle = " ".join(p for p in (ticket.vehicle_plate, ticket.vehicle_description) if p) or "—"
            outbox.enqueue("valet.code_ok", staff=staff, ticket=ticket, task=task, template="valet.code_ok",
                           params={"ticket": _t(ticket), "vehicle": vehicle}, buttons=[(delivered, "delivered")],
                           dedupe_key=f"valet.code_ok:{code.id}", now=now)
            _audit("handover.code_verified", staff, ticket)
            return "ok", MAX_CODE_ATTEMPTS - code.failed_attempts
        code.failed_attempts += 1
        if code.failed_attempts >= MAX_CODE_ATTEMPTS:
            code.locked_at = now
            code.save(update_fields=["failed_attempts", "locked_at"])
            raise_alert(ticket.event, "code_locked", ticket=ticket, severity="critical",
                        dedupe_key=f"code_locked:{code.id}")
            _audit("handover.code_locked", staff, ticket)
            return "locked", 0
        code.save(update_fields=["failed_attempts"])
        _audit("handover.code_wrong", staff, ticket, attempts=code.failed_attempts)
        return "wrong", MAX_CODE_ATTEMPTS - code.failed_attempts


def _handover_verified(ticket) -> CollectionCode | None:
    return ticket.codes.filter(consumed_at__isnull=True, revoked_at__isnull=True, verified_at__isnull=False,
                               locked_at__isnull=True).first()


def finalize_delivery(staff, ticket, req, task, now, *, code=None, channel=None) -> None:
    """Close only after actual handover: release valet, key hook and credentials; ask for a rating."""
    from ops.services import holds

    ticket.state = Ticket.State.DELIVERED
    ticket.delivered_at = now
    ticket.delivered_by = task.assignee
    ticket.version += 1
    ticket.save(update_fields=["state", "delivered_at", "delivered_by", "version"])
    task.status = Task.Status.COMPLETED
    task.completed_at = now
    task.save(update_fields=["status", "completed_at"])
    if req is not None:
        req.state = RetrievalRequest.State.COMPLETED
        req.completed_at = now
        req.save(update_fields=["state", "completed_at"])
    if code is not None:
        code.consumed_at = now
        code.save(update_fields=["consumed_at"])
    ticket.codes.filter(consumed_at__isnull=True, revoked_at__isnull=True).update(revoked_at=now)
    KeyOccupancy.objects.filter(ticket=ticket, released_at__isnull=True).update(
        released_at=now, released_by=staff, release_reason="delivered")
    tokens.revoke(ticket=ticket, now=now)
    shifts.on_task_released(task.assignee, now)
    holds.on_delivered(ticket)
    binding = ticket.bindings.filter(revoked_at__isnull=True).first()
    if binding is not None:
        buttons = [(tokens.issue("guest_rate", ticket=ticket, binding=binding, data={"value": value}), key)
                   for value, key in (("EXCELLENT", "rate_excellent"), ("OKAY", "rate_okay"), ("POOR", "rate_poor"))]
        outbox.enqueue("guest.delivered", binding=binding, ticket=ticket, template="guest.delivered", params={},
                       buttons=buttons, dedupe_key=f"guest.delivered:{ticket.id}", now=now)
    outbox.enqueue("valet.delivered_done", staff=task.assignee, ticket=ticket, template="valet.delivered_done",
                   params={"ticket": _t(ticket)}, dedupe_key=f"valet.delivered_done:{ticket.id}", now=now)
    audit("ticket.delivered", actor_id=staff.id, actor_label=actor_label(staff), channel=channel or staff_channel(),
          entity_type="ticket", entity_id=ticket.id, event_id=ticket.event_id,
          summary={"task_id": task.id, "verification": "code" if code else "assisted"})


def complete_handover(staff, payload: str, now=None) -> str:
    """Returns delivered | duplicate | blocked | stale. A verified code authorizes eligibility; only this
    physical-delivery confirmation closes the ticket."""
    from ops.services import holds

    now = now or timezone.now()
    token = _resolve(staff, payload, "valet_delivered")
    if token is None:
        return "stale"
    with transaction.atomic():
        ticket, req, task = _lock_retrieval(token)
        if ticket.state == Ticket.State.DELIVERED and ticket.delivered_by_id == staff.id:
            return "duplicate"
        token = type(token).objects.select_for_update(no_key=True).get(pk=token.pk)
        if tokens.state(token, now) != "valid" or not _current(task, staff, token) or \
                ticket.state != Ticket.State.READY:
            return "stale"
        if holds.handover_blocked(ticket):
            return "blocked"
        code = _handover_verified(ticket)
        if code is None:
            return "stale"
        tokens.mark_used(token, now)
        finalize_delivery(staff, ticket, req, task, now, code=code)
    return "delivered"


def assisted_handover(actor, ticket, method: str, reason: str, now=None) -> None:
    """Guest cannot use the code (no phone/WhatsApp): the supervisor verifies ownership in person and records how.
    Identity-document photos are never required. The delivering valet stays the task's assignee."""
    from core.errors import DomainError
    from ops.models import AssistedVerification, Role
    from ops.permissions import require
    from ops.services import holds

    now = now or timezone.now()
    require(actor, Role.SUPERVISOR, ticket.event)
    if method not in AssistedVerification.Method.values or not reason.strip():
        raise DomainError("reason_required")
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update(no_key=True).get(pk=ticket.pk)
        req = RetrievalRequest.objects.select_for_update(no_key=True).filter(
            ticket=ticket, state=RetrievalRequest.State.ACCEPTED).first()
        task = Task.objects.select_for_update(no_key=True).filter(
            ticket=ticket, type=Task.Type.RETRIEVAL, status=Task.Status.ACCEPTED).first()
        if ticket.state != Ticket.State.READY or task is None:
            raise DomainError("invalid_state")
        if holds.handover_blocked(ticket):
            raise DomainError("handover_blocked")
        AssistedVerification.objects.create(ticket=ticket, verified_by=actor, method=method,
                                            reason=reason.strip()[:200])
        ticket.contact_state = Ticket.Contact.ASSISTED_FALLBACK
        ticket.save(update_fields=["contact_state"])
        finalize_delivery(actor, ticket, req, task, now, code=None, channel="console")
