"""The plain ops scripts (scripts/ops/README.md): DRY_RUN output, the committed settings they consume, no secret echo."""
from __future__ import annotations

import importlib
import inspect
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

import pytest
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ops = importlib.import_module("ops_common")
S = ops.settings
SHA = "c" * 40
ORG, COLLECTION = "0b7e2f4c-1d3a-4c5e-9f60-7a8b9c0d1e2f", "5f4e3d2c-1b0a-4987-8654-3210fedcba98"
WORKER_SA, SAM_SA, API_SA = (f"serviceAccount:{S.ROLES[role]['service_account']}" for role in ("worker", "sam", "api"))
FAKE_TOKEN = "hf_" + "Zq" * 18  # pragma: allowlist secret (test value)


def dry(script, *args, **env):
    """Run a script with DRY_RUN=1: (exit code, stdout+stderr, the printed commands as argv lists)."""
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"PROJECT", "REGION", "SAM_CHECKPOINT_SHA256", "SAM_IMAGE", "WORKER_IMAGE"}}
    environment.update({"DRY_RUN": "1", "SOURCE_SHA": SHA, **env})
    result = subprocess.run([sys.executable, str(HERE / script), *args], capture_output=True, text=True,
                            env=environment, timeout=300)
    output = result.stdout + result.stderr
    commands = [shlex.split(line[2:]) for line in result.stdout.splitlines() if line.startswith("+ ")]
    return result.returncode, output, commands


def find(commands, *prefix):
    return [argv for argv in commands if argv[:len(prefix)] == list(prefix)]


def pairs(argv):
    return list(zip(argv, argv[1:]))


# deploy.py

def test_worker_job_is_one_task_no_retries_with_the_drain_args_and_no_maps_key():
    code, output, commands = dry("deploy.py", "worker")
    assert code == 0, output
    [job] = find(commands, "gcloud", "run", "jobs", "deploy", "specimen-worker")
    for flag, value in (("--tasks", "1"), ("--parallelism", "1"), ("--max-retries", "0"), ("--task-timeout", "3600s")):
        assert (flag, value) in pairs(job)
    assert "--args=" + ",".join(S.WORKER["args"]) in job
    assert S.WORKER["args"][:3] == ["--mode", "production", "--drain"]
    assert f"--service-account={S.WORKER_EMAIL}" in job
    assert f"--labels=source-sha={SHA}" in job and f"--image={ops.registry()}/worker:{SHA}" in job
    secrets = next(arg for arg in job if arg.startswith("--set-secrets="))
    assert ":latest" not in secrets and "HF_TOKEN=huggingface-runtime-token:" in secrets
    assert "maps" not in output.lower()
    assert f"# env SPECIMEN_SAM3_ENDPOINT={S.SAM_URL}" in output
    assert f"# env SPECIMEN_WORKER_JOB={S.WORKER_JOB}" in output
    assert f"# env SPECIMEN_SAM3_CHECKPOINT_SHA256={S.SAM_CHECKPOINT_SHA256}" in output
    assert find(commands, "gcloud", "run", "services", "describe", "specimen-sam")  # The SAM URL is looked up first.


def test_sam_service_is_private_authorized_run_with_the_read_only_checkpoint_mount():
    code, output, commands = dry("deploy.py", "sam", SAM_MIN_INSTANCES="1")
    assert code == 0, output
    [service] = find(commands, "gcloud", "run", "deploy", "specimen-sam")
    for flag in ("--no-allow-unauthenticated", "--ingress=all", "--cpu=4", "--memory=16Gi", "--concurrency=1",
                 "--max-instances=1", "--min-instances=1", "--max=1", "--min=1", "--timeout=300s", "--clear-volumes",
                 f"--service-account={S.SAM['service_account']}",
                 "--startup-probe=tcpSocket.port=8080,periodSeconds=10,timeoutSeconds=10,failureThreshold=60",
                 "--add-volume-mount=volume=checkpoint,mount-path=/model-cache"):
        assert flag in service
    assert "--no-cpu-throttling" in service and "--cpu-boost" in service
    assert "--cpu-throttling" not in service and "--no-cpu-boost" not in service
    assert f"--labels=source-sha={SHA}" in service
    prefix = f"application/sha256/{S.SAM_CHECKPOINT_SHA256}/sam3-cache"
    assert (f"--add-volume=name=checkpoint,type=cloud-storage,bucket={S.BUCKET},readonly=true,"
            f"mount-options=only-dir={prefix};uid=10001;gid=10001") in service
    assert "# env SPECIMEN_SAM3_ENABLE=authorized-run" in output
    assert "# env HF_HUB_OFFLINE=1" in output
    assert "--set-secrets=LOGFIRE_TOKEN=specimen-worker-logfire:1" in service and "HF_TOKEN" not in output
    assert not any(arg.startswith("--allow-unauthenticated") for arg in service)


