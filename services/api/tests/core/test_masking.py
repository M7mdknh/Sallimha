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


def test_masking_formatter_masks_exception_text():
    from core.logging import MaskingFormatter

    try:
        raise ValueError("cannot reach +966501234567")
    except ValueError:
        import sys

        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "send failed", (), sys.exc_info())
    rendered = MaskingFormatter("%(message)s").format(record)
    assert "966501234567" not in rendered
    assert "send failed" in rendered


def test_masking_filter_hides_json_quoted_secrets():
    text = _render('payload {"code": "123456", "token": "abcDEF123ghiJKL456", "otp": "654321"}')
    assert "123456" not in text
    assert "abcDEF123ghiJKL456" not in text
    assert "654321" not in text


def test_masking_filter_hides_parenthesised_phone():
    assert "4567" not in _render("call (050) 123-4567 now")
