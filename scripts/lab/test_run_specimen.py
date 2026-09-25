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
MAPS_FIXTURE = "AIza" + "k" * 35  # the Geocoding key's shape, synthetic
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


def run(tmp_path, *args, lane=None, env=ENV, load=1.0, clock=START, values="default", fetcher=fetch):
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
            options, fetch=fetcher, lane_factory=lane_factory, env=env,
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
    # does not record. Local SAM 3 costs nothing. PLAN 4.3 runs the lab under production's mechanism, so
    # the lab reads the bound as the largest of: the step's reservation in the run's profile, PLAN 4.3's
    # floor for a call's two requests (USD 0.04), and the call's 16,000-token limit at the top price.
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
    assert costs["unsettled_usd_bound"] == pytest.approx(3 * 0.04)
    assert costs["total_usd"] == pytest.approx(costs["readers_usd"] + costs["other_usd_upper_bound"] + 3 * 0.04)


def test_a_uniform_request_reservation_counts_when_the_profile_has_no_stage_reservations():
    # #84 round 1: workflow.py reserves request_cost_reservation_micros per step when no stage reservations exist.
    snap = snapshot(stage="processing_blocked", blocker="external_outcome_unknown", attempts={"parse": 1},
                    completed_steps=["classify", "segment"])
    snap["run"]["profile"]["execution"]["request_cost_reservation_micros"] = 70_000
    assert run_specimen.price(snap)["unsettled_usd_bound"] == pytest.approx(0.07)


def test_a_reservation_the_profile_records_raises_the_bound_for_its_step():
    snap = snapshot(stage="processing_blocked", blocker="external_outcome_unknown",
                    attempts={"transcribe:r1:handwriting-qwen": 2, "parse": 1},
                    completed_steps=["classify", "segment", "transcribe:r1:handwriting-qwen"])
    snap["run"]["profile"]["execution"]["stage_cost_reservations"] = {
        "version": "stage-cost-reservations-v1",
        "cost_micros": {"transcribe:handwriting-qwen": 90_000, "parse": 30_000}}
    costs = run_specimen.price(snap)
    assert costs["unsettled_usd_bound"] == pytest.approx(0.09 + 0.04)  # parse's 0.03 is below the floor


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


def test_the_redactor_covers_plan_7_7_identities_ids_and_key_shapes():
    # PLAN 7.7: the administrator's identity, billing and organization ids, and more secrets (#82 review 2).
    # Every value is synthetic. The private values come from the caller, which read the file once (#83 round 1).
    redact = run_specimen.Redactor({
        "HF_BILL_TO": "example-billing-org", "LOGFIRE_READ_TOKEN": "pylf_v1_us_" + "r" * 30,
        "SPECIMEN_GOOGLE_MAPS_API_KEY": MAPS_FIXTURE,
    }, values={"adminuidfixture", "zq7"})
    text = redact(
        "caller admin@example.org lacks permission; uploader adminuidfixture; billed to example-billing-org; "
        "short zq7; zq7x stays; https://logfire-us.pydantic.dev/owner-org/specimen-digitization; "
        "host specimen-sam-x1.a.run.app; key AIza" + "q" * 35 + "; token pylf_v1_us_" + "z" * 30
    )
    for leak in ("admin@example.org", "adminuidfixture", "example-billing-org", "owner-org", "run.app", "AIza",
                 "pylf_", "short zq7;"):
        assert leak not in text, leak
    assert "zq7x stays" in text  # a short value is matched as a whole word only


def test_the_redactor_ignores_case_and_percent_encoding():
    # #83 round 1: an upper-case host, a mixed-case Logfire address, a %40-encoded email and a listed value
    # in another case all survived.
    redact = run_specimen.Redactor({"HF_BILL_TO": "Example-Billing-Org"})
    text = redact("host SPECIMEN-SAM-X1.A.RUN.APP; https://Logfire-US.pydantic.dev/Owner-Org/project; "
                  "caller admin%40example.org, again admin%2540example.org; "
                  "billed to example-billing-org and EXAMPLE-BILLING-ORG")
    for leak in ("RUN.APP", "Owner-Org", "admin%40example.org", "admin%2540example.org", "example-billing-org",
                 "EXAMPLE-BILLING-ORG"):
        assert leak not in text, leak


