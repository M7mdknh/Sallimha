import pytest
from django.utils import timezone

from core.errors import DomainError
from ops.models import Role, Shift, Task, UnavailablePeriod
from ops.services import shifts
from tests.factories import make_event, make_staff, make_ticket, open_shift


def _live_task(world, valet):
    return Task.objects.create(event=world.event, ticket=make_ticket(world.event, valet), type="INTAKE",
                               status="ACCEPTED", assignee=valet, reserved_at=timezone.now())


def test_supervisor_starts_shift_in_assigned_event(world):
    shift = shifts.start_shift(world.supervisor, world.event, world.valets[0])
    assert shift.ended_at is None
    assert shift.availability == Shift.Availability.UNAVAILABLE  # valet taps "جاهز" to become available


def test_second_open_shift_rejected_with_clear_error(world):
    other_event = make_event(venue=world.event.venue, name="Other night")
    shifts.start_shift(world.manager, world.event, world.valets[0])
    with pytest.raises(DomainError) as err:
        shifts.start_shift(world.manager, other_event, world.valets[0])
    assert err.value.code == "shift_already_open"


def test_supervisor_cannot_start_shift_outside_assigned_event(world):
    other_event = make_event(venue=world.event.venue, name="Unassigned night")
    with pytest.raises(DomainError) as err:
        shifts.start_shift(world.supervisor, other_event, world.valets[0])
    assert err.value.code == "forbidden"


def test_valet_cannot_start_shifts(world):
    with pytest.raises(DomainError) as err:
        shifts.start_shift(world.valets[0], world.event, world.valets[1])
    assert err.value.code == "forbidden"


def test_disabled_staff_cannot_start_shift(world):
    world.valets[0].enabled = False
    world.valets[0].save()
    with pytest.raises(DomainError) as err:
        shifts.start_shift(world.supervisor, world.event, world.valets[0])
    assert err.value.code == "staff_disabled"


def test_staff_from_other_org_rejected(world):
    from tests.factories import make_org
    outsider = make_staff(make_org("Other org"))
    with pytest.raises(DomainError) as err:
        shifts.start_shift(world.manager, world.event, outsider)
    assert err.value.code == "forbidden"


def test_end_shift_refused_with_live_task(world):
    valet = world.valets[0]
    shift = open_shift(world.event, valet, world.supervisor)
    _live_task(world, valet)
    with pytest.raises(DomainError) as err:
        shifts.end_shift(world.supervisor, shift)
    assert err.value.code == "custody_open"
    shift.refresh_from_db()
    assert shift.ended_at is None


def test_end_shift_without_work_closes_it(world):
    shift = open_shift(world.event, world.valets[0], world.supervisor)
    shifts.end_shift(world.supervisor, shift)
    shift.refresh_from_db()
    assert shift.ended_at is not None and shift.ended_by == world.supervisor


def test_ready_makes_valet_available(world):
    valet = world.valets[0]
    open_shift(world.event, valet, world.supervisor, available=False)
    assert shifts.set_availability(valet, True) == "available"
    assert shifts.is_available(valet, world.event)


def test_break_pending_until_release(world):
    valet = world.valets[0]
    open_shift(world.event, valet, world.supervisor)
    task = _live_task(world, valet)
    assert shifts.set_availability(valet, False) == "break_pending"
    assert not shifts.is_available(valet, world.event)
    task.status = "COMPLETED"
    task.save()
    shifts.on_task_released(valet)
    shift = Shift.objects.get(staff=valet, ended_at__isnull=True)
    assert shift.availability == Shift.Availability.UNAVAILABLE and not shift.break_pending
    assert UnavailablePeriod.objects.filter(shift=shift, ended_at__isnull=True).exists()


def test_break_without_work_is_immediate_and_recorded(world):
    valet = world.valets[0]
    shift = open_shift(world.event, valet, world.supervisor)
    assert shifts.set_availability(valet, False) == "unavailable"
    assert UnavailablePeriod.objects.filter(shift=shift, ended_at__isnull=True).count() == 1
    shifts.set_availability(valet, True)
    assert UnavailablePeriod.objects.filter(shift=shift, ended_at__isnull=True).count() == 0


def test_availability_without_shift_reports_no_shift(world):
    assert shifts.set_availability(world.valets[2], True) == "no_shift"


def test_is_available_false_with_live_task(world):
    valet = world.valets[0]
    open_shift(world.event, valet, world.supervisor)
    _live_task(world, valet)
    assert not shifts.is_available(valet, world.event)


def test_manager_role_inherits_supervisor_rights_everywhere(world):
    other_event = make_event(venue=world.event.venue, name="Other night")
    shift = shifts.start_shift(world.manager, other_event, world.valets[1])
    assert shift.event == other_event


@pytest.mark.parametrize("role", [Role.SUPERVISOR, Role.MANAGER])
def test_shift_start_is_audited(world, role):
    from core.models import AuditEvent
    actor = world.supervisor if role == Role.SUPERVISOR else world.manager
    shifts.start_shift(actor, world.event, world.valets[0])
    assert AuditEvent.objects.filter(action="shift.start", actor_id=actor.id).exists()


def test_supervisor_cannot_grant_event_scope_to_another_supervisor(world):
    """Security review finding: shift start must not become an assignment backdoor."""
    from ops.models import EventAssignment
    other_sup = make_staff(world.org, Role.SUPERVISOR, name="Other supervisor")
    with pytest.raises(DomainError) as err:
        shifts.start_shift(world.supervisor, world.event, other_sup)
    assert err.value.code == "forbidden"
    assert not EventAssignment.objects.filter(event=world.event, staff=other_sup).exists()


def test_manager_can_assign_and_start_supervisor_shift(world):
    other_sup = make_staff(world.org, Role.SUPERVISOR, name="Other supervisor")
    assert shifts.start_shift(world.manager, world.event, other_sup).staff == other_sup


def test_supervisor_can_start_shift_for_already_assigned_supervisor(world):
    from tests.factories import assign
    other_sup = make_staff(world.org, Role.SUPERVISOR, name="Assigned supervisor")
    assign(world.event, other_sup)
    assert shifts.start_shift(world.supervisor, world.event, other_sup).staff == other_sup
