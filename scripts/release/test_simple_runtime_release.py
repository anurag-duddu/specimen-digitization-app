"""The simple runtime release: the workflow's shape, the deploy command, and the shell steps run against
stand-in gh, docker, gcloud and curl commands. No network and no cloud call."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))
import deploy_api  # noqa: E402
import runtime_settings  # noqa: E402  (deploy_api puts scripts/ci on the path)

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / ".github/workflows/runtime-release.yml").read_text()
WORKFLOW = yaml.load(TEXT, Loader=yaml.BaseLoader)
JOBS = WORKFLOW["jobs"]
MAIN = "github.ref == 'refs/heads/main'"
PROVIDERS = "projects/716045864126/locations/global/workloadIdentityPools/github-actions/providers"  # pragma: allowlist secret (public provider path)
SHA = "a" * 40
IMAGE = "us-east4-docker.pkg.dev/specimen-digitization/specimen-runtime/api"
DIGEST = f"{IMAGE}@sha256:{'b' * 64}"
TAG = f"{IMAGE}:sha-{SHA}-123-2"
URL = "https://specimen-api-abc123-uk.a.run.app"
HINT = "public access is not set: the owner runs scripts/ops/owner_setup.sh once"
TOKEN = "synthetic-access-token"
PUBLIC = {"bindings": [{"role": "roles/run.invoker", "members": ["allUsers"]}]}

# Each stand-in logs its arguments. answer KEY prints $FAKE/KEY.<call number>, else $FAKE/KEY.last;
# with neither file it fails, which plays a failed command.
PRELUDE = r'''#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE/$(basename "$0").args"
answer() {
  local count file
  count=$(( $(cat "$FAKE/$1.count" 2>/dev/null || printf 0) + 1 ))
  printf '%s' "$count" > "$FAKE/$1.count"
  file="$FAKE/$1.$count"
  [[ -f "$file" ]] || file="$FAKE/$1.last"
  [[ -f "$file" ]] && cat "$file"
}
'''
FAKES = {
    "gh": "answer gh\n",
    "docker": r'''case "$1" in
  login) cat > "$FAKE/docker.stdin" ;;
  push) [[ ! -e "$FAKE/push.fails" ]] ;;
  image) cat "$FAKE/digests" ;;
esac
''',
    "gcloud": r'''printf '%s %s\n' "${CLOUDSDK_CORE_DISABLE_PROMPTS:-unset}" "${CLOUDSDK_CORE_SHOULD_PROMPT_TO_ENABLE_API:-unset}" >> "$FAKE/gcloud.env"
case "$*" in
  "auth print-access-token") cat "$FAKE/token" ;;
  "run deploy specimen-api "*)
    while (($#)); do
      if [[ "$1" == "--env-vars-file" ]]; then cp "$2" "$FAKE/env.yaml"; fi
      shift
    done
    [[ ! -e "$FAKE/deploy.fails" ]] ;;
  "run services get-iam-policy "*) cat "$FAKE/policy" ;;
  "run services add-iam-policy-binding "*) [[ ! -e "$FAKE/binding.fails" ]] ;;
  "run services describe "*) cat "$FAKE/url" ;;
esac
''',
    # A reply file holds the HTTP status on its first line and the body after it.
    "curl": r'''while (($#)); do
  case "$1" in
    --output) out="$2"; shift 2 ;;
    --max-time|--write-out) shift 2 ;;
    --*) shift ;;
    *) url="$1"; shift ;;
  esac
done
reply="$(answer "$(basename "$url")")"
printf '%s' "${reply#*$'\n'}" > "$out"
printf '%s' "${reply%%$'\n'*}"
''',
}


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """Stand-in commands first on PATH; the returned directory holds their answers and their logs."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in FAKES.items():
        (bin_dir / name).write_text(PRELUDE + body)
        (bin_dir / name).chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv("SMOKE_URL", raising=False)
    for name, value in {"FAKE": tmp_path, "POLL_SECONDS": 0, "GITHUB_SHA": SHA, "GITHUB_RUN_ID": 123,
                        "GITHUB_RUN_ATTEMPT": 2, "GITHUB_REPOSITORY": "owner/repo",
                        "GITHUB_OUTPUT": tmp_path / "output"}.items():
        monkeypatch.setenv(name, str(value))
    (tmp_path / "token").write_text(TOKEN + "\n")
    (tmp_path / "url").write_text(URL + "\n")
    (tmp_path / "policy").write_text("{}")
    return tmp_path


