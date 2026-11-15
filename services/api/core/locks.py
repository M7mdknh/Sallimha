from django.db import connection

_EVENT_NAMESPACE = 4242


def lock_event(event_id: int) -> None:
    """Serialize dispatch for one event until the surrounding transaction ends."""
    if not connection.in_atomic_block:
        raise RuntimeError("lock_event must be called inside transaction.atomic()")
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [_EVENT_NAMESPACE, int(event_id)])
