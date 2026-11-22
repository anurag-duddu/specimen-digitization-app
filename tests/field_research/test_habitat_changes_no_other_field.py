"""For the same expert answers a field other than Habitat ends as on origin/main 3eb37c11 (lane H4 of the autonomy
program, fix round 2 of PR #464, 2026-11-21; the coordinator's ruling, not the owner's words).

The lane changes what a Habitat answer does in two ways, and round 2 of the review showed each reaching another field:

- A Habitat origin/main settled and this lane refuses: one that starts with the heading "Host". ONE STATED LIMIT, in
  either direction (the coordinator's ruling of round 3): a field whose decision reads a settled Habitat's text is
  decided beside a Habitat that did not settle, which can send it to review where origin/main settled it, or lose a
  refusal, reason or mark origin/main gives. On the resolver's path (production) the expert's own check refuses
  such an answer and sends the expert back; where no later answer of that attempt passes the check (the expert
  repeats the heading, or its later answers are refused for another reason, or it then answers that the sources
  cannot resolve it) the Habitat does not settle and claims nothing in the guard. Where a RESOLVED heading answer
  reaches the step directly (a recorded answer applied again; these tests; a rig's dry run), round 2 left the
  step's heading refusal out of the pass before the guard (step._first_pass, step._BEFORE_GUARD), so there the
  Habitat claims in the guard the text it claimed on origin/main and is refused at the application to the record.
  The tests of the first section inject resolved outcomes at the step and show that path only; the tests named
  "through the resolver" run the expert's check and its retries with a stand-in model.
- A Habitat origin/main refused and this lane settles: text read from the transcript over consecutive lines. In the
  readers found where a settled value's text relaxes another field's decision it counts for nothing, the whole
  value, its literal, each reader's verbatim of it and its label rows (step._over_lines): round 1 did so for the
  guard and for rule A's not-on-the-label mark (test_habitat_over_lines_gives_way.py); round 2 for the text a line
  of places holds (step._unplaced_text, Codex's finding) and for the words a settled value accounts for before
  owner decision B clears a code with no genus (step._genus_on_a_label, found by this lane's own list of the
  readers, ~/specimen-golive/autonomy-program/H4/settled_text_consumers.txt); round 3 for the texts the precise
  location's extent check blanks from the line after the locality (ontology_checks.stage, Codex's finding: another
  reader's verbatim on one line).

What origin/main 3eb37c11 and the reviewed head 19761d59 do with each case was run on those trees:
~/specimen-golive/autonomy-program/H4/fix2_probe_*.txt and, for round 3, fix3_probe_*.txt (origin/main, 575367fe and
this lane's head). The label texts are made up.
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


# ---- the heading, where a RESOLVED answer reaches the step: a claim origin/main's Habitat made --------------------

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
    naming the other. 19761d59: the heading refusal came first, so the code settled. Now, for these two RESOLVED
    outcomes given to the step, the code goes to review as on origin/main, and the Habitat goes to review too. On
    the resolver's path the same model answers end otherwise: test_limit_an_expert_that_repeats_the_heading..."""
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


# ---- the heading limit at the step: two cases that go toward review (it runs the other way too: the last section) --

def test_limit_a_heading_habitat_accounts_for_no_word_so_the_code_goes_to_review(tmp_path):
    """Stated as it is. origin/main settles "Host: Mus", which accounts for "Mus", and decision B clears the code
    "sp. 22". Here the Habitat is refused for the heading at the application to the record, "Mus" may then be the
    specimen's genus, and the Taxon stays unresolved: another field ends otherwise than on origin/main, toward review
    (as on 19761d59). A heading answer given to the step claims in the guard and is refused at the application
    to the record: it settles no value."""
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


# ---- the precise location's extent mark: each text of a settled value (round 3) -----------------------------------

MCKINLEY_HOST = "E. slope Mt. McKinley\nDavao Prov.\nMus\nmusculus\nMindanao, P.I.\n3 Sept. '46\nF.G. Werner"


