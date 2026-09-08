"""Bounded raw-reading metadata/alignment; uncertainty is never agreement.

Offsets are half-open raw Unicode codepoints, with UTF-8/UTF-16 equivalents for
storage and Flutter. No NFC, case folding, whitespace repair or grapheme slicing.
"""

from __future__ import annotations

from array import array
from hashlib import sha256
from typing import Literal
import unicodedata

from pydantic import Field, model_validator

from .authority_registry import Frozen, canonical, digest
from .review_risk import RiskSignal


class MetadataDeclaration(Frozen):
    kind: Literal["language", "script"]
    value: str | None = Field(default=None, min_length=1, max_length=100)
    method: Literal[
        "provider_reported", "model_declared", "classifier_declared", "human_recorded"
    ]
    producer: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=200)
    evidence_ref: str = Field(min_length=1, max_length=1000)
    locator: str = Field(min_length=1, max_length=1000)
    reported_confidence: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unknown_has_no_confidence(self):
        if self.value is None and self.reported_confidence is not None:
            raise ValueError("Unknown metadata cannot carry a confidence value")
        return self


class ReadingEvidenceInput(Frozen):
    observation_id: str = Field(min_length=1, max_length=100)
    region_id: str = Field(min_length=1, max_length=100)
    source_ref: str = Field(min_length=1, max_length=1000)
    source_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    text: str
    source_truncated: bool = False
    declarations: tuple[MetadataDeclaration, ...] = Field(default=(), max_length=32)


class ReadingLimits(Frozen):
    max_codepoints: int = Field(default=100000, ge=1, le=1000000)
    max_utf8_bytes: int = Field(default=400000, ge=1, le=4000000)
    max_alignment_cells: int = Field(default=65536, ge=1, le=1000000)
    max_working_bytes: int = Field(default=4194304, ge=1, le=16000000)
    max_spans: int = Field(default=256, ge=1, le=4096)
    max_alternative_codepoints: int = Field(default=20000, ge=1, le=1000000)


class ReadingReference(Frozen):
    observation_id: str
    region_id: str
    source_ref: str
    source_sha256: str | None
    codepoints: int
    utf8_bytes: int | None
    text_sha256: str | None
    source_truncated: bool


def _reference(
    reading: ReadingEvidenceInput, limits: ReadingLimits
) -> tuple[ReadingReference, str | None]:
    values = dict(
        observation_id=reading.observation_id,
        region_id=reading.region_id,
        source_ref=reading.source_ref,
        source_sha256=reading.source_sha256,
        codepoints=len(reading.text),
        source_truncated=reading.source_truncated,
    )
    if len(reading.text) > limits.max_codepoints:
        return ReadingReference(
            **values, utf8_bytes=None, text_sha256=None
        ), "reading_codepoint_limit"
    hasher, byte_count = sha256(), 0
    try:
        for start in range(0, len(reading.text), 2048):
            chunk = reading.text[start : start + 2048].encode("utf-8")
            byte_count += len(chunk)
            if byte_count > limits.max_utf8_bytes:
                return ReadingReference(
                    **values, utf8_bytes=None, text_sha256=None
                ), "reading_utf8_limit"
            hasher.update(chunk)
    except UnicodeEncodeError:
        return ReadingReference(
            **values, utf8_bytes=None, text_sha256=None
        ), "invalid_unicode_scalar"
    reference = ReadingReference(
        **values, utf8_bytes=byte_count, text_sha256=hasher.hexdigest()
    )
    return reference, "source_truncated" if reading.source_truncated else None


class ScriptHint(Frozen):
    unicode_name_prefix: str
    codepoint_count: int
    method: str = "unicode_name_prefix_diagnostic_not_script_classification"


