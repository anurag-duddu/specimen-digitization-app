"""WP 2.R item (iii) of docs/execution/units/PLAN.md: Verbatim D/T/S cleared as not on the label when the collecting
date is exact. The owner typed on 2026-11-14: "4 shouldn't be flagged. It should be caught and handled. Goal isn't
to throw everything at the user it is to help by being in in autonomy as much as possible."

The PRD records the collection manager's EMu instruction for Verbatim D/T/S: "Used to hold non EMu-standard format
time and date values", with the examples "Avril 1917; Summer 1914; am; pm", used "when there is no exact time or
date" (docs/product-requirements/PRD.md, its section on date and time semantics clarified 2026-10-07). So on the
units path the field clears as not on the label (contracts.NOT_ON_LABEL_WHEN_DATE_EXACT, step.not_on_label_allowed)
only when its expert answered label_lacks_value and the not-on-the-label check row agrees (step.mark_not_on_label,
step.not_on_label), Date Visited From is settled from the label at day precision and not marked, and no reading
writes another date with no day, a season, a month's name, or a time or part of the day
(step.date_exact_and_alone). Otherwise, and on the old path, it keeps mandatory_unresolved, as on main.

Every test runs on both first-pass paths (conftest.py)."""

from __future__ import annotations

import pytest
from test_review_rules import second_label_read
from test_step import (
    LACKS,
    TODAY,
    Scripted,
    answering,
    build_rig,
    every_field,
    label_with,
    research,
    resolved,
)

from specimen_digitization.application.domain import Disposition, ValueState
from specimen_digitization.application.human_field_carry import KEY as CARRY_KEY
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FieldAnswer

DATE = "6-Sept.-1946"
REASON = "mandatory_unresolved:verbatim_dts"
DATED = resolved(DATE, value="1946-09-06")


def dated(*extra, line=DATE):
    """The rig's label with the collecting date line `line`, no Verbatim D/T/S line, and the lines `extra`."""
    return "\n".join([label_with(date_visited_from=line, verbatim_dts=None), *extra])


def settled(tmp_path, text, other=None, *, date=DATED, dts=LACKS, literals=(DATE, DATE), offered=(), refused=False):
    """The rig's run researched, applied and finalized, its second reader writing `other` if given: the
    organiser offers each reader's collecting date (`literals`, 1A's then 1B's) and, for Verbatim D/T/S, only
    `offered`; the date's expert answers `date`, Verbatim D/T/S's `dts`. The run and the step's decisions."""
    candidates = [item for item in every_field(*(("date_visited_from", name, literal, f"date_visited_from: {literal}")
        for name, literal in zip(("1A", "1B"), literals, strict=True))) if item[0] != "verbatim_dts"] + list(offered)
    rig = build_rig(tmp_path, text, other, candidates=candidates, refused=refused)
    run = rig.specimen.run
    prepared, outcomes, calls = research(rig, Scripted({"date_visited_from": answering(date),
        "verbatim_dts": answering(dts)}))
    decisions: dict[str, dict] = {}
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    field_step.finalize_fields(run, None, outcomes, specimen=rig.specimen, blobs=rig.blobs, today=TODAY)
    return run, decisions


def check_rows(run):
    rows = {item.id: item for item in run.evidence}
    return [i for i in run.fields["verbatim_dts"].evidence_ids if rows[i].locator == field_step.NOT_ON_LABEL_CHECK]


# The exact dates that clear Verbatim D/T/S, each settled alone on the label: the named case, and a numeric
# date whose "20.10" could be a clock time, which the settled date accounts for (the coordinator's ruling on
# #442, 2026-11-15: excluded by provenance).
EXACT = {"6-Sept.-1946": "1946-09-06", "20.10.1946": "1946-10-20"}


