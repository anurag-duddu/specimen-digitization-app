"""Synthetic durable selection contracts; no real provider/account acceptance."""
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from requests import Timeout

from specimen_digitization.application.intake_connections import GOOGLE_FILE
from specimen_digitization.application.intake_selection import PickerSelection, selection_reply
from specimen_digitization.application.intake_source_routes import install_source_routes
from specimen_digitization.application.intake_sources import ImportProblem
from specimen_digitization.application.intake_cloud_sources import CloudSource
from specimen_digitization.application.bulk_intake import ident
from specimen_digitization.application.intake_worker import IntakeWorker
from test_intake_sources import connected, Response  # noqa: F401 -- shared credential-free fixture


class Adapter:
    def __init__(self):
        self.calls = []
        self.before = lambda id: None

    def metadata(self, p, connection, id, *, timeout):
        assert timeout == 5
        self.calls.append(id)
        self.before(id)
        if id == 'denied':
            raise ImportProblem('file_access', 'Not available', 'file_access', False)
        return {'id': id, 'version': '1'}

    def row(self, connection, raw):
        return {'id': raw['id'], 'filename': raw['id'] + '.jpg', 'source': {'version': raw['version']}}


def job(connected, ids):
    p, manager = connected
    moment, elapsed, adapter = [100], [0], Adapter()
    selection = PickerSelection(manager.service, lambda *args: adapter,
        clock=lambda: moment[0], monotonic=lambda: elapsed[0])
    pending, _ = manager.pending(p, 'fixture-connection', 'oauth', {'picked_file_ids': ids, 'native_picker': True})
    pending = manager.service.read(p, 'intake_oauth', pending['id'])
    pending['state'] = 'authorized'
    pending = manager.service.save(p, 'intake_oauth', pending)
    retained = selection.begin(p, pending, ids, pending['id'])
    return p, manager, moment, elapsed, adapter, selection, retained


def test_failed_authorization_exposes_its_durable_error_without_selection_progress():
    error = dict(code='account_mismatch', message='Reconnect the same account.', action='connect', retryable=False)
    assert selection_reply(dict(state='failed', error=error)) == dict(state='failed', items=[], failures=[], error=error)


def test_500_ids_are_retained_then_checked_across_bounded_polls_without_presubmit_work(connected):
    ids = [f'photo-{index}' for index in range(500)]
    p, manager, _, _, adapter, selection, retained = job(connected, ids)
    assert retained['selection_ids'] == ids and adapter.calls == []
    assert selection_reply(retained)['progress'] == {'processed': 0, 'total': 500}
    cursor = 0
    while retained['state'] != 'selected':
        retained = selection.advance(p, retained['id'])
        assert 0 < retained['selection_cursor'] - cursor <= 50
        cursor = retained['selection_cursor']
    assert adapter.calls == ids and len(retained['items']) == 500 and not retained['failures']
    assert set(selection_reply(retained)) == {'state', 'items', 'failures'}
    selection.advance(p, retained['id'])
    assert adapter.calls == ids
    assert manager.service.list(p, 'intake_draft')['items'] == []
    assert manager.service.repo.list(p.scope) == []


def test_time_budget_stops_after_each_saved_id_and_deduplicates_before_processing(connected):
    p, _, _, elapsed, adapter, selection, retained = job(connected, ['one', 'denied', 'one', 'three'])
    adapter.before = lambda id: elapsed.__setitem__(0, elapsed[0] + 2)
    retained = selection.advance(p, retained['id'])
    assert retained['selection_ids'] == ['one', 'denied', 'three']
    assert retained['selection_cursor'] == 2 and adapter.calls == ['one', 'denied']
    assert retained['failures'][0]['id'] == 'denied'
    retained = selection.advance(p, retained['id'])
    assert retained['state'] == 'selected' and [row['id'] for row in retained['items']] == ['one', 'three']


