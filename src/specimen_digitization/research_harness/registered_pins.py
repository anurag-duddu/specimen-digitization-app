"""Read immutable registered source and numeric price pins; never invent rates."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .contracts import digest
from .persistence import HeldUnknown, StaleWork
from .sources import SourcePolicy, SourceRegistry, insects_registry


_READINESS = {"qualification_state", "qualification_receipt", "schema_digest", "source_release"}


def registered_registry(source_pins):
    raw = source_pins.get("registry_policies")
    base = insects_registry()
    if type(raw) is not list or len(raw) != len(base.policies):
        raise HeldUnknown("research_registered_source_policies_missing")
    policies, identities = [], set()
    for row in raw:
        if type(row) is not dict or type(row.get("id")) is not str:
            raise StaleWork("research_source_policy_shape_changed")
        policy = SourcePolicy.model_validate(row)
        original = base.get(policy.id)
        actual, expected = policy.model_dump(mode="json"), original.model_dump(mode="json")
        if (actual != row or policy.id in identities
            or {key:value for key,value in actual.items() if key not in _READINESS}
            != {key:value for key,value in expected.items() if key not in _READINESS}):
            raise StaleWork("research_registered_source_capability_expanded")
        identities.add(policy.id)
        policies.append(policy)
    if identities != {item.id for item in base.policies}:
        raise StaleWork("research_source_registry_membership_changed")
    registry = SourceRegistry(policies)
    if registry.digest != source_pins.get("registry_digest"):
        raise StaleWork("research_source_registry_pin_changed")
    return registry


def registered_capture_policies(source_pins, registry):
    from .source_capture_v2 import RegisteredCapturePolicyV2
    raw = source_pins.get("capture_policies")
    if type(raw) is not dict or not raw:
        raise HeldUnknown("research_registered_capture_policy_missing")
    policies = {}
    for source_id, row in raw.items():
        policy = RegisteredCapturePolicyV2.model_validate(row)
        source = registry.get(source_id)
        if (policy.source_id != source_id or policy.model_dump(mode="json") != row
            or policy.source_policy_digest != digest(source)):
            raise StaleWork("research_capture_policy_source_pin_changed")
        policies[source_id] = policy
    # Unqualified/denied sources are never silently changed to full-body capture.
    # The actual broker refuses Google until its approved minimal adapter exists.
    return policies


@dataclass(frozen=True)
class RegisteredModelPriceV1:
    route_id: str
    model_id: str
    provider: str
    price_version: str
    input_micro_usd_per_million_tokens: int
    output_micro_usd_per_million_tokens: int
    max_input_tokens: int
    owner_registration_digest: str
    owner_registration_origin: str
    rate_source_sha256: str

    @classmethod
    def from_registered(cls, binding, raw):
        fields = set(cls.__dataclass_fields__)
        if (type(raw) is not dict or set(raw) != fields | {"contract_version", "currency"}
            or raw["contract_version"] != "registered-model-price/v1" or raw["currency"] != "USD"):
            raise HeldUnknown("research_registered_numeric_price_missing")
        value = cls(**{key:raw[key] for key in fields})
        if ((value.route_id,value.model_id,value.provider,value.price_version)
            != (binding.route_id,binding.model_id,binding.provider,binding.price_version)
            or any(type(getattr(value,key)) is not int or getattr(value,key) < 0 for key in
                ("input_micro_usd_per_million_tokens", "output_micro_usd_per_million_tokens"))
            or type(value.max_input_tokens) is not int or not 0 < value.max_input_tokens <= 1_000_000
            or any(type(getattr(value,key)) is not str or len(getattr(value,key)) != 64
                or any(character not in "0123456789abcdef" for character in getattr(value,key))
                for key in ("owner_registration_digest", "rate_source_sha256"))
            or type(value.owner_registration_origin) is not str or not value.owner_registration_origin):
            raise HeldUnknown("research_registered_numeric_price_unqualified")
        maximum = (value.max_input_tokens*value.input_micro_usd_per_million_tokens
            + binding.max_tokens*value.output_micro_usd_per_million_tokens + 999_999) // 1_000_000
        if maximum > binding.reservation_micro_usd:
            raise HeldUnknown("research_model_reservation_below_registered_liability")
        return value

    def actual_cost(self, response):
        usage = response.usage
        inputs, outputs = getattr(usage,"input_tokens",None), getattr(usage,"output_tokens",None)
        # Discounts/extra billed dimensions need a separately versioned adapter.
        # An unknown amount stays held; it is never recorded as zero.
        if (type(inputs) is not int or type(outputs) is not int or inputs <= 0 or outputs <= 0
            or inputs > self.max_input_tokens
            or getattr(usage,"cache_read_tokens",0) != 0 or getattr(usage,"cache_write_tokens",0) != 0
            or getattr(usage,"audio_tokens",0) != 0):
            return None
        numerator = inputs*self.input_micro_usd_per_million_tokens + outputs*self.output_micro_usd_per_million_tokens
        return (numerator + 999_999) // 1_000_000


def registered_model_prices(source_pins, bindings):
    raw = source_pins.get("model_prices")
    if type(raw) is not dict or set(raw) != {str(role) for role in bindings}:
        raise HeldUnknown("research_registered_model_prices_missing")
    return {role:RegisteredModelPriceV1.from_registered(binding, raw[str(role)]).actual_cost
        for role,binding in bindings.items()}


@dataclass(frozen=True)
class RegisteredTextRequestBoundV1:
    """A reviewed upper bound, never a heuristic tokenizer estimate.

    The retained authority proves that this exact text-only serialization and
    route's chat template/tokenizer use no more than multiplier * UTF-8 bytes
    plus fixed overhead tokens. The implementation supplies no such authority
    or provider rate. Missing proof remains an admission HOLD.
    """
    route_id: str
    model_id: str
    provider: str
    price_version: str
    serialization_version: str
    gateway_source_sha256: str
    tokenizer_source_sha256: str
    chat_template_source_sha256: str
    bound_source_sha256: str
    owner_registration_digest: str
    owner_registration_origin: str
    maximum_serialized_bytes: int
    tokens_per_utf8_byte_upper_bound: int
    fixed_overhead_tokens: int

    @classmethod
    def from_registered(cls, binding, price, raw):
        from .package_qualification import SERIALIZATION_VERSION
        from specimen_digitization import model_gateway
        fields = set(cls.__dataclass_fields__)
        if (type(raw) is not dict or set(raw) != fields | {"contract_version"}
            or raw["contract_version"] != "registered-text-request-bound/v1"):
            raise HeldUnknown("research_registered_input_liability_bound_missing")
        value = cls(**{key:raw[key] for key in fields})
        if ((value.route_id,value.model_id,value.provider,value.price_version)
            != (binding.route_id,binding.model_id,binding.provider,binding.price_version)
            or value.serialization_version != SERIALIZATION_VERSION
            or value.owner_registration_digest != price.owner_registration_digest
            or value.owner_registration_origin != price.owner_registration_origin
            or any(type(getattr(value,key)) is not str or len(getattr(value,key)) != 64
                or any(character not in "0123456789abcdef" for character in getattr(value,key))
                for key in ("gateway_source_sha256","tokenizer_source_sha256",
                    "chat_template_source_sha256","bound_source_sha256","owner_registration_digest"))
            or type(value.maximum_serialized_bytes) is not int or not 0 < value.maximum_serialized_bytes <= 1_000_000
            or type(value.tokens_per_utf8_byte_upper_bound) is not int or not 1 <= value.tokens_per_utf8_byte_upper_bound <= 16
            or type(value.fixed_overhead_tokens) is not int or not 0 <= value.fixed_overhead_tokens <= 1_000_000
            or value.gateway_source_sha256 != hashlib.sha256(Path(model_gateway.__file__).read_bytes()).hexdigest()
            or value.maximum_serialized_bytes * value.tokens_per_utf8_byte_upper_bound
                + value.fixed_overhead_tokens > price.max_input_tokens):
            raise HeldUnknown("research_registered_input_liability_bound_unqualified")
        return value

    def validate(self, messages, parameters, settings):
        if type(messages) is not list or not messages:
            raise HeldUnknown("research_input_liability_messages_unproved")
        # This version has no image/audio/URL/binary download adapter. Only
        # literal user text and the ordinary text/tool dialogue are admitted.
        allowed = {"system-prompt","user-prompt","tool-return","retry-prompt",
            "text","tool-call","thinking"}
        for message in messages:
            if type(message) is not dict or type(message.get("parts")) is not list:
                raise HeldUnknown("research_input_liability_messages_unproved")
            for part in message["parts"]:
                if (type(part) is not dict or part.get("part_kind") not in allowed
                    or part.get("part_kind") in {"user-prompt","system-prompt"}
                        and type(part.get("content")) is not str):
                    raise HeldUnknown("research_input_liability_modality_unqualified")
        try:
            body = json.dumps({"messages":messages,"parameters":parameters,"settings":settings},
                sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
        except (ValueError,TypeError,RecursionError):
            raise HeldUnknown("research_input_liability_serialization_unproved") from None
        if len(body) > self.maximum_serialized_bytes:
            raise HeldUnknown("research_input_liability_bound_exceeded")
        # Stable contract metadata enters the effect identity; timestamps and
        # transient tool IDs do not cause a duplicate paid request on replay.
        return {"contract_version":"registered-text-request-bound/v1",
            "bound_digest":digest(self.__dict__),"serialization_version":self.serialization_version}


def registered_model_request_guards(source_pins, bindings):
    prices, bounds = source_pins.get("model_prices"), source_pins.get("model_request_bounds")
    roles = {str(role) for role in bindings}
    if type(prices) is not dict or type(bounds) is not dict or set(prices) != roles or set(bounds) != roles:
        raise HeldUnknown("research_registered_input_liability_bound_missing")
    return {role:RegisteredTextRequestBoundV1.from_registered(binding,
        RegisteredModelPriceV1.from_registered(binding,prices[str(role)]),bounds[str(role)]).validate
        for role,binding in bindings.items()}
