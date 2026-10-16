from __future__ import annotations

import os
import re
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
# Load only reusable fixtures, without re-exporting G's test functions or
# changing sys.path. Each mutable control is newly constructed per test.
_engine_spec = importlib.util.spec_from_file_location(
    "deployment_engine_fixtures", ROOT / "scripts/ci/test_engine_contract_gate.py")
_engine_fixtures = importlib.util.module_from_spec(_engine_spec)
_engine_spec.loader.exec_module(_engine_fixtures)
engine_control = _engine_fixtures.control
gate = _engine_fixtures.gate
phase_control_bytes = _engine_fixtures.phase_control_bytes

WORKFLOW = ROOT / ".github/workflows/ci-cd.yml"
DEPLOY_SCRIPT = ROOT / "scripts/ci/deploy_hosting.sh"
APPROVED_DEPLOY_SCRIPTS = {
    DEPLOY_SCRIPT,
    ROOT / "scripts/release/deploy_api.py",
    ROOT / "scripts/release/deploy_models.py",
    ROOT / "scripts/release/process_worker.py",
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


def retired_tests() -> set[str]:
    """List 2 of the manifest: tests removed with the retired release scripts."""
    section = RETIRED_MANIFEST.read_text().split(
        "\n## 2. Tests of the retired scripts\n", 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"`(test_[a-z0-9_]+\.py)`", section))


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


def test_frontend_only_python_scope_keeps_the_required_gate_and_fails_closed() -> None:
    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    jobs = workflow["jobs"]
    scope, shards, aggregate = jobs["python-scope"], jobs["python-shards"], jobs["python"]

    assert scope["outputs"] == {
        "full": "${{ steps.scope.outputs.full }}",
        "matrix": "${{ steps.shards.outputs.matrix }}",
    }
    checkout = next(step for step in scope["steps"] if step.get("name") == "Check out repository history")
    assert checkout["with"] == {"fetch-depth": "0"}
    classify = next(step for step in scope["steps"] if step.get("id") == "scope")
    assert "python3 scripts/ci/python_scope.py" in classify["run"]
    assert set(classify["env"]) == {"EVENT_NAME", "BASE_SHA", "HEAD_SHA"}

    assert shards["needs"] == "python-scope"
    assert shards["if"] == "needs.python-scope.outputs.full == 'true'"
    assert aggregate["if"] == "always()"
    assert aggregate["needs"] == ["python-scope", "python-shards", "python-engines"]

    validation = next(step for step in aggregate["steps"]
                      if step.get("name") == "Require a valid scope decision")
    assert set(validation["env"]) == {"SCOPE_RESULT", "FULL_PYTHON", "SHARD_RESULT", "ENGINE_RESULT"}
    assert 'test "$ENGINE_RESULT" = success' in validation["run"]
    assert 'test "$SCOPE_RESULT" = success' in validation["run"]
    assert 'true) test "$SHARD_RESULT" = success' in validation["run"]
    assert 'false) test "$SHARD_RESULT" = skipped' in validation["run"]

    focused = next(step for step in aggregate["steps"]
                   if step.get("name") == "Run focused frontend Python contracts")
    assert focused["if"] == "needs.python-scope.outputs.full == 'false'"
    focused_paths = (
        "scripts/ci/test_public_settings.py",
        "scripts/ci/test_smoke_web_routes.py",
        "tests/test_deployment_policy.py",
        "tests/test_hosting_attempt_binding.py",
        "tests/test_local_review_runner.py",
        "tests/research_harness/test_thread_embedded_schema.py",
    )
    for path in focused_paths:
        assert path in focused["run"]

    # A Python test that resolves this repository and names the Flutter tree
    # is a cross-language contract. Keep every such test in the focused gate;
    # otherwise a frontend-only change could break it while reporting green.
    references = set()
    for directory in (ROOT / "tests", ROOT / "scripts"):
        for path in directory.rglob("test_*.py"):
            source = path.read_text(encoding="utf-8")
            names_flutter_tree = (
                "apps/specimen_digitization" in source
                or re.search(r'["\']apps["\']\s*/\s*["\']specimen_digitization["\']', source)
            )
            if "Path(__file__)" in source and names_flutter_tree:
                references.add(str(path.relative_to(ROOT)))
    assert references <= set(focused_paths)
    for name in ("Download Python results", "Verify complete Python coverage"):
        step = next(step for step in aggregate["steps"] if step.get("name") == name)
        assert step["if"] == "needs.python-scope.outputs.full == 'true'"

    writing = next(step for step in jobs["flutter"]["steps"] if step.get("name") == "Check UI writing")
    assert "scripts/ci/check_ui_strings.py" in writing["run"]


