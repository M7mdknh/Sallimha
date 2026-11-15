from django.db import IntegrityError, transaction

from ops.models import Alert


def raise_alert(event, kind: str, *, dedupe_key: str, ticket=None, severity: str = "warning",
                detail: dict | None = None) -> Alert | None:
    """Idempotent: the same dedupe_key never creates a second alert."""
    try:
        with transaction.atomic():
            return Alert.objects.create(event=event, kind=kind, ticket=ticket, severity=severity,
                                        detail=detail or {}, dedupe_key=dedupe_key)
    except IntegrityError:
        return None