def script(name, *args):
    return subprocess.run(["bash", str(ROOT / "scripts/release" / name), *args], capture_output=True, text=True, timeout=120)


def lines(fake, name):
    return (fake / name).read_text().splitlines() if (fake / name).exists() else []


def flag(command, name):
    return command[command.index(name) + 1]


def steps(job):
    """Each step as its action without the version, or its command."""
    return [step["uses"].split("@")[0] if "uses" in step else step["run"] for step in JOBS[job]["steps"]]


# --- the workflow ---

def test_a_push_to_main_or_a_manual_run_starts_the_release_and_one_runs_at_a_time():
    assert set(WORKFLOW["on"]) == {"push", "workflow_dispatch"}
    assert WORKFLOW["on"]["push"] == {"branches": ["main"]}
    assert WORKFLOW["permissions"] == {"contents": "read"}
    assert WORKFLOW["concurrency"] == {"group": "specimen-runtime-release", "cancel-in-progress": "false"}


def test_only_main_releases_and_the_release_needs_both_the_data_release_and_the_image():
    assert list(JOBS) == ["data", "build", "release"]
    assert JOBS["data"]["if"] == MAIN and JOBS["build"]["if"] == MAIN
    # The image builds while the data release runs; neither waits for the other.
    assert "needs" not in JOBS["data"] and "needs" not in JOBS["build"]
    assert JOBS["release"]["needs"] == ["data", "build"]
    assert JOBS["data"]["timeout-minutes"] == "45"


def test_every_action_is_pinned_to_a_full_commit_sha():
    used = re.findall(r"\buses:\s*(\S+)", TEXT)
    assert len(used) == 6
    assert all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", action) for action in used)


def test_only_the_build_and_the_release_get_cloud_credentials_each_in_its_own_environment():
    assert JOBS["data"]["permissions"] == {"contents": "read", "actions": "read"}
    assert "environment" not in JOBS["data"]
    assert [name for name, job in JOBS.items() if job["permissions"].get("id-token") == "write"] == ["build", "release"]
    assert JOBS["build"]["permissions"] == JOBS["release"]["permissions"] == {"contents": "read", "id-token": "write"}
    assert JOBS["build"]["environment"] == "runtime-build-production"
    assert JOBS["release"]["environment"] == "runtime-production"
    auth = {name: [step["with"] for step in job["steps"] if step.get("uses", "").startswith("google-github-actions/auth@")]
            for name, job in JOBS.items()}
    assert auth == {"data": [], "build": [{
        "project_id": "specimen-digitization", "workload_identity_provider": f"{PROVIDERS}/specimen-runtime-build",
        "service_account": "specimen-runtime-build@specimen-digitization.iam.gserviceaccount.com"}], "release": [{
            "project_id": "specimen-digitization", "workload_identity_provider": f"{PROVIDERS}/specimen-runtime-release",
            "service_account": "specimen-runtime-release@specimen-digitization.iam.gserviceaccount.com"}]}
    providers = [line for line in TEXT.splitlines() if "workload_identity_provider:" in line]
    assert len(providers) == 2 and all(line.endswith("# pragma: allowlist secret") for line in providers)


def test_each_job_runs_exactly_its_reviewed_steps_and_the_yaml_only_calls_scripts():
    assert steps("data") == ["actions/checkout", "scripts/release/wait_for_data.sh"]
    assert steps("build") == ["actions/checkout", "google-github-actions/auth", "scripts/ci/build_runtime_image.sh api",
                              "scripts/release/push_image.sh api"]
    assert steps("release") == ["actions/checkout", "astral-sh/setup-uv", "uv sync --frozen", "google-github-actions/auth",
                                'uv run python scripts/release/deploy_api.py "$IMAGE"', "scripts/release/smoke_api.sh"]
    for name in ("wait_for_data.sh", "push_image.sh", "smoke_api.sh"):
        path = ROOT / "scripts/release" / name
        assert os.access(path, os.X_OK) and "set -euo pipefail" in path.read_text()
    assert "allow-unauthenticated" not in TEXT and "secrets." not in TEXT and "vars." not in TEXT


