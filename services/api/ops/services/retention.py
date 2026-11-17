"""Retention (docs/05): 0 means never delete. Separate periods for guest contact, intake photos and resolved
incident evidence. Open disputes, active holds and unclaimed custody protect evidence. Deletion is previewed,
authorized (admin+) and audited with counts only — never personal data."""

from datetime import timedelta

from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from core.audit import audit
from core.errors import DomainError
from ops.models import CarryoverCase, GuestBinding, GuestMessage, Incident, Media, Role, SafetyHold, Ticket
from ops.permissions import actor_label, require
from ops.services.config import retention_days
from ops.services.media import delete_private

CLOSED = [Ticket.State.DELIVERED, Ticket.State.CANCELLED]


def _protected_tickets():
    """Tickets whose evidence must survive: open incidents, active holds, unclaimed custody not released.
    Existence subqueries — a join-based isnull test would treat tickets without holds as protected."""
    ticket = OuterRef("pk")
    return (Exists(Incident.objects.filter(ticket=ticket, status__in=["OPEN", "IN_REVIEW"]))
            | Exists(SafetyHold.objects.filter(ticket=ticket, cleared_at__isnull=True))
            | Exists(CarryoverCase.objects.filter(ticket=ticket, status__in=["PROPOSED", "APPROVED"])))


def _closed_before(org, cutoff):
    return (Ticket.objects.filter(event__org=org, state__in=CLOSED)
            .filter(Q(delivered_at__lt=cutoff) | Q(cancelled_at__lt=cutoff))
            .exclude(_protected_tickets()).values("id"))


def _querysets(org, now):
    days = retention_days(org)
    qs = {}
    if days["guest_contact"]:
        qs["guest_contact"] = GuestBinding.objects.filter(
            ticket_id__in=_closed_before(org, now - timedelta(days=days["guest_contact"]))).exclude(
            phone_masked="redacted")
    if days["intake_photos"]:
        qs["intake_photos"] = Media.objects.filter(
            kind=Media.Kind.INTAKE, deleted_at__isnull=True,
            ticket_id__in=_closed_before(org, now - timedelta(days=days["intake_photos"])))
    if days["incident_evidence"]:
        resolved = Incident.objects.filter(event__org=org, status="RESOLVED",
                                           resolved_at__lt=now - timedelta(days=days["incident_evidence"]))
        qs["incident_evidence"] = Media.objects.filter(kind=Media.Kind.INCIDENT, deleted_at__isnull=True,
                                                       incident_id__in=resolved.values("id")).exclude(
            ticket__in=Ticket.objects.filter(_protected_tickets()))
    return days, qs


def preview(org, now=None) -> dict:
    days, qs = _querysets(org, now or timezone.now())
    return {key: {"days": days[key], "eligible": qs[key].count() if key in qs else 0} for key in days}


def apply(actor, org, now=None) -> dict:
    now = now or timezone.now()
    require(actor, Role.ADMIN)
    if actor.org_id != org.id:
        raise DomainError("forbidden")
    with transaction.atomic():
        _days, qs = _querysets(org, now)
        result = {"guest_contact": 0, "intake_photos": 0, "incident_evidence": 0}
        if "guest_contact" in qs:
            GuestMessage.objects.filter(binding_id__in=list(qs["guest_contact"].values_list("id", flat=True))).delete()
            result["guest_contact"] = qs["guest_contact"].update(
                phone_enc="", phone_hash="", phone_masked="redacted", wa_user_id="")
        for key in ("intake_photos", "incident_evidence"):
            if key in qs:
                rows = list(qs[key])
                for media in rows:
                    delete_private(media.storage_key)
                result[key] = Media.objects.filter(pk__in=[m.pk for m in rows]).update(deleted_at=now)
        audit("retention.apply", actor_id=actor.id, actor_label=actor_label(actor), channel="console",
              entity_type="org", entity_id=org.id, summary=result)
    return result