class ReadingMetadata(Frozen):
    algorithm: str = "reading-metadata-1"
    unicode_version: str
    reference: ReadingReference
    status: Literal["available", "policy_blocked"]
    language_state: Literal["unknown", "declared", "multiple_candidates"]
    script_state: Literal["unknown", "declared", "multiple_candidates"]
    declarations: tuple[MetadataDeclaration, ...]
    script_hints: tuple[ScriptHint, ...] = ()
    reasons: tuple[str, ...]


def summarize_reading(
    reading: ReadingEvidenceInput, limits: ReadingLimits = ReadingLimits()
) -> ReadingMetadata:
    reference, blocked = _reference(reading, limits)
    languages = {
        d.value
        for d in reading.declarations
        if d.kind == "language" and d.value is not None
    }
    scripts = {
        d.value
        for d in reading.declarations
        if d.kind == "script" and d.value is not None
    }
    state = lambda values: (
        "unknown"
        if not values
        else "declared"
        if len(values) == 1
        else "multiple_candidates"
    )
    reasons = [blocked] if blocked else []
    if not languages:
        reasons.append("language_not_reported")
    if not scripts:
        reasons.append("script_not_reported")
    if len(languages) > 1 or len(scripts) > 1:
        reasons.append("multiple_metadata_candidates_not_resolved")
    # Bounded vocabulary, explicitly not a Unicode Script property or language ID.
    prefixes = (
        "LATIN",
        "GREEK",
        "CYRILLIC",
        "ARABIC",
        "HEBREW",
        "DEVANAGARI",
        "THAI",
        "HIRAGANA",
        "KATAKANA",
        "HANGUL",
        "CJK",
    )
    counts: dict[str, int] = {}
    if not blocked:
        for char in reading.text:
            if char.isalpha():
                prefix = unicodedata.name(char, "UNKNOWN").split()[0]
                prefix = prefix if prefix in prefixes else "OTHER_OR_UNKNOWN"
                counts[prefix] = counts.get(prefix, 0) + 1
    return ReadingMetadata(
        unicode_version=unicodedata.unidata_version,
        reference=reference,
        status="policy_blocked" if blocked else "available",
        language_state=state(languages),
        script_state=state(scripts),
        declarations=reading.declarations,
        script_hints=tuple(
            ScriptHint(unicode_name_prefix=k, codepoint_count=v)
            for k, v in sorted(counts.items())
        ),
        reasons=tuple(reasons),
    )


class RawPosition(Frozen):
    codepoint: int
    utf8_byte: int
    utf16_codeunit: int
    line: int
    column_codepoint: int


class ReadingSpan(Frozen):
    start: RawPosition
    end: RawPosition
    text: str


class ReadingAlternative(Frozen):
    operation: Literal["replace", "insert", "delete"]
    left: ReadingSpan
    right: ReadingSpan
    contains_numeral: bool


class ReadingAlignment(Frozen):
    algorithm: str = "bounded-raw-codepoint-levenshtein-1"
    left: ReadingReference
    right: ReadingReference
    status: Literal["agreement", "disagreement", "policy_blocked"]
    alternatives: tuple[ReadingAlternative, ...] = ()
    reasons: tuple[str, ...]
    alignment_cells: int = 0
    reserved_working_bytes: int = 0
    edit_distance: int | None = None
    comparison_sha256: str | None
    offset_convention: str = (
        "zero-based-half-open; line-one-based; column-codepoints-zero-based"
    )


def _positions(text: str, requested: set[int]) -> dict[int, RawPosition]:
    """One linear scan, storing only requested boundary positions; CRLF is one break."""
    result = {}
    byte_offset = utf16_offset = column = 0
    line = 1
    for index in range(len(text) + 1):
        if index in requested:
            result[index] = RawPosition(
                codepoint=index,
                utf8_byte=byte_offset,
                utf16_codeunit=utf16_offset,
                line=line,
                column_codepoint=column,
            )
        if index == len(text):
            break
        char = text[index]
        byte_offset += len(char.encode("utf-8"))
        utf16_offset += 2 if ord(char) > 0xFFFF else 1
        if char == "\r" and index + 1 < len(text) and text[index + 1] == "\n":
            column += 1
        elif char in "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029":
            line += 1
            column = 0
        else:
            column += 1
    return result


