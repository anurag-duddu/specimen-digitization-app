"""The collection catalog provides context without manufacturing authorization."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from specimen_digitization.application.api import create_app
from specimen_digitization.application.production import SqlConnectRepository
from specimen_digitization.application.workflow import OperationalBlock

ORG = 'c0ffee00-0000-4000-8000-000000000001'
ROOT = 'c0ffee00-0000-4000-8000-000000000002'
INSECTS = 'c0ffee00-0000-4000-8000-000000000003'
TESTING = 'c0ffee00-0000-4000-8000-000000000004'
OTHER = 'c0ffee00-0000-4000-8000-000000000005'
USER = 'owner-fixture'
HEADERS = {'Authorization': 'Bearer fixture', 'X-Firebase-AppCheck': 'fixture'}
ROWS = [{'id': ROOT, 'name': 'Zoology', 'parentId': None, 'kind': None},
        {'id': INSECTS, 'name': 'Insects', 'parentId': ROOT, 'kind': None},
        {'id': TESTING, 'name': 'Intake E2E', 'parentId': INSECTS, 'kind': 'testing'},
        {'id': OTHER, 'name': 'Mammals', 'parentId': ROOT, 'kind': None}]


def adapter(rows):
    repo = object.__new__(SqlConnectRepository)
    repo.execute = Mock(return_value={'collections': rows})
    return repo


def fixture(authorized=(TESTING, INSECTS)):
    repo = adapter(deepcopy(ROWS))
    members = [{'organization_id': ORG, 'collection_id': ident,
                'collection_name': next(row['name'] for row in ROWS if row['id'] == ident),
                'role': 'admin', 'can_view_sensitive': True} for ident in authorized]
    app = create_app(mode='production', repository=repo, blobs=SimpleNamespace(), adapters=SimpleNamespace(),
                     identity_verifier=lambda *_: USER, memberships=lambda _: members,
                     origins=['https://specimen-digitization.web.app'])
    return TestClient(app), repo


def test_catalog_keeps_parent_context_separate_from_permissions_and_default():
    client, repo = fixture()
    response = client.get(f'/v1/organizations/{ORG}/collections', headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert [row['collection_id'] for row in body['items']] == [TESTING, INSECTS]
    assert [row['collection_id'] for row in body['items'] if row['is_default']] == [INSECTS]
    assert [row['collection_id'] for row in body['hierarchy']] == [ROOT, INSECTS, TESTING, OTHER]
    assert body['items'][0]['kind'] == 'testing'
    assert body['items'][1]['parent_collection_id'] == ROOT
    assert all(set(row) == {'collection_id', 'display_name', 'parent_collection_id', 'kind'}
               for row in body['hierarchy'])
    repo.execute.assert_called_once_with('ListCollectionHierarchy', {'organizationId': ORG, 'actorUid': USER})
    # Catalog presence never grants that collection's data API.
    denied = client.get(f'/v1/organizations/{ORG}/specimens', params={'collection_id': OTHER}, headers=HEADERS)
    assert denied.status_code == 403


def test_unauthorized_organization_cannot_trigger_catalog_query():
    client, repo = fixture()
    assert client.get(f'/v1/organizations/{OTHER}/collections', headers=HEADERS).status_code == 403
    repo.execute.assert_not_called()
    assert client.get(f'/v1/organizations/{ORG}/collections').status_code == 401
    repo.execute.assert_not_called()


def test_ungranted_testing_collection_is_not_published_as_museum_context():
    client, _ = fixture((INSECTS,))
    body = client.get(f'/v1/organizations/{ORG}/collections', headers=HEADERS).json()
    assert [row['collection_id'] for row in body['hierarchy']] == [ROOT, INSECTS, OTHER]
    assert len(body['items']) == 1


def test_missing_authorized_catalog_node_fails_instead_of_disguising_it_as_a_root():
    client, repo = fixture()
    repo.execute.return_value = {'collections': [row for row in ROWS if row['id'] != TESTING]}
    response = client.get(f'/v1/organizations/{ORG}/collections', headers=HEADERS)
    assert response.status_code == 503
    assert 'items' not in response.json()


@pytest.mark.parametrize('problem', ['duplicate', 'cycle', 'orphan', 'unknown_kind', 'truncated', 'missing_rows'])
def test_malformed_or_incomplete_catalog_is_not_presented_as_an_authoritative_tree(problem):
    rows = deepcopy(ROWS)
    if problem == 'duplicate':
        rows.append(deepcopy(rows[0]))
    elif problem == 'cycle':
        rows[0]['parentId'] = INSECTS
    elif problem == 'orphan':
        rows[0]['parentId'] = ORG
    elif problem == 'unknown_kind':
        rows[0]['kind'] = 'unrecognized'
    elif problem == 'truncated':
        rows = [rows[0]] * 1001
    elif problem == 'missing_rows':
        rows = None
    with pytest.raises(OperationalBlock, match='collection_hierarchy_invalid'):
        adapter(rows).collection_hierarchy(ORG, USER)
