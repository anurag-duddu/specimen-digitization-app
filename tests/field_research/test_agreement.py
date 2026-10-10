"""The agreement rules the real runs of 2026-10-09 on the ten pilot specimens
questioned (agreement.py; FIELD_RESEARCH.md, step 5), with labels from other
countries and languages beside the pilot's.

The step's cases run the ordinary workflow's run through the scripted
resolver and sources of test_step.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry
from test_step import (
    LACKS,
    TEXT,
    Gazetteer,
    Scripted,
    answering,
    build_rig,
    cited_rows,
    confirming,
    every_field,
    failing,
    from_tgn,
    label_with,
    reasons_for,
    resolved,
    settle,
)

from specimen_digitization.application.domain import Evidence, FieldValue, LookupStatus, ValueState
from specimen_digitization.application.integrity import verify_evidence
from specimen_digitization.field_research import agreement, experts
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.checks import collapse
from specimen_digitization.field_research.contracts import (
    FIELD_TOOLS,
    Candidate,
    FieldAnswer,
    FieldTask,
    PlaceRef,
    Reading,
    SourceAnswer,
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


# ---- an expert may cite text the readings write, not only a candidate --------
# 105526328's date_visited_from: both readers of label 3 write "IV-24-48" and
# parse_date reads 1948-04-24, but the organiser offered no candidate, so the
# expert's answer was sent back and the field went to review; so did its
# collection method ("trap"), and 105526329's and 105526330's precise
# location. The literal may now be whole words of one line that each reading
# it names writes, under the same reader rules as a candidate.

PILOT_DATES = {"version": "date-rules-v1", "two_digit_year_century": 1900, "roman_numeral_months": True}
LABEL_3A = ("Yepocapa, Mun.\nYepocapa,\nchimaltenango,\nGuatemala.\nIV-24-48\nElev. 4800 ft.\n"
    "lot #2 cut branch\ntrap\nR.D. Mitchell")
LABEL_3B = ("Yepocapa, Mum.\nYepocapa,\nchimaltenago,\nGuatemala.\nIV-24-48\nElev. 4800 ft.\n"
    "lot #a cut branch\ntrap\nR.D. Mitchell")


def label(first, second=None, *, decided=False, region="region-3", names=("3A", "3B")):
    """One label's two readers; the first is its decided transcript when `decided`."""
    return (Reading(names[0], region, "obs-" + names[0], "decided_transcript" if decided else "raw_reading", first),
        Reading(names[1], region, "obs-" + names[1], "raw_reading", first if second is None else second))


def uncandidated(key, *candidates):
    """The field's task as the organiser left it: no value, and only these
    (reading, literal) candidates, each quoting its literal."""
    return FieldTask(key, True, FieldValue(), tuple(Candidate(name, text, text, f"ev-{name}-{text}")
        for name, text in candidates), FIELD_TOOLS[key])


def checked(task, readings, given, *, checks=(), received=()):
    """The expert's own check of an answer: the checks it ran, the lookups it
    received, then its answer. The answer it keeps, or the ModelRetry."""
    made = experts._Expert(task, readings, SimpleNamespace(sources=tuple(FIELD_TOOLS[task.key])), PILOT_DATES)
    for tool, literal in checks:
        asyncio.run(getattr(made, tool)(literal))
    for answer in received:
        made.calls.append(experts._Call(answer.source_id, answer.query, answer.status, answer))
    return made.validate(FieldAnswer(explanation="Read from the readings.", **given))


ACCEPTED = {
    # 105526328's label 3, two readers and no decided transcript.
    "328-collecting-date": (label(LABEL_3A, LABEL_3B), "date_visited_from",
        dict(literal="IV-24-48", value="1948-04-24"), [("parse_date", "IV-24-48")]),
    "328-collection-method": (label(LABEL_3A, LABEL_3B), "collection_method", dict(literal="trap"), []),
    # 105526330's locality, from its decided transcript; the other reader is evidence only.
    "330-precise-location": (label("Yepocapa,4800 ft.\nIV-25\n1948", "Yepocapa, 4800 ft.\nIV-25\n1948",
        decided=True), "precise_location", dict(literal="Yepocapa,4800 ft."), []),
    # A Costa Rican label: the locality before its comma, the elevation after it.
    "spanish-locality": (label("Volc" + A_ACUTE + "n Barva, 2000 msnm\n15-VIII-1965"), "precise_location",
        dict(literal="Volc" + A_ACUTE + "n Barva"), []),
    "spanish-date": (label("Volc" + A_ACUTE + "n Barva, 2000 msnm\n15-VIII-1965"), "date_visited_from",
        dict(literal="15-VIII-1965", value="1965-08-15"), [("parse_date", "15-VIII-1965")]),
    # French: a light trap and its date on one line.
    "french-method": (label("pi" + E_GRAVE + "ge lumineux, 12.VII.1971\nleg. J. Dupont"), "collection_method",
        dict(literal="pi" + E_GRAVE + "ge lumineux"), []),
    "french-date": (label("pi" + E_GRAVE + "ge lumineux, 12.VII.1971\nleg. J. Dupont"), "date_visited_from",
        dict(literal="12.VII.1971", value="1971-07-12"), [("parse_date", "12.VII.1971")]),
    # German: light trapping and a date with a Roman month.
    "german-date": (label("Lichtfang 24.VI.1952\nBayern"), "date_visited_from",
        dict(literal="24.VI.1952", value="1952-06-24"), [("parse_date", "24.VI.1952")]),
    # Portuguese: the habitat before a Malaise trap.
    "portuguese-habitat": (label("Mata Atl" + A_CIRCUMFLEX + "ntica, armadilha Malaise"), "habitat",
        dict(literal="Mata Atl" + A_CIRCUMFLEX + "ntica"), []),
    "portuguese-method": (label("Mata Atl" + A_CIRCUMFLEX + "ntica, armadilha Malaise"), "collection_method",
        dict(literal="armadilha Malaise"), []),
    # Imperial and metric elevations, as the readings write them.
    "imperial-elevation": (label("Mossy forest 6400'\nsp. 30 " + FEMALE), "elevation_from_ft",
        dict(literal="6400'", value="6400"), [("parse_elevation", "6400'")]),
    "metric-elevation": (label("Mindanao, alt. 1200 m\n24 Apr 1948"), "elevation_from_m",
        dict(literal="1200 m", value="1200"), [("parse_elevation", "1200 m")]),
    "english-date": (label("Mindanao, alt. 1200 m\n24 Apr 1948"), "date_visited_from",
        dict(literal="24 Apr 1948", value="1948-04-24"), [("parse_date", "24 Apr 1948")]),
    # Readers that differ only in case read the same text (2A's spelling).
    "case-only-readers": (label("Mossy forest\nleg. H. Hoogstraal", "mossy Forest\nleg. H. Hoogstraal"), "habitat",
        dict(literal="Mossy forest"), []),
}


