"""The live research authority's builder, the production composer and open().

Offline stand-ins replace Data Connect and the binding read; the research state
is a real SQLite store and the pins are the committed ones. No model, source or
network call is made.
"""
import asyncio
from dataclasses import asdict, replace
from types import SimpleNamespace
from uuid import UUID

import pytest

from specimen_digitization.application.domain import Principal, Scope
from specimen_digitization.application.native_drain import compose_registered_native_drain
from specimen_digitization.application.production import actor_uid
from specimen_digitization.research_harness import provisioning
from specimen_digitization.research_harness.contracts import FieldKey
from specimen_digitization.research_harness.persistence import (
    DurabilityScope, HeldUnknown, LiveResearchAuthority, PinnedRuntime, ResearchStore,
    SqliteStateBackend, StaleWork,
)
from specimen_digitization.research_harness.production_runtime import (
    NativeResearchRuntimeFactory, committed_job_pins, research_budget_policy, research_program_key,
)
from specimen_digitization.research_harness.workflow_bridge import (
    NativeResearchWorkflow, authorize_live_research, compose_production_research_workflow,
    compose_registered_native_workflow, membership_verifier,
)

from test_provisioning import COLLECTION, ORG, WORKER, plan_specimen

ON = {"SPECIMEN_RESEARCH_HARNESS": "on"}
SNAPSHOT_SHA = "5" * 64


class Repository:
    def __init__(self, specimen, role="operator"):
        self.specimen, self.role, self.member_reads = specimen, role, 0

    def memberships(self, uid):
        self.member_reads += 1
        return [{"organization_id": ORG, "collection_id": COLLECTION, "role": self.role,
            "can_view_sensitive": False}] if self.role else []

    def get(self, scope, specimen_id):
        assert specimen_id == self.specimen.id
        return self.specimen


def principal(user=WORKER):
    return Principal(user_id=user, role="operator",
        scope=Scope(organization_id=ORG, collection_id=COLLECTION))


def binding_for(specimen, *, sensitive=False, run_id=None, program_key=None):
    run_id = run_id or specimen.run.id
    job_id = f"{specimen.run.id}:r{specimen.version}"
    from specimen_digitization.application.storage import digest
    return SimpleNamespace(
        canonical=SimpleNamespace(sensitive=sensitive, specimen_id=specimen.id),
        # The registration's base identity holds UUID objects, as CanonicalIdentityV1 does.
        base_canonical=SimpleNamespace(canonical_run_id=UUID(run_id), snapshot_sha256=SNAPSHOT_SHA),
        canonical_profile_digest=digest(specimen.run.profile_snapshot),
        program_key=program_key or research_program_key(run_id),
        durability_scope=lambda caller: DurabilityScope(ORG, COLLECTION, specimen.id, job_id, 1,
            caller.user_id, sensitive),
        validate_job=lambda job, *, program_key: None)


@pytest.fixture
def worker_context():
    token = actor_uid.set(WORKER)
    yield
    actor_uid.reset(token)


def authorize(specimen, binding, *, caller=None, actor=WORKER, environ=ON, repository=None):
    repository = repository or Repository(specimen)
    return asyncio.run(authorize_live_research(caller or principal(), specimen, binding,
        actor_uid=actor, environ=environ, verify_access=membership_verifier(repository)))


def test_the_worker_actor_gets_an_authority_covering_only_its_run(worker_context):
    specimen = plan_specimen()
    binding = binding_for(specimen)
    authority = authorize(specimen, binding)
    assert authority == LiveResearchAuthority(ORG, COLLECTION, specimen.id, WORKER,
        "harness-deepseek", switch_on=True)
    assert authority.covers(binding.durability_scope(principal()))
    # Without a configured actor, the verified actor context is the worker.
    assert authorize(specimen, binding, actor=None) == authority


@pytest.mark.parametrize("environ,error", [
    ({}, "research_harness_switch_off"), ({"SPECIMEN_RESEARCH_HARNESS": "off"}, "research_harness_switch_off"),
])
def test_the_switch_off_refuses(worker_context, environ, error):
    specimen = plan_specimen()
    with pytest.raises(PermissionError, match=error):
        authorize(specimen, binding_for(specimen), environ=environ)


