"""Opt-in: the cost meter's allocation job through the real connector (COST_METER.md, PR 3).

Start scripts/data/serve-local.sh on isolated ports, then set
SPECIMEN_TEST_SQL_EMULATOR=true and SPECIMEN_SQL_EMULATOR_HOST=127.0.0.1:PORT.
Synthetic metadata only; Cloud Monitoring is a stand-in, no cloud authentication.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from specimen_digitization.application.cost_allocation import day_bounds, day_hours, latest_complete_day, meter
from specimen_digitization.application.cost_allocator import CostAllocator, cursor_id
from specimen_digitization.application.cost_ledger import cost_report
from specimen_digitization.application.domain import Asset, Principal, Scope, Specimen
from specimen_digitization.application.lane_costs import record_segmentation
from specimen_digitization.application.production import SqlConnectRepository, actor_uid, sql_emulator_host

from test_lane_costs import priced_run
from test_sqlconnect_cost_meter import seed

pytestmark = pytest.mark.skipif(
    os.getenv("SPECIMEN_TEST_SQL_EMULATOR") != "true",
    reason="Requires explicitly started isolated SQL Connect/PostgreSQL emulator",
)


class Monitoring:
    """Every hour of the day before yesterday: 60 s of SAM 3 and 120 s of the worker job."""

    def __init__(self, day):
        self.day = day

    def series(self, metric_filter, start, end, aligner, *, stop_at=None):
        points = [{"interval": {"endTime": (hour + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")},
                   "value": {"doubleValue": 60 if "service_name" in metric_filter else 120}}
                  for hour in day_hours(self.day)]
        if 'resource.type="cloud_run_job"' in metric_filter:
            return [{"resource": {"labels": {"job_name": "specimen-worker"}}, "points": points}]
        if "billable_instance_time" in metric_filter:
            return [{"resource": {"labels": {"service_name": "specimen-sam"}}, "points": points}]
        return []


def test_the_worker_allocates_its_collection_s_day_and_the_administrator_sees_it():
    scope = Scope(organization_id=str(uuid4()), collection_id=str(uuid4()))
    seed(scope)
    now = datetime.now(timezone.utc)
    day = latest_complete_day(now) - timedelta(days=1)
    token = actor_uid.set("cost-worker")
    try:
        worker = SqlConnectRepository(project="demo-specimen-data", emulator_host=sql_emulator_host())
        run = priced_run()
        record_segmentation(run, "segment", seconds=8, instance={"first": False, "idle_seconds": 1.0,
                                                                  "request_seconds": 6.0})
        run.paid_calls[-1]["at"] = (day_bounds(day)[0] + timedelta(hours=2)).isoformat()
        specimen = Specimen(scope=scope, run=run, asset=Asset(
            sensitive=False, sha256=uuid4().hex * 2, blob_ref="fixture-blob", media_type="image/png",
            size_bytes=1, width=1, height=1, filename="label.png", uploader="cost-worker"))
        worker.create(Principal(user_id="cost-worker", scope=scope, role="operator"), specimen, "alloc-create", "r")
        # The cursor starts at the day before, so this pass allocates exactly ``day``.
        worker.put_document(scope, "worker_cursor", cursor_id(scope),
                            {"sensitive": False, "allocated_through": (day - timedelta(days=1)).isoformat()}, 0)
        allocator = CostAllocator(Monitoring(day), job="specimen-worker", bucket=None, days=1)
        result = allocator.run(worker, scope, job_collections=[(scope.organization_id, scope.collection_id)])
        assert result["status"] in {"complete", "partial"} and result["days"] == 1, result
        assert result["through"] == day.isoformat() and result["rows"] > 0
    finally:
        actor_uid.reset(token)
    token = actor_uid.set("cost-admin")
    try:
        admin = SqlConnectRepository(project="demo-specimen-data", emulator_host=sql_emulator_host())
        status = admin.cost_allocation_status(scope.organization_id)
        month = day_bounds(day)[0].strftime("%Y-%m")
        read = admin.cost_totals(scope.organization_id, month, month)
    finally:
        actor_uid.reset(token)
    assert meter(status["latest_occurred_at"], now)["allocated_through"] == day.isoformat()
    body = cost_report(scope.organization_id, month, month, read["collections"], read["groups"])
    stages = {item["stage"] for item in body["months"][0]["stages"]}
    # No specimen of this collection was held at the day's end (it was saved later): no database share.
    assert {"worker", "label_finding"} <= stages and "database" not in stages
