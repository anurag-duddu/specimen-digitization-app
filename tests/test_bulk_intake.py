"""Real API/store contracts; no provider or device acceptance is claimed."""
import hashlib
from fastapi.testclient import TestClient
import pytest

from specimen_digitization.application.api import local_app, SYNTHETIC_COLLECTION
from specimen_digitization.application.domain import Scope, Principal
from specimen_digitization.application.intake_models import DraftInput, DraftItemInput, SubmitInput
from specimen_digitization.application.storage import Missing, Conflict
from test_application import HEADERS, PREFIX, TOKEN, image_bytes

ROOT = PREFIX + '/collections/' + SYNTHETIC_COLLECTION + '/intake'


def draft(client, id='draft'):
    response = client.post(ROOT + '/drafts', headers=HEADERS, json={'client_id': id})
    assert response.status_code == 200, response.text
    return response.json()


def add(client, batch, id='photo', *, sensitive=False):
    data = image_bytes()
    response = client.post(ROOT + f"/drafts/{batch['id']}/items", headers=HEADERS, json={
        'client_id': id, 'filename': id + '.png', 'media_type': 'image/png',
        'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
        'photo_sensitive': sensitive, 'source': {'provider': 'files'},
    })
    assert response.status_code == 200, response.text
    return response.json(), data


