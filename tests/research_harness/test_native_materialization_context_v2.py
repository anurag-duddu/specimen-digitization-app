"""Native normalization and call-local history validation; synthetic offline inputs."""
import copy
import hashlib
from types import SimpleNamespace
from uuid import UUID

import pytest

from test_native_canonical_v2_contract import (
    basis_v1, causal, make_intent, make_preparation, native_checkpoint,
    prepared_for, receipt,
)
from test_native_canonical_contract import ident
from test_native_materialization_loader_v2 import native_materialization_response
from specimen_digitization.application.domain import FieldValue
from specimen_digitization.research_harness.accepted_output import (
    AcceptedCheckpointProofV1, AcceptedOutputProofV1, validation_boundary_pins,
)
from specimen_digitization.research_harness.contracts import (
    FieldCheckpoint, FieldKey, FieldResolution, HumanQuestion, SourceCoverageReceipt,
    SourceResult, SpecialistRequest, SpecialistRole, ToolReceipt, digest,
)
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.native_canonical import CANONICAL_KEYS
from specimen_digitization.research_harness.native_materialization_context_v2 import (
    NativeMaterializationInputBundleV2, _normalized_native_row, canonical_prior_projection_v2,
)
from specimen_digitization.research_harness.persistence import StaleWork
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.publication_v2 import NativeCausalReceiptV2, genesis_digest, outbox_completion
from specimen_digitization.research_harness.sources import result_envelope


OUTER = {"organizationId":"native-org", "collectionId":"native-collection"}


def test_native_timestamp_normalization_retains_original_row_and_producer_spelling():
    expected = {**OUTER, "id":"native-row", "capturedAt":"2026-10-01T10:20:30Z", "literalText":"Peru"}
    raw = {**expected, "capturedAt":"2026-10-01T05:20:30.000000-05:00", "createdAt":"2026-10-01T12:00:00Z"}
    before = copy.deepcopy(raw)
    assert _normalized_native_row(raw, expected, OUTER) == expected
    assert raw == before


@pytest.mark.parametrize("changed", [
    {"capturedAt":"2026-10-01T10:20:31Z"},
    {"capturedAt":"2026-10-01T10:20:30"},
    {"capturedAt":True},
    {"organizationId":"foreign-org"},
    {"literalText":"Ecuador"},
    {"unrecognizedScientificColumn":None},
])
def test_native_write_normalization_denies_scientific_scope_or_wire_drift(changed):
    expected = {**OUTER, "id":"native-row", "capturedAt":"2026-10-01T10:20:30Z", "literalText":"Peru"}
    raw = {**expected, **changed, "createdAt":"2026-10-01T12:00:00Z"}
    before = copy.deepcopy(raw)
    with pytest.raises(PublicationUnavailable):
        _normalized_native_row(raw, expected, OUTER)
    assert raw == before


def test_normalization_does_not_treat_arbitrary_scientific_strings_as_timestamps():
    expected = {**OUTER, "id":"native-row", "literalText":"2026-10-01T10:20:30Z"}
    raw = {**expected, "literalText":"2026-10-01T05:20:30-05:00"}
    with pytest.raises(PublicationUnavailable):
        _normalized_native_row(raw, expected, OUTER)


def test_native_full_row_order_and_public_field_order_have_exact_same_scientific_projection():
    public = [{"id":"row:"+field, "recordVersionId":"current-native-record", "candidateId":None,
        "fieldKey":field, "state":"absent", "fieldGroup":"native-group"} for field in sorted(CANONICAL_KEYS)]
    native = [{**OUTER, **row, "createdAt":"2026-10-01T10:20:30Z"} for row in reversed(public)]
    before = copy.deepcopy(native)
    assert canonical_prior_projection_v2(native,"current-native-record") == tuple(public)
    assert canonical_prior_projection_v2(public,"current-native-record") == tuple(public)
    assert native == before


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "unknown_column"])
def test_projection_order_normalization_cannot_erase_duplicate_missing_or_scientific_rows(mutation):
    rows = [{"id":"row:"+field, "recordVersionId":"current-native-record", "candidateId":None,
        "fieldKey":field, "state":"absent", "fieldGroup":"native-group"} for field in sorted(CANONICAL_KEYS)]
    if mutation == "duplicate":
        rows[-1] = copy.deepcopy(rows[0])
    elif mutation == "missing":
        rows.pop()
    else:
        rows[0]["newScientificAuthority"] = "unapproved"
    with pytest.raises(PublicationUnavailable):
        canonical_prior_projection_v2(rows,"current-native-record")


