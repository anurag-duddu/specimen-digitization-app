"""WP 2.4: unit roles, and a field's parts on different labels (docs/execution/units/PLAN.md, the WP 2.4
row; docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4, "Parts on different
labels"; the ontology's rule parts_on_different_labels).

When the reading units name a field's parts (a unit's role: genus, species or author of the taxon; day,
month or year of a date the unit's fields name) on two or more labels, and no one label writes every part
another writes, the field settles neither on one label's part nor on a text no label writes: on the units
path it is ambiguous, each label's parts named in its reason and their texts its options, and marked for a
person on each label that writes a part (step.field_parts, step._field_value, step._settlement). Parts on
one label settle as today.

Every test that builds a run runs on both paths (conftest.py). The old path's readings are its own, with no
units, and it keeps main's result; so does every case of "as today" on both paths, compared with the same
run whose units carry no role."""

from __future__ import annotations

import json

import pytest
import test_step
from test_settlement_rule import findings
from test_step import (
    COLLECTORS,
    GENUS_KEY,
    GENUS_NAME,
    LABEL,
    TEXT,
    Genus,
    Scripted,
    answering,
    build_rig,
    build_tasks,
    reasons_for,
    research,
    resolved,
    settle,
    taxon_on,
)

from specimen_digitization.application.domain import Disposition, ValueState
from specimen_digitization.application.first_pass import alignment_units
from specimen_digitization.application.reading_units import ReadingUnit, ReadingUnits, UnitText
from specimen_digitization.application.workflow import store_reading_units
from specimen_digitization.field_research import reask
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FieldAnswer, Reading
from specimen_digitization.field_research.step import apply_outcomes

GENUS = "taxon: Danaus"
TAXON = [("taxon", name, "Danaus", GENUS) for name in ("1A", "1B")]
DATE = "date_visited_from: 6 Sept"
DATES = [("date_visited_from", name, "6 Sept", DATE) for name in ("1A", "1B")]


def candidates(*given):
    """The organiser's candidates: the collectors' and `given`."""
    return [*COLLECTORS, *given]


def two_labels(tmp_path, monkeypatch, first, second, given):
    """build_rig's specimen with `first` as label 1 and a second label whose readers both write
    `second`, the organiser's candidates `given`."""
    test_step.a_second_label(monkeypatch, second)
    return build_rig(tmp_path, first, candidates=candidates(*given))


def with_roles(rig, label, given):
    """On the units path, label `label`'s units (0 for label 1, 1 for label 2) with the role and
    fields `given` names ({text: (role, fields)}) where a reader writes that text there; the old
    path has no units."""
    run = rig.specimen.run
    region = run.regions[label].id
    entries = [entry for entry in run.reading_units if entry.label == region]
    if not entries:
        return
    [entry] = entries

    def update(unit):
        for text, (role, fields) in given.items():
            if text in {span.text for span in unit.readers.values()}:
                return unit.model_copy(update={"role": role, "fields": list(fields)})
        return unit

    store_reading_units(run, [entry.model_copy(update={"units": [update(unit) for unit in entry.units]})])


def genus_and_species(rig):
    with_roles(rig, 0, {"Danaus": ("genus", ["taxon"])})
    with_roles(rig, 1, {"plexippus": ("species", ["taxon"])})


def several(*options):
    return answering(FieldAnswer(outcome="several_possibilities", options=list(options),
        explanation="The labels write the name's parts apart."))


GENUS_ANSWERS = {
    # One part answered as the whole: GBIF's genus for label 1's "Danaus".
    "one-part": (lambda: taxon_on("Danaus", value=GENUS_NAME, authority_id=GENUS_KEY, literal="Danaus"),
        "Settled."),
    # The answer the rule's instruction asks for.
    "several": (lambda: several("Danaus", "plexippus"), "The labels write the name's parts apart."),
}


def marked_on_both_labels(run, key):
    regions = [region.id for region in run.regions]
    codes = [f"marked:{key}:{region}:parts_on_labels" for region in regions]
    assert findings(run, key) == sorted((code, "warning") for code in codes)
    assert sorted(reason for reason in reasons_for(run, key) if reason.startswith("marked:")) == sorted(codes)
    assert run.disposition == Disposition.REVIEW


# ---- the PLAN row's named cases, each on both paths ---------------------------------------------

