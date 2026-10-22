"""Controlled SQLite/API admission contracts; no provider or live-user evidence."""
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from specimen_digitization.application.api import local_app, SYNTHETIC_ORG, SYNTHETIC_COLLECTION
from specimen_digitization.application.bulk_intake import ident
from specimen_digitization.application.domain import Principal, Scope
from specimen_digitization.application.intake_models import DraftInput, DraftItemInput
from specimen_digitization.application.intake_routes import install_intake_routes
from specimen_digitization.application.storage import Conflict, Missing
from test_application import TOKEN


def photo(index):
    return DraftItemInput(client_id=f'photo-{index}', filename=f'{index}.jpg', media_type='image/jpeg',
        source={'provider': 'url', 'url': f'https://photos.example/{index}.jpg'})


@pytest.fixture
def admission(tmp_path):
    service = local_app(tmp_path, TOKEN).state.intake
    p = Principal(user_id='synthetic-reviewer',
        scope=Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION), role='reviewer')
    app = FastAPI()
    install_intake_routes(app, '/v1/organizations/{organization_id}', service,
        identity=lambda: p.user_id, principal=lambda *args, **kwargs: p)
    draft = service.create_draft(p, DraftInput(client_id='bulk'))
    root = f'/v1/organizations/{SYNTHETIC_ORG}/collections/{SYNTHETIC_COLLECTION}/intake/drafts/{draft["id"]}/items'
    return service, p, draft, TestClient(app), root


@pytest.mark.parametrize('count', [10, 100, 500])
def test_chunked_admission_request_bounds_and_no_scientific_work(admission, monkeypatch, count):
    service, p, draft, client, root = admission
    writes, wakeups = [], []
    save = service.save
    def track(p, kind, doc):
        writes.append(kind)
        return save(p, kind, doc)
    monkeypatch.setattr(service, 'save', track)
    service.dispatch_intake = lambda p: wakeups.append(p.user_id) or {'status': 'requested'}
    started, requests = time.perf_counter(), 0
    for start in range(0, count, 50):
        bodies = [photo(index).model_dump() for index in range(start, min(count, start + 50))]
        response = client.post(root + '/bulk', json={'items': bodies})
        assert response.status_code == 200, response.text
        result = response.json()
        assert not result['pending_client_ids']
        assert [item['client_id'] for item in result['items']] == [body['client_id'] for body in bodies]
        assert all('request_digest' not in item and 'asset' not in item for item in result['items'])
        requests += 1
    elapsed = time.perf_counter() - started
    assert requests == (count + 49) // 50
    assert writes.count('intake_draft') == requests
    assert len(service.draft(p, draft['id'])['entries']) == count
    assert len(set(entry['id'] for entry in service.draft(p, draft['id'])['entries'])) == count
    assert len(wakeups) == 1
    assert service.repo.list(p.scope) == []
    assert service.list(p, 'intake_submission')['items'] == []
    print(f'controlled admission count={count} posts={requests} draft_writes={requests} elapsed={elapsed:.3f}s')


def test_capability_explicitly_advertises_bulk_without_changing_legacy_admission(admission):
    service, p, draft, client, root = admission
    intake_root = root.split('/drafts/')[0]
    capabilities = client.get(intake_root + '/capabilities')
    assert capabilities.status_code == 200
    assert capabilities.json()['bulk_source_admission'] is True
    assert capabilities.json()['durable_picker_selection'] is True
    body = photo(1).model_dump()
    first = client.post(root, json=body)
    replay = client.post(root, json=body)
    assert first.status_code == replay.status_code == 200
    assert first.json()['id'] == replay.json()['id']
    assert len(service.draft(p, draft['id'])['entries']) == 1


@pytest.mark.parametrize('lost_kind', ['intake_item', 'intake_draft'])
def test_lost_write_reply_reconciles_exact_attachment_and_repairs_staging(admission, monkeypatch, lost_kind):
    service, p, draft, _, _ = admission
    bodies = [photo(index) for index in range(3)]
    save, lost = service.save, [False]
    def uncertain(p, kind, doc):
        result = save(p, kind, doc)
        if kind == lost_kind and not lost[0]:
            lost[0] = True
            raise TimeoutError('lost acknowledgement')
        return result
    monkeypatch.setattr(service, 'save', uncertain)
    with pytest.raises(TimeoutError):
        service.add_sources(p, draft['id'], bodies)
    monkeypatch.setattr(service, 'save', save)
    reconciled = service.reconcile_sources(p, draft['id'], bodies)
    if lost_kind == 'intake_item':
        assert not reconciled['items']
        assert reconciled['pending_client_ids'] == [body.client_id for body in bodies]
        with pytest.raises(Missing):
            service.repo.document(p.scope, 'intake_job', ident(ident(draft['id'], bodies[0].client_id), 'stage'))
    else:
        assert len(reconciled['items']) == 3 and not reconciled['pending_client_ids']
        assert all(service.repo.document(p.scope, 'intake_job', ident(item['id'], 'stage'))['state'] == 'waiting'
                   for item in reconciled['items'])
    result = service.add_sources(p, draft['id'], bodies)
    assert len(result['items']) == 3 and not result['pending_client_ids']
    assert len(service.draft(p, draft['id'])['entries']) == 3
    assert service.repo.list(p.scope) == []


