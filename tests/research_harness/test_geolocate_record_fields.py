"""G39: a GEOLocate match's point is candidate metadata in the tool result and the trace, not a record field.

A GEOLocate candidate's authority_id is stored on field_candidate rows and appears in the public
record on country, state, county and city alike. These cases run the adapter's real lookups on the
recorded Evanston answer, put each candidate's id on the four geography fields of a run, and read
the run back through the production projection (application.projection.writes: the field_candidate,
resolved_field and record_version rows) and the public workspace JSON (application.api.workspace).
The offline end-to-end test (test_production_e2e.py) scans the fake connector's tables the same
way for the rows a published research record keeps; this file covers the projection and the
public JSON directly, on the recorded Evanston answer, without the worker.
"""
import json
import re

from specimen_digitization.application.api import workspace
from specimen_digitization.application.domain import Disposition, ValueState
from specimen_digitization.application.projection import writes
from specimen_digitization.research_harness.contracts import FieldKey

from test_geolocate_validator import EVANSTON, candidates, lookup
from test_projection import locate, size
from test_projection_decisions import TracedField, base, first_pass, rows

GEOGRAPHY = {FieldKey.COUNTRY: "USA", FieldKey.PROVINCE_STATE: "Illinois", FieldKey.COUNTY: "Cook",
             FieldKey.CITY: "Evanston"}
# Two decimal numbers side by side, however separated: a point written into a string.
COORDINATE_PAIR = re.compile(r"-?\d{1,3}\.\d+\s*[,;/ ]\s*-?\d{1,3}\.\d+")
RECORD_ROWS = ("AppendFieldCandidateV2", "AppendResolvedFieldV2", "AppendRecordVersionV2")


def geography_candidates():
    """One real GEOLocate lookup per field; each field's single candidate, keyed by field."""
    found = {}
    for field_key, value in GEOGRAPHY.items():
        [candidate] = candidates(lookup("evanston-control.json", field_key, EVANSTON, value))
        found[str(field_key)] = candidate
    return found


def geography_run():
    s = first_pass(base())
    region = s.run.regions[0]
    found = geography_candidates()
    s.run.fields = {key: TracedField(
        state=ValueState.SUPPORTED, literal=candidate["value"], normalized=candidate["value"],
        authority_id=candidate["authority_id"], input_source="decided_transcript", source_region_id=region.id)
        for key, candidate in found.items()}
    s.run.field_groups = dict.fromkeys(found, "mandatory")
    # A disposition makes the projection write the record version and its resolved fields.
    s.run.disposition, s.run.reasons = Disposition.REVIEW, ["label_coverage_unconfirmed"]
    s.run.disposition_summary = "Needs human review: the label's coverage is unconfirmed."
    return s, found


def assert_no_point(candidate, text, where):
    """The candidate's matched point, in any spelling, and any coordinate pair at all, are absent."""
    for number in (candidate["decimal_latitude"], candidate["decimal_longitude"]):
        for spelling in (str(number), f"{number:.6f}", f"{number:.4f}"):
            assert spelling not in text, f"{where} holds the matched point {spelling}"
    assert not COORDINATE_PAIR.search(text), f"{where} holds a coordinate pair"


def test_no_projected_row_and_no_public_field_carries_the_matched_point():
    s, found = geography_run()
    # Evanston's best match is the same point for all four fields (as Chicago's was in the e2e).
    assert {(item["decimal_latitude"], item["decimal_longitude"]) for item in found.values()} == {(42.041141, -87.690059)}
    projected = writes(s, locate, size, "worker-uid")

    # No field_candidate, resolved_field or record_version row holds the point.
    for operation in RECORD_ROWS:
        assert rows(projected, operation), operation
        for variables in rows(projected, operation):
            for candidate in found.values():
                assert_no_point(candidate, json.dumps(variables, sort_keys=True), operation)
    # The field_candidate row stores the candidate's own id, which is the opaque one.
    stored = {row["fieldKey"]: row["authorityId"] for row in rows(projected, "AppendFieldCandidateV2")}
    assert stored == {key: candidate["authority_id"] for key, candidate in found.items()}
    assert all(re.fullmatch(r"geolocate:[0-9a-f]{16}", identifier) for identifier in stored.values())

    # The public specimen JSON: the run's fields and the workspace's own field view.
    public = workspace(s)
    for view in (public["fields"], public["run"]["fields"]):
        for candidate in found.values():
            assert_no_point(candidate, json.dumps(view, sort_keys=True), "the public fields")
        assert {key: item["authority_id"] for key, item in view.items()} == stored
