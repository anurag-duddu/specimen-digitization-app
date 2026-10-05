"""Research provisioning at the plan step: idempotent, with offline stand-ins.

The repository, the binding writer and the Data Connect binding read are fakes,
except where a test drives the production binding writer over a fake Data
Connect HTTP session. The research state is a real SQLite store; the base
record comes from the real ordinary projector. Label text is synthetic.
"""
import asyncio
import copy
from types import SimpleNamespace

import pytest

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import (
    Asset, Observation, Principal, Profile, ReaderHandoff, Region, Run, Scope, Specimen, Transcript,
)
from specimen_digitization.application.production import ProjectionRejected, SqlConnectRepository, actor_uid
from specimen_digitization.application.projection import Blob
from specimen_digitization.application.storage import digest as canonical_digest
from specimen_digitization.application.workflow import Workflow
from specimen_digitization.research_harness import provisioning
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.contracts import FieldKey, digest
from specimen_digitization.research_harness.persistence import (
    DurabilityScope, HeldUnknown, ResearchStore, SqliteStateBackend, StaleWork,
)
from specimen_digitization.research_harness.production_runtime import (
    committed_job_pins, research_budget_policy, research_program_key,
)

ORG = "00000000-0000-4000-8000-000000000001"
COLLECTION = "00000000-0000-4000-8000-000000000002"
WORKER = "offline-worker"
# Production's worker membership, which the connector lets register a binding.
WORKER_ROLE = "operator"


def plan_specimen(version=3):
    asset = Asset(sha256="a" * 64, blob_ref="a" * 64 + ":1", media_type="image/jpeg",
        size_bytes=10, width=100, height=100, filename="fixture.jpeg", uploader="fixture",
        sensitive=False)
    region = Region(asset_id=asset.id, x=0, y=0, width=100, height=100, order=0,
        method="fixture", version="fixture")
    reading = Observation(region_id=region.id, route_id="handwriting-qwen", model_id="fixture-model",
        provider="fixture", prompt_version="b" * 64, input_sha256="c" * 64, input_asset_id=asset.id,
        literal_text="country: Kenya", raw_ref="d" * 64 + ":2", raw_sha256="d" * 64)
    transcript = Transcript(region_id=region.id, text=reading.literal_text,
        observation_ids=[reading.id], alternatives=[reading.literal_text], resolved=True,
        decision_kind="identical_readings", selected_observation_id=reading.id,
        handoffs=[ReaderHandoff(observation_id=reading.id, role="decided_transcript",
            handed_text=reading.literal_text)])
    specimen = Specimen(scope=Scope(organization_id=ORG, collection_id=COLLECTION), asset=asset,
        version=version, run=Run(regions=[region], observations=[reading], transcripts=[transcript]))
    Workflow.parse(specimen.run, asset.id)
    profile = published_registry().profiles[0]
    snapshot = profile.model_dump(mode="json")
    specimen.run.profile = Profile(id=profile.id, version=profile.version,
        routes=tuple(profile.model_routes))
    specimen.run.profile_snapshot = snapshot
    specimen.run.profile_registry_version = "registry-1"
    specimen.run.dependencies = {"profile_snapshot_sha256": canonical_digest(snapshot),
        "profile_registry_version": "registry-1"}
    specimen.run.stage = "plan"
    return specimen


class Repository:
    """The ordinary repository calls provisioning makes."""
    variables = staticmethod(SqlConnectRepository.variables)

    def __init__(self, specimen, *, refuse=None):
        self.specimen, self.refuse = specimen, refuse
        self.inserts, self.member_reads = [], 0
        self.role = WORKER_ROLE

    def memberships(self, uid):
        self.member_reads += 1
        return [{"organization_id": ORG, "collection_id": COLLECTION, "role": self.role,
            "can_view_sensitive": False}] if self.role else []

    def execute(self, operation, variables, mutation=False):
        assert operation == "GetSnapshot" and variables["revision"] == self.specimen.version
        snapshot = self.specimen.model_dump(mode="json")
        return {"specimenSnapshot": {"revision": self.specimen.version, "snapshot": snapshot,
            "sha256": canonical_digest(snapshot), "contractVersion": "fixture"}}

    def locate(self, ref):
        sha, _, generation = ref.partition(":")
        return Blob("offline", sha, generation)

    def _sized(self, ref):
        return 64

    def _insert(self, operation, variables):
        if self.refuse == operation:
            raise ProjectionRejected("offline refusal")
        assert variables["actorUid"] == WORKER
        self.inserts.append((operation, variables["id"]))


