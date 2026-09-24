"""A synthetic run for the thread (DATA_CONTRACT.md 8, S5 T3), and GetRunThreadV1's rows for it.

`rows` answers GetRunThreadV1 from the projection writer's own writes the way Data Connect does:
UUIDs as 32 hex characters without dashes, timestamps in UTC with six fractional digits, every
row nested under the run found by its id and its specimen, and a decision, candidate or record
version only when its id is given. `tests/test_sqlconnect_thread.py` checks it against the real
operation, so the canonical example built from it is what the API serves.

S3's and S4's fields ride on stand-in subclasses until they reach the shared domain model.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from specimen_digitization.application.domain import (
    Asset,
    BudgetUsage,
    Disposition,
    Evidence,
    Lookup,
    LookupStatus,
    Observation,
    Profile,
    Region,
    Scope,
    Specimen,
    ValueState,
)
from specimen_digitization.application.storage import digest

from test_projection_decisions import (
    DecidedTranscript,
    Difference,
    Finding,
    Handoff,
    HarnessRun,
    ToolCallRecord,
    TracedField,
)


class ThreadRun(HarnessRun):
    """S3's coverage check, program allowance and paid calls (LANE.md T2b, T3)."""

    coverage_check: dict | None = None
    program_allowance: dict | None = None
    paid_calls: list[dict] = []


PROFILE = {
    "id": "zoology_insects_slides",
    "version": "1.0.0",
    "model_routes": ["handwriting-qwen", "handwriting-muse"],
    "segmentation_settings": {
        "prompt": "label",
        "coverage": {"version": "coverage-check-v1", "min_label_regions": 1, "max_label_regions": 3},
    },
}
TRACE = "0af7" * 8
TIMES = {n: f"2026-09-23T12:0{n}:00+00:00" for n in range(10)}
Put = Callable[[str, bytes], str]


def hexid(value):
    """A UUID as Data Connect returns it."""
    return None if value is None else str(value).replace("-", "")


