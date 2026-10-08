"""Whole-record progress uses a genuine carrier or a typed target-free native receipt.

Pure selection controls and the production composer use only synthetic labels,
FunctionModels, SQLite, and the existing fake native connector. No live model,
source, SQL, or production mutation is performed.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

import production_e2e_support as support
from test_production_bridge import RESEARCH_SCOPE, checkpoint, principal, thread, waiting
from test_native_canonical_contract import helper_resolutions
from test_unkeyed_label_reading_citation import build_rig, no_network, supervised  # noqa: F401
from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.application.production import actor_uid
from specimen_digitization.research_harness import committed_pins, native_worker
from specimen_digitization.research_harness.agents import SpecialistOutput
from specimen_digitization.research_harness.collection import COLLECTION_FIELDS, collection_resolution
from specimen_digitization.research_harness.committed_pins import committed_research_profile
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, ROLE_FIELDS, DependencyPin, FieldKey, FieldResolution, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.evidence import dts_policy_resolution, missing_irn_resolution
from specimen_digitization.research_harness.people import collector_resolution
from specimen_digitization.research_harness.persistence import DurabilityScope, StaleWork


def resolved(key, *, dependencies=()):
    return checkpoint(FieldResolution(field_key=key, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, literal="synthetic", evidence_ids=["label-evidence"],
            evidence_relations={"label-evidence": "supports"}), evidence_ids=("label-evidence",),
        dependencies=tuple(dependencies), reason="Explicitly synthetic selection checkpoint"))


def job_for(checkpoints, *, pending=(), locked=()):
    by_key = {cp.field_key: cp for cp in checkpoints}
    return {"record_revision": 4, "pins": {"profile": committed_research_profile(support.ORG, support.COLLECTION).model_dump(mode="json")}, "fields": {
        str(key): {"work_state": "pending" if key in pending else str(
            by_key[key].resolution.work_state if key in by_key else WorkState.WAITING_POLICY),
            "locked": key in locked,
            "checkpoint": {"id": "native-" + str(key), "scope": RESEARCH_SCOPE.model_dump(mode="json"),
                "payload": by_key[key].model_dump(mode="json")} if key in by_key else None}
        for key in ALL_FIELDS}}


def event_for(key, *, delivered=False):
    return {"kind": "canonical_publication_required", "delivered": delivered,
        "guard": {"checkpoint_id": "native-" + str(key), "idempotency_key": "a" * 64},
        **({"canonical_commit": {"id": "receipt-already-delivered"}} if delivered else {})}


def select(checkpoints, *, pending=(), locked=(), events=(), unpublishable=()):
    return native_worker._final_progress_carrier(checkpoints,
        job_for(checkpoints, pending=pending, locked=locked), events, frozenset(unpublishable))


def test_carrier_prefers_irn_then_real_date_then_collection_literal():
    irn = checkpoint(missing_irn_resolution())
    request, [resolution] = helper_resolutions(RESEARCH_SCOPE, "date")
    date = checkpoint(resolution)
    habitat = resolved(FieldKey.HABITAT)
    assert date.resolution.value.normalized == "1946-09-03"
    assert date.resolution.event_id and date.resolution.assembly_ids and date.resolution.evidence_ids
    assert select((habitat, date, irn)) == irn
    assert select((habitat, date, irn), locked={FieldKey.IDENTIFIED_BY_IRN}) == date
    assert select((habitat, date), locked={FieldKey.DATE_IDENTIFIED}) == habitat


@pytest.mark.parametrize("delivered", [False, True])
def test_established_operation_or_delivered_receipt_is_never_deferred(delivered):
    irn = checkpoint(missing_irn_resolution())
    habitat = resolved(FieldKey.HABITAT)
    assert select((irn, habitat), pending={FieldKey.TAXON},
        events=(event_for(FieldKey.IDENTIFIED_BY_IRN, delivered=delivered),)) == habitat
    assert select((irn,), pending={FieldKey.TAXON},
        events=(event_for(FieldKey.IDENTIFIED_BY_IRN, delivered=delivered),)) is None


def test_checkpoint_consumed_by_another_resolution_is_not_deferred():
    date = resolved(FieldKey.DATE_IDENTIFIED)
    pin = DependencyPin(field_key=date.field_key, revision=date.revision, digest=digest(date.resolution))
    dependent = resolved(FieldKey.HABITAT, dependencies=(pin,))
    assert select((date, dependent), pending={FieldKey.TAXON}) == dependent


@pytest.mark.parametrize(("source", "unfinished"), [
    (FieldKey.COLLECTORS, FieldKey.COUNTRY),
    (FieldKey.DATE_VISITED_FROM, FieldKey.COLLECTORS),
    (FieldKey.DATE_VISITED_TO, FieldKey.FMNH_INS_NUMBER),
    (FieldKey.ELEVATION_FROM_M, FieldKey.ELEVATION_TO_M),
])
def test_current_canonical_source_required_by_unfinished_role_is_not_deferred(source, unfinished):
    cp = resolved(source)
    assert select((cp,), pending={unfinished}) is None


@pytest.mark.parametrize("state", [WorkState.PENDING, WorkState.WAITING_POLICY, WorkState.WAITING_SOURCE,
    WorkState.OPERATIONAL_FAILED, WorkState.CANCELLED])
def test_nonpublishable_work_cannot_become_a_progress_carrier(state):
    assert select((waiting(FieldKey.DATE_IDENTIFIED, state),), pending={FieldKey.TAXON}) is None


def test_locked_or_relation_unproved_checkpoint_cannot_become_carrier():
    date = resolved(FieldKey.DATE_IDENTIFIED)
    assert select((date,), locked={date.field_key}) is None
    assert select((date,), unpublishable={date.field_key}) is None
    assert select((), pending={FieldKey.TAXON}) is None


def publish_pass(monkeypatch, checkpoints, *, pending=(), events=(), canonical_stage="research_in_progress", winner=False, progress_current=True):
    """Only the publication I/O seams are recording stand-ins; use the real worker loop."""
    job = job_for(checkpoints, pending=pending)
    prepared, proofs, reads = [], [], []

    async def load(_scope):
        return checkpoints

    async def prepare(_journal, _scope, key, **kwargs):
        prepared.append(key)
        return key

    async def winning_receipt(_principal, _specimen_id, **kwargs):
        return SimpleNamespace(causal=SimpleNamespace(receipt_id="receipt-retained-winner")) if winner else None

    async def publish(_principal, key, **kwargs):
        return SimpleNamespace(causal=SimpleNamespace(receipt_id="receipt-" + str(key)))

    durability = DurabilityScope(RESEARCH_SCOPE.organization_id, RESEARCH_SCOPE.collection_id,
        RESEARCH_SCOPE.specimen_id, RESEARCH_SCOPE.job_id, RESEARCH_SCOPE.generation, str(principal().user_id), False)

    async def read_current_binding(actor, specimen_id):
        reads.append((actor.scope, specimen_id))
        mapping = {str(key): str(key) for key in ALL_FIELDS}
        progress = SimpleNamespace(job_key=durability.key, generation=durability.generation,
            field_work_digest=digest(job["fields"]) if progress_current else "0" * 64,
            research_field_work={key: field["work_state"] for key, field in job["fields"].items()},
            canonical_field_work={key: field["work_state"] for key, field in job["fields"].items()},
            field_mapping_digest=digest(mapping), policy_digest="b" * 64, run_stage=canonical_stage,
            wire_status="completed" if canonical_stage == "finalized" else
                "processing_blocked" if canonical_stage == "processing_blocked" else "running")
        causal = SimpleNamespace(receipt_id="actual-native-head", resulting="current-canonical",
            scope_identity=durability.identity(), job_key=durability.key, progress_receipt=progress)
        return SimpleNamespace(causal_chain=(causal,), head_receipt_id=causal.receipt_id,
            canonical=causal.resulting, registration=SimpleNamespace(job=job, field_mapping=mapping, policy_digest="b" * 64))

    async def read_thread(_runtime):
        return thread(*checkpoints)

    async def unsupported_progress(_principal, _specimen_id, **kwargs):
        # These selection units have no actual all20 acceptance/native input
        # bundle. The composed tests below exercise successful real progress.
        raise StaleWork("native_progress_all_twenty_proof_unavailable")

    runtime = SimpleNamespace(binding=SimpleNamespace(research_scope=lambda: RESEARCH_SCOPE),
        scope=durability, blobs=None, journal=SimpleNamespace(load=load),
        store=SimpleNamespace(_read=lambda scope: SimpleNamespace(state={"outbox": {
            str(index): event for index, event in enumerate(events)}}), _job=lambda state, scope: job),
        canonical_service=SimpleNamespace(publish_checkpoint=publish, winning_receipt=winning_receipt,
            read_current_binding=read_current_binding, publish_progress=unsupported_progress))
    monkeypatch.setattr(native_worker, "read_accepted_checkpoint_proof",
        lambda store, scope, blobs, checkpoint_id: proofs.append(checkpoint_id))
    monkeypatch.setattr(native_worker, "prepare_native_publication", prepare)
    monkeypatch.setattr(native_worker.NativeResearchWorker, "_thread", staticmethod(read_thread))
    outcome = asyncio.run(native_worker.NativeResearchWorker(None)._publish_committed(
        runtime, principal(), RESEARCH_SCOPE.specimen_id))
    return outcome, prepared, proofs, reads


def test_pending_pass_defers_one_genuine_checkpoint_and_final_pass_publishes_it_last(monkeypatch):
    date, irn, habitat = resolved(FieldKey.DATE_IDENTIFIED), checkpoint(missing_irn_resolution()), resolved(FieldKey.HABITAT)
    outcome, prepared, proofs, reads = publish_pass(monkeypatch, (date, irn, habitat), pending={FieldKey.TAXON})
    assert prepared == [FieldKey.DATE_IDENTIFIED, FieldKey.HABITAT]
    assert "native-identified_by_irn" not in proofs and not reads
    assert outcome.publication_receipt_ids == ("receipt-date_identified", "receipt-habitat")
    outcome, prepared, proofs, reads = publish_pass(monkeypatch, (date, irn, habitat))
    assert prepared == [FieldKey.DATE_IDENTIFIED, FieldKey.HABITAT, FieldKey.IDENTIFIED_BY_IRN]
    assert proofs[-1] == "native-identified_by_irn" and not reads
    assert outcome.publication_receipt_ids[-1] == "receipt-identified_by_irn"


@pytest.mark.parametrize("delivered", [False, True])
def test_existing_irn_operation_is_offered_even_while_work_remains(monkeypatch, delivered):
    irn = checkpoint(missing_irn_resolution())
    outcome, prepared, proofs, reads = publish_pass(monkeypatch, (irn,), pending={FieldKey.TAXON},
        events=(event_for(irn.field_key, delivered=delivered),))
    if delivered:
        assert prepared == proofs == []
        assert outcome.publication_receipt_ids == ("receipt-already-delivered",)
    else:
        # An established operation without a winner still proceeds normally.
        assert prepared == [FieldKey.IDENTIFIED_BY_IRN]
        assert proofs == ["native-identified_by_irn"]
    assert not reads


def test_established_winning_receipt_is_reused_without_a_new_publication_or_fabricated_carrier(monkeypatch):
    irn = checkpoint(missing_irn_resolution())
    outcome, prepared, proofs, reads = publish_pass(monkeypatch, (irn,),
        events=(event_for(irn.field_key),), winner=True)
    assert prepared == [] and proofs == ["native-identified_by_irn"]
    assert outcome.publication_receipt_ids == ("receipt-retained-winner",)
    assert len(reads) == 1
    assert outcome.reason_code == "native_progress_publication_requires_reconciliation"


# A finalized receipt carrying a current waiting_source is rejected by the
# actual typed native read; the real composed source control below proves that.
@pytest.mark.parametrize("canonical_stage", ["research_in_progress", "running", "processing_blocked"])
def test_terminal_work_without_a_new_publication_reads_current_canonical_progress(monkeypatch, canonical_stage):
    cp = waiting(FieldKey.TAXON, WorkState.WAITING_SOURCE)
    outcome, prepared, proofs, reads = publish_pass(monkeypatch, (cp,), canonical_stage=canonical_stage)
    assert prepared == proofs == []
    assert reads == [(principal().scope, RESEARCH_SCOPE.specimen_id)]
    if canonical_stage in {"research_in_progress", "running"}:
        assert (outcome.status, outcome.reason_code) == ("blocked", "native_progress_publication_requires_reconciliation")
    else:
        assert outcome.reason_code is None
        assert outcome.status == "blocked"  # scientific source hold remains distinct


@pytest.mark.parametrize("canonical_stage", ["finalized", "processing_blocked"])
def test_old_terminal_stage_cannot_hide_changed_whole_twenty_progress(monkeypatch, canonical_stage):
    cp = waiting(FieldKey.TAXON, WorkState.WAITING_SOURCE)
    outcome, prepared, proofs, reads = publish_pass(monkeypatch, (cp,),
        canonical_stage=canonical_stage, progress_current=False)
    assert prepared == proofs == [] and len(reads) == 1
    assert (outcome.status, outcome.reason_code) == (
        "blocked", "native_progress_publication_requires_reconciliation")


def final_window_models(rig, *, final_state, without_carrier=False):
    """Real local helpers for early roles; no named taxon or lookup claims in the final window."""
    requests = []

    def factory(request, binding):
        requests.append(request)

        def respond(messages, info):
            rig.model_calls.append((str(request.role), 1))
            proposals = (support._dates(request) if request.role == SpecialistRole.TEMPORAL else
                support._elevations(request) if request.role == SpecialistRole.MEASUREMENT else {})
            rows = []
            for key in request.field_keys:
                if request.role in {SpecialistRole.TAXONOMY, SpecialistRole.GEOGRAPHY}:
                    row = FieldResolution(field_key=key, work_state=final_state, value=FieldValue(),
                        reason="No asserted named taxon or qualified place source in this synthetic label")
                elif key == FieldKey.IDENTIFIED_BY_IRN:
                    row = missing_irn_resolution()
                elif key == FieldKey.VERBATIM_DTS:
                    row = dts_policy_resolution(None)
                elif key in COLLECTION_FIELDS:
                    row = collection_resolution(request, key)
                elif key == FieldKey.COLLECTORS and (assemblies := [
                        item for item in request.assemblies if item.field_key == key]):
                    row = collector_resolution(request, assembly_id=assemblies[0].id)
                elif isinstance(proposals.get(key), FieldResolution):
                    row = proposals[key]
                else:
                    row = FieldResolution(field_key=key, work_state=WorkState.WAITING_POLICY,
                        value=FieldValue(), reason="missing_policy:unstructured_label_event_unqualified")
                rows.append(row)
            output = SpecialistOutput(role=request.role, resolutions=tuple(rows))
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                output.model_dump(mode="json"), tool_call_id="synthetic-final-carrier-" + str(request.role))],
                usage=support.USAGE)
        return FunctionModel(respond)
    return factory, requests



def scientific_state(rig, specimen):
    """Native facts which a target-free progress commit may never rewrite."""
    record_id = rig.fake.bindings[rig.specimen_id]["current_record_version_id"]
    projection = {row["fieldKey"]: (row["candidateId"], row["state"], row["fieldGroup"])
        for row in rig.fake.tables["resolved_field"].values() if row["recordVersionId"] == record_id}
    # A new immutable record and its 20 same-candidate projections are expected.
    # All scientific producer/evidence/lineage tables stay byte-for-byte equal.
    tables = {name: copy.deepcopy(rows) for name, rows in rig.fake.tables.items()
        if name not in {"record_version", "resolved_field", "validation_finding"}}
    run = specimen.run
    return {"projection": projection, "tables": tables,
        "fields": {key: value.model_dump(mode="json") for key, value in run.fields.items()},
        "observations": [row.model_dump(mode="json") for row in run.observations],
        "transcripts": [row.model_dump(mode="json") for row in run.transcripts],
        "evidence": [row.model_dump(mode="json") for row in run.evidence],
        "lookups": [row.model_dump(mode="json") for row in run.lookups],
        "tool_calls": [row.model_dump(mode="json") for row in run.tool_calls]}


def confirm_fixture_coverage(monkeypatch, *, large_graph=False):
    """The actual one-region synthetic geometry covers every image pixel."""
    import test_unkeyed_label_reading_citation as native_fixture
    original = native_fixture.specimen_before_adjudication
    def covered(blobs):
        specimen = original(blobs)
        [region] = specimen.run.regions
        assert (region.x, region.y, region.width, region.height) == (
            0, 0, specimen.asset.width, specimen.asset.height)
        specimen.run.coverage_confirmed = True
        if large_graph:
            padding = "synthetic packing context; " * 5000
            raw = json.dumps({"fixture_padding": padding}, sort_keys=True).encode()
            specimen.run.phase_results["synthetic_packing_fixture"] = {
                "purpose": "Exercise immutable active-run packing without a scientific assertion",
                "fixture_padding": padding, "blob_ref": blobs.put(raw),
                "sha256": hashlib.sha256(raw).hexdigest()}
        return specimen
    monkeypatch.setattr(native_fixture, "specimen_before_adjudication", covered)

def install_progress_sql_fixture(rig):
    """Faithful local connector I/O for disjoint progress operations, not SQL proof."""
    from specimen_digitization.research_harness.progress_publication_v2 import (
        ProgressIntentV2, ProgressPreparationV2,
    )
    fake = rig.fake
    native_inputs = fake.op_GetCanonicalResearchMaterializationInputsV2

    def retain_intent(variables):
        fake.require_member(variables)
        specimen_id, intent = variables["specimenId"], json.loads(variables["intentJson"])
        ProgressIntentV2.model_validate(intent)
        binding = fake.active_binding(specimen_id)
        loaded = None if binding is None else fake.state(specimen_id, binding["program_key"])
        basis, base = intent["original_prepared"]["basis"], intent["original_base"]
        if (binding is None or loaded is None or fake.specimens[specimen_id]["sensitive"]
                or intent["actor_uid"] != variables["actorUid"]
                or intent["binding_id"] != binding["binding_id"]
                or intent["job_key"] != binding["job_key"] or intent["program_key"] != binding["program_key"]
                or intent["authority_digest"] != binding["authority_digest"]
                or intent["import_proof_id"] != binding["import_proof_id"]
                or intent["import_proof_digest"] != binding["import_proof_digest"]
                or base != {"record_revision": binding["base_canonical_revision"],
                    "record_version_id": binding["base_record_version_id"],
                    "canonical_run_id": binding["canonical_run_id"],
                    "host_record_version_id": binding["base_host_record_version_id"],
                    "snapshot_sha256": binding["base_snapshot_sha256"]}
                or basis["scope"]["organization_id"] != support.ORG
                or basis["scope"]["collection_id"] != support.COLLECTION
                or basis["scope"]["specimen_id"] != specimen_id
                or basis["scope"]["job_id"] != binding["job_id"]
                or basis["scope"]["generation"] != binding["generation"]
                or basis["binding_digest"] != binding["runtime_binding_digest"]
                or loaded[0] != basis["state_revision"]
                or intent["id"] in fake.intents
                or fake._intent_for(variables, specimen_id, intent["idempotency_key"])):
            raise support.ConnectorRefusal("native progress intent unavailable")
        fake.intents[intent["id"]] = {"id": intent["id"], "specimen_id": specimen_id,
            "actor_uid": variables["actorUid"], "idempotency_key": intent["idempotency_key"],
            "operation_digest": intent["operation_digest"], "progress_basis_digest": intent["progress_basis_digest"],
            "request_identity_digest": intent["server_request_identity_digest"], "payload": intent}
        return {"retainedIntent": 1}

    def retain_preparation(variables):
        fake.require_member(variables)
        specimen_id, request = variables["specimenId"], json.loads(variables["preparationJson"])
        prepared = {key: value for key, value in request.items() if key != "preparation_digest"}
        ProgressPreparationV2.model_validate(prepared)
        assert request["preparation_digest"] == digest(prepared)
        intent = fake.intents.get(prepared["intent_id"])
        binding = fake.active_binding(specimen_id)
        loaded = None if binding is None else fake.state(specimen_id, binding["program_key"])
        prior = [] if intent is None else fake._preparations(intent["id"])
        anchor = prepared["anchor"]
        lease = None if loaded is None else loaded[1]["jobs"][binding["job_key"]].get("lease")
        if (intent is None or intent["actor_uid"] != variables["actorUid"]
                or intent["specimen_id"] != specimen_id or binding is None or loaded is None
                or intent["payload"]["binding_id"] != binding["binding_id"]
                or prepared["progress_basis_digest"] != intent["progress_basis_digest"]
                or prepared["authority_digest"] != binding["authority_digest"]
                or loaded[0] != prepared["state_revision"] or loaded[1] != prepared["expected_state"]
                or binding["current_record_version_id"] != anchor["record_version_id"]
                or binding["current_canonical_revision"] != anchor["record_revision"]
                or binding["current_snapshot_sha256"] != anchor["snapshot_sha256"]
                or binding["current_host_record_version_id"] != anchor["host_record_version_id"]
                or binding["current_chain_digest"] != prepared["anchor_chain_digest"]
                or binding["current_receipt_id"] != prepared["anchor_receipt_id"]
                or binding["registration_revision"] != prepared["anchor_registration_revision"]
                or lease != prepared["prepared"]["basis"]["lease"] or lease is None
                or lease["expires_at"] <= datetime.now(timezone.utc).timestamp()
                or intent["id"] in fake.attempts or prepared["ordinal"] != len(prior) + 1
                or prepared["ordinal"] > 1 and (prior[-1]["id"] != prepared["prior_preparation_id"]
                    or prior[-1]["preparation_digest"] != prepared["prior_preparation_digest"])):
            raise support.ConnectorRefusal("native progress preparation unavailable")
        fake.preparations[prepared["id"]] = {"id": prepared["id"], "intent_id": prepared["intent_id"],
            "ordinal": prepared["ordinal"], "preparation_digest": digest(prepared),
            "admission_digest": prepared["admission_digest"], "payload": prepared}
        return {"retainedPreparation": 1}

    def materialization_inputs(variables):
        specimen_id = variables["specimenId"]
        prep = fake.preparations.get(variables["preparationId"])
        intent = None if prep is None else fake.intents.get(prep["intent_id"])
        if intent is None or intent["payload"].get("contract_version") != "research-progress-intent/v2":
            return native_inputs(variables)
        envelope, base = fake.envelope(variables, specimen_id), fake.binding_row(variables, specimen_id)
        binding = fake.active_binding(specimen_id)
        if (base is None or binding is None or intent["specimen_id"] != specimen_id
                or intent["actor_uid"] != variables["actorUid"]
                or intent["idempotency_key"] != variables["idempotencyKey"]
                or intent["request_identity_digest"] != variables["requestIdentityDigest"]):
            return {**envelope, "binding": None}
        revision, state = fake.state(specimen_id, binding["program_key"])
        job_key, run_id = binding["job_key"], binding["canonical_run_id"]
        preparations, anchor = fake._preparations(intent["id"]), prep["payload"]["anchor"]
        anchor_record = fake.tables["record_version"].get(anchor["record_version_id"])
        receipt = fake.receipts.get(binding["current_receipt_id"])
        scoped = lambda value: (value.get("organization_id") == support.ORG
            and value.get("collection_id") == support.COLLECTION and value.get("specimen_id") == specimen_id
            and value.get("job_id") == binding["job_id"])
        inputs = {"contract_version": "research-native-progress-inputs/v2",
            "observed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "registration": base["registrations"][0],
            "outer_intent": {"original": intent["payload"], "preparation_count": len(preparations),
                "preparations": [item["payload"] for item in preparations], "attempt": fake._attempt(intent["id"])},
            "scoped_state": base["registrations"][0]["read_bundle"],
            "private_state_integrity": {"revision": revision, "contract_version": state["contract_version"],
                "state_json": support.canonical(state).decode(), "state": state},
            "current_snapshot": base["snapshot"],
            "preparation_snapshot": {"identity": anchor,
                "snapshot": fake.snapshots.get((specimen_id, anchor["record_revision"])),
                "record": None if anchor_record is None else {"id": anchor_record["id"],
                    "runId": anchor_record["runId"], "predecessorId": anchor_record["predecessorId"]}},
            "retained_history": base["causal"]["causal_chain"], "projection_rows": fake.projection_rows(run_id),
            "checkpoint_inputs": {"terminal_fields": [row["checkpoint"]["payload"]
                for _, row in sorted(state["jobs"][job_key]["fields"].items())
                if row["work_state"] in support.TERMINAL_WORK and row.get("checkpoint") is not None]},
            "original_request_sources": [{"run_id": key, "entry": entry}
                for key, entry in sorted(state["journal"].items()) if scoped(entry.get("scope", {}))],
            "captured_executions": [{"effect_id": key, "effect": effect}
                for key, effect in sorted(state["effects"].items())
                if effect.get("job_key") == job_key and scoped(effect.get("scope", {}))],
            "native_input_rows": fake.native_input_rows(specimen_id),
            "lineage_rows": fake.lineage_rows(specimen_id, run_id),
            "prepack_proof": None if receipt is None else receipt["prepack_proof"]}
        return {**envelope, "binding": {**base, "materialization_inputs": inputs}}

    original_receipt = fake.op_GetResearchPublicationReceiptV2

    def progress_receipt(variables):
        response = original_receipt(variables)
        row = next((value for value in fake.receipts.values()
            if value["actor_uid"] == variables["actorUid"]
            and value["idempotency_key"] == variables["idempotencyKey"]), None)
        if row is not None and row["causal_proof"]["contract_version"] == "native-canonical-progress/v2":
            request = fake.request_receipts.get((variables["actorUid"], "research-progress-publication/v2",
                variables["idempotencyKey"]))
            response["retained"]["request"] = None if request is None else {
                "operation": "research-progress-publication/v2", "actorUid": variables["actorUid"],
                "idempotencyKey": variables["idempotencyKey"], "requestSha256": request["request_sha256"],
                "specimenId": request["specimen_id"], "revision": request["revision"]}
        return response

    def mark_attempt(variables):
        fake.require_member(variables)
        specimen_id, admission = variables["specimenId"], json.loads(variables["admissionJson"])
        intent, prep = fake.intents.get(admission["intent_id"]), fake.preparations.get(admission["preparation_id"])
        binding = fake.active_binding(specimen_id)
        loaded = None if binding is None else fake.state(specimen_id, binding["program_key"])
        if (intent is None or intent["payload"]["contract_version"] != "research-progress-intent/v2"
                or intent["operation_digest"] != admission["operation_digest"]
                or intent["actor_uid"] != variables["actorUid"] or prep is None
                or prep["intent_id"] != intent["id"] or prep["preparation_digest"] != admission["preparation_digest"]
                or prep["admission_digest"] != admission["admission_digest"] or binding is None or loaded is None
                or binding["binding_id"] != intent["payload"]["binding_id"]
                or loaded[0] != admission["state_revision"] or loaded[1] != admission["expected_state"]
                or binding["current_record_version_id"] != admission["used_record_version_id"]
                or binding["registration_revision"] != admission["registration_revision"] or intent["id"] in fake.attempts):
            raise support.ConnectorRefusal("native progress attempt unavailable")
        fake.attempts[intent["id"]] = {"id": admission["id"], "intent_id": intent["id"],
            "preparation_id": prep["id"], "operation_digest": admission["operation_digest"],
            "preparation_digest": admission["preparation_digest"], "admission_digest": admission["admission_digest"]}
        return {"markedAttempt": 1}

    def publish(variables):
        fake.require_member(variables)
        specimen_id, commit = variables["specimenId"], json.loads(variables["commitJson"])
        specimen, binding = fake.specimens[specimen_id], fake.active_binding(specimen_id)
        receipt, causal = commit["receipt"], commit["causal"]
        intent, prep = fake.intents.get(commit["intent_id"]), fake.preparations.get(causal["winning_preparation_id"])
        attempt = None if intent is None else fake.attempts.get(intent["id"])
        loaded = None if binding is None else fake.state(specimen_id, binding["program_key"])
        run_id = None if binding is None else binding["canonical_run_id"]
        fields = [] if binding is None else sorted((fake._field_row(row)
            for row in fake.tables["resolved_field"].values()
            if row["recordVersionId"] == binding["current_record_version_id"]), key=lambda row: row["fieldKey"])
        guard = commit["materialization_input_guard"]
        lease = None if loaded is None else loaded[1]["jobs"][binding["job_key"]].get("lease")
        event = None if loaded is None else loaded[1]["outbox"].get(causal["publication_outbox_key"])
        current_locks = None if loaded is None else fake._human_locks(binding,
            loaded[1]["jobs"][binding["job_key"]], fake.snapshots[(specimen_id, specimen["revision"])]["snapshot"])
        preserved = lambda rows: [{key: row[key] for key in ("fieldKey", "candidateId", "state", "fieldGroup")}
            for row in sorted(rows, key=lambda row: row["fieldKey"])]
        admissible = (binding is not None and loaded is not None and not specimen["sensitive"]
            and binding["registration_revision"] == commit["registration_revision"]
            and binding["binding_id"] == receipt["bindingId"]
            and binding["current_canonical_revision"] == specimen["revision"] == receipt["usedCanonicalRevision"]
            and binding["current_record_version_id"] == receipt["usedRecordVersionId"]
            and binding["current_snapshot_sha256"] == receipt["usedSnapshotSha256"]
            and binding["current_receipt_id"] == causal["parent_receipt_id"]
            and binding["current_chain_digest"] == causal["parent_chain_digest"]
            and intent is not None and intent["actor_uid"] == variables["actorUid"]
            and intent["payload"]["contract_version"] == "research-progress-intent/v2"
            and intent["idempotency_key"] == receipt["idempotencyKey"]
            and intent["operation_digest"] == receipt["operationDigest"]
            and intent["progress_basis_digest"] == causal["progress_basis_digest"]
            and intent["payload"]["authority_digest"] == binding["authority_digest"]
            and prep is not None and prep["intent_id"] == intent["id"]
            and prep["preparation_digest"] == receipt["preparedDigest"]
            and prep["payload"] == commit["preparation"] and prep["payload"]["prepared"] == commit["prepared"]
            and prep["admission_digest"] == causal["admission_digest"]
            and attempt is not None and attempt["preparation_id"] == prep["id"]
            and loaded[0] == commit["state_revision"] and loaded[1] == commit["expected_state"]
            and not fake._hold_reasons(binding, loaded[1])
            and lease == commit["prepared"]["basis"]["lease"] and lease is not None
            and lease["expires_at"] > datetime.now(timezone.utc).timestamp()
            and current_locks == causal["human_locks"]
            and event == {"kind": "canonical_publication_required", "guard": commit["native_guard"], "delivered": False}
            and commit["native_guard"]["operation_kind"] == "progress_only"
            and digest(loaded[1]["jobs"][binding["job_key"]]["fields"]) == causal["progress_receipt"]["field_work_digest"]
            and guard["binding_id"] == binding["binding_id"] and guard["registration_revision"] == binding["registration_revision"]
            and guard["state_revision"] == loaded[0]
            and guard["projection_rows"] == fake.projection_rows(run_id)
            and guard["native_input_rows"] == fake.native_input_rows(specimen_id)
            and guard["lineage_rows"] == fake.lineage_rows(specimen_id, run_id)
            and "changed_field" not in commit and "delta" not in commit
            and len(fields) == len(commit["fields"]) == 20 and fields == commit["prior_fields"]
            and preserved(fields) == preserved(commit["fields"])
            and commit["record"]["runId"] == run_id
            and commit["record"]["predecessorId"] == binding["current_record_version_id"]
            and commit["record"]["id"] == receipt["nativeRecordVersionId"]
            and commit["snapshot"]["id"] == specimen_id and commit["snapshot"]["version"] == specimen["revision"] + 1
            and commit["snapshot"]["asset"]["sha256"] == binding["source_sha256"]
            and commit["snapshot"]["run"]["id"] == run_id
            and receipt["snapshotSha256"] == support.canonical_digest(commit["snapshot"]))
        if not admissible:
            raise support.ConnectorRefusal("native progress publication unavailable")
        revision, now = specimen["revision"] + 1, support.iso_now()
        rows = [("record_version", {**commit["record"], "id": receipt["nativeRecordVersionId"]})]
        rows += [("resolved_field", row) for row in commit["fields"]]
        rows += [("validation_finding", row) for row in commit["findings"]]
        if any(row["id"] in fake.tables[table] for table, row in rows):
            raise support.ConnectorRefusal("native progress publication unavailable")
        rig.progress_before = {"science": scientific_state(rig, rig.repository.get(rig.principal.scope, specimen_id)),
            "tables": copy.deepcopy(fake.tables), "snapshots": copy.deepcopy(fake.snapshots),
            "state": copy.deepcopy(loaded[1]), "binding": copy.deepcopy(binding),
            "specimen": copy.deepcopy(specimen), "receipts": copy.deepcopy(fake.receipts),
            "intents": copy.deepcopy(fake.intents), "preparations": copy.deepcopy(fake.preparations),
            "attempts": copy.deepcopy(fake.attempts), "request_receipts": copy.deepcopy(fake.request_receipts),
            "audit_events": copy.deepcopy(fake.audit_events), "outbox_events": copy.deepcopy(fake.outbox_events),
            "model_calls": copy.deepcopy(rig.model_calls), "source_urls": copy.deepcopy(rig.source_urls)}
        rig.progress_commit = copy.deepcopy(commit)
        fake.backend.cas(fake._state_scope(specimen_id), binding["program_key"], loaded[0], commit["next_state"])
        for table, row in rows:
            fake.insert(table, {"organizationId": support.ORG, "collectionId": support.COLLECTION, **row, "createdAt": now})
        specimen.update(revision=revision, state=commit["state"], disposition=commit["record"]["disposition"],
            active_run_id=run_id, work_available_at=None)
        fake._snapshot_row(specimen_id, revision, commit["snapshot"], receipt["snapshotSha256"], commit["snapshot_contract"])
        fake.request_receipts[(variables["actorUid"], "research-progress-publication/v2", receipt["idempotencyKey"])] = {
            "specimen_id": specimen_id, "revision": revision, "request_sha256": receipt["operationDigest"]}
        fake.audit_events[commit["audit_id"]] = {"specimen_id": specimen_id, "actor_uid": variables["actorUid"],
            "action": "research_publication", "revision": revision, "request_sha256": receipt["operationDigest"]}
        fake.outbox_events[commit["outbox_id"]] = {"specimen_id": specimen_id, "aggregate_revision": revision,
            "event_type": "research_publication_committed", "deduplication_key": receipt["operationDigest"]}
        prior = copy.deepcopy(binding)
        binding.update(registration_revision=binding["registration_revision"] + 1,
            current_canonical_revision=revision, current_record_version_id=receipt["nativeRecordVersionId"],
            current_snapshot_sha256=receipt["snapshotSha256"], current_host_record_version_id=receipt["hostRecordVersionId"],
            current_receipt_id=receipt["id"], current_chain_digest=causal["chain_digest"])
        fake.receipts[receipt["id"]] = {"id": receipt["id"], "actor_uid": variables["actorUid"],
            "idempotency_key": receipt["idempotencyKey"], "specimen_id": specimen_id,
            "operation_digest": receipt["operationDigest"], "publication_digest": receipt["publicationDigest"],
            "prepared_digest": receipt["preparedDigest"], "intent_id": commit["intent_id"],
            "binding_id": binding["binding_id"], "job_id": binding["job_id"], "job_key": binding["job_key"],
            "generation": binding["generation"], "input_digest": binding["input_digest"],
            "profile_digest": binding["profile_digest"], "runtime_binding_digest": binding["runtime_binding_digest"],
            "used_canonical_revision": revision - 1, "used_record_version_id": prior["current_record_version_id"],
            "used_host_record_version_id": prior["current_host_record_version_id"], "used_snapshot_sha256": prior["current_snapshot_sha256"],
            "resulting_canonical_revision": revision, "native_record_version_id": receipt["nativeRecordVersionId"],
            "canonical_run_id": run_id, "host_record_version_id": receipt["hostRecordVersionId"],
            "snapshot_sha256": receipt["snapshotSha256"], "projection_digest": receipt["projectionDigest"],
            "projection_count": 20, "audit_id": commit["audit_id"], "outbox_id": commit["outbox_id"],
            "policy_receipt_digest": receipt["policyReceiptDigest"], "lineage_digest": receipt["lineageDigest"],
            "sensitive": False, "winning_preparation_id": causal["winning_preparation_id"],
            "causal_proof": causal, "chain_digest": causal["chain_digest"],
            "prepack_proof": commit["prepack_proof"], "prepack_proof_digest": receipt["prepackProofDigest"]}
        return {"committed": 1}

    fake.op_RetainResearchProgressIntentV2 = retain_intent
    fake.op_RetainResearchProgressPreparationV2 = retain_preparation
    fake.op_GetCanonicalResearchMaterializationInputsV2 = materialization_inputs
    fake.op_GetResearchPublicationReceiptV2 = progress_receipt
    fake.op_MarkResearchProgressAttemptV2 = mark_attempt
    fake.op_PublishCanonicalResearchProgressV2 = publish


def run_composed_research(rig, models):
    """Drive the real composer and report field publications separately from progress."""
    from specimen_digitization.application.workflow import OperationalBlock
    from specimen_digitization.research_harness.workflow_bridge import compose_production_research_workflow
    workflow = compose_production_research_workflow(rig.ordinary, repository=rig.repository,
        environ={"SPECIMEN_RESEARCH_HARNESS": "on"}, actor_uid=support.WORKER, state_backend=rig.backend,
        model_factory=models, source_transport=support.fixture_source_transport(rig.source_urls),
        blobs=rig.research_blobs)
    rig.workflow = workflow
    with supervised():
        workflow.step(rig.principal, rig.specimen_id)
        parsed = workflow.step(rig.principal, rig.specimen_id)
    assert rig.ordinary.next_step(parsed.run) == "plan" and len(parsed.run.fields) == 20
    hold = None
    try:
        with supervised():
            specimen = workflow.step(rig.principal, rig.specimen_id)
    except OperationalBlock as block:
        hold = block
        # An independent read-only observer can inspect a refused worker even
        # when that worker's membership was revoked at the transaction boundary.
        token = actor_uid.set(getattr(rig, "inspection_actor_uid", support.WORKER))
        try:
            specimen = rig.repository.get(rig.principal.scope, rig.specimen_id)
        finally:
            actor_uid.reset(token)
    receipts = sorted(rig.fake.receipts.values(), key=lambda row: row["used_canonical_revision"])
    fields = [row["causal_proof"]["changed_field"] for row in receipts
        if "changed_field" in row["causal_proof"]]
    return parsed, specimen, hold, fields


def composed_case(tmp_path, monkeypatch, *, final_state, without_carrier=False, declared_geo_policy=False,
        verified_coverage=False, fixture_install=None, large_graph=False):
    if verified_coverage:
        confirm_fixture_coverage(monkeypatch, large_graph=large_graph)
    if declared_geo_policy:
        # Explicit synthetic family policy, frozen before admission. This does
        # not claim the shipped profile treats these three source holds as human
        # questions; the current-profile control below requires them to block.
        monkeypatch.setattr(committed_pins, "UNQUALIFIED_LABEL_FIELDS",
            committed_pins.UNQUALIFIED_LABEL_FIELDS | {
                FieldKey.COUNTRY, FieldKey.PROVINCE_STATE, FieldKey.PRECISE_LOCATION})
    # Keyed early assertions permit the exact helpers' genuine accepted outputs;
    # the real-shaped unkeyed fixture construction supplies immutable readings.
    # Omit taxon entirely: policy is not allowed to erase an asserted taxon.
    text = "unqualified synthetic label" if without_carrier else "\n".join(
        f"{key}: {value}" for key, value in support.LABEL_VALUES.items() if key != "taxon")
    rig, token = build_rig(tmp_path, monkeypatch, (text,))
    if fixture_install is not None:
        fixture_install(rig)
    if without_carrier:
        original_pass = native_worker.NativeResearchWorker._publish_committed
        established = []

        async def established_irn(self, runtime, principal, specimen_id, **kwargs):
            job = runtime.store.job(runtime.scope)
            native = job["fields"]["identified_by_irn"]["checkpoint"]
            if native is not None and not established:
                assert any(row["work_state"] == "pending" for row in job["fields"].values())
                # A real pre-existing durable publication guard is never deferred.
                await native_worker.prepare_native_publication(runtime.journal,
                    runtime.binding.research_scope(), FieldKey.IDENTIFIED_BY_IRN,
                    principal=principal, expected_record_revision=job["record_revision"], blobs=runtime.blobs)
                established.append(native["id"])
            return await original_pass(self, runtime, principal, specimen_id, **kwargs)
        monkeypatch.setattr(native_worker.NativeResearchWorker, "_publish_committed", established_irn)
    try:
        models, requests = final_window_models(rig, final_state=final_state, without_carrier=without_carrier)
        parsed, specimen, hold, published = run_composed_research(rig, models)
        _, state = support.research_state(rig.fake, rig.specimen_id)
        [job] = state["jobs"].values()
        receipts = sorted(rig.fake.receipts.values(), key=lambda row: row["used_canonical_revision"])
        return rig, requests, job, receipts, parsed, specimen, hold, published
    finally:
        actor_uid.reset(token)


@pytest.mark.parametrize(("final_state", "declared_geo_policy"), [
    (WorkState.WAITING_POLICY, False),
    (WorkState.WAITING_POLICY, True),
    (WorkState.WAITING_SOURCE, False),
], ids=["undeclared_policy_remains_blocked", "declared_policy_reaches_human_review", "source_remains_blocked"])
def test_final_taxonomy_and_geography_without_publishable_values_update_whole_twenty(
        tmp_path, monkeypatch, final_state, declared_geo_policy):
    rig, requests, job, receipts, parsed, specimen, hold, published = composed_case(
        tmp_path, monkeypatch, final_state=final_state, declared_geo_policy=declared_geo_policy)
    assert {request.role for request in requests} == set(SpecialistRole)
    assert len(job["fields"]) == 20 and not any(row["work_state"] == "pending" for row in job["fields"].values())
    final_keys = {*ROLE_FIELDS[SpecialistRole.TAXONOMY], *ROLE_FIELDS[SpecialistRole.GEOGRAPHY]}
    assert all(job["fields"][str(key)]["work_state"] == str(final_state) for key in final_keys)
    assert not final_keys.intersection(map(FieldKey, published))
    assert published[-1] == "identified_by_irn" and published.count("identified_by_irn") == 1
    assert all(job["fields"][str(key)]["checkpoint"] is not None for key in final_keys)
    assert all(row["causal_proof"]["changed_field"] not in set(map(str, final_keys)) for row in receipts)
    final = receipts[-1]["causal_proof"]["progress_receipt"]
    assert set(final["research_field_work"]) == set(job["fields"]) and len(final["canonical_field_work"]) == 20
    assert final["research_field_work"] == {key: row["work_state"] for key, row in job["fields"].items()}
    assert specimen.version == parsed.version + len(receipts)
    assert not rig.fake.duplicates
    if final_state == WorkState.WAITING_POLICY and declared_geo_policy:
        assert hold is None
        assert (specimen.run.stage, specimen.run.disposition) == ("finalized", "needs_human_review")
        assert not final["operational_reason_codes"] and final["human_reason_codes"]
        assert (final["wire_status"], final["run_stage"], final["disposition"], final["exportable"]) == (
            "completed", "finalized", "needs_human_review", False)
    else:
        assert (specimen.run.stage, specimen.run.disposition) == ("processing_blocked", None)
        assert final["operational_reason_codes"] and not final["exportable"]
        assert (final["wire_status"], final["run_stage"], final["disposition"]) == (
            "processing_blocked", "processing_blocked", None)


@pytest.mark.parametrize(("final_state", "declared_geo_policy", "expected_stage", "large_graph"), [
    (WorkState.WAITING_POLICY, False, "processing_blocked", False),
    (WorkState.WAITING_POLICY, True, "finalized", False),
    (WorkState.WAITING_SOURCE, False, "processing_blocked", False),
    (WorkState.WAITING_POLICY, True, "finalized", True),
], ids=["undeclared_policy_blocked", "declared_policy_needs_human", "source_blocked", "large_graph_needs_human"])
def test_no_genuine_carrier_publishes_honest_fresh_native_progress_without_science_changes(
        tmp_path, monkeypatch, final_state, declared_geo_policy, expected_stage, large_graph):
    rig, requests, job, receipts, parsed, specimen, hold, published = composed_case(
        tmp_path, monkeypatch, final_state=final_state, without_carrier=True,
        declared_geo_policy=declared_geo_policy, verified_coverage=True,
        fixture_install=install_progress_sql_fixture, large_graph=large_graph)
    assert {request.role for request in requests} == set(SpecialistRole)
    assert len(job["fields"]) == 20 and all(row["checkpoint"] is not None for row in job["fields"].values())
    assert not any(row["work_state"] == "pending" for row in job["fields"].values())
    assert len(receipts) == 2 and published == ["identified_by_irn"] and not rig.fake.duplicates
    early, final = (row["causal_proof"] for row in receipts)
    assert early["progress_receipt"]["run_stage"] == "research_in_progress"
    assert any(value == "pending" for value in early["progress_receipt"]["research_field_work"].values())
    assert final["contract_version"] == "native-canonical-progress/v2"
    assert "changed_field" not in final and "typed_checkpoint_digest" not in final
    assert final["parent_receipt_id"] == early["receipt_id"]
    assert final["resulting"]["record_revision"] == final["used"]["record_revision"] + 1
    assert specimen.version == parsed.version + 2
    progress = final["progress_receipt"]
    assert progress["field_work_digest"] == digest(job["fields"])
    assert progress["research_field_work"] == {key: row["work_state"] for key, row in job["fields"].items()}
    assert len(progress["canonical_field_work"]) == 20
    assert progress["run_stage"] == specimen.run.stage == expected_stage
    assert progress["exportable"] is False
    if expected_stage == "finalized":
        assert hold is None and specimen.run.disposition == "needs_human_review"
        assert progress["wire_status"] == "completed" and progress["human_reason_codes"]
        assert not progress["operational_reason_codes"]
    else:
        assert specimen.run.disposition is None
        assert progress["wire_status"] == "processing_blocked" and progress["operational_reason_codes"]
    before, commit = rig.progress_before, rig.progress_commit
    if large_graph:
        graph = commit["snapshot"]["active_graph"]
        assert graph is not None and graph["size_bytes"] > 96 * 1024
        assert specimen.active_graph == graph
        assert specimen.run.phase_results["synthetic_packing_fixture"]["fixture_padding"].startswith("synthetic packing context")
    assert scientific_state(rig, specimen) == before["science"]
    assert rig.model_calls == before["model_calls"] and rig.source_urls == before["source_urls"] == []
    assert "delta" not in commit and "changed_field" not in commit
    assert commit["native_guard"]["operation_kind"] == "progress_only"
    assert "checkpoint_id" not in commit["native_guard"] and "field_key" not in commit["native_guard"]
    assert all(rig.fake.tables[name][key] == row for name, rows in before["tables"].items()
        for key, row in rows.items())
    assert all(rig.fake.snapshots[key] == row for key, row in before["snapshots"].items())
    assert len(rig.fake.tables["record_version"]) == len(before["tables"]["record_version"]) + 1
    assert len(rig.fake.tables["resolved_field"]) == len(before["tables"]["resolved_field"]) + 20
    for name in ("fields", "history", "dependencies", "pins"):
        assert final["after_state"]["jobs"][final["job_key"]][name] == final["before_state"]["jobs"][final["job_key"]][name]
    for name in ("effects", "journal", "budget_policy", "budget_totals"):
        assert final["after_state"][name] == final["before_state"][name]
    other_events = {key: event for key, event in final["before_state"]["outbox"].items()
        if key != final["publication_outbox_key"]}
    assert all(final["after_state"]["outbox"][key] == event for key, event in other_events.items())
    assert final["after_state"]["outbox"][final["publication_outbox_key"]]["delivered"] is True
    if expected_stage == "finalized" and not large_graph:
        evidence = {"fixture_scope": "offline synthetic unqualified label; not live or paid SQL evidence",
            "commit": commit, "state": before["state"], "binding": before["binding"],
            "native_tables": before["tables"], "receipts": before["receipts"], "intents": before["intents"],
            "preparations": before["preparations"], "attempts": before["attempts"],
            "request_receipts": [{"actor_uid": key[0], "operation": key[1], "idempotency_key": key[2], **row}
                for key, row in before["request_receipts"].items()],
            "audit_events": before["audit_events"], "outbox_events": before["outbox_events"],
            "snapshots": [{"specimen_id": key[0], **row} for key, row in before["snapshots"].items()],
            "specimen": before["specimen"]}
        encoded = json.dumps(evidence, sort_keys=True).encode()
        evidence_sha = hashlib.sha256(encoded).hexdigest()
        Path(f"/private/tmp/harness-progress-only-native-synthetic-{evidence_sha}.json").write_bytes(encoded)
        rig.progress_evidence_path = f"/private/tmp/harness-progress-only-native-synthetic-{evidence_sha}.json"
    # Fresh lease/canonical binding service replay and full registered worker
    # replay both read the winning operation; neither resends a specialist.
    baseline = (len(rig.fake.receipts), copy.deepcopy(rig.fake.tables), copy.deepcopy(rig.model_calls),
        copy.deepcopy(rig.source_urls), specimen.version)
    token = actor_uid.set(support.WORKER)
    try:
        async def service_replay():
            runtime = await rig.workflow.native_worker.runtime_factory.open(rig.principal, rig.specimen_id,
                owner="offline-progress-service-replay")
            result = await runtime.canonical_service.publish_progress(rig.principal, rig.specimen_id,
                scope=runtime.binding.research_scope())
            assert result.replayed and str(result.causal.receipt_id) == final["receipt_id"]
            runtime.store.release(runtime.scope, runtime.lease)
        with supervised():
            asyncio.run(service_replay())
            replay = asyncio.run(rig.workflow.native_worker.run_registered(rig.principal, rig.specimen_id,
                owner="offline-progress-worker-replay"))
        assert replay.reason_code is None and final["receipt_id"] in replay.publication_receipt_ids
    finally:
        actor_uid.reset(token)
    assert (len(rig.fake.receipts), rig.fake.tables, rig.model_calls, rig.source_urls,
        rig.fake.specimens[rig.specimen_id]["revision"]) == baseline


def refused_progress_fixture(kind):
    """A concurrent refusal at the real native commit boundary, after known prep."""
    def install(rig):
        install_progress_sql_fixture(rig)
        rig.inspection_actor_uid = "offline-progress-read-only-observer"
        rig.fake.members[rig.inspection_actor_uid] = [{"organization_id": support.ORG,
            "collection_id": support.COLLECTION, "role": "viewer", "can_view_sensitive": False}]

        def refuse(variables):
            fake, specimen_id = rig.fake, rig.specimen_id
            commit = json.loads(variables["commitJson"])
            binding = fake.bindings[specimen_id]
            revision, state = fake.state(specimen_id, binding["program_key"])
            before = rig.repository.get(rig.principal.scope, specimen_id)
            rig.refused_commit = commit
            rig.refused_lease = copy.deepcopy(state["jobs"][binding["job_key"]]["lease"])
            rig.refused_receipts = copy.deepcopy(fake.receipts)
            rig.refused_model_calls, rig.refused_source_urls = copy.deepcopy(rig.model_calls), copy.deepcopy(rig.source_urls)
            if kind == "stale_q":
                current = fake.specimens[specimen_id]
                snapshot = copy.deepcopy(fake.snapshots[(specimen_id, current["revision"])]["snapshot"])
                current["revision"] += 1
                snapshot["version"] = current["revision"]
                fake._snapshot_row(specimen_id, current["revision"], snapshot,
                    support.canonical_digest(snapshot), "0.1")
            elif kind == "field_bytes":
                next(row for row in fake.tables["resolved_field"].values()
                    if row["recordVersionId"] == binding["current_record_version_id"]
                    and row["fieldKey"] == "identified_by_irn")["state"] = "unresolved"
            elif kind == "reading_bytes":
                next(iter(fake.tables["model_observation"].values()))["literalText"] += "\nconcurrent synthetic change"
            elif kind == "membership":
                fake.members[support.WORKER] = []
            elif kind in {"locked", "unknown_effect", "lease_expired"}:
                state = copy.deepcopy(state)
                job = state["jobs"][binding["job_key"]]
                if kind == "locked":
                    job["fields"]["taxon"]["locked"] = True
                elif kind == "lease_expired":
                    job["lease"]["expires_at"] = datetime.now(timezone.utc).timestamp() - 1
                else:
                    effect = next(iter(state["effects"].values()))
                    effect.update(status="held_unknown", actual_micro_usd=None,
                        held_micro_usd=effect["reservation_micro_usd"], receipt=None)
                    from specimen_digitization.research_harness.persistence import ResearchStore
                    state["budget_totals"] = ResearchStore._budget(state)
                fake.backend.cas(fake._state_scope(specimen_id), binding["program_key"], revision, state)
            elif kind != "unknown_send":
                raise AssertionError(kind)
            rig.refused_expected = {"tables": copy.deepcopy(fake.tables), "snapshots": copy.deepcopy(fake.snapshots),
                "binding": copy.deepcopy(binding), "revision": fake.specimens[specimen_id]["revision"],
                "state": copy.deepcopy(fake.state(specimen_id, binding["program_key"])[1])}
            if kind == "unknown_send":
                raise TimeoutError("offline synthetic publication outcome unknown")
        rig.fake.fail_before["PublishCanonicalResearchProgressV2"] = refuse
    return install


@pytest.mark.parametrize("kind", ["stale_q", "field_bytes", "reading_bytes", "locked", "membership",
    "unknown_effect", "unknown_send", "lease_expired"])
def test_no_carrier_native_refusal_retains_exact_custody_without_science_writes(tmp_path, monkeypatch, kind):
    rig, requests, job, receipts, parsed, specimen, hold, published = composed_case(
        tmp_path, monkeypatch, final_state=WorkState.WAITING_POLICY, without_carrier=True,
        declared_geo_policy=True, verified_coverage=True, fixture_install=refused_progress_fixture(kind))
    assert {request.role for request in requests} == set(SpecialistRole)
    assert len(job["fields"]) == 20 and not any(row["work_state"] == "pending" for row in job["fields"].values())
    assert hold is not None and "reconciliation" in str(hold)
    assert len(receipts) == 1 and published == ["identified_by_irn"]
    assert rig.fake.receipts == rig.refused_receipts and not rig.fake.duplicates
    assert rig.model_calls == rig.refused_model_calls and rig.source_urls == rig.refused_source_urls == []
    expected, commit = rig.refused_expected, rig.refused_commit
    assert rig.fake.tables == expected["tables"] and rig.fake.snapshots == expected["snapshots"]
    assert rig.fake.bindings[rig.specimen_id] == expected["binding"]
    assert rig.fake.specimens[rig.specimen_id]["revision"] == expected["revision"]
    _, state = support.research_state(rig.fake, rig.specimen_id)
    assert state == expected["state"]
    [current] = state["jobs"].values()
    assert current["lease"] is not None
    assert current["lease"] == expected["state"]["jobs"][commit["causal"]["job_key"]]["lease"]
    event = state["outbox"][commit["causal"]["publication_outbox_key"]]
    assert event["delivered"] is False and "canonical_commit" not in event
    assert event["guard"]["operation_kind"] == "progress_only" and "checkpoint_id" not in event["guard"]
    retained = rig.fake.intents[commit["intent_id"]]
    assert retained["payload"]["contract_version"] == "research-progress-intent/v2"
    assert commit["intent_id"] in rig.fake.attempts
    if kind == "membership":
        assert rig.fake.members[support.WORKER] == []