def stage(client, item, data):
    response = client.put(ROOT + f"/items/{item['id']}/content", headers=HEADERS, content=data)
    assert response.status_code == 200, response.text
    response = client.post(ROOT + f"/items/{item['id']}/save", headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def submit(client, batch, items):
    current = client.get(ROOT + f"/drafts/{batch['id']}", headers=HEADERS).json()
    return client.post(ROOT + f"/drafts/{batch['id']}/submit", headers=HEADERS,
        json={'expected_revision': current['revision'], 'item_ids': [i['id'] for i in items]})


def test_saved_draft_survives_restart_without_creating_specimens(tmp_path):
    app = local_app(tmp_path, TOKEN)
    client = TestClient(app)
    batch = draft(client)
    item, data = add(client, batch)
    saved = stage(client, item, data)
    assert saved['state'] == 'ready'
    assert 'asset' not in saved and 'chunks' not in saved
    assert app.state.workflow.repository.list(Scope(organization_id=PREFIX.split('/')[-1], collection_id=SYNTHETIC_COLLECTION)) == []
    client.close()
    client = TestClient(local_app(tmp_path, TOKEN))
    restored = client.get(ROOT + f"/drafts/{batch['id']}/items", headers=HEADERS).json()
    assert restored['items'][0]['state'] == 'ready'
    assert client.get(ROOT + f"/items/{item['id']}/preview", headers=HEADERS).status_code == 200
    accepted = submit(client, batch, [item])
    assert accepted.status_code == 202, accepted.text
    state = client.get(ROOT + f"/submissions/{accepted.json()['id']}", headers=HEADERS).json()
    assert state['counts'] == {'sent': 1}


def test_submit_replay_and_upload_ack_replay_create_one_specimen(tmp_path):
    app = local_app(tmp_path, TOKEN)
    client = TestClient(app)
    batch = draft(client)
    item, data = add(client, batch)
    saved = stage(client, item, data)
    replay = client.put(ROOT + f"/items/{item['id']}/content", headers=HEADERS, content=data)
    assert replay.status_code == 200 and replay.json()['revision'] == saved['revision']
    first = submit(client, batch, [item])
    second = submit(client, batch, [item])
    assert first.status_code == second.status_code == 202
    assert first.json()['id'] == second.json()['id']
    assert len(app.state.workflow.repository.list(Scope(organization_id=PREFIX.split('/')[-1], collection_id=SYNTHETIC_COLLECTION))) == 1


def test_partial_submit_preserves_remaining_draft_and_cancellation_is_not_rollback(tmp_path):
    app = local_app(tmp_path, TOKEN)
    client = TestClient(app)
    batch = draft(client)
    ready, data = add(client, batch)
    waiting, _ = add(client, batch, 'waiting')
    stage(client, ready, data)
    result = submit(client, batch, [ready])
    assert result.status_code == 202, result.text
    remaining = client.get(ROOT + f"/drafts/{result.json()['remaining_draft_id']}/items", headers=HEADERS).json()
    assert [i['id'] for i in remaining['items']] == [waiting['id']]
    cancelled = client.post(ROOT + f"/submissions/{result.json()['id']}/cancel", headers=HEADERS)
    assert cancelled.status_code == 200
    assert cancelled.json()['counts'] == {'sent': 1}


def test_private_owner_and_stale_edit_are_rejected(tmp_path):
    app = local_app(tmp_path, TOKEN)
    client = TestClient(app)
    batch = draft(client)
    item, _ = add(client, batch)
    stale = client.post(ROOT + f"/drafts/{batch['id']}/edit", headers=HEADERS,
        json={'expected_revision': batch['revision'], 'item_ids': [item['id']], 'action': 'remove'})
    assert stale.status_code == 409
    p = Principal(user_id='someone-else', scope=Scope(organization_id=PREFIX.split('/')[-1], collection_id=SYNTHETIC_COLLECTION), role='reviewer')
    with pytest.raises(Missing):
        app.state.intake.draft(p, batch['id'])
    assert app.state.intake.list(p, 'intake_draft')['items'] == []


def test_frozen_manifest_rejects_edits_and_can_wait_for_bytes(tmp_path):
    app = local_app(tmp_path, TOKEN)
    client = TestClient(app)
    batch = draft(client)
    item, data = add(client, batch)
    result = submit(client, batch, [item])
    assert result.status_code == 202
    current = client.get(ROOT + f"/drafts/{batch['id']}", headers=HEADERS).json()
    edit = client.post(ROOT + f"/drafts/{batch['id']}/edit", headers=HEADERS,
        json={'expected_revision': current['revision'], 'item_ids': [item['id']], 'action': 'remove'})
    assert edit.status_code == 409
    stage(client, item, data)
    state = client.get(ROOT + f"/submissions/{result.json()['id']}", headers=HEADERS).json()
    assert state['counts'] == {'sent': 1}


def test_500_photo_limit_and_paging_do_not_truncate(tmp_path):
    app = local_app(tmp_path, TOKEN)
    service = app.state.intake
    p = Principal(user_id='synthetic-reviewer', scope=Scope(organization_id=PREFIX.split('/')[-1], collection_id=SYNTHETIC_COLLECTION), role='reviewer')
    batch = service.create_draft(p, DraftInput(client_id='large'))
    payload = dict(filename='photo.png', media_type='image/png', size_bytes=100,
                   sha256='a' * 64, source={'provider': 'files'})
    for n in range(500):
        service.add_item(p, batch['id'], DraftItemInput(client_id=str(n), **payload))
    with pytest.raises(ValueError, match='500'):
        service.add_item(p, batch['id'], DraftItemInput(client_id='501', **payload))
    client = TestClient(app)
    cursor, count = 0, 0
    while cursor is not None:
        page = client.get(ROOT + f"/drafts/{batch['id']}/items", headers=HEADERS, params={'after': cursor, 'limit': 50}).json()
        count += len(page['items'])
        cursor = page['next_cursor']
    assert count == 500


def test_removing_and_restoring_does_not_delete_source_or_bytes(tmp_path):
    client = TestClient(local_app(tmp_path, TOKEN))
    batch = draft(client)
    item, data = add(client, batch)
    stage(client, item, data)
    for action in ('remove', 'restore'):
        current = client.get(ROOT + f"/drafts/{batch['id']}", headers=HEADERS).json()
        response = client.post(ROOT + f"/drafts/{batch['id']}/edit", headers=HEADERS,
            json={'expected_revision': current['revision'], 'item_ids': [item['id']], 'action': action})
        assert response.status_code == 200
    assert client.get(ROOT + f"/items/{item['id']}/preview", headers=HEADERS).status_code == 200


def test_committed_submission_outbox_recovers_after_materialization_crash(tmp_path, monkeypatch):
    from specimen_digitization.application.intake_worker import IntakeWorker
    app = local_app(tmp_path, TOKEN)
    client = TestClient(app)
    batch = draft(client)
    item, data = add(client, batch)
    stage(client, item, data)
    service = app.state.intake
    scope = Scope(organization_id=PREFIX.split('/')[-1], collection_id=SYNTHETIC_COLLECTION)
    p = Principal(user_id='synthetic-reviewer', scope=scope, role='reviewer')
    original = service._materialize_submission
    monkeypatch.setattr(service, '_materialize_submission', lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('crash')))
    current = service.draft(p, batch['id'])
    with pytest.raises(RuntimeError):
        service.submit(p, batch['id'], SubmitInput(expected_revision=current['revision'], item_ids=[item['id']]))
    assert service.repo.list(scope) == []
    monkeypatch.setattr(service, '_materialize_submission', original)
    # Reopening the queue must recover without a manually running worker.
    wakes = []
    service.dispatch_intake = lambda: wakes.append(True) or {'status': 'requested'}
    listed = service.list(p, 'intake_submission')
    assert len(listed['items']) == 1 and wakes
    IntakeWorker(service).drain(p)
    submitted = service.draft(p, batch['id'])
    assert service.submission(p, submitted['submission_id'])['counts'] == {'sent': 1}


