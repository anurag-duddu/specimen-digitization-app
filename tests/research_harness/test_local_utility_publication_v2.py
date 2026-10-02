"""Actual deterministic broker/acceptance/producer controls; synthetic native CAS.

No model, remote source, native transaction, price or live admission is claimed.
The broker results and acceptance/checkpoint validators are the real code.
"""
import asyncio
import copy
import hashlib
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest

from test_canonical_materialization import materialization, native_basis
from test_canonical_materialization_v2 import v2_case, SyntheticPrivateContextSource
from test_canonical_projection_v2 import retain_checkpoint, native_snapshot_proof
from test_native_canonical_contract import ident
from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.application.storage import digest as graph_digest
from specimen_digitization.research_harness.accepted_output import (
    AcceptedOutputProofV1, AcceptedCheckpointProofV1, validation_boundary_pins)
from specimen_digitization.research_harness.canonical_evidence_provider_v2 import CanonicalEvidenceProviderV2
from specimen_digitization.research_harness.canonical_materialization_v2 import MaterializationRequestV2
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.contracts import (
    EventHypothesis, EventKind, EvidenceItem, FieldCheckpoint, FieldKey, FieldResolution,
    SourceFragment, SpecialistRequest, SpecialistRole, WorkState, digest)
from specimen_digitization.research_harness.evidence import assemble_field, catalog_literal
from specimen_digitization.research_harness.native_canonical import CapturedCanonicalEvidenceV1
from specimen_digitization.research_harness.publication import PreparedNativePublication
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.sources import SourceBroker, SourceRegistry


def utility_request(b, tool_id="catalog_number", text="FMNH INS 105526321"):
    role, key = {"catalog_number":(SpecialistRole.COLLECTION,FieldKey.FMNH_INS_NUMBER),
        "parse_measurement":(SpecialistRole.MEASUREMENT,FieldKey.ELEVATION_FROM_FT),
        "parse_temporal":(SpecialistRole.TEMPORAL,FieldKey.DATE_VISITED_FROM)}[tool_id]
    scope = b.prepared.basis.scope
    evidence = EvidenceItem(id=ident("utility-evidence"),kind="literal",source_id="native_fixture",
        locator="fixture://label",response_digest=digest("fixture body"),source_version="fixture-v1",
        publisher_assertion_id="fixture-only",excerpt=text)
    fragments = tuple(SourceFragment(id="utility:"+o.id,scope=scope,asset_id=b.prior.asset.id,
        asset_generation="1",asset_digest=o.input_sha256,label_id=o.region_id,region_id=o.region_id,
        observation_id=o.id,reader=o.route_id,model_id=o.model_id,prompt_digest=digest("reader"),
        observation_text=text,observation_digest=hashlib.sha256(text.encode()).hexdigest(),
        start=0,end=len(text),literal=text,order=i) for i,o in enumerate(b.prior.run.observations))
    event = EventHypothesis(id="utility-event",scope=scope,kind=EventKind.COLLECTING,
        fragment_ids=tuple(f.id for f in fragments),evidence_ids=(evidence.id,),reason="Explicit synthetic label context",
        status="accepted",validator_version="fixture-qualified-event-v1")
    assemblies = tuple(assemble_field(assembly_id="utility-assembly:"+f.id,scope=scope,field_key=key,
        fragments=(f,),event=event,assertion_kind="complete") for f in fragments)
    prompt = resolve_prompt(role,profile_digest=scope.profile_digest,
        source_registry_digest=b.checkpoint.source_registry_digest,toolset_digest=digest("utility roster"),
        model_route="harness-deepseek",output_schema_digest=digest("utility schema"))
    return SpecialistRequest(scope=scope,role=role,field_keys=(key,),prompt=prompt,fragments=fragments,
        events=(event,),assemblies=assemblies,evidence=(evidence,),field_revisions={key:0})


def invoke(request, tool_id):
    return asyncio.run(SourceBroker(SourceRegistry(())).invoke_utility(request,tool_id,
        {"text":request.assemblies[0].interpreted_text,"field_key":str(request.field_keys[0])}))


