"""Bind shared scoped circuit CAS to durable worker documents."""

import math
import re
from .storage import Conflict, Missing, digest
from .provider_circuit import (
    CircuitConflict,
    CircuitKey,
    CircuitPolicy,
    CircuitState,
    ProviderCircuit,
)


_MAX_EXACT_INTEGER = 2**53 - 1
_MAX_TIMESTAMP_MS = 253402300799000


def _stored_integer(value, maximum=_MAX_EXACT_INTEGER):
    """Accept only exact nonnegative JSON numbers from the stored transport."""
    if type(value) is float:
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError("invalid_stored_circuit_integer")
        value = int(value)
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("invalid_stored_circuit_integer")
    return value


def _stored_state(raw):
    if not isinstance(raw, dict):
        raise ValueError("invalid_stored_circuit_state")
    state = dict(raw)
    for name, maximum in (
        ("schema_version", 1),
        ("epoch", _MAX_EXACT_INTEGER),
        ("transient_failures", 10000),
        ("open_count", 10000),
        ("last_clock_ms", _MAX_TIMESTAMP_MS),
    ):
        if name in state:
            state[name] = _stored_integer(state[name], maximum)
    if state.get("open_until_ms") is not None:
        state["open_until_ms"] = _stored_integer(
            state["open_until_ms"], _MAX_TIMESTAMP_MS
        )
    if "pending" in state:
        if not isinstance(state["pending"], (list, tuple)):
            raise ValueError("invalid_stored_circuit_pending")
        pending = []
        for raw_permit in state["pending"]:
            if not isinstance(raw_permit, dict):
                raise ValueError("invalid_stored_circuit_permit")
            permit = dict(raw_permit)
            for name, maximum in (
                ("epoch", _MAX_EXACT_INTEGER),
                ("expires_at_ms", _MAX_TIMESTAMP_MS),
            ):
                if name in permit:
                    permit[name] = _stored_integer(permit[name], maximum)
            pending.append(permit)
        state["pending"] = pending
    # All other fields and relationships retain the strict public model contract.
    return CircuitState.model_validate(state).model_dump(mode="json")


class RepositoryCircuitStore:
    def __init__(self, repository, scope):
        self.repository, self.scope = repository, scope

    def load(self, key):
        try:
            record = self.repository.document(self.scope, "worker_cursor", key)
        except Missing:
            return None
        return (
            _stored_integer(record["revision"]),
            _stored_state(record["circuit_state"]),
        )

    def compare_and_swap(self, key, expected_revision, state):
        expected = 0 if expected_revision is None else expected_revision
        if type(expected) is not int or not 0 <= expected < _MAX_EXACT_INTEGER:
            raise ValueError("invalid_circuit_cas_revision")
        # Writes come from the strict in-process model, never transport coercion.
        state = CircuitState.model_validate(state).model_dump(mode="json")
        state = _stored_state(state)  # Reject integers the transport cannot retain.
        try:
            result = self.repository.put_document(
                self.scope,
                "worker_cursor",
                key,
                {"circuit_state": state},
                expected,
            )
        except Conflict as exc:
            raise CircuitConflict() from exc
        revision = _stored_integer(result["revision"])
        if revision != expected + 1:
            raise ValueError("invalid_circuit_cas_acknowledgement")
        return revision


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
