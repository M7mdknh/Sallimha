import json

import pytest
from django.test import override_settings

from messaging.models import WebhookInbox
from messaging.simulator import build_message_payload, build_status_payload, sign
from messaging.webhook import InvalidSignature, ingest_webhook


def _raw(payload):
    return json.dumps(payload).encode()


@pytest.mark.django_db
def test_invalid_signature_rejected_before_persist():
    raw = _raw(build_message_payload(from_phone="+966501234567", text="hello"))
    with pytest.raises(InvalidSignature):
        ingest_webhook(raw, "sha256=" + "0" * 64)
    with pytest.raises(InvalidSignature):
        ingest_webhook(raw, None)
    assert WebhookInbox.objects.count() == 0


@pytest.mark.django_db
def test_valid_signature_stores_before_ack():
    raw = _raw(build_message_payload(from_phone="+966501234567", text="hello"))
    rows = ingest_webhook(raw, sign(raw))
    assert len(rows) == 1 and rows[0].status == WebhookInbox.Status.RECEIVED


@pytest.mark.django_db
@override_settings(WHATSAPP_APP_SECRET="new-secret", WHATSAPP_APP_SECRET_PREVIOUS="old-secret")
def test_previous_secret_accepted_during_rotation():
    old_raw = _raw(build_message_payload(from_phone="+966501234567", text="hi"))
    assert ingest_webhook(old_raw, sign(old_raw, secret="old-secret"))
    new_raw = _raw(build_message_payload(from_phone="+966501234567", text="x"))
    assert ingest_webhook(new_raw, sign(new_raw, secret="new-secret"))
    other_raw = _raw(build_message_payload(from_phone="+966501234567", text="y"))
    with pytest.raises(InvalidSignature):
        ingest_webhook(other_raw, sign(other_raw, secret="unknown-secret"))


@pytest.mark.django_db
def test_duplicate_webhook_single_inbox_row():
    payload = build_message_payload(from_phone="+966501234567", text="hello", wamid="wamid.DUP1")
    raw = _raw(payload)
    ingest_webhook(raw, sign(raw))
    ingest_webhook(raw, sign(raw))
    assert WebhookInbox.objects.filter(event_key="msg:wamid.DUP1").count() == 1


@pytest.mark.django_db
def test_status_events_are_distinct_inbox_rows():
    for status, ts in (("sent", 100), ("delivered", 101), ("read", 102)):
        raw = _raw(build_status_payload("wamid.OUT1", status, ts))
        ingest_webhook(raw, sign(raw))
    assert WebhookInbox.objects.filter(kind="status").count() == 3


def test_webhook_view_rejects_bad_signature(client, db):
    response = client.post("/webhooks/whatsapp", data=b"{}", content_type="application/json",
                           headers={"X-Hub-Signature-256": "sha256=bad"})
    assert response.status_code == 403


def test_webhook_view_accepts_signed_payload(client, db):
    raw = _raw(build_message_payload(from_phone="+966501234567", text="hello"))
    response = client.post("/webhooks/whatsapp", data=raw, content_type="application/json",
                           headers={"X-Hub-Signature-256": sign(raw)})
    assert response.status_code == 200
