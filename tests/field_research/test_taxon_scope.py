"""WP 2.T: the taxon in the collection's scope, on the units path.

- A code with no genus the organiser left as no value (owner decision B, step._unmatched_taxon):
  the units-wp15c cases "sp. 30 <female sign>", "Sp.30 <female sign>" and "sp. 22".
- A name a label writes after a host marker is never the taxon (agreement._host, the ontology's
  rule host_is_no_taxon): the units-wp15c cases "Host Thomomys" and "Ex. Canis familiaris".
- GBIF succeeds only on its accepted record inside class Insecta, the collection's higher taxon
  (application.lookup.row_one, homonym_conflict; the rule taxon_in_collection_scope), on the
  stored answers of units-wp15c's runs (tests/fixtures/gbif_wp15c_match_bodies.json)."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import httpx
import pytest
import test_step
from test_step import (
    COLLECTORS,
    LABEL,
    TEXT,
    FakeSources,
    NoGenus,
    Scripted,
    answering,
    build_rig,
    cannot_resolve,
    resolved,
    settle,
)

from specimen_digitization.application.domain import Evidence, FieldValue, Lookup, LookupStatus, ValueState
from specimen_digitization.application.lookup import COL_XR, GbifTaxonomy
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FieldAnswer, FieldOutcome, SourceAnswer, SourceCandidate

TAXON_REASONS = ("mandatory_unresolved:taxon", "taxonomy_unresolved")
BODIES = json.loads((Path(__file__).parents[1] / "fixtures" / "gbif_wp15c_match_bodies.json").read_text(
    encoding="utf-8"))["bodies"]


def without_the_taxon_line(line):
    """The synthetic label with `line` as its first line and no keyed taxon line: the organiser's
    keyed-line parser then gives the taxon no value and no candidate, and no line above `line`
    writes a word that may be a genus (checks.label_names_no_genus)."""
    return line + "\n" + TEXT.replace("taxon: " + LABEL["taxon"] + "\n", "")


# Where the readers differ no reading is decided, so the keyed-line parser reads no line and the organiser's
# candidates are the fields' only provenance: the identified-by IRN's, which no expert researches, is given here
# so that its text is accounted for (step._genus_on_a_label).
IRN = [("identified_by_irn", name, LABEL["identified_by_irn"], "identified_by_irn: " + LABEL["identified_by_irn"])
    for name in ("1A", "1B")]


def taxon_reasons(run):
    return [reason for reason in run.reasons if reason in TAXON_REASONS]


# ---- owner decision B with no organiser value (cause E3) ----------------------------------------

@pytest.mark.parametrize("code", ["sp. 30 \N{FEMALE SIGN}", "Sp.30 \N{FEMALE SIGN}", "sp. 22"])
def test_a_code_with_no_genus_the_organiser_gave_no_value_clears_unmatched_on_the_units_path(
        tmp_path, code):
    """units-wp15c's 105526321, 105526322 and 105526326: the organiser left the taxon without a
    value or a candidate, its expert asked GBIF the code and answered sources_cannot_resolve quoting
    it, and no label writes a genus. On the units path the taxon clears as written, unmatched."""
    rig = build_rig(tmp_path, without_the_taxon_line(code))
    run = rig.specimen.run
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "taxon"]
    assert (task.current.literal, task.candidates) == (None, ())
    settle(rig, Scripted({"taxon": cannot_resolve(code, asks=[code])}), tools=NoGenus(rig.blobs))
    taxon = run.fields["taxon"]
    evidence = {item.id: item for item in run.evidence}
    assert (taxon.state, taxon.literal, taxon.normalized, taxon.authority_id, taxon.layer) == (
        ValueState.SUPPORTED, code, None, None, "settled")
    assert taxon.reason == field_step.UNMATCHED
    assert field_step.taxon_unmatched(taxon, evidence, run.lookups, run=run)
    assert taxon_reasons(run) == []


def naming(text):
    """A units-path first pass whose image names `text` at a unit where the readers differ and
    one of them writes it there, and the text at each unit where every reader writes the same text
    (the synthetic cut makes "sp. 30" beside "Sp.30" one unit, the sex sign another)."""
    def seen(units):
        return units.model_copy(update={"units": [
            unit.model_copy(update={"image": text}) if text in texts and len(texts) > 1
            else unit.model_copy(update={"image": next(iter(texts))}) if len(texts) == 1 and "" not in texts
            else unit
            for unit in units.units for texts in [{span.text for span in unit.readers.values()}]]})
    return seen


def test_readers_writing_the_code_differently_settle_on_the_text_the_image_names(
        tmp_path, monkeypatch):
    """units-wp15c's 105526321: 2A writes "sp. 30 <female sign>", 2B "Sp.30 <female sign>", the
    image names 2A's text, and the expert quotes 2B's. On the units path the taxon clears unmatched
    on the text the image names."""
    monkeypatch.setattr(test_step, "seen_units", naming("sp. 30"))
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 30 \N{FEMALE SIGN}"),
        without_the_taxon_line("Sp.30 \N{FEMALE SIGN}"), candidates=[*COLLECTORS, *IRN])
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve("Sp.30 \N{FEMALE SIGN}", asks=["Sp.30 \N{FEMALE SIGN}"],
        reading="1B")}), tools=NoGenus(rig.blobs))
    taxon = run.fields["taxon"]
    assert (taxon.state, taxon.literal, taxon.reason) == (
        ValueState.SUPPORTED, "sp. 30 \N{FEMALE SIGN}", field_step.UNMATCHED)
    assert taxon_reasons(run) == []


def test_a_code_the_image_does_not_name_stays_unresolved(tmp_path, monkeypatch):
    """Rule 4 of the spec's section 4: readers agreeing alone back a text, the image or a source
    clears it. Where the readers spell the code differently and the image names neither, the
    taxon stays unresolved, as on main."""
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 30 \N{FEMALE SIGN}"),
        without_the_taxon_line("Sp.30 \N{FEMALE SIGN}"), candidates=[*COLLECTORS, *IRN])
    run = rig.specimen.run
    words = test_step.genus_words(monkeypatch)
    settle(rig, Scripted({"taxon": cannot_resolve("sp. 30 \N{FEMALE SIGN}", asks=["sp. 30 \N{FEMALE SIGN}"])}),
        tools=NoGenus(rig.blobs))
    assert (run.fields["taxon"].state, run.fields["taxon"].literal) == (ValueState.UNRESOLVED, "sp. 30 \N{FEMALE SIGN}")
    assert taxon_reasons(run) == list(TAXON_REASONS)
    # No word holds it back: the label's settlement does (rule 4).
    assert not any(words)


def test_a_code_below_a_genus_keeps_main_s_result(tmp_path):
    """units-wp15c's 105526328: "Epipsocus" with "Sp. 1" on the line below names a genus, so owner
    decision B does not apply; the taxon stays unresolved."""
    rig = build_rig(tmp_path, without_the_taxon_line("Epipsocus\nSp. 1"))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve("Sp. 1", asks=["Sp. 1"])}), tools=NoGenus(rig.blobs))
    assert (run.fields["taxon"].state, run.fields["taxon"].literal) == (ValueState.UNRESOLVED, "Sp. 1")
    assert taxon_reasons(run) == list(TAXON_REASONS)


def test_a_code_the_expert_does_not_quote_never_clears(tmp_path):
    """The code comes from the expert's own answer only when it quotes a code with no genus: an
    answer quoting another text leaves the taxon unresolved, as on main."""
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 30 \N{FEMALE SIGN}"))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve("30 \N{FEMALE SIGN}", asks=["sp. 30 \N{FEMALE SIGN}"])}),
        tools=NoGenus(rig.blobs))
    assert run.fields["taxon"].state == ValueState.UNRESOLVED
    assert taxon_reasons(run) == list(TAXON_REASONS)


def test_a_code_the_organiser_left_with_no_value_but_its_candidates_clears_unmatched_on_the_units_path(
        tmp_path, monkeypatch):
    """units-wp15c's r1/pair 105526326: the organiser left the taxon without a value, its candidates
    3A's "sp. 22" and 3B's "Sp. 22", and the image names 3A's text. On the units path the taxon clears
    unmatched on that text."""
    monkeypatch.setattr(test_step, "seen_units", naming("sp."))
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 22"), without_the_taxon_line("Sp. 22"),
        candidates=[*COLLECTORS, *IRN, ("taxon", "1A", "sp. 22", "sp. 22"), ("taxon", "1B", "Sp. 22", "Sp. 22")])
    run = rig.specimen.run
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "taxon"]
    assert task.current.literal is None and len(task.candidates) == 2
    settle(rig, Scripted({"taxon": cannot_resolve("sp. 22", asks=["sp. 22", "Sp. 22"])}), tools=NoGenus(rig.blobs))
    taxon = run.fields["taxon"]
    assert (taxon.state, taxon.literal, taxon.reason) == (ValueState.SUPPORTED, "sp. 22", field_step.UNMATCHED)
    assert taxon_reasons(run) == []


def test_two_labels_settling_two_spellings_of_the_code_never_clear(tmp_path, monkeypatch):
    """Label 1's readers write "sp. 30 <female sign>", label 2's "Sp.30 <female sign>", the organiser's
    candidate on each label its readers' text, and each label cleared on its own text: the labels give
    two texts, so the taxon stays unresolved."""
    test_step.a_second_label(monkeypatch, "Sp.30 \N{FEMALE SIGN}")
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 30 \N{FEMALE SIGN}"), candidates=[*COLLECTORS,
        *(("taxon", name, "sp. 30 \N{FEMALE SIGN}", "sp. 30 \N{FEMALE SIGN}") for name in ("1A", "1B")),
        *(("taxon", name, "Sp.30 \N{FEMALE SIGN}", "Sp.30 \N{FEMALE SIGN}") for name in ("2A", "2B"))])
    run = rig.specimen.run
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "taxon"]
    assert len(run.regions) == 2 and task.current.literal is None and len(task.candidates) == 4
    settle(rig, Scripted({"taxon": cannot_resolve("sp. 30 \N{FEMALE SIGN}", asks=["sp. 30 \N{FEMALE SIGN}"])}),
        tools=NoGenus(rig.blobs))
    assert run.fields["taxon"].state == ValueState.UNRESOLVED
    assert taxon_reasons(run) == list(TAXON_REASONS)


def test_a_code_the_organiser_gave_with_no_candidate_clears_unmatched_on_the_units_path(tmp_path):
    """units-wp15c's r2/pair 105526324: the organiser's value is the code "Sp 22", unresolved, with no
    candidate row. On the units path the label settles the code the expert quotes."""
    rig = build_rig(tmp_path, without_the_taxon_line("Sp 22"))
    run = rig.specimen.run
    run.fields["taxon"] = FieldValue(state=ValueState.UNRESOLVED, literal="Sp 22")
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "taxon"]
    assert (task.current.literal, task.candidates) == ("Sp 22", ())
    settle(rig, Scripted({"taxon": cannot_resolve("Sp 22", asks=["Sp 22"])}), tools=NoGenus(rig.blobs))
    taxon = run.fields["taxon"]
    assert (taxon.state, taxon.literal, taxon.reason) == (ValueState.SUPPORTED, "Sp 22", field_step.UNMATCHED)
    assert taxon_reasons(run) == []


def test_a_label_settling_another_code_than_the_one_quoted_never_clears(tmp_path):
    """The label writes "sp.30" and, on the next line, "sp. 39"; the organiser's verbatims give "sp. 39",
    the one text the label settles, cleared; the expert quotes "Sp. 30", which no reading writes as it
    is. The settled text is another code, so the taxon stays unresolved."""
    rig = build_rig(tmp_path, without_the_taxon_line("sp.30\nsp. 39"))
    run = rig.specimen.run
    run.fields["taxon"] = FieldValue(state=ValueState.AMBIGUOUS,
        verbatim_by_observation={item.id: "sp. 39" for item in run.observations})
    settle(rig, Scripted({"taxon": cannot_resolve("Sp. 30", asks=["Sp. 30"])}), tools=NoGenus(rig.blobs))
    assert run.fields["taxon"].state != ValueState.SUPPORTED
    assert taxon_reasons(run) == list(TAXON_REASONS)


def test_a_taxon_the_labels_do_not_write_still_goes_to_review(tmp_path):
    """The rules' instructions have the expert answer label_lacks_value where the labels write only a
    host: the taxon is then not present, and as a mandatory field it keeps both review reasons
    (PRD.md:494, :503)."""
    rig = build_rig(tmp_path, without_the_taxon_line("Host Thomomys"))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": answering(FieldAnswer(outcome="label_lacks_value",
        explanation="The labels write only the host, Thomomys."))}), tools=FakeSources(rig.blobs))
    assert run.fields["taxon"].state == ValueState.NOT_PRESENT
    assert taxon_reasons(run) == list(TAXON_REASONS)


@pytest.mark.parametrize("second", ["Epipsocus\ndet. E. L. Mockford", "Epipsocus", "epipsocus"])
def test_a_code_beside_a_genus_on_another_label_never_clears(tmp_path, monkeypatch, second):
    """Codex's round 1, finding 2, G51's P1 and Codex's round 2, finding 1 (the genus in lower case):
    label 1 writes "sp. 30 <female sign>" alone, label 2 a genus; the organiser gives the taxon no
    value, and the expert asks GBIF the code only and quotes it. A word that may be a genus on any
    label, whatever its case, holds owner decision B back (step._genus_on_a_label): the taxon stays
    unresolved, as on main."""
    test_step.a_second_label(monkeypatch, second)
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 30 \N{FEMALE SIGN}"))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve("sp. 30 \N{FEMALE SIGN}", asks=["sp. 30 \N{FEMALE SIGN}"])}),
        tools=NoGenus(rig.blobs))
    assert (run.fields["taxon"].state, run.fields["taxon"].literal) == (ValueState.UNRESOLVED, "sp. 30 \N{FEMALE SIGN}")
    assert taxon_reasons(run) == list(TAXON_REASONS)


def test_words_the_specimen_accounts_for_do_not_hold_the_code_back_on_the_units_path(tmp_path):
    """Below the code, words that begin with a capital and are no genus: the notation "CNHM.", a
    catalogue number with its prefix, a slide code's Roman month written with spaces, and "Wings" (a
    word of checks.NOT_GENERA). The taxon clears unmatched on the units path."""
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 22\nCNHM.\nFMNHINS 4486784\nIX -3- 66-10\nWings"))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve("sp. 22", asks=["sp. 22"])}), tools=NoGenus(rig.blobs))
    expected = ValueState.SUPPORTED
    assert (run.fields["taxon"].state, run.fields["taxon"].literal) == (expected, "sp. 22")


def test_another_reader_s_spelling_of_a_settled_field_s_text_does_not_hold_the_code_back_on_the_units_path(
        tmp_path, monkeypatch):
    """Reader 1B writes the habitat "Synthetic Grassland" where 1A writes "Synthetic grassland", the
    habitat settled on 1A's text: 1B's "Grassland" lies in a unit whose other reader's text the habitat
    holds, so it is accounted for, and the code clears unmatched on the units path."""
    monkeypatch.setattr(test_step, "seen_units", naming("grassland"))
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 22"),
        without_the_taxon_line("sp. 22").replace("Synthetic grassland", "Synthetic Grassland"),
        candidates=[*COLLECTORS, *IRN])
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve("sp. 22", asks=["sp. 22"])}), tools=NoGenus(rig.blobs))
    assert run.fields["habitat"].literal == "Synthetic grassland"
    expected = ValueState.SUPPORTED
    assert run.fields["taxon"].state == expected


def as_one_unit(text):
    """A units-path first pass that cuts the label writing `text` as one unit, the image naming it (G51's
    round 2 probe), and every other label as test_step.seen_units does."""
    original = test_step.seen_units

    def seen(units):
        units = original(units)
        first = units.units[0]
        if not any(text.split()[0] in span.text for span in first.readers.values()):
            return units
        readers = {key: span.model_copy(update={"text": text, "start": 0, "end": len(text)})
            for key, span in first.readers.items()}
        merged = first.model_copy(update={"readers": readers, "lines": (first.lines[0], units.units[-1].lines[1]),
            "image": text})
        return units.model_copy(update={"units": [merged]})
    return seen


@pytest.mark.parametrize("second", ["Epipsocus det. Mockford", "Epipsocus\ndet. Mockford", "Epipsocus \N{FEMALE SIGN}",
    "Epipsocus\nCNHM", "Epipsocus\N{FEMALE SIGN}", "C. pipiens"])
def test_a_genus_sharing_a_unit_with_notation_text_never_clears(
        tmp_path, monkeypatch, second):
    """G51's round 2 and the coordinator's ruling: label 2, cut as one unit, writes a genus beside a
    notation's text ("det.", a sex sign, "CNHM", glued or not), or an epithet beside an abbreviated
    genus. A word only partly inside accounted text is not accounted for, and a unit carries coverage
    only from a reader's text wholly accounted for: the taxon stays unresolved, as on main."""
    monkeypatch.setattr(test_step, "seen_units", as_one_unit(second))
    test_step.a_second_label(monkeypatch, second)
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 30 \N{FEMALE SIGN}"))
    run = rig.specimen.run
    [cut] = {tuple(tuple(span.text for span in unit.readers.values()) for unit in reading.units.units)
        for reading in field_step.run_readings(run) if reading.region_id == run.regions[1].id}
    assert cut == ((second, second),)
    settle(rig, Scripted({"taxon": cannot_resolve("sp. 30 \N{FEMALE SIGN}", asks=["sp. 30 \N{FEMALE SIGN}"])}),
        tools=NoGenus(rig.blobs))
    assert run.fields["taxon"].state == ValueState.UNRESOLVED
    assert taxon_reasons(run) == list(TAXON_REASONS)


