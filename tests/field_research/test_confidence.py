"""Confident or flagged (field_research/confidence.py, lane Q1 of the autonomy program).

Each rule flags a settled value something in the run argues against, decided on the label's reading
units, and leaves a value nothing argues against confident. The labels are the stored runs'
(`~/specimen-golive/runs/`, the 100 truth slides) cut to the lines that matter; each case names its
slide, or the review finding it answers (Codex round 1 on PR #454).
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import FieldValue, RunFinding, ValueState
from specimen_digitization.application.reading_units import ReadingUnit, ReadingUnits, UnitText
from specimen_digitization.field_research import confidence
from specimen_digitization.field_research.contracts import Reading
from specimen_digitization.field_research.step import marked_reasons

RULES = published_registry().profiles[0].date_rules
LABEL = "L1"


def readings(*texts, units=None, label=LABEL):
    """One label's readings, 1A, 1B, ...; with `units` (each (one text per reader, fields)), its
    reading units, each reader's text found in its reading in order."""
    names = [f"1{chr(65 + i)}" for i in range(len(texts))]
    built = None
    if units is not None:
        at = [0] * len(texts)
        found = []
        for number, (parts, fields) in enumerate(units, 1):
            readers = {}
            for i, part in enumerate(parts):
                start = texts[i].index(part, at[i]) if part else at[i]
                readers[f"{label}{names[i]}"] = UnitText(text=part, start=start, end=start + len(part))
                at[i] = start + len(part)
            found.append(ReadingUnit(id=f"{label}:{number}", label=label, lines=(1, 1), readers=readers,
                image=next(p for p in parts if p), fields=list(fields)))
        built = ReadingUnits(label=label, units=found)
    return tuple(Reading(name, label, f"{label}{name}", "raw_reading", text, units=built)
        for name, text in zip(names, texts))


def same(text, *units):
    """Two readers writing `text` alike, its units each (text, fields)."""
    return readings(text, text, units=[((part,) * 2, fields) for part, fields in units])


def value(literal, *, layer="settled", label=LABEL, **more):
    return FieldValue(state=ValueState.SUPPORTED, literal=literal, layer=layer, source_region_id=label, **more)


def groups(group):
    return {group[0].region_id: list(group)}


def review(fields, group, findings=(), dependencies=None):
    run = SimpleNamespace(fields=fields, evidence=[], findings=list(findings), dependencies=dependencies or {})
    confidence.review(run, readings=group, date_rules=RULES)
    return run, sorted(marked_reasons(run))


# ---- rule 1: the readers differ and the image alone chose --------------------------------------

def test_a_date_the_readers_differ_on_is_flagged_and_names_the_reading_taken():
    """105526392: 2A writes "24-VII-1916", 2B "24-VI-1916"; the image named 2A's. On main it clears."""
    group = readings("NEOTOMA\n24-VII-1916\ncol RRP", "NEOTOMA\n24-VI-1916\ncol RRP",
        units=[(("NEOTOMA",) * 2, []), (("24-VII-1916", "24-VI-1916"), ["date_visited_from"]),
            (("col RRP",) * 2, ["collectors"])])
    sentence = confidence.readers_differ("date_visited_from", value("24-VII-1916"), groups(group))
    assert sentence is not None and "1A's text '24-VII-1916'" in sentence and "reading 1B does not" in sentence


@pytest.mark.parametrize(("first", "second"), [
    ("12 mi. N, 5 mi. E", "12mi. N, 5mi. E"),          # spacing (105526632)
    ("E. Brundage Jr.COLL.", "E. Brundage Jr. COLL."),  # spacing (105526822)
    ("Coyhaique", "Coyha\N{LATIN SMALL LETTER I WITH DIAERESIS}que"),  # an accent (105526522)
    ("Ex. Blarina brevicauda \N{MALE SIGN}", "Ex. Blarina brevicauda"),  # a sex sign
    ("28- III -1974", "28- III-1974"),                 # spacing in a date (105527047)
])
def test_readers_that_differ_only_in_spacing_punctuation_or_accents_agree(first, second):
    group = readings(first, second, units=[((first, second), ["precise_location"])])
    assert confidence.readers_differ("precise_location", value(first), groups(group)) is None


