"""Bounded recovery from failed native runs, without repeating unsettled effects.

Messages are a frontier, not scientific authority. Source results are restored
only from canonical captured receipts (or deterministic utility replay). Usage
starts at the conservative prior boundary counts, including failed requests.
"""
from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_ai.usage import RunUsage
from pydantic_ai_harness.step_persistence import StepStore

from .contracts import SourceQuery, SourceResult, SpecialistRequest, SpecialistRole, digest
from .persistence import BlobRef, HeldUnknown, SqlConnectStepStore, StaleWork
from .sources import SourceBroker, SourceRegistry, result_envelope

MAX_RECOVERY_RUNS = 32
MAX_RECOVERY_MESSAGES = 128
MAX_RECOVERY_BYTES = 1_000_000


class RecoveryUnavailable(RuntimeError):
    """An unsafe frontier must be reconciled rather than resumed as fresh work."""


@dataclass(frozen=True)
class RecoveredSourceAttempt:
    query: SourceQuery
    result: SourceResult


@dataclass(frozen=True)
class RecoveryContext:
    messages: tuple[ModelMessage, ...]
    source_results: tuple[SourceResult, ...]
    source_attempts: tuple[RecoveredSourceAttempt, ...]
    conversation_id: str
    prior_run_id: str
    usage: RunUsage
    delegate_counts: tuple[tuple[str, int], ...] = ()


def _delegate_target(args, request):
    """Only the reviewed named-helper contract can consume this allowance."""
    if (not isinstance(args, dict) or not {"agent_name", "task"} <= set(args)
            or set(args) - {"agent_name", "task", "model"}
            or not isinstance(args["agent_name"], str) or not isinstance(args["task"], str)
            or args.get("model") is not None and not isinstance(args["model"], str)):
        raise RecoveryUnavailable("recovery_delegate_arguments_invalid")
    try:
        target = SpecialistRole(args["agent_name"])
    except ValueError:
        raise RecoveryUnavailable("recovery_delegate_target_not_reviewed") from None
    if target == request.role:
        raise RecoveryUnavailable("recovery_delegate_target_not_reviewed")
    return str(target)


def _delegate_calls(messages, request):
    calls = {}
    for message in messages:
        if not isinstance(message, ModelResponse):
            continue
        for part in message.parts:
            if not isinstance(part, ToolCallPart) or part.tool_name != "delegate_task":
                continue
            try:
                arguments = part.args_as_dict()
                target = _delegate_target(arguments, request)
            except (TypeError, ValueError):
                raise RecoveryUnavailable("recovery_delegate_arguments_invalid") from None
            if not isinstance(part.tool_call_id, str) or not part.tool_call_id:
                raise RecoveryUnavailable("recovery_delegate_call_identity_missing")
            identity = (target, digest({"agent_name": target, "task": arguments["task"], "model": arguments.get("model")}))
            if part.tool_call_id in calls and calls[part.tool_call_id] != identity:
                raise RecoveryUnavailable("recovery_delegate_call_identity_changed")
            calls[part.tool_call_id] = identity
    return calls


