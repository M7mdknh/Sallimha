"""Parking location with an optional confirmed pin (ADR-0013). Positions here are typed test values: no device,
no map service (SIMULATED)."""

import uuid
from datetime import UTC, datetime

import pytest
from django.test import override_settings

from ops.models import Ticket
from ops.services import relocation
from tests.app.test_valet_api import photo, post, register, work
from tests.console.conftest import login_as
from tests.factories import open_shift

GPS = {"lat": 24.764612, "lng": 46.640212, "location_source": "gps", "accuracy_m": 12.4,
       "location_device_at": "2026-11-18T19:02:11Z"}


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


def ready_to_park(client):
    ticket_id = register(client)
    for _ in range(4):
        photo(client, ticket_id)
    assert post(client, f"/api/valet/tickets/{ticket_id}/start-parking").status_code == 200
    return ticket_id


def park(client, ticket_id, **place):
    body = {"zone_code": "B", "detail": "12", "floor": "B1", "note": "beside pillar 12", "hook_number": 9, **place}
    return post(client, f"/api/valet/tickets/{ticket_id}/park", body)


def test_a_gps_pin_is_kept_with_its_accuracy_source_and_both_times(ops):
    app = login_as(ops.valets[0])
    ticket_id = ready_to_park(app)
    assert park(app, ticket_id, **GPS).status_code == 200
    t = Ticket.objects.get(pk=ticket_id)
    assert (float(t.location_lat), float(t.location_lng), t.location_source, t.location_accuracy_m) == (
        24.764612, 46.640212, "gps", 12.4)
    assert t.location_device_at == datetime(2026, 11, 18, 19, 2, 11, tzinfo=UTC)
    assert t.location_recorded_at is not None and t.location_recorded_at != t.location_device_at
    assert (t.location_floor, t.location_note) == ("B1", "beside pillar 12")


def test_parking_without_a_usable_pin_still_records_the_place(ops):
    app = login_as(ops.valets[0])
    ticket_id = ready_to_park(app)
    assert park(app, ticket_id).status_code == 200  # map unavailable, permission denied or no fix: text place only
    t = Ticket.objects.get(pk=ticket_id)
    assert t.state == "PARKED" and t.location_lat is None and t.location_source == ""
    assert t.location_zone.code == "B" and t.location_note == "beside pillar 12"


@pytest.mark.parametrize("place,code", [
    ({"lat": 24.7, "location_source": "gps", "accuracy_m": 10}, "location_pin_incomplete"),
    ({"lat": 124.7, "lng": 46.6, "location_source": "pin"}, "location_out_of_range"),
    ({"lat": 24.7, "lng": 46.6, "location_source": ""}, "location_source_invalid"),  # e.g. the venue centre
    ({"lat": 24.7, "lng": 46.6, "location_source": "gps"}, "location_accuracy_required"),
    ({"lat": 24.7, "lng": 46.6, "location_source": "gps", "accuracy_m": 400}, "location_inaccurate"),
])
def test_unconfirmed_or_invalid_pins_are_refused_and_nothing_is_parked(ops, place, code):
    app = login_as(ops.valets[0])
    ticket_id = ready_to_park(app)
    response = park(app, ticket_id, **place)
    assert response.status_code == 409 and response.json()["code"] == code
    assert Ticket.objects.get(pk=ticket_id).state == "RECEIVED"


def test_a_placed_pin_has_no_accuracy(ops):
    app = login_as(ops.valets[0])
    ticket_id = ready_to_park(app)
    assert park(app, ticket_id, lat=24.7646, lng=46.6402, location_source="pin", accuracy_m=80).status_code == 200
    t = Ticket.objects.get(pk=ticket_id)
    assert (t.location_source, t.location_accuracy_m) == ("pin", None)