def test_concurrent_poll_observes_lease_without_duplicate_metadata_scan(connected):
    p, _, _, _, adapter, selection, retained = job(connected, ['one', 'two'])
    competing = []
    adapter.before = lambda id: competing.append(selection.advance(p, retained['id'])['selection_cursor'])
    result = selection.advance(p, retained['id'])
    assert result['state'] == 'selected'
    assert adapter.calls == ['one', 'two'] and competing == [0, 1]


def test_lost_checkpoint_reply_resumes_after_restart_without_rechecking_committed_ids(connected, monkeypatch):
    p, manager, moment, elapsed, adapter, selection, retained = job(connected, ['one', 'two', 'three'])
    save, lost = manager.service.save, [False]
    def uncertain(p, kind, doc):
        result = save(p, kind, doc)
        if doc.get('selection_cursor') == 1 and not lost[0]:
            lost[0] = True
            raise RuntimeError('lost checkpoint reply')
        return result
    monkeypatch.setattr(manager.service, 'save', uncertain)
    with pytest.raises(RuntimeError): selection.advance(p, retained['id'])
    restarted = PickerSelection(manager.service, lambda *args: adapter,
        clock=lambda: moment[0], monotonic=lambda: elapsed[0])
    assert restarted.advance(p, retained['id'])['selection_cursor'] == 1
    assert adapter.calls == ['one']
    moment[0] += 61
    result = restarted.advance(p, retained['id'])
    assert result['state'] == 'selected' and adapter.calls == ['one', 'two', 'three']


def test_expired_old_lease_cannot_checkpoint_or_overwrite_a_new_owners_result(connected):
    p, _, moment, _, adapter, selection, retained = job(connected, ['one', 'two'])
    stolen = [False]
    def takeover(id):
        if not stolen[0]:
            stolen[0] = True
            moment[0] += 61
            assert selection.advance(p, retained['id'])['state'] == 'selected'
    adapter.before = takeover
    result = selection.advance(p, retained['id'])
    assert result['state'] == 'selected' and [row['id'] for row in result['items']] == ['one', 'two']
    assert result['selection_cursor'] == 2


@pytest.mark.parametrize('failure', ['transport', 'credential'])
def test_transient_or_global_failure_keeps_ids_cursor_and_retryable_progress(connected, failure):
    p, _, moment, _, adapter, selection, retained = job(connected, ['one', 'two'])
    failed = [False]
    def unavailable(id):
        if not failed[0]:
            failed[0] = True
            if failure == 'transport': raise Timeout('private provider output')
            raise ImportProblem('authorization_expired', 'Reconnect this account.', 'connect', False)
    adapter.before = unavailable
    result = selection.advance(p, retained['id'])
    assert result['selection_cursor'] == 0 and result['selection_ids'] == ['one', 'two'] and not result['failures']
    assert 'private provider output' not in str(selection_reply(result))
    assert selection_reply(result)['error']['action'] == ('retry' if failure == 'transport' else 'connect')
    selection.advance(p, retained['id'])
    assert adapter.calls == ['one']
    moment[0] += 3
    assert selection.advance(p, retained['id'])['state'] == 'selected'


def web_picker(connected):
    p, manager = connected
    manager.config['google_drive'].update(picker_api_key='synthetic-picker-key', picker_app_id='123')  # pragma: allowlist secret -- credential-free fixture
    connection = manager.connect(p, 'google_drive', 'files', 'a' * 64, 'https://app.example')
    state = parse_qs(urlsplit(connection['authorization_url']).query)['state'][0]
    reads = []
    def metadata(method, url, **kwargs):
        reads.append(url.rsplit('/', 1)[1])
        assert kwargs['timeout'] == 5
        return Response({'id': reads[-1], 'name': reads[-1] + '.png', 'mimeType': 'image/png', 'version': '7'})
    manager.http = SimpleNamespace(post=lambda *a, **kw: Response({'access_token': 'access', 'refresh_token': 'refresh', 'scope': GOOGLE_FILE}),
        get=lambda *a, **kw: Response({'user': {'permissionId': 'provider-account'}}), request=metadata)
    manager.complete(p, state, 'code', 'a' * 64)
    manager.service.sources.providers['google_drive'] = CloudSource(manager, 'google_drive')
    def client():
        app = FastAPI()
        install_source_routes(app, '/v1/organizations/{organization_id}', manager.service, manager,
            identity=lambda: p.user_id, principal=lambda *a, **kw: p, origins=('https://app.example',))
        return TestClient(app)
    browser = client()
    root = f'/v1/organizations/{p.scope.organization_id}/collections/{p.scope.collection_id}/intake'
    started = browser.post(root + f"/connections/{connection['id']}/picker").json()
    state = parse_qs(urlsplit(started['url']).fragment)['state'][0]
    bootstrap = browser.post('/v1/intake/picker/bootstrap', json={'state': state}).json()
    return p, manager, reads, browser, client, root + f"/connections/{connection['id']}/picker/{started['id']}", bootstrap['state']