@pytest.mark.parametrize(("first", "second"), [
    ("1.5 km N", "15 km N"),     # a decimal point (Codex round 1, 3)
    ("-80 m", "80 m"),           # a sign
    ("Elev. -80 m", "Elev. 80 m"),
    ("1,5 km N", "1.5 km N"),    # another decimal separator
])
def test_a_difference_in_a_number_s_digits_separator_or_sign_is_a_real_difference(first, second):
    group = readings(first, second, units=[((first, second), ["precise_location"])])
    literal = first.removeprefix("Elev. ")
    assert confidence.readers_differ("precise_location", value(literal), groups(group))
    assert not confidence.writes(second, literal)


def test_the_readers_are_compared_over_the_units_the_value_is_drawn_from_never_elsewhere():
    """Codex round 1, 4: the determiner line's "J. Smith" is no reader agreeing on the collector."""
    first, second = "leg. J. Smith\nDet. J. Smith", "leg. J. Smyth\nDet. J. Smith"
    group = readings(first, second, units=[(("leg.",) * 2, ["collectors"]), (("J. Smith", "J. Smyth"), ["collectors"]),
        (("Det.",) * 2, ["identified_by_irn"]), (("J. Smith",) * 2, ["identified_by_irn"])])
    assert confidence.readers_differ("collectors", value("J. Smith"), groups(group))


def test_a_value_both_readers_write_at_its_units_stays_confident():
    """105527047: both readers write "28- III -1974" (spacing aside): nothing in the row argues."""
    group = readings("28- III -1974\ncol R.E. MARTIN", "28- III-1974\ncol R.E. MARTIN",
        units=[(("28- III -1974", "28- III-1974"), ["date_visited_from"]), (("col R.E. MARTIN",) * 2, ["collectors"])])
    assert confidence.readers_differ("date_visited_from", value("28- III -1974"), groups(group)) is None


def test_a_source_that_decides_or_a_place_record_keeps_it_confident():
    group = readings("Kunduz", "Kundus", units=[(("Kunduz", "Kundus"), ["province_state"])])
    decided = value("Kunduz", evidence_ids=["e1"], evidence_relations={"e1": "decides"})
    assert confidence.readers_differ("taxon", decided, groups(group)) is None
    assert confidence.readers_differ("province_state", value("Kunduz", authority_id="tgn:1"), groups(group)) is None
    assert confidence.readers_differ("precise_location", value("Kunduz", authority_id="tgn:1"), groups(group))


def test_whole_tokens_only():
    assert not confidence.writes("24-VII-1916", "24-VI")
    assert confidence.writes("24-VII-1916", "24 VII")


# ---- rule 2: a derived value follows a marked one ----------------------------------------------

def dates(first, second):
    return readings(first, second, units=[((first, second), ["date_visited_from"])])


def test_a_date_derived_from_a_flagged_date_is_flagged_with_it():
    """105526355: Date Visited To derived from a From the readers differ on ("5-VII-1940", "5-VI-1940")."""
    fields = {"date_visited_from": value("5-VII-1940", parsed="1940-07-05"),
        "date_visited_to": FieldValue(state=ValueState.SUPPORTED, parsed="1940-07-05", layer="derived",
            derived_from=["date_visited_from"])}
    run, reasons = review(fields, dates("5-VII-1940", "5-VI-1940"))
    assert reasons == ["marked:date_visited_from:L1:readers_differ", "marked:date_visited_to:L1:follows_marked"]
    assert run.fields["date_visited_to"].parsed == "1940-07-05"


def test_a_value_derived_from_a_confident_one_stays_confident():
    fields = {"date_visited_from": value("5-VI-1940", parsed="1940-06-05"),
        "date_visited_to": FieldValue(state=ValueState.SUPPORTED, parsed="1940-06-05", layer="derived",
            derived_from=["date_visited_from"])}
    assert review(fields, dates("5-VI-1940", "5-VI-1940"))[1] == []


def test_a_field_marked_already_gets_no_second_mark_and_its_derived_value_follows_it():
    earlier = RunFinding(rule_id="field_settlement", rule_version="v", severity="warning",
        field_key="date_visited_from", reason_code="marked:date_visited_from:L1:text_only")
    fields = {"date_visited_from": value("5-VII-1940"), "date_visited_to": FieldValue(state=ValueState.SUPPORTED,
        parsed="1940-07-05", layer="derived", derived_from=["date_visited_from"])}
    assert review(fields, dates("5-VII-1940", "5-VI-1940"), [earlier])[1] == [
        "marked:date_visited_from:L1:text_only", "marked:date_visited_to:L1:follows_marked"]


