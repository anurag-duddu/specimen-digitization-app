"""The pins a run's research job is created with and reopened against.

Every pin comes from committed configuration or from the installed code:
- the run's published collection profile: its harness route and that route's
  price row;
- source_readiness.py: source readiness and capture retention;
- the constants below: the output cap, the request bound and the tokenizer
  files the bound reasons about;
- installed code: the source registry, model_gateway.py's bytes, the acceptance
  validator, the prompts and the research profile.

``build_committed_pins`` returns every ``PinnedRuntime`` field except the
specimen's ``input_digest``. Job creation stores
``PinnedRuntime(input_digest=..., **pins)``; reopening the job rebuilds the
pins and holds the run when the stored ones differ. The registered_pins
validators run on the result before it is returned.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path

from specimen_digitization import model_gateway
from specimen_digitization.application.collection_profiles import (
    CollectionProfile as PublishedProfile,
)
from specimen_digitization.model_gateway import HUGGINGFACE_ROUTES
from .accepted_output import VALIDATOR_SOURCE_SHA256, VALIDATOR_VERSION, validation_boundary_pins
from .agents import specialist_output_schema_digest
from .contracts import CollectionProfile, FieldKey, SourceQuery, SourceResult, SpecialistRole, digest
from .evidence import insects_profile
from .gateway import ModelBinding, ModelGatewayBlocked
from .local_utility_proof_v2 import UTILITY_ROLES, UTILITY_VERSION
from .sources import SETTLEMENT_UTILITY_VERSION
from .package_qualification import SERIALIZATION_VERSION
from .persistence import HeldUnknown, PinnedRuntime, StaleWork
from .prompts import resolve_prompt
from .registered_pins import (registered_capture_policies, registered_model_prices,
    registered_model_request_guards, registered_registry)
from .source_capture_v2 import RegisteredCapturePolicyV2
from .source_readiness import CAPTURE_POLICIES, SOURCE_READINESS
from .sources import insects_registry

ENGINE_VERSION = "research_harness_v1"

# The organiser qualifies a narrow exact event or assembly from a keyed line,
# a same-line literal proposed by the ordinary extractor, or a unanimous explicit
# collection/determination date or measured elevation in both raw readers. Every
# other declared field, and any value that cannot be placed exactly, needs a
# qualified source or honest review. Declaring the missing
# policy here, as verbatim_dts declares its own, turns a specialist's waiting_policy
# on a declared field into the existing needs_human_review path with the reason
# mandatory_unresolved:{field} (canonical_materialization_v2._policy_held, status.py
# and the connector's disposition check, none of which names a field). A
# waiting_source is not held: a failed, rate-limited or unconfigured source still
# blocks the record. The v4 role prompts tell a specialist which of the two to return.
UNQUALIFIED_LABEL_POLICY = "unstructured_label_event_unqualified"
# These twelve fields have no external source configured in this deployment;
# exact qualified label evidence can still settle some of them. An unqualified
# remainder therefore has an explicit review path ...
UNQUALIFIED_LABEL_LITERAL_FIELDS = (
    FieldKey.DATE_VISITED_FROM, FieldKey.DATE_VISITED_TO, FieldKey.DATE_IDENTIFIED,
    FieldKey.ELEVATION_FROM_M, FieldKey.ELEVATION_TO_M, FieldKey.ELEVATION_FROM_FT,
    FieldKey.ELEVATION_TO_FT, FieldKey.COLLECTORS, FieldKey.FMNH_INS_NUMBER,
    FieldKey.COLLECTION_CODE, FieldKey.HABITAT, FieldKey.COLLECTION_METHOD)
# ... and the three that have a source but, for a label that names nothing to look up
# or a lookup that completes without a match, no other end state: county (GEOLocate
# confirms a county only inside the USA, so outside it no receipt exists to back a
# human question), city (only a place the label names can be queried) and taxon (a
# completed GBIF search with no match cannot become a human question). Their prompts
# keep waiting_source for a lookup that failed, timed out or was refused.
# country, province_state and precise_location are not declared: a GEOLocate no_match
# or ambiguous result on them is already a human question.
UNQUALIFIED_LABEL_LOOKUP_FIELDS = (FieldKey.COUNTY, FieldKey.CITY, FieldKey.TAXON)
UNQUALIFIED_LABEL_FIELDS = frozenset((*UNQUALIFIED_LABEL_LITERAL_FIELDS, *UNQUALIFIED_LABEL_LOOKUP_FIELDS))


def committed_research_profile(organization_id: str, collection_id: str) -> CollectionProfile:
    """The research profile every committed job pins: insects_profile, plus the
    missing policy of each field no unstructured label can ground."""
    base = insects_profile(organization_id, collection_id)
    return insects_profile(organization_id, collection_id, overrides=tuple(
        row.model_copy(update={"missing_policy": UNQUALIFIED_LABEL_POLICY})
        for row in base.fields if row.field_key in UNQUALIFIED_LABEL_FIELDS))


# Each request writes at most 4,096 output tokens: the gateway's own cap (gateway.ModelBinding)
# and the budget the geography prompt and test_five_human_questions_echoing_their_receipts_fit_one_response
# state. 2,048 (HARNESS.md G30, written for the single-agent field harness) can truncate a
# five-field geography answer. Counted offline with the pinned DeepSeek tokenizer on answers
# scripted for the ten pilot labels (Lane P, 2026-10-03; not a production observation), one
# is 2,072 to 2,468 tokens with every default key written and 1,465 to 1,815 with null keys
# omitted. The value is in the committed pins (model, settings): a job provisioned at another
# value is held research_committed_pins_changed.
MAX_OUTPUT_TOKENS = 4096

# The tokenizer files the request bound reasons about, read 2026-10-02 from
# deepseek-ai/DeepSeek-V4.1-Flash at hub commit 2cba9e42aa026125f3ed06c6d98c1db82f7ca027:
# https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/resolve/2cba9e42aa026125f3ed06c6d98c1db82f7ca027/tokenizer.json
# https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/resolve/2cba9e42aa026125f3ed06c6d98c1db82f7ca027/chat_template.jinja
# Each download's git blob sha1 matched the hub tree at that commit. Nothing
# installed carries these files, so their sha256 values are committed here.
TOKENIZER_PIN = {
    "hf_commit": "2cba9e42aa026125f3ed06c6d98c1db82f7ca027",  # pragma: allowlist secret (Hugging Face commit id)
    "tokenizer_json_sha256": "c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b",  # pragma: allowlist secret (Hugging Face file digest) gitleaks:allow
    "chat_template_jinja_sha256": "d959d804d5101b79a49b6ff1bf3c54cd5affa9a5a78c503d925f3090040b31c3",  # pragma: allowlist secret (Hugging Face file digest) gitleaks:allow
}

# The largest serialized request the guard admits, and its local size bound. The
# tokenizer is byte-level BPE, so every token covers at least one rendered
# byte, and the chat template adds at most one separator byte per byte of the
# compact serialization: 2 tokens a byte. 8,192 tokens cover the tool preamble
# and the per-turn special tokens. 262,144 bytes is a cap, not a measurement.
# It must stay at least 72 KB: with Lane G's version 2 geography prompt the
# last geography request is about 69 KB. This estimate is only a payload guard;
# the financial reservation below uses the provider's entire context window.
REQUEST_BOUND = {
    "maximum_serialized_bytes": 262_144,
    "tokens_per_utf8_byte_upper_bound": 2,
    "fixed_overhead_tokens": 8_192,
}

_READINESS_ORIGIN = "repo:src/specimen_digitization/research_harness/source_readiness.py"
_PROFILES_ORIGIN = "repo:src/specimen_digitization/application/profiles/published.json"


def _published_profile(profile) -> PublishedProfile:
    """A run's profile snapshot or a loaded profile, validated by the profile loader."""
    if isinstance(profile, PublishedProfile):
        profile = profile.model_dump(mode="json")
    if not isinstance(profile, Mapping):
        raise TypeError("committed research pins need a published collection profile")
    return PublishedProfile.model_validate(dict(profile))


