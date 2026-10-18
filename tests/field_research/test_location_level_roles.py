"""A label's place text counts for a place field only at the level its
evidence gives it, and still locates the record (the location shapes the
batch rerun of 2026-10-17 left open: docs/execution/golive/
location-rerun-inventory-2026-10-17.md, "Shapes still open").

- A text the field's gazetteers find only as another kind of place is ruled
  out for the field (agreement.found_only_elsewhere): 48a71d53's and
  cb903c0e's "Mindanao", an island, beside the province "Davao Prov.".
- A county or a city whose every text is the text a settled place above it
  holds names no place of its own (step._only_a_place_above): 93e61763's,
  9cc24b07's, d3fb389f's and f35af3a5's department or province line.
- Initials settle when another place the label writes lies inside them by
  every source record of its name (step._placed_inside): 2b02009d's
  "Mt. Apo" beside "P.I.".

The answers are made up in the shape the run graphs of 2026-10-17 store them
(each candidate's name, record, kind and parents, as their evidence
excerpts list them), not recorded responses.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from test_step import (
    COLLECTORS,
    LACKS,
    Gazetteer,
    Scripted,
    answering,
    build_rig,
    cleared_as_not_on_label,
    label_with,
    reasons_for,
    research,
    settle,
)

from specimen_digitization.application.domain import Evidence, LookupStatus, ValueState
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.field_research import agreement
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import (
    FieldAnswer, FieldOutcome, PlaceRef, SourceAnswer, SourceCandidate,
)
from specimen_digitization.field_research.step import apply_outcomes

PH = ("Philippines", "wikidata:Q928", None)
PH_CODE = ("PH", None, "PH")
# Each answer as the run graphs of 2026-10-17 store it: (name, record, kind,
# parents as (name, record, ISO code), the record's own ISO code).
ANSWERS = {
    ("wikidata", "Philippine Islands"): [
        ("Philippines", "wikidata:Q928", "sovereign state, archipelagic state, country", (PH,), "PH"),
        ("Philippine Islands", "wikidata:Q49695034", "hill", (("Portage County", None, None),
            ("United States", "wikidata:Q30", None)), None)],
    ("wikidata", "Mindanao"): [
        ("Mindanao", "wikidata:Q4294079", "island group of the Philippines", (PH,), None),
        ("Mindanao", "wikidata:Q124873", "island", (PH,), None),
        ("Mindanao", "wikidata:Q77580575", "painting", (), None),
        ("Mindanao River", "wikidata:Q2095415", "river", (PH,), None),
        ("Mindanaona", "wikidata:Q15870487", "taxon", (), None),
        ("Mindanao", "wikidata:Q6863640", "language family", (), None),
        ("Mindanao", "wikidata:Q85785617", "film", (), None)],
    ("nga", "Mindanao"): [
        ("Mindanao", "nga:-2439985", "H.STM", (PH_CODE,), None),
        ("Mindanaw", "nga:-2439982", "P.PPL", (("Cebu", None, None), PH_CODE), None),
        ("Mindanao", "nga:-2439980", "T.ISL", (PH_CODE,), None),
        ("Mindanao", "nga:-1126389", "P.PPL", (("Yoro", None, None), ("HN", None, "HN")), None),
        ("Mindanao", "nga:11794986", "R.ST", (("Laguna", None, None), PH_CODE), None),
        ("Mindanao", "nga:11819532", "R.ST", (("Parañaque", None, None), PH_CODE), None),
        ("Mindanao", "nga:14549918", "A.ADM3", (("Cebu", None, None), PH_CODE), None),
        ("Mindanao", "nga:14734807", "P.PPL", (("Guatemala", None, None), ("GT", None, "GT")), None)],
    ("wikidata", "Davao Province"): [
        ("Davao", "wikidata:Q15095071", "former province of the Philippines, province of the Philippines, "
            "first-level administrative division", (PH,), None)],
    ("wikidata", "Mount Apo"): [
        ("Mount Apo", "wikidata:Q455963", "stratovolcano, dormant volcano, mountain",
            (("Davao Region", None, None), ("Davao del Sur", None, None), PH), None),
        ("Mount Apo", "wikidata:Q105769692", "ship", (), None),
        ("Mount Apoi", "wikidata:Q618843", "mountain", (("Samani", None, None), ("Japan", None, None)), None),
        ("Mount Apo Natural Park", "wikidata:Q1504280", "nature park", (("Davao Region", None, None), PH), None)],
    ("nga", "Mount Apo"): [
        ("Apo Mountain", "nga:-2408936", "T.MT", (("Iloilo", None, None), PH_CODE), None),
        ("Mount Apo", "nga:-2408935", "T.MT", (("Cotabato", None, None), PH_CODE), None),
        ("Mount Apo", "nga:6400675", "T.MT", (("Davao Occidental", None, None), PH_CODE), None),
        ("Mount Apo", "nga:11769188", "R.ST", (("Makati", None, None), PH_CODE), None)],
}


class Stored(Gazetteer):
    """Wikidata and NGA answering, for the name before the first comma, as
    ANSWERS stores them (`extra` adds to or replaces them); anything else as
    test_step's Gazetteer answers it."""

    def __init__(self, blobs, extra=None):
        super().__init__(blobs)
        self.answers = {**ANSWERS, **(extra or {})}

    def _answer(self, source_id, query):
        found = self.answers.get((source_id, query.split(",")[0].strip()))
        if found is None:
            return super()._answer(source_id, query)
        raw = json.dumps({"source": source_id, "query": query}).encode()
        candidates = tuple(SourceCandidate(name, record, kind,
            "in " + ", ".join(parent[0] for parent in parents) if parents else None,
            tuple(PlaceRef(*parent) for parent in parents), iso_code)
            for name, record, kind, parents, iso_code in found)
        evidence = Evidence(kind="authority", source=source_id, locator=None, raw_ref=self.blobs.put(raw),
            digest=hashlib.sha256(raw).hexdigest(), excerpt="\n".join(
                f"{c.name} | {c.authority_id} | {c.kind} | {c.detail or ''}" for c in candidates))
        status = LookupStatus.SUCCESS if len(candidates) == 1 else LookupStatus.AMBIGUOUS
        return SourceAnswer(source_id, query, status, candidates, evidence, note=str(status))


