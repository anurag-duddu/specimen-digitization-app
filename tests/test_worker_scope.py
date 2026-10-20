"""Offline scope contracts; these do not establish deployed or paid acceptance."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application.api import SYNTHETIC_COLLECTION, SYNTHETIC_ORG, SYNTHETIC_TEXT, create_app
from specimen_digitization.application.domain import Principal, Scope
from specimen_digitization.application.intake_worker import IntakeWorker
from specimen_digitization.application.lane_dispatch import (
    CloudRunJobDispatcher, CollectionJobDispatcher, dispatch_for_scope, scope_key,
)
from specimen_digitization.application.lane_worker import DrainWorker
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
from specimen_digitization.application.worker_scope import worker_scope_from_env
from specimen_digitization.application.workflow import SyntheticAdapters

from test_bulk_intake import add, draft, stage, submit
from test_lane_drain import Clock, NonSensitiveMember, ScriptedWorkflow, queued
from test_lane_trigger import RecordingDispatcher, registry

ORG = SYNTHETIC_ORG
TEST_SCOPE = Scope(organization_id=ORG, collection_id=SYNTHETIC_COLLECTION)
SHARED_SCOPE = Scope(organization_id=ORG, collection_id='00000000-0000-4000-8000-0000000000c0')
ACTOR = 'existing-worker'
BASE = 'projects/specimen-digitization/locations/us-east4/jobs/'
ROUTE = {'worker_job': BASE + 'specimen-worker-e2e', 'intake_job': BASE + 'specimen-intake-e2e', 'actor_uid': ACTOR}


def environment(lane='worker', *, dedicated=True):
    return {
        'SPECIMEN_COLLECTION_WORKER_JOBS_JSON': json.dumps({scope_key(TEST_SCOPE): ROUTE}),
        'SPECIMEN_WORKER_ACTOR_UID': ACTOR,
        'SPECIMEN_WORKER_JOB': ROUTE['worker_job'] if dedicated else BASE + 'specimen-worker',
        'SPECIMEN_INTAKE_JOB': ROUTE['intake_job'] if dedicated else BASE + 'specimen-intake',
        'CLOUD_RUN_JOB': (ROUTE[f'{lane}_job'] if dedicated else BASE + f'specimen-{lane}').rsplit('/', 1)[-1],
        **({'SPECIMEN_WORKER_SCOPE_JSON': TEST_SCOPE.model_dump_json()} if dedicated else {}),
    }


def members():
    return [dict(scope.model_dump(), role='operator', can_view_sensitive=False)
            for scope in (SHARED_SCOPE, TEST_SCOPE)]


def test_collection_routing_is_immutable_exact_and_never_sends_overrides():
    calls = []
    session = SimpleNamespace(post=lambda url, **kw: calls.append((url, kw)) or SimpleNamespace(status_code=200))
    default = CloudRunJobDispatcher(BASE + 'specimen-worker', session=session)
    selected = CloudRunJobDispatcher(ROUTE['worker_job'], session=session)
    routes = {scope_key(TEST_SCOPE): selected}
    router = CollectionJobDispatcher(default, routes)
    routes.clear()
    assert dispatch_for_scope(router, TEST_SCOPE).status == 'requested'
    other_org = TEST_SCOPE.model_copy(update={'organization_id': '00000000-0000-4000-8000-000000000099'})
    assert dispatch_for_scope(router, other_org).status == 'requested'
    assert [url for url, _ in calls] == [
        'https://run.googleapis.com/v2/' + ROUTE['worker_job'] + ':run',
        'https://run.googleapis.com/v2/' + BASE + 'specimen-worker:run',
    ]
    assert all(kwargs == {'json': {}, 'timeout': 10} for _, kwargs in calls)
    unavailable = CollectionJobDispatcher(default, {scope_key(TEST_SCOPE): None})
    assert dispatch_for_scope(unavailable, TEST_SCOPE).status == 'unconfigured'
    assert len(calls) == 2


@pytest.mark.parametrize('lane', ['worker', 'intake'])
def test_same_actor_has_disjoint_job_memberships_before_work_inventory(lane):
    dedicated = worker_scope_from_env(environment(lane), lane=lane)
    shared = worker_scope_from_env(environment(lane, dedicated=False), lane=lane)
    assert dedicated.memberships(members()) == members()[1:]
    assert shared.memberships(members()) == members()[:1]
    with pytest.raises(PermissionError):
        dedicated.memberships(members()[:1])
    with pytest.raises(PermissionError):
        dedicated.memberships(members() + members()[1:])
    with pytest.raises(PermissionError):
        dedicated.memberships([dict(members()[1], role='viewer')])


@pytest.mark.parametrize('lane', ['worker', 'intake'])
@pytest.mark.parametrize('change', [
    {'SPECIMEN_WORKER_SCOPE_JSON': ''},
    {'SPECIMEN_WORKER_SCOPE_JSON': '{"collection_id":"private-invalid"}'},
    {'SPECIMEN_WORKER_SCOPE_JSON': SHARED_SCOPE.model_dump_json()},
    {'SPECIMEN_WORKER_ACTOR_UID': 'another-actor'},
    {'SPECIMEN_COLLECTION_WORKER_JOBS_JSON': '{}'},
    {'CLOUD_RUN_JOB': 'specimen-wrong-job'},
])
def test_dedicated_worker_fails_closed_on_scope_actor_or_job_drift(lane, change):
    with pytest.raises(ValueError) as error:
        worker_scope_from_env(dict(environment(lane), **change), lane=lane)
    assert 'private-invalid' not in str(error.value)


@pytest.mark.parametrize('dedicated', [False, True])
def test_scientific_drain_leaves_other_scope_pending(tmp_path, dedicated):
    repository = NonSensitiveMember(tmp_path / 'state.sqlite3')
    clock = Clock()
    workflow = ScriptedWorkflow(repository, clock)
    for scope, ident in ((SHARED_SCOPE, 'older-live'), (TEST_SCOPE, 'new-test')):
        queued(repository, ident, 30, scope=scope)
    policy = worker_scope_from_env(environment(dedicated=dedicated), lane='worker')
    summary = DrainWorker(repository, workflow, ACTOR,
        lambda _: policy.memberships(members()), execution_id='scope-contract',
        clock=clock, sleep=clock.sleep).run()
    selected = 'new-test' if dedicated else 'older-live'
    other_scope, other = (SHARED_SCOPE, 'older-live') if dedicated else (TEST_SCOPE, 'new-test')
    assert summary['processed'] == [selected]
    assert workflow.steps == [selected]
    assert repository.get(other_scope, other).run.stage == 'pending'


@pytest.mark.parametrize('dedicated', [False, True])
def test_intake_entrypoint_filters_before_owner_switch_and_continues_own_job(monkeypatch, dedicated):
    from specimen_digitization.application import intake_worker, cli, runtime_config
    from specimen_digitization.application.production import actor_uid

    target = TEST_SCOPE if dedicated else SHARED_SCOPE
    now, inventories, drains, wakes = [0], [], [], []
    default, test = RecordingDispatcher(), RecordingDispatcher()
    router = CollectionJobDispatcher(default, {scope_key(TEST_SCOPE): test})
    repo = SimpleNamespace(memberships=lambda user: members())
    service = SimpleNamespace(repo=repo, clock=lambda: now[0])
    def inventory(repository, scope):
        assert scope == target
        inventories.append((actor_uid.get(), scope))
        return [dict(state='waiting', owner_id='batch-owner', next_attempt=0, lease_until=0)]
    def drain(self, principal, **kwargs):
        assert principal.scope == target and actor_uid.get() == 'batch-owner'
        drains.append(principal)
        now[0] = 31
    def wake(principal, *, force):
        assert force and actor_uid.get() == 'batch-owner'
        wakes.append(principal.scope)
        return dispatch_for_scope(router, principal.scope)
    service.wake = wake
    for key, value in environment('intake', dedicated=dedicated).items():
        monkeypatch.setenv(key, value)
    if not dedicated:
        monkeypatch.delenv('SPECIMEN_WORKER_SCOPE_JSON', raising=False)
    monkeypatch.setattr('sys.argv', ['intake-worker', '--max-seconds', '30'])
    monkeypatch.setattr(runtime_config.RuntimeConfig, 'from_env', lambda: object())
    monkeypatch.setattr(cli, 'production_app', lambda _: SimpleNamespace(state=SimpleNamespace(intake=service)))
    monkeypatch.setattr(intake_worker, 'active_jobs', inventory)
    monkeypatch.setattr(IntakeWorker, 'drain', drain)
    intake_worker.main()
    assert len(drains) == 1 and wakes == [target]
    assert inventories[0] == (ACTOR, target)
    assert (default.calls, test.calls) == ((0, 1) if dedicated else (1, 0))


def test_bulk_api_staging_submit_and_pipeline_start_use_authenticated_collection(tmp_path):
    shared_intake, test_intake = RecordingDispatcher(), RecordingDispatcher()
    shared_science, test_science = RecordingDispatcher(), RecordingDispatcher()
    blobs = LocalBlobs(tmp_path / 'blobs')
    app = create_app(mode='emulator', repository=SQLiteRepository(tmp_path / 'state.sqlite3'),
        blobs=blobs, adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        identity_verifier=lambda *_: 'synthetic-reviewer', memberships=lambda _: members(),
        profile_registry=registry(),
        worker_dispatcher=CollectionJobDispatcher(shared_science, {scope_key(TEST_SCOPE): test_science}),
        intake_dispatcher=CollectionJobDispatcher(shared_intake, {scope_key(TEST_SCOPE): test_intake}))
    client = TestClient(app)
    batch = draft(client)
    item, data = add(client, batch)
    stage(client, item, data)
    p = Principal(user_id='synthetic-reviewer', scope=TEST_SCOPE, role='operator')
    IntakeWorker(app.state.intake).drain(p)
    assert app.state.intake.repo.list(TEST_SCOPE) == []
    assert (shared_intake.calls, test_intake.calls, shared_science.calls, test_science.calls) == (0, 1, 0, 0)
    submission = submit(client, batch, [item])
    assert submission.status_code == 202, submission.text
    IntakeWorker(app.state.intake).drain(p)
    assert app.state.intake.submission(p, submission.json()['id'])['counts'] == {'sent': 1}
    assert (shared_science.calls, test_science.calls) == (0, 1)
    assert len(app.state.intake.repo.list(TEST_SCOPE)) == 1
