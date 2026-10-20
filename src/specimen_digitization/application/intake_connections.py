"""User-scoped OAuth connections. Refresh tokens never enter API responses."""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit
from uuid import uuid4
import requests

from .intake_models import ProviderConnection
from .intake_sources import ImportProblem
from .storage import Conflict

GOOGLE_FILE = 'https://www.googleapis.com/auth/drive.file'
GOOGLE_READ = 'https://www.googleapis.com/auth/drive.readonly'
PICKER_IMAGE_TYPES = 'image/jpeg,image/png,image/tiff,image/heic,image/heif,image/dng,image/x-adobe-dng'
DROPBOX_SCOPES = 'account_info.read files.metadata.read files.content.read sharing.read'
PROVIDERS = {
    'google_drive': ('https://accounts.google.com/o/oauth2/v2/auth', 'https://oauth2.googleapis.com/token'),
    'dropbox': ('https://www.dropbox.com/oauth2/authorize', 'https://api.dropboxapi.com/oauth2/token'),
}
CREDENTIAL_WRITE_SECONDS = 180
DYNAMIC_SECRET_ID = r'specimen-intake-[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}'


class SecretManagerTokens:
    """Dedicated per-connection secrets. Configuration pins client secret versions."""
    def __init__(self, project, session=None, *, project_number=None):
        if not re.fullmatch(r'[a-z][a-z0-9-]{4,61}[a-z0-9]', project):
            raise ValueError('Invalid secret project')
        if project_number is not None and not re.fullmatch(r'[1-9][0-9]*', str(project_number)):
            raise ValueError('Invalid secret project number')
        if session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession
            credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
            session = AuthorizedSession(credentials)
        self.project, self.session = project, session
        self.project_aliases = {project} | ({str(project_number)} if project_number else set())

    def _validate_ref(self, ref):
        match = re.fullmatch(r'projects/([^/]+)/secrets/[a-zA-Z0-9_-]+/versions/[1-9][0-9]*', ref)
        if match is None or match[1] not in self.project_aliases:
            raise ValueError('A numbered secret version in the configured project is required')

    def version_key(self, ref):
        self._validate_ref(ref)
        parts = ref.split('/')
        return parts[3], int(parts[5])

    def _parent(self, id):
        name = 'specimen-intake-' + id
        if not re.fullmatch(DYNAMIC_SECRET_ID, name):
            raise ValueError('Invalid credential identity')
        return f'projects/{self.project}/secrets/{name}'

    def owns(self, id, ref):
        return self.version_key(ref)[0] == self._parent(id).split('/')[-1]

    def list_versions(self, id):
        parent = self._parent(id)
        result, cursor, seen = [], None, set()
        while True:
            response = self.session.get('https://secretmanager.googleapis.com/v1/' + parent + '/versions',
                params={'pageSize': 100, 'filter': 'state:(ENABLED OR DISABLED)',
                        **({'pageToken': cursor} if cursor else {})}, timeout=15)
            if response.status_code == 404:
                return []
            if response.status_code != 200:
                raise ImportProblem('credential_storage', 'Connection credentials could not be checked. Retry shortly.')
            body = response.json()
            for version in body.get('versions', []):
                ref = version['name']
                if self.version_key(ref)[0] != parent.split('/')[-1]:
                    raise ValueError('Credential version belongs to another connection')
                if version.get('state') != 'DESTROYED':
                    result.append(ref)
            cursor = body.get('nextPageToken')
            if not cursor:
                return result
            if cursor in seen or len(seen) >= 100:
                raise ImportProblem('credential_storage', 'Connection credential history could not be checked. Ask your administrator.', 'administrator', False)
            seen.add(cursor)

    def destroy(self, ref):
        name, _ = self.version_key(ref)
        if not re.fullmatch(DYNAMIC_SECRET_ID, name):
            raise ValueError('Only dynamic intake credential versions may be destroyed')
        response = self.session.post('https://secretmanager.googleapis.com/v1/' + ref + ':destroy', json={}, timeout=15)
        if response.status_code != 200:
            raise ImportProblem('credential_storage', 'Old connection credentials could not be retired. Retry shortly.')

    def version_state(self, ref):
        name, _ = self.version_key(ref)
        if not re.fullmatch(DYNAMIC_SECRET_ID, name):
            raise ValueError('Only dynamic intake credential metadata may be inspected')
        response = self.session.get('https://secretmanager.googleapis.com/v1/' + ref, timeout=15)
        if response.status_code == 200:
            return response.json().get('state')
        if response.status_code == 404:
            return None  # Metadata absence may be stale; it is not destruction proof.
        raise ImportProblem('credential_storage', 'Old connection credentials could not be checked. Retry shortly.')

    def read(self, ref):
        self._validate_ref(ref)
        response = self.session.get('https://secretmanager.googleapis.com/v1/' + ref + ':access', timeout=15)
        if response.status_code != 200:
            raise ImportProblem('credential_storage', 'Connection credentials are unavailable. Ask your administrator.', 'administrator', False)
        return json.loads(base64.b64decode(response.json()['payload']['data']))

    def write(self, id, value):
        if not re.fullmatch(r'[a-f0-9-]{36}', id):
            raise ValueError('Invalid credential identity')
        parent = f'projects/{self.project}/secrets'
        secret = 'specimen-intake-' + id  # pragma: allowlist secret -- resource name, not a credential
        response = self.session.post('https://secretmanager.googleapis.com/v1/' + parent,
            params={'secretId': secret}, json={'replication': {'automatic': {}}}, timeout=15)
        if response.status_code not in {200, 409}:
            raise ImportProblem('credential_storage', 'Connection setup could not save credentials. Ask your administrator.', 'administrator', False)
        response = self.session.post('https://secretmanager.googleapis.com/v1/' + parent + '/' + secret + ':addVersion',
            json={'payload': {'data': base64.b64encode(json.dumps(value).encode()).decode()}}, timeout=15)
        if response.status_code != 200:
            raise ImportProblem('credential_storage', 'Connection credentials could not be saved. Try connecting again.', 'connect', False)
        ref = response.json()['name']
        self._validate_ref(ref)
        return ref