def expert(*queries, answer):
    """A place expert: these lookups ((source, query)), then `answer(the
    answers)`, a FieldAnswer."""
    async def script(task, readings, tools):
        found = [await tools.lookup(source, query, field_key=task.key) for source, query in queries]
        return FieldOutcome(task.key, answer(found), evidence=[item.evidence for item in found if item.evidence],
            model_calls=1)
    return script


def settled_on(literal, value, authority_id, *, cite=0, reading="1A"):
    """A resolved answer citing the `cite`th lookup's evidence."""
    return lambda found: FieldAnswer(outcome="resolved", literal=literal, reading_names=[reading], value=value,
        authority_id=authority_id, source_evidence_ids=[found[cite].evidence.id], explanation="Settled.")


def several(*options):
    return lambda found: FieldAnswer(outcome="several_possibilities", options=list(options),
        source_evidence_ids=[item.evidence.id for item in found if item.evidence], explanation="Two units.")


CANNOT = lambda found: FieldAnswer(outcome="sources_cannot_resolve",  # noqa: E731
    source_evidence_ids=[item.evidence.id for item in found if item.evidence], explanation="No province.")
NO_PLACE_LINES = dict(country=None, province_state=None, county=None, city=None, precise_location=None)
BOTH = ("1A", "1B")


def candidates(*fields):
    """The organiser's candidates ((field, literal, quote)), in both readings."""
    return [*COLLECTORS, *((key, name, literal, quote) for key, literal, quote in fields for name in BOTH)]


# ---- a text found only as another kind of place (shape 2) -----------------

def answers_about(tmp_path, *names):
    tools = Stored(LocalBlobs(tmp_path / "blobs"))
    return [tools._answer(source, f"{name}, Philippines") for source, name in names]


