from pathlib import Path
import importlib.util
import json
import sys

import pytest

DIRECTORY = Path(__file__).parent
sys.path.insert(0, str(DIRECTORY))
try:
    SPEC = importlib.util.spec_from_file_location("readiness", DIRECTORY / "check_release_readiness.py")
    assert SPEC and SPEC.loader
    MODULE = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(MODULE)
finally:
    sys.path.pop(0)


def context():
    return {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": MODULE.REPOSITORY,
            "GITHUB_REPOSITORY_ID": "1360732425", "GITHUB_REPOSITORY_OWNER_ID": "140138196",
            "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": "a" * 40,
            "GITHUB_WORKFLOW_REF": f"{MODULE.REPOSITORY}/.github/workflows/runtime-ci.yml@refs/heads/main"}


def test_main_and_integration_use_workflow_sha():
    env = context()
    assert MODULE.expected_source(env) == "a" * 40
    env.update(GITHUB_EVENT_NAME="pull_request", GITHUB_HEAD_REF="codex/live-integration", GITHUB_REF="refs/pull/9/merge")
    env["GITHUB_WORKFLOW_REF"] = f"{MODULE.REPOSITORY}/.github/workflows/runtime-ci.yml@refs/pull/9/merge"
    assert MODULE.expected_source(env) == "a" * 40


@pytest.mark.parametrize("field,value", [("GITHUB_ACTIONS", "false"), ("GITHUB_EVENT_NAME", "workflow_dispatch"),
                                         ("GITHUB_SHA", ""), ("GITHUB_WORKFLOW_REF", "other"),
                                         ("GITHUB_REPOSITORY_ID", "1"), ("GITHUB_REF", "refs/heads/other")])
def test_reject_wrong_readiness_context(field, value):
    env = context()
    env[field] = value
    with pytest.raises(ValueError):
        MODULE.expected_source(env)


def test_missing_or_example_packet_never_means_ready(tmp_path):
    with pytest.raises(OSError):
        MODULE.check(tmp_path / "absent.json", context())
    with pytest.raises(ValueError, match="never a readiness input"):
        MODULE.check(tmp_path / "candidate.example.json", context())


def test_candidate_ci_actually_runs_the_strict_preflight():
    """The strict check is worthless unless a workflow invokes it."""
    workflow = (DIRECTORY.parents[1] / ".github/workflows/runtime-ci.yml").read_text()
    assert "python3 scripts/ci/check_release_readiness.py" in workflow
    # It must stay non-deploying and credential-free where it is wired.
    assert "secrets." not in workflow and "google-github-actions" not in workflow
    # A pull request that is not the integration branch reports Not run.
    assert "Not run: release readiness is checked only on main" in workflow


def test_self_consistent_stale_source_rejected(tmp_path):
    packet = json.loads((DIRECTORY.parents[1] / "infra/release/candidate.example.json").read_text())
    packet["source_sha"] = "b" * 40
    path = tmp_path / "real-packet.json"
    path.write_text(json.dumps(packet))
    with pytest.raises(ValueError, match="expected candidate source"):
        MODULE.check(path, context())
