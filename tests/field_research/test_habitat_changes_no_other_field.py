"""For the same expert answers a field other than Habitat ends as on origin/main 3eb37c11 (lane H4 of the autonomy
program, fix round 2 of PR #464, 2026-11-21; the coordinator's ruling, not the owner's words).

The lane changes what a Habitat answer does in two ways, and round 2 of the review showed each reaching another field:

- A Habitat origin/main settled and this lane refuses: one that starts with the heading "Host". On 19761d59 the
  refusal kept it out of the settled values the guard on shared text reads (step._taken), so a field whose answer
  rests on the same text settled where origin/main sent it to review. Now the heading refusal is left out of the
  pass before the guard (step._first_pass, step._BEFORE_GUARD): the Habitat claims there the text it claimed on
  origin/main, and is refused where the answers are applied to the record.
- A Habitat origin/main refused and this lane settles: text read from the transcript over consecutive lines. Wherever
  a settled value's text relaxes another field's decision it counts for nothing (step._over_lines): round 1 did so
  for the guard and for rule A's not-on-the-label mark (test_habitat_over_lines_gives_way.py); round 2 for the text a
  line of places holds (step._unplaced_text, Codex's finding) and for the words a settled value accounts for before
  owner decision B clears a code with no genus (step._genus_on_a_label, found by this lane's own enumeration of the
  readers, ~/specimen-golive/autonomy-program/H4/settled_text_consumers.txt).

What origin/main 3eb37c11 and the reviewed head 19761d59 do with each case was run on those trees:
~/specimen-golive/autonomy-program/H4/fix2_probe_*.txt. The label texts are made up.
"""

from __future__ import annotations

import pytest
from test_location_last_gaps import COUNTRY_LOOKUPS, COUNTY, STATE, Answers, fallback
from test_location_level_roles import NO_PLACE_LINES
from test_step import (
    COLLECTORS,
    LACKS,
    TEXT,
    TODAY,
    NoGenus,
    Scripted,
    answering,
    build_rig,
    cannot_resolve,
    failing,
    label_with,
    settle,
)
from test_taxon_scope import without_the_taxon_line

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.field_research import agreement
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FieldAnswer, FieldTask, Reading

NOWHERE = "Text no reading writes"


def resolved(literal):
    return FieldAnswer(outcome="resolved", literal=literal, reading_names=["1A", "1B"], explanation="As written.")


def others(run):
    """Every field but Habitat as the step leaves it; evidence ids are made anew on every application."""
    return {key: (value.state, value.literal, value.parsed, value.normalized, value.layer, value.reason)
        for key, value in run.fields.items() if key != "habitat"}


def settled_with(tmp_path, text, habitat, answers=None):
    """(the run with the habitat answer under test, the run where the habitat answer settles nothing)."""
    runs = []
    for folder, literal in (("under-test", habitat), ("baseline", NOWHERE)):
        rig = build_rig(tmp_path / folder, text, text, candidates=COLLECTORS)
        settle(rig, Scripted({**(answers or {}), "habitat": answering(resolved(literal))}))
        runs.append(rig.specimen.run)
    return runs


# ---- the heading: a claim origin/main's Habitat made --------------------------------------------------------------

def test_the_heading_check_is_left_out_only_where_the_caller_says_so():
    """The expert's own check and the application to the record refuse the heading (the default); only the step's
    pass before its guard leaves the check out."""
    text = "Synthetic Museum\nHost: Mus\nleg. J. Smith"
    readings = (Reading("1A", "label1", "obs1a", "raw_reading", text), Reading("1B", "label1", "obs1b", "raw_reading", text))
    task = FieldTask("habitat", False, FieldValue(), (), ())
    refused = agreement.literal_refusal(task, readings, literal="Host: Mus", named=readings)
    assert refused is not None and refused.reason == agreement.HOST_HEADING
    assert agreement.literal_refusal(task, readings, literal="Host: Mus", named=readings, heading=False) is None
    assert field_step._BEFORE_GUARD.get() is False


HOST_CODE = TEXT.replace("collection_code: SYNTHETIC\n", "").replace("habitat: Synthetic grassland\n", "Host: CNHM\n")


