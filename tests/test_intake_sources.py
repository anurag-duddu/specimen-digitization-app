"""Synthetic provider/security contracts; these are not live account acceptance."""
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
import pytest
from specimen_digitization.application.api import local_app, SYNTHETIC_ORG, SYNTHETIC_COLLECTION
from specimen_digitization.application.domain import Principal, Scope
from specimen_digitization.application.intake_connections import ConnectionManager, SecretManagerTokens, GOOGLE_FILE, GOOGLE_READ, DROPBOX_SCOPES
from specimen_digitization.application.intake_cloud_sources import CloudSource, check_response, shared_parts, shared_ref
from specimen_digitization.application.intake_sources import PublicImageReader, ImportProblem
from specimen_digitization.application.intake_models import SourceReference
from test_application import TOKEN, image_bytes


class Secrets:
    def __init__(self): self.values = {'client-secret': {'client_secret': 'fixture-secret'}}  # pragma: allowlist secret -- synthetic fixture
    def write(self, id, value):
        ref = id + ':' + str(len(self.values)); self.values[ref] = dict(value); return ref
    def read(self, ref): return dict(self.values[ref])


class Response:
    def __init__(self, data=None, status=200, headers=None, content=None):
        self.data, self.status_code, self.headers, self.content = data or {}, status, headers or {}, content
    def json(self): return self.data
    def iter_content(self, size): yield self.content
    def close(self): pass


@pytest.fixture
def connected(tmp_path):
    service = local_app(tmp_path, TOKEN).state.intake
    p = Principal(user_id='synthetic-reviewer', scope=Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION), role='reviewer')
    config = {name: {'client_id': 'fixture-client', 'client_secret_ref': 'client-secret', 'redirect_uri': 'https://api.example/v1/intake/oauth/callback'} for name in ('google_drive', 'dropbox')}
    manager = ConnectionManager(service, config, Secrets(), clock=lambda: 100)
    return p, manager


def test_oauth_scopes_nonce_session_and_one_use_are_separate(connected):
    p, manager = connected
    proof = 'a' * 64
    limited = manager.connect(p, 'google_drive', 'files', proof, 'https://app.example')
    broad = manager.connect(p, 'google_drive', 'folders', proof)
    query = parse_qs(urlsplit(limited['authorization_url']).query)
    assert query['scope'] == [GOOGLE_FILE]
    assert parse_qs(urlsplit(broad['authorization_url']).query)['scope'] == [GOOGLE_READ]
    state = query['state'][0]
    with pytest.raises(PermissionError): manager.complete(p, state, '', 'b' * 64)
    other = p.model_copy(update={'user_id': 'other'})
    with pytest.raises(PermissionError): manager.complete(other, state, '', proof)
    declined = manager.complete(p, state, '', proof, error='admin_policy_enforced')
    assert declined['state'] == 'policy_blocked'
    assert declined['error']['action'] == 'administrator'
    with pytest.raises(ValueError): manager.complete(p, state, '', proof, error='access_denied')
    assert 'secret_ref' not in limited and 'session_hash' not in limited


def test_disconnect_stops_local_use_even_if_provider_revocation_fails_and_can_retry(connected):
    p, manager = connected
    doc = manager.connect(p, 'dropbox', 'folders', 'a' * 64)
    value = manager.get(p, doc['id'])
    value.update(state='connected', secret_ref=manager.secrets.write(doc['id'], {'access_token': 'access', 'refresh_token': 'refresh', 'expires_at': 1000}))
    manager.service.save(p, 'intake_connection', value)
    responses = iter([Response(status=503), Response()])
    manager.http = SimpleNamespace(post=lambda *a, **kw: next(responses))
    assert manager.disconnect(p, doc['id'])['error']['code'] == 'revocation_pending'
    with pytest.raises(ImportProblem): manager.token(p, doc['id'])
    assert 'error' not in manager.disconnect(p, doc['id'])


@pytest.mark.parametrize('status,body,code,action', [
    (401, {}, 'authorization_expired', 'connect'),
    (403, {'error': {'errors': [{'reason': 'domainPolicy'}]}}, 'institution_policy', 'administrator'),
    (403, {}, 'file_access', 'file_access'), (404, {}, 'file_access', 'file_access'),
    (429, {}, 'rate_limited', 'retry'), (503, {}, 'provider_unavailable', 'retry'),
])
def test_provider_failures_have_distinct_recovery(status, body, code, action):
    with pytest.raises(ImportProblem) as error: check_response(Response(body, status), 'google_drive')
    assert error.value.intake_problem['code'] == code
    assert error.value.intake_problem['action'] == action
    assert 'pending' not in error.value.intake_problem['message']


