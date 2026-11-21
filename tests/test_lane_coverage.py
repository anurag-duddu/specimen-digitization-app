"""The automatic label-coverage check (docs/execution/golive/LANE.md T3b, G15)."""

import pytest

from specimen_digitization.application.collection_profiles import (
    CoverageRule,
    SegmentationSettings,
    published_registry,
)
from specimen_digitization.application.domain import (
    Asset,
    Profile,
    Region,
    Run,
    Scope,
    Specimen,
)
from specimen_digitization.application.label_coverage import (
    check_coverage,
    covered_fraction,
    intersection_over_union,
    merged_count,
)

RULE = CoverageRule(
    min_label_regions=1,
    max_label_regions=3,
    merge_iou=0.9,
    cross_check_threshold=0.5,
    min_inside_fraction=0.5,
)
# S7's label boxes for the pilot, on a 1000 x 400 slide: one label on the left,
# or a left and a right label (the locality is on the right on 324-328).
LEFT = (0, 20, 370, 360)
RIGHT = (620, 20, 380, 360)


def specimen(regions, cross, *, rule=RULE):
    settings = SegmentationSettings(prompt="label", coverage=rule)
    run = Run(
        profile=Profile(synthetic=False),
        profile_rules={"segmentation_settings": settings.model_dump(mode="json")},
        regions=[
            Region(
                asset_id="asset",
                x=x,
                y=y,
                width=width,
                height=height,
                order=order,
                method="sam3",
                version="revision",
            )
            for order, (x, y, width, height) in enumerate(regions)
        ],
        segmentation={
            "blob_ref": "e" * 64 + ":3",
            "sha256": "e" * 64,
            "cross_check": {
                "concept": "text",
                "detections": [
                    {"box": list(box), "score": score} for box, score in cross
                ],
            },
        },
    )
    return Specimen(
        scope=Scope(organization_id="org", collection_id="insects"),
        run=run,
        asset=Asset(
            id="asset",
            sensitive=False,
            sha256="0" * 64,
            blob_ref="0" * 64,
            media_type="image/png",
            size_bytes=1,
            width=1000,
            height=400,
            filename="slide.png",
            uploader="lane",
        ),
    )


def test_intersection_over_union():
    assert intersection_over_union((0, 0, 10, 10), (0, 0, 10, 10)) == 1
    assert intersection_over_union((0, 0, 10, 10), (20, 0, 10, 10)) == 0
    assert intersection_over_union((0, 0, 10, 10), (5, 0, 10, 10)) == pytest.approx(1 / 3)


def test_near_duplicate_regions_count_as_one_label():
    duplicate = (1, 20, 370, 360)
    assert merged_count([LEFT, duplicate, RIGHT], 0.9) == 2
    assert merged_count([LEFT, RIGHT], 0.9) == 2
    assert merged_count([], 0.9) == 0


def test_covered_fraction_is_exact_over_a_union():
    assert covered_fraction((0, 0, 10, 10), [(0, 0, 5, 10)]) == 0.5
    assert covered_fraction((0, 0, 10, 10), [(0, 0, 5, 10), (5, 0, 5, 5)]) == 0.75
    assert covered_fraction((0, 0, 10, 10), [(0, 0, 5, 10), (0, 0, 5, 10)]) == 0.5
    assert covered_fraction((0, 0, 10, 10), []) == 0


def test_labels_that_hold_every_text_detection_confirm_coverage():
    item = specimen([LEFT, RIGHT], [((10, 40, 200, 40), 0.9), ((650, 60, 300, 90), 0.7)])
    check_coverage(RULE, item)
    assert item.run.coverage_confirmed is True
    evidence = item.run.coverage_check
    assert evidence["version"] == "coverage-check-v1"
    assert evidence["outcome"] == "confirmed"
    assert evidence["region_count"] == 2
    assert (evidence["min_label_regions"], evidence["max_label_regions"]) == (1, 3)
    assert evidence["reason_codes"] == []
    assert evidence["cross_check"]["counted"] == 2
    assert evidence["cross_check"]["uncovered_boxes"] == []
    assert (evidence["evidence_ref"], evidence["evidence_sha256"]) == (
        "e" * 64 + ":3",
        "e" * 64,
    )
    assert evidence["checked_at"]


