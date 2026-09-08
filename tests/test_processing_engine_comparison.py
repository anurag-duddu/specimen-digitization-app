"""Real process-death proof for the engine-independent persisted effect boundary.

Only local generated fixture data is used. No model, cloud API, or engine service
is called; these tests must not be presented as Temporal/Workflows integration.
"""

import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timedelta

import pytest

from specimen_digitization.application.storage import SQLiteRepository, digest
from specimen_digitization.application.workflow import Workflow, SyntheticAdapters
from test_worker_recovery import setup
from test_application import SYNTHETIC_TEXT


@pytest.mark.parametrize("effect_received", [False, True])
def test_killed_process_retains_unknown_intent_without_replaying(tmp_path, effect_received):
    repo, blobs, principal, specimens = setup(tmp_path)
    specimen = specimens[0]
    specimen.run.completed_steps = ["pin_dependencies", "classify", "quality_check"]
    specimen = repo.save(
        principal, specimen, specimen.version, "process-test", digest("process-test")
    )
    actor_file = tmp_path / "principal.json"
    actor_file.write_text(principal.model_dump_json())
    child_source = """
import os, sys, time
from pathlib import Path
from specimen_digitization.application.domain import Principal
from specimen_digitization.application.storage import SQLiteRepository, LocalBlobs
from specimen_digitization.application.workflow import Workflow, SyntheticAdapters

root, specimen_id, received = Path(sys.argv[1]), sys.argv[2], sys.argv[3] == 'true'
principal = Principal.model_validate_json((root / 'principal.json').read_text())
class InterruptedAdapter(SyntheticAdapters):
    def segment(self, specimen):
        # Workflow has committed intent before entering this adapter. The local
        # marker represents an independently observed downstream side effect.
        if received:
            with (root / 'effect-receipt').open('w') as receipt:
                receipt.write('one-local-fixture-effect')
                receipt.flush()
                os.fsync(receipt.fileno())
        (root / 'entered').write_text('intent-committed')
        while True:
            time.sleep(0.1)
blobs = LocalBlobs(root / 'blobs')
Workflow(SQLiteRepository(root / 'state.sqlite3'), blobs,
         InterruptedAdapter(blobs, 'unused fixture')).step(principal, specimen_id)
"""
    environment = dict(os.environ, LOGFIRE_SEND_TO_LOGFIRE="false")
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    child = subprocess.Popen(
        [sys.executable, "-c", child_source, str(tmp_path), specimen.id,
         str(effect_received).lower()],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 15
        while not (tmp_path / "entered").exists() and time.monotonic() < deadline:
            if child.poll() is not None:
                pytest.fail("Fixture child exited before reaching durable intent")
            time.sleep(0.02)
        assert (tmp_path / "entered").exists(), "Child did not reach durable intent"
        child.kill()  # Actual abrupt process death, with no Python finally cleanup.
        assert child.wait(timeout=5) != 0
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)

    retained = SQLiteRepository(repo.path).get(principal.scope, specimen.id)
    assert retained.run.blocker == "external_outcome_unknown"
    assert retained.run.usage.external_calls == 1
    assert (tmp_path / "effect-receipt").exists() is effect_received

    class MustNotRepeat(SyntheticAdapters):
        def segment(self, specimen):
            pytest.fail("Restart repeated an effect whose outcome is unknown")

    restart_clock = datetime.fromisoformat(retained.run.lease_until) + timedelta(seconds=1)
    recovered = Workflow(
        SQLiteRepository(repo.path), blobs, MustNotRepeat(blobs, SYNTHETIC_TEXT),
        clock=lambda: restart_clock,
    )
    blocked = recovered.step(principal, specimen.id)
    assert blocked.run.stage == "processing_blocked"
    assert blocked.run.blocker == "external_outcome_unknown"
    assert blocked.run.usage.external_calls == 1
    assert blocked.run.usage.reserved_active_seconds > 0
    assert not blocked.run.regions
