"""The agreement rules the real runs of 2026-10-09 on the ten pilot specimens
questioned (agreement.py; FIELD_RESEARCH.md, step 5), with labels from other
countries and languages beside the pilot's.

The step's cases run the ordinary workflow's run through the scripted
resolver and sources of test_step.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from test_step import (
    LACKS,
    TEXT,
    Disposition,
    Gazetteer,
    Scripted,
    ValueState,
    answering,
    build_rig,
    cited_rows,
    confirming,
    every_field,
    from_tgn,
    label_with,
    reasons_for,
    resolved,
    settle,
)

from specimen_digitization.application.domain import FieldValue
from specimen_digitization.field_research import agreement, experts
from specimen_digitization.field_research.checks import collapse
from specimen_digitization.field_research.contracts import (
    FIELD_TOOLS,
    Candidate,
    FieldAnswer,
    FieldTask,
    PlaceRef,
    Reading,
    SourceCandidate,
)

E_ACUTE, E_GRAVE, U_UMLAUT, A_ACUTE, A_CIRCUMFLEX, E_CIRCUMFLEX, SHARP_S = (
    "\N{LATIN SMALL LETTER E WITH ACUTE}", "\N{LATIN SMALL LETTER E WITH GRAVE}",
    "\N{LATIN SMALL LETTER U WITH DIAERESIS}", "\N{LATIN SMALL LETTER A WITH ACUTE}",
    "\N{LATIN SMALL LETTER A WITH CIRCUMFLEX}", "\N{LATIN SMALL LETTER E WITH CIRCUMFLEX}",
    "\N{LATIN SMALL LETTER SHARP S}")
FEMALE = "\N{FEMALE SIGN}"


# ---- G34: a near spelling is checked against the larger places only ---------
# 105526330's province: the decided reading writes "Chimaltenago", Getty TGN
# knows only "Chimaltenango", and the reading also writes the town Yepocapa.
# The step checked the town as a parent of the department and left the
# province for review. A place's parents are only larger places.

def place(name, authority_id, *parents):
    """A source's candidate with its parents (name, authority_id), nearest first."""
    return SourceCandidate(name, authority_id, "place", None, tuple(PlaceRef(*parent) for parent in parents))


def field(*texts, authority_id=None):
    return agreement.PlaceField(tuple(texts), authority_id)


FRANCE = field("France", authority_id="tgn:1000070")
GERMANY = field("Deutschland", authority_id="tgn:7000084")
BRAZIL = field("Brasil", authority_id="tgn:1000047")


@pytest.mark.parametrize(("key", "candidate", "written", "settled"), [
    # A French departement one letter off ("Finistre"), in its region and country, with the
    # town of Brest below it on the reading.
    ("county", place("Finist" + E_GRAVE + "re", "tgn:7002849", ("Bretagne", "tgn:7002848"),
        ("France", "tgn:1000070")),
     {"country": FRANCE, "province_state": field("Bretagne", authority_id="tgn:7002848"), "city": field("Brest")},
     {"country": FRANCE, "province_state": field("Bretagne", authority_id="tgn:7002848")}),
    # A German Land one letter off ("Bayer" for Bayern), with Muenchen below it.
    ("province_state", place("Bayern", "tgn:7003686", ("Deutschland", "tgn:7000084")),
     {"country": GERMANY, "city": field("M" + U_UMLAUT + "nchen")}, {"country": GERMANY}),
    # A Brazilian state one letter off ("Minas Geras"), with a county and a city below it.
    ("province_state", place("Minas Gerais", "tgn:1001780", ("Brasil", "tgn:1000047")),
     {"country": BRAZIL, "county": field("Sabar" + A_ACUTE), "city": field("Belo Horizonte")},
     {"country": BRAZIL}),
], ids=["french-departement-above-its-town", "german-land-above-its-city", "brazilian-state-above-county-and-city"])
def test_a_near_spelled_place_is_not_checked_against_the_places_below_it(key, candidate, written, settled):
    """On origin/main each is refused: the town below is no parent of the place."""
    assert agreement.parents_refusal(key, candidate, agreement.NEAR_SPELLING, written=written,
        settled=settled) is None


