"""Disposable GBIF send interruption retains holds; it does not retry around them."""
import asyncio

import pytest

from specimen_digitization.research_harness.persistence import (
    DurableEffectBroker, HeldUnknown, ImmutableFileBlobs, ResearchStore, SqliteStateBackend,
)
from specimen_digitization.research_harness.source_capture_v2 import CaptureSourceBrokerV2

from test_source_capture_v2 import make_capture_rig


def test_interrupted_gbif_send_keeps_exact_unknown_hold_on_cold_resume(tmp_path):
    rig = make_capture_rig(tmp_path, source_id="gbif")
    rig.control["cancel"] = True
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(rig.broker.query_source(rig.request, rig.query))
    before = rig.store._read(rig.durable_scope).state
    held = [item for item in before["effects"].values() if item["status"] == "held_unknown"]
    assert len(held) == 1 and len(rig.calls) == 1
    assert held[0]["held_micro_usd"] == 1 and held[0]["receipt"] is None

    rig.control["cancel"] = False
    cold_store = ResearchStore(SqliteStateBackend(rig.backend.path), "disposable-test-program")
    cold = CaptureSourceBrokerV2(rig.registry, {rig.source.id: rig.policy},
        DurableEffectBroker(cold_store, ImmutableFileBlobs(rig.blobs.directory)),
        rig.durable_scope, rig.lease, transport=rig.transport, execution_class="offline")
    with pytest.raises(HeldUnknown):
        asyncio.run(cold.query_source(rig.request, rig.query))
    after = cold_store._read(rig.durable_scope).state
    assert len(rig.calls) == 1 and before["effects"] == after["effects"]
    assert before["budget_policy"] == after["budget_policy"]
