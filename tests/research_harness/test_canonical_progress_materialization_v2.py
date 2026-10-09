"""Offline progress policy controls; no database or scientific publication claim."""
import asyncio
import copy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from test_native_canonical_contract import basis as native_basis, ident
from test_native_canonical_v2_contract import native_checkpoint
from specimen_digitization.application.domain import Disposition, FieldValue
from specimen_digitization.application.storage import digest as canonical_digest
from specimen_digitization.research_harness import canonical_progress_materialization_v2 as module
from specimen_digitization.research_harness.canonical_materialization_v2 import ResearchCanonicalPolicyV2
from specimen_digitization.research_harness.canonical_projection_v2 import NativePriorSnapshotProofV2
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, ROLE_FIELDS, FieldCheckpoint, FieldResolution, WorkState, digest,
)
from specimen_digitization.research_harness.native_canonical_v2 import CanonicalBindingV2
from specimen_digitization.research_harness.progress_publication_v2 import (
    PreparedNativeProgressV2, ProgressBasisV2, ProgressPublicationV2,
)
from specimen_digitization.research_harness.persistence import Lease


@pytest.fixture
def progress_case(native_basis):
    b = native_basis
    reg = b.binding.registration.model_copy(deep=True)
    pins = reg.job["pins"]
    pins.update(settings={"test_only":"offline"}, sources={"registry_digest":digest("offline registry")},
        prompts={str(role):{"digest":digest(["offline prompt", str(role)])} for role in ROLE_FIELDS})
    reg.job["binding_digest"] = digest(pins)
    reg.job["checkpoints"] = []
    for key in ALL_FIELDS:
        role = next(role for role, fields in ROLE_FIELDS.items() if key in fields)
        cp = FieldCheckpoint(scope=b.scope, field_key=key, revision=1,
            resolution=FieldResolution(field_key=key, work_state=WorkState.WAITING_POLICY,
                value=FieldValue(), reason="offline policy unavailable"),
            prompt_digest=pins["prompts"][str(role)]["digest"], model_settings_digest=digest(pins["settings"]),
            source_registry_digest=pins["sources"]["registry_digest"])
        native = native_checkpoint(cp)
        native["binding_digest"] = digest(pins)
        reg.job["fields"][str(key)].update(checkpoint=native, work_state="waiting_policy", reuse=None)
        reg.job["checkpoints"].append(native)
    policy = ResearchCanonicalPolicyV2(canonical_profile_digest=reg.canonical_profile_digest,
        research_profile_digest=reg.profile_digest, source_registry_digest=pins["sources"]["registry_digest"])
    semantic = copy.deepcopy(reg.semantic_mapping)
    semantic["research_policy_contract_version"] = policy.contract_version
    reg = reg.model_copy(update={"runtime_binding_digest":digest(pins), "policy_digest":digest(policy),
        "semantic_mapping":semantic, "semantic_mapping_digest":digest(semantic)})
    reg.read_bundle["job"] = reg.job
    raw = {key:value for key, value in b.binding.model_dump(mode="json").items() if key != "contract_version"}
    raw["registration"] = reg.model_dump(mode="json")
    binding = CanonicalBindingV2(**raw, authority_digest=digest("offline authority"),
        import_proof_id=ident("offline import"), import_proof_digest=digest("offline import"),
        head_receipt_id=None, head_chain_digest=digest("offline genesis"), causal_chain=())
    return SimpleNamespace(principal=b.principal, prior=b.prior, scope=b.scope, binding=binding,
        rows=b.raw["projection"], policy=policy,
        native_prior=NativePriorSnapshotProofV2(binding.canonical, b.prior.model_dump(mode="json")))


