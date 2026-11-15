"""Inbox processing. Messages are handled strictly in arrival order by one worker at a time,
so a staff member's or guest's conversation is never processed out of sequence."""

import logging
from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

from messaging.models import WebhookInbox
from messaging.parse import Inbound, inbound_from_row
from messaging.status import apply_status

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 5
_INBOX_LOCK = (4243, 0)


def handle_message(inb: Inbound) -> None:
    from messaging import router

    router.route(inb)


def _process(row: WebhookInbox, now) -> None:
    inb = inbound_from_row(row)
    try:
        with transaction.atomic():
            if inb.kind == "status":
                apply_status(inb.provider_message_id, inb.status, int(inb.timestamp.timestamp()), inb.errors)
            else:
                handle_message(inb)
            row.status = WebhookInbox.Status.PROCESSED
            row.processed_at = now
            row.attempts += 1
            row.save(update_fields=["status", "processed_at", "attempts"])
    except Exception as exc:  # noqa: BLE001 — any handler failure is retried, then dead-lettered
        log.exception("inbox item %s failed", row.id)
        row.attempts += 1
        row.last_error = type(exc).__name__[:200]
        if row.attempts >= MAX_ATTEMPTS:
            row.status = WebhookInbox.Status.DEAD
        else:
            row.next_attempt_at = now + timedelta(seconds=2**row.attempts)
        row.save(update_fields=["attempts", "last_error", "status", "next_attempt_at"])


def process_inbox(now=None, limit: int = 100) -> int:
    now = now or timezone.now()
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", _INBOX_LOCK)
        if not cursor.fetchone()[0]:
            return 0
    try:
        rows = list(
            WebhookInbox.objects.filter(status=WebhookInbox.Status.RECEIVED)
            .exclude(next_attempt_at__gt=now)
            .order_by("id")[:limit]
        )
        for row in rows:
            _process(row, now)
        return len(rows)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s, %s)", _INBOX_LOCK)