def test_text_outside_the_labels_is_a_possible_missed_label():
    missed = (450, 150, 100, 40)
    item = specimen([LEFT], [((10, 40, 200, 40), 0.9), (missed, 0.8)])
    check_coverage(RULE, item)
    assert item.run.coverage_confirmed is False
    assert item.run.coverage_check["outcome"] == "unconfirmed"
    assert item.run.coverage_check["reason_codes"] == [
        "label_coverage_unconfirmed",
        "cross_check_detection_outside_labels",
    ]
    assert item.run.coverage_check["cross_check"]["uncovered_boxes"] == [list(missed)]


def test_weak_cross_check_detections_are_recorded_but_not_counted():
    item = specimen([LEFT], [((450, 150, 100, 40), 0.3)])
    check_coverage(RULE, item)
    assert item.run.coverage_confirmed is True
    assert item.run.coverage_check["cross_check"]["counted"] == 0


@pytest.mark.parametrize(
    ("regions", "reason"),
    [
        ([], "zero_regions"),
        (
            [(0, 0, 100, 100), (200, 0, 100, 100), (400, 0, 100, 100), (600, 0, 100, 100)],
            "label_region_count_out_of_range",
        ),
    ],
)
def test_region_count_outside_the_expectation_fails(regions, reason):
    item = specimen(regions, [])
    check_coverage(RULE, item)
    assert item.run.coverage_confirmed is False
    assert reason in item.run.coverage_check["reason_codes"]
    assert item.run.coverage_check["reason_codes"][0] == "label_coverage_unconfirmed"


# The published rule: RULE plus the provisional thin-region fraction (the
# coordinator's ruling of 2026-11-21; the range and every other value as RULE).
PUBLISHED_RULE = RULE.model_copy(update={"min_region_short_side_fraction": 0.03})


def test_the_pilot_pins_the_approved_starting_values():
    settings = published_registry().resolve("insects").profile.segmentation_settings
    nested = {"min_containment": 0.95, "min_iou": 0.6}
    expected = {**PUBLISHED_RULE.model_dump(), "nested_duplicate": nested}
    assert settings.coverage == CoverageRule.model_validate(expected)
    published, base = settings.coverage.model_dump(), RULE.model_dump()
    assert {k for k in published if published[k] != base.get(k)} == {
        "min_region_short_side_fraction",
        "nested_duplicate",
    }
    assert settings.coverage.min_region_short_side_fraction == 0.03
    assert settings.coverage.nested_duplicate.model_dump() == nested
    assert settings.coverage.merge_iou == RULE.merge_iou


def test_coverage_rules_are_consistent():
    with pytest.raises(ValueError):
        CoverageRule(
            min_label_regions=4,
            max_label_regions=3,
            merge_iou=0.9,
            cross_check_threshold=0.5,
            min_inside_fraction=0.5,
        )


def test_runs_without_a_check_serialize_as_before():
    assert "coverage_check" not in Run().model_dump()
    assert "coverage" not in SegmentationSettings(prompt="label").model_dump()


def test_the_segment_step_records_a_failed_check_and_the_run_goes_on(tmp_path):
    from specimen_digitization.application.domain import Principal
    from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
    from specimen_digitization.application.workflow import SyntheticAdapters, Workflow

    from test_lane_trigger import STAGE_COSTS

    item = specimen([LEFT], [((450, 150, 100, 40), 0.8)])
    regions, segmentation = item.run.regions, item.run.segmentation
    item.run.regions, item.run.segmentation = [], {}
    item.run.completed_steps = ["pin_dependencies", "classify", "quality_check"]
    item.run.stage = "segment"
    item.run.profile.execution = item.run.profile.execution.model_copy(
        update={
            "approved_cost_limit_micros": 250_000,
            "stage_cost_reservations": STAGE_COSTS,
        }
    )

    class Adapters(SyntheticAdapters):
        def segment(self, specimen):
            specimen.run.segmentation = dict(segmentation)
            return [region.model_copy(update={"asset_id": specimen.asset.id}) for region in regions]

    blobs = LocalBlobs(tmp_path / "blobs")
    repository = SQLiteRepository(tmp_path / "state.sqlite3")
    principal = Principal(user_id="worker", scope=item.scope, role="operator")
    repository.create(principal, item, "coverage", "coverage")
    stepped = Workflow(repository, blobs, Adapters(blobs, "text")).step(
        principal, item.id
    )
    assert "segment" in stepped.run.completed_steps, stepped.run.blocker
    assert stepped.run.coverage_confirmed is False
    assert stepped.run.coverage_check["reason_codes"][0] == "label_coverage_unconfirmed"
    assert stepped.run.stage == "transcribe"


