from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ci-cd.yml"
DEPLOY_SCRIPT = ROOT / "scripts/ci/deploy_hosting.sh"


def test_workflow_preserves_production_gates() -> None:
    workflow = WORKFLOW.read_text()

    required_fragments = (
        "pull_request:",
        "push:\n    branches:\n      - main",
        "workflow_dispatch:",
        "if: github.event_name == 'push' && github.ref == 'refs/heads/main'",
        "environment:\n      name: production",
        "DEPLOYMENT_ENVIRONMENT: production",
        "id-token: write",
        "needs:\n      - repository-checks\n      - python\n      - flutter",
        "run: ../../scripts/ci/write_deployment_metadata.sh build/web",
        "run: scripts/ci/deploy_hosting.sh",
        "run: scripts/ci/smoke_hosting.sh",
    )
    for fragment in required_fragments:
        assert fragment in workflow, f"required deployment gate is missing: {fragment}"


def test_deploy_script_is_fail_closed_and_hosting_only() -> None:
    script = DEPLOY_SCRIPT.read_text()

    for required in (
        'GITHUB_ACTIONS:-}" == "true"',
        'GITHUB_EVENT_NAME:-}" == "push"',
        'GITHUB_REF:-}" == "$expected_ref"',
        'GITHUB_WORKFLOW_REF:-}" == "$expected_workflow_ref"',
        'DEPLOYMENT_ENVIRONMENT:-}" == "$expected_environment"',
        "--only hosting",
        '--project "$expected_project"',
        '--non-interactive',
    ):
        assert required in script

    assert "--force" not in script
    assert "dataconnect" not in script.lower()
    assert "storage" not in script.lower()
    assert "functions" not in script.lower()


def test_no_other_automation_can_issue_a_deploy() -> None:
    deploy_patterns = (
        re.compile(r"firebase(?:-tools)?(?:@[^\s]+)?\s+deploy", re.IGNORECASE),
        re.compile(r"firebase\s+hosting:channel:deploy", re.IGNORECASE),
        re.compile(r"gcloud\s+[^\n]*\bdeploy\b", re.IGNORECASE),
    )
    candidates = [
        *ROOT.glob(".github/workflows/*.yml"),
        *ROOT.glob(".github/workflows/*.yaml"),
        *ROOT.glob("scripts/**/*.sh"),
        *ROOT.glob("scripts/**/*.py"),
    ]

    violations: list[str] = []
    for path in candidates:
        if path == DEPLOY_SCRIPT:
            continue
        text = path.read_text()
        if any(pattern.search(text) for pattern in deploy_patterns):
            violations.append(str(path.relative_to(ROOT)))

    assert violations == [], f"unapproved deployment command in: {violations}"


def test_firebase_target_is_exactly_the_default_hosting_site() -> None:
    firebase_config = (ROOT / "firebase.json").read_text()
    firebase_alias = (ROOT / ".firebaserc").read_text()

    assert '"site": "specimen-digitization"' in firebase_config
    assert '"public": "apps/specimen_digitization/build/web"' in firebase_config
    assert '"default": "specimen-digitization"' in firebase_alias
