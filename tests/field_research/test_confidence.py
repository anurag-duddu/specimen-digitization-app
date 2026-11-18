"""Confident or flagged (field_research/confidence.py, lane Q1 of the autonomy program).

Each rule flags a settled value something in the run argues against, and leaves a value nothing
argues against confident. The labels are the stored runs' (`~/specimen-golive/runs/`, the 100 truth
slides) cut to the lines that matter; each case names its slide.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.application.reading_units import ReadingUnit, ReadingUnits, UnitText
from specimen_digitization.field_research import confidence
from specimen_digitization.field_research.contracts import Reading
from specimen_digitization.field_research.step import marked_reasons

RULES = published_registry().profiles[0].date_rules
LABEL = "L1"


def readings(*texts, units=None):
    """One label's readings, 1A, 1B, ...; with `units` (each a list of (one text per reader, fields)),
    its reading units, each reader's text found in its reading in order."""
    names = [f"1{chr(65 + i)}" for i in range(len(texts))]
    built = None
    if units is not None:
        at = [0] * len(texts)
        found = []
        for number, (parts, fields) in enumerate(units, 1):
            readers = {}
            for i, part in enumerate(parts):
                start = texts[i].index(part, at[i]) if part else at[i]
                readers[f"o{names[i]}"] = UnitText(text=part, start=start, end=start + len(part))
                at[i] = start + len(part)
            found.append(ReadingUnit(id=f"{LABEL}:{number}", label=LABEL, lines=(1, 1), readers=readers,
                image=next(p for p in parts if p), fields=list(fields)))
        built = ReadingUnits(label=LABEL, units=found)
    return tuple(Reading(name, LABEL, f"o{name}", "raw_reading", text, units=built) for name, text in zip(names, texts))


def value(literal, *, layer="settled", **more):
    return FieldValue(state=ValueState.SUPPORTED, literal=literal, layer=layer, source_region_id=LABEL, **more)


def groups(group):
    return {LABEL: list(group)}


def review(fields, group, findings=()):
    run = SimpleNamespace(fields=fields, evidence=[], findings=list(findings))
    confidence.review(run, readings=group, date_rules=RULES)
    return run, sorted(marked_reasons(run))


# ---- rule 1: the readers differ and the image alone chose --------------------------------------

def test_a_date_the_readers_differ_on_is_flagged_and_names_the_reading_taken():
    """105526392: 2A writes "24-VII-1916", 2B "24-VI-1916"; the image named 2A's. Today it clears."""
    group = readings("NEOTOMA\n24-VII-1916\ncol RRP", "NEOTOMA\n24-VI-1916\ncol RRP")
    sentence = confidence.readers_differ("date_visited_from", value("24-VII-1916"), groups(group))
    assert sentence is not None and "1A's text '24-VII-1916'" in sentence and "reading 1B does not" in sentence


@pytest.mark.parametrize(("first", "second"), [
    ("12 mi. N, 5 mi. E", "12mi. N, 5mi. E"),          # spacing (105526632)
    ("E. Brundage Jr.COLL.", "E. Brundage Jr. COLL."),  # spacing (105526822)
    ("Coyhaique", "Coyha\u00efque"),                   # an accent (105526522)
    ("Ex. Blarina brevicauda \u2642", "Ex. Blarina brevicauda"),  # a sex sign
])
def test_readers_that_differ_only_in_spacing_punctuation_or_accents_agree(first, second):
    group = readings(first, second)
    assert confidence.readers_differ("precise_location", value(first), groups(group)) is None


def test_a_value_both_readers_write_stays_confident():
    """105527047: both readers write "28- III -1974" (spacing aside): nothing in the row argues."""
    group = readings("28- III -1974\ncol R.E. MARTIN", "28- III-1974\ncol R.E. MARTIN")
    assert confidence.readers_differ("date_visited_from", value("28- III -1974"), groups(group)) is None


def test_a_source_that_decides_or_a_place_record_keeps_it_confident():
    group = readings("Kunduz", "Kundus")
    decided = value("Kunduz", evidence_ids=["e1"], evidence_relations={"e1": "decides"})
    assert confidence.readers_differ("taxon", decided, groups(group)) is None
    assert confidence.readers_differ("province_state", value("Kunduz", authority_id="tgn:1"), groups(group)) is None
    assert confidence.readers_differ("precise_location", value("Kunduz", authority_id="tgn:1"), groups(group))


