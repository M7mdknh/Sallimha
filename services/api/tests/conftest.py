import pytest

from ops.models import Role
from tests.factories import assign, make_event, make_staff


@pytest.fixture
def world(db):
    """One event with a manager, an assigned supervisor and three valets."""
    event = make_event()
    org = event.org
    manager = make_staff(org, Role.MANAGER, name="Manager")
    supervisor = make_staff(org, Role.SUPERVISOR, name="Supervisor")
    valets = [make_staff(org, Role.VALET, name=f"Valet {i}") for i in range(1, 4)]
    assign(event, supervisor, *valets)
    return type("World", (), {"event": event, "org": org, "manager": manager, "supervisor": supervisor,
                              "valets": valets})
