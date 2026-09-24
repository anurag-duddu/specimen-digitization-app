"""T2c: derived values, authority identities and review calls (DATA_CONTRACT.md 3.2, 6, 11).

S4's #144 and #160 carry `layer`, `derived_from` and the review call's decision; stand-in
subclasses carry them until they reach the shared domain model.
"""

from __future__ import annotations

import pytest

from specimen_digitization.application.domain import AuditEvent, Disposition, Evidence, ValueState
from specimen_digitization.application.projection import GoogleContentStored, derived_id, writes
from specimen_digitization.application.storage import digest

from test_projection import locate, size
from test_projection_decisions import (
    ToolCallRecord,
    TracedField,
    base,
    first_pass,
    references_come_first,
    rows,
)


class DerivedField(TracedField):
    layer: str | None = None
    derived_from: list[str] = []


class ReviewCall(ToolCallRecord):
    review_decision_id: str | None = None


def rule(s, fill="6", stored=True):
    """The derivation record that decides a derived value (#144's `apply_derivations`)."""
    item = Evidence(
        kind="derivation",
        asset_id=s.asset.id,
        source="derivation-rules-v1",
        locator="derivation:unit_conversion",
        excerpt="6400 ft",
        raw_ref=f"{fill * 64}:6" if stored else None,
        digest=fill * 64 if stored else None,
    )
    s.run.evidence.append(item)
    return item


def derived_run(**changes):
    """A stated elevation in feet, and the metres derived from it (G41)."""
    s = first_pass(base())
    region = s.run.regions[0]
    decides = rule(s)
    stated = TracedField(
        state=ValueState.SUPPORTED,
        literal="6400",
        parsed="6400",
        input_source="decided_transcript",
        source_region_id=region.id,
    )
    derived = DerivedField(
        state=ValueState.SUPPORTED,
        parsed="1950.72",
        layer="derived",
        derived_from=["elevation_from_ft"],
        evidence_ids=[decides.id],
        evidence_relations={decides.id: "decides"},
        reason="derived:unit_conversion",
    )
    fields = {"elevation_from_ft": stated, "elevation_from_m": derived}
    for key, value in changes.items():
        fields[key] = value
    s.run.fields = fields
    s.run.disposition, s.run.reasons = Disposition.CLEARED, []
    return s, decides


def candidate_of(result, key):
    return [c for c in rows(result, "AppendFieldCandidateV3") if c["fieldKey"] == key]


def resolved_of(result, key):
    (field,) = [f for f in rows(result, "AppendResolvedFieldV2") if f["fieldKey"] == key]
    return field


def test_a_derived_value_with_its_record_is_one_derived_candidate():
    s, decides = derived_run()
    result = writes(s, locate, size, "worker-uid")
    references_come_first(result)
    (stated,) = candidate_of(result, "elevation_from_ft")
    (derived,) = candidate_of(result, "elevation_from_m")
    value = s.run.fields["elevation_from_m"]
    assert derived["id"] == derived_id("candidate", s.run.id, "elevation_from_m", "-", digest(value.model_dump(mode="json")))
    assert (derived["derivation"], derived["literalValue"], derived["parsedValue"]) == ("derived", None, "1950.72")
    assert (derived["inputSource"], derived["sourceTranscriptionId"], derived["sourceObservationId"]) == (None, None, None)
    assert derived["derivedFromFieldKeys"] == ["elevation_from_ft"]
    assert stated["derivedFromFieldKeys"] is None
    links = [(link["candidateId"], link["evidenceId"], link["relation"]) for link in rows(result, "AppendCandidateEvidenceV2")]
    assert (derived["id"], decides.id, "decides") in links
    assert resolved_of(result, "elevation_from_m")["candidateId"] == derived["id"]


@pytest.mark.parametrize(
    "case",
    ["no inputs", "an input the run lacks", "no derivation record", "a record that only supports", "an unstored record"],
)
def test_a_derived_value_without_its_record_does_not_count(case):
    """PLAN 4.8: a derived value counts only when its record names its settled inputs and decides it."""
    s, decides = derived_run()
    value = s.run.fields["elevation_from_m"]
    updates = {
        "no inputs": {"derived_from": []},
        "an input the run lacks": {"derived_from": ["elevation_to_ft"]},
        "no derivation record": {"evidence_ids": [], "evidence_relations": {}},
        "a record that only supports": {"evidence_relations": {decides.id: "supports"}},
    }
    if case == "an unstored record":
        s.run.evidence = [
            e.model_copy(update={"raw_ref": None, "digest": None}) if e.id == decides.id else e
            for e in s.run.evidence
        ]
    else:
        s.run.fields["elevation_from_m"] = value.model_copy(update=updates[case])
    result = writes(s, locate, size, "worker-uid")
    assert candidate_of(result, "elevation_from_m") == []
    assert resolved_of(result, "elevation_from_m")["candidateId"] is None


