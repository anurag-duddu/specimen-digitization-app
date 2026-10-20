"""The NVIDIA option's switch and the profile variant it loads.

docs/product-requirements/NVIDIA_NEMOTRON_OPTION.md, sections 2 and 3:
SPECIMEN_NVIDIA_STAGES names the stages that run on Nemotron; with any stage on,
the published profiles load as a variant whose version names the stages.
"""

import json
import re
from types import SimpleNamespace

import pytest

from specimen_digitization.application.api import SYNTHETIC_COLLECTION
from specimen_digitization.application.collection_profiles import (
    PUBLISHED_PROFILES,
    CollectionProfileRegistry,
    published_registry,
)
from specimen_digitization.application.collection_runtime import classify_and_select
from specimen_digitization.application.domain import Profile, Region, Run
from specimen_digitization.application.lane import queue
from specimen_digitization.application.model_option import (
    SETTING,
    ModelOptionConfigurationError,
    nvidia_stages,
    nvidia_variant,
)
from specimen_digitization.application.production import ProductionAdapters
from specimen_digitization.application.profile_runtime import (
    pinned_risk_resolution,
    published_risk_registry,
)
from specimen_digitization.application.storage import LocalBlobs

from test_lane_profile import USER
from test_lane_trigger import specimen_with

ALL = "readers,first_pass,field_research"
VARIANT = "1.0.0+nvidia.readers.first-pass.field-research"
NEMOTRON = "nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4"
BASETEN = {"model_id": NEMOTRON, "provider": "baseten"}
MUSE = {"model_id": "meta-models/Muse-Glimmer-30B", "provider": "deepinfra"}


def as_published() -> CollectionProfileRegistry:
    """The published file as written, with no option applied."""
    return CollectionProfileRegistry.model_validate(json.loads(PUBLISHED_PROFILES.read_text()))


def published_profile() -> dict:
    return as_published().resolve("insects").profile.model_dump(mode="json")


# The switch.


@pytest.mark.parametrize("value", [None, "", " ", "\t\n"])
def test_unset_or_blank_is_off(value):
    environ = {} if value is None else {SETTING: value}

    assert nvidia_stages(environ) == ()
    assert published_registry(environ=environ).model_dump(mode="json") == (
        as_published().model_dump(mode="json")
    )


def test_with_the_switch_unset_the_published_profile_loads_as_written(monkeypatch):
    monkeypatch.delenv(SETTING, raising=False)

    profile = published_registry().resolve("insects").profile

    assert profile.digest == as_published().resolve("insects").profile.digest
    assert (profile.version, profile.model_routes, profile.first_pass_route, profile.harness_route) == (
        "1.0.0",
        ("handwriting-qwen", "handwriting-muse"),
        "first-pass-glm",
        "harness-deepseek",
    )


@pytest.mark.parametrize(
    "value,stages",
    [
        ("readers", ("readers",)),
        ("first_pass", ("first_pass",)),
        ("field_research", ("field_research",)),
        # Named in any order, with spaces around the names: the canonical order.
        (" field_research , readers ", ("readers", "field_research")),
        (ALL, ("readers", "first_pass", "field_research")),
        ("readers,readers", ("readers",)),
    ],
)
def test_the_switch_names_a_subset_of_the_stages(value, stages):
    assert nvidia_stages({SETTING: value}) == stages


@pytest.mark.parametrize(
    "value",
    [
        "gpu-secret-value",
        "readers,gpu-secret-value",
        "Readers",
        "first-pass",
        "on",
        "all",
        "true",
        "readers,",
        ",readers",
        "readers,,first_pass",
        "readers;first_pass",
        "readers first_pass",
    ],
)
def test_any_other_value_raises_naming_the_setting_never_the_value(value):
    with pytest.raises(ModelOptionConfigurationError) as caught:
        nvidia_stages({SETTING: value})

    # A ValueError, as the drain's other settings raise (worker._execute_drain).
    assert isinstance(caught.value, ValueError)
    assert SETTING in str(caught.value)
    assert "gpu-secret-value" not in str(caught.value)


