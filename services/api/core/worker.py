"""One worker pass over all durable work sources (ADR-0002). Steps register from app configs."""

import logging
from collections.abc import Callable

from django.db import transaction
from django.utils import timezone

from core.models import WorkerHeartbeat

log = logging.getLogger(__name__)
_steps: list[tuple[int, str, Callable]] = []


def register_step(order: int, name: str, fn: Callable) -> None:
    if not any(existing == name for _, existing, _ in _steps):
        _steps.append((order, name, fn))
        _steps.sort(key=lambda s: s[0])


def heartbeat(worker_id: str, now) -> None:
    with transaction.atomic():
        WorkerHeartbeat.objects.update_or_create(worker_id=worker_id, defaults={"beat_at": now})


def run_once(now=None, worker_id: str = "default") -> dict:
    now = now or timezone.now()
    stats = {}
    for _order, name, fn in _steps:
        stats[name] = fn(now)
    heartbeat(worker_id, timezone.now())
    return stats