@pytest.mark.parametrize("literal", list(EXACT))
def test_an_exact_date_and_nothing_else_clears_verbatim_dts_as_not_on_the_label(tmp_path, literal,
        first_pass_path):
    """Named case: "6-Sept.-1946" settled and nothing else. On the units path Verbatim D/T/S clears as not on the
    label, with its check row and no reason, and the record clears; on the old path it keeps main's reason."""
    run, decisions = settled(tmp_path, dated(line=literal), date=resolved(literal, value=EXACT[literal]),
        literals=(literal, literal))
    value = run.fields["verbatim_dts"]
    date = run.fields["date_visited_from"]
    assert (date.state, date.literal, date.parsed) == (ValueState.SUPPORTED, literal, EXACT[literal])
    assert value.state == ValueState.NOT_PRESENT
    if first_pass_path == "units":
        assert len(check_rows(run)) == 1 and value.reason.startswith("Not on the label:")
        assert decisions["verbatim_dts"]["rule"] == "A_not_on_label"
        assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
    else:
        assert not check_rows(run) and decisions["verbatim_dts"]["rule"] == "A_declined:not_listed"
        assert REASON in run.reasons and run.disposition == Disposition.REVIEW


def not_supported(run):
    run.fields["date_visited_from"].state = ValueState.UNRESOLVED


def a_persons(run):
    run.dependencies[CARRY_KEY] = {"date_visited_from": {}}


def not_from_the_label(run):
    run.fields["date_visited_from"].layer = None


@pytest.mark.parametrize("change", [not_supported, a_persons, not_from_the_label])
def test_the_rule_is_checked_again_on_the_stored_run(tmp_path, change, first_pass_path):
    """A cleared Verbatim D/T/S keeps its check row; once the collecting date is no longer supported, is a
    person's value (human_field_carry) or is no longer settled from the label (its layer), finalizing again
    (step.refinalize) brings its reason back. The old path keeps main's reason throughout."""
    run, _ = settled(tmp_path, dated())
    assert (REASON in run.reasons) is (first_pass_path == "old")
    change(run)
    field_step.refinalize(run, today=TODAY)
    assert REASON in run.reasons


KEPT = {
    "a month and year on the label": dict(text=dated("XI.46")),
    # The readers' clause around the date, "6-Sept.-1946, 10 pm", is not the expert's literal: the date is held.
    "a time on the date's line": dict(text=dated(line=DATE + ", 10 pm")),
    "a clock time on a line of its own": dict(text=dated("22:30")),
    "a clock time with a period": dict(text=dated("22.00")),
    "a span of clock times": dict(text=dated("20.00-22.00")),
    "a part of the day": dict(text=dated("sunrise p.m.")),
    "a range of days": dict(text=dated(line="6-9 Sept. 1946"), literals=("6-9 Sept. 1946",) * 2,
        date=resolved("6-9 Sept. 1946", value="1946-09-06")),
    "a season on the label": dict(text=dated("Summer 1946")),
    "a date at month precision": dict(text=dated(line="Sept. 1946"), literals=("Sept. 1946",) * 2,
        date=resolved("Sept. 1946", value="1946-09")),
    "a date held": dict(text=dated(), other=dated(line="9-Sept.-1946"), literals=(DATE, "9-Sept.-1946"),
        date=FieldAnswer(outcome="several_possibilities", options=[DATE, "9-Sept.-1946"], reading_names=["1A", "1B"],
            explanation="The readers write two dates.")),
    "a text the organiser found for it": dict(text=dated("verbatim_dts: Synthetic D/T/S"), offered=[
        ("verbatim_dts", name, "Synthetic D/T/S", "verbatim_dts: Synthetic D/T/S") for name in ("1A", "1B")]),
    "an expert that found no answer": dict(text=dated(), dts=FieldAnswer(outcome="sources_cannot_resolve",
        explanation="No source.")),
}


@pytest.mark.parametrize("case", list(KEPT))
def test_verbatim_dts_keeps_its_reason_unless_the_date_is_exact_and_alone(tmp_path, case, first_pass_path):
    """Named cases: "XI.46", "6-Sept.-1946, 10 pm", "Summer 1946" and a date held keep the reason, as do a time
    or a part of the day beside an exact date, a date the label writes to the month only, a range of days
    ("6-9 Sept. 1946", no single day), a text the organiser found for the field (its check row does not agree)
    and an expert that did not answer label_lacks_value; on both paths, the old path as main."""
    run, decisions = settled(tmp_path, **KEPT[case])
    date = run.fields["date_visited_from"]
    if case in ("a date held", "a time on the date's line"):
        assert date.state != ValueState.SUPPORTED
    elif case == "a date at month precision":
        assert (date.state, date.parsed) == (ValueState.SUPPORTED, "1946-09")
    else:
        assert (date.state, date.parsed) == (ValueState.SUPPORTED, "1946-09-06")
    assert REASON in run.reasons and run.disposition == Disposition.REVIEW
    assert run.fields["verbatim_dts"].state != ValueState.SUPPORTED and not check_rows(run)
    expected = ("A_declined:date_not_exact_and_alone" if first_pass_path == "units" else "A_declined:not_listed")
    if case == "a text the organiser found for it":
        expected = "A_declined:organiser_found_text" if first_pass_path == "units" else expected
    elif case == "an expert that found no answer":
        expected = None
    assert decisions["verbatim_dts"].get("rule") == expected


