"""The committed window size K, and why K roles can share one lease window.

The roles of a window run at once, so they must be independent: disjoint fields,
disjoint sources, one run budget. The worker hands the engine K roles per lease
and the engine runs K of them at once.
"""
import asyncio
from itertools import combinations
from types import SimpleNamespace

import pytest

from specimen_digitization.research_harness import native_worker, role_windows
from specimen_digitization.research_harness.contracts import ROLE_FIELDS, SpecialistRole
from specimen_digitization.research_harness.engine import ResearchEngine
from specimen_digitization.research_harness.source_readiness import CAPTURE_POLICIES, SOURCE_READINESS
from specimen_digitization.research_harness.sources import insects_registry

SHIPPED_WINDOW = True  # conftest: read the shipped constant, not the one-role pin


def windows(size):
    roster = tuple(SpecialistRole)
    return [roster[start:start + size] for start in range(0, len(roster), size)]


def test_the_window_size_is_one_committed_constant_the_engine_accepts():
    assert role_windows.ROLE_CONCURRENCY == 2
    assert type(role_windows.ROLE_CONCURRENCY) is int
    # engine.py is a pinned artifact whose constructor allows one or two roles at once.
    assert 1 <= role_windows.ROLE_CONCURRENCY <= 2
    with pytest.raises(ValueError, match="bounded_concurrency_required"):
        ResearchEngine(profile=None, requests={}, journal=None, harness_factory=None,
            model_settings_digest="0" * 64, max_concurrency=role_windows.ROLE_CONCURRENCY + 1)


def test_the_worker_asks_the_engine_for_the_runtime_s_window_of_roles(monkeypatch):
    calls = []

    async def run(**kwargs):
        calls.append(kwargs)

    async def publish(self, runtime, principal, specimen_id):
        return SimpleNamespace(reason_code=None)
    monkeypatch.setattr(native_worker.NativeResearchWorker, "_publish_committed", publish)
    runtime = SimpleNamespace(binding=SimpleNamespace(research_scope=lambda: "scope"), scope="durable",
        store=SimpleNamespace(_read=lambda scope: SimpleNamespace(state={"outbox": {}})),
        engine=SimpleNamespace(run=run), role_window=2)
    asyncio.run(native_worker.NativeResearchWorker(None)._run_runtime(runtime, None, "specimen",
        retry_command_id=None))
    assert calls == [{"role_limit": 2}]


def test_the_shipped_windows_pair_independent_roles_in_roster_order():
    shipped = windows(role_windows.ROLE_CONCURRENCY)
    assert [len(window) for window in shipped] == [2, 2, 2]
    assert shipped[0] == (SpecialistRole.TAXONOMY, SpecialistRole.GEOGRAPHY)
    assert shipped[1] == (SpecialistRole.TEMPORAL, SpecialistRole.MEASUREMENT)
    # The role with the always-terminal field (parties: identified_by_irn, the declared EMu
    # exception) is in the last window, together with collection, whichever of the two the
    # roster lists first: the window's one publication pass runs after both committed, so the
    # last publication of the run sees every role's work (the record is finalized on it).
    assert set(shipped[2]) == {SpecialistRole.PARTIES, SpecialistRole.COLLECTION}
    for window in shipped:
        fields = [key for role in window for key in ROLE_FIELDS[role]]
        assert len(fields) == len(set(fields))


def runnable_sources(role):
    """The sources a role's lookup can run: qualified in the committed readiness, with full capture."""
    registry = insects_registry(qualification_overrides=SOURCE_READINESS)
    return {policy.id for policy in registry.policies
            if role in policy.roles and set(ROLE_FIELDS[role]) & set(policy.fields) and policy.ready
            and CAPTURE_POLICIES.get(policy.id, ("denied", 0))[0] == "full_response"}


def test_no_two_roles_can_run_the_same_source():
    """Roles in a window never share a source, so the per-source request spacing (GEOLocate's 3 s)
    and the source-capture gate (one in-flight capture per field) are never contended across roles."""
    assert runnable_sources(SpecialistRole.TAXONOMY) == {"gbif", "global_names_verifier", "catalogue_of_life"}
    assert runnable_sources(SpecialistRole.GEOGRAPHY) == {"geolocate"}
    for role in (SpecialistRole.TEMPORAL, SpecialistRole.MEASUREMENT, SpecialistRole.PARTIES,
                 SpecialistRole.COLLECTION):
        assert runnable_sources(role) == set(), role
    for first, second in combinations(SpecialistRole, 2):
        assert not runnable_sources(first) & runnable_sources(second), (first, second)