@pytest.mark.parametrize("answer", GENUS_ANSWERS, ids=GENUS_ANSWERS)
def test_a_genus_on_label_1_and_its_species_on_label_2_are_ambiguous_with_each_label_s_part(
        tmp_path, monkeypatch, first_pass_path, answer):
    """ "Aus" on label 1 and "bus" on label 2: on the units path the taxon is ambiguous, its reason
    naming each label's part, the parts its options, and a marked finding on each label; the old
    path keeps main's result (the genus settles on GBIF's decision; the expert's options stay
    ambiguous)."""
    script, explanation = GENUS_ANSWERS[answer]
    rig = two_labels(tmp_path, monkeypatch, TEXT.replace("taxon: Danaus plexippus", GENUS), "plexippus", TAXON)
    genus_and_species(rig)
    settle(rig, Scripted({"taxon": script()}), tools=Genus(rig.blobs))
    run = rig.specimen.run
    taxon = run.fields["taxon"]
    if first_pass_path == "old":
        if answer == "one-part":
            assert (taxon.state, taxon.literal, taxon.normalized) == (ValueState.SUPPORTED, "Danaus", GENUS_NAME)
        else:
            assert (taxon.state, taxon.reason) == (ValueState.AMBIGUOUS, f"{explanation} Options: Danaus; plexippus.")
        assert findings(run, "taxon") == []
        return
    assert (taxon.state, taxon.literal) == (ValueState.AMBIGUOUS, None)
    assert taxon.reason == ("The field's parts are on different labels: label 1 writes genus Danaus; label 2 "
        f"writes species plexippus; a person decides how they assemble. {explanation} Options: Danaus; plexippus.")
    marked_on_both_labels(run, "taxon")


def test_two_genera_on_two_labels_are_ambiguous_with_both(tmp_path, monkeypatch, first_pass_path):
    """Label 1 writes the genus "Danaus", label 2 the genus "Bombus", and the expert answers label
    1's: on the units path the taxon is ambiguous with both, marked on both labels; the old path
    keeps main's result, label 1's genus settled."""
    rig = two_labels(tmp_path, monkeypatch, TEXT.replace("taxon: Danaus plexippus", GENUS), "Bombus", TAXON)
    with_roles(rig, 0, {"Danaus": ("genus", ["taxon"])})
    with_roles(rig, 1, {"Bombus": ("genus", ["taxon"])})
    settle(rig, Scripted({"taxon": taxon_on("Danaus", value=GENUS_NAME, authority_id=GENUS_KEY, literal="Danaus")}),
        tools=Genus(rig.blobs))
    run = rig.specimen.run
    taxon = run.fields["taxon"]
    if first_pass_path == "old":
        assert (taxon.state, taxon.literal) == (ValueState.SUPPORTED, "Danaus")
        return
    assert (taxon.state, taxon.literal) == (ValueState.AMBIGUOUS, None)
    assert taxon.reason == ("The field's parts are on different labels: label 1 writes genus Danaus; label 2 "
        "writes genus Bombus; a person decides how they assemble. Settled. Options: Danaus; Bombus.")
    marked_on_both_labels(run, "taxon")


DATE_ANSWERS = {
    # Label 1's day and month answered as the whole date.
    "label-1-part": ("6 Sept", "1A"),
    # Label 2's year answered as the whole date.
    "label-2-part": ("1946", "2A"),
}


@pytest.mark.parametrize("answer", DATE_ANSWERS, ids=DATE_ANSWERS)
def test_a_day_and_month_on_label_1_and_the_year_on_label_2_are_ambiguous_with_each_label_s_parts(
        tmp_path, monkeypatch, first_pass_path, answer):
    """ "6 Sept" on label 1 and "1946" on label 2, the expert answering one label's part as the date:
    on the units path the date is ambiguous, its reason naming each label's parts, marked on both
    labels; the old path keeps main's result: label 1's "6 Sept" settles, label 2's "1946" is
    refused as a text the other label does not write."""
    literal, reading = DATE_ANSWERS[answer]
    rig = two_labels(tmp_path, monkeypatch, TEXT.replace("date_visited_from: 2020-06-01", DATE), "1946", DATES)
    with_roles(rig, 0, {"6": ("day", ["date_visited_from"]), "Sept": ("month", ["date_visited_from"])})
    with_roles(rig, 1, {"1946": ("year", ["date_visited_from", "date_visited_to"])})
    settle(rig, Scripted({"date_visited_from": answering(resolved(literal, reading=reading))}))
    run = rig.specimen.run
    date = run.fields["date_visited_from"]
    if first_pass_path == "old":
        if answer == "label-1-part":
            assert (date.state, date.literal) == (ValueState.SUPPORTED, "6 Sept")
        else:
            assert (date.state, date.reason) == (ValueState.AMBIGUOUS,
                "The labels differ, and no approved source confirms them as one value. Settled.")
        assert findings(run, "date_visited_from") == []
        return
    assert (date.state, date.literal) == (ValueState.AMBIGUOUS, None)
    assert date.reason == ("The field's parts are on different labels: label 1 writes day 6, month Sept; label 2 "
        "writes year 1946; a person decides how they assemble. Settled. Options: 6; Sept; 1946.")
    marked_on_both_labels(run, "date_visited_from")