def hosting_workflow(path: Path = WORKFLOW) -> dict:
    return yaml.safe_load(path.read_text())


def workflow_step(job: dict, name: str) -> dict:
    return next(step for step in job["steps"] if step.get("name") == name)


def workflow_shell(command: str, *, env: dict, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-e", "-o", "pipefail", "-c", command],
                          cwd=cwd, env={**os.environ, **env}, capture_output=True,
                          text=True, timeout=10)


def hosted_matrix(workflow: dict, output: Path) -> subprocess.CompletedProcess:
    step = next(step for step in workflow["jobs"]["python-scope"]["steps"]
                if step.get("id") == "shards")
    return workflow_shell(step["run"], env={
        "PYTHON_HOSTED_SHARDS": str(workflow["env"]["PYTHON_HOSTED_SHARDS"]),
        "GITHUB_OUTPUT": str(output),
    })


def command_arguments(command: str, count: int) -> list[str]:
    # Expand the actual shell arguments without launching a shard or collecting tests.
    result = workflow_shell('set -- ' + command + '\nprintf "%s\\0" "$@"',
                            env={"PYTHON_HOSTED_SHARDS": str(count)})
    assert result.returncode == 0, result.stderr
    return result.stdout.rstrip("\0").split("\0")


@pytest.mark.parametrize("count", [6, 8, 10, 12, 16])
def test_one_hosted_count_controls_matrix_leaves_and_verify(tmp_path: Path, count: int) -> None:
    source = WORKFLOW.read_text()
    configured = hosting_workflow()["env"]["PYTHON_HOSTED_SHARDS"]
    assert type(configured) is int and 6 <= configured <= 16
    # A single scalar edit in a real temporary workflow copy must change all three consumers.
    changed, replacements = re.subn(r"(?m)^  PYTHON_HOSTED_SHARDS: .*?$",
                                    f"  PYTHON_HOSTED_SHARDS: {count}", source)
    assert replacements == 1, "hosted shard count must have exactly one definition"
    copy = tmp_path / "ci-cd.yml"
    copy.write_text(changed)
    workflow = hosting_workflow(copy)
    output = tmp_path / "outputs"
    result = hosted_matrix(workflow, output)
    assert result.returncode == 0, result.stderr
    outputs = dict(line.split("=", 1) for line in output.read_text().splitlines())
    matrix = json.loads(outputs["matrix"])
    assert matrix == list(range(count))
    scope = workflow["jobs"]["python-scope"]
    assert scope["outputs"]["matrix"] == "${{ steps.shards.outputs.matrix }}"
    shards = workflow["jobs"]["python-shards"]
    assert shards["strategy"]["matrix"] == {
        "shard": "${{ fromJSON(needs.python-scope.outputs.matrix) }}"}
    run = workflow_step(shards, "Run Python tests")["run"]
    for index in matrix:
        arguments = command_arguments(run.replace("${{ matrix.shard }}", str(index)), count)
        assert arguments == ["uv", "run", "python", "scripts/ci/python_shards.py", "run",
                             "--index", str(index), "--count", str(count),
                             "--output", f"python-shards/shard-{index}.json"]
    verify = workflow_step(workflow["jobs"]["python"], "Verify complete Python coverage")["run"]
    assert command_arguments(verify.splitlines()[-1], count) == [
        "python3", "scripts/ci/python_shards.py", "verify", "--count", str(count),
        "python-shards/shard-*.json"]
    local = (ROOT / "scripts/ci/verify.sh").read_text()
    assert 'python_shards.py local --count "${PYTHON_TEST_SHARDS:-6}"' in local
    assert "PYTHON_HOSTED_SHARDS" not in local


@pytest.mark.parametrize("value", ["5", "17", "0", "-1", "6.0", "true", "null",
                                  '"10"', "[]", "{}", "not-an-integer", ""])
