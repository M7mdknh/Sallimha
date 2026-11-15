"""Phone input normalization. Arabic-Indic and Persian digits are accepted; the
country code is preserved and international numbers are not forced into +966."""

import re
from dataclasses import dataclass

import phonenumbers

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_SEPARATORS = re.compile(r"[\s\-().‎‏‪-‮]")


class PhoneInvalid(ValueError):
    pass


@dataclass(frozen=True)
class ParsedPhone:
    e164: str
    masked: str
    region: str | None


def normalize_digits(text: str) -> str:
    return text.translate(_DIGITS)


def mask_e164(e164: str, country_code: int) -> str:
    national = e164[1 + len(str(country_code)) :]
    return f"+{country_code} {national[0]}{'•' * (len(national) - 5)}{national[-4:]}"


def parse_phone(raw: str, default_region: str = "SA") -> ParsedPhone:
    cleaned = _SEPARATORS.sub("", normalize_digits(raw or ""))
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not re.fullmatch(r"\+?\d{7,15}", cleaned):
        raise PhoneInvalid("not a phone number")
    try:
        number = phonenumbers.parse(cleaned, None if cleaned.startswith("+") else default_region)
    except phonenumbers.NumberParseException as exc:
        raise PhoneInvalid("unparseable") from exc
    if not phonenumbers.is_valid_number(number):
        raise PhoneInvalid("invalid number")
    e164 = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
    return ParsedPhone(
        e164=e164,
        masked=mask_e164(e164, number.country_code),
        region=phonenumbers.region_code_for_number(number),
    )
