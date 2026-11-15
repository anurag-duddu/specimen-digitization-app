"""WP 2.T: the taxon in the collection's scope, on the units path.

- A code with no genus the organiser left as no value (owner decision B, step._unmatched_taxon):
  the units-wp15c cases "sp. 30 <female sign>", "Sp.30 <female sign>" and "sp. 22".
- A name a label writes after a host marker is never the taxon (agreement._host, the ontology's
  rule host_is_no_taxon): the units-wp15c cases "Host Thomomys" and "Ex. Canis familiaris".
- GBIF succeeds only on its accepted record inside class Insecta, the collection's higher taxon
  (application.lookup.row_one, homonym_conflict; the rule taxon_in_collection_scope), on the
  stored answers of units-wp15c's runs (tests/fixtures/gbif_wp15c_match_bodies.json).

Every test that builds a run runs on both paths (conftest.py); the old path keeps main's result."""

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
from specimen_digitization.application.lookup import GbifTaxonomy
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


def taxon_reasons(run):
    return [reason for reason in run.reasons if reason in TAXON_REASONS]


# ---- owner decision B with no organiser value (cause E3) ----------------------------------------

@pytest.mark.parametrize("code", ["sp. 30 \N{FEMALE SIGN}", "Sp.30 \N{FEMALE SIGN}", "sp. 22"])
def test_a_code_with_no_genus_the_organiser_gave_no_value_clears_unmatched_on_the_units_path(
        tmp_path, first_pass_path, code):
    """units-wp15c's 105526321, 105526322 and 105526326: the organiser left the taxon without a
    value or a candidate, its expert asked GBIF the code and answered sources_cannot_resolve quoting
    it, and no label writes a genus. On the units path the taxon clears as written, unmatched; the
    old path keeps main's result, unresolved with the code as its text."""
    rig = build_rig(tmp_path, without_the_taxon_line(code))
    run = rig.specimen.run
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "taxon"]
    assert (task.current.literal, task.candidates) == (None, ())
    settle(rig, Scripted({"taxon": cannot_resolve(code, asks=[code])}), tools=NoGenus(rig.blobs))
    taxon = run.fields["taxon"]
    evidence = {item.id: item for item in run.evidence}
    if first_pass_path == "units":
        assert (taxon.state, taxon.literal, taxon.normalized, taxon.authority_id, taxon.layer) == (
            ValueState.SUPPORTED, code, None, None, "settled")
        assert taxon.reason == field_step.UNMATCHED
        assert field_step.taxon_unmatched(taxon, evidence, run.lookups, run=run)
        assert taxon_reasons(run) == []
    else:
        assert (taxon.state, taxon.literal) == (ValueState.UNRESOLVED, code)
        assert taxon_reasons(run) == list(TAXON_REASONS)


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
        tmp_path, monkeypatch, first_pass_path):
    """units-wp15c's 105526321: 2A writes "sp. 30 <female sign>", 2B "Sp.30 <female sign>", the
    image names 2A's text, and the expert quotes 2B's. On the units path the taxon clears unmatched
    on the text the image names; the old path keeps main's result."""
    monkeypatch.setattr(test_step, "seen_units", naming("sp. 30"))
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 30 \N{FEMALE SIGN}"),
        without_the_taxon_line("Sp.30 \N{FEMALE SIGN}"))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve("Sp.30 \N{FEMALE SIGN}", asks=["Sp.30 \N{FEMALE SIGN}"],
        reading="1B")}), tools=NoGenus(rig.blobs))
    taxon = run.fields["taxon"]
    if first_pass_path == "units":
        assert (taxon.state, taxon.literal, taxon.reason) == (
            ValueState.SUPPORTED, "sp. 30 \N{FEMALE SIGN}", field_step.UNMATCHED)
        assert taxon_reasons(run) == []
    else:
        assert (taxon.state, taxon.literal) == (ValueState.UNRESOLVED, "Sp.30 \N{FEMALE SIGN}")
        assert taxon_reasons(run) == list(TAXON_REASONS)


def test_a_code_the_image_does_not_name_stays_unresolved_on_both_paths(tmp_path, first_pass_path):
    """Rule 4 of the spec's section 4: readers agreeing alone back a text, the image or a source
    clears it. Where the readers spell the code differently and the image names neither, the
    taxon stays unresolved, as on main."""
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 30 \N{FEMALE SIGN}"),
        without_the_taxon_line("Sp.30 \N{FEMALE SIGN}"))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve("sp. 30 \N{FEMALE SIGN}", asks=["sp. 30 \N{FEMALE SIGN}"])}),
        tools=NoGenus(rig.blobs))
    assert (run.fields["taxon"].state, run.fields["taxon"].literal) == (ValueState.UNRESOLVED, "sp. 30 \N{FEMALE SIGN}")
    assert taxon_reasons(run) == list(TAXON_REASONS)