def test_hosted_count_rejects_out_of_range_and_nonintegers(tmp_path: Path, value: str) -> None:
    workflow = hosting_workflow()
    workflow["env"]["PYTHON_HOSTED_SHARDS"] = value
    output = tmp_path / "outputs"
    result = hosted_matrix(workflow, output)
    assert result.returncode != 0, f"invalid hosted count accepted: {value!r}"
    assert not output.exists() or not output.read_text(), "invalid count emitted a matrix"


def test_hosting_required_names_dependencies_and_attempt_binding_are_exact() -> None:
    workflow = hosting_workflow()
    jobs = workflow["jobs"]
    assert set(jobs) == {"repository-checks", "python-scope", "python-shards", "python",
                         "python-engines", "flutter", "mobile", "deploy-hosting"}
    assert {key: jobs[key]["name"] for key in ("repository-checks", "python", "flutter")} == {
        "repository-checks": "Repository checks", "python": "Python tests",
        "flutter": "Flutter checks and web build"}
    assert jobs["deploy-hosting"]["needs"] == ["repository-checks", "python", "flutter", "mobile"]
    assert workflow["concurrency"] == {
        "group": "ci-cd-${{ github.workflow }}-${{ github.ref }}",
        "cancel-in-progress": "${{ github.event_name == 'pull_request' }}"}
    assert jobs["deploy-hosting"]["concurrency"] == {
        "group": "firebase-hosting-production", "cancel-in-progress": False}
    shards, aggregate = jobs["python-shards"], jobs["python"]
    assert shards["name"] == "Python shard ${{ matrix.shard }}"
    assert shards["strategy"]["fail-fast"] is False
    upload = workflow_step(shards, "Upload Python results")
    download = workflow_step(aggregate, "Download Python results")
    binding = "python-tests-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}-"
    assert upload["if"] == "always()"
    assert upload["with"] == {"name": binding + "${{ matrix.shard }}",
                              "path": "python-shards/shard-${{ matrix.shard }}.json",
                              "if-no-files-found": "error", "retention-days": 7}
    assert download["with"] == {"pattern": binding + "*", "path": "python-shards",
                                "merge-multiple": True}
    pins = {step["uses"] for job in jobs.values() for step in job["steps"] if "uses" in step}
    assert pins == {
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
        "subosito/flutter-action@1a449444c387b1966244ae4d4f8c696479add0b2",
        "google-github-actions/auth@7c6bc770dae815cd3e89ee6cdf493a5fab2cc093",
        "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020",
        "actions/cache@0400d5f644dc74513175e3cd8d07132dd4860809",
    }
    assert all("continue-on-error" not in job and all("continue-on-error" not in step
               for step in job["steps"]) for job in jobs.values())


@pytest.mark.parametrize("scope_result", ["success", "failure", "cancelled", "skipped", ""])
@pytest.mark.parametrize("full", ["true", "false", "", "TRUE"])
@pytest.mark.parametrize("shard_result", ["success", "failure", "cancelled", "skipped", ""])
@pytest.mark.parametrize("engine_result", ["success", "failure", "skipped", "cancelled", ""])
def test_python_aggregate_scope_and_shard_truth_table(scope_result: str, full: str,
                                                    shard_result: str, engine_result: str) -> None:
    aggregate = hosting_workflow()["jobs"]["python"]
    assert aggregate["if"] == "always()"
    assert aggregate["needs"] == ["python-scope", "python-shards", "python-engines"]
    step = workflow_step(aggregate, "Require a valid scope decision")
    assert step["env"] == {"SCOPE_RESULT": "${{ needs.python-scope.result }}",
                           "FULL_PYTHON": "${{ needs.python-scope.outputs.full }}",
                           "SHARD_RESULT": "${{ needs.python-shards.result }}",
                           "ENGINE_RESULT": "${{ needs.python-engines.result }}"}
    result = workflow_shell(step["run"], env={"SCOPE_RESULT": scope_result,
                            "FULL_PYTHON": full, "SHARD_RESULT": shard_result,
                            "ENGINE_RESULT": engine_result})
    accepted = scope_result == "success" and engine_result == "success" and (full, shard_result) in {
        ("true", "success"), ("false", "skipped")}
    assert (result.returncode == 0) == accepted, (scope_result, full, shard_result, engine_result, result.stderr)


ENGINE_BINDING = "python-tests-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}-engines"
ENGINE_VERIFY = ("python3 scripts/ci/engine_contract_gate.py verify "
                 "--selection scripts/data/engine-contract-selection.json --results python-shards")


