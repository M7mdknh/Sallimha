"""Log masking. Call sites must not log secrets; these patterns are a second line of defence."""

import logging
import re

_TOKEN = re.compile(r"v1:[A-Za-z0-9_-]{16,}")
_KEYED = re.compile(r"""(?i)(["']?(?:code|otp|token|secret|password|payload)["']?\s*[=:]\s*["']?)[^"'\s,}]+""")
_TIME = re.compile(r"(?<!\d)\d{1,2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?(?!\d)")
_SPAN = re.compile(r"\+?\(?\d[\d\s().-]*\d|\d")


def _digits(text: str) -> int:
    return sum(ch.isdigit() for ch in text)


def _mask_span(span: str) -> str:
    """Mask every 9–15-digit group inside a digit span; longer unbroken runs are masked whole."""
    parts = re.split(r"(\s+)", span)
    words, seps = parts[0::2], parts[1::2] + [""]
    out, i = [], 0
    while i < len(words):
        if _digits(words[i]) > 15:
            out.append("[number]" + seps[i])
            i += 1
            continue
        best, total = None, 0
        for j in range(i, len(words)):
            total += _digits(words[j])
            if total > 15:
                break
            if total >= 9:
                best = j
        if best is None:
            out.append(words[i] + seps[i])
            i += 1
        else:
            out.append("[phone]" + seps[best])
            i = best + 1
    return "".join(out)


def _mask_phones(text: str) -> str:
    times: list[str] = []

    def protect(match: re.Match) -> str:
        times.append(match.group(0))
        return f"\x00{len(times) - 1}\x00"

    text = _TIME.sub(protect, text)
    text = _SPAN.sub(lambda m: _mask_span(m.group(0)), text)
    return re.sub(r"\x00(\d+)\x00", lambda m: times[int(m.group(1))], text)


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
