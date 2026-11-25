"""The expert's literal check reads an answer in another letter case or white space as the readings write it (lane C2
of the waiting-fields fix program, 2026-11-25).

The coordinator's ruling for the lane (the coordinator's, the Claude session local_5b5f071c; not the owner's): the
expert's literal check (`literal_not_in_reading`, and the taxon's query check) accepts an answer equal to a reading's
text up to letter case and line breaks or spacing; the settled literal is the reading's own text, never the expert's;
no other comparison changes (agreement keys, rival grouping and the rest of agreement.py stay origin/main's).

The read-only audit of 2026-11-24 found experts' answers refused for letter case or a line break alone: "Delostichus
coxalis" and "DELOSTICHUS COXALIS" where both readers write "DELOSTICHUS" over "COXALIS" (production records 1d84dd11
and 36b7d593), "Bittacus stigmaterus Say" where they write "Bittacus" over "stigmaterus Say" (a1efc490). Those three
stay unsettled: read as the readers write it, the name holds a line break, and a taxon's literal is one line of a
reading or a whole organiser candidate (agreement.literal_refusal, unchanged). They are refused by `not_candidate` now.

experts.written_as finds the one text every named reading writes; experts.whole_as_given keeps the taxon's query check
from taking a piece of a name in capitals, which the scientific-name parser cannot read (it reads "DELOSTICHUS" as no
name, so agreement._longer_written finds no longer name around it).

The label texts here are made up.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from test_first_pass_advice import with_units
from test_step import GBIF_KEY, GBIF_NAME, TEXT, Scripted, build_rig, field_checks, settle

from specimen_digitization.application.domain import Evidence, FieldValue, LookupStatus, ValueState
from specimen_digitization.application.integrity import verify_evidence
from specimen_digitization.field_research import budget, experts
from specimen_digitization.field_research.contracts import (
    FieldAnswer,
    FieldOutcome,
    FieldTask,
    Reading,
    SourceAnswer,
    SourceCandidate,
)


def two_readers_of(first, second):
    return with_units((Reading("2A", "label2", "obs2a", "raw_reading", first),
        Reading("2B", "label2", "obs2b", "raw_reading", second)))


def expert(key, readings, *answers):
    tools = ("gbif",) if key == "taxon" else ()
    made = experts._Expert(FieldTask(key, False, FieldValue(), (), tools), readings,
        SimpleNamespace(sources=tools), None)
    for found in answers:
        made.calls.append(experts._Call(found.source_id, found.query, found.status, found))
    return made


def resolved(literal, *names, **given):
    return FieldAnswer(outcome="resolved", literal=literal, reading_names=list(names),
        explanation="Both readers write it.", **given)


def gbif(query, name, key):
    """GBIF's success for `query`, deciding the candidate `name` (sources._evidence's locator)."""
    return SourceAnswer("gbif", query, LookupStatus.SUCCESS, (SourceCandidate(name, key, "SPECIES"),),
        Evidence(id=f"ev-{key}", kind="authority", source="gbif", locator=key, excerpt=f"{name} | {key} | SPECIES | "),
        note="exact")


def refused_by(made, given):
    with pytest.raises(ModelRetry) as refused:
        made.validate(given)
    return refused.value.check


# ---- the literal check ---------------------------------------------------------------------------------------

COLLECTED = "Synthetic Museum\nLOC: Synthetic Co.\nBOB SYNTHER\n10-IV-1975"


@pytest.mark.parametrize("given", ["Bob Synther", "bob synther", "BOB  SYNTHER", " Bob\nSynther "])
def test_an_answer_in_another_letter_case_or_spacing_is_the_text_the_readings_write(given):
    """The name the readers write in capitals, given in another letter case or white space: the literal is their
    text, and so is the value that was the literal. On origin/main each is refused (literal_not_in_reading)."""
    checked = expert("collectors", two_readers_of(COLLECTED, COLLECTED)).validate(
        resolved(given, "2A", "2B", value=given))
    assert (checked.literal, checked.value, checked.reading_names) == ("BOB SYNTHER", "BOB SYNTHER", ["2A", "2B"])


def test_a_locality_with_a_space_for_a_line_break_and_in_another_letter_case():
    """agreement.across_lines reads a space for a line break only in the readings' letter case; the literal check
    now reads both at once, and the literal is the readers' two lines."""
    label = "SYNTHETIC MUSEUM\nBEAVER DAM S.P.\nMACOUPIN CO., ILL.\nVIII-22, 1979"
    checked = expert("precise_location", two_readers_of(label, label)).validate(
        resolved("Beaver Dam S.P. Macoupin Co., Ill.", "2A", "2B"))
    assert checked.literal == "BEAVER DAM S.P.\nMACOUPIN CO., ILL."