def test_an_island_the_gazetteers_hold_at_no_provinces_level_is_ruled_out_for_the_province(tmp_path):
    """48a71d53's "Mindanao,": Wikidata holds an island, an island group, a
    painting, a language family and a film by that name, NGA an island, a
    stream, streets, towns and a third-level unit; neither a province. The
    towns in Honduras and Guatemala keep it for a city, and nothing it is
    asked keeps it for a country."""
    found = answers_about(tmp_path, ("wikidata", "Mindanao"), ("nga", "Mindanao"))
    assert agreement.found_only_elsewhere(found, "Mindanao,", "province_state")
    assert agreement.found_only_elsewhere(found, "Mindanao,", "county")
    assert agreement.found_only_elsewhere(found, "Mindanao,", "country")
    assert not agreement.found_only_elsewhere(found, "Mindanao,", "city")
    # Never ruled out so on a field that is no place value, nor on a name no answer is about.
    assert not agreement.found_only_elsewhere(found, "Mindanao,", "precise_location")
    assert not agreement.found_only_elsewhere(found, "Davao", "province_state")
    # The province "Davao Prov." is no island: its answer holds it at a province's level.
    davao = answers_about(tmp_path, ("wikidata", "Davao Province"))
    assert not agreement.found_only_elsewhere(davao, "Davao", "province_state")


@pytest.mark.parametrize(("made", "literal"), [
    # A candidate of the name at the field's level.
    ([("Mindanao", "nga:adm1", "A.ADM1", (PH_CODE,), None)], "Mindanao"),
    # One letter from the name there: a near spelling may be the province (G34).
    ([("Mindanau", "nga:adm1", "A.ADM1", (PH_CODE,), None), ("Mindanao", "nga:isl", "T.ISL", (PH_CODE,), None)],
        "Mindanao"),
    # A candidate of the name with no kind: what it is, no one knows.
    ([("Mindanao", "nga:unknown", None, (PH_CODE,), None)], "Mindanao"),
    # No candidate of the name at all.
    ([("Mindanao River", "nga:stm", "H.STM", (PH_CODE,), None)], "Mindanao"),
    # An abbreviation may stand for a name no source was asked ("Ill." for Illinois).
    ([("Ill", "nga:ill", "H.STM", (("FR", None, "FR"),), None)], "Ill."),
], ids=["at-the-level", "one-letter-off", "no-kind", "not-named", "abbreviated"])
def test_a_text_is_ruled_out_only_when_every_answer_finds_it_and_none_at_the_fields_level(tmp_path, made, literal):
    """Beside Wikidata's island and island group of the name, NGA's answer
    in each case keeps the text for a province."""
    name = literal.rstrip(".")
    island = [(name, "wikidata:island", "island", (PH,), None)]
    tools = Stored(LocalBlobs(tmp_path / "blobs"), {("nga", name): made, ("wikidata", name): island})
    found = [tools._answer(source, f"{name}, Philippines") for source in ("wikidata", "nga")]
    assert not agreement.found_only_elsewhere(found, literal, "province_state")
    # Both gazetteers holding it as an island alone rule it out (not for an abbreviation).
    island_too = Stored(LocalBlobs(tmp_path / "other"), {("nga", name): [(name, "nga:isl", "T.ISL", (PH_CODE,), None)],
        ("wikidata", name): island})
    both = [island_too._answer(source, f"{name}, Philippines") for source in ("wikidata", "nga")]
    assert agreement.found_only_elsewhere(both, literal, "province_state") == (literal != "Ill.")


def test_one_gazetteers_list_alone_rules_out_nothing(tmp_path):
    """Wikidata's answer holds at most seven candidates, so its island and
    island group alone may leave out a province of that name: a second
    gazetteer must find the text too."""
    found = answers_about(tmp_path, ("wikidata", "Mindanao"))
    assert not agreement.found_only_elsewhere(found, "Mindanao,", "province_state")


def test_an_answer_that_lists_no_candidate_rules_out_nothing(tmp_path):
    """NGA's "search exceeded feature limit" answer is ambiguous with no
    candidate: what it found is unknown, whatever Wikidata found."""
    tools = Stored(LocalBlobs(tmp_path / "blobs"))
    capped = tools._answer("nga", "Mindanao, Philippines")
    capped = SourceAnswer("nga", capped.query, LookupStatus.AMBIGUOUS, (), capped.evidence, note="capped")
    assert not agreement.found_only_elsewhere([tools._answer("wikidata", "Mindanao, Philippines"), capped],
        "Mindanao", "province_state")


