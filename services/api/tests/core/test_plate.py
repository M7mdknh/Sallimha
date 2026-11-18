"""Plate entry (ADR-0013): Saudi plates as entered, other plates as typed, a search key that never changes the plate."""

import pytest

from core.plate import PlateInvalid, other_plate, saudi_plate, search_key


def test_arabic_letters_are_kept_in_the_order_entered_with_digit_shapes_normalised():
    plate = saudi_plate("ا ب ح", "١٢٣٤")
    assert (plate.kind, plate.letters, plate.digits, plate.script) == ("SAUDI", "ابح", "1234", "ar")
    assert plate.display == "ا ب ح 1234"
    assert plate.key == "ABJ1234"  # internal search key only; never shown as the plate


def test_latin_entry_is_upper_cased_and_kept_in_order():
    plate = saudi_plate("abj", "۰۷۱")
    assert (plate.letters, plate.digits, plate.script, plate.display, plate.key) == ("ABJ", "071", "en", "A B J 071",
                                                                                       "ABJ071")


def test_keyboard_variants_become_plate_letters():
    assert saudi_plate("أ ي ه", "5").letters == "اىهـ"
    assert saudi_plate("إآ ـبـ", "5").letters == "ااب"


@pytest.mark.parametrize("letters,digits,code", [
    ("ابحد", "12", "plate_letters_count"),    # four letters
    ("اب", "12", "plate_letters_count"),
    ("اب ث", "12", "plate_letter_unknown"),   # ث is not used on Saudi plates: Other plate instead
    ("ABC", "12", "plate_letter_unknown"),    # C is not a Saudi plate letter
    ("اBح", "12", "plate_mixed_script"),
    ("ابح", "", "plate_digits_count"),
    ("ابح", "12345", "plate_digits_count"),
    ("ابح", "12a", "plate_digits_count"),
])
def test_refusals_never_guess(letters, digits, code):
    with pytest.raises(PlateInvalid) as caught:
        saudi_plate(letters, digits)
    assert caught.value.code == code


def test_leading_zeros_are_neither_added_nor_removed():
    assert saudi_plate("ABJ", "0071").digits == "0071"
    assert saudi_plate("ABJ", "71").digits == "71"


def test_other_plates_are_kept_as_typed():
    plate = other_plate("  dxb  a-12345 ")
    assert (plate.kind, plate.display, plate.key) == ("OTHER", "DXB A-12345", "DXBA12345")
    with pytest.raises(PlateInvalid):
        other_plate("x")


def test_search_key_matches_either_script_and_any_spacing():
    key = saudi_plate("ا ب ح", "1234").key
    assert search_key("ABJ 1234") == key
    assert search_key("ا ب ح ١٢٣٤") == key
    assert search_key("abj-1234") == key
    assert search_key("أبح1234") == key
