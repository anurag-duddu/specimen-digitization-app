"""Explainable uncalibrated triage and literal disagreement; no clearance authority."""

from __future__ import annotations

from datetime import datetime, timezone
from difflib import SequenceMatcher
import unicodedata

from typing import TYPE_CHECKING, Literal

from pydantic import Field, model_validator

from .authority_registry import Frozen, canonical, digest

if TYPE_CHECKING:
    from .reading_evidence import ReadingAlignment, ReadingMetadata


class Reading(Frozen):
    observation_id: str
    region_id: str
    text: str = Field(max_length=8000)
    language: str | None = None
    script: str | None = None


class SpanDifference(Frozen):
    left_observation_id: str
    right_observation_id: str
    left_span: tuple[int, int]
    right_span: tuple[int, int]
    left_text: str
    right_text: str
    contains_numeral: bool
    evidence_ids: tuple[str, ...]


class Disagreement(Frozen):
    version: str = "literal-difference-1"
    differences: tuple[SpanDifference, ...]
    differing_lines: tuple[int, ...]
    scripts_observed: tuple[str, ...]
    language_candidates: tuple[str, ...]
    reasons: tuple[str, ...]
    input_sha256: str


def compare_readings(left: Reading, right: Reading) -> Disagreement:
    if left.region_id != right.region_id or left.observation_id == right.observation_id:
        raise ValueError("Compare distinct observations of the same source region")
    differences = []
    for tag, a, b, c, d in SequenceMatcher(
        None, left.text, right.text, autojunk=False
    ).get_opcodes():
        if tag != "equal":
            differences.append(
                SpanDifference(
                    left_observation_id=left.observation_id,
                    right_observation_id=right.observation_id,
                    left_span=(a, b),
                    right_span=(c, d),
                    left_text=left.text[a:b],
                    right_text=right.text[c:d],
                    contains_numeral=any(
                        ch.isdigit() for ch in left.text[a:b] + right.text[c:d]
                    ),
                    evidence_ids=(left.observation_id, right.observation_id),
                )
            )
    lines_a, lines_b = left.text.splitlines(), right.text.splitlines()
    lines = tuple(
        i + 1
        for i in range(max(len(lines_a), len(lines_b)))
        if (lines_a[i] if i < len(lines_a) else None)
        != (lines_b[i] if i < len(lines_b) else None)
    )
    scripts = tuple(
        sorted(
            {
                unicodedata.name(c, "UNKNOWN").split()[0]
                for c in left.text + right.text
                if c.isalpha()
            }
        )
    )
    reasons = []
    if differences:
        reasons.append("literal_disagreement")
    if any(d.contains_numeral for d in differences):
        reasons.append("numeral_disagreement")
    if left.script is None or right.script is None or left.script != right.script:
        reasons.append("script_unconfirmed")
    if (
        left.language is None
        or right.language is None
        or left.language != right.language
    ):
        reasons.append("language_unconfirmed")
    return Disagreement(
        differences=tuple(differences),
        differing_lines=lines,
        scripts_observed=scripts,
        language_candidates=tuple(
            sorted({r.language for r in (left, right) if r.language})
        ),
        reasons=tuple(reasons),
        input_sha256=digest(
            canonical([left.model_dump(), right.model_dump()]).encode()
        ),
    )


class RiskSignal(Frozen):
    code: str = Field(min_length=1)
    count: int = Field(ge=0, le=10000)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    field_key: str | None = None


class RiskWeight(Frozen):
    code: str
    weight: int = Field(ge=0, le=100)


