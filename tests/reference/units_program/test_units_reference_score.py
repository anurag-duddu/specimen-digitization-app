"""The reference set's scorer pins the strict rule on fixed records (docs/execution/units/PLAN.md, WP 0)."""
import importlib.util
import itertools
import random
from pathlib import Path

import pytest

from specimen_digitization.application.domain import ValueState

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


def test_a_field_with_no_entry_in_the_run_is_left_without_a_value():
    assert cells({})["date_visited_to"] == ("derived", "left_without_value")


def test_the_scorer_groups_every_value_state_of_the_domain():
    # A state added to application/domain.py fails here until the scorer places it.
    states = {state.value for state in ValueState}
    assert states == score.STATES
    groups = (score.SETTLED_VALUE, score.SETTLED_ABSENT, score.UNSETTLED)
    assert sum(len(g) for g in groups) == len(states)
    with pytest.raises(ValueError):
        score.settled({"state": "invented"})


TEXTS = {  # the text a field can carry, the truth's collector "H. Hoogstraal" (PILOT_322)
    "no text": {},
    "literal only": {"literal": "H. Hoogstraal"},
    "normalized only": {"normalized": "H. Hoogstraal"},
    "parsed only": {"parsed": "H. Hoogstraal"},
    "literal and normalized": {"literal": "H. Hoogstraal", "normalized": "H. Hoogstraal"},
}
# Per state: the outcome when the truth holds "H. Hoogstraal" and when it says the field is absent, each with
# no text and with text.
SETTLEMENT = {
    "supported": {"truth": ("left_without_value", "cleared_right"), "absent": ("left_without_value", "cleared_wrong")},
    "not_present": {"truth": ("cleared_wrong", "cleared_wrong"), "absent": ("cleared_right", "cleared_right")},
    "not_applicable": {"truth": ("cleared_wrong", "cleared_wrong"), "absent": ("cleared_right", "cleared_right")},
    "unknown": {"truth": ("left_without_value",) * 2, "absent": ("left_without_value",) * 2},
    "unresolved": {"truth": ("left_without_value",) * 2, "absent": ("left_without_value",) * 2},
    "unreadable": {"truth": ("left_without_value",) * 2, "absent": ("left_without_value",) * 2},
    "ambiguous": {"truth": ("left_without_value",) * 2, "absent": ("left_without_value",) * 2},
}


@pytest.mark.parametrize("text", sorted(TEXTS))
@pytest.mark.parametrize("state", sorted(state.value for state in ValueState))
def test_each_value_state_with_the_listed_texts_settles_by_the_strict_rule(state, text):
    # On these records: supported settles a value when it has text; not_present and not_applicable settle absent
    # whatever text they carry; unknown, unresolved, unreadable and ambiguous are left without a value whatever
    # text they keep.
    field = {"state": state, **TEXTS[text]}
    with_text = text != "no text"
    expected = {k: v for k, v in PILOT_322.items() if k != "collectors"}
    found = cells({"collectors": field})["collectors"]
    absent = cells({"collectors": field}, expected=expected)["collectors"]
    assert found == ("primary", SETTLEMENT[state]["truth"][with_text])
    assert absent == ("absent", SETTLEMENT[state]["absent"][with_text])


BOUNDARY = {  # fixed records at the edges of the rule: (field, outcome against the truth, outcome against absence)
    "supported, empty literal": ({"state": "supported", "literal": ""}, "left_without_value", "left_without_value"),
    "supported, literal None": ({"state": "supported", "literal": None}, "left_without_value", "left_without_value"),
    "supported, whitespace literal": ({"state": "supported", "literal": "   "}, "left_without_value",
                                      "left_without_value"),
    "supported, whitespace parsed, text literal": ({"state": "supported", "parsed": "  ", "literal": "H. Hoogstraal"},
                                                    "cleared_right", "cleared_wrong"),
    # FieldValue's default reason (application/domain.py) is not text.
    "supported, reason only": ({"state": "supported", "reason": "No supported source value"}, "left_without_value",
                               "left_without_value"),
    # No state key: a stored FieldValue's default state is unknown, never a value.
    "no state, text literal": ({"literal": "H. Hoogstraal"}, "left_without_value", "left_without_value"),
    # A no-break space is whitespace: the literal is compared.
    "supported, no-break space normalized, text literal": (
        {"state": "supported", "normalized": "\u00a0", "literal": "H. Hoogstraal"}, "cleared_right",
        "cleared_wrong"),
    # Text after a leading newline is text: the literal is compared as it stands.
    "supported, literal after a newline": ({"state": "supported", "literal": "\nH. Hoogstraal"}, "cleared_right",
                                            "cleared_wrong"),
    # A tab is whitespace: the literal is compared.
    "supported, tab normalized, text literal": (
        {"state": "supported", "normalized": "\t", "literal": "H. Hoogstraal"}, "cleared_right", "cleared_wrong"),
    # The word "text" is text: it is compared, and it is not the collector.
    "supported, parsed 'text', text literal": ({"state": "supported", "parsed": "text", "literal": "H. Hoogstraal"},
                                               "cleared_wrong", "cleared_wrong"),
}


