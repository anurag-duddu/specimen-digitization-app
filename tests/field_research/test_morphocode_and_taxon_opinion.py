"""Lane D of the waiting-fields program (2026-11-24): the taxon's second opinion is compared on the name
without its author and year, and a blank second opinion on owner decision B's unmatched taxon marks nothing.

- second_opinion.same: "Bittacus strigosus Hagen, 1861" (GBIF's accepted name) and the second opinion's
  "Bittacus strigosus Hagen" agree (production record 13c99e90).
- second_opinion.derived: a blank second opinion on owner decision B's unmatched taxon marks nothing
  (production records 93e61763 "Sp #1", 66a72095 "sp 22", f35af3a5 "sp. 22"), where no label writes a word
  that may be a genus (step._genus_on_a_label).

Round 1's change to decision B's genus scan (the first pass's advice) was taken out after round 2 of #472's
review: a field's value, settled or not, can write a genus the first pass advised for that field."""

from __future__ import annotations

import pytest
import test_step
from test_step import NoGenus, Scripted, build_rig, cannot_resolve, settle

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.field_research import second_opinion as so
from specimen_digitization.field_research import step as field_step

# The second opinion's marks are derived here (tests/conftest.py, without_second_opinion_marks).
USES_SECOND_OPINION = True
IRN_LINE = "identified_by_irn: synthetic:eparties:1\n"


def without_the_taxon_line(line):
    """test_taxon_scope's synthetic label: `line` first, no keyed taxon line and no determiner's IRN line
    (finalizing leaves the IRN unsettled, so its "synthetic" would be a word that may be a genus when the
    second opinion's marks are derived)."""
    assert IRN_LINE in test_step.TEXT
    return line + "\n" + test_step.TEXT.replace("taxon: " + test_step.LABEL["taxon"] + "\n", "").replace(IRN_LINE, "")


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
    # round 2 of #472's review: a capitalised word with no year after a name is no author against the name
    ("Aus bus Cus", "Aus bus", False),
    ("Pulex irritans Linnaeus", "Pulex irritans", False),
    ("Aus bus (Linnaeus)", "Aus bus", False),
    ("Aus bus Cus", "Aus bus Cus", True),
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
