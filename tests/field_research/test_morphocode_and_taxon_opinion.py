"""Lane D of the waiting-fields program (2026-11-24): owner decision B's genus scan reads the first pass's
advice, and the taxon's second opinion is compared on the name without its author and year.

- step._genus_on_a_label: a reading unit the first pass placed only in fields that never hold a scientific
  name (step._placed_elsewhere: not the taxon, not the habitat) accounts for its words where one of those
  fields' stored values writes the unit's text (step._held_by_advice; round 1 of #472's review), settled or
  not. On production record 01b79931 the collector "F.G. Werner", left unsettled, held the morphocode
  "Sp. 30" back.
- second_opinion.same: "Bittacus strigosus Hagen, 1861" (GBIF's accepted name) and the second opinion's
  "Bittacus strigosus Hagen" agree (production record 13c99e90).
- second_opinion.derived: a blank second opinion on owner decision B's unmatched taxon marks nothing
  (production records 93e61763 "Sp #1", 66a72095 "sp 22", f35af3a5 "sp. 22"), where no label writes a word
  that may be a genus (step._genus_on_a_label)."""

from __future__ import annotations

import pytest
import test_step
from test_step import FieldAnswer, NoGenus, Scripted, answering, build_rig, cannot_resolve, settle

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.field_research import second_opinion as so
from specimen_digitization.field_research import step as field_step

# The second opinion's marks are derived here (tests/conftest.py, without_second_opinion_marks).
USES_SECOND_OPINION = True
TAXON_REASONS = ("mandatory_unresolved:taxon", "taxonomy_unresolved")
CODE = "sp. 30 \N{FEMALE SIGN}"
PERSON = "F.G. Werner"


IRN_LINE = "identified_by_irn: synthetic:eparties:1\n"


def without_the_taxon_line(line):
    """test_taxon_scope's synthetic label: `line` first, no keyed taxon line and no determiner's IRN line
    (finalizing leaves the IRN unsettled, so its "synthetic" would be a word that may be a genus when the
    second opinion's marks are derived)."""
    assert IRN_LINE in test_step.TEXT
    return line + "\n" + test_step.TEXT.replace("taxon: " + test_step.LABEL["taxon"] + "\n", "").replace(IRN_LINE, "")


def without_a_collector(line):
    """without_the_taxon_line's label with no collectors line ("leg. J. Smith"): the collectors' expert
    then names the only person on the specimen."""
    text = without_the_taxon_line(line)
    assert text.endswith("\nleg. J. Smith")
    return text.removesuffix("\nleg. J. Smith")


def collectors_quoting(literal):
    """A collectors' expert that finds no collecting marker and quotes `literal` (label 2's first reader)."""
    return answering(FieldAnswer(outcome="sources_cannot_resolve", literal=literal, reading_names=["2A"],
        explanation="No collecting marker stands beside the name."))


def advising(text, fields, role=""):
    """A units-path first pass (test_step.seen_units) whose units holding part of `text` (the synthetic cut
    makes a unit of each word) carry the advice `fields` and the role `role`."""
    original = test_step.seen_units

    def seen(units):
        units = original(units)
        return units.model_copy(update={"units": [
            unit.model_copy(update={"fields": list(fields), "role": role})
            if any(span.text and span.text in text for span in unit.readers.values()) else unit
            for unit in units.units]})
    return seen


def taxon_after(tmp_path, monkeypatch, second, fields, role="", collectors=None):
    """Label 1 writes the code and no person; label 2 `second`, whose units the first pass advises
    `fields`. The taxon's expert asks GBIF the code and quotes it; the collectors' expert quotes
    `collectors` (`second` by default), finding no collecting marker."""
    monkeypatch.setattr(test_step, "seen_units", advising(second, fields, role))
    test_step.a_second_label(monkeypatch, second)
    rig = build_rig(tmp_path, without_a_collector(CODE))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve(CODE, asks=[CODE]),
        "collectors": collectors_quoting(second if collectors is None else collectors)}), tools=NoGenus(rig.blobs))
    return run


# ---- owner decision B: the first pass's advice --------------------------------------------------------

@pytest.mark.parametrize("fields", [["collectors"], ["collectors", "identified_by_irn"]])
def test_a_persons_name_the_first_pass_places_with_the_collectors_does_not_hold_the_code_back(
        tmp_path, monkeypatch, fields):
    """01b79931: label 2's "F.G. Werner", advised for the collectors, which the collectors' expert quotes
    and does not settle, is no possible genus: the code clears unmatched (origin/main: unresolved, its
    "F")."""
    run = taxon_after(tmp_path, monkeypatch, PERSON, fields)
    collectors = run.fields["collectors"]
    assert (collectors.state, collectors.literal) == (ValueState.UNRESOLVED, PERSON)
    taxon = run.fields["taxon"]
    assert (taxon.state, taxon.literal, taxon.reason) == (ValueState.SUPPORTED, CODE, field_step.UNMATCHED)
    assert [reason for reason in run.reasons if reason in TAXON_REASONS] == []


