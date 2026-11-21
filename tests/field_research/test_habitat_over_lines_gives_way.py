"""A Habitat read over consecutive lines gives way where it shares text with another field's answer (lane H4 of the
autonomy program, fix round 1 of PR #464, 2026-11-21; the coordinator's ruling, not the owner's words).

The ruling: for the same expert answers, no field other than Habitat ends differently from origin/main 3eb37c11.
origin/main reads a habitat from the transcript within one line only, so it refuses a habitat literal that holds a
line break; the lane accepts one over consecutive lines (agreement.ACROSS_LINES). On the reviewed head 3df404ea such a
literal settled provisionally (step._first_pass) and the guard on shared text (step._taken) then sent ANOTHER field's
answer on the same text to review (round 1 of the review, finding 1). Now that literal claims no text against
another field (agreement.GIVES_WAY), it goes to review itself where its text is in another kind of field's settled
value or resolved answer, and rule A marks no other field absent because of it (step._settled_claims).

Each case runs the real step (research, apply_outcomes, finalize_fields) twice on one made-up label: with the
habitat answer under test, and with a habitat answer that settles nothing on either tree (its literal is in no
reading). Every field but Habitat must come out the same in both. What origin/main 3eb37c11 and the reviewed head
3df404ea do with each case was run on those trees: ~/specimen-golive/autonomy-program/H4/fix1_probe_*.txt.
"""

from __future__ import annotations

import pytest
from test_location_level_roles import NO_PLACE_LINES
from test_step import (
    COLLECTORS,
    LABEL,
    LACKS,
    TEXT,
    Scripted,
    answering,
    build_rig,
    cleared_as_not_on_label,
    failing,
    label_with,
    research,
    settle,
)

from specimen_digitization.application.domain import ValueState
from specimen_digitization.field_research import agreement
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FieldAnswer

HOST = "Mus\nmusculus"
NOWHERE = "Text no reading writes"


def resolved(literal):
    return FieldAnswer(outcome="resolved", literal=literal, reading_names=["1A", "1B"], explanation="As written.")


def others(run):
    """Every field but Habitat as the step leaves it; evidence ids are made anew on every application."""
    return {key: (value.state, value.literal, value.parsed, value.normalized, value.layer, value.reason)
        for key, value in run.fields.items() if key != "habitat"}


def settled_with(tmp_path, text, habitat, answers=None, *, candidates=COLLECTORS):
    """(the run with the habitat answer under test, the run where the habitat answer settles nothing)."""
    runs = []
    for folder, literal in (("under-test", habitat), ("baseline", NOWHERE)):
        rig = build_rig(tmp_path / folder, text, text, candidates=candidates)
        settle(rig, Scripted({**(answers or {}), "habitat": answering(resolved(literal))}))
        runs.append(rig.specimen.run)
    assert runs[1].fields["habitat"].state == ValueState.UNRESOLVED
    return runs


def test_only_the_habitat_gives_way_and_the_precise_location_keeps_its_rules():
    assert agreement.GIVES_WAY == frozenset({"habitat"}) and agreement.GIVES_WAY < agreement.ACROSS_LINES


# ---- (i) the collection code's line above the host -------------------------------------------------------------

# The code alone on its line (read from the transcript: no keyed line, no candidate), then the host's two lines.
CODE_ABOVE = TEXT.replace("collection_code: SYNTHETIC\n", f"SYNTHETIC\n{HOST}\n").replace(
    "habitat: Synthetic grassland\n", "")
CODE = {"collection_code": answering(resolved("SYNTHETIC"))}


def test_a_habitat_that_runs_on_from_the_collection_codes_line_gives_way_to_the_code(tmp_path):
    """Round 1's case: the code's expert answers the code, the habitat's expert the code's line and the host's two.
    origin/main: the code settles, the habitat is refused (not this field's text). 3df404ea: both went to review,
    each naming the other. Now the code settles as on origin/main and the habitat goes to review, naming the
    code."""
    run, baseline = settled_with(tmp_path, CODE_ABOVE, f"SYNTHETIC\n{HOST}", CODE)
    code = run.fields["collection_code"]
    assert (code.state, code.literal, code.layer) == (ValueState.SUPPORTED, "SYNTHETIC", "verbatim")
    assert others(run) == others(baseline)
    habitat = run.fields["habitat"]
    assert (habitat.state, habitat.literal) == (ValueState.UNRESOLVED, None)
    assert habitat.reason.startswith(field_step.TAKEN.format(other="Collection Code"))


def test_the_host_alone_below_the_code_settles_and_the_code_with_it(tmp_path):
    """(iv) A two-line habitat that shares no text: both settle. On origin/main the habitat is refused."""
    run, baseline = settled_with(tmp_path, CODE_ABOVE, HOST, CODE)
    assert (run.fields["habitat"].state, run.fields["habitat"].literal) == (ValueState.SUPPORTED, HOST)
    assert run.fields["collection_code"].state == ValueState.SUPPORTED and others(run) == others(baseline)


# ---- (ii) the taxon's line above a habitat's -------------------------------------------------------------------

TAXON_ABOVE = TEXT.replace("taxon: Danaus plexippus\n", "Danaus plexippus\nmeadow\n").replace(
    "habitat: Synthetic grassland\n", "")
LONGER_NAME = "The label writes a longer scientific name than this value."


