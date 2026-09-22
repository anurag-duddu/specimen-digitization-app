"""Synthetic first-scope artifacts, protected dispatch, and uncertain outcomes."""
import copy
import json

import pytest

import bootstrap_release as B
from test_bootstrap_release import FakeGoogle, artifact  # noqa: F401
from test_data_initialization import catalog_recipient


def execute(google, artifact):
    return B.bootstrap(google, artifact, artifact["artifact_sha256"], catalog_recipient())


@pytest.fixture
def first(artifact):
    identity = artifact["auth_record"]
    return B._prepared.prepare_first_scope(
        auth_record=identity, requested_email=identity["email"], requested_uid=identity["uid"],
        organization_id=artifact["request"]["variables"]["organizationId"],
        collection_id=artifact["request"]["variables"]["collectionId"],
        organization_name="Synthetic organization", collection_name="Synthetic collection",
    )


class FirstGoogle(FakeGoogle):
    def __init__(self, artifact, directory):
        super().__init__(artifact)
        self.path = directory / "packet.json"
        self.packet = {"source_sha": "a" * 40, "release_run_id": 123, "release_run_attempt": 2}
        self.before_change = {}
        self.after_change = {}
        v = artifact["request"]["variables"]
        self.mutation_result = {"data": {
            "organization_insert": {"id": v["organizationId"]},
            "collection_insert": {"organizationId": v["organizationId"], "id": v["collectionId"]},
            "organizationMember_insert": {"organizationId": v["organizationId"], "uid": v["uid"]},
            "collectionMember_insert": {"organizationId": v["organizationId"], "collectionId": v["collectionId"], "uid": v["uid"]},
        }}

    def request(self, api, method, resource, *, body):
        if not resource.endswith(":executeGraphqlRead"):
            return super().request(api, method, resource, body=body)
        self.calls.append((api, method, resource, copy.deepcopy(body)))
        v = self.artifact["request"]["variables"]
        collection = {"id": v["collectionId"], "organizationId": v["organizationId"],
                      "name": v["collectionName"], "parentId": None}
        data = {"organization": None, "collections": [], "matchingCollections": [],
                "organizationMembers": [], "members": []}
        if self.applied:
            data.update(organization={"id": v["organizationId"], "name": v["organizationName"]},
                        collections=[collection], matchingCollections=[collection],
                        organizationMembers=[{"uid": v["uid"], "active": True}],
                        members=[{"uid": v["uid"], "collectionId": v["collectionId"],
                                  "active": True, "role": "admin", "canViewSensitive": False}])
        data.update(self.after_change if self.applied else self.before_change)
        return {"data": data}


def test_first_scope_four_inserts_exact_receipt_and_durable_intent(first, tmp_path):
    google = FirstGoogle(first, tmp_path)
    receipt = execute(google, first)
    assert first["schema_version"] == "first-scope-owner-bootstrap/v1"
    assert receipt["version"] == "first-scope-owner-applied/v1"
    assert receipt["scope_verified"] and receipt["membership_verified"]
    assert receipt["sensitive_access"] is False and receipt["release_accepted"] is False
    assert receipt["artifact_sha256"] == first["artifact_sha256"]
    assert receipt["source_sha"] == "a" * 40 and receipt["run_id"] == 123 and receipt["run_attempt"] == 2
    assert "fixture-admin" not in json.dumps(receipt)
    intent = json.loads((tmp_path / "first-scope-owner.intent.json").read_bytes())
    assert intent["artifact_sha256"] == first["artifact_sha256"]
    assert len(google.calls) == 4
    with pytest.raises(ValueError):
        execute(google, first)
    assert sum(c[2].endswith(":executeGraphql") for c in google.calls) == 1


