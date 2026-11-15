import logging
import re

_PATTERNS = [
    (re.compile(r"v1:[A-Za-z0-9_-]{16,}"), "v1:***"),
    (re.compile(r"(?i)(code\s*[=:]\s*)\d{4,8}"), r"\1******"),
    (re.compile(r"\+?\d[\d\s-]{7,16}\d"), "[phone]"),
]


def mask(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class MaskingFilter(logging.Filter):
    """Removes phone numbers, collection codes and action tokens from log lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask(record.getMessage())
        record.args = ()
        return True