class Writer:
    """The binding read and the registration writer, shared across ticks.

    Registration follows the connector: an operator or above registers. The
    specimen's single binding row (``rows``) is replaced when it names another
    revision; an identical registration replays; any other is refused.
    """
    registered, binding, rows, fail_next = [], None, {}, None

    def __init__(self, repository, journal, *, blobs):
        assert journal is None and blobs is None

    def _variables(self, principal, specimen_id):
        return {"organizationId": ORG, "collectionId": COLLECTION, "specimenId": specimen_id,
            "actorUid": principal.user_id}

    async def _execute(self, operation, variables):
        assert operation == "GetCanonicalResearchBindingV2"
        return {"binding": type(self).binding}

    async def register_current_binding(self, principal, specimen_id, registration, *, store, scope):
        cls = type(self)
        if principal.role not in {"operator", "reviewer", "manager", "admin"}:
            raise PermissionError("native_canonical_operator_required")
        if cls.fail_next:
            failure, cls.fail_next = cls.fail_next, None
            raise failure
        existing = cls.rows.get(specimen_id)
        stale = existing is not None and (existing.binding_id != registration.binding_id
            and existing.current_canonical != registration.current_canonical)
        if existing is not None and not stale and existing != registration:
            raise PublicationUnavailable("native_canonical_transaction_rejected")
        cls.rows[specimen_id] = registration
        cls.registered.append((registration, store.program_key, scope))
        cls.binding = {"active_registration_count": 1}


class ConnectorResponse:
    status_code = 200

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


class ConnectorSession:
    """The Data Connect HTTP session the real binding writer posts through.

    No binding is current, and RegisterCanonicalResearchBindingV2 answers with
    the GraphQL errors the connector returns for ``refusal``.
    """

    def __init__(self, refusal):
        self.refusal, self.posts = refusal, []

    def post(self, url, json=None, timeout=None):
        operation = json["operationName"]
        self.posts.append((operation, url.rsplit(":", 1)[1]))
        if operation == "GetCanonicalResearchBindingV2":
            return ConnectorResponse({"data": {"organizationMember": {"active": True},
                "collectionMember": {"active": True, "role": WORKER_ROLE, "canViewSensitive": False},
                "specimen": {"sensitive": False}, "binding": None}})
        assert operation == "RegisterCanonicalResearchBindingV2"
        return ConnectorResponse({"errors": [self.refusal]})


CONNECTOR_URL = "https://dataconnect.invalid/v1/projects/p/locations/l/services/s/connectors/c"
# The connector's GraphQL errors for a refused registration: a registration the
# row checks do not admit, or one that may not replace the current row, writes
# no row and fails the @check on the count.
REGISTRATION_REFUSALS = {
    "row_checks": {"message": "research registration unavailable",
        "extensions": {"code": "FAILED_PRECONDITION"}},
}


@pytest.fixture
def rig(tmp_path):
    class Fresh(Writer):
        registered, binding, rows, fail_next = [], None, {}, None
    specimen = plan_specimen()
    repository = Repository(specimen)
    backend = SqliteStateBackend(tmp_path / "state.sqlite")
    backend.grant(DurabilityScope(ORG, COLLECTION, specimen.id, "membership", 1, WORKER, False))
    principal = Principal(user_id=WORKER, role=WORKER_ROLE,
        scope=Scope(organization_id=ORG, collection_id=COLLECTION))
    token = actor_uid.set(WORKER)
    def provision(value=None):
        return asyncio.run(provisioning.provision(repository, principal, value or specimen,
            state_backend=backend, writer_factory=Fresh))
    yield SimpleNamespace(specimen=specimen, repository=repository, backend=backend,
        principal=principal, writer=Fresh, provision=provision)
    actor_uid.reset(token)


def job_scope(rig, specimen=None):
    specimen = specimen or rig.specimen
    return DurabilityScope(ORG, COLLECTION, specimen.id, provisioning.research_job_id(specimen),
        1, WORKER, False)