@pytest.mark.parametrize(("readings", "key", "given", "ran"), ACCEPTED.values(), ids=ACCEPTED)
def test_text_every_reader_writes_as_whole_words_of_one_line_settles(readings, key, given, ran):
    """On origin/main each is sent back: the organiser offered no candidate."""
    task = uncandidated(key)
    names = [readings[0].name] if readings[0].input_source == "decided_transcript" or not readings[1].text.count(
        given["literal"]) else [r.name for r in readings]
    kept = checked(task, readings, dict(outcome="resolved", reading_names=names, **given), checks=ran)
    assert kept.literal == given["literal"]
    assert agreement.literal_basis(task, readings, given["literal"], [readings[0]]) == agreement.TRANSCRIPT


GBIF_DANAUS = SourceAnswer("gbif", "Danaus plexippus", LookupStatus.SUCCESS,
    (SourceCandidate("Danaus plexippus (Linnaeus, 1758)", "5133088", "SPECIES"),),
    Evidence(id="ev-danaus", kind="authority", source="gbif", locator="5133088",
        excerpt="Danaus plexippus (Linnaeus, 1758) | 5133088 | SPECIES | "), note="exact")


def test_a_taxon_read_from_the_transcript_settles_on_gbifs_decision_for_it():
    """Both readers write the binomial on a line of its own and the organiser
    offered no candidate. On origin/main the answer is sent back."""
    readings = label("Danaus plexippus\nMexico, Sinaloa\nleg. R. D. Mitchell", names=("1A", "1B"), region="r1")
    kept = checked(uncandidated("taxon"), readings, dict(outcome="resolved", literal="Danaus plexippus",
        reading_names=["1A", "1B"], value="Danaus plexippus (Linnaeus, 1758)", authority_id="5133088",
        source_evidence_ids=["ev-danaus"]), received=[GBIF_DANAUS])
    assert kept.authority_id == "5133088"


REFUSED = {
    # 105526328's municipality: 3B writes "Mum.", and the organiser found nothing there.
    "328-county-one-reader": (label(LABEL_3A, LABEL_3B), uncandidated("collection_method"),
        "Yepocapa, Mun.", ["3A"], "NOT_EVERY_READER"),
    # Portuguese: the other reader drops the accent, a letter apart.
    "portuguese-accent": (label("Mata Atl" + A_CIRCUMFLEX + "ntica, Malaise", "Mata Atlantica, Malaise"),
        uncandidated("habitat"), "Mata Atl" + A_CIRCUMFLEX + "ntica", ["3A"], "NOT_EVERY_READER"),
    # Imperial: the other reader misses the foot mark.
    "imperial-foot-mark": (label("Mossy forest 6400'", "Mossy forest 6400"), uncandidated("habitat"),
        "Mossy forest 6400'", ["3A"], "NOT_EVERY_READER"),
    # 105526323's year: the organiser gave only 2B's "6-Sept.-1948"; 2A's text read from the
    # transcript is then one of two readers' texts, and no source decides a date.
    "323-year": (label("6-Sept.-1946, Elev. 6400'", "6-Sept.-1948, Elev.6400'", names=("2A", "2B"), region="r2"),
        uncandidated("collectors", ("2B", "6-Sept.-1948")), "6-Sept.-1946", ["2A"], "DIFFER"),
    # A decided label whose organiser placed other text in the field: two texts, no settling.
    "decided-beside-a-candidate": (label("Yepocapa, Mun.\nChimaltenango", decided=True),
        uncandidated("habitat", ("3A", "Chimaltenango")), "Yepocapa, Mun.", ["3A"], "DIFFER"),
    # A taxon whose line writes a longer name, or whose genus stands on the line above.
    "longer-name-on-the-line": (label("Danaus plexippus megalippe\nleg. J. Smith"), uncandidated("taxon"),
        "Danaus plexippus", ["3A", "3B"], "PART_OF_NAME"),
    "328-genus-on-the-line-above": (label("VI-24-68-7.\nEpipsocus\nsp. 1\n" + FEMALE + " terminalia"),
        uncandidated("taxon"), "sp. 1", ["3A", "3B"], "PART_OF_NAME"),
    # A genus marked doubtful on its line.
    "doubtful-genus": (label("cf. Epipsocus sp. 1\nleg. J. Smith"), uncandidated("taxon"),
        "Epipsocus sp. 1", ["3A", "3B"], "DOUBTFUL_GENUS"),
}


@pytest.mark.parametrize(("readings", "task", "literal", "names", "reason"), REFUSED.values(), ids=REFUSED)
def test_text_read_from_the_transcript_keeps_every_other_rule(readings, task, literal, names, reason):
    """Each refusal is new: on origin/main every one is NOT_CANDIDATE."""
    named = [reading for reading in readings if reading.name in names]
    refused = agreement.refusal(task, readings, literal=literal, named=named, value=None, authority_id=None,
        cited=[], received=[])
    assert refused is not None and refused.reason == getattr(agreement, reason)


