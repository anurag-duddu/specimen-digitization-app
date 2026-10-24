from __future__ import annotations

import json
from dataclasses import replace

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
    assert captured["model"]["profile"] == {
        "supports_tools": True,
        "supports_json_schema_output": False,
        "default_structured_output_mode": "tool",
    }
    assert "hf_do_not_log" not in repr(gateway)


def test_gateway_resolves_both_transcription_routes() -> None:
    gateway = HuggingFaceModelGateway(token="hf_test")

    routes = gateway.routes_for_capability("handwriting_transcriber")

    # The NVIDIA option's reader is registered too; a profile names two of them.
    assert {route.route_id for route in routes} == {
        "handwriting-qwen",
        "handwriting-muse",
        "handwriting-nemotron",
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


def test_first_pass_and_harness_routes_are_pinned_on_reader_providers() -> None:
    gateway = HuggingFaceModelGateway(token="hf_test")

    first_pass = gateway.route("first-pass-glm")
    harness = gateway.route("harness-deepseek")

    assert (first_pass.model_id, first_pass.provider) == (
        "zai-org/GLM-5.3-Flash",
        "novita",
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
    # Each role also has the NVIDIA option's route (NVIDIA_NEMOTRON_OPTION.md).
    assert gateway.routes_for_capability("transcription_first_pass") == (
        first_pass,
        gateway.route("first-pass-nemotron"),
    )
    assert gateway.routes_for_capability("field_harness") == (
        harness,
        gateway.route("harness-nemotron"),
    )


def test_a_route_serves_a_role_with_images_only_in_that_role_with_image_input() -> None:
    reader = INITIAL_HUGGINGFACE_ROUTES["handwriting-qwen"]

    assert reader.serves_with_images("handwriting_transcriber")
    assert not reader.serves_with_images("transcription_first_pass")
    text_only = replace(reader, required_input_modalities=("text",))
    assert not text_only.serves_with_images("handwriting_transcriber")


def test_preflight_accepts_the_new_routes_when_the_catalog_serves_them() -> None:
    from specimen_digitization.huggingface_preflight import validate_route

    def served(model_id, modalities, provider):
        return {
            "id": model_id,
            "architecture": {"input_modalities": list(modalities)},
            "providers": [
                {
                    "provider": provider,
                    "status": "live",
                    "supports_tools": True,
                    "supports_structured_output": True,
                }
            ],
        }

    catalog = [
        served("zai-org/GLM-5.3-Flash", ("text", "image"), "novita"),
        served("deepseek-ai/DeepSeek-V4.1-Flash", ("text", "image"), "deepinfra"),
    ]

    for route_id in ("first-pass-glm", "harness-deepseek"):
        assert validate_route(HUGGINGFACE_ROUTES[route_id], catalog)["ready"]
    # The pilot launch and the release check read the initial set as the readers.
    assert set(INITIAL_HUGGINGFACE_ROUTES) == {"handwriting-qwen", "handwriting-muse"}


def test_a_router_route_pins_its_provider_in_the_model_name_and_keeps_org_billing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider the installed client has no helper for is pinned on HF's router.

    huggingface_hub 1.18 has no ``baseten`` helper, the only provider of
    Nemotron 3.5 Super VL on 2026-10-18. The router's ``model:provider`` name
    pins the same concrete provider, billed through the same token and org.
    """
    route = HuggingFaceInferenceRoute(
        route_id="router-example",
        logical_capability="handwriting_transcriber",
        model_id="example/vision-model",
        provider="baseten",
        transport="router",
    )
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=_completion({"role": "assistant", "content": "ok"}))

    monkeypatch.setattr(
        hf_http,
        "_GLOBAL_ASYNC_CLIENT_FACTORY",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    gateway = HuggingFaceModelGateway(
        token="hf_test", bill_to="field-museum", routes={route.route_id: route}
    )

    assert Agent(gateway.model_for(route.route_id)).run_sync("Say ok.").output == "ok"
    (request,) = sent
    assert str(request.url) == "https://router.huggingface.co/v1/chat/completions"
    assert json.loads(request.content)["model"] == "example/vision-model:baseten"
    assert request.headers["x-hf-bill-to"] == "field-museum"
    assert request.headers["authorization"] == "Bearer hf_test"


def test_a_provider_route_still_goes_through_the_provider_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured["client"] = kwargs

    monkeypatch.setattr(model_gateway, "AsyncInferenceClient", FakeClient)
    monkeypatch.setattr(model_gateway, "HuggingFaceProvider", lambda **kwargs: None)
    monkeypatch.setattr(
        model_gateway,
        "ArgumentPreservingHuggingFaceModel",
        lambda name, **kwargs: captured.setdefault("model_name", name),
    )

    HuggingFaceModelGateway(token="hf_test").model_for("handwriting-qwen")

    assert captured["client"]["provider"] == "novita"
    assert "base_url" not in captured["client"]
    assert captured["model_name"] == "Qwen/Qwen3-VL-30B-A3B-Instruct"


@pytest.mark.parametrize("transport", ["", "auto", "openai"])
def test_route_rejects_an_unknown_transport(transport: str) -> None:
    with pytest.raises(ValueError, match="transport"):
        HuggingFaceInferenceRoute(
            route_id="unsafe",
            logical_capability="handwriting_transcriber",
            model_id="example/model",
            provider="baseten",
            transport=transport,  # type: ignore[arg-type]
        )


def _sent_request(monkeypatch: pytest.MonkeyPatch, route: HuggingFaceInferenceRoute):
    """The URL and body of a structured-output request on this route."""
    from pydantic import BaseModel

    class Answer(BaseModel):
        value: int

    sent: list[dict[str, object]] = []
    reply = _completion(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "final_result", "arguments": '{"value": 7}'},
                }
            ],
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append((str(request.url), json.loads(request.content)))
        return httpx.Response(200, json=reply)

    monkeypatch.setattr(
        hf_http,
        "_GLOBAL_ASYNC_CLIENT_FACTORY",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    gateway = HuggingFaceModelGateway(token="hf_test", routes={route.route_id: route})
    agent = Agent(gateway.model_for(route.route_id), output_type=Answer)

    assert agent.run_sync("Seven.").output == Answer(value=7)
    (request,) = sent
    return request


def _sent_tool_choice(monkeypatch: pytest.MonkeyPatch, route: HuggingFaceInferenceRoute):
    """The tool_choice a structured-output request on this route carries."""
    _, body = _sent_request(monkeypatch, route)
    return body["tool_choice"], body.get("reasoning_effort")


def test_a_route_that_reasons_only_unforced_sends_auto_tool_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nemotron 3.5 Super VL on baseten skips its reasoning when a tool is forced.

    Measured 2026-10-18 through HF's router with reasoning_effort "high": a
    forced tool ("required" or named) answered with 0-1 reasoning tokens, "auto"
    with 1,516. Such a route lets the model choose the output tool.
    """
    route = HuggingFaceInferenceRoute(
        route_id="reasoning-example",
        logical_capability="transcription_first_pass",
        model_id="example/vision-model",
        provider="baseten",
        transport="router",
        request_options=(("reasoning_effort", "high"),),
        forced_tool_choice_disables_thinking=True,
    )

    assert _sent_tool_choice(monkeypatch, route) == ("auto", "high")


def test_routes_force_the_output_tool_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    route = HuggingFaceInferenceRoute(
        route_id="forced-example",
        logical_capability="transcription_first_pass",
        model_id="example/vision-model",
        provider="baseten",
        transport="router",
    )

    assert _sent_tool_choice(monkeypatch, route) == ("required", None)


def test_pydantic_ai_still_resolves_tool_choice_through_the_overridden_hook() -> None:
    """If pydantic-ai renames the hook, a reasoning route silently forces its tool again."""
    assert isinstance(vars(HuggingFaceModel)["_get_tool_choice"], staticmethod)


NEMOTRON = "nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4"


def test_the_nvidia_option_serves_one_model_on_baseten_through_the_router() -> None:
    """docs/product-requirements/NVIDIA_NEMOTRON_OPTION.md section 1."""
    from specimen_digitization.model_gateway import (
        NVIDIA_HUGGINGFACE_ROUTES,
        READER_HUGGINGFACE_ROUTES,
        STAGE_HUGGINGFACE_ROUTES,
    )

    reader = NVIDIA_HUGGINGFACE_ROUTES["handwriting-nemotron"]
    first_pass = NVIDIA_HUGGINGFACE_ROUTES["first-pass-nemotron"]
    harness = NVIDIA_HUGGINGFACE_ROUTES["harness-nemotron"]

    assert set(NVIDIA_HUGGINGFACE_ROUTES) == {
        "handwriting-nemotron",
        "first-pass-nemotron",
        "harness-nemotron",
    }
    for route in (reader, first_pass, harness):
        assert (route.model_id, route.provider, route.transport) == (
            NEMOTRON,
            "baseten",
            "router",
        )
    assert (reader.logical_capability, reader.required_input_modalities) == (
        "handwriting_transcriber",
        ("text", "image"),
    )
    assert (first_pass.logical_capability, first_pass.required_input_modalities) == (
        "transcription_first_pass",
        ("text", "image"),
    )
    assert (harness.logical_capability, harness.required_input_modalities) == (
        "field_harness",
        ("text",),
    )
    assert reader.request_options == harness.request_options == ()
    assert not reader.forced_tool_choice_disables_thinking
    assert not harness.forced_tool_choice_disables_thinking
    assert first_pass.request_options == (("reasoning_effort", "low"),)
    assert first_pass.forced_tool_choice_disables_thinking is True
    # A run pinned to any route resolves; the pilot's readers stay the initial two.
    assert dict(HUGGINGFACE_ROUTES) == {
        **INITIAL_HUGGINGFACE_ROUTES,
        **STAGE_HUGGINGFACE_ROUTES,
        **NVIDIA_HUGGINGFACE_ROUTES,
    }
    assert set(INITIAL_HUGGINGFACE_ROUTES) == {"handwriting-qwen", "handwriting-muse"}
    assert dict(READER_HUGGINGFACE_ROUTES) == {
        **INITIAL_HUGGINGFACE_ROUTES,
        "handwriting-nemotron": reader,
    }


@pytest.mark.parametrize(
    "route_id,expected",
    [
        ("handwriting-nemotron", ("required", None)),
        # The first pass reasons, so it lets the model choose its output tool.
        ("first-pass-nemotron", ("auto", "low")),
        ("harness-nemotron", ("required", None)),
    ],
)
def test_an_nvidia_route_calls_the_router_with_its_pinned_provider(
    monkeypatch: pytest.MonkeyPatch, route_id: str, expected: tuple
) -> None:
    url, body = _sent_request(monkeypatch, HUGGINGFACE_ROUTES[route_id])

    assert url == "https://router.huggingface.co/v1/chat/completions"
    assert body["model"] == f"{NEMOTRON}:baseten"
    assert (body["tool_choice"], body.get("reasoning_effort")) == expected
