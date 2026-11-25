"""Lane B of the waiting-fields program (the coordinator's brief of 2026-11-24, fix 2 of the audit of the 19
cleared production records): an agreed blank Verbatim D/T/S where nothing on the labels needs one.

Work package F2 left Verbatim D/T/S out of rule B (second_opinion.AGREED_BLANK_EXCEPT) because both missed
values of lane H1's table were Verbatim D/T/S: 105526336 (truth "1916") and 105526564 (truth "III.87"), each a
collecting date with no day. The field holds such a date, or a time of day (the second opinion's instruction,
field 17). So rule B now lifts `mandatory_unresolved:verbatim_dts` and `label_unsettled:verbatim_dts` from a
blank Verbatim D/T/S the current, obtained second opinion also leaves blank only where
second_opinion._no_verbatim_date holds: no text of the run writes a time of day, and either both collecting
dates are settled to the day, or both are blank and no text could be a date and nothing is unreadable. Every
other case keeps the flag: a date with no day (the two misses' shape), a range ending on a month, a date in
doubt, a time of day. Habitat stays excepted (test_agreed_no_flag.py).

The record is test_agreed_no_flag's (test_step's rig through the workflow with the second opinion mounted):
its label writes the collecting date to the day, "2020-06-01".
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from test_agreed_no_flag import (
    BLANKS,
    TODAY,
    answer_of,
    blank_codes,
    flagged,
    lifted,
    rig_of,
    store_obtained,
    to_end,
)
from test_second_opinion import Opinion

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.field_research import second_opinion as so
from specimen_digitization.field_research import step as field_step

# The product's behaviour: the marks are derived (tests/conftest.py).
USES_SECOND_OPINION = True
VERBATIM = frozenset({"verbatim_dts"})
DATES = ("date_visited_from", "date_visited_to")


def agreed_run(folder):
    """The rule B record: every field of BLANKS blank, the second opinion obtained, current and blank on them."""
    return to_end(rig_of(folder, BLANKS, opinion=Opinion(answer_of(BLANKS)))).run


def dated(run, start, end):
    """The record with its collecting dates shown as `start` and `end` and an obtained, current answer that
    agrees with them (so the step is not due), finalized again."""
    for key, text in zip(DATES, (start, end), strict=True):
        value = run.fields[key]
        value.parsed = value.normalized = text
    store_obtained(run, answer_of(BLANKS, **{key: {"value": text, "evidence": "L1: synthetic"}
        for key, text in zip(DATES, (start, end), strict=True)}))
    field_step.refinalize(run, today=TODAY)
    assert so.answer_current(run) and not so.due(run)
    return run


def test_a_blank_verbatim_dts_beside_a_date_written_to_the_day_carries_no_flag(tmp_path):
    run = agreed_run(tmp_path)
    assert [so.shown(run.fields[key]) for key in DATES] == ["2020-06-01", "2020-06-01"]
    assert run.fields["verbatim_dts"].state == ValueState.NOT_PRESENT
    assert so._blank_answer(run.second_opinion["answer"]["verbatim_dts"])
    assert blank_codes(VERBATIM) <= lifted(run)
    assert not blank_codes(VERBATIM) & set(run.open_reasons) and "verbatim_dts" not in flagged(run)


@pytest.mark.parametrize(("start", "end"), [("2020-06", "2020-06"), ("2020", "2020"), ("2020-06-01", "2020-07")],
    ids=["month", "year", "range-to-a-month"])
def test_a_date_with_no_day_keeps_the_flag(tmp_path, start, end):
    """The two misses' shape: "III.87" settles as a month, "1916" as a year; Verbatim D/T/S holds them."""
    run = dated(agreed_run(tmp_path), "2020-06-01", "2020-06-01")
    assert blank_codes(VERBATIM) <= lifted(run)
    dated(run, start, end)
    assert not lifted(run) & blank_codes(VERBATIM)
    assert blank_codes(VERBATIM) <= set(run.open_reasons) and "verbatim_dts" in flagged(run)


def test_a_date_in_doubt_keeps_the_flag(tmp_path):
    run = agreed_run(tmp_path)
    run.fields["date_visited_from"].state = ValueState.AMBIGUOUS
    readings = field_step.run_readings(run)
    assert so._no_verbatim_date(run, readings) is False
    assert "verbatim_dts" not in so.agreed(run, readings)[1]