def test_first_tick_writes_the_base_record_state_job_and_binding(rig):
    scope = job_scope(rig)
    rig.provision()
    operations = [operation for operation, _ in rig.repository.inserts]
    assert operations.count("AppendRecordVersionV2") == 1
    assert operations.count("AppendResolvedFieldV2") == 20
    [(registration, program_key, bound)] = rig.writer.registered
    assert program_key == research_program_key(rig.specimen.run.id) and bound == scope
    store = ResearchStore(rig.backend, program_key)
    state = store._read(scope).state
    job = store.job(scope)
    snapshot = rig.specimen.model_dump(mode="json")
    pins = committed_job_pins(rig.specimen.run.profile_snapshot, organization_id=ORG,
        collection_id=COLLECTION, input_digest=canonical_digest(snapshot))
    assert state["budget_policy"]["ceiling_micro_usd"] == 1_000_000
    assert state["budget_policy"]["live_authorized"] is True
    assert state["budget_policy"]["hold_reason"] is None
    assert job["pins"] == pins and job["record_revision"] == rig.specimen.version
    assert set(job["fields"]) == {str(key) for key in FieldKey}
    record_id = next(ident for operation, ident in rig.repository.inserts
        if operation == "AppendRecordVersionV2")
    assert str(registration.base_canonical.record_version_id) == record_id
    assert registration.base_canonical == registration.current_canonical
    assert registration.base_canonical.host_record_version_id == f"{rig.specimen.run.id}:{rig.specimen.version}"
    assert registration.base_canonical.snapshot_sha256 == canonical_digest(snapshot)
    assert (registration.job_id, registration.job_key, registration.generation) == (
        scope.job_id, scope.key, 1)
    assert registration.runtime_binding_digest == job["binding_digest"] == digest(job["pins"])
    assert registration.input_digest == canonical_digest(snapshot)
    assert registration.canonical_profile_digest == rig.specimen.run.dependencies["profile_snapshot_sha256"]
    assert registration.semantic_mapping["journal_budget_policy_digest"] == digest(state["budget_policy"])
    # No import proof exists: the legacy columns repeat the binding's own values.
    assert registration.import_proof_id == registration.binding_id
    assert registration.import_proof_digest == registration.authority_digest


def test_a_second_tick_with_a_current_binding_writes_nothing(rig):
    rig.provision()
    inserts = list(rig.repository.inserts)
    rig.provision()
    assert rig.repository.inserts == inserts
    assert len(rig.writer.registered) == 1


def test_a_retry_after_a_lost_registration_replays_one_job_and_one_binding_id(rig):
    scope = job_scope(rig)
    rig.writer.fail_next = PublicationUnavailable("native_v2_registration_rejected")
    # A refused row is this record's own hold (workflow_bridge.RECORD_REFUSALS).
    with pytest.raises(HeldUnknown, match="^research_provision_registration_refused$"):
        rig.provision()
    rig.provision()
    rig.provision()
    [(registration, program_key, _)] = rig.writer.registered
    store = ResearchStore(rig.backend, program_key)
    assert list(store._read(scope).state["jobs"]) == [scope.key]
    assert registration.binding_id == provisioning.binding_id_for(scope)


