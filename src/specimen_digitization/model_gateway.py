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

from huggingface_hub import AsyncInferenceClient, ChatCompletionInputToolCall
from pydantic import SecretStr
from pydantic_ai.messages import ToolCallPart
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

    def serves_with_images(self, logical_capability: str) -> bool:
        """Whether this route plays the role and takes the text and image it is sent."""
        return self.logical_capability == logical_capability and {
            "text",
            "image",
        }.issubset(self.required_input_modalities)


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
# The reader routes above stay the whole initial set: the pilot launch, its
# stage list and the release check compare a profile's readers against it.
# The coordinator approved the first-pass and harness routes on 2026-09-23 on
# the figures of S4's T1 report; docs/execution/golive/HARNESS.md section 5
# recomputes them from the same calls.
STAGE_HUGGINGFACE_ROUTES: Mapping[str, HuggingFaceInferenceRoute] = MappingProxyType(
    {
        "first-pass-glm": HuggingFaceInferenceRoute(
            route_id="first-pass-glm",
            logical_capability="transcription_first_pass",
            model_id="zai-org/GLM-5.3-Flash",
            provider="deepinfra",
        ),
        "harness-deepseek": HuggingFaceInferenceRoute(
            route_id="harness-deepseek",
            logical_capability="field_harness",
            model_id="deepseek-ai/DeepSeek-V4.1-Flash",
            provider="deepinfra",
            required_input_modalities=("text",),
        ),
    }
)
HUGGINGFACE_ROUTES: Mapping[str, HuggingFaceInferenceRoute] = MappingProxyType(
    {**INITIAL_HUGGINGFACE_ROUTES, **STAGE_HUGGINGFACE_ROUTES}
)


class ArgumentPreservingHuggingFaceModel(HuggingFaceModel):
    """Resend earlier tool calls with the arguments the model produced.

    pydantic-ai sets ``function.arguments`` on each replayed tool call, but
    huggingface_hub rebuilds the call with ``dataclasses.asdict``, which keeps
    only the declared ``name``, ``parameters`` and ``description``. Without
    this override every turn after a tool call or an invalid-output retry goes
    out without arguments: DeepInfra rejects it with HTTP 422 and Novita hands
    the model an empty call.
    """

    @staticmethod
    def _map_tool_call(t: ToolCallPart) -> ChatCompletionInputToolCall:
        call = HuggingFaceModel._map_tool_call(t)
        call["function"]["arguments"] = t.args_as_json_str()
        return call


class HuggingFaceModelGateway:
    """Build Pydantic AI models from explicit Hugging Face routes."""

    def __init__(
        self,
        *,
        token: str | None = None,
        bill_to: str | None = None,
        routes: Mapping[str, HuggingFaceInferenceRoute] | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        resolved_token = token or os.getenv("HF_TOKEN")
        if not resolved_token:
            raise ModelGatewayConfigurationError(
                "HF_TOKEN is required for Hugging Face model access."
            )

        if timeout_seconds is not None and not 0 < timeout_seconds <= 600:
            raise ModelGatewayConfigurationError(
                "Model timeout must be within0..600 seconds"
            )
        self._timeout_seconds = timeout_seconds
        self._token = SecretStr(resolved_token)
        self._bill_to = bill_to if bill_to is not None else os.getenv("HF_BILL_TO")
        selected_routes = HUGGINGFACE_ROUTES if routes is None else routes
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

    def model_for(self, route_id: str) -> ArgumentPreservingHuggingFaceModel:
        """Return a Pydantic AI model bound to the route's concrete provider."""
        route = self.route(route_id)
        timeout_options = (
            {"timeout": self._timeout_seconds}
            if self._timeout_seconds is not None
            else {}
        )
        client = AsyncInferenceClient(
            provider=route.provider,
            api_key=self._token.get_secret_value(),
            bill_to=self._bill_to or None,
            **timeout_options,
        )
        provider = HuggingFaceProvider(
            hf_client=client, api_key=self._token.get_secret_value()
        )
        return ArgumentPreservingHuggingFaceModel(route.model_id, provider=provider)