def davao_run(tmp_path, monkeypatch, text, other, habitat, candidates=COLLECTORS):
    """105526321's locality with its province "Davao Prov." and country "P.I." settled, the Precise Location
    answered its first line, the Habitat answered `habitat`. The image names each unit both readers write alike
    but the province's, as a first pass unsure of that line would."""
    import test_step
    from test_elevations_and_extent import DAVAO_AND_PI
    from test_precise_location_extent import whole
    from test_step import DavaoProvince

    from specimen_digitization.field_research.contracts import FIELD_TOOLS

    seen = test_step.seen_units

    def province_uncertain(units):
        named = seen(units)
        return named.model_copy(update={"units": [
            before if {span.text for span in before.readers.values()} <= {"Davao", "Prov."} else after
            for before, after in zip(units.units, named.units, strict=True)]})

    monkeypatch.setattr(test_step, "seen_units", province_uncertain)
    rig = build_rig(tmp_path, text, other, candidates=candidates)
    run = rig.specimen.run
    fields = [key for key in FIELD_TOOLS if key != "identified_by_irn"]
    settle(rig, Scripted({**{key: answering(LACKS) for key in fields}, **DAVAO_AND_PI,
        "precise_location": whole("E. slope Mt. McKinley"), "habitat": answering(habitat)}),
        tools=DavaoProvince(rig.blobs))
    return run


def extent_marks(run):
    from specimen_digitization.field_research.ontology_checks import CHECK_STAGE

    return [finding.reason_code for finding in run.findings
        if finding.rule_id == CHECK_STAGE and finding.field_key == "precise_location"]


def test_a_habitat_over_two_lines_blanks_no_text_from_the_line_after_the_locality(tmp_path, monkeypatch):
    """Codex's round-3 sequence. Two raw readers (they differ on the collector's line, so no transcript is decided)
    write "E. slope Mt. McKinley" / "Davao Prov." / "Mus" / "musculus"; the province is settled; the organiser
    offered "Davao Prov." as the Habitat for reader 1B only; the Habitat answers "Mus" over "musculus" naming 1A and
    settles on the image. The settled value keeps 1B's candidate as that reader's verbatim (step._lineage), a text on
    ONE line. origin/main refuses the Habitat and marks the Precise Location cut short before the province's line.
    On 575367fe the extent check blanked "Davao Prov." from 1B's line as the Habitat's text and abstained. Now the
    whole value counts for nothing there, the verbatims with the literal, and the mark stands as on origin/main."""
    other = MCKINLEY_HOST.replace("F.G. Werner", "F.G. Wermer")
    run = davao_run(tmp_path, monkeypatch, MCKINLEY_HOST, other,
        FieldAnswer(outcome="resolved", literal="Mus\nmusculus", reading_names=["1A"], explanation="As written."),
        candidates=[*COLLECTORS, ("habitat", "1B", "Davao Prov.", "Davao Prov.")])
    habitat = run.fields["habitat"]
    assert (habitat.state, habitat.literal) == (ValueState.SUPPORTED, "Mus\nmusculus")
    assert sorted(habitat.verbatim_by_observation.values()) == ["Davao Prov.", "Mus\nmusculus"]
    place = run.fields["precise_location"]
    assert (place.state, place.literal) == (ValueState.SUPPORTED, "E. slope Mt. McKinley")
    assert extent_marks(run) == [field_step.marked_code("precise_location", run.regions[0].id, "precise_location_extent")]


# ---- the heading as ONE stated limit: through the real resolver, and the extent mark ------------------------------

def expert_answering(*literals):
    """A field's expert through the real resolver (experts.make_resolver: the expert's own check and its retries),
    with a stand-in model that answers `literals` in turn as resolved, the last again on every later request; no
    network. Returns (the expert, the literals the model has answered)."""
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    from specimen_digitization.field_research import experts
    from specimen_digitization.field_research.budget import CostMeter

    asked: list[str] = []

    def model(messages, info):
        literal = literals[min(len(asked), len(literals) - 1)]
        asked.append(literal)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"outcome": "resolved",
            "literal": literal, "reading_names": ["1A", "1B"], "explanation": "As the label writes it."})])

    resolver = experts.make_resolver(model_factory=lambda: FunctionModel(model),
        meter=CostMeter(1_000_000, input_micros_per_million=200_000, output_micros_per_million=600_000))

    async def expert(task, readings, tools):
        return await resolver(task, readings, {}, tools=tools)

    return expert, asked


