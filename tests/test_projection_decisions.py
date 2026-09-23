"""Stages 6 to 8 of the projection (docs/execution/golive/DATA_CONTRACT.md 11, T2b).

The first pass, harness and field names come from S4's agreed shapes; stand-in
subclasses carry them until they reach the shared domain model.
"""

from __future__ import annotations

from pydantic import BaseModel

from specimen_digitization.application.domain import (
    AuditEvent,
    Disposition,
    Evidence,
    FieldValue,
    Lookup,
    LookupStatus,
    Observation,
    Transcript,
    ValueState,
)
from specimen_digitization.application.projection import derived_id, writes
from specimen_digitization.application.storage import digest

from test_projection import TracedRun, locate, pinned, read, size, specimen


class Difference(BaseModel):
    number: int
    spans: dict
    verdict: str
    material: bool


class Handoff(BaseModel):
    observation_id: str
    role: str
    handed_text: str
    note: str | None = None


class ToolCallRecord(BaseModel):
    call_key: str
    phase: str
    tool: str
    tool_version: str
    source: str | None
    field_keys: list[str]
    input_source: str
    region_id: str | None = None
    observation_id: str | None = None
    attempt: int = 1
    arguments: dict
    outcome: str
    result: dict | None = None
    evidence_id: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class DecidedTranscript(Transcript):
    decision_kind: str | None = None
    selected_observation_id: str | None = None
    first_pass_call: Observation | None = None
    differences: list[Difference] = []
    handoffs: list[Handoff] = []


class TracedField(FieldValue):
    input_source: str | None = None
    source_region_id: str | None = None
    source_observation_id: str | None = None
    precision: str | None = None
    century_rule: str | None = None


class HarnessRun(TracedRun):
    tool_calls: list[ToolCallRecord] = []
    field_groups: dict[str, str] = {}
    disposition_summary: str | None = None


def base():
    s = specimen()
    s.run = HarnessRun()
    return read(pinned(s))


def ops(result):
    return [w.operation for w in result]


def rows(result, operation):
    return [w.variables for w in result if w.operation == operation]


def first_pass(s, *, selected=True, verdict=None):
    """The region decided by the LLM first pass, as S4 records it."""
    right, left = s.run.observations
    region = s.run.regions[0]
    call = Observation(
        region_id=region.id,
        route_id="first-pass",
        model_id="model/first-pass",
        provider="fixture-provider",
        prompt_version="q" * 64,
        input_sha256="e" * 64,
        literal_text="",
        raw_ref=f"{'f' * 64}:9",
        raw_sha256="f" * 64,
        completion_state="validated_output",
    )
    difference = Difference(
        number=1,
        spans={
            left.id: {"start": 11, "end": 12, "text": "l"},
            right.id: {"start": 11, "end": 12, "text": "1"},
        },
        verdict=verdict or left.id,
        material=True,
    )
    s.run.transcripts = [
        DecidedTranscript(
            region_id=region.id,
            text=left.literal_text if selected else None,
            observation_ids=[right.id, left.id],
            alternatives=[right.literal_text, left.literal_text],
            resolved=selected,
            reason="The crop shows a lowercase l.",
            disagreement_ratio=1 / 13,
            alignment_status="difference",
            alignment_algorithm="bounded-levenshtein-fraction-v1",
            decision_kind="first_pass",
            selected_observation_id=left.id if selected else None,
            first_pass_call=call,
            differences=[difference],
            handoffs=[
                Handoff(
                    observation_id=left.id,
                    role="decided_transcript" if selected else "raw_reading",
                    handed_text=left.literal_text,
                ),
                Handoff(
                    observation_id=right.id,
                    role="raw_reading",
                    handed_text=right.literal_text,
                    note="Reads the l as a one.",
                ),
            ],
        )
    ]
    return s


def lookup(s, **fields):
    found = Lookup(
        provider="google-maps-geocoding",
        adapter_version="geocode-1",
        query={"address": "Chicago, Ill."},
        status=LookupStatus.SUCCESS,
        candidates=[{"place_id": "fixture-place"}],
        metadata={"locator": "place/fixture-place", "source_version": "v1"},
        raw_ref=f"{'9' * 64}:4",
        digest="8" * 64,
        retrieved_at="2026-09-23T12:00:00+00:00",
        **fields,
    )
    s.run.lookups = [found]
    return found


def references_come_first(result):
    written = {}
    for index, w in enumerate(result):
        for name, value in w.variables.items():
            if name.endswith("Id") and name != "id" and value in written:
                assert written[value] < index, (w.operation, name)
        written.setdefault(w.variables["id"], index)