# A region too thin to hold a label is not counted as a label (the coordinator's
# ruling of 2026-11-21, lane L1). Count only: the region stays in run.regions.
THIN_RULE = PUBLISHED_RULE


def sized(regions, width, height, *, rule=THIN_RULE, cross=()):
    item = specimen(regions, list(cross), rule=rule)
    item.asset = item.asset.model_copy(update={"width": width, "height": height})
    return item


# Measured on truth slide 105527060 (1763 x 616): three labels and a strip
# 11 px tall along the top edge, read "[unreadable]" by both readers.
SLIDE = (1763, 616)
LABEL_A, LABEL_B, BARCODE = (21, 16, 517, 573), (1216, 32, 542, 570), (1120, 405, 93, 187)
STRIP = (243, 0, 473, 11)


def test_a_strip_beside_three_labels_is_not_counted():
    item = sized([LABEL_A, LABEL_B, BARCODE, STRIP], *SLIDE)
    check_coverage(THIN_RULE, item)
    evidence = item.run.coverage_check
    assert item.run.coverage_confirmed is True
    assert evidence["outcome"] == "confirmed"
    assert evidence["region_count"] == 3
    assert evidence["reason_codes"] == []
    strip = item.run.regions[3]
    assert evidence["not_counted_regions"] == [{"id": strip.id, "box": list(STRIP)}]
    assert evidence["min_region_short_side_fraction"] == 0.03
    # Count only: the strip is still a region of the run.
    assert len(item.run.regions) == 4


def test_a_strip_beside_two_labels_counts_two():
    item = sized([LABEL_A, LABEL_B, STRIP], *SLIDE)
    check_coverage(THIN_RULE, item)
    assert item.run.coverage_confirmed is True
    assert item.run.coverage_check["region_count"] == 2
    assert len(item.run.coverage_check["not_counted_regions"]) == 1


def test_a_strip_as_the_only_region_is_held():
    item = sized([STRIP], *SLIDE)
    check_coverage(THIN_RULE, item)
    assert item.run.coverage_confirmed is False
    assert item.run.coverage_check["region_count"] == 0
    assert item.run.coverage_check["reason_codes"] == [
        "label_coverage_unconfirmed",
        "label_region_count_out_of_range",
    ]


@pytest.mark.parametrize(
    ("short_side", "counted"),
    # 3 % of a 1000 px shorter side is 30 px: a region exactly at the fraction is
    # counted (the rule is "under"), one pixel thinner is not.
    [(30, 1), (29, 0)],
)
def test_a_region_exactly_at_the_fraction_is_counted(short_side, counted):
    item = sized([(0, 0, 400, short_side)], 3000, 1000)
    check_coverage(THIN_RULE, item)
    assert item.run.coverage_check["region_count"] == counted
    assert len(item.run.coverage_check["not_counted_regions"]) == 1 - counted


