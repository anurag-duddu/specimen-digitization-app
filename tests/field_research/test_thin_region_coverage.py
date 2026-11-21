"""A region too thin to hold a label, through the real field-research step (lane L1).

The coordinator's ruling of 2026-11-21 on review round 1 of PR #460: the thin-region rule
changes only the region count, and a run whose count is then in range has its coverage
confirmed, with every consequence of a confirmed coverage. One is the not-on-the-label mark
(step.mark_not_on_label), which needs every label read whole (step._whole_label_read, which
reads run.coverage_confirmed). Pinned here with its mirror: the same slide whose thin region
both readers read as "[unreadable]", as on each of the seven strips measured on the 100 truth
slides, leaves the habitat as before.

The rig is test_step's (a 100 x 100 slide, the rig's own label, two readers, the real workflow
step, a scripted field expert), with three more regions read by both readers, and the segment
step's real label_coverage.check_run under the published coverage rule.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys

from PIL import Image

import test_step as rig_module
from test_step import LABEL, TEXT, Scripted, answering, build_rig, mounted
from specimen_digitization.application.domain import Observation, Region
from specimen_digitization.application.label_coverage import check_run
from specimen_digitization.application.region_pixels import region_png
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FieldAnswer

# Two more labels on the slide, and a strip 2 px tall along the top edge (2 % of the
# 100 px shorter side, under the published 3 %).
UPPER, LOWER = (0, 0, 100, 50), (0, 50, 100, 50)
STRIP = (0, 0, 100, 2)
NO_HABITAT = TEXT.replace(f"habitat: {LABEL['habitat']}\n", "")
NOT_WRITTEN = "No reading writes a habitat."
LACKS = answering(FieldAnswer(outcome="label_lacks_value", explanation=NOT_WRITTEN))


def with_regions(monkeypatch, texts):
    """The rig's specimen with the regions of `texts` (box: what both readers read), checked
    by the segment step's check under the rule the run pinned (the published one)."""
    original = rig_module.make_specimen

    def make(blobs, text=TEXT, other=None, *, profile=None):
        specimen = original(blobs, text, other, profile=profile)
        run = specimen.run
        image = Image.open(io.BytesIO(blobs.get(specimen.asset.blob_ref)))
        for order, (box, written) in enumerate(texts.items(), start=1):
            region = Region(asset_id=specimen.asset.id, x=box[0], y=box[1], width=box[2],
                height=box[3], order=order, method="synthetic_fixture_region", version="1")
            crop_png = region_png(image, region)
            region.crop_ref = blobs.put(crop_png)
            run.regions.append(region)
            crop = hashlib.sha256(crop_png).hexdigest()
            for route in run.profile.routes:
                raw = ("SYNTHETIC FIXTURE " + route + "\n" + written).encode()
                run.observations.append(Observation(region_id=region.id, route_id=route,
                    model_id="synthetic-" + route, provider="synthetic",
                    prompt_version="prompt:" + route, input_sha256=crop,
                    input_asset_id=specimen.asset.id, input_crop_ref=region.crop_ref,
                    literal_text=written, raw_ref=blobs.put(raw),
                    raw_sha256=hashlib.sha256(raw).hexdigest()))
                run.completed_steps.append(f"transcribe:{region.id}:{route}")
        # The segmentation evidence, as the segment step stores it (no text detection).
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


def researched(tmp_path, monkeypatch, strip_text):
    with_regions(monkeypatch, {UPPER: "LEWIS COLLECTION", LOWER: "det. R. E. Lewis",
        STRIP: strip_text})
    rig = build_rig(tmp_path, NO_HABITAT)
    mounted(rig, Scripted({"habitat": LACKS}))
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    rows = {row.id: row for row in run.evidence}
    habitat = run.fields["habitat"]
    return run, habitat, [rows[i].locator for i in habitat.evidence_ids if i in rows]


def test_a_thin_region_read_as_text_confirms_coverage_and_opens_the_not_on_label_mark(
    tmp_path, monkeypatch
):
    run, habitat, locators = researched(tmp_path, monkeypatch, "No. 12")
    # Without the rule (b35e823e): count 4, coverage unconfirmed, the habitat keeps the
    # expert's own reason and no not-on-the-label row.
    assert run.coverage_check["region_count"] == 3
    assert run.coverage_confirmed is True
    assert len(run.regions) == 4
    assert "label_coverage_unconfirmed" not in run.reasons
    assert getattr(run.disposition, "value", run.disposition) == "cleared"
    assert field_step._whole_label_read(run, field_step.run_readings(run)) is True
    assert habitat.reason.startswith("Not on the label")
    assert "check:not_on_label" in locators


def test_a_thin_region_read_as_unreadable_confirms_coverage_and_leaves_the_habitat(
    tmp_path, monkeypatch
):
    run, habitat, locators = researched(tmp_path, monkeypatch, "[unreadable]")
    assert run.coverage_check["region_count"] == 3
    assert run.coverage_confirmed is True
    assert "label_coverage_unconfirmed" not in run.reasons
    # The strip's "[unreadable]" keeps the label from being read whole, so the mark stays shut.
    assert field_step._whole_label_read(run, field_step.run_readings(run)) is False
    assert habitat.reason == NOT_WRITTEN
    assert "check:not_on_label" not in locators