def test_an_ordinary_retry_after_registration_refusal_keeps_the_old_job_and_allowance(rig, tmp_path):
    """Real API, hold and persisted jobs; native reads/registration/effects stay offline."""
    from time import monotonic

    from fastapi.testclient import TestClient

    from specimen_digitization.application.api import create_app
    from specimen_digitization.application.lane import queue
    from specimen_digitization.application.lane_dispatch import DispatchOutcome
    from specimen_digitization.application.lane_worker import DrainWorker
    from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
    from specimen_digitization.application.worker_deadline import WorkerDeadline
    from specimen_digitization.application.workflow import OperationalBlock, SyntheticAdapters
    from specimen_digitization.research_harness.workflow_bridge import NativeResearchWorkflow

    profiles = published_registry({COLLECTION: "insects"})
    queue(rig.specimen, profiles, WORKER)
    run = rig.specimen.run
    run.stage = "plan"
    run.completed_steps = ["pin_dependencies", "classify", "quality_check", "segment",
        *(f"transcribe:{region.id}:{route}" for region in run.regions for route in run.profile.routes),
        "adjudicate", "parse"]
    run.usage.reserved_cost_micros = 583_219
    run.paid_calls = [{"step": "first_pass", "attempt": 1, "outcome": "unknown",
        "reserved_micros": 318_670, "cost_micros": None}]
    assert Workflow.next_step(run) == "plan"
    canonical = SQLiteRepository(tmp_path / "canonical.sqlite")
    original = canonical.create(rig.principal, rig.specimen, "parsed", "parsed")
    rig.specimen = rig.repository.specimen = original
    original_run = original.run.model_dump(mode="json")
    old_scope = job_scope(rig)
    program_key = research_program_key(original.run.id)
    store = ResearchStore(rig.backend, program_key)
    session = ConnectorSession(REGISTRATION_REFUSALS["row_checks"])
    rig.repository.session, rig.repository.url = session, CONNECTOR_URL
    refuse_registration = True

    async def provision(principal, specimen):
        rig.repository.specimen = specimen
        kwargs = {} if refuse_registration else {"writer_factory": rig.writer}
        await provisioning.provision(rig.repository, principal, specimen,
            state_backend=rig.backend, **kwargs)

    class Native:
        def __init__(self):
            self.calls = []

        async def run_registered(self, principal, specimen_id, *, owner):
            self.calls.append(specimen_id)
            return SimpleNamespace(status="completed")

    native = Native()
    workflow = NativeResearchWorkflow(SimpleNamespace(repository=canonical, next_step=Workflow.next_step),
        native, provision=provision)
    with WorkerDeadline(monotonic() + 60).scope():
        with pytest.raises(OperationalBlock, match="^research_provision_registration_refused$"):
            workflow.step(rig.principal, original.id)
    assert session.posts == [("GetCanonicalResearchBindingV2", "impersonateQuery"),
        ("RegisterCanonicalResearchBindingV2", "impersonateMutation")]
    refused_state = copy.deepcopy(store._read(old_scope).state)
    refused_job = copy.deepcopy(store.job(old_scope))
    assert refused_job["record_revision"] == original.version
    assert refused_job["pins"]["input_digest"] == canonical_digest(original.model_dump(mode="json"))
    assert refused_job["lease"] is None and native.calls == []

    DrainWorker(canonical, workflow, WORKER, lambda uid: [], execution_id="offline-hold")._block(
        rig.principal, original.id, "research_provision_registration_refused", hold=True)
    held = canonical.get(original.scope, original.id)
    assert held.version == original.version + 1
    assert held.run.stage == "processing_blocked"
    assert held.audit[-1].action == "lane_block"
    assert store._read(old_scope).state == refused_state

    class Dispatcher:
        calls = 0

        def start(self):
            self.calls += 1
            return DispatchOutcome(status="requested")

    dispatcher = Dispatcher()
    blobs = LocalBlobs(tmp_path / "blobs")
    reviewer = "offline-reviewer"
    app = create_app(mode="emulator", repository=canonical, blobs=blobs,
        adapters=SyntheticAdapters(blobs, "country: Kenya"),
        identity_verifier=lambda token, check: reviewer,
        memberships=lambda uid: [{"organization_id": ORG, "collection_id": COLLECTION,
            "role": "reviewer", "can_view_sensitive": False}],
        profile_registry=profiles, worker_dispatcher=dispatcher)
    response = TestClient(app, raise_server_exceptions=False).post(
        f"/v1/organizations/{ORG}/runs/{original.run.id}/actions",
        headers={"Authorization": "Bearer offline-token", "Idempotency-Key": "registration-retry"},
        json={"expected_revision": held.version, "action": "retry", "reason": "Retry after connector repair"})
    assert response.status_code == 200, response.text
    retried = canonical.get(original.scope, original.id)
    assert retried.version == original.version + 2
    assert (retried.run.id, retried.run.stage, retried.run.blocker) == (original.run.id, "pending", None)
    assert (retried.audit[-1].action, retried.audit[-1].actor, retried.audit[-1].reason) == (
        "retry", reviewer, "Retry after connector repair")
    assert dispatcher.calls == 1 and Workflow.next_step(retried.run) == "plan"
    unchanged = set(original_run) - {"stage", "blocker", "queued_at", "next_retry_at"}
    assert {key: retried.run.model_dump(mode="json")[key] for key in unchanged} == {
        key: original_run[key] for key in unchanged}
    assert canonical.version(original.scope, original.id, original.version).run.model_dump(
        mode="json") == original_run
    assert store._read(old_scope).state == refused_state

    refuse_registration = False
    with WorkerDeadline(monotonic() + 60).scope():
        workflow.step(rig.principal, original.id)
    new_scope = job_scope(rig, retried)
    [(registration, registered_program, registered_scope)] = rig.writer.registered
    assert native.calls == [original.id]
    assert registered_program == program_key and registered_scope == new_scope
    assert new_scope.key != old_scope.key and registration.binding_id != provisioning.binding_id_for(old_scope)
    assert registration.input_digest == canonical_digest(retried.model_dump(mode="json"))
    assert registration.current_canonical.record_revision == retried.version
    assert store.job(old_scope) == refused_job
    new_job = store.job(new_scope)
    assert new_job["record_revision"] == retried.version
    assert new_job["pins"]["input_digest"] == registration.input_digest != refused_job["pins"]["input_digest"]
    assert {key: value for key, value in new_job["pins"].items() if key != "input_digest"} == {
        key: value for key, value in refused_job["pins"].items() if key != "input_digest"}
    state = store._read(new_scope).state
    assert set(state["jobs"]) == {old_scope.key, new_scope.key}
    assert {key: state[key] for key in state if key != "jobs"} == {
        key: refused_state[key] for key in refused_state if key != "jobs"}
    assert state["budget_policy"]["ceiling_micro_usd"] == 1_000_000
    assert state["budget_totals"]["settled_micro_usd"] == 583_219
    assert state["budget_totals"]["remaining_micro_usd"] == 416_781
    assert canonical.get(original.scope, original.id).model_dump(mode="json") == retried.model_dump(mode="json")


