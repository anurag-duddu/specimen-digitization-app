#!/usr/bin/env python3
"""Strict, non-deploying readiness preflight using GitHub's expected source."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

from validate_release_packet import validate

REPOSITORY = "anurag-duddu/specimen-digitization-app"


def expected_source(env: dict[str, str]) -> str:
    if (env.get("GITHUB_ACTIONS") != "true"
            or env.get("GITHUB_REPOSITORY") != REPOSITORY
            or env.get("GITHUB_REPOSITORY_ID") != "1360732425"
            or env.get("GITHUB_REPOSITORY_OWNER_ID") != "140138196"):
        raise ValueError("readiness requires the expected GitHub repository context")
    ref = env.get("GITHUB_REF", "")
    main = env.get("GITHUB_EVENT_NAME") == "push" and ref == "refs/heads/main"
    integration = (env.get("GITHUB_EVENT_NAME") == "pull_request"
                   and env.get("GITHUB_HEAD_REF") == "codex/live-integration"
                   and re.fullmatch(r"refs/pull/[1-9][0-9]*/merge", ref) is not None)
    if not (main or integration):
        raise ValueError("readiness only accepts main push or the integration PR")
    if env.get("GITHUB_WORKFLOW_REF") != f"{REPOSITORY}/.github/workflows/runtime-ci.yml@{ref}":
        raise ValueError("unexpected readiness workflow")
    sha = env.get("GITHUB_SHA", "")
    if re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise ValueError("missing trusted GitHub source SHA")
    return sha


def check(packet_path: Path, env: dict[str, str]) -> None:
    sha = expected_source(env)
    if packet_path.name == "candidate.example.json":
        raise ValueError("the incomplete example is never a readiness input")
    validate(json.loads(packet_path.read_text()), require_ready=True, expected_source_sha=sha)


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("supply the generated real release packet path")
        check(Path(sys.argv[1]), dict(os.environ))
    except (ValueError, OSError) as exc:
        raise SystemExit(f"Readiness blocked: {exc}") from None
    print("Source-bound evidence structure is complete; external evidence verification and authorization remain required.")
