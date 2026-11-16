"""Valet WhatsApp conversation (ADR-0006, docs/04 intake table).

Every reply is enqueued with a dedupe key derived from the inbound message id, so reprocessing an
inbox row never sends a second reply. Free text is interpreted only inside an explicit prompt.
"""

import logging

from core.crypto import decrypt_text, encrypt_text, keyed_hash_candidates
from core.errors import DomainError
from core.phone import normalize_digits
from messaging import outbox
from messaging.models import Conversation
from messaging.parse import Inbound
from ops.models import ParkingZone, Staff, Ticket
from ops.services import intake, shifts, tokens

log = logging.getLogger(__name__)

COMMANDS = {
    "new": {"مركبة جديدة", "مركبه جديده", "جديدة", "new car", "new"},
    "ready": {"جاهز", "ready"},
    "break": {"استراحة", "استراحه", "غير متاح", "break", "unavailable"},
    "help": {"مساعدة", "مساعده", "help"},
}

ERROR_REPLIES = {
    "phone_invalid": "valet.phone_invalid",
    "zone_invalid": "valet.location_invalid",
    "hook_invalid": "valet.hook_invalid",
    "hook_occupied": "valet.hook_invalid",
    "not_on_shift": "valet.not_on_shift",
    "not_available": "valet.unavailable_ok",
}


def find_staff(inb: Inbound):
    if inb.from_phone:
        staff = Staff.objects.filter(phone_hash__in=keyed_hash_candidates(inb.from_phone, "phone"),
                                     enabled=True).first()
        if staff:
            if inb.from_user_id and not staff.wa_user_id:
                Staff.objects.filter(pk=staff.pk, wa_user_id__isnull=True).update(wa_user_id=inb.from_user_id)
            return staff
    if inb.from_user_id:
        return Staff.objects.filter(wa_user_id=inb.from_user_id, enabled=True).first()
    return None


class Reply:
    def __init__(self, staff: Staff, inb: Inbound):
        self.staff, self.inb, self.n = staff, inb, 0

    def __call__(self, template: str, ticket=None, buttons=(), **params):
        self.n += 1
        if ticket is not None:
            params.setdefault("ticket", t(ticket))
        outbox.enqueue(template, staff=self.staff, ticket=ticket, template=template, params=params,
                       buttons=buttons, dedupe_key=f"reply:{self.inb.provider_message_id}:{self.n}")


def t(ticket: Ticket) -> str:
    return f"#{ticket.display_number:03d}"


def _command(text: str) -> str | None:
    cleaned = " ".join(text.strip().lower().split())
    return next((name for name, words in COMMANDS.items() if cleaned in words), None)


def _zones(ticket: Ticket) -> str:
    return "، ".join(ParkingZone.objects.filter(venue_id=ticket.event.venue_id, active=True)
                    .order_by("code").values_list("code", flat=True))


def _set(conv: Conversation, step: str, ticket=None, **data) -> None:
    conv.step = step
    conv.ticket = ticket
    conv.data = data
    conv.save(update_fields=["step", "ticket", "data", "updated_at"])


def _ticket_buttons(staff, ticket, *pairs):
    return [(tokens.issue(purpose, staff=staff, ticket=ticket), key) for purpose, key in pairs]


def handle(staff: Staff, inb: Inbound) -> None:
    outbox.note_inbound(staff=staff, at=inb.timestamp)
    conv, _ = Conversation.objects.select_for_update(no_key=True).get_or_create(party_key=f"staff:{staff.id}")
    reply = Reply(staff, inb)
    try:
        if inb.button_payload:
            _button(staff, conv, inb, reply)
        elif inb.msg_type == "image":
            _image(staff, conv, inb, reply)
        else:
            _text(staff, conv, inb.text or "", reply)
    except DomainError as err:
        _on_error(err, conv, reply)


def _on_error(err: DomainError, conv: Conversation, reply: Reply) -> None:
    ticket, code = conv.ticket, err.code
    if code == "busy":
        task = shifts.live_task(reply.staff)
        return reply("valet.busy", ticket=task.ticket) if task else reply("valet.unknown_input")
    if code == "zone_invalid" and ticket is not None:
        return reply("valet.location_invalid", zones=_zones(ticket))
    if code == "photos_incomplete" and ticket is not None:
        return reply("valet.photo_count", ticket=ticket, count=intake.intake_photo_count(ticket))
    if code == "vehicle_unidentified" and ticket is not None:
        return reply("valet.ask_vehicle", ticket=ticket)
    if code in {"phone_invalid", "hook_invalid", "hook_occupied", "not_on_shift", "not_available"}:
        return reply(ERROR_REPLIES[code])
    if code in {"not_intake_owner", "forbidden", "invalid_state", "stale"}:
        return reply("valet.stale")
    log.info("valet action refused: %s", code)
    return reply("valet.unknown_input")


