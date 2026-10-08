"""Application acceptance provenance, recorded with checkpoint CAS; no inference."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from .contracts import (
    Digest, FieldCheckpoint, FieldResolution, FrozenRecord, SourceResult,
    SpecialistRequest, digest,
)

VALIDATOR_VERSION = "validate_resolution/v8"
VALIDATOR_SOURCE_SHA256 = "1c03ee87e2a0d1e3d09cb7b200b0322b9125ea20560fe6eecbf66403d2264d86"  # pragma: allowlist secret
V3_VALIDATOR_SOURCE_SHA256 = "68e60ffdd8d840933df6f52c50f190f9febc2a72ece05810aa4aa08a32e7caa4"  # pragma: allowlist secret
PREVIOUS_VALIDATOR_SOURCE_SHA256 = "e7e0d101ff0780c314345b1c476649702d076271869bc325736d7914c717a3ff"  # pragma: allowlist secret
HISTORICAL_VALIDATOR_SOURCE_SHA256 = "dbaac411e5559241c724bf4df39ad78e8d87afaf668c5363c0efcd4b1709c400"  # pragma: allowlist secret
JOURNAL_TRANSFORM_VERSION = "sibling-dependency-revision/v1"
MAX_ACCEPTED_PROOF_BYTES = 2_000_000


def validation_boundary_pins() -> dict[str, str]:
    """Record installed application boundary bytes, never a caller version tag."""
    import hashlib
    from pathlib import Path

    directory = Path(__file__).resolve().parent
    validator = installed_validator_source_sha256(directory)
    if validator != VALIDATOR_SOURCE_SHA256:
        raise ValueError("accepted_output_validator_source_unqualified")
    from .evidence import PEOPLE_POLICY_SOURCE_SHA256
    if hashlib.sha256((directory / "people.py").read_bytes()).hexdigest() != PEOPLE_POLICY_SOURCE_SHA256:
        raise ValueError("accepted_output_people_policy_source_unqualified")
    return {
        "engine_source_sha256":hashlib.sha256((directory / "engine.py").read_bytes()).hexdigest(),
        "journal_source_sha256":hashlib.sha256((directory / "journal.py").read_bytes()).hexdigest(),
    }


VALIDATOR_COMPONENTS = ('evidence.py', 'contracts.py', 'taxonomy.py', 'temporal_context.py', 'measurement.py', 'people.py', 'collection.py', 'geography_context.py', 'geography_strategy.py', 'dependency_context.py', 'output_admission.py')
HISTORICAL_VALIDATOR_PAIRS = frozenset((('validate_resolution/v1', 'dbaac411e5559241c724bf4df39ad78e8d87afaf668c5363c0efcd4b1709c400'), ('validate_resolution/v2', 'e7e0d101ff0780c314345b1c476649702d076271869bc325736d7914c717a3ff'), ('validate_resolution/v3', '68e60ffdd8d840933df6f52c50f190f9febc2a72ece05810aa4aa08a32e7caa4'), ('validate_resolution/v4', '12a9ffe819504808b6bf08d60b4920c5d4210bf33dda0240c1bf94072bb02b41'), ('validate_resolution/v4', '411222607943d073f585020d70122078d04514f04cf8d3b12828e8b32218fd39'), ('validate_resolution/v4', '67c3902b9b882a7b3df4f423dc1412019c47d738fbdfe84e2d8aff295072a7fc'), ('validate_resolution/v4', '71b283fccd982327b55d749f2659e7cc1418f121ff887451ccf58d972872c9df'), ('validate_resolution/v4', '775b48bbd6e5ae3554af2406d3f3e76ac73cdb6e3a8e96fcac7c3983c75164dd'), ('validate_resolution/v4', '936ab14bbbf43643ec8d4f8d4e3007d4ab2ced53c6c9bd21f92409c8d8216454'), ('validate_resolution/v4', 'b5af78b21598200ba6b603b95b7a81fa5f06f5161a95d6d3320120842854f98d'), ('validate_resolution/v4', 'c09840fddab414682a0369015efb7dcc8af95a1a9903c3ffe1f92893ff0e3bc9'), ('validate_resolution/v5', '791626c0f6fce33f701f43cfae4d6f08dce8ef51ec5e97ac7b54edbc7de14605'), ('validate_resolution/v5', 'b0663f01ec72e88bd079cb13a9727c6b2e66d2d8b4059073cd00e2e3f73583d7'), ('validate_resolution/v6', '743db08d346d632241945e4c0d35c770166e8f6cc55f8c72d3d5e358b3372885'), ('validate_resolution/v7', 'c6d758fd18566a6941bdb3be07af4d5baaf5cd9d16111c1806409a3c179c9fc1')))  # pragma: allowlist secret (reviewed source digests)
TEMPORAL_LINK_VALIDATOR_SOURCE_SHA256 = "c09840fddab414682a0369015efb7dcc8af95a1a9903c3ffe1f92893ff0e3bc9"  # pragma: allowlist secret


def installed_validator_source_sha256(directory) -> str:
    """Bind the complete composed validator closure; historical pairs stay exact."""
    import hashlib
    parts = (VALIDATOR_VERSION + "\0").encode() + b"".join(
        name.encode() + b"\0" + hashlib.sha256((directory / name).read_bytes()).digest()
        for name in VALIDATOR_COMPONENTS)
    return hashlib.sha256(parts).hexdigest()


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
    validator_version: Literal['validate_resolution/v1', 'validate_resolution/v2', 'validate_resolution/v3', 'validate_resolution/v4', 'validate_resolution/v5', 'validate_resolution/v6', 'validate_resolution/v7', 'validate_resolution/v8'] = VALIDATOR_VERSION
    validator_source_sha256: Literal['12a9ffe819504808b6bf08d60b4920c5d4210bf33dda0240c1bf94072bb02b41', '411222607943d073f585020d70122078d04514f04cf8d3b12828e8b32218fd39', '67c3902b9b882a7b3df4f423dc1412019c47d738fbdfe84e2d8aff295072a7fc', '68e60ffdd8d840933df6f52c50f190f9febc2a72ece05810aa4aa08a32e7caa4', '71b283fccd982327b55d749f2659e7cc1418f121ff887451ccf58d972872c9df', '743db08d346d632241945e4c0d35c770166e8f6cc55f8c72d3d5e358b3372885', '775b48bbd6e5ae3554af2406d3f3e76ac73cdb6e3a8e96fcac7c3983c75164dd', '791626c0f6fce33f701f43cfae4d6f08dce8ef51ec5e97ac7b54edbc7de14605', '936ab14bbbf43643ec8d4f8d4e3007d4ab2ced53c6c9bd21f92409c8d8216454', 'b0663f01ec72e88bd079cb13a9727c6b2e66d2d8b4059073cd00e2e3f73583d7', 'b5af78b21598200ba6b603b95b7a81fa5f06f5161a95d6d3320120842854f98d', 'c09840fddab414682a0369015efb7dcc8af95a1a9903c3ffe1f92893ff0e3bc9', 'c6d758fd18566a6941bdb3be07af4d5baaf5cd9d16111c1806409a3c179c9fc1', 'dbaac411e5559241c724bf4df39ad78e8d87afaf668c5363c0efcd4b1709c400', 'e7e0d101ff0780c314345b1c476649702d076271869bc325736d7914c717a3ff', '1c03ee87e2a0d1e3d09cb7b200b0322b9125ea20560fe6eecbf66403d2264d86'] = VALIDATOR_SOURCE_SHA256  # pragma: allowlist secret

    @model_validator(mode="after")
    def exact_acceptance(self):
        from .evidence import validate_resolution

        if (self.validator_version, self.validator_source_sha256) not in (
                HISTORICAL_VALIDATOR_PAIRS | {(VALIDATOR_VERSION, VALIDATOR_SOURCE_SHA256)}):
            raise ValueError("accepted_output_validator_pair_unqualified")
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
    # Historical proof provenance is joined to its immutable job, not relabelled
    # as today's producer. Installed bytes and today's stronger semantics still
    # qualify every read; unknown or crossed version/hash pairs never decode.
    boundary = validation_boundary_pins()
    expected = {"contract_version":"research-acceptance-boundary/v1",
        "validator_version":proof.acceptance.validator_version,
        "validator_source_sha256":proof.acceptance.validator_source_sha256,
        "engine_source_sha256":proof.acceptance.engine_source_sha256,
        "journal_source_sha256":proof.acceptance.journal_source_sha256}
    if source_boundary is None and document.state["budget_policy"].get("live_authorized") is not True:
        source_boundary = {**expected, **boundary}
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