def test_a_label_a_person_transcribed_is_never_flagged_for_its_readers():
    first, second = readings("24-VII-1916", "24-VI-1916")
    person = Reading("1A", LABEL, "o1A", "decided_transcript", "24-VII-1916", person_decided=True)
    assert confidence.readers_differ("date_visited_from", value("24-VII-1916"), groups((person, second))) is None
    assert confidence.readers_differ("date_visited_from", value("24-VII-1916"), groups((first, second)))


def test_a_value_whose_letters_are_a_part_of_a_longer_word_is_not_written():
    """Whole tokens only: "VI" is not written by "VII"."""
    assert not confidence.writes("24-VII-1916", "24-VI")
    assert confidence.writes("24-VII-1916", "24 VII")


# ---- rule 2: a derived value follows a marked one ----------------------------------------------

def test_a_date_derived_from_a_flagged_date_is_flagged_with_it():
    """105526355: Date Visited To derived from a From the readers differ on ("5-VII-1940", "5-VI-1940")."""
    group = readings("5-VII-1940", "5-VI-1940")
    fields = {"date_visited_from": value("5-VII-1940", parsed="1940-07-05"),
        "date_visited_to": FieldValue(state=ValueState.SUPPORTED, parsed="1940-07-05", layer="derived",
            derived_from=["date_visited_from"])}
    run, reasons = review(fields, group)
    assert reasons == ["marked:date_visited_from:L1:readers_differ", "marked:date_visited_to:L1:follows_marked"]
    assert run.fields["date_visited_to"].parsed == "1940-07-05"


def test_a_value_derived_from_a_confident_one_stays_confident():
    group = readings("5-VI-1940", "5-VI-1940")
    fields = {"date_visited_from": value("5-VI-1940", parsed="1940-06-05"),
        "date_visited_to": FieldValue(state=ValueState.SUPPORTED, parsed="1940-06-05", layer="derived",
            derived_from=["date_visited_from"])}
    assert review(fields, group)[1] == []


def test_a_field_marked_already_gets_no_second_mark_and_its_derived_value_follows_it():
    from specimen_digitization.application.domain import RunFinding

    group = readings("5-VII-1940", "5-VI-1940")
    earlier = RunFinding(rule_id="field_settlement", rule_version="v", severity="warning",
        field_key="date_visited_from", reason_code="marked:date_visited_from:L1:text_only")
    fields = {"date_visited_from": value("5-VII-1940"), "date_visited_to": FieldValue(state=ValueState.SUPPORTED,
        parsed="1940-07-05", layer="derived", derived_from=["date_visited_from"])}
    assert review(fields, group, [earlier])[1] == [
        "marked:date_visited_from:L1:text_only", "marked:date_visited_to:L1:follows_marked"]


def test_a_person_s_field_is_never_flagged():
    group = readings("5-VII-1940", "5-VI-1940")
    run = SimpleNamespace(fields={"date_visited_from": value("5-VII-1940")}, evidence=[], findings=[])
    confidence.review(run, readings=group, human={"date_visited_from"}, date_rules=RULES)
    assert marked_reasons(run) == []


# ---- rule 3: the extent -----------------------------------------------------------------------

def test_a_host_cut_inside_its_unit_is_flagged_with_the_fuller_text():
    """105526617: "ex Peromyscus" settled from the unit "ex Peromyscus\\nleucopus"."""
    text = "RMT 1149\nex Peromyscus\nleucopus"
    group = readings(text, text, units=[(("RMT 1149",) * 2, ["collection_code"]),
        (("ex Peromyscus\nleucopus",) * 2, [])])
    sentence = confidence.extent("habitat", value("ex Peromyscus"), groups(group))
    assert sentence is not None and "'ex Peromyscus\\nleucopus'" in sentence


def test_a_host_genus_whose_species_is_the_next_line_alone_is_flagged():
    """105527218: "Meriones" then "LIBYCUS", one unit each; "Siphonaptera" (105526741) is no species."""
    text = "Host:\nMeriones\nLIBYCUS\nAlc. Skin"
    units = [(("Host:",) * 2, []), (("Meriones",) * 2, []), (("LIBYCUS",) * 2, []), (("Alc. Skin",) * 2, [])]
    assert confidence.extent("habitat", value("Meriones"), groups(readings(text, text, units=units)))
    heading = "On Marmot\nSiphonaptera"
    units = [(("On Marmot",) * 2, []), (("Siphonaptera",) * 2, [])]
    assert confidence.extent("habitat", value("On Marmot"), groups(readings(heading, heading, units=units))) is None


def test_a_whole_unit_value_followed_by_other_text_stays_confident():
    text = "Meriones ZARUDNYI\nAlc. Skin Fresh x"
    units = [(("Meriones ZARUDNYI",) * 2, []), (("Alc. Skin Fresh x",) * 2, [])]
    assert confidence.extent("habitat", value("Meriones ZARUDNYI"), groups(readings(text, text, units=units))) is None


