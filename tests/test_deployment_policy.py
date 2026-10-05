from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ci-cd.yml"
DEPLOY_SCRIPT = ROOT / "scripts/ci/deploy_hosting.sh"
APPROVED_DEPLOY_SCRIPTS = {
    DEPLOY_SCRIPT,
    ROOT / "scripts/release/deploy_api.py",
    ROOT / "scripts/release/deploy_models.py",
    ROOT / "scripts/release/process_worker.py",
    # Retired (scripts/ci/RETIRED.md): no workflow calls these two any more. They
    # stay listed only until the follow-up pull request deletes the files.
    ROOT / "scripts/ci/deploy_runtime.py",
    ROOT / "scripts/ci/deploy_data.py",
}
# The operator's plain runtime deploy (scripts/ops/README.md) may issue only its two Cloud Run deploys, the SAM 3
# service and the worker job; any other deploy command in it still fails. The exemption is for the hand bring-up and
# should be removed when the release workflows run these deploys.
OPS_DEPLOY = ROOT / "scripts/ops/deploy.py"
OPS_DEPLOY_CALLS = re.compile(r'"gcloud", "run", (?:"jobs", )?"deploy"')
ARGV_DEPLOY = re.compile(r'"(?:firebase|gcloud)"[^\n]*"[^"\n]*deploy[^"\n]*"', re.IGNORECASE)
DEPLOY_PATTERNS = (
    re.compile(r"firebase(?:-tools)?(?:@[^\s]+)?\s+deploy", re.IGNORECASE),
    re.compile(r"firebase\s+hosting:channel:deploy", re.IGNORECASE),
    re.compile(r"gcloud\s+[^\n]*\bdeploy\b", re.IGNORECASE),
)
RELEASE_WORKFLOWS = {
    "data": ROOT / ".github/workflows/data-release.yml",
    "runtime": ROOT / ".github/workflows/runtime-release.yml",
}
PLANES = sorted(RELEASE_WORKFLOWS)
MAIN_ONLY = "github.ref == 'refs/heads/main'"
POOL = "projects/716045864126/locations/global/workloadIdentityPools/github-actions"  # pragma: allowlist secret
# GitHub environment -> the one identity that signs in from it. The provider and the
# service account share the name, and the live provider accepts only that environment.
IDENTITIES = {
    "data-production": "specimen-data-release",
    "runtime-build-production": "specimen-runtime-build",
    "runtime-production": "specimen-runtime-release",
}
PLANE_ENVIRONMENTS = {
    "data": {"data-production"},
    "runtime": {"runtime-build-production", "runtime-production"},
}
RETIRED_MANIFEST = ROOT / "scripts/ci/RETIRED.md"
OWNER_SETUP = ROOT / "scripts/ops/owner_setup.sh"
# The words of the retired release process (AGENTS.md, "No release ceremony").
CEREMONY = re.compile(r"receipt|admission|packet|attest|recovery[\s_-]*window", re.IGNORECASE)
# owner_setup.sh prints the leftover settings of the retired process so that the owner can delete them.
LEFTOVER_NAMES = ("RELEASE_PACKET_SHA256",)
# The actions a release uses. Another one, such as an upload or a signing action, is a reviewed change here.
RELEASE_ACTIONS = {"actions/checkout", "astral-sh/setup-uv", "actions/setup-node", "google-github-actions/auth"}
# What a release step may run: a committed script, or one of the two pinned installs.
SCRIPT_CALL = re.compile(r'(?:uv run python )?(scripts/(?:release|ci)/[\w./-]+\.(?:py|sh))(?: [\w"$.-]+)*')
INSTALLS = (
    re.compile(r"uv sync --frozen"),
    re.compile(r'npm install --prefix "\$RUNNER_TEMP/[\w-]+" --no-audit --no-fund --ignore-scripts'
               r"(?: (?:@[\w-]+/)?[\w-]+@\d+\.\d+\.\d+)+"),
)


def release_text(plane: str) -> str:
    return RELEASE_WORKFLOWS[plane].read_text()


def release_workflow(plane: str) -> dict:
    return yaml.load(release_text(plane), Loader=yaml.BaseLoader)


