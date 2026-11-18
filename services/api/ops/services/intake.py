"""Vehicle intake and parking (docs/01 §2–§3, docs/04 intake table, ADR-0005 C1/C3/C4)."""

import re
from dataclasses import dataclass

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import audit
from core.context import staff_channel
from core.crypto import encrypt_text, keyed_hash
from core.errors import DomainError
from core.phone import ParsedPhone, PhoneInvalid, parse_phone
from core.plate import PlateInvalid, other_plate, saudi_plate, search_key
from messaging import outbox
from ops.models import (
    LIVE_TASK_STATUSES,
    CustodyTransfer,
    Event,
    GuestBinding,
    KeyOccupancy,
    KeyStation,
    Media,
    ParkingZone,
    RetrievalRequest,
    Role,
    Task,
    Ticket,
)
from ops.permissions import actor_label, can_access_event, has_role
from ops.services import shifts, tokens
from ops.services.alerts import raise_alert
from ops.services.media import store_private

REQUIRED_PHOTOS = 4
_PLATE = re.compile(r"^\s*((?:[A-Za-zء-ي]{1,3}\s*\d{1,4})|(?:\d{1,4}\s*[A-Za-zء-ي]{1,3}))(?=\s|$)(.*)$")


def _audit(action, actor, ticket, channel=None, **summary):
    audit(action, actor_id=actor.id if actor else None, actor_label=actor_label(actor),
          channel=channel or staff_channel(),
          entity_type="ticket", entity_id=ticket.id, event_id=ticket.event_id, summary=summary)


def intake_task(ticket) -> Task | None:
    return Task.objects.filter(ticket=ticket, type=Task.Type.INTAKE, status__in=LIVE_TASK_STATUSES).first()


def _lock_ticket(ticket) -> Ticket:
    return Ticket.objects.select_for_update(no_key=True).get(pk=ticket.pk)


def _require_owner(valet, ticket) -> Task:
    task = intake_task(ticket)
    if task is None or task.assignee_id != valet.id:
        raise DomainError("not_intake_owner")
    return task


def _bump(ticket, *fields):
    ticket.version += 1
    ticket.save(update_fields=[*fields, "version"])


def register_vehicle(valet, now=None) -> Ticket:
    now = now or timezone.now()
    shift = shifts.open_shift_for(valet)
    if shift is None or not valet.enabled:
        raise DomainError("not_on_shift")
    if shifts.live_task(valet) is not None:
        raise DomainError("busy")
    if not shifts.is_available(valet, shift.event):
        raise DomainError("not_available")
    try:
        with transaction.atomic():
            event = Event.objects.select_for_update(no_key=True).get(pk=shift.event_id)
            if event.status != Event.Status.OPEN:
                raise DomainError("event_closed")
            event.display_seq += 1
            event.save(update_fields=["display_seq"])
            ticket = Ticket.objects.create(event=event, display_number=event.display_seq, registered_by=valet,
                                           created_at=now)
            Task.objects.create(event=event, ticket=ticket, type=Task.Type.INTAKE, status=Task.Status.ACCEPTED,
                                assignee=valet, reserved_at=now, accepted_at=now)
            _audit("ticket.register", valet, ticket)
    except IntegrityError as exc:
        raise DomainError("busy") from exc
    return ticket


def set_guest_phone(valet, ticket, raw: str) -> ParsedPhone:
    _require_owner(valet, ticket)
    if ticket.bindings.filter(revoked_at__isnull=True).exists():
        raise DomainError("already_confirmed")
    try:
        return parse_phone(raw)
    except PhoneInvalid as exc:
        raise DomainError("phone_invalid") from exc


def _create_binding(ticket, e164: str, language: str, actor, revision: int, now) -> GuestBinding:
    parsed = parse_phone(e164)
    return GuestBinding.objects.create(
        ticket=ticket, revision=revision, phone_enc=encrypt_text(parsed.e164),
        phone_hash=keyed_hash(parsed.e164, "phone"), phone_masked=parsed.masked, language=language,
        consent_at=now, confirmed_by=actor,
    )


