"""Actual data entrypoints and ordinary graph pack/unpack controls. UNRUN.

No real specimen, ledger import, Storage/native connector or spend is represented.
"""
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from test_native_canonical_v2_contract import causal, call, retained_fixture, basis_v1
from specimen_digitization.application import active_graph
from specimen_digitization.application.domain import AuditEvent
from specimen_digitization.application.storage import digest as graph_digest
from specimen_digitization.research_harness.contracts import digest
from specimen_digitization.research_harness.native_canonical import PublicationUnavailable
from specimen_digitization.research_harness.native_materialization_inputs_v2 import (
    NativeMaterializationLoadV2, exact_object, int64_decimal, strict_int, strict_json, exact_types_equal,
)
from specimen_digitization.research_harness.native_prepack_proof_v2 import (
    make_prepack_proof_v2, verify_prepack_proof_v2,
)


@pytest.mark.parametrize("bad", [True, False, 1.0, "1", -1])
def test_actual_loader_rejects_noncanonical_CAS_without_coercion(bad):
    with pytest.raises(PublicationUnavailable):
        strict_int(bad)


@pytest.mark.parametrize("bad", [1, True, 1.0, "01", "+1", "-1", "1.0", "9223372036854775808"])
def test_actual_Int64_wire_does_not_alias_numbers_or_noncanonical_strings(bad):
    with pytest.raises(PublicationUnavailable):
        int64_decimal(bad)


def test_actual_Int64_wire_preserves_full_precision_and_zero():
    assert int64_decimal("9223372036854775807") == 9223372036854775807
    assert int64_decimal("0") == 0
    assert not exact_types_equal({"generation": 1}, {"generation": 1.0})


@pytest.mark.parametrize("right,expected", [
    ({"nested": {"items": [15.0, False], "value": 1}}, True),
    ({"nested": {"items": [15.0, False], "different": 1}}, False),
    ({"nested": {"value": 1, "items": [15, False]}}, False),
    ({"nested": {"value": 1, "items": [15.0, 0]}}, False),
])
def test_exact_nested_types_compare_unordered_keys_without_numeric_coercion(right, expected):
    assert exact_types_equal({"nested": {"value": 1, "items": [15.0, False]}}, right) is expected


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'])
def test_private_state_json_cannot_erase_duplicate_or_nonfinite_identity(text):
    with pytest.raises(PublicationUnavailable):
        strict_json(text)


def test_new_envelope_requires_exact_keys_before_old_binding_decoder():
    with pytest.raises(PublicationUnavailable):
        exact_object({"binding": {}}, {"organizationMember", "collectionMember", "specimen", "binding"}, "outer_missing")
    assert exact_object({"a": 1}, {"a"}, "bad") == {"a": 1}


def test_actual_materialization_entry_returns_retained_receipt_without_mutable_query(causal):
    c = causal
    writer, connector = retained_fixture(c)
    loaded = call(c, lambda: writer.get_materialization_bundle_v2(c.b.principal, c.p.basis.scope.specimen_id,
        idempotency_key=c.intent.idempotency_key, request_identity_digest=c.intent.server_request_identity_digest,
        preparation_id=c.prep.id))
    assert loaded.inputs is None and loaded.replayed_result.replayed
    assert connector.calls == ["GetResearchPublicationIntentV2", "GetResearchPublicationReceiptV2"]


def test_actual_checkpoint_entry_restarts_before_discovery_or_provider(causal):
    c = causal
    writer, connector = retained_fixture(c)
    result = call(c, lambda: writer.publish_checkpoint(c.b.principal, c.p,
        server_request_identity_digest=c.intent.server_request_identity_digest))
    assert result.replayed and result.causal.winning_preparation_id == c.prep.id
    assert connector.calls == ["GetResearchPublicationIntentV2", "GetResearchPublicationReceiptV2"]