def committed_harness_route(profile) -> str | None:
    """The profile's harness route, or None when it names no registered harness route.

    A registered harness route is a HUGGINGFACE_ROUTES key whose capability is
    field_harness and whose input is text only. A profile that does not
    validate has no harness route either.
    """
    try:
        route_id = _published_profile(profile).harness_route
    except (TypeError, ValueError):
        return None
    route = HUGGINGFACE_ROUTES.get(route_id) if route_id else None
    if (route is None or route.logical_capability != "field_harness"
        or tuple(route.required_input_modalities) != ("text",)):
        return None
    return route_id


def committed_run_cost_limit_micros(profile) -> int:
    """The profile's allowance for one run, in micro-dollars."""
    processing = _published_profile(profile).processing
    if processing is None:
        raise ValueError("research_committed_run_cost_limit_missing")
    return processing.run_cost_limit_micros


def _committed_registry():
    present = {policy.id for policy in insects_registry().policies}
    return insects_registry(qualification_overrides={source_id: dict(row)
        for source_id, row in SOURCE_READINESS.items() if source_id in present})


def _capture_policies(registry) -> dict:
    present = {policy.id for policy in registry.policies}
    rows = {}
    for source_id, (kind, maximum) in CAPTURE_POLICIES.items():
        if source_id not in present:
            continue
        rows[source_id] = RegisteredCapturePolicyV2(
            source_id=source_id, source_policy_digest=digest(registry.get(source_id)), kind=kind,
            # The committed row's own digest, so editing one row leaves the others alone.
            owner_registration_digest=digest(
                {"source_id": source_id, "kind": kind, "maximum_responses": maximum}),
            owner_registration_origin=f"{_READINESS_ORIGIN}#CAPTURE_POLICIES.{source_id}",
            maximum_responses=maximum).model_dump(mode="json")
    return rows


