"""WP 2.4's two date items, from the 2.6 gate forecast (the coordinator's rulings of 2026-11-15), on the units
path only:

1. A Roman month written with a digit one for an I ("1X-14-46", pilot slide 105526325, every reader) is read as
   that month where the date parser then reads a date (checks.digit_one_month; the ontology's notation
   roman_month, its second reading).
2. A month and day ending a line above their year ("IV-25" above "1948, R.D. Mitchell", pilot slide 105526330)
   are one date: the literal of both lines, the year alone, passes the literal check when every condition of
   agreement.year_below and agreement.next_line_year holds, and no other field's settled text sits on the year
   (step._taken). The date briefs say so on the units path (prompts/units.txt).

Every test that builds a run runs on both paths (conftest.py); the old path keeps main's result."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from test_first_pass_advice import with_units
from test_step import COLLECTORS, TEXT, Scripted, answering, build_rig, resolved, settle

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import FieldValue, LookupStatus, ValueState
from specimen_digitization.field_research import agreement, checks
from specimen_digitization.field_research.contracts import Candidate, FieldAnswer, FieldTask, Reading
from specimen_digitization.field_research.experts import Refused, _Expert
from specimen_digitization.field_research.prompts import instructions

RULES = published_registry().profiles[0].date_rules
DATE = "date_visited_from: 2020-06-01"


# ---- 1. a digit one for the I of a Roman month ----------------------------------------------------

@pytest.mark.parametrize(("literal", "text", "units", "old"), [
    # The named cases.
    ("1X-14-46", "Davao 1X-14-46 H. Hoogstraal", ("1946-09-14",), ()),
    ("X1-3-46", "X1-3-46", ("1946-11-03",), ()),
    # Arabic 11 is a month: the numeric date's two orders, as on main.
    ("11-3-46", "11-3-46", ("1946-11-03", "1946-03-11"), ("1946-11-03", "1946-03-11")),
    ("1X", "1X", (), ()),
    # Any position where a Roman month stands.
    ("14.1X.1946", "14.1X.1946", ("1946-09-14",), ()),
    ("V1-3-46", "V1-3-46", ("1946-06-03",), ()),
    # A slide code stays no date, its digit one read or not; the date beside it is read.
    ("1X-17-66", "1X-17-66-1", (), ()),
    ("1X-14-46", "1X-14-46\n1X-17-66-1", ("1946-09-14",), ()),
    # Two such months, a token that is no Roman month with its ones read as I, and lower case: as written.
    ("1X-1X-46", "1X-1X-46", (), ()),
    ("1L-14-46", "1L-14-46", (), ()),
    ("1x-14-46", "1x-14-46", (), ()),
])
def test_a_digit_one_for_the_i_of_a_roman_month_is_read_as_i_on_the_units_path_only(literal, text, units, old):
    for on, wanted in ((True, units), (False, old)):
        found = checks.parse_date(literal, reading_texts=[text], date_rules=RULES, units=on)
        assert (found.literal, tuple(reading.iso for reading in found.readings)) == (literal, wanted), (on, found)
        assert ("roman_month_digit_one" in found.notes) == (on and bool(wanted) and literal != "11-3-46")


def test_digit_one_month_reads_only_one_month_token_with_a_one_and_a_letter():
    assert checks.digit_one_month("1X-14-46") == "IX-14-46"
    assert checks.digit_one_month("X1-3-46") == "XI-3-46"
    assert checks.digit_one_month("V11-3-46") == "VII-3-46"
    for literal in ("11-3-46", "1-3-46", "IX-14-46", "1X-1X-46", "X111-3-46", "A1X-3-46", "1X4-3-46", "1x-3-46"):
        assert checks.digit_one_month(literal) is None, literal


def expert(texts, key="date_visited_from", units=True):
    """The field's expert on one label read by two readers, with the label's units or (`units` False, the old
    path) without them."""
    readings = (Reading("1A", "r1", "o1a", "raw_reading", texts[0]), Reading("1B", "r1", "o1b", "raw_reading",
        texts[1]))
    if units:
        readings = with_units(readings)
    task = FieldTask(key, True, FieldValue(), (), ("date_parser",))
    return _Expert(task, readings, tools=SimpleNamespace(sources=()), date_rules=RULES)


@pytest.mark.parametrize("units", [True, False], ids=["units", "old"])
def test_the_date_expert_settles_105526325_s_1x_on_the_value_parse_date_reads_on_the_units_path(units):
    """105526325: every reader writes "1X-14-46". On the units path the expert's parse_date returns
    1946-09-14 and its answer with that value stands; on the old path, as on main, parse_date finds no date
    and the value is refused as no check's output."""
    found = expert(["Davao Prov. 1X-14-46\nH. Hoogstraal", "Davao Prov. 1X-14-46\nH. Hoogstraal"], units=units)
    result = asyncio.run(found.parse_date("1X-14-46"))
    answer = FieldAnswer(outcome="resolved", literal="1X-14-46", reading_names=["1A", "1B"], value="1946-09-14",
        explanation="The label writes IX-14-46 with a one for the I.")
    if units:
        assert (result["status"], result["readings"][0]["iso"]) == (str(LookupStatus.SUCCESS), "1946-09-14")
        assert found.validate(answer).value == "1946-09-14"
    else:
        assert result["status"] == str(LookupStatus.NO_MATCH)
        with pytest.raises(Refused):
            found.validate(answer)


