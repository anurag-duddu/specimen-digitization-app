"""Actual unknown-cost aggregation, offline and no ledger authority claim."""
import pytest
from test_lane_costs import priced_run, QWEN
from specimen_digitization.application.lane_costs import record_reserved, record_model_usage, settle_step


def measured(run):
    record_model_usage(run, QWEN, "handwriting-qwen", input_tokens=1000, output_tokens=500)


def unknown(run):
    record_reserved(run, "segment", "service", outcome="unknown", service="sam3")


@pytest.mark.parametrize("order", [("unknown",), ("known", "unknown"), ("unknown", "known")])
def test_any_retained_unknown_call_keeps_total_unknown_and_full_hold(order):
    run = priced_run()
    run.usage.reserved_cost_micros = 45000
    for kind in order:
        measured(run) if kind == "known" else unknown(run)
    assert run.usage.actual_cost_micros is None
    assert run.usage.reserved_cost_micros == 45000
    held = [call for call in run.paid_calls if call["cost_basis"] == "reserved"]
    assert len(held) == 1 and held[0]["usage"] is None and held[0]["outcome"] == "unknown"
    assert held[0]["reserved_micros"] > 0


def test_all_known_usage_still_records_actual_total():
    run = priced_run()
    measured(run)
    measured(run)
    assert run.usage.actual_cost_micros == 1100


def test_unknown_step_does_not_settle_or_touch_repository():
    from types import SimpleNamespace
    run = priced_run()
    unknown(run)
    run.usage.reserved_cost_micros = 45000
    class NoWrite:
        def __getattr__(self, name):
            raise AssertionError("unknown step must retain reservation without repository calls")
    settle_step(NoWrite(), None, SimpleNamespace(run=run), "segment", 45000)
    assert run.usage.reserved_cost_micros == 45000
    assert run.usage.actual_cost_micros is None