def test_the_image_digest_and_the_github_token_reach_only_the_steps_that_use_them():
    assert JOBS["build"]["outputs"] == {"image": "${{ steps.push.outputs.image }}"}
    env = {job: [step.get("env", {}) for step in JOBS[job]["steps"]] for job in JOBS}
    assert all("env" not in JOBS[job] for job in JOBS) and "env" not in WORKFLOW
    assert env["data"] == [{}, {"GH_TOKEN": "${{ github.token }}"}]
    assert env["build"] == [{}, {}, {}, {}]
    assert env["release"] == [{}, {}, {}, {}, {"IMAGE": "${{ needs.build.outputs.image }}"}, {}]
    assert [step.get("id") for step in JOBS["build"]["steps"]] == [None, None, None, "push"]
    # No cloud token passes through the YAML: push_image.sh asks gcloud for one from the sign-in step's credential file.
    assert "token_format" not in TEXT and "access_token" not in TEXT and "REGISTRY_TOKEN" not in TEXT
    assert all(step["with"] == {"persist-credentials": "false"}
               for job in JOBS.values() for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@"))


# --- deploy_api.py ---

def test_the_deploy_command_comes_from_the_committed_settings_and_never_touches_access():
    api = runtime_settings.API
    command = deploy_api.deploy_command(DIGEST, SHA, "123", "2", Path("/tmp/release/api-env.yaml"))
    assert command[:4] == ["gcloud", "run", "deploy", "specimen-api"]
    assert not any("allow-unauthenticated" in argument for argument in command)
    assert flag(command, "--image") == DIGEST
    assert flag(command, "--service-account") == api["service_account"] \
        == "specimen-api-runtime@specimen-digitization.iam.gserviceaccount.com"
    assert (flag(command, "--region"), flag(command, "--project")) == ("us-east4", "specimen-digitization")
    assert [flag(command, name) for name in ("--cpu", "--memory", "--max-instances", "--concurrency", "--timeout")] \
        == [api["cpu"], api["memory"], str(api["max_instances"]), str(api["concurrency"]), str(api["timeout_seconds"])]
    assert [flag(command, name) for name in ("--platform", "--ingress", "--port", "--min-instances",
                                             "--execution-environment")] == ["managed", "all", "8080", "0", "gen2"]
    assert {"--quiet", "--cpu-throttling", "--no-cpu-boost"} <= set(command)
    assert flag(command, "--labels") == f"source-sha={SHA},release-run=123"
    assert flag(command, "--env-vars-file") == "/tmp/release/api-env.yaml"
    assert all(isinstance(argument, str) for argument in command)


def test_every_secret_is_pinned_to_a_numeric_version_and_never_latest(monkeypatch):
    pairs = flag(deploy_api.deploy_command(DIGEST, SHA, "123", "2", Path("env.yaml")), "--set-secrets").split(",")
    assert pairs == deploy_api.secret_flag().split(",") and "latest" not in ",".join(pairs)
    assert all(re.fullmatch(r"[A-Z0-9_]+=[a-z0-9-]+:[1-9][0-9]*", pair) for pair in pairs)
    assert {pair.split("=")[0]: pair.split("=")[1].split(":")[0] for pair in pairs} == runtime_settings.API["secret_env"]
    assert all(int(pair.rsplit(":", 1)[1]) == runtime_settings.SECRET_VERSIONS[pair.split("=")[1].split(":")[0]]
               for pair in pairs)
    for unpinned in (None, "latest", "1", 0, True):
        monkeypatch.setitem(runtime_settings.SECRET_VERSIONS, "specimen-source-registry", unpinned)
        with pytest.raises(ValueError, match="pinned numeric version"):
            deploy_api.secret_flag()


def test_the_env_file_holds_every_api_setting_and_the_readiness_generation_as_yaml_strings(monkeypatch):
    values = yaml.safe_load(deploy_api.env_file_text())
    assert values == deploy_api.api_env()
    assert set(values) == {*runtime_settings.API["env"], "SPECIMEN_READINESS_GENERATION"}
    assert values["SPECIMEN_READINESS_GENERATION"] == str(runtime_settings.READINESS_GENERATION)
    # "true" and "1.0" must stay strings, and no secret is written as a plain value.
    assert all(isinstance(value, str) for value in values.values())
    assert values["LOGFIRE_SEND_TO_LOGFIRE"] == "true" and values["LOGFIRE_HEAD_SAMPLE_RATE"] == "1.0"
    assert not set(values) & set(runtime_settings.API["secret_env"])
    monkeypatch.setattr(runtime_settings, "READINESS_GENERATION", None)
    with pytest.raises(ValueError, match="READINESS_GENERATION"):
        deploy_api.env_file_text()


def test_the_revision_name_fits_cloud_runs_limits():
    suffix = flag(deploy_api.deploy_command(DIGEST, SHA, "18234567890", "12", Path("env.yaml")), "--revision-suffix")
    assert suffix == f"{SHA[:12]}-18234567890-12"
    assert len(f"specimen-api-{suffix}") <= 63 and re.fullmatch(r"[a-z0-9-]+", suffix)
    with pytest.raises(ValueError, match="not a valid Cloud Run name"):
        deploy_api.revision_suffix(SHA, "1" * 40, "1")


@pytest.mark.parametrize("image", [
    f"{IMAGE}:sha-{SHA}-123-2",  # A tag can move; only a digest names one image.
    f"{IMAGE}:latest@sha256:{'b' * 64}",
    f"us-east4-docker.pkg.dev/specimen-digitization/other-repository/api@sha256:{'b' * 64}",
    f"us-east4-docker.pkg.dev/another-project/specimen-runtime/api@sha256:{'b' * 64}",
    f"us-east4-docker.pkg.dev/specimen-digitization/specimen-runtime/worker@sha256:{'b' * 64}",
    f"docker.io/specimen-digitization/specimen-runtime/api@sha256:{'b' * 64}",
    f"{IMAGE}@sha256:{'b' * 63}", f"{IMAGE}@sha256:{'B' * 64}", f"{DIGEST}\n", f"{DIGEST} --allow-unauthenticated", "",
])
def test_only_this_repositorys_api_digest_is_deployed(image, fake):
    with pytest.raises(ValueError, match="pushed API digest"):
        deploy_api.deploy_command(image, SHA, "123", "2", Path("env.yaml"))
    with pytest.raises(SystemExit, match="not deployed"):
        deploy_api.main(["deploy_api.py", image])
    assert lines(fake, "gcloud.args") == []


@pytest.mark.parametrize("sha, run_id, attempt", [("a" * 39, "123", "2"), ("A" * 40, "123", "2"), (SHA, "", "2"),
                                                  (SHA, "0", "2"), (SHA, "123", "x"), (SHA, "12 3", "2")])
def test_the_deploy_needs_this_runs_commit_and_attempt(sha, run_id, attempt):
    with pytest.raises(ValueError, match="GITHUB_SHA"):
        deploy_api.deploy_command(DIGEST, sha, run_id, attempt, Path("env.yaml"))


def test_a_first_release_deploys_then_makes_the_service_public(fake, capsys):
    deploy_api.main(["deploy_api.py", DIGEST])
    calls = lines(fake, "gcloud.args")
    assert len(calls) == 3 and calls[0].startswith("run deploy specimen-api ") and f"--image {DIGEST} " in calls[0]
    assert f"--revision-suffix {SHA[:12]}-123-2 " in calls[0]
    assert calls[1] == "run services get-iam-policy specimen-api --region us-east4 --project specimen-digitization --format json"
    assert calls[2] == ("run services add-iam-policy-binding specimen-api --region us-east4 --project specimen-digitization "
                        "--member allUsers --role roles/run.invoker --quiet")
    # gcloud read the env file this run wrote, and no call could stop at a prompt.
    assert yaml.safe_load((fake / "env.yaml").read_text()) == deploy_api.api_env()
    assert lines(fake, "gcloud.env") == ["1 false"] * 3
    assert "public access: set" in capsys.readouterr().out


def test_a_later_release_leaves_the_existing_public_binding_alone(fake, capsys):
    (fake / "policy").write_text(json.dumps(PUBLIC))
    (fake / "binding.fails").touch()  # Not reached: the read already shows the binding.
    deploy_api.main(["deploy_api.py", DIGEST])
    assert [call.split()[:3] for call in lines(fake, "gcloud.args")] == [
        ["run", "deploy", "specimen-api"], ["run", "services", "get-iam-policy"]]
    assert "public access: already set" in capsys.readouterr().out


@pytest.mark.parametrize("policy", ["{}", "not json", json.dumps({"bindings": [
    {"role": "roles/run.invoker", "members": ["serviceAccount:worker@example.iam.gserviceaccount.com"]},
    {"role": "roles/run.viewer", "members": ["allUsers"]},
    {"role": "roles/run.invoker", "members": ["allUsers"], "condition": {"expression": "false"}}]})])
def test_a_release_that_cannot_make_the_service_public_fails_with_the_owner_step(fake, policy):
    (fake / "policy").write_text(policy)
    (fake / "binding.fails").touch()
    with pytest.raises(SystemExit) as stopped:
        deploy_api.main(["deploy_api.py", DIGEST])
    assert stopped.value.code == HINT
    assert lines(fake, "gcloud.args")[-1].startswith("run services add-iam-policy-binding specimen-api ")


def test_a_failed_deploy_stops_before_any_access_change(fake):
    (fake / "deploy.fails").touch()
    with pytest.raises(SystemExit, match="its output is above"):
        deploy_api.main(["deploy_api.py", DIGEST])
    assert len(lines(fake, "gcloud.args")) == 1


def test_a_missing_gcloud_is_reported_before_anything_runs(fake, monkeypatch):
    monkeypatch.setattr(deploy_api.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit, match="gcloud is not on PATH"):
        deploy_api.main(["deploy_api.py", DIGEST])
    assert lines(fake, "gcloud.args") == []


# --- wait_for_data.sh ---

def runs(*rows, branch="main"):
    """A workflow-runs answer; each row is (run number, status, conclusion)."""
    return json.dumps({"workflow_runs": [
        {"run_number": number, "status": status, "conclusion": conclusion, "head_branch": branch,
         "html_url": f"https://github.com/owner/repo/actions/runs/{number}"} for number, status, conclusion in rows]})


def test_the_wait_passes_once_this_commits_data_release_has_succeeded(fake):
    (fake / "gh.last").write_text(runs((7, "completed", "success")))
    result = script("wait_for_data.sh")
    assert result.returncode == 0 and "actions/runs/7" in result.stdout
    assert lines(fake, "gh.args") == [f"api repos/owner/repo/actions/workflows/data-release.yml/runs?head_sha={SHA}&per_page=20"]


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "skipped", "timed_out"])
def test_the_wait_fails_with_the_run_and_its_conclusion_when_the_data_release_did_not_succeed(fake, conclusion):
    (fake / "gh.last").write_text(runs((7, "completed", conclusion)))
    result = script("wait_for_data.sh")
    assert result.returncode == 1
    assert "actions/runs/7" in result.stdout and conclusion in result.stdout


