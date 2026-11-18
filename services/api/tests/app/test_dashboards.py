"""Data behind the supervisor queue and the admin dashboard (ADR-0013): real timestamps only, nothing invented."""

from datetime import timedelta

import pytest
from django.utils import timezone

from ops.models import RetrievalRequest, Ticket
from ops.services import retrieval
from tests.app.test_intake_entry import intake
from tests.app.test_valet_api import park
from tests.console.conftest import login_as
from tests.factories import open_shift


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


def test_queue_rows_carry_plate_description_valet_and_the_wait_limits(ops):
    app = login_as(ops.valets[0])
    ticket_id = intake(app).json()["id"]
    park(app, ticket_id)
    ticket = Ticket.objects.get(pk=ticket_id)
    retrieval.request_retrieval(ticket.bindings.get(), ticket)
    live = login_as(ops.supervisor).get(f"/api/events/{ops.event.id}/live").json()
    (row,) = live["requests"]
    assert (row["plate"], row["description"]) == ("ا ب ح 1234", "كامري بيضاء")
    assert live["wait_warning_s"] > 0 and live["wait_critical_s"] > live["wait_warning_s"]


def test_activity_is_counted_per_hour_from_real_times(ops):
    app = login_as(ops.valets[0])
    ticket_id = intake(app).json()["id"]
    park(app, ticket_id)
    ticket = Ticket.objects.get(pk=ticket_id)
    two_hours_ago = timezone.now() - timedelta(hours=2)
    Ticket.objects.filter(pk=ticket_id).update(created_at=two_hours_ago)
    retrieval.request_retrieval(ticket.bindings.get(), ticket)
    board = login_as(ops.admin).get("/api/dashboard", {"event": ops.event.id}).json()
    hours = board["activity"]
    assert len(hours) == 3  # from the first hour with activity to the current hour, gaps included
    assert sum(h["received"] for h in hours) == 1 and sum(h["requested"] for h in hours) == 1
    assert hours[0]["received"] == 1 and hours[1] == {**hours[1], "received": 0, "requested": 0, "delivered": 0}
    assert RetrievalRequest.objects.count() == 1


def test_no_activity_gives_an_empty_series_not_zeros(ops):
    board = login_as(ops.admin).get("/api/dashboard", {"event": ops.event.id}).json()
    assert board["activity"] == []
    assert board["event"]["period"]["start"] is not None
