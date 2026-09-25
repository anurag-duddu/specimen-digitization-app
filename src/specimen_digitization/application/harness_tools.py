"""Typed results shared by the stage 7 harness tools (HARNESS.md section 6).

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

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .domain import LookupStatus
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
# G26: of Google's answers only the place ID, the outcome and a response
# fingerprint may be kept.
GOOGLE_SOURCES = frozenset({"google-maps-geocoding"})


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceCall(Frozen):
    """One provider request inside a tool call; the harness records one S5
    ToolCall row per source call (G23: GBIF, GNV and COL each separately).
    For Google, `raw_ref` holds the tool's own record (place ID, outcome and
    response fingerprint), never Google's body (G26)."""

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
    """A taxonomic usage from a source. GBIF's names are kept as GBIF.md
    134-160's evidence contract lists them, the coordinator's reading; G28
    itself stores the label's spelling and GBIF's settled name."""

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


class GeographyQuery(Frozen):
    literals: list[LocalityLiteral] = Field(min_length=1)
    context: dict = Field(default_factory=dict)


class PlaceCandidate(Frozen):
    """A place a source proposes for one field. Google's candidates carry only
    the place ID (G26): no name, no components, no coordinates."""

    field_key: str
    source: str
    source_record_id: str | None = None
    name: str | None = None
    components: dict[str, str] = Field(default_factory=dict)
    role: Literal["historical", "modern"] = "modern"
    valid_from: str | None = None
    valid_to: str | None = None

    @model_validator(mode="after")
    def google_keeps_only_a_place_id(self) -> "PlaceCandidate":
        if self.source in GOOGLE_SOURCES and (self.name is not None or self.components):
            raise ValueError("A Google place candidate keeps only its place ID (G26).")
        return self


class SourceRef(Frozen):
    name: str
    record_id: str | None = None
    version: str | None = None
    retrieved_at: str | None = None
    license: str | None = None


class GeoreferenceCandidate(Frozen):
    """A point with its uncertainty from openly licensed sources (S8, G12,
    G35). The Google tool never fills one: its coordinates may not be stored
    (G26), so no georeference cites Google."""

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

    @model_validator(mode="after")
    def never_from_google(self) -> "GeoreferenceCandidate":
        if any(source.name in GOOGLE_SOURCES for source in self.sources):
            raise ValueError("Google's coordinates are never a georeference (G26).")
        return self


class Check(Frozen):
    name: str
    result: Literal["supports", "conflicts", "not_assessable"]
    detail: str | None = None


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


def with_retries(
    call: Callable[[int], SourceCall],
    *,
    attempts: int = 3,
    cap_seconds: float = 20,
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] | None = None,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> list[SourceCall]:
    """Run one provider request with bounded retries (HAR-009): a rate limit, a
    timeout or a provider error is retried with backoff and jitter, never
    sooner than the provider's Retry-After, at most `attempts` times in all,
    and never past `deadline` (on `clock`). Returns every attempt, the final
    one last, so each is recorded."""
    made = []
    for attempt in range(1, attempts + 1):
        made.append(call(attempt))
        last = made[-1]
        if last.outcome not in RETRYABLE or attempt == attempts:
            break
        if last.retry_after_seconds and last.retry_after_seconds > cap_seconds:
            break  # The provider asks for longer than a step may wait.
        wait = min(cap_seconds, retry_delay(attempt, last.retry_after_seconds, random_value))
        if deadline is not None and clock() + wait >= deadline:
            break  # No attempt fits before the tool's deadline.
        sleep(wait)
    return made