def test_a_habitat_that_runs_on_from_the_taxons_line_gives_way_though_the_taxon_settles_nothing(tmp_path):
    """The taxon's answer rests on the name's line and settles nothing (its own check refuses it: origin/main's
    reason). 3df404ea settled the habitat over that line and gave the taxon the reason that Habitat holds its
    text. Now the taxon keeps origin/main's reason, and the habitat, whose text is in the taxon's answer, goes to
    review saying so."""
    run, baseline = settled_with(tmp_path, TAXON_ABOVE, "Danaus plexippus\nmeadow")
    taxon = run.fields["taxon"]
    assert taxon.state == ValueState.UNRESOLVED and taxon.reason.startswith(LONGER_NAME)
    assert others(run) == others(baseline)
    habitat = run.fields["habitat"]
    assert (habitat.state, habitat.literal) == (ValueState.UNRESOLVED, None)
    assert habitat.reason.startswith(field_step.ANSWERED.format(other="Taxon"))


# ---- (iii) the precise location, itself read over consecutive lines --------------------------------------------

LOCALITY = "E Slope Mt.\nMcKinley, Davao Prov."
LOCALITY_ABOVE = label_with(**NO_PLACE_LINES).replace("habitat: Synthetic grassland\n", "") + (
    f"\nCNHM. {LOCALITY}\n{HOST}")
PLACES = {**{key: answering(LACKS) for key in ("country", "province_state", "county", "city")},
    "precise_location": answering(resolved("E Slope Mt. McKinley, Davao Prov."))}


@pytest.mark.parametrize(("habitat", "reason"), [
    # The habitat holds the locality whole: 3df404ea sent both to review.
    (f"{LOCALITY}\n{HOST}", field_step.TAKEN),
    # It overlaps the locality's second line only: the place stood on 3df404ea too (step._partly).
    (f"McKinley, Davao Prov.\n{HOST}", field_step.RUNS_INTO),
], ids=["whole", "partly"])
def test_a_habitat_that_runs_on_from_the_locality_gives_way_to_the_precise_location(tmp_path, habitat, reason):
    """origin/main: the precise location settles over its two lines, the habitat is refused."""
    run, baseline = settled_with(tmp_path, LOCALITY_ABOVE, habitat, PLACES)
    place = run.fields["precise_location"]
    assert (place.state, place.literal) == (ValueState.SUPPORTED, LOCALITY)
    assert others(run) == others(baseline)
    value = run.fields["habitat"]
    assert (value.state, value.literal) == (ValueState.UNRESOLVED, None)
    assert value.reason.startswith(reason.format(other="Precise Location"))


def test_the_host_alone_below_the_locality_settles_beside_the_precise_location(tmp_path):
    run, baseline = settled_with(tmp_path, LOCALITY_ABOVE, HOST, PLACES)
    assert (run.fields["habitat"].state, run.fields["habitat"].literal) == (ValueState.SUPPORTED, HOST)
    assert run.fields["precise_location"].literal == LOCALITY and others(run) == others(baseline)


# ---- rule A: a field the organiser gave the host's two lines ---------------------------------------------------

METHOD_LINES = TEXT.replace("habitat: Synthetic grassland\n", "").replace(
    f"collection_method: {LABEL['collection_method']}\n", f"{HOST}\n")
METHOD_CANDIDATE = [*COLLECTORS, *(("collection_method", name, HOST, HOST) for name in ("1A", "1B"))]


def test_rule_a_marks_no_field_absent_because_a_habitat_over_two_lines_holds_its_text(tmp_path):
    """The organiser offered the host's two lines as the collecting method; the method's expert finds none; the
    habitat's expert settles those lines. origin/main refuses that habitat, so rule A declines the method (the
    organiser found text for it) and it stays for a person. On 3df404ea the settled habitat held the text and
    rule A marked the method not on the label. Now rule A declines as on origin/main."""
    rig = build_rig(tmp_path, METHOD_LINES, METHOD_LINES, candidates=METHOD_CANDIDATE)
    run = rig.specimen.run
    prepared, outcomes, calls = research(rig, Scripted({"collection_method": answering(LACKS),
        "habitat": answering(resolved(HOST))}))
    decisions: dict[str, dict] = {}
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    assert (run.fields["habitat"].state, run.fields["habitat"].literal) == (ValueState.SUPPORTED, HOST)
    assert decisions["collection_method"] == {"rule": "A_declined:organiser_found_text"}
    assert "collection_method" not in cleared_as_not_on_label(run)


# ---- a retry: the one path where a field other than Habitat can end otherwise ----------------------------------

def test_a_habitat_an_earlier_attempt_settled_over_two_lines_holds_its_text_in_a_retry(tmp_path):
    """Stated as it is, not as the ruling would have it: the guard compares the answers of ONE attempt. Where an
    earlier attempt settled the habitat over two lines and failed another field for a reason the workflow retries,
    the retry does not ask the habitat again (step.build_tasks), and the field it asks, answering text inside the
    habitat's lines, goes to review as beside any value settled before the attempt (step._taken's rule, origin/main's:
    whichever settled first). origin/main would have refused the habitat in the first attempt and asked it again in
    the retry, so the two trees do not apply the same answers here."""
    rig = build_rig(tmp_path, CODE_ABOVE, CODE_ABOVE, candidates=COLLECTORS)
    run = rig.specimen.run
    settle(rig, Scripted({"collection_code": failing("timeout"), "habitat": answering(resolved(HOST))}))
    assert (run.fields["habitat"].state, run.fields["habitat"].literal) == (ValueState.SUPPORTED, HOST)
    assert run.fields["collection_code"].state == ValueState.UNRESOLVED
    retry = Scripted({"collection_code": answering(resolved("Mus")), "habitat": answering(resolved(HOST))})
    settle(rig, retry)
    assert "collection_code" in retry.calls and "habitat" not in retry.calls
    code = run.fields["collection_code"]
    assert code.state == ValueState.UNRESOLVED and code.reason.startswith(field_step.TAKEN.format(other="Habitat"))
    assert (run.fields["habitat"].state, run.fields["habitat"].literal) == (ValueState.SUPPORTED, HOST)
