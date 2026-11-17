"""Supervisor and admin work around the valet app (ADR-0011): moves and custody through the app, acting for a valet
whose device is down, customer contact and help, the customer-channel outage, and the admin dashboard.
Customer messages are SIMULATED."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from core.crypto import decrypt_text
from core.models import AuditEvent
from messaging import outbox
from messaging.models import MessageOutbox, SimulatorControl
from ops.models import Alert, CollectionCode, GuestMessage, Shift, Task, Ticket
from ops.services import dispatch, retrieval
from tests.app.test_valet_api import GUEST, park, photo, post, register, work
from tests.console.conftest import login_as
from tests.factories import open_shift
from tests.wa import last, say


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


def parked(ops, valet_index=0, phone=GUEST, hook=7):
    app = login_as(ops.valets[valet_index])
    ticket_id = register(app, phone=phone)
    park(app, ticket_id, hook=hook)
    return app, Ticket.objects.get(pk=ticket_id)


# --- relocation and custody through the app ---------------------------------------------------------------

def test_move_is_offered_accepted_and_completed_in_the_valet_app(ops):
    _app, ticket = parked(ops)
    sup, mover = login_as(ops.supervisor), login_as(ops.valets[1])
    started = post(sup, f"/api/tickets/{ticket.id}/relocate-start",
                   {"to_staff_id": ops.valets[1].id, "reason": "Blocking the fire lane"})
    assert started.status_code == 200, started.content
    task = work(mover)["task"]
    assert (task["type"], task["step"], task["reason"]) == ("RELOCATION", "offer", "Blocking the fire lane")
    assert task["ticket"]["location"] == "A 12" and task["ticket"]["hook"] == 7
    early = post(mover, f"/api/valet/tasks/{task['id']}/moved", {"zone_code": "B", "detail": "4", "hook_number": 21})
    assert early.status_code == 409 and early.json()["code"] == "not_accepted"  # nothing moves before acceptance
    assert post(mover, f"/api/valet/tasks/{task['id']}/accept").status_code == 200
    assert work(mover)["task"]["step"] == "move"
    done = post(mover, f"/api/valet/tasks/{task['id']}/moved", {"zone_code": "B", "detail": "4", "hook_number": 21})
    assert done.status_code == 200
    ticket.refresh_from_db()
    assert (ticket.location_zone.code, ticket.location_detail, ticket.state) == ("B", "4", "PARKED")
    assert ticket.key_occupancies.get(released_at__isnull=True).hook_number == 21
    assert work(mover)["task"] is None
    record = AuditEvent.objects.get(action="relocation.complete", entity_id=ticket.id)
    assert record.channel == "app" and record.summary["confirmed_via"] == "mover"


def test_declined_move_goes_back_to_the_supervisor_and_is_not_reassigned(ops):
    _app, ticket = parked(ops)
    sup, mover = login_as(ops.supervisor), login_as(ops.valets[1])
    post(sup, f"/api/tickets/{ticket.id}/relocate-start", {"to_staff_id": ops.valets[1].id, "reason": "Fire lane"})
    task_id = work(mover)["task"]["id"]
    assert post(mover, f"/api/valet/tasks/{task_id}/decline").status_code == 200
    assert Alert.objects.filter(kind="relocation_declined", ticket=ticket).exists()
    assert not Task.objects.filter(type="RELOCATION", status__in=["OFFERED", "ACCEPTED"]).exists()


def test_custody_transfer_is_acknowledged_in_the_app_before_the_new_valet_can_act(ops):
    app, ticket = parked(ops)
    binding = ticket.bindings.get()
    retrieval.request_retrieval(binding, ticket)
    (offer,) = dispatch.dispatch_event(ops.event.id)
    post(app, f"/api/valet/tasks/{offer.id}/accept")
    sup, receiver = login_as(ops.supervisor), login_as(ops.valets[1])
    moved = post(sup, f"/api/tickets/{ticket.id}/custody-transfer", {
        "to_staff_id": ops.valets[1].id, "vehicle_location": "Lane 2", "key_location": "With Majed",
        "reason": "First valet injured"})
    assert moved.status_code == 200, moved.content
    assert work(app)["task"] is None  # the first valet no longer holds it
    assert post(app, f"/api/valet/tasks/{offer.id}/ready").status_code == 409
    task = work(receiver)["task"]
    assert task["step"] == "custody_ack" and task["custody"]["vehicle_location"] == "Lane 2"
    assert post(receiver, f"/api/valet/tasks/{task['id']}/ready").status_code == 409  # not before acknowledging
    assert post(receiver, f"/api/valet/tasks/{task['id']}/custody-ack").status_code == 200
    assert work(receiver)["task"]["step"] == "bring"
    assert post(receiver, f"/api/valet/tasks/{task['id']}/ready").status_code == 200


def test_intake_handoff_is_acknowledged_in_the_app(ops):
    first = login_as(ops.valets[0])
    ticket_id = register(first)
    sup, second = login_as(ops.supervisor), login_as(ops.valets[1])
    assert post(sup, f"/api/tickets/{ticket_id}/intake-transfer",
                {"to_staff_id": ops.valets[1].id, "reason": "Called away"}).status_code == 200
    assert work(first)["task"] is None
    task = work(second)["task"]
    assert (task["type"], task["step"]) == ("INTAKE", "custody_ack")
    assert post(second, f"/api/valet/tasks/{task['id']}/custody-ack").status_code == 200
    assert work(second)["task"]["step"] == "photos"
    park(second, ticket_id)
    assert Ticket.objects.get(pk=ticket_id).parked_by_id == ops.valets[1].id


# --- staff connectivity loss: acting for one valet -------------------------------------------------------

def test_supervisor_records_for_a_valet_only_after_marking_their_device_as_not_working(ops):
    _app, ticket = parked(ops)
    retrieval.request_retrieval(ticket.bindings.get(), ticket)
    (offer,) = dispatch.dispatch_event(ops.event.id)
    sup = login_as(ops.supervisor)
    assert "relay_accept" not in sup.get(f"/api/tickets/{ticket.id}").json()["allowed_actions"]
    refused = post(sup, f"/api/tickets/{ticket.id}/relay-accept", {"confirmed_via": "radio"})
    assert refused.status_code == 409 and refused.json()["code"] == "valet_not_assisted"

    shift = Shift.objects.get(staff=offer.assignee, ended_at__isnull=True)
    assert post(sup, f"/api/shifts/{shift.id}/assist", {"on": True, "reason": ""}).json()["code"] == "reason_required"
    assert post(sup, f"/api/shifts/{shift.id}/assist", {"on": True, "reason": "Phone battery dead"}).status_code == 200
    member = next(m for m in sup.get(f"/api/events/{ops.event.id}/live").json()["team"]
                  if m["staff_id"] == offer.assignee_id)
    assert member["assisted"] is True
    detail = sup.get(f"/api/tickets/{ticket.id}").json()
    assert "relay_accept" in detail["allowed_actions"] and detail["primary_action"] == "relay_accept"
    assert post(sup, f"/api/tickets/{ticket.id}/relay-accept", {"confirmed_via": "radio"}).status_code == 200
    assert post(sup, f"/api/tickets/{ticket.id}/relay-ready", {"confirmed_via": "in_person"}).status_code == 200
    assert Ticket.objects.get(pk=ticket.id).state == "READY"
    accepted = AuditEvent.objects.get(action="dispatch.accepted", entity_id=ticket.id)
    assert accepted.summary["relayed_by"] == ops.supervisor.id and accepted.summary["confirmed_via"] == "radio"

    assert post(sup, f"/api/shifts/{shift.id}/assist", {"on": False}).status_code == 200
    assert AuditEvent.objects.filter(action="shift.assisted_off", entity_id=shift.id).exists()


def test_a_declared_customer_outage_does_not_allow_relays_for_valets_whose_app_works(ops):
    _app, ticket = parked(ops)
    retrieval.request_retrieval(ticket.bindings.get(), ticket)
    dispatch.dispatch_event(ops.event.id)
    declared = post(login_as(ops.admin), "/api/outages/whatsapp/declare", {"reason": "Provider incident"})
    assert declared.status_code == 200
    sup = login_as(ops.supervisor)
    assert "relay_accept" not in sup.get(f"/api/tickets/{ticket.id}").json()["allowed_actions"]
    assert post(sup, f"/api/tickets/{ticket.id}/relay-accept",
                {"confirmed_via": "radio"}).json()["code"] == "valet_not_assisted"


def test_registering_and_parking_for_a_valet_without_a_device(ops):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from tests.ops.intake_helpers import JPEG

    sup = login_as(ops.supervisor)
    valet = ops.valets[1]
    body = {"valet_id": valet.id, "guest_phone": "0501239876", "plate": "QRS 4455", "description": "",
            "reason": "Phone lost", "confirmed_via": "in_person"}
    refused = post(sup, f"/api/events/{ops.event.id}/intake-on-behalf", body)
    assert refused.status_code == 409 and refused.json()["code"] == "valet_not_assisted"
    shift = Shift.objects.get(staff=valet, ended_at__isnull=True)
    post(sup, f"/api/shifts/{shift.id}/assist", {"on": True, "reason": "Phone lost"})
    created = post(sup, f"/api/events/{ops.event.id}/intake-on-behalf", body)
    assert created.status_code == 200, created.content
    ticket_id = created.json()["id"]
    assert Ticket.objects.get(pk=ticket_id).state == "RECEIVED"
    assert sup.get(f"/api/tickets/{ticket_id}").json()["primary_action"] == "relay_intake_photo"
    for _ in range(4):
        sent = sup.post(f"/api/tickets/{ticket_id}/relay-intake-photo",
                        {"photo": SimpleUploadedFile("car.jpg", JPEG, content_type="image/jpeg"),
                         "confirmed_via": "in_person"}, format="multipart", HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex)
        assert sent.status_code == 200, sent.content
    assert sup.get(f"/api/tickets/{ticket_id}").json()["primary_action"] == "relay_parked"  # photos complete
    assert post(sup, f"/api/tickets/{ticket_id}/relay-parked", {
        "valet_id": valet.id, "zone_code": "B", "detail": "8", "hook_number": 88,
        "confirmed_via": "radio"}).status_code == 200
    assert Ticket.objects.get(pk=ticket_id).parked_by_id == valet.id


# --- customer contact and help ---------------------------------------------------------------------------

def test_contact_customer_opens_the_number_for_the_event_team_and_is_audited(ops):
    _app, ticket = parked(ops)
    sup = login_as(ops.supervisor)
    detail = sup.get(f"/api/tickets/{ticket.id}").json()
    assert detail["can_contact"] is True and GUEST not in str(detail)  # masked until opened
    opened = sup.post(f"/api/tickets/{ticket.id}/contact")
    assert opened.status_code == 200 and opened.json() == {"phone": GUEST}
    record = AuditEvent.objects.get(action="guest.contact_opened", entity_id=ticket.id)
    assert record.actor_id == ops.supervisor.id and GUEST not in str(record.summary)
    assert login_as(ops.valets[0]).post(f"/api/tickets/{ticket.id}/contact").status_code == 403
    from ops.models import Role
    from tests.factories import make_staff

    outsider = login_as(make_staff(ops.org, Role.SUPERVISOR, name="Other venue"))
    assert outsider.post(f"/api/tickets/{ticket.id}/contact").status_code == 404  # not on this event's team
    assert AuditEvent.objects.filter(action="guest.contact_opened").count() == 1


def test_contact_service_itself_refuses_people_outside_the_event(ops):
    from core.errors import DomainError
    from ops.models import Role
    from ops.services import contact
    from tests.factories import make_staff

    _app, ticket = parked(ops)
    for person in (make_staff(ops.org, Role.SUPERVISOR, name="Other venue"), ops.valets[0]):
        with pytest.raises(DomainError, match="forbidden"):
            contact.open_customer_contact(person, ticket)
    assert contact.open_customer_contact(ops.admin, ticket) == GUEST  # admins reach every event of the organisation
    assert AuditEvent.objects.filter(action="guest.contact_opened").count() == 1


def test_customer_help_message_reaches_the_event_team_and_is_kept_on_the_ticket(ops):
    _app, ticket = parked(ops)
    say(GUEST, "وين سيارتي؟ انتظرت كثير")
    message = GuestMessage.objects.get()
    assert message.ticket_id == ticket.id and message.text == "وين سيارتي؟ انتظرت كثير"
    alert = Alert.objects.get(kind="guest_help")
    assert alert.ticket_id == ticket.id and alert.event_id == ops.event.id
    assert last(binding=ticket.bindings.get()).kind == "guest.help_received"
    sup = login_as(ops.supervisor)
    assert [m["text"] for m in sup.get(f"/api/tickets/{ticket.id}").json()["guest_messages"]] == [message.text]
    assert any(a["kind"] == "guest_help" for a in sup.get(f"/api/events/{ops.event.id}/live").json()["attention"])
    say(GUEST, "ألو؟")
    assert GuestMessage.objects.count() == 2 and Alert.objects.filter(kind="guest_help").count() == 1  # one open item
    post(sup, f"/api/alerts/{alert.id}/ack")
    say(GUEST, "ما أحد رد")
    assert Alert.objects.filter(kind="guest_help").count() == 2  # a new item once the last was acknowledged


def test_help_from_an_unknown_number_stores_nothing(ops):
    parked(ops)
    say("+966509999999", "hello?")
    assert not GuestMessage.objects.exists() and not Alert.objects.filter(kind="guest_help").exists()


def test_a_staff_members_own_phone_is_just_a_customer_phone_on_whatsapp(ops):
    """Staff work in the app; a message from a valet's number gets the customer treatment, never the old flow."""
    say(ops.valets[0].phone_e164, "مركبة جديدة")
    assert not Ticket.objects.exists()
    assert not MessageOutbox.objects.filter(staff__isnull=False).exists()
    assert MessageOutbox.objects.get().kind == "guest.no_active_ticket"