@pytest.mark.parametrize(("first", "second", "given"), [
    # A letter, a digit or a mark more or less is another text.
    ("Star County", "Star County", "Stark County"),
    ("VIII-22, 1946", "VIII-22, 1946", "VIII-22, 1948"),
    ("Yepocapa, 4800ft", "Yepocapa, 4800ft", "Yepocapa, 4800ft."),
    ("Mt. Synth", "Mt. Synth", "Mt Synth"),
    # A space more or less is another text.
    ("Sp.30", "Sp.30", "Sp. 30"),
    ("F. G. Synther", "F. G. Synther", "F.G. Synther"),
    # Readers who write it in different letter case write no one text: the answer naming both is refused.
    ("BOB SYNTHER", "Bob Synther", "Bob Synther"),
    ("BOB SYNTHER", "Bob Synther", "bob synther"),
    # A reading that writes it twice in different letter case writes no one text either.
    ("Synth, SYNTH Prov.", "Synth, SYNTH Prov.", "synth"),
])
def test_another_text_is_still_refused(first, second, given):
    made = expert("collection_method", two_readers_of(first, second))
    assert refused_by(made, resolved(given, "2A", "2B")) == "literal_not_in_reading"


def test_a_value_a_source_names_is_kept_and_only_a_value_that_was_the_literal_follows_it():
    """The value follows the literal only where it was the literal and names no source candidate the expert
    received: a source's spelling is the source's (here GBIF's candidate "Aus bus", the value the decided
    candidate needs)."""
    label = "SYNTHETIC MUSEUM\nAUS BUS\ndet. J. Synther"
    decided = gbif("Aus bus", "Aus bus", "gbif:7")
    checked = expert("taxon", two_readers_of(label, label), decided).validate(
        resolved("Aus bus", "2A", "2B", value="Aus bus", authority_id="gbif:7", source_evidence_ids=["ev-gbif:7"]))
    assert (checked.literal, checked.value) == ("AUS BUS", "Aus bus")


# ---- the taxon's query check ----------------------------------------------------------------------------------

ONE_LINE = "SYNTHETIC MUSEUM\nAUS BUS L., 1758\nDET. J. SYNTHER 1949"
AUS_BUS = gbif("Aus bus", "Aus bus Linnaeus, 1758", "gbif:7")
AUS = gbif("Aus", "Aus Linnaeus, 1758", "gbif:8")


def test_a_one_line_name_in_capitals_resolves_on_gbifs_answer_for_the_name_given():
    """The parser reads no name in "AUS BUS", so on origin/main no query grounds it (taxon_queries is empty) and the
    answer "Aus bus" is refused before that (literal_not_in_reading). The literal is now the label's "AUS BUS", the
    value GBIF's decided candidate."""
    checked = expert("taxon", two_readers_of(ONE_LINE, ONE_LINE), AUS_BUS, AUS).validate(
        resolved("Aus bus", "2A", "2B", value="Aus bus Linnaeus, 1758", authority_id="gbif:7",
            source_evidence_ids=["ev-gbif:7"]))
    assert (checked.literal, checked.value, checked.authority_id) == ("AUS BUS", "Aus bus Linnaeus, 1758", "gbif:7")


