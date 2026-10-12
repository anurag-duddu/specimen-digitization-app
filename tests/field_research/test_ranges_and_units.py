"""The follow-up to PR #305's approving review (issue comment 6103945603,
its non-blocking notes 1 to 6): the range, distance, date and unit rules of
field_research.written refused values the label supports, and let a few
through it does not. Each case says what the pre-fix main (d0df94b97) did.

Labels from Guatemala, Costa Rica, Mexico, Brazil, the United States,
Germany, the Netherlands, France and Italy.
"""

from __future__ import annotations

import unicodedata

import pytest
from pydantic_ai import ModelRetry
from test_agreement import checked, label, label_3, uncandidated
from test_step import Scripted, answering, settle

from specimen_digitization.application.domain import ValueState
from specimen_digitization.field_research import agreement, written
from specimen_digitization.field_research.contracts import FieldAnswer

A_ACUTE, I_ACUTE, U_UMLAUT, O_UMLAUT = ("\N{LATIN SMALL LETTER A WITH ACUTE}", "\N{LATIN SMALL LETTER I WITH ACUTE}",
    "\N{LATIN SMALL LETTER U WITH DIAERESIS}", "\N{LATIN SMALL LETTER O WITH DIAERESIS}")
COBAN = "Cob" + A_ACUTE + "n"


def refused(key, line, literal):
    """agreement.refusal of the literal read from the transcript of one
    label whose two readers write the line: its reason, or None when it
    settles."""
    readings = label(line + "\nleg. J. Smith")
    found = agreement.refusal(uncandidated(key), readings, literal=literal, named=list(readings), value=None,
        authority_id=None, cited=[], received=[])
    return None if found is None else found.reason


# ---- Note 1: a range joins like with like ------------------------------------
# A bare number joined anything, so an elevation or a date followed by a
# joiner and a distance or a count was refused as one end of a range. Two
# ends make a range only when they are of one kind (written._kind,
# written._alike): a unit, a date, or another kind (written.OTHER_UNITS: a
# distance, a count, a sex, an hour), with or without bare numbers.

LIKE_WITH_LIKE = {
    # An elevation, then a distance: Guatemala, Germany, Costa Rica.
    "dash-then-km": ("elevation_from_m", "1500 m - 5 km W of " + COBAN, "1500 m"),
    "and-then-km": ("elevation_from_m", "1500 m and 5 km W of " + COBAN, "1500 m"),
    "slash-then-km": ("elevation_from_m", "1500 m / 5 km W", "1500 m"),
    "german-und-km": ("elevation_from_m", "Berg 1200 m und 3 km N", "1200 m"),
    "spanish-y-km": ("elevation_from_m", "Volc" + A_ACUTE + "n Barva 2000 msnm y 3 km al N", "2000 msnm"),
    # An elevation or a date, then a count: the Netherlands, England, France, Brazil and Italy.
    "dutch-en-count": ("date_visited_from", "24.IV.1948 en 2 ex.", "24.IV.1948"),
    "and-others": ("date_visited_from", "IV-24-48 and 2 others", "IV-24-48"),
    "french-et-count": ("date_visited_from", "24.VI.1952 et 3 ex.", "24.VI.1952"),
    "slash-females": ("date_visited_from", "24.IV.1948 / 3 \N{FEMALE SIGN}", "24.IV.1948"),
    "portuguese-e-count": ("elevation_from_m", "1200 m e 2 ex.", "1200 m"),
    # A word of two numbers beside the value, of another kind: hours, an elevation range, a day range.
    "glued-hours": ("date_visited_from", "24.IV.1948 10-12 h", "24.IV.1948"),
    "glued-elevation-range": ("date_visited_from", "IV-24-48 1200-1500 m", "IV-24-48"),
    "glued-day-range": ("elevation_from_m", "1200 m 10-12 Sept. 1946", "1200 m"),
    # A range of the other field in the same clause, joined by a word.
    "elevation-range-beside-a-date": ("date_visited_from", "IV-24-48 1200 to 1500 m", "IV-24-48"),
}


@pytest.mark.parametrize(("key", "line", "literal"), LIKE_WITH_LIKE.values(), ids=LIKE_WITH_LIKE)
def test_a_value_beside_a_joiner_and_text_of_another_kind_settles(key, line, literal):
    """On d0df94b97 each is refused as one end of a range."""
    assert refused(key, line, literal) is None