STILL_NOT_TEXT = {
    # Part of a word: the day and year of a date, a morphocode's number, a number's thousands.
    "inside-a-date": (label(LABEL_3A, LABEL_3B), "date_visited_from", "24-48"),
    "inside-a-code": (label("Sp.30 " + FEMALE), "taxon", "30"),
    "thousands": (label("Mindanao, 1,200 m"), "elevation_from_m", "200 m"),
    # Two lines: 105526328's locality block.
    "two-lines": (label(LABEL_3A, LABEL_3B), "precise_location", "Yepocapa, Mun.\nYepocapa,"),
}


@pytest.mark.parametrize(("readings", "key", "literal"), STILL_NOT_TEXT.values(), ids=STILL_NOT_TEXT)
def test_text_that_cuts_a_word_or_spans_lines_is_still_no_literal(readings, key, literal):
    """The control: refused as before; only the retry, which now names the
    whole-word rule, is new."""
    refused = agreement.literal_refusal(uncandidated(key), readings, literal=literal, named=list(readings))
    assert refused is not None and refused.reason == agreement.NOT_CANDIDATE
    assert "whole words within one line" in refused.retry


@pytest.mark.parametrize(("written", "literal"), [
    # The second review's B2: a piece of the candidate, or the candidate extended.
    ("3 Sept. '46", "Sept. '46"),
    ("San Pedro", "San Pedro Sacatepequez"),
    ("Danaus plexippus megalippe", "Danaus plexippus"),
])
def test_text_that_cuts_or_extends_a_candidate_of_its_reading_is_still_refused(written, literal):
    """The control: the reading's text holds both, and the candidate is the
    organiser's whole text there. Refused as before; only the retry, which
    now names the candidate cut, is new."""
    readings = label(f"{written} Sacatepequez\nleg. J. Smith" if written == "San Pedro" else f"{written}\nleg. J. Smith")
    task = uncandidated("collectors", *((name, written) for name in ("3A", "3B")))
    refused = agreement.literal_refusal(task, readings, literal=literal, named=list(readings))
    assert refused is not None and refused.reason == agreement.NOT_CANDIDATE
    assert f"cuts or extends the candidate {written!r}" in refused.retry


def test_the_kinds_of_text_two_fields_may_share():
    assert agreement.may_share_text("city", "precise_location")  # a place inside the locality
    assert agreement.may_share_text("elevation_from_ft", "elevation_from_m")
    assert agreement.may_share_text("date_visited_from", "date_identified")
    assert agreement.may_share_text("verbatim_dts", "date_visited_from")  # D/T/S may hold anything
    assert not agreement.may_share_text("precise_location", "elevation_from_ft")
    assert not agreement.may_share_text("collection_code", "date_visited_from")
    assert not agreement.may_share_text("habitat", "collection_method")
    assert not agreement.may_share_text("taxon", "collection_code")
    assert agreement.may_share_text("collectors", "identified_by_irn")


@pytest.mark.parametrize(("text", "literal", "found"), [
    # A comma ends a word with no space after it, except between digits.
    ("Yepocapa,4800 ft.", "4800 ft.", True),
    ("Yepocapa,4800 ft.", "Yepocapa", True),
    ("Mindanao, 1,200 m", "1,200 m", True),
    ("Mindanao, 1,200 m", "200 m", False),
    # Punctuation at a word's edge may be left off; a word is never cut.
    ("Mindanao (Davao)", "Davao", True),
    ("Guatemala.", "Guatemala", True),
    ("IV-24-48", "24-48", False),
    ("Sp.30 " + FEMALE, "30", False),
    ("trapping site", "trap", False),
    # One line only, and a letter or a digit in it.
    ("Yepocapa,\nchimaltenango,", "Yepocapa,\nchimaltenango,", False),
    ("? Epipsocus", "?", False),
    # Any characters other than letters and digits at a word's edge may be left
    # off, as the brief says: a quote, a foot or minute mark, a bracket.
    ("3 Sept. '46", "46", True),
    ("Elev. 6400'", "6400", True),
    ('"Yepocapa"', "Yepocapa", True),
    ("lot #2 cut branch", "2", True),
    # A range glued with a hyphen is one word.
    ("1200-1500 m", "1500 m", False),
])
def test_a_run_of_whole_words_within_one_line(text, literal, found):
    assert bool(agreement.verbatim_runs(text, literal)) == found


def test_text_from_the_transcript_on_a_decided_label_is_the_decided_readings():
    """G19, as for a candidate: 105526330's other reader's spacing, which the
    decided reading does not write, is refused."""
    readings = label("Yepocapa,4800 ft.\nIV-25", "Yepocapa, 4800 ft.\nIV-25", decided=True)
    refused = agreement.refusal(uncandidated("precise_location"), readings, literal="Yepocapa, 4800 ft.",
        named=[readings[1]], value=None, authority_id=None, cited=[], received=[])
    assert refused is not None and refused.reason == agreement.NOT_DECIDED


# The step, end to end.

def label_3(tmp_path, first=LABEL_3A, second=LABEL_3B, candidates=()):
    return build_rig(tmp_path, first, second, candidates=list(candidates))


def test_105526328s_date_and_method_settle_from_the_transcript_and_say_so(tmp_path):
    """Label 3's readers both write "IV-24-48" and "trap"; the organiser
    offered neither. Both settle, each with a transcript_literal finding and a
    label row whose record names the transcript as its basis. On origin/main
    both are unresolved."""
    rig = label_3(tmp_path)
    run = rig.specimen.run
    both = ["1A", "1B"]
    settle(rig, Scripted({
        "date_visited_from": answering(FieldAnswer(outcome="resolved", literal="IV-24-48", reading_names=both,
            value="1948-04-24", explanation="Both readers write the date.")),
        "collection_method": answering(FieldAnswer(outcome="resolved", literal="trap", reading_names=both,
            explanation="Both readers write it."))}))
    date, method = run.fields["date_visited_from"], run.fields["collection_method"]
    assert (date.state, date.literal, date.parsed) == (ValueState.SUPPORTED, "IV-24-48", "1948-04-24")
    assert (method.state, method.literal) == (ValueState.SUPPORTED, "trap")
    findings = {f.reason_code: f for f in run.findings}
    assert {"transcript_literal:date_visited_from", "transcript_literal:collection_method"} <= set(findings)
    finding = findings["transcript_literal:collection_method"]
    assert (finding.severity, finding.rule_id) == ("info", "transcript_literal")
    evidence = {item.id: item for item in run.evidence}
    rows = [evidence[i] for i in finding.evidence_ids]
    assert {row.kind for row in rows} == {"literal"} and all(row.source == "field_research" for row in rows)
    assert all(json.loads(rig.blobs.get(row.raw_ref))["basis"] == "transcript" for row in rows)
    assert all(row.excerpt == "trap" for row in rows)
    verify_evidence(rig.specimen, rig.blobs)