@pytest.mark.parametrize("field,value", [
    ("organization", {"id": "other"}), ("collections", [{"id": "other"}]),
    ("matchingCollections", [{"organizationId": "other"}]),
    ("organizationMembers", [{"uid": "old", "active": False}]),
    ("members", [{"uid": "old", "role": "admin", "active": False}]),
    ("members", None),
])
def test_partial_existing_foreign_or_incomplete_scope_stops_before_intent(first, tmp_path, field, value):
    google = FirstGoogle(first, tmp_path)
    google.before_change[field] = value
    with pytest.raises(ValueError):
        execute(google, first)
    assert not google.applied and len(google.calls) == 2
    assert not (tmp_path / "first-scope-owner.intent.json").exists()


@pytest.mark.parametrize("change", ["name", "parent", "uid", "active-number", "sensitive", "extra", "missing"])
def test_exact_all_four_row_readback_required(first, tmp_path, change):
    google = FirstGoogle(first, tmp_path)
    original = google.request
    def request(api, method, resource, *, body):
        result = original(api, method, resource, body=body)
        if google.applied and resource.endswith(":executeGraphqlRead"):
            data = result["data"]
            if change == "name":
                data["organization"]["name"] = "Other"
            elif change == "parent":
                data["collections"][0]["parentId"] = "other"
            elif change == "uid":
                data["organizationMembers"][0]["uid"] = "other"
            elif change == "active-number":
                data["organizationMembers"][0]["active"] = 1
            elif change == "sensitive":
                data["members"][0]["canViewSensitive"] = True
            elif change == "extra":
                data["members"].append(dict(data["members"][0], uid="other"))
            else:
                del data["matchingCollections"]
        return result
    google.request = request
    with pytest.raises(ValueError):
        execute(google, first)
    assert google.applied
    assert (tmp_path / "first-scope-owner.intent.json").exists()
    assert not (tmp_path / "first-scope-owner.verified.json").exists()


@pytest.mark.parametrize("result", [RuntimeError("unknown"), {"data": {}, "errors": [{"message": "partial"}]}, {"data": None}])
def test_unknown_mutation_retains_intent_and_new_transport_cannot_redispatch(first, tmp_path, result):
    google = FirstGoogle(first, tmp_path)
    google.mutation_result = result
    with pytest.raises((ValueError, RuntimeError)):
        execute(google, first)
    assert sum(c[2].endswith(":executeGraphql") for c in google.calls) == 1
    replacement = FirstGoogle(first, tmp_path)
    with pytest.raises(FileExistsError):
        execute(replacement, first)
    assert not replacement.applied


@pytest.mark.parametrize("field,value", [("localId", "other"), ("emailVerified", False), ("disabled", True), ("tenantId", "foreign")])
def test_fresh_owner_mismatch_stops_before_scope_read(first, tmp_path, field, value):
    google = FirstGoogle(first, tmp_path)
    google.identity[field] = value
    with pytest.raises(ValueError):
        execute(google, first)
    assert len(google.calls) == 1


@pytest.mark.parametrize("plane", ["runtime", "production", "data-initialization"])
def test_other_planes_cannot_create_scope(first, tmp_path, plane):
    google = FirstGoogle(first, tmp_path)
    google.plane = plane
    with pytest.raises(ValueError):
        execute(google, first)
    assert not google.calls


@pytest.mark.parametrize("change", ["version", "name", "uid", "query", "extra", "sensitive"])
def test_artifact_change_rejected_before_lookup(first, tmp_path, change):
    approved = first["artifact_sha256"]
    if change == "version":
        first["schema_version"] = "first-admin-bootstrap/v1"
    elif change == "query":
        first["request"]["query"] += " mutation { organization_deleteMany }"
    else:
        key = {"name": "organizationName", "uid": "uid", "extra": "unknown", "sensitive": "canViewSensitive"}[change]
        first["request"]["variables"][key] = True if change == "sensitive" else "changed"
    google = FirstGoogle(first, tmp_path)
    with pytest.raises(ValueError):
        B.bootstrap(google, first, approved)
    assert not google.calls


