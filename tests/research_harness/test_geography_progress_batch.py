"""Equivalent owned progress views with one official persisted tool envelope."""

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage
from pydantic_ai_harness.step_persistence import InMemoryStepStore

from specimen_digitization.application.domain import FieldValue, LookupStatus
from specimen_digitization.research_harness.agents import (
    ResearchDeps, SpecialistHarness, SpecialistOutput, _geography_progress, _geography_progress_all,
)
from specimen_digitization.research_harness.contracts import (
    FieldKey, FieldResolution, ROLE_FIELDS, SpecialistRole, WorkState,
)
from specimen_digitization.research_harness.prompts import (
    GEOGRAPHY_PROGRESS_PROMPT_VERSION, GEOGRAPHY_RESEARCH_PROMPT_VERSION,
)

from prompt_test_fixtures import retained_text
from test_geography_strategy import attempt, request
from test_research_harness_agents import model, requests, sql_broker


def pinned_request(version):
    req = requests()[SpecialistRole.GEOGRAPHY]
    if version == GEOGRAPHY_RESEARCH_PROMPT_VERSION:
        text = retained_text(req.role, 9)
        req = req.model_copy(update={"prompt": req.prompt.model_copy(update={
            "version": version, "text": text, "digest": hashlib.sha256(text.encode()).hexdigest()})})
    return req


class AvailableSources:
    def __init__(self):
        self.requested = []

    def available_sources(self, req):
        assert len(req.field_keys) == 1
        self.requested.append(req.field_keys[0])
        return ("geolocate", "nga") if req.field_keys[0] == FieldKey.CITY else ("geolocate",)


def test_batch_has_the_exact_individual_views_and_retains_historical_sibling_attempts():
    req = pinned_request(GEOGRAPHY_PROGRESS_PROMPT_VERSION)
    city = request()
    history = [attempt(city, "geolocate"), attempt(city, "nga"),
        attempt(city, "geolocate", status=LookupStatus.TIMEOUT)]
    tools = AvailableSources()
    deps = ResearchDeps({req.role: req}, tools)
    deps.source_attempts[req.role] = history
    expected = {str(key): _geography_progress(deps, req, key).as_dict() for key in req.field_keys}
    tools.requested.clear()
    assert _geography_progress_all(deps, req) == expected
    assert tools.requested == list(req.field_keys)
    assert deps.source_attempts[req.role] is history and len(history) == 3
    assert expected["city"]["state"] == "waiting_source"


def test_batch_uses_one_retained_history_snapshot_even_if_availability_appends_history():
    req = pinned_request(GEOGRAPHY_PROGRESS_PROMPT_VERSION)
    city = request()
    original = [attempt(city, "geolocate")]
    deps = ResearchDeps({req.role: req}, AvailableSources())
    deps.source_attempts[req.role] = list(original)
    expected = {str(key): _geography_progress(deps, req, key, attempts=tuple(original)).as_dict()
        for key in req.field_keys}

    class ChangedAvailability(AvailableSources):
        def available_sources(self, narrowed):
            deps.source_attempts[req.role].append(attempt(city, "nga"))
            return super().available_sources(narrowed)

    deps.tool_broker = ChangedAvailability()
    assert _geography_progress_all(deps, req) == expected
    assert len(deps.source_attempts[req.role]) == len(original) + len(req.field_keys)


def test_narrowed_batch_returns_only_requested_owned_fields_without_backend_reads():
    req = pinned_request(GEOGRAPHY_PROGRESS_PROMPT_VERSION).model_copy(update={
        "field_keys": (FieldKey.PROVINCE_STATE, FieldKey.CITY)})
    tools = AvailableSources()
    tools.store = SimpleNamespace(_read=lambda *args: pytest.fail("A local progress view must not read SQL"))
    views = _geography_progress_all(ResearchDeps({req.role: req}, tools), req)
    assert tuple(views) == ("province_state", "city")
    assert tools.requested == list(req.field_keys)


@pytest.mark.parametrize("change", [
    {"role": SpecialistRole.TAXONOMY},
    {"field_keys": (FieldKey.TAXON,)},
    {"field_keys": (FieldKey.CITY, FieldKey.CITY)},
    {"field_keys": ()},
])
def test_batch_refuses_unowned_or_malformed_requests_before_source_selection(change):
    req = pinned_request(GEOGRAPHY_PROGRESS_PROMPT_VERSION).model_copy(update=change)
    tools = AvailableSources()
    with pytest.raises(ValueError, match="geography_progress_outside_requested_field"):
        _geography_progress_all(ResearchDeps({req.role: req}, tools), req)
    assert tools.requested == []


