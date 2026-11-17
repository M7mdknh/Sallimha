"""Three roles and onboarding without shared credentials (ADR-0011)."""

import importlib
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from core.errors import DomainError
from core.models import AuditEvent
from ops.models import AccountSetup, Role, Staff
from ops.services import staffdir
from tests.console.conftest import login_as
from tests.factories import make_staff

PASSWORD = "quiet-harbour-lantern-58"


def post(client, url, data=None):
    return client.post(url, data or {}, format="json", HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex)


def sign_in(username, password, otp=None):
    client = Client(enforce_csrf_checks=False)
    body = {"username": username, "password": password, **({"otp": otp} if otp else {})}
    return client, client.post("/api/auth/login", body, content_type="application/json")


def setup(username, code, password):
    return Client().post("/api/auth/setup", {"username": username, "code": code, "password": password},
                         content_type="application/json")


# --- role consolidation ----------------------------------------------------------------------------------

def test_there_are_exactly_three_roles():
    assert Role.values == ["VALET", "SUPERVISOR", "ADMIN"]


def test_migration_turns_manager_and_super_admin_into_admin_and_keeps_a_record(world):
    migration = importlib.import_module("ops.migrations.0010_three_roles_and_staff_app")
    from django.apps import apps

    manager = make_staff(world.org, Role.ADMIN, name="Was manager")
    owner = make_staff(world.org, Role.ADMIN, name="Was owner")
    Staff.objects.filter(pk=manager.pk).update(role="MANAGER")
    Staff.objects.filter(pk=owner.pk).update(role="SUPER_ADMIN")
    before = {s.pk: s.role for s in Staff.objects.all()}

    migration.consolidate_roles(apps, None)

    after = {s.pk: s.role for s in Staff.objects.all()}
    assert after[manager.pk] == after[owner.pk] == "ADMIN"
    assert {pk: role for pk, role in after.items() if pk not in (manager.pk, owner.pk)} == \
        {pk: role for pk, role in before.items() if pk not in (manager.pk, owner.pk)}  # nobody else changed
    assert after[world.supervisor.pk] == "SUPERVISOR" and after[world.valets[0].pk] == "VALET"
    records = {e.entity_id: e.summary["before"] for e in AuditEvent.objects.filter(action="staff.role_consolidated")}
    assert records == {manager.pk: "MANAGER", owner.pk: "SUPER_ADMIN"}

    migration.restore_roles(apps, None)  # rollback restores exactly what was recorded
    assert Staff.objects.get(pk=manager.pk).role == "MANAGER" and Staff.objects.get(pk=owner.pk).role == "SUPER_ADMIN"
    assert Staff.objects.get(pk=world.admin.pk).role == "ADMIN"


def test_product_admin_is_not_a_framework_superuser(world):
    person = staffdir.create_staff(world.admin, "New admin", "+966551110001", Role.ADMIN)
    assert person.user.is_superuser is False and person.user.is_staff is False


# --- what each role may do -------------------------------------------------------------------------------

ADMIN_ONLY_READS = ["/api/staff", "/api/carryover", "/api/config", "/api/ops/dead-letters",
                    "/api/integrations/whatsapp", "/api/venues", "/api/dashboard"]


@pytest.mark.parametrize("url", ADMIN_ONLY_READS)
def test_what_needed_a_manager_or_above_now_needs_an_admin(world, url):
    assert login_as(world.supervisor).get(url).status_code == 403
    assert login_as(world.admin).get(url).status_code == 200


def test_supervisor_cannot_manage_people_or_approve(world):
    sup = login_as(world.supervisor)
    valet = world.valets[0]
    assert post(sup, "/api/staff", {"full_name": "X", "phone": "+966551110002", "role": "VALET"}).status_code == 403
    assert post(sup, f"/api/staff/{valet.id}/deactivate", {"reason": "x"}).status_code == 403
    assert post(sup, f"/api/staff/{valet.id}/role", {"role": "SUPERVISOR"}).status_code == 403
    assert sup.post(f"/api/staff/{valet.id}/setup-code").status_code == 403
    assert post(sup, f"/api/staff/{valet.id}/team",
                {"event_id": world.event.id, "member": False}).status_code == 403
    assert post(sup, "/api/outages/whatsapp/declare", {"reason": "x"}).status_code == 403
    assert post(sup, f"/api/events/{world.event.id}/close").status_code == 403
    assert sup.get(f"/api/events/{world.event.id}/report").status_code == 403