def stamp(value):
    """A timestamp as Data Connect returns it."""
    if value is None:
        return None
    moment = datetime.fromisoformat(value).astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def rows(written, specimen_id: str, run_id: str, keys: dict) -> dict:
    """GetRunThreadV1's data for everything these writes put in SQL."""
    tables: dict[str, dict] = {}
    traces = {}
    for write in written:
        if write.operation == "RecordRunTraceV1":
            traces.setdefault(write.variables["id"], write.variables["traceId"])
            continue
        # A primary key keeps the first row written; a replay is absorbed.
        tables.setdefault(write.operation, {}).setdefault(write.variables["id"], write.variables)

    def table(operation, **match):
        return [
            row
            for row in tables.get(operation, {}).values()
            if all(row.get(name) == value for name, value in match.items())
        ]

    data = {"specimen": {"id": hexid(specimen_id)}, "runs": []}
    found = table("AppendPipelineRunV2", id=run_id, specimenId=specimen_id)
    if not found:
        return data
    run = found[0]
    assets = tables.get("AppendSourceAssetV2", {})
    regions = {row["id"]: row for row in table("AppendLabelRegionV2", runId=run_id)}
    observations = {row["id"]: row for row in table("AppendModelObservationV2", runId=run_id)}
    decisions = {row["id"]: row for row in table("AppendTranscriptionVersionV2", runId=run_id)}
    current = {name: set(ids) for name, ids in keys.items()}

    def region(row_id):
        row = regions.get(row_id)
        return None if row is None else {"domainRegionId": row["domainRegionId"]}

    def through(parents, parent_id):
        parent = parents.get(parent_id)
        return None if parent is None else {"region": region(parent["regionId"])}

    def candidate(row):
        return {
            "id": hexid(row["id"]),
            "fieldKey": row["fieldKey"],
            "state": row["state"],
            "literalValue": row["literalValue"],
            "parsedValue": row["parsedValue"],
            "normalizedValue": row["normalizedValue"],
            "authorityId": row["authorityId"],
            "inputSource": row["inputSource"],
            "sourceObservationId": hexid(row["sourceObservationId"]),
            "sourceTranscription": through(decisions, row["sourceTranscriptionId"]),
            "sourceObservation": through(observations, row["sourceObservationId"]),
            "links": [
                {"evidenceId": hexid(link["evidenceId"]), "relation": link["relation"]}
                for link in table("AppendCandidateEvidenceV2", candidateId=row["id"])
            ],
        }

    def record(row):
        return {
            "id": hexid(row["id"]),
            "disposition": row["disposition"],
            "policyVersion": row["policyVersion"],
            "reasonCodes": row["reasonCodes"],
            "summary": row["summary"],
            "fields": [
                {
                    "fieldKey": field["fieldKey"],
                    "state": field["state"],
                    "fieldGroup": field["fieldGroup"],
                    "candidateId": hexid(field["candidateId"]),
                }
                for field in table("AppendResolvedFieldV2", recordVersionId=row["id"])
            ],
            "findings": [
                {
                    "ruleId": finding["ruleId"],
                    "ruleVersion": finding["ruleVersion"],
                    "severity": finding["severity"],
                    "outcome": finding["outcome"],
                    "fieldKey": finding["fieldKey"],
                    "reasonCode": finding["reasonCode"],
                    "evidenceIds": None
                    if finding["evidenceIds"] is None
                    else [hexid(e) for e in finding["evidenceIds"]],
                }
                for finding in table("AppendValidationFindingV2", recordVersionId=row["id"])
            ],
        }

    data["runs"] = [
        {
            "id": hexid(run_id),
            "traceId": run["traceId"] or traces.get(run_id),
            "regions": [
                {
                    "id": hexid(row["id"]),
                    "domainRegionId": row["domainRegionId"],
                    "geometry": row["geometry"],
                    "ordinal": row["ordinal"],
                }
                for row in regions.values()
            ],
            "observations": [
                {
                    "id": hexid(row["id"]),
                    "regionId": hexid(row["regionId"]),
                    "routeId": row["routeId"],
                    "modelVersion": row["modelVersion"],
                    "provider": row["provider"],
                    "promptVersion": row["promptVersion"],
                    "literalText": row["literalText"],
                    "unreadableSpans": row["unreadableSpans"],
                    "outcome": row["outcome"],
                    "independent": row["independent"],
                    "rawAssetId": hexid(row["rawAssetId"]),
                    "rawAsset": {"sha256": assets[row["rawAssetId"]]["sha256"]},
                }
                for row in observations.values()
            ],
            "comparisons": [
                {
                    "regionId": hexid(row["regionId"]),
                    "leftObservationId": hexid(row["leftObservationId"]),
                    "rightObservationId": hexid(row["rightObservationId"]),
                    "algorithm": row["algorithm"],
                    "ratio": row["ratio"],
                    "editDistance": row["editDistance"],
                    "lengthBasis": row["lengthBasis"],
                    "status": row["status"],
                    "reasons": row["reasons"],
                }
                for row in table("AppendReadingComparisonV1", runId=run_id)
            ],
            "decisions": [
                {
                    "id": hexid(row["id"]),
                    "regionId": hexid(row["regionId"]),
                    "decisionKind": row["decisionKind"],
                    "selectedObservationId": hexid(row["selectedObservationId"]),
                    "firstPassObservationId": hexid(row["firstPassObservationId"]),
                    "literalText": row["literalText"],
                    "unresolved": row["unresolved"],
                    "rationale": row["rationale"],
                }
                for row in decisions.values()
                if row["id"] in current["decisionIds"]
            ],
            "handoffs": [
                {
                    "transcriptionVersionId": hexid(row["transcriptionVersionId"]),
                    "observationId": hexid(row["observationId"]),
                    "role": row["role"],
                    "handedText": row["handedText"],
                    "note": row["note"],
                }
                for row in table("AppendHarnessInputV1", runId=run_id)
                if row["transcriptionVersionId"] in current["decisionIds"]
            ],
            "evidence": [
                {
                    "id": hexid(row["id"]),
                    "source": row["source"],
                    "locator": row["locator"],
                    "outcome": row["outcome"],
                    "capturedAt": stamp(row["capturedAt"]),
                }
                for row in table("AppendEvidenceItemV2", runId=run_id)
            ],
            "toolCalls": [
                {
                    "callKey": row["callKey"],
                    "phase": row["phase"],
                    "tool": row["tool"],
                    "toolVersion": row["toolVersion"],
                    "source": row["source"],
                    "fieldKeys": row["fieldKeys"],
                    "inputSource": row["inputSource"],
                    "attempt": row["attempt"],
                    "arguments": row["arguments"],
                    "outcome": row["outcome"],
                    "result": row["result"],
                    "evidenceId": hexid(row["evidenceId"]),
                    "startedAt": stamp(row["startedAt"]),
                    "completedAt": stamp(row["completedAt"]),
                    "observationId": hexid(row["observationId"]),
                    "transcriptionVersion": through(decisions, row["transcriptionVersionId"]),
                    "observation": through(observations, row["observationId"]),
                }
                for row in table("AppendToolCallV1", runId=run_id)
            ],
            "candidates": [
                candidate(row)
                for row in table("AppendFieldCandidateV2", runId=run_id)
                if row["id"] in current["candidateIds"]
            ],
            "records": [
                record(row)
                for row in table("AppendRecordVersionV2", runId=run_id)
                if row["id"] in current["recordIds"]
            ],
        }
    ]
    return data


