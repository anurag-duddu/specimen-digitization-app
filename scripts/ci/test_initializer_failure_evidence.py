"""Exact refused-call evidence, confidential retention and no-resend boundaries."""
import base64
import json
from types import SimpleNamespace

import pytest

import release_bootstrap as bootstrap
from release_catalog_envelope import decrypt_catalog
from release_diagnostics import DiagnosticError, HTTPFailure, public_failure
import release_initializer_evidence as evidence
from test_data_first_initialization import Cloud, INTENT, I, D, NOW, jobs  # noqa: F401
from test_initialization_catalog_privacy import catalog_keys  # noqa: F401
from test_release_google import transport

CANARY = b'{"error":{"code":403,"message":"private-denial-canary","details":[{"reason":"IAM_PERMISSION_DENIED"}]}}'


def unwrap(path, key, packet, monkeypatch):
    provenance = {"repository": evidence.REPOSITORY, "source_sha": packet["source_sha"],
                  "run_id": packet["release_run_id"], "run_attempt": packet["release_run_attempt"]}
    # Generated test keys model local coordinator verification. Preserve the
    # runner context during retention and restore it immediately after decrypt.
    with monkeypatch.context() as local:
        local.delenv("GITHUB_ACTIONS", raising=False)
        return json.loads(decrypt_catalog(json.loads(path.read_bytes()), key[1],
            public_key_sha256=key[0]["public_key_sha256"], provenance=provenance))


@pytest.mark.parametrize("fault,expected_stage", [
    ("insert", "google.sql-initializer-user-create"),
    ("poll", "google.sql-initializer-operation-poll"),
])
def test_initializer_distinguishes_refused_insert_from_refused_operation_poll_without_resending(
        jobs, monkeypatch, catalog_keys, fault, expected_stage):
    monkeypatch.setattr(bootstrap, "recipient", lambda: catalog_keys[0])
    cloud = Cloud("data-initialization", 1)
    original = cloud.request

    def request(api, method, resource, **kwargs):
        if method == "POST" and fault == "insert":
            cloud.calls.append((method, "users"))
            cloud.initializer_failure_evidence(method, resource, 403, CANARY)
            raise HTTPFailure(403)
        result = original(api, method, resource, **kwargs)
        if method == "POST":
            return {**result, "status": "PENDING"}
        return result

    cloud.request = request
    if fault == "poll":
        def wait(client, operation, maximum_seconds):
            resource = f"projects/{I.PROJECT}/operations/{operation['name']}"
            client.initializer_failure_evidence("GET", resource, 403, CANARY)
            raise HTTPFailure(403)
        monkeypatch.setattr(D, "wait_sql", wait)
    with pytest.raises(DiagnosticError) as error:
        jobs.initialize(cloud)
    assert public_failure(error.value) == f"Data release blocked [stage={expected_stage}; http_status=403]."
    assert "private-denial-canary" not in str(error.value)
    assert [call for call in cloud.calls if call[0] != "GET"] == [("POST", "users")]
    assert not (jobs.directory / "data-initializer.json").exists() and jobs.native == []
    target = jobs.directory / "initialize" / evidence.TARGET
    assert CANARY not in target.read_bytes() and target.stat().st_mode & 0o777 == 0o600
    value = unwrap(target, catalog_keys, cloud.packet, monkeypatch)
    assert base64.b64decode(value["observations"][0]["response_b64"]) == CANARY
    journal = next(item for item in value["journals"] if item["name"].startswith("initializer-create-effect-"))
    actual = json.loads(base64.b64decode(journal["body_b64"]))
    assert actual["outcome"] == ("unknown" if fault == "insert" else "observed")
    assert value["retry_authorized"] is False and value["release_accepted"] is False
    assert not hasattr(cloud, "initializer_failure_evidence")


def test_success_has_no_failure_artifact_or_hook(jobs, catalog_keys, monkeypatch):
    monkeypatch.setattr(bootstrap, "recipient", lambda: catalog_keys[0])
    cloud = Cloud("data-initialization", 1)
    jobs.initialize(cloud)
    assert not (jobs.directory / "initialize" / evidence.TARGET).exists()
    assert not hasattr(cloud, "initializer_failure_evidence")


def test_retention_failure_keeps_original_refusal_and_unknown_intent(jobs, catalog_keys, monkeypatch):
    monkeypatch.setattr(bootstrap, "recipient", lambda: catalog_keys[0])
    monkeypatch.setattr(evidence, "encrypt_catalog", lambda *a, **kw: (_ for _ in ()).throw(ValueError("private-canary")))
    cloud = Cloud("data-initialization", 1)
    original = cloud.request
    def request(api, method, resource, **kwargs):
        if method == "POST":
            cloud.calls.append((method, "users"))
            raise HTTPFailure(403)
        return original(api, method, resource, **kwargs)
    cloud.request = request
    with pytest.raises(DiagnosticError) as error:
        jobs.initialize(cloud)
    assert error.value.http_status == 403 and "private-canary" not in str(error.value)
    effect = jobs.directory / "initialize" / f"initializer-create-effect-{I.SOURCE}.json"
    assert json.loads(effect.read_bytes())["outcome"] == "unknown"
    assert [call for call in cloud.calls if call[0] != "GET"] == [("POST", "users")]


@pytest.mark.parametrize("large", [False, True])
def test_actual_transport_captures_failed_response_only_inside_initializer_context(
        tmp_path, monkeypatch, catalog_keys, large):
    monkeypatch.setattr(bootstrap, "recipient", lambda: catalog_keys[0])
    client = transport()
    client.plane = "data-initialization"
    raw = b"x" * (evidence.LIMIT + 1) if large else CANARY
    client.session.request = lambda *a, **kw: SimpleNamespace(status_code=403, content=raw)
    resource = f"projects/{I.PROJECT}/operations/owned-operation"
    with pytest.raises(HTTPFailure):
        with evidence.preserve_failure(client, tmp_path):
            client.request("sql", "GET", resource)
    value = unwrap(tmp_path / evidence.TARGET, catalog_keys, client.packet, monkeypatch)
    actual = value["observations"][0]
    assert actual["response_bytes"] == len(raw) and actual["response_retained"] is (not large)
    assert actual["response_b64"] == (None if large else base64.b64encode(raw).decode())
    assert not hasattr(client, "initializer_failure_evidence")


def test_invalid_recipient_stops_before_any_initializer_effect(jobs, monkeypatch):
    monkeypatch.setattr(bootstrap, "recipient", lambda: (_ for _ in ()).throw(ValueError("invalid recipient")))
    cloud = Cloud("data-initialization", 1)
    with pytest.raises(ValueError, match="invalid recipient"):
        jobs.initialize(cloud)
    assert [call for call in cloud.calls if call[0] != "GET"] == [] and jobs.native == []