def test_carry_forward_upload_wakes_its_new_submission(tmp_path):
    app = local_app(tmp_path, TOKEN)
    client = TestClient(app)
    batch = draft(client)
    first, data = add(client, batch)
    other, _ = add(client, batch, 'later')
    stage(client, first, data)
    initial = submit(client, batch, [first]).json()
    remainder = client.get(ROOT + '/drafts/' + initial['remaining_draft_id'], headers=HEADERS).json()
    submitted = submit(client, remainder, [other])
    assert submitted.status_code == 202
    stage(client, other, data)
    state = client.get(ROOT + '/submissions/' + submitted.json()['id'], headers=HEADERS).json()
    assert state['counts'] == {'duplicate': 1}


def test_failed_launch_is_visible_and_batch_retry_is_idempotent(tmp_path):
    from specimen_digitization.application.lane_dispatch import DispatchOutcome
    app = local_app(tmp_path, TOKEN)
    client = TestClient(app)
    service = app.state.intake
    service.dispatch_intake = lambda: DispatchOutcome(status='failed')
    batch = draft(client)
    item, _ = add(client, batch)
    result = submit(client, batch, [item])
    assert result.status_code == 202
    # The local drain may clear a launch failure after taking ownership, but
    # enqueue itself must durably expose a failed production start.
    scope = Scope(organization_id=PREFIX.split('/')[-1], collection_id=SYNTHETIC_COLLECTION)
    p = Principal(user_id='synthetic-reviewer', scope=scope, role='reviewer')
    job = service.enqueue(p, result.json()['id'], 'submit')
    assert job['error']['code'] == 'worker_unavailable'
    assert service.submission(p, result.json()['id'])['worker_error']['retryable']


def test_stage_reconciles_concurrent_awaiting_content_commit(tmp_path, monkeypatch):
    from specimen_digitization.application.bulk_intake import ident
    app = local_app(tmp_path, TOKEN)
    client = TestClient(app)
    batch = draft(client)
    item, data = add(client, batch)
    submitted = submit(client, batch, [item]).json()
    service = app.state.intake
    p = Principal(user_id='synthetic-reviewer', scope=Scope(organization_id=PREFIX.split('/')[-1], collection_id=SYNTHETIC_COLLECTION), role='reviewer')
    service.content(p, item['id'], 0, data)
    original = service.save
    collided = False
    def concurrent_save(actor, kind, doc):
        nonlocal collided
        if kind == 'intake_job' and doc['target'] == submitted['id'] and not collided:
            collided = True
            current = service.repo.document(p.scope, kind, doc['id'])
            current.update(state='awaiting_content', lease_until=0)
            original(actor, kind, current)
        return original(actor, kind, doc)
    monkeypatch.setattr(service, 'save', concurrent_save)
    service.stage(p, item['id'])
    assert collided
    assert service.repo.document(p.scope, 'intake_job', ident(submitted['id'], 'submit'))['state'] == 'waiting'
    # A saved-stage replay must also repair a lost wake-up.
    current = service.repo.document(p.scope, 'intake_job', ident(submitted['id'], 'submit'))
    current['state'] = 'awaiting_content'
    original(p, 'intake_job', current)
    service.stage(p, item['id'])
    assert service.repo.document(p.scope, 'intake_job', current['id'])['state'] == 'waiting'


