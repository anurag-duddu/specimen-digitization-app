"""The cost meter's rows and totals (docs/execution/golive/COST_METER.md)."""

from __future__ import annotations

import copy
from uuid import UUID

import pytest
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Struct

from specimen_digitization.application import cost_ledger
from specimen_digitization.application.cost_ledger import (
    CostRowInvalid,
    cost_report,
    months_between,
    paid_call_rows,
    stage_of,
)
from specimen_digitization.application.domain import Asset, Specimen
from specimen_digitization.application.history_restore import restored_specimen
from specimen_digitization.application.lane_costs import (
    record_model_usage,
    record_refused,
    record_reserved,
    record_segmentation,
    record_tool_usage,
)
from specimen_digitization.application.lane_reservations import step_reservation
from specimen_digitization.application.projection import derived_id
from specimen_digitization.field_research.step import record_cost

from test_lane_costs import QWEN, priced_run

ORG = "00000000-0000-4000-8000-0000000000a1"
COLLECTION = "00000000-0000-4000-8000-0000000000b2"
SPECIMEN = "00000000-0000-4000-8000-0000000000c3"
INSTANCE = {"first": False, "idle_seconds": 4.0, "request_seconds": 12.5}


def rows(run, specimen=SPECIMEN):
    return paid_call_rows(ORG, COLLECTION, specimen, run)


@pytest.mark.parametrize("step,stage", [
    ("segment", "label_finding"),
    ("transcribe:region-1:handwriting-qwen", "reading"),
    ("first_pass:region-1", "first_pass"),
    ("parse", "structuring"),
    ("classify", "classification"),
    ("field_research", "field_research"),
    ("adjudicate", "adjudicate"),
    ("lookup:taxonomy", "lookup"),
])
def test_each_step_belongs_to_its_stage(step, stage):
    assert stage_of(step) == stage


def test_a_run_s_paid_calls_become_one_row_each_in_the_connector_shape():
    run = priced_run()
    run.attempts[QWEN] = 2
    record_model_usage(run, QWEN, "handwriting-qwen", input_tokens=1_000, output_tokens=500)
    record_segmentation(run, "segment", seconds=25.2, instance=INSTANCE)
    record_tool_usage(run, "parse", "geography_lookup", requests=3)
    reading, segment, tool = rows(run)
    assert set(reading) == {
        "organization_id", "collection_id", "id", "source", "specimen_id", "run_id", "step", "stage",
        "attempt", "kind", "ordinal", "provider", "resource", "usage", "reserved_micros", "cost_micros",
        "list_cost_micros", "cost_basis", "outcome", "failure_code", "price_list_version",
        "price_list_as_of", "occurred_at", "month", "allocation_method_id", "allocation_method_details",
    }
    call = run.paid_calls[0]
    assert reading == {
        "organization_id": ORG, "collection_id": COLLECTION,
        "id": derived_id("cost", SPECIMEN, run.id, QWEN, 2, "model", 0),
        "source": "paid_call", "specimen_id": SPECIMEN, "run_id": run.id, "step": QWEN,
        "stage": "reading", "attempt": 2, "kind": "model", "ordinal": 0, "provider": "huggingface",
        "resource": "handwriting-qwen", "usage": {"input_tokens": 1_000, "output_tokens": 500},
        "reserved_micros": call["reserved_micros"], "cost_micros": 550, "list_cost_micros": 550,
        "cost_basis": "computed", "outcome": "completed", "failure_code": None,
        "price_list_version": "lane-test-prices-1", "price_list_as_of": "2026-09-23",
        "occurred_at": call["at"], "month": call["at"][:7],
        "allocation_method_id": None, "allocation_method_details": None,
    }
    assert (segment["kind"], segment["provider"], segment["resource"], segment["stage"]) == (
        "service", "google_cloud", "sam3", "label_finding")
    assert segment["usage"]["instance"] == INSTANCE
    assert (tool["kind"], tool["provider"], tool["resource"], tool["cost_micros"]) == (
        "tool", "tool", "geography_lookup", 15_000)