class RiskPolicy(Frozen):
    id: str = Field(default="review-risk-draft", min_length=1, max_length=100)
    synthetic: bool = False
    version: str = "review-risk-draft-1"
    feature_version: str = "concrete-signals-1"
    weights: tuple[RiskWeight, ...] = (
        RiskWeight(code="hard_validation", weight=25),
        RiskWeight(code="unresolved_disagreement", weight=20),
        RiskWeight(code="numeral_disagreement", weight=20),
        RiskWeight(code="authority_ambiguity", weight=15),
        RiskWeight(code="contradicting_evidence", weight=20),
        RiskWeight(code="missing_coverage", weight=25),
        RiskWeight(code="operational_block", weight=10),
    )
    calibration_dataset_version: str | None = None

    @property
    def sha256(self) -> str:
        return digest(canonical(self.model_dump(mode="json")).encode())

    @property
    def reference(self) -> RiskPolicyReference:
        return RiskPolicyReference(id=self.id, version=self.version, digest=self.sha256)


class RiskComponent(Frozen):
    signal: RiskSignal
    weight: int
    contribution: int


class ReviewRisk(Frozen):
    policy_id: str = "review-risk-draft"
    policy_sha256: str | None = None
    policy_version: str
    feature_version: str
    components: tuple[RiskComponent, ...]
    composite: int
    reasons: tuple[str, ...]
    calibration_dataset_version: str | None
    calibrated: bool = False
    created_at: str
    input_sha256: str
    intended_use: str = "review_prioritization_only"


def review_risk(
    signals: tuple[RiskSignal, ...], policy: RiskPolicy = RiskPolicy()
) -> ReviewRisk:
    weights = {w.code: w.weight for w in policy.weights}
    if len(weights) != len(policy.weights):
        raise ValueError("Duplicate risk weight")
    if len({(s.code, s.field_key) for s in signals}) != len(signals):
        raise ValueError("Duplicate signal would inflate triage")
    components = tuple(
        RiskComponent(
            signal=s,
            weight=weights.get(s.code, 0),
            contribution=min(100, s.count * weights.get(s.code, 0)),
        )
        for s in signals
    )
    reasons = tuple(s.code for s in signals if s.count)
    if any(s.code not in weights for s in signals):
        reasons += ("unweighted_signal",)
    return ReviewRisk(
        policy_id=policy.id,
        policy_sha256=policy.sha256,
        policy_version=policy.version,
        feature_version=policy.feature_version,
        components=components,
        composite=min(100, sum(c.contribution for c in components)),
        reasons=reasons,
        calibration_dataset_version=policy.calibration_dataset_version,
        created_at=datetime.now(timezone.utc).isoformat(),
        input_sha256=digest(
            canonical(
                {
                    "signals": [s.model_dump() for s in signals],
                    "policy": policy.model_dump(),
                }
            ).encode()
        ),
    )


class RiskPolicyReference(Frozen):
    id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class RiskPolicyEntry(Frozen):
    policy: RiskPolicy
    status: Literal["draft", "published", "revoked"] = "draft"


class RiskPolicyResolution(Frozen):
    status: Literal["resolved", "blocked"]
    reference: RiskPolicyReference | None
    registry_version: str
    reason: str
    policy: RiskPolicy | None = None

    @model_validator(mode="after")
    def pin_matches(self):
        if self.status == "resolved" and (
            self.policy is None or self.reference != self.policy.reference
        ):
            raise ValueError("Resolved risk policy must match the exact reference")
        if self.status == "blocked" and self.policy is not None:
            raise ValueError("Blocked resolution cannot expose an executable fallback")
        return self