def send_ticket(ticket, binding, now=None) -> None:
    token = tokens.issue("guest_request", ticket=ticket, binding=binding)
    venue = ticket.event.venue
    outbox.enqueue("guest.ticket", binding=binding, ticket=ticket, template="guest.ticket",
                   params={"ticket": f"#{ticket.display_number:03d}", "venue": venue.name},
                   buttons=[(token, "request_car")], dedupe_key=f"guest.ticket:{ticket.id}:{binding.revision}",
                   now=now)


def confirm_guest_phone(valet, ticket, e164: str, language: str = "ar", now=None) -> GuestBinding:
    now = now or timezone.now()
    with transaction.atomic():
        ticket = _lock_ticket(ticket)
        _require_owner(valet, ticket)
        if ticket.state != Ticket.State.RECEIVED:
            raise DomainError("invalid_state")
        if ticket.bindings.filter(revoked_at__isnull=True).exists():
            raise DomainError("already_confirmed")
        binding = _create_binding(ticket, e164, language, valet, 1, now)
        ticket.phone_confirmed_at = now
        ticket.guest_language = language
        _bump(ticket, "phone_confirmed_at", "guest_language")
        send_ticket(ticket, binding, now)
        _audit("guest.phone_confirmed", valet, ticket, masked=binding.phone_masked)
    return binding


@dataclass(frozen=True)
class VehicleEntry:
    """How the valet identified the car (ADR-0013): a Saudi plate as entered, another plate as typed, or no readable
    plate with a description and a reason. `key` is the internal search key; it is never shown as the plate."""
    kind: str
    plate: str
    key: str
    description: str
    missing_reason: str = ""


ACTIVE_STATES = (Ticket.State.RECEIVED, Ticket.State.PARKED, Ticket.State.RETRIEVING, Ticket.State.READY,
                 Ticket.State.UNCLAIMED)


def vehicle_entry(kind: str, *, letters: str = "", digits: str = "", text: str = "", description: str = "",
                  missing_reason: str = "") -> VehicleEntry:
    description = (description or "").strip()[:200]
    try:
        if kind == Ticket.PlateKind.SAUDI:
            plate = saudi_plate(letters, digits)
        elif kind == Ticket.PlateKind.OTHER:
            plate = other_plate(text)
        elif kind == Ticket.PlateKind.NONE:
            if len(description) < 2:
                raise DomainError("vehicle_unidentified")  # make, colour, marks: something staff can match
            if not (missing_reason or "").strip():
                raise DomainError("reason_required")
            return VehicleEntry(kind=kind, plate="", key="", description=description,
                                missing_reason=missing_reason.strip()[:200])
        else:
            raise DomainError("invalid_input")
    except PlateInvalid as exc:
        raise DomainError(exc.code) from exc
    return VehicleEntry(kind=kind, plate=plate.display, key=plate.key, description=description)


def guest_number(raw: str, region: str = "SA") -> ParsedPhone:
    try:
        return parse_phone(raw, region)
    except PhoneInvalid as exc:
        raise DomainError(exc.code) from exc


def possible_duplicate(ticket, key: str):
    """Another car with the same plate still active in this operation (delivered and cancelled cars never count)."""
    if not key:
        return None
    return (Ticket.objects.filter(event_id=ticket.event_id, plate_key=key, state__in=ACTIVE_STATES)
            .exclude(pk=ticket.pk).order_by("id").first())


def apply_vehicle(ticket, entry: VehicleEntry) -> None:
    ticket.vehicle_plate = entry.plate[:40]
    ticket.plate_kind = entry.kind
    ticket.plate_key = entry.key[:40]
    ticket.vehicle_description = entry.description
    ticket.vehicle_raw = " ".join(p for p in (entry.plate, entry.description) if p)[:500]
    if entry.missing_reason:
        ticket.vehicle_exception_reason = entry.missing_reason


