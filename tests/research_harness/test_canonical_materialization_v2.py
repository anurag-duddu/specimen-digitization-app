"""V2 progress producer source cases; UNCOLLECTED_UNRUN.

Synthetic native import/registration/context authority, genuine shared pure
lineage/projector and actual whole20 work rows. Not Firebase, causal admission,
SDK, mounted host, paid capture or existing-ten qualification.
"""
import asyncio
import copy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from test_canonical_materialization import materialization, native_basis
from test_canonical_projection_v2 import settled_case
from test_native_canonical_contract import ident
from specimen_digitization.application.domain import Disposition, FieldValue, ValueState
from specimen_digitization.application.storage import digest as canonical_digest
from specimen_digitization.research_harness.canonical_materialization_v2 import (
    CanonicalResearchMaterializerV2, MaterializationRequestV2, ResearchCanonicalPolicyV2,
    TerminalFieldProofV2, _qualified_terminal_fields, _work_progress, _scientific_reasons,
)
from specimen_digitization.research_harness.canonical_projection_v2 import project_canonical_value_v2
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.contracts import CollectionProfile, FieldKey, SpecialistRequest, WorkState, digest
from specimen_digitization.research_harness.native_canonical_v2 import CanonicalBindingV2
from specimen_digitization.research_harness.publication import PreparedNativePublication
from specimen_digitization.research_harness.publication_v2 import CanonicalProgressReceiptV2


class SyntheticPrivateContextSource:
    def __init__(self, context):
        self.context = context
        self.calls = 0

    async def read_v2(self, *args):
        self.calls += 1
        return self.context


def v2_case(fixture, sibling_state="pending"):
    b = fixture
    lineage_case = settled_case(b)
    cp, prior, lineage = lineage_case.checkpoint, lineage_case.prior, lineage_case.context
    job = copy.deepcopy(lineage.job)
    job["fields"]["county"]["work_state"] = sibling_state
    lineage = replace(lineage, job=job)
    policy = ResearchCanonicalPolicyV2(canonical_profile_digest=b.policy.canonical_profile_digest,
        research_profile_digest=b.policy.research_profile_digest, source_registry_digest=b.policy.source_registry_digest)
    reg = b.binding.registration.model_dump(mode="json")
    semantic = copy.deepcopy(reg["semantic_mapping"])
    semantic["research_policy_contract_version"] = policy.contract_version
    reg.update(job=job, policy_digest=digest(policy), semantic_mapping=semantic, semantic_mapping_digest=digest(semantic))
    reg["read_bundle"]["job"] = job
    binding = CanonicalBindingV2(**{key: value for key, value in b.binding.model_dump(mode="json").items() if key != "contract_version"},
        authority_digest=digest("explicit synthetic native import authority"), import_proof_id=ident("synthetic-import"),
        import_proof_digest=digest("explicit synthetic native import proof"), head_receipt_id=None,
        head_chain_digest=digest("synthetic native genesis"), causal_chain=())
    # The actual ordinary pack supplies its opaque host identity and packed
    # snapshot SHA. Do not substitute the historical V1 fixture host tag.
    identity = lineage.native_prior_snapshot.canonical
    reg.update(base_canonical=identity.model_dump(mode="json"), current_canonical=identity.model_dump(mode="json"))
    binding = binding.model_copy(update={"canonical":identity,
        "registration": binding.registration.model_validate(reg)})
    raw = b.prepared.model_dump(mode="json")
    raw["publication"]["checkpoints"] = [cp.model_dump(mode="json")]
    native = job["fields"]["country"]["checkpoint"]
    raw["basis"].update(checkpoint_id=native["id"], checkpoint_outbox_key="checkpoint/"+native["id"],
        checkpoint_digest=digest(native),
        typed_checkpoint_digest=digest(cp), original_typed_checkpoint_digest=digest(cp))
    raw["publication"]["guard"]["checkpoint_digests"]["country"] = digest(cp)
    prepared = PreparedNativePublication.model_validate(raw)
    contribution = b.evidence[0].model_copy(update={"canonical_mapping_digest": digest(semantic)})
    context = MaterializationRequestV2(prepared_digest=digest(prepared), canonical_snapshot_sha256=binding.canonical.snapshot_sha256,
        request=lineage.original_request, tool_results=lineage.tool_results, lineage_context=lineage)
    source = SyntheticPrivateContextSource(context)
    return SimpleNamespace(principal=b.principal, prior=prior, prepared=prepared, binding=binding,
        services=b.services, rows=b.rows, evidence=(contribution,), source=source,
        producer=CanonicalResearchMaterializerV2(policy, source), checkpoint=cp)


