"""Field-checkpoint protocol backed by the sole scoped SQL lifecycle store."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
import hashlib

from .accepted_output import AcceptedOutputProofV1, AcceptedCheckpointProofV1, validation_boundary_pins, MAX_ACCEPTED_PROOF_BYTES
from collections.abc import Sequence

from .contracts import ROLE_FIELDS, DependencyPin, FieldCheckpoint, FieldKey, FieldResolution, ResearchScope, SpecialistRequest, digest
from .persistence import DurabilityScope, Lease, ResearchStore, StaleWork, ImmutableBlobs, BlobRef, canonical
from .telemetry import TraceParent, current_trace_parent


class DurableResearchJournal:
    def __init__(self, store: ResearchStore, scope: DurabilityScope, lease: Lease, blobs: ImmutableBlobs | None = None):
        self.store, self.scope, self.lease, self.blobs = store, scope, lease, blobs

    def _check_scope(self, scope: ResearchScope) -> None:
        expected = (
            self.scope.organization_id, self.scope.collection_id, self.scope.specimen_id,
            self.scope.job_id, self.scope.generation, self.scope.sensitive,
        )
        received = (
            scope.organization_id, scope.collection_id, scope.specimen_id,
            scope.job_id, scope.generation, scope.sensitive,
        )
        if expected != received:
            raise PermissionError("journal_scope_mismatch")
        job = self.store.job(self.scope)
        if job["pins"]["input_digest"] != scope.input_digest:
            raise PermissionError("journal_input_binding_mismatch")
        if digest(job["pins"]["profile"]) != scope.profile_digest:
            raise PermissionError("journal_profile_binding_mismatch")

    async def validate_request(self, request: SpecialistRequest, *, model_settings_digest: str) -> None:
        try:
            request = SpecialistRequest.model_validate(request.model_dump(mode="json"))
        except ValueError:
            raise ValueError("journal_specialist_field_role_mismatch") from None
        def check():
            self._check_scope(request.scope)
            document = self.store._read(self.scope)
            job = self.store._lease(document.state, self.scope, self.lease, document.server_time)
            pins = job["pins"]
            role = str(request.role)
            for key in request.field_keys:
                field = job["fields"].get(str(key), {})
                command_id = field.get("retry_command_id")
                if command_id != request.retry_command_id:
                    raise StaleWork("journal_retry_command_binding_mismatch")
                if command_id is not None:
                    command = document.state["outbox"].get("retry/" + command_id, {}).get("command", {})
                    if (command.get("scope") != self.scope.identity() or command.get("field_key") != str(key)
                        or command.get("binding_digest") != job["binding_digest"] or command.get("status") != "running"
                        or command.get("expected_field_revision") != request.field_revisions.get(key)
                        or command.get("lease") != asdict(self.lease)):
                        raise StaleWork("journal_retry_command_binding_mismatch")
            if (
                digest(pins["profile"]) != request.scope.profile_digest
                or pins["prompts"].get(role) != request.prompt.model_dump(mode="json")
                or pins["sources"].get("registry_digest") != request.prompt.source_registry_digest
                or pins["model"].get(role, {}).get("route") != request.prompt.model_route
                or digest(pins["settings"]) != model_settings_digest
                or not set(request.field_keys) <= set(job["fields"])
                or any(job["fields"][str(key)]["locked"] for key in request.field_keys)
                or any(job["fields"][str(key)]["revision"] != request.field_revisions.get(key, 0) for key in request.field_keys)
                or job["paused"]
            ):
                raise StaleWork("journal_runtime_binding_mismatch")
        await asyncio.to_thread(check)

    async def field_revisions(self, scope: ResearchScope) -> dict[FieldKey, int]:
        def read():
            self._check_scope(scope)
            document = self.store._read(self.scope)
            job = self.store._lease(document.state, self.scope, self.lease, document.server_time)
            return {FieldKey(key):field["revision"] for key,field in job["fields"].items()}
        return await asyncio.to_thread(read)

    async def protected_fields(self, scope: ResearchScope) -> tuple[FieldKey, ...]:
        await asyncio.to_thread(self._check_scope, scope)
        job = await asyncio.to_thread(self.store.job, self.scope)
        return tuple(FieldKey(key) for key,value in job["fields"].items() if value["locked"])

    async def trace_context(self, scope: ResearchScope) -> TraceParent | None:
        await asyncio.to_thread(self._check_scope, scope)
        job = await asyncio.to_thread(self.store.job, self.scope)
        return TraceParent(**job["trace_context"]) if job["trace_context"] else None

    async def bind_trace(self, scope: ResearchScope, parent: TraceParent) -> None:
        await asyncio.to_thread(self._check_scope, scope)
        await asyncio.to_thread(self.store.bind_trace, self.scope, self.lease, asdict(parent))

    async def load(self, scope: ResearchScope) -> tuple[FieldCheckpoint, ...]:
        await asyncio.to_thread(self._check_scope, scope)
        job = await asyncio.to_thread(self.store.job, self.scope)
        if job["binding_digest"] != digest(job["pins"]):
            raise StaleWork("checkpoint_runtime_binding_mismatch")
        result = []
        for field_key, field in job["fields"].items():
            stored = field["checkpoint"]
            if stored is None:
                continue
            checkpoint = FieldCheckpoint.model_validate(stored["payload"])
            native_scope = {key:getattr(checkpoint.scope, key) for key in self.scope.identity()}
            if (str(checkpoint.field_key) != field_key or stored.get("field_key") != field_key
                or type(field["revision"]) is not int or type(stored.get("revision")) is not int
                or field["revision"] != checkpoint.revision or stored["revision"] != checkpoint.revision
                or stored.get("scope") != native_scope
                or stored.get("id") != digest({"scope":native_scope, "field":field_key,
                    "revision":checkpoint.revision, "payload":stored["payload"]})
                or tuple(stored.get("receipt_ids", ())) != checkpoint.effect_receipt_ids
                or stored.get("dependencies") != {str(pin.field_key):pin.revision for pin in checkpoint.resolution.dependencies}
                or stored.get("dependency_digests", {}) != {str(pin.field_key):pin.digest for pin in checkpoint.resolution.dependencies}
                or stored.get("retry_command_id") != checkpoint.retry_command_id):
                raise StaleWork("checkpoint_native_typed_binding_mismatch")
            self.store._publication_basis(job, self.scope, field_key)
            if checkpoint.scope != scope:
                reuse = field.get("reuse")
                source = next((history for history in job["history"]
                    if history["scope"] == stored["scope"] and history["fields"].get(str(checkpoint.field_key), {}).get("checkpoint") == stored), None)
                if (reuse is None or source is None
                    or reuse["reused_from_scope_digest"] != digest(stored["scope"])
                    or reuse["checkpoint_digest"] != digest(stored)
                    or reuse["into_scope_digest"] != digest(self.scope.identity())
                    or reuse["source_binding_digest"] != stored["binding_digest"]
                    or reuse["source_binding_digest"] != source["binding_digest"]
                    or reuse["target_binding_digest"] != job["binding_digest"]
                    or reuse["retained_dependencies"] != stored["dependencies"]
                    or reuse.get("retained_dependency_digests") != stored.get("dependency_digests", {})
                    or any(job["dependencies"].get(key) != revision for key,revision in stored["dependencies"].items())
                    or any(job["pins"][key] != source["pins"][key] for key in job["pins"] if key != "input_digest")
                    or checkpoint.scope.input_digest != source["pins"]["input_digest"]
                    or checkpoint.scope.profile_digest != digest(source["pins"]["profile"])):
                    raise StaleWork("checkpoint_generation_requires_verified_reuse")
                checkpoint = FieldCheckpoint.model_validate({**checkpoint.model_dump(mode="json"),
                    "scope":scope.model_dump(mode="json"),
                    "reused_from_scope_digest":digest(checkpoint.scope),
                    "reused_from_checkpoint_digest":digest(checkpoint)})
            self.store._dependencies(job, stored["dependencies"], stored.get("dependency_digests", {}))
            role = next(role for role,keys in ROLE_FIELDS.items() if checkpoint.field_key in keys)
            prompt = job["pins"]["prompts"].get(str(role))
            if (prompt is None or checkpoint.prompt_digest != prompt["digest"]
                or checkpoint.source_registry_digest != job["pins"]["sources"]["registry_digest"]
                or checkpoint.model_settings_digest != digest(job["pins"]["settings"])):
                raise StaleWork("checkpoint_runtime_binding_mismatch")
            result.append(checkpoint)
        return tuple(result)

    async def commit(
        self, request: SpecialistRequest, resolutions: Sequence[FieldResolution], *,
        receipt_ids: Sequence[str], model_settings_digest: str,
        accepted_output: AcceptedOutputProofV1 | None = None,
    ) -> tuple[FieldCheckpoint, ...]:
        await self.validate_request(request, model_settings_digest=model_settings_digest)
        request = SpecialistRequest.model_validate(request.model_dump(mode="json"))
        resolutions = tuple(FieldResolution.model_validate(item.model_dump(mode="json")) for item in resolutions)
        keys = tuple(item.field_key for item in resolutions)
        if len(set(keys)) != len(keys) or not set(keys) <= set(request.field_keys):
            raise ValueError("journal_field_coverage_mismatch")
        available = {item.field_key:item for item in await self.load(request.scope)}
        dependencies = {pin.field_key:pin for pin in request.dependencies}
        for pin in request.dependencies:
            current = available.get(pin.field_key)
            if current is None or current.revision != pin.revision or digest(current.resolution) != pin.digest:
                raise StaleWork("journal_consumed_dependency_binding_mismatch")
        job = await asyncio.to_thread(self.store.job, self.scope)
        proposed = {item.field_key:item for item in resolutions}
        materialized = {}
        visiting = set()
        has_sibling_dependency = False

        def materialize(key):
            nonlocal has_sibling_dependency
            if key in materialized:
                return materialized[key]
            if key in visiting:
                raise StaleWork("journal_dependency_cycle")
            visiting.add(key)
            resolution = proposed[key]
            pins = dict(dependencies)
            derivation = resolution.derivation
            for pin in resolution.dependencies:
                if pin.field_key in dependencies:
                    if dependencies[pin.field_key] != pin:
                        raise StaleWork("journal_output_dependency_binding_mismatch")
                    continue
                source = proposed.get(pin.field_key)
                if (source is None or pin.field_key == key or derivation is None
                    or derivation.source_field != pin.field_key or digest(source) != pin.digest
                    or source.work_state != "resolved"):
                    raise StaleWork("journal_output_dependency_binding_mismatch")
                has_sibling_dependency = True
                source = materialize(pin.field_key)
                revision = request.field_revisions.get(pin.field_key, 0) + 1
                pins[pin.field_key] = DependencyPin(field_key=pin.field_key,
                    revision=revision, digest=digest(source))
                derivation = derivation.model_copy(update={"source_revision":revision})
            resolution = FieldResolution.model_validate({**resolution.model_dump(mode="json"),
                "dependencies":[pin.model_dump(mode="json") for pin in pins.values()],
                "derivation":derivation.model_dump(mode="json") if derivation else None})
            visiting.remove(key)
            materialized[key] = resolution
            return resolution

        for key in proposed:
            materialize(key)
        result, entries = [], []
        active = current_trace_parent()
        trace_id = active.trace_id if active else job["trace_context"]["trace_id"] if job["trace_context"] else None
        for resolution in materialized.values():
            expected_revision = request.field_revisions.get(resolution.field_key, 0)
            payload = FieldCheckpoint(
                scope=request.scope, field_key=resolution.field_key,
                revision=expected_revision + 1, resolution=resolution,
                prompt_digest=request.prompt.digest,
                model_settings_digest=model_settings_digest,
                source_registry_digest=request.prompt.source_registry_digest,
                effect_receipt_ids=tuple(receipt_ids),
                retry_command_id=request.retry_command_id,
                trace_id=trace_id,
            )
            entries.append({"field_key":str(resolution.field_key), "payload":payload.model_dump(mode="json"),
                "expected_revision":expected_revision, "receipt_ids":tuple(receipt_ids),
                "dependencies":{str(pin.field_key):pin.revision for pin in resolution.dependencies},
                "dependency_digests":{str(pin.field_key):pin.digest for pin in resolution.dependencies}})
            if request.retry_command_id is not None:
                entries[-1]["retry_command_id"] = request.retry_command_id
            result.append(payload)
        proof_binding = None
        if accepted_output is not None:
            accepted_output = AcceptedOutputProofV1.model_validate(accepted_output.model_dump(mode="json"))
            boundary = validation_boundary_pins()
            if (accepted_output.original_request != request or accepted_output.resolutions != resolutions
                or accepted_output.effect_ids != tuple(receipt_ids)
                or accepted_output.engine_source_sha256 != boundary["engine_source_sha256"]
                or accepted_output.journal_source_sha256 != boundary["journal_source_sha256"]
                or accepted_output.model_settings_digest != model_settings_digest or self.blobs is None):
                raise StaleWork("accepted_output_checkpoint_binding_invalid")
            proof = AcceptedCheckpointProofV1(acceptance=accepted_output, checkpoints=tuple(result))
            body = canonical(proof.model_dump(mode="json"))
            if len(body) > MAX_ACCEPTED_PROOF_BYTES:
                raise StaleWork("accepted_output_capture_bound_invalid")
            locator = "research-journal/accepted-output/" + digest(self.scope.identity()) + "/" + proof.proof_digest + ".json"
            reference = await asyncio.to_thread(self.blobs.put_at, locator, body)
            if reference.sha256 != hashlib.sha256(body).hexdigest() or reference.byte_size != len(body):
                raise StaleWork("accepted_output_capture_invalid")
            proof_binding = {"contract_version":proof.contract_version,
                "proof_digest":proof.proof_digest, "native_run_id":accepted_output.native_run_id,
                "conversation_id":accepted_output.conversation_id, "agent_name":str(request.role),
                "request_digest":digest(request), "capture":asdict(reference),
                "checkpoint_payload_digests":[digest(item.model_dump(mode="json")) for item in result]}
        if proof_binding is not None:
            # The proof and all accepted sibling checkpoints share one CAS. An
            # immutable pre-CAS blob alone is never acceptance authority.
            await asyncio.to_thread(self.store.checkpoint_batch, self.scope, self.lease, entries,
                accepted_output_proof=proof_binding)
        elif has_sibling_dependency:
            await asyncio.to_thread(self.store.checkpoint_batch, self.scope, self.lease, entries)
        else:
            for entry in entries:
                await asyncio.to_thread(self.store.checkpoint, self.scope, self.lease, **entry)
        return tuple(result)

    async def retry_eligible(self, scope: ResearchScope, field_key: FieldKey) -> bool:
        await asyncio.to_thread(self._check_scope, scope)
        document = await asyncio.to_thread(self.store._read, self.scope)
        job = self.store._job(document.state, self.scope)
        if job["paused"] or field_key not in job["fields"] or job["fields"][field_key]["locked"]:
            return False
        # Without an exact dependency-attribution permit, an unknown outcome
        # blocks every new effect on this job. No clock/restart releases it.
        effects = [effect for effect in document.state["effects"].values() if effect["job_key"] == self.scope.key]
        return not any(effect["status"] in {"sending", "held_unknown"}
            or (effect["status"] == "completed" and effect["receipt"]["actual_micro_usd"] is None)
            for effect in effects)