def test_web_retains_parent_ids_before_child_consumption_and_recovers_lost_reply(connected, monkeypatch):
    p, manager, reads, browser, restart, status, state = web_picker(connected)
    save = manager.service.save
    def crash(p, kind, doc):
        if doc.get('purpose') == 'picker_selection' and doc['state'] == 'consumed':
            raise RuntimeError('lost child acknowledgement')
        return save(p, kind, doc)
    monkeypatch.setattr(manager.service, 'save', crash)
    with pytest.raises(RuntimeError):
        browser.post('/v1/intake/picker/selection', json={'state': state, 'ids': ['one', 'two', 'one']})
    assert reads == []
    parent = manager.service.read(p, 'intake_oauth', status.rsplit('/', 1)[1])
    assert parent['selection_ids'] == ['one', 'two'] and parent['selection_cursor'] == 0
    result = restart().get(status).json()
    assert result['state'] == 'selected' and reads == ['one', 'two']
    assert restart().get(status).json() == result and reads == ['one', 'two']
    assert manager.service.list(p, 'intake_draft')['items'] == [] and manager.service.repo.list(p.scope) == []


def test_invalid_web_ids_are_rejected_before_parent_state_or_provider_work(connected):
    p, manager, reads, browser, _, status, state = web_picker(connected)
    for ids in [['one', 'bad/path'], ['one,one'], ['one'] * 501]:
        if len(ids) > 500:
            assert browser.post('/v1/intake/picker/selection', json={'state': state, 'ids': ids}).status_code == 422
        else:
            with pytest.raises(ValueError): browser.post('/v1/intake/picker/selection', json={'state': state, 'ids': ids})
    assert reads == []
    assert manager.service.read(p, 'intake_oauth', status.rsplit('/', 1)[1])['state'] == 'picking'


def worker_job(connected, ids):
    setup = job(connected, ids)
    p, manager, moment, _, _, selection, retained = setup
    service = manager.service
    service.selection, service.clock = selection, lambda: moment[0]
    service.dispatch_intake = lambda p: {'status': 'requested'}
    selection.schedule(p, retained)
    return setup


@pytest.mark.parametrize('count', [10, 100, 500])
def test_worker_finishes_without_ui_polls_and_preserves_per_file_checkpoints(connected, count):
    import time
    ids = [f'photo-{index}' for index in range(count)]
    p, manager, moment, elapsed, adapter, selection, retained = worker_job(connected, ids)
    def metadata_time(id):
        moment[0] += .02
        elapsed[0] += .02
    adapter.before = metadata_time
    started = time.perf_counter()
    IntakeWorker(manager.service).drain(p, deadline=moment[0] + 120)
    wall = time.perf_counter() - started
    result = manager.service.read(p, 'intake_oauth', retained['id'])
    assert result['state'] == 'selected' and len(result['items']) == count
    assert adapter.calls == ids and result['selection_cursor'] == count
    job_doc = manager.service.repo.document(p.scope, 'intake_job', ident(retained['id'], 'selection'))
    assert job_doc['state'] == 'done'
    assert manager.service.list(p, 'intake_draft')['items'] == [] and manager.service.repo.list(p.scope) == []
    print(f'controlled picker count={count} metadata_calls={count} ui_polls=0 provider_time={elapsed[0]:.2f}s wall={wall:.3f}s')