@pytest.mark.parametrize(("second", "fields", "role"), [
    (PERSON, [], ""),
    (PERSON, ["taxon"], ""),
    (PERSON, ["collectors", "taxon"], ""),
    (PERSON, ["habitat"], ""),
    (PERSON, ["collectors"], "genus"),
    (PERSON, ["not_a_field"], ""),
    ("Epipsocus", ["taxon"], "genus"),
])
def test_a_unit_with_no_advice_or_advised_for_a_name_still_holds_the_code_back(
        tmp_path, monkeypatch, second, fields, role):
    """No advice, advice naming the taxon or the habitat (a host's name), a name's role, or advice that
    names no field leaves the word a possible genus: the taxon stays unresolved, as on origin/main."""
    run = taxon_after(tmp_path, monkeypatch, second, fields, role)
    assert run.fields["taxon"].state == ValueState.UNRESOLVED
    assert [reason for reason in run.reasons if reason in TAXON_REASONS] == list(TAXON_REASONS)


def test_a_genus_the_first_pass_advises_for_the_collectors_still_holds_the_code_back(tmp_path, monkeypatch):
    """Round 1 of #472's review: a genus "Epipsocus" the first pass wrongly advised for the collectors,
    which the collectors' value does not write, may still be the genus. The taxon stays unresolved
    (round 1's head: unmatched)."""
    run = taxon_after(tmp_path, monkeypatch, "Epipsocus", ["collectors"], collectors="R. D. Mitchell")
    assert run.fields["collectors"].literal is None
    assert run.fields["taxon"].state == ValueState.UNRESOLVED
    assert [reason for reason in run.reasons if reason in TAXON_REASONS] == list(TAXON_REASONS)


@pytest.mark.parametrize(("collectors", "word"), [
    (FieldValue(state=ValueState.UNRESOLVED, literal=PERSON), None),
    (FieldValue(state=ValueState.AMBIGUOUS, verbatim_by_observation={"any": "x\n" + PERSON}), None),
    (FieldValue(state=ValueState.UNRESOLVED, literal="F.G. Wernerson"), "Werner"),
    (FieldValue(state=ValueState.UNRESOLVED, literal="J. Smith"), "F"),
    (FieldValue(), "F"),
])
def test_the_advised_fields_value_must_write_the_units_text(tmp_path, monkeypatch, collectors, word):
    """A unit advised for the collectors is set aside only where the collectors' literal or a reader's
    verbatim writes its text as whole words (step._held_by_advice): "Werner" inside "Wernerson" is not."""
    monkeypatch.setattr(test_step, "seen_units", advising(PERSON, ["collectors"]))
    test_step.a_second_label(monkeypatch, PERSON)
    rig = build_rig(tmp_path, without_a_collector(CODE))
    run = rig.specimen.run
    run.fields["collectors"] = collectors
    assert field_step._genus_on_a_label(run, list(field_step.run_readings(run))) == word


def test_the_advice_accounts_only_for_a_readers_own_text_at_the_unit(tmp_path, monkeypatch):
    """A reader whose text at the unit's span is not the unit's text for it (a changed reading) gains
    nothing from the advice: its word may still be a genus."""
    import dataclasses

    monkeypatch.setattr(test_step, "seen_units", advising(PERSON, ["collectors"]))
    test_step.a_second_label(monkeypatch, PERSON)
    rig = build_rig(tmp_path, without_a_collector(CODE))
    run = rig.specimen.run
    run.fields["collectors"] = FieldValue(state=ValueState.UNRESOLVED, literal=PERSON)
    readings = list(field_step.run_readings(run))
    second = [reading for reading in readings if reading.region_id == run.regions[1].id]
    assert second and field_step._genus_on_a_label(run, readings) is None
    changed = [dataclasses.replace(reading, text="F.G. Wernex") if reading in second else reading
        for reading in readings]
    assert field_step._genus_on_a_label(run, changed) == "Wernex"


# ---- the taxon's second opinion: the name without its author and year ---------------------------------

