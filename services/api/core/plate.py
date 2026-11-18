"""Vehicle plate entry (ADR-0013). The plate is stored as the valet entered it; nothing is transliterated for display.

Saudi plates: three letters from the 17-letter set and one to four digits. The Arabic letters and their Latin
equivalents are verified (Wikipedia "Vehicle registration plates of Saudi Arabia"; syarah.com plate guide). How the
letter positions of the two rows correspond is not stated by those sources, so the other-script form is used only
inside `key`, a search key in reading order: a wrong assumption there can miss a search match but never changes a
plate. Other plates (international, diplomatic, temporary) are kept as typed."""

import re
from dataclasses import dataclass

from core.phone import normalize_digits

AR_TO_LATIN = {"ا": "A", "ب": "B", "ح": "J", "د": "D", "ر": "R", "س": "S", "ص": "X", "ط": "T", "ع": "E", "ق": "G",
               "ك": "K", "ل": "L", "م": "Z", "ن": "N", "هـ": "H", "و": "U", "ى": "V"}
LATIN_LETTERS = set(AR_TO_LATIN.values())
# Keyboard forms of the same plate letter. Only exact equivalents: no look-alikes, no guesses.
_VARIANTS = {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ي": "ى", "ه": "هـ", "ھ": "هـ"}
_STRIP = re.compile(r"[\s\-_.ـ‎‏‪-‮⁦-⁩]")
_ARABIC = re.compile(r"[؀-ۿ]")


class PlateInvalid(ValueError):
    """`code`: plate_letters_count, plate_letter_unknown, plate_mixed_script, plate_digits_count or
    plate_other_invalid."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Plate:
    kind: str          # SAUDI | OTHER
    display: str       # what staff see: as entered
    key: str           # search key, never displayed as the plate
    letters: str = ""
    digits: str = ""
    script: str = ""   # ar | en (Saudi plates)


def _arabic_letters(text: str) -> list[str]:
    """Arabic plate letters, with keyboard variants folded; هـ counts as one letter however it is typed."""
    out = []
    for ch in text:
        ch = _VARIANTS.get(ch, ch)
        if ch == "هـ" or ch in AR_TO_LATIN:
            out.append(ch)
        else:
            raise PlateInvalid("plate_letter_unknown")
    return out


def saudi_plate(letters: str, digits: str) -> Plate:
    raw = _STRIP.sub("", normalize_digits(letters or ""))
    if _ARABIC.search(raw) and re.search(r"[A-Za-z]", raw):
        raise PlateInvalid("plate_mixed_script")
    if _ARABIC.search(raw):
        script, chars = "ar", _arabic_letters(raw)
        latin = "".join(AR_TO_LATIN[c] for c in chars)
    else:
        script, chars = "en", list(raw.upper())
        if any(c not in LATIN_LETTERS for c in chars):
            raise PlateInvalid("plate_letter_unknown")
        latin = "".join(chars)
    if len(chars) != 3:
        raise PlateInvalid("plate_letters_count")
    number = _STRIP.sub("", normalize_digits(digits or ""))
    if not re.fullmatch(r"\d{1,4}", number):
        raise PlateInvalid("plate_digits_count")
    text = "".join(chars)
    return Plate(kind="SAUDI", display=f"{' '.join(chars)} {number}", key=f"{latin}{number}", letters=text,
                 digits=number, script=script)


def other_plate(text: str) -> Plate:
    shown = re.sub(r"\s+", " ", normalize_digits(text or "")).strip().upper()
    key = search_key(shown)
    if not (2 <= len(key) <= 20) or not re.fullmatch(r"[\w\- ]+", shown):
        raise PlateInvalid("plate_other_invalid")
    return Plate(kind="OTHER", display=shown[:40], key=key)


def search_key(text: str) -> str:
    """Digits normalised, Saudi plate letters in either script folded to Latin, spaces and hyphens removed."""
    out = []
    for ch in _STRIP.sub("", normalize_digits(text or "")):
        ch = _VARIANTS.get(ch, ch)
        out.append(AR_TO_LATIN.get(ch, ch))
    return "".join(out).upper()
