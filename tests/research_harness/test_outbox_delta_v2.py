"""Validation-only delta equivalence; no native transaction or performance claim."""
import copy

import pytest

from test_native_canonical_v2_contract import basis_v1, causal, receipt  # noqa: F401 (pytest fixtures)
from specimen_digitization.research_harness import publication_v2 as v2
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.contracts import digest


def case():
    return {"jobs":{"job":{"fields":[{"revision":1,"values":[0,1,1.0,True,-0.0,"1"]}]}},
        "outbox":{"publication":{"delivered":False,"guard":{"pins":["a","b"]}},
            "checkpoint":{"delivered":False,"receipt_ids":["receipt"]},
            "unrelated":{"delivered":False,"payload":[{"cost":12}]}},
        "budget_totals":{"held_micro_usd":17}}


def reference(state,after,publication="publication",checkpoint="checkpoint",commit=None):
    return not (v2.outbox_completion(state,publication,checkpoint,commit)!=after)


def check(state,after,publication="publication",checkpoint="checkpoint",commit=None):
    return v2.outbox_delta_matches(state,after,publication,checkpoint,commit)


def test_plain_delta_uses_comparison_view_and_preserves_inputs(monkeypatch):
    state=case();commit={"receipt":{"ids":["one"]}}
    after=v2.outbox_completion(state,"publication","checkpoint",commit)
    saved=copy.deepcopy((state,after,commit))
    def refuse(*args):
        raise AssertionError("ordinary validation must not rebuild the full state")
    monkeypatch.setattr(v2,"outbox_completion",refuse)
    assert check(state,after,commit=commit)
    assert (state,after,commit)==saved


@pytest.mark.parametrize("mutation",["job","budget","extra_root","missing_root","extra_event",
    "missing_event","other_event","checkpoint_flag","publication_flag","commit","event_guard","list_order"])
def test_every_unpermitted_delta_matches_the_full_copy_refusal(mutation):
    state=case();commit={"native":{"ids":["one","two"]}}
    after=v2.outbox_completion(state,"publication","checkpoint",commit)
    if mutation=="job":after["jobs"]["job"]["fields"][0]["revision"]=2
    if mutation=="budget":after["budget_totals"]["held_micro_usd"]=0
    if mutation=="extra_root":after["extra"]={}
    if mutation=="missing_root":del after["budget_totals"]
    if mutation=="extra_event":after["outbox"]["extra"]={"delivered":False}
    if mutation=="missing_event":del after["outbox"]["unrelated"]
    if mutation=="other_event":after["outbox"]["unrelated"]["delivered"]=True
    if mutation=="checkpoint_flag":after["outbox"]["checkpoint"]["delivered"]=False
    if mutation=="publication_flag":after["outbox"]["publication"]["delivered"]=False
    if mutation=="commit":after["outbox"]["publication"]["canonical_commit"]["native"]["ids"].append("extra")
    if mutation=="event_guard":after["outbox"]["publication"]["guard"]["pins"].append("extra")
    if mutation=="list_order":after["outbox"]["publication"]["guard"]["pins"].reverse()
    assert check(state,after,commit=commit)==reference(state,after,commit=commit)==False


@pytest.mark.parametrize("value",[True,0,1,None,"false",[],{}])
def test_pending_requires_the_false_singleton(value):
    state=case();state["outbox"]["publication"]["delivered"]=value
    for function in (reference,check):
        with pytest.raises(PublicationUnavailable,match="native_v2_outbox_not_pending"):
            function(state,{},commit={})


@pytest.mark.parametrize("malformed",["outbox","publication","checkpoint","publication_flag","checkpoint_flag","pending_and_missing"])
def test_missing_or_malformed_rows_keep_the_existing_failure_order(malformed):
    state=case()
    if malformed=="outbox":state["outbox"]=None
    if malformed=="publication":state["outbox"]["publication"]=[]
    if malformed=="checkpoint":del state["outbox"]["checkpoint"]
    if malformed=="publication_flag":del state["outbox"]["publication"]["delivered"]
    if malformed=="checkpoint_flag":del state["outbox"]["checkpoint"]["delivered"]
    if malformed=="pending_and_missing":
        state["outbox"]["publication"]["delivered"]=True
        del state["outbox"]["checkpoint"]
    for function in (reference,check):
        with pytest.raises(PublicationUnavailable,match="native_v2_outbox_unproved"):
            function(state,{},commit={})


