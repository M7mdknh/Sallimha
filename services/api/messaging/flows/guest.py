"""Guest WhatsApp conversation (docs/01 §4, docs/04). A display number or a generic message is never
a credential; only an authorized sender acting through a valid action reference or their own
binding can request a car."""

import logging

from core.audit import audit
from core.errors import DomainError
from messaging import outbox
from messaging.parse import Inbound
from ops.services import guest_identity, retrieval, tokens
from ops.services.alerts import raise_alert
from ops.services.ratings import record_rating

log = logging.getLogger(__name__)

REQUEST_WORDS = {"اطلب سيارتي", "سيارتي", "اطلب سيارتي الآن", "request my car", "my car", "request"}


def _reply_raw(inb: Inbound, template: str, n: int = 1, **params) -> None:
    """Reply to a sender with no usable binding. Shares no personal or ticket data."""
    if inb.from_phone:
        outbox.enqueue(template, to_phone=inb.from_phone, template=template, params=params,
                       dedupe_key=f"reply:{inb.provider_message_id}:{n}")


def _reply(binding, inb: Inbound, template: str, n: int = 1, buttons=(), **params) -> None:
    outbox.enqueue(template, binding=binding, ticket=binding.ticket, template=template, params=params,
                   buttons=buttons, dedupe_key=f"reply:{inb.provider_message_id}:{n}")


def _identity_exception(inb: Inbound, ticket) -> None:
    raise_alert(ticket.event, "guest_identity_mismatch", ticket=ticket,
                dedupe_key=f"identity:{inb.provider_message_id}",
                detail={"channel": "whatsapp", "basis": "sender_not_bound"})
    audit("guest.identity_mismatch", actor_id=None, actor_label="unknown", channel="whatsapp", entity_type="ticket",
          entity_id=ticket.id, event_id=ticket.event_id)
    _reply_raw(inb, "guest.not_authorized")


def handle(inb: Inbound) -> None:
    for binding in guest_identity.bindings_for_sender(inb):
        outbox.note_inbound(binding=binding, at=inb.timestamp)
    try:
        if inb.button_payload:
            return _button(inb)
        return _text(inb)
    except DomainError as err:
        log.info("guest action refused: %s", err.code)
        return _reply_raw(inb, "guest.help", n=9)


def _request(binding, ticket, inb: Inbound) -> None:
    retrieval.request_retrieval(binding, ticket, source_id=inb.provider_message_id)


def _button(inb: Inbound) -> None:
    token = tokens.resolve(inb.button_payload)
    if token is None or token.purpose not in {"guest_request", "guest_rate", "guest_select"}:
        return _reply_raw(inb, "guest.help")
    binding, ticket = token.binding, token.ticket
    if not guest_identity.authorize(binding, inb):
        return _identity_exception(inb, ticket)
    status = tokens.state(token)
    if status in {"revoked", "expired"}:
        return _reply(binding, inb, "guest.help")
    outbox.note_inbound(binding=binding, at=inb.timestamp)
    if token.purpose in {"guest_request", "guest_select"}:
        return _request(binding, ticket, inb)
    if status == "used":
        return None
    rating = record_rating(binding, ticket, token.data.get("value", ""), source_message_id=inb.provider_message_id)
    if rating is not None:
        tokens.revoke(ticket=ticket, purposes=["guest_rate"])
    return None


def _text(inb: Inbound) -> None:
    text = " ".join((inb.text or "").strip().lower().split())
    bindings = list(guest_identity.bindings_for_sender(inb))
    authorized = [b for b in bindings if guest_identity.authorize(b, inb)]
    if not authorized:
        return _reply_raw(inb, "guest.no_active_ticket")
    if text not in REQUEST_WORDS:
        return _reply(authorized[0], inb, "guest.help")
    if len(authorized) == 1:
        binding = authorized[0]
        return _request(binding, binding.ticket, inb)
    # Several active tickets on one phone: offer an explicit choice, never guess (AT-18).
    buttons = []
    for binding in authorized[:3]:
        number = f"#{binding.ticket.display_number:03d}"
        payload = tokens.issue("guest_select", ticket=binding.ticket, binding=binding)
        buttons.append((payload, "select_ticket", {"ticket": number}))
    return _reply(authorized[0], inb, "guest.select_ticket", buttons=buttons)
