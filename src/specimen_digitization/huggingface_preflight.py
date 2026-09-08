"""Sanitized Hugging Face credential, route, and gated-asset checks."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import httpx
import logfire
from huggingface_hub import HfApi, hf_hub_download
from pydantic import BaseModel
from pydantic_ai import Agent, BinaryContent

from .hub_models import SAM3_MODEL
from .model_gateway import (
    INITIAL_HUGGINGFACE_ROUTES,
    HuggingFaceInferenceRoute,
    HuggingFaceModelGateway,
)
from .observability import CaptureMode, configure_observability

ROUTER_MODELS_URL = "https://router.huggingface.co/v1/models"
REQUIRED_RUNTIME_PERMISSIONS = frozenset(
    {"inference.serverless.write", "repo.content.read"}
)


class SyntheticImageObservation(BaseModel):
    """Small structured result used only for a non-museum live smoke test."""

    short_description: str
    contains_readable_text: bool


def _token_permissions(whoami: dict[str, Any]) -> frozenset[str]:
    access_token = whoami.get("auth", {}).get("accessToken", {})
    fine_grained = access_token.get("fineGrained", {}) or {}
    permissions = set(fine_grained.get("global", []) or [])
    for scope in fine_grained.get("scoped", []) or []:
        permissions.update(scope.get("permissions", []) or [])
    return frozenset(permissions)


def inspect_runtime_token(token: str) -> dict[str, Any]:
    """Verify authentication and report permissions without identity or token data."""
    whoami = HfApi().whoami(token=token)
    permissions = _token_permissions(whoami)
    return {
        "authenticated": bool(whoami.get("name")),
        "token_role": whoami.get("auth", {}).get("accessToken", {}).get("role"),
        "required_permissions_present": sorted(
            REQUIRED_RUNTIME_PERMISSIONS.intersection(permissions)
        ),
        "missing_required_permissions": sorted(
            REQUIRED_RUNTIME_PERMISSIONS.difference(permissions)
        ),
        "extra_permission_count": len(permissions - REQUIRED_RUNTIME_PERMISSIONS),
    }


def fetch_router_catalog(token: str) -> list[dict[str, Any]]:
    response = httpx.get(
        ROUTER_MODELS_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("data", [])


def validate_route(
    route: HuggingFaceInferenceRoute, catalog: list[dict[str, Any]]
) -> dict[str, Any]:
    model = next((item for item in catalog if item.get("id") == route.model_id), None)
    if model is None:
        return {"route_id": route.route_id, "ready": False, "reason": "model_missing"}

    input_modalities = set(model.get("architecture", {}).get("input_modalities", []))
    provider = next(
        (
            item
            for item in model.get("providers", [])
            if item.get("provider") == route.provider
        ),
        None,
    )
    missing_modalities = sorted(set(route.required_input_modalities) - input_modalities)
    ready = bool(
        provider
        and provider.get("status") == "live"
        and not missing_modalities
        and (
            not route.requires_structured_output
            or provider.get("supports_structured_output") is True
        )
    )
    return {
        "route_id": route.route_id,
        "model_id": route.model_id,
        "provider": route.provider,
        "ready": ready,
        "provider_status": provider.get("status") if provider else "missing",
        "missing_modalities": missing_modalities,
        "structured_output": (
            provider.get("supports_structured_output") if provider else False
        ),
    }


def verify_sam3_access(token: str) -> dict[str, Any]:
    """Download only SAM 3's small config file to prove gated-repo access."""
    path = hf_hub_download(
        repo_id=SAM3_MODEL.repo_id,
        filename="config.json",
        revision=SAM3_MODEL.revision,
        token=token,
    )
    return {
        "repo_id": SAM3_MODEL.repo_id,
        "revision": SAM3_MODEL.revision,
        "access": "confirmed",
        "config_downloaded": Path(path).is_file(),
    }