# 48a71d53's label: the organiser filed "Mindanao," as the province and the
# province line "3300, Davao Prov." as the county.
DAVAO_LINES = "E. slope Mt. McKinley\n3300, Davao Prov.\nMindanao,\nPhilippine Islands"
DAVAO = label_with(**NO_PLACE_LINES) + "\n" + DAVAO_LINES
DAVAO_CANDIDATES = candidates(("country", "Philippine Islands", "Philippine Islands"),
    ("province_state", "Mindanao", "Mindanao,"), ("county", "Davao Prov.", "3300, Davao Prov."))
PROVINCE_LOOKUPS = (("wikidata", "Mindanao, Philippines"), ("nga", "Mindanao, Philippines"),
    ("wikidata", "Davao Province, Philippines"))
COUNTRY = expert(("wikidata", "Philippine Islands"),
    answer=settled_on("Philippine Islands", "Philippines", "wikidata:Q928"))


@pytest.mark.parametrize("decided", [True, False], ids=["decided-transcript", "no-reading-decided"])
def test_the_province_settles_beside_an_island_its_sources_hold_at_no_provinces_level(tmp_path, decided):
    """48a71d53 on 2026-10-17 (its label's decided transcript is 2A's; or,
    here, its readers differ on the collector and no reading is decided):
    the province's expert settled "Davao Prov." on
    Wikidata's former province of Davao and was refused, as the readers'
    other text "Mindanao," was found (as an island) rather than by none, so
    it answered several_possibilities and the province went to review. Now
    "Mindanao," is ruled out for the province, which settles, and the county,
    whose only text is the province's, is not on the label. On c38f4fd4 the
    province is ambiguous (DIFFER) and the county ambiguous too."""
    rig = (build_rig(tmp_path, DAVAO, candidates=DAVAO_CANDIDATES, decided=True) if decided
        else build_rig(tmp_path, DAVAO, DAVAO.replace("J. Smith", "J. Smlth"), candidates=DAVAO_CANDIDATES))
    run = rig.specimen.run
    assert [r.input_source for r in field_step.run_readings(run)] == (
        ["decided_transcript", "raw_reading"] if decided else ["raw_reading", "raw_reading"])
    settle(rig, Scripted({"country": COUNTRY,
        "province_state": expert(*PROVINCE_LOOKUPS, answer=settled_on("Davao Prov.", "Davao",
            "wikidata:Q15095071", cite=2)),
        "county": expert(("wikidata", "Davao Province, Philippines"), answer=several("Davao Prov.", "Davao")),
        "city": answering(LACKS), "precise_location": answering(LACKS)}), tools=Stored(rig.blobs))
    province = run.fields["province_state"]
    assert (province.state, province.literal, province.normalized, province.authority_id) == (
        ValueState.SUPPORTED, "Davao Prov.", "Davao", "wikidata:Q15095071")
    assert not reasons_for(run, "province_state")
    county = run.fields["county"]
    assert (county.state, county.literal, county.authority_id) == (ValueState.NOT_PRESENT, None, None)
    assert county.reason.startswith(field_step.PLACE_ABOVE_NOT_ON_LABEL.format(
        key="county", text="Davao Prov.", field="Province/State"))
    assert "county" in cleared_as_not_on_label(run) and not reasons_for(run, "county")


def test_the_province_stays_for_review_when_the_island_is_also_a_province(tmp_path):
    """The same label, where a gazetteer also holds a first-level unit
    "Mindanao": the readers' two texts are both provinces, and the field
    goes to review as before."""
    rig = build_rig(tmp_path, DAVAO, candidates=DAVAO_CANDIDATES, decided=True)
    run = rig.specimen.run
    province = [*ANSWERS[("nga", "Mindanao")], ("Mindanao", "nga:adm1", "A.ADM1", (PH_CODE,), None)]
    settle(rig, Scripted({"country": COUNTRY,
        "province_state": expert(*PROVINCE_LOOKUPS, answer=settled_on("Davao Prov.", "Davao",
            "wikidata:Q15095071", cite=2)),
        "county": expert(("wikidata", "Davao Province, Philippines"), answer=several("Davao Prov.", "Davao")),
        "city": answering(LACKS), "precise_location": answering(LACKS)}),
        tools=Stored(rig.blobs, {("nga", "Mindanao"): province}))
    assert run.fields["province_state"].state == ValueState.AMBIGUOUS
    assert run.fields["province_state"].reason.startswith(agreement.DIFFER)
    # No place above settled: the county keeps its expert's answer.
    assert run.fields["county"].state == ValueState.AMBIGUOUS


