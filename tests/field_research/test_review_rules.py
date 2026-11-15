"""WP 2.R of docs/execution/units/PLAN.md: the two review rules narrowed to their requirements. The owner
typed on 2026-11-14: "4 shouldn't be flagged. It should be caught and handled. Goal isn't to throw everything
at the user it is to help by being in in autonomy as much as possible." and "Harness needs to work and do its
magic".

(i) unresolved_transcription, on the units path, stands only for a label whose differing spans decide a field
(G19, docs/execution/golive/PLAN.md:77: "a field still left with conflicting readings goes to needs human
review"; step.differing_spans_decide_a_field), and always for a label the first pass gave up on or with one
reader.

(ii) mandatory_unresolved is not raised for a field settled absent as not on the label (owner decision A,
docs/execution/golive/FIELD_RESEARCH.md, "Fields the label does not state") only where its expert answered
label_lacks_value and the not-on-the-label check row agrees (step.mark_not_on_label, step.not_on_label). WP 2.R
checked each field the list leaves out against its sources and adds none (contracts.NOT_ON_LABEL's comment), so
the rule is today's; its named cases are test_step's
test_the_listed_fields_a_label_does_not_state_clear_as_not_on_the_label (a field the label does not write,
cleared, no reason) and test_a_field_whose_line_the_label_writes_never_clears_as_not_on_the_label (a field whose
reading writes its text, answered label_lacks_value, keeps the reason); the fields left out are pinned below.

Every test runs on both first-pass paths (conftest.py). On the old path, live in production until WP 1.8, each
test asserts origin/main's result."""

from __future__ import annotations

import hashlib
import io

import pytest
import test_step as rig_module
from PIL import Image
from test_step import (
    LACKS,
    SMITH_OR_SMYTH,
    SMYTH,
    TEXT,
    Scripted,
    answering,
    build_rig,
    every_field,
    label_with,
    mounted,
    resolved,
    settle,
)

from specimen_digitization.application.domain import Disposition, Evidence, Observation, Region, ValueState
from specimen_digitization.application.organiser import CandidateLocation, format_locator
from specimen_digitization.application.region_pixels import region_png
from specimen_digitization.field_research import contracts, ontology_checks
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.agreement import _differs

# 105526329's second label (wp15c r2/pair): its readers differ only on a preparation note no field draws.
NOTE_A, NOTE_B = "head 4 legs", "head + legs"


def second_label_read(monkeypatch, *texts):
    """build_rig's specimen with a second label its readers read as `texts`, in route order; "" for a reader
    that read nothing, which extraction_readings leaves out (test_first_pass_advice's helper, which also takes
    make_specimen's `first_pass`, so that a first pass given up on runs on it too)."""
    original = rig_module.make_specimen

    def make(blobs, first=TEXT, other=None, *, first_pass=True):
        specimen = original(blobs, first, other, first_pass=first_pass)
        run = specimen.run
        output = io.BytesIO()
        Image.new("RGB", (100, 100), "white").save(output, format="JPEG", quality=95)
        region = Region(asset_id=specimen.asset.id, x=0, y=50, width=100, height=50, order=1,
            method="synthetic_fixture_region", version="1")
        crop_png = region_png(Image.open(io.BytesIO(output.getvalue())), region)
        region.crop_ref = blobs.put(crop_png)
        run.regions.append(region)
        crop = hashlib.sha256(crop_png).hexdigest()
        for route, text in zip(run.profile.routes, texts, strict=True):
            raw = ("SYNTHETIC FIXTURE " + route + "\n" + text).encode()
            run.observations.append(Observation(region_id=region.id, route_id=route, model_id="synthetic-" + route,
                provider="synthetic", prompt_version="prompt:" + route, input_sha256=crop,
                input_asset_id=specimen.asset.id, input_crop_ref=region.crop_ref, literal_text=text,
                raw_ref=blobs.put(raw), raw_sha256=hashlib.sha256(raw).hexdigest()))
            run.completed_steps.append(f"transcribe:{region.id}:{route}")
        if len(set(texts)) > 1 and first_pass and rig_module.PATH == "old":
            # Its first pass picked no reading, as make_specimen's.
            run.completed_steps.append(f"first_pass:{region.id}")
        return specimen
    monkeypatch.setattr(rig_module, "make_specimen", make)


