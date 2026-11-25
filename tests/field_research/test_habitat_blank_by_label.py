"""Lane B of the waiting-fields program (the coordinator's brief of 2026-11-24, fix 3 of the audit of the 19
cleared production records): a blank Habitat needs every label that could carry a habitat read whole, not the
whole slide.

Owner decision A's mark (step.mark_not_on_label) needed every label of the slide read whole
(step._whole_label_read), so one unreadable word anywhere kept a blank Habitat flagged; on record d10333ff it
was a word of the determiner's name ("J. [unreadable] det. 2021"). For the Habitat alone
(step.READ_WHOLE_BY_KIND), an unreadable part that stands inside a catalogue-number label's or a determination
label's own content no longer stops the mark (step._unreadable_inside_its_kind, step._content_line); a label of any
other kind, an unreadable part on another line or on a line that writes more than that content (a host, a
lower-case word), a label that also names a collector, a label another field is drawn on, and every other field
keep the whole-slide rule.

The rig is test_thin_region_coverage's: test_step's slide and label (which writes no habitat), two more labels
read by both readers, the segment step's real coverage check, the real field-research step with a scripted
expert.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys

import pytest
from PIL import Image

import test_step as rig_module
from test_step import LABEL, TEXT, Scripted, answering, build_rig, mounted
from specimen_digitization.application.domain import Observation, Region, Transcript, ValueState
from specimen_digitization.application.label_coverage import check_run
from specimen_digitization.application.region_pixels import region_png
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FieldAnswer

UPPER, LOWER = (0, 0, 100, 50), (0, 50, 100, 50)
WRITTEN = TEXT.replace(f"habitat: {LABEL['habitat']}\n", "").replace(
    f"collection_method: {LABEL['collection_method']}\n", "")
NOT_WRITTEN = "No reading writes a habitat."
NO_METHOD = "No reading writes a collecting method."
LACKS = answering(FieldAnswer(outcome="label_lacks_value", explanation=NOT_WRITTEN))
LACKS_METHOD = answering(FieldAnswer(outcome="label_lacks_value", explanation=NO_METHOD))
CATALOGUE = "FMNH-INS\n4313642\nFIELD MUSEUM\nWet"
DETERMINATION = "Panorpa\nsp. IVa\nJ. Kustermop det. 2021"
DETERMINER_UNREAD = "Panorpa\nsp. IVa\nJ. [unreadable] det. 2021"


def with_labels(monkeypatch, labels):
    """The rig's specimen with one more region per entry of `labels` ({box: (first reader's text, second
    reader's text, the second reader's listed unreadable spans)}), checked by the segment step's check."""
    original = rig_module.make_specimen

    def make(blobs, text=TEXT, other=None, *, profile=None):
        specimen = original(blobs, text, other, profile=profile)
        run = specimen.run
        image = Image.open(io.BytesIO(blobs.get(specimen.asset.blob_ref)))
        for order, (box, (first, second, spans)) in enumerate(labels.items(), start=1):
            region = Region(asset_id=specimen.asset.id, x=box[0], y=box[1], width=box[2], height=box[3],
                order=order, method="synthetic_fixture_region", version="1")
            crop_png = region_png(image, region)
            region.crop_ref = blobs.put(crop_png)
            run.regions.append(region)
            crop = hashlib.sha256(crop_png).hexdigest()
            for index, route in enumerate(run.profile.routes):
                written = first if index == 0 else second
                raw = ("SYNTHETIC FIXTURE " + route + "\n" + written).encode()
                run.observations.append(Observation(region_id=region.id, route_id=route,
                    model_id="synthetic-" + route, provider="synthetic", prompt_version="prompt:" + route,
                    input_sha256=crop, input_asset_id=specimen.asset.id, input_crop_ref=region.crop_ref,
                    literal_text=written, unreadable_spans=list(spans) if index else [], raw_ref=blobs.put(raw),
                    raw_sha256=hashlib.sha256(raw).hexdigest()))
                run.completed_steps.append(f"transcribe:{region.id}:{route}")
        segmentation = {"cross_check": {"concept": "text", "detections": []}}
        raw = json.dumps(segmentation, sort_keys=True).encode()
        segmentation.update(input_sha256=specimen.asset.sha256, blob_ref=blobs.put(raw),
            sha256=hashlib.sha256(raw).hexdigest())
        run.segmentation = segmentation
        run.classification_selection = {"collection_id": "insects", "actor_id": "reviewer-1",
            "reason": "Intake selection"}
        run.coverage_confirmed = False
        check_run(specimen)
        return specimen

    monkeypatch.setattr(sys.modules[rig_module.__name__], "make_specimen", make)


