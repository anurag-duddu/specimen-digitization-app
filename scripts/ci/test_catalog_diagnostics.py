"""Controlled failures exercise the real release boundaries without cloud access."""
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import deploy_data as data
import release_google as google
import release_initialize as init
from test_initialization_catalog_privacy import catalog_keys
from test_release_google import context, credential

CANARY = 'secret-token https://private.invalid/catalog SELECT private_specimen password=do-not-log'


def fail(*args, **kwargs):
    raise ValueError(CANARY)


def safe_failure(error, stage):
    text = str(error.value)
    assert stage in text
    assert all(part not in text for part in ('secret-token', 'https://', 'SELECT', 'password=', 'private_specimen'))


@pytest.mark.parametrize('where,stage', [('admit', 'data.admission'), ('read_bound_plan', 'data.plan')])
def test_python_entry_reports_fixed_gate_without_exception_message(tmp_path, monkeypatch, where, stage):
    monkeypatch.setattr(data, 'admit', lambda *a: {})
    monkeypatch.setattr(data, where, fail)
    monkeypatch.setattr('sys.argv', ['deploy_data.py', '--packet', str(tmp_path / 'packet.json'), '--deploy', '--output', str(tmp_path / 'out')])
    with pytest.raises(SystemExit) as error:
        data.main()
    safe_failure(error, stage)


@pytest.mark.parametrize('where,stage', [('admission', 'google.admission'), ('file', 'google.credentials-file'),
    ('validation', 'google.credentials-validation'), ('load', 'google.credentials-load'),
    ('session', 'google.session'), ('project', 'google.project-request'), ('identity', 'google.project-identity')])
def test_google_constructor_failure_has_safe_stage(tmp_path, monkeypatch, where, stage):
    env, packet = context()
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    path = tmp_path / 'gha-creds-synthetic.json'
    path.write_text(json.dumps(credential(env, packet))); path.chmod(0o600)
    monkeypatch.setenv('GOOGLE_GHA_CREDS_PATH', str(path))
    monkeypatch.setattr(google, 'admit', fail if where == 'admission' else lambda *a: packet)
    if where == 'file':
        monkeypatch.setattr(google, 'github_credential_bytes', fail)
    if where == 'validation':
        monkeypatch.setattr(google, 'validate_credentials', fail)
    monkeypatch.setattr('google.auth.load_credentials_from_dict', fail if where == 'load' else lambda *a, **k: (None, None))
    monkeypatch.setattr('google.auth.transport.requests.AuthorizedSession', fail if where == 'session' else lambda *a, **kw: SimpleNamespace(mount=lambda *a: None))
    monkeypatch.setattr(google.Google, 'request', fail if where == 'project' else lambda *a: {'name': CANARY})
    with pytest.raises(ValueError) as error:
        google.Google(tmp_path / 'packet.json', 'data')
    safe_failure(error, stage)


def plan_and_google(recipient):
    from test_data_initialization import packet
    plan = {'catalog_recipient': recipient, 'database_etag': 4, 'initialization_files': init.fingerprints()}
    client = SimpleNamespace(packet=packet(), request=lambda *a: {'region': 'us-east4', 'databaseVersion': 'POSTGRES_18', 'settings': {'settingsVersion': 4}})
    return plan, client


@pytest.mark.parametrize('where,stage', [('request', 'catalog.metadata-request'), ('identity', 'catalog.metadata-identity')])
def test_catalog_metadata_gate_before_node(tmp_path, monkeypatch, catalog_keys, where, stage):
    plan, client = plan_and_google(catalog_keys[0]); calls = []
    client.request = fail if where == 'request' else lambda *a: {'region': CANARY}
    monkeypatch.setattr(init.subprocess, 'run', lambda *a, **k: calls.append(a))
    with pytest.raises(ValueError) as error:
        init.inspect_catalog(client, plan, tmp_path, tmp_path / 'out')
    safe_failure(error, stage); assert calls == []


@pytest.mark.parametrize('stderr,expected', [
    (b'{"version":"release-diagnostic/v1","stage":"node.connect","sqlstate":"42501"}\n', 'node.connect'),
    (CANARY.encode(), 'catalog.native-execute'),
    (b'{"version":"release-diagnostic/v1","stage":"node.connect","message":"private_specimen"}', 'catalog.native-execute'),
    (b'{"version":"release-diagnostic/v1","stage":"node.connect","stage":"node.catalog-query"}', 'catalog.native-execute'),
    (b'{"version":"release-diagnostic/v1","stage":"private_specimen"}', 'catalog.native-execute'),
    (b'{"version":"release-diagnostic/v1","stage":"node.connect","sqlstate":"TOKEN"}', 'catalog.native-execute'),
])
def test_only_complete_allowlisted_node_error_survives_capture(tmp_path, monkeypatch, catalog_keys, stderr, expected):
    plan, client = plan_and_google(catalog_keys[0])
    monkeypatch.setattr(init.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stdout=CANARY.encode(), stderr=stderr))
    with pytest.raises(ValueError) as error:
        init.inspect_catalog(client, plan, tmp_path, tmp_path / 'out')
    safe_failure(error, expected)
    assert not list(tmp_path.glob('*.json'))


