import uuid

import pytest
from django.urls import get_resolver
from rest_framework.test import APIClient

from core.models import AuditEvent
from ops.models import Role, Ticket
from tests.console.conftest import login_as
from tests.factories import make_event, make_staff, open_shift
from tests.ops.dispatch_helpers import parked_with_request
from tests.ops.intake_helpers import register_and_confirm


def post(client, url, data=None, key=None):
    return client.post(url, data or {}, format="json", HTTP_IDEMPOTENCY_KEY=key or uuid.uuid4().hex)


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


def test_unauthenticated_is_rejected(db):
    assert APIClient().get("/api/events/").status_code in (401, 403)


def test_valet_has_no_console_access(world):
    """AT-59."""
    client = login_as(world.valets[0])
    assert client.get("/api/events/").status_code == 403


def test_no_manual_dispatch_endpoint(world):
    """AT-59: supervisors monitor and handle exceptions; no routine-dispatch control exists."""
    patterns = " ".join(str(p.pattern) for p in get_resolver().url_patterns)
    from console import urls
    routes = " ".join(str(p.pattern) for p in urls.urlpatterns)
    assert "assign" not in routes and "dispatch" not in routes and "assign" not in patterns


def test_supervisor_lists_only_assigned_events(world, as_supervisor):
    other = make_event(venue=world.event.venue, name="Not assigned")
    names = [e["name"] for e in as_supervisor.get("/api/events/").json()]
    assert world.event.name in names and other.name not in names


def test_cross_event_ticket_denied(ops, as_supervisor):
    """AT-21."""
    other = make_event(venue=ops.event.venue, name="Other")
    v = make_staff(ops.org)
    open_shift(other, v, ops.manager)
    ticket = register_and_confirm(v, other, "+966503333333")
    assert as_supervisor.get(f"/api/tickets/{ticket.id}").status_code == 404
    resp = post(as_supervisor, f"/api/tickets/{ticket.id}/cancel", {"reason": "x", "guest_has_vehicle_and_keys": True})
    assert resp.status_code == 404
    assert Ticket.objects.get(pk=ticket.pk).state == "RECEIVED"


def test_live_view_scoped_and_ordered(ops, as_supervisor):
    from datetime import timedelta

    from django.utils import timezone
    _, older = parked_with_request(ops.valets[0], ops.event, requested_at=timezone.now() - timedelta(minutes=5))
    _, newer = parked_with_request(ops.valets[1], ops.event)
    body = as_supervisor.get(f"/api/events/{ops.event.id}/live").json()
    ids = [r["request_id"] for r in body["requests"]]
    assert ids.index(older.id) < ids.index(newer.id)
    assert body["requests"][0]["elapsed_s"] >= 299
    assert {"generated_at", "attention", "counts", "team", "health"} <= set(body)
    assert "phone" not in str(body["requests"])


def test_post_requires_idempotency_key(ops, as_supervisor):
    ticket = register_and_confirm(ops.valets[0], ops.event, "+966504444444")
    resp = as_supervisor.post(f"/api/tickets/{ticket.id}/cancel", {"reason": "x", "guest_has_vehicle_and_keys": True},
                              format="json")
    assert resp.status_code == 428


def test_repeat_submit_same_key_single_effect(ops, as_supervisor):
    """AT-34."""
    ticket = register_and_confirm(ops.valets[0], ops.event, "+966505555555")
    data = {"reason": "guest left", "guest_has_vehicle_and_keys": True}
    first = post(as_supervisor, f"/api/tickets/{ticket.id}/cancel", data, key="same-key")
    second = post(as_supervisor, f"/api/tickets/{ticket.id}/cancel", data, key="same-key")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert AuditEvent.objects.filter(action="ticket.cancel", entity_id=ticket.id).count() == 1


def test_domain_refusal_is_409_with_code(ops, as_supervisor):
    ticket = register_and_confirm(ops.valets[0], ops.event, "+966506666666")
    resp = post(as_supervisor, f"/api/tickets/{ticket.id}/cancel", {"reason": "x",
                                                                   "guest_has_vehicle_and_keys": False})
    assert resp.status_code == 409 and resp.json()["code"] == "confirmation_required"


def test_supervisor_shift_operations(world, as_supervisor):
    v = world.valets[2]
    resp = post(as_supervisor, f"/api/events/{world.event.id}/shifts", {"staff_id": v.id})
    assert resp.status_code == 200
    shift_id = resp.json()["id"]
    assert post(as_supervisor, f"/api/shifts/{shift_id}/end").status_code == 200


def test_withdraw_and_custody_endpoints(ops, as_supervisor):
    ticket, req = parked_with_request(ops.valets[0], ops.event)
    resp = post(as_supervisor, f"/api/tickets/{ticket.id}/withdraw", {"reason": "guest waiting"})
    assert resp.status_code == 200 and resp.json()["state"] == "WITHDRAWN"


def test_csrf_enforced_for_session_posts(ops):
    client = APIClient(enforce_csrf_checks=True)
    login_as(ops.supervisor, client)
    ticket = register_and_confirm(ops.valets[0], ops.event, "+966507070707")
    resp = client.post(f"/api/tickets/{ticket.id}/cancel", {"reason": "x", "guest_has_vehicle_and_keys": True},
                       format="json", HTTP_IDEMPOTENCY_KEY="k1")
    assert resp.status_code == 403


def test_manager_sees_all_org_events(world, as_manager):
    other = make_event(venue=world.event.venue, name="Manager visible")
    names = [e["name"] for e in as_manager.get("/api/events/").json()]
    assert other.name in names


def test_login_and_me(world, db):
    from django.contrib.auth import get_user_model
    user = get_user_model().objects.create_user(username="sup", password="correct horse battery 9")
    world.supervisor.user = user
    world.supervisor.save()
    client = APIClient()
    assert client.post("/api/auth/login", {"username": "sup", "password": "wrong"}, format="json").status_code == 400
    assert client.post("/api/auth/login", {"username": "sup", "password": "correct horse battery 9"},
                       format="json").status_code == 200
    me = client.get("/api/auth/me").json()
    assert me["role"] == Role.SUPERVISOR and me["name"] == world.supervisor.full_name


def test_media_streams_only_within_scope(ops, as_supervisor):
    """AT-21 for media: private evidence, scope-checked, not cached."""
    from ops.models import Media
    from tests.ops.intake_helpers import JPEG, through_photos
    ticket = register_and_confirm(ops.valets[0], ops.event, "+966508080808")
    through_photos(ops.valets[0], ticket)
    media = Media.objects.filter(ticket=ticket).first()
    resp = as_supervisor.get(f"/api/media/{media.id}")
    assert resp.status_code == 200 and b"".join(resp.streaming_content) == JPEG
    assert "no-store" in resp["Cache-Control"]
    other_sup = make_staff(ops.org, Role.SUPERVISOR)
    assert login_as(other_sup).get(f"/api/media/{media.id}").status_code == 404