def test_held_refused_and_billed_calls_keep_their_basis_and_amount():
    run = priced_run()
    record_reserved(run, QWEN, "model", outcome="unknown", route_id="handwriting-qwen",
                    failure_code="model_timeout")
    record_refused(run, "first_pass:region-1", "model", route_id="first-pass-glm",
                   failure_code="provider_refused")
    record_model_usage(run, "parse", "handwriting-qwen", input_tokens=10, output_tokens=10, billed_micros=321)
    held, refused, billed = rows(run)
    assert (held["cost_basis"], held["cost_micros"], held["failure_code"]) == (
        "reserved", step_reservation(run, QWEN), "model_timeout")
    assert held["cost_micros"] == held["reserved_micros"] > 0
    assert (refused["cost_basis"], refused["cost_micros"], refused["failure_code"]) == (
        "refused", 0, "provider_refused")
    assert (billed["cost_basis"], billed["cost_micros"], billed["list_cost_micros"]) == ("billed", 321, 321)


def test_a_call_with_no_cost_counts_at_its_reservation_else_at_zero():
    run = priced_run()
    record_model_usage(run, QWEN, "handwriting-qwen", input_tokens=1, output_tokens=1)
    unknown = dict(run.paid_calls[0], cost_micros=None, cost_basis="computed", reserved_micros=4_000)
    nothing = dict(run.paid_calls[0], step="parse", cost_micros=None, reserved_micros=None)
    run.paid_calls = [unknown, nothing]
    held, zero = rows(run)
    assert (held["cost_micros"], held["cost_basis"]) == (4_000, "reserved")
    assert (zero["cost_micros"], zero["reserved_micros"]) == (0, None)


def test_field_research_s_paid_call_is_a_model_row_of_its_stage():
    run = priced_run()
    run.attempts["field_research"] = 1
    record_cost(run, "harness-deepseek", reserved=900_000, spent=1_250, outcome="completed", model_calls=25)
    record_cost(run, "harness-deepseek", reserved=900_000, spent=None, outcome="unknown")
    known, unknown = rows(run)
    assert (known["stage"], known["kind"], known["provider"], known["resource"]) == (
        "field_research", "model", "huggingface", "harness-deepseek")
    assert (known["cost_micros"], known["cost_basis"], known["usage"]) == (1_250, "computed", {"model_calls": 25})
    # The same step, attempt and kind twice: the second is ordinal 1, with its own id.
    assert (known["ordinal"], unknown["ordinal"]) == (0, 1)
    assert known["id"] != unknown["id"]
    assert unknown["id"] == derived_id("cost", SPECIMEN, run.id, "field_research", 1, "model", 1)
    assert (unknown["cost_micros"], unknown["cost_basis"], unknown["usage"]) == (900_000, "reserved", None)


def test_field_research_s_paid_call_keeps_the_tokens_its_provider_reported():
    run = priced_run()
    run.attempts["field_research"] = 1
    tokens = {"requests": 24, "input_tokens": 480_000, "cached_input_tokens": 430_000, "output_tokens": 9_000}
    record_cost(run, "harness-deepseek", reserved=900_000, spent=1_250, outcome="completed", model_calls=25,
                tokens=tokens)
    [row] = rows(run)
    assert row["usage"] == {"model_calls": 25, "reported_requests": 24, "input_tokens": 480_000,
                            "cached_input_tokens": 430_000, "output_tokens": 9_000}
    assert (row["cost_basis"], row["cost_micros"]) == ("computed", 1_250)


def test_ordinals_count_only_calls_of_the_same_step_attempt_and_kind():
    run = priced_run()
    for attempt in (1, 1, 2):
        run.attempts[QWEN] = attempt
        record_model_usage(run, QWEN, "handwriting-qwen", input_tokens=1, output_tokens=1)
    record_segmentation(run, "segment", seconds=1, instance=INSTANCE)
    record_model_usage(run, "parse", "handwriting-qwen", input_tokens=1, output_tokens=1)
    assert [(row["attempt"], row["ordinal"]) for row in rows(run)] == [(1, 0), (1, 1), (2, 0), (1, 0), (1, 0)]
    assert len({row["id"] for row in rows(run)}) == 5


