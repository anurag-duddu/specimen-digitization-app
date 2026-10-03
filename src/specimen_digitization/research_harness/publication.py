"""Verified translation of persisted research authorization; no canonical writer.

The native operation and adapter remain unadmitted. SQLite qualification proves
the translator, not a canonical SQL Connect transaction or deployment.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import Literal

from pydantic import Field, model_validator

from specimen_digitization.application.domain import Principal

from .compatibility import PublicationGuard, PublicationUnavailable, PublishedResearch, ResearchPublication
from .contracts import (
    ROLE_FIELDS, CollectionProfile, Digest, FieldCheckpoint, FieldKey, FrozenRecord,
    PromptPin, ResearchScope, digest,
)
from .journal import DurableResearchJournal
from .persistence import (
    CONTRACT_VERSION, BlobRef, CapturedResult, ImmutableBlobs, StaleWork, canonical,
)


class NativeCapture(FrozenRecord):
    locator: str = Field(min_length=1, max_length=2048)
    generation: str = Field(min_length=1)
    sha256: Digest
    byte_size: int = Field(strict=True, ge=0, le=8_000_000)


class NativeLease(FrozenRecord):
    job_key: Digest
    owner: str = Field(min_length=1)
    fence: int = Field(strict=True, gt=0)
    generation: int = Field(strict=True, gt=0)
    expires_at: float = Field(gt=0, allow_inf_nan=False)


class NativeReceiptBinding(FrozenRecord):
    effect_id: Digest
    request_digest: Digest
    binding_digest: Digest
    attempt_id: str = Field(min_length=1)
    receipt_digest: Digest
    capture: NativeCapture
    raw_capture: NativeCapture | None = None


class NativeDependencyBasis(FrozenRecord):
    field_key: FieldKey
    revision: int = Field(strict=True, gt=0)
    resolution_digest: Digest
    checkpoint_id: Digest
    checkpoint_digest: Digest


class NativePublicationBasis(FrozenRecord):
    """Exact persisted authority alongside the distinct typed publication digest.

    `state_revision` is the required native CAS revision after preparation.
    `native_guard_json` contains only the guard already validated against its
    exact persisted outbox. It is not an authorization supplied by a model.
    The native adapter must still read the canonical snapshot/run in its own
    transaction; no research-only reader can establish those canonical rows.
    """

    contract_version: Literal["research-native-publication-basis-v1"] = "research-native-publication-basis-v1"
    scope: ResearchScope
    actor_uid: str = Field(min_length=1)
    program_key: str = Field(min_length=1)
    job_key: Digest
    state_revision: int = Field(strict=True, gt=0)
    state_digest: Digest
    binding_digest: Digest
    pins_digest: Digest
    lease: NativeLease
    field_key: FieldKey
    field_revision: int = Field(strict=True, gt=0)
    expected_record_revision: int = Field(strict=True, ge=0)
    checkpoint_id: Digest
    checkpoint_digest: Digest
    original_typed_checkpoint_digest: Digest
    typed_checkpoint_digest: Digest
    original_scope: ResearchScope
    source_binding_digest: Digest
    reused: bool = Field(strict=True)
    history_digest: Digest | None = None
    dependencies: tuple[NativeDependencyBasis, ...] = ()
    receipts: tuple[NativeReceiptBinding, ...] = ()
    checkpoint_outbox_key: str
    checkpoint_outbox_digest: Digest
    publication_outbox_key: str
    publication_outbox_digest: Digest
    native_guard_json: str = Field(max_length=900_000)
    native_guard_digest: Digest
    idempotency_key: Digest

    @model_validator(mode="after")
    def bound_names(self):
        if (self.checkpoint_outbox_key != "checkpoint/" + self.checkpoint_id
            or self.publication_outbox_key != "publish/" + self.idempotency_key
            or self.reused != (self.history_digest is not None)
            or self.lease.job_key != self.job_key or self.lease.generation != self.scope.generation
            or self.binding_digest != self.pins_digest
            or hashlib.sha256(self.native_guard_json.encode()).hexdigest() != self.native_guard_digest):
            raise ValueError("native_publication_basis_binding_mismatch")
        return self


class PreparedNativePublication(FrozenRecord):
    publication: ResearchPublication
    basis: NativePublicationBasis

    @model_validator(mode="after")
    def single_field_binding(self):
        guard, basis = self.publication.guard, self.basis
        if len(self.publication.checkpoints) != 1:
            raise ValueError("native_publication_one_field_required")
        checkpoint = self.publication.checkpoints[0]
        if (guard.scope != basis.scope or checkpoint.scope != basis.scope
            or checkpoint.field_key != basis.field_key or checkpoint.revision != basis.field_revision
            or digest(checkpoint) != basis.typed_checkpoint_digest
            or self.publication.idempotency_key != basis.idempotency_key
            or guard.binding_digest != basis.binding_digest
            or guard.expected_record_revision != basis.expected_record_revision
            or guard.lease_owner != basis.lease.owner or guard.lease_fence != basis.lease.fence
            or guard.lease_expires_at != basis.lease.expires_at
            or dict(guard.checkpoint_revisions) != {str(basis.field_key): basis.field_revision}
            or dict(guard.checkpoint_digests) != {str(basis.field_key): basis.typed_checkpoint_digest}
            or guard.receipt_ids != tuple(item.effect_id for item in basis.receipts)
            or checkpoint.effect_receipt_ids != guard.receipt_ids
            or dict(guard.dependency_revisions) != {str(item.field_key): item.revision for item in basis.dependencies}
            or dict(guard.dependency_digests) != {str(item.field_key): item.resolution_digest for item in basis.dependencies}):
            raise ValueError("native_publication_typed_binding_mismatch")
        return self


def _principal(journal: DurableResearchJournal, scope: ResearchScope, principal: Principal) -> None:
    if (principal.user_id != journal.scope.actor_uid
        or principal.scope.organization_id != scope.organization_id
        or principal.scope.collection_id != scope.collection_id
        or principal.role not in {"operator", "reviewer", "manager", "admin"}):
        raise PermissionError("native_publication_actor_scope_denied")


def _runtime_pins(job, scope: ResearchScope) -> None:
    try:
        pins = job["pins"]
        profile = CollectionProfile.model_validate(pins["profile"])
        if (profile.organization_id != scope.organization_id or profile.collection_id != scope.collection_id
            or digest(profile) != scope.profile_digest or pins["input_digest"] != scope.input_digest
            or job["binding_digest"] != digest(pins) or pins["engine_version"] != "research_harness_v1"):
            raise ValueError("runtime scope changed")
        if set(pins["prompts"]) != {str(role) for role in ROLE_FIELDS}:
            raise ValueError("specialist roster changed")
        for role in ROLE_FIELDS:
            prompt = PromptPin.model_validate(pins["prompts"][str(role)])
            if (prompt.role != role or prompt.profile_digest != scope.profile_digest
                or prompt.source_registry_digest != pins["sources"]["registry_digest"]
                or prompt.model_route != pins["model"][str(role)]["route"]):
                raise ValueError("specialist runtime pin changed")
    except (ValueError, KeyError, TypeError):
        raise StaleWork("native_publication_runtime_pin_contract_changed") from None


def _json(data: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("native_publication_duplicate_capture_key")
            result[key] = value
        return result
    def nonfinite(_):
        raise ValueError("native_publication_nonfinite_capture_value")
    return json.loads(data, object_pairs_hook=unique, parse_constant=nonfinite)


def _receipt(effect, native_binding, field_key: FieldKey, blobs: ImmutableBlobs | None) -> NativeReceiptBinding:
    if blobs is None:
        raise PublicationUnavailable("native_publication_immutable_capture_reader_required")
    receipt = effect["receipt"]
    # A checkpoint carries every receipt of the specialist run that produced
    # it (engine.py investigate; AcceptedCheckpointProofV1 requires each of the
    # run's checkpoints to carry the run's effect_ids), and the V2 capture
    # requires all of the run's source receipts (canonical_evidence_provider_v2
    # _contexts). So a receipt recorded for a sibling field of the same
    # specialist is bound here too. A value may still cite only its own field's
    # capture evidence (evidence.validate_resolution, canonical_projection_v2
    # tool lineage). A receipt recorded for another specialist's field, or for
    # no field, is refused.
    owned = {str(key) for keys in ROLE_FIELDS.values() if field_key in keys for key in keys}
    if (effect["status"] != "completed" or receipt is None
        or not effect["field_keys"] or not set(effect["field_keys"]) <= owned
        or receipt["effect_id"] != effect["effect_id"]
        or native_binding != {"scope": effect["scope"], "binding_digest": effect["binding_digest"],
                              "attempt_id": receipt["attempt_id"], "capture": receipt["capture"]}):
        raise StaleWork("native_publication_receipt_binding_changed")
    attempts = [item for item in effect["attempts"] if item["attempt_id"] == receipt["attempt_id"]]
    if len(attempts) != 1:
        raise StaleWork("native_publication_receipt_attempt_changed")
    attempt = attempts[0]
    capture = NativeCapture.model_validate(receipt["capture"])
    raw_capture = NativeCapture.model_validate(receipt["raw_capture"]) if receipt.get("raw_capture") else None
    if (attempt["status"] != "completed" or attempt.get("capture") != capture.model_dump(mode="json")
        or attempt["capture_locator"] != capture.locator
        or (raw_capture is not None and raw_capture.locator != attempt["raw_capture_locator"])):
        raise StaleWork("native_publication_capture_lineage_changed")
    data = blobs.get(BlobRef(**capture.model_dump()))
    if len(data) != capture.byte_size or hashlib.sha256(data).hexdigest() != capture.sha256:
        raise StaleWork("native_publication_capture_checksum_changed")
    envelope = _json(data)
    expected = {"contract_version": CONTRACT_VERSION, "scope": effect["scope"],
                "effect_id": effect["effect_id"], "attempt_id": receipt["attempt_id"],
                "request_digest": effect["request_digest"], "binding_digest": effect["binding_digest"],
                "raw_capture": raw_capture.model_dump(mode="json") if raw_capture else None}
    if (set(envelope) != {*expected, "result"} or any(envelope[key] != value for key, value in expected.items())
        or canonical(envelope) != data):
        raise StaleWork("native_publication_capture_envelope_changed")
    captured = CapturedResult(**envelope["result"])
    if raw_capture:
        raw = blobs.get(BlobRef(**raw_capture.model_dump()))
        if len(raw) != raw_capture.byte_size or hashlib.sha256(raw).hexdigest() != raw_capture.sha256:
            raise StaleWork("native_publication_raw_capture_checksum_changed")
    if (captured.typed_payload != receipt["typed_payload"]
        or captured.actual_micro_usd != receipt["actual_micro_usd"]
        or captured.provider_request_id != receipt["provider_request_id"]
        or dict(captured.usage) != receipt["usage"] or captured.outcome != receipt["outcome"]):
        raise StaleWork("native_publication_captured_receipt_changed")
    return NativeReceiptBinding(effect_id=effect["effect_id"], request_digest=effect["request_digest"],
        binding_digest=effect["binding_digest"], attempt_id=receipt["attempt_id"], receipt_digest=digest(receipt),
        capture=capture, raw_capture=raw_capture)


def _native_checkpoint(job, typed: FieldCheckpoint, scope: ResearchScope):
    field = job["fields"].get(str(typed.field_key))
    if not field or field["locked"] or field["revision"] != typed.revision or not field["checkpoint"]:
        raise StaleWork("native_publication_checkpoint_revision_changed")
    native = field["checkpoint"]
    original = FieldCheckpoint.model_validate(native["payload"])
    if (original.field_key != typed.field_key or original.revision != typed.revision
        or native.get("field_key") != str(typed.field_key)
        or type(native.get("revision")) is not int or native["revision"] != typed.revision
        or native.get("retry_command_id") != original.retry_command_id
        or original.scope.sensitive != scope.sensitive
        or native["scope"] != {key: getattr(original.scope, key) for key in
            ("organization_id", "collection_id", "specimen_id", "job_id", "generation")}
        or native["id"] != digest({"scope": native["scope"], "field": str(typed.field_key),
                                  "revision": typed.revision, "payload": native["payload"]})
        or len([item for item in job["checkpoints"] if item == native]) != 1
        or tuple(native["receipt_ids"]) != typed.effect_receipt_ids
        or len(set(typed.effect_receipt_ids)) != len(typed.effect_receipt_ids)
        or native["dependencies"] != {str(pin.field_key): pin.revision for pin in typed.resolution.dependencies}
        or native.get("dependency_digests", {}) != {str(pin.field_key): pin.digest for pin in typed.resolution.dependencies}):
        raise StaleWork("native_publication_whole_checkpoint_changed")
    if original.scope == scope:
        if original != typed or typed.reused_from_checkpoint_digest is not None:
            raise StaleWork("native_publication_typed_checkpoint_changed")
    else:
        expected = FieldCheckpoint.model_validate({**original.model_dump(mode="json"),
            "scope": scope.model_dump(mode="json"), "reused_from_scope_digest": digest(original.scope),
            "reused_from_checkpoint_digest": digest(original)})
        if typed != expected:
            raise StaleWork("native_publication_reused_checkpoint_changed")
    return native, original


async def _translate(journal, scope, principal, typed, native_guard, blobs) -> PreparedNativePublication:
    _principal(journal, scope, principal)
    await asyncio.to_thread(journal._check_scope, scope)
    await asyncio.to_thread(journal.store.validate_publication, journal.scope, native_guard)
    document = await asyncio.to_thread(journal.store._read, journal.scope)
    job = journal.store._lease(document.state, journal.scope, journal.lease, document.server_time)
    _runtime_pins(job, scope)
    if native_guard["lease"] != asdict(journal.lease) or job["binding_digest"] != digest(job["pins"]):
        raise StaleWork("native_publication_lease_or_pins_changed")
    native, original = _native_checkpoint(job, typed, scope)
    loaded = {item.field_key: item for item in await journal.load(scope)}
    if loaded.get(typed.field_key) != typed:
        raise StaleWork("native_publication_typed_checkpoint_changed")
    for pin in typed.resolution.dependencies:
        source = loaded.get(pin.field_key)
        if source is None or source.revision != pin.revision or digest(source.resolution) != pin.digest:
            raise StaleWork("native_publication_dependency_checkpoint_changed")
        _native_checkpoint(job, source, scope)
    native_basis = journal.store._publication_basis(job, journal.scope, str(typed.field_key))
    guard_keys = {"scope", "lease", "binding_digest", "input_digest", "field_key", "field_revision",
                  "record_revision", "checkpoint_id", "checkpoint_digest", "receipt_ids", "dependencies",
                  "dependency_digests", "checkpoint_basis", "receipt_bindings", "canonical_commit", "idempotency_key"}
    if (set(native_guard) != guard_keys or native_guard["canonical_commit"] is not None
        or native_guard["idempotency_key"] != digest({key: value for key, value in native_guard.items() if key != "idempotency_key"})
        or native_guard["checkpoint_digest"] != digest(native) or native_guard["checkpoint_id"] != native["id"]
        or native_guard["checkpoint_basis"] != native_basis):
        raise StaleWork("native_publication_guard_changed")
    checkpoint_key = "checkpoint/" + native["id"]
    checkpoint_outbox = document.state["outbox"].get(checkpoint_key)
    publication_key = "publish/" + native_guard["idempotency_key"]
    publication_outbox = document.state["outbox"].get(publication_key)
    if (not checkpoint_outbox or set(checkpoint_outbox) != {"kind", "scope", "checkpoint_id", "delivered"}
        or checkpoint_outbox["kind"] != "field_checkpoint" or checkpoint_outbox["scope"] != native["scope"]
        or checkpoint_outbox["checkpoint_id"] != native["id"] or type(checkpoint_outbox["delivered"]) is not bool
        or publication_outbox != {"kind": "canonical_publication_required", "guard": native_guard, "delivered": False}):
        raise StaleWork("native_publication_persisted_outbox_changed")
    receipts = tuple(_receipt(document.state["effects"][effect_id], native_guard["receipt_bindings"][effect_id],
                              typed.field_key, blobs) for effect_id in typed.effect_receipt_ids)
    dependencies = tuple(NativeDependencyBasis(field_key=pin.field_key, revision=pin.revision,
        resolution_digest=pin.digest, checkpoint_id=job["fields"][str(pin.field_key)]["checkpoint"]["id"],
        checkpoint_digest=digest(job["fields"][str(pin.field_key)]["checkpoint"])) for pin in typed.resolution.dependencies)
    publication_guard = PublicationGuard(scope=scope, binding_digest=job["binding_digest"],
        lease_owner=journal.lease.owner, lease_fence=journal.lease.fence, lease_expires_at=journal.lease.expires_at,
        expected_record_revision=native_guard["record_revision"],
        checkpoint_revisions={str(typed.field_key): typed.revision}, checkpoint_digests={str(typed.field_key): digest(typed)},
        dependency_revisions={str(pin.field_key): pin.revision for pin in typed.resolution.dependencies},
        dependency_digests={str(pin.field_key): pin.digest for pin in typed.resolution.dependencies},
        receipt_ids=typed.effect_receipt_ids)
    publication = ResearchPublication(guard=publication_guard, checkpoints=(typed,),
                                      idempotency_key=native_guard["idempotency_key"])
    guard_json = canonical(native_guard).decode()
    basis = NativePublicationBasis(scope=scope, actor_uid=principal.user_id, program_key=journal.store.program_key,
        job_key=journal.scope.key, state_revision=document.revision, state_digest=digest(document.state),
        binding_digest=job["binding_digest"], pins_digest=digest(job["pins"]),
        lease=NativeLease.model_validate(asdict(journal.lease)), field_key=typed.field_key, field_revision=typed.revision,
        expected_record_revision=native_guard["record_revision"], checkpoint_id=native["id"], checkpoint_digest=digest(native),
        original_typed_checkpoint_digest=digest(original), typed_checkpoint_digest=digest(typed),
        original_scope=original.scope, source_binding_digest=native_basis["binding_digest"],
        reused=native_basis["reused"], history_digest=native_basis["history_digest"], dependencies=dependencies, receipts=receipts,
        checkpoint_outbox_key=checkpoint_key, checkpoint_outbox_digest=digest(checkpoint_outbox),
        publication_outbox_key=publication_key, publication_outbox_digest=digest(publication_outbox),
        native_guard_json=guard_json, native_guard_digest=hashlib.sha256(guard_json.encode()).hexdigest(),
        idempotency_key=native_guard["idempotency_key"])
    # Slow immutable capture reads may race another actor. The final CAS basis
    # must still be current; no expired or changed document is handed forward.
    final = await asyncio.to_thread(journal.store._read, journal.scope)
    journal.store._lease(final.state, journal.scope, journal.lease, final.server_time)
    if final.revision != document.revision or digest(final.state) != basis.state_digest:
        raise StaleWork("native_publication_state_revision_changed")
    return PreparedNativePublication(publication=publication, basis=basis)


async def prepare_native_publication(journal: DurableResearchJournal, scope: ResearchScope, field_key: FieldKey, *,
                                     principal: Principal, expected_record_revision: int,
                                     blobs: ImmutableBlobs | None = None) -> PreparedNativePublication:
    """Persist and translate a one-field authorization, never a canonical value."""
    scope = ResearchScope.model_validate(scope.model_dump(mode="json"))
    principal = Principal.model_validate(principal.model_dump(mode="json"))
    field_key = FieldKey(field_key)
    if type(expected_record_revision) is not int or expected_record_revision < 0:
        raise ValueError("native_publication_record_revision_required")
    _principal(journal, scope, principal)
    await asyncio.to_thread(journal._check_scope, scope)
    document = await asyncio.to_thread(journal.store._read, journal.scope)
    job = journal.store._lease(document.state, journal.scope, journal.lease, document.server_time)
    _runtime_pins(job, scope)
    checkpoints = await journal.load(scope)
    typed = next((item for item in checkpoints if item.field_key == field_key), None)
    if typed is None:
        raise StaleWork("native_publication_checkpoint_missing")
    document = await asyncio.to_thread(journal.store._read, journal.scope)
    job = journal.store._lease(document.state, journal.scope, journal.lease, document.server_time)
    _runtime_pins(job, scope)
    native, _ = _native_checkpoint(job, typed, scope)
    # prepare_publication is intentionally not a canonical completion method.
    # It must never reset an already delivered publication's durable entry.
    if any(item.get("kind") == "canonical_publication_required" and item.get("delivered") is True
           and item.get("guard", {}).get("checkpoint_id") == native["id"] for item in document.state["outbox"].values()):
        raise StaleWork("native_publication_already_delivered")
    native_guard = await asyncio.to_thread(journal.store.prepare_publication, journal.scope, journal.lease, str(field_key),
        expected_field_revision=typed.revision, expected_record_revision=expected_record_revision,
        receipt_ids=typed.effect_receipt_ids,
        dependencies={str(pin.field_key): pin.revision for pin in typed.resolution.dependencies})
    return await _translate(journal, scope, principal, typed, native_guard, blobs)


async def validate_native_publication(journal: DurableResearchJournal, prepared: PreparedNativePublication, *,
                                      principal: Principal, blobs: ImmutableBlobs | None = None) -> None:
    prepared = PreparedNativePublication.model_validate(prepared.model_dump(mode="json"))
    current = await _translate(journal, prepared.basis.scope, principal, prepared.publication.checkpoints[0],
                               _json(prepared.basis.native_guard_json.encode()), blobs)
    if current != prepared:
        raise StaleWork("native_publication_prepared_basis_changed")


class NativeCanonicalResearchAdapter(ABC):
    """Future owner-reviewed, compiled native adapter; no implementation installed.

    Its transaction must consume both bases, verify server actor/canonical
    specimen revision/run, and atomically write snapshot, RecordVersion,
    projection, request receipt and outbox completion. No ordinary save path.
    """

    @abstractmethod
    async def publish_native_research(self, principal: Principal, prepared: PreparedNativePublication) -> PublishedResearch:
        raise NotImplementedError


async def publish_native_publication(journal: DurableResearchJournal, prepared: PreparedNativePublication, *,
                                     principal: Principal, blobs: ImmutableBlobs | None = None,
                                     adapter: NativeCanonicalResearchAdapter | None = None) -> PublishedResearch:
    if not isinstance(adapter, NativeCanonicalResearchAdapter):
        raise PublicationUnavailable("native_canonical_research_adapter_not_admitted")
    await validate_native_publication(journal, prepared, principal=principal, blobs=blobs)
    result = await adapter.publish_native_research(principal, prepared)
    result = PublishedResearch.model_validate(result.model_dump(mode="json"))
    if (result.scope != prepared.basis.scope or result.publication_digest != digest(prepared.publication)
        or result.record_revision != prepared.basis.expected_record_revision + 1):
        raise StaleWork("native_publication_canonical_receipt_changed")
    return result
