import os

import pytest

from ops.models import Role
from tests.factories import assign, make_event, make_staff


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "whatsapp_staff: runs with the retired valet WhatsApp conversation (STAFF_CHANNEL=whatsapp)")


@pytest.fixture(autouse=True)
def staff_channel(request, settings):
    """Tests run as the pilot does — staff in the app (ADR-0011) — unless marked for the retired channel."""
    legacy = request.node.get_closest_marker("whatsapp_staff") or os.environ.get("SALLIMHA_TEST_ALL_LEGACY") == "1"
    settings.STAFF_CHANNEL = "whatsapp" if legacy else "app"


@pytest.fixture
def world(db):
    """One event with an admin, an assigned supervisor and three valets. `manager` is the admin: what a manager
    could do is now an admin's (ADR-0011)."""
    event = make_event()
    org = event.org
    admin = make_staff(org, Role.ADMIN, name="Admin")
    supervisor = make_staff(org, Role.SUPERVISOR, name="Supervisor")
    valets = [make_staff(org, Role.VALET, name=f"Valet {i}") for i in range(1, 4)]
    assign(event, supervisor, *valets)
    return type("World", (), {"event": event, "org": org, "admin": admin, "manager": admin,
                              "supervisor": supervisor, "valets": valets})
