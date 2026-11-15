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


def test_unexpected_transport_error_is_delivery_unknown_not_resent(monkeypatch):
    """The provider may have accepted the message before the error: never resend blindly."""
    row = _row()
    from messaging import transport

    def broken(self, payload):
        raise RuntimeError("bug in transport")

    monkeypatch.setattr(transport.FakeTransport, "send", broken)
    outbox.send_due(timezone.now())
    row.refresh_from_db()
    assert row.status == MessageOutbox.Status.DELIVERY_UNKNOWN and "RuntimeError" in row.last_error


def test_render_error_before_send_is_retried(monkeypatch):
    """Nothing reached the provider, so a retry cannot duplicate a message."""
    row = _row()
    monkeypatch.setattr(outbox, "render", lambda r, now: (_ for _ in ()).throw(RuntimeError("render bug")))
    outbox.send_due(timezone.now())
    row.refresh_from_db()
    assert row.status == MessageOutbox.Status.PENDING and "RuntimeError" in row.last_error


def test_cloud_transport_post_send_parse_failure_is_unknown(monkeypatch, settings):
    import io
    import urllib.request

    from messaging.transport import CloudApiTransport, OutboundPayload, UnknownSendOutcome
    settings.WHATSAPP_ACCESS_TOKEN = "t"
    settings.WHATSAPP_PHONE_NUMBER_ID = "1"

    class Reply(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Reply(b"not json"))
    payload = OutboundPayload(outbox_id=1, to_phone="+966501234567", mode="session", template="t", language="ar",
                              text="x")
    with pytest.raises(UnknownSendOutcome):
        CloudApiTransport().send(payload)
