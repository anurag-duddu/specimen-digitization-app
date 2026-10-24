"""Opt-in disposable SQL Connect proof of the exact release mutation and catalog query."""
from copy import deepcopy
import os
from uuid import uuid4

import pytest
import requests

import owner_collection_access as A
from test_owner_collection_access import VALUES
from specimen_digitization.application.production import SqlConnectRepository, sql_emulator_host

pytestmark = pytest.mark.skipif(os.getenv('SPECIMEN_TEST_SQL_EMULATOR') != 'true',
                               reason='Requires explicitly started isolated SQL Connect/PostgreSQL emulator')


@pytest.fixture
def lab():
    host = sql_emulator_host()  # Rejects non-loopback hosts and any cloud target.
    session = requests.Session()
    session.trust_env = False
    session.headers['Authorization'] = 'Bearer owner'
    base = f'http://{host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service'
    values = {**VALUES, 'org': str(uuid4())}

    def raw(query, variables=None, *, read=False):
        response = session.post(base + (':executeGraphqlRead' if read else ':executeGraphql'),
                                json={'query': query, 'variables': variables or values}, timeout=30)
        body = response.json()
        assert response.status_code == 200, body
        return body

    seed = '''mutation SeedCollectionAccess(''' + A.DECLARATIONS + ''') @transaction {
      organization_insert(data: {id: $org, name: "Synthetic museum"})
      insects: collection_insert(data: {organizationId: $org, id: $insects, name: "Insects"})
      testing: collection_insert(data: {organizationId: $org, id: $testing, name: "Intake E2E", parentId: $insects})
      ownerOrg: organizationMember_insert(data: {organizationId: $org, uid: $owner, active: true})
      testerOrg: organizationMember_insert(data: {organizationId: $org, uid: $tester, active: true})
      owner: collectionMember_insert(data: {organizationId: $org, collectionId: $insects, uid: $owner,
        active: true, role: "admin", canViewSensitive: true})
      tester: collectionMember_insert(data: {organizationId: $org, collectionId: $testing, uid: $tester,
        active: true, role: "operator", canViewSensitive: false})
    }'''
    assert not raw(seed).get('errors')

    def read():
        result = raw(A.READ, read=True)
        assert not result.get('errors'), result
        return result['data']

    try:
        yield values, raw, read, SqlConnectRepository(project='demo-specimen-data', emulator_host=host, session=session)
    finally:
        session.close()


def test_real_missing_membership_insert_testing_marker_and_idempotent_readback(lab):
    values, raw, read, repo = lab
    before = read()
    request = A.missing_request(values, before)
    result = raw(**request)
    assert not result.get('errors'), result
    after = read()
    assert after['target'] == before['owner']
    assert after['owner'] == before['owner'] and after['tester'] == before['tester']
    assert after['testing'] == {**before['testing'], 'kind': 'testing'}
    assert A.missing_request(values, after) is None
    # A stale duplicate request cannot duplicate, upsert, or rewrite anything.
    assert raw(**request).get('errors')
    assert read() == after
    tree = repo.collection_hierarchy(values['org'], values['tester'])
    assert [(node['display_name'], node['kind']) for node in tree] == [('Insects', 'museum'), ('Intake E2E', 'testing')]
    assert tree[1]['parent_collection_id'] == values['insects']
    assert {member['collection_id'] for member in repo.memberships(values['tester'])} == {values['insects'], values['testing']}


@pytest.mark.parametrize('existing', ['membership', 'marker'])
def test_real_partial_prior_completion_only_writes_the_missing_piece(lab, existing):
    values, raw, read, _ = lab
    if existing == 'membership':
        query = 'mutation Prior($org: UUID!, $insects: UUID!, $tester: String!) @transaction {' + A.INSERT + '}'
        used = {key: values[key] for key in ('org', 'insects', 'tester')}
    else:
        query = 'mutation Prior($org: UUID!, $testing: UUID!) @transaction {' + A.MARK_TESTING + '}'
        used = {key: values[key] for key in ('org', 'testing')}
    result = raw(query, used)
    assert not result.get('errors'), result
    before = read()
    request = A.missing_request(values, before)
    assert ('collectionMember_insert' in request['query']) is (existing != 'membership')
    assert ('collection_updateMany' in request['query']) is (existing != 'marker')
    result = raw(**request)
    assert not result.get('errors'), result
    assert A.missing_request(values, read()) is None


@pytest.mark.parametrize('race', ['owner_revoked', 'tester_org_revoked', 'owner_role', 'owner_sensitive',
                                'target_inactive', 'target_operator', 'target_admin', 'marker_kind', 'marker_done', 'parent'])
def test_transaction_refuses_changed_preconditions_without_partial_writes(lab, race):
    values, raw, read, _ = lab
    request = A.missing_request(values, read())
    changes = {
        'owner_revoked': 'organizationMember_update(key: {organizationId: $org, uid: $owner}, data: {active: false})',
        'tester_org_revoked': 'organizationMember_update(key: {organizationId: $org, uid: $tester}, data: {active: false})',
        'owner_role': 'collectionMember_update(key: {organizationId: $org, collectionId: $insects, uid: $owner}, data: {role: "reviewer"})',
        'owner_sensitive': 'collectionMember_update(key: {organizationId: $org, collectionId: $insects, uid: $owner}, data: {canViewSensitive: false})',
        'target_inactive': 'collectionMember_insert(data: {organizationId: $org, collectionId: $insects, uid: $tester, active: false, role: "admin", canViewSensitive: true})',
        'target_operator': 'collectionMember_insert(data: {organizationId: $org, collectionId: $insects, uid: $tester, active: true, role: "operator", canViewSensitive: false})',
        'target_admin': 'collectionMember_insert(data: {organizationId: $org, collectionId: $insects, uid: $tester, active: true, role: "admin", canViewSensitive: true})',
        'marker_kind': 'collection_update(key: {organizationId: $org, id: $testing}, data: {kind: "museum"})',
        'marker_done': 'collection_update(key: {organizationId: $org, id: $testing}, data: {kind: "testing"})',
        'parent': 'collection_update(key: {organizationId: $org, id: $testing}, data: {parentId: null})',
    }
    # Keep only actually-used declarations; the engine refuses unused variables.
    from re import findall
    field = changes[race]
    used = set(findall(r'\$(\w+)', field))
    declarations = ', '.join(part for part in A.DECLARATIONS.split(', ') if part.split(':')[0][1:] in used)
    changed = raw('mutation ChangePrerequisite(' + declarations + ') {' + field + '}',
                  {key: value for key, value in values.items() if key in used})
    assert not changed.get('errors'), changed
    before = deepcopy(read())
    refused = raw(**request)
    assert refused.get('errors'), refused
    assert read() == before, 'A refused correction partially changed membership or test classification'


def test_catalog_query_refuses_a_foreign_or_revoked_organization_member(lab):
    values, raw, _, repo = lab
    from specimen_digitization.application.storage import Conflict
    with pytest.raises(Conflict):
        repo.collection_hierarchy(values['org'], 'unrelated-fixture-user')
    result = raw('''mutation Revoke($org: UUID!, $owner: String!) {
      organizationMember_update(key: {organizationId: $org, uid: $owner}, data: {active: false})
    }''', {'org': values['org'], 'owner': values['owner']})
    assert not result.get('errors'), result
    with pytest.raises(Conflict):
        repo.collection_hierarchy(values['org'], values['owner'])
