"""Additive provisioning of one private intake test collection; no content or pipeline work."""
import base64
import json
from uuid import UUID

ARTIFACT = 'INTAKE_E2E_BOOTSTRAP_B64'
NAME = 'Intake E2E'
READ = '''query ReadIntakeE2E($org: UUID!, $parent: UUID!, $collection: UUID!, $uids: [String!]!) {
  organization: organization(key: {id: $org}) { id }
  parent: collection(key: {organizationId: $org, id: $parent}) { id name }
  collection: collection(key: {organizationId: $org, id: $collection}) { id name parentId kind }
  organizations: organizationMembers(where: {organizationId: {eq: $org}, uid: {in: $uids}}, limit: 3) { uid active }
  members: collectionMembers(where: {organizationId: {eq: $org}, collectionId: {eq: $collection}, uid: {in: $uids}}, limit: 3) {
    uid active role canViewSensitive
  }
}'''


def uid(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or value != value.strip() or not value.isprintable():
        raise ValueError('Invalid intake test identity')
    return value


def parse(encoded):
    """Only identifiers; names, roles, classification access and the worker identity are server-owned."""
    try:
        value = json.loads(base64.b64decode(''.join(encoded.split()), validate=True))
        if not isinstance(value, dict) or set(value) != {'organization_id', 'parent_collection_id', 'collection_id', 'tester_uid'}:
            raise ValueError
        result = {key: str(UUID(value[key])) for key in ('organization_id', 'parent_collection_id', 'collection_id')}
        result['tester_uid'] = uid(value['tester_uid'])
        if result['parent_collection_id'] == result['collection_id']:
            raise ValueError
        return result
    except (ValueError, TypeError, AttributeError, KeyError):
        raise ValueError('Invalid intake test collection artifact; private values withheld') from None


def variables(payload, worker):
    worker = uid(worker)
    if payload['tester_uid'] == worker:
        raise ValueError('The test user must differ from the existing processing actor')
    return {'org': payload['organization_id'], 'parent': payload['parent_collection_id'],
            'collection': payload['collection_id'], 'uids': [payload['tester_uid'], worker]}


def missing_request(payload, worker, live):
    """Refuse conflicting rows before writing anything. INSERT only, transactionally; never upsert permissions."""
    values = variables(payload, worker)
    try:
        if str(UUID(live['organization']['id'])) != values['org']:
            raise ValueError
        parent = live['parent']
        if str(UUID(parent['id'])) != values['parent'] or parent['name'] != 'Insects':
            raise ValueError
        collection = live['collection']
        if collection is not None and (str(UUID(collection['id'])) != values['collection']
                or collection['name'] != NAME or str(UUID(collection['parentId'])) != values['parent']
                or collection.get('kind') not in (None, 'testing')):
            raise ValueError
        by_kind = {}
        for key in ('organizations', 'members'):
            rows = live[key]
            if not isinstance(rows, list):
                raise ValueError
            by_kind[key] = {row['uid']: row for row in rows}
            if len(by_kind[key]) != len(rows) or set(by_kind[key]) - set(values['uids']):
                raise ValueError
            if any(row['active'] is not True for row in rows):
                raise ValueError
        for identity, row in by_kind['members'].items():
            if row['role'] != 'operator' or row['canViewSensitive'] is not (identity == worker):
                raise ValueError
        if collection is None and by_kind['members']:
            raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError('Intake test collection prerequisites or existing rows differ; nothing was changed') from None
    fields, declarations, write_values = [], ['$org: UUID!'], {'org': values['org']}
    if collection is None:
        declarations.extend(['$parent: UUID!', '$collection: UUID!'])
        write_values.update(parent=values['parent'], collection=values['collection'])
        fields.append('collection_insert(data: {organizationId: $org, id: $collection, parentId: $parent, name: "Intake E2E", kind: "testing"})')
    for index, identity in enumerate(values['uids']):
        missing_org = identity not in by_kind['organizations']
        missing_member = identity not in by_kind['members']
        if not (missing_org or missing_member):
            continue
        declarations.append(f'$u{index}: String!')
        write_values[f'u{index}'] = identity
        if missing_org:
            fields.append(f'o{index}: organizationMember_insert(data: {{organizationId: $org, uid: $u{index}, active: true}})')
        if missing_member:
            if 'collection' not in write_values:
                declarations.append('$collection: UUID!')
                write_values['collection'] = values['collection']
            sensitive = 'true' if identity == worker else 'false'
            fields.append(f'm{index}: collectionMember_insert(data: {{organizationId: $org, collectionId: $collection, '
                          f'uid: $u{index}, active: true, role: "operator", canViewSensitive: {sensitive}}})')
    if not fields:
        return None
    return {'query': 'mutation ProvisionIntakeE2E(' + ', '.join(declarations) + ') @transaction {\n'
            + '\n'.join(fields) + '\n}', 'variables': write_values}
