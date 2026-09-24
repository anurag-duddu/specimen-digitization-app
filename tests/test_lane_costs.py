"""The cost of every paid call (docs/execution/golive/LANE.md, T2c; G9)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
    create_app,
)
from specimen_digitization.application.collection_profiles import (
    PriceList,
    published_registry,
)
from specimen_digitization.application.domain import (
    LookupStatus,
    Principal,
    Profile,
    Run,
    Scope,
)
from specimen_digitization.application.lane import queue
from specimen_digitization.application.lane_allowance import (
    LEDGER_KIND,
    ProgramLedger,
    reserve_step,
)
from specimen_digitization.application.lane_costs import (
    record_model_usage,
    record_segmentation,
    record_tool_usage,
    segmentation_cost,
    settle_step,
)
from specimen_digitization.application.profile_runtime import published_risk_registry
from specimen_digitization.application.reliability import AdapterFailure
from specimen_digitization.application.storage import LocalBlobs

from test_lane_drain import NonSensitiveMember
from test_lane_profile import USER, ProductionLikeAdapters
from test_lane_trigger import STAGE_COSTS, RecordingDispatcher, intake, specimen_with

SCOPE = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
PRICES = PriceList(
    version="lane-test-prices-1",
    as_of="2026-09-23",
    sources=("https://prices.example.test/list",),
    models={
        "handwriting-qwen": {
            "input_micros_per_million": 200_000,
            "output_micros_per_million": 700_000,
        },
        "handwriting-muse": {
            "input_micros_per_million": 300_000,
            "output_micros_per_million": 1_200_000,
        },
    },
    segmentation={
        "vcpus": 4,
        "memory_gib": 8,
        "vcpu_micros_per_million_seconds": 24_000_000,
        "gib_micros_per_million_seconds": 2_500_000,
        "request_micros_per_million": 400_000,
    },
    tools={"geography_lookup": 5_000},
)
QWEN = "transcribe:region-1:handwriting-qwen"


def priced_run(prices=PRICES):
    run = Run(profile=Profile(synthetic=False))
    run.profile.execution = run.profile.execution.model_copy(
        update={
            "price_list": prices.model_dump(mode="json") if prices else None,
            "stage_cost_reservations": STAGE_COSTS,
        }
    )
    return run


def priced_registry(prices=PRICES):
    registry = published_registry({SYNTHETIC_COLLECTION: "insects"})
    profiles = tuple(
        profile.model_copy(
            update={
                "processing": profile.processing.model_copy(
                    update={"price_list": prices}
                )
            }
        )
        if profile.processing
        else profile
        for profile in registry.profiles
    )
    return registry.model_copy(update={"profiles": profiles})


def test_a_model_call_costs_its_tokens_at_the_route_price():
    run = priced_run()
    run.attempts[QWEN] = 1
    record_model_usage(
        run, QWEN, "handwriting-qwen", input_tokens=1_000, output_tokens=500
    )
    [call] = run.paid_calls
    # 1,000 x 0.20 + 500 x 0.70 USD per million tokens = 550 micro-dollars.
    assert call["cost_micros"] == 550
    assert call["cost_basis"] == "computed"
    assert (call["kind"], call["route_id"]) == ("model", "handwriting-qwen")
    assert call["usage"] == {"input_tokens": 1_000, "output_tokens": 500}
    assert (call["step"], call["attempt"], call["reserved_micros"]) == (QWEN, 1, 2_000)
    assert call["outcome"] == "completed"
    assert call["price_list"] == {"version": "lane-test-prices-1", "as_of": "2026-09-23"}
    assert run.usage.actual_cost_micros == 550


def test_sam3_costs_its_measured_seconds_at_the_service_size():
    run = priced_run()
    record_segmentation(run, "segment", seconds=25.2)
    [call] = run.paid_calls
    # 25.2 s x (4 vCPU x 24 + 8 GiB x 2.5) micro-dollars a second, plus one
    # request at 0.4: 2,923.6, rounded up.
    assert call["cost_micros"] == 2_924
    assert (call["kind"], call["service"]) == ("service", "sam3")
    assert call["usage"] == {"seconds": 25.2, "vcpus": 4, "memory_gib": 8}
    assert run.usage.actual_cost_micros == 2_924


def test_a_tool_call_costs_per_request():
    run = priced_run()
    record_tool_usage(run, "parse", "geography_lookup", requests=3)
    [call] = run.paid_calls
    assert (call["kind"], call["tool_id"], call["cost_micros"]) == (
        "tool",
        "geography_lookup",
        15_000,
    )
    assert call["usage"] == {"requests": 3}


def test_a_billed_amount_is_recorded_instead_of_the_computed_one():
    run = priced_run()
    record_model_usage(
        run, QWEN, "handwriting-qwen", input_tokens=1_000, output_tokens=500,
        billed_micros=321,
    )
    [call] = run.paid_calls
    assert (call["cost_micros"], call["cost_basis"]) == (321, "billed")
    assert run.usage.actual_cost_micros == 321


def test_a_call_without_a_price_is_a_configuration_error():
    run = priced_run()
    with pytest.raises(ValueError, match="No price for tool unlisted_tool"):
        record_tool_usage(run, "parse", "unlisted_tool", requests=1)
    assert run.paid_calls == []


def test_a_settled_cost_above_its_reservation_counts_in_full(tmp_path):
    repository = NonSensitiveMember(tmp_path / "state.sqlite3")
    run = priced_run()
    run.profile.execution = run.profile.execution.model_copy(
        update={
            "program_allowance_micros": 5_000_000,
            "program_ledger_collection": SYNTHETIC_COLLECTION,
        }
    )
    specimen = specimen_with(run)
    principal = Principal(user_id=USER, scope=SCOPE, role="reviewer")
    assert reserve_step(repository, principal, specimen, QWEN, 2_000) is None
    run.attempts[QWEN] = 1
    record_model_usage(
        run, QWEN, "handwriting-qwen", input_tokens=1, output_tokens=1,
        billed_micros=3_500,
    )
    settle_step(repository, principal, specimen, QWEN, 2_000)
    assert ProgramLedger(repository, SCOPE).read()["reserved_total_micros"] == 3_500


def test_a_run_without_a_price_list_records_nothing():
    run = priced_run(prices=None)
    record_model_usage(run, QWEN, "handwriting-qwen", input_tokens=1, output_tokens=1)
    assert run.paid_calls == []
    assert run.usage.actual_cost_micros is None


def test_the_price_list_prices_every_route_the_profile_names():
    unpriced = PRICES.model_copy(
        update={"models": {"handwriting-qwen": PRICES.models["handwriting-qwen"]}}
    )
    with pytest.raises(ValueError, match="price"):
        priced_registry(unpriced).model_validate(
            priced_registry(unpriced).model_dump(mode="json")
        )


def test_a_request_copies_the_price_list():
    specimen = specimen_with(Run(profile=Profile(synthetic=False)))
    queue(specimen, priced_registry(), USER)
    assert specimen.run.profile.execution.price_list == PRICES.model_dump(mode="json")


class TokenAdapters(ProductionLikeAdapters):
    """Readers that report their tokens, as the production readers do."""

    def __init__(self, *args):
        super().__init__(*args)
        self.busy = self.unknown = 0

    def segment(self, specimen):
        if self.unknown:
            self.unknown -= 1
            raise AdapterFailure(
                "sam3_timeout", LookupStatus.TIMEOUT, outcome_unknown=True
            )
        if self.busy:
            self.busy -= 1
            raise AdapterFailure("sam3_busy", LookupStatus.RATE_LIMITED)
        return super().segment(specimen)

    def transcribe(self, specimen, region, route):
        observation = super().transcribe(specimen, region, route)
        return observation.model_copy(update={"input_tokens": 1_000, "output_tokens": 500})


def lab(tmp_path, busy=0, unknown=0):
    blobs = LocalBlobs(tmp_path / "blobs")
    adapters = TokenAdapters(blobs, SYNTHETIC_TEXT)
    adapters.busy, adapters.unknown = busy, unknown
    app = create_app(
        mode="emulator",
        repository=NonSensitiveMember(tmp_path / "state.sqlite3"),
        blobs=blobs,
        adapters=adapters,
        identity_verifier=lambda token, check: USER,
        memberships=lambda user: [
            {
                "organization_id": SYNTHETIC_ORG,
                "collection_id": SYNTHETIC_COLLECTION,
                "role": "reviewer",
                "can_view_sensitive": True,
            }
        ],
        profile_registry=priced_registry(),
        risk_registry=published_risk_registry(),
        worker_dispatcher=RecordingDispatcher(),
    )
    principal = Principal(user_id=USER, scope=SCOPE, role="reviewer")
    return app, principal, intake(TestClient(app, raise_server_exceptions=False))


def test_the_workflow_records_every_reading_and_segmentation(tmp_path):
    app, principal, row = lab(tmp_path)
    run = app.state.workflow.drain(principal, row["specimen_id"]).run
    assert "parse" in run.completed_steps, run.blocker
    by_step = {call["step"]: call for call in run.paid_calls}
    assert by_step["segment"]["kind"] == "service"
    assert by_step["segment"]["outcome"] == "completed"
    assert by_step["segment"]["cost_micros"] >= 1  # At least the request.
    readings = [call for call in run.paid_calls if call["kind"] == "model"]
    assert sorted(call["route_id"] for call in readings) == [
        "handwriting-muse",
        "handwriting-qwen",
    ]
    assert {call["route_id"]: call["cost_micros"] for call in readings} == {
        "handwriting-qwen": 550,
        "handwriting-muse": 900,
    }
    assert run.usage.actual_cost_micros == sum(c["cost_micros"] for c in run.paid_calls)


def test_a_failed_call_is_recorded_with_its_attempt(tmp_path):
    app, principal, row = lab(tmp_path, busy=1)
    workflow = app.state.workflow
    run = workflow.drain(principal, row["specimen_id"]).run
    assert run.stage == "retry_scheduled"
    workflow.clock = lambda: datetime.now(timezone.utc) + timedelta(hours=1)
    run = workflow.drain(principal, row["specimen_id"]).run
    segments = [call for call in run.paid_calls if call["step"] == "segment"]
    assert [(c["attempt"], c["outcome"], c["cost_basis"]) for c in segments] == [
        (1, "failed", "reserved"),
        (2, "completed", "computed"),
    ]
    # SAM 3's busy answer reported no usage, so it stays reserved at its full
    # amount; the calls that reported usage settle to what they cost.
    assert segments[0]["cost_micros"] == 45_000
    completed = sum(c["cost_micros"] for c in run.paid_calls if c["outcome"] == "completed")
    assert ledger_total(app) == 45_000 + completed


def ledger_total(app):
    return ProgramLedger(app.state.workflow.repository, SCOPE).read()[
        "reserved_total_micros"
    ]


def test_a_settled_step_gives_back_the_rest_of_its_reservation(tmp_path):
    app, principal, row = lab(tmp_path)
    run = app.state.workflow.drain(principal, row["specimen_id"]).run
    assert "parse" in run.completed_steps, run.blocker
    # SAM 3 and two readings reserved 45,000 + 2 x 20,000, then settled to
    # what their calls cost.
    assert run.usage.reserved_cost_micros == 85_000
    assert ledger_total(app) == run.usage.actual_cost_micros < 85_000
    assert run.program_allowance["reserved_total_micros"] == ledger_total(app)


def test_an_unknown_outcome_stays_fully_reserved(tmp_path):
    app, principal, row = lab(tmp_path, unknown=1)
    run = app.state.workflow.drain(principal, row["specimen_id"]).run
    assert run.blocker == "external_outcome_unknown"
    [call] = run.paid_calls
    assert (call["step"], call["outcome"]) == ("segment", "unknown")
    assert (call["cost_micros"], call["cost_basis"], call["usage"]) == (45_000, "reserved", None)
    assert ledger_total(app) == 45_000


def test_a_call_that_would_cross_the_cap_is_refused_however_little_was_spent(
    tmp_path,
):
    app, principal, row = lab(tmp_path)
    repository = app.state.workflow.repository
    # Earlier runs settled at 4,980,000: 20,000 of the allowance is left, less
    # than SAM 3's 45,000 reservation.
    repository.put_document(
        SCOPE,
        LEDGER_KIND,
        ProgramLedger(repository, SCOPE).ident,
        {"sensitive": False, "reserved_total_micros": 4_980_000},
        0,
    )
    run = app.state.workflow.drain(principal, row["specimen_id"]).run
    assert (run.stage, run.blocker) == ("processing_blocked", "program_allowance_exhausted")
    assert run.paid_calls == []
    assert ledger_total(app) == 4_980_000


def test_a_step_without_recorded_calls_stays_reserved(tmp_path):
    repository = NonSensitiveMember(tmp_path / "state.sqlite3")
    run = priced_run()
    run.profile.execution = run.profile.execution.model_copy(
        update={
            "program_allowance_micros": 5_000_000,
            "program_ledger_collection": SYNTHETIC_COLLECTION,
        }
    )
    specimen = specimen_with(run)
    principal = Principal(user_id=USER, scope=SCOPE, role="reviewer")
    assert reserve_step(repository, principal, specimen, "parse", 20_000) is None
    run.attempts["parse"] = 1
    run.completed_steps.append("parse")
    # Nobody recorded the step's calls, so nothing is given back.
    settle_step(repository, principal, specimen, "parse", 20_000)
    assert ProgramLedger(repository, SCOPE).read()["reserved_total_micros"] == 20_000


def test_the_pilot_pins_the_prices_read_on_2026_09_23():
    prices = published_registry().resolve("insects").profile.processing.price_list
    assert (prices.version, prices.as_of) == ("pilot-prices-2026-09-23", "2026-09-23")
    assert prices.models["handwriting-qwen"].model_dump() == {
        "input_micros_per_million": 200_000,
        "output_micros_per_million": 700_000,
    }
    assert prices.models["handwriting-muse"].model_dump() == {
        "input_micros_per_million": 300_000,
        "output_micros_per_million": 1_200_000,
    }
    assert prices.tools == {"geography_lookup": 5_000}
    # SAM 3 on 4 vCPU and 16 GiB: 136 micro-dollars a second. One call is billed
    # at most its 300 s request timeout, cold start included, plus 10 s of
    # shutdown, inside the pilot's 45,000 segment reservation.
    worst = segmentation_cost(prices.model_dump(mode="json"), 310)
    assert worst == 42_161
    assert worst <= published_registry().resolve("insects").profile.processing.stage_cost_micros.for_step("segment")
