"""The committed window size K, and why K roles can share one lease window.

The roles of a window run at once, so they must be independent: disjoint fields,
disjoint model HTTP sources, one run budget. The worker hands the engine K roles per lease
and the engine runs K of them at once.
"""
import asyncio
from itertools import combinations
from types import SimpleNamespace

import pytest

from specimen_digitization.research_harness import native_worker, role_windows
from specimen_digitization.research_harness.contracts import (
    ROLE_FIELDS, FieldKey, ResearchScope, SourceQuery, SpecialistRequest, SpecialistRole,
)
from specimen_digitization.research_harness.engine import ResearchEngine
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.source_readiness import CAPTURE_POLICIES, SOURCE_READINESS
from specimen_digitization.research_harness.sources import FixtureSourceTransport, SourceBroker, insects_registry



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

    async def publish(self, runtime, principal, specimen_id, *, publication_progress=None):
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
    """Model HTTP lookups: qualified and fully captured; worker-only local adapters are separate."""
    registry = insects_registry(qualification_overrides=SOURCE_READINESS)
    return {policy.id for policy in registry.policies
            if role in policy.roles and set(ROLE_FIELDS[role]) & set(policy.fields) and policy.ready
            and CAPTURE_POLICIES.get(policy.id, ("denied", 0))[0] == "full_response"}


def test_no_two_roles_can_run_the_same_source():
    """Roles in a window never share an HTTP source, so per-source request spacing (GEOLocate's 3 s)
    and the source-capture gate (one in-flight capture per field) are never contended across roles."""
    assert runnable_sources(SpecialistRole.TAXONOMY) == {"gbif", "global_names_verifier", "catalogue_of_life"}
    # a3b4c5da qualified the historical APIs; c9ae7d1c enabled their geography-v6 use.
    assert runnable_sources(SpecialistRole.GEOGRAPHY) == {"geolocate", "tgn", "wikidata", "nga"}
    for role in (SpecialistRole.TEMPORAL, SpecialistRole.MEASUREMENT, SpecialistRole.PARTIES,
                 SpecialistRole.COLLECTION):
        assert runnable_sources(role) == set(), role
    for first, second in combinations(SpecialistRole, 2):
        assert not runnable_sources(first) & runnable_sources(second), (first, second)


@pytest.mark.parametrize("source_id", ["tgn", "wikidata", "nga"])
@pytest.mark.parametrize("role", [role for role in SpecialistRole if role != SpecialistRole.GEOGRAPHY])
def test_qualified_historical_source_refuses_another_role_before_effect_or_transport(source_id, role):
    registry = insects_registry(qualification_overrides=SOURCE_READINESS)
    scope = ResearchScope(organization_id="org", collection_id="collection", specimen_id="specimen",
        job_id="job", generation=1, input_digest="1" * 64, profile_digest="2" * 64, sensitive=False)
    prompt = resolve_prompt(role, profile_digest=scope.profile_digest,
        source_registry_digest=registry.digest, toolset_digest="3" * 64,
        model_route="fixture", output_schema_digest="4" * 64)
    request = SpecialistRequest(scope=scope, role=role, field_keys=ROLE_FIELDS[role], prompt=prompt)
    calls = []

    async def unexpected_call(*args, **kwargs):
        calls.append((args, kwargs))
        pytest.fail("cross-role lookup reached effect dispatch or transport")

    broker = SourceBroker(registry, transport=FixtureSourceTransport(unexpected_call),
        effect_dispatch=unexpected_call)
    assert registry.get(source_id).ready
    assert source_id not in broker.available_sources(request)
    query = SourceQuery(source_id=source_id, field_key=FieldKey.CITY, query_text="Yepocapa")
    with pytest.raises(ValueError, match="Source lookup escaped specialist field scope"):
        asyncio.run(broker.query_source(request, query))
    assert calls == []


@pytest.mark.parametrize("remaining,reservation,window", [
    (500_000, 100_000, 2),    # room for five requests: the full window
    (200_000, 100_000, 2),    # exactly two reservations
    (199_999, 100_000, 1),    # one micro-USD short of two
    (100_000, 100_000, 1),    # exactly one
    (50_000, 100_000, 1),     # not even one: the window is one role (its request is refused as it is today)
    (0, 100_000, 1),
    (10 ** 9, 100_000, 2),    # never above the committed constant
])
def test_a_window_is_no_wider_than_the_allowance_can_reserve_for(remaining, reservation, window):
    assert role_windows.window_size(remaining, reservation) == window


def test_the_engines_cap_is_the_one_the_window_size_is_checked_against():
    """engine.py (pinned) accepts max_concurrency up to its cap; role_windows names the same number."""
    cap = role_windows.ENGINE_MAX_CONCURRENCY
    with pytest.raises(ValueError, match="bounded_concurrency_required"):
        ResearchEngine(profile=None, requests={}, journal=None, harness_factory=None,
            model_settings_digest="0" * 64, max_concurrency=cap + 1)
    # At the cap the constructor gets past that check (and fails on the empty roster instead).
    with pytest.raises(ValueError, match="explicit_specialist_requests_required"):
        ResearchEngine(profile=None, requests={}, journal=None, harness_factory=None,
            model_settings_digest="0" * 64, max_concurrency=cap)


@pytest.mark.parametrize("configured", [0, -1, 3, 6, "2", 2.0, True, None])
def test_a_window_size_the_engine_cannot_run_is_refused_when_a_window_opens(monkeypatch, configured):
    """open() asks before it claims the lease, so a misconfigured K fails loudly with nothing to clean up."""
    monkeypatch.setattr(role_windows, "ROLE_CONCURRENCY", configured)
    with pytest.raises(ValueError, match="research_role_concurrency_unsupported"):
        role_windows.window_size(500_000, 100_000)


def test_the_window_follows_the_constant_when_it_is_changed(monkeypatch):
    monkeypatch.setattr(role_windows, "ROLE_CONCURRENCY", 1)
    assert role_windows.window_size(10 ** 9, 100_000) == 1