def second_region(run):
    return run.regions[1].id


def note_units(run):
    """The second label's units; None on the old path, which has none."""
    return next((item for item in run.reading_units if item.label == second_region(run)), None)


def transcription(run, region):
    return f"unresolved_transcription:{region}"


def noted(tmp_path, monkeypatch, *texts, refused=False):
    """test_step's label, which both readers read alike and every field's expert settles, and a second label
    its readers read as `texts`."""
    second_label_read(monkeypatch, *texts)
    rig = build_rig(tmp_path, candidates=every_field(), refused=refused)
    settle(rig, Scripted())
    return rig, rig.specimen.run


# ---- (i) unresolved_transcription --------------------------------------------------------------

def test_a_label_whose_readers_differ_only_on_a_span_no_field_draws_sends_no_record_to_a_person(tmp_path,
        monkeypatch, first_pass_path):
    """Named case 1: the second label's readers differ on "4" against "+", which no field draws and no unit
    advises for a field. On the units path the label decides no field: no unresolved_transcription, and the
    record, whose every field settles, clears. On the old path the label still goes to a person, as on main."""
    rig, run = noted(tmp_path, monkeypatch, NOTE_A, NOTE_B)
    region = second_region(run)
    if first_pass_path == "units":
        assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
        assert [[span.text for span in unit.readers.values()] for unit in note_units(run).units
            if _differs(unit)] == [["4", "+"]]
        assert not field_step.differing_spans_decide_a_field(run, region)
    else:
        assert (run.disposition, run.reasons) == (Disposition.REVIEW, [transcription(run, region)])


def test_a_label_whose_readers_differ_only_in_letter_case_or_spacing_decides_no_field(tmp_path, monkeypatch,
        first_pass_path):
    """Named case 1, as on 19 of the 20 wp15c labels the narrowing drops: the readers write "Sp. 22" and
    "sp. 22", which agreement._differs counts as the same text (letter case and spacing aside), so no unit
    differs. On the units path the label decides no field; on the old path it goes to a person, as on main."""
    rig, run = noted(tmp_path, monkeypatch, "Sp. 22\nhead 4 legs", "sp. 22\nhead  4 legs")
    region = second_region(run)
    if first_pass_path == "units":
        assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
        assert not [unit for unit in note_units(run).units if _differs(unit)]
    else:
        assert (run.disposition, run.reasons) == (Disposition.REVIEW, [transcription(run, region)])


def test_a_label_whose_readers_differ_on_a_fields_literal_keeps_the_reason(tmp_path, first_pass_path):
    """Named case 2: 1A writes "J. Smith", 1B "J. Smyth"; the collectors' expert settles 1A's text, which the
    readers do not agree on. The label keeps unresolved_transcription on both paths, and the collectors their
    own reason (test_step's test_on_a_label_with_no_decided_transcript_the_way_out_is_a_transcription_decision)."""
    rig = build_rig(tmp_path, TEXT, SMYTH, candidates=every_field(*SMITH_OR_SMYTH))
    run = rig.specimen.run
    settle(rig, Scripted({"collectors": answering(resolved("J. Smith", reading="1A"))}))
    region = run.regions[0].id
    assert (run.disposition, run.reasons) == (Disposition.REVIEW,
        [transcription(run, region), "mandatory_unresolved:collectors"])


def test_a_label_whose_first_pass_was_given_up_keeps_the_reason_whatever_its_spans_decide(tmp_path,
        monkeypatch, first_pass_path):
    """Named case 3: case 1's labels, with the first pass refused on every attempt and given up: the second
    label keeps unresolved_transcription on both paths, though its differing span decides no field (HARNESS.md,
    a given-up label goes to review however its fields settle)."""
    rig, run = noted(tmp_path, monkeypatch, NOTE_A, NOTE_B, refused=True)
    region = second_region(run)
    assert region in field_step.given_up_regions(run)
    assert transcription(run, region) in run.reasons and run.disposition == Disposition.REVIEW