def test_a_mistyped_switch_stops_the_profiles_from_loading(monkeypatch):
    monkeypatch.setenv(SETTING, "readers,gpu-secret-value")

    with pytest.raises(ModelOptionConfigurationError) as caught:
        published_registry()

    assert SETTING in str(caught.value) and "gpu-secret-value" not in str(caught.value)


# The variant.


@pytest.mark.parametrize(
    "value,suffix,changes",
    [
        ("readers", "readers", {"model_routes": ["handwriting-nemotron", "handwriting-muse"]}),
        ("first_pass", "first-pass", {"first_pass_route": "first-pass-nemotron"}),
        ("field_research", "field-research", {"harness_route": "harness-nemotron"}),
        (
            "field_research,first_pass",
            "first-pass.field-research",
            {"first_pass_route": "first-pass-nemotron", "harness_route": "harness-nemotron"},
        ),
        (
            ALL,
            "readers.first-pass.field-research",
            {
                "model_routes": ["handwriting-nemotron", "handwriting-muse"],
                "first_pass_route": "first-pass-nemotron",
                "harness_route": "harness-nemotron",
            },
        ),
    ],
)
def test_each_stage_changes_only_its_own_routes_and_the_version(value, suffix, changes):
    profile = published_registry(environ={SETTING: value}).resolve("insects").profile

    # Everything else, the processing allowance and its price list included,
    # is the published profile's.
    assert profile.model_dump(mode="json") == {
        **published_profile(),
        **changes,
        "version": "1.0.0+nvidia." + suffix,
    }


def test_the_variant_replaces_the_profile_and_its_mapping_names_the_variant():
    base = as_published()

    registry = published_registry({"private-collection-id": "insects"}, environ={SETTING: ALL})

    assert [profile.version for profile in registry.profiles] == [VARIANT]
    assert [mapping.model_dump() for mapping in registry.mappings] == [
        {"collection_id": "insects", "profile_id": "zoology_insects_slides", "profile_version": VARIANT}
    ]
    assert registry.resolve("private-collection-id").profile.version == VARIANT
    assert (registry.version, registry.nodes) == (base.version, base.nodes)


def test_the_variant_version_is_semantic_versioning_build_metadata():
    version = published_registry(environ={SETTING: ALL}).profiles[0].version

    core, build = version.split("+")
    assert core == "1.0.0"
    assert build.split(".")[0] == "nvidia"
    # Build identifiers allow ASCII alphanumerics and hyphens only (semver.org, item 10).
    assert all(re.fullmatch(r"[0-9A-Za-z-]+", identifier) for identifier in build.split("."))


def test_a_profile_version_with_build_metadata_of_its_own_is_refused():
    data = json.loads(PUBLISHED_PROFILES.read_text())
    data["profiles"][0]["version"] = "1.0.0+local"
    data["mappings"][0]["profile_version"] = "1.0.0+local"

    with pytest.raises(ValueError, match="build metadata"):
        nvidia_variant(CollectionProfileRegistry.model_validate(data), ("readers",))


def test_a_profile_that_does_not_price_an_nvidia_route_cannot_load_its_variant():
    data = json.loads(PUBLISHED_PROFILES.read_text())
    del data["profiles"][0]["processing"]["price_list"]["models"]["harness-nemotron"]
    registry = CollectionProfileRegistry.model_validate(data)

    assert nvidia_variant(registry, ("readers",)).profiles[0].harness_route == "harness-deepseek"
    with pytest.raises(ValueError, match="price every route"):
        nvidia_variant(registry, ("field_research",))


# A run under the variant.


def variant_run(tmp_path, monkeypatch, value=ALL):
    """A run the API queued and the worker classified, both under the option."""
    monkeypatch.setenv(SETTING, value)
    registry = published_registry({SYNTHETIC_COLLECTION: "insects"})
    specimen = specimen_with(Run(profile=Profile(synthetic=False)))
    queue(specimen, registry, USER)
    issue = classify_and_select(
        specimen, registry, None, LocalBlobs(tmp_path), published_risk_registry()
    )
    assert issue is None
    run = specimen.run
    run.dependencies = ProductionAdapters.pin_dependencies(SimpleNamespace(classifier=None), run)
    return specimen