@pytest.mark.parametrize("covered", ["\N{FEMALE SIGN}", "CNHM", "det."])
def test_a_reader_s_covered_text_carries_only_to_the_same_words_at_its_unit(tmp_path, monkeypatch, covered):
    """G51's round 3 and the coordinator's ruling: at one unit reader A writes only a notation's token
    and reader B "Epipsocus <female sign>". A's text is accounted for, but B's writes other words, so
    the coverage does not carry and B's "Epipsocus" may be a genus (step._same_words)."""
    import dataclasses

    second = "Epipsocus \N{FEMALE SIGN}"
    monkeypatch.setattr(test_step, "seen_units", as_one_unit(second))
    test_step.a_second_label(monkeypatch, second)
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 30 \N{FEMALE SIGN}"))
    run = rig.specimen.run
    readings = list(field_step.run_readings(run))
    region = run.regions[1].id
    first, other = [reading for reading in readings if reading.region_id == region][:2]
    units = first.units
    if units is not None:
        unit = units.units[0]
        readers = dict(unit.readers)
        readers[first.observation_id] = readers[first.observation_id].model_copy(update={
            "text": covered, "start": 0, "end": len(covered)})
        units = units.model_copy(update={"units": [unit.model_copy(update={"readers": readers})]})
    changed = [dataclasses.replace(reading, units=units if reading.region_id == region else reading.units,
        text=covered if reading.name == first.name else reading.text) for reading in readings]
    assert other.text == second and field_step._genus_on_a_label(run, changed) == "Epipsocus"
    assert field_step._same_words("Synthetic grassland", "Synthetic Grassland")
    assert not field_step._same_words(covered, second)