def test_a_second_opinion_that_reads_a_verbatim_dts_keeps_the_flag(tmp_path):
    """Rule B's own condition stands: a blank where the second opinion reads a value is a missed-value signal."""
    run = agreed_run(tmp_path)
    assert blank_codes(VERBATIM) <= lifted(run)
    store_obtained(run, answer_of(BLANKS, verbatim_dts={"value": "VI.2020", "evidence": "L1: VI.2020"}))
    field_step.refinalize(run, today=TODAY)
    assert not lifted(run) & blank_codes(VERBATIM) and "verbatim_dts" in flagged(run)


# ---- second_opinion._no_verbatim_date, case by case -----------------------------------------------------------

def value(state=ValueState.SUPPORTED, text=None, layer="settled"):
    return FieldValue(state=state, parsed=text, layer=layer if state == ValueState.SUPPORTED else None)


BLANK = FieldValue(state=ValueState.NOT_PRESENT)


def run_of(start, end, texts, *, spans=(), unreadable=False):
    """A run as the rule reads it: its two collecting dates, one reader's text per entry of `texts` (with
    `spans` listed on the first), and a transcript (marked unreadable or not)."""
    observations = [SimpleNamespace(literal_text=text, unreadable_spans=list(spans) if index == 0 else [])
        for index, text in enumerate(texts)]
    transcripts = [SimpleNamespace(text=texts[0], value_state=ValueState.UNREADABLE if unreadable else None)]
    return SimpleNamespace(fields={"date_visited_from": start, "date_visited_to": end},
        observations=observations, transcripts=transcripts)


def readings_of(texts):
    return [SimpleNamespace(text=text) for text in texts]


DAY = ("IV-23-48\nYepocapa, 4800ft\nR.D.mitchell", "IV-23-48\nYepocapa, 4800ft.\nR.D. Mitchell")


@pytest.mark.parametrize("time", ["10 am", "3 p.m.", "Sunrise", "at night", "22h", "10:30", "mañana"])
def test_a_time_of_day_keeps_the_flag(time):
    day, settled_to = value(text="1948-04-23"), value(text="1948-04-23", layer="derived")
    assert so._no_verbatim_date(run_of(day, settled_to, DAY), readings_of(DAY)) is True
    timed = (DAY[0] + "\n" + time, DAY[1])
    assert so._no_verbatim_date(run_of(day, settled_to, timed), readings_of(DAY)) is False
    assert so._no_verbatim_date(run_of(day, settled_to, DAY), readings_of(timed)) is False


@pytest.mark.parametrize(("start", "end", "expected"), [
    (value(text="1948-04-23"), value(text="1948-04-25"), True),
    (value(text="1948-04"), value(text="1948-04"), False),
    (value(text="1948"), value(text="1948"), False),
    (value(text="1948-04-23"), value(text="1948-05"), False),
    (value(text="1948-04-23"), BLANK, False),
    (value(state=ValueState.AMBIGUOUS), value(state=ValueState.AMBIGUOUS), False),
    (value(text="1948-04-23", layer=None), value(text="1948-04-23"), False),
], ids=["days", "month", "year", "to-a-month", "end-blank", "in-doubt", "unchecked-layer"])
def test_the_dates_settled_to_the_day(start, end, expected):
    assert so._no_verbatim_date(run_of(start, end, DAY), readings_of(DAY)) is expected


NO_DATE = ("Bittacus strigosus\nHagen\nDet. D. W. Webb", "FMNH-INS\n4363881\nFIELD MUSEUM")


def test_no_date_on_the_labels_and_nothing_unreadable_carries_no_flag():
    assert so._no_verbatim_date(run_of(BLANK, BLANK, NO_DATE), readings_of(NO_DATE)) is True
    assert so._no_verbatim_date(run_of(BLANK, None, NO_DATE), readings_of(NO_DATE)) is True


@pytest.mark.parametrize("change", ["a-year", "a-roman-month", "a-month-word", "a-placeholder", "a-span",
    "a-transcript-unreadable", "a-date-in-doubt"])
def test_no_date_settled_but_one_may_be_written_keeps_the_flag(change):
    texts, kwargs, start = list(NO_DATE), {}, BLANK
    if change == "a-year":
        texts[0] += "\n1916"
    elif change == "a-roman-month":
        texts[0] += "\nIII.87"
    elif change == "a-month-word":
        texts[0] += "\nAvril"
    elif change == "a-placeholder":
        texts[0] += "\n[unreadable]"
    elif change == "a-span":
        kwargs["spans"] = ["a faint word"]
    elif change == "a-transcript-unreadable":
        kwargs["unreadable"] = True
    else:
        start = value(state=ValueState.AMBIGUOUS)
    assert so._no_verbatim_date(run_of(start, BLANK, texts, **kwargs), readings_of(texts)) is False
