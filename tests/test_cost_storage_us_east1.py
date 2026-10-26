"""The app bucket's location is priced, so the shared-cost split runs (COST_METER.md, method 4).

The app bucket is in US-EAST1 (a region; default class REGIONAL, which Google bills as
Standard). The price file named only us-east4 and the US multi-region, so on 2026-10-26 the
worker logged ``cost allocation stopped: cost_allocation_storage_location_unpriced`` and
allocated nothing: not storage, and not Cloud SQL, the API or the worker job either.
"""

from __future__ import annotations

import copy
import logging

import pytest

from specimen_digitization.application import cost_allocation as ca
from specimen_digitization.application.cost_allocation import Tenant, allocate_day

from test_cost_allocation import BUCKET, CHILD, DAY, ORG_A, ORG_B, OTHER, PARENT, rows_of, usage
from test_cost_allocator import SCOPE, SERVED, Monitoring, Repo, allocator

LOCATIONS = ["us-east1", "US-EAST1"]
GIB = 2**30


def storage_rows(repo):
    return [row for _, rows in repo.sent for row in rows if row["allocation_method_id"] == "storage-bytes"]


def test_the_price_file_names_us_east1_at_twenty_thousand_micro_usd_per_gib_month():
    rates = ca.prices()["cloud_storage"]["standard_micros_per_gib_month"]
    assert rates.get("us-east1") == 20_000
    # The two it already named are untouched.
    assert (rates["us-east4"], rates["us"]) == (23_000, 26_000)


@pytest.mark.parametrize("location", LOCATIONS)
def test_storage_in_us_east1_is_the_mean_bytes_at_the_us_east1_standard_rate(location):
    collections = [Tenant(ORG_A, PARENT, asset_bytes=3 * GIB), Tenant(ORG_A, CHILD, asset_bytes=GIB),
                   Tenant(ORG_B, OTHER)]
    # 12 hours at 2 GiB and 12 at 4 GiB: a mean of 3 GiB x 20,000 x 24 / 730 = 1,972.60 micro-USD,
    # so 1,973 as 3 : 1 (the spare micro-USD goes to the larger remainder, the parent's .75).
    rows = allocate_day(DAY, collections, usage(storage={0: 2 * GIB, 12: 4 * GIB}, location=location),
                        job=None, bucket=BUCKET)
    assert rows_of(rows, "storage-bytes") == {PARENT: 1_480, CHILD: 493}
    details = next(row for row in rows if row["allocation_method_id"] == "storage-bytes")["allocation_method_details"]
    assert details["location"] == "us-east1" and details["rate_micros_per_gib_month"] == 20_000
    assert details["mean_bytes"] == str(3 * GIB) and details["allocated_micros"] == 1_973


@pytest.mark.parametrize("location", LOCATIONS)
def test_a_pass_over_the_app_bucket_s_location_allocates_every_family_and_moves_the_cursor(location, caplog):
    repo = Repo()
    with caplog.at_level(logging.WARNING):
        result = allocator(Monitoring(location=location)).run(repo, SCOPE, swept=True, job_collections=SERVED)
    assert (result["status"], result["days"], result["through"]) == ("complete", 4, "2026-10-04")
    assert "cost allocation stopped" not in caplog.text
    assert repo.cursor()["allocated_through"] == "2026-10-04"
    methods = {row["allocation_method_id"] for _, rows in repo.sent for row in rows}
    # Storage, and the families the stop used to hold with it.
    assert {"storage-bytes", "database-specimens", "worker-processing-time", "sam-residual"} <= methods
    stored = storage_rows(repo)
    assert len(stored) == 4  # this collection's row on each of the four days
    for row in stored:
        assert row["allocation_method_details"]["location"] == "us-east1"
        assert row["allocation_method_details"]["rate_micros_per_gib_month"] == 20_000
        assert row["cost_micros"] > 0


def test_days_held_for_an_unpriced_location_are_allocated_in_full_once_the_file_names_it(caplog):
    # The price file as it stood on 2026-10-26: no us-east1.
    before = copy.deepcopy(ca.prices())
    before["cloud_storage"]["standard_micros_per_gib_month"].pop("us-east1", None)
    repo = Repo()
    with caplog.at_level(logging.WARNING):
        held = allocator(Monitoring(location="US-EAST1"), table=before).run(
            repo, SCOPE, swept=True, job_collections=SERVED)
    assert held["status"] == "failed" and repo.sent == [] and repo.cursor() is None
    assert "cost allocation stopped: cost_allocation_storage_location_unpriced" in caplog.text
    # The next pass, with the committed file, writes every day from the first.
    result = allocator(Monitoring(location="US-EAST1")).run(repo, SCOPE, swept=True, job_collections=SERVED)
    assert (result["status"], result["days"], result["through"]) == ("complete", 4, "2026-10-04")
    assert repo.days() == ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]
    assert len(storage_rows(repo)) == 4
