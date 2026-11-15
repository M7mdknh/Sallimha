"""Races proven with real concurrent PostgreSQL transactions (docs/06: an in-memory DB cannot prove this)."""

import threading
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from core.errors import DomainError
from ops.models import LIVE_TASK_STATUSES, Task
from ops.services import dispatch, intake
from tests.factories import assign, make_event, make_staff, open_shift
from tests.ops.dispatch_helpers import make_busy, parked_with_request

pytestmark = pytest.mark.django_db(transaction=True)


def _race(*fns):
    barrier = threading.Barrier(len(fns))
    results, errors = [None] * len(fns), [None] * len(fns)

    def run(i, fn):
        try:
            barrier.wait()
            results[i] = fn()
        except Exception as exc:  # noqa: BLE001
            errors[i] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(i, fn)) for i, fn in enumerate(fns)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results, errors


def _world():
    from ops.models import Role
    event = make_event()
    sup = make_staff(event.org, Role.SUPERVISOR)
    valets = [make_staff(event.org) for _ in range(3)]
    assign(event, sup, *valets)
    for v in valets:
        open_shift(event, v, sup)
    return event, sup, valets


def test_two_dispatchers_one_reservation():
    """AT-08."""
    event, sup, valets = _world()
    ticket, req = parked_with_request(valets[0], event)
    results, errors = _race(lambda: dispatch.dispatch_event(event.id), lambda: dispatch.dispatch_event(event.id))
    assert errors == [None, None]
    assert sum(len(r) for r in results) == 1
    assert Task.objects.filter(request=req, status__in=LIVE_TASK_STATUSES).count() == 1


def test_intake_vs_retrieval_capacity():
    """AT-09: intake and retrieval contend on the same staff capacity."""
    event, sup, valets = _world()
    a, b, c = valets
    ticket, req = parked_with_request(b, event)
    make_busy(b)
    make_busy(c)
    results, errors = _race(lambda: intake.register_vehicle(a), lambda: dispatch.dispatch_event(event.id))
    live = Task.objects.filter(assignee=a, status__in=LIVE_TASK_STATUSES).count()
    assert live == 1
    intake_won = errors[0] is None
    offer_won = bool(results[1])
    assert intake_won != offer_won
    if not intake_won:
        assert isinstance(errors[0], DomainError) and errors[0].code in {"busy", "not_available"}


def test_accept_races_expiry_single_winner():
    """AT-11."""
    event, sup, valets = _world()
    a = valets[0]
    ticket, req = parked_with_request(a, event)
    (task,) = dispatch.dispatch_event(event.id)
    deadline = timezone.now() + timedelta(milliseconds=50)
    Task.objects.filter(pk=task.pk).update(offer_sent_at=timezone.now(), offer_deadline=deadline)
    from messaging.models import MessageOutbox
    offer = MessageOutbox.objects.get(kind="valet.offer", task=task)
    payload = next(b[0] for b in offer.buttons if b[1] == "accept")
    results, errors = _race(lambda: dispatch.accept_task(a, payload, now=deadline),
                            lambda: dispatch.expire_offers(deadline + timedelta(milliseconds=1)))
    assert errors == [None, None]
    task.refresh_from_db()
    accepted = results[0] == "accepted"
    expired = results[1] == 1
    assert accepted != expired
    assert task.status == ("ACCEPTED" if accepted else "RELEASED")


def test_concurrent_request_taps_single_request():
    """AT-10 under real concurrency."""
    from ops.services import retrieval
    event, sup, valets = _world()
    ticket, req = parked_with_request(valets[0], event)
    from ops.models import RetrievalRequest
    RetrievalRequest.objects.all().delete()
    binding = ticket.bindings.get()
    results, errors = _race(*[lambda: retrieval.request_retrieval(binding, ticket) for _ in range(4)])
    assert errors == [None] * 4
    assert RetrievalRequest.objects.filter(ticket=ticket).count() == 1
    assert sum(1 for _, created in results if created) == 1