@pytest.mark.parametrize('where,stage', [('execute', 'catalog.native-execute'), ('encrypt', 'catalog.encryption')])
def test_timeout_and_encryption_failure_never_forward_captured_bytes(tmp_path, monkeypatch, catalog_keys, where, stage):
    plan, client = plan_and_google(catalog_keys[0])
    def run(args, **kwargs):
        if where == 'execute':
            raise subprocess.TimeoutExpired(CANARY, 90, output=CANARY.encode(), stderr=CANARY.encode())
        target = Path(args[-1]); target.write_bytes(CANARY.encode()); target.chmod(0o600)
        return SimpleNamespace(returncode=1, stdout=CANARY.encode(), stderr=CANARY.encode())
    monkeypatch.setattr(init.subprocess, 'run', run)
    monkeypatch.setattr('release_catalog_envelope.encrypt_catalog', fail)
    with pytest.raises(ValueError) as error:
        init.inspect_catalog(client, plan, tmp_path, tmp_path / 'out')
    safe_failure(error, stage)


@pytest.fixture
def node_dependencies(tmp_path):
    modules = tmp_path / 'node_modules'
    firebase = modules / 'firebase-tools'; firebase.mkdir(parents=True)
    (firebase / 'package.json').write_text('{"version":"15.8.0"}')
    connector = modules / '@google-cloud/cloud-sql-connector'; connector.mkdir(parents=True)
    (connector / 'index.js').write_text("exports.AuthTypes={IAM:'IAM'};exports.IpAddressTypes={PUBLIC:'PUBLIC'};exports.Connector=class{async getOptions(){if(process.env.TEST_FAILURE==='connector')throw Error(process.env.TEST_CANARY);return{};}close(){}};")
    pg = modules / 'pg'; pg.mkdir()
    (pg / 'index.js').write_text('''
const bad=()=>{const e=Error(process.env.TEST_CANARY);if(process.env.TEST_SQLSTATE==='getter')Object.defineProperty(e,'code',{get(){throw Error(process.env.TEST_CANARY);}});else e.code=process.env.TEST_SQLSTATE||'42501';throw e;};
exports.Pool=class{constructor(o){this.o=o;}async connect(){if(process.env.TEST_FAILURE==='connect')bad();const o=this.o;return{release(){},async query(sql){
if(sql.startsWith('SELECT current_database')){if(process.env.TEST_FAILURE==='context')bad();return{rows:[{database:o.database,actor:o.user,effective:o.user}]};}
if(sql.includes('pg_stat_activity')){if(process.env.TEST_FAILURE==='sessions')bad();return{rows:[{count:0}]};}
if(sql==='BEGIN READ ONLY'){if(process.env.TEST_FAILURE==='begin')bad();return{};}
if(sql==='ROLLBACK'){if(process.env.TEST_FAILURE==='rollback')bad();return{};}
if(process.env.TEST_FAILURE==='catalog')bad();return{rows:[{catalog:{server_major:process.env.TEST_FAILURE==='validate'?17:18,canary:process.env.TEST_CANARY}}]};
}};}async end(){if(process.env.TEST_FAILURE==='cleanup')bad();}};
''')
    return tmp_path


@pytest.mark.parametrize('where,stage', [('preflight', 'node.preflight'), ('connector', 'node.connector'),
    ('connect', 'node.connect'), ('context', 'node.context'), ('sessions', 'node.sessions'),
    ('begin', 'node.catalog-begin'), ('catalog', 'node.catalog-query'), ('validate', 'node.catalog-validate'),
    ('rollback', 'node.catalog-rollback'), ('cleanup', 'node.cleanup')])
def test_real_node_process_reports_only_fixed_failure_fields(tmp_path, node_dependencies, where, stage):
    result = node_process(tmp_path, node_dependencies, where)
    assert result.returncode != 0 and result.stdout == b''
    value = json.loads(result.stderr)
    assert value['version'] == 'release-diagnostic/v1' and value['stage'] == stage
    assert set(value) <= {'version', 'stage', 'sqlstate'}
    assert value.get('sqlstate') in (None, '42501')
    assert all(part not in result.stderr for part in (b'secret-token', b'https://', b'SELECT', b'password=', b'private_specimen'))