# ---- a county or a city on a settled place's text (shape 1) ---------------

# 93e61763's label: its readers differ on the department's spelling, and no
# reading is decided.
YEPOCAPA = label_with(**NO_PLACE_LINES) + "\nYepocapa, 4800ft.\nChimaltenango,\nGuatemala"
YEPOCAPA_B = YEPOCAPA.replace("Chimaltenango,", "Chimaltenago,")
GUATEMALA = expert(("tgn", "Guatemala"), answer=settled_on("Guatemala", None, "tgn:7005493"))
DEPARTMENT = expert(("tgn", "Chimaltenango"), ("tgn", "Chimaltenago"),
    answer=settled_on("Chimaltenango", None, "tgn:1000565"))
TOWN = expert(("geolocate", "Yepocapa, Chimaltenango, Guatemala"), answer=settled_on("Yepocapa", None,
    "geolocate:Yepocapa, Chimaltenango, Guatemala"))


def yepocapa_rig(tmp_path, first=YEPOCAPA, second=YEPOCAPA_B):
    return build_rig(tmp_path, first, second, candidates=[*COLLECTORS,
        ("country", "1A", "Guatemala", "Guatemala"), ("country", "1B", "Guatemala", "Guatemala"),
        ("province_state", "1A", "Chimaltenango", "Chimaltenango,"),
        ("province_state", "1B", "Chimaltenago", "Chimaltenago,"),
        *(("city", name, "Yepocapa", "Yepocapa, 4800ft.") for name in BOTH)])


def test_a_county_on_the_settled_departments_line_is_not_on_the_label(tmp_path):
    """93e61763 on 2026-10-17: the department settled on 1A's
    "Chimaltenango" (1B's "Chimaltenago" found by none), and the county's
    expert, whose sources also hold a municipio Chimaltenango, answered the
    two readers' texts of that one line. Both are the province's text: the
    label names no county. On c38f4fd4 the county is ambiguous, for review."""
    rig = yepocapa_rig(tmp_path)
    run = rig.specimen.run
    prepared, outcomes, calls = research(rig, Scripted({"country": GUATEMALA, "province_state": DEPARTMENT,
        "county": answering(FieldAnswer(outcome="several_possibilities",
            options=["Chimaltenango,", "Chimaltenago,"], explanation="The municipio or the department.")),
        "city": TOWN, "precise_location": answering(LACKS)}), tools=Stored(rig.blobs))
    decisions: dict[str, dict] = {}
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    province = run.fields["province_state"]
    assert (province.state, province.authority_id) == (ValueState.SUPPORTED, "tgn:1000565")
    county = run.fields["county"]
    assert (county.state, county.literal, county.verbatim_by_observation) == (ValueState.NOT_PRESENT, None, {})
    assert county.reason == field_step.PLACE_ABOVE_NOT_ON_LABEL.format(key="county", text="Chimaltenango,",
        field="Province/State") + " The municipio or the department."
    assert decisions["county"] == {"refusal": "place_above_text_only", "rule": "A_not_on_label"}
    assert "county" in cleared_as_not_on_label(run)