def test_configured_status_never_performs_metadata_and_recovers_missing_wakeup(connected):
    p, manager, reads, browser, _, status, state = web_picker(connected)
    wakes = []
    manager.service.dispatch_intake = lambda p: wakes.append(p.user_id) or {'status': 'requested'}
    response = browser.post('/v1/intake/picker/selection', json={'state': state, 'ids': ['one', 'two']})
    assert response.status_code == 200 and reads == [] and len(wakes) == 1
    for _ in range(3):
        result = browser.get(status).json()
        assert result['state'] == 'selecting' and result['progress']['processed'] == 0
    assert reads == [] and len(wakes) == 1
    IntakeWorker(manager.service).drain(p)
    assert browser.get(status).json()['state'] == 'selected' and reads == ['one', 'two']


def test_worker_honors_provider_backoff_without_poll_driven_retry(connected):
    p, manager, moment, _, adapter, _, retained = worker_job(connected, ['one'])
    failed = [False]
    def rate_limit(id):
        if not failed[0]:
            failed[0] = True
            exc = ImportProblem('rate_limited', 'Retry later.')
            exc.intake_problem['retry_after'] = 30
            raise exc
    adapter.before = rate_limit
    worker = IntakeWorker(manager.service)
    worker.drain(p)
    job_doc = manager.service.repo.document(p.scope, 'intake_job', ident(retained['id'], 'selection'))
    assert job_doc['next_attempt'] == moment[0] + 30 and adapter.calls == ['one']
    worker.drain(p)
    assert adapter.calls == ['one']
    moment[0] += 30
    worker.drain(p)
    assert manager.service.read(p, 'intake_oauth', retained['id'])['state'] == 'selected'


def test_worker_deadline_leaves_exact_checkpoint_for_a_later_execution(connected):
    p, manager, moment, elapsed, adapter, _, retained = worker_job(connected, [str(i) for i in range(10)])
    def slow(id):
        moment[0] += 2
        elapsed[0] += 2
    adapter.before = slow
    worker = IntakeWorker(manager.service)
    worker.drain(p, deadline=moment[0] + 5)
    result = manager.service.read(p, 'intake_oauth', retained['id'])
    assert result['selection_cursor'] == 3 and result['state'] == 'selecting'
    assert len(adapter.calls) == 3
    moment[0] += 1
    worker.drain(p, deadline=moment[0] + 120)
    assert manager.service.read(p, 'intake_oauth', retained['id'])['state'] == 'selected'
    assert adapter.calls == [str(i) for i in range(10)]


def test_slow_token_work_cannot_checkpoint_after_selection_lease_expiry(connected, monkeypatch):
    p, manager, reads, browser, _, status, state = web_picker(connected)
    service, moment = manager.service, [100]
    service.clock = manager.clock = lambda: moment[0]
    service.selection.clock = lambda: moment[0]
    service.dispatch_intake = lambda p: {'status': 'requested'}
    assert browser.post('/v1/intake/picker/selection', json={'state': state, 'ids': ['one']}).status_code == 200
    token, slow = manager.token, [True]
    def stalled(p, id):
        value = token(p, id)
        if slow[0]:
            slow[0] = False
            moment[0] += 61
        return value
    monkeypatch.setattr(manager, 'token', stalled)
    worker = IntakeWorker(service)
    worker.drain(p, deadline=moment[0] + 120)
    result = service.read(p, 'intake_oauth', status.rsplit('/', 1)[1])
    assert result['selection_cursor'] == 0 and not result['items']
    moment[0] += 1
    worker.drain(p, deadline=moment[0] + 120)
    result = service.read(p, 'intake_oauth', result['id'])
    assert result['state'] == 'selected' and len(result['items']) == 1
    assert reads == ['one', 'one']  # Read-only recheck; no stale result was published.


