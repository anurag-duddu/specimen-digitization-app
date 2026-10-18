"""Connection, picker, and source browsing routes shared by web and native apps."""
import html
import json
import base64
import io
import tempfile
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import urlsplit, urlencode
from uuid import uuid4
from fastapi import Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import Field

from .domain import Record
from .intake_connections import safe_connection, picked_file_ids, PICKER_IMAGE_TYPES
from .intake_sources import ImportProblem, public_url
from .source_registry import validate_object_name
from .source_reader import SourceListingIncomplete
from .intake_cloud_sources import EXTENSIONS
from .intake_models import SourceReference, MAX_BYTES


class ConnectionInput(Record):
    provider: str
    access: str
    session_proof: str = Field(pattern=r'^[a-f0-9]{64}$')
    return_origin: str | None = None
    reconnect_id: str | None = Field(default=None, max_length=200)


class ConnectionComplete(Record):
    state: str = Field(max_length=2048)
    code: str = Field(default='', max_length=4096)
    error: str | None = Field(default=None, max_length=200)
    session_proof: str = Field(pattern=r'^[a-f0-9]{64}$')
    picked_file_ids: str = Field(default='', max_length=100499)


class BrowseInput(Record):
    folder: str = Field(default='', max_length=4096)
    cursor: str | None = Field(default=None, max_length=8192)
    recursive: bool = False
    limit: int = Field(default=500, ge=1, le=500)


class LinkInput(Record):
    url: str = Field(min_length=1, max_length=4096)
    connection_id: str | None = Field(default=None, max_length=200)


class PickerBootstrap(Record):
    state: str = Field(max_length=2048)


class PickerInput(Record):
    state: str = Field(max_length=2048)
    ids: list[str] = Field(min_length=1, max_length=500)


