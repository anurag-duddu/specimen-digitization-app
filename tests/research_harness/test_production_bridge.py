"""The live research authority's builder, the production composer, open(), and
the worker's publication offer and status.

Offline stand-ins replace Data Connect and the binding read; the research state
is a real SQLite store and the pins are the committed ones. No model, source or
network call is made.
"""
import asyncio
import time
from dataclasses import asdict, replace
from types import SimpleNamespace
from uuid import UUID

import pytest

from specimen_digitization.application.domain import FieldValue, Principal, Scope, ValueState
from specimen_digitization.application.lane_worker import RECORD_HOLDS
from specimen_digitization.application.native_drain import compose_registered_native_drain
from specimen_digitization.application.production import actor_uid
from specimen_digitization.application.worker_deadline import WorkerDeadline
from specimen_digitization.application.workflow import OperationalBlock
from specimen_digitization.research_harness import native_worker, provisioning
from specimen_digitization.research_harness.agents import HarnessLimits
from specimen_digitization.research_harness.contracts import (
    FieldCheckpoint, FieldKey, FieldResolution, ResearchScope, WorkState, digest,
)
from specimen_digitization.research_harness.evidence import dts_policy_resolution, insects_profile
from specimen_digitization.research_harness.persistence import (
    DurabilityScope, HeldUnknown, LiveResearchAuthority, PinnedRuntime, ResearchStore,
    SqliteStateBackend, StaleWork,
)
from specimen_digitization.research_harness.production_runtime import (
    NativeResearchRuntimeFactory, committed_job_pins, research_budget_policy, research_program_key,
)
from specimen_digitization.research_harness.status import ResearchStatusV1
from specimen_digitization.research_harness.thread_view import FieldThread, ResearchThread
from specimen_digitization.research_harness.workflow_bridge import (
    RECORD_REFUSALS, NativeResearchWorkflow, authorize_live_research,
    compose_production_research_workflow, compose_registered_native_workflow, membership_verifier,
)

from test_native_canonical_contract import helper_resolutions
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
    assert factory.limits == HarnessLimits(run_timeout_seconds=240)
    # Only the role wall clock changes. Production keeps the generic model,
    # tool, request, delegate and cost admission paths; injected fixture limits
    # and a directly built harness remain independent of this composition.
    assert (factory.limits.request_limit, factory.limits.tool_calls_limit,
            factory.limits.delegated_request_limit, factory.limits.delegate_timeout_seconds,
            factory.limits.max_delegate_calls) == (8, 12, 4, 30, 1)
    assert HarnessLimits().run_timeout_seconds == 120
    custom = HarnessLimits(run_timeout_seconds=37)
    override = compose_production_research_workflow(ordinary, repository=object(),
        environ=ON, blobs=object(), limits=custom)
    assert override.native_worker.runtime_factory.limits is custom


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
def ordinary_spend():
    """What the run's ordinary chain had spent when its research state was seeded."""
    return 0


@pytest.fixture
def opened(tmp_path, worker_context, ordinary_spend):
    specimen = plan_specimen()
    binding = binding_for(specimen)
    scope = binding.durability_scope(principal())
    backend = CountingBackend(tmp_path / "state.sqlite")
    backend.grant(scope)
    store = ResearchStore(backend, binding.program_key)
    snapshot = specimen.run.profile_snapshot
    store.initialize(scope, replace(research_budget_policy(snapshot),
        external_settled_micro_usd=ordinary_spend))
    # The registered binding names the digest of the policy the state was created with.
    binding.journal_budget_policy_digest = digest(store._read(scope).state["budget_policy"])
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
        return {**pins, "settings": {"max_tokens": 1024}}
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


