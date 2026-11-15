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


def test_ticket_export_neutralises_spreadsheet_formulas(ops):
    ticket = park(ops.valets[0], ops.event)
    Ticket.objects.filter(pk=ticket.pk).update(vehicle_plate='=HYPERLINK("http://x","y")')
    body = login_as(ops.manager).get(f"/api/events/{ops.event.id}/export/tickets.csv").content.decode()
    assert "'=HYPERLINK" in body and ',=HYPERLINK' not in body


def test_event_create_rejects_another_orgs_venue_as_not_found(ops):
    from tests.factories import make_org, make_venue

    foreign = make_venue(make_org("Other Org"), name="Elsewhere")
    resp = post(login_as(ops.manager), "/api/events", {"venue_id": foreign.id, "name": "x",
                                                       "starts_at": "2026-11-20T18:00:00Z"})
    assert resp.status_code == 404


def test_admin_operations_round_trip(ops, settings):
    from django.utils import timezone

    from messaging import outbox
    from messaging.models import MessageOutbox, SimulatorControl

    adm, mgr = login_as(ops.admin), login_as(ops.manager)
    SimulatorControl.set_next("permanent")
    dead = outbox.enqueue("valet.available_ok", staff=ops.valets[0], template="valet.available_ok", params={},
                          dedupe_key="api-dead")
    outbox.send_due(timezone.now())
    listing = adm.get("/api/ops/dead-letters").json()
    assert [r["id"] for r in listing] == [dead.id] and listing[0]["recipient"] == ops.valets[0].full_name
    assert post(adm, f"/api/ops/dead-letters/{dead.id}/replay").json() == {"ok": True}
    assert MessageOutbox.objects.get(pk=dead.pk).status != MessageOutbox.Status.DEAD

    ticket = park(ops.valets[0], ops.event, hook=41)
    post(login_as(ops.supervisor), f"/api/tickets/{ticket.id}/propose-unclaimed",
         {"custodian": "Security", "plan": "Overnight"})
    post(mgr, f"/api/tickets/{ticket.id}/approve-unclaimed")
    [row] = mgr.get("/api/carryover").json()
    assert row["ticket_id"] == ticket.id and row["status"] == "APPROVED" and row["hook"] == 41
    assert row["event"] == ops.event.name and row["event_id"] == ops.event.id and row["location"].startswith("A")

    assert post(adm, "/api/config/retention", {"retention_days": {"guest_contact": 30}}).status_code == 200
    assert adm.get("/api/config").json()["retention_days"]["guest_contact"] == 30
    assert set(post(adm, "/api/retention/apply").json()) == {"guest_contact", "intake_photos", "incident_evidence"}

    copy = {"ar": "تم ركن مركبتك يا ضيفنا. تذكرتك {ticket}.", "en": "Parked. Ticket {ticket}."}
    assert post(adm, "/api/config/templates", {"overrides": {"guest.parked": copy}}).status_code == 200
    assert adm.get("/api/config").json()["template_overrides"] == {"guest.parked": copy}
    assert post(adm, "/api/config/templates", {"overrides": {"guest.parked": None}}).status_code == 200
    assert adm.get("/api/config").json()["template_overrides"] == {}

    leaver = make_staff(ops.org, Role.VALET)
    post(mgr, f"/api/staff/{leaver.id}/deactivate", {"reason": "Season ended"})
    assert post(mgr, f"/api/staff/{leaver.id}/reactivate").status_code == 200


def test_me_reports_simulator_availability(ops, settings):
    sup = login_as(ops.supervisor)
    assert sup.get("/api/auth/me").json()["simulator"] is True
    settings.SIMULATOR_ENABLED = False
    assert sup.get("/api/auth/me").json()["simulator"] is False


def test_ticket_finder_by_number_or_plate_is_event_scoped(ops):
    ticket = park(ops.valets[0], ops.event, hook=52)
    Ticket.objects.filter(pk=ticket.pk).update(vehicle_plate="XYZ 4821")
    sup = login_as(ops.supervisor)
    by_number = sup.get(f"/api/events/{ops.event.id}/tickets", {"q": f"#{ticket.display_number}"}).json()
    assert [r["id"] for r in by_number] == [ticket.id]
    assert by_number[0]["state"] == "PARKED" and by_number[0]["hook"] == 52
    assert [r["id"] for r in sup.get(f"/api/events/{ops.event.id}/tickets", {"q": "xyz"}).json()] == [ticket.id]
    # Digits also match the plate, since many plates are mostly numbers.
    assert [r["id"] for r in sup.get(f"/api/events/{ops.event.id}/tickets", {"q": "4821"}).json()] == [ticket.id]
    assert sup.get(f"/api/events/{ops.event.id}/tickets", {"q": ""}).json() == []
    # A long run of digits (e.g. part of a plate) is not a ticket number and must not overflow the query.
    long_digits = sup.get(f"/api/events/{ops.event.id}/tickets", {"q": "9" * 40})
    assert long_digits.status_code == 200 and long_digits.json() == []

    from tests.factories import make_event, make_org, make_venue

    foreign = make_event(make_venue(make_org("Other Org")))
    assert sup.get(f"/api/events/{foreign.id}/tickets", {"q": "1"}).status_code == 404


def test_unknown_outcome_sends_are_visible_and_resent_only_on_explicit_replay(ops):
    """docs/03: ambiguous sends are never resent automatically; the operator decides, once, audited."""
    from django.utils import timezone

    from core.models import AuditEvent
    from messaging import outbox
    from messaging.models import MessageOutbox, SimulatedMessage, SimulatorControl

    adm = login_as(ops.admin)
    SimulatorControl.set_next("unknown")
    row = outbox.enqueue("valet.available_ok", staff=ops.valets[0], template="valet.available_ok", params={},
                        dedupe_key="api-unknown")
    outbox.send_due(timezone.now())
    assert MessageOutbox.objects.get(pk=row.pk).status == MessageOutbox.Status.DELIVERY_UNKNOWN
    sent = SimulatedMessage.objects.filter(direction="out", outbox_id=row.pk)
    assert sent.count() == 1  # the simulated provider received it; only the response was lost
    outbox.send_due(timezone.now())
    assert sent.count() == 1  # the worker never resends it on its own

    [listed] = adm.get("/api/ops/dead-letters").json()
    assert listed["id"] == row.id and listed["status"] == "DELIVERY_UNKNOWN"
    assert post(adm, f"/api/ops/dead-letters/{row.id}/replay").json() == {"ok": True}
    # Re-queued: it no longer awaits an operator, so a second, separate replay finds nothing to do.
    assert post(adm, f"/api/ops/dead-letters/{row.id}/replay").status_code == 404
    outbox.send_due(timezone.now())
    assert sent.count() == 2  # resent once, by explicit operator decision (a duplicate is the known cost)
    assert AuditEvent.objects.filter(action="outbox.replay", entity_id=row.id).exists()
