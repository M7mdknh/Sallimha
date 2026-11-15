"""Guest retrieval requests, withdrawal and phone correction (docs/01 §4, docs/02, ADR-0005 C2)."""

from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from core.audit import audit
from core.errors import DomainError
from messaging import outbox
from messaging.catalogue import REQUEST_STATUS
from ops.models import OPEN_REQUEST_STATES, AssignmentAttempt, RetrievalRequest, Role, Task, Ticket
from ops.permissions import actor_label, require
from ops.services import shifts, tokens


def _t(ticket) -> str:
    return f"#{ticket.display_number:03d}"


def _audit(action, actor, ticket, channel, **summary):
    audit(action, actor_id=actor.id if actor else None, actor_label=actor_label(actor), channel=channel,
          entity_type="ticket", entity_id=ticket.id, event_id=ticket.event_id, summary=summary)


def wake_dispatcher() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_notify('sallimha_work', 'dispatch')")


def open_request(ticket):
    return RetrievalRequest.objects.filter(ticket=ticket, state__in=OPEN_REQUEST_STATES).first()


def _status_text(req, ticket, language):
    key = "READY" if ticket.state == Ticket.State.READY else req.state
    return REQUEST_STATUS[key][language if language in ("ar", "en") else "ar"]


def request_retrieval(binding, ticket, *, via: str = "guest_whatsapp", actor=None, source_id: str = "",
                      now=None) -> tuple[RetrievalRequest, bool]:
    now = now or timezone.now()
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
        if ticket.state not in (Ticket.State.RECEIVED, Ticket.State.PARKED, Ticket.State.RETRIEVING,
                                Ticket.State.READY):
            raise DomainError("ticket_closed")
        existing = open_request(ticket)
        reply_key = source_id or f"{int(now.timestamp() * 1000)}"
        if existing is not None:
            if binding is not None:
                outbox.enqueue("guest.duplicate", binding=binding, ticket=ticket, template="guest.duplicate",
                               params={"status": _status_text(existing, ticket, binding.language)},
                               dedupe_key=f"guest.duplicate:{ticket.id}:{reply_key}", now=now)
            return existing, False
        state = (RetrievalRequest.State.QUEUED if ticket.state == Ticket.State.PARKED
                 else RetrievalRequest.State.WAITING_FOR_PARKING)
        try:
            with transaction.atomic():
                req = RetrievalRequest.objects.create(
                    event=ticket.event, ticket=ticket, binding=binding, state=state, requested_at=now,
                    eligible_at=now if state == RetrievalRequest.State.QUEUED else None, requested_via=via,
                    assisted_by=actor)
        except IntegrityError:
            return open_request(ticket), False
        if binding is not None:
            template = "guest.queued" if state == RetrievalRequest.State.QUEUED else "guest.early_request"
            outbox.enqueue(template, binding=binding, ticket=ticket, template=template,
                           params={"ticket": _t(ticket)}, dedupe_key=f"{template}:{req.id}", now=now)
        _audit("request.create", actor, ticket, "console" if actor else "whatsapp", via=via, state=state)
        wake_dispatcher()
    return req, True


def supersede_offer(req, now, reason: str) -> None:
    """Release an unaccepted offer's reservation; its action references die forever."""
    task = Task.objects.select_for_update().filter(request=req, status__in=["RESERVED", "OFFERED"]).first()
    if task is None:
        return
    task.status = Task.Status.RELEASED
    task.released_at = now
    task.release_reason = reason
    task.save(update_fields=["status", "released_at", "release_reason"])
    AssignmentAttempt.objects.filter(task=task, outcome="PENDING").update(outcome="SUPERSEDED", responded_at=now)
    tokens.revoke(task=task, now=now)
    shifts.on_task_released(task.assignee, now)


def withdraw_request(actor, req, reason: str, now=None) -> RetrievalRequest:
    """Supervisor withdrawal before acceptance; vehicle stays PARKED, ticket stays open (ADR-0005 C2)."""
    now = now or timezone.now()
    require(actor, Role.SUPERVISOR, req.event)
    if not reason.strip():
        raise DomainError("reason_required")
    with transaction.atomic():
        req = RetrievalRequest.objects.select_for_update().get(pk=req.pk)
        if req.state == RetrievalRequest.State.ACCEPTED:
            raise DomainError("custody_resolution_required")
        if req.state not in ("WAITING_FOR_PARKING", "QUEUED", "OFFERED"):
            raise DomainError("invalid_state")
        supersede_offer(req, now, "withdrawn")
        req.state = RetrievalRequest.State.WITHDRAWN
        req.withdrawn_at = now
        req.withdrawn_by = actor
        req.withdraw_reason = reason.strip()[:200]
        req.save(update_fields=["state", "withdrawn_at", "withdrawn_by", "withdraw_reason"])
        ticket = req.ticket
        binding = ticket.bindings.filter(revoked_at__isnull=True).first()
        if binding is not None:
            outbox.enqueue("guest.withdrawn", binding=binding, ticket=ticket, template="guest.withdrawn",
                           params={"ticket": _t(ticket)}, dedupe_key=f"guest.withdrawn:{req.id}", now=now)
        _audit("request.withdraw", actor, ticket, "console", reason=req.withdraw_reason)
    return req


def correct_guest_phone(actor, ticket, raw_phone: str, reason: str, now=None):
    """After a ticket was sent: supervisor verification, revoke old credentials, reissue (docs/04)."""
    from core.phone import PhoneInvalid, parse_phone
    from ops.services.intake import _create_binding, send_ticket

    now = now or timezone.now()
    require(actor, Role.SUPERVISOR, ticket.event)
    if not reason.strip():
        raise DomainError("reason_required")
    try:
        parsed = parse_phone(raw_phone)
    except PhoneInvalid as exc:
        raise DomainError("phone_invalid") from exc
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
        if ticket.state not in (Ticket.State.RECEIVED, Ticket.State.PARKED, Ticket.State.RETRIEVING,
                                Ticket.State.READY):
            raise DomainError("ticket_closed")
        old = ticket.bindings.select_for_update().filter(revoked_at__isnull=True).first()
        revision = (ticket.bindings.order_by("-revision").values_list("revision", flat=True).first() or 0) + 1
        if old is not None:
            old.revoked_at = now
            old.revoke_reason = "phone_corrected"
            old.save(update_fields=["revoked_at", "revoke_reason"])
            tokens.revoke(binding=old, now=now)
        ticket.codes.filter(consumed_at__isnull=True, revoked_at__isnull=True).update(revoked_at=now)
        binding = _create_binding(ticket, parsed.e164, old.language if old else ticket.guest_language, actor,
                                  revision, now)
        RetrievalRequest.objects.filter(ticket=ticket, state__in=OPEN_REQUEST_STATES).update(binding=binding)
        ticket.contact_state = Ticket.Contact.CORRECTION_REQUIRED
        ticket.version += 1
        ticket.save(update_fields=["contact_state", "version"])
        send_ticket(ticket, binding, now)
        if ticket.state == Ticket.State.READY:
            from ops.services.handover import issue_code

            issue_code(ticket, binding, now)
        _audit("guest.phone_corrected", actor, ticket, "console", old=old.phone_masked if old else "",
               new=binding.phone_masked, reason=reason.strip()[:200])
    return binding