def test_the_organiser_s_code_beside_a_genus_on_another_label_never_clears_on_the_units_path(
        tmp_path, monkeypatch):
    """G51's P1b and the coordinator's ruling on it: the organiser's value and candidates are label 1's
    "sp. 30 <female sign>", label 2 writes "Epipsocus" with its determiner. On the units path owner
    decision B's organiser branch declines too (step._genus_on_a_label)."""
    test_step.a_second_label(monkeypatch, "Epipsocus\ndet. E. L. Mockford")
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 30 \N{FEMALE SIGN}"), candidates=[*COLLECTORS,
        *(("taxon", name, "sp. 30 \N{FEMALE SIGN}", "sp. 30 \N{FEMALE SIGN}") for name in ("1A", "1B"))])
    run = rig.specimen.run
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "taxon"]
    assert task.current.literal == "sp. 30 \N{FEMALE SIGN}" and len(task.candidates) == 2
    settle(rig, Scripted({"taxon": cannot_resolve("sp. 30 \N{FEMALE SIGN}", asks=["sp. 30 \N{FEMALE SIGN}"])}),
        tools=NoGenus(rig.blobs))
    assert run.fields["taxon"].state == ValueState.UNRESOLVED
    assert taxon_reasons(run) == list(TAXON_REASONS)


