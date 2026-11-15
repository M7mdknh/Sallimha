from messaging.parse import parse_inbound
from messaging.simulator import build_message_payload, build_status_payload


def test_parse_template_button_with_context():
    payload = build_message_payload(from_phone="+966501234567", button_payload="v1:abc", context_id="wamid.ORIG",
                                    from_user_id="SA.123")
    (inb,) = parse_inbound(payload)
    assert inb.kind == "message" and inb.msg_type == "button"
    assert inb.button_payload == "v1:abc" and inb.context_id == "wamid.ORIG"
    assert inb.from_phone == "+966501234567" and inb.from_user_id == "SA.123"


def test_parse_interactive_reply_and_text():
    (btn,) = parse_inbound(build_message_payload(from_phone="+966501234567", interactive_id="v1:xyz"))
    assert btn.button_payload == "v1:xyz"
    (txt,) = parse_inbound(build_message_payload(from_phone="+966501234567", text=" ١٢ "))
    assert txt.text == " ١٢ "


def test_parse_bsuid_only_sender_has_no_phone():
    (inb,) = parse_inbound(build_message_payload(from_phone=None, from_user_id="SA.999", text="hi"))
    assert inb.from_phone is None and inb.from_user_id == "SA.999"


def test_parse_status():
    (st,) = parse_inbound(build_status_payload("wamid.X", "delivered", 1750000000))
    assert (st.kind, st.status, st.provider_message_id) == ("status", "delivered", "wamid.X")
    assert st.event_key == "st:wamid.X:delivered:1750000000"
