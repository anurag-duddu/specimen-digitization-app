"""Read-only Google Drive and Dropbox adapters with version-bound downloads."""
import json
import base64
import time
import re
from urllib.parse import quote, urlsplit, parse_qs
from .intake_sources import ImportProblem, public_url
from .intake_models import MAX_BYTES
from .source_reader import sniff_media_type

IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/tiff', 'image/heic', 'image/heif', 'image/dng', 'image/x-adobe-dng'}
EXTENSIONS = ('.jpg', '.jpeg', '.png', '.tif', '.tiff', '.heic', '.heif', '.dng')


def drive_ref(value):
    parts = value.split(':') if value.startswith('gdrive:') else ['', value, '']
    if len(parts) != 3 or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', parts[1]) or not re.fullmatch(r'[A-Za-z0-9_-]{0,200}', parts[2]):
        raise ValueError('Invalid Drive file')
    return parts[1], ({'X-Goog-Drive-Resource-Keys': parts[1] + '/' + parts[2]} if parts[2] else {})


def shared_ref(url, path=''):
    public_url(url)
    if urlsplit(url).hostname not in {'dropbox.com', 'www.dropbox.com'}:
        raise ValueError('Use a Dropbox shared link')
    encoded = 'dbx:' + base64.urlsafe_b64encode(json.dumps([url, path], separators=(',', ':')).encode()).decode()
    if len(encoded) > 2048:
        raise ValueError('This shared link is too long. Choose the file through Dropbox instead.')
    return encoded


def shared_parts(value):
    if not value.startswith('dbx:'):
        return None
    try:
        parts = json.loads(base64.b64decode(value[4:], altchars=b'-_', validate=True))
        if not isinstance(parts, list) or len(parts) != 2 or not all(isinstance(p, str) for p in parts):
            raise ValueError()
        url, path = parts
        if any(p in {'.', '..'} for p in path.split('/')) or any(ord(c) < 32 for c in path):
            raise ValueError()
        shared_ref(url, path)
        return url, path
    except (ValueError, TypeError):
        raise ValueError('Invalid shared link selection') from None


def check_response(response, provider):
    status = response.status_code
    if 200 <= status < 300:
        return
    # Structured reasons distinguish institutional policy from file access.
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    if provider == 'google_drive':
        error = body.get('error', {})
        reasons = {e.get('reason') for e in error.get('errors', []) if isinstance(e, dict)} if isinstance(error, dict) else set()
        if isinstance(error, dict):
            reasons.update(detail.get('reason') for detail in error.get('details', []) if isinstance(detail, dict))
    else:
        reasons = {body.get('error', {}).get('.tag')} if isinstance(body.get('error'), dict) else set()
    if status == 401:
        raise ImportProblem('authorization_expired', 'Connect this account again to continue.', 'connect', False)
    if 'domainPolicy' in reasons:
        raise ImportProblem('institution_policy', 'Your organization blocks this operation. Ask IT to review this app.', 'administrator', False)
    if reasons & {'accessNotConfigured', 'SERVICE_DISABLED', 'API_KEY_INVALID', 'API_KEY_SERVICE_BLOCKED', 'API_KEY_HTTP_REFERRER_BLOCKED'}:
        raise ImportProblem('provider_configuration', 'This connection needs application setup. Ask your administrator to check the provider configuration.', 'administrator', False)
    if reasons & {'insufficientPermissions', 'ACCESS_TOKEN_SCOPE_INSUFFICIENT', 'missing_scope'}:
        raise ImportProblem('connection_permissions', 'This account connection is missing the required access. Connect again and allow the requested permissions.', 'connect', False)
    if status == 429 or reasons & {'rateLimitExceeded', 'userRateLimitExceeded'}:
        error = ImportProblem('rate_limited', 'The provider is busy. This transfer will retry shortly.')
        retry = response.headers.get('Retry-After', '30')
        error.intake_problem['retry_after'] = min(3600, max(1, int(retry))) if retry.isdecimal() else 30
        raise error
    if status in {403, 404, 409}:
        raise ImportProblem('file_access', 'This file is unavailable or cannot be downloaded. Check the account and file permissions.', 'file_access', False)
    raise ImportProblem('provider_unavailable', 'The provider could not finish this request. Retry shortly.')


