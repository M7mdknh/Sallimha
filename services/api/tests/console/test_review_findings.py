"""Review 2026-11-16: confirmed defects in the console layer, each pinned by a regression test."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from ops.models import Ticket
from tests.console.conftest import login_as
from tests.factories import open_shift
from tests.ops.intake_helpers import park


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


def test_reused_idempotency_key_with_different_body_is_refused_not_replayed(ops):
    """R1: a key reused for a different intended action must not silently return the earlier result."""
    sup = login_as(ops.supervisor)
    ticket = park(ops.valets[0], ops.event)
    key = uuid.uuid4().hex
    first = sup.post(f"/api/tickets/{ticket.id}/place-hold", {"reason": "Key check", "blocks_dispatch": True,
                                                              "blocks_handover": True},
                     format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert first.status_code == 200
    again = sup.post(f"/api/tickets/{ticket.id}/place-hold", {"reason": "Key check", "blocks_dispatch": True,
                                                              "blocks_handover": True},
                     format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert again.status_code == 200 and again.json() == first.json()  # same request: replayed
    changed = sup.post(f"/api/tickets/{ticket.id}/place-hold", {"reason": "Different hold", "blocks_dispatch": True,
                                                                "blocks_handover": False},
                       format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert changed.status_code == 409 and changed.json()["code"] == "idempotency_mismatch"
    assert Ticket.objects.get(pk=ticket.pk).holds.count() == 1


@pytest.mark.parametrize("path", ["/api/auth/login", "/api/auth/logout"])
def test_login_and_logout_require_csrf(world, path):
    """R2: DRF function views are CSRF-exempt for anonymous requests; login CSRF lets another site sign a
    browser into an attacker-chosen account, and logout CSRF forces sign-out."""
    get_user_model().objects.create_user(username="sup", password="correct horse battery 9")
    client = APIClient(enforce_csrf_checks=True)
    resp = client.post(path, {"username": "sup", "password": "correct horse battery 9"}, format="json")
    assert resp.status_code == 403


def test_second_admin_saving_stale_settings_is_refused_not_silently_overwritten(world):
    """R12: two admins editing settings — the later save based on an old read must not overwrite the earlier."""
    from ops.models import Role
    from tests.factories import make_staff

    first, second = login_as(make_staff(world.org, Role.ADMIN)), login_as(make_staff(world.org, Role.ADMIN))
    version = first.get("/api/config").json()["version"]
    assert second.get("/api/config").json()["version"] == version
    ok = second.post("/api/config/timings", {"timings": {"offer_window_s": 40}, "version": version}, format="json",
                     HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex)
    assert ok.status_code == 200
    stale = first.post("/api/config/timings", {"timings": {"offer_window_s": 50}, "version": version}, format="json",
                       HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex)
    assert stale.status_code == 409 and stale.json()["code"] == "stale_settings"
    after = first.get("/api/config").json()
    assert after["timings"]["offer_window_s"] == 40 and after["version"] == version + 1


def _queries(client, url):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as ctx:
        assert client.get(url).status_code == 200
    return len(ctx.captured_queries)


def test_venue_and_carryover_lists_do_not_query_per_row(ops):
    """R14: query counts stay flat as rows grow (they used to add a query per venue / per carryover case)."""
    from ops.models import KeyStation, Venue
    from ops.services import carryover

    mgr = login_as(ops.manager)
    first = park(ops.valets[0], ops.event, hook=11)
    carryover.propose_unclaimed(ops.supervisor, first, custodian="Security", plan="Overnight")
    one_venue, one_case = _queries(mgr, "/api/venues"), _queries(mgr, "/api/carryover")
    for i in range(3):
        venue = Venue.objects.create(org=ops.org, name=f"Extra {i}")
        KeyStation.objects.create(venue=venue, name="Board", hook_count=50)
        ticket = park(ops.valets[0], ops.event, hook=20 + i, phone=f"+96650100{i:04d}")
        carryover.propose_unclaimed(ops.supervisor, ticket, custodian="Security", plan="Overnight")
    assert _queries(mgr, "/api/venues") == one_venue
    assert _queries(mgr, "/api/carryover") == one_case
