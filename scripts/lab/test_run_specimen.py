"""The lab runner's own logic, with fakes for Cloud Storage and the lane."""

from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

import run_specimen
from test_lab_checks import SUBJECT, snapshot

TOKEN = "hf_" + "Q7" * 15
ENV = {"HF_TOKEN": TOKEN, "SPECIMEN_APPROVED_INFERENCE": "true"}
IMAGE = b"\xff\xd8\xff\xe0 lab fixture bytes"
START = datetime(2026, 9, 23, 20, 15, tzinfo=timezone.utc)


class FakeLane:
    def __init__(self, fail=None):
        self.fail, self.calls, self.closed = fail, [], False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True

    def ingest(self, filename, data, media_type):
        self.calls.append(("ingest", filename, media_type))
        return "specimen-1"

    def process(self, specimen_id, deadline):
        self.calls.append(("process", specimen_id))
        if self.fail:
            raise RuntimeError("provider refused Bearer " + TOKEN)
        return [{"action": "reviewed_region", "reason": "lab substitute"}]

    def collect(self, specimen_id):
        snap = snapshot()
        snap["asset"]["sha256"] = hashlib.sha256(IMAGE).hexdigest()
        snap["run"]["usage"]["tokens"] = 2200 + 500
        return {
            "snapshot": snap,
            "workspace": {"specimen_id": specimen_id, "echo": TOKEN},
            "artifacts": {
                "crops/r1.png": b"\x89PNG crop",
                "responses/o-r1-handwriting-qwen.json": json.dumps(
                    {"headers": {"authorization": "Bearer " + TOKEN}}
                ).encode(),
            },
            "rows": {},
            "actions": [],
        }


def fetch(subject):
    return IMAGE, {"bucket": "b", "object_name": f"p/{subject}.jpeg", "generation": "1"}


def run(tmp_path, *args, lane=None, env=ENV, load=1.0, clock=START):
    lanes = []

    def lane_factory(state, options, environment):
        lanes.append(lane or FakeLane())
        return lanes[-1]

    options = run_specimen.parse_args(
        [SUBJECT, "--runs-root", str(tmp_path / "runs"),
         "--reports-root", str(tmp_path / "reports"), "--no-logfire", *args]
    )
    code = run_specimen.execute(
        options, fetch=fetch, lane_factory=lane_factory, env=env,
        clock=lambda: clock, loadavg=lambda: (load, load, load),
        commit=lambda: {"head": "f" * 40, "dirty": False},
    )
    return code, lanes


def only_run(tmp_path):
    [path] = (tmp_path / "runs" / SUBJECT).iterdir()
    return path


def test_a_run_writes_its_evidence_and_report_and_never_a_token(tmp_path):
    code, [lane] = run(tmp_path, "--persistence", "sqlite")
    assert code == 1  # incomplete: stages 4, 6, 7 and tracing are not built on this commit
    path = only_run(tmp_path)
    assert path.name == "20260923T201500Z"
    for name in (
        "run.json", "report.md", "runner.log", "snapshot.json", "workspace.json",
        f"inputs/{SUBJECT}.jpeg", "inputs/source.json", "crops/r1.png",
        "responses/o-r1-handwriting-qwen.json",
    ):
        assert (path / name).is_file(), name
    written = [p for p in path.rglob("*") if p.is_file()]
    written.append(tmp_path / "reports" / f"{SUBJECT}.md")
    assert all(TOKEN.encode() not in p.read_bytes() for p in written)
    summary = json.loads((path / "run.json").read_text())
    assert summary["result"] == "incomplete"
    assert [p["name"] for p in summary["phases"]] == [
        "preflight", "fetch", "ingest", "process", "collect", "check", "report"
    ]
    assert {p["status"] for p in summary["phases"]} == {"passed"}
    assert summary["source"]["sha256"] == hashlib.sha256(IMAGE).hexdigest()
    assert summary["costs"]["total_usd"] == pytest.approx(0.00083 + 0.0006)
    assert summary["actions"] == [{"action": "reviewed_region", "reason": "lab substitute"}]
    assert lane.calls[0] == ("ingest", SUBJECT + ".jpeg", "image/jpeg") and lane.closed
    assert "| 2 Label segmentation | substituted |" in (path / "report.md").read_text()


