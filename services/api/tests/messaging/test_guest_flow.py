import pytest
from django.utils import timezone

from core.errors import DomainError
from messaging.models import MessageOutbox
from ops.models import Alert, GuestBinding, Rating, RetrievalRequest, Ticket
from ops.services import retrieval
from ops.services.ratings import record_rating
from tests.factories import open_shift
from tests.ops.intake_helpers import park, register_and_confirm
from tests.wa import button, last, tap


@pytest.fixture
def ops(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    return world


GUEST = "+966501234567"


def _ticket_msg(ticket):
    return MessageOutbox.objects.get(kind="guest.ticket", ticket=ticket, binding__revoked_at__isnull=True)


def test_early_request_waits_for_parking(ops):
    """AT-04."""
    ticket = register_and_confirm(ops.valets[0], ops.event, GUEST)
    tap(GUEST, button(_ticket_msg(ticket), "request_car"))
    req = RetrievalRequest.objects.get(ticket=ticket)
    assert req.state == "WAITING_FOR_PARKING"
    assert last(binding=ticket.bindings.get()).template == "guest.early_request"


def test_repeat_tap_single_request(ops):
    """AT-10."""
    ticket = park(ops.valets[0], ops.event, GUEST)
    payload = button(_ticket_msg(ticket), "request_car")
    tap(GUEST, payload)
    tap(GUEST, payload)
    tap(GUEST, payload)
    assert RetrievalRequest.objects.filter(ticket=ticket).count() == 1
    assert last(binding=ticket.bindings.get()).template == "guest.duplicate"


def test_queued_message_never_claims_retrieval(ops):
    """AT-38."""
    ticket = park(ops.valets[0], ops.event, GUEST)
    tap(GUEST, button(_ticket_msg(ticket), "request_car"))
    msg = last(binding=ticket.bindings.get(), kind="guest.queued")
    assert msg is not None and "إحضار مركبتك" not in msg.template


def test_forwarded_button_other_sender_rejected(ops):
    """AT-16: a forwarded ticket/button from another account cannot authorize retrieval."""
    ticket = park(ops.valets[0], ops.event, GUEST)
    tap("+966559999999", button(_ticket_msg(ticket), "request_car"))
    assert not RetrievalRequest.objects.filter(ticket=ticket).exists()
    alert = Alert.objects.get(kind="guest_identity_mismatch")
    assert "966559999999" not in str(alert.detail) and "966501234567" not in str(alert.detail)


def test_display_number_text_not_credential(ops):
    ticket = park(ops.valets[0], ops.event, GUEST)
    from tests.wa import say
    say("+966559999999", f"{ticket.display_number:03d}")
    say("+966559999999", "اطلب سيارتي")
    assert not RetrievalRequest.objects.exists()


def test_bsuid_only_sender_binds_via_context(ops):
    ticket = park(ops.valets[0], ops.event, GUEST)
    msg = _ticket_msg(ticket)
    from messaging.outbox import send_due
    send_due(timezone.now())
    msg.refresh_from_db()
    tap(None, button(msg, "request_car"), context_id=msg.provider_message_id, from_user_id="SA.BSUID.1")
    assert RetrievalRequest.objects.filter(ticket=ticket).exists()
    binding = GuestBinding.objects.get(ticket=ticket)
    assert binding.wa_user_id == "SA.BSUID.1" and binding.matched_via == "context_token"


def test_bsuid_only_sender_without_context_rejected(ops):
    ticket = park(ops.valets[0], ops.event, GUEST)
    tap(None, button(_ticket_msg(ticket), "request_car"), from_user_id="SA.BSUID.2")
    assert not RetrievalRequest.objects.exists()


def test_multi_ticket_phone_requires_selection(ops):
    """AT-18."""
    first = park(ops.valets[0], ops.event, GUEST)
    second = park(ops.valets[1], ops.event, GUEST)
    from tests.wa import say
    say(GUEST, "اطلب سيارتي")
    assert not RetrievalRequest.objects.exists()
    selection = MessageOutbox.objects.filter(kind="guest.select_ticket").latest("id")
    assert len(selection.buttons) == 2
    chosen = next(b[0] for b in selection.buttons if b[2]["ticket"] == f"#{second.display_number:03d}")
    tap(GUEST, chosen)
    assert RetrievalRequest.objects.get().ticket == second
    assert first.requests.count() == 0


def test_single_ticket_generic_request_creates_request(ops):
    ticket = park(ops.valets[0], ops.event, GUEST)
    from tests.wa import say
    say(GUEST, "اطلب سيارتي")
    assert RetrievalRequest.objects.get().ticket == ticket


def test_correction_revokes_old_tokens(ops):
    """AT-17."""
    ticket = park(ops.valets[0], ops.event, GUEST)
    old_payload = button(_ticket_msg(ticket), "request_car")
    retrieval.correct_guest_phone(ops.supervisor, ticket, "+966507777777", "typo at intake")
    tap(GUEST, old_payload)
    assert not RetrievalRequest.objects.exists()
    ticket.refresh_from_db()
    assert ticket.contact_state == Ticket.Contact.CORRECTION_REQUIRED
    tap("+966507777777", button(_ticket_msg(ticket), "request_car"))
    assert RetrievalRequest.objects.filter(ticket=ticket).count() == 1
    with pytest.raises(DomainError):
        retrieval.correct_guest_phone(ops.valets[0], ticket, "+966508888888", "valet cannot")


def test_withdraw_queued_keeps_parked(ops):
    """AT-54."""
    ticket = park(ops.valets[0], ops.event, GUEST)
    tap(GUEST, button(_ticket_msg(ticket), "request_car"))
    req = RetrievalRequest.objects.get()
    retrieval.withdraw_request(ops.supervisor, req, "guest asked to wait")
    req.refresh_from_db()
    ticket.refresh_from_db()
    assert req.state == "WITHDRAWN" and ticket.state == Ticket.State.PARKED
    assert last(binding=ticket.bindings.get()).template == "guest.withdrawn"
    tap(GUEST, button(_ticket_msg(ticket), "request_car"))
    assert RetrievalRequest.objects.filter(ticket=ticket, state="QUEUED").count() == 1
    with pytest.raises(DomainError):
        retrieval.withdraw_request(ops.valets[1], RetrievalRequest.objects.get(state="QUEUED"), "no")


def _delivered(ops):
    ticket = park(ops.valets[0], ops.event, GUEST)
    Ticket.objects.filter(pk=ticket.pk).update(state="DELIVERED", delivered_at=timezone.now(),
                                               delivered_by=ops.valets[1])
    ticket.refresh_from_db()
    return ticket


@pytest.mark.parametrize(("value", "praise", "alert"), [("EXCELLENT", True, False), ("OKAY", False, False),
                                                       ("POOR", False, True)])
def test_ratings_routing(ops, value, praise, alert):
    """AT-23."""
    ticket = _delivered(ops)
    binding = ticket.bindings.get()
    record_rating(binding, ticket, value, source_message_id=f"wamid.r.{value}")
    assert Rating.objects.get(ticket=ticket).delivering_valet == ops.valets[1]
    assert MessageOutbox.objects.filter(kind="valet.praise", staff=ops.valets[1]).exists() is praise
    assert Alert.objects.filter(kind="poor_rating", ticket=ticket).exists() is alert
    record_rating(binding, ticket, "POOR", source_message_id="wamid.r.again")
    assert Rating.objects.filter(ticket=ticket).count() == 1
