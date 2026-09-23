"""The runtime plane deploys from a gate record with committed settings (RELEASE.md 3.2).
Cloud Run, GitHub, attestation and readiness are fakes: no network, no credentials."""
import copy
import importlib
import json
from pathlib import Path
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).parent))
M = importlib.import_module("deploy_runtime")
S = importlib.import_module("runtime_settings")
GATE = importlib.import_module("release_gate")
SHA, OLD, RUN, ATTEMPT = "a" * 40, "b" * 40, 456, 1
PREFIX = "projects/specimen-digitization/locations/us-east4"
NAMES = {"sam": f"{PREFIX}/services/specimen-sam", "worker": f"{PREFIX}/jobs/specimen-worker",
         "api": f"{PREFIX}/services/specimen-api"}
ACCOUNT = "{}-runtime@specimen-digitization.iam.gserviceaccount.com"
WORKER = "serviceAccount:" + ACCOUNT.format("specimen-worker")
REVISION, LATEST = "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION", "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
NEW = {role: f"specimen-{role}-aaaaaaaaaaaa-456-1" for role in ("api", "sam")}
CANDIDATE, SERVICE = "https://candidate---specimen-api-x7-uk.a.run.app", "https://specimen-api-x7-uk.a.run.app"
SAM_URL = "https://specimen-sam-716045864126.us-east4.run.app"
SAM_ACTION = "grant roles/run.invoker on specimen-sam to the worker runtime identity only"
API_ACTION = "grant roles/run.invoker on specimen-api to allUsers"
COMPARE = f"repos/anurag-duddu/specimen-digitization-app/compare/{OLD}...{SHA}"


def image(role):
    return f"us-east4-docker.pkg.dev/specimen-digitization/specimen-runtime/{role}@sha256:" + "6" * 64


def gate_record():
    now = int(time.time())
    return {"version": "protected-release-gate/v1", "plane": "runtime", "repository": "anurag-duddu/specimen-digitization-app",
            "project": "specimen-digitization", "source_sha": SHA, "source_tree_sha": "d" * 40, "pull_request": 15,
            "ci_run_id": 123, "ci_run_attempt": 1, "release_run_id": RUN, "release_run_attempt": ATTEMPT,
            "issued_at_unix": now, "expires_at_unix": now + 3600, "identity": GATE.identity("runtime")}


def policy(*members, condition=None):
    binding = {"role": "roles/run.invoker", "members": list(members)}
    return {"bindings": [{"role": "roles/viewer", "members": ["user:someone@example.invalid"]},
                         binding if condition is None else {**binding, "condition": condition}]}


def previous(role):
    """What an earlier release left: labelled with an older commit; the API serves its old revision."""
    state = {"name": NAMES[role], "etag": f"{role}-old", "labels": {"source-sha": OLD, "release-run": "1"}}
    if role == "api":
        state["trafficStatuses"] = [{"type": REVISION, "revision": "specimen-api-old", "percent": 100}]
    return state


