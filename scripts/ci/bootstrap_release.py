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
from release_context import PROJECT

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


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def validate_prepared(payload, expected_sha256):
    """Regenerate, do not trust the query or caller-supplied apply requirements."""
    digest(expected_sha256, "approved first-admin artifact")
    try:
        identity, variables = payload["auth_record"], payload["request"]["variables"]
        require(variables["canViewSensitive"] is False, "initial sensitive access is not authorized")
        version = payload["schema_version"]
        require(version in {"first-admin-bootstrap/v1", "first-scope-owner-bootstrap/v1"}, "unknown bootstrap mode")
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


def read_first_scope(google, variables):
    data = graphql_data(google.request("data", "POST", SERVICE + ":executeGraphqlRead", body={
        "query": READ_FIRST_SCOPE,
        "variables": {key: variables[key] for key in ("organizationId", "collectionId")},
    }))
    require(set(data) == {"organization", "collections", "matchingCollections", "organizationMembers", "members"}
            and all(isinstance(data[key], list) and len(data[key]) <= 2 for key in
                    ("collections", "matchingCollections", "organizationMembers", "members")),
            "first-scope observation incomplete")
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


def apply_first_scope(google, payload, expected_sha256):
    variables = payload["request"]["variables"]
    before = read_first_scope(google, variables)
    require(before == {"organization": None, "collections": [], "matchingCollections": [],
                       "organizationMembers": [], "members": []},
            "first-scope target is existing or partial; reconcile without adoption")
    provenance = {"source_sha": google.packet["source_sha"], "run_id": google.packet["release_run_id"],
                  "run_attempt": google.packet["release_run_attempt"], "artifact_sha256": expected_sha256}
    directory = google.path.parent
    retain_first_scope(directory, "first-scope-owner.intent.json", {
        "version": "first-scope-owner-intent/v1", **provenance,
        "request_sha256": hashlib.sha256(canonical(payload["request"])).hexdigest(),
        "before_sha256": hashlib.sha256(canonical(before)).hexdigest(),
    })
    # Intent is durable before dispatch. Any exception, partial response or failed
    # readback leaves it consumed. A new runner cannot adopt committed rows: the
    # same pinned organization's insert still conflicts. No retry or new IDs.
    response = google.request("data", "POST", SERVICE + ":executeGraphql", body=payload["request"])
    retain_first_scope(directory, "first-scope-owner.response.json", response)
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
    after = read_first_scope(google, variables)
    retain_first_scope(directory, "first-scope-owner.readback.json", after)
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
    retain_first_scope(directory, "first-scope-owner.verified.json", receipt)
    return receipt


def bootstrap(google, prepared_payload, expected_sha256):
    """Recheck identity, execute exact transaction once, then verify membership.

    The caller supplies the already-admitted data-plane Google transport only
    after verified restore/schema/index readiness. That transport rechecks source,
    identity, expiry and the cumulative budget immediately before each request.
    An uncertain mutation or readback propagates; retries require reconciliation.
    The transaction's organization lock and insert-only predicates prevent replay.
    """
    require(google.plane == "data", "first-admin maintenance requires the data release identity")
    payload = validate_prepared(prepared_payload, expected_sha256)
    identity, variables = payload["auth_record"], payload["request"]["variables"]
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
    if payload["schema_version"] == "first-scope-owner-bootstrap/v1":
        return apply_first_scope(google, payload, expected_sha256)
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
