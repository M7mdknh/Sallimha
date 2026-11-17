"""Admin credentials are never reset from the app (ADR-0012). Valets and supervisors keep routine onboarding and
reset by an admin; an admin's sign-in is set up or recovered only by the controlled procedure, which names two
people, resets password and second factor together and leaves a record every admin sees on the Team page."""

import io
import uuid

import pyotp
import pytest
from django.core.management import CommandError, call_command
from django.test import Client

from core.errors import DomainError
from core.models import AuditEvent
from ops.models import AccountSetup, Role, Staff
from ops.services import staffdir
from tests.console.conftest import login_as
from tests.factories import make_org, make_staff

PASSWORD = "quiet-harbour-lantern-58"
OTHER = "amber-courtyard-window-31"


def post(client, url, data=None):
    return client.post(url, data or {}, format="json", HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex)


def sign_in(username, password, otp=None):
    client = Client()
    body = {"username": username, "password": password, **({"otp": otp} if otp else {})}
    return client, client.post("/api/auth/login", body, content_type="application/json")


def person(world, name, phone, role):
    """Someone who set their own password with a code from the admin (supervisor first: admins are promoted)."""
    staff = staffdir.create_staff(world.admin, name, phone, Role.SUPERVISOR)
    staffdir.complete_setup(phone, staffdir.issue_setup_code(world.admin, staff), PASSWORD)
    if role == Role.ADMIN:
        staffdir.change_role(world.admin, staff, Role.ADMIN)
    staff.refresh_from_db()
    return staff


def grant(target, requested_by, approved_by, reason="lost phone, identity checked in person"):
    return staffdir.grant_admin_access(target, requested_by=requested_by, approved_by=approved_by, reason=reason,
                                       operator="on-call technical owner")


# --- normal staff management ------------------------------------------------------------------------------

def test_an_admin_cannot_issue_a_setup_code_for_another_admin(world):
    peer = person(world, "Peer", "+966551120001", Role.ADMIN)
    with pytest.raises(DomainError, match="admin_access_procedure"):
        staffdir.issue_setup_code(world.admin, peer)
    refused = login_as(world.admin).post(f"/api/staff/{peer.id}/setup-code")
    assert refused.status_code == 409 and refused.json()["code"] == "admin_access_procedure"
    assert not AccountSetup.objects.filter(staff=peer, used_at__isnull=True, revoked_at__isnull=True).exists()


def test_the_app_has_no_second_factor_reset_for_anyone(world):
    peer = person(world, "Peer", "+966551120002", Role.ADMIN)
    assert login_as(world.admin).post(f"/api/staff/{peer.id}/mfa").status_code == 404
    assert not hasattr(staffdir, "issue_mfa_enrolment")


@pytest.mark.parametrize("role", [Role.VALET, Role.SUPERVISOR])
def test_valets_and_supervisors_keep_routine_onboarding_and_reset(world, role):
    staff = staffdir.create_staff(world.admin, "Routine", "+966551120003", role)
    admin = login_as(world.admin)
    first = admin.post(f"/api/staff/{staff.id}/setup-code")
    assert first.status_code == 200
    staffdir.complete_setup("+966551120003", first.json()["setup_code"], PASSWORD)
    reset = admin.post(f"/api/staff/{staff.id}/setup-code")
    assert reset.status_code == 200
    staffdir.complete_setup("+966551120003", reset.json()["setup_code"], OTHER)
    assert sign_in("+966551120003", OTHER)[1].status_code == 200


def test_promotion_to_admin_cancels_a_code_issued_before_it(world):
    staff = staffdir.create_staff(world.admin, "Lead", "+966551120004", Role.SUPERVISOR)
    code = staffdir.issue_setup_code(world.admin, staff)
    staffdir.change_role(world.admin, staff, Role.ADMIN)
    with pytest.raises(DomainError, match="setup_invalid"):
        staffdir.complete_setup("+966551120004", code, PASSWORD)


def test_demote_reset_and_promote_again_does_not_give_one_admin_another_admins_access(world):
    """The detour around the rule: demote a peer, reset them as a supervisor, promote them back."""
    peer = person(world, "Peer", "+966551120005", Role.ADMIN)
    staffdir.change_role(world.admin, peer, Role.SUPERVISOR)
    staffdir.complete_setup("+966551120005", staffdir.issue_setup_code(world.admin, peer), OTHER)  # admin knows it
    staffdir.change_role(world.admin, peer, Role.ADMIN)
    _client, refused = sign_in("+966551120005", OTHER)
    assert refused.status_code == 400 and refused.json()["code"] == "mfa_enrolment_required"  # no admin sign-in
    approver = person(world, "Approver", "+966551120006", Role.SUPERVISOR)
    code, uri = grant(peer, requested_by=world.admin, approved_by=approver)
    assert sign_in("+966551120005", OTHER)[1].status_code == 400  # the password the first admin chose is gone
    staffdir.complete_setup("+966551120005", code, PASSWORD)
    _client, step = sign_in("+966551120005", PASSWORD)
    assert step.json() == {"ok": False, "mfa_required": True}
    _client, ok = sign_in("+966551120005", PASSWORD, pyotp.TOTP(pyotp.parse_uri(uri).secret).now())
    assert ok.json() == {"ok": True, "role": "ADMIN"}


# --- the controlled procedure -----------------------------------------------------------------------------

