from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import threading
from uuid import UUID

import pytest
from pydantic import ValidationError

from specimen_digitization.application.provider_circuit import (
    CircuitConflict,
    CircuitKey,
    CircuitPolicy,
    ProviderCircuit,
)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 9, 8, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


class SQLiteStore:
    """Real SQL transactions and revision CAS; each operation uses its own client."""

    def __init__(self, path):
        self.path = path
        self.barrier = None
        self.reads = self.writes = 0
        with sqlite3.connect(path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS circuit (key TEXT PRIMARY KEY, revision INTEGER NOT NULL, state TEXT NOT NULL)"
            )

    def load(self, key):
        self.reads += 1
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT revision, state FROM circuit WHERE key=?", (key,)
            ).fetchone()
        if self.barrier is not None:
            barrier, self.barrier = self.barrier, None
            barrier.wait(timeout=5)
        return (row[0], json.loads(row[1])) if row else None

    def compare_and_swap(self, key, expected_revision, state):
        self.writes += 1
        with sqlite3.connect(self.path, timeout=5) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT revision FROM circuit WHERE key=?", (key,)
            ).fetchone()
            actual = row[0] if row else None
            if actual != expected_revision:
                raise CircuitConflict()
            revision = (actual or 0) + 1
            db.execute(
                "INSERT INTO circuit(key,revision,state) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET revision=excluded.revision,state=excluded.state",
                (key, revision, json.dumps(state)),
            )
            return revision


@pytest.fixture
def setup(tmp_path):
    store, clock = SQLiteStore(tmp_path / "circuits.sqlite"), Clock()
    return store, clock, ProviderCircuit(store, clock)


def key(**changes):
    values = dict(
        organization_id="synthetic",
        collection_id="insects",
        provider="synthetic_provider",
        config_sha256="1" * 64,
    )
    values.update(changes)
    return CircuitKey(**values)


def trip(circuit, config=None):
    config = config or key()
    for _ in range(3):
        admission = circuit.admit(config, 20)
        assert admission.status == "permitted"
        assert circuit.record_failure(admission.token, "timeout").status == "recorded"
    assert circuit.admit(config, 20).status == "open"


def test_threshold_restart_half_open_success_and_duplicate_fencing(setup):
    store, clock, circuit = setup
    first = circuit.admit(key(), 20)
    assert (
        store.load(key().storage_key)[1]["pending"][0]["token_id"]
        == first.token.token_id
    )
    assert circuit.record_failure(first.token, "timeout").status == "recorded"
    assert circuit.record_failure(first.token, "timeout").status == "stale"
    for _ in range(2):
        permit = circuit.admit(key(), 20).token
        circuit.record_failure(permit, "provider_error")
    fresh = ProviderCircuit(SQLiteStore(store.path), clock)
    assert fresh.admit(key(), 20).retry_at == clock.now + timedelta(seconds=30)
    clock.advance(30)
    probe = fresh.admit(key(), 20)
    assert probe.status == "permitted" and probe.token.probe
    assert circuit.admit(key(), 20).status == "busy"
    assert fresh.record_success(probe.token).status == "recorded"
    assert circuit.record_failure(probe.token, "timeout").status == "stale"
    state = store.load(key().storage_key)[1]
    assert (
        state["state"] == "CLOSED"
        and state["transient_failures"] == state["open_count"] == 0
    )


def test_two_sqlite_clients_race_for_one_half_open_probe(setup):
    store, clock, circuit = setup
    trip(circuit)
    clock.advance(30)
    stores = (SQLiteStore(store.path), SQLiteStore(store.path))
    barrier = threading.Barrier(2)
    for client in stores:
        client.barrier = barrier
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda client: ProviderCircuit(client, clock).admit(key(), 20), stores
            )
        )
    assert sorted(r.status for r in results) == ["busy", "permitted"]
    assert len(store.load(key().storage_key)[1]["pending"]) == 1
    assert sum(s.writes for s in stores) == 2  # one winner, one rejected CAS


def test_concurrent_closed_failures_have_no_lost_increment(setup):
    store, clock, circuit = setup
    tokens = [circuit.admit(key(), 20).token for _ in range(2)]
    stores = (SQLiteStore(store.path), SQLiteStore(store.path))
    barrier = threading.Barrier(2)
    for client in stores:
        client.barrier = barrier
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda pair: ProviderCircuit(pair[0], clock).record_failure(
                    pair[1], "timeout"
                ),
                zip(stores, tokens),
            )
        )
    assert all(r.status == "recorded" for r in results)
    assert store.load(key().storage_key)[1]["transient_failures"] == 2


