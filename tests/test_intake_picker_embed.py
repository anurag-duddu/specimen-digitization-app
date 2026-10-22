"""Isolated inline Picker contracts; no real Google/account acceptance."""
import json
import re
import subprocess
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from specimen_digitization.application.intake_source_routes import install_source_routes
from specimen_digitization.application.storage import Conflict
from test_intake_selection import web_picker
from test_intake_sources import connected  # noqa: F401 -- credential-free fixture

APP = 'https://app.example'
OTHER = 'https://other.example'
API = 'https://api.example'


@pytest.fixture
def inline(connected):
    p, manager, reads, _, _, status, _ = web_picker(connected)
    permitted = [True]
    def principal(user, org, collection, **kwargs):
        if not permitted[0] or (user, org, collection) != (p.user_id, p.scope.organization_id, p.scope.collection_id):
            raise PermissionError('Current membership unavailable')
        return p
    app = FastAPI()
    install_source_routes(app, '/v1/organizations/{organization_id}', manager.service, manager,
        identity=lambda: p.user_id, principal=principal, origins=(APP, OTHER))
    client = TestClient(app)
    start = status.rsplit('/', 1)[0]
    result = client.post(start, json={'return_origin': APP}, headers={'Origin': APP}).json()
    state = parse_qs(urlsplit(result['url']).fragment)['state'][0]
    return SimpleNamespace(p=p, manager=manager, reads=reads, client=client, permitted=permitted,
        start=start, result=result, state=state, status=start + '/' + result['id'],
        bootstrap={'state': state, 'return_origin': APP, 'picker_id': result['id']})


def bootstrap(ctx):
    response = ctx.client.post('/v1/intake/picker/bootstrap', json=ctx.bootstrap, headers={'Origin': API})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'private, no-store'
    return response.json()


def parent(ctx):
    return ctx.manager.service.read(ctx.p, 'intake_oauth', ctx.result['id'])


def test_embed_origin_is_authenticated_persisted_and_exact(inline):
    c = inline
    parsed = urlsplit(c.result['url'])
    assert parsed.scheme + '://' + parsed.netloc == API
    assert parse_qs(parsed.query) == {'embed_origin': [APP], 'picker_id': [c.result['id']]}
    assert parent(c)['return_origin'] == APP
    for origin, header in [(APP, None), (APP, OTHER), ('https://app.example.evil.test', APP), ('null', 'null')]:
        with pytest.raises(PermissionError):
            c.client.post(c.start, json={'return_origin': origin}, headers={'Origin': header} if header else {})
    c.permitted[0] = False
    with pytest.raises(PermissionError):
        c.client.post(c.start, json={'return_origin': APP}, headers={'Origin': APP})
    with pytest.raises(PermissionError):
        bootstrap(c)


def test_embed_frame_policy_is_page_scoped_and_bootstrap_cannot_override_binding(inline, monkeypatch):
    c = inline
    page = c.client.get(c.result['url'])
    assert page.status_code == 200
    assert page.headers['content-security-policy'].endswith('frame-ancestors ' + APP)
    assert OTHER not in page.headers['content-security-policy']
    assert page.headers['cache-control'] == 'no-store'
    assert "frame-ancestors 'none'" in c.client.get('/v1/intake/picker').headers['content-security-policy']
    for origin in ['https://evil.example', APP + '/path', APP + '; frame-ancestors *']:
        with pytest.raises((PermissionError, ValueError)):
            c.client.get('/v1/intake/picker', params={'embed_origin': origin, 'picker_id': c.result['id']})
    tokens = []
    token = c.manager.token
    monkeypatch.setattr(c.manager, 'token', lambda *args: tokens.append(True) or token(*args))
    for body in [dict(c.bootstrap, return_origin=OTHER), dict(c.bootstrap, picker_id='different'), {'state': c.state}]:
        with pytest.raises(PermissionError):
            c.client.post('/v1/intake/picker/bootstrap', json=body, headers={'Origin': API})
    for origin in [None, APP, OTHER]:
        with pytest.raises(PermissionError):
            c.client.post('/v1/intake/picker/bootstrap', json=c.bootstrap, headers={'Origin': origin} if origin else {})
    assert tokens == [] and parent(c)['state'] == 'pending'
    result = bootstrap(c)
    assert result['return_origin'] == APP and result['id'] == c.result['id']
    assert result['token'] == 'access' and tokens == [True]
    assert 'access' not in page.text and 'refresh' not in page.text
    with pytest.raises(ValueError, match='expired'):
        bootstrap(c)