def test_105526325_s_date_settles_and_date_visited_to_derives_on_the_units_path(tmp_path, first_pass_path):
    """The step's own check of the expert's answer: on the units path "1X-14-46" settles 1946-09-14 with the
    check's derived row, and Date Visited To derives it; the old path keeps main's result, the value with no
    check row behind it."""
    rig = build_rig(tmp_path, TEXT.replace(DATE, "Davao Prov. 1X-14-46"),
        candidates=[*COLLECTORS, *(("date_visited_from", n, "1X-14-46", "Davao Prov. 1X-14-46") for n in ("1A", "1B"))])
    settle(rig, Scripted({"date_visited_from": answering(resolved("1X-14-46", value="1946-09-14"))}))
    run = rig.specimen.run
    date, to = run.fields["date_visited_from"], run.fields["date_visited_to"]
    rows = {item.id: item for item in run.evidence}
    checked = [rows[i] for i in date.evidence_ids if rows[i].kind == "derived"]
    assert (date.state, date.literal, date.parsed) == (ValueState.SUPPORTED, "1X-14-46", "1946-09-14")
    if first_pass_path == "old":
        assert checked == []
        return
    assert len(checked) == 1 and "1946-09-14" in checked[0].excerpt
    assert (to.state, to.parsed, to.layer) == (ValueState.SUPPORTED, "1946-09-14", "derived")


def test_the_ontology_s_roman_month_names_the_digit_one_reading_and_its_sources():
    from specimen_digitization import ontology

    [month] = [notation for notation in ontology.ontology().notations if notation.id == "roman_month"]
    assert month.readings[1] == "the same, a 1 written for an I (1X: IX)"
    assert {"tests/fixtures/field_model_pilot_rows.json:163-167", "tests/fixtures/field_model_pilot_rows.json:193",
        "src/specimen_digitization/field_research/checks.py:55-73"} <= set(month.source)


# ---- 2. a month and day ending a line above their year -------------------------------------------

LINE = "Guatemala, IV-25\n1948, R.D. Mitchell"
IV25 = [*COLLECTORS, *(("date_visited_from", n, "IV-25", "Guatemala, IV-25") for n in ("1A", "1B"))]


def year_below_run(tmp_path, literal, *, first=LINE, other=None, settled=None, candidate="IV-25"):
    """The run once the date's expert answers `literal`, its first label `first` (and `other` for reader
    1B), the organiser's candidate `candidate`, with `settled` ({field: literal}) settled on label 1 before
    this attempt."""
    quote = first.split("\n")[0]
    rig = build_rig(tmp_path, TEXT.replace(DATE, first), None if other is None else TEXT.replace(DATE, other),
        candidates=[*COLLECTORS, *(("date_visited_from", n, candidate, quote) for n in ("1A", "1B"))])
    run = rig.specimen.run
    for key, text in (settled or {}).items():
        run.fields[key] = FieldValue(state=ValueState.SUPPORTED, literal=text, layer="settled",
            source_region_id=run.regions[0].id, reason="Settled before.")
    settle(rig, Scripted({"date_visited_from": answering(resolved(literal, value="1948-04-25"))}))
    return run


@pytest.mark.parametrize("literal", ["IV-25\n1948", "IV-25\n1948,"])
def test_105526330_s_month_and_day_with_the_year_below_settle_and_date_visited_to_derives(tmp_path,
        first_pass_path, literal):
    """ "IV-25" ends a line above "1948, R.D. Mitchell" in both readings, the organiser's candidate "IV-25":
    on the units path both lines, the year alone (with or without its comma), settle 1948-04-25 and Date Visited
    To derives it; the old path keeps main's result, the literal refused as no candidate."""
    run = year_below_run(tmp_path, literal)
    date, to = run.fields["date_visited_from"], run.fields["date_visited_to"]
    if first_pass_path == "old":
        assert (date.state, date.reason) == (ValueState.UNRESOLVED, agreement.NOT_CANDIDATE + " Settled.")
        return
    assert (date.state, date.literal, date.parsed) == (ValueState.SUPPORTED, literal, "1948-04-25")
    assert (to.state, to.parsed, to.layer) == (ValueState.SUPPORTED, "1948-04-25", "derived")


