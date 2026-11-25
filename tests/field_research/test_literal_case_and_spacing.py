"""The expert's literal check reads an answer in another letter case or white space as the readings write it (lane C2
of the waiting-fields fix program, 2026-11-25), for every field but the taxon.

The coordinator's ruling for the lane (the coordinator's, the Claude session local_5b5f071c; not the owner's): the
expert's literal check (`literal_not_in_reading`, and the taxon's query check) accepts an answer equal to a reading's
text up to letter case and line breaks or spacing; the settled literal is the reading's own text, never the expert's;
no other comparison changes (agreement keys, rival grouping and the rest of agreement.py stay origin/main's).

The taxon keeps origin/main's check. Three rounds of #474's review found taxon answers that, read as the readers write
them, settle a piece of the name the label writes: the scientific-name parser reads no name in capitals, and the checks
that keep a piece of a name from settling look at no word before a literal that names a genus ("Smithi cus" after
"AUS (XUS)"). The audit's taxon examples ("Delostichus coxalis" where both readers write "DELOSTICHUS" over "COXALIS",
production records 1d84dd11 and 36b7d593; "Bittacus stigmaterus Say" over two lines, a1efc490) would stay unsettled
either way: read as the readers write it, the name holds a line break, and a taxon's literal is one line of a reading
or a whole organiser candidate (agreement.literal_refusal, unchanged).

The label texts here are made up.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from test_first_pass_advice import with_units
from test_step import TEXT, Scripted, build_rig, field_checks, settle

from specimen_digitization.application.domain import Evidence, FieldValue, LookupStatus, ValueState
from specimen_digitization.application.integrity import verify_evidence
from specimen_digitization.field_research import budget, experts
from specimen_digitization.field_research.contracts import (
    Candidate,
    FieldAnswer,
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


def test_a_text_inside_a_word_is_never_found_even_where_an_organiser_candidate_is_that_piece():
    """Round 1 of #474's review, finding 2: both readers write "leg. STARK" and the organiser's candidate is "STAR",
    quoting it. The answer "Star" is not read as the candidate: "STAR" cuts the word "STARK"."""
    label = "Synthetic Museum\nleg. STARK\n10-IV-1975"
    readings = two_readers_of(label, label)
    candidates = tuple(Candidate(name, "leg. STARK", "STAR", f"row-{name}") for name in ("2A", "2B"))
    made = experts._Expert(FieldTask("collectors", False, FieldValue(), candidates, ()), readings,
        SimpleNamespace(sources=()), None)
    assert experts.written_as(readings, "Star") is None
    assert refused_by(made, resolved("Star", "2A", "2B", value="Star")) == "literal_not_in_reading"
    assert experts.written_as(readings, "stark") == "STARK"


def test_a_text_that_ends_in_a_mark_inside_a_word_is_never_found():
    """Round 2 of #474's review, finding 1: both readers write "leg. VAN-DYKE" and the organiser's candidate is
    "VAN-". The answer "Van-" is not read as it: the token "VAN-DYKE" holds "DYKE" after it."""
    label = "Synthetic Museum\nleg. VAN-DYKE\n10-IV-1975"
    readings = two_readers_of(label, label)
    candidates = tuple(Candidate(name, "leg. VAN-DYKE", "VAN-", f"row-{name}") for name in ("2A", "2B"))
    made = experts._Expert(FieldTask("collectors", False, FieldValue(), candidates, ()), readings,
        SimpleNamespace(sources=()), None)
    assert experts.written_as(readings, "Van-") is None
    assert refused_by(made, resolved("Van-", "2A", "2B", value="Van-")) == "literal_not_in_reading"
    # A mark at a token's edge may be left off, as an answer given exactly may leave it off.
    assert experts.written_as(two_readers_of("LOC: YEPOCAPA, 4800FT", "LOC: YEPOCAPA, 4800FT"), "Yepocapa") == "YEPOCAPA"
    assert experts.written_as(two_readers_of("LOC: YEPOCAPA,4800FT", "LOC: YEPOCAPA,4800FT"), "Yepocapa") is None


def test_two_texts_found_at_overlapping_places_are_two_texts():
    """Round 1 of #474's review, finding 3: "a a" in "A A a" is "A A" and, overlapping it, "A a"."""
    readings = two_readers_of("Synthetic A A a", "Synthetic A A a")
    assert experts.written_as(readings, "a a") is None
    assert refused_by(expert("collection_method", readings), resolved("a a", "2A", "2B")) == "literal_not_in_reading"


