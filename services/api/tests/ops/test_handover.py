import pytest
from django.utils import timezone

from core.errors import DomainError
from messaging.models import MessageOutbox
from messaging.outbox import send_due
from ops.models import Alert, CollectionCode, KeyOccupancy, RetrievalRequest, Task, Ticket
from ops.services import custody, dispatch, handover, retrieval
from tests.factories import open_shift
from tests.ops.dispatch_helpers import parked_with_request


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


def _btn(kind, task, key):
    row = MessageOutbox.objects.filter(kind=kind, task=task).latest("id")
    return next(b[0] for b in row.buttons if b[1] == key)


def accepted(ops, valet=None):
    valet = valet or ops.valets[0]
    ticket, req = parked_with_request(valet, ops.event)
    (task,) = dispatch.dispatch_event(ops.event.id)
    assert dispatch.accept_task(task.assignee, _btn("valet.offer", task, "accept")) == "accepted"
    task.refresh_from_db()
    return ticket, req, task


def ready(ops):
    ticket, req, task = accepted(ops)
    assert handover.mark_ready(task.assignee, _btn("valet.assigned", task, "car_ready")) == "ready"
    ticket.refresh_from_db()
    return ticket, req, task


def _code(ticket):
    row = MessageOutbox.objects.get(kind="guest.ready", ticket=ticket)
    send_due(timezone.now())
    row.refresh_from_db()
    from messaging.models import SimulatedMessage
    body = SimulatedMessage.objects.get(outbox_id=row.id).body
    return next(tok for tok in body.replace(".", " ").split() if tok.isdigit() and len(tok) == 6)


def test_ready_code_handover_closes_once_releases_all(ops):
    """AT-15."""
    ticket, req, task = ready(ops)
    assert ticket.state == Ticket.State.READY
    code = _code(ticket)
    assert CollectionCode.objects.get(ticket=ticket).delivery_enc == ""  # wiped after sending
    assert handover.verify_collection(task.assignee, ticket, code)[0] == "ok"
    payload = _btn("valet.code_ok", task, "delivered")
    assert handover.complete_handover(task.assignee, payload) == "delivered"
    assert handover.complete_handover(task.assignee, payload) == "duplicate"
    ticket.refresh_from_db()
    req.refresh_from_db()
    task.refresh_from_db()
    assert ticket.state == Ticket.State.DELIVERED and ticket.delivered_by == task.assignee
    assert req.state == "COMPLETED" and task.status == "COMPLETED"
    assert not KeyOccupancy.objects.filter(ticket=ticket, released_at__isnull=True).exists()
    assert CollectionCode.objects.get(ticket=ticket).consumed_at is not None
    rating = MessageOutbox.objects.get(kind="guest.delivered", ticket=ticket)
    assert [b[1] for b in rating.buttons] == ["rate_excellent", "rate_okay", "rate_poor"]
    from ops.services.shifts import is_available
    assert is_available(task.assignee, ops.event)


def test_wrong_code_five_attempts_then_review(ops):
    """AT-16."""
    ticket, req, task = ready(ops)
    code = _code(ticket)
    wrong = "000000" if code != "000000" else "111111"
    for expected_remaining in (4, 3, 2, 1):
        assert handover.verify_collection(task.assignee, ticket, wrong) == ("wrong", expected_remaining)
    assert handover.verify_collection(task.assignee, ticket, wrong)[0] == "locked"
    assert handover.verify_collection(task.assignee, ticket, code)[0] == "locked"
    assert Alert.objects.filter(kind="code_locked", ticket=ticket).exists()


def test_handover_requires_verified_code(ops):
    ticket, req, task = ready(ops)
    from ops.services import tokens
    forged = tokens.issue("valet_delivered", staff=task.assignee, task=task, ticket=ticket, generation=task.generation)
    assert handover.complete_handover(task.assignee, forged) == "stale"


def test_late_ready_from_superseded_assignee_rejected(ops):
    """AT-14."""
    ticket, req, task = accepted(ops)
    old = task.assignee
    payload = _btn("valet.assigned", task, "car_ready")
    receiver = next(v for v in ops.valets if v != old)
    transfer = custody.transfer_custody(ops.supervisor, task, receiver, "Zone A 12", "Hook 1", "phone died")
    assert handover.mark_ready(old, payload) == "stale"
    ticket.refresh_from_db()
    assert ticket.state == Ticket.State.RETRIEVING
    custody.acknowledge_custody(receiver, transfer)
    new_task = Task.objects.get(request=req, assignee=receiver)
    assert new_task.status == "ACCEPTED"


def test_transfer_custody_revokes_old_tokens_requires_ack(ops):
    ticket, req, task = accepted(ops)
    receiver = next(v for v in ops.valets if v != task.assignee)
    transfer = custody.transfer_custody(ops.supervisor, task, receiver, "Zone A 12", "with valet", "offline")
    new_task = Task.objects.get(request=req, assignee=receiver)
    assert new_task.status == "RESERVED" and transfer.acknowledged_at is None
    with pytest.raises(DomainError):
        custody.acknowledge_custody(ops.valets[0] if receiver != ops.valets[0] else ops.valets[1], transfer)
    with pytest.raises(DomainError):
        custody.transfer_custody(ops.valets[2], new_task, ops.valets[2], "x", "y", "valets cannot")


def test_withdraw_accepted_requires_custody_resolution(ops):
    """AT-57."""
    ticket, req, task = accepted(ops)
    with pytest.raises(DomainError) as err:
        retrieval.withdraw_request(ops.supervisor, req, "guest staying")
    assert err.value.code == "custody_resolution_required"
    custody.withdraw_accepted_with_custody_resolution(ops.supervisor, req, zone_code="B", detail="7", hook_number=44,
                                                      reason="guest staying longer")
    ticket.refresh_from_db()
    req.refresh_from_db()
    task.refresh_from_db()
    assert ticket.state == Ticket.State.PARKED and ticket.location_zone.code == "B"
    assert req.state == "WITHDRAWN" and task.status == "RELEASED" and task.release_reason == "custody_resolved"
    assert KeyOccupancy.objects.get(ticket=ticket, released_at__isnull=True).hook_number == 44
    from ops.services.shifts import is_available
    assert is_available(task.assignee, ops.event)


def test_ready_code_revoked_on_phone_correction(ops):
    ticket, req, task = ready(ops)
    old_code = _code(ticket)
    retrieval.correct_guest_phone(ops.supervisor, ticket, "+966507777777", "wrong number")
    assert handover.verify_collection(task.assignee, ticket, old_code)[0] == "wrong"
    assert CollectionCode.objects.filter(ticket=ticket, revoked_at__isnull=True).count() == 1
    assert RetrievalRequest.objects.get(pk=req.pk).state == "ACCEPTED"
