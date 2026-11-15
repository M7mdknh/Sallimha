"""Incidents (docs/01 §7): supervisors create, view and annotate; only manager+ resolve with an outcome."""

from django.db import transaction
from django.utils import timezone

from core.audit import audit
from core.errors import DomainError
from ops.models import Incident, IncidentNote, Role
from ops.permissions import actor_label, require


def _audit(action, actor, incident, **summary):
    audit(action, actor_id=actor.id if actor else None, actor_label=actor_label(actor), channel="console",
          entity_type="incident", entity_id=incident.id, event_id=incident.event_id, summary=summary)


def open_incident(actor, event, category: str, description: str, *, ticket=None) -> Incident:
    require(actor, Role.SUPERVISOR, event)
    if category not in Incident.Category.values:
        raise DomainError("invalid_category")
    if not description.strip():
        raise DomainError("description_required")
    if ticket is not None and ticket.event_id != event.id:
        raise DomainError("forbidden")
    incident = Incident.objects.create(event=event, ticket=ticket, category=category,
                                       description=description.strip()[:2000], created_by=actor)
    _audit("incident.open", actor, incident, category=category, ticket_id=ticket.id if ticket else None)
    return incident


def annotate(actor, incident, text: str) -> IncidentNote:
    require(actor, Role.SUPERVISOR, incident.event)
    if not text.strip():
        raise DomainError("description_required")
    note = IncidentNote.objects.create(incident=incident, author=actor, text=text.strip()[:2000])
    if incident.status == Incident.Status.OPEN:
        Incident.objects.filter(pk=incident.pk).update(status=Incident.Status.IN_REVIEW)
    _audit("incident.note", actor, incident)
    return note


def resolve(actor, incident, outcome: str) -> Incident:
    require(actor, Role.MANAGER, incident.event)
    if not outcome.strip():
        raise DomainError("outcome_required")
    with transaction.atomic():
        incident = Incident.objects.select_for_update(no_key=True).get(pk=incident.pk)
        if incident.status == Incident.Status.RESOLVED:
            return incident
        incident.status = Incident.Status.RESOLVED
        incident.resolution = outcome.strip()[:2000]
        incident.resolved_by = actor
        incident.resolved_at = timezone.now()
        incident.save(update_fields=["status", "resolution", "resolved_by", "resolved_at"])
        _audit("incident.resolve", actor, incident)
    return incident


def open_complaint_from_rating(rating) -> Incident:
    """Poor rating → complaint incident linked to the ticket (no automatic reprimand to the valet)."""
    ticket = rating.ticket
    incident = Incident.objects.create(event=ticket.event, ticket=ticket, category=Incident.Category.COMPLAINT,
                                       description="Poor guest rating received after delivery.")
    _audit("incident.open", None, incident, category="complaint", source="rating")
    return incident


def brief(ticket) -> list[dict]:
    return [{"id": i.id, "category": i.category, "status": i.status, "created_at": i.created_at}
            for i in ticket.incidents.order_by("-id")]


def allowed_actions(ticket) -> list[str]:
    return ["open_incident"]


def attach_photo(staff, incident_id: int, data: bytes, content_type: str, provider_media_id: str = "") -> Incident:
    """Evidence photo from a valet for an incident they explicitly selected (AT-36)."""
    from ops.models import Media
    from ops.services.media import store_private

    incident = Incident.objects.select_related("ticket").get(pk=incident_id)
    if incident.status == Incident.Status.RESOLVED or incident.ticket is None:
        raise DomainError("invalid_state")
    key, digest = store_private(data, content_type, f"incident/{incident.event_id}/{incident.id}")
    Media.objects.create(ticket=incident.ticket, incident_id=incident.id, kind=Media.Kind.INCIDENT, storage_key=key,
                         sha256=digest, content_type=content_type, size=len(data), uploaded_by=staff,
                         received_at=timezone.now(), provider_media_id=provider_media_id[:128])
    _audit("incident.photo", staff, incident)
    return incident