def test_actual_auth_producer_0640_is_tightened_before_any_consumption(tmp_path, monkeypatch):
    env, packet = context()
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    path = tmp_path / 'gha-creds-synthetic.json'
    path.write_text(json.dumps(credential(env, packet))); path.chmod(0o640)
    monkeypatch.setenv('GOOGLE_GHA_CREDS_PATH', str(path))
    monkeypatch.setattr(google, 'admit', lambda *a: packet)
    loaded = []
    def load(value, **kwargs):
        assert path.stat().st_mode & 0o777 == 0o600
        loaded.append(value)
        return None, None
    monkeypatch.setattr('google.auth.load_credentials_from_dict', load)
    monkeypatch.setattr('google.auth.transport.requests.AuthorizedSession', lambda *a, **kw: SimpleNamespace(mount=lambda *a: None))
    monkeypatch.setattr(google.Google, 'request', lambda *a: {'name': 'projects/123456789', 'projectId': 'specimen-digitization', 'state': 'ACTIVE'})
    google.Google(tmp_path / 'packet', 'data')
    assert loaded == [credential(env, packet)]
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('unsafe', ['symlink', 'hardlink', 'public', 'group-write', 'wrong-owner', 'directory'])
def test_credential_tightening_never_reads_or_changes_an_unapproved_file(tmp_path, monkeypatch, unsafe):
    env, packet = context()
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    path = tmp_path / 'gha-creds-synthetic.json'; original = tmp_path / 'unrelated'
    original.write_text(CANARY); original.chmod(0o640)
    if unsafe == 'symlink': path.symlink_to(original)
    elif unsafe == 'hardlink': os.link(original, path)
    elif unsafe == 'directory': path.mkdir()
    else:
        path.write_text(CANARY); path.chmod(0o644 if unsafe == 'public' else 0o660 if unsafe == 'group-write' else 0o640)
    monkeypatch.setenv('GOOGLE_GHA_CREDS_PATH', str(path))
    monkeypatch.setattr(google, 'admit', lambda *a: packet)
    monkeypatch.setattr('google.auth.load_credentials_from_dict', lambda *a, **k: pytest.fail('unsafe credential loaded'))
    if unsafe == 'wrong-owner': monkeypatch.setattr(google.os, 'geteuid', lambda: os.getuid() + 1)
    before = original.stat().st_mode
    with pytest.raises(ValueError) as error:
        google.Google(tmp_path / 'packet', 'data')
    safe_failure(error, 'google.credentials-file')
    assert original.stat().st_mode == before


def test_http_status_is_numeric_and_body_never_reaches_diagnostic(monkeypatch):
    from test_release_google import transport
    from release_diagnostics import public_failure, stage
    client = transport()
    client.session.request = lambda *a, **k: SimpleNamespace(status_code=403, text=CANARY, json=lambda: {'error': CANARY})
    with pytest.raises(ValueError) as error:
        with stage('catalog.metadata-request'):
            client.request('sql', 'GET', 'projects/specimen-digitization/instances/specimen-digitization-instance')
    safe_failure(error, 'catalog.metadata-request')
    assert 'http_status=403' in public_failure(error.value)


def test_unknown_exception_type_and_codes_cannot_supply_public_fields():
    from release_diagnostics import DiagnosticError, HTTPFailure, public_failure
    error = type('private_specimen', (ValueError,), {})(CANARY)
    error.http_status = 403; error.sqlstate = '42501'; error.stage = 'node.connect'
    assert public_failure(error) == 'Data release blocked [stage=data.execute].'
    assert public_failure(DiagnosticError(CANARY, http_status=True, sqlstate='TOKEN')) == 'Data release blocked [stage=data.execute].'
    assert public_failure(HTTPFailure(CANARY)) == 'Data release blocked [stage=data.execute].'


def test_descriptor_is_private_before_first_byte_read(tmp_path, monkeypatch):
    path = tmp_path / 'gha-creds-synthetic.json'; path.write_bytes(b'{}'); path.chmod(0o640)
    real = os.fdopen; reads = []
    class Checked:
        def __init__(self, handle): self.handle = handle
        def __enter__(self): return self
        def __exit__(self, *args): return self.handle.__exit__(*args)
        def fileno(self): return self.handle.fileno()
        def read(self, *args):
            assert os.fstat(self.fileno()).st_mode & 0o777 == 0o600
            reads.append(True)
            return self.handle.read(*args)
    monkeypatch.setattr(google.os, 'fdopen', lambda *a, **k: Checked(real(*a, **k)))
    assert google.github_credential_bytes(path) == b'{}'
    assert reads == [True]


