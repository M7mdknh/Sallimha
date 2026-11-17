import pytest
from django.core.management import call_command
from django.utils import timezone

from core import worker
from core.models import WorkerHeartbeat
from messaging import outbox
from messaging.models import MessageOutbox, WebhookInbox
from messaging.simulator import build_message_payload, build_status_payload, post_inbound


@pytest.mark.whatsapp_staff
def test_run_once_applies_status_inbox_and_beats(world):
    row = outbox.enqueue("valet.available_ok", staff=world.valets[0], template="valet.available_ok", params={},
                         dedupe_key="w-1")
    worker.run_once(worker_id="t1")
    row.refresh_from_db()
    assert row.status == MessageOutbox.Status.SENT
    post_inbound(build_status_payload(row.provider_message_id, "delivered", 1750000001))
    worker.run_once(worker_id="t1")
    row.refresh_from_db()
    assert row.status == MessageOutbox.Status.DELIVERED
    assert WebhookInbox.objects.filter(status="PROCESSED").count() == 1
    assert WorkerHeartbeat.objects.get(worker_id="t1").beat_at <= timezone.now()


def test_inbox_handler_failure_retries_then_dead(world, monkeypatch):
    from messaging import inbound

    def boom(inb):
        raise RuntimeError("handler bug")

    monkeypatch.setattr(inbound, "handle_message", boom)
    post_inbound(build_message_payload(from_phone="+966501234567", text="x"))
    row = WebhookInbox.objects.get()
    for hour in range(1, inbound.MAX_ATTEMPTS + 1):
        inbound.process_inbox(timezone.now() + timezone.timedelta(hours=hour))
    row.refresh_from_db()
    assert row.status == WebhookInbox.Status.DEAD and row.attempts == inbound.MAX_ATTEMPTS


def test_inbox_processes_in_arrival_order(world, monkeypatch):
    from messaging import inbound

    seen = []
    monkeypatch.setattr(inbound, "handle_message", lambda inb: seen.append(inb.text))
    for text in ("first", "second", "third"):
        post_inbound(build_message_payload(from_phone="+966501234567", text=text))
    inbound.process_inbox(timezone.now())
    assert seen == ["first", "second", "third"]


@pytest.mark.django_db
def test_run_worker_command_once():
    call_command("run_worker", "--once", "--id", "cmd-test")
    assert WorkerHeartbeat.objects.filter(worker_id="cmd-test").exists()