def test_the_wait_tolerates_a_run_that_is_not_listed_yet_then_follows_it_to_success(fake):
    (fake / "gh.1").write_text(runs())
    (fake / "gh.2").write_text(runs())
    (fake / "gh.3").write_text(runs((7, "queued", None)))
    (fake / "gh.4").write_text(runs((7, "in_progress", None)))
    (fake / "gh.last").write_text(runs((7, "completed", "success")))
    result = script("wait_for_data.sh")
    assert result.returncode == 0 and len(lines(fake, "gh.args")) == 5
    assert "(queued)" in result.stdout and "(in_progress)" in result.stdout


def test_the_wait_gives_up_after_about_three_minutes_without_a_run(fake):
    (fake / "gh.last").write_text(runs())
    result = script("wait_for_data.sh")
    assert result.returncode == 1 and "No data release run exists" in result.stderr
    # Twelve polls at the default 15 seconds.
    assert len(lines(fake, "gh.args")) == 12
    assert "${POLL_SECONDS:-15}" in (ROOT / "scripts/release/wait_for_data.sh").read_text()


def test_the_newest_run_on_main_decides_whatever_started_it(fake):
    (fake / "gh.last").write_text(runs((7, "completed", "failure"), (9, "completed", "success")))
    assert script("wait_for_data.sh").returncode == 0
    (fake / "gh.last").write_text(runs((9, "completed", "failure"), (7, "completed", "success")))
    result = script("wait_for_data.sh")
    assert result.returncode == 1 and "actions/runs/9" in result.stdout
    # A run of the same commit on another branch releases nothing, so it is not the one to wait for.
    (fake / "gh.last").write_text(runs((11, "completed", "success"), branch="side"))
    assert script("wait_for_data.sh").returncode == 1


