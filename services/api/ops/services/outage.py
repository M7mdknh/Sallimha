"""Outage workflow (ADR-0008).

WhatsApp unavailable, console working: a supervisor declares the outage. While it is open — and only then — a
supervisor may record what a valet reports by radio or in person: acceptance of the dispatcher's own offer, car
ready, receipt of custody, acceptance of a move, and an intake on the valet's behalf. Each record names the
valet, how it was confirmed and who relayed it. The supervisor never chooses who retrieves a car.

Whole system unavailable: staff follow the continuity procedure (docs/runbooks/whatsapp-outage.md). Afterwards a
manager records the outage window and reconciles what happened in it. A reconciliation keeps the actual time
apart from the entry time, names the responsible staff and the verifier, records the evidence and reason, never
completes a ticket twice and never overrides a safety hold.
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import audit
from core.crypto import encrypt_text, keyed_hash
from core.errors import DomainError
from core.phone import PhoneInvalid, parse_phone
from ops.models import (
    LIVE_TASK_STATUSES,
    AssistedVerification,
    CustodyTransfer,
    Event,
    EventAssignment,
    GuestBinding,
    KeyOccupancy,
    OutageWindow,
    ParkingZone,
    Reconciliation,
    RetrievalRequest,
    Role,
    Task,
    Ticket,
)
from ops.permissions import actor_label, can_access_event, has_role, require
from ops.services import shifts, tokens

CONFIRMED_VIA = ("in_person", "radio")
FINAL_STATES = (Ticket.State.DELIVERED, Ticket.State.CANCELLED)
MAX_WINDOW = timedelta(hours=24)  # a recorded whole-system outage longer than this needs an engineer, not the console
MAX_AGE = timedelta(days=30)  # reconciliation is for recent outages only


def _audit(action, actor, entity_id, event_id=None, entity_type="ticket", **summary):
    audit(action, actor_id=actor.id, actor_label=actor_label(actor), channel="console", entity_type=entity_type,
          entity_id=entity_id, event_id=event_id, summary=summary)


# --- WhatsApp outage ----------------------------------------------------------------------------------------

def active_whatsapp_outage(org) -> OutageWindow | None:
    return OutageWindow.objects.filter(org=org, kind=OutageWindow.Kind.WHATSAPP, ended_at__isnull=True).first()


def _has_standing(actor, org) -> bool:
    """The WhatsApp sender is organisation-wide, so the outage is too. A supervisor may declare it only while
    assigned to an open event of the organisation (they are on the stand); managers always may."""
    if has_role(actor, Role.MANAGER):
        return True
    return EventAssignment.objects.filter(staff=actor, event__org=org, event__status=Event.Status.OPEN).exists()


def declare_whatsapp_outage(actor, org, reason: str, now=None) -> OutageWindow:
    from ops.services.alerts import raise_alert

    now = now or timezone.now()
    require(actor, Role.SUPERVISOR)
    if actor.org_id != org.id or not _has_standing(actor, org):
        raise DomainError("forbidden")
    if not reason.strip():
        raise DomainError("reason_required")
    try:
        with transaction.atomic():
            window = OutageWindow.objects.create(org=org, kind=OutageWindow.Kind.WHATSAPP, started_at=now,
                                                 reason=reason.strip()[:200], declared_by=actor)
            for event in Event.objects.filter(org=org, status=Event.Status.OPEN):
                raise_alert(event, "whatsapp_outage", severity="critical", dedupe_key=f"whatsapp_outage:{window.id}",
                            detail={"declared_by": actor.id})
            _audit("outage.declared", actor, window.id, entity_type="outage", kind="WHATSAPP",
                   reason=window.reason)
    except IntegrityError as exc:
        raise DomainError("outage_already_declared") from exc
    return window


def end_whatsapp_outage(actor, org, reason: str, now=None) -> OutageWindow:
    now = now or timezone.now()
    require(actor, Role.SUPERVISOR)
    if actor.org_id != org.id:
        raise DomainError("forbidden")
    with transaction.atomic():
        window = OutageWindow.objects.select_for_update(no_key=True).filter(
            org=org, kind=OutageWindow.Kind.WHATSAPP, ended_at__isnull=True).first()
        if window is None:
            raise DomainError("no_active_outage")
        if window.declared_by_id != actor.id and not has_role(actor, Role.MANAGER):
            raise DomainError("forbidden")  # only the declarer or a manager ends an organisation-wide outage
        window.ended_at, window.ended_by, window.end_reason = now, actor, reason.strip()[:200]
        window.save(update_fields=["ended_at", "ended_by", "end_reason"])
        _audit("outage.ended", actor, window.id, entity_type="outage", kind="WHATSAPP", reason=window.end_reason)
    return window


def _relay_guard(actor, event, confirmed_via: str) -> None:
    require(actor, Role.SUPERVISOR, event)
    if active_whatsapp_outage(event.org) is None:
        raise DomainError("no_active_outage")
    if confirmed_via not in CONFIRMED_VIA:
        raise DomainError("confirmation_required")


def relay_accept(actor, task, *, confirmed_via: str, now=None) -> None:
    """The valet the system offered the task to accepted by radio or in person."""
    from ops.services import dispatch, relocation

    _relay_guard(actor, task.event, confirmed_via)
    if task.type == Task.Type.RETRIEVAL:
        dispatch.accept_relayed(actor, task, confirmed_via, now=now)
    elif task.type == Task.Type.RELOCATION:
        relocation.accept_relayed(actor, task, confirmed_via, now=now)
    else:
        raise DomainError("invalid_state")


def relay_ready(actor, task, *, confirmed_via: str, now=None) -> None:
    from ops.services import handover

    _relay_guard(actor, task.event, confirmed_via)
    handover.mark_ready_relayed(actor, task, confirmed_via, now=now)


def relay_custody_ack(actor, transfer, *, confirmed_via: str, now=None) -> None:
    from ops.services import custody

    _relay_guard(actor, transfer.ticket.event, confirmed_via)
    if transfer.kind != CustodyTransfer.Kind.RETRIEVAL_TRANSFER:
        raise DomainError("invalid_state")
    custody.acknowledge_custody(transfer.to_staff, transfer, now=now, relayed_by=actor, confirmed_via=confirmed_via)


# --- intake on a valet's behalf (WhatsApp outage, or reconciliation after a system outage) ------------------

def record_intake(actor, event, *, valet, guest_phone: str, plate: str, description: str, zone_code: str,
                  detail: str, hook_number: int, reason: str, confirmed_via: str = "", outage=None,
                  received_at=None, parked_at=None, evidence: str = "", now=None) -> Ticket:
    """Creates the ticket directly as PARKED with the valet as registrant and parker. Photos are excepted with the
    reason; the guest's contact is a supervisor-assisted fallback (no in-person receipt confirmation was possible),
    and the WhatsApp ticket is queued for delivery — queued, not delivered.

    Without `outage` this is the WhatsApp-outage path (supervisor+, now). With a recorded system `outage` it is a
    reconciliation (manager+): `received_at`/`parked_at` are the actual times and must fall inside the window."""
    now = now or timezone.now()
    if outage is None:
        _relay_guard(actor, event, confirmed_via)
        received_at = parked_at = now
    else:
        require(actor, Role.MANAGER, event)
        _check_window(actor, outage, now)
        if received_at is None or parked_at is None or received_at > parked_at:
            raise DomainError("conflict_time")
        if not (outage.started_at <= received_at and parked_at <= outage.ended_at):
            raise DomainError("outside_outage_window")
        if not evidence.strip():
            raise DomainError("evidence_required")
    if not reason.strip():
        raise DomainError("reason_required")
    if not _event_valet(valet, event):
        raise DomainError("receiver_unavailable")
    if outage is None and shifts.open_shift_for(valet, event) is None:
        raise DomainError("not_on_shift")
    if not (plate or "").strip():
        raise DomainError("vehicle_unidentified")
    try:
        parsed = parse_phone(guest_phone)
    except PhoneInvalid as exc:
        raise DomainError("phone_invalid") from exc
    zone = ParkingZone.objects.filter(venue_id=event.venue_id, code__iexact=zone_code.strip(), active=True).first()
    if zone is None:
        raise DomainError("zone_invalid")
    station = event.venue.key_stations.order_by("id").first()
    if station is None:
        raise DomainError("no_key_station")
    if not 1 <= int(hook_number) <= station.hook_count:
        raise DomainError("hook_invalid")
    try:
        with transaction.atomic():
            event = Event.objects.select_for_update(no_key=True).get(pk=event.pk)
            if event.status != Event.Status.OPEN:
                raise DomainError("event_closed")
            event.display_seq += 1
            event.save(update_fields=["display_seq"])
            why = reason.strip()[:200]
            ticket = Ticket.objects.create(
                event=event, display_number=event.display_seq, registered_by=valet, created_at=received_at,
                state=Ticket.State.PARKED, contact_state=Ticket.Contact.ASSISTED_FALLBACK,
                vehicle_plate=plate.strip()[:40], vehicle_description=(description or "").strip()[:200],
                vehicle_raw=f"{plate} {description}".strip(), photos_exception_reason=f"outage: {why}"[:200],
                location_zone=zone, location_detail=(detail or "").strip()[:80], phone_confirmed_at=received_at,
                parking_started_at=received_at, parked_at=parked_at, parked_by=valet)
            Task.objects.create(event=event, ticket=ticket, type=Task.Type.INTAKE, status=Task.Status.COMPLETED,
                                assignee=valet, reserved_at=received_at, accepted_at=received_at,
                                completed_at=parked_at)
            KeyOccupancy.objects.create(key_station=station, hook_number=int(hook_number), ticket=ticket,
                                        occupied_at=parked_at, occupied_by=valet)
            binding = GuestBinding.objects.create(
                ticket=ticket, revision=1, phone_enc=encrypt_text(parsed.e164),
                phone_hash=keyed_hash(parsed.e164, "phone"), phone_masked=parsed.masked, language="ar",
                consent_at=received_at, confirmed_by=actor)
            from ops.services.intake import send_ticket

            send_ticket(ticket, binding, now)  # queued; delivered when WhatsApp is available
            if outage is not None:
                Reconciliation.objects.create(ticket=ticket, kind=Reconciliation.Kind.INTAKE, outage=outage,
                                              occurred_at=parked_at, recorded_by=actor, responsible=valet,
                                              evidence=evidence.strip()[:2000], reason=why)
            _audit("intake.recorded_on_behalf", actor, ticket.id, event.id, valet=valet.id,
                   confirmed_via=confirmed_via or "reconciliation", outage=outage.id if outage else None,
                   received_at=received_at.isoformat(), parked_at=parked_at.isoformat(), hook=int(hook_number),
                   zone=zone.code, reason=why)
    except IntegrityError as exc:
        raise DomainError("hook_occupied") from exc
    return ticket


# --- whole-system outage ------------------------------------------------------------------------------------

def record_system_outage(actor, org, *, started_at, ended_at, reason: str, now=None) -> OutageWindow:
    """Recorded after recovery, with both times. Windows of the same organisation never overlap."""
    now = now or timezone.now()
    require(actor, Role.MANAGER)
    if actor.org_id != org.id:
        raise DomainError("forbidden")
    if not reason.strip():
        raise DomainError("reason_required")
    if not (started_at < ended_at <= now) or ended_at - started_at > MAX_WINDOW or started_at < now - MAX_AGE:
        raise DomainError("invalid_window")
    with transaction.atomic():
        overlapping = OutageWindow.objects.select_for_update().filter(
            org=org, kind=OutageWindow.Kind.SYSTEM, started_at__lt=ended_at, ended_at__gt=started_at)
        if overlapping.exists():
            raise DomainError("overlaps")
        window = OutageWindow.objects.create(org=org, kind=OutageWindow.Kind.SYSTEM, started_at=started_at,
                                             ended_at=ended_at, reason=reason.strip()[:200], declared_by=actor,
                                             ended_by=actor)
        _audit("outage.recorded", actor, window.id, entity_type="outage", kind="SYSTEM",
               started_at=started_at.isoformat(), ended_at=ended_at.isoformat(), reason=window.reason)
    return window


def _check_window(actor, outage, now) -> None:
    if outage.org_id != actor.org_id:
        raise DomainError("forbidden")
    if outage.kind != OutageWindow.Kind.SYSTEM or outage.ended_at is None or outage.ended_at > now or \
            outage.ended_at < now - MAX_AGE:
        raise DomainError("invalid_window")


def _event_valet(person, event) -> bool:
    return (person.org_id == event.org_id and person.role == Role.VALET and person.enabled
            and EventAssignment.objects.filter(event=event, staff=person).exists())


def reconcile_handover(actor, ticket, *, outage, occurred_at, delivered_by, verified_by, method: str,
                       evidence: str, reason: str, now=None) -> Reconciliation:
    """Records a handover that happened during a whole-system outage. Rejected: an actual time outside the window,
    before the car was parked or in the future; a verifier who is not supervisor+ for the event; missing
    evidence or reason; a ticket already completed; an active safety hold (clear it first, with a reason)."""
    from ops.services import holds

    now = now or timezone.now()
    require(actor, Role.MANAGER, ticket.event)
    _check_window(actor, outage, now)
    if not (outage.started_at <= occurred_at <= outage.ended_at):
        raise DomainError("outside_outage_window")
    if method not in AssistedVerification.Method.values:
        raise DomainError("reason_required")
    if not evidence.strip():
        raise DomainError("evidence_required")
    if not reason.strip():
        raise DomainError("reason_required")
    if not (has_role(verified_by, Role.SUPERVISOR) and can_access_event(verified_by, ticket.event)):
        raise DomainError("verifier_not_authorized")
    if verified_by.id == actor.id:
        raise DomainError("verifier_must_differ")  # two people attest an after-the-fact handover
    if not _event_valet(delivered_by, ticket.event):
        raise DomainError("receiver_unavailable")
    try:
        with transaction.atomic():
            ticket = Ticket.objects.select_for_update(no_key=True).get(pk=ticket.pk)
            if ticket.state in FINAL_STATES:
                raise DomainError("already_delivered" if ticket.state == Ticket.State.DELIVERED else "invalid_state")
            if ticket.state not in (Ticket.State.PARKED, Ticket.State.RETRIEVING, Ticket.State.READY):
                raise DomainError("invalid_state")
            if occurred_at < (ticket.parked_at or ticket.created_at):
                raise DomainError("conflict_time")
            if holds.handover_blocked(ticket):
                raise DomainError("handover_blocked")
            req = RetrievalRequest.objects.select_for_update(no_key=True).filter(
                ticket=ticket, state__in=["WAITING_FOR_PARKING", "QUEUED", "OFFERED", "ACCEPTED"]).first()
            live = list(Task.objects.select_for_update(no_key=True).filter(ticket=ticket,
                                                                             status__in=LIVE_TASK_STATUSES))
            record = Reconciliation.objects.create(
                ticket=ticket, kind=Reconciliation.Kind.HANDOVER, outage=outage, occurred_at=occurred_at,
                recorded_by=actor, responsible=delivered_by, verified_by=verified_by, method=method,
                evidence=evidence.strip()[:2000], reason=reason.strip()[:200])
            for task in live:
                delivered_here = task.type == Task.Type.RETRIEVAL and task.assignee_id == delivered_by.id
                task.status = Task.Status.COMPLETED if delivered_here else Task.Status.RELEASED
                task.completed_at = now if delivered_here else task.completed_at
                task.released_at = None if delivered_here else now
                task.release_reason = "" if delivered_here else "reconciled_offline_handover"
                task.save(update_fields=["status", "completed_at", "released_at", "release_reason"])
                shifts.on_task_released(task.assignee, now)
            if req is not None:
                req.state = RetrievalRequest.State.COMPLETED
                req.completed_at = occurred_at
                req.save(update_fields=["state", "completed_at"])
            ticket.state = Ticket.State.DELIVERED
            ticket.delivered_at = occurred_at
            ticket.delivered_by = delivered_by
            ticket.version += 1
            ticket.save(update_fields=["state", "delivered_at", "delivered_by", "version"])
            ticket.codes.filter(consumed_at__isnull=True, revoked_at__isnull=True).update(revoked_at=now)
            KeyOccupancy.objects.filter(ticket=ticket, released_at__isnull=True).update(
                released_at=occurred_at, released_by=delivered_by, release_reason="delivered")
            tokens.revoke(ticket=ticket, now=now)
            holds.on_delivered(ticket)
            _audit("ticket.delivered", actor, ticket.id, ticket.event_id, verification="reconciled",
                   reconciliation=record.id, outage=outage.id, occurred_at=occurred_at.isoformat(),
                   delivered_by=delivered_by.id, verified_by=verified_by.id, method=method)
    except IntegrityError as exc:
        raise DomainError("already_delivered") from exc
    return record