def test_sam_scaling_is_set_at_both_levels_as_the_release_body_sets_it():
    code, output, commands = dry("deploy.py", "sam")
    assert code == 0, output
    [service] = find(commands, "gcloud", "run", "deploy", "specimen-sam")
    flags = {arg.split("=", 1)[0]: arg.split("=", 1)[1] for arg in service
             if arg.startswith(("--min", "--max"))}
    released = importlib.import_module("deploy_runtime")
    body = released.released_bodies({"sam": f"{released.REGISTRY}/sam@sha256:" + "6" * 64}, SHA, 1, 1, ["sam"])["sam"]
    service_level, revision_level = body["scaling"], body["template"]["scaling"]
    assert flags == {
        "--min": str(service_level["minInstanceCount"]), "--max": str(service_level["maxInstanceCount"]),
        "--min-instances": str(revision_level["minInstanceCount"]),
        "--max-instances": str(revision_level["maxInstanceCount"]),
    } == {"--min": "0", "--max": "1", "--min-instances": "0", "--max-instances": "1"}


def test_deploy_refuses_another_project_and_a_bad_minimum():
    assert dry("deploy.py", "sam", PROJECT="another-project")[0] != 0
    assert dry("deploy.py", "sam", SAM_MIN_INSTANCES="2")[0] != 0


@pytest.mark.parametrize("image, source, label", [
    (f"{{registry}}/sam:{'d' * 40}", "", "d" * 40),  # build_images.py's tag names the commit
    (f"{{registry}}/sam:{'d' * 40}", "d" * 40, "d" * 40),
    (f"{{registry}}/sam@sha256:{'6' * 64}", "d" * 40, "d" * 40),  # by digest: SOURCE_SHA names the commit
    (f"{{registry}}/sam:{'d' * 40}", SHA, None),  # tag and SOURCE_SHA disagree
    (f"{{registry}}/sam@sha256:{'6' * 64}", "", None),  # by digest, no commit named
    ("{registry}/sam:latest", "", None),
])
def test_deploy_labels_each_resource_with_the_image_commit(image, source, label):
    code, output, commands = dry("deploy.py", "sam", SAM_IMAGE=image.format(registry=ops.registry()), SOURCE_SHA=source)
    if label is None:
        assert code != 0 and not find(commands, "gcloud", "run", "deploy")
        return
    assert code == 0, output
    [service] = find(commands, "gcloud", "run", "deploy", "specimen-sam")
    assert f"--labels=source-sha={label}" in service
    released = importlib.import_module("deploy_runtime")
    released.rollback_guard({"labels": {"source-sha": label}}, label)  # A release of that commit accepts the label.


