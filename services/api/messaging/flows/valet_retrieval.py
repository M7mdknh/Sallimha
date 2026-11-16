"""Valet retrieval, handover and relocation interactions (ADR-0006, ADR-0007): offers, ready, code, delivered,
custody, and supervisor-initiated moves."""

from core.errors import DomainError
from core.phone import normalize_digits
from ops.models import ParkingZone
from ops.services import custody, dispatch, handover, relocation


def _set(conv, step, ticket=None, **data):
    from messaging.flows.valet import _set as set_step

    set_step(conv, step, ticket, **data)


def _accept(staff, conv, token, reply):
    outcome = dispatch.accept_task(staff, reply.inb.button_payload)
    if outcome == "accepted":
        _set(conv, "retrieving", token.ticket)
    else:
        reply("valet.duplicate" if outcome == "duplicate" else "valet.stale")


def _decline(staff, conv, token, reply):
    outcome = dispatch.decline_task(staff, reply.inb.button_payload)
    reply("valet.offer_released" if outcome == "declined" else "valet.stale")


def _car_ready(staff, conv, token, reply):
    outcome = handover.mark_ready(staff, reply.inb.button_payload)
    if outcome == "ready":
        _set(conv, "awaiting_code", token.ticket)
        reply("valet.ask_code", ticket=token.ticket)
    else:
        reply("valet.duplicate" if outcome == "duplicate" else "valet.stale")


def _delivered(staff, conv, token, reply):
    outcome = handover.complete_handover(staff, reply.inb.button_payload)
    if outcome == "delivered":
        _set(conv, "idle")
    elif outcome == "blocked":
        reply("valet.handover_blocked", ticket=token.ticket)
    else:
        reply("valet.duplicate" if outcome == "duplicate" else "valet.stale")


def _ack_custody(staff, conv, token, reply):
    from ops.models import CustodyTransfer, Ticket

    transfer = CustodyTransfer.objects.get(pk=token.data["transfer_id"])
    custody.acknowledge_custody(staff, transfer)
    ticket = Ticket.objects.get(pk=transfer.ticket_id)
    if ticket.state == Ticket.State.READY:
        _set(conv, "awaiting_code", ticket)
        reply("valet.ask_code", ticket=ticket)
    else:
        _set(conv, "retrieving", ticket)


def _relocation_accept(staff, conv, token, reply):
    outcome = relocation.accept_relocation(staff, reply.inb.button_payload)
    if outcome == "accepted":
        _set(conv, "relocating", token.ticket)
    else:
        reply("valet.duplicate" if outcome == "duplicate" else "valet.stale")


def _relocation_decline(staff, conv, token, reply):
    outcome = relocation.decline_relocation(staff, reply.inb.button_payload)
    reply("valet.offer_released" if outcome == "declined" else "valet.stale")


def _relocation_moved(staff, conv, token, reply):
    from messaging.flows.valet import _zones

    task = relocation.mover_task(staff, reply.inb.button_payload)
    if task is None:
        return reply("valet.stale")
    _set(conv, "relocation_location", task.ticket, task_id=task.id)
    return reply("valet.ask_location", ticket=task.ticket, zones=_zones(task.ticket))


BUTTON_HANDLERS = {
    "relocation_accept": _relocation_accept,
    "relocation_decline": _relocation_decline,
    "relocation_moved": _relocation_moved,
    "valet_accept": _accept,
    "valet_decline": _decline,
    "valet_car_ready": _car_ready,
    "valet_delivered": _delivered,
    "ack_retrieval_custody": _ack_custody,
}


def _relocation_text(staff, conv, text, reply) -> None:
    from ops.models import Task

    task = Task.objects.filter(pk=conv.data.get("task_id"), assignee=staff).first()
    if task is None:
        _set(conv, "idle")
        return reply("valet.stale")
    if conv.step == "relocation_location":
        parts = normalize_digits(text).split(maxsplit=1)
        if not parts or not ParkingZone.objects.filter(venue_id=task.event.venue_id, code__iexact=parts[0],
                                                       active=True).exists():
            raise DomainError("zone_invalid")
        _set(conv, "relocation_hook", task.ticket, task_id=task.id, zone=parts[0],
             detail=parts[1] if len(parts) > 1 else "")
        return reply("valet.ask_hook", ticket=task.ticket)
    digits = normalize_digits(text).strip()
    if not digits.isdigit():
        raise DomainError("hook_invalid")
    relocation.complete_relocation(staff, task, zone_code=conv.data["zone"], detail=conv.data.get("detail", ""),
                                   hook_number=int(digits))
    _set(conv, "idle")
    return None


def handle_text(staff, conv, text, reply) -> bool:
    if conv.step in {"relocation_location", "relocation_hook"} and conv.ticket is not None:
        _relocation_text(staff, conv, text, reply)
        return True
    if conv.step != "awaiting_code" or conv.ticket is None:
        return False
    outcome, remaining = handover.verify_collection(staff, conv.ticket, text)
    if outcome == "wrong":
        reply("valet.code_wrong", remaining=remaining)
    elif outcome == "locked":
        reply("valet.code_locked")
    elif outcome == "stale":
        reply("valet.stale")
    return True
