"""Actual HTTP duplicate races and shared SQL/SQLite circuit binding."""

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import threading

import pytest
from test_application import (
    HEADERS,
    PREFIX,
    TOKEN,
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    image_bytes,
)
from test_authority_runtime import running_api
from specimen_digitization.application.api import create_app, SYNTHETIC_TEXT
from specimen_digitization.application.domain import (
    Scope,
    Principal,
    Specimen,
    Asset,
    Run,
    Profile,
    LookupStatus,
)
from specimen_digitization.application.production import (
    SqlConnectRepository,
    sql_emulator_host,
    actor_uid,
)
from specimen_digitization.application.storage import (
    SQLiteRepository,
    LocalBlobs,
    digest,
)
from specimen_digitization.application.workflow import Workflow, SyntheticAdapters
from specimen_digitization.application.reliability import AdapterFailure


def repository(root, kind):
    if kind == "sql":
        if os.getenv("SPECIMEN_TEST_SQL_EMULATOR") != "true":
            pytest.skip("Requires seeded SQL Connect/PostgreSQL")
        return SqlConnectRepository(
            project="demo-specimen-data", emulator_host=sql_emulator_host()
        )
    return SQLiteRepository(root / "state.db")


@pytest.mark.parametrize("kind", ["sqlite", "sql"])
def test_same_source_concurrent_http_completion_is_authorized_duplicate(tmp_path, kind):
    repo = repository(tmp_path, kind)
    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="synthetic",
        repository=repo,
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        token=TOKEN,
    )
    data = image_bytes() + str(uuid4()).encode()
    checksum = hashlib.sha256(data).hexdigest()
    with running_api(app) as http:
        batch = http.post(
            PREFIX + "/batches",
            headers={**HEADERS, "Idempotency-Key": str(uuid4())},
            json={
                "collection_id": SYNTHETIC_COLLECTION,
                "display_name": "Synthetic race",
            },
        ).json()
        pending = []
        for _ in range(2):
            response = http.post(
                PREFIX + "/batches/" + batch["batch_id"] + "/items",
                headers={**HEADERS, "Idempotency-Key": str(uuid4())},
                json={
                    "client_item_id": str(uuid4()),
                    "filename": "synthetic.png",
                    "media_type": "image/png",
                    "size_bytes": len(data),
                    "width": 120,
                    "height": 80,
                    "sha256": checksum,
                },
            )
            assert response.status_code == 200, response.text
            item = response.json()
            assert item["state"] == "uploading"
            chunk = http.put(item["upload_url"], headers=HEADERS, content=data).json()
            pending.append(
                (
                    PREFIX + "/uploads/" + item["upload_id"] + "/complete",
                    {"expected_revision": chunk["revision"]},
                    {**HEADERS, "Idempotency-Key": str(uuid4())},
                )
            )

        def complete(item):
            return http.post(item[0], json=item[1], headers=item[2])

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(complete, pending))
        assert [result.status_code for result in results] == [200, 200], [
            result.text for result in results
        ]
        assert len({result.json()["specimen_id"] for result in results}) == 1
        assert (
            sum(result.json().get("upload_state") == "duplicate" for result in results)
            == 1
        )
        for item, result in zip(pending, results):
            assert complete(item).json() == result.json()
    actor_uid.set("synthetic-reviewer")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    assert len(repo.find_checksum(scope, checksum, True)) == 1


@pytest.mark.parametrize("kind", ["sqlite", "sql"])
def test_shared_circuit_survives_worker_restart_and_fences_half_probe(tmp_path, kind):
    repo = repository(tmp_path, kind)
    blobs = LocalBlobs(tmp_path / "blobs")
    principal = Principal(
        user_id="synthetic-reviewer",
        role="reviewer",
        scope=Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION),
    )
    actor_uid.set(principal.user_id)
    clock = [datetime.now(timezone.utc)]
    config = str(uuid4())
    items = []
    for index in range(6):
        data = image_bytes() + str(uuid4()).encode()
        ref = blobs.put(data)
        specimen = Specimen(
            scope=principal.scope,
            asset=Asset(
                sha256=hashlib.sha256(data).hexdigest(),
                blob_ref=ref,
                media_type="image/png",
                size_bytes=len(data),
                width=120,
                height=80,
                filename="synthetic.png",
                uploader=principal.user_id,
            ),
            run=Run(
                profile=Profile(synthetic=True),
                completed_steps=["pin_dependencies", "classify", "quality_check"],
                dependencies={"segmentation": {"test_configuration": config}},
            ),
        )
        items.append(repo.create(principal, specimen, str(uuid4()), digest(index)))
    state = {"calls": 0, "fail": True}
    entered = threading.Event()
    release = threading.Event()

    class Adapter(SyntheticAdapters):
        def segment(self, specimen):
            state["calls"] += 1
            if state["fail"]:
                raise AdapterFailure("provider_error", LookupStatus.PROVIDER)
            entered.set()
            assert release.wait(5)
            return super().segment(specimen)

    def worker_step(specimen):
        actor_uid.set(principal.user_id)
        # New worker instances share only persistence, not an in-memory breaker.
        return Workflow(
            repo, blobs, Adapter(blobs, SYNTHETIC_TEXT), clock=lambda: clock[0]
        ).step(principal, specimen.id)

    for specimen in items[:3]:
        worker_step(specimen)
    blocked = worker_step(items[3])
    assert state["calls"] == 3 and blocked.run.blocker.startswith("provider_circuit:")
    assert blocked.run.usage.external_calls == 0
    state["fail"] = False
    clock[0] += timedelta(seconds=31)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker_step, specimen) for specimen in items[4:]]
        assert entered.wait(5)
        done, _ = wait(futures, timeout=5, return_when=FIRST_COMPLETED)
        assert len(done) == 1 and next(iter(done)).result().run.blocker.startswith(
            "provider_circuit:"
        )
        assert state["calls"] == 4
        release.set()
        results = [future.result(timeout=5) for future in futures]
    assert sum("segment" in result.run.completed_steps for result in results) == 1
