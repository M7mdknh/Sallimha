"""AT-31: database failure never produces a false success."""

import uuid

from django.db import OperationalError

from tests.console.conftest import login_as
from tests.factories import open_shift
from tests.ops.intake_helpers import register_and_confirm


def test_db_failure_no_false_success(world, monkeypatch):
    open_shift(world.event, world.valets[0], world.supervisor)
    ticket = register_and_confirm(world.valets[0], world.event, "+966509990000")
    client = login_as(world.supervisor)
    from ops.services import intake

    def down(*args, **kwargs):
        raise OperationalError("connection lost")

    monkeypatch.setattr(intake, "cancel_ticket", down)
    key = uuid.uuid4().hex
    resp = client.post(f"/api/tickets/{ticket.id}/cancel", {"reason": "x", "guest_has_vehicle_and_keys": True},
                       format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert resp.status_code == 503 and resp.json() == {"code": "service_unavailable"}
    monkeypatch.undo()
    retry = client.post(f"/api/tickets/{ticket.id}/cancel", {"reason": "x", "guest_has_vehicle_and_keys": True},
                        format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert retry.status_code == 200 and retry.json()["state"] == "CANCELLED"
