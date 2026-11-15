import pytest
from django.utils import timezone

from core.errors import DomainError
from ops.models import Alert, Role, Staff, Task
from ops.services import staffdir
from tests.factories import make_staff, make_ticket, open_shift

PASSWORD = "a-strong-console-pass-77"


def test_manager_cannot_grant_manager_or_above(world):
    """AT-45."""
    with pytest.raises(DomainError) as err:
        staffdir.create_staff(world.manager, "New Manager", "+966551112233", Role.MANAGER, username="m2",
                              password=PASSWORD)
    assert err.value.code == "forbidden"
    sup = staffdir.create_staff(world.manager, "New Supervisor", "+966551112234", Role.SUPERVISOR, username="s2",
                                password=PASSWORD)
    assert sup.user.check_password(PASSWORD)
    with pytest.raises(DomainError):
        staffdir.change_role(world.manager, sup, Role.MANAGER)


def test_admin_grants_up_to_manager(world):
    admin = make_staff(world.org, Role.ADMIN)
    staffdir.change_role(admin, world.supervisor, Role.MANAGER)
    world.supervisor.refresh_from_db()
    assert world.supervisor.role == Role.MANAGER
    with pytest.raises(DomainError):
        staffdir.change_role(admin, world.supervisor, Role.ADMIN)


def test_cannot_change_own_role(world):
    admin = make_staff(world.org, Role.ADMIN)
    with pytest.raises(DomainError):
        staffdir.change_role(admin, admin, Role.SUPER_ADMIN)


def test_last_super_admin_protected(world):
    root = make_staff(world.org, Role.SUPER_ADMIN)
    with pytest.raises(DomainError) as err:
        staffdir.deactivate(root, root, "leaving")
    assert err.value.code in {"last_super_admin", "forbidden"}
    second = make_staff(world.org, Role.SUPER_ADMIN)
    staffdir.change_role(second, root, Role.ADMIN)
    with pytest.raises(DomainError) as err:
        staffdir.change_role(second, second, Role.ADMIN)
    assert err.value.code in {"last_super_admin", "forbidden"}


def test_deactivate_not_delete_keeps_history(world):
    valet = world.valets[0]
    staffdir.deactivate(world.manager, valet, "Left the company")
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
    staffdir.deactivate(world.manager, valet, "Account compromised")
    task.refresh_from_db()
    assert task.status == "ACCEPTED" and task.assignee == valet
    assert Alert.objects.filter(kind="custody_exception", event=world.event, severity="critical").exists()


def test_deactivated_console_user_cannot_sign_in(world):
    from rest_framework.test import APIClient
    sup = staffdir.create_staff(world.manager, "Temp Sup", "+966551112235", Role.SUPERVISOR, username="temp",
                                password=PASSWORD)
    staffdir.deactivate(world.manager, sup, "Contract ended")
    resp = APIClient().post("/api/auth/login", {"username": "temp", "password": PASSWORD}, format="json")
    assert resp.status_code == 400