class FakeGoogle:
    """Cloud Run v2 as far as the release uses it. Every call is recorded; operations finish at once."""

    run_iam_policy = M.Google.run_iam_policy  # the real read-only guard; it issues GET <service>:getIamPolicy
    real_wait = M.Google.wait  # the real operation-name and deadline checks

    def __init__(self, existing=(), policies=None, fail_traffic=False):
        self.packet = gate_record()
        self.state = {item["name"]: copy.deepcopy(item) for item in existing}
        self.policies = {"specimen-sam": policy(WORKER), "specimen-api": policy("allUsers")} if policies is None else policies
        self.calls, self.bodies, self.fail_traffic = [], [], fail_traffic

    def registry_login(self):
        self.calls.append("login")

    def request(self, api, method, resource, *, body=None, params=None, missing=False):
        assert api == "run"
        self.calls.append(" ".join([method, resource.rsplit("/", 1)[1], *map(str, (params or {}).values())]))
        if resource.endswith(":getIamPolicy"):
            return copy.deepcopy(self.policies.get(resource.rsplit("/", 1)[1].split(":")[0], {}))
        if method == "GET":
            assert missing or resource in self.state
            return copy.deepcopy(self.state.get(resource))
        self.bodies.append(copy.deepcopy(body))
        if self.fail_traffic and (params or {}).get("updateMask") == "traffic":
            raise ConnectionError("synthetic transport failure")
        name = resource if method == "PATCH" else f"{resource}/{next(iter(params.values()))}"
        current = self.state.get(name)
        assert (current is None) == (method == "POST") and body.get("etag") == (current or {}).get("etag")
        if (params or {}).get("updateMask") == "traffic":
            state = {**current, "traffic": body["traffic"]}
        else:
            state = {**copy.deepcopy(body), "reconciling": False, "terminalCondition": {"state": "CONDITION_SUCCEEDED"}}
        state.update(etag=f"etag-{len(self.bodies)}", generation=str(len(self.bodies)))
        if "/services/" in name:
            service, revision = name.rsplit("/", 1)[1], state["template"]["revision"]
            state.update(latestReadyRevision=f"{name}/revisions/{revision}", uri=f"https://{service}-x7-uk.a.run.app",
                         urls=[f"https://{service}-716045864126.us-east4.run.app"],
                         trafficStatuses=[{"revision": revision, **target, **(
                             {"uri": f"https://{target['tag']}---{service}-x7-uk.a.run.app"} if "tag" in target else {})}
                             for target in state["traffic"]])
        self.state[name] = state
        return {"name": f"{PREFIX}/operations/operation-{len(self.bodies)}", "done": True, "response": {}}

    def wait(self, api, operation, *, maximum_seconds=600):
        self.calls.append(f"wait {maximum_seconds}")
        return self.real_wait(api, operation, maximum_seconds=maximum_seconds)


@pytest.fixture
def ready(monkeypatch):
    """Fill each setting still PENDING with a synthetic value, as T4 and the processing lane will; committed ones stay."""
    for name, value in (("READINESS_GENERATION", 1790000000000001), ("SAM_CHECKPOINT_SHA256", "4" * 64),
                        ("SAM_SERVER_ENV", {"SPECIMEN_SAM3_MAX_REQUEST_BYTES": "1048576"})):
        if getattr(S, name) is S.PENDING:
            monkeypatch.setattr(S, name, value)
    if S.WORKER["args"] is S.PENDING:
        monkeypatch.setitem(S.WORKER, "args", ["--drain", "--max-seconds", "3300"])


def deploy(tmp_path, monkeypatch, google, *, status="ahead", failing=None):
    """Run the released deploy against fakes; return the receipt, the error (or None) and what was observed."""
    seen = {"attested": [], "compared": [], "probed": []}

    def compare(path):
        seen["compared"].append(path)
        return {"status": status}

    def probe(uri, sha):
        assert sha == SHA
        seen["probed"].append(uri)
        if uri == failing:
            raise ValueError("synthetic readiness failure")

    monkeypatch.setattr(M, "Google", lambda path, plane: google if plane == "runtime" else pytest.fail("wrong plane"))
    monkeypatch.setattr(M, "gh_json", compare)
    monkeypatch.setattr(M, "verify_public_api", probe)
    monkeypatch.setattr(M, "verify_attestation", lambda subject, sha, flow: seen["attested"].append((subject, sha, flow)))
    receipts = tmp_path / "images"
    for role in NAMES:
        folder = receipts / f"runtime-image-{role}-{SHA}-{ATTEMPT}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{role}.json").write_text(json.dumps({"version": "runtime-image/v1", "role": role, "source_sha": SHA,
                                                         "run_id": RUN, "run_attempt": ATTEMPT, "reference": image(role)}))
    output, error = tmp_path / "runtime-receipt.json", None
    try:
        M.deploy_released(tmp_path / "packet.json", receipts, output)
    except ValueError as exc:
        error = exc
    return json.loads(output.read_text()), error, seen


