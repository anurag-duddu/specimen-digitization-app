"""Versioned research envelopes; legacy FieldValue remains the value truth."""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from specimen_digitization.application.domain import FieldValue, LookupStatus, ValueState

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


def digest(value: object) -> str:
    """Canonical pin digest, including exact decimal strings and ordered tuples."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


class FrozenRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FrozenFieldRevisions(dict):
    """JSON-compatible captured revision map with no mutable update surface."""

    def _immutable(self, *args, **kwargs):
        raise TypeError("Captured field revisions are immutable")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _immutable

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self


class FieldKey(StrEnum):
    FMNH_INS_NUMBER = "fmnh_ins_number"
    COLLECTION_CODE = "collection_code"
    COUNTRY = "country"
    PROVINCE_STATE = "province_state"
    COUNTY = "county"
    CITY = "city"
    PRECISE_LOCATION = "precise_location"
    ELEVATION_FROM_M = "elevation_from_m"
    ELEVATION_TO_M = "elevation_to_m"
    ELEVATION_FROM_FT = "elevation_from_ft"
    ELEVATION_TO_FT = "elevation_to_ft"
    HABITAT = "habitat"
    COLLECTION_METHOD = "collection_method"
    DATE_VISITED_FROM = "date_visited_from"
    DATE_VISITED_TO = "date_visited_to"
    COLLECTORS = "collectors"
    VERBATIM_DTS = "verbatim_dts"
    TAXON = "taxon"
    IDENTIFIED_BY_IRN = "identified_by_irn"
    DATE_IDENTIFIED = "date_identified"


class SpecialistRole(StrEnum):
    # Declaration order is run order (engine._batches walks it) and so is
    # publication order: only a terminal checkpoint publishes, and the whole-record
    # disposition is computed on the last publication. PARTIES runs last because its
    # identified_by_irn always ends terminal (the declared EMu exception), so the last
    # publication sees every other role's work. With COLLECTION last and no terminal
    # field in it, the record stays research_in_progress after the final publication.
    TAXONOMY = "specimen_taxonomy"
    GEOGRAPHY = "specimen_geography"
    TEMPORAL = "specimen_temporal"
    MEASUREMENT = "specimen_measurement"
    COLLECTION = "specimen_collection"
    PARTIES = "specimen_parties"


ROLE_FIELDS = {
    SpecialistRole.TAXONOMY: (FieldKey.TAXON,),
    SpecialistRole.GEOGRAPHY: (FieldKey.COUNTRY, FieldKey.PROVINCE_STATE, FieldKey.COUNTY,
                             FieldKey.CITY, FieldKey.PRECISE_LOCATION),
    SpecialistRole.TEMPORAL: (FieldKey.DATE_VISITED_FROM, FieldKey.DATE_VISITED_TO,
                            FieldKey.DATE_IDENTIFIED),
    SpecialistRole.MEASUREMENT: (FieldKey.ELEVATION_FROM_M, FieldKey.ELEVATION_TO_M,
                               FieldKey.ELEVATION_FROM_FT, FieldKey.ELEVATION_TO_FT),
    SpecialistRole.PARTIES: (FieldKey.COLLECTORS, FieldKey.IDENTIFIED_BY_IRN),
    SpecialistRole.COLLECTION: (FieldKey.FMNH_INS_NUMBER, FieldKey.COLLECTION_CODE,
                              FieldKey.HABITAT, FieldKey.COLLECTION_METHOD,
                              FieldKey.VERBATIM_DTS),
}
ALL_FIELDS = tuple(FieldKey)


class WorkState(StrEnum):
    PENDING = "pending"
    RESEARCHING = "researching"
    RESOLVED = "resolved"
    WAITING_SOURCE = "waiting_source"
    WAITING_POLICY = "waiting_policy"
    RETRY_SCHEDULED = "retry_scheduled"
    OPERATIONAL_FAILED = "operational_failed"
    WAITING_HUMAN = "waiting_human"
    NONBLOCKING_EXCEPTION = "nonblocking_exception"
    CANCELLED = "cancelled"


class ResearchScope(FrozenRecord):
    organization_id: str = Field(min_length=1)
    collection_id: str = Field(min_length=1)
    specimen_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    generation: int = Field(strict=True, ge=0)
    input_digest: Digest
    profile_digest: Digest
    sensitive: bool = Field(default=True, strict=True)


class DependencyPin(FrozenRecord):
    field_key: FieldKey
    revision: int = Field(strict=True, ge=0)
    digest: Digest


class PromptPin(FrozenRecord):
    role: SpecialistRole
    version: str
    text: str = Field(min_length=1)
    digest: Digest
    output_schema_digest: Digest
    profile_digest: Digest
    source_registry_digest: Digest
    toolset_digest: Digest
    model_route: str
    requested_label: str = "repository"
    served_label: str | None = "repository"
    fallback_reason: str | None = None

    @model_validator(mode="after")
    def exact_content(self):
        if hashlib.sha256(self.text.encode()).hexdigest() != self.digest:
            raise ValueError("Prompt content differs from pinned digest")
        return self


class SourceCoverageState(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    UNQUALIFIED = "unqualified"
    INACCESSIBLE = "inaccessible"
    SCHEMA_ONLY = "schema_only"
    FAILED = "failed"
    SEARCHED = "searched"
    EXHAUSTED = "exhausted"


class SourceCoverageReceipt(FrozenRecord):
    source_id: str
    field_key: FieldKey
    state: SourceCoverageState
    source_version: str
    qualification_digest: Digest | None = None
    exact_join_attempted: bool = False
    exact_join_proven: bool = False
    query_digest: Digest | None = None
    receipt_ids: tuple[str, ...] = ()
    candidate_count: int | None = Field(default=None, strict=True, ge=0)
    coverage_limit: str
    reason: str

    @model_validator(mode="after")
    def exhausted_is_scoped(self):
        if self.exact_join_proven and not self.exact_join_attempted:
            raise ValueError("Join proof requires an actual join attempt")
        if self.state == SourceCoverageState.EXHAUSTED and (
            not self.exact_join_attempted or not self.receipt_ids or self.query_digest is None
            or self.qualification_digest is None
        ):
            raise ValueError("Exhaustion requires qualified scoped search receipts")
        return self


class EvidenceItem(FrozenRecord):
    id: str
    kind: str
    source_id: str
    locator: str
    response_digest: Digest
    source_version: str
    publisher_assertion_id: str
    excerpt: str = ""
    event_id: str | None = None
    retrieved_at: str | None = None
    role: Literal["decides", "supports", "contradicts"] = "supports"


class Geometry(FrozenRecord):
    coordinate_frame: Literal["original_pixel_edges", "crop_pixel_edges"]
    bounds: tuple[int, int, int, int]
    kind: Literal["region", "measured_fragment"]
    provenance: str = Field(min_length=1)
    crop_transform_digest: Digest | None = None

    @model_validator(mode="after")
    def real_bounds(self):
        x, y, width, height = self.bounds
        if x < 0 or y < 0 or width <= 0 or height <= 0:
            raise ValueError("Geometry must be an available positive bounding box")
        return self


class SourceFragment(FrozenRecord):
    id: str
    scope: ResearchScope
    asset_id: str
    asset_generation: str
    asset_digest: Digest
    label_id: str
    region_id: str
    observation_id: str
    reader: str
    model_id: str
    prompt_digest: Digest
    observation_text: str
    observation_digest: Digest
    start: int = Field(strict=True, ge=0)
    end: int = Field(strict=True, ge=0)
    literal: str
    order: int = Field(strict=True, ge=0)
    granularity: Literal["line", "span", "label"] = "span"
    input_source: Literal["decided_transcript", "raw_reading"] = "raw_reading"
    geometry: Geometry | None = None
    unreadable: bool = False

    @model_validator(mode="after")
    def exact_span(self):
        if hashlib.sha256(self.observation_text.encode()).hexdigest() != self.observation_digest:
            raise ValueError("Immutable reading digest mismatch")
        if not self.start < self.end <= len(self.observation_text):
            raise ValueError("Fragment offsets exceed immutable reading")
        if self.literal != self.observation_text[self.start:self.end]:
            raise ValueError("Fragment must preserve exact reading substring")
        return self


class EventKind(StrEnum):
    COLLECTING = "collecting"
    DETERMINATION = "determination"
    PREPARATION = "preparation"
    UNKNOWN = "unknown"


class EventHypothesis(FrozenRecord):
    id: str
    scope: ResearchScope
    kind: EventKind
    fragment_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    reason: str = Field(min_length=1)
    competing_event_ids: tuple[str, ...] = ()
    rule_version: str = "event-v1"
    status: Literal["proposed", "accepted", "rejected"] = "proposed"
    validator_version: str | None = None

    @model_validator(mode="after")
    def accepted_event_evidence(self):
        if self.status == "accepted" and not self.validator_version:
            raise ValueError("Accepted event requires pinned semantic validation")
        return self


class RelationKind(StrEnum):
    CONTINUATION = "same_assertion_continuation"
    INDEPENDENT = "independent_assertions"
    DIFFERENT_EVENT = "different_events"
    UNKNOWN = "unknown"


class FragmentRelation(FrozenRecord):
    id: str
    scope: ResearchScope
    fragment_ids: tuple[str, ...] = Field(min_length=2)
    kind: RelationKind
    event_id: str | None = None
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    reason: str = Field(min_length=1)
    proposer_version: str
    validator_version: str | None = None
    status: Literal["proposed", "accepted", "rejected"] = "proposed"
    dependencies: tuple[DependencyPin, ...] = ()

    @model_validator(mode="after")
    def accepted_has_validator(self):
        if self.status == "accepted" and not self.validator_version:
            raise ValueError("Accepted relation requires pinned validation")
        return self


class FieldAssemblyCandidate(FrozenRecord):
    id: str
    scope: ResearchScope
    field_key: FieldKey
    event_id: str
    fragment_ids: tuple[str, ...] = Field(min_length=1)
    relation_ids: tuple[str, ...] = ()
    assertion_kind: Literal["complete", "complementary"]
    interpreted_text: str
    rule_version: str
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    competing_assembly_ids: tuple[str, ...] = ()


class DerivationRecord(FrozenRecord):
    rule_id: str
    rule_version: str
    operation: Literal["copy_endpoint", "multiply", "divide"]
    source_field: FieldKey
    source_revision: int = Field(strict=True, ge=0)
    source_digest: Digest
    source_value: str
    factor: str = "1"
    decimal_precision: int = Field(default=34, ge=1)
    rounding: str = "ROUND_HALF_EVEN"
    exact_operation: str
    unrounded_value: str
    display_value: str
    source_assembly_ids: tuple[str, ...]
    source_fragment_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class MeasurementMetadata(FrozenRecord):
    original_unit: Literal["ft", "m"]
    original_quantity: str
    original_to_quantity: str | None = None
    qualifiers: tuple[str, ...] = ()
    uncertainty: str | None = None
    precision: str = "unknown"
    vertical_datum: str = "unknown"
    decimal_context: int = 34
    rendering_rule: str = "decimal-2-half-even-v1"
    derived_unit: Literal["ft", "m"] | None = None
    converted_uncertainty: str | None = None
    assertion_metadata: tuple[str, ...] = ()


class PolicyException(FrozenRecord):
    field_key: FieldKey
    dependency: str
    policy_version: str
    reason: str
    reevaluate_when: str


def _geolocate_unresolved(item: SourceCoverageReceipt, field_key: FieldKey) -> bool:
    """A searched GEOLocate no_match or ambiguous outcome for a geography field.

    Coordinator engineering call of 2026-10-03, citing the owner's rule G6 that unresolved or
    unavailable data goes to the human queue with a reason: for this case only, "human questions
    need exhausted sources" is loosened. The outcome is scientific (GEOLocate answered and nothing
    agreed, or agreeing points lie far apart); outages stay FAILED, INACCESSIBLE or UNQUALIFIED and
    remain operational blocks. The receipt has no status field, so the adapter's reason leads with
    the typed status; evidence.py requires every claimed receipt to equal a real broker receipt.
    """
    return (item.state == SourceCoverageState.SEARCHED and item.source_id == "geolocate"
            and field_key in {FieldKey.COUNTRY, FieldKey.PROVINCE_STATE, FieldKey.COUNTY,
                              FieldKey.CITY, FieldKey.PRECISE_LOCATION}
            and re.fullmatch(r"(?:no_match|ambiguous): \S.*", item.reason, re.DOTALL) is not None)


class HumanQuestion(FrozenRecord):
    field_key: FieldKey
    question: str = Field(min_length=1)
    reason: Literal["evidence_conflict", "scoped_absence", "semantic_ambiguity"]
    coverage: tuple[SourceCoverageReceipt, ...] = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def no_operational_review(self):
        # Either every strategy is exhausted, or every claim is a GEOLocate scientific outcome; never mixed.
        if not (all(item.state == SourceCoverageState.EXHAUSTED for item in self.coverage)
                or all(_geolocate_unresolved(item, self.field_key) for item in self.coverage)):
            raise ValueError("Human review requires exhausted available permitted strategies")
        if any(item.field_key != self.field_key for item in self.coverage):
            raise ValueError("Human coverage belongs to the same requested field")
        return self


class FieldResolution(FrozenRecord):
    field_key: FieldKey
    work_state: WorkState
    value: FieldValue
    value_layer: Literal["verbatim", "settled", "derived"] = "verbatim"
    evidence_ids: tuple[str, ...] = ()
    assembly_ids: tuple[str, ...] = ()
    rejected_assembly_ids: tuple[str, ...] = ()
    event_id: str | None = None
    dependencies: tuple[DependencyPin, ...] = ()
    source_coverage: tuple[SourceCoverageReceipt, ...] = ()
    question: HumanQuestion | None = None
    exception: PolicyException | None = None
    derivation: DerivationRecord | None = None
    measurement: MeasurementMetadata | None = None
    reason: str

    @model_validator(mode="after")
    def valid_termination(self):
        if self.work_state == WorkState.RESOLVED and (
            self.value.state != ValueState.SUPPORTED or not self.evidence_ids
        ):
            raise ValueError("Resolved requires supported legacy value and evidence")
        if self.value_layer == "derived" and self.derivation is None:
            raise ValueError("Derived value requires a deterministic derivation record")
        if self.work_state == WorkState.NONBLOCKING_EXCEPTION and (
            self.exception is None or self.exception.field_key != self.field_key
            or self.value.state == ValueState.SUPPORTED
            or self.value.authority_id is not None or self.value.authority_identity is not None
            or self.value.parsed is not None or self.value.normalized is not None
        ):
            raise ValueError("Exception is explicit field-scoped unresolved scientific value")
        if self.work_state == WorkState.WAITING_HUMAN and (
            self.question is None or self.question.field_key != self.field_key
        ):
            raise ValueError("Human state requires a legitimate field-specific question")
        return self


# The most organiser candidates one request carries. The ordinary extractor returns at most
# 100 candidates (application/harness.py ExtractionOutput) and a request carries only its
# role's fields, so this is never reached by today's pairs; it bounds what a later organiser
# may add.
MAX_ORGANISER_CANDIDATES = 100
# The longest literal a candidate carries: the extractor's own bound (ExtractionCandidate).
MAX_ORGANISER_LITERAL = 2000


class OrganiserCandidate(FrozenRecord):
    """One proposal for a field's value, handed to a specialist next to the raw readings.

    A candidate is a proposal to verify, never evidence: the evidence is the reading text
    (``fragments``) and, for a grounded candidate, the accepted assembly built from it. The
    ``literal`` is what the proposer wrote (``source``: the ordinary extractor today). Where it
    sits in a reading (``observation_id``, ``region_id``, ``start``, ``end``) is computed by
    trusted code in initial_requests, never taken from the proposer, and ``SpecialistRequest``
    re-checks every span against the reading text it cites (a claimed span that is not a
    verbatim substring cannot be constructed).

    - ``grounded``: the literal is a verbatim substring of exactly one line of the decided
      reading and an accepted event and assembly (``event_id``, ``assembly_id``) carry it;
    - ``located``: the same span, but no assembly (``reason`` names why: the field has no
      literal assembly path, the reading has unreadable spans, ...);
    - ``ungrounded``: the literal could not be located exactly; a hint only. It has no span,
      no event and no assembly, and never becomes a value.
    """

    id: str
    field_key: FieldKey
    literal: str = Field(min_length=1, max_length=MAX_ORGANISER_LITERAL)
    source: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    status: Literal["grounded", "located", "ungrounded"]
    reason: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    region_id: str | None = None
    observation_id: str | None = None
    start: int | None = Field(default=None, strict=True, ge=0)
    end: int | None = Field(default=None, strict=True, ge=0)
    fragment_id: str | None = None
    event_id: str | None = None
    assembly_id: str | None = None
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def status_matches_fields(self):
        located = (self.region_id, self.observation_id, self.start, self.end)
        if self.status == "ungrounded":
            if (self.observation_id is not None or self.start is not None or self.end is not None
                or self.fragment_id is not None or self.event_id is not None or self.assembly_id is not None
                or self.evidence_ids):
                raise ValueError("An ungrounded candidate carries no span, event, assembly or evidence")
            return self
        if any(item is None for item in located) or not self.start < self.end:
            raise ValueError("A located candidate names its region, reading and span")
        if self.status == "located" and (self.fragment_id is not None or self.event_id is not None
                                         or self.assembly_id is not None):
            raise ValueError("A located candidate has no event or assembly")
        if self.status == "grounded" and (self.fragment_id is None or self.event_id is None
                                          or self.assembly_id is None or not self.evidence_ids):
            raise ValueError("A grounded candidate names its fragment, event, assembly and evidence")
        return self


class SpecialistRequest(FrozenRecord):
    scope: ResearchScope
    role: SpecialistRole
    field_keys: tuple[FieldKey, ...] = Field(min_length=1)
    prompt: PromptPin
    fragments: tuple[SourceFragment, ...] = ()
    relations: tuple[FragmentRelation, ...] = ()
    events: tuple[EventHypothesis, ...] = ()
    assemblies: tuple[FieldAssemblyCandidate, ...] = ()
    evidence: tuple[EvidenceItem, ...] = ()
    source_coverage: tuple[SourceCoverageReceipt, ...] = ()
    accepted_decisions: tuple[str, ...] = ()
    dependencies: tuple[DependencyPin, ...] = ()
    field_revisions: dict[FieldKey, Annotated[int, Field(strict=True, ge=0)]] = Field(default_factory=FrozenFieldRevisions)
    retry_command_id: Digest | None = None
    organiser_candidates: tuple[OrganiserCandidate, ...] = Field(default=(), max_length=MAX_ORGANISER_CANDIDATES)

    @field_validator("field_revisions", mode="after")
    @classmethod
    def immutable_field_revisions(cls, value):
        return FrozenFieldRevisions(value)

    @model_validator(mode="after")
    def scoped_role(self):
        if len(set(self.field_keys)) != len(self.field_keys) or not set(self.field_keys) <= set(ROLE_FIELDS[self.role]):
            raise ValueError("Specialist can propose only its requested owned fields")
        if not set(self.field_revisions) <= set(self.field_keys):
            raise ValueError("Captured field revisions must belong to requested owned fields")
        if self.retry_command_id is not None and (len(self.field_keys) != 1 or set(self.field_revisions) != set(self.field_keys)):
            raise ValueError("A retry command requires one field and its captured revision")
        if self.prompt.role != self.role or self.prompt.profile_digest != self.scope.profile_digest:
            raise ValueError("Prompt role/profile differs from durable request")
        for records in (self.fragments, self.relations, self.events, self.assemblies):
            if any(record.scope != self.scope for record in records):
                raise ValueError("Evidence graph cannot cross scoped specimens/generations")
        self._check_organiser_candidates()
        return self

    def _check_organiser_candidates(self) -> None:
        """A candidate's span is trusted only because it is re-read here from the reading text."""
        if len({item.id for item in self.organiser_candidates}) != len(self.organiser_candidates):
            raise ValueError("Organiser candidate identities must be unique")
        readings = {(item.observation_id, item.region_id): item for item in self.fragments}
        decided = {item.observation_id for item in self.fragments if item.input_source == "decided_transcript"}
        fragments = {item.id: item for item in self.fragments}
        assemblies = {item.id: item for item in self.assemblies}
        events = {item.id: item for item in self.events}
        for candidate in self.organiser_candidates:
            if candidate.field_key not in self.field_keys:
                raise ValueError("An organiser candidate belongs to a requested owned field")
            if candidate.status == "ungrounded":
                continue
            reading = readings.get((candidate.observation_id, candidate.region_id))
            if (reading is None or candidate.observation_id not in decided
                or reading.observation_text[candidate.start:candidate.end] != candidate.literal):
                raise ValueError("An organiser span must be a verbatim substring of the decided reading it cites")
            if candidate.status == "located":
                continue
            fragment, assembly = fragments.get(candidate.fragment_id), assemblies.get(candidate.assembly_id)
            event = events.get(candidate.event_id)
            if (fragment is None or assembly is None or event is None
                or (fragment.observation_id, fragment.region_id, fragment.start, fragment.end, fragment.literal)
                    != (candidate.observation_id, candidate.region_id, candidate.start, candidate.end, candidate.literal)
                or assembly.field_key != candidate.field_key or assembly.event_id != event.id
                or assembly.fragment_ids != (fragment.id,) or assembly.interpreted_text != candidate.literal
                or assembly.evidence_ids != candidate.evidence_ids or event.status != "accepted"
                or fragment.id not in event.fragment_ids):
                raise ValueError("A grounded organiser candidate names an accepted assembly of its own span")