def test_open_epoch_fences_other_inflight_success_and_failure(setup):
    store, clock, circuit = setup
    late = circuit.admit(key(), 200).token
    trip(circuit)
    before = store.load(key().storage_key)
    assert circuit.record_success(late).status == "stale"
    assert circuit.record_failure(late, "timeout").status == "stale"
    assert store.load(key().storage_key) == before


def test_expired_probe_reopens_without_reuse_and_requires_fresh_cooldown(setup):
    store, clock, circuit = setup
    trip(circuit)
    clock.advance(30)
    probe = circuit.admit(key(), 10).token
    clock.advance(10)
    restarted = ProviderCircuit(SQLiteStore(store.path), clock)
    denied = restarted.admit(key(), 10)
    assert denied.status == "open" and denied.reason == "probe_expired_outcome_unknown"
    assert denied.retry_at == clock.now + timedelta(seconds=60)
    assert restarted.record_success(probe).status == "stale"
    clock.advance(60)
    next_probe = restarted.admit(key(), 10).token
    assert next_probe.token_id != probe.token_id and next_probe.epoch > probe.epoch


def test_retry_after_is_immediate_and_not_shortened_by_local_cap(setup):
    store, clock, circuit = setup
    token = circuit.admit(key(), 20).token
    outcome = circuit.record_failure(token, "rate_limited", retry_after=600)
    assert outcome.reason == "provider_retry_after"
    assert outcome.retry_at == clock.now + timedelta(seconds=600)
    clock.advance(300)
    assert circuit.admit(key(), 20).status == "open"
    clock.advance(300)
    assert circuit.admit(key(), 20).token.probe


def test_exponential_backoff_caps_at_300_seconds(setup):
    store, clock, circuit = setup
    trip(circuit)
    for expected in (30, 60, 120, 240, 300, 300):
        denied = circuit.admit(key(), 10)
        assert (denied.retry_at - clock.now).total_seconds() == expected
        clock.advance(expected)
        token = circuit.admit(key(), 10).token
        assert circuit.record_failure(token, "timeout").status == "recorded"


def test_scope_provider_config_isolation_and_no_sensitive_key_state(setup):
    store, clock, circuit = setup
    trip(circuit)
    for changed in (
        key(organization_id="other"),
        key(collection_id="other"),
        key(provider="other"),
        key(config_sha256="2" * 64),
    ):
        assert circuit.admit(changed, 10).status == "permitted"
        UUID(changed.storage_key)
        serialized = json.dumps(store.load(changed.storage_key)[1])
        assert "synthetic_provider" not in serialized and "insects" not in serialized
    assert (
        key().storage_key == key().storage_key
        and key().storage_key != key(collection_id="other").storage_key
    )


def test_nontransient_outcomes_do_not_increment_transient_count(setup):
    store, clock, circuit = setup
    for failure in (
        "authentication_error",
        "authorization_error",
        "policy_blocked",
        "malformed_response",
    ):
        token = circuit.admit(key(), 20).token
        result = circuit.record_failure(token, failure)
        assert result.reason == "nontransient_not_counted"
        assert store.load(key().storage_key)[1]["transient_failures"] == 0
    trip(circuit)
    clock.advance(30)
    probe = circuit.admit(key(), 20).token
    assert (
        circuit.record_failure(probe, "authentication_error").reason == "probe_failed"
    )
    assert circuit.admit(key(), 20).status == "open"


def test_utc_and_regressed_clock_fail_closed(setup):
    store, clock, circuit = setup
    circuit.admit(key(), 20)
    clock.advance(-1)
    assert circuit.admit(key(), 20).reason == "clock_regressed"
    for invalid in (
        datetime(2026, 9, 8),
        datetime(2026, 9, 8, tzinfo=timezone(timedelta(hours=1))),
        datetime.max.replace(tzinfo=timezone.utc),
        None,
    ):
        assert (
            ProviderCircuit(store, lambda: invalid).admit(key(), 20).reason
            == "clock_invalid"
        )


