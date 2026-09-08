"""Application-owned evidence contracts. No provider or database types escape here."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def uid() -> str:
    return str(uuid4())


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ValueState(StrEnum):
    SUPPORTED = "supported"
    UNKNOWN = "unknown"
    UNRESOLVED = "unresolved"
    UNREADABLE = "unreadable"
    AMBIGUOUS = "ambiguous"
    NOT_PRESENT = "not_present"
    NOT_APPLICABLE = "not_applicable"


class Disposition(StrEnum):
    CLEARED = "cleared"
    REVIEW = "needs_human_review"
    DEFERRED = "deferred"


class LookupStatus(StrEnum):
    SUCCESS = "success"
    NO_MATCH = "no_match"
    AMBIGUOUS = "ambiguous"
    EMPTY = "empty_response"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    AUTHENTICATION = "authentication_error"
    AUTHORIZATION = "authorization_error"
    PROVIDER = "provider_error"
    MALFORMED = "malformed_response"
    POLICY = "policy_blocked"


OPERATIONAL = frozenset(
    {
        LookupStatus.RATE_LIMITED,
        LookupStatus.TIMEOUT,
        LookupStatus.AUTHENTICATION,
        LookupStatus.AUTHORIZATION,
        LookupStatus.PROVIDER,
        LookupStatus.MALFORMED,
        LookupStatus.POLICY,
    }
)
MANDATORY = (
    "fmnh_ins_number",
    "collection_code",
    "country",
    "province_state",
    "county",
    "city",
    "precise_location",
    "elevation_from_m",
    "elevation_to_m",
    "elevation_from_ft",
    "elevation_to_ft",
    "habitat",
    "collection_method",
    "date_visited_from",
    "date_visited_to",
    "collectors",
    "verbatim_dts",
    "taxon",
    "identified_by_irn",
    "date_identified",
)


class Scope(Record):
    organization_id: str = Field(min_length=1, max_length=100)
    collection_id: str = Field(min_length=1, max_length=100)


class Principal(Record):
    user_id: str
    scope: Scope
    role: str


class Asset(Record):
    id: str = Field(default_factory=uid)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    blob_ref: str
    media_type: str
    size_bytes: int = Field(gt=0, le=25000000)
    width: int = Field(gt=0, le=20000)
    height: int = Field(gt=0, le=20000)
    filename: str = Field(min_length=1, max_length=255)
    uploader: str
    created_at: str = Field(default_factory=now)


class Region(Record):
    id: str = Field(default_factory=uid)
    asset_id: str
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    order: int = Field(ge=0)
    method: str
    version: str
    crop_ref: str | None = None
    mask_ref: str | None = None


class Observation(Record):
    id: str = Field(default_factory=uid)
    region_id: str
    route_id: str
    model_id: str
    provider: str
    prompt_version: str
    input_sha256: str
    literal_text: str
    unreadable_spans: list[str] = Field(default_factory=list)
    raw_ref: str
    raw_sha256: str
    created_at: str = Field(default_factory=now)
    input_tokens: int = 0
    output_tokens: int = 0


class Transcript(Record):
    value_state: ValueState | None = None
    region_id: str
    text: str | None = None
    observation_ids: list[str]
    alternatives: list[str]
    resolved: bool
    actor: str | None = None
    reason: str | None = None
    disagreement_ratio: float = 0


class Evidence(Record):
    id: str = Field(default_factory=uid)
    kind: str
    asset_id: str | None = None
    region_id: str | None = None
    observation_ids: list[str] = Field(default_factory=list)
    source: str
    locator: str
    excerpt: str
    raw_ref: str | None = None
    digest: str | None = None
    created_at: str = Field(default_factory=now)


class FieldValue(Record):
    state: ValueState = ValueState.UNKNOWN
    literal: str | None = None
    parsed: str | None = None
    normalized: str | None = None
    authority_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str = "No supported source value"


class Lookup(Record):
    id: str = Field(default_factory=uid)
    provider: str
    adapter_version: str
    query: dict[str, str]
    status: LookupStatus
    candidates: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    raw_ref: str | None = None
    digest: str | None = None
    retrieved_at: str = Field(default_factory=now)
    retry_after_seconds: int | None = None


class Profile(Record):
    id: str = "zoology_insects"
    version: str = "0.1.0-draft"
    schema_version: str = "insects-v1"
    policy_version: str = "insects-clearance-v1"
    mandatory_fields: tuple[str, ...] = MANDATORY
    routes: tuple[str, str] = ("handwriting-qwen", "handwriting-muse")
    synthetic: bool = False
    institutional_policy_approved: bool = False
    semantics_confirmed: bool = False


class Run(Record):
    id: str = Field(default_factory=uid)
    profile: Profile = Field(default_factory=Profile)
    stage: str = "ingested"
    completed_steps: list[str] = Field(default_factory=list)
    regions: list[Region] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    transcripts: list[Transcript] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    fields: dict[str, FieldValue] = Field(
        default_factory=lambda: {k: FieldValue() for k in MANDATORY}
    )
    lookups: list[Lookup] = Field(default_factory=list)
    coverage_confirmed: bool = False
    human_approved: bool = False
    disposition: Disposition | None = None
    reasons: list[str] = Field(default_factory=list)
    blocker: str | None = None
    attempts: dict[str, int] = Field(default_factory=dict)
    capability_reason: str | None = None
    retry_eligibility: str | None = None
    next_retry_at: str | None = None
    dead_letter: bool = False
    lease_until: str | None = None
    created_at: str = Field(default_factory=now)


class AuditEvent(Record):
    id: str = Field(default_factory=uid)
    actor: str
    action: str
    reason: str
    before: dict = Field(default_factory=dict)
    after: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=now)


class Specimen(Record):
    id: str = Field(default_factory=uid)
    scope: Scope
    asset: Asset
    version: int = 1
    batch_id: str | None = None
    run: Run
    previous_runs: list[Run] = Field(default_factory=list)
    audit: list[AuditEvent] = Field(default_factory=list)
    created_at: str = Field(default_factory=now)