# ---- persons ------------------------------------------------------------------------------------

def test_no_mark_lands_on_a_field_a_person_carried_locked_or_transcribed():
    """A carried decision, a locked research selection, a label a person transcribed."""
    group = dates("5-VII-1940", "5-VI-1940")
    reason = "Settled by a person."
    run = SimpleNamespace(fields={"date_visited_from": value("5-VII-1940", reason=reason)}, evidence=[], findings=[],
        dependencies={})
    confidence.review(run, readings=group, human={"date_visited_from"}, date_rules=RULES)
    assert (marked_reasons(run), run.fields["date_visited_from"].reason) == ([], reason)
    locked = SimpleNamespace(fields={"date_visited_from": value("5-VII-1940", reason=reason)}, evidence=[],
        findings=[], dependencies={confidence.LOCKS: {"date_visited_from": {"selection_id": "s1"}}})
    confidence.review(locked, readings=group, date_rules=RULES)
    assert (marked_reasons(locked), locked.fields["date_visited_from"].reason) == ([], reason)
    person = (replace(group[0], input_source="decided_transcript", person_decided=True), group[1])
    transcribed = SimpleNamespace(fields={"date_visited_from": value("5-VII-1940", reason=reason)}, evidence=[],
        findings=[], dependencies={})
    confidence.review(transcribed, readings=person, date_rules=RULES)
    assert (marked_reasons(transcribed), transcribed.fields["date_visited_from"].reason) == ([], reason)


def test_release_takes_this_pass_s_mark_and_sentence_off_a_field_and_nothing_else():
    run, reasons = review({"date_visited_from": value("5-VII-1940", reason="Read as written.")},
        dates("5-VII-1940", "5-VI-1940"))
    assert reasons == ["marked:date_visited_from:L1:readers_differ"]
    confidence.release(run, {"date_visited_from"})
    assert (marked_reasons(run), run.fields["date_visited_from"].reason) == ([], "Read as written.")


# ---- rule 3: the extent -----------------------------------------------------------------------

def test_a_host_cut_inside_its_unit_is_flagged_with_the_fuller_text():
    """105526617: "ex Peromyscus" settled from the unit "ex Peromyscus\\nleucopus"."""
    group = same("RMT 1149\nex Peromyscus\nleucopus", ("RMT 1149", ["collection_code"]), ("ex Peromyscus\nleucopus", []))
    sentence = confidence.extent("habitat", value("ex Peromyscus"), groups(group))
    assert sentence is not None and "'ex Peromyscus\\nleucopus'" in sentence


def test_a_unit_that_also_holds_the_next_field_s_text_on_the_value_s_line_gives_no_fuller_text():
    """The first pass cut "Shrubs;1946" as one unit: the year on the same line is no more of the habitat."""
    group = readings("Shrubs;1946", "Shrubs,1946", units=[(("Shrubs;1946", "Shrubs,1946"), [])])
    assert confidence.extent("habitat", value("Shrubs"), groups(group)) is None


def test_a_unit_the_readers_write_differently_gives_no_fuller_text():
    """105527313: "Meriones\\nLIPOCUS" against "Meriones\\nLIPYCUS": no agreed longer run."""
    group = readings("Meriones\nLIPOCUS", "Meriones\nLIPYCUS", units=[(("Meriones\nLIPOCUS", "Meriones\nLIPYCUS"), [])])
    assert confidence.extent("habitat", value("Meriones"), groups(group)) is None


@pytest.mark.parametrize("text, units", [
    # Codex round 1, 6: a country after the host is no species of it.
    ("Meriones\nCHILE", [("Meriones", ["habitat"]), ("CHILE", ["country"])]),
    # A heading after the host (105526741).
    ("On Marmot\nSiphonaptera", [("On Marmot", ["habitat"]), ("Siphonaptera", [])]),
    # A species on its own line with no advice: the rule no longer guesses it (105527218).
    ("Meriones\nLIBYCUS", [("Meriones", []), ("LIBYCUS", [])]),
])
def test_no_fuller_text_is_guessed_from_a_neighbouring_unit_the_first_pass_does_not_give_the_field(text, units):
    literal = units[0][0]
    assert confidence.extent("habitat", value(literal), groups(same(text, *units))) is None


