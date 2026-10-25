"""The cost meter's true-up of calls whose cost the run could not know (COST_METER.md, "Held and spent").

Every expected amount is worked out by hand from the committed files:
profiles/provider_bills.json (Hugging Face, per UTC day and model) and
profiles/infrastructure_prices.json (Cloud Run instance-based 18 and 2 micro-USD
per vCPU- and GiB-second, so 104 a second at 4 vCPU and 16 GiB).
"""

from __future__ import annotations

import json
from uuid import UUID

import pytest
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Struct

from specimen_digitization.application import cost_ledger
from specimen_digitization.application.cost_ledger import (
    PROVIDER_DAY_MEAN,
    SAM_REQUEST_SECONDS,
    TRUED_UP,
    call_rows,
    cost_report,
    provider_bills,
)
from specimen_digitization.model_gateway import HUGGINGFACE_ROUTES

ORG = "00000000-0000-4000-8000-0000000000a1"
COLLECTION = "00000000-0000-4000-8000-0000000000b2"
SPECIMEN = "00000000-0000-4000-8000-0000000000c3"
RUN = "00000000-0000-4000-8000-0000000000d4"
PRICES = {"version": "pilot-prices-2026-10-17", "as_of": "2026-09-24"}


def call(step, kind, name, *, basis, cost, reserved, at, usage=None, outcome="failed", **extra):
    key = {"model": "route_id", "service": "service", "tool": "tool_id"}[kind]
    return {"step": step, "attempt": 1, "kind": kind, key: name, "reserved_micros": reserved, "usage": usage,
            "outcome": outcome, "cost_micros": cost, "cost_basis": basis, "price_list": PRICES, "at": at, **extra}


def one(paid_call):
    [row] = call_rows(ORG, COLLECTION, SPECIMEN, RUN, [paid_call])
    return row


def test_the_bills_are_tenant_free_days_of_registered_models():
    bills = provider_bills()
    models = {route.model_id for route in HUGGINGFACE_ROUTES.values()}
    for day, cells in bills["huggingface"]["days"].items():
        assert len(day) == 10 and day.startswith("2026-10-")
        assert set(cells) <= models
        assert all(set(cell) == {"requests", "nano_usd"} and cell["requests"] > 0 for cell in cells.values())
    text = json.dumps(bills)
    for word in text.replace('"', " ").replace(",", " ").split():
        with pytest.raises(ValueError):
            UUID(word)  # no organization, collection or specimen id


def test_a_held_model_call_is_trued_up_to_one_request_at_the_day_s_billed_mean():
    # GLM on 2026-10-12: 39,668,880 nano-USD over 64 requests = 619.83 micro-USD a request, rounded up.
    row = one(call("first_pass:region-1", "model", "first-pass-glm", basis="reserved", cost=318_670,
                   reserved=318_670, at="2026-10-12T15:04:05+00:00", failure_code="model_malformed_response"))
    assert (row["cost_basis"], row["cost_micros"], row["list_cost_micros"]) == (TRUED_UP, 620, 620)
    assert row["reserved_micros"] == 318_670, "the reservation stays on the row"
    assert row["allocation_method_id"] == PROVIDER_DAY_MEAN
    assert row["allocation_method_details"] == {
        "original_basis": "reserved", "original_cost_micros": 318_670, "requests": 1, "requests_from": "one request",
        "provider": "huggingface", "bills": provider_bills()["version"], "day": "2026-10-12",
        "model": "zai-org/GLM-5.3-Flash", "billed_requests": 64, "billed_nano_usd": 39_668_880,
        "note": "the call's requests at the provider's billed mean per request for the model that UTC day"}


def test_a_held_call_never_counts_above_its_reservation_and_counts_its_recorded_requests():
    # Field research held with its requests counted: 40 x 218,188,457 / 1,258 nano-USD = 6,937.65 micro-USD.
    deepseek = dict(step="field_research", kind="model", name="harness-deepseek", at="2026-10-18T12:00:00+00:00",
                    usage={"model_calls": 40})
    assert one(call(**deepseek, basis="reserved", cost=1_000_000, reserved=1_000_000))["cost_micros"] == 6_938
    assert one(call(**deepseek, basis="reserved", cost=5_000, reserved=5_000))["cost_micros"] == 5_000


def test_a_call_on_a_day_or_route_the_bills_do_not_cover_stays_held():
    for at, route in (("2026-10-24T12:00:00+00:00", "first-pass-glm"),   # after the bills' last day
                      ("2026-10-04T12:00:00+00:00", "first-pass-glm"),   # GLM billed nothing that day
                      ("2026-10-12T12:00:00+00:00", "harness-nemotron")):  # a model the bills do not hold
        row = one(call("first_pass:region-1", "model", route, basis="reserved", cost=9_000, reserved=9_000, at=at))
        assert (row["cost_basis"], row["cost_micros"]) == ("reserved", 9_000)
        assert (row["allocation_method_id"], row["allocation_method_details"]) == (None, None)


def test_a_legacy_held_parse_call_is_matched_to_the_route_parse_calls_and_trued_up():
    # Before 2026-10-25 a held parse call named its step as its route. Qwen on 2026-10-12:
    # 32,629,000 nano-USD over 107 requests = 304.94 micro-USD, rounded up.
    row = one(call("parse", "model", "parse", basis="reserved", cost=53_568, reserved=53_568,
                   at="2026-10-12T16:00:00+00:00", outcome="completed"))
    assert (row["resource"], row["stage"], row["provider"]) == ("handwriting-qwen", "structuring", "huggingface")
    assert (row["cost_basis"], row["cost_micros"]) == (TRUED_UP, 305)
    assert row["allocation_method_details"]["model"] == "Qwen/Qwen3-VL-30B-A3B-Instruct"
    # Another step's route is never renamed.
    assert one(call("classify", "model", "classify", basis="reserved", cost=1, reserved=1,
                    at="2026-10-24T00:00:00+00:00"))["resource"] == "classify"