def register_with_guest(valet, guest_phone: str, entry: VehicleEntry, language: str = "ar", *, region: str = "SA",
                        confirm_duplicate: bool = False, now=None) -> Ticket:
    """Staff app, stage 1 (ADR-0011, ADR-0013): the customer's number and the car, then the ticket is queued. One
    transaction registers the car in the valet's custody, records the vehicle, binds the customer and queues their
    WhatsApp ticket; a refused number, plate or unconfirmed possible duplicate leaves nothing behind."""
    now = now or timezone.now()
    if language not in ("ar", "en"):
        raise DomainError("invalid_input")
    parsed = guest_number(guest_phone, region)
    with transaction.atomic():
        ticket = register_vehicle(valet, now=now)
        twin = possible_duplicate(ticket, entry.key)
        if twin is not None and not confirm_duplicate:
            mine = twin.tasks.filter(assignee=valet, status__in=LIVE_TASK_STATUSES).exists()
            raise DomainError("possible_duplicate", ticket=f"#{twin.display_number:03d}", ticket_state=twin.state,
                              mine=mine)
        ticket = _lock_ticket(ticket)
        apply_vehicle(ticket, entry)
        _bump(ticket, "vehicle_plate", "plate_kind", "plate_key", "vehicle_description", "vehicle_raw",
              "vehicle_exception_reason")
        _audit("ticket.vehicle", valet, ticket, plate_kind=entry.kind, duplicate_confirmed=bool(twin))
        confirm_guest_phone(valet, ticket, parsed.e164, language=language, now=now)
    return Ticket.objects.get(pk=ticket.pk)


def park(valet, ticket, zone_code: str, detail: str, hook_number: int, now=None, *, floor: str = "", note: str = "",
         pin=None) -> Ticket:
    """Staff app, stage 3: the place (zone, spot, floor, description, optional confirmed pin) and the key hook,
    recorded together on arrival. A refused hook changes nothing."""
    now = now or timezone.now()
    with transaction.atomic():
        record_location(valet, ticket, zone_code, detail, now=now, floor=floor, note=note, pin=pin)
        return complete_parking(valet, ticket, hook_number, now=now)


def confirm_guest_receipt(actor, ticket, received: bool, now=None) -> Ticket:
    """Only an explicit staff answer sets CONFIRMED_IN_PERSON (ADR-0005 C3)."""
    now = now or timezone.now()
    with transaction.atomic():
        ticket = _lock_ticket(ticket)
        if not has_role(actor, Role.SUPERVISOR):
            _require_owner(actor, ticket)
        elif not can_access_event(actor, ticket.event):
            raise DomainError("forbidden")
        binding = ticket.bindings.filter(revoked_at__isnull=True).first()
        if binding is None:
            raise DomainError("no_contact")
        binding.receipt_confirmed = received
        binding.receipt_answered_by = actor
        binding.receipt_answered_at = now
        binding.save(update_fields=["receipt_confirmed", "receipt_answered_by", "receipt_answered_at"])
        ticket.contact_state = Ticket.Contact.CONFIRMED_IN_PERSON if received else Ticket.Contact.UNCONFIRMED
        _bump(ticket, "contact_state")
        if not received:
            raise_alert(ticket.event, "guest_contact_unconfirmed", ticket=ticket,
                        dedupe_key=f"contact:{ticket.id}:{binding.revision}:{int(now.timestamp())}")
        _audit("guest.receipt", actor, ticket, received=received)
    return ticket