def test_a_refused_base_record_holds_before_any_state(rig):
    rig.repository.refuse = "AppendRecordVersionV2"
    with pytest.raises(HeldUnknown, match="research_base_record_unavailable"):
        rig.provision()
    scope = job_scope(rig)
    assert rig.backend.load(scope, research_program_key(rig.specimen.run.id)) is None
    assert rig.writer.registered == []
    rig.repository.refuse = None
    rig.provision()
    assert len(rig.writer.registered) == 1


def test_a_new_revision_after_a_stale_binding_starts_a_new_job(rig):
    rig.provision()
    later = rig.specimen.model_copy(deep=True)
    later.version += 1
    rig.repository.specimen = later
    rig.writer.binding = None  # The row names the earlier revision.
    rig.provision(later)
    first, second = rig.writer.registered
    assert first[0].job_id.endswith("-r3") and second[0].job_id.endswith("-r4")
    assert first[1] == second[1] == research_program_key(later.run.id)
    assert first[0].binding_id != second[0].binding_id
    assert rig.writer.rows == {later.id: second[0]}
    store = ResearchStore(rig.backend, second[1])
    assert len(store._read(job_scope(rig, later)).state["jobs"]) == 2


@pytest.mark.parametrize("refusal", sorted(REGISTRATION_REFUSALS))
def test_a_registration_the_connector_refuses_holds_the_record_through_the_real_writer(rig, refusal,
                                                                                      caplog):
    # The production binding writer: the connector's GraphQL errors reach it as
    # native_canonical_transaction_rejected, which is this record's own hold.
    session = ConnectorSession(REGISTRATION_REFUSALS[refusal])
    rig.repository.session, rig.repository.url = session, CONNECTOR_URL
    with caplog.at_level("WARNING", logger=provisioning.__name__):
        with pytest.raises(HeldUnknown, match="^research_provision_registration_refused$"):
            asyncio.run(provisioning.provision(rig.repository, rig.principal, rig.specimen,
                state_backend=rig.backend))
    # The underlying code is logged so a transient connector error can be told
    # apart from a refusal; the record id is shortened and no payload is logged.
    [record] = [item for item in caplog.records if item.name == provisioning.__name__]
    assert record.levelname == "WARNING"
    assert "native_canonical_transaction_rejected" in record.getMessage()
    assert str(rig.specimen.id) not in record.getMessage()
    assert str(rig.specimen.id)[-6:] in record.getMessage()
    assert session.posts == [("GetCanonicalResearchBindingV2", "impersonateQuery"),
        ("RegisterCanonicalResearchBindingV2", "impersonateMutation")]
    # The steps before registration were written once; the next tick replays them.
    scope = job_scope(rig)
    store = ResearchStore(rig.backend, research_program_key(rig.specimen.run.id))
    assert list(store._read(scope).state["jobs"]) == [scope.key]