def catalog_case(materialization):
    b=v2_case(materialization)
    request=utility_request(b);result=invoke(request,"catalog_number");key=request.field_keys[0]
    text=request.assemblies[0].interpreted_text
    prior=b.prior.model_copy(deep=True)
    for o in prior.run.observations:o.literal_text=text
    for t in prior.run.transcripts:t.text=text
    native=next(e for e in prior.run.evidence if e.id==ident("i4a-evidence-fmnh_ins_number"))
    native.excerpt=text
    evidence=request.evidence[0]
    resolution=FieldResolution(field_key=key,work_state=WorkState.RESOLVED,value_layer="settled",
        value=FieldValue(state=ValueState.SUPPORTED,literal=None,parsed=catalog_literal(text),
            verbatim_by_observation={o.id:text for o in prior.run.observations},
            input_source_by_observation={o.id:"raw_reading" for o in prior.run.observations},
            settled_observation_ids=[o.id for o in prior.run.observations],input_source="raw_reading",
            source_region_id=prior.run.regions[0].id,evidence_ids=[evidence.id],
            evidence_relations={evidence.id:"supports"},reason="Exact catalog parser from complete literal assemblies"),
        event_id=request.events[0].id,assembly_ids=tuple(a.id for a in request.assemblies),
        evidence_ids=(evidence.id,),reason="Deterministic catalog literal")
    checkpoint=FieldCheckpoint(scope=request.scope,field_key=key,revision=1,resolution=resolution,
        prompt_digest=request.prompt.digest,model_settings_digest=digest("utility settings"),
        source_registry_digest=request.prompt.source_registry_digest,effect_receipt_ids=())
    accepted=AcceptedCheckpointProofV1(acceptance=AcceptedOutputProofV1(original_request=request,
        native_run_id=ident("utility native run"),conversation_id="actual-local-fixture-conversation",
        resolutions=(resolution,),source_results=(result,),effect_ids=(),
        model_settings_digest=checkpoint.model_settings_digest,**validation_boundary_pins()),checkpoints=(checkpoint,))
    context=b.source.context.lineage_context
    job=copy.deepcopy(context.job);job["checkpoints"]=[]
    for row in job["fields"].values():row.update(work_state="pending",checkpoint=None,revision=0)
    native_cp=retain_checkpoint(job,checkpoint);job["fields"][str(key)]["work_state"]="resolved"
    snapshot=native_snapshot_proof(prior,b.binding.canonical.record_version_id)
    context=replace(context,job=job,prior_snapshot_sha256=graph_digest(prior.model_dump(mode="json")),
        native_prior_snapshot=snapshot,original_request=request,tool_results=(result,),
        evidence_id_mapping={evidence.id:UUID(native.id)},accepted_checkpoint_proof=accepted)
    registration=b.binding.registration.model_copy(deep=True)
    registration.read_bundle["job"]=job
    registration=registration.model_copy(update={"job":job,"current_canonical":snapshot.canonical,"base_canonical":snapshot.canonical})
    binding=b.binding.model_copy(update={"registration":registration,"canonical":snapshot.canonical})
    raw=b.prepared.model_dump(mode="json");raw["publication"]["checkpoints"]=[checkpoint.model_dump(mode="json")]
    raw["publication"]["guard"].update(checkpoint_revisions={str(key):1},checkpoint_digests={str(key):digest(checkpoint)},receipt_ids=[])
    raw["basis"].update(field_key=str(key),checkpoint_id=native_cp["id"],checkpoint_digest=digest(native_cp),
        checkpoint_outbox_key="checkpoint/"+native_cp["id"],typed_checkpoint_digest=digest(checkpoint),
        original_typed_checkpoint_digest=digest(checkpoint),receipts=[])
    prepared=PreparedNativePublication.model_validate(raw)
    materialization_context=MaterializationRequestV2(digest(prepared),binding.canonical.snapshot_sha256,
        request,(result,),context)
    b.producer.request_source=SyntheticPrivateContextSource(materialization_context)
    contribution=CapturedCanonicalEvidenceV1(origin="existing_canonical",evidence=evidence,canonical_evidence=native,
        canonical_producer=None,receipt=None,source_policy_digest=digest("existing literal proof"),
        source_registry_digest=checkpoint.source_registry_digest,canonical_mapping_digest=registration.semantic_mapping_digest,
        canonical_run_id=prior.run.id,canonical_region_id=native.region_id,
        canonical_observation_ids=tuple(UUID(x) for x in native.observation_ids))
    return SimpleNamespace(**{**vars(b),"request":request,"utility":result,"accepted":accepted,
        "checkpoint":checkpoint,"prior":prior,"binding":binding,"prepared":prepared,"evidence":(contribution,)})


