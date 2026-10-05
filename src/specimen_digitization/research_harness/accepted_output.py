"""Application acceptance provenance, recorded with checkpoint CAS; no inference."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from .contracts import (
    Digest, FieldCheckpoint, FieldResolution, FrozenRecord, SourceResult,
    SpecialistRequest, digest,
)

VALIDATOR_VERSION = "validate_resolution/v1"
VALIDATOR_SOURCE_SHA256 = "dbaac411e5559241c724bf4df39ad78e8d87afaf668c5363c0efcd4b1709c400"  # pragma: allowlist secret
JOURNAL_TRANSFORM_VERSION = "sibling-dependency-revision/v1"
MAX_ACCEPTED_PROOF_BYTES = 2_000_000


def validation_boundary_pins() -> dict[str, str]:
    """Record installed application boundary bytes, never a caller version tag."""
    import hashlib
    from pathlib import Path

    directory = Path(__file__).resolve().parent
    validator = hashlib.sha256((directory / "evidence.py").read_bytes()).hexdigest()
    if validator != VALIDATOR_SOURCE_SHA256:
        raise ValueError("accepted_output_validator_source_unqualified")
    return {
        "engine_source_sha256":hashlib.sha256((directory / "engine.py").read_bytes()).hexdigest(),
        "journal_source_sha256":hashlib.sha256((directory / "journal.py").read_bytes()).hexdigest(),
    }


class AcceptedOutputProofV1(FrozenRecord):
    contract_version: Literal["research-accepted-output/v1"] = "research-accepted-output/v1"
    original_request: SpecialistRequest
    native_run_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    resolutions: tuple[FieldResolution, ...]
    source_results: tuple[SourceResult, ...]
    effect_ids: tuple[Digest, ...]
    model_settings_digest: Digest
    engine_source_sha256: Digest
    journal_source_sha256: Digest
    validator_version: Literal["validate_resolution/v1"] = VALIDATOR_VERSION
    validator_source_sha256: Literal["dbaac411e5559241c724bf4df39ad78e8d87afaf668c5363c0efcd4b1709c400"] = VALIDATOR_SOURCE_SHA256

    @model_validator(mode="after")
    def exact_acceptance(self):
        from .evidence import validate_resolution

        if str(UUID(self.native_run_id)) != self.native_run_id:
            raise ValueError("accepted_output_native_run_identity_invalid")
        keys = tuple(item.field_key for item in self.resolutions)
        if len(set(keys)) != len(keys) or set(keys) != set(self.original_request.field_keys):
            raise ValueError("accepted_output_field_coverage_invalid")
        if len(set(self.effect_ids)) != len(self.effect_ids):
            raise ValueError("accepted_output_effect_identity_invalid")
        for item in self.resolutions:
            if validate_resolution(self.original_request, item, self.source_results) != item:
                raise ValueError("accepted_output_resolution_not_validated")
        for item in self.source_results:
            if item.receipt is not None and (
                item.receipt.scope != self.original_request.scope
                or item.receipt.effect_id not in self.effect_ids
            ):
                raise ValueError("accepted_output_source_receipt_invalid")
        return self


class AcceptedCheckpointProofV1(FrozenRecord):
    contract_version: Literal["research-accepted-checkpoints/v1"] = "research-accepted-checkpoints/v1"
    acceptance: AcceptedOutputProofV1
    checkpoints: tuple[FieldCheckpoint, ...]
    journal_transform_version: Literal["sibling-dependency-revision/v1"] = JOURNAL_TRANSFORM_VERSION

    @model_validator(mode="after")
    def exact_checkpoint_binding(self):
        request = self.acceptance.original_request
        keys = tuple(item.field_key for item in self.checkpoints)
        if len(set(keys)) != len(keys) or set(keys) != set(request.field_keys):
            raise ValueError("accepted_checkpoint_field_coverage_invalid")
        original = {item.field_key:item for item in self.acceptance.resolutions}
        materialized = {}
        visiting = set()
        def transform(key):
            if key in materialized:
                return materialized[key]
            if key in visiting:
                raise ValueError("accepted_checkpoint_dependency_cycle")
            visiting.add(key)
            resolution = original[key]
            pins = {pin.field_key:pin for pin in request.dependencies}
            derivation = resolution.derivation
            for pin in resolution.dependencies:
                if pin.field_key in pins:
                    if pins[pin.field_key] != pin:
                        raise ValueError("accepted_checkpoint_dependency_invalid")
                    continue
                sibling = original.get(pin.field_key)
                if (sibling is None or pin.field_key == key or derivation is None
                    or derivation.source_field != pin.field_key or digest(sibling) != pin.digest
                    or sibling.work_state != "resolved"):
                    raise ValueError("accepted_checkpoint_sibling_invalid")
                sibling = transform(pin.field_key)
                revision = request.field_revisions[pin.field_key] + 1
                from .contracts import DependencyPin
                pins[pin.field_key] = DependencyPin(field_key=pin.field_key,
                    revision=revision, digest=digest(sibling))
                derivation = derivation.model_copy(update={"source_revision":revision})
            result = FieldResolution.model_validate({**resolution.model_dump(mode="json"),
                "dependencies":[pin.model_dump(mode="json") for pin in pins.values()],
                "derivation":derivation.model_dump(mode="json") if derivation else None})
            visiting.remove(key)
            materialized[key] = result
            return result
        for checkpoint in self.checkpoints:
            if (checkpoint.resolution != transform(checkpoint.field_key)
                or checkpoint.scope != request.scope
                or checkpoint.revision != request.field_revisions[checkpoint.field_key] + 1
                or checkpoint.prompt_digest != request.prompt.digest
                or checkpoint.source_registry_digest != request.prompt.source_registry_digest
                or checkpoint.model_settings_digest != self.acceptance.model_settings_digest
                or checkpoint.effect_receipt_ids != self.acceptance.effect_ids
                or checkpoint.retry_command_id != request.retry_command_id):
                raise ValueError("accepted_checkpoint_binding_invalid")
        return self

    @property
    def proof_digest(self) -> str:
        return digest(self)


def read_accepted_checkpoint_proof(store, scope, blobs, checkpoint_id: str) -> AcceptedCheckpointProofV1:
    """Recover only an exact committed native checkpoint/run/blob closure."""
    from .persistence import BlobRef, StaleWork, canonical
    import hashlib

    document = store._read(scope)
    job = store._job(document.state, scope)
    matches = [item for item in job["checkpoints"] if item["id"] == checkpoint_id]
    if len(matches) != 1:
        raise StaleWork("accepted_output_checkpoint_unavailable")
    native = matches[0]
    binding = native.get("accepted_output_proof")
    if not isinstance(binding, dict):
        raise StaleWork("accepted_output_historical_proof_unavailable")
    run = document.state["journal"].get(binding.get("native_run_id"))
    retained = run.get("accepted_outputs", {}).get(binding.get("proof_digest")) if run else None
    if (run is None or run["scope"] != native["scope"]
        or run["agent_name"] != binding.get("agent_name")
        or retained is None or retained["proof"] != binding
        or checkpoint_id not in retained["checkpoint_ids"]):
        raise StaleWork("accepted_output_retained_native_binding_invalid")
    capture = binding.get("capture")
    if (not isinstance(capture, dict) or set(capture) != {"locator", "generation", "sha256", "byte_size"}
        or type(capture["byte_size"]) is not int
        or not 0 < capture["byte_size"] <= MAX_ACCEPTED_PROOF_BYTES
        or capture["sha256"] != binding.get("proof_digest")):
        raise StaleWork("accepted_output_capture_bound_invalid")
    from pydantic import ValidationError
    try:
        raw = blobs.get(BlobRef(**capture))
        if (not isinstance(raw, bytes) or len(raw) != capture["byte_size"]
            or hashlib.sha256(raw).hexdigest() != binding["proof_digest"]):
            raise ValueError("capture_mismatch")
        proof = AcceptedCheckpointProofV1.model_validate_json(raw)
    except (ValidationError, ValueError, TypeError, OSError):
        raise StaleWork("accepted_output_capture_unavailable") from None
    source_boundary = job["pins"]["sources"].get("acceptance_boundary")
    expected = {"contract_version":"research-acceptance-boundary/v1",
        "validator_version":VALIDATOR_VERSION, "validator_source_sha256":VALIDATOR_SOURCE_SHA256,
        "engine_source_sha256":proof.acceptance.engine_source_sha256,
        "journal_source_sha256":proof.acceptance.journal_source_sha256}
    if source_boundary is None and document.state["budget_policy"].get("live_authorized") is not True:
        source_boundary = {**expected, **validation_boundary_pins()}
    if source_boundary != expected:
        raise StaleWork("accepted_output_source_boundary_unqualified")
    if (canonical(proof.model_dump(mode="json")) != raw
        or hashlib.sha256(raw).hexdigest() != binding["proof_digest"]
        or proof.proof_digest != binding["proof_digest"]
        or digest(proof.acceptance.original_request) != binding["request_digest"]
        or proof.acceptance.native_run_id != binding["native_run_id"]
        or proof.acceptance.conversation_id != binding["conversation_id"]
        or str(proof.acceptance.original_request.role) != binding["agent_name"]
        or run["record"].get("conversation_id") != binding["conversation_id"]
        or binding["checkpoint_payload_digests"] != [digest(item) for item in proof.checkpoints]):
        raise StaleWork("accepted_output_immutable_body_invalid")
    committed = [item for item in job["checkpoints"] if item["id"] in retained["checkpoint_ids"]]
    by_digest = {digest(item["payload"]):item for item in committed}
    if (len(committed) != len(proof.checkpoints) or len(by_digest) != len(committed)
        or len(set(retained["checkpoint_ids"])) != len(committed)
        or set(by_digest) != set(binding["checkpoint_payload_digests"])
        or any(item.get("accepted_output_proof") != binding for item in committed)
        or any(by_digest[digest(item)]["payload"] != item.model_dump(mode="json") for item in proof.checkpoints)):
        raise StaleWork("accepted_output_committed_checkpoint_closure_invalid")
    return proof
