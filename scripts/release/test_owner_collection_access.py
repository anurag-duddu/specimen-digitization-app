"""Bounded second-owner access; all identities and IDs here are invented."""
import base64
from copy import deepcopy
import json

import pytest

import data_release as D
import owner_collection_access as A
from test_simple_data_release import ADMIN, WORKER, artifact

OWNER = artifact()
BASE = OWNER['request']['variables']
INTAKE = {'organization_id': BASE['organizationId'], 'parent_collection_id': BASE['collectionId'],
          'collection_id': 'c0ffee00-0000-4000-8000-000000000099', 'tester_uid': 'second-owner-canary'}
BINDING = {'organization_id': INTAKE['organization_id'], 'insects_collection_id': INTAKE['parent_collection_id'],
           'testing_collection_id': INTAKE['collection_id'], 'owner_uid': ADMIN['uid'], 'second_uid': INTAKE['tester_uid']}
OWNER_ENCODED = base64.b64encode(json.dumps(BINDING).encode()).decode()
VALUES = A.variables(OWNER, INTAKE, BINDING, WORKER, D.reviewed.B._prepared)
ENCODED = base64.b64encode(json.dumps(INTAKE).encode()).decode()


def live(complete=False):
    return {'ownerOrganization': {'active': True}, 'testerOrganization': {'active': True},
            'insects': {'id': VALUES['insects'].replace('-', ''), 'name': 'Insects'},
            'testing': {'id': VALUES['testing'].replace('-', ''), 'name': 'Intake E2E',
                        'parentId': VALUES['insects'].replace('-', ''), 'kind': 'testing' if complete else None},
            'owner': {'active': True, 'role': 'admin', 'canViewSensitive': True},
            'tester': {'active': True, 'role': 'operator', 'canViewSensitive': False},
            'target': {'active': True, 'role': 'admin', 'canViewSensitive': True} if complete else None}


def test_reuses_exact_private_inputs_not_display_name_or_email_matching():
    assert VALUES['owner'] == ADMIN['uid'] and VALUES['tester'] == INTAKE['tester_uid']
    for changed in ({**INTAKE, 'organization_id': INTAKE['collection_id']},
                    {**INTAKE, 'parent_collection_id': INTAKE['collection_id']},
                    {**INTAKE, 'tester_uid': ADMIN['uid']}, {**INTAKE, 'tester_uid': WORKER}):
        with pytest.raises(ValueError, match='private values withheld'):
            A.variables(OWNER, changed, BINDING, WORKER, D.reviewed.B._prepared)
    for changed in (None, {}, {**OWNER, 'artifact_sha256': 'wrong'}):
        with pytest.raises(ValueError, match='private values withheld'):
            A.variables(changed, INTAKE, BINDING, WORKER, D.reviewed.B._prepared)


def test_explicit_binding_does_not_follow_a_future_intake_tester():
    assert A.parse(OWNER_ENCODED) == BINDING
    future = {**INTAKE, 'tester_uid': 'unrelated-future-tester'}
    with pytest.raises(ValueError, match='inputs differ'):
        A.variables(OWNER, future, BINDING, WORKER, D.reviewed.B._prepared)
    for payload in (None, [], {**BINDING, 'second_uid': ADMIN['uid']}, {**BINDING, 'role': 'admin'},
                    {**BINDING, 'owner_uid': ' padded '}, {**BINDING, 'organization_id': 'invalid'}):
        with pytest.raises(ValueError, match='private values withheld'):
            A.parse(base64.b64encode(json.dumps(payload).encode()).decode())


def test_absent_owner_binding_preserves_existing_intake_only_configuration(monkeypatch):
    calls = []
    monkeypatch.setattr(D, '_bootstrap', lambda *_: calls.append('ordinary'))
    monkeypatch.setattr(D, 'bootstrap_intake_e2e', lambda *_: calls.append('intake'))
    monkeypatch.setattr(D, 'restore_owner_collection_access', lambda *_: pytest.fail('No owner access opt-in'))
    D.bootstrap(D.Release(object(), object(), intake_artifact=ENCODED))
    assert calls == ['ordinary', 'intake']


