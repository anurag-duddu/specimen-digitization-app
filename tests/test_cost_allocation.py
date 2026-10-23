"""The cost meter's split of shared Google costs (docs/execution/golive/COST_METER.md, PR 3).

Every expected amount below is worked out by hand from the committed price file:
instance-based Cloud Run 18 and 2 micro-USD per vCPU- and GiB-second, request-based
24 and 2.5 plus 0.4 per request, Standard storage 23,000 per GiB-month in us-east4
over 730 hours, and db-f1-micro 11,200 per hour plus 10 GiB of SSD at 181,900 per
GiB-month.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path

import pytest

from specimen_digitization.application import cost_allocation as ca
from specimen_digitization.application.cost_allocation import (
    BILLING_ZONE, FIRST_DAY, Tenant, Usage, allocate_day, allowance, day_bounds, day_hours, due_days,
    latest_complete_day, meter, split, tenants,
)
from specimen_digitization.application.projection import derived_id

ROOT = Path(__file__).resolve().parents[1]
ORG_A = "00000000-0000-4000-8000-0000000000a1"
ORG_B = "00000000-0000-4000-8000-0000000000a2"
PARENT = "00000000-0000-4000-8000-0000000000b1"  # Insects, in A
CHILD = "00000000-0000-4000-8000-0000000000b2"   # Beetles, under Insects, in A
OTHER = "00000000-0000-4000-8000-0000000000b3"   # Fishes, in B
DAY = date(2026, 10, 19)
JOB = "specimen-worker"
BUCKET = "specimen-digitization.firebasestorage.app"
UTC = timezone.utc


def at(day, hour):
    """The UTC start of the billing day's hour number ``hour``."""
    return day_hours(day)[hour]


def usage(day=DAY, *, sam=None, api=None, requests=None, jobs=None, orgs=None, storage=None,
          location="us-east4", start=None):
    """Monitoring readings: each argument maps an hour number of ``day`` to its value."""
    hours = lambda values: {at(day, hour): D(value) for hour, value in (values or {}).items()}  # noqa: E731
    return Usage(start=start or day_bounds(day.replace(day=1))[0], end=day_bounds(day)[1],
                 services={"specimen-sam": hours(sam), "specimen-api": hours(api)},
                 jobs={name: hours(values) for name, values in (jobs or {}).items()},
                 requests=hours(requests), organizations={org: hours(values) for org, values in (orgs or {}).items()},
                 storage=hours(storage), storage_location=location, storage_metric="v2")


def rows_of(rows, method, resource=None):
    return {row["collection_id"]: row["cost_micros"] for row in rows
            if row["allocation_method_id"] == method and (resource is None or row["resource"] == resource)}


def credits_of(rows, resource):
    return rows_of(rows, "free-allowance", resource)


TENANTS = [Tenant(ORG_A, PARENT), Tenant(ORG_A, CHILD), Tenant(ORG_B, OTHER)]


# ---- billing days -------------------------------------------------------------

def test_a_billing_day_is_a_pacific_calendar_day_in_utc_hours():
    assert BILLING_ZONE == "America/Los_Angeles"
    assert day_bounds(DAY) == (datetime(2026, 10, 19, 7, tzinfo=UTC), datetime(2026, 10, 20, 7, tzinfo=UTC))
    assert len(day_hours(DAY)) == 24
    # Daylight saving ends on 2026-11-01 (25 hours) and starts on 2027-03-14 (23 hours).
    assert day_bounds(date(2026, 11, 1)) == (datetime(2026, 11, 1, 7, tzinfo=UTC), datetime(2026, 11, 2, 8, tzinfo=UTC))
    assert len(day_hours(date(2026, 11, 1))) == 25
    assert day_bounds(date(2027, 3, 14)) == (datetime(2027, 3, 14, 8, tzinfo=UTC), datetime(2027, 3, 15, 7, tzinfo=UTC))
    assert len(day_hours(date(2027, 3, 14))) == 23