def env_of(container):
    plain = {item["name"]: item["value"] for item in container["env"] if "value" in item}
    secret = {item["name"]: tuple(item["valueSource"]["secretKeyRef"][key] for key in ("secret", "version"))
              for item in container["env"] if "valueSource" in item}
    return plain, secret


def test_committed_settings_name_each_pending_value_and_nothing_is_touched(tmp_path, monkeypatch):
    assert S.pending("api") == ["READINESS_GENERATION"]
    assert S.pending("worker") == ['WORKER["args"]', "SAM_CHECKPOINT_SHA256"]
    assert S.pending("sam") == ["SAM_SERVER_ENV", "SAM_CHECKPOINT_SHA256"]
    assert {secret for role in S.ROLES.values() for secret in role["secret_env"].values()} == set(S.SECRET_VERSIONS)
    with pytest.raises(ValueError):
        M.released_bodies({role: image(role) for role in NAMES}, SHA, RUN, ATTEMPT, ["api"])
    google = FakeGoogle()
    receipt, error, seen = deploy(tmp_path, monkeypatch, google)
    assert error is None and google.calls == [] and seen == {"attested": [], "compared": [], "probed": []}
    assert receipt == {"version": "runtime-deployed/v1", "source_sha": SHA, "run_id": RUN, "run_attempt": ATTEMPT,
                       "deployed": {}, "pending": {role: S.pending(role) for role in ("api", "worker", "sam")},
                       "promoted": False, "worker_executed": False}


