"""Private bootstrap evidence survives ordinary failed jobs without plaintext publication."""
import copy
import hashlib
import json
from functools import lru_cache

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import bootstrap_release as B
import deploy_data as D
from release_catalog_envelope import decrypt_catalog
from test_bootstrap_release import artifact  # noqa: F401
from test_first_scope_bootstrap import FirstGoogle, first, tree  # noqa: F401


@lru_cache
def keys():
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return {"public_key_pem": public.decode(), "public_key_sha256": hashlib.sha256(public).hexdigest()}, private


def recipient():
    return copy.deepcopy(keys()[0])


def readiness_plan(first):
    return {"version": "data-bootstrap/v1", "source_sha": "a" * 40, "source_files": D.source_fingerprints(),
            "schema_receipt": {"run_id": 123, "run_attempt": 2, "source_sha": "b" * 40, "sha256": "c" * 64},
            "bootstrap": {"payload": first, "sha256": first["artifact_sha256"], "evidence_recipient": recipient()}}


@pytest.mark.parametrize("phase", ["data-bootstrap/v1", "data-apply/v1"])
def test_missing_first_scope_recipient_rejected_by_plan_before_effects(first, phase):
    from test_data_release import plan, recovery_packet
    value = readiness_plan(first) if phase == "data-bootstrap/v1" else plan()
    value["bootstrap"] = {"payload": first, "sha256": first["artifact_sha256"]}
    with pytest.raises(ValueError):
        D.validate_plan(value, recovery_packet(), now=1788890400)


@pytest.mark.parametrize("change", ["absent", "digest", "private", "extra", "weak"])
def test_bad_recipient_stops_before_auth_or_scope(first, tmp_path, change):
    value = recipient()
    if change == "absent":
        value = None
    elif change == "digest":
        value["public_key_sha256"] = "0" * 64
    elif change == "private":
        value["public_key_pem"] = keys()[1].decode()
        value["public_key_sha256"] = hashlib.sha256(keys()[1]).hexdigest()
    elif change == "extra":
        value["destination"] = "unreviewed"
    else:
        weak = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        value = {"public_key_pem": weak.decode(), "public_key_sha256": hashlib.sha256(weak).hexdigest()}
    google = FirstGoogle(first, tmp_path)
    with pytest.raises(ValueError):
        B.bootstrap(google, first, first["artifact_sha256"], value)
    assert not google.calls and not list(tmp_path.iterdir())


@pytest.mark.parametrize("outcome", ["success", "partial", "bad-readback", "rejected-readback", "unknown"])
def test_bootstrap_encrypts_exact_evidence_after_success_or_failure(first, tmp_path, monkeypatch, outcome):
    google = FirstGoogle(first, tmp_path)
    if outcome == "partial":
        google.mutation_result = {"data": {}, "errors": [{"message": "private fixture-admin response"}]}
    elif outcome == "bad-readback":
        google.after_change = {"organization": {"id": first["request"]["variables"]["organizationId"], "name": "private wrong name"}}
    elif outcome == "unknown":
        google.mutation_result = TimeoutError("private unknown response")
    elif outcome == "rejected-readback":
        original = google.request
        def request(api, method, resource, *, body):
            response = original(api, method, resource, body=body)
            if google.applied and resource.endswith(":executeGraphqlRead"):
                return {"errors": [{"message": "private fixture-admin response"}]}
            return response
        google.request = request
    if outcome == "success":
        B.bootstrap(google, first, first["artifact_sha256"], recipient())
    else:
        with pytest.raises((ValueError, TimeoutError)):
            B.bootstrap(google, first, first["artifact_sha256"], recipient())
    raw_files = sorted(p for p in tmp_path.glob("first-scope-owner.*.json") if ".encrypted." not in p.name)
    assert len(raw_files) == {"success": 4, "partial": 2, "bad-readback": 3, "rejected-readback": 3, "unknown": 1}[outcome]
    for raw in raw_files:
        encrypted = raw.with_suffix(".encrypted.json")
        assert encrypted.exists()
        envelope = json.loads(encrypted.read_bytes())
        arguments = {"public_key_sha256": recipient()["public_key_sha256"],
                     "provenance": {"repository": "anurag-duddu/specimen-digitization-app", "source_sha": "a" * 40,
                                    "run_id": 123, "run_attempt": 2}}
        # Synthetic private keys represent the local coordinator, never a runner.
        # Prove the runner denial before testing that separate local readback.
        with monkeypatch.context() as context:
            context.setenv("GITHUB_ACTIONS", "true")
            with pytest.raises(ValueError):
                decrypt_catalog(envelope, keys()[1], **arguments)
            context.delenv("GITHUB_ACTIONS")
            assert decrypt_catalog(envelope, keys()[1], **arguments) == raw.read_bytes()
        for private in ("fixture-admin", "admin@example.invalid", "Synthetic organization", "private wrong name"):
            assert private.encode() not in encrypted.read_bytes()
        assert encrypted.stat().st_mode & 0o777 == 0o600
    assert sum(c[2].endswith(":executeGraphql") for c in google.calls) == 1


def test_encryption_failure_consumes_intent_without_dispatch(first, tmp_path, monkeypatch):
    import release_catalog_envelope as E
    def fail(*args, **kwargs):
        raise ValueError("synthetic encryption failure")
    monkeypatch.setattr(E, "encrypt_catalog", fail)
    google = FirstGoogle(first, tmp_path)
    with pytest.raises(ValueError, match="encryption"):
        B.bootstrap(google, first, first["artifact_sha256"], recipient())
    assert not google.applied and (tmp_path / "first-scope-owner.intent.json").exists()
    with pytest.raises(FileExistsError):
        B.bootstrap(FirstGoogle(first, tmp_path), first, first["artifact_sha256"], recipient())


