import pytest
from django.test import override_settings

from core.errors import DomainError
from messaging.models import MessageOutbox
from ops.models import Alert, KeyOccupancy, RetrievalRequest, Task, Ticket
from ops.services import intake
from tests.factories import make_event, make_staff, open_shift
from tests.ops.intake_helpers import JPEG, park, register_and_confirm, through_photos


@pytest.fixture
def on_shift(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


def test_register_reserves_valet_and_numbers_ticket(on_shift):
    valet = on_shift.valets[0]
    ticket = intake.register_vehicle(valet)
    assert ticket.state == Ticket.State.RECEIVED and ticket.display_number == 1
    assert Task.objects.get(ticket=ticket).status == "ACCEPTED"
    with pytest.raises(DomainError) as err:
        intake.register_vehicle(valet)
    assert err.value.code == "busy"


def test_register_requires_shift(world):
    with pytest.raises(DomainError) as err:
        intake.register_vehicle(world.valets[0])
    assert err.value.code == "not_on_shift"


def test_phone_never_confused_with_hook(on_shift):
    ticket = intake.register_vehicle(on_shift.valets[0])
    with pytest.raises(DomainError) as err:
        intake.set_guest_phone(on_shift.valets[0], ticket, "١٢")
    assert err.value.code == "phone_invalid"


def test_ticket_sent_before_parking_remains_received(on_shift):
    """AT-02."""
    ticket = register_and_confirm(on_shift.valets[0], on_shift.event)
    ticket.refresh_from_db()
    assert ticket.state == Ticket.State.RECEIVED
    msg = MessageOutbox.objects.get(kind="guest.ticket", ticket=ticket)
    assert msg.binding.phone_masked == "+966 5••••4567"
    assert msg.buttons[0][1] == "request_car" and msg.buttons[0][0].startswith("v1:")


def test_receipt_confirmation_only_by_staff(on_shift):
    """AT-35: provider status never confirms; only the staff answer does."""
    valet = on_shift.valets[0]
    ticket = register_and_confirm(valet, on_shift.event)
    msg = MessageOutbox.objects.get(kind="guest.ticket", ticket=ticket)
    msg.status = "READ"
    msg.save()
    ticket.refresh_from_db()
    assert ticket.contact_state == Ticket.Contact.UNCONFIRMED
    intake.confirm_guest_receipt(valet, ticket, False)
    ticket.refresh_from_db()
    assert ticket.contact_state == Ticket.Contact.UNCONFIRMED
    assert Alert.objects.filter(kind="guest_contact_unconfirmed", ticket=ticket).exists()
    intake.confirm_guest_receipt(valet, ticket, True)
    ticket.refresh_from_db()
    assert ticket.contact_state == Ticket.Contact.CONFIRMED_IN_PERSON


def test_parking_requires_photos_or_exception(on_shift):
    """AT-03."""
    valet = on_shift.valets[0]
    ticket = register_and_confirm(valet, on_shift.event)
    intake.record_vehicle(valet, ticket, "ABC 1234")
    intake.attach_intake_media(valet, ticket, JPEG, "image/jpeg")
    with pytest.raises(DomainError) as err:
        intake.start_parking(valet, ticket)
    assert err.value.code == "photos_incomplete"
    with pytest.raises(DomainError):
        intake.except_intake_requirement(valet, ticket, "photos", "rain")  # valets cannot grant exceptions
    intake.except_intake_requirement(on_shift.supervisor, ticket, "photos", "camera failure")
    intake.start_parking(valet, ticket)


def test_vehicle_identifier_required(on_shift):
    valet = on_shift.valets[0]
    ticket = register_and_confirm(valet, on_shift.event)
    for _ in range(4):
        intake.attach_intake_media(valet, ticket, JPEG, "image/jpeg")
    with pytest.raises(DomainError) as err:
        intake.start_parking(valet, ticket)
    assert err.value.code == "vehicle_unidentified"


def test_rejects_non_image_and_oversize_media(on_shift):
    valet = on_shift.valets[0]
    ticket = register_and_confirm(valet, on_shift.event)
    with pytest.raises(DomainError):
        intake.attach_intake_media(valet, ticket, b"%PDF-1.7", "application/pdf")
    with override_settings(MEDIA_MAX_BYTES=10), pytest.raises(DomainError):
        intake.attach_intake_media(valet, ticket, JPEG, "image/jpeg")


def test_parked_after_location_and_hook_releases_valet(on_shift):
    valet = on_shift.valets[0]
    ticket = park(valet, on_shift.event, hook=7)
    assert ticket.state == Ticket.State.PARKED and ticket.parked_by == valet
    assert KeyOccupancy.objects.get(ticket=ticket, released_at__isnull=True).hook_number == 7
    assert MessageOutbox.objects.filter(kind="guest.parked", ticket=ticket).exists()
    from ops.services.shifts import is_available
    assert is_available(valet, on_shift.event)


def test_hook_collision_rejected_across_events(on_shift):
    """AT-33 / AT-43: venue hooks are shared by every event at the venue."""
    park(on_shift.valets[0], on_shift.event, hook=12)
    later = make_event(venue=on_shift.event.venue, name="Later")
    v_later = make_staff(on_shift.org)
    open_shift(later, v_later, on_shift.supervisor)
    ticket = register_and_confirm(v_later, later, phone="+966509999999")
    through_photos(v_later, ticket)
    intake.start_parking(v_later, ticket)
    intake.record_location(v_later, ticket, "A", "3")
    with pytest.raises(DomainError) as err:
        intake.complete_parking(v_later, ticket, 12)
    assert err.value.code == "hook_occupied"


def test_hook_out_of_range_rejected(on_shift):
    valet = on_shift.valets[0]
    ticket = register_and_confirm(valet, on_shift.event)
    through_photos(valet, ticket)
    intake.start_parking(valet, ticket)
    intake.record_location(valet, ticket, "A", "1")
    with pytest.raises(DomainError) as err:
        intake.complete_parking(valet, ticket, 999)
    assert err.value.code == "hook_invalid"


def test_intake_transfer_sets_parked_by(on_shift):
    """AT-37."""
    a, b = on_shift.valets[0], on_shift.valets[1]
    ticket = register_and_confirm(a, on_shift.event)
    through_photos(a, ticket)
    transfer = intake.transfer_intake(on_shift.supervisor, ticket, b, "A needed at the door")
    intake.acknowledge_intake_transfer(b, transfer)
    intake.start_parking(b, ticket)
    intake.record_location(b, ticket, "B", "4")
    intake.complete_parking(b, ticket, 30)
    ticket.refresh_from_db()
    assert ticket.parked_by == b and ticket.registered_by == a
    with pytest.raises(DomainError):
        intake.start_parking(a, ticket)


def test_cancel_before_parking_with_confirmation(on_shift):
    """AT-55."""
    valet = on_shift.valets[0]
    ticket = register_and_confirm(valet, on_shift.event)
    intake.cancel_ticket(on_shift.supervisor, ticket, "guest left with car", guest_has_vehicle_and_keys=True)
    ticket.refresh_from_db()
    assert ticket.state == Ticket.State.CANCELLED
    from ops.services.shifts import live_task
    assert live_task(valet) is None


def test_cancel_refused_without_confirmation(on_shift):
    ticket = register_and_confirm(on_shift.valets[0], on_shift.event)
    with pytest.raises(DomainError) as err:
        intake.cancel_ticket(on_shift.supervisor, ticket, "changed mind", guest_has_vehicle_and_keys=False)
    assert err.value.code == "confirmation_required"


def test_cancel_refused_after_parking_started(on_shift):
    valet = on_shift.valets[0]
    ticket = register_and_confirm(valet, on_shift.event)
    through_photos(valet, ticket)
    intake.start_parking(valet, ticket)
    with pytest.raises(DomainError) as err:
        intake.cancel_ticket(on_shift.supervisor, ticket, "guest left", guest_has_vehicle_and_keys=True)
    assert err.value.code == "parking_started"


def test_valet_cannot_cancel_after_ticket_sent(on_shift):
    valet = on_shift.valets[0]
    ticket = register_and_confirm(valet, on_shift.event)
    with pytest.raises(DomainError) as err:
        intake.cancel_ticket(valet, ticket, "guest left", guest_has_vehicle_and_keys=True)
    assert err.value.code == "forbidden"


def test_valet_can_abandon_draft_before_ticket_sent(on_shift):
    valet = on_shift.valets[0]
    ticket = intake.register_vehicle(valet)
    intake.cancel_ticket(valet, ticket, "wrong button", guest_has_vehicle_and_keys=True)
    ticket.refresh_from_db()
    assert ticket.state == Ticket.State.CANCELLED


def test_cancel_cascade_withdraws_request_revokes_tokens(on_shift):
    """AT-56."""
    from ops.models import ActionToken
    valet = on_shift.valets[0]
    ticket = register_and_confirm(valet, on_shift.event)
    req = RetrievalRequest.objects.create(event=on_shift.event, ticket=ticket, state="WAITING_FOR_PARKING",
                                          requested_at=ticket.created_at, requested_via="guest_whatsapp")
    intake.cancel_ticket(on_shift.supervisor, ticket, "guest left", guest_has_vehicle_and_keys=True)
    req.refresh_from_db()
    assert req.state == "WITHDRAWN" and req.withdraw_reason == "ticket_cancelled"
    assert not ActionToken.objects.filter(ticket=ticket, revoked_at__isnull=True, used_at__isnull=True).exists()
    assert MessageOutbox.objects.filter(kind="guest.cancelled", ticket=ticket).exists()


def test_early_request_becomes_queued_on_parking(on_shift):
    valet = on_shift.valets[0]
    ticket = register_and_confirm(valet, on_shift.event)
    req = RetrievalRequest.objects.create(event=on_shift.event, ticket=ticket, state="WAITING_FOR_PARKING",
                                          requested_at=ticket.created_at, requested_via="guest_whatsapp")
    intake.confirm_guest_receipt(valet, ticket, True)
    through_photos(valet, ticket)
    intake.start_parking(valet, ticket)
    intake.record_location(valet, ticket, "A", "1")
    intake.complete_parking(valet, ticket, 1)
    req.refresh_from_db()
    assert req.state == "QUEUED" and req.requested_at == ticket.created_at and req.eligible_at is not None