def test_a_locality_after_its_higher_place_line_is_flagged():
    """105527218: "27 km. north of Kunduz" after "Loc: AFGHANISTAN,", which the first pass advises for the
    locality; 105526996: "TRAPPIST MONASTERY" after "SANTIAGO PROV.," on the same line."""
    text = "Host Data\nLoc: AFGHANISTAN,\n27 km. north of Kunduz\n549 m."
    units = [(("Host Data",) * 2, []), (("Loc: AFGHANISTAN,",) * 2, ["country", "precise_location"]),
        (("27 km. north of Kunduz",) * 2, ["precise_location"]), (("549 m.",) * 2, ["elevation_from_m"])]
    assert confidence.extent("precise_location", value("27 km. north of Kunduz"), groups(readings(text, text, units=units)))
    text = "CHILE: SANTIAGO\nPROV., TRAPPIST\nMONASTERY\n27-IV-1976"
    units = [(("CHILE:",) * 2, ["country"]), (("SANTIAGO\nPROV.,",) * 2, ["province_state"]),
        (("TRAPPIST\nMONASTERY",) * 2, ["precise_location"]), (("27-IV-1976",) * 2, ["date_visited_from"])]
    assert confidence.extent("precise_location", value("TRAPPIST\nMONASTERY"), groups(readings(text, text, units=units)))


def test_a_whole_locality_between_a_heading_and_a_date_stays_confident():
    text = "LEWIS COLLECTION\nAFGHANISTAN,\n27 km. north of Kunduz\n24-VIII-1965"
    units = [(("LEWIS COLLECTION",) * 2, ["collection_code"]), (("AFGHANISTAN,\n27 km. north of Kunduz",) * 2,
        ["country", "precise_location"]), (("24-VIII-1965",) * 2, ["date_visited_from"])]
    whole = value("AFGHANISTAN,\n27 km. north of Kunduz")
    assert confidence.extent("precise_location", whole, groups(readings(text, text, units=units))) is None


def test_a_heading_kept_in_the_value_or_a_role_word_in_a_name_is_flagged():
    """105526760 "HOST: coyote"; the "Loc:" localities; 105526822 "E. Brundage Jr.COLL."."""
    assert confidence.extent("habitat", value("HOST: coyote"), {})
    assert confidence.extent("precise_location", value("Loc: AFGHANISTAN,\nPAGHMAN"), {})
    assert confidence.extent("collectors", value("E. Brundage Jr.COLL."), {})
    assert confidence.extent("collectors", value("W.E. Eiqsti. COLL"), {})
    assert confidence.extent("precise_location", value("CHILE: SANTIAGO PROV."), {}) is None
    assert confidence.extent("collectors", value("R.E. MARTIN"), {}) is None


def test_a_role_word_beside_the_name_in_its_unit_is_no_more_of_it():
    """105526647: "M. BOSCH" from the unit "col M. BOSCH": the value is the whole name."""
    text = "col M. BOSCH\n12-IV-1976"
    units = [(("col M. BOSCH",) * 2, ["collectors"]), (("12-IV-1976",) * 2, ["date_visited_from"])]
    assert confidence.extent("collectors", value("M. BOSCH"), groups(readings(text, text, units=units))) is None


def test_a_genus_alone_on_a_label_that_writes_its_species_is_flagged():
    """105527218: the taxon "Xenopsylla" where the label writes "C. CONFORMIS" (the addition to rule 3)."""
    text = "Xenopsylla\nC. CONFORMIS\n(WAGN., 1903)"
    units = [(("Xenopsylla",) * 2, ["taxon"]), (("C. CONFORMIS",) * 2, ["taxon"]), (("(WAGN., 1903)",) * 2, ["taxon"])]
    assert confidence.extent("taxon", value("Xenopsylla"), groups(readings(text, text, units=units)))
    alone = "Xenopsylla\nHost: Meriones"
    units = [(("Xenopsylla",) * 2, ["taxon"]), (("Host: Meriones",) * 2, ["habitat"])]
    assert confidence.extent("taxon", value("Xenopsylla"), groups(readings(alone, alone, units=units))) is None


# ---- rule 4: conventions -----------------------------------------------------------------------

