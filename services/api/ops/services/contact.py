"""Contacting a customer (ADR-0011). Sallimha stores what the customer wrote; a call or a WhatsApp chat with them
happens on the supervisor's own device, outside Sallimha. Opening the number is scoped to the event and audited."""

from core.audit import audit
from core.crypto import decrypt_text
from core.errors import DomainError
from ops.models import Role
from ops.permissions import actor_label, require


def open_customer_contact(actor, ticket) -> str:
    """The customer's full number for a supervisor of this event or an admin. Valets never get it."""
    require(actor, Role.SUPERVISOR, ticket.event)
    binding = ticket.bindings.filter(revoked_at__isnull=True).exclude(phone_enc="").first()
    if binding is None:
        raise DomainError("no_contact")
    audit("guest.contact_opened", actor_id=actor.id, actor_label=actor_label(actor), channel="console",
          entity_type="ticket", entity_id=ticket.id, event_id=ticket.event_id)
    return decrypt_text(binding.phone_enc)
