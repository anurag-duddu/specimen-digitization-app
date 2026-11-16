"""The first-pass route bounds GLM-5.3-Flash's hidden reasoning on Novita.

From 2026-10-12 03:00 to 2026-10-18 14:45 UTC, 29 of the 141 `chat
zai-org/GLM-5.3-Flash` spans in Logfire stopped at the 4,096-token output cap
with finish reason "length", and 26 of the 119 first-pass runs ended with no
answer: Novita counts the model's hidden reasoning in its output tokens. Novita
honours the OpenAI-style `reasoning_effort` request field for this model. In
the 2026-10-18 probes no first pass sent with "medium" or "low" stopped at the
cap, and scored against reference readings "medium" decided the most labels
rightly (HARNESS.md section 5, "The first pass's reasoning bound"). The route
carries `reasoning_effort: medium` as its request option, through the gateway's
model settings. The units path's first pass, since WP 1.8 the only one, sends its
own options over it (first_pass.UNITS_REQUEST_OPTIONS: low reasoning and
temperature 0; test_first_pass_units.py tests its requests). These tests drive
the real gateway over an offline HTTP transport: no live model request is made.
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

from specimen_digitization.model_gateway import (
    HUGGINGFACE_ROUTES,
    INITIAL_HUGGINGFACE_ROUTES,
    HuggingFaceModelGateway,
)

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