def produce_v2(b):
    return asyncio.run(b.producer.materialize(b.principal, b.prepared, b.binding, b.prior,
        prior_projection=b.rows, captured_evidence=b.evidence, projection_services=b.services))


@pytest.mark.parametrize("state", ["pending", "researching"])
def test_settled_A_publishes_while_real_B_work_remains_running(materialization, state):
    b = v2_case(materialization, state)
    before = b.prior.model_dump(mode="json")
    work_before = copy.deepcopy(b.binding.registration.job["fields"])
    proof = produce_v2(b)
    assert proof.contract_version == "canonical-policy-materialization/v2"
    assert proof.result.run.fields["country"].literal is None
    assert proof.result.run.fields["country"].normalized == "Peru"
    assert proof.result.run.disposition is None and proof.progress_receipt.disposition is None
    assert proof.policy_receipt["disposition"] is None
    assert proof.result.run.stage == "research_in_progress"
    assert proof.progress_receipt.wire_status == "running" and proof.progress_receipt.exportable is False
    assert proof.progress_receipt.canonical_field_work["county"] == state
    assert proof.progress_receipt.field_work_digest == digest(work_before)
    assert all(proof.result.run.fields[key] == b.prior.run.fields[key] for key in b.prior.run.fields if key != "country")
    assert b.prior.model_dump(mode="json") == before and b.binding.registration.job["fields"] == work_before
    actual = project_canonical_value_v2(b.principal, prior=b.prior, result=proof.result,
        checkpoint=b.checkpoint, context=b.source.context.lineage_context)
    assert proof.lineage_digest == actual.lineage_digest
    assert proof.result_digest == canonical_digest(proof.result.model_dump(mode="json"))
    assert digest(proof.progress_receipt) == proof.progress_receipt_digest


@pytest.mark.parametrize("state", ["waiting_source", "waiting_policy", "operational_failed", "retry_scheduled", "cancelled"])
def test_actual_operational_B_blocks_export_without_human_quality_completion(materialization, state):
    b = v2_case(materialization, state)
    proof = produce_v2(b)
    assert proof.result.run.disposition is None and proof.progress_receipt.disposition is None
    assert proof.result.run.stage == "processing_blocked" and proof.progress_receipt.wire_status == "processing_blocked"
    assert proof.progress_receipt.exportable is False
    assert f"research_work:county:{state}" in proof.progress_receipt.operational_reason_codes
    assert f"research_human_question:county" not in proof.progress_receipt.human_reason_codes
    assert proof.result.run.fields["county"] == b.prior.run.fields["county"]


def test_terminal_claim_requires_actual_whole20_original_field_grounding(materialization):
    b = v2_case(materialization, "resolved")
    proof = produce_v2(b)
    assert proof.result.run.disposition is None and proof.progress_receipt.disposition is None
    assert proof.progress_receipt.wire_status == "processing_blocked" and proof.progress_receipt.exportable is False
    assert "canonical_field_grounding_unproved:date_identified" in proof.progress_receipt.operational_reason_codes
    assert proof.progress_receipt.canonical_field_work["county"] == "resolved"
    assert all(state in {"resolved", "nonblocking_exception"} for state in proof.progress_receipt.canonical_field_work.values())


@pytest.mark.parametrize("change", ["missing_field", "extra_field", "boolean_state", "missing_context", "packed_graph_alias"])
def test_unknown_whole20_mapping_or_private_native_origin_holds(materialization, change):
    b = v2_case(materialization)
    if change == "missing_context":
        b.producer.request_source = object()
    elif change == "packed_graph_alias":
        context = b.source.context.lineage_context
        b.source.context = replace(b.source.context, lineage_context=replace(context, prior_snapshot_sha256=digest("wrong graph")))
    else:
        reg = b.binding.registration.model_copy(deep=True)
        if change == "missing_field": reg.job["fields"].pop("county")
        elif change == "extra_field": reg.job["fields"]["fake"] = {"work_state": "resolved"}
        else: reg.job["fields"]["county"]["work_state"] = True
        b.binding = b.binding.model_copy(update={"registration": reg})
        b.source.context = replace(b.source.context, lineage_context=replace(b.source.context.lineage_context, job=reg.job))
    before = b.prior.model_dump(mode="json")
    with pytest.raises(PublicationUnavailable):
        produce_v2(b)
    assert b.prior.model_dump(mode="json") == before


