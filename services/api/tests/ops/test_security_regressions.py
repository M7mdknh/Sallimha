"""Security Guidance findings on 38796c9 (4x MEDIUM)."""

import pytest
from django.utils import timezone

from core.errors import DomainError
from messaging import outbox
from messaging.models import MessageOutbox, SimulatorControl
from ops.models import Role, Staff
from ops.services import config, opening, staffdir
from tests.factories import make_org, make_staff


def _dead_row(staff, key):
    SimulatorControl.set_next("permanent")
    row = outbox.enqueue("valet.available_ok", staff=staff, template="valet.available_ok", params={}, dedupe_key=key)
    outbox.send_due(timezone.now())
    row.refresh_from_db()
    assert row.status == MessageOutbox.Status.DEAD
    return row


@pytest.mark.whatsapp_staff
def test_replay_of_other_org_dead_letter_forbidden(world):
    other_org = make_org("Other org")
    foreign = _dead_row(make_staff(other_org), "foreign-dead")
    admin = make_staff(world.org, Role.ADMIN)
    with pytest.raises(DomainError) as err:
        opening.replay_dead_letter(admin, foreign)
    assert err.value.code in {"forbidden", "not_found"}
    foreign.refresh_from_db()
    assert foreign.status == MessageOutbox.Status.DEAD


@pytest.mark.whatsapp_staff
def test_opening_dead_letter_count_is_org_scoped(world):
    _dead_row(make_staff(make_org("Other org")), "foreign-dead-2")
    assert opening.opening_check(world.event)["dead_letters"] == 0
    _dead_row(world.valets[0], "own-dead")
    assert opening.opening_check(world.event)["dead_letters"] == 1


@pytest.mark.parametrize("bad", ["{ticket:>99999999} {venue}", "{ticket!r} {venue}", "{ticket.__class__} {venue}",
                                 "{ticket[0]} {venue}", "x" * 2001 + "{ticket}{venue}"])
def test_template_override_rejects_format_specs_and_attribute_access(world, bad):
    admin = make_staff(world.org, Role.ADMIN)
    with pytest.raises(DomainError):
        config.update_templates(admin, world.org, {"guest.ticket": {"ar": bad, "en": "Ticket {ticket} at {venue}."}})


def test_mfa_issue_increments_epoch_from_database_not_stale_copy(world):
    admin = make_staff(world.org, Role.ADMIN)
    manager = world.manager
    stale = Staff.objects.get(pk=manager.pk)
    Staff.objects.filter(pk=manager.pk).update(session_epoch=7)  # changed elsewhere after `stale` was read
    staffdir.issue_mfa_enrolment(admin, stale)
    assert Staff.objects.get(pk=manager.pk).session_epoch == 8
