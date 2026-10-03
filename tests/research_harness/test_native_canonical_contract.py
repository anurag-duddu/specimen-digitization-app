"""I2 caller contract source. UNRUN; fake connector is not native SQL proof.

The focused controls retain the actual typed adapter/receipt/materialization
callers. Native compiler, physical tables, races, IAM and full transaction
rollback need separately admitted real connector tests, not these fakes.
"""
import asyncio
import copy
import hashlib
import json
from types import SimpleNamespace
from uuid import UUID, uuid5, NAMESPACE_URL

import pytest

from specimen_digitization.application.domain import Asset, Disposition, FieldValue, Principal, Run, Scope, Specimen
from specimen_digitization.application.production import actor_uid
from specimen_digitization.application.projection import Blob, writes
from specimen_digitization.application.storage import digest as canonical_digest
from specimen_digitization.research_harness import native_canonical as module
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, CollectionProfile, DependencyPin, DerivationRecord, FieldCheckpoint, FieldKey, FieldProfile, FieldResolution,
    ResearchScope, WorkState, digest,
)
from specimen_digitization.research_harness.native_canonical import (
    CanonicalBindingV1, CanonicalIdentityV1, CanonicalPolicyMaterializationV1,
    PublicationUnavailable, SqlConnectCanonicalResearchWriter, scientific_intent,
)
from specimen_digitization.research_harness.publication import PreparedNativePublication


def ident(name):
    return str(uuid5(NAMESPACE_URL, "i2-source-test:" + name))


class FakeConnector:
    """Named operations only; no ordinary save/create, model or source method."""
    graph_blobs = None

    def __init__(self):
        self.calls = []
        self.retained = None
        self.intent = None
        self.intent_write_calls = 0
        self.lose_intent_ack = False
        self.binding = None
        self.denied = False
        self.lose_ack = False
        self.write_calls = 0
        self.on_commit = None

    def execute(self, operation, variables, mutation=False):
        self.calls.append((operation, copy.deepcopy(variables), mutation, actor_uid.get()))
        if self.denied:
            raise PermissionError("access_denied")
        if operation == "GetResearchPublicationReceiptV1":
            return {"retained":copy.deepcopy(self.retained)}
        if operation == "GetResearchPublicationIntentV1":
            return {"intent":copy.deepcopy(self.intent)}
        if operation == "RetainResearchPublicationIntentV1":
            assert mutation
            self.intent_write_calls += 1
            assert self.intent is None  # immutable fake table, no rewrite
            i=json.loads(variables["intentJson"])
            self.intent={"id":i["id"],"actorUid":i["actor_uid"],"specimenId":i["scope"]["specimen_id"],
                "requestIdentityDigest":i["request_identity_digest"],"operationDigest":i["operation_digest"],
                "preparedDigest":i["prepared_digest"],"publicationDigest":i["publication_digest"],"preparedJson":variables["preparedJson"]}
            if self.lose_intent_ack:
                raise ConnectionError("synthetic_accepted_intent_lost_ack")
            return {"retainedIntent":1}
        if operation == "GetCanonicalResearchBindingV1":
            return {"binding":copy.deepcopy(self.binding)}
        assert operation == "PublishCanonicalResearchV1" and mutation
        self.write_calls += 1
        payload = json.loads(variables["commitJson"])
        if self.on_commit:
            self.on_commit(payload)
        if self.lose_ack:
            raise ConnectionError("synthetic_accepted_lost_ack")
        return {"committed":1}

    def _snapshot(self, row):
        assert canonical_digest(row["snapshot"]) == row["sha256"]
        return Specimen.model_validate(row["snapshot"], context={"persisted_snapshot":True})

    def locate(self, ref):
        sha, _, generation = ref.partition(":")
        return Blob("local",sha,generation or "1")

    def _sized(self, ref):
        return 2


