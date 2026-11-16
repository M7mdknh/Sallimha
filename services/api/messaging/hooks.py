"""Post-send callbacks registered by domain modules, keyed by outbox kind."""

from collections.abc import Callable

_on_sent: dict[str, Callable] = {}
_on_failed: dict[str, Callable] = {}
_relevant: dict[str, Callable] = {}


def register(kind: str, *, sent: Callable | None = None, failed: Callable | None = None,
             relevant: Callable | None = None) -> None:
    if sent:
        _on_sent[kind] = sent
    if failed:
        _on_failed[kind] = failed
    if relevant:
        _relevant[kind] = relevant


def still_relevant(row) -> bool:
    """Checked just before a send: a message that is no longer true (an expired offer, a code for a car already
    handed over) is never delivered late (ADR-0010)."""
    check = _relevant.get(row.kind)
    return True if check is None else bool(check(row))


def on_sent(row) -> None:
    handler = _on_sent.get(row.kind)
    if handler:
        handler(row)


def on_failed(row) -> None:
    handler = _on_failed.get(row.kind)
    if handler:
        handler(row)
