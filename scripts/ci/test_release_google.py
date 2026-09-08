"""No credentials or network: transport and surviving disposal authority."""
import copy
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

from test_release_context import valid_context

M = importlib.import_module("release_google")


def context():
    env = valid_context("data")
    env.update(GITHUB_RUN_ID="123", GITHUB_RUN_ATTEMPT="2",
               ACTIONS_ID_TOKEN_REQUEST_URL="https://test.actions.githubusercontent.com/token?api-version=2.0",
               ACTIONS_ID_TOKEN_REQUEST_TOKEN="synthetic-only")
    packet = {"source_sha": "a" * 40, "release_run_id": 123, "release_run_attempt": 2,
              "issued_at_unix": 1788890400, "expires_at_unix": 1788897600, "clone_expires_at_unix": 1788897600,
              "identity": {"project_number": "123456789", "pool_id": "reviewed-pool", "provider":
                  "projects/123456789/locations/global/workloadIdentityPools/reviewed-pool/providers/specimen-data-release"}}  # pragma: allowlist secret (synthetic resource ID)
    env["RELEASE_CLEANUP_PERMIT"] = json.dumps(packet)
    return env, packet


def credential(env, packet):
    return {"type": "external_account", "audience": "//iam.googleapis.com/" + packet["identity"]["provider"],
            "subject_token_type": "urn:ietf:params:oauth:token-type:jwt", "token_url": "https://sts.googleapis.com/v1/token",
            "service_account_impersonation_url": "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/" + env["RELEASE_SERVICE_ACCOUNT"] + ":generateAccessToken",
            "credential_source": {"url": env["ACTIONS_ID_TOKEN_REQUEST_URL"] + "&" + urlencode({"audience": packet["identity"]["provider"]}),
                                  "headers": {"Authorization": "Bearer " + env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]},
                                  "format": {"type": "json", "subject_token_field_name": "value"}}}


def test_bound_keyless_credential_can_only_exchange_this_jobs_oidc_token():
    env, packet = context()
    M.validate_credentials(credential(env, packet), packet, env)


@pytest.mark.parametrize("change", [
    lambda c: c.update(type="service_account"),
    lambda c: c.update(token_url="https://foreign.example/token"),
    lambda c: c.update(service_account_impersonation_url="https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/foreign:generateAccessToken"),
    lambda c: c["credential_source"].update(url="https://foreign.example/token"),
    lambda c: c["credential_source"].update(executable={"command": "anything"}),
    lambda c: c["credential_source"]["headers"].update(Authorization="Bearer different"),
])
def test_changed_credentials_rejected_before_loading_or_refresh(change):
    env, packet = context()
    value = credential(env, packet)
    change(value)
    with pytest.raises(ValueError):
        M.validate_credentials(value, packet, env)


def test_cleanup_original_admission_survives_new_authorized_sha_but_never_wrong_run():
    env, packet = context()
    env["RELEASE_AUTHORIZED_SHA"] = "b" * 40
    assert M.cleanup_packet(Path("missing"), env) == packet
    for field, value in (("GITHUB_RUN_ATTEMPT", "3"), ("GITHUB_SHA", "b" * 40),
                         ("GITHUB_EVENT_NAME", "workflow_dispatch"), ("DEPLOYMENT_ENVIRONMENT", "production")):
        with pytest.raises(ValueError):
            M.cleanup_packet(Path("missing"), {**env, field: value})


def transport():
    _, packet = context()
    google = M.Google.__new__(M.Google)
    google.packet, google.path, google.plane = packet, Path("missing"), "data"
    google.session = SimpleNamespace(request=lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: {"ok": True}))
    return google


def test_transport_accepts_only_observed_project_alias_and_fixed_origin(monkeypatch):
    google = transport()
    for project in ("specimen-digitization", "123456789"):
        assert google.request("run", "GET", f"projects/{project}/locations/us-east4/services/specimen-api") == {"ok": True}
    for resource in ("projects/987654321/instances/x", "projects/specimen-digitization/../other",
                     "projects/specimen-digitization/instances/x?redirect=foreign", "https://foreign.example"):
        with pytest.raises(ValueError):
            google.request("run", "GET", resource)
    with pytest.raises(ValueError):
        google.request("foreign", "GET", "projects/specimen-digitization")
    monkeypatch.setattr(M, "admit", lambda *a, **kw: (_ for _ in ()).throw(ValueError("expired authority")))
    with pytest.raises(ValueError, match="expired"):
        google.request("sql", "POST", "projects/specimen-digitization/instances", body={})


def test_only_fixed_owned_clone_delete_survives_expired_general_admission(monkeypatch):
    env, _ = context()
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    google = transport()
    calls = []
    google.session.delete = lambda url, **kw: (calls.append((url, kw)) or SimpleNamespace(status_code=200, json=lambda: {"name": "delete-operation"}))
    monkeypatch.setattr(M, "admit", lambda *a, **kw: pytest.fail("disposal cannot request new paid authority"))
    assert google.cleanup_clone()["name"] == "delete-operation"
    assert calls[0][0].endswith("/instances/specimen-digitization-restore-20260908-r1")
    assert calls[0][1]["allow_redirects"] is False


@pytest.mark.parametrize("project", ["specimen-digitization", "123456789"])
def test_native_operation_same_project_alias_is_usable(project):
    google = transport()
    operation = {"name": f"projects/{project}/locations/us-east4/operations/abc", "done": True, "response": {"ok": True}}
    assert google.wait("run", operation) == {"ok": True}
    operation["name"] = "projects/foreign/locations/us-east4/operations/abc"
    with pytest.raises(ValueError):
        google.wait("run", operation)
