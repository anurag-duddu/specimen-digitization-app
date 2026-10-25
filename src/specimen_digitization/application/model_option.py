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
    from .collection_profiles import CollectionProfile, CollectionProfileRegistry
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


def active_routes(stages: Iterable[str]):
    """The routes the active option calls: today's, with the readers stage's
    added reader after today's readers and each other enabled stage's route
    replaced by its NVIDIA route (what preflight checks)."""
    from ..model_gateway import (
        HUGGINGFACE_ROUTES,
        INITIAL_HUGGINGFACE_ROUTES,
        STAGE_HUGGINGFACE_ROUTES,
    )

    stages = set(stages)
    added = [route for stage, route in ADDED_ROUTES.items() if stage in stages]
    replaced = {old: new for stage, (old, new) in REPLACED_ROUTES.items() if stage in stages}
    routes = [
        *INITIAL_HUGGINGFACE_ROUTES,
        *(route for route in added if route not in INITIAL_HUGGINGFACE_ROUTES),
        *(replaced.get(route_id, route_id) for route_id in STAGE_HUGGINGFACE_ROUTES),
    ]
    return {route_id: HUGGINGFACE_ROUTES[route_id] for route_id in routes}
