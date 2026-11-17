"""Server-side role and event-scope checks (docs/02). UI hiding is never authorization."""

from core.errors import DomainError
from ops.models import ROLE_RANK, EventAssignment, Role


def has_role(staff, minimum: str) -> bool:
    return bool(staff and staff.enabled and ROLE_RANK[staff.role] >= ROLE_RANK[minimum])


def can_access_event(staff, event) -> bool:
    if not staff or not staff.enabled or staff.org_id != event.org_id:
        return False
    if ROLE_RANK[staff.role] >= ROLE_RANK[Role.ADMIN]:
        return True
    if staff.role == Role.SUPERVISOR:
        return EventAssignment.objects.filter(event=event, staff=staff).exists()
    return False


def require(staff, minimum: str, event=None) -> None:
    if not has_role(staff, minimum):
        raise DomainError("forbidden")
    if event is not None and not can_access_event(staff, event):
        raise DomainError("forbidden")


def actor_label(staff) -> str:
    return f"{staff.role}:{staff.id}" if staff else "system"