def test_a_label_row_for_text_from_the_transcript_cites_its_whole_word():
    """The row cites the line that writes "trap" as a word, not "trapping"
    above it, where the text first stands."""
    reading = Reading("1A", "r1", "o1a", "raw_reading", "trapping site\ntrap")
    assert field_step._literal_row("collection_method", reading, "trap", None, None, transcript=True).excerpt == "trap"
    assert field_step._literal_row("collection_method", reading, "trap", None, None).excerpt == "trapping site"


def test_the_trace_names_the_field_read_from_the_transcript_never_its_text(tmp_path, capfire):
    rig = label_3(tmp_path)
    settle(rig, Scripted({"collection_method": answering(FieldAnswer(outcome="resolved", literal="trap",
        reading_names=["1A", "1B"], explanation="Both readers write it."))}))
    [event] = [item for item in capfire.exporter.exported_spans_as_dict()
        if item["name"].startswith("field_research literal read from the transcript")]
    assert event["attributes"]["field_key"] == "collection_method"
    assert event["attributes"]["literal_basis"] == "transcript"
    assert json.loads(event["attributes"]["reading_names"]) == ["1A", "1B"]
    assert "trap" not in json.dumps(event["attributes"])


SPANISH_LABEL = "Yepocapa, 4800ft.\nIV-23-48\nR.D. Mitchell"


def test_text_from_the_transcript_that_another_kind_of_field_settles_goes_to_review(tmp_path):
    """105526329's locality: both readers write "Yepocapa, 4800ft.", whose
    "4800ft." the organiser gave as the elevation. The precise location read
    from the transcript whole would hold that elevation: the step sends it to
    review, naming the field. On origin/main it is unresolved as no
    candidate."""
    rig = label_3(tmp_path, SPANISH_LABEL, SPANISH_LABEL.replace("Mitchell", "mitchell"),
        [("elevation_from_ft", name, "4800ft.", "Yepocapa, 4800ft.") for name in ("1A", "1B")])
    run = rig.specimen.run
    settle(rig, Scripted({
        "elevation_from_ft": answering(resolved("4800ft.", value="4800")),
        "precise_location": answering(FieldAnswer(outcome="resolved", literal="Yepocapa, 4800ft.",
            reading_names=["1A", "1B"], explanation="Both readers write it."))}))
    place = run.fields["precise_location"]
    assert place.state == ValueState.UNRESOLVED
    assert place.reason == field_step.TAKEN.format(other="Elevation From (ft)") + " Both readers write it."
    assert run.fields["elevation_from_ft"].state == ValueState.SUPPORTED
    assert "transcript_literal:precise_location" not in [f.reason_code for f in run.findings]


def test_text_from_the_transcript_beside_another_kinds_text_settles(tmp_path):
    """A Costa Rican label: the locality before the comma, the elevation
    after it. Neither holds the other: the locality settles from the
    transcript. On origin/main it is unresolved as no candidate."""
    text = "Volc" + A_ACUTE + "n Barva, 2000 msnm\n15-VIII-1965"
    rig = label_3(tmp_path, text, text + "\nleg. anon.",
        [("elevation_from_m", name, "2000 msnm", "Volc" + A_ACUTE + "n Barva, 2000 msnm") for name in ("1A", "1B")])
    run = rig.specimen.run
    settle(rig, Scripted({"precise_location": answering(FieldAnswer(outcome="resolved",
        literal="Volc" + A_ACUTE + "n Barva", reading_names=["1A", "1B"], explanation="Both readers write it."))}))
    assert run.fields["precise_location"].state == ValueState.SUPPORTED
    assert "transcript_literal:precise_location" in [f.reason_code for f in run.findings]


@pytest.mark.parametrize(("key", "settles"), [
    # A collection code read from the transcript where the organiser placed the date.
    ("collection_code", False),
    # Verbatim D/T/S may hold the date: its meaning is an open museum question.
    ("verbatim_dts", True),
])
def test_text_the_organiser_placed_in_another_field(tmp_path, key, settles):
    """The organiser gave "IV-24-48" as the collecting date; another field's
    expert reads the same text from the transcript. The organiser's date
    settles either way; a field of another kind does not. On origin/main
    both are unresolved as no candidate."""
    rig = label_3(tmp_path, candidates=[("date_visited_from", name, "IV-24-48", "IV-24-48") for name in ("1A", "1B")])
    run = rig.specimen.run
    settle(rig, Scripted({
        "date_visited_from": answering(resolved("IV-24-48", value="1948-04-24")),
        key: answering(FieldAnswer(outcome="resolved", literal="IV-24-48", reading_names=["1A", "1B"],
            explanation="Read from the transcript."))}))
    assert run.fields["date_visited_from"].state == ValueState.SUPPORTED
    value = run.fields[key]
    if settles:
        assert value.state == ValueState.SUPPORTED
        return
    assert value.state == ValueState.UNRESOLVED
    assert value.reason.startswith(field_step.TAKEN.format(other="Date Visited From"))


