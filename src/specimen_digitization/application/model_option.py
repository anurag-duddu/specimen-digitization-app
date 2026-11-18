"""Which pipeline stages run on NVIDIA Nemotron (the NVIDIA option).

docs/product-requirements/NVIDIA_NEMOTRON_OPTION.md, section 2.
SPECIMEN_NVIDIA_STAGES is a comma-separated subset of "readers", "first_pass"
and "field_research". Unset, empty or blank is off: the published profiles load
as written. Any other value raises, naming the setting and never its value, so
a mistyped value never decides which models run (the precedent:
research_harness/enablement.py).

With a stage on, published_registry() loads each published profile as its
variant: the readers stage adds Nemotron as one more reader after the
published ones; the first-pass and field-research stages move their route to
the NVIDIA route (model_gateway.NVIDIA_HUGGINGFACE_ROUTES); and the version
gains semantic versioning build metadata naming the stages in their canonical
order, for example "1.0.0+nvidia.readers.first-pass.field-research". The
collection mapping names the variant. A run classified under it keeps that
snapshot, so it records the option it ran under and never changes option
mid-way. The API and the worker each load the profiles, so both carry the same
value (scripts/ci/test_runtime_settings.py).

A second, separate switch, SPECIMEN_READER_A, puts a stronger model in reader
A's place (the autonomy program's reader measurement, 2026-11-18): its only
value today is "kimi", which loads each published profile as a variant whose
first reader is handwriting-kimi (Kimi K3.1 Pro on DeepInfra) in place of
handwriting-qwen, with reader B and everything else as published. The organiser
(parse), which runs on reader A's route, stays on Qwen
(model_gateway.organiser_route). The two switches do not combine. Unset, empty
or blank is off and the published profiles load as written; any other value
raises, naming the setting and never its value.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

SETTING = "SPECIMEN_NVIDIA_STAGES"
# The stages, in the canonical order a variant's version names them in.
STAGES = ("readers", "first_pass", "field_research")
# Nemotron is one more reader, after the published ones: with today's Qwen (A)
# and Muse (B) it is reader C. Reader A keeps its place, so parse, which runs on
# reader A's route, is unchanged (NVIDIA_NEMOTRON_OPTION.md 1).
ADDED_READER = "handwriting-nemotron"
FIRST_PASS_ROUTE = "first-pass-nemotron"
HARNESS_ROUTE = "harness-nemotron"
# The route the readers stage adds to today's routes.
ADDED_ROUTES = {"readers": ADDED_READER}
# Today's route each other stage replaces, and the route that replaces it.
REPLACED_ROUTES = {
    "first_pass": ("first-pass-glm", FIRST_PASS_ROUTE),
    "field_research": ("harness-deepseek", HARNESS_ROUTE),
}
BUILD_PREFIX = "nvidia"

READER_A_SETTING = "SPECIMEN_READER_A"
# The value the switch takes, and the reader route it puts in reader A's place.
READER_A_ROUTES = {"kimi": "handwriting-kimi"}
READER_A_BUILD_PREFIX = "reader-a"
# The reader A these variants replace: today's, the first of the published routes.
REPLACED_READER_A = "handwriting-qwen"
# What a reader-A route costs, in the price list's units, and the floor its
# stage reserves (as every reader's: 20,000 micro-dollars). Hugging Face's
# router lists Kimi K3.1 Pro on DeepInfra at USD 1.90 in and 9.50 out per
# million tokens with a 1,048,576-token context (snapshot of 2026-11-18). The
# image rule is the model's own: its preprocessor_config.json sets 14-pixel
# patches merged 2 by 2 (28 pixels a token) and at most 65,536 patches an image
# (16,384 tokens); the 269 label crops of the arbiter benchmark came out at
# exactly ceil(h/28) x ceil(w/28) image tokens each. The rows live here, in
# the variant, and not in published.json, so the published profile, its price
# list and its digest stay as they are until the option is made the default.
READER_A_PRICES = {
    "handwriting-kimi": {
        "input_micros_per_million": 1_900_000,
        "output_micros_per_million": 9_500_000,
        "context_tokens": 1_048_576,
        "image_tokens": {
            "pixels_per_token": 28,
            "max_tokens": 16_384,
            "source": "https://huggingface.co/moonshotai/Kimi-K3.1-Pro/blob/main/preprocessor_config.json",
        },
    }
}
READER_A_STAGE_COST_MICROS = 20_000


class ModelOptionConfigurationError(ValueError):
    """SPECIMEN_NVIDIA_STAGES names something other than its stages."""


def nvidia_stages(environ: Mapping[str, str]) -> tuple[str, ...]:
    """The stages the switch turns on, in canonical order; () when it is off.

    Errors name the setting, never its value.
    """
    value = environ.get(SETTING, "")
    if not value.strip():
        return ()
    names = {name.strip() for name in value.split(",")}
    if not names <= set(STAGES):
        raise ModelOptionConfigurationError(
            f"{SETTING} must be a comma-separated list of readers, first_pass "
            "and field_research"
        )
    return tuple(stage for stage in STAGES if stage in names)


def reader_a_route(environ: Mapping[str, str]) -> str | None:
    """The reader route the switch puts in reader A's place; None when it is off.

    Errors name the setting, never its value.
    """
    value = environ.get(READER_A_SETTING, "")
    if not value.strip():
        return None
    route = READER_A_ROUTES.get(value.strip())
    if route is None:
        raise ModelOptionConfigurationError(
            f"{READER_A_SETTING} must be empty or one of: " + ", ".join(sorted(READER_A_ROUTES))
        )
    return route


def variant_version(version: str, stages: Iterable[str]) -> str:
    """The published version with build metadata naming the stages.

    Semantic versioning allows only [0-9A-Za-z-] in a build identifier, so a
    stage's underscore becomes a hyphen.
    """
    if "+" in version:
        raise ValueError(
            "A published profile version that carries build metadata has no NVIDIA variant."
        )
    names = [stage.replace("_", "-") for stage in STAGES if stage in set(stages)]
    return ".".join([f"{version}+{BUILD_PREFIX}", *names])


def label_scaled_limit(value: int, readers: int, published_readers: int) -> int:
    """A run limit raised so that a run with more readers fits as many labels.

    Every attempt at a reading or a first pass reserves 16,000 tokens and
    weighs 2 calls (workflow.py, the limits checked before each step:
    ``reservation_tokens`` and ``external_weight``), and the reservation is
    never given back. A label costs a run a attempts per reader and b
    first-pass attempts: a >= 1, and b = 0 when its readings agree, so it skips
    the first pass, up to the step's attempts otherwise. Its share of either
    limit is (a x readers + b) attempts; the fixed steps (segment, classify,
    parse, field research) do not grow with the readers. The share grows by at
    most readers / published_readers (at b = 0), so ceil(value x readers /
    published_readers) fits at least as many labels as ``value`` did with the
    published readers, whether or not the labels need a first pass. Scaling by
    (readers + 1) / (published_readers + 1) would not: it covers labels that
    need a first pass, and fits fewer labels whose readings agree.
    """
    if readers <= published_readers:
        return value
    return math.ceil(value * readers / published_readers)


def nvidia_variant(registry, stages: Iterable[str]):
    """The registry with each profile replaced by its variant for these stages.

    With the readers stage each profile's readers gain ADDED_READER after its
    own, and its token and weighted-call limits rise with the reader count
    (label_scaled_limit); its first-pass and harness routes, where it names
    one, become the NVIDIA routes with their stages. Nothing else changes: the
    variant's price list is the published one, which must price every NVIDIA
    route it names (CollectionProfile.validate_fields), so a profile that does
    not cannot load its variant. Every mapping to a profile names its variant.
    """
    from .collection_profiles import CollectionProfile
    from .domain import ExecutionPolicy

    stages = tuple(stage for stage in STAGES if stage in set(stages))
    if not stages:
        return registry
    versions: dict[tuple[str, str], str] = {}
    profiles = []
    for profile in registry.profiles:
        data = profile.model_dump(mode="json")
        data["version"] = variant_version(profile.version, stages)
        if "readers" in stages and ADDED_READER not in profile.model_routes:
            data["model_routes"] = [*profile.model_routes, ADDED_READER]
            processing = data.get("processing")
            if processing is not None:
                # The run's limits, as lane.queue copies them: the allowance's
                # value, or the execution policy's default when it sets none.
                defaults = ExecutionPolicy()
                for name in ("max_tokens", "max_external_calls"):
                    value = processing.get(name) or getattr(defaults, name)
                    processing[name] = label_scaled_limit(
                        value, len(data["model_routes"]), len(profile.model_routes)
                    )
        if "first_pass" in stages and profile.first_pass_route is not None:
            data["first_pass_route"] = FIRST_PASS_ROUTE
        if "field_research" in stages and profile.harness_route is not None:
            data["harness_route"] = HARNESS_ROUTE
        versions[(profile.id, profile.version)] = data["version"]
        profiles.append(CollectionProfile.model_validate(data))
    return _registry_of(registry, profiles, versions)


def _registry_of(registry, profiles, versions: Mapping[tuple[str, str], str]):
    """The registry with these (variant) profiles in place of its own, and every
    mapping to a profile naming its variant's version."""
    from .collection_profiles import CollectionProfileRegistry

    mappings = [
        mapping.model_copy(
            update={
                "profile_version": versions.get(
                    (mapping.profile_id, mapping.profile_version), mapping.profile_version
                )
            }
        ).model_dump(mode="json")
        for mapping in registry.mappings
    ]
    return CollectionProfileRegistry.model_validate(
        {
            **registry.model_dump(mode="json"),
            "profiles": [profile.model_dump(mode="json") for profile in profiles],
            "mappings": mappings,
            "bindings": dict(registry.bindings),
        }
    )