def test_due_days_start_on_the_first_day_wait_three_hours_and_are_bounded():
    assert FIRST_DAY == date(2026, 10, 1)
    end_of_day = day_bounds(date(2026, 10, 3))[1]  # 2026-10-04T07:00Z
    assert due_days(None, end_of_day + timedelta(hours=3), 10) == [date(2026, 10, 1), date(2026, 10, 2),
                                                                    date(2026, 10, 3)]
    assert due_days(None, end_of_day + timedelta(hours=2, minutes=59), 10)[-1] == date(2026, 10, 2)
    assert due_days(None, end_of_day + timedelta(hours=3), 2) == [date(2026, 10, 1), date(2026, 10, 2)]
    assert due_days(date(2026, 10, 2), end_of_day + timedelta(hours=3), 7) == [date(2026, 10, 3)]
    assert due_days(date(2026, 10, 3), end_of_day + timedelta(hours=3), 7) == []
    assert due_days(date(2026, 9, 1), end_of_day + timedelta(hours=3), 1) == [FIRST_DAY]
    assert latest_complete_day(end_of_day + timedelta(hours=3)) == date(2026, 10, 3)


def test_rows_occur_at_the_day_s_start_so_their_utc_month_is_the_pacific_month():
    for day, month in ((date(2026, 10, 31), "2026-10"), (date(2026, 11, 1), "2026-11"), (date(2026, 11, 30), "2026-11")):
        rows = allocate_day(day, TENANTS, usage(day), job=None, bucket=None)
        assert {row["occurred_at"] for row in rows} == {day_bounds(day)[0].isoformat()}
        assert {row["month"] for row in rows} == {month}


# ---- arithmetic ------------------------------------------------------------------

def test_split_keeps_the_total_exactly_and_gives_remainders_to_the_largest_then_by_key():
    assert split(10, {"a": D(1), "b": D(1), "c": D(1)}) == {"a": 4, "b": 3, "c": 3}
    assert split(-10, {"a": D(1), "b": D(1), "c": D(1)}) == {"a": -4, "b": -3, "c": -3}
    assert split(100, {"a": D(2), "b": D(1)}) == {"a": 67, "b": 33}
    assert split(7, {"a": D(0), "b": D(3)}) == {"b": 7}
    assert split(0, {"a": D(1)}) == {} and split(5, {}) == {} and split(5, {"a": D(0)}) == {}
    assert split(1, {"a": D(1), "b": D(1)}) == {"a": 1}  # a zero part is left out


# ---- 1. the worker job ---------------------------------------------------------

def test_the_worker_job_is_split_by_each_collection_s_processing_time():
    collections = [Tenant(ORG_A, PARENT, worker_seconds=D("600.5")), Tenant(ORG_A, CHILD, worker_seconds=D("199.5")),
                   Tenant(ORG_B, OTHER)]
    rows = allocate_day(DAY, collections, usage(jobs={JOB: {3: 700, 4: 300}}), job=JOB,
                        job_collections=[(ORG_A, PARENT), (ORG_A, CHILD)], bucket=None)
    # 1,000 billable seconds at 1 vCPU and 1 GiB: 1,000 x (18 + 2) = 20,000; 600.5 : 199.5 of 800.
    assert rows_of(rows, "worker-processing-time") == {PARENT: 15_013, CHILD: 4_987}
    [row] = [row for row in rows if row["allocation_method_id"] == "worker-processing-time"
             and row["collection_id"] == PARENT]
    details = row["allocation_method_details"]
    assert (row["resource"], row["stage"], row["step"]) == (JOB, "worker", "allocation:" + JOB)
    assert details["share"] == {"measure": details["share"]["measure"], "basis": "day", "numerator": "600.5",
                                "denominator": "800"}
    assert details["hourly_seconds"][3:5] == ["700", "300"] and len(details["hourly_seconds"]) == 24
    assert (details["time_zone"], details["billing_day"], details["billable_seconds"]) == (BILLING_ZONE, "2026-10-19",
                                                                                           "1000")
    assert row["usage"] == {"processing_seconds": 600.5}
    # Another job's time is never this job's to split.
    other = allocate_day(DAY, collections, usage(jobs={"specimen-worker-fishes": {3: 1000}}), job=JOB,
                         job_collections=[(ORG_A, PARENT)], bucket=None)
    assert rows_of(other, "worker-processing-time") == {}


