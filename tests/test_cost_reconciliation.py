"""The monthly check of the cost meter against the real bills (docs/execution/golive/COST_RECONCILIATION.md).

Every figure in these fixtures is worked out by hand in the comment beside it.
"""

from __future__ import annotations

import itertools
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from specimen_digitization.application import cost_reconciliation as cr
from specimen_digitization.application.cost_reconciliation import (
    BillingZone,
    ReconciliationInputError,
    Thresholds,
    check_billing_day,
    default_route_models,
    google_family,
    parse_google,
    parse_huggingface,
    parse_meter_rows,
    reconcile,
    render_markdown,
)
from specimen_digitization.model_gateway import HUGGINGFACE_ROUTES

ORG = "00000000-0000-4000-8000-0000000000a1"
COLLECTION = "00000000-0000-4000-8000-0000000000b2"
MONTH = "2026-10"
PROJECT = "specimen-digitization"
QWEN = HUGGINGFACE_ROUTES["handwriting-qwen"].model_id
MUSE = HUGGINGFACE_ROUTES["handwriting-muse"].model_id
GLM = HUGGINGFACE_ROUTES["first-pass-glm"].model_id
DEEPSEEK = HUGGINGFACE_ROUTES["harness-deepseek"].model_id
_ids = itertools.count(1)


def meter(provider, resource, cost, *, basis="computed", kind=None, source=None, stage="reading",
          when="2026-10-10T12:00:00Z", list_cost=None, method=None, **extra):
    """A CostEntry row as Data Connect returns it: camelCase, Int64 as text."""
    row = {
        "organizationId": ORG, "collectionId": COLLECTION, "id": f"00000000-0000-4000-8000-{next(_ids):012d}",
        "source": source or ("allocation" if method else "paid_call"),
        "kind": kind or ("model" if provider == "huggingface" else "allocation" if method else "service"),
        "stage": stage, "provider": provider, "resource": resource,
        "costMicros": str(cost), "listCostMicros": str(cost if list_cost is None else list_cost),
        "costBasis": basis, "occurredAt": when, "month": when[:7], "allocationMethodId": method,
        "priceListVersion": "2026-10-test", "priceListAsOf": "2026-10-01",
    }
    row.update(extra)
    return row


def hf(days):
    """{"2026-10-10": {model: (requests, nano_usd)}} as the normalized bill."""
    return {"days": {day: {model: {"requests": r, "nano_usd": n} for model, (r, n) in models.items()}
                     for day, models in days.items()}}


def codes(entry):
    return [item["code"] for item in entry["explanations"]]


def model(report, model_id):
    return next(e for e in report["huggingface"]["models"] if e["label"] == model_id)


def family(report, name):
    return next(f for f in report["google"]["families"] if f["family"] == name)


# ---- the route map and the meter rows ---------------------------------------

def test_route_models_come_from_the_registry_and_cover_every_published_route():
    mapping = default_route_models()
    assert mapping == {route_id: route.model_id for route_id, route in HUGGINGFACE_ROUTES.items()}
    published = json.loads((Path(cr.__file__).parent / "profiles" / "published.json").read_text())
    named = set()

    def walk(node, key=None):
        if isinstance(node, dict):
            for name, value in node.items():
                if name in ("first_pass_route", "harness_route") and isinstance(value, str):
                    named.add(value)
                if name == "model_routes":
                    named.update(value)
                if name == "price_list":
                    named.update(value.get("models", {}))
                walk(value, name)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(published)
    assert named >= {"handwriting-qwen", "handwriting-muse", "first-pass-glm", "harness-deepseek"}
    assert named <= set(mapping), sorted(named - set(mapping))


def test_meter_rows_accept_graphql_wrappers_text_or_number_int64_and_drop_other_months_and_duplicates():
    good = meter("huggingface", "handwriting-qwen", 1_500_000)
    numeric = dict(good, id="00000000-0000-4000-8000-0000000000f1", costMicros=250, listCostMicros=250.0)
    september = meter("huggingface", "handwriting-qwen", 9, when="2026-09-30T23:00:00Z")
    snake = {"organization_id": ORG, "collection_id": COLLECTION, "id": "00000000-0000-4000-8000-0000000000f2",
             "provider": "google_cloud", "resource": "sam3", "cost_micros": 7, "cost_basis": "computed",
             "occurred_at": "2026-10-01T00:00:00+00:00"}
    for wrapped in ([good, numeric, good, september, snake], {"costEntries": [good, numeric, good, september, snake]},
                    {"data": {"costEntries": [good, numeric, good, september, snake]}}):
        rows, info = parse_meter_rows(wrapped, MONTH)
        assert [r.cost for r in rows] == [1_500_000, 250, 7]
        assert [r.list_cost for r in rows] == [1_500_000, 250, 7]
        assert info == {"rows_supplied": 5, "rows_other_month": 1, "duplicates_dropped": 1}
        assert rows[2].source == "paid_call" and rows[2].month == MONTH


@pytest.mark.parametrize("bad,why", [
    ("rows", "expected a list"),
    ([5], "expected an object"),
    ([{"provider": "huggingface", "resource": "x", "month": MONTH}], "costMicros"),
    ([{"costMicros": "1.5", "provider": "huggingface", "resource": "x", "month": MONTH}], "whole number"),
    ([{"costMicros": 1, "resource": "x", "month": MONTH}], "provider and resource"),
    ([{"costMicros": 1, "provider": "huggingface", "resource": "x"}], "month or occurredAt"),
])
def test_unreadable_meter_rows_stop_the_check_and_say_where(bad, why):
    with pytest.raises(ReconciliationInputError, match=why):
        parse_meter_rows(bad, MONTH)


# ---- the Hugging Face bill --------------------------------------------------

HISTOGRAM_BARS = [
    {"date": "2026-10-10", "bars": [{"model": QWEN, "numRequests": 2, "usedNanoUsd": 1_500_000_000},
                                    {"model": MUSE, "numRequests": 1, "usedNanoUsd": "400000000"}]},
    {"date": "2026-10-11", "bars": [{"model": QWEN, "numRequests": 1, "usedNanoUsd": 500_000_000}]},
]
NORMALIZED = hf({"2026-10-10": {QWEN: (2, 1_500_000_000), MUSE: (1, 400_000_000)},
                 "2026-10-11": {QWEN: (1, 500_000_000)}})


def totals_of(bill):
    return {(day.isoformat(), bill.names[key]): tuple(cell) for day, models in bill.days.items()
            for key, cell in models.items()}


