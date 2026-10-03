"""Concrete immutable request/evidence provider for versioned native integration.

SOURCE ONLY, UNRUN. V1 capture deliberately refuses the new request envelope;
V2 consumer/schema admission is separate. Missing legacy provenance never causes
refetch, scope rebinding, a new provider charge or an invented original body.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import stat
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from specimen_digitization.application.domain import Evidence, Principal, Specimen, ToolCallRecord
from specimen_digitization.application.projection import derived_id
from specimen_digitization.application.storage import digest as canonical_digest

from .canonical_materialization import MaterializationRequestV1
from .contracts import Digest, EvidenceItem, FieldCheckpoint, FrozenRecord, LookupStatus, SourceFragment, SourceQuery, SourceResult, SpecialistRequest, digest
from .native_canonical import CanonicalBindingV1, CapturedCanonicalEvidenceV1, SqlConnectCanonicalResearchWriter
from .persistence import BlobRef, CONTRACT_VERSION, GcsImmutableBlobs, ImmutableFileBlobs
from .publication import NativeCapture, NativeReceiptBinding, PreparedNativePublication
from .source_capture_v2 import (
    CAPTURE_VERSION, MAX_ENVELOPE_BYTES, OPERATION_PREFIX, CaptureSourceBrokerV2,
    CapturedTransportResponseV2, RegisteredCapturePolicyV2, SourceRequestEnvelopeV2,
    logical_request_v2, tool_receipt_v2, typed, unavailable,
)
from .sources import canonical_json, result_envelope, validate_destination

MAX_NATIVE_INPUT_BINDINGS = 128
MAX_NATIVE_INPUT_BYTES = 64_000_000


def strict_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                unavailable("source_capture_duplicate_member")
            result[key] = value
        return result
    def nonfinite(_):
        unavailable("source_capture_nonfinite_value")
    try:
        value = json.loads(data, object_pairs_hook=unique, parse_constant=nonfinite)
    except (ValueError, TypeError, UnicodeError):
        unavailable()
    if canonical_json(value).encode() != data:
        unavailable("source_capture_noncanonical_envelope")
    return value


class NativeInputBindingV2(FrozenRecord):
    observation_id: UUID
    input_ref: str = Field(min_length=1)
    input_sha256: Digest
    input_generation: str = Field(min_length=1)
    input_origin: Literal["native_original_asset", "native_region_crop"]
    raw_ref: str = Field(min_length=1)
    raw_sha256: Digest
    raw_generation: str = Field(min_length=1)
    observation_digest: Digest
    request_sha256: Digest | None


class ToolInputLineageV2(FrozenRecord):
    """Actual input shape, including honest empty and mixed reading inputs.

    This is a proposed versioned native ABI, not an installed ToolCallV1 row.
    The original request envelope remains the authority for its fragments.
    """
    contract_version: Literal["research-tool-input-lineage/v2"] = "research-tool-input-lineage/v2"
    original_request_digest: Digest
    query_digest: Digest
    canonical_run_id: UUID
    fragments: tuple[SourceFragment, ...]
    observation_ids: tuple[UUID, ...]
    region_ids: tuple[UUID, ...]
    input_sources: tuple[Literal["raw_reading", "decided_transcript"], ...]
    native_inputs: tuple[NativeInputBindingV2, ...] = Field(max_length=MAX_NATIVE_INPUT_BINDINGS)
    selected_observation_id: UUID | None

    @model_validator(mode="after")
    def exact_input_shape(self):
        if (tuple(dict.fromkeys(str(row.observation_id) for row in self.fragments)) != tuple(str(value) for value in self.observation_ids)
            or tuple(dict.fromkeys(str(row.region_id) for row in self.fragments)) != tuple(str(value) for value in self.region_ids)
            or tuple(dict.fromkeys(row.input_source for row in self.fragments)) != self.input_sources
            or tuple(row.observation_id for row in self.native_inputs) != self.observation_ids
            or self.selected_observation_id is not None and self.selected_observation_id not in self.observation_ids):
            raise ValueError("canonical_tool_input_lineage_changed")
        return self


class CanonicalCaptureContextV2(FrozenRecord):
    """Runtime proof from original captured inputs and the actual native graph.

    No adaptive request/query digest requires advance owner registration.
    The stable source-mapping rule authorizes this verifier, never its result.
    """
    request_digest: Digest
    query_digest: Digest
    canonical_run_id: UUID
    asset_id: str = Field(min_length=1)
    region_id: str | None
    observation_ids: tuple[UUID, ...]
    input_source: Literal["raw_reading", "decided_transcript"] | None
    selected_observation_id: UUID | None
    canonical_source: str = Field(min_length=1)
    evidence_id_rule: Literal["research-canonical-evidence/v1"]
    tool_input_lineage: ToolInputLineageV2


class VerifiedSourceCaptureV2(FrozenRecord):
    """Four distinct identities, all proven; raw_capture is never rebound."""
    contract_version: Literal["source-capture-proof/v2"] = "source-capture-proof/v2"
    receipt: NativeReceiptBinding
    semantic_capture: NativeCapture
    request_envelope: NativeCapture
    selected_response: CapturedTransportResponseV2
    original_request: SpecialistRequest
    query_digest: Digest
    capture_policy_digest: Digest
    original_response_fingerprint: Digest
    canonical_copy_ref: str = Field(min_length=1)
    canonical_copy_sha256: Digest
    canonical_copy_generation: str = Field(min_length=1)
    canonical_copy_byte_size: int = Field(strict=True, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def distinct_capture_bindings(self):
        if (self.semantic_capture != self.receipt.capture or self.request_envelope != self.receipt.raw_capture
            or self.original_response_fingerprint != self.selected_response.response_fingerprint
            or self.original_response_fingerprint != self.selected_response.body.sha256
            or self.canonical_copy_sha256 != self.original_response_fingerprint
            or self.canonical_copy_byte_size != self.selected_response.body.byte_size):
            raise ValueError("canonical_source_v2_proof_changed")
        return self


class CapturedToolExecutionV2(FrozenRecord):
    """Actual durable attempt metadata, even when no V1 input fits."""
    contract_version: Literal["research-tool-execution/v2"] = "research-tool-execution/v2"
    effect_id: Digest
    attempt_id: str = Field(min_length=1)
    tool_id: Literal["source_lookup"] = "source_lookup"
    tool_version: Literal["research-source-request-envelope/v2"] = CAPTURE_VERSION
    source: str = Field(min_length=1)
    field_keys: tuple[str, ...] = Field(min_length=1, max_length=1)
    arguments: SourceQuery
    outcome: LookupStatus
    response_fingerprint: Digest
    evidence_id: UUID
    started_at: str = Field(min_length=1)
    completed_at: str = Field(min_length=1)


class CapturedCanonicalEvidenceV2(FrozenRecord):
    contract_version: Literal["captured-canonical-evidence/v2"] = "captured-canonical-evidence/v2"
    origin: Literal["captured_source_result"] = "captured_source_result"
    evidence: EvidenceItem
    canonical_evidence: Evidence
    canonical_producer: ToolCallRecord | None
    tool_input_lineage: ToolInputLineageV2
    tool_execution: CapturedToolExecutionV2
    source_policy_digest: Digest
    source_registry_digest: Digest
    canonical_mapping_digest: Digest
    canonical_run_id: UUID
    canonical_region_id: str | None
    canonical_observation_ids: tuple[UUID, ...]
    original_specialist_request: SpecialistRequest
    source_result: SourceResult
    proof: VerifiedSourceCaptureV2

    @model_validator(mode="after")
    def actual_producer_context(self):
        lineage, producer, execution = self.tool_input_lineage, self.canonical_producer, self.tool_execution
        # A single-source lineage always has its producer. A mixed one (the
        # decided transcript and the raw readings of a two-reader region) has
        # one when the value's own grounding names a single input source.
        representable = bool(lineage.observation_ids) and len(lineage.input_sources) == 1
        if ((producer is None if representable else producer is not None and not lineage.observation_ids)
            or lineage.original_request_digest != digest(self.original_specialist_request)
            or lineage.query_digest != self.proof.query_digest
            or lineage.query_digest != digest(execution.arguments)
            or self.proof.original_request != self.original_specialist_request
            or execution.effect_id != self.proof.receipt.effect_id or execution.attempt_id != self.proof.receipt.attempt_id
            or execution.response_fingerprint != self.evidence.response_digest
            or execution.arguments.source_id != self.evidence.source_id
            or execution.outcome != self.source_result.status
            or str(execution.evidence_id) != self.canonical_evidence.id
            or self.canonical_evidence.raw_ref != self.proof.canonical_copy_ref
            or self.canonical_evidence.digest != self.proof.canonical_copy_sha256
            or self.source_result.receipt is not None
            or self.evidence not in self.source_result.evidence):
            raise ValueError("canonical_v2_producer_context_changed")
        if producer is not None and (producer.input_source not in lineage.input_sources
            or producer.evidence_id != self.canonical_evidence.id
            or producer.arguments != execution.arguments.model_dump(mode="json")
            or producer.started_at != execution.started_at or producer.completed_at != execution.completed_at):
            raise ValueError("canonical_v1_producer_context_changed")
        return self


class _BoundedCaptureSinkV3(io.BytesIO):
    """Stop before copying any transport bytes beyond the admitted body size."""
    def __init__(self, limit):
        super().__init__()
        self.limit, self.bytes_written = limit, 0

    def write(self, data):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise ValueError("Retained capture stream requires bytes")
        if self.bytes_written + memoryview(data).nbytes > self.limit:
            raise ValueError("Retained capture exceeds admitted size")
        result = super().write(data)
        self.bytes_written += result
        return result


class BoundedImmutableCaptureReaderV3:
    """Explicit adapters for the named local and production immutable stores.

    Never invokes their unbounded get/discover methods. GCS requires the pinned
    official SDK's raw, non-single-shot stream behavior; it remains UNRUN here.
    Its bounded sink also rejects a response that exceeds the requested range.
    """
    def __init__(self, store):
        if type(store) not in {ImmutableFileBlobs, GcsImmutableBlobs}:
            unavailable("canonical_capture_bounded_reader_unavailable")
        self.store = store

    @classmethod
    def from_store(cls, store):
        return store if type(store) is cls else cls(store)

    @staticmethod
    def _reference(reference, max_bytes):
        if (type(max_bytes) is not int or max_bytes < 0
            or type(reference.byte_size) is not int or reference.byte_size < 0 or reference.byte_size > max_bytes
            or type(reference.locator) is not str or not reference.locator
            or type(reference.generation) is not str or not reference.generation.isascii()
            or not reference.generation.isdecimal() or str(int(reference.generation)) != reference.generation
            or int(reference.generation) < 1
            or type(reference.sha256) is not str or len(reference.sha256) != 64
            or any(char not in "0123456789abcdef" for char in reference.sha256)):
            raise ValueError("Invalid bounded immutable reference")

    @staticmethod
    def _verified(reference, data):
        if len(data) != reference.byte_size or hashlib.sha256(data).hexdigest() != reference.sha256:
            raise ValueError("Retained capture generation/checksum changed")
        return data

    def get_bounded(self, reference: BlobRef, *, max_bytes: int) -> bytes:
        self._reference(reference, max_bytes)
        if type(self.store) is ImmutableFileBlobs:
            return self._file(reference, max_bytes)
        return self._gcs(reference, max_bytes)

    def _file(self, reference, max_bytes):
        if reference.generation != "1" or not hasattr(os, "O_NOFOLLOW"):
            raise ValueError("Bounded local generation is unavailable")
        fd = os.open(self.store._path(reference.locator), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_size != reference.byte_size
                or before.st_size > max_bytes):
                raise ValueError("Retained local capture size changed")
            # One sentinel byte detects growth; no Path.read_bytes or unbounded get.
            data = os.read(fd, reference.byte_size + 1)
            after = os.fstat(fd)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError("Retained local capture changed during bounded read")
            return self._verified(reference, data)
        finally:
            os.close(fd)

    def _gcs(self, reference, max_bytes):
        if type(self.store.maximum_bytes) is not int or self.store.maximum_bytes < 1:
            raise ValueError("Bounded GCS store limit is unavailable")
        limit = min(max_bytes, self.store.maximum_bytes)
        if reference.byte_size > limit:
            raise ValueError("Retained GCS capture exceeds configured bound")
        generation = int(reference.generation)
        try:
            blob = self.store._blob(reference.locator, reference.generation)
            blob.reload(if_generation_match=generation, timeout=30, retry=None)
            if (str(blob.generation) != reference.generation or type(blob.size) is not int
                or blob.size != reference.byte_size or blob.size > limit
                or not isinstance(blob.metadata, dict) or blob.metadata.get("sha256") != reference.sha256):
                raise ValueError("Fresh retained GCS generation/size/checksum metadata changed")
            if reference.byte_size == 0:
                return self._verified(reference, b"")
            # None selects RawDownload streaming rather than ChunkedDownload;
            # raw_download disables decompression and single_shot=False avoids
            # response.raw.read() of the whole body. SDK/header behavior is a
            # separately pinned qualification dependency, not inferred here.
            blob.chunk_size = None
            with _BoundedCaptureSinkV3(reference.byte_size) as sink:
                blob.download_to_file(sink, start=0, end=reference.byte_size,
                    raw_download=True, if_generation_match=generation, checksum="crc32c",
                    timeout=30, retry=None, single_shot_download=False)
                if str(blob.generation) != reference.generation:
                    raise ValueError("Retained GCS response generation changed")
                return self._verified(reference, sink.getvalue())
        except Exception:
            # Preserve no provider/body/error content in the operational failure.
            raise ValueError("Bounded retained GCS read unavailable") from None


class CanonicalEvidenceProviderV2:
    """Reads genuine saved effects/bodies, then copies permitted bytes once.

    Source blobs are the DurableEffectBroker's immutable generation reader.
    Canonical blobs are the existing repository's immutable BlobStore. This
    object does not initialize budgets/jobs or create leases/provider requests.
    """
    def __init__(self, source_blobs, canonical_blobs, registry, asset_locator):
        if (source_blobs is None or canonical_blobs is None or not callable(asset_locator)
            or not callable(getattr(canonical_blobs, "get_bounded", None))):
            unavailable("canonical_capture_blob_origins_unavailable")
        self.source_blobs, self.canonical_blobs = source_blobs, canonical_blobs
        self.source_reader = BoundedImmutableCaptureReaderV3.from_store(source_blobs)
        self.registry, self.asset_locator = registry, asset_locator

    @classmethod
    def from_service(cls, repository, effect_broker, registry):
        return cls(effect_broker.blobs, repository.graph_blobs, registry, repository.locate)

    @staticmethod
    def _authority(principal, prepared, binding):
        if (principal.user_id != prepared.basis.actor_uid or principal.role not in {"operator", "reviewer", "manager", "admin"}
            or str(binding.organization_id) != principal.scope.organization_id
            or str(binding.collection_id) != principal.scope.collection_id
            or str(binding.specimen_id) != prepared.basis.scope.specimen_id
            or principal.scope.organization_id != prepared.basis.scope.organization_id
            or principal.scope.collection_id != prepared.basis.scope.collection_id
            or binding.registration.job_id != prepared.basis.scope.job_id
            or binding.registration.generation != prepared.basis.scope.generation
            or binding.registration.runtime_binding_digest != prepared.basis.binding_digest
            or binding.registration.job_key != prepared.basis.job_key
            or binding.registration.program_key != prepared.basis.program_key
            or binding.registration.input_digest != prepared.basis.scope.input_digest
            or binding.registration.profile_digest != prepared.basis.scope.profile_digest
            or digest(binding.registration.job["pins"]) != prepared.basis.binding_digest
            or binding.registration.read_bundle["job"] != binding.registration.job
            or binding.sensitive or prepared.basis.scope.sensitive):
            raise PermissionError("canonical_capture_actor_scope_denied")
        if binding.registration.read_bundle["hold_reasons"] or binding.registration.read_bundle["halted"] or binding.registration.read_bundle["paused"]:
            unavailable("canonical_capture_operational_hold")
        job, basis = binding.registration.job, prepared.basis
        field = job["fields"].get(str(basis.field_key))
        native = field.get("checkpoint") if isinstance(field, dict) else None
        if (job.get("lease") != basis.lease.model_dump(mode="json")
            or basis.lease.expires_at <= binding.registration.read_bundle["server_time"]
            or binding.registration.read_bundle["state_revision"] != basis.state_revision
            or field is None or field.get("locked") is not False
            or type(field.get("revision")) is not int or field["revision"] != basis.field_revision
            or binding.registration.human_locks.get(binding.registration.field_mapping[str(basis.field_key)]) is not False
            or not isinstance(native, dict) or native.get("id") != basis.checkpoint_id
            or digest(native) != basis.checkpoint_digest):
            unavailable("canonical_capture_checkpoint_or_lease_stale")
        from .native_canonical_v2 import CanonicalBindingV2
        if isinstance(binding, CanonicalBindingV2):
            from .publication import _native_checkpoint
            original = _native_checkpoint(job, prepared.publication.checkpoints[0], basis.scope)[1].scope
        else:
            original = SqlConnectCanonicalResearchWriter._capture_lineage(prepared, binding)[0]
        checkpoint = typed(FieldCheckpoint, native["payload"])
        if checkpoint.scope != original or digest(checkpoint) != basis.original_typed_checkpoint_digest:
            unavailable("canonical_capture_original_checkpoint_changed")
        return original

    async def _bytes(self, capture, limit):
        if capture.byte_size > limit:
            unavailable("canonical_capture_bound_changed")
        try:
            data = await asyncio.to_thread(self.source_reader.get_bounded,
                BlobRef(**capture.model_dump()), max_bytes=limit)
        except (ValueError, KeyError, OSError):
            unavailable("canonical_capture_immutable_read_unavailable")
        if len(data) != capture.byte_size or hashlib.sha256(data).hexdigest() != capture.sha256:
            unavailable("canonical_capture_generation_checksum_changed")
        return data

    async def _contexts(self, principal, prepared, binding, *, accepted_original=None):
        original_scope = self._authority(principal, prepared, binding)
        checkpoint = prepared.publication.checkpoints[0]
        effects = binding.registration.read_bundle["effects"]
        contexts = []
        original = accepted_original.request if accepted_original is not None else None
        identity = {key: getattr(original_scope, key) for key in ("organization_id", "collection_id", "specimen_id", "job_id", "generation")}
        for receipt in prepared.basis.receipts:
            effect = effects.get(receipt.effect_id)
            if not isinstance(effect, dict):
                unavailable("canonical_capture_effect_unavailable")
            if not str(effect.get("operation_key", "")).startswith(OPERATION_PREFIX):
                continue  # Native admission owns model effects/costs, not this source reader.
            saved = effect.get("receipt")
            if (strict_effect_scope_v2(effect.get("scope")) != identity
                or effect.get("status") != "completed" or not isinstance(saved, dict)
                or type(saved.get("actual_micro_usd")) is not int or saved["actual_micro_usd"] < 0
                or type(effect.get("actual_micro_usd")) is not int or effect["actual_micro_usd"] < 0
                or type(saved.get("held_micro_usd")) is not int or saved["held_micro_usd"] != 0
                or type(effect.get("held_micro_usd")) is not int or effect["held_micro_usd"] != 0):
                unavailable("canonical_capture_effect_cost_unreconciled")
            if (effect.get("scope") != identity or effect.get("job_key") != prepared.basis.job_key
                or effect.get("status") != "completed" or not isinstance(saved, dict)
                or digest(saved) != receipt.receipt_digest or saved.get("effect_id") != receipt.effect_id
                or effect.get("request_digest") != receipt.request_digest
                or effect.get("binding_digest") != receipt.binding_digest
                or receipt.binding_digest != prepared.basis.source_binding_digest
                or saved.get("capture") != receipt.capture.model_dump(mode="json")
                or receipt.raw_capture is None or saved.get("raw_capture") != receipt.raw_capture.model_dump(mode="json")):
                unavailable("canonical_capture_receipt_changed")
            attempts = [item for item in effect.get("attempts", []) if item.get("attempt_id") == receipt.attempt_id]
            if (len(attempts) != 1 or attempts[0].get("status") != "completed"
                or attempts[0].get("capture_locator") != receipt.capture.locator
                or attempts[0].get("raw_capture_locator") != receipt.raw_capture.locator
                or attempts[0].get("capture") != saved["capture"] or saved.get("attempt_id") != receipt.attempt_id):
                unavailable("canonical_capture_attempt_changed")
            semantic = strict_json(await self._bytes(receipt.capture, 8_000_000))
            expected = {"contract_version": CONTRACT_VERSION, "scope": identity, "effect_id": receipt.effect_id,
                "attempt_id": receipt.attempt_id, "request_digest": receipt.request_digest,
                "binding_digest": receipt.binding_digest, "raw_capture": receipt.raw_capture.model_dump(mode="json")}
            if not isinstance(semantic, dict) or set(semantic) != {*expected, "result"} or any(semantic[key] != value for key, value in expected.items()):
                unavailable("canonical_capture_semantic_binding_changed")
            captured = semantic["result"]
            if (not isinstance(captured, dict) or captured.get("raw_payload") is not None
                or any(captured.get(key) != saved.get(key) for key in ("typed_payload", "actual_micro_usd", "provider_request_id", "usage", "outcome"))):
                unavailable("canonical_capture_saved_result_changed")
            envelope = typed(SourceRequestEnvelopeV2, strict_json(await self._bytes(receipt.raw_capture, MAX_ENVELOPE_BYTES)))
            request, query, policy = envelope.original_request, envelope.query, envelope.policy
            source_policy = self.registry.get(query.source_id)
            policy_pin = binding.registration.job["pins"]["sources"].get("capture_policies", {}).get(query.source_id)
            if (request.scope != original_scope or checkpoint.field_key not in request.field_keys
                or (query.field_key not in request.field_keys if accepted_original is not None
                    else query.field_key != checkpoint.field_key) or envelope.effect_id != receipt.effect_id
                or envelope.attempt_id != receipt.attempt_id or envelope.binding_digest != receipt.binding_digest
                or request.prompt.digest != checkpoint.prompt_digest
                or request.prompt.source_registry_digest != checkpoint.source_registry_digest
                or self.registry.digest != checkpoint.source_registry_digest
                or digest(source_policy) != policy.source_policy_digest or not source_policy.ready
                or source_policy.paid or source_policy.credentials_required
                or binding.registration.job["pins"]["prompts"].get(str(request.role)) != request.prompt.model_dump(mode="json")
                or policy_pin != policy.model_dump(mode="json")
                or effect.get("operation_key") != OPERATION_PREFIX + digest(envelope.logical_request)
                or receipt.request_digest != digest(envelope.logical_request)
                or envelope.logical_request != logical_request_v2(request, query, policy)):
                unavailable("canonical_capture_original_request_changed")
            if query.join is not None and binding.registration.job["pins"]["sources"].get("exact_specimen_joins", {}).get(query.source_id) != query.join.model_dump(mode="json"):
                unavailable("canonical_capture_specimen_join_changed")
            if original is not None and original != request:
                unavailable("canonical_capture_original_requests_disagree")
            original = request
            result = typed(SourceResult, captured["typed_payload"])
            if (result.coverage.source_id != query.source_id or result.coverage.field_key != query.field_key
                or result.coverage.qualification_digest != policy.source_policy_digest
                or result.receipt is not None
                or hashlib.sha256(result_envelope(result).encode()).hexdigest() != envelope.semantic_result_digest):
                unavailable("canonical_capture_source_result_changed")
            enriched = result.model_copy(update={"receipt": tool_receipt_v2(request, query, effect, result)})
            contexts.append((receipt, effect, envelope, enriched))
        if original is None:
            unavailable("canonical_original_request_envelope_unavailable")
        if accepted_original is not None:
            recovered = tuple(item[3] for item in contexts)
            from .local_utility_proof_v2 import local_utility_replays_v2
            local_utility_replays_v2(original, accepted_original.tool_results,
                accepted_checkpoint_proof=accepted_original.accepted_checkpoint_proof)
            accepted_tools = tuple(tool for tool in accepted_original.tool_results if tool.receipt is not None)
            if (len(recovered) != len(accepted_tools) or any(
                    len([row for row in recovered if row == tool]) != 1 for tool in accepted_tools)):
                unavailable("canonical_capture_accepted_source_results_changed")
        return original, contexts

    async def read(self, principal, prepared, binding):
        request, contexts = await self._contexts(principal, prepared, binding)
        return MaterializationRequestV1(digest(prepared), binding.canonical.snapshot_sha256,
            request, tuple(item[3] for item in contexts), None)

    async def capture(self, principal, prepared, binding, prior):
        """Native V1 interface: do not reinterpret request envelope as rawbody."""
        await self._contexts(principal, prepared, binding)
        unavailable("canonical_source_capture_v2_requires_native_v2")

    async def capture_v2(self, principal: Principal, prepared: PreparedNativePublication,
                         binding: CanonicalBindingV1, prior: Specimen):
        request, contexts = await self._contexts(principal, prepared, binding)
        return await self._capture_contexts(principal, prepared, binding, prior, request, contexts,
            native_verified=False)

    async def capture_native_v2(self, principal, prepared, binding, prior, *, native_inputs,
            accepted_checkpoint_proofs, projection_services, active_graph_bytes=None):
        from .native_materialization_context_v2 import native_acceptance_context_v2
        context, accepted = native_acceptance_context_v2(native_inputs=native_inputs, binding=binding,
            prepared=prepared, prior=prior, accepted_checkpoint_proofs=accepted_checkpoint_proofs,
            active_graph_bytes=active_graph_bytes)
        request, contexts = await self._contexts(principal, prepared, binding, accepted_original=accepted)
        return await self._capture_contexts(principal, prepared, binding, prior, request, contexts,
            native_verified=True)

    async def read_v2(self, principal, prepared, binding, prior, prior_projection, *, bundle=None):
        from .native_materialization_context_v2 import NativeMaterializationInputBundleV2, canonical_prior_projection_v2
        if (not isinstance(bundle, NativeMaterializationInputBundleV2)
                or bundle.target.prepared_digest != digest(prepared)
                or bundle.target.lineage_context.prior_projection != canonical_prior_projection_v2(
                    prior_projection, binding.canonical.record_version_id)):
            unavailable("canonical_v2_native_bundle_required")
        self._authority(principal, prepared, binding)
        return bundle.target

    async def prepare_native_context(self, bundle, *, checkpoint):
        from .native_materialization_context_v2 import NativeMaterializationInputBundleV2
        if not isinstance(bundle, NativeMaterializationInputBundleV2):
            unavailable("canonical_v2_native_bundle_required")
        proof = bundle.original_request_proofs.get(str(checkpoint.field_key))
        if proof is None:
            unavailable("canonical_accepted_checkpoint_proof_unavailable")
        return proof

    async def _capture_contexts(self, principal, prepared, binding, prior, request, contexts, *, native_verified):
        reg = binding.registration
        if (prior.id != str(binding.specimen_id) or prior.scope != principal.scope
            or prior.run.id != str(binding.canonical.canonical_run_id)
            or prior.version != binding.canonical.record_revision
            or prior.asset.sha256 != reg.source_sha256
            or canonical_digest(prior.run.profile_snapshot) != reg.canonical_profile_digest
            or not native_verified and canonical_digest(prior.model_dump(mode="json")) != binding.canonical.snapshot_sha256):
            unavailable("canonical_capture_prior_snapshot_changed")
        checkpoint = prepared.publication.checkpoints[0]
        expected = set(checkpoint.resolution.evidence_ids) | set(checkpoint.resolution.value.evidence_ids)
        found = {}
        # A retained native evidence row may support a no-tool reading. The
        # accepted request must name the same native ID and body facts; presence
        # of a similar excerpt or URL never authorizes a mapping.
        if native_verified:
            for evidence in request.evidence:
                if evidence.id not in expected:
                    continue
                matches = [row for row in prior.run.evidence if row.id == evidence.id
                    and (row.digest or digest(row)) == evidence.response_digest
                    and (row.locator or "native-evidence:" + row.id) == evidence.locator
                    and row.excerpt == evidence.excerpt and (row.source or "native_evidence") == evidence.source_id
                    and evidence.source_version == "native-evidence-adapter/v1"
                    and evidence.publisher_assertion_id == digest(row)]
                if len(matches) != 1:
                    continue
                canonical = matches[0]
                found[evidence.id] = CapturedCanonicalEvidenceV1(origin="existing_canonical",
                    evidence=evidence, canonical_evidence=canonical.model_copy(deep=True),
                    canonical_producer=None, receipt=None, source_policy_digest=digest({
                        "contract_version":"native-existing-evidence/v2", "evidence":canonical.model_dump(mode="json")}),
                    source_registry_digest=checkpoint.source_registry_digest,
                    canonical_mapping_digest=reg.semantic_mapping_digest,
                    canonical_run_id=binding.canonical.canonical_run_id,
                    canonical_region_id=canonical.region_id,
                    canonical_observation_ids=tuple(UUID(value) for value in canonical.observation_ids))
        try:
            asset = self.asset_locator(prior.asset.blob_ref)
        except (ValueError, LookupError, OSError):
            unavailable("canonical_capture_asset_generation_unavailable")
        if not isinstance(asset.generation, str) or not asset.generation:
            unavailable("canonical_capture_asset_generation_unavailable")
        native_inputs = await self._native_inputs(request, prior)
        for receipt, effect, envelope, result in contexts:
            source_mapping = reg.semantic_mapping.get("evidence_sources", {}).get(envelope.query.source_id)
            if (not isinstance(source_mapping, dict) or source_mapping.get("policy_digest") != envelope.policy.source_policy_digest
                or type(source_mapping.get("canonical_source")) is not str or not source_mapping["canonical_source"]
                or source_mapping.get("input_context_rule") != "exact_original_request_fragments/v2"
                or source_mapping.get("evidence_id_rule") != "research-canonical-evidence/v1"):
                unavailable("canonical_capture_native_context_unproved")
            context = native_input_context_v2(request, envelope.query, checkpoint.resolution, prior, source_mapping,
                asset_generation=asset.generation, native_inputs=native_inputs)
            source_policy = self.registry.get(envelope.query.source_id)
            for evidence in result.evidence:
                if evidence.id not in expected:
                    continue
                if evidence.id in found:
                    unavailable("canonical_capture_evidence_ambiguous")
                selected = [row for row in envelope.responses if row.response_fingerprint == evidence.response_digest and row.url == evidence.locator]
                if len(selected) != 1:
                    unavailable("canonical_capture_response_selection_unproved")
                selected = selected[0]
                if envelope.policy.kind != "full_response":
                    unavailable("canonical_policy_minimal_source_adapter_unqualified")
                validate_destination(source_policy, selected.url)
                body = await self._bytes(selected.body, source_policy.max_response_bytes)
                canonical_ref = await asyncio.to_thread(self.canonical_blobs.put, body)
                copied = await asyncio.to_thread(self.canonical_blobs.get_bounded, canonical_ref, source_policy.max_response_bytes)
                if copied != body:
                    unavailable("canonical_capture_body_copy_unproved")
                identifier = derived_id(context.evidence_id_rule, request.scope.organization_id,
                    request.scope.collection_id, request.scope.specimen_id, prior.run.id,
                    evidence.id, receipt.effect_id, evidence.response_digest)
                canonical_evidence = Evidence(id=identifier, kind="lookup", asset_id=prior.asset.id,
                    region_id=context.region_id, observation_ids=[str(value) for value in context.observation_ids],
                    source=context.canonical_source, locator=evidence.locator if str(result.status) == "success" else None,
                    excerpt="\n".join(result.candidate_json), raw_ref=canonical_ref,
                    digest=evidence.response_digest, created_at=evidence.retrieved_at)
                attempt = next(item for item in effect["attempts"] if item["attempt_id"] == receipt.attempt_id)
                def timestamp(key):
                    value = attempt.get(key)
                    if type(value) not in {int, float}:
                        unavailable("canonical_capture_attempt_time_unproved")
                    try:
                        return datetime.fromtimestamp(value, timezone.utc).isoformat()
                    except (OverflowError, ValueError, OSError):
                        unavailable("canonical_capture_attempt_time_unproved")
                execution = CapturedToolExecutionV2(effect_id=receipt.effect_id, attempt_id=receipt.attempt_id,
                    source=context.canonical_source, field_keys=(reg.field_mapping[str(envelope.query.field_key)],),
                    arguments=envelope.query, outcome=result.status, response_fingerprint=evidence.response_digest,
                    evidence_id=identifier, started_at=timestamp("sent_at"), completed_at=timestamp("completed_at"))
                producer = None
                if context.input_source is not None:
                    producer = ToolCallRecord(call_key=digest({"effect_id": receipt.effect_id, "evidence_id": evidence.id}),
                        phase="lookup", tool="source_lookup", tool_version=CAPTURE_VERSION, source=context.canonical_source,
                        field_keys=[reg.field_mapping[str(envelope.query.field_key)]], input_source=context.input_source,
                        region_id=context.region_id, observation_id=str(context.selected_observation_id) if context.selected_observation_id else None,
                        attempt=effect["attempts"].index(attempt) + 1, arguments=envelope.query.model_dump(mode="json"),
                        outcome=result.status, result={"capture_contract": CAPTURE_VERSION, "response_fingerprint": evidence.response_digest},
                        evidence_id=identifier, started_at=execution.started_at, completed_at=execution.completed_at)
                proof = VerifiedSourceCaptureV2(receipt=receipt, semantic_capture=receipt.capture,
                    request_envelope=receipt.raw_capture, selected_response=selected, original_request=request,
                    query_digest=digest(envelope.query), capture_policy_digest=digest(envelope.policy),
                    original_response_fingerprint=evidence.response_digest, canonical_copy_ref=canonical_ref,
                    canonical_copy_sha256=hashlib.sha256(copied).hexdigest(),
                    canonical_copy_generation=self.asset_locator(canonical_ref).generation, canonical_copy_byte_size=len(copied))
                found[evidence.id] = CapturedCanonicalEvidenceV2(evidence=evidence, canonical_evidence=canonical_evidence,
                    canonical_producer=producer, tool_input_lineage=context.tool_input_lineage,
                    tool_execution=execution,
                    source_policy_digest=envelope.policy.source_policy_digest,
                    source_registry_digest=checkpoint.source_registry_digest, canonical_mapping_digest=reg.semantic_mapping_digest,
                    canonical_run_id=context.canonical_run_id, canonical_region_id=context.region_id,
                    canonical_observation_ids=context.observation_ids, original_specialist_request=request,
                    source_result=result.model_copy(update={"receipt":None}), proof=proof)
        if set(found) != expected:
            unavailable("canonical_capture_missing_actual_evidence")
        return tuple(found[identifier] for identifier in sorted(found))

    async def _native_inputs(self, request, prior):
        """Verify retained input/raw blobs selected by actual native reading IDs.

        This reads existing canonical objects, never refetches source responses.
        Missing legacy crop provenance fails closed without inventing an input.
        """
        observations = {row.id: row for row in prior.run.observations}
        regions = {row.id: row for row in prior.run.regions}
        if len(observations) != len(prior.run.observations) or len(regions) != len(prior.run.regions):
            unavailable("canonical_capture_native_input_identity_ambiguous")
        verified, retained, read_bytes = {}, {}, 0
        async def retained_fingerprint(ref, limit):
            nonlocal read_bytes
            if ref in retained:
                fingerprint, size = retained[ref]
                if size > limit:
                    unavailable("canonical_capture_native_input_bound_changed")
                return fingerprint
            if read_bytes >= MAX_NATIVE_INPUT_BYTES:
                unavailable("canonical_capture_native_input_total_bound")
            data = await asyncio.to_thread(self.canonical_blobs.get_bounded, ref,
                min(limit, MAX_NATIVE_INPUT_BYTES - read_bytes))
            read_bytes += len(data)
            fingerprint = hashlib.sha256(data).hexdigest()
            retained[ref] = fingerprint, len(data)
            return fingerprint
        for fragment in request.fragments:
            if fragment.observation_id in verified:
                continue
            if len(verified) >= MAX_NATIVE_INPUT_BINDINGS:
                unavailable("canonical_capture_native_input_count_bound")
            reading = observations.get(fragment.observation_id)
            region = regions.get(fragment.region_id)
            if reading is None or region is None or region.asset_id != prior.asset.id or reading.region_id != region.id:
                unavailable("canonical_capture_native_input_unavailable")
            if reading.input_asset_id is not None and reading.input_asset_id != prior.asset.id:
                unavailable("canonical_capture_native_asset_unproved")
            # A checksum proves bytes, never an input object or its generation.
            # Honor the actual declared crop even when its bytes equal the asset.
            if reading.input_crop_ref is not None:
                if not reading.input_crop_ref or reading.input_crop_ref != region.crop_ref:
                    unavailable("canonical_capture_native_crop_unproved")
                input_ref, origin = reading.input_crop_ref, "native_region_crop"
            elif (reading.input_asset_id == prior.asset.id
                    and reading.input_sha256 == prior.asset.sha256 and region.crop_ref is None):
                input_ref, origin = prior.asset.blob_ref, "native_original_asset"
            else:
                # Legacy/ambiguous crop identity cannot be recovered from SHA.
                unavailable("canonical_capture_native_input_origin_unproved")
            try:
                input_blob, raw_blob = self.asset_locator(input_ref), self.asset_locator(reading.raw_ref)
                input_fingerprint = await retained_fingerprint(input_ref, 25_000_000)
                raw_fingerprint = await retained_fingerprint(reading.raw_ref, 8_000_000)
            except (ValueError, LookupError, OSError):
                unavailable("canonical_capture_native_input_read_unavailable")
            if input_fingerprint != reading.input_sha256 or raw_fingerprint != reading.raw_sha256:
                unavailable("canonical_capture_native_input_checksum_changed")
            verified[reading.id] = NativeInputBindingV2(observation_id=reading.id, input_ref=input_ref,
                input_sha256=reading.input_sha256, input_generation=input_blob.generation, input_origin=origin,
                raw_ref=reading.raw_ref, raw_sha256=reading.raw_sha256, raw_generation=raw_blob.generation,
                observation_digest=canonical_digest(reading.model_dump(mode="json")), request_sha256=reading.request_sha256)
        return tuple(verified.values())


def build_captured_research_services_v2(*, repository, effect_broker, scope, lease, registry,
                                      policies, transport, execution_class="live", reservation_micro_usd=1):
    """Concrete factory seam for I1/I3; no mounting, lease creation or fallback."""
    broker = CaptureSourceBrokerV2(registry, policies, effect_broker, scope, lease, transport=transport,
        execution_class=execution_class, reservation_micro_usd=reservation_micro_usd)
    provider = CanonicalEvidenceProviderV2.from_service(repository, effect_broker, registry)
    return broker, provider


def strict_effect_scope_v2(value):
    keys = {"organization_id", "collection_id", "specimen_id", "job_id", "generation"}
    if (type(value) is not dict or set(value) != keys or type(value["generation"]) is not int
        or value["generation"] < 0 or any(type(value[key]) is not str or not value[key] for key in keys - {"generation"})):
        unavailable("canonical_capture_effect_scope_unproved")
    return value


def native_input_context_v2(request, query, resolution, prior, source_mapping, *, asset_generation, native_inputs):
    """Bind actual captured reading IDs/text/assets to the authoritative graph.

    All actual input readings are retained; none is picked by order. A selected
    observation must be explicitly declared in the genuine checkpoint value.
    Mixed or absent input readings have no guessed legacy ToolCallV1 producer.
    """
    observations = {row.id: row for row in prior.run.observations}
    if len(observations) != len(prior.run.observations):
        unavailable("canonical_capture_native_reading_identity_ambiguous")
    ids, regions, input_sources = [], [], []
    input_bindings = {str(row.observation_id): row for row in native_inputs}
    if len(input_bindings) != len(native_inputs):
        unavailable("canonical_capture_native_input_identity_ambiguous")
    for fragment in request.fragments:
        reading = observations.get(fragment.observation_id)
        native_input = input_bindings.get(fragment.observation_id)
        if fragment.input_source == "decided_transcript":
            transcripts = [row for row in prior.run.transcripts if row.region_id == fragment.region_id
                and row.resolved is True and fragment.observation_id in row.observation_ids
                and row.text == fragment.observation_text]
            if len(transcripts) != 1:
                unavailable("canonical_capture_original_transcript_unproved")
            actual_text = transcripts[0].text
        else:
            actual_text = reading.literal_text if reading is not None else None
        if (reading is None or native_input is None
            or native_input.observation_digest != canonical_digest(reading.model_dump(mode="json"))
            or native_input.input_sha256 != reading.input_sha256 or native_input.raw_sha256 != reading.raw_sha256
            or native_input.raw_ref != reading.raw_ref or native_input.request_sha256 != reading.request_sha256
            or fragment.asset_id != prior.asset.id or fragment.asset_digest != prior.asset.sha256
            or fragment.asset_generation != asset_generation
            or fragment.region_id != reading.region_id or fragment.model_id != reading.model_id
            or fragment.observation_text != actual_text
            or fragment.observation_digest != hashlib.sha256(actual_text.encode()).hexdigest()
            or not reading.raw_ref or not reading.raw_sha256
            or not any(region.id == fragment.region_id for region in prior.run.regions)):
            unavailable("canonical_capture_original_reading_mismatch")
        if fragment.observation_id not in ids:
            ids.append(fragment.observation_id)
        if fragment.region_id not in regions:
            regions.append(fragment.region_id)
        if fragment.input_source not in input_sources:
            input_sources.append(fragment.input_source)
    selected = resolution.value.source_observation_id
    if selected is not None and selected not in ids:
        unavailable("canonical_capture_selected_reading_unproved")
    # The lookup's producer takes the input source of the value's own grounding:
    # the fragments of the assemblies it cites, or the reading it selects. A
    # two-reader request carries both the decided transcript and the raw
    # readings; its value's assemblies come from the decided transcript only.
    cited = {key for item in request.assemblies if item.id in resolution.assembly_ids for key in item.fragment_ids}
    grounding = list(dict.fromkeys(fragment.input_source for fragment in request.fragments
        if fragment.id in cited or selected is not None and fragment.observation_id == selected))
    producer_source = (input_sources[0] if len(input_sources) == 1
        else grounding[0] if len(grounding) == 1 else None)
    try:
        native_ids = tuple(UUID(identifier) for identifier in ids)
        native_regions = tuple(UUID(identifier) for identifier in regions)
        if any(str(native) != original for native, original in zip(native_ids, ids)):
            unavailable("canonical_capture_native_reading_id_invalid")
        if any(str(native) != original for native, original in zip(native_regions, regions)):
            unavailable("canonical_capture_native_region_id_invalid")
        run_id = UUID(prior.run.id)
    except (ValueError, TypeError, AttributeError):
        unavailable("canonical_capture_native_reading_id_invalid")
    lineage = ToolInputLineageV2(original_request_digest=digest(request), query_digest=digest(query),
        canonical_run_id=run_id, fragments=request.fragments, observation_ids=native_ids,
        region_ids=native_regions, input_sources=tuple(input_sources),
        native_inputs=tuple(input_bindings[identifier] for identifier in ids),
        selected_observation_id=UUID(selected) if selected is not None else None)
    return CanonicalCaptureContextV2(request_digest=digest(request), query_digest=digest(query),
        canonical_run_id=run_id, asset_id=prior.asset.id,
        region_id=regions[0] if len(regions) == 1 else None,
        observation_ids=native_ids, input_source=producer_source,
        selected_observation_id=UUID(selected) if selected is not None else None,
        canonical_source=source_mapping["canonical_source"], evidence_id_rule=source_mapping["evidence_id_rule"],
        tool_input_lineage=lineage)
