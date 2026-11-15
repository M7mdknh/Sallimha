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


def test_masking_keeps_dates_and_times_readable():
    from core.logging import MaskingFormatter

    record = logging.LogRecord("t", logging.INFO, __file__, 1, "at 2026-11-15T11:23:06 and 2026-11-15 11:23", (), None)
    rendered = MaskingFormatter("%(asctime)s %(message)s").format(record)
    assert "[phone]" not in rendered
    assert "2026-11-15T11:23:06" in rendered


def test_masking_key_colon_phone():
    assert "0501234567" not in _render("phone:0501234567")
    assert "966501234567" not in _render("to=+966501234567")


def test_masking_date_followed_by_phone():
    text = _render("on 2026-11-15 0501234567 arrived")
    assert "0501234567" not in text and "2026-11-15" in text


def test_masking_adjacent_phones():
    text = _render("numbers 0501234567 0559876543")
    assert "0501234567" not in text and "0559876543" not in text


def test_masking_long_digit_run_is_masked_not_leaked():
    assert "96650123456712345" not in _render("raw 96650123456712345")
