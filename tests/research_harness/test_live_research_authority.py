"""LiveResearchAuthority: the one scope-matched check for live research work.

Synthetic ids and a disposable local SQLite ledger; no provider is called.
"""
from dataclasses import replace

import pytest

from specimen_digitization.research_harness.persistence import (
    BudgetExceeded, BudgetPolicy, DurabilityScope, LiveResearchAuthority, PinnedRuntime,
    ResearchStore, SqliteStateBackend,
)

SCOPE = DurabilityScope("org", "collection", "specimen", "job", 1, "worker", False)
REQUIRED = "^research_live_authority_required$"
MISMATCHES = ({"organization_id": "other-org"}, {"collection_id": "other-collection"},
              {"specimen_id": "other-specimen"}, {"actor_uid": "other-worker"})


def authority(**changes):
    values = {"organization_id": "org", "collection_id": "collection", "specimen_id": "specimen",
              "actor_uid": "worker", "harness_route": "harness-deepseek", "switch_on": True}
    return LiveResearchAuthority(**{**values, **changes})


REFUSED = {"no_authority": (None, SCOPE),
           "wrong_specimen": (authority(specimen_id="other-specimen"), SCOPE),
           "wrong_actor": (authority(actor_uid="other-worker"), SCOPE),
           "sensitive_scope": (authority(), replace(SCOPE, sensitive=True))}


def rig(tmp_path, *, live_authority=None, policy=None, name="state.sqlite"):
    backend = SqliteStateBackend(tmp_path / name)
    backend.grant(SCOPE, role="operator")
    store = ResearchStore(backend, "synthetic-run-program", live_authority=live_authority)
    store.initialize(SCOPE, policy or BudgetPolicy(100, live_authorized=True, hold_reason=None))
    pins = PinnedRuntime("input", {"version": "p1"}, {"text": "exact pinned"}, {"version": "s1"},
                         {"route": "harness-deepseek"}, {"max_tokens": 128}, "specialist_harness_v2")
    store.create_job(SCOPE, pins, ["taxon", "country"])
    return store, store.claim(SCOPE, "owner", ttl_seconds=30)


def failed_country(store, lease):
    store.checkpoint(SCOPE, lease, "country", {"state": "operational_failed"}, expected_revision=0)
    return {"expected_generation": 1, "expected_field_revision": 1,
            "idempotency_key": "server-stable", "execution_class": "live"}


@pytest.mark.parametrize("changes", [
    {"switch_on": False}, {"switch_on": 1}, {"switch_on": "on"}, {"organization_id": ""},
    {"collection_id": ""}, {"specimen_id": ""}, {"actor_uid": ""}, {"actor_uid": None},
    {"harness_route": ""}])
def test_authority_requires_the_switch_on_and_every_id(changes):
    with pytest.raises(ValueError, match="^research_live_authority_invalid$"):
        authority(**changes)


def test_authority_covers_its_own_non_sensitive_scope_for_any_job_or_generation():
    assert authority().covers(SCOPE)
    assert authority().covers(replace(SCOPE, job_id="another-job", generation=7))
    assert not authority().covers(replace(SCOPE, sensitive=True))


@pytest.mark.parametrize("changes", MISMATCHES)
def test_authority_for_another_scope_or_actor_does_not_cover(tmp_path, changes):
    other = authority(**changes)
    assert not other.covers(SCOPE)
    store = ResearchStore(SqliteStateBackend(tmp_path / "state.sqlite"), "synthetic-run-program",
                          live_authority=other)
    with pytest.raises(PermissionError, match=REQUIRED):
        store.require_live_authority(SCOPE)


def test_require_live_authority_passes_only_a_covering_authority(tmp_path):
    backend = SqliteStateBackend(tmp_path / "state.sqlite")
    with pytest.raises(PermissionError, match=REQUIRED):
        ResearchStore(backend, "synthetic-run-program").require_live_authority(SCOPE)
    covered = ResearchStore(backend, "synthetic-run-program", live_authority=authority())
    covered.require_live_authority(SCOPE)
    with pytest.raises(PermissionError, match=REQUIRED):
        covered.require_live_authority(replace(SCOPE, sensitive=True))


