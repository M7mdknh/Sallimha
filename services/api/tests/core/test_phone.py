import pytest

from core.phone import PhoneInvalid, normalize_digits, parse_phone


def test_normalize_digits_arabic_indic():
    assert normalize_digits("٠٥٠١٢٣٤٥٦٧") == "0501234567"


def test_normalize_digits_persian():
    assert normalize_digits("۰۵۰۱۲۳۴۵۶۷") == "0501234567"


def test_parse_saudi_local_and_intl():
    assert parse_phone("0501234567").e164 == "+966501234567"
    assert parse_phone("٠٥٠ ١٢٣ ٤٥٦٧").e164 == "+966501234567"
    assert parse_phone("+966 50-123-4567").e164 == "+966501234567"
    assert parse_phone("00966501234567").e164 == "+966501234567"


def test_parse_international_not_forced_966():
    egypt = parse_phone("+201001234567")
    assert egypt.e164 == "+201001234567"
    assert egypt.region == "EG"
    assert parse_phone("+1 650 253 0000").e164 == "+16502530000"


@pytest.mark.parametrize("raw", ["12", "٧", "12345", "abc", "+966 12", "", "0501234567 ext 9"])
def test_reject_short_or_non_numeric(raw):
    with pytest.raises(PhoneInvalid):
        parse_phone(raw)


def test_mask_keeps_cc_and_last4():
    assert parse_phone("0501234567").masked == "+966 5••••4567"
