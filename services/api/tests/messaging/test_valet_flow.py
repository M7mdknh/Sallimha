import pytest

from ops.models import GuestBinding, Shift, Ticket
from ops.services import shifts
from tests.factories import open_shift
from tests.wa import button, last, photo, say, tap


@pytest.fixture
def valet(world):
    v = world.valets[0]
    open_shift(world.event, v, world.supervisor)
    return v


def test_full_intake_via_whatsapp_reaches_parked(world, valet):
    p = valet.phone_e164
    say(p, "مركبة جديدة")
    assert last(valet).template == "valet.ask_phone"
    say(p, "٠٥٠١٢٣٤٥٦٧")
    confirm = last(valet)
    assert confirm.template == "valet.confirm_phone" and confirm.params["masked"] == "+966 5••••4567"
    tap(p, button(confirm, "confirm_phone"))
    ticket = Ticket.objects.get()
    assert last(binding=ticket.bindings.get(), kind="guest.ticket") is not None
    tap(p, button(last(valet), "receipt_yes"))
    ticket.refresh_from_db()
    assert ticket.contact_state == "CONFIRMED_IN_PERSON"
    say(p, "ABC 1234 كامري بيضاء")
    for _ in range(4):
        photo(p)
    tap(p, button(last(valet), "start_parking"))
    say(p, "A 12")
    say(p, "١٥")
    ticket.refresh_from_db()
    assert ticket.state == Ticket.State.PARKED and ticket.parked_by == valet
    assert ticket.vehicle_plate == "ABC 1234" and ticket.location_detail == "12"
    assert last(valet).template == "valet.parked_done"


def test_numeric_text_outside_prompt_is_not_guessed(world, valet):
    say(valet.phone_e164, "12")
    assert last(valet).template == "valet.unknown_input"
    assert not Ticket.objects.exists()


def test_invalid_phone_reprompts_without_binding(world, valet):
    say(valet.phone_e164, "مركبة جديدة")
    say(valet.phone_e164, "12")
    assert last(valet).template == "valet.phone_invalid"
    assert not GuestBinding.objects.exists()


def test_ready_button_sets_available(world):
    v = world.valets[1]
    shift = shifts.start_shift(world.supervisor, world.event, v)
    invite = last(v, kind="valet.shift_started")
    tap(v.phone_e164, button(invite, "ready"))
    shift.refresh_from_db()
    assert shift.availability == Shift.Availability.AVAILABLE
    assert last(v).template == "valet.available_ok"


def test_break_request_pending_while_intake(world, valet):
    say(valet.phone_e164, "مركبة جديدة")
    say(valet.phone_e164, "استراحة")
    assert last(valet).template == "valet.break_pending"


def test_other_valets_button_is_rejected(world, valet):
    other = world.valets[1]
    open_shift(world.event, other, world.supervisor)
    say(valet.phone_e164, "مركبة جديدة")
    say(valet.phone_e164, "0501234567")
    payload = button(last(valet), "confirm_phone")
    tap(other.phone_e164, payload)
    assert last(other).template == "valet.stale"
    assert not GuestBinding.objects.exists()


def test_duplicate_button_tap_has_no_second_effect(world, valet):
    say(valet.phone_e164, "مركبة جديدة")
    say(valet.phone_e164, "0501234567")
    payload = button(last(valet), "confirm_phone")
    tap(valet.phone_e164, payload)
    tap(valet.phone_e164, payload)
    assert GuestBinding.objects.count() == 1
    assert last(valet).template == "valet.duplicate"


def test_new_car_while_busy_reports_current_ticket(world, valet):
    say(valet.phone_e164, "مركبة جديدة")
    say(valet.phone_e164, "مركبة جديدة")
    assert last(valet).template in {"valet.busy", "valet.ask_phone"}
    assert Ticket.objects.count() == 1


def test_unknown_sender_is_not_treated_as_staff(world, valet):
    say("+966509999999", "مركبة جديدة")
    assert not Ticket.objects.exists()