def test_an_invalid_switch_value_names_the_setting(worker_context):
    specimen = plan_specimen()
    with pytest.raises(ValueError, match="SPECIMEN_RESEARCH_HARNESS"):
        authorize(specimen, binding_for(specimen), environ={"SPECIMEN_RESEARCH_HARNESS": "yes"})


def test_a_principal_or_context_other_than_the_worker_refuses(worker_context):
    specimen = plan_specimen()
    binding = binding_for(specimen)
    with pytest.raises(PermissionError, match="research_worker_actor_required"):
        authorize(specimen, binding, caller=principal("reviewer-person"))
    with pytest.raises(PermissionError, match="research_worker_actor_required"):
        authorize(specimen, binding, actor="another-worker")
    token = actor_uid.set("reviewer-person")
    try:
        with pytest.raises(PermissionError, match="research_worker_actor_required"):
            authorize(specimen, binding)
    finally:
        actor_uid.reset(token)


@pytest.mark.parametrize("route", [None, "handwriting-qwen", "no-such-route"])
def test_a_profile_without_a_harness_route_refuses(worker_context, route):
    specimen = plan_specimen()
    specimen.run.profile_snapshot = {**specimen.run.profile_snapshot, "harness_route": route}
    with pytest.raises(PermissionError, match="research_profile_harness_disabled"):
        authorize(specimen, binding_for(specimen))


def test_a_sensitive_binding_or_another_run_refuses(worker_context):
    specimen = plan_specimen()
    with pytest.raises(PermissionError, match="research_binding_scope_denied"):
        authorize(specimen, binding_for(specimen, sensitive=True))
    with pytest.raises(PermissionError, match="research_binding_scope_denied"):
        authorize(specimen, binding_for(specimen, run_id="00000000-0000-4000-8000-0000000000aa"))


def test_membership_is_read_afresh_and_a_lost_membership_refuses(worker_context):
    specimen = plan_specimen()
    repository = Repository(specimen)
    authorize(specimen, binding_for(specimen), repository=repository)
    repository.role = None
    with pytest.raises(PermissionError, match="research_worker_access_denied"):
        authorize(specimen, binding_for(specimen), repository=repository)
    assert repository.member_reads == 2


def test_the_composer_requires_the_switch_and_mounts_the_production_parts():
    ordinary = SimpleNamespace(repository=object())
    with pytest.raises(ValueError, match="research_harness_switch_off"):
        compose_production_research_workflow(ordinary, repository=object(), environ={})
    composed = compose_production_research_workflow(ordinary, repository=object(), environ=ON,
        blobs=object())
    assert isinstance(composed, NativeResearchWorkflow) and composed.ordinary is ordinary
    factory = composed.native_worker.runtime_factory
    assert callable(factory.authorize) and factory.state_backend is None
    assert composed.provision.func is provisioning.provision


@pytest.mark.parametrize("compose", [
    lambda ordinary, environ: compose_registered_native_workflow(ordinary, repository=object(),
        admission=object(), environ=environ),
    lambda ordinary, environ: compose_registered_native_drain(ordinary, repository=object(),
        environ=environ),
])
def test_the_worker_shims_follow_the_switch(monkeypatch, compose):
    ordinary = SimpleNamespace(repository=object())
    monkeypatch.setattr(NativeResearchRuntimeFactory, "__init__", lambda self, *a, **k: None)
    assert compose(ordinary, {}) is ordinary
    assert compose(ordinary, {"SPECIMEN_RESEARCH_HARNESS": "off"}) is ordinary
    mounted = compose(ordinary, ON)
    assert isinstance(getattr(mounted, "workflow", mounted), NativeResearchWorkflow)
    assert mounted.ordinary is ordinary
    with pytest.raises(ValueError, match="SPECIMEN_RESEARCH_HARNESS"):
        compose(ordinary, {"SPECIMEN_RESEARCH_HARNESS": "true"})