@pytest.fixture
def basis():
    organization, collection, specimen_id, run_id = (ident(v) for v in ("org","collection","specimen","run"))
    principal = Principal(user_id="reviewer-A",scope=Scope(organization_id=organization,collection_id=collection),role="reviewer")
    research_profile = CollectionProfile(id="insects",version="fixture-v1",organization_id=organization,
        collection_id=collection,ancestry=(),knowledge_version="fixture-v1",
        # verbatim_dts declares its missing policy, as the production profile does.
        fields=tuple(FieldProfile(field_key=key,missing_policy="verbatim_dts_definition_examples"
            if key == FieldKey.VERBATIM_DTS else None) for key in ALL_FIELDS))
    pins = {"input_digest":digest("research-input-distinct-from-image"),"profile":research_profile.model_dump(mode="json"),
            "test_only":"No provider/native authority"}
    scope = ResearchScope(organization_id=organization,collection_id=collection,specimen_id=specimen_id,
        job_id="opaque-job:not-a-uuid",generation=1,input_digest=pins["input_digest"],profile_digest=digest(research_profile),sensitive=False)
    checkpoint = FieldCheckpoint(scope=scope,field_key=FieldKey.COUNTRY,revision=1,
        resolution=FieldResolution(field_key=FieldKey.COUNTRY,work_state=WorkState.WAITING_SOURCE,
            value=FieldValue(literal="unresolved fixture country"),reason="Fixture unresolved; no supported assertion"),
        prompt_digest=digest("prompt"),model_settings_digest=digest("settings"),source_registry_digest=digest("registry"))
    guard_json = module.exact_json({"fixture":"immutable prepared intent, not native authority"})
    binding_digest = digest(pins)
    publication = {"guard":{"scope":scope.model_dump(mode="json"),"binding_digest":binding_digest,
        "lease_owner":"owner-A","lease_fence":1,"lease_expires_at":4102444800.0,"expected_record_revision":1,
        "checkpoint_revisions":{"country":1},"checkpoint_digests":{"country":digest(checkpoint)},
        "dependency_revisions":{},"dependency_digests":{},"receipt_ids":[]},
        "checkpoints":[checkpoint.model_dump(mode="json")],"idempotency_key":digest("operation")}
    prepared = PreparedNativePublication.model_validate({"publication":publication,"basis":{
        "scope":scope.model_dump(mode="json"),"actor_uid":principal.user_id,"program_key":"existing-program",
        "job_key":digest("job-key"),"state_revision":7,"state_digest":digest("state"),"binding_digest":binding_digest,
        "pins_digest":binding_digest,"lease":{"job_key":digest("job-key"),"owner":"owner-A","fence":1,
            "generation":1,"expires_at":4102444800.0},"field_key":"country","field_revision":1,
        "expected_record_revision":1,"checkpoint_id":digest("checkpoint"),"checkpoint_digest":digest("native-checkpoint"),
        "original_typed_checkpoint_digest":digest(checkpoint),"typed_checkpoint_digest":digest(checkpoint),
        "original_scope":scope.model_dump(mode="json"),"source_binding_digest":binding_digest,"reused":False,
        "dependencies":[],"receipts":[],"checkpoint_outbox_key":"checkpoint/"+digest("checkpoint"),
        "checkpoint_outbox_digest":digest("checkpoint-outbox"),"publication_outbox_key":"publish/"+digest("operation"),
        "publication_outbox_digest":digest("publication-outbox"),"native_guard_json":guard_json,
        "native_guard_digest":hashlib.sha256(guard_json.encode()).hexdigest(),"idempotency_key":digest("operation")}})
    canonical_profile = {"fixture":"canonical profile distinct from enhanced profile"}
    prior = Specimen(id=specimen_id,scope=principal.scope,
        asset=Asset(id=ident("asset"),sensitive=False,sha256=digest("image"),blob_ref=digest("image")+":1",
            media_type="image/jpeg",size_bytes=2,width=1,height=1,filename="fixture.jpeg",uploader=principal.user_id),
        run=Run(id=run_id,profile_snapshot=canonical_profile,profile_registry_version="fixture-registry",
            dependencies={"profile_snapshot_sha256":canonical_digest(canonical_profile),"profile_registry_version":"fixture-registry"},
            disposition=Disposition.DEFERRED,reasons=["fixture_unresolved"]),version=1)
    connector = FakeConnector()
    old = writes(prior,connector.locate,connector._sized,principal.user_id)
    record = next(w.variables for w in old if w.operation == "AppendRecordVersionV2")
    fields = sorted([w.variables for w in old if w.operation == "AppendResolvedFieldV2"],key=lambda r:r["fieldKey"])
    identity = CanonicalIdentityV1(record_revision=1,record_version_id=record["id"],canonical_run_id=run_id,
        host_record_version_id=run_id+":1",snapshot_sha256=canonical_digest(prior.model_dump(mode="json")))
    semantic_mapping = {"field_mapping":{str(k):str(k) for k in ALL_FIELDS},"research_policy_origin":"owner-approved fixture only",
        "journal_budget_policy_digest":digest("fixture policy pin")}
    job = {"identity":{"organization_id":organization,"collection_id":collection,"specimen_id":specimen_id,"job_id":scope.job_id},
        "record_revision":1,"generation":1,"sensitive":False,"binding_digest":binding_digest,"pins":pins,"paused":False,
        "fields":{str(k):{"locked":False,"revision":1,"checkpoint":None} for k in ALL_FIELDS},"history":[],"checkpoints":[],"dependencies":{},"trace_context":None}
    registration = {"binding_id":ident("binding"),"registration_revision":1,"active":True,
        "base_canonical":identity.model_dump(mode="json"),"current_canonical":identity.model_dump(mode="json"),"publication_transition":None,
        "job_id":scope.job_id,"job_key":prepared.basis.job_key,"generation":1,"input_digest":scope.input_digest,
        "profile_digest":scope.profile_digest,"runtime_binding_digest":binding_digest,"canonical_profile_digest":canonical_digest(canonical_profile),
        "source_sha256":prior.asset.sha256,"semantic_mapping_digest":digest(semantic_mapping),"policy_digest":digest("research policy"),
        "program_key":"existing-program","field_mapping":semantic_mapping["field_mapping"],"semantic_mapping":semantic_mapping,
        "human_locks":{str(k):False for k in ALL_FIELDS},"job":job,"research_policy_origin":semantic_mapping["research_policy_origin"],
        "journal_budget_policy_digest":semantic_mapping["journal_budget_policy_digest"],
        "journal_budget_policy_origin":"verified_owner_registration_not_SQL_recomputed",
        "read_bundle":{"state_revision":7,"server_time":2000000000.0,"job_key":prepared.basis.job_key,"job":job,
            "halted":False,"paused":False,"effects":{},"outbox":{},"hold_reasons":[]}}
    raw = {"canonical":{**identity.model_dump(mode="json"),"organization_id":organization,"collection_id":collection,
        "specimen_id":specimen_id,"sensitive":False},"registrations":[registration],
        "active_registration_count":1,"snapshot":{"snapshot":prior.model_dump(mode="json"),"sha256":identity.snapshot_sha256,"revision":1,"contractVersion":"0.1"},"projection":fields}
    connector.binding = raw
    binding = CanonicalBindingV1.from_native(principal.scope,specimen_id,raw)
    result = prior.model_copy(deep=True); result.version=2; result.run.fields["country"]=module.canonical_value_v1(checkpoint.resolution,semantic_mapping["field_mapping"],{})
    projected = writes(result,connector.locate,connector._sized,principal.user_id)
    new_fields = sorted([w.variables for w in projected if w.operation == "AppendResolvedFieldV2"],key=lambda r:r["fieldKey"])
    policy_receipt = {"status":"computed","publication_digest":digest(prepared.publication),"prior_canonical":identity.model_dump(mode="json"),
        "result_digest":canonical_digest(result.model_dump(mode="json")),"policy_digest":registration["policy_digest"],
        "semantic_mapping_digest":registration["semantic_mapping_digest"],"exact_field_keys":sorted(module.CANONICAL_KEYS)}
    lineage = {"prior_fields":fields,"fields":new_fields,"evidence_id_mapping":{},
        "before_fields":{k:v.model_dump(mode="json") for k,v in prior.run.fields.items()},
        "after_fields":{k:v.model_dump(mode="json") for k,v in result.run.fields.items()},"human_locks":registration["human_locks"]}
    materialized = CanonicalPolicyMaterializationV1(prepared_digest=digest(prepared),publication_digest=digest(prepared.publication),
        prior_canonical=identity,source_sha256=prior.asset.sha256,canonical_profile_digest=registration["canonical_profile_digest"],
        research_profile_digest=scope.profile_digest,runtime_binding_digest=binding_digest,semantic_mapping_digest=registration["semantic_mapping_digest"],
        policy_digest=registration["policy_digest"],evidence_id_mapping={},result=result,result_digest=policy_receipt["result_digest"],
        policy_receipt=policy_receipt,policy_receipt_digest=digest(policy_receipt),lineage_digest=digest(lineage))
    return SimpleNamespace(principal=principal,scope=scope,prepared=prepared,prior=prior,connector=connector,
        raw=raw,binding=binding,materialized=materialized)


def retained_from_payload(payload):
    receipt = payload["receipt"]
    prepared=PreparedNativePublication.model_validate(payload["prepared"])
    identity=digest({"operation":module.OPERATION,"actor_uid":receipt["actorUid"],
        "scope":prepared.basis.scope.model_dump(mode="json"),"idempotency_key":prepared.basis.idempotency_key,
        "publication_digest":digest(prepared.publication),"expected_record_revision":prepared.basis.expected_record_revision})
    return {"publication":receipt,"request":{"operation":module.OPERATION,"actorUid":receipt["actorUid"],
        "idempotencyKey":receipt["idempotencyKey"],"requestSha256":receipt["operationDigest"],
        "specimenId":receipt["specimenId"],"revision":receipt["resultingCanonicalRevision"]},
        "snapshot":{"snapshot":payload["snapshot"],"sha256":receipt["snapshotSha256"],"revision":2,"contractVersion":"0.1"},
        "record":{"id":receipt["nativeRecordVersionId"],"runId":receipt["canonicalRunId"],"predecessorId":receipt["usedRecordVersionId"]},
        "fields":payload["fields"],"audit":{"actorUid":receipt["actorUid"],"revision":2,"requestSha256":receipt["operationDigest"]},
        "outbox":{"aggregateRevision":2,"deduplicationKey":receipt["operationDigest"]},
        "intent":{"preparedDigest":digest(prepared),"requestIdentityDigest":identity,"operationDigest":receipt["operationDigest"]}}