def test_deploy_env_and_secrets_match_the_release_bodies():
    """The same committed settings, composed the same way as deploy_runtime.released_bodies."""
    deploy = importlib.import_module("deploy")
    released = importlib.import_module("deploy_runtime")
    images = {role: f"{released.REGISTRY}/{role}@sha256:" + "6" * 64 for role in ("worker", "sam")}
    bodies = released.released_bodies(images, SHA, 1, 1, ["worker", "sam"])
    for role, body in bodies.items():
        container = (body["template"]["template"] if role == "worker" else body["template"])["containers"][0]
        plain = {item["name"]: item["value"] for item in container["env"] if "value" in item}
        refs = {item["name"]: "{secret}:{version}".format(**item["valueSource"]["secretKeyRef"])
                for item in container["env"] if "valueSource" in item}
        assert deploy.role_env(role, S.SAM_CHECKPOINT_SHA256) == plain
        assert dict(pair.split("=", 1) for pair in deploy.role_secrets(role).split(",")) == refs
    assert released.REGISTRY == ops.registry()
    probe = bodies["sam"]["template"]["containers"][0]["startupProbe"]
    assert deploy.probe_flag(probe) == "tcpSocket.port=8080,periodSeconds=10,timeoutSeconds=10,failureThreshold=60"
    mount = bodies["sam"]["template"]["volumes"][0]["gcs"]["mountOptions"]
    assert mount == deploy.mount_options(S.SAM_CHECKPOINT_SHA256)
    assert mount[0] == "only-dir=" + deploy.checkpoint_prefix(S.SAM_CHECKPOINT_SHA256)
    # gcloud splits mount-options on ";" into the v2 list (googlecloudsdk command_lib/run/volumes.py).
    code, output, commands = dry("deploy.py", "sam")
    assert code == 0, output
    [service] = find(commands, "gcloud", "run", "deploy", "specimen-sam")
    volume = next(arg for arg in service if arg.startswith("--add-volume="))
    assert volume.split("mount-options=", 1)[1].split(";") == mount
    resources = bodies["sam"]["template"]["containers"][0]["resources"]
    assert ("--no-cpu-throttling" if not resources["cpuIdle"] else "--cpu-throttling") in service
    assert ("--cpu-boost" if resources["startupCpuBoost"] else "--no-cpu-boost") in service


def test_worker_deploy_refuses_a_sam_service_without_the_committed_url(monkeypatch):
    deploy = importlib.import_module("deploy")
    monkeypatch.delenv("DRY_RUN", raising=False)
    described = {"status": {"url": "https://specimen-sam-abc123-uk.a.run.app"},
                 "metadata": {"annotations": {"run.googleapis.com/urls": json.dumps([S.SAM_URL])}}}
    monkeypatch.setattr(ops, "read", lambda argv: json.dumps(described))
    assert S.SAM_URL in deploy.sam_urls()
    described["metadata"]["annotations"] = {}
    ran = []
    monkeypatch.setattr(ops, "run", ran.append)
    with pytest.raises(SystemExit, match="SAM_URL"):
        deploy.deploy("worker")
    assert ran == []


# iam.py

def test_iam_grants_are_standing_bindings_only():
    code, output, commands = dry("iam.py")
    assert code == 0, output
    assert "request.time" not in output and "timestamp(" not in output
    assert commands and all("add-iam-policy-binding" in argv for argv in commands)
    for argv in commands:
        conditions = [arg for arg in argv if arg.startswith("--condition")]
        if argv[1:3] == ["run", "jobs"]:
            assert conditions == []
        else:
            assert len(conditions) == 1 and (conditions[0] == "--condition=None"
                                             or conditions[0].startswith("--condition-from-file="))
    members = {arg.split("=", 1)[1] for argv in commands for arg in argv if arg.startswith("--member=")}
    assert members == {WORKER_SA, SAM_SA, API_SA}
    jobs = find(commands, "gcloud", "run", "jobs", "add-iam-policy-binding", "specimen-worker")
    assert {next(a for a in argv if a.startswith("--member=")) for argv in jobs} == {
        f"--member={WORKER_SA}", f"--member={API_SA}"}
    assert all("--role=roles/run.invoker" in argv for argv in jobs)
    [sam] = find(commands, "gcloud", "run", "services", "add-iam-policy-binding", "specimen-sam")
    assert f"--member={WORKER_SA}" in sam and "--role=roles/run.invoker" in sam
    assert f'startsWith("application/sha256/{S.SAM_CHECKPOINT_SHA256}/sam3-cache")' in output
    assert "google-maps" not in output


