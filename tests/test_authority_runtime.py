"""Application review and durable receipts around actual local TCP authority reads."""

import json

# ruff: noqa: F811 -- pytest fixture injection shares the imported fixture name
from fastapi.testclient import TestClient
from pydantic import SecretStr

from test_authority_registry import authority_server, source  # noqa: F401
from test_application import intake, HEADERS, PREFIX, TOKEN
from specimen_digitization.application.api import (
    create_app,
    SYNTHETIC_TEXT,
    SYNTHETIC_ORG,
    SYNTHETIC_COLLECTION,
)
from specimen_digitization.application.authority_registry import AuthorityRegistry
from specimen_digitization.application.collection_runtime import application_registry
from specimen_digitization.application.parties import PartiesAdapter, PartiesConnection
from specimen_digitization.application.storage import SQLiteRepository, LocalBlobs
from specimen_digitization.application.workflow import SyntheticAdapters
from specimen_digitization.application.domain import Scope


def assembly(tmp_path, authority_server, price=0, repository=None):
    state, client = authority_server
    state["body"] = json.dumps(
        {
            "hits": 1,
            "matches": [
                {
                    "id": "emu:/fmnh/eparties/7",
                    "version": 1,
                    "data": {"NamFullName": "Synthetic Collector"},
                }
            ],
        }
    ).encode()
    blobs = LocalBlobs(tmp_path / "blobs")
    repo = repository or SQLiteRepository(tmp_path / "state.sqlite3")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    source_registry = AuthorityRegistry(
        version="synthetic-source-registry",
        sources=(source(True, scopes=((SYNTHETIC_ORG, SYNTHETIC_COLLECTION),)),),
    )
    observed_intents = []

    class ObservedParties(PartiesAdapter):
        def lookup(self, query):
            current = repo.list(scope)[0]
            observed_intents.append(
                any(
                    m["state"] == "intent"
                    for m in current.run.authority_receipts.values()
                )
            )
            return super().lookup(query)

    parties = ObservedParties(
        source_registry,
        blobs,
        PartiesConnection(
            source_id="parties",
            source_system="emu",
            connection_id="synthetic-read",
            tenant="fmnh",
            environment="synthetic",
        ),
        SecretStr("synthetic-token"),
        client,
    )
    registry = application_registry(True)
    registry = registry.model_copy(
        update={
            "profiles": (
                registry.profiles[0].model_copy(
                    update={
                        "tools": ("taxonomy_verifier", "parties"),
                        "data_sources": ("gbif-col-xr", "parties"),
                    }
                ),
            )
        }
    )
    text = SYNTHETIC_TEXT.replace("synthetic:eparties:1", "Synthetic Collector")
    app = create_app(
        mode="synthetic",
        repository=repo,
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, text),
        token=TOKEN,
        profile_registry=registry,
        authority_tools={"parties": parties},
        authority_cost_reservations={"parties": price},
    )
    return app, state, observed_intents


def decision(http, path, current, kind, key, **extra):
    return http.post(
        path + "/decisions",
        headers=dict(HEADERS, **{"Idempotency-Key": key}),
        json={
            "kind": kind,
            "reason": "Synthetic authority review decision",
            "expected_revision": current["revision"],
            "base_record_version_id": current["record_version_id"],
            **extra,
        },
    )