def test_shared_dropbox_folder_uses_account_adapter_without_modifying_originals():
    calls = []
    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return Response({'entries': [{'.tag': 'file', 'name': 'photo.png', 'path_lower': '/photo.png', 'rev': 'r1'}], 'has_more': False})
    manager = SimpleNamespace(get=lambda *a, **kw: {'provider': 'dropbox', 'access': 'folders'}, token=lambda *a: 'access', http=SimpleNamespace(request=request))
    adapter = CloudSource(manager, 'dropbox')
    link = 'https://www.dropbox.com/scl/fo/fixture?rlkey=fixture'
    result = adapter.browse(None, 'connection', shared_ref(link))
    assert calls[0][2]['json']['shared_link'] == {'url': link}
    assert calls[0][2]['json']['recursive'] is False
    assert shared_parts(result['items'][0]['source']['object_id']) == (link, '/photo.png')
    assert all('/files/list_folder' in url for _, url, _ in calls)


def test_drive_resource_key_is_preserved_and_original_change_is_detected():
    calls = []
    responses = iter([Response({'id': 'file', 'name': 'x.png', 'mimeType': 'image/png', 'version': '2'})])
    def request(method, url, **kwargs): calls.append((url, kwargs)); return next(responses)
    manager = SimpleNamespace(get=lambda *a, **kw: {'provider': 'google_drive', 'access': 'folders'}, token=lambda *a: 'access', http=SimpleNamespace(request=request))
    adapter = CloudSource(manager, 'google_drive')
    with pytest.raises(ImportProblem) as error:
        adapter.read(None, SourceReference(provider='google_drive', connection_id='c', object_id='gdrive:file:key', version='1'))
    assert error.value.intake_problem['code'] == 'source_changed'
    assert calls[0][1]['headers']['X-Goog-Drive-Resource-Keys'] == 'file/key'
    assert len(calls) == 1


def test_public_reader_rejects_private_dns_and_redirects_before_connecting():
    calls = []
    def resolve(host, *a, **kw):
        return [(2, 1, 6, '', ('127.0.0.1' if host == 'internal.example' else '8.8.8.8', 443))]
    class Connection:
        def request(self, *a, **kw): pass
        def getresponse(self):
            return SimpleNamespace(status=302, getheader=lambda name: 'https://internal.example/image.png')
        def close(self): pass
    def connect(host, address, **kw): calls.append((host, address)); return Connection()
    reader = PublicImageReader(resolve=resolve, connect=connect)
    with pytest.raises(ImportProblem): reader.read('https://internal.example/photo.png')
    assert calls == []
    with pytest.raises(ImportProblem): reader.read('https://public.example/photo.png')
    assert calls == [('public.example', '8.8.8.8')]


def test_direct_reader_sniffs_images_and_bounds_downloads():
    import io
    content = image_bytes()
    class Connection:
        def request(self, *a, **kw): pass
        def getresponse(self):
            stream = io.BytesIO(content)
            return SimpleNamespace(status=200, getheader=lambda key, default=None: str(len(content)) if key == 'Content-Length' else default, read=stream.read)
        def close(self): pass
    reader = PublicImageReader(resolve=lambda *a, **kw: [(2, 1, 6, '', ('8.8.8.8', 443))], connect=lambda *a, **kw: Connection())
    assert reader.read('https://public.example/photo.png') == (content, 'image/png')
    content = b'<html>webpage</html>'
    with pytest.raises((ImportProblem, ValueError)): reader.read('https://public.example/page')


def test_registered_source_keeps_sensitive_listing_gate(tmp_path):
    from test_source_authorization import member_client, HEADERS
    from source_fixtures import SOURCE_ID, OBJECT_PREFIX, FIRST_GENERATION, write_object, jpeg_bytes
    objects = tmp_path / 'objects'
    write_object(objects, OBJECT_PREFIX + 'private.jpeg', jpeg_bytes(), FIRST_GENERATION)
    client = member_client(tmp_path / 'app', objects, 'operator', can_view_sensitive=False)
    root = f'/v1/organizations/{SYNTHETIC_ORG}/collections/{SYNTHETIC_COLLECTION}/intake'
    assert client.post(root + f'/sources/{SOURCE_ID}/browse', headers=HEADERS, json={}).status_code == 403
    assert client.get(root + '/sources', headers=HEADERS).json()['items'] == []


