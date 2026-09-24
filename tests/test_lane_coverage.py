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


def test_the_pilot_pins_the_approved_starting_values():
    settings = published_registry().resolve("insects").profile.segmentation_settings
    assert settings.coverage == RULE


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