# ---- as today -------------------------------------------------------------------------------------

def outcome_of(tmp_path, monkeypatch, first, second, given, script, roles, tools):
    """The run's fields, findings and reasons once `script` settles it, with the units' roles and
    fields `roles` gives each label ({label: {text: (role, fields)}})."""
    rig = two_labels(tmp_path, monkeypatch, first, second, given)
    for label, named in roles.items():
        with_roles(rig, label, named)
    settle(rig, Scripted({"taxon": script}), tools=tools(rig.blobs))
    run = rig.specimen.run
    shown = json.dumps({"fields": {key: value.model_dump(mode="json", exclude={"evidence_ids", "evidence_relations"})
        for key, value in run.fields.items()}, "findings": sorted(f.reason_code for f in run.findings),
        "reasons": run.reasons, "disposition": run.disposition}, sort_keys=True)
    # The run's own ids, by their order in it: two runs built alike compare equal.
    for number, region in enumerate(run.regions):
        shown = shown.replace(region.id, f"region-{number}")
    for number, observation in enumerate(run.observations):
        shown = shown.replace(observation.id, f"observation-{number}")
    return json.loads(shown)


WHOLE = "taxon: Danaus plexippus"
AS_TODAY = {
    # "Aus bus" on one label, the other label writing no part.
    "whole-name-on-one-label": ("Mossy forest", {0: {"Danaus": ("genus", ["taxon"]),
        "plexippus": ("species", ["taxon"])}}),
    # The other label writes a part label 1 writes too: label 1 writes every part.
    "other-label-repeats-a-part": ("Danaus", {0: {"Danaus": ("genus", ["taxon"]),
        "plexippus": ("species", ["taxon"])}, 1: {"Danaus": ("genus", ["taxon"])}}),
    # The same whole name on both labels, in another letter case on label 2.
    "same-name-on-both-labels": ("DANAUS PLEXIPPUS", {0: {"Danaus": ("genus", ["taxon"]),
        "plexippus": ("species", ["taxon"])}, 1: {"DANAUS": ("genus", ["taxon"]),
        "PLEXIPPUS": ("species", ["taxon"])}}),
    # The role gate: label 2's unit names the taxon but carries no role.
    "no-role": ("plexippus", {0: {"Danaus": ("genus", ["taxon"])}, 1: {"plexippus": ("", ["taxon"])}}),
    # Label 2's unit carries the role but its fields do not name the taxon.
    "fields-do-not-name-it": ("plexippus", {0: {"Danaus": ("genus", ["taxon"])},
        1: {"plexippus": ("species", [])}}),
    # A role of another field's parts.
    "a-date-role": ("plexippus", {0: {"Danaus": ("genus", ["taxon"])}, 1: {"plexippus": ("year", ["taxon"])}}),
    # Owner decision B (WP 2.T): parts that name no genus on any label.
    "no-genus": ("sp. 30", {0: {"plexippus": ("species", ["taxon"])}, 1: {"30": ("species", ["taxon"])}}),
}


@pytest.mark.parametrize("case", AS_TODAY, ids=AS_TODAY)
def test_parts_one_label_writes_whole_settle_as_today_on_both_paths(tmp_path, monkeypatch, case):
    """Label 1 writes "Danaus plexippus" and the expert answers it: the run is the same, with the
    units' roles or without them, on both paths."""
    second, roles = AS_TODAY[case]
    given = [("taxon", name, LABEL["taxon"], WHOLE) for name in ("1A", "1B")]
    given_roles = outcome_of(tmp_path / "roles", monkeypatch, TEXT, second, given, taxon_on(LABEL["taxon"]), roles,
        test_step.FakeSources)
    without = outcome_of(tmp_path / "none", monkeypatch, TEXT, second, given, taxon_on(LABEL["taxon"]), {},
        test_step.FakeSources)
    assert given_roles == without
    assert given_roles["fields"]["taxon"]["state"] == "supported"