def test_bootstrap_phase_signed_receipt_keeps_exact_bootstrap_proof(first, tmp_path, monkeypatch):
    import deploy_data as D
    google = FirstGoogle(first, tmp_path)
    sequence = []
    monkeypatch.setattr(D, "verify_schema_receipt", lambda *a: sequence.append("verified-schema") or {
        "version": "data-schema-ready/v1", "schema_ready": True, "native_restore_verified": True})
    output = tmp_path / "data-ready.json"
    D.verify_or_bootstrap(google, {"version": "data-bootstrap/v1", "bootstrap": {
        "payload": first, "sha256": first["artifact_sha256"], "evidence_recipient": catalog_recipient()}}, output)
    assert sequence == ["verified-schema"]
    result = json.loads(output.read_bytes())
    assert result["bootstrap_receipt"]["artifact_sha256"] == first["artifact_sha256"]
    assert result["bootstrap_receipt"]["scope_verified"]
    assert result["data_ready"] is False


def test_scope_names_are_bounded_explicit_and_sensitive_is_fixed(artifact):
    identity = artifact["auth_record"]
    args = dict(auth_record=identity, requested_email=identity["email"], requested_uid=identity["uid"],
                organization_id=artifact["request"]["variables"]["organizationId"],
                collection_id=artifact["request"]["variables"]["collectionId"],
                organization_name="Synthetic organization", collection_name="Synthetic collection")
    for key in ("organization_name", "collection_name"):
        for bad in ("", " padded ", "bad\nname", "x" * 257, None):
            with pytest.raises(ValueError):
                B._prepared.prepare_first_scope(**{**args, key: bad})
    with pytest.raises(ValueError):
        B._prepared.prepare_first_scope(**args, can_view_sensitive=True)


def test_parent_sync_failure_prevents_mutation(first, tmp_path, monkeypatch):
    import os
    import stat
    original = os.fsync
    def fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("synthetic directory fsync failure")
        return original(fd)
    monkeypatch.setattr(os, "fsync", fsync)
    google = FirstGoogle(first, tmp_path)
    with pytest.raises(OSError):
        execute(google, first)
    assert not google.applied
    assert (tmp_path / "first-scope-owner.intent.json").exists()


def test_mutation_response_cannot_be_empty_even_if_readback_matches(first, tmp_path):
    google = FirstGoogle(first, tmp_path)
    google.mutation_result = {"data": {}}
    with pytest.raises(ValueError):
        execute(google, first)
    assert google.applied
    assert len(google.calls) == 3
    assert (tmp_path / "first-scope-owner.response.json").exists()


def test_legacy_receipt_shape_stays_unchanged(artifact, tmp_path, monkeypatch):
    import deploy_data as D
    google = FakeGoogle(artifact)
    google.packet = {"source_sha": "a" * 40, "release_run_id": 123, "release_run_attempt": 2}
    monkeypatch.setattr(D, "verify_schema_receipt", lambda *a: {
        "version": "data-schema-ready/v1", "schema_ready": True, "native_restore_verified": True})
    output = tmp_path / "data-ready.json"
    D.verify_or_bootstrap(google, {"version": "data-bootstrap/v1", "bootstrap": {
        "payload": artifact, "sha256": artifact["artifact_sha256"]}}, output)
    assert "bootstrap_receipt" not in json.loads(output.read_bytes())


def test_first_scope_prepare_cli_requires_explicit_mode_and_names(first, tmp_path, monkeypatch):
    import sys
    tmp_path.chmod(0o700)
    variables, identity = first["request"]["variables"], first["auth_record"]
    request = {"requested_uid": identity["uid"], "requested_email": identity["email"],
               "organization_id": variables["organizationId"], "collection_id": variables["collectionId"],
               "organization_name": variables["organizationName"], "collection_name": variables["collectionName"]}
    for name, value in (("request.json", request), ("auth.json", identity)):
        path = tmp_path / name
        path.write_text(json.dumps(value))
        path.chmod(0o600)
    arguments = ["bootstrap_admin.py", "--request", str(tmp_path / "request.json"),
                 "--auth-record", str(tmp_path / "auth.json"), "--output", str(tmp_path / "prepared.json")]
    monkeypatch.setattr(sys, "argv", arguments)
    with pytest.raises(SystemExit):
        B._prepared.main()
    assert not (tmp_path / "prepared.json").exists()
    monkeypatch.setattr(sys, "argv", arguments + ["--first-scope"])
    assert B._prepared.main() == 0
    assert json.loads((tmp_path / "prepared.json").read_bytes()) == first