def test_the_organiser_s_code_beside_another_spelling_on_another_label_never_clears_on_the_units_path(
        tmp_path, monkeypatch):
    """The coordinator's ruling on P1b, its second condition: the organiser's value and candidates are
    label 1's "sp. 30 <female sign>", and label 2 writes "Sp.30 <female sign>". On the units path every
    label whose readings write the code must be among the labels that settle, whichever branch reaches
    owner decision B."""
    test_step.a_second_label(monkeypatch, "Sp.30 \N{FEMALE SIGN}")
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 30 \N{FEMALE SIGN}"), candidates=[*COLLECTORS,
        *(("taxon", name, "sp. 30 \N{FEMALE SIGN}", "sp. 30 \N{FEMALE SIGN}") for name in ("1A", "1B"))])
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve("sp. 30 \N{FEMALE SIGN}", asks=["sp. 30 \N{FEMALE SIGN}"])}),
        tools=NoGenus(rig.blobs))
    expected = ValueState.UNRESOLVED
    assert run.fields["taxon"].state == expected


def test_an_unsettled_field_s_text_accounts_for_nothing(tmp_path, monkeypatch):
    """The habitat's expert finds no habitat, so its line, which the organiser's row still cites, is no
    settled field's occurrence: its words may be a genus and hold the code back on the units path."""
    words = test_step.genus_words(monkeypatch)
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 22"))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve("sp. 22", asks=["sp. 22"]),
        "habitat": answering(FieldAnswer(outcome="label_lacks_value", explanation="No habitat."))}),
        tools=NoGenus(rig.blobs))
    assert run.fields["habitat"].state == ValueState.NOT_PRESENT
    assert set(words) == {"Synthetic"} and run.fields["taxon"].state == ValueState.UNRESOLVED