def test_home_paths_are_found_in_any_case(monkeypatch):
    # #83 round 2: macOS paths ignore case, so a home path can be written in another case; #84 round 1: a
    # home path that ends a sentence is found too, but not a longer name that starts with it.
    monkeypatch.setenv("HOME", "/Users/labfixture")
    redact = run_specimen.Redactor({})
    assert redact("/users/labfixture/runs and /USERS/LABFIXTURE/x") == "~/runs and ~/x"
    text = "saved under /Users/labfixture. Then /Users/labfixture.old"
    assert redact(text) == "saved under ~. Then /Users/labfixture.old"


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
            snap["run"]["classification_selection"] = {"collection_id": "c", "actor_id": "Firstname Lastname",
                                                       "reason": "Explicit synthetic fixture intake selection"}
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


class PlantedLane(FakeLane):
    """A private value where no person field names it: only the values file can redact it."""

    def collect(self, specimen_id):
        evidence = super().collect(specimen_id)
        evidence["workspace"]["note"] = "signed in as adminuidfixture"
        return evidence


def test_the_tilde_form_of_the_values_file_redacts_its_values(tmp_path, monkeypatch):
    # #83 round 1 (blocking): preflight expanded "~" while the redactor read the raw path and loaded nothing.
    monkeypatch.setenv("HOME", str(tmp_path))
    values = tmp_path / "private" / "redact-values"
    values.parent.mkdir()
    values.write_text("adminuidfixture\n")
    run(tmp_path, lane=PlantedLane(), values="~/private/redact-values")
    assert "adminuidfixture" not in (only_run(tmp_path) / "workspace.json").read_text()


def test_the_values_file_is_located_before_any_read_and_read_once(tmp_path, monkeypatch):
    # #83 round 1: the redactor read the file before the location check, and apart from preflight's read.
    reads = []
    original = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: reads.append(Path(self)) or original(self, *a, **k))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.write_text("adminuidfixture\n")
    code, lanes = run(tmp_path / "a", values=elsewhere)
    assert code == 3 and lanes == [] and elsewhere not in reads
    run(tmp_path / "b")
    values = (tmp_path / "b" / "private" / "redact-values").resolve()
    assert [p for p in reads if p.resolve() == values] == [values]


def test_a_values_file_without_a_usable_value_is_refused(tmp_path):
    # Values shorter than 3 characters are never matched, so such a file redacts nothing (#83 round 1).
    short = tmp_path / "private" / "short-values"
    short.parent.mkdir()
    short.write_text("a\nbb\n \n")
    code, lanes = run(tmp_path, values=short)
    assert code == 3 and lanes == []
    assert not (tmp_path / "runs" / SUBJECT).exists()


class CollectFailsLane(FakeLane):
    def collect(self, specimen_id):
        raise RuntimeError("the emulator dump failed")


class TeardownFailsLane(FakeLane):
    def __exit__(self, *exc):
        super().__exit__(*exc)
        raise RuntimeError("could not stop the emulator")


def test_a_run_that_cannot_be_priced_is_held_at_its_bound(tmp_path):
    # #83 round 1: after the lane starts, paid calls may have run, so an unpriced run counts at
    # --max-run-usd, the most one run may cost, and the next preflight sees it.
    code, _ = run(tmp_path, lane=CollectFailsLane())
    summary = json.loads((only_run(tmp_path) / "run.json").read_text())
    assert code == 2 and summary["result"] == "error"
    assert summary["costs"]["total_usd"] == pytest.approx(0.75)
    assert summary["lab_spend_usd"] == pytest.approx(0.75)
    assert run_specimen.recorded_spend(tmp_path / "runs") == pytest.approx(0.75)
    assert "the lab's own rule" in (only_run(tmp_path) / "report.md").read_text()


