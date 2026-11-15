"""Phase 2 console endpoints: server-side role matrix (AT-20, AT-59), contract shapes and audited actions."""

import uuid

import pytest

from ops.models import Incident, Role, Ticket
from tests.console.conftest import login_as
from tests.factories import make_staff, open_shift
from tests.ops.intake_helpers import park


def post(client, url, data=None):
    return client.post(url, data or {}, format="json", HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex)


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    world.admin = make_staff(world.org, Role.ADMIN)
    world.root = make_staff(world.org, Role.SUPER_ADMIN)
    return world


def test_incident_lifecycle_role_matrix(ops):
    ticket = park(ops.valets[0], ops.event)
    sup, mgr = login_as(ops.supervisor), login_as(ops.manager)
    resp = post(sup, f"/api/tickets/{ticket.id}/open-incident", {"category": "damage", "description": "Scratch"})
    assert resp.status_code == 200
    incident_id = resp.json()["id"]
    assert post(sup, f"/api/incidents/{incident_id}/notes", {"text": "Asked for photos"}).status_code == 200
    assert post(sup, f"/api/incidents/{incident_id}/resolve", {"outcome": "x"}).status_code == 403
    assert post(mgr, f"/api/incidents/{incident_id}/resolve", {"outcome": "Pre-existing"}).status_code == 200
    listing = sup.get(f"/api/events/{ops.event.id}/incidents").json()
    assert listing[0]["status"] == "RESOLVED"
    detail = sup.get(f"/api/incidents/{incident_id}").json()
    assert detail["notes"][0]["text"] == "Asked for photos" and detail["resolution"] == "Pre-existing"
    assert Incident.objects.get(pk=incident_id).resolved_by == ops.manager


def test_hold_relocation_and_unclaimed_actions(ops):
    ticket = park(ops.valets[0], ops.event, hook=33)
    sup, mgr = login_as(ops.supervisor), login_as(ops.manager)
    hold = post(sup, f"/api/tickets/{ticket.id}/place-hold",
                {"reason": "Key check", "blocks_dispatch": True, "blocks_handover": True})
    assert hold.status_code == 200
    assert post(sup, f"/api/tickets/{ticket.id}/clear-hold", {"hold_id": hold.json()["id"],
                                                              "reason": "Key found"}).status_code == 200
    start = post(sup, f"/api/tickets/{ticket.id}/relocate-start", {"to_staff_id": ops.valets[1].id,
                                                                   "reason": "Lane"})
    assert start.status_code == 200
    assert post(sup, f"/api/tickets/{ticket.id}/relocate-complete",
                {"zone_code": "B", "detail": "9", "hook_number": 34}).status_code == 200
    assert post(sup, f"/api/tickets/{ticket.id}/propose-unclaimed",
                {"custodian": "Security", "plan": "Overnight"}).status_code == 200
    assert post(sup, f"/api/tickets/{ticket.id}/approve-unclaimed").status_code == 403
    assert post(mgr, f"/api/tickets/{ticket.id}/approve-unclaimed").status_code == 200
    assert Ticket.objects.get(pk=ticket.pk).state == "UNCLAIMED"
    assert post(sup, f"/api/tickets/{ticket.id}/release-carryover",
                {"method": "collected_verified", "note": "x"}).status_code == 403
    assert post(mgr, f"/api/tickets/{ticket.id}/release-carryover",
                {"method": "collected_verified", "note": "Owner verified in person"}).status_code == 200
    register = mgr.get("/api/carryover").json()
    assert register == []


def test_directory_config_and_integrations_role_matrix(ops):
    sup, mgr, adm, root = (login_as(ops.supervisor), login_as(ops.manager), login_as(ops.admin),
                           login_as(ops.root))
    assert sup.get("/api/staff").status_code == 403
    assert mgr.get("/api/staff").status_code == 200
    created = post(mgr, "/api/staff", {"full_name": "New Valet", "phone": "+966551239999", "role": "VALET"})
    assert created.status_code == 200
    staff_id = created.json()["id"]
    assert post(mgr, f"/api/staff/{staff_id}/role", {"role": "MANAGER"}).status_code == 403
    assert post(mgr, f"/api/staff/{staff_id}/deactivate", {"reason": "Left"}).status_code == 200
    assert mgr.get("/api/config").status_code == 403
    assert adm.get("/api/config").status_code == 200
    assert post(adm, "/api/config/timings", {"timings": {"offer_window_s": 40}}).status_code == 200
    assert adm.get("/api/integrations/whatsapp").status_code == 403
    integration = root.get("/api/integrations/whatsapp").json()
    assert integration["status"] == "simulated" and "token" not in str(integration).lower().replace("_configured", "")
    mfa = post(adm, f"/api/staff/{ops.manager.id}/mfa")
    assert mfa.status_code == 200 and mfa.json()["otpauth_uri"].startswith("otpauth://")


def test_exports_and_reports(ops):
    park(ops.valets[0], ops.event, phone="+966501000099")
    sup, mgr, adm = login_as(ops.supervisor), login_as(ops.manager), login_as(ops.admin)
    assert sup.get(f"/api/events/{ops.event.id}/report").status_code == 403
    assert mgr.get(f"/api/events/{ops.event.id}/report").json()["outcomes"]["PARKED"] == 1
    tickets_csv = mgr.get(f"/api/events/{ops.event.id}/export/tickets.csv")
    body = b"".join(tickets_csv.streaming_content).decode() if tickets_csv.streaming else tickets_csv.content.decode()
    assert tickets_csv["Content-Type"].startswith("text/csv") and "966501000099" not in body
    assert mgr.get(f"/api/events/{ops.event.id}/export/guest-phones.csv").status_code == 403
    phones = adm.get(f"/api/events/{ops.event.id}/export/guest-phones.csv")
    assert phones.status_code == 200 and "+966501000099" in phones.content.decode()


def test_opening_check_and_dead_letters(ops):
    sup, adm = login_as(ops.supervisor), login_as(ops.admin)
    check = sup.get(f"/api/events/{ops.event.id}/opening-check").json()
    assert check["ok"] is False and "worker" in check["causes"]
    assert sup.get("/api/ops/dead-letters").status_code == 403
    assert adm.get("/api/ops/dead-letters").json() == []


def test_event_create_and_close(ops):
    mgr = login_as(ops.manager)
    venues = mgr.get("/api/venues").json()
    created = post(mgr, "/api/events", {"venue_id": venues[0]["id"], "name": "New night",
                                        "starts_at": "2026-11-20T18:00:00Z"})
    assert created.status_code == 200
    assert post(mgr, f"/api/events/{created.json()['id']}/close").status_code == 200
    assert post(login_as(ops.supervisor), "/api/events", {"venue_id": venues[0]["id"], "name": "x",
                                                          "starts_at": "2026-11-20T18:00:00Z"}).status_code == 403