def test_a_genus_alone_on_one_label_settles_as_today_on_both_paths(tmp_path, monkeypatch):
    """Label 1 writes the genus "Danaus" and label 2 no part of the name: the same run with the role
    as without it."""
    roles = {0: {"Danaus": ("genus", ["taxon"])}}
    script = taxon_on("Danaus", value=GENUS_NAME, authority_id=GENUS_KEY, literal="Danaus")
    first = TEXT.replace("taxon: Danaus plexippus", GENUS)
    assert outcome_of(tmp_path / "roles", monkeypatch, first, "Mossy forest", TAXON, script, roles, Genus) == (
        outcome_of(tmp_path / "none", monkeypatch, first, "Mossy forest", TAXON, script, {}, Genus))


def test_an_old_path_run_whose_record_carries_units_with_roles_keeps_main_s_result(tmp_path, monkeypatch,
        first_pass_path):
    """The units-path gate: an old-path run is decided on its readings alone (step.run_readings
    attaches no units to them), so even units with the roles of the named case in its record leave
    the genus settled as main settles it."""
    if first_pass_path == "units":
        pytest.skip("the old path's gate")
    rig = two_labels(tmp_path, monkeypatch, TEXT.replace("taxon: Danaus plexippus", GENUS), "plexippus", TAXON)
    run = rig.specimen.run
    entries = []
    for number, region in enumerate(run.regions):
        units = alignment_units(region.id, [o for o in run.observations if o.region_id == region.id])
        named = {"Danaus": "genus", "plexippus": "species"}
        entries.append(units.model_copy(update={"units": [unit.model_copy(update={
            "role": next((named[span.text] for span in unit.readers.values() if span.text in named), ""),
            "fields": ["taxon"] if any(span.text in named for span in unit.readers.values()) else []})
            for unit in units.units]}))
    store_reading_units(run, entries)
    settle(rig, Scripted({"taxon": taxon_on("Danaus", value=GENUS_NAME, authority_id=GENUS_KEY, literal="Danaus")}),
        tools=Genus(rig.blobs))
    taxon = run.fields["taxon"]
    assert (taxon.state, taxon.literal) == (ValueState.SUPPORTED, "Danaus")
    assert not [f for f in run.findings if f.reason_code.endswith(":parts_on_labels")]


# ---- WP 2.3c's re-ask -------------------------------------------------------------------------------

def test_a_field_marked_by_this_rule_is_not_put_back_to_its_expert(tmp_path, monkeypatch, first_pass_path):
    """The re-ask puts back only a value its expert settled that a check of the stage marks
    (reask.to_ask): a field left ambiguous because its parts are on different labels is never one."""
    rig = two_labels(tmp_path, monkeypatch, TEXT.replace("taxon: Danaus plexippus", GENUS), "plexippus", TAXON)
    genus_and_species(rig)
    run = rig.specimen.run
    prepared, outcomes, calls = research(rig, Scripted({"taxon": GENUS_ANSWERS["one-part"][0]()}),
        tools=Genus(rig.blobs))
    decisions = {}
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    if first_pass_path == "units":
        assert decisions["taxon"]["rule"] == field_step.PARTS
        assert run.fields["taxon"].state == ValueState.AMBIGUOUS
    assert "taxon" not in reask.to_ask(run, run, decisions, outcomes)


# ---- field_parts, the condition itself ------------------------------------------------------------

def label_units(region, *units):
    """A label's units, each (text, role, fields) and both readers writing its text."""
    found, at = [], 0
    for number, (text, role, fields) in enumerate(units, 1):
        span = UnitText(text=text, start=at, end=at + len(text))
        found.append(ReadingUnit(id=f"{region}:{number}", label=region, lines=(1, 1),
            readers={"a": span, "b": span}, image="uncertain", role=role, fields=list(fields)))
        at += len(text) + 1
    return ReadingUnits(label=region, units=found)


def readings(*labels):
    """Two readings of each label, named 1A, 1B, 2A, ... with its units (readers a and b)."""
    found = []
    for number, units in enumerate(labels, 1):
        text = " ".join(unit.readers["a"].text for unit in units.units)
        found += [Reading(f"{number}{letter}", units.label, letter.lower(), "raw_reading", text, units=units)
            for letter in "AB"]
    return tuple(found)


T = ("taxon",)
D = ("date_visited_from",)