def test_the_wait_fails_when_github_cannot_be_read(fake):
    result = script("wait_for_data.sh")
    assert result.returncode == 1 and "Could not read the data release runs" in result.stderr
    assert len(lines(fake, "gh.args")) == 5


# --- push_image.sh ---

def test_the_push_logs_in_with_a_gcloud_token_over_stdin_tags_this_attempt_and_reports_the_registry_digest(fake):
    (fake / "digests").write_text(f"specimen-ci-api@sha256:{'c' * 64}\n{DIGEST}\n")
    result = script("push_image.sh", "api")
    assert result.returncode == 0
    assert (fake / "output").read_text() == f"image={DIGEST}\n"
    calls = lines(fake, "docker.args")
    assert calls[:3] == ["login --username oauth2accesstoken --password-stdin https://us-east4-docker.pkg.dev",
                         f"tag specimen-ci-api:{SHA} {TAG}", f"push {TAG}"]
    assert len(calls) == 4 and calls[3].startswith(f"image inspect {TAG} ")
    # gcloud is asked twice, a check and then the login, and can never stop at a prompt.
    assert lines(fake, "gcloud.args") == ["auth print-access-token"] * 2
    assert lines(fake, "gcloud.env") == ["1 unset"] * 2
    # The token reaches docker on stdin only: never an argument of any command, never in the output.
    assert (fake / "docker.stdin").read_text() == TOKEN + "\n"
    assert TOKEN not in result.stdout + result.stderr + "\n".join(calls + lines(fake, "gcloud.args"))
    text = (ROOT / "scripts/release/push_image.sh").read_text()
    assert "REGISTRY_TOKEN" not in text and "set -x" not in text and "xtrace" not in text