@pytest.mark.parametrize(
    ("width", "height", "box", "thin"),
    [
        # Landscape: the image's shorter side is its height (600; 3 % is 18 px).
        (2000, 600, (100, 0, 900, 17), True),
        (2000, 600, (100, 0, 900, 18), False),
        # Portrait: the image's shorter side is its width (600 again), and a
        # tall narrow region's shorter side is its width.
        (600, 2000, (0, 100, 17, 900), True),
        (600, 2000, (0, 100, 18, 900), False),
        # A region 17 px tall on a portrait image is measured against the width.
        (600, 2000, (0, 0, 500, 17), True),
    ],
)
def test_portrait_and_landscape_use_the_shorter_sides(width, height, box, thin):
    label = (0, 300, 500, 250) if width > height else (50, 1000, 500, 250)
    item = sized([label, box], width, height)
    check_coverage(THIN_RULE, item)
    assert item.run.coverage_check["region_count"] == (1 if thin else 2)


def test_a_rule_without_the_fraction_counts_every_region():
    item = sized([LABEL_A, LABEL_B, BARCODE, STRIP], *SLIDE, rule=RULE)
    check_coverage(RULE, item)
    evidence = item.run.coverage_check
    assert item.run.coverage_confirmed is False
    assert evidence["region_count"] == 4
    assert "label_region_count_out_of_range" in evidence["reason_codes"]
    # The record keeps today's keys only.
    assert "not_counted_regions" not in evidence
    assert "min_region_short_side_fraction" not in evidence
    assert "min_region_short_side_fraction" not in RULE.model_dump()


def test_a_thin_region_still_counts_for_the_cross_check_and_the_geometry():
    # Text detected inside the strip is covered by it: the cross-check is untouched.
    item = sized(
        [LABEL_A, STRIP], *SLIDE, cross=[((300, 0, 200, 10), 0.9)]
    )
    check_coverage(THIN_RULE, item)
    assert item.run.coverage_check["cross_check"]["uncovered_boxes"] == []
    assert item.run.coverage_confirmed is True


def test_thin_regions_are_left_out_before_the_merge():
    # Two thin boxes that would merge, beside one label: the count is 1.
    item = sized([LABEL_A, STRIP, (243, 0, 473, 10)], *SLIDE)
    check_coverage(THIN_RULE, item)
    assert item.run.coverage_check["region_count"] == 1
    assert len(item.run.coverage_check["not_counted_regions"]) == 2


def test_a_stored_check_without_the_new_keys_still_loads():
    stored = {
        "version": "coverage-check-v1",
        "outcome": "unconfirmed",
        "region_count": 4,
        "min_label_regions": 1,
        "max_label_regions": 3,
        "cross_check": {
            "concept": "text",
            "threshold": 0.5,
            "min_inside_fraction": 0.5,
            "counted": 0,
            "uncovered_boxes": [],
        },
        "reason_codes": ["label_coverage_unconfirmed", "label_region_count_out_of_range"],
        "evidence_ref": "e" * 64,
        "evidence_sha256": "e" * 64,
        "checked_at": "2026-11-20T00:00:00Z",
    }
    run = Run.model_validate({"coverage_check": stored})
    assert run.coverage_check == stored
    assert Run.model_validate(run.model_dump(mode="json")).coverage_check == stored
    # A stored rule without the field loads, and keeps counting every region.
    pinned = SegmentationSettings.model_validate(
        {"prompt": "label", "coverage": RULE.model_dump(mode="json")}
    )
    assert pinned.coverage.min_region_short_side_fraction is None
    assert "min_region_short_side_fraction" not in pinned.model_dump(mode="json")["coverage"]


def test_the_segment_step_uses_the_rule_the_run_pinned():
    from specimen_digitization.application.label_coverage import check_run

    for rule, count in ((RULE, 4), (THIN_RULE, 3)):
        item = sized([LABEL_A, LABEL_B, BARCODE, STRIP], *SLIDE, rule=rule)
        check_run(item)
        assert item.run.coverage_check["region_count"] == count



# The same label boxed twice is counted once (the coordinator's ruling of
# 2026-11-21, lane L3, review round 1 of #461; provisional, not an owner
# sign-off): one box drawn inside the other, as the label finder's outer card
# and inner frame. merge_iou stays 0.9; the rule's nested_duplicate value counts
# such a pair once. Count only: both boxes stay in run.regions.
from pydantic import ValidationError  # noqa: E402