def test_worker_restart_keeps_checkpoint_after_process_death(connected, monkeypatch):
    p, manager, moment, _, adapter, _, retained = worker_job(connected, ['one', 'two'])
    save = manager.service.save
    def die(p, kind, doc):
        result = save(p, kind, doc)
        if kind == 'intake_oauth' and doc.get('selection_cursor') == 1:
            raise SystemExit('worker stopped')
        return result
    monkeypatch.setattr(manager.service, 'save', die)
    with pytest.raises(SystemExit):
        IntakeWorker(manager.service).drain(p)
    monkeypatch.setattr(manager.service, 'save', save)
    IntakeWorker(manager.service).drain(p)
    assert adapter.calls == ['one']
    moment[0] += 181
    IntakeWorker(manager.service).drain(p)
    assert adapter.calls == ['one', 'two']
    assert manager.service.read(p, 'intake_oauth', retained['id'])['state'] == 'selected'


def test_exhausted_worker_is_visible_and_only_explicit_retry_resets_after_backoff(connected):
    p, manager, reads, browser, _, status, state = web_picker(connected)
    service, moment = manager.service, [100]
    service.clock = manager.clock = lambda: moment[0]
    service.selection.clock = lambda: moment[0]
    service.dispatch_intake = lambda p: {'status': 'requested'}
    assert browser.post('/v1/intake/picker/selection', json={'state': state, 'ids': ['one']}).status_code == 200
    request, calls = manager.http.request, []
    def unavailable(*args, **kwargs):
        calls.append(True)
        return Response(status=503)
    manager.http.request = unavailable
    worker, id = IntakeWorker(service), status.rsplit('/', 1)[1]
    for attempt in range(4):
        worker.drain(p)
        job_doc = service.repo.document(p.scope, 'intake_job', ident(id, 'selection'))
        assert job_doc['attempts'] == attempt + 1
        if attempt < 3:
            moment[0] = job_doc['next_attempt']
    assert job_doc['state'] == 'needs_attention'
    for _ in range(2):
        reply = browser.get(status).json()
        assert reply['state'] == 'selecting' and reply['error']['code'] == 'selection_retry_exhausted'
        assert reply['progress'] == {'processed': 0, 'total': 1}
    browser.post(status + '/retry')
    assert service.repo.document(p.scope, 'intake_job', job_doc['id']) == job_doc
    moment[0] = job_doc['next_attempt']
    browser.get(status)
    worker.drain(p)
    assert len(calls) == 4
    assert browser.post(status + '/retry').status_code == 200
    queued = service.repo.document(p.scope, 'intake_job', job_doc['id'])
    assert queued['attempts'] == 0 and queued['state'] == 'waiting'
    manager.http.request = request
    worker.drain(p)
    assert browser.get(status).json()['state'] == 'selected' and reads == ['one']


def test_retry_keeps_connection_and_current_permission_binding(connected, monkeypatch):
    p, manager, reads, browser, _, status, state = web_picker(connected)
    service = manager.service
    service.dispatch_intake = lambda p: {'status': 'requested'}
    assert browser.post('/v1/intake/picker/selection', json={'state': state, 'ids': ['one']}).status_code == 200
    wrong = status.split('/connections/')[0] + '/connections/wrong/picker/' + status.rsplit('/', 1)[1]
    with pytest.raises(ValueError, match='Invalid picker'):
        browser.post(wrong + '/retry')
    def revoked(*args):
        raise PermissionError('Membership was removed')
    monkeypatch.setattr(service, 'classify', revoked)
    with pytest.raises(PermissionError):
        browser.post(status + '/retry')
    assert reads == []


def test_retry_cannot_replace_an_active_worker_claim(connected):
    p, manager, moment, _, adapter, selection, retained = worker_job(connected, ['one'])
    service = manager.service
    job_doc = service.repo.document(p.scope, 'intake_job', ident(retained['id'], 'selection'))
    job_doc.update(lease_until=moment[0] + 180, lease_token='current-worker', attempts=2)
    expected = service.save(p, 'intake_job', job_doc)
    selection.retry(p, retained)
    assert service.repo.document(p.scope, 'intake_job', job_doc['id']) == expected
    assert not adapter.calls