def test_actual_checkpoint_unknown_attempt_never_prepares_or_reissues(causal):
    c = causal
    writer, connector = retained_fixture(c)
    connector.row = None
    with pytest.raises(PublicationUnavailable, match="attempt_outcome_unknown"):
        call(c, lambda: writer.publish_checkpoint(c.b.principal, c.p,
            server_request_identity_digest=c.intent.server_request_identity_digest))
    assert connector.calls == ["GetResearchPublicationIntentV2", "GetResearchPublicationReceiptV2"]


class ImmutableMemoryGraphs:
    def __init__(self):
        self.items = {}
    def put(self, raw):
        key = hashlib.sha256(raw).hexdigest()
        prior = self.items.setdefault(key, bytes(raw))
        assert prior == raw
        return key
    def get_bounded(self, key, limit):
        value = self.items[key]
        assert len(value) <= limit
        return value


def packed_proof(c, monkeypatch):
    monkeypatch.setattr(active_graph, "GRAPH_THRESHOLD", 1)
    blobs = ImmutableMemoryGraphs()
    old = c.b.prior.model_copy(deep=True)
    active_graph.pack(old, blobs)  # genuine predecessor already has external metadata
    policy = old.model_copy(deep=True)
    policy.version += 1
    policy.run.stage = "research_in_progress"
    post = policy.model_copy(deep=True)
    audit_id = "10000000-0000-0000-0000-000000000001"
    native_version = "10000000-0000-0000-0000-000000000002"
    post.audit.append(AuditEvent(id=audit_id, actor=c.b.principal.user_id, action="research_publication",
        reason=c.intent.operation_digest, before={"revision": old.version},
        after={"revision": post.version, "record_version_id": native_version}))
    progress = SimpleNamespace(result_digest=graph_digest(policy.model_dump(mode="json")),
        run_stage=policy.run.stage, disposition=str(policy.run.disposition))
    before_pack = post.model_copy(deep=True)
    packed = active_graph.pack(post, blobs)
    proof = make_prepack_proof_v2(policy, before_pack, packed, progress=progress, audit_id=audit_id,
        actor_uid=c.b.principal.user_id, operation_digest=c.intent.operation_digest, native_record_version_id=native_version)
    retained = active_graph.unpack(copy.deepcopy(packed), blobs)
    return proof, retained, packed, progress, audit_id, native_version


def test_actual_ordinary_external_pack_restart_preserves_both_prepack_and_packed_identities(causal, monkeypatch):
    c = causal
    proof, retained, packed, progress, audit_id, native_version = packed_proof(c, monkeypatch)
    original_post = json.loads(proof["post_audit_graph_json"])
    assert original_post["active_graph"] != proof["packing_metadata"]
    # A fresh repository reconstruction retains new metadata. No old audit-pop
    # digest shortcut may equate it with the immutable pure-policy graph.
    assert graph_digest(retained.model_dump(mode="json")) != progress.result_digest
    policy = verify_prepack_proof_v2(proof, expected_digest=digest(proof), retained=retained,
        packed_snapshot=packed, progress=progress, audit_id=audit_id, actor_uid=c.b.principal.user_id,
        operation_digest=c.intent.operation_digest, native_record_version_id=native_version)
    assert graph_digest(policy) == progress.result_digest
    assert original_post["active_graph"] == policy["active_graph"]