def test_engine_job_is_parallel_and_required_for_both_scopes() -> None:
    workflow = hosting_workflow()
    jobs = workflow["jobs"]
    assert "python-engines" in jobs, "mandatory parallel engine job is missing"
    engines, aggregate = jobs["python-engines"], jobs["python"]
    assert engines["name"] == "SQL and Storage engine contracts"
    assert engines["runs-on"] == "ubuntu-24.04"
    assert engines["timeout-minutes"] == 10
    assert "needs" not in engines and "if" not in engines
    assert engines["permissions"] == {"contents": "read"}
    assert "environment" not in engines and "secrets." not in str(engines)
    assert "id-token" not in str(engines) and not any(is_sign_in(s) for s in engines["steps"])
    checkout = workflow_step(engines, "Check out repository")
    assert checkout["uses"] == "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
    assert checkout["with"] == {"persist-credentials": False}
    setup = workflow_step(engines, "Install uv and Python")
    assert setup["uses"] == "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d"
    assert setup["with"] == {"version": "${{ env.UV_VERSION }}", "enable-cache": True, "python-version": "3.12"}
    assert workflow_step(engines, "Install locked dependencies")["run"] == "uv sync --frozen"
    assert not any("setup-node@" in s.get("uses", "") or "setup-java@" in s.get("uses", "")
                   for s in engines["steps"])
    runtime = workflow_step(engines, "Select pinned runner tools")["run"]
    for required in ("node/22.23.3/x64/bin", 'test "$(node --version)" = v22.23.3',
                     'test "$(npm --version)" = 10.9.9', "JAVA_HOME_21_X64", "/usr/lib/postgresql/16/bin"):
        assert required in runtime
    assert not re.search(r"apt-get|brew |npm (?:ci|install)|npx ", str(engines))
    provision = workflow_step(engines, "Provision verified engine files")
    assert "provision-engine-tools.py" in provision["run"] and "--download" in provision["run"]
    assert "if" not in provision
    run = workflow_step(engines, "Run mandatory engine contracts")
    assert "if" not in run
    assert run["run"] == (
        "uv run python scripts/ci/engine_contract_gate.py record "
        "--selection scripts/data/engine-contract-selection.json --results python-engines "
        "-- bash -euo pipefail -c 'scripts/data/test-postgres.sh; scripts/data/test-storage.sh'")
    assert engines["env"] == {"SPECIMEN_TEST_SQL_EMULATOR": "true", "PYTHONDONTWRITEBYTECODE": "1"}
    upload = workflow_step(engines, "Upload engine result")
    assert upload["uses"] == "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
    assert upload["if"] == "always()"
    assert upload["with"] == {"name": ENGINE_BINDING, "path": "python-engines/engine-contract.json",
                               "if-no-files-found": "error", "retention-days": 7}
    verify = workflow_step(aggregate, "Verify mandatory engine evidence")
    assert "if" not in verify and verify["run"] == ENGINE_VERIFY
    assert verify["env"] == {"ENGINE_CACHE_MODE": "${{ github.event_name == 'workflow_dispatch' && inputs.engine_cache_mode || 'normal' }}"}
    focused = workflow_step(aggregate, "Download engine result for focused contracts")
    assert focused["uses"] == "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c"
    assert focused["if"] == "needs.python-scope.outputs.full == 'false'"
    assert focused["with"] == {"name": ENGINE_BINDING, "path": "python-shards"}
    names = [s["name"] for s in aggregate["steps"]]
    assert names.index("Download Python results") < names.index(verify["name"])
    assert names.index(focused["name"]) < names.index(verify["name"])
    assert names.index(verify["name"]) < names.index("Run focused frontend Python contracts")
    # Existing job budgets, shard scalar, permissions and production boundary stay exact.
    assert workflow["env"]["PYTHON_HOSTED_SHARDS"] == 12
    assert {key: jobs[key]["timeout-minutes"] for key in jobs if key != "python-engines"} == {
        "repository-checks": 15, "python-scope": 5, "python-shards": 90, "python": 15,
        "flutter": 30, "mobile": 45, "deploy-hosting": 15}
    assert workflow["permissions"] == {"contents": "read"}
    for step in engines["steps"]:
        assert "continue-on-error" not in step
        if "uses" in step:
            assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", step["uses"])