def test_a_failed_check_keeps_the_priced_spend(tmp_path, monkeypatch):
    def broken(*args):
        raise KeyError("stage")

    monkeypatch.setattr(run_specimen.lab_checks, "check_stages", broken)
    code, _ = run(tmp_path)
    summary = json.loads((only_run(tmp_path) / "run.json").read_text())
    assert code == 2 and summary["costs"]["total_usd"] == pytest.approx(0.00083 + 0.0006)


def test_a_lane_teardown_error_still_writes_the_run_its_reports_and_spend(tmp_path):
    try:
        code, _ = run(tmp_path, lane=TeardownFailsLane())
    except RuntimeError:
        code = None  # the error escaped, and with it the record
    path = only_run(tmp_path)
    assert (path / "run.json").is_file() and (path / "report.md").is_file()
    assert (tmp_path / "reports" / f"{SUBJECT}.md").is_file()
    summary = json.loads((path / "run.json").read_text())
    assert code == 2 and summary["result"] == "error"
    assert summary["costs"]["total_usd"] == pytest.approx(0.00083 + 0.0006)
    assert any(p["status"] == "failed" and "could not stop the emulator" in p["error"] for p in summary["phases"])


class DotSegmentLane(FakeLane):
    """Requests a client sends to the occurrence API, or with occurrence query keys (#83 round 1)."""

    def process(self, specimen_id, deadline):
        import httpx
        from specimen_digitization.application import http_effect

        for url in ("https://api.gbif.org/v1/./occurrence/search", "https://api.gbif.org/v1/x/../occurrence/search",
                    "https://api.gbif.org/v1/././occurrence", "https://api.gbif.org/v1/species/search?catalogNumber=1",
                    "https://api.gbif.org/../v1/occurrence/search",  # ".." above the root (#83 round 2)
                    # #84 round 1: encoded dots, merged slashes and a trailing host dot
                    "https://api.gbif.org/%2E%2E/v1/occurrence/search", "https://api.gbif.org/v1//occurrence/12345",
                    "https://api.gbif.org./v1/occurrence/search", "https://api.gbif.org//v1/occurrence/search",
                    "https://api.gbif.org/v2/%2e%2e/%2e%2e/v1/occurrence/search",
                    "https://api.gbif.org/v2/species/match?name=Epipsocus"):  # the last is species match
            http_effect.bounded_http(url, timeout_seconds=1, max_bytes=1)
        http_effect.bounded_http("https://api.gbif.org/v1/species/search", timeout_seconds=1, max_bytes=1,
                                 params=httpx.QueryParams({"recordedBy": "Hoogstraal"}))
        client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})))
        client.get("https://api.gbif.org/v1/species/search", params={"recordedBy": "Hoogstraal"})
        client.get("https://api.gbif.org/v1/species/search?institutionCode=FMNH")
        client.get("https://api.gbif.org/v2/species/match", params={"name": "Epipsocus"})  # not counted
        return super().process(specimen_id, deadline)


def test_the_parent_count_removes_dot_segments_and_reads_query_keys_in_the_url(tmp_path, monkeypatch):
    from specimen_digitization.application import http_effect

    monkeypatch.setattr(http_effect, "bounded_http", fake_bounded_http)
    run(tmp_path, lane=DotSegmentLane())
    summary = json.loads((only_run(tmp_path) / "run.json").read_text())
    assert summary["gbif_occurrence_requests"] == 13


def test_a_receipt_blob_recording_an_occurrence_query_fails_stage_7(tmp_path, monkeypatch):
    # #83 round 1: the blob scan applied only the text test, not the record test.
    from specimen_digitization.application import http_effect

    class RecordReceiptLane(FakeLane):
        def collect(self, specimen_id):
            evidence = super().collect(specimen_id)
            evidence["artifacts"]["receipts/c2.json"] = json.dumps(
                {"source": "gbif", "arguments": {"recordedBy": "Hoogstraal"}}).encode()
            return evidence

    monkeypatch.setattr(http_effect, "bounded_http", fake_bounded_http)
    run(tmp_path, lane=RecordReceiptLane())
    summary = json.loads((only_run(tmp_path) / "run.json").read_text())
    assert next(s for s in summary["stages"] if s["stage"] == "7")["status"] == "failed"


