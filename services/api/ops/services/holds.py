"""Safety holds (docs/02). The hold model arrives in Task 2.1; until then nothing is held."""


def dispatch_blocked_ticket_ids(event) -> set[int]:
    return set()


def handover_blocked(ticket) -> bool:
    return False