def test_storage_selection_does_not_hide_the_501st_photo_after_a_folder_marker(tmp_path):
    from source_fixtures import SOURCE_ID, OBJECT_PREFIX, HEADERS, paged_gcs_reader, source_client

    objects = [{'name': OBJECT_PREFIX}]
    objects += [{'name': OBJECT_PREFIX + f'a-unsupported-{i:04}.txt', 'size': '12', 'generation': '1'} for i in range(4500)]
    objects += [{'name': OBJECT_PREFIX + f'b-photo-{i:03}.jpg', 'size': '12', 'generation': '1'} for i in range(501)]
    reader, calls = paged_gcs_reader(objects)
    client = source_client(tmp_path / 'app', tmp_path / 'objects', reader=reader)
    root = f'/v1/organizations/{SYNTHETIC_ORG}/collections/{SYNTHETIC_COLLECTION}/intake'

    response = client.post(root + f'/sources/{SOURCE_ID}/select-folder', headers=HEADERS, json={})

    assert response.status_code == 422, response.text
    assert response.json()['error']['code'] == 'folder_limit'
    assert len(calls) == 6


def test_storage_selection_reports_incomplete_marker_scan(tmp_path, monkeypatch):
    from source_fixtures import SOURCE_ID, OBJECT_PREFIX, HEADERS, paged_gcs_reader, source_client
    from specimen_digitization.application import source_reader

    monkeypatch.setattr(source_reader, 'MIN_LISTING_SCAN_LIMIT', 5001)
    objects = [{'name': OBJECT_PREFIX + f'folder-{i}/'} for i in range(5001)]
    objects.append({'name': OBJECT_PREFIX + 'hidden.jpg', 'size': '12', 'generation': '1'})
    reader, _ = paged_gcs_reader(objects)
    client = source_client(tmp_path / 'app', tmp_path / 'objects', reader=reader)
    root = f'/v1/organizations/{SYNTHETIC_ORG}/collections/{SYNTHETIC_COLLECTION}/intake'

    response = client.post(root + f'/sources/{SOURCE_ID}/select-folder', headers=HEADERS, json={})

    assert response.status_code == 422, response.text
    assert response.json()['error']['code'] == 'incomplete_search'


def test_expired_dropbox_access_requires_refresh_then_revocation(connected):
    _, manager = connected
    calls = []
    responses = iter([Response(status=401), Response({'access_token': 'fresh'}), Response()])
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return next(responses)
    manager.http = SimpleNamespace(post=post)
    assert manager._revoke('dropbox', {'access_token': 'expired', 'refresh_token': 'refresh'})
    assert calls[1][1]['data']['grant_type'] == 'refresh_token'
    assert calls[2][1]['headers']['Authorization'] == 'Bearer fresh'


def test_partial_drive_search_requires_narrower_folder():
    adapter = CloudSource(None, 'google_drive')
    adapter.browse = lambda *a: {'items': [], 'message': 'Select a specific folder.'}
    with pytest.raises(ImportProblem) as error:
        adapter.select_folder(None, 'c', 'folder', False, 500)
    assert error.value.intake_problem['code'] == 'incomplete_search'


def test_folder_counts_separate_download_denial_from_unsupported_formats():
    adapter = CloudSource(None, 'google_drive')
    files = [
        {'id': 'ok', 'name': 'ok.png', 'mimeType': 'image/png'},
        {'id': 'denied', 'name': 'private.png', 'mimeType': 'image/png', 'capabilities': {'canDownload': False}},
        {'id': 'text', 'name': 'notes.txt', 'mimeType': 'text/plain'},
    ]
    adapter.browse = lambda *a: {'items': [adapter.row('c', row) for row in files]}
    result = adapter.select_folder(None, 'c', 'folder', False, 500)
    assert (result['discovered'], result['unsupported'], result['inaccessible']) == (3, 1, 1)
    assert [row['id'] for row in result['items']] == ['ok']