def test_manifest_conflict_retains_unattached_items_without_overwriting_edit(admission, monkeypatch):
    service, p, draft, _, _ = admission
    body = photo(1)
    save, raced = service.save, [False]
    def concurrent(p, kind, doc):
        if kind == 'intake_draft' and not raced[0]:
            raced[0] = True
            other = service.draft(p, draft['id'])
            other['name'] = 'Concurrent name'
            save(p, kind, other)
        return save(p, kind, doc)
    monkeypatch.setattr(service, 'save', concurrent)
    with pytest.raises(Conflict):
        service.add_sources(p, draft['id'], [body])
    assert service.reconcile_sources(p, draft['id'], [body])['pending_client_ids'] == [body.client_id]
    service.add_sources(p, draft['id'], [body])
    current = service.draft(p, draft['id'])
    assert current['name'] == 'Concurrent name' and len(current['entries']) == 1


def test_499_plus_two_is_refused_before_new_records_or_manifest_changes(admission):
    service, p, draft, _, _ = admission
    for start in range(0, 499, 50):
        service.add_sources(p, draft['id'], [photo(index) for index in range(start, min(499, start + 50))])
    before = service.draft(p, draft['id'])
    with pytest.raises(ValueError, match='500'):
        service.add_sources(p, draft['id'], [photo(499), photo(500)])
    assert service.draft(p, draft['id']) == before
    with pytest.raises(Missing):
        service.read(p, 'intake_item', ident(draft['id'], photo(499).client_id))


def test_duplicates_and_changed_identity_are_refused_before_writes(admission):
    service, p, draft, client, root = admission
    body = photo(1)
    assert client.post(root + '/bulk', json={'items': [body.model_dump()] * 2}).status_code == 422
    assert not service.draft(p, draft['id'])['entries']
    first = service.add_sources(p, draft['id'], [body])
    replay = service.add_sources(p, draft['id'], [body])
    assert replay['draft_revision'] == first['draft_revision']
    assert replay['items'][0]['id'] == first['items'][0]['id']
    changed = body.model_copy(update={'source': body.source.model_copy(update={'version': 'changed'})})
    for method in (service.add_sources, service.reconcile_sources):
        with pytest.raises(Conflict, match='different content'):
            method(p, draft['id'], [photo(2), changed])
    with pytest.raises(Missing):
        service.read(p, 'intake_item', ident(draft['id'], photo(2).client_id))


def test_reconciliation_keeps_initial_request_identity_after_transfer_and_policy_normalization(admission, monkeypatch):
    service, p, draft, _, _ = admission
    monkeypatch.setattr(service.sources, 'required_sensitive', lambda *args: True)
    body = photo(1)
    result = service.add_sources(p, draft['id'], [body])
    item = result['items'][0]
    assert item['sensitive'] and item['policy_sensitive'] and item['photo_sensitive']
    item.update(state='ready', size_bytes=123, sha256='a' * 64)
    service.save(p, 'intake_item', item)
    assert service.reconcile_sources(p, draft['id'], [body])['items'][0]['size_bytes'] == 123
    other = p.model_copy(update={'user_id': 'different-owner'})
    with pytest.raises(Missing):
        service.reconcile_sources(other, draft['id'], [body])


def test_slow_validation_returns_exact_committed_prefix_and_pending_ids(admission, monkeypatch):
    service, p, draft, _, _ = admission
    elapsed = [0.0]
    service.monotonic = lambda: elapsed[0]
    validate = service.sources.validate
    def slow(p, source):
        elapsed[0] += 1.1
        validate(p, source)
    monkeypatch.setattr(service.sources, 'validate', slow)
    bodies = [photo(index) for index in range(10)]
    first = service.add_sources(p, draft['id'], bodies)
    assert len(first['items']) == 3
    assert first['pending_client_ids'] == [body.client_id for body in bodies[3:]]
    assert len(service.draft(p, draft['id'])['entries']) == 3
    assert len(service.reconcile_sources(p, draft['id'], bodies)['items']) == 3


def test_slow_preflight_does_not_exhaust_admission_budget_or_repeat_permission_reads(admission, monkeypatch):
    service, p, draft, _, _ = admission
    elapsed, permissions = [0.0], []
    service.monotonic = lambda: elapsed[0]
    classify, matches, validate = service.classify, service.source_matches, service.sources.validate
    def membership(actor, sensitive):
        elapsed[0] += 0.06
        permissions.append(sensitive)
        classify(actor, sensitive)
    def slow_preflight(*args):
        result = matches(*args)
        elapsed[0] += 4  # A slow repository reply is outside the admission budget.
        return result
    def slow_validation(*args):
        elapsed[0] += 1.1
        validate(*args)
    monkeypatch.setattr(service, 'classify', membership)
    monkeypatch.setattr(service, 'source_matches', slow_preflight)
    monkeypatch.setattr(service.sources, 'validate', slow_validation)
    bodies = [photo(index) for index in range(50)]
    first = service.add_sources(p, draft['id'], bodies)
    assert elapsed[0] > 7
    assert len(first['items']) == 3
    assert first['pending_client_ids'] == [body.client_id for body in bodies[3:]]
    assert permissions == [False, False]  # Draft and strongest input requirement.
    permissions.clear()
    second = service.add_sources(p, draft['id'], bodies)
    assert len(second['items']) == 6
    assert second['pending_client_ids'] == [body.client_id for body in bodies[6:]]
    assert permissions == [False, False, False]  # Plus one persisted-item page.
    assert len({item['id'] for item in second['items']}) == 6