def reader_a_variant(registry, route: str | None):
    """The registry with each profile replaced by its variant that has ``route``
    as reader A in place of today's (handwriting-qwen); the registry itself when
    ``route`` is None.

    Reader B and every other route are as published, and so are the run's limits
    (the same number of readers). The route's price and its stage's reservation
    are added to the profile's price list and stage costs, whose version gains
    the same build metadata as the profile's, so a variant's run records the
    list it was priced with. A profile whose first reader is not today's reader A
    has no such variant.
    """
    from .collection_profiles import CollectionProfile

    if route is None:
        return registry
    if route not in READER_A_PRICES:
        raise ValueError("Unknown reader-A route.")
    build = ".".join([READER_A_BUILD_PREFIX, route.removeprefix("handwriting-")])
    versions: dict[tuple[str, str], str] = {}
    profiles = []
    for profile in registry.profiles:
        if "+" in profile.version:
            raise ValueError(
                "A published profile version that carries build metadata has no reader-A variant."
            )
        if not profile.model_routes or profile.model_routes[0] != REPLACED_READER_A:
            raise ValueError("A reader-A variant replaces a first reader that is not Qwen.")
        data = profile.model_dump(mode="json")
        data["version"] = f"{profile.version}+{build}"
        data["model_routes"] = [route, *profile.model_routes[1:]]
        processing = data.get("processing")
        if processing is not None:
            stage_costs = processing["stage_cost_micros"]["cost_micros"]
            stage_costs.setdefault(f"transcribe:{route}", READER_A_STAGE_COST_MICROS)
            price_list = processing.get("price_list")
            if price_list is not None:
                price_list["version"] = f"{price_list['version']}+{build}"
                price_list["models"].setdefault(route, dict(READER_A_PRICES[route]))
        versions[(profile.id, profile.version)] = data["version"]
        profiles.append(CollectionProfile.model_validate(data))
    return _registry_of(registry, profiles, versions)


def active_routes(stages: Iterable[str], reader_a: str | None = None):
    """The routes the active option calls: today's, with the readers stage's
    added reader after today's readers and each other enabled stage's route
    replaced by its NVIDIA route, and the reader-A option's route added (Qwen
    stays: the organiser runs on it) (what preflight checks)."""
    from ..model_gateway import (
        HUGGINGFACE_ROUTES,
        INITIAL_HUGGINGFACE_ROUTES,
        STAGE_HUGGINGFACE_ROUTES,
    )

    stages = set(stages)
    added = [route for stage, route in ADDED_ROUTES.items() if stage in stages]
    if reader_a is not None:
        added.append(reader_a)
    replaced = {old: new for stage, (old, new) in REPLACED_ROUTES.items() if stage in stages}
    routes = [
        *INITIAL_HUGGINGFACE_ROUTES,
        *(route for route in added if route not in INITIAL_HUGGINGFACE_ROUTES),
        *(replaced.get(route_id, route_id) for route_id in STAGE_HUGGINGFACE_ROUTES),
    ]
    return {route_id: HUGGINGFACE_ROUTES[route_id] for route_id in routes}
