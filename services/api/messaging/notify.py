"""Business-event notifications. Each function enqueues outbox rows inside the caller's transaction."""


def shift_started(shift) -> None:
    """Invite the valet to tap «جاهز». Implemented with the valet WhatsApp flow (Task 1.4)."""
