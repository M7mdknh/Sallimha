"""Webhook receipt: verify the signature over the raw body, then store durably (docs/03, docs/11)."""

import hashlib
import hmac
import json
import logging
from dataclasses import asdict

from django.conf import settings
from django.db import connection, transaction
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from messaging.models import WebhookInbox
from messaging.parse import parse_inbound

log = logging.getLogger(__name__)


class InvalidSignature(Exception):
    pass


def verify_signature(raw: bytes, header: str | None) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    supplied = header.removeprefix("sha256=")
    for secret in (settings.WHATSAPP_APP_SECRET, settings.WHATSAPP_APP_SECRET_PREVIOUS):
        if not secret:
            continue
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, supplied):
            return True
    return False


def ingest_webhook(raw: bytes, signature_header: str | None) -> list[WebhookInbox]:
    """Returns newly stored rows. Duplicates are ignored (one row per event key)."""
    if not verify_signature(raw, signature_header):
        raise InvalidSignature()
    payload = json.loads(raw)
    created = []
    with transaction.atomic():
        for item in parse_inbound(payload):
            data = asdict(item)
            data["timestamp"] = item.timestamp.isoformat()
            row, was_created = WebhookInbox.objects.get_or_create(
                event_key=item.event_key, defaults={"kind": item.kind, "payload": data}
            )
            if was_created:
                created.append(row)
        if created:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_notify('sallimha_work', 'inbox')")
    return created


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request):
    if request.method == "GET":
        verify_token = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "")
        if verify_token and request.GET.get("hub.mode") == "subscribe" and hmac.compare_digest(
            request.GET.get("hub.verify_token", ""), verify_token
        ):
            return HttpResponse(request.GET.get("hub.challenge", ""), content_type="text/plain")
        return HttpResponseForbidden()
    try:
        ingest_webhook(request.body, request.headers.get("X-Hub-Signature-256"))
    except InvalidSignature:
        log.warning("webhook rejected: invalid signature")
        return HttpResponseForbidden()
    except (ValueError, KeyError):
        log.warning("webhook rejected: malformed payload")
        return HttpResponse(status=400)
    return HttpResponse(status=200)