def writer_for(basis):
    return SqlConnectCanonicalResearchWriter(basis.connector,None,blobs=None,materializer=None,operation_client=basis.connector,
        projection_services=module.CanonicalProjectionServicesV1(writes,basis.connector.locate,basis.connector._sized,module.CANONICAL_PROJECTOR_SHA256))


def call_as(principal, callback):
    token=actor_uid.set(principal.user_id)
    try:
        return asyncio.run(callback())
    finally:
        actor_uid.reset(token)


def materialized_payload(basis):
    writer=writer_for(basis)
    return writer._materialization(basis.principal,basis.prepared,basis.binding,basis.raw,basis.prior,basis.materialized)


def test_actual_policy_consumer_preserves_twenty_and_native_id_distinctions(basis):
    payload=materialized_payload(basis)
    assert len(payload["fields"])==20 and {r["fieldKey"] for r in payload["fields"]}==module.CANONICAL_KEYS
    assert payload["receipt"]["usedCanonicalRevision"]==1 and payload["receipt"]["resultingCanonicalRevision"]==2
    assert UUID(payload["receipt"]["nativeRecordVersionId"]) != UUID(payload["receipt"]["canonicalRunId"])
    assert payload["receipt"]["jobId"]=="opaque-job:not-a-uuid"
    assert payload["receipt"]["hostRecordVersionId"]==basis.prior.run.id+":2"
    assert all(r["candidateId"]==next(old for old in basis.raw["projection"] if old["fieldKey"]==r["fieldKey"])["candidateId"]
               for r in payload["fields"] if r["fieldKey"]!="country")
    assert basis.prior.version==1 and basis.prior.run.fields["country"].literal is None


@pytest.mark.parametrize("mutation",["missing_field","duplicate_field","wrong_record","wrong_candidate","changed_other_field","cost_rollback","policy_unknown","human_lock"])
def test_actual_materialization_rejects_incomplete_or_wrong_lineage(basis,mutation):
    raw=copy.deepcopy(basis.raw); result=basis.materialized.result.model_copy(deep=True)
    if mutation=="missing_field": raw["projection"].pop()
    if mutation=="duplicate_field": raw["projection"][-1]=raw["projection"][0]
    if mutation=="wrong_record": raw["projection"][0]["recordVersionId"]=ident("wrong-run")
    if mutation=="wrong_candidate": raw["projection"][0]["candidateId"]=ident("foreign-candidate")
    if mutation=="changed_other_field": result.run.fields["county"]=FieldValue(literal="new unrelated value")
    if mutation=="cost_rollback": result.run.usage.actual_cost_micros=500000
    if mutation=="policy_unknown": result.run.disposition=None
    if mutation=="human_lock":
        reg=basis.binding.registration.model_copy(update={"human_locks":{**basis.binding.registration.human_locks,"country":True}})
        basis.binding=basis.binding.model_copy(update={"registration":reg})
    materialized=basis.materialized.model_copy(update={"result":result,"result_digest":canonical_digest(result.model_dump(mode="json"))})
    with pytest.raises(PublicationUnavailable):
        writer_for(basis)._materialization(basis.principal,basis.prepared,basis.binding,raw,basis.prior,materialized)
    assert basis.connector.write_calls==0


def test_removed_registration_unavailable_mutable_lease_outbox_replays_before_guards(basis):
    basis.connector.retained=retained_from_payload(materialized_payload(basis))
    basis.connector.binding=None  # old registration removed; not consulted on replay
    writer=writer_for(basis)       # journal/materializer unavailable; not consulted
    first=call_as(basis.principal,lambda:writer.publish_receipt_first(basis.principal,basis.prepared))
    second=call_as(basis.principal,lambda:writer.publish_receipt_first(basis.principal,basis.prepared))
    assert first==second and first.replayed
    assert [c[0] for c in basis.connector.calls]==["GetResearchPublicationReceiptV1"]*2
    assert basis.connector.write_calls==0 and actor_uid.get() is None


@pytest.mark.parametrize("part",["publication","request","snapshot","record","audit","outbox","intent"])
def test_actual_receipt_partial_native_commit_is_hold_not_new_write(basis,part):
    row=retained_from_payload(materialized_payload(basis));row[part]=None;basis.connector.retained=row
    with pytest.raises(PublicationUnavailable):
        call_as(basis.principal,lambda:writer_for(basis).publish_receipt_first(basis.principal,basis.prepared))
    assert basis.connector.write_calls==0 and [c[0] for c in basis.connector.calls]==["GetResearchPublicationReceiptV1"]


@pytest.mark.parametrize("field,value",[("operationDigest",digest("conflicting intent")),("actorUid","other actor"),
    ("nativeRecordVersionId",ident("wrong native version")),("resultingCanonicalRevision",3),
    ("canonicalRunId",ident("job-is-not-run")),("snapshotSha256",digest("wrong snapshot"))])
def test_actual_receipt_conflict_never_becomes_new_write(basis,field,value):
    row=retained_from_payload(materialized_payload(basis));row["publication"][field]=value;basis.connector.retained=row
    with pytest.raises(PublicationUnavailable):
        call_as(basis.principal,lambda:writer_for(basis).publish_receipt_first(basis.principal,basis.prepared))
    assert basis.connector.write_calls==0


def test_fresh_access_revocation_wins_over_retained_receipt(basis):
    basis.connector.retained=retained_from_payload(materialized_payload(basis));basis.connector.denied=True
    with pytest.raises(PermissionError):
        call_as(basis.principal,lambda:writer_for(basis).publish_receipt_first(basis.principal,basis.prepared))
    assert basis.connector.write_calls==0 and actor_uid.get() is None


def test_unverified_actor_never_reaches_connector(basis):
    with pytest.raises(PermissionError):
        asyncio.run(writer_for(basis).publish_receipt_first(basis.principal,basis.prepared))
    assert basis.connector.calls==[]


def test_missing_materializer_holds_after_fresh_receipt_probe_without_canonical_write(basis):
    with pytest.raises(PublicationUnavailable,match="canonical_policy_materializer_unavailable"):
        call_as(basis.principal,lambda:writer_for(basis).publish_receipt_first(basis.principal,basis.prepared))
    assert [c[0] for c in basis.connector.calls]==["GetResearchPublicationReceiptV1"] and basis.connector.write_calls==0


