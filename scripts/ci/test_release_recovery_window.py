"""Offline native-attempt, attestation and real transport seams; no paid effects."""
from contextlib import contextmanager
import copy
from datetime import datetime, timezone
import hashlib
import json
import signal
import subprocess
import sys
from pathlib import Path
import time

import pytest

import deploy_data as D
import deploy_runtime as runtime
import release_gate as GATE
import release_google as G
import release_initialize as I
import release_recovery_window as R
from release_diagnostics import DiagnosticError, HTTPFailure, public_failure, stage
from test_release_gate import GitHub, environment, watch

START = 1790164800
C = START - 600
SHA, RUN = "a" * 40, 456
BASE = f"repos/{R.REPOSITORY}/actions/runs/{RUN}"
BOOTSTRAP_CANARY = "private-bootstrap-canary-value"


def utc(value):
    return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record(attempt=2, plane="data", issued=C + 2000):
    value = GATE.admit_gate(plane, environment(plane), wait_seconds=0, now=issued,
                           observe=watch(GitHub(), wait_data=False))
    return {**value, "release_run_attempt": attempt}


def env(attempt=2, plane="data", **changes):
    return environment(plane, GITHUB_RUN_ATTEMPT=str(attempt), RELEASE_RECOVERY_WINDOW="true", **changes)


def native_run(attempt=1, **changes):
    return {"id": RUN, "run_attempt": attempt, "head_sha": SHA, "head_branch": "main", "event": "push",
            "path": R.WORKFLOW, "repository": {"id": R.REPOSITORY_ID}, "head_repository": {"id": R.REPOSITORY_ID},
            "created_at": utc(START), "run_started_at": utc(START if attempt == 1 else START + 300),
            "status": "completed" if attempt == 1 else "in_progress", "conclusion": "success" if attempt == 1 else None,
            **changes}


def receipts():
    binding = {"source_sha": SHA, "run_id": RUN, "run_attempt": 1}
    released = {"version": "data-released/v1", **binding, **dict.fromkeys(R.DATA_FACTS),
                "phase": "initialize", "bootstrap": "deferred"}
    principal = {"version": "data-initializer/v1", **binding, "instance": R.SOURCE, "database": R.DATABASE,
                 "postconditions_sha256": "b" * 64}
    initialized = {"version": "data-initialized/v1", **binding, "phase": "initialize", "schema_etag": "schema-etag",
                   "schema_update_time": utc(START + 200), "connector_etag": "connector-etag",
                   "storage_ruleset": f"projects/{R.PROJECT}/rulesets/current", "tables": 1, "views": 0}
    return {"data-receipt": released, "data-initializer": principal, "data-initialized": initialized}


class NativeGitHub:
    def __init__(self, attempt=2):
        jobs = [{"name": name, "head_sha": SHA, "run_id": RUN, "run_attempt": 1, "status": "completed",
                 "conclusion": "success"} for name in sorted(R.JOBS)]
        artifacts = [{"name": f"{prefix}-{SHA}-1", "expired": False, "workflow_run": {"id": RUN, "head_sha": SHA}}
                     for prefix in receipts()]
        self.answers = {BASE + "/attempts/1": native_run(status="in_progress", conclusion=None) if attempt == 1 else native_run(),
                        BASE + "/attempts/2": native_run(2),
                        BASE + "/attempts/1/jobs?per_page=100&page=1": {"total_count": len(jobs), "jobs": jobs},
                        BASE + "/artifacts?per_page=100": {"total_count": len(artifacts), "artifacts": artifacts}}
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        return copy.deepcopy(self.answers[path])


def test_ordinary_releases_after_secret_removal_keep_their_exact_record_and_perform_no_extra_reads():
    value = record(attempt=9)
    no_calls = lambda path: pytest.fail("ordinary G11 never reads recovery evidence")
    assert R.admit_record(value, {}, gh=no_calls) is value
    assert R.readmit_record(value, {R.MODE: "false"}, gh=no_calls) is value
    assert R.observe(value, {}, gh=no_calls) is None
    assert not R.enabled({R.MODE: "true"}, "runtime")


@pytest.mark.parametrize("bad", [True, False, 1, None, [], "TRUE", "true\n", BOOTSTRAP_CANARY])
def test_only_an_exact_presence_boolean_is_accepted_before_any_native_read(bad):
    gh = NativeGitHub()
    with pytest.raises(ValueError, match="presence flag"):
        R.observe(record(), {R.MODE: bad}, now=C + 2000, gh=gh)
    assert gh.calls == []


def test_secret_values_never_authorize_a_clock_or_leak_through_the_boolean_transport():
    R.require_secret_presence({R.MODE: "true"}, {"DATA_BOOTSTRAP_ARTIFACT_B64": BOOTSTRAP_CANARY})
    R.require_secret_presence({R.MODE: "false"}, {"DATA_BOOTSTRAP_ARTIFACT_B64": ""})
    for flag, value in [("false", BOOTSTRAP_CANARY), ("true", "")]:
        with pytest.raises(ValueError) as failure:
            R.require_secret_presence({R.MODE: flag}, {"DATA_BOOTSTRAP_ARTIFACT_B64": value})
        assert BOOTSTRAP_CANARY not in str(failure.value)