def test_an_unsettled_input_does_not_count():
    s, _ = derived_run()
    stated = s.run.fields["elevation_from_ft"]
    s.run.fields["elevation_from_ft"] = stated.model_copy(update={"state": ValueState.AMBIGUOUS})
    result = writes(s, locate, size, "worker-uid")
    assert candidate_of(result, "elevation_from_m") == []


def test_a_settled_value_keeps_its_authority_identity():
    """PLAN 4.8: the credit travels with the name that is kept."""
    s = first_pass(base())
    identity = {"name": "Apis mellifera", "source": "gbif", "source_record_id": "fixture-gbif-1", "credit": "GBIF Backbone Taxonomy"}
    s.run.fields = {
        "taxon": TracedField(
            state=ValueState.SUPPORTED,
            literal="Apis mellifera",
            normalized="Apis mellifera",
            authority_id="fixture-gbif-1",
            authority_identity=identity,
            input_source="decided_transcript",
            source_region_id=s.run.regions[0].id,
        )
    }
    (candidate,) = rows(writes(s, locate, size, "worker-uid"), "AppendFieldCandidateV3")
    assert candidate["authorityIdentity"] == identity


def test_only_a_settled_entry_carries_the_identity():
    s = first_pass(base())
    right, left = s.run.observations
    identity = {"name": "Chicago", "source": "geonames", "source_record_id": "fixture-geonames-1", "credit": "fixture credit, CC BY 4.0"}
    s.run.fields = {
        "city": TracedField(
            state=ValueState.SUPPORTED,
            verbatim_by_observation={right.id: "Chicago", left.id: "Chicag0"},
            input_source_by_observation={right.id: "raw_reading", left.id: "raw_reading"},
            settled_observation_ids=[right.id],
            normalized="Chicago",
            authority_id="fixture-geonames-1",
            authority_identity=identity,
        )
    }
    settled, unsettled = rows(writes(s, locate, size, "worker-uid"), "AppendFieldCandidateV3")
    assert (settled["authorityIdentity"], unsettled["authorityIdentity"]) == (identity, None)


def test_a_google_identity_with_a_name_refuses_the_projection():
    """G26: nothing of Google's but the place id is kept, so its identity carries no name."""
    s = first_pass(base())
    nameless = {"source": "google-maps-geocoding", "source_record_id": "fixture-place"}
    field = TracedField(
        state=ValueState.SUPPORTED,
        literal="Chicago",
        authority_id="fixture-place",
        authority_identity=nameless,
        input_source="decided_transcript",
        source_region_id=s.run.regions[0].id,
    )
    s.run.fields = {"city": field}
    (candidate,) = rows(writes(s, locate, size, "worker-uid"), "AppendFieldCandidateV3")
    assert candidate["authorityIdentity"] == nameless
    s.run.fields = {"city": field.model_copy(update={"authority_identity": {**nameless, "name": "fixture-google-name"}})}
    with pytest.raises(GoogleContentStored) as refused:
        writes(s, locate, size, "worker-uid")
    assert "fixture-google-name" not in str(refused.value)


def test_a_review_call_names_its_decision_and_follows_it():
    """G38's "fill the rest": a call on a reviewer's text names the review decision it ran for."""
    s = first_pass(base())
    s.version = 3
    asked = AuditEvent(actor="reviewer-uid", action="review_fill_the_rest", reason="Filled the county", before={}, after={"county": "Cook"})
    s.audit = [asked]
    s.run.tool_calls = [
        ReviewCall(
            call_key="lookup:geonames:review:1",
            phase="lookup",
            tool="geonames",
            tool_version="g1",
            source="geonames",
            field_keys=["county"],
            input_source="review",
            arguments={"name": "Cook"},
            outcome="no_match",
            result={},
            review_decision_id=asked.id,
        )
    ]
    result = writes(s, locate, size, "reviewer-uid", reviewer=True)
    (call,) = rows(result, "AppendToolCallV2")
    assert (call["inputSource"], call["reviewDecisionId"]) == ("review", asked.id)
    assert (call["transcriptionVersionId"], call["observationId"]) == (None, None)
    order = [w.operation for w in result]
    assert order.index("AppendReviewDecisionV1") < order.index("AppendToolCallV2")


def test_every_candidate_and_call_uses_the_t2c_operations():
    s, _ = derived_run()
    s.run.tool_calls = [
        ToolCallRecord(
            call_key="validate:date_parser:1",
            phase="validate",
            tool="date_parser",
            tool_version="d1",
            source=None,
            field_keys=["date_visited_from"],
            input_source="decided_transcript",
            region_id=s.run.regions[0].id,
            arguments={"literal": "VII-46"},
            outcome="success",
            result={"parsed": {"readings": []}, "warnings": []},
        )
    ]
    operations = {w.operation for w in writes(s, locate, size, "worker-uid")}
    assert {"AppendFieldCandidateV3", "AppendToolCallV2"} <= operations
    assert not {"AppendFieldCandidateV2", "AppendToolCallV1"} & operations