def test_bodies_are_built_only_from_the_committed_settings(ready):
    from specimen_digitization.application.production import sql_endpoint_from_env
    from specimen_digitization.application.runtime_config import RuntimeConfig
    from specimen_digitization.hub_models import SAM3_MODEL
    assert all(S.pending(role) == [] for role in S.ROLES)
    images = {role: image(role) for role in NAMES}
    for wrong in ({**images, "api": image("worker")}, {**images, "sam": image("sam").split("@")[0] + ":latest"}):
        with pytest.raises(ValueError):
            M.released_bodies(wrong, SHA, RUN, ATTEMPT, ["sam", "api"])
    bodies = M.released_bodies(images, SHA, RUN, ATTEMPT, ["sam", "worker", "api"])
    sql = {"SPECIMEN_SQL_LOCATION": "us-east4", "SPECIMEN_SQL_SERVICE": "specimen-digitization-service",
           "SPECIMEN_SQL_CONNECTOR": "specimen-server"}
    bucket, labels = "specimen-digitization.firebasestorage.app", {"source-sha": SHA, "release-run": "456"}
    api_env, api_secrets = env_of(bodies["api"]["template"]["containers"][0])
    assert api_env == {
        "SPECIMEN_FIREBASE_PROJECT": "specimen-digitization", "SPECIMEN_FIREBASE_PROJECT_NUMBER": "716045864126",
        "SPECIMEN_FIREBASE_APP_IDS": "1:716045864126:web:a193fa80c7a98bcac8e2ef,1:716045864126:android:6d2aeda8bc992e16c8e2ef,"  # pragma: allowlist secret (public app ids)
                                     "1:716045864126:ios:b4ae90c54b5beccac8e2ef",
        **sql, "SPECIMEN_GCS_BUCKET": bucket,
        "SPECIMEN_CORS_ORIGINS": "https://specimen-digitization.web.app,https://specimen-digitization.firebaseapp.com",
        "SPECIMEN_READINESS_OBJECT": "application/sha256/a1c115b623cdc43c1b062e5431c8ca8cb6411aa08057885e3b44a9238747818e",  # pragma: allowlist secret (public marker digest)
        "SPECIMEN_READINESS_GENERATION": "1790000000000001", "SPECIMEN_WORKER_JOB": NAMES["worker"]}
    assert api_secrets == {"LOGFIRE_TOKEN": ("specimen-worker-logfire", "1"),
                           "SPECIMEN_SOURCE_REGISTRY_JSON": ("specimen-source-registry", "1"),
                           "SPECIMEN_COLLECTION_BINDINGS_JSON": ("specimen-collection-bindings", "1")}
    assert RuntimeConfig.from_env(api_env).readiness_generation == 1790000000000001
    for role, cpu, memory, cap, concurrency, timeout in (("api", "1", "1Gi", 2, 8, "600s"), ("sam", "4", "16Gi", 1, 1, "300s")):
        body, template = bodies[role], bodies[role]["template"]
        assert (body["name"], body["ingress"], body["labels"]) == (NAMES[role], "INGRESS_TRAFFIC_ALL", labels)
        assert body["scaling"] == template["scaling"] == {"minInstanceCount": 0, "maxInstanceCount": cap}
        assert (template["revision"], template["serviceAccount"], template["timeout"], template["maxInstanceRequestConcurrency"],
                template["executionEnvironment"]) == (NEW[role], ACCOUNT.format(f"specimen-{role}"), timeout, concurrency,
                                                      "EXECUTION_ENVIRONMENT_GEN2")
        assert template["containers"][0]["resources"] == {"limits": {"cpu": cpu, "memory": memory}, "cpuIdle": True,
                                                          "startupCpuBoost": False}
    sam = bodies["sam"]["template"]
    assert sam["volumes"] == [{"name": "checkpoint", "gcs": {"bucket": bucket, "readOnly": True, "mountOptions": [
        "only-dir=application/sha256/" + "4" * 64 + "/sam3-cache"]}}]
    assert sam["containers"][0]["volumeMounts"] == [{"name": "checkpoint", "mountPath": "/model-cache"}]
    assert env_of(sam["containers"][0]) == ({
        "HF_HOME": "/model-cache", "HF_HUB_OFFLINE": "1", "SPECIMEN_SAM3_CHECKPOINT_SHA256": "4" * 64,
        "SPECIMEN_SAM3_AUDIENCE": SAM_URL, "SPECIMEN_SAM3_CALLER_EMAIL": ACCOUNT.format("specimen-worker"),
        "SPECIMEN_SAM3_OUTPUT_BUCKET": bucket, "SPECIMEN_SAM3_MAX_REQUEST_BYTES": "1048576"},
        {"LOGFIRE_TOKEN": ("specimen-worker-logfire", "1")})
    worker = bodies["worker"]
    task = worker["template"]["template"]
    assert (worker["name"], worker["labels"], worker["template"]["taskCount"], worker["template"]["parallelism"]) == (
        NAMES["worker"], labels, 1, 1)
    assert (task["serviceAccount"], task["timeout"], task["maxRetries"]) == (ACCOUNT.format("specimen-worker"), "3600s", 0)
    container = task["containers"][0]
    assert container["args"] == ["--drain", "--max-seconds", "3300"]
    assert container["resources"] == {"limits": {"cpu": "1", "memory": "1Gi"}}
    worker_env, worker_secrets = env_of(container)
    assert worker_env == {**sql, "SPECIMEN_GCS_BUCKET": bucket, "SPECIMEN_SAM3_ENDPOINT": SAM_URL,
                          "SPECIMEN_SAM3_REVISION": SAM3_MODEL.revision, "SPECIMEN_APPROVED_INFERENCE": "true",
                          "SPECIMEN_SAM3_CHECKPOINT_SHA256": "4" * 64}
    assert worker_secrets == {"HF_TOKEN": ("huggingface-runtime-token", "2"), "LOGFIRE_TOKEN": ("specimen-worker-logfire", "1"),
                              "SPECIMEN_GOOGLE_MAPS_API_KEY": ("specimen-google-maps-key", "1"),
                              "SPECIMEN_WORKER_ACTOR_UID": ("specimen-worker-actor-uid", "1"),
                              "SPECIMEN_COLLECTION_BINDINGS_JSON": ("specimen-collection-bindings", "1")}
    assert sql_endpoint_from_env(worker_env) == {"location": "us-east4", "service": "specimen-digitization-service",
                                                 "connector": "specimen-server"}
    assert "ExecutionToken" not in json.dumps(worker)


