"""Independent ordinary-wire literals; one fresh journey per module invocation.

The exporter owns setup only. These expectations are intentionally not imported
by it or shared with Dart. Exact types exclude bool and fractional revisions.
"""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/general_api_contracts.json'
S = '00000000-0000-4000-8000-000000000001'
R = '00000000-0000-4000-8000-000000000002'
U = '00000000-0000-4000-8000-000000000003'
ACTIONS = ['retry', 'resume', 'pause', 'cancel', 'reprocess', 'field',
           'transcription', 'reading_metadata', 'coverage', 'approve',
           'classification', 'regions', 'taxonomy_resolution',
           'authority_resolution', 'capability_defer', 'restore_version']
# pragma: allowlist nextline secret -- Synthetic retained candidate selection SHA-256.
SELECTION = '0f970a204f3b22c88e2913393e9a0ac6e8729430bd51f32b12c4b46cd93940c7'
# pragma: allowlist nextline secret -- Synthetic 257-byte PNG SHA-256.
PNG_HASH = '7f194fdff2c2798ac3f1702acdcb187b9ad6b8dd23d2668bc2ea21f9e001ecd8'
# pragma: allowlist nextline secret -- Synthetic PNG remaining-tail SHA-256.
TAIL_HASH = '63807a3f952e417c78fd4692e56a0d96eb2dae99a0a1cabd27e7b6e94aa9e80e'
PREFIX = '/v1/organizations/' + S


def record(revision, disposition, actions):
    return dict(specimen_id=S, organization_id=S, collection_id=R,
                revision=revision, active_run_id=R,
                record_version_id=R + ':' + str(revision), status='completed',
                stage='finalized', disposition=disposition, available_actions=actions)


def workspace(revision, disposition, actions, parsed='United States'):
    return {**record(revision, disposition, actions), 'fields': {'country': {
        'literal': 'United States', 'parsed': parsed,
        'state': 'supported', 'value_state': 'supported'}}}


def upload(revision, offset):
    return dict(upload_id=U, specimen_id=S, collection_id=R, revision=revision,
                state='uploading', offset=offset, size_bytes=257,
                upload_method='PUT', upload_url=PREFIX + '/uploads/' + U + '/content',
                sha256=PNG_HASH, chunks=[{'offset': 0, 'size': 20,
                    # pragma: allowlist nextline secret -- Synthetic PNG first-chunk SHA-256.
                    'sha256': '1bf0a9034faa63a8a53121b00ef018df9890126003c37e1416fb5a6401e25afd'}]
                    + ([{'offset': 20, 'size': 237, 'sha256': TAIL_HASH}] if offset == 257 else []))


# Independently authored required keys. Additional unknown server keys are legal.
TABLE = {
    'list': {'items': [record(20, 'needs_human_review', [])], 'next_cursor': None,
             'cutoff': '2026-01-02T03:04:05+00:00'},
    'workspace': workspace(20, 'needs_human_review', ACTIONS),
    'error': {'error': {'code': 'revision_or_idempotency_conflict',
                      'category': 'conflict', 'retryable': False, 'details': {},
                      'message': 'Stale revision',
                      'request_id': '00000000-0000-0000-0000-00000000008e'}},
    'error_readback': workspace(20, 'needs_human_review', ACTIONS),
    'upload': upload(2, 20), 'upload_tail': upload(3, 257),
    'upload_current': upload(3, 257),
    'upload_complete': {**record(1, None, ACTIONS), 'status': 'running', 'stage': 'ingested'},
    'action': workspace(21, 'cleared', ACTIONS),
    'action_readback': workspace(21, 'cleared', ACTIONS),
    'review_batch': {'requested': 1, 'applied': 1, 'refused': 0, 'skipped': 0,
        'results': [{'index': 0, 'specimen_id': S, 'kind': 'research_candidate',
                    'idempotency_key': 'i11-candidate-0', 'outcome': 'applied',
                    'revision': 22, 'record_version_id': R + ':22',
                    'disposition': 'needs_human_review'}]},
    'review_readback': workspace(22, 'needs_human_review',
                                [a for a in ACTIONS if a != 'reprocess'], 'Philippines'),
}
GROUPS = {'list': ['list'], 'workspace': ['workspace'],
          'error': ['error', 'error_readback'],
          'upload': ['upload', 'upload_tail', 'upload_current', 'upload_complete'],
          'action': ['action', 'action_readback'],
          'review_batch': ['review_batch', 'review_readback']}
APPROVE = {'expected_revision': 20, 'base_record_version_id': R + ':20',
           'kind': 'approve', 'reason': 'I11 synthetic reviewed', 'target_id': '',
           'after': {'confirmed': True}, 'evidence_ids': []}