@pytest.mark.parametrize("tamper", ["old_metadata", "policy_body", "post_body", "packed_digest", "actor"])
def test_actual_external_graph_prepack_restart_refuses_unproved_changes(causal, monkeypatch, tamper):
    c = causal
    proof, retained, packed, progress, audit_id, native_version = packed_proof(c, monkeypatch)
    if tamper == "old_metadata":
        retained.active_graph = json.loads(proof["post_audit_graph_json"])["active_graph"]
    if tamper == "policy_body":
        value = json.loads(proof["policy_graph_json"])
        value["version"] += 1
        proof["policy_graph_json"] = json.dumps(value)
    if tamper == "post_body":
        value = json.loads(proof["post_audit_graph_json"])
        value["run"]["stage"] = "processing_blocked"
        proof["post_audit_graph_json"] = json.dumps(value)
        proof["post_audit_graph_digest"] = graph_digest(value)
    if tamper == "packed_digest":
        proof["packed_snapshot_digest"] = digest("foreign")
    if tamper == "actor":
        retained.audit[-1].actor = "foreign-reviewer"
    with pytest.raises(PublicationUnavailable):
        verify_prepack_proof_v2(proof, expected_digest=digest(proof), retained=retained, packed_snapshot=packed,
            progress=progress, audit_id=audit_id, actor_uid=c.b.principal.user_id,
            operation_digest=c.intent.operation_digest, native_record_version_id=native_version)


def test_tagged_native_load_never_claims_both_receipt_and_mutable_inputs():
    with pytest.raises(PublicationUnavailable):
        NativeMaterializationLoadV2()
    with pytest.raises(PublicationUnavailable):
        NativeMaterializationLoadV2(replayed_result=object(), inputs=object())


def test_missing_historical_prepack_proof_is_hold_not_audit_pop_reconstruction(causal):
    c = causal
    writer, connector = retained_fixture(c)
    del connector.row["prepack"]
    with pytest.raises(PublicationUnavailable, match="receipt_partial"):
        call(c, lambda: writer.resume_same_operation(c.b.principal, c.p.basis.scope.specimen_id,
            c.intent.idempotency_key, c.intent.server_request_identity_digest))
    assert connector.calls == ["GetResearchPublicationIntentV2", "GetResearchPublicationReceiptV2"]


def test_native_checkpoint_raw_generation_bool_is_rejected_before_typed_model(causal):
    from specimen_digitization.research_harness.native_materialization_inputs_v2 import _current_checkpoint
    c = causal
    original = copy.deepcopy(c.job)
    original["fields"]["country"]["checkpoint"]["payload"]["scope"]["generation"] = True
    with pytest.raises(PublicationUnavailable, match="integer_invalid"):
        _current_checkpoint(original, "country", c.p.basis.scope)
    assert c.job["fields"]["country"]["checkpoint"]["payload"]["scope"]["generation"] == 1