def test_identical_keys_preserve_the_single_row_reference_behavior():
    state=case();commit={"receipt":[1]}
    after=v2.outbox_completion(state,"publication","publication",commit)
    assert check(state,after,"publication","publication",commit)==reference(state,after,"publication","publication",commit)
    assert after["outbox"]["checkpoint"]["delivered"] is False


def test_custom_string_keys_with_identical_lookups_use_the_builder_fallback(monkeypatch):
    class LookupKey(str):
        def __eq__(self,other):
            return False if type(other) is LookupKey else str.__eq__(self,other)
        __hash__=str.__hash__
    key=LookupKey("publication");state=case();commit={"receipt":[1]}
    assert key=="publication" and not (key==key)
    after=v2.outbox_completion(state,key,key,commit)
    assert after["outbox"]["publication"]["canonical_commit"]==commit
    assert reference(state,after,key,key,commit) is True
    calls=[];builder=v2.outbox_completion
    def observe(*args):
        calls.append(True)
        return builder(*args)
    monkeypatch.setattr(v2,"outbox_completion",observe)
    assert check(state,after,key,key,commit) is True
    assert calls==[True]
    assert state["outbox"]["publication"]["delivered"] is False
    assert "canonical_commit" not in state["outbox"]["publication"]


@pytest.mark.parametrize("alias",["event","outbox","nested_mutable","shared_event_keys","after_state"])
def test_aliased_mutable_shapes_use_the_full_copy_fallback(monkeypatch,alias):
    state=case();commit={"receipt":[1]}
    if alias=="event":state["mirror"]=state["outbox"]["publication"]
    if alias=="outbox":state["mirror"]=state["outbox"]
    if alias=="nested_mutable":state["mirror"]=state["jobs"]["job"]["fields"]
    if alias=="shared_event_keys":state["outbox"]["checkpoint"]=state["outbox"]["publication"]
    after=v2.outbox_completion(state,"publication","checkpoint",commit)
    if alias=="after_state":after["mirror"]=after["jobs"];state["mirror"]=copy.deepcopy(state["jobs"])
    saved=copy.deepcopy((state,after,commit));calls=[];builder=v2.outbox_completion
    def observe(*args):
        calls.append(True)
        return builder(*args)
    monkeypatch.setattr(v2,"outbox_completion",observe)
    assert check(state,after,commit=commit)==reference(state,after,commit=commit)
    assert len(calls)==2
    assert (state,after,commit)==saved
    if alias in {"event","outbox","shared_event_keys"}:
        changed=copy.deepcopy(after)
        if alias=="outbox":changed["mirror"]=copy.deepcopy(state["mirror"])
        elif alias=="event":changed["mirror"]=copy.deepcopy(state["mirror"])
        else:changed["outbox"]["checkpoint"]=copy.deepcopy(state["outbox"]["checkpoint"])
        assert check(state,changed,commit=commit)==reference(state,changed,commit=commit)==False


def test_cross_state_aliases_do_not_mutate_an_unchanged_branch():
    state=case();commit={"receipt":[1]}
    after=v2.outbox_completion(state,"publication","checkpoint",commit)
    after["jobs"]=state["jobs"]
    after["outbox"]["unrelated"]=state["outbox"]["unrelated"]
    saved=copy.deepcopy((state,after,commit))
    assert check(state,after,commit=commit)==reference(state,after,commit=commit)==True
    assert (state,after,commit)==saved


def test_key_order_and_existing_numeric_equality_are_not_new_guards():
    state=case();commit={"receipt":[1]}
    after=v2.outbox_completion(state,"publication","checkpoint",commit)
    after=dict(reversed(tuple(after.items())))
    after["outbox"]=dict(reversed(tuple(after["outbox"].items())))
    after["jobs"]["job"]["fields"][0]["values"][1]=True
    assert check(state,after,commit=commit)==reference(state,after,commit=commit)==True


