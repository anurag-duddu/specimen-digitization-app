"""The owner's second sign-in receives the same Insects membership, and no other grant.

Identifiers come from the existing private owner and intake-test provisioning inputs.
This is a bounded correction, not account linking or an organization-wide role policy.
"""
import base64
import json
from uuid import UUID

import intake_e2e_bootstrap as intake

ARTIFACT = 'OWNER_COLLECTION_ACCESS_B64'
DECLARATIONS = '$org: UUID!, $insects: UUID!, $testing: UUID!, $owner: String!, $tester: String!'
READ_FIELDS = '''
  ownerOrganization: organizationMember(key: {organizationId: $org, uid: $owner}) { active }
  testerOrganization: organizationMember(key: {organizationId: $org, uid: $tester}) { active }
  insects: collection(key: {organizationId: $org, id: $insects}) { id name }
  testing: collection(key: {organizationId: $org, id: $testing}) { id name parentId kind }
  owner: collectionMember(key: {organizationId: $org, collectionId: $insects, uid: $owner}) { active role canViewSensitive }
  tester: collectionMember(key: {organizationId: $org, collectionId: $testing, uid: $tester}) { active role canViewSensitive }
  target: collectionMember(key: {organizationId: $org, collectionId: $insects, uid: $tester}) { active role canViewSensitive }
'''
READ = 'query ReadOwnerCollectionAccess(' + DECLARATIONS + ') {' + READ_FIELDS + '}'
PRECONDITIONS = '''
  query @redact {
    ownerOrganization: organizationMember(key: {organizationId: $org, uid: $owner})
      @check(expr: "this.active == true") { active }
    testerOrganization: organizationMember(key: {organizationId: $org, uid: $tester})
      @check(expr: "this.active == true") { active }
    insects: collection(key: {organizationId: $org, id: $insects})
      @check(expr: "this.name == 'Insects'") { name }
    testing: collection(key: {organizationId: $org, id: $testing})
      @check(expr: "this.name == 'Intake E2E' && this.parentId == vars.insects && (this.kind == null || this.kind == 'testing')") { name parentId kind }
    owner: collectionMember(key: {organizationId: $org, collectionId: $insects, uid: $owner})
      @check(expr: "this.active == true && this.role == 'admin' && this.canViewSensitive == true") { active role canViewSensitive }
    tester: collectionMember(key: {organizationId: $org, collectionId: $testing, uid: $tester})
      @check(expr: "this.active == true && this.role == 'operator' && this.canViewSensitive == false") { active role canViewSensitive }
    target: collectionMember(key: {organizationId: $org, collectionId: $insects, uid: $tester})
      @check(expr: "vars.targetPresent ? (this.active == true && this.role == 'admin' && this.canViewSensitive == true) : this == null") { active role canViewSensitive }
  }
'''
INSERT = '''
  collectionMember_insert(data: {organizationId: $org, collectionId: $insects, uid: $tester,
    active: true, role: "admin", canViewSensitive: true})
'''
MARK_TESTING = '''
  collection_updateMany(where: {organizationId: {eq: $org}, id: {eq: $testing}, kind: {isNull: true}},
    data: {kind: "testing"}) @check(expr: "this == 1")
'''


def parse(encoded):
    """Explicit owner-alias intent, independent of the generic intake tester input."""
    try:
        payload = json.loads(base64.b64decode(''.join(encoded.split()), validate=True))
        if set(payload) != {'organization_id', 'insects_collection_id', 'testing_collection_id', 'owner_uid', 'second_uid'}:
            raise ValueError
        result = {key: str(UUID(payload[key])) for key in ('organization_id', 'insects_collection_id', 'testing_collection_id')}
        result.update({key: intake.uid(payload[key]) for key in ('owner_uid', 'second_uid')})
        if (result['owner_uid'] == result['second_uid']
                or result['insects_collection_id'] == result['testing_collection_id']):
            raise ValueError
        return result
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError('Invalid owner collection access input; private values withheld') from None


def variables(owner_artifact, intake_artifact, binding, worker, prepared):
    """Resolve exact reviewed identifiers without embedding either identity in source."""
    try:
        approved = prepared._approved_hierarchy(owner_artifact, owner_artifact['artifact_sha256'])
        owner = approved['request']['variables']
        if approved['hierarchy']['admin_collection_key'] != 'insects':
            raise ValueError
        result = {'org': str(UUID(owner['organizationId'])), 'insects': str(UUID(owner['collectionId'])),
                  'testing': intake_artifact['collection_id'], 'owner': intake.uid(owner['uid']),
                  'tester': intake_artifact['tester_uid']}
        if (result['org'] != intake_artifact['organization_id']
                or result['insects'] != intake_artifact['parent_collection_id']
                or len({result['owner'], result['tester'], intake.uid(worker)}) != 3
                or binding != {'organization_id': result['org'], 'insects_collection_id': result['insects'],
                               'testing_collection_id': result['testing'], 'owner_uid': result['owner'],
                               'second_uid': result['tester']}):
            raise ValueError
        return result
    except (ValueError, TypeError, KeyError, AttributeError, OSError):
        raise ValueError('Owner collection access inputs differ; private values withheld') from None


def missing_request(values, live):
    """Read first; conflicts never reactivate or overwrite an existing membership."""
    try:
        if any(live[key]['active'] is not True for key in ('ownerOrganization', 'testerOrganization')):
            raise ValueError
        if str(UUID(live['insects']['id'])) != values['insects'] or live['insects']['name'] != 'Insects':
            raise ValueError
        testing = live['testing']
        if (str(UUID(testing['id'])) != values['testing'] or testing['name'] != intake.NAME
                or str(UUID(testing['parentId'])) != values['insects'] or testing.get('kind') not in (None, 'testing')):
            raise ValueError
        admin = {'active': True, 'role': 'admin', 'canViewSensitive': True}
        tester = {'active': True, 'role': 'operator', 'canViewSensitive': False}
        if live['owner'] != admin or live['tester'] != tester:
            raise ValueError
        if live['target'] is not None and live['target'] != admin:
            raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError('Owner collection access prerequisites or existing rows differ; nothing was changed') from None
    fields = (INSERT if live['target'] is None else '') + (MARK_TESTING if testing.get('kind') is None else '')
    if not fields:
        return None
    return {'query': 'mutation RestoreOwnerCollectionAccess(' + DECLARATIONS + ', $targetPresent: Boolean!) @transaction {'
            + PRECONDITIONS + fields + '}', 'variables': {**values, 'targetPresent': live['target'] is not None}}