def test_parties_requires_qualified_selection_and_persists_intent_before_tcp(
    tmp_path, authority_server
):
    app, state, observed = assembly(tmp_path, authority_server)
    with TestClient(app) as http:
        row = intake(http)
        path = PREFIX + f"/specimens/{row['specimen_id']}"
        work = http.get(path + "/workspace", headers=HEADERS).json()
        assert observed == [True]
        assert len(state["requests"]) == 1
        assert work["disposition"] == "needs_human_review", work["blocker"]
        assert work["run"]["authority_usage"]["tool_calls"] == 1
        assert (
            list(work["run"]["authority_receipts"].values())[0]["state"] == "completed"
        )
        phases = work["run"]["phase_results"]
        assert set(phases) == {
            "parse",
            "plan",
            "lookup",
            "resolve",
            "normalize",
            "validate",
            "finalize",
        }
        lookup = http.get(path + "/phases/lookup", headers=HEADERS).json()
        parties = next(
            item for item in lookup["lookups"] if item["source_id"] == "parties"
        )
        assert parties["status"] == "ambiguous"
        assert parties["candidates"][0]["identity"]["module"] == "eparties"
        response = decision(http, path, work, "approve", "no-choice")
        assert response.status_code == 200, response.text
        work = response.json()
        assert work["disposition"] == "needs_human_review"
        assert (
            "parties_identity_resolution_required:identified_by_irn"
            in work["reason_codes"]
        )
        invalid = decision(
            http,
            path,
            work,
            "authority_resolution",
            "wrong-choice",
            target_id="identified_by_irn",
            after={"tool_id": "parties", "identifier": "emu:/other/eparties/7"},
        )
        assert invalid.status_code == 422
        selected = decision(
            http,
            path,
            work,
            "authority_resolution",
            "selected",
            target_id="identified_by_irn",
            after={"tool_id": "parties", "identifier": "emu:/fmnh/eparties/7"},
        )
        assert selected.status_code == 200, selected.text
        work = selected.json()
        assert (
            work["fields"]["identified_by_irn"]["authority_identity"]["connection_id"]
            == "synthetic-read"
        )
        approved = decision(http, path, work, "approve", "approved")
        assert approved.status_code == 200, approved.text
        assert approved.json()["disposition"] == "cleared", approved.json()[
            "reason_codes"
        ]
        assert (
            len(state["requests"]) == 1
        )  # Pure review phases never reissue the authority call.
        retained = http.get(path + "/phases/lookup", headers=HEADERS).json()
        assert (
            next(
                item for item in retained["lookups"] if item["source_id"] == "parties"
            )["status"]
            == "ambiguous"
        )


def test_unknown_authority_price_blocks_without_network(tmp_path, authority_server):
    app, state, observed = assembly(tmp_path, authority_server, price=None)
    with TestClient(app) as http:
        row = intake(http)
        work = http.get(
            PREFIX + f"/specimens/{row['specimen_id']}/workspace", headers=HEADERS
        ).json()
        assert work["status"] == "processing_blocked"
        assert work["blocker"] == "only_known_free_authority_tools_supported"
        assert not state["requests"]
        assert not observed


def test_source_correction_invalidates_authority_and_retains_old_revision(
    tmp_path, authority_server
):
    app, state, _ = assembly(tmp_path, authority_server)
    with TestClient(app) as http:
        row = intake(http)
        path = PREFIX + f"/specimens/{row['specimen_id']}"
        work = http.get(path + "/workspace", headers=HEADERS).json()
        revision = work["revision"]
        old_receipts = work["run"]["authority_receipts"].copy()
        transcript = work["run"]["transcripts"][0]
        response = decision(
            http,
            path,
            work,
            "transcription",
            "changed-source",
            target_id=transcript["region_id"],
            after={
                "text": transcript["text"].replace(
                    "Synthetic Collector", "Synthetic New Collector"
                ),
                "state": "supported",
            },
        )
        assert response.status_code == 200, response.text
        current = http.get(path + "/workspace", headers=HEADERS).json()
        assert len(state["requests"]) == 2, current["blocker"]
        assert len(current["run"]["authority_receipts"]) == 2
        old = http.get(path + f"/history/{revision}", headers=HEADERS).json()
        assert old["run"]["authority_receipts"] == old_receipts
        artifact = http.get(
            path
            + f"/authority-results/parties?field_key=identified_by_irn&revision={revision}",
            headers=HEADERS,
        )
        assert artifact.status_code == 200
        assert (
            http.get(
                path + "/authority-results/parties?field_key=taxon", headers=HEADERS
            ).status_code
            == 404
        )
        assert (
            http.get(
                path + "/authority-results/parties/raw?field_key=identified_by_irn",
                headers=HEADERS,
            ).content
            == state["body"]
        )


from contextlib import contextmanager


@contextmanager
def running_api(app):
    import socket, threading, time, httpx, uvicorn

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [listener]}, daemon=True
    )
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30) as http:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(0.02)
            assert server.started
            yield http
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()