@pytest.mark.parametrize("ordinary,halted", [(1_000_000, False), (1_000_000, True), (0, True)])
def test_exhausted_or_halted_runtime_can_publish_without_constructing_senders(opened, monkeypatch, ordinary, halted):
    from specimen_digitization.research_harness import production_runtime as module
    from specimen_digitization.research_harness import native_materialization_services_v2 as services_module
    from specimen_digitization.research_harness.canonical_materialization_v2 import ResearchCanonicalPolicyV2

    opened.specimen.run.usage.reserved_cost_micros = ordinary
    opened.store._mutate(opened.scope, lambda state, now: state.update(halted=halted))
    built = opened.factory()  # Its request factory raises if called.
    def forbidden(*args, **kwargs):
        pytest.fail("publication recovery constructed a provider")
    monkeypatch.setattr(module, "_gateway_models", forbidden)
    monkeypatch.setattr(module, "_georeferencing_adapter", forbidden)
    monkeypatch.setattr(module, "build_research_engine", forbidden)
    monkeypatch.setattr(module, "BoundedHTTPTransport", forbidden)
    monkeypatch.setattr(ResearchCanonicalPolicyV2, "from_registered_binding", lambda binding: "reviewed-policy")
    captures = []
    def materialization(repository, objects, registry, policy, request_factory):
        assert vars(objects) == {"blobs": built.blobs}
        assert policy == "reviewed-policy" and request_factory is built.request_factory
        captures.append(objects)
        return SimpleNamespace(materializer=object(), evidence_provider=object(), projection_services=object())
    monkeypatch.setattr(services_module, "build_native_materialization_services_v2", materialization)
    runtime = opened.open(built)
    assert runtime.publication_only is True and runtime.role_window == 0
    assert runtime.engine.journal is runtime.journal and len(captures) == 1
    assert runtime.canonical_service is not None and runtime.lease.owner == "offline-owner"
    with pytest.raises(HeldUnknown, match="research_program_headroom_unavailable"):
        asyncio.run(runtime.engine.run(role_limit=1))
    state = opened.store._read(opened.scope).state
    assert state["halted"] is halted and state["effects"] == {}
    assert opened.store.budget(opened.scope)["remaining_micro_usd"] == 1_000_000 - ordinary


@pytest.mark.parametrize("change", ["paused", "invalid_halt"])
def test_publication_recovery_preserves_admission_holds(opened, monkeypatch, change):
    opened.specimen.run.usage.reserved_cost_micros = 1_000_000
    def mutate(state, now):
        if change == "paused":
            state["jobs"][opened.scope.key]["paused"] = True
        else:
            state["halted"] = "unknown"
    opened.store._mutate(opened.scope, mutate)
    with pytest.raises(HeldUnknown, match="research_live_admission_unqualified"):
        opened.open(opened.factory())


SYSTEMIC = "native_research_admission_or_binding_unavailable"


class Refusing:
    """A native worker whose research open() refuses."""
    def __init__(self, refusal):
        self.refusal = refusal

    async def run_registered(self, caller, ident, *, owner):
        raise self.refusal


def bridge_step(specimen, worker, *, provision=None, repository=None):
    ordinary = SimpleNamespace(repository=repository or Repository(specimen),
        next_step=lambda run: "plan")
    workflow = NativeResearchWorkflow(ordinary, worker, provision=provision)
    with WorkerDeadline(time.monotonic() + 30).scope():
        return workflow.step(principal(), specimen.id)


# A refusal that concerns this run alone keeps its own code, which the drain
# holds as that record's (lane_worker.RECORD_HOLDS). Every other refusal is the
# one code that ends the drain's execution.
@pytest.mark.parametrize("site,refusal,code", [
    ("open", HeldUnknown("research_committed_pins_changed"), "research_committed_pins_changed"),
    ("provision", StaleWork("research_provision_run_unavailable"), "research_provision_run_unavailable"),
    ("provision", HeldUnknown("research_provision_state_conflict"), "research_provision_state_conflict"),
    ("provision", HeldUnknown("research_provision_registration_refused"),
        "research_provision_registration_refused"),
    ("open", HeldUnknown("research_live_admission_unqualified"), "research_live_admission_unqualified"),
    ("open", HeldUnknown("research_program_headroom_unavailable"), "research_program_headroom_unavailable"),
    ("provision", HeldUnknown("native_canonical_owner_required"), SYSTEMIC),
    ("open", PermissionError("research_harness_switch_off"), SYSTEMIC),
    ("open", PermissionError("research_worker_actor_required"), SYSTEMIC),
    ("open", PermissionError("research_worker_access_denied"), SYSTEMIC),
    ("open", HeldUnknown("research_committed_pins_unavailable"), SYSTEMIC),
    ("provision", PermissionError("research_worker_actor_required"), SYSTEMIC),
    ("provision", HeldUnknown("research_base_record_unavailable"), SYSTEMIC),
])
def test_a_runs_own_refusal_keeps_its_code_for_the_drain_to_hold(site, refusal, code):
    async def provision(caller, specimen):
        if site == "provision":
            raise refusal
    with pytest.raises(OperationalBlock, match=f"^{code}$"):
        bridge_step(plan_specimen(), Refusing(refusal), provision=provision)
    assert (code in RECORD_HOLDS) is (code != SYSTEMIC)


def test_the_drain_holds_every_refusal_the_bridge_keeps_as_the_runs_own():
    assert RECORD_REFUSALS <= RECORD_HOLDS and SYSTEMIC not in RECORD_HOLDS


