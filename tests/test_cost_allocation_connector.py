"""The allocation's connector operations through SqlConnectRepository and FakeDataConnect.

FakeDataConnect (tests/research_harness/production_e2e_support.py) answers
CostAllocationInputsV1, UpsertCostAllocationsV1 and CostAllocationStatusV1 with the
checks dataconnect/connector/cost_allocation.gql makes; scripts/data/cost-allocation-test.mjs
runs the real SQL against PostgreSQL and the SQL Connect emulator.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path

import pytest

from specimen_digitization.application.cost_allocation import (
    Usage, allocate_day, day_bounds, day_hours, tenants,
)
from specimen_digitization.application.cost_ledger import cost_report
from specimen_digitization.application.domain import Asset, Principal, Scope, Specimen
from specimen_digitization.application.lane_costs import record_segmentation
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.storage import Conflict, LocalBlobs

from test_lane_costs import priced_run

sys.path.insert(0, str(Path(__file__).resolve().parent / "research_harness"))
import production_e2e_support as support  # noqa: E402

SCOPE = Scope(organization_id=support.ORG, collection_id=support.COLLECTION)
ADMIN = "cost-admin"
VIEWER = "cost-viewer"
UTC = timezone.utc


def fake():
    member = lambda role: [{"organization_id": support.ORG, "collection_id": support.COLLECTION,  # noqa: E731
                            "role": role, "can_view_sensitive": False}]
    return support.FakeDataConnect(None, members={support.WORKER: member("operator"), ADMIN: member("admin"),
                                                  VIEWER: member("viewer")})


def repository(tmp_path, session, uid=support.WORKER):
    actor_uid.set(uid)
    repo = SqlConnectRepository(session=session, graph_blobs=LocalBlobs(tmp_path / "blobs"))
    repo.pause = lambda seconds: None
    return repo


def specimen(n):
    run = priced_run()
    record_segmentation(run, "segment", seconds=12, instance={"first": False, "idle_seconds": 2.0, "request_seconds": 7.5})
    asset = Asset(sensitive=False, sha256=f"{n:064x}", blob_ref="blob", media_type="image/png", size_bytes=1,
                  width=1, height=1, filename="label.png", uploader=support.WORKER)
    return Specimen(id=f"00000000-0000-4000-8000-{n:012x}", scope=SCOPE, asset=asset, run=run)


def window(now):
    """The billing day holding ``now`` and its month's start."""
    day = (now - timedelta(hours=7)).date()
    start, end = day_bounds(day)
    return day, start, end, day_bounds(day.replace(day=1))[0]


def test_the_inputs_count_saves_the_worker_s_time_sam_3_calls_assets_and_specimens(tmp_path):
    session = fake()
    repo = repository(tmp_path, session)
    for n in (1, 2):
        repo.create(Principal(user_id=support.WORKER, scope=SCOPE, role="operator"), specimen(n), f"create-{n}", f"r-{n}")
    now = datetime.now(UTC)
    day, start, end, first = window(now)
    [measures] = tenants(repo.cost_allocation_inputs(SCOPE, start, end, first, 900))
    assert (measures.organization_id, measures.collection_id) == (support.ORG, support.COLLECTION)
    assert (measures.saves, measures.month_saves, measures.specimens) == (2, 2, 2)
    # The first save counts the cap (no save before it); the second the gap since the first.
    assert D(900) <= measures.worker_seconds < D(901)
    # Each create's SAM 3 call: its request seconds and its direct charge.
    assert measures.sam_seconds == D("15.0")
    calls = [entry["row"] for entry in session.cost_entries.values() if entry["row"]["resource"] == "sam3"]
    assert measures.sam_direct_micros == sum(row["cost_micros"] for row in calls) > 0
    assert measures.asset_bytes == sum(int(row["byteSize"] or 0) for row in session.tables["source_asset"].values())
    # A window before anything was saved counts nothing but what was held by then.
    early = tenants(repo.cost_allocation_inputs(SCOPE, start - timedelta(days=40), start - timedelta(days=39),
                                                start - timedelta(days=40), 900))
    assert early[0].saves == early[0].specimens == 0