def test_iam_covers_owner_grants_for_the_worker_and_sam_identities():
    iam = importlib.import_module("iam")
    grants = importlib.import_module("owner_grants")
    mine = [(g.member, g.role, (g.kind, g.name), g.condition) for g in iam.grants(S.PROJECT, S.SAM_CHECKPOINT_SHA256)]
    standing, waiting = grants.runtime_grants(S)
    assert waiting == []
    theirs = [g for g in (*grants.STANDING, *grants.AFTER_RELEASE, *standing) if g.member in {WORKER_SA, SAM_SA}]
    theirs += [g for g in grants.AFTER_RELEASE if g.member == API_SA and g.resource == ("job", "specimen-worker")]
    # The bucket's resource conditions are kept exactly. Secrets are left to their version-pinned grants.
    expected = [(g.member, g.role, g.resource, g.condition if g.resource[0] == "bucket" else None) for g in theirs
                if g.resource[0] != "secret"]
    # Plus the one grant owner_grants does not list: SAM 3's unconditioned bucket listing for the mount.
    expected.append((SAM_SA, "roles/storage.legacyBucketReader", ("bucket", S.BUCKET), None))
    assert sorted(mine) == sorted(expected) and len(set(mine)) == len(mine)


def test_iam_never_grants_secret_access():
    # Each runtime secret is granted at one pinned version; a binding without that condition would open every version.
    code, output, commands = dry("iam.py")
    assert code == 0, output
    assert "secretmanager" not in output
    assert not [argv for argv in commands if argv[:2] == ["gcloud", "secrets"]]
    assert not [g for g in importlib.import_module("iam").grants(S.PROJECT, S.SAM_CHECKPOINT_SHA256)
                if g.kind == "secret" or "secretmanager" in g.role]


def test_sam_gets_an_unconditioned_bucket_listing_and_no_other_unconditioned_bucket_grant():
    code, output, commands = dry("iam.py")
    assert code == 0, output
    buckets = find(commands, "gcloud", "storage", "buckets", "add-iam-policy-binding", f"gs://{S.BUCKET}")
    unconditioned = [argv for argv in buckets if "--condition=None" in argv]
    assert unconditioned == [["gcloud", "storage", "buckets", "add-iam-policy-binding", f"gs://{S.BUCKET}",
                              f"--member={SAM_SA}", "--role=roles/storage.legacyBucketReader", "--condition=None",
                              "--quiet"]]
    # The checkpoint's conditioned listing grant stays.
    assert any(f"--member={SAM_SA}" in argv and "--role=roles/storage.objectViewer" in argv
               and any("specimen_sam3_checkpoint_listing" in arg for arg in argv) for argv in buckets)


# build_images.py

def test_build_images_tags_the_commit_skips_existing_tags_and_runs_as_the_build_identity():
    code, output, commands = dry("build_images.py")
    assert code == 0, output
    assert find(commands, "gcloud", "services", "enable", "cloudbuild.googleapis.com")
    builds = find(commands, "gcloud", "builds", "submit")
    assert len(builds) == 2
    for role, build in zip(("worker", "sam"), builds):
        image = f"{ops.registry()}/{role}:{SHA}"
        assert any(arg.startswith("--substitutions=") and f"_IMAGE={image}" in arg and f"_SOURCE_SHA={SHA}" in arg
                   for arg in build)
        assert (f"--service-account=projects/{S.PROJECT}/serviceAccounts/"
                f"specimen-runtime-build@{S.PROJECT}.iam.gserviceaccount.com") in build
        describe = ["gcloud", "artifacts", "docker", "images", "describe", image]
        assert commands.index(find(commands, *describe)[0]) < commands.index(build)
    [_, sam_archive] = find(commands, "git", "archive")
    assert "containers/worker/sam3.Dockerfile" in sam_archive and "containers/worker/sam3-requirements.lock" in sam_archive
    assert SHA in sam_archive
    config = yaml.safe_load((HERE / "cloudbuild-image.yaml").read_text())
    assert config["images"] == ["${_IMAGE}"]
    build_args = config["steps"][0]["args"]
    assert "--platform=linux/amd64" in build_args and "--build-arg=SOURCE_SHA=${_SOURCE_SHA}" in build_args


