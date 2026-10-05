"""Offline SQLite admission checks; these fixtures are not live human proof."""

import asyncio
from dataclasses import replace
from contextvars import copy_context
from uuid import uuid4

import pytest

from specimen_digitization.research_harness.persistence import (
    BudgetExceeded, BudgetPolicy, CapturedResult, DurabilityScope, DurableEffectBroker,
    ImmutableFileBlobs, PinnedRuntime, ResearchStore, SqliteStateBackend, StaleWork,
    _trusted_locked_source_read, digest,
)


@pytest.fixture
def held(tmp_path):
    scope = DurabilityScope(*(str(uuid4()) for _ in range(4)), 1, "worker", False)
    backend = SqliteStateBackend(tmp_path / "state.sqlite")
    backend.grant(scope, role="reviewer")
    store = ResearchStore(backend, "offline-locked-read-test")
    store.initialize(scope, BudgetPolicy(10))
    pins = PinnedRuntime("input", {}, {}, {}, {}, {}, "specialist_harness_v2")
    store.create_job(scope, pins, ["country", "locality", "latitude"],
        human_locks={"country": "a" * 64, "locality": "b" * 64})
    lease = store.claim(scope, "owner")
    broker = DurableEffectBroker(store, ImmutableFileBlobs(tmp_path / "blobs"))
    return store, scope, lease, broker


def logical(source="geolocate", local=False):
    return {"contract_version": "research-pinned-dataset-request/v1" if local
            else "research-source-request-envelope/v2", "tool_id": "source_lookup",
        "query" if local else "arguments": {"source_id": source, "field_key": "locality"},
        "trusted_derivation_command_digest": "c" * 64,
        "original_request_digest": "d" * 64, "field_revision": 0}


def permit(held, request, verifier=lambda: None, **changes):
    _, scope, _, broker = held
    values = dict(field_key="locality", source_id=request.get("query", request.get("arguments"))["source_id"],
        command_digest="c" * 64, verify_current=verifier)
    values.update(changes)
    return _trusted_locked_source_read(broker, scope, "source_capture_v2:" + digest(request),
        request, **values)


def run(held, request, dispatch, **changes):
    _, scope, lease, broker = held
    values = dict(field_keys=("locality",))
    values.update(changes)
    return asyncio.run(broker.execute(scope, lease, "source_capture_v2:" + digest(request),
        request, 1, dispatch, **values))


async def completed(*_):
    return CapturedResult({"validation": "offline fixture"}, 0)


@pytest.mark.parametrize("source,local", [("geolocate", False), ("georeference_history", False),
                                         ("georeference_history", True)])
def test_exact_source_read_rechecks_all_three_gates_and_preserves_lock(held, source, local):
    store, scope, _, _ = held
    request, checks = logical(source, local), []
    before = store.job(scope)
    with permit(held, request, lambda: checks.append("fresh proof")):
        receipt = run(held, request, completed)
    assert len(checks) == 3
    assert store.effect(scope, receipt.effect_id)["field_keys"] == ["locality"]
    assert store.job(scope)["fields"] == before["fields"]
    assert store.job(scope)["human_lock_proofs"] == before["human_lock_proofs"]
    assert store.budget(scope)["held_micro_usd"] == 0


def test_full_logical_command_digest_without_private_context_still_denies(held):
    with pytest.raises(StaleWork, match="human-locked"):
        run(held, logical(), completed)


@pytest.mark.parametrize("failed_gate", [1, 2, 3])
def test_stale_command_at_each_gate_never_dispatches_and_retains_existing_hold(held, failed_gate):
    store, scope, _, _ = held
    request, checks, sends = logical(), [], []
    def verify():
        checks.append(1)
        if len(checks) == failed_gate:
            raise StaleWork("current command or human input proof changed")
    async def dispatch(*_):
        sends.append(1)
        return await completed()
    with permit(held, request, verify), pytest.raises(StaleWork, match="proof changed"):
        run(held, request, dispatch)
    assert sends == []
    assert store.budget(scope)["held_micro_usd"] == (0 if failed_gate == 1 else 1)
    if failed_gate == 3:
        effect = next(iter(store._read(scope).state["effects"].values()))
        assert effect["status"] == "held_unknown"


@pytest.mark.parametrize("change", ["source", "field", "command", "tool", "contract", "operation"])
def test_mismatched_or_model_envelope_cannot_create_a_permit(held, change):
    _, scope, _, broker = held
    request = logical()
    operation = "source_capture_v2:" + digest(request)
    if change == "source":
        request["arguments"]["source_id"] = "taxonomy"
    elif change == "field":
        request["arguments"]["field_key"] = "country"
    elif change == "command":
        request["trusted_derivation_command_digest"] = "e" * 64
    elif change == "tool":
        request["tool_id"] = "model_request"
    elif change == "contract":
        request["contract_version"] = "research-model-request/v1"
    else:
        operation = "model:" + digest(request)
    with pytest.raises(PermissionError):
        with _trusted_locked_source_read(broker, scope, operation, request,
                field_key="locality", source_id="geolocate", command_digest="c" * 64,
                verify_current=lambda: None):
            pytest.fail("mismatched envelope admitted")