STILL_RANGES = {
    # The other end of the same kind, or a bare number that takes the other end's kind.
    "day-range-before-its-month": ("date_visited_from", "1200 m 10-12 Sept. 1946", "Sept. 1946"),
    "elevation-range-beside-a-date": ("elevation_from_m", "IV-24-48 1200 - 1500 m", "1500 m"),
    "bare-days-then-a-month": ("date_visited_from", "5 to 7 May 1948", "7 May 1948"),
    "roman-month-after-the-day": ("date_visited_from", "24 IV a 2 V 1948", "2 V 1948"),
    "bare-day-then-a-date": ("date_visited_from", "24 al 30-IV-1948", "30-IV-1948"),
    "bare-start-then-metres": ("elevation_from_m", "1200 to 1500 m, 2 ex.", "1500 m"),
    # Nothing marks a bare number's kind: it stays a range's end.
    "bare-glued-word-beside-a-date": ("date_visited_from", "24.IV.1948 10-12", "24.IV.1948"),
    "bare-number-after-a-date": ("date_visited_from", "IV-24-48 - 1200", "IV-24-48"),
}


@pytest.mark.parametrize(("key", "line", "literal"), STILL_RANGES.values(), ids=STILL_RANGES)
def test_one_end_of_a_range_of_one_kind_is_still_refused(key, line, literal):
    """The control: each is refused, as on d0df94b97."""
    assert refused(key, line, literal) == agreement.PART_OF_RANGE


def test_the_ends_kinds_are_read_from_what_is_written_after_them():
    """The kinds written.ranges reads: a distance or a count after the
    second end makes no range with an elevation or a date; a month after it
    makes a date."""
    def ranges(line):
        return written.ranges(line, written.pieces(line, written.words(line)))

    assert ranges("1500 m - 5 km W") == [] and ranges("24.IV.1948 en 2 ex.") == []
    [found] = ranges("24 IV a 2 V 1948")
    assert found.marked and found.kinds == frozenset({written.DATE_KIND})
    [found] = ranges("2 to 5 km N")
    assert not found.marked and found.kinds == frozenset({written.BARE, "distance"})


def test_the_experts_check_keeps_a_date_beside_a_count():
    """The expert's own check, parse_date run on the date: on d0df94b97 it
    sends "24.IV.1948" of "24.IV.1948 en 2 ex." back as a range's end."""
    readings = label("Gelderland, 24.IV.1948 en 2 ex.\nleg. J. de Vries")
    kept = checked(uncandidated("date_visited_from"), readings, dict(outcome="resolved", literal="24.IV.1948",
        reading_names=["3A", "3B"], value="1948-04-24"), checks=[("parse_date", "24.IV.1948")])
    assert kept.literal == "24.IV.1948"


# A word that ended in a comma was left out of its clause, so a range whose
# second end the comma follows was no range: both ends of "IV-24-48 to
# V-2-48, Yepocapa" settled a date. The clause's words are now cut at its
# comma (agreement._in_a_range).

CLAUSE_ENDS_AT_A_COMMA = {
    "second-end-before-a-comma": ("date_visited_from", "IV-24-48 to V-2-48, Yepocapa", "V-2-48"),
    "first-end-before-a-comma": ("date_visited_to", "IV-24-48 to V-2-48, Yepocapa", "IV-24-48"),
    "month-day-range-then-year": ("date_visited_from", "May 2 to 5, 1948", "May 2"),
    "semicolon": ("date_visited_from", "24.IV.1948 bis 2.V.1948; Bayern", "2.V.1948"),
}


@pytest.mark.parametrize(("key", "line", "literal"), CLAUSE_ENDS_AT_A_COMMA.values(), ids=CLAUSE_ENDS_AT_A_COMMA)
def test_a_range_whose_second_end_a_comma_follows_is_still_a_range(key, line, literal):
    """On d0df94b97 each settles."""
    assert refused(key, line, literal) == agreement.PART_OF_RANGE


# ---- Note 2: distance words ----------------------------------------------------
# written.DISTANCE_AFTER knew compass points and "of", "from" and their kin:
# a locality with "along", "upstream", "above" and the like was refused as
# holding an elevation, and its expert, told to leave the number out, could
# settle only the locality cut short (written.RELATIONS).