def release_steps(plane: str) -> list[tuple[str, dict]]:
    return [(name, step) for name, job in release_workflow(plane)["jobs"].items() for step in job["steps"]]


def environment_of(job: dict) -> str | None:
    environment = job.get("environment")
    return environment["name"] if isinstance(environment, dict) else environment


def needs_of(job: dict) -> list[str]:
    needs = job.get("needs", [])
    return [needs] if isinstance(needs, str) else needs


def is_sign_in(step: dict) -> bool:
    return step.get("uses", "").startswith("google-github-actions/auth@")


def is_install(step: dict) -> bool:
    return any(pattern.fullmatch(step.get("run", "")) for pattern in INSTALLS) or "/setup-" in step.get("uses", "")


def release_sources() -> list[Path]:
    """Everything a release runs: the two workflows and the non-test files of scripts/release and scripts/ops."""
    return [*RELEASE_WORKFLOWS.values(), *sorted(
        path for folder in ("scripts/release", "scripts/ops") for path in (ROOT / folder).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and not path.name.startswith(("test_", ".")))]


def retired() -> tuple[set[str], list[str]]:
    """List 1 of the manifest: the retired file names in scripts/ci, and the retired action directories."""
    section = RETIRED_MANIFEST.read_text().split("\n## 1. Retired scripts\n", 1)[1].split("\n## ", 1)[0]
    bullets = re.findall(r"^- .*(?:\n  .*)*", section, re.MULTILINE)
    # A name without a directory is a file in scripts/ci; a bullet may also name the script that replaced it.
    scripts = {name for bullet in bullets for name in re.findall(r"`([^`/]+)`", bullet)}
    actions = [name.rstrip("/") for name in re.findall(r"`(\.github/actions/[^`]+)`", section)]
    return scripts, actions


def retired_reference() -> re.Pattern[str]:
    """A retired file by its name, a retired Python module in an import line or as a quoted module name,
    or a retired action directory."""
    scripts, actions = retired()
    modules = "|".join(sorted(re.escape(Path(name).stem) for name in scripts if name.endswith(".py")))
    return re.compile("|".join((
        r"(?<!\w)(?:%s)(?!\w)" % "|".join(sorted(map(re.escape, scripts))),
        r"^[ \t]*(?:from|import)[ \t][^\n#]*(?<!\w)(?:%s)(?!\w)" % modules,
        r"[\"'](?:%s)[\"']" % modules,
        *map(re.escape, actions),
    )), re.MULTILINE)


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


def test_hosting_and_the_release_workflows_never_run_each_others_scripts() -> None:
    hosting = WORKFLOW.read_text()
    assert "scripts/release/" not in hosting and "scripts/ops/" not in hosting
    # The Hosting workflow never signs in as a release identity or enters a release environment.
    for environment, identity in IDENTITIES.items():
        assert environment not in hosting and identity not in hosting
    for plane in PLANES:
        assert "deploy_hosting" not in release_text(plane), plane


def test_only_the_three_deploy_workflows_can_sign_in_to_the_cloud() -> None:
    deployers = {WORKFLOW.name, *(path.name for path in RELEASE_WORKFLOWS.values())}
    others = [path for path in (*ROOT.glob(".github/workflows/*.yml"), *ROOT.glob(".github/workflows/*.yaml"))
              if path.name not in deployers]
    for path in others:
        text = path.read_text()
        assert "id-token" not in text and "google-github-actions/auth" not in text, path.name


def test_no_other_automation_can_issue_a_deploy() -> None:
    candidates = [
        *ROOT.glob(".github/workflows/*.yml"),
        *ROOT.glob(".github/workflows/*.yaml"),
        *ROOT.glob("scripts/**/*.sh"),
        *ROOT.glob("scripts/**/*.py"),
    ]
    # An approval names a file in the tree; a stale one would approve a later file of that name.
    assert all(path.is_file() for path in APPROVED_DEPLOY_SCRIPTS)

    violations: list[str] = []
    for path in candidates:
        if path in APPROVED_DEPLOY_SCRIPTS:
            continue
        if issues_deploy(path, path.read_text()):
            violations.append(str(path.relative_to(ROOT)))

    assert violations == [], f"unapproved deployment command in: {violations}"


