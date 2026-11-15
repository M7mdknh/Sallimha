import logging

from core.logging import MaskingFilter


def _render(msg, *args):
    record = logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, None)
    MaskingFilter().filter(record)
    return record.getMessage()


def test_masking_filter_hides_phone_and_code():
    text = _render("sent ticket to %s with code=%s", "+966501234567", "123456")
    assert "966501234567" not in text
    assert "123456" not in text


def test_masking_filter_hides_action_tokens():
    text = _render("button payload v1:Qm9ndXMtdG9rZW4tdmFsdWUtZm9yLXRlc3Rz")
    assert "Qm9ndXMtdG9rZW4tdmFsdWUtZm9yLXRlc3Rz" not in text


def test_masking_filter_keeps_short_numbers():
    assert _render("ticket %s hook %s", "#024", "12") == "ticket #024 hook 12"
