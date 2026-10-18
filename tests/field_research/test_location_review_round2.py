"""Round 1 of PR #380's review (2026-10-18): its four non-blocking findings.

1. A field that only runs into a place that settles is told so ("This text
   runs into the value found for ..."), not that its text was read from the
   transcript and is the place's value.
2. The country check's line reading sets aside only what a supported value
   holds: the country expert's own unresolved "Canada" still holds the
   places below it back.
3. A label's other reader's line at the place lines' index is read too:
   "Canada" on a line of its own.
4. A date or an elevation inside a group is set aside and the rest weighed:
   "Canada 1948", "Canada 1200 ft".

The answers are made up in the shape the run graphs store them, not
recorded responses.
"""

from __future__ import annotations

import pytest
from test_location_last_gaps import (
    COLES_B,
    COLES_CANDIDATES,
    COUNTRY_LOOKUPS,
    COUNTY,
    STATE,
    Answers,
    coles,
    fallback,
)
from test_location_level_roles import NO_PLACE_LINES, expert
from test_step import COLLECTORS, LACKS, Scripted, answering, build_rig, label_with, research, settle

from specimen_digitization.application.domain import ValueState
from specimen_digitization.field_research.contracts import FieldAnswer
from specimen_digitization.field_research.step import apply_outcomes

RUNS_INTO = "This text runs into the value found for Precise Location."
NO_PLACES = {key: answering(LACKS) for key in ("country", "province_state", "county", "city")}


def resolved(literal, *names):
    return answering(FieldAnswer(outcome="resolved", literal=literal, reading_names=list(names) or ["1A", "1B"],
        explanation="Read from the label."))


# ---- 1. the reason of a field that runs into a place -----------------------

def test_a_collector_that_runs_into_the_locality_is_told_so(tmp_path):
    """The review's probe: "leg. J. Smith Creek, 2 mi N", the collector the
    organiser's "J. Smith" and the locality "Smith Creek, 2 mi N" read from
    the transcript. They share "Smith"; the locality settles, and the
    collectors go to review with a reason that says the collector runs into
    it. On 0346a26e the reason says the collector's text was read from the
    transcript and is the locality's value, neither of which is true."""
    line = "leg. J. Smith Creek, 2 mi N"
    text = label_with(**NO_PLACE_LINES).replace("leg. J. Smith", line)
    rig = build_rig(tmp_path, text, text.replace("Synthetic net", "Synthetic nets"),
        candidates=[("collectors", name, "J. Smith", line) for name in ("1A", "1B")])
    run = rig.specimen.run
    settle(rig, Scripted({**NO_PLACES, "collectors": resolved("J. Smith"),
        "precise_location": resolved("Smith Creek, 2 mi N")}))
    assert run.fields["precise_location"].state == ValueState.SUPPORTED
    collectors = run.fields["collectors"]
    assert collectors.state == ValueState.UNRESOLVED
    assert collectors.reason.startswith(RUNS_INTO)
    assert "read from the transcript" not in collectors.reason


# ---- 2. an unresolved value holds no text on the place line ----------------

def test_the_country_experts_unresolved_canada_still_holds_the_places_back(tmp_path):
    """The other reader writes "Canada: Ill. Coles Co.", no candidate filed
    for it, and the country expert answers sources_cannot_resolve with the
    literal "Canada", which the field keeps. Its value settles nothing, so
    it sets no text aside: the state and the county are refused NO_COUNTRY.
    On 0346a26e they settle inside the United States."""
    other = COLES_B.replace("U.S.B.I.L.: Coles Co.,", "Canada: Ill. Coles Co.")
    country = expert(*COUNTRY_LOOKUPS, answer=lambda found: FieldAnswer(outcome="sources_cannot_resolve",
        literal="Canada", reading_names=["1B"], explanation="1B writes Canada, 1A USA."))
    run, decisions = coles(tmp_path, other, country=country)
    assert (run.fields["country"].state, run.fields["country"].literal) == (ValueState.UNRESOLVED, "Canada")
    assert decisions["province_state"].get("refusal") == "no_country"
    assert decisions["county"].get("refusal") == "no_country"


# ---- 3. the other reader's line at the place lines' index ------------------

LINED_A = label_with(**NO_PLACE_LINES) + "\nUSA\nIll.\nColes Co.\nFox Ridge State Park"
LINED_CANDIDATES = [*COLLECTORS, ("country", "1A", "USA", "USA"), ("province_state", "1A", "Ill.", "Ill."),
    ("county", "1A", "Coles Co.", "Coles Co.")]


def lined(tmp_path, first_line):
    rig = build_rig(tmp_path, LINED_A, LINED_A.replace("\nUSA\n", f"\n{first_line}\n"), candidates=LINED_CANDIDATES)
    run = rig.specimen.run
    decisions: dict[str, dict] = {}
    prepared, outcomes, calls = research(rig, Scripted({"country": fallback(*COUNTRY_LOOKUPS),
        "province_state": STATE, "county": COUNTY, "city": answering(LACKS),
        "precise_location": answering(LACKS)}), tools=Answers(rig.blobs))
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    return run, decisions


def test_a_country_on_a_line_of_its_own_still_holds_the_places_back(tmp_path):
    """Reader 1A writes "USA" over "Ill." over "Coles Co.", reader 1B
    "Canada" over the same two lines, and only 1A's texts are filed. 1B's
    first line writes no place text of the record, but it stands where 1A's
    "USA" does. On 0346a26e the country derives as the United States."""
    run, decisions = lined(tmp_path, "Canada")
    assert decisions["province_state"].get("refusal") == "no_country"
    assert decisions["county"].get("refusal") == "no_country"
    assert run.fields["country"].layer is None


def test_a_word_no_source_found_on_that_line_holds_nothing_back(tmp_path):
    run, _ = lined(tmp_path, "U.S.B.I.L.")
    assert run.fields["county"].authority_id == "wikidata:Q112137"
    assert (run.fields["country"].layer, run.fields["country"].parsed) == ("derived", "United States")


# ---- 4. a date or an elevation inside a group ------------------------------

@pytest.mark.parametrize("first", ["Canada 1948", "Canada 1200 ft"], ids=["a-year", "an-elevation"])
def test_a_country_beside_a_date_or_an_elevation_still_holds_the_places_back(tmp_path, first):
    """The year or the elevation is another field's text; the rest of the
    group, "Canada", is weighed. On 0346a26e the whole group passes and the
    country derives as the United States."""
    other = COLES_B.replace("U.S.B.I.L.: Coles Co.,", f"{first}: Ill. Coles Co.")
    run, decisions = coles(tmp_path, other, country=fallback(*COUNTRY_LOOKUPS))
    assert decisions["province_state"].get("refusal") == "no_country"
    assert decisions["county"].get("refusal") == "no_country"
    assert run.fields["country"].layer is None


def test_a_date_alone_on_the_place_line_holds_nothing_back(tmp_path):
    """A date that is the whole group, as "1-9 June 1979" beside the places,
    is set aside and leaves nothing."""
    first = COLES_B.replace("U.S.B.I.L.: Coles Co.,", "1-9 June 1979: Ill. Coles Co.")
    run, _ = coles(tmp_path, first, country=fallback(*COUNTRY_LOOKUPS))
    assert (run.fields["country"].layer, run.fields["country"].parsed) == ("derived", "United States")