@pytest.mark.parametrize(("label", "given", "found"), [
    # The genus alone of a name in capitals, on its line or over two: never the whole name.
    (ONE_LINE, "Aus", AUS),
    ("SYNTHETIC MUSEUM\nAUS\nBUS\nL., 1758", "Aus", AUS),
    # A species where the label writes a subspecies after it.
    ("SYNTHETIC MUSEUM\nAUS BUS CUS\n(L., 1758)", "Aus bus", AUS_BUS),
])
def test_a_piece_of_a_name_in_capitals_is_still_refused(label, given, found):
    made = expert("taxon", two_readers_of(label, label), found)
    decided = found.candidates[0]
    assert refused_by(made, resolved(given, "2A", "2B", value=decided.name, authority_id=decided.authority_id,
        source_evidence_ids=[found.evidence.id])) == "taxon_query_not_whole_name"
    assert not experts.whole_as_given(made.readings, given.upper(), given)


def test_the_name_given_exactly_keeps_origin_mains_check():
    """Where the readings write the literal as given, only the label's own name grounds a query, as on origin/main:
    "AUS" given as the readers write it is refused on GBIF's answer for "Aus"."""
    made = expert("taxon", two_readers_of(ONE_LINE, ONE_LINE), AUS)
    assert refused_by(made, resolved("AUS", "2A", "2B", value="Aus Linnaeus, 1758", authority_id="gbif:8",
        source_evidence_ids=["ev-gbif:8"])) == "taxon_query_not_whole_name"


def test_a_name_over_two_lines_stays_refused_now_as_no_candidate():
    """1d84dd11 and 36b7d593: "Delostichus coxalis" given for "DELOSTICHUS" over "COXALIS" (here "AUS" over "BUS").
    Read as the readers write it, the literal holds their line break, and a taxon's literal is one line of each
    reading or a whole organiser candidate (agreement.literal_refusal, unchanged): refused by not_candidate where
    origin/main refused it by literal_not_in_reading."""
    label = "SYNTHETIC MUSEUM\nAUS\nBUS\n(L., 1758)"
    made = expert("taxon", two_readers_of(label, label), AUS_BUS)
    assert refused_by(made, resolved("Aus bus", "2A", "2B", value="Aus bus Linnaeus, 1758", authority_id="gbif:7",
        source_evidence_ids=["ev-gbif:7"])) == "not_candidate"


# ---- through the resolver and the step -----------------------------------------------------------------------

CAPITALS = TEXT.replace("leg. J. Smith", "leg. J. SMITH")
CANDIDATES = [("collectors", name, "J. SMITH", "leg. J. SMITH") for name in ("1A", "1B")]


def answering_model(literal):
    """A model that answers `literal` from both readers every time it is asked."""
    def respond(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"outcome": "resolved",
            "literal": literal, "reading_names": ["1A", "1B"], "explanation": "Both readers write it."})])
    return FunctionModel(respond)


class Collectors(Scripted):
    """The collectors' real expert (make_resolver, on a model that answers `literal`); every other field scripted."""

    def __init__(self, literal):
        super().__init__()
        self.expert = experts.make_resolver(model_factory=lambda: answering_model(literal),
            meter=budget.CostMeter(10_000_000, input_micros_per_million=200_000, output_micros_per_million=600_000))

    async def __call__(self, task, readings, context, *, tools):
        if task.key == "collectors":
            return await self.expert(task, readings, context, tools=tools)
        return await super().__call__(task, readings, context, tools=tools)


def settled_collectors(tmp_path, given):
    rig = build_rig(tmp_path, CAPITALS, CAPITALS, candidates=CANDIDATES)
    settle(rig, Collectors(given))
    return rig, rig.specimen.run.fields["collectors"]


