"""Exact-key synthetic labels still require complete written elevation proof."""
import pytest

from specimen_digitization.research_harness.contracts import FieldKey, SpecialistRole
from specimen_digitization.research_harness.evidence import elevation_resolutions, settle_elevation
from specimen_digitization.research_harness.initial_requests import NativeGenerationRequestFactory
from specimen_digitization.application.harness import ExtractionCandidate, ExtractionOutput, apply_candidates
from test_organiser_raw_reading_evidence import Label, build, candidates, request_for, two_labels


@pytest.mark.parametrize(("selected", "peer"), (
    ("elevation_from_m: 1200 m", "elevation_from_m: 1300 m"),
    ("elevation_from_m: 1200 m\nCamp at 1300 m", "elevation_from_m: 1200 m"),
    ("elevation_from_m: 1200 m", "elevation_from_m: ~1200 m"),
    ("elevation_from_ft: 100 ft", "elevation_from_ft: 30.48 m"),
    ("elevation_from_m: 1200 m", "elevation_from_m: 1200 to 1200 m"),
    ("elevation_from_m: 1200 m", "elevation_from_m: 1200 ± 0 m"),
    ("elevation_from_m: 1200", "elevation_from_m: 1200"),
    ("elevation_from_m: 1200 yards", "elevation_from_m: 1200 yards"),
    ("elevation_from_m: 1200 m +/- -2 m", "elevation_from_m: 1200 m +/- -2 m"),
    ("elevation_from_m: 1200 m", "Elevation: 13OO m"),
    ("elevation_from_m: 1200 m", "Altitude: 1300"),
    ("elevation_from_m: 1200 m", "Elev. 1200 m ± unclear"),
    ("elevation_from_m: 1200 m", "Elev. 1200 m to unclear"),
))
def test_keyed_elevation_cannot_bypass_complete_measurement_and_retained_reader_veto(selected, peer):
    built = build((Label(selected, peer, decided="a"),), keyed=True)
    assert not [assembly for assembly in built.graph[2] if "elevation" in str(assembly.field_key)]
    assert all(event.status == "proposed" for event in built.graph[1])
    assert {fragment.observation_text for fragment in built.graph[0]} == {selected, peer}


@pytest.mark.parametrize(("literal", "peer", "expected_ft", "expected_m"), (
    ("6,400 ft", "elevation_from_m: 6400 feet", "6400.00", "1950.72"),
    ("6,400 ft", "Catalogue label only", "6400.00", "1950.72"),
    ("1200 m", "elevation_from_m: 1200 metres", "3937.01", "1200.00"),
    ("6,400 ft", "Elev. 6400 feet, mossy forest", "6400.00", "1950.72"),
))
def test_keyed_target_preserves_written_units_and_exact_g41_conversion(literal, peer, expected_ft, expected_m):
    # The target key does not assert a written source unit. A metre target can
    # consume a genuine feet literal; G41 retains feet as the native source.
    built = build((Label("elevation_from_m: " + literal, peer, decided="a"),), keyed=True)
    [assembly] = built.graph[2]
    event = next(item for item in built.graph[1] if item.id == assembly.event_id)
    assert event.validator_version == event.rule_version == "exact-elevation-field-key-line/v1"
    request = request_for(built, SpecialistRole.MEASUREMENT)
    rows = elevation_resolutions(settle_elevation(request, assembly_ids=(assembly.id,)))
    assert len(rows) == 4
    assert all(row.value.normalized == (expected_ft if str(row.field_key).endswith("_ft") else expected_m)
               for row in rows)
    source = next(row for row in rows if row.derivation is None)
    assert source.field_key == (FieldKey.ELEVATION_FROM_FT if literal.endswith("ft") else FieldKey.ELEVATION_FROM_M)
    assert all(row.derivation.source_field == source.field_key for row in rows if row.derivation)
    assert source.value.literal == literal


def test_equal_cross_label_quantities_do_not_manufacture_accepted_event_membership():
    feet, metres = "Camp at 100 ft", "Camp at 30.48 m"
    built = build((Label(feet), Label(metres)), [
        ("elevation_from_ft", "1A", "100 ft", feet), ("elevation_from_ft", "1B", "100 ft", feet),
        ("elevation_from_m", "2A", "30.48 m", metres), ("elevation_from_m", "2B", "30.48 m", metres)])
    assert built.graph[2] == ()
    assert all(item.status == "located" for item in candidates(built))
    request = request_for(built, SpecialistRole.MEASUREMENT)
    assert request.relations == () and not [event for event in request.events if event.status == "accepted"]


