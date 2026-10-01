"""Actual FunctionModel/Harness journal acceptance closure, never live providers."""
import asyncio
from dataclasses import asdict

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from specimen_digitization.application.domain import FieldValue
from specimen_digitization.research_harness.accepted_output import read_accepted_checkpoint_proof
from specimen_digitization.research_harness.agents import SpecialistOutput, specialist_output_schema_digest
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, ROLE_FIELDS, CollectionProfile, FieldProfile, FieldResolution,
    ResearchScope, SpecialistRequest, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.gateway import ModelBinding
from specimen_digitization.research_harness.persistence import (
    BudgetPolicy, DurabilityScope, ImmutableFileBlobs, ResearchStore, SqliteStateBackend, StaleWork,
)
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.runtime import build_research_engine, runtime_pins
from specimen_digitization.research_harness.sources import SourceBroker, insects_registry


def actual_runtime(tmp_path):
    registry = insects_registry()
    profile = CollectionProfile(id="insects", version="test-v1", organization_id="org-test",
        collection_id="collection-test", ancestry=("org-test", "collection-test"),
        fields=tuple(FieldProfile(field_key=key) for key in ALL_FIELDS), knowledge_version="test-v1")
    scope = ResearchScope(organization_id="org-test", collection_id="collection-test",
        specimen_id="specimen-test", job_id="opaque-test-job", generation=1,
        input_digest="a"*64, profile_digest=digest(profile), sensitive=False)
    role = SpecialistRole.COLLECTION
    request = SpecialistRequest(scope=scope, role=role, field_keys=ROLE_FIELDS[role],
        prompt=resolve_prompt(role, profile_digest=scope.profile_digest,
            source_registry_digest=registry.digest, toolset_digest="b"*64,
            model_route="harness-deepseek", output_schema_digest=specialist_output_schema_digest()))
    bindings = {role:ModelBinding("harness-deepseek", "deepseek-ai/DeepSeek-V4.1-Flash",
        "deepinfra", 128, 10, "offline-test-v1")}
    settings = {"max_tokens":128}
    requests = {role:request}
    pins = runtime_pins(profile, requests,
        model={r:{"route":b.route_id, **asdict(b)} for r,b in bindings.items()}, settings=settings)
    durable = DurabilityScope(scope.organization_id,scope.collection_id,scope.specimen_id,
        scope.job_id,scope.generation,"test-operator",False)
    backend = SqliteStateBackend(tmp_path/"research.sqlite")
    backend.grant(durable)
    store = ResearchStore(backend,"existing-test-program")
    store.initialize(durable,BudgetPolicy(1000))
    store.create_job(durable,pins,list(ALL_FIELDS))
    lease = store.claim(durable,"test-worker",ttl_seconds=120)
    blobs = ImmutableFileBlobs(tmp_path/"blobs")
    def respond(messages, info):
        output = SpecialistOutput(role=role,resolutions=tuple(FieldResolution(field_key=key,
            work_state=WorkState.WAITING_POLICY if str(key)=="verbatim_dts" else WorkState.WAITING_SOURCE,
            value=FieldValue(),reason="source_qualification_required")
            for key in request.field_keys))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
            output.model_dump(mode="json"),tool_call_id="accepted-output")],
            usage=RequestUsage(input_tokens=1,output_tokens=1))
    engine = build_research_engine(profile=profile,requests=requests,store=store,scope=durable,
        lease=lease,blobs=blobs,tool_broker=SourceBroker(registry),bindings=bindings,
        settings=settings,base_model_factory=lambda request:FunctionModel(respond),actual_cost=lambda response:1)
    return engine,store,durable,blobs


def test_actual_native_run_acceptance_is_atomic_with_all_checkpoints(tmp_path):
    engine,store,scope,blobs = actual_runtime(tmp_path)
    result = asyncio.run(engine.run())
    assert len(result.checkpoints) == len(ROLE_FIELDS[SpecialistRole.COLLECTION])
    state = store._read(scope).state
    native = state["jobs"][scope.key]["checkpoints"]
    proofs = [read_accepted_checkpoint_proof(store,scope,blobs,cp["id"]) for cp in native]
    assert len({proof.proof_digest for proof in proofs}) == 1
    proof = proofs[0]
    assert proof.checkpoints == result.checkpoints
    run = state["journal"][proof.acceptance.native_run_id]
    retained = run["accepted_outputs"][proof.proof_digest]
    by_field = {cp["field_key"]:cp for cp in native}
    assert retained["checkpoint_ids"] == [by_field[str(cp.field_key)]["id"] for cp in proof.checkpoints]
    assert set(retained["checkpoint_ids"]) == {cp["id"] for cp in native}
    assert proof.acceptance.effect_ids == result.checkpoints[0].effect_receipt_ids
    assert proof.acceptance.original_request.field_revisions == {
        key:0 for key in ROLE_FIELDS[SpecialistRole.COLLECTION]}
    assert asyncio.run(engine.run()).checkpoints == result.checkpoints


def test_unlinked_or_changed_native_acceptance_is_not_authority(tmp_path):
    engine,store,scope,blobs = actual_runtime(tmp_path)
    asyncio.run(engine.run())
    document = store._read(scope)
    job = document.state["jobs"][scope.key]
    cp = job["checkpoints"][0]
    proof = cp["accepted_output_proof"]
    document.state["journal"][proof["native_run_id"]]["accepted_outputs"].clear()
    store.backend.cas(scope,store.program_key,document.revision,document.state)
    with pytest.raises(StaleWork,match="retained_native_binding_invalid"):
        read_accepted_checkpoint_proof(store,scope,blobs,cp["id"])


def test_unknown_checkpoint_has_no_immutable_blob_authority(tmp_path):
    engine,store,scope,blobs = actual_runtime(tmp_path)
    asyncio.run(engine.run())
    with pytest.raises(StaleWork,match="checkpoint_unavailable"):
        read_accepted_checkpoint_proof(store,scope,blobs,"f"*64)


def test_oversize_proof_refuses_before_any_blob_body_read(tmp_path):
    from specimen_digitization.research_harness.accepted_output import MAX_ACCEPTED_PROOF_BYTES
    engine,store,scope,blobs = actual_runtime(tmp_path)
    asyncio.run(engine.run())
    document = store._read(scope)
    native = document.state["jobs"][scope.key]["checkpoints"][0]
    binding = native["accepted_output_proof"]
    binding["capture"]["byte_size"] = MAX_ACCEPTED_PROOF_BYTES + 1
    retained = document.state["journal"][binding["native_run_id"]]["accepted_outputs"][binding["proof_digest"]]
    retained["proof"] = dict(binding)
    store.backend.cas(scope,store.program_key,document.revision,document.state)
    class NoBodyRead:
        def get(self, ref):
            pytest.fail("An oversized declaration must refuse before body allocation")
    with pytest.raises(StaleWork,match="capture_bound_invalid"):
        read_accepted_checkpoint_proof(store,scope,NoBodyRead(),native["id"])


def test_changed_registered_acceptance_boundary_is_not_historical_authority(tmp_path):
    engine,store,scope,blobs = actual_runtime(tmp_path)
    asyncio.run(engine.run())
    document = store._read(scope)
    job = document.state["jobs"][scope.key]
    job["pins"]["sources"]["acceptance_boundary"] = {"contract_version":"foreign-boundary"}
    store.backend.cas(scope,store.program_key,document.revision,document.state)
    with pytest.raises(StaleWork,match="source_boundary_unqualified"):
        read_accepted_checkpoint_proof(store,scope,blobs,job["checkpoints"][0]["id"])
