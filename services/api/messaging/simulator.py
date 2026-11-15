"""Local WhatsApp simulator helpers (dev/test only). Builds payloads in the Cloud API shapes
verified in docs/11 and signs them like Meta does, so the real webhook path is exercised.
Everything produced here is SIMULATED and is never evidence of real integration."""

import hashlib
import hmac
import itertools
import json
import time
import uuid

from django.conf import settings

_seq = itertools.count(1)


def sign(raw: bytes, secret: str | None = None) -> str:
    key = (secret or settings.WHATSAPP_APP_SECRET).encode()
    return "sha256=" + hmac.new(key, raw, hashlib.sha256).hexdigest()


def _envelope(value: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "SIM-WABA", "changes": [{"field": "messages", "value": value}]}],
    }


def build_message_payload(
    *,
    from_phone: str | None,
    from_user_id: str | None = None,
    text: str | None = None,
    button_payload: str | None = None,
    interactive_id: str | None = None,
    image_id: str | None = None,
    image_mime: str = "image/jpeg",
    context_id: str | None = None,
    wamid: str | None = None,
    timestamp: int | None = None,
) -> dict:
    message: dict = {
        "id": wamid or f"wamid.SIMIN.{uuid.uuid4().hex}",
        "timestamp": str(timestamp or int(time.time())),
        "from_user_id": from_user_id or f"SIM.{(from_phone or 'anon').lstrip('+')}",
    }
    if from_phone:
        message["from"] = from_phone.lstrip("+")
    if context_id:
        message["context"] = {"from": "SIMBUSINESS", "id": context_id}
    if button_payload is not None:
        message.update(type="button", button={"payload": button_payload, "text": "button"})
    elif interactive_id is not None:
        message.update(type="interactive", interactive={"type": "button_reply",
                                                        "button_reply": {"id": interactive_id, "title": "button"}})
    elif image_id is not None:
        message.update(type="image", image={"id": image_id, "mime_type": image_mime})
    else:
        message.update(type="text", text={"body": text or ""})
    contact = {"profile": {"name": "Simulated"}, "user_id": message["from_user_id"]}
    if from_phone:
        contact["wa_id"] = from_phone.lstrip("+")
    return _envelope({"messaging_product": "whatsapp", "contacts": [contact], "messages": [message]})


def build_status_payload(wamid: str, status: str, timestamp: int, recipient_phone: str = "+966500000000",
                         errors: list | None = None) -> dict:
    item = {"id": wamid, "status": status, "timestamp": str(timestamp), "recipient_id": recipient_phone.lstrip("+")}
    if errors:
        item["errors"] = errors
    return _envelope({"messaging_product": "whatsapp", "statuses": [item]})


def post_inbound(payload: dict):
    """Feed a simulated payload through the real signature check and inbox."""
    from messaging.webhook import ingest_webhook

    raw = json.dumps(payload).encode()
    return ingest_webhook(raw, sign(raw))
