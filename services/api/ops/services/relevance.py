"""Which queued messages are still true when the worker can finally send them (ADR-0010). A row whose message is
no longer true becomes OBSOLETE instead of being delivered late."""

from django.utils import timezone

from messaging import hooks
from ops.models import Task, Ticket

ACTIVE = (Ticket.State.RECEIVED, Ticket.State.PARKED, Ticket.State.RETRIEVING, Ticket.State.READY)


def _task(row):
    return Task.objects.filter(pk=row.task_id).first() if row.task_id else None


def _offer_open(row) -> bool:
    task = _task(row)
    deadline = task and (task.hard_deadline or task.offer_deadline)
    return bool(task and task.status == Task.Status.OFFERED and task.assignee_id == row.staff_id
                and (deadline is None or timezone.now() <= deadline or row.created_at >= timezone.now()))


def _accepted(row) -> bool:
    task = _task(row)
    return bool(task and task.status == Task.Status.ACCEPTED and task.assignee_id == row.staff_id)


def _ticket_in(*states):
    def check(row) -> bool:
        return bool(row.ticket_id and Ticket.objects.filter(pk=row.ticket_id, state__in=states).exists())
    return check


def _code_still_valid(row) -> bool:
    ticket = Ticket.objects.filter(pk=row.ticket_id).first() if row.ticket_id else None
    return bool(ticket and ticket.state == Ticket.State.READY and
                ticket.codes.filter(consumed_at__isnull=True, revoked_at__isnull=True).exists())


def _binding_active(row) -> bool:
    return bool(_ticket_in(*ACTIVE)(row) and row.binding_id and row.binding.revoked_at is None)


def register() -> None:
    hooks.register("valet.offer", relevant=lambda row: _task(row) is not None and _task(row).status == "OFFERED")
    hooks.register("valet.relocation_offer", relevant=lambda row: _task(row) is not None and
                   _task(row).status == "OFFERED")
    hooks.register("valet.assigned", relevant=_accepted)
    hooks.register("valet.relocation_accepted", relevant=_accepted)
    hooks.register("guest.accepted", relevant=_ticket_in(Ticket.State.RETRIEVING))
    hooks.register("guest.ready", relevant=_code_still_valid)
    hooks.register("guest.parked", relevant=_ticket_in(Ticket.State.PARKED))
    hooks.register("guest.ticket", relevant=_binding_active)
