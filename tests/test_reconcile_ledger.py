"""Reconciling an unknown reading reserves the re-run on its own, and refunds nothing.

The lab of `test_lane_costs.py`: the published insects profile with a test price
list and the program's 5,000,000 micro-dollar allowance on a seeded ledger. A
reading's request goes out, its outcome is unknown, and an administrator
reconciles it. Both ledgers, the program's (`ordinary_effects`, keyed by run,
step and attempt) and the run's shared research state (`step:attempt`), must
show attempt 1 still held in full beside a new attempt 2.
"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
    create_app,
)
from specimen_digitization.application.domain import LookupStatus, Principal
from specimen_digitization.application.lane_allowance import ProgramLedger
from specimen_digitization.application.profile_runtime import published_risk_registry
from specimen_digitization.application.reliability import AdapterFailure
from specimen_digitization.application.storage import LocalBlobs, canonical_json, digest
from specimen_digitization.research_harness.persistence import (
    DurabilityScope,
    SqliteStateBackend,
)
from specimen_digitization.research_harness.production_runtime import research_program_key
from specimen_digitization.research_harness.program_budget import (
    research_liability_micros,
    reserve_ordinary_liability,
    settle_ordinary_liability,
)

from test_application import HEADERS, PREFIX
from test_lane_costs import SCOPE, TokenAdapters, ledger_total, priced_registry, seed_synthetic_ledger
from test_lane_drain import NonSensitiveMember
from test_lane_profile import USER
from test_lane_trigger import RecordingDispatcher, intake

UNKNOWN = "external_outcome_unknown"
MUSE = "handwriting-muse"


class DroppedReader(TokenAdapters):
    """Readers whose first `handwriting-muse` request has an unknown outcome."""

    unknown_reads = 0

    def transcribe(self, specimen, region, route):
        if route == MUSE and self.unknown_reads:
            self.unknown_reads -= 1
            raise AdapterFailure(
                "model_timeout", LookupStatus.TIMEOUT, outcome_unknown=True
            )
        return super().transcribe(specimen, region, route)


def ledger_lab(tmp_path):
    """The lab, with an admin membership and the research state wired as production does."""
    blobs = LocalBlobs(tmp_path / "blobs")
    adapters = DroppedReader(blobs, SYNTHETIC_TEXT)
    adapters.unknown_reads = 1
    repository = NonSensitiveMember(tmp_path / "state.sqlite3")
    seed_synthetic_ledger(repository, 0)
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
                "role": "admin",
                "can_view_sensitive": True,
            }
        ],
        profile_registry=priced_registry(),
        risk_registry=published_risk_registry(),
        worker_dispatcher=RecordingDispatcher(),
    )
    client = TestClient(app, raise_server_exceptions=False)
    principal = Principal(user_id=USER, scope=SCOPE, role="admin")
    # The ordinary calls share the run's cost cap with research (workflow_bridge).
    backend = SqliteStateBackend(tmp_path / "research.sqlite3")
    backend.grant(
        DurabilityScope(SYNTHETIC_ORG, SYNTHETIC_COLLECTION, "any", "any", 1, USER, False),
        role="admin",
    )
    workflow = app.state.workflow
    workflow.retained_cost = lambda p, specimen: research_liability_micros(
        repository, p, specimen, state_backend=backend
    )
    workflow.reserve_retained_cost = lambda p, specimen, step, cost: reserve_ordinary_liability(
        repository, p, specimen, step, cost, state_backend=backend
    )
    workflow.settle_retained_cost = lambda p, specimen, step: settle_ordinary_liability(
        repository, p, specimen, step, state_backend=backend
    )
    row = intake(client)
    return app, client, principal, backend, row["specimen_id"]


def program_entries(app, specimen):
    return ProgramLedger(app.state.workflow.repository, SCOPE).read()["ordinary_effects"]


def program_key(specimen, step, attempt):
    return canonical_json([specimen.id, specimen.run.id, step, attempt])


def research_reservations(backend, specimen):
    scope = DurabilityScope(
        SYNTHETIC_ORG, SYNTHETIC_COLLECTION, specimen.id, "ordinary-budget-read", 1, USER, False
    )
    return backend.load(scope, research_program_key(specimen.run.id)).state[
        "ordinary_reservations"
    ]


def test_the_rerun_reserves_under_a_new_attempt_and_the_first_stays_held(tmp_path):
    app, client, principal, backend, ident = ledger_lab(tmp_path)
    workflow = app.state.workflow
    blocked = workflow.drain(principal, ident)
    assert blocked.run.blocker == UNKNOWN
    step = next(s for s in blocked.run.attempts if s.endswith(":" + MUSE))
    assert blocked.run.attempts[step] == 1
    [unknown] = [c for c in blocked.run.paid_calls if c["step"] == step]
    assert (unknown["attempt"], unknown["outcome"], unknown["cost_basis"]) == (
        1,
        "unknown",
        "reserved",
    )
    held = unknown["cost_micros"]
    assert held > 0

    # The lease expires, and the administrator reconciles.
    blocked.run.lease_until = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    blocked = workflow.repository.save(
        principal, blocked, blocked.version, "expired-lease", digest("expired-lease")
    )
    program_before = dict(program_entries(app, blocked))
    research_before = dict(research_reservations(backend, blocked))
    total_before = ledger_total(app)
    assert program_key(blocked, step, 1) in program_before
    assert research_before[step + ":1"] == {"reserved_micros": held, "settled_micros": None}
    response = client.post(
        PREFIX + f"/runs/{blocked.run.id}/actions",
        headers=dict(HEADERS, **{"Idempotency-Key": "reconcile-ledger"}),
        json={
            "action": "reconcile",
            "expected_revision": blocked.version,
            "reason": "The reader timed out; read it again",
        },
    )
    assert response.status_code == 200, response.text

    # Reconciling itself changes no counter, no attempt, no paid call and no ledger.
    queued = workflow.repository.get(SCOPE, ident)
    assert queued.run.usage == blocked.run.usage
    assert queued.run.attempts == blocked.run.attempts
    assert queued.run.paid_calls == blocked.run.paid_calls
    assert dict(program_entries(app, queued)) == program_before
    assert dict(research_reservations(backend, queued)) == research_before
    assert ledger_total(app) == total_before

    done = workflow.drain(principal, ident)

    assert "parse" in done.run.completed_steps, done.run.blocker
    assert done.run.attempts[step] == 2
    # The program ledger: attempt 1 is untouched and unsettled, attempt 2 is its own
    # entry, reserved and then settled to what the reading cost.
    entries = program_entries(app, done)
    assert entries[program_key(done, step, 1)] == program_before[program_key(done, step, 1)]
    assert entries[program_key(done, step, 1)]["settled_micros"] is None
    second = entries[program_key(done, step, 2)]
    assert second["reserved_micros"] > 0 and second["settled_micros"] == 900
    # The run's shared research state keeps `step:1` held in full beside `step:2`.
    reservations = research_reservations(backend, done)
    assert reservations[step + ":1"] == {"reserved_micros": held, "settled_micros": None}
    assert reservations[step + ":2"]["reserved_micros"] == second["reserved_micros"]
    assert reservations[step + ":2"]["settled_micros"] == 900
    # The first attempt's whole reservation is still counted, by the run and by the
    # program, and the two agree.
    calls = {(c["step"], c["attempt"]): c for c in done.run.paid_calls}
    assert calls[(step, 1)]["cost_micros"] == held
    assert calls[(step, 2)]["outcome"] == "completed"
    assert done.run.usage.reserved_cost_micros == sum(c["cost_micros"] for c in done.run.paid_calls)
    assert done.run.usage.reserved_cost_micros >= held + 900
    assert ledger_total(app) == done.run.usage.reserved_cost_micros
    assert done.run.program_allowance["reserved_total_micros"] == ledger_total(app)
