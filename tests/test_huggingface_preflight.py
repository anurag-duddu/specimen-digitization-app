from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic_ai import BinaryContent
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from specimen_digitization import huggingface_preflight
from specimen_digitization.hub_models import NEMOTRON_VLM_MODEL, SAM3_MODEL
from specimen_digitization.huggingface_preflight import (
    _token_permissions,
    preflight_ready,
    validate_route,
)
from specimen_digitization.model_gateway import (
    HUGGINGFACE_ROUTES,
    INITIAL_HUGGINGFACE_ROUTES,
)
from specimen_digitization.observability import CaptureMode


def test_token_permissions_merge_global_and_scoped_permissions() -> None:
    whoami = {
        "auth": {
            "accessToken": {
                "fineGrained": {
                    "global": ["discussion.write"],
                    "scoped": [
                        {
                            "permissions": [
                                "repo.content.read",
                                "inference.serverless.write",
                            ]
                        }
                    ],
                }
            }
        }
    }

    assert _token_permissions(whoami) == frozenset(
        {
            "discussion.write",
            "repo.content.read",
            "inference.serverless.write",
        }
    )


def test_route_validation_requires_image_and_structured_output() -> None:
    route = INITIAL_HUGGINGFACE_ROUTES["handwriting-qwen"]
    catalog = [
        {
            "id": route.model_id,
            "architecture": {"input_modalities": ["text", "image"]},
            "providers": [
                {
                    "provider": route.provider,
                    "status": "live",
                    "supports_structured_output": True,
                }
            ],
        }
    ]

    report = validate_route(route, catalog)

    assert report["ready"] is True
    assert report["missing_modalities"] == []


def test_route_validation_fails_closed_on_missing_capability() -> None:
    route = INITIAL_HUGGINGFACE_ROUTES["handwriting-muse"]
    catalog = [
        {
            "id": route.model_id,
            "architecture": {"input_modalities": ["text"]},
            "providers": [
                {
                    "provider": route.provider,
                    "status": "live",
                    "supports_structured_output": False,
                }
            ],
        }
    ]

    report = validate_route(route, catalog)

    assert report["ready"] is False
    assert report["missing_modalities"] == ["image"]


def test_self_hosted_assets_are_revision_pinned() -> None:
    assert SAM3_MODEL.repo_id == "facebook/sam3"
    assert len(SAM3_MODEL.revision) == 40
    assert SAM3_MODEL.gated is True
    assert NEMOTRON_VLM_MODEL.serving_mode == "self-hosted-openai-compatible"
    assert len(NEMOTRON_VLM_MODEL.revision) == 40


def test_preflight_ready_requires_every_gate() -> None:
    report = {
        "token": {"authenticated": True, "missing_required_permissions": []},
        "routes": [{"ready": True}, {"ready": True}],
        "sam3": {"access": "confirmed", "config_downloaded": True},
    }

    assert preflight_ready(report) is True

    report["routes"][1]["ready"] = False
    assert preflight_ready(report) is False


def test_live_cli_configures_and_flushes_logfire(monkeypatch) -> None:
    report = {
        "token": {"authenticated": True, "missing_required_permissions": []},
        "routes": [{"ready": True}],
        "sam3": {"access": "confirmed", "config_downloaded": True},
        "live_smoke": {"structured_output_valid": True},
    }
    configure = Mock()
    flush = Mock()
    run_preflight = Mock(return_value=report)
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "specimen-huggingface-preflight",
            "--live-route",
            "handwriting-qwen",
            "--image",
            "fixture.png",
            "--approved-content",
        ],
    )
    monkeypatch.setattr(huggingface_preflight, "configure_observability", configure)
    monkeypatch.setattr(huggingface_preflight.logfire, "force_flush", flush)
    monkeypatch.setattr(huggingface_preflight, "run_preflight", run_preflight)

    huggingface_preflight.main()

    configure.assert_called_once_with(capture_mode=CaptureMode.APPROVED_CONTENT)
    flush.assert_called_once_with()
    assert run_preflight.call_args.kwargs["image_path"] == Path("fixture.png")


