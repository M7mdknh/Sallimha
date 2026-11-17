import pytest
from django.utils import timezone

from core.errors import DomainError
from ops.models import Alert, Role, Staff, Task
from ops.services import staffdir
from tests.factories import make_staff, make_ticket, onboard, open_shift

PASSWORD = "a-strong-console-pass-77"


def test_only_admins_grant_roles(world):
    """AT-45 after ADR-0011: supervisors and valets grant nothing; an admin grants any of the three roles."""
    for actor in (world.supervisor, world.valets[0]):
        with pytest.raises(DomainError) as err:
            staffdir.create_staff(actor, "New Supervisor", "+966551112233", Role.SUPERVISOR)
        assert err.value.code == "forbidden"
        with pytest.raises(DomainError):
            staffdir.change_role(actor, world.valets[1], Role.SUPERVISOR)
    sup = staffdir.create_staff(world.admin, "New Supervisor", "+966551112234", Role.SUPERVISOR)
    assert sup.user.has_usable_password() is False  # the admin never chooses or sees a password
    staffdir.change_role(world.admin, sup, Role.ADMIN)
    sup.refresh_from_db()
    assert sup.role == Role.ADMIN


def test_retired_roles_cannot_be_granted(world):
    for retired in ("MANAGER", "SUPER_ADMIN"):
        with pytest.raises(DomainError):
            staffdir.change_role(world.admin, world.supervisor, retired)


def test_cannot_change_own_role(world):
    with pytest.raises(DomainError):
        staffdir.change_role(world.admin, world.admin, Role.SUPERVISOR)


def test_an_admin_cannot_remove_themselves_so_one_always_remains(world):
    with pytest.raises(DomainError) as err:
        staffdir.deactivate(world.admin, world.admin, "leaving")
    assert err.value.code in {"last_admin", "forbidden"}
    second = make_staff(world.org, Role.ADMIN)
    staffdir.change_role(second, world.admin, Role.SUPERVISOR)
    with pytest.raises(DomainError) as err:
        staffdir.change_role(second, second, Role.SUPERVISOR)
    assert err.value.code in {"last_admin", "forbidden"}
    assert Staff.objects.filter(org=world.org, role=Role.ADMIN, enabled=True).count() == 1


def test_deactivate_not_delete_keeps_history(world):
    valet = world.valets[0]
    staffdir.deactivate(world.admin, valet, "Left the company")
    valet.refresh_from_db()
    assert not valet.enabled and valet.deactivated_at is not None
    assert Staff.objects.filter(pk=valet.pk).exists()
    assert not hasattr(staffdir, "delete_staff")


def test_deactivation_with_custody_opens_exception(world):
    """AT-19 (deactivation part): never silently mark them free."""
    valet = world.valets[0]
    open_shift(world.event, valet, world.supervisor)
    task = Task.objects.create(event=world.event, ticket=make_ticket(world.event, valet), type="INTAKE",
                               status="ACCEPTED", assignee=valet, reserved_at=timezone.now())
    staffdir.deactivate(world.admin, valet, "Account compromised")
    task.refresh_from_db()
    assert task.status == "ACCEPTED" and task.assignee == valet
    assert Alert.objects.filter(kind="custody_exception", event=world.event, severity="critical").exists()


def test_deactivated_person_cannot_sign_in(world):
    from rest_framework.test import APIClient

    sup = onboard(world.admin, "Temp Sup", "+966551112235", Role.SUPERVISOR, PASSWORD, username="temp")
    assert APIClient().post("/api/auth/login", {"username": "temp", "password": PASSWORD},
                            format="json").status_code == 200
    staffdir.deactivate(world.admin, sup, "Contract ended")
    resp = APIClient().post("/api/auth/login", {"username": "temp", "password": PASSWORD}, format="json")
    assert resp.status_code == 400
