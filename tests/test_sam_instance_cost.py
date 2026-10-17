"""A SAM 3 call settles at the instance time it caused (PLAN 4.3).

specimen-sam runs with CPU always allocated (`run.googleapis.com/cpu-throttling:
"false"`, scripts/release/deploy_models.py), so Cloud Run bills it by instance:
its whole life from start to shutdown, idle time included, and keeps an idle
instance up to 15 minutes after its last request. On 2026-10-17 the 11-record
batch used two instances for 4,168.0 billable seconds, about 446,490
micro-dollars at the instance-based rates, while the ledger held 182,321 for
each call, 2,005,531 in all. The worker's request seconds alone (41 to 134 s a
call) would miss the idle time, which was 84% of what was billed.

The service now reports, beside each answer, its own seconds and the instance
seconds before it (sam3_server.InstanceMeter); each call pays those, and the
instance's first call also pays the start and the last idle wait
(lane_costs.segmentation_instance_cost). A call with no report stays reserved.
"""

import json
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.lane_costs import (
    record_segmentation,
    segmentation_instance_cost,
)
from specimen_digitization.application.lane_reservations import step_reservation
from specimen_digitization.application.sam3_effect import (
    INSTANCE_HEADER,
    _instance_header,
    instance_accounting,
)
from specimen_digitization.application.sam3_server import InstanceMeter, create_app

from test_lane_costs import priced_run
from test_lane_sam_server import image_bytes, post, run_request

PRICES = published_registry().resolve("insects").profile.processing.price_list.model_dump(
    mode="json"
)
FIRST = {"first": True, "idle_seconds": 80.443, "request_seconds": 41.626}
LATER = {"first": False, "idle_seconds": 131.24, "request_seconds": 39.794}


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Timed:
    """A segmenter that takes the given seconds on the clock; a `None` refuses."""

    def __init__(self, clock, *seconds):
        self.clock, self.seconds = clock, list(seconds)

    def segment(self, request):
        took = self.seconds.pop(0)
        self.clock.now += took or 1
        if took is None:
            raise HTTPException(429, "sam3_busy")
        return {"run_id": request.run_id}


def metered(*seconds):
    clock = Clock()
    meter = InstanceMeter(started=0.0, clock=clock)

    def auth(header):
        if header != "Bearer fixture":
            raise ValueError("denied")

    app = create_app(Timed(clock, *seconds), auth, meter=meter)
    return clock, TestClient(app)


def reported(response):
    raw = response.headers.get(INSTANCE_HEADER)
    return None if raw is None else json.loads(raw)


def test_the_service_reports_each_requests_instance_time():
    clock, client = metered(40, 45, None, 30)
    raw = image_bytes()
    clock.now = 80.0  # The instance started 80 s before its first request.
    first = post(client, run_request(raw, run_id="run-a"))
    clock.now = 300.0
    second = post(client, run_request(raw, run_id="run-b"))
    clock.now = 400.0
    refused = post(client, run_request(raw, run_id="run-c"))
    clock.now = 500.0
    fourth = post(client, run_request(raw, run_id="run-d"))
    assert [r.status_code for r in (first, second, refused, fourth)] == [200, 200, 429, 200]
    assert reported(first) == {"first": True, "idle_seconds": 80.0, "request_seconds": 40.0}
    # Idle since the first one ended (at 120 s).
    assert reported(second) == {"first": False, "idle_seconds": 180.0, "request_seconds": 45.0}
    # A refusal reports nothing (its call stays reserved), but it used the
    # instance: the next request's idle time counts from its end, at 401 s.
    assert reported(refused) is None
    assert reported(fourth) == {"first": False, "idle_seconds": 99.0, "request_seconds": 30.0}
    # The report is beside the answer, never in it: a repeat of a run is
    # answered from its stored response, and reports its own instance time.
    assert INSTANCE_HEADER.lower() not in json.dumps(first.json()).lower()


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "not json",
        json.dumps({"first": "yes", "idle_seconds": 1, "request_seconds": 1}),
        json.dumps({"first": True, "idle_seconds": -1, "request_seconds": 1}),
        json.dumps({"first": True, "idle_seconds": 1}),
        json.dumps({"first": True, "idle_seconds": 1, "request_seconds": 1e9}),
        '{"first": true, "idle_seconds": NaN, "request_seconds": 1}',
        json.dumps(dict(FIRST, extra=1)),
        "x" * 300,
    ],
)
def test_an_instance_report_that_is_not_one_is_ignored(header):
    assert _instance_header(header) is None