def test_a_code_below_a_genus_keeps_main_s_result_on_both_paths(tmp_path):
    """units-wp15c's 105526328: "Epipsocus" with "Sp. 1" on the line below names a genus, so owner
    decision B does not apply; the taxon stays unresolved."""
    rig = build_rig(tmp_path, without_the_taxon_line("Epipsocus\nSp. 1"))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve("Sp. 1", asks=["Sp. 1"])}), tools=NoGenus(rig.blobs))
    assert (run.fields["taxon"].state, run.fields["taxon"].literal) == (ValueState.UNRESOLVED, "Sp. 1")
    assert taxon_reasons(run) == list(TAXON_REASONS)


def test_a_code_the_expert_does_not_quote_never_clears_on_either_path(tmp_path):
    """The code comes from the expert's own answer only when it quotes a code with no genus: an
    answer quoting another text leaves the taxon unresolved, as on main."""
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 30 \N{FEMALE SIGN}"))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve("30 \N{FEMALE SIGN}", asks=["sp. 30 \N{FEMALE SIGN}"])}),
        tools=NoGenus(rig.blobs))
    assert run.fields["taxon"].state == ValueState.UNRESOLVED
    assert taxon_reasons(run) == list(TAXON_REASONS)


def test_a_code_the_organiser_left_with_no_value_but_its_candidates_clears_unmatched_on_the_units_path(
        tmp_path, monkeypatch, first_pass_path):
    """units-wp15c's r1/pair 105526326: the organiser left the taxon without a value, its candidates
    3A's "sp. 22" and 3B's "Sp. 22", and the image names 3A's text. On the units path the taxon clears
    unmatched on that text; the old path keeps main's result."""
    monkeypatch.setattr(test_step, "seen_units", naming("sp."))
    rig = build_rig(tmp_path, without_the_taxon_line("sp. 22"), without_the_taxon_line("Sp. 22"),
        candidates=[*COLLECTORS, ("taxon", "1A", "sp. 22", "sp. 22"), ("taxon", "1B", "Sp. 22", "Sp. 22")])
    run = rig.specimen.run
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "taxon"]
    assert task.current.literal is None and len(task.candidates) == 2
    settle(rig, Scripted({"taxon": cannot_resolve("sp. 22", asks=["sp. 22", "Sp. 22"])}), tools=NoGenus(rig.blobs))
    taxon = run.fields["taxon"]
    if first_pass_path == "units":
        assert (taxon.state, taxon.literal, taxon.reason) == (ValueState.SUPPORTED, "sp. 22", field_step.UNMATCHED)
        assert taxon_reasons(run) == []
    else:
        assert (taxon.state, taxon.literal) == (ValueState.UNRESOLVED, "sp. 22")
        assert taxon_reasons(run) == list(TAXON_REASONS)


def test_two_labels_settling_two_spellings_of_the_code_never_clear_on_either_path(tmp_path, monkeypatch):
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


def test_a_code_the_organiser_gave_with_no_candidate_clears_unmatched_on_the_units_path(tmp_path, first_pass_path):
    """units-wp15c's r2/pair 105526324: the organiser's value is the code "Sp 22", unresolved, with no
    candidate row. On the units path the label settles the code the expert quotes; the old path keeps
    main's result."""
    rig = build_rig(tmp_path, without_the_taxon_line("Sp 22"))
    run = rig.specimen.run
    run.fields["taxon"] = FieldValue(state=ValueState.UNRESOLVED, literal="Sp 22")
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "taxon"]
    assert (task.current.literal, task.candidates) == ("Sp 22", ())
    settle(rig, Scripted({"taxon": cannot_resolve("Sp 22", asks=["Sp 22"])}), tools=NoGenus(rig.blobs))
    taxon = run.fields["taxon"]
    if first_pass_path == "units":
        assert (taxon.state, taxon.literal, taxon.reason) == (ValueState.SUPPORTED, "Sp 22", field_step.UNMATCHED)
        assert taxon_reasons(run) == []
    else:
        assert (taxon.state, taxon.literal) == (ValueState.UNRESOLVED, "Sp 22")
        assert taxon_reasons(run) == list(TAXON_REASONS)


def test_a_label_settling_another_code_than_the_one_quoted_never_clears_on_either_path(tmp_path):
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