def native_materialization_response(c):
    from datetime import datetime, timezone
    from test_native_canonical_v2_contract import writes
    from specimen_digitization.research_harness import publication_v2
    # Actual ordinary projector rows, with an explicit synthetic SQL wrapper.
    # This exercises the real DTO decoder, not native acceptance or live authority.
    response=copy.deepcopy(c.b.raw)
    response["organizationMember"]={"active":True}
    response["collectionMember"]={"active":True,"role":c.b.principal.role,"canViewSensitive":False}
    response["specimen"]={"sensitive":False}
    # The old fixture raw is binding-only. Preserve it as the strict old-six
    # subset and construct the new envelope explicitly for this caller control.
    old={k:copy.deepcopy(c.b.raw[k]) for k in ("canonical","registrations","snapshot","projection")}
    reg=old["registrations"][0]
    reg["job"]=copy.deepcopy(c.job)
    reg["registration_revision"]=1
    reg["current_canonical"]=c.intent.original_base.model_dump(mode="json")
    reg["publication_transition"]=None
    bundle=reg["read_bundle"]
    bundle.update(state_revision=7,job=copy.deepcopy(c.job),job_key=c.intent.job_key,
        halted=False,paused=c.job["paused"],effects={},outbox={},hold_reasons=[])
    old["active_registration_count"]=1
    old["causal"]={"contract_version":publication_v2.OPERATION_V2,
        "authority_digest":c.intent.authority_digest,"import_proof_id":str(c.intent.import_proof_id),
        "import_proof_digest":c.intent.import_proof_digest,"head_receipt_id":None,
        "head_chain_digest":publication_v2.genesis_digest(c.intent.binding_id,c.intent.original_base),
        "causal_chain":[],"causal_count":0}
    scope=c.b.principal.scope
    projected=writes(c.b.prior,c.b.connector.locate,c.b.connector._sized,c.b.principal.user_id)
    operations={"AppendRecordVersionV2":"record_versions","AppendResolvedFieldV2":"resolved_fields",
        "AppendFieldCandidateV2":"candidates","AppendCandidateEvidenceV2":"candidate_evidence",
        "AppendEvidenceItemV2":"evidence","AppendToolCallV1":"tool_calls","AppendValidationFindingV2":"findings"}
    projections={name:[] for name in operations.values()}
    native_ops={"AppendPipelineRunV2":"runs","AppendLabelRegionV2":"regions","AppendModelObservationV2":"observations",
        "AppendTranscriptionVersionV2":"transcriptions","AppendHarnessInputV1":"handoffs",
        "AppendReadingComparisonV1":"comparisons","AppendSourceAssetV2":"assets"}
    native={name:[] for name in native_ops.values()}
    for write in projected:
        row=copy.deepcopy(write.variables)
        row.update(organizationId=scope.organization_id,collectionId=scope.collection_id)
        if write.operation in operations:
            projections[operations[write.operation]].append(row)
        if write.operation in native_ops:
            if write.operation=="AppendSourceAssetV2":
                row["byteSize"]=str(row["byteSize"])
            native[native_ops[write.operation]].append(row)
    record=next(row for row in projections["record_versions"] if row["id"]==str(c.intent.original_base.record_version_id))
    checkpoint=c.job["fields"][str(c.p.basis.field_key)]["checkpoint"]["payload"]
    raw={"contract_version":"research-native-materialization-inputs/v2",
        "observed_at":datetime.fromtimestamp(bundle["server_time"],timezone.utc).isoformat(),
        "registration":copy.deepcopy(reg),"outer_intent":{"original":c.intent.model_dump(mode="json"),
            "preparations":[c.prep.model_dump(mode="json")],"preparation_count":1,"attempt":None},
        "scoped_state":copy.deepcopy(bundle),
        "private_state_integrity":{"revision":7,"contract_version":"research-durability/v1",
            "state_json":json.dumps(c.state,separators=(",",":"),allow_nan=False),"state":copy.deepcopy(c.state)},
        "current_snapshot":copy.deepcopy(old["snapshot"]),
        "preparation_snapshot":{"identity":c.prep.anchor.model_dump(mode="json"),
            "snapshot":copy.deepcopy(old["snapshot"]),"record":{"id":record["id"],"runId":record["runId"],"predecessorId":record.get("predecessorId")}},
        "retained_history":[],"projection_rows":projections,
        "checkpoint_inputs":{"target":checkpoint,"terminal_siblings":[]},
        "original_request_sources":[],"captured_executions":[],"native_input_rows":native,
        "lineage_rows":{key:[] for key in ("value_lineages","value_dependencies","value_evidence","tool_input_lineage","captured_tool_executions")},
        "prepack_proof":None}
    old["materialization_inputs"]=raw
    return {"organizationMember":{"active":True},
        "collectionMember":{"active":True,"role":c.b.principal.role,"canViewSensitive":False},
        "specimen":{"sensitive":False},"binding":old}


def test_actual_full_native_envelope_decodes_same_original_and_current_target(causal):
    from specimen_digitization.research_harness.native_materialization_inputs_v2 import NativeMaterializationInputsV2
    c=causal;response=native_materialization_response(c)
    loaded=NativeMaterializationInputsV2.from_response(c.b.principal,c.intent,c.prep,response)
    key=str(c.p.basis.field_key)
    assert loaded.preparation==c.prep and loaded.intent==c.intent
    assert loaded.checkpoint_pairs[key]["original"]==c.job["fields"][key]["checkpoint"]
    assert loaded.native_inputs["checkpoint_inputs"]["target"]==c.p.publication.checkpoints[0].model_dump(mode="json")
    assert loaded.state_document==c.state and loaded.state_revision==7
    assert loaded.native_inputs["private_state_integrity"]["state_digest"]==digest(c.state)
    assert "state" not in loaded.native_inputs["private_state_integrity"]


