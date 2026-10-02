"""Concrete per-binding composition; no provider dispatch or job creation."""
from dataclasses import dataclass

from .canonical_evidence_provider_v2 import CanonicalEvidenceProviderV2
from .canonical_materialization_v2 import CanonicalResearchMaterializerV2, ResearchCanonicalPolicyV2
from .native_canonical import CanonicalProjectionServicesV1


@dataclass(frozen=True)
class NativeMaterializationServicesV2:
    materializer: CanonicalResearchMaterializerV2
    evidence_provider: CanonicalEvidenceProviderV2
    projection_services: CanonicalProjectionServicesV1
    request_factory: object


def build_native_materialization_services_v2(repository, effect_broker, registry, policy, request_factory):
    """Build from real service-owned origins and the registered scientific pin.

    The backend owns initial immutable native request generation; this factory
    does not create prompts, request bodies, budgets, leases or missing lineage.
    """
    qualified_policy = ResearchCanonicalPolicyV2.model_validate(policy.model_dump(mode="json"))
    provider = CanonicalEvidenceProviderV2.from_service(repository, effect_broker, registry)
    services = CanonicalProjectionServicesV1.from_repository(repository)
    return NativeMaterializationServicesV2(CanonicalResearchMaterializerV2(qualified_policy, provider),
        provider, services, request_factory)
