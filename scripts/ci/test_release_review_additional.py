"""Independent regressions for signed bytes and original cleanup deadlines."""
import hashlib
import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

D = importlib.import_module('deploy_data')
R = importlib.import_module('deploy_runtime')
G = importlib.import_module('release_google')
from test_release_google import context


@pytest.mark.parametrize('replace_back', [False, True])
def test_verified_subject_must_match_consumed_bytes_even_if_path_restored(tmp_path, monkeypatch, replace_back):
    original = b'{"approved":"original"}'
    replacement = b'{"approved":"different"}'
    path = tmp_path / 'artifact.json'
    path.write_bytes(original)
    expected = hashlib.sha256(original).hexdigest()
    def verify(p, *args):
        Path(p).write_bytes(replacement)
        proof = json.dumps([{'verificationResult': {'statement': {'subject': [
            {'digest': {'sha256': hashlib.sha256(Path(p).read_bytes()).hexdigest()}}]}}}])
        if replace_back:
            Path(p).write_bytes(original)
        return proof
    monkeypatch.setattr(R, 'verify_attestation', verify)
    with pytest.raises(ValueError, match='subject'):
        R.verified_receipt_bytes(path, expected, 'a' * 40, 'data-release.yml')


def test_matching_verified_subject_consumes_original_buffer(tmp_path, monkeypatch):
    raw = b'{"approved":"same"}'
    path = tmp_path / 'artifact.json'
    path.write_bytes(raw)
    expected = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(R, 'verify_attestation', lambda *args: json.dumps([
        {'verificationResult': {'statement': {'subject': [{'digest': {'sha256': expected}}]}}}]))
    assert R.verified_receipt_bytes(path, expected, 'a' * 40, 'data-release.yml') == raw


def test_fallback_cleanup_without_local_receipt_preserves_shorter_approved_permit(tmp_path, monkeypatch):
    env, packet = context()
    deadline = packet['issued_at_unix'] + 3600
    env['RELEASE_CLEANUP_PERMIT'] = json.dumps(G.cleanup_permit(packet, deadline))
    actual = G.cleanup_packet(tmp_path / 'missing.json', env)
    created = datetime.fromtimestamp(packet['issued_at_unix'] + 60, timezone.utc).isoformat()
    clone = {'name': D.CLONE, 'createTime': created, 'settings': {'userLabels': {
        'release-run': '123', 'release-attempt': '2', 'source-sha': packet['source_sha'],
        'purpose': 'isolated-restore-rehearsal'}}}
    operation = {'name': 'create-one', 'operationType': 'CREATE', 'targetId': D.CLONE,
        'targetProject': D.PROJECT, 'user': f'specimen-data-release@{D.PROJECT}.iam.gserviceaccount.com',
        'insertTime': created, 'status': 'DONE'}
    class Fake:
        packet = actual
        current = clone
        deletes = 0
        def request(self, api, method, resource, **kwargs):
            assert method == 'GET'
            return {'items': [operation]} if resource.endswith('/operations') else self.current
        def cleanup_clone(self):
            self.deletes += 1
            self.current = None
            return {'name': 'delete-one', 'status': 'DONE'}
    google = Fake()
    monkeypatch.setattr(D.time, 'time', lambda: deadline + 100)
    D.cleanup_rehearsal(google, tmp_path)
    result = json.loads((tmp_path / 'native-recovery.json').read_text())
    assert google.deletes == 1
    assert result['expires_at_unix'] == deadline
    assert result['deadline_exceeded'] is True


@pytest.mark.parametrize('bad', [True, '1788894000', 1788890400, 1788897601, None])
def test_fallback_permit_rejects_untyped_or_unbounded_deadline(tmp_path, bad):
    env, packet = context()
    packet['clone_expires_at_unix'] = bad
    env['RELEASE_CLEANUP_PERMIT'] = json.dumps(packet)
    with pytest.raises(ValueError):
        G.cleanup_packet(tmp_path / 'missing.json', env)
