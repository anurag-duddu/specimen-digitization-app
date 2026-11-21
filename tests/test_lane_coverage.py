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
    assert settings.coverage == CoverageRule.model_validate(PUBLISHED_RULE.model_dump())
    published, base = settings.coverage.model_dump(), RULE.model_dump()
    assert {k for k in published if published[k] != base.get(k)} == {
        "min_region_short_side_fraction"
    }
    assert settings.coverage.min_region_short_side_fraction == 0.03


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