# What another label may write that Verbatim D/T/S holds, the first label's date exact: the named case "XI.46",
# and the inputs of #442's review round 1 (Codex and G51) under the coordinator's rulings of 2026-11-15.
OTHER_LABEL = (
    # a month and a year, which checks.parse_date reads or not
    "XI.46", "xi.46", "9.1946", "09/1946",
    # a year alone, a range of years, a decade
    "1946", "1950", "'46", "1946-47", "1940s",
    # a month's name in a joined word
    "mid-Sept.", "Sept.-Oct.",
    # a clock time, with no marker too
    "10.30", "22.00", "20.00-22.00", "a. m.", "10 o'clock",
    # a season in each language: en, es, pt, fr, de, it
    "Summer 1946", "oto\N{LATIN SMALL LETTER N WITH TILDE}o", "ver\N{LATIN SMALL LETTER A WITH TILDE}o",
    "\N{LATIN SMALL LETTER E WITH ACUTE}t\N{LATIN SMALL LETTER E WITH ACUTE}",
    "\N{LATIN CAPITAL LETTER E WITH ACUTE}t\N{LATIN SMALL LETTER E WITH ACUTE} 1946", "Herbst", "Sommer 1946",
    "estate 1946",
    # a part of the day in each language
    "twilight", "nightfall", "night-time", "noche", "alba", "crep\N{LATIN SMALL LETTER U WITH ACUTE}sculo",
    "noite", "nuit", "Nacht", "notte",
)


@pytest.mark.parametrize("written", OTHER_LABEL)
def test_a_date_without_a_day_or_a_time_on_another_label_keeps_the_reason(tmp_path, monkeypatch, written,
        first_pass_path):
    """Named case: "XI.46" on any label. The second label's readers write it, or another text Verbatim D/T/S
    holds; the first label's date is exact."""
    second_label_read(monkeypatch, written, written)
    run, decisions = settled(tmp_path, dated())
    date = run.fields["date_visited_from"]
    assert (date.state, date.parsed) == (ValueState.SUPPORTED, "1946-09-06")
    assert REASON in run.reasons and not check_rows(run)
    assert decisions["verbatim_dts"]["rule"] == (
        "A_declined:date_not_exact_and_alone" if first_pass_path == "units" else "A_declined:not_listed")


def test_a_date_settled_but_marked_keeps_the_reason(tmp_path, first_pass_path):
    """Named case: a date settled but marked. The first pass is refused and given up on, so on the units path
    the label settles every field on its readers agreeing alone, marked text_only (test_step's
    AGREEING_ALONE): the date is supported and exact, but marked, and Verbatim D/T/S keeps its reason. The
    settlement is recorded after rule A marks Verbatim D/T/S, so its check row stands, and the rule is checked
    again on the stored run (step.finalize_fields)."""
    run, decisions = settled(tmp_path, dated(), refused=True)
    date = run.fields["date_visited_from"]
    assert (date.state, date.parsed) == (ValueState.SUPPORTED, "1946-09-06")
    marked = f"marked:date_visited_from:{run.regions[0].id}:text_only"
    assert (marked in run.reasons) is (first_pass_path == "units")
    assert REASON in run.reasons
    if first_pass_path == "units":
        assert decisions["verbatim_dts"]["rule"] == "A_not_on_label" and len(check_rows(run)) == 1
    else:
        assert decisions["verbatim_dts"]["rule"] == "A_declined:not_listed" and not check_rows(run)