def test_a_job_pinned_before_the_pins_changed_is_held_as_its_record(opened, monkeypatch):
    from specimen_digitization.research_harness import production_runtime
    real = production_runtime.build_committed_pins
    monkeypatch.setattr(production_runtime, "build_committed_pins",
        lambda *args, **kwargs: {**real(*args, **kwargs), "settings": {"max_tokens": 1024}})
    built = opened.factory()

    class Opening:
        async def run_registered(self, caller, ident, *, owner):
            await built.open(caller, ident, owner=owner)

    with pytest.raises(OperationalBlock, match="^research_committed_pins_changed$"):
        bridge_step(opened.specimen, Opening(), repository=opened.repository)
    assert "research_committed_pins_changed" in RECORD_HOLDS


# A field waiting on the policy its profile declares missing (verbatim_dts)
# waits on people; every other waiting state stays an operational block.
RESEARCH_PROFILE = insects_profile(ORG, COLLECTION)
DECLARED = frozenset(row.field_key for row in RESEARCH_PROFILE.fields if row.missing_policy)
RESEARCH_SCOPE = ResearchScope(organization_id=ORG, collection_id=COLLECTION, specimen_id="synthetic-specimen",
    job_id="synthetic-job", generation=1, input_digest=digest("synthetic input"),
    profile_digest=digest(RESEARCH_PROFILE), sensitive=False)


def checkpoint(resolution):
    return FieldCheckpoint(scope=RESEARCH_SCOPE, field_key=resolution.field_key, revision=1,
        resolution=resolution, prompt_digest=digest("prompt"), model_settings_digest=digest("settings"),
        source_registry_digest=digest("registry"))


def waiting(key, state):
    return checkpoint(FieldResolution(field_key=key, work_state=state, value=FieldValue(),
        reason="synthetic waiting work"))


DTS = checkpoint(dts_policy_resolution("synthetic D/T/S text"))
TAXON = checkpoint(FieldResolution(field_key=FieldKey.TAXON, work_state=WorkState.RESOLVED,
    value=FieldValue(state=ValueState.SUPPORTED, literal="Synthetic taxon", evidence_ids=["e-taxon"],
        evidence_relations={"e-taxon": "decides"}),
    evidence_ids=("e-taxon",), reason="synthetic resolved work"))
# Deliberately malformed relation-less checkpoints. The helpers now provide
# supports relations, so these exercise the publication hold rather than
# describing a valid helper result.
def without_relations(resolution):
    return resolution.model_copy(update={"value": resolution.value.model_copy(update={"evidence_relations": {}})})


DATE = checkpoint(without_relations(helper_resolutions(RESEARCH_SCOPE, "date")[1][0]))
ELEVATIONS = tuple(checkpoint(without_relations(item) if item.field_key == FieldKey.ELEVATION_FROM_FT else item)
                   for item in helper_resolutions(RESEARCH_SCOPE, "elevation")[1])


def thread(*checkpoints, locked=()):
    """Every other field resolved; ``locked`` fields wait on policy with no checkpoint."""
    by_key = {item.field_key: item for item in checkpoints}
    fields = []
    for key in FieldKey:
        item = by_key.get(key)
        state = item.resolution.work_state if item else WorkState.WAITING_POLICY if key in locked else WorkState.RESOLVED
        fields.append(FieldThread(field_key=key, work_state=state, value=FieldValue(), checkpoint=item))
    return ResearchThread(scope=RESEARCH_SCOPE, paused=False, fields=tuple(fields), effects=(),
        resolved_count=sum(item.work_state == WorkState.RESOLVED for item in fields), exception_count=0)


def status(view, declared=DECLARED):
    return ResearchStatusV1.from_thread(view, missing_policy_fields=declared).status


def test_the_insects_profile_helper_declares_a_missing_policy_only_for_verbatim_dts():
    # The committed job profile adds fifteen more declarations on top of this helper's
    # (committed_pins.committed_research_profile; test_unqualified_label_policy.py).
    assert DECLARED == {FieldKey.VERBATIM_DTS}


def test_a_committed_held_policy_checkpoint_waits_on_people():
    assert status(thread(DTS)) == "waiting_input"
    # Without the profile's declaration it is still an operational block.
    assert status(thread(DTS), declared=frozenset()) == "blocked"
    assert ResearchStatusV1.from_thread(thread(DTS)).status == "blocked"


@pytest.mark.parametrize("other", [waiting(FieldKey.COUNTY, WorkState.WAITING_SOURCE),
    waiting(FieldKey.COUNTY, WorkState.OPERATIONAL_FAILED), waiting(FieldKey.HABITAT, WorkState.WAITING_POLICY)])
def test_other_waiting_work_beside_a_held_field_stays_blocked(other):
    assert status(thread(DTS, other)) == "blocked"