@pytest.mark.parametrize("mutate",["missing","ambiguous","base_zero","native_mismatch","generation","input","profile","run","policy_origin","foreign_effect"])
def test_real_binding_mapper_fails_closed_and_read_has_no_effect(basis,mutate):
    row=copy.deepcopy(basis.raw)
    if mutate=="missing":row["registrations"]=[]
    if mutate=="ambiguous":row["registrations"].append(copy.deepcopy(row["registrations"][0]))
    if mutate=="base_zero":row["registrations"][0]["base_canonical"]["record_revision"]=0
    if mutate=="native_mismatch":row["canonical"]["record_version_id"]=ident("wrong")
    if mutate=="generation":row["registrations"][0]["generation"]=2
    if mutate=="input":row["registrations"][0]["input_digest"]=digest("new input")
    if mutate=="profile":row["registrations"][0]["profile_digest"]=digest("new profile")
    if mutate=="run":row["canonical"]["canonical_run_id"]=ident("wrong run")
    if mutate=="policy_origin":row["registrations"][0]["research_policy_origin"]=""
    if mutate=="foreign_effect":row["registrations"][0]["read_bundle"]["effects"]={"bad":{"job_key":digest("other"),"scope":{}}}
    with pytest.raises((PublicationUnavailable,ValueError)):
        CanonicalBindingV1.from_native(basis.principal.scope,basis.scope.specimen_id,row)
    assert basis.connector.write_calls==0


def test_current_after_publication_keeps_immutable_jobbase_and_receipt_transition(basis):
    payload=materialized_payload(basis);r=payload["receipt"];row=copy.deepcopy(basis.raw)
    current={"record_revision":2,"record_version_id":r["nativeRecordVersionId"],"canonical_run_id":r["canonicalRunId"],
        "host_record_version_id":r["hostRecordVersionId"],"snapshot_sha256":r["snapshotSha256"]}
    reg=row["registrations"][0];reg["current_canonical"]=current
    reg["publication_transition"]={"receipt_id":r["id"],"operation_digest":r["operationDigest"],"publication_digest":r["publicationDigest"],
        **{k:reg[k] for k in ("binding_id","job_id","job_key","generation","input_digest","profile_digest","runtime_binding_digest")},
        "base_canonical":reg["base_canonical"],"current_canonical":current}
    row["canonical"].update(current)
    rebound=CanonicalBindingV1.from_native(basis.principal.scope,basis.scope.specimen_id,row)
    assert rebound.canonical.record_revision==2 and rebound.registration.job["record_revision"]==1
    reg["publication_transition"]=None
    with pytest.raises(PublicationUnavailable,match="transition_missing"):
        CanonicalBindingV1.from_native(basis.principal.scope,basis.scope.specimen_id,row)


def test_actual_lost_ack_receipt_path_has_no_second_mutation(basis,monkeypatch):
    # The real atomic SQL qualifier is separate. This synthetic finite transport
    # control isolates the adapter's acknowledgement handling and same-operation
    # replay; publication validation is explicitly replaced, not misreported.
    payload=materialized_payload(basis);state={"outbox":{basis.prepared.basis.publication_outbox_key:{"delivered":False},
        basis.prepared.basis.checkpoint_outbox_key:{"delivered":False}}}
    state_digest=digest(state)
    prepared=basis.prepared.model_copy(update={"basis":basis.prepared.basis.model_copy(update={"state_digest":state_digest})})
    async def admitted_fixture(*args,**kwargs):return None
    monkeypatch.setattr(module,"validate_native_publication",admitted_fixture)
    writer=SqlConnectCanonicalResearchWriter(basis.connector,SimpleNamespace(scope=None,
        store=SimpleNamespace(_read=lambda scope:SimpleNamespace(revision=7,state=state))),blobs=None,
        materializer=SimpleNamespace(materialize=None),operation_client=basis.connector,
        projection_services=module.CanonicalProjectionServicesV1(writes,basis.connector.locate,basis.connector._sized,module.CANONICAL_PROJECTOR_SHA256))
    async def materialize(*args,**kwargs):return basis.materialized
    writer.materializer.materialize=materialize
    # Native contract payload construction is separately covered above; retain
    # fixture immutable operation digest for this distinct transport case.
    original=writer._materialization
    writer._materialization=lambda *args,**kwargs:copy.deepcopy(payload)
    payload["prepared"]=prepared.model_dump(mode="json")
    payload["receipt"]["preparedDigest"]=digest(prepared)
    payload["receipt"]["operationDigest"]=scientific_intent(basis.principal,prepared)
    payload["snapshot"]["audit"][-1]["reason"]=payload["receipt"]["operationDigest"]
    payload["receipt"]["snapshotSha256"]=canonical_digest(payload["snapshot"])
    basis.connector.lose_ack=True
    basis.connector.on_commit=lambda p:setattr(basis.connector,"retained",retained_from_payload(p))
    result=call_as(basis.principal,lambda:writer.publish_receipt_first(basis.principal,prepared))
    assert result.replayed and basis.connector.write_calls==1
    replay=call_as(basis.principal,lambda:writer.publish_receipt_first(basis.principal,prepared))
    assert replay==result and basis.connector.write_calls==1
    assert state["outbox"][prepared.basis.publication_outbox_key]["delivered"] is False
    assert all(call[3]==basis.principal.user_id for call in basis.connector.calls)
    writer._materialization=original



def expired_original(basis):
    """A durable original whose expiry1 is past; replay must not refresh it."""
    data=basis.prepared.model_dump(mode="json")
    data["basis"]["lease"]["expires_at"]=1.0
    data["publication"]["guard"]["lease_expires_at"]=1.0
    basis.prepared=PreparedNativePublication.model_validate(data)
    receipt={**basis.materialized.policy_receipt,"publication_digest":digest(basis.prepared.publication)}
    basis.materialized=basis.materialized.model_copy(update={"prepared_digest":digest(basis.prepared),
        "publication_digest":digest(basis.prepared.publication),"policy_receipt":receipt,"policy_receipt_digest":digest(receipt)})
    return basis.prepared


def retained_intent_row(basis):
    prepared=basis.prepared
    return {"id":ident("retained-original-intent"),"actorUid":basis.principal.user_id,"specimenId":basis.scope.specimen_id,
        "requestIdentityDigest":module.request_identity(basis.principal,prepared),
        "operationDigest":scientific_intent(basis.principal,prepared),"preparedDigest":digest(prepared),
        "publicationDigest":digest(prepared.publication),"preparedJson":module.exact_json(prepared.model_dump(mode="json"))}


