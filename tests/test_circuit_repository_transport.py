"""Stored circuit numbers survive SQL Connect's Struct transport without coercion."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

from google.protobuf import json_format
from google.protobuf.struct_pb2 import Struct
import pytest
from pydantic import ValidationError

from specimen_digitization.application.circuit_runtime import RepositoryCircuitStore
from specimen_digitization.application.domain import Scope, Specimen
from specimen_digitization.application.provider_circuit import (
    CircuitConflict,
    CircuitKey,
    CircuitState,
    ProviderCircuit,
)
from specimen_digitization.application.storage import SQLiteRepository


def transported(value):
    return json_format.MessageToDict(json_format.ParseDict(value, Struct()))


@pytest.fixture
def setup(tmp_path, monkeypatch):
    repository = SQLiteRepository(tmp_path / "circuits.sqlite")
    scope = Scope(organization_id="fixture", collection_id="fixture")
    document = repository.document
    monkeypatch.setattr(repository, "document", lambda *a: transported(document(*a)))
    store = RepositoryCircuitStore(repository, scope)
    clock = [datetime(2026, 9, 9, tzinfo=timezone.utc)]
    key = CircuitKey(
        organization_id=scope.organization_id,
        collection_id=scope.collection_id,
        provider="fixture",
        config_sha256="1" * 64,
    )
    return repository, store, clock, key


def test_stored_struct_numbers_allow_restart_success_and_fence_stale_permit(setup):
    repository, store, clock, key = setup
    first = ProviderCircuit(store, lambda: clock[0]).admit(key, 20)
    assert first.status == "permitted"
    restarted = ProviderCircuit(
        RepositoryCircuitStore(repository, store.scope), lambda: clock[0]
    )
    assert restarted.record_success(first.token).status == "recorded"
    assert restarted.record_success(first.token).status == "stale"
    second = restarted.admit(key, 20)
    assert second.status == "permitted"
    assert second.token.token_id != first.token.token_id
    assert restarted.record_failure(second.token, "timeout").status == "recorded"


def test_stored_open_deadline_and_half_open_pending_permit_survive_transport(setup):
    _, store, clock, key = setup
    circuit = ProviderCircuit(store, lambda: clock[0])
    for _ in range(3):
        attempt = circuit.admit(key, 20)
        assert attempt.status == "permitted"
        assert circuit.record_failure(attempt.token, "timeout").status == "recorded"
    assert circuit.admit(key, 20).status == "open"
    clock[0] += timedelta(seconds=30)
    restarted = ProviderCircuit(store, lambda: clock[0])
    probe = restarted.admit(key, 20)
    assert probe.status == "permitted" and probe.token.probe
    assert circuit.admit(key, 20).status == "busy"
    assert restarted.record_success(probe.token).status == "recorded"


def stored_record():
    return {
        "revision": 3.0,
        "circuit_state": {
            "schema_version": 1.0,
            "fingerprint": "fixture",
            "policy_sha256": "fixture",
            "state": "CLOSED",
            "epoch": 2.0,
            "transient_failures": 0.0,
            "open_count": 0.0,
            "open_until_ms": None,
            "last_clock_ms": 1788912000000.0,
            "pending": [
                {"token_id": "fixture", "epoch": 2.0, "expires_at_ms": 1788912020000.0}
            ],
        },
    }


def store_with_record(record):
    class Repository:
        def document(self, *args):
            return record

    return RepositoryCircuitStore(Repository(), None)


@pytest.mark.parametrize(
    "path",
    [
        ("revision",),
        ("circuit_state", "schema_version"),
        ("circuit_state", "epoch"),
        ("circuit_state", "transient_failures"),
        ("circuit_state", "open_count"),
        ("circuit_state", "open_until_ms"),
        ("circuit_state", "last_clock_ms"),
        ("circuit_state", "pending", 0, "epoch"),
        ("circuit_state", "pending", 0, "expires_at_ms"),
    ],
)
@pytest.mark.parametrize("invalid", [True, -1, 1.5, float("inf"), float("nan"), 2**53, "1"])
def test_malformed_stored_integer_field_is_rejected(path, invalid):
    record = stored_record()
    target = record
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = invalid
    with pytest.raises((ValueError, TypeError)):
        store_with_record(record).load("fixture")


def test_storage_normalization_does_not_mutate_record_or_relax_public_models():
    record = stored_record()
    before = deepcopy(record)
    revision, state = store_with_record(record).load("fixture")
    assert type(revision) is int
    assert type(state["pending"][0]["epoch"]) is int
    assert record == before
    with pytest.raises(ValidationError):
        CircuitState.model_validate(record["circuit_state"])


def test_stale_revision_still_loses_compare_and_swap(setup):
    _, store, clock, key = setup
    first = ProviderCircuit(store, lambda: clock[0]).admit(key, 20)
    assert first.status == "permitted"
    revision, state = store.load(key.storage_key)
    assert store.compare_and_swap(key.storage_key, revision, state) == revision + 1
    with pytest.raises(CircuitConflict):
        store.compare_and_swap(key.storage_key, revision, state)


def test_whole_cohort_struct_transport_retains_all_forty_readings(tmp_path, monkeypatch):
    from test_cohort_reading_barrier import cohort, segment_all

    c = cohort(tmp_path, monkeypatch, regions=2, timeout=1)
    segment_all(c)
    get, document = c.repo.get, c.repo.document
    monkeypatch.setattr(
        c.repo,
        "get",
        lambda *a: Specimen.model_validate(
            transported(get(*a).model_dump(mode="json")),
            context={"persisted_snapshot": True},
        ),
    )
    monkeypatch.setattr(c.repo, "document", lambda *a: transported(document(*a)))
    for _ in range(6):
        for binding in c.launch.specimens:
            c.flow.step(c.principal, binding.specimen_id)
    assert c.worker.result_summary()["status"] == "evidence_review_required"
    reads = [event for event in c.events if event[0] == "read"]
    assert len(reads) == len(set(reads)) == 40


@pytest.mark.parametrize("invalid", [True, -1, 1.0, 1.5, float("inf"), float("nan"), 2**53 - 1, "1"])
def test_invalid_cas_revision_is_rejected_before_write(invalid):
    class Repository:
        calls = 0

        def put_document(self, *args):
            self.calls += 1
            return {"revision": 4}

    repository = Repository()
    store = RepositoryCircuitStore(repository, None)
    with pytest.raises((ValueError, TypeError)):
        store.compare_and_swap("fixture", invalid, {})
    assert repository.calls == 0


@pytest.mark.parametrize("ack", [3, 5, True, 4.5, float("inf"), 2**53])
def test_invalid_cas_acknowledgement_does_not_report_a_known_commit(ack):
    class Repository:
        calls = 0

        def put_document(self, *args):
            self.calls += 1
            return {"revision": ack}

    repository = Repository()
    store = RepositoryCircuitStore(repository, None)
    state = CircuitState(fingerprint="fixture", policy_sha256="fixture", last_clock_ms=0)
    with pytest.raises((ValueError, TypeError)):
        store.compare_and_swap("fixture", 3, state.model_dump(mode="json"))
    assert repository.calls == 1


@pytest.mark.parametrize("invalid_epoch", [1.0, True, 2**53])
def test_cas_does_not_relax_or_write_unsafe_in_process_state(invalid_epoch):
    class Repository:
        calls = 0

        def put_document(self, *args):
            self.calls += 1
            return {"revision": 4}

    repository = Repository()
    store = RepositoryCircuitStore(repository, None)
    state = CircuitState(fingerprint="fixture", policy_sha256="fixture", last_clock_ms=0)
    payload = state.model_dump(mode="json")
    payload["epoch"] = invalid_epoch
    with pytest.raises((ValueError, TypeError)):
        store.compare_and_swap("fixture", 3, payload)
    assert repository.calls == 0