@pytest.mark.parametrize('same_account', [True, False])
def test_reconnect_preserves_item_connection_only_for_the_same_provider_account(connected, same_account):
    p, manager = connected
    value = manager.connect(p, 'google_drive', 'folders', 'a' * 64)
    doc = manager.get(p, value['id'])
    doc.update(state='connected', account_id='original-account', secret_ref=manager.secrets.write(value['id'], {'access_token': 'expired', 'refresh_token': 'revoked', 'expires_at': 0}))
    manager.service.save(p, 'intake_connection', doc)
    manager.http = SimpleNamespace(post=lambda *a, **kw: Response(status=400))
    with pytest.raises(ImportProblem): manager.token(p, value['id'])
    resumed = manager.connect(p, 'google_drive', 'folders', 'b' * 64, reconnect_id=value['id'])
    assert resumed['id'] == value['id']
    state = parse_qs(urlsplit(resumed['authorization_url']).query)['state'][0]
    manager.http = SimpleNamespace(
        post=lambda *a, **kw: Response({'access_token': 'fresh', 'refresh_token': 'refresh', 'scope': GOOGLE_READ}),
        get=lambda *a, **kw: Response({'user': {'permissionId': 'original-account' if same_account else 'other-account', 'emailAddress': 'fixture@example.test'}}))
    if same_account:
        manager.complete(p, state, 'code', 'b' * 64)
        assert manager.token(p, value['id']) == 'fresh'
        CloudSource(manager, 'google_drive').validate(p, SourceReference(provider='google_drive', connection_id=value['id'], object_id='old-file', version='1'))
    else:
        with pytest.raises(ImportProblem) as error: manager.complete(p, state, 'code', 'b' * 64)
        assert error.value.intake_problem['code'] == 'account_mismatch'
        assert manager.get(p, value['id'])['state'] == 'needs_authorization'


def test_source_preview_is_private_and_does_not_create_a_draft_or_specimen(tmp_path):
    import base64
    from fastapi.testclient import TestClient
    from test_application import HEADERS, PREFIX
    app = local_app(tmp_path, TOKEN)
    content = image_bytes()
    app.state.intake.sources.url_reader = SimpleNamespace(read=lambda url: (content, 'image/png'))
    client = TestClient(app)
    root = PREFIX + '/collections/' + SYNTHETIC_COLLECTION + '/intake'
    result = client.post(root + '/source-preview', headers=HEADERS, json={'provider': 'url', 'url': 'https://public.example/photo.png'})
    assert result.status_code == 200, result.text
    assert base64.b64decode(result.json()['image']).startswith(b'\xff\xd8')
    assert result.headers['cache-control'] == 'private, no-store'
    assert client.get(root + '/drafts', headers=HEADERS).json()['items'] == []
    assert app.state.workflow.repository.list(Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)) == []


def test_provider_links_use_the_explicit_owned_account(connected):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from specimen_digitization.application.intake_source_routes import install_source_routes
    p, manager = connected
    ids = []
    for _ in range(2):
        initial = manager.connect(p, 'google_drive', 'folders', 'a' * 64)
        doc = manager.get(p, initial['id'])
        doc['state'] = 'connected'
        manager.service.save(p, 'intake_connection', doc)
        ids.append(doc['id'])
    manager.service.sources.providers['google_drive'] = SimpleNamespace(resolve=lambda p, id, url: {'connection_id': id})
    app = FastAPI()
    install_source_routes(app, '/v1/organizations/{organization_id}', manager.service, manager, identity=lambda: p.user_id, principal=lambda *a, **kw: p)
    client = TestClient(app)
    root = f'/v1/organizations/{p.scope.organization_id}/collections/{p.scope.collection_id}/intake/resolve'
    body = {'url': 'https://drive.google.com/file/d/file/view', 'connection_id': ids[1]}
    assert client.post(root, json=body).json()['items'][0]['connection_id'] == ids[1]
    with pytest.raises(ImportProblem) as error:
        client.post(root, json={'url': body['url']})
    assert error.value.intake_problem['code'] == 'choose_account'
    with pytest.raises(ImportProblem):
        client.post(root, json={**body, 'connection_id': 'someone-elses-connection'})


def test_web_callback_leaves_popup_lifecycle_to_initiating_app(connected):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from specimen_digitization.application.intake_source_routes import install_source_routes
    p, manager = connected
    app = FastAPI()
    install_source_routes(app, '/v1/organizations/{organization_id}', manager.service, manager,
        identity=lambda: p.user_id, principal=lambda *a, **kw: p)
    connection = manager.connect(p, 'google_drive', 'files', 'a' * 64, 'https://app.example')
    state = parse_qs(urlsplit(connection['authorization_url']).query)['state'][0]
    response = TestClient(app).get('/v1/intake/oauth/callback', params={'state': state, 'code': 'one-use-code'})
    assert response.status_code == 200
    assert 'window.opener.postMessage(' in response.text
    assert '"https://app.example"' in response.text
    assert 'window.close()' not in response.text
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['referrer-policy'] == 'no-referrer'
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    # Merely visiting the callback must not exchange credentials or connect.
    assert manager.get(p, connection['id'])['state'] == 'needs_authorization'
    assert manager.verify_pending(p, state, 'oauth')['state'] == 'pending'


