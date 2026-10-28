"""The reference set's scorer pins the strict rule on fixed records (docs/execution/units/PLAN.md, WP 0)."""
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("units_program_score", Path(__file__).with_name("score.py"))
score = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(score)

PILOT_322 = {  # tests/fixtures/field_model_pilot_rows.json, subject 105526322, `expected`
    "fmnh_ins_number": "4486783", "country": "Philippines", "province_state": "Davao",
    "precise_location": "CNHM. E Slope Mt.\nMcKinley, Davao Prov.\nMindanao, P.I.",
    "elevation_from_m": "1950.72", "elevation_to_m": "1950.72", "elevation_from_ft": "6400",
    "elevation_to_ft": "6400", "date_visited_from": "1946-09-06", "date_visited_to": "1946-09-06",
    "collectors": "H. Hoogstraal"}


def supported(literal=None, parsed=None, normalized=None):
    return {"state": "supported", "literal": literal, "parsed": parsed, "normalized": normalized}


def row(fields, reasons=(), findings=(), subject="105526322", disposition="needs_human_review"):
    return {"subject": subject, "fields": fields, "reasons": list(reasons), "findings": list(findings),
            "disposition": disposition}


def cells(fields, expected=PILOT_322, **kwargs):
    return score.score_specimen(row(fields, **kwargs), expected)["cells"]


def test_a_value_equal_to_the_truth_is_cleared_right():
    assert cells({"country": supported("P.I.", parsed="Philippines")})["country"] == ("primary", "cleared_right")


def test_a_value_unlike_the_truth_is_cleared_wrong():
    assert cells({"country": supported("Mindanao", parsed="Mindanao")})["country"] == ("primary", "cleared_wrong")


def test_the_strict_rule_reads_the_parsed_value_before_the_normalized_one():
    # The rig's --lenient option would accept the normalized "Philippines"; the strict rule does not.
    field = supported("P.I.", parsed="P.I.", normalized="Philippines")
    assert cells({"country": field})["country"] == ("primary", "cleared_wrong")


@pytest.mark.parametrize("state", ["unknown", "unresolved", "ambiguous", "unreadable"])
def test_a_field_not_settled_is_left_without_a_value(state):
    assert cells({"collectors": {"state": state}})["collectors"] == ("primary", "left_without_value")


def test_a_field_with_no_entry_in_the_run_is_left_without_a_value():
    assert cells({})["date_visited_to"] == ("derived", "left_without_value")


@pytest.mark.parametrize("state", ["unknown", "unresolved", "unreadable", "ambiguous"])
def test_a_field_not_settled_is_left_without_a_value_whatever_text_it_keeps(state):
    # 105526322's pair runs keep reader text on an unresolved elevation: it is no value for a person, in any state
    # but supported (application/domain.py ValueState).
    elevation = {"state": state, "literal": "6400", "parsed": "6400"}
    collectors = {"state": state, "literal": "H. Hoogstraal"}
    found = cells({"elevation_from_ft": elevation, "collectors": collectors})
    assert found["elevation_from_ft"] == ("primary", "left_without_value")
    assert found["collectors"] == ("primary", "left_without_value")
    assert score.settled(collectors) is None


def test_a_supported_state_with_no_text_is_left_without_a_value():
    assert cells({"collectors": supported()})["collectors"] == ("primary", "left_without_value")


def test_a_field_settled_absent_where_the_truth_holds_a_value_is_wrong():
    assert cells({"collectors": {"state": "not_present"}})["collectors"] == ("primary", "cleared_wrong")


def test_a_field_the_truth_says_is_absent_scores_in_the_absent_category():
    expected = {k: v for k, v in PILOT_322.items() if not k.startswith("elevation_")}
    found = cells({"elevation_from_ft": {"state": "not_present"},
                   "elevation_from_m": supported("6400", parsed="1950.72"),
                   "elevation_to_m": {"state": "unresolved"}}, expected=expected)
    assert found["elevation_from_ft"] == ("absent", "cleared_right")
    assert found["elevation_from_m"] == ("absent", "cleared_wrong")
    assert found["elevation_to_m"] == ("absent", "left_without_value")


def test_a_marked_value_is_counted_as_marked_and_as_right_when_its_value_is_right():
    fields = {"elevation_from_ft": supported("Elev.6400", parsed="6400"),
              "collectors": supported("H. Hoogstraal leg.", parsed="H. Hoogstraal leg.")}
    reasons = ["marked:elevation_from_ft:L2:text_only", "marked:collectors:L2:text_only"]
    scored = score.score_specimen(row(fields, reasons=reasons), PILOT_322)
    assert scored["cells"]["elevation_from_ft"] == ("primary", "marked_right")
    assert scored["cells"]["collectors"] == ("primary", "marked_wrong")
    primary = score.tally([scored])["primary"]
    assert (primary["marked_right"], primary["marked_wrong"], primary["marked"], primary["right"]) == (1, 1, 2, 1)
    assert primary["n"] == len(score.PRIMARY)


def test_a_marked_code_in_a_finding_marks_the_field_too():
    fields = {"country": supported("P.I.", parsed="Philippines")}
    findings = [{"code": "marked:country:L2:image_uncertain", "field": "country"}]
    assert cells(fields, findings=findings)["country"] == ("primary", "marked_right")


