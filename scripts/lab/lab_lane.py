"""Drive the app on this workstation for the lab runner (docs/execution/golive/LAB.md)."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import threading
import time
import uuid

from fastapi.testclient import TestClient
from PIL import Image

from specimen_digitization.application.api import SYNTHETIC_COLLECTION, SYNTHETIC_ORG, create_app
from specimen_digitization.application.domain import Scope
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
from specimen_digitization.application.workflow import SyntheticAdapters

import lab_checks

REPO = Path(__file__).resolve().parents[2]
PG_BIN = Path(os.getenv("POSTGRES_BIN", "/opt/homebrew/opt/postgresql@18/bin"))
PREFIX = f"/v1/organizations/{SYNTHETIC_ORG}"
CHUNK = 4 * 1024 * 1024
USE_REVIEWED_REGIONS = "sam3_serving_contract_not_configured_use_reviewed_regions"
# G31: the owner classified these ten pilot slides not sensitive against PRD.md 724's criteria (2026-09-23), as
# CONTRACTS.md 169-170 requires. Every other slide stays Sensitive: a run with the production adapters refuses
# it before any upload (production_lane), so its image never reaches a model provider (PRD.md 67, PLAN.md 182).
# The synthetic adapters may still drive one in tests.
NOT_SENSITIVE = frozenset(f"subject_1055263{n}" for n in range(21, 31))
READER = "synthetic-reviewer"


class LabError(RuntimeError):
    pass


def refuse_sensitive(subject):
    if subject not in NOT_SENSITIVE:
        raise LabError(f"{subject} is not one of the ten pilot slides declared not sensitive (G31); a run with the "
                       "production adapters never processes a Sensitive slide (PRD.md 67, PLAN.md 182)")


class AppLane:
    """The app factory behind an in-process ASGI client, as the client and worker use it."""

    def __init__(self, root, *, adapters_factory, persistence, segmentation, subject):
        self.root, self.adapters_factory = Path(root), adapters_factory
        self.persistence, self.segmentation, self.subject = persistence, segmentation, subject
        self.token, self.nonce, self.emulator = secrets.token_urlsafe(24), uuid.uuid4().hex[:12], None
        self.sensitive = subject not in NOT_SENSITIVE  # G31

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True)
        self.blobs = LocalBlobs(self.root / "blobs")
        adapters = self.adapters_factory(self.blobs)
        if type(adapters) is not SyntheticAdapters:  # G31, where the adapters are built (learning 21)
            refuse_sensitive(self.subject)
        self.interrupted = self.in_request = False
        self.previous_sigint = None
        if threading.current_thread() is threading.main_thread():
            self.previous_sigint = signal.signal(signal.SIGINT, self.on_sigint)
        try:
            if self.persistence == "sqlite":
                self.repository = SQLiteRepository(self.root / "state.sqlite3")
            else:
                self.emulator = Emulator(self.root / "emulator")
                self.emulator.start()
                self.repository = SqlConnectRepository(
                    project="demo-specimen-data", emulator_host=self.emulator.host
                )
            app = create_app(mode="synthetic", repository=self.repository, blobs=self.blobs,
                             adapters=adapters, token=self.token)
            self.client = TestClient(app, raise_server_exceptions=False).__enter__()
        except BaseException:
            try:
                if self.emulator:  # __exit__ never runs when __enter__ raises
                    self.emulator.stop()
            finally:
                self.restore_sigint()
            raise
        return self

    def __exit__(self, *exc):
        try:
            self.client.__exit__(*exc)
        finally:
            try:
                if self.emulator:
                    self.emulator.stop()
            finally:
                self.restore_sigint()

    def on_sigint(self, signum, frame):
        """The test client swallows a BaseException raised during one of the app's requests (a 500 if the app had
        not started its response, otherwise the endpoint's own response), so a first Ctrl-C during a request is
        held until the request returns, when call() raises it. Outside a request, a Ctrl-C is raised at once."""
        if self.in_request and not self.interrupted:
            self.interrupted = True
            return
        raise KeyboardInterrupt

    def restore_sigint(self):
        if self.previous_sigint is not None:
            signal.signal(signal.SIGINT, self.previous_sigint)
            self.previous_sigint = None

    def call(self, method, path, key=None, headers=None, **kwargs):
        headers = {"Authorization": "Bearer " + self.token, **(headers or {})}
        if key:
            headers["Idempotency-Key"] = f"lab:{self.nonce}:{key}"
        self.in_request = True
        try:
            response = self.client.request(method, PREFIX + path, headers=headers, **kwargs)
        finally:
            self.in_request = False
        if self.interrupted:
            raise KeyboardInterrupt  # the Ctrl-C held while the app's request ran
        if response.status_code >= 400:
            raise LabError(f"{method} {path} returned {response.status_code}: {response.text[:300]}")
        return response.json()

    def ingest(self, filename, data, media_type):
        width, height = Image.open(io.BytesIO(data)).size
        batch = self.call("POST", "/batches", key="batch", json={
            "collection_id": SYNTHETIC_COLLECTION, "display_name": "Acceptance lab " + self.subject,
            "sensitive": self.sensitive})
        item = self.call("POST", f"/batches/{batch['batch_id']}/items", key="item", json={
            "client_item_id": self.subject, "filename": filename, "media_type": media_type, "sensitive": self.sensitive,
            "size_bytes": len(data), "width": width, "height": height,
            "sha256": hashlib.sha256(data).hexdigest()})
        if item["state"] != "uploading":
            raise LabError(f"upload state {item['state']}; this lab database already holds the image")
        upload, revision = f"/uploads/{item['upload_id']}", item["revision"]
        for offset in range(0, len(data), CHUNK):
            revision = self.call("PUT", upload + "/content", content=data[offset:offset + CHUNK],
                                 headers={"Upload-Offset": str(offset)})["revision"]
        # The app drains the workflow in a background task; the ASGI client returns after it.
        self.call("POST", upload + "/complete", key="complete", json={"expected_revision": revision})
        return item["specimen_id"]

    def workspace(self, specimen_id):
        return self.call("GET", f"/specimens/{specimen_id}/workspace")

    def process(self, specimen_id, deadline):
        actions = []
        for _ in range(50):
            view = self.workspace(specimen_id)
            run = view["run"]
            if run["stage"] == "finalized":
                return actions
            if run["stage"] == "processing_blocked":
                if (run["blocker"] == USE_REVIEWED_REGIONS and self.segmentation == "reviewed-region"
                        and not actions):
                    actions.append(self.draw_regions(specimen_id, view))
                    continue
                return actions
            wait_until = run.get("next_retry_at") or run.get("lease_until")
            if wait_until:
                pause = (datetime.fromisoformat(wait_until) - datetime.now(timezone.utc)).total_seconds()
                if time.monotonic() + pause > deadline:
                    raise TimeoutError(f"{run['stage']} until {wait_until} is past the lab deadline")
                time.sleep(max(0.0, pause) + 1)
            elif time.monotonic() > deadline:
                raise TimeoutError(f"stage {run['stage']} at the lab deadline")
            self.call("POST", f"/specimens/{specimen_id}/process")  # the worker's tick
        raise LabError("the record did not settle in 50 lab ticks")

    def draw_regions(self, specimen_id, view):
        asset = view["asset"]
        width, height = asset["width"], asset["height"]
        regions = []
        for order, (lo, hi) in enumerate(lab_checks.label_boxes(self.subject)):
            x = round(lo * width)
            regions.append({"id": str(uuid.uuid4()), "asset_id": asset["id"], "x": x, "y": 0,
                            "width": round(hi * width) - x, "height": height, "order": order,
                            "method": "reviewer_rectangle", "version": "lab-substitute-v1"})
        reason = (f"Lab substitute after {USE_REVIEWED_REGIONS}: SAM 3 has no local mode "
                  "until S3 T3; the lab's label boxes for this slide")
        self.call("POST", f"/specimens/{specimen_id}/regions", key="regions", json={
            "expected_revision": view["revision"], "reason": reason,
            "base_run_id": view["run"]["id"], "regions": regions})
        boxes = [[r["x"], r["y"], r["width"], r["height"]] for r in regions]
        return {"action": lab_checks.SUBSTITUTE, "reason": reason, "boxes": boxes}

    def collect(self, specimen_id):
        actor_uid.set(READER)
        scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
        specimen = self.repository.get(scope, specimen_id)
        artifacts = {}
        for run in [*specimen.previous_runs, specimen.run]:
            for o in run.observations:
                artifacts[f"responses/{o.id}.json"] = self.blobs.get(o.raw_ref)
                if o.input_crop_ref:
                    artifacts.setdefault(f"crops/{o.region_id}.png", self.blobs.get(o.input_crop_ref))
            for r in run.regions:
                if r.crop_ref:
                    artifacts.setdefault(f"crops/{r.id}.png", self.blobs.get(r.crop_ref))
            artifacts.update(receipt_blobs(run, self.blobs))
            if run.segmentation.get("blob_ref"):
                artifacts[f"segmentation/{run.id}.json"] = self.blobs.get(run.segmentation["blob_ref"])
        return {"snapshot": specimen.model_dump(mode="json"), "workspace": self.workspace(specimen_id),
                "artifacts": artifacts, "rows": self.emulator.dump() if self.emulator else {},
                "actions": []}


def receipt_blobs(run, blobs):
    """The blobs the run's receipts point to (a receipt keeps only blob_ref, sha256, state and call_id),
    so the runner can scan the requests themselves for D4."""
    found = {}
    for key, receipt in (run.authority_receipts or {}).items():
        if isinstance(receipt, dict) and receipt.get("blob_ref"):
            name = re.sub(r"[^A-Za-z0-9._-]", "_", str(receipt.get("call_id") or key))
            found[f"receipts/{name}.json"] = blobs.get(receipt["blob_ref"])
    return found


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Emulator:
    """A disposable PostgreSQL and SQL Connect emulator (scripts/data/serve-local.sh) for one run."""

    def __init__(self, root):
        self.root, self.ready, self.retained = Path(root), threading.Event(), None

    def start(self, timeout=180):
        self.root.mkdir(parents=True, exist_ok=True)
        self.pg_port, dc_port = free_port(), free_port()
        self.host = f"127.0.0.1:{dc_port}"
        # The script's cluster stays in the system TMPDIR: PostgreSQL's socket path is capped at 103 bytes.
        env = dict(os.environ, SPECIMEN_TEST_PG_PORT=str(self.pg_port), SPECIMEN_TEST_DC_PORT=str(dc_port))
        try:
            self.process = subprocess.Popen(
                ["bash", "scripts/data/serve-local.sh"], cwd=REPO, env=env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
            self.pumping = threading.Thread(target=self.pump, daemon=True)
            self.pumping.start()
            deadline = time.monotonic() + timeout
            while not self.ready.wait(1):
                if self.process.poll() is not None or time.monotonic() > deadline:
                    raise LabError(f"the SQL Connect emulator did not start; see {self.root}")
        except BaseException:  # a Ctrl-C too: the emulator runs in its own session, which SIGINT never reaches
            self.stop()
            raise
        return self

    def pump(self):
        with (self.root / "serve-local.log").open("w") as log:
            for line in self.process.stdout:
                log.write(line)
                log.flush()
                if "SQL Connect ready" in line:
                    self.ready.set()
                if "retained: " in line:
                    self.retained = Path(line.split("retained: ", 1)[1].strip())

    def psql(self, sql):
        result = subprocess.run(
            [str(PG_BIN / "psql"), "-h", "127.0.0.1", "-p", str(self.pg_port), "-At",
             "-d", "specimen-digitization-database", "-v", "ON_ERROR_STOP=1", "-c", sql],
            capture_output=True, text=True, check=True, timeout=60)
        return result.stdout

    def dump(self):
        tables = self.psql("select tablename from pg_tables where schemaname = 'public' order by 1")
        return {t: json.loads(self.psql(f'select coalesce(json_agg(t), \'[]\') from "{t}" t'))
                for t in tables.split()}

    def stop(self):
        """Stops the emulator and keeps its logs; safe to call again, or before it fully started."""
        process = getattr(self, "process", None)
        if process is None:
            return
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=60)
        pumping = getattr(self, "pumping", None)
        if pumping is not None and pumping.is_alive():
            pumping.join(timeout=10)
        if self.retained and self.retained.name.startswith("specimen-data-serve."):
            for log in self.retained.glob("*.log"):
                shutil.copy(log, self.root / log.name)
            shutil.rmtree(self.retained, ignore_errors=True)  # the run's disposable cluster


def production_lane(state, options, environment):
    refuse_sensitive(options.subject)  # before any adapter is built or any image uploaded
    from specimen_digitization.application.production import ProductionAdapters

    return AppLane(state, adapters_factory=ProductionAdapters, persistence=options.persistence,
                   segmentation=options.segmentation, subject=options.subject)
