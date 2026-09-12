"""Prepare a private first-admin transaction; never authenticate or apply it.

Inputs are separately obtained Firebase Admin user-record fields, not an ID token.
Preparation does not prove export freshness. Before any approved application, a
maintenance operator must re-read Auth, compare these fields, and review the
artifact hash. This operation must never be published in the runtime connector.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any
from uuid import UUID

from specimen_digitization.application.pilot_manifest import read_private


# The first UPDATE takes a row lock shared by all bootstrap attempts in this
# organization. The following query runs after that lock, preventing two distinct
# UIDs from both passing the first-admin predicate. No names or roles are updated.
BOOTSTRAP_MUTATION = """mutation PrepareFirstAdministrator(
  $organizationId: UUID!, $collectionId: UUID!, $uid: String!,
  $canViewSensitive: Boolean!
) @transaction {
  bootstrapLock: organization_update(key: {id: $organizationId}, data: {id: $organizationId})
    @check(expr: "this != null", message: "Bootstrap organization missing")
  query @redact {
    collection(key: {organizationId: $organizationId, id: $collectionId})
      @check(expr: "this != null", message: "Bootstrap collection missing") { id }
    priorAdmins: collectionMembers(where: {organizationId: {eq: $organizationId}, role: {eq: "admin"}}, limit: 1)
      @check(expr: "this.size() == 0", message: "Administrator already exists") { uid }
    organizationMember(key: {organizationId: $organizationId, uid: $uid})
      @check(expr: "this == null", message: "Membership already exists") { uid }
    priorMemberships: collectionMembers(where: {organizationId: {eq: $organizationId}, uid: {eq: $uid}}, limit: 1)
      @check(expr: "this.size() == 0", message: "Membership already exists") { uid }
  }
  organizationMember_insert(data: {organizationId: $organizationId, uid: $uid, active: true})
  collectionMember_insert(data: {organizationId: $organizationId, collectionId: $collectionId,
    uid: $uid, active: true, role: "admin", canViewSensitive: $canViewSensitive})
}
"""

# The first insert contends on the pinned organization primary key. A competing
# transaction or replay cannot get past it. All four inserts commit or roll back
# together; none can adopt, rename, reactivate or elevate an existing row.
FIRST_SCOPE_MUTATION = """mutation PrepareFirstScopeAndOwner(
  $organizationId: UUID!, $collectionId: UUID!, $uid: String!,
  $organizationName: String!, $collectionName: String!, $canViewSensitive: Boolean!
) @transaction {
  organization_insert(data: {id: $organizationId, name: $organizationName})
  query @redact {
    matchingCollections: collections(where: {id: {eq: $collectionId}}, limit: 1)
      @check(expr: "this.size() == 0", message: "Collection identifier already exists") { id }
  }
  collection_insert(data: {organizationId: $organizationId, id: $collectionId,
    name: $collectionName, parentId: null})
  organizationMember_insert(data: {organizationId: $organizationId, uid: $uid, active: true})
  collectionMember_insert(data: {organizationId: $organizationId, collectionId: $collectionId,
    uid: $uid, active: true, role: "admin", canViewSensitive: $canViewSensitive})
}
"""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Scope must be an explicit canonical UUID")
    return value


def prepare_bootstrap(
    *,
    auth_record: dict[str, Any],
    requested_email: str,
    requested_uid: str,
    organization_id: str,
    collection_id: str,
    can_view_sensitive: bool = False,
) -> dict[str, Any]:
    """Validate explicit identity and return an unapplied, reviewable artifact.

    auth_record uses Firebase Admin JSON fields uid/email/emailVerified/disabled.
    No normalization or fallback identity matching is permitted. Only the four
    required fields enter the artifact; exports may contain private extra fields.
    """
    if (
        not isinstance(requested_email, str)
        or requested_email != requested_email.strip()
        or requested_email.count("@") != 1
        or not all(requested_email.split("@"))
        or any(character.isspace() or ord(character) < 32 for character in requested_email)
    ):
        raise ValueError("An explicit email is required")
    if (
        not isinstance(requested_uid, str)
        or not 1 <= len(requested_uid) <= 128
        or requested_uid != requested_uid.strip()
        or any(ord(character) < 32 for character in requested_uid)
    ):
        raise ValueError("An explicit Firebase UID is required")
    if not isinstance(auth_record, dict) or (
        auth_record.get("uid") != requested_uid
        or auth_record.get("email") != requested_email
        or auth_record.get("emailVerified") is not True
        or auth_record.get("disabled") is not False
    ):
        raise ValueError("Auth record must match the requested verified, enabled account exactly")
    if type(can_view_sensitive) is not bool:
        raise ValueError("Sensitive access must be an explicit boolean")
    identity = {
        "uid": requested_uid,
        "email": requested_email,
        "emailVerified": True,
        "disabled": False,
    }
    artifact = {
        "schema_version": "first-admin-bootstrap/v1",
        "state": "prepared_not_applied",
        "project_id": "specimen-digitization",
        "auth_record": identity,
        "auth_record_sha256": hashlib.sha256(_canonical(identity)).hexdigest(),
        "apply_requirements": [
            "explicit maintenance authorization and artifact hash approval",
            "fresh Firebase Admin account read in the pinned project matches auth_record",
            "reviewed database backup and restore evidence",
            "separately approved maintenance identity; never runtime connector or Hosting identity",
        ],
        "request": {
            "query": BOOTSTRAP_MUTATION,
            "variables": {
                "organizationId": _identifier(organization_id),
                "collectionId": _identifier(collection_id),
                "uid": requested_uid,
                "canViewSensitive": can_view_sensitive,
            },
        },
    }
    artifact["artifact_sha256"] = hashlib.sha256(_canonical(artifact)).hexdigest()
    return artifact


def prepare_first_scope(
    *, organization_name: str, collection_name: str, can_view_sensitive: bool = False, **identity_scope: Any,
) -> dict[str, Any]:
    """Prepare only the explicitly selected empty-scope mode; never mint IDs."""
    if can_view_sensitive is not False:
        raise ValueError("Initial sensitive access is not authorized")
    for name in (organization_name, collection_name):
        if (not isinstance(name, str) or not name or name != name.strip()
                or len(name.encode("utf-8")) > 256
                or any(ord(character) < 32 or ord(character) == 127 for character in name)):
            raise ValueError("Scope names must be explicit bounded text")
    artifact = prepare_bootstrap(**identity_scope, can_view_sensitive=False)
    artifact["schema_version"] = "first-scope-owner-bootstrap/v1"
    artifact["request"]["query"] = FIRST_SCOPE_MUTATION
    artifact["request"]["variables"].update(organizationName=organization_name, collectionName=collection_name)
    del artifact["artifact_sha256"]
    artifact["artifact_sha256"] = hashlib.sha256(_canonical(artifact)).hexdigest()
    return artifact


def write_private_artifact(path: Path, artifact: dict[str, Any]) -> None:
    """Exclusively create mode0600 outside Git, beneath a private owned directory."""
    parent = path.parent.resolve(strict=True)
    if any((ancestor / ".git").exists() for ancestor in (parent, *parent.parents)):
        raise ValueError("Private bootstrap artifact must be outside Git")
    info = parent.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("Private artifact directory must be owned by you with mode0700")
    descriptor = os.open(parent / path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(_canonical(artifact) + b"\n")
        output.flush()
        os.fsync(output.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True, help="Private JSON with explicit requested fields")
    parser.add_argument("--auth-record", type=Path, required=True, help="Private exported Admin user record JSON")
    parser.add_argument("--output", type=Path, required=True, help="New private file outside Git; parent mode0700")
    parser.add_argument("--first-scope", action="store_true", help="Explicit empty organization/collection and owner mode")
    args = parser.parse_args()
    try:
        request = json.loads(read_private(args.request))
        auth_record = json.loads(read_private(args.auth_record))
        prepare = prepare_first_scope if args.first_scope else prepare_bootstrap
        artifact = prepare(auth_record=auth_record, **request)
        write_private_artifact(args.output, artifact)
    except (ValueError, TypeError, OSError):
        # Do not echo private identity, record, path, or GraphQL variables.
        parser.exit(2, "Bootstrap preparation refused: check explicit identity, scope, and private output requirements.\n")
    print("Prepared private first-admin artifact; no cloud calls or writes performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