REFUSED = {
    # (b) the extension takes more of the next line than its year.
    "more-than-the-year": ("IV-25\n1948, R.D.", LINE, None, "IV-25"),
    # (b) a next line that is no year.
    "no-year": ("IV-25\nR.D.", "Guatemala, IV-25\nR.D. Mitchell", None, "IV-25"),
    # (c) readers that disagree on the year.
    "readers-disagree": ("IV-25\n1948", LINE, "Guatemala, IV-25\n1949, R.D. Mitchell", "IV-25"),
    # (c) a reader that writes no line break after the date.
    "one-reader-on-one-line": ("IV-25\n1948", LINE, "Guatemala, IV-25 1948, R.D. Mitchell", "IV-25"),
    # (a) the first line is no candidate: it holds more than the candidate.
    "first-line-not-the-candidate": ("Guatemala, IV-25\n1948", LINE, None, "IV-25"),
    # (a) the first line is no candidate: the organiser's candidate is another text of the line.
    "first-line-not-a-candidate": ("IV-25\n1948", LINE, None, "Guatemala,"),
    # (b) a year with a measurement mark is no year.
    "year-with-a-mark": ("IV-25\n1948'", "Guatemala, IV-25\n1948' R.D. Mitchell", None, "IV-25"),
    # (b) the next line's first token is more than the year and its punctuation, though the date rules
    # read the two lines as one date.
    "year-glued-to-a-name": ("IV-25\n1948", "Guatemala, IV-25\n1948,R.D. Mitchell", None, "IV-25"),
    # (d) the date rules read no date of the two lines: a day the calendar refuses.
    "no-such-day": ("II-30\n1948", "Guatemala, II-30\n1948, R.D. Mitchell", None, "II-30"),
}


@pytest.mark.parametrize("case", REFUSED, ids=REFUSED)
def test_a_year_below_that_breaks_a_condition_is_refused_as_today_on_both_paths(tmp_path, case):
    literal, first, other, candidate = REFUSED[case]
    run = year_below_run(tmp_path, literal, first=first, other=other, candidate=candidate)
    date = run.fields["date_visited_from"]
    assert (date.state, date.reason) == (ValueState.UNRESOLVED, agreement.NOT_CANDIDATE + " Settled.")


def test_another_field_s_settled_text_on_the_year_holds_the_date_back_on_the_units_path(tmp_path, first_pass_path):
    """(e): the habitat was settled before this attempt as "1948", the year the date's literal takes from the
    next line. On the units path the date is not settled on it (step._taken): it goes to a person; the old path
    keeps main's result, the literal refused as no candidate."""
    run = year_below_run(tmp_path, "IV-25\n1948", settled={"habitat": "1948"})
    date = run.fields["date_visited_from"]
    if first_pass_path == "old":
        assert (date.state, date.reason) == (ValueState.UNRESOLVED, agreement.NOT_CANDIDATE + " Settled.")
        return
    assert date.state != ValueState.SUPPORTED and date.literal != "IV-25\n1948"
    assert "Habitat" in date.reason


def test_year_below_and_next_line_year_on_the_named_readings():
    readings = with_units((Reading("1A", "r1", "o1a", "raw_reading", LINE),
        Reading("1B", "r1", "o1b", "raw_reading", LINE.replace(", IV", ",IV"))))

    task = FieldTask("date_visited_from", True, FieldValue(), tuple(Candidate(n, "Guatemala, IV-25", "IV-25", f"e{n}")
        for n in ("1A", "1B")), ("date_parser",))
    assert agreement.year_below(task, readings, "IV-25\n1948", readings) == ("IV-25", "1948")
    assert agreement.next_line_year(task, readings, "IV-25\n1948", readings, RULES)
    assert not agreement.next_line_year(task, readings, "IV-25\n1948", readings, None)
    assert agreement.year_below(task, readings, "IV-25\n1948, R.D.", readings) is None
    other = FieldTask("habitat", True, FieldValue(), task.candidates, ())
    assert agreement.year_below(other, readings, "IV-25\n1948", readings) is None


@pytest.mark.parametrize("key", ["date_visited_from", "date_visited_to"])
def test_the_date_briefs_say_so_on_the_units_path_only(key):
    sentence = ("are one date: the literal is both lines exactly as written, with the line break and the year "
        "alone (\"<Roman month>-<dd>\\n<yyyy>\").")
    assert sentence in instructions(key, units=True)
    assert sentence not in instructions(key)