def test_custom_inequality_uses_the_original_predicate():
    class Distinct(dict):
        def __eq__(self,other):return True
        def __ne__(self,other):return True
    state=case();after=v2.outbox_completion(state,"publication","checkpoint",{})
    after=Distinct(after)
    assert reference(state,after,commit={}) is False
    assert check(state,after,commit={}) is False


@pytest.mark.parametrize("location",["state","commit"])
def test_custom_metaclass_cannot_admit_a_deepcopy_changing_value(monkeypatch,location):
    class PretendJson(type):
        def __eq__(cls,other):return other is str
        __hash__=type.__hash__
    class ChangedByCopy(metaclass=PretendJson):
        def __deepcopy__(self,memo):return {"copied":True}
    value=ChangedByCopy();state=case();commit={"receipt":[1]}
    assert type(value)==str and type(value) is not str
    if location=="state":state["custom"]=value
    else:commit["custom"]=value
    after=v2.outbox_completion(state,"publication","checkpoint",commit)
    copied=after["custom"] if location=="state" else after["outbox"]["publication"]["canonical_commit"]["custom"]
    assert copied=={"copied":True}
    calls=[];builder=v2.outbox_completion
    def observe(*args):
        calls.append(True)
        return builder(*args)
    monkeypatch.setattr(v2,"outbox_completion",observe)
    assert check(state,after,commit=commit) is True
    assert calls==[True]
    assert (state if location=="state" else commit)["custom"] is value


def test_real_builder_retains_deep_isolation():
    state=case();commit={"receipt":{"ids":["one"]}}
    after=v2.outbox_completion(state,"publication","checkpoint",commit)
    after["jobs"]["job"]["fields"][0]["values"].append("changed")
    after["outbox"]["publication"]["canonical_commit"]["receipt"]["ids"].append("changed")
    assert state["jobs"]["job"]["fields"][0]["values"]==[0,1,1.0,True,-0.0,"1"]
    assert commit=={"receipt":{"ids":["one"]}}


def test_actual_receipt_transition_and_aliased_outbox_remain_valid(causal):
    state=copy.deepcopy(causal.state)
    state["outbox"]["synthetic-sibling-publication/county"]={"delivered":False}
    state["mirror"]=state["outbox"]["synthetic-sibling-publication/county"]
    value=receipt(causal,state=state)
    assert value.transition() is value
    assert value.before_state["mirror"]["delivered"] is False
    assert value.after_state["mirror"]["delivered"] is True


@pytest.mark.parametrize("mutation,code",[("before_digest","native_v2_causal_receipt_invalid"),
    ("after_digest","native_v2_causal_receipt_invalid"),("progress_digest","native_v2_causal_receipt_invalid"),
    ("chain_digest","native_v2_causal_delta_invalid"),("unrelated_delta","native_v2_causal_delta_invalid"),
    ("commit","native_v2_causal_delta_invalid"),("pending","native_v2_outbox_not_pending"),
    ("missing_checkpoint","native_v2_outbox_unproved")])
def test_actual_transition_preserves_digest_delta_and_pending_failures(causal,mutation,code):
    value=receipt(causal);updates={}
    if mutation in {"before_digest","after_digest","progress_digest","chain_digest"}:
        key={"before_digest":"before_state_digest","after_digest":"after_state_digest",
            "progress_digest":"progress_receipt_digest","chain_digest":"chain_digest"}[mutation]
        updates[key]=digest("tampered digest")
    if mutation=="unrelated_delta":
        after=copy.deepcopy(value.after_state);after["budget_totals"]["held_micro_usd"]=23
        updates.update(after_state=after,after_state_digest=digest(after))
    if mutation=="commit":updates["native_commit"]={"substituted":"receipt"}
    if mutation in {"pending","missing_checkpoint"}:
        before=copy.deepcopy(value.before_state)
        if mutation=="pending":before["outbox"][value.publication_outbox_key]["delivered"]=True
        else:del before["outbox"][value.checkpoint_outbox_key]
        updates.update(before_state=before,before_state_digest=digest(before))
    with pytest.raises(PublicationUnavailable,match=code):
        value.model_copy(update=updates).transition()
