"""Phone input normalization. Arabic-Indic and Persian digits are accepted; the
country code is preserved and international numbers are not forced into +966.

The server is the authority (ADR-0013): the app may format as the valet types, but only this decides. Input is never
guessed or truncated; a refusal carries a specific code so the app can say what is wrong."""

import re
from dataclasses import dataclass

import phonenumbers

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_SEPARATORS = re.compile(r"[\s\-‐-―().‎‏‪-‮⁦-⁩]")


class PhoneInvalid(ValueError):
    """`code` is the stable refusal shown to staff: phone_required, phone_not_a_number, phone_too_short,
    phone_too_long, phone_invalid_for_country, phone_country_unknown."""

    def __init__(self, code: str = "phone_invalid"):
        super().__init__(code)
        self.code = code


_REASONS = {
    phonenumbers.ValidationResult.TOO_SHORT: "phone_too_short",
    phonenumbers.ValidationResult.IS_POSSIBLE_LOCAL_ONLY: "phone_too_short",
    phonenumbers.ValidationResult.TOO_LONG: "phone_too_long",
    phonenumbers.ValidationResult.INVALID_COUNTRY_CODE: "phone_country_unknown",
    phonenumbers.ValidationResult.INVALID_LENGTH: "phone_invalid_for_country",
}


@dataclass(frozen=True)
class ParsedPhone:
    e164: str
    masked: str
    region: str | None


def normalize_digits(text: str) -> str:
    return text.translate(_DIGITS)


def mask_e164(e164: str, country_code: int) -> str:
    """Show the country code and a few digits only; at least half the national number stays hidden."""
    national = e164[1 + len(str(country_code)) :]
    if len(national) >= 9:
        return f"+{country_code} {national[0]}{'•' * (len(national) - 5)}{national[-4:]}"
    return f"+{country_code} {'•' * (len(national) - 2)}{national[-2:]}"


def parse_phone(raw: str, default_region: str = "SA") -> ParsedPhone:
    """`default_region` is the country the number is read in when it has no + or 00 prefix (the app's selector)."""
    region = (default_region or "").upper()
    if region not in phonenumbers.SUPPORTED_REGIONS:
        raise PhoneInvalid("phone_country_unknown")
    cleaned = _SEPARATORS.sub("", normalize_digits(raw or ""))
    if not cleaned:
        raise PhoneInvalid("phone_required")
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not re.fullmatch(r"\+?\d+", cleaned):
        raise PhoneInvalid("phone_not_a_number")  # letters, extensions or stray symbols are never stripped
    if len(cleaned.lstrip("+")) < 7:
        raise PhoneInvalid("phone_too_short")
    if len(cleaned.lstrip("+")) > 15:
        raise PhoneInvalid("phone_too_long")
    try:
        number = phonenumbers.parse(cleaned, None if cleaned.startswith("+") else region)
    except phonenumbers.NumberParseException as exc:
        if exc.error_type == phonenumbers.NumberParseException.INVALID_COUNTRY_CODE:
            raise PhoneInvalid("phone_country_unknown") from exc
        raise PhoneInvalid("phone_not_a_number") from exc
    reason = phonenumbers.is_possible_number_with_reason(number)
    if reason in _REASONS:
        raise PhoneInvalid(_REASONS[reason])
    if not phonenumbers.is_valid_number(number):
        raise PhoneInvalid("phone_invalid_for_country")
    e164 = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
    return ParsedPhone(
        e164=e164,
        masked=mask_e164(e164, number.country_code),
        region=phonenumbers.region_code_for_number(number),
    )