@pytest.mark.parametrize("offset", [0, 100, 599, 600])
def test_conservative_proof_depends_on_roots_external_native_timestamp_witness(offset):
    # No module claims to know T0. This is the required ROOT witness's arithmetic.
    frozen_t0 = START - offset
    assert frozen_t0 <= START <= frozen_t0 + R.ANCHOR_SECONDS
    assert C <= frozen_t0
    assert C + R.B_START_SECONDS + R.RUN_SECONDS + R.CLEANUP_SECONDS == C + R.DATA_SECONDS
    assert C + R.DATA_SECONDS <= frozen_t0 + R.DATA_SECONDS
    assert R.OPERATING_SECONDS == 6600 and R.OPERATING_SECONDS + R.CLEANUP_SECONDS == R.DATA_SECONDS


def test_a_reads_exact_attempt_one_and_caps_the_initializer_without_a_caller_timestamp():
    gh = NativeGitHub(attempt=1)
    value = record(attempt=1, plane="data-initialization", issued=C + 4400)
    admitted = R.admit_record(value, env(attempt=1, plane="data-initialization"), now=C + 4400, gh=gh)
    assert gh.calls == [BASE + "/attempts/1"]
    assert admitted["expires_at_unix"] == C + R.INIT_SECONDS
    assert admitted.keys() == value.keys() and admitted["issued_at_unix"] == C + 4400
    assert admitted["expires_at_unix"] <= admitted["issued_at_unix"] + GATE.WINDOW_SECONDS


def test_admission_uses_process_time_after_native_reads_and_cannot_reset_the_cap(monkeypatch):
    gh = NativeGitHub(attempt=1)
    clock = [C + 4499]
    monkeypatch.setattr(R.time, "time", lambda: clock[0])

    def delayed(path):
        result = gh(path)
        clock[0] = C + 4500
        return result
    with pytest.raises(ValueError, match="waited past"):
        R.admit_record(record(attempt=1, plane="data-initialization"), env(attempt=1, plane="data-initialization"), gh=delayed)
    assert gh.calls == [BASE + "/attempts/1"]


@pytest.mark.parametrize("when", [C + 3000, C + 3000.001, C + 6800])
def test_late_queued_b_is_refused_even_if_its_attempt_started_earlier(when):
    gh = NativeGitHub()
    with pytest.raises(ValueError, match="B admission"):
        R.admit_record(record(), env(), now=when, gh=gh)
    assert gh.calls[0] == BASE + "/attempts/1" and gh.calls[-1] == BASE + "/attempts/2"
    assert all("/attempts/1/jobs?" in path for path in gh.calls if "/jobs?" in path)
    assert BASE not in gh.calls  # Neither the latest run nor its unchanged created_at anchors B.


@pytest.mark.parametrize("change", [
    {"status": "in_progress"}, {"conclusion": "failure"}, {"conclusion": "cancelled"},
    {"run_attempt": 2}, {"run_attempt": True}, {"id": RUN + 1}, {"head_sha": "c" * 40},
    {"head_branch": "feature"}, {"event": "workflow_dispatch"}, {"path": ".github/workflows/runtime-release.yml"},
    {"repository": {"id": 1}}, {"head_repository": None}, {"run_started_at": utc(C + 7000)},
    {"run_started_at": "2026-01-01T00:00:00+00:00"}, {"run_started_at": BOOTSTRAP_CANARY},
])
def test_b_rejects_failed_unfinished_foreign_or_unqualified_a_without_echoing_native_values(change):
    gh = NativeGitHub()
    gh.answers[BASE + "/attempts/1"].update(change)
    with pytest.raises(ValueError) as failure:
        R.admit_record(record(), env(), now=C + 2000, gh=gh)
    assert BOOTSTRAP_CANARY not in str(failure.value) and SHA not in str(failure.value)


@pytest.mark.parametrize("change", [
    lambda jobs: jobs.pop(), lambda jobs: jobs.append(copy.deepcopy(jobs[0])),
    lambda jobs: jobs[0].update(conclusion="skipped"), lambda jobs: jobs[0].update(conclusion="failure"),
    lambda jobs: jobs[0].update(head_sha="c" * 40), lambda jobs: jobs[0].update(run_attempt=2),
    lambda jobs: jobs[0].update(run_id=RUN + 1), lambda jobs: jobs[0].update(status="in_progress"),
])
def test_every_a_job_including_disposal_and_migration_must_authentically_succeed(change):
    gh = NativeGitHub()
    listing = gh.answers[BASE + "/attempts/1/jobs?per_page=100&page=1"]
    change(listing["jobs"])
    listing["total_count"] = len(listing["jobs"])
    with pytest.raises(ValueError):
        R.admit_record(record(), env(), now=C + 2000, gh=gh)


def test_prior_jobs_are_complete_across_pages_and_count_drift_is_rejected():
    gh = NativeGitHub()
    path = BASE + "/attempts/1/jobs?per_page=100&page="
    jobs = gh.answers[path + "1"]["jobs"]
    gh.answers[path + "1"] = {"total_count": 5, "jobs": jobs[:2]}
    gh.answers[path + "2"] = {"total_count": 5, "jobs": jobs[2:]}
    assert R.observe(record(), env(), now=C + 2000, gh=gh)["origin"] == C
    gh.answers[path + "2"]["total_count"] = 6
    with pytest.raises(ValueError, match="count changed"):
        R.observe(record(), env(), now=C + 2000, gh=gh)


