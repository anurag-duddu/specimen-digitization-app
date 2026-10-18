"""A completed parse settles at the tokens its extraction reported.

Production, the 11-specimen batch of 2026-10-17: every run's `parse` (agent
insects_bounded_extractor, Qwen/Qwen3-VL-30B-A3B-Instruct on the
handwriting-qwen route, provider novita) completed with one request, and every
one was recorded at its whole reservation: 58,164 micro-dollars, cost basis
"reserved", usage null, 639,804 in all. Their tokens in Logfire, at the route's
0.20 and 0.70 per million, come to 11,005; specimen 19f0f1f6's answered 1,627
in and 1,077 out, 1,080.

The tokens never reached the meter. The extraction answers through Pydantic
AI's output tool, and after that answer the agent queues the tool's return as
one more request, which nothing sends. `reliability.reported_usage` counted it
as a request sent and not answered, so it called the spend unknown.

These drive the real isolated model child (`model_runtime.invoke_model`) with an
offline provider, in the lab of `test_extraction_recovery.py` (the published
pilot profile's prices and pins, both ledgers wired as production wires them).
No live model request is made.
"""

import os
from pathlib import Path

from specimen_digitization.application.lane_costs import model_cost
from specimen_digitization.application.storage import LocalBlobs

from test_extraction_recovery import ExtractionLab, extraction_findings, parse_calls
from test_lane_routes import PARSE_RESERVATION
from test_rate_limit_refusal import lab, requests, research_state

ANSWER = "SPECIMEN_TEST_PROVIDER_ANSWER"
# 19f0f1f6's extraction, one request (Logfire, 2026-10-17).
REPORTED = (1_627, 1_077)


def answering_model_child(payload):
    """The isolated model child, with a provider whose extraction answers.

    It answers with no candidates, in one request. `reported` reports
    19f0f1f6's tokens; `no_input_tokens` reports its output tokens alone, as
    Pydantic AI records an answer whose provider sent no prompt count. Each
    request is counted in a file beside the blobs.
    """
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.usage import RequestUsage

    from specimen_digitization.application import production
    from specimen_digitization.application.model_runtime import model_child
    from specimen_digitization.model_gateway import HUGGINGFACE_ROUTES

    input_tokens, output_tokens = REPORTED
    if os.environ[ANSWER] == "no_input_tokens":
        input_tokens = 0
    sent = Path(payload["storage"]["root"]).parent / f"requests-{payload['operation']}"

    class Gateway:
        def __init__(self, timeout_seconds=None):
            self.routes = dict(HUGGINGFACE_ROUTES)

        def route(self, route_id):
            return self.routes[route_id]

        def model_for(self, route_id):
            def respond(messages, info):
                with sent.open("a") as requests:
                    requests.write(route_id + "\n")
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            info.output_tools[0].name, {"candidates": [], "unresolved": []}
                        )
                    ],
                    usage=RequestUsage(input_tokens=input_tokens, output_tokens=output_tokens),
                    finish_reason="stop",
                )

            return FunctionModel(respond, model_name="local-provider")

    production.HuggingFaceModelGateway = Gateway
    return model_child(payload)


def answered_parse(tmp_path, monkeypatch, answer):
    """The lab run, drained once, whose one extraction goes to the child."""
    monkeypatch.setenv(ANSWER, answer)
    adapters = ExtractionLab(LocalBlobs(tmp_path / "blobs"), extracts=1)
    adapters.model_effect = answering_model_child
    workflow, principal, ident, backend = lab(tmp_path, monkeypatch, adapters, "none")
    return workflow.drain(principal, ident), backend


def test_a_completed_parse_settles_at_the_tokens_its_provider_reported(tmp_path, monkeypatch):
    specimen, backend = answered_parse(tmp_path, monkeypatch, "reported")

    run = specimen.run
    prices = run.profile.execution.price_list
    cost = model_cost(prices, "handwriting-qwen", *REPORTED)
    assert cost == 1_080
    assert run.attempts["parse"] == 1 and requests(tmp_path, "extract") == 1
    assert "parse" in run.completed_steps and extraction_findings(run) == []
    # Before: (1, "completed", "reserved", 58,164, None), usage None.
    assert parse_calls(run) == [(1, "completed", "computed", cost, None)]
    [call] = [c for c in run.paid_calls if c["step"] == "parse"]
    assert (call["kind"], call["route_id"], call["usage"]) == (
        "model",
        "handwriting-qwen",
        {"input_tokens": 1_627, "output_tokens": 1_077},
    )
    assert call["reserved_micros"] == PARSE_RESERVATION
    # The run's budget and the shared research ledger both settle to its cost.
    settled = {"reserved_micros": PARSE_RESERVATION, "settled_micros": cost}
    assert run.dependencies["ordinary_cost_settlements"]["parse:1"] == settled
    assert research_state(backend, specimen)["ordinary_reservations"]["parse:1"] == settled


def test_a_completed_parse_whose_provider_reported_no_input_tokens_stays_held(
    tmp_path, monkeypatch
):
    # Its spend is unknown, so its whole reservation stays held: over, never under.
    specimen, backend = answered_parse(tmp_path, monkeypatch, "no_input_tokens")

    run = specimen.run
    assert run.attempts["parse"] == 1 and requests(tmp_path, "extract") == 1
    assert "parse" in run.completed_steps and extraction_findings(run) == []
    assert parse_calls(run) == [(1, "completed", "reserved", PARSE_RESERVATION, None)]
    [call] = [c for c in run.paid_calls if c["step"] == "parse"]
    assert call["usage"] is None
    assert "parse:1" not in run.dependencies.get("ordinary_cost_settlements", {})
    assert research_state(backend, specimen)["ordinary_reservations"]["parse:1"] == {
        "reserved_micros": PARSE_RESERVATION,
        "settled_micros": None,
    }
    # A held liability is not a measured actual.
    assert run.usage.actual_cost_micros is None