def test_single_insert_plus_bounded_marker_does_not_rewrite_existing_permissions():
    result = A.missing_request(VALUES, live())
    query = result['query']
    assert query.count('collectionMember_insert') == 1
    assert 'collection_updateMany' in query and 'kind: {isNull: true}' in query
    assert '@transaction' in query and 'query @redact' in query and 'this == null' in query
    assert 'this.role == \'admin\'' in query and 'this.canViewSensitive == true' in query
    assert not any(word in query for word in ('collectionMember_update', 'upsert', 'delete', 'organizationMember_insert'))
    assert result['variables'] == {**VALUES, 'targetPresent': False}
    assert A.missing_request(VALUES, live(True)) is None
    marked_only = live()
    marked_only['testing']['kind'] = 'testing'
    assert 'collection_updateMany' not in A.missing_request(VALUES, marked_only)['query']
    member_only = live(True)
    member_only['testing']['kind'] = None
    assert 'collectionMember_insert' not in A.missing_request(VALUES, member_only)['query']


@pytest.mark.parametrize('field,value', [
    ('ownerOrganization', None), ('ownerOrganization', {'active': False}),
    ('testerOrganization', {'active': False}), ('owner', None), ('tester', None),
    ('owner', {'active': True, 'role': 'reviewer', 'canViewSensitive': True}),
    ('owner', {'active': True, 'role': 'admin', 'canViewSensitive': False}),
    ('tester', {'active': True, 'role': 'admin', 'canViewSensitive': True}),
    ('target', {'active': False, 'role': 'admin', 'canViewSensitive': True}),
    ('target', {'active': True, 'role': 'operator', 'canViewSensitive': False}),
])
def test_membership_conflicts_never_reactivate_or_promote_existing_rows(field, value):
    state = live()
    state[field] = value
    with pytest.raises(ValueError, match='nothing was changed'):
        A.missing_request(VALUES, state)


@pytest.mark.parametrize('field,value', [('name', 'Renamed'), ('parentId', INTAKE['collection_id']), ('kind', 'museum')])
def test_test_marker_never_reclassifies_an_unexpected_collection(field, value):
    state = live()
    state['testing'][field] = value
    with pytest.raises(ValueError, match='nothing was changed'):
        A.missing_request(VALUES, state)


class Api:
    def __init__(self, *, lost=False, complete=False, readback=True):
        self.state, self.writes, self.lost, self.readback = live(complete), [], lost, readback

    def call(self, method, url, **kwargs):
        assert kwargs['private'] is True
        if method == 'GET':
            assert url == D.WORKER_UID_URL
            return {'payload': {'data': base64.b64encode(WORKER.encode()).decode()}}
        if url.endswith(':executeGraphqlRead'):
            return {'data': deepcopy(self.state)}
        assert url.endswith(':executeGraphql')
        self.writes.append(kwargs['body'])
        if self.readback:
            self.state = live(True)
        if self.lost:
            raise D.Failure('lost acknowledgement')
        return {'data': {}}


def test_release_readback_rerun_and_logs_do_not_repeat_writes_or_expose_identifiers(capsys):
    api = Api()
    D.restore_owner_collection_access(api, OWNER, ENCODED, OWNER_ENCODED)
    D.restore_owner_collection_access(api, OWNER, ENCODED, OWNER_ENCODED)
    assert len(api.writes) == 1
    output = capsys.readouterr().out
    assert 'skipped' in output
    assert not any(value in output for value in (*VALUES.values(), WORKER, ADMIN['email'], ENCODED))


def test_acknowledgement_loss_and_incomplete_readback_do_not_blindly_retry():
    api = Api(lost=True)
    with pytest.raises(D.Failure, match='lost acknowledgement'):
        D.restore_owner_collection_access(api, OWNER, ENCODED, OWNER_ENCODED)
    D.restore_owner_collection_access(api, OWNER, ENCODED, OWNER_ENCODED)
    assert len(api.writes) == 1
    api = Api(readback=False)
    with pytest.raises(D.Failure, match='readback is incomplete'):
        D.restore_owner_collection_access(api, OWNER, ENCODED, OWNER_ENCODED)
    assert len(api.writes) == 1


def test_existing_conflict_stops_release_before_write():
    api = Api()
    api.state['target'] = {'active': False, 'role': 'admin', 'canViewSensitive': True}
    with pytest.raises(D.Failure, match='nothing was changed'):
        D.restore_owner_collection_access(api, OWNER, ENCODED, OWNER_ENCODED)
    assert not api.writes


def test_conflicting_readback_reports_uncertainty_after_dispatch():
    class ConflictingReadback(Api):
        def call(self, method, url, **kwargs):
            result = super().call(method, url, **kwargs)
            if url.endswith(':executeGraphql'):
                self.state['target']['active'] = False
            return result

    api = ConflictingReadback()
    with pytest.raises(D.Failure, match='readback differs after the write') as error:
        D.restore_owner_collection_access(api, OWNER, ENCODED, OWNER_ENCODED)
    assert len(api.writes) == 1 and 'nothing was changed' not in str(error.value)