def test_batch_permission_uses_strongest_input_before_any_item_write(admission, monkeypatch):
    service, p, draft, _, _ = admission
    permissions = []
    def nonsensitive_only(actor, sensitive):
        permissions.append(sensitive)
        if sensitive is not False:
            raise PermissionError('Sensitive access removed')
    monkeypatch.setattr(service, 'classify', nonsensitive_only)
    bodies = [photo(index) for index in range(50)]
    bodies[-1] = bodies[-1].model_copy(update={'photo_sensitive': True})
    with pytest.raises(PermissionError):
        service.add_sources(p, draft['id'], bodies)
    assert permissions == [False, True]
    assert service.repo.private_documents(p.scope, 'intake_item', p.user_id,
        [ident(draft['id'], body.client_id) for body in bodies]) == []
    assert not service.repo.document(p.scope, 'intake_draft', draft['id'])['entries']


def test_replay_checks_strongest_persisted_sensitivity_and_current_membership(admission, monkeypatch):
    service, p, draft, _, _ = admission
    bodies = [photo(index) for index in range(50)]
    result = service.add_sources(p, draft['id'], bodies)
    item = service.repo.document(p.scope, 'intake_item', result['items'][-1]['id'])
    item['sensitive'] = True
    service.save(p, 'intake_item', item)
    permissions = []
    def nonsensitive_only(actor, sensitive):
        permissions.append(sensitive)
        if sensitive is not False:
            raise PermissionError('Sensitive access removed')
    monkeypatch.setattr(service, 'classify', nonsensitive_only)
    with pytest.raises(PermissionError):
        service.reconcile_sources(p, draft['id'], bodies)
    assert permissions == [False, False, True]


def test_registered_policy_lookup_is_deduplicated_only_within_scoped_request(admission, monkeypatch):
    from specimen_digitization.application.source_registry import RegisteredSource, SourceRegistry
    service, p, draft, _, _ = admission
    ids = ['10000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000002']
    sources = [RegisteredSource(source_id=id, collection_id=p.scope.collection_id, bucket='fixture-photos',
        prefix=f'photos/{index}/', media_types=('image/jpeg',), sensitive=bool(index),
        registered_by='fixture-admin', registered_at='2026-10-21T00:00:00Z') for index, id in enumerate(ids)]
    registry = SourceRegistry(sources)
    service.sources.registry = registry
    calls, resolve = [], registry.get
    def tracked(id, collections):
        calls.append((id, tuple(collections)))
        return resolve(id, collections)
    monkeypatch.setattr(registry, 'get', tracked)
    bodies = [photo(index).model_copy(update={'source': photo(index).source.model_copy(update={
        'provider': 'storage', 'source_id': ids[index % 2], 'object_id': f'photos/{index % 2}/{index}.jpg',
        'version': '1', 'url': None})}) for index in range(50)]
    for _ in range(2):
        normalized = service.source_inputs(p, draft['id'], bodies)
        assert [body.photo_sensitive for _, body, _, _ in normalized] == [bool(index % 2) for index in range(50)]
    assert calls == [(id, (p.scope.collection_id,)) for _ in range(2) for id in ids]
    other = p.model_copy(update={'scope': p.scope.model_copy(update={
        'collection_id': '10000000-0000-4000-8000-000000000003'})})
    with pytest.raises(Missing):
        service.source_inputs(other, draft['id'], bodies)
    # Deduplicating policy never substitutes for an individual object's prefix guard.
    service.sources.storage = object()
    invalid = bodies[0].source.model_copy(update={'object_id': 'outside/photo.jpg'})
    with pytest.raises(ValueError, match='outside'):
        service.sources.validate(p, invalid)


def test_reconciliation_preserves_existing_job_backoff_and_lease(admission):
    service, p, draft, _, _ = admission
    body = photo(1)
    item = service.add_sources(p, draft['id'], [body])['items'][0]
    job = service.repo.document(p.scope, 'intake_job', ident(item['id'], 'stage'))
    job.update(next_attempt=999999999999, lease_until=999999999999, lease_token='existing', attempts=3,
        error={'code': 'rate_limited', 'retryable': True})
    expected = service.save(p, 'intake_job', job)
    service.reconcile_sources(p, draft['id'], [body])
    assert service.repo.document(p.scope, 'intake_job', job['id']) == expected
