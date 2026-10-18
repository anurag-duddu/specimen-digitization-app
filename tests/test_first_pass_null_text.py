"""A first pass whose pick is written as the text "null" picks no reader.

GLM-5.3-Flash on Novita answers the first pass's `selected_reader` with the
string "null" where the schema asks for JSON null (its retries once wrote
"None", once ""), and often writes it again on the output retry. In Logfire,
from 2026-10-12 03:00 UTC to 2026-10-18 14:45 UTC, 16 traces hold a first-pass
run that ended "Exceeded maximum output retries" (`model_malformed_response`),
and each of the 16 holds an answer whose `selected_reader` is the string
"null"; the 2026-10-18 provider probe through `first_pass_direct` recorded the
same answers (HARNESS.md section 3, "A first pass's null written as text").
Such a value names no reader, so it is read as null: the answer is used, and it
selects no reading (G19).
"""

import pytest

from specimen_digitization.application.first_pass import FirstPassOutput, output_problems
from specimen_digitization.application.reliability import AdapterFailure

from test_first_pass import VALID, direct_first_pass

LETTERS = {"A": None, "B": None}


def no_pick(text):
    """VALID's answer with its pick written as this text, as recorded."""
    return dict(VALID, selected_reader=text)


@pytest.mark.parametrize("text", ["null", "None", "", " NULL "])
def test_a_pick_written_as_a_null_text_is_no_pick(text):
    output = FirstPassOutput.model_validate(no_pick(text))

    assert output.selected_reader is None
    assert output_problems(output, LETTERS, 3) == []


@pytest.mark.parametrize("text", ["a", "neither", "C", "nil"])
def test_any_other_text_is_still_refused(text):
    output = FirstPassOutput.model_validate(no_pick(text))

    assert output_problems(output, LETTERS, 3) == [
        "selected_reader must be one of ['A', 'B'] or null"
    ]


def test_an_answer_whose_pick_is_null_text_is_decided_on_its_first_request(
    monkeypatch, tmp_path
):
    # Before: refused, the retry answered the same, and the call failed as
    # model_malformed_response after two requests (the recorded shape).
    calls = []
    decision, readings = direct_first_pass(
        monkeypatch, tmp_path, calls, no_pick("null"), no_pick("null")
    )

    assert len(calls) == 1
    assert decision.selected_observation_id is None
    assert decision.call.completion_state == "validated_output"
    assert decision.rationale == VALID["rationale"]
    assert [d.verdict for d in decision.differences] == [readings[1].id] * 3


def test_a_real_letter_after_a_null_text_retry_is_unchanged(monkeypatch, tmp_path):
    # A lower-case letter is not a null text: it is refused, and the retry's
    # pick stands, as before.
    calls = []
    decision, readings = direct_first_pass(
        monkeypatch, tmp_path, calls, no_pick("b"), VALID
    )

    assert len(calls) == 2
    assert decision.selected_observation_id == readings[1].id


def test_an_answer_still_malformed_after_its_retry_still_fails(monkeypatch, tmp_path):
    with pytest.raises(AdapterFailure) as failure:
        direct_first_pass(monkeypatch, tmp_path, [], no_pick("C"), no_pick("C"))

    assert str(failure.value) == "model_malformed_response"