def test_no_third_recovery_attempt_and_no_b_initializer_are_admitted():
    gh = NativeGitHub()
    for value in [record(attempt=3), record(attempt=2, plane="data-initialization")]:
        with pytest.raises(ValueError):
            R.observe(value, env(), now=C + 2000, gh=gh)
    assert BASE + "/attempts/2" not in gh.calls


def test_readmission_never_mints_another_hour_and_keeps_post_start_cleanup_possible():
    gh = NativeGitHub()
    admitted = R.admit_record(record(), env(), now=C + 2999, gh=gh)
    assert admitted["expires_at_unix"] == C + 6599
    assert R.observe(admitted, env(), now=C + 6200, gh=gh)["expires_before"] == C + 6600
    assert R.readmit_record(admitted, env(), now=C + 6200, gh=gh) is admitted
    with pytest.raises(ValueError, match="expired"):
        R.readmit_record(admitted, env(), now=admitted["expires_at_unix"], gh=gh)
    with pytest.raises(ValueError, match="fixed protected"):
        R.readmit_record({**admitted, "expires_at_unix": C + 6901}, env(), now=C + 6200, gh=gh)
    with pytest.raises(ValueError, match="start boundary"):
        R.readmit_record({**admitted, "issued_at_unix": C + 3000}, env(), now=C + 6200, gh=gh)


def test_real_gate_rechecks_github_context_and_digest_without_changing_its_serialized_keys(tmp_path, monkeypatch):
    native = NativeGitHub()
    monkeypatch.setattr(R, "gh_json", native)
    files = {"GITHUB_ENV": str(tmp_path / "env"), "GITHUB_OUTPUT": str(tmp_path / "output")}
    for path in files.values():
        Path(path).touch()
    context = {**env(), **files}
    admitted = GATE.admit_gate("data", context, wait_seconds=0, now=C + 2000,
                              observe=watch(GitHub(), wait_data=False))
    assert admitted.keys() == GATE.RECORD_KEYS
    packet = tmp_path / "packet.json"
    context["RELEASE_PACKET_SHA256"] = GATE.write_record(admitted, packet, context)
    assert Path(files["GITHUB_ENV"]).read_text().endswith("RELEASE_RECOVERY_WINDOW=true\n")
    assert Path(files["GITHUB_OUTPUT"]).read_text().endswith("recovery_window=true\n")
    raw = packet.read_bytes()
    assert BOOTSTRAP_CANARY not in raw.decode() + Path(files["GITHUB_ENV"]).read_text() + Path(files["GITHUB_OUTPUT"]).read_text()
    assert GATE.readmit(packet, "data", context, now=C + 5000, observe=watch(GitHub(), wait_data=False)) == admitted
    assert packet.read_bytes() == raw
    with pytest.raises(ValueError, match="digest"):
        GATE.readmit(packet, "data", {**context, "RELEASE_PACKET_SHA256": "0" * 64}, now=C + 2000)
    with pytest.raises(ValueError):
        GATE.admit_gate("data", {**context, "GITHUB_REF_PROTECTED": "false"}, wait_seconds=0, now=C + 2000)