@pytest.mark.parametrize('provider', ['google_drive', 'dropbox'])
def test_connection_setup_failure_has_browser_readable_recovery(tmp_path, provider):
    from fastapi.testclient import TestClient
    from test_application import HEADERS, PREFIX
    app = local_app(tmp_path, TOKEN)
    root = PREFIX + '/collections/' + SYNTHETIC_COLLECTION + '/intake'
    # The default TestClient also rejects an unhandled exception: this must be
    # a handled import response, not the outer server-error middleware.
    response = TestClient(app).post(root + '/connections',
        headers={**HEADERS, 'Origin': 'http://localhost:3000'},
        json={'provider': provider, 'access': 'folders', 'session_proof': 'a' * 64,
              'return_origin': 'http://localhost:3000'})
    assert response.status_code == 422
    assert response.headers['access-control-allow-origin'] == 'http://localhost:3000'
    error = response.json()['error']
    assert error['code'] == 'provider_not_configured'
    assert error['details']['action'] == 'administrator'
    assert error['retryable'] is False
    assert 'setup' in error['message']


def test_secret_store_roundtrip_accepts_only_configured_project_id_and_number():
    import base64
    from uuid import uuid4
    id = str(uuid4())
    ref = f'projects/123456789/secrets/specimen-intake-{id}/versions/2'
    stored, calls = {}, []
    def post(url, **kwargs):
        calls.append(url)
        if url.endswith(':addVersion'):
            stored.update(kwargs['json'])
            return Response({'name': ref})
        return Response()
    def get(url, **kwargs):
        calls.append(url)
        return Response(stored)
    store = SecretManagerTokens('fixture-project', SimpleNamespace(post=post, get=get), project_number='123456789')
    assert store.write(id, {'verifier': 'credential-free-fixture'}) == ref
    assert store.read(ref) == {'verifier': 'credential-free-fixture'}
    assert store.read(ref.replace('123456789', 'fixture-project')) == {'verifier': 'credential-free-fixture'}
    calls.clear()
    for invalid in [ref.replace('123456789', '987654321'), ref.replace('123456789', 'another-project'), ref.replace('/2', '/latest')]:
        with pytest.raises(ValueError): store.read(invalid)
    assert calls == []
    assert json.loads(base64.b64decode(stored['payload']['data']))['verifier'] == 'credential-free-fixture'


def test_native_drive_picker_uses_exact_scope_and_persists_confirmed_selection(connected):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from specimen_digitization.application.intake_source_routes import install_source_routes
    p, manager = connected
    native = manager.connect(p, 'google_drive', 'files', 'a' * 64)
    query = parse_qs(urlsplit(native['authorization_url']).query)
    assert query['scope'] == [GOOGLE_FILE]
    assert query['include_granted_scopes'] == ['false']
    assert query['trigger_onepick'] == ['true']
    assert query['allow_multiple'] == ['true']
    assert 'image/jpeg' in query['mimetypes'][0]
    state = query['state'][0]
    reads = []
    def metadata(method, url, **kwargs):
        reads.append(url)
        if url.endswith('/denied'):
            return Response(status=403)
        return Response({'id': 'photo', 'name': 'photo.png', 'mimeType': 'image/png', 'version': '7'})
    manager.http = SimpleNamespace(
        post=lambda *a, **kw: Response({'access_token': 'access', 'refresh_token': 'refresh', 'scope': GOOGLE_FILE}),
        get=lambda *a, **kw: Response({'user': {'permissionId': 'provider-account', 'emailAddress': 'fixture@example.test'}}),
        request=metadata)
    manager.service.sources.providers['google_drive'] = CloudSource(manager, 'google_drive')
    app = FastAPI()
    install_source_routes(app, '/v1/organizations/{organization_id}', manager.service, manager,
        identity=lambda: p.user_id, principal=lambda *a, **kw: p)
    client = TestClient(app)
    callback = client.get('/v1/intake/oauth/callback', params={'state': state, 'code': 'one-use-code', 'picked_file_ids': 'photo,denied,photo'}, follow_redirects=False)
    assert callback.status_code == 303
    assert parse_qs(urlsplit(callback.headers['location']).fragment)['picked_file_ids'] == ['photo,denied,photo']
    assert manager.get(p, native['id'])['state'] == 'needs_authorization'
    assert reads == []
    root = f'/v1/organizations/{p.scope.organization_id}/collections/{p.scope.collection_id}/intake'
    response = client.post(root + '/connections/complete', json={'state': state, 'code': 'one-use-code',
        'session_proof': 'a' * 64, 'picked_file_ids': 'photo,denied,photo'})
    assert response.status_code == 200
    value = response.json()
    assert 'secret_ref' not in value
    assert value['selection']['items'][0]['source']['version'] == '7'
    assert value['selection']['failures'][0]['error']['code'] == 'file_access'
    assert len(reads) == 2
    status = client.get(root + f"/connections/{native['id']}/picker/{native['picker_id']}").json()
    assert status == value['selection']
    assert len(reads) == 2
    assert manager.service.list(p, 'intake_draft')['items'] == []
    assert manager.service.repo.list(p.scope) == []