from specimen_digitization.application.collection_profiles import (  # noqa: E402
    NestedDuplicateRule,
)
from specimen_digitization.application.label_coverage import (  # noqa: E402
    merged_groups,
    nested_duplicate,
)

NESTED = NestedDuplicateRule(min_containment=0.95, min_iou=0.6)


def published_rule():
    return published_registry().resolve("insects").profile.segmentation_settings.coverage


def count(boxes, rule=None):
    """The check's own merge, as check_coverage makes it."""
    rule = rule or published_rule()
    return len(
        merged_groups(
            boxes,
            lambda a, b: intersection_over_union(a, b) >= rule.merge_iou
            or (rule.nested_duplicate is not None and nested_duplicate(a, b, rule.nested_duplicate)),
        )
    )


# Measured on truth slide 105527007 (1788 x 639): a barcode label, a left label,
# and the right-hand label boxed twice, as its outer card and its inner frame
# (IoU 0.7847, the frame wholly inside the card); three labels on the truth sheet.
SLIDE_007 = (1788, 639)
BARCODE_007, LEFT_007 = (1103, 417, 95, 165), (6, 51, 544, 538)
CARD_007, FRAME_007 = (1204, 23, 576, 562), (1240, 49, 505, 503)
# Measured on truth slide 105526361 (1757 x 630): a barcode label and one label
# boxed twice (IoU 0.7731, the frame wholly inside the card); two labels.
SLIDE_361 = (1757, 630)
BARCODE_361, CARD_361, FRAME_361 = (1068, 427, 97, 173), (1174, 23, 574, 569), (1211, 50, 504, 501)


def test_the_published_rule_counts_slide_105527007_s_card_and_frame_once():
    item = sized([BARCODE_007, LEFT_007, CARD_007, FRAME_007], *SLIDE_007, rule=published_rule())
    segmentation = dict(item.run.segmentation)
    check_coverage(published_rule(), item)
    evidence = item.run.coverage_check
    assert item.run.coverage_confirmed is True
    assert evidence["region_count"] == 3
    assert evidence["reason_codes"] == []
    card, frame = item.run.regions[2], item.run.regions[3]
    assert evidence["merged_regions"] == [[card.id, frame.id]]
    assert evidence["nested_duplicate"] == {"min_containment": 0.95, "min_iou": 0.6}
    # Count only: both boxes are still regions of the run, nothing is left out as
    # thin, and the segmentation evidence is untouched.
    assert len(item.run.regions) == 4
    assert evidence["not_counted_regions"] == []
    assert item.run.segmentation == segmentation


def test_the_published_rule_counts_slide_105526361_s_card_and_frame_once():
    assert intersection_over_union(CARD_361, FRAME_361) == pytest.approx(0.7731, abs=1e-4)
    item = sized([BARCODE_361, CARD_361, FRAME_361], *SLIDE_361, rule=published_rule())
    check_coverage(published_rule(), item)
    evidence = item.run.coverage_check
    assert evidence["region_count"] == 2
    assert evidence["outcome"] == "confirmed"
    assert evidence["merged_regions"] == [[item.run.regions[1].id, item.run.regions[2].id]]
    assert len(item.run.regions) == 3


def test_four_diagonal_labels_stay_four_and_are_held():
    # Codex's round-1 counterexample on #461: four separate narrow labels tilted
    # 45 degrees, whose axis-aligned boxes overlap consecutively at IoU 0.6807
    # (202500 / 297500) with 0.81 of each box inside the next. Under merge_iou
    # 0.6 alone (#461's first design) they chained into one label and coverage
    # was confirmed; box IoU alone is not a duplicate's identity.
    boxes = [(100, 250, 500, 500), (150, 200, 500, 500), (200, 150, 500, 500), (250, 100, 500, 500)]
    assert intersection_over_union(boxes[0], boxes[1]) == pytest.approx(202500 / 297500)
    lowered = PUBLISHED_RULE.model_copy(update={"merge_iou": 0.6})
    assert count(boxes, lowered) == 1
    item = sized(boxes, 1000, 1000, rule=published_rule())
    check_coverage(published_rule(), item)
    assert item.run.coverage_check["region_count"] == 4
    assert item.run.coverage_confirmed is False
    assert "label_region_count_out_of_range" in item.run.coverage_check["reason_codes"]
    assert item.run.coverage_check["merged_regions"] == []


