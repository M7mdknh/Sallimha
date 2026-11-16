"""Outage workflow over HTTP (ADR-0008): role matrix, venue-local times and state-aware actions."""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from ops.models import OutageWindow, Reconciliation, Ticket
from ops.services import dispatch
from tests.console.conftest import login_as
from tests.factories import open_shift
from tests.ops.dispatch_helpers import parked_with_request
from tests.ops.intake_helpers import park

RIYADH = ZoneInfo("Asia/Riyadh")


def post(client, url, data=None):
    return client.post(url, data or {}, format="json", HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex)


def local(dt):
    return dt.astimezone(RIYADH).strftime("%Y-%m-%dT%H:%M")


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


def test_declare_relay_and_end_whatsapp_outage(ops):
    sup = login_as(ops.supervisor)
    ticket, _req = parked_with_request(ops.valets[0], ops.event)
    (task,) = dispatch.dispatch_event(ops.event.id)
    assert "relay_accept" not in sup.get(f"/api/tickets/{ticket.id}").json()["allowed_actions"]
    assert post(sup, f"/api/tickets/{ticket.id}/relay-accept", {"confirmed_via": "radio"}).json()["code"] == \
        "no_active_outage"
    assert post(sup, "/api/outages/whatsapp/declare", {"reason": "Provider incident"}).status_code == 403
    assert post(sup, f"/api/events/{ops.event.id}/outages/report", {"reason": "No replies"}).status_code == 200
    assert post(login_as(ops.manager), "/api/outages/whatsapp/declare", {"reason": "Provider incident"}).status_code \
        == 200
    status = sup.get("/api/outages").json()
    assert status["whatsapp"]["declared_by"] == ops.manager.full_name
    assert sup.get(f"/api/events/{ops.event.id}/live").json()["outage"]["reason"] == "Provider incident"
    detail = sup.get(f"/api/tickets/{ticket.id}").json()
    assert "relay_accept" in detail["allowed_actions"] and detail["offered_to"] == task.assignee.full_name
    assert post(sup, f"/api/tickets/{ticket.id}/relay-accept", {"confirmed_via": "radio"}).status_code == 200
    assert "relay_ready" in sup.get(f"/api/tickets/{ticket.id}").json()["allowed_actions"]
    assert post(sup, f"/api/tickets/{ticket.id}/relay-ready", {"confirmed_via": "in_person"}).status_code == 200
    assert Ticket.objects.get(pk=ticket.pk).state == "READY"
    assert post(sup, "/api/outages/whatsapp/end", {"reason": "Recovered"}).status_code == 403
    assert post(login_as(ops.manager), "/api/outages/whatsapp/end", {"reason": "Recovered"}).status_code == 200
    assert sup.get("/api/outages").json()["whatsapp"] is None


def test_intake_on_behalf_over_http(ops):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from tests.ops.intake_helpers import JPEG

    sup = login_as(ops.supervisor)
    post(login_as(ops.manager), "/api/outages/whatsapp/declare", {"reason": "Provider incident"})
    people = sup.get(f"/api/events/{ops.event.id}/people").json()
    assert {p["role"] for p in people} >= {"VALET", "SUPERVISOR"}
    resp = post(sup, f"/api/events/{ops.event.id}/intake-on-behalf", {
        "valet_id": ops.valets[1].id, "guest_phone": "0501239876", "plate": "QRS 4455", "description": "",
        "reason": "WhatsApp down", "confirmed_via": "in_person"})
    assert resp.status_code == 200
    ticket_id = resp.json()["id"]
    assert Ticket.objects.get(pk=ticket_id).state == "RECEIVED"
    actions = sup.get(f"/api/tickets/{ticket_id}").json()["allowed_actions"]
    assert {"relay_intake_photo", "relay_parked"} <= set(actions)
    for _ in range(4):
        photo = sup.post(f"/api/tickets/{ticket_id}/relay-intake-photo",
                         {"photo": SimpleUploadedFile("car.jpg", JPEG, content_type="image/jpeg"),
                          "confirmed_via": "in_person"}, format="multipart", HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex)
        assert photo.status_code == 200, photo.content
    bad = sup.post(f"/api/tickets/{ticket_id}/relay-intake-photo",
                   {"photo": SimpleUploadedFile("x.jpg", b"not an image", content_type="image/jpeg"),
                    "confirmed_via": "in_person"}, format="multipart", HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex)
    assert bad.status_code == 409 and bad.json()["code"] == "media_content_mismatch"
    parked = post(sup, f"/api/tickets/{ticket_id}/relay-parked", {
        "valet_id": ops.valets[1].id, "zone_code": "B", "detail": "8", "hook_number": 88, "confirmed_via": "radio"})
    assert parked.status_code == 200
    assert Ticket.objects.get(pk=ticket_id).state == "PARKED"