# Exercise the actual synchronous bundle and all receipt/accepted-checkpoint
# validators. These in-memory rows are deliberately synthetic native inputs,
# not a SQL transaction, retained journal capture or publication authority.


def _accepted_field(scope, field):
    key = FieldKey(field)
    prompt = resolve_prompt(SpecialistRole.GEOGRAPHY, profile_digest=scope.profile_digest,
        source_registry_digest=digest("inert fixture registry"), toolset_digest=digest("inert tools"),
        model_route="fixture", output_schema_digest=digest("fixture schema"))
    request = SpecialistRequest(scope=scope, role=SpecialistRole.GEOGRAPHY,
        field_keys=(key,), prompt=prompt, field_revisions={key:0})
    results, effects = (), ()
    resolution = FieldResolution(field_key=key, work_state="waiting_source", value=FieldValue(), reason="Offline fixture")
    if field != "country":
        effect = digest(["offline fixture", field])
        coverage = SourceCoverageReceipt(source_id="offline-fixture", field_key=key,
            state="exhausted", source_version="fixture-v1", qualification_digest=digest("fixture"),
            exact_join_attempted=True, query_digest=digest([field]), receipt_ids=(effect,),
            coverage_limit="Synthetic scoped absence only", reason="fixture_absence")
        result = SourceResult(status="no_match", coverage=coverage)
        body = result_envelope(result)
        tool = ToolReceipt(id=effect, scope=scope, tool_id="offline-fixture", source_id="offline-fixture",
            field_keys=(key,), effect_id=effect, attempt_ids=("fixture-attempt",),
            request_digest=digest(request), binding_digest=digest("fixture"), outcome="no_match",
            effect_status="completed", result_json=body, result_digest=hashlib.sha256(body.encode()).hexdigest())
        results, effects = (result.model_copy(update={"receipt":tool}),), (effect,)
        resolution = FieldResolution(field_key=key, work_state="waiting_human", value=FieldValue(),
            question=HumanQuestion(field_key=key, question="Which place is intended?", reason="scoped_absence",
                coverage=(coverage,)), reason="Synthetic source exhausted")
    checkpoint = FieldCheckpoint(scope=scope, field_key=key, revision=1, resolution=resolution,
        prompt_digest=prompt.digest, model_settings_digest=digest("fixture settings"),
        source_registry_digest=prompt.source_registry_digest, effect_receipt_ids=effects)
    accepted = AcceptedCheckpointProofV1(acceptance=AcceptedOutputProofV1(original_request=request,
        native_run_id=ident("accepted:"+field), conversation_id="offline:"+field, resolutions=(resolution,),
        source_results=results, effect_ids=effects, model_settings_digest=checkpoint.model_settings_digest,
        **validation_boundary_pins()), checkpoints=(checkpoint,))
    return checkpoint, accepted