@pytest.mark.parametrize(("first", "second"), (
    ("elevation_from_m: 1200 m", "elevation_from_m: 1300 m"),
    ("elevation_from_ft: 100 ft", "elevation_from_m: 30.48 m"),
    ("elevation_from_m: 1200 m", "elevation_from_m: 1200 m"),
))
def test_keyed_cross_label_elevations_remain_unqualified_without_common_event_proof(first, second):
    built = build((Label(first, decided="a"), Label(second, decided="a")), keyed=True)
    assert built.graph[2] == ()
    assert not [event for event in built.graph[1] if event.status == "accepted"]
    assert {fragment.observation_text for fragment in built.graph[0]} == {first, second}


@pytest.mark.parametrize("other", ("100 ft", "200 ft"))
def test_keyed_span_cannot_hide_another_labels_retained_unstructured_elevation_candidate(other):
    text = "Camp at " + other
    built = build((Label("elevation_from_ft: 100 ft", decided="a"), Label(text)), keyed=True)
    apply_candidates(built.specimen.run, built.specimen.asset.id, ExtractionOutput(candidates=[
        ExtractionCandidate(field_key="elevation_from_ft", reading=name, literal=other, source_excerpt=text)
        for name in ("2A", "2B")]), "fixture-response", "d" * 64)
    graph = NativeGenerationRequestFactory._build_graph(built.specimen, built.scope)
    assert graph[2] == ()
    assert not [event for event in graph[1] if event.status == "accepted"]
    assert {item.status for item in graph[5]} == {"located"}


@pytest.mark.parametrize("other", ("Elev. 1300 m", "Altitude: 1300 m", "Elevation: 1200 m", "Altitude: 13OO m"))
def test_omitted_candidate_cannot_hide_another_labels_explicit_elevation(other):
    built = build((Label("elevation_from_m: 1200 m", decided="a"), Label(other)), keyed=True)
    assert built.graph[2] == ()
    assert not [event for event in built.graph[1] if event.status == "accepted"]


@pytest.mark.parametrize("peer", ("Elevation: 13OO m", "Altitude: 1300"))
def test_decided_unstructured_claim_cannot_treat_a_malformed_explicit_peer_as_silent(peer):
    text = "Camp at 1200 m"
    built = build(two_labels(a=text, b=peer, decided="a"), [("elevation_from_m", "2A", "1200 m", text)])
    assert built.graph[2] == ()
    assert {item.status for item in candidates(built)} == {"located"}


def test_complete_elevation_span_in_headed_narrative_remains_supported():
    text = "Elev. 1200 m, mossy forest"
    built = build(two_labels(a=text), [("elevation_from_m", "2A", "1200 m", text),
                                      ("elevation_from_m", "2B", "1200 m", text)])
    [assembly] = built.graph[2]
    request = request_for(built, SpecialistRole.MEASUREMENT)
    rows = elevation_resolutions(settle_elevation(request, assembly_ids=(assembly.id,)))
    assert all(row.value.normalized == ("3937.01" if str(row.field_key).endswith("_ft") else "1200.00")
               for row in rows)


def test_unproved_rounded_endpoint_columns_are_not_silently_ignored_as_label_assertions():
    text = "\n".join(("elevation_from_m: 180 to 181 m", "elevation_to_m: 181",
                      "elevation_from_ft: 590.55", "elevation_to_ft: 593.83"))
    built = build((Label(text, decided="a"),), keyed=True)
    assert built.graph[2] == ()
    assert all(event.status == "proposed" for event in built.graph[1])


def test_one_genuine_native_range_supplies_all_four_requested_endpoint_fields():
    built = build((Label("elevation_from_m: 180 to 181 m", decided="a"),), keyed=True)
    [assembly] = built.graph[2]
    request = request_for(built, SpecialistRole.MEASUREMENT)
    rows = elevation_resolutions(settle_elevation(request, assembly_ids=(assembly.id,)))
    assert {str(row.field_key): row.value.normalized for row in rows} == {
        "elevation_from_m": "180.00", "elevation_to_m": "181.00",
        "elevation_from_ft": "590.55", "elevation_to_ft": "593.83"}
    assert all(row.value.literal == "180 to 181 m" for row in rows if row.derivation is None)
    assert all(row.derivation.factor == "0.3048" and row.derivation.operation == "divide"
               for row in rows if row.derivation)