def safe_connection(doc):
    return {key: doc[key] for key in ('id', 'provider', 'access', 'state', 'account_label', 'account_id', 'revision') if key in doc} | (
        {'error': doc['error']} if doc.get('error') else {})


def picked_file_ids(value):
    """Native Picker callback data is untrusted and bounded before metadata reads."""
    ids = value.split(',') if value else []
    if len(ids) > 500 or any(not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', id) for id in ids):
        raise ValueError('Select at most 500 valid Drive files')
    return list(dict.fromkeys(ids))


def oauth_failure(response, *, refreshing=False):
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = body.get('error') if isinstance(body, dict) else None
    error = error if isinstance(error, str) else None
    if error in {'invalid_client', 'unauthorized_client', 'redirect_uri_mismatch'}:
        return ImportProblem('provider_configuration', 'This connection needs application setup. Ask your administrator to check the provider configuration.', 'administrator', False)
    if error in {'admin_policy_enforced', 'org_internal'}:
        return ImportProblem('institution_policy', 'Your organization prevents this connection. Ask IT to review this app.', 'administrator', False)
    if response.status_code == 429 or response.status_code >= 500:
        return ImportProblem('provider_unavailable', 'The provider is temporarily unavailable. Try again shortly.', 'retry' if refreshing else 'connect', refreshing)
    return ImportProblem('authorization_expired' if refreshing else 'authorization_failed',
        'This account needs to be connected again.' if refreshing else 'This authorization expired or was refused. Connect again.', 'connect', False)


class ConnectionManager:
    def __init__(self, service, configuration, secrets_store, *, http=None, clock=time.time):
        self.service, self.config, self.secrets = service, configuration, secrets_store
        self.http, self.clock = http or requests.Session(), clock
        for name, config in self.config.items():
            if name not in PROVIDERS or urlsplit(config['redirect_uri']).scheme != 'https':
                raise ValueError('Explicit HTTPS OAuth callback configuration required')
            if not config.get('client_id') or not config.get('client_secret_ref'):
                raise ValueError('OAuth client configuration is incomplete')

    def get(self, p, id, *, connected=False):
        self.service.authorize(p)  # A worker's previously constructed Principal may be stale.
        doc = self.service.read(p, 'intake_connection', id)
        if connected and doc['state'] != 'connected':
            raise ImportProblem('authorization_required', 'Connect this account again to continue.', 'connect', False)
        return doc

    def _same_ref(self, left, right):
        return bool(left and right and self.secrets.version_key(left) == self.secrets.version_key(right))

    @staticmethod
    def _changed():
        return ImportProblem('connection_changed', 'The connection changed. Reconnect or retry.', 'connect', False)

    def _queue_retirement(self, connection, ref, *, revoke=False):
        if not self.secrets.owns(connection['id'], ref):
            raise ValueError('Credential retirement belongs to another connection')
        if not any(self._same_ref(item['ref'], ref) for item in connection.get('credential_retirements', [])):
            connection.setdefault('credential_retirements', []).append(dict(ref=ref, revoke=revoke))

    def _retired(self, connection, ref):
        if not self.secrets.owns(connection['id'], ref):
            raise ValueError('Credential version belongs to another connection')
        version = self.secrets.version_key(ref)[1]
        return any(first <= version <= last for first, last in connection.get('credential_retired_versions', []))

    def _remember_retired(self, connection, ref):
        version = self.secrets.version_key(ref)[1]
        intervals = sorted(connection.get('credential_retired_versions', []) + [[version, version]])
        merged = []
        for first, last in intervals:
            if merged and first <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], last)
            else:
                merged.append([first, last])
        connection['credential_retired_versions'] = merged

    @staticmethod
    def _revocation_pending():
        return ImportProblem('revocation_pending', 'Old provider access still needs to be revoked. Retry this connection.', 'retry', True)

    def _retire(self, p, connection):
        for retirement in list(connection.get('credential_retirements', [])):
            connection = self.get(p, connection['id'])
            retirement = next((item for item in connection.get('credential_retirements', [])
                if self._same_ref(item['ref'], retirement['ref'])), None)
            if retirement is None:
                continue
            if not self.secrets.owns(connection['id'], retirement['ref']):
                raise ValueError('Credential retirement belongs to another connection')
            if connection['state'] != 'disconnected' and self._same_ref(connection.get('secret_ref'), retirement['ref']):
                raise self._changed()
            if not self._retired(connection, retirement['ref']):
                if retirement['revoke']:
                    claim = retirement.get('revocation_claim')
                    if claim and claim['expires_at'] > self.clock():
                        raise self._revocation_pending()
                    claim = dict(id=str(uuid4()), expires_at=self.clock() + CREDENTIAL_WRITE_SECONDS)
                    retirement['revocation_claim'] = claim
                    connection = self.service.save(p, 'intake_connection', connection)
                    token = self.secrets.read(retirement['ref'])
                    current = self.get(p, connection['id'])
                    current_item = next((item for item in current.get('credential_retirements', [])
                        if self._same_ref(item['ref'], retirement['ref'])), {})
                    if current_item.get('revocation_claim', {}).get('id') != claim['id'] or claim['expires_at'] <= self.clock():
                        raise self._revocation_pending()
                    revoked = self._revoke(connection['provider'], token)
                    connection = self.get(p, connection['id'])
                    current_item = next((item for item in connection.get('credential_retirements', [])
                        if self._same_ref(item['ref'], retirement['ref'])), {})
                    if current_item.get('revocation_claim', {}).get('id') != claim['id']:
                        raise self._revocation_pending()
                    current_item.pop('revocation_claim', None)
                    if not revoked:
                        self.service.save(p, 'intake_connection', connection)
                        raise self._revocation_pending()
                    # A retry after destruction must not need the destroyed payload.
                    for item in connection['credential_retirements']:
                        if self._same_ref(item['ref'], retirement['ref']):
                            item['revoke'] = False
                    connection = self.service.save(p, 'intake_connection', connection)
                # Only the current owned document can authorize retirement.
                latest = self.get(p, connection['id'])
                if latest['state'] != 'disconnected' and self._same_ref(latest.get('secret_ref'), retirement['ref']):
                    raise self._changed()
                current_item = next(item for item in latest['credential_retirements']
                    if self._same_ref(item['ref'], retirement['ref']))
                destroying = current_item.get('destroying', False)
                if not destroying:
                    current_item['destroying'] = True
                    latest = self.service.save(p, 'intake_connection', latest)
                if not destroying or self.secrets.version_state(retirement['ref']) != 'DESTROYED':
                    self.secrets.destroy(retirement['ref'])
                connection = latest
            self._remember_retired(connection, retirement['ref'])
            connection['credential_retirements'] = [item for item in connection.get('credential_retirements', [])
                if not self._same_ref(item['ref'], retirement['ref'])]
            if connection['state'] == 'disconnected' and self._same_ref(connection.get('secret_ref'), retirement['ref']):
                connection.pop('secret_ref', None)
            connection = self.service.save(p, 'intake_connection', connection)
        return connection

    def _settle(self, p, connection, *, confirmed_refs=()):
        """Recover a recorded write, then retire only fenced/non-current versions.

        SQL holds operation IDs and references, never token payloads. An empty
        scan after the pending deadline fences an unsent/unknown write; a late
        append remains discoverable on this exact parent at the next activity.
        """
        connection = self._retire(p, connection)
        refs = self.secrets.list_versions(connection['id'])
        candidate_ref = connection.get('credential_write', {}).get('candidate_ref')
        refs = list(dict.fromkeys(refs + list(confirmed_refs) + ([candidate_ref] if candidate_ref else [])))
        values = {ref: self.secrets.read(ref) for ref in refs
                  if not self._same_ref(ref, connection.get('secret_ref')) and not self._retired(connection, ref)}
        intent = connection.get('credential_write')
        candidates = [ref for ref, value in values.items() if intent and value.get('_intake_credential') ==
                      dict(id=intent['id'], generation=intent['generation'], kind=intent['kind'])]
        changed = False
        if intent and candidates and intent.get('rejection'):
            old_ref = connection.get('secret_ref')
            old = self.secrets.read(old_ref) if old_ref else {}
            for ref in candidates:
                rejected = values[ref]
                # Google revocation invalidates the accepted project grant too.
                # A Dropbox token without family identity may share that family.
                revoke = connection['state'] == 'disconnected' or not old_ref or (
                    connection['provider'] == 'dropbox' and rejected.get('refresh_token')
                    and old.get('refresh_token') and rejected['refresh_token'] != old['refresh_token'])
                self._queue_retirement(connection, ref, revoke=bool(revoke))
            if connection['state'] != 'disconnected':
                connection.update(state=connection.get('authorization_previous_state', 'needs_authorization')
                    if old_ref else 'needs_authorization', error=intent['rejection'])
            if intent.get('oauth_id'):
                connection['credential_rejected_oauth'] = dict(id=intent['oauth_id'], error=intent['rejection'])
            connection.pop('credential_write')
            connection.pop('authorization_previous_state', None)
            changed = True
        elif intent and candidates and intent['updates'].get('state') == 'connected' and connection['state'] != 'disconnected':
            candidate = max(candidates, key=lambda ref: self.secrets.version_key(ref)[1])
            old_ref = connection.get('secret_ref')
            if old_ref:
                old = self.secrets.read(old_ref)
                revoke = connection['provider'] == 'dropbox' and intent['kind'] == 'connect' and old.get('refresh_token') != values[candidate].get('refresh_token')
                self._queue_retirement(connection, old_ref, revoke=revoke)
            connection.update(intent['updates'], secret_ref=candidate)
            if intent.get('oauth_id'):
                connection['credential_authorized_oauth_id'] = intent['oauth_id']
            connection.pop('credential_write')
            connection.pop('authorization_previous_state', None)
            connection.pop('error', None)
            changed = True
        elif intent and (candidates or intent['expires_at'] <= self.clock()):
            # Never expire current credentials or discard a recoverable candidate.
            connection.pop('credential_write')
            if connection['state'] != 'disconnected':
                connection.update(state='needs_authorization', error=dict(code='authorization_retry',
                    message='Connection saving was interrupted. Connect again to continue.', action='connect', retryable=False))
            changed = True
        current = None
        for ref, value in values.items():
            if self._same_ref(ref, connection.get('secret_ref')):
                continue
            marker = value.get('_intake_credential', {})
            if marker.get('generation', 0) > connection.get('credential_generation', 0):
                raise self._changed()
            if current is None and connection.get('secret_ref'):
                current = self.secrets.read(connection['secret_ref'])
            revoke = connection['state'] == 'disconnected' or (connection['provider'] == 'dropbox'
                and marker.get('kind', 'connect') == 'connect'
                and value.get('refresh_token') != (current or {}).get('refresh_token'))
            self._queue_retirement(connection, ref, revoke=revoke)
            changed = True
        if connection['state'] == 'disconnected' and connection.get('secret_ref'):
            self._queue_retirement(connection, connection['secret_ref'], revoke=True)
            changed = True
        if changed:
            connection = self.service.save(p, 'intake_connection', connection)
        connection = self._retire(p, connection)
        if connection.get('credential_write'):
            raise ImportProblem('credential_write_pending', 'This connection is still being saved. Retry shortly; if saving was interrupted, reconnect after three minutes.')
        oauth_id = connection.get('credential_authorized_oauth_id')
        if oauth_id and connection['state'] == 'connected':
            pending = self.service.read(p, 'intake_oauth', oauth_id)
            if pending['state'] == 'exchanging':
                pending['state'] = 'authorized'
                self.service.save(p, 'intake_oauth', pending)
            connection.pop('credential_authorized_oauth_id')
            connection = self.service.save(p, 'intake_connection', connection)
        rejected_oauth = connection.get('credential_rejected_oauth')
        if rejected_oauth:
            pending = self.service.read(p, 'intake_oauth', rejected_oauth['id'])
            if pending['state'] == 'exchanging':
                pending.update(state='failed', error=rejected_oauth['error'])
                self.service.save(p, 'intake_oauth', pending)
            connection.pop('credential_rejected_oauth')
            connection = self.service.save(p, 'intake_connection', connection)
        return connection

    def recover(self, p, id):
        return self._settle(p, self.get(p, id))

    def _begin_write(self, p, connection, kind):
        connection = self._settle(p, connection)
        generation = connection.get('credential_generation', 0) + 1
        connection.update(credential_generation=generation, credential_write=dict(
            id=str(uuid4()), generation=generation, kind=kind,
            expires_at=self.clock() + CREDENTIAL_WRITE_SECONDS, updates={},
            oauth_id=connection.get('authorization_id') if kind == 'connect' else None))
        return self.service.save(p, 'intake_connection', connection)

    def _cancel_write(self, p, connection, *, state=None):
        current = self.get(p, connection['id'])
        if current.get('credential_write', {}).get('id') != connection['credential_write']['id']:
            raise self._changed()
        current.pop('credential_write')
        if state and current['state'] != 'disconnected':
            current['state'] = state
        return self.service.save(p, 'intake_connection', current)

    def _persist(self, p, connection, token, updates, *, rejection=None):
        intent = connection['credential_write']
        current = self.get(p, connection['id'])
        if current.get('credential_write', {}).get('id') == intent['id'] and intent['expires_at'] <= self.clock():
            self._settle(p, current)
            current = self.get(p, connection['id'])
        if current.get('credential_write', {}).get('id') == intent['id']:
            current['credential_write']['updates'] = updates
            if rejection:
                current['credential_write']['rejection'] = rejection
            try:
                current = self.service.save(p, 'intake_connection', current)
            except Conflict:
                # The issued grant still needs a durable retirement handle.
                current = self.get(p, connection['id'])
        value = dict(token, _intake_credential={key: intent[key] for key in ('id', 'generation', 'kind')})
        confirmed_ref = None
        try:
            confirmed_ref = self.secrets.write(current['id'], value)
        except (requests.RequestException, ImportProblem):
            # A lost addVersion reply is recovered by exact-parent inventory.
            pass
        if confirmed_ref:
            current = self.get(p, current['id'])
            if current.get('credential_write', {}).get('id') == intent['id']:
                current['credential_write']['candidate_ref'] = confirmed_ref
                try:
                    self.service.save(p, 'intake_connection', current)
                except Conflict:
                    pass  # Direct numbered access still identifies this writer's result.
        try:
            result = self._settle(p, self.get(p, current['id']), confirmed_refs=[confirmed_ref] if confirmed_ref else [])
        except Conflict:
            raise self._changed() from None
        if rejection:
            return result
        if result['state'] != 'connected':
            raise self._changed()
        stored = self.secrets.read(result['secret_ref'])
        if stored.get('_intake_credential') != value['_intake_credential']:
            raise self._changed()
        return result

    def _reject_issued(self, p, connection, token, problem):
        if any(isinstance(token.get(key), str) and token[key] for key in ('access_token', 'refresh_token')):
            self._persist(p, connection, token, {}, rejection=problem.intake_problem)
        else:
            current = self.get(p, connection['id'])
            intent = current.get('credential_write', {})
            if intent.get('id') != connection['credential_write']['id']:
                raise self._changed()
            current.pop('credential_write')
            if current['state'] != 'disconnected':
                current.update(state=current.get('authorization_previous_state', 'needs_authorization')
                    if current.get('secret_ref') else 'needs_authorization', error=problem.intake_problem)
            current.pop('authorization_previous_state', None)
            current['credential_rejected_oauth'] = dict(id=intent['oauth_id'], error=problem.intake_problem)
            self._settle(p, self.service.save(p, 'intake_connection', current))
        raise problem

    def pending(self, p, connection_id, purpose, payload=None):
        id, nonce = str(uuid4()), secrets.token_urlsafe(32)
        doc = dict(id=id, owner_id=p.user_id, collection_id=p.scope.collection_id,
            connection_id=connection_id, purpose=purpose, nonce_hash=hashlib.sha256(nonce.encode()).hexdigest(),
            expires_at=self.clock() + 600, state='pending', sensitive=False, revision=0, **(payload or {}))
        self.service.save(p, 'intake_oauth', doc)
        state = base64.urlsafe_b64encode(json.dumps(dict(id=id, nonce=nonce, user=p.user_id,
            organization=p.scope.organization_id, collection=p.scope.collection_id), separators=(',', ':')).encode()).decode()
        return doc, state

    @staticmethod
    def decode_state(state):
        if len(state) > 2048:
            raise ValueError('Invalid connection session')
        try:
            fields = json.loads(base64.b64decode(state, altchars=b'-_', validate=True))
            if set(fields) != {'id', 'nonce', 'user', 'organization', 'collection'} or not all(isinstance(v, str) for v in fields.values()):
                raise ValueError()
            return fields
        except (ValueError, TypeError):
            raise ValueError('Invalid connection session') from None

    def verify_pending(self, p, state, purpose):
        fields = self.decode_state(state)
        if (fields['user'], fields['organization'], fields['collection']) != (p.user_id, p.scope.organization_id, p.scope.collection_id):
            raise PermissionError('Connection session does not belong to this account')
        doc = self.service.read(p, 'intake_oauth', fields['id'])
        if (doc['purpose'] != purpose or doc['state'] != 'pending' or doc['expires_at'] < self.clock()
            or not hmac.compare_digest(doc['nonce_hash'], hashlib.sha256(fields['nonce'].encode()).hexdigest())):
            raise ValueError('This connection session expired. Start again in the app.')
        return doc

    def connect(self, p, provider, access, session_proof, return_origin=None, reconnect_id=None):
        if not re.fullmatch(r'[a-f0-9]{64}', session_proof):
            raise ValueError('A fresh application session proof is required')
        if provider not in self.config:
            raise ImportProblem('provider_not_configured', 'This provider needs administrator setup. Choose another source for now.', 'administrator', False)
        if access not in {'files', 'folders'} or (provider == 'dropbox' and access != 'folders'):
            raise ValueError('Invalid provider access level')
        config = self.config[provider]
        if reconnect_id:
            connection = self._settle(p, self.get(p, reconnect_id))
            if connection['provider'] != provider or connection['access'] != access:
                raise ValueError('Reconnect must preserve provider and access level')
            if not connection.get('account_id'):
                raise ImportProblem('account_identity_missing', 'Choose a new connection and select these files again.', 'choose_source', False)
            id = reconnect_id
            connection.setdefault('authorization_previous_state', connection['state'])
            connection.update(state='needs_authorization', revocation_complete=False)
        else:
            id = str(uuid4())
            connection = ProviderConnection(id=id, owner_id=p.user_id, collection_id=p.scope.collection_id,
                provider=provider, access=access, state='needs_authorization').model_dump()
        connection = self.service.save(p, 'intake_connection', connection)
        # The app already owns a fresh 256-bit proof and must present it at
        # completion. It is also a valid PKCE verifier; only its hash is stored.
        verifier = session_proof
        native_picker = provider == 'google_drive' and access == 'files' and return_origin is None
        pending, state = self.pending(p, id, 'oauth', {
            'session_hash': hashlib.sha256(session_proof.encode()).hexdigest(), 'return_origin': return_origin,
            'expected_account_id': connection.get('account_id'), 'native_picker': native_picker})
        connection['authorization_id'] = pending['id']
        connection = self.service.save(p, 'intake_connection', connection)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        params = dict(client_id=config['client_id'], redirect_uri=config['redirect_uri'], response_type='code',
            state=state, code_challenge=challenge, code_challenge_method='S256')
        if provider == 'google_drive':
            params.update(scope=GOOGLE_FILE if access == 'files' else GOOGLE_READ,
                          access_type='offline', include_granted_scopes='false', prompt='consent select_account')
            if native_picker:
                params.update(trigger_onepick='true', allow_multiple='true', mimetypes=PICKER_IMAGE_TYPES)
        else:
            params.update(scope=DROPBOX_SCOPES, token_access_type='offline', force_reapprove='true')
        return dict(safe_connection(connection), authorization_url=PROVIDERS[provider][0] + '?' + urlencode(params),
                    **({'picker_id': pending['id']} if native_picker else {}))

    def complete(self, p, state, code, session_proof, error=None, selected_files=''):
        pending = self.verify_pending(p, state, 'oauth')
        if not hmac.compare_digest(pending['session_hash'], hashlib.sha256(session_proof.encode()).hexdigest()):
            raise PermissionError('Return to the application session that began this connection')
        if selected_files and not pending.get('native_picker'):
            raise ValueError('File selection does not belong to this connection session')
        selected_ids = picked_file_ids(selected_files)
        pending['state'] = 'exchanging'
        pending['picked_file_ids'] = selected_ids
        pending = self.service.save(p, 'intake_oauth', pending)  # one use, including lost replies
        connection = self.get(p, pending['connection_id'])
        if connection.get('authorization_id') != pending['id']:
            raise self._changed()
        if connection['state'] == 'disconnected':
            raise ImportProblem('connection_cancelled', 'This connection was cancelled. Start a new connection.', 'connect', False)
        if error:
            blocked = error in {'admin_policy_enforced', 'org_internal'}
            connection.update(state='policy_blocked' if blocked else 'needs_authorization', error=dict(
                code='institution_policy' if blocked else 'authorization_declined',
                message='Your organization prevents this connection. Ask IT to review this app.' if blocked else 'The account was not connected. Try again or choose another source.',
                action='administrator' if blocked else 'connect', retryable=False))
            return self.service.save(p, 'intake_connection', connection)
        if not code or len(code) > 4096:
            raise ValueError('An authorization code is required')
        provider = connection['provider']; config = self.config[provider]
        client_secret = self.secrets.read(config['client_secret_ref'])['client_secret']
        connection = self._begin_write(p, connection, 'connect')
        try:
            response = self.http.post(PROVIDERS[provider][1], data=dict(client_id=config['client_id'], client_secret=client_secret,
                code=code, grant_type='authorization_code', redirect_uri=config['redirect_uri'],
                code_verifier=session_proof), timeout=20)
        except requests.RequestException:
            self._cancel_write(p, connection)
            raise ImportProblem('provider_unavailable', 'The provider could not finish connecting. Connect again.', 'connect', False) from None
        if response.status_code != 200:
            self._cancel_write(p, connection)
            raise oauth_failure(response)
        try:
            token = response.json()
        except ValueError:
            token = None
        if not isinstance(token, dict):
            self._cancel_write(p, connection)
            raise ImportProblem('provider_unavailable', 'The provider did not return usable connection credentials. Connect again.', 'connect', False)
        required = GOOGLE_FILE if connection['access'] == 'files' else GOOGLE_READ
        scopes = set(token['scope'].split()) if isinstance(token.get('scope'), str) else set()
        if (provider == 'google_drive' and (required not in scopes or (pending.get('native_picker') and scopes != {GOOGLE_FILE}))) or (
                provider == 'dropbox' and not set(DROPBOX_SCOPES.split()) <= scopes):
            self._reject_issued(p, connection, token, ImportProblem('scope_declined', 'The requested access was not granted. Connect again and allow the requested access, or choose another source.', 'connect', False))
        if not all(isinstance(token.get(key), str) and token[key] for key in ('access_token', 'refresh_token')):
            self._reject_issued(p, connection, token, ImportProblem('offline_access_required', 'Connect again and allow access so unfinished imports can resume.', 'connect', False))
        try:
            token['expires_at'] = self.clock() + token.get('expires_in', 3600)
            if provider == 'google_drive':
                account = self.http.get('https://www.googleapis.com/drive/v3/about', params={'fields': 'user(emailAddress,displayName,permissionId)'},
                                       headers={'Authorization': 'Bearer ' + token['access_token']}, timeout=15)
            else:
                account = self.http.post('https://api.dropboxapi.com/2/users/get_current_account',
                                         headers={'Authorization': 'Bearer ' + token['access_token']}, timeout=15)
            if account.status_code != 200:
                from .intake_cloud_sources import check_response
                check_response(account, provider)
            info = account.json()
            if provider == 'google_drive':
                info = info.get('user') if isinstance(info, dict) else None
            if not isinstance(info, dict):
                raise ValueError('Invalid provider account metadata')
            account_id, label = ((info.get('permissionId'), info.get('emailAddress', 'Google Drive'))
                if provider == 'google_drive' else (info.get('account_id'), info.get('email', 'Dropbox')))
            if account_id is not None and not isinstance(account_id, str):
                raise ValueError('Invalid provider account identity')
        except ImportProblem as problem:
            self._reject_issued(p, connection, token, problem)
        except (requests.RequestException, ValueError, TypeError):
            self._reject_issued(p, connection, token, ImportProblem('provider_unavailable', 'The provider account could not be checked. Connect again.', 'connect', False))
        if not account_id or (pending.get('expected_account_id') and account_id != pending['expected_account_id']):
            self._reject_issued(p, connection, token, ImportProblem('account_mismatch', 'Reconnect the same provider account to resume these photos. Choose another account as a new connection.', 'connect', False))
        connection = self._persist(p, connection, token, dict(state='connected', account_id=account_id, account_label=label))
        pending = self.service.read(p, 'intake_oauth', pending['id'])
        if pending['state'] == 'exchanging':
            pending['state'] = 'authorized'
            self.service.save(p, 'intake_oauth', pending)
        return connection

    def token(self, p, id):
        connection = self._settle(p, self.get(p, id))
        if connection['state'] != 'connected':
            raise ImportProblem('authorization_required', 'Connect this account again to continue.', 'connect', False)
        value = self.secrets.read(connection['secret_ref'])
        if value['expires_at'] > self.clock() + 60:
            self.service.authorize(p)
            self.service.save(p, 'intake_connection', connection)
            return value['access_token']
        config = self.config[connection['provider']]
        client_secret = self.secrets.read(config['client_secret_ref'])['client_secret']
        connection = self._begin_write(p, connection, 'refresh')
        try:
            response = self.http.post(PROVIDERS[connection['provider']][1], data=dict(
                client_id=config['client_id'], client_secret=client_secret,
                grant_type='refresh_token', refresh_token=value['refresh_token']), timeout=20)
        except requests.RequestException:
            self._cancel_write(p, connection)
            raise ImportProblem('provider_unavailable', 'The provider could not refresh this connection. Retry shortly.') from None
        if response.status_code != 200:
            problem = oauth_failure(response, refreshing=True)
            self._cancel_write(p, connection, state='needs_authorization' if problem.intake_problem['code'] == 'authorization_expired' else None)
            raise problem
        fresh = response.json()
        if not isinstance(fresh, dict) or not isinstance(fresh.get('access_token'), str) or not fresh['access_token']:
            self._cancel_write(p, connection)
            raise ImportProblem('provider_unavailable', 'The provider did not return a usable connection token. Retry shortly.')
        value.update(fresh, expires_at=self.clock() + fresh.get('expires_in', 3600))
        connection = self._persist(p, connection, value, dict(state='connected'))
        self.service.authorize(p)
        self.service.save(p, 'intake_connection', connection)
        return value['access_token']

    def _revoke(self, provider, token):
        access = token.get('access_token') if isinstance(token.get('access_token'), str) else None
        refresh = token.get('refresh_token') if isinstance(token.get('refresh_token'), str) else None
        if not access and not refresh:
            return False
        try:
            if provider == 'google_drive':
                response = self.http.post('https://oauth2.googleapis.com/revoke',
                    data={'token': refresh or access}, timeout=15)
                if response.status_code == 400 and refresh:
                    try:
                        body = response.json()
                    except ValueError:
                        body = None
                    if isinstance(body, dict) and body.get('error') == 'invalid_token':
                        return True
            else:
                response = self.http.post('https://api.dropboxapi.com/2/auth/token/revoke',
                    headers={'Authorization': 'Bearer ' + access}, timeout=15) if access else None
                if refresh and (response is None or response.status_code == 401):
                    # Expired Dropbox access is not proof of refresh-token revocation.
                    config = self.config[provider]
                    fresh = self.http.post(PROVIDERS[provider][1], data=dict(
                        client_id=config['client_id'], client_secret=self.secrets.read(config['client_secret_ref'])['client_secret'],
                        grant_type='refresh_token', refresh_token=refresh), timeout=20)
                    if fresh.status_code == 400 and fresh.json().get('error') == 'invalid_grant':
                        return True  # A prior successful revoke may have lost its reply.
                    if fresh.status_code != 200 or not fresh.json().get('access_token'):
                        return False
                    response = self.http.post('https://api.dropboxapi.com/2/auth/token/revoke',
                        headers={'Authorization': 'Bearer ' + fresh.json()['access_token']}, timeout=15)
            return response is not None and response.status_code == 200
        except requests.RequestException:
            # Keep the durable revocation claim until its conservative retry
            # boundary; a missing reply is not permission for duplicate revokers.
            raise self._revocation_pending() from None

    def disconnect(self, p, id):
        connection = self.get(p, id)
        connection['state'] = 'disconnected'
        connection = self.service.save(p, 'intake_connection', connection)
        try:
            connection = self._settle(p, connection)
            complete = not connection.get('credential_write') and not connection.get('credential_retirements')
        except ImportProblem:
            connection = self.get(p, id)
            complete = False
        connection.update(revocation_complete=complete, error=None if complete else dict(
            code='revocation_pending', message='Disconnected here. Retry disconnect to revoke access at the provider.',
            action='retry', retryable=True))
        self.service.save(p, 'intake_connection', connection)
        return safe_connection(connection)