def test_the_drain_shim_reads_the_process_environment(monkeypatch):
    ordinary = SimpleNamespace(repository=object())
    monkeypatch.setattr(NativeResearchRuntimeFactory, "__init__", lambda self, *a, **k: None)
    monkeypatch.delenv("SPECIMEN_RESEARCH_HARNESS", raising=False)
    assert compose_registered_native_drain(ordinary, repository=object()) is ordinary
    monkeypatch.setenv("SPECIMEN_RESEARCH_HARNESS", "on")
    mounted = compose_registered_native_drain(ordinary, repository=object())
    assert isinstance(mounted.workflow, NativeResearchWorkflow) and mounted.ordinary is ordinary


class Stop(Exception):
    """open() reached the request factory: every check before it passed."""


class CountingBackend(SqliteStateBackend):
    loads = 0

    def load(self, scope, program_key):
        type(self).loads += 1
        return super().load(scope, program_key)


@pytest.fixture
def opened(tmp_path, worker_context):
    specimen = plan_specimen()
    binding = binding_for(specimen)
    scope = binding.durability_scope(principal())
    backend = CountingBackend(tmp_path / "state.sqlite")
    backend.grant(scope)
    store = ResearchStore(backend, binding.program_key)
    snapshot = specimen.run.profile_snapshot
    store.initialize(scope, research_budget_policy(snapshot))
    pins = committed_job_pins(snapshot, organization_id=ORG, collection_id=COLLECTION,
        input_digest=SNAPSHOT_SHA)
    store.create_job(scope, PinnedRuntime(**pins), [str(key) for key in FieldKey],
        record_revision=specimen.version)
    repository = Repository(specimen)

    async def stop(*_):
        raise Stop
    def factory(*, authorized=True, environ=ON):
        composed = compose_production_research_workflow(SimpleNamespace(repository=repository),
            repository=repository, environ=environ, state_backend=backend, blobs=object(),
            request_factory=stop)
        built = composed.native_worker.runtime_factory
        if not authorized:
            built.authorize = None
        async def bound(caller, ident):
            return binding
        built.discovery.binding = bound
        return built
    def open_(built):
        return asyncio.run(built.open(principal(), specimen.id, owner="offline-owner"))
    CountingBackend.loads = 0
    return SimpleNamespace(specimen=specimen, binding=binding, scope=scope, store=store,
        repository=repository, factory=factory, open=open_, backend=backend)


def test_open_with_the_authority_passes_every_check(opened):
    built = opened.factory()
    with pytest.raises(Stop):
        opened.open(built)
    with pytest.raises(Stop):
        opened.open(built)
    # The authority, and so the membership, is rebuilt at each open.
    assert opened.repository.member_reads == 2


def test_open_without_an_authority_refuses_before_reading_state(opened):
    with pytest.raises(PermissionError, match="research_live_authority_required"):
        opened.open(opened.factory(authorized=False))
    assert CountingBackend.loads == 0


def test_open_refuses_a_binding_on_another_program(opened):
    opened.binding.program_key = "research-run:00000000-0000-4000-8000-0000000000bb"
    with pytest.raises(StaleWork, match="research_program_key_unproved"):
        opened.open(opened.factory())


def test_open_holds_when_the_committed_pins_changed(opened, monkeypatch):
    from specimen_digitization.research_harness import production_runtime
    real = production_runtime.build_committed_pins
    def changed(*args, **kwargs):
        pins = real(*args, **kwargs)
        return {**pins, "settings": {"max_tokens": 4096}}
    monkeypatch.setattr(production_runtime, "build_committed_pins", changed)
    with pytest.raises(HeldUnknown, match="research_committed_pins_changed"):
        opened.open(opened.factory())


def test_open_holds_when_the_allowance_is_not_the_committed_one(opened, monkeypatch):
    from specimen_digitization.research_harness import production_runtime
    policy = research_budget_policy(opened.specimen.run.profile_snapshot)
    monkeypatch.setattr(production_runtime, "research_budget_policy",
        lambda profile: replace(policy, ceiling_micro_usd=policy.ceiling_micro_usd - 1))
    with pytest.raises(HeldUnknown, match="research_live_admission_unqualified"):
        opened.open(opened.factory())
    assert opened.store._read(opened.scope).state["budget_policy"] == asdict(policy)
