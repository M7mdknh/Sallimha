"""Guest feedback routing (docs/01 §7): excellent → praise valet; okay → silent; poor → supervisor."""

from django.db import IntegrityError, transaction

from core.audit import audit
from messaging import outbox
from ops.models import Rating, Ticket
from ops.services.alerts import raise_alert


def record_rating(binding, ticket, value: str, source_message_id: str) -> Rating | None:
    if value not in Rating.Value.values:
        return None
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update(no_key=True).get(pk=ticket.pk)
        if ticket.state != Ticket.State.DELIVERED or ticket.delivered_by_id is None:
            return None
        try:
            with transaction.atomic():
                rating = Rating.objects.create(ticket=ticket, delivering_valet=ticket.delivered_by, value=value,
                                               source_message_id=source_message_id)
        except IntegrityError:
            return None
        t = f"#{ticket.display_number:03d}"
        if value == Rating.Value.EXCELLENT:
            outbox.enqueue("valet.praise", staff=ticket.delivered_by, ticket=ticket, template="valet.praise",
                           params={"ticket": t}, dedupe_key=f"valet.praise:{ticket.id}")
        if value == Rating.Value.POOR:
            raise_alert(ticket.event, "poor_rating", ticket=ticket, severity="critical",
                        dedupe_key=f"poor_rating:{ticket.id}", detail={"rating_id": rating.id})
            from ops.services import incidents

            incidents.open_complaint_from_rating(rating)
            outbox.enqueue("guest.poor_ack", binding=binding, ticket=ticket, template="guest.poor_ack", params={},
                           dedupe_key=f"guest.poor_ack:{ticket.id}")
        else:
            outbox.enqueue("guest.thanks", binding=binding, ticket=ticket, template="guest.thanks", params={},
                           dedupe_key=f"guest.thanks:{ticket.id}")
        audit("rating.record", actor_id=None, actor_label="guest", channel="whatsapp", entity_type="ticket",
              entity_id=ticket.id, event_id=ticket.event_id, summary={"value": value})
    return rating
