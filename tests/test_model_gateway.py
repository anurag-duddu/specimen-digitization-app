from __future__ import annotations

import json

import httpx
import pytest
from huggingface_hub.hf_api import InferenceProviderMapping
from huggingface_hub.inference._providers._common import (
    HARDCODED_MODEL_INFERENCE_MAPPING,
)
from huggingface_hub.utils import _http as hf_http
from pydantic_ai import Agent
from pydantic_ai.models.huggingface import HuggingFaceModel

from specimen_digitization import model_gateway
from specimen_digitization.model_gateway import (
    HUGGINGFACE_ROUTES,
    INITIAL_HUGGINGFACE_ROUTES,
    HuggingFaceInferenceRoute,
    HuggingFaceModelGateway,
    ModelGatewayConfigurationError,
)


def test_initial_routes_are_explicit_and_independent() -> None:
    qwen = INITIAL_HUGGINGFACE_ROUTES["handwriting-qwen"]
    muse = INITIAL_HUGGINGFACE_ROUTES["handwriting-muse"]

    assert qwen.model_id != muse.model_id
    assert qwen.provider != muse.provider
    assert qwen.logical_capability == muse.logical_capability
    assert qwen.required_input_modalities == ("text", "image")
    assert muse.requires_structured_output is True


@pytest.mark.parametrize("provider", ["", "auto", "fastest", "cheapest", "preferred"])
def test_route_rejects_automatic_provider_policies(provider: str) -> None:
    with pytest.raises(ValueError, match="pin a concrete provider"):
        HuggingFaceInferenceRoute(
            route_id="unsafe",
            logical_capability="handwriting_transcriber",
            model_id="example/model",
            provider=provider,
        )


def test_gateway_requires_a_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)

    with pytest.raises(ModelGatewayConfigurationError, match="HF_TOKEN"):
        HuggingFaceModelGateway()


def test_gateway_builds_model_with_pinned_provider_and_org_billing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured["client"] = kwargs

    class FakeProvider:
        def __init__(self, **kwargs: object) -> None:
            captured["provider"] = kwargs

    class FakeModel:
        def __init__(self, model_name: str, **kwargs: object) -> None:
            captured["model_name"] = model_name
            captured["model"] = kwargs

    monkeypatch.setattr(model_gateway, "AsyncInferenceClient", FakeClient)
    monkeypatch.setattr(model_gateway, "HuggingFaceProvider", FakeProvider)
    monkeypatch.setattr(model_gateway, "ArgumentPreservingHuggingFaceModel", FakeModel)

    gateway = HuggingFaceModelGateway(token="hf_do_not_log", bill_to="field-museum")
    gateway.model_for("handwriting-muse")

    assert captured["client"] == {
        "provider": "deepinfra",
        "api_key": "hf_do_not_log",  # pragma: allowlist secret
        "bill_to": "field-museum",
    }
    assert captured["model_name"] == "meta-models/Muse-Glimmer-30B"
    assert "hf_do_not_log" not in repr(gateway)


def test_gateway_resolves_both_transcription_routes() -> None:
    gateway = HuggingFaceModelGateway(token="hf_test")

    routes = gateway.routes_for_capability("handwriting_transcriber")

    assert {route.route_id for route in routes} == {
        "handwriting-qwen",
        "handwriting-muse",
    }


def test_gateway_respects_an_explicit_empty_route_set() -> None:
    gateway = HuggingFaceModelGateway(token="hf_test", routes={})

    assert gateway.routes == {}


def test_explicit_gateway_credential_does_not_require_environment(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    gateway = HuggingFaceModelGateway(token="synthetic-test-credential")
    model = gateway.model_for("handwriting-qwen")
    assert model.model_name == "Qwen/Qwen3-VL-30B-A3B-Instruct"
    import os

    assert "HF_TOKEN" not in os.environ


def _completion(message: dict[str, object]) -> dict[str, object]:
    return {
        "id": "completion",
        "object": "chat.completion",
        "created": 0,
        "model": "meta-models/Muse-Glimmer-30B",
        "system_fingerprint": "fake",
        "choices": [
            {"index": 0, "finish_reason": "stop", "message": message, "logprobs": None}
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def test_replayed_tool_calls_keep_their_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second model turn resends the earlier tool call with its arguments."""
    route = INITIAL_HUGGINGFACE_ROUTES["handwriting-muse"]
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
    replies = iter(
        [
            _completion(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "lookup",
                                "arguments": '{"name": "alpha"}',
                            },
                        }
                    ],
                }
            ),
            _completion({"role": "assistant", "content": "code 7"}),
        ]
    )
    sent: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=next(replies))

    # huggingface_hub reads this factory on every request; monkeypatch restores it.
    monkeypatch.setattr(
        hf_http,
        "_GLOBAL_ASYNC_CLIENT_FACTORY",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    agent = Agent(HuggingFaceModelGateway(token="hf_test").model_for(route.route_id))

    @agent.tool_plain
    def lookup(name: str) -> str:
        return f"code {7 if name == 'alpha' else 0}"

    assert agent.run_sync("Look up alpha.").output == "code 7"
    replayed = [
        call
        for message in sent[1]["messages"]
        for call in message.get("tool_calls") or []
    ]
    assert replayed == [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "lookup", "arguments": '{"name": "alpha"}'},
        }
    ]


def test_pydantic_ai_still_maps_tool_calls_through_the_overridden_hook() -> None:
    """If pydantic-ai renames the hook, the argument fix silently stops applying."""
    assert isinstance(vars(HuggingFaceModel)["_map_tool_call"], staticmethod)


def test_first_pass_and_harness_routes_are_pinned_on_the_reader_provider() -> None:
    gateway = HuggingFaceModelGateway(token="hf_test")

    first_pass = gateway.route("first-pass-glm")
    harness = gateway.route("harness-deepseek")

    assert (first_pass.model_id, first_pass.provider) == (
        "zai-org/GLM-5.3-Flash",
        "deepinfra",
    )
    assert first_pass.required_input_modalities == ("text", "image")
    assert (harness.model_id, harness.provider) == (
        "deepseek-ai/DeepSeek-V4.1-Flash",
        "deepinfra",
    )
    assert harness.required_input_modalities == ("text",)
    readers = {
        route.model_id
        for route in gateway.routes_for_capability("handwriting_transcriber")
    }
    assert {first_pass.model_id, harness.model_id}.isdisjoint(readers)
    assert gateway.routes_for_capability("transcription_first_pass") == (first_pass,)
    assert gateway.routes_for_capability("field_harness") == (harness,)


def test_preflight_accepts_the_new_routes_when_the_catalog_serves_them() -> None:
    from specimen_digitization.huggingface_preflight import validate_route

    def served(model_id, modalities):
        return {
            "id": model_id,
            "architecture": {"input_modalities": list(modalities)},
            "providers": [
                {
                    "provider": "deepinfra",
                    "status": "live",
                    "supports_structured_output": True,
                }
            ],
        }

    catalog = [
        served("zai-org/GLM-5.3-Flash", ("text", "image")),
        served("deepseek-ai/DeepSeek-V4.1-Flash", ("text", "image")),
    ]

    for route_id in ("first-pass-glm", "harness-deepseek"):
        assert validate_route(HUGGINGFACE_ROUTES[route_id], catalog)["ready"]
    # The pilot launch and the release check read the initial set as the readers.
    assert set(INITIAL_HUGGINGFACE_ROUTES) == {"handwriting-qwen", "handwriting-muse"}