def test_the_first_pass_writes_its_call_its_decision_and_each_handoff():
    s = first_pass(base())
    result = writes(s, locate, size, "worker-uid")
    references_come_first(result)
    right, left = s.run.observations
    region = s.run.regions[0]
    transcript = s.run.transcripts[0]
    call = transcript.first_pass_call
    assert ops(result)[9:] == [
        "AppendSourceAssetV2",
        "AppendModelObservationV2",
        "AppendTranscriptionVersionV2",
        "AppendHarnessInputV1",
        "AppendHarnessInputV1",
    ]
    written_call = rows(result, "AppendModelObservationV2")[-1]
    assert written_call["id"] == call.id
    assert written_call["independent"] is False
    assert written_call["stepKey"] == f"first_pass:{region.id}"
    assert written_call["literalText"] == ""
    decision = rows(result, "AppendTranscriptionVersionV2")[0]
    assert decision["regionId"] == region.id
    assert decision["decisionKind"] == "first_pass"
    assert decision["selectedObservationId"] == left.id
    assert decision["firstPassObservationId"] == call.id
    assert decision["literalText"] == left.literal_text
    assert decision["rationale"] == "The crop shows a lowercase l."
    assert decision["spans"] == [transcript.differences[0].model_dump(mode="json")]
    assert decision["alternatives"] == []
    assert decision["unresolved"] is False
    handoffs = rows(result, "AppendHarnessInputV1")
    assert [(h["observationId"], h["role"]) for h in handoffs] == [
        (left.id, "decided_transcript"),
        (right.id, "raw_reading"),
    ]
    assert handoffs[1]["handedText"] == right.literal_text
    assert handoffs[1]["note"] == "Reads the l as a one."
    assert handoffs[0]["id"] == derived_id("handoff", decision["id"], left.id)
    assert all(h["transcriptionVersionId"] == decision["id"] for h in handoffs)


def test_no_selected_reading_or_an_uncertain_material_difference_is_unresolved():
    unselected = rows(
        writes(first_pass(base(), selected=False), locate, size, "worker-uid"),
        "AppendTranscriptionVersionV2",
    )[0]
    assert unselected["selectedObservationId"] is None
    assert unselected["unresolved"] is True
    assert unselected["literalText"] == ""
    s = first_pass(base(), verdict="uncertain")
    uncertain = rows(writes(s, locate, size, "worker-uid"), "AppendTranscriptionVersionV2")[0]
    assert uncertain["unresolved"] is True
    assert uncertain["alternatives"] == [s.run.transcripts[0].differences[0].model_dump(mode="json")]


def test_today_identical_and_reviewer_decisions_are_recognised():
    s = base()
    right, left = s.run.observations
    transcript = s.run.transcripts[0]
    s.run.observations = [right, left.model_copy(update={"literal_text": right.literal_text})]
    transcript.resolved, transcript.text = True, right.literal_text
    identical = rows(writes(s, locate, size, "worker-uid"), "AppendTranscriptionVersionV2")
    assert [(d["decisionKind"], d["selectedObservationId"], d["unresolved"]) for d in identical] == [
        ("identical_readings", transcript.observation_ids[0], False)
    ]
    s = base()
    transcript = s.run.transcripts[0]
    transcript.actor, transcript.resolved, transcript.text = "reviewer-uid", True, "Chicago, Ill."
    transcript.reason = "The crop shows a lowercase l."
    human = rows(writes(s, locate, size, "worker-uid"), "AppendTranscriptionVersionV2")[0]
    assert (human["decisionKind"], human["selectedObservationId"], human["unresolved"]) == (
        "human",
        None,
        False,
    )
    assert human["rationale"] == "The crop shows a lowercase l."
    undecided = base()
    assert "AppendTranscriptionVersionV2" not in ops(writes(undecided, locate, size, "worker-uid"))


def test_lookups_and_stored_evidence_become_evidence_items():
    s = first_pass(base())
    found = lookup(s)
    s.run.lookups.append(
        Lookup(provider="gbif", adapter_version="g1", query={"name": "x"}, status=LookupStatus.TIMEOUT)
    )
    stored = Evidence(
        kind="authority",
        source="gbif-backbone",
        locator="gbif/1",
        excerpt="",
        raw_ref=f"{'7' * 64}:5",
        digest="6" * 64,
    )
    s.run.evidence = [stored, Evidence(kind="transcript", source="region", locator="r/1", excerpt="x")]
    result = writes(s, locate, size, "worker-uid")
    references_come_first(result)
    items = rows(result, "AppendEvidenceItemV2")
    assert [i["id"] for i in items] == [found.id, stored.id]
    geocoded = items[0]
    assert geocoded["source"] == "google-maps-geocoding"
    assert (geocoded["sourceVersion"], geocoded["adapterVersion"]) == ("v1", "geocode-1")
    assert geocoded["query"] == {"address": "Chicago, Ill."}
    assert geocoded["outcome"] == "success"
    assert geocoded["locator"] == "place/fixture-place"
    assert geocoded["responseSha256"] == "8" * 64
    assert geocoded["capturedAt"] == "2026-09-23T12:00:00+00:00"
    asset = next(w.variables for w in result if w.variables["id"] == geocoded["rawAssetId"])
    assert (asset["kind"], asset["sha256"], asset["width"]) == ("lookup_response", "9" * 64, None)
    assert items[1]["locator"] == "gbif/1"


