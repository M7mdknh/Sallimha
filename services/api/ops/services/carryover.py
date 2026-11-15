"""Unclaimed vehicles (docs/01 §8, ADR-0005 C1): supervisor proposes, manager approves a named custodian and
plan; the venue key hook stays reserved across events until a manager's explicit, audited release."""

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import audit
from core.errors import DomainError
from ops.models import OPEN_REQUEST_STATES, CarryoverCase, KeyOccupancy, Role, Ticket
from ops.permissions import actor_label, require
from ops.services import tokens
from ops.services.alerts import raise_alert


def _audit(action, actor, ticket, **summary):
    audit(action, actor_id=actor.id, actor_label=actor_label(actor), channel="console", entity_type="ticket",
          entity_id=ticket.id, event_id=ticket.event_id, summary=summary)


def propose_unclaimed(actor, ticket, *, custodian: str, plan: str) -> CarryoverCase:
    require(actor, Role.SUPERVISOR, ticket.event)
    if not custodian.strip() or not plan.strip():
        raise DomainError("custody_details_required")
    if ticket.state != Ticket.State.PARKED or ticket.requests.filter(state__in=OPEN_REQUEST_STATES).exists():
        raise DomainError("invalid_state")
    try:
        case = CarryoverCase.objects.create(ticket=ticket, custodian=custodian.strip()[:160],
                                            plan=plan.strip()[:2000], proposed_by=actor)
    except IntegrityError as exc:
        raise DomainError("already_proposed") from exc
    raise_alert(ticket.event, "unclaimed_pending", ticket=ticket, dedupe_key=f"unclaimed:{case.id}")
    _audit("carryover.propose", actor, ticket, custodian=case.custodian)
    return case


def approve_unclaimed(actor, case, now=None) -> CarryoverCase:
    now = now or timezone.now()
    require(actor, Role.MANAGER, case.ticket.event)
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update(no_key=True).get(pk=case.ticket_id)
        case = CarryoverCase.objects.select_for_update(no_key=True).get(pk=case.pk)
        if case.status != CarryoverCase.Status.PROPOSED or ticket.state != Ticket.State.PARKED:
            raise DomainError("invalid_state")
        case.status = CarryoverCase.Status.APPROVED
        case.approved_by = actor
        case.approved_at = now
        case.save(update_fields=["status", "approved_by", "approved_at"])
        ticket.state = Ticket.State.UNCLAIMED
        ticket.version += 1
        ticket.save(update_fields=["state", "version"])
        tokens.revoke(ticket=ticket, purposes=["guest_request"], now=now)
        _audit("carryover.approve", actor, ticket, custodian=case.custodian)
    return case


def release_carryover(actor, case, method: str, note: str, now=None) -> CarryoverCase:
    now = now or timezone.now()
    require(actor, Role.MANAGER, case.ticket.event)
    if method not in CarryoverCase.ReleaseMethod.values or not note.strip():
        raise DomainError("reason_required")
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update(no_key=True).get(pk=case.ticket_id)
        case = CarryoverCase.objects.select_for_update(no_key=True).get(pk=case.pk)
        if case.status != CarryoverCase.Status.APPROVED:
            raise DomainError("invalid_state")
        KeyOccupancy.objects.filter(ticket=ticket, released_at__isnull=True).update(
            released_at=now, released_by=actor, release_reason="carryover_release")
        case.status = CarryoverCase.Status.RELEASED
        case.released_by = actor
        case.released_at = now
        case.release_method = method
        case.release_note = note.strip()[:2000]
        case.save(update_fields=["status", "released_by", "released_at", "release_method", "release_note"])
        _audit("carryover.release", actor, ticket, method=method)
    return case


def register(org):
    """Carryover register: every unclaimed case not yet released, across events."""
    return (CarryoverCase.objects.filter(ticket__event__org=org).exclude(status=CarryoverCase.Status.RELEASED)
            .select_related("ticket", "ticket__event", "ticket__location_zone").order_by("proposed_at"))