@pytest.mark.parametrize("version,tool_name,count", [
    (GEOGRAPHY_RESEARCH_PROMPT_VERSION, "geography_progress", 5),
    (GEOGRAPHY_PROGRESS_PROMPT_VERSION, "geography_progress_all", 1),
])
def test_exact_v9_and_v10_tool_rosters_and_official_journal_envelopes(tmp_path, version, tool_name, count):
    req = pinned_request(version)
    store, scope, lease, broker = sql_broker(tmp_path)
    records, tools, returned, rosters = InMemoryStepStore(), AvailableSources(), {}, []

    def respond(messages, info):
        rosters.append({tool.name: tool.sequential for tool in info.function_tools})
        returns = [part for message in messages for part in message.parts
            if isinstance(part, ToolReturnPart) and part.tool_name == tool_name]
        if not returns:
            calls = ([ToolCallPart(tool_name, {"field_key": str(key)}, tool_call_id=f"progress-{key}")
                for key in req.field_keys] if count == 5 else
                [ToolCallPart(tool_name, {}, tool_call_id="progress-all")])
            return ModelResponse(calls, usage=RequestUsage(input_tokens=10, output_tokens=8))
        returned.update({part.tool_call_id: part.content for part in returns})
        output = SpecialistOutput(role=req.role, resolutions=tuple(FieldResolution(field_key=key,
            work_state=WorkState.WAITING_SOURCE, value=FieldValue(), reason="synthetic source prerequisite")
            for key in req.field_keys))
        return ModelResponse([ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"),
            tool_call_id="final-result")], usage=RequestUsage(input_tokens=10, output_tokens=8))

    runtime = SpecialistHarness(requests={req.role: req}, tool_broker=tools,
        model_factory=lambda request: model(FunctionModel(respond), request=request,
            broker=broker, scope=scope, lease=lease), step_store_factory=lambda _: records)
    result = asyncio.run(runtime.run_specialist(req.role))
    # A one-role harness has no sibling to delegate to; the full six-role
    # roster (including delegate_task) is covered by test_research_harness_agents.
    expected_tools = {"lookup_source", "invoke_utility", tool_name, "geography_hierarchy"}
    assert all(set(roster) == expected_tools and roster[tool_name] for roster in rosters), rosters
    events = asyncio.run(records.list_events(run_id=result.native_run_id))
    assert len([event for event in events if event.kind == "tool_call_started"
        and event.tool_name == tool_name]) == count
    assert len([event for event in events if event.kind == "tool_call_completed"
        and event.tool_name == tool_name]) == count
    expected = {str(key): _geography_progress(ResearchDeps({req.role: req}, AvailableSources()), req, key).as_dict()
        for key in req.field_keys}
    actual = (returned["progress-all"] if count == 1 else
        {str(key): returned[f"progress-{key}"] for key in req.field_keys})
    assert json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert result.source_results == () and store.budget(scope)["held_micro_usd"] == 0


def test_new_prompt_keeps_v9_bytes_and_every_other_scientific_instruction():
    root = Path("src/specimen_digitization/research_harness/prompts")
    old = (root / "specimen_geography-v9.txt").read_bytes()
    assert hashlib.sha256(old).hexdigest() == "5a347f42cb62138985458db0626d78810ebadada4dd1487c9f2edf3ae19f3017"  # pragma: allowlist secret
    before = "strategy if one is available. geography_progress(field_key) lists retained query\ndigests, evidence, next permitted sources and legitimate stop reasons without a\nprovider call."
    after = "strategy if one is available. Call geography_progress_all() once for all\nrequest.field_keys: its keyed field views list the same retained query digests,\nevidence, next permitted sources and legitimate stop reasons without a provider\ncall. Do not request five separate progress calls; one batch retains the same\nper-field strategy and evidence checks within one journal/tool envelope."
    assert (root / "specimen_geography-v10.txt").read_text() == old.decode().replace(before, after)
    assert pinned_request(GEOGRAPHY_PROGRESS_PROMPT_VERSION).prompt.version != GEOGRAPHY_RESEARCH_PROMPT_VERSION
    assert set(pinned_request(GEOGRAPHY_PROGRESS_PROMPT_VERSION).field_keys) == set(ROLE_FIELDS[SpecialistRole.GEOGRAPHY])
