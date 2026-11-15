"""Post-send callbacks registered by domain modules, keyed by outbox kind."""

from collections.abc import Callable

_on_sent: dict[str, Callable] = {}
_on_failed: dict[str, Callable] = {}


def register(kind: str, *, sent: Callable | None = None, failed: Callable | None = None) -> None:
    if sent:
        _on_sent[kind] = sent
    if failed:
        _on_failed[kind] = failed


def on_sent(row) -> None:
    handler = _on_sent.get(row.kind)
    if handler:
        handler(row)


def on_failed(row) -> None:
    handler = _on_failed.get(row.kind)
    if handler:
        handler(row)
