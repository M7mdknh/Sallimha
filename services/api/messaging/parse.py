"""Parse WhatsApp Cloud API webhook payloads (shapes verified in docs/11)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class Inbound:
    event_key: str
    kind: str  # message | status
    provider_message_id: str
    timestamp: datetime
    from_phone: str | None = None
    from_user_id: str | None = None
    msg_type: str = ""
    text: str | None = None
    button_payload: str | None = None
    media_id: str | None = None
    media_mime: str | None = None
    context_id: str | None = None
    status: str | None = None
    recipient_phone: str | None = None
    errors: list = field(default_factory=list)


def _ts(value) -> datetime:
    return datetime.fromtimestamp(int(value), tz=UTC)


def _phone(raw: str | None) -> str | None:
    if not raw:
        return None
    return raw if raw.startswith("+") else f"+{raw}"


def _message(m: dict) -> Inbound:
    msg_type = m.get("type", "")
    text = button = media_id = media_mime = None
    if msg_type == "text":
        text = (m.get("text") or {}).get("body")
    elif msg_type == "button":
        button = (m.get("button") or {}).get("payload")
    elif msg_type == "interactive":
        interactive = m.get("interactive") or {}
        reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
        button = reply.get("id")
    elif msg_type == "image":
        image = m.get("image") or {}
        media_id, media_mime = image.get("id"), image.get("mime_type")
    return Inbound(
        event_key=f"msg:{m['id']}",
        kind="message",
        provider_message_id=m["id"],
        timestamp=_ts(m.get("timestamp", 0)),
        from_phone=_phone(m.get("from")),
        from_user_id=m.get("from_user_id"),
        msg_type=msg_type,
        text=text,
        button_payload=button,
        media_id=media_id,
        media_mime=media_mime,
        context_id=(m.get("context") or {}).get("id"),
    )


def _status(s: dict) -> Inbound:
    return Inbound(
        event_key=f"st:{s['id']}:{s['status']}:{s.get('timestamp', 0)}",
        kind="status",
        provider_message_id=s["id"],
        timestamp=_ts(s.get("timestamp", 0)),
        status=s["status"],
        recipient_phone=_phone(s.get("recipient_id")),
        errors=s.get("errors") or [],
    )


def parse_inbound(payload: dict) -> list[Inbound]:
    items: list[Inbound] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            items.extend(_message(m) for m in value.get("messages") or [] if m.get("id"))
            items.extend(_status(s) for s in value.get("statuses") or [] if s.get("id") and s.get("status"))
    return items


def inbound_from_row(row) -> Inbound:
    """Rebuild an Inbound from a stored inbox row (payload holds the single item)."""
    data = dict(row.payload)
    data["timestamp"] = datetime.fromisoformat(data["timestamp"])
    return Inbound(**data)