def test_pending_run_retains_actual_field_human_question_in_distinct_reason_set(materialization):
    b = v2_case(materialization)
    reg = b.binding.registration.model_copy(deep=True)
    reg.job["fields"]["habitat"]["work_state"] = "waiting_human"
    b.binding = b.binding.model_copy(update={"registration": reg})
    b.source.context = replace(b.source.context, lineage_context=replace(b.source.context.lineage_context, job=reg.job))
    proof = produce_v2(b)
    assert proof.result.run.disposition is None and proof.progress_receipt.wire_status == "running"
    assert "research_human_question:habitat" in proof.progress_receipt.human_reason_codes
    assert "research_human_question:habitat" not in proof.progress_receipt.operational_reason_codes


@pytest.mark.parametrize("state,wire,stage", [("pending", "running", "research_in_progress"),
    ("waiting_source", "processing_blocked", "processing_blocked")])
def test_native_writer_publishes_an_unfinished_or_blocked_record_without_a_disposition(materialization, state, wire, stage):
    from specimen_digitization.research_harness.native_canonical_v2 import SqlConnectCanonicalResearchWriterV2
    b = v2_case(materialization, state)
    proof = produce_v2(b)
    writer = SqlConnectCanonicalResearchWriterV2(None, None, blobs=None, operation_client=object())
    intent = SimpleNamespace(operation_digest=digest("synthetic operation"), actor_uid=b.principal.user_id,
        idempotency_key=b.prepared.basis.idempotency_key)
    payload = writer._materialization_v2(b.principal, b.prepared, b.binding, {"projection": list(b.rows)}, b.prior, proof,
        intent=intent, bundle=SimpleNamespace(target=b.source.context), projection_services=b.services,
        captured_evidence=b.evidence)
    assert payload["state"] == wire and payload["snapshot"]["run"]["stage"] == stage
    assert payload["snapshot"]["run"]["disposition"] is None and payload["record"]["disposition"] is None
    # record_version.summary is required: the reasons, or the stage when there are none.
    assert payload["record"]["summary"] == ("; ".join(proof.result.run.reasons) or stage)
    assert len(payload["fields"]) == 20


def terminal_routing_case(materialization, monkeypatch, human_field=None):
    """All 20 fields terminal, with whole-record grounding and the science rules
    stubbed, so only the materializer's routing decides the outcome."""
    from specimen_digitization.research_harness import canonical_materialization_v2 as module
    b = v2_case(materialization, "resolved")
    if human_field is not None:
        reg = b.binding.registration.model_copy(deep=True)
        reg.job["fields"][human_field]["work_state"] = "waiting_human"
        b.binding = b.binding.model_copy(update={"registration": reg})
        b.source.context = replace(b.source.context, lineage_context=replace(b.source.context.lineage_context, job=reg.job))
    monkeypatch.setattr(module, "_qualified_terminal_fields", lambda *args: module.KEYS)
    monkeypatch.setattr(module, "_scientific_reasons", lambda *args, **kwargs: [])
    return b


def test_terminal_record_with_a_human_question_routes_to_review(materialization, monkeypatch):
    proof = produce_v2(terminal_routing_case(materialization, monkeypatch, human_field="habitat"))
    assert proof.result.run.disposition == Disposition.REVIEW and proof.result.run.stage == "finalized"
    assert proof.progress_receipt.disposition == "needs_human_review" and proof.policy_receipt["disposition"] == "needs_human_review"
    assert proof.progress_receipt.wire_status == "completed" and proof.progress_receipt.exportable is False
    assert proof.progress_receipt.human_reason_codes == ("research_human_question:habitat",)
    assert proof.progress_receipt.operational_reason_codes == ()


def test_terminal_record_without_reasons_routes_to_cleared(materialization, monkeypatch):
    proof = produce_v2(terminal_routing_case(materialization, monkeypatch))
    assert proof.result.run.disposition == Disposition.CLEARED and proof.result.run.stage == "finalized"
    assert proof.progress_receipt.disposition == "cleared" and proof.policy_receipt["disposition"] == "cleared"
    assert proof.progress_receipt.wire_status == "completed" and proof.progress_receipt.exportable is True
    assert proof.result.run.reasons == []


