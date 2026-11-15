"""Log masking. Call sites must not log secrets; these patterns are a second line of defence."""

import logging
import re

_TOKEN = re.compile(r"v1:[A-Za-z0-9_-]{16,}")
_KEYED = re.compile(r"""(?i)(["']?(?:code|otp|token|secret|password|payload)["']?\s*[=:]\s*["']?)[^"'\s,}]+""")
_SPAN = re.compile(r"\+?\(?\d[\d\s().-]*\d|\d")
_TRAILING_HOUR = re.compile(r"\s+\d{1,2}$")


def _digits(text: str) -> int:
    return sum(ch.isdigit() for ch in text)


def _mask_phones(text: str) -> str:
    """Mask any digit span with 9+ digits as a whole (linear; over-masking is preferred to leaking).

    Clock times stay readable: a 1–2 digit word directly followed by ':' is an hour, not part of a number.
    """

    def replace(match: re.Match) -> str:
        span, tail = match.group(0), ""
        if text[match.end() : match.end() + 1] == ":":
            hour = _TRAILING_HOUR.search(span)
            if hour:
                span, tail = span[: hour.start()], span[hour.start() :]
        return ("[phone]" if _digits(span) >= 9 else span) + tail

    return _SPAN.sub(replace, text)


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