def prepared(case):
    reg = case.binding.registration
    guard = {"operation_kind":"progress_only", "offline":"not native custody"}
    return PreparedNativeProgressV2(basis=ProgressBasisV2(scope=case.scope, actor_uid=case.principal.user_id,
        job_key=reg.job_key, program_key=reg.program_key, binding_digest=reg.runtime_binding_digest,
        pins_digest=digest(reg.job["pins"]), field_work_digest=digest(reg.job["fields"]),
        field_mapping_digest=digest(reg.field_mapping), policy_digest=reg.policy_digest,
        human_locks=reg.human_locks, expected_record_revision=case.prior.version,
        lease=Lease(reg.job_key,"offline",1,case.scope.generation,2000000030.0),
        state_revision=7, state_digest=digest("offline state"), publication_outbox_key="publish/offline",
        native_guard_digest=digest(guard)),
        publication=ProgressPublicationV2(scope=case.scope, field_work_digest=digest(reg.job["fields"]),
            field_mapping_digest=digest(reg.field_mapping), canonical_anchor=case.binding.canonical), guard=guard)


def produce(case, **kwargs):
    return asyncio.run(module.CanonicalProgressMaterializerV2(case.policy).materialize_progress_v2(
        case.principal, prepared(case), case.binding, case.prior, terminal_contexts=(),
        prior_projection=case.rows, native_prior_snapshot=case.native_prior, **kwargs))


def test_blocked_progress_preserves_science_provenance_and_history(progress_case):
    b = progress_case
    before = b.prior.model_dump(mode="json")
    job = copy.deepcopy(b.binding.registration.job)
    result = produce(b)
    assert result.result.version == b.prior.version + 1
    assert result.result.run.stage == "processing_blocked" and result.result.run.disposition is None
    assert result.progress_receipt.exportable is False
    assert "mandatory_unresolved:verbatim_dts" in result.progress_receipt.human_reason_codes
    assert "research_work:country:waiting_policy" in result.progress_receipt.operational_reason_codes
    after = result.result.model_dump(mode="json")
    for key in ("stage","disposition","reasons"):
        after["run"][key] = before["run"][key]
    after["version"] = before["version"]
    assert after == before
    assert b.prior.model_dump(mode="json") == before and b.binding.registration.job == job
    assert result.evidence_id_mapping == {} and not any("target" in key for key in result.progress_receipt.model_dump())


@pytest.mark.parametrize("mutation", ["state", "checkpoint_id", "duplicate_checkpoint", "missing_field", "boolean_state",
    "unproved_lock", "wrong_registry", "wrong_prompt", "wrong_settings", "missing_checkpoint", "wrong_dependency", "wrong_input_scope", "wrong_profile_scope"])
def test_whole20_native_checkpoint_drift_refuses_before_policy(progress_case, mutation):
    b = progress_case
    reg = b.binding.registration
    row = reg.job["fields"]["country"]
    if mutation == "state": row["work_state"] = "waiting_source"
    elif mutation == "checkpoint_id": row["checkpoint"]["id"] = digest("changed")
    elif mutation == "duplicate_checkpoint": reg.job["checkpoints"].append(copy.deepcopy(row["checkpoint"]))
    elif mutation == "missing_field": reg.job["fields"].pop("county")
    elif mutation == "boolean_state": row["work_state"] = True
    elif mutation == "unproved_lock": row["locked"] = True
    elif mutation == "missing_checkpoint": row["checkpoint"] = None
    elif mutation == "wrong_dependency":
        row["checkpoint"]["dependency_digests"] = {"county":digest("changed")}
    elif mutation in {"wrong_input_scope", "wrong_profile_scope"}:
        cp = FieldCheckpoint.model_validate(row["checkpoint"]["payload"])
        attr = "input_digest" if mutation == "wrong_input_scope" else "profile_digest"
        cp = cp.model_copy(update={"scope":cp.scope.model_copy(update={attr:digest("foreign scope")})})
        native = native_checkpoint(cp)
        native["binding_digest"] = reg.runtime_binding_digest
        reg.job["checkpoints"].remove(row["checkpoint"])
        reg.job["checkpoints"].append(native)
        row["checkpoint"] = native
    else:
        attr = {"wrong_registry":"source_registry_digest", "wrong_prompt":"prompt_digest", "wrong_settings":"model_settings_digest"}[mutation]
        cp = FieldCheckpoint.model_validate(row["checkpoint"]["payload"]).model_copy(update={attr:digest("changed")})
        native = native_checkpoint(cp)
        native["binding_digest"] = reg.runtime_binding_digest
        reg.job["checkpoints"].remove(row["checkpoint"])
        reg.job["checkpoints"].append(native)
        row["checkpoint"] = native
    before = b.prior.model_dump(mode="json")
    with pytest.raises((PublicationUnavailable, ValueError)):
        produce(b)
    assert b.prior.model_dump(mode="json") == before


