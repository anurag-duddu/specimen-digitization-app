"""Transport timeouts cross the model boundary without releasing unknown spend."""

import asyncio
from contextlib import contextmanager
import json
import socket
from types import SimpleNamespace

import httpx
import pytest
from huggingface_hub.errors import InferenceTimeoutError
from huggingface_hub.hf_api import InferenceProviderMapping
from huggingface_hub.inference._providers._common import (
    HARDCODED_MODEL_INFERENCE_MAPPING,
)
from huggingface_hub.utils import _http as hf_http
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from specimen_digitization.application.domain import Asset, LookupStatus, Profile, Region
from specimen_digitization.application.reliability import AdapterFailure, run_agent_bounded
from specimen_digitization.model_gateway import (
    HuggingFaceModelGateway,
    INITIAL_HUGGINGFACE_ROUTES,
)


class Pick(BaseModel):
    selected_reader: int


@pytest.fixture
def muse_agent(monkeypatch):
    """The installed Pydantic/HF/HTTPX stack, with no network or real credential."""
    route = INITIAL_HUGGINGFACE_ROUTES["handwriting-muse"]
    monkeypatch.setitem(HARDCODED_MODEL_INFERENCE_MAPPING, route.provider, {
        route.model_id: InferenceProviderMapping(
            provider=route.provider, hf_model_id=route.model_id,
            providerId=route.model_id, status="live", task="conversational",
        ),
    })
    monkeypatch.setenv("PYDANTIC_AI_NO_BANNER", "1")

    def forbid_network(*args, **kwargs):
        raise AssertionError("This fixture must not use the network")

    monkeypatch.setattr(socket.socket, "connect", forbid_network)
    monkeypatch.setattr(socket, "getaddrinfo", forbid_network)
    clients = []

    def build(error, malformed_first=False):
        requests = []

        def handler(request):
            body = json.loads(request.content)
            requests.append((body, request.extensions["timeout"]))
            if malformed_first and len(requests) == 1:
                return httpx.Response(200, json={
                    "id": "synthetic-completion", "object": "chat.completion",
                    "created": 0, "model": route.model_id,
                    "choices": [{"index": 0, "finish_reason": "stop", "message": {
                        "role": "assistant", "content": None, "tool_calls": [{
                            "id": "synthetic-tool", "type": "function", "function": {
                                "name": body["tools"][0]["function"]["name"],
                                "arguments": '{"selected_reader":"invalid"}',
                            },
                        }],
                    }}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                })
            raise error

        def client_factory():
            client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            clients.append(client)
            return client

        monkeypatch.setattr(hf_http, "_GLOBAL_ASYNC_CLIENT_FACTORY", client_factory)
        gateway = HuggingFaceModelGateway(
            token="hf_synthetic_offline", bill_to="", timeout_seconds=60,
        )
        return Agent(gateway.model_for(route.route_id), output_type=Pick), requests

    yield build
    for client in clients:
        asyncio.run(client.aclose())


def bounded(agent):
    return run_agent_bounded(
        agent, "Synthetic text only", timeout_seconds=120,
        usage_limits=UsageLimits(request_limit=2, total_tokens_limit=16_000),
    )


@pytest.mark.parametrize("error_type", [
    httpx.ReadTimeout, httpx.ConnectTimeout, httpx.WriteTimeout, httpx.PoolTimeout,
    TimeoutError, InferenceTimeoutError,
])
@pytest.mark.parametrize("malformed_first", [False, True])
def test_transport_timeout_retains_unknown_spend_without_an_sdk_retry(
    muse_agent, error_type, malformed_first,
):
    error = error_type("PRIVATE-TIMEOUT-CANARY")
    agent, requests = muse_agent(error, malformed_first)
    with pytest.raises(AdapterFailure) as failure:
        bounded(agent)
    # HF wraps builtin timeouts once; HTTPX timeouts pass through unchanged.
    cause = failure.value.__cause__
    assert cause is error or cause.__cause__ is error
    assert str(failure.value) == "provider_deadline_outcome_unknown"
    assert failure.value.status is LookupStatus.PROVIDER
    assert failure.value.outcome_unknown is True
    assert failure.value.refused is False
    # Even an earlier answered request cannot prove what the timed-out one cost.
    assert failure.value.usage is None
    assert len(requests) == (2 if malformed_first else 1)
    assert all(body["max_tokens"] == 4096 for body, _ in requests)
    assert all(set(timeout.values()) == {60} for _, timeout in requests)


@pytest.mark.parametrize("error_type", [ValueError, httpx.ReadError])
def test_non_timeout_errors_are_not_reclassified(muse_agent, error_type):
    error = error_type("PRIVATE-OTHER-ERROR-CANARY")
    agent, requests = muse_agent(error)
    with pytest.raises(error_type) as failure:
        bounded(agent)
    assert failure.value is error
    assert len(requests) == 1


def test_child_reports_safe_adapter_metadata_for_transport_timeout(
    muse_agent, monkeypatch, tmp_path,
):
    from specimen_digitization.application import model_runtime, production

    agent, requests = muse_agent(httpx.ReadTimeout("PRIVATE-TIMEOUT-CANARY"))
    monkeypatch.setattr(production, "ProductionAdapters", lambda blobs: SimpleNamespace(
        _transcribe_direct=lambda *args: bounded(agent),
    ))
    attributes = {}

    @contextmanager
    def span(*args, **kwargs):
        yield SimpleNamespace(set_attribute=lambda key, value: attributes.update({key: value}))

    monkeypatch.setattr(model_runtime, "isolated_model_span", span)
    asset = Asset(sha256="0" * 64, blob_ref="synthetic", media_type="image/png",
                  size_bytes=1, width=1, height=1, filename="synthetic.png", uploader="synthetic")
    region = Region(asset_id=asset.id, x=0, y=0, width=1, height=1,
                    order=0, method="synthetic", version="1")
    result = model_runtime.model_child({
        "operation": "transcribe", "storage": {"kind": "local", "root": str(tmp_path)},
        "asset": asset.model_dump(mode="json"), "profile": Profile().model_dump(mode="json"),
        "dependencies": {}, "region": region.model_dump(mode="json"), "route": "handwriting-muse",
    })
    assert json.loads(result) == {
        "status": "adapter_failure", "code": "provider_deadline_outcome_unknown",
        "lookup_status": "provider_error", "retry_after_seconds": None,
        "outcome_unknown": True, "refused": False, "usage": None,
    }
    assert attributes == {"specimen.model.outcome": "adapter_failure"}
    assert b"PRIVATE-TIMEOUT-CANARY" not in result
    assert len(requests) == 1
