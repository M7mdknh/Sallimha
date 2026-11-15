"""Business-event notifications. Each function enqueues outbox rows inside the caller's transaction."""

from messaging import outbox


def _t(ticket) -> str:
    return f"#{ticket.display_number:03d}"


def shift_started(shift) -> None:
    from ops.services import tokens

    ready = tokens.issue("valet_ready", staff=shift.staff)
    away = tokens.issue("valet_unavailable", staff=shift.staff)
    outbox.enqueue("valet.shift_started", staff=shift.staff, template="valet.shift_started",
                   params={"event": shift.event.name}, buttons=[(ready, "ready"), (away, "unavailable")],
                   dedupe_key=f"valet.shift_started:{shift.id}")


def intake_transferred(transfer) -> None:
    from ops.services import tokens

    ack = tokens.issue("ack_custody", staff=transfer.to_staff, ticket=transfer.ticket,
                       data={"transfer_id": transfer.id})
    outbox.enqueue("valet.custody_assigned", staff=transfer.to_staff, ticket=transfer.ticket,
                   template="valet.custody_assigned",
                   params={"ticket": _t(transfer.ticket), "vehicle_location": transfer.vehicle_location,
                           "key_location": transfer.key_location},
                   buttons=[(ack, "ack_custody")], dedupe_key=f"valet.custody_assigned:{transfer.id}")