def run_live_image_smoke(
    token: str, *, route_id: str, image_path: Path, bill_to: str | None = None
) -> dict[str, Any]:
    gateway = HuggingFaceModelGateway(token=token, bill_to=bill_to)
    route = gateway.route(route_id)
    media_type = {
        ".jpeg": "image/jpeg",
        ".jpg": "image/jpeg",
        ".png": "image/png",
    }.get(image_path.suffix.lower())
    if media_type is None:
        raise ValueError("The live smoke image must be a PNG or JPEG file.")

    agent = Agent(
        gateway.model_for(route_id),
        name=f"huggingface_route_smoke_{route.route_id.replace('-', '_')}",
        output_type=SyntheticImageObservation,
        instructions=(
            "Inspect this synthetic/public test image. Return only the requested "
            "short factual description and whether it contains readable text."
        ),
    )
    with logfire.span(
        "Run Hugging Face route smoke",
        **{
            "specimen.run.kind": "approved-fixture-smoke",
            "specimen.model.route_id": route.route_id,
            "specimen.model.id": route.model_id,
            "specimen.model.upstream_provider": route.provider,
        },
    ):
        result = agent.run_sync(
            [
                "Describe this test image without inferring any private information.",
                BinaryContent(data=image_path.read_bytes(), media_type=media_type),
            ]
        )
    return {
        "route_id": route.route_id,
        "model_id": route.model_id,
        "provider": route.provider,
        "structured_output_valid": bool(result.output.short_description),
        "usage_available": result.usage is not None,
    }


def run_preflight(
    *,
    token: str,
    live_route: str | None = None,
    image_path: Path | None = None,
    bill_to: str | None = None,
) -> dict[str, Any]:
    token_report = inspect_runtime_token(token)
    catalog = fetch_router_catalog(token)
    route_reports = [
        validate_route(route, catalog) for route in INITIAL_HUGGINGFACE_ROUTES.values()
    ]
    report: dict[str, Any] = {
        "token": token_report,
        "router_model_count": len(catalog),
        "routes": route_reports,
        "sam3": verify_sam3_access(token),
    }
    if live_route:
        if image_path is None:
            raise ValueError("--image is required with --live-route.")
        report["live_smoke"] = run_live_image_smoke(
            token,
            route_id=live_route,
            image_path=image_path,
            bill_to=bill_to,
        )
    return report


def preflight_ready(report: dict[str, Any]) -> bool:
    """Return whether every configured preflight gate passed."""
    token_report = report.get("token", {})
    routes = report.get("routes", [])
    sam3 = report.get("sam3", {})
    live_smoke = report.get("live_smoke")
    return bool(
        token_report.get("authenticated")
        and not token_report.get("missing_required_permissions")
        and routes
        and all(route.get("ready") for route in routes)
        and sam3.get("access") == "confirmed"
        and sam3.get("config_downloaded") is True
        and (live_smoke is None or live_smoke.get("structured_output_valid") is True)
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify Hugging Face routing and gated SAM 3 access safely."
    )
    parser.add_argument(
        "--live-route",
        choices=sorted(INITIAL_HUGGINGFACE_ROUTES),
        help="Optionally run one paid synthetic image request through this route.",
    )
    parser.add_argument(
        "--image",
        type=Path,
        help="PNG or JPEG approved fixture used by --live-route.",
    )
    parser.add_argument(
        "--approved-content",
        action="store_true",
        help=(
            "Export prompt and output text for this approved fixture. Binary image "
            "content remains excluded."
        ),
    )
    args = parser.parse_args()

    token = os.getenv("HF_TOKEN")
    if not token:
        parser.error("HF_TOKEN is not set.")

    if args.live_route:
        configure_observability(
            capture_mode=(
                CaptureMode.APPROVED_CONTENT if args.approved_content else None
            )
        )
    try:
        report = run_preflight(
            token=token,
            live_route=args.live_route,
            image_path=args.image,
            bill_to=os.getenv("HF_BILL_TO") or None,
        )
    finally:
        if args.live_route:
            logfire.force_flush()

    print(json.dumps(report, indent=2, sort_keys=True))
    if not preflight_ready(report):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