def test_date_identified_stays_mandatory_and_emu_irn_exception_does_not_fabricate_party(materialization):
    b = v2_case(materialization, "resolved")
    profile = CollectionProfile.model_validate(b.binding.registration.job["pins"]["profile"])
    result = b.prior.model_copy(deep=True)
    result.run.fields["date_identified"] = FieldValue(state=ValueState.UNKNOWN)
    _, work, _, _ = _work_progress(b.binding.registration, b.checkpoint, result.run)
    reasons = _scientific_reasons(result, profile, 2000000000.0, latest_work=work,
        field_mapping=b.binding.registration.field_mapping, scientific_qualified=frozenset())
    assert "mandatory_unresolved:date_identified" in reasons
    assert "mandatory_unresolved:identified_by_irn" not in reasons
    assert result.run.fields["identified_by_irn"].authority_identity is None


def test_external_graph_policy_receipt_retains_exact_prepack_metadata(materialization, tmp_path):
    from specimen_digitization.application.active_graph import pack, unpack
    from specimen_digitization.application.storage import LocalBlobs
    from test_canonical_projection_v2 import native_snapshot_proof
    b = v2_case(materialization)
    b.prior.run.reading_metadata["synthetic-large-label-context"] = "x" * 120000
    blobs = LocalBlobs(tmp_path / "actual-original-and-result-graphs")
    native = native_snapshot_proof(b.prior, b.binding.canonical.record_version_id, blobs)
    reg = b.binding.registration.model_copy(update={"base_canonical": native.canonical, "current_canonical": native.canonical})
    b.binding = b.binding.model_copy(update={"canonical": native.canonical, "registration": reg})
    lineage = replace(b.source.context.lineage_context, native_prior_snapshot=native,
        prior_snapshot_sha256=canonical_digest(b.prior.model_dump(mode="json")))
    b.source.context = replace(b.source.context, canonical_snapshot_sha256=native.canonical.snapshot_sha256, lineage_context=lineage)
    proof = produce_v2(b)
    assert proof.policy_receipt["prepack_active_graph"] == native.snapshot["active_graph"]
    assert proof.policy_receipt["prepack_native_snapshot_digest"] == native.canonical.snapshot_sha256
    assert proof.policy_receipt["prepack_full_graph_digest"] == lineage.prior_snapshot_sha256
    packed_result = pack(proof.result.model_copy(deep=True), blobs)
    retained = unpack(packed_result, blobs)
    assert retained.active_graph != proof.policy_receipt["prepack_active_graph"]
    assert canonical_digest(retained.model_dump(mode="json")) != proof.result_digest
    # The sole native receipt consumer must verify metadata against its actual
    # winning used snapshot, then restore it for the prepack-policy SHA check.
    retained.active_graph = copy.deepcopy(proof.policy_receipt["prepack_active_graph"])
    assert canonical_digest(retained.model_dump(mode="json")) == proof.result_digest


def test_terminal_target_uses_actual_field_in_a_multiple_field_request(materialization):
    b = v2_case(materialization)
    old = b.source.context
    original = old.request
    request = SpecialistRequest.model_validate({**original.model_dump(mode="json"),
        "field_keys": [str(FieldKey.COUNTY), str(FieldKey.COUNTRY)],
        "field_revisions": {str(FieldKey.COUNTY): 0, str(FieldKey.COUNTRY): b.checkpoint.revision - 1}})
    lineage = replace(old.lineage_context, original_request=request)
    b.source.context = replace(old, request=request, lineage_context=lineage)
    proof = produce_v2(b)
    assert request.field_keys[0] != b.checkpoint.field_key
    assert proof.result.run.fields["country"].normalized == "Peru"
    assert proof.result.run.fields["county"] == b.prior.run.fields["county"]
    assert proof.progress_receipt.wire_status == "running"
    assert proof.progress_receipt.exportable is False