def test_the_worker_keeps_the_report_on_the_run(monkeypatch, tmp_path):
    # The effect child reads the header (sam3_effect._exchange); the adapter
    # keeps it with the segmentation it saves.
    import httpx

    from specimen_digitization.application import production
    import specimen_digitization.application.bounded_effect as bounded
    from specimen_digitization.application.sam3_effect import sam3_run_request
    from specimen_digitization.application.sam3_server import RunSegmenter
    from specimen_digitization.application.storage import LocalBlobs

    from test_lane_sam_client import isolated, lane_specimen
    from test_lane_sam_detections import PILOT_PARAMETERS, DetectionEngine
    from test_lane_sam_server import RunObjects
    from specimen_digitization.application.collection_profiles import (
        Sam3Parameters,
        SegmentationSettings,
    )
    from specimen_digitization.application.sam3_effect import canonical_sha256

    raw = image_bytes()
    engine = DetectionEngine()
    engine.checkpoint_sha256 = canonical_sha256(engine.checkpoint_files)
    clock = Clock()
    clock.now = 75.0
    app = create_app(
        RunSegmenter(RunObjects(raw), engine),
        lambda header: None,
        meter=InstanceMeter(started=0.0, clock=clock),
    )
    monkeypatch.setattr(httpx, "Client", lambda **settings: TestClient(app))
    monkeypatch.setattr(
        bounded,
        "run_isolated",
        lambda effect, payload, *args, **kwargs: isolated(
            "completed", "ok", sam3_run_request(dict(payload, lab_token="fixture"))
        ),
    )
    specimen = lane_specimen()
    specimen.run.profile_rules["segmentation_settings"] = SegmentationSettings(
        prompt="label", parameters=Sam3Parameters(**PILOT_PARAMETERS)
    ).model_dump(mode="json")
    specimen.run.dependencies["segmentation"]["checkpoint_sha256"] = engine.checkpoint_sha256
    service = production.Sam3Service(
        "https://sam.run.app", LocalBlobs(tmp_path), effect=lambda payload: b""
    )
    assert service.segment_per_run(specimen)
    instance = specimen.run.segmentation["instance"]
    assert instance == {"first": True, "idle_seconds": 75.0, "request_seconds": 0.0}
    assert instance_accounting(instance) == instance


def test_the_instances_first_request_pays_its_start_and_its_last_idle_wait():
    # f35af3a5, the first request on 2026-10-17's first instance. At the
    # instance-based rates (4 x 18 + 16 x 2 = 104 micro-dollars a second):
    # its start (80.443 s measured, plus 30 s before the server's clock),
    # its 41.626 s, and the last idle wait (900 + 20 s) and shutdown (10 s),
    # 1,082.069 s; and the start's CPU boost (4 more vCPU at 18 for 120.443 s).
    assert segmentation_instance_cost(PRICES, FIRST) == 121_208
    assert 1_082.069 * 104 + 120.443 * 4 * 18 == pytest.approx(121_207.08, abs=0.01)


def test_a_later_request_pays_its_own_time_and_the_idle_time_before_it():
    # 48a71d53, 131.24 s after the request before it ended: 171.034 s at 104.
    assert segmentation_instance_cost(PRICES, LATER) == 17_788


def test_idle_time_past_what_cloud_run_allows_is_not_the_runs():
    # Only a minimum instance kept warm idles longer than 15 minutes; the
    # infrastructure budget carries that (lane_reservations).
    warm = dict(LATER, idle_seconds=5_000)
    assert segmentation_instance_cost(PRICES, warm) == segmentation_instance_cost(
        PRICES, dict(LATER, idle_seconds=920)
    )
    cold = dict(FIRST, idle_seconds=5_000)
    assert segmentation_instance_cost(PRICES, cold) == segmentation_instance_cost(
        PRICES, dict(FIRST, idle_seconds=600)
    )