def _acceptance_boundary() -> dict:
    return {"contract_version": "research-acceptance-boundary/v1",
        "validator_version": VALIDATOR_VERSION, "validator_source_sha256": VALIDATOR_SOURCE_SHA256,
        **validation_boundary_pins()}


def _toolset_digest() -> str:
    # The two tools every specialist registers (SpecialistHarness._register_tools)
    # and the deterministic utilities behind invoke_utility.
    return digest({"contract_version": "research-toolset/v1",
        "tools": ["lookup_source", "invoke_utility"],
        "utility_roles": {name: str(role) for name, role in sorted(UTILITY_ROLES.items())},
        "utility_version": UTILITY_VERSION,
        "settlement_utility_version": SETTLEMENT_UTILITY_VERSION,
        "source_query_schema": SourceQuery.model_json_schema(),
        "source_result_schema": SourceResult.model_json_schema()})


def _harness_binding(profile: PublishedProfile):
    route_id = committed_harness_route(profile)
    prices = profile.processing.price_list if profile.processing else None
    if route_id is None or prices is None or route_id not in prices.models:
        raise ValueError("research_committed_harness_route_unavailable")
    route = HUGGINGFACE_ROUTES[route_id]
    # The route's row in the profile's price list. For harness-deepseek
    # (deepseek-ai/DeepSeek-V4.1-Flash on DeepInfra) it is the list price,
    # USD 0.20 / 0.60 per 1M input / output tokens, read 2026-10-02 from the
    # Hugging Face router's deepinfra entry (https://router.huggingface.co/v1/models)
    # and from https://deepinfra.com/deepseek-ai/DeepSeek-V4.1-Flash.
    price = prices.models[route_id]
    # A tokenizer/template heuristic cannot prove the billable input bound.
    # Reserve the full documented provider context, including schemas/history,
    # plus the enforced generation cap. Provider page checked 2026-10-05: the
    # window is 1,048,576, standard list rates remain USD 0.20 / 0.60 above
    # current promotional rates. No priority tier or automatic retry is sent.
    max_input = price.context_tokens
    if type(max_input) is not int or max_input != 1_048_576:
        raise ValueError("research_committed_context_bound_unavailable")
    if (REQUEST_BOUND["maximum_serialized_bytes"] * REQUEST_BOUND["tokens_per_utf8_byte_upper_bound"]
            + REQUEST_BOUND["fixed_overhead_tokens"] > max_input):
        raise ValueError("research_committed_request_bound_exceeds_context")
    # Each request reserves its worst case, rounded up as RegisteredModelPriceV1 does.
    reservation = (max_input * price.input_micros_per_million
        + MAX_OUTPUT_TOKENS * price.output_micros_per_million + 999_999) // 1_000_000
    try:
        binding = ModelBinding(route.route_id, route.model_id, route.provider, MAX_OUTPUT_TOKENS,
            reservation, prices.version)
    except ModelGatewayBlocked as error:
        raise ValueError(f"research_committed_pins_rejected: {error}") from error
    owner = {"owner_registration_digest": profile.digest, "owner_registration_origin":
        f"{_PROFILES_ORIGIN}#{profile.id}@{profile.version}"
        f"/processing.price_list.models.{route_id}@{prices.version}"}
    route_pin = {"route_id": route.route_id, "model_id": route.model_id,
        "provider": route.provider, "price_version": prices.version}
    price_row = {"contract_version": "registered-model-price/v1", "currency": "USD", **route_pin,
        "input_micro_usd_per_million_tokens": price.input_micros_per_million,
        "output_micro_usd_per_million_tokens": price.output_micros_per_million,
        "max_input_tokens": max_input, **owner,
        "rate_source_sha256": digest({"route_id": route_id, "price_list_version": prices.version,
            "as_of": prices.as_of, "sources": list(prices.sources),
            "price": price.model_dump(mode="json")})}
    bound_row = {"contract_version": "registered-text-request-bound/v1", **route_pin,
        "serialization_version": SERIALIZATION_VERSION,
        "gateway_source_sha256": hashlib.sha256(Path(model_gateway.__file__).read_bytes()).hexdigest(),
        "tokenizer_source_sha256": TOKENIZER_PIN["tokenizer_json_sha256"],
        "chat_template_source_sha256": TOKENIZER_PIN["chat_template_jinja_sha256"],
        "bound_source_sha256": digest({"contract_version": "byte-level-bpe-2x-template/v1",
            **TOKENIZER_PIN, **REQUEST_BOUND}),
        **owner, **REQUEST_BOUND}
    return binding, price_row, bound_row