@pytest.mark.parametrize(("literal", "nation", "authority_id", "town"), [
    # Spanish: "Mexco" beside the city "Mexico" (with its accent), TGN's nation lists itself.
    ("Mexco", "Mexico", "tgn:1000077", "M" + E_ACUTE + "xico"),
    # German and French spellings of Luxembourg, the city of the same name below it.
    ("Luxemburg", "Luxembourg", "tgn:7006830", "Luxembourg"),
    # Spanish: "Panma" beside the city "Panama" (with its accent).
    ("Panma", "Panam" + A_ACUTE, "tgn:1000149", "Panam" + A_ACUTE),
], ids=["mexico", "luxembourg", "panama"])
def test_a_near_spelled_country_never_settles_on_a_city_of_its_name(literal, nation, authority_id, town):
    """On origin/main each settles: a nation lists itself as its parent, and
    the city below it has the nation's name. A country has no larger place."""
    candidate = place(nation, authority_id, (nation, authority_id))
    refused = agreement.parents_refusal("country", candidate, agreement.NEAR_SPELLING,
        written={"city": field(town)}, settled={})
    assert refused is not None and refused.reason == agreement.NEAR_UNFIT


def test_a_near_spelled_city_still_needs_every_larger_place_as_its_parent():
    """The control, unchanged: a Brazilian city one letter off ("Bello
    Horizonte") whose reading writes a state it does not lie in."""
    candidate = place("Belo Horizonte", "tgn:7012345", ("Minas Gerais", "tgn:1001780"), ("Brasil", "tgn:1000047"))
    refused = agreement.parents_refusal("city", candidate, agreement.NEAR_SPELLING,
        written={"country": BRAZIL, "province_state": field("S" + A_ACUTE + "o Paulo")}, settled={"country": BRAZIL})
    assert refused is not None and refused.reason == agreement.NEAR_UNFIT


def test_105526330s_province_settles_one_letter_off_beside_its_town(tmp_path):
    """The real run's shape: country Guatemala, the decided province
    "Chimaltenago" and the town Yepocapa. Getty TGN's department
    Chimaltenango, one letter off, lies in Guatemala: the province settles
    with a near_spelling warning, and the town settles inside it. On
    origin/main the province goes to review (NEAR_UNFIT)."""
    rig = build_rig(tmp_path, label_with(country="Guatemala", province_state="Chimaltenago", county=None,
        city="Yepocapa"))
    run = rig.specimen.run
    settle(rig, Scripted({"country": from_tgn("Guatemala", "Guatemala", None, "tgn:7005493"),
        "province_state": from_tgn("Chimaltenango", "Chimaltenago", "Chimaltenango", "tgn:1000565"),
        "county": answering(LACKS),
        "city": confirming("Yepocapa", reading="1A", within=("Chimaltenango", "Guatemala"))}),
        tools=Gazetteer(rig.blobs))
    province = run.fields["province_state"]
    assert (province.state, province.literal, province.normalized, province.authority_id) == (
        ValueState.SUPPORTED, "Chimaltenago", "Chimaltenango", "tgn:1000565")
    assert [f.reason_code for f in run.findings] == ["near_spelling:province_state"]
    assert run.fields["city"].state == ValueState.SUPPORTED
    assert not reasons_for(run, "province_state") and not reasons_for(run, "city")


# ---- readers that differ only in letter case or spacing agree ---------------
# 105526322's habitat ("shrubs, mostly forest" and "Shrubs, mostly forest")
# and taxon ("sp. 30" and "Sp.30"), and 105526330's precise location
# ("Yepocapa,4800 ft." beside "Yepocapa, 4800 ft."), went to review as readers
# that differ. Compared after casefolding and removing every space, they are
# one text, settled on the first reader's spelling.

