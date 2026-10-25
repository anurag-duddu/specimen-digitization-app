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
QWEN = {"model_id": "Qwen/Qwen3-VL-30B-A3B-Instruct", "provider": "novita"}
# Nemotron is reader C, after today's Qwen (A) and Muse (B).
THREE_READERS = ["handwriting-qwen", "handwriting-muse", "handwriting-nemotron"]
# The published limits, 480,000 tokens and 96 weighted calls, x 3/2 for three
# readers (model_option.label_scaled_limit).
THREE_READER_LIMITS = {"max_tokens": 720_000, "max_external_calls": 144}


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
        ("readers", "readers", {"model_routes": THREE_READERS}),
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
                "model_routes": THREE_READERS,
                "first_pass_route": "first-pass-nemotron",
                "harness_route": "harness-nemotron",
            },
        ),
    ],
)
def test_each_stage_changes_only_its_own_routes_and_the_version(value, suffix, changes):
    profile = published_registry(environ={SETTING: value}).resolve("insects").profile
    published = published_profile()
    if "readers" in value:
        # A third reader raises the run's token and weighted-call limits.
        changes = {**changes, "processing": {**published["processing"], **THREE_READER_LIMITS}}

    # Everything else, the price list and the cost limit included, is the
    # published profile's.
    assert profile.model_dump(mode="json") == {
        **published,
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
    assert run.profile.routes == tuple(THREE_READERS)
    assert run.profile.first_pass_route == "first-pass-nemotron"
    assert (run.profile_snapshot["version"], run.profile_snapshot["harness_route"]) == (
        VARIANT,
        "harness-nemotron",
    )
    assert run.dependencies["routes"] == {
        "handwriting-qwen": QWEN,
        "handwriting-muse": MUSE,
        "handwriting-nemotron": BASETEN,
        "first-pass-nemotron": BASETEN,
    }
    # The checks that tie a run to its snapshot accept the variant.
    assert pinned_risk_resolution(run).status == "resolved"
    # Field research mounts on the variant's harness route ("fields" mode).
    assert committed_harness_route(run.profile_snapshot) == "harness-nemotron"
    assert run.profile.execution.price_list["version"] == "pilot-prices-2026-10-18"
    execution = run.profile.execution
    assert {"max_tokens": execution.max_tokens, "max_external_calls": execution.max_external_calls} == (
        THREE_READER_LIMITS
    )


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


def test_variant_parse_stays_on_qwen_and_first_pass_reserves_two_whole_nemotron_contexts(
    tmp_path, monkeypatch
):
    from specimen_digitization.application.lane_reservations import step_reservation

    specimen = variant_run(tmp_path, monkeypatch)
    region = with_region(specimen, 600, 400)

    # Parse runs on reader A's route (harness.extract_with_agent), still Qwen's:
    # two whole Qwen contexts, as with the option off (test_lane_routes).
    assert specimen.run.profile.routes[0] == "handwriting-qwen"
    assert step_reservation(specimen.run, "parse") == 58_164
    assert step_reservation(specimen.run, f"first_pass:{region.id}") == NEMOTRON_TWO_REQUESTS == 423_528


def test_variant_parse_settles_at_the_qwen_price(tmp_path, monkeypatch):
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
    # 10,000 x 0.20 + 1,000 x 0.70 = 2,700 micro-dollars, Qwen's row.
    assert (call["route_id"], call["cost_micros"], call["cost_basis"]) == (
        "handwriting-qwen",
        2_700,
        "computed",
    )
    assert call["reserved_micros"] == 58_164
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
        for step in ("transcribe:r:handwriting-qwen", "transcribe:r:handwriting-muse",
                     "transcribe:r:handwriting-nemotron", "first_pass:r", "parse")
    }

    assert providers == {
        "transcribe:r:handwriting-qwen": "novita",
        "transcribe:r:handwriting-muse": "deepinfra",
        "transcribe:r:handwriting-nemotron": "baseten",
        "first_pass:r": "baseten",
        "parse": "novita",
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


# Reader C: the readers stage adds Nemotron as a third reader.


def test_the_readers_stage_adds_nemotron_as_reader_c_and_parse_stays_on_reader_a(
    tmp_path, monkeypatch
):
    specimen = variant_run(tmp_path, monkeypatch, "readers")
    run = specimen.run

    assert run.profile.version == "1.0.0+nvidia.readers"
    assert run.profile.routes == ("handwriting-qwen", "handwriting-muse", "handwriting-nemotron")
    # The other stages keep today's routes.
    assert run.profile.first_pass_route == "first-pass-glm"
    assert run.profile_snapshot["harness_route"] == "harness-deepseek"
    assert run.dependencies["routes"] == {
        "handwriting-qwen": QWEN,
        "handwriting-muse": MUSE,
        "handwriting-nemotron": BASETEN,
        "first-pass-glm": {"model_id": "zai-org/GLM-5.3-Flash", "provider": "novita"},
    }
    # One reading per label per reader, in route order (Workflow.next_step).
    from specimen_digitization.application.workflow import Workflow

    region = with_region(specimen, 600, 400)
    steps = []
    run.completed_steps = ["pin_dependencies", "classify", "quality_check", "segment"]
    while (step := Workflow.next_step(run)).startswith("transcribe:"):
        steps.append(step)
        run.completed_steps.append(step)
    assert steps == [f"transcribe:{region.id}:{route}" for route in THREE_READERS]


def test_a_profile_that_already_names_nemotron_as_a_reader_keeps_its_readers_and_limits():
    data = json.loads(PUBLISHED_PROFILES.read_text())
    data["profiles"][0]["model_routes"] = ["handwriting-qwen", "handwriting-nemotron"]
    registry = CollectionProfileRegistry.model_validate(data)

    profile = nvidia_variant(registry, ("readers",)).profiles[0]

    assert profile.model_routes == ("handwriting-qwen", "handwriting-nemotron")
    assert (profile.processing.max_tokens, profile.processing.max_external_calls) == (480_000, 96)


@pytest.mark.parametrize(
    "readers,published,expected",
    [(2, 2, 480_000), (3, 2, 720_000), (4, 2, 960_000), (3, 3, 480_000), (4, 3, 640_000)],
)
def test_a_limit_grows_by_the_readers_over_the_published_readers(readers, published, expected):
    from specimen_digitization.application.model_option import label_scaled_limit

    assert label_scaled_limit(480_000, readers, published) == expected
    # Rounded up, never down.
    assert label_scaled_limit(95, 3, 2) == 143


# What a label costs the run's limits (workflow.py, before each step): every
# attempt at a reading or a first pass reserves 16,000 tokens and weighs 2
# calls. The fixed steps a slide takes whatever its labels: segment and classify
# (16,000 tokens, 1 call each), parse (16,000, 2) and field research (16,000, 1).
ATTEMPT_TOKENS, ATTEMPT_CALLS = 16_000, 2
FIXED_TOKENS, FIXED_CALLS = 4 * 16_000, 1 + 1 + 2 + 1


def label_steps(routes, labels, readings_agree):
    """The reading and first-pass steps of a slide's labels, in Workflow.next_step order."""
    from specimen_digitization.application.domain import Observation
    from specimen_digitization.application.workflow import Workflow

    run = Run(profile=Profile(routes=tuple(routes)))
    run.regions = [
        Region(asset_id="a", x=0, y=0, width=9, height=9, order=n, method="m", version="1")
        for n in range(labels)
    ]
    run.completed_steps = ["pin_dependencies", "classify", "quality_check", "segment"]
    steps = []
    while (step := Workflow.next_step(run)) != "adjudicate":
        steps.append(step)
        run.completed_steps.append(step)
        if step.startswith("transcribe:"):
            _, region, route = step.split(":")
            text = "same" if readings_agree else route
            run.observations.append(Observation(
                region_id=region, route_id=route, model_id="m", provider="p",
                prompt_version="v", input_sha256="0" * 64, literal_text=text,
                raw_ref="r", raw_sha256="1" * 64,
            ))
    return steps


def most_labels(routes, max_tokens, max_calls, readings_agree):
    """The most labels a slide can have, one attempt per step, within both limits."""
    labels = 0
    while True:
        steps = len(label_steps(routes, labels + 1, readings_agree))
        if (
            FIXED_TOKENS + steps * ATTEMPT_TOKENS > max_tokens
            or FIXED_CALLS + steps * ATTEMPT_CALLS > max_calls
        ):
            return labels
        labels += 1


@pytest.mark.parametrize("readings_agree", [False, True], ids=["first pass", "no first pass"])
def test_a_third_reader_fits_as_many_labels_per_slide_within_the_raised_limits(readings_agree):
    two = ("handwriting-qwen", "handwriting-muse")
    three = (*two, "handwriting-nemotron")
    # A label is one step per reader, plus a first pass when its readings differ.
    assert len(label_steps(three, 1, readings_agree)) == 3 + (not readings_agree)

    published = most_labels(two, 480_000, 96, readings_agree)
    variant = most_labels(three, THREE_READER_LIMITS["max_tokens"],
        THREE_READER_LIMITS["max_external_calls"], readings_agree)

    # The published limits fit 8 labels that need a first pass, or 13 whose
    # readings agree (tokens bind first); three readers fit 10 or 13.
    assert (published, variant) == ((8, 10) if not readings_agree else (13, 13))
    assert most_labels(three, 480_000, 96, readings_agree) < published
    # Scaling by (readers + 1) / (published readers + 1) would fit fewer labels
    # whose readings agree (12 of 13): x 3/2 is what keeps both.
    four_thirds = most_labels(three, 640_000, 128, readings_agree)
    assert four_thirds >= published if not readings_agree else four_thirds == 12 < published