def researched(tmp_path, monkeypatch, labels, script=None):
    with_labels(monkeypatch, labels)
    rig = build_rig(tmp_path, WRITTEN)
    mounted(rig, Scripted(script or {"habitat": LACKS}))
    return rig.workflow.step(rig.principal, rig.specimen.id).run


def marked(run, key="habitat"):
    rows = {row.id: row for row in run.evidence}
    value = run.fields[key]
    return (value.state == ValueState.NOT_PRESENT and value.reason.startswith("Not on the label")
        and any(rows[i].locator == field_step.NOT_ON_LABEL_CHECK for i in value.evidence_ids if i in rows))


def by_kind(run):
    readings = field_step.run_readings(run)
    return (field_step._whole_label_read(run, readings), field_step._whole_label_read(run, readings, by_kind=True))


def same(text, spans=()):
    return (text, text, tuple(spans))


def test_an_unreadable_word_in_a_determiners_name_does_not_stop_a_blank_habitat(tmp_path, monkeypatch):
    """d10333ff's determination label: one reader could not read a word of the determiner's name."""
    run = researched(tmp_path, monkeypatch, {UPPER: same(CATALOGUE),
        LOWER: (DETERMINATION, DETERMINER_UNREAD, ("[unreadable]",))})
    assert run.coverage_confirmed is True and len(run.regions) == 3
    assert by_kind(run) == (False, True)
    assert marked(run)


def test_an_unreadable_part_of_the_catalogue_heading_does_not_stop_a_blank_habitat(tmp_path, monkeypatch):
    run = researched(tmp_path, monkeypatch, {UPPER: same("FMNH-INS [unreadable]\n4313642\nFIELD MUSEUM"),
        LOWER: same("Panorpa speciosa\ndet. J.W. Griffiths")})
    assert by_kind(run) == (False, True)
    assert marked(run)


def test_every_other_field_still_needs_the_whole_slide_read(tmp_path, monkeypatch):
    """The collecting method answered label_lacks_value too: it keeps its expert's reason and no mark, while the
    Habitat is marked."""
    run = researched(tmp_path, monkeypatch, {UPPER: same(CATALOGUE),
        LOWER: (DETERMINATION, DETERMINER_UNREAD, ("[unreadable]",))},
        script={"habitat": LACKS, "collection_method": LACKS_METHOD})
    assert marked(run) and not marked(run, "collection_method")
    method = run.fields["collection_method"]
    assert method.state == ValueState.NOT_PRESENT and method.reason == NO_METHOD


