"""Database-enforced invariants (ADR-0003). Each test bypasses services on purpose."""

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from ops.models import KeyOccupancy, KeyStation, RetrievalRequest, Shift, Task, Ticket
from tests.factories import make_event, make_staff, make_ticket, open_shift


def _task(ticket, staff, status="ACCEPTED", type_="INTAKE", event=None):
    return Task.objects.create(event=event or ticket.event, ticket=ticket, type=type_, status=status,
                               assignee=staff, reserved_at=timezone.now())


def test_second_open_shift_rejected_by_db(world):
    other_event = make_event(venue=world.event.venue, name="Other night")
    open_shift(world.event, world.valets[0])
    with pytest.raises(IntegrityError), transaction.atomic():
        Shift.objects.create(event=other_event, staff=world.valets[0], started_at=timezone.now(),
                             started_by=world.supervisor)


def test_one_live_task_per_valet(world):
    v = world.valets[0]
    _task(make_ticket(world.event, v), v)
    with pytest.raises(IntegrityError), transaction.atomic():
        _task(make_ticket(world.event, v), v, status="OFFERED", type_="RETRIEVAL")


def test_one_live_movement_task_per_ticket(world):
    ticket = make_ticket(world.event, world.valets[0])
    _task(ticket, world.valets[0])
    with pytest.raises(IntegrityError), transaction.atomic():
        _task(ticket, world.valets[1], status="OFFERED", type_="RETRIEVAL")


def test_one_open_request_per_ticket(world):
    ticket = make_ticket(world.event, world.valets[0])
    RetrievalRequest.objects.create(event=world.event, ticket=ticket, state="QUEUED", requested_at=timezone.now(),
                                    requested_via="guest_whatsapp")
    with pytest.raises(IntegrityError), transaction.atomic():
        RetrievalRequest.objects.create(event=world.event, ticket=ticket, state="WAITING_FOR_PARKING",
                                        requested_at=timezone.now(), requested_via="guest_whatsapp")


def test_withdrawn_request_allows_new_request(world):
    ticket = make_ticket(world.event, world.valets[0])
    RetrievalRequest.objects.create(event=world.event, ticket=ticket, state="WITHDRAWN", requested_at=timezone.now(),
                                    requested_via="guest_whatsapp", withdrawn_at=timezone.now())
    RetrievalRequest.objects.create(event=world.event, ticket=ticket, state="QUEUED", requested_at=timezone.now(),
                                    requested_via="guest_whatsapp")


def test_key_hook_unique_across_events_at_same_venue(world):
    station = KeyStation.objects.get(venue=world.event.venue)
    first = make_ticket(world.event, world.valets[0])
    later_event = make_event(venue=world.event.venue, name="Next night")
    second = make_ticket(later_event, world.valets[0])
    KeyOccupancy.objects.create(key_station=station, hook_number=12, ticket=first, occupied_at=timezone.now(),
                                occupied_by=world.valets[0])
    with pytest.raises(IntegrityError), transaction.atomic():
        KeyOccupancy.objects.create(key_station=station, hook_number=12, ticket=second, occupied_at=timezone.now(),
                                    occupied_by=world.valets[0])


def test_cancelled_requires_parking_not_started(world):
    ticket = make_ticket(world.event, world.valets[0], parking_started_at=timezone.now())
    with pytest.raises(IntegrityError), transaction.atomic():
        Ticket.objects.filter(pk=ticket.pk).update(state="CANCELLED", cancelled_at=timezone.now())


def test_task_must_share_ticket_event(world):
    ticket = make_ticket(world.event, world.valets[0])
    other_event = make_event(venue=world.event.venue, name="Other night")
    with pytest.raises(IntegrityError), transaction.atomic():
        _task(ticket, world.valets[0], event=other_event)


def test_staff_phone_unique_per_org(world):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_staff(world.org, phone=world.valets[0].phone_e164)
