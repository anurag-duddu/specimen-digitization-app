"""Host-read accepted proof context with synthetic native journal rows; no IO."""
from copy import deepcopy

import pytest

from specimen_digitization.research_harness.contracts import ALL_FIELDS, FieldKey, digest
from specimen_digitization.research_harness.dependency_context import collecting_context_for_job
from specimen_digitization.research_harness.persistence import StaleWork
from test_geography_context import accepted_dependency, request


def source_job(*sources):
    pins={"fixture":"native-host-proof-context"}
    job={"pins":pins,"history":[],"fields":{str(key):dict(locked=False,checkpoint=None,
        revision=0,work_state="pending") for key in ALL_FIELDS}}
    proofs={}
    for proof,pin in sources:
        cp=next(cp for cp in proof.checkpoints if cp.field_key==pin.field_key)
        scope={key:getattr(cp.scope,key) for key in ("organization_id","collection_id","specimen_id","job_id","generation")}
        native=dict(scope=scope,field_key=str(cp.field_key),revision=cp.revision,payload=cp.model_dump(mode="json"),
            binding_digest=digest(pins),retry_command_id=cp.retry_command_id,receipt_ids=list(cp.effect_receipt_ids),
            dependencies={str(p.field_key):p.revision for p in cp.resolution.dependencies},
            dependency_digests={str(p.field_key):p.digest for p in cp.resolution.dependencies},
            accepted_output_proof=dict(proof_digest=proof.proof_digest,request_digest=digest(proof.acceptance.original_request)))
        native["id"]=digest({"scope":scope,"field":str(cp.field_key),"revision":cp.revision,"payload":native["payload"]})
        job["fields"][str(cp.field_key)]=dict(locked=False,revision=cp.revision,checkpoint=native,work_state="resolved")
        proofs[native["id"]]=proof
    return job,proofs


def test_production_context_reads_and_revalidates_actual_native_proofs():
    date=accepted_dependency()
    collector=accepted_dependency(FieldKey.COLLECTORS,"Synthetic Collector")
    job,proofs=source_job(date,collector)
    req=request(dependencies=(date[1],collector[1]))
    read=[]
    def reader(key):
        read.append(key)
        return proofs[key]
    context=collecting_context_for_job(req,job,checkpoint_proof_reader=reader)
    assert set(read)==set(proofs)
    assert context.collected_on=="1948-04-25"
    assert {item.field_key for item in context.values}=={FieldKey.DATE_VISITED_FROM,FieldKey.COLLECTORS}
    assert {item.proof_digest for item in context.proofs}=={date[0].proof_digest,collector[0].proof_digest}
    assert collecting_context_for_job(request(),job,checkpoint_proof_reader=lambda _:pytest.fail("unpinned read")) is None


@pytest.mark.parametrize("kind", ["changed_pin","missing_proof","crossed_proof","locked","preserved_human"])
def test_current_proof_or_dependency_fence_cannot_be_forged(kind):
    date=accepted_dependency()
    job,proofs=source_job(date)
    req=request(dependencies=(date[1],))
    reader=proofs.get
    if kind=="changed_pin":req=req.model_copy(update={"dependencies":(date[1].model_copy(update={"revision":2}),)})
    elif kind=="missing_proof":reader=lambda _:None
    elif kind=="crossed_proof":reader=lambda _:accepted_dependency(text="1948-04-26")[0]
    elif kind=="locked":job["fields"][str(FieldKey.DATE_VISITED_FROM)]["locked"]=True
    elif kind=="preserved_human":job["preserved_human_outcomes"]={str(FieldKey.DATE_VISITED_FROM):{"protected":True}}
    with pytest.raises(StaleWork):collecting_context_for_job(req,job,checkpoint_proof_reader=reader)


def test_distinct_accepted_events_are_not_silently_joined_for_geography():
    date=accepted_dependency()
    collector=accepted_dependency(FieldKey.COLLECTORS,"Synthetic Collector",event_id="other-event")
    job,proofs=source_job(date,collector)
    assert collecting_context_for_job(request(dependencies=(date[1],collector[1])),job,
        checkpoint_proof_reader=proofs.get) is None
