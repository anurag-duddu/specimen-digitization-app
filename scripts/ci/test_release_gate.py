"""Synthetic GitHub facts, clocks and step files for the runtime release gate; never network."""
import copy
import functools
import hashlib
import importlib
import json
from pathlib import Path
import stat
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
M = importlib.import_module("release_gate")
CONTEXT = importlib.import_module("release_context")
REPOSITORY = "anurag-duddu/specimen-digitization-app"
BASE = f"repos/{REPOSITORY}"
SHA, TREE, HEAD = "a" * 40, "d" * 40, "e" * 40
NOW = 1790164800
REPO = {"id": 1360732425}
COMPARE, COMMIT, PULLS = f"{BASE}/compare/{SHA}...main", f"{BASE}/commits/{SHA}", f"{BASE}/commits/{SHA}/pulls"
PULL, HEAD_COMMIT = f"{BASE}/pulls/15", f"{BASE}/commits/{HEAD}"
RUNS = f"{BASE}/actions/workflows/ci-cd.yml/runs?head_sha={SHA}&event=push&branch=main&per_page=20"
PROVIDER = "projects/716045864126/locations/global/workloadIdentityPools/github-actions/providers/"  # pragma: allowlist secret (public WIF provider path)


def jobs_path(attempt=1, page=1):
    return f"{BASE}/actions/runs/123/attempts/{attempt}/jobs?per_page=100&page={page}"


def run(**changes):
    return {"id": 123, "run_attempt": 1, "head_sha": SHA, "head_branch": "main", "event": "push",
            "path": ".github/workflows/ci-cd.yml", "status": "completed", "conclusion": "success",
            "repository": dict(REPO), "head_repository": dict(REPO), **changes}


def responses(pull=15, attempt=1):
    jobs = [{"name": name, "status": "completed", "conclusion": "success", "head_sha": SHA, "run_id": 123,
             "run_attempt": attempt} for name in [*sorted(M.CHECKS), "Deploy Firebase Hosting"]]
    return {
        COMPARE: {"status": "identical", "base_commit": {"sha": SHA}},
        COMMIT: {"sha": SHA, "commit": {"tree": {"sha": TREE}}},
        PULLS: [{"number": pull, "merge_commit_sha": SHA, "merged_at": "2026-09-23T12:00:00Z"}],
        f"{BASE}/pulls/{pull}": {"number": pull, "merged": True, "merge_commit_sha": SHA,
                                 "base": {"ref": "main", "repo": dict(REPO)}, "head": {"sha": HEAD, "repo": dict(REPO)}},
        HEAD_COMMIT: {"sha": HEAD, "commit": {"tree": {"sha": TREE}}},
        RUNS: {"total_count": 1, "workflow_runs": [run(run_attempt=attempt)]},
        jobs_path(attempt): {"total_count": len(jobs), "jobs": jobs},
    }


class Replies(list):
    """Successive answers for one path; the last one repeats."""


class GitHub:
    def __init__(self, answers=None):
        self.answers, self.calls = responses() if answers is None else answers, []

    def __call__(self, path):
        self.calls.append(path)
        answer = self.answers[path]
        if isinstance(answer, Replies):
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        return copy.deepcopy(answer)


class Clock:
    def __init__(self):
        self.now, self.sleeps = NOW, []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def watch(github, clock=None):
    clock = clock or Clock()
    return functools.partial(M.observe, gh=github, clock=clock.time, sleep=clock.sleep)


def gate(answers=None, wait_seconds=0, clock=None):
    return M.validate_facts(SHA, watch(GitHub(answers), clock)(SHA, wait_seconds=wait_seconds))


def environment(plane="runtime", **changes):
    name, workflow, identity = CONTEXT.PLANES[plane]
    env = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPOSITORY, "GITHUB_REPOSITORY_ID": "1360732425",
           "GITHUB_REPOSITORY_OWNER_ID": "140138196", "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main",
           "GITHUB_REF_PROTECTED": "true", "GITHUB_WORKFLOW_REF": f"{REPOSITORY}/.github/workflows/{workflow}@refs/heads/main",
           "GITHUB_SHA": SHA, "GITHUB_RUN_ID": "456", "GITHUB_RUN_ATTEMPT": "1", "DEPLOYMENT_ENVIRONMENT": name,
           "RELEASE_PROJECT": "specimen-digitization",
           "RELEASE_SERVICE_ACCOUNT": f"{identity}@specimen-digitization.iam.gserviceaccount.com", **changes}
    return {key: value for key, value in env.items() if value is not None}