@pytest.fixture
def bundle_case(causal):
    c = causal
    checkpoints, accepted = {}, {}
    for field in ("country", "county", "city"):
        cp, proof = _accepted_field(c.p.basis.scope, field)
        checkpoints[field], accepted[field] = cp, proof
    # The ordinary prepared target has no effect; the terminal siblings carry
    # their own actual typed accepted source receipts and nullable projections.
    c.b.prepared = c.b.prepared.model_copy(update={"publication":c.b.prepared.publication.model_copy(
        update={"checkpoints":(checkpoints["country"],)})})
    c.p = prepared_for(c.b, "country", c.state, 7, resolution=checkpoints["country"].resolution)
    c.job["checkpoints"] = []
    for field, cp in checkpoints.items():
        native = native_checkpoint(cp)
        proof = accepted[field]
        native["accepted_output_proof"] = {
            "proof_digest":proof.proof_digest, "request_digest":digest(proof.acceptance.original_request),
            "native_run_id":proof.acceptance.native_run_id, "conversation_id":proof.acceptance.conversation_id,
            "checkpoint_payload_digests":[digest(cp)],
        }
        c.job["fields"][field].update(checkpoint=native, revision=cp.revision, work_state=str(cp.resolution.work_state))
        c.job["checkpoints"].append(native)
        c.state["outbox"]["checkpoint/"+native["id"]] = {"delivered":False}
    c.p = c.p.model_copy(update={"basis":c.p.basis.model_copy(update={"state_digest":digest(c.state)})})
    c.intent = make_intent(c.b, c.p)
    c.prep = make_preparation(c.intent, c.p, c.state, 7, c.intent.original_base, None,
        genesis_digest(c.intent.binding_id, c.intent.original_base), 1)
    history = []
    for field in ("county", "city"):
        raw = receipt(c, field=field).model_dump(mode="json")
        raw["checkpoint_outbox_key"] = "checkpoint/"+c.job["fields"][field]["checkpoint"]["id"]
        raw["after_state"] = outbox_completion(raw["before_state"], raw["publication_outbox_key"],
            raw["checkpoint_outbox_key"], raw["native_commit"])
        raw["after_state_digest"] = digest(raw["after_state"])
        history.append(NativeCausalReceiptV2.model_validate(raw).model_dump(mode="json"))
    response = native_materialization_response(c)
    native = response["binding"]["materialization_inputs"]
    native["retained_history"] = history
    native["checkpoint_inputs"]["terminal_siblings"] = [checkpoints[k].model_dump(mode="json") for k in ("county", "city")]
    reg = c.b.binding.registration.model_copy(update={"job":c.job, "read_bundle":native["scoped_state"]})
    return SimpleNamespace(native=native, binding=c.b.binding.model_copy(update={"registration":reg}),
        intent=c.intent, preparation=c.prep, prior=c.b.prior, accepted=accepted)


def _bundle(case):
    return NativeMaterializationInputBundleV2.from_native_inputs(native_inputs=case.native,
        current_binding=case.binding, intent=case.intent, preparation=case.preparation,
        prior=case.prior, accepted_checkpoint_proofs=case.accepted, projection_services=None)


def test_bundle_retains_both_nullable_sibling_proofs_without_mutating_native_inputs(bundle_case):
    case = bundle_case
    before = copy.deepcopy(case.native)
    first, second = _bundle(case), _bundle(case)
    assert first == second
    assert set(first.original_request_proofs) == {"country", "county", "city"}
    assert [str(p.checkpoint.field_key) for p in first.target.field_lineage_contexts] == ["county", "city"]
    assert all(p.lineage_context.consumed_sources == () for p in first.target.field_lineage_contexts)
    assert first.native_inputs_digest == digest(before) and case.native == before


