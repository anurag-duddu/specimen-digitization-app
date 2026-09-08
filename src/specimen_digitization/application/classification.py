"""Classifier boundary: no production model or calibration is assumed."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import Field, model_validator

from .collection_profiles import (
    CollectionProfileRegistry,
    FrozenRecord,
    ProfileResolution,
)


class ClassificationRequest(FrozenRecord):
    asset_id: str = Field(min_length=1)
    input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    collection_ids: tuple[str, ...] = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=20)


class Candidate(FrozenRecord):
    collection_id: str = Field(min_length=1)
    score: float = Field(ge=0, le=1, allow_inf_nan=False)
    reasons: tuple[str, ...] = Field(min_length=1)


class ClassificationResult(FrozenRecord):
    status: Literal["completed", "blocked"]
    input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidates: tuple[Candidate, ...] = ()
    reason: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    route_id: str | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    raw_response_ref: str | None = None
    calibration_version: str | None = None
    synthetic: bool = False

    @model_validator(mode="after")
    def validate_result(self):
        if self.status == "blocked" and self.candidates:
            raise ValueError("blocked result cannot contain predictions")
        if self.status == "completed":
            if not all(
                (
                    self.route_id,
                    self.model_version,
                    self.prompt_version,
                    self.raw_response_ref,
                )
            ):
                raise ValueError("completed predictions require provenance")
            ids = [c.collection_id for c in self.candidates]
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate candidate")
            if list(self.candidates) != sorted(self.candidates, key=lambda c: -c.score):
                raise ValueError("candidates must be ranked")
        return self


class ClassifierAdapter(Protocol):
    def classify(self, request: ClassificationRequest) -> ClassificationResult: ...


class UnconfiguredClassifier:
    def classify(self, request: ClassificationRequest) -> ClassificationResult:
        return ClassificationResult(
            status="blocked",
            input_sha256=request.input_sha256,
            reason="approved_classifier_route_missing",
            adapter_version="classifier-contract-v1",
        )


def classify(
    request: ClassificationRequest, adapter: ClassifierAdapter
) -> ClassificationResult:
    result = adapter.classify(request)
    if result.input_sha256 != request.input_sha256:
        raise ValueError("classifier input digest mismatch")
    if len(result.candidates) > request.top_k or any(
        c.collection_id not in request.collection_ids for c in result.candidates
    ):
        raise ValueError("classifier returned out-of-contract candidates")
    return result


class SelectionPolicy(FrozenRecord):
    version: str = Field(min_length=1)
    require_confirmation: bool = True
    minimum_score: float = Field(default=1, ge=0, le=1, allow_inf_nan=False)
    minimum_margin: float = Field(default=1, ge=0, le=1, allow_inf_nan=False)
    calibration_version: str | None = None
    allow_synthetic: bool = False


class ManualSelection(FrozenRecord):
    collection_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


def select_profile(
    result: ClassificationResult,
    registry: CollectionProfileRegistry,
    policy: SelectionPolicy,
    manual_selection: ManualSelection | None = None,
) -> ProfileResolution:
    """Caller authorizes collection scope and persists request/result/decision atomically."""

    def review(reason):
        return ProfileResolution(status="review", reason=reason)

    if manual_selection is not None:
        resolved = registry.resolve(manual_selection.collection_id)
    else:
        if result.status == "blocked":
            return review(result.reason)
        if result.synthetic and not policy.allow_synthetic:
            return review("synthetic_classifier_forbidden")
        if policy.require_confirmation:
            return review("human_confirmation_required")
        if (
            not policy.calibration_version
            or result.calibration_version != policy.calibration_version
        ):
            return review("classification_uncalibrated")
        if not result.candidates:
            return review("no_candidates")
        first = result.candidates[0]
        second = result.candidates[1].score if len(result.candidates) > 1 else 0
        if (
            first.score < policy.minimum_score
            or first.score - second < policy.minimum_margin
            or first.score == second
        ):
            return review("classification_ambiguous")
        resolved = registry.resolve(first.collection_id)
    if (
        manual_selection is None
        and resolved.profile
        and resolved.profile.classification_confirmation_required
    ):
        return review("profile_confirmation_required")
    if resolved.profile and resolved.profile.synthetic and not policy.allow_synthetic:
        return review("synthetic_profile_forbidden")
    return resolved


class CorrectionInvalidation(FrozenRecord):
    correction: Literal["classification", "segmentation", "transcription", "field"]
    supersede_stages: tuple[str, ...]
    new_run_required: bool
    preserve_originals: Literal[True] = True
    preserve_observations: Literal[True] = True
    training_authorized: Literal[False] = False


def correction_invalidation(
    kind: Literal["classification", "segmentation", "transcription", "field"],
) -> CorrectionInvalidation:
    stages = (
        "quality_check",
        "segmenting",
        "transcribing",
        "adjudicating",
        "extracting",
        "validating",
        "finalizing",
    )
    starts = {"classification": 0, "segmentation": 2, "transcription": 4, "field": 5}
    if kind not in starts:
        raise ValueError("unknown correction kind")
    return CorrectionInvalidation(
        correction=kind,
        supersede_stages=stages[starts[kind] :],
        new_run_required=kind in {"classification", "segmentation"},
    )