def test_a_box_wholly_inside_another_at_iou_exactly_0_6_counts_once():
    # Exact arithmetic: 6000 * 1 >= 0.6 * 10000, as written; just under, 5900
    # against 10000, the pair is two.
    outer = (0, 0, 100, 100)
    assert nested_duplicate(outer, (0, 0, 100, 60), NESTED) is True
    assert nested_duplicate(outer, (0, 0, 100, 59), NESTED) is False
    assert count([outer, (0, 0, 100, 60)]) == 1
    assert count([outer, (0, 0, 100, 59)]) == 2


def test_containment_exactly_at_0_95_counts_once_and_just_under_does_not():
    # The inner box is 100 x 80; 76 of its 80 rows inside the outer box is 0.95
    # (IoU 7600 / 10400, about 0.73); 75 rows is 0.9375 (IoU about 0.71).
    outer = (0, 0, 100, 100)
    at, under = (0, 24, 100, 80), (0, 25, 100, 80)
    assert nested_duplicate(outer, at, NESTED) is True
    assert nested_duplicate(outer, under, NESTED) is False
    assert intersection_over_union(outer, under) < 0.9
    assert count([outer, at]) == 1
    assert count([outer, under]) == 2


def test_a_box_around_two_equal_labels_counts_three():
    # Each label is wholly inside the box around both, but at IoU 0.5, under 0.6.
    left, right, around = (0, 20, 400, 360), (400, 20, 400, 360), (0, 20, 800, 360)
    item = sized([left, right, around], 1000, 400, rule=published_rule())
    check_coverage(published_rule(), item)
    assert item.run.coverage_check["region_count"] == 3
    assert item.run.coverage_check["merged_regions"] == []


def test_a_large_and_a_small_label_inside_one_spanning_box_count_two():
    # The spanning box holds the large label at IoU 0.8 (144000 / 180000) and is
    # counted with it; the small label (IoU 10000 / 180000 with the box) stays
    # apart. Two, the number of labels; the spanning box is not a label of its
    # own, so the count is right here, though the box is counted with the large
    # label rather than set aside.
    large, small, spanning = (0, 0, 400, 360), (400, 0, 100, 100), (0, 0, 500, 360)
    item = sized([large, small, spanning], 1000, 400, rule=published_rule())
    check_coverage(published_rule(), item)
    assert item.run.coverage_check["region_count"] == 2
    assert item.run.coverage_check["merged_regions"] == [
        [item.run.regions[0].id, item.run.regions[2].id]
    ]


def test_a_small_sticker_inside_a_large_label_counts_two():
    # Containment 1.0, IoU 3200 / 144000: two labels.
    label, sticker = (0, 0, 400, 360), (50, 50, 80, 40)
    assert count([label, sticker]) == 2


def test_a_duplicate_and_a_thin_strip_together_count_three():
    strip = (243, 0, 473, 11)
    item = sized([BARCODE_007, LEFT_007, CARD_007, FRAME_007, strip], *SLIDE_007, rule=published_rule())
    check_coverage(published_rule(), item)
    evidence = item.run.coverage_check
    assert item.run.coverage_confirmed is True
    assert evidence["region_count"] == 3
    assert [n["box"] for n in evidence["not_counted_regions"]] == [list(strip)]
    assert evidence["merged_regions"] == [[item.run.regions[2].id, item.run.regions[3].id]]
    assert len(item.run.regions) == 5


def test_a_rule_without_the_nested_value_counts_as_before():
    # PUBLISHED_RULE is #460's published rule (0.9 and the 0.03 fraction).
    item = sized([BARCODE_007, LEFT_007, CARD_007, FRAME_007], *SLIDE_007, rule=PUBLISHED_RULE)
    check_coverage(PUBLISHED_RULE, item)
    evidence = item.run.coverage_check
    assert item.run.coverage_confirmed is False
    assert evidence["region_count"] == 4
    assert "nested_duplicate" not in evidence and "merged_regions" not in evidence
    assert "nested_duplicate" not in PUBLISHED_RULE.model_dump(mode="json")


