"""The valet app's API (ADR-0011): the whole intake-to-delivery journey without any staff WhatsApp message, and the
limits of what a valet may read or do. Customer messages are SIMULATED."""

import uuid
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from messaging.models import MessageOutbox
from ops.models import ActionToken, RetrievalRequest, Task, Ticket
from ops.services import dispatch, retrieval
from tests.console.conftest import login_as
from tests.factories import open_shift
from tests.ops.intake_helpers import JPEG
from tests.wa import button, last, tap

GUEST = "+966501234001"


def post(client, url, data=None):
    return client.post(url, data or {}, format="json", HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex)


def photo(client, ticket_id, content=JPEG, name="car.jpg"):
    return client.post(f"/api/valet/tickets/{ticket_id}/photo",
                       {"photo": SimpleUploadedFile(name, content, content_type="image/jpeg")},
                       format="multipart", HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex)


def work(client):
    response = client.get("/api/valet/work")
    assert response.status_code == 200, response.content
    return response.json()


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


def car(vehicle: str) -> dict:
    """The structured entry (ADR-0013) for a test car: its plate typed as an 'other' plate."""
    return {"plate_kind": "OTHER", "plate_text": vehicle}


def register(client, phone=GUEST, vehicle="ABC 1234"):
    response = post(client, "/api/valet/intake", {"guest_phone": phone, **car(vehicle),
                                                  "vehicle_description": "كامري بيضاء"})
    assert response.status_code == 200, response.content
    return response.json()["id"]


def park(client, ticket_id, hook=7):
    for _ in range(4):
        assert photo(client, ticket_id).status_code == 200
    assert post(client, f"/api/valet/tickets/{ticket_id}/start-parking").status_code == 200
    response = post(client, f"/api/valet/tickets/{ticket_id}/park", {"zone_code": "A", "detail": "12",
                                                                     "hook_number": hook})
    assert response.status_code == 200, response.content


def test_full_journey_in_the_app_without_any_staff_whatsapp_message(ops):
    valet = ops.valets[0]
    app = login_as(valet)
    home = work(app)
    assert home["task"] is None and home["shift"]["availability"] == "available"
    assert home["shift"]["event"]["name"] == ops.event.name  # the operation comes from the assignment
    assert [z["code"] for z in home["venue"]["zones"]] == ["A", "B"]

    ticket_id = register(app)
    ticket = Ticket.objects.get(pk=ticket_id)
    binding = ticket.bindings.get()
    assert last(binding=binding, kind="guest.ticket") is not None  # the customer's ticket is queued at once
    task = work(app)["task"]
    assert (task["type"], task["step"]) == ("INTAKE", "photos")
    assert task["ticket"]["phone_masked"] == binding.phone_masked and GUEST not in str(task)

    for n in range(1, 5):
        assert photo(app, ticket_id).json()["count"] == n
    assert work(app)["task"]["step"] == "start_parking"  # no receipt question (ADR-0013)
    assert post(app, f"/api/valet/tickets/{ticket_id}/start-parking").status_code == 200
    assert work(app)["task"]["step"] == "park"
    parked = post(app, f"/api/valet/tickets/{ticket_id}/park", {"zone_code": "a", "detail": "12", "hook_number": 7})
    assert parked.status_code == 200
    ticket.refresh_from_db()
    assert ticket.state == "PARKED" and ticket.parked_by_id == valet.id
    assert work(app)["task"] is None

    tap(GUEST, button(last(binding=binding, kind="guest.ticket"), "request_car"))  # the customer, in WhatsApp
    (offer,) = dispatch.dispatch_event(ops.event.id)
    assert offer.assignee_id == valet.id and offer.offer_deadline is None  # window starts when the app shows it
    task = work(app)["task"]
    assert (task["type"], task["step"], task["id"], task["shown"]) == ("RETRIEVAL", "offer", offer.id, False)
    assert task["ticket"]["location"] == "A 12" and task["ticket"]["hook"] == 7
    assert post(app, f"/api/valet/tasks/{offer.id}/shown").json()["outcome"] == "shown"  # the card is on screen
    offer.refresh_from_db()
    assert offer.offer_sent_at is not None and offer.offer_deadline <= offer.hard_deadline

    assert post(app, f"/api/valet/tasks/{offer.id}/accept").status_code == 200
    assert work(app)["task"]["step"] == "bring"
    assert post(app, f"/api/valet/tasks/{offer.id}/ready").status_code == 200
    assert work(app)["task"]["step"] == "code"
    ready = last(binding=binding, kind="guest.ready")
    from core.crypto import decrypt_text
    from ops.models import CollectionCode

    code = decrypt_text(CollectionCode.objects.get(pk=ready.params["__code_id"]).delivery_enc)
    wrong = post(app, f"/api/valet/tasks/{offer.id}/code", {"code": "000000" if code != "000000" else "111111"})
    assert wrong.json() == {"outcome": "wrong", "remaining": 4}
    refused = post(app, f"/api/valet/tasks/{offer.id}/deliver")
    assert refused.status_code == 409 and refused.json()["code"] == "code_required"
    assert post(app, f"/api/valet/tasks/{offer.id}/code", {"code": code}).json()["outcome"] == "ok"
    assert work(app)["task"]["step"] == "deliver"
    assert post(app, f"/api/valet/tasks/{offer.id}/deliver").status_code == 200
    ticket.refresh_from_db()
    assert ticket.state == "DELIVERED" and ticket.delivered_by_id == valet.id
    home = work(app)
    assert home["task"] is None and [r["type"] for r in home["recent"]] == ["RETRIEVAL", "INTAKE"]

    assert not MessageOutbox.objects.filter(staff__isnull=False).exists()  # nothing was ever queued to staff
    assert not ActionToken.objects.filter(staff__isnull=False).exists()
    assert last(binding=binding, kind="guest.delivered") is not None


