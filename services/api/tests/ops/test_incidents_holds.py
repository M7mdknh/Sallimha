import pytest

from core.errors import DomainError
from ops.models import Incident, KeyOccupancy, SafetyHold, Task, Ticket
from ops.services import dispatch, handover, holds, incidents, relocation, retrieval
from tests.factories import open_shift
from tests.ops.dispatch_helpers import parked_with_request
from tests.ops.intake_helpers import park


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


def test_supervisor_creates_and_annotates_but_cannot_resolve_incident(ops):
    """AT-20 (incident part)."""
    ticket = park(ops.valets[0], ops.event)
    incident = incidents.open_incident(ops.supervisor, ops.event, "damage", "Scratch on rear bumper", ticket=ticket)
    incidents.annotate(ops.supervisor, incident, "Photos requested from the valet")
    with pytest.raises(DomainError) as err:
        incidents.resolve(ops.supervisor, incident, "Guest compensated")
    assert err.value.code == "forbidden"
    with pytest.raises(DomainError):
        incidents.resolve(ops.manager, incident, "  ")
    incidents.resolve(ops.manager, incident, "Pre-existing damage confirmed from intake photos")
    incident.refresh_from_db()
    assert incident.status == Incident.Status.RESOLVED and incident.resolved_by == ops.manager


def test_incident_alone_does_not_block_hold_does(ops):
    """AT-22."""
    from tests.ops.test_handover import _btn, _code
    ticket, req = parked_with_request(ops.valets[0], ops.event)
    (task,) = dispatch.dispatch_event(ops.event.id)
    dispatch.accept_task(task.assignee, _btn("valet.offer", task, "accept"))
    handover.mark_ready(task.assignee, _btn("valet.assigned", task, "car_ready"))
    incidents.open_incident(ops.supervisor, ops.event, "damage", "Dent reported at pickup", ticket=ticket)
    ticket.refresh_from_db()
    assert ticket.state == Ticket.State.READY  # incident never falsifies vehicle state
    code = _code(ticket)
    hold = holds.place_hold(ops.supervisor, ticket, "Damage dispute", blocks_dispatch=False, blocks_handover=True)
    assert handover.verify_collection(task.assignee, ticket, code)[0] == "ok"
    assert handover.complete_handover(task.assignee, _btn("valet.code_ok", task, "delivered")) == "blocked"
    holds.clear_hold(ops.supervisor, hold, "Manager reviewed photos")
    assert handover.complete_handover(task.assignee, _btn("valet.code_ok", task, "delivered")) == "delivered"


def test_dispatch_hold_keeps_request_queued(ops):
    ticket, req = parked_with_request(ops.valets[0], ops.event)
    holds.place_hold(ops.supervisor, ticket, "Key missing from hook", blocks_dispatch=True, blocks_handover=True)
    assert dispatch.dispatch_event(ops.event.id) == []
    req.refresh_from_db()
    assert req.state == "QUEUED"
    assert SafetyHold.objects.filter(ticket=ticket, cleared_at__isnull=True).count() == 1


def test_valet_cannot_place_holds(ops):
    ticket = park(ops.valets[0], ops.event)
    with pytest.raises(DomainError):
        holds.place_hold(ops.valets[0], ticket, "x", blocks_dispatch=True, blocks_handover=True)


def test_assisted_handover_supervisor_only_records_reason(ops):
    """AT-41: guest without a phone."""
    from tests.ops.test_handover import _btn
    ticket, req = parked_with_request(ops.valets[0], ops.event)
    (task,) = dispatch.dispatch_event(ops.event.id)
    dispatch.accept_task(task.assignee, _btn("valet.offer", task, "accept"))
    handover.mark_ready(task.assignee, _btn("valet.assigned", task, "car_ready"))
    with pytest.raises(DomainError):
        handover.assisted_handover(ops.valets[0], ticket, "in_person_check", "Phone battery dead")
    with pytest.raises(DomainError):
        handover.assisted_handover(ops.supervisor, ticket, "in_person_check", " ")
    handover.assisted_handover(ops.supervisor, ticket, "in_person_check", "Phone dead; matched plate, ticket and face")
    ticket.refresh_from_db()
    assert ticket.state == Ticket.State.DELIVERED and ticket.delivered_by == task.assignee
    assert ticket.contact_state == Ticket.Contact.ASSISTED_FALLBACK


def test_assisted_request_for_guest_without_phone(ops):
    ticket = park(ops.valets[0], ops.event)
    req, created = retrieval.request_retrieval(None, ticket, via="assisted", actor=ops.supervisor)
    assert created and req.assisted_by == ops.supervisor and req.state == "QUEUED"


def test_relocation_task_moves_hook_records_custody(ops):
    """AT-33 relocation."""
    ticket = park(ops.valets[0], ops.event, hook=21)
    task = relocation.start_relocation(ops.supervisor, ticket, ops.valets[1], "Blocking emergency lane")
    assert task.type == Task.Type.RELOCATION and task.status == "ACCEPTED"
    retrieval.request_retrieval(ticket.bindings.get(), ticket)
    assert dispatch.dispatch_event(ops.event.id) == []  # waits until the movement task is released
    relocation.complete_relocation(ops.supervisor, task, zone_code="B", detail="2", hook_number=22)
    ticket.refresh_from_db()
    assert ticket.location_zone.code == "B"
    assert KeyOccupancy.objects.get(ticket=ticket, released_at__isnull=True).hook_number == 22
    assert KeyOccupancy.objects.get(ticket=ticket, hook_number=21).release_reason == "relocated"
    assert len(dispatch.dispatch_event(ops.event.id)) == 1


def test_poor_rating_opens_complaint_incident(ops):
    from django.utils import timezone

    from ops.services.ratings import record_rating
    ticket = park(ops.valets[0], ops.event)
    Ticket.objects.filter(pk=ticket.pk).update(state="DELIVERED", delivered_at=timezone.now(),
                                               delivered_by=ops.valets[0])
    record_rating(ticket.bindings.get(), ticket, "POOR", "wamid.poor.1")
    assert Incident.objects.get(ticket=ticket).category == "complaint"


def test_note_on_stale_copy_never_reopens_resolved_incident(ops):
    """Security review regression: annotate must not regress RESOLVED via a stale in-memory status."""
    stale = incidents.open_incident(ops.supervisor, ops.event, "damage", "Scratch")
    incidents.resolve(ops.manager, Incident.objects.get(pk=stale.pk), "Pre-existing")
    incidents.annotate(ops.supervisor, stale, "Late note")
    assert Incident.objects.get(pk=stale.pk).status == Incident.Status.RESOLVED