def test_both_hugging_face_shapes_read_to_the_same_bill():
    expected = {("2026-10-10", QWEN): (2, 1_500_000_000), ("2026-10-10", MUSE): (1, 400_000_000),
                ("2026-10-11", QWEN): (1, 500_000_000)}
    assert totals_of(parse_huggingface(NORMALIZED)) == expected
    midnight = lambda day: int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp() * 1000)  # noqa: E731
    variants = [
        {"histogram": HISTOGRAM_BARS},
        {"inferenceUsageMetrics": {"histogram": HISTOGRAM_BARS}},
        {"props": [{"deep": {"inferenceUsageMetrics": {"histogram": HISTOGRAM_BARS}}}]},
        json.dumps({"x": {"inferenceUsageMetrics": {"histogram": HISTOGRAM_BARS}}}),
        {"histogram": {"2026-10-10": {QWEN: {"numRequests": 2, "usedNanoUsd": 1_500_000_000},
                                      MUSE: {"numRequests": 1, "usedNanoUsd": 400_000_000}},
                       "2026-10-11": {QWEN: {"numRequests": 1, "usedNanoUsd": 500_000_000}}}},
        {"histogram": [{"timestamp": midnight("2026-10-10"), "models": [
            {"name": QWEN, "numRequests": 2, "usedNanoUsd": 1_500_000_000},
            {"name": MUSE, "numRequests": 1, "usedNanoUsd": 400_000_000}]},
            {"timestamp": midnight("2026-10-11"), "models": {QWEN: {"numRequests": 1, "usedNanoUsd": 500_000_000}}}]},
        {"histogram": [{"day": "2026-10-10", "model": QWEN, "numRequests": 1, "usedNanoUsd": 1_000_000_000},
                       {"day": "2026-10-10", "model": QWEN + ":novita", "numRequests": 1, "usedNanoUsd": 500_000_000},
                       {"day": "2026-10-10", "model": MUSE, "numRequests": 1, "usedNanoUsd": 400_000_000},
                       {"day": "2026-10-11", "model": QWEN, "numRequests": 1, "usedNanoUsd": 500_000_000}]},
    ]
    for variant in variants:
        assert totals_of(parse_huggingface(variant)) == expected


def test_a_histogram_with_no_usage_is_an_empty_bill_but_an_unplaceable_one_is_an_error():
    assert parse_huggingface({"histogram": []}).days == {}
    assert parse_huggingface({"histogram": [{"date": "2026-10-10", "bars": []}]}).days == {}
    with pytest.raises(ReconciliationInputError, match="unrecognized layout"):
        parse_huggingface({"histogram": 7})
    with pytest.raises(ReconciliationInputError, match="first entry keys: \\['date', 'spend'\\]"):
        parse_huggingface({"histogram": [{"date": "2026-10-10", "spend": [{"who": "x", "cents": 3}]}]})
    with pytest.raises(ReconciliationInputError, match="inferenceUsageMetrics"):
        parse_huggingface({"nothing": 1})
    with pytest.raises(ReconciliationInputError, match="not a day"):
        parse_huggingface({"days": {"2026-13-40": {QWEN: {"requests": 1, "nano_usd": 1}}}})


def hugging_face_scenario():
    rows = [
        # Qwen: 1,000,000 + 2,000,000 + 500,000 settled = 3,500,000; one refused call costs 0.
        meter("huggingface", "handwriting-qwen", 1_000_000, when="2026-10-10T08:00:00Z"),
        meter("huggingface", "handwriting-qwen", 2_000_000, when="2026-10-11T08:00:00Z"),
        meter("huggingface", "handwriting-qwen", 500_000, when="2026-10-11T09:00:00Z"),
        meter("huggingface", "handwriting-qwen", 0, basis="refused", when="2026-10-12T09:00:00Z"),
        # A September row and a duplicate must not count.
        meter("huggingface", "handwriting-qwen", 9_999_999, when="2026-09-30T23:59:00Z"),
        # Muse: 4,000,000 + 1,000,000 = 5,000,000 settled.
        meter("huggingface", "handwriting-muse", 4_000_000, when="2026-10-10T10:00:00Z"),
        meter("huggingface", "handwriting-muse", 1_000_000, when="2026-10-10T11:00:00Z"),
        # GLM: 2 x 1,000,000 settled, one call held at its 3,000,000 reservation.
        meter("huggingface", "first-pass-glm", 1_000_000, when="2026-10-12T08:00:00Z", stage="first_pass"),
        meter("huggingface", "first-pass-glm", 1_000_000, when="2026-10-12T09:00:00Z", stage="first_pass"),
        meter("huggingface", "first-pass-glm", 3_000_000, basis="reserved", when="2026-10-13T09:00:00Z",
              stage="first_pass"),
        # A route the registry does not name.
        meter("huggingface", "handwriting-legacy", 300_000, when="2026-10-15T09:00:00Z"),
    ]
    rows.append(rows[0])  # the same row twice, as two overlapping pages would carry it
    bill = hf({
        "2026-10-10": {QWEN: (1, 1_000_000_000), MUSE: (2, 4_350_000_000)},
        "2026-10-11": {QWEN: (2, 2_500_000_000)},
        "2026-10-12": {GLM: (2, 2_000_000_000)},
        "2026-10-14": {DEEPSEEK: (5, 1_000_000_000), "acme/Other-7B": (1, 200_000_000)},
        "2026-09-30": {QWEN: (1, 77_000_000_000)},
    })
    return rows, bill


def test_hugging_face_gaps_split_settled_held_discounted_and_unmatched_models():
    rows, bill = hugging_face_scenario()
    report = reconcile(meter_rows=rows, huggingface=bill, month=MONTH)
    section = report["huggingface"]
    assert section["bill_days_outside_month"] == 1
    assert report["inputs"]["rows_other_month"] == 1 and report["inputs"]["duplicates_dropped"] == 1

    qwen = model(report, QWEN)
    assert (qwen["billed_micros"], qwen["billed_requests"]) == (3_500_000, 3)
    assert (qwen["metered_settled_micros"], qwen["metered_held_micros"], qwen["metered_micros"]) == (3_500_000, 0, 3_500_000)
    assert (qwen["meter_calls"], qwen["meter_refused_calls"], qwen["meter_settled_calls"]) == (4, 1, 3)
    assert qwen["gap_micros"] == 0 and not qwen["flagged"] and qwen["explanations"] == []

    muse = model(report, MUSE)  # billed 4,350,000 against 5,000,000 at list: 87%
    assert (muse["billed_micros"], muse["metered_settled_micros"], muse["gap_micros"]) == (4_350_000, 5_000_000, 650_000)
    assert muse["gap_percent"] == 14.94 and muse["threshold_micros"] == 217_500 and muse["flagged"]
    assert muse["billed_over_settled"] == 0.87 and codes(muse) == ["provider_discount"]
    assert "87.0%" in muse["explanations"][0]["text"]

    glm = model(report, GLM)  # the bill matches the settled calls; the held call is the whole gap
    assert (glm["metered_settled_micros"], glm["metered_held_micros"], glm["metered_micros"]) == (2_000_000, 3_000_000, 5_000_000)
    assert (glm["gap_micros"], glm["gap_settled_micros"], glm["meter_held_calls"]) == (3_000_000, 0, 1)
    assert codes(glm) == ["held_calls"]
    assert "Settled calls alone are within the limit" in glm["explanations"][0]["text"]

    deepseek = model(report, DEEPSEEK)
    assert deepseek["gap_micros"] == -1_000_000 and codes(deepseek) == ["no_meter_rows"]
    assert "the registry names this model" in deepseek["explanations"][0]["text"]
    other = model(report, "acme/Other-7B")
    assert other["in_registry"] is False and codes(other) == ["no_meter_rows"]
    assert "no route in the registry names this model" in other["explanations"][0]["text"]

    legacy = model(report, "handwriting-legacy")
    assert legacy["model_id"] is None and legacy["metered_micros"] == 300_000 and codes(legacy) == ["route_not_in_registry"]

    totals = section["totals"]
    assert totals["billed_micros"] == 3_500_000 + 4_350_000 + 2_000_000 + 1_000_000 + 200_000 == 11_050_000
    assert totals["metered_micros"] == 3_500_000 + 5_000_000 + 5_000_000 + 300_000 == 13_800_000
    assert totals["gap_micros"] == 2_750_000
    flagged = {f["key"] for f in report["flags"] if f["scope"] == "huggingface"}
    assert flagged == {MUSE, GLM, DEEPSEEK, "acme/Other-7B", "handwriting-legacy"}
    assert report["totals"]["metered_micros"] == 13_800_000  # the meter's own month total, every row once


