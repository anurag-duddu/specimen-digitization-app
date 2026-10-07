"""Final whole-record progress travels on a genuine unsent checkpoint.

Pure selection controls and the production composer use only synthetic labels,
FunctionModels, SQLite, and the existing fake native connector. No live model,
source, SQL, or production mutation is performed.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

import production_e2e_support as support
from test_production_bridge import RESEARCH_SCOPE, checkpoint, principal, thread, waiting
from test_native_canonical_contract import helper_resolutions
from test_unkeyed_label_reading_citation import build_rig, no_network, run_research  # noqa: F401
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
from specimen_digitization.research_harness.persistence import DurabilityScope


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
        progress = SimpleNamespace(job_key=durability.key, generation=durability.generation,
            field_work_digest=digest(job["fields"]) if progress_current else "0" * 64,
            research_field_work={key: field["work_state"] for key, field in job["fields"].items()},
            field_mapping_digest=digest({}), policy_digest="b" * 64, run_stage=canonical_stage,
            wire_status="completed" if canonical_stage == "finalized" else
                "processing_blocked" if canonical_stage == "processing_blocked" else "running")
        causal = SimpleNamespace(receipt_id="actual-native-head", resulting="current-canonical",
            scope_identity=durability.identity(), job_key=durability.key, progress_receipt=progress)
        return SimpleNamespace(causal_chain=(causal,), head_receipt_id=causal.receipt_id,
            canonical=causal.resulting, registration=SimpleNamespace(job=job, field_mapping={}, policy_digest="b" * 64))

    async def read_thread(_runtime):
        return thread(*checkpoints)

    runtime = SimpleNamespace(binding=SimpleNamespace(research_scope=lambda: RESEARCH_SCOPE),
        scope=durability, blobs=None, journal=SimpleNamespace(load=load),
        store=SimpleNamespace(_read=lambda scope: SimpleNamespace(state={"outbox": {
            str(index): event for index, event in enumerate(events)}}), _job=lambda state, scope: job),
        canonical_service=SimpleNamespace(publish_checkpoint=publish, winning_receipt=winning_receipt,
            read_current_binding=read_current_binding))
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
    assert outcome.reason_code == "final_research_progress_requires_native_publication"


@pytest.mark.parametrize("canonical_stage", ["research_in_progress", "running", "finalized", "processing_blocked"])
def test_terminal_work_without_a_new_publication_reads_current_canonical_progress(monkeypatch, canonical_stage):
    cp = waiting(FieldKey.TAXON, WorkState.WAITING_SOURCE)
    outcome, prepared, proofs, reads = publish_pass(monkeypatch, (cp,), canonical_stage=canonical_stage)
    assert prepared == proofs == []
    assert reads == [(principal().scope, RESEARCH_SCOPE.specimen_id)]
    if canonical_stage in {"research_in_progress", "running"}:
        assert (outcome.status, outcome.reason_code) == ("blocked", "final_research_progress_requires_native_publication")
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
        "blocked", "final_research_progress_requires_native_publication")


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


def composed_case(tmp_path, monkeypatch, *, final_state, without_carrier=False, declared_geo_policy=False):
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
        parsed, specimen, hold, published = run_research(rig, models)
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


def test_no_genuine_carrier_exposes_native_progress_gate_without_fabrication(tmp_path, monkeypatch):
    rig, requests, job, receipts, parsed, specimen, hold, published = composed_case(
        tmp_path, monkeypatch, final_state=WorkState.WAITING_POLICY, without_carrier=True)
    assert {request.role for request in requests} == set(SpecialistRole)
    assert len(receipts) == 1 and published == ["identified_by_irn"] and not rig.fake.duplicates
    assert receipts[0]["causal_proof"]["progress_receipt"]["run_stage"] == "research_in_progress"
    assert any(value == "pending" for value in receipts[0]["causal_proof"]["progress_receipt"]["research_field_work"].values())
    assert str(hold) == "final_research_progress_requires_native_publication"
    assert specimen.run.stage == "research_in_progress"
    assert len(job["fields"]) == 20 and all(row["checkpoint"] is not None for row in job["fields"].values())
    assert all(row["work_state"] != "pending" for row in job["fields"].values())
