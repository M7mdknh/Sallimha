"""Transactional outbox: enqueue inside business transactions, send outside them (ADR-0002)."""

import logging
from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

from core.crypto import decrypt_text, encrypt_text, keyed_hash
from messaging import hooks
from messaging.catalogue import button_title, render_text
from messaging.models import Conversation, MessageOutbox
from messaging.transport import (
    OutboundPayload,
    PermanentSendError,
    TransientSendError,
    UnknownSendOutcome,
    get_transport,
)

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 6
LEASE = timedelta(seconds=30)
SERVICE_WINDOW = timedelta(hours=24)


def _notify_worker() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_notify('sallimha_work', 'outbox')")


def enqueue(kind: str, *, staff=None, binding=None, to_phone: str | None = None, template: str, params: dict,
            buttons=(), ticket=None, task=None, dedupe_key: str, language: str | None = None,
            now=None) -> MessageOutbox:
    """Call inside the business transaction. `buttons` = [(payload, button_key, key_params?)]."""
    now = now or timezone.now()
    lang = language or (binding.language if binding is not None else getattr(staff, "language", "ar"))
    row, created = MessageOutbox.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults={
            "kind": kind, "staff": staff, "binding": binding, "ticket": ticket, "task": task,
            "to_phone_enc": encrypt_text(to_phone) if to_phone else "",
            "to_phone_hash": keyed_hash(to_phone, "phone") if to_phone else "",
            "template": template, "params": params, "buttons": [list(b) for b in buttons],
            "language": lang, "next_attempt_at": now,
        },
    )
    if created:
        _notify_worker()
    return row


def party_key(*, staff=None, binding=None, phone_hash: str = "") -> str:
    if staff is not None:
        return f"staff:{staff.id}"
    return f"guest:{binding.phone_hash if binding is not None else phone_hash}"


def note_inbound(*, staff=None, binding=None, key: str | None = None, at=None) -> None:
    at = at or timezone.now()
    key = key or party_key(staff=staff, binding=binding)
    conv, _ = Conversation.objects.get_or_create(party_key=key)
    if conv.last_inbound_at is None or conv.last_inbound_at < at:
        conv.last_inbound_at = at
        conv.save(update_fields=["last_inbound_at", "updated_at"])


def choose_mode(row: MessageOutbox, now) -> str:
    key = party_key(staff=row.staff, binding=row.binding, phone_hash=row.to_phone_hash)
    conv = Conversation.objects.filter(party_key=key).first()
    if conv and conv.last_inbound_at and now - conv.last_inbound_at < SERVICE_WINDOW:
        return "session"
    return "template"


def _resolve_params(row: MessageOutbox) -> dict:
    params = dict(row.params)
    code_id = params.pop("__code_id", None)
    if code_id is not None:
        from ops.models import CollectionCode

        code = CollectionCode.objects.get(pk=code_id)
        if not code.delivery_enc:
            raise PermanentSendError("collection code no longer deliverable")
        params["code"] = decrypt_text(code.delivery_enc)
    return params


def render(row: MessageOutbox, now) -> OutboundPayload:
    params = _resolve_params(row)
    if row.staff_id:
        to_phone = row.staff.phone_e164
    elif row.binding_id:
        to_phone = decrypt_text(row.binding.phone_enc)
    else:
        to_phone = decrypt_text(row.to_phone_enc)
    buttons = [(b[0], button_title(b[1], row.language, b[2] if len(b) > 2 else None)) for b in row.buttons]
    return OutboundPayload(
        outbox_id=row.id, to_phone=to_phone, mode=choose_mode(row, now), template=row.template,
        language=row.language, text=render_text(row.template, row.language, params), params=params, buttons=buttons,
    )


def recover_expired_leases(now) -> int:
    """A send that crashed mid-flight may have reached the provider: never resend blindly (AT-26)."""
    return MessageOutbox.objects.filter(status=MessageOutbox.Status.SENDING, lease_until__lt=now).update(
        status=MessageOutbox.Status.DELIVERY_UNKNOWN, last_error="lease expired during send"
    )


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(2**attempts, 300))


def _claim(now, limit: int) -> list[MessageOutbox]:
    with transaction.atomic():
        rows = list(
            MessageOutbox.objects.select_for_update(skip_locked=True)
            .filter(status=MessageOutbox.Status.PENDING, next_attempt_at__lte=now)
            .order_by("next_attempt_at", "id")[:limit]
        )
        for row in rows:
            row.status = MessageOutbox.Status.SENDING
            row.lease_until = now + LEASE
            row.attempts += 1
            row.save(update_fields=["status", "lease_until", "attempts"])
    return rows


def _finish(row_id: int, now, **changes) -> MessageOutbox:
    with transaction.atomic():
        row = MessageOutbox.objects.select_for_update().get(pk=row_id)
        if row.status != MessageOutbox.Status.SENDING:
            return row
        for name, value in changes.items():
            setattr(row, name, value)
        row.lease_until = None
        row.save()
        if row.status == MessageOutbox.Status.SENT:
            hooks.on_sent(row)
        elif row.status == MessageOutbox.Status.DEAD:
            hooks.on_failed(row)
    return row


def send_due(now=None, limit: int = 20) -> int:
    now = now or timezone.now()
    recover_expired_leases(now)
    transport = get_transport()
    sent = 0
    for row in _claim(now, limit):
        try:
            payload = render(row, now)
            result = transport.send(payload)
        except TransientSendError as exc:
            if row.attempts >= MAX_ATTEMPTS:
                _finish(row.id, now, status=MessageOutbox.Status.DEAD, failure_class="exhausted",
                        last_error=str(exc)[:200])
            else:
                _finish(row.id, now, status=MessageOutbox.Status.PENDING, next_attempt_at=now + _backoff(row.attempts),
                        last_error=str(exc)[:200])
        except PermanentSendError as exc:
            _finish(row.id, now, status=MessageOutbox.Status.DEAD, failure_class="permanent", last_error=str(exc)[:200])
        except UnknownSendOutcome as exc:
            _finish(row.id, now, status=MessageOutbox.Status.DELIVERY_UNKNOWN, last_error=str(exc)[:200])
        else:
            _finish(row.id, now, status=MessageOutbox.Status.SENT, sent_at=now, sent_via=payload.mode,
                    provider_message_id=result.provider_message_id)
            sent += 1
    return sent


def replay(outbox_id: int, now=None) -> bool:
    """Operator replay of a dead letter. Idempotent: only a DEAD row is re-queued."""
    now = now or timezone.now()
    with transaction.atomic():
        row = MessageOutbox.objects.select_for_update().get(pk=outbox_id)
        if row.status != MessageOutbox.Status.DEAD:
            return False
        row.status = MessageOutbox.Status.PENDING
        row.next_attempt_at = now
        row.failure_class = ""
        row.last_error = ""
        row.save(update_fields=["status", "next_attempt_at", "failure_class", "last_error"])
        _notify_worker()
    return True
