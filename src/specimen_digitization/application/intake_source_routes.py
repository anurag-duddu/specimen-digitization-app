"""Connection, picker, and source browsing routes shared by web and native apps."""
import html
import json
import base64
import io
import tempfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import urlsplit, urlencode
from uuid import UUID, uuid4
from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import Field, model_validator

from .domain import Record
from .intake_connections import safe_connection, PICKER_IMAGE_TYPES
from .intake_sources import ImportProblem, public_url
from .source_registry import validate_object_name
from .source_reader import SourceListingIncomplete
from .intake_cloud_sources import EXTENSIONS
from .intake_models import SourceReference, MAX_BYTES
from .intake_selection import PickerSelection, selection_reply
from .storage import Conflict


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
    return_origin: str | None = None
    picker_id: str | None = None


class PickerStart(Record):
    return_origin: str | None = None


class PickerInput(Record):
    state: str = Field(max_length=2048)
    ids: list[str] = Field(default_factory=list, max_length=500)
    action: Literal['selected', 'cancelled', 'error'] = 'selected'

    @model_validator(mode='after')
    def selected_ids(self):
        if bool(self.ids) != (self.action == 'selected'):
            raise ValueError('Only a file selection includes photo identifiers')
        return self


def install_source_routes(app, prefix, service, manager, *, identity, principal, origins=()):
    root = prefix + '/collections/{collection_id}/intake'

    def access(org, collection, user):
        return principal(user, org, collection, write=True)

    def provider(p, id):
        if manager is None:
            raise ImportProblem('provider_not_configured', 'Cloud connections need administrator setup.', 'administrator', False)
        doc = manager.get(p, id, connected=True)
        return service.sources.providers[doc['provider']]

    selection_rows = PickerSelection(service, provider, clock=manager.clock) if manager else None
    service.selection = selection_rows

    def native_selection(p, pending, *, advance=True):
        # An authenticated completion retains the IDs before exchange. Polling
        # can finish metadata validation after a lost completion reply.
        if pending['state'] == 'authorized':
            pending = selection_rows.begin(p, pending, pending['picked_file_ids'], pending['id'])
        if advance and pending['state'] == 'selecting':
            pending = selection_rows.status(p, pending)
        return selection_reply(pending)

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
            result['selection'] = native_selection(p, pending, advance=False)
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

    def allowed_picker_origin(value):
        parsed = urlsplit(value)
        return (value in origins and parsed.scheme in {'http', 'https'} and parsed.hostname
            and not parsed.username and not parsed.password and not parsed.path and not parsed.query and not parsed.fragment
            and not any(character.isspace() or character in "'\";*" for character in value))

    def picker_context(request, pending):
        if pending.get('return_origin') is not None:
            callback = urlsplit(manager.config['google_drive']['redirect_uri'])
            if request.headers.get('origin') != f'{callback.scheme}://{callback.netloc}':
                raise PermissionError('Picker credentials stay in the API frame')

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
    def start_picker(organization_id: str, collection_id: str, connection_id: str, request: Request,
                     body: PickerStart | None = None, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        return_origin = body.return_origin if body else None
        if return_origin is not None and (not allowed_picker_origin(return_origin) or request.headers.get('origin') != return_origin):
            raise PermissionError('Unknown initiating application origin')
        doc = manager.get(p, connection_id, connected=True)
        if doc['provider'] != 'google_drive': raise ValueError('This picker is for Google Drive')
        config = manager.config['google_drive']
        if not config.get('picker_api_key') or not config.get('picker_app_id'):
            raise ImportProblem('picker_setup', 'The Drive file picker needs administrator setup.', 'administrator', False)
        pending, state = manager.pending(p, connection_id, 'picker',
            {'return_origin': return_origin} if return_origin is not None else None)
        callback_url = urlsplit(config['redirect_uri'])
        query = '?' + urlencode({'embed_origin': return_origin, 'picker_id': pending['id']}) if return_origin is not None else ''
        url = f'{callback_url.scheme}://{callback_url.netloc}/v1/intake/picker{query}#' + urlencode({'state': state})
        return dict(id=pending['id'], url=url)

    @app.get(root + '/connections/{connection_id}/picker/{picker_id}')
    def picker_status(organization_id: str, collection_id: str, connection_id: str, picker_id: str, user=Depends(identity)):
        return picker_progress(organization_id, collection_id, connection_id, picker_id, user)

    @app.post(root + '/connections/{connection_id}/picker/{picker_id}/retry')
    def picker_retry(organization_id: str, collection_id: str, connection_id: str, picker_id: str, user=Depends(identity)):
        return picker_progress(organization_id, collection_id, connection_id, picker_id, user, retry=True)

    @app.post(root + '/connections/{connection_id}/picker/{picker_id}/cancel')
    def picker_cancel(organization_id: str, collection_id: str, connection_id: str, picker_id: str, user=Depends(identity)):
        return picker_progress(organization_id, collection_id, connection_id, picker_id, user, cancel=True)

    def finish_picker(p, pending, *, failed=False):
        # A cancellation may race bootstrap or selection persistence. Only an
        # unselected parent can be closed; selection's CAS remains authoritative.
        for _ in range(3):
            if pending['state'] not in {'pending', 'picking'}:
                return pending
            update = dict(pending, state='failed' if failed else 'cancelled')
            if failed:
                update['error'] = dict(code='picker_failed', message='Drive file selection could not finish. Choose photos again.',
                    action='choose_source', retryable=True)
            try:
                return service.save(p, 'intake_oauth', update)
            except Conflict:
                pending = service.read(p, 'intake_oauth', pending['id'])
        raise Conflict('The Picker session changed. Check its current selection.')

    def picker_progress(organization_id, collection_id, connection_id, picker_id, user, *, retry=False, cancel=False):
        p = access(organization_id, collection_id, user)
        pending = service.read(p, 'intake_oauth', picker_id)
        native = pending['purpose'] == 'oauth' and pending.get('native_picker')
        if pending['connection_id'] != connection_id or (pending['purpose'] != 'picker' and not native):
            raise ValueError('Invalid picker session')
        if cancel:
            if native:
                raise ValueError('Only an embedded web Picker can be cancelled here')
            return selection_reply(finish_picker(p, pending))
        if retry and pending['state'] == 'selecting':
            return selection_reply(selection_rows.retry(p, pending))
        if native:
            if pending['state'] == 'exchanging':
                try:
                    manager.recover(p, connection_id)
                except ImportProblem as exc:
                    if exc.intake_problem['code'] != 'credential_write_pending':
                        raise
                pending = service.read(p, 'intake_oauth', picker_id)
            return native_selection(p, pending)
        if pending['state'] == 'selecting':
            pending = selection_rows.status(p, pending)
        return selection_reply(pending)

    @app.post('/v1/intake/picker/bootstrap')
    def picker_bootstrap(body: PickerBootstrap, request: Request):
        p = state_principal(body.state)
        pending = manager.verify_pending(p, body.state, 'picker')
        picker_context(request, pending)
        if (pending.get('return_origin') != body.return_origin
                or (body.return_origin is not None and (body.return_origin not in origins or body.picker_id != pending['id']))
                or (body.return_origin is None and body.picker_id is not None)):
            raise PermissionError('Picker application origin changed')
        pending['state'] = 'picking'
        service.save(p, 'intake_oauth', pending)
        selection, state = manager.pending(p, pending['connection_id'], 'picker_selection', {'picker_id': pending['id']})
        config = manager.config['google_drive']
        return JSONResponse(dict(token=manager.token(p, pending['connection_id']), state=state,
            key=config['picker_api_key'], app=config['picker_app_id'], id=pending['id'],
            return_origin=pending.get('return_origin'), expires_in=max(0, pending['expires_at'] - manager.clock())),
            headers={'Cache-Control': 'private, no-store'})

    @app.get('/v1/intake/picker', response_class=HTMLResponse)
    def picker_page(embed_origin: str | None = None, picker_id: str | None = None):
        if embed_origin is not None:
            if not allowed_picker_origin(embed_origin) or not picker_id or str(UUID(picker_id)) != picker_id:
                raise PermissionError('Unknown Picker frame origin or identity')
        elif picker_id is not None:
            raise ValueError('An embedded Picker needs its application origin')
        nonce = uuid4().hex
        values = json.dumps(dict(origin=embed_origin, id=picker_id)).replace('<', '\\u003c')
        page = '''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Choose Drive photos</title>
<style>html,body{margin:0;width:100%;height:100%;font:16px system-ui,sans-serif;color:#25332c;background:#fff}#status{padding:16px;margin:0}#picker{height:100%;width:100%}iframe{border:0;width:100%;height:100%;display:block}</style></head><body>
<p id="status" role="status">Opening Google Drive…</p><div id="picker"></div><script nonce="NONCE">
const embedded=EMBEDDED;
let state=new URLSearchParams(location.hash.slice(1)).get('state');
history.replaceState(null,'','/v1/intake/picker');
let done=false,busy=false,picker=null,frame=null,expiry=null,readySent=false;
const status=document.getElementById('status');
function notify(action){if(embedded.origin&&window.parent!==window){window.parent.postMessage({type:'specimen-intake-picker',picker_id:embedded.id,action},embedded.origin);}}
function clearPicker(){if(frame){frame.remove();frame=null;}if(picker){picker.setVisible(false);picker=null;}}
function finish(action,message){if(done)return;done=true;clearTimeout(loadTimer);clearTimeout(expiry);clearPicker();status.hidden=false;status.textContent=message;notify(action);}
function failed(){finish('error','Could not finish Drive selection. Check your selection in the app before trying again.');}
function ready(){if(done||readySent)return;readySent=true;clearTimeout(loadTimer);status.hidden=true;notify('ready');}
const loadTimer=setTimeout(failed,30000);
window.addEventListener('pagehide',()=>{done=true;clearTimeout(loadTimer);clearTimeout(expiry);clearPicker();});
async function post(path,body){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
 try{const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal});
  if(!response.ok)throw new Error('Picker request failed');return await response.json();
 }finally{clearTimeout(timer);}
}
async function loaded(){
 try{
  if(done)return;
  const config=await post('/v1/intake/picker/bootstrap',{state,...(embedded.origin?{return_origin:embedded.origin,picker_id:embedded.id}:{})});state=null;
  if(done)return;
  if(embedded.origin&&(config.return_origin!==embedded.origin||config.id!==embedded.id))throw new Error('Picker context changed');
  expiry=setTimeout(failed,Math.max(0,config.expires_in)*1000);
  gapi.load('picker',{callback:()=>{
   if(done)return;
   try{
    const view=new google.picker.DocsView().setMimeTypes('IMAGE_TYPES').setMode(google.picker.DocsViewMode.LIST);
    const builder=new google.picker.PickerBuilder().addView(view).setOAuthToken(config.token).setDeveloperKey(config.key)
     .setAppId(config.app).setOrigin(config.return_origin||location.origin).enableFeature(google.picker.Feature.MULTISELECT_ENABLED)
     .setCallback(async data=>{
      if(done||busy)return;
      let action;
      if(data.action===google.picker.Action.PICKED)action='selected';
      else if(data.action===google.picker.Action.CANCEL)action='cancelled';
      else if(data.action===google.picker.Action.ERROR)action='error';
      else return;
      busy=true;clearTimeout(loadTimer);clearPicker();status.hidden=false;status.textContent='Saving your selection…';
      try{
       const result=await post('/v1/intake/picker/selection',{state:config.state,action,...(action==='selected'?{ids:data.docs.map(d=>d.id)}:{})});
       if(result.state==='selecting'||result.state==='selected')finish('selected','Selection saved. Check your photos in the app.');
       else if(result.state==='cancelled')finish('cancelled','Selection cancelled.');
       else failed();
      }catch{failed();}
     });
    if(embedded.origin){
     frame=document.createElement('iframe');frame.title='Google Drive photo selection';
     frame.onload=ready;frame.onerror=failed;
     frame.src=builder.toUri().toString();document.getElementById('picker').appendChild(frame);
    }else{picker=builder.build();picker.setVisible(true);ready();}
    config.token=null;
   }catch{failed();}
  },onerror:failed,timeout:30000,ontimeout:failed});
 }catch{failed();}
}
</script><script nonce="NONCE" src="https://apis.google.com/js/api.js?onload=loaded"></script></body></html>'''.replace('NONCE', nonce).replace('IMAGE_TYPES', PICKER_IMAGE_TYPES).replace('EMBEDDED', values)
        ancestors = embed_origin if embed_origin is not None else "'none'"
        return HTMLResponse(page, headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'strict-origin',
            'Content-Security-Policy': f"default-src 'none'; script-src 'nonce-{nonce}' https://apis.google.com https://www.gstatic.com; frame-src https://docs.google.com https://drive.google.com; connect-src 'self' https://www.googleapis.com; style-src 'unsafe-inline'; img-src https://*.googleusercontent.com https://www.gstatic.com; frame-ancestors {ancestors}"})

    @app.post('/v1/intake/picker/selection')
    def picker_selection(body: PickerInput, request: Request):
        p = state_principal(body.state)
        pending = manager.verify_pending(p, body.state, 'picker_selection')
        parent = service.read(p, 'intake_oauth', pending['picker_id'])
        if parent['purpose'] != 'picker' or parent['connection_id'] != pending['connection_id']:
            raise ValueError('Invalid Picker selection')
        picker_context(request, parent)
        if body.action != 'selected':
            parent = finish_picker(p, parent, failed=body.action == 'error')
            pending['state'] = 'consumed'
            try:
                service.save(p, 'intake_oauth', pending)
            except Conflict:
                pass
            return dict(state=parent['state'])
        parent = selection_rows.begin(p, parent, body.ids, pending['id'])
        pending['state'] = 'consumed'
        try:
            service.save(p, 'intake_oauth', pending)
        except Conflict:
            pass  # The frozen parent already owns this exact selection.
        return dict(state=parent['state'], selected=len(parent['selection_ids']), failures=[])