class ToolReceipt(FrozenRecord):
    id: str
    scope: ResearchScope
    tool_id: str
    source_id: str
    field_keys: tuple[FieldKey, ...]
    effect_id: str
    attempt_ids: tuple[str, ...]
    request_digest: Digest
    binding_digest: Digest
    outcome: LookupStatus
    effect_status: Literal["reserved", "sending", "held_unknown", "completed"]
    evidence_ids: tuple[str, ...] = ()
    capture_locator: str | None = None
    response_digest: Digest | None = None
    reservation_micro_usd: int = Field(default=0, strict=True, ge=0)
    settled_micro_usd: int | None = Field(default=None, strict=True, ge=0)
    held_micro_usd: int = Field(default=0, strict=True, ge=0)
    native_run_id: str | None = None
    native_tool_call_id: str | None = None
    result_json: str | None = None
    result_digest: Digest | None = None

    @model_validator(mode="after")
    def bound_result(self):
        if self.result_json is not None and (
            len(self.result_json.encode()) > 32768
            or hashlib.sha256(self.result_json.encode()).hexdigest() != self.result_digest
        ):
            raise ValueError("Tool semantic result exceeds bounds or digest differs")
        return self


class ExactSpecimenJoin(FrozenRecord):
    dataset_id: str
    occurrence_id: str | None = None
    institution_code: str | None = None
    collection_code: str | None = None
    catalog_number: str | None = None

    @model_validator(mode="after")
    def exact_join_key(self):
        if not self.occurrence_id and not all((self.institution_code, self.collection_code, self.catalog_number)):
            raise ValueError("Exact join needs occurrence GUID or institution/collection/catalog")
        return self