def test_restart_recovers_original_expired_intent_then_receipt_with_no_mutable_store(basis):
    prepared=expired_original(basis)
    basis.connector.retained=retained_from_payload(materialized_payload(basis))
    basis.connector.intent=retained_intent_row(basis)
    basis.connector.binding=None
    # A fresh writer has no in-memory prepared, journal, materializer or lease.
    # The actual native-intent adapter loads full original JSON from the fake DB.
    fresh=writer_for(basis)
    result=call_as(basis.principal,lambda:fresh.resume_same_operation(basis.principal,basis.scope.specimen_id,
        prepared.basis.idempotency_key,module.request_identity(basis.principal,prepared)))
    assert result.replayed and result.receipt_id==UUID(basis.connector.retained["publication"]["id"])
    assert [call[0] for call in basis.connector.calls]==["GetResearchPublicationIntentV1","GetResearchPublicationReceiptV1"]
    assert basis.connector.write_calls==basis.connector.intent_write_calls==0
    restored=PreparedNativePublication.model_validate(json.loads(basis.connector.intent["preparedJson"]))
    assert restored==prepared and restored.basis.lease.expires_at==1.0
    assert actor_uid.get() is None


@pytest.mark.parametrize("mutation",["missing","actor","specimen","request_digest","prepared","operation"])
def test_restart_missing_or_conflicting_intent_never_prepares_or_writes(basis,mutation):
    row=retained_intent_row(basis)
    if mutation=="missing":row=None
    if mutation=="actor":row["actorUid"]="other reviewer"
    if mutation=="specimen":row["specimenId"]=ident("other specimen")
    if mutation=="request_digest":row["requestIdentityDigest"]=digest("other command")
    if mutation=="prepared":row["preparedDigest"]=digest("other prepared")
    if mutation=="operation":row["operationDigest"]=digest("other operation")
    basis.connector.intent=row
    with pytest.raises(PublicationUnavailable):
        call_as(basis.principal,lambda:writer_for(basis).resume_same_operation(basis.principal,basis.scope.specimen_id,
            basis.prepared.basis.idempotency_key,module.request_identity(basis.principal,basis.prepared)))
    assert [call[0] for call in basis.connector.calls]==["GetResearchPublicationIntentV1"]
    assert basis.connector.write_calls==basis.connector.intent_write_calls==0


def test_intent_accepted_lost_ack_is_one_insert_then_exact_read_never_rewrite(basis):
    basis.connector.lose_intent_ack=True
    writer=writer_for(basis)
    retained=call_as(basis.principal,lambda:writer._retain_intent(basis.principal,basis.prepared))
    again=call_as(basis.principal,lambda:writer._retain_intent(basis.principal,basis.prepared))
    assert retained==again and retained.prepared==basis.prepared
    assert basis.connector.intent_write_calls==1 and basis.connector.write_calls==0
    assert [call[0] for call in basis.connector.calls]==["GetResearchPublicationIntentV1","RetainResearchPublicationIntentV1",
        "GetResearchPublicationIntentV1","GetResearchPublicationIntentV1"]
    assert actor_uid.get() is None


@pytest.mark.parametrize("denial",["organization_inactive","collection_inactive","sensitive","historical_sensitive"])
def test_actual_outer_access_metadata_denial_is_typed_and_not_missing_binding(denial):
    data={"organizationMember":{"active":True},"collectionMember":{"active":True,"role":"reviewer","canViewSensitive":False},
        "specimen":{"sensitive":False},"retained":None}
    if denial=="organization_inactive":data["organizationMember"]["active"]=False
    if denial=="collection_inactive":data["collectionMember"]["active"]=False
    if denial=="sensitive":data["specimen"]["sensitive"]=True
    if denial=="historical_sensitive":data["retained"]={"publication":{"sensitive":True}}
    with pytest.raises(PermissionError):
        module.SqlConnectNativeOperationClient._access_data(data,"GetResearchPublicationReceiptV1")


def test_actual_outer_aliases_allow_null_unavailable_binding_but_reject_shape_drift():
    data={"organizationMember":{"active":True},"collectionMember":{"active":True,"role":"viewer","canViewSensitive":False},
        "specimen":{"sensitive":False},"binding":None}
    module.SqlConnectNativeOperationClient._access_data(data,"GetCanonicalResearchBindingV1")
    with pytest.raises(PublicationUnavailable):
        module.SqlConnectNativeOperationClient._access_data({"binding":None},"GetCanonicalResearchBindingV1")



def proved_reuse(basis):
    original=basis.prepared.publication.checkpoints[0]
    old_scope=original.scope
    current_scope=old_scope.model_copy(update={"generation":2})
    original_identity={k:getattr(old_scope,k) for k in ("organization_id","collection_id","specimen_id","job_id","generation")}
    current_identity={k:getattr(current_scope,k) for k in original_identity}
    native={"scope":original_identity,"field_key":"country","revision":1,"payload":original.model_dump(mode="json"),
        "dependencies":{},"dependency_digests":{},"receipt_ids":[]}
    native["id"]=digest({"scope":native["scope"],"field":"country","revision":1,"payload":native["payload"]})
    job=copy.deepcopy(basis.binding.registration.job)
    history={"scope":original_identity,"binding_digest":job["binding_digest"],"pins":copy.deepcopy(job["pins"]),
        "fields":{"country":{"checkpoint":native}}}
    job["generation"]=2;job["history"]=[history]
    job["fields"]["country"]["checkpoint"]=native
    job["fields"]["country"]["reuse"]={"reused_from_scope_digest":digest(original_identity),"checkpoint_digest":digest(native),
        "into_scope_digest":digest(current_identity),"source_binding_digest":job["binding_digest"],
        "target_binding_digest":job["binding_digest"],"retained_dependencies":{},"retained_dependency_digests":{}}
    reused=FieldCheckpoint.model_validate({**original.model_dump(mode="json"),"scope":current_scope.model_dump(mode="json"),
        "reused_from_scope_digest":digest(old_scope),"reused_from_checkpoint_digest":digest(original)})
    data=basis.prepared.model_dump(mode="json")
    data["publication"]["checkpoints"]=[reused.model_dump(mode="json")]
    data["publication"]["guard"]["scope"]=current_scope.model_dump(mode="json")
    data["publication"]["guard"]["checkpoint_digests"]={"country":digest(reused)}
    data["basis"].update(scope=current_scope.model_dump(mode="json"),original_scope=old_scope.model_dump(mode="json"),
        reused=True,history_digest=digest(history),checkpoint_id=native["id"],checkpoint_digest=digest(native),
        original_typed_checkpoint_digest=digest(original),typed_checkpoint_digest=digest(reused),
        checkpoint_outbox_key="checkpoint/"+native["id"])
    data["basis"]["lease"]["generation"]=2
    prepared=PreparedNativePublication.model_validate(data)
    reg=basis.binding.registration.model_copy(update={"generation":2,"job":job,
        "read_bundle":{**basis.binding.registration.read_bundle,"job":job}})
    return prepared,basis.binding.model_copy(update={"registration":reg}),history


