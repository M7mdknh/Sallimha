"""Outage workflow (ADR-0008).

WhatsApp down, console up: a supervisor declares the outage; only then may they *relay* what a valet reports by
radio or in person (acceptance of the dispatcher's own offer, car ready, custody receipt, move acceptance) and
record an intake on a valet's behalf. Whole system down: staff follow the continuity procedure; afterwards a
manager records the outage window and reconciles, with the actual time kept apart from the entry time.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.errors import DomainError
from core.models import AuditEvent
from messaging.models import MessageOutbox
from ops.models import KeyOccupancy, OutageWindow, Reconciliation, RetrievalRequest, Task, Ticket
from ops.services import custody, dispatch, handover, holds, outage, relocation
from tests.factories import open_shift
from tests.ops.dispatch_helpers import parked_with_request
from tests.ops.intake_helpers import park


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


def _declared(ops):
    return outage.declare_whatsapp_outage(ops.supervisor, ops.org, "Meta status page shows an incident")


def _offered(ops):
    ticket, req = parked_with_request(ops.valets[0], ops.event)
    (task,) = dispatch.dispatch_event(ops.event.id)
    return ticket, req, task


# --- WhatsApp outage: declaration and relayed actions ------------------------------------------------------

def test_relayed_actions_require_a_declared_whatsapp_outage(ops):
    _ticket, _req, task = _offered(ops)
    with pytest.raises(DomainError) as err:
        outage.relay_accept(ops.supervisor, task, confirmed_via="radio")
    assert err.value.code == "no_active_outage"


def test_one_open_outage_per_organisation_declared_and_ended_with_audit(ops):
    window = _declared(ops)
    with pytest.raises(DomainError) as err:
        _declared(ops)
    assert err.value.code == "outage_already_declared"
    outage.end_whatsapp_outage(ops.supervisor, ops.org, "Messages flowing again")
    window.refresh_from_db()
    assert window.ended_at is not None and window.ended_by == ops.supervisor
    assert {"outage.declared", "outage.ended"} <= set(AuditEvent.objects.values_list("action", flat=True))
    with pytest.raises(DomainError):
        outage.declare_whatsapp_outage(ops.valets[0], ops.org, "valets cannot declare")


def test_relayed_acceptance_is_the_dispatchers_choice_and_records_who_relayed(ops):
    ticket, req, task = _offered(ops)
    _declared(ops)
    outage.relay_accept(ops.supervisor, task, confirmed_via="radio")
    task.refresh_from_db()
    req.refresh_from_db()
    ticket.refresh_from_db()
    assert task.status == Task.Status.ACCEPTED and req.state == RetrievalRequest.State.ACCEPTED
    assert ticket.state == Ticket.State.RETRIEVING
    accepted = AuditEvent.objects.get(action="dispatch.accepted", entity_id=ticket.id)
    assert accepted.summary["relayed_by"] == ops.supervisor.id and accepted.summary["confirmed_via"] == "radio"
    assert accepted.actor_id == task.assignee_id  # the valet accepted; the supervisor only relayed it


def test_relay_cannot_accept_an_offer_that_is_no_longer_current(ops):
    _ticket, _req, task = _offered(ops)
    _declared(ops)
    dispatch.expire_offers(timezone.now() + timedelta(hours=1))
    with pytest.raises(DomainError) as err:
        outage.relay_accept(ops.supervisor, task, confirmed_via="radio")
    assert err.value.code == "stale"


def test_relayed_ready_then_assisted_handover_delivers(ops):
    ticket, _req, task = _offered(ops)
    _declared(ops)
    outage.relay_accept(ops.supervisor, task, confirmed_via="radio")
    outage.relay_ready(ops.supervisor, Task.objects.get(pk=task.pk), confirmed_via="in_person")
    ticket.refresh_from_db()
    assert ticket.state == Ticket.State.READY
    handover.assisted_handover(ops.supervisor, ticket, "in_person_check", "Checked photos and plate with the guest")
    ticket.refresh_from_db()
    assert ticket.state == Ticket.State.DELIVERED and ticket.delivered_by == task.assignee


def test_relayed_custody_receipt(ops):
    _ticket, _req, task = _offered(ops)
    _declared(ops)
    outage.relay_accept(ops.supervisor, task, confirmed_via="radio")
    receiver = next(v for v in ops.valets if v != task.assignee)
    transfer = custody.transfer_custody(ops.supervisor, Task.objects.get(pk=task.pk), receiver, "Zone A 12",
                                        "with the valet", "handover between valets")
    outage.relay_custody_ack(ops.supervisor, transfer, confirmed_via="in_person")
    transfer.refresh_from_db()
    assert transfer.acknowledged_by == receiver
    ack = AuditEvent.objects.get(action="custody.acknowledged")
    assert ack.summary["relayed_by"] == ops.supervisor.id


def test_relayed_move_acceptance(ops):
    ticket = park(ops.valets[0], ops.event)
    move = relocation.start_relocation(ops.supervisor, ticket, ops.valets[1], "Lane")
    _declared(ops)
    outage.relay_accept(ops.supervisor, move, confirmed_via="radio")
    move.refresh_from_db()
    assert move.status == Task.Status.ACCEPTED


def test_intake_on_behalf_during_outage_parks_with_fallback_contact_and_queued_ticket(ops):
    _declared(ops)
    ticket = outage.record_intake(ops.supervisor, ops.event, valet=ops.valets[1], guest_phone="0501239876",
                                  plate="QRS 4455", description="Tahoe black", zone_code="B", detail="8",
                                  hook_number=88, reason="WhatsApp down", confirmed_via="in_person")
    assert ticket.state == Ticket.State.PARKED and ticket.parked_by == ops.valets[1]
    assert ticket.registered_by == ops.valets[1] and ticket.contact_state == Ticket.Contact.ASSISTED_FALLBACK
    assert ticket.photos_exception_reason and KeyOccupancy.objects.get(ticket=ticket).hook_number == 88
    queued = MessageOutbox.objects.get(kind="guest.ticket", ticket=ticket)
    assert queued.status == MessageOutbox.Status.PENDING  # queued, not delivered
    record = AuditEvent.objects.get(action="intake.recorded_on_behalf", entity_id=ticket.id)
    assert record.actor_id == ops.supervisor.id and record.summary["valet"] == ops.valets[1].id


def test_intake_on_behalf_refused_without_outage_and_on_an_occupied_hook(ops):
    args = dict(valet=ops.valets[1], guest_phone="0501239876", plate="QRS 4455", description="", zone_code="B",
                detail="8", hook_number=31, reason="WhatsApp down", confirmed_via="in_person")
    with pytest.raises(DomainError) as err:
        outage.record_intake(ops.supervisor, ops.event, **args)
    assert err.value.code == "no_active_outage"
    park(ops.valets[0], ops.event, hook=31)
    _declared(ops)
    with pytest.raises(DomainError) as err:
        outage.record_intake(ops.supervisor, ops.event, **args)
    assert err.value.code == "hook_occupied"


# --- Whole-system outage: recorded window and reconciliation ------------------------------------------------

def _system_window(ops, minutes_ago_start=60, minutes_ago_end=10):
    now = timezone.now()
    return outage.record_system_outage(ops.manager, ops.org, started_at=now - timedelta(minutes=minutes_ago_start),
                                       ended_at=now - timedelta(minutes=minutes_ago_end), reason="Hosting outage")


def _parked_earlier(ops, minutes_ago=90, hook=None, phone="+966501230001"):
    ticket = park(ops.valets[0], ops.event, hook=hook, phone=phone)
    earlier = timezone.now() - timedelta(minutes=minutes_ago)
    Ticket.objects.filter(pk=ticket.pk).update(created_at=earlier, parked_at=earlier)
    ticket.refresh_from_db()
    return ticket


def _handover_args(ops, window, **over):
    args = dict(outage=window, occurred_at=window.started_at + timedelta(minutes=20), delivered_by=ops.valets[0],
                verified_by=ops.supervisor, method="in_person_check",
                evidence="Offline log line 14: plate and photos matched, guest showed the WhatsApp ticket",
                reason="Delivered during the hosting outage")
    args.update(over)
    return args


def test_reconciled_handover_keeps_actual_time_apart_from_entry_time(ops):
    window = _system_window(ops)
    ticket = _parked_earlier(ops, hook=61)
    args = _handover_args(ops, window)
    record = outage.reconcile_handover(ops.manager, ticket, **args)
    ticket.refresh_from_db()
    assert ticket.state == Ticket.State.DELIVERED and ticket.delivered_at == args["occurred_at"]
    assert ticket.delivered_by == ops.valets[0]
    assert record.occurred_at == args["occurred_at"] and record.recorded_at > record.occurred_at
    assert record.recorded_by == ops.manager and record.verified_by == ops.supervisor and record.evidence
    occ = KeyOccupancy.objects.get(ticket=ticket)
    assert occ.released_at == args["occurred_at"] and occ.release_reason == "delivered"


def test_reconciliation_closes_the_open_retrieval_and_releases_the_valet(ops):
    window = _system_window(ops)
    ticket, req, task = _offered(ops)
    Ticket.objects.filter(pk=ticket.pk).update(parked_at=window.started_at - timedelta(minutes=5))
    args = _handover_args(ops, window, delivered_by=task.assignee)
    outage.reconcile_handover(ops.manager, Ticket.objects.get(pk=ticket.pk), **args)
    req.refresh_from_db()
    task.refresh_from_db()
    assert req.state == RetrievalRequest.State.COMPLETED and req.completed_at == args["occurred_at"]
    assert task.status == Task.Status.COMPLETED and task.completed_at == args["occurred_at"]  # actual, not entry
    assert not Task.objects.filter(assignee=task.assignee, status__in=["RESERVED", "OFFERED", "ACCEPTED"]).exists()


@pytest.mark.parametrize("case,code", [
    ("outside_window", "outside_outage_window"),
    ("before_parking", "conflict_time"),
    ("valet_verifier", "verifier_not_authorized"),
    ("no_evidence", "evidence_required"),
])
def test_reconciliation_rejects_conflicts(ops, case, code):
    window = _system_window(ops)
    ticket = _parked_earlier(ops, minutes_ago=90)
    over = {
        "outside_window": {"occurred_at": window.ended_at + timedelta(minutes=1)},
        "before_parking": {"occurred_at": window.started_at + timedelta(minutes=1)},
        "valet_verifier": {"verified_by": ops.valets[1]},
        "no_evidence": {"evidence": "  "},
    }[case]
    if case == "before_parking":
        Ticket.objects.filter(pk=ticket.pk).update(parked_at=window.started_at + timedelta(minutes=5))
        ticket.refresh_from_db()
    with pytest.raises(DomainError) as err:
        outage.reconcile_handover(ops.manager, ticket, **_handover_args(ops, window, **over))
    assert err.value.code == code
    ticket.refresh_from_db()
    assert ticket.state == Ticket.State.PARKED


def test_reconciliation_is_manager_only_and_never_completes_twice(ops):
    window = _system_window(ops)
    ticket = _parked_earlier(ops)
    with pytest.raises(DomainError) as err:
        outage.reconcile_handover(ops.supervisor, ticket, **_handover_args(ops, window))
    assert err.value.code == "forbidden"
    outage.reconcile_handover(ops.manager, ticket, **_handover_args(ops, window))
    with pytest.raises(DomainError) as err:
        outage.reconcile_handover(ops.manager, Ticket.objects.get(pk=ticket.pk), **_handover_args(ops, window))
    assert err.value.code == "already_delivered"
    assert Reconciliation.objects.filter(ticket=ticket).count() == 1


def test_reconciliation_does_not_bypass_a_safety_hold(ops):
    window = _system_window(ops)
    ticket = _parked_earlier(ops)
    holds.place_hold(ops.supervisor, ticket, "Identity dispute", blocks_dispatch=True, blocks_handover=True)
    with pytest.raises(DomainError) as err:
        outage.reconcile_handover(ops.manager, ticket, **_handover_args(ops, window))
    assert err.value.code == "handover_blocked"


def test_system_outage_window_must_be_in_the_past_and_not_overlap(ops):
    now = timezone.now()
    with pytest.raises(DomainError) as err:
        outage.record_system_outage(ops.manager, ops.org, started_at=now - timedelta(minutes=5),
                                    ended_at=now + timedelta(minutes=5), reason="x")
    assert err.value.code == "invalid_window"
    _system_window(ops)
    with pytest.raises(DomainError) as err:
        _system_window(ops, minutes_ago_start=30, minutes_ago_end=5)
    assert err.value.code == "overlaps"
    assert OutageWindow.objects.filter(kind="SYSTEM").count() == 1


def test_offline_intake_is_reconciled_with_its_actual_times(ops):
    window = _system_window(ops)
    received = window.started_at + timedelta(minutes=5)
    parked = window.started_at + timedelta(minutes=12)
    ticket = outage.record_intake(ops.manager, ops.event, valet=ops.valets[2], guest_phone="0501230777",
                                  plate="OFF 1234", description="", zone_code="B", detail="1", hook_number=77,
                                  reason="Received during the hosting outage", outage=window,
                                  received_at=received, parked_at=parked,
                                  evidence="Offline log line 3")
    assert ticket.created_at == received and ticket.parked_at == parked and ticket.state == Ticket.State.PARKED
    record = Reconciliation.objects.get(ticket=ticket, kind="INTAKE")
    assert record.occurred_at == parked and record.responsible == ops.valets[2]
    with pytest.raises(DomainError) as err:
        outage.record_intake(ops.manager, ops.event, valet=ops.valets[2], guest_phone="0501230778", plate="OFF 1",
                             description="", zone_code="B", detail="2", hook_number=78, reason="x", outage=window,
                             received_at=window.ended_at + timedelta(minutes=1),
                             parked_at=window.ended_at + timedelta(minutes=2), evidence="log")
    assert err.value.code == "outside_outage_window"


# --- Security Guidance findings on dafc68a (2x MEDIUM) -------------------------------------------------------

def test_reconciliation_needs_a_second_person_as_verifier_and_a_valet_from_the_event(ops):
    """Two-person attestation: the recorder cannot also be the verifier; the delivering person must be a valet
    assigned to the event."""
    from ops.models import Role
    from tests.factories import make_staff

    window = _system_window(ops)
    ticket = _parked_earlier(ops)
    with pytest.raises(DomainError) as err:
        outage.reconcile_handover(ops.manager, ticket, **_handover_args(ops, window, verified_by=ops.manager))
    assert err.value.code == "verifier_must_differ"
    stranger = make_staff(ops.org, Role.VALET, name="Not on this event")
    with pytest.raises(DomainError) as err:
        outage.reconcile_handover(ops.manager, ticket, **_handover_args(ops, window, delivered_by=stranger))
    assert err.value.code == "receiver_unavailable"
    with pytest.raises(DomainError) as err:
        outage.reconcile_handover(ops.manager, ticket, **_handover_args(ops, window, delivered_by=ops.supervisor))
    assert err.value.code == "receiver_unavailable"


def test_outage_windows_are_bounded_in_age_and_length(ops):
    now = timezone.now()
    with pytest.raises(DomainError) as err:
        outage.record_system_outage(ops.manager, ops.org, started_at=now - timedelta(days=31),
                                    ended_at=now - timedelta(days=31) + timedelta(hours=1), reason="old")
    assert err.value.code == "invalid_window"
    with pytest.raises(DomainError) as err:
        outage.record_system_outage(ops.manager, ops.org, started_at=now - timedelta(hours=30),
                                    ended_at=now - timedelta(hours=1), reason="too long")
    assert err.value.code == "invalid_window"


def test_whatsapp_outage_declared_by_an_assigned_supervisor_and_ended_by_them_or_a_manager(ops):
    from ops.models import Role
    from tests.factories import make_staff

    unassigned = make_staff(ops.org, Role.SUPERVISOR, name="Other venue supervisor")
    with pytest.raises(DomainError) as err:
        outage.declare_whatsapp_outage(unassigned, ops.org, "no standing")
    assert err.value.code == "forbidden"
    _declared(ops)
    other = make_staff(ops.org, Role.SUPERVISOR, name="Second supervisor")
    from ops.models import EventAssignment
    EventAssignment.objects.create(event=ops.event, staff=other, assigned_by=ops.manager)
    with pytest.raises(DomainError) as err:
        outage.end_whatsapp_outage(other, ops.org, "not mine")
    assert err.value.code == "forbidden"
    outage.end_whatsapp_outage(ops.manager, ops.org, "manager ends it")
