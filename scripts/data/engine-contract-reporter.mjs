// Ordered evidence emitted only AFTER real assertions/stages. Local diagnostics
// never publish engine-contract.json; only G's independent hosted recorder can.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {spawn, execFileSync} from 'node:child_process';
import {appendFileSync, existsSync, readFileSync, writeFileSync, mkdirSync, mkdtempSync, chmodSync, copyFileSync, cpSync, renameSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import net from 'node:net';
import os from 'node:os';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const read = p => JSON.parse(readFileSync(p, 'utf8'));
const elapsed = start => (performance.now() - start) / 1000;
export function passed(id) {
  if (process.env.ENGINE_CONTRACT_NODE_EVENTS) appendFileSync(process.env.ENGINE_CONTRACT_NODE_EVENTS,
    JSON.stringify({id, outcome:'passed', seconds:elapsed(groupStart)}) + '\n', {mode:0o600});
  groupStart = performance.now();
}
let groupStart = performance.now();
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const TIMED_OUT=Symbol('timed out');
async function bounded(promise,ms) {
  let timer;
  try {return await Promise.race([promise,new Promise(resolve=> {timer=setTimeout(()=>resolve(TIMED_OUT),ms);})]);}
  finally {clearTimeout(timer);}
}
// Signal non-child Storage processes through a pidfd bound to their captured
// OS birth. Opening the fd before rechecking birth closes the PID-reuse race.
// The default remains SIGKILL for the Java forced-cleanup diagnostic.
export const JAVA_CLEANUP_CODE=String.raw`import importlib.util,json,os,signal,sys
spec=importlib.util.spec_from_file_location('engine_gate_cleanup',sys.argv[3])
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
pid=int(sys.argv[1])
receipt=gate.read_json(sys.argv[2])
gate.require(receipt.get('pid')==pid and bool(receipt.get('birth_id')),'missing owned birth identity; refusing PID-only signal')
requested=int(sys.argv[4]) if len(sys.argv)>4 else signal.SIGKILL
gate.require(requested in (signal.SIGINT,signal.SIGTERM,signal.SIGKILL),'unsupported owned-process signal')
forced=False
try:
    descriptor=os.pidfd_open(pid)
except ProcessLookupError:
    descriptor=None
if descriptor is not None:
    try:
        observed=gate.process_birth(pid)
        if observed is not None and observed[0]==receipt['birth_id']:
            try:
                signal.pidfd_send_signal(descriptor,requested)
            except ProcessLookupError:
                pass
            else:
                forced=True
    finally:
        os.close(descriptor)
print(json.dumps({'forced':forced}))
`;
function linuxBirth(pid) {
  if(process.platform!=='linux') return null; // diagnostics only; canonical uses G
  const value=readFileSync(`/proc/${pid}/stat`,'utf8');
  const fields=value.slice(value.lastIndexOf(') ')+2).trim().split(/\s+/);
  return createHash('sha256').update(JSON.stringify({boot_id:readFileSync('/proc/sys/kernel/random/boot_id','utf8').trim(),start_ticks:Number(fields[19])})).digest('hex');
}
function atomic(p, value) {
  mkdirSync(path.dirname(p), {recursive:true, mode:0o700});
  writeFileSync(p + '.partial', JSON.stringify(value), {mode:0o600, flag:'wx'});
  renameSync(p + '.partial', p);
}
function checkIds(rows, ids, label) {
  assert.deepEqual(rows.map(row => row.id), ids, `${label} inventory mismatch`);
  assert.ok(rows.every(row => row.outcome === 'passed' && Number.isFinite(row.seconds) && row.seconds >= 0), `${label} failed`);
}
async function portOpen(port) {
  const socket=net.createConnection({host:'127.0.0.1',port});
  try {await new Promise((resolve,reject)=> {socket.once('connect',resolve);socket.once('error',reject);socket.setTimeout(1000,()=>reject(new Error('readiness port timeout')));});}
  finally {socket.destroy();}
}
async function portsFree(ports) {
  for (const port of ports) {
    const server = net.createServer();
    await new Promise((resolve,reject) => { server.once('error',reject); server.listen(port,'127.0.0.1',resolve); });
    await new Promise((resolve,reject) => server.close(error => error ? reject(error) : resolve()));
  }
}
function live(pid) { try { process.kill(pid,0); return true; } catch(error) { if(error.code==='ESRCH') return false; throw error; } }
function processTable(env) {
  return execFileSync('ps', ['-ww','-axo','pid=,ppid=,args='], {env,encoding:'utf8'}).trim().split('\n').map(row => {
    const match = row.trim().match(/^(\d+)\s+(\d+)\s+(.+)$/); return match && {pid:Number(match[1]),parent:Number(match[2]),command:match[3]};
  }).filter(Boolean);
}
function storageIdentity(pid,env) {
  if(!live(pid)) return null;
  if(process.platform==='linux') {
    try {
      const value=readFileSync(`/proc/${pid}/stat`,'utf8');
      const fields=value.slice(value.lastIndexOf(') ')+2).trim().split(/\s+/);
      return {parent:Number(fields[1]),command:readFileSync(`/proc/${pid}/cmdline`,'utf8').replaceAll('\0',' ').trim(),birth_id:createHash('sha256').update(JSON.stringify({boot_id:readFileSync('/proc/sys/kernel/random/boot_id','utf8').trim(),start_ticks:Number(fields[19])})).digest('hex')};
    } catch(error) {if(error.code==='ENOENT') return null;throw error;}
  }
  assert.equal(process.platform,'darwin','unsupported Storage process birth lookup');
  // Local diagnostics only. Canonical tools and pidfd signaling require Linux.
  let value;
  try {value=execFileSync('ps',['-p',String(pid),'-o','ppid=,lstart='],{env:{...env,LC_ALL:'C'},encoding:'utf8'}).trim();}
  catch(error) {if(error.status===1 && !String(error.stdout).trim()) return null;throw error;}
  const match=value.match(/^(\d+)\s+(.+)$/);
  assert.ok(match,'missing Storage OS birth identity');
  return {parent:Number(match[1]),birth_id:createHash('sha256').update(JSON.stringify({darwin_lstart:match[2]})).digest('hex')};
}
// Every link must still have the captured OS birth, and the child's OS PPID
// must agree with the table. Neither a stale table nor a recycled ancestor can
// confer ownership. Also captures helpers during partial startup, before Java.
export function discoverStorageProcesses(rows,owners,inspect) {
  const bound=new Map(owners.filter(owner=>inspect(owner.pid)?.birth_id===owner.birth_id).map(owner=>[owner.pid,owner]));
  const found=[];
  for(let changed=true;changed;) {
    changed=false;
    for(const row of rows) {
      if(bound.has(row.pid)) continue;
      const parent=bound.get(row.parent);
      if(!parent || inspect(parent.pid)?.birth_id!==parent.birth_id) continue;
      const identity=inspect(row.pid);
      if(!identity || identity.parent!==parent.pid || inspect(parent.pid)?.birth_id!==parent.birth_id) continue;
      const again=inspect(row.pid);
      if(again?.birth_id!==identity.birth_id || again.parent!==parent.pid) continue;
      const owned={...row,...identity,parent_pid:parent.pid,parent_birth_id:parent.birth_id,depth:parent.depth+1};
      found.push(owned);bound.set(owned.pid,owned);changed=true;
    }
  }
  return found;
}

async function harness(kind, argv) {
  const flag = kind === 'sql' ? '--python-contract-output' : '--contract-output';
  let output;
  while(argv.length) {
    const arg = argv.shift();
    if(arg !== flag || output || !argv.length || argv[0].startsWith('--')) {
      console.error(`unknown argument or missing value: ${arg}`); return 2;
    }
    output = path.resolve(argv.shift());
  }
  output ||= mkdtempSync(path.join(os.tmpdir(), `specimen-${kind}-output-`));
  mkdirSync(output, {recursive:true,mode:0o700}); chmodSync(output,0o700);
  const scratch = mkdtempSync(path.join(output,'private-'));
  const lifecyclePath = process.env.ENGINE_CONTRACT_LIFECYCLE || path.join(output,'lifecycle.json');
  const selection = read(path.join(root,'scripts/data/engine-contract-selection.json'));
  const python = path.join(root,'.venv/bin/python');
  const env = {...process.env,PYTHONDONTWRITEBYTECODE:'1'};
  const pg = process.env.POSTGRES_BIN || '/usr/lib/postgresql/16/bin';
  const ports = [Number(env.SPECIMEN_TEST_PG_PORT || 5559), Number(env.SPECIMEN_TEST_DC_PORT || 9509), Number(env.SPECIMEN_TEST_STORAGE_PORT || 9299)];
  const host = `127.0.0.1:${ports[1]}`;
  const canonicalRegistry=Boolean(env.ENGINE_CONTRACT_PROCESS_TOKEN);
  const hasSql=kind==='storage' && existsSync(lifecyclePath);
  let lifecycle = {schema:1, engine_flag:canonicalRegistry?env.SPECIMEN_TEST_SQL_EMULATOR:'diagnostic', readiness:[], stages:[], node_events:[], processes:[]};
  if(hasSql) lifecycle = read(lifecyclePath);
  if(!canonicalRegistry) lifecycle.engine_flag='diagnostic';
  const eventPath = path.join(scratch,'node-events.jsonl');
  writeFileSync(eventPath,'',{mode:0o600,flag:'wx'});
  const children = [];
  let bodyStatus = 0, cleanupFailed = false, interrupted = 0;
  let pgProcess, dcProcess, cliProcess, javaProcess, pgStarted = false;
  const storageOwners=[];
  const auxiliaryPorts=[];
  let database = 'specimen-digitization-database';
  const gate = path.join(root,'scripts/ci/engine_contract_gate.py');
  const config = path.join(scratch,'dataconnect');
  const pgDir = path.join(scratch,'cluster');
  const seedPath = path.join(scratch,'seed.json');
  const deniedCredentials = ['GOOGLE_APPLICATION_CREDENTIALS','FIREBASE_TOKEN','CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE', 'GOOGLE_OAUTH_ACCESS_TOKEN'];
  const onSignal = signal => {
    interrupted = signal==='SIGINT' ? 130 : 143;
    // Active stage children only. Engines are stopped in the single finally path.
    for(const child of children) if(!child.engine && child.exitCode===null && child.signalCode===null) child.kill(signal);
  };
  const intHandler = () => onSignal('SIGINT'), termHandler = () => onSignal('SIGTERM');
  process.on('SIGINT',intHandler); process.on('SIGTERM',termHandler);
  async function run(command,args=[],options={}) {
    const {allowFailure=false,allowInterrupted=false,...spawnOptions}=options;
    if(!allowInterrupted) assert.equal(interrupted,0,'harness interrupted');
    const child=spawn(command,args,{cwd:root,env,stdio:['ignore','pipe','pipe'],...spawnOptions});
    children.push(child);
    let stdout='',stderr='';
    child.stdout?.on('data',chunk=> { stdout+=chunk; process.stdout.write(chunk); });
    child.stderr?.on('data',chunk=> { stderr+=chunk; process.stderr.write(chunk); });
    const status=await new Promise((resolve,reject)=> {child.once('error',reject); child.once('close',(code,signal)=>resolve(code ?? (signal==='SIGINT'?130:signal==='SIGTERM'?143:1)));});
    if(status!==0 && !allowFailure) {const error=new Error(`${command} failed (${status})`); error.status=status; throw error;}
    return {stdout,stderr,status};
  }
  async function stage(id,body) {
    assert.equal(interrupted,0,'harness interrupted');
    const start=performance.now();
    try { const result=await body(); lifecycle.stages.push({id,outcome:'passed',seconds:elapsed(start)}); return result; }
    catch(error) {lifecycle.stages.push({id,outcome:'failed',seconds:elapsed(start)}); const wrapped=new Error(`${id}: ${error.message}`,{cause:error});wrapped.status=error.status;throw wrapped;}
  }
  function register(role,pid) {
    if(!canonicalRegistry) {
      const receiptFile=path.join(scratch,`${role}.launch.json`);
      const birth_id=linuxBirth(pid);
      writeFileSync(receiptFile,JSON.stringify({id:role,pid,birth_id}),{mode:0o600,flag:'wx'});
      return {role,pid,birth_id,receiptFile,diagnostic:true,started_ns:Number(process.hrtime.bigint())};
    }
    const receipt=JSON.parse(execFileSync(python,[gate,'process-start','--id',role,'--pid',String(pid)],{env,encoding:'utf8'}));
    const receiptFile=path.join(scratch,`${role}.launch.json`);
    writeFileSync(receiptFile,JSON.stringify(receipt),{mode:0o600,flag:'wx'});
    return {role,pid,birth_id:receipt.birth_id,receiptFile};
  }
  function registerEnd(owned) {
    if(owned.diagnostic) {assert.ok(!live(owned.pid)||(owned.birth_id&&linuxBirth(owned.pid)!==owned.birth_id),'diagnostic cleanup survivor');lifecycle.processes.push({id:owned.role,pid:owned.pid,started_ns:owned.started_ns,ended_ns:Number(process.hrtime.bigint()),owned:true,stopped:true,waited:true,diagnostic:true});return;}
    const receipt=JSON.parse(execFileSync(python,[gate,'process-end','--receipt',owned.receiptFile,'--waited'],{env,encoding:'utf8'}));
    lifecycle.processes.push(receipt);
  }
  function launch(command,args,role) {
    const log=path.join(scratch,`${role}.log`);
    const child=spawn(command,args,{cwd:kind==='storage'?scratch:root,env,stdio:['ignore','pipe','pipe']});
    child.engine=true;
    let spawnError;
    child.on('error',error=> {spawnError=error;});
    child.stdout.on('data',chunk=>appendFileSync(log,chunk,{mode:0o600}));
    child.stderr.on('data',chunk=>appendFileSync(log,chunk,{mode:0o600}));
    const done=new Promise(resolve=>child.once('close',(code,signal)=>resolve({code,signal})));
    children.push(child);
    const owned={child,done,log,role,pid:child.pid,error:()=>spawnError};
    // Retain direct-child ownership even if independent registration fails.
    // Otherwise a forked CLI could be lost before assignment at the callsite.
    if(role==='storage.cli') {cliProcess=owned;captureStorageLauncher();}
    Object.assign(owned,register(role,child.pid));
    return owned;
  }
  function captureStorageLauncher() {
    const launcher=storageIdentity(cliProcess.pid,env);
    assert.ok(launcher,'Storage launcher OS identity missing');
    const receiptFile=path.join(scratch,'storage-owned-launcher.launch.json');
    const owned={pid:cliProcess.pid,birth_id:launcher.birth_id,parent_pid:null,parent_birth_id:null,depth:0,command:env.FIREBASE_CLI_BIN,started_ns:Number(process.hrtime.bigint()),receiptFile};
    writeFileSync(receiptFile,JSON.stringify(owned),{mode:0o600,flag:'wx'});storageOwners.push(owned);
  }
  async function stop(owned,signal='SIGTERM') {
    assert.ok(owned && !owned.ended, 'cleanup missing or repeated owned process');
    let failed=false;
    if(owned.child) {
      if(owned.child.exitCode!==null || owned.child.signalCode!==null) failed=true;
      else if(!owned.child.kill(signal)) failed=true;
      const ended=await bounded(owned.done,2000);
      if(ended!==TIMED_OUT && ended.code!==0 && ended.signal!==signal) failed=true;
      if(ended===TIMED_OUT) { failed=true; owned.child.kill('SIGKILL'); await owned.done; }
    } else {
      // CLI must reap its Java child before it reports shutdown completed.
      for(let n=0;n<100 && live(owned.pid);n++) await delay(20);
      if(live(owned.pid)) {
        const result=JSON.parse(execFileSync(python,['-c',JAVA_CLEANUP_CODE,String(owned.pid),owned.receiptFile,gate],{env,encoding:'utf8'}));
        failed ||= result.forced;
        if(result.forced) for(let n=0;n<100 && live(owned.pid);n++) await delay(20);
      }
    }
    if(owned.child) assert.ok(!live(owned.pid), `cleanup survivor: ${owned.role}`);
    registerEnd(owned); owned.ended=true;
    assert.ok(!failed, `cleanup required forced termination or engine exited early: ${owned.role}`);
  }
  function storageAlive(owned) {return storageIdentity(owned.pid,env)?.birth_id===owned.birth_id;}
  function captureStorageTree() {
    for(const owner of discoverStorageProcesses(processTable(env),storageOwners,pid=>storageIdentity(pid,env))) {
      const receiptFile=path.join(scratch,`storage-owned-${storageOwners.length}.launch.json`);
      const receipt={...owner,started_ns:Number(process.hrtime.bigint()),receiptFile};
      writeFileSync(receiptFile,JSON.stringify(receipt),{mode:0o600,flag:'wx'});
      storageOwners.push(receipt);
    }
  }
  function signalStorage(owned,signal) {
    return JSON.parse(execFileSync(python,['-c',JAVA_CLEANUP_CODE,String(owned.pid),owned.receiptFile,gate,String(os.constants.signals[signal])],{env,encoding:'utf8'}));
  }
  async function waitStorage(owners,refresh=false) {
    const deadline=performance.now()+2000;
    do {
      if(refresh) captureStorageTree();
      const current=refresh?storageOwners.filter(owner=>owner.depth>0):owners;
      if(current.every(owner=>!storageAlive(owner))) return true;
      await delay(20);
    } while(performance.now()<deadline);
    return (refresh?storageOwners.filter(owner=>owner.depth>0):owners).every(owner=>!storageAlive(owner));
  }
  async function stopStorage() {
    let failed=false;
    const attempt=async body=> {try {await body();} catch(error) {failed=true;console.error(`Storage cleanup: ${error.stack || error}`);}};
    // Keep the launcher alive to reap the CLI, and the CLI alive to reap Java.
    // The standalone launcher does not promise to forward shutdown signals.
    await attempt(async()=>captureStorageTree());
    const topCli=storageOwners.filter(owner=>owner.depth===1 && !/(?:^|[\s/])java(?:\s|$)/.test(owner.command));
    if(topCli.length) {
      for(const owned of topCli) await attempt(async()=>signalStorage(owned,'SIGINT'));
    } else if(cliProcess.child.exitCode===null && cliProcess.child.signalCode===null) {
      await attempt(async()=>assert.ok(cliProcess.child.kill('SIGINT'),'Storage launcher signal failed'));
    }
    await attempt(async()=>waitStorage(null,true));
    const descendants=storageOwners.filter(owner=>owner.depth>0);
    // A noncooperating descendant makes the run fail. Kill deepest first while
    // parents can still wait/reap, and never signal a bare or recycled PID.
    for(const owned of [...descendants].sort((a,b)=>b.depth-a.depth)) await attempt(async()=> {
      if(storageAlive(owned)) {
        failed=true;signalStorage(owned,'SIGKILL');
        assert.ok(await waitStorage([owned]),`Storage cleanup survivor: ${owned.pid}`);
      }
    });
    await attempt(async()=> {
      let ended=await bounded(cliProcess.done,2000);
      if(ended===TIMED_OUT) {failed=true;await stop(cliProcess,'SIGINT');}
      else {
        assert.ok(ended.code===0 || ended.signal==='SIGINT','Storage launcher/CLI exited unsuccessfully');
        assert.ok(cliProcess.receiptFile,'Storage launcher registration missing');
        registerEnd(cliProcess);cliProcess.ended=true;
      }
    });
    if(javaProcess) await attempt(async()=> {registerEnd(javaProcess);javaProcess.ended=true;});
    lifecycle.storage_processes=[];
    for(const owned of storageOwners) await attempt(async()=> {
      const stopped=!storageAlive(owned);
      lifecycle.storage_processes.push({...owned,receiptFile:undefined,stopped,waited:stopped,ended_ns:Number(process.hrtime.bigint())});
      assert.ok(stopped,`Storage cleanup survivor: ${owned.pid}`);
    });
    assert.ok(!failed,'Storage cleanup failed or required forced termination');
  }
  const node=(name,...args)=>run('node',[path.join(root,`scripts/data/${name}.mjs`),...args]);
  const psql=(...args)=>run(path.join(pg,'psql'),['-h','127.0.0.1','-p',String(ports[0]),'-d',database,...args]);
  async function indexes() {
    await psql('-v','ON_ERROR_STOP=1','-f',path.join(config,'sql/paging-indexes.sql'));
    await psql('-v','ON_ERROR_STOP=1','-f',path.join(config,'sql/search-indexes.sql'));
    const check=await run('bash',[path.join(root,'scripts/data/source-asset-read-back.sh'),path.join(pg,'psql'),'-h','127.0.0.1','-p',String(ports[0]),'-d',database]);
    assert.equal(check.stdout.trim(),'1','source asset unique index readback failed');
    await psql('-v','ON_ERROR_STOP=1','-f',path.join(config,'sql/drop-specimen-unique-1.sql'));
  }
  async function startConnector(round,readinessId) {
    await stage(`sql.start.${round}`,async()=> {
      dcProcess=launch(env.DATACONNECT_EMULATOR_BIN,['dev','-config_dir',config,'-listen',host,'-local_connection_string',`postgresql://127.0.0.1:${ports[0]}/${database}?sslmode=disable`],`dataconnect.${round}`);
    });
    await stage(`sql.ready.${round}`,async()=> {
      const start=performance.now();
      try {await node('wait-local');} catch(error) {throw Object.assign(new Error('readiness failed: '+error.message),{status:error.status});}
      assert.ok(!dcProcess.error() && live(dcProcess.pid),'readiness process exited');
      try {await portOpen(ports[1]);} catch(error) {throw new Error('readiness port failed: '+error.message);}
      lifecycle.readiness.push({id:readinessId,outcome:'passed',seconds:elapsed(start)});
    });
  }
  function events() { return readFileSync(eventPath,'utf8').trim().split('\n').filter(Boolean).map(JSON.parse); }
  async function preflight() {
    assert.ok(deniedCredentials.every(key=>!env[key]),'cloud credentials refused');
    for(const key of ['GCLOUD_PROJECT','GOOGLE_CLOUD_PROJECT','FIREBASE_PROJECT_ID']) assert.ok(!env[key] || env[key]==='demo-specimen-data', `cloud project refused: ${key}`);
    assert.ok(ports.every(p=>Number.isInteger(p)&&p>1024&&p<65536&&p!==3000&&p!==8000)&&new Set(ports).size===3,'invalid ports');
    assert.ok(!env.SPECIMEN_SQL_EMULATOR_HOST || env.SPECIMEN_SQL_EMULATOR_HOST===host,'port_mismatch: Python host differs');
    assert.ok(!env.FIREBASE_DATACONNECT_EMULATOR_HOST || env.FIREBASE_DATACONNECT_EMULATOR_HOST===host,'port_mismatch: DC host differs');
    assert.ok(!env.FIREBASE_STORAGE_EMULATOR_HOST || env.FIREBASE_STORAGE_EMULATOR_HOST===`127.0.0.1:${ports[2]}`,'port_mismatch: Storage host differs');
    await portsFree(ports);
    const probe=await run(python,[path.join(root,'scripts/data/provision-engine-tools.py'),'--verify-only','--directory',env.ENGINE_TOOLS_DIR || '', '--mode',env.ENGINE_CACHE_MODE || 'normal','--output',env.ENGINE_PROVISION_REPORT || '']);
    const evidence=JSON.parse(probe.stdout);
    if(kind==='sql' || !hasSql) {
      assert.ok(kind==='sql' || !canonicalRegistry,'canonical Storage requires completed SQL lifecycle');
      if(kind==='sql') assert.equal(env.SPECIMEN_TEST_SQL_EMULATOR,'true','explicit engine flag required');
      Object.assign(lifecycle,{tools:evidence.tools,runtime:evidence.runtime,cache:evidence.cache,
        preflight:{project:'demo-specimen-data',host:'127.0.0.1',ports,ports_free_before:true,credentials_absent:true,
          postgres_host:`127.0.0.1:${ports[0]}`,dataconnect_host:host,python_host:host,storage_host:`127.0.0.1:${ports[2]}`}});
    } else {
      assert.deepEqual(evidence.tools,lifecycle.tools,'Storage/SQL tool mismatch');
      assert.deepEqual(evidence.cache,lifecycle.cache,'Storage/SQL cache mismatch');
      assert.deepEqual(evidence.runtime,lifecycle.runtime,'Storage/SQL runtime mismatch');
    }
    // Never consult real HOME/config or libpq environment. Engines and CLI use a
    // private working/cache directory and fail outbound requests at a dead proxy.
    for(const key of Object.keys(env)) if(key.startsWith('PG') || (/TOKEN|SECRET|PASSWORD|API_KEY|CREDENTIAL/.test(key) && key!=='ENGINE_CONTRACT_PROCESS_TOKEN')) delete env[key];
    Object.assign(env,{TMPDIR:scratch,TMP:scratch,TEMP:scratch,HOME:path.join(scratch,'home'),XDG_CONFIG_HOME:path.join(scratch,'home/config'),XDG_CACHE_HOME:path.join(scratch,'home/cache'),
      FIREBASE_CLI_DISABLE_UPDATE_CHECK:'true',NO_UPDATE_NOTIFIER:'1',CI:'true',
      HTTP_PROXY:'http://127.0.0.1:1',HTTPS_PROXY:'http://127.0.0.1:1',ALL_PROXY:'http://127.0.0.1:1',
      http_proxy:'http://127.0.0.1:1',https_proxy:'http://127.0.0.1:1',all_proxy:'http://127.0.0.1:1',NO_PROXY:'127.0.0.1,localhost',no_proxy:'127.0.0.1,localhost',
      FIREBASE_DATACONNECT_EMULATOR_HOST:host,SPECIMEN_SQL_EMULATOR_HOST:host,FIREBASE_STORAGE_EMULATOR_HOST:`127.0.0.1:${ports[2]}`,
      DATA_RESTART_PROOF:path.join(scratch,'restart.json'),DATA_TEST_DIR:scratch,DATA_TEST_EMULATOR_BIN:env.DATACONNECT_EMULATOR_BIN,
      POSTGRES_BIN:pg,SPECIMEN_TEST_PG_PORT:String(ports[0]),PSQL_BIN:path.join(pg,'psql'),
      ENGINE_CONTRACT_NODE_EVENTS:eventPath,ENGINE_CONTRACT_SEED_REPORT:seedPath});
    if(env.JAVA_HOME) env.PATH=path.join(env.JAVA_HOME,'bin')+path.delimiter+env.PATH;
    mkdirSync(env.XDG_CONFIG_HOME,{recursive:true,mode:0o700});
    const override=process.env.SPECIMEN_TEST_DATACONNECT_CONFIG;
    assert.ok(!override || !canonicalRegistry,'diagnostic config cannot qualify canonical evidence');
    cpSync(override || path.join(root,'dataconnect'),config,{recursive:true});
  }
  try {
    if(kind==='sql') {
      await stage('preflight',preflight);
      await stage('sql.compile',async()=> {
        const result=await run(env.DATACONNECT_EMULATOR_BIN,['build','-config_dir',config]);
        writeFileSync(path.join(scratch,'compile.json'),result.stdout,{mode:0o600});
        const compiled=JSON.parse(result.stdout);
        assert.ok(compiled && typeof compiled==='object' && !Array.isArray(compiled),'invalid compile result');
        // The Firebase 15.8.0 build consumer permits omitted/null errors on success.
        assert.ok(compiled.errors==null || (Array.isArray(compiled.errors) && compiled.errors.length===0),'compile errors despite exit0');
      });
      await stage('postgres.init',()=>run(path.join(pg,'initdb'),['-D',pgDir,'-A','trust','--no-locale']));
      await stage('postgres.start',async()=> {
        // Foreground postgres is our direct child: wait() and birth receipt are
        // available, unlike pg_ctl's detached postmaster. Same original flags.
        pgProcess=launch(path.join(pg,'postgres'),['-D',pgDir,'-h','127.0.0.1','-p',String(ports[0]),'-k',scratch],'postgres'); pgStarted=true;
        // pg_ctl -w start used to wait for readiness. Preserve that proof by
        // bounded real SQL probes, with no changed existing engine timeout.
        let ready=false;
        for(let n=0;n<100;n++) {const r=await run(path.join(pg,'psql'),['-h','127.0.0.1','-p',String(ports[0]),'-d','postgres','-Atc','SELECT 1'],{allowFailure:true}); if(r.status===0&&r.stdout.trim()==='1') {ready=true;break;} await delay(100);}
        assert.ok(ready && live(pgProcess.pid),'postgres readiness failed');
        const version=await run(path.join(pg,'psql'),['-h','127.0.0.1','-p',String(ports[0]),'-d','postgres','-Atc','SHOW server_version']);
        const serverVersion=version.stdout.trim();
        const exactVersion=serverVersion.match(/^(16\.\d+)(?: \([^\r\n]*\))?$/)?.[1];
        assert.ok(exactVersion && exactVersion===lifecycle.runtime.postgres_server,'PostgreSQL server version mismatch');
        lifecycle.postgres_server_version=serverVersion;
        await run(path.join(pg,'psql'),['-h','127.0.0.1','-p',String(ports[0]),'-d','postgres','-v','ON_ERROR_STOP=1','-c','CREATE EXTENSION "uuid-ossp"']);
      });
      await stage('postgres.createdb',()=>run(path.join(pg,'createdb'),['-h','127.0.0.1','-p',String(ports[0]),database]));
      await startConnector('initial','sql.initial');
      for(const name of ['legacy-import-proof-schema','connector','projection','bootstrap','worker-membership','research-registration','research-send-fence','pilot-ledger','sensitivity']) {
        await stage(`sql.${name}`,()=>node(`${name}-test`));
      }
      await stage('sql.indexes.initial',indexes);
      for(const name of ['paging','search','checksum']) await stage(`sql.${name}`,()=>node(`${name}-test`));
      await stage('sql.seed',async()=> {
        await node('seed-integration');
        assert.ok(existsSync(seedPath),'seed missing readback');
        const expected={organization:'00000000-0000-4000-8000-000000000001',collection:'00000000-0000-4000-8000-000000000002',uid:'synthetic-reviewer',organization_active:true,collection_active:true,role:'reviewer',can_view_sensitive:true};
        assert.deepEqual(read(seedPath),expected,'seed mismatch'); lifecycle.seed=read(seedPath);
      });
      await stage('sql.python',async()=> {
        const report=process.env.ENGINE_CONTRACT_PYTEST_REPORT || path.join(output,'pytest-phases.json');
        assert.ok(!existsSync(report),'refuse stale Python report');
        env.ENGINE_CONTRACT_PYTEST_REPORT=report;
        await run(python,['-m','pytest','-q','-p','no:cacheprovider',`--basetemp=${path.join(scratch,'pytest')}`,'-p','scripts.ci.engine_contract_gate',...selection.python_nodes]);
        assert.ok(existsSync(report),'missing Python phase report');
      });
      await stage('sql.stop.initial',()=>stop(dcProcess));
      console.log('INFO all synthetic application writers quiesced during schema reconciliation and index repair');
      await startConnector('reconciliation','sql.reconciliation');
      await stage('sql.indexes.inspect',async()=> {
        const count=await psql('-Atc',"SELECT count(*) FROM pg_index JOIN pg_class ON pg_class.oid = indexrelid WHERE relname IN ('specimen_text_cursor', 'auxiliary_text_cursor', 'specimen_search_cursor', 'snapshot_search_batch') AND indisvalid");
        writeFileSync(path.join(scratch,'source-reconciliation.json'),JSON.stringify({validSupplementalIndexesAfterEmulatorStartup:Number(count.stdout.trim()),requiredPostSchemaPhase:'paging-indexes.sql + search-indexes.sql + drop-specimen-unique-1.sql'}),{mode:0o600});
        if(count.stdout.trim()!=='4') console.log('OBSERVED emulator reconciliation removed supplemental indexes; explicit post-schema DDL reapplied');
      });
      await stage('sql.indexes.reconciliation',indexes);
      await stage('sql.restart',()=>node('restart-test'));
      await stage('sql.stop.reconciliation',()=>stop(dcProcess));
      await stage('sql.restore',()=>node('backup-restore-test','restore'));
      database='specimen-digitization-restored';
      for(const round of [1,2]) {
        await startConnector(`restored${round}`,`sql.restored${round}`);
        await stage(`sql.restore.reconcile${round}`,()=>node('backup-restore-test','reconcile'));
        await stage(`sql.indexes.restored${round}`,indexes);
        await stage(`sql.restart.restored${round}`,()=>node('restart-test'));
        await stage(`sql.restore.verify${round}`,()=>node('backup-restore-test','verify'));
        await stage(`sql.indexes.repeat${round}`,indexes);
        await stage(`sql.restore.repeat-verify${round}`,()=>node('backup-restore-test','verify'));
        await stage(`sql.stop.restored${round}`,()=>stop(dcProcess));
      }
      checkIds(events(),selection.connector_groups,'connector'); lifecycle.node_events.push(...events());
    } else {
      await preflight();
      await stage('storage.start',async()=> {
        const rules=process.env.SPECIMEN_TEST_STORAGE_RULES;
        assert.ok(!rules || !canonicalRegistry,'diagnostic Storage rules cannot qualify');
        const localRules=path.join(scratch,'storage.rules'); copyFileSync(rules || path.join(root,'storage.rules'),localRules);
        // The CLI also owns hub/logging listeners. Give them private known ports
        // and prove their release, rather than touching shared 4400/4500.
        for(let n=0;n<2;n++) {
          const server=net.createServer();
          await new Promise((resolve,reject)=> {server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
          const port=server.address().port;
          await new Promise(resolve=>server.close(resolve));
          assert.ok(!ports.includes(port)&&!auxiliaryPorts.includes(port),'auxiliary port alias');auxiliaryPorts.push(port);
        }
        await portsFree(auxiliaryPorts);
        lifecycle.preflight.auxiliary_ports=[...auxiliaryPorts];
        const configFile=path.join(scratch,'firebase.json');
        writeFileSync(configFile,JSON.stringify({storage:{rules:localRules},emulators:{storage:{host:'127.0.0.1',port:ports[2]},hub:{host:'127.0.0.1',port:auxiliaryPorts[0]},logging:{host:'127.0.0.1',port:auxiliaryPorts[1]},ui:{enabled:false},singleProjectMode:true}}),{mode:0o600});
        env.FIREBASE_EMULATORS_PATH=path.join(scratch,'emulators'); mkdirSync(env.FIREBASE_EMULATORS_PATH,{mode:0o700});
        const cachedJar=path.join(env.FIREBASE_EMULATORS_PATH,'cloud-storage-rules-runtime-v1.1.3.jar');
        copyFileSync(env.STORAGE_RULES_RUNTIME_JAR,cachedJar);
        // firebase-tools 15.8.0 getDownloadDetails marks an explicit binary
        // override localOnly: even a cache miss cannot trigger a download.
        env.STORAGE_EMULATOR_BINARY_PATH=cachedJar;
        cliProcess=launch(env.FIREBASE_CLI_BIN,['emulators:start','--only','storage','--project','demo-specimen-data','--config',configFile,'--non-interactive'],'storage.cli');
        assert.ok(!canonicalRegistry || storageOwners[0].birth_id===cliProcess.birth_id,'Storage launcher birth mismatch');
        let java;
        for(let n=0;n<100;n++) {
          captureStorageTree();
          assert.equal(interrupted,0,'harness interrupted during Storage startup');
          java=storageOwners.find(row=>row.depth>0 && storageAlive(row) && /(?:^|[\s/])java(?:\s|$)/.test(row.command) && row.command.includes(env.STORAGE_EMULATOR_BINARY_PATH));
          if(java) break;
          assert.ok(live(cliProcess.pid),'Storage CLI exited during startup'); await delay(100);
        }
        assert.ok(java,'Storage Java child missing'); javaProcess=register('storage.java',java.pid);
        assert.ok(!canonicalRegistry || javaProcess.birth_id===java.birth_id,'Storage Java birth mismatch');
      });
      await stage('storage.ready',async()=> {
        const start=performance.now();
        await run('node',[path.join(root,'scripts/data/wait-local.mjs')],{env:{...env,FIREBASE_DATACONNECT_EMULATOR_HOST:env.FIREBASE_STORAGE_EMULATOR_HOST}});
        assert.ok(live(cliProcess.pid)&&live(javaProcess.pid),'Storage readiness failed');
        await portOpen(ports[2]);
        assert.ok(!/downloading|download failed/i.test(readFileSync(cliProcess.log,'utf8')),'Storage CLI attempted download');
        lifecycle.readiness.push({id:'storage',outcome:'passed',seconds:elapsed(start)});
      });
      await stage('storage.assertions',async()=> { await node('storage-test'); checkIds(events(),selection.storage_assertions,'storage denial/admin/original bytes'); lifecycle.node_events.push(...events()); });
    }
  } catch(error) { console.error(error.stack || error); bodyStatus=error.status || interrupted || 1; }
  finally {
    const start=performance.now();
    async function attempt(body) {try {await body();} catch(error) {console.error(`cleanup: ${error.stack || error}`);cleanupFailed=true;}}
    if(dcProcess && !dcProcess.ended) await attempt(()=>stop(dcProcess));
    if(pgProcess && !pgProcess.ended) {
      if(pgStarted) await attempt(async()=> {const result=await run(path.join(pg,'pg_ctl'),['-D',pgDir,'-m','fast','stop'],{allowFailure:true,allowInterrupted:true}); assert.equal(result.status,0,'PostgreSQL cleanup pg_ctl failed'); assert.ok((await bounded(pgProcess.done,2000))!==TIMED_OUT,'PostgreSQL cleanup wait failed'); assert.ok(!live(pgProcess.pid),'PostgreSQL cleanup survivor'); registerEnd(pgProcess); pgProcess.ended=true;});
      if(!pgProcess.ended) await attempt(()=>stop(pgProcess));
    }
    if(cliProcess && existsSync(cliProcess.log)) await attempt(async()=>assert.ok(!/downloading|download failed/i.test(readFileSync(cliProcess.log,'utf8')),'Storage CLI attempted download'));
    if(cliProcess) await attempt(()=>stopStorage());
    await attempt(()=>portsFree([...ports,...auxiliaryPorts]));
    const survivors=children.filter(c=>c.exitCode===null&&c.signalCode===null).map(c=>c.pid);
    for(const owned of storageOwners) if(storageAlive(owned) && !survivors.includes(owned.pid)) survivors.push(owned.pid);
    if(survivors.length) {
      cleanupFailed=true;
      for(const child of children.filter(c=>survivors.includes(c.pid))) {
        child.kill('SIGTERM');
        await delay(100);
        if(child.exitCode===null&&child.signalCode===null) child.kill('SIGKILL');
      }
    }
    lifecycle.cleanup={outcome:cleanupFailed?'failed':'passed',ports_free_after:!cleanupFailed,survivors,seconds:elapsed(start)};
    lifecycle.stages.push({id:kind==='sql'?'sql.cleanup':'storage.cleanup',outcome:cleanupFailed?'failed':'passed',seconds:elapsed(start)});
    // Registration order is distinct from cleanup order (PG ends after DC).
    lifecycle.processes.sort((a,b)=>selection.processes.indexOf(a.id)-selection.processes.indexOf(b.id));
    if(!bodyStatus && !cleanupFailed) {
      try {checkIds(lifecycle.stages,selection.stages.filter(id=>kind==='storage'?(hasSql||id.startsWith('storage.')):!id.startsWith('storage.')),'stage');}
      catch(error) {console.error(error.stack);bodyStatus=1;}
    }
    // A part is useful diagnostics on failure, never canonical success.
    atomic(lifecyclePath,lifecycle);
    if(lifecyclePath!==path.join(output,'lifecycle.json')) atomic(path.join(output,'lifecycle.json'),lifecycle);
    process.removeListener('SIGINT',intHandler);process.removeListener('SIGTERM',termHandler);
    console.log(`Synthetic ${kind} logs retained at ${scratch}`);
  }
  return interrupted || bodyStatus || (cleanupFailed?1:0);
}

if(process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const [kind,...args]=process.argv.slice(2);
  if(!['sql','storage'].includes(kind)) {console.error('unknown harness kind');process.exitCode=2;}
  else harness(kind,args).then(code=> {process.exitCode=code;}).catch(error=> {console.error(error.stack);process.exitCode=1;});
}