def test_first_scope_is_not_an_end_user_connector():
    assert all("PrepareFirstScopeAndOwner" not in p.read_text() for p in (B.ROOT / "dataconnect/connector").glob("*.gql"))


def test_first_scope_waits_for_verified_schema_restore_and_cleanup(first, tmp_path, monkeypatch):
    import deploy_data as D
    def reject(*args):
        raise ValueError("synthetic signed readiness failure")
    monkeypatch.setattr(D, "verify_schema_receipt", reject)
    google = FirstGoogle(first, tmp_path)
    output = tmp_path / "data-ready.json"
    with pytest.raises(ValueError, match="signed readiness"):
        D.verify_or_bootstrap(google, {"version": "data-bootstrap/v1", "bootstrap": {
            "payload": first, "sha256": first["artifact_sha256"]}}, output)
    assert not google.calls and not output.exists()
    assert not (tmp_path / "first-scope-owner.intent.json").exists()


@pytest.mark.parametrize("field,key", [
    ("organization_insert", "id"), ("collection_insert", "organizationId"),
    ("collection_insert", "id"), ("organizationMember_insert", "uid"),
    ("collectionMember_insert", "collectionId"),
])
def test_wrong_inserted_key_stops_before_readback(first, tmp_path, field, key):
    google = FirstGoogle(first, tmp_path)
    google.mutation_result["data"][field][key] = "foreign"
    with pytest.raises(ValueError):
        execute(google, first)
    assert len(google.calls) == 3 and google.applied
    assert (tmp_path / "first-scope-owner.response.json").exists()
    assert not (tmp_path / "first-scope-owner.verified.json").exists()


# ------------------------------------------- the whole reviewed hierarchy ---


def reviewed_tree():
    return (B.ROOT / B._prepared.TREE_PATH).read_bytes()


def minted(entries):
    return [{"key": entry["key"], "id": f"00000000-0000-4000-8000-0000000{index:05x}",
             "name": entry["name"], "parent": entry["parent"]}
            for index, entry in enumerate(entries, start=1)]


@pytest.fixture
def tree(artifact):
    """The committed reviewed tree with synthetic identifiers; the release regenerates it."""
    identity = artifact["auth_record"]
    raw = reviewed_tree()
    return B._prepared.prepare_first_scope_hierarchy(
        auth_record=identity, requested_email=identity["email"], requested_uid=identity["uid"],
        organization_id=artifact["request"]["variables"]["organizationId"],
        organization_name="Synthetic organization", collections=minted(B._prepared.tree_entries(raw)),
        admin_collection_key="insects", tree=raw,
    )


class TreeGoogle(FakeGoogle):
    def __init__(self, artifact, directory):
        super().__init__(artifact)
        self.path = directory / "packet.json"
        self.packet = {"source_sha": "a" * 40, "release_run_id": 123, "release_run_attempt": 2}
        self.before_change = {}
        self.after_change = {}
        v = artifact["request"]["variables"]
        self.mutation_result = {"data": {
            "organization_insert": {"id": v["organizationId"]},
            "organizationMember_insert": {"organizationId": v["organizationId"], "uid": v["uid"]},
            "collectionMember_insert": {"organizationId": v["organizationId"],
                                        "collectionId": v["collectionId"], "uid": v["uid"]},
            **{f"c{index}": {"organizationId": v["organizationId"], "id": row["id"]}
               for index, row in enumerate(artifact["hierarchy"]["collections"])},
        }}

    def rows(self):
        v = self.artifact["request"]["variables"]
        entries = self.artifact["hierarchy"]["collections"]
        position = {entry["key"]: index for index, entry in enumerate(entries)}
        return [{"id": entry["id"], "organizationId": v["organizationId"], "name": entry["name"],
                 "parentId": None if entry["parent"] is None else entries[position[entry["parent"]]]["id"]}
                for entry in entries]

    def request(self, api, method, resource, *, body):
        if not resource.endswith(":executeGraphqlRead"):
            return super().request(api, method, resource, body=body)
        self.calls.append((api, method, resource, copy.deepcopy(body)))
        v = self.artifact["request"]["variables"]
        data = {"organization": None, "collections": [], "matchingCollections": [],
                "organizationMembers": [], "members": []}
        if self.applied:
            rows = self.rows()
            data.update(organization={"id": v["organizationId"], "name": v["organizationName"]},
                        collections=rows, matchingCollections=copy.deepcopy(rows),
                        organizationMembers=[{"uid": v["uid"], "active": True}],
                        members=[{"uid": v["uid"], "collectionId": v["collectionId"],
                                  "active": True, "role": "admin", "canViewSensitive": False}])
        data.update(self.after_change if self.applied else self.before_change)
        return {"data": data}