def test_a_locality_after_a_unit_advised_for_the_locality_is_flagged():
    """105527218: "27 km. north of Kunduz" after "Loc: AFGHANISTAN,", which the first pass advises for
    the locality too."""
    group = same("Host Data\nLoc: AFGHANISTAN,\n27 km. north of Kunduz\n549 m.", ("Host Data", []),
        ("Loc: AFGHANISTAN,", ["country", "precise_location"]), ("27 km. north of Kunduz", ["precise_location"]),
        ("549 m.", ["elevation_from_m"]))
    assert confidence.extent("precise_location", value("27 km. north of Kunduz"), groups(group))


def test_a_locality_after_a_unit_advised_only_for_a_higher_place_is_left_as_it_is():
    """105526996: "SANTIAGO PROV.," is advised for the province alone: no longer run of the same field."""
    group = same("CHILE: SANTIAGO\nPROV., TRAPPIST\nMONASTERY", ("CHILE:", ["country"]),
        ("SANTIAGO\nPROV.,", ["province_state"]), ("TRAPPIST\nMONASTERY", ["precise_location"]))
    assert confidence.extent("precise_location", value("TRAPPIST\nMONASTERY"), groups(group)) is None


def test_a_whole_locality_stays_confident():
    group = same("LEWIS COLLECTION\nAFGHANISTAN,\n27 km. north of Kunduz\n24-VIII-1965",
        ("LEWIS COLLECTION", ["collection_code"]), ("AFGHANISTAN,\n27 km. north of Kunduz", ["country", "precise_location"]),
        ("24-VIII-1965", ["date_visited_from"]))
    whole = value("AFGHANISTAN,\n27 km. north of Kunduz")
    assert confidence.extent("precise_location", whole, groups(group)) is None


def test_a_value_that_takes_in_another_field_s_unit_is_flagged():
    """Codex round 1, 5: "ex Peromyscus leucopus\\nShidler" settled whole as the Habitat, "Shidler" the city's unit."""
    group = same("ex Peromyscus leucopus\nShidler", ("ex Peromyscus leucopus", ["habitat"]), ("Shidler", ["city"]))
    sentence = confidence.extent("habitat", value("ex Peromyscus leucopus\nShidler"), groups(group))
    assert sentence is not None and "'Shidler'" in sentence
    locality = same("Puerto Ibanez\n(Aisen)\n549 m.", ("Puerto Ibanez", ["precise_location"]),
        ("(Aisen)", ["province_state"]), ("549 m.", ["elevation_from_m"]))
    assert confidence.extent("precise_location", value("Puerto Ibanez\n(Aisen)\n549 m."), groups(locality)) is None


def test_a_heading_kept_in_the_value_or_a_role_word_in_a_name_is_flagged():
    """105526760 "HOST: coyote"; the "Loc:" localities; 105526822 "E. Brundage Jr.COLL."."""
    assert confidence.extent("habitat", value("HOST: coyote"), {})
    assert confidence.extent("precise_location", value("Loc: AFGHANISTAN,\nPAGHMAN"), {})
    assert confidence.extent("collectors", value("E. Brundage Jr.COLL."), {})
    assert confidence.extent("collectors", value("W.E. Eiqsti. COLL"), {})
    assert confidence.extent("precise_location", value("CHILE: SANTIAGO PROV."), {}) is None
    assert confidence.extent("collectors", value("R.E. MARTIN"), {}) is None


def test_a_value_starting_with_a_modifier_letter_and_a_colon_is_no_heading_and_raises_nothing():
    """Codex round 1, 2: "\\u037a: mouse" has no letters once accents are set aside."""
    assert confidence.extent("habitat", value("\N{GREEK YPOGEGRAMMENI}: mouse"), {}) is None


def test_a_role_word_beside_the_name_in_its_unit_is_no_more_of_it():
    """105526647: "M. BOSCH" from the unit "col M. BOSCH": the value is the whole name."""
    group = same("col M. BOSCH\n12-IV-1976", ("col M. BOSCH", ["collectors"]), ("12-IV-1976", ["date_visited_from"]))
    assert confidence.extent("collectors", value("M. BOSCH"), groups(group)) is None


