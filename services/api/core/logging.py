"""Log masking. Call sites must not log secrets; these patterns are a second line of defence."""

import logging
import re

_TOKEN = re.compile(r"v1:[A-Za-z0-9_-]{16,}")
_KEYED = re.compile(r"""(?i)(["']?(?:code|otp|token|secret|password|payload)["']?\s*[=:]\s*["']?)[^"'\s,}]+""")
_SPAN = re.compile(r"\+?\(?\d[\d\s().-]*\d|\d")


def _digits(text: str) -> int:
    return sum(ch.isdigit() for ch in text)


def _mask_phones(text: str) -> str:
    """Mask any digit span with 9+ digits as a whole, in one linear pass.

    Over-masking (for example a date written next to a number) is preferred to leaking. Log timestamps
    stay readable because the formatter adds them after masking.
    """
    return _SPAN.sub(lambda m: "[phone]" if _digits(m.group(0)) >= 9 else m.group(0), text)


def mask(text: str) -> str:
    text = _TOKEN.sub("v1:***", text)
    text = _KEYED.sub(r"\1***", text)
    return _mask_phones(text)


class MaskingFilter(logging.Filter):
    """Masks the rendered message (and arguments) of every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask(record.getMessage())
        record.args = ()
        return True


class MaskingFormatter(logging.Formatter):
    """Masks the message, exception and stack text; leaves the formatter's own timestamp intact."""

    def format(self, record: logging.LogRecord) -> str:
        record.msg = mask(record.getMessage())
        record.args = ()
        return super().format(record)

    def formatException(self, ei) -> str:  # noqa: N802 — logging API name
        return mask(super().formatException(ei))

    def formatStack(self, stack_info: str) -> str:  # noqa: N802 — logging API name
        return mask(super().formatStack(stack_info))
