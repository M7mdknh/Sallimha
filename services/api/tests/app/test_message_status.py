"""No receipt question (ADR-0013): the customer's ticket message is tracked from provider events, and a failure
becomes one supervisor issue with correct-the-number and resend. Every message here is SIMULATED."""

import pytest
from django.utils import timezone

from messaging import outbox, status
from messaging.models import MessageOutbox, SimulatorControl
from ops.models import Alert, Ticket
from tests.app.test_valet_api import photo, post, register, work
from tests.console.conftest import login_as
from tests.factories import open_shift


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


def ticket_row(ticket_id):
    return MessageOutbox.objects.filter(ticket_id=ticket_id, kind="guest.ticket").latest("id")


def detail(client, ticket_id):
    response = client.get(f"/api/tickets/{ticket_id}")
    assert response.status_code == 200, response.content
    return response.json()


def test_the_valet_goes_from_photos_to_parking_without_a_receipt_question(ops):
    app = login_as(ops.valets[0])
    ticket_id = register(app)
    for _ in range(4):
        assert photo(app, ticket_id).status_code == 200
    assert work(app)["task"]["step"] == "start_parking"
    assert post(app, f"/api/valet/tickets/{ticket_id}/start-parking").status_code == 200
    assert post(app, f"/api/valet/tickets/{ticket_id}/receipt", {"received": True}).status_code == 404  # gone
    assert Ticket.objects.get(pk=ticket_id).contact_state == "UNCONFIRMED"  # never set automatically


def test_message_status_follows_the_provider_never_ahead_of_it(ops):
    app = login_as(ops.valets[0])
    ticket_id = register(app)
    supervisor = login_as(ops.supervisor)
    assert work(app)["task"]["ticket"]["message"] == "queued"
    assert detail(supervisor, ticket_id)["guest_message"]["status"] == "queued"
    outbox.send_due(timezone.now())
    assert work(app)["task"]["ticket"]["message"] == "sent"  # accepted by the provider, not yet delivered
    row = ticket_row(ticket_id)
    status.apply_status(row.provider_message_id, "delivered", 1)
    assert work(app)["task"]["ticket"]["message"] == "delivered"
    status.apply_status(row.provider_message_id, "read", 2)
    assert detail(supervisor, ticket_id)["guest_message"]["status"] == "read"
    assert Ticket.objects.get(pk=ticket_id).contact_state == "UNCONFIRMED"


def test_a_failed_ticket_message_raises_one_issue_with_correct_and_resend(ops):
    app = login_as(ops.valets[0])
    ticket_id = register(app)
    outbox.send_due(timezone.now())
    row = ticket_row(ticket_id)
    status.apply_status(row.provider_message_id, "failed", 3, [{"title": "Not a WhatsApp user"}])
    status.apply_status(row.provider_message_id, "failed", 4, [{"title": "again"}])  # a repeated callback
    issues = Alert.objects.filter(kind="guest_message_failed", ticket_id=ticket_id)
    assert issues.count() == 1 and issues.get().acknowledged_at is None
    assert work(app)["task"]["ticket"]["message"] == "failed"
    supervisor = login_as(ops.supervisor)
    actions = detail(supervisor, ticket_id)["allowed_actions"]
    assert "resend_ticket" in actions and "correct_phone" in actions and "confirm_receipt" not in actions

    resent = post(supervisor, f"/api/tickets/{ticket_id}/resend-ticket")
    assert resent.status_code == 200, resent.content
    assert ticket_row(ticket_id).status == "PENDING" and ticket_row(ticket_id).id != row.id
    assert issues.get().acknowledged_at is not None  # the action answered the issue
    again = post(supervisor, f"/api/tickets/{ticket_id}/resend-ticket")
    assert again.status_code == 409 and again.json()["code"] == "message_not_failed"  # queued, not failed


def test_a_dead_letter_raises_the_same_single_issue(ops):
    app = login_as(ops.valets[0])
    ticket_id = register(app)
    SimulatorControl.set_next("permanent")
    outbox.send_due(timezone.now())
    assert ticket_row(ticket_id).status == "DEAD"
    assert Alert.objects.filter(kind="guest_message_failed", ticket_id=ticket_id).count() == 1
    assert work(app)["task"]["ticket"]["message"] == "failed"


def test_an_unknown_outcome_is_neither_sent_nor_failed(ops):
    app = login_as(ops.valets[0])
    ticket_id = register(app)
    SimulatorControl.set_next("unknown")
    outbox.send_due(timezone.now())
    assert work(app)["task"]["ticket"]["message"] == "unknown"
    assert not Alert.objects.filter(kind="guest_message_failed", ticket_id=ticket_id).exists()
    supervisor = login_as(ops.supervisor)
    # the supervisor decides, with the customer
    assert "resend_ticket" in detail(supervisor, ticket_id)["allowed_actions"]


def test_resend_is_for_supervisors_in_scope_only(ops):
    app = login_as(ops.valets[0])
    ticket_id = register(app)
    SimulatorControl.set_next("permanent")
    outbox.send_due(timezone.now())
    assert post(app, f"/api/tickets/{ticket_id}/resend-ticket").status_code == 403


def test_correcting_the_number_still_revokes_the_old_credentials(ops):
    app = login_as(ops.valets[0])
    ticket_id = register(app)
    supervisor = login_as(ops.supervisor)
    corrected = post(supervisor, f"/api/tickets/{ticket_id}/correct-phone",
                     {"phone": "07911 123456", "guest_region": "GB", "reason": "customer read it out again"})
    assert corrected.status_code == 200, corrected.content
    ticket = Ticket.objects.get(pk=ticket_id)
    assert ticket.bindings.filter(revoked_at__isnull=True).count() == 1
    assert ticket.bindings.filter(revoked_at__isnull=False, revoke_reason="phone_corrected").count() == 1
    # after a correction it still means something
    assert "confirm_receipt" in detail(supervisor, ticket_id)["allowed_actions"]



def test_a_message_that_fails_again_after_a_resend_raises_a_new_issue(ops):
    app = login_as(ops.valets[0])
    ticket_id = register(app)
    SimulatorControl.set_next("permanent")
    outbox.send_due(timezone.now())
    supervisor = login_as(ops.supervisor)
    assert post(supervisor, f"/api/tickets/{ticket_id}/resend-ticket").status_code == 200
    SimulatorControl.set_next("permanent")
    outbox.send_due(timezone.now())
    issues = Alert.objects.filter(kind="guest_message_failed", ticket_id=ticket_id)
    assert issues.count() == 2 and issues.filter(acknowledged_at__isnull=True).count() == 1