def test_only_an_operator_or_above_reads_the_inputs(tmp_path):
    session = fake()
    now = datetime.now(UTC)
    _, start, end, first = window(now)
    with pytest.raises(Conflict):
        repository(tmp_path, session, VIEWER).cost_allocation_inputs(SCOPE, start, end, first, 900)
    with pytest.raises(Conflict):
        repository(tmp_path, session).cost_allocation_inputs(SCOPE, start, end, first, 0)


def rows_for(day, measures):
    readings = Usage(start=day_bounds(day.replace(day=1))[0], end=day_bounds(day)[1],
                     services={"specimen-sam": {day_hours(day)[0]: D(100)}})
    return allocate_day(day, measures, readings, job=None, bucket=None)


def test_allocation_rows_are_upserted_idempotently_and_any_malformed_row_refuses_the_call(tmp_path):
    session = fake()
    repo = repository(tmp_path, session)
    day = date(2026, 10, 19)
    measures = tenants([{"organization_id": support.ORG, "collection_id": support.COLLECTION, "sam_seconds": "10",
                         "specimens": "3"}])
    rows = rows_for(day, measures)
    assert {row["allocation_method_id"] for row in rows} == {"sam-residual", "free-allowance", "database-specimens"}
    assert repo.send_cost_allocations(SCOPE, rows) == len(rows)
    stored = {key: dict(entry) for key, entry in session.cost_entries.items()}
    assert repo.send_cost_allocations(SCOPE, rows) == len(rows)
    assert session.cost_entries == stored, "an identical resend keeps every value and updatedAt"
    bad = [
        {**rows[0], "id": rows[1]["id"]},                                   # not its derived id
        {**rows[0], "occurred_at": "2026-10-19T00:00:00+00:00"},            # not the Pacific day's start
        {**rows[0], "allocation_method_id": "guess"},
        {**rows[0], "specimen_id": "00000000-0000-4000-8000-000000000001"},
        {**rows[0], "collection_id": "00000000-0000-4000-8000-0000000000ff"},
        {**rows[-1], "cost_micros": -1, "list_cost_micros": -1},            # only a residual or a credit is negative
        {**next(row for row in rows if row["allocation_method_id"] == "free-allowance"), "list_cost_micros": 5},
        {**rows[0], "cost_micros": 1.5},
        {**rows[0], "month": "2026-11"},
    ]
    for row in bad:
        with pytest.raises(Conflict):
            repo.send_cost_allocations(SCOPE, [rows[1], row])
    assert session.cost_entries == stored, "a refused call writes nothing"
    with pytest.raises(Conflict):
        repository(tmp_path, session, VIEWER).send_cost_allocations(SCOPE, rows)


def test_the_status_names_the_latest_allocated_day_for_an_administrator_and_totals_take_credits(tmp_path):
    session = fake()
    admin = repository(tmp_path, session, ADMIN)
    assert admin.cost_allocation_status(support.ORG) == {"latest_occurred_at": None}
    worker = repository(tmp_path, session)
    measures = tenants([{"organization_id": support.ORG, "collection_id": support.COLLECTION, "sam_seconds": "10"}])
    for day in (date(2026, 10, 18), date(2026, 10, 19)):
        worker.send_cost_allocations(SCOPE, rows_for(day, measures))
    admin = repository(tmp_path, session, ADMIN)
    assert admin.cost_allocation_status(support.ORG) == {"latest_occurred_at": "2026-10-19T07:00:00Z"}
    with pytest.raises(Conflict):
        repository(tmp_path, session).cost_allocation_status(support.ORG)
    # The organization's totals: each day's SAM 3 residual (100 s x 104 = 10,400) less its full
    # credit, and the database's 328,603 (no specimen anywhere: the one collection takes it).
    admin = repository(tmp_path, session, ADMIN)
    read = admin.cost_totals(support.ORG, "2026-10", "2026-10")
    body = cost_report(support.ORG, "2026-10", "2026-10", read["collections"], read["groups"])
    assert body["totals"] == {"cost_micros": 657_206, "held_micros": 0, "list_cost_micros": 678_006, "entries": 6}
    assert body["months"][0]["stages"] == [
        {"stage": "database", "cost_micros": 657_206, "held_micros": 0, "list_cost_micros": 657_206, "entries": 2},
        {"stage": "label_finding", "cost_micros": 0, "held_micros": 0, "list_cost_micros": 20_800, "entries": 4}]
    assert body["models"] == []  # allocation rows are not a model's