def install_source_routes(app, prefix, service, manager, *, identity, principal, origins=()):
    root = prefix + '/collections/{collection_id}/intake'

    def access(org, collection, user):
        return principal(user, org, collection, write=True)

    def provider(p, id):
        if manager is None:
            raise ImportProblem('provider_not_configured', 'Cloud connections need administrator setup.', 'administrator', False)
        doc = manager.get(p, id, connected=True)
        return service.sources.providers[doc['provider']]

    def selection_rows(p, connection_id, ids):
        adapter = provider(p, connection_id)
        rows, failures = [], []
        for id in dict.fromkeys(ids):
            try:
                rows.append(adapter.row(connection_id, adapter.metadata(p, connection_id, id)))
            except ImportProblem as exc:
                failures.append(dict(id=id, error=exc.intake_problem))
        return dict(items=rows, failures=failures)

    def native_selection(p, pending):
        # An authenticated completion retains the IDs before exchange. Polling
        # can finish metadata validation after a lost completion reply.
        if pending['state'] == 'authorized':
            pending.update(selection_rows(p, pending['connection_id'], pending['picked_file_ids']), state='selected')
            pending = service.save(p, 'intake_oauth', pending)
        return dict(state=pending['state'], items=pending.get('items', []), failures=pending.get('failures', []))

    @app.post(root + '/source-preview')
    def source_preview(organization_id: str, collection_id: str, body: SourceReference, user=Depends(identity)):
        from PIL import Image
        from .storage import LocalBlobs
        from .intake_image import verify_photo
        p = access(organization_id, collection_id, user)
        service.classify(p, service.sources.required_sensitive(p, body))
        content, media_type = service.sources.read(p, body.model_dump())
        if not content or len(content) > MAX_BYTES:
            raise ValueError('Photo exceeds the image size limit')
        # One explicitly requested preview, with the same codec/pixel limits as
        # staging. Temporary private bytes are removed without creating a draft.
        with tempfile.TemporaryDirectory(prefix='intake-preview-') as directory:
            blobs = LocalBlobs(Path(directory))
            asset = verify_photo(content, dict(media_type=media_type, width=None, height=None), blobs, service.codec_policy)
            with Image.open(io.BytesIO(blobs.get(asset['view_derivative']['blob_ref']))) as image:
                image.thumbnail((800, 800))
                out = io.BytesIO()
                image.convert('RGB').save(out, format='JPEG', quality=85)
            return JSONResponse(dict(image=base64.b64encode(out.getvalue()).decode(), media_type='image/jpeg'), headers={'Cache-Control': 'private, no-store'})

    @app.get(root + '/connections')
    def connections(organization_id: str, collection_id: str, provider: str, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        rows, cursor = [], ''
        while True:
            page = service.list(p, 'intake_connection', after=cursor, limit=100)
            rows.extend(page['items'])
            cursor = page['next_cursor']
            if not cursor:
                break
        return dict(configured=manager is not None and provider in manager.config,
                    items=[safe_connection(row) for row in rows if row['provider'] == provider])

    @app.post(root + '/connections')
    def connect(organization_id: str, collection_id: str, body: ConnectionInput, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        if manager is None:
            raise ImportProblem('provider_not_configured', 'Cloud connections need administrator setup. Choose files or camera for now.', 'administrator', False)
        if body.return_origin is not None and body.return_origin not in origins:
            raise PermissionError('Unknown application origin')
        return manager.connect(p, body.provider, body.access, body.session_proof, body.return_origin, body.reconnect_id)

    @app.post(root + '/connections/complete')
    def complete_connection(organization_id: str, collection_id: str, body: ConnectionComplete, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        if manager is None:
            raise ImportProblem('provider_not_configured', 'Cloud connections need administrator setup.', 'administrator', False)
        connection = manager.complete(p, body.state, body.code, body.session_proof, body.error, body.picked_file_ids)
        result = safe_connection(connection)
        pending = service.read(p, 'intake_oauth', manager.decode_state(body.state)['id'])
        if pending.get('native_picker') and connection['state'] == 'connected':
            result['selection'] = native_selection(p, pending)
        return result

    @app.get(root + '/connections/{connection_id}')
    def connection(organization_id: str, collection_id: str, connection_id: str, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        return safe_connection(service.read(p, 'intake_connection', connection_id))

    @app.post(root + '/connections/{connection_id}/disconnect')
    def disconnect(organization_id: str, collection_id: str, connection_id: str, user=Depends(identity)):
        if manager is None:
            raise ImportProblem('provider_not_configured', 'Cloud connections need administrator setup.', 'administrator', False)
        return manager.disconnect(access(organization_id, collection_id, user), connection_id)

    @app.post(root + '/connections/{connection_id}/browse')
    def browse(organization_id: str, collection_id: str, connection_id: str, body: BrowseInput, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        return provider(p, connection_id).browse(p, connection_id, body.folder, body.cursor)

    @app.post(root + '/connections/{connection_id}/select-folder')
    def select_folder(organization_id: str, collection_id: str, connection_id: str, body: BrowseInput, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        return provider(p, connection_id).select_folder(p, connection_id, body.folder, body.recursive, body.limit)

    @app.get(root + '/sources')
    def sources(organization_id: str, collection_id: str, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        rows = []
        for s in service.sources.registry.for_collections([p.scope.collection_id]):
            try:
                service.classify(p, s.sensitive)
            except PermissionError:
                continue
            rows.append(dict(id=s.source_id, label=f'{s.bucket}/{s.prefix}', sensitive=s.sensitive))
        return dict(items=rows)

    def storage_rows(p, source_id, folder, recursive):
        source = service.sources.registry.get(source_id, [p.scope.collection_id])
        service.classify(p, source.sensitive)
        path = folder or source.prefix
        if path != source.prefix:
            validate_object_name(source, path)
        if not path.endswith('/'):
            raise ValueError('Choose a registered folder')
        try:
            rows = service.sources.storage.list_objects(source.bucket, path, 5000)
        except SourceListingIncomplete as exc:
            raise ImportProblem('incomplete_search', 'Could not list every file in this folder. Choose a smaller folder or try again.', 'choose_source', False) from exc
        if len(rows) > 5000:
            raise ImportProblem('folder_limit', 'Choose a smaller folder to review all of its contents.', 'choose_source', False)
        result, folders = [], set()
        for row in rows:
            name = row['object_name']; relative = name[len(path):]
            if not recursive and '/' in relative:
                folder_path = path + relative.split('/')[0] + '/'
                if folder_path not in folders:
                    folders.add(folder_path)
                    result.append(dict(id=folder_path, kind='folder', filename=relative.split('/')[0], source_id=source_id))
                continue
            formats = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.tif': 'image/tiff', '.tiff': 'image/tiff'}
            supported = formats.get(PurePosixPath(name).suffix.lower()) in source.media_types
            result.append(dict(id=name, kind='file', filename=PurePosixPath(name).name, supported=supported,
                photo_sensitive=source.sensitive,
                error=None if supported else 'Unsupported file type.',
                source=dict(provider='storage', source_id=source_id, object_id=name, version=row['generation'])))
        return result

    @app.post(root + '/sources/{source_id}/browse')
    def browse_storage(organization_id: str, collection_id: str, source_id: str, body: BrowseInput, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        rows = storage_rows(p, source_id, body.folder, False)
        offset = int(body.cursor or 0)
        if offset < 0: raise ValueError('Invalid page')
        return dict(items=rows[offset:offset + 100], next_cursor=str(offset + 100) if offset + 100 < len(rows) else None)

    @app.post(root + '/sources/{source_id}/select-folder')
    def select_storage(organization_id: str, collection_id: str, source_id: str, body: BrowseInput, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        rows = [row for row in storage_rows(p, source_id, body.folder, body.recursive) if row['kind'] == 'file']
        supported = [row for row in rows if row['supported']]
        if len(supported) > body.limit:
            raise ImportProblem('selection_limit', 'This folder exceeds the batch limit. Choose fewer files.', 'choose_source', False)
        return dict(items=supported, discovered=len(rows), unsupported=len(rows) - len(supported), inaccessible=0)

    @app.post(root + '/resolve')
    def resolve(organization_id: str, collection_id: str, body: LinkInput, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        url = urlsplit(body.url)
        if url.scheme == 'gs':
            for source in service.sources.registry.for_collections([collection_id]):
                path = url.path.lstrip('/')
                if url.netloc != source.bucket or not path.startswith(source.prefix): continue
                service.classify(p, source.sensitive)
                if path.endswith('/'):
                    return dict(items=[dict(id=path, kind='folder', filename=path, source_id=source.source_id)])
                validate_object_name(source, path)
                version = service.sources.storage.current_generation(source.bucket, path)
                return dict(items=[dict(id=path, filename=PurePosixPath(path).name, kind='file', supported=path.lower().endswith(EXTENSIONS),
                    source=dict(provider='storage', source_id=source.source_id, object_id=path, version=version))])
            raise ImportProblem('unregistered_source', 'This storage location is not registered for this collection.', 'administrator', False)
        public_url(body.url)
        name = 'google_drive' if url.hostname in {'drive.google.com', 'docs.google.com'} else 'dropbox' if url.hostname in {'dropbox.com', 'www.dropbox.com'} else None
        if name:
            candidates, cursor = [], ''
            while True:
                page = service.list(p, 'intake_connection', after=cursor, limit=100)
                candidates.extend(row for row in page['items'] if row['provider'] == name and row['state'] == 'connected')
                cursor = page['next_cursor']
                if not cursor: break
            if body.connection_id:
                candidates = [row for row in candidates if row['id'] == body.connection_id]
            if not candidates:
                raise ImportProblem('connect_provider', 'Connect this provider from Add photos, then review the link again.', 'connect', False)
            if len(candidates) != 1:
                raise ImportProblem('choose_account', 'Choose the account to use for this provider link.', 'choose_account', False)
            connection_id = candidates[0]['id']
            return dict(items=[provider(p, connection_id).resolve(p, connection_id, body.url)])
        return dict(items=[dict(id=body.url, filename=PurePosixPath(url.path).name or 'Linked photo', supported=True, kind='file',
            source=dict(provider='url', url=body.url))])

    if manager is None:
        return

    def state_principal(state):
        fields = manager.decode_state(state)
        return access(fields['organization'], fields['collection'], fields['user'])

    @app.get('/v1/intake/oauth/callback', response_class=HTMLResponse)
    def callback(state: str, code: str = '', error: str | None = None, picked_file_ids: str = ''):
        p = state_principal(state)
        pending = manager.verify_pending(p, state, 'oauth')
        if len(code) > 4096 or (error and len(error) > 200):
            raise ValueError('Invalid connection response')
        if picked_file_ids and (not pending.get('native_picker') or len(picked_file_ids) > 100499):
            raise ValueError('Unexpected file selection')
        # Validate callback syntax without treating a redirect as authorization.
        from .intake_connections import picked_file_ids as parse_picked_files
        parse_picked_files(picked_file_ids)
        payload = dict(state=state, code=code, error=error,
            **({'picked_file_ids': picked_file_ids} if pending.get('native_picker') else {}))
        headers = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'}
        # This endpoint never exchanges or stores the code. Only its original
        # application window/device receives it and can prove the initiating
        # session in an authenticated completion request. Forwarding an OAuth
        # authorization URL cannot attach a bystander's account to its sender.
        if pending.get('return_origin') is None:
            return RedirectResponse('specimenintake://oauth/callback#' + urlencode({k: v for k, v in payload.items() if v is not None}),
                status_code=303, headers=headers)
        nonce = uuid4().hex
        values = json.dumps(payload).replace('<', '\\u003c')
        target = json.dumps(pending['return_origin']).replace('<', '\\u003c')
        page = '<!doctype html><meta name="viewport" content="width=device-width"><title>Photo import</title><p>Return to the app that opened this window to finish connecting.</p>'
        # The initiating app owns the popup lifecycle. It can reuse this same
        # user-opened window for Picker without a second popup permission.
        page += f'<script nonce="{nonce}">history.replaceState(null,"","/v1/intake/oauth/callback");if(window.opener){{window.opener.postMessage({values},{target});}}</script>'
        return HTMLResponse(page, headers=dict(headers, **{'Content-Security-Policy': f"default-src 'none'; script-src 'nonce-{nonce}'; frame-ancestors 'none'"}))

    @app.post(root + '/connections/{connection_id}/picker')
    def start_picker(organization_id: str, collection_id: str, connection_id: str, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        doc = manager.get(p, connection_id, connected=True)
        if doc['provider'] != 'google_drive': raise ValueError('This picker is for Google Drive')
        config = manager.config['google_drive']
        if not config.get('picker_api_key') or not config.get('picker_app_id'):
            raise ImportProblem('picker_setup', 'The Drive file picker needs administrator setup.', 'administrator', False)
        pending, state = manager.pending(p, connection_id, 'picker')
        callback_url = urlsplit(config['redirect_uri'])
        url = f'{callback_url.scheme}://{callback_url.netloc}/v1/intake/picker#' + urlencode({'state': state})
        return dict(id=pending['id'], url=url)

    @app.get(root + '/connections/{connection_id}/picker/{picker_id}')
    def picker_status(organization_id: str, collection_id: str, connection_id: str, picker_id: str, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        pending = service.read(p, 'intake_oauth', picker_id)
        native = pending['purpose'] == 'oauth' and pending.get('native_picker')
        if pending['connection_id'] != connection_id or (pending['purpose'] != 'picker' and not native):
            raise ValueError('Invalid picker session')
        if native:
            return native_selection(p, pending)
        return dict(state=pending['state'], items=pending.get('items', []), failures=pending.get('failures', []))

    @app.post('/v1/intake/picker/bootstrap')
    def picker_bootstrap(body: PickerBootstrap):
        p = state_principal(body.state)
        pending = manager.verify_pending(p, body.state, 'picker')
        pending['state'] = 'picking'
        service.save(p, 'intake_oauth', pending)
        selection, state = manager.pending(p, pending['connection_id'], 'picker_selection', {'picker_id': pending['id']})
        config = manager.config['google_drive']
        return dict(token=manager.token(p, pending['connection_id']), state=state,
            key=config['picker_api_key'], app=config['picker_app_id'])

    @app.get('/v1/intake/picker', response_class=HTMLResponse)
    def picker_page():
        nonce = uuid4().hex
        page = '''<!doctype html><meta name="viewport" content="width=device-width"><title>Choose Drive photos</title>
<p id="status">Opening Google Drive…</p><script nonce="NONCE">
const state=new URLSearchParams(location.hash.slice(1)).get('state');
history.replaceState(null,'','/v1/intake/picker');
async function loaded(){
 const response=await fetch('/v1/intake/picker/bootstrap',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({state})});
 if(!response.ok){document.getElementById('status').textContent='This picker session expired. Return to the app and choose files again.';return;}
 const config=await response.json();
 gapi.load('picker',()=>{
 const view=new google.picker.DocsView().setMimeTypes('IMAGE_TYPES');
 const picker=new google.picker.PickerBuilder().addView(view).setOAuthToken(config.token).setDeveloperKey(config.key)
 .setAppId(config.app).setOrigin(location.origin).enableFeature(google.picker.Feature.MULTISELECT_ENABLED)
 .setCallback(async data=>{if(data.action===google.picker.Action.PICKED){
  const r=await fetch('/v1/intake/picker/selection',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({state:config.state,ids:data.docs.map(d=>d.id)})});
  document.getElementById('status').textContent=r.ok?'Photos selected. Return to the app to review them.':'Could not retain the selection. Return to the app and try again.';
 }}).build();picker.setVisible(true);
});}
</script><script nonce="NONCE" src="https://apis.google.com/js/api.js?onload=loaded"></script>'''.replace('NONCE', nonce).replace('IMAGE_TYPES', PICKER_IMAGE_TYPES)
        return HTMLResponse(page, headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'strict-origin',
            'Content-Security-Policy': f"default-src 'none'; script-src 'nonce-{nonce}' https://apis.google.com https://www.gstatic.com; frame-src https://docs.google.com https://drive.google.com; connect-src 'self' https://www.googleapis.com; style-src 'unsafe-inline'; img-src https://*.googleusercontent.com https://www.gstatic.com; frame-ancestors 'none'"})

    @app.post('/v1/intake/picker/selection')
    def picker_selection(body: PickerInput):
        p = state_principal(body.state)
        pending = manager.verify_pending(p, body.state, 'picker_selection')
        pending['state'] = 'selecting'
        pending = service.save(p, 'intake_oauth', pending)
        for id in body.ids:
            if len(picked_file_ids(id)) != 1:
                raise ValueError('Invalid Drive file')
        selection = selection_rows(p, pending['connection_id'], body.ids)
        parent = service.read(p, 'intake_oauth', pending['picker_id'])
        parent.update(state='selected', **selection)
        service.save(p, 'intake_oauth', parent)
        pending['state'] = 'selected'
        service.save(p, 'intake_oauth', pending)
        return dict(selected=len(selection['items']), failures=selection['failures'])