def test_every_text_artifact_is_redacted_whatever_its_suffix(tmp_path):
    class SuffixLane(FakeLane):
        def collect(self, specimen_id):
            evidence = super().collect(specimen_id)
            for name in ("responses/o-r1-handwriting-muse.JSON", "rows-extra/t.jsonl", "receipts/raw"):
                evidence["artifacts"][name] = ("Bearer " + TOKEN).encode()
            return evidence

    run(tmp_path, lane=SuffixLane())
    path = only_run(tmp_path)
    for name in ("responses/o-r1-handwriting-muse.JSON", "rows-extra/t.jsonl", "receipts/raw"):
        assert TOKEN.encode() not in (path / name).read_bytes(), name
    assert (path / "crops/r1.png").read_bytes() == b"\x89PNG crop"  # binary is written as it came


def test_paths_under_the_home_directory_are_written_relative_to_it(tmp_path, monkeypatch):
    # #83 round 1: the account name in a home path equals the Logfire organization slug (PLAN 7.7).
    monkeypatch.setenv("HOME", str(tmp_path))
    run(tmp_path)
    for text in ((only_run(tmp_path) / "run.json").read_text(), (tmp_path / "reports" / f"{SUBJECT}.md").read_text()):
        assert str(tmp_path) not in text and "~/runs" in text


def test_a_verdict_that_is_not_utf8_is_named_and_never_breaks_the_report(tmp_path):
    run(tmp_path)
    (only_run(tmp_path) / "verdict.md").write_bytes(b"\xff\xfe failed: habitat\n")
    run(tmp_path, clock=START + timedelta(hours=1))
    assert "verdict.md is not UTF-8 text" in (tmp_path / "reports" / f"{SUBJECT}.md").read_text()


def test_a_report_only_rebuild_carries_a_new_verdict_without_preflight_or_fetch(tmp_path):
    # PLAN 8 step 3: a person's final verdict reaches reports/<subject>.md without another run (#83 round 1).
    run(tmp_path)
    (only_run(tmp_path) / "verdict.md").write_text("passed: every reason matches the expected outcome\n")

    def no_fetch(subject):
        raise AssertionError("a report-only rebuild fetches nothing")

    code, lanes = run(tmp_path, "--report-only", load=99.0, env={}, fetcher=no_fetch)
    assert code == 0 and lanes == []
    assert len(list((tmp_path / "runs" / SUBJECT).iterdir())) == 1
    report = (tmp_path / "reports" / f"{SUBJECT}.md").read_text()
    assert "passed: every reason matches the expected outcome" in report
    code, _ = run(tmp_path, "--report-only", values=None, fetcher=no_fetch)
    assert code == 3  # the report is redacted, so the values file is still required


@pytest.mark.parametrize("line", ["ADMIN_UID=adminuidfixture", '"adminuidfixture"', "adminuidfixture # admin",
                                  "admin uid fixture", "'adminuidfixture'", "uid1fixture,uid2fixture",
                                  "adminuidfixture\u200b", "adminuidfixture\nsecondvalue\ufeff"])
def test_a_values_file_line_that_is_not_one_bare_value_is_refused(tmp_path, line, capsys):
    # #83 round 2: such a file passed, and its value never matched anything. The refusal names the line
    # number, never its private content.
    values = tmp_path / "private" / "values"
    values.parent.mkdir()
    values.write_text(f"{line}\n")
    code, lanes = run(tmp_path, values=values)
    assert code == 3 and lanes == []
    captured = capsys.readouterr()
    assert "lines [" in captured.err and "adminuidfixture" not in captured.out + captured.err


def test_a_byte_order_mark_does_not_hide_the_first_value(tmp_path):
    values = tmp_path / "private" / "values"
    values.parent.mkdir()
    values.write_bytes("\ufeffadminuidfixture\n".encode())
    run(tmp_path, lane=PlantedLane(), values=values)
    assert "adminuidfixture" not in (only_run(tmp_path) / "workspace.json").read_text()


def test_a_report_only_rebuild_without_any_run_is_refused(tmp_path):
    code, lanes = run(tmp_path, "--report-only")
    assert code == 3 and lanes == []
    assert not (tmp_path / "reports" / f"{SUBJECT}.md").exists()


