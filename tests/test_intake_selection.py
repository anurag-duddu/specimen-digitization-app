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
        assert 0 < retained['selection_cursor'] - cursor <= 5
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