def test_a_settled_cached_input_route_call_without_cached_tokens_is_trued_up_to_the_bill():
    # DeepSeek on 2026-10-18 was billed 14.8% of list (cached input). 40 requests: 6,938 micro-USD.
    listed = call("field_research", "model", "harness-deepseek", basis="computed", cost=46_996, reserved=1_000_000,
                  at="2026-10-18T12:00:00+00:00", usage={"model_calls": 40}, outcome="completed")
    row = one(listed)
    assert (row["cost_basis"], row["cost_micros"]) == (TRUED_UP, 6_938)
    assert row["allocation_method_details"]["original_basis"] == "computed"
    assert row["allocation_method_details"]["original_cost_micros"] == 46_996
    # A call that recorded its cached tokens was priced at the cached rate: kept as it is.
    cached = one(dict(listed, usage={"model_calls": 40, "input_tokens": 400_000, "cached_input_tokens": 360_000,
                                     "output_tokens": 8_000, "reported_requests": 40}))
    assert (cached["cost_basis"], cached["cost_micros"]) == ("computed", 46_996)
    # Never above what it was settled at, and a route billed at list is left alone.
    assert one(dict(listed, cost_micros=5_000))["cost_micros"] == 5_000
    qwen = one(call("transcribe:region-1:handwriting-qwen", "model", "handwriting-qwen", basis="computed", cost=550,
                    reserved=9_000, at="2026-10-12T12:00:00+00:00", usage={"model_calls": 1}, outcome="completed"))
    assert (qwen["cost_basis"], qwen["cost_micros"]) == ("computed", 550)


def test_a_held_sam_call_that_reported_its_seconds_settles_at_them_and_one_without_stays_held():
    # 132.5 s x (4 x 18 + 16 x 2) = 13,780 micro-USD, against a 182,321 reservation.
    usage = {"seconds": 132.5, "vcpus": 4, "memory_gib": 16}
    row = one(call("segment", "service", "sam3", basis="reserved", cost=182_321, reserved=182_321,
                   at="2026-10-12T12:00:00+00:00", usage=usage, outcome="completed"))
    assert (row["cost_basis"], row["cost_micros"], row["reserved_micros"]) == (TRUED_UP, 13_780, 182_321)
    assert row["allocation_method_id"] == SAM_REQUEST_SECONDS
    details = row["allocation_method_details"]
    assert (details["request_seconds"], details["rate_micros_per_second"], details["rates"]) == (
        132.5, "104", "infrastructure-prices-2026-10-20")
    assert "specimen-sam allocation's residual" in details["note"]
    # A failed call, or one with no seconds, has nothing to settle at.
    for outcome, used in (("failed", usage), ("completed", None)):
        held = one(call("segment", "service", "sam3", basis="reserved", cost=182_321, reserved=182_321,
                        at="2026-10-12T12:00:00+00:00", usage=used, outcome=outcome))
        assert (held["cost_basis"], held["cost_micros"]) == ("reserved", 182_321)


def test_a_trued_up_row_is_the_same_after_the_snapshot_s_transport():
    # The sweep reads calls back through protobuf Struct, where every number is a float.
    paid = [call("field_research", "model", "harness-deepseek", basis="reserved", cost=1_000_000, reserved=1_000_000,
                 at="2026-10-18T12:00:00+00:00", usage={"model_calls": 40}),
            call("segment", "service", "sam3", basis="reserved", cost=182_321, reserved=182_321,
                 at="2026-10-12T12:00:00+00:00", usage={"seconds": 132.5, "vcpus": 4, "memory_gib": 16},
                 outcome="completed")]
    struct = Struct()
    struct.update({"calls": paid})
    carried = json_format.MessageToDict(struct)["calls"]
    assert carried[0]["usage"]["model_calls"] == 40.0 and type(carried[0]["reserved_micros"]) is float
    assert call_rows(ORG, COLLECTION, SPECIMEN, RUN, carried) == call_rows(ORG, COLLECTION, SPECIMEN, RUN, paid)


def test_the_report_separates_settled_held_and_estimated():
    group = lambda basis, cost: {"collection_id": COLLECTION, "month": "2026-10", "stage": "reading",  # noqa: E731
                                 "source": "paid_call", "kind": "model", "provider": "huggingface",
                                 "resource": "handwriting-qwen", "cost_basis": basis, "cost_micros": str(cost),
                                 "list_cost_micros": str(cost), "entries": "1", "updated_at": None}
    body = cost_report(ORG, "2026-10", "2026-10", [{"id": COLLECTION, "name": "Insects", "parentId": None}],
                       [group("computed", 550), group("reserved", 9_000), group(TRUED_UP, 305)])
    assert body["totals"] == {"cost_micros": 9_855, "held_micros": 9_000, "settled_micros": 855,
                              "estimated_micros": 305, "list_cost_micros": 9_855, "entries": 3}
    assert body["models"][0]["settled_micros"] == 855


def test_the_rules_version_names_the_rules_and_the_bills():
    assert cost_ledger.rules_version() == f"{cost_ledger.RULES}/{provider_bills()['version']}"
