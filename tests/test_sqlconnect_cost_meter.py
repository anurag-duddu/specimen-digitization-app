"""Opt-in: the cost meter's Python writer, sweep and totals through the real connector.

Start scripts/data/serve-local.sh on isolated ports, then set
SPECIMEN_TEST_SQL_EMULATOR=true and SPECIMEN_SQL_EMULATOR_HOST=127.0.0.1:PORT.
Synthetic metadata only; no images, models or cloud authentication.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import requests

from specimen_digitization.application.cost_ledger import cost_report, paid_call_rows
from specimen_digitization.application.cost_sweep import sweep
from specimen_digitization.application.domain import Asset, Principal, Scope, Specimen
from specimen_digitization.application.lane_costs import (
    record_model_usage, record_refused, record_reserved, record_segmentation,
)
from specimen_digitization.application.production import SqlConnectRepository, actor_uid, sql_emulator_host
from specimen_digitization.field_research.step import record_cost

from test_lane_costs import QWEN, priced_run

pytestmark = pytest.mark.skipif(
    os.getenv("SPECIMEN_TEST_SQL_EMULATOR") != "true",
    reason="Requires explicitly started isolated SQL Connect/PostgreSQL emulator",
)


def seed(scope):
    response = requests.post(
        "http://" + sql_emulator_host()
        + "/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service:executeGraphql",
        headers={"Authorization": "Bearer owner"},
        json={"query": f'''mutation @transaction {{
          organization_insert(data:{{id:"{scope.organization_id}",name:"Synthetic cost meter"}})
          collection_insert(data:{{organizationId:"{scope.organization_id}",id:"{scope.collection_id}",name:"Synthetic insects"}})
          w: organizationMember_insert(data:{{organizationId:"{scope.organization_id}",uid:"cost-worker",active:true}})
          a: organizationMember_insert(data:{{organizationId:"{scope.organization_id}",uid:"cost-admin",active:true}})
          wc: collectionMember_insert(data:{{organizationId:"{scope.organization_id}",collectionId:"{scope.collection_id}",uid:"cost-worker",active:true,role:"operator",canViewSensitive:false}})
          ac: collectionMember_insert(data:{{organizationId:"{scope.organization_id}",collectionId:"{scope.collection_id}",uid:"cost-admin",active:true,role:"admin",canViewSensitive:false}})
        }}'''},
        timeout=10,
    ).json()
    assert not response.get("errors") and not response.get("code"), response


def test_saved_calls_are_metered_swept_back_unchanged_and_totalled(caplog):
    scope = Scope(organization_id=str(uuid4()), collection_id=str(uuid4()))
    seed(scope)
    run = priced_run()
    run.attempts[QWEN] = 1
    record_model_usage(run, QWEN, "handwriting-qwen", input_tokens=1_000, output_tokens=500)
    record_segmentation(run, "segment", seconds=25.2, instance={"first": True, "idle_seconds": 3.5,
                                                                "request_seconds": 12.25})
    record_refused(run, "first_pass:region-1", "model", route_id="first-pass-glm", failure_code="provider_refused")
    record_reserved(run, QWEN, "model", outcome="unknown", route_id="handwriting-qwen", failure_code="model_timeout")
    record_cost(run, "harness-deepseek", reserved=900_000, spent=1_250, outcome="completed", model_calls=25)
    specimen = Specimen(scope=scope, run=run, asset=Asset(
        sensitive=False, sha256=uuid4().hex * 2, blob_ref="fixture-blob", media_type="image/png",
        size_bytes=1, width=1, height=1, filename="label.png", uploader="cost-worker"))
    token = actor_uid.set("cost-worker")
    try:
        worker = SqlConnectRepository(project="demo-specimen-data", emulator_host=sql_emulator_host())
        with caplog.at_level(logging.WARNING):
            saved = worker.create(Principal(user_id="cost-worker", scope=scope, role="operator"),
                                  specimen, "cost-create", "cost-request")
        assert "Cost rows not written" not in caplog.text
        rows = paid_call_rows(scope.organization_id, scope.collection_id, saved.id, saved.run)
        assert len(rows) == 5 and worker._costed[saved.id] != {}
        # A fresh process (nothing remembered) sweeps the record back from its stored
        # snapshot: the same rows, through the snapshot's transport.
        fresh = SqlConnectRepository(project="demo-specimen-data", emulator_host=sql_emulator_host())
        page = fresh.run_paid_calls_page(scope, "", "1970-01-01T00:00:00Z", 25)
        assert [item["run_id"] for item in page["items"]] == [run.id]
        result = sweep(fresh, scope, clock=lambda: datetime.now(timezone.utc))
        assert result["status"] == "complete" and result["rows"] == 5 and result["skipped"] == 0
    finally:
        actor_uid.reset(token)
    token = actor_uid.set("cost-admin")
    try:
        admin = SqlConnectRepository(project="demo-specimen-data", emulator_host=sql_emulator_host())
        month = rows[0]["month"]
        read = admin.cost_totals(scope.organization_id, month, month)
    finally:
        actor_uid.reset(token)
    body = cost_report(scope.organization_id, month, month, read["collections"], read["groups"])
    held = sum(row["cost_micros"] for row in rows if row["cost_basis"] == "reserved")
    assert body["totals"] == {"cost_micros": sum(row["cost_micros"] for row in rows), "held_micros": held,
                              "list_cost_micros": sum(row["cost_micros"] for row in rows), "entries": 5}
    assert held == rows[3]["reserved_micros"] > 0
    [insects] = body["collections"]
    assert (insects["collection_id"], insects["name"], insects["total"]) == (
        scope.collection_id, "Synthetic insects", body["totals"])
    assert {(item["stage"], item["resource"]) for item in body["models"]} == {
        ("reading", "handwriting-qwen"), ("label_finding", "sam3"), ("first_pass", "first-pass-glm"),
        ("field_research", "harness-deepseek")}