def test_hierarchy_creates_every_reviewed_collection_with_a_durable_intent(tree, tmp_path):
    google = TreeGoogle(tree, tmp_path)
    receipt = execute(google, tree)
    count = len(tree["hierarchy"]["collections"])
    assert tree["schema_version"] == "first-scope-hierarchy-bootstrap/v1"
    assert receipt["version"] == "first-scope-hierarchy-applied/v1"
    assert receipt["collections_verified"] == count == 18
    assert receipt["tree_sha256"] == tree["hierarchy"]["tree_sha256"]
    assert receipt["scope_verified"] and receipt["membership_verified"]
    assert receipt["sensitive_access"] is False and receipt["release_accepted"] is False
    assert receipt["artifact_sha256"] == tree["artifact_sha256"]
    assert receipt["source_sha"] == "a" * 40 and receipt["run_id"] == 123 and receipt["run_attempt"] == 2
    assert "fixture-admin" not in json.dumps(receipt)
    intent = json.loads((tmp_path / "first-scope-hierarchy.intent.json").read_bytes())
    assert intent["version"] == "first-scope-hierarchy-intent/v1"
    assert intent["artifact_sha256"] == tree["artifact_sha256"]
    # One identity lookup, one before read, one mutation, one readback. No retry.
    assert len(google.calls) == 4
    read = google.calls[1][3]["variables"]
    assert read["limit"] == count + 1 and len(read["ids"]) == count
    with pytest.raises(ValueError):
        execute(google, tree)
    assert sum(call[2].endswith(":executeGraphql") for call in google.calls) == 1


@pytest.mark.parametrize("field,value", [
    ("organization", {"id": "other"}), ("collections", [{"id": "other"}]),
    ("matchingCollections", [{"organizationId": "other"}]),
    ("organizationMembers", [{"uid": "old", "active": False}]),
    ("members", [{"uid": "old", "role": "admin", "active": False}]),
    ("members", None),
])
def test_hierarchy_partial_or_existing_scope_stops_before_intent(tree, tmp_path, field, value):
    google = TreeGoogle(tree, tmp_path)
    google.before_change[field] = value
    with pytest.raises(ValueError):
        execute(google, tree)
    assert not google.applied and len(google.calls) == 2
    assert not (tmp_path / "first-scope-hierarchy.intent.json").exists()


@pytest.mark.parametrize("field,key", [
    ("organization_insert", "id"), ("c0", "id"), ("c0", "organizationId"),
    ("c9", "id"), ("c17", "id"), ("organizationMember_insert", "uid"),
    ("collectionMember_insert", "collectionId"),
])
def test_hierarchy_wrong_inserted_key_stops_before_readback(tree, tmp_path, field, key):
    google = TreeGoogle(tree, tmp_path)
    google.mutation_result["data"][field][key] = "foreign"
    with pytest.raises(ValueError):
        execute(google, tree)
    assert len(google.calls) == 3 and google.applied
    assert (tmp_path / "first-scope-hierarchy.response.json").exists()
    assert not (tmp_path / "first-scope-hierarchy.verified.json").exists()


