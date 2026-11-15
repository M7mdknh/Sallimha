from collections.abc import Callable

from django.db import IntegrityError, transaction

from core.models import IdempotencyRecord


def idempotent(scope: str, key: str, fn: Callable[[], dict]) -> tuple[dict, bool]:
    """Run `fn` once per (scope, key). Returns (result, replayed)."""
    existing = IdempotencyRecord.objects.filter(scope=scope, key=key).first()
    if existing is not None:
        return existing.response, True
    try:
        with transaction.atomic():
            result = fn()
            IdempotencyRecord.objects.create(scope=scope, key=key, response=result)
            return result, False
    except IntegrityError:
        existing = IdempotencyRecord.objects.filter(scope=scope, key=key).first()
        if existing is None:
            raise
        return existing.response, True
