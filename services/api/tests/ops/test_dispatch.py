from datetime import timedelta

import pytest
from django.utils import timezone

from messaging.models import MessageOutbox
from ops.models import Alert, AssignmentAttempt, RetrievalRequest, Task, Ticket
from ops.services import dispatch, tokens
from tests.factories import open_shift
from tests.ops.dispatch_helpers import make_busy, parked_with_request, set_idle


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


def _offer_of(req):
    req.refresh_from_db()
    return req.current_task


def test_original_parking_valet_gets_offer(ops):
    """AT-05."""
    a, b, c = ops.valets
    ticket, req = parked_with_request(a, ops.event)
    set_idle(b, 60)
    set_idle(c, 50)
    dispatch.dispatch_event(ops.event.id)
    assert _offer_of(req).assignee == a


def test_original_busy_other_free_offered_immediately(ops):
    """AT-06: longest-idle alternative, stable tie-break by staff id."""
    a, b, c = ops.valets
    ticket, req = parked_with_request(a, ops.event)
    make_busy(a)
    set_idle(b, 5)
    set_idle(c, 30)
    dispatch.dispatch_event(ops.event.id)
    assert _offer_of(req).assignee == c


def test_everyone_busy_queue_keeps_age(ops):
    """AT-07."""
    a = ops.valets[0]
    asked = timezone.now() - timedelta(minutes=3)
    ticket, req = parked_with_request(a, ops.event, requested_at=asked)
    for v in ops.valets:
        make_busy(v)
    assert dispatch.dispatch_event(ops.event.id) == []
    req.refresh_from_db()
    assert req.state == "QUEUED" and req.requested_at == asked


def test_fairness_beats_affinity(ops):
    """AT-32: a free valet cannot bypass an older eligible request because they parked a newer car."""
    a, b, c = ops.valets
    older_ticket, older = parked_with_request(b, ops.event, requested_at=timezone.now() - timedelta(minutes=5))
    newer_ticket, newer = parked_with_request(a, ops.event, requested_at=timezone.now())
    make_busy(b)
    make_busy(c)
    dispatch.dispatch_event(ops.event.id)
    assert _offer_of(older).assignee == a
    newer.refresh_from_db()
    assert newer.state == "QUEUED"


def test_offer_has_no_code_or_phone(ops):
    """AT-39."""
    ticket, req = parked_with_request(ops.valets[0], ops.event)
    dispatch.dispatch_event(ops.event.id)
    offer = MessageOutbox.objects.get(kind="valet.offer")
    flat = str(offer.params)
    assert set(offer.params) == {"ticket", "vehicle", "location", "hook", "expires"}
    assert "+966" not in flat and "code" not in flat
    assert [b[1] for b in offer.buttons] == ["accept", "decline"]


def _accept_payload(task):
    offer = MessageOutbox.objects.get(kind="valet.offer", task=task)
    return next(b[0] for b in offer.buttons if b[1] == "accept")


def test_accept_moves_ticket_to_retrieving(ops):
    ticket, req = parked_with_request(ops.valets[0], ops.event)
    (task,) = dispatch.dispatch_event(ops.event.id)
    assert dispatch.accept_task(ops.valets[0], _accept_payload(task)) == "accepted"
    ticket.refresh_from_db()
    req.refresh_from_db()
    assert ticket.state == Ticket.State.RETRIEVING and req.state == "ACCEPTED"
    assert MessageOutbox.objects.filter(kind="guest.accepted", ticket=ticket).exists()


def test_duplicate_accept_no_second_effect(ops):
    """AT-60."""
    ticket, req = parked_with_request(ops.valets[0], ops.event)
    (task,) = dispatch.dispatch_event(ops.event.id)
    payload = _accept_payload(task)
    assert dispatch.accept_task(ops.valets[0], payload) == "accepted"
    assert dispatch.accept_task(ops.valets[0], payload) == "duplicate"
    assert MessageOutbox.objects.filter(kind="guest.accepted", ticket=ticket).count() == 1


def test_timeout_requeues_preserves_age_cooldown_alert(ops):
    """AT-12."""
    a, b, c = ops.valets
    asked = timezone.now() - timedelta(minutes=1)
    ticket, req = parked_with_request(a, ops.event, requested_at=asked)
    make_busy(c)
    (first,) = dispatch.dispatch_event(ops.event.id)
    assert first.assignee == a
    later = timezone.now() + timedelta(seconds=61)
    assert dispatch.expire_offers(later) == 1
    req.refresh_from_db()
    assert req.state == "QUEUED" and req.requested_at == asked and req.failed_offers == 1
    assert dispatch.accept_task(a, _accept_payload(first)) == "stale"
    (second,) = dispatch.dispatch_event(ops.event.id, now=later)
    assert second.assignee == b  # a is cooling down for this request
    dispatch.expire_offers(later + timedelta(seconds=61))
    assert Alert.objects.filter(kind="offer_failures", ticket=ticket).exists()
    assert AssignmentAttempt.objects.filter(request=req, outcome="EXPIRED").count() == 2


