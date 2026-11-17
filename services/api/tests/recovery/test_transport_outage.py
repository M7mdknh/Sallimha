"""A real (simulated) WhatsApp outage and its recovery (ADR-0010). The fake transport refuses every send while the
outage lasts; the worker's own steps run over simulated minutes. Asserted throughout: nothing is delivered, offers
expire and are re-issued without duplicate assignments, stale actions are refused; after recovery only messages that
are still true are delivered, each exactly once."""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.views_health import whatsapp_status
from messaging import outbox
from messaging.models import MessageOutbox, SimulatedMessage, SimulatorControl
from ops.models import LIVE_TASK_STATUSES, Alert, Task, Ticket
from ops.services import dispatch, handover, outage, relocation
from tests.factories import open_shift
from tests.ops.dispatch_helpers import parked_with_request
from tests.ops.intake_helpers import park


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


def _tick(now):
    """One pass of the worker's steps, in the worker's order."""
    dispatch.expire_offers(now)
    relocation.expire_offers(now)
    dispatch.dispatch_all(now)
    outbox.send_due(now)


def _delivered(kind=None, ticket=None):
    qs = MessageOutbox.objects.filter(pk__in=SimulatedMessage.objects.filter(direction="out").values("outbox_id"))
    if kind:
        qs = qs.filter(kind=kind)
    if ticket is not None:
        qs = qs.filter(ticket=ticket)
    return qs


def _button(row, key):
    return next(b[0] for b in row.buttons if b[1] == key)


@pytest.mark.whatsapp_staff
def test_outage_then_recovery_without_duplicate_assignments_or_misleading_messages(ops):
    ticket, req = parked_with_request(ops.valets[0], ops.event)
    now = timezone.now()
    outbox.send_due(now)  # everything before the outage is delivered
    before = SimulatedMessage.objects.filter(direction="out").count()

    SimulatorControl.set_outage(True)
    late = park(ops.valets[1], ops.event, phone="+966501239001")  # a car parked during the outage
    outage.declare_whatsapp_outage(ops.manager, ops.org, "Provider down")
    offered = set()
    for _ in range(36):  # six minutes, ten seconds apart
        now += timedelta(seconds=10)
        _tick(now)
        assert SimulatedMessage.objects.filter(direction="out").count() == before  # nothing gets through
        assert Task.objects.filter(request=req, status="OFFERED").count() <= 1  # one offer at a time
        for valet in ops.valets:
            assert Task.objects.filter(assignee=valet, status__in=LIVE_TASK_STATUSES).count() <= 1
        offered |= set(Task.objects.filter(request=req).values_list("id", flat=True))
    assert len(offered) >= 2  # offers expired unseen and were re-issued
    assert Alert.objects.filter(kind="offer_failures").exists()
    assert MessageOutbox.objects.filter(ticket=late, kind="guest.ticket").exclude(status="SENT").exists()  # queued
    assert whatsapp_status() == "degraded"
    expired = Task.objects.filter(request=req, status="RELEASED").order_by("id").first()
    stale_accept = _button(MessageOutbox.objects.get(kind="valet.offer", task=expired), "accept")
    assert dispatch.accept_task(expired.assignee, stale_accept) == "stale"  # a late tap cannot assign
    assert not MessageOutbox.objects.filter(kind="valet.offer", task__status="RELEASED",
                                            status__in=["PENDING", "DEAD"]).exists()  # superseded, not queued

    # A car handed over during the outage with the supervisor's assistance: its code message must never go out.
    free = next(v for v in ops.valets if not Task.objects.filter(assignee=v, status__in=LIVE_TASK_STATUSES).exists())
    other, other_req = parked_with_request(free, ops.event)
    _tick(now)
    move = Task.objects.get(request=other_req, status="OFFERED")
    outage.relay_accept(ops.supervisor, move, confirmed_via="radio", now=now)
    outage.relay_ready(ops.supervisor, Task.objects.get(pk=move.pk), confirmed_via="in_person", now=now)
    handover.assisted_handover(ops.supervisor, Ticket.objects.get(pk=other.pk), "in_person_check", "checked", now=now)

    SimulatorControl.set_outage(False)
    for _ in range(40):  # until the first offer gets through
        now += timedelta(seconds=10)
        _tick(now)
        if _delivered("valet.offer", ticket).exists():
            break
    offers = _delivered("valet.offer", ticket)
    assert offers.count() == 1 and offers.get().task.status == "OFFERED"  # the current offer, nothing older
    assert not _delivered("valet.offer").filter(task_id__in=offered).exists()  # no offer made during the outage
    current = offers.get().task
    assert dispatch.accept_task(current.assignee, _button(offers.get(), "accept")) == "accepted"
    assert Task.objects.filter(request=req, status="ACCEPTED").count() == 1
    for _ in range(40):  # queued messages drain (their backoff can reach five minutes)
        now += timedelta(seconds=10)
        _tick(now)
    assert whatsapp_status() != "degraded"
    assert Task.objects.filter(request=req, status="ACCEPTED").count() == 1  # still exactly one assignment
    assert not _delivered("guest.ready", other).exists()  # the code for a car already handed over: never sent
    assert _delivered("guest.ticket", late).count() == 1 and _delivered("guest.parked", late).count() == 1
    assert _delivered("guest.accepted", ticket).count() == 1
    assert MessageOutbox.objects.filter(status="OBSOLETE").exists()
