"""Valet retrieval and handover interactions (ADR-0006): offers, ready, code, delivered, custody."""

from ops.services import custody, dispatch, handover


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


BUTTON_HANDLERS = {
    "valet_accept": _accept,
    "valet_decline": _decline,
    "valet_car_ready": _car_ready,
    "valet_delivered": _delivered,
    "ack_retrieval_custody": _ack_custody,
}


def handle_text(staff, conv, text, reply) -> bool:
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