def test_a_heading_habitat_still_takes_the_text_it_took_on_origin_main_from_the_collection_code(tmp_path):
    """Codex's round-2 sequence: both readers write "Host: CNHM", neither field has a candidate, the code's expert
    answers "CNHM" and the habitat's "Host: CNHM". origin/main: both settle before the guard and each goes to review
    naming the other. 19761d59: the heading refusal came first, so the code settled. Now the code goes to review as
    on origin/main, and the Habitat, never settled with the heading, goes to review too."""
    rig = build_rig(tmp_path, HOST_CODE, HOST_CODE, candidates=COLLECTORS)
    run = rig.specimen.run
    settle(rig, Scripted({"collection_code": answering(resolved("CNHM")), "habitat": answering(resolved("Host: CNHM"))}))
    code, habitat = run.fields["collection_code"], run.fields["habitat"]
    assert (code.state, code.literal) == (ValueState.UNRESOLVED, None)
    assert code.reason.startswith(field_step.TAKEN.format(other="Habitat"))
    assert (habitat.state, habitat.literal) == (ValueState.UNRESOLVED, None)
    assert habitat.reason.startswith(field_step.TAKEN.format(other="Collection Code"))


HOST_TAXON = TEXT.replace("taxon: Danaus plexippus\n", "").replace(
    "habitat: Synthetic grassland\n", "Host: Danaus plexippus\n")


def test_a_heading_habitat_still_sends_the_taxon_on_the_hosts_name_to_review(tmp_path):
    """The same with the Taxon answering the host's name as its own. origin/main: the Habitat settles "Host: ..." and
    the Taxon goes to review, its reason naming the Habitat. 19761d59: the Taxon kept its own check's reason. Now the
    Taxon's value, state and reason are origin/main's; the Habitat is refused for the heading (on origin/main it
    settled with it), so the Taxon's reason names a field that holds no value."""
    rig = build_rig(tmp_path, HOST_TAXON, HOST_TAXON, candidates=COLLECTORS)
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": answering(resolved("Danaus plexippus")),
        "habitat": answering(resolved("Host: Danaus plexippus"))}))
    taxon, habitat = run.fields["taxon"], run.fields["habitat"]
    assert taxon.state == ValueState.UNRESOLVED and taxon.reason.startswith(field_step.TAKEN.format(other="Habitat"))
    assert (habitat.state, habitat.literal) == (ValueState.UNRESOLVED, None)
    assert habitat.reason.startswith(agreement.HOST_HEADING)


def test_a_heading_habitat_that_shares_no_text_is_refused_and_nothing_else_moves(tmp_path):
    text = TEXT.replace("habitat: Synthetic grassland\n", "Host: Mus\n")
    run, baseline = settled_with(tmp_path, text, "Host: Mus")
    habitat = run.fields["habitat"]
    assert (habitat.state, habitat.literal) == (ValueState.UNRESOLVED, None)
    assert habitat.reason.startswith(agreement.HOST_HEADING)
    assert others(run) == others(baseline)


@pytest.mark.parametrize(("lines", "habitat", "taken"), [
    # Over the code's text: origin/main refused it (a line break), so there it claimed nothing; here neither, and
    # the code's settled text takes it.
    ("Host: CNHM\nMus", "Host: CNHM\nMus", True),
    # Sharing no text: refused for the heading.
    ("Host:\nMus\nmusculus", "Host:\nMus\nmusculus", False),
], ids=["over-the-code", "alone"])
def test_a_heading_habitat_over_two_lines_claims_nothing_and_is_refused(tmp_path, lines, habitat, taken):
    """Both rules meet: before the guard such a Habitat settles (the heading check is left out there, and it runs
    over lines), but as text read over consecutive lines it claims nothing, as on origin/main, which refused it for
    the line break. Every other field is as where the habitat answer settles nothing."""
    text = TEXT.replace("collection_code: SYNTHETIC\n", "").replace("habitat: Synthetic grassland\n", lines + "\n")
    run, baseline = settled_with(tmp_path, text, habitat, {"collection_code": answering(resolved("CNHM"))})
    value = run.fields["habitat"]
    reason = field_step.TAKEN.format(other="Collection Code") if taken else agreement.HOST_HEADING
    assert (value.state, value.literal) == (ValueState.UNRESOLVED, None) and value.reason.startswith(reason)
    assert others(run) == others(baseline)
    if taken:
        assert (run.fields["collection_code"].state, run.fields["collection_code"].literal) == (
            ValueState.SUPPORTED, "CNHM")


