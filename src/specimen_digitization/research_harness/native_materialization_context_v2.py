"""Native-only producer contexts; acceptance bodies come from the journal reader.

No HTTP/model mapping is accepted here. The native loader owns access, the
coherent SQL read and blob hydration; these checks preserve that read's facts.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Mapping
from uuid import UUID

from specimen_digitization.application.domain import Specimen
from specimen_digitization.application.projection import _first_pass, _reading, _region_row
from specimen_digitization.application.storage import digest as graph_digest
from .accepted_output import AcceptedCheckpointProofV1
from .canonical_projection_v2 import (
    CanonicalLineageContextV2, ConsumedCanonicalSourceV2, NativePriorSnapshotProofV2,
    NativeRawSourceAssetProofV2, NativeTranscriptionDecisionProofV2, _checkpoint,
    _prior_snapshot, _source_lineage,
)
from .compatibility import PublicationUnavailable
from .contracts import FieldCheckpoint, digest
from .native_canonical import CANONICAL_KEYS
from .publication import NativeDependencyBasis

INPUT_KEYS = frozenset({"contract_version", "observed_at", "registration", "outer_intent",
    "scoped_state", "private_state_integrity", "current_snapshot", "preparation_snapshot",
    "retained_history", "projection_rows", "checkpoint_inputs", "original_request_sources",
    "captured_executions", "native_input_rows", "lineage_rows", "prepack_proof"})
NORMALIZATION_VERSION = "native-query-rows-to-write-variables/v2"
TIMESTAMP_COLUMNS = frozenset({"capturedAt", "startedAt", "completedAt"})
TIMESTAMP_WIRE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z")


def hold(code):
    raise PublicationUnavailable(code)


def _one(rows, predicate, code):
    matches = [row for row in rows if predicate(row)]
    if len(matches) != 1:
        hold(code)
    return matches[0]


def canonical_prior_projection_v2(rows, record_id):
    """Normalize the public six-column projection into canonical field order.

    The full native row arrays remain untouched in inputs/native guard. Their
    query order is by UUID; the existing public view is ordered by fieldKey.
    No scientific row, identity or candidate/state distinction is discarded.
    """
    keys = {"id", "recordVersionId", "candidateId", "fieldKey", "state", "fieldGroup"}
    permitted = keys | {"organizationId", "collectionId", "createdAt"}
    selected = []
    for row in rows:
        if type(row) is not dict or not keys <= set(row) or not set(row) <= permitted:
            hold("canonical_native_projection_row_shape_unproved")
        if row["recordVersionId"] == str(record_id):
            selected.append({key:copy.deepcopy(row[key]) for key in keys})
    if (len(selected) != 20 or {row["fieldKey"] for row in selected} != CANONICAL_KEYS
            or len({row["id"] for row in selected}) != 20):
        hold("canonical_native_projection_whole20_unproved")
    return tuple(sorted(selected, key=lambda row:row["fieldKey"]))


def _normalized_native_row(raw, expected, outer):
    """Only server createdAt is outside the complete scoped write ABI.

    Retain the original row separately in the bundle's native input digest.
    Unknown scientific columns, omitted columns and changed nulls are refused.
    """
    if type(raw) is not dict or any(raw.get(k) != v for k, v in outer.items()):
        hold("canonical_native_row_scope_unproved")
    normalized = {k: copy.deepcopy(v) for k, v in raw.items() if k != "createdAt"}
    # PostgreSQL Timestamp JSON can spell a proven identical instant with a
    # different offset/fractional suffix. Only these three typed timestamp
    # columns receive this explicit versioned normalization; both original
    # spellings remain covered by native input/producer graph digests.
    for key in TIMESTAMP_COLUMNS & normalized.keys() & expected.keys():
        if normalized[key] == expected[key]:
            continue
        actual, original = normalized[key], expected[key]
        if (type(actual) is not str or type(original) is not str
                or TIMESTAMP_WIRE.fullmatch(actual) is None or TIMESTAMP_WIRE.fullmatch(original) is None):
            hold("canonical_native_timestamp_wire_unproved")
        try:
            actual_time = datetime.fromisoformat(actual.replace("Z", "+00:00")).astimezone(timezone.utc)
            original_time = datetime.fromisoformat(original.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            hold("canonical_native_timestamp_wire_unproved")
        if actual_time != original_time:
            hold("canonical_native_timestamp_instant_changed")
        normalized[key] = original
    if normalized != expected:
        hold("canonical_native_row_write_normalization_unproved")
    return normalized


@dataclass(frozen=True)
class OriginalRequestProofV2:
    accepted_checkpoint_proof: AcceptedCheckpointProofV1
    original_checkpoint: FieldCheckpoint
    native_checkpoint_id: str
    native_checkpoint_digest: str

    @property
    def request(self):
        return self.accepted_checkpoint_proof.acceptance.original_request

    @property
    def tool_results(self):
        return self.accepted_checkpoint_proof.acceptance.source_results

    @property
    def accepted_resolution(self):
        return _one(self.accepted_checkpoint_proof.acceptance.resolutions,
            lambda row: row.field_key == self.original_checkpoint.field_key,
            "canonical_accepted_target_resolution_ambiguous")


def _accepted_original(context, checkpoint, accepted):
    if not isinstance(accepted, AcceptedCheckpointProofV1):
        hold("canonical_accepted_checkpoint_proof_unavailable")
    # Re-run the actual validator and journal transform, rather than trusting a
    # type produced with model_construct or a caller-supplied version string.
    verified = AcceptedCheckpointProofV1.model_validate(accepted.model_dump(mode="json"))
    native, original = _checkpoint(context, checkpoint)
    selected = _one(verified.checkpoints, lambda cp: cp.field_key == checkpoint.field_key,
        "canonical_accepted_checkpoint_ambiguous")
    pointer = native.get("accepted_output_proof")
    request = verified.acceptance.original_request
    if (selected != original or type(pointer) is not dict
            or pointer.get("proof_digest") != verified.proof_digest
            or pointer.get("request_digest") != digest(request)
            or pointer.get("native_run_id") != verified.acceptance.native_run_id
            or pointer.get("conversation_id") != verified.acceptance.conversation_id
            or pointer.get("checkpoint_payload_digests") != [digest(cp) for cp in verified.checkpoints]):
        hold("canonical_accepted_checkpoint_native_binding_unproved")
    if (request.scope != original.scope or original.field_key not in request.field_keys
            or request.prompt.digest != original.prompt_digest
            or request.prompt.source_registry_digest != original.source_registry_digest):
        hold("canonical_accepted_original_request_unproved")
    return OriginalRequestProofV2(verified, original, native["id"], digest(native))


def native_acceptance_context_v2(*, native_inputs, binding, prepared, prior,
        accepted_checkpoint_proofs, active_graph_bytes=None):
    """Verify the target before any source capture or canonical blob write."""
    if set(native_inputs) != INPUT_KEYS or native_inputs["scoped_state"] != binding.registration.read_bundle:
        hold("canonical_native_capture_inputs_unproved")
    checkpoint = FieldCheckpoint.model_validate(native_inputs["checkpoint_inputs"]["target"])
    if checkpoint != prepared.publication.checkpoints[0]:
        hold("canonical_native_capture_checkpoint_changed")
    accepted = accepted_checkpoint_proofs.get(str(checkpoint.field_key))
    if not isinstance(accepted, AcceptedCheckpointProofV1):
        hold("canonical_historical_accepted_output_proof_unavailable")
    reg = binding.registration
    projection = canonical_prior_projection_v2(native_inputs["projection_rows"]["resolved_fields"],
        binding.canonical.record_version_id)
    context = CanonicalLineageContextV2(scope=prepared.basis.scope, actor_uid=prepared.basis.actor_uid,
        prior_record_version_id=binding.canonical.record_version_id, prior_revision=prior.version,
        prior_snapshot_sha256=graph_digest(prior.model_dump(mode="json")),
        native_prior_snapshot=NativePriorSnapshotProofV2(binding.canonical,
            copy.deepcopy(native_inputs["current_snapshot"]["snapshot"]), active_graph_bytes),
        job=reg.job, field_mapping=reg.field_mapping, evidence_id_mapping={}, human_locks=reg.human_locks,
        prior_projection=projection, original_request=accepted.acceptance.original_request,
        tool_results=accepted.acceptance.source_results, accepted_checkpoint_proof=accepted)
    _prior_snapshot(prior, context)
    return context, _accepted_original(context, checkpoint, accepted)


def _transcription_contexts(prior, native_inputs, scope, projection_services, requests):
    """Recompute complete decision/reader writes, then join exact native rows."""
    groups = native_inputs["native_input_rows"]
    outer = {"organizationId": scope.organization_id, "collectionId": scope.collection_id}
    assets = groups["assets"]
    observations = {item.id: item for item in prior.run.observations}
    proofs = []
    selected_regions = {fragment.region_id for request in requests for fragment in request.fragments
        if fragment.input_source == "decided_transcript"}
    for transcript in prior.run.transcripts:
        if transcript.region_id not in selected_regions or not transcript.resolved or not transcript.text:
            continue
        used = {}
        def asset(ref, kind):
            # Source refs are content-addressed object locators. The object's
            # SHA is separate from the observation's recorded response SHA.
            sha, separator, locator = ref.partition(":")
            if not separator or len(sha) != 64 or not locator:
                hold("canonical_native_raw_asset_ref_unproved")
            location = projection_services.locate(ref)
            matches = [row for row in assets if row.get("sha256") == sha
                and row.get("kind") == kind and row.get("specimenId") == prior.id
                and row.get("runId") in {None, prior.run.id}
                and row.get("objectName") == location.object_name
                and row.get("bucket") == location.bucket and row.get("generation") == location.generation]
            row = _one(matches, lambda _: True, "canonical_native_raw_asset_selection_unproved")
            if any(row.get(k) != v for k, v in outer.items()):
                hold("canonical_native_raw_asset_scope_unproved")
            raw = {k: copy.deepcopy(v) for k, v in row.items() if k != "createdAt"}
            # _decided_source verifies the full asset ABI and deterministic ID.
            used[ref] = NativeRawSourceAssetProofV2(original_ref=ref, row=raw)
            return row["id"]
        decision_writes = _first_pass(prior.run, transcript, asset, {}, reviewer=True)
        decision = []
        operation_groups = {"AppendTranscriptionVersionV2":"transcriptions",
            "AppendHarnessInputV1":"handoffs", "AppendReadingComparisonV1":"comparisons"}
        for write in decision_writes:
            expected = {**outer, **write.variables}
            group = operation_groups.get(write.operation)
            if group is None:
                hold("canonical_native_decision_operation_unproved")
            raw = _one(groups[group], lambda row: row.get("id") == expected["id"],
                "canonical_native_decision_row_unavailable")
            decision.append({"operation":write.operation,
                "variables":_normalized_native_row(raw, expected, outer)})
        readers = []
        for key in transcript.observation_ids:
            reading = observations.get(key)
            if reading is None:
                hold("canonical_native_transcription_member_unavailable")
            write = _reading(prior.run, reading, asset(reading.raw_ref, "raw_response"))
            expected = {**outer, **write.variables}
            raw = _one(groups["observations"], lambda row: row.get("id") == expected["id"],
                "canonical_native_transcription_reader_unavailable")
            readers.append({"operation":write.operation,
                "variables":_normalized_native_row(raw, expected, outer)})
        region_id = _region_row(prior.run.id, transcript.region_id)
        region = _one(groups["regions"], lambda row: row.get("id") == region_id,
            "canonical_native_transcription_region_unavailable")
        version = _one(decision, lambda row: row["operation"] == "AppendTranscriptionVersionV2",
            "canonical_native_transcription_version_ambiguous")["variables"]["id"]
        proofs.append(NativeTranscriptionDecisionProofV2(region_id=transcript.region_id,
            transcription_version_id=UUID(version),
            region_row={k: copy.deepcopy(v) for k, v in region.items() if k != "createdAt"},
            decision_rows=tuple(decision), reader_rows=tuple(readers), raw_assets=tuple(used.values())))
    return tuple(proofs)


def _sibling_winner(context, checkpoint, intent, native_inputs):
    from .publication_v2 import NativeCausalReceiptV2
    native, _ = _checkpoint(context, checkpoint)
    key = context.field_mapping[str(checkpoint.field_key)]
    winners = [NativeCausalReceiptV2.model_validate(row) for row in native_inputs["retained_history"]]
    matches = [row for row in winners if row.changed_field == key
        and row.checkpoint_outbox_key == "checkpoint/" + native["id"]]
    if not matches:
        return None
    winner = _one(matches, lambda _:True, "canonical_native_sibling_winning_receipt_ambiguous")
    committed = winner.after_state.get("jobs", {}).get(intent.job_key, {}).get("fields", {}).get(str(checkpoint.field_key), {}).get("checkpoint")
    if (winner.job_key != intent.job_key or winner.binding_id != intent.binding_id
            or winner.program_key != intent.program_key or winner.profile_digest != context.scope.profile_digest
            or winner.runtime_binding_digest != context.job["binding_digest"] or committed != native):
        hold("canonical_native_sibling_winning_receipt_scope_changed")
    return winner


def _consumed_sources(context, checkpoint, intent, native_inputs, prior, *, target=True):
    rows = native_inputs["projection_rows"]
    bases = intent.dependency_sources
    if not target:
        # A terminal sibling has its own winning immutable receipt; target
        # intent dependencies cannot stand in for the sibling's source intent.
        native, original = _checkpoint(context, checkpoint)
        canonical_key = context.field_mapping[str(checkpoint.field_key)]
        current = _one(rows["resolved_fields"], lambda row:
            row.get("recordVersionId") == str(context.prior_record_version_id)
            and row.get("fieldKey") == canonical_key, "canonical_native_sibling_projection_unavailable")
        winner = _sibling_winner(context, checkpoint, intent, native_inputs)
        if winner is None:
            hold("canonical_native_sibling_winning_receipt_unavailable")
        if current.get("candidateId") is not None:
            line = _one(native_inputs["lineage_rows"]["value_lineages"], lambda row:
                row.get("candidateId") == current["candidateId"]
                and row.get("nativeCheckpointId") == native["id"]
                and row.get("typedCheckpointDigest") == digest(original),
                "canonical_native_sibling_winning_lineage_unavailable")
            if str(winner.resulting.record_version_id) != line["recordVersionId"]:
                hold("canonical_native_sibling_lineage_receipt_changed")
        bases = winner.dependency_sources
    proofs = []
    for pin in checkpoint.resolution.dependencies:
        source = _one(bases, lambda item: item.field_key == pin.field_key,
            "canonical_native_dependency_intent_unavailable")
        from .publication import _native_checkpoint
        # These typed views were normalized by the native loader's exact
        # journal-reuse predicate; no ad-hoc scope rebinding is performed.
        inventory = [native_inputs["checkpoint_inputs"]["target"],
            *native_inputs["checkpoint_inputs"]["terminal_siblings"]]
        current = _one([FieldCheckpoint.model_validate(row) for row in inventory],
            lambda cp: cp.field_key == pin.field_key, "canonical_native_dependency_checkpoint_unavailable")
        native, original = _native_checkpoint(context.job, current, context.scope)
        if (current.revision != pin.revision or digest(current.resolution) != pin.digest
                or source.source_record_version_id != source.projection_record_version_id
                or source.checkpoint_id != native["id"] or source.checkpoint_digest != digest(native)
                or source.checkpoint_revision != current.revision or source.resolution_digest != pin.digest):
            hold("canonical_native_dependency_pointer_unproved")
        candidate = _one(rows["candidates"], lambda row: row.get("id") == str(source.candidate_id),
            "canonical_native_dependency_candidate_unavailable")
        record_id = str(source.source_record_version_id)
        record = _one(rows["record_versions"], lambda row: row.get("id") == record_id,
            "canonical_native_dependency_record_unavailable")
        projection = tuple(row for row in rows["resolved_fields"] if row.get("recordVersionId") == record_id)
        field = context.field_mapping[str(pin.field_key)]
        resolved = _one(projection, lambda row: row.get("fieldKey") == field,
            "canonical_native_dependency_projection_unavailable")
        value = prior.run.fields[field]
        # ScientificIntent uses the public six-column resolved view plus value;
        # raw native row digests below retain server metadata independently.
        six = {key:resolved[key] for key in ("id","recordVersionId","candidateId","fieldKey","state","fieldGroup")}
        if source.lineage_digest != digest({"resolved":six, "canonical_value":value.model_dump(mode="json")}):
            hold("canonical_native_dependency_scientific_basis_changed")
        lineage = [row for row in native_inputs["lineage_rows"]["value_lineages"]
            if row.get("candidateId") == str(source.candidate_id)]
        if len(lineage) > 1:
            hold("canonical_native_dependency_lineage_ambiguous")
        contract = "canonical-value-lineage/v2" if lineage else "ordinary-pr168/v2"
        publication_digest = digest(lineage[0]) if lineage else source.lineage_digest
        proofs.append(ConsumedCanonicalSourceV2(checkpoint=current,
            native_basis=NativeDependencyBasis(field_key=current.field_key, revision=current.revision,
                resolution_digest=digest(current.resolution), checkpoint_id=native["id"], checkpoint_digest=digest(native)),
            canonical_run_id=UUID(prior.run.id), canonical_candidate_id=source.candidate_id,
            canonical_record_version_id=source.source_record_version_id, canonical_field_key=field,
            candidate_contract=contract, candidate=copy.deepcopy(candidate), record=copy.deepcopy(record),
            resolved_field=copy.deepcopy(resolved), record_projection=copy.deepcopy(projection),
            record_projection_digest=digest(projection), candidate_digest=digest(candidate), record_digest=digest(record),
            source_publication_lineage_digest=publication_digest))
    return tuple(proofs)


@dataclass(frozen=True)
class NativeMaterializationInputBundleV2:
    target: object
    native_inputs_digest: str
    normalization_version: str
    original_request_proofs: Mapping[str, OriginalRequestProofV2]

    @classmethod
    def from_native_inputs(cls, *, native_inputs, current_binding, intent, preparation,
            prior: Specimen, accepted_checkpoint_proofs, captured_tools=(), projection_services,
            active_graph_bytes: bytes | None = None):
        from .canonical_materialization_v2 import MaterializationRequestV2, TerminalFieldProofV2
        if (not isinstance(prior, Specimen) or set(native_inputs) != INPUT_KEYS
                or native_inputs["contract_version"] != "research-native-materialization-inputs/v2"
                or preparation.prepared.basis.scope != intent.original_prepared.basis.scope
                or native_inputs["scoped_state"] != current_binding.registration.read_bundle
                or preparation not in tuple(type(preparation).model_validate(row)
                    for row in native_inputs["outer_intent"]["preparations"])):
            hold("canonical_native_input_bundle_unproved")
        reg = current_binding.registration
        snapshot_row = native_inputs["current_snapshot"]
        snapshot = snapshot_row.get("snapshot")
        if type(snapshot) is not dict:
            hold("canonical_native_packed_snapshot_unavailable")
        raw_graph = active_graph_bytes
        if snapshot.get("active_graph") is None and raw_graph is not None:
            hold("canonical_native_graph_bytes_unexpected")
        native_proof = NativePriorSnapshotProofV2(current_binding.canonical, copy.deepcopy(snapshot), raw_graph)
        prior_projection = canonical_prior_projection_v2(native_inputs["projection_rows"]["resolved_fields"],
            current_binding.canonical.record_version_id)
        checkpoints = native_inputs["checkpoint_inputs"]
        target_cp = FieldCheckpoint.model_validate(checkpoints["target"])
        all_cp = (target_cp, *(FieldCheckpoint.model_validate(row) for row in checkpoints["terminal_siblings"]))
        if len({cp.field_key for cp in all_cp}) != len(all_cp):
            hold("canonical_native_terminal_checkpoint_duplicate")
        requests = []
        for cp in all_cp:
            accepted = accepted_checkpoint_proofs.get(str(cp.field_key))
            if not isinstance(accepted, AcceptedCheckpointProofV1):
                hold("canonical_historical_accepted_output_proof_unavailable")
            requests.append(accepted.acceptance.original_request)
        transcription = _transcription_contexts(prior, native_inputs, preparation.prepared.basis.scope,
            projection_services, requests)
        contexts, originals = [], {}
        for cp in all_cp:
            key = str(cp.field_key)
            accepted = accepted_checkpoint_proofs.get(key)
            if accepted is None:
                hold("canonical_historical_accepted_output_proof_unavailable")
            request = accepted.acceptance.original_request
            tools = accepted.acceptance.source_results
            ids = {row.evidence.id:UUID(row.canonical_evidence.id) for row in captured_tools}
            # Sibling evidence must already have been published with native
            # lineage; never invent its research→canonical association.
            if cp is not target_cp:
                current_row = _one(native_inputs["projection_rows"]["resolved_fields"], lambda row:
                    row.get("recordVersionId") == str(current_binding.canonical.record_version_id)
                    and row.get("fieldKey") == reg.field_mapping[key],
                    "canonical_native_sibling_projection_unavailable")
                selected_lineages = [line for line in native_inputs["lineage_rows"]["value_lineages"]
                    if line.get("candidateId") == current_row.get("candidateId")
                    and line.get("researchFieldKey") == key]
                # Candidate-less exceptions/review outcomes still have an
                # atomic winning record receipt. Their genuine nullable value
                # must not require a fictional candidate or value lineage.
                candidate_less = current_row.get("candidateId") is None
                if not selected_lineages and not candidate_less:
                    # A newly accepted sibling is not yet a canonical settled
                    # field. Keep genuine whole20 work, but do not count it as
                    # scientifically qualified until its publication commits.
                    continue
                if not candidate_less and len(selected_lineages) != 1:
                    hold("canonical_native_sibling_lineage_ambiguous")
                ids = {} if candidate_less else {row["researchEvidenceId"]:UUID(row["evidenceId"])
                    for row in native_inputs["lineage_rows"]["value_evidence"]
                    if row.get("lineageId") == selected_lineages[0]["id"]}
            context = CanonicalLineageContextV2(scope=cp.scope, actor_uid=preparation.prepared.basis.actor_uid,
                prior_record_version_id=current_binding.canonical.record_version_id,
                prior_revision=prior.version, prior_snapshot_sha256=graph_digest(prior.model_dump(mode="json")),
                native_prior_snapshot=native_proof, job=reg.job, field_mapping=reg.field_mapping,
                evidence_id_mapping=ids, human_locks=reg.human_locks, prior_projection=prior_projection,
                original_request=request, tool_results=tools,
                transcription_ids={row.region_id:row.transcription_version_id for row in transcription},
                transcription_proofs=transcription, accepted_checkpoint_proof=accepted)
            _prior_snapshot(prior, context)
            proof = _accepted_original(context, cp, accepted)
            if cp is not target_cp and _sibling_winner(context, cp, intent, native_inputs) is None:
                continue
            consumed = _consumed_sources(context, cp, intent, native_inputs, prior,
                target=cp is target_cp)
            context = replace(context, consumed_sources=consumed)
            _source_lineage(context, prior, proof.original_checkpoint, consumed)
            originals[key] = proof
            contexts.append((cp, context))
        target_context = contexts[0][1]
        target = MaterializationRequestV2(digest(preparation.prepared), current_binding.canonical.snapshot_sha256,
            target_context.original_request, target_context.tool_results, target_context,
            tuple(TerminalFieldProofV2(cp, context) for cp, context in contexts[1:]))
        return cls(target, digest(native_inputs), NORMALIZATION_VERSION, originals)
