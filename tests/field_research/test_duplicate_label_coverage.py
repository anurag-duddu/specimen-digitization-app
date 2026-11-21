"""The same label boxed twice, through the real field-research step (lane L3).

The coordinator's ruling of 2026-11-21 on review round 1 of #461 (provisional, not an owner
sign-off): the published coverage rule's nested_duplicate value (0.95 of the smaller box inside
the larger, IoU 0.6 or more) counts a label the label finder boxes twice, its outer card and its
inner frame (IoU about 0.78, the frame wholly inside, on truth slides 105527007 and 105526361),
once. merge_iou stays 0.9. Count only: both boxes stay regions of the run and both are read.

The rig is lane L1's (tests/field_research/test_thin_region_coverage.py: test_step's 100 x 100
slide and label, two readers, the real workflow step, a scripted field expert, and the segment
step's real label_coverage.check_run under the published coverage rule), with two more labels,
and on the second slide the upper one boxed a second time, by its inner frame.
"""

from __future__ import annotations

import sys

import test_step as rig_module
from test_step import Scripted, build_rig, mounted
from test_thin_region_coverage import LACKS, LOWER, NO_HABITAT, UPPER, with_regions
from specimen_digitization.application.label_coverage import intersection_over_union

# The upper label's inner frame, wholly inside the upper label's box at IoU 0.792 (3960 / 5000);
# also wholly inside the rig's whole-slide label, at IoU 0.396, and apart from the lower label.
# The upper and lower labels are wholly inside the whole-slide label at IoU 0.5: not duplicates.
FRAME = (5, 3, 90, 44)
ONCE = {UPPER: "LEWIS COLLECTION", LOWER: "det. R. E. Lewis"}
TWICE = ONCE | {FRAME: "LEWIS COLLECTION"}


def researched(tmp_path, monkeypatch, texts):
    module = sys.modules[rig_module.__name__]
    plain = module.make_specimen
    with_regions(monkeypatch, texts)
    rig = build_rig(tmp_path, NO_HABITAT)
    mounted(rig, Scripted({"habitat": LACKS}))
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    # Back to the rig's own specimen (only this patch: the suite's fixtures patch more).
    monkeypatch.setattr(module, "make_specimen", plain)
    return run


def shown(run):
    return {key: (str(getattr(value.state, "value", value.state)), value.normalized or value.parsed
        or value.literal, value.reason) for key, value in run.fields.items()}


def test_a_label_boxed_twice_clears_as_the_same_slide_boxed_once(tmp_path, monkeypatch):
    assert round(intersection_over_union(UPPER, FRAME), 3) == 0.792
    once = researched(tmp_path / "once", monkeypatch, ONCE)
    twice = researched(tmp_path / "twice", monkeypatch, TWICE)
    # Under #460's published rule (no nested value) the twice-boxed slide counts 4 and is held.
    for run in (once, twice):
        assert run.coverage_check["region_count"] == 3
        assert run.coverage_confirmed is True
        assert "label_coverage_unconfirmed" not in run.reasons
        assert getattr(run.disposition, "value", run.disposition) == "cleared"
    # Count only: the frame is a region of the run, and both readers read it.
    assert len(once.regions) == 3 and len(twice.regions) == 4
    frame = twice.regions[3]
    assert twice.coverage_check["merged_regions"] == [[twice.regions[1].id, frame.id]]
    assert once.coverage_check["merged_regions"] == []
    assert {o.route_id for o in twice.observations if o.region_id == frame.id} == set(
        twice.profile.routes)
    # The second reading of the same label changes no field: every field shows the same
    # state, value and reason as on the slide boxed once.
    assert shown(twice) == shown(once)
    assert twice.reasons == once.reasons