# ---- a line of places: the text a settled value holds (step._unplaced_text) ----------------------------------------

PLACE_LINES = "USA: Canada\nMarmota\nIll.\nColes Co."
PLACES_TEXT = label_with(**NO_PLACE_LINES).replace("habitat: Synthetic grassland\n", "") + "\n" + PLACE_LINES
PLACE_CANDIDATES = [*COLLECTORS, *(item for name in ("1A", "1B") for item in (
    ("country", name, "USA", "USA: Canada"), ("province_state", name, "Ill.", "Ill."),
    ("county", name, "Coles Co.", "Coles Co.")))]
NO_FINER = {"city": answering(LACKS), "precise_location": answering(LACKS)}
COUNTRY = fallback(*COUNTRY_LOOKUPS[:2])


def test_a_habitat_over_two_lines_does_not_hold_text_that_may_be_another_country(tmp_path):
    """Codex's round-2 sequence. Both readers write "USA: Canada" / "Marmota" / "Ill." / "Coles Co."; the organiser
    files USA, Ill. and Coles Co. Attempt 1: the Habitat answers "Canada" over "Marmota" and settles; the
    Province/State's and the County's experts time out; the Country falls back after its lookups. The retry: the two
    lower places answer their source records, the Country falls back again, the Habitat is not asked. origin/main
    (which refused that Habitat) weighs the unfiled "Canada" and refuses both lower places for want of a country
    (agreement.NO_COUNTRY). On 19761d59 the settled Habitat held "Canada" and both settled. Now both are refused, as
    on origin/main; and a finalize after it moves no field."""
    rig = build_rig(tmp_path, PLACES_TEXT, PLACES_TEXT, candidates=PLACE_CANDIDATES)
    run = rig.specimen.run
    habitat = answering(resolved("Canada\nMarmota"))
    settle(rig, Scripted({**NO_FINER, "country": COUNTRY, "province_state": failing("timeout"),
        "county": failing("timeout"), "habitat": habitat}), tools=Answers(rig.blobs))
    assert (run.fields["habitat"].state, run.fields["habitat"].literal) == (ValueState.SUPPORTED, "Canada\nMarmota")
    retry = Scripted({**NO_FINER, "country": COUNTRY, "province_state": STATE, "county": COUNTY, "habitat": habitat})
    settle(rig, retry, tools=Answers(rig.blobs))
    assert "habitat" not in retry.calls and {"province_state", "county"} <= set(retry.calls)
    for key in ("province_state", "county"):
        value = run.fields[key]
        assert value.state == ValueState.UNRESOLVED and value.reason.startswith(agreement.NO_COUNTRY), key
    assert run.fields["habitat"].state == ValueState.SUPPORTED
    before = {key: value.model_dump(mode="json") for key, value in run.fields.items()}
    field_step.refinalize(run, today=TODAY)
    assert {key: value.model_dump(mode="json") for key, value in run.fields.items()} == before


def test_in_one_attempt_the_places_are_decided_before_the_habitat_is_applied(tmp_path):
    """The same label with every expert answering in one attempt: the places are applied first (from the country
    down), so the Habitat of the same attempt is not yet a value when "Canada" is weighed. Refused on every tree."""
    rig = build_rig(tmp_path, PLACES_TEXT, PLACES_TEXT, candidates=PLACE_CANDIDATES)
    run = rig.specimen.run
    settle(rig, Scripted({**NO_FINER, "country": COUNTRY, "province_state": STATE, "county": COUNTY,
        "habitat": answering(resolved("Canada\nMarmota"))}), tools=Answers(rig.blobs))
    assert run.fields["province_state"].reason.startswith(agreement.NO_COUNTRY)
    assert run.fields["county"].reason.startswith(agreement.NO_COUNTRY)


# ---- owner decision B: the words a settled value accounts for (step._genus_on_a_label) -----------------------------