def _self_check(pins: dict, registry) -> None:
    """Read the pins back the way the registered runtime does."""
    sources = pins["sources"]
    try:
        if registered_registry(sources).digest != registry.digest:
            raise ValueError("research_committed_registry_digest_differs")
        registered_capture_policies(sources, registry)
        bindings = {}
        for role in SpecialistRole:
            data = dict(pins["model"][str(role)])
            route = data.pop("route")
            bindings[role] = ModelBinding(**data)
            if bindings[role].route_id != route:
                raise ValueError("research_committed_model_route_differs")
        registered_model_prices(sources, bindings)
        registered_model_request_guards(sources, bindings)
    except (HeldUnknown, StaleWork, ModelGatewayBlocked) as error:
        raise ValueError(f"research_committed_pins_rejected: {error}") from error


def build_committed_pins(profile, *, organization_id: str, collection_id: str) -> dict:
    """Every pin of the run's research job except ``input_digest``.

    ``profile`` is the run's profile snapshot (``run.profile_snapshot``) or a
    loaded published ``CollectionProfile``. The result is JSON in the form
    ``PinnedRuntime.payload()`` stores, and two calls on the same inputs and
    installed code return equal dicts.
    """
    if any(type(value) is not str or not value for value in (organization_id, collection_id)):
        raise ValueError("research_committed_scope_missing")
    profile = _published_profile(profile)
    registry = _committed_registry()
    binding, price_row, bound_row = _harness_binding(profile)
    if binding.reservation_micro_usd > committed_run_cost_limit_micros(profile):
        raise ValueError("research_committed_reservation_exceeds_run_limit")
    roles = tuple(SpecialistRole)
    research_profile = committed_research_profile(organization_id, collection_id)
    toolset, schema = _toolset_digest(), specialist_output_schema_digest()
    prompts = {str(role): resolve_prompt(role, profile_digest=digest(research_profile),
        source_registry_digest=registry.digest, toolset_digest=toolset,
        model_route=binding.route_id, output_schema_digest=schema).model_dump(mode="json")
        for role in roles}
    sources = {"registry_digest": registry.digest,
        "registry_policies": [policy.model_dump(mode="json") for policy in registry.policies],
        "capture_policies": _capture_policies(registry),
        "acceptance_boundary": _acceptance_boundary(),
        "model_prices": {str(role): price_row for role in roles},
        "model_request_bounds": {str(role): bound_row for role in roles}}
    # Normalised exactly as create_job stores them; input_digest is the job's own.
    pins = PinnedRuntime(input_digest="", profile=research_profile.model_dump(mode="json"),
        prompts=prompts, sources=sources,
        model={str(role): {"route": binding.route_id, **asdict(binding)} for role in roles},
        settings={"max_tokens": MAX_OUTPUT_TOKENS}, engine_version=ENGINE_VERSION).payload()
    del pins["input_digest"]
    _self_check(pins, registry)
    return pins