def test_a_label_one_reader_read_keeps_the_reason(tmp_path, monkeypatch, first_pass_path):
    """Named case 4: the second label's other reader read nothing (wp15c's pair arm, where one reader returned
    nothing on seven labels): one reading has no second reading to differ from, so the label keeps
    unresolved_transcription on both paths."""
    rig, run = noted(tmp_path, monkeypatch, NOTE_A, "")
    region = second_region(run)
    assert [r.text for r in field_step.run_readings(run) if r.region_id == region] == [NOTE_A]
    assert transcription(run, region) in run.reasons and run.disposition == Disposition.REVIEW


# Each condition of differing_spans_decide_a_field, on named case 1's run (where none holds) with one thing
# changed: the reason stands again on the units path. On the old path the narrowing never applies.

def a_row_on_the_note(run, key, start, end):
    """A label row of field `key` on 2A's note, its quote [start, end)."""
    region = second_region(run)
    reading = next(r for r in field_step.run_readings(run) if r.region_id == region and r.name == "2A")
    row = Evidence(kind="literal", region_id=region, observation_ids=[reading.observation_id],
        source=field_step.SOURCE, excerpt=reading.text[start:end],
        locator=format_locator(CandidateLocation("2A", reading.observation_id, start, end, start, end)))
    run.evidence.append(row)
    run.fields[key].evidence_ids.append(row.id)
    return row


def unplaced_row(run):
    row = a_row_on_the_note(run, "habitat", 0, 4)
    row.locator = "region:" + second_region(run)


def stale_quote(run):
    row = a_row_on_the_note(run, "habitat", 0, 4)
    row.excerpt = "hand"


def reader_unnamed(run):
    """2A's row names an observation the label's units do not name."""
    entry = note_units(run)
    if entry is not None:
        first = next(iter(entry.units[0].readers))
        for unit in entry.units:
            unit.readers["elsewhere"] = unit.readers.pop(first)
    a_row_on_the_note(run, "habitat", 0, 4)


def units_not_the_readings_text(run):
    """2A's text at the differing unit, as the units hold it, is not 2A's reading there."""
    entry = note_units(run)
    if entry is not None:
        reading = next(r for r in field_step.run_readings(run) if r.region_id == second_region(run) and r.name == "2A")
        unit = next(unit for unit in entry.units if _differs(unit))
        unit.readers[reading.observation_id] = unit.readers[reading.observation_id].model_copy(update={"text": "x"})
    a_row_on_the_note(run, "habitat", 0, 4)


def advised(run):
    entry = note_units(run)
    if entry is not None:
        next(unit for unit in entry.units if _differs(unit)).fields.append("habitat")
    run.fields["habitat"] = run.fields["habitat"].model_copy(update={"state": ValueState.NOT_PRESENT,
        "literal": None, "parsed": None, "normalized": None})


def advised_supported(run):
    """The differing unit advised for a field settled with a value elsewhere: no field depends."""
    entry = note_units(run)
    if entry is not None:
        next(unit for unit in entry.units if _differs(unit)).fields.append("habitat")


def no_units(run):
    region = second_region(run)
    run.reading_units = [item for item in run.reading_units if item.label != region]


def one_route(run):
    for item in run.observations:
        if item.region_id == second_region(run):
            item.route_id = "one-route"


def one_model(run):
    for item in run.observations:
        if item.region_id == second_region(run):
            item.model_id = "one-model"