@pytest.mark.parametrize('body', [None, {}])
def test_legacy_popup_start_and_bootstrap_remain_compatible(inline, body):
    c = inline
    result = c.client.post(c.start, **({'json': body} if body is not None else {})).json()
    parsed = urlsplit(result['url'])
    assert not parsed.query
    state = parse_qs(parsed.fragment)['state'][0]
    response = c.client.post('/v1/intake/picker/bootstrap', json={'state': state})
    assert response.status_code == 200 and response.json()['token'] == 'access'
    assert response.json()['return_origin'] is None
    assert "frame-ancestors 'none'" in c.client.get(result['url']).headers['content-security-policy']


def test_no_extra_tokens_or_lifecycle_fields_are_accepted(inline):
    c = inline
    assert c.client.post(c.start, json={'return_origin': APP, 'token': 'untrusted'}, headers={'Origin': APP}).status_code == 422
    assert c.client.post('/v1/intake/picker/bootstrap', json={**c.bootstrap, 'token': 'untrusted'}, headers={'Origin': API}).status_code == 422
    state = bootstrap(c)['state']
    for extra in [{'token': 'untrusted'}, {'docs': [{'id': 'one'}]}, {'picker_id': c.result['id']}, {'return_origin': APP}]:
        response = c.client.post('/v1/intake/picker/selection', json={'state': state, 'ids': ['one'], **extra}, headers={'Origin': API})
        assert response.status_code == 422
    with pytest.raises(PermissionError):
        c.client.post('/v1/intake/picker/selection', json={'state': state, 'ids': ['one']}, headers={'Origin': APP})
    assert parent(c)['state'] == 'picking' and not c.reads


@pytest.mark.parametrize('action,state', [('cancelled', 'cancelled'), ('error', 'failed')])
def test_provider_terminal_callbacks_close_only_current_unselected_session(inline, action, state):
    c = inline
    proof = bootstrap(c)['state']
    response = c.client.post('/v1/intake/picker/selection', json={'state': proof, 'action': action}, headers={'Origin': API})
    assert response.json()['state'] == state
    assert parent(c)['state'] == state and not c.reads
    assert c.client.post(c.status + '/cancel').json()['state'] == state
    with pytest.raises(ValueError, match='expired'):
        c.client.post('/v1/intake/picker/selection', json={'state': proof, 'ids': ['one']}, headers={'Origin': API})


def test_owned_cancel_checks_connection_and_current_membership(inline):
    c = inline
    wrong = c.status.replace('/connections/' + parent(c)['connection_id'], '/connections/wrong')
    with pytest.raises(ValueError, match='Invalid picker'):
        c.client.post(wrong + '/cancel')
    c.permitted[0] = False
    with pytest.raises(PermissionError):
        c.client.post(c.status + '/cancel')
    c.permitted[0] = True
    assert parent(c)['state'] == 'pending'
    assert c.client.post(c.status + '/cancel').json()['state'] == 'cancelled'
    assert c.client.post(c.status + '/cancel').json()['state'] == 'cancelled'
    with pytest.raises(ValueError, match='expired'):
        bootstrap(c)


def test_expired_embedded_session_cannot_bootstrap_credentials(inline, monkeypatch):
    c = inline
    monkeypatch.setattr(c.manager, 'clock', lambda: parent(c)['expires_at'] + 1)
    monkeypatch.setattr(c.manager, 'token', lambda *args: pytest.fail('Expired session accessed a provider token'))
    with pytest.raises(ValueError, match='expired'):
        bootstrap(c)
    assert c.client.post(c.status + '/cancel').json()['state'] == 'cancelled'


@pytest.mark.parametrize('winner', ['cancel', 'selection'])
def test_selection_and_cancel_cas_cannot_resurrect_or_drop_committed_selection(inline, monkeypatch, winner):
    c = inline
    proof = bootstrap(c)['state']
    service, raced = c.manager.service, [False]
    save = service.save
    def race(p, kind, doc):
        boundary = 'selecting' if winner == 'cancel' else 'cancelled'
        if kind == 'intake_oauth' and doc['id'] == c.result['id'] and doc['state'] == boundary and not raced[0]:
            raced[0] = True
            if winner == 'cancel':
                assert c.client.post(c.status + '/cancel').json()['state'] == 'cancelled'
            else:
                assert c.client.post('/v1/intake/picker/selection', json={'state': proof, 'ids': ['one']}, headers={'Origin': API}).json()['state'] == 'selecting'
        return save(p, kind, doc)
    monkeypatch.setattr(service, 'save', race)
    if winner == 'cancel':
        with pytest.raises(Conflict):
            c.client.post('/v1/intake/picker/selection', json={'state': proof, 'ids': ['one']}, headers={'Origin': API})
        assert parent(c)['state'] == 'cancelled' and 'selection_ids' not in parent(c)
        assert not c.reads
    else:
        assert c.client.post(c.status + '/cancel').json()['state'] == 'selecting'
        assert parent(c)['selection_ids'] == ['one']
        assert c.client.get(c.status).json()['state'] == 'selected'
        assert c.client.post(c.status + '/cancel').json()['items'][0]['id'] == 'one'
    assert raced[0]


