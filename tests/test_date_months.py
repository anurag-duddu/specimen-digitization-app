"""The month words the date parser reads, by language."""

from __future__ import annotations

import pytest

from specimen_digitization.application import date_months
from specimen_digitization.application.date_months import (
    MONTH_WORDS,
    MONTH_WORDS_BY_LANGUAGE,
    fold,
    month_of,
)
from specimen_digitization.application.field_validators import MONTH_NAMES

E_ACUTE = "\N{LATIN SMALL LETTER E WITH ACUTE}"
U_CIRCUMFLEX = "\N{LATIN SMALL LETTER U WITH CIRCUMFLEX}"
A_UMLAUT = "\N{LATIN SMALL LETTER A WITH DIAERESIS}"
C_CEDILLA = "\N{LATIN SMALL LETTER C WITH CEDILLA}"

FULL_NAMES = {
    "en": "january february march april may june july august september october november december",
    "es": "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre",
    "fr": "janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre",
    "de": "januar februar marz april mai juni juli august september oktober november dezember",
    "pt": "janeiro fevereiro marco abril maio junho julho agosto setembro outubro novembro dezembro",
    "it": "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre",
    "la": "januarius februarius martius aprilis maius junius julius augustus september october november december",
}


def test_the_seven_languages_are_in_the_table():
    assert set(MONTH_WORDS_BY_LANGUAGE) == {"en", "es", "fr", "de", "pt", "it", "la"}


@pytest.mark.parametrize("language", sorted(FULL_NAMES))
def test_each_language_names_its_twelve_months(language):
    for number, name in enumerate(FULL_NAMES[language].split(), 1):
        assert MONTH_WORDS_BY_LANGUAGE[language][name] == number, name
        assert month_of(name) == number


def test_a_word_two_languages_share_means_the_same_month_in_both():
    seen: dict[str, int] = {}
    for words in MONTH_WORDS_BY_LANGUAGE.values():
        for word, month in words.items():
            assert seen.setdefault(word, month) == month, word
    assert seen == MONTH_WORDS


def test_a_word_that_is_two_months_stops_the_table_loading(monkeypatch):
    first = (("aaa",),) + (("bbb",),) * 11
    second = (("bbb",),) + (("ccc",),) * 11
    monkeypatch.setattr(date_months, "_OTHER", {"xx": first, "yy": second})

    with pytest.raises(ValueError, match="bbb"):
        date_months._build()


@pytest.mark.parametrize(
    ("word", "month"),
    [
        ("sept.", 9), ("Sept.", 9), ("sept", 9), ("SEPT", 9), ("ene.", 1), ("janv.", 1),
        ("Mai", 5), ("mars", 3), ("Okt.", 10), ("agosto", 8), ("Sep", 9), ("set.", 9),
        (f"f{E_ACUTE}v.", 2), (f"Ao{U_CIRCUMFLEX}t", 8), (f"M{A_UMLAUT}rz", 3),
        (f"mar{C_CEDILLA}o", 3), ("Septembris", 9), ("Decembris", 12),
    ],
)
def test_a_word_reads_with_or_without_its_period_accent_or_case(word, month):
    assert month_of(word) == month


@pytest.mark.parametrize("word", ["", "p", "Mossy", "forest", "Roman", "xx", "sun", "I", "IX"])
def test_a_word_that_is_no_month_is_none(word):
    assert month_of(word) is None


def test_the_english_names_read_as_they_did_before():
    months = ("january february march april may june july august september october "
        "november december").split()
    # The first three and four letters of each name, and the name (origin/main's rule).
    before = {n: i for i, full in enumerate(months, 1) for n in (full[:3], full[:4], full)}

    assert MONTH_NAMES == before
    assert MONTH_NAMES["sept"] == MONTH_NAMES["september"] == 9


def test_folding_drops_accents_and_keeps_case():
    assert fold(f"F{E_ACUTE}vrier") == "Fevrier"
    assert fold("IX") == "IX"