def test_a_date_settled_before_or_quoted_unsettled_still_holds_its_text(tmp_path):
    """Another field's claim on the text need not be settled in this
    attempt: a date settled by an earlier attempt, or a date expert that
    quotes the text and cannot settle it, both hold "IV-24-48" against a
    collection code read from the transcript."""
    for earlier in (True, False):
        rig = label_3(tmp_path / str(earlier))
        run = rig.specimen.run
        region = run.regions[0].id
        scripts = {"collection_code": answering(FieldAnswer(outcome="resolved", literal="IV-24-48",
            reading_names=["1A", "1B"], explanation="Read from the transcript."))}
        if earlier:
            run.fields["date_visited_from"] = FieldValue(state=ValueState.SUPPORTED, literal="IV-24-48",
                parsed="1948-04-24", layer="settled", source_region_id=region)
        else:
            scripts["date_visited_from"] = answering(FieldAnswer(outcome="sources_cannot_resolve",
                literal="IV-24-48", reading_names=["1A"], explanation="Two possible years."))
        settle(rig, Scripted(scripts))
        code = run.fields["collection_code"]
        assert code.state == ValueState.UNRESOLVED
        assert code.reason.startswith(field_step.TAKEN.format(other="Date Visited From"))


def test_two_fields_that_read_the_same_text_from_the_transcript_both_go_to_review(tmp_path):
    rig = label_3(tmp_path)
    run = rig.specimen.run
    settle(rig, Scripted({key: answering(FieldAnswer(outcome="resolved", literal="IV-24-48",
        reading_names=["1A", "1B"], explanation="Read from the transcript."))
        for key in ("date_visited_from", "collection_code")}))
    assert run.fields["date_visited_from"].reason.startswith(field_step.TAKEN.format(other="Collection Code"))
    assert run.fields["collection_code"].reason.startswith(field_step.TAKEN.format(other="Date Visited From"))


def test_a_province_read_from_the_transcript_one_letter_off_settles_on_g34(tmp_path):
    """105526330's spelling with no organiser candidate: both readers write
    "Chimaltenago", Getty TGN's department is one letter off, and the
    country above it, settled for the reading, is its parent. On origin/main
    the province is unresolved as no candidate."""
    places = dict(country="Guatemala", province_state="Chimaltenago", county=None, city=None)
    rig = build_rig(tmp_path, label_with(**places), label_with(**places).replace("J. Smith", "J. Smyth"),
        candidates=[("country", name, "Guatemala", "country: Guatemala") for name in ("1A", "1B")])
    run = rig.specimen.run
    settle(rig, Scripted({"country": from_tgn("Guatemala", "Guatemala", None, "tgn:7005493"),
        "province_state": from_tgn("Chimaltenango", "Chimaltenago", "Chimaltenango", "tgn:1000565"),
        **dict.fromkeys(("county", "city"), answering(LACKS))}), tools=Gazetteer(rig.blobs))
    province = run.fields["province_state"]
    assert (province.state, province.literal, province.normalized) == (
        ValueState.SUPPORTED, "Chimaltenago", "Chimaltenango")
    codes = [f.reason_code for f in run.findings]
    assert "near_spelling:province_state" in codes and "transcript_literal:province_state" in codes


def test_a_country_read_from_the_transcript_is_the_country_its_places_lie_in(tmp_path):
    """A Guatemalan label whose organiser missed the country: both readers
    write "Guatemala", Getty TGN settles it, and the department below it is
    checked against it (step._misfit). On origin/main the country is
    unresolved, and the department finds no country (NO_COUNTRY)."""
    places = dict(country="Guatemala", province_state="Chimaltenango", county=None, city=None)
    rig = build_rig(tmp_path, label_with(**places), label_with(**places).replace("J. Smith", "J. Smyth"),
        candidates=[("province_state", name, "Chimaltenango", "province_state: Chimaltenango")
            for name in ("1A", "1B")])
    run = rig.specimen.run
    settle(rig, Scripted({"country": from_tgn("Guatemala", "Guatemala", None, "tgn:7005493"),
        "province_state": from_tgn("Chimaltenango", "Chimaltenango", None, "tgn:1000565"),
        **dict.fromkeys(("county", "city"), answering(LACKS))}), tools=Gazetteer(rig.blobs))
    country, province = run.fields["country"], run.fields["province_state"]
    assert (country.state, country.authority_id) == (ValueState.SUPPORTED, "tgn:7005493")
    assert (province.state, province.authority_id) == (ValueState.SUPPORTED, "tgn:1000565")
    assert "transcript_literal:country" in [f.reason_code for f in run.findings]


# ---- a doubtful genus on any reader of a label with no decided transcript ----
# The sixth review's probe 3 (readers disagreeing on "cf."): 1A writes "cf.
# Epipsocus sp. 1", 1B "Epipsocus sp. 1", and an answer naming only 1B settled
# the genus. On origin/main its record went to review only because its other
# fields had no candidate; once they settle from the transcript, the taxon
# would clear.

@pytest.mark.parametrize("doubtful", ["cf. Epipsocus sp. 1", "? Epipsocus sp. 1", "aff. Epipsocus sp. 1"],
    ids=["cf", "question-mark", "aff"])
def test_one_readers_doubt_holds_the_genus_whichever_reader_is_named(doubtful):
    """On origin/main the answer naming 1B passes."""
    literal = "Epipsocus sp. 1"
    readings = label(doubtful + "\nleg. J. Smith", literal + "\nleg. J. Smith", names=("1A", "1B"), region="r1")
    task = FieldTask("taxon", True, FieldValue(state=ValueState.SUPPORTED, literal=literal),
        (Candidate("1A", doubtful, literal, "ev-1A"), Candidate("1B", literal, literal, "ev-1B")), FIELD_TOOLS["taxon"])
    refused = agreement.refusal(task, readings, literal=literal, named=[readings[1]], value=None, authority_id=None,
        cited=[], received=[])
    assert refused is not None and refused.reason == agreement.DOUBTFUL_GENUS


def test_a_decided_clean_transcript_still_decides_beside_a_doubtful_reader():
    """The control, unchanged (G19): the decided reading writes no doubt, and
    the other reader's "cf." is evidence only."""
    literal = "Epipsocus sp. 1"
    readings = label(literal + "\nleg. J. Smith", "cf. Epipsocus sp. 1\nleg. J. Smith", decided=True,
        names=("1A", "1B"), region="r1")
    task = FieldTask("taxon", True, FieldValue(state=ValueState.SUPPORTED, literal=literal),
        (Candidate("1A", literal, literal, "ev-1A"),), FIELD_TOOLS["taxon"])
    assert agreement.refusal(task, readings, literal=literal, named=[readings[0]], value=None, authority_id=None,
        cited=[], received=[]) is None