def test_a_day_without_the_job_s_saves_falls_back_to_the_month_then_to_its_collections_evenly():
    month = [Tenant(ORG_A, PARENT, month_worker_seconds=D(300)), Tenant(ORG_A, CHILD, month_worker_seconds=D(100)),
             Tenant(ORG_B, OTHER)]
    rows = allocate_day(DAY, month, usage(jobs={JOB: {0: 61}}), job=JOB,
                        job_collections=[(ORG_A, PARENT), (ORG_A, CHILD)], bucket=None)
    # 61 s x 20 = 1,220, as the month's 300 : 100.
    assert rows_of(rows, "worker-processing-time") == {PARENT: 915, CHILD: 305}
    assert {row["allocation_method_details"]["share"]["basis"] for row in rows
            if row["allocation_method_id"] == "worker-processing-time"} == {"month"}
    rows = allocate_day(DAY, TENANTS, usage(jobs={JOB: {0: 61}}), job=JOB,
                        job_collections=[(ORG_A, PARENT), (ORG_A, CHILD)], bucket=None)
    assert rows_of(rows, "worker-processing-time") == {PARENT: 610, CHILD: 610}
    assert "split evenly over its collections" in rows[0]["allocation_method_details"]["note"]


# ---- 2. SAM 3's residual -------------------------------------------------------

def test_sam_3_pays_only_its_residual_split_by_request_seconds():
    collections = [Tenant(ORG_A, PARENT, sam_seconds=D(30), sam_direct_micros=20_000),
                   Tenant(ORG_A, CHILD, sam_seconds=D(10), sam_direct_micros=8_000), Tenant(ORG_B, OTHER)]
    rows = allocate_day(DAY, collections, usage(sam={5: 500}), job=None, bucket=None)
    # 500 s x (4 x 18 + 16 x 2) = 52,000, less 28,000 already charged per request: 24,000 as 30 : 10.
    assert rows_of(rows, "sam-residual") == {PARENT: 18_000, CHILD: 6_000}
    details = next(row for row in rows if row["allocation_method_id"] == "sam-residual")["allocation_method_details"]
    assert (details["list_micros"], details["direct_micros"], details["allocated_micros"]) == ("52000", 28_000, 24_000)


def test_a_negative_sam_residual_is_written_as_it_is():
    collections = [Tenant(ORG_A, PARENT, sam_seconds=D(30), sam_direct_micros=2_000),
                   Tenant(ORG_A, CHILD, sam_seconds=D(10), sam_direct_micros=1_000), Tenant(ORG_B, OTHER)]
    rows = allocate_day(DAY, collections, usage(sam={5: 10}), job=None, bucket=None)
    # 10 s x 104 = 1,040 measured, 3,000 charged: -1,960 as 30 : 10.
    assert rows_of(rows, "sam-residual") == {PARENT: -1_470, CHILD: -490}
    assert all(row["cost_micros"] == row["list_cost_micros"] for row in rows if row["allocation_method_id"] == "sam-residual")
    assert "negative when the per-request charges came to more" in rows[0]["allocation_method_details"]["note"]


# ---- 3. the API ----------------------------------------------------------------

def test_the_api_is_split_by_organization_requests_then_by_each_collection_s_saves():
    collections = [Tenant(ORG_A, PARENT, saves=3), Tenant(ORG_A, CHILD, saves=1), Tenant(ORG_B, OTHER, saves=50)]
    rows = allocate_day(DAY, collections, usage(api={2: 100}, requests={2: 1_000}, orgs={ORG_A: {2: 750}, ORG_B: {2: 250}}),
                        job=None, bucket=None)
    # 100 s x 26.5 + 1,000 x 0.4 = 3,050; 750 : 250 gives A 2,287.5 (2,288) and B 762.5 (762);
    # A's 2,288 by saves 3 : 1.
    assert rows_of(rows, "api-requests") == {PARENT: 1_716, CHILD: 572, OTHER: 762}
    share = next(row for row in rows if row["collection_id"] == PARENT
                 and row["allocation_method_id"] == "api-requests")["allocation_method_details"]["share"]
    assert share["organization"]["basis"] == "requests" and share["collection"]["basis"] == "day"


def test_without_request_counts_the_api_is_split_across_organizations_by_saves():
    collections = [Tenant(ORG_A, PARENT, saves=3), Tenant(ORG_A, CHILD, saves=1), Tenant(ORG_B, OTHER, saves=4)]
    rows = allocate_day(DAY, collections, usage(api={2: 100}, requests={2: 1_000}), job=None, bucket=None)
    # 3,050 as A 4 : B 4, then A's 1,525 as 3 : 1.
    assert rows_of(rows, "api-requests") == {PARENT: 1_144, CHILD: 381, OTHER: 1_525}
    share = next(row for row in rows if row["allocation_method_id"] == "api-requests")["allocation_method_details"]["share"]
    assert share["organization"]["basis"] == "day"


# ---- 4. storage and 5. the database ------------------------------------------