def test_retrieval_shows_the_saved_place_and_pin(ops):
    from ops.services import dispatch, retrieval

    app = login_as(ops.valets[0])
    ticket_id = ready_to_park(app)
    park(app, ticket_id, **GPS)
    ticket = Ticket.objects.get(pk=ticket_id)
    retrieval.request_retrieval(ticket.bindings.get(), ticket)
    dispatch.dispatch_event(ops.event.id)
    place = work(app)["task"]["ticket"]["place"]
    assert (place["zone"], place["spot"], place["floor"], place["note"]) == ("B", "12", "B1", "beside pillar 12")
    assert place["pin"]["lat"] == 24.764612 and place["pin"]["source"] == "gps" and place["pin"]["accuracy_m"] == 12.4
    detail = login_as(ops.supervisor).get(f"/api/tickets/{ticket_id}").json()
    assert detail["place"]["pin"]["lng"] == 46.640212


def test_a_move_keeps_the_old_pin_until_it_is_completed_and_never_after(ops):
    app = login_as(ops.valets[0])
    ticket_id = ready_to_park(app)
    park(app, ticket_id, **GPS)
    ticket = Ticket.objects.get(pk=ticket_id)
    task = relocation.start_relocation(ops.supervisor, ticket, ops.valets[1], reason="clear the entrance")
    mover_app = login_as(ops.valets[1])
    assert post(mover_app, f"/api/valet/tasks/{task.id}/accept").status_code == 200
    assert float(Ticket.objects.get(pk=ticket_id).location_lat) == 24.764612  # still the confirmed old place
    moved = post(mover_app, f"/api/valet/tasks/{task.id}/moved",
                 {"zone_code": "A", "detail": "3", "hook_number": 9, "note": "ground floor, by the ramp"})
    assert moved.status_code == 200, moved.content
    t = Ticket.objects.get(pk=ticket_id)
    assert (t.location_zone.code, t.location_note, t.location_lat, t.location_source) == (
        "A", "ground floor, by the ramp", None, "")  # no new pin: the old one is cleared, never left behind


def test_a_move_with_a_new_pin_saves_it(ops):
    app = login_as(ops.valets[0])
    ticket_id = ready_to_park(app)
    park(app, ticket_id, **GPS)
    task = relocation.start_relocation(ops.supervisor, Ticket.objects.get(pk=ticket_id), ops.valets[1],
                                       reason="event entrance")
    mover_app = login_as(ops.valets[1])
    post(mover_app, f"/api/valet/tasks/{task.id}/accept")
    assert post(mover_app, f"/api/valet/tasks/{task.id}/moved",
                {"zone_code": "A", "detail": "3", "hook_number": 9, "lat": 24.7651, "lng": 46.6411,
                 "location_source": "pin"}).status_code == 200
    t = Ticket.objects.get(pk=ticket_id)
    assert (float(t.location_lat), t.location_source) == (24.7651, "pin")


def test_maps_config_is_empty_until_configured_and_never_needs_a_build(ops):
    valet = login_as(ops.valets[0])
    assert valet.get("/api/maps/config").json() == {"configured": False, "api_key": "", "map_id": ""}
    with override_settings(GOOGLE_MAPS_BROWSER_KEY="test-browser-key", GOOGLE_MAPS_MAP_ID="test-map"):
        assert login_as(ops.supervisor).get("/api/maps/config").json() == {
            "configured": True, "api_key": "test-browser-key", "map_id": "test-map"}
    from rest_framework.test import APIClient

    assert APIClient().get("/api/maps/config").status_code == 403


def test_admin_sets_the_venue_centre_and_the_valet_map_opens_there(ops):
    admin = login_as(ops.admin)
    venue = ops.event.venue
    body = {"lat": 24.7646, "lng": 46.6402}
    assert login_as(ops.supervisor).post(f"/api/venues/{venue.id}/map-centre", body, format="json",
                                         HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex).status_code == 403
    assert admin.post(f"/api/venues/{venue.id}/map-centre", body, format="json",
                      HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex).status_code == 200
    assert work(login_as(ops.valets[0]))["venue"]["centre"] == {"lat": 24.7646, "lng": 46.6402}