# ---- PR #300's review: readers that write more words around the text ---------
# Blocking finding 1: 3A "trap" and 3B "light trap" settled the method on
# "trap", because 3B's "light trap" writes "trap" as a run of whole words; the
# same readers with each reader's text as its candidate refuse (DIFFER). The
# clause of each reader's line that holds the text (between commas or
# semicolons, else the whole line) must now agree, letter case and spacing
# aside.

AROUND = {
    # The review's four cases.
    "trap-beside-light-trap": ("collection_method", "trap", "light trap"),
    "yepocapa-beside-near-yepocapa": ("precise_location", "Yepocapa", "near Yepocapa"),
    "forest-beside-cloud-forest": ("habitat", "forest", "cloud forest"),
    "date-beside-a-date-range": ("date_visited_from", "IV-24-48", "IV-24-48 to V-2-48"),
    # Spanish, French and Portuguese.
    "spanish-cerca-de": ("precise_location", "Yepocapa", "cerca de Yepocapa"),
    "french-piege-lumineux": ("collection_method", "pi" + E_GRAVE + "ge", "pi" + E_GRAVE + "ge lumineux"),
    "portuguese-mata-atlantica": ("habitat", "mata", "mata atl" + A_CIRCUMFLEX + "ntica"),
}


@pytest.mark.parametrize(("key", "first", "second"), AROUND.values(), ids=AROUND)
def test_readers_that_write_more_words_around_the_text_disagree(key, first, second):
    """On 61c193e93 each settles on the first reader's text."""
    readings = label(first + "\nleg. J. Smith", second + "\nleg. J. Smith")
    refused = agreement.refusal(uncandidated(key), readings, literal=first, named=[readings[0]], value=None,
        authority_id=None, cited=[], received=[])
    assert refused is not None and (refused.reason, refused.differ) == (agreement.DIFFER, True)
    assert repr(collapse(second)) in refused.retry


@pytest.mark.parametrize("names", [("3A", "3B"), ("3A",)], ids=["both-named", "first-named"])
def test_the_review_probe_trap_beside_light_trap_refuses_however_the_readers_are_named(names):
    readings = label("trap\nleg. J. Smith", "light trap\nleg. J. Smith")
    refused = agreement.refusal(uncandidated("collection_method"), readings, literal="trap",
        named=[r for r in readings if r.name in names], value=None, authority_id=None, cited=[], received=[])
    assert refused is not None and refused.reason == agreement.DIFFER


@pytest.mark.parametrize(("first", "second", "literal"), [
    # 105526328's municipality line: the clause holding "Yepocapa" is the same.
    (LABEL_3A, LABEL_3B, "Yepocapa"),
    # A Costa Rican line whose readers space the comma differently.
    ("Volc" + A_ACUTE + "n Barva, 2000 msnm", "Volc" + A_ACUTE + "n Barva,2000 msnm", "Volc" + A_ACUTE + "n Barva"),
    # Case and spacing aside, the clause is one.
    ("Mossy forest, 6400'", "mossy  Forest, 6400'", "Mossy forest"),
], ids=["328-municipality-clause", "spanish-comma-spacing", "case-and-spacing"])
def test_readers_whose_clauses_holding_the_text_agree_settle(first, second, literal):
    """The control: unchanged from 61c193e93."""
    readings = label(first, second)
    assert agreement.refusal(uncandidated("precise_location" if "Barva" in literal else "habitat"), readings,
        literal=literal, named=[readings[0]], value=None, authority_id=None, cited=[], received=[]) is None


@pytest.mark.parametrize(("key", "first", "second"), list(AROUND.values())[:4], ids=list(AROUND)[:4])
def test_through_the_step_readers_that_write_more_words_go_to_review(tmp_path, key, first, second):
    """The review's four cases end to end; on 61c193e93 each field is
    supported on the first reader's text, and the second reader's verbatim is
    recorded as that text."""
    rig = build_rig(tmp_path, first + "\nleg. J. Smith", second + "\nleg. J. Smith", candidates=[])
    run = rig.specimen.run
    settle(rig, Scripted({key: answering(FieldAnswer(outcome="resolved", literal=first, reading_names=["1A"],
        explanation="Read from the readings."))}))
    value = run.fields[key]
    assert (value.state, value.literal) == (ValueState.AMBIGUOUS, None)
    assert value.reason.startswith(agreement.DIFFER)
    assert f"transcript_literal:{key}" not in [f.reason_code for f in run.findings]


def test_the_review_probe_p13_trap_and_light_trap_naming_both_readers(tmp_path):
    rig = build_rig(tmp_path, "trap\nleg. J. Smith", "light trap\nleg. J. Smith", candidates=[])
    run = rig.specimen.run
    settle(rig, Scripted({"collection_method": answering(FieldAnswer(outcome="resolved", literal="trap",
        reading_names=["1A", "1B"], explanation="Both write it."))}))
    method = run.fields["collection_method"]
    assert (method.state, method.literal) == (ValueState.AMBIGUOUS, None)


# Not blocking 2: the overlap guard was attempt-local. With the elevation
# expert failing, "Yepocapa, 4800ft." cleared as the locality; the organiser's
# candidate "4800ft." for the elevation now claims its text whatever the
# elevation's expert did.