class InterruptedLane(FakeLane):
    def process(self, specimen_id, deadline):
        raise KeyboardInterrupt


def test_ctrl_c_is_recorded_as_a_failure_and_the_run_held_at_its_bound(tmp_path):
    # #83 round 2: an interrupted phase was recorded as passed.
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, lane=InterruptedLane())
    summary = json.loads((only_run(tmp_path) / "run.json").read_text())
    process = next(p for p in summary["phases"] if p["name"] == "process")
    assert process["status"] == "failed" and "KeyboardInterrupt" in process["error"]
    assert summary["result"] == "error" and summary["costs"]["total_usd"] == pytest.approx(0.75)


class InterruptedTeardownLane(InterruptedLane):
    def __exit__(self, *exc):
        super().__exit__(*exc)
        raise RuntimeError("could not stop the emulator")


def test_ctrl_c_still_stops_the_run_when_the_teardown_then_fails(tmp_path):
    # #84 round 1: the teardown's error replaced the interrupt, so the check ran and execute returned 2.
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, lane=InterruptedTeardownLane())
    summary = json.loads((only_run(tmp_path) / "run.json").read_text())
    names = {p["name"]: p for p in summary["phases"]}
    assert "check" not in names and names["teardown"]["status"] == "failed"
    assert summary["costs"]["total_usd"] == pytest.approx(0.75)


def test_run_json_holds_the_run_bound_from_the_moment_the_lane_starts(tmp_path):
    # #84 round 1: a run killed after the lane starts must still count in the tally (G9).
    seen = {}

    class WatchingLane(FakeLane):
        def ingest(self, filename, data, media_type):
            record = self.state.parent / "run.json"
            seen["total"] = json.loads(record.read_text())["costs"]["total_usd"] if record.exists() else None
            return super().ingest(filename, data, media_type)

    lane = WatchingLane()
    original = run_specimen.execute

    def execute(options, *, lane_factory, **kwargs):
        def factory(state, opts, env):
            lane.state = state
            return lane_factory(state, opts, env)
        return original(options, lane_factory=factory, **kwargs)

    run_specimen.execute, saved = execute, run_specimen.execute
    try:
        run(tmp_path, lane=lane)
    finally:
        run_specimen.execute = saved
    assert seen["total"] == pytest.approx(0.75)
    summary = json.loads((only_run(tmp_path) / "run.json").read_text())
    assert summary["costs"]["total_usd"] == pytest.approx(0.00083 + 0.0006)  # priced at the end
    assert summary["lab_spend_usd"] == pytest.approx(0.00083 + 0.0006)  # the run counts once


@pytest.mark.parametrize("total", ["NaN", "-0.5", '"0.1"', None])
def test_a_tally_that_cannot_be_trusted_stops_the_next_run(tmp_path, total):
    # #84 round 1: an unreadable or non-finite total was skipped or passed preflight's comparison, and an
    # adjustment may only raise the tally.
    earlier = tmp_path / "runs" / "_adjustments" / "20260925T000000Z"
    earlier.mkdir(parents=True)
    (earlier / "run.json").write_text("{not json" if total is None else '{"costs": {"total_usd": %s}}' % total)
    code, lanes = run(tmp_path)
    assert code == 3 and lanes == []


def test_main_refuses_a_slide_outside_the_ten_before_any_fetch(tmp_path, monkeypatch):
    # #84 round 1 (blocking): only the ten are not sensitive (G31); a run of any other slide would send a
    # Sensitive image to the model providers. A dry run builds no lane and fetches only.
    calls = []
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setattr(run_specimen, "execute", lambda options, **kwargs: calls.append(options.subject) or 0)
    roots = ["--runs-root", str(tmp_path / "runs"), "--reports-root", str(tmp_path / "reports")]
    assert run_specimen.main(["subject_105526331", *roots]) == 3 and calls == []
    assert run_specimen.main(["subject_105526331", "--dry-run", *roots]) == 0
    assert run_specimen.main(["subject_105526321", *roots]) == 0
    assert calls == ["subject_105526331", "subject_105526321"]
