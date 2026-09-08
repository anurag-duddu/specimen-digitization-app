import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("release_context", Path(__file__).with_name("release_context.py"))
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
SHA = "a" * 40


def valid_context(plane):
    environment, workflow, identity = MODULE.PLANES[plane]
    return {
        "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": MODULE.REPOSITORY,
        "GITHUB_REPOSITORY_ID": "1360732425", "GITHUB_REPOSITORY_OWNER_ID": "140138196",
        "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main", "GITHUB_REF_PROTECTED": "true",
        "GITHUB_WORKFLOW_REF": f"{MODULE.REPOSITORY}/.github/workflows/{workflow}@refs/heads/main",
        "GITHUB_SHA": SHA, "DEPLOYMENT_ENVIRONMENT": environment, "RELEASE_AUTHORIZED_SHA": SHA,
        "RELEASE_PROJECT": MODULE.PROJECT,
        "RELEASE_SERVICE_ACCOUNT": f"{identity}@{MODULE.PROJECT}.iam.gserviceaccount.com",
    }


@pytest.mark.parametrize("plane", ["runtime", "data"])
def test_accept_exact_candidate_context(plane):
    MODULE.validate_context(valid_context(plane), plane, SHA)


@pytest.mark.parametrize("plane", ["runtime", "data"])
@pytest.mark.parametrize("field,value", [
    ("GITHUB_ACTIONS", "false"), ("GITHUB_REPOSITORY", "fork/specimen-digitization-app"),
    ("GITHUB_REPOSITORY_ID", "1"), ("GITHUB_REPOSITORY_OWNER_ID", "1"),
    ("GITHUB_EVENT_NAME", "pull_request"), ("GITHUB_EVENT_NAME", "workflow_dispatch"),
    ("GITHUB_EVENT_NAME", "workflow_run"), ("GITHUB_REF", "refs/heads/feature"),
    ("GITHUB_REF_PROTECTED", "false"), ("GITHUB_WORKFLOW_REF", "ci-cd.yml"),
    ("GITHUB_SHA", "b" * 40), ("DEPLOYMENT_ENVIRONMENT", "production"),
    ("RELEASE_AUTHORIZED_SHA", "b" * 40), ("RELEASE_PROJECT", "other"),
    ("RELEASE_SERVICE_ACCOUNT", "github-firebase-hosting@specimen-digitization.iam.gserviceaccount.com"),
])
def test_reject_wrong_identity_event_environment_source_and_target(plane, field, value):
    env = valid_context(plane)
    env[field] = value
    with pytest.raises(ValueError, match=field):
        MODULE.validate_context(env, plane, SHA)


@pytest.mark.parametrize("plane", ["runtime", "data"])
def test_reject_every_missing_guard(plane):
    for field in valid_context(plane):
        env = valid_context(plane)
        del env[field]
        with pytest.raises(ValueError, match=field):
            MODULE.validate_context(env, plane, SHA)


def test_runtime_identity_cannot_be_used_for_data():
    with pytest.raises(ValueError):
        MODULE.validate_context(valid_context("runtime"), "data", SHA)