DISTANCES = {
    "along": "500 m along road to " + COBAN,
    "upstream": "Rio Negro, 200 m upstream of ford",
    "downstream": "Rio Dulce, 500 m downstream of the dam",
    "above-the-bridge": "5 km S of Yepocapa, 100 m above the bridge",
    "below": "Salto Grande, 50 m below the falls",
    "past": "Trail, 500 m past the bridge",
    "beyond": "300 m beyond the gate, Finca Moca",
    "before": "200 m before the bridge, Ruta 7",
    "after": "Carretera a " + COBAN + ", 400 m after the bridge",
    "inland": "Playa Grande, 500 m inland",
    "upstream-alone": "Rio Negro, 500 m upstream",
    "spanish-arriba": "R" + I_ACUTE + "o Negro, 300 m arriba del puente",
    "spanish-abajo": "R" + I_ACUTE + "o Negro, 300 m abajo del puente",
    "portuguese-acima": "Rio Doce, 200 m acima da ponte",
    "portuguese-abaixo": "Rio Doce, 200 m abaixo da ponte",
    "german-oberhalb": "Titisee, 300 m oberhalb der Br" + U_UMLAUT + "cke",
    "german-unterhalb": "Titisee, 300 m unterhalb der Br" + U_UMLAUT + "cke",
}


@pytest.mark.parametrize("literal", DISTANCES.values(), ids=DISTANCES)
def test_a_locality_holding_a_distance_settles(literal):
    """On d0df94b97 each is refused as holding an elevation."""
    assert refused("precise_location", literal, literal) is None


ELEVATIONS_AFTER_A_DISTANCE_WORD = {
    # Sea level or altitude after the word: an elevation (English, Portuguese, German, Spanish).
    "above-sea-level": "Finca Moca, 1500 m above sea level",
    "portuguese-acima-do-nivel": "Serra do Mar, 900 m acima do n" + I_ACUTE + "vel do mar",
    "german-oberhalb-des-meeres": "Schwarzwald, 800 m oberhalb des Meeresspiegels",
    # Nothing after the word in its clause: above what is not written.
    "above-nothing": "Finca Moca, 1500 m above",
    "abajo-then-comma": "Finca Moca, 1500 m abajo, " + COBAN,
}


@pytest.mark.parametrize("literal", ELEVATIONS_AFTER_A_DISTANCE_WORD.values(), ids=ELEVATIONS_AFTER_A_DISTANCE_WORD)
def test_an_elevation_above_sea_level_is_still_an_elevation(literal):
    """The control: each is refused, as on d0df94b97."""
    assert refused("precise_location", literal, literal) == agreement.HOLDS_AN_ELEVATION


def test_an_elevation_de_altitud_is_an_elevation():
    """"de" is a distance word ("500 m de la carretera"), but "de altitud"
    is the elevation's: on d0df94b97 the locality settles."""
    assert refused("precise_location", COBAN + ", 1500 m de altitud", COBAN + ", 1500 m de altitud") == (
        agreement.HOLDS_AN_ELEVATION)
    assert refused("precise_location", "2 km al S de Antigua, 300 m de la carretera",
        "2 km al S de Antigua, 300 m de la carretera") is None


def test_the_elevation_fields_still_settle_an_elevation_above_sea_level():
    """The control: as on d0df94b97."""
    assert refused("elevation_from_m", "1500 m above sea level", "1500 m") is None
    assert refused("elevation_from_ft", "4800 ft above sea level", "4800") is None


def test_the_experts_check_keeps_a_locality_upstream_of_a_place():
    """The review's probe: on d0df94b97 the locality is sent back as holding
    an elevation."""
    readings = label("Rio Negro, 200 m upstream of ford\nleg. J. Smith")
    kept = checked(uncandidated("precise_location"), readings, dict(outcome="resolved",
        literal="Rio Negro, 200 m upstream of ford", reading_names=["3A", "3B"]))
    assert kept.literal == "Rio Negro, 200 m upstream of ford"


def test_the_step_settles_a_locality_holding_a_distance(tmp_path):
    """Through the step, no other field claiming the text: on d0df94b97 the
    locality goes to review as holding an elevation."""
    text = "Rio Doce, 200 m abaixo da ponte\nIV-23-48\nleg. anon."
    rig = label_3(tmp_path, text, text, [])
    run = rig.specimen.run
    settle(rig, Scripted({"precise_location": answering(FieldAnswer(outcome="resolved",
        literal="Rio Doce, 200 m abaixo da ponte", reading_names=["1A", "1B"], explanation="Both write it."))}))
    assert run.fields["precise_location"].state == ValueState.SUPPORTED


