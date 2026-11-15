"""Shared intake helpers for tests (synthetic data only)."""

from ops.services import intake

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


def register_and_confirm(valet, event, phone="+966501234567", language="ar"):
    ticket = intake.register_vehicle(valet)
    intake.set_guest_phone(valet, ticket, phone)
    intake.confirm_guest_phone(valet, ticket, phone, language=language)
    return ticket


def through_photos(valet, ticket):
    intake.record_vehicle(valet, ticket, "ABC 1234 كامري بيضاء")
    for _ in range(4):
        intake.attach_intake_media(valet, ticket, JPEG, "image/jpeg")


def park(valet, event, phone="+966501234567", hook=None, zone="A"):
    ticket = register_and_confirm(valet, event, phone)
    intake.confirm_guest_receipt(valet, ticket, True)
    through_photos(valet, ticket)
    intake.start_parking(valet, ticket)
    intake.record_location(valet, ticket, zone, "12")
    intake.complete_parking(valet, ticket, hook if hook is not None else ticket.display_number)
    ticket.refresh_from_db()
    return ticket