@pytest.fixture
def engine_workflow_fixture(engine_control, gate, tmp_path, monkeypatch):
    """Real stdlib verifier in a small checkout; only Git's identity transport is synthetic.

    Reuse G's immutable phase report and valid lifecycle control, then independently
    bind the scratch inventory. No engine, server, credential or download is used.
    """
    result, _, selection, root, env = engine_control
    cli = root / "scripts/ci/engine_contract_gate.py"
    cli.parent.mkdir(parents=True)
    cli.write_bytes((ROOT / "scripts/ci/engine_contract_gate.py").read_bytes())
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    binary = root / "git-bin"
    binary.mkdir()
    fake_git = binary / "git"
    fake_git.write_text(f"#!{sys.executable}\nimport sys\nargs=sys.argv[3:]\n"
                        f"answers={{('rev-parse','HEAD'):{'a' * 40!r},"
                        f"('ls-files','-z'):{chr(0).join(files) + chr(0)!r},"
                        "('diff','--name-only','HEAD'):''}\n"
                        "sys.stdout.write(answers[tuple(args)])\n")
    fake_git.chmod(0o700)
    def git_transport(_root, *args):
        return subprocess.check_output([str(fake_git), "-C", str(root), *args], text=True).strip("\n")
    monkeypatch.setattr(gate, "git", git_transport)
    expected = gate.expected_context(root, root / "scripts/data/engine-contract-selection.json", env)
    result["context_start"] = dict(expected)
    result["context_end"] = dict(expected)
    gate.validate(result, expected, selection)
    return root, result, {**env, "PATH": str(binary) + os.pathsep + os.environ["PATH"]}


@pytest.mark.parametrize("full", ["true", "false"], ids=["full", "focused"])
@pytest.mark.parametrize("fault", ["none", "missing", "old_attempt", "old_sha", "wrong_run",
                                  "wrong_config", "partial", "all_skipped", "cleanup_failed"])
def test_python_aggregate_rejects_engine_artifact_fault(engine_workflow_fixture, full, fault) -> None:
    root, result, env = engine_workflow_fixture
    aggregate = hosting_workflow()["jobs"]["python"]
    decision = workflow_step(aggregate, "Require a valid scope decision")
    checked = workflow_shell(decision["run"], cwd=root, env={**env, "SCOPE_RESULT": "success",
                             "FULL_PYTHON": full, "SHARD_RESULT": "success" if full == "true" else "skipped",
                             "ENGINE_RESULT": "success"})
    assert checked.returncode == 0, checked.stderr
    verifier = workflow_step(aggregate, "Verify mandatory engine evidence")
    assert "if" not in verifier, "engine verification must also run for focused scope"
    directory = root / "python-shards"
    directory.mkdir()
    if fault in ("old_attempt", "old_sha", "wrong_run", "wrong_config"):
        field, value = {"old_attempt": ("run_attempt", "1"), "old_sha": ("source_sha", "b" * 40),
                        "wrong_run": ("run_id", "41"), "wrong_config": ("config_digest", "0" * 64)}[fault]
        for context in ("context_start", "context_end"):
            result[context][field] = value
    elif fault == "all_skipped":
        for event in result["pytest"]["events"]:
            event["outcome"] = "skipped"
    elif fault == "cleanup_failed":
        result["lifecycle"]["cleanup"]["outcome"] = "failed"
    name = "engine-contract.json.partial" if fault == "partial" else "engine-contract.json"
    if fault != "missing":
        (directory / name).write_text(json.dumps(result))
    checked = workflow_shell(verifier["run"], cwd=root, env=env)
    assert (checked.returncode == 0) == (fault == "none"), checked.stdout + checked.stderr
    if fault == "none":
        assert "mandatory engine contract evidence verified" in checked.stdout
    else:
        assert "engine contract gate:" in checked.stderr
        assert "Traceback" not in checked.stderr, "a verifier crash is not an intended rejection"