# ---- Note 3: places with numbers ----------------------------------------------
# The year rule reached place text: a number after a road, km, hill, farm or
# estate word was refused as a date, as was a road's code read as a month
# and day (written.PLACE_WORDS). Only in a place's text, and only right
# after the word.

PLACES_WITH_NUMBERS = {
    "hill": ("precise_location", "Hill 1800"),
    "texas-farm-to-market-road": ("precise_location", "FM 1960, Harris Co."),
    "brazil-km-post": ("precise_location", "BR-116 km 1850"),
    "interstate-code": ("precise_location", "Hwy I-5, 3 mi N of Redding"),
    "mexico-street": ("precise_location", "Calle 5 de Mayo, " + COBAN),
    "spanish-hill": ("precise_location", "Cerro 1850, Sierra de las Minas"),
    "portuguese-road": ("precise_location", "Rodovia 1960, km 12"),
    "farm": ("precise_location", "Fazenda 1890, Minas Gerais"),
    "spanish-route": ("precise_location", "Ruta 1960, 5 km al N"),
}


@pytest.mark.parametrize(("key", "literal"), PLACES_WITH_NUMBERS.values(), ids=PLACES_WITH_NUMBERS)
def test_a_number_right_after_a_road_hill_or_farm_word_is_part_of_the_place(key, literal):
    """On d0df94b97 each is refused as holding a date."""
    assert refused(key, literal, literal) is None


STILL_DATES = {
    # Another word between the farm word and the year: the farm, then the year it was collected.
    "farm-name-then-year": ("precise_location", "Finca Moca 1948"),
    "place-then-year": ("province_state", "Davao 1948"),
    "road-number-then-year": ("precise_location", "Route 66 1948"),
    # A date and a camp, or a camp named for a date: in doubt.
    "month-day-then-camp": ("precise_location", "May 5 Camp, Alaska"),
    # A surname that is also a hill word, after initials or a collector's mark.
    "initials-then-surname": ("precise_location", COBAN + ", J. Hill 1948"),
    "collector-mark-then-surname": ("precise_location", "Schwarzwald, leg. Berg 1948"),
    # A code may write a date: a Roman month and a day, a Roman month and a year, a year after "FM".
    "code-roman-month-day": ("collection_code", "X-12"),
    "code-roman-month-year": ("collection_code", "IV-1948"),
    "code-after-a-road-word": ("collection_code", "FM 1960"),
}


@pytest.mark.parametrize(("key", "literal"), STILL_DATES.values(), ids=STILL_DATES)
def test_a_year_or_a_date_not_right_after_a_place_word_is_still_a_date(key, literal):
    """The control: each is refused, as on d0df94b97."""
    assert refused(key, literal, literal) == agreement.HOLDS_A_DATE


# ---- Note 4: a capital "M" -----------------------------------------------------
# The unit-before rule read a code's "M" or a collector's initial as metres,
# and a count of males and females as an elevation.

def test_a_capital_m_before_a_number_is_no_unit():
    """On d0df94b97 each code is refused as holding an elevation, and
    "1200" after a capital "M" settles elevation_from_m."""
    assert refused("collection_code", "M 12", "M 12") is None
    assert refused("collection_code", "M. 12", "M. 12") is None
    assert refused("elevation_from_m", "M 1200", "1200") == agreement.NO_UNIT
    assert refused("elevation_from_m", "M. 1200", "1200") == agreement.NO_UNIT


def test_a_count_of_males_and_females_is_no_elevation():
    """On d0df94b97 each locality is refused as holding an elevation."""
    assert refused("precise_location", "Finca Moca, 3 M. 2 F.", "Finca Moca, 3 M. 2 F.") is None
    assert refused("precise_location", "Finca Moca, 2 F. 3 M.", "Finca Moca, 2 F. 3 M.") is None


def test_a_capital_m_before_a_name_is_no_unit():
    """The number before a collector's initial is written in no unit: on
    d0df94b97 "1200" settles elevation_from_m and "4800" is refused from
    elevation_from_ft as metres."""
    assert refused("elevation_from_m", "lot 1200 M. Smith", "1200") == agreement.NO_UNIT
    assert refused("elevation_from_ft", "Trap 4800 M. Smith", "4800") == agreement.NO_UNIT


