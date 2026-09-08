import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("public_settings", Path(__file__).with_name("validate_public_settings.py"))
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_empty_configuration_preserves_setup_screen():
    MODULE.validate({})


def test_public_https_settings():
    MODULE.validate({"SPECIMEN_API_BASE_URL": "https://example.run.app/api", "SPECIMEN_RECAPTCHA_SITE_KEY": "synthetic-site-key"})


@pytest.mark.parametrize("url", ["http://example.com", "https://fixture-user@example.com", "https://example.com?q=x", "https://example.com#x", "https://localhost", "https://example.com:8000", "https://example.com\\@evil.com", "https://example.com\n"])
def test_reject_unsafe_urls(url):
    with pytest.raises(ValueError):
        MODULE.validate({"SPECIMEN_API_BASE_URL": url, "SPECIMEN_RECAPTCHA_SITE_KEY": "synthetic-site-key"})


@pytest.mark.parametrize("env", [{"SPECIMEN_API_BASE_URL": "https://example.com"}, {"SPECIMEN_RECAPTCHA_SITE_KEY": "synthetic-site-key"}, {"SPECIMEN_AUTH_EMULATOR_HOST": "localhost:9099"}, {"SPECIMEN_LOCAL_SYNTHETIC": "true"}])
def test_reject_partial_or_development_settings(env):
    with pytest.raises(ValueError):
        MODULE.validate(env)


@pytest.mark.parametrize("event,ref,live", [
    ("push", "refs/heads/main", True),
    ("pull_request", "refs/pull/1/merge", False),
    ("workflow_dispatch", "refs/heads/main", False),
    ("push", "refs/heads/feature", False),
])
def test_build_forwards_public_values_only_on_main_push(tmp_path, event, ref, live):
    import os
    import subprocess

    root = Path(__file__).resolve().parents[2]
    binary = tmp_path / "flutter"
    binary.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    binary.chmod(0o755)
    env = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}", GITHUB_ACTIONS="true",
               GITHUB_EVENT_NAME=event, GITHUB_REF=ref,
               SPECIMEN_API_BASE_URL="https://example.run.app",
               SPECIMEN_RECAPTCHA_SITE_KEY="synthetic-site-key")
    env.pop("SPECIMEN_AUTH_EMULATOR_HOST", None)
    env.pop("SPECIMEN_LOCAL_SYNTHETIC", None)
    result = subprocess.run([str(root / "scripts/ci/build_web.sh")], cwd=root / "apps/specimen_digitization",
                            env=env, text=True, capture_output=True, check=True)
    assert ("--dart-define=SPECIMEN_API_BASE_URL=" in result.stdout) is live
    assert ("--dart-define=SPECIMEN_RECAPTCHA_SITE_KEY=" in result.stdout) is live