# sam_checkpoint.py

def test_checkpoint_patterns_are_the_servers():
    checkpoint = importlib.import_module("sam_checkpoint")
    server = importlib.import_module("specimen_digitization.application.sam3_server")
    assert repr(checkpoint.PATTERNS).replace("'", '"') in inspect.getsource(server.offline_checkpoint_path)


def test_checkpoint_dry_run_prints_the_layout_and_the_digest():
    code, output, commands = dry("sam_checkpoint.py")
    assert code == 0, output
    assert output.rstrip().endswith(S.SAM_CHECKPOINT_SHA256)
    [rsync] = find(commands, "gcloud", "storage", "rsync")
    assert "--no-ignore-symlinks" in rsync and "--checksums-only" in rsync
    assert rsync[4] == (f"gs://{S.BUCKET}/application/sha256/{S.SAM_CHECKPOINT_SHA256}/sam3-cache/hub/"
                        f"models--facebook--sam3/snapshots/{S.SAM3_MODEL.revision}/")
    pinned = str(S.SECRET_VERSIONS["huggingface-runtime-token"])
    assert find(commands, "gcloud", "secrets", "versions", "access", pinned, "--secret=huggingface-runtime-token")
    assert pinned == dict(pair.split("=", 1) for pair in importlib.import_module("deploy").role_secrets(
        "worker").split(","))["HF_TOKEN"].rsplit(":", 1)[1]  # The version the worker's HF_TOKEN reads.
    assert "latest" not in output


class FakeGcloud:
    """Answers the few gcloud commands the scripts send; records every argv."""

    def __init__(self, listings=(), secret=FAKE_TOKEN, secrets=None):
        self.calls, self.listings, self.secret, self.secrets = [], list(listings), secret, secrets or {}

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        out = ""
        if argv[:4] == ["gcloud", "secrets", "versions", "access"]:
            # gcloud prints the stored value with no terminator (format value[terminator=""]).
            name = next(arg.split("=", 1)[1] for arg in argv if arg.startswith("--secret="))
            out = self.secrets.get(name, self.secret)
        elif argv[:4] == ["gcloud", "storage", "objects", "list"]:
            out = json.dumps(self.listings.pop(0) if self.listings else [])
        elif argv[:3] == ["gcloud", "config", "get-value"]:
            out = "operator@example.org\n"
        elif argv[:3] == ["gcloud", "auth", "print-identity-token"]:
            out = self.secret + "\n"
        return SimpleNamespace(returncode=0, stdout=out, stderr="")


def listing(prefix_name, files):
    return [{"name": prefix_name + path, "size": size} for path, size in files.items()]