def two_readers(key, first, second, *, line="leg. R. D. Mitchell"):
    """Label 2 with no decided transcript: 2A writes `first`, 2B `second`, and
    the organiser gives each reader's text as its candidate."""
    readings = tuple(Reading(name, "region-2", "obs-" + name, "raw_reading", f"{text}\n{line}")
        for name, text in (("2A", first), ("2B", second)))
    task = FieldTask(key, True, FieldValue(state=ValueState.AMBIGUOUS),
        tuple(Candidate(name, text, text, "ev-" + name) for name, text in (("2A", first), ("2B", second))),
        FIELD_TOOLS[key])
    return task, readings


def refusal_of(task, readings, literal, *names):
    named = [reading for reading in readings if reading.name in (names or ("2A",))]
    return agreement.refusal(task, readings, literal=literal, named=named, value=None, authority_id=None,
        cited=[], received=[])


AGREE = {
    # 105526322's habitat and taxon, and a locality with "Mt." in capitals.
    "322-habitat": ("habitat", "shrubs, mostly forest", "Shrubs, mostly forest"),
    "322-taxon": ("taxon", "sp. 30 " + FEMALE, "Sp.30 " + FEMALE),
    "mount-in-capitals": ("precise_location", "E. slope Mt. McKinley", "E. slope MT. McKinley"),
    # Spanish, Portuguese, French and German labels.
    "spanish-habitat": ("habitat", "bosque nublado", "Bosque Nublado"),
    "portuguese-habitat": ("habitat", "mata atl" + A_CIRCUMFLEX + "ntica", "Mata Atl" + A_CIRCUMFLEX + "ntica"),
    "french-locality-spacing": ("precise_location", "for" + E_CIRCUMFLEX + "t de  Fontainebleau",
        "For" + E_CIRCUMFLEX + "t de Fontainebleau"),
    "german-method": ("collection_method", "Lichtfang", "LICHTFANG"),
    "german-sharp-s": ("precise_location", "Waldstra" + SHARP_S + "e 4", "WALDSTRASSE 4"),
    # Metric and imperial elevations, and dates in Roman and numeric styles.
    "feet-spacing": ("elevation_from_ft", "6400 ft", "6400ft"),
    "metres-case": ("elevation_from_m", "1200 m", "1200 M"),
    "roman-month-case": ("date_visited_from", "24.IV.1948", "24.iv.1948"),
    "numeric-date-spacing": ("date_visited_from", "IV-24-48", "IV-24- 48"),
    "collector-initials-spacing": ("collectors", "H. Hoogstraal", "H.Hoogstraal"),
}


@pytest.mark.parametrize(("key", "first", "second"), AGREE.values(), ids=AGREE)
def test_readers_that_differ_only_in_case_or_spacing_agree_on_the_first_readers_spelling(key, first, second):
    """On origin/main each label settles on nothing: its readers differ."""
    task, readings = two_readers(key, first, second)
    [label] = agreement.labels(task, readings, []).values()
    assert (label.settled, label.by_source) == (frozenset({collapse(first)}), False)
    assert refusal_of(task, readings, first) is None


@pytest.mark.parametrize(("key", "first", "second"), list(AGREE.values())[:4], ids=list(AGREE)[:4])
def test_the_second_readers_spelling_is_sent_back_for_the_first(key, first, second):
    """The literal keeps the first reader's spelling. On origin/main the
    answer is refused as readers that disagree."""
    task, readings = two_readers(key, first, second)
    refused = refusal_of(task, readings, second, "2B")
    assert refused is not None and refused.reason == agreement.DIFFER and refused.differ
    assert f"agree on {collapse(first)!r}" in refused.retry