def test_a_source_name_beside_the_provinces_text_is_no_county_the_label_writes(tmp_path):
    """f35af3a5 on 2026-10-17: "Davao, Prov." settled as the province, and the
    county's expert answered "Davao", written only in that line, and "Davao
    City", a source's name the label never writes. On c38f4fd4 the county
    is ambiguous, for review."""
    text = label_with(**NO_PLACE_LINES) + "\nE. slope Mt. McKinley\nDavao, Prov. 3300'\nMindanao, P.I."
    rig = build_rig(tmp_path, text, candidates=candidates(("country", "P.I.", "Mindanao, P.I."),
        ("province_state", "Davao, Prov.", "Davao, Prov. 3300'")))
    run = rig.specimen.run
    settle(rig, Scripted({
        "country": expert(("wikidata", "Philippine Islands"), answer=settled_on("P.I.", "Philippines",
            "wikidata:Q928")),
        "province_state": expert(("wikidata", "Davao Province, Philippines"), answer=settled_on(
            "Davao, Prov.", "Davao", "wikidata:Q15095071")),
        "county": answering(FieldAnswer(outcome="several_possibilities", options=["Davao", "Davao City"],
            explanation="The province or the city.")),
        "city": answering(LACKS), "precise_location": answering(LACKS)}), tools=Stored(rig.blobs))
    assert run.fields["province_state"].state == ValueState.SUPPORTED
    # The province, inside the Philippines, confirms "P.I." (as before).
    assert run.fields["country"].state == ValueState.SUPPORTED
    county = run.fields["county"]
    assert (county.state, county.literal) == (ValueState.NOT_PRESENT, None)
    assert county.reason.startswith(field_step.PLACE_ABOVE_NOT_ON_LABEL.format(
        key="county", text="Davao", field="Province/State"))
    assert "county" in cleared_as_not_on_label(run) and not reasons_for(run, "county")


@pytest.mark.parametrize(("options", "first", "why"), [
    # The label writes the name twice: the second line is no province's text.
    (["Chimaltenango,"], YEPOCAPA.replace("\nGuatemala", "\nChimaltenango,\nGuatemala"), "written twice"),
    # The town's line: a place below the county, not above it.
    (["Chimaltenango,", "Yepocapa"], YEPOCAPA, "a place below"),
    # A name the label writes on no settled place's line.
    (["Chimaltenango,", "Acatenango"], YEPOCAPA + "\nAcatenango", "another line"),
], ids=["written-twice", "the-towns-text", "another-line"])
def test_a_county_with_text_no_place_above_holds_stays_for_review(tmp_path, options, first, why):
    rig = yepocapa_rig(tmp_path, first, first.replace("Chimaltenango,\nGuatemala", "Chimaltenago,\nGuatemala"))
    run = rig.specimen.run
    settle(rig, Scripted({"country": GUATEMALA, "province_state": DEPARTMENT,
        "county": answering(FieldAnswer(outcome="several_possibilities", options=options, explanation=why)),
        "city": TOWN, "precise_location": answering(LACKS)}), tools=Stored(rig.blobs))
    assert run.fields["province_state"].state == ValueState.SUPPORTED
    county = run.fields["county"]
    assert county.state == ValueState.AMBIGUOUS and "mandatory_unresolved:county" in run.reasons


def test_a_county_left_open_beside_an_unsettled_province_keeps_its_answer(tmp_path):
    """No place above settled: nothing holds the county's text."""
    rig = yepocapa_rig(tmp_path)
    run = rig.specimen.run
    settle(rig, Scripted({"country": GUATEMALA,
        "province_state": answering(FieldAnswer(outcome="several_possibilities",
            options=["Chimaltenango", "Chimaltenago"], explanation="Two spellings.")),
        "county": answering(FieldAnswer(outcome="several_possibilities",
            options=["Chimaltenango,", "Chimaltenago,"], explanation="Two units.")),
        "city": TOWN, "precise_location": answering(LACKS)}), tools=Stored(rig.blobs))
    assert run.fields["county"].state == ValueState.AMBIGUOUS


# ---- initials located by another place of the label (shape 3) -------------

# 2b02009d's labels: "P.I." under "Mindanao", and "Mt. Apo" below "Seliban Riv.".
APO = label_with(**NO_PLACE_LINES) + "\nMindanao\nVII.31.36 P.I.\nSeliban Riv.\nMt. Apo"
APO_CANDIDATES = candidates(("country", "P.I.", "VII.31.36 P.I."), ("province_state", "Mindanao", "Mindanao"),
    ("city", "Seliban Riv.", "Seliban Riv."), ("precise_location", "Mt. Apo", "Mt. Apo"))