def test_checkpoint_download_never_echoes_the_token_and_cleans_up(monkeypatch, capsys):
    checkpoint = importlib.import_module("sam_checkpoint")
    server = importlib.import_module("specimen_digitization.application.sam3_server")
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.delenv("SAM_CHECKPOINT_SHA256", raising=False)
    for name in ("HF_HOME", "HF_HUB_DISABLE_TELEMETRY"):  # main() sets both; restore them afterwards.
        monkeypatch.setenv(name, os.environ.get(name, ""))
    monkeypatch.setattr(S, "SAM_CHECKPOINT_SHA256", None)  # A new revision: no digest known yet.
    files = {"config.json": b"{}", "model.safetensors": b"weights", "merges.txt": b"a b"}
    monkeypatch.setattr(checkpoint, "hub_files", lambda token: {name: len(raw) for name, raw in files.items()})
    seen = {}

    def download(token, cache_dir):
        seen["token"], seen["work"] = token, cache_dir.parent
        snapshot = cache_dir / "snapshot"
        snapshot.mkdir(parents=True)
        for name, raw in files.items():
            (snapshot / name).write_bytes(raw)
        seen["digest"] = server.checkpoint_files_digest(snapshot)[1]
        seen["prefix"] = checkpoint.snapshot_prefix(S.BUCKET, seen["digest"])[len(f"gs://{S.BUCKET}/"):]
        gcloud.listings[:] = [[], listing(seen["prefix"], {n: len(r) for n, r in files.items()})]
        return snapshot

    gcloud = FakeGcloud()
    monkeypatch.setattr(ops.subprocess, "run", gcloud)
    monkeypatch.setattr(checkpoint, "download", download)
    assert checkpoint.main() == 0
    out, err = capsys.readouterr()
    assert seen["token"] == FAKE_TOKEN
    assert FAKE_TOKEN not in out + err and not any(FAKE_TOKEN in " ".join(argv) for argv in gcloud.calls)
    assert out.rstrip().endswith(seen["digest"])
    [rsync] = [argv for argv in gcloud.calls if argv[:3] == ["gcloud", "storage", "rsync"]]
    assert rsync[4] == f"gs://{S.BUCKET}/{seen['prefix']}" and "--no-ignore-symlinks" in rsync
    assert not seen["work"].exists()


def test_checkpoint_already_stored_downloads_nothing(monkeypatch, capsys):
    checkpoint = importlib.import_module("sam_checkpoint")
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.delenv("SAM_CHECKPOINT_SHA256", raising=False)
    for name in ("HF_HOME", "HF_HUB_DISABLE_TELEMETRY"):  # main() sets both; restore them afterwards.
        monkeypatch.setenv(name, os.environ.get(name, ""))
    wanted = {"config.json": 25843, "model.safetensors": 3439938512}
    monkeypatch.setattr(checkpoint, "hub_files", lambda token: wanted)
    prefix = checkpoint.snapshot_prefix(S.BUCKET, S.SAM_CHECKPOINT_SHA256)[len(f"gs://{S.BUCKET}/"):]
    gcloud = FakeGcloud([listing(prefix, wanted)])
    monkeypatch.setattr(ops.subprocess, "run", gcloud)
    monkeypatch.setattr(checkpoint, "download", lambda *_: pytest.fail("downloaded a stored checkpoint"))
    assert checkpoint.main() == 0
    assert capsys.readouterr().out.rstrip().endswith(S.SAM_CHECKPOINT_SHA256)
    assert [argv[:4] for argv in gcloud.calls] == [["gcloud", "storage", "objects", "list"]]  # No secret, no upload.


# seed_allowance_ledger.py

ACTOR = "worker-actor-" + "x" * 12
BINDINGS = json.dumps({COLLECTION: "insects", "7d9a1c2b-3e4f-4a5b-8c6d-0e1f2a3b4c5d": "botany"})


def seed_secrets(actor=ACTOR, bindings=BINDINGS):
    return FakeGcloud(secrets={"specimen-worker-actor-uid": actor, "specimen-collection-bindings": bindings})


def test_seed_dry_run_reads_both_secrets_and_prints_no_identifier():
    code, output, commands = dry("seed_allowance_ledger.py", ORG_ID=ORG)
    assert code == 0, output
    assert find(commands, "gcloud", "secrets", "versions", "access", "1", "--secret=specimen-worker-actor-uid")
    assert find(commands, "gcloud", "secrets", "versions", "access", "1", "--secret=specimen-collection-bindings")
    assert ORG not in output and "as the operator credentials" in output
    assert dry("seed_allowance_ledger.py", ORG_ID=ORG.upper())[0] != 0
    assert dry("seed_allowance_ledger.py")[0] != 0


class FakeStore:
    def __init__(self, existing=None, member=True, role="operator"):
        self.existing, self.member, self.role, self.created = existing, member, role, []

    def memberships(self, uid):
        assert uid == ACTOR
        return [{"organization_id": ORG, "collection_id": COLLECTION, "role": self.role}] if self.member else []

    def document(self, scope, kind, ident):
        from specimen_digitization.application.storage import Missing

        assert (scope.organization_id, scope.collection_id, kind) == (ORG, COLLECTION, "worker_cursor")
        if self.existing is None:
            raise Missing(ident)
        return self.existing

    def put_document(self, scope, kind, ident, payload, expected):
        self.created.append((kind, ident, payload, expected))
        return dict(payload, revision=expected + 1)