def test_requests_outside_the_meter_and_list_price_drift_are_told_apart():
    rows = [meter("huggingface", "handwriting-qwen", 1_000_000), meter("huggingface", "handwriting-muse", 1_000_000)]
    bill = hf({"2026-10-10": {QWEN: (4, 1_900_000_000), MUSE: (1, 1_300_000_000)}})
    report = reconcile(meter_rows=rows, huggingface=bill, month=MONTH)
    assert codes(model(report, QWEN)) == ["requests_outside_meter"]
    assert "3 more requests (4)" in model(report, QWEN)["explanations"][0]["text"]
    assert codes(model(report, MUSE)) == ["billed_above_list"]
    assert "2026-10-test as of 2026-10-01" in model(report, MUSE)["explanations"][0]["text"]


def test_routes_that_share_a_model_are_billed_as_one_model():
    nemotron = HUGGINGFACE_ROUTES["handwriting-nemotron"].model_id
    assert {HUGGINGFACE_ROUTES[r].model_id for r in ("first-pass-nemotron", "harness-nemotron")} == {nemotron}
    rows = [meter("huggingface", "handwriting-nemotron", 100_000), meter("huggingface", "first-pass-nemotron", 200_000),
            meter("huggingface", "harness-nemotron", 300_000), meter("huggingface", "harness-nemotron", 50_000)]
    report = reconcile(meter_rows=rows, huggingface=hf({"2026-10-10": {nemotron.upper() + ":baseten": (4, 650_000_000)}}),
                       month=MONTH)
    [entry] = report["huggingface"]["models"]
    assert entry["label"] == nemotron and (entry["billed_micros"], entry["metered_micros"]) == (650_000, 650_000)
    assert [(r["route_id"], r["calls"], r["settled_micros"]) for r in entry["routes"]] == [
        ("first-pass-nemotron", 1, 200_000), ("handwriting-nemotron", 1, 100_000), ("harness-nemotron", 2, 350_000)]
    assert not entry["flagged"] and report["flags"] == []


def test_a_gap_on_the_months_last_day_is_named_a_day_boundary_edge():
    rows = [meter("huggingface", "handwriting-qwen", 1_000_000, when="2026-10-10T12:00:00Z"),
            meter("huggingface", "handwriting-qwen", 1_000_000, when="2026-10-31T23:30:00Z")]
    bill = hf({"2026-10-10": {QWEN: (1, 1_000_000_000)}})  # the second call is billed on 1 November
    qwen = model(reconcile(meter_rows=rows, huggingface=bill, month=MONTH), QWEN)
    assert qwen["gap_micros"] == 1_000_000 and "day_boundary" in codes(qwen)
    last = qwen["days"][-1]
    assert last["day"] == "2026-10-31" and last["gap_micros"] == 1_000_000


@pytest.mark.parametrize("gap,billed,flagged", [
    (50_000, 0, False),          # at the USD 0.05 floor: not above it
    (50_001, 0, True),
    (500_000, 10_000_000, False),  # 5% of USD 10 is USD 0.50
    (500_001, 10_000_000, True),
    (-500_001, 10_000_000, True),
])
def test_a_gap_is_flagged_above_the_larger_of_the_floor_and_five_percent(gap, billed, flagged):
    assert Thresholds().exceeded(gap, billed) is flagged


def test_custom_thresholds_change_what_is_flagged():
    rows, bill = hugging_face_scenario()
    strict = reconcile(meter_rows=rows, huggingface=bill, month=MONTH, thresholds=Thresholds(0, 0.0))
    lax = reconcile(meter_rows=rows, huggingface=bill, month=MONTH, thresholds=Thresholds(10_000_000, 0.0))
    assert len([f for f in strict["flags"] if f["scope"] == "huggingface"]) == 5
    assert [f for f in lax["flags"] if f["scope"] == "huggingface"] == []
    assert strict["thresholds"] == {"absolute_micros": 0, "relative": 0.0}


# ---- the Google bill --------------------------------------------------------

SAM_CPU = "Services CPU (Instance-based billing) in us-east4"
SAM_MEMORY = "Services Memory (Instance-based billing) in us-east4"
JOBS_CPU = "Jobs CPU in us-east4"
API_CPU = "Services CPU (Request-based billing)"
SQL_MICRO = "Cloud SQL for PostgreSQL: Zonal - Micro instance in Northern Virginia"
SQL_STORAGE = "Cloud SQL for PostgreSQL: Zonal - Standard storage in Northern Virginia"