def test_storage_is_the_bucket_s_mean_bytes_split_by_source_asset_bytes():
    collections = [Tenant(ORG_A, PARENT, asset_bytes=3 * 2**30), Tenant(ORG_A, CHILD, asset_bytes=2**30),
                   Tenant(ORG_B, OTHER)]
    # 12 hours at 2 GiB and 12 at 4 GiB: a mean of 3 GiB x 23,000 x 24 / 730 = 2,268.49 micro-USD.
    rows = allocate_day(DAY, collections, usage(storage={0: 2 * 2**30, 12: 4 * 2**30}), job=None, bucket=BUCKET)
    assert rows_of(rows, "storage-bytes") == {PARENT: 1_701, CHILD: 567}
    details = next(row for row in rows if row["allocation_method_id"] == "storage-bytes")["allocation_method_details"]
    assert details["mean_bytes"] == str(3 * 2**30) and details["location"] == "us-east4"
    # A bucket with no object has no series: no storage row.
    assert rows_of(allocate_day(DAY, collections, usage(), job=None, bucket=BUCKET), "storage-bytes") == {}
    with pytest.raises(ValueError, match="cost_allocation_storage_location_unpriced"):
        allocate_day(DAY, collections, usage(storage={0: 2**30}, location="asia-south2"), job=None, bucket=BUCKET)


def test_the_database_is_its_daily_list_price_split_by_specimens_held():
    collections = [Tenant(ORG_A, PARENT, specimens=3), Tenant(ORG_A, CHILD, specimens=1), Tenant(ORG_B, OTHER)]
    rows = allocate_day(DAY, collections, usage(), job=None, bucket=None)
    # 24 x (11,200 + 10 x 181,900 / 730) = 328,602.74, so 328,603 as 3 : 1.
    assert rows_of(rows, "database-specimens") == {PARENT: 246_452, CHILD: 82_151}
    assert "no-cost trial may make the bill zero" in rows[0]["allocation_method_details"]["note"]
    # With no specimen anywhere, evenly over every collection of the deployment.
    assert rows_of(allocate_day(DAY, TENANTS, usage(), job=None, bucket=None), "database-specimens") == {
        PARENT: 109_535, CHILD: 109_534, OTHER: 109_534}


@pytest.mark.parametrize("day,hours", [(date(2026, 11, 1), 25), (date(2027, 3, 14), 23)])
def test_a_daylight_saving_day_is_its_own_hours(day, hours):
    collections = [Tenant(ORG_A, PARENT, specimens=1, asset_bytes=1, sam_seconds=D(1))]
    readings = usage(day, sam={hours - 1: 100}, storage={0: 2**30})
    rows = allocate_day(day, collections, readings, job=None, bucket=BUCKET)
    per_hour = D(11_200) + D(10) * D(181_900) / D(730)
    assert rows_of(rows, "database-specimens") == {PARENT: ca.whole(per_hour * hours)}
    # 1 GiB x 23,000 x hours / 730.
    assert rows_of(rows, "storage-bytes") == {PARENT: ca.whole(D(23_000) * hours / D(730))}
    details = next(row for row in rows if row["allocation_method_id"] == "sam-residual")["allocation_method_details"]
    assert details["hours"] == hours and len(details["hourly_seconds"]) == hours
    assert details["hourly_seconds"][-1] == "100"  # the last hour of the day is read, not dropped


# ---- 6. the free allowance -----------------------------------------------------

def test_the_free_allowance_is_drawn_day_by_day_and_crosses_exhaustion_mid_month():
    # SAM 3 runs 10,000 s every day: 40,000 vCPU-s and 160,000 GiB-s of the instance-based
    # pool's 240,000 and 450,000.
    days = [date(2026, 10, n) for n in range(1, 8)]
    readings = Usage(start=day_bounds(days[0])[0], end=day_bounds(days[-1])[1],
                     services={"specimen-sam": {day_hours(day)[0]: D(10_000) for day in days}})
    table = ca.prices()
    expected = {
        1: 40_000 * 18 + 160_000 * 2,   # 1,040,000: the whole day
        2: 40_000 * 18 + 160_000 * 2,
        3: 40_000 * 18 + 130_000 * 2,   # memory runs out: 130,000 GiB-s were left
        4: 40_000 * 18,                 # vCPU only
        5: 40_000 * 18,
        6: 40_000 * 18,                 # the last 40,000 vCPU-s
        7: 0,
    }
    for day in days:
        credits, pools = allowance(day, readings, table)
        assert ca.whole(credits.get("specimen-sam", D(0))) == expected[day.day], day
    _, pools = allowance(date(2026, 10, 3), readings, table)
    assert pools["instance_based"]["gib_seconds"] == {"remaining_before": "130000", "drawn": "160000",
                                                      "consumed": "130000", "remaining_after": "0"}
    # A new invoice month starts with full pools.
    november = Usage(start=day_bounds(date(2026, 11, 1))[0], end=day_bounds(date(2026, 11, 1))[1],
                     services={"specimen-sam": {day_hours(date(2026, 11, 1))[0]: D(10_000)}})
    assert ca.whole(allowance(date(2026, 11, 1), november, table)[0]["specimen-sam"]) == 1_040_000


