"""Auth release contracts with fake HTTP/CLI only; no live credentials or network."""
from __future__ import annotations

import copy
import importlib.util
import json
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