@pytest.fixture
def steps(tmp_path):
    files = {"GITHUB_ENV": tmp_path / "github-env", "GITHUB_OUTPUT": tmp_path / "github-output"}
    for path in files.values():
        path.touch()
    return {key: str(path) for key, path in files.items()}


def admitted(tmp_path, steps, plane="runtime"):
    env = environment(plane, **steps)
    record = M.admit_gate(plane, env, wait_seconds=0, now=NOW, observe=watch(GitHub()))
    path = tmp_path / "release" / "packet.json"
    env["RELEASE_PACKET_SHA256"] = M.write_record(record, path, env)
    return record, path, env


def store(path, value):
    raw = json.dumps(value).encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("plane,role", [("runtime-build", "runtime-build"), ("runtime", "runtime-release")])
def test_the_record_binds_github_facts_and_the_planes_fixed_provider(tmp_path, steps, plane, role):
    record, path, env = admitted(tmp_path, steps, plane)
    assert record == {
        "version": "protected-release-gate/v1", "plane": plane, "repository": REPOSITORY,
        "project": "specimen-digitization", "source_sha": SHA, "source_tree_sha": TREE, "pull_request": 15,
        "ci_run_id": 123, "ci_run_attempt": 1, "release_run_id": 456, "release_run_attempt": 1,
        "issued_at_unix": NOW, "expires_at_unix": NOW + 3600,
        "identity": {"project_number": "716045864126", "pool_id": "github-actions", "provider": f"{PROVIDER}specimen-{role}"}}
    raw = path.read_bytes()
    assert raw == json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    assert hashlib.sha256(raw).hexdigest() == env["RELEASE_PACKET_SHA256"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600 and stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert Path(steps["GITHUB_ENV"]).read_text() == f"RELEASE_PACKET_SHA256={env['RELEASE_PACKET_SHA256']}\n"
    assert Path(steps["GITHUB_OUTPUT"]).read_text() == f"provider={PROVIDER}specimen-{role}\nsource_sha={SHA}\n"
    with pytest.raises(FileExistsError):
        M.write_record(record, path, env)
    assert path.read_bytes() == raw and len(Path(steps["GITHUB_ENV"]).read_text().splitlines()) == 1
    for missing in steps:
        with pytest.raises(ValueError):
            M.write_record(record, tmp_path / "other" / "packet.json", {**env, missing: ""})
    for injected in ({**record, "source_sha": f"{SHA}\nprovider=x"}, {**record, "identity": {"provider": "p\nq=r"}}):
        with pytest.raises(ValueError):
            M.write_record(injected, tmp_path / "other" / "packet.json", env)
    assert not (tmp_path / "other").exists()


@pytest.mark.parametrize("field,value", [
    ("GITHUB_REF_PROTECTED", "false"), ("GITHUB_REF_PROTECTED", None), ("GITHUB_EVENT_NAME", "workflow_dispatch"),
    ("GITHUB_EVENT_NAME", "pull_request"), ("GITHUB_REF", "refs/heads/feature"), ("GITHUB_REPOSITORY_ID", "1"),
    ("GITHUB_WORKFLOW_REF", f"{REPOSITORY}/.github/workflows/ci-cd.yml@refs/heads/main"),
    ("GITHUB_WORKFLOW_REF", f"{REPOSITORY}/.github/workflows/runtime-release.yml@refs/heads/feature"),
    ("DEPLOYMENT_ENVIRONMENT", "runtime-build-production"), ("DEPLOYMENT_ENVIRONMENT", "production"),
    ("RELEASE_SERVICE_ACCOUNT", "github-firebase-hosting@specimen-digitization.iam.gserviceaccount.com"),
    ("RELEASE_SERVICE_ACCOUNT", "specimen-runtime-build@specimen-digitization.iam.gserviceaccount.com"),
    ("GITHUB_SHA", "main"), ("GITHUB_RUN_ID", "0456"), ("GITHUB_RUN_ID", None),
    ("GITHUB_RUN_ATTEMPT", "+1"), ("GITHUB_RUN_ATTEMPT", "0"), ("GITHUB_RUN_ATTEMPT", "1\n"),
])
def test_an_untrusted_context_is_rejected_before_any_github_call(field, value):
    github = GitHub()
    with pytest.raises(ValueError):
        M.admit_gate("runtime", environment(**{field: value}), wait_seconds=0, now=NOW, observe=watch(github))
    assert github.calls == []


def test_the_retired_owner_authorized_sha_is_neither_required_nor_consulted():
    for stale in (None, "b" * 40):
        env = environment(RELEASE_AUTHORIZED_SHA=stale)
        assert M.admit_gate("runtime", env, wait_seconds=0, now=NOW, observe=watch(GitHub()))["source_sha"] == SHA


@pytest.mark.parametrize("plane", ["data", "data-initialization"])
def test_the_gate_admits_only_the_runtime_planes(plane):
    github = GitHub()
    with pytest.raises(ValueError, match="runtime planes"):
        M.admit_gate(plane, environment(plane), wait_seconds=0, now=NOW, observe=watch(github))
    assert github.calls == []


@pytest.mark.parametrize("change", [lambda c: c.update(status="behind"), lambda c: c.update(status="diverged"),
                                    lambda c: c.pop("status"), lambda c: c["base_commit"].update(sha="b" * 40)])
def test_a_commit_that_is_not_on_main_is_refused(change):
    answers = responses()
    change(answers[COMPARE])
    with pytest.raises(ValueError, match="not on main"):
        gate(answers)


@pytest.mark.parametrize("change", [
    lambda a: a[PULLS].clear(), lambda a: a[PULLS][0].update(merged_at=None),
    lambda a: a[PULLS].append({**a[PULLS][0], "number": 16}), lambda a: a[PULLS][0].update(merge_commit_sha="b" * 40),
    lambda a: a[PULL].update(merge_commit_sha="b" * 40), lambda a: a[PULL].update(merged=False),
    lambda a: a[PULL].update(number=16), lambda a: a[PULL]["base"].update(ref="release"),
    lambda a: a[PULL]["base"]["repo"].update(id=1), lambda a: a[PULL]["head"]["repo"].update(id=999),
    lambda a: a[PULL]["head"].update(repo=None), lambda a: a[HEAD_COMMIT]["commit"]["tree"].update(sha="f" * 40),
    lambda a: a[HEAD_COMMIT].update(sha="f" * 40), lambda a: a[COMMIT].update(sha="b" * 40),
])
def test_exactly_one_merged_pull_request_of_this_repository_with_the_reviewed_tree(change):
    answers = responses()
    change(answers)
    with pytest.raises(ValueError):
        gate(answers)


def test_the_gate_waits_for_the_ci_run_that_starts_on_the_same_push_and_issues_after_it(monkeypatch):
    answers, clock = responses(), Clock()
    answers[RUNS] = Replies([{"total_count": 0, "workflow_runs": []},
                             {"total_count": 1, "workflow_runs": [run(status="in_progress", conclusion=None)]},
                             answers[RUNS]])
    monkeypatch.setattr(M.time, "time", clock.time)
    record = M.admit_gate("runtime", environment(), wait_seconds=120, observe=watch(GitHub(answers), clock))
    assert clock.sleeps == [30, 30]
    assert (record["issued_at_unix"], record["expires_at_unix"]) == (NOW + 60, NOW + 60 + 3600)


@pytest.mark.parametrize("runs,wait,message,sleeps", [
    ([run(status="in_progress", conclusion=None)], 60, "did not finish in time", [30, 30]),
    ([], 0, "did not finish in time", []),
    ([run(), run(id=124, status="in_progress", conclusion=None)], 600, "ambiguous", []),
])
def test_an_unfinished_missing_or_ambiguous_ci_run_fails_within_the_bounded_wait(runs, wait, message, sleeps):
    answers, clock = responses(), Clock()
    answers[RUNS] = {"total_count": len(runs), "workflow_runs": runs}
    with pytest.raises(ValueError, match=message):
        gate(answers, wait_seconds=wait, clock=clock)
    assert clock.sleeps == sleeps


@pytest.mark.parametrize("wait", [-1, 3301, 30.0, True, "30"])
def test_the_wait_is_a_bounded_integer(wait):
    github = GitHub()
    with pytest.raises(ValueError, match="wait"):
        watch(github)(SHA, wait_seconds=wait)
    assert github.calls == []


@pytest.mark.parametrize("field,value", [
    ("path", ".github/workflows/spoof.yml"), ("event", "workflow_dispatch"), ("head_branch", "feature"),
    ("head_sha", "b" * 40), ("conclusion", "failure"), ("conclusion", "cancelled"), ("conclusion", None),
    ("repository", {"id": 1}), ("head_repository", {"id": 1}), ("id", 0), ("run_attempt", "1"),
])
def test_only_a_successful_ci_cd_push_run_of_this_repository_counts(field, value):
    answers = responses()
    answers[RUNS]["workflow_runs"][0][field] = value
    with pytest.raises(ValueError):
        gate(answers)
    observed = watch(GitHub())(SHA, wait_seconds=0)
    observed["run"][field] = value
    job_field = {"id": "run_id", "run_attempt": "run_attempt"}.get(field)
    for job in observed["jobs"] if job_field else ():
        job[job_field] = value  # consistent jobs: only the run's own check can refuse it
    with pytest.raises(ValueError):
        M.validate_facts(SHA, observed)


def test_runs_of_other_events_branches_workflows_or_commits_are_not_candidates():
    answers = responses()
    answers[RUNS]["workflow_runs"] += [run(id=124, event="workflow_dispatch"), run(id=125, head_branch="feature"),
                                       run(id=126, path=".github/workflows/spoof.yml"), run(id=127, head_sha="b" * 40)]
    assert gate(answers)["ci_run_id"] == 123


@pytest.mark.parametrize("change", [
    lambda jobs: jobs.pop(0), lambda jobs: jobs.append(copy.deepcopy(jobs[0])),
    lambda jobs: jobs[0].update(conclusion="failure"), lambda jobs: jobs[0].update(conclusion="skipped"),
    lambda jobs: jobs[0].update(status="in_progress"), lambda jobs: jobs[0].update(run_attempt=2),
    lambda jobs: jobs[0].update(run_id=124), lambda jobs: jobs[0].update(head_sha="b" * 40),
])
def test_each_required_check_is_one_successful_job_of_the_latest_attempt(change):
    answers = responses()
    listing = answers[jobs_path()]
    change(listing["jobs"])
    listing["total_count"] = len(listing["jobs"])
    with pytest.raises(ValueError, match="required check"):
        gate(answers)


def test_jobs_are_read_across_pages_until_the_count_reconciles():
    answers = responses()
    jobs = answers[jobs_path()]["jobs"]
    answers[jobs_path()], answers[jobs_path(page=2)] = {"total_count": 6, "jobs": jobs[:3]}, {"total_count": 6, "jobs": jobs[3:]}
    assert gate(answers)["ci_run_id"] == 123
    answers.update({jobs_path(page=page): {"total_count": 7, "jobs": []} for page in range(2, 101)})
    with pytest.raises(ValueError, match="reconcile"):
        gate(answers)


@pytest.mark.parametrize("plane", ["runtime-build", "runtime"])
def test_readmission_observes_the_same_facts_again_without_waiting(tmp_path, steps, plane):
    record, path, env = admitted(tmp_path, steps, plane)
    answers, clock = responses(), Clock()
    answers[COMPARE]["status"] = "ahead"  # main moved on; the gate never requires the tip
    assert M.readmit(path, plane, env, now=NOW + 3599, observe=watch(GitHub(answers), clock)) == record
    assert clock.sleeps == []


@pytest.mark.parametrize("plane,changes,now", [
    ("runtime", {"RELEASE_PACKET_SHA256": "0" * 64}, NOW), ("runtime", {"RELEASE_PACKET_SHA256": "pinned"}, NOW),
    ("runtime", {"GITHUB_RUN_ATTEMPT": "2"}, NOW), ("runtime", {"GITHUB_RUN_ID": "457"}, NOW),
    ("runtime", {}, NOW + 3600), ("runtime", {}, NOW - 1), ("runtime", {"GITHUB_REF_PROTECTED": "false"}, NOW),
    ("runtime-build", {}, NOW), ("data", {}, NOW),
])
def test_readmission_rejects_a_changed_digest_run_window_context_or_plane(tmp_path, steps, plane, changes, now):
    record, path, env = admitted(tmp_path, steps)
    github = GitHub()
    with pytest.raises(ValueError):
        M.readmit(path, plane, {**env, **changes}, now=now, observe=watch(github))
    assert github.calls == []


@pytest.mark.parametrize("change", [
    lambda r: r.update(unexpected=True), lambda r: r.pop("ci_run_attempt"),
    lambda r: r.update(version="protected-release/v1"), lambda r: r.update(plane="runtime-build"),
    lambda r: r.update(repository="fork/specimen-digitization-app"), lambda r: r.update(project="other"),
    lambda r: r["identity"].update(provider=f"{PROVIDER}specimen-runtime-build"),
    lambda r: r["identity"].update(project_number="1"), lambda r: r["identity"].update(unexpected=True),
    lambda r: r.update(expires_at_unix=NOW + 3601), lambda r: r.update(issued_at_unix=True),
    lambda r: r.update(release_run_attempt=True), lambda r: r.update(pull_request=15.0),
    lambda r: r.update(source_tree_sha="b" * 40), lambda r: r.update(ci_run_id=124),
])
def test_a_forged_record_is_refused_even_with_its_own_digest(tmp_path, steps, change):
    record, path, env = admitted(tmp_path, steps)
    change(record)
    forged = tmp_path / "forged.json"
    with pytest.raises(ValueError):
        M.readmit(forged, "runtime", {**env, "RELEASE_PACKET_SHA256": store(forged, record)}, now=NOW,
                  observe=watch(GitHub()))


@pytest.mark.parametrize("answers,message", [
    (responses(attempt=2), "changed"), (responses(pull=16), "changed"),
    ({**responses(), RUNS: {"total_count": 1, "workflow_runs": [run(run_attempt=2, status="in_progress", conclusion=None)]}},
     "did not finish in time"),
], ids=["ci-rerun", "other-pull-request", "ci-rerun-in-progress"])
def test_readmission_fails_without_waiting_when_github_facts_changed(tmp_path, steps, answers, message):
    record, path, env = admitted(tmp_path, steps)
    clock = Clock()
    with pytest.raises(ValueError, match=message):
        M.readmit(path, "runtime", env, now=NOW + 60, observe=watch(GitHub(answers), clock))
    assert clock.sleeps == []


def test_admission_hands_a_gate_record_to_readmission_for_the_runtime_planes_only(tmp_path, steps, monkeypatch):
    admission = importlib.import_module("release_admission")
    record, path, env = admitted(tmp_path, steps)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("RELEASE_AUTHORIZED_SHA", raising=False)
    monkeypatch.setattr(admission, "github_snapshot", lambda packet: pytest.fail("a gate record is not an envelope"))
    readmit = M.readmit
    monkeypatch.setattr(M, "readmit", lambda *args, **kwargs: readmit(*args, **kwargs, observe=watch(GitHub())))
    assert admission.admit(path, "runtime", now=NOW + 60) == record
    with pytest.raises(ValueError, match="runtime planes"):
        admission.admit(path, "data", now=NOW + 60)


def test_envelope_packets_keep_their_existing_admission(tmp_path, monkeypatch):
    admission = importlib.import_module("release_admission")
    envelope = tmp_path / "packet.json"
    monkeypatch.setenv("RELEASE_PACKET_SHA256", store(envelope, {"version": "protected-release/v1", "plane": "runtime"}))
    monkeypatch.setattr(M, "readmit", lambda *args, **kwargs: pytest.fail("an envelope is not a gate record"))
    with pytest.raises(ValueError, match="invalid release source"):
        admission.admit(envelope, "runtime", now=NOW)


def test_the_command_line_blocks_without_echoing_what_failed(tmp_path, monkeypatch):
    output = tmp_path / "release" / "packet.json"
    monkeypatch.setattr(sys, "argv", ["release_gate.py", "--plane", "runtime", "--output", str(output)])
    for key, value in environment(GITHUB_REF_PROTECTED="false").items():
        monkeypatch.setenv(key, value)
    with pytest.raises(SystemExit) as blocked:
        M.main()
    assert "GITHUB_REF_PROTECTED" not in str(blocked.value) and SHA not in str(blocked.value)
    assert not output.exists()