def test_no_deployed_setting_ever_carries_a_lab_only_value(ready):
    """Lab switches never reach a deployed role, as a plain or a secret variable, including values committed later."""
    bodies = M.released_bodies({role: image(role) for role in NAMES}, SHA, RUN, ATTEMPT, list(NAMES))
    assert set(bodies) == set(NAMES)
    for role, body in bodies.items():
        env = body["template"].get("template", body["template"])["containers"][0]["env"]
        names = {item["name"] for item in env}
        assert set(S.ROLES[role]["secret_env"]) <= names  # the secret env is scanned too
        assert not names & {"SPECIMEN_SAM3_LAB_TOKEN", "SPECIMEN_SAM3_LAB_DIR"}
        assert all(item.get("value") not in (None, "lab") for item in env if item["name"] == "SPECIMEN_SAM3_ENABLE")


def test_the_first_release_creates_each_role_and_names_both_owner_grants(tmp_path, monkeypatch, ready):
    google = FakeGoogle(policies={})
    receipt, error, seen = deploy(tmp_path, monkeypatch, google)
    assert isinstance(error, ValueError) and SAM_ACTION in str(error) and API_ACTION in str(error)
    assert google.calls == [
        "login", "GET specimen-sam", "POST services specimen-sam", "wait 900", "GET specimen-sam",
        "GET specimen-worker", "POST jobs specimen-worker", "wait 900", "GET specimen-worker",
        "GET specimen-api", "POST services specimen-api", "wait 900", "GET specimen-api",
        "GET specimen-sam:getIamPolicy 3", "GET specimen-api:getIamPolicy 3"]
    assert google.bodies[0]["traffic"] == google.bodies[2]["traffic"] == [{"type": LATEST, "percent": 100}]
    assert seen["attested"] == [("oci://" + image(role), SHA, "runtime-release.yml") for role in ("sam", "worker", "api")]
    assert seen["probed"] == [] and seen["compared"] == []
    assert receipt["promoted"] is False and receipt["worker_executed"] is False
    assert receipt["deployed"] == {
        "sam": {"name": NAMES["sam"], "revision": NEW["sam"], "image": image("sam")},
        "worker": {"name": NAMES["worker"], "generation": "2", "etag": "etag-2", "image": image("worker")},
        "api": {"name": NAMES["api"], "revision": NEW["api"], "image": image("api")}}
    assert not any(":run" in call for call in google.calls) and "ExecutionToken" not in json.dumps(google.bodies)


def test_a_release_checks_the_api_candidate_before_moving_traffic_to_it(tmp_path, monkeypatch, ready):
    google = FakeGoogle(existing=[previous(role) for role in NAMES])
    receipt, error, seen = deploy(tmp_path, monkeypatch, google)
    assert error is None and receipt["promoted"] is True
    assert google.calls == [
        "login", "GET specimen-sam", "PATCH specimen-sam", "wait 900", "GET specimen-sam",
        "GET specimen-worker", "PATCH specimen-worker", "wait 900", "GET specimen-worker",
        "GET specimen-api", "PATCH specimen-api", "wait 900", "GET specimen-api",
        "GET specimen-sam:getIamPolicy 3", "GET specimen-api:getIamPolicy 3",
        "PATCH specimen-api traffic", "wait 900", "GET specimen-api"]
    sam, worker, api, promotion = google.bodies
    assert [sam["etag"], worker["etag"], api["etag"]] == ["sam-old", "worker-old", "api-old"]
    assert sam["traffic"] == [{"type": LATEST, "percent": 100}]
    assert api["traffic"] == [{"type": REVISION, "revision": "specimen-api-old", "percent": 100},
                              {"type": REVISION, "revision": NEW["api"], "percent": 0, "tag": "candidate"}]
    assert promotion == {"name": NAMES["api"], "etag": "etag-3",
                         "traffic": [{"type": REVISION, "revision": NEW["api"], "percent": 100}]}
    assert seen["probed"] == [CANDIDATE, SERVICE] and seen["compared"] == [COMPARE] * 3
    assert not any(":run" in call for call in google.calls) and "ExecutionToken" not in json.dumps(google.bodies)


