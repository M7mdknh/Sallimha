import pytest

from core.errors import DomainError
from ops.models import CarryoverCase, Event, KeyOccupancy, Ticket
from ops.services import carryover, events, intake
from tests.factories import make_event, make_staff, open_shift
from tests.ops.intake_helpers import park, register_and_confirm, through_photos


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


def test_unclaimed_requires_manager_approval_named_custodian(ops):
    """AT-24 (unclaimed part)."""
    ticket = park(ops.valets[0], ops.event, hook=40)
    with pytest.raises(DomainError):
        carryover.propose_unclaimed(ops.supervisor, ticket, custodian="", plan="Night storage")
    case = carryover.propose_unclaimed(ops.supervisor, ticket, custodian="Venue security (Ali)", plan="Keep in B2")
    ticket.refresh_from_db()
    assert ticket.state == Ticket.State.PARKED  # a proposal changes nothing yet
    with pytest.raises(DomainError) as err:
        carryover.approve_unclaimed(ops.supervisor, case)
    assert err.value.code == "forbidden"
    carryover.approve_unclaimed(ops.manager, case)
    ticket.refresh_from_db()
    case.refresh_from_db()
    assert ticket.state == Ticket.State.UNCLAIMED and case.status == CarryoverCase.Status.APPROVED
    assert ticket.delivered_at is None  # never a fake delivery


def test_key_hook_reserved_across_events_until_explicit_release(ops):
    """AT-43 / AT-58."""
    ticket = park(ops.valets[0], ops.event, hook=41)
    case = carryover.approve_unclaimed(ops.manager, carryover.propose_unclaimed(ops.supervisor, ticket,
                                                                               custodian="Security", plan="Hold"))
    next_event = make_event(venue=ops.event.venue, name="Next night")
    v = make_staff(ops.org)
    open_shift(next_event, v, ops.manager)
    other = register_and_confirm(v, next_event, "+966501112222")
    through_photos(v, other)
    intake.start_parking(v, other)
    intake.record_location(v, other, "A", "1")
    with pytest.raises(DomainError) as err:
        intake.complete_parking(v, other, 41)
    assert err.value.code == "hook_occupied"
    with pytest.raises(DomainError):
        carryover.release_carryover(ops.supervisor, case, "collected_verified", "Owner collected")
    carryover.release_carryover(ops.manager, case, "collected_verified", "Owner showed ticket and ID in person")
    assert KeyOccupancy.objects.get(ticket=ticket, hook_number=41).release_reason == "carryover_release"
    intake.complete_parking(v, other, 41)


def test_event_close_refused_with_open_custody(ops):
    park(ops.valets[0], ops.event)
    with pytest.raises(DomainError) as err:
        events.close_event(ops.manager, ops.event)
    assert err.value.code == "custody_open"


def test_event_close_allowed_after_reconciliation(ops):
    ticket = park(ops.valets[0], ops.event)
    carryover.approve_unclaimed(ops.manager, carryover.propose_unclaimed(ops.supervisor, ticket, custodian="Sec",
                                                                       plan="Hold"))
    from ops.models import Shift
    for shift in Shift.objects.filter(event=ops.event, ended_at__isnull=True):
        from ops.services import shifts
        shifts.end_shift(ops.supervisor, shift)
    with pytest.raises(DomainError):
        events.close_event(ops.supervisor, ops.event)
    events.close_event(ops.manager, ops.event)
    ops.event.refresh_from_db()
    assert ops.event.status == Event.Status.CLOSED and ops.event.closed_by == ops.manager
    assert CarryoverCase.objects.filter(ticket=ticket, status="APPROVED").exists()  # carryover remains visible


def test_open_carryover_case_blocks_new_requests_and_approval_rechecks(ops):
    """Security review regression: no request may slip in around an unclaimed proposal."""
    from ops.models import RetrievalRequest
    from ops.services import retrieval
    ticket = park(ops.valets[0], ops.event)
    case = carryover.propose_unclaimed(ops.supervisor, ticket, custodian="Security", plan="Hold")
    with pytest.raises(DomainError) as err:
        retrieval.request_retrieval(ticket.bindings.get(), ticket)
    assert err.value.code == "carryover_open"
    RetrievalRequest.objects.create(event=ops.event, ticket=ticket, state="QUEUED", requested_at=ticket.created_at,
                                    requested_via="guest_whatsapp")  # simulates a request that raced the proposal
    with pytest.raises(DomainError) as err:
        carryover.approve_unclaimed(ops.manager, case)
    assert err.value.code == "invalid_state"