def test_tool_calls_point_at_the_decision_they_ran_on_and_the_evidence_they_made():
    s = first_pass(base())
    found = lookup(s)
    region = s.run.regions[0]
    right, _ = s.run.observations
    s.run.tool_calls = [
        ToolCallRecord(
            call_key="lookup:geocode:decided_transcript:-:0af70af70af70af7:1",
            phase="lookup",
            tool="geocode",
            tool_version="t1",
            source="google-maps-geocoding",
            field_keys=["country", "city"],
            input_source="decided_transcript",
            region_id=region.id,
            arguments={"query": "Chicago, Ill."},
            outcome="success",
            result={"candidates": [{"place_id": "fixture-place"}]},
            evidence_id=found.id,
            started_at="2026-09-23T12:00:00+00:00",
            completed_at="2026-09-23T12:00:01+00:00",
        ),
        ToolCallRecord(
            call_key="lookup:gbif:raw_reading:x:1",
            phase="lookup",
            tool="gbif",
            tool_version="g1",
            source="gbif-backbone",
            field_keys=["taxon"],
            input_source="raw_reading",
            region_id=region.id,
            observation_id=right.id,
            arguments={"name": "x"},
            outcome="timeout",
            result={"error": "timed out", "retry_after": 30},
            evidence_id="no-such-evidence",
        ),
    ]
    result = writes(s, locate, size, "worker-uid")
    references_come_first(result)
    decision = rows(result, "AppendTranscriptionVersionV2")[0]
    geocode, gbif = rows(result, "AppendToolCallV1")
    assert geocode["id"] == derived_id("tool-call", s.run.id, geocode["callKey"])
    assert geocode["transcriptionVersionId"] == decision["id"]
    assert geocode["observationId"] is None
    assert geocode["evidenceId"] == found.id
    assert geocode["fieldKeys"] == ["country", "city"]
    assert (geocode["source"], geocode["outcome"], geocode["attempt"]) == ("google-maps-geocoding", "success", 1)
    assert (gbif["transcriptionVersionId"], gbif["observationId"]) == (None, right.id)
    assert gbif["evidenceId"] is None
    assert gbif["result"] == {"error": "timed out", "retry_after": 30}


def test_fields_carry_their_source_date_precision_and_evidence():
    s = first_pass(base())
    found = lookup(s)
    region = s.run.regions[0]
    right, _ = s.run.observations
    s.run.fields = {
        "date_visited_from": TracedField(
            state=ValueState.SUPPORTED,
            literal="VII-46",
            parsed="1946-07",
            input_source="decided_transcript",
            source_region_id=region.id,
            precision="month",
            century_rule="date-rules-v1:two_digit_year_century=1900",
        ),
        "city": TracedField(
            state=ValueState.SUPPORTED,
            literal="Chicago",
            authority_id="fixture-place",
            evidence_ids=[found.id, "no-such-evidence"],
            input_source="raw_reading",
            source_region_id=region.id,
            source_observation_id=right.id,
        ),
        "county": TracedField(),
    }
    result = writes(s, locate, size, "worker-uid")
    references_come_first(result)
    decision = rows(result, "AppendTranscriptionVersionV2")[0]
    date, city = rows(result, "AppendFieldCandidateV2")
    assert date["fieldKey"] == "date_visited_from"
    assert date["parsedValue"] == {
        "value": "1946-07",
        "precision": "month",
        "century_rule": "date-rules-v1:two_digit_year_century=1900",
    }
    assert (date["derivation"], date["inputSource"]) == ("parsed", "decided_transcript")
    assert (date["sourceTranscriptionId"], date["sourceObservationId"]) == (decision["id"], None)
    assert city["parsedValue"] is None
    assert (city["derivation"], city["authorityId"]) == ("lookup", "fixture-place")
    assert (city["sourceTranscriptionId"], city["sourceObservationId"]) == (None, right.id)
    links = rows(result, "AppendCandidateEvidenceV2")
    assert [(link["candidateId"], link["evidenceId"], link["relation"]) for link in links] == [
        (city["id"], found.id, "supports")
    ]


