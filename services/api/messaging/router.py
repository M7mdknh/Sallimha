"""Routes an inbound message to the valet or guest conversation flow."""

from messaging.parse import Inbound


def route(inb: Inbound) -> None:
    from messaging.flows import guest, valet

    staff = valet.find_staff(inb)
    if staff is not None:
        valet.handle(staff, inb)
    else:
        guest.handle(inb)