@pytest.mark.parametrize("token", ["", "\n", None])
def test_the_push_stops_before_docker_when_gcloud_gives_no_token(fake, token):
    if token is None:
        (fake / "token").unlink()  # The stand-in gcloud then fails, as an unauthenticated one does.
    else:
        (fake / "token").write_text(token)
    result = script("push_image.sh", "api")
    assert result.returncode == 1 and "gcloud printed no access token" in result.stderr
    assert lines(fake, "docker.args") == [] and not (fake / "output").exists()


def test_the_push_needs_gcloud_before_it_touches_docker(fake, monkeypatch):
    (fake / "bin/gcloud").unlink()
    tools = fake / "tools"
    tools.mkdir()
    for name in ("bash", "cat", "basename", "grep"):
        (tools / name).symlink_to(shutil.which(name))
    # Only the stand-ins and these few tools: no real gcloud of the machine can be found.
    monkeypatch.setenv("PATH", f"{fake / 'bin'}{os.pathsep}{tools}")
    result = script("push_image.sh", "api")
    assert result.returncode == 1 and "gcloud is not on PATH" in result.stderr
    assert lines(fake, "docker.args") == [] and not (fake / "output").exists()


@pytest.mark.parametrize("digests", [f"{IMAGE}@sha256:{'b' * 63}\n", f"{IMAGE}@sha256:{'b' * 65}\n",
                                     f"{IMAGE}@sha256:{'B' * 64}\n", f"specimen-ci-api@sha256:{'c' * 64}\n", ""])
def test_the_push_reports_no_image_without_this_repositorys_full_digest(fake, digests):
    (fake / "digests").write_text(digests)
    result = script("push_image.sh", "api")
    assert result.returncode == 1 and "no digest" in result.stderr
    assert not (fake / "output").exists()


def test_a_failed_push_or_another_role_reports_no_image(fake):
    (fake / "digests").write_text(DIGEST + "\n")
    (fake / "push.fails").touch()
    assert script("push_image.sh", "api").returncode != 0 and not (fake / "output").exists()
    (fake / "push.fails").unlink()
    (fake / "docker.args").unlink()
    for role in ("worker", "sam", ""):
        assert script("push_image.sh", role).returncode == 1
    assert lines(fake, "docker.args") == [] and not (fake / "output").exists()


# --- smoke_api.sh ---