def test_reviewed_recipient_survives_plan_and_deploy_call_chain(first, tmp_path, monkeypatch):
    plan = readiness_plan(first)
    assert D.validate_plan(plan, {"source_sha": "a" * 40}) == plan
    monkeypatch.setattr(D, "verify_schema_receipt", lambda *args: {"version": "data-schema-ready/v1"})
    google = FirstGoogle(first, tmp_path)
    D.verify_or_bootstrap(google, plan, tmp_path / "data-ready.json")
    assert (tmp_path / "first-scope-owner.verified.encrypted.json").exists()


# ------------------------------------------- the whole reviewed hierarchy ---


@pytest.mark.parametrize("outcome", ["success", "partial", "bad-readback", "unknown"])
def test_hierarchy_evidence_is_encrypted_under_its_own_names(tree, tmp_path, monkeypatch, outcome):
    from test_first_scope_bootstrap import TreeGoogle
    google = TreeGoogle(tree, tmp_path)
    if outcome == "partial":
        google.mutation_result = {"data": {}, "errors": [{"message": "private fixture-admin response"}]}
    elif outcome == "bad-readback":
        google.after_change = {"organization": {
            "id": tree["request"]["variables"]["organizationId"], "name": "private wrong name"}}
    elif outcome == "unknown":
        google.mutation_result = TimeoutError("private unknown response")
    if outcome == "success":
        B.bootstrap(google, tree, tree["artifact_sha256"], recipient())
    else:
        with pytest.raises((ValueError, TimeoutError)):
            B.bootstrap(google, tree, tree["artifact_sha256"], recipient())
    raw_files = sorted(p for p in tmp_path.glob("first-scope-hierarchy.*.json") if ".encrypted." not in p.name)
    assert [p.name.split(".")[1] for p in raw_files] == {
        "success": ["intent", "readback", "response", "verified"],
        "partial": ["intent", "response"],
        "bad-readback": ["intent", "readback", "response"],
        "unknown": ["intent"],
    }[outcome]
    for raw in raw_files:
        encrypted = raw.with_suffix(".encrypted.json")
        assert encrypted.exists()
        envelope = json.loads(encrypted.read_bytes())
        arguments = {"public_key_sha256": recipient()["public_key_sha256"],
                     "provenance": {"repository": "anurag-duddu/specimen-digitization-app",
                                    "source_sha": "a" * 40, "run_id": 123, "run_attempt": 2}}
        with monkeypatch.context() as context:
            context.setenv("GITHUB_ACTIONS", "true")
            with pytest.raises(ValueError):
                decrypt_catalog(envelope, keys()[1], **arguments)
            context.delenv("GITHUB_ACTIONS")
            assert decrypt_catalog(envelope, keys()[1], **arguments) == raw.read_bytes()
        for private in ("fixture-admin", "admin@example.invalid", "Synthetic organization",
                        "private wrong name", "Invertebrate Zoology"):
            assert private.encode() not in encrypted.read_bytes()
        assert encrypted.stat().st_mode & 0o777 == 0o600
    assert sum(call[2].endswith(":executeGraphql") for call in google.calls) == 1


def test_hierarchy_encryption_failure_consumes_intent_without_dispatch(tree, tmp_path, monkeypatch):
    from test_first_scope_bootstrap import TreeGoogle
    import release_catalog_envelope as E

    def fail(*args, **kwargs):
        raise ValueError("synthetic encryption failure")

    monkeypatch.setattr(E, "encrypt_catalog", fail)
    google = TreeGoogle(tree, tmp_path)
    with pytest.raises(ValueError, match="encryption"):
        B.bootstrap(google, tree, tree["artifact_sha256"], recipient())
    assert not google.applied and (tmp_path / "first-scope-hierarchy.intent.json").exists()
    with pytest.raises(FileExistsError):
        B.bootstrap(TreeGoogle(tree, tmp_path), tree, tree["artifact_sha256"], recipient())


@pytest.mark.parametrize("change", ["absent", "digest", "private", "extra", "weak"])
def test_hierarchy_bad_recipient_stops_before_auth_or_scope(tree, tmp_path, change):
    from test_first_scope_bootstrap import TreeGoogle
    value = recipient()
    if change == "absent":
        value = None
    elif change == "digest":
        value["public_key_sha256"] = "0" * 64
    elif change == "private":
        value["public_key_pem"] = keys()[1].decode()
        value["public_key_sha256"] = hashlib.sha256(keys()[1]).hexdigest()
    elif change == "extra":
        value["destination"] = "unreviewed"
    else:
        weak = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        value = {"public_key_pem": weak.decode(), "public_key_sha256": hashlib.sha256(weak).hexdigest()}
    google = TreeGoogle(tree, tmp_path)
    with pytest.raises(ValueError):
        B.bootstrap(google, tree, tree["artifact_sha256"], value)
    assert not google.calls and not list(tmp_path.iterdir())


def test_hierarchy_reviewed_recipient_survives_plan_and_deploy_call_chain(tree, tmp_path, monkeypatch):
    from test_first_scope_bootstrap import TreeGoogle
    plan = {**readiness_plan(tree), "bootstrap": {
        "payload": tree, "sha256": tree["artifact_sha256"], "evidence_recipient": recipient()}}
    assert D.validate_plan(plan, {"source_sha": "a" * 40}) == plan
    monkeypatch.setattr(D, "verify_schema_receipt", lambda *args: {"version": "data-schema-ready/v1"})
    D.verify_or_bootstrap(TreeGoogle(tree, tmp_path), plan, tmp_path / "data-ready.json")
    assert (tmp_path / "first-scope-hierarchy.verified.encrypted.json").exists()
