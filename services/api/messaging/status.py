"""Apply provider delivery statuses without regression (AT-27)."""

from django.db import IntegrityError, transaction

from messaging.models import MessageOutbox, MessageStatusEvent

_RANK = {"SENT": 1, "DELIVERED": 2, "READ": 3}


def apply_status(provider_message_id: str, status: str, provider_timestamp: int, errors: list | None = None) -> None:
    status_upper = status.upper()
    with transaction.atomic():
        row = (MessageOutbox.objects.select_for_update(no_key=True)
               .filter(provider_message_id=provider_message_id).first())
        try:
            with transaction.atomic():
                MessageStatusEvent.objects.create(
                    outbox=row, provider_message_id=provider_message_id, status=status,
                    provider_timestamp=provider_timestamp, errors=errors or [],
                )
        except IntegrityError:
            return  # duplicate transition
        if row is None:
            return
        current = _RANK.get(row.status, 0)
        if status_upper in _RANK and _RANK[status_upper] > current:
            row.status = status_upper
            row.save(update_fields=["status"])
        elif status_upper == "FAILED" and current < _RANK["DELIVERED"]:
            row.status = MessageOutbox.Status.FAILED
            row.last_error = str((errors or [{}])[0].get("title", "failed"))[:200]
            row.save(update_fields=["status", "last_error"])
            from messaging import hooks

            hooks.on_failed(row)