class RiskPolicyRegistry(Frozen):
    version: str = Field(min_length=1)
    entries: tuple[RiskPolicyEntry, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def unique_immutable_versions(self):
        identities = [(e.policy.id, e.policy.version) for e in self.entries]
        if len(set(identities)) != len(identities):
            raise ValueError("Duplicate risk policy ID/version")
        for entry in self.entries:
            if len({w.code for w in entry.policy.weights}) != len(entry.policy.weights):
                raise ValueError("Duplicate risk policy weight")
        return self

    def resolve(
        self, reference: RiskPolicyReference | None, *, allow_synthetic: bool = False
    ) -> RiskPolicyResolution:
        reason = "risk_policy_reference_missing"
        if reference is not None:
            entry = next(
                (
                    e
                    for e in self.entries
                    if (e.policy.id, e.policy.version)
                    == (reference.id, reference.version)
                ),
                None,
            )
            if entry is None:
                reason = "risk_policy_unknown_id_or_version"
            elif entry.status != "published":
                reason = "risk_policy_" + entry.status
            elif entry.policy.sha256 != reference.digest:
                reason = "risk_policy_digest_mismatch"
            elif entry.policy.synthetic and not allow_synthetic:
                reason = "synthetic_risk_policy_not_allowed"
            else:
                return RiskPolicyResolution(
                    status="resolved",
                    reference=reference,
                    registry_version=self.version,
                    reason="exact_published_risk_policy",
                    policy=entry.policy,
                )
        return RiskPolicyResolution(
            status="blocked",
            reference=reference,
            registry_version=self.version,
            reason=reason,
        )


def synthetic_risk_policies() -> RiskPolicyRegistry:
    """Explicit test policies; neither represents an institution-approved threshold."""
    balanced = RiskPolicy(
        id="synthetic-review-risk-balanced", version="1", synthetic=True
    )
    numeral = balanced.model_copy(
        update={
            "id": "synthetic-review-risk-numeral-sensitive",
            "weights": tuple(
                RiskWeight(
                    code=w.code,
                    weight=40 if w.code == "numeral_disagreement" else w.weight,
                )
                for w in balanced.weights
            ),
        }
    )
    return RiskPolicyRegistry(
        version="synthetic-risk-registry-1",
        entries=(
            RiskPolicyEntry(policy=balanced, status="published"),
            RiskPolicyEntry(policy=numeral, status="published"),
        ),
    )


class ScopedReviewRisk(Frozen):
    scope: Literal["label", "field", "specimen"]
    target_id: str
    status: Literal["scored", "unmeasured", "blocked"]
    policy_reference: RiskPolicyReference | None
    registry_version: str
    feature_version: str | None
    components: tuple[RiskComponent, ...]
    composite: int | None
    reasons: tuple[str, ...]
    unmeasured: tuple[str, ...]
    calibrated: Literal[False] = False
    calibration_dataset_version: str | None
    clearance_authority: Literal[False] = False
    intended_use: str = "review_prioritization_only"
    created_at: str
    input_sha256: str


def assess_risk(
    signals: tuple[RiskSignal, ...],
    resolution: RiskPolicyResolution,
    *,
    scope: Literal["label", "field", "specimen"],
    target_id: str,
    unmeasured: tuple[str, ...] = (),
    blocked_reasons: tuple[str, ...] = (),
) -> ScopedReviewRisk:
    """Published-policy assessment; unknown inputs never masquerade as zero risk."""
    if len(signals) > 1000:
        raise ValueError("Risk signal budget exceeded")
    missing = list(dict.fromkeys(unmeasured))
    blocked = list(dict.fromkeys(blocked_reasons))
    components = ()
    score = None
    reasons = [s.code for s in signals if s.count]
    if resolution.status == "blocked":
        blocked.append(resolution.reason)
    else:
        policy = resolution.policy
        primitive = review_risk(signals, policy)
        components, score = primitive.components, primitive.composite
        known_weights = {w.code for w in policy.weights}
        missing.extend(
            "weight:" + s.code for s in signals if s.code not in known_weights
        )
        reasons = list(primitive.reasons)
    if any(s.code == "operational_block" and s.count for s in signals):
        blocked.append("operational_evidence_blocked")
    missing = list(dict.fromkeys(missing))
    status = "blocked" if blocked else "unmeasured" if missing else "scored"
    return ScopedReviewRisk(
        scope=scope,
        target_id=target_id,
        status=status,
        policy_reference=resolution.reference,
        registry_version=resolution.registry_version,
        feature_version=resolution.policy.feature_version
        if resolution.policy
        else None,
        components=components,
        composite=score if status == "scored" else None,
        reasons=tuple(
            dict.fromkeys((*reasons, *blocked, *("unmeasured:" + m for m in missing)))
        ),
        unmeasured=tuple(missing),
        calibration_dataset_version=resolution.policy.calibration_dataset_version
        if resolution.policy
        else None,
        created_at=datetime.now(timezone.utc).isoformat(),
        input_sha256=digest(
            canonical(
                {
                    "scope": scope,
                    "target_id": target_id,
                    "signals": [s.model_dump() for s in signals],
                    "resolution": resolution.model_dump(),
                    "unmeasured": missing,
                    "blocked": blocked,
                }
            ).encode()
        ),
    )


def label_review_risk(
    region_id: str,
    observation_ids: tuple[str, ...],
    alignments: tuple[ReadingAlignment, ...],
    metadata: tuple[ReadingMetadata, ...],
    resolution: RiskPolicyResolution,
    *,
    additional_signals: tuple[RiskSignal, ...] = (),
    unmeasured: tuple[str, ...] = (),
) -> ScopedReviewRisk:
    """Pairwise observed label risk. This does not prove model independence/coverage."""
    from .reading_evidence import reading_risk_evidence

    if (
        len(observation_ids) > 8
        or len(alignments) > 28
        or len(metadata) > 8
        or len(additional_signals) > 100
    ):
        raise ValueError("Label risk input budget exceeded")
    if len(set(observation_ids)) != len(observation_ids):
        raise ValueError("Duplicate label observation IDs")
    if len({m.reference.observation_id for m in metadata}) != len(metadata):
        raise ValueError("Duplicate label metadata")
    if any(
        m.reference.region_id != region_id
        or m.reference.observation_id not in observation_ids
        for m in metadata
    ):
        raise ValueError("Label metadata lineage mismatch")
    expected = {
        frozenset((a, b))
        for index, a in enumerate(observation_ids)
        for b in observation_ids[index + 1 :]
    }
    seen: set[frozenset[str]] = set()
    signals = list(additional_signals)
    missing, blocked = list(unmeasured), []
    for alignment in alignments:
        ids = frozenset((alignment.left.observation_id, alignment.right.observation_id))
        if (
            alignment.left.region_id != region_id
            or alignment.right.region_id != region_id
            or ids not in expected
            or ids in seen
        ):
            raise ValueError("Label comparison lineage or duplicate pair")
        seen.add(ids)
        pair_metadata = tuple(m for m in metadata if m.reference.observation_id in ids)
        evidence = reading_risk_evidence(alignment, pair_metadata)
        signals.extend(evidence.signals)
        missing.extend(evidence.unmeasured)
        if alignment.status == "policy_blocked":
            blocked.extend(alignment.reasons)
    if len(observation_ids) < 2 or seen != expected:
        missing.append("reading_comparisons")
    if not alignments:
        missing.extend(("language", "script"))
    # Aggregate repeated codes across distinct comparison pairs while retaining
    # every observation/evidence ID. Counts mean pair/span signals, not error rate.
    grouped: dict[tuple[str, str | None], list[RiskSignal]] = {}
    for signal in signals:
        grouped.setdefault((signal.code, signal.field_key), []).append(signal)
    combined = tuple(
        RiskSignal(
            code=code,
            field_key=field,
            count=sum(s.count for s in group),
            evidence_ids=tuple(dict.fromkeys(e for s in group for e in s.evidence_ids)),
        )
        for (code, field), group in grouped.items()
    )
    return assess_risk(
        combined,
        resolution,
        scope="label",
        target_id=region_id,
        unmeasured=tuple(dict.fromkeys(missing)),
        blocked_reasons=tuple(dict.fromkeys(blocked)),
    )