CHANGES = {
    # A field's evidence row quotes the differing unit ("4" is 2A's characters 5 to 6).
    "quote-on-the-differing-unit": (lambda run: a_row_on_the_note(run, "habitat", 0, 11), True),
    # A row whose quote ends before the differing unit: it decides nothing there.
    "quote-beside-the-differing-unit": (lambda run: a_row_on_the_note(run, "habitat", 0, 4), False),
    "row-of-the-label-not-placed": (unplaced_row, True),
    "quote-not-the-readings-text": (stale_quote, True),
    "row-on-a-reading-the-units-do-not-name": (reader_unnamed, True),
    "units-not-the-readings-text": (units_not_the_readings_text, True),
    # A field's literal is the differing unit's text in a reading of the label.
    "literal-on-the-differing-unit": (lambda run: setattr(run.fields["habitat"], "literal", "head 4"), True),
    "verbatim-on-the-differing-unit": (lambda run: run.fields["habitat"].verbatim_by_observation.update(
        {run.observations[0].id: "4 legs"}), True),
    # identified_by_irn never routes a record (G16, G43), as the label's drawn fields leave it out.
    "irn-on-the-differing-unit": (lambda run: setattr(run.fields["identified_by_irn"], "literal", "head 4"), False),
    "absent-field-advised-for-the-differing-unit": (advised, True),
    "settled-field-advised-for-the-differing-unit": (advised_supported, False),
    "no-units": (no_units, True),
    "one-route": (one_route, True),
    "one-model": (one_model, True),
}


@pytest.mark.parametrize("change", list(CHANGES))
def test_each_condition_that_ties_a_field_to_a_differing_span_keeps_the_reason(tmp_path, monkeypatch,
        first_pass_path, change):
    rig, run = noted(tmp_path, monkeypatch, NOTE_A, NOTE_B)
    region = second_region(run)
    alter, stands = CHANGES[change]
    alter(run)
    field_step.refinalize(run)
    if first_pass_path == "units":
        assert (transcription(run, region) in run.reasons) is stands
        assert field_step.differing_spans_decide_a_field(run, region) is stands
    else:
        # Main's rule: the label draws no field, so the reason stands whatever the change.
        assert transcription(run, region) in run.reasons


def test_a_held_fields_candidate_on_a_differing_span_keeps_the_reason(tmp_path, monkeypatch, first_pass_path):
    """The second label's readers write the habitat line differently ("grassland" against "grass1and"), and the
    habitat is left held, with no text of its own: its organiser candidate, quoted on the first label, stands on
    the second label's differing unit, so that label keeps unresolved_transcription (a field still left with
    conflicting readings)."""
    rig, run = noted(tmp_path, monkeypatch, "Synthetic grassland", "Synthetic grass1and")
    region = second_region(run)
    run.fields["habitat"] = run.fields["habitat"].model_copy(update={"state": ValueState.UNRESOLVED,
        "literal": None, "parsed": None, "normalized": None, "verbatim_by_observation": {}})
    field_step.refinalize(run)
    assert transcription(run, region) in run.reasons
    if first_pass_path == "units":
        assert field_step.differing_spans_decide_a_field(run, region)


def test_a_field_held_on_a_label_whose_reason_is_dropped_keeps_its_own(tmp_path, monkeypatch, first_pass_path):
    """The second label's readers differ only on the note, and its collection code, which only that label
    writes and both readers write alike, is answered as several possibilities: the label decides no field by
    its differing span, but the field keeps its own reason, so the record still goes to a person for it."""
    second_label_read(monkeypatch, "collection_code: LEWIS\n" + NOTE_A, "collection_code: LEWIS\n" + NOTE_B)
    rig = build_rig(tmp_path, label_with(collection_code=None), candidates=every_field(
        *(("collection_code", name, "LEWIS", "collection_code: LEWIS") for name in ("2A", "2B"))))
    run = rig.specimen.run
    unsure = answering(LACKS.model_copy(update={"outcome": "sources_cannot_resolve", "literal": "LEWIS",
        "reading_names": ["2A", "2B"], "explanation": "Whether LEWIS is the code is unsure."}))
    settle(rig, Scripted({"collection_code": unsure}))
    region = second_region(run)
    assert run.fields["collection_code"].state != ValueState.SUPPORTED
    assert "mandatory_unresolved:collection_code" in run.reasons and run.disposition == Disposition.REVIEW
    assert (transcription(run, region) in run.reasons) is (first_pass_path == "old")


# ---- (ii) mandatory_unresolved on a field settled absent ------------------------------------------

