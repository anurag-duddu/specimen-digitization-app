"""Follow-ups to PR #379's review and its live reruns (2026-10-18).

1. A country no answer settled no longer holds back a place inside the one
   nation its texts are confirmed as (#379). Text a reader writes on a line
   of the record's places that no field holds now keeps that country check
   in force: another reader's "Canada: Ill. Coles Co." with no candidate
   filed for "Canada" (finding 2).
2. A country text an undecided label's other reader writes as other words
   is set aside only when those words are a field of another kind's text (a
   taxon, a collector, a date), never another place field's (finding 1).
3. A precise location over consecutive lines never extends a candidate on
   one of its lines (finding 3).
4. e98a924c's precise location (run 629f91eb on 616ae010) went to review
   beside its collection code, the organiser's whole first line "CNHM. E
   Slope Mt.". A place read from the transcript that another field's text
   overlaps only partly now stands; that field goes to review.

The answers are made up in the shape the run graphs store them, not
recorded responses.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from test_location_last_gaps import COLES_B, COLES_CANDIDATES, COUNTRY_LOOKUPS, coles, fallback
from test_location_level_roles import NO_PLACE_LINES
from test_step import COLLECTORS, LACKS, Scripted, answering, build_rig, field_checks, label_with, settle

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.field_research import agreement
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import Candidate, FieldAnswer, FieldTask, Reading


# ---- 1. text on the place line that no field holds -------------------------

def test_an_unfiled_country_on_the_place_line_still_holds_the_places_below_it(tmp_path):
    """3781e440's label, where the other reader writes "Canada: Ill. Coles
    Co." and the organiser filed no candidate for "Canada": the country
    texts filed ("USA") are all the United States, but the line writes
    another word no field holds and no source ruled out. The state and the
    county are refused NO_COUNTRY and no country is derived, as on main
    before #379. On 616ae010 they settle and the country derives as the
    United States."""
    other = COLES_B.replace("U.S.B.I.L.: Coles Co.,", "Canada: Ill. Coles Co.")
    run, decisions = coles(tmp_path, other, country=fallback(*COUNTRY_LOOKUPS))
    assert run.fields["province_state"].state == ValueState.UNRESOLVED
    assert decisions["province_state"]["refusal"] == "no_country"
    assert run.fields["county"].state == ValueState.UNRESOLVED
    assert decisions["county"]["refusal"] == "no_country"
    assert run.fields["country"].layer is None


def test_a_word_the_sources_found_nothing_for_on_the_place_line_holds_nothing_back(tmp_path):
    """The live shape: 2A's "U.S.B.I.L." there, which Wikidata and NGA found
    nothing for, leaves the derivation as it was (the state, the county and
    the derived United States)."""
    run, _ = coles(tmp_path, country=fallback(*COUNTRY_LOOKUPS))
    assert run.fields["county"].authority_id == "wikidata:Q112137"
    assert (run.fields["country"].layer, run.fields["country"].parsed) == ("derived", "United States")


# ---- 2. the other reader's words: a field of another kind only -------------

def claimed_of(texts):
    """step._claimed_texts on a run whose reading 2B has, by field, these organiser texts."""
    tasks = {key: FieldTask(key, False, FieldValue(), (Candidate("2B", text, text, f"row-{key}"),), ())
        for key, text in texts.items()}
    return field_step._claimed_texts(SimpleNamespace(fields={}), tasks, (), "country")


def two_readers(first, second):
    return (Reading("2A", "label2", "obs2a", "raw_reading", first),
        Reading("2B", "label2", "obs2b", "raw_reading", second))


def test_another_place_fields_text_is_a_rival_reading_never_set_aside():
    """"Mexico" where the other reader writes "Texas", that reader's province:
    two readings of one place, so the country stays for review. On 616ae010
    "Mexico" is set aside."""
    readings = two_readers("Mexico\nsp. ?", "Texas\nsp. ?")
    claimed = claimed_of({"province_state": "Texas"})
    assert "Texas" not in claimed.get("2B", ())
    assert not agreement.set_aside("Mexico", readings, claimed)


@pytest.mark.parametrize(("first", "second", "texts"), [
    # 3B's taxon (d10333ff), a collector's name, a date.
    ("Panama\nsp. ?", "Panorpa\nsp. ?", {"taxon": "Panorpa"}),
    ("Chile\nleg.", "Chas.\nleg.", {"collectors": "Chas."}),
    ("Peru\nleg.", "1945\nleg.", {"date_visited_from": "1945"}),
], ids=["taxon", "collector", "date"])
def test_a_field_of_another_kinds_text_there_sets_the_country_aside(first, second, texts):
    readings = two_readers(first, second)
    claimed = claimed_of(texts)
    assert agreement.set_aside(first.split("\n")[0], readings, claimed)


# ---- 3. a run over lines never extends a candidate on its line -------------

def locality_task(*literals):
    return FieldTask("precise_location", False, FieldValue(),
        tuple(Candidate("2A", literal, literal, f"row-{index}") for index, literal in enumerate(literals)),
        ("geolocate",))


@pytest.mark.parametrize(("text", "literal", "candidates", "refused"), [
    # "near" beside the organiser's "Mt. Apo" on its line extends it, as on one line.
    ("Seliban Riv.\nnear Mt. Apo", "Seliban Riv.\nnear Mt. Apo", ("Seliban Riv.", "Mt. Apo"), True),
    ("near Mt. Apo", "near Mt. Apo", ("Mt. Apo",), True),
    # Each line its candidate, or two candidates and the comma between them.
    ("Seliban Riv.\nMt. Apo", "Seliban Riv.\nMt. Apo", ("Seliban Riv.", "Mt. Apo"), False),
    ("Seliban Riv.\nMt. Apo, Davao", "Seliban Riv.\nMt. Apo, Davao", ("Seliban Riv.", "Mt. Apo", "Davao"), False),
    # A line holding no candidate joins them (e98a924c's lines, none filed).
    ("Seliban Riv.\nnear the ford", "Seliban Riv.\nnear the ford", ("Seliban Riv.",), False),
], ids=["extends-on-its-line", "one-line", "a-candidate-a-line", "two-on-a-line", "a-line-of-its-own"])
def test_a_run_over_lines_extends_no_candidate_on_its_line(text, literal, candidates, refused):
    """On 616ae010 "Seliban Riv.\\nnear Mt. Apo" passes as text read from the
    transcript, while "near Mt. Apo" on one line is NOT_CANDIDATE."""
    readings = (Reading("2A", "label2", "obs2a", "decided_transcript", text),
        Reading("2B", "label2", "obs2b", "raw_reading", text))
    found = agreement.literal_refusal(locality_task(*candidates), readings, literal=literal, named=[readings[0]])
    assert (found is not None and found.reason == agreement.NOT_CANDIDATE) == refused


# ---- 4. a locality line that begins with another field's text --------------

CNHM = "CNHM. E Slope Mt.\nMcKinley, Davao Prov.\nMindanao, P.I."
CNHM_A = label_with(**NO_PLACE_LINES, collection_code=None) + "\n" + CNHM
CNHM_B = CNHM_A.replace("leg. J. Smith", "leg. J. Smlth")
TWO_LINES = "E Slope Mt.\nMcKinley, Davao Prov."
NO_PLACES = {key: answering(LACKS) for key in ("country", "province_state", "county", "city")}

CODE_LINE = [*COLLECTORS, *(("collection_code", name, "CNHM. E Slope Mt.", "CNHM. E Slope Mt.") for name in ("1A", "1B"))]


def resolved(literal, *names):
    return answering(FieldAnswer(outcome="resolved", literal=literal, reading_names=list(names) or ["1A", "1B"],
        explanation="Read from the label."))


@pytest.mark.parametrize("decided", [False, True], ids=["no-reading-decided", "decided-transcript"])
def test_a_locality_after_another_fields_text_settles_and_that_field_goes_to_review(tmp_path, decided):
    """e98a924c on 616ae010 (run 629f91eb): the organiser filed the whole
    first line "CNHM. E Slope Mt." as the collection code, its expert kept
    that candidate, and the precise location's expert read "E Slope Mt." /
    "McKinley, Davao Prov.", leaving "CNHM." out. The two texts share "E
    Slope Mt." and neither holds the other. Now the locality settles and
    the collection code, which runs into it, goes to review. On 616ae010
    the locality goes to review and the code settles."""
    rig = build_rig(tmp_path, CNHM_A, CNHM_B, decided=decided, candidates=CODE_LINE)
    run = rig.specimen.run
    settle(rig, Scripted({**NO_PLACES, "collection_code": resolved("CNHM. E Slope Mt.", *(["1A"] if decided else [])),
        "precise_location": resolved(TWO_LINES, *(["1A"] if decided else []))}))
    locality, code = run.fields["precise_location"], run.fields["collection_code"]
    assert (locality.state, locality.literal) == (ValueState.SUPPORTED, TWO_LINES)
    assert field_checks(run, {"precise_location"}) == []
    assert code.state == ValueState.UNRESOLVED
    assert code.reason.startswith("This text runs into the value found for Precise Location.")


def test_a_locality_that_holds_another_fields_whole_text_still_goes_to_review(tmp_path):
    """The other way round: a locality that takes in the code "CNHM." holds
    another field's whole text, and it goes to review as before."""
    candidates = [*COLLECTORS, *(("collection_code", name, "CNHM.", "CNHM.") for name in ("1A", "1B"))]
    rig = build_rig(tmp_path, CNHM_A, CNHM_B, candidates=candidates)
    run = rig.specimen.run
    settle(rig, Scripted({**NO_PLACES, "collection_code": resolved("CNHM."),
        "precise_location": resolved("CNHM. E Slope Mt.\nMcKinley, Davao Prov.")}))
    assert run.fields["collection_code"].state == ValueState.SUPPORTED
    locality = run.fields["precise_location"]
    assert locality.state == ValueState.UNRESOLVED
    assert locality.reason.startswith(field_step.TAKEN.format(other="Collection Code"))


def test_a_locality_beside_a_code_settled_before_this_attempt_still_goes_to_review(tmp_path):
    """A collection code settled before this attempt (or by a person) is not
    researched again, so it cannot go to review: the locality yields to it
    as before."""
    rig = build_rig(tmp_path, CNHM_A, CNHM_B, candidates=CODE_LINE)
    run = rig.specimen.run
    run.fields["collection_code"] = run.fields["collection_code"].model_copy(update={
        "state": ValueState.SUPPORTED, "literal": "CNHM. E Slope Mt.", "layer": "verbatim",
        "source_region_id": run.regions[0].id})
    settle(rig, Scripted({**NO_PLACES, "precise_location": resolved(TWO_LINES)}))
    assert run.fields["collection_code"].state == ValueState.SUPPORTED
    assert run.fields["precise_location"].state == ValueState.UNRESOLVED
    assert run.fields["precise_location"].reason.startswith(field_step.TAKEN.format(other="Collection Code"))