def record_vehicle(valet, ticket, text: str, now=None) -> Ticket:
    text = (text or "").strip()
    if len(text) < 2:
        raise DomainError("vehicle_unidentified")
    with transaction.atomic():
        ticket = _lock_ticket(ticket)
        _require_owner(valet, ticket)
        match = _PLATE.match(text)
        ticket.vehicle_raw = text[:500]
        ticket.vehicle_plate = re.sub(r"\s+", " ", match.group(1)).upper()[:40] if match else ""
        ticket.plate_key = search_key(ticket.vehicle_plate)[:40]  # free text (retired channel): kind stays unknown
        ticket.vehicle_description = (match.group(2) if match else text).strip()[:200]
        _bump(ticket, "vehicle_raw", "vehicle_plate", "plate_key", "vehicle_description")
        _audit("ticket.vehicle", valet, ticket)
    return ticket


def attach_intake_media(valet, ticket, data: bytes, content_type: str, provider_media_id: str = "",
                        now=None) -> Media:
    now = now or timezone.now()
    ticket = Ticket.objects.get(pk=ticket.pk)
    _require_owner(valet, ticket)
    if ticket.parking_started_at is not None:
        raise DomainError("photos_after_parking")
    key, digest = store_private(data, content_type, f"intake/{ticket.event_id}/{ticket.id}")
    media = Media.objects.create(ticket=ticket, kind=Media.Kind.INTAKE, storage_key=key, sha256=digest,
                                 content_type=content_type, size=len(data), uploaded_by=valet, received_at=now,
                                 provider_media_id=provider_media_id[:128])
    _audit("ticket.photo", valet, ticket, media_id=media.id)
    return media


def intake_photo_count(ticket) -> int:
    return Media.objects.filter(ticket=ticket, kind=Media.Kind.INTAKE, deleted_at__isnull=True).count()


def except_intake_requirement(actor, ticket, kind: str, reason: str) -> Ticket:
    if not has_role(actor, Role.SUPERVISOR) or not can_access_event(actor, ticket.event):
        raise DomainError("forbidden")
    if kind not in {"photos", "vehicle"} or not reason.strip():
        raise DomainError("reason_required")
    with transaction.atomic():
        ticket = _lock_ticket(ticket)
        field = "photos_exception_reason" if kind == "photos" else "vehicle_exception_reason"
        setattr(ticket, field, reason.strip()[:200])
        _bump(ticket, field)
        _audit(f"ticket.exception.{kind}", actor, ticket, channel="console", reason=reason.strip()[:200])
    return ticket


def start_parking(valet, ticket, now=None) -> Ticket:
    """Recorded before the car moves; from here the ticket cannot be cancelled (ADR-0005 C4)."""
    now = now or timezone.now()
    with transaction.atomic():
        ticket = _lock_ticket(ticket)
        _require_owner(valet, ticket)
        if ticket.parking_started_at is not None:
            return ticket
        if not ticket.bindings.filter(revoked_at__isnull=True).exists() and \
                ticket.contact_state != Ticket.Contact.ASSISTED_FALLBACK:
            raise DomainError("no_contact")
        if not (ticket.vehicle_plate or ticket.vehicle_description or ticket.vehicle_exception_reason):
            raise DomainError("vehicle_unidentified")
        if intake_photo_count(ticket) < REQUIRED_PHOTOS and not ticket.photos_exception_reason:
            raise DomainError("photos_incomplete")
        ticket.parking_started_at = now
        _bump(ticket, "parking_started_at")
        _audit("ticket.parking_started", valet, ticket)
    return ticket


def record_location(valet, ticket, zone_code: str, detail: str, now=None, *, floor: str = "", note: str = "",
                    pin=None) -> Ticket:
    from ops.services.location import PLACE_FIELDS, apply_place

    now = now or timezone.now()
    with transaction.atomic():
        ticket = _lock_ticket(ticket)
        _require_owner(valet, ticket)
        if ticket.parking_started_at is None:
            raise DomainError("parking_not_started")
        zone = ParkingZone.objects.filter(venue_id=ticket.event.venue_id, code__iexact=zone_code.strip(),
                                          active=True).first()
        if zone is None:
            raise DomainError("zone_invalid")
        apply_place(ticket, zone=zone, spot=detail, floor=floor, note=note, pin=pin, now=now)
        _bump(ticket, *PLACE_FIELDS)
        _audit("ticket.location", valet, ticket, zone=zone.code, pin=pin.source if pin else None)
    return ticket


