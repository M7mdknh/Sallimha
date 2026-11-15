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