def test_controlled_access_needs_a_reason_and_two_different_people(world):
    target = person(world, "Target", "+966551120007", Role.ADMIN)
    approver = person(world, "Approver", "+966551120008", Role.SUPERVISOR)
    stranger = make_staff(make_org("Elsewhere"), Role.ADMIN, name="Stranger")
    refusals = [
        ({"requested_by": world.admin, "approved_by": world.admin}, "approver_must_differ"),
        ({"requested_by": world.admin, "approved_by": target}, "approver_must_differ"),
        ({"requested_by": world.supervisor, "approved_by": approver}, "requester_not_admin"),
        ({"requested_by": stranger, "approved_by": approver}, "requester_not_admin"),
        ({"requested_by": world.admin, "approved_by": world.valets[0]}, "approver_not_authorized"),
        ({"requested_by": world.admin, "approved_by": stranger}, "approver_not_authorized"),
    ]
    for people, code in refusals:
        with pytest.raises(DomainError, match=code):
            grant(target, **people)
    with pytest.raises(DomainError, match="reason_required"):
        grant(target, requested_by=world.admin, approved_by=approver, reason="  ")
    with pytest.raises(DomainError, match="not_admin"):
        grant(approver, requested_by=world.admin, approved_by=world.supervisor)
    assert not AuditEvent.objects.filter(action="staff.admin_access").exists()


def test_controlled_access_resets_password_and_second_factor_together_and_ends_sessions(world):
    target = person(world, "Target", "+966551120009", Role.ADMIN)
    approver = person(world, "Approver", "+966551120010", Role.SUPERVISOR)
    _code, uri = grant(target, requested_by=target, approved_by=approver, reason="first admin access")
    staffdir.complete_setup("+966551120009", _code, PASSWORD)
    old_totp = pyotp.TOTP(pyotp.parse_uri(uri).secret)
    client, ok = sign_in("+966551120009", PASSWORD, old_totp.now())
    assert ok.json()["ok"] is True and client.get("/api/auth/me").status_code == 200

    code, new_uri = grant(target, requested_by=world.admin, approved_by=approver)  # e.g. a lost phone
    assert client.get("/api/auth/me").status_code == 403  # every session of the old credentials ended
    assert sign_in("+966551120009", PASSWORD)[1].status_code == 400  # old password gone
    staffdir.complete_setup("+966551120009", code, OTHER)
    assert sign_in("+966551120009", OTHER, old_totp.now())[1].json()["code"] == "mfa_invalid"  # old factor gone
    new_totp = pyotp.TOTP(pyotp.parse_uri(new_uri).secret)
    assert sign_in("+966551120009", OTHER, new_totp.now())[1].json() == {"ok": True, "role": "ADMIN"}

    record = AuditEvent.objects.filter(action="staff.admin_access", entity_id=target.id).latest("id")
    assert record.summary["requested_by"] == world.admin.id and record.summary["approved_by"] == approver.id
    assert record.summary["reason"] and record.summary["operator"] == "on-call technical owner"
    assert code not in str(record.summary) and new_uri not in str(record.summary)


def test_controlled_access_unlocks_a_locked_second_factor(world):
    target = person(world, "Target", "+966551120011", Role.ADMIN)
    Staff.objects.filter(pk=target.pk).update(mfa_failures=5, mfa_locked_at=target.created_at)
    code, uri = grant(target, requested_by=target, approved_by=world.supervisor)
    staffdir.complete_setup("+966551120011", code, PASSWORD)
    totp = pyotp.TOTP(pyotp.parse_uri(uri).secret)
    assert sign_in("+966551120011", PASSWORD, totp.now())[1].json()["ok"] is True


def test_first_admin_only_when_nobody_else_could_approve(world):
    target = person(world, "Target", "+966551120012", Role.ADMIN)
    with pytest.raises(DomainError, match="other_admins_exist"):
        staffdir.grant_admin_access(target, requested_by=None, approved_by=None, first_admin=True,
                                    reason="new deployment", operator="tech")
    org = make_org("Fresh deployment")
    first = make_staff(org, Role.ADMIN, name="First")
    code, uri = staffdir.grant_admin_access(first, requested_by=None, approved_by=None, first_admin=True,
                                            reason="new deployment", operator="tech")
    assert code and uri.startswith("otpauth://")
    assert AuditEvent.objects.get(action="staff.admin_access", entity_id=first.id).summary["first_admin"] is True


def test_every_admin_sees_the_last_controlled_access_on_the_team_page(world):
    target = person(world, "Target", "+966551120013", Role.ADMIN)
    approver = person(world, "Approver", "+966551120014", Role.SUPERVISOR)
    row = next(r for r in login_as(world.admin).get("/api/staff").json() if r["id"] == target.id)
    assert row["admin_access"] is None
    grant(target, requested_by=world.admin, approved_by=approver)
    row = next(r for r in login_as(world.admin).get("/api/staff").json() if r["id"] == target.id)
    access = row["admin_access"]
    assert (access["requested_by"], access["approved_by"], access["first_admin"]) == ("Admin", "Approver", False)
    assert access["at"] and access["reason"]


def test_the_server_command_runs_the_same_rules_and_shows_the_secrets_once(world):
    target = person(world, "Target", "+966551120015", Role.ADMIN)
    approver = person(world, "Approver", "+966551120016", Role.SUPERVISOR)
    with pytest.raises(CommandError, match="approver_must_differ"):
        call_command("admin_access", target.user.username, requested_by=target.user.username,
                     approved_by=target.user.username, reason="test", operator="tech", stdout=io.StringIO())
    assert not AuditEvent.objects.filter(action="staff.admin_access").exists()
    out = io.StringIO()
    call_command("admin_access", target.user.username, requested_by=target.user.username,
                 approved_by=approver.user.username, reason="locked out", operator="tech", stdout=out)
    printed = out.getvalue()
    assert "otpauth://" in printed
    code = next(line.split()[-1] for line in printed.splitlines() if "setup code" in line.lower())
    assert staffdir.complete_setup("+966551120015", code, PASSWORD).id == target.id
