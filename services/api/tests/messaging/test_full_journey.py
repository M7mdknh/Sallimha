"""Whole journey through simulated WhatsApp webhooks and the real worker pass (SIMULATED)."""

from core import worker
from messaging.models import SimulatedMessage
from ops.models import Rating, Ticket
from tests.factories import open_shift
from tests.wa import button, last, photo, say, tap

GUEST = "+966501234567"


def _code_from_simulated(ticket):
    worker.run_once(worker_id="journey")
    body = SimulatedMessage.objects.filter(phone=GUEST, direction="out").order_by("-id").values_list("body", flat=True)
    for text in body:
        for tok in text.replace(".", " ").split():
            if tok.isdigit() and len(tok) == 6:
                return tok
    raise AssertionError("no code delivered")


def test_registration_to_rating_end_to_end(world):
    valet = world.valets[0]
    open_shift(world.event, valet, world.supervisor)
    p = valet.phone_e164
    say(p, "مركبة جديدة")
    say(p, "0501234567")
    tap(p, button(last(valet), "confirm_phone"))
    tap(p, button(last(valet), "receipt_yes"))
    say(p, "ABC 1234")
    for _ in range(4):
        photo(p)
    tap(p, button(last(valet), "start_parking"))
    say(p, "A 3")
    say(p, "9")
    ticket = Ticket.objects.get()
    binding = ticket.bindings.get()
    tap(GUEST, button(last(binding=binding, kind="guest.ticket"), "request_car"))
    worker.run_once(worker_id="journey")  # dispatch + send offer
    tap(p, button(last(valet, kind="valet.offer"), "accept"))
    tap(p, button(last(valet, kind="valet.assigned"), "car_ready"))
    code = _code_from_simulated(ticket)
    say(p, "000000" if code != "000000" else "111111")
    assert last(valet).template == "valet.code_wrong"
    say(p, code)
    tap(p, button(last(valet, kind="valet.code_ok"), "delivered"))
    ticket.refresh_from_db()
    assert ticket.state == Ticket.State.DELIVERED
    tap(GUEST, button(last(binding=binding, kind="guest.delivered"), "rate_excellent"))
    assert Rating.objects.get(ticket=ticket).value == "EXCELLENT"
    assert last(valet, kind="valet.praise") is not None
    worker.run_once(worker_id="journey")
    assert SimulatedMessage.objects.filter(direction="out").count() >= 15