@pytest.mark.parametrize("case", sorted(REFUSED))
def test_live_effect_without_a_covering_authority_is_refused_before_any_hold(tmp_path, case):
    live_authority, scope = REFUSED[case]
    store, lease = rig(tmp_path, live_authority=live_authority)
    with pytest.raises(PermissionError, match=REQUIRED):
        store.reserve_effect(scope, lease, "live-taxon", {"name": "Danaus plexippus"}, 10,
                             execution_class="live", field_keys=("taxon",))
    assert store.budget(SCOPE)["held_micro_usd"] == 0


def test_covering_authority_reserves_a_live_effect(tmp_path):
    store, lease = rig(tmp_path, live_authority=authority())
    effect = store.reserve_effect(SCOPE, lease, "live-taxon", {"name": "Danaus plexippus"}, 10,
                                  execution_class="live", field_keys=("taxon",))
    assert (effect["execution_class"], effect["status"], effect["held_micro_usd"]) == ("live", "reserved", 10)
    assert store.budget(SCOPE)["held_micro_usd"] == 10


def test_covering_authority_keeps_the_program_hold_and_the_ceiling(tmp_path):
    held, lease = rig(tmp_path, live_authority=authority(), policy=BudgetPolicy(100), name="hold.sqlite")
    with pytest.raises(PermissionError, match="Live dispatch blocked by imported program HOLD"):
        held.reserve_effect(SCOPE, lease, "live-taxon", {}, 10, execution_class="live")
    store, lease = rig(tmp_path, live_authority=authority(), name="ceiling.sqlite")
    with pytest.raises(BudgetExceeded):
        store.reserve_effect(SCOPE, lease, "live-taxon", {}, 101, execution_class="live")
    assert held.budget(SCOPE)["held_micro_usd"] == store.budget(SCOPE)["held_micro_usd"] == 0


@pytest.mark.parametrize("live_authority", [None, authority(actor_uid="other-worker")],
                         ids=["no_authority", "wrong_actor"])
def test_live_retry_without_a_covering_authority_is_refused(tmp_path, live_authority):
    store, lease = rig(tmp_path, live_authority=live_authority)
    arguments = failed_country(store, lease)
    with pytest.raises(PermissionError, match=REQUIRED):
        store.admit_retry(SCOPE, "country", **arguments)
    assert not any(key.startswith("retry/") for key in store._read(SCOPE).state["outbox"])


def test_covering_authority_queues_a_live_retry(tmp_path):
    store, lease = rig(tmp_path, live_authority=authority())
    command = store.admit_retry(SCOPE, "country", **failed_country(store, lease))
    assert (command["execution_class"], command["status"]) == ("live", "queued")
    assert store.job(SCOPE)["fields"]["country"]["work_state"] == "retry_scheduled"


def test_queued_live_retry_is_read_only_by_a_store_with_a_covering_authority(tmp_path):
    store, lease = rig(tmp_path, live_authority=authority())
    command = store.admit_retry(SCOPE, "country", **failed_country(store, lease))
    state = store._read(SCOPE).state
    plain = ResearchStore(store.backend, store.program_key)
    with pytest.raises(PermissionError, match=REQUIRED):
        plain._retry_command(state, SCOPE, command["id"])
    with pytest.raises(PermissionError, match=REQUIRED):
        plain.claim_retry_command(SCOPE, lease, command["id"])
    assert store._retry_command(state, SCOPE, command["id"]) == command
    assert store.claim_retry_command(SCOPE, lease, command["id"])["status"] == "running"


def test_live_policy_needs_only_a_cleared_hold_reason():
    policy = BudgetPolicy(500_000, live_authorized=True, hold_reason=None)
    assert policy.live_authorized and policy.external_ledger_digest == "local-unqualified"
    with pytest.raises(ValueError, match="^A live allowance cannot carry a hold reason$"):
        BudgetPolicy(500_000, live_authorized=True, hold_reason="external_live_admission_not_confirmed")