class ResumeDelegationBudget(AbstractCapability):
    """Restore per-helper call ceilings before the official SubAgents dispatch.

    This capability adds no tool and confers no new authority. Use it on the
    recovered root's ``Agent.run(capabilities=[...])``; the official per-run
    SubAgents limit still applies as well.
    """

    def __init__(self, request: SpecialistRequest, *,
                 delegate_counts: Mapping[str, int] | Sequence[tuple[str, int]], max_calls: int):
        if type(max_calls) is not int or max_calls < 1:
            raise ValueError("recovery_delegate_positive_limit_required")
        entries = list(delegate_counts.items() if isinstance(delegate_counts, Mapping) else delegate_counts)
        if len({name for name, _ in entries}) != len(entries):
            raise ValueError("recovery_delegate_count_duplicate")
        for name, count in entries:
            if (name not in {str(role) for role in SpecialistRole if role != request.role}
                    or type(count) is not int or count < 0):
                raise ValueError("recovery_delegate_count_invalid")
        self.id = "resume-delegation-budget-" + str(request.role)
        self.request = request
        self.prior_counts = MappingProxyType(dict(entries))
        self.max_calls = max_calls
        self._used, self._seen = {}, set()

    def _check(self, ctx):
        if (ctx.agent.name != str(self.request.role)
                or ctx.deps.for_agent(ctx.agent.name) != self.request):
            raise PermissionError("recovery_delegate_request_or_role_changed")

    async def for_run(self, ctx):
        self._check(ctx)
        materialized = copy.copy(self)
        materialized._used, materialized._seen = {}, set()
        return materialized

    async def wrap_tool_execute(self, ctx, *, call, tool_def, args, handler):
        if tool_def.name != "delegate_task":
            return await handler(args)
        self._check(ctx)
        target = _delegate_target(args, self.request)
        if call.tool_call_id in self._seen:
            raise RecoveryUnavailable("recovery_delegate_call_identity_reused")
        self._seen.add(call.tool_call_id)
        # No await between checking and incrementing: concurrent calls of one
        # model response cannot race past the remaining per-target allowance.
        used = self.prior_counts.get(target, 0) + self._used.get(target, 0)
        if used >= self.max_calls:
            # A legitimate spent allowance is an ordinary contained outcome,
            # not an argument retry. Production deliberately has zero tool
            # retries; ModelRetry here would discard valid retained progress.
            return "specialist_operational_failure: helper_call_limit_exhausted"
        self._used[target] = self._used.get(target, 0) + 1
        return await handler(args)


def _metadata(request, serialization_version):
    return {"job_id": request.scope.job_id, "generation": str(request.scope.generation),
            "prompt_digest": request.prompt.digest, "serialization_version": serialization_version}


def _complete_calls(messages):
    pending, seen, completed = {}, set(), []
    for message in messages:
        if isinstance(message, ModelResponse):
            if message.state != "complete":
                raise RecoveryUnavailable("recovery_partial_model_response")
            for part in message.parts:
                if isinstance(part, ToolCallPart):
                    if part.tool_call_id in seen:
                        raise RecoveryUnavailable("recovery_duplicate_open_tool_call")
                    seen.add(part.tool_call_id)
                    pending[part.tool_call_id] = part
        elif isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, ToolReturnPart) and part.tool_call_id not in pending:
                    raise RecoveryUnavailable("recovery_orphan_tool_result")
                if isinstance(part, (ToolReturnPart, RetryPromptPart)) and part.tool_call_id in pending:
                    call = pending.pop(part.tool_call_id)
                    if part.tool_name != call.tool_name:
                        raise RecoveryUnavailable("recovery_tool_result_identity_changed")
                    if isinstance(part, ToolReturnPart) and part.outcome == "interrupted":
                        raise HeldUnknown("recovery_tool_result_interrupted")
                    if isinstance(part, ToolReturnPart) and part.outcome == "success":
                        completed.append((call, part))
    if pending:
        raise HeldUnknown("recovery_frontier_has_unsettled_tool_calls")
    return completed