@pytest.mark.parametrize("labels", [
    {UPPER: same(CATALOGUE), LOWER: same("Panorpa [unreadable]\ndet. R. E. Lewis")},
    {UPPER: same(CATALOGUE), LOWER: same("leg. & det. R. E. [unreadable]")},
    {UPPER: same(CATALOGUE), LOWER: same("Quercus [unreadable]\nR. E. Lewis")},
    {UPPER: same("FMNH-INS\n4313642\nFIELD MUSEUM\n[unreadable]"), LOWER: same("det. R. E. Lewis")},
    {UPPER: same("FMNH-INS 4313642\n[unreadable] meadow"), LOWER: same("det. R. E. Lewis")},
    {UPPER: same(CATALOGUE), LOWER: same("det. R. E. Lewis", ["a faint word after Lewis"])},
    {UPPER: same(CATALOGUE), LOWER: same("[unreadable]")},
    {UPPER: same(CATALOGUE), LOWER: same("Panorpa speciosa\ndet. R. E. Lewis on Quercus [unreadable]")},
    {UPPER: same(CATALOGUE), LOWER: same("Panorpa speciosa\nHost: [unreadable] det. R. E. Lewis")},
    {UPPER: same(CATALOGUE), LOWER: same("Panorpa speciosa\ndet. R. E. Lewis, oak [unreadable]")},
    {UPPER: same("FMNH-INS [unreadable] meadow\n4313642"), LOWER: same("det. R. E. Lewis")},
    {UPPER: same(CATALOGUE), LOWER: ("Host: Quercus\rdet. R. E. Lewis", "Host: Quercus\rdet. R. E. Lewis",
        ("Quercus",))},
    {UPPER: same(CATALOGUE), LOWER: ("det. R. E. Lewis\rHost: oak", "det. R. E. Lewis\rHost: oak",
        ("Lewis\rHost",))},
    {UPPER: same("FMNH123 [unreadable]\nFIELD MUSEUM"), LOWER: same("det. R. E. Lewis")},
    {UPPER: same(CATALOGUE), LOWER: same("Panorpa speciosa\nSubstrate: [unreadable]; det. R. E. Lewis")},
    {UPPER: same(CATALOGUE), LOWER: same("Panorpa speciosa\n[unreadable] det. R. E. Lewis")},
    {UPPER: same(CATALOGUE), LOWER: ("Panorpa speciosa\nLeaf det. R. E. Lewis", "Panorpa speciosa\nLeaf det. R. E. Lewis",
        ("Leaf",))},
], ids=["another-line-of-a-determination-label", "a-collector-on-it-too", "a-label-of-no-such-kind",
    "a-line-of-the-catalogue-label-without-its-content", "beside-a-heading-on-another-line",
    "a-span-the-text-does-not-hold", "a-label-wholly-unreadable", "a-host-on-the-determiners-line",
    "a-host-heading-on-the-determiners-line", "a-lower-case-word-on-the-determiners-line",
    "another-word-on-the-catalogue-heading-line", "a-span-on-a-line-a-carriage-return-ends",
    "a-span-across-a-carriage-return", "a-heading-run-into-digits", "after-a-capitalised-heading",
    "at-the-line-start", "a-span-after-no-initial"])
def test_an_unreadable_part_anywhere_else_still_stops_the_mark(tmp_path, monkeypatch, labels):
    run = researched(tmp_path, monkeypatch, labels)
    assert by_kind(run) == (False, False)
    assert not marked(run) and run.fields["habitat"].reason == NOT_WRITTEN


def test_a_transcript_marked_unreadable_or_a_field_drawn_on_the_label_still_stops_it(tmp_path, monkeypatch):
    run = researched(tmp_path, monkeypatch, {UPPER: same(CATALOGUE),
        LOWER: (DETERMINATION, DETERMINER_UNREAD, ("[unreadable]",))})
    assert by_kind(run) == (False, True)
    determination = run.regions[2].id
    readings = field_step.run_readings(run)
    assert field_step._unreadable_inside_its_kind(run, readings, determination) is True
    # A collecting field drawn on the label: it holds more than a determination.
    run.fields["collectors"].source_region_id = determination
    assert field_step._unreadable_inside_its_kind(run, readings, determination) is False
    assert by_kind(run) == (False, False)
    run.fields["collectors"].source_region_id = None
    # Or one of its readings settling a collecting field, or as that field's source reading.
    reading = next(o.id for o in run.observations if o.region_id == determination)
    run.fields["collectors"].settled_observation_ids = [reading]
    assert field_step._unreadable_inside_its_kind(run, readings, determination) is False
    run.fields["collectors"].settled_observation_ids = []
    run.fields["collectors"].source_observation_id = reading
    assert field_step._unreadable_inside_its_kind(run, readings, determination) is False
    run.fields["collectors"].source_observation_id = None
    # The determination's own fields may be drawn on it.
    run.fields["date_identified"].source_region_id = determination
    assert field_step._unreadable_inside_its_kind(run, readings, determination) is True
    # A transcript of the label marked unreadable.
    run.transcripts.append(Transcript(region_id=determination, value_state=ValueState.UNREADABLE, text=None,
        observation_ids=[o.id for o in run.observations if o.region_id == determination], alternatives=[],
        resolved=False))
    assert field_step._unreadable_inside_its_kind(run, readings, determination) is False
    assert by_kind(run) == (False, False)