MOUNT_APO = (("wikidata", "Mount Apo, Mindanao, Philippines"), ("nga", "Mount Apo, Mindanao, Philippines"))
APO_EXPERTS = {
    "country": expert(("wikidata", "Philippine Islands"), answer=settled_on("P.I.", "Philippines", "wikidata:Q928")),
    "province_state": expert(("wikidata", "Mindanao, Philippines"), ("nga", "Mindanao, Philippines"), answer=CANNOT),
    "county": answering(LACKS), "city": answering(LACKS),
    "precise_location": expert(*MOUNT_APO, answer=lambda found: FieldAnswer(outcome="resolved", literal="Mt. Apo",
        reading_names=["1A"], source_evidence_ids=[item.evidence.id for item in found],
        explanation="The mountain, as written.")),
}


def test_initials_settle_beside_a_mountain_every_source_places_inside_them(tmp_path):
    """2b02009d on 2026-10-17: "P.I." settled as the Philippines on its
    expansion "Philippine Islands", and no place field below it settled
    ("Mindanao" is an island, a village in Honduras and in Guatemala too),
    so the initials alone did not decide. Its "Mt. Apo" is a Mount Apo only
    in the Philippines, for Wikidata (the volcano; the ship names no place)
    and NGA (two mountains and a street): that confirms the initials, and
    the country cites those answers. On c38f4fd4 the country is ambiguous."""
    rig = build_rig(tmp_path, APO, candidates=APO_CANDIDATES)
    run = rig.specimen.run
    settle(rig, Scripted(APO_EXPERTS), tools=Stored(rig.blobs))
    country = run.fields["country"]
    assert (country.state, country.literal, country.normalized, country.authority_id) == (
        ValueState.SUPPORTED, "P.I.", "Philippines", "wikidata:Q928")
    assert country.reason.endswith(field_step.PLACED_INSIDE.format(literal="P.I.",
        expansion="Philippine Islands", text="Mt. Apo"))
    apo = {row.id for row in run.evidence if row.excerpt and row.excerpt.startswith(("Apo Mountain", "Mount Apo"))}
    assert len(apo) == 2 and all(country.evidence_relations[i] == "supports" for i in apo)
    assert not reasons_for(run, "country")
    # The island is still no province.
    assert run.fields["province_state"].state == ValueState.UNRESOLVED


@pytest.mark.parametrize("extra", [
    # A Mount Apo NGA places in another country.
    {("nga", "Mount Apo"): [*ANSWERS[("nga", "Mount Apo")],
        ("Mount Apo", "nga:elsewhere", "T.MT", (("Sabah", None, None), ("MY", None, "MY")), None)]},
    # No source holds a Mount Apo that names a place it is in.
    {("wikidata", "Mount Apo"): [("Mount Apo", "wikidata:Q105769692", "ship", (), None)],
     ("nga", "Mount Apo"): [("Apo Mountain", "nga:-2408936", "T.MT", (("Iloilo", None, None), PH_CODE), None)]},
], ids=["one-elsewhere", "none-placed"])
def test_initials_stay_ambiguous_when_the_other_place_is_not_only_inside_them(tmp_path, extra):
    rig = build_rig(tmp_path, APO, candidates=APO_CANDIDATES)
    run = rig.specimen.run
    settle(rig, Scripted(APO_EXPERTS), tools=Stored(rig.blobs, extra))
    country = run.fields["country"]
    assert (country.state, country.literal) == (ValueState.AMBIGUOUS, None)
    assert country.reason.startswith(agreement.initialism_alone("P.I.", "Philippine Islands"))


def test_an_island_with_namesakes_elsewhere_confirms_no_initials(tmp_path):
    """"Mindanao, P.I." alone: NGA also holds a Mindanao in Honduras and in
    Guatemala, so the island confirms nothing (as before this change)."""
    text = label_with(**NO_PLACE_LINES) + "\nMindanao, P.I."
    rig = build_rig(tmp_path, text, candidates=candidates(("country", "P.I.", "Mindanao, P.I."),
        ("province_state", "Mindanao", "Mindanao, P.I.")))
    run = rig.specimen.run
    settle(rig, Scripted({**APO_EXPERTS, "precise_location": answering(LACKS)}), tools=Stored(rig.blobs))
    assert run.fields["country"].state == ValueState.AMBIGUOUS