def reused_v2_case(materialization):
    """Explicit synthetic retained history; never native generation authority."""
    b = v2_case(materialization)
    old = b.source.context
    original = b.checkpoint
    current_scope = original.scope.model_copy(update={"generation": original.scope.generation + 1})
    identity = {key: getattr(current_scope, key)
        for key in ("organization_id", "collection_id", "specimen_id", "job_id", "generation")}
    job = copy.deepcopy(b.binding.registration.job)
    native = copy.deepcopy(job["fields"]["country"]["checkpoint"])
    history = {"scope": native["scope"], "binding_digest": job["binding_digest"],
        "pins": copy.deepcopy(job["pins"]), "fields": copy.deepcopy(job["fields"])}
    job["generation"] = current_scope.generation
    job["history"] = [history]
    job["fields"]["country"]["reuse"] = {
        "reused_from_scope_digest": digest(native["scope"]), "checkpoint_digest": digest(native),
        "into_scope_digest": digest(identity), "source_binding_digest": job["binding_digest"],
        "target_binding_digest": job["binding_digest"], "retained_dependencies": native["dependencies"],
        "retained_dependency_digests": native["dependency_digests"]}
    current = original.model_validate({**original.model_dump(mode="json"),
        "scope": current_scope.model_dump(mode="json"), "reused_from_scope_digest": digest(original.scope),
        "reused_from_checkpoint_digest": digest(original)})
    raw = b.prepared.model_dump(mode="json")
    raw["publication"]["checkpoints"] = [current.model_dump(mode="json")]
    raw["publication"]["guard"]["scope"] = current_scope.model_dump(mode="json")
    raw["publication"]["guard"]["checkpoint_digests"] = {"country": digest(current)}
    raw["basis"].update(scope=current_scope.model_dump(mode="json"),
        original_scope=original.scope.model_dump(mode="json"), reused=True, history_digest=digest(history),
        checkpoint_id=native["id"], checkpoint_digest=digest(native),
        original_typed_checkpoint_digest=digest(original), typed_checkpoint_digest=digest(current),
        checkpoint_outbox_key="checkpoint/" + native["id"])
    raw["basis"]["lease"]["generation"] = current_scope.generation
    b.prepared = PreparedNativePublication.model_validate(raw)
    reg = b.binding.registration.model_copy(update={"generation": current_scope.generation, "job": job,
        "read_bundle": {**b.binding.registration.read_bundle, "job": job}})
    b.binding = b.binding.model_copy(update={"registration": reg})
    b.checkpoint = b.prepared.publication.checkpoints[0]
    lineage = replace(old.lineage_context, scope=b.checkpoint.scope, job=b.binding.registration.job)
    b.source.context = replace(old, prepared_digest=digest(b.prepared), lineage_context=lineage)
    return b, history, old


def test_current_typed_reuse_view_reaches_value_and_terminal_verifier(materialization):
    b, history, original_context = reused_v2_case(materialization)
    before = copy.deepcopy(b.binding.registration.job["history"])
    proof = produce_v2(b)
    assert b.checkpoint.scope.generation == original_context.request.scope.generation + 1
    assert b.source.context.request == original_context.request
    assert b.source.context.request.scope != b.source.context.lineage_context.scope
    assert b.checkpoint.reused_from_checkpoint_digest == digest(
        original_context.lineage_context.job["fields"]["country"]["checkpoint"]["payload"])
    assert proof.result.run.fields["country"].normalized == "Peru"
    assert proof.result.run.stage == "research_in_progress"
    assert proof.progress_receipt.wire_status == "running"
    assert b.binding.registration.job["history"] == before == [history]
    assert all(proof.result.run.fields[key] == b.prior.run.fields[key]
        for key in b.prior.run.fields if key != "country")
    projected = project_canonical_value_v2(b.principal, prior=b.prior, result=proof.result,
        checkpoint=b.checkpoint, context=b.source.context.lineage_context)
    assert projected.lineage_digest == proof.lineage_digest


def test_original_payload_cannot_replace_actual_current_terminal_view(materialization):
    b, _, original_context = reused_v2_case(materialization)
    proof = produce_v2(b)
    original = b.checkpoint.model_validate(
        original_context.lineage_context.job["fields"]["country"]["checkpoint"]["payload"])
    with pytest.raises(PublicationUnavailable):
        _qualified_terminal_fields(b.prior, proof.result,
            TerminalFieldProofV2(original, b.source.context.lineage_context), (),
            proof.progress_receipt.canonical_field_work)
    assert b.source.context.request == original_context.request


def test_duplicate_native_terminal_proof_is_ambiguous(materialization):
    b = v2_case(materialization)
    proof = produce_v2(b)
    field = TerminalFieldProofV2(b.checkpoint, b.source.context.lineage_context)
    with pytest.raises(PublicationUnavailable):
        _qualified_terminal_fields(b.prior, proof.result, field, (field,),
            proof.progress_receipt.canonical_field_work)
    assert proof.progress_receipt.exportable is False
