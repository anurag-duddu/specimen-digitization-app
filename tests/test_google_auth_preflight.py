import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dev" / "google_auth_preflight.py"


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
])
def test_blank_profile_overrides_are_harmless(tmp_path, key):
    result, calls, _flags, _home = run_preflight(tmp_path, **{key: ""})

    assert result.returncode == 0
    assert payload(result)["status"] == "ready"
    assert calls.exists()


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
])
def test_identity_or_token_file_override_stops_before_discovery(monkeypatch, capsys, key):
    module = load_module()
    monkeypatch.setattr(module.os, "environ", {key: "PRIVATE_OVERRIDE_VALUE"})

    def forbidden(*_args, **_kwargs):
        pytest.fail("an explicit identity/token override must stop before gcloud discovery or probes")

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