def test_customer_request_word_still_requests_the_car(ops):
    _app, ticket = parked(ops)
    say(GUEST, "اطلب سيارتي")
    assert ticket.requests.get().state == "QUEUED" and not GuestMessage.objects.exists()


# --- staff keep working while the customer channel is down ------------------------------------------------

def test_staff_complete_the_journey_in_the_app_while_customer_whatsapp_is_down(ops):
    SimulatorControl.set_outage(True)
    try:
        app, ticket = parked(ops)  # registration, photos and parking need no WhatsApp at all
        binding = ticket.bindings.get()
        outbox.send_due(timezone.now())
        assert last(binding=binding, kind="guest.ticket").status == "PENDING"  # queued, not delivered
        assert work(app)["customer_messages"] == "delayed"
        sup = login_as(ops.supervisor)
        assert post(sup, f"/api/tickets/{ticket.id}/assisted-request",
                    {"reason": "Customer at the stand, no message"}).status_code == 200
        (offer,) = dispatch.dispatch_event(ops.event.id)
        task = work(app)["task"]
        assert task["id"] == offer.id and task["step"] == "offer"
        assert post(app, f"/api/valet/tasks/{offer.id}/accept").status_code == 200
        assert post(app, f"/api/valet/tasks/{offer.id}/ready").status_code == 200
        assert work(app)["task"]["step"] == "code"  # the code cannot reach the customer; the supervisor verifies
        assert post(sup, f"/api/tickets/{ticket.id}/assisted-handover",
                    {"method": "in_person_check", "reason": "WhatsApp down; registration card checked"}
                    ).status_code == 200
        assert Ticket.objects.get(pk=ticket.id).state == "DELIVERED"
        assert work(app)["task"] is None
    finally:
        SimulatorControl.set_outage(False)
    outbox.send_due(timezone.now() + timedelta(minutes=10))
    assert last(binding=binding, kind="guest.ready").status == "OBSOLETE"  # a code for a delivered car is never sent
    assert last(binding=binding, kind="guest.ticket").status == "OBSOLETE"


