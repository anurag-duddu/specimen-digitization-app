import hashlib
import importlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
M = importlib.import_module('deploy_data')
R = importlib.import_module('deploy_runtime')
SHA = 'a' * 40


def test_cleanup_preserves_earlier_recorded_recovery_deadline(tmp_path, monkeypatch):
    packet = {'source_sha': SHA, 'release_run_id': 123, 'release_run_attempt': 2,
              'issued_at_unix': 10000, 'expires_at_unix': 17200}
    created = datetime.fromtimestamp(10060, timezone.utc).isoformat()
    clone = {'name': M.CLONE, 'createTime': created, 'settings': {'userLabels': {
        'release-run': '123', 'release-attempt': '2', 'source-sha': SHA,
        'purpose': 'isolated-restore-rehearsal'}}}
    operation = {'name': 'owned-create', 'operationType': 'CREATE', 'targetId': M.CLONE,
                 'targetProject': M.PROJECT, 'user': f'specimen-data-release@{M.PROJECT}.iam.gserviceaccount.com',
                 'insertTime': created, 'status': 'DONE'}
    receipt_path = tmp_path / 'native-recovery.json'
    receipt_path.write_text(json.dumps({'clone': M.CLONE, 'source': M.SOURCE,
        'run_id': 123, 'run_attempt': 2, 'create_time': created,
        'expires_at_unix': 13600, 'native_restore_verified': True}))
    receipt_path.chmod(0o600)
    class Fake:
        current = clone
        def request(self, api, method, resource, **kwargs):
            assert method == 'GET'
            return {'items': [operation]} if resource.endswith('/operations') else self.current
        def cleanup_clone(self):
            self.current = None
            return {'name': 'owned-delete', 'status': 'DONE'}
    google = Fake()
    google.packet = packet
    monkeypatch.setattr(M.time, 'time', lambda: 14500)
    M.cleanup_rehearsal(google, tmp_path)
    receipt = json.loads(receipt_path.read_text())
    assert receipt['expires_at_unix'] == 13600
    assert receipt['deadline_exceeded'] is True


def test_schema_receipt_verifies_the_same_bytes_that_are_parsed(tmp_path, monkeypatch):
    native = {'native_restore_verified': True, 'deleted_at_unix': 12345,
              'deadline_exceeded': False, 'clone': M.CLONE, 'source': M.SOURCE,
              'source_sha': SHA, 'run_id': 123, 'run_attempt': 2}
    native_raw = json.dumps(native).encode()
    receipt = {'version': 'data-schema-ready/v1', 'schema_ready': True,
        'native_restore_verified': True, 'source_files': M.source_fingerprints(),
        'source_sha': SHA, 'run_id': 123, 'run_attempt': 2,
        'restore_receipt': {'source_sha': SHA, 'run_id': 123, 'run_attempt': 2,
                            'sha256': hashlib.sha256(native_raw).hexdigest()},
        'schema': {'name': f'{M.PREFIX}/schemas/main', 'etag': 'schema1'},
        'connector': {'name': f'{M.PREFIX}/connectors/specimen-server', 'etag': 'connector1'},
        'storage_ruleset': 'pinned-rules'}
    raw = json.dumps(receipt).encode()
    plan = {'schema_receipt': {'source_sha': SHA, 'run_id': 123, 'run_attempt': 2,
                               'sha256': hashlib.sha256(raw).hexdigest()}}
    attested = []
    def download(command, **kwargs):
        folder = Path(command[-1])
        name = command[command.index('--name') + 1]
        if name.startswith('data-ready-'):
            (folder / 'data-ready.json').write_bytes(raw)
        else:
            (folder / 'native-recovery.json').write_bytes(native_raw)
    def verify(path, *args):
        # Simulate replacement between the outer read and the verifier's read.
        Path(path).write_bytes(b'{"different_attested_artifact":true}')
        attested.append(Path(path).read_bytes())
    class Fake:
        packet = {'identity': {'project_number': '123'}}
        def request(self, api, method, resource, **kwargs):
            if api == 'rules':
                return {'rulesetName': 'pinned-rules'}
            return {'etag': 'schema1' if resource.endswith('schemas/main') else 'connector1'}
    monkeypatch.setattr(R, 'checked', download)
    monkeypatch.setattr(R, 'verify_attestation', verify)
    with pytest.raises(ValueError):
        M.verify_schema_receipt(Fake(), plan)
    assert attested != [raw]


@pytest.mark.parametrize('phase', ['data-bootstrap/v1', 'data-verify/v1'])
def test_full_bootstrap_cli_does_not_require_unrelated_sql_cleanup(tmp_path, monkeypatch, phase):
    calls = []
    packet = {'source_sha': SHA, 'release_run_id': 123, 'release_run_attempt': 3}
    plan = {'version': phase, 'source_sha': SHA, 'source_files': M.source_fingerprints(),
            'schema_receipt': {'source_sha': SHA, 'run_id': 123, 'run_attempt': 2, 'sha256': 'b' * 64},
            'bootstrap': {'payload': {}, 'sha256': 'c' * 64} if phase == 'data-bootstrap/v1' else None}
    monkeypatch.setattr(M, 'admit', lambda *args: packet)
    monkeypatch.setattr(M, 'read_bound_plan', lambda *args: plan)
    monkeypatch.setattr(M, 'verify_schema_receipt', lambda *args: {
        'version': 'data-schema-ready/v1', 'schema_ready': True, 'native_restore_verified': True})
    monkeypatch.setattr(importlib.import_module('bootstrap_release'), 'bootstrap',
                        lambda *args: calls.append('bootstrap-completed'))
    output = tmp_path / 'data-ready.json'
    monkeypatch.setenv('GITHUB_OUTPUT',str(tmp_path/'github-output'))
    def google(*args, **kwargs):
        if kwargs.get('cleanup'):
            assert json.loads(output.read_text())['schema_ready'] is True
            calls.append(('unrelated-cleanup', True))
            raise ValueError('SQL cleanup transport unavailable')
        return type('Fake', (), {'packet': packet})()
    monkeypatch.setattr(M, 'Google', google)
    monkeypatch.setattr(sys, 'argv', ['deploy_data.py', '--packet', str(tmp_path / 'packet.json'),
        '--deploy', '--output', str(output)])
    M.main()
    assert calls == (['bootstrap-completed'] if phase == 'data-bootstrap/v1' else [])