def run_seed(monkeypatch, store, gcloud=None):
    seed = importlib.import_module("seed_allowance_ledger")
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.delenv("IMPERSONATE", raising=False)
    monkeypatch.setenv("ORG_ID", ORG)
    identities = []
    monkeypatch.setattr(ops.subprocess, "run", gcloud or seed_secrets())
    monkeypatch.setattr(seed, "repository", lambda impersonate: (identities.append(impersonate), store)[1])
    return seed.main(), identities


@pytest.mark.parametrize("existing", [None, {"sensitive": False, "reserved_total_micros": 12, "revision": 4}])
def test_seed_creates_the_ledger_only_when_absent(monkeypatch, capsys, existing):
    store = FakeStore(existing)
    code, identities = run_seed(monkeypatch, store)
    assert code == 0
    out, err = capsys.readouterr()
    # The ledger is the worker's own: its id, kind and scope as lane_allowance reads them.
    from specimen_digitization.application.domain import Scope
    from specimen_digitization.application.lane_allowance import LEDGER_KIND, ProgramLedger

    ident = ProgramLedger(None, Scope(organization_id=ORG, collection_id=COLLECTION)).ident
    assert ident == str(uuid5(NAMESPACE_URL, f"processing-lane-allowance:{ORG}/{COLLECTION}"))
    expected = [] if existing else [(LEDGER_KIND, ident, {"sensitive": False, "reserved_total_micros": 0}, 0)]
    assert store.created == expected
    assert identities == [""]  # The operator's own credentials unless IMPERSONATE names an account.
    assert ACTOR not in out + err and ORG not in out + err and COLLECTION not in out + err


def test_seed_refuses_without_the_actor_membership(monkeypatch):
    store = FakeStore(member=False)
    with pytest.raises(SystemExit, match="membership"):
        run_seed(monkeypatch, store)
    assert store.created == []


def test_seed_refuses_a_membership_role_the_ledger_write_rejects(monkeypatch):
    store = FakeStore(role="viewer")
    with pytest.raises(SystemExit, match="role"):
        run_seed(monkeypatch, store)
    assert store.created == []


@pytest.mark.parametrize("actor", [ACTOR + "\n", " " + ACTOR, ACTOR + "\x00"])
def test_seed_refuses_an_actor_uid_the_worker_would_not_match(monkeypatch, capsys, actor):
    store = FakeStore()
    with pytest.raises(SystemExit, match="exact Firebase UID") as refusal:
        run_seed(monkeypatch, store, seed_secrets(actor=actor))
    assert ACTOR not in str(refusal.value) + "".join(capsys.readouterr())
    assert store.created == []
    from specimen_digitization.application.lane_worker import drain_settings

    with pytest.raises(ValueError, match="SPECIMEN_WORKER_ACTOR_UID"):  # The worker refuses the same value.
        drain_settings({"SPECIMEN_WORKER_ACTOR_UID": actor})


@pytest.mark.parametrize("bindings", [
    json.dumps({COLLECTION: "botany"}),  # None bound to the ledger node.
    json.dumps({COLLECTION: "insects", "7d9a1c2b-3e4f-4a5b-8c6d-0e1f2a3b4c5d": "insects"}),  # Two.
    json.dumps({COLLECTION: "no-such-node"}),
    "{" + COLLECTION,
    json.dumps({"not-a-uuid": "insects"}),
])
def test_seed_takes_the_one_bound_ledger_collection_or_refuses(monkeypatch, capsys, bindings):
    store = FakeStore()
    with pytest.raises(SystemExit) as refusal:
        run_seed(monkeypatch, store, seed_secrets(bindings=bindings))
    message = str(refusal.value) + "".join(capsys.readouterr())
    assert COLLECTION not in message and "7d9a1c2b" not in message and "not-a-uuid" not in message
    assert store.created == []


