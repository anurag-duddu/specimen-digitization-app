"""The first-pass route bounds GLM-5.3-Flash's hidden reasoning on Novita.

From 2026-10-12 03:00 to 2026-10-18 14:45 UTC, 29 of the 141 `chat
zai-org/GLM-5.3-Flash` spans in Logfire stopped at the 4,096-token output cap
with finish reason "length", and 26 of the 119 first-pass runs ended with no
answer: Novita counts the model's hidden reasoning in its output tokens. Novita
honours the OpenAI-style `reasoning_effort` request field for this model. In
the 2026-10-18 probes no first pass sent with "medium" or "low" stopped at the
cap, and scored against reference readings "medium" decided the most labels
rightly (HARNESS.md section 5, "The first pass's reasoning bound"). The route
sends `reasoning_effort: medium` in every request, through the gateway's model
settings, and the first pass records it with the call's parameters. These tests
drive the real gateway and `first_pass_direct` over an offline HTTP transport:
no live model request is made.
"""

import io
import json

import httpx
import pytest
from huggingface_hub.hf_api import InferenceProviderMapping
from huggingface_hub.inference._providers._common import (
    HARDCODED_MODEL_INFERENCE_MAPPING,
)
from huggingface_hub.utils import _http as hf_http
from PIL import Image

from specimen_digitization.application import first_pass as first_pass_module
from specimen_digitization.application import workflow as workflow_module
from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import ExecutionPolicy, Profile, Run
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.model_gateway import (
    HUGGINGFACE_ROUTES,
    INITIAL_HUGGINGFACE_ROUTES,
    HuggingFaceModelGateway,
)

from test_first_pass import INCOMPLETE, MUSE, QWEN, REGION, VALID, pinned_route, reading

ROUTE = HUGGINGFACE_ROUTES["first-pass-glm"]
BOUND = {"reasoning_effort": "medium"}


def png(width, height):
    output = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="PNG")
    return output.getvalue()


def offline_provider(monkeypatch, route, answers):
    """Serve the route's model from these answers in turn, each a tool call to the
    request's one output tool; return the request bodies the client sent."""
    monkeypatch.setitem(
        HARDCODED_MODEL_INFERENCE_MAPPING,
        route.provider,
        {
            route.model_id: InferenceProviderMapping(
                provider=route.provider,
                hf_model_id=route.model_id,
                providerId=route.model_id,
                status="live",
                task="conversational",
            )
        },
    )
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        answer = answers[min(len(sent), len(answers)) - 1]
        tool = body["tools"][0]["function"]["name"]
        call = {"id": f"call_{len(sent)}", "type": "function",
                "function": {"name": tool, "arguments": json.dumps(answer)}}
        return httpx.Response(200, json={
            "id": "completion", "object": "chat.completion", "created": 0,
            "model": route.model_id, "system_fingerprint": "fixture",
            "choices": [{"index": 0, "finish_reason": "tool_calls", "logprobs": None,
                         "message": {"role": "assistant", "content": None, "tool_calls": [call]}}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 150, "total_tokens": 1050},
        })

    monkeypatch.setattr(
        hf_http,
        "_GLOBAL_ASYNC_CLIENT_FACTORY",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return sent


def test_the_first_pass_route_asks_novita_for_medium_reasoning():
    assert (ROUTE.model_id, ROUTE.provider) == ("zai-org/GLM-5.3-Flash", "novita")
    assert dict(ROUTE.request_options) == BOUND
    # Only the first pass's route carries a request option.
    for route_id in (*INITIAL_HUGGINGFACE_ROUTES, "harness-deepseek"):
        assert HUGGINGFACE_ROUTES[route_id].request_options == ()


def test_every_first_pass_request_carries_the_bound_and_the_call_records_it(
    monkeypatch, tmp_path
):
    # The first answer is refused (one verdict of three), so the output retry
    # is a second request: both carry the bound.
    sent = offline_provider(monkeypatch, ROUTE, [INCOMPLETE, VALID])
    monkeypatch.setenv("HF_TOKEN", "synthetic-test-credential")
    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    monkeypatch.setattr(workflow_module, "crop_bytes", lambda *args: png(60, 40))
    prices = published_registry().resolve("insects").profile.processing.price_list
    run = Run(
        profile=Profile(
            first_pass_route=ROUTE.route_id,
            execution=ExecutionPolicy(price_list=prices.model_dump(mode="json")),
        ),
        dependencies=pinned_route(ROUTE.route_id),
    )
    readings = [reading("handwriting-qwen", QWEN), reading("handwriting-muse", MUSE)]

    from types import SimpleNamespace

    decision = first_pass_module.first_pass_direct(
        SimpleNamespace(blobs=LocalBlobs(tmp_path)),
        SimpleNamespace(asset=SimpleNamespace(id="asset-1"), run=run),
        REGION,
        readings,
    )

    assert len(sent) == 2
    assert [body["reasoning_effort"] for body in sent] == ["medium", "medium"]
    assert [body["max_tokens"] for body in sent] == [4_096, 4_096]
    assert decision.selected_observation_id == readings[1].id
    assert decision.call.parameters == {"extra_body": BOUND, "max_tokens": 4_096}


@pytest.mark.parametrize("route_id", sorted(INITIAL_HUGGINGFACE_ROUTES))
def test_a_reader_route_sends_no_request_option(monkeypatch, route_id):
    from pydantic import BaseModel
    from pydantic_ai import Agent

    class Reading(BaseModel):
        text: str

    route = HUGGINGFACE_ROUTES[route_id]
    sent = offline_provider(monkeypatch, route, [{"text": "ok"}])
    agent = Agent(HuggingFaceModelGateway(token="hf_test").model_for(route_id), output_type=Reading)

    agent.run_sync("Read it.")

    assert "reasoning_effort" not in sent[0]
    assert "extra_body" not in sent[0]