@pytest.mark.parametrize("name", sorted(BOUNDARY))
def test_boundary_records_settle_by_the_strict_rule(name):
    field, against_truth, against_absence = BOUNDARY[name]
    expected = {k: v for k, v in PILOT_322.items() if k != "collectors"}
    assert cells({"collectors": field})["collectors"] == ("primary", against_truth)
    assert cells({"collectors": field}, expected=expected)["collectors"] == ("absent", against_absence)


def test_text_is_any_string_with_a_character_python_does_not_call_whitespace():
    # Every code point, the surrogates included (a str may hold one), alone and repeated, against Python's own
    # str.isspace, so the check holds on whatever Unicode version the interpreter carries. has_text returns a bool.
    wrong = [cp for cp in range(0x110000) for c in (chr(cp),) for expected in (not c.isspace(),)
             if score.has_text(c) is not expected or score.has_text(c * 3) is not expected]
    assert wrong == []
    assert score.has_text(None) is False and score.has_text("") is False and score.has_text(" x ") is True


def test_text_on_seeded_random_strings_is_any_character_python_does_not_call_whitespace():
    # 20,000 strings, each a body of 0 to 12 characters drawn from every whitespace code point and a few others (letters, a
    # digit, punctuation, a control character, a surrogate, an emoji), most with a leading or trailing newline or
    # tab (an edge may be \r\n, so a string has up to 16 characters), against Python's own str.isspace, character by
    # character.
    rng = random.Random(20261028)
    space = [c for c in map(chr, range(0x110000)) if c.isspace()]
    other = ["H", "x", "7", ".", "-", "'", chr(0), chr(0xD800), chr(0x1F600)]
    edges = ["\n", "\t", "\r\n", ""]
    wrong = []
    for _ in range(20_000):
        body = "".join(rng.choice(space) if rng.random() < 0.6 else rng.choice(other) for _ in range(rng.randint(0, 12)))
        text = rng.choice(edges) + body + rng.choice(edges)
        if score.has_text(text) is not any(not c.isspace() for c in text):
            wrong.append(text)
    assert wrong == []


@pytest.mark.parametrize("state", ["", "SUPPORTED", "Supported", " supported", "invented"])
def test_a_state_outside_the_domain_is_refused(state):
    with pytest.raises(ValueError):
        score.settled({"state": state, "literal": "H. Hoogstraal"})
    with pytest.raises(ValueError):
        cells({"collectors": {"state": state, "literal": "H. Hoogstraal"}})


PICK_TEXT = {"parsed": "H. Hoogstraal", "normalized": "R.D. Mitchell", "literal": "F.G. Werner"}  # one per key
SHAPES = {"None": None, "empty": "", "blank": "  ", "text": "text"}


@pytest.mark.parametrize("parsed,normalized,literal", list(itertools.product(SHAPES, repeat=3)))
def test_the_compared_value_is_the_first_of_parsed_normalized_literal_that_has_text(parsed, normalized, literal):
    # All 64 combinations of the three keys, each None, "", "  " or text (a different text per key). The compared
    # value is the first key, in the order parsed, normalized, literal, whose string has a character other than
    # whitespace; with none, a supported field is left without a value.
    shapes = {"parsed": parsed, "normalized": normalized, "literal": literal}
    field = {"state": "supported", **{key: PICK_TEXT[key] if shape == "text" else SHAPES[shape]
                                      for key, shape in shapes.items()}}
    pick = next((key for key in ("parsed", "normalized", "literal") if shapes[key] == "text"), None)
    assert score.compared_value(field) == (PICK_TEXT[pick] if pick else None)
    # Scored against a truth that is the expected pick's text: any other pick is cleared wrong.
    expected = dict(PILOT_322, collectors=PICK_TEXT[pick] if pick else "H. Hoogstraal")
    found = cells({"collectors": field}, expected=expected)["collectors"]
    assert found == ("primary", "cleared_right" if pick else "left_without_value")


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