# warm_sam.py

def test_warm_sam_retries_until_live_without_echoing_the_token(monkeypatch, capsys):
    warm = importlib.import_module("warm_sam")
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.setattr(ops.subprocess, "run", FakeGcloud())
    statuses, urls = [503, 429, 0, 200], []
    monkeypatch.setattr(warm, "get", lambda url, token: (urls.append((url, token)), statuses.pop(0))[1])
    monkeypatch.setattr(warm.time, "sleep", lambda seconds: None)
    assert warm.main() == 0
    out, err = capsys.readouterr()
    assert urls == [(S.SAM_URL + "/health/live", FAKE_TOKEN)] * 4
    assert FAKE_TOKEN not in out + err
    server = importlib.import_module("specimen_digitization.application.sam3_server")
    assert '"/health/live"' in inspect.getsource(server.create_app)


# scale_sam.py

def test_scale_sam_dry_run_sets_both_minimums():
    for wanted in ("0", "1"):
        code, output, commands = dry("scale_sam.py", wanted)
        assert code == 0, output
        [update] = find(commands, "gcloud", "run", "services", "update", "specimen-sam")
        assert f"--min={wanted}" in update and f"--min-instances={wanted}" in update
        assert f"--region={S.REGION}" in update and f"--project={S.PROJECT}" in update
    for wrong in ((), ("2",), ("-1",), ("one",), ("0", "1")):
        assert dry("scale_sam.py", *wrong)[0] != 0
    assert dry("scale_sam.py", "0", PROJECT="another-project")[0] != 0


def described(service_min, revision_min):
    """`gcloud run services describe --format=json`; gcloud removes a minimum annotation for 0."""
    def annotations(key, value):
        return {} if value == 0 else {key: str(value)}
    return json.dumps({"metadata": {"annotations": annotations("run.googleapis.com/minScale", service_min)},
                       "spec": {"template": {"metadata": {"annotations": annotations(
                           "autoscaling.knative.dev/minScale", revision_min)}}}})


@pytest.mark.parametrize("before, wanted, flags", [
    ((1, 1), 0, ["--min=0", "--min-instances=0"]),
    ((0, 0), 1, ["--min=1", "--min-instances=1"]),
    ((0, 1), 0, ["--min-instances=0"]),  # Only the level that differs changes.
    ((0, 0), 0, None),  # Already there: no update.
])
def test_scale_sam_changes_only_what_differs_and_prints_the_result(monkeypatch, capsys, before, wanted, flags):
    scale = importlib.import_module("scale_sam")
    monkeypatch.delenv("DRY_RUN", raising=False)
    state, updates = list(before), []
    monkeypatch.setattr(ops, "read", lambda argv: described(*state))

    def run(argv):
        updates.append(argv)
        state[:] = [wanted if any(a.startswith("--min=") for a in argv) else state[0],
                    wanted if any(a.startswith("--min-instances=") for a in argv) else state[1]]

    monkeypatch.setattr(ops, "run", run)
    assert scale.main([str(wanted)]) == 0
    if flags is None:
        assert updates == []
    else:
        [update] = updates
        assert update[:5] == ["gcloud", "run", "services", "update", "specimen-sam"]
        assert [arg for arg in update if arg.startswith("--min")] == flags
    assert f"service level {wanted}, revision level {wanted}" in capsys.readouterr().out


def test_scale_sam_fails_when_the_service_does_not_report_the_minimum(monkeypatch):
    scale = importlib.import_module("scale_sam")
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.setattr(ops, "read", lambda argv: described(1, 1))
    monkeypatch.setattr(ops, "run", lambda argv: None)  # The update did not take.
    with pytest.raises(SystemExit, match="minimum of 0"):
        scale.main(["0"])
    monkeypatch.setattr(ops, "read", lambda argv: None)
    with pytest.raises(SystemExit, match="not deployed"):
        scale.main(["1"])