async def verify_durable_source_result(store: SqlConnectStepStore, request: SpecialistRequest,
                                       result: SourceResult, *, query: SourceQuery | None = None) -> SourceResult:
    """Rehydrate the exact source result from immutable application capture bytes."""
    receipt = result.receipt
    if (receipt is None or receipt.scope != request.scope or receipt.effect_status != "completed"
            or receipt.field_keys != (result.coverage.field_key,) or result.coverage.field_key not in request.field_keys
            or receipt.source_id != result.coverage.source_id or receipt.outcome != result.status
            or receipt.result_json is None or receipt.held_micro_usd or receipt.settled_micro_usd is None):
        raise RecoveryUnavailable("recovery_source_receipt_not_scoped")
    effect = await asyncio.to_thread(store.store.effect, store.scope, receipt.effect_id)
    saved = effect["receipt"]
    if (effect["scope"] != store.scope.identity() or effect["status"] != "completed" or saved is None
            or saved["actual_micro_usd"] is None or saved["held_micro_usd"] or saved["outcome"] != "completed"
            or effect["field_keys"] != [str(result.coverage.field_key)]
            or effect["request_digest"] != receipt.request_digest or effect["binding_digest"] != receipt.binding_digest
            or tuple(attempt["attempt_id"] for attempt in effect["attempts"]) != receipt.attempt_ids
            or saved["capture"]["locator"] != receipt.capture_locator
            or saved["capture"]["sha256"] != receipt.response_digest
            or saved["actual_micro_usd"] != receipt.settled_micro_usd):
        raise RecoveryUnavailable("recovery_source_effect_changed")
    data = await asyncio.to_thread(store.blobs.get, BlobRef(**saved["capture"]))
    envelope = json.loads(data)
    expected = {"scope": store.scope.identity(), "effect_id": receipt.effect_id,
                "attempt_id": saved["attempt_id"], "request_digest": receipt.request_digest,
                "binding_digest": receipt.binding_digest}
    if any(envelope.get(key) != value for key, value in expected.items()):
        raise RecoveryUnavailable("recovery_source_capture_changed")
    if query is not None:
        if not saved["raw_capture"]:
            raise RecoveryUnavailable("recovery_original_source_request_capture_required")
        original = json.loads(await asyncio.to_thread(store.blobs.get, BlobRef(**saved["raw_capture"])))
        if (original.get("original_request") != request.model_dump(mode="json")
                or original.get("query") != query.model_dump(mode="json")
                or original.get("effect_id") != receipt.effect_id
                or original.get("binding_digest") != receipt.binding_digest
                or original.get("attempt_id") != saved["attempt_id"]):
            raise RecoveryUnavailable("recovery_original_source_query_changed")
    authoritative = SourceResult.model_validate(envelope["result"]["typed_payload"])
    if authoritative.receipt is not None or authoritative.model_dump(mode="json") != saved["typed_payload"]:
        raise RecoveryUnavailable("recovery_source_capture_payload_changed")
    authoritative = authoritative.model_copy(update={"receipt": receipt})
    if result_envelope(authoritative) != receipt.result_json:
        raise RecoveryUnavailable("recovery_source_semantics_changed")
    # Settlement tools have a compact presentation, retained separately from
    # their canonical source/utility result. Reuse exactly the existing view.
    from .agents import utility_model_view

    if result not in (authoritative, utility_model_view(authoritative)):
        raise RecoveryUnavailable("recovery_source_model_view_changed")
    return authoritative


async def _restore_sources(store, request, pairs, verifier):
    from .agents import utility_model_view

    sources, attempts = [], []
    for call, returned in pairs:
        if call.tool_name not in {"lookup_source", "invoke_utility"}:
            continue
        try:
            content = returned.content
            if isinstance(content, str):
                content = json.loads(content)
            result = SourceResult.model_validate(content)
            arguments = call.args_as_dict()
        except (ValueError, TypeError, KeyError):
            raise RecoveryUnavailable("recovery_source_content_or_arguments_invalid") from None
        if call.tool_name == "lookup_source":
            if set(arguments) != {"query"}:
                raise RecoveryUnavailable("recovery_source_arguments_changed")
            try:
                query = SourceQuery.model_validate(arguments["query"])
            except (ValueError, TypeError):
                raise RecoveryUnavailable("recovery_source_query_invalid") from None
            if (query.field_key not in request.field_keys or result.coverage.field_key != query.field_key
                    or result.coverage.source_id != query.source_id or result.coverage.query_digest != digest(query)):
                raise RecoveryUnavailable("recovery_source_query_changed")
            if verifier is not None:
                authoritative = await verifier(request, result)
            elif isinstance(store, SqlConnectStepStore):
                authoritative = await verify_durable_source_result(store, request, result, query=query)
            else:
                raise RecoveryUnavailable("recovery_source_capture_verifier_required")
            attempts.append(RecoveredSourceAttempt(query, authoritative))
        else:
            if set(arguments) != {"tool_id", "arguments"} or result.receipt is not None:
                raise RecoveryUnavailable("recovery_utility_arguments_changed")
            # The reviewed utility roster performs only pure request-bound work;
            # this source broker has no transport and cannot perform a lookup.
            authoritative = await SourceBroker(SourceRegistry(())).invoke_utility(
                request, arguments["tool_id"], arguments["arguments"])
            if result not in (authoritative, utility_model_view(authoritative)):
                raise RecoveryUnavailable("recovery_utility_replay_changed")
        if authoritative.coverage.field_key not in request.field_keys:
            raise RecoveryUnavailable("recovery_source_verifier_returned_wrong_scope")
        sources.append(authoritative)
    return tuple(sources), tuple(attempts)