@pytest.mark.parametrize("elevation", ["fails", "lacks"])
def test_an_organiser_candidate_claims_its_text_when_its_expert_settles_nothing(tmp_path, elevation):
    """On 61c193e93 the locality is supported."""
    rig = label_3(tmp_path, SPANISH_LABEL, SPANISH_LABEL.replace("Mitchell", "mitchell"),
        [("elevation_from_ft", name, "4800ft.", "Yepocapa, 4800ft.") for name in ("1A", "1B")])
    run = rig.specimen.run
    settle(rig, Scripted({
        "elevation_from_ft": failing("timeout") if elevation == "fails" else answering(LACKS),
        "precise_location": answering(FieldAnswer(outcome="resolved", literal="Yepocapa, 4800ft.",
            reading_names=["1A", "1B"], explanation="Both readers write it."))}))
    place = run.fields["precise_location"]
    assert place.state == ValueState.UNRESOLVED
    assert place.reason.startswith(field_step.TAKEN.format(other="Elevation From (ft)"))


# Not blocking 3: a date or an elevation read from the transcript is never one
# end of a range its line writes ("to", "-", an en dash or "a" between two
# words that hold digits).

RANGE_ENDS = {
    "date-to-end": ("date_visited_from", "IV-24-48 to V-2-48", "V-2-48"),
    "date-to-start": ("date_visited_from", "IV-24-48 to V-2-48", "IV-24-48"),
    "date-hyphen-end": ("date_visited_from", "IV-24-48 - V-2-48", "V-2-48"),
    "date-capital-to": ("date_visited_to", "IV-24-48 TO V-2-48", "V-2-48"),
    "spanish-date-a": ("date_visited_from", "10 a 15-VIII-1965", "15-VIII-1965"),
    "elevation-to": ("elevation_from_m", "1200 to 1500 m", "1500 m"),
    "spanish-elevation-a": ("elevation_to_m", "1200 a 1500 m", "1500 m"),
    "elevation-en-dash": ("elevation_from_m", "1200 \N{EN DASH} 1500 m", "1500 m"),
    "imperial-elevation-to": ("elevation_from_ft", "4000 to 4800 ft.", "4800 ft."),
}


@pytest.mark.parametrize(("key", "line", "literal"), RANGE_ENDS.values(), ids=RANGE_ENDS)
def test_one_end_of_a_range_is_never_read_from_the_transcript(key, line, literal):
    """On 61c193e93 each is accepted."""
    readings = label(line + "\nleg. J. Smith")
    refused = agreement.refusal(uncandidated(key), readings, literal=literal, named=list(readings), value=None,
        authority_id=None, cited=[], received=[])
    assert refused is not None and refused.reason == agreement.PART_OF_RANGE


def test_a_foot_mark_left_off_is_still_feet_to_the_written_rules():
    """Edge characters may be left off a run, but extraction_refusal still
    reads the reading: "6400" of "Elev. 6400'" is no elevation in metres."""
    readings = label("Mossy forest, Elev. 6400'\nleg. J. Smith")
    assert agreement.verbatim_runs(readings[0].text, "6400")
    with pytest.raises(ModelRetry):
        checked(uncandidated("elevation_from_m"), readings, dict(outcome="resolved", literal="6400",
            reading_names=["3A", "3B"]))


def test_the_experts_check_sends_a_range_end_back():
    """The review's probe: "V-2-48" as date_visited_from 1948-05-02 passed the
    expert's check on 61c193e93."""
    readings = label("IV-24-48 to V-2-48\nleg. J. Smith")
    with pytest.raises(ModelRetry, match="one end of a range"):
        checked(uncandidated("date_visited_from"), readings, dict(outcome="resolved", literal="V-2-48",
            reading_names=["3A", "3B"], value="1948-05-02"), checks=[("parse_date", "V-2-48")])


@pytest.mark.parametrize(("key", "line", "literal"), [
    # The whole range keeps today's handling.
    ("elevation_from_m", "1200 to 1500 m", "1200 to 1500 m"),
    # A range in another clause of the line.
    ("elevation_from_ft", "Yepocapa, 4800 ft., IV-24-48 to V-2-48", "4800 ft."),
    # "a" that joins no two numbers (Spanish "at").
    ("elevation_from_m", "Mata a 1200 m", "1200 m"),
    # A field that is no date or elevation.
    ("collection_code", "IV-24-48 to V-2-48", "V-2-48"),
], ids=["whole-range", "range-in-another-clause", "a-joining-no-numbers", "not-a-date-field"])
def test_text_beside_or_holding_a_whole_range_is_not_cut_from_it(key, line, literal):
    """The control: unchanged from 61c193e93."""
    readings = label(line + "\nleg. J. Smith")
    assert agreement.refusal(uncandidated(key), readings, literal=literal, named=list(readings), value=None,
        authority_id=None, cited=[], received=[]) is None


# PR #300's review of 6fd595b3b, finding 1: the range guard knew only "to",
# "-", an en dash and "a" standing as words between two words with digits.
# Ranges are written in many languages, with every form of dash, with a dash
# touching one end, and with a unit or a month between a number and the
# joiner (written.RANGE_WORDS, RANGE_SIGNS, DASHES, BESIDE_A_NUMBER).

