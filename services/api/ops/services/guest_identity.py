"""Who may act for a ticket (docs/04 Guest ticket and action security, docs/11 #7).

A sender is matched by phone (keyed hash) when the provider supplies it; otherwise by the
business-scoped user id once learned. A first BSUID-only contact is accepted only when the
action reference is valid AND the reply's context id is a message we sent to this binding."""

from django.db.models import Q

from core.crypto import keyed_hash
from messaging.models import MessageOutbox
from ops.models import GuestBinding, Ticket

ACTIVE_TICKET_STATES = [Ticket.State.RECEIVED, Ticket.State.PARKED, Ticket.State.RETRIEVING, Ticket.State.READY]


def sender_hash(inb) -> str:
    return keyed_hash(inb.from_phone, "phone") if inb.from_phone else ""


def bindings_for_sender(inb):
    match = Q()
    if inb.from_phone:
        match |= Q(phone_hash=sender_hash(inb))
    if inb.from_user_id:
        match |= Q(wa_user_id=inb.from_user_id)
    if not match:
        return GuestBinding.objects.none()
    return (GuestBinding.objects.filter(match, revoked_at__isnull=True, ticket__state__in=ACTIVE_TICKET_STATES)
            .select_related("ticket").order_by("ticket__display_number"))


def authorize(binding: GuestBinding | None, inb) -> bool:
    """True if this sender may act through `binding`; learns the BSUID when safely possible."""
    if binding is None or binding.revoked_at is not None:
        return False
    if inb.from_phone:
        if sender_hash(inb) != binding.phone_hash:
            return False
        if inb.from_user_id and not binding.wa_user_id:
            binding.wa_user_id = inb.from_user_id
            binding.matched_via = "phone"
            binding.save(update_fields=["wa_user_id", "matched_via"])
        return True
    if binding.wa_user_id:
        return bool(inb.from_user_id) and inb.from_user_id == binding.wa_user_id
    if inb.from_user_id and inb.context_id and MessageOutbox.objects.filter(
        binding=binding, provider_message_id=inb.context_id
    ).exists():
        binding.wa_user_id = inb.from_user_id
        binding.matched_via = "context_token"
        binding.save(update_fields=["wa_user_id", "matched_via"])
        return True
    return False
