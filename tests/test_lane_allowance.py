"""The program's model allowance (docs/execution/golive/LANE.md, T2b; G9, G30)."""

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
    create_app,
)
from specimen_digitization.application.collection_profiles import (
    CollectionProfileRegistry,
    published_registry,
)
from specimen_digitization.application.domain import (
    LookupStatus,
    Principal,
    Profile,
    Run,
    Scope,
)
from specimen_digitization.application.lane import LaneConflict, queue
from specimen_digitization.application.lane_allowance import (
    LEDGER_KIND,
    ProgramLedger,
    reserve_step,
)
from specimen_digitization.application.profile_runtime import published_risk_registry
from specimen_digitization.application.reliability import AdapterFailure
from specimen_digitization.application.storage import Conflict, LocalBlobs

from test_lane_drain import NonSensitiveMember
from test_lane_profile import USER, ProductionLikeAdapters
from test_lane_trigger import RecordingDispatcher, intake, specimen_with

PUBLISHED = (
    Path(__file__).resolve().parents[1]
    / "src/specimen_digitization/application/profiles/published.json"
)
SCOPE = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
OTHER_COLLECTION = "00000000-0000-4000-8000-0000000000c9"
MOMENT = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


def lab(tmp_path, adapters=ProductionLikeAdapters, repository=None):
    blobs = LocalBlobs(tmp_path / "blobs")
    repository = repository or NonSensitiveMember(tmp_path / "state.sqlite3")
    app = create_app(
        mode="emulator",
        repository=repository,
        blobs=blobs,
        adapters=adapters(blobs, SYNTHETIC_TEXT),
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
    return app, repository


def principal():
    return Principal(user_id=USER, scope=SCOPE, role="reviewer")


def uploaded(app):
    return intake(TestClient(app, raise_server_exceptions=False))["specimen_id"]


def seed(repository, reserved_total_micros):
    ledger = ProgramLedger(repository, SCOPE)
    repository.put_document(
        SCOPE,
        LEDGER_KIND,
        ledger.ident,
        {"sensitive": False, "reserved_total_micros": reserved_total_micros},
        0,
    )


def test_the_pilot_carries_the_program_allowance():
    allowance = published_registry().resolve("insects").profile.processing.program_allowance
    assert (allowance.allowance_micros, allowance.ledger_collection) == (
        5_000_000,
        "insects",
    )


def published_with(change):
    data = json.loads(PUBLISHED.read_text())
    change(data)
    return data


def test_every_profile_carries_the_same_program_allowance():
    def second_profile(data):
        pilot = next(p for p in data["profiles"] if p["id"] == "zoology_insects_slides")
        other = copy.deepcopy(pilot)
        other["id"] = "zoology_mammals_lane_test"
        other["collection_id"] = "mammals"
        other["processing"]["program_allowance"]["allowance_micros"] = 9_000_000
        data["profiles"].append(other)
        data["mappings"].append(
            {
                "collection_id": "mammals",
                "profile_id": other["id"],
                "profile_version": other["version"],
            }
        )

    with pytest.raises(ValueError, match="program allowance"):
        CollectionProfileRegistry.model_validate(published_with(second_profile))


def test_the_ledger_collection_is_a_published_node():
    def unknown_ledger(data):
        pilot = next(p for p in data["profiles"] if p["id"] == "zoology_insects_slides")
        pilot["processing"]["program_allowance"]["ledger_collection"] = "no-such-node"

    with pytest.raises(ValueError, match="ledger"):
        CollectionProfileRegistry.model_validate(published_with(unknown_ledger))


def test_a_request_copies_the_allowance_and_the_ledger_collection():
    specimen = specimen_with(Run(profile=Profile(synthetic=False)))
    queue(specimen, published_registry({SYNTHETIC_COLLECTION: "insects"}), USER)
    execution = specimen.run.profile.execution
    assert execution.program_allowance_micros == 5_000_000
    assert execution.program_ledger_collection == SYNTHETIC_COLLECTION


def test_a_ledger_collection_bound_twice_refuses_the_request():
    specimen = specimen_with(Run(profile=Profile(synthetic=False)))
    bindings = {SYNTHETIC_COLLECTION: "insects", OTHER_COLLECTION: "insects"}
    with pytest.raises(LaneConflict) as caught:
        queue(specimen, published_registry(bindings), USER)
    assert caught.value.code == "program_allowance_unavailable"


def test_each_paid_step_reserves_on_the_program_ledger(tmp_path):
    app, repository = lab(tmp_path)
    specimen = app.state.workflow.drain(principal(), uploaded(app))
    run = specimen.run
    assert "parse" in run.completed_steps, run.blocker
    # The ledger adds every paid step's reservation, as the run's budget does.
    assert run.usage.reserved_cost_micros > 0
    stored = ProgramLedger(repository, SCOPE).read()
    assert stored["reserved_total_micros"] == run.usage.reserved_cost_micros
    assert stored["sensitive"] is False
    position = run.program_allowance
    assert position["allowance_micros"] == 5_000_000
    assert position["reserved_total_micros"] == run.usage.reserved_cost_micros
    assert position["remaining_micros"] == 5_000_000 - run.usage.reserved_cost_micros
    assert position["ledger_revision"] == stored["revision"]


class CountingAdapters(ProductionLikeAdapters):
    def __init__(self, *args):
        super().__init__(*args)
        self.segments = 0

    def segment(self, specimen):
        self.segments += 1
        return super().segment(specimen)


def test_a_step_that_would_cross_the_allowance_is_not_called(tmp_path):
    app, repository = lab(tmp_path, adapters=CountingAdapters)
    seed(repository, 4_990_000)
    specimen = app.state.workflow.drain(principal(), uploaded(app))
    run = specimen.run
    assert (run.stage, run.blocker) == ("processing_blocked", "program_allowance_exhausted")
    assert app.state.workflow.adapters.segments == 0
    position = run.program_allowance
    assert position["remaining_micros"] == 10_000
    assert position["requested_micros"] == 33_000
    assert ProgramLedger(repository, SCOPE).read()["reserved_total_micros"] == 4_990_000


class BusyOnceAdapters(ProductionLikeAdapters):
    def __init__(self, *args):
        super().__init__(*args)
        self.busy = 1

    def segment(self, specimen):
        if self.busy:
            self.busy -= 1
            raise AdapterFailure("sam3_busy", LookupStatus.RATE_LIMITED)
        return super().segment(specimen)


def test_a_retry_reserves_again(tmp_path):
    app, repository = lab(tmp_path, adapters=BusyOnceAdapters)
    workflow = app.state.workflow
    specimen = workflow.drain(principal(), uploaded(app))
    assert specimen.run.stage == "retry_scheduled"
    first = ProgramLedger(repository, SCOPE).read()["reserved_total_micros"]
    workflow.clock = lambda: datetime.now(timezone.utc) + timedelta(hours=1)
    specimen = workflow.drain(principal(), specimen.id)
    assert specimen.run.attempts["segment"] == 2
    total = ProgramLedger(repository, SCOPE).read()["reserved_total_micros"]
    assert first == 33_000
    assert total == specimen.run.usage.reserved_cost_micros
    assert total - first >= 33_000  # The retry's segment was reserved again.


def test_without_an_allowance_the_ledger_is_not_consulted(tmp_path):
    repository = NonSensitiveMember(tmp_path / "state.sqlite3")
    specimen = specimen_with(Run(profile=Profile(synthetic=False)))
    assert reserve_step(repository, principal(), specimen, "segment", 15_000) is None
    assert specimen.run.program_allowance is None
    assert repository.documents(SCOPE, LEDGER_KIND) == []


class ContendedLedger(NonSensitiveMember):
    """Another collection's reservation lands between this one's read and write."""

    def __init__(self, *args):
        super().__init__(*args)
        self.contended = 1

    def put_document(self, scope, kind, ident, payload, expected):
        if kind == LEDGER_KIND and self.contended:
            self.contended -= 1
            super().put_document(
                scope,
                kind,
                ident,
                {"sensitive": False, "reserved_total_micros": 1_000},
                expected,
            )
            raise Conflict("Stale document revision")
        return super().put_document(scope, kind, ident, payload, expected)


def test_a_concurrent_reservation_is_retried_on_a_fresh_read(tmp_path):
    repository = ContendedLedger(tmp_path / "state.sqlite3")
    ledger = ProgramLedger(repository, SCOPE, clock=lambda: MOMENT)
    reservation = ledger.reserve(
        5_000_000, 15_000, specimen_id="s", run_id="r", step="segment", attempt=1
    )
    assert reservation.issue is None
    assert reservation.position["reserved_total_micros"] == 16_000
    assert ledger.read()["reserved_total_micros"] == 16_000
    assert ledger.read()["last"] == {
        "specimen_id": "s",
        "run_id": "r",
        "step": "segment",
        "attempt": 1,
        "micros": 15_000,
        "allowance_micros": 5_000_000,
        "at": MOMENT.isoformat(),
    }


class ForeignLedger(NonSensitiveMember):
    """A ledger another actor created cannot be read (S5's createdBy check)."""

    def document(self, scope, kind, ident):
        if kind == LEDGER_KIND:
            raise Conflict("SQL Connect transaction rejected")
        return super().document(scope, kind, ident)


def test_an_unreadable_ledger_blocks_rather_than_spends(tmp_path):
    ledger = ProgramLedger(ForeignLedger(tmp_path / "state.sqlite3"), SCOPE)
    reservation = ledger.reserve(
        5_000_000, 15_000, specimen_id="s", run_id="r", step="segment", attempt=1
    )
    assert reservation.issue == "program_allowance_ledger_unavailable"
    assert reservation.position is None


def test_a_ledger_that_stays_busy_blocks_the_run(tmp_path):
    class AlwaysContended(ContendedLedger):
        def put_document(self, scope, kind, ident, payload, expected):
            self.contended = 1
            return super().put_document(scope, kind, ident, payload, expected)

    ledger = ProgramLedger(AlwaysContended(tmp_path / "state.sqlite3"), SCOPE)
    reservation = ledger.reserve(
        5_000_000, 15_000, specimen_id="s", run_id="r", step="segment", attempt=1
    )
    assert reservation.issue == "program_allowance_ledger_unavailable"


def test_the_ledger_reads_numbers_sql_connect_returns_as_doubles(tmp_path):
    repository = NonSensitiveMember(tmp_path / "state.sqlite3")
    seed(repository, 15_000)
    document = repository.document

    def transported(scope, kind, ident):
        # SQL Connect's Struct transport may return every JSON number as a double.
        stored = document(scope, kind, ident)
        return {k: float(v) if type(v) is int else v for k, v in stored.items()}

    repository.document = transported
    ledger = ProgramLedger(repository, SCOPE, clock=lambda: MOMENT)
    reservation = ledger.reserve(
        5_000_000, 20_000, specimen_id="s", run_id="r", step="parse", attempt=1
    )
    assert reservation.issue is None
    assert reservation.position["reserved_total_micros"] == 35_000
    assert type(ledger.read()["reserved_total_micros"]) is int
