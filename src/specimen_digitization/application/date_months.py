"""The month words a label writes, in the languages its collectors wrote in.

English, Spanish, French, German, Portuguese, Italian and Latin, each as the
full name and the abbreviations a label uses, with or without its period
(`sept.` and `sept` are one entry). The table is one word to one month: a word
two languages share (`mar`, `sept`, `mai`) must mean the same month in both, and
the table refuses to load otherwise, so a reading is never a choice of language.
Words are folded (accents dropped, lower case) before they are looked up, so
the accented spellings of the French February and August, the German March and
the Portuguese March are `fev`, `aout`, `marz` and `marco`.

Nothing here is a Roman numeral: those are the profile's rule (G29).
"""

from __future__ import annotations

import unicodedata

# English keeps the parser's original rule (the first three and four letters
# of the name, and the name), so every abbreviation it read before it still reads.
_ENGLISH = ("january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december")

# Month number -> the words (full names, then abbreviations) of each language.
_OTHER: dict[str, tuple[tuple[str, ...], ...]] = {
    "es": (
        ("enero", "ene"), ("febrero", "feb"), ("marzo", "mar", "mzo"),
        ("abril", "abr"), ("mayo", "may"), ("junio", "jun"), ("julio", "jul"),
        ("agosto", "ago", "agto"), ("septiembre", "setiembre", "sep", "sept", "set", "sbre"),
        ("octubre", "oct", "obre"), ("noviembre", "nov", "nbre"), ("diciembre", "dic", "dbre"),
    ),
    "fr": (
        ("janvier", "janv", "jan"), ("fevrier", "fevr", "fev"), ("mars", "mar"),
        ("avril", "avr"), ("mai",), ("juin",), ("juillet", "juil", "juill"),
        ("aout",), ("septembre", "sept", "sep"), ("octobre", "oct"),
        ("novembre", "nov"), ("decembre", "dec"),
    ),
    "de": (
        ("januar", "janner", "jaenner", "jan"), ("februar", "feber", "feb"),
        ("marz", "maerz", "mrz", "mar"), ("april", "apr"), ("mai",), ("juni", "jun"),
        ("juli", "jul"), ("august", "aug"), ("september", "sept", "sep"),
        ("oktober", "okt"), ("november", "nov"), ("dezember", "dez"),
    ),
    "pt": (
        ("janeiro", "jan"), ("fevereiro", "fev"), ("marco", "mar"), ("abril", "abr"),
        ("maio", "mai"), ("junho", "jun"), ("julho", "jul"), ("agosto", "ago"),
        ("setembro", "set", "sep", "sept"), ("outubro", "out"), ("novembro", "nov"),
        ("dezembro", "dez"),
    ),
    "it": (
        ("gennaio", "gen", "genn"), ("febbraio", "feb", "febbr"), ("marzo", "mar"),
        ("aprile", "apr"), ("maggio", "mag"), ("giugno", "giu"), ("luglio", "lug"),
        ("agosto", "ago"), ("settembre", "sett", "set"), ("ottobre", "ott"),
        ("novembre", "nov"), ("dicembre", "dic"),
    ),
    # Classical names, the genitives labels use after the day ("die 3 Septembris"),
    # and the shared abbreviations.
    "la": (
        ("ianuarius", "januarius", "ianuarii", "januarii", "ian"),
        ("februarius", "februarii", "febr"), ("martius", "martii", "mart"),
        ("aprilis", "apr"), ("maius", "maii", "maj"),
        ("iunius", "junius", "iunii", "junii", "iun"),
        ("iulius", "julius", "iulii", "julii", "iul"),
        ("augustus", "augusti", "aug"), ("september", "septembris", "sept"),
        ("october", "octobris", "oct"), ("november", "novembris", "nov"),
        ("december", "decembris", "dec"),
    ),
}


def fold(text: str) -> str:
    """The text with its accents dropped and its letters otherwise as written
    (the French August is "Aout", the German March "Marz"); case is kept, for
    the Roman numerals."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _english() -> dict[str, int]:
    return {word: number for number, full in enumerate(_ENGLISH, 1)
        for word in (full[:3], full[:4], full)}


def _build() -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    by_language: dict[str, dict[str, int]] = {"en": _english()}
    for language, months in _OTHER.items():
        assert len(months) == 12, language
        by_language[language] = {word: number for number, words in enumerate(months, 1)
            for word in words}
    merged: dict[str, int] = {}
    for language, words in by_language.items():
        for word, number in words.items():
            if merged.setdefault(word, number) != number:
                raise ValueError(f"{word!r} is two months in the date vocabulary ({language})")
    return merged, by_language


# The folded lower-case word (no period) -> the month it names, 1 to 12.
MONTH_WORDS, MONTH_WORDS_BY_LANGUAGE = _build()


def month_of(word: str) -> int | None:
    """The month a word names, in any of the languages, or None."""
    return MONTH_WORDS.get(fold(word).rstrip(".").lower())
