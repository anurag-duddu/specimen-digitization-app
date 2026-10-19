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
from typing import Literal

from huggingface_hub import AsyncInferenceClient, ChatCompletionInputToolCall
from pydantic import SecretStr
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.huggingface import HuggingFaceModel
from pydantic_ai.providers.huggingface import HuggingFaceProvider


# Hugging Face's OpenAI-compatible router. A "model:provider" name pins one
# concrete provider there, billed through the same token and bill-to org.
HUGGINGFACE_ROUTER_URL = "https://router.huggingface.co/v1"


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
    structured_output_mode: Literal["tool"] = "tool"
    # Provider-specific fields sent in the body of every request on this route,
    # as (name, value) pairs; each one measured to have its effect on the
    # route's provider (HARNESS.md section 5). They travel with the route, so
    # a change of provider re-measures them there or clears them: a provider
    # that refuses a field rejects every request (model_request_rejected).
    request_options: tuple[tuple[str, str], ...] = ()
    # "provider": huggingface_hub's own helper for the provider builds the
    # request. "router": HF's router receives "model_id:provider", for a
    # provider the installed client has no helper for (baseten in
    # huggingface_hub 1.18). Either way one concrete provider serves it.
    transport: Literal["provider", "router"] = "provider"
    # True when the provider answers a forced tool call without the model's
    # reasoning (Nemotron 3.5 Super VL on baseten: 0-1 reasoning tokens with a
    # forced tool, 1,516 with "auto", measured 2026-10-18). The route's requests
    # then think (its request options turn reasoning on), and Pydantic AI sends
    # tool_choice "auto" in place of a "required" it resolved itself, as
    # ModelProfile.forced_tool_choice_disables_thinking does for the providers
    # whose Pydantic AI models honour it (its HuggingFaceModel does not).
    forced_tool_choice_disables_thinking: bool = False

    def __post_init__(self) -> None:
        if self.structured_output_mode != "tool":
            raise ValueError("Hugging Face routes use schema-validated tool output.")
        if self.transport not in {"provider", "router"}:
            raise ValueError(
                "A Hugging Face route's transport is 'provider' or 'router'."
            )
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

    @property
    def served_model_name(self) -> str:
        """The model name its requests carry: on the router, "model_id:provider"."""
        if self.transport == "router":
            return f"{self.model_id}:{self.provider}"
        return self.model_id


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
            # Moved from DeepInfra on 2026-10-12: it refused 22 of 29 live
            # first-pass calls (HTTP 429/503); Novita answered 8 of 8 at the
            # same price and already serves the handwriting-qwen reader.
            provider="novita",
            # Novita runs the model's hidden reasoning in full, which stopped
            # about a fifth of first passes at the 4,096-token cap. "medium"
            # ended the cap stops and scored best against the reference
            # readings (HARNESS.md 5). Measured on Novita only: a provider
            # move re-measures it or clears it.
            request_options=(("reasoning_effort", "medium"),),
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
# The NVIDIA option (docs/product-requirements/NVIDIA_NEMOTRON_OPTION.md): one
# model, Nemotron 3.5 Super VL, for each stage SPECIMEN_NVIDIA_STAGES turns on
# (application/model_option.py). Baseten is its only Hugging Face provider, and
# huggingface_hub 1.18 has no helper for it, so the router serves these routes.
NEMOTRON_MODEL_ID = "nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4"
NVIDIA_HUGGINGFACE_ROUTES: Mapping[str, HuggingFaceInferenceRoute] = MappingProxyType(
    {
        "handwriting-nemotron": HuggingFaceInferenceRoute(
            route_id="handwriting-nemotron",
            logical_capability="handwriting_transcriber",
            model_id=NEMOTRON_MODEL_ID,
            provider="baseten",
            transport="router",
        ),
        "first-pass-nemotron": HuggingFaceInferenceRoute(
            route_id="first-pass-nemotron",
            logical_capability="transcription_first_pass",
            model_id=NEMOTRON_MODEL_ID,
            provider="baseten",
            transport="router",
            # Measured settings (NVIDIA_NEMOTRON_OPTION.md section 7, on
            # Baseten): the reasoning effort the first pass thinks at, and the
            # unforced output tool without which it skips its reasoning (see
            # forced_tool_choice_disables_thinking). Change them here.
            request_options=(("reasoning_effort", "low"),),
            forced_tool_choice_disables_thinking=True,
        ),
        "harness-nemotron": HuggingFaceInferenceRoute(
            route_id="harness-nemotron",
            logical_capability="field_harness",
            model_id=NEMOTRON_MODEL_ID,
            provider="baseten",
            transport="router",
            required_input_modalities=("text",),
        ),
    }
)
# The routes a profile may name as readers: the initial pair and the option's.
READER_HUGGINGFACE_ROUTES: Mapping[str, HuggingFaceInferenceRoute] = MappingProxyType(
    {
        **INITIAL_HUGGINGFACE_ROUTES,
        "handwriting-nemotron": NVIDIA_HUGGINGFACE_ROUTES["handwriting-nemotron"],
    }
)
# Every registered route: a run pinned to any of them resolves.
HUGGINGFACE_ROUTES: Mapping[str, HuggingFaceInferenceRoute] = MappingProxyType(
    {
        **INITIAL_HUGGINGFACE_ROUTES,
        **STAGE_HUGGINGFACE_ROUTES,
        **NVIDIA_HUGGINGFACE_ROUTES,
    }
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


class UnforcedOutputToolHuggingFaceModel(ArgumentPreservingHuggingFaceModel):
    """Let the model choose the tool where a forced tool call skips its reasoning.

    Pydantic AI resolves an agent that must end in its output tool to
    tool_choice "required". A provider that answers a forced tool call without
    the model's reasoning (HuggingFaceInferenceRoute.forced_tool_choice_disables_thinking)
    gets "auto" instead; a text answer then earns the agent's usual retry.
    """

    def _get_tool_choice(self, model_settings, model_request_parameters):  # type: ignore[override]
        tools, tool_choice = HuggingFaceModel._get_tool_choice(
            model_settings, model_request_parameters
        )
        return tools, "auto" if tool_choice == "required" else tool_choice


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
        if route.transport == "router":
            client = AsyncInferenceClient(
                base_url=HUGGINGFACE_ROUTER_URL,
                api_key=self._token.get_secret_value(),
                bill_to=self._bill_to or None,
                **timeout_options,
            )
        else:
            client = AsyncInferenceClient(
                provider=route.provider,
                api_key=self._token.get_secret_value(),
                bill_to=self._bill_to or None,
                **timeout_options,
            )
        provider = HuggingFaceProvider(
            hf_client=client, api_key=self._token.get_secret_value()
        )
        model_class = (
            UnforcedOutputToolHuggingFaceModel
            if route.forced_tool_choice_disables_thinking
            else ArgumentPreservingHuggingFaceModel
        )
        # The HF adapter sends a function schema, not native response_format.
        # Keep the transport explicit even if a future provider profile changes.
        return model_class(
            route.served_model_name,
            provider=provider,
            profile={
                "supports_tools": True,
                "supports_json_schema_output": False,
                "default_structured_output_mode": route.structured_output_mode,
            },
            # Model-level defaults: every agent on this route sends them, and
            # Pydantic AI merges them under each agent's and run's own settings.
            settings={"extra_body": dict(route.request_options)}
            if route.request_options
            else None,
        )
