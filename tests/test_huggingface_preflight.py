from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock

from specimen_digitization import huggingface_preflight
from specimen_digitization.hub_models import NEMOTRON_VLM_MODEL, SAM3_MODEL
from specimen_digitization.huggingface_preflight import (
    _token_permissions,
    preflight_ready,
    validate_route,
)
from specimen_digitization.model_gateway import INITIAL_HUGGINGFACE_ROUTES


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
        ],
    )
    monkeypatch.setattr(huggingface_preflight, "configure_observability", configure)
    monkeypatch.setattr(huggingface_preflight.logfire, "force_flush", flush)
    monkeypatch.setattr(huggingface_preflight, "run_preflight", run_preflight)

    huggingface_preflight.main()

    configure.assert_called_once_with()
    flush.assert_called_once_with()
    assert run_preflight.call_args.kwargs["image_path"] == Path("fixture.png")
