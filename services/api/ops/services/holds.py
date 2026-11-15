"""Safety holds (docs/02). The hold model arrives in Task 2.1; until then nothing is held."""


def dispatch_blocked_ticket_ids(event) -> set[int]:
    return set()


def handover_blocked(ticket) -> bool:
    return False


def on_delivered(ticket) -> None:
    """Hook for incidents/holds bookkeeping after a verified delivery (Task 2.1)."""


def brief(ticket) -> list[dict]:
    return []


def allowed_actions(ticket) -> list[str]:
    return []