class CloudSource:
    def __init__(self, manager, provider):
        self.manager, self.provider = manager, provider

    def connection(self, p, id, *, folders=False):
        doc = self.manager.get(p, id, connected=True)
        if doc['provider'] != self.provider:
            raise ValueError('The connection belongs to a different provider')
        if folders and doc['access'] != 'folders':
            raise ImportProblem('folder_access_required', 'Folder browsing needs additional read-only access. Connect folder access or choose individual files.', 'connect', False)
        return doc

    def validate(self, p, source):
        self.connection(p, source.connection_id)
        if not source.object_id or not source.version:
            raise ValueError('Select a current provider file before adding it')
        if self.provider == 'google_drive':
            drive_ref(source.object_id)
        else:
            shared_parts(source.object_id)

    def request(self, p, connection_id, method, path, *, content=False, timeout=20, **kwargs):
        self.connection(p, connection_id)
        headers = dict(kwargs.pop('headers', {}), Authorization='Bearer ' + self.manager.token(p, connection_id))
        base = 'https://www.googleapis.com/drive/v3/' if self.provider == 'google_drive' else (
            'https://content.dropboxapi.com/2/' if content else 'https://api.dropboxapi.com/2/')
        response = self.manager.http.request(method, base + path, headers=headers,
            timeout=timeout, allow_redirects=False, **kwargs)
        check_response(response, self.provider)
        return response

    def row(self, connection_id, raw, locator=None):
        google = self.provider == 'google_drive'
        folder = raw.get('mimeType') == 'application/vnd.google-apps.folder' if google else raw.get('.tag') == 'folder'
        id = locator or (raw.get('id') if google else raw.get('path_lower', raw.get('id')))
        if google and raw.get('resourceKey') and locator is None:
            id = 'gdrive:' + id + ':' + raw['resourceKey']
        name = raw.get('name', 'Photo')
        supported = not folder and (raw.get('mimeType') in IMAGE_TYPES if google else name.lower().endswith(EXTENSIONS))
        downloadable = raw.get('capabilities', {}).get('canDownload', True) if google else raw.get('is_downloadable', True)
        supported = supported and downloadable
        return dict(id=id, filename=name, kind='folder' if folder else 'file', supported=supported, inaccessible=not downloadable,
            media_type=raw.get('mimeType', 'application/octet-stream'), connection_id=connection_id,
            error=None if folder or supported else 'Download access is required.' if not downloadable else 'Unsupported file type.',
            source=dict(provider=self.provider, connection_id=connection_id, object_id=id,
                        version=str(raw.get('version', raw.get('rev', ''))) if not folder else None))

    def metadata(self, p, connection_id, object_id, *, timeout=20):
        if self.provider == 'google_drive':
            object_id, headers = drive_ref(object_id)
            return self.request(p, connection_id, 'GET', 'files/' + object_id, headers=headers, timeout=timeout,
                params={'fields': 'id,name,mimeType,version,size,resourceKey,capabilities(canDownload,canListChildren)', 'supportsAllDrives': 'true'}).json()
        shared = shared_parts(object_id)
        if shared:
            return self.request(p, connection_id, 'POST', 'sharing/get_shared_link_metadata', timeout=timeout,
                json={'url': shared[0], **({'path': shared[1]} if shared[1] else {})}).json()
        return self.request(p, connection_id, 'POST', 'files/get_metadata', json={'path': object_id}, timeout=timeout).json()

    def browse(self, p, connection_id, folder='', cursor=None, recursive=False):
        self.connection(p, connection_id, folders=True)
        if self.provider == 'google_drive':
            folder = folder or 'root'
            locator = folder
            folder, headers = drive_ref(folder)
            if folder != 'root':
                metadata = self.metadata(p, connection_id, locator)
                if not metadata.get('capabilities', {}).get('canListChildren', True):
                    raise ImportProblem('folder_access', 'This folder does not allow listing its contents.', 'file_access', False)
            result = self.request(p, connection_id, 'GET', 'files', headers=headers, params={
                'q': f"'{folder}' in parents and trashed=false", 'pageSize': 100,
                'fields': 'nextPageToken,incompleteSearch,files(id,name,mimeType,version,size,resourceKey,capabilities(canDownload))',
                'supportsAllDrives': 'true', 'includeItemsFromAllDrives': 'true',
                **({'pageToken': cursor} if cursor else {}),
            }).json()
            return dict(items=[self.row(connection_id, row) for row in result.get('files', [])],
                next_cursor=result.get('nextPageToken'), message='Some locations could not be searched. Select a specific folder.' if result.get('incompleteSearch') else None)
        path = 'files/list_folder/continue' if cursor else 'files/list_folder'
        shared = shared_parts(folder)
        body = {'cursor': cursor} if cursor else {'path': shared[1] if shared else folder, 'recursive': recursive if not shared else False, 'limit': 100, 'include_non_downloadable_files': True,
            **({'shared_link': {'url': shared[0]}} if shared else {})}
        result = self.request(p, connection_id, 'POST', path, json=body).json()
        return dict(items=[self.row(connection_id, row, shared_ref(shared[0], row.get('path_lower') or shared[1].rstrip('/') + '/' + row['name']) if shared else None) for row in result.get('entries', [])],
                    next_cursor=result['cursor'] if result.get('has_more') else None)

    def select_folder(self, p, connection_id, folder, recursive, limit):
        pending, seen, rows, unsupported, inaccessible, discovered = [folder], set(), [], 0, 0, 0
        while pending:
            current = pending.pop(0)
            if current in seen:
                continue
            seen.add(current)
            if len(seen) > 500:
                raise ImportProblem('folder_limit', 'This folder contains too many subfolders. Select a smaller folder.', 'choose_source', False)
            cursor = None
            while True:
                try:
                    page = self.browse(p, connection_id, current, cursor)
                except ImportProblem as exc:
                    if exc.intake_problem['code'] in {'folder_access', 'file_access'}:
                        inaccessible += 1
                        break
                    raise
                if page.get('message'):
                    raise ImportProblem('incomplete_search', page['message'], 'choose_source', False)
                for row in page['items']:
                    if row['kind'] == 'folder':
                        if recursive: pending.append(row['id'])
                        continue
                    discovered += 1
                    if row['supported']: rows.append(row)
                    elif row.get('inaccessible'): inaccessible += 1
                    else: unsupported += 1
                    if len(rows) > limit or discovered > 5000:
                        raise ImportProblem('selection_limit', 'This selection exceeds the batch limit. Choose fewer files or a smaller folder.', 'choose_source', False)
                cursor = page.get('next_cursor')
                if not cursor: break
        return dict(items=rows, discovered=discovered, unsupported=unsupported, inaccessible=inaccessible)

    def read(self, p, source):
        self.validate(p, source)
        before = self.metadata(p, source.connection_id, source.object_id)
        version = str(before.get('version', before.get('rev', '')))
        if version != source.version:
            raise ImportProblem('source_changed', 'This photo changed after selection. Select its current version again.', 'choose_source', False)
        if self.provider == 'google_drive':
            object_id, headers = drive_ref(source.object_id)
            response = self.request(p, source.connection_id, 'GET', 'files/' + object_id, headers=headers,
                params={'alt': 'media', 'supportsAllDrives': 'true'}, stream=True)
        else:
            shared = shared_parts(source.object_id)
            args = {'url': shared[0], **({'path': shared[1]} if shared[1] else {})} if shared else {'path': 'rev:' + source.version}
            response = self.request(p, source.connection_id, 'POST', 'sharing/get_shared_link_file' if shared else 'files/download', content=True,
                headers={'Dropbox-API-Arg': json.dumps(args)}, stream=True)
        data = bytearray()
        deadline = time.monotonic() + 60
        try:
            for block in response.iter_content(65536):
                if time.monotonic() > deadline:
                    raise ImportProblem('transfer_timeout', 'This download took too long. Retry the photo.')
                data.extend(block)
                if len(data) > MAX_BYTES:
                    raise ImportProblem('image_too_large', 'Photos must be 25 MB or smaller.', 'choose_source', False)
        finally:
            response.close()
        after = self.metadata(p, source.connection_id, source.object_id)
        if str(after.get('version', after.get('rev', ''))) != source.version:
            raise ImportProblem('source_changed', 'This photo changed during download. Select it again.', 'choose_source', False)
        return bytes(data), sniff_media_type(bytes(data))

    def resolve(self, p, connection_id, value):
        url = urlsplit(value)
        if self.provider == 'google_drive':
            parts = url.path.split('/')
            id = parse_qs(url.query).get('id', [None])[0]
            for marker in ('d', 'folders'):
                if marker in parts and len(parts) > parts.index(marker) + 1:
                    id = parts[parts.index(marker) + 1]
            if not id: raise ValueError('Use a Drive file or folder link')
            key = parse_qs(url.query).get('resourcekey', [''])[0]
            locator = 'gdrive:' + id + ':' + key if key else id
            return self.row(connection_id, self.metadata(p, connection_id, locator), locator)
        locator = shared_ref(value)
        return self.row(connection_id, self.metadata(p, connection_id, locator), locator)