def answers(fake, **replies):
    """Each reply is (status, body); a key such as ready_2 answers only the second request for /health/ready."""
    served = {"version": (200, {"source_sha": SHA, "contract_version": "api-runtime-v1", "mode": "production"}),
              "ready": (200, {"status": "ready", "mode": "production"}), "session": (401, {"detail": "Bearer identity required"}),
              **replies}
    for key, (status, body) in served.items():
        name, _, call = key.partition("_")
        (fake / f"{name}.{call or 'last'}").write_text(f"{status}\n{body if isinstance(body, str) else json.dumps(body)}")


def test_the_smoke_passes_when_the_public_api_serves_this_commit_ready_and_refuses_an_anonymous_session(fake):
    answers(fake)
    result = script("smoke_api.sh")
    assert result.returncode == 0 and f"API smoke passed for {SHA} at {URL}." in result.stdout
    assert lines(fake, "gcloud.args") == [
        "run services describe specimen-api --region us-east4 --project specimen-digitization --format=value(status.url)"]
    assert [call.split()[-1] for call in lines(fake, "curl.args")] == [f"{URL}/version", f"{URL}/health/ready", f"{URL}/v1/session"]


def test_the_smoke_waits_for_readiness(fake):
    not_ready = (503, {"status": "not_ready", "mode": "production"})
    answers(fake, ready_1=not_ready, ready_2=not_ready)
    assert script("smoke_api.sh").returncode == 0
    assert (fake / "ready.count").read_text() == "3"


def test_the_smoke_prints_the_last_body_when_the_api_never_becomes_ready(fake):
    answers(fake, ready=(503, {"status": "not_ready", "mode": "production"}))
    result = script("smoke_api.sh")
    assert result.returncode == 1 and "/health/ready failed with HTTP 503" in result.stderr and "not_ready" in result.stderr
    # All 18 tries at the default 10 seconds, about three minutes, and the session check never starts.
    assert (fake / "ready.count").read_text() == "18" and not (fake / "session.count").exists()
    assert "${POLL_SECONDS:-10}" in (ROOT / "scripts/release/smoke_api.sh").read_text()


@pytest.mark.parametrize("version", [
    (200, {"source_sha": "c" * 40, "mode": "production"}), (200, {"source_sha": SHA, "mode": "synthetic"}),
    (200, "<html>not json</html>"), (404, {"source_sha": SHA, "mode": "production"})])
def test_the_smoke_fails_when_another_commit_or_mode_is_serving(fake, version):
    answers(fake, version=version)
    result = script("smoke_api.sh")
    assert result.returncode == 1 and "/version failed" in result.stderr and HINT not in result.stderr
    assert not (fake / "ready.count").exists()


def test_a_google_403_names_the_owner_step_and_any_other_session_answer_just_fails(fake):
    answers(fake, session=(403, "<html>Your client does not have permission to get URL</html>"))
    result = script("smoke_api.sh")
    assert result.returncode == 1 and HINT in result.stderr and "/v1/session failed with HTTP 403" in result.stderr
    answers(fake, version=(403, "<html>Forbidden</html>"))
    result = script("smoke_api.sh")
    assert result.returncode == 1 and HINT in result.stderr and "/version failed with HTTP 403" in result.stderr
    for status in (200, 404):
        answers(fake, session=(status, {"detail": "unexpected"}))
        result = script("smoke_api.sh")
        assert result.returncode == 1 and HINT not in result.stderr


def test_a_first_public_binding_may_take_a_few_tries_to_reach_every_request(fake):
    forbidden = (403, "<html>Forbidden</html>")
    answers(fake, version_1=forbidden, version_2=forbidden, session_1=forbidden)
    assert script("smoke_api.sh").returncode == 0


@pytest.mark.parametrize("url", ["http://specimen-api-abc123-uk.a.run.app", "https://specimen-api.example.com",
                                 "https://specimen-api-abc123-uk.a.run.app/path", "https://run.app.example.org", ""])
def test_the_smoke_only_calls_a_cloud_run_url_unless_one_is_given_for_a_local_server(fake, url):
    answers(fake)
    (fake / "url").write_text(url + "\n")
    result = script("smoke_api.sh")
    assert result.returncode == 1 and "Unexpected API URL" in result.stderr and lines(fake, "curl.args") == []
    assert script("smoke_api.sh", "http://127.0.0.1:8080").returncode == 0
    assert lines(fake, "curl.args")[0].endswith(" http://127.0.0.1:8080/version")
    assert len(lines(fake, "gcloud.args")) == 1