def test_replacement_conflict_replay_cannot_include_two_edits(tmp_path, monkeypatch):
    app = local_app(tmp_path, TOKEN)
    client = TestClient(app)
    batch = draft(client)
    item, _ = add(client, batch)
    service = app.state.intake
    p = Principal(user_id='synthetic-reviewer', scope=Scope(organization_id=PREFIX.split('/')[-1], collection_id=SYNTHETIC_COLLECTION), role='reviewer')
    body = DraftItemInput(client_id='edit-b', filename='edit.png', media_type='image/png',
        size_bytes=100, sha256='b' * 64, source={'provider': 'files'}, replaces_id=item['id'])
    original = service.save
    def fail_manifest(actor, kind, doc):
        if kind == 'intake_draft': raise Conflict('Concurrent edit')
        return original(actor, kind, doc)
    monkeypatch.setattr(service, 'save', fail_manifest)
    with pytest.raises(Conflict): service.add_item(p, batch['id'], body)
    monkeypatch.setattr(service, 'save', original)
    service.add_item(p, batch['id'], body.model_copy(update={'client_id': 'edit-c'}))
    with pytest.raises(Conflict): service.add_item(p, batch['id'], body)
    assert sum(not e['removed'] for e in service.draft(p, batch['id'])['entries']) == 1


def test_tightened_source_policy_blocks_submit_and_handoff_including_edits(tmp_path, monkeypatch):
    from types import SimpleNamespace
    app = local_app(tmp_path, TOKEN)
    client = TestClient(app)
    batch = draft(client)
    original, data = add(client, batch)
    service = app.state.intake
    p = Principal(user_id='synthetic-reviewer', scope=Scope(organization_id=PREFIX.split('/')[-1], collection_id=SYNTHETIC_COLLECTION), role='reviewer')
    # A registered original's provenance survives a local edit.
    original_doc = service.item(p, original['id'])
    original_doc['source'] = {'provider': 'storage', 'source_id': 'protected', 'object_id': 'photo.png'}
    service.save(p, 'intake_item', original_doc)
    policy = {'sensitive': False}
    service.sources = SimpleNamespace(required_sensitive=lambda actor, source: source.provider == 'storage' and policy['sensitive'])
    edited = service.add_item(p, batch['id'], DraftItemInput(client_id='edit', filename='edited.png', media_type='image/png',
        size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), source={'provider': 'files'}, replaces_id=original['id']))
    service.content(p, edited['id'], 0, data)
    service.stage(p, edited['id'])
    policy['sensitive'] = True
    with pytest.raises(Conflict, match='policy changed'):
        service.submit(p, batch['id'], SubmitInput(expected_revision=service.draft(p, batch['id'])['revision'], item_ids=[edited['id']]))
    policy['sensitive'] = False
    result = service.submit(p, batch['id'], SubmitInput(expected_revision=service.draft(p, batch['id'])['revision'], item_ids=[edited['id']]))
    policy['sensitive'] = True
    assert service.process_submission(p, result['id'])['counts'] == {'needs_attention': 1}
    assert service.repo.list(p.scope) == []
    service.cancel(p, result['id'])
    assert service.process_submission(p, result['id'])['counts'] == {'cancelled': 1}
