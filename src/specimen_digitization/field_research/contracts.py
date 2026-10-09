"""What the parts of field research hand each other.

One expert resolver per field (owner, 2026-10-03; docs/execution/golive/FIELD_RESEARCH.md).
The organiser's field-value pairs and every reading of every label go in; one
outcome per field comes out. Nothing here touches storage.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from specimen_digitization.application.domain import Evidence, FieldValue, LookupStatus


PLACE_SOURCES = ("geolocate", "tgn", "wikidata", "nga")

# The approved sources and deterministic checks each field's expert may call.
# "gbif" is GBIF's decision with Catalogue of Life and Global Names Verifier
# alongside (application.taxonomy_tool.verify_taxon).
FIELD_TOOLS: Mapping[str, tuple[str, ...]] = {
    "taxon": ("gbif",),
    "country": PLACE_SOURCES,
    "province_state": PLACE_SOURCES,
    "county": PLACE_SOURCES,
    "city": PLACE_SOURCES,
    # Verbatim locality text: checked against places, never replaced (PRD 515).
    "precise_location": PLACE_SOURCES,
    "date_visited_from": ("date_parser",),
    "date_visited_to": ("date_parser",),
    "date_identified": ("date_parser",),
    "elevation_from_m": ("elevation_parser",),
    "elevation_to_m": ("elevation_parser",),
    "elevation_from_ft": ("elevation_parser",),
    "elevation_to_ft": ("elevation_parser",),
    "fmnh_ins_number": ("catalog_number_validator",),
    "collectors": (),
    "collection_code": (),
    "habitat": (),
    "collection_method": (),
    "verbatim_dts": (),
    # Needs a confirmed EMu parties IRN; no approved source can supply one yet,
    # and a name on the label is not an IRN (CONTRACTS.md). Never finalized
    # from the label.
    "identified_by_irn": (),
}

NO_APPROVED_AUTHORITY = frozenset({"identified_by_irn"})

# Owner decision A, 2026-10-09: "clearing as not on the label is fine". The
# fields of a collection profile that clear as "not on the label" when no
# reading states them and their expert found none (step.mark_not_on_label;
# FIELD_RESEARCH.md, "Fields the label does not state"). The list is the schema
# session's engineering reading of the decision (schema-harness-plan.md, H6
# item 5), which the owner may narrow. It lives here, keyed by the profile's id
# and version, and the rule reads it through the run's pinned profile: a Retry
# keeps the run's profile snapshot, so a key added to the published profile
# would never reach it. Another profile, or a new version of this one, gets its
# own entry.
NOT_ON_LABEL: Mapping[tuple[str, str], frozenset[str]] = {
    ("zoology_insects_slides", "1.0.0"): frozenset({
        "county", "city", "collection_code", "collection_method", "date_identified", "habitat",
        "elevation_from_m", "elevation_to_m", "elevation_from_ft", "elevation_to_ft", "precise_location",
    }),
}
# Never "not on the label", whatever a profile lists: their absence usually
# means a reading failed. The taxon follows owner decision B instead (a name
# with no genus clears as written, unmatched; step._unmatched_taxon).
NEVER_NOT_ON_LABEL = frozenset({
    "fmnh_ins_number", "country", "date_visited_from", "date_visited_to", "collectors", "taxon"})


def not_on_label_fields(profile_id: str, version: str) -> frozenset[str]:
    """The fields of this profile version that may clear as "not on the label"."""
    return NOT_ON_LABEL.get((profile_id, version), frozenset()) - NEVER_NOT_ON_LABEL


@dataclass(frozen=True)
class Reading:
    """One reader's text of one label, named as the organiser names it (1A, 1B, 2A)."""

    name: str
    region_id: str
    observation_id: str
    input_source: Literal["decided_transcript", "raw_reading"]
    text: str


@dataclass(frozen=True)
class Candidate:
    """One organiser candidate for a field: the reading it quotes, the quote, the literal."""

    reading: str
    quote: str
    literal: str
    evidence_id: str


@dataclass(frozen=True)
class FieldTask:
    """One field's work: the organiser's value after parse and what its expert may use."""

    key: str
    mandatory: bool
    current: FieldValue
    candidates: tuple[Candidate, ...]
    # Approved source ids and deterministic checks this field's expert may call.
    tools: tuple[str, ...]


@dataclass(frozen=True)
class PlaceRef:
    """A place a source puts a candidate in: the name the source gives it and,
    when the source names it by one of its own records, that record's
    authority_id, in the form the source's candidates carry ("tgn:1000135")."""

    name: str
    authority_id: str | None = None


@dataclass(frozen=True)
class SourceCandidate:
    """One match a source returned, in the source's own words."""

    name: str
    authority_id: str | None
    kind: str | None = None  # rank for a taxon, place type for a place
    detail: str | None = None  # short context: classification, parent places
    # A place's parent places as its source gives them, nearest first, its
    # country last (sources._place, sources._geolocate); () when the source
    # names none.
    parents: tuple[PlaceRef, ...] = ()


@dataclass(frozen=True)
class SourceAnswer:
    """One approved lookup as an expert sees it, with the evidence that stores it."""

    source_id: str
    query: str
    status: LookupStatus
    candidates: tuple[SourceCandidate, ...]
    # The stored response; None when nothing came back (a timeout, an outage).
    evidence: Evidence | None
    # One plain sentence, e.g. "GBIF: exact accepted match at species rank".
    note: str = ""
    # The GBIF lookup behind a taxon answer, for the run's taxonomy record
    # (application.lookup.Lookup); None for every other source.
    taxonomy_lookup: object | None = None


class SourceTools(Protocol):
    """The approved sources of one record. Repeated queries are answered from a cache."""

    sources: tuple[str, ...]

    async def lookup(self, source_id: str, query: str, *, field_key: str) -> SourceAnswer: ...


Outcome = Literal["resolved", "label_lacks_value", "sources_cannot_resolve", "several_possibilities"]


class FieldAnswer(BaseModel):
    """What one field expert returns. Every claim is checked before it is used."""

    model_config = ConfigDict(extra="forbid")

    outcome: Outcome
    # Exactly as the named readings write it.
    literal: str | None = None
    reading_names: list[str] = Field(default_factory=list)
    # The settled value when it differs from the literal: a source candidate's
    # name, or a deterministic parse of the literal.
    value: str | None = None
    authority_id: str | None = None
    # Ids of the source evidence that supports the value.
    source_evidence_ids: list[str] = Field(default_factory=list)
    # For several_possibilities: the values a person can choose from.
    options: list[str] = Field(default_factory=list)
    # One or two plain sentences for the reviewer.
    explanation: str


Failure = Literal["source_unavailable", "model_error", "timeout", "budget_exhausted", "input_too_large"]


@dataclass
class FieldOutcome:
    """One field's result. A failure means no answer could be produced; retry is safe."""

    key: str
    answer: FieldAnswer | None
    failure: Failure | None = None
    # Every source response captured for this field, in call order.
    evidence: list[Evidence] = field(default_factory=list)
    # GBIF lookups behind taxon answers (application.lookup.Lookup).
    lookups: list[object] = field(default_factory=list)
    finalized_without_model: bool = False
    cost_micros: int = 0
    model_calls: int = 0


class FieldResolver(Protocol):
    """Runs one field's expert. Never raises for a field-level problem: it returns a failure."""

    async def __call__(
        self,
        task: FieldTask,
        readings: Sequence[Reading],
        context: Mapping[str, FieldValue],
        *,
        tools: SourceTools,
    ) -> FieldOutcome: ...
