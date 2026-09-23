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
from specimen_digitization.application.projection import derived_id
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
 labelRegions(where:{{runId:{{eq:"{run}"}}}}) {{ id domainRegionId sourceAssetId }}
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
        region = saved.run.regions[0]
        assert [bare(r["id"]) for r in found["labelRegions"]] == [bare(derived_id("region", saved.run.id, region.id))]
        assert found["labelRegions"][0]["domainRegionId"] == region.id
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
        # A second specimen whose readers returned byte-identical responses: the content-addressed
        # store keeps one object, and each specimen records it as its own asset.
        t = specimen(blobs, scope, principal.user_id)
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            created = repo.create(principal, t, "ingest:" + t.id, digest({"create": t.id}))
            other = repo.save(principal, processed(created, blobs), 1, "result:1:" + t.id, digest({"save": t.id}))
        assert not [r for r in caplog.records if "Projection" in r.getMessage()]
        theirs = rows(other)
        assert len(theirs["modelObservations"]) == 2
        raw = {x: {bare(a["id"]) for a in f["sourceAssets"] if a["kind"] == "raw_response"} for x, f in (("s", found), ("t", theirs))}
        assert len(raw["t"]) == 2 and not raw["s"] & raw["t"]
    finally:
        actor_uid.reset(token)


