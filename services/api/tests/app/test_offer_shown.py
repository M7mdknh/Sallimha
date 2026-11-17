"""Reading My work changes nothing; the app acknowledges an offer when it is on screen (ADR-0012).

The acknowledgement starts the offer's response window once. Polling, refreshes and other tabs never restart or extend
it, and the hard limit from the reservation always applies."""

import uuid
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from ops.models import Task, Ticket
from ops.services import dispatch, retrieval
from tests.app.test_valet_api import park, post, register, work
from tests.console.conftest import login_as
from tests.factories import open_shift

WRITES = ("INSERT", "UPDATE", "DELETE")


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


def offered(ops, now=None):
    """The first valet parked a car and its customer asked for it: an offer is waiting on that valet's phone."""
    app = login_as(ops.valets[0])
    park(app, register(app))
    ticket = Ticket.objects.get()
    now = now or timezone.now()
    retrieval.request_retrieval(ticket.bindings.get(), ticket, now=now)
    (offer,) = dispatch.dispatch_event(ops.event.id, now=now)
    return app, offer


def shown(client, task_id, key=None):
    return client.post(f"/api/valet/tasks/{task_id}/shown", {}, format="json",
                       HTTP_IDEMPOTENCY_KEY=key or uuid.uuid4().hex)


def test_reading_my_work_never_writes_anything(ops):
    app, offer = offered(ops)
    with CaptureQueriesContext(connection) as queries:
        for _ in range(3):
            assert work(app)["task"]["step"] == "offer"
    writes = [q["sql"] for q in queries if q["sql"].lstrip().upper().startswith(WRITES)
              and "django_session" not in q["sql"]]
    assert writes == []
    offer.refresh_from_db()
    assert offer.offer_sent_at is None and offer.offer_deadline is None
    assert work(app)["task"]["shown"] is False


def test_the_acknowledgement_starts_the_window_once_and_nothing_moves_it(ops):
    app, offer = offered(ops)
    first = shown(app, offer.id)
    assert first.status_code == 200 and first.json()["outcome"] == "shown"
    offer.refresh_from_db()
    deadline = offer.offer_deadline
    assert deadline - offer.offer_sent_at == timedelta(seconds=30) and deadline <= offer.hard_deadline
    assert work(app)["task"]["shown"] is True
    assert work(app)["task"]["deadline"] == first.json()["deadline"]

    again = shown(app, offer.id)  # a refresh: new request, new key
    other_tab = shown(login_as(ops.valets[0]), offer.id)
    assert again.json() == other_tab.json() == {"outcome": "already_shown", "deadline": first.json()["deadline"]}
    later = offer.offer_sent_at + timedelta(seconds=20)
    assert dispatch.offer_seen(ops.valets[0], offer.id, later) == "already_shown"
    offer.refresh_from_db()
    assert offer.offer_deadline == deadline


def test_a_late_acknowledgement_never_goes_past_the_hard_limit(ops):
    start = timezone.now()
    _app, offer = offered(ops, now=start)
    assert dispatch.offer_seen(ops.valets[0], offer.id, start + timedelta(seconds=45)) == "shown"
    offer.refresh_from_db()
    assert offer.offer_deadline == offer.hard_deadline == start + timedelta(seconds=60)


def test_an_acknowledgement_after_the_hard_limit_changes_nothing(ops):
    start = timezone.now()
    _app, offer = offered(ops, now=start)
    assert dispatch.offer_seen(ops.valets[0], offer.id, start + timedelta(seconds=61)) == "stale"
    offer.refresh_from_db()
    assert offer.offer_sent_at is None and offer.offer_deadline is None
    assert dispatch.expire_offers(start + timedelta(seconds=61)) == 1


def test_an_offer_polled_but_never_acknowledged_still_lapses_at_the_hard_limit(ops):
    start = timezone.now()
    app, offer = offered(ops, now=start)
    for _ in range(5):
        work(app)
    assert dispatch.expire_offers(start + timedelta(seconds=45)) == 0
    assert dispatch.expire_offers(start + timedelta(seconds=61)) == 1
    assert Task.objects.get(pk=offer.id).status == "RELEASED"  # released for someone else, never accepted


def test_an_offer_can_be_accepted_before_its_acknowledgement_arrives(ops):
    app, offer = offered(ops)
    assert post(app, f"/api/valet/tasks/{offer.id}/accept").status_code == 200
    late = shown(app, offer.id)
    assert late.status_code == 409 and late.json()["code"] == "stale"
    assert Task.objects.get(pk=offer.id).status == "ACCEPTED"


def test_the_acknowledgement_is_the_valets_own_signed_csrf_protected_command(ops):
    _app, offer = offered(ops)
    csrf_client = APIClient(enforce_csrf_checks=True)
    login_as(ops.valets[0], csrf_client)
    assert shown(csrf_client, offer.id).status_code == 403  # no CSRF token
    assert shown(login_as(ops.valets[1]), offer.id).status_code == 404  # another valet's offer
    assert shown(APIClient(), offer.id).status_code == 403  # signed out
    assert shown(login_as(ops.supervisor), offer.id).status_code == 403  # console roles
    no_key = login_as(ops.valets[0]).post(f"/api/valet/tasks/{offer.id}/shown", {}, format="json")
    assert no_key.status_code == 428
    offer.refresh_from_db()
    assert offer.offer_sent_at is None