def test_prior_receipts_use_the_real_subject_bound_attestation_consumer(tmp_path, monkeypatch):
    native, payloads, downloaded = NativeGitHub(), receipts(), []

    def checked(command, **kwargs):
        assert command[:3] == ["gh", "run", "download"] and command[3] == str(RUN)
        name, folder = command[command.index("--name") + 1], Path(command[command.index("--dir") + 1])
        prefix = next(key for key in payloads if name == f"{key}-{SHA}-1")
        raw = json.dumps(payloads[prefix]).encode()
        (folder / f"{prefix}.json").write_bytes(raw)
        downloaded.append(name)

    def verified(path, source, workflow):
        assert source == SHA and workflow == "data-release.yml"
        return json.dumps([{"verificationResult": {"statement": {"subject": [{
            "digest": {"sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}}]}}}])

    monkeypatch.setattr(runtime, "checked", checked)
    monkeypatch.setattr(runtime, "verify_attestation", verified)
    principal, initialized = R.qualified_prior(record(), gh=native)
    assert principal == payloads["data-initializer"] and initialized == payloads["data-initialized"]
    assert len(downloaded) == 3
    monkeypatch.setattr(runtime, "verify_attestation", lambda *args: "[]")
    with pytest.raises(ValueError, match="subject evidence"):
        R.qualified_prior(record(), gh=native)


@pytest.mark.parametrize("prefix,key,value", [
    ("data-receipt", "source_sha", "c" * 40), ("data-initializer", "run_id", RUN + 1),
    ("data-initialized", "run_attempt", 2), ("data-receipt", "bootstrap", "applied"),
    ("data-receipt", "backup_id", 123), ("data-initializer", "postconditions_sha256", BOOTSTRAP_CANARY),
    ("data-initialized", "tables", None), ("data-initialized", "schema_etag", None),
])
def test_attested_receipt_source_run_attempt_and_complete_postconditions_are_not_interchangeable(prefix, key, value):
    payloads, native = receipts(), NativeGitHub()
    payloads[prefix][key] = value
    fetch = lambda name, filename: copy.deepcopy(payloads[filename.removesuffix(".json")])
    with pytest.raises(ValueError) as failure:
        R.qualified_prior(record(), gh=native, fetch=fetch)
    assert BOOTSTRAP_CANARY not in str(failure.value)


def test_missing_expired_foreign_or_unattested_artifacts_fail_before_native_data_effects():
    for change in [lambda items: items.pop(), lambda items: items[0].update(expired=True),
                   lambda items: items[0]["workflow_run"].update(id=RUN + 1),
                   lambda items: items[0]["workflow_run"].update(head_sha="c" * 40)]:
        native = NativeGitHub()
        listing = native.answers[BASE + "/artifacts?per_page=100"]
        change(listing["artifacts"])
        listing["total_count"] = len(listing["artifacts"])
        with pytest.raises(ValueError):
            R.qualified_prior(record(), gh=native, fetch=lambda *args: receipts()[args[1].removesuffix(".json")])


def test_native_initializer_absence_and_a_postconditions_are_rechecked_before_b(tmp_path, monkeypatch):
    observed = {"expected_database": True, "expected_actor": True, "tables": ["public.specimen"], "views": [],
                "owners": [D.OWNER], "extensions": ["plpgsql", "uuid-ossp"], "postconditions": {"schema_owner": D.OWNER}}
    prior = (receipts()["data-initializer"], receipts()["data-initialized"])
    prior[0]["postconditions_sha256"] = I.sha(observed["postconditions"])
    calls = []
    monkeypatch.setattr(I, "own_principal", lambda google: None)
    monkeypatch.setattr(D, "gate_sql", lambda *args, **kwargs: calls.append((args, kwargs)) or observed)
    monkeypatch.setattr(D, "committed_source", lambda folder: {"files": [
        {"path": "schema.gql", "content": "type Specimen @table { id: UUID! }"}]})
    monkeypatch.setattr(D.schema_gate, "declared_sql", lambda *args: ({"specimen"}, set(), set()))
    monkeypatch.setattr(D, "relaxations", lambda: set())
    google = G.Google.__new__(G.Google)
    google.packet = record()
    D.require_prior_initialization(google, tmp_path, prior)
    assert calls[0][0][0] == "migrated" and calls[0][1] == {"deadline": google.packet["expires_at_unix"]}
    monkeypatch.setattr(I, "own_principal", lambda google: {"name": "private-user-canary"})
    with pytest.raises(ValueError, match="not natively absent"):
        D.require_prior_initialization(google, tmp_path, prior)
    monkeypatch.setattr(I, "own_principal", lambda google: None)
    observed["postconditions"]["schema_owner"] = "other"
    with pytest.raises(ValueError, match="postconditions differ"):
        D.require_prior_initialization(google, tmp_path, prior)


@pytest.mark.parametrize("api,method,resource,params", [
    ("sql", "GET", f"projects/{R.PROJECT}/instances/{R.SOURCE}", None),
    ("data", "POST", R.SERVICE + ":executeGraphqlRead", None),
    ("identity", "POST", f"projects/{R.PROJECT}/accounts:lookup", None),
    ("data", "PATCH", R.SERVICE + "/schemas/main", {"validateOnly": "true"}),
    ("data", "PATCH", R.SERVICE + "/connectors/specimen-server", {"validateOnly": "true"}),
])
def test_read_only_requests_do_not_latch_the_first_write(api, method, resource, params):
    value = record()
    window = R.observe(value, env(), now=C + 2000, gh=NativeGitHub())
    guard = R.FirstEffect(value, window, clock=lambda: C + 3100)
    guard(api, method, resource, params)
    assert not guard.started and guard.budget(api, method, resource, params) == value["expires_at_unix"] - C - 3100
    with pytest.raises(ValueError, match="first effect"):
        guard("sql", "POST", f"projects/{R.PROJECT}/backups")
    assert not guard.started


def test_first_send_latches_unknown_outcome_but_cannot_extend_cleanup_past_the_original_gate():
    value = record()
    window = R.observe(value, env(), now=C + 2000, gh=NativeGitHub())
    clock = [C + 2999]
    guard = R.FirstEffect(value, window, clock=lambda: clock[0])
    assert guard.budget("data", "POST", R.SERVICE + ":executeGraphql") == 1
    guard("data", "POST", R.SERVICE + ":executeGraphql")
    assert guard.started
    clock[0] = C + 3100
    guard("sql", "DELETE", f"projects/{R.PROJECT}/instances/specimen-digitization-restore-20260908-r1")
    assert guard.started
    clock[0] = value["expires_at_unix"]
    with pytest.raises(ValueError, match="original fixed gate"):
        guard("sql", "DELETE", f"projects/{R.PROJECT}/instances/specimen-digitization-restore-20260908-r1")


class Response:
    status_code = 200

    def json(self):
        return {"name": "private-response-canary"}


def transport(monkeypatch, clock):
    value = record()
    window = R.observe(value, env(), now=C + 2000, gh=NativeGitHub())
    google = G.Google.__new__(G.Google)
    google.packet, google.path, google.plane = value, Path("unused-private-packet"), "data"
    google.recovery_first_effect_guard = R.FirstEffect(value, window, clock=lambda: clock[0])
    monkeypatch.setenv(R.MODE, "true")
    monkeypatch.setattr(G.time, "time", lambda: clock[0])
    monkeypatch.setattr(G, "admit", lambda *args: value)
    monkeypatch.setattr(__import__("release_clone"), "authorize_effect", lambda *args: None)
    calls, budgets = [], []

    @contextmanager
    def deadline(seconds):
        budgets.append(seconds)
        yield
    monkeypatch.setattr(G, "request_deadline", deadline)

    class Session:
        def request(self, *args, **kwargs):
            calls.append((args, kwargs))
            return Response()
    google.session = Session()
    return google, calls, budgets


def test_real_google_boundary_refuses_time_advanced_by_admission_before_any_first_dispatch(monkeypatch):
    clock = [C + 2999]
    google, calls, budgets = transport(monkeypatch, clock)

    def delayed_admission(*args):
        clock[0] = C + 3000
        return google.packet
    monkeypatch.setattr(G, "admit", delayed_admission)
    with pytest.raises(ValueError, match="remaining fixed authority"):
        google.request("sql", "POST", f"projects/{R.PROJECT}/backups", body={"private": BOOTSTRAP_CANARY})
    assert calls == [] and budgets == [] and not google.recovery_first_effect_guard.started


def test_real_google_boundary_caps_first_send_and_preserves_http_failure_without_replay(monkeypatch):
    clock = [C + 2999]
    google, calls, budgets = transport(monkeypatch, clock)
    Response.status_code = 403
    try:
        with pytest.raises(HTTPFailure) as failure:
            google.request("sql", "POST", f"projects/{R.PROJECT}/backups", body={"private": BOOTSTRAP_CANARY})
        assert failure.value.http_status == 403 and failure.value.body is None
        assert len(calls) == 1 and budgets == [1]
        assert calls[0][1]["max_allowed_time"] == 1 and calls[0][1]["timeout"] == 1
        assert google.recovery_first_effect_guard.started
    finally:
        Response.status_code = 200
    clock[0] = C + 3100
    google.request("sql", "DELETE", f"projects/{R.PROJECT}/instances/specimen-digitization-restore-20260908-r1")
    assert len(calls) == 2 and budgets[-1] == 30


def test_real_google_read_only_post_after_start_cutoff_stays_a_read_and_never_latches(monkeypatch):
    google, calls, budgets = transport(monkeypatch, [C + 3100])
    google.request("data", "POST", R.SERVICE + ":executeGraphqlRead", body={"query": BOOTSTRAP_CANARY})
    assert len(calls) == 1 and budgets == [30] and not google.recovery_first_effect_guard.started
    with pytest.raises(ValueError):
        google.request("data", "POST", R.SERVICE + ":executeGraphql", body={"query": BOOTSTRAP_CANARY})
    assert len(calls) == 1


def test_actual_process_deadline_interrupts_first_send_body_or_refresh_without_retry(monkeypatch):
    actual_deadline = G.request_deadline
    google, calls, _ = transport(monkeypatch, [C + 2999])
    monkeypatch.setattr(G, "request_deadline", actual_deadline)
    google.recovery_first_effect_guard.start_before = C + 2999.01

    def delayed(*args, **kwargs):
        calls.append((args, kwargs))
        time.sleep(0.03)
        return Response()
    monkeypatch.setattr(google.session, "request", delayed)
    with pytest.raises(TimeoutError, match="native request deadline"):
        google.request("data", "POST", R.SERVICE + ":executeGraphql", body={"query": BOOTSTRAP_CANARY})
    assert len(calls) == 1 and google.recovery_first_effect_guard.started


def disposal_transport(monkeypatch, clock):
    google, calls, budgets = transport(monkeypatch, clock)
    google.sql_read_deadline = clock[0] + 180
    return google, calls, budgets


def test_real_ordinary_disposal_uses_its_fixed_gate_after_b_start_without_invoking_the_first_effect_guard(monkeypatch):
    google, calls, budgets = disposal_transport(monkeypatch, [C + 3100])
    assert not google.recovery_first_effect_guard.started
    assert google.dispose_initializer(I.SOURCE, "delete") == {"name": "private-response-canary"}
    assert len(calls) == 1 and budgets == [30]
    assert calls[0][1]["timeout"] == 30 and calls[0][1]["max_allowed_time"] == 30
    assert calls[0][1]["allow_redirects"] is False and not google.recovery_first_effect_guard.started


@pytest.mark.parametrize("deadline_owner", ["original-gate", "original-observation"])
def test_real_disposal_budget_intersects_the_gate_and_the_existing_observation_clock(monkeypatch, deadline_owner):
    clock = [C + 3100]
    google, calls, budgets = disposal_transport(monkeypatch, clock)
    if deadline_owner == "original-gate":
        google.packet["expires_at_unix"] = clock[0] + 2
    else:
        google.sql_read_deadline = clock[0] + 2
    assert google.dispose_initializer(I.SOURCE, "delete") == {"name": "private-response-canary"}
    assert budgets == [2] and len(calls) == 1
    assert calls[0][1]["timeout"] == calls[0][1]["max_allowed_time"] == 2


def test_ordinary_disposal_refuses_a_gate_consumed_by_readmission_before_any_dispatch(monkeypatch):
    clock = [C + 3100]
    google, calls, budgets = disposal_transport(monkeypatch, clock)
    google.packet["expires_at_unix"] = clock[0] + 1

    def delayed_admission(*args):
        clock[0] += 2
        return google.packet
    monkeypatch.setattr(G, "admit", delayed_admission)
    with pytest.raises(ValueError, match="ordinary disposal deadline"):
        google.dispose_initializer(I.SOURCE, "delete")
    assert calls == [] and budgets == [] and not google.recovery_first_effect_guard.started


@pytest.mark.parametrize("phase", ["refresh", "body"])
@pytest.mark.parametrize("deadline_owner", ["original-gate", "original-observation"])
def test_actual_ordinary_disposal_process_deadline_interrupts_refresh_or_body_and_never_replays(
        monkeypatch, phase, deadline_owner):
    hard_deadline = G.request_deadline
    clock = [C + 3100]
    google, calls, _ = disposal_transport(monkeypatch, clock)
    monkeypatch.setattr(G, "request_deadline", hard_deadline)
    if deadline_owner == "original-gate":
        google.packet["expires_at_unix"] = clock[0] + 0.01
    else:
        google.sql_read_deadline = clock[0] + 0.01
    parsed = []

    class DelayedBody:
        status_code = 200

        def json(self):
            parsed.append(True)
            if phase == "body":
                time.sleep(0.03)
            return {"name": BOOTSTRAP_CANARY}

    def delayed_session(*args, **kwargs):
        calls.append((args, kwargs))
        if phase == "refresh":
            time.sleep(0.03)
        return DelayedBody()
    monkeypatch.setattr(google.session, "request", delayed_session)
    with pytest.raises(TimeoutError, match="native request deadline") as failure:
        google.dispose_initializer(I.SOURCE, "delete")
    assert len(calls) == 1 and 0 < calls[0][1]["max_allowed_time"] < 0.02
    assert calls[0][1]["timeout"] == calls[0][1]["max_allowed_time"]
    assert parsed == ([True] if phase == "body" else [])
    assert not google.recovery_first_effect_guard.started and BOOTSTRAP_CANARY not in str(failure.value)
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


@pytest.mark.parametrize("status", [403, 500])
def test_disposal_non2xx_keeps_its_existing_fixed_public_stage_and_never_reads_error_body(monkeypatch, status):
    google, calls, budgets = disposal_transport(monkeypatch, [C + 3100])

    class RefusedResponse:
        status_code = status

        def json(self):
            pytest.fail("a disposal rejection never parses or retains a private error body")

    def refused(*args, **kwargs):
        calls.append((args, kwargs))
        return RefusedResponse()
    monkeypatch.setattr(google.session, "request", refused)
    with pytest.raises(DiagnosticError) as failure:
        with stage("data.execute"):
            google.dispose_initializer(I.SOURCE, "delete")
    assert failure.value.stage == "data.execute" and failure.value.http_status is None
    assert public_failure(failure.value) == "Data release blocked [stage=data.execute]."
    assert len(calls) == 1 and budgets == [30] and not google.recovery_first_effect_guard.started
    assert BOOTSTRAP_CANARY not in str(failure.value) and I.INITIALIZER_SQL not in str(failure.value)


def test_disposal_success_body_parse_failure_cannot_leak_private_text_through_outer_diagnostics(monkeypatch):
    google, calls, _ = disposal_transport(monkeypatch, [C + 3100])

    class MalformedBody:
        status_code = 200

        def json(self):
            raise ValueError(BOOTSTRAP_CANARY)

    def malformed(*args, **kwargs):
        calls.append((args, kwargs))
        return MalformedBody()
    monkeypatch.setattr(google.session, "request", malformed)
    with pytest.raises(DiagnosticError) as failure:
        with stage("data.execute"):
            google.dispose_initializer(I.SOURCE, "delete")
    assert len(calls) == 1 and public_failure(failure.value) == "Data release blocked [stage=data.execute]."
    assert BOOTSTRAP_CANARY not in str(failure.value) and failure.value.http_status is None


def test_removed_secret_mode_keeps_ordinary_disposals_existing_transport_shape(monkeypatch):
    google, calls, budgets = disposal_transport(monkeypatch, [C + 3100])
    monkeypatch.setenv(R.MODE, "false")
    assert google.dispose_initializer(I.SOURCE, "delete") == {"name": "private-response-canary"}
    assert len(calls) == 1 and budgets == [] and "max_allowed_time" not in calls[0][1]
    assert calls[0][1]["timeout"] == 30 and not google.recovery_first_effect_guard.started


def summary_cli(monkeypatch, clock):
    summary = {**dict.fromkeys(D.COUNTS, 0), "expected_database": True, "expected_actor": True,
               "extensions": [], "roles": []}
    calls = []
    monkeypatch.setattr(D.time, "time", lambda: clock[0])

    def run(command, **kwargs):
        calls.append((command, kwargs))
        assert command[:4] == ["node", "scripts/ci/release_sql.mjs", "summary", D.SOURCE]
        path = Path(command[4])
        path.write_text(json.dumps(summary))
        path.chmod(0o600)
        return subprocess.CompletedProcess(command, 0, b"", b"")
    monkeypatch.setattr(D.subprocess, "run", run)
    return summary, calls


@pytest.mark.parametrize("remaining,expected", [(3, 3), (120, 60)])
def test_real_catalog_cli_boundary_caps_timeout_to_remaining_packet_without_an_ignored_environment_deadline(
        tmp_path, monkeypatch, remaining, expected):
    clock = [C + 5000]
    summary, calls = summary_cli(monkeypatch, clock)
    assert D.first_catalog(tmp_path, SHA, deadline=clock[0] + remaining) == summary
    assert len(calls) == 1 and calls[0][1]["timeout"] == expected
    assert calls[0][1]["env"]["RELEASE_GATE_SHA"] == SHA and calls[0][1]["capture_output"] is True
    assert calls[0][1]["cwd"] == D.ROOT
    assert "RELEASE_OPERATION_DEADLINE" not in calls[0][1]["env"]


def test_recovery_first_step_forwards_only_its_admitted_packet_expiry_after_pre_reads(tmp_path, monkeypatch):
    clock = [C + 5000]
    _, calls = summary_cli(monkeypatch, clock)
    monkeypatch.setenv(R.MODE, "true")
    value = record(attempt=1)
    value["expires_at_unix"] = clock[0] + 2
    assert D.first_step(value, tmp_path) == "initialize"
    assert len(calls) == 1 and calls[0][1]["timeout"] == 2
    assert calls[0][1]["env"]["RELEASE_GATE_SHA"] == value["source_sha"]


def test_pre_reads_consuming_a_packet_refuse_before_any_catalog_child_launch(tmp_path, monkeypatch):
    clock = [C + 5000]
    _, calls = summary_cli(monkeypatch, clock)
    monkeypatch.setenv(R.MODE, "true")
    value = record(attempt=1)
    value["expires_at_unix"] = clock[0]
    with pytest.raises(ValueError, match="before launch"):
        D.first_step(value, tmp_path)
    assert calls == [] and not (tmp_path / "first-catalog.json").exists()


def test_a_summary_finishing_at_the_deadline_cannot_be_read_or_adopted(tmp_path, monkeypatch):
    clock = [C + 5000]
    _, calls = summary_cli(monkeypatch, clock)
    run = D.subprocess.run

    def completed_late(command, **kwargs):
        result = run(command, **kwargs)
        clock[0] += 2
        return result
    monkeypatch.setattr(D.subprocess, "run", completed_late)
    monkeypatch.setattr(D, "private_bytes", lambda *args: pytest.fail("late catalog output is never consumed"))
    with pytest.raises(ValueError, match="completed after"):
        D.first_catalog(tmp_path, SHA, deadline=C + 5002)
    assert len(calls) == 1 and calls[0][1]["timeout"] == 2


def test_actual_parent_process_timeout_bounds_catalog_runtime_without_a_terminal_sql_claim(tmp_path, monkeypatch):
    actual_run = subprocess.run
    calls = []
    monkeypatch.setattr(D.time, "time", lambda: C + 5000.99)

    def blocked_runtime(command, **kwargs):
        # Exercise first_catalog's real parent-process timeout using an offline
        # stand-in child; never import the native connector or contact SQL.
        assert command[:4] == ["node", "scripts/ci/release_sql.mjs", "summary", D.SOURCE]
        calls.append((command, kwargs))
        return actual_run([sys.executable, "-c", "import time; time.sleep(10)"], **kwargs)
    monkeypatch.setattr(D.subprocess, "run", blocked_runtime)
    with pytest.raises(subprocess.TimeoutExpired):
        D.first_catalog(tmp_path, SHA, deadline=C + 5000 + 1)
    assert len(calls) == 1 and 0 < calls[0][1]["timeout"] < 0.02
    assert not (tmp_path / "first-catalog.json").exists()


def test_catalog_timeout_keeps_the_existing_fixed_public_failure_and_does_not_replay(tmp_path, monkeypatch):
    clock = [C + 5000]
    _, calls = summary_cli(monkeypatch, clock)

    def unknown_runtime(command, **kwargs):
        calls.append((command, kwargs))
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output=BOOTSTRAP_CANARY.encode(), stderr=BOOTSTRAP_CANARY.encode())
    monkeypatch.setattr(D.subprocess, "run", unknown_runtime)
    with pytest.raises(DiagnosticError) as failure:
        with stage("data.execute"):
            D.first_catalog(tmp_path, SHA, deadline=clock[0] + 2)
    assert len(calls) == 1 and calls[0][1]["timeout"] == 2
    assert public_failure(failure.value) == "Data release blocked [stage=data.execute]."
    assert BOOTSTRAP_CANARY not in str(failure.value)


def test_unset_recovery_first_step_keeps_the_existing_two_argument_catalog_shape(tmp_path, monkeypatch):
    monkeypatch.delenv(R.MODE, raising=False)
    summary = {**dict.fromkeys(D.COUNTS, 0), "expected_database": True, "expected_actor": True,
               "extensions": [], "roles": []}
    calls = []

    def ordinary(directory, source_sha):
        calls.append((directory, source_sha))
        return summary
    monkeypatch.setattr(D, "first_catalog", ordinary)
    assert D.first_step(record(attempt=1), tmp_path) == "initialize"
    assert calls == [(tmp_path, SHA)]


@pytest.mark.parametrize("phase", ["child", "private-read", "parse"])
@pytest.mark.parametrize("late_by", [0, 0.001])
def test_gate_sql_never_adopts_a_result_finishing_at_or_after_its_original_deadline(
        tmp_path, monkeypatch, phase, late_by):
    clock, calls, consumed = [C + 5000], [], []
    deadline = clock[0] + 2
    raw = b'{"committed":true}'
    target = tmp_path / f"{D.SOURCE}-migrate.json"
    real_read, real_parse = D.private_bytes, D.strict_json
    monkeypatch.setattr(D.time, "time", lambda: clock[0])

    def run(command, **kwargs):
        calls.append((command, kwargs))
        target.write_bytes(raw)
        target.chmod(0o600)
        if phase == "child":
            clock[0] = deadline + late_by
        return subprocess.CompletedProcess(command, 0, b"", b"")

    def read(path):
        consumed.append("private-read")
        result = real_read(path)
        if phase == "private-read":
            clock[0] = deadline + late_by
        return result

    def parse(value):
        consumed.append("parse")
        result = real_parse(value)
        if phase == "parse":
            clock[0] = deadline + late_by
        return result

    monkeypatch.setattr(D.subprocess, "run", run)
    monkeypatch.setattr(D, "private_bytes", read)
    monkeypatch.setattr(D, "strict_json", parse)
    assert D.gate_sql("migrate", tmp_path, SHA, deadline=deadline) is None
    assert len(calls) == 1 and calls[0][1]["timeout"] == 2
    assert consumed == {"child": [], "private-read": ["private-read"], "parse": ["private-read", "parse"]}[phase]
    assert target.read_bytes() == raw  # Retained evidence never proves server rollback or permits replay.


@pytest.mark.parametrize("remaining,expected", [(0.25, 0.25), (2, 2), (600, 300), (None, 300)])
def test_gate_sql_timely_result_uses_the_remaining_original_budget_without_a_one_second_floor(
        tmp_path, monkeypatch, remaining, expected):
    clock, calls = [C + 5000], []
    monkeypatch.setattr(D.time, "time", lambda: clock[0])

    def run(command, **kwargs):
        calls.append((command, kwargs))
        path = Path(command[4])
        path.write_text('{"observed":true}')
        path.chmod(0o600)
        return subprocess.CompletedProcess(command, 0, b"", b"")
    monkeypatch.setattr(D.subprocess, "run", run)
    deadline = None if remaining is None else clock[0] + remaining
    assert D.gate_sql("migrated", tmp_path, SHA, deadline=deadline) == {"observed": True}
    assert len(calls) == 1 and calls[0][1]["timeout"] == expected
    assert calls[0][0][:4] == ["node", "scripts/ci/release_sql.mjs", "migrated", D.SOURCE]
    assert calls[0][1]["env"]["RELEASE_GATE_SHA"] == SHA and calls[0][1]["cwd"] == D.ROOT


@pytest.mark.parametrize("remaining", [0, -0.001])
def test_gate_sql_expired_original_budget_never_launches_a_child(tmp_path, monkeypatch, remaining):
    monkeypatch.setattr(D.time, "time", lambda: C + 5000)
    monkeypatch.setattr(D.subprocess, "run", lambda *args, **kwargs: pytest.fail("expired SQL never launches"))
    assert D.gate_sql("indexes", tmp_path, SHA, deadline=C + 5000 + remaining) is None
    assert list(tmp_path.iterdir()) == []


def test_gate_sql_real_parent_timeout_retains_unknown_output_without_a_second_invocation(tmp_path, monkeypatch):
    actual_run, calls = subprocess.run, []
    target = tmp_path / f"{D.SOURCE}-migrate.json"
    target.write_bytes(b'{"committed":true}')
    target.chmod(0o600)
    monkeypatch.setattr(D.time, "time", lambda: C + 5000.99)
    monkeypatch.setattr(D, "private_bytes", lambda *args: pytest.fail("unknown SQL output is never adopted"))

    def blocked_runtime(command, **kwargs):
        calls.append((command, kwargs))
        return actual_run([sys.executable, "-c", "import time; time.sleep(10)"], **kwargs)
    monkeypatch.setattr(D.subprocess, "run", blocked_runtime)
    assert D.gate_sql("migrate", tmp_path, SHA, deadline=C + 5001) is None
    assert len(calls) == 1 and 0 < calls[0][1]["timeout"] < 0.02
    assert target.read_bytes() == b'{"committed":true}'


def test_unknown_migration_terminal_state_never_claims_rollback_or_recommends_replay(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(D, "gate_sql", lambda *args, **kwargs: calls.append((args, kwargs)))
    with pytest.raises(ValueError) as failure:
        D.run_migration(tmp_path, SHA, [], set(), deadline=C + 5001)
    assert len(calls) == 1 and calls[0][1]["deadline"] == C + 5001
    assert "terminal state is unproved" in str(failure.value)
    assert "rolled back" not in str(failure.value) and "re-run" not in str(failure.value)