def test_jobs_share_the_instance_pool_with_sam_3_in_proportion_to_what_each_drew():
    days = [date(2026, 10, 1), date(2026, 10, 2)]
    readings = Usage(start=day_bounds(days[0])[0], end=day_bounds(days[-1])[1],
                     services={"specimen-sam": {day_hours(days[0])[0]: D(26_250), day_hours(days[1])[0]: D(1_000)}},
                     jobs={JOB: {day_hours(days[1])[0]: D(4_000)}})
    # Day 1 leaves 450,000 - 420,000 = 30,000 GiB-s and 240,000 - 105,000 = 135,000 vCPU-s.
    # Day 2 draws 16,000 (SAM) + 4,000 (job) = 20,000 GiB-s and 4,000 + 4,000 vCPU-s: all fit.
    credits, _ = allowance(days[1], readings, ca.prices())
    assert ca.whole(credits["specimen-sam"]) == 4_000 * 18 + 16_000 * 2
    assert ca.whole(credits["job:" + JOB]) == 4_000 * 18 + 4_000 * 2
    # With the job at 34,000 s the day draws 50,000 GiB-s of 30,000 left: SAM 16/50, the job 34/50.
    readings.jobs[JOB][day_hours(days[1])[0]] = D(34_000)
    credits, _ = allowance(days[1], readings, ca.prices())
    assert ca.whole(credits["specimen-sam"]) == ca.whole(D(4_000) * 18 + D(30_000) * D(16_000) / D(50_000) * 2)
    assert ca.whole(credits["job:" + JOB]) == ca.whole(D(34_000) * 18 + D(30_000) * D(34_000) / D(50_000) * 2)


def test_credits_are_negative_rows_split_like_the_service_and_list_cost_is_before_the_allowance():
    collections = [Tenant(ORG_A, PARENT, sam_seconds=D(30), worker_seconds=D(3), saves=1),
                   Tenant(ORG_A, CHILD, sam_seconds=D(10), worker_seconds=D(1), saves=1), Tenant(ORG_B, OTHER)]
    rows = allocate_day(DAY, collections, usage(sam={0: 100}, api={0: 40}, requests={0: 100}, jobs={JOB: {0: 100}},
                                                orgs={ORG_A: {0: 100}}), job=JOB,
                        job_collections=[(ORG_A, PARENT), (ORG_A, CHILD)], bucket=None)
    # Nothing has drawn on the pools this month: every Cloud Run cost is credited in full.
    assert credits_of(rows, "specimen-sam") == {PARENT: -7_800, CHILD: -2_600}   # 10,400 as 30 : 10
    assert credits_of(rows, JOB) == {PARENT: -1_500, CHILD: -500}               # 2,000 as 3 : 1
    assert credits_of(rows, "specimen-api") == {PARENT: -550, CHILD: -550}      # 1,060 + 40 as 1 : 1
    for row in rows:
        if row["allocation_method_id"] == "free-allowance":
            assert row["list_cost_micros"] == 0 and row["cost_micros"] < 0 and row["stage"] in {"label_finding", "worker", "api"}
    cloud_run = [row for row in rows if row["resource"] in {"specimen-sam", JOB, "specimen-api"}]
    assert sum(row["cost_micros"] for row in cloud_run) == 0  # after the allowance
    assert sum(row["list_cost_micros"] for row in cloud_run) == 10_400 + 2_000 + 1_100  # before it


# ---- rows ----------------------------------------------------------------------