@pytest.mark.parametrize("change", ["sensitive", "stage", "no_route", "unpinned"])
def test_a_run_that_cannot_be_researched_is_refused_before_any_write(rig, change):
    specimen = rig.specimen.model_copy(deep=True)
    if change == "sensitive":
        specimen.asset.sensitive = True
    elif change == "stage":
        specimen.run.stage = "lookup"
    elif change == "no_route":
        specimen.run.profile_snapshot = {**specimen.run.profile_snapshot, "harness_route": None}
        specimen.run.dependencies["profile_snapshot_sha256"] = canonical_digest(specimen.run.profile_snapshot)
    else:
        specimen.run.dependencies["profile_snapshot_sha256"] = "0" * 64
    with pytest.raises(StaleWork, match="research_provision_run_unavailable"):
        rig.provision(specimen)
    assert rig.repository.inserts == [] and rig.writer.registered == []


@pytest.mark.parametrize("incomplete", ["pin_dependencies", "classify", "quality_check", "segment",
    "reader", "adjudicate", "parse", "past_plan"])
def test_a_pending_run_outside_the_plan_boundary_is_refused_before_any_write(rig, incomplete):
    run = rig.specimen.run
    run.stage = "pending"
    readers = [f"transcribe:{region.id}:{route}" for region in run.regions for route in run.profile.routes]
    run.completed_steps = ["pin_dependencies", "classify", "quality_check", "segment",
        *readers, "adjudicate", "parse"]
    if incomplete == "past_plan":
        run.completed_steps.append("plan")
    else:
        run.completed_steps.remove(readers[-1] if incomplete == "reader" else incomplete)
    assert Workflow.next_step(run) != "plan"
    with pytest.raises(StaleWork, match="^research_provision_run_unavailable$"):
        rig.provision()
    assert rig.repository.inserts == [] and rig.writer.registered == []
    assert rig.backend.load(job_scope(rig), research_program_key(run.id)) is None


def test_only_the_worker_actor_with_fresh_membership_provisions(rig):
    other = rig.principal.model_copy(update={"user_id": "someone-else"})
    with pytest.raises(PermissionError, match="research_worker_actor_required"):
        asyncio.run(provisioning.provision(rig.repository, other, rig.specimen,
            state_backend=rig.backend, writer_factory=rig.writer))
    rig.repository.role = None
    with pytest.raises(PermissionError, match="research_worker_access_denied"):
        rig.provision()
    assert rig.repository.member_reads == 1
    assert rig.repository.inserts == [] and rig.writer.registered == []


def test_an_existing_state_with_another_allowance_holds(rig):
    scope = job_scope(rig)
    store = ResearchStore(rig.backend, research_program_key(rig.specimen.run.id))
    policy = research_budget_policy(rig.specimen.run.profile_snapshot)
    from dataclasses import replace
    store.initialize(scope, replace(policy, ceiling_micro_usd=policy.ceiling_micro_usd + 1))
    with pytest.raises(HeldUnknown, match="research_provision_state_conflict"):
        rig.provision()
    assert rig.writer.registered == []


def test_the_run_allowance_is_seeded_with_the_ordinary_spend(rig):
    # The ordinary chain's running total against the same per-run limit: the
    # measured actuals of settled calls and the full reservation of any call
    # whose cost it could not measure. By the plan step every paid ordinary
    # step is done, so the number is final when the research state is created.
    rig.specimen.run.usage.reserved_cost_micros = 234_567
    scope = job_scope(rig)
    rig.provision()
    [(registration, program_key, _)] = rig.writer.registered
    state = ResearchStore(rig.backend, program_key)._read(scope).state
    policy, totals = state["budget_policy"], state["budget_totals"]
    assert policy["external_settled_micro_usd"] == 234_567 and policy["external_held_micro_usd"] == 0
    assert policy["ceiling_micro_usd"] == 1_000_000
    # The ceiling bounds the whole specimen run: the research run starts with the
    # ordinary spend already counted.
    assert totals["settled_micro_usd"] == 234_567 and totals["held_micro_usd"] == 0
    assert totals["remaining_micro_usd"] == 1_000_000 - 234_567
    # The registered binding and its authority name the seeded policy.
    assert registration.semantic_mapping["journal_budget_policy_digest"] == digest(policy)
    assert registration.authority_digest == digest({"program_key": program_key, "budget_policy": policy})


def test_a_replay_after_a_lost_registration_keeps_the_seeded_spend(rig):
    rig.specimen.run.usage.reserved_cost_micros = 40_000
    scope = job_scope(rig)
    rig.writer.fail_next = PublicationUnavailable("native_v2_registration_rejected")
    with pytest.raises(HeldUnknown, match="^research_provision_registration_refused$"):
        rig.provision()
    rig.provision()
    [(_, program_key, _)] = rig.writer.registered
    state = ResearchStore(rig.backend, program_key)._read(scope).state
    assert state["budget_policy"]["external_settled_micro_usd"] == 40_000
    assert list(state["jobs"]) == [scope.key]


