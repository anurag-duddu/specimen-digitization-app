from __future__ import annotations

import pytest

from specimen_digitization import model_gateway
from specimen_digitization.model_gateway import (
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
    monkeypatch.setattr(model_gateway, "HuggingFaceModel", FakeModel)

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