@pytest.mark.parametrize("scenario", ["normal", "cold", "unknown", "push_cold", "pr_cold"])
def test_engine_cache_mode_changes_only_provisioning(tmp_path, scenario) -> None:
    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    assert workflow["on"]["workflow_dispatch"]["inputs"] == {"engine_cache_mode": {
        "description": "Engine file cache provisioning only", "type": "choice", "default": "normal",
        "options": ["normal", "cold"]}}
    job = workflow["jobs"]["python-engines"]
    select = workflow_step(job, "Select engine cache mode")
    assert select["env"] == {"EVENT_NAME": "${{ github.event_name }}",
                             "REQUESTED_MODE": "${{ inputs.engine_cache_mode || 'normal' }}"}
    event = "push" if scenario == "push_cold" else "pull_request" if scenario == "pr_cold" else "workflow_dispatch"
    requested = "cold" if scenario in ("cold", "push_cold", "pr_cold") else scenario
    output, exported = tmp_path / "outputs", tmp_path / "environment"
    checked = workflow_shell(select["run"], env={"EVENT_NAME": event, "REQUESTED_MODE": requested,
        "RUNNER_TEMP": str(tmp_path), "GITHUB_OUTPUT": str(output), "GITHUB_ENV": str(exported)})
    assert (checked.returncode == 0) == (scenario != "unknown"), checked.stderr
    if scenario == "unknown":
        assert not output.exists() and not exported.exists(), "unknown cache mode emitted usable configuration"
        return
    values = dict(line.split("=", 1) for line in exported.read_text().splitlines())
    outputs = dict(line.split("=", 1) for line in output.read_text().splitlines())
    mode = "cold" if scenario == "cold" else "normal"
    assert values["ENGINE_CACHE_MODE"] == outputs["mode"] == mode
    directory = Path(values["ENGINE_TOOLS_DIR"])
    assert str(directory) == outputs["directory"]
    assert not directory.exists(), "provisioner must receive an unseeded engine directory"
    spec = importlib.util.spec_from_file_location("workflow_provision", ROOT / "scripts/data/provision-engine-tools.py")
    provisioner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(provisioner)
    evidence = provisioner.prepare_directory(directory, mode=mode, event=event,
                                             restore="bypassed" if mode == "cold" else "miss")
    assert list(directory.iterdir()) == [] and directory.stat().st_mode & 0o777 == 0o700
    assert evidence == {"mode": mode, "directory_private": True, "directory_fresh": True,
                        "entries_before": 0, "restore": "bypassed" if mode == "cold" else "miss"}
    if mode == "cold":
        assert directory.parent.stat().st_mode & 0o777 == 0o700
        with pytest.raises(ValueError, match="new nonexistent directory"):
            provisioner.prepare_directory(directory, mode=mode, event=event, restore="bypassed")
    cache = workflow_step(job, "Cache verified engine files")
    assert cache["if"] == "steps.engine-cache.outputs.mode == 'normal'"
    assert cache["uses"] == "actions/cache@0400d5f644dc74513175e3cd8d07132dd4860809"
    assert cache["with"] == {"path": "${{ steps.engine-cache.outputs.directory }}",
        "key": "engine-tools-${{ runner.os }}-${{ runner.arch }}-${{ hashFiles('scripts/data/engine-toolchain.json') }}"}
    # One combined restore/save action, and no cold condition around any assertion,
    # lifecycle, inventory, tool-byte verification, record or upload operation.
    assert [s for s in job["steps"] if s.get("uses", "").startswith("actions/cache")] == [cache]
    assert {s["name"] for s in job["steps"] if "if" in s} == {"Cache verified engine files", "Upload engine result"}
    provision = workflow_step(job, "Provision verified engine files")
    assert provision["env"] == {"CACHE_HIT": "${{ steps.engine-files.outputs.cache-hit }}"}
    # Execute the real provisioning shell using an argv-only spy: never download.
    binary = tmp_path / "bin"
    binary.mkdir()
    spy = binary / "python3"
    spy.write_text(f"#!{sys.executable}\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n")
    spy.chmod(0o700)
    for hit in ("", "false", "true", "invalid"):
        checked = workflow_shell(provision["run"], env={**values, "CACHE_HIT": hit,
            "PATH": str(binary) + os.pathsep + os.environ["PATH"]})
        accepted = hit in ("", "false") if mode == "cold" else hit != "invalid"
        assert (checked.returncode == 0) == accepted, checked.stderr
        if accepted:
            restore = "bypassed" if mode == "cold" else "hit" if hit == "true" else "miss"
            assert checked.stdout.strip(), "provisioning bypassed verified engine bytes"
            assert json.loads(checked.stdout) == ["scripts/data/provision-engine-tools.py", "--download",
                "--directory", str(directory), "--mode", mode, "--restore", restore,
                "--output", values["ENGINE_PROVISION_REPORT"]]


