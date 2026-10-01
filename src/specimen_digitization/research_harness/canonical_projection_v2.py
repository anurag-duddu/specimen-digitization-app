"""Additive canonical-value-lineage/v2 pure projection source, UNRUN.

The native V2 writer must supply transaction-read inputs and recompute this
projection. These types, JSON hashes and supplied rows are not authorization.
This function does no IO or scientific calculation and does not install the
native transaction, capture consumer or whole-record policy producer.
Ordinary PR168 projection and the current V1 HOLD guards remain unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import Field

from specimen_digitization.application.domain import FieldValue, Principal, Specimen, ValueState
from specimen_digitization.application.active_graph import GRAPH_LIMIT, run_summary
from specimen_digitization.application.projection import Write, _record, _first_pass, _reading, _region_row, derived_id
from specimen_digitization.application.storage import digest as canonical_digest
from .compatibility import PublicationUnavailable
from .canonical_evidence_provider_v2 import CapturedCanonicalEvidenceV2
from .contracts import Digest, FieldCheckpoint, FrozenRecord, ResearchScope, SourceResult, SpecialistRequest, WorkState, digest
from .evidence import validate_assembly, validate_resolution
from .native_canonical import CANONICAL_KEYS, RESEARCH_KEYS, CanonicalIdentityV1, canonical_value_v1, strict_history_scope_v1
from .publication import NativeDependencyBasis, _native_checkpoint

CONTRACT = "canonical-value-lineage/v2"


def unavailable(code):
    raise PublicationUnavailable(code)


class ConsumedCanonicalSourceV2(FrozenRecord):
    """Exact source rows loaded and locked by the native writer, never model input."""
    checkpoint: FieldCheckpoint
    native_basis: NativeDependencyBasis
    canonical_run_id: UUID
    canonical_candidate_id: UUID
    canonical_record_version_id: UUID
    canonical_field_key: str = Field(min_length=1)
    candidate_contract: Literal["ordinary-pr168/v2", "canonical-value-lineage/v2"]
    candidate: dict
    record: dict
    resolved_field: dict
    record_projection: tuple[dict, ...]
    record_projection_digest: Digest
    candidate_digest: Digest
    record_digest: Digest
    source_publication_lineage_digest: Digest


@dataclass(frozen=True)
class NativePriorSnapshotProofV2:
    """Actual native pointer, packed JSON and original bounded graph bytes.

    Sole native consumer supplies these transaction-read inputs. Neither this
    private type nor its hashes authorize a model/client-provided snapshot.
    """
    canonical: CanonicalIdentityV1
    snapshot: dict
    active_graph_bytes: bytes | None = None


class NativeRawSourceAssetProofV2(FrozenRecord):
    """Actual scoped SourceAsset row and its native-loaded original ref binding.

    The native consumer verifies retained generation and bounded original bytes.
    This private row does not authorize a blob lookup.
    """
    original_ref: str = Field(min_length=1)
    row: dict


class NativeTranscriptionDecisionProofV2(FrozenRecord):
    """Actual native selections normalized to complete scoped write payloads.

    decision_rows retain transcription, first-pass observation and all handoffs;
    reader_rows retain every independent transcript member. Query selections
    omit server timestamps, not scientific or decision fields.
    """
    region_id: str = Field(min_length=1)
    transcription_version_id: UUID
    region_row: dict
    decision_rows: tuple[dict, ...]
    reader_rows: tuple[dict, ...]
    raw_assets: tuple[NativeRawSourceAssetProofV2, ...]


@dataclass(frozen=True)
class CanonicalLineageContextV2:
    scope: ResearchScope
    actor_uid: str
    prior_record_version_id: UUID
    prior_revision: int
    prior_snapshot_sha256: str  # Rehydrated policy graph SHA, never packed native SHA.
    native_prior_snapshot: NativePriorSnapshotProofV2
    job: dict
    field_mapping: dict[str, str]
    evidence_id_mapping: dict[str, UUID]
    human_locks: dict[str, bool]
    prior_projection: tuple[dict, ...]
    original_request: SpecialistRequest
    tool_results: tuple[SourceResult, ...]
    consumed_sources: tuple[ConsumedCanonicalSourceV2, ...] = ()
    # Actual verified native transcription identities, not region->ID guesses.
    transcription_ids: dict[str, UUID] | None = None
    transcription_proofs: tuple[NativeTranscriptionDecisionProofV2, ...] = ()
    # Forward-only CAS-linked application acceptance. Historical contexts keep
    # their existing direct validation; this never manufactures an old proof.
    accepted_checkpoint_proof: object | None = None


def validate_checkpoint_resolution_v2(context, original):
    proof = context.accepted_checkpoint_proof
    if proof is None:
        return validate_resolution(context.original_request, original.resolution, context.tool_results)
    from .accepted_output import AcceptedCheckpointProofV1
    try:
        verified = AcceptedCheckpointProofV1.model_validate(proof.model_dump(mode="json"))
    except (ValueError, TypeError, AttributeError):
        unavailable("canonical_accepted_resolution_transform_unproved")
    matches = [cp for cp in verified.checkpoints if cp.field_key == original.field_key]
    if (len(matches) != 1 or matches[0] != original
            or verified.acceptance.original_request != context.original_request
            or verified.acceptance.source_results != context.tool_results):
        unavailable("canonical_accepted_resolution_transform_unproved")
    # The accepted body's validator checks the pre-transform resolutions; its
    # checkpoint validator reproduces the exact committed sibling transform.
    return original.resolution


@dataclass(frozen=True)
class CanonicalValueProjectionV2:
    contract_version: str
    field_key: str
    candidate_id: UUID | None
    record_version_id: UUID
    predecessor_id: UUID
    prior_revision: int
    result_revision: int
    result_snapshot_sha256: str
    target_writes: tuple[Write, ...]
    record_writes: tuple[Write, ...]
    lineage_digest: str



def _prior_snapshot(prior, context):
    """Pure exact reconstruction of retained native snapshot/graph bytes."""
    proof = context.native_prior_snapshot
    if not isinstance(proof, NativePriorSnapshotProofV2) or not isinstance(proof.canonical, CanonicalIdentityV1) or type(proof.snapshot) is not dict:
        unavailable("canonical_lineage_native_snapshot_unproved")
    native, payload = proof.canonical, proof.snapshot
    if any(type(revision) is not int or revision < 1 for revision in
            (context.prior_revision, prior.version, native.record_revision)):
        unavailable("canonical_lineage_revision_unproved")
    graph = prior.model_dump(mode="json")
    if (native.record_revision != context.prior_revision or native.record_version_id != context.prior_record_version_id
            or str(native.canonical_run_id) != prior.run.id or type(payload.get("version")) is not int
            or payload.get("version") != prior.version or payload.get("id") != prior.id
            or canonical_digest(payload) != native.snapshot_sha256
            or canonical_digest(graph) != context.prior_snapshot_sha256):
        unavailable("canonical_lineage_native_snapshot_unproved")
    metadata = payload.get("active_graph")
    raw_digest = None
    if metadata is None:
        if proof.active_graph_bytes is not None or payload != graph:
            unavailable("canonical_lineage_native_graph_unproved")
    else:
        raw = proof.active_graph_bytes
        keys = {"contract_version", "scope", "specimen_id", "revision", "run_id", "blob_ref", "sha256", "run_sha256", "size_bytes"}
        if (type(metadata) is not dict or set(metadata) != keys or metadata["contract_version"] != "active-run-v1"
                or type(raw) is not bytes or not 0 < len(raw) <= GRAPH_LIMIT
                or type(metadata["size_bytes"]) is not int or metadata["size_bytes"] != len(raw)
                or type(metadata["revision"]) is not int or metadata["revision"] != prior.version
                or metadata["scope"] != payload.get("scope") or metadata["specimen_id"] != prior.id
                or metadata["run_id"] != prior.run.id or type(metadata["blob_ref"]) is not str or not metadata["blob_ref"]
                or hashlib.sha256(raw).hexdigest() != metadata["sha256"]):
            unavailable("canonical_lineage_native_graph_unproved")
        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    unavailable("canonical_lineage_native_graph_unproved")
                value[key] = item
            return value
        def nonfinite(_):
            unavailable("canonical_lineage_native_graph_unproved")
        try:
            retained = json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)
        except (ValueError, UnicodeError, TypeError):
            unavailable("canonical_lineage_native_graph_unproved")
        if (type(retained) is not dict or set(retained) != {"contract_version", "scope", "specimen_id", "revision", "run"}
                or retained["contract_version"] != "active-run-v1" or retained["scope"] != payload["scope"]
                or retained["specimen_id"] != prior.id or type(retained["revision"]) is not int
                or retained["revision"] != prior.version or retained["run"] != graph["run"]
                or canonical_digest(retained["run"]) != metadata["run_sha256"]
                or payload.get("run") != run_summary(retained["run"])
                or {**payload, "run": retained["run"]} != graph):
            unavailable("canonical_lineage_native_graph_unproved")
        raw_digest = metadata["sha256"]
    return {"native": native.snapshot_sha256, "graph": context.prior_snapshot_sha256, "active_graph": raw_digest}


def _value(resolution, context):
    required = set(resolution.evidence_ids) | set(resolution.value.evidence_ids)
    if not required <= set(context.evidence_id_mapping):
        unavailable("canonical_lineage_evidence_mapping_missing")
    return canonical_value_v1(resolution, context.field_mapping,
        {key: context.evidence_id_mapping[key] for key in required})


def _checkpoint(context, typed):
    row = context.job.get("fields", {}).get(str(typed.field_key), {}).get("checkpoint")
    if not isinstance(row, dict):
        unavailable("canonical_lineage_native_checkpoint_missing")
    # Raw scalar types precede equality: True must not alias generation 1.
    strict_history_scope_v1(row.get("scope"))
    return _native_checkpoint(context.job, typed, context.scope)


def _parsed(value, *, ordinary=False):
    if ordinary and (value.precision or value.century_rule):
        return {"value": value.parsed, "precision": value.precision, "century_rule": value.century_rule}
    return value.parsed


def _source_lineage(context, prior, target, sources):
    pins = target.resolution.dependencies
    if len(pins) != len(sources) or len({pin.field_key for pin in pins}) != len(pins):
        unavailable("canonical_lineage_consumed_source_set_unproved")
    ordered = []
    for ordinal, (pin, proof) in enumerate(zip(pins, sources)):
        cp = proof.checkpoint
        native, original = _checkpoint(context, cp)
        expected_basis = NativeDependencyBasis(field_key=cp.field_key, revision=cp.revision,
            resolution_digest=digest(cp.resolution), checkpoint_id=native["id"], checkpoint_digest=digest(native))
        field = context.field_mapping[str(pin.field_key)]
        value = _value(original.resolution, context)
        current_rows = [row for row in context.prior_projection if row["fieldKey"] == field]
        candidate, record, resolved = proof.candidate, proof.record, proof.resolved_field
        scope = {"organizationId": context.scope.organization_id, "collectionId": context.scope.collection_id}
        source_rows = proof.record_projection
        if (len(source_rows) != 20 or {row.get("fieldKey") for row in source_rows} != CANONICAL_KEYS
                or digest(source_rows) != proof.record_projection_digest
                or any(str(row.get("recordVersionId")) != str(proof.canonical_record_version_id)
                    or any(row.get(key) != value for key, value in scope.items()) for row in source_rows)
                or len([row for row in source_rows if row == resolved]) != 1
                or str(resolved.get("id")) != derived_id(str(proof.canonical_record_version_id), "field", field)):
            unavailable("canonical_lineage_source_record_membership_unproved")
        if (pin.field_key != cp.field_key or pin.revision != cp.revision or pin.digest != digest(cp.resolution)
                or proof.native_basis != expected_basis or original.resolution != cp.resolution
                or proof.canonical_field_key != field or str(proof.canonical_run_id) != prior.run.id
                or prior.run.fields[field] != value or value.state != ValueState.SUPPORTED
                or digest(candidate) != proof.candidate_digest or digest(record) != proof.record_digest
                or any(candidate.get(key) != val or record.get(key) != val for key, val in scope.items())
                or str(candidate.get("id")) != str(proof.canonical_candidate_id)
                or candidate.get("runId") != prior.run.id or candidate.get("fieldKey") != field
                or candidate.get("state") != str(value.state)
                or candidate.get("parsedValue") != _parsed(value, ordinary=proof.candidate_contract == "ordinary-pr168/v2")
                or candidate.get("normalizedValue") != value.normalized or candidate.get("authorityId") != value.authority_id
                or str(record.get("id")) != str(proof.canonical_record_version_id) or record.get("runId") != prior.run.id
                or len(current_rows) != 1 or str(current_rows[0].get("candidateId")) != str(proof.canonical_candidate_id)
                or str(resolved.get("recordVersionId")) != str(proof.canonical_record_version_id)
                or str(resolved.get("candidateId")) != str(proof.canonical_candidate_id)
                or resolved.get("fieldKey") != field or resolved.get("state") != str(value.state)):
            unavailable("canonical_lineage_consumed_source_unproved")
        ordered.append({"ordinal": ordinal, "researchFieldKey": str(pin.field_key), "canonicalFieldKey": field,
            "sourceRevision": pin.revision, "dependencyResolutionDigest": pin.digest,
            "sourceCheckpointId": native["id"], "sourceCheckpointDigest": digest(native),
            "sourceTypedCheckpointDigest": digest(original), "sourceRunId": str(proof.canonical_run_id),
            "sourceCandidateId": str(proof.canonical_candidate_id), "sourceRecordVersionId": str(proof.canonical_record_version_id),
            "sourceCandidateDigest": proof.candidate_digest, "sourceRecordDigest": proof.record_digest,
            "sourcePublicationLineageDigest": proof.source_publication_lineage_digest,
            "sourceRecordFieldsDigest": proof.record_projection_digest, "sourceRecordFields": list(source_rows)})
    return ordered


def _native_Int64_size(value):
    """Actual native Int64 JSON form; retain it verbatim in the source proof."""
    maximum = (1 << 63) - 1
    if type(value) is int and 0 <= value <= maximum:
        return value
    if (type(value) is str and 1 <= len(value) <= 19
            and (len(value) == 1 or value[0] != "0")
            and all(char in "0123456789" for char in value) and int(value) <= maximum):
        return int(value)
    unavailable("canonical_lineage_transcription_raw_asset_unproved")


def _decided_source(run, region_id, observation_id, context):
    """Join decided text to actual native transcription, decision and members."""
    transcripts = [item for item in run.transcripts if item.region_id == region_id
        and item.resolved is True and item.text and observation_id in item.observation_ids]
    proofs = [item for item in context.transcription_proofs if isinstance(item, NativeTranscriptionDecisionProofV2)
        and item.region_id == region_id]
    if len(transcripts) != 1 or len(proofs) != 1:
        unavailable("canonical_lineage_selected_transcription_unproved")
    transcript, proof = transcripts[0], proofs[0]
    outer = {"organizationId": context.scope.organization_id, "collectionId": context.scope.collection_id}
    observations = {item.id: item for item in run.observations}
    if (len(observations) != len(run.observations) or not transcript.observation_ids
            or len(set(transcript.observation_ids)) != len(transcript.observation_ids)
            or any(key not in observations or observations[key].region_id != region_id for key in transcript.observation_ids)
            or type(proof.region_row) is not dict or any(proof.region_row.get(key) != value for key, value in outer.items())
            or proof.region_row.get("runId") != run.id or proof.region_row.get("id") != _region_row(run.id, region_id)
            or proof.region_row.get("domainRegionId") != region_id
            or context.transcription_ids is not None and context.transcription_ids.get(region_id) != proof.transcription_version_id):
        unavailable("canonical_lineage_selected_transcription_unproved")

    used_raw_refs = set()

    def asset(ref, kind):
        selected = [item for item in proof.raw_assets if item.original_ref == ref]
        calls = [item for item in run.observations if item.raw_ref == ref]
        if transcript.first_pass_call is not None and transcript.first_pass_call.raw_ref == ref:
            calls.append(transcript.first_pass_call)
        if len(selected) != 1 or not calls:
            unavailable("canonical_lineage_transcription_raw_asset_unproved")
        row = selected[0].row
        stored_sha = ref.partition(":")[0]
        if (type(row) is not dict or any(row.get(key) != value for key, value in outer.items())
                or row.get("specimenId") != context.scope.specimen_id or row.get("kind") != kind
                or any(type(row.get(key)) is not str or not row[key] for key in ("id", "bucket", "objectName", "generation", "sha256", "mimeType"))
                or len(stored_sha) != 64 or any(char not in "0123456789abcdef" for char in stored_sha)
                or row["sha256"] != stored_sha
                or row["id"] != derived_id("asset", context.scope.specimen_id, row["bucket"], row["objectName"], row["generation"])
                or any(type(call.raw_sha256) is not str or len(call.raw_sha256) != 64
                    or any(char not in "0123456789abcdef" for char in call.raw_sha256) for call in calls)):
            unavailable("canonical_lineage_transcription_raw_asset_unproved")
        _native_Int64_size(row.get("byteSize"))
        try:
            UUID(row["id"])
        except (ValueError, TypeError, AttributeError):
            unavailable("canonical_lineage_transcription_raw_asset_unproved")
        used_raw_refs.add(ref)
        return row["id"]

    expected = _first_pass(run, transcript, asset, {}, reviewer=True)
    expected_rows = tuple({"operation": row.operation, "variables": {**outer, **row.variables}} for row in expected)
    if proof.decision_rows != expected_rows:
        unavailable("canonical_lineage_transcription_decision_unproved")
    versions = [row["variables"] for row in expected_rows if row["operation"] == "AppendTranscriptionVersionV2"]
    if (len(versions) != 1 or versions[0]["id"] != str(proof.transcription_version_id)
            or versions[0]["unresolved"] is not False):
        unavailable("canonical_lineage_selected_transcription_unproved")
    expected_readers = tuple({"operation": "AppendModelObservationV2", "variables": {
        **outer, **_reading(run, observations[key], asset(observations[key].raw_ref, "raw_response")).variables}}
        for key in transcript.observation_ids)
    if proof.reader_rows != expected_readers:
        unavailable("canonical_lineage_transcription_members_unproved")
    if (len(proof.raw_assets) != len(used_raw_refs)
            or {item.original_ref for item in proof.raw_assets} != used_raw_refs):
        unavailable("canonical_lineage_transcription_raw_asset_members_unproved")
    return transcript.text, str(proof.transcription_version_id), proof


def _readings(value, run, context):
    observations = {item.id: item for item in run.observations}
    if len(observations) != len(run.observations):
        unavailable("canonical_lineage_reading_identity_ambiguous")
    rows = []
    for reading, literal in value.verbatim_by_observation.items():
        native = observations.get(reading)
        fragments = tuple(item for item in context.original_request.fragments if item.observation_id == reading)
        routes = {item.input_source for item in fragments}
        declared = value.input_source_by_observation.get(reading, value.input_source)
        if native is None or not fragments or len(routes) != 1 or declared is not None and declared not in routes:
            unavailable("canonical_lineage_reading_unproved")
        route = next(iter(routes))
        if route == "raw_reading":
            text, transcription, raw_object_digest = native.literal_text, None, None
        elif route == "decided_transcript":
            text, transcription, proof = _decided_source(run, native.region_id, reading, context)
            raw_object_digest = next(item.row["sha256"] for item in proof.raw_assets if item.original_ref == native.raw_ref)
        else:
            unavailable("canonical_lineage_reading_unproved")
        if (not literal or literal not in text or not native.raw_ref or not native.raw_sha256
                or value.source_region_id is not None and value.source_region_id != native.region_id
                or any(item.scope != context.original_request.scope or item.region_id != native.region_id
                    or item.observation_text != text or item.observation_digest != hashlib.sha256(text.encode()).hexdigest()
                    or type(item.start) is not int or type(item.end) is not int
                    or not 0 <= item.start < item.end <= len(text) or item.literal != text[item.start:item.end] for item in fragments)):
            unavailable("canonical_lineage_reading_unproved")
        # The unique route is proved by every original fragment, never inferred
        # from an absent FieldValue default or a selected reader.
        rows.append({"observationId": str(UUID(reading)), "regionId": str(UUID(native.region_id)),
            "literal": literal, "inputSource": route, "rawRef": native.raw_ref, "rawDigest": native.raw_sha256,
            "rawObjectDigest": raw_object_digest,
            "transcriptionVersionId": transcription,
            "fragments": [item.model_dump(mode="json") for item in fragments]})
    if (not set(value.settled_observation_ids) <= set(value.verbatim_by_observation)
            or value.source_observation_id is not None and (
                value.source_observation_id not in value.verbatim_by_observation
                or value.source_observation_id not in value.settled_observation_ids
                or value.source_observation_id not in {item.observation_id for item in context.original_request.fragments})):
        unavailable("canonical_lineage_selected_reading_unproved")
    transcript = None
    if value.input_source == "decided_transcript":
        selected = [row for row in rows if row["inputSource"] == "decided_transcript" and row["regionId"] == value.source_region_id]
        identities = {row["transcriptionVersionId"] for row in selected}
        if not selected or len(identities) != 1 or None in identities:
            unavailable("canonical_lineage_selected_transcription_unproved")
        transcript = next(iter(identities))
    return rows, transcript


def _literal_grounding(value, resolution, reading_rows, request):
    """Retain raw/assembly proof without inventing or selecting a reader.

    Matching a full observation outside the original target fragments cannot
    ground a candidate literal. A joined literal needs the exact original
    target assembly, deterministically reconstructed from proven fragments.
    The native consumer must independently re-read these inputs and recompute.
    """
    if value.literal is None:
        return {"kind": "absent", "literal": None}
    if type(value.literal) is not str or not value.literal:
        unavailable("canonical_lineage_literal_unproved")
    original = {item.id: item for item in request.fragments}
    proven = {item["id"]: item for row in reading_rows for item in row["fragments"]}
    if len(original) != len(request.fragments):
        unavailable("canonical_lineage_literal_fragment_identity_ambiguous")
    raw = [item.model_dump(mode="json") for item in request.fragments
        if item.id in proven and item.model_dump(mode="json") == proven[item.id]
        and value.literal in item.literal
        and any(row["observationId"] == item.observation_id and value.literal in row["literal"] for row in reading_rows)]
    if raw:
        return {"kind": "original_fragment", "literal": value.literal, "fragments": raw}
    assemblies = {item.id: item for item in request.assemblies}
    events = {item.id: item for item in request.events}
    relations = {item.id: item for item in request.relations}
    if (len(assemblies) != len(request.assemblies) or len(events) != len(request.events)
            or len(relations) != len(request.relations)):
        unavailable("canonical_lineage_literal_assembly_identity_ambiguous")
    proofs = []
    for key in resolution.assembly_ids:
        assembly = assemblies.get(key)
        if (assembly is None or assembly.scope != request.scope or assembly.field_key != resolution.field_key
                or assembly.event_id != resolution.event_id or assembly.interpreted_text != value.literal
                or not set(assembly.fragment_ids) <= set(proven)
                or any(original.get(fid) is None or original[fid].model_dump(mode="json") != proven[fid]
                    for fid in assembly.fragment_ids)):
            continue
        validate_assembly(request, assembly)
        proofs.append({"assembly": assembly.model_dump(mode="json"), "assemblyDigest": digest(assembly),
            "event": events[assembly.event_id].model_dump(mode="json"),
            "relations": [relations[rid].model_dump(mode="json") for rid in assembly.relation_ids],
            "fragments": [original[fid].model_dump(mode="json") for fid in assembly.fragment_ids]})
    if not proofs:
        unavailable("canonical_lineage_literal_unproved")
    return {"kind": "original_target_assembly", "literal": value.literal, "assemblies": proofs}


def project_canonical_value_v2(principal: Principal, *, prior: Specimen, result: Specimen,
        checkpoint: FieldCheckpoint, context: CanonicalLineageContextV2) -> CanonicalValueProjectionV2:
    """Faithfully project one validated value and all20 normalized field references.

    Policy disposition/reasons arrive from the separately qualified V2 producer;
    this pure mapping never treats a supplied policy outcome as native authority.
    Native V2 must prove access, captures, policy, complete causal ancestry, the
    exact preparation and current CAS, then commit all outputs atomically.
    """
    if not isinstance(context, CanonicalLineageContextV2):
        unavailable("canonical_lineage_current_basis_unproved")
    snapshot_proof = _prior_snapshot(prior, context)
    scope = context.scope
    if (type(context.prior_revision) is not int
            or context.prior_revision < 1 or prior.version != context.prior_revision
            or type(prior.version) is not int or type(result.version) is not int or result.version != prior.version + 1
            or principal.user_id != context.actor_uid or principal.scope != prior.scope
            or principal.scope.organization_id != scope.organization_id or principal.scope.collection_id != scope.collection_id
            or prior.id != scope.specimen_id or result.id != prior.id or result.scope != prior.scope
            or result.asset != prior.asset or result.run.id != prior.run.id
            or prior.asset.sensitive != scope.sensitive or checkpoint.scope != scope
            or canonical_digest(prior.model_dump(mode="json")) != context.prior_snapshot_sha256
            or set(prior.run.fields) != CANONICAL_KEYS or set(result.run.fields) != CANONICAL_KEYS
            or set(context.field_mapping) != RESEARCH_KEYS or set(context.field_mapping.values()) != CANONICAL_KEYS
            or len(set(context.field_mapping.values())) != 20
            or set(context.human_locks) != CANONICAL_KEYS or any(type(lock) is not bool for lock in context.human_locks.values())):
        unavailable("canonical_lineage_current_basis_unproved")
    target = context.field_mapping[str(checkpoint.field_key)]
    if context.human_locks[target]:
        unavailable("canonical_lineage_target_human_locked")
    native, original = _checkpoint(context, checkpoint)
    if (context.original_request.scope != original.scope or context.original_request.prompt.digest != original.prompt_digest
            or context.original_request.prompt.source_registry_digest != original.source_registry_digest):
        unavailable("canonical_lineage_original_request_unproved")
    validate_checkpoint_resolution_v2(context, original)
    if original.resolution.work_state not in {WorkState.RESOLVED, WorkState.WAITING_HUMAN, WorkState.NONBLOCKING_EXCEPTION}:
        unavailable("canonical_lineage_target_not_publishable")
    expected = _value(original.resolution, context)
    if result.run.fields[target] != expected:
        unavailable("canonical_lineage_scientific_value_changed")
    if any(result.run.fields[key] != prior.run.fields[key] for key in CANONICAL_KEYS - {target}):
        unavailable("canonical_lineage_other19_changed")
    mutable = {"fields", "reasons", "disposition", "stage", "evidence", "tool_calls"}
    old_run = prior.run.model_dump(mode="json")
    new_run = result.run.model_dump(mode="json")
    if (result.previous_runs != prior.previous_runs or result.audit != prior.audit
            or result.history_through_revision != prior.history_through_revision
            or any(new_run[key] != value for key, value in old_run.items() if key not in mutable)
            or len({item.id for item in result.run.evidence}) != len(result.run.evidence)
            or len({item.call_key for item in result.run.tool_calls}) != len(result.run.tool_calls)
            or result.run.evidence[:len(prior.run.evidence)] != prior.run.evidence
            or result.run.tool_calls[:len(prior.run.tool_calls)] != prior.run.tool_calls):
        unavailable("canonical_lineage_retained_history_changed")
    old = context.prior_projection
    if (len(old) != 20 or {row.get("fieldKey") for row in old} != CANONICAL_KEYS
            or any(str(row.get("recordVersionId")) != str(context.prior_record_version_id) for row in old)):
        unavailable("canonical_lineage_prior20_unproved")
    sources = _source_lineage(context, prior, original, context.consumed_sources)
    derivation = original.resolution.derivation
    if expected.layer == "derived" and derivation is None:
        unavailable("canonical_lineage_derivation_missing")
    reading_rows, transcript = _readings(expected, result.run, context)
    literal_grounding = _literal_grounding(expected, original.resolution, reading_rows, context.original_request)
    candidate = UUID(derived_id(CONTRACT, "candidate", prior.run.id, native["id"], digest(expected))) if expected.state == ValueState.SUPPORTED else None
    candidates = {row["fieldKey"]: row.get("candidateId") for row in old}
    candidates[target] = str(candidate) if candidate else None
    record_writes = _record(result.run, candidates, {item.id for item in result.run.evidence})
    record = next(item.variables for item in record_writes if item.operation == "AppendRecordVersionV2")
    record_id = UUID(derived_id(CONTRACT, "record", str(context.prior_record_version_id), prior.run.id, digest(record)))
    normalized = []
    for write in record_writes:
        row = dict(write.variables)
        if write.operation == "AppendRecordVersionV2":
            row.update(id=str(record_id), predecessorId=str(context.prior_record_version_id))
        elif write.operation == "AppendResolvedFieldV2":
            row.update(id=derived_id(str(record_id), "field", row["fieldKey"]), recordVersionId=str(record_id))
            retained = next(item for item in old if item["fieldKey"] == row["fieldKey"])
            if (row["fieldGroup"] != retained.get("fieldGroup")
                    or row["fieldKey"] != target and any(row.get(key) != retained.get(key) for key in ("candidateId", "state"))):
                unavailable("canonical_lineage_retained_native_field_changed")
        elif write.operation == "AppendValidationFindingV2":
            row.update(id=derived_id(CONTRACT, "finding", str(record_id), row["id"]), recordVersionId=str(record_id))
        else:
            unavailable("canonical_lineage_record_operation_unproved")
        normalized.append(Write(write.operation, row, write.operation + ":" + row["id"]))
    target_writes = []
    if candidate:
        selected = expected.source_observation_id
        row = {"id": str(candidate), "runId": prior.run.id, "fieldKey": target, "state": str(expected.state),
            "literalValue": expected.literal, "parsedValue": expected.parsed, "normalizedValue": expected.normalized,
            "authorityId": expected.authority_id, "derivation": expected.layer, "inputSource": expected.input_source,
            "sourceTranscriptionId": transcript, "sourceObservationId": selected}
        target_writes.append(Write("AppendFieldCandidateLineageV2", row, "candidate:" + str(candidate)))
        canonical_ids = {item.id for item in result.run.evidence}
        for evidence in expected.evidence_ids:
            relation = expected.evidence_relations.get(evidence)
            original_ids = [key for key, mapped in context.evidence_id_mapping.items() if str(mapped) == evidence]
            scientific = (derivation is not None and len(original_ids) == 1 and original_ids[0] in derivation.evidence_ids)
            if evidence not in canonical_ids or (relation is None and not scientific):
                unavailable("canonical_lineage_candidate_evidence_unproved")
            if relation is not None:
                if relation not in {"decides", "supports", "contradicts"}:
                    unavailable("canonical_lineage_candidate_evidence_unproved")
                row = {"id": derived_id("candidate-evidence", str(candidate), evidence), "candidateId": str(candidate),
                    "evidenceId": evidence, "relation": relation}
                target_writes.append(Write("AppendCandidateEvidenceLineageV2", row, "candidate-evidence:" + row["id"]))
        lineage_id = derived_id(CONTRACT, "lineage", str(candidate), str(record_id))
        lineage = {"id": lineage_id, "contractVersion": CONTRACT, "runId": prior.run.id, "specimenId": prior.id,
            "candidateId": str(candidate), "recordVersionId": str(record_id), "predecessorId": str(context.prior_record_version_id),
            "priorRevision": prior.version, "resultRevision": result.version, "fieldKey": target,
            "priorNativeSnapshotDigest": snapshot_proof["native"], "priorGraphSnapshotDigest": snapshot_proof["graph"],
            "priorActiveGraphDigest": snapshot_proof["active_graph"],
            "researchFieldKey": str(original.field_key), "layer": expected.layer,
            "resolutionDigest": digest(original.resolution), "typedCheckpointDigest": digest(original),
            "nativeCheckpointId": native["id"], "nativeCheckpointDigest": digest(native),
            "originalRequestDigest": digest(context.original_request), "originalScope": original.scope.model_dump(mode="json"),
            "derivation": derivation.model_dump(mode="json") if derivation else None,
            "derivationDigest": digest(derivation) if derivation else None,
            "scientificSourceDigest": derivation.source_digest if derivation else None,
            "precision": expected.precision, "centuryRule": expected.century_rule,
            "readingSources": reading_rows, "literalGrounding": literal_grounding,
            "selectedObservationId": selected, "selectedTranscriptionId": transcript,
            "settledObservationIds": list(expected.settled_observation_ids), "evidenceIds": list(expected.evidence_ids),
            "evidenceRelations": dict(expected.evidence_relations), "consumedDependencies": sources}
        target_writes.append(Write("AppendCanonicalValueLineageV2", lineage, "lineage:" + lineage_id))
        for evidence in expected.evidence_ids:
            original_ids = [key for key, mapped in context.evidence_id_mapping.items() if str(mapped) == evidence]
            if len(original_ids) != 1:
                unavailable("canonical_lineage_original_evidence_ambiguous")
            scientific = derivation is not None and original_ids[0] in derivation.evidence_ids
            row = {"id": derived_id(CONTRACT, "evidence", lineage_id, evidence), "lineageId": lineage_id,
                "evidenceId": evidence, "researchEvidenceId": original_ids[0],
                "associationKind": "original_derivation_record" if scientific else "original_value_evidence",
                "originalRelation": expected.evidence_relations.get(evidence)}
            target_writes.append(Write("AppendCanonicalValueEvidenceV2", row, "value-evidence:" + row["id"]))
        for source in sources:
            row = {"id": derived_id(CONTRACT, "dependency", lineage_id, str(source["ordinal"])),
                "lineageId": lineage_id, **source}
            target_writes.append(Write("AppendCanonicalValueDependencyV2", row, "dependency:" + row["id"]))
    return CanonicalValueProjectionV2(CONTRACT, target, candidate, record_id, context.prior_record_version_id,
        prior.version, result.version, canonical_digest(result.model_dump(mode="json")), tuple(target_writes), tuple(normalized),
        digest({"target": [{"operation": row.operation, "variables": row.variables} for row in target_writes],
                "record": [{"operation": row.operation, "variables": row.variables} for row in normalized]}))


def project_tool_input_lineage_v2(principal: Principal, *, prior: Specimen,
        checkpoint: FieldCheckpoint, context: CanonicalLineageContextV2,
        contribution: CapturedCanonicalEvidenceV2) -> tuple[Write, ...]:
    """Pure map of an actual captured request, input lineage and durable attempt.

    Native V2 must transaction-read/reverify the contribution and its immutable
    body/input refs before atomically appending these rows with the value. This
    function never obtains authority from a supplied type, hash or native ID.
    Empty/mixed inputs remain honest; no legacy producer/reader is invented.
    """
    if not isinstance(context, CanonicalLineageContextV2) or not isinstance(contribution, CapturedCanonicalEvidenceV2):
        unavailable("canonical_tool_lineage_unproved")
    _prior_snapshot(prior, context)
    native, original = _checkpoint(context, checkpoint)
    try:
        item = CapturedCanonicalEvidenceV2.model_validate(contribution.model_dump(mode="json"))
    except (ValueError, TypeError, AttributeError):
        unavailable("canonical_tool_lineage_unproved")
    request, execution, proof, lineage = item.original_specialist_request, item.tool_execution, item.proof, item.tool_input_lineage
    scope = context.scope
    tools = [tool for tool in context.tool_results if tool.model_copy(update={"receipt": None}) == item.source_result
        and tool.receipt is not None and tool.receipt.scope == request.scope
        and tool.receipt.effect_status == "completed" and tool.receipt.effect_id == proof.receipt.effect_id
        and tool.receipt.request_digest == proof.receipt.request_digest and tool.receipt.binding_digest == proof.receipt.binding_digest
        and tool.receipt.capture_locator == proof.receipt.capture.locator]
    if (principal.user_id != context.actor_uid or principal.scope != prior.scope
            or principal.scope.organization_id != scope.organization_id or principal.scope.collection_id != scope.collection_id
            or prior.id != scope.specimen_id or request != context.original_request or request.scope != original.scope
            or request.prompt.digest != original.prompt_digest or request.prompt.source_registry_digest != original.source_registry_digest
            or len(tools) != 1 or item.evidence not in item.source_result.evidence
            or execution.effect_id not in original.effect_receipt_ids
            or execution.field_keys != (context.field_mapping[str(original.field_key)],)
            or str(item.canonical_run_id) != prior.run.id or lineage.canonical_run_id != item.canonical_run_id
            or tuple(lineage.fragments) != tuple(request.fragments)
            or tuple(str(value) for value in lineage.observation_ids) != tuple(str(value) for value in item.canonical_observation_ids)
            or lineage.selected_observation_id != (UUID(original.resolution.value.source_observation_id) if original.resolution.value.source_observation_id else None)
            or item.canonical_evidence.source != execution.source
            or context.evidence_id_mapping.get(item.evidence.id) != UUID(item.canonical_evidence.id)):
        unavailable("canonical_tool_lineage_unproved")
    if (execution.attempt_id not in tools[0].receipt.attempt_ids
            or proof.receipt.attempt_id not in tools[0].receipt.attempt_ids):
        unavailable("canonical_tool_lineage_attempt_unproved")
    # Preserve the exact captured raw or decided-transcript input membership.
    # Actual retained native generation/body admission is the native consumer's
    # obligation; this pure mapping also rejects drift in the policy graph.
    observations = {row.id: row for row in prior.run.observations}
    regions = {row.id: row for row in prior.run.regions}
    native_inputs = {str(row.observation_id): row for row in lineage.native_inputs}
    if len(observations) != len(prior.run.observations) or len(regions) != len(prior.run.regions) or len(native_inputs) != len(lineage.native_inputs):
        unavailable("canonical_tool_lineage_input_unproved")
    transcription_proofs = {}
    for fragment in lineage.fragments:
        reading, retained = observations.get(fragment.observation_id), native_inputs.get(fragment.observation_id)
        text = reading.literal_text if reading is not None else None
        if fragment.input_source == "decided_transcript":
            text, _, transcription_proof = _decided_source(prior.run, fragment.region_id, fragment.observation_id, context)
            transcription_proofs[fragment.region_id] = transcription_proof.model_dump(mode="json")
        elif fragment.input_source != "raw_reading":
            unavailable("canonical_tool_lineage_input_unproved")
        if (reading is None or retained is None or fragment.region_id not in regions
                or reading.region_id != fragment.region_id or fragment.asset_id != prior.asset.id or fragment.asset_digest != prior.asset.sha256
                or fragment.model_id != reading.model_id or fragment.observation_text != text
                or fragment.observation_digest != hashlib.sha256(text.encode()).hexdigest()
                or type(fragment.start) is not int or type(fragment.end) is not int
                or not 0 <= fragment.start < fragment.end <= len(text) or text[fragment.start:fragment.end] != fragment.literal
                or retained.observation_digest != canonical_digest(reading.model_dump(mode="json"))
                or retained.input_sha256 != reading.input_sha256 or retained.raw_sha256 != reading.raw_sha256
                or retained.raw_ref != reading.raw_ref or retained.request_sha256 != reading.request_sha256):
            unavailable("canonical_tool_lineage_input_unproved")
    lineage_id = derived_id("research-tool-input-lineage/v2", prior.run.id, execution.effect_id, execution.attempt_id, digest(lineage))
    outer = {"organizationId": scope.organization_id, "collectionId": scope.collection_id}
    row = {**outer, "id": lineage_id, "contractVersion": lineage.contract_version, "specimenId": prior.id, "runId": prior.run.id,
        "evidenceId": item.canonical_evidence.id, "nativeCheckpointId": native["id"], "nativeCheckpointDigest": digest(native),
        "originalRequestDigest": digest(request), "originalScope": request.scope.model_dump(mode="json"),
        "originalRequest": request.model_dump(mode="json"), "queryDigest": lineage.query_digest,
        "query": execution.arguments.model_dump(mode="json"), "effectId": execution.effect_id, "attemptId": execution.attempt_id,
        "receiptDigest": proof.receipt.receipt_digest, "receiptBindingDigest": digest(proof.receipt), "sourcePolicyDigest": item.source_policy_digest,
        "capturePolicyDigest": proof.capture_policy_digest, "sourceRegistryDigest": item.source_registry_digest,
        "canonicalMappingDigest": item.canonical_mapping_digest, "sourceCaptureProof": proof.model_dump(mode="json"),
        "fragments": [value.model_dump(mode="json") for value in lineage.fragments],
        "fragmentDigests": [digest(value) for value in lineage.fragments],
        "observationIds": [str(value) for value in lineage.observation_ids], "regionIds": [str(value) for value in lineage.region_ids],
        "inputSources": list(lineage.input_sources), "nativeInputs": [value.model_dump(mode="json") for value in lineage.native_inputs],
        "selectedObservationId": str(lineage.selected_observation_id) if lineage.selected_observation_id else None,
        "nativeTranscriptionProofs": [transcription_proofs[key] for key in sorted(transcription_proofs)],
        "legacyProducerDigest": digest(item.canonical_producer) if item.canonical_producer else None}
    executed = {**outer, "id": derived_id("research-tool-execution/v2", lineage_id, digest(execution)),
        "contractVersion": execution.contract_version, "lineageId": lineage_id, "runId": prior.run.id, "evidenceId": item.canonical_evidence.id,
        "execution": execution.model_dump(mode="json"), "executionDigest": digest(execution), "effectId": execution.effect_id, "attemptId": execution.attempt_id}
    return (Write("AppendToolInputLineageV2", row, "tool-input-lineage:" + lineage_id),
        Write("AppendCapturedToolExecutionV2", executed, "captured-tool-execution:" + executed["id"]))
