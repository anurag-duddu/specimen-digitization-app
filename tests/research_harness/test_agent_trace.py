"""The run-scoped trace state of a specialist agent: cap of a repeated input, request costs."""
import json

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from specimen_digitization.research_harness import agent_trace as A

BIG = "Immutable scoped research input: " + "x" * 5_000


def messages_json(*messages):
    return json.dumps(list(messages), ensure_ascii=False, separators=(",", ":"))


def user(*parts):
    return {"role": "user", "parts": list(parts)}


def text(content):
    return {"type": "text", "content": content}


def test_the_first_copy_is_returned_unchanged_and_an_identical_repeat_is_marked():
    run = A.RunTrace()
    first = messages_json(user(text(BIG)))
    assert run.cap_repeated_input(first) == first
    capped = json.loads(run.cap_repeated_input(messages_json(user(text(BIG)))))
    content = capped[0]["parts"][0]["content"]
    head = BIG[:A.REPEATED_INPUT_HEAD_CHARS]
    removed = len(BIG.encode()) - len(head.encode())
    assert content.startswith(head + " ... [truncated ") and f"[truncated {removed} bytes:" in content
    assert len(content) < 500


def test_the_byte_count_is_utf8_bytes_not_characters():
    run = A.RunTrace()
    multibyte = ("Immutable " + chr(0xE9) + chr(0xE8) + chr(0xFC) + " ") * 600
    once = messages_json(user(text(multibyte)))
    assert run.cap_repeated_input(once) == once
    content = json.loads(run.cap_repeated_input(once))[0]["parts"][0]["content"]
    head = multibyte[:A.REPEATED_INPUT_HEAD_CHARS]
    assert f"[truncated {len(multibyte.encode()) - len(head.encode())} bytes:" in content
    assert len(multibyte.encode()) > len(multibyte)


def test_a_new_long_text_a_short_text_and_every_other_part_are_never_capped():
    run = A.RunTrace()
    other = BIG.replace("x", "y")
    call = {"type": "tool_call", "id": "1", "name": "lookup_source", "arguments": {"query_text": BIG}}
    result = {"type": "tool_call_response", "id": "1", "name": "lookup_source", "result": {"status": BIG}}
    history = messages_json(
        user(text(BIG)), {"role": "assistant", "parts": [call, text(BIG)]}, user(result), user(text("short repeat")))
    run.cap_repeated_input(history)
    again = json.loads(run.cap_repeated_input(history))
    # The scoped input repeats and is marked; the assistant's text, the tool call, the tool
    # result and the short text are untouched, and so is a different long text.
    assert "[truncated " in again[0]["parts"][0]["content"]
    assert again[1]["parts"] == [call, text(BIG)]
    assert again[2]["parts"] == [result]
    assert again[3]["parts"] == [text("short repeat")]
    assert json.loads(run.cap_repeated_input(messages_json(user(text(other)))))[0]["parts"][0]["content"] == other


def test_a_run_starts_with_nothing_seen_and_a_delegated_run_does_not_share_the_parents():
    with A.run_scope() as parent:
        parent.cap_repeated_input(messages_json(user(text(BIG))))
        with A.run_scope() as child:
            assert A.current_run() is child and child is not parent
            whole = messages_json(user(text(BIG)))
            assert child.cap_repeated_input(whole) == whole
        assert A.current_run() is parent
        assert "[truncated " in parent.cap_repeated_input(messages_json(user(text(BIG))))
    assert A.current_run() is None


@pytest.mark.parametrize("broken", ["not json", "{}", "[1, 2]", '[{"role":"user","parts":[{"type":"text","content":7}]}]'])
def test_an_attribute_it_cannot_read_is_recorded_as_it_came(broken):
    assert A.RunTrace().cap_repeated_input(broken) == broken


def test_costs_are_per_run_and_a_request_outside_a_run_is_ignored():
    A.record_request_cost(5)
    with A.run_scope() as outer:
        A.record_request_cost(3)
        with A.run_scope() as inner:
            A.record_request_cost(4)
            A.record_request_cost(None)
        A.record_request_cost(2)
    assert (outer.requests, inner.requests) == ([3, 2], [4, None])
    assert (outer.cost_micro_usd, outer.unknown_requests) == (5, 0)
    assert (inner.cost_micro_usd, inner.unknown_requests) == (4, 1)


