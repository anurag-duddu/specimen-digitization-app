"""Typed results shared by the stage 7 harness tools (HARNESS.md section 5).

A tool answers with exactly one HAR-008 outcome, the candidates behind it and
the HAR-010 provenance of every provider request it made; no tool writes a
field. The profile maps fields to tool ids (S3's `CollectionProfile.field_tools`).
The geography types are the interface S8's retrospective georeferencing plan
targets (G12): an accepted plan replaces the implementation, not these types.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .domain import LookupStatus
from .place_text import PLACE_FIELDS
from .reliability import retry_delay

TOOL_IDS = (
    "taxonomy_verifier",
    "geography_lookup",
    "catalog_number_validator",
    "date_parser",
)
# HAR-009: only these are retried inside a tool; the rest are final at once.
RETRYABLE = frozenset(
    {LookupStatus.RATE_LIMITED, LookupStatus.TIMEOUT, LookupStatus.PROVIDER}
)


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceCall(Frozen):
    """One provider request inside a tool call; the harness records one S5
    ToolCall row per source call (G23: GBIF, GNV and COL each separately)."""

    source: str
    query: dict
    retrieved_at: str
    outcome: LookupStatus
    attempt: int = Field(default=1, ge=1)
    raw_ref: str | None = None
    response_sha256: str | None = None
    license: str | None = None
    retry_after_seconds: int | None = None
    sanitized_error: str | None = None


class TaxonCandidate(Frozen):
    """A taxonomic usage from a source; GBIF names may be stored (G28)."""

    source: str
    usage_key: str
    name: str
    canonical_name: str | None = None
    authorship: str | None = None
    rank: str | None = None
    status: str | None = None
    accepted_usage_key: str | None = None


class LocalityLiteral(Frozen):
    """A locality literal exactly as a reading has it; `field_key` None marks
    locality text that belongs to no field (S8: "Mindanao")."""

    field_key: str | None
    literal: str
    source_observation_id: str
    source_region_id: str
    # In "fill the rest", a place value the reviewer entered or changed: a
    # source though no reading holds it, with the harness's value for its
    # field in the run under review as the anchor of the reviewer's own text
    # (HARNESS.md sections 7 and 13; the coordinator's rulings of 06:36Z and
    # 07:33Z on 2026-09-25).
    reviewer: bool = False
    anchor: str | None = None


class GeographyQuery(Frozen):
    literals: list[LocalityLiteral] = Field(min_length=1)
    context: dict = Field(default_factory=dict)
    # What PLAN 4.8's filter reads beside the literals (HARNESS.md section 7,
    # agreed with S8): the record's reading texts, every literal any reading
    # assigns to a non-place field, and the knowledge the profile names, as
    # `harness_knowledge.KNOWLEDGE[knowledge_id]`.
    reading_texts: list[str] = Field(default_factory=list)
    non_place_literals: list[str] = Field(default_factory=list)
    knowledge_id: str | None = None
    # In "fill the rest", the reviewer's own non-place values, which alone of
    # the non-place values cut the reviewer's own text.
    reviewer_non_place_literals: list[str] = Field(default_factory=list)

    @property
    def sources(self) -> list[str]:
        """The query's own sources for PLAN 4.8's filter: its place-field
        literals, the reviewer's in "fill the rest" among them, and its
        unassigned locality text, never a literal it gives a non-place field
        (the coordinator's ruling on #191's review)."""
        return [
            item.literal
            for item in self.literals
            if item.field_key is None or item.field_key in PLACE_FIELDS
        ]


class PlaceCandidate(Frozen):
    """A place a source proposes for one field. Google's candidates carry only
    the place ID (G26): no name, no components, no coordinates."""

    field_key: str
    source: str
    source_record_id: str | None = None
    name: str | None = None
    # The source's exact credit, from S8's manifest (PLAN 4.8); none for Google.
    credit: str | None = None
    components: dict[str, str] = Field(default_factory=dict)
    role: Literal["historical", "modern"] = "modern"
    valid_from: str | None = None
    valid_to: str | None = None


class SourceRef(Frozen):
    name: str
    record_id: str | None = None
    version: str | None = None
    retrieved_at: str | None = None
    license: str | None = None
    credit: str | None = None  # The source's exact credit text (PLAN 4.8).


class GeoreferenceCandidate(Frozen):
    """A point with its uncertainty from openly licensed sources (S8, G12).
    The Google tool never fills one: its coordinates may not be stored."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    uncertainty_m: float | None = Field(default=None, ge=0)
    datum: str | None = None
    protocol: str | None = None
    sources: list[SourceRef] = Field(default_factory=list)
    coordinate_precision: float | None = None
    footprint_wkt: str | None = None
    spatial_fit: float | None = None
    remarks: str | None = None
    verification_status: str = "requires verification"
    georeferenced_by: str | None = None
    georeferenced_date: str | None = None


class Check(Frozen):
    name: str
    result: Literal["supports", "conflicts", "not_assessable"]
    detail: str | None = None


class Derivation(Frozen):
    """A value for a field the label leaves out (G37), in the derived layer
    (G38). S8's geographic tool emits containment, elevation-model and
    gazetteer derivations; the harness emits those that need no outside data.
    `inputs` maps each settled field it comes from to that field's value."""

    field_key: str
    value: str
    unit: str | None = None
    # A derived date's precision, as its source date was written (G24, G44).
    precision: Literal["day", "month", "year"] | None = None
    method: Literal[
        "containment",
        "elevation_model",
        "gazetteer_name",
        "unit_conversion",
        "stated_elevation",
        "stated_date",
    ]
    authority: SourceRef
    inputs: dict[str, str] = Field(default_factory=dict)
    evidence: list[Check] = Field(default_factory=list)


class ToolResult(Frozen):
    """What one tool call returns to the harness and its trace."""

    tool: str
    tool_version: str
    outcome: LookupStatus
    field_outcomes: dict[str, LookupStatus] = Field(default_factory=dict)
    taxa: list[TaxonCandidate] = Field(default_factory=list)
    places: list[PlaceCandidate] = Field(default_factory=list)
    georeferences: list[GeoreferenceCandidate] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)
    parsed: dict | None = None
    sub_calls: list[SourceCall] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    derivations: list[Derivation] = Field(default_factory=list)


def with_retries(
    call: Callable[[int], SourceCall],
    *,
    attempts: int = 3,
    cap_seconds: float = 20,
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] | None = None,
) -> list[SourceCall]:
    """Run one provider request with bounded retries (HAR-009): a rate limit, a
    timeout or a provider error is retried with backoff and jitter, never
    sooner than the provider's Retry-After, at most `attempts` times in all.
    Returns every attempt, the final one last, so each is recorded."""
    made = []
    for attempt in range(1, attempts + 1):
        made.append(call(attempt))
        last = made[-1]
        if last.outcome not in RETRYABLE or attempt == attempts:
            break
        if last.retry_after_seconds and last.retry_after_seconds > cap_seconds:
            break  # The provider asks for longer than a step may wait.
        sleep(
            min(
                cap_seconds,
                retry_delay(attempt, last.retry_after_seconds, random_value),
            )
        )
    return made
