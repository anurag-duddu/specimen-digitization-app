"""Pinned model requests pass through the application effect ledger before send."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol

from pydantic import TypeAdapter
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings

from specimen_digitization.model_gateway import (
    HUGGINGFACE_ROUTES, ArgumentPreservingHuggingFaceModel, HuggingFaceModelGateway,
)
from specimen_digitization.provider_privacy import PrivateProviderModel

from .agent_trace import annotate_cost, record_request_cost
from .package_qualification import SERIALIZATION_VERSION
from .telemetry import ResearchTrace, TraceIdentity

LOGGER = logging.getLogger(__name__)
_RESPONSE = TypeAdapter(ModelResponse)
_PARAMETERS = TypeAdapter(ModelRequestParameters)


class ModelEffectBroker(Protocol):
    async def execute(self, *, scope: Any, lease: Any, operation_key: str,
                      request: dict, reservation_micro_usd: int,
                      dispatch: Callable, execution_class: str,
                      field_keys: tuple[str, ...]) -> Any: ...


class ModelGatewayBlocked(RuntimeError):
    """The call cannot satisfy its pinned model/effect contract."""


@dataclass(frozen=True)
class ModelBinding:
    """Already admitted route, settings and conservative per-request liability."""

    route_id: str
    model_id: str
    provider: str
    max_tokens: int
    reservation_micro_usd: int
    price_version: str

    def __post_init__(self):
        route = HUGGINGFACE_ROUTES.get(self.route_id)
        if route is None or (route.model_id, route.provider) != (self.model_id, self.provider):
            raise ModelGatewayBlocked("unqualified_model_route")
        if (type(self.max_tokens) is not int or not 0 < self.max_tokens <= 4096
            or type(self.reservation_micro_usd) is not int or self.reservation_micro_usd <= 0
            or type(self.price_version) is not str or not self.price_version):
            raise ModelGatewayBlocked("missing_or_invalid_model_budget_pin")


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def _stable_messages(messages) -> list[dict]:
    """Discard transport identities only, preserving scientific argument content."""
    data = ModelMessagesTypeAdapter.dump_python(messages, mode="json")
    for message in data:
        for key in ("timestamp", "run_id", "conversation_id", "metadata", "provider_details",
                    "provider_response_id", "usage"):
            message.pop(key, None)
        for part in message.get("parts", []):
            for key in ("timestamp", "tool_call_id", "id", "provider_details"):
                part.pop(key, None)
    return data


class EffectModel(WrapperModel):
    """Every actual request, including delegated requests, reserves and captures.

    Streaming, model compaction and provider token counting are deliberately
    closed until they have their own recoverable effect adapters. This avoids
    inheriting the ungated passthroughs of ``WrapperModel``.
    """

    def __init__(self, wrapped: Model, *, broker: ModelEffectBroker, scope: Any,
                 lease: Any, role: str, binding: ModelBinding, pins: Mapping[str, Any],
                 model_settings: Mapping[str, Any] | None = None,
                 actual_cost: Callable[[ModelResponse], int | None] | None = None,
                 request_guard: Callable[[list, dict, dict], dict] | None = None):
        offline = isinstance(wrapped, (FunctionModel, TestModel))
        if not offline and (not isinstance(wrapped, ArgumentPreservingHuggingFaceModel)
                            or wrapped.model_name != binding.model_id
                            or wrapped.provider.client.provider != binding.provider):
            raise ModelGatewayBlocked("wrapped_model_does_not_match_qualified_gateway")
        if not offline and not callable(request_guard):
            raise ModelGatewayBlocked("live_request_liability_guard_missing")
        super().__init__(PrivateProviderModel(wrapped))
        self.broker, self.scope, self.lease = broker, scope, lease
        self.role, self.binding = role, binding
        # JSON snapshot prevents a mutable caller mapping changing resumed pins.
        self.pins = json.loads(json.dumps(dict(pins), sort_keys=True))
        settings = dict(model_settings or {})
        if settings.get("max_tokens", binding.max_tokens) != binding.max_tokens:
            raise ModelGatewayBlocked("model_settings_differ_from_pin")
        settings["max_tokens"] = binding.max_tokens
        self.expected_settings = MappingProxyType(json.loads(json.dumps(settings, sort_keys=True)))
        self.actual_cost = actual_cost
        self.request_guard = request_guard
        self.execution_class = "offline" if offline else "live"
        self.effect_ids: list[str] = []
        # effect id -> the receipt's settled micro-USD (None: not priced), for the run's trace spans.
        self.effect_costs: dict[str, int | None] = {}
        self.trace = ResearchTrace(TraceIdentity(scope.specimen_id, scope.job_id, scope.generation))

    async def request(self, messages, model_settings, model_request_parameters):
        from .persistence import CapturedResult

        settings = dict(model_settings or {})
        settings.setdefault("max_tokens", self.binding.max_tokens)
        if settings != dict(self.expected_settings):
            raise ModelGatewayBlocked("model_settings_differ_from_pin")
        parameters = _PARAMETERS.dump_python(model_request_parameters, mode="json")
        liability = None
        if self.request_guard is not None:
            # Inspect the complete serialized dialogue and tool/output schemas,
            # before even creating a reservation or reaching provider dispatch.
            liability = self.request_guard(
                ModelMessagesTypeAdapter.dump_python(messages, mode="json"), parameters, settings)
            if type(liability) is not dict:
                raise ModelGatewayBlocked("request_liability_guard_result_unproved")
        request = {
            "messages_digest": _digest(_stable_messages(messages)),
            "parameters_digest": _digest(parameters),
            "settings": settings,
            "route_id": self.binding.route_id,
        }
        if liability is not None:
            request["input_liability"] = liability
        pins = {**self.pins, "role": self.role, "route_id": self.binding.route_id,
                "requested_model": self.binding.model_id, "provider": self.binding.provider,
                "price_version": self.binding.price_version,
                "serialization_version": SERIALIZATION_VERSION}

        async def dispatch(attempt_id, provider_idempotency_key):
            # HF does not expose a qualified provider idempotency parameter.
            # Unknown responses remain held by the broker rather than retried.
            with self.trace.span("effect", role=self.role, attempt_id=attempt_id):
                response = await self.wrapped.request(messages, settings, model_request_parameters)
            payload = _RESPONSE.dump_python(response, mode="json")
            return CapturedResult(
                typed_payload=payload,
                raw_payload=payload,
                actual_micro_usd=self.actual_cost(response) if self.actual_cost else None,
                provider_request_id=response.provider_response_id,
                usage=TypeAdapter(type(response.usage)).dump_python(response.usage, mode="json"),
            )

        metadata = {"role": self.role, "field_keys": tuple(self.pins["field_keys"])}
        if "prompt_digest" in self.pins:
            metadata["prompt_digest"] = self.pins["prompt_digest"]
        with self.trace.span("model", **metadata) as span:
            receipt = await self.broker.execute(
                scope=self.scope, lease=self.lease, operation_key=f"model:{self.role}",
                request={**request, "pins": pins},
                reservation_micro_usd=self.binding.reservation_micro_usd, dispatch=dispatch,
                execution_class=self.execution_class,
                field_keys=tuple(self.pins["field_keys"]),
            )
            span.set_attribute("research.effect_id", receipt.effect_id)
            span.set_attribute("research.attempt_id", receipt.attempt_id)
            self._trace_cost(span, receipt)
        self.effect_ids.append(receipt.effect_id)
        return _RESPONSE.validate_python(receipt.typed_payload)

    def _trace_cost(self, span, receipt) -> None:
        """The settled cost of this request from its receipt, for the request's trace spans.

        None when the provider's usage cannot price it: the effect stays held for that amount,
        and the span says "unknown" rather than zero. The request has been paid for and its
        receipt settled, so nothing here may fail it: telemetry can never fail an effect.
        """
        try:
            self.effect_costs[receipt.effect_id] = receipt.actual_micro_usd
            annotate_cost(self.trace, span, [receipt.actual_micro_usd])
            record_request_cost(receipt.actual_micro_usd)
        except Exception as error:
            LOGGER.debug("trace_cost_failed: %s", type(error).__name__)

    @asynccontextmanager
    async def request_stream(self, *args, **kwargs):
        raise ModelGatewayBlocked("streaming_effect_adapter_not_qualified")
        yield  # pragma: no cover

    async def count_tokens(self, *args, **kwargs):
        raise ModelGatewayBlocked("token_count_effect_adapter_not_qualified")

    async def compact_messages(self, *args, **kwargs):
        raise ModelGatewayBlocked("compaction_effect_adapter_not_qualified")

    async def cancel_suspended_response(self, *args, **kwargs):
        raise ModelGatewayBlocked("suspended_response_effect_adapter_not_qualified")


def bound_huggingface_model(*, gateway: HuggingFaceModelGateway, broker: ModelEffectBroker,
                           scope: Any, lease: Any, role: str, binding: ModelBinding,
                           pins: Mapping[str, Any], model_settings=None,
                           actual_cost=None, request_guard=None) -> EffectModel:
    """Reuse the registered argument-preserving HF gateway without route fallback."""
    return EffectModel(gateway.model_for(binding.route_id), broker=broker, scope=scope,
                       lease=lease, role=role, binding=binding, pins=pins,
                       model_settings=model_settings,
                       actual_cost=actual_cost, request_guard=request_guard)