def test_a_taxon_the_labels_do_not_write_still_goes_to_review_on_both_paths(tmp_path):
    """The rules' instructions have the expert answer label_lacks_value where the labels write only a
    host: the taxon is then not present, and as a mandatory field it keeps both review reasons
    (PRD.md:494, :503)."""
    rig = build_rig(tmp_path, without_the_taxon_line("Host Thomomys"))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": answering(FieldAnswer(outcome="label_lacks_value",
        explanation="The labels write only the host, Thomomys."))}), tools=FakeSources(rig.blobs))
    assert run.fields["taxon"].state == ValueState.NOT_PRESENT
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
        tmp_path, first_pass_path, line, literal, name):
    """units-wp15c's 105526459 ("Host Thomomys") and 105526596 ("Ex. Canis familiaris"), with GBIF
    deciding the name: on the units path the answer is refused and the taxon is left for a person;
    the old path keeps main's result, the host settled as the taxon."""
    rig = build_rig(tmp_path, without_the_taxon_line(line))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": deciding(literal, name)}), tools=HostGbif(rig.blobs, {literal: name}))
    taxon = run.fields["taxon"]
    if first_pass_path == "units":
        assert taxon.state == ValueState.UNRESOLVED
        assert taxon.reason.startswith("The label writes this name as the host the specimen was taken from")
        assert taxon_reasons(run) == list(TAXON_REASONS)
    else:
        assert (taxon.state, taxon.literal, taxon.normalized) == (ValueState.SUPPORTED, literal, name)
        assert taxon_reasons(run) == []


def test_an_organiser_candidate_written_after_a_host_marker_is_never_the_taxon_on_the_units_path(
        tmp_path, first_pass_path):
    """The organiser's candidate "Thomomys", quoted from "Host Thomomys": the answer naming it (its
    candidate basis) is refused on the units path, as text read from the transcript is."""
    rig = build_rig(tmp_path, without_the_taxon_line("Host Thomomys"), candidates=[*COLLECTORS,
        *(("taxon", name, "Thomomys", "Host Thomomys") for name in ("1A", "1B"))])
    run = rig.specimen.run
    name = "Thomomys Wied-Neuwied, 1839"
    settle(rig, Scripted({"taxon": deciding("Thomomys", name)}), tools=HostGbif(rig.blobs, {"Thomomys": name}))
    taxon = run.fields["taxon"]
    if first_pass_path == "units":
        assert taxon.state == ValueState.UNRESOLVED
        assert taxon.reason.startswith("The label writes this name as the host the specimen was taken from")
    else:
        assert (taxon.state, taxon.normalized) == (ValueState.SUPPORTED, name)


def test_another_field_s_text_after_a_marker_settles_on_both_paths(tmp_path):
    """The host marker is the taxon's rule only: a habitat written "on oak bark" settles as written."""
    rig = build_rig(tmp_path, TEXT.replace("habitat: " + LABEL["habitat"], "habitat: on oak bark"))
    run = rig.specimen.run
    settle(rig, Scripted({"habitat": answering(resolved("on oak bark"))}), tools=FakeSources(rig.blobs))
    assert (run.fields["habitat"].state, run.fields["habitat"].literal) == (ValueState.SUPPORTED, "on oak bark")


@pytest.mark.parametrize("line", ["Mex. Danaus plexippus", "Hosts Danaus plexippus", "Upon Danaus plexippus"])
def test_a_name_after_a_word_that_only_ends_in_a_marker_settles_on_both_paths(tmp_path, line):
    rig = build_rig(tmp_path, without_the_taxon_line(line))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": deciding("Danaus plexippus", test_step.GBIF_NAME)}), tools=FakeSources(rig.blobs))
    assert (run.fields["taxon"].state, run.fields["taxon"].literal) == (ValueState.SUPPORTED, "Danaus plexippus")


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
    ("Canis familiaris", ["Mex. Canis familiaris"], False),
    ("Canis familiaris", ["Ixex Canis familiaris"], False),
    ("Thomomys", ["Hosts Thomomys"], False),
    ("Thomomys", ["Upon Thomomys"], False),
    ("Thomomys", ["Thomomys from Utah"], False),
    ("Thomomys", ["ex\nThomomys"], False),
    ("CYNOMYS", ["LEWIS COLLECTION\nCYNOMYS"], False),
    ("Danaus plexippus", ["taxon: Danaus plexippus"], False),
    ("", ["ex "], False),
], ids=lambda value: repr(value) if isinstance(value, str) else None)
def test_a_host_is_a_name_right_after_a_whole_word_marker_on_its_line(literal, texts, host):
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
    assert found.query == BODIES[name]["query"]
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