def test_saves_project_the_first_pass_harness_fields_and_decision(tmp_path, caplog):
    from test_projection_decisions import (
        DecidedTranscript,
        Difference,
        Handoff,
        HarnessRun,
        ToolCallRecord,
        TracedField,
    )
    from specimen_digitization.application.domain import (
        AuditEvent,
        Disposition,
        Lookup,
        LookupStatus,
        ValueState,
    )

    token = actor_uid.set("synthetic-reviewer")
    try:
        scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
        principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
        blobs = LocalBlobs(tmp_path / "blobs")
        repo = SqlConnectRepository(project="demo-specimen-data", emulator_host=sql_emulator_host(), graph_blobs=blobs)
        s = specimen(blobs, scope, principal.user_id)
        s.run = HarnessRun()
        created = repo.create(principal, s, "ingest:" + s.id, digest({"create": s.id}))
        run = processed(created, blobs).run
        left, right = run.observations
        region = run.regions[0]
        call_raw = blobs.put(b'{"selected": "left"}')
        call = left.model_copy(update={"id": Observation.model_fields["id"].default_factory(), "route_id": "first-pass", "literal_text": "", "raw_ref": call_raw, "raw_sha256": call_raw})
        run.transcripts = [
            DecidedTranscript(
                **run.transcripts[0].model_dump(),
                decision_kind="first_pass",
                selected_observation_id=left.id,
                first_pass_call=call,
                differences=[Difference(number=1, spans={left.id: {"start": 11, "end": 12, "text": "l"}, right.id: {"start": 11, "end": 12, "text": "1"}}, verdict=left.id, material=True)],
                # A picked decision hands over its decided transcript only (G19).
                handoffs=[Handoff(observation_id=left.id, role="decided_transcript", handed_text=left.literal_text)],
            )
        ]
        record = blobs.put(b'{"place_id": "fixture-place", "outcome": "success", "response_sha256": "8888"}')
        found = Lookup(provider="google-maps-geocoding", adapter_version="geocode-1", query={"address": "Chicago, Ill."}, status=LookupStatus.SUCCESS, metadata={"locator": "place/fixture-place"}, raw_ref=record, digest="8" * 64)
        run.lookups = [found]
        run.tool_calls = [
            ToolCallRecord(call_key=f"lookup:geocode:decided_transcript:{region.id}:-:0af70af70af70af7:1", phase="lookup", tool="geocode", tool_version="t1", source="google-maps-geocoding", field_keys=["country", "city"], input_source="decided_transcript", region_id=region.id, arguments={"query": "Chicago, Ill."}, outcome="success", result={"candidates": [{"place_id": "fixture-place"}]}, evidence_id=found.id, started_at="2026-09-23T12:00:00+00:00", completed_at="2026-09-23T12:00:01+00:00"),
        ]
        run.fields = {
            "city": TracedField(state=ValueState.SUPPORTED, literal="Chicago", authority_id="fixture-place", evidence_ids=[found.id], evidence_relations={found.id: "supports"}, input_source="decided_transcript", source_region_id=region.id),
            "date_visited_from": TracedField(state=ValueState.SUPPORTED, literal="VII-46", parsed="1946-07", input_source="decided_transcript", source_region_id=region.id, precision="month", century_rule="date-rules-v1:two_digit_year_century=1900"),
            "county": TracedField(),
        }
        run.field_groups = {"city": "mandatory", "date_visited_from": "mandatory", "county": "mandatory"}
        run.disposition, run.reasons = Disposition.REVIEW, ["mandatory_unresolved:county"]
        run.disposition_summary = "Needs human review: county unresolved."
        created.audit.append(AuditEvent(actor=principal.user_id, action="review_field", reason="Checked the label", after={"literal": "Cook"}))
        with caplog.at_level(logging.WARNING):
            saved = repo.save(principal, created, 1, "result:1:" + s.id, digest({"save": s.id}))
        assert not [r for r in caplog.records if "Projection" in r.getMessage()], [r.getMessage() for r in caplog.records]
        runid = saved.run.id
        found_rows = admin(f"""query {{
 modelObservations(where:{{runId:{{eq:"{runid}"}}}}) {{ id independent stepKey }}
 transcriptionVersions(where:{{runId:{{eq:"{runid}"}}}}) {{ id decisionKind selectedObservationId firstPassObservationId unresolved spans }}
 harnessInputs(where:{{runId:{{eq:"{runid}"}}}}) {{ role handedText note }}
 evidenceItems(where:{{runId:{{eq:"{runid}"}}}}) {{ id source locator responseSha256 }}
 toolCalls(where:{{runId:{{eq:"{runid}"}}}}) {{ fieldKeys source outcome transcriptionVersionId evidenceId }}
 fieldCandidates(where:{{runId:{{eq:"{runid}"}}}}) {{ id fieldKey parsedValue inputSource sourceObservationId sourceTranscriptionId }}
 candidateEvidences(where:{{evidenceId:{{eq:"{found.id}"}}}}) {{ candidateId relation }}
 recordVersions(where:{{runId:{{eq:"{runid}"}}}}) {{ id disposition summary reasonCodes }}
 reviewDecisions(where:{{specimenId:{{eq:"{s.id}"}}}}) {{ baseRevision resultingRevision correction }}
}}""")
        assert sorted(o["independent"] for o in found_rows["modelObservations"]) == [False, True, True]
        (decision,) = found_rows["transcriptionVersions"]
        assert decision["decisionKind"] == "first_pass" and decision["unresolved"] is False
        assert bare(decision["selectedObservationId"]) == bare(left.id)
        assert bare(decision["firstPassObservationId"]) == bare(call.id)
        assert [h["role"] for h in found_rows["harnessInputs"]] == ["decided_transcript"]
        (evidence,) = found_rows["evidenceItems"]
        assert (evidence["locator"], evidence["responseSha256"]) == ("place/fixture-place", "8" * 64)
        (tool,) = found_rows["toolCalls"]
        assert tool["fieldKeys"] == ["country", "city"] and bare(tool["evidenceId"]) == bare(found.id)
        candidates = {c["fieldKey"]: c for c in found_rows["fieldCandidates"]}
        assert candidates["date_visited_from"]["parsedValue"] == {"value": "1946-07", "precision": "month", "century_rule": "date-rules-v1:two_digit_year_century=1900"}
        assert bare(candidates["date_visited_from"]["sourceTranscriptionId"]) == bare(decision["id"])
        assert candidates["date_visited_from"]["sourceObservationId"] is None
        (link,) = found_rows["candidateEvidences"]
        assert (bare(link["candidateId"]), link["relation"]) == (bare(candidates["city"]["id"]), "supports")
        (record_row,) = found_rows["recordVersions"]
        assert record_row["disposition"] == "needs_human_review" and record_row["summary"] == "Needs human review: county unresolved."
        (review,) = found_rows["reviewDecisions"]
        assert (review["baseRevision"], review["resultingRevision"]) == (1, 2)
        assert review["correction"]["action"] == "review_field"
        counts_after = admin(f"""query {{
 resolvedFields(where:{{recordVersionId:{{eq:"{record_row['id']}"}}}}) {{ fieldKey fieldGroup }}
 validationFindings(where:{{recordVersionId:{{eq:"{record_row['id']}"}}}}) {{ ruleId fieldKey }}
}}""")
        assert sorted(r["fieldKey"] for r in counts_after["resolvedFields"]) == ["city", "county", "date_visited_from"]
        assert counts_after["validationFindings"] == [{"ruleId": "mandatory_unresolved", "fieldKey": "county"}]
    finally:
        actor_uid.reset(token)
