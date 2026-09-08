"""Bind shared scoped circuit CAS to durable worker documents."""

import re
from .storage import Conflict, Missing, digest
from .provider_circuit import (
    CircuitConflict,
    CircuitKey,
    CircuitPolicy,
    ProviderCircuit,
)


class RepositoryCircuitStore:
    def __init__(self, repository, scope):
        self.repository, self.scope = repository, scope

    def load(self, key):
        try:
            record = self.repository.document(self.scope, "worker_cursor", key)
        except Missing:
            return None
        return record["revision"], record["circuit_state"]

    def compare_and_swap(self, key, expected_revision, state):
        try:
            return self.repository.put_document(
                self.scope,
                "worker_cursor",
                key,
                {"circuit_state": state},
                expected_revision or 0,
            )["revision"]
        except Conflict as exc:
            raise CircuitConflict() from exc


def circuit_for(workflow, principal, run, step):
    if step.startswith("authority:"):
        tool = step.split(":")[2]
        provider = tool
        config = run.dependencies.get("authority_pins", {}).get(
            tool, {"unconfigured": tool}
        )
    elif step.startswith("transcribe:") or step == "parse":
        route = (
            step.split(":")[-1]
            if step.startswith("transcribe:")
            else run.profile.routes[0]
        )
        selected = run.dependencies.get("routes", {}).get(route, {})
        provider = selected.get(
            "provider", "synthetic" if run.profile.synthetic else "unconfigured_model"
        )
        # Provider account/routing configuration is shared across models and runs.
        config = {
            "provider": provider,
            "adapter": run.dependencies.get("adapter_version"),
            "routes": run.dependencies.get("routes", {}),
        }
    elif step == "segment":
        provider = "synthetic_segmentation" if run.profile.synthetic else "sam3"
        config = run.dependencies.get(
            "segmentation", {"synthetic": run.profile.synthetic}
        )
    elif step == "lookup":
        provider = "synthetic_taxonomy" if run.profile.synthetic else "gbif"
        config = {
            "adapter": run.dependencies.get("adapter_version"),
            "operation": "taxonomy",
        }
    else:
        provider = "classifier"
        config = {"registry": run.profile_registry_version}
    policy = CircuitPolicy()
    key = CircuitKey(
        organization_id=principal.scope.organization_id,
        collection_id=principal.scope.collection_id,
        provider=re.sub("[^a-zA-Z0-9_.-]", "_", provider)[:100],
        config_sha256=digest(
            {
                "provider_config": config,
                "circuit_policy": policy.model_dump(),
                "binding_version": "provider-circuit-binding-v1",
            }
        ),
    )
    return ProviderCircuit(
        RepositoryCircuitStore(workflow.repository, principal.scope),
        workflow.clock,
        policy,
    ), key
