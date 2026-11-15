"""AT-25 / AT-31 recovery with a real `run_worker` process killed and restarted (not an in-process call)."""

import os
import signal
import subprocess
import sys
import time
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from messaging import outbox
from messaging.models import MessageOutbox
from ops.models import Task
from ops.services import dispatch
from tests.factories import assign, make_event, make_staff, open_shift
from tests.ops.dispatch_helpers import parked_with_request

pytestmark = pytest.mark.django_db(transaction=True)


def _start_worker(worker_id: str) -> subprocess.Popen:
    db = connection.settings_dict
    env = {**os.environ, "DATABASE_URL": f"postgres://{db['USER']}:{db['PASSWORD']}@{db['HOST']}:{db['PORT']}/{db['NAME']}",
           "SALLIMHA_ENV": "test", "WHATSAPP_TRANSPORT": "fake"}
    return subprocess.Popen([sys.executable, "manage.py", "run_worker", "--poll", "0.2", "--id", worker_id],
                            env=env, cwd=os.getcwd(), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def _wait_for(predicate, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.2)
    return False


def test_killed_worker_recovers_work_from_stored_state():
    from ops.models import Role
    event = make_event()
    sup = make_staff(event.org, Role.SUPERVISOR)
    valets = [make_staff(event.org) for _ in range(2)]
    assign(event, sup, *valets)
    for v in valets:
        open_shift(event, v, sup)

    worker = _start_worker("recovery-1")
    try:
        first = outbox.enqueue("valet.available_ok", staff=valets[0], template="valet.available_ok", params={},
                               dedupe_key="recovery-first")
        assert _wait_for(lambda: MessageOutbox.objects.get(pk=first.pk).status == "SENT"), "live worker did not send"
    finally:
        worker.send_signal(signal.SIGKILL)  # crash: no graceful shutdown
        worker.wait(timeout=10)

    # While the worker is down: a business commit queues a message, and an offer's deadline passes.
    ticket, req = parked_with_request(valets[0], event)
    (task,) = dispatch.dispatch_event(event.id)
    Task.objects.filter(pk=task.pk).update(offer_sent_at=timezone.now() - timedelta(seconds=90),
                                           offer_deadline=timezone.now() - timedelta(seconds=60))
    queued = outbox.enqueue("valet.available_ok", staff=valets[1], template="valet.available_ok", params={},
                            dedupe_key="recovery-while-down")

    worker = _start_worker("recovery-2")
    try:
        assert _wait_for(lambda: MessageOutbox.objects.get(pk=queued.pk).status == "SENT"), "restart lost outbox work"
        assert _wait_for(lambda: Task.objects.get(pk=task.pk).status == "RELEASED"), "restart lost the deadline"
        req.refresh_from_db()
        assert req.requested_at <= timezone.now()  # original age preserved through requeue
        from core.models import WorkerHeartbeat
        assert _wait_for(lambda: WorkerHeartbeat.objects.filter(worker_id="recovery-2").exists())
    finally:
        worker.send_signal(signal.SIGTERM)  # graceful stop
        assert worker.wait(timeout=10) == 0
