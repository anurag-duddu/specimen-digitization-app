"""Derived values (HARNESS.md section 12; G37, G38)."""

import json

from specimen_digitization.application.derivations import (
    Found,
    apply_derivations,
    elevation_derivations,
    settled_value,
)
from specimen_digitization.application.domain import FieldValue
from specimen_digitization.application.domain import ValueState as V
from specimen_digitization.application.harness_tools import (
    Check,
    Derivation,
    SourceRef,
)

CITY = FieldValue(
    state=V.SUPPORTED,
    literal="Chimaltenango",
    authority_id="place-1",
    evidence_ids=["e-city"],
)
FIELDS = {
    "city": CITY,
    "county": FieldValue(),
    "elevation_from_m": FieldValue(),
    "elevation_from_ft": FieldValue(),
}


class Blobs:
    def __init__(self):
        self.puts = {}

    def put(self, data):
        ref = f"blob-{len(self.puts)}"
        self.puts[ref] = data
        return ref


def derivation(
    key, value, inputs, method="containment", name="gadm", record_id="ADM2-1"
):
    return Derivation(
        field_key=key,
        value=value,
        method=method,
        authority=SourceRef(name=name, record_id=record_id, version="4.1"),
        inputs=inputs,
        evidence=[
            Check(
                name="circle_inside_unit",
                result="supports",
                detail="whole circle inside one ADM2",
            )
        ],
    )


def apply(fields, derivations):
    blobs = Blobs()
    filled, evidence = apply_derivations(fields, derivations, asset_id="a", blobs=blobs)
    return filled, evidence, blobs


def test_a_derivation_fills_a_field_the_label_leaves_out_with_its_evidence():
    found = Found(
        derivation("county", "Chimaltenango", {"city": "place-1"}), ("e-call",)
    )

    filled, evidence, blobs = apply(FIELDS, [found])

    county = filled["county"]
    assert (county.state, county.layer, county.parsed, county.literal) == (
        V.SUPPORTED,
        "derived",
        "Chimaltenango",
        None,
    )
    assert (county.authority_id, county.derived_from, county.reason) == (
        "ADM2-1",
        ["city"],
        "derived:containment",
    )
    (item,) = evidence
    assert (item.kind, item.source, item.locator, item.excerpt) == (
        "derivation",
        "gadm",
        "derivation:containment",
        "whole circle inside one ADM2",
    )
    # It names its settled input, the authority with its version, and the
    # tool call that returned it (#124, PLAN 4.8).
    assert county.evidence_relations == {
        item.id: "decides",
        "e-call": "supports",
        "e-city": "supports",
    }
    record = json.loads(blobs.puts[item.raw_ref])
    assert record["derivation"]["inputs"] == {"city": "place-1"}
    assert record["derivation"]["authority"]["version"] == "4.1"
    assert record["call_evidence_ids"] == ["e-call"]


def test_a_derivation_whose_inputs_are_not_settled_to_its_values_does_not_apply():
    other_place = derivation(
        "county", "X", {"city": "place-2"}
    )  # A request that didn't settle.
    unsettled = derivation("county", "X", {"province_state": "Y"})

    assert apply(FIELDS, [other_place])[0] == {}
    assert apply(FIELDS, [unsettled])[0] == {}


def test_a_stated_field_is_never_replaced_and_disagreeing_derivations_fill_nothing():
    stated = FIELDS | {"county": FieldValue(state=V.SUPPORTED, literal="Chimaltenango")}
    twice = [
        derivation("county", "A", {"city": "place-1"}),
        derivation("county", "B", {"city": "place-1"}),
    ]

    assert apply(stated, [derivation("county", "Z", {"city": "place-1"})])[0] == {}
    assert apply(FIELDS, twice)[0] == {}


def test_a_value_derived_earlier_may_be_an_input():
    metres = derivation(
        "elevation_from_m",
        "1396",
        {"city": "place-1"},
        method="elevation_model",
        name="copernicus-glo-30",
        record_id="N14W091",
    )
    feet = derivation(
        "elevation_from_ft",
        "4580.05",
        {"elevation_from_m": "1396"},
        method="unit_conversion",
        name="field_harness",
        record_id=None,
    )

    filled, _, _ = apply(FIELDS, [metres, feet])

    assert {k: v.parsed for k, v in filled.items()} == {
        "elevation_from_m": "1396",
        "elevation_from_ft": "4580.05",
    }