def test_the_same_calls_always_derive_the_same_ids():
    run = priced_run()
    record_model_usage(run, QWEN, "handwriting-qwen", input_tokens=1, output_tokens=1)
    record_segmentation(run, "segment", seconds=1, instance=INSTANCE)
    first = rows(run)
    assert rows(run.model_copy(deep=True)) == first
    # Another specimen's copy of the run is another set of rows.
    assert {row["id"] for row in rows(run, "00000000-0000-4000-8000-0000000000d4")}.isdisjoint(
        {row["id"] for row in first})


def test_a_history_restored_run_keeps_the_ids_of_its_calls():
    """history_restore copies the latest same-run accounting, so the restored
    run's calls, and the ids derived from them, are the original run's."""
    run = priced_run()
    record_model_usage(run, QWEN, "handwriting-qwen", input_tokens=1_000, output_tokens=500)
    record_segmentation(run, "segment", seconds=25.2, instance=INSTANCE)
    original = Specimen(
        id=SPECIMEN,
        scope={"organization_id": ORG, "collection_id": COLLECTION},
        asset=Asset(sensitive=False, sha256="a" * 64, blob_ref="blob", media_type="image/png",
                    size_bytes=1, width=1, height=1, filename="label.png", uploader="uploader"),
        run=run,
    )
    original.version = 2
    # A later run became active; a person restores the original run's content.
    newer = original.model_copy(deep=True)
    newer.version, newer.previous_runs = 3, [original.run.model_copy(deep=True)]
    newer.run = priced_run()
    restored = restored_specimen(newer, copy.deepcopy(original), accounting=original)
    assert restored.run.id == run.id and restored.run.paid_calls == run.paid_calls
    assert rows(restored.run) == rows(run)


def test_rows_read_back_through_the_snapshot_transport_are_the_rows_sent():
    """Struct turns every number into a double; the rows (and their digests) do not change."""
    from specimen_digitization.application.storage import digest

    run = priced_run()
    record_model_usage(run, QWEN, "handwriting-qwen", input_tokens=1_000, output_tokens=500)
    record_segmentation(run, "segment", seconds=25.0, instance=INSTANCE)
    stored = run.model_dump(mode="json")
    transported = json_format.MessageToDict(json_format.ParseDict(stored, Struct()))
    assert type(transported["paid_calls"][0]["cost_micros"]) is float
    sent, read = rows(run), rows(transported)
    assert read == sent
    assert [digest(row) for row in read] == [digest(row) for row in sent]
    assert all(type(row["cost_micros"]) is int and type(row["attempt"]) is int for row in read)


@pytest.mark.parametrize("change,code", [
    ({"kind": "allocation"}, "cost_kind_invalid"),
    ({"cost_basis": "allocated"}, "cost_basis_invalid"),
    ({"cost_micros": -1}, "cost_micros_invalid"),
    ({"cost_micros": 1.5}, "cost_micros_invalid"),
    ({"cost_micros": 10**15}, "cost_micros_invalid"),
    ({"cost_micros": "550"}, "cost_micros_invalid"),
    ({"attempt": 0}, "cost_attempt_invalid"),
    ({"at": "yesterday"}, "cost_occurred_at_invalid"),
    ({"at": None}, "cost_occurred_at_invalid"),
    ({"usage": {"input_tokens": "1,000"}}, "cost_usage_not_numeric"),
    ({"usage": {"model": {"name": "label text"}}}, "cost_usage_not_numeric"),
    ({"usage": ["tokens"]}, "cost_usage_not_numeric"),
    ({"route_id": ""}, "cost_resource_invalid"),
    ({"step": "x" * 301}, "cost_step_invalid"),
    ({"failure_code": "f" * 201}, "cost_failure_code_invalid"),
])
def test_a_call_the_ledger_cannot_record_is_refused_with_a_code(change, code):
    run = priced_run()
    record_model_usage(run, QWEN, "handwriting-qwen", input_tokens=1, output_tokens=1)
    run.paid_calls[0].update(change)
    with pytest.raises(CostRowInvalid) as refused:
        rows(run)
    assert str(refused.value) == code