def test_a_disposition_writes_the_record_its_fields_and_a_finding_per_reason():
    s = first_pass(base())
    s.run.fields = {
        "city": TracedField(state=ValueState.SUPPORTED, literal="Chicago"),
        "county": TracedField(),
        "habitat": TracedField(),
    }
    assert "AppendRecordVersionV2" not in ops(writes(s, locate, size, "worker-uid"))
    s.run.disposition = Disposition.REVIEW
    s.run.reasons = ["mandatory_unresolved:county", "label_coverage_unconfirmed"]
    s.run.field_groups = {"city": "mandatory", "county": "mandatory", "habitat": "optional"}
    s.run.disposition_summary = "Needs human review under insects-clearance-v1: county unresolved."
    result = writes(s, locate, size, "worker-uid")
    references_come_first(result)
    record = rows(result, "AppendRecordVersionV2")[0]
    assert record["disposition"] == "needs_human_review"
    assert record["policyVersion"] == s.run.profile.policy_version
    assert record["reasonCodes"] == ["mandatory_unresolved:county", "label_coverage_unconfirmed"]
    assert record["summary"] == s.run.disposition_summary
    assert record["predecessorId"] is None
    candidate = rows(result, "AppendFieldCandidateV2")[0]
    resolved = rows(result, "AppendResolvedFieldV2")
    assert [(r["fieldKey"], r["state"], r["fieldGroup"], r["candidateId"]) for r in resolved] == [
        ("city", "supported", "mandatory", candidate["id"]),
        ("county", "unknown", "mandatory", None),
        ("habitat", "unknown", "optional", None),
    ]
    findings = rows(result, "AppendValidationFindingV2")
    assert [(f["ruleId"], f["fieldKey"], f["reasonCode"]) for f in findings] == [
        ("mandatory_unresolved", "county", "mandatory_unresolved:county"),
        ("label_coverage_unconfirmed", None, "label_coverage_unconfirmed"),
    ]
    assert all((f["severity"], f["outcome"]) == ("hard", "fail") for f in findings)
    s.run.disposition_summary, s.run.field_groups = None, {}
    fallback = writes(s, locate, size, "worker-uid")
    assert rows(fallback, "AppendRecordVersionV2")[0]["summary"] == (
        "mandatory_unresolved:county; label_coverage_unconfirmed"
    )
    groups = [r["fieldGroup"] for r in rows(fallback, "AppendResolvedFieldV2")]
    assert groups == ["mandatory", "mandatory", "optional"]


def test_a_changed_decision_is_a_new_record_version_and_an_unchanged_one_is_not():
    s = first_pass(base())
    s.run.fields = {"city": TracedField(state=ValueState.SUPPORTED, literal="Chicago")}
    s.run.disposition, s.run.reasons = Disposition.REVIEW, ["taxonomy_unresolved"]
    first = rows(writes(s, locate, size, "worker-uid"), "AppendRecordVersionV2")[0]["id"]
    assert rows(writes(s, locate, size, "worker-uid"), "AppendRecordVersionV2")[0]["id"] == first
    s.run.disposition, s.run.reasons = Disposition.CLEARED, []
    assert rows(writes(s, locate, size, "worker-uid"), "AppendRecordVersionV2")[0]["id"] != first


def test_review_decisions_are_written_only_by_reviewers():
    s = base()
    s.version = 7
    decided = AuditEvent(
        actor="reviewer-uid",
        action="review_field",
        reason="Checked the label",
        before={"literal": None},
        after={"literal": "Cook"},
    )
    s.audit = [AuditEvent(actor="worker-uid", action="workflow_step", reason=""), decided]
    assert "AppendReviewDecisionV1" not in ops(writes(s, locate, size, "worker-uid"))
    result = writes(s, locate, size, "reviewer-uid", reviewer=True)
    assert rows(result, "AppendReviewDecisionV1") == [
        {
            "id": decided.id,
            "specimenId": s.id,
            "baseRevision": 6,
            "resultingRevision": 7,
            "reason": "Checked the label",
            "correction": {
                "action": "review_field",
                "before": {"literal": None},
                "after": {"literal": "Cook"},
            },
        }
    ]
    assert ops(result)[-1] == "AppendReviewDecisionV1"


def test_record_ids_depend_on_the_decision_content():
    s = first_pass(base())
    s.run.disposition, s.run.reasons = Disposition.CLEARED, []
    record = rows(writes(s, locate, size, "worker-uid"), "AppendRecordVersionV2")[0]
    content = {
        "disposition": "cleared",
        "reasons": [],
        "summary": "cleared",
        "fields": {key: value.state.value for key, value in s.run.fields.items()},
    }
    assert record["id"] == derived_id("record", s.run.id, digest(content))
