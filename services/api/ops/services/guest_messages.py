"""The customer's ticket message, as the provider reports it (ADR-0013). Replaces the staff receipt question.

Status comes only from the outbox row and the provider's status events: queued is not sent, sent is not delivered,
and an unknown outcome is neither. A failed or dead customer message raises one supervisor issue per ticket and phone
binding; the supervisor corrects the number (existing, audited, revokes old credentials) or resends the ticket."""

from django.db import transaction
from django.utils import timezone

from core.audit import audit
from core.errors import DomainError
from messaging import hooks
from messaging.models import MessageOutbox
from ops.models import Alert, Role, Ticket
from ops.permissions import actor_label, require
from ops.services.alerts import raise_alert

S = MessageOutbox.Status
SHOWN = {S.PENDING: "queued", S.SENDING: "queued", S.SENT: "sent", S.DELIVERED: "delivered", S.READ: "read",
         S.FAILED: "failed", S.DEAD: "failed", S.DELIVERY_UNKNOWN: "unknown", S.OBSOLETE: "not_sent"}
RESENDABLE = (S.FAILED, S.DEAD, S.DELIVERY_UNKNOWN)
OPEN_STATES = (Ticket.State.RECEIVED, Ticket.State.PARKED, Ticket.State.RETRIEVING, Ticket.State.READY)
WATCHED = ("guest.ticket", "guest.ready")  # the ticket itself and the collection code


def _ticket_row(ticket):
    binding = ticket.bindings.filter(revoked_at__isnull=True).first()
    if binding is None:
        return None
    return MessageOutbox.objects.filter(ticket=ticket, binding=binding, kind="guest.ticket").order_by("-id").first()


def ticket_message(ticket) -> str | None:
    """queued | sent | delivered | read | failed | unknown | not_sent, or None when no ticket was sent."""
    row = _ticket_row(ticket)
    return SHOWN.get(row.status) if row is not None else None


def ticket_message_detail(ticket) -> dict | None:
    row = _ticket_row(ticket)
    if row is None:
        return None
    return {"status": SHOWN.get(row.status), "queued_at": row.created_at,
            "error": row.last_error if row.status in (S.FAILED, S.DEAD) else ""}


def can_resend(ticket) -> bool:
    row = _ticket_row(ticket)
    return bool(row is not None and row.status in RESENDABLE and ticket.state in OPEN_STATES)


def _failed(row) -> None:
    ticket, binding = row.ticket, row.binding
    if ticket is None or binding is None or binding.revoked_at is not None or ticket.state not in OPEN_STATES:
        return
    raise_alert(ticket.event, "guest_message_failed", ticket=ticket, severity="critical",
                dedupe_key=f"guest_message_failed:{ticket.id}:{binding.revision}",
                detail={"kind": row.kind})


def _close_issue(actor, ticket, now) -> None:
    Alert.objects.filter(ticket=ticket, kind="guest_message_failed", acknowledged_at__isnull=True).update(
        acknowledged_at=now, acknowledged_by=actor)


def resend_ticket(actor, ticket, now=None) -> MessageOutbox:
    """Supervisor: queue the ticket message again for the current number, only when the last attempt failed or its
    outcome is unknown (the supervisor checks with the customer first, as an unknown one may have arrived)."""
    from messaging import outbox
    from ops.services import tokens

    now = now or timezone.now()
    require(actor, Role.SUPERVISOR, ticket.event)
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update(no_key=True).get(pk=ticket.pk)
        if ticket.state not in OPEN_STATES:
            raise DomainError("ticket_closed")
        binding = ticket.bindings.filter(revoked_at__isnull=True).first()
        if binding is None:
            raise DomainError("no_contact")
        last = _ticket_row(ticket)
        if last is None or last.status not in RESENDABLE:
            raise DomainError("message_not_failed")
        attempt = MessageOutbox.objects.filter(ticket=ticket, binding=binding, kind="guest.ticket").count()
        token = tokens.issue("guest_request", ticket=ticket, binding=binding)
        row = outbox.enqueue("guest.ticket", binding=binding, ticket=ticket, template="guest.ticket",
                             params={"ticket": f"#{ticket.display_number:03d}", "venue": ticket.event.venue.name},
                             buttons=[(token, "request_car")],
                             dedupe_key=f"guest.ticket:{ticket.id}:{binding.revision}:resend:{attempt}", now=now)
        _close_issue(actor, ticket, now)
        audit("guest.ticket_resent", actor_id=actor.id, actor_label=actor_label(actor), channel="console",
              entity_type="ticket", entity_id=ticket.id, event_id=ticket.event_id,
              summary={"previous": last.status, "attempt": attempt + 1})
    return row


def close_issue_after_correction(actor, ticket, now) -> None:
    _close_issue(actor, ticket, now)


def register() -> None:
    for kind in WATCHED:
        hooks.register(kind, failed=_failed)
