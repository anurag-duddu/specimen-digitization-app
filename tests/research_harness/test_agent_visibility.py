"""What the owner sees in Logfire for one harness run, over the offline production rig.

One specimen's plan tick (provisioning, six named specialist agents, publication,
finalize) runs through the production composer with the worker's own
configure_production_observability (approved-content, the SDK scrubber and its
extra patterns) and an in-memory exporter beside the real processors. Nothing is
sent anywhere: sockets and httpx are refused, no token is read (a placeholder
string stands in) and the models are scripted. Label text is the public synthetic
fixture.

The spans must carry, per specialist agent: a readable description, the fields it
owns, the cost of its model requests from the effect receipts, and the run id.
The scoped research input (about 150 KB) repeats on every model request of a run;
only that repeat is capped, with an explicit marker, and only after the first
request of the run. The system prompt, the tool calls and results and the agent's
complete conversation stay whole, and the authority ids stay scrubbed.
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from specimen_digitization import observability
from specimen_digitization.research_harness.contracts import ROLE_FIELDS, SpecialistRole

from production_e2e_support import (
    WORKER, fixture_source_transport, research_state, scripted_model_factory,
)

SCOPED_INPUT = "Immutable scoped research input"
SCRUBBED = "[Scrubbed due to 'auth']"
# The authority id GEOLocate's recorded Chicago candidate carries
# (test_production_e2e.CHICAGO); it must never reach an exported span unscrubbed.
CHICAGO_AUTHORITY = "geolocate:79a9389b0ba6bcaf"
PRODUCTION_ENV = {
    "APP_ENV": "production", "LOGFIRE_CAPTURE_MODE": "approved-content", "LOGFIRE_SEND_TO_LOGFIRE": "true",
    "LOGFIRE_SERVICE_NAME": "specimen-worker", "LOGFIRE_HEAD_SAMPLE_RATE": "1.0",
    "LOGFIRE_DISTRIBUTED_TRACING": "true", "LOGFIRE_TOKEN": "offline-placeholder-not-a-credential",
}


class Span:
    def __init__(self, raw):
        context = raw.get_span_context()
        self.name = raw.name
        self.id = context.span_id
        self.parent = raw.parent.span_id if raw.parent is not None else None
        self.attrs = dict(raw.attributes or {})

    def __repr__(self):
        return f"Span({self.name!r})"


def keys(value):
    """A span attribute holding a list: a JSON string (logfire spans) or a sequence (OTel)."""
    return json.loads(value) if isinstance(value, str) else list(value)


def messages(span):
    return json.loads(span.attrs["gen_ai.input.messages"])


def scoped_text(span):
    first = messages(span)[0]["parts"][0]
    assert first["type"] == "text"
    return first["content"]


@pytest.fixture(scope="module")
def tick(tmp_path_factory):
    """The research plan tick of one synthetic specimen, spans collected in memory."""
    import httpx
    import logfire
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelRequest, UserPromptPart
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.usage import RequestUsage

    import test_production_e2e as T
    from specimen_digitization.research_harness.workflow_bridge import compose_production_research_workflow

    patch = pytest.MonkeyPatch()
    exporter = InMemorySpanExporter()
    real_configure = logfire.configure
    previous_default = Agent._instrument_default

    def configure_offline(**options):
        # The production call, kept whole, except that nothing can leave the process.
        options.pop("token", None)
        options["send_to_logfire"] = False
        options["additional_span_processors"] = [SimpleSpanProcessor(exporter)]
        advanced = options.get("advanced")
        options["advanced"] = logfire.AdvancedOptions(
            exception_callback=getattr(advanced, "exception_callback", None))
        return real_configure(**options)

    def refuse(*args, **kwargs):
        raise AssertionError("the offline visibility test performs no HTTP")

    for key in list(os.environ):
        if key.startswith(("OTEL_", "SPECIMEN_TRACE_")) or key in {
                "LOGFIRE_BASE_URL", "LOGFIRE_ENVIRONMENT", "LOGFIRE_SERVICE_VERSION"}:
            patch.delenv(key, raising=False)
    for key, value in PRODUCTION_ENV.items():
        patch.setenv(key, value)
    patch.setattr(httpx.AsyncClient, "send", refuse)
    patch.setattr(httpx.Client, "send", refuse)
    patch.setattr(observability, "_service_version", lambda: "0" * 40)
    patch.setattr(observability, "_configured_settings", None)
    patch.setattr(observability, "_bounded_runtime", None)
    patch.setattr(logfire, "configure", configure_offline)
    try:
        observability.configure_production_observability("specimen-worker")
        tmp = tmp_path_factory.mktemp("visibility")
        generator = T.build_rig(tmp)
        rig = next(generator)
        received = []
        base = scripted_model_factory(rig.model_calls)
        counter = {"n": 0}

        def factory(request, binding):
            inner = base(request, binding).function

            def spy(history, info):
                first = next(part for message in history if isinstance(message, ModelRequest)
                             for part in message.parts if isinstance(part, UserPromptPart))
                received.append((str(request.role), len(first.content)))
                response = inner(history, info)
                # A different price for each request, so a cost attributed to the wrong
                # span cannot match by accident.
                counter["n"] += 1
                response.usage = RequestUsage(input_tokens=1_000 * counter["n"], output_tokens=100 * counter["n"])
                return response
            return FunctionModel(spy)

        workflow = compose_production_research_workflow(rig.ordinary, repository=rig.repository,
            environ=T.SWITCH_ON, actor_uid=WORKER, state_backend=rig.backend, model_factory=factory,
            source_transport=fixture_source_transport(rig.source_urls), blobs=rig.research_blobs)
        parsed = T.to_plan(workflow, rig)
        exporter.clear()
        with T.supervised():
            specimen = workflow.step(rig.principal, rig.specimen_id)
        assert (specimen.run.stage, specimen.run.disposition) == ("finalized", "needs_human_review")
        _, state = research_state(rig.fake, rig.specimen_id)
        spans = [Span(raw) for raw in exporter.get_finished_spans()]
        next(generator, None)
        yield SimpleNamespace(spans=spans, run_id=parsed.run.id, state=state, received=received,
                              job_id=f"{parsed.run.id}-r3")
    finally:
        patch.undo()
        Agent._instrument_default = previous_default
        real_configure(send_to_logfire=False, console=False)


def named(tick, prefix):
    return [span for span in tick.spans if span.name.startswith(prefix)]


def agents(tick):
    found = {span.name.removeprefix("invoke_agent "): span for span in named(tick, "invoke_agent ")}
    assert set(found) == {role.value for role in SpecialistRole}
    return found


def chats_of(tick, role):
    by_id = {span.id: span for span in tick.spans}
    agent_id = agents(tick)[role.value].id
    return [span for span in tick.spans if span.name.startswith("chat ") and span.parent == agent_id
            and by_id[span.parent].attrs["gen_ai.agent.name"] == role.value]


def receipts(tick):
    return {effect_id: effect for effect_id, effect in tick.state["effects"].items()
            if effect["operation_key"].startswith("model:")}


# ---- the agents --------------------------------------------------------------------

def test_the_rig_is_the_six_role_ten_request_tick(tick):
    assert len(named(tick, "invoke_agent ")) == 6 and len(named(tick, "chat ")) == 10
    assert len({span.attrs.get("research.job_id") for span in tick.spans
                if "research.job_id" in span.attrs}) == 1


def test_each_expert_agent_span_carries_a_readable_description_and_its_owned_fields(tick):
    descriptions = []
    for role in SpecialistRole:
        span = agents(tick)[role.value]
        description = span.attrs["gen_ai.agent.description"]
        descriptions.append(description)
        owned = [key.value for key in ROLE_FIELDS[role]]
        assert role.value.removeprefix("specimen_") in description.lower()
        assert all(key in description for key in owned), description
        assert 0 < len(description) <= 400
        assert keys(span.attrs["research.field_keys"]) == owned
    assert len(set(descriptions)) == 6


def test_the_specialist_span_names_the_role_fields_too(tick):
    inner = [span for span in named(tick, "research_harness.specialist") if "research.field_keys" in span.attrs]
    assert {span.attrs["research.role"] for span in inner} == {role.value for role in SpecialistRole}
    for span in inner:
        assert keys(span.attrs["research.field_keys"]) == [
            key.value for key in ROLE_FIELDS[SpecialistRole(span.attrs["research.role"])]]


# ---- cost from the receipts ----------------------------------------------------------

def test_cost_on_the_model_chat_agent_and_specialist_spans_equals_the_receipts(tick):
    effects = receipts(tick)
    assert len(effects) == 10 and len({effect["actual_micro_usd"] for effect in effects.values()}) == 10
    by_id = {span.id: span for span in tick.spans}
    model_spans = named(tick, "research_harness.model")
    assert len(model_spans) == 10
    for model in model_spans:
        cost = effects[model.attrs["research.effect_id"]]["actual_micro_usd"]
        assert model.attrs["research.cost_micro_usd"] == cost
        chat = by_id[model.parent]
        assert chat.name.startswith("chat ") and chat.attrs["research.cost_micro_usd"] == cost
    for role in SpecialistRole:
        total = sum(effect["actual_micro_usd"] for effect in effects.values()
                    if effect["operation_key"].startswith(f"model:{role.value}"))
        assert total > 0
        assert agents(tick)[role.value].attrs["research.cost_micro_usd"] == total
        specialist = [span for span in named(tick, "research_harness.specialist")
                      if span.attrs.get("research.role") == role.value and "research.field_keys" in span.attrs]
        assert [span.attrs["research.cost_micro_usd"] for span in specialist] == [total]
    assert sum(agents(tick)[role.value].attrs["research.cost_micro_usd"] for role in SpecialistRole) == sum(
        effect["actual_micro_usd"] for effect in effects.values())


def test_no_request_is_reported_unknown_when_every_receipt_has_a_cost(tick):
    assert not [span for span in tick.spans if "research.cost_unknown_requests" in span.attrs]


# ---- the run id ----------------------------------------------------------------------

def test_the_run_id_is_on_every_app_agent_and_chat_span_and_matches_the_job_id(tick):
    harness = named(tick, "research_harness.")
    pydantic = named(tick, "invoke_agent ") + named(tick, "chat ")
    assert len(harness) == 51 and len(pydantic) == 16
    for span in harness + pydantic:
        assert span.attrs["specimen.run.id"] == tick.run_id, span.name
    assert {span.attrs["research.job_id"] for span in harness} == {tick.job_id}
    assert tick.job_id == f"{tick.run_id}-r3"


def test_no_user_identity_or_secret_rides_the_new_attributes(tick):
    new = ("specimen.run.id", "research.field_keys", "research.cost_micro_usd", "gen_ai.agent.description")
    for span in tick.spans:
        for key in new:
            if key in span.attrs:
                value = json.dumps(span.attrs[key]).lower()
                assert WORKER not in value and "@" not in value and "token" not in value


# ---- the repeated scoped input -------------------------------------------------------

def test_the_model_always_receives_the_complete_scoped_input(tick):
    assert len(tick.received) == 10 and min(size for _, size in tick.received) > 100_000


def test_only_the_repeat_of_the_scoped_input_is_capped_and_the_first_request_stays_whole(tick):
    for role in SpecialistRole:
        chats = chats_of(tick, role)
        assert chats
        first = scoped_text(chats[0])
        assert first.startswith(SCOPED_INPUT) and len(first) > 100_000 and "[truncated" not in first
        for later in chats[1:]:
            capped = scoped_text(later)
            head = first[:200]
            assert capped.startswith(head + " ... [truncated ") and len(capped) < 1_000
            removed = len(first.encode()) - len(head.encode())
            assert f"[truncated {removed} bytes:" in capped
            # Only that one text part changed shape: the same messages follow it, whole.
            assert [m["role"] for m in messages(later)][0] == "user"


def test_tool_calls_and_results_in_a_capped_request_are_whole(tick):
    chats = chats_of(tick, SpecialistRole.TAXONOMY)
    assert len(chats) == 4
    history = [messages(chat) for chat in chats]
    for earlier, later in zip(history[1:], history[2:]):
        assert later[1:len(earlier)] == earlier[1:]
    calls = [part for message in history[3][1:] for part in message["parts"] if part["type"] == "tool_call"]
    results = [part for message in history[3][1:] for part in message["parts"]
               if part["type"] == "tool_call_response"]
    assert len(calls) == len(results) == 3
    assert all(part["name"] == "lookup_source" and "query_text" in json.dumps(part["arguments"]) for part in calls)
    assert all(len(json.dumps(part["result"])) > 1_000 and "[truncated" not in json.dumps(part["result"])
               for part in results)
    assert "[truncated" not in json.dumps([part for message in history[3][1:] for part in message["parts"]])


def test_the_system_prompt_and_the_complete_conversation_stay_whole(tick):
    for role in SpecialistRole:
        agent = agents(tick)[role.value]
        prompt = agent.attrs["gen_ai.system_instructions"]
        assert f"Owned fields: {', '.join(key.value for key in ROLE_FIELDS[role])}." in prompt
        for chat in chats_of(tick, role):
            assert chat.attrs["gen_ai.system_instructions"] == prompt
        conversation = agent.attrs["pydantic_ai.all_messages"]
        assert "[truncated" not in conversation
        first_user = json.loads(conversation)[0]["parts"][0]["content"]
        assert first_user.startswith(SCOPED_INPUT) and len(first_user) > 100_000


def test_tool_spans_keep_their_arguments_and_results(tick):
    tools = named(tick, "execute_tool ")
    assert len(tools) == 7
    for span in tools:
        assert "query_text" in span.attrs["gen_ai.tool.call.arguments"]
        assert len(span.attrs["gen_ai.tool.call.result"]) > 500


def test_attribute_bytes_no_longer_grow_with_each_model_request(tick):
    # Each role keeps two complete copies (its first request and its conversation); the
    # four repeats (taxonomy three, geography one) are a few KB of tool history each.
    inputs = [len(span.attrs["gen_ai.input.messages"]) for span in tick.spans if span.name.startswith("chat ")]
    assert len(inputs) == 10 and len([size for size in inputs if size > 100_000]) == 6
    assert sum(inputs) < 6.5 * max(inputs), inputs


# ---- what must not change ------------------------------------------------------------

def test_authority_ids_are_still_scrubbed_by_the_sdk(tick):
    results = named(tick, "execute_tool ")
    assert any(SCRUBBED in span.attrs["gen_ai.tool.call.result"] for span in results)
    assert any(SCRUBBED in span.attrs.get("final_result", "") for span in named(tick, "invoke_agent "))
    for span in results:
        result = span.attrs["gen_ai.tool.call.result"]
        assert CHICAGO_AUTHORITY not in result
        for candidate in json.loads(result).get("candidate_json", []):
            assert json.loads(candidate)["authority_id"] == SCRUBBED
    for span in named(tick, "invoke_agent "):
        assert CHICAGO_AUTHORITY not in span.attrs["final_result"]
    assert any("auth" in span.attrs.get("logfire.scrubbed", "") for span in tick.spans)
