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
    environment.update(DRY_RUN="1", SOURCE_SHA=SHA, **env)
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
                 "--max-instances=1", "--min-instances=1", "--timeout=300s", "--clear-volumes",
                 f"--service-account={S.SAM['service_account']}",
                 "--startup-probe=tcpSocket.port=8080,periodSeconds=10,timeoutSeconds=10,failureThreshold=60",
                 "--add-volume-mount=volume=checkpoint,mount-path=/model-cache"):
        assert flag in service
    prefix = f"application/sha256/{S.SAM_CHECKPOINT_SHA256}/sam3-cache"
    assert (f"--add-volume=name=checkpoint,type=cloud-storage,bucket={S.BUCKET},readonly=true,"
            f"mount-options=only-dir={prefix}") in service
    assert "# env SPECIMEN_SAM3_ENABLE=authorized-run" in output
    assert "# env HF_HUB_OFFLINE=1" in output
    assert "--set-secrets=LOGFIRE_TOKEN=specimen-worker-logfire:1" in service and "HF_TOKEN" not in output
    assert not any(arg.startswith("--allow-unauthenticated") for arg in service)


def test_deploy_refuses_another_project_and_a_bad_minimum():
    assert dry("deploy.py", "sam", PROJECT="another-project")[0] != 0
    assert dry("deploy.py", "sam", SAM_MIN_INSTANCES="2")[0] != 0


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
    assert mount == ["only-dir=" + deploy.checkpoint_prefix(S.SAM_CHECKPOINT_SHA256)]


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
    # The bucket's resource conditions are kept exactly; owner_grants' secret-version pins are not (per-secret grants).
    expected = [(g.member, g.role, g.resource, g.condition if g.resource[0] == "bucket" else None) for g in theirs]
    assert sorted(mine) == sorted(expected) and len(set(mine)) == len(mine)
    assert any(resource[0] == "secret" for _, _, resource, _ in mine)


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
    assert find(commands, "gcloud", "secrets", "versions", "access", "latest", "--secret=huggingface-runtime-token")


class FakeGcloud:
    """Answers the few gcloud commands the scripts send; records every argv."""

    def __init__(self, listings=(), secret=FAKE_TOKEN):
        self.calls, self.listings, self.secret = [], list(listings), secret

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        out = ""
        if argv[:4] == ["gcloud", "secrets", "versions", "access"]:
            out = self.secret + "\n"
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

def test_seed_dry_run_prints_the_ledger_id_per_spec():
    code, output, commands = dry("seed_allowance_ledger.py", ORG_ID=ORG, COLLECTION_ID=COLLECTION)
    assert code == 0, output
    assert output.rstrip().endswith(str(uuid5(NAMESPACE_URL, f"processing-lane-allowance:{ORG}/{COLLECTION}")))
    assert find(commands, "gcloud", "secrets", "versions", "access", "1", "--secret=specimen-worker-actor-uid")
    assert dry("seed_allowance_ledger.py", ORG_ID=ORG.upper(), COLLECTION_ID=COLLECTION)[0] != 0
    assert dry("seed_allowance_ledger.py", ORG_ID=ORG)[0] != 0


class FakeStore:
    def __init__(self, existing=None, member=True):
        self.existing, self.member, self.created = existing, member, []

    def memberships(self, uid):
        return [{"organization_id": ORG, "collection_id": COLLECTION}] if self.member else []

    def document(self, scope, kind, ident):
        from specimen_digitization.application.storage import Missing

        assert (scope.organization_id, scope.collection_id, kind) == (ORG, COLLECTION, "worker_cursor")
        if self.existing is None:
            raise Missing(ident)
        return self.existing

    def put_document(self, scope, kind, ident, payload, expected):
        self.created.append((kind, ident, payload, expected))
        return dict(payload, revision=expected + 1)


@pytest.mark.parametrize("existing", [None, {"sensitive": False, "reserved_total_micros": 12, "revision": 4}])
def test_seed_creates_the_ledger_only_when_absent(monkeypatch, capsys, existing):
    seed = importlib.import_module("seed_allowance_ledger")
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.setenv("ORG_ID", ORG)
    monkeypatch.setenv("COLLECTION_ID", COLLECTION)
    actor = "worker-actor-" + "x" * 12
    store = FakeStore(existing)
    monkeypatch.setattr(ops.subprocess, "run", FakeGcloud(secret=actor))
    monkeypatch.setattr(seed, "repository", lambda impersonate: store)
    assert seed.main() == 0
    out, err = capsys.readouterr()
    ident = str(uuid5(NAMESPACE_URL, f"processing-lane-allowance:{ORG}/{COLLECTION}"))
    expected = [] if existing else [("worker_cursor", ident, {"sensitive": False, "reserved_total_micros": 0}, 0)]
    assert store.created == expected
    assert actor not in out + err and ORG not in out + err and COLLECTION not in out + err


def test_seed_refuses_without_the_actor_membership(monkeypatch):
    seed = importlib.import_module("seed_allowance_ledger")
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.setenv("ORG_ID", ORG)
    monkeypatch.setenv("COLLECTION_ID", COLLECTION)
    store = FakeStore(member=False)
    monkeypatch.setattr(ops.subprocess, "run", FakeGcloud(secret="worker-actor"))  # pragma: allowlist secret (test value)
    monkeypatch.setattr(seed, "repository", lambda impersonate: store)
    with pytest.raises(SystemExit, match="membership"):
        seed.main()
    assert store.created == []


# warm_sam.py

def test_warm_sam_retries_until_live_without_echoing_the_token(monkeypatch, capsys):
    warm = importlib.import_module("warm_sam")
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.setattr(ops.subprocess, "run", FakeGcloud())
    statuses, urls = [503, 0, 200], []
    monkeypatch.setattr(warm, "get", lambda url, token: (urls.append((url, token)), statuses.pop(0))[1])
    monkeypatch.setattr(warm.time, "sleep", lambda seconds: None)
    assert warm.main() == 0
    out, err = capsys.readouterr()
    assert urls == [(S.SAM_URL + "/health/live", FAKE_TOKEN)] * 3
    assert FAKE_TOKEN not in out + err
    server = importlib.import_module("specimen_digitization.application.sam3_server")
    assert '"/health/live"' in inspect.getsource(server.create_app)