@pytest.mark.parametrize("untag_fails", [False, True])
def test_an_api_candidate_that_fails_readiness_loses_its_tag_and_never_receives_traffic(tmp_path, monkeypatch, ready,
                                                                                         untag_fails):
    google = FakeGoogle(existing=[previous(role) for role in NAMES], fail_traffic=untag_fails)
    receipt, error, seen = deploy(tmp_path, monkeypatch, google, failing=CANDIDATE)
    assert seen["probed"] == [CANDIDATE] and receipt["promoted"] is False
    # Exactly one traffic-only PATCH: all traffic stays on the previous revision, and no tag is listed.
    assert google.calls.count("PATCH specimen-api traffic") == 1
    assert google.bodies[-1] == {"name": NAMES["api"], "etag": "etag-3",
                                 "traffic": [{"type": REVISION, "revision": "specimen-api-old", "percent": 100}]}
    if untag_fails:
        assert str(error) == "the API candidate failed readiness and its tag could not be removed; reconcile"
        assert google.calls[-1] == "PATCH specimen-api traffic"
    else:
        assert str(error) == "synthetic readiness failure"  # the readiness failure itself propagates
        assert google.calls[-3:] == ["PATCH specimen-api traffic", "wait 900", "GET specimen-api"]
        assert google.state[NAMES["api"]]["trafficStatuses"] == [{"type": REVISION, "revision": "specimen-api-old",
                                                                   "percent": 100}]


def test_a_failed_check_on_the_service_url_fails_the_run_and_the_receipt_says_traffic_moved(tmp_path, monkeypatch, ready):
    google = FakeGoogle(existing=[previous(role) for role in NAMES])
    receipt, error, seen = deploy(tmp_path, monkeypatch, google, failing=SERVICE)
    assert isinstance(error, ValueError) and seen["probed"] == [CANDIDATE, SERVICE]
    assert "PATCH specimen-api traffic" in google.calls and receipt["promoted"] is True


@pytest.mark.parametrize("sam,api,actions", [
    (policy(WORKER, "allUsers"), policy("allUsers"), [SAM_ACTION]),
    (policy(WORKER, condition={"expression": "true"}), policy("allUsers"), [SAM_ACTION]),
    (policy(WORKER), policy("allUsers", "allAuthenticatedUsers"), [API_ACTION]),
    (policy(WORKER), policy("allUsers", condition={"expression": "true"}), [API_ACTION]),
])
def test_invoker_policies_are_read_and_must_be_exact(tmp_path, monkeypatch, ready, sam, api, actions):
    google = FakeGoogle(policies={"specimen-sam": sam, "specimen-api": api})
    receipt, error, seen = deploy(tmp_path, monkeypatch, google)
    assert [action for action in (SAM_ACTION, API_ACTION) if action in str(error)] == actions
    assert seen["probed"] == [] and receipt["promoted"] is False
    assert [call for call in google.calls if "IamPolicy" in call] == ["GET specimen-sam:getIamPolicy 3",
                                                                       "GET specimen-api:getIamPolicy 3"]


@pytest.mark.parametrize("status", ["ahead", "identical", "behind", "diverged"])
def test_the_rollback_guard_replaces_only_an_older_deployed_commit(status):
    compared = []
    compare = lambda path: compared.append(path) or {"status": status}  # noqa: E731
    if status in {"ahead", "identical"}:
        M.rollback_guard({"labels": {"source-sha": OLD}}, SHA, compare=compare)
    else:
        with pytest.raises(ValueError, match="newer commit is already deployed"):
            M.rollback_guard({"labels": {"source-sha": OLD}}, SHA, compare=compare)
    assert compared == [COMPARE]


