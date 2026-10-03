"""The pilot's first-pass route reaches its step (docs/execution/golive/HARNESS.md 3).

`classify` sets the run's profile from the published one, and the workflow
pins the dependencies again after it, so the route `classify` keeps is the one
pinned for the first pass. Readings that differ then reach the first pass with
its reservation instead of blocking as `approved_cost_budget_unavailable`.
"""

from fastapi.testclient import TestClient

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
    create_app,
)
from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import LookupStatus, Principal, Scope
from specimen_digitization.application.first_pass import synthetic_decision
from specimen_digitization.application.lane_reservations import step_reservation
from specimen_digitization.application.production import ProductionAdapters
from specimen_digitization.application.profile_runtime import published_risk_registry
from specimen_digitization.application.reliability import AdapterFailure
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.model_gateway import STAGE_HUGGINGFACE_ROUTES

from test_lane_costs import seed_synthetic_ledger
from test_lane_drain import NonSensitiveMember
from test_lane_profile import USER, ProductionLikeAdapters
from test_lane_trigger import RecordingDispatcher, intake

SCOPE = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
GLM = {"model_id": "zai-org/GLM-5.3-Flash", "provider": "deepinfra"}
# PLAN 4.3 (a) for each of the call's two requests, since the route documents
# no image rule: 1,048,576 in and 4,096 out at 0.15 and 0.50 dollars a million.
FIRST_PASS_RESERVATION = 2 * 159_335


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
    }


def test_the_first_pass_reserves_its_routes_context_since_it_documents_no_image_rule():
    from test_lane_reservations import reading

    run, _ = reading(600, 400)
    run.profile = run.profile.model_copy(update={"first_pass_route": "first-pass-glm"})
    assert step_reservation(run, "first_pass:" + run.regions[0].id) == (
        FIRST_PASS_RESERVATION
    )


class DisagreeingReaders(ProductionLikeAdapters):
    """Production's pins, two readings that differ, and a first pass that
    records the pin and the reservation it was called with."""

    classifier = None  # Read by production's pin_dependencies.
    pin_dependencies = ProductionAdapters.pin_dependencies

    def __init__(self, blobs, fail=False):
        super().__init__(blobs, SYNTHETIC_TEXT, SYNTHETIC_TEXT + " 1946")
        self.fail = fail
        self.pins, self.reserved = [], []

    def first_pass(self, specimen, region, readings):
        run = specimen.run
        route = run.profile.first_pass_route
        self.pins.append(run.dependencies["routes"].get(route))
        self.reserved.append(
            (run.blocker, step_reservation(run, "first_pass:" + region.id))
        )
        if self.fail:
            raise AdapterFailure("first_pass_rate_limited", LookupStatus.RATE_LIMITED)
        decision = synthetic_decision(self.blobs, region, readings)
        call = decision.call.model_copy(
            update={"route_id": route, **GLM, "input_tokens": 1_200, "output_tokens": 300}
        )
        return decision.model_copy(update={"call": call})


def drain(tmp_path, fail=False):
    blobs = LocalBlobs(tmp_path / "blobs")
    adapters = DisagreeingReaders(blobs, fail)
    repository = NonSensitiveMember(tmp_path / "state.sqlite3")
    seed_synthetic_ledger(repository, reserved_total_micros=0)
    app = create_app(
        mode="emulator",
        repository=repository,
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
        profile_registry=published_registry({SYNTHETIC_COLLECTION: "insects"}),
        risk_registry=published_risk_registry(),
        worker_dispatcher=RecordingDispatcher(),
    )
    principal = Principal(user_id=USER, scope=SCOPE, role="reviewer")
    ident = intake(TestClient(app, raise_server_exceptions=False))["specimen_id"]
    run = app.state.workflow.drain(principal, ident).run
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