def test_two_different_labels_touching_stay_two():
    # Measured on truth slide 105527165: the largest IoU of two different labels
    # on the 100 slides (0.0496), 0.446 of the barcode label's box inside.
    label, barcode = (1232, 21, 541, 560), (1120, 398, 202, 178)
    assert intersection_over_union(label, barcode) == pytest.approx(0.0496, abs=1e-4)
    assert count([label, barcode]) == 2


def test_chains_join_the_two_tests():
    # Transitive across both tests: a frame inside a card (nested) and the card
    # at IoU 0.9 or more with a third box are one group.
    # The frame is 0.9375 inside the shifted box at IoU about 0.58: no direct link.
    card, frame, shifted = (0, 0, 100, 100), (0, 0, 80, 80), (5, 0, 100, 100)
    assert nested_duplicate(card, frame, NESTED) and intersection_over_union(card, shifted) >= 0.9
    assert not nested_duplicate(frame, shifted, NESTED)
    assert intersection_over_union(frame, shifted) < 0.9
    assert count([frame, card, shifted]) == 1


def test_a_stored_check_without_the_nested_keys_still_loads():
    stored = {
        "version": "coverage-check-v1",
        "outcome": "confirmed",
        "region_count": 3,
        "min_label_regions": 1,
        "max_label_regions": 3,
        "cross_check": {"concept": "text", "threshold": 0.5, "min_inside_fraction": 0.5,
            "counted": 0, "uncovered_boxes": []},
        "reason_codes": [],
        "min_region_short_side_fraction": 0.03,
        "not_counted_regions": [],
        "evidence_ref": "e" * 64,
        "evidence_sha256": "e" * 64,
        "checked_at": "2026-11-21T00:00:00Z",
    }
    run = Run.model_validate({"coverage_check": stored})
    assert Run.model_validate(run.model_dump(mode="json")).coverage_check == stored
    # A stored rule without the value loads and serialises without it.
    pinned = CoverageRule.model_validate(PUBLISHED_RULE.model_dump(mode="json"))
    assert pinned.nested_duplicate is None
    assert "nested_duplicate" not in pinned.model_dump(mode="json")


@pytest.mark.parametrize(
    "value",
    [
        {"min_containment": 0.95},
        {"min_iou": 0.6},
        {"min_containment": 0, "min_iou": 0.6},
        {"min_containment": 0.95, "min_iou": 1.5},
        {"min_containment": 0.95, "min_iou": 0.6, "extra": 1},
    ],
)
def test_the_nested_values_are_validated_together(value):
    with pytest.raises(ValidationError):
        CoverageRule.model_validate({**PUBLISHED_RULE.model_dump(), "nested_duplicate": value})


def test_a_stated_residual_two_parallel_diagonal_labels_with_nested_boxes_count_once():
    # A residual risk, pinned so that it is stated, not fixed: two separate narrow
    # labels at 45 degrees, side by side (the shorter 0.8 of the longer's length,
    # its centre 40 px across from the longer's), have axis-aligned boxes one
    # wholly inside the other at IoU 0.64 (160000 / 250000), and count as one
    # label. No such pair is among the 269 regions of the 100 truth slides
    # (different labels there: at most 0.491 of the smaller box inside the other).
    longer, shorter = (100, 100, 500, 500), (178, 122, 400, 400)
    assert intersection_over_union(longer, shorter) == 0.64
    assert nested_duplicate(longer, shorter, NESTED) is True
    assert count([longer, shorter]) == 1
    # Chained, any number join: a third, shorter label whose box nests in the
    # second's (IoU 0.766) joins both, though its box and the longer's are only
    # at IoU 0.49.
    third = (200, 150, 350, 350)
    assert nested_duplicate(shorter, third, NESTED) and not nested_duplicate(longer, third, NESTED)
    assert count([longer, shorter, third]) == 1