@pytest.mark.parametrize(("labels", "parted"), [
    # The named cases.
    ([[("Aus", "genus", T)], [("bus", "species", T)]], True),
    ([[("Aus", "genus", T), ("bus", "species", T)], [("Mossy", "", ())]], False),
    ([[("Aus", "genus", T)], [("Cus", "genus", T)]], True),
    # One label writes every part another writes, letter case and spacing aside.
    ([[("Aus", "genus", T), ("bus", "species", T)], [("AUS", "genus", T)]], False),
    ([[("Aus", "genus", T)], [("aus", "genus", T), ("bus", "species", T)]], False),
    # The same text in another role is another part.
    ([[("Aus", "genus", T)], [("Aus", "species", T)]], True),
    # Three labels: two write the genus, the third the species.
    ([[("Aus", "genus", T)], [("Aus", "genus", T)], [("bus", "species", T)]], True),
    # Three labels: the second and third each write a part the other does not; the first writes less.
    ([[("Aus", "genus", T)], [("Aus", "genus", T), ("bus", "species", T)], [("Aus", "genus", T), ("L.", "author", T)]],
        True),
    # The role gate, the fields gate, a role of another field, and no genus on any label.
    ([[("Aus", "genus", T)], [("bus", "", T)]], False),
    ([[("Aus", "genus", T)], [("bus", "species", ())]], False),
    ([[("Aus", "genus", T)], [("bus", "day", T)]], False),
    ([[("bus", "species", T)], [("cus", "species", T)]], False),
    ([[("Aus", "author", T)], [("bus", "species", T)]], False),
])
def test_field_parts_holds_back_a_taxon_only_when_no_label_writes_every_part(labels, parted):
    given = readings(*(label_units(f"r{n}", *units) for n, units in enumerate(labels, 1)))
    found = field_step.field_parts("taxon", given)
    assert bool(found) == parted
    if parted:
        assert list(found) == [f"r{n}" for n, units in enumerate(labels, 1) if any(role for _, role, _ in units)]


def test_field_parts_takes_a_date_s_parts_where_its_fields_name_the_date():
    """A date's roles are shared by the three date fields: a part is this date's only where the unit's
    fields name it."""
    day_month = label_units("r1", ("6", "day", D), ("Sept", "month", D))
    year = label_units("r2", ("1946", "year", D))
    found = field_step.field_parts("date_visited_from", readings(day_month, year))
    assert found == {"r1": [("day", ("6",)), ("month", ("Sept",))], "r2": [("year", ("1946",))]}
    assert field_step.field_parts("date_identified", readings(day_month, year)) == {}
    assert field_step.field_parts("taxon", readings(day_month, year)) == {}
    determined = label_units("r2", ("1950", "year", ("date_identified",)))
    assert field_step.field_parts("date_visited_from", readings(day_month, determined)) == {}


def test_field_parts_names_each_reader_s_text_once():
    first = label_units("r1", ("Aus", "genus", T))
    differing = ReadingUnits(label="r2", units=[ReadingUnit(id="r2:1", label="r2", lines=(1, 1), readers={
        "a": UnitText(text="bus", start=0, end=3), "b": UnitText(text="hus", start=0, end=3)}, image="uncertain",
        role="species", fields=["taxon"])])
    given = (*readings(first), Reading("2A", "r2", "a", "raw_reading", "bus", units=differing),
        Reading("2B", "r2", "b", "raw_reading", "hus", units=differing))
    assert field_step.field_parts("taxon", given) == {"r1": [("genus", ("Aus",))], "r2": [("species", ("bus", "hus"))]}


def test_the_units_document_carries_each_unit_s_role():
    """The experts' request carries a unit's role where it has one (experts.units_document), which the
    rule's instruction refers to."""
    from specimen_digitization.field_research.experts import units_document

    document = units_document(readings(label_units("r1", ("Aus", "genus", T)), label_units("r2", ("x", "", ()))))
    assert document["1"] == [{"lines": [1, 1], "text": "Aus", "image": "uncertain", "role": "genus",
        "fields": ["taxon"]}]
    assert "role" not in document["2"][0]


def test_the_taxon_and_date_experts_carry_the_rule_s_instruction_on_the_units_path_only():
    from specimen_digitization import ontology
    from specimen_digitization.field_research.prompts import instructions

    [rule] = [rule for rule in ontology.ontology().rules if rule.id == "parts_on_different_labels"]
    for key in ("taxon", "date_visited_from", "date_visited_to", "date_identified"):
        assert rule.instruction in instructions(key, units=True)
        assert rule.instruction not in instructions(key)
    for key in ("country", "province_state", "precise_location", "collectors"):
        assert rule.instruction not in instructions(key, units=True)


def test_build_tasks_is_unchanged_by_roles(tmp_path, monkeypatch):
    """The roles change what the step applies, not what each expert is asked about (build_tasks)."""
    rig = two_labels(tmp_path, monkeypatch, TEXT.replace("taxon: Danaus plexippus", GENUS), "plexippus", TAXON)
    before = [(task.key, task.candidates) for task in build_tasks(rig.specimen.run)[1]]
    genus_and_species(rig)
    assert [(task.key, task.candidates) for task in build_tasks(rig.specimen.run)[1]] == before
