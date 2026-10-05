"""The pilot's first-pass route reaches its step (docs/execution/golive/HARNESS.md 3).

`classify` sets the run's profile from the published one, and the workflow
pins the dependencies again after it, so the route `classify` keeps is the one
pinned for the first pass. Readings that differ then reach the first pass with
its reservation instead of blocking as `approved_cost_budget_unavailable`.

The first pass retains its payload guard, while financial qualification in
bbd6e620 reserves both requests at the whole provider context. Unknown calls
remain fully held; successful calls settle to reported usage. The current
held-plus-settled liability must stay inside the USD 1 run limit, including
each new request's reservation before dispatch.
"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
    create_app,
)
from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import (
    LookupStatus,
    Principal,
    Region,
    Scope,
)
from specimen_digitization.application.first_pass import synthetic_decision
from specimen_digitization.application.lane_reservations import (
    call_micros,
    step_reservation,
)
from specimen_digitization.application.production import ProductionAdapters
from specimen_digitization.application.profile_runtime import published_risk_registry
from specimen_digitization.application.reliability import AdapterFailure
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.model_gateway import STAGE_HUGGINGFACE_ROUTES

from test_lane_costs import seed_synthetic_ledger
from test_lane_drain import NonSensitiveMember
from test_lane_profile import USER, ProductionLikeAdapters
from test_lane_reservations import with_models
from test_lane_trigger import RecordingDispatcher, intake

SCOPE = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
GLM = {"model_id": "zai-org/GLM-5.3-Flash", "provider": "deepinfra"}
# The configured payload estimate would price each request at 6,964 microUSD.
# That estimate is not a qualified provider-token liability bound.
BOUNDED_CALL = 2 * 6_964
FIRST_PASS_RESERVATION = 318_670
# Two full-context requests: ceil((1,048,576 x 0.15) + (4,096 x 0.50)).
CONTEXT_RESERVATION = 2 * 159_335
# SAM's complete startup/request/shutdown liability and the first reader's
# two full-context extraction requests, independently priced from the profile.
SAM_RESERVATION = 182_321
PARSE_RESERVATION = 58_164
# The published profile's per-run limit, which `queue` copies into each run.
RUN_CAP = published_registry().resolve("insects").profile.processing.run_cost_limit_micros
UNBOUNDED = {"first-pass-glm": {"max_input_tokens": None, "max_output_tokens": None}}
# The same route with a 2,097,152-token context and no bound: each request
# reserves ceil((2,097,152 x 0.15 + 4,096 x 0.50) million micro-dollars) = 316,621.
LONG_CONTEXT = {"first-pass-glm": {**UNBOUNDED["first-pass-glm"], "context_tokens": 2_097_152}}
LONG_CONTEXT_RESERVATION = 2 * 316_621


def test_the_pilot_names_a_registered_first_pass_route_priced_and_reserved():
    profile = published_registry().resolve("insects").profile
    assert profile.first_pass_route == "first-pass-glm"
    route = STAGE_HUGGINGFACE_ROUTES[profile.first_pass_route]
    assert {"model_id": route.model_id, "provider": route.provider} == GLM
    processing = profile.processing
    assert processing.stage_cost_micros.for_step("first_pass:region-1") == 20_000
    assert processing.price_list.models["first-pass-glm"].model_dump() == {
        "input_micros_per_million": 150_000,
        "output_micros_per_million": 500_000,
        "context_tokens": 1_048_576,
        "max_input_tokens": 32_768,
        "max_output_tokens": 4_096,
    }


def first_pass_run(registry=None):
    from test_lane_reservations import reading

    run, _ = reading(600, 400, registry)
    run.profile = run.profile.model_copy(update={"first_pass_route": "first-pass-glm"})
    return run, "first_pass:" + run.regions[0].id


def test_the_first_pass_reserves_full_context_despite_its_payload_bound():
    run, step = first_pass_run()
    price = run.profile.execution.price_list["models"]["first-pass-glm"]
    assert call_micros(price, None) == BOUNDED_CALL
    assert price["max_input_tokens"] == 32_768
    assert step_reservation(run, step) == FIRST_PASS_RESERVATION
    # Removing the payload bound cannot reduce the full-context liability.
    unbounded = with_models(
        published_registry({SYNTHETIC_COLLECTION: "insects"}), **UNBOUNDED
    )
    assert step_reservation(*first_pass_run(unbounded)) == CONTEXT_RESERVATION


class DisagreeingReaders(ProductionLikeAdapters):
    """Production's pins, two readings that differ in every region, and a first
    pass that records the pin and the reservation it was called with; its first
    `fail` calls are rate limited."""

    classifier = None  # Read by production's pin_dependencies.
    pin_dependencies = ProductionAdapters.pin_dependencies

    def __init__(self, blobs, fail=0, regions=1):
        super().__init__(blobs, SYNTHETIC_TEXT, SYNTHETIC_TEXT + " 1946")
        self.fail, self.regions = int(fail), regions
        self.pins, self.reserved, self.exposure = [], [], []

    def segment(self, specimen):
        if self.regions == 1:
            return super().segment(specimen)
        # Four quadrants of the 120 x 80 slide.
        width, height = specimen.asset.width // 2, specimen.asset.height // 2
        return [
            Region(
                asset_id=specimen.asset.id,
                x=width * (order % 2),
                y=height * (order // 2),
                width=width,
                height=height,
                order=order,
                method="lab_fixture_region",
                version="1",
            )
            for order in range(self.regions)
        ]

    def first_pass(self, specimen, region, readings):
        run = specimen.run
        route = run.profile.first_pass_route
        self.pins.append(run.dependencies["routes"].get(route))
        self.reserved.append(
            (run.blocker, step_reservation(run, "first_pass:" + region.id))
        )
        self.exposure.append(run.usage.reserved_cost_micros)
        if self.fail:
            self.fail -= 1
            raise AdapterFailure("first_pass_rate_limited", LookupStatus.RATE_LIMITED)
        decision = synthetic_decision(self.blobs, region, readings)
        call = decision.call.model_copy(
            update={"route_id": route, **GLM, "input_tokens": 1_200, "output_tokens": 300}
        )
        return decision.model_copy(update={"call": call})


def start(tmp_path, adapters, registry=None):
    repository = NonSensitiveMember(tmp_path / "state.sqlite3")
    seed_synthetic_ledger(repository, reserved_total_micros=0)
    app = create_app(
        mode="emulator",
        repository=repository,
        blobs=adapters.blobs,
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
        profile_registry=registry
        or published_registry({SYNTHETIC_COLLECTION: "insects"}),
        risk_registry=published_risk_registry(),
        worker_dispatcher=RecordingDispatcher(),
    )
    principal = Principal(user_id=USER, scope=SCOPE, role="reviewer")
    ident = intake(TestClient(app, raise_server_exceptions=False))["specimen_id"]
    return app.state.workflow, principal, ident


def drain(tmp_path, fail=False):
    adapters = DisagreeingReaders(LocalBlobs(tmp_path / "blobs"), fail)
    workflow, principal, ident = start(tmp_path, adapters)
    run = workflow.drain(principal, ident).run
    calls = [c for c in run.paid_calls if c["step"].startswith("first_pass:")]
    return run, adapters, calls


def test_differing_readings_reach_the_first_pass_with_its_reservation(tmp_path):
    run, adapters, calls = drain(tmp_path)
    assert run.blocker != "approved_cost_budget_unavailable"
    # Called once, on the pinned route, after its intent and reservation were saved.
    assert adapters.pins == [GLM], run.blocker
    assert adapters.reserved == [("external_outcome_unknown", FIRST_PASS_RESERVATION)]
    assert any(step.startswith("first_pass:") for step in run.completed_steps)
    # 1,200 input and 300 output tokens at 0.15 and 0.50 dollars a million.
    [call] = calls
    assert (call["route_id"], call["cost_basis"], call["cost_micros"]) == (
        "first-pass-glm",
        "computed",
        330,
    )


def test_a_first_pass_that_reported_nothing_stays_reserved(tmp_path):
    run, adapters, calls = drain(tmp_path, fail=True)
    assert adapters.pins == [GLM], run.blocker
    [call] = calls
    assert (
        call["route_id"],
        call["outcome"],
        call["cost_basis"],
        call["cost_micros"],
    ) == ("first-pass-glm", "failed", "reserved", FIRST_PASS_RESERVATION)
    assert run.usage.reserved_cost_micros == SAM_RESERVATION + FIRST_PASS_RESERVATION == 500_991
    assert run.usage.actual_cost_micros is None


def four_regions_and_a_retried_first_pass(tmp_path, registry=None):
    """Four regions whose readings differ; the first first pass is rate limited
    once, then retried an hour later, as the workflow schedules it."""
    adapters = DisagreeingReaders(LocalBlobs(tmp_path / "blobs"), fail=1, regions=4)
    workflow, principal, ident = start(tmp_path, adapters, registry)
    run = workflow.drain(principal, ident).run
    assert run.stage == "retry_scheduled", run.blocker
    workflow.clock = lambda: datetime.now(timezone.utc) + timedelta(hours=1)
    return workflow.drain(principal, ident).run, adapters


def test_four_disagreeing_regions_and_a_retried_first_pass_fit_the_run_cap(tmp_path):
    run, adapters = four_regions_and_a_retried_first_pass(tmp_path)
    steps = [f"first_pass:{region.id}" for region in run.regions]
    assert len(steps) == 4 and set(steps) <= set(run.completed_steps), run.blocker
    assert {"adjudicate", "parse"} <= set(run.completed_steps), run.blocker
    assert run.stage == "finalized"
    # Five first passes: the failed one, its retry, and the other three regions.
    assert [run.attempts[step] for step in steps] == [2, 1, 1, 1]
    assert adapters.reserved == [("external_outcome_unknown", FIRST_PASS_RESERVATION)] * 5
    first_passes = [c for c in run.paid_calls if c["step"].startswith("first_pass:")]
    assert [(c["outcome"], c["cost_basis"]) for c in first_passes] == [
        ("failed", "reserved")
    ] + [("completed", "computed")] * 4
    # Historical reservations include amounts later settled; only the current
    # held-plus-settled liability is tested against the cap at the next dispatch.
    reserved = {(c["step"], c["attempt"]): c["reserved_micros"] for c in run.paid_calls}
    assert reserved[("segment", 1)] == SAM_RESERVATION
    assert sum(r for (step, _), r in reserved.items() if step in steps) == 1_593_350
    assert sum(reserved.values()) == 1_935_671
    assert adapters.exposure == [500_991, 819_661, 819_991, 820_321, 820_651]
    assert max(adapters.exposure) < RUN_CAP == 1_000_000
    # SAM has no billing receipt and the failed model call reported no usage;
    # both remain fully held even after later first passes settle at 330 each.
    held = sum(c["cost_micros"] for c in run.paid_calls if c["cost_basis"] == "reserved")
    assert held == SAM_RESERVATION + FIRST_PASS_RESERVATION == 500_991
    spent = sum(c["cost_micros"] for c in run.paid_calls if c["cost_basis"] == "computed")
    assert spent == 1_320
    assert run.usage.reserved_cost_micros == held + spent == 502_311
    assert run.usage.actual_cost_micros is None
    # This emulator's parse makes no paid call. A subsequent production parse
    # must still reserve its complete two-request liability before dispatch.
    assert step_reservation(run, "parse") == PARSE_RESERVATION
    assert run.usage.reserved_cost_micros + PARSE_RESERVATION == 560_475 <= RUN_CAP


def test_removing_the_payload_bound_keeps_the_full_context_retry_liability(tmp_path):
    # The failed call holds 318,670 and its retry needs as much again. Removing
    # the payload bound leaves those liabilities and the USD 1 limit intact.
    assert RUN_CAP == 1_000_000 > 2 * CONTEXT_RESERVATION
    registry = with_models(
        published_registry({SYNTHETIC_COLLECTION: "insects"}), **UNBOUNDED
    )
    run, adapters = four_regions_and_a_retried_first_pass(tmp_path, registry)
    assert run.blocker != "cost_budget_exhausted"
    assert adapters.reserved[:2] == [("external_outcome_unknown", CONTEXT_RESERVATION)] * 2


def test_the_run_limit_blocks_a_retry_whose_reservation_would_cross_it(tmp_path):
    # The same hazard at the limit USD 1 sets: a first-pass route with a
    # 2,097,152-token context and no request bound reserves its whole context on
    # both requests, 633,242 a call. The first call fits under the limit; it fails
    # and holds that, and its retry needs as much again, past the run's limit.
    assert LONG_CONTEXT_RESERVATION < RUN_CAP < 2 * LONG_CONTEXT_RESERVATION
    registry = with_models(
        published_registry({SYNTHETIC_COLLECTION: "insects"}), **LONG_CONTEXT
    )
    run, adapters = four_regions_and_a_retried_first_pass(tmp_path, registry)
    assert run.blocker == "cost_budget_exhausted"
    assert adapters.reserved == [("external_outcome_unknown", LONG_CONTEXT_RESERVATION)]
    assert not any(step.startswith("first_pass:") for step in run.completed_steps)
    assert run.usage.reserved_cost_micros == SAM_RESERVATION + LONG_CONTEXT_RESERVATION == 815_563
    assert run.usage.actual_cost_micros is None
    assert run.usage.reserved_cost_micros + LONG_CONTEXT_RESERVATION > RUN_CAP