def test_a_run_classified_under_the_variant_pins_the_nvidia_routes_on_baseten(
    tmp_path, monkeypatch
):
    from specimen_digitization.research_harness.committed_pins import committed_harness_route

    run = variant_run(tmp_path, monkeypatch).run

    assert (run.profile.id, run.profile.version) == ("zoology_insects_slides", VARIANT)
    assert run.profile.routes == ("handwriting-nemotron", "handwriting-muse")
    assert run.profile.first_pass_route == "first-pass-nemotron"
    assert (run.profile_snapshot["version"], run.profile_snapshot["harness_route"]) == (
        VARIANT,
        "harness-nemotron",
    )
    assert run.dependencies["routes"] == {
        "handwriting-nemotron": BASETEN,
        "handwriting-muse": MUSE,
        "first-pass-nemotron": BASETEN,
    }
    # The checks that tie a run to its snapshot accept the variant.
    assert pinned_risk_resolution(run).status == "resolved"
    # Field research mounts on the variant's harness route ("fields" mode).
    assert committed_harness_route(run.profile_snapshot) == "harness-nemotron"
    assert run.profile.execution.price_list["version"] == "pilot-prices-2026-10-18"


def test_a_run_queued_with_the_switch_off_is_priced_for_every_nvidia_route(tmp_path, monkeypatch):
    # The API copies the price list and stage floors when it queues a run; the
    # worker picks the routes when it classifies. Both carry the same switch,
    # and the published allowance prices the NVIDIA routes anyway.
    monkeypatch.delenv(SETTING, raising=False)
    specimen = specimen_with(Run(profile=Profile(synthetic=False)))
    queue(specimen, published_registry({SYNTHETIC_COLLECTION: "insects"}), USER)
    execution = specimen.run.profile.execution

    assert {"handwriting-nemotron", "first-pass-nemotron", "harness-nemotron"} <= set(
        execution.price_list["models"]
    )
    assert execution.stage_cost_reservations.for_step("transcribe:r:handwriting-nemotron") == 20_000


# Reservations and costs under the variant, from the NVIDIA rows (USD 0.20 in,
# 0.50 out per million tokens, context 1,048,576).

# One whole-context request: ceil((1,048,576 x 200,000 + 4,096 x 500,000) / 10^6)
# = ceil((209,715,200,000 + 2,048,000,000) / 10^6) = ceil(211,763.2) = 211,764.
NEMOTRON_CONTEXT_REQUEST = 211_764
# Parse and the first pass each reserve two whole-context requests.
NEMOTRON_TWO_REQUESTS = 2 * NEMOTRON_CONTEXT_REQUEST  # 423,528


def with_region(specimen, width, height):
    region = Region(
        asset_id=specimen.asset.id, x=0, y=0, width=width, height=height,
        order=0, method="test", version="1",
    )
    specimen.run.regions = [region]
    return region


def test_a_variant_reading_reserves_from_the_nemotron_row(tmp_path, monkeypatch):
    from specimen_digitization.application.lane_reservations import (
        reading_prompt_tokens,
        reading_reservation,
        step_reservation,
    )

    specimen = variant_run(tmp_path, monkeypatch)
    region = with_region(specimen, 8_000, 5_000)
    step = f"transcribe:{region.id}:handwriting-nemotron"
    run = specimen.run

    # The pinned reading prompt and its answer's schema, in bytes, plus framing.
    assert reading_prompt_tokens(run) == 2_513
    # The crop under Nemotron's rule: 250 x 157 patches of 32 pixels, capped at
    # 3,328, plus 250 + 157 separators and 256 of slack: 3,991 tokens.
    # Request 1: 3,991 + 2,513 = 6,504 in, 4,096 out:
    #   ceil((6,504 x 200,000 + 4,096 x 500,000) / 10^6) = ceil(3,348.8) = 3,349.
    # Request 2 (the retry adds the answer, the feedback and framing):
    #   6,504 + 4,096 + 8,192 + 256 = 19,048 in:
    #   ceil((19,048 x 200,000 + 4,096 x 500,000) / 10^6) = ceil(5,857.6) = 5,858.
    assert reading_reservation(run, step, 1) == 3_349 + 5_858 == 9_207
    # Below the reader floor, which the published allowance sets for this route.
    assert step_reservation(run, step) == 20_000