def align_readings(
    left: ReadingEvidenceInput,
    right: ReadingEvidenceInput,
    limits: ReadingLimits = ReadingLimits(),
) -> ReadingAlignment:
    if left.region_id != right.region_id or left.observation_id == right.observation_id:
        raise ValueError("Distinct observations of one region are required")
    left_ref, left_blocked = _reference(left, limits)
    right_ref, right_blocked = _reference(right, limits)
    key = digest(
        canonical(
            {
                "left": left_ref.model_dump(),
                "right": right_ref.model_dump(),
                "limits": limits.model_dump(),
            }
        ).encode()
    )
    base = dict(
        left=left_ref,
        right=right_ref,
        comparison_sha256=key
        if left_ref.text_sha256 and right_ref.text_sha256
        else None,
    )
    if left_blocked or right_blocked:
        return ReadingAlignment(
            **base,
            status="policy_blocked",
            reasons=tuple(dict.fromkeys(r for r in (left_blocked, right_blocked) if r)),
        )
    a, b = left.text, right.text
    if not a or not b:
        return ReadingAlignment(
            **base, status="policy_blocked", reasons=("empty_reading_not_agreement",)
        )
    prefix = 0
    while prefix < min(len(a), len(b)) and a[prefix] == b[prefix]:
        prefix += 1
    if prefix == len(a) == len(b):
        return ReadingAlignment(
            **base,
            status="agreement",
            reasons=("exact_raw_text_agreement_not_correctness",),
            edit_distance=0,
        )
    end_a, end_b = len(a), len(b)
    while end_a > prefix and end_b > prefix and a[end_a - 1] == b[end_b - 1]:
        end_a -= 1
        end_b -= 1
    n, m = end_a - prefix, end_b - prefix
    cells = (n + 1) * (m + 1)
    # Compact directions + two uint32 score rows + worst-case grouped edit/output
    # boundary objects. This reservation is conservative, not a process RSS limit.
    reserved = (
        cells
        + 8 * (m + 1)
        + 8192 * min(n + m, limits.max_spans + 1)
        + 8 * (n + m)
        + 16384
    )
    base.update(alignment_cells=cells, reserved_working_bytes=reserved)
    if cells > limits.max_alignment_cells:
        return ReadingAlignment(
            **base,
            status="policy_blocked",
            reasons=("alignment_cell_budget_exhausted",),
        )
    if reserved > limits.max_working_bytes:
        return ReadingAlignment(
            **base,
            status="policy_blocked",
            reasons=("alignment_memory_budget_exhausted",),
        )
    directions = bytearray(cells)
    width = m + 1
    previous = array("I", range(width))
    for j in range(1, width):
        directions[j] = 3
    for i in range(1, n + 1):
        current = array("I", [i]) + array("I", [0]) * m
        directions[i * width] = 2
        for j in range(1, m + 1):
            same = a[prefix + i - 1] == b[prefix + j - 1]
            choices = (
                previous[j - 1] + (not same),
                previous[j] + 1,
                current[j - 1] + 1,
            )
            best = min(choices)
            current[j] = best
            directions[i * width + j] = (
                1 if best == choices[0] else 2 if best == choices[1] else 3
            )
        previous = current
    distance = previous[m]
    # Trace backwards, group contiguous non-equal cells, preserve all raw offsets.
    spans: list[tuple[int, int, int, int]] = []
    i, j = n, m
    group_end: tuple[int, int] | None = None
    while i or j:
        direction = directions[i * width + j]
        same = direction == 1 and a[prefix + i - 1] == b[prefix + j - 1]
        if same and group_end is not None:
            spans.append(
                (prefix + i, prefix + group_end[0], prefix + j, prefix + group_end[1])
            )
            group_end = None
        elif not same and group_end is None:
            group_end = (i, j)
        if direction == 1:
            i, j = i - 1, j - 1
        elif direction == 2:
            i -= 1
        else:
            j -= 1
        if len(spans) > limits.max_spans:
            return ReadingAlignment(
                **base,
                status="policy_blocked",
                reasons=("alignment_span_budget_exhausted",),
            )
    if group_end is not None:
        spans.append((prefix, prefix + group_end[0], prefix, prefix + group_end[1]))
    if len(spans) > limits.max_spans:
        return ReadingAlignment(
            **base,
            status="policy_blocked",
            reasons=("alignment_span_budget_exhausted",),
        )
    if sum(y - x + v - u for x, y, u, v in spans) > limits.max_alternative_codepoints:
        return ReadingAlignment(
            **base,
            status="policy_blocked",
            reasons=("alignment_output_budget_exhausted",),
        )
    pos_a = _positions(a, {p for x, y, _, _ in spans for p in (x, y)})
    pos_b = _positions(b, {p for _, _, u, v in spans for p in (u, v)})
    alternatives = tuple(
        ReadingAlternative(
            operation="insert" if x == y else "delete" if u == v else "replace",
            left=ReadingSpan(start=pos_a[x], end=pos_a[y], text=a[x:y]),
            right=ReadingSpan(start=pos_b[u], end=pos_b[v], text=b[u:v]),
            contains_numeral=any(c.isnumeric() for c in a[x:y])
            or any(c.isnumeric() for c in b[u:v]),
        )
        for x, y, u, v in reversed(spans)
    )
    return ReadingAlignment(
        **base,
        status="disagreement",
        alternatives=alternatives,
        edit_distance=distance,
        reasons=("raw_readings_disagree",),
    )