@pytest.mark.parametrize(("first", "second", "agree"), [
    ("Bittacus strigosus Hagen, 1861", "Bittacus strigosus Hagen", True),
    ("Panorpa speciosa Carpenter, 1931", "Panorpa speciosa Carpenter", True),
    ("Pulex irritans Linnaeus, 1758", "Pulex irritans", True),
    ("Aus bus (Linnaeus, 1758)", "Aus bus", True),
    ("Stivalius abacetus J. & R., 1922", "Stivalius abacetus", True),
    ("Panorpa Linnaeus, 1758", "Panorpa Linnaeus", True),
    # round 1 of #472's review: a hybrid, a capitalised epithet, two authors, a genus with an author alone
    ("Aus bus Smith \N{MULTIPLICATION SIGN} Aus cus Jones", "Aus bus Smith", False),
    ("Aus bus Smith x Aus cus Jones", "Aus bus Smith", False),
    ("Pulex Irritans", "Pulex Simulans", False),
    ("Pulex Irritans", "Pulex", False),
    ("Aus bus Smith", "Aus bus Jones", False),
    ("Panorpa Linnaeus, 1758", "Panorpa", False),
    ("Panorpa", "Panorpa speciosa", False),
    ("Panorpa speciosa Carpenter", "Panorpa nuptialis Carpenter", False),
    ("Panorpa sp. 3", "Panorpa sp. 5", False),
    ("Panorpa sp. 3", "Panorpa", False),
    ("DELOSTICHUS COXALIS", "DELOSTICHUS FUSCUS", False),
    ("Aus bus cus Smith", "Aus bus", False),
    ("Aus bus de Geer", "Aus bus", False),
])
def test_two_taxa_agree_on_the_name_without_its_author_and_year(first, second, agree):
    assert so.same("taxon", first, second) is agree
    assert so.same("taxon", second, first) is agree


def test_the_author_rule_is_the_taxons_alone():
    """Another text field keeps the text rule: an author is part of its value."""
    assert not so.same("habitat", "Pulex irritans Linnaeus, 1758", "Pulex irritans")
    assert not so.same("collectors", "Bittacus strigosus Hagen", "Bittacus strigosus")


# ---- a blank second opinion on owner decision B's unmatched taxon ---------------------------------------

def unmatched_run(tmp_path):
    """The units-path run whose taxon owner decision B settled as written, unmatched ("sp. 22")."""
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 22"))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve("sp. 22", asks=["sp. 22"])}), tools=NoGenus(rig.blobs))
    evidence = {item.id: item for item in run.evidence}
    assert field_step.taxon_unmatched(run.fields["taxon"], evidence, run.lookups, run=run)
    return run


def judged(run, entry):
    run.second_opinion = {"status": so.OBTAINED, "fields": {"taxon": {"compared": so.shown(run.fields["taxon"]),
        **entry, "verdict": so.DIFFERS_VERDICT}}}
    return [why for key, why in so.derived(run) if key == "taxon"]


def test_a_blank_second_opinion_on_the_unmatched_taxon_marks_nothing(tmp_path):
    """93e61763, 66a72095 and f35af3a5: the second opinion gives a morphocode with no genus no taxon. Its
    blank (no value, no UNSURE) is no other reading of the name: no mark (origin/main: differs)."""
    run = unmatched_run(tmp_path)
    assert judged(run, {"value": None, "evidence": ""}) == []


@pytest.mark.parametrize("entry", [
    {"value": None, "evidence": "UNSURE: no genus is written"},
    {"value": "Epipsocus", "evidence": "L1: Epipsocus"},
    {"value": "sp. 23", "evidence": "L1: sp. 23"},
])
def test_an_unsure_or_another_value_on_the_unmatched_taxon_still_marks(tmp_path, entry):
    run = unmatched_run(tmp_path)
    assert judged(run, entry) == [so.DIFFERS]


def test_a_blank_second_opinion_on_any_other_taxon_still_marks(tmp_path):
    """A taxon that is not owner decision B's unmatched name (here the same text with GBIF's no-name check
    row taken away) keeps the mark for a blank second opinion."""
    run = unmatched_run(tmp_path)
    taxon = run.fields["taxon"]
    run.fields["taxon"] = FieldValue(state=ValueState.SUPPORTED, literal=taxon.literal, parsed=taxon.parsed,
        layer=taxon.layer, source_region_id=taxon.source_region_id)
    assert judged(run, {"value": None, "evidence": ""}) == [so.DIFFERS]


def test_a_blank_second_opinion_where_a_label_writes_a_genus_still_marks(tmp_path, monkeypatch):
    """Round 1 of #472's review: a stored unmatched "sp. 22" (decision B's value, here settled while the
    genus scan was kept from seeing label 2) on a specimen whose label 2 writes "Epipsocus", advised for
    the taxon, keeps the mark for a blank second opinion (round 1's head: no mark)."""
    monkeypatch.setattr(test_step, "seen_units", advising("Epipsocus", ["taxon"], "genus"))
    test_step.a_second_label(monkeypatch, "Epipsocus")
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 22"))
    run = rig.specimen.run
    with monkeypatch.context() as unseen:
        unseen.setattr(field_step, "_genus_on_a_label", lambda run, readings: None)
        settle(rig, Scripted({"taxon": cannot_resolve("sp. 22", asks=["sp. 22"])}), tools=NoGenus(rig.blobs))
    evidence = {item.id: item for item in run.evidence}
    assert field_step.taxon_unmatched(run.fields["taxon"], evidence, run.lookups, run=run)
    assert field_step._genus_on_a_label(run, field_step.run_readings(run)) == "Epipsocus"
    assert judged(run, {"value": None, "evidence": ""}) == [so.DIFFERS]