@pytest.mark.parametrize(("key", "line", "literal", "reason"), [
    # Feet before the initial, a capital "M" with nothing after it, Italian metres before the number.
    ("elevation_from_ft", "4800 ft. M. Smith", "4800", None),
    ("elevation_from_m", "ALT. 1500 M", "1500 M", None),
    ("elevation_from_ft", "ALT. 1500 M", "1500 M", "UNIT_DIFFERS"),
    ("elevation_from_m", "Alpi Apuane, m 1200", "m 1200", None),
    # A lower-case "m" before a number is still metres in a code; a capital "M" before a name or a
    # number may still be metres in a place.
    ("collection_code", "m 12", "m 12", "HOLDS_AN_ELEVATION"),
    ("precise_location", "Trap 4800 M. Smith", "Trap 4800 M. Smith", "HOLDS_AN_ELEVATION"),
    ("precise_location", "Alpi Apuane, M 1200", "Alpi Apuane, M 1200", "HOLDS_AN_ELEVATION"),
    ("precise_location", "Alpi Apuane, M. 1200", "Alpi Apuane, M. 1200", "HOLDS_AN_ELEVATION"),
], ids=["feet-then-initial", "capital-m-at-the-end", "capital-m-as-feet", "italian-unit-first", "code-lower-case-m",
    "place-with-m-before-a-name", "place-with-m-before-a-number", "place-with-m-period-before-a-number"])
def test_a_capital_m_that_is_metres_still_is(key, line, literal, reason):
    """The control: as on d0df94b97."""
    assert refused(key, line, literal) == (None if reason is None else getattr(agreement, reason))


# ---- Note 5: the gaps ----------------------------------------------------------

ELEVATIONS_IN_A_PLACE = {
    # A comma after the unit ends the clause: the compass point is the slope's.
    "comma-then-compass": "Finca Moca, 1500 m, N slope",
    "comma-then-two-letter-compass": "Finca Moca, 1500 m, NE slope",
    # A compass point that names a mountain's side, and a heading before the number.
    "compass-then-slope": "Finca Moca 1500 m N slope",
    "heading-then-compass-side": "Finca Moca, alt. 1500 m E side",
    "spanish-ladera": "Volc" + A_ACUTE + "n Barva 2600 m S ladera",
    # A heading and a bare number: Guatemala, Germany, Costa Rica.
    "heading-bare-number": COBAN + ", alt. 1200",
    "elev-bare-number": "Finca Moca, elev. 1200",
    "german-hohe": "Feldberg, H" + O_UMLAUT + "he 1400",
    "spanish-cota": "Volc" + A_ACUTE + "n Barva, cota 2500",
}


@pytest.mark.parametrize("literal", ELEVATIONS_IN_A_PLACE.values(), ids=ELEVATIONS_IN_A_PLACE)
def test_a_locality_holding_an_elevation_written_so_is_refused(literal):
    """On d0df94b97 each settles."""
    assert refused("precise_location", literal, literal) == agreement.HOLDS_AN_ELEVATION


def test_a_heading_and_a_year_shaped_number_is_an_elevation():
    """On d0df94b97 it is refused as holding a date."""
    assert refused("precise_location", COBAN + ", alt. 1800", COBAN + ", alt. 1800") == agreement.HOLDS_AN_ELEVATION
    assert written.other_kind(COBAN + ", alt. 1800", place=True) == (written.ELEVATION, "alt. 1800")


@pytest.mark.parametrize("literal", [
    "Yepocapa, 500 m N",
    "Finca Moca 1500 m S. of town",
    "Cerro 1200 m N de " + COBAN,
    "Yepocapa, 500 m al N",
], ids=["compass-at-the-end", "compass-then-of", "compass-then-spanish-de", "spanish-al-then-compass"])
def test_a_distance_by_a_compass_point_still_settles(literal):
    """The control: each settles, as on d0df94b97."""
    assert refused("precise_location", literal, literal) is None


def test_a_heading_and_a_bare_number_still_settles_no_unit_field():
    """The control: as on d0df94b97."""
    assert refused("elevation_from_m", COBAN + ", alt. 1200", "1200") == agreement.NO_UNIT
    assert refused("elevation_from_ft", "Elev. 1200", "Elev. 1200") == agreement.NO_UNIT