RANGES_IN_ANY_LANGUAGE = {
    # Elevations: France, Germany, Spain and Latin America, Brazil, Italy, the Netherlands.
    "french-a-grave": ("elevation_from_m", "1200 \N{LATIN SMALL LETTER A WITH GRAVE} 1500 m", "1500 m"),
    "german-bis": ("elevation_from_m", "H\N{LATIN SMALL LETTER O WITH DIAERESIS}he 1200 bis 1500 m", "1500 m"),
    "spanish-hasta": ("elevation_to_m", "desde 1200 hasta 1500 m", "1500 m"),
    "spanish-entre-y": ("elevation_from_m", "entre 1200 y 1500 msnm", "1500 msnm"),
    "portuguese-ate": ("elevation_from_m", "1200 at\N{LATIN SMALL LETTER E WITH ACUTE} 1500 m", "1500 m"),
    "italian-fino-a": ("elevation_from_m", "da 1200 fino a 1500 m s.l.m.", "1500 m s.l.m."),
    "dutch-tot": ("elevation_from_m", "van 1200 tot 1500 m", "1500 m"),
    "latin-ad": ("elevation_from_m", "1200 ad 1500 m", "1500 m"),
    "english-and": ("elevation_from_m", "between 1200 and 1500 m", "1500 m"),
    "ampersand": ("elevation_from_m", "1200 & 1500 m", "1500 m"),
    # Every dash, standing alone or touching one end.
    "em-dash": ("elevation_from_m", "1200 \N{EM DASH} 1500 m", "1500 m"),
    "minus-sign": ("elevation_from_m", "1200 \N{MINUS SIGN} 1500 m", "1500 m"),
    "figure-dash": ("elevation_from_m", "1200 \N{FIGURE DASH} 1500 m", "1500 m"),
    "fullwidth-hyphen": ("elevation_from_m", "1200 \N{FULLWIDTH HYPHEN-MINUS} 1500 m", "1500 m"),
    "japanese-wave-dash": ("elevation_from_m", "1200 \N{WAVE DASH} 1500 m", "1500 m"),
    "hyphen-touching-the-first": ("elevation_from_m", "1200- 1500 m", "1500 m"),
    "hyphen-touching-the-second": ("elevation_from_m", "1200 -1500 m", "1500 m"),
    # A unit on both ends, either end taken.
    "units-on-both-ends": ("elevation_from_m", "1200 m to 1500 m", "1500 m"),
    "units-on-both-ends-first": ("elevation_from_m", "1200 m - 1500 m", "1200 m"),
    "feet-on-both-ends": ("elevation_from_ft", "4000 ft to 4800 ft", "4000 ft"),
    # Dates: French, German, English and Spanish joiners, a slash, a dash touching one end.
    "french-au": ("date_visited_from", "IV-24-48 au V-2-48", "V-2-48"),
    "german-bis-date": ("date_visited_to", "24.IV.1948 bis 2.V.1948", "2.V.1948"),
    "english-thru": ("date_visited_from", "IV-24-48 thru V-2-48", "V-2-48"),
    "ampersand-date": ("date_visited_from", "IV-24-48 & V-2-48", "V-2-48"),
    "slash-date": ("date_visited_from", "IV-24-48 / V-2-48", "V-2-48"),
    "dash-touching-the-second-date": ("date_visited_from", "IV-24-48 -V-2-48", "V-2-48"),
    "dash-touching-the-first-date": ("date_visited_from", "IV-24-48- V-2-48", "IV-24-48"),
    "spanish-al-days": ("date_visited_from", "24 al 30-IV-1948", "30-IV-1948"),
    # A month between the number and the joiner, in English and in French.
    "english-month-names": ("date_visited_from", "April 24 to May 2, 1948", "May 2, 1948"),
    "french-month-names": ("date_visited_from", "24 avril au 2 mai 1948", "2 mai 1948"),
    # A day range glued in one word, right before the month and year.
    "glued-day-range": ("date_visited_from", "10-12 Sept. 1946", "Sept. 1946"),
    "glued-slash-day-range": ("date_visited_from", "24/30 IV 1948", "IV 1948"),
}


@pytest.mark.parametrize(("key", "line", "literal"), RANGES_IN_ANY_LANGUAGE.values(), ids=RANGES_IN_ANY_LANGUAGE)
def test_one_end_of_a_range_in_any_language_is_never_read_from_the_transcript(key, line, literal):
    """On 6fd595b3b each is accepted."""
    readings = label(line + "\nleg. J. Smith")
    refused = agreement.refusal(uncandidated(key), readings, literal=literal, named=list(readings), value=None,
        authority_id=None, cited=[], received=[])
    assert refused is not None and refused.reason == agreement.PART_OF_RANGE


def test_the_experts_check_sends_back_a_range_end_joined_in_german():
    """The expert's own check, with parse_date run on the end: on 6fd595b3b it
    keeps "2.V.1948" as the start of "24.IV.1948 bis 2.V.1948"."""
    readings = label("Bayern, 24.IV.1948 bis 2.V.1948\nleg. J. Schmidt")
    with pytest.raises(ModelRetry, match="one end of a range"):
        checked(uncandidated("date_visited_from"), readings, dict(outcome="resolved", literal="2.V.1948",
            reading_names=["3A", "3B"], value="1948-05-02"), checks=[("parse_date", "2.V.1948")])


@pytest.mark.parametrize(("key", "line", "literal"), [
    # One elevation written in both units is no range.
    ("elevation_from_ft", "4800 ft. / 1463 m", "4800 ft."),
    ("elevation_from_m", "4800 ft. / 1463 m", "1463 m"),
    # Dashes and slashes between fields of different kinds join no range.
    ("elevation_from_m", "Guatemala / 1200 m / 24.IV.1948", "1200 m"),
    ("date_visited_from", "Guatemala / 1200 m / 24.IV.1948", "24.IV.1948"),
    ("date_visited_from", "Yepocapa - 1200 m - IV-24-48", "IV-24-48"),
    # A range of the other field in another clause.
    ("elevation_from_m", "alt. 1200 m, 24 al 30-IV-1948", "1200 m"),
    # Spanish "a" and Italian "e" joining no two numbers.
    ("elevation_from_m", "camino a Yepocapa, 1200 m", "1200 m"),
    ("date_visited_from", "Lago di Garda e dintorni 24.VI.1952", "24.VI.1952"),
    # Whole ranges, in Spanish and German, keep the rules a candidate has.
    ("elevation_from_m", "1200 a 1500 m", "1200 a 1500 m"),
    ("date_visited_from", "24.IV.1948 bis 2.V.1948", "24.IV.1948 bis 2.V.1948"),
], ids=["feet-beside-metres", "metres-beside-feet", "slash-separated-elevation", "slash-separated-date",
    "dash-separated-date", "range-in-another-clause", "spanish-a-before-a-word", "italian-e-between-words",
    "whole-spanish-range", "whole-german-range"])
def test_text_beside_a_joiner_that_joins_no_range_settles(key, line, literal):
    """The control: each settles, as on 6fd595b3b."""
    readings = label(line + "\nleg. J. Smith")
    assert agreement.refusal(uncandidated(key), readings, literal=literal, named=list(readings), value=None,
        authority_id=None, cited=[], received=[]) is None
