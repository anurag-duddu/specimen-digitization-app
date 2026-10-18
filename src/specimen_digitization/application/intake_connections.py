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
        doc = self.service.read(p, 'intake_connection', id)
        if connected and doc['state'] != 'connected':
            raise ImportProblem('authorization_required', 'Connect this account again to continue.', 'connect', False)
        return doc

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
            connection = self.get(p, reconnect_id)
            if connection['provider'] != provider or connection['access'] != access:
                raise ValueError('Reconnect must preserve provider and access level')
            if not connection.get('account_id'):
                raise ImportProblem('account_identity_missing', 'Choose a new connection and select these files again.', 'choose_source', False)
            id = reconnect_id
            connection.update(state='needs_authorization', revocation_complete=False)
        else:
            id = str(uuid4())
            connection = ProviderConnection(id=id, owner_id=p.user_id, collection_id=p.scope.collection_id,
                provider=provider, access=access, state='needs_authorization').model_dump()
        connection = self.service.save(p, 'intake_connection', connection)
        verifier = secrets.token_urlsafe(64)
        verifier_ref = self.secrets.write(str(uuid4()), {'verifier': verifier})
        native_picker = provider == 'google_drive' and access == 'files' and return_origin is None
        pending, state = self.pending(p, id, 'oauth', {'verifier_ref': verifier_ref,
            'session_hash': hashlib.sha256(session_proof.encode()).hexdigest(), 'return_origin': return_origin,
            'expected_account_id': connection.get('account_id'), 'native_picker': native_picker})
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
        try:
            response = self.http.post(PROVIDERS[provider][1], data=dict(client_id=config['client_id'], client_secret=client_secret,
                code=code, grant_type='authorization_code', redirect_uri=config['redirect_uri'],
                code_verifier=self.secrets.read(pending['verifier_ref'])['verifier']), timeout=20)
        except requests.RequestException:
            raise ImportProblem('provider_unavailable', 'The provider could not finish connecting. Connect again.', 'connect', False) from None
        if response.status_code != 200:
            raise oauth_failure(response)
        token = response.json()
        required = GOOGLE_FILE if connection['access'] == 'files' else GOOGLE_READ
        scopes = set(token.get('scope', '').split())
        if (provider == 'google_drive' and (required not in scopes or (pending.get('native_picker') and scopes != {GOOGLE_FILE}))) or (
                provider == 'dropbox' and not set(DROPBOX_SCOPES.split()) <= scopes):
            self._revoke(provider, token)
            raise ImportProblem('scope_declined', 'The requested access was not granted. Connect again and allow the requested access, or choose another source.', 'connect', False)
        if not token.get('refresh_token') or not token.get('access_token'):
            raise ImportProblem('offline_access_required', 'Connect again and allow access so unfinished imports can resume.', 'connect', False)
        token['expires_at'] = self.clock() + token.get('expires_in', 3600)
        if provider == 'google_drive':
            account = self.http.get('https://www.googleapis.com/drive/v3/about', params={'fields': 'user(emailAddress,displayName,permissionId)'},
                                   headers={'Authorization': 'Bearer ' + token['access_token']}, timeout=15)
            if account.status_code != 200:
                self._revoke(provider, token)
                from .intake_cloud_sources import check_response
                check_response(account, provider)
            info = account.json().get('user', {})
            account_id, label = info.get('permissionId'), info.get('emailAddress', 'Google Drive')
        else:
            account = self.http.post('https://api.dropboxapi.com/2/users/get_current_account',
                                     headers={'Authorization': 'Bearer ' + token['access_token']}, timeout=15)
            if account.status_code != 200:
                self._revoke(provider, token)
                from .intake_cloud_sources import check_response
                check_response(account, provider)
            info = account.json()
            account_id, label = info.get('account_id'), info.get('email', 'Dropbox')
        if not account_id or (pending.get('expected_account_id') and account_id != pending['expected_account_id']):
            self._revoke(provider, token)
            raise ImportProblem('account_mismatch', 'Reconnect the same provider account to resume these photos. Choose another account as a new connection.', 'connect', False)
        connection.update(secret_ref=self.secrets.write(connection['id'], token), state='connected', account_id=account_id, account_label=label)
        connection.pop('error', None)
        try:
            connection = self.service.save(p, 'intake_connection', connection)
        except Conflict:
            self._revoke(provider, token)
            raise ImportProblem('connection_changed', 'The connection changed. Connect again.', 'connect', False) from None
        pending['state'] = 'authorized'
        self.service.save(p, 'intake_oauth', pending)
        return connection

    def token(self, p, id):
        connection = self.get(p, id, connected=True)
        value = self.secrets.read(connection['secret_ref'])
        if value['expires_at'] > self.clock() + 60:
            return value['access_token']
        config = self.config[connection['provider']]
        response = self.http.post(PROVIDERS[connection['provider']][1], data=dict(
            client_id=config['client_id'], client_secret=self.secrets.read(config['client_secret_ref'])['client_secret'],
            grant_type='refresh_token', refresh_token=value['refresh_token']), timeout=20)
        if response.status_code != 200:
            problem = oauth_failure(response, refreshing=True)
            if problem.intake_problem['code'] == 'authorization_expired':
                connection['state'] = 'needs_authorization'
                self.service.save(p, 'intake_connection', connection)
            raise problem
        fresh = response.json()
        if not isinstance(fresh, dict) or not isinstance(fresh.get('access_token'), str) or not fresh['access_token']:
            raise ImportProblem('provider_unavailable', 'The provider did not return a usable connection token. Retry shortly.')
        value.update(fresh, expires_at=self.clock() + fresh.get('expires_in', 3600))
        connection['secret_ref'] = self.secrets.write(id, value)
        try:
            self.service.save(p, 'intake_connection', connection)
        except Conflict:
            # Disconnect may have won while the provider refreshed credentials.
            # Never return that token to an in-flight download.
            if self.get(p, id)['state'] == 'disconnected':
                self._revoke(connection['provider'], value)
            raise ImportProblem('connection_changed', 'The connection changed. Reconnect or retry.', 'connect', False) from None
        return value['access_token']

    def _revoke(self, provider, token):
        if not token.get('access_token'):
            return False
        try:
            if provider == 'google_drive':
                response = self.http.post('https://oauth2.googleapis.com/revoke',
                    data={'token': token.get('refresh_token', token['access_token'])}, timeout=15)
            else:
                response = self.http.post('https://api.dropboxapi.com/2/auth/token/revoke',
                    headers={'Authorization': 'Bearer ' + token['access_token']}, timeout=15)
                if response.status_code == 401 and token.get('refresh_token'):
                    # Expired Dropbox access is not proof of refresh-token revocation.
                    config = self.config[provider]
                    fresh = self.http.post(PROVIDERS[provider][1], data=dict(
                        client_id=config['client_id'], client_secret=self.secrets.read(config['client_secret_ref'])['client_secret'],
                        grant_type='refresh_token', refresh_token=token['refresh_token']), timeout=20)
                    if fresh.status_code != 200 or not fresh.json().get('access_token'):
                        return False
                    response = self.http.post('https://api.dropboxapi.com/2/auth/token/revoke',
                        headers={'Authorization': 'Bearer ' + fresh.json()['access_token']}, timeout=15)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def disconnect(self, p, id):
        connection = self.get(p, id)
        if connection['state'] == 'disconnected' and connection.get('revocation_complete'):
            return safe_connection(connection)
        connection['state'] = 'disconnected'
        connection = self.service.save(p, 'intake_connection', connection)
        try:
            token = self.secrets.read(connection['secret_ref']) if connection.get('secret_ref') else None
            complete = token is None or self._revoke(connection['provider'], token)
        except ImportProblem:
            complete = False
        connection.update(revocation_complete=complete, error=None if complete else dict(
            code='revocation_pending', message='Disconnected here. Retry disconnect to revoke access at the provider.',
            action='retry', retryable=True))
        self.service.save(p, 'intake_connection', connection)
        return safe_connection(connection)
