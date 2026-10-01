import ast
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dev" / "google_auth_preflight.py"
SAFE_PROBE_SETTINGS = {
    "CLOUDSDK_AUTH_DISABLE_SSL_VALIDATION": "false",
    "CLOUDSDK_CORE_DISABLE_FILE_LOGGING": "true",
    "CLOUDSDK_CORE_MAX_LOG_DAYS": "0",
    "CLOUDSDK_CORE_LOG_HTTP": "false",
    "CLOUDSDK_CORE_LOG_HTTP_REDACT_TOKEN": "true",
    "CLOUDSDK_CORE_LOG_HTTP_SHOW_REQUEST_BODY": "false",
    "CLOUDSDK_CORE_LOG_HTTP_STREAMING_BODY": "false",
    "CLOUDSDK_CORE_USER_OUTPUT_ENABLED": "true",
    "CLOUDSDK_CORE_FORMAT": "value[private](token)",
    "CLOUDSDK_CORE_DRY_RUN": "0",
}
TRANSPORT_PROFILE_KEYS = (
    "CLOUDSDK_AUTH_DISABLE_SSL_VALIDATION",
    "CLOUDSDK_CORE_CUSTOM_CA_CERTS_FILE",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "CLOUDSDK_AUTH_TOKEN_INTROSPECTION_ENDPOINT",
    "CLOUDSDK_CORE_UNIVERSE_DOMAIN",
    "CLOUDSDK_API_ENDPOINT_OVERRIDES_IAMCREDENTIALS",
    "CLOUDSDK_API_ENDPOINT_OVERRIDES_STORAGE",
)