@pytest.mark.parametrize("fields", [(), ("country",), ("locality", "country"), ("latitude",)])
def test_permit_cannot_be_reused_for_other_or_implicit_fields(held, fields):
    request = logical()
    with permit(held, request), pytest.raises(PermissionError):
        run(held, request, completed, field_keys=fields)


@pytest.mark.parametrize("change", ["broker", "scope", "request", "operation"])
def test_permit_cannot_escape_exact_broker_scope_and_logical_effect(held, change):
    store, scope, lease, broker = held
    request = logical()
    with permit(held, request), pytest.raises(PermissionError):
        other = DurableEffectBroker(store, broker.blobs) if change == "broker" else broker
        other_scope = replace(scope, actor_uid="another") if change == "scope" else scope
        other_request = dict(request, field_revision=1) if change == "request" else request
        operation = "model:request" if change == "operation" else "source_capture_v2:" + digest(request)
        asyncio.run(other.execute(other_scope, lease, operation, other_request, 1,
            completed, field_keys=("locality",)))


@pytest.mark.parametrize("gate", ["reserve", "mark_sending", "validate_dispatch"])
def test_exiting_private_context_restores_denial_at_every_gate(held, gate):
    store, scope, lease, _ = held
    request = logical()
    with permit(held, request):
        effect = store.reserve_effect(scope, lease, "source_capture_v2:" + digest(request), request,
            1, field_keys=("locality",))
        if gate == "validate_dispatch":
            attempt = store.mark_sending(scope, lease, effect["effect_id"])
    with pytest.raises(StaleWork, match="human-locked"):
        if gate == "reserve":
            store.reserve_effect(scope, lease, "source_capture_v2:" + digest(request), request,
                1, field_keys=("locality",))
        elif gate == "mark_sending":
            store.mark_sending(scope, lease, effect["effect_id"])
        else:
            store.validate_dispatch(scope, lease, effect["effect_id"], attempt["attempt_id"])
    assert store.budget(scope)["held_micro_usd"] == 1


@pytest.mark.parametrize("barrier", ["halted", "exhausted", "paused", "lease", "live"])
def test_source_permit_cannot_bypass_other_admission_barriers(held, barrier):
    store, scope, lease, broker = held
    request = logical()
    if barrier == "halted":
        store._mutate(scope, lambda state, _: state.update(halted=True))
    elif barrier == "exhausted":
        store.reserve_effect(scope, lease, "ordinary-test", {}, 10, field_keys=("latitude",))
    elif barrier == "paused":
        store.pause(scope, expected_generation=1)
    elif barrier == "lease":
        held = store, scope, replace(lease, fence=lease.fence + 1), broker
    with permit(held, request), pytest.raises((BudgetExceeded, StaleWork, PermissionError)):
        run(held, request, completed, execution_class="live" if barrier == "live" else "offline")


def test_permit_does_not_authorize_checkpoint_publication(held):
    store, scope, lease, _ = held
    with permit(held, logical()), pytest.raises(StaleWork):
        store.checkpoint(scope, lease, "locality", {"changed": True}, expected_revision=0)
    assert store.job(scope)["fields"]["locality"]["locked"]


@pytest.mark.parametrize("flag", [True, False])
def test_boolean_proof_callback_is_not_authority(held, flag):
    with permit(held, logical(), lambda: flag), pytest.raises(PermissionError, match="flag"):
        run(held, logical(), completed)


def test_copied_context_cannot_retain_authority_after_exit(held):
    with permit(held, logical()):
        inherited = copy_context()
    with pytest.raises(PermissionError):
        inherited.run(run, held, logical(), completed)


def test_source_send_preserves_existing_canonical_authorization(held, monkeypatch):
    store, scope, _, broker = held
    authorization = dict(canonical_revision=7, canonical_run_id=str(uuid4()),
        binding_id="binding", job_key=scope.key, generation=scope.generation,
        record_version_id="record", snapshot_sha256="f" * 64)
    observed = []
    original = store.mark_sending
    def mark(*args, **kwargs):
        observed.append(kwargs.get("send_authorization"))
        # SQLite is an offline fixture. Inspect forwarding, not native SQL authorization.
        kwargs.pop("send_authorization", None)
        return original(*args, **kwargs)
    monkeypatch.setattr(store, "mark_sending", mark)
    monkeypatch.setattr(broker, "send_authorization", lambda _: authorization)
    with permit(held, logical()):
        run(held, logical(), completed)
    assert observed == [authorization]