def test_the_readers_text_settles_through_the_resolver_and_the_step(tmp_path):
    """The expert answers "J. Smith" where both readers write "J. SMITH": the Collectors settle exactly as for the
    answer "J. SMITH" (state, literal, layers, the rows they cite), passing the field checks and the evidence
    check. On origin/main every answer "J. Smith" is refused (literal_not_in_reading) and the field is
    unresolved."""
    rig, value = settled_collectors(tmp_path / "recased", "J. Smith")
    exact_rig, exact = settled_collectors(tmp_path / "exact", "J. SMITH")
    assert (value.state, value.literal) == (ValueState.SUPPORTED, "J. SMITH")

    def shown(rig, value):
        rows = {row.id: row for row in rig.specimen.run.evidence}
        return (value.state, value.literal, value.parsed, value.normalized, value.layer, value.reason,
            sorted((rows[i].kind, rows[i].source, rows[i].excerpt) for i in value.evidence_ids))

    assert shown(rig, value) == shown(exact_rig, exact)
    assert field_checks(rig.specimen.run, {"collectors"}) == []
    verify_evidence(rig.specimen, rig.blobs)


def test_another_text_stays_unresolved_through_the_resolver_and_the_step(tmp_path):
    """A letter more ("J. Smiths"): every answer is refused by the same check, as on origin/main."""
    _, value = settled_collectors(tmp_path, "J. Smiths")
    assert value.state == ValueState.UNRESOLVED
    assert value.reason.endswith("Refused answers: 'J. Smiths' by literal_not_in_reading; 'J. Smiths' by "
        "literal_not_in_reading; 'J. Smiths' by literal_not_in_reading.")


def test_an_answer_the_readings_hold_as_given_is_never_read_again():
    """Where every reading named holds the literal as given, the answer stands as given, even where a reading also
    writes it in another letter case."""
    label = "Synthetic Museum\nBob Synther\nBOB SYNTHER"
    checked = expert("collectors", two_readers_of(label, label)).validate(resolved("Bob Synther", "2A", "2B"))
    assert checked.literal == "Bob Synther"


def test_a_name_in_capitals_the_check_takes_settles_and_its_record_keeps_taxonomy_unresolved(tmp_path):
    """The stated limit: a taxon the expert's check takes on the name as given ("Danaus plexippus" where both readers
    write "DANAUS PLEXIPPUS") settles through the step, the label's text its literal and GBIF's decided candidate
    its value, and its record keeps the reason taxonomy_unresolved: the step's check of the settling query at
    finalize (step.taxon_decided, checks.taxon_query_grounded on the literal) is origin/main's and reads no name in
    capitals. The flag stays."""
    capitals = TEXT.replace("taxon: Danaus plexippus", "taxon: DANAUS PLEXIPPUS")
    rig = build_rig(tmp_path, capitals, capitals)

    async def script(task, readings, tools):
        found = await tools.lookup("gbif", "Danaus plexippus", field_key="taxon")
        made = experts._Expert(task, readings, tools, None)
        made.calls.append(experts._Call("gbif", found.query, found.status, found))
        checked = made.validate(resolved("Danaus plexippus", "1A", "1B", value=GBIF_NAME, authority_id=GBIF_KEY,
            source_evidence_ids=[found.evidence.id]))
        assert checked.literal == "DANAUS PLEXIPPUS"
        return FieldOutcome("taxon", checked, evidence=[found.evidence], lookups=[found.taxonomy_lookup],
            model_calls=1)

    settle(rig, Scripted({"taxon": script}))
    run = rig.specimen.run
    value = run.fields["taxon"]
    assert (value.state, value.literal, value.normalized) == (ValueState.SUPPORTED, "DANAUS PLEXIPPUS", GBIF_NAME)
    assert "taxonomy_unresolved" in [*run.reasons, *run.open_reasons]