def test_system_outage_and_reconciliation_use_venue_local_time(ops):
    mgr, sup = login_as(ops.manager), login_as(ops.supervisor)
    ticket = park(ops.valets[0], ops.event)
    Ticket.objects.filter(pk=ticket.pk).update(parked_at=timezone.now() - timedelta(hours=3))
    start, end = timezone.now() - timedelta(hours=2), timezone.now() - timedelta(minutes=30)
    window = {"started_at_local": local(start), "ended_at_local": local(end), "reason": "Hosting outage"}
    assert post(sup, f"/api/events/{ops.event.id}/outages/system", window).status_code == 403
    assert post(mgr, f"/api/events/{ops.event.id}/outages/system", window).status_code == 200
    recorded = OutageWindow.objects.get(kind="SYSTEM")
    expected = datetime.strptime(local(start), "%Y-%m-%dT%H:%M").replace(tzinfo=RIYADH)
    assert recorded.started_at == expected  # interpreted in the venue's zone (Asia/Riyadh), not the browser's
    assert "reconcile_handover" in mgr.get(f"/api/tickets/{ticket.id}").json()["allowed_actions"]
    assert "reconcile_handover" not in sup.get(f"/api/tickets/{ticket.id}").json()["allowed_actions"]
    body = {"occurred_at_local": local(start + timedelta(minutes=30)), "delivered_by_id": ops.valets[0].id,
            "verified_by_id": ops.supervisor.id, "method": "in_person_check",
            "evidence": "Offline log line 7", "reason": "Delivered during the outage"}
    assert post(sup, f"/api/tickets/{ticket.id}/reconcile-handover", body).status_code == 403
    assert post(mgr, f"/api/tickets/{ticket.id}/reconcile-handover", body).status_code == 200
    again = post(mgr, f"/api/tickets/{ticket.id}/reconcile-handover", body)
    assert again.status_code == 409 and again.json()["code"] == "already_delivered"
    outside = dict(body, occurred_at_local=local(end + timedelta(minutes=5)))
    other = park(ops.valets[0], ops.event, phone="+966501112299")
    assert post(mgr, f"/api/tickets/{other.id}/reconcile-handover", outside).json()["code"] == \
        "outside_outage_window"
    assert Reconciliation.objects.count() == 1


def test_oversize_relayed_photo_is_refused_before_it_is_read(ops, settings, monkeypatch):
    """Security Guidance on ec2b0ad (MEDIUM): the size cap must apply before the upload is read into memory."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from tests.ops.intake_helpers import JPEG

    settings.MEDIA_MAX_BYTES = 1024
    sup = login_as(ops.supervisor)
    post(login_as(ops.manager), "/api/outages/whatsapp/declare", {"reason": "Provider incident"})
    ticket_id = post(sup, f"/api/events/{ops.event.id}/intake-on-behalf", {
        "valet_id": ops.valets[1].id, "guest_phone": "0501239876", "plate": "QRS 4455", "description": "",
        "reason": "WhatsApp down", "confirmed_via": "in_person"}).json()["id"]
    from ops.services import outage

    handed_over = []
    monkeypatch.setattr(outage, "relay_intake_photo", lambda *a, **k: handed_over.append(len(a[2])))
    big = SimpleUploadedFile("big.jpg", JPEG + b"0" * 4096, content_type="image/jpeg")
    resp = sup.post(f"/api/tickets/{ticket_id}/relay-intake-photo", {"photo": big, "confirmed_via": "in_person"},
                    format="multipart", HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex)
    assert resp.status_code == 409 and resp.json()["code"] == "media_too_large"
    assert handed_over == []  # refused on its declared size, never read and passed on
