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


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def validate_prepared(payload, expected_sha256):
    """Regenerate, do not trust the query or caller-supplied apply requirements."""
    digest(expected_sha256, "approved first-admin artifact")
    try:
        identity, variables = payload["auth_record"], payload["request"]["variables"]
        require(variables["canViewSensitive"] is False, "initial sensitive access is not authorized")
        expected = _prepared.prepare_bootstrap(
            auth_record=identity, requested_email=identity["email"], requested_uid=identity["uid"],
            organization_id=variables["organizationId"], collection_id=variables["collectionId"],
            can_view_sensitive=False,
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