def test_a_refused_number_or_vehicle_registers_nothing(ops):
    app = login_as(ops.valets[0])
    bad = post(app, "/api/valet/intake", {"guest_phone": "12", **car("ABC 1234")})
    assert bad.status_code == 409 and bad.json()["code"] == "phone_too_short"
    blank = post(app, "/api/valet/intake", {"guest_phone": GUEST, **car(" ")})
    assert blank.json()["code"] == "plate_other_invalid"
    assert blank.status_code in (400, 409)
    assert not Ticket.objects.exists() and work(app)["task"] is None


def test_double_tap_and_a_second_tab_never_register_or_deliver_twice(ops):
    valet = ops.valets[0]
    tab_one = login_as(valet)
    tab_two = login_as(valet)
    key = uuid.uuid4().hex
    body = {"guest_phone": GUEST, **car("ABC 1234")}
    first = tab_one.post("/api/valet/intake", body, format="json", HTTP_IDEMPOTENCY_KEY=key)
    again = tab_one.post("/api/valet/intake", body, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert first.json() == again.json() and Ticket.objects.count() == 1
    other = post(tab_two, "/api/valet/intake", {"guest_phone": "+966501234002", **car("XYZ 77")})
    assert other.status_code == 409 and other.json()["code"] == "busy"  # one live task per valet
    ticket_id = first.json()["id"]
    park(tab_one, ticket_id)
    stale = post(tab_two, f"/api/valet/tickets/{ticket_id}/park", {"zone_code": "B", "detail": "1", "hook_number": 9})
    assert stale.status_code in (404, 409)
    ticket = Ticket.objects.get(pk=ticket_id)
    retrieval.request_retrieval(ticket.bindings.get(), ticket)
    (offer,) = dispatch.dispatch_event(ops.event.id)
    assert post(tab_one, f"/api/valet/tasks/{offer.id}/accept").status_code == 200
    assert post(tab_two, f"/api/valet/tasks/{offer.id}/accept").status_code == 200  # already accepted: no change
    assert Task.objects.filter(type="RETRIEVAL", status="ACCEPTED").count() == 1
    declined = post(tab_two, f"/api/valet/tasks/{offer.id}/decline")
    assert declined.status_code == 409 and Task.objects.get(pk=offer.id).status == "ACCEPTED"


def test_unseen_offer_expires_at_the_hard_limit_and_is_reassigned(ops):
    first_valet, second_valet = ops.valets[0], ops.valets[1]
    app = login_as(first_valet)
    park(app, register(app))
    ticket = Ticket.objects.get()
    start = timezone.now()
    retrieval.request_retrieval(ticket.bindings.get(), ticket, now=start)
    (offer,) = dispatch.dispatch_event(ops.event.id, now=start)
    assert offer.assignee_id == first_valet.id  # the valet who parked it comes first
    assert dispatch.expire_offers(start + timedelta(seconds=45)) == 0  # never shown: only the hard limit applies
    assert dispatch.expire_offers(start + timedelta(seconds=61)) == 1
    late = post(app, f"/api/valet/tasks/{offer.id}/accept")
    assert late.status_code == 409 and late.json()["code"] == "stale"
    (second,) = dispatch.dispatch_event(ops.event.id, now=start + timedelta(seconds=62))
    assert second.assignee_id == second_valet.id  # cooldown keeps it away from the valet who missed it
    assert RetrievalRequest.objects.get().requested_at == start  # the customer's waiting time is not reset
    other = login_as(second_valet)
    assert work(other)["task"]["id"] == second.id
    assert post(other, f"/api/valet/tasks/{second.id}/accept").status_code == 200


def test_a_seen_offer_expires_after_its_response_window(ops):
    app = login_as(ops.valets[0])
    park(app, register(app))
    ticket = Ticket.objects.get()
    retrieval.request_retrieval(ticket.bindings.get(), ticket)
    (offer,) = dispatch.dispatch_event(ops.event.id)
    assert post(app, f"/api/valet/tasks/{offer.id}/shown").status_code == 200
    shown = work(app)["task"]
    offer.refresh_from_db()
    assert shown["deadline"] is not None and offer.offer_deadline - offer.offer_sent_at == timedelta(seconds=30)
    assert dispatch.expire_offers(offer.offer_deadline + timedelta(seconds=1)) == 1
    assert work(app)["task"] is None


def test_decline_releases_the_offer_for_someone_else(ops):
    app = login_as(ops.valets[0])
    park(app, register(app))
    ticket = Ticket.objects.get()
    retrieval.request_retrieval(ticket.bindings.get(), ticket)
    (offer,) = dispatch.dispatch_event(ops.event.id)
    assert post(app, f"/api/valet/tasks/{offer.id}/decline").status_code == 200
    (second,) = dispatch.dispatch_event(ops.event.id)
    assert second.assignee_id != ops.valets[0].id


def test_parking_needs_the_photos_and_a_free_valid_hook(ops):
    app = login_as(ops.valets[0])
    ticket_id = register(app)
    early = post(app, f"/api/valet/tickets/{ticket_id}/start-parking")
    assert early.status_code == 409 and early.json()["code"] == "photos_incomplete"
    not_an_image = photo(app, ticket_id, content=b"not an image")
    assert not_an_image.status_code == 409 and not_an_image.json()["code"] == "media_content_mismatch"
    park(app, ticket_id, hook=7)
    other = login_as(ops.valets[1])
    second = register(other, phone="+966501234002", vehicle="XYZ 77")
    for _ in range(4):
        photo(other, second)
    post(other, f"/api/valet/tickets/{second}/start-parking")
    taken = post(other, f"/api/valet/tickets/{second}/park", {"zone_code": "A", "detail": "3", "hook_number": 7})
    assert taken.status_code == 409 and taken.json()["code"] == "hook_occupied"
    assert Ticket.objects.get(pk=second).location_zone_id is None  # refused whole: no half-recorded location
    unknown = post(other, f"/api/valet/tickets/{second}/park", {"zone_code": "Z", "detail": "", "hook_number": 8})
    assert unknown.json()["code"] == "zone_invalid"


def test_early_request_is_kept_and_shown_to_the_valet_who_is_parking(ops):
    app = login_as(ops.valets[0])
    ticket_id = register(app)
    ticket = Ticket.objects.get(pk=ticket_id)
    binding = ticket.bindings.get()
    tap(GUEST, button(last(binding=binding, kind="guest.ticket"), "request_car"))
    assert RetrievalRequest.objects.get().state == "WAITING_FOR_PARKING"
    assert work(app)["task"]["ticket"]["early_request"] is True
    park(app, ticket_id)
    assert RetrievalRequest.objects.get().state == "QUEUED"


def test_availability_and_break(ops):
    app = login_as(ops.valets[0])
    assert post(app, "/api/valet/availability", {"available": False}).json()["availability"] == "unavailable"
    refused = post(app, "/api/valet/intake", {"guest_phone": GUEST, **car("ABC 1234")})
    assert refused.status_code == 409 and refused.json()["code"] == "not_available"
    assert post(app, "/api/valet/availability", {"available": True}).json()["availability"] == "available"
    ticket_id = register(app)
    assert post(app, "/api/valet/availability", {"available": False}).json()["availability"] == "break_pending"
    park(app, ticket_id)
    assert work(app)["shift"]["availability"] == "unavailable"  # the break starts when the car is parked


def test_no_shift_shows_the_assigned_operation_and_refuses_work(world):
    app = login_as(world.valets[0])
    home = work(app)
    assert home["shift"] is None and home["assigned"]["event"] == world.event.name
    refused = post(app, "/api/valet/intake", {"guest_phone": GUEST, **car("ABC 1234")})
    assert refused.status_code == 409 and refused.json()["code"] == "not_on_shift"


def test_a_valet_reads_and_acts_on_their_own_work_only(ops):
    mine, theirs = login_as(ops.valets[0]), login_as(ops.valets[1])
    ticket_id = register(mine)
    assert photo(theirs, ticket_id).status_code == 404
    assert post(theirs, f"/api/valet/tickets/{ticket_id}/start-parking").status_code == 404
    assert work(theirs)["task"] is None
    park(mine, ticket_id)
    ticket = Ticket.objects.get(pk=ticket_id)
    retrieval.request_retrieval(ticket.bindings.get(), ticket)
    (offer,) = dispatch.dispatch_event(ops.event.id)
    for action in ("accept", "decline", "ready", "deliver"):
        assert post(theirs, f"/api/valet/tasks/{offer.id}/{action}").status_code == 404
    assert post(theirs, f"/api/valet/tasks/{offer.id}/code", {"code": "123456"}).status_code == 404
    assert Task.objects.get(pk=offer.id).status == "OFFERED"


@pytest.mark.parametrize("url", [
    "/api/events/", "/api/staff", "/api/carryover", "/api/config", "/api/outages", "/api/ops/dead-letters",
    "/api/integrations/whatsapp", "/api/dashboard",
])
def test_a_valet_account_has_no_console_access(ops, url):
    app = login_as(ops.valets[0])
    assert app.get(url).status_code == 403
    event = ops.event.id
    assert app.get(f"/api/events/{event}/live").status_code == 403
    assert app.get(f"/api/events/{event}/tickets?q=1").status_code == 403
    assert app.get(f"/api/events/{event}/export/guest-phones.csv").status_code == 403


def test_console_roles_cannot_use_the_valet_endpoints(ops):
    for person in (ops.supervisor, ops.admin):
        client = login_as(person)
        assert client.get("/api/valet/work").status_code == 403
        assert post(client, "/api/valet/intake", {"guest_phone": GUEST, **car("ABC 1234")}).status_code == 403


def test_signed_out_requests_are_refused(ops):
    from rest_framework.test import APIClient

    assert APIClient().get("/api/valet/work").status_code == 403


def test_handover_hold_blocks_delivery_in_the_app(ops):
    from ops.services import holds

    app = login_as(ops.valets[0])
    ticket_id = register(app)
    park(app, ticket_id)
    ticket = Ticket.objects.get(pk=ticket_id)
    binding = ticket.bindings.get()
    retrieval.request_retrieval(binding, ticket)
    (offer,) = dispatch.dispatch_event(ops.event.id)
    post(app, f"/api/valet/tasks/{offer.id}/accept")
    post(app, f"/api/valet/tasks/{offer.id}/ready")
    holds.place_hold(ops.supervisor, ticket, reason="Ownership dispute", blocks_dispatch=False, blocks_handover=True)
    from core.crypto import decrypt_text
    from ops.models import CollectionCode

    code = decrypt_text(CollectionCode.objects.get(ticket=ticket).delivery_enc)
    post(app, f"/api/valet/tasks/{offer.id}/code", {"code": code})
    assert work(app)["task"]["ticket"]["handover_blocked"] is True
    blocked = post(app, f"/api/valet/tasks/{offer.id}/deliver")
    assert blocked.status_code == 409 and blocked.json()["code"] == "handover_blocked"
    assert Ticket.objects.get(pk=ticket_id).state == "READY"