def test_actual_catalog_utility_acceptance_reaches_materialization_without_external_effect(materialization):
    b=catalog_case(materialization)
    proof=asyncio.run(b.producer.materialize(b.principal,b.prepared,b.binding,b.prior,
        prior_projection=b.rows,captured_evidence=b.evidence,projection_services=b.services))
    assert proof.result.run.fields["fmnh_ins_number"].parsed=="105526321"
    assert proof.progress_receipt.wire_status=="running" and not proof.progress_receipt.exportable
    assert b.producer.request_source.context.tool_results==(b.utility,)
    assert b.utility.receipt is None and b.checkpoint.effect_receipt_ids==()
    assert proof.policy_receipt["local_utility_replays"][0]["arguments"]=={
        "text":"FMNH INS 105526321","field_key":"fmnh_ins_number"}


def test_actual_catalog_utility_acceptance_reaches_provider_without_source_capture(materialization):
    b=catalog_case(materialization)
    provider=object.__new__(CanonicalEvidenceProviderV2)
    provider._authority=lambda *args:b.request.scope
    # Pure provider context call: no IO/effects needed for this local-only result.
    binding=b.binding.model_copy(deep=True);binding.registration.read_bundle["effects"]={}
    original=SimpleNamespace(request=b.request,tool_results=(b.utility,),accepted_checkpoint_proof=b.accepted)
    request,captured=asyncio.run(provider._contexts(b.principal,b.prepared,binding,accepted_original=original))
    assert request==b.request and captured==[]
    assert original.tool_results==(b.utility,) and original.tool_results[0].receipt is None


@pytest.mark.parametrize("tool,text",[("parse_measurement","-10 ft"),("parse_temporal","2020-01-02"),("catalog_number","FMNH INS 105526321")])
def test_exact_actual_local_parser_replay_retains_result_and_inputs(materialization,tool,text):
    from specimen_digitization.research_harness.local_utility_proof_v2 import verify_local_utility_v2
    b=v2_case(materialization);request=utility_request(b,tool,text);result=invoke(request,tool)
    before=request.model_dump(mode="json"),result.model_dump(mode="json")
    replay=verify_local_utility_v2(request,result)
    assert replay.original_request_digest==digest(request) and replay.result_digest==digest(result)
    assert replay.text==text and replay.tool_id==tool
    assert before==(request.model_dump(mode="json"),result.model_dump(mode="json"))
    assert result.receipt is None and not result.evidence


@pytest.mark.parametrize("mutation",["candidate","unbound_text","version","scope_field","unknown_utility","extra_qualification","no_assemblies"])
def test_receiptless_result_tamper_or_unavailable_local_provenance_holds(materialization,mutation):
    from specimen_digitization.research_harness.local_utility_proof_v2 import verify_local_utility_v2
    b=v2_case(materialization);request=utility_request(b);result=invoke(request,"catalog_number")
    if mutation=="candidate":result=result.model_copy(update={"candidate_json":('{"field_key":"fmnh_ins_number","value":"105526322","rule_version":"catalog-number-v1"}',)})
    elif mutation=="unbound_text":request=request.model_copy(update={"assemblies":tuple(a.model_copy(update={"interpreted_text":"FMNH INS 105526322"}) for a in request.assemblies)})
    elif mutation=="version":result=result.model_copy(update={"coverage":result.coverage.model_copy(update={"source_version":"unknown-v2"})})
    elif mutation=="scope_field":result=result.model_copy(update={"coverage":result.coverage.model_copy(update={"field_key":FieldKey.COLLECTION_CODE})})
    elif mutation=="unknown_utility":result=result.model_copy(update={"coverage":result.coverage.model_copy(update={"source_id":"unknown_local"})})
    elif mutation=="extra_qualification":result=result.model_copy(update={"coverage":result.coverage.model_copy(update={"qualification_digest":digest("fabricated remote qualification")})})
    else:request=request.model_copy(update={"assemblies":()})
    with pytest.raises(PublicationUnavailable,match="local_utility_unproved"):
        verify_local_utility_v2(request,result)


def test_local_result_cannot_publish_without_true_accepted_checkpoint_proof(materialization):
    b=catalog_case(materialization)
    context=b.producer.request_source.context
    b.producer.request_source.context=replace(context,lineage_context=replace(context.lineage_context,accepted_checkpoint_proof=None))
    with pytest.raises(PublicationUnavailable,match="local_utility_acceptance_unproved"):
        asyncio.run(b.producer.materialize(b.principal,b.prepared,b.binding,b.prior,
            prior_projection=b.rows,captured_evidence=b.evidence,projection_services=b.services))
