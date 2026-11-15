"""Valet retrieval and handover interactions (ADR-0006): offers, ready, code, delivered."""

from ops.services import dispatch


def _accept(staff, conv, token, reply):
    from messaging.flows.valet import _set

    outcome = dispatch.accept_task(staff, reply.inb.button_payload)
    if outcome == "accepted":
        _set(conv, "retrieving", token.ticket, task_id=token.task_id)
    elif outcome == "duplicate":
        reply("valet.duplicate")
    else:
        reply("valet.stale")


def _decline(staff, conv, token, reply):
    outcome = dispatch.decline_task(staff, reply.inb.button_payload)
    reply("valet.offer_released" if outcome == "declined" else "valet.stale")


BUTTON_HANDLERS = {
    "valet_accept": _accept,
    "valet_decline": _decline,
}


def handle_text(staff, conv, text, reply) -> bool:
    return False