@pytest.mark.parametrize("state", ["pending", "researching", "retry_scheduled"])
def test_progress_only_cannot_consume_runnable_work(progress_case, state):
    row = progress_case.binding.registration.job["fields"]["country"]
    if state in {"pending","researching"}:
        row.update(checkpoint=None, work_state=state)
    else:
        cp = FieldCheckpoint.model_validate(row["checkpoint"]["payload"])
        cp = cp.model_copy(update={"resolution":cp.resolution.model_copy(update={"work_state":WorkState.RETRY_SCHEDULED})})
        native = native_checkpoint(cp)
        native["binding_digest"] = progress_case.binding.registration.runtime_binding_digest
        progress_case.binding.registration.job["checkpoints"].remove(row["checkpoint"])
        progress_case.binding.registration.job["checkpoints"].append(native)
        row.update(checkpoint=native, work_state=state)
    with pytest.raises(PublicationUnavailable, match="canonical_progress_runnable_work_remaining"):
        produce(progress_case)


@pytest.mark.parametrize("attr", ["human_approved","history_restore_human_locks"])
def test_global_human_decision_is_not_reopened(progress_case, attr):
    setattr(progress_case.prior.run, attr, True)
    with pytest.raises(PublicationUnavailable, match="canonical_progress_global_human_decision_locked"):
        produce(progress_case)


def test_declared_missing_dts_completes_honestly_with_review(progress_case, monkeypatch):
    # Routing-only control: separate native/accepted scientific qualification is
    # exercised by the real composed worker cases, not asserted by this seam.
    b = progress_case
    for key, row in b.binding.registration.job["fields"].items():
        if key == "verbatim_dts":
            continue
        cp = FieldCheckpoint.model_validate(row["checkpoint"]["payload"])
        value = FieldValue(state="supported", literal="offline fixture", evidence_ids=["offline"])
        cp = cp.model_copy(update={"resolution":FieldResolution(field_key=cp.field_key,
            work_state="resolved", value=value, evidence_ids=("offline",), reason="offline routing fixture")})
        native = native_checkpoint(cp)
        native["binding_digest"] = b.binding.registration.runtime_binding_digest
        b.binding.registration.job["checkpoints"].remove(row["checkpoint"])
        b.binding.registration.job["checkpoints"].append(native)
        row.update(checkpoint=native, work_state="resolved")
    monkeypatch.setattr(module, "_qualified_fields", lambda *args:frozenset(module.KEYS - {"verbatim_dts"}))
    monkeypatch.setattr(module, "_scientific_reasons", lambda *args, **kwargs:[])
    monkeypatch.setattr(module, "_relations_unproved", lambda *args:frozenset())
    result = produce(b)
    assert result.result.run.stage == "finalized" and result.result.run.disposition == Disposition.REVIEW
    assert result.progress_receipt.wire_status == "completed" and result.progress_receipt.exportable is False
    assert result.progress_receipt.human_reason_codes == ("mandatory_unresolved:verbatim_dts",)
    assert result.result.run.fields == b.prior.run.fields


def test_snapshot_proof_is_required_even_with_no_published_context(progress_case):
    b = progress_case
    b.native_prior = replace(b.native_prior, snapshot={**b.native_prior.snapshot,"version":2})
    with pytest.raises(PublicationUnavailable, match="canonical_lineage_native_snapshot_unproved"):
        produce(b)


