"""Exact first-admin maintenance operation, callable only by protected data release.

API contracts checked 2026-09-08:
https://docs.cloud.google.com/identity-platform/docs/reference/rest/v1/projects.accounts/lookup
https://firebase.google.com/docs/reference/sql-connect/rest/v1/projects.locations.services/executeGraphql
https://firebase.google.com/docs/reference/sql-connect/rest/v1/projects.locations.services/executeGraphqlRead
No generic GraphQL input, account creation, role update or implicit retry.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from uuid import UUID

from release_admission import digest, require
from release_context import PROJECT, REPOSITORY

ROOT = Path(__file__).resolve().parents[2]
SERVICE = f"projects/{PROJECT}/locations/us-east4/services/specimen-digitization-service"
_spec = importlib.util.spec_from_file_location("release_prepared_admin", ROOT / "scripts/data/bootstrap_admin.py")
_prepared = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_prepared)

READ_SCOPE = """query VerifyFirstAdministrator(
  $organizationId: UUID!, $collectionId: UUID!, $uid: String!
) {
  organization(key: {id: $organizationId}) { id }
  collection(key: {organizationId: $organizationId, id: $collectionId}) { id organizationId }
  organizationMember(key: {organizationId: $organizationId, uid: $uid}) { uid active }
  members: collectionMembers(where: {organizationId: {eq: $organizationId}, uid: {eq: $uid}}, limit: 2) {
    uid collectionId active role canViewSensitive
  }
  admins: collectionMembers(where: {organizationId: {eq: $organizationId}, role: {eq: "admin"}}, limit: 2) { uid }
}
"""

READ_FIRST_SCOPE = """query VerifyFirstScopeAndOwner($organizationId: UUID!, $collectionId: UUID!) {
  organization(key: {id: $organizationId}) { id name }
  collections(where: {organizationId: {eq: $organizationId}}, limit: 2) { id organizationId name parentId }
  matchingCollections: collections(where: {id: {eq: $collectionId}}, limit: 2) { id organizationId name parentId }
  organizationMembers(where: {organizationId: {eq: $organizationId}}, limit: 2) { uid active }
  members: collectionMembers(where: {organizationId: {eq: $organizationId}}, limit: 2) {
    uid collectionId active role canViewSensitive
  }
}
"""

# One collection more than the reviewed tree is read back, so an extra row under
# the new organization or an extra row bound to a reviewed identifier is visible
# instead of being truncated away by the limit.
READ_FIRST_SCOPE_HIERARCHY = """query VerifyFirstScopeHierarchy(
  $organizationId: UUID!, $ids: [UUID!]!, $limit: Int!
) {
  organization(key: {id: $organizationId}) { id name }
  collections(where: {organizationId: {eq: $organizationId}}, limit: $limit) { id organizationId name parentId }
  matchingCollections: collections(where: {id: {in: $ids}}, limit: $limit) { id organizationId name parentId }
  organizationMembers(where: {organizationId: {eq: $organizationId}}, limit: 2) { uid active }
  members: collectionMembers(where: {organizationId: {eq: $organizationId}}, limit: 2) {
    uid collectionId active role canViewSensitive
  }
}
"""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def reviewed_tree(hierarchy):
    """Only the committed reviewed tree, at the exact digest the artifact bound.

    The path is fixed, not taken from the artifact, so a prepared payload cannot
    redirect regeneration at another file. The digest is recomputed from this
    source checkout, so editing the tree after preparation fails closed instead
    of silently bootstrapping a different set of collections.
    """
    require(isinstance(hierarchy, dict)
            and set(hierarchy) == {"tree_path", "tree_sha256", "collections", "admin_collection_key"},
            "invalid reviewed collection tree binding")
    require(hierarchy["tree_path"] == _prepared.TREE_PATH, "unreviewed collection tree path")
    digest(hierarchy["tree_sha256"], "reviewed collection tree")
    tree = (ROOT / _prepared.TREE_PATH).read_bytes()
    require(hashlib.sha256(tree).hexdigest() == hierarchy["tree_sha256"],
            "reviewed collection tree changed after preparation")
    return tree


def validate_prepared(payload, expected_sha256):
    """Regenerate, do not trust the query or caller-supplied apply requirements."""
    digest(expected_sha256, "approved first-admin artifact")
    try:
        identity, variables = payload["auth_record"], payload["request"]["variables"]
        require(variables["canViewSensitive"] is False, "initial sensitive access is not authorized")
        version = payload["schema_version"]
        require(version in {"first-admin-bootstrap/v1", "first-scope-owner-bootstrap/v1",
                            "first-scope-hierarchy-bootstrap/v1"}, "unknown bootstrap mode")
        if version == "first-scope-hierarchy-bootstrap/v1":
            expected = _prepared.prepare_first_scope_hierarchy(
                auth_record=identity, requested_email=identity["email"], requested_uid=identity["uid"],
                organization_id=variables["organizationId"], organization_name=variables["organizationName"],
                can_view_sensitive=False, tree=reviewed_tree(payload["hierarchy"]),
                collections=payload["hierarchy"]["collections"],
                admin_collection_key=payload["hierarchy"]["admin_collection_key"],
            )
        else:
            extra = {}
            prepare = _prepared.prepare_bootstrap
            if version == "first-scope-owner-bootstrap/v1":
                prepare = _prepared.prepare_first_scope
                extra = {"organization_name": variables["organizationName"], "collection_name": variables["collectionName"]}
            expected = prepare(
                auth_record=identity, requested_email=identity["email"], requested_uid=identity["uid"],
                organization_id=variables["organizationId"], collection_id=variables["collectionId"],
                can_view_sensitive=False,
                **extra,
            )
        require(expected["artifact_sha256"] == expected_sha256 and canonical(payload) == canonical(expected),
                "prepared first-admin artifact changed")
    except (KeyError, TypeError, AttributeError):
        raise ValueError("invalid prepared first-admin artifact") from None
    return expected


def graphql_data(response):
    require(isinstance(response, dict) and not response.get("errors") and not response.get("code")
            and isinstance(response.get("data"), dict), "maintenance GraphQL result failed or unknown")
    return response["data"]


def same_uuid(observed, expected):
    # SQL Connect returns UUID scalars without hyphens; compare the actual UUID.
    try:
        return isinstance(observed, str) and UUID(observed) == UUID(expected)
    except (ValueError, TypeError, AttributeError):
        return False


def read_scope(google, variables):
    response = google.request("data", "POST", SERVICE + ":executeGraphqlRead", body={
        "query": READ_SCOPE,
        "variables": {key: variables[key] for key in ("organizationId", "collectionId", "uid")},
    })
    data = graphql_data(response)
    organization, collection = data.get("organization"), data.get("collection")
    require(isinstance(organization, dict) and same_uuid(organization.get("id"), variables["organizationId"])
            and isinstance(collection, dict) and same_uuid(collection.get("id"), variables["collectionId"])
            and same_uuid(collection.get("organizationId"), variables["organizationId"]), "existing bootstrap scope mismatch")
    require("organizationMember" in data and isinstance(data.get("members"), list)
            and isinstance(data.get("admins"), list), "membership observation incomplete")
    return data


def read_first_scope(google, variables, observe=None):
    response = google.request("data", "POST", SERVICE + ":executeGraphqlRead", body={
        "query": READ_FIRST_SCOPE,
        "variables": {key: variables[key] for key in ("organizationId", "collectionId")},
    })
    if observe is not None:
        observe(response)
    data = graphql_data(response)
    require(set(data) == {"organization", "collections", "matchingCollections", "organizationMembers", "members"}
            and all(isinstance(data[key], list) and len(data[key]) <= 2 for key in
                    ("collections", "matchingCollections", "organizationMembers", "members")),
            "first-scope observation incomplete")
    return data


def read_first_scope_hierarchy(google, variables, identifiers, limit, observe=None):
    response = google.request("data", "POST", SERVICE + ":executeGraphqlRead", body={
        "query": READ_FIRST_SCOPE_HIERARCHY,
        "variables": {"organizationId": variables["organizationId"], "ids": identifiers, "limit": limit},
    })
    if observe is not None:
        observe(response)
    data = graphql_data(response)
    require(set(data) == {"organization", "collections", "matchingCollections", "organizationMembers", "members"}
            and all(isinstance(data[key], list) and len(data[key]) <= limit
                    for key in ("collections", "matchingCollections"))
            and all(isinstance(data[key], list) and len(data[key]) <= 2
                    for key in ("organizationMembers", "members")),
            "first-scope hierarchy observation incomplete")
    return data


def retain_first_scope(directory, name, value):
    """Fixed attempt-local exclusive evidence; existing intent never resets."""
    descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(canonical(value) + b"\n")
        output.flush()
        os.fsync(output.fileno())
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def validate_evidence_recipient(recipient):
    """Use the existing reviewed public-key envelope; no private key enters CI."""
    from release_initialize import validate_catalog_recipient
    return validate_catalog_recipient(recipient)


def evidence_retainer(google, expected_sha256, evidence_recipient):
    """The original exclusive local fence and its encrypted sibling, for both modes."""
    provenance = {"source_sha": google.packet["source_sha"], "run_id": google.packet["release_run_id"],
                  "run_attempt": google.packet["release_run_attempt"], "artifact_sha256": expected_sha256}
    directory = google.path.parent
    envelope_provenance = {"repository": REPOSITORY,
                          **{key: provenance[key] for key in ("source_sha", "run_id", "run_attempt")}}
    def retain(name, value):
        from release_catalog_envelope import encrypt_catalog
        # Keep the original exclusive local fence, including on encryption failure.
        # Only its separately encrypted sibling may enter workflow artifacts.
        retain_first_scope(directory, name, value)
        envelope = encrypt_catalog(canonical(value) + b"\n", evidence_recipient["public_key_pem"].encode(),
                                   public_key_sha256=evidence_recipient["public_key_sha256"],
                                   provenance=envelope_provenance)
        retain_first_scope(directory, name.removesuffix(".json") + ".encrypted.json", envelope)
    return provenance, retain


def apply_first_scope(google, payload, expected_sha256, evidence_recipient):
    variables = payload["request"]["variables"]
    before = read_first_scope(google, variables)
    require(before == {"organization": None, "collections": [], "matchingCollections": [],
                       "organizationMembers": [], "members": []},
            "first-scope target is existing or partial; reconcile without adoption")
    provenance, retain = evidence_retainer(google, expected_sha256, evidence_recipient)
    retain("first-scope-owner.intent.json", {
        "version": "first-scope-owner-intent/v1", **provenance,
        "request_sha256": hashlib.sha256(canonical(payload["request"])).hexdigest(),
        "before_sha256": hashlib.sha256(canonical(before)).hexdigest(),
    })
    # Intent is durable before dispatch. Any exception, partial response or failed
    # readback leaves it consumed. A new runner cannot adopt committed rows: the
    # same pinned organization's insert still conflicts. No retry or new IDs.
    response = google.request("data", "POST", SERVICE + ":executeGraphql", body=payload["request"])
    retain("first-scope-owner.response.json", response)
    inserted = graphql_data(response)
    keys = {
        "organization_insert": {"id": "organizationId"},
        "collection_insert": {"organizationId": "organizationId", "id": "collectionId"},
        "organizationMember_insert": {"organizationId": "organizationId", "uid": "uid"},
        "collectionMember_insert": {"organizationId": "organizationId", "collectionId": "collectionId", "uid": "uid"},
    }
    require(set(inserted) == set(keys), "first-scope mutation result incomplete")
    for field, mapping in keys.items():
        row = inserted[field]
        require(isinstance(row, dict) and set(row) == set(mapping), "first-scope inserted key incomplete")
        for key, variable in mapping.items():
            require(row[key] == variables[variable] if key == "uid" else same_uuid(row[key], variables[variable]),
                    "first-scope inserted key differs")
    # Retain even a rejected GraphQL readback before interpreting its fields.
    after = read_first_scope(google, variables, lambda value: retain("first-scope-owner.readback.json", value))
    organization = after["organization"]
    require(isinstance(organization, dict) and set(organization) == {"id", "name"}
            and same_uuid(organization["id"], variables["organizationId"])
            and organization["name"] == variables["organizationName"], "first-scope organization readback differs")
    for key in ("collections", "matchingCollections"):
        require(len(after[key]) == 1, "first-scope collection set differs")
        collection = after[key][0]
        require(isinstance(collection, dict) and set(collection) == {"id", "organizationId", "name", "parentId"}
                and same_uuid(collection["id"], variables["collectionId"])
                and same_uuid(collection["organizationId"], variables["organizationId"])
                and collection["name"] == variables["collectionName"] and collection["parentId"] is None,
                "first-scope collection readback differs")
    require(len(after["organizationMembers"]) == 1 and len(after["members"]) == 1, "first-scope owner set differs")
    owner = after["organizationMembers"][0]
    require(isinstance(owner, dict) and set(owner) == {"uid", "active"}
            and owner["uid"] == variables["uid"] and owner["active"] is True, "first-scope owner differs")
    member = after["members"][0]
    require(isinstance(member, dict) and set(member) == {"uid", "collectionId", "active", "role", "canViewSensitive"}
            and member["uid"] == variables["uid"] and member["active"] is True
            and member["role"] == "admin" and member["canViewSensitive"] is False
            and same_uuid(member["collectionId"], variables["collectionId"]), "first-scope owner readback differs")
    receipt = {"version": "first-scope-owner-applied/v1", **provenance,
               "membership_sha256": hashlib.sha256(canonical(after)).hexdigest(),
               "scope_verified": True, "membership_verified": True, "sensitive_access": False, "release_accepted": False}
    retain("first-scope-owner.verified.json", receipt)
    return receipt


def apply_first_scope_hierarchy(google, payload, expected_sha256, evidence_recipient):
    """Create the whole reviewed tree once: one organization, N collections, two memberships.

    Every gate the four-insert mode applies is applied here for every row: the
    target must be entirely empty, the intent is durable before the single
    dispatch, each insert returns its exact pinned key, and the readback must
    show precisely the reviewed collections with their exact parents.
    """
    variables, hierarchy = payload["request"]["variables"], payload["hierarchy"]
    collections = hierarchy["collections"]
    count = len(collections)
    identifiers = [entry["id"] for entry in collections]
    limit = count + 1
    before = read_first_scope_hierarchy(google, variables, identifiers, limit)
    require(before == {"organization": None, "collections": [], "matchingCollections": [],
                       "organizationMembers": [], "members": []},
            "first-scope hierarchy target is existing or partial; reconcile without adoption")
    provenance, retain = evidence_retainer(google, expected_sha256, evidence_recipient)
    retain("first-scope-hierarchy.intent.json", {
        "version": "first-scope-hierarchy-intent/v1", **provenance,
        "request_sha256": hashlib.sha256(canonical(payload["request"])).hexdigest(),
        "before_sha256": hashlib.sha256(canonical(before)).hexdigest(),
    })
    # Intent is durable before dispatch. Any exception, partial response or failed
    # readback leaves it consumed. A new runner cannot adopt committed rows: the
    # same pinned organization's insert still conflicts. No retry or new IDs.
    response = google.request("data", "POST", SERVICE + ":executeGraphql", body=payload["request"])
    retain("first-scope-hierarchy.response.json", response)
    inserted = graphql_data(response)
    keys = {
        "organization_insert": {"id": "organizationId"},
        "organizationMember_insert": {"organizationId": "organizationId", "uid": "uid"},
        "collectionMember_insert": {"organizationId": "organizationId", "collectionId": "collectionId", "uid": "uid"},
        **{f"c{index}": {"organizationId": "organizationId", "id": f"c{index}Id"} for index in range(count)},
    }
    require(set(inserted) == set(keys), "first-scope hierarchy mutation result incomplete")
    for field, mapping in keys.items():
        row = inserted[field]
        require(isinstance(row, dict) and set(row) == set(mapping), "first-scope hierarchy inserted key incomplete")
        for key, variable in mapping.items():
            require(row[key] == variables[variable] if key == "uid" else same_uuid(row[key], variables[variable]),
                    "first-scope hierarchy inserted key differs")
    # Retain even a rejected GraphQL readback before interpreting its fields.
    after = read_first_scope_hierarchy(google, variables, identifiers, limit,
                                       lambda value: retain("first-scope-hierarchy.readback.json", value))
    organization = after["organization"]
    require(isinstance(organization, dict) and set(organization) == {"id", "name"}
            and same_uuid(organization["id"], variables["organizationId"])
            and organization["name"] == variables["organizationName"],
            "first-scope hierarchy organization readback differs")
    position = {entry["key"]: index for index, entry in enumerate(collections)}
    expected = [{"id": entry["id"], "name": entry["name"],
                 "parentId": None if entry["parent"] is None else collections[position[entry["parent"]]]["id"]}
                for entry in collections]
    # SQL Connect does not promise an order here, so each reviewed identifier must
    # match exactly one observed row and the counts must agree: a missing row, a
    # duplicate row and an unreviewed extra row are all rejected.
    for key in ("collections", "matchingCollections"):
        observed = after[key]
        require(len(observed) == count, "first-scope hierarchy collection set differs")
        for row in expected:
            found = [seen for seen in observed
                     if isinstance(seen, dict) and set(seen) == {"id", "organizationId", "name", "parentId"}
                     and same_uuid(seen["id"], row["id"])]
            require(len(found) == 1, "first-scope hierarchy collection set differs")
            require(same_uuid(found[0]["organizationId"], variables["organizationId"])
                    and found[0]["name"] == row["name"]
                    and (found[0]["parentId"] is None if row["parentId"] is None
                         else same_uuid(found[0]["parentId"], row["parentId"])),
                    "first-scope hierarchy collection readback differs")
    require(len(after["organizationMembers"]) == 1 and len(after["members"]) == 1,
            "first-scope hierarchy owner set differs")
    owner = after["organizationMembers"][0]
    require(isinstance(owner, dict) and set(owner) == {"uid", "active"}
            and owner["uid"] == variables["uid"] and owner["active"] is True,
            "first-scope hierarchy owner differs")
    member = after["members"][0]
    require(isinstance(member, dict) and set(member) == {"uid", "collectionId", "active", "role", "canViewSensitive"}
            and member["uid"] == variables["uid"] and member["active"] is True
            and member["role"] == "admin" and member["canViewSensitive"] is False
            and same_uuid(member["collectionId"], variables["collectionId"]),
            "first-scope hierarchy owner readback differs")
    receipt = {"version": "first-scope-hierarchy-applied/v1", **provenance,
               "membership_sha256": hashlib.sha256(canonical(after)).hexdigest(),
               "scope_verified": True, "membership_verified": True, "collections_verified": count,
               "tree_sha256": hierarchy["tree_sha256"], "sensitive_access": False, "release_accepted": False}
    retain("first-scope-hierarchy.verified.json", receipt)
    return receipt


def fresh_administrator(google, identity):
    """Read the approved administrator's account again, read-only, just before the write: exactly one account with the
    prepared UID and email, verified, enabled and in no tenant."""
    result = google.request("identity", "POST", f"projects/{PROJECT}/accounts:lookup",
                            body={"email": [identity["email"]]})
    users = result.get("users") if isinstance(result, dict) else None
    require(isinstance(users, list) and len(users) == 1 and isinstance(users[0], dict), "unique approved Auth identity required")
    user = users[0]
    # As in Firebase Admin UserRecord.disabled, an omitted proto boolean means
    # false. Reject non-boolean supplied values instead of SDK truthiness coercion.
    require(user.get("localId") == identity["uid"] and user.get("email") == identity["email"]
            and user.get("emailVerified") is True and user.get("disabled", False) is False
            and not user.get("tenantId"), "fresh Auth identity differs, is unverified or disabled")


def bootstrap(google, prepared_payload, expected_sha256, evidence_recipient=None):
    """Recheck identity, execute exact transaction once, then verify membership.

    The caller supplies the already-admitted data-plane Google transport only
    after verified restore/schema/index readiness. That transport rechecks source,
    identity, expiry and the cumulative budget immediately before each request.
    An uncertain mutation or readback propagates; retries require reconciliation.
    The transaction's organization lock and insert-only predicates prevent replay.
    """
    require(google.plane == "data", "first-admin maintenance requires the data release identity")
    payload = validate_prepared(prepared_payload, expected_sha256)
    version = payload["schema_version"]
    first_scope = version in {"first-scope-owner-bootstrap/v1", "first-scope-hierarchy-bootstrap/v1"}
    if first_scope:
        validate_evidence_recipient(evidence_recipient)
    else:
        require(evidence_recipient is None, "legacy bootstrap does not accept an evidence recipient")
    identity, variables = payload["auth_record"], payload["request"]["variables"]
    fresh_administrator(google, identity)
    if version == "first-scope-hierarchy-bootstrap/v1":
        return apply_first_scope_hierarchy(google, payload, expected_sha256, evidence_recipient)
    if first_scope:
        return apply_first_scope(google, payload, expected_sha256, evidence_recipient)
    before = read_scope(google, variables)
    require(before["organizationMember"] is None and before["members"] == [] and before["admins"] == [],
            "first-admin target or organization already has membership; reconcile without elevation")
    graphql_data(google.request("data", "POST", SERVICE + ":executeGraphql", body=payload["request"]))
    after = read_scope(google, variables)
    org = after["organizationMember"]
    require(isinstance(org, dict) and org.get("uid") == identity["uid"] and org.get("active") is True
            and after["admins"] == [{"uid": identity["uid"]}] and len(after["members"]) == 1,
            "first-admin membership readback differs")
    member = after["members"][0]
    require(isinstance(member, dict) and member.get("uid") == identity["uid"] and member.get("active") is True
            and member.get("role") == "admin" and member.get("canViewSensitive") is False
            and same_uuid(member.get("collectionId"), variables["collectionId"]), "first-admin scope or permissions differ")
    return {"version": "first-admin-applied/v1", "artifact_sha256": expected_sha256,
            "membership_sha256": hashlib.sha256(canonical(after)).hexdigest(),
            "membership_verified": True, "sensitive_access": False, "release_accepted": False}