def write_fake_gcloud(path: Path) -> None:
    path.write_text(
        """#!/bin/sh
set -eu
printf '%s\\n' "$*" >> "$FAKE_GCLOUD_CALLS"
printf '%s|%s\\n' "${CLOUDSDK_CORE_DISABLE_PROMPTS:-}" "${CLOUDSDK_CORE_SHOULD_PROMPT_TO_ENABLE_API:-}" >> "$FAKE_GCLOUD_ENV"
if IFS= read -r ignored; then
  printf '%s\\n' 'unexpected-stdin' >&2
  exit 98
fi
if [ "$1" = auth ] && [ "$2" = print-access-token ]; then
  printf '%s' "${FAKE_CLI_STDOUT:-PRIVATE_CLI_TOKEN}"
  printf '%s' "${FAKE_CLI_STDERR:-PRIVATE_CLI_ERROR}" >&2
  exit "${FAKE_CLI_CODE:-0}"
fi
if [ "$1" = auth ] && [ "$2" = application-default ] && [ "$3" = print-access-token ]; then
  printf '%s' "${FAKE_ADC_STDOUT:-PRIVATE_ADC_TOKEN}"
  printf '%s' "${FAKE_ADC_STDERR:-PRIVATE_ADC_ERROR}" >&2
  exit "${FAKE_ADC_CODE:-0}"
fi
printf '%s\\n' 'unapproved-gcloud-command' >&2
exit 97
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def preflight_env(tmp_path: Path, *, with_gcloud: bool = True) -> tuple[dict[str, str], Path, Path]:
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    flags = tmp_path / "flags.log"
    if with_gcloud:
        write_fake_gcloud(bin_dir / "gcloud")
    env = {
        "HOME": str(home),
        "PATH": str(bin_dir),
        "LC_ALL": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_GCLOUD_CALLS": str(calls),
        "FAKE_GCLOUD_ENV": str(flags),
    }
    return env, calls, flags


def run_preflight(tmp_path: Path, *, with_gcloud: bool = True, **updates: str) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    env, calls, flags = preflight_env(tmp_path, with_gcloud=with_gcloud)
    env.update(updates)
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return result, calls, flags, Path(env["HOME"])


def payload(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.stdout.endswith("\n")
    assert result.stdout.count("\n") == 1
    return json.loads(result.stdout)


def assert_private_canaries_are_absent(result: subprocess.CompletedProcess[str]) -> None:
    combined = result.stdout + result.stderr
    for canary in (
        "PRIVATE_CLI_TOKEN",
        "PRIVATE_CLI_ERROR",
        "PRIVATE_ADC_TOKEN",
        "PRIVATE_ADC_ERROR",
        "PRIVATE_OVERRIDE_VALUE",
        "wrong-project",
    ):
        assert canary not in combined


def test_success_is_sanitized_noninteractive_and_runs_only_the_two_probes(tmp_path):
    result, calls, flags, home = run_preflight(tmp_path)

    assert result.returncode == 0
    assert payload(result) == {
        "blocking_reasons": [],
        "checks": {
            "application_default_credentials": "ready",
            "cli_auth": "ready",
            "environment": "clear",
            "gcloud": "available",
        },
        "next_action": "none",
        "schema_version": 1,
        "status": "ready",
    }
    assert calls.read_text(encoding="utf-8").splitlines() == [
        "auth print-access-token --project=specimen-digitization --quiet",
        "auth application-default print-access-token --project=specimen-digitization --quiet",
    ]
    assert flags.read_text(encoding="utf-8").splitlines() == ["true|false", "true|false"]
    assert list(home.iterdir()) == []
    assert_private_canaries_are_absent(result)


@pytest.mark.parametrize(
    ("updates", "expected_reason", "expected_checks"),
    [
        (
            {"FAKE_CLI_CODE": "1"},
            "cli_auth_unavailable",
            {"cli_auth": "blocked", "application_default_credentials": "ready"},
        ),
        (
            {"FAKE_ADC_CODE": "1"},
            "application_default_credentials_unavailable",
            {"cli_auth": "ready", "application_default_credentials": "blocked"},
        ),
        (
            {"FAKE_CLI_CODE": "1", "FAKE_ADC_CODE": "1"},
            "cli_auth_unavailable",
            {"cli_auth": "blocked", "application_default_credentials": "blocked"},
        ),
    ],
)
def test_auth_failures_never_trigger_login_or_leak_subprocess_output(tmp_path, updates, expected_reason, expected_checks):
    result, calls, _flags, home = run_preflight(tmp_path, **updates)

    assert result.returncode == 2
    result_payload = payload(result)
    assert result_payload["status"] == "blocked"
    assert expected_reason in result_payload["blocking_reasons"]
    assert result_payload["next_action"] == "owner_sign_in_required"
    for key, value in expected_checks.items():
        assert result_payload["checks"][key] == value
    called = calls.read_text(encoding="utf-8")
    assert "login" not in called
    assert "deploy" not in called
    assert "config set" not in called
    assert list(home.iterdir()) == []
    assert_private_canaries_are_absent(result)


def test_missing_gcloud_stops_without_falling_back_to_a_real_binary(tmp_path):
    result, calls, _flags, home = run_preflight(tmp_path, with_gcloud=False)

    assert result.returncode == 2
    assert payload(result)["blocking_reasons"] == ["gcloud_missing"]
    assert not calls.exists()
    assert list(home.iterdir()) == []


@pytest.mark.parametrize(
    ("key", "reason"),
    [
        ("GOOGLE_APPLICATION_CREDENTIALS", "credential_override:GOOGLE_APPLICATION_CREDENTIALS"),
        ("CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE", "credential_override:CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE"),
        ("CLOUDSDK_AUTH_ACCESS_TOKEN", "credential_override:CLOUDSDK_AUTH_ACCESS_TOKEN"),
        ("CLOUDSDK_AUTH_ACCESS_TOKEN_FILE", "credential_override:CLOUDSDK_AUTH_ACCESS_TOKEN_FILE"),
        ("CLOUDSDK_CORE_ACCOUNT", "identity_override:CLOUDSDK_CORE_ACCOUNT"),
        ("CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT", "identity_override:CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT"),
        ("CLOUDSDK_CONFIG", "cloudsdk_config_override:CLOUDSDK_CONFIG"),
        ("CLOUDSDK_ACTIVE_CONFIG_NAME", "cloudsdk_config_override:CLOUDSDK_ACTIVE_CONFIG_NAME"),
        ("CLOUDSDK_AUTH_TOKEN_HOST", "cloudsdk_config_override:CLOUDSDK_AUTH_TOKEN_HOST"),
        ("CLOUDSDK_AUTH_MTLS_TOKEN_HOST", "cloudsdk_config_override:CLOUDSDK_AUTH_MTLS_TOKEN_HOST"),
    ],
)
def test_nonempty_profile_overrides_are_blocked_without_reading_or_printing_them(tmp_path, key, reason):
    result, calls, _flags, home = run_preflight(tmp_path, **{key: "PRIVATE_OVERRIDE_VALUE"})

    assert result.returncode == 2
    result_payload = payload(result)
    assert reason in result_payload["blocking_reasons"]
    assert result_payload["next_action"] == "clear_local_profile_overrides"
    assert not calls.exists()
    assert list(home.iterdir()) == []
    assert_private_canaries_are_absent(result)


@pytest.mark.parametrize("key", [
    "GOOGLE_APPLICATION_CREDENTIALS",
    "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE",
    "CLOUDSDK_AUTH_ACCESS_TOKEN",
    "CLOUDSDK_AUTH_ACCESS_TOKEN_FILE",
    "CLOUDSDK_CORE_ACCOUNT",
    "CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT",
    "CLOUDSDK_CONFIG",
    "CLOUDSDK_ACTIVE_CONFIG_NAME",
    "CLOUDSDK_AUTH_TOKEN_HOST",
    "CLOUDSDK_AUTH_MTLS_TOKEN_HOST",
])
def test_blank_profile_overrides_are_refused_for_the_parent_caller_contract(tmp_path, key):
    result, calls, _flags, _home = run_preflight(tmp_path, **{key: ""})

    assert result.returncode == 2
    assert payload(result)["status"] == "blocked"
    assert payload(result)["next_action"] == "clear_local_profile_overrides"
    assert not calls.exists()
    parent = {key: "", "PATH": "/synthetic/normal-profile", "LANG": "C"}
    child = load_module().no_prompt_environment(parent)
    assert key not in child
    assert child["PATH"] == parent["PATH"] and child["LANG"] == parent["LANG"]
    assert parent == {key: "", "PATH": "/synthetic/normal-profile", "LANG": "C"}


@pytest.mark.parametrize("key", ["GOOGLE_CLOUD_PROJECT", "GCLOUD_PROJECT", "CLOUDSDK_CORE_PROJECT"])
def test_mismatched_project_override_is_blocked_without_leaking_its_value(tmp_path, key):
    result, calls, _flags, _home = run_preflight(tmp_path, **{key: "wrong-project"})

    assert result.returncode == 2
    result_payload = payload(result)
    assert result_payload["blocking_reasons"] == [f"project_override_mismatch:{key}"]
    assert result_payload["next_action"] == "correct_project_override"
    assert not calls.exists()
    assert_private_canaries_are_absent(result)


def test_matching_project_override_is_allowed(tmp_path):
    result, calls, _flags, _home = run_preflight(
        tmp_path, GOOGLE_CLOUD_PROJECT="specimen-digitization"
    )

    assert result.returncode == 0
    assert payload(result)["status"] == "ready"
    assert calls.exists()


def test_invalid_usage_does_not_invoke_gcloud(tmp_path):
    env, calls, _flags = preflight_env(tmp_path)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--unexpected"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 64
    assert payload(result)["blocking_reasons"] == ["usage_error"]
    assert not calls.exists()


def load_module():
    spec = importlib.util.spec_from_file_location("google_auth_preflight", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("key", [
    "CLOUDSDK_CORE_ACCOUNT",
    "CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT",
    "CLOUDSDK_AUTH_ACCESS_TOKEN_FILE",
    "CLOUDSDK_AUTH_TOKEN_HOST",
    "CLOUDSDK_AUTH_MTLS_TOKEN_HOST",
])
def test_profile_override_stops_before_discovery(monkeypatch, capsys, key):
    module = load_module()
    monkeypatch.setattr(module.os, "environ", {key: "PRIVATE_OVERRIDE_VALUE"})

    def forbidden(*_args, **_kwargs):
        pytest.fail("an explicit profile override must stop before gcloud discovery or probes")

    monkeypatch.setattr(module.shutil, "which", forbidden)
    monkeypatch.setattr(module.subprocess, "run", forbidden)

    assert module.main([]) == 2
    result = capsys.readouterr()
    assert json.loads(result.out)["checks"] == {
        "environment": "blocked", "gcloud": "not_run", "cli_auth": "not_run",
        "application_default_credentials": "not_run",
    }
    assert "PRIVATE_OVERRIDE_VALUE" not in result.out + result.err


def test_timeout_is_sanitized_and_never_retried(monkeypatch, capsys):
    module = load_module()
    for key in (
        *module.CREDENTIAL_OVERRIDE_KEYS,
        *module.IDENTITY_OVERRIDE_KEYS,
        *module.CONFIG_OVERRIDE_KEYS,
        *module.PROJECT_OVERRIDE_KEYS,
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(module.shutil, "which", lambda *_args, **_kwargs: "/synthetic/gcloud")
    calls = []

    def timeout(arguments, **kwargs):
        calls.append((arguments, kwargs))
        raise subprocess.TimeoutExpired(arguments, kwargs["timeout"], output=b"PRIVATE_TIMEOUT_TOKEN", stderr=b"PRIVATE_TIMEOUT_ERROR")

    monkeypatch.setattr(module.subprocess, "run", timeout)

    assert module.main([]) == 2
    result = capsys.readouterr()
    result_payload = json.loads(result.out)
    assert result_payload["blocking_reasons"] == [
        "cli_auth_unavailable",
        "application_default_credentials_unavailable",
    ]
    assert result_payload["next_action"] == "owner_sign_in_required"
    assert len(calls) == 2
    for _arguments, kwargs in calls:
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["timeout"] == module.PROBE_TIMEOUT_SECONDS
        assert kwargs["env"]["CLOUDSDK_CORE_DISABLE_PROMPTS"] == "true"
        assert kwargs["env"]["CLOUDSDK_CORE_SHOULD_PROMPT_TO_ENABLE_API"] == "false"
    assert "PRIVATE_TIMEOUT" not in result.out + result.err


@pytest.mark.parametrize("key", TRANSPORT_PROFILE_KEYS)
@pytest.mark.parametrize("value", ["", "PRIVATE_OVERRIDE_VALUE"])
def test_transport_overrides_stop_before_discovery(monkeypatch, capsys, key, value):
    module = load_module()
    parent = {"PATH": "/synthetic/normal-profile", key: value}
    monkeypatch.setattr(module.os, "environ", parent)
    monkeypatch.setattr(module.shutil, "which", lambda *_a, **_k: pytest.fail("discovery forbidden"))
    monkeypatch.setattr(module.subprocess, "run", lambda *_a, **_k: pytest.fail("probe forbidden"))

    assert module.main([]) == 2
    result = capsys.readouterr()
    body = json.loads(result.out)
    assert body["blocking_reasons"] == [f"transport_override:{key}"]
    assert body["checks"]["cli_auth"] == body["checks"]["gcloud"] == "not_run"
    assert body["next_action"] == "clear_local_profile_overrides"
    assert "PRIVATE_OVERRIDE_VALUE" not in result.out + result.err
    assert parent == {"PATH": "/synthetic/normal-profile", key: value}


@pytest.mark.parametrize("inherited", [{}, {
    "CLOUDSDK_CORE_DISABLE_FILE_LOGGING": "false",
    "CLOUDSDK_CORE_LOG_HTTP": "true",
    "CLOUDSDK_CORE_LOG_HTTP_REDACT_TOKEN": "false",
    "CLOUDSDK_CORE_LOG_HTTP_SHOW_REQUEST_BODY": "true",
    "CLOUDSDK_CORE_LOG_HTTP_STREAMING_BODY": "true",
    "CLOUDSDK_CORE_USER_OUTPUT_ENABLED": "false",
    "CLOUDSDK_CORE_FORMAT": "none",
    "CLOUDSDK_CORE_DRY_RUN": "1",
}])
def test_probe_policy_prevents_synthetic_sdk_logging_and_false_login(monkeypatch, capsys, tmp_path, inherited):
    module = load_module()
    parent = {"PATH": "/synthetic/gcloud", "LANG": "C", **inherited}
    frozen_parent = dict(parent)
    monkeypatch.setattr(module.os, "environ", parent)
    monkeypatch.setattr(module.shutil, "which", lambda *_a, **_k: "/synthetic/gcloud")
    sdk_log = tmp_path / "synthetic-sdk.log"
    calls = []

    def fake_sdk(arguments, **kwargs):
        child = kwargs["env"]
        calls.append((arguments, kwargs))
        # Model the reviewed SDK formatter/file logger and HTTP-body policy;
        # these are synthetic secrets, never an actual SDK or credential store.
        if child.get("CLOUDSDK_CORE_DISABLE_FILE_LOGGING") != "true":
            sdk_log.write_text("PRIVATE_ACCESS_TOKEN", encoding="utf-8")
        if child.get("CLOUDSDK_CORE_LOG_HTTP") == "true" and child.get("CLOUDSDK_CORE_LOG_HTTP_REDACT_TOKEN") != "true":
            sdk_log.write_text("PRIVATE_REFRESH_TOKEN PRIVATE_CLIENT_SECRET PRIVATE_ACCESS_TOKEN", encoding="utf-8")
        suppressed = child.get("CLOUDSDK_CORE_USER_OUTPUT_ENABLED") == "false" or child.get("CLOUDSDK_CORE_FORMAT") == "none"
        return subprocess.CompletedProcess(arguments, 0, b"" if suppressed else b"PRIVATE_ACCESS_TOKEN", b"PRIVATE_ERROR")

    monkeypatch.setattr(module.subprocess, "run", fake_sdk)
    assert module.main([]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["next_action"] == "none"
    assert len(calls) == 2
    assert not sdk_log.exists()
    for _arguments, kwargs in calls:
        assert {key: kwargs["env"].get(key) for key in SAFE_PROBE_SETTINGS} == SAFE_PROBE_SETTINGS
        assert kwargs["env"]["PATH"] == parent["PATH"] and kwargs["env"]["LANG"] == "C"
        assert kwargs["stdin"] is subprocess.DEVNULL
    assert parent == frozen_parent
    assert "PRIVATE_" not in output.out + output.err


def test_child_policy_defensively_overrides_tls_without_mutating_parent():
    parent = {key: "PRIVATE_UNSAFE_SETTING" for key in SAFE_PROBE_SETTINGS}
    parent["CLOUDSDK_AUTH_DISABLE_SSL_VALIDATION"] = "true"
    child = load_module().no_prompt_environment(parent)
    assert {key: child.get(key) for key in SAFE_PROBE_SETTINGS} == SAFE_PROBE_SETTINGS
    assert parent["CLOUDSDK_AUTH_DISABLE_SSL_VALIDATION"] == "true"
    assert parent["CLOUDSDK_CORE_LOG_HTTP"] == "PRIVATE_UNSAFE_SETTING"


@pytest.mark.parametrize("blank", [False, True])
def test_preflight_to_documented_inventory_uses_the_same_effective_policy(monkeypatch, capsys, blank):
    module = load_module()
    parent = {"PATH": "/synthetic/gcloud", "LANG": "C"}
    if blank:
        parent["CLOUDSDK_AUTH_TOKEN_HOST"] = ""
    frozen_parent = dict(parent)
    monkeypatch.setattr(module.os, "environ", parent)
    monkeypatch.setattr(module.shutil, "which", lambda *_a, **_k: "/synthetic/gcloud")
    calls = []

    def fake_run(arguments, **kwargs):
        calls.append(kwargs["env"])
        bad_endpoint = kwargs["env"].get("CLOUDSDK_AUTH_TOKEN_HOST") == ""
        return subprocess.CompletedProcess(arguments, 1 if bad_endpoint else 0, b"PRIVATE_ACCESS_TOKEN", b"")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    code = module.main([])
    report = json.loads(capsys.readouterr().out)
    if blank:
        # No false ready that invites the unchanged caller with an empty URI.
        assert code == 2 and report["next_action"] == "clear_local_profile_overrides"
        assert not calls
    else:
        assert code == 0
        runbook = (ROOT / "docs/execution/GO_LIVE_RUNBOOK.md").read_text(encoding="utf-8")
        block = re.search(r"```bash\n(env CLOUDSDK_AUTH_DISABLE_SSL_VALIDATION=false.*?)\n```", runbook, re.S)
        assert block, "runbook must retain the scoped safe-policy inventory command"
        words = shlex.split(block.group(1).replace("\\\n", " "))
        caller_settings = dict(word.split("=", 1) for word in words[1:] if word.startswith("CLOUDSDK_") and "=" in word)
        assert caller_settings == SAFE_PROBE_SETTINGS
        assert "scripts/data/inventory_cloud.py" in words
        # Execute only the unchanged caller's actual run_gcloud function AST.
        # Never import or invoke inventory(), its REST path, or real subprocesses.
        source = ROOT / "scripts/data/inventory_cloud.py"
        wrapper = next(node for node in ast.parse(source.read_text(encoding="utf-8")).body if isinstance(node, ast.FunctionDef) and node.name == "run_gcloud")
        namespace = {"os": SimpleNamespace(environ={**parent, **caller_settings}), "subprocess": SimpleNamespace(run=fake_run, DEVNULL=subprocess.DEVNULL)}
        exec(compile(ast.Module(body=[wrapper], type_ignores=[]), str(source), "exec"), namespace)
        result = namespace["run_gcloud"](["gcloud", "auth", "print-access-token", "--project=specimen-digitization"], 1)
        assert result.returncode == 0 and len(calls) == 3
        for child in calls:
            assert {key: child.get(key) for key in SAFE_PROBE_SETTINGS} == SAFE_PROBE_SETTINGS
            assert child["CLOUDSDK_CORE_DISABLE_PROMPTS"] == "true"
    assert parent == frozen_parent