def test_a_settled_value_is_the_authority_id_or_the_value_the_field_holds():
    assert settled_value(CITY) == "place-1"
    assert (
        settled_value(FieldValue(state=V.SUPPORTED, parsed="1948-05-04"))
        == "1948-05-04"
    )
    assert settled_value(FieldValue(state=V.AMBIGUOUS, literal="x")) is None


def stated(literal, evidence="e-literal"):
    return FieldValue(
        state=V.SUPPORTED, literal=literal, evidence_ids=[evidence], layer="verbatim"
    )


def derive(fields):
    """G41's elevation rules, applied."""
    return apply(fields, elevation_derivations(fields))


EMPTY = dict.fromkeys(
    ("elevation_from_m", "elevation_to_m", "elevation_from_ft", "elevation_to_ft"),
    FieldValue(),
)


def test_a_range_in_feet_fills_the_metre_fields_by_the_exact_factor():
    fields = EMPTY | {
        "elevation_from_ft": stated("4000", "e-from"),
        "elevation_to_ft": stated("4200 ft.", "e-to"),
    }

    filled, evidence, blobs = derive(fields)

    assert {k: v.parsed for k, v in filled.items()} == {
        "elevation_from_m": "1219.2",
        "elevation_to_m": "1280.16",
    }
    low = filled["elevation_from_m"]
    assert (low.layer, low.derived_from, low.state, low.literal) == (
        "derived",
        ["elevation_from_ft"],
        V.SUPPORTED,
        None,
    )
    rule = next(e for e in evidence if e.id in low.evidence_ids)
    assert (rule.kind, rule.locator) == ("derivation", "derivation:unit_conversion")
    assert rule.excerpt == "1 ft = 0.3048 m, exact"
    assert low.evidence_relations == {rule.id: "decides", "e-from": "supports"}
    assert json.loads(blobs.puts[rule.raw_ref])["derivation"]["inputs"] == {
        "elevation_from_ft": "4000"
    }


def test_a_g41_value_names_its_stated_field_its_rule_and_apply_derivations():
    # A derived value counts only with its record (#124, PLAN 4.8).
    filled, evidence, blobs = derive(EMPTY | {"elevation_from_ft": stated("4000")})

    rule = next(e for e in evidence if e.id in filled["elevation_from_m"].evidence_ids)
    record = json.loads(blobs.puts[rule.raw_ref])["derivation"]
    assert rule.source == "apply_derivations"
    assert (record["inputs"], record["method"]) == (
        {"elevation_from_ft": "4000"},
        "unit_conversion",
    )
    assert (record["authority"]["name"], record["authority"]["version"]) == (
        "apply_derivations",
        "derivation-rules-v1",
    )
    assert [check["name"] for check in record["evidence"]] == ["feet_to_metres"]


def test_a_single_metre_value_is_both_ends_and_fills_the_feet_fields():
    filled, _, _ = derive(EMPTY | {"elevation_from_m": stated("1200 m")})

    assert {k: v.parsed for k, v in filled.items()} == {
        "elevation_to_m": "1200",
        "elevation_from_ft": "3937.01",
        "elevation_to_ft": "3937.01",
    }
    assert filled["elevation_to_m"].reason == "derived:stated_elevation"
    assert {v.derived_from[0] for v in filled.values()} == {"elevation_from_m"}


def test_stated_elevations_are_never_replaced():
    fields = EMPTY | {
        "elevation_from_m": stated("1200"),
        "elevation_to_m": stated("1300"),
        "elevation_from_ft": stated("3900"),
    }

    filled, _, _ = derive(fields)

    # The label states feet too, so nothing converts; only the feet maximum
    # is filled from the feet minimum.
    assert {k: v.parsed for k, v in filled.items()} == {"elevation_to_ft": "3900"}


def test_nothing_is_derived_from_an_unsettled_or_unreadable_elevation():
    conflict = FieldValue(
        state=V.AMBIGUOUS, verbatim_by_observation={"a": "1200 m", "b": "1260 m"}
    )

    assert derive(EMPTY | {"elevation_from_m": conflict})[0] == {}
    assert derive(EMPTY | {"elevation_from_m": stated("1200-1500 m")})[0] == {}
    assert derive(EMPTY)[0] == {}
