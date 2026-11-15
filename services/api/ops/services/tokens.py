"""Opaque single-use action references. Only a keyed hash is stored (Global Constraints)."""

from django.utils import timezone

from core.crypto import keyed_hash, new_token
from ops.models import ActionToken

PREFIX = "v1:"


def issue(purpose: str, *, ticket=None, binding=None, staff=None, task=None, generation=None, data=None,
          expires_at=None) -> str:
    raw = new_token()
    ActionToken.objects.create(
        token_hash=keyed_hash(raw, "action"), purpose=purpose, ticket=ticket, binding=binding, staff=staff,
        task=task, generation=generation, data=data or {}, expires_at=expires_at,
    )
    return PREFIX + raw


def resolve(payload: str | None, *, lock: bool = True) -> ActionToken | None:
    if not payload or not payload.startswith(PREFIX):
        return None
    qs = ActionToken.objects.filter(token_hash=keyed_hash(payload[len(PREFIX):], "action"))
    if lock:
        qs = qs.select_for_update(no_key=True)
    return qs.first()


def state(token: ActionToken, now=None) -> str:
    """valid | used | revoked | expired"""
    now = now or timezone.now()
    if token.revoked_at:
        return "revoked"
    if token.used_at:
        return "used"
    if token.expires_at and token.expires_at <= now:
        return "expired"
    return "valid"


def mark_used(token: ActionToken, now=None) -> None:
    token.used_at = now or timezone.now()
    token.save(update_fields=["used_at"])


def revoke(*, ticket=None, task=None, binding=None, purposes=None, now=None) -> int:
    qs = ActionToken.objects.filter(revoked_at__isnull=True, used_at__isnull=True)
    if ticket is not None:
        qs = qs.filter(ticket=ticket)
    if task is not None:
        qs = qs.filter(task=task)
    if binding is not None:
        qs = qs.filter(binding=binding)
    if purposes:
        qs = qs.filter(purpose__in=purposes)
    return qs.update(revoked_at=now or timezone.now())