def test_usage_keeps_numbers_booleans_and_nulls_and_times_become_utc():
    run = priced_run()
    record_segmentation(run, "segment", seconds=25.2, instance=dict(INSTANCE, first=True))
    run.paid_calls[0]["at"] = "2026-10-31T21:30:00-05:00"
    [row] = rows(run)
    assert row["usage"] == {"seconds": 25.2, "vcpus": 4, "memory_gib": 8, "instance": dict(INSTANCE, first=True)}
    assert (row["occurred_at"], row["month"]) == ("2026-11-01T02:30:00+00:00", "2026-11")


def test_ids_scope_and_specimen_are_normalized_uuids():
    run = priced_run()
    record_model_usage(run, QWEN, "handwriting-qwen", input_tokens=1, output_tokens=1)
    [row] = paid_call_rows(ORG.upper(), COLLECTION.replace("-", ""), SPECIMEN.upper(), run)
    assert (row["organization_id"], row["collection_id"], row["specimen_id"]) == (ORG, COLLECTION, SPECIMEN)
    assert UUID(row["id"]).version == 5
    with pytest.raises(ValueError):
        paid_call_rows(ORG, COLLECTION, "not-a-specimen", run)


# ---- the GET .../costs body ------------------------------------------------

ROOT, CHILD, GRANDCHILD, OTHER = (f"00000000-0000-4000-8000-00000000{n:04d}" for n in (1, 2, 3, 4))


def group(collection, month="2026-10", stage="reading", kind="model", provider="huggingface",
          resource="handwriting-qwen", basis="computed", cost=0, entries=1, updated="2026-10-20T15:04:05Z"):
    return {"collection_id": collection, "month": month, "stage": stage, "source": "paid_call", "kind": kind,
            "provider": provider, "resource": resource, "cost_basis": basis, "cost_micros": str(cost),
            "list_cost_micros": str(cost), "entries": str(entries), "updated_at": updated}


COLLECTIONS = [
    # As the connector returns them: ids without hyphens.
    {"id": ROOT.replace("-", ""), "name": "Zoology", "parentId": None},
    {"id": CHILD.replace("-", ""), "name": "Insects", "parentId": ROOT.replace("-", "")},
    {"id": GRANDCHILD.replace("-", ""), "name": "Beetles", "parentId": CHILD.replace("-", "")},
    {"id": OTHER.replace("-", ""), "name": "Botany", "parentId": None},
]


def test_totals_roll_up_the_collection_tree_and_split_held_from_spent():
    groups = [
        group(ROOT, cost=10),
        group(CHILD, cost=200, entries=2),
        group(CHILD, stage="label_finding", kind="service", provider="google_cloud", resource="sam3",
              basis="reserved", cost=3_000, updated="2026-10-21T00:00:00Z"),
        group(GRANDCHILD, month="2026-09", cost=40_000),
        group(OTHER, cost=500_000),
    ]
    body = cost_report(ROOT, "2026-09", "2026-10", COLLECTIONS, groups)
    by_name = {item["name"]: item for item in body["collections"]}
    amount = lambda cost, held=0, entries=1: {
        "cost_micros": cost, "held_micros": held, "settled_micros": cost - held, "estimated_micros": 0,
        "list_cost_micros": cost, "entries": entries}
    assert by_name["Beetles"]["own"] == by_name["Beetles"]["total"] == amount(40_000)
    assert by_name["Insects"]["own"] == amount(3_200, 3_000, 3)
    assert by_name["Insects"]["total"] == amount(43_200, 3_000, 4)
    assert by_name["Zoology"]["own"] == amount(10)
    assert by_name["Zoology"]["total"] == amount(43_210, 3_000, 5)
    assert by_name["Botany"]["total"] == amount(500_000)
    assert body["totals"] == amount(543_210, 3_000, 6)
    assert [item["name"] for item in body["collections"]] == ["Beetles", "Botany", "Insects", "Zoology"]
    assert by_name["Insects"]["parent_id"] == ROOT and by_name["Zoology"]["parent_id"] is None
    assert by_name["Insects"]["collection_id"] == CHILD
    assert all(item["cap"] is None for item in body["collections"])
    assert (body["organization_cap"], body["meter"], body["currency"]) == (None, None, "USD")
    assert body["updated_at"] == "2026-10-21T00:00:00Z"
    assert (body["from_month"], body["to_month"]) == ("2026-09", "2026-10")
    september, october = body["months"]
    assert (september["month"], september["totals"]) == ("2026-09", amount(40_000))
    assert october["totals"] == amount(503_210, 3_000, 5)
    assert october["stages"] == [
        {"stage": "label_finding", **amount(3_000, 3_000)},
        {"stage": "reading", **amount(500_210, 0, 4)},
    ]
    assert body["models"] == [
        {"month": "2026-09", "stage": "reading", "provider": "huggingface", "resource": "handwriting-qwen",
         **amount(40_000)},
        {"month": "2026-10", "stage": "label_finding", "provider": "google_cloud", "resource": "sam3",
         **amount(3_000, 3_000)},
        {"month": "2026-10", "stage": "reading", "provider": "huggingface", "resource": "handwriting-qwen",
         **amount(500_210, 0, 4)},
    ]