# Every dash of Unicode's dash punctuation (Pd), by name, as Unicode 14.0,
# 15.0 and 15.1 list them; never read from this Python's unicodedata, as
# CI's Python has another Unicode.
PD_NAMES = (
    "HYPHEN-MINUS", "ARMENIAN HYPHEN", "HEBREW PUNCTUATION MAQAF", "CANADIAN SYLLABICS HYPHEN",
    "MONGOLIAN TODO SOFT HYPHEN", "HYPHEN", "NON-BREAKING HYPHEN", "FIGURE DASH", "EN DASH", "EM DASH",
    "HORIZONTAL BAR", "DOUBLE OBLIQUE HYPHEN", "HYPHEN WITH DIAERESIS", "TWO-EM DASH", "THREE-EM DASH",
    "DOUBLE HYPHEN", "OBLIQUE HYPHEN", "WAVE DASH", "WAVY DASH", "KATAKANA-HIRAGANA DOUBLE HYPHEN",
    "PRESENTATION FORM FOR VERTICAL EM DASH", "PRESENTATION FORM FOR VERTICAL EN DASH", "SMALL EM DASH",
    "SMALL HYPHEN-MINUS", "FULLWIDTH HYPHEN-MINUS", "YEZIDI HYPHENATION MARK",
)
# Dash-like signs of other categories that labels write for one.
OTHER_DASH_NAMES = ("MINUS SIGN", "SWUNG DASH", "FULLWIDTH TILDE", "HYPHEN BULLET", "TILDE OPERATOR")


@pytest.mark.parametrize("name", PD_NAMES + OTHER_DASH_NAMES)
def test_every_dash_by_name_joins_a_range(name):
    """On d0df94b97 18 of these 31 are no joiners (among them the Armenian
    hyphen, the Hebrew maqaf, the two-em dash, the hyphen bullet and the
    tilde operator): "1500 m" of "1200 <dash> 1500 m" settles. The other 13
    are the control."""
    dash = unicodedata.lookup(name)
    assert dash in written.DASHES
    assert refused("elevation_from_m", f"1200 {dash} 1500 m", "1500 m") == agreement.PART_OF_RANGE


def test_the_pd_dashes_are_pinned_by_name():
    """The table holds the 26 by name, each a Pd character; whether a later
    Unicode adds another is not asserted."""
    assert written.PD_DASHES == frozenset(unicodedata.lookup(name) for name in PD_NAMES)
    assert {unicodedata.category(dash) for dash in written.PD_DASHES} == {"Pd"}


@pytest.mark.parametrize("line", [
    "1200 --- 1500 m", "1200 ---- 1500 m", "1200 \N{EN DASH}\N{EN DASH}\N{EN DASH} 1500 m",
], ids=["three-hyphens", "four-hyphens", "three-en-dashes"])
def test_a_run_of_dashes_of_any_length_joins_a_range(line):
    """On d0df94b97 a run of more than two dashes joins none: "1500 m"
    settles."""
    assert refused("elevation_from_m", line, "1500 m") == agreement.PART_OF_RANGE


JOINERS_OF_SEVERAL_WORDS = {
    "german-bis-zum": ("date_visited_from", "vom 24.IV.1948 bis zum 2.V.1948", "2.V.1948"),
    "dutch-tot-en-met": ("date_visited_from", "24.IV tot en met 2.V.1948", "2.V.1948"),
    "spanish-hasta-el": ("date_visited_from", "desde el 24 hasta el 30.IV.1948", "30.IV.1948"),
    "german-bis-zum-elevation": ("elevation_from_m", "von 1200 bis zum 1500 m", "1500 m"),
}


@pytest.mark.parametrize(("key", "line", "literal"), JOINERS_OF_SEVERAL_WORDS.values(), ids=JOINERS_OF_SEVERAL_WORDS)
def test_a_joiner_of_several_words_joins_a_range(key, line, literal):
    """On d0df94b97 each settles: "zum", "met" and "el" joined nothing."""
    assert refused(key, line, literal) == agreement.PART_OF_RANGE


def test_a_later_word_of_a_joiner_joins_nothing_alone():
    """The control: "zum" with no joiner before it, as on d0df94b97."""
    assert refused("date_visited_from", "24.IV.1948 zum Berg 2 km", "24.IV.1948") is None


# ---- Note 6: the window for words beside a number ------------------------------

def test_four_pieces_may_stand_between_an_end_and_its_joiner():
    """The window written.BESIDE_WORDS counts the end's own piece, as the
    docs now say: four pieces beside the number join a range, a fifth
    leaves the end outside it. The same on d0df94b97."""
    four = "1200 m a. s. l. to 1500 m"
    assert len(written.ranges(four, written.pieces(four, written.words(four)))) == 1
    five = "1200 m a. s. l. ca. to 1500 m"
    assert written.ranges(five, written.pieces(five, written.words(five))) == []


