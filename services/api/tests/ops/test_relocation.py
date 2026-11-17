"""Relocation custody (ADR-0007): assigning a move is an offer, not an acceptance; the vehicle's confirmed location
changes only when the move is completed, and the mover is the valet who accepted it."""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.errors import DomainError
from core.models import AuditEvent
from messaging.models import MessageOutbox
from ops.models import Alert, KeyOccupancy, Task, Ticket
from ops.services import dispatch, holds, relocation, retrieval
from tests.factories import open_shift
from tests.ops.intake_helpers import park
from tests.wa import button, last, say, tap


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


def _offer_button(task, key):
    row = MessageOutbox.objects.filter(kind="valet.relocation_offer", task=task).latest("id")
    return next(b[0] for b in row.buttons if b[1] == key)


@pytest.mark.whatsapp_staff
def test_assigning_a_move_is_an_offer_and_changes_nothing_physical(ops):
    ticket = park(ops.valets[0], ops.event, hook=21)
    task = relocation.start_relocation(ops.supervisor, ticket, ops.valets[1], "Blocking emergency lane")
    assert task.status == Task.Status.OFFERED and task.accepted_at is None and task.offer_deadline is not None
    ticket.refresh_from_db()
    assert ticket.location_zone.code == "A" and ticket.location_detail == "12"
    assert KeyOccupancy.objects.get(ticket=ticket, released_at__isnull=True).hook_number == 21
    offer = last(ops.valets[1])
    assert offer.template == "valet.relocation_offer" and {b[1] for b in offer.buttons} == {"accept", "decline"}


def test_supervisor_cannot_record_completion_of_an_unaccepted_move(ops):
    ticket = park(ops.valets[0], ops.event, hook=21)
    task = relocation.start_relocation(ops.supervisor, ticket, ops.valets[1], "Lane")
    with pytest.raises(DomainError) as err:
        relocation.complete_relocation(ops.supervisor, task, zone_code="B", detail="2", hook_number=22,
                                       confirmed_via="in_person")
    assert err.value.code == "not_accepted"
    ticket.refresh_from_db()
    assert ticket.location_zone.code == "A"


@pytest.mark.whatsapp_staff
def test_mover_accepts_moves_and_reports_the_new_location_in_whatsapp(ops):
    mover = ops.valets[1]
    ticket = park(ops.valets[0], ops.event, hook=21)
    retrieval.request_retrieval(ticket.bindings.get(), ticket)
    task = relocation.start_relocation(ops.supervisor, ticket, mover, "Lane")
    assert dispatch.dispatch_event(ops.event.id) == []  # retrieval waits for the movement custody
    tap(mover.phone_e164, _offer_button(task, "accept"))
    task.refresh_from_db()
    assert task.status == Task.Status.ACCEPTED and task.accepted_at is not None
    ticket.refresh_from_db()
    assert ticket.location_zone.code == "A"  # not moved until the mover reports it
    tap(mover.phone_e164, button(last(mover), "moved"))
    say(mover.phone_e164, "B 2")
    say(mover.phone_e164, "22")
    ticket.refresh_from_db()
    task.refresh_from_db()
    assert task.status == Task.Status.COMPLETED and ticket.location_zone.code == "B"
    assert KeyOccupancy.objects.get(ticket=ticket, released_at__isnull=True).hook_number == 22
    assert KeyOccupancy.objects.get(ticket=ticket, hook_number=21).release_reason == "relocated"
    done = AuditEvent.objects.get(action="relocation.complete", entity_id=ticket.id)
    assert done.summary["mover"] == mover.id and done.summary["from"] == "A 12" and done.summary["to"] == "B 2"
    assert len(dispatch.dispatch_event(ops.event.id)) == 1


