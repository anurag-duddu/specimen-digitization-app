"""Synthetic provider/security contracts; these are not live account acceptance."""
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
import pytest
from specimen_digitization.application.api import local_app, SYNTHETIC_ORG, SYNTHETIC_COLLECTION
from specimen_digitization.application.domain import Principal, Scope
from specimen_digitization.application.intake_connections import ConnectionManager, GOOGLE_FILE, GOOGLE_READ
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