@pytest.mark.parametrize("fault", ["none", "missing", "stale_attempt", "failed", "wrong_count"])
def test_python_aggregate_verifies_current_attempt_artifacts(tmp_path: Path, fault: str) -> None:
    # Run the workflow's real verifier against complete synthetic schema-2 leaves.
    # No pytest collection, leaf execution or network call occurs here.
    workflow = hosting_workflow()
    count = workflow["env"]["PYTHON_HOSTED_SHARDS"]
    script = ROOT / "scripts/ci/python_shards.py"
    spec = importlib.util.spec_from_file_location("deployment_shards", script)
    shards = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shards)
    directory = tmp_path / "scripts/ci"
    directory.mkdir(parents=True)
    (directory / script.name).write_bytes(script.read_bytes())
    timing_path = directory / "python_shard_timings.json"
    timing_path.write_text(json.dumps({"schema": 1, "module_seconds": {}}))
    timings = shards.load_timings(timing_path)
    sources = shards.source_fingerprints(tmp_path)
    identity = {"GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2"}
    nodes = [f"tests/test_module_{index}.py::test_case" for index in range(count)]
    results_dir = tmp_path / "python-shards"
    results_dir.mkdir()
    for index, selected in enumerate(shards.partition(nodes, count, timings)):
        if fault == "missing" and index == count - 1:
            continue
        result = {"schema": 2, "identity": dict(identity), "index": index, "count": count,
                  "collected": nodes, "selected": selected, "collection_errors": 0, "exitstatus": 0,
                  "inventory_digest": shards.digest(nodes), "source_fingerprints": sources,
                  "timing_manifest_digest": timings.manifest_digest, "timing_mode": timings.mode,
                  "telemetry": {"collection_seconds": 0.1, "execution_seconds": 0.2},
                  "reports": {node: dict.fromkeys(("setup", "call", "teardown"), "passed")
                              for node in selected},
                  "durations": {node: dict.fromkeys(("setup", "call", "teardown"), 0.01)
                                for node in selected}}
        if index == 0:
            if fault == "stale_attempt":
                result["identity"]["GITHUB_RUN_ATTEMPT"] = "1"
            elif fault == "failed":
                result["exitstatus"] = 1
            elif fault == "wrong_count":
                result["count"] = count + 1
        (results_dir / f"shard-{index}.json").write_text(json.dumps(result))
    step = workflow_step(workflow["jobs"]["python"], "Verify complete Python coverage")
    assert step["if"] == "needs.python-scope.outputs.full == 'true'"
    assert step["env"] == {"SHARD_RESULT": "${{ needs.python-shards.result }}"}
    checked = workflow_shell(step["run"], cwd=tmp_path, env={
        **identity, "SHARD_RESULT": "success", "PYTHON_HOSTED_SHARDS": str(count)})
    assert (checked.returncode == 0) == (fault == "none"), checked.stdout + checked.stderr
    if fault == "none":
        assert f"exactly once across {count} shards" in checked.stdout
    else:
        assert "Python shard verification failed:" in checked.stderr


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


def test_readme_marks_linked_go_live_documents_as_retired_history() -> None:
    readme = (ROOT / "README.md").read_text()
    assert "Historical records only (retired; do not follow their commands)" in readme

    for relative in (
        "docs/execution/GO_LIVE_READINESS.md",
        "docs/execution/GO_LIVE_RUNBOOK.md",
    ):
        document = (ROOT / relative).read_text()
        opening = "\n".join(document.splitlines()[:12])
        assert "RETIRED — historical record only" in opening
        assert "Do not follow commands or" in opening
        assert "scripts/ops/owner_setup.sh" in opening
        assert "scripts/ci/RETIRED.md" in opening


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
    assert not [name for name in scripts if (ROOT / "scripts/ci" / name).exists()]
    assert not [path for name in actions for path in (ROOT / name).rglob("*") if path.is_file()]
    tests = retired_tests()
    assert len(tests) == 56
    assert not [name for name in tests if (ROOT / "scripts/ci" / name).exists()]
    assert not (ROOT / "scripts/ci/fixtures/publication_auth_transport.cjs").exists()
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