def test_admin_sees_every_operation_supervisor_only_assigned_ones(world):
    from tests.factories import make_event

    other = make_event(org=world.org, name="Other night")
    assert {e["id"] for e in login_as(world.admin).get("/api/events/").json()} == {world.event.id, other.id}
    assert [e["id"] for e in login_as(world.supervisor).get("/api/events/").json()] == [world.event.id]
    assert login_as(world.supervisor).get(f"/api/events/{other.id}/live").status_code == 404


def test_admin_manages_everyone_but_themselves(world):
    admin = world.admin
    peer = make_staff(world.org, Role.ADMIN, name="Peer")
    staffdir.change_role(admin, world.supervisor, Role.ADMIN)
    staffdir.deactivate(admin, peer, "left")
    with pytest.raises(DomainError, match="forbidden"):
        staffdir.deactivate(admin, admin, "self")
    with pytest.raises(DomainError, match="forbidden"):
        staffdir.change_role(admin, admin, Role.VALET)
    with pytest.raises(DomainError, match="forbidden"):
        staffdir.change_role(world.supervisor.__class__.objects.get(pk=world.valets[0].pk), admin, Role.VALET)


def test_promotion_to_admin_needs_a_second_factor_before_sign_in(world):
    target = staffdir.create_staff(world.admin, "Lead", "+966551110003", Role.SUPERVISOR)
    code = staffdir.issue_setup_code(world.admin, target)
    assert setup("+966551110003", code, PASSWORD).status_code == 200
    _client, ok = sign_in("0551110003", PASSWORD)
    assert ok.json()["role"] == "SUPERVISOR"
    staffdir.change_role(world.admin, target, Role.ADMIN)
    _client, refused = sign_in("0551110003", PASSWORD)
    assert refused.status_code == 400 and refused.json()["code"] == "mfa_enrolment_required"


def test_a_valet_with_a_car_cannot_be_made_a_supervisor(world):
    from ops.services import intake
    from tests.factories import open_shift

    valet = world.valets[0]
    open_shift(world.event, valet, world.supervisor)
    intake.register_with_guest(valet, "+966501234001", "ABC 1234")
    with pytest.raises(DomainError, match="custody_open"):
        staffdir.change_role(world.admin, valet, Role.SUPERVISOR)


# --- onboarding ------------------------------------------------------------------------------------------

def test_admin_adds_a_valet_who_sets_their_own_password_and_reaches_only_the_valet_app(world):
    admin = login_as(world.admin)
    created = post(admin, "/api/staff", {"full_name": "نواف", "phone": "0551110010", "role": "VALET",
                                         "event_id": world.event.id})
    assert created.status_code == 200, created.content
    staff = Staff.objects.get(pk=created.json()["id"])
    assert staff.user.has_usable_password() is False  # nobody, including the admin, knows a password
    assert world.event.assignments.filter(staff=staff).exists()
    row = next(r for r in admin.get("/api/staff").json() if r["id"] == staff.id)
    assert (row["can_sign_in"], row["setup_pending"], row["event_ids"]) == (False, False, [world.event.id])

    issued = admin.post(f"/api/staff/{staff.id}/setup-code")
    assert issued.status_code == 200
    code = issued.json()["setup_code"]
    assert issued.json()["sign_in_name"] == "+966551110010" and len(code) == 8
    assert not AccountSetup.objects.filter(code_hash=code).exists()  # only a keyed hash is stored
    assert code not in str(list(AuditEvent.objects.values_list("summary", flat=True)))

    assert setup("0551110010", code, "short").json()["code"] == "weak_password"
    assert setup("0551110010", code, "stone-91x").status_code == 200  # valets: 8 characters or more
    assert setup("0551110010", code, "another-pass-22").json()["code"] == "setup_invalid"  # single use

    client, signed_in = sign_in("055 111 0010", "stone-91x")
    assert signed_in.status_code == 200 and signed_in.json() == {"ok": True, "role": "VALET"}
    assert client.get("/api/auth/me").json()["role"] == "VALET"
    assert client.get("/api/valet/work").status_code == 200
    assert client.get("/api/events/").status_code == 403


def test_wrong_setup_codes_are_counted_and_the_code_locks(world):
    person = staffdir.create_staff(world.admin, "Sami", "+966551110011", Role.VALET)
    code = staffdir.issue_setup_code(world.admin, person)
    wrong = "00000000" if code != "00000000" else "11111111"
    for _ in range(staffdir.MAX_SETUP_ATTEMPTS):
        with pytest.raises(DomainError, match="setup_invalid"):
            staffdir.complete_setup("+966551110011", wrong, "river-stone-91")
    with pytest.raises(DomainError, match="setup_invalid"):
        staffdir.complete_setup("+966551110011", code, "river-stone-91")  # locked even for the right code
    assert AuditEvent.objects.filter(action="auth.setup_locked", entity_id=person.id).exists()
    fresh = staffdir.issue_setup_code(world.admin, person)  # the admin issues a new one
    assert staffdir.complete_setup("+966551110011", fresh, "river-stone-91").id == person.id