class ReadingRiskEvidence(Frozen):
    signals: tuple[RiskSignal, ...]
    unmeasured: tuple[str, ...]
    comparison_complete: bool


def reading_risk_evidence(
    alignment: ReadingAlignment, metadata: tuple[ReadingMetadata, ...]
) -> ReadingRiskEvidence:
    evidence = (alignment.left.observation_id, alignment.right.observation_id)
    signals = []
    unmeasured = []
    if alignment.status == "policy_blocked":
        signals.append(
            RiskSignal(code="operational_block", count=1, evidence_ids=evidence)
        )
        unmeasured.append("reading_disagreement")
    elif alignment.status == "disagreement":
        signals.append(
            RiskSignal(
                code="unresolved_disagreement",
                count=len(alignment.alternatives),
                evidence_ids=evidence,
            )
        )
        numeral_count = sum(a.contains_numeral for a in alignment.alternatives)
        if numeral_count:
            signals.append(
                RiskSignal(
                    code="numeral_disagreement",
                    count=numeral_count,
                    evidence_ids=evidence,
                )
            )
    references = {r.observation_id: r for r in (alignment.left, alignment.right)}
    if len({m.reference.observation_id for m in metadata}) != len(metadata):
        raise ValueError("Duplicate reading metadata")
    if any(
        m.reference.observation_id not in references
        or m.reference != references[m.reference.observation_id]
        for m in metadata
    ):
        raise ValueError("Metadata does not belong to compared reading versions")
    for kind in ("language", "script"):
        values = {
            d.value
            for m in metadata
            for d in m.declarations
            if d.kind == kind and d.value is not None
        }
        if (
            len(metadata) != 2
            or len(values) != 1
            or any(
                m.status == "policy_blocked"
                or getattr(m, kind + "_state") != "declared"
                for m in metadata
            )
        ):
            unmeasured.append(kind)
    return ReadingRiskEvidence(
        signals=tuple(signals),
        unmeasured=tuple(unmeasured),
        comparison_complete=alignment.status != "policy_blocked",
    )