# --- text -------------------------------------------------------------------------------------

def _text(staff, conv, text, reply):
    command = _command(text)
    if command == "new":
        return _new_car(staff, conv, reply)
    if command == "ready":
        return _availability(staff, True, reply)
    if command == "break":
        return _availability(staff, False, reply)
    if command == "help":
        task = shifts.live_task(staff)
        return reply("valet.help", current=t(task.ticket) if task else "—")
    ticket = conv.ticket
    if conv.step == "awaiting_phone" and ticket:
        parsed = intake.set_guest_phone(staff, ticket, text)
        _set(conv, "awaiting_phone_confirm", ticket, phone_enc=encrypt_text(parsed.e164))
        buttons = _ticket_buttons(staff, ticket, ("intake_phone_ok", "confirm_phone"),
                                  ("intake_phone_edit", "edit_phone"))
        return reply("valet.confirm_phone", ticket=ticket, buttons=buttons, masked=parsed.masked)
    if conv.step == "awaiting_vehicle" and ticket:
        intake.record_vehicle(staff, ticket, text)
        _set(conv, "awaiting_photos", ticket)
        return reply("valet.ask_photos", ticket=ticket)
    if conv.step == "awaiting_location" and ticket:
        parts = normalize_digits(text).split(maxsplit=1)
        if not parts:
            raise DomainError("zone_invalid")
        intake.record_location(staff, ticket, parts[0], parts[1] if len(parts) > 1 else "")
        _set(conv, "awaiting_hook", ticket)
        return reply("valet.ask_hook", ticket=ticket)
    if conv.step == "awaiting_hook" and ticket:
        digits = normalize_digits(text).strip()
        if not digits.isdigit():
            raise DomainError("hook_invalid")
        intake.complete_parking(staff, ticket, int(digits))
        ticket.refresh_from_db()
        _set(conv, "idle")
        location = f"{ticket.location_zone.code} {ticket.location_detail}".strip()
        return reply("valet.parked_done", ticket=ticket, location=location, hook=digits)
    from messaging.flows import valet_retrieval

    if valet_retrieval.handle_text(staff, conv, text, reply):
        return None
    return reply("valet.unknown_input")


def _new_car(staff, conv, reply):
    ticket = intake.register_vehicle(staff)
    _set(conv, "awaiting_phone", ticket)
    reply("valet.ask_phone", ticket=ticket)


def _availability(staff, available: bool, reply):
    result = shifts.set_availability(staff, available)
    template = {"available": "valet.available_ok", "unavailable": "valet.unavailable_ok",
                "break_pending": "valet.break_pending", "no_shift": "valet.not_on_shift"}[result]
    reply(template)


# --- images -----------------------------------------------------------------------------------

def _incident_choices(staff):
    """Open incidents on tickets this valet holds or handled in their current event (never 'the latest')."""
    from django.db.models import Q

    from ops.models import Incident

    shift = shifts.open_shift_for(staff)
    if shift is None:
        return []
    return list(Incident.objects.filter(event=shift.event, status__in=["OPEN", "IN_REVIEW"], ticket__isnull=False)
                .filter(Q(ticket__registered_by=staff) | Q(ticket__parked_by=staff) | Q(ticket__tasks__assignee=staff))
                .distinct().order_by("-id")[:3])


def _image(staff, conv, inb, reply):
    ticket = conv.ticket
    if conv.step != "awaiting_photos" or ticket is None:
        choices = _incident_choices(staff)
        if not choices:
            return reply("valet.photo_no_incident")
        buttons = [(tokens.issue("incident_photo", staff=staff, ticket=i.ticket,
                                 data={"incident_id": i.id, "media_id": inb.media_id, "mime": inb.media_mime or ""}),
                    "select_incident", {"incident": f"#{i.id}"}) for i in choices]
        return reply("valet.photo_choose_incident", buttons=buttons)
    from messaging.transport import get_transport

    data, content_type = get_transport().fetch_media(inb.media_id)
    intake.attach_intake_media(staff, ticket, data, inb.media_mime or content_type, provider_media_id=inb.media_id)
    count = intake.intake_photo_count(ticket)
    if count >= intake.REQUIRED_PHOTOS:
        _set(conv, "ready_to_park", ticket)
        buttons = _ticket_buttons(staff, ticket, ("intake_start_parking", "start_parking"))
        return reply("valet.ready_to_park", ticket=ticket, buttons=buttons)
    return reply("valet.photo_count", ticket=ticket, count=count)


# --- buttons ----------------------------------------------------------------------------------