def test_a_locked_field_without_a_checkpoint_stays_blocked():
    assert status(thread(locked={FieldKey.VERBATIM_DTS})) == "blocked"


class PublishingRuntime:
    """The runtime parts _publish_committed reads, with recorded publications."""

    def __init__(self, typed):
        self.typed, self.prepared, self.proofs = typed, [], []
        self.scope, self.blobs = "durability-scope", None
        self.binding = SimpleNamespace(research_scope=lambda: RESEARCH_SCOPE)
        self.journal = SimpleNamespace(load=self._load)
        job = {"record_revision": 4, "pins": {"profile": RESEARCH_PROFILE.model_dump(mode="json")},
            "fields": {str(key): {"checkpoint": {"id": f"native-{key}", "scope": RESEARCH_SCOPE.model_dump(mode="json"),
                "payload": {"field_key": str(key)}}} for key in FieldKey}}
        self.store = SimpleNamespace(job=lambda scope: job,
            _read=lambda scope: SimpleNamespace(state={"outbox": {}}), _job=lambda state, scope: job)
        self.canonical_service = SimpleNamespace(publish_checkpoint=self._publish)

    async def _load(self, scope):
        return list(self.typed)

    async def _publish(self, principal, prepared, *, server_request_identity_digest):
        return SimpleNamespace(causal=SimpleNamespace(receipt_id=f"receipt-{prepared}"))


def publish(monkeypatch, typed, view):
    runtime = PublishingRuntime(typed)
    monkeypatch.setattr(native_worker, "read_accepted_checkpoint_proof",
        lambda store, scope, blobs, checkpoint_id: runtime.proofs.append(checkpoint_id))

    async def prepare(journal, scope, field_key, *, principal, expected_record_revision, blobs):
        runtime.prepared.append(field_key)
        return str(field_key)

    async def read_thread(_runtime):
        return view
    monkeypatch.setattr(native_worker, "prepare_native_publication", prepare)
    monkeypatch.setattr(native_worker.NativeResearchWorker, "_thread", staticmethod(read_thread))
    outcome = asyncio.run(native_worker.NativeResearchWorker(None)._publish_committed(
        runtime, principal(), RESEARCH_SCOPE.specimen_id))
    return runtime, outcome


def test_only_terminal_checkpoints_are_offered_for_publication(monkeypatch):
    county = waiting(FieldKey.COUNTY, WorkState.WAITING_SOURCE)
    runtime, outcome = publish(monkeypatch, (DTS, county, TAXON), thread(DTS, TAXON))
    assert runtime.prepared == [FieldKey.TAXON] and runtime.proofs == ["native-taxon"]
    assert outcome.checkpoint_ids == ("native-taxon",) and outcome.publication_receipt_ids == ("receipt-taxon",)
    # The held D/T/S field waits on people: no reconciliation hold, no operational block.
    assert outcome.reason_code is None and outcome.status == "waiting_input"


def test_a_source_outage_ends_the_tick_as_an_operational_block(monkeypatch):
    county = waiting(FieldKey.COUNTY, WorkState.WAITING_SOURCE)
    runtime, outcome = publish(monkeypatch, (DTS, county, TAXON), thread(DTS, county, TAXON))
    assert runtime.prepared == [FieldKey.TAXON]
    assert outcome.reason_code is None and outcome.status == "blocked"


def test_a_date_without_evidence_relations_is_not_offered_for_publication(monkeypatch):
    runtime, outcome = publish(monkeypatch, (DATE, TAXON), thread(DATE, TAXON))
    assert runtime.prepared == [FieldKey.TAXON] and runtime.proofs == ["native-taxon"]
    assert outcome.checkpoint_ids == ("native-taxon",) and outcome.publication_receipt_ids == ("receipt-taxon",)
    # Neither a reconciliation hold nor an operational block: the next
    # publication gives the field its review reason.
    assert outcome.reason_code is None and outcome.status == "completed"


def test_an_elevation_without_evidence_relations_holds_its_derived_endpoints(monkeypatch):
    runtime, outcome = publish(monkeypatch, (*ELEVATIONS, TAXON), thread(*ELEVATIONS, TAXON))
    assert runtime.prepared == [FieldKey.TAXON]
    assert outcome.reason_code is None and outcome.status == "completed"


def test_a_source_outage_beside_a_value_without_relations_stays_an_operational_block(monkeypatch):
    county = waiting(FieldKey.COUNTY, WorkState.WAITING_SOURCE)
    runtime, outcome = publish(monkeypatch, (DATE, county, TAXON), thread(DATE, county, TAXON))
    assert runtime.prepared == [FieldKey.TAXON]
    assert outcome.reason_code is None and outcome.status == "blocked"