def test_a_failed_phase_is_recorded_redacted_and_still_reported(tmp_path):
    code, [lane] = run(tmp_path, lane=FakeLane(fail=True))
    assert code == 2 and lane.closed
    summary = json.loads((only_run(tmp_path) / "run.json").read_text())
    failed = [p for p in summary["phases"] if p["status"] != "passed"]
    assert failed[0]["name"] == "process"
    assert failed[0]["error"] == "RuntimeError: provider refused Bearer [redacted]"
    assert summary["result"] == "error"
    assert (only_run(tmp_path) / "report.md").is_file()


@pytest.mark.parametrize(
    "env, load, spent",
    [
        (ENV, 12.0, 0),  # machine too busy (PLAN 7.4)
        ({"HF_TOKEN": TOKEN}, 1.0, 0),  # inference switch off
        ({"SPECIMEN_APPROVED_INFERENCE": "true"}, 1.0, 0),  # no token
        (ENV, 1.0, 4.5),  # allowance: 4.5 spent + 0.75 bound > 5.00
    ],
)
def test_preflight_refuses_before_any_fetch_or_paid_call(tmp_path, env, load, spent):
    earlier = tmp_path / "runs" / "subject_1" / "20260901T000000Z"
    earlier.mkdir(parents=True)
    (earlier / "run.json").write_text(json.dumps({"costs": {"total_usd": spent}}))
    code, lanes = run(tmp_path, env=env, load=load)
    assert code == 3 and lanes == []
    assert not (tmp_path / "runs" / SUBJECT).exists()


def test_a_dry_run_fetches_but_never_builds_the_lane(tmp_path):
    code, lanes = run(tmp_path, "--dry-run", env={})
    assert code == 0 and lanes == []
    summary = json.loads((only_run(tmp_path) / "run.json").read_text())
    assert summary["result"] == "dry-run" and summary["costs"]["total_usd"] == 0


def test_the_subject_report_lists_every_run_newest_first(tmp_path):
    run(tmp_path)
    run(tmp_path, clock=START + timedelta(hours=1))
    run(tmp_path, clock=START + timedelta(hours=1))  # same second: a distinct directory
    runs = sorted(p.name for p in (tmp_path / "runs" / SUBJECT).iterdir())
    assert runs == ["20260923T201500Z", "20260923T211500Z", "20260923T211500Z-2"]
    report = (tmp_path / "reports" / f"{SUBJECT}.md").read_text()
    assert report.index("20260923T211500Z-2") < report.index("20260923T211500Z |")
    assert report.index("20260923T211500Z |") < report.index("20260923T201500Z")


def test_costs_price_each_reading_and_bound_the_remaining_tokens():
    snap = snapshot()
    snap["run"]["usage"]["tokens"] = 2200 + 500
    snap["run"]["observations"][1]["route_id"] = "unknown-route"
    costs = run_specimen.price(snap)
    assert costs["readers_usd"] == pytest.approx(0.00032)
    assert costs["unpriced_routes"] == ["unknown-route"]
    assert costs["other_tokens"] == 500 + 1100  # the unpriced reading joins the bound
    assert costs["other_usd_upper_bound"] == pytest.approx(1600 * 1.20e-6)


def test_the_redactor_removes_token_values_and_token_shapes():
    redact = run_specimen.Redactor({"HF_TOKEN": TOKEN, "SPECIMEN_APPROVED_INFERENCE": "true"})
    text = redact(
        f"{TOKEN} hf_{'z' * 24} Authorization: Bearer abc.def-ghi "
        "ya29.A0AfB_byC-1234567890 eyJhbGciOiJSUzI1.eyJzdWIiOiIxMjM0.c2lnbmF0dXJlMTIz true"
    )
    assert "hf_" not in text and "abc.def" not in text and "ya29." not in text
    assert "eyJ" not in text and text.endswith(" true")