def test_policy_malformed_state_and_invalid_calls_are_explicit(setup):
    store, clock, circuit = setup
    with pytest.raises(ValidationError):
        CircuitPolicy(cooldown_seconds=60, max_cooldown_seconds=30)
    with pytest.raises(ValidationError):
        CircuitPolicy(max_cas_attempts=5)
    token = circuit.admit(key(), 20).token
    assert (
        ProviderCircuit(store, clock, CircuitPolicy(failure_threshold=4))
        .admit(key(), 20)
        .reason
        == "circuit_identity_or_policy_mismatch"
    )
    assert (
        circuit.record_failure(token, "unknown").reason == "failure_class_unrecognized"
    )
    for delay in (-1, float("inf"), float("nan"), True, 86401):
        assert circuit.record_failure(token, "timeout", delay).status == "blocked"
    for lease in (0, -1, float("nan"), True, 301):
        assert circuit.admit(key(), lease).reason == "invalid_probe_lease"
    revision, state = store.load(key().storage_key)
    state["state"] = "HALF_OPEN"
    state["pending"] = []
    store.compare_and_swap(key().storage_key, revision, state)
    assert circuit.admit(key(), 20).reason == "circuit_state_malformed"


def test_four_cas_attempts_and_lost_ack_never_grant_permit(setup):
    store, clock, circuit = setup

    class AlwaysConflict(SQLiteStore):
        def compare_and_swap(self, key, expected_revision, state):
            self.writes += 1
            raise CircuitConflict()

    conflict = AlwaysConflict(store.path)
    assert (
        ProviderCircuit(conflict, clock).admit(key(), 20).reason
        == "circuit_cas_contention"
    )
    assert conflict.reads == conflict.writes == 4

    class LostAck(SQLiteStore):
        def compare_and_swap(self, key, expected_revision, state):
            super().compare_and_swap(key, expected_revision, state)
            raise OSError("synthetic acknowledgement lost")

    result = ProviderCircuit(LostAck(store.path), clock).admit(key(), 20)
    assert (
        result.status == "blocked"
        and result.token is None
        and result.reason == "circuit_commit_outcome_unknown"
    )
    assert len(store.load(key().storage_key)[1]["pending"]) == 1


def test_closed_lease_expiry_and_inflight_bound(setup):
    store, clock, _ = setup
    circuit = ProviderCircuit(store, clock, CircuitPolicy(max_inflight=1))
    token = circuit.admit(key(), 10).token
    assert circuit.admit(key(), 10).reason == "circuit_inflight_limit"
    clock.advance(10)
    assert circuit.record_success(token).reason == "circuit_token_lease_expired"
    assert circuit.admit(key(), 10).status == "permitted"
    assert circuit.record_success(token).status == "stale"


def test_probe_survives_interpreter_exit_and_new_process_cannot_duplicate(setup):
    import subprocess
    import sys
    from pathlib import Path
    from specimen_digitization.application.provider_circuit import PermitToken

    store, clock, circuit = setup
    trip(circuit)
    clock.advance(30)
    code = """
import sys
sys.path.insert(0, sys.argv[1])
from datetime import datetime
from test_provider_circuit import SQLiteStore, key
from specimen_digitization.application.provider_circuit import ProviderCircuit
clock = lambda: datetime.fromisoformat(sys.argv[3])
result = ProviderCircuit(SQLiteStore(sys.argv[2]), clock).admit(key(), 20)
print(result.model_dump_json())
"""
    command = [
        sys.executable,
        "-c",
        code,
        str(Path(__file__).parent),
        str(store.path),
        clock.now.isoformat(),
    ]
    first = json.loads(subprocess.check_output(command, text=True))
    second = json.loads(subprocess.check_output(command, text=True))
    assert first["status"] == "permitted" and second["status"] == "busy"
    token = PermitToken.model_validate(first["token"])
    assert (
        ProviderCircuit(SQLiteStore(store.path), clock).record_success(token).status
        == "recorded"
    )


def test_outcome_contention_is_bounded_and_read_failure_is_typed(setup):
    store, clock, circuit = setup
    token = circuit.admit(key(), 20).token

    class ConflictingOutcome(SQLiteStore):
        def compare_and_swap(self, key, expected_revision, state):
            self.writes += 1
            raise CircuitConflict()

    conflict = ConflictingOutcome(store.path)
    assert (
        ProviderCircuit(conflict, clock).record_success(token).reason
        == "circuit_cas_contention"
    )
    assert conflict.writes == 4

    class Unavailable(SQLiteStore):
        def load(self, key):
            raise OSError("synthetic storage fault")

    assert (
        ProviderCircuit(Unavailable(store.path), clock).admit(key(), 20).reason
        == "circuit_storage_unavailable"
    )
