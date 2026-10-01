"""Distinct I2 native writer source. No generic save or paid-work fallback.

The connector operations are concrete sources, not compiled/installed claims.
The service factory must supply I4's reviewed canonical policy materializer.
Missing policy or legacy-import authority fails closed. The original mutable
publication wrapper is deliberately not this writer's receipt-first entrypoint.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from specimen_digitization.application.active_graph import pack
from specimen_digitization.application.domain import AuditEvent, Evidence, FieldValue, MANDATORY, Principal, Specimen, ToolCallRecord, ValueState
from specimen_digitization.application.lane import run_status
from specimen_digitization.application.production import actor_uid
from specimen_digitization.application import projection as canonical_projection
from specimen_digitization.application.projection import derived_id, writes
from specimen_digitization.application.worker_deadline import deadline_call, guarded
from specimen_digitization.application.storage import check_snapshot, digest as canonical_digest

from .compatibility import PublicationUnavailable, PublishedResearch
from .contracts import ALL_FIELDS, Digest, FieldCheckpoint, EvidenceItem as ResearchEvidenceItem, FrozenRecord, ResearchScope, SourceResult, SpecialistRequest, digest
from .publication import NativeCanonicalResearchAdapter, NativeCapture, NativeReceiptBinding, PreparedNativePublication, validate_native_publication
from .persistence import BlobRef

OPERATION = "research-publication/v1"
Positive = Annotated[int, Field(strict=True, ge=1)]
CANONICAL_KEYS = frozenset(MANDATORY)
RESEARCH_KEYS = frozenset(str(key) for key in ALL_FIELDS)


def exact_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def fail(code: str = "native_canonical_binding_unavailable"):
    raise PublicationUnavailable(code)



CANONICAL_PROJECTOR_SHA256 = "619c041edacfba1ed7144980d1a6bf3e257e728ec7e7dc735df0412acf5c5635"
ACCESS_DENIED = "native_canonical_access_denied"


@dataclass(frozen=True)
class CanonicalProjectionServicesV1:
    """Exact PR168 projector plus service-owned immutable blob lookup origins."""
    projector: object
    locate: object
    size: object
    projector_sha256: str

    def verify(self):
        if self.projector is not canonical_projection.writes or self.projector_sha256 != CANONICAL_PROJECTOR_SHA256:
            fail("canonical_projector_source_not_qualified")
        if hashlib.sha256(Path(canonical_projection.__file__).read_bytes()).hexdigest()!=CANONICAL_PROJECTOR_SHA256:
            fail("canonical_projector_source_not_qualified")
        from sys import modules
        expected = {
            "specimen_digitization.application.domain":"688b93cd47a8a7df577734c67bbb17f434dc492fc29e269c873d46901aa5c67f",
            "specimen_digitization.application.storage":"3c9511b52160da2ae7b529b5262431f3b5a76b8fb228f98e34689a833f41be88",
            "specimen_digitization.application.active_graph":"9f22032c3443a564f034d92fc41eda616bbee6f36de6002653bd14aacc892d47",
        }
        for name,source_sha in expected.items():
            loaded=modules.get(name)
            if loaded is None or hashlib.sha256(Path(loaded.__file__).read_bytes()).hexdigest()!=source_sha:
                fail("canonical_dependency_source_not_qualified")
        return self

    @classmethod
    def from_repository(cls, repository):
        source_path = Path(canonical_projection.__file__)
        source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if source_sha != CANONICAL_PROJECTOR_SHA256:
            fail("canonical_projector_source_not_qualified")
        return cls(canonical_projection.writes,repository.locate,repository._sized,source_sha).verify()


class SqlConnectNativeOperationClient:
    """Reuse the existing repository's authenticated session/endpoint/deadline.

    Preserve typed401/403 and explicit returned inactive membership/sensitivity.
    Unknown HTTP200 GraphQL errors are unavailable, never error-text inferred403.
    Actual generated error envelopes are UNRUN.
    """
    def __init__(self, repository):
        self.repository = repository

    @guarded
    def execute(self, operation, variables, mutation=False):
        response = deadline_call(self.repository.session.post,
            self.repository.url + (":impersonateMutation" if mutation else ":impersonateQuery"),
            json={"operationName":operation,"variables":variables},timeout=30)
        if response.status_code in {401,403}:
            raise PermissionError(ACCESS_DENIED)
        if response.status_code != 200:
            fail("native_canonical_connector_unavailable")
        body = deadline_call(response.json)
        if not isinstance(body,dict):
            fail("native_canonical_connector_response_invalid")
        errors = body.get("errors") or []
        if errors:
            fail("native_canonical_transaction_rejected")
        if not isinstance(body.get("data"),dict):
            fail("native_canonical_connector_response_invalid")
        data = body["data"]
        if operation in {"GetCanonicalResearchBindingV1","GetResearchPublicationReceiptV1","GetResearchPublicationIntentV1"}:
            self._access_data(data,operation)
        return data

    @staticmethod
    def _access_data(data,operation):
        payload = {"GetCanonicalResearchBindingV1":"binding","GetResearchPublicationReceiptV1":"retained","GetResearchPublicationIntentV1":"intent"}[operation]
        if set(data)!={"organizationMember","collectionMember","specimen",payload}:
            fail("native_canonical_connector_envelope_invalid")
        org,collection,specimen = (data[k] for k in ("organizationMember","collectionMember","specimen"))
        if org is None or collection is None:
            raise PermissionError(ACCESS_DENIED)
        if (not isinstance(org,dict) or set(org)!={"active"} or type(org["active"]) is not bool
            or not isinstance(collection,dict) or set(collection)!={"active","role","canViewSensitive"}
            or type(collection["active"]) is not bool or type(collection["canViewSensitive"]) is not bool
            or not isinstance(collection["role"],str)):
            fail("native_canonical_connector_access_metadata_invalid")
        if not org["active"] or not collection["active"]:
            raise PermissionError(ACCESS_DENIED)
        if specimen is None:
            fail("native_canonical_specimen_unavailable")
        if not isinstance(specimen,dict) or set(specimen)!={"sensitive"} or type(specimen["sensitive"]) is not bool:
            fail("native_canonical_connector_access_metadata_invalid")
        if specimen["sensitive"] and not collection["canViewSensitive"]:
            raise PermissionError(ACCESS_DENIED)
        if operation == "GetResearchPublicationReceiptV1":
            retained=data["retained"]
            publication=retained.get("publication") if isinstance(retained,dict) else None
            if isinstance(publication,dict) and publication.get("sensitive") is True and not collection["canViewSensitive"]:
                raise PermissionError(ACCESS_DENIED)


class CapturedCanonicalEvidenceV1(FrozenRecord):
    """Trusted provider input, never guessed evidence from an ID or locator.

    Existing evidence must be byte-equal to the authoritative canonical graph.
    New source evidence must occur in a verified immutable SourceResult capture,
    carry the actual body object/digest and one typed producer. Provider copies
    genuine source bytes to the canonical blob namespace before materialization.
    """
    origin: Literal["existing_canonical","captured_source_result"]
    evidence: ResearchEvidenceItem
    canonical_evidence: Evidence
    canonical_producer: ToolCallRecord | None
    receipt: NativeReceiptBinding | None
    source_policy_digest: Digest
    source_registry_digest: Digest
    canonical_mapping_digest: Digest
    body: dict | None = None
    canonical_body_digest: Digest | None = None
    original_specialist_request: SpecialistRequest | None = None
    source_result: SourceResult | None = None
    capture_envelope_digest: Digest | None = None
    raw_capture: NativeCapture | None = None
    canonical_run_id: UUID
    canonical_region_id: str | None = None
    canonical_observation_ids: tuple[UUID,...] = ()


class CanonicalIdentityV1(FrozenRecord):
    record_revision: Positive
    record_version_id: UUID
    canonical_run_id: UUID
    host_record_version_id: str = Field(min_length=1, max_length=512)
    snapshot_sha256: Digest


class PublicationTransitionV1(FrozenRecord):
    receipt_id: UUID
    operation_digest: Digest
    publication_digest: Digest
    binding_id: UUID
    job_id: str = Field(min_length=1, max_length=256)
    job_key: Digest
    generation: Positive
    input_digest: Digest
    profile_digest: Digest
    runtime_binding_digest: Digest
    base_canonical: CanonicalIdentityV1
    current_canonical: CanonicalIdentityV1

    @model_validator(mode="after")
    def strict_transition(self):
        if (self.current_canonical.record_revision != self.base_canonical.record_revision + 1
            or self.current_canonical.canonical_run_id != self.base_canonical.canonical_run_id):
            fail("native_canonical_transition_invalid")
        return self


class CanonicalRegistrationV1(FrozenRecord):
    binding_id: UUID
    registration_revision: Positive = 1
    active: bool = Field(strict=True)
    base_canonical: CanonicalIdentityV1
    current_canonical: CanonicalIdentityV1
    publication_transition: PublicationTransitionV1 | None
    job_id: str = Field(min_length=1, max_length=256)
    job_key: Digest
    generation: Positive
    input_digest: Digest
    profile_digest: Digest
    runtime_binding_digest: Digest
    canonical_profile_digest: Digest
    source_sha256: Digest
    semantic_mapping_digest: Digest
    policy_digest: Digest
    program_key: str = Field(min_length=1, max_length=256)
    field_mapping: dict[str, str]
    semantic_mapping: dict
    human_locks: dict[str, bool]
    job: dict
    research_policy_origin: str = Field(min_length=1)
    journal_budget_policy_digest: Digest
    journal_budget_policy_origin: Literal["verified_owner_registration_not_SQL_recomputed"]
    read_bundle: dict

    @model_validator(mode="after")
    def exact_mapping(self):
        if (set(self.field_mapping) != RESEARCH_KEYS or set(self.field_mapping.values()) != CANONICAL_KEYS
            or len(self.field_mapping) != 20 or len(set(self.field_mapping.values())) != 20
            or self.semantic_mapping.get("field_mapping") != self.field_mapping
            or digest(self.semantic_mapping) != self.semantic_mapping_digest
            or self.semantic_mapping.get("research_policy_origin") != self.research_policy_origin
            or self.semantic_mapping.get("journal_budget_policy_digest") != self.journal_budget_policy_digest
            or set(self.human_locks) != CANONICAL_KEYS
            or any(type(v) is not bool for v in self.human_locks.values())):
            fail("native_canonical_mapping_invalid")
        return self


class CanonicalBindingV1(FrozenRecord):
    contract_version: Literal["canonical-binding/v1"] = "canonical-binding/v1"
    organization_id: UUID
    collection_id: UUID
    specimen_id: UUID
    canonical: CanonicalIdentityV1
    sensitive: bool = Field(strict=True)
    registration: CanonicalRegistrationV1

    @classmethod
    def from_native(cls, scope, specimen_id, row):
        if not isinstance(row, dict) or set(row) != {"canonical", "registrations", "snapshot", "projection", "active_registration_count"}:
            fail()
        canonical = row["canonical"]
        if not isinstance(canonical, dict) or set(canonical) != {
            "organization_id", "collection_id", "specimen_id", "record_revision", "record_version_id",
            "canonical_run_id", "host_record_version_id", "snapshot_sha256", "sensitive"
        }:
            fail()
        registrations = row["registrations"]
        if not isinstance(registrations, list) or len(registrations) != 1 or type(row["active_registration_count"]) is not int or row["active_registration_count"] != 1:
            fail("native_canonical_registration_missing_or_ambiguous")
        registration = CanonicalRegistrationV1.model_validate(registrations[0])
        result = cls(organization_id=canonical["organization_id"], collection_id=canonical["collection_id"],
            specimen_id=canonical["specimen_id"], sensitive=canonical["sensitive"],
            canonical={k:v for k,v in canonical.items() if k not in {"organization_id", "collection_id", "specimen_id", "sensitive"}},
            registration=registration)
        if (str(result.organization_id) != scope.organization_id or str(result.collection_id) != scope.collection_id
            or str(result.specimen_id) != str(UUID(specimen_id)) or not registration.active
            or result.canonical != registration.current_canonical):
            fail("native_canonical_registration_stale")
        job = registration.job
        identity = {"organization_id": scope.organization_id, "collection_id": scope.collection_id,
                    "specimen_id": str(result.specimen_id), "job_id": registration.job_id}
        if (job.get("identity") != identity or type(job.get("record_revision")) is not int
            or job["record_revision"] != registration.base_canonical.record_revision
            or type(job.get("generation")) is not int or job["generation"] != registration.generation
            or job.get("sensitive") is not result.sensitive
            or job.get("pins", {}).get("input_digest") != registration.input_digest
            or digest(job.get("pins", {}).get("profile")) != registration.profile_digest
            or job.get("binding_digest") != registration.runtime_binding_digest
            or digest(job.get("pins")) != registration.runtime_binding_digest
            or set(job.get("fields", {})) != RESEARCH_KEYS):
            fail("native_canonical_job_binding_invalid")
        bundle = registration.read_bundle
        if (set(bundle) != {"state_revision","server_time","job_key","job","halted","paused","effects","outbox","hold_reasons"}
            or type(bundle["state_revision"]) is not int or bundle["state_revision"] < 1
            or type(bundle["server_time"]) not in {int,float} or bundle["server_time"] <= 0
            or bundle["job_key"] != registration.job_key or bundle["job"] != job
            or type(bundle["halted"]) is not bool or bundle["paused"] is not job.get("paused")
            or not isinstance(bundle["effects"],dict) or not isinstance(bundle["outbox"],dict)
            or not isinstance(bundle["hold_reasons"],list)
            or len(set(bundle["hold_reasons"])) != len(bundle["hold_reasons"])
            or not set(bundle["hold_reasons"]) <= {"legacy_live_import_not_confirmed","program_halted","job_paused","unknown_effect","budget_unavailable"}):
            fail("native_canonical_scoped_bundle_invalid")
        for effect in bundle["effects"].values():
            if effect.get("job_key") != registration.job_key or any(effect.get("scope",{}).get(k) != v for k,v in identity.items()):
                fail("native_canonical_scoped_bundle_invalid")
        for outbox in bundle["outbox"].values():
            if outbox.get("kind") != "research_field_retry" or any(outbox.get("command",{}).get("scope",{}).get(k) != v for k,v in identity.items()):
                fail("native_canonical_scoped_bundle_invalid")
        transition = registration.publication_transition
        if result.canonical == registration.base_canonical:
            if transition is not None:
                fail("native_canonical_transition_invalid")
        else:
            if transition is None:
                fail("native_canonical_transition_missing")
            if (transition.base_canonical != registration.base_canonical or transition.current_canonical != result.canonical
                or any(getattr(transition, key) != getattr(registration, key) for key in (
                    "binding_id", "job_id", "job_key", "generation", "input_digest", "profile_digest", "runtime_binding_digest"))):
                fail("native_canonical_transition_invalid")
        return result


class OwnerRegistrationV1(FrozenRecord):
    """Server owner basis, not a public request or financial authorization."""
    binding_id: UUID
    base_canonical: CanonicalIdentityV1
    current_canonical: CanonicalIdentityV1
    publication_transition: None = None
    job_id: str = Field(min_length=1, max_length=256)
    job_key: Digest
    generation: Positive
    input_digest: Digest
    profile_digest: Digest
    runtime_binding_digest: Digest
    canonical_profile_digest: Digest
    source_sha256: Digest
    semantic_mapping_digest: Digest
    policy_digest: Digest
    program_key: str = Field(min_length=1, max_length=256)
    semantic_mapping: dict

    @model_validator(mode="after")
    def initial(self):
        mapping = self.semantic_mapping.get("field_mapping", {})
        if (self.base_canonical != self.current_canonical or set(mapping) != RESEARCH_KEYS
            or set(mapping.values()) != CANONICAL_KEYS or len(set(mapping.values())) != 20
            or digest(self.semantic_mapping) != self.semantic_mapping_digest):
            fail("native_canonical_owner_registration_invalid")
        return self


class CanonicalPolicyMaterializationV1(FrozenRecord):
    """I4 producer contract: materialize ALL canonical layers and policy together.

    Instances come only from the reviewed service-factory materializer. A model,
    queued acknowledgement or HTTP caller cannot submit this as authority.
    Native semantic proof still depends on restricted backend IAM; SQL checks
    persisted bases/CAS/lineage, not the scientific truth of a Python assertion.
    """
    contract_version: Literal["canonical-policy-materialization/v1"] = "canonical-policy-materialization/v1"
    prepared_digest: Digest
    publication_digest: Digest
    prior_canonical: CanonicalIdentityV1
    source_sha256: Digest
    canonical_profile_digest: Digest
    research_profile_digest: Digest
    runtime_binding_digest: Digest
    semantic_mapping_digest: Digest
    policy_digest: Digest
    # Explicit identity rebinding; no last/first candidate or string-to-UUID guess.
    evidence_id_mapping: dict[str, UUID]
    result: Specimen
    result_digest: Digest
    policy_receipt: dict
    policy_receipt_digest: Digest
    lineage_digest: Digest

    @model_validator(mode="after")
    def immutable_result(self):
        if (canonical_digest(self.result.model_dump(mode="json")) != self.result_digest
            or digest(self.policy_receipt) != self.policy_receipt_digest):
            fail("native_canonical_policy_materialization_invalid")
        return self


class NativeCanonicalResultV1(FrozenRecord):
    receipt_version: Literal["native-canonical-publication/v1"] = "native-canonical-publication/v1"
    published: PublishedResearch
    receipt_id: UUID
    operation_digest: Digest
    used_canonical_revision: Positive
    resulting_canonical_revision: Positive
    native_record_version_id: UUID
    canonical_run_id: UUID
    opaque_record_version: str = Field(min_length=1, max_length=512)
    snapshot_sha256: Digest
    publication_digest: Digest
    replayed: bool = Field(strict=True)

    @model_validator(mode="after")
    def next_revision(self):
        if (self.resulting_canonical_revision != self.used_canonical_revision + 1
            or self.published.record_revision != self.resulting_canonical_revision
            or self.publication_digest != self.published.publication_digest):
            fail("native_canonical_receipt_invalid")
        return self


def scientific_intent(principal, prepared):
    return digest({"operation": OPERATION, "actor_uid": principal.user_id,
                   "scope": prepared.basis.scope.model_dump(mode="json"), "prepared_digest": digest(prepared)})


def strict_history_scope_v1(value):
    """Raw immutable history identity; forbid JSON equality/coercion aliases."""
    keys={"organization_id","collection_id","specimen_id","job_id","generation"}
    if (type(value) is not dict or set(value)!=keys
        or any(type(value[key]) is not str or not value[key] for key in keys-{"generation"})
        or type(value["generation"]) is not int or value["generation"]<1):
        fail("canonical_capture_reuse_history_scope_invalid")
    return value


def canonical_value_v1(resolution,field_mapping,evidence_id_mapping):
    """Shared deterministic declared-layer/lineage transform; no scientific guess.

    I4A produces and I2 independently validates this same pure value. The current
    native projector cannot represent genuine derived records, which publication
    separately refuses before canonical mutation; this transform does not waive it.
    Scientific source_digest and consumed whole-resolution digest are distinct.
    This pure mapping matches source field/revision only, preserving both hashes;
    trusted validate_resolution and authoritative checkpoint/native proofs remain
    mandatory at their separate producer/publication boundaries.
    """
    if (set(field_mapping)!=RESEARCH_KEYS or set(field_mapping.values())!=CANONICAL_KEYS
        or len(set(field_mapping.values()))!=20):
        fail("canonical_value_field_mapping_unproved")
    expected_ids=set(resolution.evidence_ids)|set(resolution.value.evidence_ids)
    if set(evidence_id_mapping)!=expected_ids:
        fail("canonical_value_evidence_mapping_unproved")
    mapped={}
    for key,value in evidence_id_mapping.items():
        if not isinstance(value,(UUID,str)):
            fail("canonical_value_evidence_mapping_unproved")
        try:
            mapped[key]=str(value if isinstance(value,UUID) else UUID(value))
        except ValueError:
            fail("canonical_value_evidence_mapping_unproved")
    if len(set(mapped.values()))!=len(mapped):
        fail("canonical_value_evidence_mapping_unproved")
    value=resolution.value.model_dump(mode="json")
    if value["layer"] is not None and value["layer"]!=resolution.value_layer:
        fail("canonical_value_layer_conflict")
    value["layer"]=resolution.value_layer
    dependencies=[str(pin.field_key) for pin in resolution.dependencies]
    if len(set(dependencies))!=len(dependencies) or not set(dependencies)<=set(field_mapping):
        fail("canonical_value_dependency_mapping_unproved")
    derived_from=[]
    if resolution.value_layer=="derived":
        derivation=resolution.derivation
        if derivation is None or not dependencies:
            fail("canonical_value_derivation_unproved")
        source=[pin for pin in resolution.dependencies if pin.field_key==derivation.source_field
            and pin.revision==derivation.source_revision]
        if len(source)!=1 or not set(derivation.evidence_ids)<=set(mapped):
            fail("canonical_value_derivation_unproved")
        derived_from=[field_mapping[key] for key in dependencies]
    elif resolution.derivation is not None:
        fail("canonical_value_derivation_layer_conflict")
    if value["derived_from"] and value["derived_from"]!=derived_from:
        fail("canonical_value_derived_fields_conflict")
    value["derived_from"]=derived_from
    if not set(value["evidence_relations"])<=set(mapped):
        fail("canonical_value_evidence_mapping_unproved")
    value["evidence_ids"]=[mapped[evidence] for evidence in value["evidence_ids"]]
    value["evidence_relations"]={mapped[evidence]:relation for evidence,relation in value["evidence_relations"].items()}
    return FieldValue.model_validate(value)


def _projection_fields(rows, record_id):
    if not isinstance(rows, list) or len(rows) != 20:
        fail("native_canonical_projection_incomplete")
    if {row.get("fieldKey") for row in rows} != CANONICAL_KEYS or len({row.get("id") for row in rows}) != 20:
        fail("native_canonical_projection_incomplete")
    for row in rows:
        if (set(row) != {"id", "recordVersionId", "candidateId", "fieldKey", "state", "fieldGroup"}
            or str(UUID(row["recordVersionId"])) != str(record_id) or row["fieldGroup"] not in {"mandatory", "optional"}):
            fail("native_canonical_projection_invalid")
        UUID(row["id"])
        if row["candidateId"] is not None:
            UUID(row["candidateId"])
    return {row["fieldKey"]:row for row in rows}



def request_identity(principal,prepared):
    """Stable server request identity retained OUTSIDE journal/state hashing."""
    return digest({"operation":OPERATION,"actor_uid":principal.user_id,
        "scope":prepared.basis.scope.model_dump(mode="json"),"idempotency_key":prepared.basis.idempotency_key,
        "publication_digest":digest(prepared.publication),"expected_record_revision":prepared.basis.expected_record_revision})


class ReceiptFirstIntentV1(FrozenRecord):
    contract_version: Literal["research-publication-intent/v1"] = "research-publication-intent/v1"
    id: UUID
    actor_uid: str = Field(min_length=1)
    scope: ResearchScope
    idempotency_key: Digest
    request_identity_digest: Digest
    operation_digest: Digest
    prepared_digest: Digest
    publication_digest: Digest
    expected_record_revision: Positive
    # Complete original Prepared is recoverable without lease/outbox translation.
    prepared: PreparedNativePublication

    @model_validator(mode="after")
    def exact_intent(self):
        if (self.prepared.basis.scope!=self.scope or self.prepared.basis.actor_uid!=self.actor_uid
            or self.prepared.basis.idempotency_key!=self.idempotency_key
            or self.prepared.basis.expected_record_revision!=self.expected_record_revision
            or digest(self.prepared)!=self.prepared_digest or digest(self.prepared.publication)!=self.publication_digest):
            fail("native_canonical_intent_invalid")
        return self


class SqlConnectCanonicalResearchWriter(NativeCanonicalResearchAdapter):
    """Concrete operation adapter. Ordinary SqlConnectRepository.save is unused."""
    research_contract_version = "research-publication-v1"

    def __init__(self, repository, journal, *, blobs, materializer=None, evidence_provider=None,
                 projection_services=None, operation_client=None):
        self.repository, self.journal, self.blobs, self.materializer = repository, journal, blobs, materializer
        self.evidence_provider = evidence_provider
        self.projection_services = projection_services
        self.operation_client = operation_client or SqlConnectNativeOperationClient(repository)

    @staticmethod
    def _principal(principal, specimen_id):
        principal = Principal.model_validate(principal.model_dump(mode="json"))
        if principal.user_id != actor_uid.get() or principal.role not in {"viewer", "operator", "reviewer", "manager", "admin"}:
            raise PermissionError("native_canonical_verified_actor_required")
        UUID(principal.scope.organization_id); UUID(principal.scope.collection_id); UUID(specimen_id)
        return principal

    def _variables(self, principal, specimen_id):
        return {"organizationId": principal.scope.organization_id, "collectionId": principal.scope.collection_id,
                "specimenId": str(UUID(specimen_id)), "actorUid": principal.user_id}

    async def _execute(self, operation, variables, *, mutation=False):
        # asyncio.to_thread copies the verified ContextVar; caller owns token reset.
        # No session/credentials/default-ADC construction occurs in this adapter.
        return await asyncio.to_thread(self.operation_client.execute, operation, variables, mutation=mutation)

    async def read_current_binding(self, principal, specimen_id):
        principal = self._principal(principal, specimen_id)
        data = await self._execute("GetCanonicalResearchBindingV1", self._variables(principal, specimen_id))
        return CanonicalBindingV1.from_native(principal.scope, specimen_id, data.get("binding"))

    async def register_current_binding(self, principal, specimen_id, registration):
        principal = self._principal(principal, specimen_id)
        if principal.role not in {"manager", "admin"}:
            raise PermissionError("native_canonical_owner_required")
        registration = OwnerRegistrationV1.model_validate(registration.model_dump(mode="json"))
        variables = self._variables(principal, specimen_id)
        document = await asyncio.to_thread(self.journal.store._read, self.journal.scope)
        if (self.journal.scope.actor_uid != principal.user_id
            or self.journal.scope.specimen_id != str(UUID(specimen_id))
            or digest(document.state.get("budget_policy")) != registration.semantic_mapping.get("journal_budget_policy_digest")):
            fail("native_canonical_owner_budget_policy_pin_invalid")
        native_registration = registration.model_dump(mode="json")
        native_registration["journal_budget_policy"] = document.state["budget_policy"]
        native_registration["state_revision"] = document.revision
        variables["registrationJson"] = exact_json(native_registration)
        data = await self._execute("RegisterCanonicalResearchBindingV1", variables, mutation=True)
        if type(data.get("registered")) is not int or data["registered"] != 1:
            fail("native_canonical_registration_rejected")
        return await self.read_current_binding(principal, specimen_id)

    async def read_same_operation_intent(self,principal,specimen_id,idempotency_key,request_identity_digest):
        """I1 invokes BEFORE mutable prepare on restart, using its exact server request digest."""
        principal=self._principal(principal,specimen_id)
        variables={**self._variables(principal,specimen_id),"idempotencyKey":idempotency_key,
                   "requestIdentityDigest":request_identity_digest}
        data=await self._execute("GetResearchPublicationIntentV1",variables)
        row=data.get("intent")
        if row is None:
            return None
        if not isinstance(row,dict) or set(row)!={"id","actorUid","specimenId","requestIdentityDigest","operationDigest","preparedDigest","publicationDigest","preparedJson"}:
            fail("native_canonical_intent_partial")
        if (row["actorUid"]!=principal.user_id or row["specimenId"]!=str(UUID(specimen_id))
            or row["requestIdentityDigest"]!=request_identity_digest):
            fail("native_canonical_intent_conflict")
        prepared=PreparedNativePublication.model_validate(json.loads(row["preparedJson"]))
        if (prepared.basis.scope.organization_id!=principal.scope.organization_id
            or prepared.basis.scope.collection_id!=principal.scope.collection_id
            or prepared.basis.scope.specimen_id!=str(UUID(specimen_id))
            or prepared.basis.idempotency_key!=idempotency_key
            or row["operationDigest"]!=scientific_intent(principal,prepared)
            or row["requestIdentityDigest"]!=request_identity(principal,prepared)):
            fail("native_canonical_intent_conflict")
        return ReceiptFirstIntentV1(id=row["id"],actor_uid=principal.user_id,scope=prepared.basis.scope,
            idempotency_key=idempotency_key,request_identity_digest=row["requestIdentityDigest"],
            operation_digest=row["operationDigest"],prepared_digest=row["preparedDigest"],
            publication_digest=row["publicationDigest"],expected_record_revision=prepared.basis.expected_record_revision,prepared=prepared)

    async def resume_same_operation(self,principal,specimen_id,idempotency_key,request_identity_digest):
        intent=await self.read_same_operation_intent(principal,specimen_id,idempotency_key,request_identity_digest)
        if intent is None:
            fail("native_canonical_original_intent_unavailable")
        return await self.publish_receipt_first(principal,intent.prepared)

    async def _retain_intent(self,principal,prepared):
        identity_digest=request_identity(principal,prepared)
        old=await self.read_same_operation_intent(principal,prepared.basis.scope.specimen_id,prepared.basis.idempotency_key,identity_digest)
        if old is not None:
            if old.prepared!=prepared:
                fail("native_canonical_intent_conflict")
            return old
        intent=ReceiptFirstIntentV1(id=derived_id("research-publication-intent/v1",principal.user_id,prepared.basis.idempotency_key),
            actor_uid=principal.user_id,scope=prepared.basis.scope,idempotency_key=prepared.basis.idempotency_key,
            request_identity_digest=identity_digest,operation_digest=scientific_intent(principal,prepared),
            prepared_digest=digest(prepared),publication_digest=digest(prepared.publication),
            expected_record_revision=prepared.basis.expected_record_revision,prepared=prepared)
        variables={**self._variables(principal,prepared.basis.scope.specimen_id),"intentJson":exact_json(intent.model_dump(mode="json")),
            "preparedJson":exact_json(prepared.model_dump(mode="json"))}
        try:
            result=await self._execute("RetainResearchPublicationIntentV1",variables,mutation=True)
            if type(result.get("retainedIntent")) is not int or result["retainedIntent"]!=1:
                fail("native_canonical_intent_not_retained")
        except asyncio.CancelledError:
            raise
        except Exception:
            # Unknown insert acknowledgement: one read, no repeated mutation.
            found=await self.read_same_operation_intent(principal,prepared.basis.scope.specimen_id,prepared.basis.idempotency_key,identity_digest)
            if found is None or found.prepared!=prepared:
                fail("native_canonical_intent_outcome_unknown")
            return found
        found=await self.read_same_operation_intent(principal,prepared.basis.scope.specimen_id,prepared.basis.idempotency_key,identity_digest)
        if found is None or found.prepared!=prepared:
            fail("native_canonical_intent_not_retained")
        return found

    def _receipt_variables(self, principal, prepared):
        return {**self._variables(principal, prepared.basis.scope.specimen_id),
                "idempotencyKey": prepared.basis.idempotency_key,
                "operationDigest": scientific_intent(principal, prepared)}

    async def _receipt(self, principal, prepared, *, replayed):
        # This native query performs fresh persisted membership/sensitivity checks.
        # It reads no mutable binding/lease/outbox/budget or job state.
        data = await self._execute("GetResearchPublicationReceiptV1", self._receipt_variables(principal, prepared))
        row = data.get("retained")
        if row is None:
            return None
        if not isinstance(row, dict) or set(row) != {"publication", "request", "snapshot", "record", "fields", "audit", "outbox", "intent"}:
            fail("native_canonical_receipt_partial")
        pub, request, snapshot, record = (row[k] for k in ("publication", "request", "snapshot", "record"))
        if not all(isinstance(v, dict) for v in (pub, request, snapshot, record, row["audit"], row["outbox"])):
            fail("native_canonical_receipt_partial")
        intent_row=row["intent"]
        if (not isinstance(intent_row,dict) or intent_row.get("preparedDigest")!=digest(prepared)
            or intent_row.get("requestIdentityDigest")!=request_identity(principal,prepared)
            or intent_row.get("operationDigest")!=scientific_intent(principal,prepared)):
            fail("native_canonical_receipt_intent_partial")
        expected_scope = prepared.basis.scope
        if (pub.get("actorUid") != principal.user_id or pub.get("specimenId") != expected_scope.specimen_id
            or pub.get("operationDigest") != scientific_intent(principal, prepared)
            or pub.get("preparedDigest") != digest(prepared)
            or pub.get("publicationDigest") != digest(prepared.publication)
            or pub.get("idempotencyKey") != prepared.basis.idempotency_key
            or pub.get("jobId") != expected_scope.job_id or pub.get("generation") != expected_scope.generation
            or pub.get("inputDigest") != expected_scope.input_digest or pub.get("profileDigest") != expected_scope.profile_digest
            or pub.get("runtimeBindingDigest") != prepared.basis.binding_digest
            or type(pub.get("usedCanonicalRevision")) is not int
            or pub["usedCanonicalRevision"] != prepared.basis.expected_record_revision
            or type(pub.get("resultingCanonicalRevision")) is not int
            or pub["resultingCanonicalRevision"] != pub["usedCanonicalRevision"] + 1
            or pub.get("projectionCount") != 20):
            fail("native_canonical_receipt_conflict")
        expected_request = {"operation": OPERATION, "actorUid": principal.user_id,
            "idempotencyKey": prepared.basis.idempotency_key, "requestSha256": pub["operationDigest"],
            "specimenId": expected_scope.specimen_id, "revision": pub["resultingCanonicalRevision"]}
        if request != expected_request or snapshot.get("sha256") != pub.get("snapshotSha256"):
            fail("native_canonical_receipt_partial")
        retained = await asyncio.to_thread(self.repository._snapshot, snapshot)
        if (retained.id != expected_scope.specimen_id or retained.version != pub["resultingCanonicalRevision"]
            or retained.run.id != pub.get("canonicalRunId") or retained.asset.sensitive != pub.get("sensitive")
            or canonical_digest(snapshot["snapshot"]) != pub["snapshotSha256"]
            or record.get("id") != pub.get("nativeRecordVersionId") or record.get("runId") != retained.run.id
            or record.get("predecessorId") != pub.get("usedRecordVersionId")
            or row["audit"].get("requestSha256") != pub["operationDigest"]
            or row["audit"].get("actorUid") != principal.user_id
            or row["audit"].get("revision") != retained.version
            or row["outbox"].get("deduplicationKey") != pub["operationDigest"]
            or row["outbox"].get("aggregateRevision") != retained.version):
            fail("native_canonical_receipt_partial")
        _projection_fields(row["fields"], pub["nativeRecordVersionId"])
        if digest(row["fields"]) != pub.get("projectionDigest"):
            fail("native_canonical_receipt_partial")
        return NativeCanonicalResultV1(published=PublishedResearch(scope=expected_scope,
            record_revision=retained.version, publication_digest=pub["publicationDigest"]),
            receipt_id=pub["id"], operation_digest=pub["operationDigest"],
            used_canonical_revision=pub["usedCanonicalRevision"], resulting_canonical_revision=retained.version,
            native_record_version_id=pub["nativeRecordVersionId"], canonical_run_id=retained.run.id,
            opaque_record_version=pub["hostRecordVersionId"], snapshot_sha256=pub["snapshotSha256"],
            publication_digest=pub["publicationDigest"], replayed=replayed)

    async def publish_receipt_first(self, principal, prepared):
        prepared = PreparedNativePublication.model_validate(prepared.model_dump(mode="json"))
        principal = self._principal(principal, prepared.basis.scope.specimen_id)
        scope = prepared.basis.scope
        if (principal.user_id != prepared.basis.actor_uid or principal.scope.organization_id != scope.organization_id
            or principal.scope.collection_id != scope.collection_id or prepared.basis.expected_record_revision < 1):
            raise PermissionError("native_canonical_intent_scope_denied")
        old = await self._receipt(principal, prepared, replayed=True)
        if old is not None:
            return old
        if principal.role not in {"operator", "reviewer", "manager", "admin"}:
            raise PermissionError("native_canonical_write_role_denied")
        if self.materializer is None:
            fail("canonical_policy_materializer_unavailable")
        await validate_native_publication(self.journal, prepared, principal=principal, blobs=self.blobs)
        raw = (await self._execute("GetCanonicalResearchBindingV1", self._variables(principal, scope.specimen_id))).get("binding")
        binding = CanonicalBindingV1.from_native(principal.scope, scope.specimen_id, raw)
        registration = binding.registration
        if (binding.sensitive != scope.sensitive or binding.sensitive
            or binding.canonical.record_revision != prepared.basis.expected_record_revision
            or registration.base_canonical != binding.canonical
            or registration.publication_transition is not None
            or registration.job_id != scope.job_id or registration.generation != scope.generation
            or registration.input_digest != scope.input_digest or registration.profile_digest != scope.profile_digest
            or registration.runtime_binding_digest != prepared.basis.binding_digest
            or registration.program_key != prepared.basis.program_key or registration.job_key != prepared.basis.job_key):
            fail("native_canonical_new_write_basis_stale")
        if registration.read_bundle["hold_reasons"]:
            fail("native_canonical_import_or_operational_authority_unavailable")
        # Version1 permits one strict base->base+1 publication. Sibling rebase and
        # additional same-job publication need a new reviewed version, never offsets.
        prior = await asyncio.to_thread(self.repository._snapshot, raw["snapshot"])
        if (prior.version != binding.canonical.record_revision or prior.run.id != str(binding.canonical.canonical_run_id)
            or prior.asset.sha256 != registration.source_sha256
            or canonical_digest(prior.run.profile_snapshot) != registration.canonical_profile_digest):
            fail("native_canonical_snapshot_binding_invalid")
        services = self.projection_services or CanonicalProjectionServicesV1.from_repository(self.repository)
        services.verify()
        prior_projection = tuple(copy.deepcopy(raw["projection"]))
        _projection_fields(list(prior_projection),binding.canonical.record_version_id)
        if self.evidence_provider is None:
            if prepared.publication.checkpoints[0].resolution.evidence_ids or prepared.publication.checkpoints[0].resolution.value.evidence_ids:
                fail("canonical_captured_evidence_provider_unavailable")
            captured_evidence = ()
        else:
            captured_evidence = tuple(CapturedCanonicalEvidenceV1.model_validate(item.model_dump(mode="json"))
                for item in await self.evidence_provider.capture(principal,prepared,binding,prior.model_copy(deep=True)))
        await self._verify_captured_evidence(prepared,binding,prior,captured_evidence)
        # I4 owns the exact trusted policy implementation; no public payload route.
        materialized = await self.materializer.materialize(principal, prepared, binding, prior.model_copy(deep=True),
            prior_projection=prior_projection,captured_evidence=captured_evidence,projection_services=services)
        materialized = CanonicalPolicyMaterializationV1.model_validate(materialized.model_dump(mode="json"))
        payload = self._materialization(principal, prepared, binding, raw, prior, materialized, projection_services=services, captured_evidence=captured_evidence)
        intent=await self._retain_intent(principal,prepared)
        payload["intent_id"]=str(intent.id)
        capture_scope,reuse_history=self._capture_lineage(prepared,binding)
        payload["capture_scope"]=capture_scope.model_dump(mode="json")
        payload["reuse_history"]=reuse_history
        # Revalidate slow capture/materialization reads before the final native CAS.
        await validate_native_publication(self.journal, prepared, principal=principal, blobs=self.blobs)
        document = await asyncio.to_thread(self.journal.store._read, self.journal.scope)
        if document.revision != prepared.basis.state_revision or digest(document.state) != prepared.basis.state_digest:
            fail("native_canonical_research_state_changed")
        payload["expected_state"] = copy.deepcopy(document.state)
        payload["next_state"] = copy.deepcopy(document.state)
        # Do NOT mutate immutable job.record_revision or any effect/budget/history.
        payload["next_state"]["outbox"][prepared.basis.publication_outbox_key]["delivered"] = True
        payload["next_state"]["outbox"][prepared.basis.checkpoint_outbox_key]["delivered"] = True
        payload["next_state"]["outbox"][prepared.basis.publication_outbox_key]["canonical_commit"] = payload["receipt"]
        payload["next_state_json"] = exact_json(payload["next_state"])
        # The native operation verifies only this exact outbox delta is permitted.
        variables = {**self._variables(principal, scope.specimen_id), "commitJson": exact_json(payload)}
        try:
            result = await self._execute("PublishCanonicalResearchV1", variables, mutation=True)
            if type(result.get("committed")) is not int or result["committed"] != 1:
                fail("native_canonical_transaction_rejected")
        except asyncio.CancelledError:
            # No cleanup/retry can resurrect authority after request cancellation.
            raise
        except Exception:
            # Unknown acknowledgement gets one fresh receipt read, never a write,
            # new lease/reservation/model call or generic-save fallback.
            retained = await self._receipt(principal, prepared, replayed=True)
            if retained is None:
                fail("native_canonical_commit_outcome_unknown")
            return retained
        retained = await self._receipt(principal, prepared, replayed=False)
        if retained is None:
            fail("native_canonical_commit_receipt_missing")
        return retained


    @staticmethod
    def _capture_lineage(prepared,binding):
        """Authoritative existing same-job reuse; never scope-rebind an old receipt."""
        basis=prepared.basis; current=basis.scope; original=basis.original_scope
        if not basis.reused:
            if original!=current or basis.source_binding_digest!=binding.registration.runtime_binding_digest:
                fail("canonical_capture_original_scope_unproved")
            return current,None
        identity_keys=("organization_id","collection_id","specimen_id","job_id","input_digest","profile_digest","sensitive")
        if (any(getattr(original,key)!=getattr(current,key) for key in identity_keys)
            or original.generation>=current.generation or basis.history_digest is None):
            fail("canonical_capture_reuse_scope_unproved")
        job=binding.registration.job
        original_identity={key:getattr(original,key) for key in ("organization_id","collection_id","specimen_id","job_id","generation")}
        retained_history=job.get("history",[])
        if type(retained_history) is not list or any(type(item) is not dict for item in retained_history):
            fail("canonical_capture_reuse_history_unproved")
        history=[item for item in retained_history
            if strict_history_scope_v1(item.get("scope"))==original_identity and digest(item)==basis.history_digest]
        if len(history)!=1:
            fail("canonical_capture_reuse_history_unproved")
        history=history[0];field=job.get("fields",{}).get(str(basis.field_key),{})
        native=field.get("checkpoint"); old_field=history.get("fields",{}).get(str(basis.field_key),{})
        if (not isinstance(native,dict) or old_field.get("checkpoint")!=native
            or native.get("id")!=basis.checkpoint_id or digest(native)!=basis.checkpoint_digest
            or history.get("binding_digest")!=basis.source_binding_digest
            or digest(history.get("pins"))!=basis.source_binding_digest
            or history.get("pins")!=job.get("pins") or job.get("binding_digest")!=basis.binding_digest):
            fail("canonical_capture_reuse_checkpoint_unproved")
        typed_original=FieldCheckpoint.model_validate(native["payload"])
        expected=FieldCheckpoint.model_validate({**typed_original.model_dump(mode="json"),
            "scope":current.model_dump(mode="json"),"reused_from_scope_digest":digest(original),
            "reused_from_checkpoint_digest":digest(typed_original)})
        current_identity={key:getattr(current,key) for key in original_identity}
        expected_link={"reused_from_scope_digest":digest(original_identity),"checkpoint_digest":digest(native),
            "into_scope_digest":digest(current_identity),"source_binding_digest":basis.source_binding_digest,
            "target_binding_digest":basis.binding_digest,"retained_dependencies":native["dependencies"],
            "retained_dependency_digests":native.get("dependency_digests",{})}
        if (typed_original.scope!=original or digest(typed_original)!=basis.original_typed_checkpoint_digest
            or prepared.publication.checkpoints!=(expected,) or field.get("reuse")!=expected_link
            or field.get("locked") is not False):
            fail("canonical_capture_reuse_link_unproved")
        return original,copy.deepcopy(history)

    async def _verify_captured_evidence(self,prepared,binding,prior,items):
        capture_scope,_=self._capture_lineage(prepared,binding)
        checkpoint = prepared.publication.checkpoints[0]
        expected_ids = set(checkpoint.resolution.evidence_ids) | set(checkpoint.resolution.value.evidence_ids)
        if len({item.evidence.id for item in items}) != len(items) or {item.evidence.id for item in items} != expected_ids:
            fail("canonical_captured_evidence_scope_invalid")
        receipts = {receipt.effect_id:receipt for receipt in prepared.basis.receipts}
        native_ids = set()
        for item in items:
            UUID(item.canonical_evidence.id)
            if (str(item.canonical_run_id)!=prior.run.id or item.canonical_region_id!=item.canonical_evidence.region_id
                or tuple(str(value) for value in item.canonical_observation_ids)!=tuple(item.canonical_evidence.observation_ids)
                or item.canonical_region_id is not None and not any(region.id==item.canonical_region_id for region in prior.run.regions)
                or any(not any(observation.id==str(value) for observation in prior.run.observations) for value in item.canonical_observation_ids)):
                fail("canonical_evidence_reading_identity_unproved")
            if item.canonical_evidence.id in native_ids or item.canonical_mapping_digest != binding.registration.semantic_mapping_digest:
                fail("canonical_captured_evidence_mapping_invalid")
            native_ids.add(item.canonical_evidence.id)
            if item.source_registry_digest != checkpoint.source_registry_digest:
                fail("canonical_captured_evidence_registry_invalid")
            if item.origin == "existing_canonical":
                if (item.receipt is not None or sum(e == item.canonical_evidence for e in prior.run.evidence) != 1
                    or item.canonical_producer is not None and sum(p == item.canonical_producer for p in prior.run.tool_calls) != 1):
                    fail("canonical_existing_evidence_unproved")
                continue
            receipt = item.receipt
            if receipt is None or receipts.get(receipt.effect_id) != receipt or self.blobs is None or item.body is None:
                fail("canonical_source_capture_unproved")
            def read_capture():
                data = self.blobs.get(BlobRef(**receipt.capture.model_dump()))
                if len(data)!=receipt.capture.byte_size or hashlib.sha256(data).hexdigest()!=receipt.capture.sha256:
                    fail("canonical_source_capture_unproved")
                envelope = json.loads(data)
                return SourceResult.model_validate(envelope["result"]["typed_payload"])
            source = await asyncio.to_thread(read_capture)
            request=item.original_specialist_request
            if (request is None or request.scope!=capture_scope or checkpoint.field_key not in request.field_keys
                or request.prompt.source_registry_digest!=item.source_registry_digest
                or item.source_result is None
                or item.source_result.model_copy(update={"receipt":None})!=source.model_copy(update={"receipt":None})
                or item.capture_envelope_digest!=receipt.capture.sha256
                or item.raw_capture!=receipt.raw_capture):
                fail("canonical_source_request_envelope_unproved")
            tool_receipt=item.source_result.receipt
            if (tool_receipt is None or tool_receipt.scope!=capture_scope or tool_receipt.effect_status!="completed"
                or tool_receipt.effect_id!=receipt.effect_id or tool_receipt.request_digest!=receipt.request_digest
                or tool_receipt.binding_digest!=receipt.binding_digest or tool_receipt.binding_digest!=prepared.basis.source_binding_digest
                or tool_receipt.capture_locator!=receipt.capture.locator or receipt.attempt_id not in tool_receipt.attempt_ids
                or checkpoint.field_key not in tool_receipt.field_keys or tool_receipt.source_id!=item.evidence.source_id
                or tool_receipt.outcome!=source.status or tool_receipt.settled_micro_usd is None or tool_receipt.held_micro_usd!=0):
                fail("canonical_source_tool_receipt_unproved")
            if (sum(e == item.evidence for e in source.evidence)!=1
                or source.coverage.field_key!=checkpoint.field_key
                or source.coverage.source_id!=item.evidence.source_id
                or source.coverage.qualification_digest!=item.source_policy_digest):
                fail("canonical_source_evidence_unproved")
            source_mapping = binding.registration.semantic_mapping.get("evidence_sources",{}).get(item.evidence.source_id)
            if not isinstance(source_mapping,dict) or source_mapping.get("policy_digest")!=item.source_policy_digest:
                fail("canonical_source_mapping_unavailable")
            if (item.canonical_evidence.source != source_mapping.get("canonical_source")
                or item.canonical_evidence.kind != "lookup"
                or item.canonical_evidence.locator != (item.evidence.locator if str(source.status)=="success" else None)
                or item.canonical_evidence.digest != item.evidence.response_digest
                or item.canonical_producer is None or item.canonical_producer.evidence_id!=item.canonical_evidence.id
                or item.canonical_producer.outcome!=source.status or item.canonical_producer.phase!="lookup"):
                fail("canonical_source_evidence_lineage_invalid")
            # IDs/semantic capture alone do not establish the original source
            # body. Both actual immutable body and its canonical copy are read.
            body_ref = BlobRef(**item.body)
            body = await asyncio.to_thread(self.blobs.get,body_ref)
            if hashlib.sha256(body).hexdigest()!=item.evidence.response_digest:
                fail("canonical_source_body_unproved")
            canonical_ref = item.canonical_evidence.raw_ref
            if canonical_ref is None or item.canonical_body_digest!=hashlib.sha256(body).hexdigest():
                fail("canonical_source_body_unproved")
            canonical_body = await asyncio.to_thread(self.repository.graph_blobs.get,canonical_ref)
            if canonical_body != body:
                fail("canonical_source_body_copy_unproved")

    async def publish_native_research(self, principal, prepared):
        return (await self.publish_receipt_first(principal, prepared)).published

    def _materialization(self, principal, prepared, binding, raw, prior, materialized, *, projection_services=None, captured_evidence=()):
        reg, result = binding.registration, materialized.result.model_copy(deep=True)
        cp = prepared.publication.checkpoints[0]
        key = reg.field_mapping[str(cp.field_key)]
        if (materialized.prepared_digest != digest(prepared) or materialized.publication_digest != digest(prepared.publication)
            or materialized.prior_canonical != binding.canonical
            or materialized.source_sha256 != reg.source_sha256
            or materialized.canonical_profile_digest != reg.canonical_profile_digest
            or materialized.research_profile_digest != reg.profile_digest
            or materialized.runtime_binding_digest != reg.runtime_binding_digest
            or materialized.semantic_mapping_digest != reg.semantic_mapping_digest or materialized.policy_digest != reg.policy_digest
            or result.id != prior.id or result.scope != prior.scope or result.asset != prior.asset
            or result.version != prior.version + 1 or result.run.id != prior.run.id
            or result.previous_runs != prior.previous_runs or result.audit != prior.audit
            or result.audit_offset != prior.audit_offset or result.history_through_revision != prior.history_through_revision
            or result.run.disposition is None or result.run.human_approved != prior.run.human_approved
            or set(prior.run.fields) != CANONICAL_KEYS or set(result.run.fields) != CANONICAL_KEYS
            or any(reg.human_locks[field] and result.run.fields[field] != prior.run.fields[field] for field in CANONICAL_KEYS)):
            fail("canonical_policy_materialization_invalid")
        id_map = {k:str(v) for k,v in materialized.evidence_id_mapping.items()}
        if ({item.evidence.id:str(UUID(item.canonical_evidence.id)) for item in captured_evidence} != id_map
            or set(id_map) != set(cp.resolution.evidence_ids) | set(cp.resolution.value.evidence_ids)) :
            fail("canonical_policy_evidence_mapping_invalid")
        for item in captured_evidence:
            if sum(e == item.canonical_evidence for e in result.run.evidence) != 1:
                fail("canonical_policy_evidence_body_changed")
            if item.canonical_producer is not None and sum(p == item.canonical_producer for p in result.run.tool_calls) != 1:
                fail("canonical_policy_evidence_producer_changed")
        expected_value=canonical_value_v1(cp.resolution,reg.field_mapping,id_map)
        if result.run.fields[key] != expected_value:
            fail("canonical_policy_checkpoint_value_changed")
        if any(result.run.fields[k] != prior.run.fields[k] for k in CANONICAL_KEYS - {key}):
            fail("canonical_policy_untouched_fields_changed")
        # Immutable input/readings/costs/authority history must not roll back or revive.
        allowed = {"fields", "evidence", "lookups", "tool_calls", "disposition", "disposition_summary", "reasons", "findings", "stage"}
        before, after = prior.run.model_dump(mode="json"), result.run.model_dump(mode="json")
        if {k:v for k,v in before.items() if k not in allowed} != {k:v for k,v in after.items() if k not in allowed}:
            fail("canonical_policy_immutable_history_changed")
        for name in ("evidence", "lookups", "tool_calls"):
            if after[name][:len(before[name])] != before[name]:
                fail("canonical_policy_immutable_history_changed")
        expected_policy_basis = {"publication_digest": digest(prepared.publication), "prior_canonical": binding.canonical.model_dump(mode="json"),
            "result_digest": materialized.result_digest, "policy_digest": reg.policy_digest,
            "semantic_mapping_digest": reg.semantic_mapping_digest, "exact_field_keys": sorted(CANONICAL_KEYS)}
        if any(materialized.policy_receipt.get(k) != v for k,v in expected_policy_basis.items()) or materialized.policy_receipt.get("status") != "computed":
            fail("canonical_policy_receipt_unproved")
        # Existing PR168 _fields skips literal-less values and has no genuine
        # DerivationRecord projection. Never fabricate a literal/candidate or
        # relabel a derived record as "parsed" merely to progress.
        if cp.resolution.value_layer=="derived":
            fail("canonical_derived_projection_v1_unavailable")
        if (expected_value.state==ValueState.SUPPORTED and expected_value.layer=="settled"
            and expected_value.literal is None and not expected_value.verbatim_by_observation):
            fail("canonical_settled_projection_v1_unavailable")
        # Derive the normalized graph with the existing pure canonical projector.
        services = projection_services or self.projection_services or CanonicalProjectionServicesV1.from_repository(self.repository)
        services.verify()
        projection = services.projector(result, services.locate, services.size, principal.user_id)
        old_projection = services.projector(prior, services.locate, services.size, principal.user_id)
        records = [w.variables for w in projection if w.operation == "AppendRecordVersionV2"]
        if len(records) != 1:
            fail("canonical_policy_record_projection_missing")
        record = records[0]
        record["predecessorId"] = str(binding.canonical.record_version_id)
        fields = sorted([w.variables for w in projection if w.operation == "AppendResolvedFieldV2"], key=lambda row:row["fieldKey"])
        new_fields = _projection_fields(fields, record["id"])
        old_fields = _projection_fields(raw["projection"], binding.canonical.record_version_id)
        for field in CANONICAL_KEYS - {key}:
            if any(new_fields[field][k] != old_fields[field][k] for k in ("candidateId", "state", "fieldGroup")):
                fail("canonical_policy_retained_projection_changed")
        if result.run.fields[key].state == ValueState.SUPPORTED and new_fields[key]["candidateId"] is None:
            fail("canonical_policy_supported_candidate_missing")
        lineage = {"prior_fields": sorted(raw["projection"], key=lambda r:r["fieldKey"]), "fields": fields,
            "evidence_id_mapping": id_map, "before_fields": {k:v.model_dump(mode="json") for k,v in prior.run.fields.items()},
            "after_fields": {k:v.model_dump(mode="json") for k,v in result.run.fields.items()}, "human_locks": reg.human_locks}
        if digest(lineage) != materialized.lineage_digest:
            fail("canonical_policy_lineage_unproved")
        old_keys = {w.key for w in old_projection}
        operation_names = {"AppendSourceAssetV2":"assets", "AppendEvidenceItemV2":"evidence", "AppendToolCallV1":"tool_calls",
            "AppendFieldCandidateV2":"candidates", "AppendCandidateEvidenceV2":"links", "AppendValidationFindingV2":"findings"}
        delta = {name:[] for name in operation_names.values()}
        for write in projection:
            if write.key in old_keys or write.operation in {"AppendRecordVersionV2", "AppendResolvedFieldV2"}:
                continue
            if write.operation not in operation_names:
                fail("canonical_policy_projection_delta_unavailable")
            if write.operation == "AppendFieldCandidateV2" and write.variables["fieldKey"] != key:
                fail("canonical_policy_untouched_candidate_changed")
            delta[operation_names[write.operation]].append(write.variables)
        operation_digest = scientific_intent(principal, prepared)
        receipt_id = derived_id(OPERATION, principal.user_id, prepared.basis.idempotency_key)
        result.audit.append(AuditEvent(id=derived_id(receipt_id,"audit"), actor=principal.user_id,
            action="research_publication", reason=operation_digest,
            before={"revision":prior.version}, after={"revision":result.version, "record_version_id":record["id"]}))
        snapshot = pack(result, self.repository.graph_blobs)
        check_snapshot(exact_json(snapshot))
        # Existing host representation is opaque to consumers. Its producer is
        # the same canonical API convention, never a UUID parser or job=run guess.
        opaque = f"{result.run.id}:{result.version}"
        receipt = {"id":receipt_id, "actorUid":principal.user_id, "idempotencyKey":prepared.basis.idempotency_key,
            "operationDigest":operation_digest, "publicationDigest":digest(prepared.publication), "preparedDigest":digest(prepared),
            "specimenId":result.id, "bindingId":str(reg.binding_id), "jobId":reg.job_id,"jobKey":reg.job_key,"generation":reg.generation,
            "inputDigest":reg.input_digest,"profileDigest":reg.profile_digest,"runtimeBindingDigest":reg.runtime_binding_digest,
            "usedCanonicalRevision":prior.version,"usedRecordVersionId":str(binding.canonical.record_version_id),
            "usedHostRecordVersionId":binding.canonical.host_record_version_id,"usedSnapshotSha256":binding.canonical.snapshot_sha256,
            "resultingCanonicalRevision":result.version,"nativeRecordVersionId":record["id"],"canonicalRunId":result.run.id,
            "hostRecordVersionId":opaque,"snapshotSha256":canonical_digest(snapshot),"projectionDigest":digest(fields),
            "projectionCount":20,"sensitive":result.asset.sensitive,
            "auditId":derived_id(receipt_id,"audit"), "outboxId":derived_id(receipt_id,"outbox"),
            "policyReceiptDigest":materialized.policy_receipt_digest, "lineageDigest":materialized.lineage_digest}
        return {"receipt":receipt, "snapshot":snapshot, "snapshot_contract":"0.1", "state":run_status(result.run),
            "record":record,"fields":fields,"prior_fields":sorted(raw["projection"],key=lambda r:r["fieldKey"]),
            "delta":delta,"changed_field":key,"registration_revision":reg.registration_revision,
            "program_key":reg.program_key,"state_revision":prepared.basis.state_revision,
            "native_guard":json.loads(prepared.basis.native_guard_json),"prepared":prepared.model_dump(mode="json"),
            "policy_materialization":materialized.model_dump(mode="json"),
            "audit_id":derived_id(receipt_id,"audit"),"outbox_id":derived_id(receipt_id,"outbox")}