@__import__("pytest").mark.skipif(
    __import__("os").getenv("SPECIMEN_TEST_SQL_EMULATOR") != "true",
    reason="Requires seeded SQL Connect/PostgreSQL",
)
def test_sql_authority_review_and_search_metadata(
    tmp_path, authority_server, monkeypatch
):
    import io
    from uuid import uuid4
    from PIL import Image, PngImagePlugin
    import test_application
    from specimen_digitization.application.production import (
        SqlConnectRepository,
        sql_emulator_host,
    )

    repo = SqlConnectRepository(
        project="demo-specimen-data", emulator_host=sql_emulator_host()
    )
    output = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("synthetic_case", str(uuid4()))
    Image.new("RGB", (120, 80), "white").save(output, format="PNG", pnginfo=metadata)
    monkeypatch.setattr(test_application, "image_bytes", lambda: output.getvalue())
    monkeypatch.setitem(HEADERS, "Idempotency-Key", "sql-authority-" + str(uuid4()))
    app, state, _ = assembly(tmp_path, authority_server, repository=repo)
    with running_api(app) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        work = http.get(path + "/workspace", headers=HEADERS).json()
        import time

        for _ in range(100):
            if work["status"] in {"completed", "processing_blocked"}:
                break
            time.sleep(0.05)
            work = http.get(path + "/workspace", headers=HEADERS).json()
        assert work["disposition"] == "needs_human_review", work["blocker"]
        selected = decision(
            http,
            path,
            work,
            "authority_resolution",
            "sql-selection-" + str(uuid4()),
            target_id="identified_by_irn",
            after={
                "tool_id": "parties",
                "field_key": "identified_by_irn",
                "identifier": "emu:/fmnh/eparties/7",
            },
        )
        assert selected.status_code == 200, selected.text
        approved = decision(
            http, path, selected.json(), "approve", "sql-approve-" + str(uuid4())
        )
        assert (
            approved.status_code == 200 and approved.json()["disposition"] == "cleared"
        ), approved.text
        params = {
            "collection_id": SYNTHETIC_COLLECTION,
            "specimen_id": row["specimen_id"],
            "state": "completed",
            "disposition": "cleared",
            "profile_id": work["profile_id"],
            "limit": 1,
        }
        listing = http.get(PREFIX + "/specimens", params=params, headers=HEADERS)
        assert listing.status_code == 200, listing.text
        item = listing.json()["items"][0]
        assert item["created_at"] == approved.json()["created_at"]
        assert item["domain_created_at"] == approved.json()["domain_created_at"]
        assert item["revision"] == approved.json()["revision"]
        assert item["uploader_id"] == "synthetic-reviewer"
        assert item["risk"] is None
        assert approved.json()["run"]["review_risk"]["composite"] is None
        # Human approval does not manufacture a measured risk score. Numeric
        # ranges exclude unmeasured NULL values instead of treating them as zero.
        ranged = http.get(
            PREFIX + "/specimens",
            params={**params, "risk_min": 0, "risk_max": 100},
            headers=HEADERS,
        )
        assert ranged.status_code == 200 and ranged.json()["items"] == [], ranged.text
        following = http.get(
            PREFIX + "/specimens",
            params={**params, "cursor": listing.json()["next_cursor"]},
            headers=HEADERS,
        )
        assert following.status_code == 200 and following.json()["items"] == [], (
            following.text
        )
        assert len(state["requests"]) == 1


def test_missing_authority_literal_is_review_not_provider_failure(
    tmp_path, authority_server
):
    app, state, _ = assembly(tmp_path, authority_server)
    app.state.workflow.adapters.text = app.state.workflow.adapters.text.replace(
        "identified_by_irn: Synthetic Collector", "identified_by_irn: "
    )
    with TestClient(app) as http:
        row = intake(http)
        work = http.get(
            PREFIX + "/specimens/" + row["specimen_id"] + "/workspace", headers=HEADERS
        ).json()
        assert work["disposition"] == "needs_human_review", work["blocker"]
        assert work["blocker"] is None
        assert not state["requests"]
        assert (
            "authority_source_literal_unresolved:identified_by_irn"
            in work["reason_codes"]
        )