def test_todays_finding_codes_mark_nothing():
    fields = {"country": supported("P.I.", parsed="Philippines")}
    findings = [{"code": "first_pass_conflict:country", "field": "country"}]
    assert cells(fields, findings=findings)["country"] == ("primary", "cleared_right")


def test_a_precise_location_that_only_names_the_place_is_partial_and_wrong():
    scored = score.score_specimen(row({"precise_location": supported("E Slope Mt. McKinley")}), PILOT_322)
    assert scored["cells"]["precise_location"] == ("primary", "cleared_wrong")
    assert scored["partial"] == ["precise_location"]
    assert score.tally([scored])["primary"]["of_which_partial"] == 1


def test_the_whole_locality_block_is_right():
    field = supported("CNHM. E Slope Mt.\nMcKinley, Davao Prov.\nMindanao, P.I.")
    assert cells({"precise_location": field})["precise_location"] == ("primary", "cleared_right")


def test_elevations_compare_as_numbers_and_the_catalogue_number_as_digits():
    found = cells({"elevation_from_m": supported("6400'", parsed="1950.720"),
                   "fmnh_ins_number": supported("FMNHINS 4486783")})
    assert found["elevation_from_m"] == ("derived", "cleared_right")
    assert found["fmnh_ins_number"] == ("primary", "cleared_right")


def test_the_tally_gives_every_outcome_with_its_denominator():
    scored = score.score_specimen(row({"country": supported(parsed="Philippines")}), PILOT_322)
    tally = score.tally([scored])
    assert tally["primary"]["n"] == 7 and tally["derived"]["n"] == 4 and tally["absent"]["n"] == 0
    assert tally["primary"]["cleared_right"] == 1 and tally["primary"]["left_without_value"] == 6


def test_a_specimen_without_truth_is_counted_never_scored():
    fields = {"country": supported(parsed="Guatemala"), "habitat": {"state": "not_present"},
              "taxon": {"state": "unresolved"}, "collectors": supported("R.D. Mitchell")}
    scored = score.score_specimen(row(fields, reasons=["marked:collectors:L1:text_only"]), None)
    assert scored["truth"] is False and "cells" not in scored
    assert scored["counts"] == {"cleared_value": 1, "cleared_absent": 1, "left_without_value": 1,
                                "marked_value": 1}
    assert score.tally([scored])["primary"]["n"] == 0


def test_criterion_two_counts_fields_cleared_in_both_runs_on_different_values():
    a = [row({"collectors": supported("R.D.Mitchell"), "habitat": supported("Mossy forest 6400'"),
              "elevation_from_m": supported(parsed="1950.72"), "country": supported(parsed="Guatemala"),
              "city": {"state": "unresolved"}})]
    b = [row({"collectors": supported("R.D.mitchell"), "habitat": supported("Mossy forest"),
              "elevation_from_m": supported(parsed="1950.720"), "country": supported(parsed="Guatemala"),
              "city": supported("Yepocapa")}, reasons=["marked:country:L1:text_only"])]
    found = score.cleared_differences(a, b)
    # country is marked in b, city is not settled in a: neither counts; case and spacing are normalised away.
    assert found["cleared_in_both"] == 3
    assert found["fields"] == [{"subject": "105526322", "field": "habitat", "kind": "two_values",
                                "a": "Mossy forest 6400'", "b": "Mossy forest"}]


def test_criterion_two_counts_a_cleared_absence_as_cleared():
    a = [row({"elevation_from_m": supported(parsed="1005.84"), "county": {"state": "not_present"},
              "habitat": {"state": "not_present"}, "city": {"state": "not_present"}})]
    b = [row({"elevation_from_m": {"state": "not_present"}, "county": {"state": "not_applicable"},
              "habitat": supported("Forest"), "city": {"state": "unresolved"}})]
    found = score.cleared_differences(a, b)
    # city is not settled in b; county is absent in both (two absent states are one result).
    assert found["cleared_in_both"] == 3
    assert found["fields"] == [
        {"subject": "105526322", "field": "elevation_from_m", "kind": "value_absent", "a": "1005.84",
         "b": "(absent)"},
        {"subject": "105526322", "field": "habitat", "kind": "value_absent", "a": "(absent)", "b": "Forest"}]


def test_criterion_two_compares_ascii_letters_and_digits_folding_case():
    # norm keeps ASCII letters and digits and folds case: "México" -> "mxico", "Mèxico" -> "mxico".
    a = [row({"country": supported(parsed="Mexico"), "collectors": supported("R.D.Mitchell"),
              "city": supported("México")})]
    b = [row({"country": supported(parsed="México"), "collectors": supported("R.D.mitchell"),
              "city": supported("Mèxico")})]
    found = score.cleared_differences(a, b)
    assert found["cleared_in_both"] == 3
    # 105526617's country in the baseline: two values, never a value against absence.
    assert found["fields"] == [
        {"subject": "105526322", "field": "country", "kind": "two_values", "a": "Mexico", "b": "México"}]


def test_the_pilot_truth_is_the_fixture_and_the_drawn_slides_have_none():
    manifest = {"specimens": [{"subject": "105526322", "truth": "fixture"}, {"subject": "1", "truth": "none"}]}
    expected = score.truth(manifest)
    assert expected["105526322"] == PILOT_322
    assert expected["1"] is None
    with pytest.raises(ValueError):
        score.truth({"specimens": [{"subject": "1", "truth": "pipeline"}]})