def test_decline_requeues_and_releases(ops):
    a = ops.valets[0]
    ticket, req = parked_with_request(a, ops.event)
    (task,) = dispatch.dispatch_event(ops.event.id)
    offer = MessageOutbox.objects.get(kind="valet.offer", task=task)
    decline = next(b[0] for b in offer.buttons if b[1] == "decline")
    assert dispatch.decline_task(a, decline) == "declined"
    req.refresh_from_db()
    task.refresh_from_db()
    assert req.state == "QUEUED" and task.status == "RELEASED"
    assert tokens.state(tokens.resolve(_accept_payload(task), lock=False)) == "revoked"


def test_offer_deadline_starts_when_provider_accepts_send(ops):
    from messaging.outbox import send_due
    ticket, req = parked_with_request(ops.valets[0], ops.event)
    (task,) = dispatch.dispatch_event(ops.event.id)
    assert task.offer_deadline is None and task.hard_deadline is not None
    send_due(timezone.now())
    task.refresh_from_db()
    assert task.offer_sent_at is not None
    assert task.offer_deadline == min(task.offer_sent_at + timedelta(seconds=30), task.hard_deadline)


def test_send_failure_releases_reservation(ops):
    from messaging.models import SimulatorControl
    from messaging.outbox import send_due
    a = ops.valets[0]
    ticket, req = parked_with_request(a, ops.event)
    send_due(timezone.now())  # flush earlier guest messages so the injected failure hits the offer
    (task,) = dispatch.dispatch_event(ops.event.id)
    SimulatorControl.set_next("permanent")
    send_due(timezone.now())
    task.refresh_from_db()
    req.refresh_from_db()
    assert task.status == "RELEASED" and task.release_reason == "send_failed" and req.state == "QUEUED"


def test_accepted_not_reassigned_alert_only(ops):
    """AT-13."""
    a = ops.valets[0]
    ticket, req = parked_with_request(a, ops.event)
    (task,) = dispatch.dispatch_event(ops.event.id)
    dispatch.accept_task(a, _accept_payload(task))
    much_later = timezone.now() + timedelta(minutes=10)
    dispatch.expire_offers(much_later)
    dispatch.dispatch_event(ops.event.id, now=much_later)
    dispatch.raise_alerts(much_later)
    assert Task.objects.filter(request=req).count() == 1
    task.refresh_from_db()
    assert task.status == "ACCEPTED"
    assert Alert.objects.filter(kind="accepted_overdue", ticket=ticket).exists()


def test_break_pending_until_handover(ops):
    from ops.services import shifts
    a = ops.valets[0]
    ticket, req = parked_with_request(a, ops.event)
    (task,) = dispatch.dispatch_event(ops.event.id)
    dispatch.accept_task(a, _accept_payload(task))
    assert shifts.set_availability(a, False) == "break_pending"
    assert not shifts.is_available(a, ops.event)


def test_wait_alerts_preserve_original_time(ops):
    asked = timezone.now() - timedelta(minutes=7)
    ticket, req = parked_with_request(ops.valets[0], ops.event, requested_at=asked)
    for v in ops.valets:
        make_busy(v, available=False)
    dispatch.raise_alerts(timezone.now())
    kinds = set(Alert.objects.filter(ticket=ticket).values_list("kind", flat=True))
    assert {"wait_warning", "wait_critical"} <= kinds


def test_no_manual_dispatch_function_exposed():
    """Supervisors never dispatch routine work: no public assign-to-staff command exists."""
    assert not hasattr(dispatch, "assign") and not hasattr(dispatch, "manual_assign")


def test_request_not_eligible_while_not_parked(ops):
    from ops.services import retrieval
    from tests.ops.intake_helpers import register_and_confirm
    ticket = register_and_confirm(ops.valets[0], ops.event, "+966501111111")
    retrieval.request_retrieval(ticket.bindings.get(), ticket)
    assert dispatch.dispatch_event(ops.event.id) == []
    assert RetrievalRequest.objects.get(ticket=ticket).state == "WAITING_FOR_PARKING"