def export(service, sku, cost, start="2026-10-16T12:00:00Z", *, credits=(), project=PROJECT,
           invoice="202610", cost_type="regular"):
    """A row of the standard export as `bq query --format=json` prints it: nested, numbers as text."""
    begin = datetime.fromisoformat(start.replace("Z", "+00:00"))
    return {"service": {"id": "S", "description": service}, "sku": {"id": "K", "description": sku},
            "project": {"id": project}, "usage_start_time": begin.strftime("%Y-%m-%d %H:%M:%S"),
            "usage_end_time": (begin + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            "cost": str(cost), "currency": "USD", "cost_type": cost_type,
            "credits": [{"amount": str(amount), "type": kind, "name": kind.title()} for amount, kind in credits],
            "invoice": {"month": invoice}}


def google_export():
    return [
        export("Cloud Run", SAM_CPU, 0.23, credits=[(-0.23, "FREE_TIER")]),       # SAM: 330,000 - 230,000
        export("Cloud Run", SAM_MEMORY, 0.10),                                      #      = 100,000
        export("Cloud Run", JOBS_CPU, 0.20, "2026-10-15T12:00:00Z", credits=[(-0.05, "FREE_TIER")]),
        export("Cloud Run", JOBS_CPU, 0.20, "2026-10-16T12:00:00Z"),                # worker: 600,000 - 50,000
        export("Cloud Run", JOBS_CPU, 0.20, "2026-10-17T12:00:00Z"),                #        = 550,000
        export("Cloud Run", API_CPU, 0.02, credits=[(-0.02, "FREE_TIER")]),         # API: 20,000 - 20,000 = 0
        export("Cloud Run", "Requests", 0.00),
        export("Cloud Storage", "Standard Storage US Multi-region", 0.02),          # storage: 30,000
        export("Cloud Storage", "Standard Class A Operations", 0.01),
        export("Cloud SQL", SQL_MICRO, 0.11),                                       # database: 130,000, a
        export("Cloud SQL", SQL_STORAGE, 0.02, credits=[(-0.01, "PROMOTION")]),     # promotion kept apart
        export("Artifact Registry", "Artifact Registry Storage", 0.04),             # not metered: 40,000
        export("Secret Manager", "Secret access operations", 0.00),
        export("Tax", "Tax", 0.01, cost_type="tax"),                                # not metered: 10,000
        export("Cloud Run", SAM_CPU, 0.50, project="other-project", credits=[(-0.30, "FREE_TIER")]),
        export("Cloud Run", JOBS_CPU, 1.00, "2026-09-20T12:00:00Z", invoice="202609"),  # September usage
    ]


def google_meter():
    return [
        meter("google_cloud", "sam3", 100_000, kind="service", stage="label_finding", when="2026-10-16T12:00:00Z"),
        meter("google_cloud", "specimen-sam", 230_000, method="sam-residual", stage="label_finding",
              when="2026-10-16T07:00:00Z"),
        meter("google_cloud", "specimen-sam", -230_000, list_cost=0, method="free-allowance", stage="label_finding",
              basis="allocated", when="2026-10-16T07:00:00Z"),
        meter("google_cloud", "specimen-worker", 200_000, method="gap-attributed", stage="worker",
              when="2026-10-15T07:00:00Z"),
        meter("google_cloud", "bucket-x", 30_000, method="stored-bytes", stage="storage", when="2026-10-16T07:00:00Z"),
        meter("google_cloud", "cloud-sql", 130_000, method="specimens-held", stage="database",
              when="2026-10-16T07:00:00Z"),
        meter("tool", "geography_lookup", 5_000, kind="tool", stage="parse"),
        meter("google_cloud", "mystery", 7_000, kind="service", stage="elsewhere"),
    ]


def test_google_export_rows_map_to_families_with_the_free_allowance_kept_apart():
    report = reconcile(meter_rows=google_meter(), google=google_export(), month=MONTH, project_id=PROJECT)
    g = report["google"]
    assert g["source"] == "export" and g["lines_outside_month"] == 1
    assert g["other_projects"] == {"lines": 1, "cost_micros": 500_000, "free_micros": -300_000}
    sam = family(report, "specimen-sam")
    assert (sam["billed_cost_micros"], sam["billed_credits_micros"], sam["billed_after_allowance_micros"]) == (330_000, -230_000, 100_000)
    assert (sam["meter_list_micros"], sam["meter_credits_micros"], sam["meter_after_allowance_micros"]) == (330_000, -230_000, 100_000)
    assert (sam["meter_direct_micros"], sam["meter_allocated_micros"], sam["gap_micros"], sam["gap_list_micros"]) == (100_000, 0, 0, 0)
    assert not sam["flagged"]
    api = family(report, "specimen-api")
    assert (api["billed_cost_micros"], api["billed_credits_micros"], api["billed_after_allowance_micros"]) == (20_000, -20_000, 0)
    storage = family(report, "storage")
    assert storage["billed_after_allowance_micros"] == 30_000 and storage["gap_micros"] == 0
    database = family(report, "database")  # 130,000 before credits; the promotion credit is not the free allowance
    assert (database["billed_cost_micros"], database["billed_credits_micros"], database["billed_other_credits_micros"]) == (130_000, 0, -10_000)
    assert (database["billed_after_allowance_micros"], database["billed_net_micros"], database["gap_micros"]) == (130_000, 120_000, 0)
    unmetered = g["unmetered"]
    assert [(l["service"], l["sku"], l["net_micros"]) for l in unmetered["lines"]] == [
        ("Artifact Registry", "Artifact Registry Storage", 40_000), ("Tax", "(tax)", 10_000),
        ("Secret Manager", "Secret access operations", 0)]
    assert (unmetered["after_allowance_micros"], unmetered["net_micros"], unmetered["other_credits_micros"]) == (50_000, 50_000, 0)
    assert g["totals"]["billed_micros"] == 100_000 + 550_000 + 0 + 30_000 + 130_000 + 50_000 == 860_000
    assert g["totals"]["metered_families_micros"] == 100_000 + 200_000 + 0 + 30_000 + 130_000 == 460_000
    assert g["totals"]["billed_other_credits_micros"] == -10_000
    # Every meter row is counted once: families, the unplaced Google row and the tool row.
    assert g["meter_unplaced"] == {"rows": 1, "cost_micros": 7_000}
    assert report["meter_other"]["cost_micros"] == 5_000
    assert report["totals"]["metered_micros"] == 100_000 + 230_000 - 230_000 + 200_000 + 30_000 + 130_000 + 5_000 + 7_000 == 472_000
    assert report["totals"]["billed_google_unmetered_micros"] == 50_000


def test_a_free_allowance_row_that_names_no_family_still_counts_and_is_listed():
    rows = [meter("google_cloud", "sam3", 100_000, kind="service"),
            meter("google_cloud", "shared-pool", -40_000, list_cost=0, method="free-allowance", stage="pool")]
    report = reconcile(meter_rows=rows, google={"lines": []}, month=MONTH)
    assert report["google"]["meter_unassigned_credits_micros"] == -40_000
    assert report["google"]["totals"]["metered_micros"] == 60_000 == report["totals"]["metered_micros"]
    assert family(report, "specimen-sam")["meter_after_allowance_micros"] == 100_000
    assert "| google_cloud |  | (free allowance, not placed in a family) |  | -$0.0400 |" in render_markdown(report)


def test_a_worker_gap_names_the_days_with_no_allocation_and_the_intake_jobs():
    report = reconcile(meter_rows=google_meter(), google=google_export(), month=MONTH, project_id=PROJECT)
    worker = family(report, "specimen-worker")
    assert (worker["billed_cost_micros"], worker["billed_after_allowance_micros"]) == (600_000, 550_000)
    assert worker["meter_after_allowance_micros"] == 200_000 and worker["gap_micros"] == -350_000
    assert worker["gap_percent"] == -63.64 and worker["flagged"]
    assert worker["billed_days"] == ["2026-10-15", "2026-10-16", "2026-10-17"]
    assert worker["allocation_days"] == ["2026-10-15"]
    assert codes(worker) == ["missing_allocation_days", "intake_jobs"]
    assert "2026-10-16, 2026-10-17" in worker["explanations"][0]["text"]
    assert [f["key"] for f in report["flags"]] == ["specimen-worker"]


def test_a_meter_with_no_allocation_rows_says_so_and_a_held_direct_charge_is_named():
    only_sam = [meter("google_cloud", "sam3", 40_000, kind="service", when="2026-10-16T12:00:00Z")]
    report = reconcile(meter_rows=only_sam, google=google_export(), month=MONTH, project_id=PROJECT)
    assert report["inputs"]["meter_has_allocation_rows"] is False
    sam = family(report, "specimen-sam")
    assert sam["gap_micros"] == -60_000 and codes(sam) == ["no_allocation_rows"]
    assert "only direct SAM 3 charges ($0.0400 here)" in sam["explanations"][0]["text"]
    held = [meter("google_cloud", "sam3", 400_000, kind="service", basis="reserved", when="2026-10-16T12:00:00Z")]
    bill = [export("Cloud Run", SAM_MEMORY, 0.10)]
    report = reconcile(meter_rows=held, google=bill, month=MONTH)
    sam = family(report, "specimen-sam")
    assert (sam["meter_held_micros"], sam["gap_micros"]) == (400_000, 300_000) and "held_calls" in codes(sam)


def test_a_shared_free_tier_is_named_when_the_meter_allowed_more_than_the_bill_gave():
    rows = [meter("google_cloud", "sam3", 100_000, kind="service", when="2026-10-16T12:00:00Z"),
            meter("google_cloud", "specimen-sam", 230_000, method="sam-residual", stage="label_finding",
                  when="2026-10-16T07:00:00Z"),
            meter("google_cloud", "specimen-sam", -230_000, list_cost=0, method="free-allowance", stage="label_finding",
                  when="2026-10-16T07:00:00Z")]  # list 330,000; after the allowance 100,000
    bill = [export("Cloud Run", SAM_CPU, 0.23, credits=[(-0.03, "FREE_TIER")]), export("Cloud Run", SAM_MEMORY, 0.10),
            export("Cloud Run", SAM_CPU, 0.40, project="other-project", credits=[(-0.20, "FREE_TIER")])]
    sam = family(reconcile(meter_rows=rows, google=bill, month=MONTH, project_id=PROJECT), "specimen-sam")
    assert (sam["billed_after_allowance_micros"], sam["meter_after_allowance_micros"], sam["gap_micros"]) == (300_000, 100_000, -200_000)
    assert codes(sam) == ["free_allowance"]
    assert "shared by every project" in sam["explanations"][0]["text"]
    assert "$0.2000 of free-tier credit on other projects" in sam["explanations"][0]["text"]
    # The meter applied no allowance at all: the opposite direction, with its own wording.
    rows = [meter("google_cloud", "sam3", 330_000, kind="service", when="2026-10-16T12:00:00Z")]
    bill = [export("Cloud Run", SAM_CPU, 0.23, credits=[(-0.23, "FREE_TIER")]), export("Cloud Run", SAM_MEMORY, 0.10)]
    sam = family(reconcile(meter_rows=rows, google=bill, month=MONTH), "specimen-sam")
    assert sam["gap_micros"] == 230_000 and codes(sam) == ["free_allowance"]
    assert "holds no free-allowance rows" in sam["explanations"][0]["text"]


def test_console_lines_give_the_same_families_and_other_free_credit_types_can_be_added():
    lines = {"lines": [
        {"service": "Cloud Run", "sku": SAM_MEMORY, "day": "2026-10-17", "cost_usd": 0.10, "credits_usd": 0.0},
        {"service": "Cloud Run", "sku": SAM_CPU, "day": "2026-10-17", "cost_usd": 0.23, "credits_usd": -0.23},
        {"service": "Cloud Run", "sku": "Jobs Memory in us-east4", "day": "2026-10-17", "cost_usd": 0.01, "credits_usd": 0},
        {"service": "Cloud Run", "sku": JOBS_CPU, "day": "2026-10-17", "cost_usd": 0.05, "credits_usd": -0.05},
        {"service": "Cloud Run", "sku": "Services Memory (Request-based billing)", "day": "2026-10-17", "cost_usd": 0.00,
         "credits_usd": 0},
        {"service": "Cloud Run", "sku": API_CPU, "day": "2026-10-17", "cost_usd": 0.02, "credits_usd": -0.02},
        {"service": "Cloud Run", "sku": "Requests", "day": "2026-10-17", "cost_usd": 0.00, "credits_usd": 0},
        {"service": "Cloud SQL", "sku": SQL_MICRO, "day": "2026-10-17", "cost_usd": 0.11, "credits_usd": 0},
        {"service": "Artifact Registry", "sku": "Artifact Registry Storage", "day": "2026-10-17", "cost_usd": 0.04,
         "credits_usd": 0},
        {"service": "Cloud Run", "sku": JOBS_CPU, "day": "2026-09-30", "cost_usd": 5.00, "credits_usd": 0}]}
    report = reconcile(meter_rows=[], google=lines, month=MONTH)
    g = report["google"]
    assert g["source"] == "console" and g["lines_outside_month"] == 1
    figures = {f["family"]: (f["billed_cost_micros"], f["billed_credits_micros"], f["billed_after_allowance_micros"])
               for f in g["families"]}
    assert figures == {"specimen-sam": (330_000, -230_000, 100_000), "specimen-worker": (60_000, -50_000, 10_000),
                       "specimen-api": (20_000, -20_000, 0), "storage": (0, 0, 0), "database": (110_000, 0, 110_000)}
    assert g["unmetered"]["after_allowance_micros"] == g["unmetered"]["net_micros"] == 40_000
    with pytest.raises(ReconciliationInputError, match="zero or negative"):
        parse_google({"lines": [dict(lines["lines"][1], credits_usd=0.23)]})
    # An export credit of another type counts as the free allowance only when the operator says so.
    row = export("Cloud Run", SAM_CPU, 0.23, credits=[(-0.23, "SPENDING_BASED_DISCOUNT")])
    assert parse_google([row]).export[0].free == 0
    assert parse_google([row], free_credit_types={"FREE_TIER", "SPENDING_BASED_DISCOUNT"}).export[0].free == -230_000_000


@pytest.mark.parametrize("service,sku,expected", [
    ("Cloud Run", SAM_CPU, "specimen-sam"), ("Cloud Run", SAM_MEMORY, "specimen-sam"),
    ("Cloud Run", JOBS_CPU, "specimen-worker"), ("Cloud Run", "Jobs Memory in us-east4", "specimen-worker"),
    ("Cloud Run", API_CPU, "specimen-api"), ("Cloud Run", "Services Memory (Request-based billing)", "specimen-api"),
    ("Cloud Run", "Requests", "specimen-api"),
    ("Cloud Run", "Cloud Run Network Internet Data Transfer Out North America to North America", None),
    ("Cloud Run", "Delayed Jobs CPU in us-east4", None),
    ("Cloud Storage", "Standard Storage US Multi-region", "storage"), ("Cloud SQL", SQL_MICRO, "database"),
    ("Firebase Data Connect", "Firebase SQL Connect number of operation requests", None),
    ("Artifact Registry", "Artifact Registry Storage", None), ("Secret Manager", "Secret access operations", None),
    ("Cloud Logging", "Log Volume", None), ("Firebase Hosting", "Storage", None),
])
def test_google_lines_map_to_families_by_service_and_sku(service, sku, expected):
    assert google_family(service, sku) == expected


def test_export_columns_may_be_flat_dotted_text_and_a_data_wrapper_is_unwrapped():
    flat = {"service.description": "Cloud Run", "sku.description": SAM_CPU, "usage_start_time": "2026-10-16T12:00:00Z",
            "cost": 0.5, "credits": json.dumps([{"amount": -0.5, "type": "FREE_TIER"}]), "project.id": "p",
            "invoice.month": "202610"}
    bill = parse_google({"data": [flat]})
    assert (bill.export[0].cost, bill.export[0].free, bill.export[0].project) == (500_000_000, -500_000_000, "p")
    with pytest.raises(ReconciliationInputError, match='"lines"'):
        parse_google({"unrelated": 1})
    with pytest.raises(ReconciliationInputError, match="usage_start_time"):
        parse_google([{"service": {"description": "Cloud Run"}, "sku": {"description": SAM_CPU}, "cost": 1}])


def test_rows_of_other_projects_and_other_invoice_months_are_counted_apart():
    rows = [export("Cloud Run", JOBS_CPU, 0.10, "2026-10-31T12:00:00Z", invoice="202611"),
            export("Cloud Run", JOBS_CPU, 0.20, "2026-10-30T12:00:00Z"),
            export("Cloud Run", JOBS_CPU, 0.40, "2026-10-30T12:00:00Z", project="elsewhere")]
    report = reconcile(meter_rows=[], google=rows, month=MONTH, project_id=PROJECT)
    assert family(report, "specimen-worker")["billed_cost_micros"] == 300_000
    assert report["google"]["invoice_month_shift"] == {"lines": 1, "cost_micros": 100_000}
    assert report["google"]["other_projects"]["cost_micros"] == 400_000
    everything = reconcile(meter_rows=[], google=rows, month=MONTH)  # no project given: all rows count
    assert family(everything, "specimen-worker")["billed_cost_micros"] == 700_000


def test_credits_of_other_types_are_shown_by_type_per_family_and_in_the_headline():
    bill = [
        # The Data Connect no-cost Cloud SQL trial arrives as a credit: 330,000 cost, -330,000 PROMOTION, charge 0.
        export("Cloud SQL", SQL_MICRO, 0.33, credits=[(-0.33, "PROMOTION")]),
        # SAM: 400,000 cost, -300,000 free tier, -20,000 DISCOUNT: 100,000 after the free tier, 80,000 charged.
        export("Cloud Run", SAM_CPU, 0.40, credits=[(-0.30, "FREE_TIER"), (-0.02, "DISCOUNT")]),
        # An unmetered service: 40,000 cost, -10,000 PROMOTION.
        export("Artifact Registry", "Artifact Registry Storage", 0.04, credits=[(-0.01, "PROMOTION")]),
    ]
    meter_rows = [meter("google_cloud", "cloud-sql", 330_000, method="specimens-held", stage="database"),
                  meter("google_cloud", "sam3", 100_000, kind="service")]
    report = reconcile(meter_rows=meter_rows, huggingface={"days": {}}, google=bill, month=MONTH, project_id=PROJECT)
    database, sam = family(report, "database"), family(report, "specimen-sam")
    assert (database["billed_cost_micros"], database["billed_credits_micros"], database["billed_other_credits_micros"],
            database["billed_net_micros"], database["billed_after_allowance_micros"]) == (330_000, 0, -330_000, 0, 330_000)
    assert database["billed_other_credits_by_type"] == {"PROMOTION": -330_000}
    assert (sam["billed_other_credits_by_type"], sam["billed_net_micros"]) == ({"DISCOUNT": -20_000}, 80_000)
    assert not database["flagged"] and not sam["flagged"]   # the meter matches what the free tier leaves
    [artifact] = report["google"]["unmetered"]["lines"]
    assert (artifact["other_credits_by_type"], artifact["after_allowance_micros"], artifact["net_micros"]) == (
        {"PROMOTION": -10_000}, 40_000, 30_000)
    totals = report["totals"]
    assert (totals["billed_google_cost_micros"], totals["billed_google_credits_micros"],
            totals["billed_google_other_credits_micros"], totals["billed_google_net_micros"]) == (
        770_000, -300_000, -360_000, 110_000)
    assert totals["billed_google_other_credits_by_type"] == {"DISCOUNT": -20_000, "PROMOTION": -340_000}
    assert (totals["billed_micros"], totals["billed_net_micros"]) == (470_000, 110_000)
    text = render_markdown(report)
    assert text.splitlines()[2].startswith("Billed: $0.4700 after the free tier ($0.1100 net of $0.3600 of other credits).")
    assert ("- Google Cloud: cost $0.7700, free-tier credits -$0.3000, other credits -$0.3600 "
            "(DISCOUNT -$0.0200, PROMOTION -$0.3400); net charge $0.1100.") in text
    assert "--free-credit-type <TYPE>" in text
    assert "| Cloud SQL | $0.3300 | $0.0000 | -$0.3300 (PROMOTION) | $0.0000 | $0.3300 |" in text
    assert "| Artifact Registry | Artifact Registry Storage | $0.0400 | $0.0000 | -$0.0100 (PROMOTION) | $0.0300 |" in text
    # No other credit: the headline carries no net note and the Google line says there is none.
    plain = render_markdown(reconcile(meter_rows=[], google={"lines": []}, huggingface={"days": {}}, month=MONTH))
    assert "net of" not in plain and "no other credits" in plain and "--free-credit-type" not in plain


def test_a_free_tier_typed_differently_is_named_before_the_shared_free_tier_is_blamed():
    rows = [meter("google_cloud", "sam3", 100_000, kind="service", when="2026-10-16T12:00:00Z"),
            meter("google_cloud", "specimen-sam", 230_000, method="sam-residual", stage="label_finding",
                  when="2026-10-16T07:00:00Z"),
            meter("google_cloud", "specimen-sam", -230_000, list_cost=0, method="free-allowance", stage="label_finding",
                  when="2026-10-16T07:00:00Z")]  # list 330,000; after the allowance 100,000
    bill = [export("Cloud Run", SAM_CPU, 0.23, credits=[(-0.23, "SPENDING_BASED_DISCOUNT")]), export("Cloud Run", SAM_MEMORY, 0.10)]
    sam = family(reconcile(meter_rows=rows, google=bill, month=MONTH, project_id=PROJECT), "specimen-sam")
    assert (sam["billed_credits_micros"], sam["billed_other_credits_by_type"]) == (0, {"SPENDING_BASED_DISCOUNT": -230_000})
    assert sam["gap_micros"] == -230_000 and codes(sam) == ["free_allowance"]
    text = sam["explanations"][0]["text"]
    assert "other credits (SPENDING_BASED_DISCOUNT -$0.2300)" in text
    assert "re-run with --free-credit-type <TYPE> (SPENDING_BASED_DISCOUNT)" in text
    assert text.index("SPENDING_BASED_DISCOUNT") < text.index("Otherwise, Google's free tier is shared by every project")
    # Told the type, the comparison closes.
    fixed = reconcile(meter_rows=rows, google=bill, month=MONTH, project_id=PROJECT,
                      free_credit_types={"FREE_TIER", "SPENDING_BASED_DISCOUNT"})
    assert family(fixed, "specimen-sam")["gap_micros"] == 0 and fixed["flags"] == []
    # With no other credit on the family the wording is the plain one.
    plain = [export("Cloud Run", SAM_CPU, 0.23, credits=[(-0.03, "FREE_TIER")]), export("Cloud Run", SAM_MEMORY, 0.10)]
    text = family(reconcile(meter_rows=rows, google=plain, month=MONTH, project_id=PROJECT),
                  "specimen-sam")["explanations"][0]["text"]
    assert "other credits" not in text and "Otherwise" not in text and "shared by every project" in text


def test_other_credits_on_a_flagged_family_get_their_own_explanation():
    # Worker: 600,000 cost, -100,000 PROMOTION, no meter rows: flagged, and the credit is not what explains it.
    bill = [export("Cloud Run", JOBS_CPU, 0.60, "2026-10-15T12:00:00Z", credits=[(-0.10, "PROMOTION")])]
    rows = [meter("google_cloud", "specimen-sam", 1_000, method="sam-residual", stage="label_finding",
                  when="2026-10-15T07:00:00Z")]
    worker = family(reconcile(meter_rows=rows, google=bill, month=MONTH, project_id=PROJECT), "specimen-worker")
    assert worker["gap_micros"] == -600_000 and "other_credits" in codes(worker)
    text = next(e["text"] for e in worker["explanations"] if e["code"] == "other_credits")
    assert "(PROMOTION -$0.1000)" in text and "net charge for this family was $0.5000" in text


def test_warnings_the_caller_passes_reach_the_report_and_the_markdown():
    plain = reconcile(meter_rows=[], huggingface={"days": {}}, month=MONTH)
    assert plain["warnings"] == [] and "## Warnings" not in render_markdown(plain)
    report = reconcile(meter_rows=[], huggingface={"days": {}}, month=MONTH, input_warnings=("page.json holds exactly 1000 rows",))
    assert report["warnings"] == ["page.json holds exactly 1000 rows"]
    assert "## Warnings\n\n- page.json holds exactly 1000 rows\n" in render_markdown(report)


def test_nano_usd_are_rounded_to_the_nearest_micro_away_from_zero():
    micros = cr._micros
    assert [micros(n) for n in (0, 499, 500, 501, 1_499, 1_500, 1_501)] == [0, 0, 1, 1, 1, 2, 2]
    assert [micros(-n) for n in (499, 500, 1_499, 1_500)] == [0, -1, -1, -2]
    bill = hf({"2026-10-10": {QWEN: (1, 2_000_001_500)}})  # 2,000,001.5 micro-USD rounds up to 2,000,002
    qwen = model(reconcile(meter_rows=[], huggingface=bill, month=MONTH), QWEN)
    assert qwen["billed_micros"] == 2_000_002


def test_allocation_days_are_read_in_the_billing_zone_not_as_the_utc_date():
    # 04:00Z on the 16th is 21:00 on the 15th in Pacific, 23:00 on the 15th in UTC-5, and the 16th in UTC.
    rows = [meter("google_cloud", "specimen-worker", 200_000, method="worker-processing-time", stage="worker",
                  when="2026-10-16T04:00:00Z")]
    bill = [export("Cloud Run", JOBS_CPU, 0.60, "2026-10-15T12:00:00Z")]
    days = {zone: family(reconcile(meter_rows=rows, google=bill, month=MONTH, project_id=PROJECT, billing_zone=zone),
                         "specimen-worker")["allocation_days"]
            for zone in ("America/Los_Angeles", "UTC-5", "UTC")}
    assert days == {"America/Los_Angeles": ["2026-10-15"], "UTC-5": ["2026-10-15"], "UTC": ["2026-10-16"]}


# ---- the billing-day check --------------------------------------------------

MARKERS = [  # (usage start in UTC, USD). The day each falls on, by zone, is worked out beside each.
    ("2026-10-16T04:00:00Z", 1),     # Pacific 15th 21:00, UTC-5 15th 23:00, UTC 16th
    ("2026-10-16T06:00:00Z", 2),     # Pacific 15th 23:00, UTC-5 16th 01:00, UTC 16th
    ("2026-10-16T12:00:00Z", 4),     # the 16th in all three
    ("2026-10-17T04:00:00Z", 8),     # Pacific 16th, UTC-5 16th, UTC 17th
    ("2026-10-17T06:00:00Z", 16),    # Pacific 16th, UTC-5 17th, UTC 17th
    ("2026-10-17T12:00:00Z", 32),    # the 17th in all three
    ("2026-10-18T04:00:00Z", 64),    # Pacific 17th, UTC-5 17th, UTC 18th
    ("2026-10-18T06:00:00Z", 128),   # Pacific 17th, UTC-5 18th, UTC 18th
    ("2026-10-18T12:00:00Z", 256),   # the 18th in all three
]
# Daily totals under each zone for the 16th and 17th: Pacific 28 and 224 (4+8+16, 32+64+128);
# UTC 7 and 56 (1+2+4, 8+16+32); UTC-5 14 and 112 (2+4+8, 16+32+64).
DAILY = {"America/Los_Angeles": (28, 224), "UTC": (7, 56), "UTC-5": (14, 112)}


def hourly_export():
    rows = [export("Cloud Run", SAM_MEMORY, 0, "2026-10-15T00:00:00Z"),
            export("Cloud Run", SAM_MEMORY, 0, "2026-10-19T00:00:00Z")]
    return rows + [export("Cloud Run", SAM_MEMORY, usd, start) for start, usd in MARKERS]


def console_days(zone):
    sixteenth, seventeenth = DAILY[zone]
    return {"lines": [{"service": "Cloud Run", "sku": SAM_MEMORY, "day": "2026-10-16", "cost_usd": sixteenth,
                       "credits_usd": 0},
                      {"service": "Cloud Run", "sku": SAM_MEMORY, "day": "2026-10-17", "cost_usd": seventeenth,
                       "credits_usd": 0}]}


@pytest.mark.parametrize("truth", ["America/Los_Angeles", "UTC", "UTC-5"])
def test_the_day_boundary_that_fits_the_console_best_is_found(truth):
    bill = parse_google(hourly_export(), console_days(truth))
    check = check_billing_day(bill, BillingZone("America/Los_Angeles"))
    errors = {c["zone"]: c["abs_error_micros"] for c in check["candidates"]}
    # The two non-matching zones miss by the differences of the totals above, in micro-USD.
    wrong = {"America/Los_Angeles": {"UTC": 189, "UTC-5": 126}, "UTC": {"America/Los_Angeles": 189, "UTC-5": 63},
             "UTC-5": {"America/Los_Angeles": 126, "UTC": 63}}[truth]
    assert check["status"] == "ok" and check["best_fit"] == truth and errors[truth] == 0
    assert {zone: usd // 1_000_000 for zone, usd in errors.items() if zone != truth} == wrong
    assert check["days_compared"] == ["2026-10-16", "2026-10-17"]
    assert check["assumed_zone_fits_best"] is (truth == "America/Los_Angeles")


def test_a_best_fit_other_than_the_assumed_zone_is_flagged_and_a_tie_is_not_resolved():
    report = reconcile(meter_rows=[], google=(hourly_export(), console_days("UTC-5")), month=MONTH)
    check = report["billing_zone"]["check"]
    assert check["best_fit"] == "UTC-5" and "--billing-zone UTC-5" in check["message"]
    flag = next(f for f in report["flags"] if f["key"] == "billing_day")
    assert flag["explanations"][0]["code"] == "billing_zone" and flag["gap_micros"] is None
    # A bill whose only usage falls mid-day fits every zone equally: no winner.
    midday = [export("Cloud Run", SAM_MEMORY, 0, "2026-10-15T00:00:00Z"),
              export("Cloud Run", SAM_MEMORY, 0, "2026-10-19T00:00:00Z"),
              export("Cloud Run", SAM_MEMORY, 4, "2026-10-16T12:00:00Z"), export("Cloud Run", SAM_MEMORY, 8, "2026-10-17T12:00:00Z")]
    lines = {"lines": [{"service": "Cloud Run", "sku": SAM_MEMORY, "day": "2026-10-16", "cost_usd": 4, "credits_usd": 0},
                       {"service": "Cloud Run", "sku": SAM_MEMORY, "day": "2026-10-17", "cost_usd": 8, "credits_usd": 0}]}
    check = check_billing_day(parse_google(midday, lines), BillingZone("UTC"))
    assert check["status"] == "ok" and check["best_fit"] is None and "equally well" in check["message"]
    # Zones whose errors differ by under a cent are not told apart: the console rounds to cents. Rows: 4.000 at
    # 16th 12:00Z, 0.001 at 17th 03:00Z, 0.003 at 17th 06:00Z, 8.005 at 17th 12:00Z; the console shows 4.00 and 8.01.
    # UTC: days 4.000 and 8.009, off by 0 + 0.001. UTC-5: 4.001 and 8.008, off by 0.001 + 0.002.
    # Pacific: 4.004 and 8.005, off by 0.004 + 0.005. UTC leads Pacific by 0.008 and UTC-5 by 0.002: all under a cent.
    near = [export("Cloud Run", SAM_MEMORY, 0, "2026-10-15T00:00:00Z"),
            export("Cloud Run", SAM_MEMORY, 0, "2026-10-19T00:00:00Z"),
            export("Cloud Run", SAM_MEMORY, 4.000, "2026-10-16T12:00:00Z"),
            export("Cloud Run", SAM_MEMORY, 0.001, "2026-10-17T03:00:00Z"),
            export("Cloud Run", SAM_MEMORY, 0.003, "2026-10-17T06:00:00Z"),
            export("Cloud Run", SAM_MEMORY, 8.005, "2026-10-17T12:00:00Z")]
    lines = {"lines": [{"service": "Cloud Run", "sku": SAM_MEMORY, "day": "2026-10-16", "cost_usd": 4.00, "credits_usd": 0},
                       {"service": "Cloud Run", "sku": SAM_MEMORY, "day": "2026-10-17", "cost_usd": 8.01, "credits_usd": 0}]}
    check = check_billing_day(parse_google(near, lines), BillingZone("UTC"))
    errors = {c["zone"]: c["abs_error_micros"] for c in check["candidates"]}
    assert errors == {"UTC": 1_000, "UTC-5": 3_000, "America/Los_Angeles": 9_000}
    assert check["best_fit"] is None and "differ by under USD 0.01" in check["message"]
    assert check["message"].startswith("The zones UTC, UTC-5, America/Los_Angeles fit equally well")


def test_the_day_boundary_check_says_why_it_did_not_run():
    zone = BillingZone("America/Los_Angeles")
    assert "No hourly export rows" in check_billing_day(None, zone)["reason"]
    assert "daily console lines" in check_billing_day(parse_google(hourly_export()), zone)["reason"]
    assert "hourly" in check_billing_day(parse_google([dict(r, usage_end_time="2026-10-30 00:00:00") for r in hourly_export()],
                                                      console_days("UTC")), zone)["reason"]
    short = parse_google([export("Cloud Run", SAM_MEMORY, 1, "2026-10-16T12:00:00Z")], console_days("UTC"))
    assert "fully inside" in check_billing_day(short, zone)["reason"]


def test_the_pacific_rule_matches_the_clock_changes_and_the_tz_database():
    pacific = BillingZone("US/Pacific")
    assert pacific.name == "America/Los_Angeles"
    at = lambda text: datetime.fromisoformat(text).replace(tzinfo=timezone.utc)  # noqa: E731
    hours = lambda text: pacific.offset(at(text)).total_seconds() / 3600  # noqa: E731
    assert (hours("2026-03-08T09:59:59"), hours("2026-03-08T10:00:00")) == (-8, -7)
    assert (hours("2026-11-01T08:59:59"), hours("2026-11-01T09:00:00")) == (-7, -8)
    assert pacific.day_bounds(date(2026, 10, 17)) == (at("2026-10-17T07:00:00"), at("2026-10-18T07:00:00"))
    assert pacific.day_bounds(date(2026, 11, 1)) == (at("2026-11-01T07:00:00"), at("2026-11-02T08:00:00"))
    assert BillingZone("utc-5").name == "UTC-5" and BillingZone("UTC+5:30").name == "UTC+5:30"
    assert BillingZone("UTC-5").day_bounds(date(2026, 10, 17)) == (at("2026-10-17T05:00:00"), at("2026-10-18T05:00:00"))
    zoneinfo = pytest.importorskip("zoneinfo")
    try:
        database = zoneinfo.ZoneInfo("America/Los_Angeles")
    except zoneinfo.ZoneInfoNotFoundError:
        pytest.skip("no tz database on this machine")
    start = at("2026-01-01T00:00:00")
    for hour in range(24 * 365):
        instant = start + timedelta(hours=hour)
        assert pacific.offset(instant) == instant.astimezone(database).utcoffset(), instant
    with pytest.raises(ReconciliationInputError, match="billing zone"):
        BillingZone("Mars/Olympus")


# ---- empty and partial inputs, and the report --------------------------------

def test_empty_inputs_make_an_empty_report_that_still_renders():
    report = reconcile(meter_rows=[], huggingface={"days": {}}, google={"lines": []}, month=MONTH)
    assert report["flags"] == []
    assert report["totals"]["billed_micros"] == report["totals"]["metered_micros"] == 0
    assert report["totals"]["gap_percent"] is None
    assert report["huggingface"]["models"] == []
    assert [f["billed_after_allowance_micros"] for f in report["google"]["families"]] == [0] * 5
    text = render_markdown(report)
    assert "No gap is above the limit" in text and "Billed: $0.0000 after the free tier. Metered: $0.0000." in text
    assert reconcile(meter_rows={"data": {"costEntries": []}}, huggingface={"histogram": []}, google=[], month=MONTH)["flags"] == []


def test_a_bill_that_was_not_supplied_is_left_out_not_counted_as_zero():
    rows = [meter("huggingface", "handwriting-qwen", 2_000_000)]
    report = reconcile(meter_rows=rows, month=MONTH)
    assert report["inputs"]["huggingface_supplied"] is False and report["flags"] == []
    assert report["totals"]["comparable_billed_micros"] == report["totals"]["comparable_metered_micros"] == 0
    assert report["totals"]["metered_micros"] == 2_000_000
    text = render_markdown(report)
    assert "no bill supplied" in text and text.splitlines()[2].startswith("No bill was supplied. Metered: $2.0000")
    only_google = render_markdown(reconcile(meter_rows=rows, google={"lines": []}, month=MONTH))
    assert "only the Google Cloud bill was supplied" in only_google
    assert "Overall, " not in only_google and "like-for-like line" in only_google


def test_a_total_gap_over_the_limit_lists_what_the_parts_show():
    rows = google_meter() + [meter("huggingface", "handwriting-qwen", 1_000_000)]
    report = reconcile(meter_rows=rows, huggingface=hf({"2026-10-10": {QWEN: (1, 1_000_000_000)}}),
                       google=google_export(), month=MONTH, project_id=PROJECT)
    total = next(f for f in report["flags"] if f["scope"] == "total")
    assert (total["billed_micros"], total["metered_micros"], total["gap_micros"]) == (1_860_000, 1_472_000, -388_000)
    assert [x["code"] for x in total["explanations"]] == ["unmetered_services", "tools_without_bill", "flagged_items"]
    assert report["totals"]["comparable_billed_micros"] == 1_000_000 + 810_000
    assert report["totals"]["comparable_gap_micros"] == (1_000_000 + 460_000) - (1_000_000 + 810_000)


def test_the_json_report_round_trips_and_the_markdown_is_plain_ascii_prose():
    rows, bill = hugging_face_scenario()
    report = reconcile(meter_rows=rows + google_meter(), huggingface=bill, google=(google_export(), console_days("UTC")),
                       month=MONTH, project_id=PROJECT)
    assert json.loads(json.dumps(report)) == report
    text = render_markdown(report)
    text.encode("ascii")
    for expected in ("# Cost meter check, 2026-10", "## What needs a look", "## Hugging Face, by model",
                     "## Google Cloud, by cost family", "### Google lines the meter does not cover",
                     "## Billing-day time zone", "## Inputs and limits", "87.0%",
                     "Settled calls alone are within the limit", "intake jobs", "## Metered rows with no bill to compare",
                     "| tool | tool | geography_lookup | 1 | $0.0050 |",
                     "| google_cloud |  | (not placed in a family) | 1 | $0.0070 |"):
        assert expected in text, expected
    assert text.startswith("# Cost meter check, 2026-10\n\nBilled: $")
    headline = text.splitlines()[2]
    assert "Overall, the meter is" in headline and "the bill" in headline


def test_a_bad_month_or_billing_zone_is_refused():
    with pytest.raises(ValueError, match="YYYY-MM"):
        reconcile(meter_rows=[], month="2026-13")
    with pytest.raises(ReconciliationInputError, match="billing zone"):
        reconcile(meter_rows=[], month=MONTH, billing_zone="Nowhere/Land")