@pytest.mark.parametrize("mutation,reason", [
    ("changed_state", "native_v2_causal_receipt_invalid"),
    ("unmatched_malformed", "native_v2_causal_receipt_invalid"),
    ("duplicate", "canonical_native_sibling_winning_receipt_ambiguous"),
    ("profile", "canonical_native_sibling_winning_receipt_scope_changed"),
    ("runtime_binding", "canonical_native_sibling_winning_receipt_scope_changed"),
    ("program", "canonical_native_sibling_winning_receipt_scope_changed"),
    ("committed_checkpoint", "canonical_native_sibling_winning_receipt_scope_changed"),
])
def test_fresh_bundle_cannot_reuse_previously_valid_history(bundle_case, mutation, reason):
    case = bundle_case
    assert len(_bundle(case).target.field_lineage_contexts) == 2
    raw = case.native["retained_history"][0]
    if mutation == "changed_state":
        raw["after_state"]["halted"] = True
    elif mutation == "unmatched_malformed":
        raw = copy.deepcopy(raw)
        raw["changed_field"] = "collectors"
        case.native["retained_history"].append(raw)
    elif mutation == "duplicate":
        case.native["retained_history"].append(copy.deepcopy(raw))
    elif mutation == "profile":
        raw["profile_digest"] = digest("different profile")
    elif mutation == "runtime_binding":
        raw["runtime_binding_digest"] = digest("different runtime binding")
    elif mutation == "program":
        raw["program_key"] = "different-program"
    else:
        # A structurally valid receipt for a different committed checkpoint
        # still cannot satisfy this sibling's exact native checkpoint proof.
        for state_key in ("before_state", "after_state"):
            raw[state_key]["jobs"][case.intent.job_key]["fields"]["county"]["checkpoint"]["accepted_output_proof"]["conversation_id"] = "other"
            raw[state_key+"_digest"] = digest(raw[state_key])
        raw["progress_receipt"]["field_work_digest"] = digest(raw["before_state"]["jobs"][case.intent.job_key]["fields"])
        raw["progress_receipt_digest"] = digest(raw["progress_receipt"])
        NativeCausalReceiptV2.model_validate(raw)
    with pytest.raises(PublicationUnavailable, match=reason):
        _bundle(case)


@pytest.mark.parametrize("mutation", ["revision", "record", "scope"])
def test_fresh_bundle_revalidates_its_current_snapshot_and_scope(bundle_case, mutation):
    case = bundle_case
    _bundle(case)
    if mutation == "revision":
        case.prior = case.prior.model_copy(update={"version":case.prior.version+1})
    elif mutation == "record":
        case.binding = case.binding.model_copy(update={"canonical":case.binding.canonical.model_copy(
            update={"record_version_id":UUID(ident("another record"))})})
    else:
        scope = case.preparation.prepared.basis.scope.model_copy(update={"collection_id":ident("another collection")})
        case.preparation = case.preparation.model_copy(update={"prepared":case.preparation.prepared.model_copy(
            update={"basis":case.preparation.prepared.basis.model_copy(update={"scope":scope})})})
    with pytest.raises(PublicationUnavailable):
        _bundle(case)


@pytest.mark.parametrize("skip", ["target_only", "unpublished_siblings"])
def test_unused_malformed_history_keeps_the_existing_lazy_validation_boundary(bundle_case, skip):
    case = bundle_case
    case.native["retained_history"] = [{"malformed":"unused history"}]
    if skip == "target_only":
        case.native["checkpoint_inputs"]["terminal_siblings"] = []
    else:
        for row in case.native["projection_rows"]["resolved_fields"]:
            if row["fieldKey"] in {"county", "city"}:
                row["candidateId"] = ident("unpublished:"+row["fieldKey"])
    result = _bundle(case)
    assert set(result.original_request_proofs) == {"country"}
    assert result.target.field_lineage_contexts == ()
    assert result.native_inputs_digest == digest(case.native)


def test_native_checkpoint_failure_still_precedes_malformed_history(bundle_case):
    case = bundle_case
    case.native["retained_history"] = [{"malformed":"must not hide checkpoint refusal"}]
    case.binding.registration.job["fields"]["county"]["revision"] += 1
    with pytest.raises(StaleWork, match="native_publication_checkpoint_revision_changed"):
        _bundle(case)


def test_fresh_empty_history_cannot_inherit_prior_sibling_winners(bundle_case):
    case = bundle_case
    assert len(_bundle(case).target.field_lineage_contexts) == 2
    case.native["retained_history"] = []
    result = _bundle(case)
    assert set(result.original_request_proofs) == {"country"}
    assert result.target.field_lineage_contexts == ()
    assert result.native_inputs_digest == digest(case.native)