def test_failed_permission_tightening_reads_nothing(tmp_path, monkeypatch):
    path = tmp_path / 'gha-creds-synthetic.json'; path.write_bytes(CANARY.encode()); path.chmod(0o640)
    monkeypatch.setattr(google.os, 'fchmod', fail)
    with pytest.raises(ValueError): google.github_credential_bytes(path)
    assert path.stat().st_mode & 0o777 == 0o640


def test_different_adc_job_path_rejected_before_tightening(tmp_path, monkeypatch):
    env, packet = context()
    for k, v in env.items(): monkeypatch.setenv(k, v)
    path = tmp_path / 'gha-creds-synthetic.json'; path.write_bytes(b'{}'); path.chmod(0o640)
    monkeypatch.setenv('GOOGLE_GHA_CREDS_PATH', str(path))
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', str(tmp_path / 'other'))
    monkeypatch.setattr(google, 'admit', lambda *a: packet)
    with pytest.raises(ValueError) as error: google.Google(tmp_path / 'packet', 'data')
    safe_failure(error, 'google.credentials-file')
    assert path.stat().st_mode & 0o777 == 0o640


def node_process(tmp_path, node_dependencies, where, sqlstate="42501"):
    env = {'PATH': os.environ['PATH'], 'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'anurag-duddu/specimen-digitization-app',
        'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/main', 'GITHUB_REF_PROTECTED': 'true',
        'GITHUB_WORKFLOW_REF': 'anurag-duddu/specimen-digitization-app/.github/workflows/data-release.yml@refs/heads/main',
        'GITHUB_SHA': 'a'*40, 'RELEASE_AUTHORIZED_SHA': 'a'*40, 'DEPLOYMENT_ENVIRONMENT': 'data-production',
        'RELEASE_SERVICE_ACCOUNT': 'specimen-data-release@specimen-digitization.iam.gserviceaccount.com',
        'INITIALIZATION_DEADLINE': '1989000000', 'INITIALIZATION_FILES': json.dumps(init.fingerprints()),
        'RELEASE_NODE_ROOT': str(node_dependencies), 'TEST_FAILURE': where, 'TEST_CANARY': CANARY, 'TEST_SQLSTATE': sqlstate}
    if where == 'preflight':
        env['GITHUB_REPOSITORY'] = CANARY
    return subprocess.run(['node', 'scripts/ci/release_initialize.mjs', 'inspect', init.SOURCE, str(tmp_path / 'private.json')],
        cwd=init.ROOT, env=env, capture_output=True, timeout=10)


@pytest.mark.parametrize('code', ['TOKEN', 'secret-token', '42501\nprivate_specimen', 'getter'])
def test_real_node_never_serializes_arbitrary_error_codes(tmp_path, node_dependencies, code):
    result = node_process(tmp_path, node_dependencies, 'connect', code)
    assert result.returncode == 1 and result.stdout == b''
    assert json.loads(result.stderr) == {'version': 'release-diagnostic/v1', 'stage': 'node.connect'}


def test_real_node_success_keeps_private_six_file_catalog_protocol(tmp_path, node_dependencies):
    result = node_process(tmp_path, node_dependencies, 'success')
    assert result.returncode == 0 and result.stdout == result.stderr == b''
    value = json.loads((tmp_path / 'private.json').read_bytes())
    assert set(value) == {'instance', 'mode', 'files', 'catalog', 'qualified', 'native_client_sessions'}
    assert value['files'] == init.fingerprints() and len(value['files']) == 6
    assert value['mode'] == 'inspect' and value['instance'] == init.SOURCE and value['qualified'] is True
    assert value['catalog']['canary'] == CANARY and value['native_client_sessions'] == 0
    assert (tmp_path / 'private.json').stat().st_mode & 0o777 == 0o600


def test_native_failure_stage_survives_top_level_cli_with_no_public_payload(tmp_path, monkeypatch, catalog_keys):
    plan, client = plan_and_google(catalog_keys[0])
    plan['version'] = 'data-initialization-inventory/v1'
    monkeypatch.setattr(data, 'admit', lambda *a: client.packet)
    monkeypatch.setattr(data, 'read_bound_plan', lambda *a: plan)
    monkeypatch.setattr(data, 'validate_plan', lambda p, *a: p)
    monkeypatch.setattr(data, 'Google', lambda *a: client)
    monkeypatch.setattr(init.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stdout=CANARY.encode(),
        stderr=b'{"version":"release-diagnostic/v1","stage":"node.connect","sqlstate":"42501"}\n'))
    monkeypatch.setattr('sys.argv', ['deploy_data.py', '--packet', str(tmp_path / 'packet.json'), '--deploy', '--output', str(tmp_path / 'out')])
    with pytest.raises(SystemExit) as error: data.main()
    assert str(error.value) == 'Data release blocked [stage=node.connect; sqlstate=42501].'
    assert not list(tmp_path.glob('*.json'))
