"""Resolve published policies once and validate exact retained run settings."""

from .collection_profiles import CollectionProfile, resolve_profile_rules
from .reading_declarations import LanguageHandling
from .review_risk import (
    RiskPolicyRegistry,
    RiskPolicyReference,
    RiskPolicyResolution,
    synthetic_risk_policies,
)


def bind_profile_rules(specimen, published, registry=None):
    registry = registry or (
        synthetic_risk_policies()
        if specimen.run.profile.synthetic
        else RiskPolicyRegistry(version="unconfigured-risk-registry")
    )
    reference = (
        RiskPolicyReference.model_validate(published.scoring_policy_ref.model_dump())
        if published.scoring_policy_ref
        else None
    )
    resolution = registry.resolve(
        reference, allow_synthetic=specimen.run.profile.synthetic
    )
    if resolution.status != "resolved":
        raise ValueError(resolution.reason)
    rules = resolve_profile_rules(published, (published.scoring_policy_ref,))
    specimen.run.profile_rules = rules.model_dump(mode="json")
    specimen.run.risk_policy_snapshot = resolution.model_dump(mode="json")
    return LanguageHandling.model_validate(rules.language_handling.model_dump())


def pinned_risk_resolution(run):
    try:
        resolution = RiskPolicyResolution.model_validate(run.risk_policy_snapshot)
        published = CollectionProfile.model_validate(run.profile_snapshot)
        rules = resolve_profile_rules(
            published,
            (published.scoring_policy_ref,) if resolution.status == "resolved" else (),
        )
        if (
            rules.model_dump(mode="json") != run.profile_rules
            or resolution.reference.model_dump()
            != published.scoring_policy_ref.model_dump()
            or run.profile.language_handling.model_dump()
            != rules.language_handling.model_dump()
            or run.profile.id != published.id
            or run.profile.version != published.version
        ):
            raise ValueError("Pinned profile policy mismatch")
        return resolution
    except (ValueError, TypeError, AttributeError):
        return RiskPolicyResolution(
            status="blocked",
            reference=None,
            registry_version="unavailable",
            reason="pinned_profile_rules_missing_or_invalid",
        )