def test_variant_parse_and_first_pass_reserve_two_whole_nemotron_contexts(tmp_path, monkeypatch):
    from specimen_digitization.application.lane_reservations import step_reservation

    specimen = variant_run(tmp_path, monkeypatch)
    region = with_region(specimen, 600, 400)

    # Parse runs on reader A's route (harness.extract_with_agent), now Nemotron's.
    assert step_reservation(specimen.run, "parse") == NEMOTRON_TWO_REQUESTS == 423_528
    assert step_reservation(specimen.run, f"first_pass:{region.id}") == 423_528


def test_variant_parse_settles_at_the_nemotron_price(tmp_path, monkeypatch):
    from specimen_digitization.application.lane_costs import record_step

    specimen = variant_run(tmp_path, monkeypatch)
    run = specimen.run
    run.attempts["parse"] = 1
    run.completed_steps.append("parse")

    record_step(
        None, None, specimen, "parse", [], 1.0, 0,
        usage={"input_tokens": 10_000, "output_tokens": 1_000},
    )

    (call,) = run.paid_calls
    # 10,000 x 0.20 + 1,000 x 0.50 = 2,500 micro-dollars (Qwen's row: 2,700).
    assert (call["route_id"], call["cost_micros"], call["cost_basis"]) == (
        "handwriting-nemotron",
        2_500,
        "computed",
    )
    assert call["reserved_micros"] == 423_528
    assert call["price_list"]["version"] == "pilot-prices-2026-10-18"


def test_variant_reader_and_first_pass_calls_settle_at_the_nemotron_price(tmp_path, monkeypatch):
    from specimen_digitization.application.lane_costs import record_model_usage

    run = variant_run(tmp_path, monkeypatch).run

    record_model_usage(run, "transcribe:r:handwriting-nemotron", "handwriting-nemotron",
        input_tokens=4_000, output_tokens=300)
    record_model_usage(run, "first_pass:r", "first-pass-nemotron",
        input_tokens=6_000, output_tokens=2_000)

    # 4,000 x 0.20 + 300 x 0.50 = 950; 6,000 x 0.20 + 2,000 x 0.50 = 2,200.
    assert [call["cost_micros"] for call in run.paid_calls] == [950, 2_200]


def test_variant_circuits_are_keyed_by_baseten(tmp_path, monkeypatch):
    from specimen_digitization.application.circuit_runtime import circuit_for

    specimen = variant_run(tmp_path, monkeypatch)
    principal = SimpleNamespace(scope=specimen.scope)
    workflow = SimpleNamespace(repository=None, clock=None)

    providers = {
        step: circuit_for(workflow, principal, specimen.run, step)[1].provider
        for step in ("transcribe:r:handwriting-nemotron", "transcribe:r:handwriting-muse",
                     "first_pass:r", "parse")
    }

    assert providers == {
        "transcribe:r:handwriting-nemotron": "baseten",
        "transcribe:r:handwriting-muse": "deepinfra",
        "first_pass:r": "baseten",
        "parse": "baseten",
    }