def at(clock):
    return datetime.fromisoformat(f"2026-10-17T{clock}+00:00").timestamp()


# SAM's request log of 2026-10-17: each instance's measured start, and each
# request's start and latency (the first one's includes the start).
BATCH = [
    (80.443, [("16:28:38.754", 122.069), ("16:32:52.063", 39.794), ("16:36:17.179", 41.787),
              ("16:39:52.661", 40.820), ("16:41:53.290", 41.853), ("16:43:59.225", 42.735)]),
    (80.387, [("17:53:16.749", 131.907), ("17:58:12.779", 51.600), ("18:00:16.814", 48.995),
              ("18:01:48.659", 51.972), ("18:17:12.748", 49.051)]),
]
# Cloud Monitoring's billable_instance_time for those two instances, at 104 a
# second, plus the startup boost (4 vCPU at 18 for each start and 10 s after).
BILLED = 446_490


def batch_reports():
    for startup, requests in BATCH:
        ended = None
        for number, (start, latency) in enumerate(requests):
            if number == 0:
                yield {"first": True, "idle_seconds": startup, "request_seconds": latency - startup}
            else:
                yield {"first": False, "idle_seconds": at(start) - ended, "request_seconds": latency}
            ended = at(start) + latency


def test_the_batch_of_2026_10_17_is_charged_close_to_what_cloud_run_billed():
    assert 4_167.98 * 104 + 2 * 90.4 * 4 * 18 == pytest.approx(BILLED, abs=20)
    charged = [segmentation_instance_cost(PRICES, report) for report in batch_reports()]
    assert len(charged) == 11
    # Never less than the bill, and within 6% of it, against 2,005,531 held.
    assert BILLED <= sum(charged) == 471_644 <= BILLED * 1.06
    assert sum(charged) < 11 * 182_321 / 4


def test_a_reported_call_settles_and_one_without_a_report_stays_reserved():
    run = priced_run()
    run.profile.execution = run.profile.execution.model_copy(
        update={"price_list": PRICES}
    )
    record_segmentation(run, "segment", seconds=53.1, instance=LATER)
    record_segmentation(run, "segment", seconds=53.1, instance={"first": True})
    settled, held = run.paid_calls
    assert (settled["cost_basis"], settled["cost_micros"]) == ("computed", 17_788)
    assert settled["usage"] == {"seconds": 53.1, "vcpus": 4, "memory_gib": 16, "instance": LATER}
    assert (held["cost_basis"], held["cost_micros"]) == ("reserved", step_reservation(run, "segment"))
    assert run.usage.actual_cost_micros is None


def test_the_workflow_settles_segmentation_at_its_instance_time(tmp_path, monkeypatch):
    from test_lane_costs import TokenAdapters, lab, ledger_total

    kept = TokenAdapters.segment

    def segment(self, specimen):
        import hashlib

        regions = kept(self, specimen)
        raw = b'{"regions": []}'
        specimen.run.segmentation = {
            "blob_ref": self.blobs.put(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "input_sha256": specimen.asset.sha256,
            "elapsed_seconds": 53.1,
            "instance": LATER,
        }
        return regions

    monkeypatch.setattr(TokenAdapters, "segment", segment)
    app, principal, row = lab(tmp_path)
    run = app.state.workflow.drain(principal, row["specimen_id"]).run
    assert "parse" in run.completed_steps, run.blocker
    [call] = [c for c in run.paid_calls if c["step"] == "segment"]
    # The lab's price list names no instance rates: its request-based ones
    # (4 x 24 + 8 x 2.5 = 116 a second, plus 0.4 a request), 171.034 s.
    assert (call["cost_basis"], call["cost_micros"]) == ("computed", 19_841)
    # Every call is known now, segmentation and the two readings (550, 900):
    # the run and the program ledger settle to what they cost.
    assert run.usage.actual_cost_micros == 19_841 + 550 + 900
    assert run.usage.reserved_cost_micros == run.usage.actual_cost_micros
    assert ledger_total(app) == run.usage.actual_cost_micros
    assert datetime.fromisoformat(call["at"]) <= datetime.now(timezone.utc)
