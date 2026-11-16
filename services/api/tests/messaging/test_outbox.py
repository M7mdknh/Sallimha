from datetime import timedelta

import pytest
from django.utils import timezone

from messaging import outbox
from messaging.models import MessageOutbox, SimulatedMessage, SimulatorControl
from messaging.status import apply_status
from tests.factories import make_staff


@pytest.fixture
def valet(world):
    return world.valets[0]


def _enqueue(valet, key="k1"):
    return outbox.enqueue("valet.available_ok", staff=valet, template="valet.available_ok", params={}, dedupe_key=key)


def test_enqueue_is_deduplicated(valet):
    a = _enqueue(valet)
    b = _enqueue(valet)
    assert a.pk == b.pk


def test_outbox_sent_after_restart(valet):
    """AT-25: a row committed by business code is sent by a fresh worker pass."""
    row = _enqueue(valet)
    assert row.status == MessageOutbox.Status.PENDING
    sent = outbox.send_due(timezone.now())
    row.refresh_from_db()
    assert sent == 1 and row.status == MessageOutbox.Status.SENT and row.provider_message_id
    assert SimulatedMessage.objects.filter(direction="out", provider_message_id=row.provider_message_id).exists()


def test_lost_response_marks_delivery_unknown(valet):
    """AT-26: provider may have accepted; never claim delivery, never blindly resend."""
    SimulatorControl.set_next("unknown")
    row = _enqueue(valet)
    outbox.send_due(timezone.now())
    row.refresh_from_db()
    assert row.status == MessageOutbox.Status.DELIVERY_UNKNOWN
    assert outbox.send_due(timezone.now() + timedelta(minutes=5)) == 0


def test_crashed_send_lease_becomes_delivery_unknown(valet):
    row = _enqueue(valet)
    MessageOutbox.objects.filter(pk=row.pk).update(status="SENDING", lease_until=timezone.now() - timedelta(seconds=1))
    outbox.recover_expired_leases(timezone.now())
    row.refresh_from_db()
    assert row.status == MessageOutbox.Status.DELIVERY_UNKNOWN


def test_transient_failure_retries_with_backoff(valet):
    SimulatorControl.set_next("transient")
    row = _enqueue(valet)
    now = timezone.now()
    outbox.send_due(now)
    row.refresh_from_db()
    assert row.status == MessageOutbox.Status.PENDING and row.next_attempt_at > now
    assert outbox.send_due(row.next_attempt_at) == 1


def test_permanent_failure_goes_dead_and_replay_is_once(valet):
    """AT-51."""
    SimulatorControl.set_next("permanent")
    row = _enqueue(valet)
    outbox.send_due(timezone.now())
    row.refresh_from_db()
    assert row.status == MessageOutbox.Status.DEAD
    outbox.replay(row.pk)
    outbox.replay(row.pk)
    outbox.send_due(timezone.now())
    assert SimulatedMessage.objects.filter(direction="out", outbox_id=row.pk).count() == 1


def test_status_out_of_order_no_regression(valet):
    """AT-27."""
    row = _enqueue(valet)
    outbox.send_due(timezone.now())
    row.refresh_from_db()
    pid = row.provider_message_id
    apply_status(pid, "read", 200)
    apply_status(pid, "delivered", 150)
    apply_status(pid, "sent", 100)
    row.refresh_from_db()
    assert row.status == MessageOutbox.Status.READ
    assert row.status_events.count() == 3


def test_failed_status_after_read_is_recorded_not_applied(valet):
    row = _enqueue(valet)
    outbox.send_due(timezone.now())
    row.refresh_from_db()
    apply_status(row.provider_message_id, "read", 200)
    apply_status(row.provider_message_id, "failed", 300)
    row.refresh_from_db()
    assert row.status == MessageOutbox.Status.READ
    assert row.status_events.filter(status="failed").exists()


def test_window_selects_template_when_closed(world):
    """AT-28: no inbound within 24 h → approved template path."""
    fresh = make_staff(world.org)
    row = outbox.enqueue("valet.available_ok", staff=fresh, template="valet.available_ok", params={}, dedupe_key="w1")
    assert outbox.choose_mode(row, timezone.now()) == "template"
    outbox.note_inbound(staff=fresh, at=timezone.now() - timedelta(hours=1))
    assert outbox.choose_mode(row, timezone.now()) == "session"
    assert outbox.choose_mode(row, timezone.now() + timedelta(hours=24)) == "template"


def test_transient_failures_keep_a_message_queued_through_a_long_outage(valet, settings):
    """ADR-0010: an outage longer than a few retries must not drop messages; they wait (capped backoff) for the
    retry window, then become dead letters."""
    from datetime import timedelta

    SimulatorControl.set_outage(True)
    row = _enqueue(valet)
    now = timezone.now()
    for _ in range(30):  # 30 minutes of failures
        now += timedelta(minutes=1)
        outbox.send_due(now)
    row.refresh_from_db()
    assert row.status == MessageOutbox.Status.PENDING and row.attempts > 6
    assert row.next_attempt_at - now <= timedelta(minutes=5)
    SimulatorControl.set_outage(False)
    outbox.send_due(row.next_attempt_at)
    row.refresh_from_db()
    assert row.status == MessageOutbox.Status.SENT
    settings.OUTBOX_TRANSIENT_RETRY_WINDOW_S = 60
    SimulatorControl.set_outage(True)
    stale = _enqueue(valet, key="window-ends")
    outbox.send_due(timezone.now() + timedelta(minutes=10))
    stale.refresh_from_db()
    assert stale.status == MessageOutbox.Status.DEAD and stale.failure_class == "exhausted"