def test_lost_selection_response_is_recovered_by_owned_cancel_and_status(inline, monkeypatch):
    c = inline
    proof = bootstrap(c)['state']
    service = c.manager.service
    save = service.save
    def lost(p, kind, doc):
        result = save(p, kind, doc)
        if kind == 'intake_oauth' and doc.get('purpose') == 'picker_selection' and doc['state'] == 'consumed':
            raise TimeoutError('Lost acknowledgement')
        return result
    monkeypatch.setattr(service, 'save', lost)
    with pytest.raises(TimeoutError):
        c.client.post('/v1/intake/picker/selection', json={'state': proof, 'ids': ['one', 'two']}, headers={'Origin': API})
    assert c.client.post(c.status + '/cancel').json()['state'] == 'selecting'
    result = c.client.get(c.status).json()
    assert result['state'] == 'selected' and [row['id'] for row in result['items']] == ['one', 'two']
    assert c.client.post(c.status + '/cancel').json() == result
    assert c.reads == ['one', 'two']


def test_lost_cancel_response_is_idempotently_reconciled(inline, monkeypatch):
    c = inline
    service = c.manager.service
    save, lost = service.save, [False]
    def uncertain(p, kind, doc):
        result = save(p, kind, doc)
        if doc['id'] == c.result['id'] and doc['state'] == 'cancelled' and not lost[0]:
            lost[0] = True
            raise TimeoutError('Lost acknowledgement')
        return result
    monkeypatch.setattr(service, 'save', uncertain)
    with pytest.raises(TimeoutError):
        c.client.post(c.status + '/cancel')
    assert c.client.post(c.status + '/cancel').json()['state'] == 'cancelled'
    assert not c.reads


@pytest.mark.parametrize('scenario', ['selected', 'cancelled', 'error', 'selection_lost', 'cancel_lost',
    'bootstrap_error', 'gapi_error', 'expiry', 'load_timeout', 'pagehide', 'legacy'])
