"""WP 2.4's two date items, from the 2.6 gate forecast (the coordinator's rulings of 2026-11-15):

1. A Roman month written with a digit one for an I ("1X-14-46", pilot slide 105526325, every reader) is read as
   that month where the date parser then reads a date (checks.digit_one_month; the ontology's notation
   roman_month, its second reading).
2. A month and day ending a line above their year ("IV-25" above "1948, R.D. Mitchell", pilot slide 105526330)
   are one date: the literal of both lines, the year alone, passes the literal check when every condition of
   agreement.year_below and agreement.next_line_year holds, and no other field's settled text sits on the year
   (step._taken). The date briefs say so (prompts/date_visited_from.txt, date_visited_to.txt)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from test_first_pass_advice import with_units
from test_step import COLLECTORS, TEXT, Scripted, answering, build_rig, failing, resolved, settle

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import FieldValue, LookupStatus, ValueState
from specimen_digitization.field_research import agreement, checks
from specimen_digitization.field_research.contracts import Candidate, FieldAnswer, FieldTask, Reading
from specimen_digitization.field_research.experts import Refused, _Expert
from specimen_digitization.field_research.prompts import instructions

RULES = published_registry().profiles[0].date_rules
DATE = "date_visited_from: 2020-06-01"


# ---- 1. a digit one for the I of a Roman month ----------------------------------------------------

@pytest.mark.parametrize(("literal", "text", "wanted"), [
    # The named cases.
    ("1X-14-46", "Davao 1X-14-46 H. Hoogstraal", ("1946-09-14",)),
    ("X1-3-46", "X1-3-46", ("1946-11-03",)),
    # Arabic 11 is a month: the numeric date's two orders, as on main.
    ("11-3-46", "11-3-46", ("1946-11-03", "1946-03-11")),
    ("1X", "1X", ()),
    # Any position where a Roman month stands.
    ("14.1X.1946", "14.1X.1946", ("1946-09-14",)),
    ("V1-3-46", "V1-3-46", ("1946-06-03",)),
    # A slide code stays no date, its digit one read or not; the date beside it is read.
    ("1X-17-66", "1X-17-66-1", ()),
    ("1X-14-46", "1X-14-46\n1X-17-66-1", ("1946-09-14",)),
    # 1s and Is alone, which read as Arabic make a month (G51's round 1 on #444): as written.
    ("1I-3-46", "1I-3-46", ()),
    ("I1-3-46", "I1-3-46", ()),
    # Two such months, a token that is no Roman month with its ones read as I, and lower case: as written.
    ("1X-1X-46", "1X-1X-46", ()),
    ("1L-14-46", "1L-14-46", ()),
    ("1x-14-46", "1x-14-46", ()),
])
def test_a_digit_one_for_the_i_of_a_roman_month_is_read_as_i(literal, text, wanted):
    found = checks.parse_date(literal, reading_texts=[text], date_rules=RULES)
    assert (found.literal, tuple(reading.iso for reading in found.readings)) == (literal, wanted), found
    assert ("roman_month_digit_one" in found.notes) == (bool(wanted) and literal != "11-3-46")


def test_digit_one_month_reads_only_one_month_token_with_a_one_and_a_v_or_an_x():
    assert checks.digit_one_month("1X-14-46") == "IX-14-46"
    assert checks.digit_one_month("X1-3-46") == "XI-3-46"
    assert checks.digit_one_month("V11-3-46") == "VII-3-46"
    for literal in ("11-3-46", "1-3-46", "1I-3-46", "I1-3-46", "11I-3-46", "IX-14-46", "1X-1X-46", "X111-3-46", "A1X-3-46",
            "1X4-3-46", "1x-3-46"):
        assert checks.digit_one_month(literal) is None, literal


def expert(texts, key="date_visited_from"):
    """The field's expert on one label read by two readers, with the label's units."""
    readings = with_units((Reading("1A", "r1", "o1a", "raw_reading", texts[0]),
        Reading("1B", "r1", "o1b", "raw_reading", texts[1])))
    task = FieldTask(key, True, FieldValue(), (), ("date_parser",))
    return _Expert(task, readings, tools=SimpleNamespace(sources=()), date_rules=RULES)


def test_the_date_expert_settles_105526325_s_1x_on_the_value_parse_date_reads():
    """105526325: every reader writes "1X-14-46". The expert's parse_date returns 1946-09-14 and its
    answer with that value stands."""
    found = expert(["Davao Prov. 1X-14-46\nH. Hoogstraal", "Davao Prov. 1X-14-46\nH. Hoogstraal"])
    result = asyncio.run(found.parse_date("1X-14-46"))
    answer = FieldAnswer(outcome="resolved", literal="1X-14-46", reading_names=["1A", "1B"], value="1946-09-14",
        explanation="The label writes IX-14-46 with a one for the I.")
    assert (result["status"], result["readings"][0]["iso"]) == (str(LookupStatus.SUCCESS), "1946-09-14")
    assert found.validate(answer).value == "1946-09-14"


def test_105526325_s_date_settles_and_date_visited_to_derives(tmp_path):
    """The step's own check of the expert's answer: "1X-14-46" settles 1946-09-14 with the check's derived
    row, and Date Visited To derives it."""
    rig = build_rig(tmp_path, TEXT.replace(DATE, "Davao Prov. 1X-14-46"),
        candidates=[*COLLECTORS, *(("date_visited_from", n, "1X-14-46", "Davao Prov. 1X-14-46") for n in ("1A", "1B"))])
    settle(rig, Scripted({"date_visited_from": answering(resolved("1X-14-46", value="1946-09-14"))}))
    run = rig.specimen.run
    date, to = run.fields["date_visited_from"], run.fields["date_visited_to"]
    rows = {item.id: item for item in run.evidence}
    checked = [rows[i] for i in date.evidence_ids if rows[i].kind == "derived"]
    assert (date.state, date.literal, date.parsed) == (ValueState.SUPPORTED, "1X-14-46", "1946-09-14")
    assert len(checked) == 1 and "1946-09-14" in checked[0].excerpt
    assert (to.state, to.parsed, to.layer) == (ValueState.SUPPORTED, "1946-09-14", "derived")


def test_the_ontology_s_roman_month_names_the_digit_one_reading_and_its_sources():
    from specimen_digitization import ontology

    [month] = [notation for notation in ontology.ontology().notations if notation.id == "roman_month"]
    assert month.readings[1] == "the same, a 1 written for an I (1X: IX)"
    assert {"tests/fixtures/field_model_pilot_rows.json:163-167", "tests/fixtures/field_model_pilot_rows.json:193",
        "src/specimen_digitization/field_research/checks.py:55-75"} <= set(month.source)


# ---- 2. a month and day ending a line above their year -------------------------------------------

LINE = "Guatemala, IV-25\n1948, R.D. Mitchell"
IV25 = [*COLLECTORS, *(("date_visited_from", n, "IV-25", "Guatemala, IV-25") for n in ("1A", "1B"))]


def year_below_run(tmp_path, literal, *, first=LINE, other=None, settled=None, candidate="IV-25", quote=None):
    """The run once the date's expert answers `literal`, its first label `first` (and `other` for reader
    1B), the organiser's candidate `candidate` quoting `quote` (the first line of `first` by default), with
    `settled` ({field: literal}) settled on label 1 before this attempt."""
    quote = first.split("\n")[0] if quote is None else quote
    rig = build_rig(tmp_path, TEXT.replace(DATE, first), None if other is None else TEXT.replace(DATE, other),
        candidates=[*COLLECTORS, *(("date_visited_from", n, candidate, quote) for n in ("1A", "1B"))])
    run = rig.specimen.run
    for key, text in (settled or {}).items():
        run.fields[key] = FieldValue(state=ValueState.SUPPORTED, literal=text, layer="settled",
            source_region_id=run.regions[0].id, reason="Settled before.")
    settle(rig, Scripted({"date_visited_from": answering(resolved(literal, value="1948-04-25"))}))
    return run


@pytest.mark.parametrize("literal", ["IV-25\n1948", "IV-25\n1948,"])
def test_105526330_s_month_and_day_with_the_year_below_settle_and_date_visited_to_derives(tmp_path, literal):
    """ "IV-25" ends a line above "1948, R.D. Mitchell" in both readings, the organiser's candidate "IV-25":
    both lines, the year alone (with or without its comma), settle 1948-04-25 and Date Visited To derives it."""
    run = year_below_run(tmp_path, literal)
    date, to = run.fields["date_visited_from"], run.fields["date_visited_to"]
    assert (date.state, date.literal, date.parsed) == (ValueState.SUPPORTED, literal, "1948-04-25")
    assert (to.state, to.parsed, to.layer) == (ValueState.SUPPORTED, "1948-04-25", "derived")


REFUSED = {
    # (b) the extension takes more of the next line than its year.
    "more-than-the-year": ("IV-25\n1948, R.D.", LINE, None, "IV-25"),
    # (b) a next line that is no year.
    "no-year": ("IV-25\nR.D.", "Guatemala, IV-25\nR.D. Mitchell", None, "IV-25"),
    # (c) readers that disagree on the year.
    "readers-disagree": ("IV-25\n1948", LINE, "Guatemala, IV-25\n1949, R.D. Mitchell", "IV-25"),
    # (c) readers whose tokens there differ, though both read 1948: one writes a comma after it, one a period.
    "readers-differ-in-the-token": ("IV-25\n1948", LINE, "Guatemala, IV-25\n1948. R.D. Mitchell", "IV-25"),
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
    # (b) the second line is no year: a year alone on its line above the date (Codex's round 1 on #444),
    # which the date rules read as one date with it (date_lines.split_literal takes a year first).
    "year-first": ("1948\nIV-25", "Guatemala,\n1948\nIV-25, R.D. Mitchell", None, "1948"),
    "two-digit-year-first": ("'48\nIV-25", "Guatemala,\n'48\nIV-25 R.D. Mitchell", None, "'48"),
}


@pytest.mark.parametrize("case", REFUSED, ids=REFUSED)
def test_a_year_below_that_breaks_a_condition_is_refused(tmp_path, case):
    literal, first, other, candidate = REFUSED[case]
    run = year_below_run(tmp_path, literal, first=first, other=other, candidate=candidate,
        quote=candidate if case.endswith("year-first") else None)
    date = run.fields["date_visited_from"]
    assert (date.state, date.reason) == (ValueState.UNRESOLVED, agreement.NOT_CANDIDATE + " Settled.")


def test_another_field_s_settled_text_on_the_year_holds_the_date_back(tmp_path):
    """(e): the habitat was settled before this attempt as "1948", the year the date's literal takes from the
    next line. The date is not settled on it (step._taken): it goes to a person."""
    run = year_below_run(tmp_path, "IV-25\n1948", settled={"habitat": "1948"})
    date = run.fields["date_visited_from"]
    assert date.state != ValueState.SUPPORTED and date.literal != "IV-25\n1948"
    # The reason says what holds the year: not text read from the transcript (G51's round 1 on #444).
    assert date.reason.startswith("The year this date takes from the next line is also in the value found for Habitat.")


def test_a_later_attempt_s_text_over_the_borrowed_year_is_refused(tmp_path):
    """Codex's round 1 on #444: attempt 1 settles "IV-25\n1948" while the collectors' expert fails; attempt 2
    settles the organiser's collectors candidate "1948, R.D. Mitchell", which runs over the year the date
    took. The date, settled first, keeps it and the collectors are refused (step._taken, _borrowed_years)."""
    candidates = [*(("collectors", n, "1948, R.D. Mitchell", "1948, R.D. Mitchell") for n in ("1A", "1B")),
        *(("date_visited_from", n, "IV-25", "Guatemala, IV-25") for n in ("1A", "1B"))]
    rig = build_rig(tmp_path, TEXT.replace(DATE, LINE), candidates=candidates)
    run = rig.specimen.run
    settle(rig, Scripted({"date_visited_from": answering(resolved("IV-25\n1948", value="1948-04-25")),
        "collectors": failing("model_error")}))
    assert run.fields["collectors"].state != ValueState.SUPPORTED
    settle(rig, Scripted({"collectors": answering(resolved("1948, R.D. Mitchell"))}))
    date, collectors = run.fields["date_visited_from"], run.fields["collectors"]
    assert (date.state, date.literal) == (ValueState.SUPPORTED, "IV-25\n1948")
    assert collectors.state != ValueState.SUPPORTED
    assert collectors.reason.startswith(
        "This text holds the year the value found for Date Visited From took from its next line.")


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
def test_the_date_briefs_say_so(key):
    sentence = ("are one date: the literal is both lines exactly as written, with the line break and the year "
        "alone (\"<Roman month>-<dd>\\n<yyyy>\").")
    assert instructions(key).count(sentence) == 1
