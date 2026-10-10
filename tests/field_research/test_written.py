"""The tables and readers of field_research.written: how a label joins a
range and writes an elevation's unit, in any language (PR #300's review of
6fd595b3b, finding 1). The guards that use them are tested through
agreement.refusal, the experts' check and the step in test_agreement.
"""

from __future__ import annotations

import unicodedata

import pytest
from test_agreement import label, uncandidated

from specimen_digitization.field_research import agreement, written


@pytest.mark.parametrize("dash", sorted(written.DASHES), ids=lambda dash: unicodedata.name(dash))
def test_every_dash_joins_a_range_standing_alone_or_touching_an_end(dash):
    """Each dash the table pins by name, spaced, touching the first end and
    touching the second: the end is never read alone."""
    for line in (f"1200 {dash} 1500 m", f"1200{dash} 1500 m", f"1200 {dash}1500 m"):
        readings = label(line + "\nleg. J. Smith")
        refused = agreement.refusal(uncandidated("elevation_from_m"), readings, literal="1500 m",
            named=list(readings), value=None, authority_id=None, cited=[], received=[])
        assert refused is not None and refused.reason == agreement.PART_OF_RANGE, line


@pytest.mark.parametrize(("language", "word"), [(language, word) for language, words in written.RANGE_WORDS.items()
    for word in words], ids=lambda value: written.fold(value))
def test_every_range_word_joins_a_range_in_any_letter_case(language, word):
    """Each word of the table, as written and in capitals, between two dates."""
    for joiner in (word, word.upper()):
        line = f"IV-24-48 {joiner} V-2-48"
        readings = label(line + "\nleg. J. Smith")
        refused = agreement.refusal(uncandidated("date_visited_from"), readings, literal="V-2-48",
            named=list(readings), value=None, authority_id=None, cited=[], received=[])
        assert refused is not None and refused.reason == agreement.PART_OF_RANGE, (language, line)


@pytest.mark.parametrize(("text", "folded"), [
    ("\N{LATIN SMALL LETTER A WITH GRAVE}", "a"),
    ("AT\N{LATIN CAPITAL LETTER E WITH ACUTE}", "ate"),
    ("Fu\N{LATIN SMALL LETTER SHARP S}", "fu\N{LATIN SMALL LETTER SHARP S}"),
    ("6400\N{RIGHT SINGLE QUOTATION MARK}", "6400'"),
    ("6400\N{PRIME}", "6400'"),
    ("m \N{LATIN SMALL LETTER U WITH DIAERESIS}. M.", "m u. m."),
])
def test_fold_keeps_one_character_for_one(text, folded):
    assert written.fold(text) == folded and len(written.fold(text)) == len(text)


@pytest.mark.parametrize(("line", "units"), [
    ("alt. 1500 m", ["m"]),
    ("1500 m.s.n.m.", ["m"]),
    ("2000msnm", ["m"]),
    ("Alpi Apuane, m 1200 s.l.m.", ["m"]),
    ("Elev.6400'", ["ft"]),
    ("6400 pies", ["ft"]),
    ("1200 to 1500 m", ["m", "m"]),
    ("1200-1500 ft", ["ft", "ft"]),
    ("4800 ft. / 1463 m", ["ft", "m"]),
    # No unit: "mt" may be Mount, "mm" is no elevation, minutes of arc are no feet.
    ("1200 mt", [None]),
    ("1200 mm", [None]),
    ("7\N{DEGREE SIGN}30' N", [None, None]),
])
def test_the_unit_each_number_is_written_in(line, units):
    assert [number.unit for number in written.numbers(line)] == units