def issues_deploy(path: Path, text: str) -> bool:
    if path == OPS_DEPLOY:
        text = OPS_DEPLOY_CALLS.sub("", text)
        if ARGV_DEPLOY.search(text):
            return True
    return any(pattern.search(text) for pattern in DEPLOY_PATTERNS)


def test_ops_deploy_may_issue_only_its_two_cloud_run_deploys() -> None:
    text = OPS_DEPLOY.read_text()
    assert len(OPS_DEPLOY_CALLS.findall(text)) == 2
    assert not issues_deploy(OPS_DEPLOY, text)
    for added in ('["firebase", "deploy", "--only", "hosting"]', "firebase deploy --only hosting",
                  '["gcloud", "functions", "deploy", "f"]', "gcloud app deploy"):
        assert issues_deploy(OPS_DEPLOY, text + "\n" + added + "\n"), added


def test_firebase_target_is_exactly_the_default_hosting_site() -> None:
    firebase_config = (ROOT / "firebase.json").read_text()
    firebase_alias = (ROOT / ".firebaserc").read_text()

    assert '"site": "specimen-digitization"' in firebase_config
    assert '"public": "apps/specimen_digitization/build/web"' in firebase_config
    assert '"default": "specimen-digitization"' in firebase_alias


def test_release_contract_names_only_approved_backend_workflows() -> None:
    agents = (ROOT / "AGENTS.md").read_text()
    contract = (ROOT / "docs/DEPLOYMENT.md").read_text()
    for document in (agents, contract):
        for filename in ("ci-cd.yml", "runtime-release.yml", "data-release.yml"):
            assert f".github/workflows/{filename}" in document
        # The one-time owner setup and the list of retired scripts are part of the contract.
        assert "scripts/ops/owner_setup.sh" in document
        assert "scripts/ci/RETIRED.md" in document
        assert "workflow_dispatch" in document
    # The identity table names, for each release workflow, the pairs the workflows are held to below.
    for plane, environments in PLANE_ENVIRONMENTS.items():
        for environment in environments:
            identity = IDENTITIES[environment]
            row = f"| `.github/workflows/{plane}-release.yml` | `{environment}` | `{identity}` | `{identity}` |"
            assert row in contract, row


@pytest.mark.parametrize("plane", PLANES)
def test_release_workflow_starts_from_main_or_a_manual_run_and_one_runs_at_a_time(plane: str) -> None:
    workflow = release_workflow(plane)
    # No pull request, fork, schedule or other workflow can start a release.
    assert set(workflow["on"]) == {"push", "workflow_dispatch"}
    assert workflow["on"]["push"] == {"branches": ["main"]}
    # Manual releases take no deployment configuration. The one runtime input
    # explicitly opts into processing already queued work after the release.
    if plane == "data":
        assert workflow["on"]["workflow_dispatch"] == ""
    else:
        inputs = workflow["on"]["workflow_dispatch"]["inputs"]
        assert set(inputs) == {"process_queued"}
        assert inputs["process_queued"]["type"] == "boolean"
        assert inputs["process_queued"]["default"] == "false"
    assert workflow.get("permissions") == {"contents": "read"}
    assert workflow.get("concurrency") == {"group": f"specimen-{plane}-release", "cancel-in-progress": "false"}


def test_release_workflows_never_share_a_concurrency_group() -> None:
    # The runtime release waits for the data release of its commit; in one shared group it would wait for itself.
    groups = [release_workflow(plane)["concurrency"]["group"] for plane in PLANES]
    assert len(set(groups)) == len(groups)


@pytest.mark.parametrize("plane", PLANES)
def test_every_release_job_runs_only_for_main_on_a_pinned_runner_within_a_time_limit(plane: str) -> None:
    jobs = release_workflow(plane)["jobs"]
    for name, job in jobs.items():
        assert job.get("runs-on") == "ubuntu-24.04", name
        assert job.get("timeout-minutes", "").isdigit(), f"{name} has no time limit"
        if not needs_of(job):
            # A manual run can start from any branch, so every first job checks the ref itself.
            assert job.get("if") == MAIN_ONLY, name
        else:
            assert set(needs_of(job)) <= set(jobs), name
            # A later job is skipped when a job it needs was skipped or failed,
            # unless a status function overrides that.
            assert not re.search(r"\b(always|failure|cancelled)\s*\(", job.get("if", "")), name