def test_a_word_only_partly_inside_a_settled_field_s_occurrence_is_not_accounted_for(tmp_path):
    """A settled field's occurrence, at its row's offsets, covers "Epi" of the label's "Epipsocus": the
    word is not wholly inside it, so it may be a genus (step._genus_on_a_label); nor is it when another
    settled field's occurrence covers "psocus" (Codex's round 3)."""
    from specimen_digitization.application.organiser import CandidateLocation, format_locator

    rig = build_rig(tmp_path, without_the_taxon_line("Epipsocus"))
    run = rig.specimen.run
    readings = field_step.run_readings(run)
    assert field_step._genus_on_a_label(run, readings) == "Epipsocus"
    reading = next(r for r in readings if r.name == "1A")
    row = Evidence(kind="literal", region_id=reading.region_id, observation_ids=[reading.observation_id],
        source="test", locator=format_locator(CandidateLocation("1A", reading.observation_id, 0, 3, 0, 3)),
        excerpt="Epi")
    run.evidence.append(row)
    run.fields["collection_method"] = FieldValue(state=ValueState.SUPPORTED, literal="Epi", evidence_ids=[row.id])
    assert field_step._genus_on_a_label(run, readings) == "Epipsocus"
    # Codex's round 3: a second settled field's occurrence cites the rest of the word, [3, 9). Two spans
    # that meet do not hold the word: only one single span does.
    other = Evidence(kind="literal", region_id=reading.region_id, observation_ids=[reading.observation_id],
        source="test", locator=format_locator(CandidateLocation("1A", reading.observation_id, 3, 9, 3, 9)),
        excerpt="psocus")
    run.evidence.append(other)
    run.fields["habitat"] = FieldValue(state=ValueState.SUPPORTED, literal="psocus", evidence_ids=[other.id])
    assert field_step._genus_on_a_label(run, readings) == "Epipsocus"
    row.locator = format_locator(CandidateLocation("1A", reading.observation_id, 0, 9, 0, 9))
    row.excerpt = run.fields["collection_method"].literal = "Epipsocus"
    assert field_step._genus_on_a_label(run, readings) != "Epipsocus"


@pytest.mark.parametrize("provenance", ["verbatim", "keyed-line-row"])
def test_a_verbatim_or_a_row_with_no_offsets_accounts_only_for_its_own_label(tmp_path, monkeypatch, provenance):
    """Label 2 and label 3 each write "Aedes"; a settled collection code "Aedes" whose provenance is
    label 3's alone, a reader's verbatim or a row with no offsets (a keyed line's, locator
    "region:<id>"), accounts for label 3's word only: label 2's stays a possible genus."""
    test_step.a_second_label(monkeypatch, "Aedes")
    test_step.a_second_label(monkeypatch, "Aedes")
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 30 \N{FEMALE SIGN}"))
    run = rig.specimen.run
    readings = field_step.run_readings(run)
    third = [reading for reading in readings if reading.region_id == run.regions[2].id]
    value = FieldValue(state=ValueState.SUPPORTED, literal="Aedes", source_region_id=run.regions[2].id)
    if provenance == "verbatim":
        value.verbatim_by_observation = {reading.observation_id: "Aedes" for reading in third}
    else:
        row = Evidence(kind="literal", region_id=run.regions[2].id, observation_ids=[r.observation_id for r in third],
            source="test", locator="region:" + run.regions[2].id, excerpt="Aedes")
        run.evidence.append(row)
        value.evidence_ids = [row.id]
    run.fields["collection_code"] = value
    covered = [reading.name for reading in readings if reading.region_id == run.regions[2].id]
    assert covered and field_step._genus_on_a_label(run, [r for r in readings if r.region_id != run.regions[1].id
        and r.region_id != run.regions[0].id]) is None
    assert field_step._genus_on_a_label(run, [r for r in readings if r.region_id != run.regions[0].id]) == "Aedes"