def test_variant_field_research_meters_at_the_nemotron_price(tmp_path, monkeypatch):
    from specimen_digitization.field_research.step import (
        _route_price,
        cost_meter,
        one_request_micros,
        profile_of,
    )

    run = variant_run(tmp_path, monkeypatch).run
    profile = profile_of(run)
    price = _route_price(profile, profile.harness_route)
    meter = cost_meter(1_000_000, price)

    assert profile.harness_route == "harness-nemotron"
    assert (meter.input_micros_per_million, meter.output_micros_per_million) == (200_000, 500_000)
    # One expert request's worst case: (48,000 + 512) tokens in at 0.20 and
    # 2,048 out at 0.50 = ceil(9,702.4 + 1,024) = 10,727 (DeepSeek's: 10,932).
    assert one_request_micros(price) == 10_727


def test_the_not_on_label_list_follows_the_published_version(tmp_path, monkeypatch):
    from specimen_digitization.field_research.contracts import not_on_label_fields
    from specimen_digitization.field_research.step import not_on_label_keys, profile_of

    run = variant_run(tmp_path, monkeypatch).run
    published = not_on_label_fields("zoology_insects_slides", "1.0.0")

    assert published  # The pilot profile's list is not empty.
    assert not_on_label_keys(profile_of(run)) == published
    assert not_on_label_fields("zoology_insects_slides", VARIANT) == published
    assert not_on_label_fields("zoology_insects_slides", "1.0.0+nvidia.readers") == published
    # Another version keeps its own (empty) entry.
    assert not_on_label_fields("zoology_insects_slides", "1.0.1+nvidia.readers") == frozenset()


# The six-specialist harness ("on" mode, not production's "fields" mode).


def _effect_model(wrapped, route_id):
    from specimen_digitization.model_gateway import HUGGINGFACE_ROUTES
    from specimen_digitization.research_harness.gateway import EffectModel, ModelBinding

    route = HUGGINGFACE_ROUTES[route_id]
    binding = ModelBinding(route_id, route.model_id, route.provider, 4096, 211_764, "prices")
    scope = SimpleNamespace(specimen_id="specimen", job_id="job", generation=1)
    return EffectModel(wrapped, broker=None, scope=scope, lease=None, role="role",
        binding=binding, pins={"field_keys": []}, request_guard=lambda *_: {})


@pytest.mark.parametrize("route_id", ["harness-nemotron", "harness-deepseek"])
def test_an_effect_model_accepts_the_gateways_model_of_either_transport(route_id):
    from specimen_digitization.model_gateway import HuggingFaceModelGateway

    wrapped = HuggingFaceModelGateway(token="hf_test").model_for(route_id)

    assert _effect_model(wrapped, route_id).binding.route_id == route_id


@pytest.mark.parametrize(
    "built,bound",
    [
        ("harness-deepseek", "harness-nemotron"),
        ("harness-nemotron", "harness-deepseek"),
        ("handwriting-qwen", "harness-nemotron"),
    ],
)
def test_an_effect_model_refuses_another_routes_model(built, bound):
    from specimen_digitization.model_gateway import HuggingFaceModelGateway
    from specimen_digitization.research_harness.gateway import ModelGatewayBlocked

    wrapped = HuggingFaceModelGateway(token="hf_test").model_for(built)

    with pytest.raises(ModelGatewayBlocked, match="wrapped_model_does_not_match_qualified_gateway"):
        _effect_model(wrapped, bound)


def test_on_mode_pins_refuse_a_harness_model_whose_tokenizer_is_not_pinned():
    # The request bound cites DeepSeek's tokenizer files (committed_pins.TOKENIZER_PIN);
    # they prove nothing about Nemotron's, so its "on"-mode job is not pinned.
    from specimen_digitization.research_harness.committed_pins import build_committed_pins

    variant = published_registry(environ={SETTING: "field_research"}).resolve("insects").profile
    published = published_registry(environ={}).resolve("insects").profile

    with pytest.raises(ValueError, match="research_committed_tokenizer_unpinned"):
        build_committed_pins(variant, organization_id="org", collection_id="insects")
    pins = build_committed_pins(published, organization_id="org", collection_id="insects")
    assert {row["route_id"] for row in pins["sources"]["model_prices"].values()} == {"harness-deepseek"}
