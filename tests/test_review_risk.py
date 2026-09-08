import pytest

from specimen_digitization.application.review_risk import (
    Reading,
    RiskPolicy,
    RiskSignal,
    RiskWeight,
    compare_readings,
    review_risk,
)


def test_minority_numeral_span_line_and_script_uncertainty_are_retained():
    left = Reading(
        observation_id="a", region_id="r", text="Illinois\n1900", language="en"
    )
    right = Reading(
        observation_id="b", region_id="r", text="Illinois\n1908", language="en"
    )
    difference = compare_readings(left, right)
    span = difference.differences[0]
    assert left.text[slice(*span.left_span)] == "0"
    assert right.text[slice(*span.right_span)] == "8"
    assert span.contains_numeral and span.evidence_ids == ("a", "b")
    assert difference.differing_lines == (2,)
    assert set(difference.reasons) == {
        "literal_disagreement",
        "numeral_disagreement",
        "script_unconfirmed",
    }
    assert compare_readings(left, right) == difference


def test_risk_explains_inputs_and_cannot_override_validation_or_disposition():
    signals = (
        RiskSignal(code="hard_validation", count=1, evidence_ids=("validation-1",)),
        RiskSignal(
            code="numeral_disagreement", count=1, evidence_ids=("obs-a", "obs-b")
        ),
    )
    result = review_risk(signals)
    assert result.composite == 45 and result.components[0].contribution == 25
    assert result.calibrated is False and result.calibration_dataset_version is None
    assert "disposition" not in result.model_dump()
    zero = review_risk(
        signals, RiskPolicy(weights=(RiskWeight(code="hard_validation", weight=0),))
    )
    assert zero.composite == 0 and "hard_validation" in zero.reasons
    assert "unweighted_signal" in zero.reasons
    with pytest.raises(ValueError):
        review_risk((signals[0], signals[0]))