# --- dashboard -------------------------------------------------------------------------------------------

def test_dashboard_counts_and_request_to_ready_definition(ops):
    from ops.models import RetrievalRequest

    app, ticket = parked(ops)
    binding = ticket.bindings.get()
    retrieval.request_retrieval(binding, ticket)
    (offer,) = dispatch.dispatch_event(ops.event.id)
    assert post(app, f"/api/valet/tasks/{offer.id}/accept").status_code == 200
    assert post(app, f"/api/valet/tasks/{offer.id}/ready").status_code == 200
    ticket.refresh_from_db()  # the customer asked 150 seconds before the car was ready
    RetrievalRequest.objects.filter(ticket=ticket).update(requested_at=ticket.ready_at - timedelta(seconds=150))
    code = decrypt_text(CollectionCode.objects.get(ticket=ticket).delivery_enc)
    post(app, f"/api/valet/tasks/{offer.id}/code", {"code": code})
    post(app, f"/api/valet/tasks/{offer.id}/deliver")
    _app2, waiting = parked(ops, valet_index=1, phone="+966501234002", hook=8)
    retrieval.request_retrieval(waiting.bindings.get(), waiting, now=timezone.now() - timedelta(minutes=10))
    receiving = login_as(ops.valets[2])
    register(receiving, phone="+966501234003", vehicle="NEW 1")
    dispatch.raise_alerts(timezone.now())

    board = login_as(ops.admin).get("/api/dashboard").json()
    assert board["event"]["id"] == ops.event.id
    assert board["cars"] == {"receiving": 1, "parked": 1, "retrieving": 0, "ready": 0, "delivered": 1}
    assert board["waiting_requests"] == 1 and board["delayed_requests"] == 1
    assert board["delay_threshold_s"] == 240 and board["oldest_wait_s"] >= 600
    assert board["request_to_ready"] == {"count": 1, "median_s": 150, "p95_s": 150}
    assert board["problems"]["alerts"] >= 2 and board["problems"]["critical"] >= 1
    team = board["team"]
    assert (team["available"], team["busy"], team["unavailable"], team["not_started"]) == (2, 1, 0, 0)
    first = next(m for m in team["members"] if m["staff_id"] == ops.valets[0].id)
    assert (first["parked"], first["delivered"], first["task"]) == (1, 1, None)
    assert login_as(ops.supervisor).get("/api/dashboard").status_code == 403


def test_team_snapshot_shows_work_done_this_shift(ops):
    parked(ops)
    member = next(m for m in login_as(ops.supervisor).get(f"/api/events/{ops.event.id}/live").json()["team"]
                  if m["staff_id"] == ops.valets[0].id)
    assert member["done"] == 1 and member["assisted"] is False


def test_photo_upload_counts_towards_the_same_four(ops):
    app = login_as(ops.valets[0])
    ticket_id = register(app)
    assert photo(app, ticket_id).json() == {"count": 1, "required": 4}