def test_the_taxon_is_never_given_a_fuller_text():
    """Codex round 1, 7: an "Order Siphonaptera" unit never marks a correct genus."""
    group = same("Order Siphonaptera\nXenopsylla", ("Order Siphonaptera", ["taxon"]), ("Xenopsylla", ["taxon"]))
    assert confidence.extent("taxon", value("Xenopsylla"), groups(group)) is None


# ---- rule 4: conventions -----------------------------------------------------------------------

@pytest.mark.parametrize(("key", "units", "literal"), [
    ("city", [("12 mi. N, 5 mi. E", ["precise_location"]), ("Shidler,", ["city"]), ("Osage", ["county"])], "Shidler,"),
    ("city", [("\N{VULGAR FRACTION ONE HALF}mi.S,2\N{VULGAR FRACTION ONE HALF}mi.E", ["precise_location"]),
        ("Cottonwood,", ["city"])], "Cottonwood,"),                                                    # 105526636
    ("city", [("14.5 km NNW", ["precise_location"]), ("Puerto Octay", ["city"])], "Puerto Octay"),      # 105526536
    ("province_state", [("Loc: AFGHANISTAN,", ["country"]), ("27 km. north of Kunduz", ["precise_location"])],
        "Kunduz"),                                                                                     # 105527218
])
def test_a_town_named_only_as_a_distance_s_origin_is_flagged(key, units, literal):
    text = "\n".join(part for part, _ in units)
    assert confidence.distance_origin(key, value(literal), groups(same(text, *units)))


def test_a_distance_in_another_unit_than_the_town_s_own_or_the_one_before_flags_nothing():
    """The distance must stand in the town's unit or the unit right before it."""
    far = same("12 mi. N, 5 mi. E\nCo., Oklahoma\nShidler", ("12 mi. N, 5 mi. E", ["precise_location"]),
        ("Co., Oklahoma", ["province_state"]), ("Shidler", ["city"]))
    assert confidence.distance_origin("city", value("Shidler"), groups(far)) is None
    plain = same("Shidler, Osage\nCo., Oklahoma", ("Shidler,", ["city"]), ("Osage", ["county"]),
        ("Co., Oklahoma", ["province_state"]))
    assert confidence.distance_origin("city", value("Shidler,"), groups(plain)) is None
    unitless = readings("5 mi. E Shidler", "5 mi. E Shidler")
    assert confidence.distance_origin("city", value("Shidler"), groups(unitless)) is None


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
    group = same("IV-29-68-4\n1916\nSan Diego", ("IV-29-68-4", []), ("1916", ["verbatim_dts"]), ("San Diego", ["city"]))
    assert review({"verbatim_dts": value("1916", layer="verbatim")}, group)[1] == []


def test_the_identification_date_s_own_units_are_flagged_and_the_literal_kept():
    """105526808: "VI.'41" on the DATE line of a determination label, settled as Date Identified and as
    Verbatim D/T/S from the same unit. The literal stays as written (Codex on PR #453)."""
    group = same("ROBT. TRAUB Det.\nDATE VI.'41", ("ROBT. TRAUB Det.", ["identified_by_irn"]), ("DATE", []),
        ("VI.'41", ["date_identified", "verbatim_dts"]))
    fields = {"date_identified": value("VI.'41"), "verbatim_dts": value("VI.'41", layer="verbatim")}
    run, reasons = review(fields, group)
    assert reasons == ["marked:verbatim_dts:L1:not_verbatim_date"]
    assert (run.fields["verbatim_dts"].literal, run.fields["verbatim_dts"].state) == ("VI.'41", ValueState.SUPPORTED)


def test_the_same_month_on_a_collecting_label_and_a_determination_label_is_no_identification_text():
    """Codex round 1, 8: equal text on two labels shares no unit: the collecting month stays."""
    collecting = same("Chile\nXI.'46", ("Chile", ["country"]), ("XI.'46", ["verbatim_dts"]))
    determination = readings("Det. Traub\nXI.'46", "Det. Traub\nXI.'46", label="L2",
        units=[(("Det. Traub",) * 2, ["identified_by_irn"]), (("XI.'46",) * 2, ["date_identified"])])
    fields = {"date_identified": value("XI.'46", label="L2"), "verbatim_dts": value("XI.'46", layer="verbatim")}
    assert review(fields, (*collecting, *determination))[1] == []