def test_native_materialization_keeps_key_order_and_isolates_nested_inputs(causal):
    from specimen_digitization.research_harness.native_materialization_inputs_v2 import NativeMaterializationInputsV2
    c = causal
    # The real transport decodes independent JSON trees, not shared fixture aliases.
    response = json.loads(json.dumps(native_materialization_response(c)))
    raw = response["binding"]["materialization_inputs"]
    loaded = NativeMaterializationInputsV2.from_response(c.b.principal, c.intent, c.prep, response)
    assert list(loaded.native_inputs) == list(raw)
    assert loaded.guard["inputs_digest"] == digest(loaded.native_inputs)
    assert loaded.native_inputs["private_state_integrity"]["state_digest"] == loaded.guard["state_digest"] == digest(c.state)
    original_row = raw["projection_rows"]["resolved_fields"][0]
    returned_row = loaded.native_inputs["projection_rows"]["resolved_fields"][0]
    guard_row = loaded.guard["projection_rows"]["resolved_fields"][0]
    field_key = original_row["fieldKey"]
    original_row["fieldKey"] = "changed-original"
    assert returned_row["fieldKey"] == guard_row["fieldKey"] == field_key
    returned_row["fieldKey"] = "changed-returned"
    assert original_row["fieldKey"] == "changed-original"
    assert guard_row["fieldKey"] == field_key


@pytest.mark.parametrize("tamper",["unknown_alias","ambiguous_registration","duplicate_field","foreign_row","state_float","changed_original","missing_source_record","changed_packed_body","changed_anchor_body","snapshot_float_revision"])
def test_actual_full_native_envelope_refuses_ambiguous_or_foreign_facts(causal,tamper):
    from specimen_digitization.research_harness.native_materialization_inputs_v2 import NativeMaterializationInputsV2
    c=causal;response=native_materialization_response(c);binding=response["binding"];raw=binding["materialization_inputs"]
    if tamper=="unknown_alias":binding["forged"]={}
    if tamper=="ambiguous_registration":binding["active_registration_count"]=2
    if tamper=="duplicate_field":raw["projection_rows"]["resolved_fields"].append(copy.deepcopy(raw["projection_rows"]["resolved_fields"][0]))
    if tamper=="foreign_row":raw["projection_rows"]["record_versions"][0]["collectionId"]="10000000-0000-0000-0000-000000000099"
    if tamper=="state_float":raw["private_state_integrity"]["state"]["jobs"][c.intent.job_key]["generation"]=1.0
    if tamper=="changed_original":raw["checkpoint_inputs"]["target"]["revision"]+=1
    if tamper=="missing_source_record":raw["projection_rows"]["record_versions"]=[]
    if tamper=="changed_packed_body":raw["current_snapshot"]["snapshot"]["run"]["stage"]="foreign-state"
    if tamper=="changed_anchor_body":raw["preparation_snapshot"]["snapshot"]["snapshot"]["run"]["stage"]="foreign-state"
    if tamper=="snapshot_float_revision":raw["current_snapshot"]["revision"]=float(raw["current_snapshot"]["revision"])
    with pytest.raises(PublicationUnavailable):
        NativeMaterializationInputsV2.from_response(c.b.principal,c.intent,c.prep,response)


def test_actual_full_native_envelope_revoked_member_is_permission_failure(causal):
    from specimen_digitization.research_harness.native_materialization_inputs_v2 import NativeMaterializationInputsV2
    c=causal;response=native_materialization_response(c);response["collectionMember"]["active"]=False
    with pytest.raises(PermissionError):
        NativeMaterializationInputsV2.from_response(c.b.principal,c.intent,c.prep,response)