class SourceQuery(FrozenRecord):
    source_id: str
    field_key: FieldKey
    query_text: str = Field(default="", max_length=500)
    join: ExactSpecimenJoin | None = None
    north_american: bool = False


class SourceResult(FrozenRecord):
    status: LookupStatus
    coverage: SourceCoverageReceipt
    evidence: tuple[EvidenceItem, ...] = ()
    candidate_json: tuple[str, ...] = ()
    receipt: ToolReceipt | None = None

    @model_validator(mode="after")
    def bounded_semantics(self):
        if sum(len(item.encode()) for item in self.candidate_json) > 32768:
            raise ValueError("Tool candidates exceed safe output cap")
        for item in self.candidate_json:
            if not isinstance(json.loads(item), dict):
                raise ValueError("Typed candidate must be a JSON object")
        return self


class EmuRecordIdentity(FrozenRecord):
    source_system: Literal["emu"] = "emu"
    connection: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    environment: str = Field(min_length=1)
    module: Literal["ecatalogue", "emultimedia", "eparties"]
    irn: int = Field(strict=True, gt=0)


class IdentifierObservation(FrozenRecord):
    id: str
    scope: ResearchScope
    acquisition: Literal["qr", "linear_barcode", "printed_text"]
    raw_payload: str
    payload_digest: Digest
    asset_id: str
    asset_digest: Digest
    decoder_version: str | None = None
    reading_id: str | None = None

    @model_validator(mode="after")
    def qualified_acquisition(self):
        if hashlib.sha256(self.raw_payload.encode()).hexdigest() != self.payload_digest:
            raise ValueError("Identifier payload digest mismatch")
        if self.acquisition != "printed_text" and self.decoder_version is None:
            raise ValueError("Actual symbol decode requires decoder provenance")
        if self.acquisition == "printed_text" and self.reading_id is None:
            raise ValueError("Printed text needs a reading, not a claimed QR decode")
        return self


