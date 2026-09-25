"""The lab runner's own logic, with fakes for Cloud Storage and the lane."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

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


def run(tmp_path, *args, lane=None, env=ENV, load=1.0, clock=START, values="default"):
    lanes = []
    private = tmp_path / "private"  # stands in for ~/specimen-release-private/ (PLAN 840)
    if values == "default":
        values = private / "redact-values"
        values.parent.mkdir(parents=True, exist_ok=True)
        values.write_text("adminuidfixture\n")
    env = dict(env) if values is None else dict(env, LAB_REDACT_VALUES_FILE=str(values))
    run_specimen.PRIVATE_ROOT, saved = private, run_specimen.PRIVATE_ROOT

    def lane_factory(state, options, environment):
        lanes.append(lane or FakeLane())
        return lanes[-1]

    options = run_specimen.parse_args(
        [SUBJECT, "--runs-root", str(tmp_path / "runs"),
         "--reports-root", str(tmp_path / "reports"), "--no-logfire", *args]
    )
    try:
        code = run_specimen.execute(
            options, fetch=fetch, lane_factory=lane_factory, env=env,
            clock=lambda: clock, loadavg=lambda: (load, load, load),
            commit=lambda: {"head": "f" * 40, "dirty": False},
        )
    finally:
        run_specimen.PRIVATE_ROOT = saved
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
    # The lab's own running tally against its USD 5.00 share (G9, G30): production's ledger never sees it.
    assert summary["lab_spend_usd"] == pytest.approx(0.00083 + 0.0006)
    assert "Lab spend to date: USD 0.001430 of 5.00" in (path / "report.md").read_text()
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


def test_paid_attempts_without_settled_usage_count_at_their_full_bound():
    # Until production's reserve-then-settle ledger lands, every paid attempt whose usage the run did
    # not settle is held at the full per-call bound: an unknown outcome (coordinator, 2026-09-23) and,
    # since #86, a call that returned and then failed with a known blocker, whose usage the workflow
    # does not record. Local SAM 3 costs nothing.
    earlier = snapshot()["run"] | {
        "id": "run-1", "stage": "processing_blocked", "blocker": "external_outcome_unknown",
        "attempts": {"segment": 1, "parse": 1}, "completed_steps": ["classify"], "observations": [],
    }
    snap = snapshot(stage="processing_blocked", blocker="evidence_integrity_failure",
                    attempts={"transcribe:r1:handwriting-qwen": 2, "parse": 1},
                    completed_steps=["classify", "segment", "transcribe:r1:handwriting-qwen"])
    snap["previous_runs"] = [earlier]
    costs = run_specimen.price(snap)
    # run-1: parse with an unknown outcome; run-2: a retried reader attempt, and parse after a known failure
    assert sorted(costs["unsettled_attempts"]) == ["parse", "parse", "transcribe:r1:handwriting-qwen"]
    assert costs["unsettled_usd_bound"] == pytest.approx(3 * 16_000 * 1.20e-6)
    assert costs["total_usd"] == pytest.approx(
        costs["readers_usd"] + costs["other_usd_upper_bound"] + 3 * 16_000 * 1.20e-6
    )


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


def test_the_redactor_removes_instance_addresses_and_the_sam_lab_token():
    # PLAN 7.7 keeps instance addresses out of shared logs and issues; the app pins the SAM 3
    # endpoint into a run's dependencies, so it reaches snapshot.json (#82 review, finding 11).
    endpoint = "https://specimen-sam-q7w2e9r4-uk.a.run.app"
    lab_token = "L" * 40
    redact = run_specimen.Redactor({"SPECIMEN_SAM3_ENDPOINT": endpoint, "SPECIMEN_SAM3_LAB_TOKEN": lab_token})
    text = redact(json.dumps({"segmentation": {"endpoint": endpoint, "other": "https://api-x1.a.run.app/v1/segment"},
                              "token": lab_token}))
    assert "run.app" not in text and lab_token not in text
    assert json.loads(text)["segmentation"]["endpoint"] == "[redacted]"  # JSON stays valid


def test_the_redactor_covers_plan_7_7_identities_ids_and_key_shapes(tmp_path):
    # PLAN 7.7: the administrator's identity, billing and organization ids, and more secrets (#82 review 2).
    private = tmp_path / "private-values"
    private.write_text("adminuidfixture\n")
    redact = run_specimen.Redactor({
        "HF_BILL_TO": "fmnh", "LOGFIRE_READ_TOKEN": "pylf_v1_us_" + "r" * 30,
        "SPECIMEN_GOOGLE_MAPS_API_KEY": "AIza" + "k" * 35, "LAB_REDACT_VALUES_FILE": str(private),
    })
    text = redact(
        "caller admin@example.org lacks permission; uploader adminuidfixture; billed to fmnh; "
        "fmnhx stays; https://logfire-us.pydantic.dev/owner-org/specimen-digitization; "
        "host specimen-sam-x1.a.run.app; key AIza" + "q" * 35 + "; token pylf_v1_us_" + "z" * 30
    )
    for leak in ("admin@example.org", "adminuidfixture", "owner-org", "run.app", "AIza", "pylf_", " fmnh;"):
        assert leak not in text, leak
    assert "fmnhx stays" in text  # a short value is matched as a whole word only


class OccurrenceLane(FakeLane):
    """GBIF reads leave through bounded_http in the parent (lookup.py); injected clients through httpx."""

    def process(self, specimen_id, deadline):
        import httpx
        from specimen_digitization.application import http_effect

        http_effect.bounded_http("https://API.gbif.org/v1/%6Fccurrence/search", timeout_seconds=1,
                                 max_bytes=1, params={"recordedBy": "Hoogstraal"})
        http_effect.bounded_http("https://api.gbif.org/v2/species/match", timeout_seconds=1, max_bytes=1)
        client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})))
        client.get("https://api.gbif.org/v1/occurrence/search", params={"catalogNumber": "1"})
        return super().process(specimen_id, deadline)


def fake_bounded_http(url, **kwargs):  # sends nothing: no child process, no network
    return {"status_code": 200, "body": b"{}", "retry_after": "", "truncated": False}


def test_the_runner_counts_gbif_occurrence_requests_in_the_parent(tmp_path, monkeypatch):
    # D4 is held; the count is taken at bounded_http before sending, and on any injected httpx client.
    from specimen_digitization.application import http_effect

    monkeypatch.setattr(http_effect, "bounded_http", fake_bounded_http)
    code, _ = run(tmp_path, lane=OccurrenceLane())
    summary = json.loads((only_run(tmp_path) / "run.json").read_text())
    assert summary["gbif_occurrence_requests"] == 2 and code == 1
    assert next(s for s in summary["stages"] if s["stage"] == "7")["status"] == "failed"
    assert http_effect.bounded_http is fake_bounded_http  # restored after the run


def test_a_missing_hook_reads_not_checked_and_receipt_blobs_are_scanned(tmp_path, monkeypatch):
    from specimen_digitization.application import http_effect

    monkeypatch.delattr(http_effect, "bounded_http")
    run(tmp_path / "a")
    summary = json.loads((only_run(tmp_path / "a") / "run.json").read_text())
    assert summary["gbif_occurrence_requests"] is None
    assert next(s for s in summary["stages"] if s["stage"] == "7")["status"] == "not checked"

    class ReceiptLane(FakeLane):
        def collect(self, specimen_id):
            evidence = super().collect(specimen_id)
            evidence["artifacts"]["receipts/c1.json"] = b'{"url": "https://api.gbif.org/v1/occurrence/search"}'
            return evidence

    monkeypatch.setattr(http_effect, "bounded_http", fake_bounded_http, raising=False)
    run(tmp_path / "b", lane=ReceiptLane())
    summary = json.loads((only_run(tmp_path / "b") / "run.json").read_text())
    assert next(s for s in summary["stages"] if s["stage"] == "7")["status"] == "failed"


def test_the_values_file_is_required_private_and_never_in_the_repository(tmp_path):
    empty = tmp_path / "empty"
    empty.write_text("")
    inside = Path(run_specimen.__file__).resolve().parents[2] / "scripts" / "lab" / "never-created"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.write_text("adminuidfixture\n")
    for values in (None, empty, tmp_path / "missing", inside, elsewhere):
        code, lanes = run(tmp_path, values=values)
        assert code == 3 and lanes == [], values
    assert not (tmp_path / "runs" / SUBJECT).exists()  # nothing written
    assert not inside.exists()


def test_fields_that_name_a_person_are_redacted_by_field(tmp_path):
    class PersonLane(FakeLane):
        def collect(self, specimen_id):
            evidence = super().collect(specimen_id)
            snap = evidence["snapshot"]
            snap["asset"]["uploader"] = "Firstname Lastname"
            snap["audit"] = [{"id": "a1", "actor": "Firstname Lastname", "action": "upload", "reason": "",
                              "before": {}, "after": {}, "created_at": "2026-09-25T00:00:00+00:00"}]
            snap["run"]["transcripts"][0]["actor"] = "Firstname Lastname"
            evidence["rows"] = {"audit_event": [{"id": "e1", "actor_uid": "Firstname Lastname"}],
                                "source_asset": [{"id": "a1", "uploader_uid": "Firstname Lastname"}],
                                "profile_version": [{"id": "p1", "approved_by": "Firstname Lastname"}]}
            return evidence

    run(tmp_path, lane=PersonLane())
    path = only_run(tmp_path)
    for name in ("snapshot.json", "rows/audit_event.json", "rows/source_asset.json", "rows/profile_version.json"):
        assert "Firstname Lastname" not in (path / name).read_text(), name
    assert json.loads((path / "snapshot.json").read_text())["asset"]["uploader"] == "[redacted]"


def test_a_persons_verdict_survives_every_rebuild_of_the_subject_report(tmp_path):
    # PLAN 8 step 3 keeps the record in reports/<subject>.md, which the runner rebuilds: a person writes
    # a run's verdict.md, which the runner never writes and carries into the report.
    run(tmp_path)
    verdict = only_run(tmp_path) / "verdict.md"
    verdict.write_text("failed: the review names habitat, which the label states\n")
    run(tmp_path, clock=START + timedelta(hours=1))
    report = (tmp_path / "reports" / f"{SUBJECT}.md").read_text()
    assert "failed: the review names habitat, which the label states" in report
    assert verdict.read_text() == "failed: the review names habitat, which the label states\n"
