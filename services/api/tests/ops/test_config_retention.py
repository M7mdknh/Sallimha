from datetime import timedelta

import pytest
from django.utils import timezone

from core.errors import DomainError
from core.models import AuditEvent
from messaging.models import MessageOutbox
from ops.models import GuestBinding, Media, Role, Task, Ticket
from ops.services import config, dispatch, holds, incidents, opening, retention
from tests.factories import make_staff, open_shift
from tests.ops.dispatch_helpers import parked_with_request
from tests.ops.intake_helpers import park


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    world.admin = make_staff(world.org, Role.ADMIN)
    return world


def test_timing_change_audited_and_live_offer_keeps_deadline(ops):
    """AT-40."""
    from messaging.outbox import send_due
    ticket, req = parked_with_request(ops.valets[0], ops.event)
    (task,) = dispatch.dispatch_event(ops.event.id)
    send_due(timezone.now())
    task.refresh_from_db()
    original = task.offer_deadline
    with pytest.raises(DomainError):
        config.update_timings(ops.manager, ops.org, {"offer_window_s": 45})
    config.update_timings(ops.admin, ops.org, {"offer_window_s": 45})
    task.refresh_from_db()
    assert task.offer_deadline == original
    assert dispatch.timings(ops.event)["offer_window_s"] == 45
    entry = AuditEvent.objects.get(action="config.timings")
    assert entry.summary["before"]["offer_window_s"] == 30 and entry.summary["after"]["offer_window_s"] == 45
    with pytest.raises(DomainError):
        config.update_timings(ops.admin, ops.org, {"offer_window_s": 90})  # above the 60 s hard limit
    with pytest.raises(DomainError):
        config.update_timings(ops.admin, ops.org, {"offer_window_s": 0})
    with pytest.raises(DomainError):
        config.update_timings(ops.admin, ops.org, {"unknown_setting": 5})


def test_template_wording_change_keeps_action(ops):
    """AT-47."""
    from messaging.outbox import render
    config.update_templates(ops.admin, ops.org, {"guest.ticket": {"ar": "مرحبًا! تذكرتك {ticket} لدى {venue}.",
                                                                   "en": "Hello! Ticket {ticket} at {venue}."}})
    ticket = park(ops.valets[0], ops.event)
    row = MessageOutbox.objects.get(kind="guest.ticket", ticket=ticket)
    payload = render(row, timezone.now())
    assert payload.text.startswith("مرحبًا!")
    from tests.wa import button, tap
    tap("+966501234567", button(row, "request_car"))
    assert ticket.requests.count() == 1


def test_template_override_rejects_placeholder_changes(ops):
    with pytest.raises(DomainError) as err:
        config.update_templates(ops.admin, ops.org, {"guest.ready": {"ar": "جاهزة", "en": "Ready"}})
    assert err.value.code == "placeholders_mismatch"


def _delivered(ops, phone, days_ago):
    ticket = park(ops.valets[0], ops.event, phone=phone)
    Ticket.objects.filter(pk=ticket.pk).update(state="DELIVERED", delivered_by=ops.valets[0],
                                               delivered_at=timezone.now() - timedelta(days=days_ago))
    return ticket


def test_retention_zero_never_deletes(ops):
    _delivered(ops, "+966501000001", days_ago=400)
    preview = retention.preview(ops.org)
    assert preview["guest_contact"] == {"days": 0, "eligible": 0}
    assert retention.apply(ops.admin, ops.org)["guest_contact"] == 0


def test_retention_skips_held_evidence_and_audits(ops):
    """AT-30."""
    config.update_retention(ops.admin, ops.org, {"guest_contact": 30, "intake_photos": 30})
    old = _delivered(ops, "+966501000002", days_ago=60)
    disputed = _delivered(ops, "+966501000003", days_ago=60)
    recent = _delivered(ops, "+966501000004", days_ago=5)
    incidents.open_incident(ops.supervisor, ops.event, "identity_dispute", "Owner disputes handover", ticket=disputed)
    assert retention.preview(ops.org)["guest_contact"]["eligible"] == 1
    with pytest.raises(DomainError):
        retention.apply(ops.supervisor, ops.org)
    result = retention.apply(ops.admin, ops.org)
    assert result == {"guest_contact": 1, "intake_photos": 4, "incident_evidence": 0}
    assert GuestBinding.objects.get(ticket=old).phone_masked == "redacted"
    assert GuestBinding.objects.get(ticket=disputed).phone_masked != "redacted"
    assert GuestBinding.objects.get(ticket=recent).phone_masked != "redacted"
    assert Media.objects.filter(ticket=old, deleted_at__isnull=False).count() == 4
    assert Media.objects.filter(ticket=disputed, deleted_at__isnull=True).count() == 4
    entry = AuditEvent.objects.get(action="retention.apply")
    assert entry.summary == {"guest_contact": 1, "intake_photos": 4, "incident_evidence": 0}


def test_hold_protects_evidence_from_retention(ops):
    config.update_retention(ops.admin, ops.org, {"intake_photos": 30})
    held = park(ops.valets[0], ops.event, phone="+966501000005")
    holds.place_hold(ops.supervisor, held, "Insurance claim", blocks_dispatch=True, blocks_handover=True)
    Ticket.objects.filter(pk=held.pk).update(state="DELIVERED", delivered_by=ops.valets[0],
                                             delivered_at=timezone.now() - timedelta(days=90))
    assert retention.preview(ops.org)["intake_photos"]["eligible"] == 0


def test_dead_letter_replay_admin_only_and_audited(ops):
    from messaging import outbox
    from messaging.models import SimulatorControl
    SimulatorControl.set_next("permanent")
    row = outbox.enqueue("valet.available_ok", staff=ops.valets[0], template="valet.available_ok", params={},
                         dedupe_key="dl-1")
    outbox.send_due(timezone.now())
    assert [r.id for r in opening.dead_letters(ops.org)] == [row.id]
    with pytest.raises(DomainError):
        opening.replay_dead_letter(ops.supervisor, row)
    opening.replay_dead_letter(ops.admin, row)
    row.refresh_from_db()
    assert row.status == "PENDING" and AuditEvent.objects.filter(action="outbox.replay").exists()


def test_opening_check_degraded_when_worker_stale(ops):
    """AT-44."""
    result = opening.opening_check(ops.event)
    assert result["ok"] is False
    assert "worker" in result["causes"] and "whatsapp" in result["causes"]
    from core.models import WorkerHeartbeat
    WorkerHeartbeat.objects.create(worker_id="w", beat_at=timezone.now())
    result = opening.opening_check(ops.event)
    assert "worker" not in result["causes"] and result["zones"] >= 1 and result["key_hooks"] >= 1


def test_live_offer_count_unaffected_by_config_change(ops):
    ticket, req = parked_with_request(ops.valets[0], ops.event)
    dispatch.dispatch_event(ops.event.id)
    config.update_timings(ops.admin, ops.org, {"hard_limit_s": 120})
    assert Task.objects.filter(status="OFFERED").count() == 1