# ---- the tables and the briefs ---------------------------------------------------

def test_no_word_of_another_kind_is_a_unit_a_month_or_a_joiner():
    """written.OTHER_UNITS shares no word with the tables a range's end and
    its joiner are read from."""
    words = frozenset(written.OTHER_OF)
    assert not words & (written.BESIDE_A_NUMBER | written.JOINERS | written.CONTINUATIONS | frozenset(written.UNIT_OF))
    assert not written.CONTINUATIONS & written.JOINERS


def test_the_briefs_say_what_the_rules_read():
    """The shared brief's range and unit lines and the locality brief name
    the new rules, as patterns."""
    from specimen_digitization.field_research.prompts import instructions

    range_line, unit_line = written.range_line(), written.unit_line()
    assert '"bis zum"' in range_line and '"tot en met"' in range_line and '"hasta el"' in range_line
    assert "a distance, a count or an hour beside an elevation or a date makes no range" in range_line
    assert 'A capital "M" is no unit before a number ("M <n>", "M. <n>")' in unit_line
    locality = instructions("precise_location")
    assert '"<n> m upstream of <Place>"' in locality and '"<Place>, alt. <n>"' in locality
    assert '"<Place>, <n> m, N slope"' in locality and '("km <n>", "Hill <n>")' in locality


# ---- Codex's review of 77fdaeba ------------------------------------------------
# Three wrong settles: an elevation field took a distance as an elevation (on
# d0df94b97 too); a place word followed by a comma or a semicolon kept the date
# after it in the place; a capital "M" before a count of females, across a
# joiner word, or before a name in capitals, was read as metres.

DISTANCES_FOR_AN_ELEVATION_FIELD = {
    "along-road": ("elevation_from_m", "Finca Moca, 1200 m along road", "1200 m"),
    "spanish-arriba": ("elevation_from_m", "Rio Negro, 300 m arriba del puente", "300 m"),
    "upstream-of": ("elevation_from_m", "Rio Negro, 200 m upstream of ford", "200 m"),
    "above-the-bridge": ("elevation_from_m", "5 km S of Yepocapa, 100 m above the bridge", "100 m"),
    "feet-past": ("elevation_from_ft", "Trail, 1500 ft past the bridge", "1500 ft"),
}


@pytest.mark.parametrize(("key", "line", "literal"), DISTANCES_FOR_AN_ELEVATION_FIELD.values(),
    ids=DISTANCES_FOR_AN_ELEVATION_FIELD)
def test_an_elevation_field_never_takes_a_distance(key, line, literal):
    """On 77fdaeba each settles its elevation field."""
    assert refused(key, line, literal) == agreement.A_DISTANCE


def test_an_elevation_above_sea_level_or_by_a_comma_is_still_an_elevation_field_s():
    """The control: as on 77fdaeba."""
    assert refused("elevation_from_m", "Finca Moca, 1500 m above sea level", "1500 m") is None
    assert refused("elevation_from_m", "Finca Moca, 1500 m above", "1500 m") is None
    assert refused("elevation_from_m", "Finca Moca, 1500 m, N slope", "1500 m") is None
    assert refused("elevation_from_m", COBAN + ", 1500 m de altitud", "1500 m") is None


PLACE_WORD_THEN_A_COMMA = {
    "road-comma-year": "Ruta, 1960",
    "hill-semicolon-year": "Hill; 1800",
    "farm-comma-year": "Fazenda, 1948",
    "route-comma-roman-month-year": "Route, IV-1948",
}


@pytest.mark.parametrize("literal", PLACE_WORD_THEN_A_COMMA.values(), ids=PLACE_WORD_THEN_A_COMMA)
def test_a_comma_or_a_semicolon_after_a_place_word_leaves_the_date_a_date(literal):
    """On 77fdaeba each settles the locality."""
    assert refused("precise_location", literal, literal) == agreement.HOLDS_A_DATE