def reused_case(case):
    reg = case.binding.registration
    job, original_scope = reg.job, case.scope
    original_identity = {key:getattr(original_scope,key) for key in (
        "organization_id","collection_id","specimen_id","job_id","generation")}
    history = {"scope":original_identity, "binding_digest":job["binding_digest"],
        "pins":copy.deepcopy(job["pins"]), "fields":copy.deepcopy(job["fields"])}
    scope = original_scope.model_copy(update={"generation":2,"input_digest":digest("corrected offline input")})
    job["history"] = [history]
    job["generation"] = 2
    job["pins"]["input_digest"] = scope.input_digest
    job["binding_digest"] = digest(job["pins"])
    current_identity = {key:getattr(scope,key) for key in original_identity}
    for row in job["fields"].values():
        checkpoint = row["checkpoint"]
        row["reuse"] = {"reused_from_scope_digest":digest(original_identity), "checkpoint_digest":digest(checkpoint),
            "into_scope_digest":digest(current_identity), "source_binding_digest":checkpoint["binding_digest"],
            "target_binding_digest":job["binding_digest"], "retained_dependencies":checkpoint["dependencies"],
            "retained_dependency_digests":checkpoint["dependency_digests"]}
    return reg, scope


def test_actual_prior_generation_reuse_requires_immutable_same_job_history(progress_case):
    reg, scope = reused_case(progress_case)
    before = copy.deepcopy(reg.job)
    research, canonical = module._current_work(reg, scope, progress_case.principal.user_id, {})
    assert len(research) == len(canonical) == 20 and set(research.values()) == {"waiting_policy"}
    assert reg.job == before
    reg.job["fields"]["country"]["reuse"] = None
    with pytest.raises(PublicationUnavailable, match="canonical_progress_checkpoint_state_unproved"):
        module._current_work(reg, scope, progress_case.principal.user_id, {})


from test_canonical_materialization import materialization
from test_canonical_projection_v2 import native_snapshot_proof, settled_case
from specimen_digitization.research_harness.canonical_materialization_v2 import TerminalFieldProofV2


def qualified_case(materialization):
    b = settled_case(materialization)
    prior = b.result.model_copy(deep=True)
    native = native_snapshot_proof(prior, b.context.prior_record_version_id)
    context = replace(b.context, prior_revision=prior.version,
        prior_snapshot_sha256=canonical_digest(prior.model_dump(mode="json")), native_prior_snapshot=native)
    context.job["fields"]["country"]["work_state"] = "resolved"
    binding = SimpleNamespace(canonical=native.canonical, registration=SimpleNamespace(job=context.job,
        field_mapping=context.field_mapping, human_locks=context.human_locks))
    return SimpleNamespace(principal=b.principal, prior=prior, binding=binding, scope=b.checkpoint.scope,
        proof=TerminalFieldProofV2(b.checkpoint,context), projection=context.prior_projection,
        canonical={key:"resolved" for key in module.KEYS})


def test_published_science_is_independently_grounded_without_a_selected_target(materialization):
    b = qualified_case(materialization)
    before = b.prior.model_dump(mode="json")
    qualified = module._qualified_fields(b.principal,b.prior,b.binding,b.scope,(b.proof,),b.canonical,b.projection)
    assert qualified == frozenset({"country"}) and b.prior.model_dump(mode="json") == before


@pytest.mark.parametrize("mutation", ["duplicate", "changed_value", "foreign_actor", "stale_job", "wrong_projection"])
def test_terminal_count_does_not_replace_actual_published_value_and_context(materialization, mutation):
    b = qualified_case(materialization)
    proofs = (b.proof,)
    if mutation == "duplicate": proofs = (b.proof,b.proof)
    elif mutation == "changed_value": b.prior.run.fields["country"].normalized = "Invented different place"
    else:
        context = b.proof.lineage_context
        if mutation == "foreign_actor": context = replace(context,actor_uid="foreign")
        elif mutation == "stale_job": context = replace(context,job={**context.job,"extra_stale_marker":True})
        else: context = replace(context,prior_projection=())
        proofs = (replace(b.proof,lineage_context=context),)
    with pytest.raises(PublicationUnavailable):
        module._qualified_fields(b.principal,b.prior,b.binding,b.scope,proofs,b.canonical,b.projection)
