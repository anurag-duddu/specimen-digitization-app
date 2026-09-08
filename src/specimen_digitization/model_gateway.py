"""Application-owned Hugging Face model routing.

The gateway keeps credentials out of collection profiles and makes every
model/provider choice explicit.  Production callers must select a pinned route;
Hugging Face's automatic provider fallback is intentionally not used.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from huggingface_hub import AsyncInferenceClient
from pydantic import SecretStr
from pydantic_ai.models.huggingface import HuggingFaceModel
from pydantic_ai.providers.huggingface import HuggingFaceProvider


class ModelGatewayConfigurationError(RuntimeError):
    """Raised when a model route or its credential is not configured safely."""


@dataclass(frozen=True, slots=True)
class HuggingFaceInferenceRoute:
    """A reviewed model/provider pair served by Inference Providers."""

    route_id: str
    logical_capability: str
    model_id: str
    provider: str
    required_input_modalities: tuple[str, ...] = ("text", "image")
    requires_structured_output: bool = True

    def __post_init__(self) -> None:
        disallowed_provider_policies = {"", "auto", "fastest", "cheapest", "preferred"}
        if self.provider.strip().lower() in disallowed_provider_policies:
            raise ValueError(
                "Hugging Face routes must pin a concrete provider; automatic "
                "routing and policy suffixes are not allowed."
            )


INITIAL_HUGGINGFACE_ROUTES: Mapping[str, HuggingFaceInferenceRoute] = MappingProxyType(
    {
        "handwriting-qwen": HuggingFaceInferenceRoute(
            route_id="handwriting-qwen",
            logical_capability="handwriting_transcriber",
            model_id="Qwen/Qwen3-VL-30B-A3B-Instruct",
            provider="novita",
        ),
        "handwriting-muse": HuggingFaceInferenceRoute(
            route_id="handwriting-muse",
            logical_capability="handwriting_transcriber",
            model_id="meta-models/Muse-Glimmer-30B",
            provider="deepinfra",
        ),
    }
)


class HuggingFaceModelGateway:
    """Build Pydantic AI models from explicit Hugging Face routes."""

    def __init__(
        self,
        *,
        token: str | None = None,
        bill_to: str | None = None,
        routes: Mapping[str, HuggingFaceInferenceRoute] | None = None,
    ) -> None:
        resolved_token = token or os.getenv("HF_TOKEN")
        if not resolved_token:
            raise ModelGatewayConfigurationError(
                "HF_TOKEN is required for Hugging Face model access."
            )

        self._token = SecretStr(resolved_token)
        self._bill_to = bill_to if bill_to is not None else os.getenv("HF_BILL_TO")
        selected_routes = INITIAL_HUGGINGFACE_ROUTES if routes is None else routes
        self._routes = MappingProxyType(dict(selected_routes))

    @property
    def routes(self) -> Mapping[str, HuggingFaceInferenceRoute]:
        return self._routes

    def route(self, route_id: str) -> HuggingFaceInferenceRoute:
        try:
            return self._routes[route_id]
        except KeyError as exc:
            available = ", ".join(sorted(self._routes))
            raise ModelGatewayConfigurationError(
                f"Unknown Hugging Face route {route_id!r}; available routes: {available}."
            ) from exc

    def routes_for_capability(
        self, logical_capability: str
    ) -> tuple[HuggingFaceInferenceRoute, ...]:
        return tuple(
            route
            for route in self._routes.values()
            if route.logical_capability == logical_capability
        )

    def model_for(self, route_id: str) -> HuggingFaceModel:
        """Return a Pydantic AI model bound to the route's concrete provider."""
        route = self.route(route_id)
        client = AsyncInferenceClient(
            provider=route.provider,
            api_key=self._token.get_secret_value(),
            bill_to=self._bill_to or None,
        )
        provider = HuggingFaceProvider(hf_client=client)
        return HuggingFaceModel(route.model_id, provider=provider)
