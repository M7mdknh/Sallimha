import pytest
from django.test import override_settings

from messaging.models import SimulatedMessage
from ops.models import Ticket
from tests.console.conftest import login_as
from tests.factories import open_shift


@pytest.fixture
def sim(world):
    open_shift(world.event, world.valets[0], world.supervisor)
    return login_as(world.supervisor)


def test_simulator_send_text_runs_real_webhook_path(world, sim):
    phone = world.valets[0].phone_e164
    resp = sim.post("/api/dev/sim/send", {"phone": phone, "text": "مركبة جديدة"}, format="json")
    assert resp.status_code == 200
    from messaging import inbound
    inbound.process_inbox()
    assert Ticket.objects.count() == 1
    assert SimulatedMessage.objects.filter(direction="in", phone=phone).exists()


def test_simulator_lists_phones_and_messages(world, sim):
    phones = sim.get("/api/dev/sim/phones").json()
    assert any(p["phone"] == world.valets[0].phone_e164 and p["role"] == "VALET" for p in phones)
    assert sim.get("/api/dev/sim/messages", {"phone": world.valets[0].phone_e164}).status_code == 200


@override_settings(SIMULATOR_ENABLED=False)
def test_simulator_absent_when_disabled(world, sim):
    assert sim.post("/api/dev/sim/send", {"phone": "+966500000000", "text": "x"}, format="json").status_code == 404
    assert sim.get("/api/dev/sim/phones").status_code == 404


def test_seed_demo_creates_synthetic_world(db):
    from django.core.management import call_command

    from ops.models import Event, Staff
    call_command("seed_demo", "--reset")
    assert Event.objects.filter(name__contains="تجريبي").exists()
    assert Staff.objects.filter(role="VALET").count() >= 3
    assert Staff.objects.filter(user__username="supervisor").exists()
    # One synthetic account per console role, so the role matrix (AT-59) can be demonstrated end to end.
    assert set(Staff.objects.filter(user__isnull=False).values_list("role", flat=True)) == {
        "SUPERVISOR", "MANAGER", "ADMIN", "SUPER_ADMIN"}


def test_seed_demo_with_activity_builds_mid_event_state(db):
    from django.core.management import call_command

    from ops.models import Alert, RetrievalRequest, Ticket
    call_command("seed_demo", "--reset", "--with-activity")
    assert set(RetrievalRequest.objects.values_list("state", flat=True)) == {"OFFERED", "ACCEPTED"}
    assert Ticket.objects.filter(state="RECEIVED", contact_state="UNCONFIRMED").exists()
    assert {"guest_contact_unconfirmed", "wait_warning"} <= set(Alert.objects.values_list("kind", flat=True))


def test_simulated_outage_refuses_inbound_and_reports_degraded(as_supervisor, world):
    """ADR-0010: a simulated provider outage stops both directions until it is cleared."""
    assert as_supervisor.post("/api/dev/sim/outage", {"down": True}, format="json").json() == {"down": True}
    assert as_supervisor.get("/api/dev/sim/outage").json() == {"down": True}
    refused = as_supervisor.post("/api/dev/sim/send", {"phone": world.valets[0].phone_e164, "text": "مساعدة"},
                                 format="json")
    assert refused.status_code == 409 and refused.json()["code"] == "simulated_outage"
    assert as_supervisor.get(f"/api/events/{world.event.id}/live").json()["health"]["whatsapp"] == "degraded"
    assert as_supervisor.post("/api/dev/sim/outage", {"down": False}, format="json").json() == {"down": False}