DIFFER = {
    # 105526328's municipality and 105526323's year: a letter apart.
    "328-municipality": ("collection_method", "Yepocapa, Mun.", "Yepocapa, Mum."),
    "323-year": ("date_visited_from", "6-Sept.-1946", "6-Sept.-1948"),
    # 105526322's elevation, the foot mark missing; a metres period; a dotted month.
    "322-foot-mark": ("elevation_from_ft", "Elev.6400'", "Elev. 6400"),
    "metres-period": ("elevation_from_m", "1200 m", "1200 m."),
    "month-period": ("date_visited_from", "24 Apr 1948", "24 apr. 1948"),
    # An accent is a letter: Portuguese "Atlantica" against "Atlantica" with its circumflex.
    "accent": ("habitat", "Mata Atlantica", "Mata Atl" + A_CIRCUMFLEX + "ntica"),
    # 105526322's collector, a letter apart.
    "322-collector": ("collectors", "H. Hoopstraal", "H. Hoogstraal"),
}


@pytest.mark.parametrize(("key", "first", "second"), DIFFER.values(), ids=DIFFER)
def test_readers_that_differ_in_punctuation_or_a_letter_still_disagree(key, first, second):
    """The control, unchanged: no source decides between them."""
    task, readings = two_readers(key, first, second)
    [label] = agreement.labels(task, readings, []).values()
    assert not label.settled
    refused = refusal_of(task, readings, first)
    assert refused is not None and refused.reason == agreement.DIFFER


def test_a_decided_transcript_keeps_its_own_spelling():
    """105526330's precise location: 2A, the decided reading, writes
    "Yepocapa,4800 ft.", 2B "Yepocapa, 4800 ft.". G19 decides on 2A's text;
    2B's spelling is refused as before."""
    readings = (Reading("2A", "region-2", "obs-2A", "decided_transcript", "Yepocapa,4800 ft.\nIV-25 1948"),
        Reading("2B", "region-2", "obs-2B", "raw_reading", "Yepocapa, 4800 ft.\nIV-25 1948"))
    task = FieldTask("precise_location", False, FieldValue(state=ValueState.AMBIGUOUS),
        (Candidate("2A", "Yepocapa,4800 ft.", "Yepocapa,4800 ft.", "ev-2A"),
         Candidate("2B", "Yepocapa, 4800 ft.", "Yepocapa, 4800 ft.", "ev-2B")), FIELD_TOOLS["precise_location"])
    assert refusal_of(task, readings, "Yepocapa,4800 ft.") is None
    assert refusal_of(task, readings, "Yepocapa, 4800 ft.", "2B").reason == agreement.NOT_DECIDED


def test_the_experts_check_accepts_the_first_readers_spelling():
    """105526322's habitat at the expert: the answer naming 2A passes its
    check; on origin/main it is sent back as readers that disagree."""
    task, readings = two_readers("habitat", "shrubs, mostly forest", "Shrubs, mostly forest")
    made = experts._Expert(task, readings, SimpleNamespace(sources=()), None)
    given = FieldAnswer(outcome="resolved", literal="shrubs, mostly forest", reading_names=["2A"],
        explanation="Both readers write it; 2B capitalises it.")
    assert made.validate(given).reading_names == ["2A"]


def test_readers_that_differ_only_in_case_settle_the_field_and_keep_both_texts(tmp_path):
    """105526322's habitat through the step: no decided transcript, 1A writes
    "shrubs, mostly forest" and 1B "Shrubs, mostly forest". The value is 1A's
    spelling; 1B's text stays in the lineage. On origin/main it is ambiguous."""
    first, second = "shrubs, mostly forest", "Shrubs, mostly forest"
    rig = build_rig(tmp_path, TEXT.replace("Synthetic grassland", first), TEXT.replace("Synthetic grassland", second),
        candidates=every_field(("habitat", "1A", first, "habitat: " + first),
            ("habitat", "1B", second, "habitat: " + second)))
    run = rig.specimen.run
    reader_a, reader_b = run.observations
    settle(rig, Scripted({"habitat": answering(resolved(first, reading="1A"))}))
    habitat = run.fields["habitat"]
    assert (habitat.state, habitat.literal, habitat.input_source) == (ValueState.SUPPORTED, first, "raw_reading")
    assert habitat.verbatim_by_observation == {reader_a.id: first, reader_b.id: second}
    assert cited_rows(run, "habitat")["habitat: " + first] == "supports"
    assert not reasons_for(run, "habitat")
