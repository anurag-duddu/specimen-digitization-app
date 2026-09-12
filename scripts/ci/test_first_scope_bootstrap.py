"""Synthetic first-scope artifacts, protected dispatch, and uncertain outcomes."""
import copy
import json

import pytest

import bootstrap_release as B
from test_bootstrap_release import FakeGoogle, artifact, execute  # noqa: F401


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
        "payload": first, "sha256": first["artifact_sha256"]}}, output)
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
