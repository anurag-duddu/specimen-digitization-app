"""Same-Run package upgrade with a real prior-SDK journal and offline effects.

The journal fixture was emitted by official 2.51.0/0.36.0 wheels (hashes below),
using FunctionModel and StepPersistence. Provisioning uses the
existing synthetic repository/binding writer and real SQLite research store;
this is neither a provider qualification nor a production migration.
"""

import asyncio
import copy
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from specimen_digitization.research_harness import provisioning
from specimen_digitization.research_harness.package_qualification import SERIALIZATION_VERSION
from specimen_digitization.research_harness.persistence import (
    CapturedResult, DurableEffectBroker, HeldUnknown, ImmutableFileBlobs,
    ResearchStore, SqlConnectStepStore, canonical,
)
from specimen_digitization.research_harness.production_runtime import research_program_key
from test_provisioning import job_scope, rig  # noqa: F401

# Public PyPI wheel SHA-256 digests, verified against the previous uv.lock:
# AI Slim 2.51.0: e2adf6adec72326fab7088640f27c749a969738bfd5b5b068bc4de21b965af00  # pragma: allowlist secret
# Harness 0.36.0: 242df9da8d229cadaffe93a7444ecf6ab1a52567ffb977e0efb40bac5c047663  # pragma: allowlist secret
# Evals 2.51.0: fd0764c12c9a5bc386a030d7e4e92d3f8d58e35ed4e6fc9f9a5ba185789c9b44  # pragma: allowlist secret
# Graph 2.51.0: 38ccf69d931e1bf7a719cb380224af1d66064bac050219eee83287cec4b0309f  # pragma: allowlist secret


def test_revision_61_keeps_same_run_old_journal_effects_holds_and_allowance(rig, tmp_path, monkeypatch):
    old_serialization = "pydantic-ai-2.51.0+harness-0.36.0/v1"
    fixture = json.loads((Path(__file__).parents[1] / "fixtures/research_harness/package-upgrade-251-036.json").read_text())
    assert fixture["generated_with"] == {"pydantic-ai-slim": "2.51.0", "pydantic-ai-harness": "0.36.0",
        "pydantic-evals": "2.51.0", "pydantic-graph": "2.51.0"}
    rig.specimen.version = 59
    rig.specimen.run.usage.reserved_cost_micros = 500_000
    run_id = rig.specimen.run.id
    committed = provisioning.committed_job_pins

    def old_pins(*args, **kwargs):
        # Synthetic admission for the old runtime; retain its actual version
        # identifiers rather than relabeling it when current code provisions r61.
        pins = committed(*args, **kwargs)
        pins["serialization_version"] = "harness-0.36.0/core-2.51.0"
        for bound in pins["sources"]["model_request_bounds"].values():
            bound["serialization_version"] = old_serialization
        return pins

    with monkeypatch.context() as patch:
        patch.setattr(provisioning, "committed_job_pins", old_pins)
        rig.provision()
    old_scope = job_scope(rig)
    program = research_program_key(run_id)
    store = ResearchStore(rig.backend, program)
    lease = store.claim(old_scope, "offline-old-worker", ttl_seconds=120)
    blobs = ImmutableFileBlobs(tmp_path / "historical-blobs")
    broker = DurableEffectBroker(store, blobs)

    async def settled(*_):
        return CapturedResult({"synthetic": "retained"}, 25_000)

    async def lost(*_):
        raise OSError("offline lost response")

    receipt = asyncio.run(broker.execute(old_scope, lease, "old-settled", {"version": old_serialization},
        40_000, settled))
    with pytest.raises(OSError, match="offline lost response"):
        asyncio.run(broker.execute(old_scope, lease, "old-unknown", {"version": old_serialization},
            100_000, lost))

    snapshot = fixture["snapshot"]
    snapshot_bytes = canonical(snapshot)
    reference = blobs.put_at("retained-old-sdk-snapshot", snapshot_bytes)
    native_run_id = fixture["run"]["run_id"]
    retained = {"scope": old_scope.identity(), "agent_name": fixture["run"]["agent_name"],
        "record": fixture["run"], "events": fixture["events"],
        "tools": {fixture["tool_effect"]["tool_call_id"]: fixture["tool_effect"]},
        "snapshots": [{"step_index": snapshot["step_index"], "state": snapshot["state"],
            "idempotency_key": snapshot["idempotency_key"], "timestamp": snapshot["timestamp"],
            "reference": asdict(reference), "sequence": 1}]}
    store._mutate(old_scope, lambda state, _: state["journal"].update({native_run_id: retained}))
    before = copy.deepcopy(store._read(old_scope).state)

    later = rig.specimen.model_copy(deep=True)
    later.version = 61
    rig.repository.specimen = later
    rig.writer.binding = None  # The synthetic current binding names revision 59.
    rig.provision(later)
    current_scope = job_scope(rig, later)
    state = store._read(current_scope).state
    assert later.run.id == run_id and research_program_key(later.run.id) == program
    assert current_scope.job_id == f"{run_id}-r61" and old_scope.job_id == f"{run_id}-r59"
    assert set(state["jobs"]) == {old_scope.key, current_scope.key}
    assert state["jobs"][old_scope.key] == before["jobs"][old_scope.key]
    assert store.job(old_scope)["pins"]["serialization_version"] == "harness-0.36.0/core-2.51.0"
    for key in set(before) - {"jobs"}:
        assert state[key] == before[key]
    assert store.job(current_scope)["pins"]["serialization_version"] == SERIALIZATION_VERSION
    registration, registered_program, bound_scope = rig.writer.registered[-1]
    assert (registered_program, bound_scope) == (program, current_scope)
    assert registration.runtime_binding_digest == store.job(current_scope)["binding_digest"]
    budget = store.budget(current_scope)
    assert budget["ceiling_micro_usd"] == 1_000_000
    assert budget["settled_micro_usd"] == 525_000
    assert budget["held_micro_usd"] == 100_000
    assert budget["remaining_micro_usd"] == 375_000

    journal = SqlConnectStepStore(store, old_scope, blobs, agent_name=fixture["run"]["agent_name"])
    record = asyncio.run(journal.get_run(run_id=native_run_id))
    assert record.metadata["serialization_version"] == old_serialization
    reopened = asyncio.run(journal.latest_snapshot(run_id=native_run_id))
    assert reopened.state == "complete" and reopened.messages[-1].parts[0].content == "Historical synthetic result"
    assert len(asyncio.run(journal.list_events(run_id=native_run_id))) == len(fixture["events"])
    effect = asyncio.run(journal.get_tool_effect(run_id=native_run_id, tool_call_id="historical-tool"))
    assert effect.status == fixture["tool_effect"]["status"]
    assert blobs.get(reference) == snapshot_bytes

    async def forbidden(*_):
        pytest.fail("historical replay attempted a second send")

    assert asyncio.run(broker.execute(old_scope, lease, "old-settled", {"version": old_serialization},
        40_000, forbidden)) == receipt
    with pytest.raises(HeldUnknown):
        asyncio.run(broker.execute(old_scope, lease, "old-unknown", {"version": old_serialization},
            100_000, forbidden))
    assert store._read(current_scope).state == state
