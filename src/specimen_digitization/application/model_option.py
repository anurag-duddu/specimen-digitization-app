"""Which pipeline stages run on NVIDIA Nemotron (the NVIDIA option).

docs/product-requirements/NVIDIA_NEMOTRON_OPTION.md, section 2.
SPECIMEN_NVIDIA_STAGES is a comma-separated subset of "readers", "first_pass"
and "field_research". Unset, empty or blank is off: the published profiles load
as written. Any other value raises, naming the setting and never its value, so
a mistyped value never decides which models run (the precedent:
research_harness/enablement.py).

With a stage on, published_registry() loads each published profile as its
variant: the stage's routes move to the NVIDIA routes
(model_gateway.NVIDIA_HUGGINGFACE_ROUTES), and the version gains semantic
versioning build metadata naming the stages in their canonical order, for
example "1.0.0+nvidia.readers.first-pass.field-research". The collection
mapping names the variant. A run classified under it keeps that snapshot, so it
records the option it ran under and never changes option mid-way. The API and
the worker each load the profiles, so both carry the same value
(scripts/ci/test_runtime_settings.py).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

SETTING = "SPECIMEN_NVIDIA_STAGES"
# The stages, in the canonical order a variant's version names them in.
STAGES = ("readers", "first_pass", "field_research")
# Nemotron takes reader A's place; Muse stays reader B (NVIDIA_NEMOTRON_OPTION.md 1).
READER_ROUTES = ("handwriting-nemotron", "handwriting-muse")
FIRST_PASS_ROUTE = "first-pass-nemotron"
HARNESS_ROUTE = "harness-nemotron"
# Today's route each stage replaces, and the route that replaces it.
REPLACED_ROUTES = {
    "readers": ("handwriting-qwen", "handwriting-nemotron"),
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


def nvidia_variant(registry, stages: Iterable[str]):
    """The registry with each profile replaced by its variant for these stages.

    Each profile's readers become READER_ROUTES with the readers stage; its
    first-pass and harness routes, where it names one, become the NVIDIA
    routes with their stages. Nothing else changes: the variant's processing
    allowance is the published one, which must price every NVIDIA route it
    names (CollectionProfile.validate_fields), so a profile that does not
    cannot load its variant. Every mapping to a profile names its variant.
    """
    from .collection_profiles import CollectionProfile, CollectionProfileRegistry

    stages = tuple(stage for stage in STAGES if stage in set(stages))
    if not stages:
        return registry
    versions: dict[tuple[str, str], str] = {}
    profiles = []
    for profile in registry.profiles:
        data = profile.model_dump(mode="json")
        data["version"] = variant_version(profile.version, stages)
        if "readers" in stages:
            data["model_routes"] = list(READER_ROUTES)
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
    """The routes the active option calls: today's, with each enabled stage's
    route replaced by its NVIDIA route (what preflight checks)."""
    from ..model_gateway import (
        HUGGINGFACE_ROUTES,
        INITIAL_HUGGINGFACE_ROUTES,
        STAGE_HUGGINGFACE_ROUTES,
    )

    replaced = {
        old: new for stage, (old, new) in REPLACED_ROUTES.items() if stage in set(stages)
    }
    return {
        replaced.get(route_id, route_id): HUGGINGFACE_ROUTES[replaced.get(route_id, route_id)]
        for route_id in (*INITIAL_HUGGINGFACE_ROUTES, *STAGE_HUGGINGFACE_ROUTES)
    }
