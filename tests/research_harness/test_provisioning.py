"""Research provisioning at the plan step: idempotent, with offline stand-ins.

The repository, the binding writer and the Data Connect binding read are fakes.
The research state is a real SQLite store; the base record comes from the
real ordinary projector. Label text is synthetic.
"""
import asyncio
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
        self.role = "operator"

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
    """The binding read and the registration writer, shared across ticks."""
    registered, binding, fail_next = [], None, None

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
        if cls.fail_next:
            failure, cls.fail_next = cls.fail_next, None
            raise failure
        cls.registered.append((registration, store.program_key, scope))
        cls.binding = {"active_registration_count": 1}


@pytest.fixture
def rig(tmp_path):
    class Fresh(Writer):
        registered, binding, fail_next = [], None, None
    specimen = plan_specimen()
    repository = Repository(specimen)
    backend = SqliteStateBackend(tmp_path / "state.sqlite")
    backend.grant(DurabilityScope(ORG, COLLECTION, specimen.id, "membership", 1, WORKER, False))
    principal = Principal(user_id=WORKER, role="operator",
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
    assert state["budget_policy"]["ceiling_micro_usd"] == 500_000
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
    with pytest.raises(HeldUnknown, match="native_v2_registration_rejected"):
        rig.provision()
    rig.provision()
    rig.provision()
    [(registration, program_key, _)] = rig.writer.registered
    store = ResearchStore(rig.backend, program_key)
    assert list(store._read(scope).state["jobs"]) == [scope.key]
    assert registration.binding_id == provisioning.binding_id_for(scope)


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
    store = ResearchStore(rig.backend, second[1])
    assert len(store._read(job_scope(rig, later)).state["jobs"]) == 2


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