def test_expired_or_replaced_codes_do_not_work(world):
    from datetime import timedelta

    from django.utils import timezone

    person = staffdir.create_staff(world.admin, "Huda", "+966551110012", Role.SUPERVISOR)
    first = staffdir.issue_setup_code(world.admin, person)
    second = staffdir.issue_setup_code(world.admin, person)
    with pytest.raises(DomainError, match="setup_invalid"):
        staffdir.complete_setup("+966551110012", first, PASSWORD)
    with pytest.raises(DomainError, match="setup_invalid"):
        staffdir.complete_setup("+966551110012", second, PASSWORD, now=timezone.now() + timedelta(hours=73))
    with pytest.raises(DomainError, match="weak_password"):
        staffdir.complete_setup("+966551110012", second, "stone-91x")  # supervisors keep the 12-character rule
    assert staffdir.complete_setup("+966551110012", second, PASSWORD).id == person.id


def test_setup_code_is_the_password_reset_and_signs_other_sessions_out(world):
    person = staffdir.create_staff(world.admin, "Rana", "+966551110013", Role.SUPERVISOR)
    staffdir.complete_setup("+966551110013", staffdir.issue_setup_code(world.admin, person), PASSWORD)
    client, _ = sign_in("+966551110013", PASSWORD)
    assert client.get("/api/auth/me").status_code == 200
    staffdir.complete_setup("+966551110013", staffdir.issue_setup_code(world.admin, person), "new-harbour-lantern-77")
    assert client.get("/api/auth/me").status_code == 403  # the old session ended with the reset
    assert sign_in("+966551110013", PASSWORD)[1].status_code == 400
    assert sign_in("+966551110013", "new-harbour-lantern-77")[1].status_code == 200


def test_existing_valet_without_an_account_gets_one_when_a_code_is_issued(world):
    valet = world.valets[0]
    assert valet.user_id is None
    code = staffdir.issue_setup_code(world.admin, valet)
    valet.refresh_from_db()
    assert valet.user.username == valet.phone_e164 and not valet.user.has_usable_password()
    staffdir.complete_setup(valet.phone_e164, code, "river-stone-91")
    assert sign_in(valet.phone_e164, "river-stone-91")[1].json()["role"] == "VALET"


def test_deactivated_person_cannot_finish_setup_or_sign_in(world):
    person = staffdir.create_staff(world.admin, "Omar", "+966551110014", Role.VALET)
    code = staffdir.issue_setup_code(world.admin, person)
    staffdir.deactivate(world.admin, person, "left the team")
    with pytest.raises(DomainError, match="setup_invalid"):
        staffdir.complete_setup("+966551110014", code, "river-stone-91")
    with pytest.raises(DomainError, match="staff_disabled"):
        staffdir.issue_setup_code(world.admin, person)


def test_assignment_gives_and_removes_a_supervisors_scope(world):
    from tests.factories import make_event

    other = make_event(org=world.org, name="Other night")
    admin = login_as(world.admin)
    sup_client = login_as(world.supervisor)
    assert sup_client.get(f"/api/events/{other.id}/live").status_code == 404
    assert post(admin, f"/api/staff/{world.supervisor.id}/team",
                {"event_id": other.id, "member": True}).status_code == 200
    assert sup_client.get(f"/api/events/{other.id}/live").status_code == 200
    assert post(admin, f"/api/staff/{world.supervisor.id}/team",
                {"event_id": other.id, "member": False}).status_code == 200
    assert sup_client.get(f"/api/events/{other.id}/live").status_code == 404


def test_nobody_is_taken_off_a_team_during_their_shift(world):
    from tests.factories import open_shift

    open_shift(world.event, world.valets[0], world.supervisor)
    with pytest.raises(DomainError, match="shift_open"):
        staffdir.set_assignment(world.admin, world.valets[0], world.event, False)


def test_create_staff_no_longer_accepts_a_password(world):
    admin = login_as(world.admin)
    response = post(admin, "/api/staff", {"full_name": "Sara", "phone": "+966551110015", "role": "SUPERVISOR",
                                          "password": "an-admin-chosen-password-1"})
    assert response.status_code == 200
    user = get_user_model().objects.get(username="+966551110015")
    assert not user.has_usable_password() and not user.check_password("an-admin-chosen-password-1")
