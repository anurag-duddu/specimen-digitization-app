"""Missing cumulative ledgers stay blocked; fixture seeding is explicit only."""

import pytest

from specimen_digitization.application.domain import Principal
from specimen_digitization.application.lane_allowance import (
    LEDGER_KIND,
    UNAVAILABLE,
    LegacyLedgerUnavailable,
    ProgramLedger,
    reserve_step,
)

from test_lane_costs import QWEN, SCOPE, lab, priced_run
from test_lane_drain import NonSensitiveMember
from test_lane_profile import USER
from test_lane_trigger import specimen_with


def test_missing_original_ledger_refuses_reservation_without_initializing(tmp_path):
    repository = NonSensitiveMember(tmp_path / "state.sqlite3")
    run = priced_run()
    run.profile.execution = run.profile.execution.model_copy(
        update={
            "program_allowance_micros": 5_000_000,
            "program_ledger_collection": SCOPE.collection_id,
        }
    )
    principal = Principal(user_id=USER, scope=SCOPE, role="reviewer")
    with pytest.raises(LegacyLedgerUnavailable, match=UNAVAILABLE):
        ProgramLedger(repository, SCOPE).read()
    assert reserve_step(repository, principal, specimen_with(run), QWEN, 2_000) == UNAVAILABLE
    assert repository.documents(SCOPE, LEDGER_KIND) == []
    assert run.paid_calls == []


def test_unseeded_workflow_blocks_before_any_paid_call(tmp_path):
    app, principal, row = lab(tmp_path, ledger_total_micros=None)
    repository = app.state.workflow.repository
    run = app.state.workflow.drain(principal, row["specimen_id"]).run
    assert (run.stage, run.blocker) == ("processing_blocked", UNAVAILABLE)
    assert run.paid_calls == []
    with pytest.raises(LegacyLedgerUnavailable, match=UNAVAILABLE):
        ProgramLedger(repository, SCOPE).read()