@pytest.mark.parametrize("existing,refused", [
    (None, False), ({}, False), ({"labels": {}}, False), ({"labels": {"source-sha": SHA}}, False),
    ({"labels": {"source-sha": "main"}}, True), ({"labels": {"source-sha": OLD + "/../../x"}}, True),
    ({"labels": {"source-sha": OLD.upper()}}, True),
])
def test_no_label_or_this_commit_needs_no_compare_and_a_malformed_label_is_refused(existing, refused):
    compare = lambda path: pytest.fail("no comparison is needed or safe")  # noqa: E731
    if refused:
        with pytest.raises(ValueError):
            M.rollback_guard(existing, SHA, compare=compare)
    else:
        M.rollback_guard(existing, SHA, compare=compare)


def test_a_newer_deployed_commit_stops_the_release_before_any_change(tmp_path, monkeypatch, ready):
    google = FakeGoogle(existing=[previous("sam")])
    receipt, error, seen = deploy(tmp_path, monkeypatch, google, status="behind")
    assert "newer commit" in str(error) and seen["compared"] == [COMPARE]
    assert google.calls == ["login", "GET specimen-sam"] and google.bodies == [] and receipt["deployed"] == {}


@pytest.mark.parametrize("setting,skipped", [('WORKER["args"]', {"worker"}), ("SAM_CHECKPOINT_SHA256", {"worker", "sam"})])
def test_a_role_with_a_pending_setting_is_not_deployed_and_the_others_are(tmp_path, monkeypatch, ready, setting, skipped):
    if setting == "SAM_CHECKPOINT_SHA256":  # the worker carries the same digest as SAM 3, so both wait for it
        monkeypatch.setattr(S, "SAM_CHECKPOINT_SHA256", S.PENDING)
    else:
        monkeypatch.setitem(S.WORKER, "args", S.PENDING)
    google = FakeGoogle()
    receipt, error, seen = deploy(tmp_path, monkeypatch, google)
    deployed = [role for role in NAMES if role not in skipped]
    assert error is None and not any(NAMES[role].rsplit("/", 1)[1] in call for role in skipped for call in google.calls)
    assert receipt["pending"] == {role: [setting] if role in skipped else [] for role in ("api", "worker", "sam")}
    assert set(receipt["deployed"]) == set(deployed) and receipt["promoted"] is True and seen["probed"] == [SERVICE]
    assert [subject for subject, _, _ in seen["attested"]] == ["oci://" + image(role) for role in deployed]


@pytest.mark.parametrize("action", ["--admit", "--deploy"])
def test_the_command_line_sends_a_gate_record_down_the_released_path(tmp_path, monkeypatch, action):
    plane = "runtime-build" if action == "--admit" else "runtime"
    record = {**gate_record(), "plane": plane, "identity": GATE.identity(plane)}
    step, released = tmp_path / "github-output", []
    step.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(step))
    monkeypatch.setattr(M, "admit", lambda path, admitted: record if admitted == plane else pytest.fail("wrong plane"))
    monkeypatch.setattr(M, "read_bound_plan", lambda *args: pytest.fail("a gate record has no plan"))
    monkeypatch.setattr(M, "deploy", lambda *args: pytest.fail("a gate record never takes the envelope deploy"))
    monkeypatch.setattr(M, "deploy_released", lambda *args: released.append(args))
    extra = ["--receipts", str(tmp_path / "images"), "--output", str(tmp_path / "receipt.json")] if action == "--deploy" else []
    monkeypatch.setattr(sys, "argv", ["deploy_runtime.py", "--plane", plane, action, "--packet",
                                      str(tmp_path / "packet.json"), *extra])
    M.main()
    if action == "--admit":
        assert step.read_text() == f"provider={GATE.PROVIDERS['runtime-build']}\n" and released == []
    else:
        assert step.read_text() == "" and len(released) == 1