def test_actual_proved_reuse_preserves_original_scope_and_history_without_new_accounting(basis):
    prepared,binding,history=proved_reuse(basis)
    before=copy.deepcopy(binding.registration.job)
    capture_scope,retained=SqlConnectCanonicalResearchWriter._capture_lineage(prepared,binding)
    assert capture_scope==prepared.basis.original_scope and capture_scope.generation==1
    assert prepared.basis.scope.generation==2 and retained==history
    assert binding.registration.job==before and basis.connector.write_calls==basis.connector.intent_write_calls==0


@pytest.mark.parametrize("mutation",["missing_history","changed_input","changed_profile","changed_pins","wrong_link","locked"])
def test_actual_reuse_requires_authoritative_causal_history_without_scope_rebinding(basis,mutation):
    prepared,binding,history=proved_reuse(basis)
    job=copy.deepcopy(binding.registration.job)
    if mutation=="missing_history":job["history"]=[]
    if mutation=="changed_input":prepared=prepared.model_copy(update={"basis":prepared.basis.model_copy(update={
        "original_scope":prepared.basis.original_scope.model_copy(update={"input_digest":digest("other input")})})})
    if mutation=="changed_profile":prepared=prepared.model_copy(update={"basis":prepared.basis.model_copy(update={
        "original_scope":prepared.basis.original_scope.model_copy(update={"profile_digest":digest("other profile")})})})
    if mutation=="changed_pins":job["pins"]={**job["pins"],"different_runtime":"unknown"}
    if mutation=="wrong_link":job["fields"]["country"]["reuse"]["target_binding_digest"]=digest("unproved target")
    if mutation=="locked":job["fields"]["country"]["locked"]=True
    binding=binding.model_copy(update={"registration":binding.registration.model_copy(update={"job":job})})
    with pytest.raises(PublicationUnavailable):
        SqlConnectCanonicalResearchWriter._capture_lineage(prepared,binding)
    assert basis.connector.write_calls==basis.connector.intent_write_calls==0



def test_declared_verbatim_transform_preserves_value_and_sets_layer_without_guess(basis):
    cp=basis.prepared.publication.checkpoints[0]
    transformed=module.canonical_value_v1(cp.resolution,basis.binding.registration.field_mapping,{})
    assert transformed.layer=="verbatim" and transformed.derived_from==[]
    assert transformed.literal==cp.resolution.value.literal and transformed.parsed==cp.resolution.value.parsed
    assert cp.resolution.value.layer is None  # immutable checkpoint is not rewritten


def test_settled_transform_retains_absent_literal_without_inventing_candidate(basis):
    cp=basis.prepared.publication.checkpoints[0]
    resolution=cp.resolution.model_copy(update={"value_layer":"settled","value":cp.resolution.value.model_copy(update={"literal":None})})
    value=module.canonical_value_v1(resolution,basis.binding.registration.field_mapping,{})
    assert value.layer=="settled" and value.literal is None and value.derived_from==[]


def test_declared_layer_disagreement_is_hold_without_normalization(basis):
    cp=basis.prepared.publication.checkpoints[0]
    resolution=cp.resolution.model_copy(update={"value_layer":"settled","value":cp.resolution.value.model_copy(update={"layer":"verbatim"})})
    with pytest.raises(PublicationUnavailable,match="layer_conflict"):
        module.canonical_value_v1(resolution,basis.binding.registration.field_mapping,{})
    assert basis.connector.write_calls==0



def derived_resolution():
    dependency=DependencyPin(field_key=FieldKey.ELEVATION_FROM_FT,revision=1,digest=digest("typed-fixture-source-resolution"))
    derivation=DerivationRecord(rule_id="fixture-ft-to-m",rule_version="fixture-v1",operation="multiply",
        source_field=dependency.field_key,source_revision=dependency.revision,source_digest=dependency.digest,
        source_value="10",factor="0.3048",exact_operation="10 * 0.3048",unrounded_value="3.048",display_value="3.05",
        source_assembly_ids=(),source_fragment_ids=(),evidence_ids=("research-evidence",))
    return FieldResolution(field_key=FieldKey.ELEVATION_FROM_M,work_state=WorkState.RESOLVED,value_layer="derived",
        value=FieldValue(state=module.ValueState.SUPPORTED,literal=None,parsed="3.05",evidence_ids=["research-evidence"]),
        evidence_ids=("research-evidence",),dependencies=(dependency,),derivation=derivation,reason="Synthetic typed transformation only")


def test_derived_transform_maps_actual_consumed_dependency_and_does_not_fabricate_literal(basis):
    resolution=derived_resolution()
    value=module.canonical_value_v1(resolution,basis.binding.registration.field_mapping,{"research-evidence":ident("canonical-evidence")})
    assert value.layer=="derived" and value.derived_from==["elevation_from_ft"]
    assert value.parsed=="3.05" and value.literal is None
    assert value.evidence_ids==[ident("canonical-evidence")] and resolution.value.evidence_ids==["research-evidence"]


def test_current_exact_projector_lacks_literal_less_derived_candidate_and_no_fake_fix(basis):
    resolution=derived_resolution()
    value=module.canonical_value_v1(resolution,basis.binding.registration.field_mapping,{"research-evidence":ident("canonical-evidence")})
    specimen=basis.prior.model_copy(deep=True);specimen.version=2;specimen.run.fields["elevation_from_m"]=value
    projection=writes(specimen,basis.connector.locate,basis.connector._sized,basis.principal.user_id)
    row=next(write.variables for write in projection if write.operation=="AppendResolvedFieldV2" and write.variables["fieldKey"]=="elevation_from_m")
    assert row["candidateId"] is None
    assert not any(write.operation=="AppendFieldCandidateV2" and write.variables["fieldKey"]=="elevation_from_m" for write in projection)
    assert specimen.run.fields["elevation_from_m"].literal is None and basis.connector.write_calls==0


def test_derived_transform_rejects_unproved_consumed_revision(basis):
    resolution=derived_resolution()
    resolution=resolution.model_copy(update={"dependencies":(resolution.dependencies[0].model_copy(update={"revision":2}),)})
    with pytest.raises(PublicationUnavailable,match="derivation_unproved"):
        module.canonical_value_v1(resolution,basis.binding.registration.field_mapping,{"research-evidence":ident("canonical-evidence")})



def test_transform_real_uuid_instance_and_string_evidence_mapping_are_equivalent(basis):
    resolution=derived_resolution();identifier=ident("canonical-evidence")
    as_string=module.canonical_value_v1(resolution,basis.binding.registration.field_mapping,{"research-evidence":identifier})
    as_uuid=module.canonical_value_v1(resolution,basis.binding.registration.field_mapping,{"research-evidence":UUID(identifier)})
    assert as_string==as_uuid and as_uuid.evidence_ids==[identifier]