def live_smoke(monkeypatch, tmp_path, seen, route_id, *, image, usage=None):
    """The paid smoke test against a fake provider that records each request."""

    def respond(messages, info):
        seen.append((messages, info.model_settings))
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {"short_description": "a fixture", "contains_readable_text": True},
                )
            ],
            usage=usage or RequestUsage(),
            finish_reason="stop",
        )

    class Gateway:
        def __init__(self, token=None, bill_to=None):
            pass

        def route(self, route_id):
            return HUGGINGFACE_ROUTES[route_id]

        def model_for(self, route_id):
            return FunctionModel(respond, model_name="fake-smoke")

    monkeypatch.setattr(huggingface_preflight, "HuggingFaceModelGateway", Gateway)
    fixture = tmp_path / "fixture.png"
    fixture.write_bytes(b"PNG")
    return huggingface_preflight.run_live_image_smoke(
        "hf_test", route_id=route_id, image_path=fixture if image else None
    )


@pytest.mark.parametrize(
    "route_id,image", [("first-pass-glm", True), ("harness-deepseek", False)]
)
def test_live_smoke_sends_an_image_only_to_a_route_that_takes_one(
    monkeypatch, tmp_path, route_id, image
) -> None:
    seen = []

    report = live_smoke(monkeypatch, tmp_path, seen, route_id, image=image)

    ((messages, _),) = seen
    sent = [
        item
        for part in messages[0].parts
        if part.part_kind == "user-prompt"
        for item in (part.content if isinstance(part.content, list) else [part.content])
    ]
    assert any(isinstance(item, BinaryContent) for item in sent) is image
    assert report["structured_output_valid"] is True


def test_live_smoke_is_capped_like_a_reading(monkeypatch, tmp_path) -> None:
    # A reading's caps: 4,096 output tokens a response, two requests, and a
    # stop once the run passes 16,000 tokens (production.py's reader call).
    limits = []
    run_sync = huggingface_preflight.Agent.run_sync

    def recording(self, *args, **kwargs):
        limits.append(kwargs.get("usage_limits"))
        return run_sync(self, *args, **kwargs)

    monkeypatch.setattr(huggingface_preflight.Agent, "run_sync", recording)
    seen = []
    live_smoke(monkeypatch, tmp_path, seen, "first-pass-glm", image=True)
    ((_, settings),) = seen
    assert (settings or {}).get("max_tokens") == 4096
    assert [
        (getattr(limit, "request_limit", None), getattr(limit, "total_tokens_limit", None))
        for limit in limits
    ] == [(2, 16000)]

    with pytest.raises(UsageLimitExceeded):
        live_smoke(
            monkeypatch,
            tmp_path,
            [],
            "first-pass-glm",
            image=True,
            usage=RequestUsage(input_tokens=15000, output_tokens=2000),
        )


@pytest.mark.parametrize(
    "route_id,image", [("first-pass-glm", False), ("harness-deepseek", True)]
)
def test_live_smoke_refuses_a_missing_or_an_unwanted_image_before_any_request(
    monkeypatch, tmp_path, route_id, image
) -> None:
    seen = []

    with pytest.raises(ValueError):
        live_smoke(monkeypatch, tmp_path, seen, route_id, image=image)

    assert seen == []


def test_preflight_runs_a_text_only_smoke_without_an_image(monkeypatch) -> None:
    smoke = Mock(return_value={"structured_output_valid": True})
    monkeypatch.setattr(huggingface_preflight, "inspect_runtime_token", Mock())
    monkeypatch.setattr(
        huggingface_preflight, "fetch_router_catalog", Mock(return_value=[])
    )
    monkeypatch.setattr(huggingface_preflight, "validate_route", Mock())
    monkeypatch.setattr(huggingface_preflight, "verify_sam3_access", Mock())
    monkeypatch.setattr(huggingface_preflight, "run_live_image_smoke", smoke)

    report = huggingface_preflight.run_preflight(
        token="hf_test", live_route="harness-deepseek"
    )

    assert smoke.call_args.kwargs["image_path"] is None
    assert report["live_smoke"] == {"structured_output_valid": True}