def fixed(n: int) -> str:
    """A readable synthetic UUID for the canonical example."""
    return f"00000000-0000-4000-8000-{n:012d}"


def labelled(label: str, data: bytes) -> str:
    """A stored blob's ref for the canonical example: a low-entropy digest and generation 7."""
    return f"{label * 64}:7"


def synthetic_run(
    put: Put = labelled,
    ident: Callable[[int], str] = fixed,
    scope: Scope = Scope(organization_id="org-1", collection_id="coll-1"),
) -> Specimen:
    """A two-label slide read to its queue decision, covering every part of section 8.

    The left label's readings differ by one character and the first pass picks one; Google
    confirms the locality on the decided transcript and finds nothing for the county. The right
    label's readings differ materially, so the first pass picks none (G19) and each reader keeps
    its verbatim (G27, G28); GBIF confirms one reader's taxon and decides it, and Catalogue of
    Life contradicts it, which is a warning (G23). `put` stores a blob and returns its ref.
    """
    image = put("a", b"synthetic slide image")
    asset = Asset(
        id=ident(1),
        sha256=image.partition(":")[0],
        blob_ref=image,
        media_type="image/jpeg",
        size_bytes=2048,
        width=4000,
        height=3000,
        filename="synthetic-slide.jpg",
        uploader="synthetic-uploader",
        created_at=TIMES[0],
    )
    run = ThreadRun(
        id=ident(2),
        created_at=TIMES[0],
        profile=Profile(
            id="zoology_insects_slides",
            version="1.0.0",
            routes=("handwriting-qwen", "handwriting-muse"),
        ),
        profile_snapshot=PROFILE,
        profile_registry_version="registry-1",
        dependencies={"profile_snapshot_sha256": digest(PROFILE)},
        stage="finalized",
        trace_id=TRACE,
        segmentation={
            "model_id": "facebook/sam3",
            "model_revision": "sam3-fixture-revision",
            "settings": {"prompt": "label", "parameters": {"label_threshold": 0.5}},
        },
        coverage_check={
            "version": "coverage-check-v1",
            "outcome": "confirmed",
            "region_count": 2,
            "min_label_regions": 1,
            "max_label_regions": 3,
            "cross_check": {
                "concept": "text",
                "threshold": 0.5,
                "min_inside_fraction": 0.5,
                "counted": 2,
                "uncovered_boxes": [],
            },
            "reason_codes": [],
            "evidence_ref": put("e", b"segmentation response"),
            "evidence_sha256": "e" * 64,
            "checked_at": TIMES[1],
        },
        program_allowance={
            "allowance_micros": 5000000,
            "reserved_total_micros": 60000,
            "remaining_micros": 4940000,
            "ledger_revision": 4,
            "at": TIMES[2],
        },
        usage=BudgetUsage(actual_cost_micros=5200),
    )
    left = Region(
        id=ident(10), asset_id=asset.id, x=180, y=1210, width=1320, height=640, order=0,
        method="sam3", version="sam3-fixture-revision",
    )
    right = Region(
        id=ident(11), asset_id=asset.id, x=2480, y=1190, width=1360, height=700, order=1,
        method="sam3", version="sam3-fixture-revision", rotation_quarter_turns=1,
    )

    def reading(n, region, route, text, label, spans=()):
        raw = put(label, f"{route} {text}".encode())
        return Observation(
            id=ident(n),
            region_id=region.id,
            route_id=route,
            model_id=f"model/{route}",
            provider="fixture-provider",
            prompt_version="p" * 64,
            input_sha256="b" * 64,
            literal_text=text,
            unreadable_spans=list(spans),
            raw_ref=raw,
            raw_sha256=raw.partition(":")[0],
            completion_state="validated_output",
            created_at=TIMES[3],
        )

    left_qwen = reading(20, left, "handwriting-qwen", "Chicago, Ill. VII-46 Cook Co.", "c")
    left_muse = reading(21, left, "handwriting-muse", "Chicago, Il1. VII-46 Cook Co.", "d", ["Il1."])
    right_qwen = reading(22, right, "handwriting-qwen", "Aedes aegypti L.", "1")
    right_muse = reading(23, right, "handwriting-muse", "Aedes aegypti Linn.", "2")
    left_call = reading(24, left, "first-pass", "", "f")
    right_call = reading(25, right, "first-pass", "", "3")
    run.regions = [left, right]
    run.observations = [left_qwen, left_muse, right_qwen, right_muse]
    run.transcripts = [
        DecidedTranscript(
            region_id=left.id,
            text=left_qwen.literal_text,
            observation_ids=[left_qwen.id, left_muse.id],
            alternatives=[],
            resolved=True,
            reason="The crop shows a lowercase l.",
            disagreement_ratio=1 / 29,
            alignment_status="difference",
            alignment_algorithm="bounded-levenshtein-fraction-v1",
            alignment_reasons=["one_substitution"],
            decision_kind="first_pass",
            selected_observation_id=left_qwen.id,
            first_pass_call=left_call,
            differences=[
                Difference(
                    number=1,
                    spans={
                        left_qwen.id: {"start": 11, "end": 12, "text": "l"},
                        left_muse.id: {"start": 11, "end": 12, "text": "1"},
                    },
                    verdict=left_qwen.id,
                    material=True,
                )
            ],
            handoffs=[
                Handoff(
                    observation_id=left_qwen.id,
                    role="decided_transcript",
                    handed_text=left_qwen.literal_text,
                )
            ],
        ),
        DecidedTranscript(
            region_id=right.id,
            text=None,
            observation_ids=[right_qwen.id, right_muse.id],
            alternatives=[right_qwen.literal_text, right_muse.literal_text],
            resolved=False,
            reason="The authority abbreviation is L. or Linn.; the crop does not settle it.",
            disagreement_ratio=3 / 19,
            alignment_status="difference",
            alignment_algorithm="bounded-levenshtein-fraction-v1",
            decision_kind="first_pass",
            selected_observation_id=None,
            first_pass_call=right_call,
            differences=[
                Difference(
                    number=1,
                    spans={
                        right_qwen.id: {"start": 14, "end": 16, "text": "L."},
                        right_muse.id: {"start": 14, "end": 19, "text": "Linn."},
                    },
                    verdict="uncertain",
                    material=True,
                )
            ],
            handoffs=[
                Handoff(
                    observation_id=right_qwen.id,
                    role="raw_reading",
                    handed_text=right_qwen.literal_text,
                    note="Reads the authority as L.",
                ),
                Handoff(
                    observation_id=right_muse.id,
                    role="raw_reading",
                    handed_text=right_muse.literal_text,
                    note="Reads the authority as Linn.",
                ),
            ],
        ),
    ]
    place = Lookup(
        id=ident(30),
        provider="google-maps-geocoding",
        adapter_version="geocode-1",
        query={"address": "Chicago, Ill."},
        status=LookupStatus.SUCCESS,
        candidates=[{"place_id": "fixture-place"}],
        metadata={"locator": "place/fixture-place", "source_version": "v1"},
        raw_ref=put("9", b"place record"),
        digest="8" * 64,
        retrieved_at=TIMES[4],
    )
    nowhere = Lookup(
        id=ident(31),
        provider="google-maps-geocoding",
        adapter_version="geocode-1",
        query={"address": "Cook Co."},
        status=LookupStatus.NO_MATCH,
        metadata={"source_version": "v1"},
        raw_ref=put("7", b"no match record"),
        digest="6" * 64,
        retrieved_at=TIMES[4],
    )
    gbif = Lookup(
        id=ident(32),
        provider="gbif",
        adapter_version="gbif-1",
        query={"name": "Aedes aegypti L."},
        status=LookupStatus.SUCCESS,
        candidates=[{"usage_key": 1651891}],
        metadata={"locator": "gbif/species/1651891", "source_version": "backbone-2026"},
        raw_ref=put("5", b"gbif response"),
        digest="4" * 64,
        retrieved_at=TIMES[5],
    )
    col = Lookup(
        id=ident(33),
        provider="catalogue-of-life",
        adapter_version="col-1",
        query={"name": "Aedes aegypti L."},
        status=LookupStatus.SUCCESS,
        candidates=[{"id": "fixture-col-taxon"}],
        metadata={"locator": "col/taxon/fixture-col-taxon", "source_version": "col-2026"},
        raw_ref=put("0", b"col response"),
        digest="1" * 64,
        retrieved_at=TIMES[5],
    )
    coverage = Evidence(
        id=ident(34),
        kind="coverage",
        source="label-coverage-check",
        locator="coverage/coverage-check-v1",
        excerpt="",
        raw_ref=run.coverage_check["evidence_ref"],
        digest="e" * 64,
        created_at=TIMES[1],
    )
    run.lookups = [place, nowhere, gbif, col]
    run.evidence = [coverage]

    def call(tool, source, fields, source_kind, arguments, outcome, result, evidence, *, region=None, reading=None):
        # {phase}:{tool}:{input_source}:{region}:{reading}:{16 hex of the arguments' digest}:{attempt}
        key = [tool, source_kind, region or "-", reading or "-", digest(arguments)[:16], "1"]
        return ToolCallRecord(
            call_key="lookup:" + ":".join(key),
            phase="lookup",
            tool=tool,
            tool_version=f"{tool}-1",
            source=source,
            field_keys=fields,
            input_source=source_kind,
            region_id=region,
            observation_id=reading,
            attempt=1,
            arguments=arguments,
            outcome=outcome,
            result=result,
            evidence_id=evidence,
            started_at=TIMES[4],
            completed_at=TIMES[5],
        )

    run.tool_calls = [
        call("geocode", "google-maps-geocoding", ["province_state", "city"], "decided_transcript",
             {"query": "Chicago, Ill."}, "success", {"candidates": [{"place_id": "fixture-place"}]}, place.id, region=left.id),
        call("geocode", "google-maps-geocoding", ["county"], "decided_transcript",
             {"query": "Cook Co."}, "no_match", {"candidates": []}, nowhere.id, region=left.id),
        call("gbif", "gbif", ["taxon"], "raw_reading", {"name": "Aedes aegypti L."}, "success",
             {"candidates": [{"usage_key": 1651891}]}, gbif.id, region=right.id, reading=right_qwen.id),
        call("catalogue-of-life", "catalogue-of-life", ["taxon"], "raw_reading", {"name": "Aedes aegypti L."},
             "success", {"candidates": [{"id": "fixture-col-taxon"}]}, col.id, region=right.id, reading=right_qwen.id),
    ]
    decided = {"input_source": "decided_transcript", "source_region_id": left.id}
    run.fields = {
        "province_state": TracedField(
            state=ValueState.SUPPORTED,
            literal="Ill.",
            evidence_ids=[place.id],
            evidence_relations={place.id: "supports"},
            **decided,
        ),
        "city": TracedField(
            state=ValueState.SUPPORTED,
            literal="Chicago",
            authority_id="fixture-place",
            evidence_ids=[place.id],
            evidence_relations={place.id: "supports"},
            **decided,
        ),
        "county": TracedField(
            state=ValueState.UNRESOLVED,
            literal="Cook Co.",
            reason="No single match for the county",
            **decided,
        ),
        "date_visited_from": TracedField(
            state=ValueState.SUPPORTED,
            literal="VII-46",
            parsed="1946-07",
            precision="month",
            century_rule="date-rules-v1:two_digit_year_century=1900",
            **decided,
        ),
        "taxon": TracedField(
            state=ValueState.SUPPORTED,
            literal=None,
            verbatim_by_observation={
                right_qwen.id: right_qwen.literal_text,
                right_muse.id: right_muse.literal_text,
            },
            normalized="Aedes aegypti",
            authority_id="gbif:1651891",
            evidence_ids=[gbif.id, col.id],
            evidence_relations={gbif.id: "decides", col.id: "contradicts"},
            input_source="raw_reading",
            source_region_id=right.id,
            source_observation_id=right_qwen.id,
        ),
        "identified_by_irn": TracedField(),
    }
    run.field_groups = {
        "province_state": "mandatory",
        "city": "mandatory",
        "county": "mandatory",
        "date_visited_from": "mandatory",
        "taxon": "mandatory",
        "identified_by_irn": "optional",
    }
    run.findings = [
        Finding(
            rule_id="taxonomy_source_disagreement",
            rule_version="g23-v1",
            severity="warning",
            field_key="taxon",
            reason_code="taxonomy_source_disagreement",
            evidence_ids=[col.id],
        )
    ]
    run.disposition = Disposition.REVIEW
    run.reasons = ["mandatory_unresolved:county"]
    run.disposition_summary = "Needs human review under insects-clearance-v1: county unresolved."
    run.paid_calls = [
        {
            "step": f"transcribe:{left.id}:handwriting-qwen",
            "attempt": 1,
            "reserved_micros": 20000,
            "usage": {"input_tokens": 1200, "output_tokens": 40},
            "outcome": "validated_output",
            "cost_micros": 2600,
            "cost_basis": "computed",
            "price_list": {"version": "prices-v1", "as_of": "2026-09-01"},
        },
        {
            "step": f"transcribe:{right.id}:handwriting-qwen",
            "attempt": 1,
            "reserved_micros": 20000,
            "usage": {"input_tokens": 1180, "output_tokens": 38},
            "outcome": "validated_output",
            "cost_micros": 2600,
            "cost_basis": "computed",
            "price_list": {"version": "prices-v1", "as_of": "2026-09-01"},
        },
    ]
    return Specimen(
        id=ident(3),
        scope=scope,
        asset=asset,
        version=12,
        run=run,
        created_at=TIMES[0],
    )