def test_a_later_revision_with_a_larger_ordinary_spend_keeps_the_stored_seed(rig):
    # A person's transcription correction after research rewinds the same run to
    # parse (api.py, decision kind "transcription"), and parse is billed again, so
    # the run's later revision carries a larger ordinary spend. The run's allowance
    # is immutable (SQL), so provisioning keeps the stored seed instead of holding
    # the run with research_provision_state_conflict. The seed can then under-count
    # by the re-billed parse, at most one parse reservation (20,000) a correction.
    rig.specimen.run.usage.reserved_cost_micros = 40_000
    rig.provision()
    later = rig.specimen.model_copy(deep=True)
    later.version += 1
    later.run.usage.reserved_cost_micros = 60_000
    rig.repository.specimen = later
    rig.writer.binding = None  # The row names the earlier revision.
    rig.provision(later)
    first, second = rig.writer.registered
    state = ResearchStore(rig.backend, research_program_key(later.run.id))._read(job_scope(rig, later)).state
    assert state["budget_policy"]["external_settled_micro_usd"] == 40_000 and len(state["jobs"]) == 2
    # Both bindings name the one stored policy.
    assert first[0].semantic_mapping["journal_budget_policy_digest"] == digest(state["budget_policy"])
    assert second[0].semantic_mapping["journal_budget_policy_digest"] == digest(state["budget_policy"])
    assert second[0].job_id.endswith(f"-r{later.version}")


@pytest.mark.parametrize("change", [{"ceiling_micro_usd": 1}, {"external_held_micro_usd": 1},
    {"external_ledger_digest": "another-ledger"}, {"live_authorized": False, "hold_reason": "held"}])
def test_only_the_seed_may_differ_from_an_existing_allowance(rig, change):
    # The stored seed is reused, every other field is compared strictly.
    scope = job_scope(rig)
    store = ResearchStore(rig.backend, research_program_key(rig.specimen.run.id))
    policy = research_budget_policy(rig.specimen.run.profile_snapshot, 999)
    change = {key: policy.ceiling_micro_usd + value if key == "ceiling_micro_usd" else value
        for key, value in change.items()}
    from dataclasses import replace
    store.initialize(scope, replace(policy, **change))
    with pytest.raises(HeldUnknown, match="research_provision_state_conflict"):
        rig.provision()
    assert rig.writer.registered == []


def with_run_limit(specimen, limit):
    """The run's profile snapshot with another collection's per-run limit, re-pinned."""
    snapshot = copy.deepcopy(specimen.run.profile_snapshot)
    snapshot["processing"]["run_cost_limit_micros"] = limit
    specimen.run.profile_snapshot = snapshot
    specimen.run.dependencies["profile_snapshot_sha256"] = canonical_digest(snapshot)


@pytest.mark.parametrize("limit", [250_000, 750_000, 2_000_000])
def test_the_ceiling_is_the_collection_profiles_run_limit(rig, limit):
    # An institution sets its own limit in its collection's profile; the
    # research ceiling is that run's snapshot of it, not a constant.
    with_run_limit(rig.specimen, limit)
    rig.provision()
    [(_, program_key, _)] = rig.writer.registered
    state = ResearchStore(rig.backend, program_key)._read(job_scope(rig)).state
    assert state["budget_policy"]["ceiling_micro_usd"] == limit == state["budget_totals"]["ceiling_micro_usd"]


def test_a_run_limit_below_one_request_reservation_holds_the_run(rig):
    with_run_limit(rig.specimen, 50_000)
    with pytest.raises(HeldUnknown, match="research_committed_pins_unavailable"):
        rig.provision()
    assert rig.writer.registered == [] and rig.repository.inserts == []