@pytest.mark.parametrize("invalid",[True,1,None,{},"not-a-uuid"])
def test_transform_non_uuid_evidence_mapping_holds_without_type_coercion(basis,invalid):
    with pytest.raises(PublicationUnavailable,match="evidence_mapping_unproved"):
        module.canonical_value_v1(derived_resolution(),basis.binding.registration.field_mapping,{"research-evidence":invalid})
    assert basis.connector.write_calls==0


# Corrective SOURCE controls. They invoke genuine deterministic producers when
# separately qualified; no project execution or native/capture acceptance yet.
def genuine_derivation_request(basis,kind):
    from specimen_digitization.research_harness.contracts import (
        EventHypothesis,EventKind,ROLE_FIELDS,SourceFragment,SpecialistRole,SpecialistRequest)
    from specimen_digitization.research_harness.evidence import assemble_field
    from specimen_digitization.research_harness.prompts import resolve_prompt
    from specimen_digitization.research_harness.sources import insects_registry
    scope=basis.prepared.basis.scope
    text={"G44":"3 IX '46","G41-ft":"100 ft","G41-m":"30 m"}[kind]
    field={"G44":FieldKey.DATE_VISITED_FROM,"G41-ft":FieldKey.ELEVATION_FROM_FT,
           "G41-m":FieldKey.ELEVATION_FROM_M}[kind]
    role=SpecialistRole.TEMPORAL if kind=="G44" else SpecialistRole.MEASUREMENT
    fragment=SourceFragment(id="genuine-fragment",scope=scope,asset_id=ident("asset"),asset_generation="1",
        asset_digest="0"*64,label_id=ident("label"),region_id=ident("region"),observation_id=ident("reading"),
        reader="independent-fixture-reader",model_id="fake",prompt_digest="0"*64,observation_text=text,
        observation_digest=hashlib.sha256(text.encode()).hexdigest(),start=0,end=len(text),literal=text,order=0)
    event=EventHypothesis(id="genuine-event",scope=scope,kind=EventKind.COLLECTING,
        fragment_ids=(fragment.id,),evidence_ids=("role-evidence",),reason="Synthetic independently accepted input",
        status="accepted",validator_version="fixture-v1")
    assembly=assemble_field(assembly_id="genuine-assembly",scope=scope,field_key=field,
        fragments=(fragment,),event=event)
    prompt=resolve_prompt(role,profile_digest=scope.profile_digest,source_registry_digest=insects_registry().digest,
        toolset_digest="0"*64,model_route="harness-deepseek",output_schema_digest="0"*64)
    return SpecialistRequest(scope=scope,role=role,field_keys=ROLE_FIELDS[role],prompt=prompt,
        fragments=(fragment,),events=(event,),assemblies=(assembly,))


def genuine_derivation(basis,kind):
    from specimen_digitization.research_harness.evidence import (
        temporal_resolutions,settle_elevation,elevation_resolutions)
    request=genuine_derivation_request(basis,kind)
    if kind=="G44":
        results=temporal_resolutions(request,event_id=request.events[0].id,source_revision=7)
        target=FieldKey.DATE_VISITED_TO
    else:
        settled=settle_elevation(request,assembly_ids=(request.assemblies[0].id,),source_revision=7)
        results=elevation_resolutions(settled)
        target=FieldKey.ELEVATION_FROM_M if kind=="G41-ft" else FieldKey.ELEVATION_FROM_FT
    derived=next(value for value in results if value.field_key==target)
    source=next(value for value in results if value.field_key==derived.derivation.source_field)
    return request,source,derived


def helper_resolutions(scope,kind):
    """The evidence.py helpers' own results for synthetic label text: a written
    determination date ("date") or one written elevation ("elevation"). Neither
    helper sets value.evidence_relations."""
    from specimen_digitization.research_harness.contracts import (
        EventHypothesis,EventKind,ROLE_FIELDS,SourceFragment,SpecialistRole,SpecialistRequest)
    from specimen_digitization.research_harness.evidence import (
        assemble_field,elevation_resolutions,settle_elevation,temporal_resolutions)
    from specimen_digitization.research_harness.prompts import resolve_prompt
    from specimen_digitization.research_harness.sources import insects_registry
    if kind=="date":
        text,field,role,event_kind="3 IX '46",FieldKey.DATE_IDENTIFIED,SpecialistRole.TEMPORAL,EventKind.DETERMINATION
    else:
        text,field,role,event_kind="100 ft",FieldKey.ELEVATION_FROM_FT,SpecialistRole.MEASUREMENT,EventKind.COLLECTING
    fragment=SourceFragment(id="helper-fragment",scope=scope,asset_id=ident("asset"),asset_generation="1",
        asset_digest="0"*64,label_id=ident("label"),region_id=ident("region"),observation_id=ident("reading"),
        reader="independent-fixture-reader",model_id="fake",prompt_digest="0"*64,observation_text=text,
        observation_digest=hashlib.sha256(text.encode()).hexdigest(),start=0,end=len(text),literal=text,order=0)
    event=EventHypothesis(id="helper-event",scope=scope,kind=event_kind,fragment_ids=(fragment.id,),
        evidence_ids=("role-evidence",),reason="Synthetic independently accepted input",status="accepted",
        validator_version="fixture-v1")
    assembly=assemble_field(assembly_id="helper-assembly",scope=scope,field_key=field,fragments=(fragment,),event=event)
    prompt=resolve_prompt(role,profile_digest=scope.profile_digest,source_registry_digest=insects_registry().digest,
        toolset_digest="0"*64,model_route="harness-deepseek",output_schema_digest="0"*64)
    request=SpecialistRequest(scope=scope,role=role,field_keys=ROLE_FIELDS[role],prompt=prompt,
        fragments=(fragment,),events=(event,),assemblies=(assembly,))
    if kind=="date":
        return request,temporal_resolutions(request,event_id=event.id)
    return request,elevation_resolutions(settle_elevation(request,assembly_ids=(assembly.id,)))


@pytest.mark.parametrize("kind",["G44","G41-ft","G41-m"])
def test_real_temporal_and_elevation_producers_keep_distinct_science_and_resolution_digests(basis,kind):
    from specimen_digitization.research_harness.evidence import validate_resolution
    request,source,resolution=genuine_derivation(basis,kind)
    pin=resolution.dependencies[0];record=resolution.derivation
    before=resolution.model_dump(mode="json")
    assert record.source_field==pin.field_key and record.source_revision==pin.revision==7
    assert pin.digest==digest(source) and record.source_digest!=pin.digest
    assert validate_resolution(request,resolution)==resolution
    mapping={key:UUID(ident("genuine-evidence:"+key)) for key in resolution.evidence_ids}
    value=module.canonical_value_v1(resolution,basis.binding.registration.field_mapping,mapping)
    assert value.layer=="derived" and value.literal is None
    assert value.derived_from==[basis.binding.registration.field_mapping[str(pin.field_key)]]
    assert value.parsed==resolution.value.parsed and value.normalized==resolution.value.normalized
    assert resolution.model_dump(mode="json")==before and resolution.derivation==record
    assert basis.connector.write_calls==basis.connector.intent_write_calls==0