def default_key_station(ticket) -> KeyStation:
    station = KeyStation.objects.filter(venue_id=ticket.event.venue_id).order_by("id").first()
    if station is None:
        raise DomainError("no_key_station")
    return station


def complete_parking(valet, ticket, hook_number: int, key_station=None, now=None) -> Ticket:
    now = now or timezone.now()
    try:
        with transaction.atomic():
            ticket = _lock_ticket(ticket)
            task = _require_owner(valet, ticket)
            if ticket.parking_started_at is None or ticket.location_zone_id is None:
                raise DomainError("location_required")
            station = key_station or default_key_station(ticket)
            if not 1 <= int(hook_number) <= station.hook_count:
                raise DomainError("hook_invalid")
            KeyOccupancy.objects.create(key_station=station, hook_number=int(hook_number), ticket=ticket,
                                        occupied_at=now, occupied_by=valet)
            ticket.state = Ticket.State.PARKED
            ticket.parked_at = now
            ticket.parked_by = valet
            _bump(ticket, "state", "parked_at", "parked_by")
            task.status = Task.Status.COMPLETED
            task.completed_at = now
            task.save(update_fields=["status", "completed_at"])
            shifts.on_task_released(valet, now)
            RetrievalRequest.objects.filter(ticket=ticket, state=RetrievalRequest.State.WAITING_FOR_PARKING).update(
                state=RetrievalRequest.State.QUEUED, eligible_at=now)
            binding = ticket.bindings.filter(revoked_at__isnull=True).first()
            if binding is not None:
                outbox.enqueue("guest.parked", binding=binding, ticket=ticket, template="guest.parked",
                               params={"ticket": f"#{ticket.display_number:03d}"},
                               dedupe_key=f"guest.parked:{ticket.id}", now=now)
            _audit("ticket.parked", valet, ticket, hook=int(hook_number), zone=ticket.location_zone.code)
    except IntegrityError as exc:
        raise DomainError("hook_occupied") from exc
    return ticket


def transfer_intake(actor, ticket, to_staff, reason: str, now=None) -> CustodyTransfer:
    """Explicit intake handoff so `parked_by` and retrieval priority follow the person who parks."""
    now = now or timezone.now()
    if not has_role(actor, Role.SUPERVISOR) or not can_access_event(actor, ticket.event):
        raise DomainError("forbidden")
    if not reason.strip():
        raise DomainError("reason_required")
    if not shifts.is_available(to_staff, ticket.event):
        raise DomainError("receiver_unavailable")
    try:
        with transaction.atomic():
            ticket = _lock_ticket(ticket)
            task = intake_task(ticket)
            if task is None or ticket.state != Ticket.State.RECEIVED:
                raise DomainError("invalid_state")
            previous = task.assignee
            task.status = Task.Status.RELEASED
            task.released_at = now
            task.release_reason = "intake_transferred"
            task.save(update_fields=["status", "released_at", "release_reason"])
            Task.objects.create(event=ticket.event, ticket=ticket, type=Task.Type.INTAKE, status=Task.Status.ACCEPTED,
                                assignee=to_staff, reserved_at=now, accepted_at=now)
            shifts.on_task_released(previous, now)
            transfer = CustodyTransfer.objects.create(
                ticket=ticket, task=task, kind=CustodyTransfer.Kind.INTAKE_HANDOFF, from_staff=previous,
                to_staff=to_staff, vehicle_location="intake area", key_location=f"with {previous.full_name}",
                reason=reason.strip()[:200], initiated_by=actor)
            _audit("ticket.intake_transfer", actor, ticket, channel="console", to=to_staff.id, frm=previous.id)
            from messaging import notify

            notify.intake_transferred(transfer)
    except IntegrityError as exc:
        raise DomainError("receiver_unavailable") from exc
    return transfer