def test_a_count_of_males_beside_females_across_a_joiner_is_no_elevation():
    """On 77fdaeba "3 M." settles elevation_from_m as 3 metres, and each
    locality is refused as holding an elevation."""
    assert refused("elevation_from_m", "Finca Moca, 3 M. and 5 females", "3 M.") is not None
    assert refused("precise_location", "Finca Moca, 3 M. and 5 females", "Finca Moca, 3 M. and 5 females") is None
    assert refused("precise_location", "Finca Moca, 5 females y 3 M.", "Finca Moca, 5 females y 3 M.") is None


def test_a_capital_m_before_a_name_in_capitals_is_no_unit():
    """On 77fdaeba "1200" settles elevation_from_m as metres."""
    assert refused("elevation_from_m", "lot 1200 M. SMITH", "1200") == agreement.NO_UNIT
    # The control: a marker word in capitals after it is no name ("ALT"), as on 77fdaeba.
    assert refused("elevation_from_m", "ALT. 1500 M", "1500 M") is None


def test_a_joiner_that_is_also_a_compass_point_before_a_number_is_no_distance():
    """Portuguese and Italian "e" ("and") is also East: before a number it
    joins, so the elevation is an elevation. On 77fdaeba the locality holding
    it settled, the elevation read as a distance east."""
    assert refused("elevation_from_m", "1200 m e 2 ex.", "1200 m") is None
    assert refused("precise_location", "Serra, 1200 m e 2 ex.", "Serra, 1200 m e 2 ex.") == agreement.HOLDS_AN_ELEVATION
    # The control: a compass point before the place it is measured from is a distance, as on 77fdaeba.
    assert refused("precise_location", "Yepocapa, 500 m E of the bridge", "Yepocapa, 500 m E of the bridge") is None
    assert refused("elevation_from_m", "Yepocapa, 500 m E of the bridge", "500 m") == agreement.A_DISTANCE


PLACE_WORD_THEN_A_PERIOD = {
    "farm-period-year": "Fazenda. 1948",
    "road-period-year": "Ruta. 1960",
    "route-period-year": "Route. 1960",
    "hill-period-year": "Berg. 1960",
    "street-period-year": "Calle. 1960",
}


@pytest.mark.parametrize("literal", PLACE_WORD_THEN_A_PERIOD.values(), ids=PLACE_WORD_THEN_A_PERIOD)
def test_a_period_after_a_whole_place_word_leaves_the_date_a_date(literal):
    """Codex's review of b9f42db6: on b9f42db6 each settles the locality."""
    assert refused("precise_location", literal, literal) == agreement.HOLDS_A_DATE


@pytest.mark.parametrize("literal", ["Hwy. 1960", "Rte. 1960", "km. 1850", "Rd. 1800"])
def test_the_period_of_an_abbreviated_place_word_is_its_own(literal):
    """The control: as on b9f42db6, the number is part of the place."""
    assert refused("precise_location", literal, literal) is None


PLACE_WORD_THEN_A_DATE_WITH_ITS_YEAR = {
    "abbreviation-period-full-date": "Hwy. 24.IV.1948",
    "abbreviation-full-date": "Hwy 24.IV.1948",
    "dotted-abbreviation-full-date": "H.W.Y. 24.IV.1948",
    "route-month-year": "Route IV-1948",
    "farm-month-day-year": "Finca Sept. 3, 1948",
}


@pytest.mark.parametrize("literal", PLACE_WORD_THEN_A_DATE_WITH_ITS_YEAR.values(),
    ids=PLACE_WORD_THEN_A_DATE_WITH_ITS_YEAR)
def test_a_date_with_its_year_after_a_place_word_is_still_a_date(literal):
    """Codex's review of 1b997582: on 1b997582 each settles the locality but
    the last, which a later word's run already refused. Only a bare number or
    a month and a day with no year is the place's."""
    assert refused("precise_location", literal, literal) == agreement.HOLDS_A_DATE


@pytest.mark.parametrize("literal", ['"Fazenda." 1948 collector J. Smith', "(Fazenda.) 1948 collector J. Smith"])
def test_a_period_inside_closing_punctuation_still_ends_the_place_word_s_clause(literal):
    """Codex's review of 1b997582: on 1b997582 each settles the locality."""
    assert refused("precise_location", literal, literal) == agreement.HOLDS_A_DATE


@pytest.mark.parametrize("literal", ["Hwy I-5", "Calle 5 de Mayo", "Hill 1800", "Hwy. 1960"])
def test_a_bare_number_or_a_month_and_day_after_a_place_word_is_still_the_place_s(literal):
    """The control: as on 1b997582."""
    assert refused("precise_location", literal, literal) is None