async def load_specialist_recovery(store: StepStore, request: SpecialistRequest, *, input_text: str,
                                    serialization_version: str, request_limit: int, tool_calls_limit: int,
                                    conversation_id: str | None = None,
                                    verify_source_result: Callable[[SpecialistRequest, SourceResult], Awaitable[SourceResult]] | None = None
                                    ) -> RecoveryContext | None:
    """Return a failed root run's complete frontier and spent usage, or no prior run.

    A completed run is never reopened. Missing, active, mismatched or unknown
    state raises rather than erasing history. Callers pass ``usage`` back to
    ``Agent.run`` with their ordinary limits; recovery grants no new allowance.
    """
    request = SpecialistRequest.model_validate(request.model_dump(mode="json"))
    conversation_id = conversation_id or f"{request.scope.job_id}:{request.scope.generation}:{request.role.value}"
    records = await store.list_runs(conversation_id=conversation_id)
    if len(records) > MAX_RECOVERY_RUNS:
        raise RecoveryUnavailable("recovery_run_bound_exceeded")
    roots = [record for record in records if record.parent_run_id is None and record.agent_name == str(request.role)]
    if not roots:
        return None
    record = max(roots, key=lambda value: value.started_at)
    retained = await store.get_run(run_id=record.run_id)
    if retained != record or any(record.metadata.get(key) != value for key, value in _metadata(request, serialization_version).items()):
        raise RecoveryUnavailable("recovery_run_pins_changed")
    events = await store.list_events(run_id=record.run_id)
    if events and events[-1].kind == "run_completed":
        return None
    if not events or events[-1].kind != "run_failed":
        raise RecoveryUnavailable("recovery_run_is_not_failed")
    if await store.list_unresolved_tool_effects(run_id=record.run_id):
        raise HeldUnknown("recovery_native_tool_effect_unresolved")
    # Native SQL StepStore refuses even an interrupted read while any sending
    # or held effect remains. Never turn that refusal into fresh history.
    snapshot = await store.latest_snapshot(run_id=record.run_id, include_interrupted=True)
    if snapshot is None:
        raise RecoveryUnavailable("recovery_failed_run_has_no_frontier")
    if (snapshot.run_id != record.run_id or snapshot.agent_name != str(request.role)
            or snapshot.parent_run_id is not None or snapshot.conversation_id != conversation_id
            or len(snapshot.messages) > MAX_RECOVERY_MESSAGES):
        raise RecoveryUnavailable("recovery_frontier_scope_or_bound_changed")
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    messages = copy.deepcopy(snapshot.messages)
    if len(ModelMessagesTypeAdapter.dump_json(messages)) > MAX_RECOVERY_BYTES:
        raise RecoveryUnavailable("recovery_frontier_byte_bound_exceeded")
    inputs = [part.content for message in messages if isinstance(message, ModelRequest)
              for part in message.parts if isinstance(part, UserPromptPart)
              and isinstance(part.content, str) and part.content.startswith("Immutable scoped research input")]
    if not inputs or any(value != input_text for value in inputs):
        raise RecoveryUnavailable("recovery_exact_research_input_changed")
    if isinstance(store, SqlConnectStepStore):
        job = await asyncio.to_thread(store.store.job, store.scope)
        document = await asyncio.to_thread(store.store._read, store.scope)
        if any(effect["scope"] == store.scope.identity() and effect["receipt"] is not None
               and effect["actual_micro_usd"] is None for effect in document.state["effects"].values()):
            raise HeldUnknown("recovery_application_effect_cost_unreconciled")
        pins = job["pins"]
        if (any(value != getattr(request.scope, key) for key, value in store.scope.identity().items())
                or store.scope.sensitive != request.scope.sensitive
                or pins["input_digest"] != request.scope.input_digest
                or digest(pins["profile"]) != request.scope.profile_digest
                or pins["prompts"].get(str(request.role)) != request.prompt.model_dump(mode="json")
                or any(job["fields"][str(key)]["locked"] or job["fields"][str(key)]["revision"] != request.field_revisions.get(key, 0)
                       for key in request.field_keys)):
            raise StaleWork("recovery_job_request_or_field_changed")
    pairs = _complete_calls(messages)
    sources, attempts = await _restore_sources(store, request, pairs, verify_source_result)
    delegate_calls = _delegate_calls(messages, request)
    usage = RunUsage()
    for message in messages:
        if isinstance(message, ModelResponse):
            usage.incr(message.usage)
    started_requests, started_tools = 0, 0
    for prior in records:
        if prior.agent_name != str(request.role):
            continue
        if any(prior.metadata.get(key) != value for key, value in _metadata(request, serialization_version).items()):
            raise RecoveryUnavailable("recovery_prior_usage_pins_changed")
        prior_events = await store.list_events(run_id=prior.run_id)
        started_requests += sum(event.kind == "model_request_started" for event in prior_events)
        started_tools += sum(event.kind == "tool_call_started" for event in prior_events)
        if prior.parent_run_id is not None:
            continue
        if prior.run_id == record.run_id:
            prior_calls = _delegate_calls(messages, request)
        else:
            previous = await store.latest_snapshot(run_id=prior.run_id, include_interrupted=True)
            if previous is None:
                prior_calls = {}
            else:
                if (previous.run_id != prior.run_id or previous.agent_name != str(request.role)
                        or previous.parent_run_id is not None or previous.conversation_id != conversation_id
                        or len(previous.messages) > MAX_RECOVERY_MESSAGES
                        or len(ModelMessagesTypeAdapter.dump_json(previous.messages)) > MAX_RECOVERY_BYTES):
                    raise RecoveryUnavailable("recovery_delegate_history_scope_or_bound_changed")
                prior_inputs = [part.content for message in previous.messages if isinstance(message, ModelRequest)
                    for part in message.parts if isinstance(part, UserPromptPart)
                    and isinstance(part.content, str) and part.content.startswith("Immutable scoped research input")]
                if not prior_inputs or any(value != input_text for value in prior_inputs):
                    raise RecoveryUnavailable("recovery_delegate_history_input_changed")
                prior_calls = _delegate_calls(previous.messages, request)
        for event in prior_events:
            if event.kind == "tool_call_started" and event.tool_name == "delegate_task" and event.tool_call_id not in prior_calls:
                raise RecoveryUnavailable("recovery_delegate_started_history_missing")
        for call_id, identity in prior_calls.items():
            if call_id in delegate_calls and delegate_calls[call_id] != identity:
                raise RecoveryUnavailable("recovery_delegate_call_identity_changed")
            delegate_calls[call_id] = identity
    # Response usage cannot include failed requests; event starts are the
    # conservative boundary. Helpers of this role in the same conversation
    # count as well; unrelated role stores do not.
    usage.requests = max(usage.requests, started_requests)
    usage.tool_calls = max(len(pairs), started_tools)
    if usage.requests >= request_limit or usage.tool_calls >= tool_calls_limit:
        raise RecoveryUnavailable("recovery_prior_usage_limit_exhausted")
    counts = tuple((target, sum(value[0] == target for value in delegate_calls.values()))
                   for target in sorted({value[0] for value in delegate_calls.values()}))
    return RecoveryContext(tuple(messages), sources, attempts, conversation_id, record.run_id, usage, counts)