@pytest.mark.parametrize("field", ["c0", "c17", "organization_insert", "collectionMember_insert"])
def test_hierarchy_result_must_return_every_pinned_key(tree, tmp_path, field):
    google = TreeGoogle(tree, tmp_path)
    del google.mutation_result["data"][field]
    with pytest.raises(ValueError, match="incomplete"):
        execute(google, tree)
    assert google.applied and len(google.calls) == 3


@pytest.mark.parametrize("change", [
    "parent", "root", "missing", "extra", "duplicate", "name", "organization", "foreign"])
def test_hierarchy_readback_must_show_exactly_the_reviewed_tree(tree, tmp_path, change):
    google = TreeGoogle(tree, tmp_path)
    original = google.request

    def request(api, method, resource, *, body):
        result = original(api, method, resource, body=body)
        if google.applied and resource.endswith(":executeGraphqlRead"):
            data = result["data"]
            if change == "parent":
                data["collections"][1]["parentId"] = data["collections"][7]["id"]
            elif change == "root":
                data["collections"][1]["parentId"] = None
            elif change == "missing":
                data["collections"].pop()
            elif change == "extra":
                data["matchingCollections"].append(
                    dict(data["matchingCollections"][0], id="99999999-9999-4999-8999-999999999999"))
            elif change == "duplicate":
                data["collections"][3] = dict(data["collections"][2])
            elif change == "name":
                data["collections"][0]["name"] = "Other"
            elif change == "organization":
                data["collections"][5]["organizationId"] = "99999999-9999-4999-8999-999999999999"
            else:
                data["matchingCollections"][2]["id"] = "99999999-9999-4999-8999-999999999999"
        return result

    google.request = request
    with pytest.raises(ValueError):
        execute(google, tree)
    assert google.applied
    assert (tmp_path / "first-scope-hierarchy.readback.json").exists()
    assert not (tmp_path / "first-scope-hierarchy.verified.json").exists()


@pytest.mark.parametrize("change", ["version", "name", "uid", "query", "sensitive",
                                    "collection-id", "collection-name", "admin-key",
                                    "tree-path", "tree-digest", "extra-hierarchy-key"])
def test_hierarchy_artifact_change_rejected_before_lookup(tree, tmp_path, change):
    approved = tree["artifact_sha256"]
    if change == "version":
        tree["schema_version"] = "first-scope-owner-bootstrap/v1"
    elif change == "query":
        tree["request"]["query"] += " mutation { organization_deleteMany }"
    elif change == "collection-id":
        tree["hierarchy"]["collections"][3]["id"] = "99999999-9999-4999-8999-999999999999"
    elif change == "collection-name":
        tree["hierarchy"]["collections"][3]["name"] = "Renamed"
    elif change == "admin-key":
        tree["hierarchy"]["admin_collection_key"] = "botany"
    elif change == "tree-path":
        tree["hierarchy"]["tree_path"] = "infra/reference/other-tree.json"
    elif change == "tree-digest":
        tree["hierarchy"]["tree_sha256"] = "0" * 64
    elif change == "extra-hierarchy-key":
        tree["hierarchy"]["unreviewed"] = True
    else:
        key = {"name": "organizationName", "uid": "uid", "sensitive": "canViewSensitive"}[change]
        tree["request"]["variables"][key] = True if change == "sensitive" else "changed"
    google = TreeGoogle(tree, tmp_path)
    with pytest.raises(ValueError):
        B.bootstrap(google, tree, approved, catalog_recipient())
    assert not google.calls
    assert not list(tmp_path.iterdir())