def test_another_field_s_text_accounts_only_for_the_label_its_provenance_cites(tmp_path, monkeypatch):
    """Codex's round 2, finding 2: label 2 writes "Aedes" as the identification and label 3 "Aedes",
    settled as the collection code from label 3 alone. The collection code accounts for label 3's
    word only, so label 2's genus holds owner decision B back: the taxon stays unresolved."""
    test_step.a_second_label(monkeypatch, "Aedes")
    test_step.a_second_label(monkeypatch, "Aedes")
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 30 \N{FEMALE SIGN}").replace(
        "collection_code: " + LABEL["collection_code"] + "\n", ""))
    run = rig.specimen.run
    names = {reading.name: reading.region_id for reading in field_step.run_readings(run)}
    assert len(run.regions) == 3 and names["3A"] == run.regions[2].id
    settle(rig, Scripted({"taxon": cannot_resolve("sp. 30 \N{FEMALE SIGN}", asks=["sp. 30 \N{FEMALE SIGN}"]),
        "collection_code": answering(resolved("Aedes", reading="3A"))}), tools=NoGenus(rig.blobs))
    assert (run.fields["collection_code"].state, run.fields["collection_code"].literal) == (ValueState.SUPPORTED, "Aedes")
    assert run.fields["taxon"].state == ValueState.UNRESOLVED
    assert taxon_reasons(run) == list(TAXON_REASONS)


def test_a_second_label_writing_another_spelling_of_the_code_holds_it_back(tmp_path, monkeypatch):
    """G51's P2: label 1 writes "sp. 30 <female sign>", label 2 "Sp.30 <female sign>", no organiser
    candidate. Label 2 writes the code but settles no text of it: the taxon stays unresolved."""
    test_step.a_second_label(monkeypatch, "Sp.30 \N{FEMALE SIGN}")
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 30 \N{FEMALE SIGN}"))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve("sp. 30 \N{FEMALE SIGN}", asks=["sp. 30 \N{FEMALE SIGN}"])}),
        tools=NoGenus(rig.blobs))
    assert run.fields["taxon"].state == ValueState.UNRESOLVED
    assert taxon_reasons(run) == list(TAXON_REASONS)


def test_a_code_a_person_settled_as_another_field_never_clears_as_the_taxon(tmp_path):
    """Codex's round 1, finding 3: a person settled the label's "sp. 30 <female sign>" as the collection
    code. Owner decision B's value is guarded as a resolved answer is (step._taken): the taxon stays
    unresolved, the reason naming the collection code."""
    from specimen_digitization.application.human_field_carry import KEY as CARRY_KEY

    rig = build_rig(tmp_path, without_the_taxon_line("sp. 30 \N{FEMALE SIGN}").replace(
        "collection_code: " + LABEL["collection_code"] + "\n", ""))
    run = rig.specimen.run
    run.dependencies[CARRY_KEY] = {"collection_code": {}}
    run.fields["collection_code"] = FieldValue(state=ValueState.SUPPORTED, literal="sp. 30 \N{FEMALE SIGN}",
        source_region_id=run.regions[0].id)
    settle(rig, Scripted({"taxon": cannot_resolve("sp. 30 \N{FEMALE SIGN}", asks=["sp. 30 \N{FEMALE SIGN}"])}),
        tools=NoGenus(rig.blobs))
    assert run.fields["taxon"].state == ValueState.UNRESOLVED
    assert run.fields["taxon"].reason.startswith(field_step.TAKEN.format(other="Collection Code"))
    assert taxon_reasons(run) == list(TAXON_REASONS)


# ---- a host is never the taxon (cause E2) ---------------------------------------------------------

class HostGbif(FakeSources):
    """GBIF deciding each name of `names` (a success, its candidate the name with its authorship),
    as it would for a host GBIF finds inside Insecta."""

    def __init__(self, blobs, names):
        super().__init__(blobs)
        self.names = names

    def _answer(self, source_id, query):
        if source_id != "gbif" or query not in self.names:
            return super()._answer(source_id, query)
        name, key = self.names[query], "gbif:H" + str(len(query))
        raw = json.dumps({"source": "gbif", "query": query}).encode()
        ref, sha = self.blobs.put(raw), hashlib.sha256(raw).hexdigest()
        evidence = Evidence(kind="authority", source="gbif", locator=key,
            excerpt=f"GBIF: exact accepted match\n{name} | {key} | GENUS | ", raw_ref=ref, digest=sha)
        lookup = Lookup(provider="gbif", adapter_version="test", query={"name": query}, status=LookupStatus.SUCCESS,
            candidates=[{"key": key, "scientificName": name}], raw_ref=ref, digest=sha)
        return SourceAnswer("gbif", query, LookupStatus.SUCCESS, (SourceCandidate(name=name, authority_id=key,
            kind="GENUS"),), evidence, note="exact", taxonomy_lookup=lookup)


def deciding(literal, name):
    async def script(task, readings, tools):
        answer = await tools.lookup("gbif", literal, field_key=task.key)
        return FieldOutcome(task.key, resolved(literal, value=name, authority_id=answer.candidates[0].authority_id,
            cited=[answer.evidence.id]), evidence=[answer.evidence], lookups=[answer.taxonomy_lookup], model_calls=1)
    return script