def test_runtime_deploy_waits_for_the_data_release_and_the_image() -> None:
    jobs = release_workflow("runtime")["jobs"]
    assert any(step.get("run") == "scripts/release/wait_for_data.sh" for step in jobs["data"]["steps"])
    assert environment_of(jobs["build"]) == "runtime-build-production"
    assert environment_of(jobs["release"]) == "runtime-production"
    assert sorted(needs_of(jobs["release"])) == ["build", "data"]
    for name, job in jobs.items():
        if environment_of(job) == "runtime-production":
            assert "data" in needs_of(job), f"{name} can deploy before the data release succeeded"


@pytest.mark.parametrize("plane", PLANES)
def test_cloud_credentials_exist_only_in_an_environment_with_its_own_identity(plane: str) -> None:
    jobs = release_workflow(plane)["jobs"]
    used = set()
    for name, job in jobs.items():
        permissions = job.get("permissions", {})
        assert isinstance(permissions, dict), name
        # Nothing but the sign-in token is ever writable.
        assert all(value == "read" for key, value in permissions.items() if key != "id-token"), name
        sign_ins = [step.get("with", {}) for step in job["steps"] if is_sign_in(step)]
        environment = environment_of(job)
        if environment is None:
            assert "id-token" not in permissions, f"{name} can sign in outside a main-only environment"
            assert sign_ins == [], name
            continue
        assert environment in PLANE_ENVIRONMENTS[plane], name
        identity = IDENTITIES[environment]
        assert len(sign_ins) == 1, name
        assert sign_ins[0].get("project_id") == "specimen-digitization", name
        assert sign_ins[0].get("workload_identity_provider") == f"{POOL}/providers/{identity}", name
        assert sign_ins[0].get("service_account") == f"{identity}@specimen-digitization.iam.gserviceaccount.com", name
        used.add(environment)
    assert used == PLANE_ENVIRONMENTS[plane]
    # Keyless only: a service-account key never reaches a release.
    assert "credentials_json" not in release_text(plane)


@pytest.mark.parametrize("plane", PLANES)
def test_every_release_action_is_pinned_to_a_full_commit_sha(plane: str) -> None:
    jobs = release_workflow(plane)["jobs"]
    used = [step["uses"] for _, step in release_steps(plane) if "uses" in step]
    assert used and all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", action) for action in used), used
    assert {action.split("@")[0] for action in used} <= RELEASE_ACTIONS, used
    # No job is a reusable workflow, whose steps this file could not read.
    assert not any("uses" in job for job in jobs.values())
    assert len(re.findall(r"^\s*(?:- )?uses:", release_text(plane), re.MULTILINE)) == len(used)


@pytest.mark.parametrize("plane", PLANES)
def test_release_steps_stop_at_a_failure_and_run_only_committed_scripts(plane: str) -> None:
    assert "continue-on-error" not in release_text(plane)
    commands = [step["run"] for _, step in release_steps(plane) if "run" in step]
    assert commands
    for command in commands:
        if any(pattern.fullmatch(command) for pattern in INSTALLS):
            continue
        # One committed script per step: no inline gcloud, firebase or docker command, and no shell around it.
        call = SCRIPT_CALL.fullmatch(command)
        assert call, f"not a call of a script under scripts/release or scripts/ci: {command!r}"
        script = ROOT / call.group(1)
        assert script.is_file() and ".." not in script.parts, command
        if command.startswith("scripts/"):
            assert os.access(script, os.X_OK), f"{call.group(1)} is run directly and must be executable"


