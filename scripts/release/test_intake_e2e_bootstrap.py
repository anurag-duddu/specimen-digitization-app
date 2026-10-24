"""Provisioning contracts only; these tests do not establish live Gmail acceptance."""
import base64
from copy import deepcopy
import json

import pytest

import data_release as D
import intake_e2e_bootstrap as E

PAYLOAD = {'organization_id': 'c0ffee00-0000-4000-8000-000000000001',
           'parent_collection_id': 'c0ffee00-0000-4000-8000-000000000002',
           'collection_id': 'c0ffee00-0000-4000-8000-000000000003', 'tester_uid': 'tester-canary'}
WORKER = 'existing-worker-canary'


def encoded(value):
    return base64.b64encode(json.dumps(value).encode()).decode()


def live(complete=False):
    return {'organization': {'id': PAYLOAD['organization_id'].replace('-', '')},
            'parent': {'id': PAYLOAD['parent_collection_id'].replace('-', ''), 'name': 'Insects'},
            'collection': {'id': PAYLOAD['collection_id'].replace('-', ''), 'name': E.NAME,
                           'parentId': PAYLOAD['parent_collection_id'].replace('-', '')} if complete else None,
            'organizations': [{'uid': identity, 'active': True} for identity in (PAYLOAD['tester_uid'], WORKER)],
            'members': [{'uid': identity, 'active': True, 'role': 'operator', 'canViewSensitive': identity == WORKER}
                        for identity in (PAYLOAD['tester_uid'], WORKER)] if complete else []}


def test_valid_artifact_normalizes_uuid_and_refuses_private_shape_expansion():
    assert E.parse(encoded(PAYLOAD)) == PAYLOAD
    assert E.parse(encoded({**PAYLOAD, 'collection_id': PAYLOAD['collection_id'].replace('-', '')})) == PAYLOAD
    for value in ({**PAYLOAD, 'worker_uid': 'another-actor'}, {**PAYLOAD, 'role': 'admin'},
                  {**PAYLOAD, 'collection_id': PAYLOAD['parent_collection_id']},
                  {**PAYLOAD, 'tester_uid': ' trailing '}, {**PAYLOAD, 'organization_id': 'not-a-uuid'}, [], None):
        with pytest.raises(ValueError, match='private values withheld'):
            E.parse(encoded(value))
    with pytest.raises(ValueError, match='differ'):
        E.variables(PAYLOAD, PAYLOAD['tester_uid'])


def test_atomic_insert_only_does_not_start_processing_or_expand_existing_roles():
    state = live()
    state['organizations'] = [{'uid': WORKER, 'active': True}]
    result = E.missing_request(PAYLOAD, WORKER, state)
    assert '@transaction' in result['query']
    assert 'collection_insert' in result['query'] and 'o0: organizationMember_insert' in result['query']
    assert 'o1: organizationMember_insert' not in result['query']
    assert result['query'].count('collectionMember_insert') == 2
    assert 'canViewSensitive: false' in result['query'] and 'canViewSensitive: true' in result['query']
    assert not any(word in result['query'].lower() for word in ('specimen_insert', 'submission', 'upsert', 'delete', 'update'))
    assert E.missing_request(PAYLOAD, WORKER, live(True)) is None


@pytest.mark.parametrize('problem', ['missing_org', 'wrong_parent', 'wrong_name', 'wrong_parent_name',
                                   'inactive_org', 'inactive_member', 'expanded_role', 'sensitivity', 'duplicate_uid'])
def test_conflicting_rows_fail_before_any_write(problem):
    state = live(True)
    if problem == 'missing_org':
        state['organization'] = None
    elif problem == 'wrong_parent':
        state['collection']['parentId'] = PAYLOAD['collection_id']
    elif problem == 'wrong_name':
        state['collection']['name'] = 'Existing institutional collection'
    elif problem == 'wrong_parent_name':
        state['parent']['name'] = 'Another department'
    elif problem == 'inactive_org':
        state['organizations'][0]['active'] = False
    elif problem == 'inactive_member':
        state['members'][0]['active'] = False
    elif problem == 'expanded_role':
        state['members'][0]['role'] = 'admin'
    elif problem == 'sensitivity':
        state['members'][0]['canViewSensitive'] = True
    elif problem == 'duplicate_uid':
        state['members'].append(deepcopy(state['members'][0]))
    with pytest.raises(ValueError, match='nothing was changed'):
        E.missing_request(PAYLOAD, WORKER, state)


class Api:
    def __init__(self, lost=False):
        self.complete, self.writes, self.lost = False, 0, lost

    def call(self, method, url, **kwargs):
        assert kwargs['private'] is True
        if method == 'GET':
            assert url == D.WORKER_UID_URL
            return {'payload': {'data': base64.b64encode(WORKER.encode()).decode()}}
        if url.endswith(':executeGraphqlRead'):
            return {'data': live(self.complete)}
        assert url.endswith(':executeGraphql')
        self.writes += 1
        self.complete = True
        if self.lost:
            raise D.Failure('lost acknowledgement')
        return {'data': {'collection_insert': {}}}


def test_release_reads_back_and_reruns_without_duplicate_mutation(capsys):
    api = Api()
    D.bootstrap_intake_e2e(api, encoded(PAYLOAD))
    D.bootstrap_intake_e2e(api, encoded(PAYLOAD))
    assert api.writes == 1
    output = capsys.readouterr().out
    assert 'memberships match, skipped' in output
    assert not any(value in output for value in (*PAYLOAD.values(), WORKER))


def test_lost_ack_is_reconciled_by_next_read_not_blindly_retried():
    api = Api(lost=True)
    with pytest.raises(D.Failure, match='lost acknowledgement'):
        D.bootstrap_intake_e2e(api, encoded(PAYLOAD))
    assert api.writes == 1
    D.bootstrap_intake_e2e(api, encoded(PAYLOAD))
    assert api.writes == 1