REQUESTS = {
    'action': ('/specimens/' + S + '/decisions', 'i11-approve', APPROVE),
    'error': ('/specimens/' + S + '/decisions', 'i11-stale',
              {**APPROVE, 'expected_revision': 19, 'base_record_version_id': R + ':19'}),
    'upload_complete': ('/uploads/' + U + '/complete', 'i11-complete', {'expected_revision': 3}),
    'review_batch': ('/decisions:batch',
        # pragma: allowlist nextline secret -- Synthetic candidate request idempotency SHA-256.
        '7651ca196a03f7cc18d5625844ca3b2fdc68a62d7b19c691c3b222ad40a77aa8',
        {'reason': 'I11 retained source reviewed', 'decisions': [{
            'specimen_id': S, 'expected_revision': 21, 'base_record_version_id': R + ':21',
            'kind': 'research_candidate', 'target_id': 'country',
            'after': {'selection_id': SELECTION}, 'idempotency_key': 'i11-candidate-0'}]}),
}


def strict(actual, expected, path='body'):
    assert type(actual) is type(expected), f'{path}: expected {type(expected).__name__}, got {actual!r}'
    if isinstance(expected, dict) and expected:
        for key, value in expected.items():
            assert key in actual, f'{path}.{key}: required key missing'
            strict(actual[key], value, path + '.' + key)
    elif isinstance(expected, list):
        assert len(actual) == len(expected), f'{path}: wrong length'
        for index, value in enumerate(expected):
            strict(actual[index], value, f'{path}[{index}]')
    else:
        assert actual == expected, f'{path}: expected {expected!r}, got {actual!r}'


def assert_group(wire, group):
    corpus = json.loads(wire)
    strict(corpus['schema_version'], 1, 'schema_version')
    for name in GROUPS[group]:
        envelope = corpus['responses'][name]
        assert 'status_code' in envelope, name + ': missing HTTP status'
        assert 'body_utf8' in envelope, name + ': missing exact body'
        strict(envelope['status_code'], 409 if name == 'error' else 200, name + '.status_code')
        assert type(envelope['body_utf8']) is str
        body = json.loads(envelope['body_utf8'])
        strict(body, TABLE[name], name)
        if name in ('workspace', 'error_readback', 'action', 'action_readback', 'review_readback'):
            assert 'latest_record_version_id' not in body, name + ': server alias leaked'
        if name == 'error':
            for key in ('specimen_id', 'revision', 'record_version_id', 'status', 'stage', 'disposition', 'available_actions'):
                assert key not in body and key not in body['error'], 'error invented record field: ' + key
        if name.startswith('upload') and name != 'upload_complete':
            assert all(k not in body for k in ('record_version_id', 'disposition', 'available_actions'))
        if name == 'review_batch':
            assert all(k not in body['results'][0] for k in ('status', 'stage', 'available_actions'))
    if group in REQUESTS:
        path, key, expected = REQUESTS[group]
        request = corpus['requests'][group]
        strict(request['method'], 'POST', group + '.method')
        strict(request['path'], PREFIX + path, group + '.path')
        strict(request['headers']['Idempotency-Key'], key, group + '.key')
        decoded = json.loads(request['body_utf8'])
        strict(decoded, expected, group + '.request')
        assert decoded == expected, group + ': unexpected outgoing request keys'
    if group == 'upload':
        request = corpus['requests']['upload_tail']
        strict(request['method'], 'PUT')
        strict(request['path'], PREFIX + '/uploads/' + U + '/content')
        strict(request['headers'], {'Upload-Offset': '20', 'Idempotency-Key': 'chunk-' + U + '-20'})
        data = base64.b64decode(corpus['png_base64'], validate=True)
        assert len(data) == 257 and hashlib.sha256(data).hexdigest() == PNG_HASH
        assert len(data[20:]) == 237 and hashlib.sha256(data[20:]).hexdigest() == TAIL_HASH
        request = corpus['requests']['upload_complete']
        strict(request['method'], 'POST')
        strict(request['path'], PREFIX + '/uploads/' + U + '/complete')
        strict(request['headers'], {'Idempotency-Key': 'i11-complete'})
        strict(json.loads(request['body_utf8']), {'expected_revision': 3})
    if group == 'review_batch':
        strict(corpus['selection_id'], SELECTION)


@pytest.fixture(scope='module')
def committed():
    assert FIXTURE.is_file(), f'Missing shared byte corpus: {FIXTURE}'
    return FIXTURE.read_bytes()


