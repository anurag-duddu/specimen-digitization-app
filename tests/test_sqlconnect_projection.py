"""Opt-in: the projection writer against real PostgreSQL and SQL Connect; never cloud."""

from __future__ import annotations

import logging
import os

import pytest
import requests

from specimen_digitization.application.api import SYNTHETIC_COLLECTION, SYNTHETIC_ORG
from specimen_digitization.application.domain import (
    Asset,
    Observation,
    Principal,
    Profile,
    Region,
    Run,
    Scope,
    Specimen,
    Transcript,
)
from specimen_digitization.application.production import (
    SqlConnectRepository,
    actor_uid,
    sql_emulator_host,
)
from specimen_digitization.application.storage import LocalBlobs, digest

pytestmark = pytest.mark.skipif(
    os.getenv("SPECIMEN_TEST_SQL_EMULATOR") != "true",
    reason="Requires explicitly started isolated SQL Connect/PostgreSQL emulator",
)
PROFILE = {"id": "zoology_insects_slides", "version": "1.0.0", "segmentation_settings": {"concept_prompt": "label"}}


def admin(query: str) -> dict:
    """Read rows directly, as the acceptance lab does, bypassing the connector."""
    host = sql_emulator_host()
    url = f"http://{host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service:executeGraphql"
    body = requests.post(url, json={"query": query}, headers={"Authorization": "Bearer owner"}, timeout=30).json()
    assert not body.get("errors"), body
    return body["data"]


def bare(value: str) -> str:
    return value.replace("-", "")


def specimen(blobs: LocalBlobs, scope: Scope, uploader: str) -> Specimen:
    image = os.urandom(64)
    ref = blobs.put(image)
    return Specimen(
        scope=scope,
        asset=Asset(
            sha256=ref,
            blob_ref=ref,
            media_type="image/png",
            size_bytes=len(image),
            width=1000,
            height=520,
            filename="projection-synthetic.png",
            uploader=uploader,
        ),
        run=Run(),
    )


def processed(s: Specimen, blobs: LocalBlobs) -> Specimen:
    run = s.run
    run.profile = Profile(id="zoology_insects_slides", version="1.0.0", routes=("handwriting-qwen", "handwriting-muse"))
    run.profile_snapshot = PROFILE
    run.dependencies = {"profile_snapshot_sha256": digest(PROFILE)}
    region = Region(asset_id=s.asset.id, x=10, y=20, width=390, height=160, order=0, method="sam3", version="rev-1")
    readings = []
    for route, text in (("handwriting-qwen", "Chicago, Ill."), ("handwriting-muse", "Chicago, Il1.")):
        raw = blobs.put(b'{"route": "%s", "text": "%s"}' % (route.encode(), text.encode()))
        readings.append(
            Observation(
                region_id=region.id,
                route_id=route,
                model_id=f"model/{route}",
                provider="synthetic",
                prompt_version="p" * 64,
                input_sha256="b" * 64,
                literal_text=text,
                raw_ref=raw,
                raw_sha256=raw,
                completion_state="validated_output",
            )
        )
    run.regions = [region]
    run.observations = readings
    run.transcripts = [
        Transcript(
            region_id=region.id,
            observation_ids=[o.id for o in readings],
            alternatives=[o.literal_text for o in readings],
            resolved=False,
            disagreement_ratio=1 / 13,
            alignment_status="difference",
            alignment_algorithm="bounded-levenshtein-fraction-v1",
        )
    ]
    return s


def rows(s: Specimen) -> dict:
    run = s.run.id
    return admin(f"""query {{
 pipelineRun(key:{{organizationId:"{SYNTHETIC_ORG}",collectionId:"{SYNTHETIC_COLLECTION}",id:"{run}"}}) {{ specimenId profileVersionId }}
 labelRegions(where:{{runId:{{eq:"{run}"}}}}) {{ id sourceAssetId }}
 modelObservations(where:{{runId:{{eq:"{run}"}}}}) {{ id stepKey routeId independent rawAssetId }}
 readingComparisons(where:{{runId:{{eq:"{run}"}}}}) {{ ratio editDistance lengthBasis }}
 sourceAssets(where:{{specimenId:{{eq:"{s.id}"}}}}) {{ id kind byteSize width }}
}}""")


def counts(found: dict) -> dict:
    return {table: len(value) if isinstance(value, list) else value for table, value in found.items()}


def test_saves_project_every_stage_one_to_five_row_once(tmp_path, caplog):
    token = actor_uid.set("synthetic-reviewer")
    try:
        scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
        principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
        blobs = LocalBlobs(tmp_path / "blobs")
        repo = SqlConnectRepository(project="demo-specimen-data", emulator_host=sql_emulator_host(), graph_blobs=blobs)
        s = specimen(blobs, scope, principal.user_id)
        with caplog.at_level(logging.WARNING):
            created = repo.create(principal, s, "ingest:" + s.id, digest({"create": s.id}))
            saved = repo.save(principal, processed(created, blobs), 1, "result:1:" + s.id, digest({"save": s.id}))
        assert not [r for r in caplog.records if "Projection" in r.getMessage()]
        found = rows(saved)
        assert bare(found["pipelineRun"]["specimenId"]) == bare(s.id)
        assert [bare(r["id"]) for r in found["labelRegions"]] == [bare(saved.run.regions[0].id)]
        assert bare(found["labelRegions"][0]["sourceAssetId"]) == bare(s.asset.id)
        observations = sorted(found["modelObservations"], key=lambda o: o["routeId"])
        assert [o["routeId"] for o in observations] == ["handwriting-muse", "handwriting-qwen"]
        assert all(o["independent"] for o in observations)
        assert {bare(o["id"]) for o in observations} == {bare(o.id) for o in saved.run.observations}
        assert found["readingComparisons"] == [{"ratio": 1 / 13, "editDistance": 1, "lengthBasis": 13}]
        kinds = sorted(a["kind"] for a in found["sourceAssets"])
        assert kinds == ["original", "raw_response", "raw_response"]
        assert all(a["width"] is None for a in found["sourceAssets"] if a["kind"] == "raw_response")
        # A new process writes everything once more; the primary keys absorb the repeats.
        fresh = SqlConnectRepository(project="demo-specimen-data", emulator_host=sql_emulator_host(), graph_blobs=blobs)
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            fresh.write_projection(scope, saved)
        assert not [r for r in caplog.records if "Projection" in r.getMessage()]
        assert counts(rows(saved)) == counts(found)
    finally:
        actor_uid.reset(token)
