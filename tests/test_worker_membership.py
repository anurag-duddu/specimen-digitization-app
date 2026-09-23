"""The worker membership bootstrap document (docs/execution/golive/WORKER_MEMBERSHIP.md)."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bootstrap_admin", ROOT / "scripts/data/bootstrap_admin.py")
admin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin)

# The exact document for two collections: each row carries its own collection variable.
TWO_COLLECTIONS = """mutation PrepareWorkerMembership(
  $organizationId: UUID!, $uid: String!,
  $c0: UUID!,
  $c1: UUID!
) @transaction {
  organizationMember_insert(data: {organizationId: $organizationId, uid: $uid, active: true})
  query @redact {
    priorMemberships: collectionMembers(where: {organizationId: {eq: $organizationId}, uid: {eq: $uid}}, limit: 1)
      @check(expr: "this.size() == 0", message: "Membership already exists") { uid }
  }
  m0: collectionMember_insert(data: {organizationId: $organizationId, collectionId: $c0,
    uid: $uid, active: true, role: "operator", canViewSensitive: false})
  m1: collectionMember_insert(data: {organizationId: $organizationId, collectionId: $c1,
    uid: $uid, active: true, role: "operator", canViewSensitive: false})
}
"""


def prepared(tree: bytes, organization_id: str | None = None) -> dict:
    """An approved hierarchy artifact with synthetic identifiers, as the owner prepares it."""
    identity = {"uid": "synthetic-admin", "email": "admin@example.invalid", "emailVerified": True, "disabled": False}
    return admin.prepare_first_scope_hierarchy(
        auth_record=identity, requested_email=identity["email"], requested_uid=identity["uid"],
        organization_id=organization_id or str(uuid4()), organization_name="Synthetic organization",
        collections=[{**entry, "id": str(uuid4())} for entry in admin.tree_entries(tree)],
        admin_collection_key="insects", tree=tree,
    )


@pytest.fixture
def hierarchy():
    return prepared((ROOT / admin.TREE_PATH).read_bytes())


def request(approved, **change):
    """The request for the approved artifact, with any argument replaced."""
    values = {"artifact": approved, "approved_sha256": approved["artifact_sha256"],
              "uid": "synthetic-worker", "collection_keys": ["insects"]}
    return admin.worker_membership_request(**{**values, **change})


def collection_id(artifact, key):
    return next(entry["id"] for entry in artifact["hierarchy"]["collections"] if entry["key"] == key)


def test_the_document_is_exact_and_each_row_has_its_own_collection():
    assert admin.worker_membership_mutation(2) == TWO_COLLECTIONS
    one = admin.worker_membership_mutation(1)
    assert one.count("collectionMember_insert(") == 1 and "$c1" not in one
    assert admin.worker_membership_mutation(3).count('role: "operator", canViewSensitive: false') == 3


@pytest.mark.parametrize("count", [0, 65, True, 1.0, "1", None])
def test_the_document_needs_a_bounded_explicit_count(count):
    with pytest.raises(ValueError):
        admin.worker_membership_mutation(count)


def test_the_organization_and_collection_come_from_the_approved_hierarchy(hierarchy):
    assert admin.WORKER_COLLECTION_KEYS == ("insects",)
    assert request(hierarchy) == {
        "mode": "worker-membership-bootstrap/v1",
        "query": admin.worker_membership_mutation(1),
        "variables": {
            "organizationId": hierarchy["request"]["variables"]["organizationId"],
            "uid": "synthetic-worker",
            "c0": collection_id(hierarchy, "insects"),
        },
    }


@pytest.mark.parametrize(
    "keys",
    [["insects", "other"], ["mammals"], ["Insects"], ["insects", "insects"], [], [None], "insects"],
    ids=["insects-and-other", "mammals", "case", "repeated", "empty", "none", "string"],
)
def test_only_the_committed_allow_list_is_accepted(hierarchy, keys):
    with pytest.raises(ValueError):
        request(hierarchy, collection_keys=keys)


@pytest.mark.parametrize(
    "uid",
    ["", " worker", "worker\n", "w" * 129, None, "synthetic-admin"],
    ids=["empty", "padded", "control", "long", "none", "administrator"],
)
def test_the_uid_is_explicit_and_never_the_administrator(hierarchy, uid):
    with pytest.raises(ValueError):
        request(hierarchy, uid=uid)


@pytest.mark.parametrize("change", [
    "approval", "approval-case", "approval-missing", "reprepared", "version", "organization",
    "collection-id", "collection-key", "admin-key", "query", "tree-path", "tree-digest", "extra", "shape",
])
def test_a_changed_or_unapproved_hierarchy_artifact_is_refused(hierarchy, change):
    approved, artifact = hierarchy["artifact_sha256"], copy.deepcopy(hierarchy)
    insects = next(entry for entry in artifact["hierarchy"]["collections"] if entry["key"] == "insects")
    if change == "approval":
        approved = approved[::-1]
    elif change == "approval-case":
        approved = approved.upper()
    elif change == "approval-missing":
        approved = None
    elif change == "reprepared":
        # A self-consistent artifact for another organization, under the original approval.
        artifact = prepared((ROOT / admin.TREE_PATH).read_bytes())
    elif change == "version":
        artifact["schema_version"] = "first-scope-owner-bootstrap/v1"
    elif change == "organization":
        artifact["request"]["variables"]["organizationId"] = str(uuid4())
    elif change == "collection-id":
        insects["id"] = str(uuid4())
    elif change == "collection-key":
        insects["key"] = "insects-renamed"
    elif change == "admin-key":
        artifact["hierarchy"]["admin_collection_key"] = "botany"
    elif change == "query":
        artifact["request"]["query"] += " mutation { organization_deleteMany }"
    elif change == "tree-path":
        artifact["hierarchy"]["tree_path"] = "infra/reference/other-tree.json"
    elif change == "tree-digest":
        artifact["hierarchy"]["tree_sha256"] = "0" * 64
    elif change == "extra":
        artifact["hierarchy"]["unreviewed"] = True
    else:
        artifact = [artifact]
    with pytest.raises(ValueError):
        request(hierarchy, artifact=artifact, approved_sha256=approved)


def test_a_tree_edited_after_preparation_is_refused(hierarchy, tmp_path, monkeypatch):
    """The tree is read from this checkout's fixed path and must still hash to the bound digest."""
    edited = json.loads((ROOT / admin.TREE_PATH).read_bytes())
    edited["collections"].append({"key": "meteorites", "name": "Meteorites", "parent": "geology"})
    path = tmp_path / admin.TREE_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(json.dumps(edited, indent=2).encode() + b"\n")
    monkeypatch.setattr(admin, "ROOT", tmp_path)
    with pytest.raises(ValueError):
        request(hierarchy)
    # The same checkout accepts an artifact prepared from those exact bytes.
    reprepared = prepared(path.read_bytes())
    assert request(reprepared)["variables"]["c0"] == collection_id(reprepared, "insects")


def test_the_worker_membership_is_not_published_as_a_runtime_operation():
    for path in (ROOT / "dataconnect/connector").glob("*.gql"):
        assert "PrepareWorkerMembership" not in path.read_text()
