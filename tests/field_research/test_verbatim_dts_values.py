"""Verbatim D/T/S never settles on an exact date or a slide code (step._verbatim_dts_refusal).

The field holds date and time wording that is not an exact date: PRD.md:529 ("Original collection-event
date/time expressions that do not fit EMu's standard format, including partial or seasonal dates and
qualitative times") and PRD.md:540-544, the collection manager's instruction the owner relayed (used "when
there is no exact time or date"). G45 keeps a slide code out of every field. The stored units-wp26 runs cleared
"IX-14-46" (105526324) and "1X-14-46" (105526325) as Verbatim D/T/S; a live run cleared the slide code
"IX-3-66-10". A resolved answer holding either is refused here and stays for a person (unresolved), its
reason saying why; a partial date, a season and a time of day settle as before.
"""
from __future__ import annotations

import pytest
from test_first_pass_advice import with_units

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import FieldValue, Run, ValueState
from specimen_digitization.field_research import step
from specimen_digitization.field_research.contracts import Candidate, FieldAnswer, FieldOutcome, FieldTask, Reading

RULES = published_registry().profiles[0].date_rules


def settle(literal: str, line: str | None = None):
    """The Verbatim D/T/S value both readers' resolved answer gives, the literal on a line of its own."""
    line = literal if line is None else line
    text = f"E. slope Mt. Apo\n{line}\nF.G. Werner"
    readings = with_units(tuple(Reading(name, "label2", f"obs-{name}", "raw_reading", text) for name in ("2A", "2B")))
    task = FieldTask("verbatim_dts", True, FieldValue(literal=literal),
        tuple(Candidate(name, line, literal, f"row-{name}") for name in ("2A", "2B")), ())
    outcome = FieldOutcome("verbatim_dts", FieldAnswer(outcome="resolved", literal=literal,
        reading_names=["2A", "2B"], explanation="Copied as written."))
    decision: dict = {}
    value = step._field_value(Run(), task, outcome, readings=readings, by_name={r.name: r for r in readings},
        evidence={}, asset_id=None, blobs=None, date_rules=RULES, places={}, decision=decision)
    return value, decision


@pytest.mark.parametrize("literal, iso", [
    ("3 Sept. '46", "1946-09-03"),       # 105526321
    ("6-Sept.-1946", "1946-09-06"),      # 105526323
    ("IX-14-46", "1946-09-14"),          # 105526324, cleared in r2/pair
    ("1X-14-46", "1946-09-14"),          # 105526325, cleared in r1/pair (a 1 written for the I)
    ("5/6/39", "1939-05-06 or 1939-06-05"),   # both orders are exact days
    ("3-10.VIII.1915", "1915-08-03"),    # a day range: its ends are exact days, Date Visited From and To's
    ("12-15 June 1946", "1946-06-12"),
])
def test_an_exact_date_is_no_verbatim_dts(literal, iso):
    value, decision = settle(literal)
    assert value.state == ValueState.UNRESOLVED
    assert decision["refusal"] == step.VERBATIM_EXACT_DATE
    assert value.reason.startswith("Verbatim D/T/S holds only date or time wording that is not an exact date")
    assert f"the exact date {iso}" in value.reason
    assert value.literal == literal   # the text stays for the person who decides


@pytest.mark.parametrize("literal, line", [
    ("IX-3-66-10", "IX-3-66-10"),             # live run 7b052445
    ("10-6-78-1a", "10-6-78-1a"),             # a pilot slide's top-edge code
    ("IV-29-68", "IV-29-68-4"),               # a date-shaped part of a code
])
def test_a_slide_code_is_no_verbatim_dts(literal, line):
    value, decision = settle(literal, line)
    assert value.state == ValueState.UNRESOLVED
    assert decision["refusal"] == step.VERBATIM_SLIDE_CODE
    assert "never holds a slide code" in value.reason


@pytest.mark.parametrize("literal", ["XI.'46", "XI.46", "1916", "Nov, Dec 1955", "XI, XII-1955", "III.87",
    "XII-1970", "Summer 1914", "Summer 1946", "Avril 1917", "am", "sunrise", "10:30", "c. 1946", "46",
    "12-15 June", "3 Sept. '46 10:30", "early Sept. 1946"])
def test_wording_that_is_not_an_exact_date_settles_as_written(literal):
    value, decision = settle(literal)
    assert value.state == ValueState.SUPPORTED
    assert (value.literal, value.layer) == (literal, "verbatim")
    assert "refusal" not in decision


def test_the_refusal_covers_exact_dates_and_slide_codes_only():
    """Text that is neither an exact date nor a slide code is not refused by this rule, whatever else is
    wrong with it: the printed heading "Siphonaptera of Utah", which a stored run cleared as Verbatim D/T/S
    (105526461, r1/three), is left to the field's other rules."""
    reading = Reading("2A", "label2", "obs-2A", "raw_reading", "Siphonaptera of Utah\nLocality Carey, Ida.")
    assert step._verbatim_dts_refusal("Siphonaptera of Utah", (reading,), RULES) is None
    assert step._verbatim_dts_refusal("", (reading,), RULES) is None


def test_another_field_s_exact_date_is_not_refused():
    """Date Visited From still settles on the exact date (the refusal is Verbatim D/T/S's alone)."""
    text = "E. slope Mt. Apo\n3 Sept. '46\nF.G. Werner"
    readings = with_units(tuple(Reading(name, "label2", f"obs-{name}", "raw_reading", text) for name in ("2A", "2B")))
    task = FieldTask("date_visited_from", True, FieldValue(literal="3 Sept. '46"),
        tuple(Candidate(name, "3 Sept. '46", "3 Sept. '46", f"row-{name}") for name in ("2A", "2B")),
        ("date_parser",))
    outcome = FieldOutcome("date_visited_from", FieldAnswer(outcome="resolved", literal="3 Sept. '46",
        value="1946-09-03", reading_names=["2A", "2B"], explanation="The collecting date."))
    decision: dict = {}
    value = step._field_value(Run(), task, outcome, readings=readings, by_name={r.name: r for r in readings},
        evidence={}, asset_id=None, blobs=None, date_rules=RULES, places={}, decision=decision)
    assert (value.state, value.parsed) == (ValueState.SUPPORTED, "1946-09-03")
    assert "refusal" not in decision
