"""Routes an inbound message to the guest conversation (or, in the retired staff channel, the valet's)."""

from messaging.parse import Inbound


def route(inb: Inbound) -> None:
    from core.context import staff_app
    from messaging.flows import guest, valet

    if staff_app():
        return guest.handle(inb)  # ADR-0011: WhatsApp is the customers' channel; staff work in the app
    staff = valet.find_staff(inb)
    if staff is not None:
        valet.handle(staff, inb)
    else:
        guest.handle(inb)
