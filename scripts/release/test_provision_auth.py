"""Auth release contracts with fake HTTP/CLI only; no live credentials or network."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
import yaml

SPEC = importlib.util.spec_from_file_location("provision_auth", Path(__file__).with_name("provision_auth.py"))
auth = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(auth)

CONFIG = {"signIn": {"email": {"enabled": True}}, "authorizedDomains": sorted(auth.DOMAINS)}
PROVIDER = {"name": f"projects/{auth.NUMBER}/defaultSupportedIdpConfigs/google.com", "enabled": True,
            "clientId": "123-example.apps.googleusercontent.com"}
APPS = {"apps": [{"appId": auth.WEB_APP, "state": "ACTIVE"}]}


class FakeApi:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def call(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        assert self.answers, "unexpected API call"
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return copy.deepcopy(answer)


def environment(tmp_path):
    credentials = tmp_path / "gha-creds.json"
    credentials.write_text("{}")
    return {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": auth.REPOSITORY,
            "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": "ab" * 20, "GITHUB_EVENT_NAME": "push",
            "GITHUB_WORKFLOW_REF": f"{auth.REPOSITORY}/.github/workflows/data-release.yml@refs/heads/main",
            "AUTH_RELEASE_ENVIRONMENT": "data-production", "GOOGLE_GHA_CREDS_PATH": str(credentials)}


@pytest.mark.parametrize("event", ["push", "workflow_dispatch"])
def test_main_release_guard_accepts_the_data_workflow(tmp_path, event):
    env = environment(tmp_path)
    env["GITHUB_EVENT_NAME"] = event
    auth.require_release(env, env["GITHUB_SHA"])


@pytest.mark.parametrize("key,value", [
    ("GITHUB_ACTIONS", "false"), ("GITHUB_REPOSITORY", "example/other"),
    ("GITHUB_REF", "refs/heads/feature"), ("GITHUB_WORKFLOW_REF", "other-workflow"),
    ("AUTH_RELEASE_ENVIRONMENT", "production"), ("GITHUB_EVENT_NAME", "pull_request"),
    ("GITHUB_SHA", "not-a-sha"), ("GITHUB_SHA", "cd" * 20),
    ("GOOGLE_GHA_CREDS_PATH", ""), ("GOOGLE_GHA_CREDS_PATH", "/missing/gha.json"),
    ("FIREBASE_TOKEN", "forbidden-token"), ("FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099"),
])
def test_release_guard_rejects_other_contexts(tmp_path, key, value):
    env = environment(tmp_path)
    env[key] = value
    with pytest.raises(auth.Failure):
        auth.require_release(env, "ab" * 20)


def test_main_stops_before_authentication_or_network_outside_workflow(monkeypatch, capsys):
    monkeypatch.setattr(auth.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="ab" * 20))
    monkeypatch.setattr(auth.os, "environ", {})
    monkeypatch.setattr(auth, "provision", lambda *a: pytest.fail("no cloud calls outside workflow"))
    assert auth.main() == 1
    assert "only in the main Data release" in capsys.readouterr().err


def test_existing_enabled_google_is_an_idempotent_read_only_noop(monkeypatch, capsys):
    api = FakeApi(CONFIG, PROVIDER)
    monkeypatch.setattr(auth, "run_cli", lambda *a: pytest.fail("must retain existing client"))
    auth.provision(api, "unused", auth.AUTH_CONFIG)
    assert [call[0] for call in api.calls] == ["GET", "GET"]
    assert api.calls[0] == ("GET", auth.CONFIG_URL, {"fields": auth.PRESERVED_FIELDS})
    assert api.calls[1] == ("GET", auth.GOOGLE_URL, {"fields": auth.GOOGLE_FIELDS, "missing": True})
    assert "already enabled" in capsys.readouterr().out


def test_missing_google_uses_only_cli_then_verifies_email_domains_and_provider(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(auth, "run_cli", lambda *a: calls.append(a))
    api = FakeApi(CONFIG, None, APPS, CONFIG, PROVIDER)
    auth.provision(api, "/fake/firebase", auth.AUTH_CONFIG)
    assert calls == [("/fake/firebase", auth.AUTH_CONFIG)]
    assert [call[1] for call in api.calls] == [auth.CONFIG_URL, auth.GOOGLE_URL, auth.APPS_URL,
                                             auth.CONFIG_URL, auth.GOOGLE_URL]
    assert all(call[0] == "GET" for call in api.calls)
    assert "email and domains preserved" in capsys.readouterr().out


def test_disabled_provider_updates_only_enabled_and_retains_its_client(monkeypatch):
    monkeypatch.setattr(auth, "run_cli", lambda *a: pytest.fail("must not replace existing client"))
    api = FakeApi(CONFIG, {**PROVIDER, "enabled": False}, PROVIDER, CONFIG, PROVIDER)
    auth.provision(api, "unused", auth.AUTH_CONFIG)
    assert [call for call in api.calls if call[0] != "GET"] == [
        ("PATCH", auth.GOOGLE_URL, {"fields": auth.GOOGLE_FIELDS, "body": {"enabled": True},
                                   "update_mask": "enabled"})]


@pytest.mark.parametrize("provider", [
    {}, {**PROVIDER, "name": "projects/other/defaultSupportedIdpConfigs/google.com"},
    {**PROVIDER, "clientId": ""}, {**PROVIDER, "clientId": "untrusted.example"},
])
def test_invalid_existing_google_client_is_never_replaced(monkeypatch, provider):
    monkeypatch.setattr(auth, "run_cli", lambda *a: pytest.fail("must not replace existing client"))
    api = FakeApi(CONFIG, provider)
    with pytest.raises(auth.Failure, match="invalid identity/client"):
        auth.provision(api, "unused", auth.AUTH_CONFIG)
    assert all(call[0] == "GET" for call in api.calls)


@pytest.mark.parametrize("config", [
    {}, {**CONFIG, "signIn": {}}, {**CONFIG, "signIn": {"email": None}},
    {**CONFIG, "signIn": {"email": {"enabled": False}}},
    {**CONFIG, "signIn": {"email": {"enabled": True, "passwordRequired": True}}},
    {**CONFIG, "authorizedDomains": []}, {**CONFIG, "authorizedDomains": "example.com"},
    {**CONFIG, "authorizedDomains": [1]},
])
def test_email_and_domain_preflight_fails_before_any_mutation(monkeypatch, config):
    monkeypatch.setattr(auth, "run_cli", lambda *a: pytest.fail("no provisioning"))
    api = FakeApi(config)
    with pytest.raises(auth.Failure, match="nothing changed"):
        auth.provision(api, "unused", auth.AUTH_CONFIG)
    assert len(api.calls) == 1


@pytest.mark.parametrize("apps", [
    {}, {"apps": []}, {"apps": APPS["apps"] * 2}, {**APPS, "nextPageToken": "more"},
    {"apps": [{"appId": "another-app", "state": "ACTIVE"}]},
    {"apps": [{"appId": auth.WEB_APP, "state": "DELETED"}]},
])
def test_missing_provider_refuses_ambiguous_or_different_app(monkeypatch, apps):
    monkeypatch.setattr(auth, "run_cli", lambda *a: pytest.fail("no provisioning"))
    with pytest.raises(auth.Failure, match="single existing production web app"):
        auth.provision(FakeApi(CONFIG, None, apps), "unused", auth.AUTH_CONFIG)


@pytest.mark.parametrize("after", [
    {**CONFIG, "authorizedDomains": [*CONFIG["authorizedDomains"], "added.example"]},
    {**CONFIG, "signIn": {"email": {"enabled": False}}},
    auth.Failure("unavailable"),
])
def test_post_provision_email_or_domain_change_stops_without_repair(monkeypatch, after):
    monkeypatch.setattr(auth, "run_cli", lambda *a: None)
    api = FakeApi(CONFIG, None, APPS, after)
    with pytest.raises(auth.Failure, match="stop and inspect") as caught:
        auth.provision(api, "unused", auth.AUTH_CONFIG)
    assert "nothing changed" not in str(caught.value)
    assert all(call[0] == "GET" for call in api.calls)


def test_provider_must_be_ready_after_provision(monkeypatch):
    monkeypatch.setattr(auth, "run_cli", lambda *a: None)
    with pytest.raises(auth.Failure, match="keep the web flag off"):
        auth.provision(FakeApi(CONFIG, None, APPS, CONFIG, {**PROVIDER, "enabled": False}),
                       "unused", auth.AUTH_CONFIG)


@pytest.mark.parametrize("extra", ["email", "anonymous", "saml"])
def test_extra_provider_config_is_rejected_before_calls(extra):
    config = copy.deepcopy(auth.AUTH_CONFIG)
    config["auth"]["providers"][extra] = {"enabled": True}
    api = FakeApi()
    with pytest.raises(auth.Failure, match="only the approved Google"):
        auth.provision(api, "unused", config)
    assert api.calls == []


@pytest.mark.parametrize("failure", [None, "version", "exit", "timeout"])
def test_cli_is_pinned_auth_only_and_logs_no_raw_output(monkeypatch, capsys, failure):
    calls, directories = [], []

    def run(argv, **kwargs):
        calls.append(argv)
        directories.append(Path(kwargs["cwd"]))
        assert kwargs["capture_output"] and kwargs["text"] and not kwargs["check"]
        if argv[-1] == "--version":
            return SimpleNamespace(returncode=0, stdout="wrong" if failure == "version" else "15.8.0\n")
        path = Path(argv[argv.index("--config") + 1])
        assert json.loads(path.read_text()) == auth.AUTH_CONFIG
        assert path.parent == Path(kwargs["cwd"])
        assert kwargs["timeout"] == 300
        # Simulate the CLI's private debug file; cleanup must remove it even on failure.
        (path.parent / "firebase-debug.log").write_text("PRIVATE-RESPONSE")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(argv, 300, output="PRIVATE-RESPONSE")
        return SimpleNamespace(returncode=1 if failure == "exit" else 0,
                               stdout="PRIVATE-RESPONSE", stderr="PRIVATE-RESPONSE")

    monkeypatch.setattr(auth.subprocess, "run", run)
    if failure:
        with pytest.raises(auth.Failure) as caught:
            auth.run_cli("/pinned/firebase", auth.AUTH_CONFIG)
        assert "PRIVATE-RESPONSE" not in str(caught.value)
    else:
        auth.run_cli("/pinned/firebase", auth.AUTH_CONFIG)
    assert calls[0] == ["/pinned/firebase", "--version"]
    assert len(calls) == (1 if failure == "version" else 2)
    if len(calls) == 2:
        assert calls[1][:7] == ["/pinned/firebase", "deploy", "--only", "auth", "--project",
                               auth.PROJECT, "--config"]
        assert calls[1][-1] == "--non-interactive"
    assert all(not path.exists() for path in directories)
    assert "PRIVATE-RESPONSE" not in str(capsys.readouterr())


PROVISION_URL = "https://firebase.googleapis.com/v1alpha/firebase:provisionFirebaseApp"
OPERATION_URL = "https://firebase.googleapis.com/v1beta1/operations/provision-example_123"
PRIVATE_CANARIES = ["secret-token-canary", "secret-client-canary", "private@example.test",
                    "https://private.example.test/credential", "private-operation-id"]


def debug_response(kind, payload, *, method="POST", url=PROVISION_URL, prefix="file"):
    # Exact CLI 15.8.0 logger.js and apiv2.js formats; no live log contents.
    prefixes = {"file": "[debug] [2026-10-17T21:00:00.000Z] ",
                "console": "[2026-10-17T21:00:00.000Z] ", "plain": ""}
    return f"{prefixes[prefix]}<<< [apiv2][{kind}] {method} {url} {payload}"


def private_api_error(**overrides):
    error = {"code": 403, "status": "PERMISSION_DENIED", "message": " ".join(PRIVATE_CANARIES),
             "clientSecret": PRIVATE_CANARIES[1], "details": [
                 {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "IAM_PERMISSION_DENIED",
                  "domain": PRIVATE_CANARIES[2], "metadata": {"permission": "firebaseauth.configs.update",
                  "accessToken": PRIVATE_CANARIES[0], "resource": PRIVATE_CANARIES[3]}},
                 {"@type": "type.googleapis.com/google.rpc.Help", "links": [
                     {"description": PRIVATE_CANARIES[1], "url": PRIVATE_CANARIES[3]}]},
             ]}
    return {"error": {**error, **overrides}}


@pytest.mark.parametrize("prefix", ["file", "console", "plain"])
def test_real_cli_response_formats_keep_only_enumerated_error_fields(tmp_path, prefix):
    text = "\n".join([
        "[debug] Authorization: Bearer " + PRIVATE_CANARIES[0],
        debug_response("status", "403", prefix=prefix),
        debug_response("body", json.dumps(private_api_error()), prefix=prefix),
        f"Error: Failed to provision Firebase app: Request to {PROVISION_URL} had HTTP Error: 403, "
        + " ".join(PRIVATE_CANARIES),
    ])
    (tmp_path / "firebase-debug.log").write_text(text)
    message = auth.cli_failure_diagnostic(SimpleNamespace(stdout="", stderr=""), tmp_path)
    assert message == ("CLI response diagnostic: stage=provider_provision http=403 api_code=403 "
                       "api_status=PERMISSION_DENIED reason=IAM_PERMISSION_DENIED "
                       "permission=firebaseauth.configs.update")
    assert all(canary not in message for canary in PRIVATE_CANARIES)
    assert "https://" not in message and "@" not in message


def test_completed_operation_error_is_detected_despite_http_success(tmp_path):
    url = OPERATION_URL.replace("provision-example_123", PRIVATE_CANARIES[4])
    text = "\n".join([
        debug_response("status", "200", method="GET", url=url),
        debug_response("body", json.dumps({"done": True, **private_api_error(code=7)}), method="GET", url=url),
    ])
    (tmp_path / "firebase-debug.log").write_text(text)
    message = auth.cli_failure_diagnostic(SimpleNamespace(stderr="", stdout=""), tmp_path)
    assert "stage=provider_operation http=200 api_code=7 api_status=PERMISSION_DENIED" in message
    assert all(canary not in message for canary in PRIVATE_CANARIES)


def operation_transcript(name, *, poll_url=None, provision_status="200", provision_url=PROVISION_URL):
    # CLI 15.8.0 forwards response.body.name to OperationPoller; apiv2 only
    # prepends the fixed API prefix and a slash when the name has none.
    if poll_url is None:
        poll_url = "https://firebase.googleapis.com/v1beta1" + (
            name if name.startswith("/") else "/" + name)
    return "\n".join([
        debug_response("status", provision_status, url=provision_url),
        debug_response("body", json.dumps({"name": name}), url=provision_url),
        debug_response("status", "200", method="GET", url=poll_url),
        debug_response("body", json.dumps({"done": True, **private_api_error(code=7)}),
                       method="GET", url=poll_url),
    ])


@pytest.mark.parametrize("name", [
    "operations/private-operation-id:1.2",
    f"projects/{auth.NUMBER}/locations/global/operations/private-operation-id:1.2",
    "/operations/private-operation-id:1.2",
])
def test_server_operation_name_correlates_completed_error_without_leaking_name(tmp_path, name):
    # Synthetic resource names exercise the pinned CLI contract, not a claim
    # about the shape of the discarded production response.
    (tmp_path / "firebase-debug.log").write_text(operation_transcript(name))
    message = auth.cli_failure_diagnostic(SimpleNamespace(stdout="", stderr=""), tmp_path)
    assert message == ("CLI response diagnostic: stage=provider_operation http=200 api_code=7 "
                       "api_status=PERMISSION_DENIED reason=IAM_PERMISSION_DENIED "
                       "permission=firebaseauth.configs.update")
    assert all(canary not in message for canary in PRIVATE_CANARIES)
    assert name not in message and "https://" not in message and len(message) < 256


@pytest.mark.parametrize("poll_url", [
    OPERATION_URL,  # Even the old recognized grammar must match the learned name.
    "https://firebase.googleapis.com/v1beta1/operations/different:1.2",
    "https://firebase.googleapis.com/v1beta1/operations/private-operation-id:1.2/extra",
    "https://firebase.googleapis.com/v1beta1/operations/private-operation-id:1.2?key=private",
    "https://firebase.googleapis.com/v1beta1/operations/private-operation-id:1.2#private",
    "https://firebase.googleapis.com.evil.test/v1beta1/operations/private-operation-id:1.2",
])
def test_learned_operation_cannot_borrow_another_poll_response(poll_url):
    assert auth._cli_observation(operation_transcript(
        "operations/private-operation-id:1.2", poll_url=poll_url)) == {
            "stage": "provider_provision", "http": 200}


@pytest.mark.parametrize("name", [
    None, False, 7, [], {}, "", "operations/" + "x" * 2048,
    "https://private.example.test/operations/id", "//private.example.test/operations/id",
    "https:operations/id", "operations/id?access_token=private", "operations/id#private",
    "operations/../id", "operations/./id", "../operations/id", "operations//id",
    "operations/id/", "operations/%2e%2e/id", "operations/id%3Fkey=private",
    "operations\\id", "operations/id\nprivate", "operations/id\rprivate",
    "operations/id\tprivate", "operations/id\x00private", "operations/id private",
    "operations/id\u2028private", "operations/id\x7fprivate",
])
def test_untrusted_operation_name_cannot_authorize_poll_diagnostics(name):
    # A malformed response disables legacy uncorrelated operation matching too.
    assert auth._cli_observation(operation_transcript(name, poll_url=OPERATION_URL)) == {
        "stage": "provider_provision", "http": 200}


@pytest.mark.parametrize("status", ["400", "403", "500"])
def test_failed_provision_response_does_not_authorize_poll_diagnostics(status):
    assert auth._cli_observation(operation_transcript(
        "operations/private-operation-id:1.2", provision_status=status)) == {
            "stage": "provider_provision", "http": int(status)}


def test_untrusted_provision_response_cannot_teach_an_operation_name():
    text = operation_transcript("operations/private-operation-id:1.2",
                                provision_url="https://private.example.test/provision")
    assert auth._cli_observation(text) == {}


def test_operation_name_requires_a_paired_provision_response():
    text = operation_transcript("operations/private-operation-id:1.2")
    assert auth._cli_observation("\n".join(text.splitlines()[1:])) == {}
    text = text.replace(debug_response("status", "200"), "\n".join([
        debug_response("status", "200"),
        debug_response("status", "200", url="https://private.example.test/unrelated"),
    ]), 1)
    assert auth._cli_observation(text) == {"stage": "provider_provision", "http": 200}


def test_new_provision_response_invalidates_previous_operation_name():
    first = operation_transcript("operations/first:1.2").splitlines()[:2]
    second = operation_transcript("operations/second:1.2",
                                   poll_url="https://firebase.googleapis.com/v1beta1/operations/first:1.2")
    assert auth._cli_observation("\n".join([*first, second])) == {
        "stage": "provider_provision", "http": 200}


def test_correlated_operation_http_error_omits_arbitrary_message():
    name = "operations/private-operation-id:1.2"
    prefix = operation_transcript(name).splitlines()[:2]
    text = "\n".join([*prefix,
        "Error: Failed to provision Firebase app: Request to "
        f"https://firebase.googleapis.com/v1beta1/{name} had HTTP Error: 403, "
        + " ".join(PRIVATE_CANARIES)])
    assert auth._cli_observation(text) == {"stage": "provider_operation", "http": 403}


def test_provision_http_error_invalidates_previously_learned_operation():
    lines = operation_transcript("operations/private-operation-id:1.2").splitlines()
    text = "\n".join([*lines[:2],
        f"Error: Request to {PROVISION_URL} had HTTP Error: 403, " + PRIVATE_CANARIES[0],
        *lines[2:]])
    assert auth._cli_observation(text) == {"stage": "provider_provision", "http": 403}


def test_error_body_cannot_teach_operation_name_despite_success_http():
    name = "operations/private-operation-id:1.2"
    text = operation_transcript(name).splitlines()
    text[1] = debug_response("body", json.dumps({"name": name, **private_api_error(code=7)}))
    assert auth._cli_observation("\n".join(text)) == {
        "stage": "provider_provision", "http": 200, "api_code": 7,
        "api_status": "PERMISSION_DENIED", "reason": "IAM_PERMISSION_DENIED",
        "permission": "firebaseauth.configs.update"}


def test_successful_correlated_operation_does_not_extract_response_secrets(tmp_path):
    name = "operations/private-operation-id:1.2"
    text = operation_transcript(name).splitlines()[:3]
    text.append(debug_response("body", json.dumps({
        "name": name, "done": True, "response": {"clientSecret": " ".join(PRIVATE_CANARIES)},
    }), method="GET", url="https://firebase.googleapis.com/v1beta1/" + name))
    (tmp_path / "firebase-debug.log").write_text("\n".join(text))
    assert auth.cli_failure_diagnostic(SimpleNamespace(stdout="", stderr=""), tmp_path) == (
        "CLI response diagnostic: stage=provider_operation http=200")


def test_operation_correlation_is_not_shared_between_independent_output_sources(tmp_path):
    lines = operation_transcript("operations/private-operation-id:1.2").splitlines()
    (tmp_path / "firebase-debug.log").write_text("\n".join(lines[:2]))
    assert auth.cli_failure_diagnostic(SimpleNamespace(stdout="\n".join(lines[2:]), stderr=""), tmp_path) == (
        "CLI response diagnostic: stage=provider_provision http=200")


@pytest.mark.parametrize("method,url,stage", [
    ("POST", f"https://cloudresourcemanager.googleapis.com/v1/projects/{auth.PROJECT}:testIamPermissions", "permission_check"),
    ("GET", f"https://cloudresourcemanager.googleapis.com/v1/projects/{auth.NUMBER}", "project_read"),
    ("GET", f"https://firebase.googleapis.com/v1beta1/projects/{auth.PROJECT}", "firebase_project_read"),
    ("GET", f"https://firebase.googleapis.com/v1beta1/projects/{auth.NUMBER}/webApps", "web_app_list"),
    ("POST", PROVISION_URL, "provider_provision"),
    ("GET", OPERATION_URL, "provider_operation"),
    ("GET", f"https://firebase.googleapis.com/v1beta1/projects/{auth.PROJECT}/operations/example", "provider_operation"),
])
def test_only_known_endpoint_shapes_are_mapped_to_fixed_stages(method, url, stage):
    assert auth._cli_observation(debug_response("status", "503", method=method, url=url)) == {
        "stage": stage, "http": 503}


@pytest.mark.parametrize("url", [
    PROVISION_URL.replace("firebase.googleapis.com", "firebase.googleapis.com.evil.test"),
    PROVISION_URL.replace("https://", "https://private@example.test@"),
    PROVISION_URL + "?access_token=secret-token-canary", PROVISION_URL + "#secret-token-canary",
    PROVISION_URL + "/extra", PROVISION_URL.replace("https://", "http://"),
    "https://firebase.googleapis.com/v1beta1/projects/another-project/webApps",
    "https://firebase.googleapis.com/v1beta1/projects/specimen-digitization/secrets/example",
])
def test_unknown_or_credential_bearing_urls_never_become_diagnostics(url):
    assert auth._cli_observation(debug_response("status", "403", url=url)) == {}
    assert auth._cli_observation(f"Error: Request to {url} had HTTP Error: 403, private") == {}


@pytest.mark.parametrize("payload", ["099", "600", "403 secret", "True", "-1"])
def test_malformed_http_status_is_not_reported(payload):
    assert auth._cli_observation(debug_response("status", payload)) == {}


@pytest.mark.parametrize("body", ["{broken", "[]", "null", '{"error": "private"}',
                                "[" * 2000 + "]" * 2000])
def test_malformed_bodies_keep_only_the_known_http_observation(body):
    text = debug_response("status", "403") + "\n" + debug_response("body", body)
    assert auth._cli_observation(text) == {"stage": "provider_provision", "http": 403}


@pytest.mark.parametrize("code", [True, False, 0, 17, 399, 600, 7.0, "403", [403], {"code": 403}])
def test_unbounded_or_wrong_type_error_fields_are_omitted(code):
    body = private_api_error(code=code, status=PRIVATE_CANARIES[0], details=[
        {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": PRIVATE_CANARIES[1],
         "metadata": {"permission": PRIVATE_CANARIES[2]}},
        {"@type": "unrecognized", "reason": "IAM_PERMISSION_DENIED",
         "metadata": {"permission": "firebaseauth.configs.update"}},
    ])
    assert auth._structured_cli_error(json.dumps(body)) == {
        "api_code": "unrecognized", "api_status": "unrecognized",
        "reason": "unrecognized", "permission": "unrecognized"}


@pytest.mark.parametrize("reason,permission", [
    ("SERVICE_DISABLED", "serviceusage.services.enable"),
    ("BILLING_DISABLED", "serviceusage.services.get"),
    ("ACCESS_TOKEN_SCOPE_INSUFFICIENT", "serviceusage.services.use"),
    ("ACCESS_TOKEN_TYPE_UNSUPPORTED", "clientauthconfig.brands.create"),
    ("ACCOUNT_TYPE_UNSUPPORTED", "clientauthconfig.clients.create"),
    ("CREDENTIAL_TYPE_UNSUPPORTED", "firebase.clients.create"),
    ("RESOURCE_USAGE_RESTRICTION_VIOLATED", "clientauthconfig.clients.get"),
    ("ENDPOINT_USAGE_RESTRICTION_VIOLATED", "resourcemanager.projects.get"),
])
def test_public_api_restriction_reasons_and_permissions_are_preserved(reason, permission):
    body = private_api_error(details=[
        {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": reason,
         "metadata": {"permission": permission, "credential": PRIVATE_CANARIES[0]}},
    ])
    assert auth._structured_cli_error(json.dumps(body)) == {
        "api_code": 403, "api_status": "PERMISSION_DENIED", "reason": reason, "permission": permission}


@pytest.mark.parametrize("query", ["pageSize=100", "pageSize=100&pageToken=secret-token-canary%2Fnext"])
def test_web_app_pagination_in_real_cli_error_url_is_classified_without_query_values(query):
    url = f"https://firebase.googleapis.com/v1beta1/projects/{auth.PROJECT}/webApps?{query}"
    # listFirebaseApps logs responseToError.message as a debug line. apiv2's
    # ordinary status/body records use requestURL without this query string.
    text = f"[debug] [2026-10-17T21:00:00.000Z] Request to {url} had HTTP Error: 403, private"
    assert auth._cli_observation(text) == {"stage": "web_app_list", "http": 403}
    assert auth._cli_observation(debug_response("status", "403", method="GET", url=url)) == {
        "stage": "web_app_list", "http": 403}


@pytest.mark.parametrize("query", ["access_token=secret-token-canary", "pageSize=100&token=private",
                                 "pageSize=100&pageSize=200", "pageSize=private", "pageToken=",
                                 "pageSize=100#secret-token-canary", "pageSize=100&pageToken=x&other=y"])
def test_unrecognized_query_shapes_are_not_classified(query):
    url = f"https://firebase.googleapis.com/v1beta1/projects/{auth.PROJECT}/webApps?{query}"
    assert auth._cli_observation(debug_response("status", "403", method="GET", url=url)) == {}
    assert auth._cli_observation(debug_response("status", "403", method="GET", url=OPERATION_URL + "?" + query)) == {}


def test_structured_error_requires_the_matching_response_record():
    body = debug_response("body", json.dumps(private_api_error()))
    assert auth._cli_observation(body) == {}
    text = "\n".join([debug_response("status", "403"),
                       debug_response("status", "403", url="https://unknown.example.test"), body])
    assert auth._cli_observation(text) == {"stage": "provider_provision", "http": 403}
    text = "\n".join([debug_response("status", "403"), body,
                       debug_response("status", "200", method="GET", url=OPERATION_URL)])
    assert auth._cli_observation(text) == {"stage": "provider_operation", "http": 200}


@pytest.mark.parametrize("log_kind", ["missing", "directory", "symlink", "hardlink", "fifo", "oversize", "binary"])
def test_unsafe_or_unreadable_debug_log_uses_bounded_console_fallback(tmp_path, log_kind):
    path = tmp_path / "firebase-debug.log"
    if log_kind == "directory":
        path.mkdir()
    elif log_kind in {"symlink", "hardlink"}:
        target = tmp_path / "private-other-file"
        target.write_text(debug_response("status", "401") + "\n" + PRIVATE_CANARIES[0])
        path.symlink_to(target) if log_kind == "symlink" else os.link(target, path)
    elif log_kind == "fifo":
        os.mkfifo(path)
    elif log_kind == "oversize":
        path.write_text(debug_response("status", "401") + "\n" + "x" * auth.DIAGNOSTIC_LIMIT)
    elif log_kind == "binary":
        path.write_bytes(debug_response("status", "401").encode() + b"\xff")
    assert auth._private_cli_log(tmp_path) == ""
    done = SimpleNamespace(stdout=PRIVATE_CANARIES[1], stderr=(
        f"Error: Failed to provision Firebase app: Request to {PROVISION_URL} had HTTP Error: 400, "
        + " ".join(PRIVATE_CANARIES)))
    assert auth.cli_failure_diagnostic(done, tmp_path) == (
        "CLI response diagnostic: stage=provider_provision http=400")


def test_private_log_read_error_is_bounded(monkeypatch, tmp_path):
    def refuse(*args):
        raise PermissionError(" ".join(PRIVATE_CANARIES))

    monkeypatch.setattr(auth.os, "open", refuse)
    assert auth.cli_failure_diagnostic(SimpleNamespace(stdout="", stderr=""), tmp_path) == (
        "CLI diagnostic unavailable")


def test_private_log_growth_past_size_limit_is_refused(monkeypatch, tmp_path):
    path = tmp_path / "firebase-debug.log"
    path.write_bytes(b"x" * (auth.DIAGNOSTIC_LIMIT + 1))
    actual_stat = os.stat(path)
    monkeypatch.setattr(auth.os, "fstat", lambda fd: SimpleNamespace(
        st_mode=actual_stat.st_mode, st_size=1, st_nlink=1))
    assert auth._private_cli_log(tmp_path) == ""


def test_oversize_captured_output_and_lines_are_not_parsed(tmp_path):
    line = debug_response("status", "403")
    assert auth._cli_observation(line + "\n" + "x" * auth.DIAGNOSTIC_LIMIT) == {}
    assert auth._cli_observation("Error: Request to " + PROVISION_URL + " had HTTP Error: 403, "
                                 + "x" * auth.DIAGNOSTIC_LINE_LIMIT) == {}
    done = SimpleNamespace(stdout="not a debug record " + line, stderr=" ".join(PRIVATE_CANARIES))
    assert auth.cli_failure_diagnostic(done, tmp_path) == "CLI diagnostic unavailable"


@pytest.mark.parametrize("timeout", [False, True])
def test_cli_failure_reads_private_log_before_cleanup_without_changing_command(monkeypatch, capsys, timeout):
    folders = []

    def run(argv, **kwargs):
        folders.append(Path(kwargs["cwd"]))
        if argv[-1] == "--version":
            assert kwargs["timeout"] == 30
            return SimpleNamespace(returncode=0, stdout="15.8.0\n")
        assert argv[1:7] == ["deploy", "--only", "auth", "--project", auth.PROJECT, "--config"]
        assert kwargs["timeout"] == 300 and argv[-1] == "--non-interactive"
        (folders[-1] / "firebase-debug.log").write_text("\n".join([
            debug_response("status", "403"), debug_response("body", json.dumps(private_api_error())),
        ]))
        if timeout:
            raise subprocess.TimeoutExpired(argv, 300, output=" ".join(PRIVATE_CANARIES))
        return SimpleNamespace(returncode=2, stdout=" ".join(PRIVATE_CANARIES), stderr=PRIVATE_CANARIES[0])

    monkeypatch.setattr(auth.subprocess, "run", run)
    with pytest.raises(auth.Failure) as caught:
        auth.run_cli("/pinned/firebase", auth.AUTH_CONFIG)
    message = str(caught.value)
    assert ("Pinned Auth CLI did not complete" if timeout else "Pinned Auth CLI exited 2") in message
    assert "stage=provider_provision http=403 api_code=403" in message
    assert "raw output omitted" in message
    assert all(canary not in message for canary in PRIVATE_CANARIES)
    assert len(folders) == 2 and all(not path.exists() for path in folders)
    assert capsys.readouterr() == ("", "")


class Response:
    def __init__(self, status, data=None):
        self.status_code, self.data = status, data

    def json(self):
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


class Session:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.mark.parametrize("failure", [Response(429), Response(503), OSError("PRIVATE-RESPONSE")])
def test_api_retries_reads_and_preserves_partial_response_fields(monkeypatch, failure):
    sleeps = []
    monkeypatch.setattr(auth.time, "sleep", sleeps.append)
    session = Session(failure, failure, Response(200, PROVIDER))
    assert auth.Api(session).call("GET", auth.GOOGLE_URL, fields=auth.GOOGLE_FIELDS) == PROVIDER
    assert sleeps == [1, 2] and len(session.calls) == 3
    assert all(call == (("GET", auth.GOOGLE_URL), {"params": {"fields": "name,enabled,clientId"},
                                                 "json": None, "timeout": (10, 30)}) for call in session.calls)


@pytest.mark.parametrize("answer", [Response(403, {"detail": "PRIVATE-RESPONSE"}), Response(503),
                                   OSError("PRIVATE-RESPONSE")])
def test_api_never_retries_writes_or_logs_raw_response(monkeypatch, answer):
    monkeypatch.setattr(auth.time, "sleep", lambda *a: pytest.fail("no retry"))
    session = Session(answer)
    with pytest.raises(auth.Failure) as caught:
        auth.Api(session).call("PATCH", auth.GOOGLE_URL, fields=auth.GOOGLE_FIELDS,
                               body={"enabled": True}, update_mask="enabled")
    assert len(session.calls) == 1 and "PRIVATE-RESPONSE" not in str(caught.value)
    assert session.calls[0][1]["params"] == {"fields": auth.GOOGLE_FIELDS, "updateMask": "enabled"}


@pytest.mark.parametrize("answer", [Response(200, []), Response(200, ValueError("PRIVATE-RESPONSE")),
                                   Response(400, {"detail": "PRIVATE-RESPONSE"})])
def test_api_rejects_invalid_or_error_answers_without_their_content(answer):
    with pytest.raises(auth.Failure) as caught:
        auth.Api(Session(answer)).call("GET", auth.GOOGLE_URL, fields=auth.GOOGLE_FIELDS)
    assert "PRIVATE-RESPONSE" not in str(caught.value)


def test_only_explicit_missing_provider_read_accepts_404():
    assert auth.Api(Session(Response(404))).call("GET", auth.GOOGLE_URL, fields=auth.GOOGLE_FIELDS,
                                               missing=True) is None
    with pytest.raises(auth.Failure, match="HTTP 404"):
        auth.Api(Session(Response(404))).call("GET", auth.CONFIG_URL, fields=auth.PRESERVED_FIELDS)


def test_workflow_keeps_auth_after_data_and_installs_pinned_cli_before_credentials():
    workflow = yaml.load((auth.ROOT / ".github/workflows/data-release.yml").read_text(), Loader=yaml.BaseLoader)
    steps = workflow["jobs"]["release"]["steps"]
    install = next(i for i, step in enumerate(steps) if step.get("name") == "Install the pinned Firebase Auth CLI")
    signin = next(i for i, step in enumerate(steps) if step.get("uses", "").startswith("google-github-actions/auth@"))
    data = next(i for i, step in enumerate(steps) if step.get("run", "").endswith("data_release.py"))
    georef = next(i for i, step in enumerate(steps) if step.get("run", "").endswith("georef_datasets.py"))
    provider = next(i for i, step in enumerate(steps) if step.get("run", "").endswith("provision_auth.py"))
    assert install < signin < data < georef < provider
    assert steps[install]["run"] == ('npm install --prefix "$RUNNER_TEMP/auth-cli" --no-audit --no-fund '
                                      '--ignore-scripts firebase-tools@15.8.0')
    assert steps[provider]["env"] == {"AUTH_RELEASE_ENVIRONMENT": "data-production",
                                      "AUTH_RELEASE_CLI": "${{ runner.temp }}/auth-cli/node_modules/.bin/firebase"}
    assert json.loads((auth.ROOT / "firebase.auth.json").read_text()) == auth.AUTH_CONFIG
    assert "auth" not in json.loads((auth.ROOT / "firebase.json").read_text())
    # Read projections cannot fetch password hashes, client secrets or users.
    assert auth.PRESERVED_FIELDS == "authorizedDomains,signIn(email(enabled,passwordRequired))"
    assert auth.GOOGLE_FIELDS == "name,enabled,clientId"