def test_cost_metadata_sums_the_priced_requests_and_counts_the_rest():
    assert A.cost_metadata([3, 3]) == {"cost_micro_usd": 6}
    assert A.cost_metadata([3, None]) == {"cost_micro_usd": 3, "cost_unknown_requests": 1}
    assert A.cost_metadata([None]) == {"cost_unknown_requests": 1}
    assert A.cost_metadata([0]) == {"cost_micro_usd": 0}
    assert A.cost_metadata([]) == {}


def test_annotate_cost_sets_allowlisted_metadata_and_swallows_only_a_refused_value():
    from specimen_digitization.research_harness.telemetry import ResearchTrace, TraceIdentity

    trace = ResearchTrace(TraceIdentity("specimen-test", "run-1-r1", 0))
    span = FakeSpan()
    A.annotate_cost(trace, span, [3, None])
    assert span.attributes == {"research.cost_micro_usd": 3, "research.cost_unknown_requests": 1}
    refused = FakeSpan()
    A.annotate_cost(trace, refused, [10**10])
    assert refused.attributes == {}

    class Broken:
        @staticmethod
        def annotate(span, **metadata):
            raise RuntimeError("not a refused value")

    with pytest.raises(RuntimeError):
        A.annotate_cost(Broken(), FakeSpan(), [1])


class FakeSpan:
    def __init__(self):
        self.attributes = {}

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def set_attributes(self, attributes):
        self.attributes.update(attributes)


def record(settings, history):
    span = FakeSpan()
    settings.handle_messages(history, ModelResponse(parts=[TextPart("ok")]), span)
    return json.loads(span.attributes["gen_ai.input.messages"]), span.attributes


@pytest.mark.parametrize("configured", [True, False])
def test_the_harness_settings_keep_the_capture_flags_of_agent_instrumentation(monkeypatch, configured):
    from pydantic_ai.models.instrumented import InstrumentationSettings

    from specimen_digitization import provider_privacy

    monkeypatch.setattr(provider_privacy, "approved_content_configured", lambda: configured)
    base = provider_privacy.agent_instrumentation()
    capped = provider_privacy.agent_instrumentation(A.RepeatCappedInstrumentationSettings)
    assert type(base) is InstrumentationSettings
    assert type(capped) is A.RepeatCappedInstrumentationSettings
    flags = ("include_content", "include_binary_content", "include_model_request_parameters", "version")
    assert [getattr(capped, flag) for flag in flags] == [getattr(base, flag) for flag in flags]
    assert capped.include_content is configured and capped.include_binary_content is False


def test_outside_a_run_scope_the_settings_record_exactly_what_the_base_class_does():
    from pydantic_ai.models.instrumented import InstrumentationSettings

    options = dict(include_content=True, include_binary_content=False, include_model_request_parameters=False,
                   version=5)
    capped, base = A.RepeatCappedInstrumentationSettings(**options), InstrumentationSettings(**options)
    history = [ModelRequest([UserPromptPart(BIG)])]
    for _ in range(2):
        assert record(capped, history) == record(base, history)


def test_inside_a_run_scope_with_content_on_the_repeat_is_marked_through_the_settings():
    options = dict(include_content=True, include_binary_content=False, include_model_request_parameters=False,
                   version=5)
    settings = A.RepeatCappedInstrumentationSettings(**options)
    history = [ModelRequest([UserPromptPart(BIG)])]
    with A.run_scope():
        first, _ = record(settings, history)
        second, attributes = record(settings, history)
    assert first[0]["parts"][0]["content"] == BIG
    assert second[0]["parts"][0]["content"].startswith(BIG[:A.REPEATED_INPUT_HEAD_CHARS] + " ... [truncated ")
    assert history[0].parts[0].content == BIG
    assert "gen_ai.output.messages" in attributes
