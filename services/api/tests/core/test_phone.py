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


def test_mask_hides_most_digits_of_short_national_numbers():
    from core.phone import mask_e164

    masked = mask_e164("+97312345678", 973)  # 8-digit national number
    digits_shown = sum(ch.isdigit() for ch in masked.split(" ", 1)[1])
    assert digits_shown <= 2


# --- ADR-0013: explicit region from the country selector and specific refusals ---------------------------------

@pytest.mark.parametrize("raw,region,e164", [
    ("050-123-4567", "SA", "+966501234567"),
    ("(050) 123 4567", "SA", "+966501234567"),
    ("966501234567", "SA", "+966501234567"),  # the country code typed without a plus is still Saudi
    ("+44 7911 123456", "SA", "+447911123456"),  # an explicit + wins over the selected country
    ("07911 123456", "GB", "+447911123456"),
    ("۰۷۹۱۱ ۱۲۳۴۵۶", "GB", "+447911123456"),
    ("0112345678", "SA", "+966112345678"),
])
def test_parse_with_the_selected_country(raw, region, e164):
    assert parse_phone(raw, region).e164 == e164


@pytest.mark.parametrize("raw,region,code", [
    ("", "SA", "phone_required"),
    ("05012a34567", "SA", "phone_not_a_number"),
    ("0501234", "SA", "phone_too_short"),
    ("05012345678901", "SA", "phone_too_long"),
    ("07911 123456", "SA", "phone_invalid_for_country"),  # a UK number with Saudi selected: never guessed
    ("+999 123456", "SA", "phone_country_unknown"),
])
def test_refusals_say_what_is_wrong(raw, region, code):
    with pytest.raises(PhoneInvalid) as caught:
        parse_phone(raw, region)
    assert caught.value.code == code


def test_an_unknown_region_is_refused_not_ignored():
    with pytest.raises(PhoneInvalid) as caught:
        parse_phone("0501234567", "XX")
    assert caught.value.code == "phone_country_unknown"