def _button(staff, conv, inb, reply):
    token = tokens.resolve(inb.button_payload)
    if token is None or token.staff_id != staff.id:
        return reply("valet.stale")
    status = tokens.state(token)
    reusable = token.purpose in {"valet_ready", "valet_unavailable"}
    if status == "used" and not reusable:
        return reply("valet.duplicate")
    if status in {"revoked", "expired"}:
        return reply("valet.stale")
    handler = BUTTON_HANDLERS.get(token.purpose)
    if handler is None:
        from messaging.flows import valet_retrieval

        handler = valet_retrieval.BUTTON_HANDLERS.get(token.purpose)
    if handler is None:
        return reply("valet.stale")
    result = handler(staff, conv, token, reply)
    if not reusable:
        tokens.mark_used(token)
    return result


def _phone_ok(staff, conv, token, reply):
    ticket = token.ticket
    if conv.ticket_id != ticket.id or "phone_enc" not in conv.data:
        return reply("valet.stale")
    intake.confirm_guest_phone(staff, ticket, decrypt_text(conv.data["phone_enc"]), language="ar")
    _set(conv, "awaiting_receipt", ticket)
    buttons = _ticket_buttons(staff, ticket, ("intake_receipt_yes", "receipt_yes"), ("intake_receipt_no", "receipt_no"))
    reply("valet.ask_receipt", ticket=ticket, buttons=buttons)


def _phone_edit(staff, conv, token, reply):
    tokens.revoke(ticket=token.ticket, purposes=["intake_phone_ok", "intake_phone_edit"])
    _set(conv, "awaiting_phone", token.ticket)
    reply("valet.ask_phone", ticket=token.ticket)


def _receipt(received: bool):
    def handler(staff, conv, token, reply):
        ticket = token.ticket
        tokens.revoke(ticket=ticket, purposes=["intake_receipt_yes", "intake_receipt_no"])
        intake.confirm_guest_receipt(staff, ticket, received)
        if not received:
            reply("valet.receipt_unconfirmed", ticket=ticket)
        if conv.ticket_id == ticket.id and conv.step == "awaiting_receipt":
            _set(conv, "awaiting_vehicle", ticket)
            reply("valet.ask_vehicle", ticket=ticket)

    return handler


def _start_parking(staff, conv, token, reply):
    ticket = intake.start_parking(staff, token.ticket)
    _set(conv, "awaiting_location", ticket)
    reply("valet.ask_location", ticket=ticket, zones=_zones(ticket))


def _availability_button(available: bool):
    def handler(staff, conv, token, reply):
        _availability(staff, available, reply)

    return handler


def resume_step(ticket) -> str:
    if ticket.parking_started_at:
        return "awaiting_hook" if ticket.location_zone_id else "awaiting_location"
    if intake.intake_photo_count(ticket) >= intake.REQUIRED_PHOTOS:
        return "ready_to_park"
    if ticket.vehicle_plate or ticket.vehicle_description:
        return "awaiting_photos"
    return "awaiting_vehicle"


def _ack_intake_custody(staff, conv, token, reply):
    from ops.models import CustodyTransfer

    transfer = CustodyTransfer.objects.get(pk=token.data["transfer_id"])
    intake.acknowledge_intake_transfer(staff, transfer)
    ticket = transfer.ticket
    step = resume_step(ticket)
    _set(conv, step, ticket)
    prompts = {"awaiting_vehicle": "valet.ask_vehicle", "awaiting_photos": "valet.ask_photos",
               "awaiting_hook": "valet.ask_hook"}
    if step == "ready_to_park":
        reply("valet.ready_to_park", ticket=ticket,
              buttons=_ticket_buttons(staff, ticket, ("intake_start_parking", "start_parking")))
    elif step == "awaiting_location":
        reply("valet.ask_location", ticket=ticket, zones=_zones(ticket))
    else:
        reply(prompts[step], ticket=ticket)


def _incident_photo(staff, conv, token, reply):
    from messaging.transport import get_transport
    from ops.services.incidents import attach_photo

    data, content_type = get_transport().fetch_media(token.data["media_id"])
    incident = attach_photo(staff, token.data["incident_id"], data, token.data.get("mime") or content_type,
                            provider_media_id=token.data["media_id"])
    tokens.revoke(staff=staff, purposes=["incident_photo"])
    reply("valet.photo_attached", incident=f"#{incident.id}")


BUTTON_HANDLERS = {
    "incident_photo": _incident_photo,
    "intake_phone_ok": _phone_ok,
    "intake_phone_edit": _phone_edit,
    "intake_receipt_yes": _receipt(True),
    "intake_receipt_no": _receipt(False),
    "intake_start_parking": _start_parking,
    "valet_ready": _availability_button(True),
    "valet_unavailable": _availability_button(False),
    "ack_custody": _ack_intake_custody,
}