def test_actual_api_page_script_keeps_credentials_isolated_and_clears_lifecycle(inline, scenario):
    c = inline
    page = c.client.get('/v1/intake/picker' if scenario == 'legacy' else c.result['url']).text
    script = re.search(r'<script nonce="[^"]+">(.*?)</script>', page, re.S).group(1)
    # Run the actual generated script with a local Google/DOM contract. Real
    # provider rendering and cross-origin browser enforcement are separate gates.
    result = subprocess.run(['node', '-e', _PAGE_CONTRACT], input=json.dumps({
        'script': script, 'scenario': scenario, 'id': c.result['id']}), text=True,
        capture_output=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'isolated lifecycle passed'


_PAGE_CONTRACT = r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
let input='';process.stdin.on('data',part=>input+=part);process.stdin.on('end',async()=>{
 try{
  const {script,scenario,id}=JSON.parse(input),legacy=scenario==='legacy';
  const events=[],requests=[],frames=[],handlers={},timers=new Map(),seen={};
  const status={hidden:false,textContent:''};let callback,nextTimer=1;
  const config={token:'fixture-provider-access',state:'fixture-selection-capability',key:'fixture-key',app:'123',
   return_origin:legacy?null:'https://app.example',id,expires_in:600};
  class DocsView{setMimeTypes(value){seen.types=value;return this;}setMode(value){seen.mode=value;return this;}}
  class PickerBuilder{
   addView(){return this;}setOAuthToken(value){seen.token=value;return this;}
   setDeveloperKey(){return this;}setAppId(){return this;}
   setOrigin(value){seen.origin=value;return this;}enableFeature(){return this;}
   setCallback(fn){callback=fn;return this;}
   toUri(){seen.uri=true;return {toString:()=> 'https://docs.google.com/picker?oauth_token='+seen.token};}
   build(){seen.dialog=true;return {setVisible:value=>seen.visible=value};}
  }
  const context={URLSearchParams,AbortController,Error,Math,
   location:{hash:'#state=fixture-parent-capability',origin:'https://api.example'},
   history:{replaceState(){seen.hashCleared=true;}},
   setTimeout(fn,ms){const key=nextTimer++;timers.set(key,{fn,ms});return key;},clearTimeout(key){timers.delete(key);},
   window:{parent:{postMessage(payload,target){events.push({payload:JSON.parse(JSON.stringify(payload)),target});}},
    addEventListener(name,fn){handlers[name]=fn;}},
   document:{getElementById(name){return name==='status'?status:{appendChild(frame){frames.push(frame);frame.onload();}};},
    createElement(name){assert.equal(name,'iframe');return {remove(){this.removed=true;}};}},
   google:{picker:{DocsView,PickerBuilder,DocsViewMode:{LIST:'list'},Feature:{MULTISELECT_ENABLED:'multi'},
    Action:{PICKED:'picked',CANCEL:'cancel',ERROR:'error'}}},
   gapi:{load(name,options){assert.equal(name,'picker');scenario==='gapi_error'?options.onerror():options.callback();}},
   async fetch(path,options){
    const body=JSON.parse(options.body);requests.push({path,body});
    if(path.endsWith('/bootstrap'))return {ok:scenario!=='bootstrap_error',json:async()=>({...config})};
    assert.equal(path,'/v1/intake/picker/selection');
    if(scenario==='selection_lost'||scenario==='cancel_lost')throw Error('untrusted transport details');
    return {ok:true,json:async()=>({state:body.action==='selected'?'selecting':body.action==='cancelled'?'cancelled':'failed'})};
   }
  };
  vm.createContext(context);vm.runInContext(script,context);
  if(scenario==='load_timeout')timers.values().next().value.fn();
  else await vm.runInContext('loaded()',context);
  if(!['load_timeout','bootstrap_error','gapi_error'].includes(scenario)){
   assert.equal(seen.mode,'list');assert.equal(seen.origin,legacy?'https://api.example':'https://app.example');
   assert.equal(seen.token,'fixture-provider-access');assert.equal(seen.hashCleared,true);
   if(legacy){assert.equal(seen.dialog,true);assert.equal(seen.uri,undefined);}
   else{assert.equal(seen.dialog,undefined);assert.equal(seen.uri,true);assert.equal(frames.length,1);
    assert.match(frames[0].src,/^https:\/\/docs.google.com\/picker\?/);assert.equal(frames[0].title,'Google Drive photo selection');}
   if(scenario==='expiry'){[...timers.values()].find(t=>t.ms===600000).fn();}
   else if(scenario==='pagehide'){handlers.pagehide();}
   else{const action=['selected','selection_lost','legacy'].includes(scenario)?'picked':scenario==='error'?'error':'cancel';
    await callback({action,docs:[{id:'one',private:'not-forwarded'}]});}
  }
  const terminal=['selected','legacy'].includes(scenario)?'selected':scenario==='cancelled'?'cancelled':'error';
  if(!legacy){
   for(const event of events){assert.equal(event.target,'https://app.example');
    assert.deepEqual(Object.keys(event.payload).sort(),['action','picker_id','type']);
    assert.equal(event.payload.type,'specimen-intake-picker');assert.equal(event.payload.picker_id,id);}
   assert.equal(events.at(-1).payload.action,scenario==='pagehide'?'ready':terminal);
   assert.ok(!JSON.stringify(events).includes('fixture-provider-access'));
   assert.ok(!JSON.stringify(events).includes('fixture-selection-capability'));
  }else assert.equal(events.length,0);
  assert.ok(frames.every(frame=>frame.removed));assert.equal(timers.size,0);
  const previous=requests.length;if(callback)await callback({action:'picked',docs:[{id:'late'}]});
  assert.equal(requests.length,previous,'terminal session ignores stale callbacks');
  if(requests[0])assert.deepEqual(requests[0].body,legacy?{state:'fixture-parent-capability'}:
   {state:'fixture-parent-capability',return_origin:'https://app.example',picker_id:id});
  if(requests[1]&&['selected','selection_lost','legacy'].includes(scenario))
   assert.deepEqual(requests[1].body,{state:'fixture-selection-capability',action:'selected',ids:['one']});
  assert.ok(!status.textContent.includes('untrusted transport details'));
  process.stdout.write('isolated lifecycle passed\n');
 }catch(error){process.stderr.write(String(error.stack)+'\n');process.exitCode=1;}
});
'''
