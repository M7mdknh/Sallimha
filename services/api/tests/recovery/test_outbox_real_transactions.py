"""Outbox behaviour with real autocommit transactions, as in the worker process (not wrapped by pytest)."""

import pytest
from django.utils import timezone

from messaging import outbox
from messaging.models import MessageOutbox, SimulatorControl

pytestmark = pytest.mark.django_db(transaction=True)


def _row():
    from ops.models import Role
    from tests.factories import make_org, make_staff
    staff = make_staff(make_org(), Role.VALET)
    return outbox.enqueue("valet.available_ok", staff=staff, template="valet.available_ok", params={},
                          dedupe_key="rt-1")


def test_send_due_outside_transaction_sends():
    row = _row()
    assert outbox.send_due(timezone.now()) == 1
    row.refresh_from_db()
    assert row.status == MessageOutbox.Status.SENT


def test_failure_injection_works_outside_transaction():
    SimulatorControl.set_next("transient")
    row = _row()
    outbox.send_due(timezone.now())
    row.refresh_from_db()
    assert row.status == MessageOutbox.Status.PENDING and row.attempts == 1


def test_unexpected_error_retries_row_instead_of_aborting_pass(monkeypatch):
    row = _row()
    from messaging import transport

    def broken(self, payload):
        raise RuntimeError("bug in transport")

    monkeypatch.setattr(transport.FakeTransport, "send", broken)
    outbox.send_due(timezone.now())
    row.refresh_from_db()
    assert row.status == MessageOutbox.Status.PENDING and "RuntimeError" in row.last_error