# The fields contracts.NOT_ON_LABEL leaves out, each kept out by WP 2.R from its sources (contracts.py's
# comment): their absence keeps mandatory_unresolved on both paths. identified_by_irn never routes (G16, G43);
# the taxon follows owner decision B as WP 2.T left it.
LEFT_OUT = ("fmnh_ins_number", "country", "province_state", "date_visited_from", "date_visited_to", "collectors",
    "verbatim_dts")


def test_the_not_on_label_list_is_unchanged_by_wp_2r():
    [key] = contracts.NOT_ON_LABEL
    listed = contracts.NOT_ON_LABEL[key]
    assert not listed & {*LEFT_OUT, "taxon", "identified_by_irn"}
    assert contracts.not_on_label_fields(*key) == listed


@pytest.mark.parametrize("key", LEFT_OUT)
def test_a_field_left_off_the_list_keeps_its_reason_when_the_label_does_not_write_it(tmp_path, key,
        first_pass_path):
    """Its line is off the label, the organiser gives no candidate for it and its expert answers
    label_lacks_value: the field is not present and keeps mandatory_unresolved, with no not-on-the-label row,
    on both paths."""
    # A country or a province is derived from a settled place below it (derive.fill): the label then writes
    # no place at all.
    places = ("country", "province_state", "county", "city") if key in ("country", "province_state") else (key,)
    text = TEXT.replace("\nleg. J. Smith", "") if key == "collectors" else label_with(**dict.fromkeys(places))
    rig = build_rig(tmp_path, text, candidates=[] if key == "collectors" else every_field())
    run = rig.specimen.run
    settle(rig, Scripted(dict.fromkeys(places, answering(LACKS))))
    value = run.fields[key]
    if key == "date_visited_to":
        # The step's derivation from the collecting date (G44) fills it: no reason of its own.
        assert value.layer == "derived" and f"mandatory_unresolved:{key}" not in run.reasons
        return
    assert value.state == ValueState.NOT_PRESENT
    rows = {item.id: item for item in run.evidence}
    assert not [i for i in value.evidence_ids if rows[i].locator == field_step.NOT_ON_LABEL_CHECK]
    assert f"mandatory_unresolved:{key}" in run.reasons and run.disposition == Disposition.REVIEW


def test_a_field_that_waits_for_its_source_is_never_settled_absent(tmp_path, first_pass_path):
    """Date Visited To follows Date Visited From (G44), which the readers write differently and which stays
    held. On the units path the To date waits (WP 2.3b, ontology_checks.waiting_fields): unknown, no
    not-on-the-label row and no reason of its own, its source's reason routing the record. On the old path it
    is not present with its own reason, as on main."""
    first, second = (label_with(date_visited_from=date) for date in ("2020-06-01", "2020-06-07"))
    rig = build_rig(tmp_path, first, second, candidates=every_field(
        ("date_visited_from", "1A", "2020-06-01", "date_visited_from: 2020-06-01"),
        ("date_visited_from", "1B", "2020-06-07", "date_visited_from: 2020-06-07")))
    run = rig.specimen.run
    several = answering(LACKS.model_copy(update={"outcome": "several_possibilities",
        "options": ["2020-06-01", "2020-06-07"], "reading_names": ["1A", "1B"],
        "explanation": "The readers write two dates."}))
    settle(rig, Scripted({"date_visited_from": several, "date_visited_to": answering(LACKS)}))
    to = run.fields["date_visited_to"]
    rows = {item.id: item for item in run.evidence}
    assert not [i for i in to.evidence_ids if rows[i].locator == field_step.NOT_ON_LABEL_CHECK]
    assert "mandatory_unresolved:date_visited_from" in run.reasons
    if first_pass_path == "units":
        assert "date_visited_to" in ontology_checks.waiting_fields(run)
        assert to.state == ValueState.UNKNOWN and "mandatory_unresolved:date_visited_to" not in run.reasons
    else:
        assert to.state == ValueState.NOT_PRESENT and "mandatory_unresolved:date_visited_to" in run.reasons
