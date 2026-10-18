"""The two location gaps PR #377 left open (the third rerun of 2026-10-18).

- 3781e440 (one label, Coles Co., Illinois): reader 2B writes "USA: Ill. Coles
  Co.", reader 2A "U.S.B.I.L.: Coles Co.,". "USA" and "Ill." are one reader's
  abbreviations, and a label whose readers differ settles a text only when an
  answer confirms it, which `agreement.identities` read as a candidate of the
  text's own name. Wikidata's answer for "United States of America" (and for
  "Illinois") now confirms it, as `agreement.place_settling` already settles
  an abbreviation on its expansion; and a country no answer settled no
  longer holds back a place inside the one nation its texts are confirmed as
  (`agreement.confirmed_place`), which then derives the country.
- d10333ff (Edgar County, Illinois): label 3, a determination label, has no
  decided transcript (its first pass reached its token cap in one run and
  chose no reading in the next two). Reader 3A writes "Panama" where 3B
  writes "Panorpa", 3B's taxon. That disputed text, and the decided label's
  other reader's "BONITELL", no longer hold back the country the settled
  Illinois and Edgar County derive (`agreement.set_aside`,
  `step._country_alternatives_are_lower_places`).

The answers are made up in the shape the run graphs of 2026-10-18 store them
(each candidate's name, record, kind and parents, as their evidence excerpts
list them), not recorded responses.
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import test_step
from PIL import Image
from test_location_level_roles import NO_PLACE_LINES, Stored, expert, settled_on, several
from test_step import (
    COLLECTORS,
    LACKS,
    TEXT,
    Scripted,
    answering,
    build_rig,
    label_with,
    research,
    settle,
    worker_principal,
)

from specimen_digitization.application.domain import (
    Evidence, FieldValue, LookupStatus, Observation, Region, ValueState,
)
from specimen_digitization.application.harness import ExtractionCandidate, ExtractionOutput, apply_candidates
from specimen_digitization.application.region_pixels import region_png
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
from specimen_digitization.application.workflow import SyntheticAdapters, Workflow
from specimen_digitization.field_research import agreement, experts
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import (
    Candidate, FieldAnswer, FieldOutcome, FieldTask, Reading, SourceAnswer,
)
from specimen_digitization.field_research.step import apply_outcomes

US = ("United States", "wikidata:Q30", None)
IL = ("Illinois", "wikidata:Q1204", None)
NATION = "sovereign state, country, superpower"
# As the run graphs of 2026-10-18 store Wikidata's answers (3781e440's run
# 1078c504, d10333ff's runs a75b4e51, 1427d6ba and 8a91d868).
ANSWERS = {
    ("wikidata", "USA"): [
        ("United States", "wikidata:Q30", NATION, (US,), "US"),
        ("USA Network", "wikidata:Q248713", "cable channel", (US,), None),
        ("United States Army", "wikidata:Q9212", "army", (US,), None),
        ("USA", "wikidata:Q2195271", "album", (), None),
        ("Usa", "wikidata:Q6476962", "river", (("Minsk region", None, None), ("Belarus", None, None)), None)],
    ("wikidata", "United States of America"): [
        ("United States", "wikidata:Q30", NATION, (US,), "US"),
        ("United States of America", "wikidata:Q105870683", "music track with vocals", (), None),
        ("United States of America", "wikidata:Q99281400",
            "real country in a fiction work, location in a fictional work", (), None),
        ("American Red Cross", "wikidata:Q470110", "organization", (US,), None)],
    ("wikidata", "Illinois"): [
        ("Illinois", "wikidata:Q1204", "U.S. state", (US,), None),
        ("Illinois", "wikidata:Q1658831", "album", (), None),
        ("Illinois State University", "wikidata:Q558922", "university", (("Normal", None, None), US), None),
        ("township of Illinois", "wikidata:Q17198545", None, (US,), None)],
    ("wikidata", "Coles County"): [
        ("Coles County", "wikidata:Q112137", "county of Illinois, second-level administrative division",
            (IL, US), None),
        ("Coles County Memorial Airport", "wikidata:Q1654299", "airport", (IL, US), None)],
    ("wikidata", "Edgar County"): [
        ("Edgar County", "wikidata:Q484124", "county of Illinois, second-level administrative division",
            (IL, US), None),
        ("Edgar County Airport", "wikidata:Q5337188", "airport", (IL, US), None)],
    ("wikidata", "Panama"): [
        ("Panama", "wikidata:Q804", "sovereign state, republic, country", (("Panama", "wikidata:Q804", None),),
            "PA"),
        ("Panama City", "wikidata:Q3306", "city, metropolitan area, big city",
            (("Panamá District", None, None), ("Panama", None, None)), None),
        ("Panama", "wikidata:Q94016605", "music track with vocals", (), None)],
    ("wikidata", "Canada"): [
        ("Canada", "wikidata:Q16", "sovereign state, country", (("Canada", "wikidata:Q16", None),), "CA")],
}


class Answers(Stored):
    """ANSWERS (and Stored's), and a no_match answer for each name in `missing`."""

    def __init__(self, blobs, extra=None, *, missing=("U.S.B.I.L.",)):
        super().__init__(blobs, {**ANSWERS, **(extra or {})})
        self.missing = set(missing)

    def _answer(self, source_id, query):
        if query.split(",")[0].strip() not in self.missing:
            return super()._answer(source_id, query)
        raw = json.dumps({"source": source_id, "query": query}).encode()
        evidence = Evidence(kind="lookup", source=source_id, locator=None, excerpt="no match",
            raw_ref=self.blobs.put(raw), digest=hashlib.sha256(raw).hexdigest())
        return SourceAnswer(source_id, query, LookupStatus.NO_MATCH, (), evidence, note="no match")


def answers(tmp_path, *queries):
    tools = Answers(LocalBlobs(tmp_path / "answers"))
    return [tools._answer(source, query) for source, query in queries]


# ---- an abbreviation confirmed through its expansion ------------------------

def test_an_abbreviation_is_confirmed_by_the_answer_asked_its_expansion(tmp_path):
    """3781e440's "USA" and "Ill.": Wikidata's answers for "United States of
    America" and "Illinois" each hold one candidate at the field's level,
    the place the letters spell. On d5a6502d neither confirms anything, as
    neither candidate has the label's own name."""
    usa, expanded, illinois = answers(tmp_path, ("wikidata", "USA"), ("wikidata", "United States of America"),
        ("wikidata", "Illinois, United States"))
    assert agreement.identities([expanded], "USA", "country") == {"wikidata:Q30"}
    assert agreement.identities([illinois], "Ill.", "province_state") == {"wikidata:Q1204"}
    # The label's own text asked: its one nation is not of its name, so it confirms nothing.
    assert agreement.identities([usa], "USA", "country") == set()
    # A name the letters do not spell ("Iowa" for "Ill."), or a field whose level
    # the expansion's answer holds nothing at, confirms nothing.
    assert agreement.identities([expanded], "USA", "province_state") == set()
    assert agreement.identities([illinois], "Ia.", "province_state") == set()
    # A text written out in full is no abbreviation of a longer name.
    assert agreement.identities([illinois], "Illi", "province_state") == set()


def test_an_expansion_whose_answer_holds_two_places_at_the_level_confirms_nothing(tmp_path):
    tools = Answers(LocalBlobs(tmp_path / "answers"), {("wikidata", "United States of America"): [
        ("United States", "wikidata:Q30", NATION, (US,), "US"),
        ("Confederate States of America", "wikidata:Q81931", "country", (), None)]})
    assert agreement.identities([tools._answer("wikidata", "United States of America")], "USA", "country") == set()


def test_one_readers_abbreviation_settles_its_label_through_its_expansion(tmp_path):
    """3781e440's province: only 2B writes "Ill." (2A reads the line as
    "U.S.B.I.L.:", which no source found). Its expert's answer cited
    Wikidata's answer for "Illinois" and was refused DIFFER on d5a6502d."""
    readings = (Reading("2A", "label2", "obs2a", "raw_reading", "U.S.B.I.L.: Coles Co.,\nKankakee State Park"),
        Reading("2B", "label2", "obs2b", "raw_reading", "USA: Ill. Coles Co.\nFox Ridge State Park"))
    illinois, nothing = answers(tmp_path, ("wikidata", "Illinois, United States"), ("wikidata", "U.S.B.I.L."))
    task = FieldTask("province_state", False, FieldValue(), (Candidate("2B", "USA: Ill. Coles Co.", "Ill.", "row-2b"),),
        ("geolocate", "tgn", "wikidata", "nga"))
    common = dict(literal="Ill.", named=[readings[1]], value="Illinois", authority_id="wikidata:Q1204",
        received=[illinois, nothing])
    assert agreement.refusal(task, readings, cited=[illinois], **common) is None
    # Citing only an answer that is not about the text or its expansion still refuses.
    refused = agreement.refusal(task, readings, cited=[nothing], **common)
    assert refused is not None and refused.reason == agreement.DIFFER
    assert "answer asked its expansion" in refused.retry
    # The country "USA": citing the lookup of "USA" itself (its one nation is
    # "United States", not of the text's name) is sent back to cite the
    # answer asked "United States of America", which settles it.
    usa, expanded = answers(tmp_path, ("wikidata", "USA"), ("wikidata", "United States of America"))
    country = FieldTask("country", False, FieldValue(), (Candidate("2B", "USA: Ill. Coles Co.", "USA", "row-2b"),),
        ("tgn", "wikidata", "nga"))
    common = dict(literal="USA", named=[readings[1]], value="United States", authority_id="wikidata:Q30",
        received=[usa, expanded, nothing])
    refused = agreement.refusal(country, readings, cited=[usa], **common)
    assert refused is not None and refused.reason == agreement.DIFFER
    assert "answer asked its expansion" in refused.retry
    assert agreement.refusal(country, readings, cited=[expanded], **common) is None


# ---- the nation every country text is confirmed as ---------------------------

def test_the_record_s_country_texts_confirmed_as_one_nation(tmp_path):
    usa, expanded, canada = answers(tmp_path, ("wikidata", "USA"), ("wikidata", "United States of America"),
        ("wikidata", "Canada"))
    found = agreement.confirmed_place([usa, expanded], ["USA"], "country")
    assert found == agreement.PlaceField(("United States",), "wikidata:Q30", "US")
    # Two texts confirmed as different nations, a text no answer confirms, or no text.
    assert agreement.confirmed_place([usa, expanded, canada], ["USA", "Canada"], "country") is None
    assert agreement.confirmed_place([usa], ["USA"], "country") is None
    assert agreement.confirmed_place([usa, expanded], ["USA", "U.S.B.I.L."], "country") is None
    assert agreement.confirmed_place([usa, expanded], [], "country") is None
    # The label's own text placed at another nation than its expansion is.
    elsewhere = Answers(LocalBlobs(tmp_path / "elsewhere"), {("wikidata", "USA"): [
        ("Uganda", "wikidata:Q1036", NATION, (), "UG")]})._answer("wikidata", "USA")
    assert agreement.confirmed_place([elsewhere, expanded], ["USA"], "country") is None


# 3781e440's label: the two readers' lines, the rest as test_step's label.
COLES = label_with(**NO_PLACE_LINES) + "\nUSA: Ill. Coles Co.\nFox Ridge State Park"
COLES_B = label_with(**NO_PLACE_LINES) + "\nU.S.B.I.L.: Coles Co.,\nKankakee State Park"
COLES_CANDIDATES = [*COLLECTORS, ("country", "1A", "USA", "USA: Ill. Coles Co."),
    ("province_state", "1A", "Ill.", "USA: Ill. Coles Co."), ("county", "1A", "Coles Co.", "USA: Ill. Coles Co.")]
COUNTRY_LOOKUPS = (("wikidata", "USA"), ("wikidata", "United States of America"), ("wikidata", "U.S.B.I.L."))
STATE = expert(("wikidata", "Illinois, United States"), ("wikidata", "U.S.B.I.L."),
    answer=settled_on("Ill.", "Illinois", "wikidata:Q1204"))
COUNTY = expert(("wikidata", "Coles County, Illinois, United States"),
    answer=settled_on("Coles Co.", "Coles County", "wikidata:Q112137"))


def fallback(*queries):
    """The resolver's fallback after its lookups: no answer of the expert's passed its check."""
    async def script(task, readings, tools):
        found = [await tools.lookup(source, query, field_key=task.key) for source, query in queries]
        return FieldOutcome(task.key, FieldAnswer(outcome="sources_cannot_resolve", explanation=experts.UNCHECKED),
            evidence=[item.evidence for item in found if item.evidence], model_calls=3, fallback=True)
    return script


def coles(tmp_path, other=COLES_B, candidates=COLES_CANDIDATES, *, country):
    rig = build_rig(tmp_path, COLES, other, candidates=candidates)
    run = rig.specimen.run
    assert [r.input_source for r in field_step.run_readings(run)] == ["raw_reading", "raw_reading"]
    decisions: dict[str, dict] = {}
    prepared, outcomes, calls = research(rig, Scripted({"country": country, "province_state": STATE,
        "county": COUNTY, "city": answering(LACKS), "precise_location": answering(LACKS)}),
        tools=Answers(rig.blobs))
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    return run, decisions


@pytest.mark.parametrize("country", ["fallback", "cites-the-expansion"])
def test_one_readers_usa_and_ill_settle_the_state_county_and_country(tmp_path, country):
    """3781e440 on 2026-10-18 (run 1078c504): no answer of the country's
    expert cited Wikidata's answer for "United States of America" (only its
    answer for "USA" itself and the no-match answers for "U.S.B.I.L."), each
    was refused, and the country fell back; the state's "Ill." was refused DIFFER and its expert
    ended ambiguous; the county was refused NO_COUNTRY. Now the state and the
    county settle, and the country is derived from them (or, when the
    expert cites the answer for "United States of America", settles on the
    initials, corroborated by the county). On d5a6502d the state is
    ambiguous, the county unresolved (no_country) and the country
    unresolved."""
    script = (fallback(*COUNTRY_LOOKUPS) if country == "fallback"
        else expert(*COUNTRY_LOOKUPS, answer=settled_on("USA", "United States", "wikidata:Q30", cite=1)))
    run, decisions = coles(tmp_path, country=script)
    state, county, nation = (run.fields[key] for key in ("province_state", "county", "country"))
    assert (state.state, state.literal, state.normalized, state.authority_id) == (
        ValueState.SUPPORTED, "Ill.", "Illinois", "wikidata:Q1204")
    assert (county.state, county.literal, county.normalized, county.authority_id) == (
        ValueState.SUPPORTED, "Coles Co.", "Coles County", "wikidata:Q112137")
    assert nation.state == ValueState.SUPPORTED
    if country == "fallback":
        assert (nation.layer, nation.parsed, decisions["country"]) == ("derived", "United States", {"rule": "derived"})
    else:
        assert (nation.layer, nation.literal, nation.normalized, nation.authority_id) == (
            "settled", "USA", "United States", "wikidata:Q30")
    assert not decisions.get("county", {}).get("refusal")


def test_a_second_country_text_on_the_label_keeps_the_places_below_it_for_review(tmp_path):
    """The same label where the other reader writes "Canada" for the country,
    which Wikidata confirms as Canada: the country texts are two nations, so
    neither the state nor the county settles without a country (NO_COUNTRY),
    and nothing derives the country."""
    other = COLES_B.replace("U.S.B.I.L.: Coles Co.,", "Canada: Ill. Coles Co.")
    candidates = [*COLES_CANDIDATES, ("country", "1B", "Canada", "Canada: Ill. Coles Co."),
        ("province_state", "1B", "Ill.", "Canada: Ill. Coles Co."),
        ("county", "1B", "Coles Co.", "Canada: Ill. Coles Co.")]
    run, decisions = coles(tmp_path, other, candidates, country=fallback(*COUNTRY_LOOKUPS, ("wikidata", "Canada")))
    assert run.fields["province_state"].state == ValueState.UNRESOLVED
    assert decisions["province_state"]["refusal"] == "no_country"
    assert run.fields["county"].state == ValueState.UNRESOLVED
    assert decisions["county"]["refusal"] == "no_country"
    assert run.fields["country"].state == ValueState.UNRESOLVED and run.fields["country"].layer is None


# ---- text that stands on no settling reading ---------------------------------

LABEL_3A = "Panama\n30. IA\n1. octubre del 2021"
LABEL_3B = "Panorpa\nsp. ?\n[unreadable] det. 2021"
DECIDED_1A = "ILLINOIS\nEdgar county\n4mi SSE Kansas"
RAW_1B = "BONITELL\nEdgar County\n4mi SSE Kansas"


def d10333ff_readings(second=LABEL_3B):
    return (Reading("1A", "label1", "obs1a", "decided_transcript", DECIDED_1A),
        Reading("1B", "label1", "obs1b", "raw_reading", RAW_1B),
        Reading("3A", "label3", "obs3a", "raw_reading", LABEL_3A),
        Reading("3B", "label3", "obs3b", "raw_reading", second))


def test_a_decided_labels_other_reader_writes_its_own_text_only_as_evidence():
    """G19: d10333ff's label 1 decided on 1A; 1B's "BONITELL" is evidence only."""
    readings = d10333ff_readings()
    assert agreement.evidence_only("BONITELL", readings[1], readings)
    assert not agreement.evidence_only("ILLINOIS", readings[0], readings)
    # Text both readers of the decided label write is the label's.
    assert not agreement.evidence_only("Edgar", readings[1], readings)
    assert not agreement.evidence_only("Panama", readings[2], readings)


def test_text_the_other_reader_reads_as_another_fields_is_disputed():
    """d10333ff's label 3: 3A writes "Panama" where 3B writes "Panorpa", 3B's
    taxon."""
    readings = d10333ff_readings()
    taxon = {"3B": {"Panorpa"}}
    assert agreement.disputed("Panama", readings[2], readings, taxon)
    assert agreement.set_aside("Panama", readings, taxon)
    assert agreement.set_aside("BONITELL", readings, taxon)
    # The decided label's own text, and any text on a decided label, is no dispute.
    assert not agreement.set_aside("ILLINOIS", readings, taxon)
    assert not agreement.disputed("ILLINOIS", readings[0], readings, taxon)


@pytest.mark.parametrize("second", [
    # The other reader writes the text too, at that point or elsewhere.
    "Panama\nsp. ?\n[unreadable] det. 2021",
    "Panorpa\nsp. ? Panama\n[unreadable] det. 2021",
    # Its words there are the text with accents aside, or one letter off.
    "Panamá\nsp. ?\n[unreadable] det. 2021",
    "Panamo\nsp. ?\n[unreadable] det. 2021",
    # It leaves the line out: it reads nothing else there.
    "sp. ?\n[unreadable] det. 2021",
], ids=["also-writes-it", "writes-it-elsewhere", "accented", "one-letter-off", "leaves-it-out"])
def test_text_the_other_reader_does_not_read_as_other_words_is_no_dispute(second):
    readings = d10333ff_readings(second)
    claimed = {"3B": {"Panorpa", "Panamá", "Panamo", "Panama"}}
    assert not agreement.disputed("Panama", readings[2], readings, claimed)
    assert not agreement.set_aside("Panama", readings, claimed)


def test_other_words_no_field_holds_are_no_dispute():
    """Two readers' spellings of one name may differ by more than a letter:
    unless the other reader's words there are another field's text, the
    text stays its label's country."""
    readings = d10333ff_readings()
    assert not agreement.disputed("Panama", readings[2], readings, {})
    # Another reader's field text, or one that holds the words only inside a word.
    assert not agreement.disputed("Panama", readings[2], readings, {"3A": {"Panorpa"}})
    assert not agreement.set_aside("Panama", readings, {"3B": {"Panorpas"}})
    # A field text that holds them as whole words is enough: the taxon "Panorpa sp. ?".
    assert agreement.set_aside("Panama", readings, {"3B": {"Panorpa sp. ?"}})


def two_label_rig(tmp_path, *, first, second, candidates):
    """build_rig's run with two labels: label 1's readers write `first` (two
    texts; the first pass decided 1A's), label 2's write `second` (two
    texts, whose first pass chose no reading, as one reaching its token cap
    does: no decided transcript)."""
    original = test_step.make_specimen

    def make(blobs, text=TEXT, other=None, *, first_pass=True):
        specimen = original(blobs, *first, first_pass=first_pass)
        run = specimen.run
        output = io.BytesIO()
        Image.new("RGB", (100, 100), "white").save(output, format="JPEG", quality=95)
        region = Region(asset_id=specimen.asset.id, x=0, y=50, width=100, height=50, order=1,
            method="synthetic_fixture_region", version="1")
        crop_png = region_png(Image.open(io.BytesIO(output.getvalue())), region)
        region.crop_ref = blobs.put(crop_png)
        run.regions.append(region)
        crop = hashlib.sha256(crop_png).hexdigest()
        for route, written in zip(run.profile.routes, second, strict=True):
            raw = ("SYNTHETIC FIXTURE " + route + "\n" + written).encode()
            run.observations.append(Observation(region_id=region.id, route_id=route, model_id="synthetic-" + route,
                provider="synthetic", prompt_version="prompt:" + route, input_sha256=crop,
                input_asset_id=specimen.asset.id, input_crop_ref=region.crop_ref, literal_text=written,
                raw_ref=blobs.put(raw), raw_sha256=hashlib.sha256(raw).hexdigest()))
            run.completed_steps.append(f"transcribe:{region.id}:{route}")
        if len(set(second)) > 1:
            run.completed_steps.append(f"first_pass:{region.id}")
        return specimen

    blobs = LocalBlobs(tmp_path / "blobs")
    repository = SQLiteRepository(tmp_path / "records.sqlite")
    clock = SimpleNamespace(now=datetime(2026, 10, 18, 5, tzinfo=timezone.utc))
    workflow = Workflow(repository, blobs, SyntheticAdapters(blobs, TEXT), clock=lambda: clock.now)
    principal = worker_principal()
    created = repository.create(principal, make(blobs), "intake", "intake")
    adjudicated = workflow.step(principal, created.id)  # adjudicate
    run = adjudicated.run
    [transcript] = [t for t in run.transcripts if t.region_id == run.regions[0].id]
    chosen = next(o for o in run.observations if o.region_id == run.regions[0].id)
    transcript.text, transcript.resolved, transcript.selected_observation_id = chosen.literal_text, True, chosen.id
    repository.save(principal, adjudicated, adjudicated.version, "first-pass", "first-pass")
    parsed = workflow.step(principal, created.id)  # parse
    assert workflow.next_step(parsed.run) == "plan"
    raw = b"organiser response"
    apply_candidates(parsed.run, parsed.asset.id, ExtractionOutput(candidates=[
        ExtractionCandidate(field_key=key, reading=name, literal=literal, source_excerpt=quote)
        for key, name, literal, quote in candidates]), blobs.put(raw), hashlib.sha256(raw).hexdigest())
    parsed = repository.save(principal, parsed, parsed.version, "organiser", "organiser")
    return SimpleNamespace(blobs=blobs, repository=repository, workflow=workflow, principal=principal,
        specimen=parsed, clock=clock)


EDGAR_1A = label_with(**NO_PLACE_LINES) + "\n" + DECIDED_1A
EDGAR_1B = label_with(**NO_PLACE_LINES) + "\n" + RAW_1B
EDGAR_CANDIDATES = [*COLLECTORS, ("country", "1A", "ILLINOIS", "ILLINOIS"), ("country", "1B", "BONITELL", "BONITELL"),
    ("country", "2A", "Panama", "Panama"), ("province_state", "1A", "ILLINOIS", "ILLINOIS"),
    ("county", "1A", "Edgar county", "Edgar county")]
TAXON_2B = ("taxon", "2B", "Panorpa", "Panorpa")
EDGAR_EXPERTS = {
    "country": expert(("wikidata", "Illinois"), ("wikidata", "Panama"), answer=several("ILLINOIS", "Panama")),
    "province_state": expert(("wikidata", "Illinois"), answer=settled_on("ILLINOIS", "Illinois", "wikidata:Q1204")),
    "county": expert(("wikidata", "Edgar County, Illinois, United States"),
        answer=settled_on("Edgar county", "Edgar County", "wikidata:Q484124")),
    "city": answering(LACKS), "precise_location": answering(LACKS), "taxon": answering(LACKS)}


def edgar(tmp_path, second=(LABEL_3A, LABEL_3B), candidates=(*EDGAR_CANDIDATES, TAXON_2B)):
    rig = two_label_rig(tmp_path, first=(EDGAR_1A, EDGAR_1B), second=second,
        candidates=list(candidates))
    run = rig.specimen.run
    readings = field_step.run_readings(run)
    assert [(r.name, r.input_source) for r in readings] == [("1A", "decided_transcript"), ("1B", "raw_reading"),
        ("2A", "raw_reading"), ("2B", "raw_reading")]
    settle(rig, Scripted(EDGAR_EXPERTS), tools=Answers(rig.blobs))
    return run


def test_an_undecided_labels_disputed_country_no_longer_holds_back_the_derived_country(tmp_path):
    """d10333ff on 2026-10-17 and 2026-10-18 (runs a75b4e51, 1427d6ba and
    8a91d868): label 1 settles Illinois and Edgar County; its decided
    reading writes "ILLINOIS" on the country line, its other reader
    "BONITELL"; the determination label, with no decided transcript, has
    2A's "Panama" where 2B writes "Panorpa", 2B's taxon. The country expert
    answered several_possibilities ("ILLINOIS", "Panama"). Now the country
    is derived from the settled places. On d5a6502d it stays ambiguous."""
    run = edgar(tmp_path)
    assert run.fields["province_state"].authority_id == "wikidata:Q1204"
    assert run.fields["county"].authority_id == "wikidata:Q484124"
    nation = run.fields["country"]
    assert (nation.state, nation.layer, nation.parsed) == (ValueState.SUPPORTED, "derived", "United States")
    assert not [reason for reason in run.reasons if reason.endswith(":country")]


@pytest.mark.parametrize(("second", "taxon"), [
    # Both readers of the determination label write "Panama": the label says it.
    (("Panama\n30. IA\n1. octubre del 2021", "Panama\nsp. ?\n[unreadable] det. 2021"), True),
    # 2B's "Panorpa" is no field's text: two readings of one word, not another field's.
    ((LABEL_3A, LABEL_3B), False),
], ids=["both-readers-write-it", "other-words-no-fields"])
def test_a_country_text_its_label_does_not_dispute_still_holds_the_country_for_review(
        tmp_path, second, taxon):
    run = edgar(tmp_path, second, (*EDGAR_CANDIDATES, *((TAXON_2B,) if taxon else ())))
    assert run.fields["county"].authority_id == "wikidata:Q484124"
    assert run.fields["country"].state == ValueState.AMBIGUOUS
