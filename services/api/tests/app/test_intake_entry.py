"""Registering a car in the app (ADR-0013): customer number with a country, a structured plate, possible duplicates.
Customer messages are SIMULATED."""

import uuid

import pytest

from core.crypto import decrypt_text, keyed_hash
from ops.models import Ticket
from tests.console.conftest import login_as
from tests.factories import open_shift


def post(client, url, data=None, key=None):
    return client.post(url, data or {}, format="json", HTTP_IDEMPOTENCY_KEY=key or uuid.uuid4().hex)


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


def intake(client, **fields):
    body = {"guest_phone": "0501234567", "plate_kind": "SAUDI", "plate_letters": "ا ب ح", "plate_digits": "١٢٣٤",
            "vehicle_description": "كامري بيضاء", **fields}
    return post(client, "/api/valet/intake", body)


def test_a_saudi_plate_is_stored_as_entered_with_an_internal_search_key(ops):
    app = login_as(ops.valets[0])
    response = intake(app)
    assert response.status_code == 200, response.content
    ticket = Ticket.objects.get(pk=response.json()["id"])
    assert (ticket.plate_kind, ticket.vehicle_plate, ticket.plate_key) == ("SAUDI", "ا ب ح 1234", "ABJ1234")
    assert ticket.vehicle_description == "كامري بيضاء"
    assert decrypt_text(ticket.bindings.get().phone_enc) == "+966501234567"


def test_the_selected_country_reads_a_local_number(ops):
    app = login_as(ops.valets[0])
    response = intake(app, guest_phone="07911 123456", guest_region="GB")
    assert response.status_code == 200, response.content
    assert decrypt_text(Ticket.objects.get(pk=response.json()["id"]).bindings.get().phone_enc) == "+447911123456"


@pytest.mark.parametrize("phone,region,code", [
    ("0501234", "SA", "phone_too_short"), ("07911 123456", "SA", "phone_invalid_for_country"),
    ("05012a34567", "SA", "phone_not_a_number"), ("0501234567", "XX", "phone_country_unknown")])
def test_a_refused_number_says_why_and_registers_nothing(ops, phone, region, code):
    app = login_as(ops.valets[0])
    response = intake(app, guest_phone=phone, guest_region=region)
    assert response.status_code == 409 and response.json()["code"] == code
    assert not Ticket.objects.exists()


@pytest.mark.parametrize("fields,code", [
    ({"plate_letters": "اب ث"}, "plate_letter_unknown"), ({"plate_digits": "12345"}, "plate_digits_count"),
    ({"plate_kind": "OTHER", "plate_text": "x"}, "plate_other_invalid"),
    ({"plate_kind": "NONE", "vehicle_description": "سيارة", "plate_missing_reason": ""}, "reason_required"),
    ({"plate_kind": "NONE", "vehicle_description": "", "plate_missing_reason": "no plate"}, "vehicle_unidentified")])
def test_plate_refusals(ops, fields, code):
    response = intake(login_as(ops.valets[0]), **fields)
    assert response.status_code == 409 and response.json()["code"] == code
    assert not Ticket.objects.exists()


def test_other_and_missing_plates(ops):
    other = intake(login_as(ops.valets[0]), plate_kind="OTHER", plate_text="dxb a 12345")
    ticket = Ticket.objects.get(pk=other.json()["id"])
    assert (ticket.plate_kind, ticket.vehicle_plate, ticket.plate_key) == ("OTHER", "DXB A 12345", "DXBA12345")
    missing = intake(login_as(ops.valets[1]), plate_kind="NONE", vehicle_description="Silver Lexus, dented door",
                     plate_missing_reason="no front or rear plate")
    ticket = Ticket.objects.get(pk=missing.json()["id"])
    assert (ticket.plate_kind, ticket.vehicle_plate, ticket.plate_key) == ("NONE", "", "")
    assert ticket.vehicle_exception_reason == "no front or rear plate"


def test_one_customer_number_may_have_several_cars(ops):
    first = intake(login_as(ops.valets[0]))
    second = intake(login_as(ops.valets[1]), plate_letters="د ر س", plate_digits="55")
    assert first.status_code == second.status_code == 200
    assert Ticket.objects.filter(bindings__phone_hash=keyed_hash("+966501234567", "phone")).count() == 2


def test_a_possible_duplicate_is_shown_and_needs_an_explicit_choice(ops):
    first = intake(login_as(ops.valets[0]))
    again = intake(login_as(ops.valets[1]), plate_letters="ABJ", plate_digits="1234")  # same plate, Latin entry
    assert again.status_code == 409
    assert again.json() == {"code": "possible_duplicate", "ticket": first.json()["ticket"],
                            "ticket_state": "RECEIVED", "mine": False}
    assert Ticket.objects.count() == 1
    anyway = intake(login_as(ops.valets[1]), plate_letters="ABJ", plate_digits="1234", confirm_duplicate=True)
    assert anyway.status_code == 200 and Ticket.objects.count() == 2


def test_a_finished_ticket_does_not_block_a_later_visit(ops):
    from ops.services import intake as service

    first = intake(login_as(ops.valets[0]))
    service.cancel_ticket(ops.supervisor, Ticket.objects.get(pk=first.json()["id"]), "customer left",
                          guest_has_vehicle_and_keys=True)
    assert intake(login_as(ops.valets[1])).status_code == 200


def test_search_finds_a_plate_in_either_script(ops):
    intake(login_as(ops.valets[0]))
    supervisor = login_as(ops.supervisor)
    for q in ("ABJ 1234", "ا ب ح ١٢٣٤", "abj1234", "1234"):
        rows = supervisor.get(f"/api/events/{ops.event.id}/tickets", {"q": q}).json()
        assert [r["ticket"] for r in rows] == ["#001"], q