def locator_response(c):
    row={"contract_version":"retained-publication-locator/v2","intent_id":str(c.intent.id),
        "original_scope":c.p.basis.scope.model_dump(mode="json"),"program_key":c.intent.program_key,
        "idempotency_key":c.intent.idempotency_key,"request_identity_digest":c.intent.server_request_identity_digest,
        "receipt_present":True,"attempt_present":True}
    return {"organizationMember":{"active":True},
        "collectionMember":{"active":True,"role":c.b.principal.role,"canViewSensitive":False},
        "specimen":{"sensitive":False},"inventory":{"locator_count":1,"locators":[row]}}


def locator_connector(c,monkeypatch,response):
    writer,connector=retained_fixture(c);original=connector.execute
    def execute(operation,variables,mutation=False):
        if operation=="GetRetainedResearchPublicationLocatorsV2":
            connector.calls.append(operation)
            assert not mutation and variables["actorUid"]==c.b.principal.user_id
            assert variables["specimenId"]==c.p.basis.scope.specimen_id
            return copy.deepcopy(response)
        return original(operation,variables,mutation=mutation)
    monkeypatch.setattr(connector,"execute",execute)
    return writer,connector


def test_actual_specimen_locator_and_winner_facade_needs_no_journal_or_runtime(causal,monkeypatch):
    c=causal;writer,connector=locator_connector(c,monkeypatch,locator_response(c))
    assert writer.journal is None and writer.materializer is None
    rows=call(c,lambda:writer.list_retained_publication_locators(c.b.principal,c.p.basis.scope.specimen_id))
    assert len(rows)==1 and rows[0].original_scope==c.p.basis.scope
    assert rows[0].program_key==c.intent.program_key and rows[0].intent_id==c.intent.id
    winner=call(c,lambda:writer.read_winning_receipt(c.b.principal,rows[0].original_scope.specimen_id,
        rows[0].idempotency_key,rows[0].request_identity_digest))
    assert winner.replayed and winner.causal.intent_id==rows[0].intent_id
    assert connector.calls==["GetRetainedResearchPublicationLocatorsV2","GetResearchPublicationIntentV2","GetResearchPublicationReceiptV2"]
    assert winner.causal.progress_receipt.wire_status=="running"  # a winner is not whole20 completion


@pytest.mark.parametrize("tamper",["overflow","generation_bool","duplicate","foreign_scope","false_receipt_type","missing_locator"])
def test_actual_immutable_inventory_refuses_partial_aliases_and_foreign_scopes(causal,monkeypatch,tamper):
    c=causal;response=locator_response(c);inventory=response["inventory"];row=inventory["locators"][0]
    if tamper=="overflow":inventory.update(locator_count=21,locators=None)
    if tamper=="generation_bool":row["original_scope"]["generation"]=True
    if tamper=="duplicate":inventory["locators"].append(copy.deepcopy(row));inventory["locator_count"]=2
    if tamper=="foreign_scope":row["original_scope"]["collection_id"]="10000000-0000-0000-0000-000000000099"
    if tamper=="false_receipt_type":row["receipt_present"]=1
    if tamper=="missing_locator":inventory["locators"]=[]
    writer,connector=locator_connector(c,monkeypatch,response)
    with pytest.raises((PublicationUnavailable,ValueError)):
        call(c,lambda:writer.list_retained_publication_locators(c.b.principal,c.p.basis.scope.specimen_id))
    assert connector.calls==["GetRetainedResearchPublicationLocatorsV2"]


def test_read_only_winner_absence_never_continues_unexecuted_intent(causal):
    c=causal;writer,connector=retained_fixture(c)
    connector.row=None;connector.intent_row["attempt"]=None
    assert call(c,lambda:writer.read_winning_receipt(c.b.principal,c.p.basis.scope.specimen_id,
        c.intent.idempotency_key,c.intent.server_request_identity_digest)) is None
    assert connector.calls==["GetResearchPublicationIntentV2","GetResearchPublicationReceiptV2"]


