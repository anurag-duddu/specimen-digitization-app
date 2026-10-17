"""Controlled subprocess qualification; these fixtures never launch real engines."""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import threading
import time
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get('ENGINE_HARNESS_SOURCE', ROOT)) / 'scripts/data'


def provisioner():
    spec = importlib.util.spec_from_file_location('provision_under_test', DATA / 'provision-engine-tools.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verified_cache_control(p,directory,monkeypatch):
    directory.mkdir()
    marker=directory/'executed'
    payload=f'#!/bin/sh\n# good\necho executed > {marker}\n'.encode()
    config=json.loads(json.dumps(p.gate.APPROVED_TOOLCHAIN))
    cache=directory/'cache';cache.mkdir(mode=0o700)
    for name,asset in config['assets'].items():
        asset.update(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest())
        target=cache/p.FILENAMES[name];target.write_bytes(payload);target.chmod(0o700)
    monkeypatch.setattr(p,'load_toolchain',lambda:config)
    monkeypatch.setattr(p.gate,'inspect_runtime',lambda _env: {'java':'21.0.13+11','node':'22.24.0','postgres':'16.16','image_version':'20261019.400.1'},raising=False)
    monkeypatch.setattr(p,'download_asset',lambda *_a,**_k:pytest.fail('restored-cache validation attempted a download'))
    return config,cache,payload,marker


@pytest.mark.parametrize('fault', ['missing', 'size', 'sha', 'corrupt_cache', 'wrong_version'])
def test_provision_checks_size_and_sha_after_restore(tmp_path, fault, monkeypatch, capsys):
    p = provisioner()
    asset = tmp_path / 'never-execute'
    marker=tmp_path/'executed'
    good=f'#!/bin/sh\n# good\necho executed > {marker}\n'.encode()
    approved = {'version': '3.2.0', 'bytes': len(good), 'sha256': hashlib.sha256(good).hexdigest(), 'url': 'https://example.invalid/pinned'}
    asset.write_bytes(good)
    asset.chmod(0o700)
    if fault == 'missing':
        asset.unlink()
    elif fault == 'size':
        asset.write_bytes(good + b'!')
    elif fault in ('sha', 'corrupt_cache'):
        asset.write_bytes(good.replace(b'# good', b'# evil', 1))
    else:
        approved['version'] = '3.4.22'
    with pytest.raises((ValueError, OSError), match='missing|size|hash|version|No such'):
        p.verify_asset(asset, approved, version='3.2.0')
    assert not marker.exists(), 'unverified binary was executed'
    config,cache,payload,cache_marker=verified_cache_control(p,tmp_path/'restored',monkeypatch)
    cached=cache/p.FILENAMES['dataconnect']
    if fault=='missing': cached.unlink()
    elif fault=='size': cached.write_bytes(payload+b'!')
    elif fault in ('sha','corrupt_cache'): cached.write_bytes(payload.replace(b'# good',b'# evil'))
    else: cached.rename(cache/'dataconnect-emulator-3.4.22')
    assert p.main(['--directory',str(cache),'--mode','normal','--restore','hit','--output',str(tmp_path/'restore.json')])==1
    expected='size' if fault=='size' else 'hash' if fault in ('sha','corrupt_cache') else 'missing' if fault=='missing' else 'unexpected'
    assert expected in capsys.readouterr().err
    assert not cache_marker.exists(), 'restored binary was executed'


def test_pinned_manifest_matches_independent_gate():
    spec = importlib.util.spec_from_file_location('gate_constants', ROOT / 'scripts/ci/engine_contract_gate.py')
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    assert json.loads((DATA / 'engine-toolchain.json').read_text()) == g.APPROVED_TOOLCHAIN


@pytest.mark.parametrize('fault', ['size', 'sha', 'oversize'])
def test_download_checks_bytes_without_executing(tmp_path, fault):
    p = provisioner()
    import io
    content = b'payload'
    asset = {'version': '1', 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest(), 'url': 'https://example.invalid/pinned'}
    body = content[:-1] if fault == 'size' else b'changed' if fault == 'sha' else content + b'extra'
    with pytest.raises(ValueError, match='size|hash'):
        p.download_asset(tmp_path / 'tool', asset, opener=lambda _: io.BytesIO(body))
    assert not (tmp_path / 'tool').exists()


def test_cold_cache_refuses_inherited_or_preseeded_directory(tmp_path):
    p = provisioner()
    directory = tmp_path / 'preseeded'
    directory.mkdir()
    (directory / 'engine').write_text('inherited')
    with pytest.raises(ValueError, match='cold.*new|cold.*exist'):
        p.prepare_directory(directory, mode='cold', event='workflow_dispatch', restore='bypassed')
    with pytest.raises(ValueError, match='dispatch'):
        p.prepare_directory(tmp_path / 'new', mode='cold', event='pull_request', restore='bypassed')
    fresh = tmp_path / 'cold'
    evidence = p.prepare_directory(fresh, mode='cold', event='workflow_dispatch', restore='bypassed')
    assert evidence == {'mode': 'cold', 'directory_private': True, 'directory_fresh': True, 'entries_before': 0, 'restore': 'bypassed'}
    assert list(fresh.iterdir()) == []
    assert fresh.stat().st_mode & 0o777 == 0o700


# All stand-ins are copied into a private synthetic repository. They are never
# injectable into a canonical gate: G hashes tracked helpers and independently
# checks approved tool bytes before the wrapper starts.
STANDIN = r'''#!PYTHON
import json, os, pathlib, signal, sys, time
args=sys.argv[1:]; name=pathlib.Path(sys.argv[0]).name
fault=os.getenv('FIXTURE_FAULT',''); root=pathlib.Path(os.environ['FIXTURE_ROOT'])
with (root/'calls.jsonl').open('a') as f: f.write(json.dumps([name,*args])+'\n')
def birth(pid):
 import hashlib
 if sys.platform=='linux':
  fields=pathlib.Path('/proc/'+str(pid)+'/stat').read_text().rsplit(') ',1)[1].split()
  return hashlib.sha256(json.dumps({'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'start_ticks':int(fields[19])},separators=(',',':')).encode()).hexdigest()
 return hashlib.sha256(json.dumps({'darwin_lstart':'fixture-'+str(pid)},separators=(',',':')).encode()).hexdigest()
if name in ('postgres','dc','firebase','java'):
 (root/'instances').mkdir(exist_ok=True)
 entry=root/'instances'/(str(os.getpid())+'.json')
 entry.with_suffix('.partial').write_text(json.dumps({'pid':os.getpid(),'parent':os.getppid(),'command':str(pathlib.Path(sys.argv[0]).resolve())+' '+' '.join(args)})); entry.with_suffix('.partial').rename(entry)
if name=='firebase' and fault=='unknown_argument': sys.exit(0)
if name=='ps':
 if '-p' in args:
  pid=int(args[args.index('-p')+1])
  try: os.kill(pid,0)
  except ProcessLookupError: sys.exit(1)
  deadline=time.monotonic()+1
  while not (root/'instances'/(str(pid)+'.json')).exists() and time.monotonic()<deadline: time.sleep(.001)
  row=json.loads((root/'instances'/(str(pid)+'.json')).read_text())
  print(str(row['parent'])+' fixture-'+str(pid)); sys.exit(0)
 for entry in (root/'instances').glob('*.json'):
  row=json.loads(entry.read_text())
  try: os.kill(row['pid'],0)
  except ProcessLookupError: continue
  print(str(row['pid'])+' '+str(row['parent'])+' '+row['command'])
 sys.exit(0)
if name=='python':
 if '-c' in args:
  # Model the native pidfd helper only in this private subprocess fixture.
  # Its real birth/pidfd semantics are separately tested without OS signals.
  pid=int(args[args.index('-c')+2]); receipt=json.loads(pathlib.Path(args[args.index('-c')+3]).read_text())
  assert receipt['pid']==pid
  sig=int(args[-1]) if args[-1].isdigit() else int(signal.SIGKILL)
  try:
   assert receipt['birth_id']==birth(pid)
   os.kill(pid,sig)
  # Match pidfd_open/process_birth: an already reaped process is gone. Linux
  # removes its /proc stat file; the Darwin fixture uses a synthetic birth.
  except (ProcessLookupError,FileNotFoundError): sent=False
  else: sent=True
  with (root/'native-signals.jsonl').open('a') as f: f.write(json.dumps({'pid':pid,'signal':sig})+'\n')
  print(json.dumps({'forced':sent})); sys.exit(0)
 if 'provision-engine-tools.py' in ' '.join(args):
  print(json.dumps(json.loads((root/'preflight.json').read_text()))); sys.exit(0)
 if 'process-start' in args:
  pid=int(args[args.index('--pid')+1])
  # Our synthetic ps birth record is written by the child, while the real OS
  # record exists at spawn. Publish the mock receipt only after that barrier.
  deadline=time.monotonic()+1
  while not (root/'instances'/(str(pid)+'.json')).exists() and time.monotonic()<deadline: time.sleep(.001)
  assert (root/'instances'/(str(pid)+'.json')).exists(),'fixture child identity was not published'
  if fault=='storage_registration_failed' and args[args.index('--id')+1]=='storage.cli':
   while not (root/'storage-cli-running').exists() and time.monotonic()<deadline: time.sleep(.001)
   assert (root/'storage-cli-running').exists(),'fixture forked CLI did not start'
   sys.exit(29)
  print(json.dumps({'id':args[args.index('--id')+1],'pid':pid,'birth_id':birth(pid)})); sys.exit(0)
 if 'process-end' in args:
  print(pathlib.Path(args[args.index('--receipt')+1]).read_text()); sys.exit(0)
 # pytest stand-in checks the exact in-lifetime environment.
 (root/'python-env.json').write_text(json.dumps({'bytecode':os.getenv('PYTHONDONTWRITEBYTECODE'),'tmpdir':os.getenv('TMPDIR')}))
 assert os.environ['SPECIMEN_SQL_EMULATOR_HOST']==os.environ['FIREBASE_DATACONNECT_EMULATOR_HOST']
 assert (root/'seed-seen').exists()
 pathlib.Path(os.environ['ENGINE_CONTRACT_PYTEST_REPORT']).write_text('{}')
 if fault=='hold_python':
  (root/'python-running').touch()
  while True: time.sleep(.02)
 sys.exit(17 if fault=='test_failed' else 0)
if name=='node':
 target=pathlib.Path(args[0]).name if args else ''
 if target=='engine-contract-reporter.mjs': os.execv(os.environ['REAL_NODE'],[os.environ['REAL_NODE'],*args])
 if target=='wait-local.mjs': sys.exit(19 if fault=='readiness_failed' else 0)
 if target=='seed-integration.mjs':
  if fault!='seed_missing':
   seed=json.loads((root/'seed.json').read_text())
   if fault=='seed_mismatch': seed['role']='outsider'
   pathlib.Path(os.environ['ENGINE_CONTRACT_SEED_REPORT']).write_text(json.dumps(seed))
  (root/'seed-seen').touch(); sys.exit(0)
 if target in ('connector-test.mjs','storage-test.mjs'):
  if target=='storage-test.mjs' and fault=='hold_storage':
   (root/'storage-assertions-running').touch()
   while True: time.sleep(.02)
  selection=json.loads((root/'scripts/data/engine-contract-selection.json').read_text())
  ids=selection['connector_groups' if target=='connector-test.mjs' else 'storage_assertions']
  with open(os.environ['ENGINE_CONTRACT_NODE_EVENTS'],'a') as f:
   for id in ids:
    if id==fault: continue
    f.write(json.dumps({'id':id,'outcome':'passed','seconds':0})+'\n')
 if target=='source-asset-read-back.sh': print('1')
 sys.exit(0)
if name=='dc':
 if args[0]=='build':
  if 'FIXTURE_COMPILE_RESPONSE' in os.environ:
   print(os.environ['FIXTURE_COMPILE_RESPONSE']); sys.exit(0)
  print(json.dumps({'errors':['compile rejected'] if fault=='compile_errors_exit0' else []})); sys.exit(0)
# Process census and receipt stand-ins exit above without loading engine servers.
import socket, subprocess, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
if name=='firebase' and os.getenv('FIXTURE_STANDALONE') and '--fixture-cli' not in args:
 child=subprocess.Popen([sys.argv[0],'--fixture-cli',*args])
 (root/'standalone-pids.json').write_text(json.dumps({'launcher':os.getpid(),'cli':child.pid}))
 if fault=='storage_ready_cli_exit':
  # Keep the readiness probe pending until the launcher has reaped the CLI.
  # Otherwise it can observe Java's exit in the interval before CLI exit.
  config=json.loads(pathlib.Path(args[args.index('--config')+1]).read_text())['emulators']
  # Linux requires reuse on this listener as well as cleanup's replacement
  # binder after the accepted connection is actively closed (socket(7)).
  exit_hub=socket.socket(); exit_hub.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); exit_hub.bind(('127.0.0.1',config['hub']['port'])); exit_hub.listen(16)
  def exit_probe():
   with exit_hub.accept()[0] as connection:
    assert connection.recv(4096).startswith(b'GET /emulators ')
    (root/'hub-requested').touch()
    child.wait()
  threading.Thread(target=exit_probe,daemon=True).start()
 def end(signum,*_):
  # A safety net for a broken controller, with an auditable signal record.
  # The corrected controller must signal the CLI, leaving this path unused.
  with (root/'launcher-signals.jsonl').open('a') as f: f.write(json.dumps(signum)+'\n')
  child.send_signal(signum); child.wait(timeout=5); sys.exit(0)
 signal.signal(signal.SIGINT,end); signal.signal(signal.SIGTERM,end)
 sys.exit(child.wait())
if name=='firebase' and '--fixture-cli' in args: args.remove('--fixture-cli')
if name in ('postgres','dc','firebase','java'):
 if name in ('dc','firebase') and fault!='false_readiness':
  port=int(args[args.index('-listen')+1].split(':')[1]) if name=='dc' else json.loads(pathlib.Path(args[args.index('--config')+1]).read_text())['emulators']['storage']['port']
  listener=socket.socket(); listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); listener.bind(('127.0.0.1',port)); listener.listen(16)
 if name=='postgres':
  directory=pathlib.Path(args[args.index('-D')+1]); directory.mkdir(exist_ok=True)
  (directory/'postmaster.pid').write_text(str(os.getpid()))
 if name=='firebase':
  config=json.loads(pathlib.Path(args[args.index('--config')+1]).read_text())['emulators']
  class Hub(BaseHTTPRequestHandler):
   def do_GET(self):
    assert self.path=='/emulators'
    (root/'hub-requested').touch()
    body=json.dumps({} if fault.startswith('storage_ready_') else {'storage':{'name':'storage','host':'127.0.0.1','port':config['storage']['port']}}).encode()
    self.send_response(200); self.end_headers(); self.wfile.write(body)
   def log_message(self,*_): pass
  if fault!='storage_ready_cli_exit' or not os.getenv('FIXTURE_STANDALONE'):
   hub=ThreadingHTTPServer(('127.0.0.1',config['hub']['port']),Hub)
   threading.Thread(target=hub.serve_forever,daemon=True).start()
  probe=subprocess.Popen([str(root/'bin/java'),'--version']) if os.getenv('FIXTURE_JAVA_PROBE') else None
  child=None if fault=='storage_no_java' else subprocess.Popen([str(root/'bin/java'),os.environ['STORAGE_EMULATOR_BINARY_PATH']])
  (root/'java-pid.json').write_text(json.dumps({'pid':child.pid if child else None,'parent':os.getpid(),'probe':probe.pid if probe else None,'jar':os.environ['STORAGE_EMULATOR_BINARY_PATH']}))
  def end(*_):
   failed=False
   for owned in ([probe] if probe else [])+([child] if child else []):
    owned.terminate()
    try: owned.wait(timeout=1)
    except subprocess.TimeoutExpired: owned.kill(); owned.wait(); failed=True
   sys.exit(31 if failed else 0)
  signal.signal(signal.SIGINT,end); signal.signal(signal.SIGTERM,end)
  for owned in ([probe] if probe else [])+([child] if child else []):
   deadline=time.monotonic()+1
   while not (root/'instances'/(str(owned.pid)+'.json')).exists() and time.monotonic()<deadline: time.sleep(.001)
   assert (root/'instances'/(str(owned.pid)+'.json')).exists(),'fixture Java identity was not published'
  (root/'storage-cli-running').touch(); print('Downloading forbidden runtime' if fault=='storage_download' else 'Storage fixture started',flush=True)
  while True:
   if (root/'hub-requested').exists() and fault in ('storage_ready_cli_exit','storage_ready_java_exit'):
    if child and child.poll() is None: child.terminate(); child.wait(timeout=1)
    if fault=='storage_ready_cli_exit': sys.exit(0)
   time.sleep(.02)
 if name=='dc' and fault=='dc_cleanup_failed': signal.signal(signal.SIGTERM,signal.SIG_IGN)
 else: signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
 signal.signal(signal.SIGINT,lambda *_:sys.exit(0))
 while True: time.sleep(.02)
if name=='pg_ctl':
 if args[-1]=='start': sys.exit(0)
 if fault=='cleanup_failed': sys.exit(23)
 pidfile=pathlib.Path(args[args.index('-D')+1])/'postmaster.pid'
 if not pidfile.exists(): sys.exit(0)
 pid=int(pidfile.read_text())
 os.kill(pid,signal.SIGTERM)
if name=='psql':
 print(os.getenv('FIXTURE_PG_VERSION','16.15') if 'SHOW server_version' in ' '.join(args) else '4' if 'count(*)' in ' '.join(args) else '1')
'''


# Each fixture subprocess starts in its own session: its process group ID is its
# PID, and the group holds exactly the tree this test started. These two bounds
# are new and only limit stopping that tree; no existing test limit changed.
FIXTURE_TERM_SECONDS = 5
FIXTURE_KILL_SECONDS = 5


def process_states():
    """Map each PID to (process group, state); a process exiting meanwhile is omitted."""
    states = {}
    if sys.platform == 'linux':
        for entry in os.scandir('/proc'):
            if entry.name.isdigit():
                try:
                    with open(f'/proc/{entry.name}/stat') as handle:
                        fields = handle.read().rsplit(') ', 1)[1].split()
                except (FileNotFoundError, ProcessLookupError):
                    continue  # It exited and was reaped while the table was read.
                states[int(entry.name)] = (int(fields[2]), fields[0])
        return states
    listing = subprocess.run(['/bin/ps', '-A', '-o', 'pid=,pgid=,stat='], capture_output=True, text=True,
                             timeout=10, check=True, env=dict(os.environ, LC_ALL='C'))
    for row in listing.stdout.splitlines():
        pid, group, state = row.split()
        states[int(pid)] = (int(group), state)
    return states


def live_processes(pids):
    """The given PIDs that have not exited. A zombie has exited and holds no port."""
    states = process_states()
    return sorted(pid for pid in pids if pid in states and not states[pid][1].startswith(('Z', 'X')))


def live_group_members(group):
    """Members of one process group that have not exited."""
    states = process_states()
    return live_processes(pid for pid, (owner, _) in states.items() if owner == group)


class FixtureProcesses:
    """Own only subprocess sessions created by this test, even after failure."""

    def __init__(self):
        self.children = []

    def start(self, command, **options):
        child = subprocess.Popen(command, start_new_session=True, **options)
        self.children.append(child)
        return child

    def group_live(self, child):
        """Whether this test's own process group still has a member that has not exited."""
        child.poll()  # Reap an exited leader; only this owner ever waits for it.
        if child.returncode is not None:
            try:
                os.getpgid(child.pid)
            except ProcessLookupError:
                pass  # No process holds the PID, so a group with this ID is still ours.
            else:
                # Linux and Darwin never reissue a PID that still names a process
                # group: a new process here proves this test's group already ended.
                return False
        try:
            os.killpg(child.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            # Darwin answers EPERM when every remaining member has exited and only
            # awaits its reaper. That tree is stopped; a live member is not.
            live = live_group_members(child.pid)
            if live:
                raise RuntimeError(f'live fixture group members cannot be signaled: {live}')
            return False
        return True

    def stop_group(self, child):
        for signum, seconds in ((signal.SIGTERM, FIXTURE_TERM_SECONDS), (signal.SIGKILL, FIXTURE_KILL_SECONDS)):
            if not self.group_live(child):
                return
            try:
                os.killpg(child.pid, signum)
            except (ProcessLookupError, PermissionError):
                pass  # It exited meanwhile; group_live() reports a live member it cannot signal.
            deadline = time.monotonic() + seconds
            census = time.monotonic() + .2
            while self.group_live(child):
                now = time.monotonic()
                if now >= census:
                    # Linux still answers for a group of exited zombies; stop once none is live.
                    if not live_group_members(child.pid):
                        return
                    census = now + 1
                if now >= deadline:
                    break
                time.sleep(.02)
            else:
                return
        live = live_group_members(child.pid)
        if live:
            raise RuntimeError(f'fixture group members survived SIGKILL: {live}')

    def stop(self, child):
        if child not in self.children:
            return
        try:
            self.stop_group(child)
            child.wait(timeout=FIXTURE_KILL_SECONDS)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            raise RuntimeError(f'fixture cleanup pid={child.pid} command={child.args!r} '
                               f'returncode={child.returncode}: {error}') from error
        for stream in (child.stdin, child.stdout, child.stderr):
            if stream is not None:
                stream.close()
        self.children.remove(child)

    def run(self, command, *, capture_output=False, timeout=None, **options):
        """subprocess.run() in an owned session; the whole tree stops before it returns."""
        if capture_output:
            options.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        child = self.start(command, **options)
        try:
            stdout, stderr = child.communicate(timeout=timeout)
        finally:
            self.stop(child)
        return subprocess.CompletedProcess(command, child.returncode, stdout, stderr)

    def close(self):
        # ExitStack continues stopping the other owned sessions if one stop fails.
        with ExitStack() as cleanup:
            for child in self.children[:]:
                cleanup.callback(self.stop, child)


@pytest.fixture
def fixture_processes():
    processes = FixtureProcesses()
    try:
        yield processes
    finally:
        processes.close()


def test_fixture_cleanup_does_not_signal_an_absent_group(fixture_processes, monkeypatch):
    killpg = os.killpg
    signals = []
    def reject_stale_signal(group, signum):
        signals.append(signum)
        if signum:
            raise PermissionError('completed fixture group no longer exists')
        return killpg(group, signum)
    monkeypatch.setattr(os, 'killpg', reject_stale_signal)
    result = fixture_processes.run([sys.executable, '-B', '-c', 'print("completed"); raise SystemExit(7)'],
                                   capture_output=True, text=True, timeout=5)
    assert result.returncode == 7 and result.stdout == 'completed\n'
    assert not any(signals), f'cleanup signaled a completed, absent group: {signals}'
    assert not fixture_processes.children


def test_fixture_cleanup_treats_an_exited_zombie_group_as_stopped(fixture_processes, monkeypatch, tmp_path):
    # The state after a completed run: the leader is reaped and the group's last
    # member has exited but is not yet reaped. Darwin refuses a group signal here
    # with EPERM; that must count as stopped, not mask the test's result. The
    # member's parent escapes to its own session: never this test's to signal.
    record, release = tmp_path / 'record.json', tmp_path / 'release'
    escaped = r'''
import json, os, pathlib, subprocess, sys, time
record, release = map(pathlib.Path, sys.argv[1:3])
member = subprocess.Popen([sys.executable, '-B', '-c', 'pass'], stdout=subprocess.PIPE)
member.stdout.read()  # EOF: the member has exited; it stays an unreaped zombie.
os.setsid()  # Leave the fixture group; the zombie member stays in it.
record.write_text(json.dumps({'escaped': os.getpid(), 'zombie': member.pid}))
deadline = time.monotonic() + 30
while not release.exists() and time.monotonic() < deadline:
    time.sleep(.02)
'''
    leader = fixture_processes.start([sys.executable, '-B', '-c',
                                      'import os, subprocess, sys; subprocess.Popen([sys.executable, "-B", "-c", *sys.argv[1:]]); os._exit(0)',
                                      escaped, str(record), str(release)])
    try:
        deadline = time.monotonic() + 10
        while not record.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        ids = json.loads(record.read_text())
        assert leader.wait(timeout=10) == 0
        while process_states().get(ids['zombie'], (None, ''))[1][:1] != 'Z' and time.monotonic() < deadline:
            time.sleep(.02)
        group, state = process_states()[ids['zombie']]
        assert group == leader.pid and state.startswith('Z'), (group, state)
        assert live_processes([ids['escaped']]) == [ids['escaped']]
        killpg = os.killpg
        signals = []
        def observed(group, signum):
            signals.append(group)
            return killpg(group, signum)
        with monkeypatch.context() as patch:
            patch.setattr(os, 'killpg', observed)
            fixture_processes.stop(leader)
        assert leader not in fixture_processes.children
        assert set(signals) <= {leader.pid}, f'cleanup signaled a group it did not start: {signals}'
        assert live_processes([ids['escaped']]) == [ids['escaped']], 'cleanup reached a process outside its group'
    finally:
        release.touch()
        if record.exists():
            escaped_pid = json.loads(record.read_text())['escaped']
            deadline = time.monotonic() + 10
            while live_processes([escaped_pid]) and time.monotonic() < deadline:
                time.sleep(.02)


def test_fixture_cleanup_reports_a_live_group_it_may_not_signal(fixture_processes, monkeypatch):
    child = fixture_processes.start([sys.executable, '-B', '-c', 'import signal; signal.pause()'])
    def deny(group, signum):
        raise PermissionError(f'signal {signum} to group {group} denied')
    try:
        with monkeypatch.context() as patch:
            patch.setattr(os, 'killpg', deny)
            with pytest.raises(RuntimeError, match=rf'pid={child.pid}.*signal\.pause.*cannot be signaled: \[{child.pid}\]'):
                fixture_processes.stop(child)
        assert child.poll() is None, 'denied cleanup unexpectedly stopped the control'
        assert child in fixture_processes.children, 'failed cleanup abandoned its live child'
    finally:
        fixture_processes.stop(child)


def test_fixture_cleanup_never_signals_a_reused_leader_pid(fixture_processes, monkeypatch):
    child = fixture_processes.start([sys.executable, '-B', '-c', 'pass'])
    child.wait(timeout=5)
    signals = []
    with monkeypatch.context() as patch:
        # Once wait() reaps our leader, a live process at that PID belongs to
        # another owner, even if it leads a new group with the same ID.
        patch.setattr(os, 'getpgid', lambda pid: pid)
        patch.setattr(os, 'killpg', lambda group, signum: signals.append(signum))
        fixture_processes.stop(child)
    assert not signals, f'cleanup signaled an unverified replacement: {signals}'
    assert not fixture_processes.children


def test_fixture_cleanup_signals_descendants_after_leader_is_reaped(monkeypatch):
    from types import SimpleNamespace
    # Model an exited/reaped leader with a still-live group. No real PID is
    # targeted: the signal boundary is replaced before stop() is called.
    child = SimpleNamespace(pid=12345, args=['exited-fixture'], returncode=0, poll=lambda: 0,
                            wait=lambda **_: 0, stdin=None, stdout=None, stderr=None)
    processes = FixtureProcesses()
    processes.children.append(child)
    signals = []
    def no_leader(pid):
        raise ProcessLookupError()
    def descendant_group(group, signum):
        assert group == child.pid
        if signals:
            raise ProcessLookupError()
        if signum:
            signals.append(signum)
    monkeypatch.setattr(os, 'getpgid', no_leader)
    monkeypatch.setattr(os, 'killpg', descendant_group)
    processes.stop(child)
    assert signals == [signal.SIGTERM], 'reaping the leader abandoned its descendant group'
    assert not processes.children


@pytest.fixture
def shell_fixture(tmp_path, fixture_processes):
    root = tmp_path / 'repo'
    (root / 'scripts/data').mkdir(parents=True)
    (root / 'scripts/ci').mkdir()
    for source in DATA.glob('*'):
        if source.is_file():
            shutil.copyfile(source, root / 'scripts/data' / source.name)
    shutil.copyfile(ROOT / 'scripts/ci/engine_contract_gate.py', root / 'scripts/ci/engine_contract_gate.py')
    (root / 'dataconnect/sql').mkdir(parents=True)
    (root / 'storage.rules').write_text('synthetic fixture')
    (root / 'bin').mkdir()
    for name in ['node','python','dc','postgres','initdb','pg_ctl','createdb','psql','firebase','java','ps']:
        path = root / 'bin' / name
        path.write_text(STANDIN.replace('#!PYTHON', '#!' + sys.executable))
        path.chmod(0o700)
    (root/'.venv/bin').mkdir(parents=True)
    shutil.copyfile(root/'bin/python',root/'.venv/bin/python')
    (root/'.venv/bin/python').chmod(0o700)
    # The existing readback helper's real shell is controlled as a subprocess.
    (root / 'scripts/data/source-asset-read-back.sh').write_text('#!/bin/bash\nprintf "1\\n"\n')
    seed = {'organization':'00000000-0000-4000-8000-000000000001','collection':'00000000-0000-4000-8000-000000000002','uid':'synthetic-reviewer','organization_active':True,'collection_active':True,'role':'reviewer','can_view_sensitive':True}
    (root / 'seed.json').write_text(json.dumps(seed))
    preflight={'tools':{},'runtime':{'postgres_server':'16.15'},'cache':{'mode':'normal','directory_private':True,'directory_fresh':True,'entries_before':0,'restore':'miss'}}
    (root / 'preflight.json').write_text(json.dumps(preflight))
    class Environment(dict):
        def __repr__(self):
            return '<controlled subprocess environment>'
    env = Environment(os.environ, PATH=str(root / 'bin') + ':' + os.environ['PATH'], REAL_NODE=shutil.which('node'), FIXTURE_ROOT=str(root),
               POSTGRES_BIN=str(root / 'bin'), DATACONNECT_EMULATOR_BIN=str(root / 'bin/dc'),
               FIREBASE_CLI_BIN=str(root / 'bin/firebase'), STORAGE_RULES_RUNTIME_JAR=str(root / 'runtime.jar'),
               SPECIMEN_TEST_SQL_EMULATOR='true', ENGINE_TOOLS_DIR=str(root / 'tools'), TMPDIR=str(tmp_path),
               ENGINE_CONTRACT_LIFECYCLE=str(root / 'lifecycle.json'), ENGINE_CONTRACT_PROCESS_TOKEN='controlled-fixture')
    env.processes = fixture_processes
    # Hold all three reservations together so this test's ports are distinct.
    # Release them immediately before the controlled wrappers need to bind.
    with ExitStack() as reservations:
        for key in ('SPECIMEN_TEST_PG_PORT', 'SPECIMEN_TEST_DC_PORT', 'SPECIMEN_TEST_STORAGE_PORT'):
            listener = reservations.enter_context(socket.socket())
            listener.bind(('127.0.0.1', 0))
            env[key] = str(listener.getsockname()[1])
    for key in ['GOOGLE_APPLICATION_CREDENTIALS','FIREBASE_TOKEN','CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE','SPECIMEN_SQL_EMULATOR_HOST','FIREBASE_DATACONNECT_EMULATOR_HOST']:
        env.pop(key,None)
    (root / 'runtime.jar').write_bytes(b'fixture')
    return root, env


def run_shell(fixture, fault='', storage=False):
    root, env = fixture
    command = ['bash', str(root / 'scripts/data' / ('test-storage.sh' if storage else 'test-postgres.sh')),
               '--contract-output' if storage else '--python-contract-output', str(root / ('storage-out' if storage else 'sql-out'))]
    return env.processes.run(command, env=dict(env, FIXTURE_FAULT=fault), capture_output=True, text=True, timeout=35)


@pytest.mark.parametrize('storage', [False, True], ids=['sql', 'storage'])
@pytest.mark.parametrize('failure', ['assertion', 'timeout'])
def test_fixture_failure_stops_process_tree_and_releases_ports(tmp_path, storage, failure):
    # A separate pytest run fails while its fixture tree is live: a forced
    # assertion (only the fixture finalizer can stop that tree) or a forced
    # subprocess wait timeout (run_shell's own cleanup). Afterwards nothing it
    # started may be alive and its ports must bind. This test's emergency
    # cleanup is deliberately independent of the code under test.
    probe = tmp_path / 'test_interrupted.py'
    probe.write_text('''
import importlib.util, json, os, pathlib, subprocess, time
spec = importlib.util.spec_from_file_location('harness', os.environ['HARNESS_MODULE'])
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)
shell_fixture = harness.shell_fixture
if hasattr(harness, 'fixture_processes'):
    fixture_processes = harness.fixture_processes

def test_interrupted(shell_fixture, monkeypatch):
    root, env = shell_fixture
    storage = os.environ['PROBE_STORAGE'] == 'True'
    env.update(FIXTURE_STANDALONE='true')
    if storage:
        env.pop('ENGINE_CONTRACT_PROCESS_TOKEN')
        env.pop('SPECIMEN_TEST_SQL_EMULATOR')
    marker = root / ('storage-assertions-running' if storage else 'python-running')
    original = subprocess.Popen.communicate
    def interrupted(child, *args, **kwargs):
        if any(str(arg).endswith('test-storage.sh' if storage else 'test-postgres.sh') for arg in child.args):
            pathlib.Path(os.environ['PROBE_RECORD']).write_text(json.dumps({
                'root': str(root), 'pid': child.pid, 'group': os.getpgid(child.pid),
                'ports': [int(env[key]) for key in ('SPECIMEN_TEST_PG_PORT', 'SPECIMEN_TEST_DC_PORT', 'SPECIMEN_TEST_STORAGE_PORT')]}))
            deadline = time.monotonic() + 15
            while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            assert marker.exists(), 'failure probe never reached its live fixture tree'
            if os.environ['PROBE_FAILURE'] != 'timeout':
                raise AssertionError('forced fixture assertion')
            raise subprocess.TimeoutExpired(child.args, .001)
        return original(child, *args, **kwargs)
    monkeypatch.setattr(subprocess.Popen, 'communicate', interrupted)
    if os.environ['PROBE_FAILURE'] == 'assertion':
        command = ['bash', str(root / 'scripts/data' / ('test-storage.sh' if storage else 'test-postgres.sh')),
                   '--contract-output' if storage else '--python-contract-output', str(root / ('storage-out' if storage else 'sql-out'))]
        options = dict(env=dict(env, FIXTURE_FAULT='hold_storage' if storage else 'hold_python'),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        child = env.processes.start(command, **options) if hasattr(env, 'processes') else subprocess.Popen(command, start_new_session=True, **options)
        interrupted(child)  # Only the pytest fixture finalizer can stop this tree.
    harness.run_shell(shell_fixture, 'hold_storage' if storage else 'hold_python', storage=storage)
''')
    # Baseline runs also use private ports, so reproducing the missing teardown
    # cannot occupy another test's default listener.
    with socket.socket() as pg, socket.socket() as dc, socket.socket() as store:
        for listener in (pg, dc, store):
            listener.bind(('127.0.0.1', 0))
        ports = [listener.getsockname()[1] for listener in (pg, dc, store)]
    record = tmp_path / 'owner.json'
    env = dict(os.environ, HARNESS_MODULE=str(Path(__file__).resolve()),
               PROBE_STORAGE=str(storage), PROBE_FAILURE=failure, PROBE_RECORD=str(record),
               PYTEST_ADDOPTS='', PYTHONDONTWRITEBYTECODE='1',
               SPECIMEN_TEST_PG_PORT=str(ports[0]), SPECIMEN_TEST_DC_PORT=str(ports[1]),
               SPECIMEN_TEST_STORAGE_PORT=str(ports[2]))
    def answers(group):
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            pass  # Darwin: only exited members remain, or a member denies us.
        return bool(live_group_members(group))
    groups = set()
    with (tmp_path / 'pytest.log').open('w') as log:
        child = subprocess.Popen([sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                                  '--confcutdir=' + str(tmp_path), '--basetemp=' + str(tmp_path / 'nested'), str(probe)],
                                 env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        groups.add(child.pid)
        try:
            assert child.wait(timeout=35) == 1, 'failure probe must fail its inner test'
            output = (tmp_path / 'pytest.log').read_text()
            assert ('TimeoutExpired' if failure == 'timeout' else 'forced fixture assertion') in output, output
            assert record.exists(), output
            owner = json.loads(record.read_text())
            assert owner['group'] in (child.pid, owner['pid']), owner
            groups.add(owner['group'])
            instances = list((Path(owner['root']) / 'instances').glob('*.json'))
            assert instances, 'probe did not start any fixture engines'
            started = {owner['pid'], *(json.loads(entry.read_text())['pid'] for entry in instances)}
            survivors = live_processes(started)
            assert not survivors, f'{failure} left fixture processes alive: {survivors}'
            assert not live_group_members(owner['group']), f'{failure} left its process group alive'
            for port in owner['ports']:
                with socket.socket() as listener:
                    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    listener.bind(('127.0.0.1', port))
        finally:
            # The negative control must also clean up when run against the
            # original file or a mutant with its teardown kill removed. Only
            # the probe's own session and the wrapper session it recorded count.
            try:
                recorded = json.loads(record.read_text())
            except (FileNotFoundError, ValueError):
                recorded = {}
            if recorded.get('group') in (child.pid, recorded.get('pid')):
                groups.add(recorded['group'])
            for signum in (signal.SIGTERM, signal.SIGKILL):
                for group in groups:
                    if answers(group):
                        try:
                            os.killpg(group, signum)
                        except (ProcessLookupError, PermissionError):
                            pass  # Its last live member exited meanwhile.
                deadline = time.monotonic() + 5
                while any(answers(group) for group in groups) and time.monotonic() < deadline:
                    child.poll()
                    time.sleep(.05)
            child.wait(timeout=5)


def test_fixture_ports_are_private(shell_fixture):
    _, env = shell_fixture
    ports = [int(env[key]) for key in ('SPECIMEN_TEST_PG_PORT', 'SPECIMEN_TEST_DC_PORT', 'SPECIMEN_TEST_STORAGE_PORT')]
    assert len(set(ports)) == 3, f'fixture ports alias each other: {ports}'
    assert not set(ports) & {5559, 9509, 9299}, f'fixture reused a shared default port: {ports}'


@pytest.mark.parametrize('fault', ['compile_errors_exit0','seed_missing','seed_mismatch','readiness_failed','false_readiness','port_mismatch'])
def test_sql_wrapper_requires_compile_seed_and_readiness(shell_fixture, fault):
    if fault=='port_mismatch':
        shell_fixture[1]['SPECIMEN_SQL_EMULATOR_HOST']='127.0.0.1:9998'
    result = run_shell(shell_fixture, fault)
    assert result.returncode != 0, f'{fault} was accepted: {result.stdout} {result.stderr}'
    assert ('readiness' if fault=='false_readiness' else fault.split('_')[0]) in result.stderr.lower(), result.stderr


@pytest.mark.parametrize('errors_member', ['absent', 'null'])
def test_sql_wrapper_accepts_metadata_only_compile(shell_fixture, errors_member):
    # Firebase 15.8.0 treats errors as optional. This metadata shape is a
    # response-compatibility control, not qualification of an engine version.
    response = {'metadata': {'primaryDataSource': {'postgres': {'requiredExtensions': ['uuid-ossp']}}}}
    if errors_member == 'null':
        response['errors'] = None
    root, env = shell_fixture
    env['FIXTURE_COMPILE_RESPONSE'] = json.dumps(response)
    result = run_shell(shell_fixture)
    assert result.returncode == 0, result.stdout + result.stderr
    lifecycle = json.loads((root / 'lifecycle.json').read_text())
    selection = json.loads((DATA / 'engine-contract-selection.json').read_text())
    assert [row['id'] for row in lifecycle['stages']] == [id for id in selection['stages'] if not id.startswith('storage.')]
    assert [row['id'] for row in lifecycle['node_events']] == selection['connector_groups']
    assert lifecycle['seed'] == json.loads((root / 'seed.json').read_text())
    assert lifecycle['cleanup']['ports_free_after'] is True


@pytest.mark.parametrize('response', [
    pytest.param('{', id='invalid-json'),
    pytest.param('null', id='null-result'),
    pytest.param('[]', id='array-result'),
    pytest.param('"success"', id='string-result'),
    pytest.param('1', id='number-result'),
    pytest.param('true', id='boolean-result'),
    pytest.param('{"errors": {}}', id='object-errors'),
    pytest.param('{"errors": ""}', id='string-errors'),
    pytest.param('{"errors": false}', id='boolean-errors'),
    pytest.param('{"errors": 0}', id='number-errors'),
])
def test_sql_wrapper_rejects_malformed_compile_output(shell_fixture, response):
    root, env = shell_fixture
    env['FIXTURE_COMPILE_RESPONSE'] = response
    result = run_shell(shell_fixture)
    assert result.returncode != 0, f'malformed compile output accepted: {response}\n{result.stdout} {result.stderr}'
    assert 'sql.compile' in result.stderr, result.stderr
    lifecycle = json.loads((root / 'lifecycle.json').read_text())
    assert [(row['id'], row['outcome']) for row in lifecycle['stages']] == [
        ('preflight', 'passed'), ('sql.compile', 'failed'), ('sql.cleanup', 'passed'),
    ]
    assert 'initdb' not in (root / 'calls.jsonl').read_text(), 'malformed compile reached PostgreSQL initialization'


@pytest.mark.parametrize('fault,code', [('test_failed',17),('cleanup_failed',1),('dc_cleanup_failed',1)])
def test_sql_wrapper_preserves_test_failure_and_fails_cleanup(shell_fixture, fault, code):
    result=run_shell(shell_fixture, fault)
    assert result.returncode == code, result.stdout + result.stderr
    calls=(shell_fixture[0]/'calls.jsonl').read_text()
    assert 'pg_ctl' in calls, 'owned PostgreSQL cleanup was not attempted'


@pytest.mark.parametrize('mode',['normal','cold'])
def test_sql_wrapper_complete_original_sequence(shell_fixture,mode):
    preflight=shell_fixture[0]/'preflight.json'
    evidence=json.loads(preflight.read_text())
    if mode=='cold': evidence['cache'].update(mode='cold',restore='bypassed')
    preflight.write_text(json.dumps(evidence))
    shell_fixture[1]['ENGINE_CACHE_MODE']=mode
    result=run_shell(shell_fixture)
    assert result.returncode==0, result.stdout+result.stderr
    lifecycle=json.loads((shell_fixture[0]/'lifecycle.json').read_text())
    selection=json.loads((DATA/'engine-contract-selection.json').read_text())
    expected=[id for id in selection['stages'] if not id.startswith('storage.')]
    assert [row['id'] for row in lifecycle['stages']]==expected
    assert [row['id'] for row in lifecycle['node_events']]==selection['connector_groups']
    assert lifecycle['seed']==json.loads((shell_fixture[0]/'seed.json').read_text())
    assert lifecycle['cleanup']['ports_free_after'] is True


@pytest.mark.parametrize('fault', [*json.loads((ROOT / 'scripts/data/engine-contract-selection.json').read_text())['storage_assertions'], 'cleanup_failed'])
def test_storage_wrapper_requires_all_denial_ids_and_cleanup(shell_fixture, fault):
    # Supply a passing SQL part first, exactly as the combined hosted command does.
    result=run_shell(shell_fixture)
    assert result.returncode==0, result.stderr
    if fault=='cleanup_failed':
        # A live owned port left behind must be a cleanup failure. Fixture Java
        # ignores TERM, requiring fallback termination and a failing outcome.
        java=shell_fixture[0]/'bin/java'
        java.write_text(java.read_text().replace("signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))", "signal.signal(signal.SIGTERM,signal.SIG_IGN)"))
    result=run_shell(shell_fixture, fault, storage=True)
    assert result.returncode != 0, result.stdout+result.stderr
    assert ('cleanup' if fault=='cleanup_failed' else 'inventory mismatch') in result.stderr.lower(), result.stderr
    assert 'storage-test.mjs' in (shell_fixture[0]/'calls.jsonl').read_text(), 'failure occurred before assertions'


@pytest.mark.parametrize('layout',['direct','standalone'])
def test_storage_wrapper_complete_inventory(shell_fixture,layout):
    if layout=='standalone': shell_fixture[1]['FIXTURE_STANDALONE']='true'
    assert run_shell(shell_fixture).returncode==0
    result=run_shell(shell_fixture,storage=True)
    assert result.returncode==0, result.stdout+result.stderr
    lifecycle=json.loads((shell_fixture[0]/'lifecycle.json').read_text())
    selection=json.loads((DATA/'engine-contract-selection.json').read_text())
    assert [r['id'] for r in lifecycle['stages']]==selection['stages']
    assert [r['id'] for r in lifecycle['node_events']]==selection['connector_groups']+selection['storage_assertions']
    assert [r['id'] for r in lifecycle['processes']]==selection['processes']
    if layout=='standalone': assert_storage_tree_stopped(shell_fixture,lifecycle)


def assert_storage_tree_stopped(fixture,lifecycle,cleanup='passed'):
    root,_=fixture
    diagnostics=json.dumps({'cleanup':lifecycle['cleanup'],'storage_processes':lifecycle['storage_processes']},sort_keys=True)
    pids=json.loads((root/'standalone-pids.json').read_text())
    if (root/'java-pid.json').exists():
        runtime=json.loads((root/'java-pid.json').read_text())
        if runtime['pid']: pids['java']=runtime['pid']
        if runtime.get('probe'): pids['probe']=runtime['probe']
    for pid in pids.values():
        with pytest.raises(ProcessLookupError):
            os.kill(pid,0)
    assert not (root/'launcher-signals.jsonl').exists(),'shutdown must reach the actual forked CLI, without relying on launcher signal forwarding; '+diagnostics
    rows=lifecycle['storage_processes']
    assert {row['pid'] for row in rows}==set(pids.values()),diagnostics
    assert all(row['birth_id'] and row['stopped'] and row['waited'] and row['ended_ns']>=row['started_ns'] for row in rows),diagnostics
    cli=next(row for row in rows if row['pid']==pids['cli'])
    launcher=next(row for row in rows if row['pid']==pids['launcher'])
    assert cli['parent_pid']==launcher['pid'] and cli['parent_birth_id']==launcher['birth_id'],diagnostics
    if 'java' in pids:
        java=next(row for row in rows if row['pid']==pids['java'])
        assert java['parent_pid']==cli['pid'] and java['parent_birth_id']==cli['birth_id'],diagnostics
    assert lifecycle['cleanup']['outcome']==cleanup and lifecycle['cleanup']['survivors']==[],diagnostics


@pytest.mark.parametrize('fault,reason',[('storage_no_java','Storage Java child missing'),('storage_download','Storage CLI attempted download')])
def test_storage_standalone_startup_failure_cleans_partial_tree(shell_fixture,fault,reason):
    root,env=shell_fixture
    env['FIXTURE_STANDALONE']='true'
    assert run_shell(shell_fixture).returncode==0
    result=run_shell(shell_fixture,fault,storage=True)
    assert result.returncode!=0 and reason in result.stderr,result.stdout+result.stderr
    lifecycle=json.loads((root/'lifecycle.json').read_text())
    assert_storage_tree_stopped(shell_fixture,lifecycle,cleanup='failed' if fault=='storage_download' else 'passed')
    assert 'storage-test.mjs' not in (root/'calls.jsonl').read_text()


def test_storage_registration_failure_still_owns_and_stops_tree(shell_fixture):
    root,env=shell_fixture
    env['FIXTURE_STANDALONE']='true'
    assert run_shell(shell_fixture).returncode==0
    result=run_shell(shell_fixture,'storage_registration_failed',storage=True)
    assert result.returncode==29,result.stdout+result.stderr
    lifecycle=json.loads((root/'lifecycle.json').read_text())
    assert_storage_tree_stopped(shell_fixture,lifecycle,cleanup='failed')
    assert 'storage-test.mjs' not in (root/'calls.jsonl').read_text()


@pytest.mark.parametrize('phase',['startup','assertions'])
@pytest.mark.parametrize('signum,expected',[(signal.SIGINT,130),(signal.SIGTERM,143)])
def test_storage_standalone_interruption_cleans_complete_tree(shell_fixture,phase,signum,expected):
    root,env=shell_fixture
    env.update(FIXTURE_STANDALONE='true',FIXTURE_JAVA_PROBE='true')
    assert run_shell(shell_fixture).returncode==0
    fault='storage_no_java' if phase=='startup' else 'hold_storage'
    marker=root/('storage-cli-running' if phase=='startup' else 'storage-assertions-running')
    command=['bash',str(root/'scripts/data/test-storage.sh'),'--contract-output',str(root/'storage-out')]
    child=env.processes.start(command,env=dict(env,FIXTURE_FAULT=fault),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        deadline=time.monotonic()+15
        while not marker.exists() and child.poll() is None and time.monotonic()<deadline: time.sleep(.02)
        assert marker.exists(),'interruption control did not reach '+phase
        child.send_signal(signum)
        stdout,stderr=child.communicate(timeout=15)
        assert child.returncode==expected,stdout+stderr
        lifecycle=json.loads((root/'lifecycle.json').read_text())
        assert_storage_tree_stopped(shell_fixture,lifecycle)
    finally:
        if child.poll() is None:
            child.terminate(); child.communicate(timeout=15)


@pytest.mark.parametrize('script', ['test-postgres.sh','test-storage.sh'])
def test_wrappers_reject_unknown_arguments(shell_fixture, script):
    root,env=shell_fixture
    result=env.processes.run(['bash',str(root/'scripts/data'/script),'--unknown'],env=dict(env,FIXTURE_FAULT='unknown_argument'),capture_output=True,text=True,timeout=5)
    assert result.returncode==2
    assert 'unknown argument' in result.stderr.lower()


def assert_wrapper_rejects_before_work(fixture, script, arguments):
    root, env = fixture
    scratch = root.parent / 'wrapper-scratch'
    scratch.mkdir()
    before = set(root.rglob('*'))
    result = env.processes.run(['bash', str(root / 'scripts/data' / script), *arguments],
                            env=dict(env, TMPDIR=str(scratch)),
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 2, result.stdout + result.stderr
    assert not result.stdout, 'rejected configuration printed stdout'
    assert result.stderr.strip(), 'rejection must explain the invalid configuration'
    assert not (root / 'calls.jsonl').exists(), 'rejected configuration started Node or an engine'
    assert set(root.rglob('*')) == before, 'rejected configuration wrote output or scratch files'
    assert not list(scratch.iterdir()), 'rejected configuration created a temporary directory'


@pytest.mark.parametrize('script,flag', [
    ('test-postgres.sh', '--python-contract-output'),
    ('test-storage.sh', '--contract-output'),
])
@pytest.mark.parametrize('variable', [
    'SPECIMEN_TEST_PG_PORT', 'SPECIMEN_TEST_DC_PORT', 'SPECIMEN_TEST_STORAGE_PORT',
])
@pytest.mark.parametrize('port', ['3000', '8000', '0003000', '0', '1024', '65536', '-1', 'bad', '1.5', '99999999999999999999'])
def test_wrappers_validate_all_ports_before_contract_output(shell_fixture, script, flag, variable, port):
    root, env = shell_fixture
    env[variable] = port
    assert_wrapper_rejects_before_work(shell_fixture, script, [flag, str(root / 'new-output')])


@pytest.mark.parametrize('script,flag', [
    ('test-postgres.sh', '--python-contract-output'),
    ('test-storage.sh', '--contract-output'),
])
@pytest.mark.parametrize('variable,port', [
    ('SPECIMEN_TEST_PG_PORT', '9509'),
    ('SPECIMEN_TEST_DC_PORT', '9299'),
    ('SPECIMEN_TEST_STORAGE_PORT', '5559'),
    ('SPECIMEN_TEST_STORAGE_PORT', '05559'),
])
def test_wrappers_reject_aliased_ports_before_contract_output(shell_fixture, script, flag, variable, port):
    root, env = shell_fixture
    for key in ('SPECIMEN_TEST_PG_PORT', 'SPECIMEN_TEST_DC_PORT', 'SPECIMEN_TEST_STORAGE_PORT'):
        env.pop(key)
    env[variable] = port
    assert_wrapper_rejects_before_work(shell_fixture, script, [flag, str(root / 'new-output')])


@pytest.mark.parametrize('script,flag,other', [
    ('test-postgres.sh', '--python-contract-output', '--contract-output'),
    ('test-storage.sh', '--contract-output', '--python-contract-output'),
])
@pytest.mark.parametrize('case', ['unknown', 'missing', 'flag-value', 'duplicate', 'extra', 'wrong-flag'])
def test_wrappers_validate_every_argument_before_work(shell_fixture, script, flag, other, case):
    root, _ = shell_fixture
    output = str(root / 'new-output')
    arguments = {
        'unknown': ['--unknown'],
        'missing': [flag],
        'flag-value': [flag, '--unknown'],
        'duplicate': [flag, output, flag, output],
        'extra': [flag, output, 'extra'],
        'wrong-flag': [other, output],
    }[case]
    assert_wrapper_rejects_before_work(shell_fixture, script, arguments)


def test_sql_wrapper_rejects_omitted_original_stage(shell_fixture):
    reporter=shell_fixture[0]/'scripts/data/engine-contract-reporter.mjs'
    before=reporter.read_text()
    assert before.count("['paging','search','checksum']")==1
    reporter.write_text(before.replace("['paging','search','checksum']", "['paging','checksum']"))
    result=run_shell(shell_fixture)
    assert result.returncode!=0
    assert 'stage inventory mismatch' in result.stderr


@pytest.mark.parametrize('mutated', [False,True])
def test_storage_real_node_assertions_and_independent_denials(tmp_path, mutated, fixture_processes):
    # Response fault model only: actual storage.rules mutant needs hosted Java.
    loader=tmp_path/'fetch.mjs'
    events=tmp_path/'events.jsonl'
    probes=tmp_path/'probes.jsonl'
    loader.write_text(r'''
import {appendFileSync} from 'node:fs';
const objects=new Map();
globalThis.fetch=async (url,options={})=> {
 const u=new URL(url), method=options.method||'GET';
 const owner=options.headers?.Authorization==='Bearer owner';
 const name=u.searchParams.get('name')||decodeURIComponent(u.pathname.split('/o/')[1]||'');
 if(!owner) {
  appendFileSync(process.env.PROBES,JSON.stringify({method,name})+'\n');
  if(process.env.ALLOW_ALL==='true') {
   if(method==='DELETE') objects.delete(name);
   if(method==='POST') objects.set(name,new Uint8Array(Buffer.from(options.body)));
  }
  return new Response('response fault',{status:process.env.ALLOW_ALL==='true'?200:403});
 }
 if(method==='POST') {objects.set(name,new Uint8Array(options.body));return new Response('{}',{status:200});}
 return new Response(objects.get(name),{status:200});
};
''')
    result=fixture_processes.run(['node','--import',str(loader),str(DATA/'storage-test.mjs')],env=dict(os.environ,
                          ENGINE_CONTRACT_NODE_EVENTS=str(events),PROBES=str(probes),ALLOW_ALL=str(mutated).lower()),
                          capture_output=True,text=True,timeout=10)
    rows=[json.loads(line) for line in events.read_text().splitlines()]
    assert len(probes.read_text().splitlines())==10, 'not every independent denial was exercised'
    if mutated:
        assert result.returncode!=0
        assert 'storage.anonymous.read: GET unexpected 200' in result.stderr
        assert 'AggregateError: Storage denial assertions failed' in result.stderr, 'primary denial failures were hidden by later diagnostics'
        assert len(rows)==3, 'failed assertions must not emit passed events'
    else:
        assert result.returncode==0, result.stderr
        assert [row['id'] for row in rows]==json.loads((ROOT/'scripts/data/engine-contract-selection.json').read_text())['storage_assertions']


@pytest.mark.parametrize('fault', ['none','organization','collection','uid','role','organization_active','collection_active','can_view_sensitive','missing'])
def test_seed_real_node_requires_exact_readback(tmp_path, fault, fixture_processes):
    loader=tmp_path/'seed-fetch.mjs'
    seed=tmp_path/'seed.json'
    loader.write_text(r'''
const org='00000000-0000-4000-8000-000000000001', col='00000000-0000-4000-8000-000000000002';
let count=0;
globalThis.fetch=async()=> {
 if(count++===0) return new Response(JSON.stringify({data:{}}),{status:200});
 const organization={organizationId:org,uid:'synthetic-reviewer',active:true};
 const collection={organizationId:org,collectionId:col,uid:'synthetic-reviewer',active:true,role:'reviewer',canViewSensitive:true};
 switch(process.env.SEED_FAULT) {
 case 'organization': organization.organizationId=col;break;
 case 'collection': collection.collectionId=org;break;
 case 'uid': collection.uid='outsider';break;
 case 'role': collection.role='outsider';break;
 case 'organization_active': organization.active=false;break;
 case 'collection_active': collection.active=false;break;
 case 'can_view_sensitive': collection.canViewSensitive=false;break;
 }
 return new Response(JSON.stringify({data:{organizationMembers:[organization],collectionMembers:process.env.SEED_FAULT==='missing'?[]:[collection]}}),{status:200});
};
''')
    result=fixture_processes.run(['node','--import',str(loader),str(DATA/'seed-integration.mjs')],env=dict(os.environ,
                          SEED_FAULT=fault,ENGINE_CONTRACT_SEED_REPORT=str(seed)),capture_output=True,text=True,timeout=10)
    if fault=='none':
        assert result.returncode==0, result.stderr
        assert json.loads(seed.read_text())['role']=='reviewer'
    else:
        assert result.returncode!=0
        assert not seed.exists(), 'a mismatched readback must not publish a seed result'


@pytest.mark.parametrize('signum,expected',[(signal.SIGINT,130),(signal.SIGTERM,143)])
def test_sql_signal_stops_owned_engines_and_waits(shell_fixture,signum,expected):
    root,env=shell_fixture
    command=['bash',str(root/'scripts/data/test-postgres.sh'),'--python-contract-output',str(root/'sql-out')]
    child=env.processes.start(command,env=dict(env,FIXTURE_FAULT='hold_python'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        deadline=time.monotonic()+15
        while not (root/'python-running').exists() and child.poll() is None and time.monotonic()<deadline:
            time.sleep(.02)
        assert (root/'python-running').exists(),'signal probe did not reach the live seeded Python stage'
        child.send_signal(signum)
        stdout,stderr=child.communicate(timeout=10)
        assert child.returncode==expected,stdout+stderr
        lifecycle=json.loads((root/'lifecycle.json').read_text())
        assert lifecycle['cleanup']['outcome']=='passed'
        assert lifecycle['cleanup']['survivors']==[]
        assert [row['id'] for row in lifecycle['processes']]==['postgres','dataconnect.initial']
    finally:
        if child.poll() is None:
            child.terminate()
            child.communicate(timeout=10)


def test_storage_standalone_is_diagnostic(shell_fixture):
    root,env=shell_fixture
    env.pop('ENGINE_CONTRACT_PROCESS_TOKEN')
    env.pop('SPECIMEN_TEST_SQL_EMULATOR')
    result=run_shell(shell_fixture,storage=True)
    assert result.returncode==0,result.stdout+result.stderr
    lifecycle=json.loads((root/'lifecycle.json').read_text())
    assert lifecycle['engine_flag']=='diagnostic'
    assert [row['id'] for row in lifecycle['stages']]==['storage.start','storage.ready','storage.assertions','storage.cleanup']


@pytest.mark.parametrize('version,accepted',[('16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)',True),('16.16 (Ubuntu 16.16-0ubuntu0.24.04.1)',True),('15.15',False),('17.6',False),('16garbage',False)])
def test_sql_server_version_enforces_approved_major(shell_fixture,version,accepted):
    shell_fixture[1]['FIXTURE_PG_VERSION']=version
    if accepted:
        report=shell_fixture[0]/'preflight.json'
        evidence=json.loads(report.read_text())
        evidence['runtime']['postgres_server']=version.split()[0]
        report.write_text(json.dumps(evidence))
    result=run_shell(shell_fixture)
    if accepted:
        assert result.returncode==0,result.stdout+result.stderr
        assert json.loads((shell_fixture[0]/'lifecycle.json').read_text())['postgres_server_version']==version
    else:
        assert result.returncode!=0
        assert 'PostgreSQL server version mismatch' in result.stderr


@pytest.mark.parametrize('kind,override',[('sql','SPECIMEN_TEST_DATACONNECT_CONFIG'),('storage','SPECIMEN_TEST_STORAGE_RULES')])
def test_scratch_configuration_cannot_qualify_canonical(shell_fixture,kind,override):
    if kind=='storage':
        assert run_shell(shell_fixture).returncode==0
    root,env=shell_fixture
    env[override]=str(root/('dataconnect' if kind=='sql' else 'storage.rules'))
    result=run_shell(shell_fixture,storage=kind=='storage')
    assert result.returncode!=0
    assert 'diagnostic' in result.stderr and 'cannot qualify' in result.stderr


def test_storage_registers_jar_runtime_instead_of_java_version_probe(shell_fixture):
    assert run_shell(shell_fixture).returncode==0
    root,env=shell_fixture
    env['FIXTURE_JAVA_PROBE']='true'
    result=run_shell(shell_fixture,storage=True)
    assert result.returncode==0,result.stdout+result.stderr
    observed=json.loads((root/'lifecycle.json').read_text())
    runtime=json.loads((root/'java-pid.json').read_text())
    receipt=next(row for row in observed['processes'] if row['id']=='storage.java')
    assert receipt['pid']==runtime['pid'],'registered Java version probe instead of the verified Storage JAR runtime'
    assert receipt['pid']!=runtime['probe']


@pytest.mark.parametrize('case',['owned','reused','gone','missing'])
@pytest.mark.parametrize('requested',[None,2,15,9])
def test_forced_java_cleanup_binds_birth_and_pidfd(tmp_path,case,requested, fixture_processes):
    # No OS signal is issued. Native pidfd/signal calls are replaced only in a
    # disposable child, and a different birth must never receive a signal.
    result=fixture_processes.run(['node','--input-type=module','-e',
                          f"import {{JAVA_CLEANUP_CODE}} from {json.dumps((DATA/'engine-contract-reporter.mjs').as_uri())}; console.log(JSON.stringify(JAVA_CLEANUP_CODE));"],
                          capture_output=True,text=True,timeout=5)
    assert result.returncode==0,result.stderr
    code=json.loads(result.stdout)
    gate=tmp_path/'gate.py'
    gate.write_text('import json, os\nfrom pathlib import Path\ndef read_json(p): return json.loads(Path(p).read_text())\ndef require(c,m):\n if not c: raise ValueError(m)\ndef process_birth(pid):\n c=os.environ["PIDFD_CASE"]\n return None if c=="gone" else ("known-birth" if c=="owned" else "different-birth",123)\n')
    receipt=tmp_path/'receipt.json'
    receipt.write_text(json.dumps({'pid':12345,'birth_id':'known-birth'}))
    marker=tmp_path/'calls.json'
    prelude='''import os,signal,sys,json
from pathlib import Path
calls=[]
def fake_open(pid):
 assert pid==12345
 if os.environ['PIDFD_CASE']=='missing': raise ProcessLookupError()
 return 42
os.pidfd_open=fake_open
signal.pidfd_send_signal=lambda fd,sig: calls.append(['signal',fd,int(sig)])
os.close=lambda fd: calls.append(['close',fd])
'''
    arguments=['cleanup','12345',str(receipt),str(gate)]+([] if requested is None else [str(requested)])
    prelude+=f'sys.argv={arguments!r}\nexec({code!r})\nPath({str(marker)!r}).write_text(json.dumps(calls))\n'
    result=fixture_processes.run([sys.executable,'-B','-c',prelude],env=dict(os.environ,PIDFD_CASE=case),capture_output=True,text=True,timeout=5)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)=={'forced':case=='owned'}
    calls=json.loads(marker.read_text())
    assert [call for call in calls if call[0]=='signal']==([['signal',42,9 if requested is None else requested]] if case=='owned' else [])
    assert [call for call in calls if call[0]=='close']==([] if case=='missing' else [['close',42]])


@pytest.mark.parametrize('fault',['none','recycled_launcher','child_reparented','child_recycled','parent_recycled'])
def test_storage_discovery_binds_every_ancestry_link(tmp_path,fault, fixture_processes):
    # Reverse table order, an unrelated verified-JAR lookalike, and OS identity
    # changes during capture: discovery may claim only the stable owned chain.
    script=tmp_path/'ancestry.mjs'
    script.write_text(f"import {{discoverStorageProcesses}} from {json.dumps((DATA/'engine-contract-reporter.mjs').as_uri())};\n"+r'''
const root={pid:101,birth_id:'launcher',depth:0};
const rows=[{pid:103,parent:102,command:'java verified.jar'},{pid:201,parent:999,command:'java verified.jar'},{pid:102,parent:101,command:'firebase CLI'}];
const calls=new Map(), fault=process.argv[2];
function inspect(pid) {
 const n=(calls.get(pid)||0)+1;calls.set(pid,n);
 const identities={101:{parent:1,birth_id:'launcher'},102:{parent:101,birth_id:'cli'},103:{parent:102,birth_id:'jar'},201:{parent:999,birth_id:'unrelated'}};
 const identity=identities[pid];
 if(pid===101 && (fault==='recycled_launcher' || (fault==='parent_recycled' && n>1))) identity.birth_id='new-launcher';
 if(pid===102 && fault==='child_reparented') identity.parent=999;
 if(pid===102 && fault==='child_recycled') identity.birth_id='cli-'+n;
 return identity;
}
console.log(JSON.stringify(discoverStorageProcesses(rows,[root],inspect)));
''')
    result=fixture_processes.run(['node',str(script),fault],capture_output=True,text=True,timeout=5)
    assert result.returncode==0,result.stderr
    rows=json.loads(result.stdout)
    assert [row['pid'] for row in rows]==([102,103] if fault=='none' else [])
    if fault=='none':
        assert [row['parent_birth_id'] for row in rows]==['launcher','cli']
        assert [row['birth_id'] for row in rows]==['cli','jar']


def test_sql_python_scratch_is_private(shell_fixture):
    root,env=shell_fixture
    env.pop('PYTHONDONTWRITEBYTECODE',None)
    result=run_shell(shell_fixture)
    assert result.returncode==0,result.stdout+result.stderr
    calls=[json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
    pytest_call=next(row for row in calls if row[0]=='python' and '-m' in row and 'pytest' in row)
    assert 'no:cacheprovider' in pytest_call,'mandatory Python must not write checkout cache'
    base=next(arg.split('=',1)[1] for arg in pytest_call if arg.startswith('--basetemp='))
    assert Path(base).is_relative_to(root/'sql-out')
    assert Path(base).parent.stat().st_mode & 0o777==0o700
    assert json.loads((root/'python-env.json').read_text())['bytecode']=='1'


def test_valid_restored_cache_and_download_are_verified_offline(tmp_path,monkeypatch,capsys):
    import io
    p=provisioner()
    download=p.download_asset
    config,cache,payload,marker=verified_cache_control(p,tmp_path/'valid',monkeypatch)
    observed=p.verify_asset(cache/p.FILENAMES['dataconnect'],config['assets']['dataconnect'],version='3.2.0')
    assert observed['sha256']==hashlib.sha256(payload).hexdigest()
    report=tmp_path/'provision.json'
    assert p.main(['--directory',str(cache),'--mode','normal','--restore','hit','--output',str(report)])==0
    assert json.loads(capsys.readouterr().out)['cache']['restore']=='hit'
    assert json.loads(report.read_text())['cache']['entries_before']==3
    target=tmp_path/'downloaded'
    download(target,config['assets']['dataconnect'],opener=lambda _:io.BytesIO(payload))
    assert target.read_bytes()==payload
    assert target.stat().st_mode & 0o777==0o700
    assert not target.with_name(target.name+'.partial').exists()
    assert not marker.exists(),'verification must never execute engine assets'


@pytest.mark.parametrize('version', ['15.15', '17.6'])
def test_sql_server_rejects_unapproved_major_even_when_provision_claims_it(shell_fixture, version):
    root, env = shell_fixture
    report=root/'preflight.json'
    evidence=json.loads(report.read_text())
    evidence['runtime']['postgres_server']=version
    report.write_text(json.dumps(evidence))
    env['FIXTURE_PG_VERSION']=version
    result=run_shell(shell_fixture)
    assert result.returncode != 0, result.stdout+result.stderr
    assert 'PostgreSQL server version mismatch' in result.stderr


@pytest.mark.parametrize('asset', ['dataconnect', 'storage', 'firebase'])
@pytest.mark.parametrize('fault', ['size', 'sha'])
def test_every_download_pin_remains_enforced(tmp_path, asset, fault):
    import io
    p=provisioner()
    good=b'pinned asset bytes'
    approved=dict(p.gate.APPROVED_TOOLCHAIN['assets'][asset], bytes=len(good), sha256=hashlib.sha256(good).hexdigest())
    bad=good+b'!' if fault=='size' else b'corrupt asset data'
    assert fault=='size' or len(good)==len(bad)
    with pytest.raises(ValueError, match='size|hash'):
        p.download_asset(tmp_path/asset, approved, opener=lambda _:io.BytesIO(bad))
    assert not (tmp_path/asset).exists()


@pytest.mark.parametrize('fault', ['none', 'java', 'node', 'postgres', 'image_version'])
def test_provision_report_records_and_cross_checks_runtime(tmp_path, monkeypatch, capsys, fault):
    p=provisioner()
    config,cache,payload,_=verified_cache_control(p,tmp_path/'runtime',monkeypatch)
    runtime={'java':'21.0.13+11','node':'22.24.0','postgres':'16.16','image_version':'20261019.400.1'}
    monkeypatch.setattr(p.gate,'inspect_runtime',lambda _env: dict(runtime),raising=False)
    report=tmp_path/'report.json'
    assert p.main(['--directory',str(cache),'--mode','normal','--restore','hit','--output',str(report)])==0
    assert json.loads(report.read_text())['runtime']==runtime
    assert json.loads(capsys.readouterr().out)['runtime']==runtime
    tools=p.verify_directory(cache,config)
    monkeypatch.setattr(p.gate,'inspect_tools',lambda _env: {'tools':tools,'runtime':dict(runtime)})
    for name,variable in p.VARIABLES.items():
        monkeypatch.setenv(variable,tools[name]['path'])
    if fault!='none':
        changed=json.loads(report.read_text())
        changed['runtime'][fault]='forged observation'
        report.write_text(json.dumps(changed))
    status=p.main(['--directory',str(cache),'--mode','normal','--verify-only','--output',str(report)])
    assert status==int(fault!='none')
    if fault!='none':
        assert 'recorded runtime differs' in capsys.readouterr().err


def test_sql_server_exact_version_disagreement_stays_rejected(shell_fixture):
    shell_fixture[1]['FIXTURE_PG_VERSION']='16.16'
    result=run_shell(shell_fixture)
    assert result.returncode!=0
    assert 'PostgreSQL server version mismatch' in result.stderr


def test_storage_rejects_runtime_drift_since_sql(shell_fixture):
    root,env=shell_fixture
    control=run_shell(shell_fixture)
    assert control.returncode==0,control.stdout+control.stderr
    report=root/'preflight.json'
    evidence=json.loads(report.read_text())
    evidence['runtime']['postgres_server']='16.16'
    report.write_text(json.dumps(evidence))
    result=run_shell(shell_fixture,storage=True)
    assert result.returncode!=0
    assert 'Storage/SQL runtime mismatch' in result.stderr


def test_storage_readiness_does_not_use_sql_waiter(shell_fixture):
    root, _ = shell_fixture
    control = run_shell(shell_fixture)
    assert control.returncode == 0, control.stdout + control.stderr
    # Reproduce the hosted defect: the SQL-specific root probe cannot qualify
    # Storage, even though its real loopback hub and Storage socket are ready.
    result = run_shell(shell_fixture, 'readiness_failed', storage=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (root / 'hub-requested').exists(), 'Storage readiness never consulted its private hub'
    calls = [json.loads(line) for line in (root / 'calls.jsonl').read_text().splitlines()]
    assert len([row for row in calls if row[0] == 'node' and row[1].endswith('/wait-local.mjs')]) == 4
    lifecycle = json.loads((root / 'lifecycle.json').read_text())
    assert {'id': 'storage', 'outcome': 'passed'} in [
        {key: row[key] for key in ('id', 'outcome')} for row in lifecycle['readiness']]
    assert lifecycle['cleanup']['ports_free_after'] is True


@pytest.mark.parametrize('fault,reason', [
    ('storage_ready_cli_exit', 'Storage CLI exited during readiness'),
    ('storage_ready_java_exit', 'Storage Java child exited during readiness'),
])
def test_storage_readiness_child_exit_stops_assertions_and_cleans(shell_fixture, fault, reason):
    root, env = shell_fixture
    env['FIXTURE_STANDALONE'] = 'true'
    control = run_shell(shell_fixture)
    assert control.returncode == 0, control.stdout + control.stderr
    result = run_shell(shell_fixture, fault, storage=True)
    assert result.returncode != 0 and reason in result.stderr, result.stdout + result.stderr
    lifecycle = json.loads((root / 'lifecycle.json').read_text())
    assert ('storage.ready', 'failed') in [(row['id'], row['outcome']) for row in lifecycle['stages']]
    assert 'storage-test.mjs' not in (root / 'calls.jsonl').read_text()
    # Readiness is failed, while the existing cleanup can pass after a clean
    # early CLI exit has reaped Java and released every owned port.
    assert_storage_tree_stopped(shell_fixture, lifecycle)


def test_storage_readiness_cli_exit_with_linux_reaped_birth(shell_fixture):
    root,env=shell_fixture
    # Linux requires SO_REUSEADDR on both binders when cleanup reuses the hub
    # address after an active close. Capture the option BEFORE the first bind;
    # Darwin can otherwise hide the missing option on that previous listener.
    launcher=root/'bin/firebase'
    source=launcher.read_text()
    target='exit_hub.bind('
    assert source.count(target)==1
    launcher.write_text(source.replace(target,"(root/'exit-hub-options.json').write_text(json.dumps({'reuseaddr_before_bind':exit_hub.getsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR)})); "+target))
    # Linux removes /proc/<pid>/stat after wait/reap. Darwin's synthetic birth
    # otherwise hides the fixture's read-before-signal failure for a gone CLI.
    helper=root/'.venv/bin/python'
    source=helper.read_text()
    target='def birth(pid):\n'
    assert source.count(target)==1
    helper.write_text(source.replace(target,target+''' try: os.kill(pid,0)
 except ProcessLookupError: raise FileNotFoundError('/proc/'+str(pid)+'/stat')
'''))
    env['FIXTURE_STANDALONE']='true'
    control=run_shell(shell_fixture)
    assert control.returncode==0,control.stdout+control.stderr
    result=run_shell(shell_fixture,'storage_ready_cli_exit',storage=True)
    assert result.returncode!=0 and 'Storage CLI exited during readiness' in result.stderr,result.stdout+result.stderr
    lifecycle=json.loads((root/'lifecycle.json').read_text())
    assert ('storage.ready','failed') in [(row['id'],row['outcome']) for row in lifecycle['stages']]
    assert 'storage-test.mjs' not in (root/'calls.jsonl').read_text()
    assert_storage_tree_stopped(shell_fixture,lifecycle)
    assert 'Storage cleanup:' not in result.stderr,result.stderr
    options=json.loads((root/'exit-hub-options.json').read_text())
    assert options['reuseaddr_before_bind']!=0,'Linux requires SO_REUSEADDR on the previous hub listener before bind: '+json.dumps(options)


def test_storage_cleanup_rejects_live_owned_survivor(shell_fixture):
    root,env=shell_fixture
    control=run_shell(shell_fixture)
    assert control.returncode==0,control.stdout+control.stderr
    reporter=root/'scripts/data/engine-contract-reporter.mjs'
    source=reporter.read_text()
    target='    const survivors=children.filter('
    assert source.count(target)==1
    # Seed a late-discovered, genuinely live owner at the final survivor gate.
    # Keep it a direct child of this test so teardown can always kill AND reap
    # it, without leaving an orphan/zombie behind on either operating system.
    reporter.write_text(source.replace(target,"    storageOwners.push({pid:Number(env.FIXTURE_SURVIVOR_PID),...storageIdentity(Number(env.FIXTURE_SURVIVOR_PID),env)});\n"+target))
    child=env.processes.start([sys.executable,'-c','import signal; signal.pause()'])
    try:
        (root/'instances'/f'{child.pid}.json').write_text(json.dumps({'pid':child.pid,'parent':os.getpid(),'command':'owned-survivor'}))
        env['FIXTURE_SURVIVOR_PID']=str(child.pid)
        result=run_shell(shell_fixture,storage=True)
        os.kill(child.pid,0)
        assert result.returncode!=0,'live owned survivor was accepted: '+result.stdout+result.stderr
        lifecycle=json.loads((root/'lifecycle.json').read_text())
        assert lifecycle['cleanup']['outcome']=='failed',lifecycle['cleanup']
        assert lifecycle['cleanup']['survivors']==[child.pid],lifecycle['cleanup']
        assert ('storage.assertions','passed') in [(row['id'],row['outcome']) for row in lifecycle['stages']]
    finally:
        child.kill()
        child.wait(timeout=5)


@contextmanager
def storage_readiness_servers(case):
    # The bound-but-not-listening socket reserves the negative TCP control's
    # exact port, so no concurrent test can accidentally make that control pass.
    with socket.socket() as storage:
        storage.bind(('127.0.0.1', 0))
        port = storage.getsockname()[1]
        if case not in ('closed_tcp', 'delayed_tcp'):
            storage.listen(128)
        requests = []

        class Hub(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                row = {'name': 'storage', 'host': '127.0.0.1', 'port': port}
                body = {'storage': row}
                if case in ('only_other', 'cli_exit', 'java_exit', 'download'):
                    body = {'auth': dict(row, name='auth')}
                elif case == 'wrong_port':
                    row['port'] = port + 1
                elif case == 'wrong_host':
                    row['host'] = 'localhost'
                elif case == 'string_port':
                    row['port'] = str(port)
                elif case == 'null_storage':
                    body['storage'] = None
                elif case == 'delayed' and len(requests) == 1:
                    body = {}
                if case == 'delayed_tcp' and len(requests) == 2:
                    storage.listen(128)
                if case == 'hung_headers':
                    time.sleep(.7)
                    return
                self.send_response(503 if case == 'http_error' else 302 if case == 'redirect' else 200)
                if case == 'redirect':
                    self.send_header('Location', '/redirect-must-not-be-followed')
                self.end_headers()
                if case == 'hung_body':
                    time.sleep(.7)
                    return
                try:
                    self.wfile.write(b'{' if case == 'malformed' else json.dumps(body).encode())
                except (BrokenPipeError, ConnectionResetError):
                    pass  # The bounded waiter has already closed its request.

            def log_message(self, *_):
                pass

        with ThreadingHTTPServer(('127.0.0.1', 0), Hub) as hub:
            thread = threading.Thread(target=lambda: hub.serve_forever(poll_interval=.01))
            thread.start()
            try:
                yield hub.server_port, port, requests
            finally:
                hub.shutdown()
                thread.join(timeout=2)
                assert not thread.is_alive(), 'fake hub did not shut down'


@pytest.mark.parametrize('case', [
    'ready', 'delayed', 'delayed_tcp', 'only_other', 'wrong_port', 'wrong_host', 'string_port',
    'null_storage', 'malformed', 'closed_tcp', 'http_error', 'redirect',
    'hung_headers', 'hung_body', 'cli_exit', 'java_exit', 'download',
])
def test_storage_waiter_real_loopback(tmp_path, case, fixture_processes):
    script = tmp_path / 'storage-ready.mjs'
    script.write_text(f"import {{waitForStorage}} from {json.dumps((DATA / 'wait-storage.mjs').as_uri())};\n" + r'''
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
const [hubPort,storagePort,scenario]=process.argv.slice(2);
const children=['CLI','Java child'].map(role=> {
  const child=spawn(process.execPath,['-e','setInterval(()=>{},1000)']);
  const done=new Promise(resolve=>child.once('exit',resolve));
  return {role,child,done};
});
let downloaded=false, checks=0;
const timer=setTimeout(()=> {
  if(scenario==='cli_exit') children[0].child.kill();
  if(scenario==='java_exit') children[1].child.kill();
  downloaded=scenario==='download';
},100);
try {
  await waitForStorage({hubPort:Number(hubPort),storagePort:Number(storagePort),timeoutMs:350,
    checkRunning:()=> {
      checks++;
      for(const {role,child} of children)
        assert.ok(child.exitCode===null && child.signalCode===null,`Storage ${role} exited during readiness`);
      assert.ok(!downloaded,'Storage CLI attempted download');
    }});
  console.log('storage ready');
} catch(error) { console.error(error.message); process.exitCode=1; }
finally {
  clearTimeout(timer);
  for(const {child,done} of children) {if(child.exitCode===null && child.signalCode===null) child.kill(); await done;}
  console.log(`guard checks: ${checks}`);
}
''')
    with storage_readiness_servers(case) as (hub, storage, requests):
        start = time.monotonic()
        result = fixture_processes.run(['node', str(script), str(hub), str(storage), case],
                                capture_output=True, text=True, timeout=5)
        seconds = time.monotonic() - start
    if case in ('ready', 'delayed', 'delayed_tcp'):
        assert result.returncode == 0 and 'storage ready' in result.stdout, result.stdout + result.stderr
        if case in ('delayed', 'delayed_tcp'):
            assert len(requests) >= 2, 'waiter did not poll until Storage registered'
    else:
        assert result.returncode != 0, f'{case} incorrectly became ready: {result.stdout}'
        reason = {'cli_exit': 'Storage CLI exited during readiness',
                  'java_exit': 'Storage Java child exited during readiness',
                  'download': 'Storage CLI attempted download'}.get(case, 'Storage emulator did not become ready within 350 ms')
        assert reason in result.stderr, result.stdout + result.stderr
    assert requests and set(requests) == {'/emulators'}, 'waiter must only GET the private hub /emulators'
    assert seconds < 3, f'{case} exceeded its bounded readiness budget: {seconds:.3f}s'
    assert int(result.stdout.split('guard checks: ')[1]) >= 2, 'process/download guard was not rechecked'
