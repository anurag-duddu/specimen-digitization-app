"""Fail-closed identity checks for the candidate runtime/data release contract.

Offline checks are necessary but insufficient: WIF and GitHub environment policy
must enforce the same restrictions. This module grants no cloud credentials.
"""
from __future__ import annotations

import re

REPOSITORY = "anurag-duddu/specimen-digitization-app"
PROJECT = "specimen-digitization"
PLANES = {
    "runtime": ("runtime-production", "runtime-release.yml", "specimen-runtime-release"),
    "data": ("data-production", "data-release.yml", "specimen-data-release"),
}


def validate_context(env: dict[str, str], plane: str, source_sha: str) -> None:
    if plane not in PLANES:
        raise ValueError("unknown release plane")
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("invalid release source")
    environment, workflow, identity = PLANES[plane]
    expected = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_REPOSITORY_ID": "1360732425",
        "GITHUB_REPOSITORY_OWNER_ID": "140138196",
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REF_PROTECTED": "true",
        "GITHUB_WORKFLOW_REF": f"{REPOSITORY}/.github/workflows/{workflow}@refs/heads/main",
        "GITHUB_SHA": source_sha,
        "DEPLOYMENT_ENVIRONMENT": environment,
        "RELEASE_AUTHORIZED_SHA": source_sha,
        "RELEASE_PROJECT": PROJECT,
        "RELEASE_SERVICE_ACCOUNT": f"{identity}@{PROJECT}.iam.gserviceaccount.com",
    }
    for key, value in expected.items():
        if env.get(key) != value:
            raise ValueError(f"release context rejected: {key}")
