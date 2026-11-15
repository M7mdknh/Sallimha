"""Log masking. Call sites must not log secrets; these patterns are a second line of defence."""

import logging
import re

_TOKEN = re.compile(r"v1:[A-Za-z0-9_-]{16,}")
_KEYED = re.compile(r"""(?i)(["']?(?:code|otp|token|secret|password|payload)["']?\s*[=:]\s*["']?)[^"'\s,}]+""")
# Phone candidates: 9–15 digits with common separators; never adjacent to ':' (times) or other digits.
_PHONE = re.compile(r"(?<![\d:])\+?\(?\d[\d\s().-]{6,22}\d(?![\d:])")


def _phone_sub(match: re.Match) -> str:
    digits = sum(ch.isdigit() for ch in match.group(0))
    return "[phone]" if 9 <= digits <= 15 else match.group(0)


def mask(text: str) -> str:
    text = _TOKEN.sub("v1:***", text)
    text = _KEYED.sub(r"\1***", text)
    return _PHONE.sub(_phone_sub, text)


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
