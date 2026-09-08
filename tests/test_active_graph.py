"""Large supported evidence graphs retain full provenance outside compact rows."""

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_application import (
    HEADERS,
    PREFIX,
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    TOKEN,
    image_bytes,
    intake,
)
from test_hardening_concurrency import repository

from specimen_digitization.application.active_graph import (
    GRAPH_LIMIT,
    WORKSPACE_LIMIT,
    GraphTooLarge,
    save_recoverably,
)
from specimen_digitization.application.api import SYNTHETIC_TEXT, create_app
from specimen_digitization.application.domain import (
    Principal,
    Region,
    Scope,
)
from specimen_digitization.application.storage import (
    Conflict,
    LocalBlobs,
    SQLiteRepository,
    digest,
)
from specimen_digitization.application.workflow import SyntheticAdapters


class MultiLabels(SyntheticAdapters):
    def segment(self, specimen):
        return [
            Region(
                asset_id=specimen.asset.id,
                x=index * 12,
                y=0,
                width=12,
                height=80,
                order=index,
                method="synthetic",
                version="fixture-v1",
            )
            for index in range(10)
        ]


def app_at(root, repo=None):
    blobs = LocalBlobs(root / "blobs")
    repo = repo or SQLiteRepository(root / "state.db")
    return create_app(
        mode="synthetic",
        repository=repo,
        blobs=blobs,
        adapters=MultiLabels(
            blobs,
            "Synthetic unstructured context " + ("z" * 9000) + "\n" + SYNTHETIC_TEXT,
        ),
        token=TOKEN,
    )


