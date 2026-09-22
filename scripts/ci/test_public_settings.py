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


@pytest.mark.parametrize("contact", ["Alex Mwangi <alex.mwangi@fieldmuseum.org>", "Entomology data team, insects-data@fieldmuseum.org", "insects-data@fieldmuseum.org", ""])
def test_accept_administrator_contact_forms(contact):
    MODULE.validate_contact({"SPECIMEN_ADMIN_CONTACT": contact})


@pytest.mark.parametrize("contact", ["Alex Mwangi", "Alex <not-an-address>", "<alex@fieldmuseum.org", "Alex <alex@fieldmuseum.org>\n", "Alex \"Ops\" <alex@fieldmuseum.org>", "a" * 190 + " <alex@fieldmuseum.org>", "Alex <alex@fieldmuseum.org> <b@c.org>"])
def test_reject_malformed_administrator_contact(contact):
    with pytest.raises(ValueError):
        MODULE.validate_contact({"SPECIMEN_ADMIN_CONTACT": contact})


@pytest.mark.parametrize("scope", [
    "",
    "Ten original specimens",
    "Ten original specimens, Hymenoptera drawer 4 (2026 pilot)",
    "a",
    "a" * 80,
])
def test_accept_pilot_scope_a_band_can_draw(scope):
    MODULE.validate_pilot_scope({"SPECIMEN_PILOT_SCOPE": scope})


def test_pilot_scope_stands_alone():
    """It is not paired with the API URL. A bounded pilot can be stamped on a
    build whose API address is still unset, and the client shows the band from
    the build stamp alone."""
    MODULE.validate_pilot_scope({"SPECIMEN_PILOT_SCOPE": "Ten original specimens"})
    MODULE.validate({})


@pytest.mark.parametrize("scope,reason", [
    (" Ten original specimens", "whitespace"),
    ("Ten original specimens ", "whitespace"),
    # A repository variable that picked up a newline is the likeliest way this
    # goes wrong, and the band would draw the stamp nobody can see is broken.
    ("Ten original specimens\n", "whitespace"),
    ("   ", "whitespace"),
    ("a" * 81, "longer than 80"),
    ("Ten original\nspecimens", "unprintable"),
    ("Ten original\tspecimens", "unprintable"),
    ("Ten original\x00specimens", "unprintable"),
    ("Ten original\x7fspecimens", "unprintable"),
])
def test_reject_pilot_scope_the_band_cannot_draw(scope, reason):
    with pytest.raises(ValueError) as raised:
        MODULE.validate_pilot_scope({"SPECIMEN_PILOT_SCOPE": scope})
    assert reason in str(raised.value)
    # The reason names the rule, never the value: this file is the one gate
    # that runs over public settings in a log anybody can read.
    if scope.strip():
        assert scope.strip() not in str(raised.value)


def test_the_entry_point_runs_the_pilot_scope_gate():
    """`validate` and `validate_contact` are both called from `__main__`, and
    a third rule that nothing calls is not a gate."""
    source = (Path(__file__).with_name("validate_public_settings.py")
              .read_text(encoding="utf-8"))
    entry = source.split('if __name__ == "__main__":', 1)[1]
    assert "validate_pilot_scope(os.environ)" in entry


def test_the_length_budget_is_the_one_the_band_promises():
    """The band is one line or two at every text scale (finding V-15), and the
    scope is drawn straight into its headline. The cap lives here because the
    build is the only place that can refuse a value before it ships."""
    assert MODULE.PILOT_SCOPE_MAX == 80


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
               SPECIMEN_RECAPTCHA_SITE_KEY="synthetic-site-key",
               SPECIMEN_ADMIN_CONTACT="Alex Mwangi <alex.mwangi@fieldmuseum.org>",
               SPECIMEN_PILOT_SCOPE="Ten original specimens")
    env.pop("SPECIMEN_AUTH_EMULATOR_HOST", None)
    env.pop("SPECIMEN_LOCAL_SYNTHETIC", None)
    result = subprocess.run([str(root / "scripts/ci/build_web.sh")], cwd=root / "apps/specimen_digitization",
                            env=env, text=True, capture_output=True, check=True)
    assert ("--dart-define=SPECIMEN_API_BASE_URL=" in result.stdout) is live
    assert ("--dart-define=SPECIMEN_RECAPTCHA_SITE_KEY=" in result.stdout) is live
    assert ("--dart-define=SPECIMEN_ADMIN_CONTACT=" in result.stdout) is live
    assert ("--dart-define=SPECIMEN_PILOT_SCOPE=" in result.stdout) is live


@pytest.mark.parametrize("sha", ["4f9f518", None])
def test_build_stamps_the_commit_when_ci_provides_one(tmp_path, sha):
    import os
    import subprocess

    root = Path(__file__).resolve().parents[2]
    binary = tmp_path / "flutter"
    binary.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    binary.chmod(0o755)
    env = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}")
    env.pop("GITHUB_ACTIONS", None)
    env.pop("GITHUB_SHA", None)
    if sha is not None:
        env["GITHUB_SHA"] = sha
    result = subprocess.run([str(root / "scripts/ci/build_web.sh")], cwd=root / "apps/specimen_digitization",
                            env=env, text=True, capture_output=True, check=True)
    stamped = f"--dart-define=APP_BUILD={sha}" in result.stdout
    assert stamped is (sha is not None)
    assert "APP_BUILD" not in result.stdout if sha is None else True