@pytest.mark.parametrize(("line", "literal", "name"), [
    ("Host Thomomys", "Thomomys", "Thomomys Wied-Neuwied, 1839"),
    ("Ex. Canis familiaris", "Canis familiaris", "Canis familiaris Linnaeus, 1758"),
    ("ex Peromyscus leucopus", "Peromyscus leucopus", "Peromyscus leucopus (Rafinesque, 1818)"),
    ("on Quercus alba", "Quercus alba", "Quercus alba L."),
    ("from Vulpes vulpes", "Vulpes vulpes", "Vulpes vulpes (Linnaeus, 1758)"),
], ids=["Host", "Ex.", "ex", "on", "from"])
def test_a_name_written_after_a_host_marker_is_never_the_taxon_on_the_units_path(
        tmp_path, line, literal, name):
    """units-wp15c's 105526459 ("Host Thomomys") and 105526596 ("Ex. Canis familiaris"), with GBIF
    deciding the name: the answer is refused and the taxon is left for a person."""
    rig = build_rig(tmp_path, without_the_taxon_line(line))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": deciding(literal, name)}), tools=HostGbif(rig.blobs, {literal: name}))
    taxon = run.fields["taxon"]
    assert taxon.state == ValueState.UNRESOLVED
    assert taxon.reason.startswith("The label writes this name as the host the specimen was taken from")
    assert taxon_reasons(run) == list(TAXON_REASONS)


def test_an_organiser_candidate_written_after_a_host_marker_is_never_the_taxon_on_the_units_path(
        tmp_path):
    """The organiser's candidate "Thomomys", quoted from "Host Thomomys": the answer naming it (its
    candidate basis) is refused on the units path, as text read from the transcript is."""
    rig = build_rig(tmp_path, without_the_taxon_line("Host Thomomys"), candidates=[*COLLECTORS,
        *(("taxon", name, "Thomomys", "Host Thomomys") for name in ("1A", "1B"))])
    run = rig.specimen.run
    name = "Thomomys Wied-Neuwied, 1839"
    settle(rig, Scripted({"taxon": deciding("Thomomys", name)}), tools=HostGbif(rig.blobs, {"Thomomys": name}))
    taxon = run.fields["taxon"]
    assert taxon.state == ValueState.UNRESOLVED
    assert taxon.reason.startswith("The label writes this name as the host the specimen was taken from")


def test_another_field_s_text_after_a_marker_settles(tmp_path):
    """The host marker is the taxon's rule only: a habitat written "on oak bark" settles as written."""
    rig = build_rig(tmp_path, TEXT.replace("habitat: " + LABEL["habitat"], "habitat: on oak bark"))
    run = rig.specimen.run
    settle(rig, Scripted({"habitat": answering(resolved("on oak bark"))}), tools=FakeSources(rig.blobs))
    assert (run.fields["habitat"].state, run.fields["habitat"].literal) == (ValueState.SUPPORTED, "on oak bark")


@pytest.mark.parametrize("line", ["Mex. Danaus plexippus", "Hosts Danaus plexippus", "Upon Danaus plexippus"])
def test_a_name_after_a_word_that_only_ends_in_a_marker_settles(tmp_path, line):
    rig = build_rig(tmp_path, without_the_taxon_line(line))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": deciding("Danaus plexippus", test_step.GBIF_NAME)}), tools=FakeSources(rig.blobs))
    assert (run.fields["taxon"].state, run.fields["taxon"].literal) == (ValueState.SUPPORTED, "Danaus plexippus")


def test_a_name_another_label_writes_inside_a_host_s_longer_name_settles(tmp_path, monkeypatch):
    """Codex's round 1, finding 1: the specimen's "Musca", GBIF deciding it, beside another label writing
    "Host Muscardinus avellanarius": "Musca" is not written there as a whole name, so it settles."""
    test_step.a_second_label(monkeypatch, "Host Muscardinus avellanarius")
    rig = build_rig(tmp_path, without_the_taxon_line("Musca"))
    run = rig.specimen.run
    name = "Musca Linnaeus, 1758"
    settle(rig, Scripted({"taxon": deciding("Musca", name)}), tools=HostGbif(rig.blobs, {"Musca": name}))
    assert (run.fields["taxon"].state, run.fields["taxon"].normalized) == (ValueState.SUPPORTED, name)


def test_a_name_after_a_marker_earlier_on_its_line_is_never_the_taxon_on_the_units_path(tmp_path):
    """Codex's round 1, finding 4: "from nest of Formica rufa", the organiser's candidate "Formica rufa"
    and GBIF deciding it. Nothing shows the nest's ant is the specimen: on the units path the answer is
    refused."""
    rig = build_rig(tmp_path, without_the_taxon_line("from nest of Formica rufa"), candidates=[*COLLECTORS,
        *(("taxon", name, "Formica rufa", "from nest of Formica rufa") for name in ("1A", "1B"))])
    run = rig.specimen.run
    name = "Formica rufa Linnaeus, 1761"
    settle(rig, Scripted({"taxon": deciding("Formica rufa", name)}), tools=HostGbif(rig.blobs, {"Formica rufa": name}))
    taxon = run.fields["taxon"]
    assert taxon.state == ValueState.UNRESOLVED
    assert taxon.reason.startswith("The label writes this name as the host the specimen was taken from")


def test_a_name_before_a_marker_on_its_line_settles(tmp_path):
    """The coordinator's ruling on finding 4: "Aus bus on Quercus" settles "Aus bus"."""
    rig = build_rig(tmp_path, without_the_taxon_line("Aus bus on Quercus"))
    run = rig.specimen.run
    name = "Aus bus Smith, 1900"
    settle(rig, Scripted({"taxon": deciding("Aus bus", name)}), tools=HostGbif(rig.blobs, {"Aus bus": name}))
    assert (run.fields["taxon"].state, run.fields["taxon"].normalized) == (ValueState.SUPPORTED, name)


