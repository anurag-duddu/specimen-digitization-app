"""Lane B of the waiting-fields program (the coordinator's brief of 2026-11-24, fix 2 of the audit of the 19
cleared production records): an agreed blank Verbatim D/T/S where nothing on the labels needs one.

Work package F2 left Verbatim D/T/S out of rule B (second_opinion.AGREED_BLANK_EXCEPT) because both missed
values of lane H1's table were Verbatim D/T/S: 105526336 (truth "1916") and 105526564 (truth "III.87"), each a
collecting date with no day. The field holds such a date, a season or a time of day (the second opinion's instruction,
field 17). So rule B now lifts `mandatory_unresolved:verbatim_dts` and `label_unsettled:verbatim_dts` from a
blank Verbatim D/T/S the current, obtained second opinion also leaves blank only where
second_opinion._no_verbatim_date holds: both collecting dates are settled to the day, no text of the run writes
a time of day or a season, and no part of a label the dates are drawn on is unreadable. Pinned here as keeping
the flag: a date with no day (the two misses' shape), a range ending on a month, a date in doubt, no date at
all, a time of day or a season, an unreadable part of the date's label. Habitat stays excepted
(test_agreed_no_flag.py).

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

DATE_LABEL, OTHER_LABEL = "label-date", "label-other"


def value(state=ValueState.SUPPORTED, text=None, layer="settled", label=DATE_LABEL):
    return FieldValue(state=state, parsed=text, layer=layer if state == ValueState.SUPPORTED else None,
        source_region_id=label if state == ValueState.SUPPORTED else None)


BLANK = FieldValue(state=ValueState.NOT_PRESENT)
DAY = ("IV-23-48\nYepocapa, 4800ft\nR.D.mitchell", "IV-23-48\nYepocapa, 4800ft.\nR.D. Mitchell")
DETERMINATION = ("Panorpa\nsp. IVa\nJ. Kustermop det. 2021", "Panorpa\nsp. IVa\nJ. Kustermop det. 2021")


def run_of(start, end, texts=DAY, *, other=DETERMINATION, spans=(), unreadable=None):
    """A run as the rule reads it: its two collecting dates, the date's label read by two readers (`texts`,
    with `spans` listed by the first) and another label (`other`), each with a transcript; `unreadable` names
    the label whose transcript is marked unreadable."""
    observations, transcripts = [], []
    for label, written in ((DATE_LABEL, texts), (OTHER_LABEL, other)):
        for index, text in enumerate(written):
            observations.append(SimpleNamespace(id=f"{label}-{index}", region_id=label, literal_text=text,
                unreadable_spans=list(spans) if label == DATE_LABEL and index == 0 else []))
        transcripts.append(SimpleNamespace(region_id=label, text=written[0],
            value_state=ValueState.UNREADABLE if unreadable == label else None))
    return SimpleNamespace(fields={"date_visited_from": start, "date_visited_to": end},
        observations=observations, transcripts=transcripts, evidence=[])


def readings_of(texts=DAY, other=DETERMINATION):
    return [SimpleNamespace(text=text, region_id=label) for label, written in ((DATE_LABEL, texts),
        (OTHER_LABEL, other)) for text in written]


DAYS = (value(text="1948-04-23"), value(text="1948-04-23", layer="derived"))


@pytest.mark.parametrize("time", ["10 am", "3 p.m.", "Sunrise", "at night", "22h", "10:30", "mañana", "Summer",
    "verano", "Été", "10  hrs", "midi", "22.30 h", "10 o'clock", "10\nhrs", "10\rhrs", "9-11 h", "10 h.", "22 h\nLight trap", "22 h. Light trap", "22.30 h. UV trap",
    "15.VI.1950 - 22 h. Light trap", "15.VI.1950 - 22.30 H. UV trap", "15.VI.1950 - 22.30 h", "15/VI/1950 22.30 H. UV"])
def test_a_time_of_day_or_a_season_keeps_the_flag(time):
    assert so._no_verbatim_date(run_of(*DAYS), readings_of()) is True
    timed = (DAY[0] + "\n" + time, DAY[1])
    assert so._no_verbatim_date(run_of(*DAYS, timed), readings_of()) is False
    assert so._no_verbatim_date(run_of(*DAYS), readings_of(timed)) is False
    assert so._no_verbatim_date(run_of(*DAYS, other=(DETERMINATION[0] + " " + time, DETERMINATION[1])),
        readings_of()) is False


@pytest.mark.parametrize(("start", "end", "expected"), [
    (value(text="1948-04-23"), value(text="1948-04-25"), True),
    (value(text="1948-04"), value(text="1948-04"), False),
    (value(text="1948"), value(text="1948"), False),
    (value(text="1948-04-23"), value(text="1948-05"), False),
    (value(text="1948-04-23"), BLANK, False),
    (value(state=ValueState.AMBIGUOUS), value(state=ValueState.AMBIGUOUS), False),
    (value(text="1948-04-23", layer=None), value(text="1948-04-23"), False),
    (BLANK, BLANK, False),
], ids=["days", "month", "year", "to-a-month", "end-blank", "in-doubt", "unchecked-layer", "no-date-at-all"])
def test_the_dates_settled_to_the_day(start, end, expected):
    assert so._no_verbatim_date(run_of(start, end), readings_of()) is expected


@pytest.mark.parametrize("change", ["a-placeholder", "a-span", "a-transcript-unreadable", "a-reading-placeholder"])
def test_an_unreadable_part_of_the_dates_label_keeps_the_flag(change):
    """An unreadable word beside the date may be a time; on another label it does not stop the rule."""
    texts, other, kwargs, readings = list(DAY), list(DETERMINATION), {}, None
    if change == "a-placeholder":
        texts[0] += "\nTime: [unreadable]"
        other[0] = other[0].replace("Kustermop", "[unreadable]")
    elif change == "a-span":
        kwargs["spans"] = ["a faint word"]
    elif change == "a-transcript-unreadable":
        kwargs["unreadable"] = DATE_LABEL
    else:
        readings = readings_of((DAY[0] + " [unreadable]", DAY[1]))
    assert so._no_verbatim_date(run_of(*DAYS, tuple(texts), other=tuple(other), **kwargs),
        readings or readings_of(tuple(texts), tuple(other))) is False
    # The same part on the other label only.
    elsewhere = run_of(*DAYS, other=(DETERMINATION[0].replace("Kustermop", "[unreadable]"), DETERMINATION[1]),
        unreadable=OTHER_LABEL)
    assert so._no_verbatim_date(elsewhere, readings_of(other=(DETERMINATION[0] + " [unreadable]",
        DETERMINATION[1]))) is True


def test_dates_drawn_on_no_label_ask_every_label():
    start, end = (FieldValue(state=ValueState.SUPPORTED, parsed="1948-04-23", layer="settled") for _ in range(2))
    assert so._no_verbatim_date(run_of(start, end), readings_of()) is True
    other = (DETERMINATION[0].replace("Kustermop", "[unreadable]"), DETERMINATION[1])
    assert so._no_verbatim_date(run_of(start, end, other=other), readings_of(other=other)) is False


@pytest.mark.parametrize("text", ["IX-14-46\nH. Hoogstraal", "IX-14-46 H. Hoogstraal", "1X - 14 - 46\nH. Hoogstraal",
    "IX.14.46 H. Hoogstraal", "IV-23-48\nH.R. Goodrich", "Elev. 4800 ft.", "Mt. McKinley", "Malaise Trap", "Hamburg",
    "Hagen, 1861", "1X - 14 - 46 H. Hoogstraal", "IV-23-48 H.R. Goodrich"], ids=["a-name-on-the-next-line",
    "a-name-after-the-date", "a-spaced-date", "a-dotted-date", "two-initials", "feet", "mount", "trap", "a-place",
    "an-author-and-year", "a-spaced-date-then-a-name", "two-initials-after-the-date"])
def test_a_date_and_a_name_or_a_measure_are_no_time_of_day(text):
    """Production records 48a71d53 and f35af3a5 write "IX-14-46" and "1X - 14 - 46" above "H. Hoogstraal": no clock
    time."""
    texts = (text + "\n" + DAY[0], DAY[1])
    assert so._no_verbatim_date(run_of(*DAYS, texts), readings_of(texts)) is True


@pytest.mark.parametrize("written", ["Collecting season: Summer", "VI–VIII", "VI-VIII"])
def test_a_label_with_no_date_the_checks_read_keeps_the_flag(written):
    """Codex's round-1 cases: a season or a range of Roman months, with both dates blank and no other text that
    could be a date."""
    texts, other = (written, written), ("Panorpa\nsp. IVa", "Panorpa\nsp. IVa")
    assert so._no_verbatim_date(run_of(BLANK, BLANK, texts, other=other), readings_of(texts, other)) is False
