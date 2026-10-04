"""The pilot's first-pass route reaches its step (docs/execution/golive/HARNESS.md 3).

`classify` sets the run's profile from the published one, and the workflow
pins the dependencies again after it, so the route `classify` keeps is the one
pinned for the first pass. Readings that differ then reach the first pass with
its reservation instead of blocking as `approved_cost_budget_unavailable`.

The first pass's request is bounded (the coordinator, 2026-10-03): each request
reserves its input bound, not the route's 1,048,576-token context, so a retried
first pass still fits the run's limit (USD 1 since the owner's ruling of
2026-10-03, 500,000 micro-dollars before it).
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
# Each of the call's two requests at its bound, 32,768 in and 4,096 out at 0.15
# and 0.50 dollars a million: 6,964 micro-dollars, so the call's 13,928 is under
# the stage's 20,000 floor, and the floor is the reservation.
BOUNDED_CALL = 2 * 6_964
FIRST_PASS_RESERVATION = 20_000
# Before the bound, PLAN 4.3 (a) on the context: 1,048,576 in and 4,096 out.
CONTEXT_RESERVATION = 2 * 159_335
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


def test_the_first_pass_reserves_its_request_bound_not_its_routes_context():
    run, step = first_pass_run()
    price = run.profile.execution.price_list["models"]["first-pass-glm"]
    assert call_micros(price, None) == BOUNDED_CALL
    assert step_reservation(run, step) == FIRST_PASS_RESERVATION
    # The pre-bound price reserved the route's whole context on both requests.
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
        self.pins, self.reserved = [], []

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
    # Every paid attempt's reservation, as if none had settled, fits the cap:
    # 45,000 for SAM 3, 8 x 20,000 for the readings, 5 x 20,000 for the first
    # passes (this emulator's parse makes no paid call).
    reserved = {(c["step"], c["attempt"]): c["reserved_micros"] for c in run.paid_calls}
    assert sum(r for (step, _), r in reserved.items() if step in steps) == 100_000
    assert sum(reserved.values()) == 305_000 <= RUN_CAP
    # Production's parse is a paid call (ProductionAdapters.extract): 20,000 more.
    assert sum(reserved.values()) + step_reservation(run, "parse") == 325_000 <= RUN_CAP
    # Settled: the failed call's 20,000 stays held, the rest is what was spent.
    spent = sum(c["cost_micros"] for c in run.paid_calls if c["cost_basis"] == "computed")
    assert run.usage.reserved_cost_micros == 20_000 + spent


def test_the_pre_bound_price_retries_a_first_pass_within_the_usd_1_run_limit(tmp_path):
    # At the run's former 500,000 the pre-bound price could not retry: the failed
    # call holds 318,670 and its retry needs as much again. The published limit is
    # now USD 1 (the owner, 2026-10-03), and 637,340 fits, so the request bound is
    # no longer what lets a retry through; it still keeps the reservation small.
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