def test_the_host_markers_are_the_ontology_s_notation():
    from specimen_digitization.field_research.taxon_host import host_markers

    assert host_markers() == frozenset({"host", "ex", "on", "from"})


@pytest.mark.parametrize(("literal", "texts", "host"), [
    ("Thomomys", ["Host Thomomys"], True),
    ("Thomomys", ["Host: Thomomys"], True),
    ("Thomomys", ["(ex Thomomys)"], True),
    ("Canis familiaris", ["Ex. Canis familiaris"], True),
    ("Canis familiaris", ["Ex.Canis familiaris"], True),
    ("Canis familiaris", ["ex  Canis\tfamiliaris"], True),
    ("Peromyscus\nleucopus", ["24 Apr 1973\nex Peromyscus\nleucopus"], True),
    ("Ex. Canis familiaris", ["Ex. Canis familiaris"], True),
    ("Host Thomomys", ["Host Thomomys"], True),
    ("Quercus alba", ["ON Quercus alba"], True),
    ("Vulpes", ["from Vulpes"], True),
    ("Canis familiaris", ["Canis familiaris", "ex Canis familiaris"], True),
    ("Canis familiaris", ["Canis familiaris\nex Canis familiaris"], True),
    ("Formica rufa", ["from nest of Formica rufa"], True),
    ("Aus bus", ["from nest of Aus bus"], True),
    ("Aus bus", ["Aus bus on Quercus"], False),
    ("Musca", ["Musca", "Host Muscardinus avellanarius"], False),
    ("Aedes", ["Aedes", "on Aedesia sp."], False),
    ("Canis familiaris", ["Mex. Canis familiaris"], False),
    ("Canis familiaris", ["ex XCanis familiaris"], False),
    ("Canis familiaris", ["Ixex Canis familiaris"], False),
    ("Thomomys", ["Hosts Thomomys"], False),
    ("Thomomys", ["Upon Thomomys"], False),
    ("Thomomys", ["Thomomys from Utah"], False),
    ("Thomomys", ["ex\nThomomys"], False),
    ("CYNOMYS", ["LEWIS COLLECTION\nCYNOMYS"], False),
    ("Danaus plexippus", ["taxon: Danaus plexippus"], False),
    ("", ["ex "], False),
], ids=lambda value: repr(value) if isinstance(value, str) else None)
def test_a_host_is_a_whole_name_after_a_whole_word_marker_earlier_on_its_line(literal, texts, host):
    from specimen_digitization.field_research.taxon_host import host_written

    assert host_written(literal, texts) is host


# ---- GBIF's record inside the collection's higher taxon (cause F3) ---------------------------------

def stored(name, *, class_of=None):
    """The stored GBIF answer for `name` (gbif_wp15c_match_bodies.json), through GbifTaxonomy, with
    `class_of` giving an exact alternative's class (by its usage's name) in place of the stored one."""
    body = copy.deepcopy(BODIES[name]["body"])
    for alternative in body["diagnostics"]["alternatives"]:
        if class_of and alternative["usage"]["name"] in class_of:
            for level in alternative["classification"]:
                if level["rank"] == "CLASS":
                    level["name"] = class_of[alternative["usage"]["name"]]

    def handler(request):
        if request.url.path.endswith("/metadata"):
            return httpx.Response(200, json={"alias": "fixture-index"})
        return httpx.Response(200, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("name", ["Cynomys", "Citellus", "Canis familiaris", "Thomomys"])
def test_a_name_whose_every_exact_gbif_record_lies_outside_insecta_never_succeeds(tmp_path, name):
    """units-wp15c's hosts written without a marker: every exact record GBIF gave is a mammal's."""
    found = GbifTaxonomy(LocalBlobs(tmp_path), stored(name)).lookup(name)
    assert found.query == {**BODIES[name]["query"], "checklistKey": COL_XR}
    assert (found.status.value, found.status) == (BODIES[name]["stored_status"], LookupStatus.AMBIGUOUS)


def test_epipsocus_names_two_genera_inside_insecta_and_stays_ambiguous(tmp_path):
    """units-wp15c's 105526328: GBIF's exact records of "Epipsocus" in Insecta are the accepted
    Epipsocus Hagen, 1866 and Epipsocus Badonnel, 1955, a synonym whose accepted name is another
    genus, Epipsocopsis Badonnel, 1955: a homonym inside the scope, so no record settles it."""
    [synonym] = [alternative for alternative in BODIES["Epipsocus"]["body"]["diagnostics"]["alternatives"]
        if alternative["usage"]["name"] == "Epipsocus Badonnel, 1955"]
    assert synonym["acceptedUsage"]["name"] == "Epipsocopsis Badonnel, 1955"
    assert GbifTaxonomy(LocalBlobs(tmp_path), stored("Epipsocus")).lookup("Epipsocus").status == LookupStatus.AMBIGUOUS


def test_the_one_accepted_insecta_record_settles_a_name_whose_homonym_lies_outside_insecta(tmp_path):
    """The stored "Epipsocus" answer with its other exact record moved to another class: the one
    accepted record inside Insecta is GBIF's decision, its first candidate."""
    found = GbifTaxonomy(LocalBlobs(tmp_path), stored("Epipsocus", class_of={
        "Epipsocus Badonnel, 1955": "Mammalia"})).lookup("Epipsocus")
    assert found.status == LookupStatus.SUCCESS
    assert (found.candidates[0]["scientificName"], found.candidates[0]["status"]) == ("Epipsocus Hagen, 1866", "ACCEPTED")
