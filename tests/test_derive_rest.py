"""G38's "fill the rest" (HARNESS.md section 13): what a reviewer's values let
the harness derive, as a proposal the reviewer edits and approves (S5)."""

import json

from test_derivations import Blobs

from specimen_digitization.application.derivations import (
    derive_rest,
    rest_place_inputs,
)
from specimen_digitization.application.domain import FieldValue, Run
from specimen_digitization.application.domain import ValueState as V

ELEVATIONS = (
    "elevation_from_m",
    "elevation_to_m",
    "elevation_from_ft",
    "elevation_to_ft",
)


def run_with(**fields) -> Run:
    return Run(fields={key: FieldValue() for key in ELEVATIONS} | fields)


def stated(literal):
    return FieldValue(
        state=V.SUPPORTED, literal=literal, evidence_ids=["e-label"], layer="verbatim"
    )


def test_a_reviewers_elevation_fills_the_rest_with_its_record():
    blobs = Blobs()

    proposal = derive_rest(
        run_with(),
        {"elevation_from_ft": "6400"},
        decision_id="d-1",
        asset_id="a",
        blobs=blobs,
    )

    fields = proposal.fields
    # G41 on the reviewer's number: both ends, and the metres by the exact factor.
    assert {k: v.parsed for k, v in fields.items()} == {
        "elevation_to_ft": "6400",
        "elevation_from_m": "1950.72",
        "elevation_to_m": "1950.72",
    }
    assert all(
        (v.layer, v.derived_from) == ("derived", ["elevation_from_ft"])
        for v in fields.values()
    )
    (review,) = [e for e in proposal.evidence if e.kind == "review"]
    assert (review.source, review.locator, review.excerpt) == (
        "review_decision",
        "decision/d-1",
        "6400",
    )
    assert json.loads(blobs.puts[review.raw_ref]) == {
        "decision_id": "d-1",
        "field_key": "elevation_from_ft",
        "value": "6400",
    }
    metres = fields["elevation_from_m"].evidence_relations
    (rule,) = [e for e, relation in metres.items() if relation == "decides"]
    assert metres[review.id] == "supports"
    assert rule in {e.id for e in proposal.evidence}
    assert (proposal.tool_calls, proposal.lookups, proposal.findings) == ([], [], [])


def test_it_fills_only_what_the_label_and_the_reviewer_leave_empty():
    # G37: the label's value and the reviewer's are never replaced, and a value
    # the harness already resolved is not proposed again.
    run = run_with(
        elevation_from_m=stated("1200 m"),
        elevation_to_m=FieldValue(state=V.SUPPORTED, parsed="1200", layer="derived"),
    )

    proposal = derive_rest(
        run,
        {"elevation_from_ft": "3937"},
        decision_id="d-1",
        asset_id="a",
        blobs=Blobs(),
    )

    assert set(proposal.fields) == {"elevation_to_ft"}


def test_the_run_is_not_changed():
    run = run_with()
    before = run.model_dump()

    derive_rest(
        run,
        {"elevation_from_ft": "6400"},
        decision_id="d-1",
        asset_id="a",
        blobs=Blobs(),
    )

    assert run.model_dump() == before


def test_a_reviewers_date_fills_date_visited_to():
    # G44 in review's "fill the rest".
    run = Run(
        fields={"date_visited_from": FieldValue(), "date_visited_to": FieldValue()}
    )

    proposal = derive_rest(
        run,
        {"date_visited_from": "1946-09-03"},
        decision_id="d-1",
        asset_id="a",
        blobs=Blobs(),
    )

    to = proposal.fields["date_visited_to"]
    assert (to.parsed, to.precision, to.layer) == ("1946-09-03", "day", "derived")


def test_the_place_calls_inputs_anchor_each_reviewer_value_on_the_run():
    # #208's security review, the coordinator's rulings of 06:36Z, 07:33Z and
    # 08:01Z (HARNESS.md section 13): each place value in `filled` is the
    # reviewer's, anchored on every text the run holds for that field, the
    # settled literal and each reading's verbatim, so what the reviewer kept is
    # cut; a field the run holds nothing for has no anchor.
    run = Run(
        fields={
            "precise_location": stated("Mindanao F.G. Wermer"),
            "province_state": FieldValue(),
            "county": FieldValue(
                verbatim_by_observation={"o-1": "Davao", "o-2": "Davao City"}
            ),
            "collectors": stated("F.G. Wermer"),
            "habitat": stated("Mossy forest"),
        }
    )
    filled = {
        "precise_location": "Mindanao F.G. Wermer, P.I.",
        "province_state": "Davao del Sur",
        "county": "Davao",
        "collectors": "F.G. Werner",
        "habitat": "mossy forest",  # Kept: equal, folded, to what the run holds.
    }

    inputs = rest_place_inputs(run, filled, decision_id="d-1")

    assert [
        (item.field_key, item.literal, item.reviewer, item.anchors)
        for item in inputs.literals
    ] == [
        (
            "precise_location",
            "Mindanao F.G. Wermer, P.I.",
            True,
            ["Mindanao F.G. Wermer"],
        ),
        ("province_state", "Davao del Sur", True, []),
        ("county", "Davao", True, ["Davao", "Davao City"]),
    ]
    assert {
        (item.source_observation_id, item.source_region_id) for item in inputs.literals
    } == {("review_decision", "decision/d-1")}
    # Every value the harness gave a non-place field, kept or replaced, and the
    # reviewer's own; only what the reviewer entered or changed is the
    # reviewer's own, and alone cuts the reviewer's own text (08:01Z).
    assert inputs.non_place_literals == [
        "F.G. Wermer",
        "Mossy forest",
        "F.G. Werner",
        "mossy forest",
    ]
    assert inputs.reviewer_non_place_literals == ["F.G. Werner"]
