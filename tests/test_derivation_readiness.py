"""Public capability must reflect the deployed worker, including rollout gaps."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from specimen_digitization.application.derivation_readiness import DeployedDerivationWorker
from specimen_digitization.application.lane_dispatch import RUN_API

JOB = 'projects/specimen-digitization/locations/us-east4/jobs/specimen-worker'
SHA = 'a' * 40


@pytest.fixture
def readiness(monkeypatch):
    monkeypatch.setattr('specimen_digitization.research_harness.committed_pins.committed_harness_route',
        lambda profile: 'research' if profile == 'configured' else None)
    scope = SimpleNamespace(collection_id='collection')
    specimen = SimpleNamespace(scope=scope, asset=SimpleNamespace(sensitive=False),
        run=SimpleNamespace(profile_snapshot='configured'))
    principal = SimpleNamespace(scope=scope)
    metadata = {'name':JOB, 'labels':{'source-sha':SHA}, 'reconciling':False,
        'terminalCondition':{'state':'CONDITION_SUCCEEDED'},
        'template':{'taskCount':1, 'parallelism':1, 'template':{'maxRetries':0,
            'containers':[{'args':['--mode','production','--drain','--max-seconds','3300'],
                'env':[{'name':'SPECIMEN_RESEARCH_HARNESS','value':'on'}]}]}}}
    calls = []
    def get(url, *, timeout):
        calls.append((url, timeout))
        return SimpleNamespace(status_code=200, json=lambda:deepcopy(metadata))
    dispatcher = SimpleNamespace(job=JOB, session=lambda:SimpleNamespace(get=get))
    check = DeployedDerivationWorker(SimpleNamespace(worker_job=JOB,
        collection_bindings=(('collection','insects'),)), {'source_sha':SHA}, dispatcher)
    return SimpleNamespace(check=check, principal=principal, specimen=specimen,
        metadata=metadata, calls=calls, dispatcher=dispatcher)


def test_capability_waits_for_same_source_enabled_worker(readiness):
    r = readiness
    assert r.check(r.principal, r.specimen) is True
    r.metadata['labels']['source-sha'] = 'b' * 40
    assert r.check(r.principal, r.specimen) is False
    r.metadata['labels']['source-sha'] = SHA
    r.metadata['template']['template']['containers'][0]['env'] = []
    assert r.check(r.principal, r.specimen) is False
    assert r.calls == [(RUN_API + JOB, 3)] * 3


@pytest.mark.parametrize('alter', [
    lambda d:d.update(name=JOB + '-other'),
    lambda d:d.update(reconciling=True),
    lambda d:d['terminalCondition'].update(state='CONDITION_FAILED'),
    lambda d:d['template'].update(taskCount=2),
    lambda d:d['template'].update(parallelism=2),
    lambda d:d['template']['template'].update(maxRetries=1),
    lambda d:d['template']['template']['containers'][0].update(args=['--mode','production']),
    lambda d:d['template']['template']['containers'][0]['env'].append(
        {'name':'SPECIMEN_RESEARCH_HARNESS','value':'off'}),
    lambda d:d['template']['template']['containers'][0].update(env=[
        {'name':'SPECIMEN_RESEARCH_HARNESS','valueSource':{'secretKeyRef':{}}}]),
])
def test_incomplete_or_changed_worker_is_unavailable(readiness, alter):
    alter(readiness.metadata)
    assert readiness.check(readiness.principal, readiness.specimen) is False


def test_unbound_collection_is_denied_before_metadata_read(readiness):
    readiness.principal.scope = SimpleNamespace(collection_id='other')
    assert readiness.check(readiness.principal, readiness.specimen) is False
    assert readiness.calls == []


@pytest.mark.parametrize('status', [403,404,500])
def test_worker_read_authority_unavailable_hides_capability(readiness, status):
    readiness.dispatcher.session = lambda:SimpleNamespace(get=lambda *a, **kw:
        SimpleNamespace(status_code=status))
    assert readiness.check(readiness.principal, readiness.specimen) is False


def test_timeout_hides_capability_without_starting_work(readiness):
    def unavailable(*args, **kwargs):
        raise TimeoutError('private transport detail')
    readiness.dispatcher.session = lambda:SimpleNamespace(get=unavailable)
    assert readiness.check(readiness.principal, readiness.specimen) is False
