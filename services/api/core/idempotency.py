from collections.abc import Callable

from django.db import IntegrityError, transaction

from core.models import IdempotencyRecord


class IdempotencyMismatch(Exception):
    """The key was already used for a different request body."""


def _replay(existing: IdempotencyRecord, fingerprint: str) -> tuple[dict, bool]:
    if existing.fingerprint and fingerprint and existing.fingerprint != fingerprint:
        raise IdempotencyMismatch
    return existing.response, True


def idempotent(scope: str, key: str, fn: Callable[[], dict], fingerprint: str = "") -> tuple[dict, bool]:
    """Run `fn` once per (scope, key). Returns (result, replayed). A repeat with a different `fingerprint`
    (request body) raises IdempotencyMismatch instead of replaying an unrelated result."""
    existing = IdempotencyRecord.objects.filter(scope=scope, key=key).first()
    if existing is not None:
        return _replay(existing, fingerprint)
    try:
        with transaction.atomic():
            result = fn()
            IdempotencyRecord.objects.create(scope=scope, key=key, fingerprint=fingerprint, response=result)
            return result, False
    except IntegrityError:
        existing = IdempotencyRecord.objects.filter(scope=scope, key=key).first()
        if existing is None:
            raise
        return _replay(existing, fingerprint)