def acknowledge_intake_transfer(staff, transfer, now=None) -> CustodyTransfer:
    now = now or timezone.now()
    with transaction.atomic():
        transfer = CustodyTransfer.objects.select_for_update(no_key=True).get(pk=transfer.pk)
        if transfer.to_staff_id != staff.id:
            raise DomainError("forbidden")
        if transfer.acknowledged_at is None:
            transfer.acknowledged_at = now
            transfer.acknowledged_by = staff
            transfer.save(update_fields=["acknowledged_at", "acknowledged_by"])
            _audit("custody.acknowledged", staff, transfer.ticket, transfer=transfer.id)
    return transfer


def cancel_ticket(actor, ticket, reason: str, *, guest_has_vehicle_and_keys: bool, now=None) -> Ticket:
    """Abandoned intake only, before parking starts, with the guest-has-car-and-keys confirmation."""
    now = now or timezone.now()
    if not guest_has_vehicle_and_keys:
        raise DomainError("confirmation_required")
    if not reason.strip():
        raise DomainError("reason_required")
    with transaction.atomic():
        ticket = _lock_ticket(ticket)
        sent = ticket.bindings.exists()
        is_supervisor = has_role(actor, Role.SUPERVISOR) and can_access_event(actor, ticket.event)
        if not is_supervisor:
            task = intake_task(ticket)
            if sent or task is None or task.assignee_id != actor.id:
                raise DomainError("forbidden")
        if ticket.parking_started_at is not None:
            raise DomainError("parking_started")
        if ticket.state != Ticket.State.RECEIVED:
            raise DomainError("not_cancellable")
        RetrievalRequest.objects.filter(
            ticket=ticket, state__in=["WAITING_FOR_PARKING", "QUEUED", "OFFERED", "ACCEPTED"]
        ).update(state=RetrievalRequest.State.WITHDRAWN, withdrawn_at=now, withdrawn_by=actor,
                 withdraw_reason="ticket_cancelled")
        task = intake_task(ticket)
        if task is not None:
            task.status = Task.Status.CANCELLED
            task.released_at = now
            task.release_reason = "ticket_cancelled"
            task.save(update_fields=["status", "released_at", "release_reason"])
            shifts.on_task_released(task.assignee, now)
        tokens.revoke(ticket=ticket, now=now)
        ticket.codes.filter(consumed_at__isnull=True, revoked_at__isnull=True).update(revoked_at=now)
        ticket.state = Ticket.State.CANCELLED
        ticket.cancelled_at = now
        ticket.cancelled_by = actor
        ticket.cancel_reason = reason.strip()[:200]
        _bump(ticket, "state", "cancelled_at", "cancelled_by", "cancel_reason")
        binding = ticket.bindings.filter(revoked_at__isnull=True).first()
        if binding is not None:
            outbox.enqueue("guest.cancelled", binding=binding, ticket=ticket, template="guest.cancelled",
                           params={"ticket": f"#{ticket.display_number:03d}"},
                           dedupe_key=f"guest.cancelled:{ticket.id}", now=now)
        if task is not None and task.assignee_id != actor.id:
            outbox.enqueue("valet.cancelled", staff=task.assignee, ticket=ticket, template="valet.cancelled",
                           params={"ticket": f"#{ticket.display_number:03d}"},
                           dedupe_key=f"valet.cancelled:{ticket.id}", now=now)
        _audit("ticket.cancel", actor, ticket, channel="console" if is_supervisor else staff_channel(),
               reason=ticket.cancel_reason, guest_has_vehicle_and_keys=True)
    return ticket


def media_limits() -> tuple[int, set]:
    return settings.MEDIA_MAX_BYTES, settings.MEDIA_ALLOWED_TYPES