def test_hierarchy_tree_edited_after_preparation_is_rejected(tree, tmp_path, monkeypatch):
    """The digest is recomputed from this source checkout, never trusted."""
    edited = json.loads(reviewed_tree())
    edited["collections"].append({"key": "meteorites", "name": "Meteorites", "parent": "geology"})
    checkout = tmp_path / "checkout"
    path = checkout / B._prepared.TREE_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(json.dumps(edited, indent=2).encode() + b"\n")
    monkeypatch.setattr(B, "ROOT", checkout)
    google = TreeGoogle(tree, tmp_path)
    with pytest.raises(ValueError, match="reviewed collection tree changed"):
        B.bootstrap(google, tree, tree["artifact_sha256"], catalog_recipient())
    assert not google.calls
    # The same checkout still accepts an artifact prepared from those exact bytes.
    reprepared = B._prepared.prepare_first_scope_hierarchy(
        auth_record=tree["auth_record"], requested_email=tree["auth_record"]["email"],
        requested_uid=tree["auth_record"]["uid"],
        organization_id=tree["request"]["variables"]["organizationId"],
        organization_name=tree["request"]["variables"]["organizationName"],
        collections=minted(edited["collections"]), admin_collection_key="insects",
        tree=path.read_bytes())
    assert B.reviewed_tree(reprepared["hierarchy"]) == path.read_bytes()


@pytest.mark.parametrize("result", [RuntimeError("unknown"),
                                    {"data": {}, "errors": [{"message": "partial"}]}, {"data": None}])
def test_hierarchy_unknown_mutation_retains_intent_and_cannot_be_redispatched(tree, tmp_path, result):
    google = TreeGoogle(tree, tmp_path)
    google.mutation_result = result
    with pytest.raises((ValueError, RuntimeError)):
        execute(google, tree)
    assert sum(call[2].endswith(":executeGraphql") for call in google.calls) == 1
    replacement = TreeGoogle(tree, tmp_path)
    with pytest.raises(FileExistsError):
        execute(replacement, tree)
    assert not replacement.applied


def test_hierarchy_requires_the_evidence_recipient_and_the_data_plane(tree, tmp_path):
    google = TreeGoogle(tree, tmp_path)
    with pytest.raises(ValueError):
        B.bootstrap(google, tree, tree["artifact_sha256"])
    assert not google.calls
    google.plane = "runtime"
    with pytest.raises(ValueError):
        execute(google, tree)
    assert not google.calls


def test_hierarchy_receipt_reaches_the_signed_data_readiness_file(tree, tmp_path, monkeypatch):
    import deploy_data as D
    google = TreeGoogle(tree, tmp_path)
    monkeypatch.setattr(D, "verify_schema_receipt", lambda *args: {
        "version": "data-schema-ready/v1", "schema_ready": True, "native_restore_verified": True})
    output = tmp_path / "data-ready.json"
    D.verify_or_bootstrap(google, {"version": "data-bootstrap/v1", "bootstrap": {
        "payload": tree, "sha256": tree["artifact_sha256"], "evidence_recipient": catalog_recipient()}}, output)
    result = json.loads(output.read_bytes())
    assert result["bootstrap_receipt"]["version"] == "first-scope-hierarchy-applied/v1"
    assert result["bootstrap_receipt"]["collections_verified"] == 18
    assert result["membership_bootstrapped"] is True
    assert result["data_ready"] is False and result["release_accepted"] is False


def test_hierarchy_plan_requires_the_reviewed_evidence_recipient(tree):
    import deploy_data as D
    plan = {"version": "data-bootstrap/v1", "source_sha": "a" * 40, "source_files": D.source_fingerprints(),
            "schema_receipt": {"run_id": 1, "run_attempt": 1, "source_sha": "b" * 40, "sha256": "c" * 64},
            "bootstrap": {"payload": tree, "sha256": tree["artifact_sha256"]}}
    with pytest.raises(ValueError):
        D.validate_plan(plan, {"source_sha": "a" * 40})
    plan["bootstrap"]["evidence_recipient"] = catalog_recipient()
    assert D.validate_plan(plan, {"source_sha": "a" * 40}) is plan


def test_hierarchy_is_not_an_end_user_connector():
    assert all("PrepareFirstScopeHierarchy" not in path.read_text()
               for path in (B.ROOT / "dataconnect/connector").glob("*.gql"))