class IdentityProof(FrozenRecord):
    identity: EmuRecordIdentity
    scope: ResearchScope
    relationship: Literal["specimen", "asset", "collector", "determiner"]
    identification_row_id: str | None = None
    receipt_id: str
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    qualified_schema_digest: Digest


class FieldProfile(FrozenRecord):
    field_key: FieldKey
    mandatory: bool = Field(default=True, strict=True)
    source_ids: tuple[str, ...] = ()
    exception: PolicyException | None = None
    missing_policy: str | None = None


class CollectionProfile(FrozenRecord):
    id: str
    version: str
    organization_id: str
    collection_id: str
    ancestry: tuple[str, ...]
    fields: tuple[FieldProfile, ...]
    knowledge_version: str
    engine: Literal["research_harness_v1"] = "research_harness_v1"

    @model_validator(mode="after")
    def twenty_fields(self):
        if len(self.fields) != len(ALL_FIELDS) or {item.field_key for item in self.fields} != set(ALL_FIELDS):
            raise ValueError("Insects profile retains exactly all twenty fields")
        if any(item.mandatory is not True for item in self.fields):
            raise ValueError("Approved Insects profile requires all twenty fields mandatory; IRN uses its visible exception")
        return self


class FieldCheckpoint(FrozenRecord):
    scope: ResearchScope
    field_key: FieldKey
    revision: int = Field(strict=True, ge=0)
    resolution: FieldResolution
    prompt_digest: Digest
    model_settings_digest: Digest
    source_registry_digest: Digest
    effect_receipt_ids: tuple[str, ...] = ()
    retry_command_id: Digest | None = None
    reused_from_scope_digest: Digest | None = None
    reused_from_checkpoint_digest: Digest | None = None
    trace_id: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")] | None = None

    @model_validator(mode="after")
    def explicit_reuse_link(self):
        if (self.reused_from_scope_digest is None) != (self.reused_from_checkpoint_digest is None):
            raise ValueError("Checkpoint reuse requires both original scope and checkpoint pins")
        if self.resolution.field_key != self.field_key:
            raise ValueError("Checkpoint and resolution fields differ")
        return self


class ResearchThreadView(FrozenRecord):
    scope: ResearchScope
    checkpoints: tuple[FieldCheckpoint, ...]
    receipt_ids: tuple[str, ...]
    trace_ids: tuple[str, ...] = ()