def through_the_resolver(tmp_path, *habitat_answers):
    from test_step import research

    rig = build_rig(tmp_path, HOST_CODE, HOST_CODE, candidates=COLLECTORS)
    run = rig.specimen.run
    habitat, asked = expert_answering(*habitat_answers)
    code, _ = expert_answering("CNHM")
    prepared, outcomes, calls = research(rig, Scripted({"habitat": habitat, "collection_code": code}))
    [received] = [outcome for outcome in outcomes if outcome.key == "habitat"]
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)
    return run, received, asked


def test_limit_an_expert_that_repeats_the_heading_makes_no_claim_so_the_code_settles(tmp_path):
    """One case of the stated limit of the heading, on the resolver's path (Codex round 3, finding 1; the
    coordinator's ruling R2: no code for it). The limit applies wherever no later answer of the attempt passes the
    expert's check; repeating the heading is one way, a later answer refused for another reason is another (Codex
    round 4; run, not pinned: ~/specimen-golive/autonomy-program/H4/fix4_probe_resolver_once.txt).
    Both readers write "Host: CNHM"; the code's model answers "CNHM"; the habitat's model
    answers "Host: CNHM" on every request. The expert's own check refuses each such answer and sends the expert
    back; after its retries the resolver's fallback is the Habitat's outcome (sources_cannot_resolve, no literal),
    so the step receives no resolved Habitat, no claim is made in the guard, and the Collection Code settles.
    origin/main accepts the Habitat's first answer and sends both fields to review (fix3_probe_resolver_*.txt).
    The pass before the guard (step._BEFORE_GUARD) acts only where a resolved heading answer reaches the step."""
    from specimen_digitization.field_research import experts

    run, received, asked = through_the_resolver(tmp_path, "Host: CNHM")
    assert len(asked) > 1 and set(asked) == {"Host: CNHM"}
    assert (received.answer.outcome, received.answer.literal, received.fallback) == ("sources_cannot_resolve", None, True)
    assert received.answer.explanation == experts.UNCHECKED
    code, habitat = run.fields["collection_code"], run.fields["habitat"]
    assert (code.state, code.literal) == (ValueState.SUPPORTED, "CNHM")
    assert (habitat.state, habitat.literal) == (ValueState.UNRESOLVED, None)


def test_an_expert_that_leaves_the_heading_out_when_sent_back_claims_the_name_in_the_guard(tmp_path):
    """The habitat's model answers "Host: CNHM", is sent back by the expert's check, and answers "CNHM". That
    answer is applied by the ordinary rules: read from the transcript on one line, as the code's is, so each goes
    to review naming the other, as on origin/main (where the first answer was accepted and did the same)."""
    run, received, asked = through_the_resolver(tmp_path, "Host: CNHM", "CNHM")
    assert asked == ["Host: CNHM", "CNHM"]
    assert (received.answer.outcome, received.answer.literal, received.fallback) == ("resolved", "CNHM", False)
    code, habitat = run.fields["collection_code"], run.fields["habitat"]
    assert code.state == ValueState.UNRESOLVED and code.reason.startswith(field_step.TAKEN.format(other="Habitat"))
    assert habitat.state == ValueState.UNRESOLVED
    assert habitat.reason.startswith(field_step.TAKEN.format(other="Collection Code"))


def test_limit_a_refused_heading_habitat_is_not_blanked_so_the_extent_check_abstains(tmp_path, monkeypatch):
    """The stated limit, the other direction, at the step (Codex round 3, finding 2, second sequence). The line
    after the locality is "Host: Mus Davao Prov.", the province settled. origin/main settles the Habitat "Host:
    Mus"; with that text blanked the line is the province's alone and the Precise Location is marked cut short.
    Here the Habitat is refused, "Host" and "Mus" stay on the line, and the check abstains: a mark origin/main gives
    is not given."""
    text = "E. slope Mt. McKinley\nHost: Mus Davao Prov.\nMindanao, P.I.\n3 Sept. '46\nF.G. Werner"
    run = davao_run(tmp_path, monkeypatch, text, None, resolved("Host: Mus"))
    assert run.fields["habitat"].state == ValueState.UNRESOLVED
    assert (run.fields["precise_location"].state, run.fields["precise_location"].literal) == (
        ValueState.SUPPORTED, "E. slope Mt. McKinley")
    assert extent_marks(run) == []