def test_read_only_winner_unknown_attempt_is_hold_without_runtime(causal):
    c=causal;writer,connector=retained_fixture(c);connector.row=None
    with pytest.raises(PublicationUnavailable,match="attempt_outcome_unknown"):
        call(c,lambda:writer.read_winning_receipt(c.b.principal,c.p.basis.scope.specimen_id,
            c.intent.idempotency_key,c.intent.server_request_identity_digest))
    assert connector.calls==["GetResearchPublicationIntentV2","GetResearchPublicationReceiptV2"]


# These controls exercise the real typed provider/captured receipt branch only.
# The upstream accepted-output reader/validator is qualified separately; this
# fixture supplies its already-decoded acceptance view without minting authority.
def receipt_binding_case(tmp_path):
    import asyncio
    from test_canonical_evidence_provider_v2 import make_native_capture_rig
    from specimen_digitization.research_harness.native_canonical_v2 import SqlConnectCanonicalResearchWriterV2
    f = make_native_capture_rig(tmp_path)
    items = asyncio.run(f.provider.capture_v2(f.principal, f.prepared, f.binding, f.prior))
    proof = SimpleNamespace(acceptance=SimpleNamespace(
        original_request=f.rig.request, source_results=(f.result,)))
    writer = SqlConnectCanonicalResearchWriterV2(f.repository, None, blobs=f.rig.blobs)
    return f, writer, items, {str(f.checkpoint.field_key): proof}


def test_actual_capture_native_binding_has_no_scope_and_uses_true_tool_receipt(tmp_path):
    f, writer, items, accepted = receipt_binding_case(tmp_path)
    assert "scope" not in type(items[0].proof.receipt).model_fields
    assert accepted[str(f.checkpoint.field_key)].acceptance.source_results[0].receipt.scope == f.rig.request.scope
    before = copy.deepcopy(f.binding.registration.read_bundle)
    writer._verify_capture_bindings_v2(f.prepared, f.binding, f.prior, items, accepted)
    assert f.binding.registration.read_bundle == before
    assert len(f.rig.calls) == 1  # canonical validation never refetches the source


@pytest.mark.parametrize("mutation", ["missing", "foreign_job", "foreign_specimen", "generation_bool", "extra_key"])
def test_actual_capture_scope_refuses_unproved_retained_effect_identity(tmp_path, mutation):
    f, writer, items, accepted = receipt_binding_case(tmp_path)
    binding = f.binding.model_copy(deep=True)
    effect = binding.registration.read_bundle["effects"][items[0].proof.receipt.effect_id]
    if mutation == "missing":
        del effect["scope"]
    elif mutation == "foreign_job":
        effect["scope"]["job_id"] = "foreign-job"
    elif mutation == "foreign_specimen":
        effect["scope"]["specimen_id"] = "10000000-0000-0000-0000-000000000099"
    elif mutation == "generation_bool":
        effect["scope"]["generation"] = True
    else:
        effect["scope"]["unproved_alias"] = 1
    with pytest.raises(PublicationUnavailable, match="effect_scope_unproved"):
        writer._verify_capture_bindings_v2(f.prepared, binding, f.prior, items, accepted)
    assert len(f.rig.calls) == 1


def test_actual_capture_rejects_foreign_accepted_tool_receipt_scope(tmp_path):
    f, writer, items, accepted = receipt_binding_case(tmp_path)
    native_scope = f.rig.request.scope
    changed_tool = f.result.receipt.model_copy(update={"scope": native_scope.model_copy(update={"job_id": "foreign-job"})})
    source = f.result.model_copy(deep=True, update={"receipt": changed_tool})
    accepted[str(f.checkpoint.field_key)].acceptance.source_results = (source,)
    with pytest.raises(PublicationUnavailable, match="tool_receipt_unproved"):
        writer._verify_capture_bindings_v2(f.prepared, f.binding, f.prior, items, accepted)
    assert len(f.rig.calls) == 1