@pytest.mark.parametrize("plane", PLANES)
def test_release_jobs_install_pinned_tools_before_any_credential_exists(plane: str) -> None:
    hosting = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    for name, job in release_workflow(plane)["jobs"].items():
        steps = job["steps"]
        for step in steps:
            action = step.get("uses", "").split("@")[0]
            if action == "actions/checkout":
                # The commit that started the run, and no token left behind in the work tree.
                assert step.get("with") == {"persist-credentials": "false"}, name
            elif action == "astral-sh/setup-uv":
                # The uv version of the required checks (ci-cd.yml) and of scripts/ci/verify.sh.
                assert step.get("with") == {"version": hosting["env"]["UV_VERSION"], "python-version": "3.12"}, name
            elif action == "actions/setup-node":
                assert step.get("with") == {"node-version": "22"}, name
        sign_in = next((index for index, step in enumerate(steps) if is_sign_in(step)), len(steps))
        late = [step.get("run") or step["uses"] for step in steps[sign_in:] if is_install(step)]
        assert late == [], f"{name} installs packages while a cloud credential exists: {late}"


def test_release_workflows_read_one_secret_and_no_variable() -> None:
    data, runtime = release_text("data"), release_text("runtime")
    # The owner's first-rows artifact reaches only the step that runs the data release, as an environment variable.
    assert re.findall(r"\bsecrets\b[^\s}]*", data) == ["secrets.DATA_BOOTSTRAP_ARTIFACT_B64"]
    holders = [step for _, step in release_steps("data") if "secrets." in str(step)]
    assert len(holders) == 1 and holders[0].get("run") == "uv run python scripts/release/data_release.py"
    assert holders[0].get("env", {}).get("DATA_BOOTSTRAP_ARTIFACT_B64") == "${{ secrets.DATA_BOOTSTRAP_ARTIFACT_B64 }}"
    assert re.findall(r"\bsecrets\b", runtime) == []
    # The read-only run token is used once, by the job that waits for the data release and has no cloud identity.
    token = re.compile(r"github\.token|GITHUB_TOKEN")
    assert token.findall(data) == [] and token.findall(runtime) == ["github.token"]
    holders = [(name, step) for name, step in release_steps("runtime") if token.search(str(step))]
    assert [(name, step.get("run"), step.get("env")) for name, step in holders] == [
        ("data", "scripts/release/wait_for_data.sh", {"GH_TOKEN": "${{ github.token }}"})]
    assert environment_of(release_workflow("runtime")["jobs"]["data"]) is None
    # Every other value is a committed file: a release reads no repository or environment variable.
    for text in (data, runtime):
        assert not re.search(r"\bvars\.", text)


def test_no_release_file_refers_to_a_retired_script_or_brings_the_ceremony_back() -> None:
    scripts, actions = retired()
    assert {"deploy_data.py", "deploy_runtime.py", "release_gate.py"} <= scripts
    assert ".github/actions/runtime-publication" in actions
    reference = retired_reference()
    sources = release_sources()
    # The scan reaches every script the workflows run, and the owner's script.
    calls = [SCRIPT_CALL.fullmatch(step.get("run", "")) for plane in PLANES for _, step in release_steps(plane)]
    called = {ROOT / call.group(1) for call in calls if call and call.group(1).startswith("scripts/release/")}
    assert called and called <= set(sources) and OWNER_SETUP in sources
    problems: list[str] = []
    for path in sources:
        text = path.read_text()
        if path == OWNER_SETUP:
            for name in LEFTOVER_NAMES:
                text = text.replace(name, "")
        for match in (*reference.finditer(text), *CEREMONY.finditer(text)):
            line = text.count("\n", 0, match.start()) + 1
            problems.append(f"{path.name}:{line}: {match.group(0).strip()}")
    assert problems == []
    # The manifest's own claim: no workflow at all, and not the local gate, calls a retired script.
    for path in (*ROOT.glob(".github/workflows/*.yml"), *ROOT.glob(".github/workflows/*.yaml"),
                 ROOT / "scripts/ci/verify.sh"):
        assert not reference.search(path.read_text()), path.name


def test_new_release_code_never_applies_data_connect_through_the_firebase_cli() -> None:
    # scripts/ci/test_schema_gate.py holds the same rule for the workflows and scripts/ci.
    for path in release_sources():
        assert not re.search(r"--only[= ][^\n]*dataconnect|\bdataconnect:[a-z]", path.read_text()), path.name
