import string

import pytest

from messaging.catalogue import BUTTONS, MESSAGES, button_title, render_text
from messaging.transport import OutboundPayload, build_cloud_request


def _fields(template: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(template) if f}


@pytest.mark.parametrize("key", sorted(MESSAGES))
def test_every_message_has_both_languages_with_same_placeholders(key):
    entry = MESSAGES[key]
    assert set(entry) == {"ar", "en"}
    assert _fields(entry["ar"]) == _fields(entry["en"])
    sample = {f: "#024" for f in _fields(entry["ar"])}
    assert render_text(key, "ar", sample) and render_text(key, "en", sample)


@pytest.mark.parametrize("key", sorted(BUTTONS))
def test_button_titles_fit_whatsapp_limit(key):
    for lang in ("ar", "en"):
        assert len(button_title(key, lang, {"ticket": "#1024"})) <= 20


def _payload(mode, buttons):
    return OutboundPayload(outbox_id=1, to_phone="+966501234567", mode=mode, template="valet.offer", language="ar",
                           text="body", params={"ticket": "#024"}, buttons=buttons)


def test_cloud_session_request_uses_interactive_reply_buttons():
    body = build_cloud_request(_payload("session", [("v1:a", "قبول"), ("v1:b", "اعتذار")]))
    assert body["to"] == "966501234567" and body["type"] == "interactive"
    buttons = body["interactive"]["action"]["buttons"]
    assert [b["reply"]["id"] for b in buttons] == ["v1:a", "v1:b"]


def test_cloud_template_request_carries_quick_reply_payloads():
    body = build_cloud_request(_payload("template", [("v1:a", "قبول")]))
    components = body["template"]["components"]
    quick = [c for c in components if c["type"] == "button"]
    assert quick == [{"type": "button", "sub_type": "quick_reply", "index": "0",
                      "parameters": [{"type": "payload", "payload": "v1:a"}]}]
    assert body["template"]["language"] == {"code": "ar"}


def test_cloud_plain_text_without_buttons():
    assert build_cloud_request(_payload("session", []))["type"] == "text"