def code_beside(tmp_path, lines, habitat):
    """A label that writes the code "sp. 22" with no genus, and `lines` in the habitat's place; the taxon's expert
    asks GBIF the code and cannot resolve it; the habitat's expert answers `habitat`."""
    text = without_the_taxon_line("sp. 22").replace("habitat: Synthetic grassland\n", lines + "\n")
    rig = build_rig(tmp_path, text)
    settle(rig, Scripted({"taxon": cannot_resolve("sp. 22", asks=["sp. 22"]), "habitat": answering(resolved(habitat))}),
        tools=NoGenus(rig.blobs))
    return rig.specimen.run


def test_a_habitat_over_two_lines_accounts_for_no_word_that_may_be_a_genus(tmp_path):
    """The host "Mus" over "musculus": on origin/main the Habitat is refused, "Mus" may be the specimen's genus, and
    owner decision B does not clear the code (the Taxon stays unresolved). On 19761d59 the settled Habitat accounted
    for both words and the Taxon cleared as written, unmatched, in the same attempt. Now the Taxon is as on
    origin/main and as where the habitat answer settles nothing."""
    run = code_beside(tmp_path / "host", "Mus\nmusculus", "Mus\nmusculus")
    baseline = code_beside(tmp_path / "baseline", "Mus\nmusculus", NOWHERE)
    assert (run.fields["habitat"].state, run.fields["habitat"].literal) == (ValueState.SUPPORTED, "Mus\nmusculus")
    taxon = run.fields["taxon"]
    assert (taxon.state, taxon.literal) == (ValueState.UNRESOLVED, "sp. 22")
    assert others(run) == others(baseline)
    assert field_step._genus_on_a_label(run, field_step.run_readings(run)) == "Mus"


def test_a_habitat_on_one_line_accounts_for_its_words_as_on_origin_main(tmp_path):
    """The control: a host on one line settles on origin/main too, accounts for its words, and decision B clears
    the code."""
    run = code_beside(tmp_path, "Mus musculus", "Mus musculus")
    taxon = run.fields["taxon"]
    assert (taxon.state, taxon.literal, taxon.reason) == (ValueState.SUPPORTED, "sp. 22", field_step.UNMATCHED)


# ---- what remains of the heading refusal outside the guard: stated limits, each toward review ---------------------

def test_limit_a_heading_habitat_accounts_for_no_word_so_the_code_goes_to_review(tmp_path):
    """Stated as it is. origin/main settles "Host: Mus", which accounts for "Mus", and decision B clears the code
    "sp. 22". Here the Habitat is refused for the heading at the application to the record, "Mus" may then be the
    specimen's genus, and the Taxon stays unresolved: another field ends otherwise than on origin/main, toward review
    (as on 19761d59). The heading Habitat claims only in the guard; it is never a settled value."""
    run = code_beside(tmp_path, "Host: Mus", "Host: Mus")
    assert run.fields["habitat"].state == ValueState.UNRESOLVED
    assert (run.fields["taxon"].state, run.fields["taxon"].literal) == (ValueState.UNRESOLVED, "sp. 22")


def test_limit_rule_a_declines_a_field_whose_organiser_text_is_the_heading_habitats(tmp_path):
    """Stated as it is. The organiser offered "Host: Mus" as the collecting method; the method's expert finds none;
    the habitat's expert answers "Host: Mus". origin/main settles that Habitat and rule A marks the method not on the
    label. Here the Habitat is refused, so rule A declines the method and it stays for a person: toward review (as on
    19761d59)."""
    from test_step import LABEL, cleared_as_not_on_label, research

    text = TEXT.replace("habitat: Synthetic grassland\n", "").replace(
        f"collection_method: {LABEL['collection_method']}\n", "Host: Mus\n")
    candidates = [*COLLECTORS, *(("collection_method", name, "Host: Mus", "Host: Mus") for name in ("1A", "1B"))]
    rig = build_rig(tmp_path, text, text, candidates=candidates)
    run = rig.specimen.run
    prepared, outcomes, calls = research(rig, Scripted({"collection_method": answering(LACKS),
        "habitat": answering(resolved("Host: Mus"))}))
    decisions: dict[str, dict] = {}
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    assert run.fields["habitat"].state == ValueState.UNRESOLVED
    assert decisions["collection_method"] == {"rule": "A_declined:organiser_found_text"}
    assert "collection_method" not in cleared_as_not_on_label(run)