def test_every_month_of_the_range_is_listed_even_with_nothing_spent():
    body = cost_report(ROOT, "2025-11", "2026-02", COLLECTIONS, [])
    assert [month["month"] for month in body["months"]] == ["2025-11", "2025-12", "2026-01", "2026-02"]
    assert all(month["stages"] == [] for month in body["months"])
    assert body["updated_at"] is None and body["models"] == []
    assert all(item["total"]["entries"] == 0 for item in body["collections"])


def test_sums_above_two_to_the_fifty_three_stay_exact():
    big = 10_999_999_999_999_989
    body = cost_report(ROOT, "2026-10", "2026-10", COLLECTIONS, [group(CHILD, cost=big, entries=11)])
    assert body["totals"]["cost_micros"] == big
    assert {item["name"]: item["total"]["cost_micros"] for item in body["collections"]}["Zoology"] == big


def test_a_cycle_in_the_collection_tree_is_refused():
    cyclic = [dict(item) for item in COLLECTIONS]
    cyclic[0]["parentId"] = GRANDCHILD
    with pytest.raises(ValueError, match="collection_tree_cycle"):
        cost_report(ROOT, "2026-10", "2026-10", cyclic, [])
    alone = [{"id": ROOT, "name": "Loop", "parentId": ROOT}]
    with pytest.raises(ValueError, match="collection_tree_cycle"):
        cost_report(ROOT, "2026-10", "2026-10", alone, [])


def test_rows_of_an_unlisted_collection_still_count_and_a_missing_parent_is_a_root():
    orphan = [{"id": CHILD, "name": "Insects", "parentId": "00000000-0000-4000-8000-00000000ffff"}]
    stray = "00000000-0000-4000-8000-00000000eeee"
    body = cost_report(ROOT, "2026-10", "2026-10", orphan, [group(CHILD, cost=5), group(stray, cost=7)])
    by_id = {item["collection_id"]: item for item in body["collections"]}
    assert by_id[CHILD]["total"]["cost_micros"] == 5
    assert (by_id[stray]["name"], by_id[stray]["total"]["cost_micros"]) == (None, 7)
    assert body["totals"]["cost_micros"] == 12


@pytest.mark.parametrize("months", [("2026-13", "2026-13"), ("2026-1", "2026-01"), ("26-10", "26-10"),
                                    ("2026-11", "2026-10"), ("2024-10", "2026-10"), ("\uff12\uff10\uff12\uff16-10", "2026-10")])
def test_months_are_whole_utc_months_in_order_at_most_twenty_four(months):
    with pytest.raises(ValueError):
        months_between(*months)


def test_twenty_four_months_is_the_longest_range():
    assert len(months_between("2024-11", "2026-10")) == cost_ledger.MAX_MONTHS == 24


def test_a_group_outside_the_range_or_with_a_malformed_sum_is_refused():
    with pytest.raises(ValueError):
        cost_report(ROOT, "2026-10", "2026-10", COLLECTIONS, [group(CHILD, month="2026-09")])
    malformed = dict(group(CHILD), cost_micros="1e3")
    with pytest.raises(ValueError):
        cost_report(ROOT, "2026-10", "2026-10", COLLECTIONS, [malformed])
