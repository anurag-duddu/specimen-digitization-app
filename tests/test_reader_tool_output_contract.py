"""Offline two-reader wire contract; synthetic model responses, no paid calls."""
from dataclasses import replace
import json

import httpx
import pytest
from huggingface_hub.hf_api import InferenceProviderMapping
from huggingface_hub.inference._providers._common import HARDCODED_MODEL_INFERENCE_MAPPING
from huggingface_hub.utils import _http as hf_http
from pydantic_ai import BinaryContent
from pydantic_ai.usage import UsageLimits

from specimen_digitization.huggingface_preflight import validate_route
from specimen_digitization.model_gateway import INITIAL_HUGGINGFACE_ROUTES, HuggingFaceModelGateway
from specimen_digitization.prompts import PromptName, ResolvedPrompt
from specimen_digitization.transcription import build_literal_transcription_agent


def catalog_for(route, *, tools=True, native_schema=False, status="live", modalities=("text", "image")):
    # Synthetic catalog fixture mirrors the observed capability flags only.
    return [{"id": route.model_id, "architecture": {"input_modalities": list(modalities)},
             "providers": [{"provider": route.provider, "status": status,
                            "supports_tools": tools, "supports_structured_output": native_schema}]}]


def test_muse_tool_schema_output_does_not_require_native_json_schema():
    route = INITIAL_HUGGINGFACE_ROUTES["handwriting-muse"]
    report = validate_route(route, catalog_for(route, tools=True, native_schema=False))
    assert report["ready"] is True
    assert report["structured_output"] is False
    assert report["structured_output_mode"] == "tool" and report["tool_output"] is True


@pytest.mark.parametrize("tools", [False, None, "true", 1])
def test_native_schema_flag_cannot_replace_strict_tool_output_capability(tools):
    route = INITIAL_HUGGINGFACE_ROUTES["handwriting-muse"]
    assert validate_route(route, catalog_for(route, tools=tools, native_schema=True))["ready"] is False


def test_tool_mode_keeps_pinned_provider_live_and_image_checks():
    route = INITIAL_HUGGINGFACE_ROUTES["handwriting-muse"]
    for items in ([], catalog_for(route, status="offline"), catalog_for(route, modalities=("text",))):
        assert validate_route(route, items)["ready"] is False
    items = catalog_for(route)
    items[0]["providers"][0]["provider"] = "another-provider"
    assert validate_route(route, items)["ready"] is False


def test_routes_refuse_an_unimplemented_native_output_mode():
    with pytest.raises(ValueError, match="schema-validated tool output"):
        replace(INITIAL_HUGGINGFACE_ROUTES["handwriting-muse"], structured_output_mode="native")


@pytest.mark.parametrize("route_id", ["handwriting-qwen", "handwriting-muse"])
def test_actual_hf_reader_sends_tool_schema_and_validates_literal_retry(monkeypatch, route_id):
    route = INITIAL_HUGGINGFACE_ROUTES[route_id]
    monkeypatch.setitem(HARDCODED_MODEL_INFERENCE_MAPPING, route.provider, {
        route.model_id: InferenceProviderMapping(provider=route.provider, hf_model_id=route.model_id,
                                                 providerId=route.model_id, status="live", task="conversational")})
    sent = []

    def handler(request):
        assert request.url.path.endswith("/chat/completions")
        payload = json.loads(request.content)
        sent.append(payload)
        assert len(sent) <= 2
        assert "response_format" not in payload
        assert payload["tools"] and payload["tool_choice"]
        tool = payload["tools"][0]
        assert tool["type"] == "function"
        assert {"verbatim_text", "lines"} <= set(tool["function"]["parameters"]["required"])
        assert payload["max_tokens"] == 4096
        output = {"verbatim_text": "synthetic alpha", "lines": ["wrong" if len(sent) == 1 else "synthetic alpha"]}
        return httpx.Response(200, json={
            "id": "synthetic-completion-" + str(len(sent)), "object": "chat.completion", "created": 0,
            "model": route.model_id, "system_fingerprint": "offline-synthetic",
            "choices": [{"index": 0, "finish_reason": "tool_calls", "logprobs": None,
                         "message": {"role": "assistant", "content": None, "tool_calls": [{
                             "id": "synthetic-call-" + str(len(sent)), "type": "function", "function": {
                                 "name": tool["function"]["name"], "arguments": json.dumps(output)}}]}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})

    monkeypatch.setattr(hf_http, "_GLOBAL_ASYNC_CLIENT_FACTORY",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    gateway = HuggingFaceModelGateway(token="hf_synthetic_offline")
    model = gateway.model_for(route_id)
    assert model.profile["default_structured_output_mode"] == "tool"
    assert model.profile["supports_tools"] is True and model.profile["supports_json_schema_output"] is False
    prompt = ResolvedPrompt(name=PromptName.LITERAL_TRANSCRIPTION, text="Read the synthetic fixture literally.",
                            requested_label="offline", served_label=None, version=None,
                            resolution_reason="code-default")
    agent = build_literal_transcription_agent(gateway, route_id=route_id, prompt=prompt)
    result = agent.run_sync(["synthetic fixture", BinaryContent(data=b"synthetic image fixture", media_type="image/png")],
                            model_settings={"max_tokens": 4096},
                            usage_limits=UsageLimits(request_limit=2, total_tokens_limit=16000))
    assert result.output.verbatim_text == "synthetic alpha" and result.output.lines == ["synthetic alpha"]
    assert len(sent) == 2  # Invalid lines were refused by the real LiteralTranscription validator.
    earlier = [call for message in sent[1]["messages"] for call in message.get("tool_calls") or []]
    assert len(earlier) == 1
    assert json.loads(earlier[0]["function"]["arguments"]) == {"verbatim_text": "synthetic alpha", "lines": ["wrong"]}
    assert (route.model_id, route.provider) == (("Qwen/Qwen3-VL-30B-A3B-Instruct", "novita") if route_id == "handwriting-qwen"
                                              else ("meta-models/Muse-Glimmer-30B", "deepinfra"))
