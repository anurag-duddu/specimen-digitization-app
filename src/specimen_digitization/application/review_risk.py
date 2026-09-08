"""Explainable uncalibrated triage and literal disagreement; no clearance authority."""

from datetime import datetime, timezone
from difflib import SequenceMatcher
import unicodedata

from pydantic import Field

from .authority_registry import Frozen, canonical, digest


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


class RiskComponent(Frozen):
    signal: RiskSignal
    weight: int
    contribution: int


class ReviewRisk(Frozen):
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