def test_every_row_has_its_derived_id_and_the_ledger_s_fixed_fields():
    collections = [Tenant(ORG_A, PARENT, specimens=1, saves=1)]
    rows = allocate_day(DAY, collections, usage(api={0: 10}), job=None, bucket=None)
    assert rows and json.loads(json.dumps(rows)) == rows
    for row in rows:
        assert row["id"] == derived_id("cost-allocation", "2026-10-19", row["resource"], row["collection_id"],
                                       row["allocation_method_id"])
        assert (row["source"], row["kind"], row["cost_basis"], row["provider"]) == (
            "allocation", "allocation", "allocated", "google_cloud")
        assert (row["specimen_id"], row["run_id"], row["attempt"], row["ordinal"], row["reserved_micros"]) == (
            None, None, 1, 0, None)
        assert row["step"] == "allocation:" + row["resource"] and row["billing_day"] == "2026-10-19"
        assert (row["price_list_version"], row["price_list_as_of"]) == ("infrastructure-prices-2026-10-20", "2026-10-20")
        assert row["allocation_method_details"]["time_zone"] == BILLING_ZONE


def test_the_same_inputs_give_the_same_rows():
    collections = [Tenant(ORG_A, PARENT, sam_seconds=D("1.25"), saves=2, specimens=4)]
    readings = usage(sam={1: "12.5"}, api={1: 3}, requests={1: 9})
    assert allocate_day(DAY, collections, readings, job=None, bucket=None) == allocate_day(
        DAY, list(collections), readings, job=None, bucket=None)


def test_readings_that_miss_the_month_s_start_are_refused():
    late = usage(start=day_bounds(DAY)[0])
    with pytest.raises(ValueError, match="cost_allocation_usage_incomplete"):
        allocate_day(DAY, TENANTS, late, job=None, bucket=None)


# ---- inputs and the meter ------------------------------------------------------

def test_the_connector_s_measures_are_read_exactly_and_anything_else_is_refused():
    [tenant] = tenants([{"organization_id": ORG_A.upper(), "collection_id": PARENT, "saves": "3", "month_saves": "9",
                         "worker_seconds": "12.500000", "month_worker_seconds": "40", "sam_seconds": "2.5",
                         "month_sam_seconds": "7.5", "sam_direct_micros": "1500", "asset_bytes": "1073741824",
                         "specimens": "2"}])
    assert tenant == Tenant(ORG_A, PARENT, 3, 9, D("12.5"), D(40), D("2.5"), D("7.5"), 1500, 2**30, 2)
    for bad in ({"saves": "-1"}, {"saves": "1.5"}, {"worker_seconds": "NaN"}, {"organization_id": "x"},
                {"specimens": True}):
        with pytest.raises(ca.AllocationInputsInvalid):
            tenants([{"organization_id": ORG_A, "collection_id": PARENT, **bad}])
    with pytest.raises(ca.AllocationInputsInvalid):
        tenants([{"organization_id": ORG_A, "collection_id": PARENT}] * 2)


def test_the_meter_reports_the_last_allocated_day_and_whether_it_lags():
    now = datetime(2026, 10, 20, 12, tzinfo=UTC)  # 05:00 in Los Angeles: the 19th ended 5 hours ago
    assert latest_complete_day(now) == date(2026, 10, 19)
    assert meter(None, now) == {"allocated_through": None, "allocation_status": "never_run"}
    assert meter("2026-10-19T07:00:00Z", now) == {"allocated_through": "2026-10-19", "allocation_status": "ok"}
    assert meter("2026-10-17T07:00:00Z", now) == {"allocated_through": "2026-10-17", "allocation_status": "ok"}
    assert meter("2026-10-16T07:00:00Z", now) == {"allocated_through": "2026-10-16", "allocation_status": "behind"}


def test_the_price_file_s_shapes_are_the_deployed_ones():
    spec = importlib.util.spec_from_file_location("runtime_settings_for_prices", ROOT / "scripts/ci/runtime_settings.py")
    settings = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(settings)
    run = ca.prices()["cloud_run"]
    gib = lambda value: int(value.removesuffix("Gi"))  # noqa: E731
    for role, shape in ((settings.SAM, run["services"]["specimen-sam"]), (settings.API, run["services"]["specimen-api"]),
                        (settings.WORKER, run["jobs"])):
        assert (int(role["cpu"]), gib(role["memory"])) == (shape["vcpus"], shape["memory_gib"])
    assert settings.SAM["cpu_idle"] is False and run["services"]["specimen-sam"]["billing"] == "instance_based"
    assert settings.REGION == ca.prices()["region"] and settings.BUCKET.endswith(".firebasestorage.app")
