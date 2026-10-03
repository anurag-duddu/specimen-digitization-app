"""Concurrent specialists lose the state document's compare-and-swap to each other.

A lost swap re-reads the state and runs the reducer again, up to a bound. Without a
pause the contenders retry in lockstep; each retry now waits a random time that
doubles up to a cap. Offline: a real SQLite store whose swap is lost on demand,
with the clock and the random draw replaced.
"""
import random
import time

import pytest

from specimen_digitization.research_harness.persistence import (
    BudgetPolicy, CasConflict, DurabilityScope, PinnedRuntime, ResearchStore, SqliteStateBackend,
)


class Contended(SqliteStateBackend):
    """Loses the next ``lost`` compare-and-swaps to a sibling that never wins."""
    lost = 0

    def cas(self, *args, **kwargs):
        if self.lost:
            self.lost -= 1
            raise CasConflict("a sibling wrote first")
        return super().cas(*args, **kwargs)


@pytest.fixture
def contended(tmp_path, monkeypatch):
    scope = DurabilityScope("org", "insects", "synthetic", "job", 1, "worker")
    backend = Contended(tmp_path / "state.sqlite")
    backend.grant(scope, can_view_sensitive=True)
    store = ResearchStore(backend, "program")
    store.initialize(scope, BudgetPolicy(10_000))
    store.create_job(scope, PinnedRuntime("a" * 64, {"digest": "b" * 64}, {"version": "v1"},
        {"digest": "c" * 64}, {"route": "r"}, {"max_tokens": 128}, "specialist_harness_v2"), ["taxon"])
    sleeps, bounds = [], []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    def uniform(low, high):
        bounds.append((low, high))
        return high   # the longest wait the draw allows: deterministic
    monkeypatch.setattr(random, "uniform", uniform)
    return store, scope, backend, sleeps, bounds


def test_an_uncontended_mutation_never_waits(contended):
    store, scope, backend, sleeps, bounds = contended
    store.claim(scope, "worker", ttl_seconds=60)
    assert sleeps == [] and bounds == []


def test_each_lost_swap_waits_a_random_time_that_doubles(contended):
    store, scope, backend, sleeps, bounds = contended
    backend.lost = 3
    assert store.claim(scope, "worker", ttl_seconds=60).fence == 1   # the fourth try wins
    # Random in [0, bound): the bound doubles from 10 ms. No wait after the swap that wins.
    assert bounds == [(0, 0.01), (0, 0.02), (0, 0.04)] and sleeps == [0.01, 0.02, 0.04]


def test_the_wait_is_capped_and_the_retry_bound_is_unchanged(contended):
    store, scope, backend, sleeps, bounds = contended
    backend.lost = 10 ** 6
    with pytest.raises(CasConflict, match="Bounded SQL rebase limit exceeded"):
        store.claim(scope, "worker", ttl_seconds=60)
    # 32 tries, a wait between tries only (none after the last), never above half a second.
    assert store.max_cas_retries == 32 and len(sleeps) == 31
    assert max(sleeps) == 0.5 and sleeps[:7] == [0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.5]
    assert sum(sleeps) < 14
    # The job is untouched by the lost swaps.
    assert store.job(scope)["lease"] is None
