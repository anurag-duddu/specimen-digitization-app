"""The lane drives the real app factory; synthetic adapters stand in for SAM 3 and the readers."""

import io
import os
import time

from PIL import Image
import pytest

from specimen_digitization.application.api import SYNTHETIC_TEXT
from specimen_digitization.application.workflow import OperationalBlock, SyntheticAdapters

import lab_lane

BLOCK = "sam3_serving_contract_not_configured_use_reviewed_regions"


class NoLocalSam(SyntheticAdapters):
    """What ProductionAdapters does with SPECIMEN_SAM3_ENDPOINT unset."""

    def segment(self, specimen):
        raise OperationalBlock(BLOCK)


def jpeg(width=890, height=295):
    stream = io.BytesIO()
    Image.new("RGB", (width, height), "beige").save(stream, format="JPEG")
    return stream.getvalue()


def drive(tmp_path, adapters, subject, segmentation):
    lane = lab_lane.AppLane(
        tmp_path / "state",
        adapters_factory=lambda blobs: adapters(blobs, SYNTHETIC_TEXT),
        persistence="sqlite",
        segmentation=segmentation,
        subject=subject,
    )
    with lane:
        specimen_id = lane.ingest(subject + ".jpeg", jpeg(), "image/jpeg")
        actions = lane.process(specimen_id, time.monotonic() + 120)
        return actions, lane.collect(specimen_id)


def test_the_lane_ingests_processes_and_collects_through_the_app(tmp_path):
    actions, evidence = drive(tmp_path, SyntheticAdapters, "subject_105526321", "sam3")
    run = evidence["snapshot"]["run"]
    assert actions == [] and run["stage"] == "finalized"
    assert evidence["snapshot"]["asset"]["filename"] == "subject_105526321.jpeg"
    assert evidence["snapshot"]["asset"]["sensitive"] is False  # as the ten are imported
    assert evidence["workspace"]["stage"] == "finalized"
    assert {f"responses/{o['id']}.json" for o in run["observations"]} <= set(
        evidence["artifacts"]
    )
    assert evidence["rows"] == {}  # SQLite keeps only the snapshot


def test_a_blocked_segmentation_gets_the_reviewer_boxes_for_the_slide(tmp_path):
    actions, evidence = drive(tmp_path, NoLocalSam, "subject_105526324", "reviewed-region")
    [action] = actions
    assert action["action"] == "reviewed_region" and BLOCK in action["reason"]
    snapshot = evidence["snapshot"]
    assert snapshot["previous_runs"][-1]["blocker"] == BLOCK
    boxes = [(r["x"], r["width"], r["height"]) for r in snapshot["run"]["regions"]]
    assert boxes == [(0, 303, 295), (552, 338, 295)]  # 0-0.34 and 0.62-1.0 of 890 px
    assert len(snapshot["run"]["observations"]) == 4  # two readers per label


def test_only_the_ten_the_owner_classified_are_created_not_sensitive(tmp_path):
    # G31: the owner classified the ten pilot slides not sensitive; every other slide stays Sensitive.
    _, pilot = drive(tmp_path / "pilot", SyntheticAdapters, "subject_105526330", "sam3")
    _, other = drive(tmp_path / "other", SyntheticAdapters, "subject_105526331", "sam3")
    assert pilot["snapshot"]["asset"]["sensitive"] is False
    assert "sensitive" not in other["snapshot"]["asset"]  # the default, Sensitive, is not serialized


def test_without_the_substitute_the_lane_leaves_a_block_alone(tmp_path):
    actions, evidence = drive(tmp_path, NoLocalSam, "subject_105526321", "sam3")
    assert actions == []
    run = evidence["snapshot"]["run"]
    assert run["stage"] == "processing_blocked" and run["blocker"] == BLOCK


@pytest.mark.skipif(
    os.getenv("SPECIMEN_TEST_SQL_EMULATOR") != "true",
    reason="needs PostgreSQL and the SQL Connect emulator binaries",
)
def test_the_emulator_lane_dumps_every_table(tmp_path):
    lane = lab_lane.AppLane(
        tmp_path / "state",
        adapters_factory=lambda blobs: SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        persistence="sql-emulator",
        segmentation="sam3",
        subject="subject_105526321",
    )
    with lane:
        specimen_id = lane.ingest("subject_105526321.jpeg", jpeg(), "image/jpeg")
        lane.process(specimen_id, time.monotonic() + 120)
        evidence = lane.collect(specimen_id)
    assert any(evidence["rows"].values())
