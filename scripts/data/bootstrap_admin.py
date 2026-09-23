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


ROOT = Path(__file__).resolve().parents[2]

# The reviewed public collection tree. It carries display names and stable keys
# only; the canonical UUIDs stay in the owner's private request and artifact.
TREE_PATH = "infra/reference/fieldmuseum-collection-tree.json"


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


def _bounded_name(value: Any) -> str:
    """The existing scope-name rule: nonempty, trimmed, printable, 256 UTF-8 bytes."""
    if (not isinstance(value, str) or not value or value != value.strip()
            or len(value.encode("utf-8")) > 256
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        raise ValueError("Scope names must be explicit bounded text")
    return value


def tree_entries(tree: Any) -> list[dict[str, Any]]:
    """Parse the reviewed public tree's exact bytes; the digest binds those bytes.

    The reviewed tree is public and lives in the repository. Only its ordered
    (key, name, parent) triples are authoritative here; no identifier is read
    from it, so a review of this file never exposes a production UUID.
    """
    if not isinstance(tree, bytes):
        raise ValueError("The reviewed collection tree must be supplied as its exact bytes")
    document = json.loads(tree.decode("utf-8"))
    if (not isinstance(document, dict) or document.get("schema_version") != "collection-tree/v1"
            or not isinstance(document.get("collections"), list)):
        raise ValueError("Unknown reviewed collection tree document")
    return document["collections"]


def hierarchy_mutation(parents: list[int | None]) -> str:
    """Render the one @transaction deterministically from the reviewed tree shape.

    Variable declarations follow only from the count, and each row's `parentId`
    from its parent's earlier index, so the same reviewed tree always yields the
    same bytes and a reviewer can regenerate them without the private values.
    """
    count = len(parents)
    declared = [
        "  $organizationId: UUID!, $organizationName: String!, $uid: String!, $canViewSensitive: Boolean!,",
        "  $collectionId: UUID!,",
    ]
    declared += [f"  $c{index}Id: UUID!, $c{index}Name: String!," for index in range(count)]
    declared[-1] = declared[-1].removesuffix(",")
    identifiers = ", ".join(f"$c{index}Id" for index in range(count))
    rows = [
        f"  c{index}: collection_insert(data: {{organizationId: $organizationId, id: $c{index}Id,\n"
        f"    name: $c{index}Name, parentId: {'null' if parent is None else '$c%dId' % parent}}})"
        for index, parent in enumerate(parents)
    ]
    return (
        "mutation PrepareFirstScopeHierarchy(\n" + "\n".join(declared) + "\n) @transaction {\n"
        "  organization_insert(data: {id: $organizationId, name: $organizationName})\n"
        "  query @redact {\n"
        f"    matchingCollections: collections(where: {{id: {{in: [{identifiers}]}}}}, limit: 1)\n"
        '      @check(expr: "this.size() == 0", message: "Collection identifier already exists") { id }\n'
        "  }\n" + "\n".join(rows) + "\n"
        "  organizationMember_insert(data: {organizationId: $organizationId, uid: $uid, active: true})\n"
        "  collectionMember_insert(data: {organizationId: $organizationId, collectionId: $collectionId,\n"
        '    uid: $uid, active: true, role: "admin", canViewSensitive: $canViewSensitive})\n'
        "}\n"
    )


# The worker's own account (docs/execution/golive/WORKER_MEMBERSHIP.md). The organization
# member and every collection member commit or roll back together. A replay, or a uid that is
# already a member, stops on the organization member's primary key; an unknown collection stops
# on the composite foreign key. Role and sensitivity are literals, never variables.
WORKER_MEMBERSHIP_MODE = "worker-membership-bootstrap/v1"
WORKER_COLLECTIONS_MAX = 64


def worker_membership_mutation(count: int) -> str:
    """Render the one @transaction for `count` processing collections, deterministically."""
    if type(count) is not int or not 1 <= count <= WORKER_COLLECTIONS_MAX:
        raise ValueError("A bounded, explicit number of processing collections is required")
    declared = ["  $organizationId: UUID!, $uid: String!,"]
    declared += [f"  $c{index}: UUID!," for index in range(count)]
    declared[-1] = declared[-1].removesuffix(",")
    rows = [
        f"  m{index}: collectionMember_insert(data: {{organizationId: $organizationId, collectionId: $c{index},\n"
        '    uid: $uid, active: true, role: "operator", canViewSensitive: false})'
        for index in range(count)
    ]
    return (
        "mutation PrepareWorkerMembership(\n" + "\n".join(declared) + "\n) @transaction {\n"
        "  organizationMember_insert(data: {organizationId: $organizationId, uid: $uid, active: true})\n"
        + "\n".join(rows) + "\n}\n"
    )


def worker_membership_request(
    *, organization_id: str, uid: str, collection_ids: list[str]
) -> dict[str, Any]:
    """The reviewed worker-membership request; the release job supplies the private values."""
    # The first-admin rule for an explicit Firebase UID.
    if (
        not isinstance(uid, str)
        or not 1 <= len(uid) <= 128
        or uid != uid.strip()
        or any(ord(character) < 32 for character in uid)
    ):
        raise ValueError("An explicit Firebase UID is required")
    if (
        not isinstance(collection_ids, list)
        or not collection_ids
        or len(collection_ids) > WORKER_COLLECTIONS_MAX
    ):
        raise ValueError("Processing collections must be an explicit, bounded list")
    identifiers = [_identifier(value) for value in collection_ids]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Processing collections must be distinct")
    variables = {"organizationId": _identifier(organization_id), "uid": uid}
    variables.update({f"c{index}": value for index, value in enumerate(identifiers)})
    return {
        "mode": WORKER_MEMBERSHIP_MODE,
        "query": worker_membership_mutation(len(identifiers)),
        "variables": variables,
    }


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
        _bounded_name(name)
    artifact = prepare_bootstrap(**identity_scope, can_view_sensitive=False)
    artifact["schema_version"] = "first-scope-owner-bootstrap/v1"
    artifact["request"]["query"] = FIRST_SCOPE_MUTATION
    artifact["request"]["variables"].update(organizationName=organization_name, collectionName=collection_name)
    del artifact["artifact_sha256"]
    artifact["artifact_sha256"] = hashlib.sha256(_canonical(artifact)).hexdigest()
    return artifact


def prepare_first_scope_hierarchy(
    *,
    auth_record: dict[str, Any],
    requested_email: str,
    requested_uid: str,
    organization_id: str,
    organization_name: str,
    collections: list[dict[str, Any]],
    admin_collection_key: str,
    tree: Any,
    can_view_sensitive: bool = False,
) -> dict[str, Any]:
    """Prepare the owner's whole reviewed collection tree as one transaction.

    `collections` is the private ordered list of {key, id, name, parent} carrying
    the owner's already minted canonical UUIDs. `tree` is the exact bytes of the
    reviewed public tree; the private list must repeat its (key, name, parent)
    triples in the same order. Nothing is generated here and no ID is chosen.
    """
    if can_view_sensitive is not False:
        raise ValueError("Initial sensitive access is not authorized")
    _bounded_name(organization_name)
    reviewed = tree_entries(tree)
    if not isinstance(collections, list) or not 1 <= len(collections) <= 64:
        raise ValueError("The hierarchy must carry between one and 64 explicit collections")
    if len(reviewed) != len(collections):
        raise ValueError("The private collections do not match the reviewed tree")
    keys: list[str] = []
    identifiers: set[str] = set()
    siblings: set[tuple[Any, str]] = set()
    parents: list[int | None] = []
    for entry, public in zip(collections, reviewed):
        if not isinstance(entry, dict) or set(entry) != {"key", "id", "name", "parent"}:
            raise ValueError("Each collection must carry exactly key, id, name and parent")
        if not isinstance(public, dict) or set(public) != {"key", "name", "parent"}:
            raise ValueError("Unknown reviewed collection tree document")
        if (entry["key"], entry["name"], entry["parent"]) != (public["key"], public["name"], public["parent"]):
            raise ValueError("The private collections do not match the reviewed tree")
        key = entry["key"]
        if not isinstance(key, str) or not key or key in keys:
            raise ValueError("Collection keys must be unique explicit text")
        _bounded_name(entry["name"])
        identifier = _identifier(entry["id"])
        if identifier in identifiers:
            raise ValueError("Collection identifiers must be unique canonical UUIDs")
        identifiers.add(identifier)
        parent = entry["parent"]
        if parent is None:
            parents.append(None)
        elif parent in keys:
            parents.append(keys.index(parent))
        else:
            raise ValueError("Every parent must appear earlier in the reviewed tree")
        if (parent, entry["name"]) in siblings:
            raise ValueError("One parent cannot hold two collections with the same name")
        siblings.add((parent, entry["name"]))
        keys.append(key)
    if admin_collection_key not in keys:
        raise ValueError("The administrator's collection must be one of the reviewed keys")
    administrator = collections[keys.index(admin_collection_key)]
    # The administrator's collection keeps the existing `collectionId` variable,
    # so every existing reader of the membership rows continues to work unchanged.
    artifact = prepare_bootstrap(
        auth_record=auth_record, requested_email=requested_email, requested_uid=requested_uid,
        organization_id=organization_id, collection_id=administrator["id"], can_view_sensitive=False,
    )
    artifact["schema_version"] = "first-scope-hierarchy-bootstrap/v1"
    artifact["request"]["query"] = hierarchy_mutation(parents)
    variables = artifact["request"]["variables"]
    variables["organizationName"] = organization_name
    for index, entry in enumerate(collections):
        variables[f"c{index}Id"] = entry["id"]
        variables[f"c{index}Name"] = entry["name"]
    artifact["hierarchy"] = {
        "tree_path": TREE_PATH,
        "tree_sha256": hashlib.sha256(tree).hexdigest(),
        "collections": [{"key": entry["key"], "id": entry["id"], "name": entry["name"],
                         "parent": entry["parent"]} for entry in collections],
        "admin_collection_key": admin_collection_key,
    }
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--first-scope", action="store_true", help="Explicit empty organization/collection and owner mode")
    mode.add_argument("--hierarchy", action="store_true", help="Explicit empty organization and whole reviewed collection tree")
    parser.add_argument("--tree", type=Path, default=ROOT / TREE_PATH,
                        help="Reviewed public collection tree; defaults to the committed repository file")
    args = parser.parse_args()
    try:
        request = json.loads(read_private(args.request))
        auth_record = json.loads(read_private(args.auth_record))
        if args.hierarchy:
            artifact = prepare_first_scope_hierarchy(
                auth_record=auth_record, tree=Path(args.tree).read_bytes(), **request)
        else:
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
