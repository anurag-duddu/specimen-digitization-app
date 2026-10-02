"""Strict native canonical-binding/v1 identity and causal journal mapping."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from specimen_digitization.application.domain import MANDATORY, Principal

from .contracts import FieldKey, FrozenFieldRevisions, FrozenRecord, ResearchScope, digest
from .persistence import DurabilityScope, StaleWork

Identifier = Annotated[str, Field(strict=True, min_length=1, max_length=100)]
JobIdentifier = Annotated[str, Field(strict=True, min_length=1, max_length=256)]
Digest = Annotated[str, Field(strict=True, pattern=r"^[a-f0-9]{64}$")]
HoldReason = Literal["legacy_live_import_not_confirmed", "program_halted",
                     "job_paused", "unknown_effect", "budget_unavailable"]


class BindingUnavailable(RuntimeError):
    """Absent/ambiguous/stale/uninstalled mapping; no scientific absence claim."""


def native_uuid(value: str) -> str:
    if str(UUID(value)) != value:
        raise ValueError("Native UUID must use canonical source spelling")
    return value


def strict_durability_identity(value: Any) -> dict[str, Any]:
    """Exact persisted scope; bool/float/string generations never alias integers."""
    keys = {"organization_id", "collection_id", "specimen_id", "job_id", "generation"}
    if (type(value) is not dict or set(value) != keys
        or any(type(value[key]) is not str or not value[key] for key in keys - {"generation"})
        or type(value["generation"]) is not int or value["generation"] < 1):
        raise ValueError("Malformed exact durability identity")
    return dict(value)


class CanonicalVersionTuple(FrozenRecord):
    """Actual native version columns; historical sensitivity is not invented."""

    record_revision: int = Field(strict=True, ge=1)
    record_version_id: Identifier
    canonical_run_id: Identifier
    host_record_version_id: str = Field(strict=True, min_length=1, max_length=200)
    snapshot_sha256: Digest

    @field_validator("record_version_id", "canonical_run_id")
    @classmethod
    def uuid_version_fields(cls, value: str) -> str:
        return native_uuid(value)


class CanonicalIdentity(CanonicalVersionTuple):
    """Version tuple under authoritative native joins and fresh sensitivity."""

    organization_id: Identifier
    collection_id: Identifier
    specimen_id: Identifier
    sensitive: bool = Field(strict=True)

    @field_validator("organization_id", "collection_id", "specimen_id")
    @classmethod
    def uuid_scope_fields(cls, value: str) -> str:
        return native_uuid(value)

    def version_tuple(self) -> CanonicalVersionTuple:
        return CanonicalVersionTuple(
            record_revision=self.record_revision, record_version_id=self.record_version_id,
            canonical_run_id=self.canonical_run_id, host_record_version_id=self.host_record_version_id,
            snapshot_sha256=self.snapshot_sha256,
        )


class PublicationTransition(FrozenRecord):
    """Native immutable receipt, never a calculated revision/UUID relationship."""

    receipt_id: Identifier
    operation_digest: Digest
    publication_digest: Digest
    binding_id: Identifier
    job_key: Digest
    base_canonical: CanonicalVersionTuple
    current_canonical: CanonicalVersionTuple
    job_id: JobIdentifier
    generation: int = Field(strict=True, ge=1)
    input_digest: Digest
    profile_digest: Digest
    runtime_binding_digest: Digest

    @field_validator("receipt_id", "binding_id")
    @classmethod
    def uuid_receipt(cls, value: str) -> str:
        return native_uuid(value)


class ScopedReadBundle(FrozenRecord):
    """Real native scoped projection; no global ledger or synthetic document."""

    state_revision: int = Field(strict=True, ge=1)
    server_time: float = Field(strict=True, gt=0, allow_inf_nan=False)
    job_key: Digest
    job: dict[str, Any]
    effects: dict[str, Any]
    outbox: dict[str, Any]
    halted: bool = Field(strict=True)
    paused: bool = Field(strict=True)
    hold_reasons: tuple[HoldReason, ...]

    @field_validator("hold_reasons", mode="before")
    @classmethod
    def unique_native_holds(cls, value):
        if (not isinstance(value, (list, tuple)) or any(type(reason) is not str for reason in value)
            or len(value) != len(set(value))):
            raise ValueError("Native hold reasons require a unique typed list")
        return value


class CanonicalResearchBinding(FrozenRecord):
    binding_id: Identifier
    active: bool = Field(strict=True)
    registration_revision: int = Field(strict=True, ge=1)
    base_canonical: CanonicalVersionTuple
    current_canonical: CanonicalVersionTuple
    job_id: JobIdentifier  # Existing journal String; never inferred from canonical run.
    job_key: Digest
    generation: int = Field(strict=True, ge=1)
    input_digest: Digest
    profile_digest: Digest
    runtime_binding_digest: Digest
    canonical_profile_digest: Digest
    source_sha256: Digest
    semantic_mapping_digest: Digest
    semantic_mapping: dict[str, Any]
    policy_digest: Digest
    journal_budget_policy_digest: Digest
    journal_budget_policy_origin: Literal["verified_owner_registration_not_SQL_recomputed"]
    research_policy_origin: str = Field(strict=True, min_length=1, max_length=256)
    program_key: str = Field(strict=True, min_length=1, max_length=200)
    field_mapping: dict[FieldKey, str]
    human_locks: dict[str, bool]
    publication_transition: PublicationTransition | None
    job: dict[str, Any]
    read_bundle: ScopedReadBundle | None = None
    authoritative_canonical: CanonicalIdentity | None = Field(default=None, exclude=True)

    @field_validator("binding_id")
    @classmethod
    def uuid_binding(cls, value: str) -> str:
        return native_uuid(value)

    @field_validator("field_mapping")
    @classmethod
    def exact_field_mapping(cls, value):
        if set(value) != set(FieldKey) or set(value.values()) != set(MANDATORY):
            raise ValueError("Owner must explicitly map every exact20 field once")
        return FrozenFieldRevisions(value)

    @field_validator("human_locks", mode="before")
    @classmethod
    def exact_canonical_locks(cls, value):
        if (not isinstance(value, dict) or set(value) != set(MANDATORY)
            or any(type(locked) is not bool for locked in value.values())):
            raise ValueError("Native exact20 canonical locks require strict booleans")
        return FrozenFieldRevisions(value)

    @model_validator(mode="after")
    def causal_current(self):
        if self.base_canonical != self.current_canonical:
            if (self.base_canonical.canonical_run_id != self.current_canonical.canonical_run_id
                or self.current_canonical.record_revision != self.base_canonical.record_revision + 1
                or self.current_canonical.record_version_id == self.base_canonical.record_version_id):
                raise ValueError("Publication transition changes protected identity or original CAS")
            transition = self.publication_transition
            if transition is None or (
                transition.binding_id != self.binding_id or transition.job_key != self.job_key
                or transition.base_canonical != self.base_canonical
                or transition.current_canonical != self.current_canonical
                or transition.job_id != self.job_id or transition.generation != self.generation
                or transition.input_digest != self.input_digest
                or transition.profile_digest != self.profile_digest
                or transition.runtime_binding_digest != self.runtime_binding_digest
            ):
                raise ValueError("Current publication requires native causal receipt mapping")
        elif self.publication_transition is not None:
            raise ValueError("Equal initial basis must not claim publication transition")
        if self.read_bundle is not None:
            if (self.read_bundle.job != self.job or self.read_bundle.job_key != self.job_key
                or type(self.job.get("paused")) is not bool
                or self.read_bundle.paused is not self.job["paused"]):
                raise ValueError("Scoped bundle differs from coherent registered job")
            self.validate_scoped_rows()
        identity = self.durability_identity()
        if self.authoritative_canonical is not None and (
            self.authoritative_canonical.version_tuple() != self.current_canonical
            or any(identity[key] != getattr(self.authoritative_canonical, key)
                   for key in ("organization_id", "collection_id", "specimen_id"))
        ):
            raise ValueError("Native authoritative joins differ from registered current version")
        if (digest(self.semantic_mapping) != self.semantic_mapping_digest
            or self.semantic_mapping.get("field_mapping") != self.field_mapping
            or self.semantic_mapping.get("research_policy_origin") != self.research_policy_origin
            or self.semantic_mapping.get("journal_budget_policy_digest") != self.journal_budget_policy_digest):
            raise ValueError("Explicit owner semantic mapping or policy origin differs")
        return self

    @property
    def canonical(self) -> CanonicalIdentity:
        if self.authoritative_canonical is None:
            raise BindingUnavailable("canonical_binding_unavailable")
        return self.authoritative_canonical

    @property
    def research_locks(self) -> tuple[FieldKey, ...]:
        return tuple(key for key in FieldKey if self.human_locks[self.field_mapping[key]])

    def durability_identity(self) -> dict[str, str]:
        # These are actual scoped native job columns, never route/caller defaults.
        identity = self.job.get("identity")
        if (not isinstance(identity, dict)
            or set(identity) != {"organization_id", "collection_id", "specimen_id", "job_id"}
            or any(type(value) is not str for value in identity.values())
            or identity["job_id"] != self.job_id):
            raise ValueError("Malformed authoritative native job scope")
        for key in ("organization_id", "collection_id", "specimen_id"):
            native_uuid(identity[key])
        return dict(identity)

    def accepts_effect_scope(self, scope: dict, binding_digest: Any) -> bool:
        identity = self.durability_identity()
        try:
            scoped = strict_durability_identity(scope)
        except ValueError:
            return False
        if ({key: scoped[key] for key in identity} != identity
            or scoped["generation"] > self.generation):
            return False
        if scoped["generation"] == self.generation:
            return binding_digest == self.runtime_binding_digest
        history = self.job.get("history")
        if not isinstance(history, list):
            return False
        matches = []
        for prior in history:
            if not isinstance(prior, dict):
                return False
            try:
                prior_scope = strict_durability_identity(prior.get("scope"))
            except ValueError:
                return False
            if (prior_scope == scoped and type(prior.get("generation")) is int
                and prior["generation"] == scoped["generation"]
                and prior.get("binding_digest") == binding_digest
                and isinstance(prior.get("pins"), dict)
                and digest(prior["pins"]) == binding_digest):
                matches.append(prior)
        return len(matches) == 1

    def validate_scoped_rows(self) -> None:
        """Validate every row before copying/disclosing the scoped read bundle.

        Current commands may overlay their exact current field. Retained older
        commands are terminal history only, never queued/running work authority.
        """
        if self.read_bundle is None:
            return
        for effect in self.read_bundle.effects.values():
            if (not isinstance(effect, dict) or effect.get("job_key") != self.job_key
                or not self.accepts_effect_scope(effect.get("scope"), effect.get("binding_digest"))):
                raise ValueError("Foreign effect or unproved generation lineage in scoped native bundle")
        for event in self.read_bundle.outbox.values():
            if (not isinstance(event, dict) or event.get("kind") != "research_field_retry"
                or not isinstance(event.get("command"), dict) or type(event.get("delivered")) is not bool):
                raise ValueError("Malformed command in scoped native bundle")
            command = event["command"]
            if not self.accepts_effect_scope(command.get("scope"), command.get("binding_digest")):
                raise ValueError("Foreign command or unproved generation lineage in scoped native bundle")
            generation = command["scope"]["generation"]
            if (type(command.get("expected_generation")) is not int
                or command["expected_generation"] != generation
                or type(command.get("status")) is not str
                or command["status"] not in {"queued", "running", "completed", "blocked"}):
                raise ValueError("Malformed retry generation or status in scoped native bundle")
            if generation < self.generation and (
                command["status"] not in {"completed", "blocked"} or event["delivered"] is not True
            ):
                raise ValueError("Historical retry cannot authorize current-generation work")

    def durability_scope(self, principal: Principal) -> DurabilityScope:
        if (principal.scope.organization_id, principal.scope.collection_id) != (
            self.canonical.organization_id, self.canonical.collection_id,
        ) or not principal.user_id or not self.active:
            raise PermissionError("research_access_denied")
        return DurabilityScope(
            self.canonical.organization_id, self.canonical.collection_id,
            self.canonical.specimen_id, self.job_id, self.generation,
            principal.user_id, self.canonical.sensitive,
        )

    def research_scope(self) -> ResearchScope:
        return ResearchScope(**self.durability_identity(), generation=self.generation,
            input_digest=self.input_digest, profile_digest=self.profile_digest,
            sensitive=self.canonical.sensitive)

    def stable_snapshot(self) -> dict[str, Any]:
        # Native statement clock changes on every read; preserve it as evidence,
        # but compare all scientific/state/registration facts independently.
        value = self.model_dump(mode="json")
        value["authoritative_canonical"] = (None if self.authoritative_canonical is None
                                            else self.authoritative_canonical.model_dump(mode="json"))
        if value["read_bundle"] is not None:
            value["read_bundle"].pop("server_time")
        return value

    def same_snapshot(self, other) -> bool:
        return isinstance(other, CanonicalResearchBinding) and self.stable_snapshot() == other.stable_snapshot()

    def validate_job(self, job: dict, *, program_key: str) -> None:
        if (
            job != self.job or job.get("identity") != self.durability_identity()
            or digest(self.durability_identity()) != self.job_key
            or type(job.get("record_revision")) is not int
            or job["record_revision"] != self.base_canonical.record_revision
            or type(job.get("generation")) is not int or job["generation"] != self.generation
            or job.get("sensitive") is not self.canonical.sensitive
            or program_key != self.program_key
        ):
            raise StaleWork("research_state_changed")
        pins = job.get("pins")
        if not isinstance(pins, dict) or (
            pins.get("input_digest") != self.input_digest
            or digest(pins.get("profile")) != self.profile_digest
            or digest(pins) != self.runtime_binding_digest
            or job.get("binding_digest") != self.runtime_binding_digest
            or not isinstance(job.get("fields"), dict)
            or set(job["fields"]) != {str(key) for key in FieldKey}
        ):
            raise StaleWork("research_state_changed")
        # policy_digest is an owner research-policy pin, not budget_policy digest.
        # I1 cannot derive headroom/import authority from either digest.


class CanonicalBindingSnapshot(FrozenRecord):
    schema_version: Literal["canonical-binding/v1"] = "canonical-binding/v1"
    canonical: CanonicalIdentity | None
    active_registration_count: int = Field(strict=True, ge=0)
    registrations: tuple[CanonicalResearchBinding, ...] = Field(max_length=2)
    snapshot: dict[str, Any] | None
    projection: tuple[dict[str, Any], ...]

    @classmethod
    def from_native_response(cls, data: dict):
        if not isinstance(data, dict) or set(data) != {
            "organizationMember", "collectionMember", "specimen", "binding",
        }:
            raise BindingUnavailable("canonical_binding_unavailable")
        organization = data["organizationMember"]
        collection = data["collectionMember"]
        specimen = data["specimen"]
        if organization is not None and (
            not isinstance(organization, dict) or set(organization) != {"active"}
            or type(organization["active"]) is not bool
        ):
            raise BindingUnavailable("canonical_binding_unavailable")
        if collection is not None and (
            not isinstance(collection, dict) or set(collection) != {"active", "role", "canViewSensitive"}
            or type(collection["active"]) is not bool
            or type(collection["canViewSensitive"]) is not bool
            or type(collection["role"]) is not str
            or collection["role"] not in {"viewer", "operator", "reviewer", "manager", "admin"}
        ):
            raise BindingUnavailable("canonical_binding_unavailable")
        if organization is None or collection is None or not organization["active"] or not collection["active"]:
            raise PermissionError("research_access_denied")
        if (not isinstance(specimen, dict) or set(specimen) != {"sensitive"}
            or type(specimen["sensitive"]) is not bool):
            raise BindingUnavailable("canonical_binding_unavailable")
        if specimen["sensitive"] and not collection["canViewSensitive"]:
            raise PermissionError("research_access_denied")
        value = data["binding"]
        if not isinstance(value, dict) or set(value) != {
            "canonical", "active_registration_count", "registrations", "snapshot", "projection",
        }:
            raise BindingUnavailable("canonical_binding_unavailable")
        if (type(value["active_registration_count"]) is not int or value["active_registration_count"] < 0
            or not isinstance(value["registrations"], list)
            or not isinstance(value["projection"], list)
            or (value["canonical"] is not None and not isinstance(value["canonical"], dict))):
            raise BindingUnavailable("canonical_binding_unavailable")
        if any(not isinstance(row, dict) or "authoritative_canonical" in row
               for row in value["registrations"]):
            raise BindingUnavailable("canonical_binding_unavailable")
        snapshot = cls.model_validate({"schema_version": "canonical-binding/v1", **value})
        if snapshot.canonical is not None and snapshot.canonical.sensitive is not specimen["sensitive"]:
            raise BindingUnavailable("canonical_binding_unavailable")
        return snapshot

    def current(self, *, organization_id: str, collection_id: str,
                specimen_id: str) -> CanonicalResearchBinding:
        if self.canonical is None or self.active_registration_count != 1:
            raise BindingUnavailable("canonical_binding_unavailable")
        if (self.canonical.organization_id, self.canonical.collection_id,
            self.canonical.specimen_id) != (organization_id, collection_id, specimen_id):
            raise PermissionError("research_access_denied")
        if (not isinstance(self.snapshot, dict)
            or set(self.snapshot) != {"snapshot", "sha256", "revision", "contractVersion"}
            or self.snapshot["sha256"] != self.canonical.snapshot_sha256
            or type(self.snapshot["revision"]) is not int
            or self.snapshot["revision"] != self.canonical.record_revision
            or not isinstance(self.snapshot["contractVersion"], str)
            or not self.snapshot["contractVersion"]):
            raise BindingUnavailable("canonical_binding_unavailable")
        # Private native snapshot/projection remain private and are not a
        # competing writer or an invented set of scientific values.
        # Count all ACTIVE rows before comparison; never filter a mismatch away.
        for row in self.registrations:
            identity = row.durability_identity()
            if tuple(identity[key] for key in ("organization_id", "collection_id", "specimen_id")) != (
                self.canonical.organization_id, self.canonical.collection_id, self.canonical.specimen_id,
            ):
                raise PermissionError("research_access_denied")
        active = tuple(row for row in self.registrations if row.active)
        if len(self.registrations) != 1 or len(active) != 1 or active[0].current_canonical != self.canonical.version_tuple():
            raise BindingUnavailable("canonical_binding_unavailable")
        # Attach only the real typed native scope joins. Raw registrations cannot
        # supply this private binding, and caller coordinates never populate it.
        bound = CanonicalResearchBinding.model_validate({
            **active[0].model_dump(), "authoritative_canonical": self.canonical,
        })
        try:
            bound.validate_job(bound.job, program_key=bound.program_key)
        except StaleWork as exc:
            raise BindingUnavailable("canonical_binding_unavailable") from exc
        return bound
