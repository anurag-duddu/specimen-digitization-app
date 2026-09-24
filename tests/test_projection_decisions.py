"""Stages 6 to 8 of the projection (docs/execution/golive/DATA_CONTRACT.md 11, T2b).

The first pass, harness and field names come from S4's agreed shapes; stand-in
subclasses carry them until they reach the shared domain model.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from specimen_digitization.application.domain import (
    AuditEvent,
    Disposition,
    Evidence,
    FieldValue,
    Lookup,
    LookupStatus,
    Observation,
    Region,
    Transcript,
    ValueState,
)
from specimen_digitization.application.projection import derived_id, writes
from specimen_digitization.application.storage import digest

from test_projection import TracedRun, locate, pinned, read, reading, size, specimen


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
    verbatim_by_observation: dict[str, str] = {}
    input_source_by_observation: dict[str, str] = {}
    settled_observation_ids: list[str] = []
    evidence_relations: dict[str, str] = {}


class Finding(BaseModel):
    rule_id: str
    rule_version: str
    severity: str
    field_key: str | None
    reason_code: str
    evidence_ids: list[str] = []


class HarnessRun(TracedRun):
    coverage_check: dict | None = None
    tool_calls: list[ToolCallRecord] = []
    field_groups: dict[str, str] = {}
    disposition_summary: str | None = None
    findings: list[Finding] = []


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
    region_row = derived_id("region", s.run.id, region.id)
    written_call = rows(result, "AppendModelObservationV2")[-1]
    assert written_call["id"] == call.id
    assert written_call["independent"] is False
    assert written_call["regionId"] == region_row
    assert written_call["stepKey"] == f"first_pass:{region.id}"
    assert written_call["literalText"] == ""
    decision = rows(result, "AppendTranscriptionVersionV2")[0]
    assert decision["regionId"] == region_row
    assert decision["decisionKind"] == "first_pass"
    assert decision["selectedObservationId"] == left.id
    assert decision["firstPassObservationId"] == call.id
    assert decision["literalText"] == left.literal_text
    assert decision["rationale"] == "The crop shows a lowercase l."
    assert decision["spans"] == [transcript.differences[0].model_dump(mode="json")]
    assert decision["alternatives"] == []
    assert decision["unresolved"] is False
    handoff, fallback = rows(result, "AppendHarnessInputV1")
    assert (handoff["observationId"], handoff["role"]) == (left.id, "decided_transcript")
    assert handoff["id"] == derived_id("handoff", decision["id"], left.id)
    # What the other reader returned to the harness is recorded too (S4, #98).
    assert (fallback["observationId"], fallback["role"], fallback["note"]) == (
        right.id,
        "raw_reading",
        "Reads the l as a one.",
    )
    assert all(h["transcriptionVersionId"] == decision["id"] for h in (handoff, fallback))


def test_only_a_decision_without_a_selected_reading_is_unresolved():
    s = first_pass(base(), selected=False)
    right, left = s.run.observations
    result = writes(s, locate, size, "worker-uid")
    unselected = rows(result, "AppendTranscriptionVersionV2")[0]
    assert unselected["selectedObservationId"] is None
    assert unselected["unresolved"] is True
    assert unselected["literalText"] == ""
    # G19: every reading goes to the harness as a raw reading.
    handoffs = rows(result, "AppendHarnessInputV1")
    assert [(h["observationId"], h["role"]) for h in handoffs] == [
        (left.id, "raw_reading"),
        (right.id, "raw_reading"),
    ]
    assert (handoffs[1]["handedText"], handoffs[1]["note"]) == (right.literal_text, "Reads the l as a one.")
    # A selected reading is resolved, and the open difference stays among the alternatives.
    s = first_pass(base(), verdict="uncertain")
    uncertain = rows(writes(s, locate, size, "worker-uid"), "AppendTranscriptionVersionV2")[0]
    assert uncertain["unresolved"] is False
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
    # A reviewer's decision is written only by a reviewer's own save (section 6).
    assert "AppendTranscriptionVersionV2" not in ops(writes(s, locate, size, "worker-uid"))
    human = rows(
        writes(s, locate, size, "reviewer-uid", reviewer=True), "AppendTranscriptionVersionV2"
    )[0]
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
    nothing = Lookup(
        provider="google-maps-geocoding",
        adapter_version="geocode-1",
        query={"address": "Nowhere, Ill."},
        status=LookupStatus.NO_MATCH,
        metadata={"source_version": "v1"},
        raw_ref=f"{'1' * 64}:4",
        digest="2" * 64,
    )
    s.run.lookups.append(nothing)
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
    assert [i["id"] for i in items] == [found.id, nothing.id, stored.id]
    geocoded = items[0]
    assert geocoded["source"] == "google-maps-geocoding"
    assert (geocoded["sourceVersion"], geocoded["adapterVersion"]) == ("v1", "geocode-1")
    assert geocoded["query"] == {"address": "Chicago, Ill."}
    assert geocoded["outcome"] == "success"
    assert geocoded["locator"] == "place/fixture-place"
    assert geocoded["responseSha256"] == "8" * 64
    assert geocoded["capturedAt"] == "2026-09-23T12:00:00+00:00"
    asset = next(w.variables for w in result if w.variables["id"] == geocoded["rawAssetId"])
    # G26: Google's stored record holds our reduced record, never its response.
    assert (asset["kind"], asset["sha256"], asset["width"]) == ("evidence_record", "9" * 64, None)
    assert (items[1]["outcome"], items[1]["locator"]) == ("no_match", None)
    assert items[2]["locator"] == "gbif/1"


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
            result={"place_ids": ["fixture-place"]},
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
    nothing = Lookup(
        provider="google-maps-geocoding",
        adapter_version="geocode-1",
        query={"address": "Nowhere, Ill."},
        status=LookupStatus.NO_MATCH,
        raw_ref=f"{'1' * 64}:4",
        digest="2" * 64,
    )
    s.run.lookups.append(nothing)
    region = s.run.regions[0]
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
            evidence_ids=[found.id, nothing.id, "no-such-evidence"],
            evidence_relations={found.id: "supports", nothing.id: "supports", "no-such-evidence": "supports"},
            input_source="decided_transcript",
            source_region_id=region.id,
        ),
        "country": TracedField(
            state=ValueState.SUPPORTED,
            literal="U.S.A.",
            evidence_ids=[found.id],
            input_source="decided_transcript",
            source_region_id=region.id,
        ),
        "county": TracedField(),
    }
    result = writes(s, locate, size, "worker-uid")
    references_come_first(result)
    decision = rows(result, "AppendTranscriptionVersionV2")[0]
    date, city, country = rows(result, "AppendFieldCandidateV2")
    assert date["fieldKey"] == "date_visited_from"
    assert date["parsedValue"] == {
        "value": "1946-07",
        "precision": "month",
        "century_rule": "date-rules-v1:two_digit_year_century=1900",
    }
    assert (date["derivation"], date["inputSource"]) == ("parsed", "decided_transcript")
    assert (date["sourceTranscriptionId"], date["sourceObservationId"]) == (decision["id"], None)
    assert city["parsedValue"] is None
    assert (city["derivation"], city["authorityId"]) == ("literal", "fixture-place")
    assert (city["sourceTranscriptionId"], city["sourceObservationId"]) == (decision["id"], None)
    # Only a successful call's evidence is linked, and only with a relation: no default (G23).
    links = rows(result, "AppendCandidateEvidenceV2")
    assert [(link["candidateId"], link["evidenceId"], link["relation"]) for link in links] == [
        (city["id"], found.id, "supports")
    ]
    assert country["id"] not in {link["candidateId"] for link in links}


def test_a_deciding_source_makes_a_lookup_and_every_relation_is_kept():
    s = first_pass(base())
    gbif = Lookup(provider="gbif", adapter_version="g1", query={"name": "Aedes aegypti"}, status=LookupStatus.SUCCESS, raw_ref=f"{'5' * 64}:2", digest="4" * 64)
    col = Lookup(provider="catalogue-of-life", adapter_version="c1", query={"name": "Aedes aegypti"}, status=LookupStatus.SUCCESS, raw_ref=f"{'3' * 64}:2", digest="2" * 64)
    s.run.lookups = [gbif, col]
    s.run.fields = {
        "taxon": TracedField(
            state=ValueState.SUPPORTED,
            literal="Aedes aegypti L.",
            normalized="Aedes aegypti",
            authority_id="gbif:1651891",
            evidence_ids=[gbif.id, col.id],
            evidence_relations={gbif.id: "decides", col.id: "contradicts"},
            input_source="decided_transcript",
            source_region_id=s.run.regions[0].id,
        )
    }
    result = writes(s, locate, size, "worker-uid")
    (taxon,) = rows(result, "AppendFieldCandidateV2")
    assert (taxon["derivation"], taxon["normalizedValue"]) == ("lookup", "Aedes aegypti")
    links = rows(result, "AppendCandidateEvidenceV2")
    assert [(link["evidenceId"], link["relation"]) for link in links] == [
        (gbif.id, "decides"),
        (col.id, "contradicts"),
    ]


def test_each_reader_keeps_its_verbatim_when_the_first_pass_picked_none():
    s = first_pass(base(), selected=False)
    found = lookup(s)
    right, left = s.run.observations
    s.run.fields = {
        "city": TracedField(
            state=ValueState.SUPPORTED,
            literal=None,
            verbatim_by_observation={left.id: "Chimaltenango", right.id: "Chimaltenago"},
            normalized="Chimaltenango",
            authority_id="fixture-place",
            evidence_ids=[found.id],
            evidence_relations={found.id: "supports"},
            input_source_by_observation={left.id: "raw_reading", right.id: "raw_reading"},
            settled_observation_ids=[left.id],
        )
    }
    s.run.disposition, s.run.reasons = Disposition.CLEARED, []
    result = writes(s, locate, size, "worker-uid")
    candidates = rows(result, "AppendFieldCandidateV2")
    assert [(c["literalValue"], c["sourceObservationId"], c["inputSource"]) for c in candidates] == [
        ("Chimaltenango", left.id, "raw_reading"),
        ("Chimaltenago", right.id, "raw_reading"),
    ]
    assert all(c["sourceTranscriptionId"] is None for c in candidates)
    # G20: only the confirmed reader's candidate carries the settled value and its evidence.
    confirmed, other = candidates
    assert (confirmed["normalizedValue"], confirmed["authorityId"]) == ("Chimaltenango", "fixture-place")
    assert (other["normalizedValue"], other["authorityId"], other["derivation"]) == (None, None, "literal")
    assert [link["candidateId"] for link in rows(result, "AppendCandidateEvidenceV2")] == [confirmed["id"]]
    (resolved,) = rows(result, "AppendResolvedFieldV2")
    assert resolved["candidateId"] == confirmed["id"]
    # With no reader confirmed, no single verbatim is implied.
    s.run.fields["city"] = s.run.fields["city"].model_copy(
        update={"settled_observation_ids": [], "normalized": None, "authority_id": None, "evidence_ids": [], "evidence_relations": {}}
    )
    unconfirmed = writes(s, locate, size, "worker-uid")
    assert all(c["authorityId"] is None for c in rows(unconfirmed, "AppendFieldCandidateV2"))
    assert rows(unconfirmed, "AppendResolvedFieldV2")[0]["candidateId"] is None


def test_a_disposition_writes_the_record_its_fields_and_a_finding_per_reason():
    s = first_pass(base())
    s.run.fields = {
        "city": TracedField(state=ValueState.SUPPORTED, literal="Chicago"),
        "county": TracedField(),
        "label_notes": TracedField(),
    }
    assert "AppendRecordVersionV2" not in ops(writes(s, locate, size, "worker-uid"))
    s.run.disposition = Disposition.REVIEW
    s.run.reasons = ["mandatory_unresolved:county", "label_coverage_unconfirmed"]
    s.run.field_groups = {"city": "mandatory", "county": "mandatory", "label_notes": "optional"}
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
        ("label_notes", "unknown", "optional", None),
    ]
    findings = rows(result, "AppendValidationFindingV2")
    assert [(f["ruleId"], f["fieldKey"], f["reasonCode"]) for f in findings] == [
        ("mandatory_unresolved", "county", "mandatory_unresolved:county"),
        ("label_coverage_unconfirmed", None, "label_coverage_unconfirmed"),
    ]
    assert all((f["severity"], f["outcome"]) == ("hard", "fail") for f in findings)
    assert all((f["runId"], f["evidenceIds"]) == (s.run.id, None) for f in findings)
    none = digest([])
    assert [f["id"] for f in findings] == [
        derived_id(record["id"], "finding", "hard", "mandatory_unresolved", "county", "mandatory_unresolved:county", none),
        derived_id(record["id"], "finding", "hard", "label_coverage_unconfirmed", "-", "label_coverage_unconfirmed", none),
    ]
    found = lookup(s)
    s.run.findings = [
        Finding(
            rule_id="taxonomy_source_disagreement",
            rule_version="g23-v1",
            severity="warning",
            field_key="taxon",
            reason_code="taxonomy_source_disagreement",
            evidence_ids=[found.id, "no-such-evidence", found.id],
        ),
        # Two spelling warnings on different fields keep distinct ids (G27).
        Finding(rule_id="spelling_disagreement", rule_version="g27-v1", severity="warning", field_key="city", reason_code="spelling_disagreement"),
        Finding(rule_id="spelling_disagreement", rule_version="g27-v1", severity="warning", field_key="county", reason_code="spelling_disagreement"),
    ]
    warned = writes(s, locate, size, "worker-uid")
    extra, city_spelling, county_spelling = rows(warned, "AppendValidationFindingV2")[-3:]
    assert (extra["severity"], extra["outcome"], extra["ruleId"], extra["ruleVersion"]) == (
        "warning",
        "fail",
        "taxonomy_source_disagreement",
        "g23-v1",
    )
    assert (extra["fieldKey"], extra["reasonCode"]) == ("taxon", "taxonomy_source_disagreement")
    # Only evidence the run recorded is named, each once, and the id covers it.
    assert extra["evidenceIds"] == [found.id]
    assert extra["id"] == derived_id(
        rows(warned, "AppendRecordVersionV2")[0]["id"],
        "finding",
        "warning",
        "taxonomy_source_disagreement",
        "taxon",
        "taxonomy_source_disagreement",
        digest([found.id]),
    )
    assert city_spelling["id"] != county_spelling["id"]
    assert city_spelling["evidenceIds"] is None
    assert rows(warned, "AppendRecordVersionV2")[0]["disposition"] == "needs_human_review"
    assert rows(warned, "AppendRecordVersionV2")[0]["id"] != record["id"]
    s.run.findings = []
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
        "findings": [],
        "fields": {key: value.state.value for key, value in s.run.fields.items()},
        "candidates": {key: None for key in s.run.fields},
    }
    assert record["id"] == derived_id("record", s.run.id, digest(content))


def test_a_new_resolved_candidate_is_a_new_record_version():
    s = first_pass(base())
    s.run.fields = {"city": TracedField(state=ValueState.SUPPORTED, literal="Chicago")}
    s.run.disposition, s.run.reasons = Disposition.CLEARED, []
    first = rows(writes(s, locate, size, "worker-uid"), "AppendRecordVersionV2")[0]["id"]
    # Same state, another value: an authority selection that keeps the state still changes the record.
    s.run.fields["city"] = s.run.fields["city"].model_copy(update={"literal": "Chicago, Ill."})
    assert rows(writes(s, locate, size, "worker-uid"), "AppendRecordVersionV2")[0]["id"] != first


def second_label(s):
    """A second label on the slide, read by both routes; its first pass picked none (G19)."""
    region = Region(
        asset_id=s.asset.id, x=10, y=200, width=390, height=160, order=1, method="sam3", version="rev-1"
    )
    right = reading(region, "handwriting-muse", "Chicago, Il1.", "5")
    left = reading(region, "handwriting-qwen", "Chicago, Ill.", "6")
    call = left.model_copy(
        update={
            "id": Observation.model_fields["id"].default_factory(),
            "route_id": "first-pass",
            "literal_text": "",
            "raw_ref": f"{'7' * 64}:9",
            "raw_sha256": "7" * 64,
        }
    )
    s.run.regions.append(region)
    s.run.observations += [right, left]
    s.run.transcripts.append(
        DecidedTranscript(
            region_id=region.id,
            observation_ids=[right.id, left.id],
            alternatives=[right.literal_text, left.literal_text],
            resolved=False,
            disagreement_ratio=1 / 13,
            alignment_status="difference",
            alignment_algorithm="bounded-levenshtein-fraction-v1",
            decision_kind="first_pass",
            first_pass_call=call,
            handoffs=[
                Handoff(observation_id=o.id, role="raw_reading", handed_text=o.literal_text)
                for o in (right, left)
            ],
        )
    )
    return region, left, right


def two_labels():
    """Label one decided by the first pass; label two with no pick (G32)."""
    s = first_pass(base())
    _, picked = s.run.observations[:2]
    region, left, _ = second_label(s)
    return s, picked, region, left


def test_a_field_on_two_labels_keeps_one_candidate_per_label():
    s, picked, _, left = two_labels()
    s.run.fields = {
        "locality": TracedField(
            state=ValueState.SUPPORTED,
            verbatim_by_observation={picked.id: "Chicago", left.id: "Chicago"},
            input_source_by_observation={picked.id: "decided_transcript", left.id: "raw_reading"},
            settled_observation_ids=[picked.id, left.id],
            normalized="Chicago",
        )
    }
    s.run.disposition, s.run.reasons = Disposition.CLEARED, []
    result = writes(s, locate, size, "worker-uid")
    label_one = rows(result, "AppendTranscriptionVersionV2")[0]
    first, second = rows(result, "AppendFieldCandidateV2")
    # Each label keeps its own candidate and provenance, even with identical texts.
    assert (first["inputSource"], first["sourceTranscriptionId"], first["sourceObservationId"]) == (
        "decided_transcript",
        label_one["id"],
        None,
    )
    assert (second["inputSource"], second["sourceTranscriptionId"], second["sourceObservationId"]) == (
        "raw_reading",
        None,
        left.id,
    )
    assert [c["literalValue"] for c in (first, second)] == ["Chicago", "Chicago"]
    # A field without a lookup that clears on identical texts has the common text in normalized.
    assert all((c["normalizedValue"], c["derivation"]) == ("Chicago", "normalized") for c in (first, second))
    assert rows(result, "AppendResolvedFieldV2")[0]["candidateId"] == first["id"]


def test_labels_in_conflict_settle_nothing():
    s, picked, _, left = two_labels()
    s.run.fields = {
        "locality": TracedField(
            state=ValueState.SUPPORTED,
            verbatim_by_observation={picked.id: "Chicago", left.id: "Chimaltenango"},
            input_source_by_observation={picked.id: "decided_transcript", left.id: "raw_reading"},
            settled_observation_ids=[],
        )
    }
    s.run.disposition, s.run.reasons = Disposition.REVIEW, ["labels_conflict:locality"]
    result = writes(s, locate, size, "worker-uid")
    candidates = rows(result, "AppendFieldCandidateV2")
    assert [c["literalValue"] for c in candidates] == ["Chicago", "Chimaltenango"]
    assert all((c["normalizedValue"], c["authorityId"], c["derivation"]) == (None, None, "literal") for c in candidates)
    assert rows(result, "AppendResolvedFieldV2")[0]["candidateId"] is None


def test_each_settled_label_links_the_evidence_its_own_call_made():
    s, picked, region, left = two_labels()
    found = lookup(s)
    other = found.model_copy(
        update={
            "id": Lookup.model_fields["id"].default_factory(),
            "query": {"address": "Chicago, Ill."},
            "raw_ref": f"{'4' * 64}:4",
            "digest": "3" * 64,
        }
    )
    s.run.lookups.append(other)
    call = dict(phase="lookup", tool="geocode", tool_version="t1", source="google-maps-geocoding", field_keys=["locality"], arguments={}, outcome="success")
    s.run.tool_calls = [
        ToolCallRecord(call_key="one", input_source="decided_transcript", region_id=s.run.regions[0].id, evidence_id=found.id, **call),
        ToolCallRecord(call_key="two", input_source="raw_reading", region_id=region.id, observation_id=left.id, evidence_id=other.id, **call),
    ]
    s.run.fields = {
        "locality": TracedField(
            state=ValueState.SUPPORTED,
            verbatim_by_observation={picked.id: "Chicago", left.id: "Chicago, Ill."},
            input_source_by_observation={picked.id: "decided_transcript", left.id: "raw_reading"},
            settled_observation_ids=[picked.id, left.id],
            normalized="Chicago",
            authority_id="fixture-place",
            evidence_ids=[found.id, other.id],
            evidence_relations={found.id: "supports", other.id: "supports"},
        )
    }
    result = writes(s, locate, size, "worker-uid")
    first, second = rows(result, "AppendFieldCandidateV2")
    links = rows(result, "AppendCandidateEvidenceV2")
    assert [(link["candidateId"], link["evidenceId"]) for link in links] == [
        (first["id"], found.id),
        (second["id"], other.id),
    ]


def test_the_coverage_check_is_recorded_evidence():
    s = base()
    s.run.coverage_check = {
        "version": "label-coverage-v1",
        "outcome": "unconfirmed",
        "region_count": 3,
        "min_label_regions": 1,
        "max_label_regions": 2,
        "cross_check": {"concept": "label", "threshold": 0.5, "min_inside_fraction": 0.8, "counted": 1, "uncovered_boxes": []},
        "reason_codes": ["label_coverage_unconfirmed", "label_region_count_out_of_range"],
        "evidence_ref": f"{'2' * 64}:3",
        "evidence_sha256": "2" * 64,
        "checked_at": "2026-09-23T12:00:00+00:00",
    }
    result = writes(s, locate, size, "worker-uid")
    references_come_first(result)
    (item,) = [w for w in rows(result, "AppendEvidenceItemV2") if w["source"] == "label-coverage-check"]
    assert item["id"] == derived_id("coverage", s.run.id, "2" * 64)
    assert (item["outcome"], item["locator"]) == ("recorded", "coverage/label-coverage-v1")
    assert (item["sourceVersion"], item["responseSha256"]) == ("label-coverage-v1", "2" * 64)
    assert item["capturedAt"] == "2026-09-23T12:00:00+00:00"
    asset = next(w.variables for w in result if w.variables["id"] == item["rawAssetId"])
    assert asset["kind"] == "evidence_record"
    # A check without an evidence blob has no evidence item.
    s.run.coverage_check = {**s.run.coverage_check, "evidence_ref": None}
    assert "label-coverage-check" not in {w["source"] for w in rows(writes(s, locate, size, "worker-uid"), "AppendEvidenceItemV2")}


def another(found, fill, **fields):
    """A second stored lookup, like `found`."""
    return found.model_copy(
        update={
            "id": Lookup.model_fields["id"].default_factory(),
            "raw_ref": f"{fill * 64}:4",
            "digest": fill * 64,
            **fields,
        }
    )


def literal(s, reading, text, fill):
    """The harness's literal evidence of one reading's text, stored (#131)."""
    item = Evidence(
        kind="literal",
        asset_id=s.asset.id,
        region_id=reading.region_id,
        observation_ids=[reading.id],
        source="field_harness",
        locator=f"region:{reading.region_id}",
        excerpt=text,
        raw_ref=f"{fill * 64}:5",
        digest=fill * 64,
    )
    s.run.evidence.append(item)
    return item


def test_two_labels_with_one_text_keep_two_candidate_ids():
    s, picked, _, left = two_labels()
    field = TracedField(
        state=ValueState.SUPPORTED,
        verbatim_by_observation={picked.id: "Chicago", left.id: "Chicago"},
        input_source_by_observation={picked.id: "decided_transcript", left.id: "raw_reading"},
        settled_observation_ids=[picked.id, left.id],
        normalized="Chicago",
    )
    s.run.fields = {"locality": field}
    first, second = rows(writes(s, locate, size, "worker-uid"), "AppendFieldCandidateV2")
    # A decided entry is keyed by its label's selected reading, not by "-" (section 5).
    content = digest(field.model_dump(mode="json"))
    assert first["id"] == derived_id("candidate", s.run.id, "locality", picked.id, content)
    assert second["id"] == derived_id("candidate", s.run.id, "locality", left.id, content)
    assert first["id"] != second["id"]


@pytest.mark.parametrize("named", ["its decided reading", "the confirmed reading"])
def test_a_decided_label_settled_through_the_fallback_settles_with_its_call(named):
    """G20 inside G32: S4 names the label's decided reading or the raw reading a lookup confirmed."""
    s, picked, region, left = two_labels()
    one = s.run.regions[0]
    confirmed = s.run.observations[0]
    right = next(o for o in s.run.observations if o.region_id == region.id and o.id != left.id)
    missed = lookup(s).model_copy(update={"status": LookupStatus.NO_MATCH, "metadata": {"source_version": "v1"}})
    place = {"locator": "place/fixture-place", "source_version": "v1"}
    fallback = another(missed, "4", status=LookupStatus.SUCCESS, metadata=place)
    second = another(missed, "3", status=LookupStatus.SUCCESS, metadata=place)
    s.run.lookups = [missed, fallback, second]
    call = dict(phase="lookup", tool="geocode", tool_version="t1", source="google-maps-geocoding", field_keys=["locality"], arguments={})
    s.run.tool_calls = [
        ToolCallRecord(call_key="decided", input_source="decided_transcript", region_id=one.id, outcome="no_match", result={"place_ids": []}, evidence_id=missed.id, **call),
        ToolCallRecord(call_key="fallback", input_source="raw_reading", region_id=one.id, observation_id=confirmed.id, outcome="success", result={"place_ids": ["fixture-place"]}, evidence_id=fallback.id, **call),
        ToolCallRecord(call_key="label-two", input_source="raw_reading", region_id=region.id, observation_id=left.id, outcome="success", result={"place_ids": ["fixture-place"]}, evidence_id=second.id, **call),
    ]
    s.run.fields = {
        "locality": TracedField(
            state=ValueState.SUPPORTED,
            verbatim_by_observation={picked.id: "Chicago, Ill", right.id: "Chicago, Il1", left.id: "Chicago, Ill"},
            input_source_by_observation={picked.id: "decided_transcript", right.id: "raw_reading", left.id: "raw_reading"},
            settled_observation_ids=[picked.id if named == "its decided reading" else confirmed.id, left.id],
            normalized="Chicago, Ill",
            authority_id="fixture-place",
            evidence_ids=[fallback.id, second.id],
            evidence_relations={fallback.id: "supports", second.id: "supports"},
        )
    }
    s.run.disposition, s.run.reasons = Disposition.CLEARED, []
    result = writes(s, locate, size, "worker-uid")
    references_come_first(result)
    decided, unsettled, settled = rows(result, "AppendFieldCandidateV2")
    assert [c["authorityId"] for c in (decided, unsettled, settled)] == ["fixture-place", None, "fixture-place"]
    # The fallback call ran on a raw reading of label one: its evidence goes to label one's entry.
    links = rows(result, "AppendCandidateEvidenceV2")
    assert [(link["candidateId"], link["evidenceId"]) for link in links] == [
        (decided["id"], fallback.id),
        (settled["id"], second.id),
    ]
    assert rows(result, "AppendResolvedFieldV2")[0]["candidateId"] == decided["id"]


def test_evidence_links_to_the_entry_it_names_settled_or_not():
    s, picked, _, left = two_labels()
    one = literal(s, picked, "Chicago", "5")
    two = literal(s, left, "Chimaltenango", "6")
    s.run.fields = {
        "locality": TracedField(
            state=ValueState.AMBIGUOUS,
            reason="labels_conflict",
            verbatim_by_observation={picked.id: "Chicago", left.id: "Chimaltenango"},
            input_source_by_observation={picked.id: "decided_transcript", left.id: "raw_reading"},
            evidence_ids=[one.id, two.id],
            evidence_relations={one.id: "supports", two.id: "supports"},
        )
    }
    s.run.disposition, s.run.reasons = Disposition.REVIEW, ["labels_conflict:locality"]
    result = writes(s, locate, size, "worker-uid")
    references_come_first(result)
    first, second = rows(result, "AppendFieldCandidateV2")
    # Each label's reading goes to review with its own literal evidence.
    links = rows(result, "AppendCandidateEvidenceV2")
    assert [(link["candidateId"], link["evidenceId"], link["relation"]) for link in links] == [
        (first["id"], one.id, "supports"),
        (second["id"], two.id, "supports"),
    ]
    assert all((c["normalizedValue"], c["authorityId"]) == (None, None) for c in (first, second))
    assert rows(result, "AppendResolvedFieldV2")[0]["candidateId"] is None


def test_readers_that_agree_without_a_pick_are_one_verbatim():
    """A field without a lookup whose readers all read the same text takes it and clears
    (coordinator ruling on #88's final review; #131's `_verbatim_source`)."""
    s = first_pass(base(), selected=False)
    right, left = s.run.observations
    # Every agreeing reader's literal is its own evidence, so the provenance names each (S4).
    each = [literal(s, right, "Chicago", "5"), literal(s, left, "Chicago", "6")]
    field = TracedField(
        state=ValueState.SUPPORTED,
        reason="transcribed_as_seen",
        literal="Chicago",
        input_source="raw_reading",
        source_region_id=s.run.regions[0].id,
        source_observation_id=right.id,
        evidence_ids=[e.id for e in each],
        evidence_relations={e.id: "supports" for e in each},
    )
    s.run.fields = {"locality": field}
    s.run.disposition, s.run.reasons = Disposition.CLEARED, []
    result = writes(s, locate, size, "worker-uid")
    (candidate,) = rows(result, "AppendFieldCandidateV2")
    assert (candidate["literalValue"], candidate["inputSource"]) == ("Chicago", "raw_reading")
    assert (candidate["sourceObservationId"], candidate["sourceTranscriptionId"]) == (right.id, None)
    assert (candidate["derivation"], candidate["normalizedValue"]) == ("literal", None)
    assert candidate["id"] == derived_id("candidate", s.run.id, "locality", right.id, digest(field.model_dump(mode="json")))
    assert [link["evidenceId"] for link in rows(result, "AppendCandidateEvidenceV2")] == [e.id for e in each]
    assert rows(result, "AppendResolvedFieldV2")[0]["candidateId"] == candidate["id"]


def test_an_unsettled_date_keeps_every_reading_on_its_call():
    """G29, G33: the date parser's call is ambiguous and keeps its readings in `result` (#121, #138)."""
    s = first_pass(base())
    readings = [
        {"year": 1948, "month": 5, "day": 4, "precision": "day"},
        {"year": 1948, "month": 4, "day": 5, "precision": "day"},
    ]
    kept = {"parsed": {"readings": readings, "year_literal": None}, "warnings": ["several_readings"]}
    s.run.tool_calls = [
        ToolCallRecord(
            call_key="validate:date_parser:decided_transcript:-:1",
            phase="validate",
            tool="date_parser",
            tool_version="d1",
            source=None,
            field_keys=["date_visited_from"],
            input_source="decided_transcript",
            region_id=s.run.regions[0].id,
            arguments={"literal": "4-5-48"},
            outcome="ambiguous",
            result=kept,
        )
    ]
    (call,) = rows(writes(s, locate, size, "worker-uid"), "AppendToolCallV1")
    assert (call["outcome"], call["result"]) == ("ambiguous", kept)


# Built at run time, so no scanner finds a key in this file.
FAKE_KEY = "AIza" + "0" * 35


@pytest.mark.parametrize(
    "where",
    ["a key-bearing URL in arguments", "an API key in arguments", "a URL in the error", "a key in a lookup query"],
)
def test_a_key_with_a_call_refuses_the_projection_and_is_never_logged(where):
    """Rule 1.6: no key is stored with a call, and the refusal names where, never the key."""
    s = first_pass(base())
    found = lookup(s)
    url = "https://maps.example.test/geocode/json?address=Chicago&key=" + ("k3y" if "URL" in where else FAKE_KEY)
    record = ToolCallRecord(
        call_key="lookup:geocode:1",
        phase="lookup",
        tool="geocode",
        tool_version="t1",
        source="google-maps-geocoding",
        field_keys=["city"],
        input_source="decided_transcript",
        region_id=s.run.regions[0].id,
        arguments={"query": "Chicago, Ill."},
        outcome="success",
        result={"place_ids": ["fixture-place"]},
        evidence_id=found.id,
    )
    if where == "a key-bearing URL in arguments":
        record = record.model_copy(update={"arguments": {"url": url}})
    elif where == "an API key in arguments":
        record = record.model_copy(update={"arguments": {"query": "Chicago, Ill.", "key": FAKE_KEY}})
    elif where == "a URL in the error":
        record = record.model_copy(update={"outcome": "authorization_error", "result": {"error": f"403 for {url}"}, "evidence_id": None})
    else:
        s.run.lookups = [found.model_copy(update={"query": {"address": "Chicago, Ill.", "key": FAKE_KEY}})]
    s.run.tool_calls = [record]
    with pytest.raises(ValueError) as refused:
        writes(s, locate, size, "worker-uid")
    assert FAKE_KEY not in str(refused.value) and "k3y" not in str(refused.value)


@pytest.mark.parametrize(
    ("kept", "allowed"),
    [
        ({"place_ids": ["fixture-place"]}, True),
        ({"place_ids": [], "error": "rate limited", "retry_after": 30}, True),
        ({"candidates": [{"place_id": "fixture-place"}]}, False),
        ({"place_ids": ["fixture-place"], "names": ["x"]}, False),
        ({"place_ids": [{"place_id": "fixture-place", "name": "x"}]}, False),
    ],
)
def test_a_google_call_keeps_only_place_ids(kept, allowed):
    """Rule 1.6: a Google call's result holds only place ids, its error and its retry time."""
    s = first_pass(base())
    s.run.tool_calls = [
        ToolCallRecord(
            call_key="lookup:geocode:1",
            phase="lookup",
            tool="geocode",
            tool_version="t1",
            source="google-maps-geocoding",
            field_keys=["city"],
            input_source="decided_transcript",
            region_id=s.run.regions[0].id,
            arguments={"query": "Chicago, Ill."},
            outcome="success",
            result=kept,
        )
    ]
    if allowed:
        (call,) = rows(writes(s, locate, size, "worker-uid"), "AppendToolCallV1")
        assert call["result"] == kept
    else:
        with pytest.raises(ValueError):
            writes(s, locate, size, "worker-uid")
