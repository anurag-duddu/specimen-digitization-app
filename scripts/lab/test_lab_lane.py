"""The lane drives the real app factory; synthetic adapters stand in for SAM 3 and the readers."""

import io
import os
import signal
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


def test_receipt_blobs_are_collected_for_the_d4_scan(tmp_path):
    # Run receipts keep only blob_ref, sha256, state and call_id; the request itself is in the blob.
    from specimen_digitization.application.domain import Run
    from specimen_digitization.application.storage import LocalBlobs

    blobs = LocalBlobs(tmp_path / "blobs")
    body = b'{"url": "https://api.gbif.org/v1/occurrence/search"}'
    receipt = {"blob_ref": blobs.put(body), "sha256": "0" * 64, "state": "completed", "call_id": "authority:0/x"}
    run = Run(authority_receipts={"authority:0:x": receipt, "other": {"state": "reserved"}})
    assert lab_lane.receipt_blobs(run, blobs) == {"receipts/authority_0_x.json": body}


def test_a_production_run_refuses_a_slide_outside_the_ten(tmp_path):
    # #84 round 1 (blocking): the lane processed a Sensitive slide. With the production adapters its image
    # would reach the model providers, which PRD.md 67 and PLAN.md 182 rule out; refuse before any upload.
    from types import SimpleNamespace

    options = SimpleNamespace(persistence="sqlite", segmentation="sam3", subject="subject_105526331")
    with pytest.raises(lab_lane.LabError, match="not one of the ten"):
        lab_lane.production_lane(tmp_path / "state", options, {})
    assert not (tmp_path / "state").exists()
    ten = SimpleNamespace(persistence="sqlite", segmentation="sam3", subject="subject_105526321")
    assert isinstance(lab_lane.production_lane(tmp_path / "state", ten, {}), lab_lane.AppLane)


def test_a_failed_start_stops_the_emulator(tmp_path, monkeypatch):
    # #84 round 1: __exit__ never runs when __enter__ raises after the emulator started.
    stopped = []

    class FakeEmulator:
        def __init__(self, root):
            self.host = "127.0.0.1:1"

        def start(self):
            return self

        def stop(self):
            stopped.append(True)

    def broken_repository(**kwargs):  # built after the emulator starts; the adapters are built before it
        raise RuntimeError("the repository could not be built")

    monkeypatch.setattr(lab_lane, "Emulator", FakeEmulator)
    monkeypatch.setattr(lab_lane, "SqlConnectRepository", broken_repository)
    lane = lab_lane.AppLane(tmp_path / "state", adapters_factory=lambda blobs: object(),
                            persistence="sql-emulator", segmentation="sam3", subject="subject_105526321")
    with pytest.raises(RuntimeError, match="the repository could not be built"):
        lane.__enter__()
    assert stopped == [True]


def test_the_lane_itself_refuses_a_slide_outside_the_ten_with_adapters_that_are_not_synthetic(tmp_path):
    # #84 round 2: the guard sits where the adapters are built (learning 21), not only in production_lane.
    lane = lab_lane.AppLane(tmp_path / "state", adapters_factory=lambda blobs: object(), persistence="sqlite",
                            segmentation="sam3", subject="subject_105526331")
    with pytest.raises(lab_lane.LabError, match="not one of the ten"):
        lane.__enter__()


def test_a_ctrl_c_while_the_emulator_starts_stops_it(tmp_path, monkeypatch):
    # #84 round 2: the emulator runs in its own session, so a Ctrl-C during start never reaches it.
    killed = []

    class FakeProcess:
        pid, stdout = 999_999, iter(())

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    def interrupt(timeout=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(lab_lane.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(lab_lane.os, "killpg", lambda pid, sig: killed.append(pid))
    emulator = lab_lane.Emulator(tmp_path / "emulator")
    monkeypatch.setattr(emulator.ready, "wait", interrupt)
    with pytest.raises(KeyboardInterrupt):
        emulator.start()
    assert killed == [999_999]


class InterruptingAdapters(SyntheticAdapters):
    """Sends this process a Ctrl-C while the app's /complete drain runs segment."""

    def segment(self, specimen):
        os.kill(os.getpid(), signal.SIGINT)
        return super().segment(specimen)


def test_a_ctrl_c_during_the_apps_request_is_raised_when_the_request_returns(tmp_path):
    # #84 round 3: the test client turns a BaseException in a request into a 500, so the lane holds a Ctrl-C
    # while a request runs and raises it once the request returns; the previous handler comes back after.
    before = signal.getsignal(signal.SIGINT)
    lane = lab_lane.AppLane(tmp_path / "state", adapters_factory=lambda blobs: InterruptingAdapters(blobs, SYNTHETIC_TEXT),
                            persistence="sqlite", segmentation="sam3", subject="subject_105526321")
    with pytest.raises(KeyboardInterrupt):
        with lane:
            lane.ingest("subject_105526321.jpeg", jpeg(), "image/jpeg")
    assert signal.getsignal(signal.SIGINT) is before


def test_a_subclass_of_the_synthetic_adapters_is_not_trusted_as_synthetic(tmp_path):
    # #84 round 3: a subclass can carry production methods (tests/test_model_runtime.py builds one).
    class Carrying(SyntheticAdapters):
        pass

    lane = lab_lane.AppLane(tmp_path / "state", adapters_factory=lambda blobs: Carrying(blobs, SYNTHETIC_TEXT),
                            persistence="sqlite", segmentation="sam3", subject="subject_105526331")
    with pytest.raises(lab_lane.LabError, match="not one of the ten"):
        lane.__enter__()


def test_a_ctrl_c_right_after_the_emulator_is_launched_stops_it(tmp_path, monkeypatch):
    # #84 round 3: the window between Popen and the wait was outside the cleanup.
    killed = []

    class FakeProcess:
        pid, stdout = 999_998, iter(())

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    class InterruptedThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise KeyboardInterrupt

        def is_alive(self):
            return False

    monkeypatch.setattr(lab_lane.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(lab_lane.os, "killpg", lambda pid, sig: killed.append(pid))
    monkeypatch.setattr(lab_lane.threading, "Thread", InterruptedThread)
    with pytest.raises(KeyboardInterrupt):
        lab_lane.Emulator(tmp_path / "emulator").start()
    assert killed == [999_998]