def test_a_second_pass_replaces_its_own_marks():
    run, _ = review({"date_visited_from": value("5-VII-1940")}, dates("5-VII-1940", "5-VI-1940"))
    run.fields["date_visited_from"] = value("5-VI-1940")
    confidence.review(run, readings=dates("5-VI-1940", "5-VI-1940"), date_rules=RULES)
    assert marked_reasons(run) == []


def test_every_why_has_a_plain_code():
    assert confidence.WHYS == ("readers_differ", "follows_marked", "extent", "distance_origin", "not_collection_code",
        "not_verbatim_date")


# ---- the guard ----------------------------------------------------------------------------------

def test_an_exception_inside_the_pass_leaves_the_run_exactly_as_without_it(monkeypatch):
    """Codex round 1, 2: the pass never fails research. Raised at the start, in a rule, and after a
    reason has been changed and a finding added: no mark, the fields and findings put back."""
    def fresh():
        return SimpleNamespace(fields={"date_visited_from": value("5-VII-1940", reason="Read."),
            "date_visited_to": FieldValue(state=ValueState.SUPPORTED, parsed="1940-07-05", layer="derived",
                derived_from=["date_visited_from"])}, evidence=[], findings=[], dependencies={})

    group = dates("5-VII-1940", "5-VI-1940")
    without = fresh()

    def boom(*args, **kwargs):
        raise RuntimeError("forced")

    for target in ("release", "readers_differ", "_marked_fields"):
        with monkeypatch.context() as patch:
            patch.setattr(confidence, target, boom)
            run = fresh()
            confidence.guarded(run, confidence.review, readings=group, date_rules=RULES)
            assert run.fields == without.fields and run.findings == without.findings, target
    with monkeypatch.context() as patch:
        made = []

        def late(**kwargs):
            if made:
                raise RuntimeError("forced")
            made.append(kwargs)
            return RunFinding(**kwargs)

        patch.setattr(confidence, "RunFinding", late)
        run = fresh()
        confidence.guarded(run, confidence.review, readings=group, date_rules=RULES)
        assert run.fields == without.fields and run.findings == without.findings


# ---- a person's decision, through the decision endpoint ------------------------------------------

def test_a_person_s_field_decision_takes_the_mark_off_and_refinalize_never_puts_it_back(tmp_path):
    """Codex round 1, 1: readers "Shrubs" and "Shurbs", the image naming 1A's; research marks the habitat
    readers_differ. A reviewer confirms "Shrubs" by a field decision, keeping its settled layer: the
    mark goes, the reviewer's reason is untouched, and the approval's refinalize adds nothing."""
    from test_settlement_rule import HABITATS, naming
    from test_step import TEXT, Scripted, answering, build_rig, decide, mounted, reasons_for, resolved, review_client

    rig = build_rig(tmp_path, TEXT.replace("Synthetic grassland", "Shrubs"),
        TEXT.replace("Synthetic grassland", "Shurbs"), candidates=HABITATS)
    naming(rig, 0)
    rig.specimen = rig.repository.save(rig.principal, rig.specimen, rig.specimen.version, "naming", "naming")
    mounted(rig, Scripted({"habitat": answering(resolved("Shrubs", reading="1A"))}))
    done = rig.workflow.step(rig.principal, rig.specimen.id).run
    region = done.regions[0].id
    assert reasons_for(done, "habitat") == [f"marked:habitat:{region}:readers_differ"]
    client = review_client(rig)
    habitat = done.fields["habitat"]
    after = habitat.model_dump(mode="json", exclude={"evidence_ids"}) | {"reason": "Checked on the slide: Shrubs."}
    decided = decide(client, rig, "field-habitat", "field", target_id="habitat", after=after,
        evidence_ids=list(habitat.evidence_ids))
    assert decided.fields["habitat"].reason == "Checked on the slide: Shrubs."
    assert (decided.fields["habitat"].literal, decided.fields["habitat"].layer) == ("Shrubs", habitat.layer)
    assert reasons_for(decided, "habitat") == []
    assert not [f for f in decided.findings if f.rule_id == confidence.RULE and f.field_key == "habitat"]
    approved = decide(client, rig, "approve-habitat", "approve")
    assert reasons_for(approved, "habitat") == []
    assert approved.fields["habitat"].reason == "Checked on the slide: Shrubs."
