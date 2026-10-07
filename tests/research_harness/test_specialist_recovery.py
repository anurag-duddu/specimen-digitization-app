"""Native message recovery over actual local step stores and source captures."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage
from pydantic_ai_harness.step_persistence import ContinuableSnapshot, RunRecord, StepEvent, ToolEffectRecord
from pydantic_ai_harness import SubAgent, SubAgents

from specimen_digitization.research_harness.agents import _research_input
from specimen_digitization.research_harness.contracts import FieldKey, SourceQuery, SpecialistRole
from specimen_digitization.research_harness.package_qualification import SERIALIZATION_VERSION
from specimen_digitization.research_harness.persistence import DurableEffectBroker, HeldUnknown, SqlConnectStepStore
from specimen_digitization.research_harness.recovery import RecoveryUnavailable, ResumeDelegationBudget, load_specialist_recovery

from test_geolocate_capture import RECORDED_BODY, make_rig


def setup(tmp_path):
    rig = make_rig(tmp_path, [RECORDED_BODY])
    rig.steps = SqlConnectStepStore(rig.store, rig.durable_scope, rig.blobs, agent_name=str(rig.request.role))
    rig.query = SourceQuery(source_id="geolocate", field_key=FieldKey.CITY,
        query_text=json.dumps({"country": "Guatemala", "state": "Chimaltenango", "locality": "Yepocapa", "place": "Yepocapa", "value": "Yepocapa"}))
    rig.result = asyncio.run(rig.broker.query_source(rig.request, rig.query))
    return rig


def metadata(rig):
    return {"job_id": rig.request.scope.job_id, "generation": str(rig.request.scope.generation),
        "prompt_digest": rig.request.prompt.digest, "serialization_version": SERIALIZATION_VERSION}


def messages(rig):
    return [ModelRequest([UserPromptPart(_research_input(rig.request))]),
        ModelResponse([ToolCallPart("lookup_source", {"query": rig.query.model_dump(mode="json")}, "lookup-1")],
                      usage=RequestUsage(input_tokens=17, output_tokens=12)),
        ModelRequest([ToolReturnPart("lookup_source", rig.result.model_dump(mode="json"), "lookup-1")])]


def seed(rig, *, run_id="failed-1", completed=False, active=False, prior_requests=2,
         prior_tools=1, content=None, changed_metadata=None, unresolved_tool=False, timestamp=None):
    async def write():
        conversation = f"job:1:{rig.request.role}"
        await rig.steps.register_run(RunRecord(run_id=run_id, conversation_id=conversation,
            agent_name=str(rig.request.role), metadata=changed_metadata or metadata(rig),
            started_at=timestamp or datetime.now(timezone.utc)))
        kinds = ["run_started"] + ["model_request_started"] * prior_requests + ["tool_call_started"] * prior_tools
        if not active:
            kinds += ["run_completed" if completed else "run_failed"]
        for index, kind in enumerate(kinds):
            await rig.steps.append_event(StepEvent(run_id=run_id, kind=kind, step_index=index))
        await rig.steps.save_snapshot(ContinuableSnapshot(run_id=run_id, step_index=5,
            conversation_id=conversation, agent_name=str(rig.request.role), state="interrupted",
            messages=content if content is not None else messages(rig)))
        if unresolved_tool:
            await rig.steps.record_tool_effect(ToolEffectRecord(run_id=run_id,
                tool_call_id="lookup-1", tool_name="lookup_source", status="started"))
    asyncio.run(write())


def recover(rig, **kwargs):
    return asyncio.run(load_specialist_recovery(rig.steps, rig.request,
        input_text=_research_input(rig.request), serialization_version=SERIALIZATION_VERSION,
        request_limit=kwargs.pop("request_limit", 8), tool_calls_limit=kwargs.pop("tool_calls_limit", 12), **kwargs))


def test_failed_frontier_rehydrates_source_proof_and_consumes_previous_limits(tmp_path):
    rig = setup(tmp_path)
    seed(rig)
    restored = recover(rig)
    assert restored.prior_run_id == "failed-1" and restored.source_results == (rig.result,)
    assert restored.source_attempts[0].query == rig.query and restored.source_attempts[0].result == rig.result
    assert (restored.usage.requests, restored.usage.tool_calls) == (2, 1)
    assert (restored.usage.input_tokens, restored.usage.output_tokens) == (17, 12)
    assert restored.messages[-1].parts[0].content == rig.result.model_dump(mode="json")
    # A resumed identical source query uses the captured effect; recovery itself
    # only reads bytes and never sends a provider request.
    assert asyncio.run(rig.broker.query_source(rig.request, rig.query)) == rig.result
    assert len(rig.calls) == 1


def test_completed_run_is_never_reopened(tmp_path):
    rig = setup(tmp_path)
    seed(rig, completed=True)
    assert recover(rig) is None and len(rig.calls) == 1


def test_new_active_run_prevents_falling_back_to_older_failed_run(tmp_path):
    rig = setup(tmp_path)
    earlier = datetime.now(timezone.utc) - timedelta(seconds=10)
    seed(rig, timestamp=earlier)
    seed(rig, run_id="active-2", active=True)
    with pytest.raises(RecoveryUnavailable, match="not_failed"):
        recover(rig)


@pytest.mark.parametrize("change", ["prompt", "input", "source", "query"])
def test_changed_recovery_provenance_is_refused(tmp_path, change):
    rig = setup(tmp_path)
    frontier = messages(rig)
    changed = None
    if change == "prompt":
        changed = {**metadata(rig), "prompt_digest": "f" * 64}
    elif change == "input":
        frontier[0].parts[0] = UserPromptPart("Immutable scoped research input changed")
    elif change == "source":
        frontier[-1].parts[0].content["candidate_json"] = ('{"field_key":"city","value":"Atlantis"}',)
    elif change == "query":
        frontier[1].parts[0].args["query"]["query_text"] = "other place"
    seed(rig, content=frontier, changed_metadata=changed)
    with pytest.raises(RecoveryUnavailable):
        recover(rig)
    assert len(rig.calls) == 1


def test_unsettled_tool_frontier_cannot_resume(tmp_path):
    rig = setup(tmp_path)
    seed(rig, content=messages(rig)[:-1])
    with pytest.raises(HeldUnknown, match="unsettled_tool"):
        recover(rig)


def test_unresolved_native_tool_record_cannot_resume(tmp_path):
    rig = setup(tmp_path)
    seed(rig, unresolved_tool=True)
    with pytest.raises(HeldUnknown, match="native_tool"):
        recover(rig)


def test_unknown_application_send_blocks_history_without_reissuing(tmp_path):
    rig = setup(tmp_path)
    seed(rig)
    async def lost(*args):
        raise OSError("fixture provider interrupted")
    broker = DurableEffectBroker(rig.store, rig.blobs)
    with pytest.raises(OSError):
        asyncio.run(broker.execute(rig.durable_scope, rig.broker.effects.lease, "prior-unknown", {}, 1,
            lost, field_keys=(str(FieldKey.COUNTRY),)))
    with pytest.raises(HeldUnknown, match="reconciliation"):
        recover(rig)
    assert len(rig.calls) == 1


@pytest.mark.parametrize("limit", ["requests", "tools"])
def test_failed_request_and_tool_counts_cannot_reset_on_resume(tmp_path, limit):
    rig = setup(tmp_path)
    seed(rig, prior_requests=3, prior_tools=2)
    with pytest.raises(RecoveryUnavailable, match="usage_limit_exhausted"):
        recover(rig, request_limit=3 if limit == "requests" else 8,
                tool_calls_limit=2 if limit == "tools" else 12)


def test_prior_same_conversation_run_usage_is_counted_once(tmp_path):
    rig = setup(tmp_path)
    seed(rig, timestamp=datetime.now(timezone.utc) - timedelta(seconds=10))
    seed(rig, run_id="failed-2", prior_requests=3, prior_tools=2)
    restored = recover(rig)
    assert restored.prior_run_id == "failed-2"
    assert (restored.usage.requests, restored.usage.tool_calls) == (5, 3)


def with_delegate(frontier, *, call_id="delegate-old", target=SpecialistRole.TAXONOMY, args=None):
    return [*frontier, ModelResponse([ToolCallPart("delegate_task", args if args is not None else {
        "agent_name": str(target), "task": "Use the captured scoped context"}, call_id)]),
        ModelRequest([ToolReturnPart("delegate_task", "Captured helper result", call_id)])]


def test_recovery_deduplicates_prior_delegations_in_full_resume_prefix(tmp_path):
    rig = setup(tmp_path)
    first = with_delegate(messages(rig))
    seed(rig, content=first, prior_tools=2, timestamp=datetime.now(timezone.utc) - timedelta(seconds=10))
    second = with_delegate(first, call_id="delegate-party", target=SpecialistRole.PARTIES)
    seed(rig, run_id="failed-2", content=second, prior_tools=2)
    restored = recover(rig)
    assert dict(restored.delegate_counts) == {str(SpecialistRole.TAXONOMY): 1, str(SpecialistRole.PARTIES): 1}
    assert len(rig.calls) == 1


def test_delegate_identity_cannot_be_reused_for_a_changed_task(tmp_path):
    rig = setup(tmp_path)
    seed(rig, content=with_delegate(messages(rig)), prior_tools=2,
         timestamp=datetime.now(timezone.utc) - timedelta(seconds=10))
    changed = with_delegate(messages(rig), args={"agent_name": str(SpecialistRole.TAXONOMY), "task": "A different task"})
    seed(rig, run_id="failed-2", content=changed, prior_tools=2)
    with pytest.raises(RecoveryUnavailable, match="delegate_call_identity_changed"):
        recover(rig)


@pytest.mark.parametrize("args", [{"task": "scope"}, {"agent_name": 3, "task": "scope"},
    {"agent_name": "other-helper", "task": "scope"}, {"agent_name": str(SpecialistRole.TAXONOMY), "task": None},
    {"agent_name": str(SpecialistRole.GEOGRAPHY), "task": "scope"},
    {"agent_name": str(SpecialistRole.TAXONOMY), "task": "scope", "shell": "whoami"}])
def test_malformed_retained_delegation_never_grants_fresh_allowance(tmp_path, args):
    rig = setup(tmp_path)
    seed(rig, content=with_delegate(messages(rig), args=args), prior_tools=2)
    with pytest.raises(RecoveryUnavailable, match="delegate_"):
        recover(rig)


def test_started_delegate_missing_from_captured_history_refuses_recovery(tmp_path):
    rig = setup(tmp_path)
    seed(rig)
    async def add_missing():
        await rig.steps.append_event(StepEvent(run_id="failed-1", kind="tool_call_started", step_index=10,
            tool_name="delegate_task", tool_call_id="missing-delegate"))
        await rig.steps.append_event(StepEvent(run_id="failed-1", kind="run_failed", step_index=11))
    asyncio.run(add_missing())
    with pytest.raises(RecoveryUnavailable, match="delegate_started_history_missing"):
        recover(rig)


def test_real_subagent_dispatch_is_blocked_when_recovered_helper_allowance_is_used(tmp_path):
    rig = setup(tmp_path)
    seed(rig, content=with_delegate(messages(rig)), prior_tools=2)
    recovered = recover(rig)
    helper_calls, root_calls = [], []
    def helper_model(messages, info):
        helper_calls.append(messages)
        return ModelResponse([TextPart("A new helper response should never run")])
    def root_model(messages, info):
        root_calls.append(messages)
        if any(isinstance(part, ToolReturnPart) and part.content == "specialist_operational_failure: helper_call_limit_exhausted"
               for message in messages for part in message.parts):
            return ModelResponse([TextPart("Use the captured helper result")])
        return ModelResponse([ToolCallPart("delegate_task", {"agent_name": str(SpecialistRole.TAXONOMY),
            "task": "Research again"}, "delegate-after-resume")])
    helper = Agent(FunctionModel(helper_model), name=str(SpecialistRole.TAXONOMY))
    delegation = SubAgents(agents=[SubAgent(helper, name=str(SpecialistRole.TAXONOMY), max_calls=1)],
        agent_folders=None, tool_retries=0)
    root = Agent(FunctionModel(root_model), name=str(rig.request.role), capabilities=[delegation])
    guard = ResumeDelegationBudget(rig.request, delegate_counts=recovered.delegate_counts, max_calls=1)
    result = asyncio.run(root.run("Continue scoped work", message_history=recovered.messages,
        deps=SimpleNamespace(for_agent=lambda name: rig.request), capabilities=[guard]))
    assert result.output == "Use the captured helper result" and helper_calls == []
    assert len(root_calls) == 2
    assert any("helper_call_limit_exhausted" in str(part)
        for message in root_calls[1] for part in message.parts)
    assert len(rig.calls) == 1


def test_real_subagent_dispatch_spends_only_remaining_allowance_even_in_one_batch(tmp_path):
    rig = setup(tmp_path)
    helper_calls = []
    def helper_model(messages, info):
        helper_calls.append(messages)
        return ModelResponse([TextPart("One remaining helper result")])
    def root_model(messages, info):
        if any(isinstance(part, ToolReturnPart) and part.content == "specialist_operational_failure: helper_call_limit_exhausted"
               for message in messages for part in message.parts):
            return ModelResponse([TextPart("Use the retained and newly captured evidence")])
        return ModelResponse([ToolCallPart("delegate_task", {"agent_name": str(SpecialistRole.TAXONOMY),
            "task": "Scoped remaining call"}, f"delegate-new-{index}") for index in (1, 2)])
    helper = Agent(FunctionModel(helper_model), name=str(SpecialistRole.TAXONOMY))
    root = Agent(FunctionModel(root_model), name=str(rig.request.role), capabilities=[SubAgents(
        agents=[SubAgent(helper, name=str(SpecialistRole.TAXONOMY), max_calls=2)], agent_folders=None, tool_retries=0)])
    result = asyncio.run(root.run("Continue scoped work", deps=SimpleNamespace(for_agent=lambda name: rig.request),
        capabilities=[ResumeDelegationBudget(rig.request, delegate_counts=((str(SpecialistRole.TAXONOMY), 1),), max_calls=2)]))
    assert result.output == "Use the retained and newly captured evidence" and len(helper_calls) == 1


def test_delegation_resume_guard_cannot_be_attached_to_another_role(tmp_path):
    rig = setup(tmp_path)
    called = []
    def respond(messages, info):
        called.append(1)
        return ModelResponse([TextPart("wrong role")])
    agent = Agent(FunctionModel(respond), name=str(SpecialistRole.TAXONOMY))
    with pytest.raises(PermissionError, match="request_or_role_changed"):
        asyncio.run(agent.run("wrong", deps=SimpleNamespace(for_agent=lambda name: rig.request),
            capabilities=[ResumeDelegationBudget(rig.request, delegate_counts=(), max_calls=1)]))
    assert called == []