@pytest.mark.parametrize("kind", ["sqlite", "sql"])
def test_multilabel_graph_beyond_old_cap_restarts_and_preserves_hash_history(
    tmp_path, kind, monkeypatch
):
    import test_application

    if kind == "sql":
        import httpx
        import sys
        import specimen_digitization.application.api as api_module
        from specimen_digitization.application.production import sql_emulator_host

        collection = str(uuid4())
        host = sql_emulator_host()
        assert host and (host.startswith("127.0.0.1:") or host.startswith("localhost:"))
        query = f'''mutation @transaction {{
          collection_insert(data:{{organizationId:"{SYNTHETIC_ORG}",id:"{collection}",name:"Isolated graph test"}})
          collectionMember_insert(data:{{organizationId:"{SYNTHETIC_ORG}",collectionId:"{collection}",uid:"synthetic-reviewer",active:true,role:"reviewer",canViewSensitive:true}})
        }}'''
        seeded = httpx.post(
            f"http://{host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service:executeGraphql",
            json={"query": query},
        ).json()
        assert not seeded.get("errors") and not seeded.get("code"), seeded
        for module in (test_application, api_module, sys.modules[__name__]):
            monkeypatch.setattr(module, "SYNTHETIC_COLLECTION", collection)

    original = image_bytes() + str(uuid4()).encode()
    monkeypatch.setattr(test_application, "image_bytes", lambda: original)
    repo = repository(tmp_path, kind)
    app = app_at(tmp_path, repo)
    with TestClient(app) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        work = http.get(path + "/workspace", headers=HEADERS)
        assert work.status_code == 200, work.text[:300]
        data = work.json()
        assert data["disposition"] == "needs_human_review", data["blocker"]
        assert len(data["observations"]) == 20 and len(data["transcriptions"]) == 10
        assert data["active_graph"]["size_bytes"] > 256 * 1024
        scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
        p = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
        from specimen_digitization.application.production import actor_uid

        actor_uid.set(p.user_id)
        before = repo.get(scope, row["specimen_id"])
        prior = before.version
        info = repo.version_info(scope, before.id, prior)
        assert info["run_sha256"] == digest(data["run"])
        if kind == "sqlite":
            with repo.connect() as db:
                packed = json.loads(
                    db.execute(
                        "SELECT payload FROM records WHERE id=?", (before.id,)
                    ).fetchone()[0]
                )
        else:
            packed = repo.execute(
                "GetSnapshot", dict(repo.variables(scope), id=before.id, revision=prior)
            )["specimenSnapshot"]["snapshot"]
        assert (
            len(json.dumps(packed).encode()) < 256 * 1024
            and packed["run"]["observations"] == []
        )
        exact = http.get(data["active_graph_url"], headers=HEADERS)
        assert exact.status_code == 200 and exact.json()["run"] == data["run"]
        assert len(exact.content) <= GRAPH_LIMIT
        approved = http.post(
            path + "/decisions",
            headers=HEADERS,
            json={
                "kind": "approve",
                "reason": "Synthetic full multi-label evidence inspected",
                "expected_revision": prior,
                "base_record_version_id": data["record_version_id"],
            },
        )
        assert (
            approved.status_code == 200 and approved.json()["disposition"] == "cleared"
        ), approved.text[:300]
        assert (
            http.get(path + f"/history/{prior}", headers=HEADERS).json()["run"]
            == data["run"]
        )
        actor_uid.set(p.user_id)
        with pytest.raises(Conflict):
            repo.save(p, before, prior, "stale-graph", digest("stale"))
        assert repo.get(scope, before.id).version == approved.json()["revision"]
    restarted = app_at(tmp_path, repository(tmp_path, kind))
    with TestClient(restarted) as http:
        restored = http.get(path + "/workspace", headers=HEADERS).json()
        assert (
            restored["disposition"] == "cleared" and len(restored["observations"]) == 20
        )
        assert (
            restored["observations"][0]["literal_text"]
            == data["observations"][0]["literal_text"]
        )
    if kind == "sql":
        import subprocess
        import sys

        code = """
import json,sys
from pathlib import Path
from specimen_digitization.application.production import SqlConnectRepository,sql_emulator_host,actor_uid
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.application.domain import Scope
actor_uid.set('synthetic-reviewer')
repo=SqlConnectRepository(project='demo-specimen-data',emulator_host=sql_emulator_host(),graph_blobs=LocalBlobs(Path(sys.argv[1])))
rows=repo.list(Scope(organization_id=sys.argv[2],collection_id=sys.argv[3]))
assert len(rows)==1 and rows[0].id==sys.argv[4]
assert len(rows[0].run.observations)==20 and rows[0].run.disposition.value=='cleared'
print(rows[0].version)
"""
        subprocess.run(
            [
                sys.executable,
                "-c",
                code,
                str(tmp_path / "blobs"),
                SYNTHETIC_ORG,
                SYNTHETIC_COLLECTION,
                before.id,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )


def test_graph_limit_is_atomic_and_oversized_workspace_has_complete_artifact_and_cancel(
    tmp_path,
):
    app = app_at(tmp_path)
    with TestClient(app) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        repo = app.state.workflow.repository
        p = Principal(
            user_id="synthetic-reviewer",
            scope=Scope(
                organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION
            ),
            role="reviewer",
        )
        before = repo.get(p.scope, row["specimen_id"])
        revision = before.version
        huge = before.model_copy(deep=True)
        huge.run.observations[0].literal_text = "x" * (GRAPH_LIMIT + 1)
        with pytest.raises(GraphTooLarge):
            repo.save(p, huge, revision, "too-large", digest("large"))
        assert repo.get(p.scope, before.id).version == revision
        recovered = save_recoverably(
            repo, p, huge, revision, "too-large", digest("large")
        )
        assert recovered.run.blocker == "active_graph_limit_exceeded"
        assert (
            recovered.run.observations[0].literal_text
            == before.run.observations[0].literal_text
        )
        # Supported complete graph can exceed the smaller interactive response cap.
        large = recovered.model_copy(deep=True)
        large.run.observations[0].literal_text = "q" * (WORKSPACE_LIMIT // 2)
        large = repo.save(p, large, large.version, "large-readable", digest("readable"))
        response = http.get(path + "/workspace", headers=HEADERS)
        assert response.status_code == 413, response.text[:300]
        details = response.json()["error"]["details"]
        assert details["revision"] == large.version
        assert len(response.content) < 4096
        artifact = http.get(details["artifact_url"], headers=HEADERS)
        assert (
            artifact.status_code == 200
            and len(artifact.json()["run"]["observations"][0]["literal_text"])
            == WORKSPACE_LIMIT // 2
        )
        summary = http.get(details["summary_url"], headers=HEADERS).json()
        cancel = http.post(
            PREFIX + "/runs/" + summary["active_run_id"] + "/actions",
            headers=HEADERS,
            json={
                "action": "cancel",
                "reason": "Synthetic oversized-response recovery",
                "expected_revision": summary["revision"],
            },
        )
        assert cancel.status_code == 200 and cancel.json()["status"] == "cancelled", (
            cancel.text[:300]
        )
        with pytest.raises(Conflict):
            metadata = large.active_graph
            (repo.graph_blobs.root / metadata["blob_ref"]).write_bytes(b"tampered")
            repo.version(p.scope, large.id, large.version)


@pytest.mark.parametrize(
    "fault",
    ["scope", "revision", "run", "summary", "missing", "bytes", "size", "digest"],
)
def test_graph_reconstruction_rejects_identity_and_content_faults(tmp_path, fault):
    from specimen_digitization.application.active_graph import pack, read_graph

    app = app_at(tmp_path)
    with TestClient(app) as http:
        row = intake(http)
    repo = app.state.workflow.repository
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    specimen = repo.get(scope, row["specimen_id"])
    payload = pack(specimen, repo.graph_blobs)
    assert read_graph(payload, repo.graph_blobs)[1] == specimen.run.model_dump(
        mode="json"
    )
    metadata = payload["active_graph"]
    if fault == "scope":
        payload["scope"]["collection_id"] = "another-collection"
    elif fault == "revision":
        metadata["revision"] += 1
    elif fault == "run":
        metadata["run_id"] = "another-run"
    elif fault == "summary":
        payload["run"]["stage"] = "cancelled"
    elif fault == "missing":
        (repo.graph_blobs.root / metadata["blob_ref"]).unlink()
    elif fault == "bytes":
        (repo.graph_blobs.root / metadata["blob_ref"]).write_bytes(b"{}")
    elif fault == "size":
        metadata["size_bytes"] = GRAPH_LIMIT + 1
    elif fault == "digest":
        metadata["run_sha256"] = "incorrect"
    with pytest.raises(Conflict, match="Active graph integrity"):
        read_graph(payload, repo.graph_blobs)