@pytest.mark.parametrize("kind",["G44","G41-ft","G41-m"])
@pytest.mark.parametrize("mutation",["scientific_sha","source_value","source_context","source_scope","missing_request"])
def test_exact_scientific_validation_refuses_tampered_source_record_or_original_context(basis,kind,mutation):
    from specimen_digitization.research_harness.evidence import EvidenceError,validate_resolution
    request,source,resolution=genuine_derivation(basis,kind)
    if mutation=="scientific_sha":
        resolution=resolution.model_copy(update={"derivation":resolution.derivation.model_copy(update={"source_digest":digest("tampered science")})})
    if mutation=="source_value":
        resolution=resolution.model_copy(update={"derivation":resolution.derivation.model_copy(update={"source_value":"unproved"})})
    if mutation=="source_context":
        changed=request.events[0].model_copy(update={"id":"different-event"})
        request=request.model_copy(update={"events":(changed,)})
    if mutation=="source_scope":
        request=request.model_copy(update={"scope":request.scope.model_copy(update={"generation":2})})
    if mutation=="missing_request":
        request=request.model_copy(update={"assemblies":()})
    with pytest.raises(EvidenceError):
        validate_resolution(request,resolution)
    assert basis.connector.write_calls==basis.connector.intent_write_calls==0


@pytest.mark.parametrize("mutation",["field","revision","no_pin","duplicate_pin"])
def test_pure_transform_rejects_wrong_or_ambiguous_consumed_source_identity(basis,mutation):
    request,source,resolution=genuine_derivation(basis,"G44")
    pin=resolution.dependencies[0]
    if mutation=="field":pins=(pin.model_copy(update={"field_key":FieldKey.DATE_IDENTIFIED}),)
    elif mutation=="revision":pins=(pin.model_copy(update={"revision":8}),)
    elif mutation=="no_pin":pins=()
    else:pins=(pin,pin)
    resolution=resolution.model_copy(update={"dependencies":pins})
    mapping={key:ident("genuine-evidence:"+key) for key in resolution.evidence_ids}
    with pytest.raises(PublicationUnavailable):
        module.canonical_value_v1(resolution,basis.binding.registration.field_mapping,mapping)
    assert basis.connector.write_calls==0


@pytest.mark.parametrize("generation",[True,False,"1",1.0,0,-1,None])
def test_actual_reuse_raw_history_generation_is_strict_before_digest_selection(basis,generation):
    prepared,binding,history=proved_reuse(basis)
    history=copy.deepcopy(history);history["scope"]["generation"]=generation
    job=copy.deepcopy(binding.registration.job);job["history"]=[history]
    binding=binding.model_copy(update={"registration":binding.registration.model_copy(update={"job":job})})
    # A digest of the malformed actual row is no authority for its scope types.
    prepared=prepared.model_copy(update={"basis":prepared.basis.model_copy(update={"history_digest":digest(history)})})
    with pytest.raises(PublicationUnavailable,match="history_scope_invalid"):
        SqlConnectCanonicalResearchWriter._capture_lineage(prepared,binding)
    assert basis.connector.write_calls==basis.connector.intent_write_calls==0


@pytest.mark.parametrize("mutation",["extra","missing","bool_job","float_org","none_collection","empty_specimen"])
def test_actual_reuse_raw_history_requires_exact_five_string_identity_keys(basis,mutation):
    prepared,binding,history=proved_reuse(basis)
    history=copy.deepcopy(history);scope=history["scope"]
    if mutation=="extra":scope["sensitive"]=False
    if mutation=="missing":del scope["specimen_id"]
    if mutation=="bool_job":scope["job_id"]=True
    if mutation=="float_org":scope["organization_id"]=1.0
    if mutation=="none_collection":scope["collection_id"]=None
    if mutation=="empty_specimen":scope["specimen_id"]=""
    job=copy.deepcopy(binding.registration.job);job["history"]=[history]
    binding=binding.model_copy(update={"registration":binding.registration.model_copy(update={"job":job})})
    prepared=prepared.model_copy(update={"basis":prepared.basis.model_copy(update={"history_digest":digest(history)})})
    with pytest.raises(PublicationUnavailable,match="history_scope_invalid"):
        SqlConnectCanonicalResearchWriter._capture_lineage(prepared,binding)
    assert basis.connector.write_calls==basis.connector.intent_write_calls==0


def genuine_native_source_checkpoint(basis):
    request,source,resolution=genuine_derivation(basis,"G44")
    checkpoint=basis.prepared.publication.checkpoints[0].model_copy(update={
        "field_key":source.field_key,"revision":7,"resolution":source})
    identity={key:getattr(request.scope,key) for key in ("organization_id","collection_id","specimen_id","job_id","generation")}
    native={"scope":identity,"field_key":str(source.field_key),"revision":7,
        "payload":checkpoint.model_dump(mode="json"),"retry_command_id":checkpoint.retry_command_id,
        "receipt_ids":list(checkpoint.effect_receipt_ids),"dependencies":{},"dependency_digests":{}}
    native["id"]=digest({"scope":identity,"field":str(source.field_key),"revision":7,"payload":native["payload"]})
    job={"fields":{str(source.field_key):{"locked":False,"revision":7,"checkpoint":native}},"checkpoints":[native]}
    return request,resolution,checkpoint,native,job


def test_actual_native_checkpoint_proves_complete_source_separate_from_scientific_fingerprint(basis):
    from specimen_digitization.research_harness.publication import _native_checkpoint
    request,resolution,checkpoint,native,job=genuine_native_source_checkpoint(basis)
    actual,original=_native_checkpoint(job,checkpoint,request.scope)
    assert actual==native and original==checkpoint
    assert resolution.dependencies[0].digest==digest(original.resolution)
    assert resolution.derivation.source_digest!=resolution.dependencies[0].digest
    assert basis.connector.write_calls==0  # this proves neither nativeSQL nor publication


@pytest.mark.parametrize("mutation",["missing","wrong_revision","wrong_id","changed_payload"])
def test_actual_native_source_checkpoint_refuses_absent_or_mutated_proof(basis,mutation):
    from specimen_digitization.research_harness.publication import _native_checkpoint
    from specimen_digitization.research_harness.persistence import StaleWork
    request,resolution,checkpoint,native,job=genuine_native_source_checkpoint(basis)
    field=job["fields"][str(checkpoint.field_key)]
    if mutation=="missing":field["checkpoint"]=None
    if mutation=="wrong_revision":field["revision"]=8
    if mutation=="wrong_id":native["id"]=digest("unproved source checkpoint")
    if mutation=="changed_payload":native["payload"]["resolution"]["reason"]="unproved scientific basis"
    with pytest.raises(StaleWork):
        _native_checkpoint(job,checkpoint,request.scope)
    assert basis.connector.write_calls==basis.connector.intent_write_calls==0
