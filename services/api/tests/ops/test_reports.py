from datetime import timedelta

import pytest
from django.utils import timezone

from core.errors import DomainError
from core.models import AuditEvent
from ops.models import RetrievalRequest, Role, Shift, Ticket, UnavailablePeriod
from ops.services import reports
from tests.factories import make_event, make_staff, open_shift
from tests.ops.intake_helpers import park


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    world.admin = make_staff(world.org, Role.ADMIN)
    return world


def _delivered(ops, phone, requested_ago, accepted_ago, ready_ago, delivered_ago):
    now = timezone.now()
    ticket = park(ops.valets[0], ops.event, phone=phone)
    RetrievalRequest.objects.create(event=ops.event, ticket=ticket, state="COMPLETED", requested_via="guest_whatsapp",
                                    requested_at=now - timedelta(seconds=requested_ago),
                                    accepted_at=now - timedelta(seconds=accepted_ago),
                                    completed_at=now - timedelta(seconds=delivered_ago))
    Ticket.objects.filter(pk=ticket.pk).update(state="DELIVERED", delivered_by=ops.valets[1],
                                               ready_at=now - timedelta(seconds=ready_ago),
                                               delivered_at=now - timedelta(seconds=delivered_ago))
    return ticket


def test_stage_durations_survive_reassignment(ops):
    """AT-52: requested→accepted includes queue time and unanswered offers (original requested_at)."""
    _delivered(ops, "+966501000011", requested_ago=600, accepted_ago=300, ready_ago=120, delivered_ago=60)
    _delivered(ops, "+966501000012", requested_ago=400, accepted_ago=300, ready_ago=200, delivered_ago=100)
    report = reports.event_report(ops.manager, ops.event)
    assert report["stages"]["request_to_accept"]["median_s"] == 200
    assert report["stages"]["request_to_accept"]["p95_s"] == 300
    assert report["stages"]["accept_to_ready"]["median_s"] == 140
    assert report["stages"]["ready_to_delivered"]["count"] == 2
    assert report["outcomes"]["DELIVERED"] == 2


def test_hours_from_actual_shifts_breaks_separate(ops):
    shift = Shift.objects.get(staff=ops.valets[2], ended_at__isnull=True)
    start = timezone.now() - timedelta(hours=4)
    Shift.objects.filter(pk=shift.pk).update(started_at=start, ended_at=start + timedelta(hours=3))
    UnavailablePeriod.objects.create(shift=shift, started_at=start + timedelta(hours=1),
                                     ended_at=start + timedelta(hours=1, minutes=30))
    row = next(r for r in reports.event_report(ops.manager, ops.event)["hours"] if r["staff_id"] == ops.valets[2].id)
    assert row["worked_s"] == 3 * 3600 and row["break_s"] == 1800  # breaks shown, not deducted (policy needed)


def test_supervisor_cannot_read_reports(ops):
    with pytest.raises(DomainError):
        reports.event_report(ops.supervisor, ops.event)


def test_manager_export_has_no_phones(ops):
    """AT-29 / AT-20."""
    _delivered(ops, "+966501000013", 300, 200, 100, 50)
    rows = reports.ticket_rows(ops.manager, ops.event, state=None)
    assert rows and all("phone" not in key for key in rows[0])
    assert "966501000013" not in str(rows)


def test_export_respects_filters_and_scope(ops):
    _delivered(ops, "+966501000014", 300, 200, 100, 50)
    park(ops.valets[0], ops.event, phone="+966501000015")
    assert {r["state"] for r in reports.ticket_rows(ops.manager, ops.event, state="PARKED")} == {"PARKED"}
    other_sup = make_staff(ops.org, Role.SUPERVISOR)
    with pytest.raises(DomainError):
        reports.ticket_rows(other_sup, ops.event, state=None)
    from tests.factories import make_org
    outsider = make_staff(make_org("Other"), Role.ADMIN)
    with pytest.raises(DomainError):
        reports.ticket_rows(outsider, ops.event, state=None)


def test_guest_phone_export_admin_only_and_audited(ops):
    """AT-20 / AT-48."""
    _delivered(ops, "+966501000016", 300, 200, 100, 50)
    with pytest.raises(DomainError):
        reports.guest_phone_rows(ops.manager, ops.event)
    rows = reports.guest_phone_rows(ops.admin, ops.event)
    assert rows[0]["phone"] == "+966501000016"
    entry = AuditEvent.objects.get(action="export.guest_phones")
    assert entry.summary == {"rows": 1} and "966" not in str(entry.summary)


def test_report_scoped_to_event(ops):
    other = make_event(venue=ops.event.venue, name="Other night")
    assert reports.event_report(ops.manager, other)["outcomes"] == {}
