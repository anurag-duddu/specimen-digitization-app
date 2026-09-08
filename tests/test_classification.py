from hashlib import sha256

import pytest
from pydantic import ValidationError

from specimen_digitization.application.classification import (
    Candidate,
    ClassificationRequest,
    ClassificationResult,
    ManualSelection,
    SelectionPolicy,
    UnconfiguredClassifier,
    classify,
    correction_invalidation,
    select_profile,
)
from specimen_digitization.application.collection_profiles import (
    CollectionNode,
    CollectionProfileRegistry,
    ProfileMapping,
    insects_registry,
)

DIGEST = sha256(b"synthetic classifier input").hexdigest()


def result(**updates):
    values = dict(
        status="completed",
        input_sha256=DIGEST,
        candidates=(
            Candidate(
                collection_id="insects", score=0.9, reasons=("synthetic_fixture",)
            ),
        ),
        reason="synthetic_fixture",
        adapter_version="fixture-v1",
        route_id="synthetic",
        model_version="fixture-v1",
        prompt_version="fixture-v1",
        raw_response_ref="fixture://classification-v1",
        synthetic=True,
    )
    values.update(updates)
    return ClassificationResult(**values)


def test_unconfigured_blocks_but_manual_choice_is_explicit():
    request = ClassificationRequest(
        asset_id="synthetic", input_sha256=DIGEST, collection_ids=("insects",)
    )
    blocked = classify(request, UnconfiguredClassifier())
    assert not blocked.candidates
    registry = insects_registry(synthetic=True)
    policy = SelectionPolicy(version="synthetic-v1", allow_synthetic=True)
    assert select_profile(blocked, registry, policy).status == "review"
    assert (
        select_profile(
            blocked,
            registry,
            policy,
            ManualSelection(
                collection_id="insects", actor_id="reviewer", reason="Synthetic review"
            ),
        ).status
        == "selected"
    )
    with pytest.raises(ValidationError):
        ManualSelection(collection_id="insects", actor_id="reviewer", reason=" ")


def test_calibration_thresholds_and_synthetic_gate():
    registry = insects_registry(synthetic=True)
    registry = registry.model_copy(
        update={
            "profiles": (
                registry.profiles[0].model_copy(
                    update={"classification_confirmation_required": False}
                ),
            )
        }
    )
    assert (
        select_profile(result(), registry, SelectionPolicy(version="v1")).reason
        == "synthetic_classifier_forbidden"
    )
    policy = SelectionPolicy(
        version="v1",
        allow_synthetic=True,
        require_confirmation=False,
        minimum_score=0.8,
        minimum_margin=0.2,
    )
    assert (
        select_profile(result(), registry, policy).reason
        == "classification_uncalibrated"
    )
    policy = policy.model_copy(update={"calibration_version": "synthetic-calibration"})
    assert (
        select_profile(
            result(calibration_version="synthetic-calibration"), registry, policy
        ).status
        == "selected"
    )
    assert (
        select_profile(
            result(
                calibration_version="synthetic-calibration",
                candidates=(
                    Candidate(
                        collection_id="insects", score=0.79, reasons=("fixture",)
                    ),
                ),
            ),
            registry,
            policy,
        ).reason
        == "classification_ambiguous"
    )


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -1, 1.01])
def test_malformed_score_rejected(score):
    with pytest.raises(ValidationError):
        Candidate(collection_id="insects", score=score, reasons=("fixture",))


def test_adapter_boundary_and_provenance():
    request = ClassificationRequest(
        asset_id="fixture", input_sha256=DIGEST, collection_ids=("other",)
    )

    class SyntheticClassifier:
        def classify(self, request):
            return result()

    with pytest.raises(ValueError, match="out-of-contract"):
        classify(request, SyntheticClassifier())
    with pytest.raises(ValidationError):
        result(raw_response_ref=None)
    with pytest.raises(ValidationError):
        result(candidates=result().candidates * 2)


def test_correction_selects_distinct_profile_without_mutating_original():
    original = insects_registry(synthetic=True)
    second = original.profiles[0].model_copy(
        update={
            "id": "synthetic_other",
            "collection_id": "synthetic-other",
            "version": "fixture-v2",
        }
    )
    registry = CollectionProfileRegistry(
        version="two-fixtures",
        nodes=original.nodes
        + (CollectionNode(id="synthetic-other", name="Synthetic other"),),
        profiles=original.profiles + (second,),
        mappings=original.mappings
        + (
            ProfileMapping(
                collection_id="synthetic-other",
                profile_id=second.id,
                profile_version=second.version,
            ),
        ),
    )
    selected = select_profile(
        result(),
        registry,
        SelectionPolicy(version="test", allow_synthetic=True),
        ManualSelection(
            collection_id="synthetic-other",
            actor_id="fixture-reviewer",
            reason="Correction fixture",
        ),
    )
    assert selected.profile.id == second.id
    assert original.profiles[0].id == "zoology_insects"
    invalidation = correction_invalidation("classification")
    assert (
        invalidation.new_run_required and "segmenting" in invalidation.supersede_stages
    )
    assert invalidation.preserve_observations and not invalidation.training_authorized
    assert "transcribing" not in correction_invalidation("field").supersede_stages


def test_rank_digest_and_ties_fail_closed():
    first = Candidate(collection_id="insects", score=0.9, reasons=("synthetic",))
    other = Candidate(collection_id="other", score=0.95, reasons=("synthetic",))
    with pytest.raises(ValidationError):
        result(candidates=(first, other))

    class WrongInputClassifier:
        def classify(self, request):
            return result(input_sha256=sha256(b"wrong input").hexdigest())

    request = ClassificationRequest(
        asset_id="fixture", input_sha256=DIGEST, collection_ids=("insects",)
    )
    with pytest.raises(ValueError, match="digest mismatch"):
        classify(request, WrongInputClassifier())
    policy = SelectionPolicy(
        version="synthetic",
        allow_synthetic=True,
        require_confirmation=False,
        minimum_score=0,
        minimum_margin=0,
        calibration_version="synthetic",
    )
    tied = result(
        candidates=(
            first,
            Candidate(collection_id="other", score=0.9, reasons=("synthetic",)),
        ),
        calibration_version="synthetic",
    )
    assert (
        select_profile(tied, insects_registry(synthetic=True), policy).reason
        == "classification_ambiguous"
    )


def test_profile_confirmation_cannot_be_waived_by_call_policy():
    registry = insects_registry(synthetic=True)
    policy = SelectionPolicy(
        version="fixture",
        allow_synthetic=True,
        require_confirmation=False,
        minimum_score=0,
        minimum_margin=0,
        calibration_version="fixture",
    )
    assert (
        select_profile(result(calibration_version="fixture"), registry, policy).reason
        == "profile_confirmation_required"
    )