@pytest.fixture(scope='module')
def generated(tmp_path_factory):
    path = ROOT / 'scripts/ci/export_general_api_contract_fixtures.py'
    spec = importlib.util.spec_from_file_location('general_api_exporter', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path_factory.mktemp('ordinary-wire')
    from specimen_digitization.application import api, domain, workflow, search, review_risk, provider_circuit
    from specimen_digitization.research_harness import persistence
    absent = object()
    bindings = [(owner, key, getattr(owner, key, absent)) for owner, key in [
        (api, 'datetime'), (api, 'uuid5'), (domain, 'datetime'), (domain, 'uuid4'),
        (workflow, 'datetime'), (workflow.Workflow, '__init__'), (search, 'datetime'),
        (review_risk, 'datetime'), (provider_circuit, 'uuid4'),
        (persistence, 'uuid4'), (persistence.SqliteStateBackend, '_time')]]
    wire = module.export_fixture_bytes(root)
    for owner, key, prior in bindings:
        assert getattr(owner, key, absent) is prior, f'Exporter leaked {owner}.{key}'
    # Read immutable saves, never compress or change canonical versions.
    from specimen_digitization.application import api, domain
    from specimen_digitization.application.storage import SQLiteRepository
    repository = SQLiteRepository(root / 'state.sqlite3')
    scope = domain.Scope(organization_id=api.SYNTHETIC_ORG, collection_id=api.SYNTHETIC_COLLECTION)
    for revision, stage in [(7, 'transcribe'), (19, 'finalize'), (20, 'finalized')]:
        assert repository.version(scope, S, revision).run.stage == stage
    return wire


def test_fixture_bytes_match_regeneration(committed, generated):
    assert generated == committed, 'Regenerate general_api_contracts.json with the exporter'
    assert committed.endswith(b'\n')
    corpus = json.loads(committed)
    assert all(set(e) == {'status_code', 'body_utf8'} for e in corpus['responses'].values())
    assert 'checkpoints' not in corpus


@pytest.mark.parametrize('group', GROUPS)
def test_independent_literal_table(committed, generated, group):
    assert_group(committed, group)
    assert_group(generated, group)


def required_paths(value, path=()):
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield path + (key,), child
            yield from required_paths(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from required_paths(child, path + (index,))


# Cheap fresh-fixture faults exercise every required key, including containers.
FAULTS = [(group, name, path, fault) for group, names in GROUPS.items()
          for name in names for path, _ in required_paths(TABLE[name])
          for fault in ('missing', 'renamed', 'type')]


@pytest.mark.parametrize('group,name,path,fault', FAULTS,
                         ids=lambda value: str(value))
def test_required_key_fault_is_semantically_rejected(committed, group, name, path, fault):
    corpus = json.loads(committed)
    body = json.loads(corpus['responses'][name]['body_utf8'])
    target = body
    for key in path[:-1]:
        target = target[key]
    key = path[-1]
    if fault == 'missing':
        del target[key]
    elif fault == 'renamed':
        target[str(key) + '_renamed'] = target.pop(key)
    else:
        target[key] = 'incompatible' if not isinstance(target[key], str) else 7
    corpus['responses'][name]['body_utf8'] = json.dumps(body)
    with pytest.raises(AssertionError):
        assert_group(json.dumps(corpus).encode(), group)


@pytest.mark.parametrize('bad', [True, '20', 20.5])
def test_revision_requires_integer(committed, bad):
    corpus = json.loads(committed)
    body = json.loads(corpus['responses']['workspace']['body_utf8'])
    body['revision'] = bad
    corpus['responses']['workspace']['body_utf8'] = json.dumps(body)
    with pytest.raises(AssertionError, match='revision'):
        assert_group(json.dumps(corpus).encode(), 'workspace')


INTEGER_FIELDS = [(group, name, path, value) for group, names in GROUPS.items()
                  for name in names for path, value in required_paths(TABLE[name])
                  if type(value) is int]


@pytest.mark.parametrize('group,name,path,value', INTEGER_FIELDS)
@pytest.mark.parametrize('kind', ['bool', 'float'])
def test_integer_fields_reject_equal_numeric_primitives(committed, group, name, path, value, kind):
    """In particular False/0 and 1.0/1 must never compare as valid integers."""
    corpus = json.loads(committed)
    body = json.loads(corpus['responses'][name]['body_utf8'])
    target = body
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = bool(value) if kind == 'bool' else float(value)
    corpus['responses'][name]['body_utf8'] = json.dumps(body)
    with pytest.raises(AssertionError, match='expected int'):
        assert_group(json.dumps(corpus).encode(), group)
