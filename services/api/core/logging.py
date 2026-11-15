"""Log masking. Call sites must not log secrets; these patterns are a second line of defence."""

import logging
import re

_PATTERNS = [
    (re.compile(r"v1:[A-Za-z0-9_-]{16,}"), "v1:***"),
    (
        re.compile(r"""(?i)(["']?(?:code|otp|token|secret|password|payload)["']?\s*[=:]\s*["']?)[^"'\s,}]+"""),
        r"\1***",
    ),
    (re.compile(r"\+?\(?\d[\d\s()-]{7,18}\d"), "[phone]"),
]


def mask(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class MaskingFilter(logging.Filter):
    """Masks the rendered message (and arguments) of every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask(record.getMessage())
        record.args = ()
        return True


class MaskingFormatter(logging.Formatter):
    """Masks the final rendered line, including exception and stack text."""

    def format(self, record: logging.LogRecord) -> str:
        return mask(super().format(record))
