"""Safety holds (docs/02): explicit, audited, and the only way an incident can block dispatch or handover."""

from django.db import transaction
from django.utils import timezone

from core.audit import audit
from core.errors import DomainError
from ops.models import Role, SafetyHold
from ops.permissions import actor_label, require
from ops.services.alerts import raise_alert


def _active(ticket_qs_filter):
    return SafetyHold.objects.filter(cleared_at__isnull=True, **ticket_qs_filter)


def place_hold(actor, ticket, reason: str, *, blocks_dispatch: bool, blocks_handover: bool,
               incident=None) -> SafetyHold:
    require(actor, Role.SUPERVISOR, ticket.event)
    if not reason.strip():
        raise DomainError("reason_required")
    if not (blocks_dispatch or blocks_handover):
        raise DomainError("hold_must_block")
    hold = SafetyHold.objects.create(event=ticket.event, ticket=ticket, incident=incident, reason=reason.strip()[:200],
                                     blocks_dispatch=blocks_dispatch, blocks_handover=blocks_handover, created_by=actor)
    raise_alert(ticket.event, "hold_active", ticket=ticket, severity="critical", dedupe_key=f"hold:{hold.id}")
    audit("hold.place", actor_id=actor.id, actor_label=actor_label(actor), channel="console", entity_type="ticket",
          entity_id=ticket.id, event_id=ticket.event_id,
          summary={"hold_id": hold.id, "dispatch": blocks_dispatch, "handover": blocks_handover})
    return hold


def clear_hold(actor, hold, reason: str) -> SafetyHold:
    require(actor, Role.SUPERVISOR, hold.event)
    if not reason.strip():
        raise DomainError("reason_required")
    with transaction.atomic():
        hold = SafetyHold.objects.select_for_update(no_key=True).get(pk=hold.pk)
        if hold.cleared_at is None:
            hold.cleared_at = timezone.now()
            hold.cleared_by = actor
            hold.clear_reason = reason.strip()[:200]
            hold.save(update_fields=["cleared_at", "cleared_by", "clear_reason"])
            audit("hold.clear", actor_id=actor.id, actor_label=actor_label(actor), channel="console",
                  entity_type="ticket", entity_id=hold.ticket_id, event_id=hold.event_id, summary={"hold_id": hold.id})
    return hold


def dispatch_blocked_ticket_ids(event) -> set[int]:
    return set(_active({"event": event, "blocks_dispatch": True}).values_list("ticket_id", flat=True))


def handover_blocked(ticket) -> bool:
    return _active({"ticket": ticket, "blocks_handover": True}).exists()


def on_delivered(ticket) -> None:
    """Holds that only blocked dispatch have no further effect after a verified delivery; they stay on record."""


def brief(ticket) -> list[dict]:
    return [{"id": h.id, "reason": h.reason, "blocks_dispatch": h.blocks_dispatch,
             "blocks_handover": h.blocks_handover, "created_at": h.created_at}
            for h in _active({"ticket": ticket}).order_by("-id")]


def allowed_actions(ticket) -> list[str]:
    actions = []
    if ticket.state in ("RECEIVED", "PARKED", "RETRIEVING", "READY", "UNCLAIMED"):
        actions.append("place_hold")
    if _active({"ticket": ticket}).exists():
        actions.append("clear_hold")
    return actions
