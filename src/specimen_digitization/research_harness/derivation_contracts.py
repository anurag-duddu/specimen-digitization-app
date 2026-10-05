"""G38 request, saved command and proposal reads; these shapes confer no source authority.

Only the request comes from the client. The API constructs input proofs from
genuine saved review decisions; the worker rechecks their scope and revisions
before producing durable proposals. Neither a command nor a proposal settles a
canonical field without the ordinary reviewer decision.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .contracts import Digest, FieldKey, FrozenRecord, digest

DERIVATION_RULE_VERSION = "retrospective-georeferencing-v1"

GEOGRAPHY_FIELDS = frozenset({FieldKey.COUNTRY, FieldKey.PROVINCE_STATE, FieldKey.COUNTY,
                            FieldKey.CITY, FieldKey.PRECISE_LOCATION})
DERIVABLE_FIELDS = GEOGRAPHY_FIELDS | frozenset({FieldKey.ELEVATION_FROM_M, FieldKey.ELEVATION_TO_M,
                                               FieldKey.ELEVATION_FROM_FT, FieldKey.ELEVATION_TO_FT})
Identifier = Annotated[str, Field(min_length=1, max_length=200)]
EvidenceIdentifier = Annotated[str, Field(min_length=1, max_length=240)]
ReasonCode = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")]
DerivationStatus = Literal["queued", "running", "completed", "blocked"]
Revision = Annotated[int, Field(strict=True, ge=1)]


def _distinct(values):
    if len(set(values)) != len(values):
        raise ValueError("Derivation fields must be distinct")
    return values


def _targets(values):
    if not set(values) <= DERIVABLE_FIELDS:
        raise ValueError("Derivation targets must be geography or elevation fields")
    return _distinct(values)


class DerivationRequest(FrozenRecord):
    expected_record_revision: Revision
    base_record_version_id: Identifier
    reason: str = Field(min_length=1, max_length=1000)
    requested_fields: tuple[FieldKey, ...] = Field(min_length=1, max_length=9)

    _allowed_targets = field_validator("requested_fields")(_targets)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value):
        if not value.strip():
            raise ValueError("A review reason is required")
        return value


class SettledDerivationInput(FrozenRecord):
    field_key: FieldKey
    value: str = Field(min_length=1)
    evidence_ids: tuple[EvidenceIdentifier, ...] = Field(min_length=1)
    revision: Revision
    authority_id: str = Field(min_length=1)
    field_digest: Digest
    review_decision_id: str = Field(min_length=1, max_length=100)
    provenance_blob_ref: str = Field(min_length=1, max_length=2048)
    provenance_sha256: Digest
    selection_id: Digest | None = None
    original_review_revision: Revision

    @field_validator("field_key")
    @classmethod
    def geography_input(cls, value):
        if value not in GEOGRAPHY_FIELDS:
            raise ValueError("Settled derivation inputs must be geography fields")
        return value

    @field_validator("value", "authority_id", "review_decision_id", "provenance_blob_ref")
    @classmethod
    def nonempty_provenance(cls, value):
        if not value.strip():
            raise ValueError("A settled input requires its value and genuine provenance")
        return value


def derivation_input_digest(inputs) -> str:
    """Hash the complete ordered typed inputs, including each saved human proof."""
    return digest([SettledDerivationInput.model_validate(item).model_dump(mode="json") for item in inputs])


class _QueuedRevision(FrozenRecord):
    source_revision: Revision
    queued_revision: Revision

    @model_validator(mode="after")
    def one_saved_revision(self):
        if self.queued_revision != self.source_revision + 1:
            raise ValueError("A derivation request is queued by one canonical save")
        return self


class DerivationCommand(_QueuedRevision):
    contract_version: Literal["research-derivation-command/v1"] = "research-derivation-command/v1"
    id: Digest
    status: DerivationStatus = "queued"
    actor_uid: Identifier
    reason: str = Field(min_length=1, max_length=1000)
    canonical_run_id: Identifier
    source_snapshot_sha256: Digest
    input_digest: Digest
    inputs: tuple[SettledDerivationInput, ...] = Field(min_length=1, max_length=5)
    human_locked_fields: tuple[FieldKey, ...] = Field(max_length=20)
    requested_fields: tuple[FieldKey, ...] = Field(min_length=1, max_length=9)
    idempotency_key: Identifier
    request_digest: Digest
    blocked_reason: ReasonCode | None = None

    _allowed_targets = field_validator("requested_fields")(_targets)
    _unique_locks = field_validator("human_locked_fields")(_distinct)

    @model_validator(mode="after")
    def exact_inputs(self):
        keys = tuple(item.field_key for item in self.inputs)
        _distinct(keys)
        if self.input_digest != derivation_input_digest(self.inputs):
            raise ValueError("Derivation input digest must match the saved proofs")
        if any(item.revision != self.source_revision for item in self.inputs):
            raise ValueError("Derivation inputs must belong to the exact source revision")
        if not set(keys) <= set(self.human_locked_fields):
            raise ValueError("Derivation inputs must remain human-locked")
        if set(self.requested_fields) & (set(keys) | set(self.human_locked_fields)):
            raise ValueError("Derivation cannot target settled inputs or human-locked fields")
        if any(item.original_review_revision > self.source_revision for item in self.inputs):
            raise ValueError("A derivation cannot cite a future review")
        if not self.reason.strip():
            raise ValueError("A review reason is required")
        return self


class DerivationAccepted(_QueuedRevision):
    contract_version: Literal["research-derivation-accepted/v1"] = "research-derivation-accepted/v1"
    request_id: Digest
    status: Literal["queued"] = "queued"
    canonical_run_id: Identifier


class DerivationScheduleReceipt(FrozenRecord):
    contract_version: Literal["research-derivation-schedule/v1"] = "research-derivation-schedule/v1"
    request_id: Digest
    queued_revision: Revision
    canonical_run_id: Identifier
    status: Literal["scheduled"] = "scheduled"


class DerivationCapability(FrozenRecord):
    contract_version: Literal["research-derivation-capability/v1"] = "research-derivation-capability/v1"
    available: bool = Field(strict=True)
    blocked_reason: ReasonCode | None = None
    canonical_revision: Revision
    eligible_fields: tuple[FieldKey, ...] = Field(default=(), max_length=9)

    _allowed_targets = field_validator("eligible_fields")(_targets)


class DerivationProposal(FrozenRecord):
    field_key: FieldKey
    value: str = Field(min_length=1)
    input_fields: tuple[FieldKey, ...] = Field(min_length=1, max_length=5)
    input_revisions: tuple[tuple[FieldKey, Revision], ...] = Field(min_length=1, max_length=5)
    evidence_ids: tuple[EvidenceIdentifier, ...] = Field(min_length=1)
    authority_id: str = Field(min_length=1)
    dataset_ids: tuple[Identifier, ...] = Field(min_length=1)
    tool_call_id: Identifier
    value_layer: Literal["derived"] = "derived"
    rule_version: Identifier
    checkpoint_id: Digest
    checkpoint_revision: Revision
    effect_id: Digest
    selection_id: Digest | None = None
    source_id: Literal["georeference_spatial"] = "georeference_spatial"

    @model_validator(mode="after")
    def field_dependencies(self):
        _targets((self.field_key,))
        _distinct(self.input_fields)
        revision_keys = tuple(key for key, _ in self.input_revisions)
        _distinct(revision_keys)
        if (not set(self.input_fields) <= GEOGRAPHY_FIELDS or set(revision_keys) != set(self.input_fields)
                or self.field_key in self.input_fields):
            raise ValueError("A derived proposal must name the exact distinct source field revisions")
        return self


class DerivationResultRead(_QueuedRevision):
    contract_version: Literal["research-derivation-result/v1"] = "research-derivation-result/v1"
    request_id: Digest
    status: DerivationStatus
    canonical_revision: Revision
    stale: bool = Field(strict=True)
    proposals: tuple[DerivationProposal, ...] = Field(default=(), max_length=9)
    blocked_reason: ReasonCode | None = None

    @model_validator(mode="after")
    def distinct_proposals(self):
        _distinct(tuple(item.field_key for item in self.proposals))
        return self