def reviewed_candidate():
    from specimen_digitization.application.domain import AuditEvent, Evidence
    from specimen_digitization.application.storage import ReviewDecisionProof
    specimen = plan_specimen()
    evidence = Evidence(id="candidate-evidence", kind="authority_selection", source="gbif",
        locator="research-candidate:selection-1", excerpt="Chosen taxon | 123",
        raw_ref="a" * 64 + ":1", digest="a" * 64)
    specimen.run.evidence.append(evidence)
    field = specimen.run.fields["taxon"]
    field.parsed = field.normalized = "Chosen taxon"
    field.authority_id = "123"
    field.evidence_ids.append(evidence.id)
    field.evidence_relations[evidence.id] = "decides"
    specimen.run.dependencies["human_review_field_locks"] = {
        "taxon": {"selection_id": "selection-1", "evidence_id": evidence.id}}
    event = AuditEvent(actor="real-reviewer", action="review_research_candidate", reason="chosen source",
        after={"field_key": "taxon", "selection_id": "selection-1", "value": "Chosen taxon",
            "authority_id": "123", "source_id": "gbif", "effect_id": "effect", "checkpoint_id": "checkpoint",
            "evidence_ids": [evidence.id]}, base_revision=1, resulting_revision=2)
    specimen.audit.append(event)
    proof = ReviewDecisionProof(specimen.id, event, 1, 2, "b" * 64, "c" * 64, "real-server-audit")
    return specimen, proof


def test_only_verified_candidate_audit_and_matching_ordinary_evidence_create_lock():
    specimen, proof = reviewed_candidate()
    locks = provisioning.verified_human_locks(specimen, [proof])
    assert set(locks) == {"taxon"} and len(locks["taxon"]) == 64
    with pytest.raises(HeldUnknown, match="human_lock_provenance"):
        provisioning.verified_human_locks(specimen, [])


@pytest.mark.parametrize("mutation", ["field", "action", "value", "authority", "source", "selection",
    "evidence", "locator", "relation", "raw", "duplicate"])
def test_candidate_lock_provenance_mismatch_fails_closed(mutation):
    specimen, proof = reviewed_candidate()
    if mutation in {"field", "action", "value", "authority", "source", "selection", "evidence"}:
        if mutation == "action":
            proof.event.action = "process"
        else:
            key = {"field": "field_key", "authority": "authority_id", "source": "source_id",
                "selection": "selection_id", "evidence": "evidence_ids"}.get(mutation, mutation)
            proof.event.after[key] = [] if mutation == "evidence" else "changed"
    if mutation == "locator": specimen.run.evidence[-1].locator = "candidate:other"
    if mutation == "relation": specimen.run.fields["taxon"].evidence_relations.clear()
    if mutation == "raw": specimen.run.evidence[-1].raw_ref = None
    with pytest.raises(HeldUnknown, match="human_lock_provenance"):
        provisioning.verified_human_locks(specimen, [proof, proof] if mutation == "duplicate" else [proof])


def test_base_record_projection_receives_repository_verified_review_proofs(monkeypatch):
    specimen, proof = reviewed_candidate()
    repository = Repository(specimen)
    repository._review_proofs = lambda scope, current: ([proof], None)
    calls = []
    def writes(*args, **kwargs):
        calls.append(kwargs)
        return [SimpleNamespace(operation="AppendRecordVersionV2", variables={"id": "record", "actorUid": WORKER})]
    monkeypatch.setattr(provisioning.projection, "writes", writes)
    token = actor_uid.set(WORKER)
    try:
        assert provisioning._write_base_record(repository, specimen.scope, specimen, WORKER) == "record"
    finally:
        actor_uid.reset(token)
    assert calls == [{"base_record": True, "review_proofs": [proof]}]


def test_new_job_initializes_human_locks_atomically_and_replay_cannot_remove_them(tmp_path):
    from specimen_digitization.research_harness.persistence import BudgetPolicy, PinnedRuntime
    specimen, proof = reviewed_candidate()
    scope = DurabilityScope(ORG, COLLECTION, specimen.id, "future-job", 1, WORKER, False)
    backend = SqliteStateBackend(tmp_path / "human-locks.sqlite")
    backend.grant(scope)
    store = ResearchStore(backend, "research-run:human-locks")
    store.initialize(scope, BudgetPolicy(1_000_000))
    pins = PinnedRuntime("input", {}, {}, {}, {}, {}, "fixture")
    locks = provisioning.verified_human_locks(specimen, [proof])
    job = store.create_job(scope, pins, ["taxon", "country"], human_locks=locks)
    assert job["fields"]["taxon"]["locked"] is True
    assert job["fields"]["country"]["locked"] is False
    assert job["human_lock_proofs"] == locks
    assert store.create_job(scope, pins, ["taxon", "country"], human_locks=locks) == job
    with pytest.raises(ValueError, match="immutable"):
        store.create_job(scope, pins, ["taxon", "country"])