@pytest.mark.whatsapp_staff
def test_supervisor_records_completion_only_after_acceptance_and_names_the_mover(ops):
    mover = ops.valets[1]
    ticket = park(ops.valets[0], ops.event, hook=21)
    task = relocation.start_relocation(ops.supervisor, ticket, mover, "Lane")
    tap(mover.phone_e164, _offer_button(task, "accept"))
    task.refresh_from_db()
    relocation.complete_relocation(ops.supervisor, task, zone_code="B", detail="5", hook_number=25,
                                   confirmed_via="in_person")
    done = AuditEvent.objects.get(action="relocation.complete", entity_id=ticket.id)
    assert done.summary["mover"] == mover.id and done.summary["recorded_by"] == ops.supervisor.id
    assert done.summary["confirmed_via"] == "in_person"


@pytest.mark.whatsapp_staff
def test_decline_returns_the_move_to_the_supervisor_without_reassignment(ops):
    ticket = park(ops.valets[0], ops.event)
    task = relocation.start_relocation(ops.supervisor, ticket, ops.valets[1], "Lane")
    tap(ops.valets[1].phone_e164, _offer_button(task, "decline"))
    task.refresh_from_db()
    assert task.status == Task.Status.RELEASED and task.release_reason == "declined"
    assert Alert.objects.filter(kind="relocation_declined", ticket=ticket).exists()
    assert not Task.objects.filter(ticket=ticket, status__in=["RESERVED", "OFFERED", "ACCEPTED"]).exists()


def test_unanswered_move_offer_expires(ops):
    ticket = park(ops.valets[0], ops.event)
    task = relocation.start_relocation(ops.supervisor, ticket, ops.valets[1], "Lane")
    assert relocation.expire_offers(timezone.now() + timedelta(hours=1)) == 1
    task.refresh_from_db()
    assert task.status == Task.Status.RELEASED and task.release_reason == "expired"
    assert Alert.objects.filter(kind="relocation_declined", ticket=ticket).exists()


def test_movement_hold_blocks_a_new_move(ops):
    ticket = park(ops.valets[0], ops.event)
    holds.place_hold(ops.supervisor, ticket, "Police check", blocks_dispatch=True, blocks_handover=True)
    with pytest.raises(DomainError) as err:
        relocation.start_relocation(ops.supervisor, ticket, ops.valets[1], "Lane")
    assert err.value.code == "hold_active"


@pytest.mark.whatsapp_staff
def test_cancel_offered_move_freely_but_accepted_move_needs_custody_confirmation(ops):
    ticket = park(ops.valets[0], ops.event, hook=21)
    offered = relocation.start_relocation(ops.supervisor, ticket, ops.valets[1], "Lane")
    relocation.cancel_relocation(ops.supervisor, offered, reason="Not needed", car_returned=False)
    offered.refresh_from_db()
    assert offered.status == Task.Status.RELEASED and offered.release_reason == "cancelled"
    accepted = relocation.start_relocation(ops.supervisor, ticket, ops.valets[2], "Lane again")
    tap(ops.valets[2].phone_e164, _offer_button(accepted, "accept"))
    accepted.refresh_from_db()
    with pytest.raises(DomainError) as err:
        relocation.cancel_relocation(ops.supervisor, accepted, reason="Not needed", car_returned=False)
    assert err.value.code == "custody_resolution_required"
    relocation.cancel_relocation(ops.supervisor, accepted, reason="Back where it was", car_returned=True)
    accepted.refresh_from_db()
    ticket.refresh_from_db()
    assert accepted.status == Task.Status.RELEASED and ticket.location_zone.code == "A"
    assert KeyOccupancy.objects.get(ticket=ticket, released_at__isnull=True).hook_number == 21


def test_busy_valet_cannot_be_given_a_move(ops):
    ticket = park(ops.valets[0], ops.event)
    other = park(ops.valets[0], ops.event, phone="+966501112233")
    relocation.start_relocation(ops.supervisor, ticket, ops.valets[1], "Lane")
    with pytest.raises(DomainError) as err:
        relocation.start_relocation(ops.supervisor, other, ops.valets[1], "Lane")
    assert err.value.code == "receiver_unavailable"
    assert Ticket.objects.get(pk=other.pk).tasks.filter(type="RELOCATION").count() == 0