@pytest.mark.parametrize(("key", "text", "literal"), [
    ("city", "12 mi. N, 5 mi. E\nShidler, Osage\nCo., Oklahoma", "Shidler,"),        # 105526631
    ("city", "\u00bdmi.S,2\u00bdmi.E\nCottonwood,\nJackson Co.,", "Cottonwood,"),       # 105526636
    ("city", "14.5 km NNW\nPuerto Octay\n(Osorno)", "Puerto Octay"),                    # 105526536
    ("province_state", "Loc: AFGHANISTAN,\n27 km. north of Kunduz", "Kunduz"),          # 105527218
])
def test_a_town_named_only_as_a_distance_s_origin_is_flagged(key, text, literal):
    assert confidence.distance_origin(key, value(literal), groups(readings(text, text)))


def test_a_town_written_as_a_place_of_its_own_stays_confident():
    text = "12 mi. N of Shidler\nShidler, Osage Co."
    assert confidence.distance_origin("city", value("Shidler"), groups(readings(text, text))) is None
    plain = "Shidler, Osage\nCo., Oklahoma\n30 May 1972"
    assert confidence.distance_origin("city", value("Shidler"), groups(readings(plain, plain))) is None
    assert confidence.distance_origin("precise_location", value("Shidler"),
        groups(readings("5 mi. E Shidler",) * 2)) is None


@pytest.mark.parametrize(("literal", "flagged"), [
    ("LEWIS COLLECTION", False), ("LEWIS\nCOLLECTION", False), ("FM SUB.563", True), ("FMA 8 SUB. 664", True),
    ("RMT 1149", True), ("1X-17-66-1", True),
])
def test_only_the_ruled_heading_is_a_collection_code(literal, flagged):
    assert bool(confidence.not_collection_code("collection_code", value(literal, layer="verbatim"))) is flagged


@pytest.mark.parametrize(("literal", "flagged"), [
    ("1X-14-46", True),               # an exact day, a digit one for the I (105526325)
    ("3 sept. '46", True),            # an exact day
    ("17.Mar.1934 10:30", True),      # Codex on PR #453: an exact date with a clock time
    ("6-Sept.-1946 4 p.m.", True),
    ("1916 IV-29-68-4", True),        # Codex on PR #453: a slide code as a part of the literal
    ("IX-3-66-10", True),
    ("VI.'41", False), ("XI.'46", False), ("1916", False), ("III.87", False), ("Nov, Dec 1955", False),
    ("XII-1970 I-1971", False), ("July-Aug. 1950", False),
])
def test_verbatim_dts_holds_only_dates_that_are_not_exact(literal, flagged):
    fields = {"verbatim_dts": value(literal, layer="verbatim")}
    assert bool(confidence.not_verbatim_date("verbatim_dts", fields["verbatim_dts"], fields, RULES)) is flagged


def test_a_code_elsewhere_on_the_label_never_flags_a_year():
    """Codex on PR #453: only the value's own text is read; the label's slide code flags nothing."""
    group = readings("IV-29-68-4\n1916\nSan Diego", "IV-29-68-4\n1916\nSan Diego")
    run, reasons = review({"verbatim_dts": value("1916", layer="verbatim")}, group)
    assert reasons == []


def test_the_text_of_an_exact_collecting_date_or_of_the_identification_date_is_flagged_and_kept():
    """105526808: "VI.'41" settled as the identification date and as Verbatim D/T/S; a day-precision
    collecting date's own text. The literal stays as written (Codex on PR #453)."""
    group = readings("ROBT. TRAUB Det.\nDATE VI.'41", "ROBT. TRAUB Det.\nDATE VI.'41")
    fields = {"date_identified": value("VI.'41"), "verbatim_dts": value("VI.'41", layer="verbatim")}
    run, reasons = review(fields, group)
    assert reasons == ["marked:verbatim_dts:L1:not_verbatim_date"]
    assert (run.fields["verbatim_dts"].literal, run.fields["verbatim_dts"].state) == ("VI.'41", ValueState.SUPPORTED)
    month = {"date_visited_from": value("XI.'46", parsed="1946-11"), "verbatim_dts": value("XI.'46", layer="verbatim")}
    assert review(month, readings("XI.'46", "XI.'46"))[1] == []


def test_a_second_pass_replaces_its_own_marks():
    group = readings("5-VII-1940", "5-VI-1940")
    run, _ = review({"date_visited_from": value("5-VII-1940")}, group)
    run.fields["date_visited_from"] = value("5-VI-1940")
    confidence.review(run, readings=readings("5-VI-1940", "5-VI-1940"), date_rules=RULES)
    assert marked_reasons(run) == []


def test_every_why_has_a_plain_code():
    assert confidence.WHYS == ("readers_differ", "follows_marked", "extent", "distance_origin", "not_collection_code",
        "not_verbatim_date")