def test_native_selection_requires_original_session_proof_before_exchange(connected):
    p, manager = connected
    native = manager.connect(p, 'google_drive', 'files', 'a' * 64)
    state = parse_qs(urlsplit(native['authorization_url']).query)['state'][0]
    with pytest.raises(PermissionError):
        manager.complete(p, state, 'code', 'b' * 64, selected_files='photo')
    assert manager.verify_pending(p, state, 'oauth')['state'] == 'pending'
    for files in ['photo/invalid', 'photo,,other', ','.join(['photo'] * 501)]:
        with pytest.raises(ValueError):
            manager.complete(p, state, 'code', 'a' * 64, selected_files=files)
    assert manager.verify_pending(p, state, 'oauth')['state'] == 'pending'


@pytest.mark.parametrize('scope', [GOOGLE_READ, GOOGLE_FILE + ' ' + GOOGLE_READ])
def test_native_picker_refuses_missing_or_combined_grants(connected, scope):
    p, manager = connected
    native = manager.connect(p, 'google_drive', 'files', 'a' * 64)
    state = parse_qs(urlsplit(native['authorization_url']).query)['state'][0]
    manager.http = SimpleNamespace(post=lambda *a, **kw: Response({'access_token': 'access', 'refresh_token': 'refresh', 'scope': scope}))
    with pytest.raises(ImportProblem) as error:
        manager.complete(p, state, 'code', 'a' * 64, selected_files='photo')
    assert error.value.intake_problem['code'] == 'scope_declined'
    assert manager.get(p, native['id'])['state'] == 'needs_authorization'


@pytest.mark.parametrize('provider,scope', [('google_drive', GOOGLE_FILE), ('dropbox', DROPBOX_SCOPES)])
def test_oauth_client_configuration_failure_is_not_institution_policy(connected, provider, scope):
    p, manager = connected
    native = manager.connect(p, provider, 'files' if provider == 'google_drive' else 'folders', 'a' * 64)
    state = parse_qs(urlsplit(native['authorization_url']).query)['state'][0]
    manager.http = SimpleNamespace(post=lambda *a, **kw: Response({'error': 'invalid_client'}, status=401))
    with pytest.raises(ImportProblem) as error:
        manager.complete(p, state, 'code', 'a' * 64)
    assert error.value.intake_problem['code'] == 'provider_configuration'
    assert error.value.intake_problem['action'] == 'administrator'
    assert manager.get(p, native['id'])['state'] == 'needs_authorization'


@pytest.mark.parametrize('body,code,action', [
    ({'error': {'errors': [{'reason': 'accessNotConfigured'}]}}, 'provider_configuration', 'administrator'),
    ({'error': {'details': [{'reason': 'SERVICE_DISABLED'}]}}, 'provider_configuration', 'administrator'),
    ({'error': {'details': [{'reason': 'ACCESS_TOKEN_SCOPE_INSUFFICIENT'}]}}, 'connection_permissions', 'connect'),
])
def test_drive_application_setup_and_scope_errors_are_not_file_denials(body, code, action):
    with pytest.raises(ImportProblem) as error:
        check_response(Response(body, 403), 'google_drive')
    assert error.value.intake_problem['code'] == code
    assert error.value.intake_problem['action'] == action