def test_a_value_a_source_names_is_kept_and_only_a_value_that_was_the_literal_follows_it():
    """The value follows the literal only where it was the literal and names no candidate of a source answer the
    expert received: a source's spelling is the source's."""
    label = "Synthetic Museum\nLOC: SANTIAGO PROV.\n10-IV-1975"
    readings = two_readers_of(label, label)
    place = SourceAnswer("tgn", "Santiago", LookupStatus.SUCCESS, (SourceCandidate("Santiago", "tgn:1", "province"),),
        Evidence(id="ev-tgn-1", kind="authority", source="tgn", locator="tgn:1", excerpt="Santiago | tgn:1 |"),
        note="match")
    made = expert("province_state", readings, place)
    assert made._as_written(resolved("Santiago", "2A", "2B", value="Santiago")).value == "Santiago"
    unsourced = expert("province_state", readings)
    assert (unsourced._as_written(resolved("Santiago", "2A", "2B", value="Santiago")).model_dump(
        include={"literal", "value"}) == {"literal": "SANTIAGO", "value": "SANTIAGO"})
    other = unsourced._as_written(resolved("Santiago", "2A", "2B", value="Santiago Metropolitan"))
    assert (other.literal, other.value) == ("SANTIAGO", "Santiago Metropolitan")


# ---- the collectors' role words ---------------------------------------------------------------------------------

@pytest.mark.parametrize(("label", "given", "settled"), [
    # The marker as the notation spells it is left off the answer first (_without_role), then the name is read.
    ("Synthetic Museum\nleg. J. SYNTHER", "leg. J. Synther", "J. SYNTHER"),
    ("Synthetic Museum\nLEG. J. SYNTHER", "leg. J. Synther", "J. SYNTHER"),
    ("Synthetic Museum\nJ. SYNTHER LEG.", "J. Synther leg.", "J. SYNTHER"),
    # A role word the readers' text would hold in another letter case: never read so.
    ("Synthetic Museum\nLEG. J. SYNTHER", "Leg. J. Synther", None),
    ("Synthetic Museum\nJ. SYNTHER COLL.", "J. Synther Coll", None),
    ("Synthetic Museum\nDET. J. SYNTHER", "det. J. Synther", None),
])
def test_a_collectors_answer_is_read_without_its_role_word(label, given, settled):
    made = expert("collectors", two_readers_of(label, label))
    if settled is None:
        assert refused_by(made, resolved(given, "2A", "2B", value=given)) == "literal_not_in_reading"
        return
    checked = made.validate(resolved(given, "2A", "2B", value=given))
    assert (checked.literal, checked.value) == (settled, settled)


def test_a_place_answer_that_holds_a_date_or_an_elevation_as_given_is_never_read_again():
    """The date parser reads a Roman month only in capitals: read as the readers write it, "SYNTH, iv-24-48" holds no
    date it reads, but the answer as given does, and is refused as on origin/main."""
    from specimen_digitization.field_research import agreement

    label = "Synthetic Museum\nSYNTH, iv-24-48\nleg. J. Synther"
    task = FieldTask("collection_code", False, FieldValue(), (), ())
    assert agreement._holds_another_kind(task, "SYNTH, iv-24-48") is None
    assert agreement._holds_another_kind(task, "SYNTH, IV-24-48") is not None
    made = expert("collection_code", two_readers_of(label, label))
    assert refused_by(made, resolved("SYNTH, IV-24-48", "2A", "2B")) == "literal_not_in_reading"
    for key, given in (("city", "Yepocapa, 4800 ft"), ("precise_location", "Yepocapa, 4800 ft")):
        caps = "Synthetic Museum\nYEPOCAPA, 4800 FT\n10-IV-1975"
        assert refused_by(expert(key, two_readers_of(caps, caps)), resolved(given, "2A", "2B")) == (
            "literal_not_in_reading"), key


# ---- the taxon keeps origin/main's check ------------------------------------------------------------------------

SMITHI_CUS = gbif("Smithi cus", "Smithi cus Synther, 1901", "gbif:9")
AUS_BUS = gbif("Aus bus", "Aus bus Linnaeus, 1758", "gbif:7")


@pytest.mark.parametrize(("label", "given", "found"), [
    # A one-line name in capitals, and the audit's name over two lines.
    ("SYNTHETIC MUSEUM\nRT 6519\nAUS BUS L., 1758", "Aus bus", AUS_BUS),
    ("SYNTHETIC MUSEUM\nAUS\nBUS\n(L., 1758)", "Aus bus", AUS_BUS),
    # Rounds 1 to 3 of #474's review: pieces of a name a re-read would settle.
    ("SYNTHETIC MUSEUM\nAUS Smithi cus", "smithi cus", SMITHI_CUS),
    ("SYNTHETIC MUSEUM\nAUS (XUS)\nSmithi cus", "Smithi  cus", SMITHI_CUS),
    ("SYNTHETIC MUSEUM\nAUS (XUS)\u2640\nSmithi cus", "Smithi  cus", SMITHI_CUS),
    ("SYNTHETIC MUSEUM\nAUS (XUS) male\nSmithi cus", "Smithi\ncus", SMITHI_CUS),
])
def test_a_taxon_in_another_letter_case_or_white_space_is_refused_as_on_origin_main(label, given, found):
    made = expert("taxon", two_readers_of(label, label), found)
    decided = found.candidates[0]
    assert experts.written_as(made.readings, given) is not None
    assert refused_by(made, resolved(given, "2A", "2B", value=decided.name, authority_id=decided.authority_id,
        source_evidence_ids=[found.evidence.id])) == "literal_not_in_reading"


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
