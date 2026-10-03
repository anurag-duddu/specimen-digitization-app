"""Offline failure-window and real SQL tests for app-owned Harness durability."""

import asyncio
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import os
import re
import json
import subprocess
import sys
from dataclasses import asdict
from uuid import uuid4

import pytest

from specimen_digitization.research_harness.persistence import (
    BudgetExceeded,
    BudgetPolicy,
    CapturedResult,
    DurabilityScope,
    DurableEffectBroker,
    HeldUnknown,
    ImmutableFileBlobs,
    PinnedRuntime,
    ResearchStore,
    SqliteStateBackend,
    GcsMediaStore,
    GcsImmutableBlobs,
    SqlConnectStepStore,
    SqlConnectStateBackend,
    StaleWork,
    digest,
)


def fixture(tmp_path, ceiling=100, external_held=0, retry_policy=False):
    backend = SqliteStateBackend(tmp_path / "state.sqlite")
    scope = DurabilityScope("org", "collection", "specimen", "job", 1, "worker", False)
    backend.grant(scope, role="reviewer")
    store = ResearchStore(backend, "existing-program-ledger")
    store.initialize(scope, BudgetPolicy(ceiling, external_held_micro_usd=external_held))
    pins = PinnedRuntime("input", {"version": "p1"}, {"text": "exact pinned"},
                         {"version": "s1"}, {"route": "harness-deepseek"},
                         {"max_tokens": 128, "retry_failed_no_effect": retry_policy, "safe_retry_attempt_limit": 2}, "specialist_harness_v2")
    store.create_job(scope, pins, ["taxon", "country"])
    lease = store.claim(scope, "owner", ttl_seconds=30)
    blobs = ImmutableFileBlobs(tmp_path / "blobs")
    return store, scope, lease, DurableEffectBroker(store, blobs), blobs


def test_atomic_hold_replay_and_pins_survive_restart(tmp_path):
    store, scope, lease, broker, blobs = fixture(tmp_path)
    calls = []

    async def dispatch(attempt, token):
        calls.append((attempt, token))
        assert store.budget(scope)["held_micro_usd"] == 70
        return CapturedResult({"accepted": "Chironomus"}, 25, usage={"input_tokens": 4})

    first = asyncio.run(broker.execute(scope, lease, "taxonomy-query", {"name": "Chironomus"}, 70, dispatch))
    second = asyncio.run(broker.execute(scope, lease, "taxonomy-query", {"name": "Chironomus"}, 70, dispatch))
    assert first == second
    assert len(calls) == 1
    assert store.budget(scope)["settled_micro_usd"] == 25
    fresh = ResearchStore(SqliteStateBackend(tmp_path / "state.sqlite"), "existing-program-ledger")
    assert fresh.job(scope)["pins"]["prompts"]["text"] == "exact pinned"
    assert asyncio.run(DurableEffectBroker(fresh, blobs).execute(scope, lease, "taxonomy-query", {"name": "Chironomus"}, 70, dispatch)) == first
    assert len(calls) == 1


def test_sent_unknown_never_retries_or_releases_hold(tmp_path):
    store, scope, lease, broker, _ = fixture(tmp_path)
    calls = []

    async def dispatch(*_):
        calls.append(1)
        raise TimeoutError("provider outcome unavailable")

    with pytest.raises(TimeoutError):
        asyncio.run(broker.execute(scope, lease, "query", {}, 70, dispatch))
    with pytest.raises(HeldUnknown):
        asyncio.run(broker.execute(scope, lease, "query", {}, 70, dispatch))
    assert len(calls) == 1
    assert store.budget(scope)["held_micro_usd"] == 70
    with pytest.raises(BudgetExceeded):
        store.reserve_effect(scope, lease, "other", {}, 40)


def test_pinned_proven_no_effect_retry_has_distinct_attempt_and_keeps_charges(tmp_path):
    store, scope, lease, broker, _ = fixture(tmp_path, retry_policy=True)
    calls = []
    async def rejected(attempt, _):
        calls.append(attempt)
        return CapturedResult({"error": "known preexecution rejection"}, 5, outcome="failed_no_effect")
    first = asyncio.run(broker.execute(scope, lease, "retryable", {}, 40, rejected))
    store.retry_effect(scope, lease, first.effect_id)
    async def completed(attempt, _):
        calls.append(attempt)
        return CapturedResult({"accepted": True}, 10)
    second = asyncio.run(broker.execute(scope, lease, "retryable", {}, 40, completed))
    assert first.effect_id == second.effect_id
    assert first.attempt_id != second.attempt_id
    assert len(set(calls)) == 2
    assert store.budget(scope)["settled_micro_usd"] == 15
    assert store.budget(scope)["held_micro_usd"] == 0
    with pytest.raises((HeldUnknown, PermissionError)):
        store.retry_effect(scope, lease, first.effect_id)


def test_predeclared_capture_recovers_without_second_call(tmp_path):
    store, scope, lease, broker, blobs = fixture(tmp_path)
    intent = store.reserve_effect(scope, lease, "query", {}, 70)
    attempt = store.mark_sending(scope, lease, intent["effect_id"])
    envelope = broker.envelope(scope, intent, attempt, CapturedResult({"answer": 42}, 20))
    blobs.put_at(attempt["capture_locator"], envelope)
    # Simulate kill after immutable capture but before the SQL receipt transaction.
    store.hold_unknown(scope, intent["effect_id"], "worker_lost")

    async def forbidden(*_):
        pytest.fail("capture replay must not call the provider")

    receipt = asyncio.run(broker.execute(scope, lease, "query", {}, 70, forbidden))
    assert receipt.typed_payload == {"answer": 42}
    assert store.budget(scope)["held_micro_usd"] == 0
    assert store.budget(scope)["settled_micro_usd"] == 20


def test_binary_raw_capture_roundtrip_replay_and_loss_fail_closed(tmp_path):
    store, scope, lease, broker, blobs = fixture(tmp_path)
    calls = []
    raw = b"\x00\xff\x80raw-provider-envelope"
    async def dispatch(*_):
        calls.append(1)
        return CapturedResult({"answer": 42}, 20, raw_payload=raw)
    receipt = asyncio.run(broker.execute(scope, lease, "binary", {}, 70, dispatch))
    assert receipt.raw_capture is not None
    assert blobs.get(receipt.raw_capture) == raw
    assert asyncio.run(broker.execute(scope, lease, "binary", {}, 70, dispatch)) == receipt
    assert calls == [1]
    blobs._path(receipt.raw_capture.locator).unlink()
    with pytest.raises(FileNotFoundError):
        asyncio.run(broker.execute(scope, lease, "binary", {}, 70, dispatch))
    assert calls == [1]
    assert store.budget(scope)["settled_micro_usd"] == 20


def test_unknown_usage_keeps_hold_and_actual_overrun_halts(tmp_path):
    store, scope, lease, broker, _ = fixture(tmp_path)

    async def unknown(*_):
        return CapturedResult({"ok": True}, None)

    asyncio.run(broker.execute(scope, lease, "unknown-charge", {}, 40, unknown))
    assert store.budget(scope)["held_micro_usd"] == 40

    async def overrun(*_):
        return CapturedResult({"ok": True}, 80)

    asyncio.run(broker.execute(scope, lease, "overrun", {}, 30, overrun))
    assert store.budget(scope)["settled_micro_usd"] == 80
    assert store.budget(scope)["halted"]
    with pytest.raises(BudgetExceeded):
        store.reserve_effect(scope, lease, "blocked", {}, 1)


def test_stale_fence_human_lock_revocation_and_neighbor_progress(tmp_path):
    store, scope, lease, _, _ = fixture(tmp_path)
    store.checkpoint(scope, lease, "country", {"state": "resolved"}, expected_revision=0)
    store.pause(scope, expected_generation=1)
    with pytest.raises(StaleWork):
        store.reserve_effect(scope, lease, "late", {}, 1)
    new_scope = store.correct_fields(scope, ["taxon"], expected_generation=1, new_pins=replace(PinnedRuntime(**store.job(scope)["pins"]), input_digest="corrected-input"))
    assert store.job(new_scope)["fields"]["country"]["checkpoint"]["payload"]["state"] == "resolved"
    reuse = store.job(new_scope)["fields"]["country"]["reuse"]
    assert reuse["reused_from_scope_digest"]
    assert store.job(new_scope)["history"][0]["pins"]["input_digest"] == "input"
    new_lease = store.claim(new_scope, "new-owner", ttl_seconds=30)
    with pytest.raises(StaleWork):
        store.checkpoint(scope, lease, "taxon", {}, expected_revision=0)
    with pytest.raises(StaleWork):
        store.checkpoint(new_scope, new_lease, "taxon", {}, expected_revision=0)
    store.backend.revoke(new_scope)
    with pytest.raises(PermissionError):
        store.reserve_effect(new_scope, new_lease, "denied", {}, 1)


def test_resume_exact_bindings_and_publication_guard_are_scoped(tmp_path):
    store, scope, lease, _, _ = fixture(tmp_path)
    store.checkpoint(scope, lease, "country", {"state": "resolved"}, expected_revision=0)
    guard = store.prepare_publication(scope, lease, "country", expected_field_revision=1, expected_record_revision=0)
    store.validate_publication(scope, guard)
    pins = PinnedRuntime(**store.job(scope)["pins"])
    store.pause(scope, expected_generation=1)
    with pytest.raises(StaleWork):
        store.validate_publication(scope, guard)
    with pytest.raises(StaleWork):
        store.resume(scope, expected_generation=1, pins=replace(pins, settings={"max_tokens": 999}))
    store.resume(scope, expected_generation=1, pins=pins)
    fresh_lease = store.claim(scope, "fresh-owner")
    assert fresh_lease.fence > lease.fence
    with pytest.raises(StaleWork):
        store.validate_publication(scope, guard)


def test_trace_context_persists_and_human_checkpoint_requires_accepted_writer(tmp_path):
    store, scope, lease, _, _ = fixture(tmp_path)
    context = {"trace_id": "1" * 32, "span_id": "2" * 16, "trace_flags": 1}
    store.bind_trace(scope, lease, context)
    store.bind_trace(scope, lease, context)
    with pytest.raises(ValueError):
        store.bind_trace(scope, lease, {**context, "trace_id": "3" * 32})
    checkpoint = store.checkpoint(scope, lease, "country", {"state": "resolved"}, expected_revision=0)
    assert checkpoint["trace_context"] == context
    new_scope = store.correct_fields(scope, ["taxon"], expected_generation=1, new_pins=replace(PinnedRuntime(**store.job(scope)["pins"]), input_digest="human-updated-input"))
    assert store.job(new_scope)["history"][0]["trace_context"] == context
    with pytest.raises(PermissionError):
        store.accept_human_checkpoint(new_scope, "taxon", {"state": "supported"}, expected_field_revision=1, canonical_commit_reference="decision", verify_commit=lambda *_: False)
    human = store.accept_human_checkpoint(new_scope, "taxon", {"state": "supported"}, expected_field_revision=1, canonical_commit_reference="canonical-decision-1", verify_commit=lambda _, ref, payload: ref == "canonical-decision-1" and payload["state"] == "supported")
    assert human["authority"] == "canonical_human_decision"
    assert store.job(new_scope)["fields"]["taxon"]["work_state"] == "resolved"


def test_cross_scope_and_immutable_blob_mismatch(tmp_path):
    store, scope, lease, _, blobs = fixture(tmp_path)
    with pytest.raises(PermissionError):
        store.job(replace(scope, collection_id="other"))
    ref = blobs.put_at("capture/scope/attempt", b"original")
    with pytest.raises(ValueError):
        blobs.put_at("capture/scope/attempt", b"different")
    assert blobs.get(ref) == b"original"


def test_gcs_protocol_pins_generation_precondition_checksum_and_namespace():
    from google.api_core.exceptions import NotFound, PreconditionFailed
    class Bucket:
        def __init__(self):
            self.objects, self.calls = {}, []
        def blob(self, locator, generation=None):
            return Blob(self, locator, generation)
    class Blob:
        def __init__(self, bucket, locator, generation):
            self.bucket, self.locator, self.generation = bucket, locator, generation
            self.metadata, self.size = None, None
        def upload_from_string(self, data, **kwargs):
            self.bucket.calls.append(("upload", kwargs))
            assert kwargs["if_generation_match"] == 0 and kwargs["checksum"] == "crc32c"
            if self.locator in self.bucket.objects:
                raise PreconditionFailed("object already exists")
            self.bucket.objects[self.locator] = (data, 17, dict(self.metadata))
        def reload(self, **kwargs):
            if self.locator not in self.bucket.objects:
                raise NotFound("absent")
            data, generation, metadata = self.bucket.objects[self.locator]
            if self.generation is not None and self.generation != generation:
                raise PreconditionFailed("generation changed before body read")
            self.size, self.generation, self.metadata = len(data), generation, metadata
        def download_as_bytes(self, **kwargs):
            pytest.fail("Immutable adapter must stream into the bounded sink")
        def download_to_file(self, sink, **kwargs):
            self.bucket.calls.append(("download", kwargs))
            data, generation, _ = self.bucket.objects[self.locator]
            if self.generation != generation or kwargs["if_generation_match"] != generation:
                raise PreconditionFailed("generation changed")
            assert kwargs["checksum"] == "crc32c" and kwargs["raw_download"] is True
            assert kwargs["start"] == 0 and kwargs["end"] == len(data)-1
            sink.write(data)
    bucket = Bucket()
    blobs = GcsImmutableBlobs(bucket, maximum_bytes=20)
    assert blobs.discover("research-capture/absent") is None
    reference = blobs.put_at("research-capture/attempt", b"raw")
    assert reference.generation == "17"
    assert blobs.get(reference) == b"raw"
    assert blobs.put_at(reference.locator, b"raw") == reference
    with pytest.raises(ValueError):
        blobs.put_at(reference.locator, b"changed")
    with pytest.raises(PreconditionFailed):
        blobs.get(replace(reference, generation="18"))
    with pytest.raises(ValueError):
        blobs.get(replace(reference, sha256="0" * 64))
    with pytest.raises(ValueError):
        blobs.put_at("other/data", b"raw")
    with pytest.raises(ValueError):
        blobs.put_at("research-capture/oversize", b"x" * 21)


def test_publication_guard_retains_exact_checkpoint_basis(tmp_path):
    store, scope, lease, broker, _ = fixture(tmp_path)
    async def dispatch(*_):
        return CapturedResult({"answer": 42}, 10)
    receipt = asyncio.run(broker.execute(scope, lease, "basis", {}, 20, dispatch))
    checkpoint = store.checkpoint(scope, lease, "country", {"state": "resolved"}, expected_revision=0, receipt_ids=(receipt.effect_id,))
    guard = store.prepare_publication(scope, lease, "country", expected_field_revision=1, expected_record_revision=0)
    assert guard["receipt_ids"] == checkpoint["receipt_ids"]
    with pytest.raises(StaleWork):
        store.prepare_publication(scope, lease, "country", expected_field_revision=1, expected_record_revision=0, receipt_ids=("different",))
    with pytest.raises(StaleWork):
        store.validate_publication(scope, {**guard, "record_revision": 2})
    with pytest.raises(StaleWork):
        store.validate_publication(scope, {**guard, "receipt_ids": []})


def test_consumed_dependency_digest_and_correction_closure_are_atomic(tmp_path):
    store, scope, lease, _, _ = fixture(tmp_path)
    resolution = {"field_key": "taxon", "value": "Chironomus"}
    store.checkpoint(scope, lease, "taxon", {"resolution": resolution}, expected_revision=0)
    with pytest.raises(StaleWork):
        store.checkpoint(scope, lease, "country", {}, expected_revision=0, dependencies={"taxon": 1}, dependency_digests={"taxon": "forged"})
    with pytest.raises(ValueError):
        store.checkpoint(scope, lease, "country", {}, expected_revision=0, dependencies={"taxon": 1})
    store.checkpoint(scope, lease, "country", {"state": "resolved"}, expected_revision=0, dependencies={"taxon": 1}, dependency_digests={"taxon": digest(resolution)})
    guard = store.prepare_publication(scope, lease, "country", expected_field_revision=1, expected_record_revision=0)
    assert "pins" not in guard and guard["binding_digest"] == digest(store.job(scope)["pins"])
    assert guard["dependency_digests"] == {"taxon": digest(resolution)}
    pins = replace(PinnedRuntime(**store.job(scope)["pins"]), input_digest="corrected-taxon")
    with pytest.raises(ValueError):
        store.correct_fields(scope, ["taxon"], expected_generation=1, new_pins=pins)
    store.checkpoint(scope, lease, "taxon", {"resolution": {**resolution, "value": "Changed"}}, expected_revision=1)
    with pytest.raises(StaleWork):
        store.validate_publication(scope, guard)
    corrected = store.correct_fields(scope, ["taxon"], expected_generation=1, new_pins=pins, invalidated_fields=("country",))
    assert store.job(corrected)["fields"]["country"]["checkpoint"] is None


def test_dependency_changed_payload_between_read_and_cas_is_rejected(tmp_path):
    store, scope, lease, _, _ = fixture(tmp_path)
    resolution = {"field_key": "taxon", "value": "Original"}
    store.checkpoint(scope, lease, "taxon", {"resolution": resolution}, expected_revision=0)
    backend = store.backend
    original_cas = backend.cas
    raced = []
    def race(current_scope, program_key, revision, state, **kwargs):
        if not raced:
            raced.append(True)
            current = backend.load(current_scope, program_key)
            current.state["jobs"][scope.key]["fields"]["taxon"]["checkpoint"]["payload"]["resolution"]["value"] = "Changed at same revision"
            original_cas(current_scope, program_key, current.revision, current.state)
        return original_cas(current_scope, program_key, revision, state, **kwargs)
    backend.cas = race
    with pytest.raises(StaleWork):
        store.checkpoint(scope, lease, "country", {}, expected_revision=0, dependencies={"taxon": 1}, dependency_digests={"taxon": digest(resolution)})
    assert raced == [True]
    assert store.job(scope)["fields"]["country"]["checkpoint"] is None


def test_checkpoint_batch_commits_sibling_dependency_or_nothing(tmp_path):
    store, scope, lease, _, _ = fixture(tmp_path)
    source = {"field_key": "taxon", "work_state": "resolved", "value": "source"}
    entries = [
        {"field_key": "country", "payload": {"resolution": {"work_state": "resolved", "value": "derived"}}, "expected_revision": 0,
         "dependencies": {"taxon": 1}, "dependency_digests": {"taxon": digest(source)}},
        {"field_key": "taxon", "payload": {"resolution": source}, "expected_revision": 0},
    ]
    bad = json.loads(json.dumps(entries))
    bad[0]["dependency_digests"]["taxon"] = "wrong"
    with pytest.raises(StaleWork):
        store.checkpoint_batch(scope, lease, bad)
    assert store.job(scope)["checkpoints"] == []
    cyclic = json.loads(json.dumps(entries))
    cyclic[1].update(dependencies={"country": 1}, dependency_digests={"country": "cyclic"})
    with pytest.raises(ValueError):
        store.checkpoint_batch(scope, lease, cyclic)
    committed = store.checkpoint_batch(scope, lease, entries)
    assert [c["field_key"] for c in committed] == ["country", "taxon"]
    assert committed[1]["sequence"] == 1 and committed[0]["sequence"] == 2
    assert store.job(scope)["fields"]["country"]["work_state"] == "resolved"


def test_overrun_stops_already_reserved_and_sending_siblings_but_replays_capture(tmp_path):
    store, scope, lease, broker, _ = fixture(tmp_path)
    first = store.reserve_effect(scope, lease, "first", {}, 20)
    reserved = store.reserve_effect(scope, lease, "reserved", {}, 20)
    sending = store.reserve_effect(scope, lease, "sending", {}, 20)
    sent_attempt = store.mark_sending(scope, lease, sending["effect_id"])
    async def overrun(*_):
        return CapturedResult({"answer": 42}, 40)
    completed = asyncio.run(broker.execute(scope, lease, "first", {}, 20, overrun))
    assert completed.effect_id == first["effect_id"]
    with pytest.raises(BudgetExceeded):
        store.mark_sending(scope, lease, reserved["effect_id"])
    with pytest.raises(BudgetExceeded):
        store.validate_dispatch(scope, lease, sending["effect_id"], sent_attempt["attempt_id"])
    assert store.budget(scope)["held_micro_usd"] == 40
    async def forbidden(*_):
        pytest.fail("completed overrun capture replay called provider")
    assert asyncio.run(broker.execute(scope, lease, "first", {}, 20, forbidden)) == completed


def test_live_allowed_program_without_live_authority_cannot_authorize_live_or_viewer_mutation(tmp_path):
    backend = SqliteStateBackend(tmp_path / "authority.sqlite")
    scope = DurabilityScope("org", "collection", "specimen", "job", 1, "actor", False)
    backend.grant(scope)
    store = ResearchStore(backend, "caller-invented-program")
    store.initialize(scope, BudgetPolicy(100, external_ledger_digest="fabricated", live_authorized=True, hold_reason=None))
    pins = PinnedRuntime("input", {}, {}, {}, {}, {}, "engine")
    store.create_job(scope, pins, ["taxon"])
    lease = store.claim(scope, "owner")
    with pytest.raises(PermissionError, match="research_live_authority_required"):
        store.reserve_effect(scope, lease, "live", {}, 10, execution_class="live")
    backend.grant(scope, role="viewer")
    assert store.job(scope)["pins"] == pins.payload()
    with pytest.raises(PermissionError):
        store.reserve_effect(scope, lease, "offline", {}, 10)


def test_sql_connect_exact_serialization_survives_any_numeric_rehydration(tmp_path):
    store, scope, _, _, _ = fixture(tmp_path)
    state = store._read(scope).state
    state["jobs"][scope.key]["pins"]["settings"]["temperature"] = 1.0
    projected = json.loads(json.dumps(state), parse_int=float)
    class Repository:
        def variables(self, scope):
            return {"actorUid": scope.actor_uid}
        def execute(self, *_args, **_kwargs):
            return {"read": {"researchHarnessState": {"revision": 1, "observedAt": "2026-09-29T12:00:00Z", "state": projected, "stateJson": json.dumps(state)}}}
    restored = SqlConnectStateBackend(Repository()).load(scope, store.program_key)
    assert type(restored.state["jobs"][scope.key]["generation"]) is int
    assert type(restored.state["jobs"][scope.key]["pins"]["settings"]["temperature"]) is float
    assert digest(restored.state) == digest(state)


def test_shared_imported_ledger_does_not_reset(tmp_path):
    store, scope, lease, _, _ = fixture(tmp_path, external_held=70)
    with pytest.raises(BudgetExceeded):
        store.reserve_effect(scope, lease, "too-much", {}, 40)
    with pytest.raises(ValueError):
        store.initialize(scope, BudgetPolicy(100))


def test_concurrent_reservations_are_one_atomic_program_hold(tmp_path):
    store, scope, lease, _, _ = fixture(tmp_path)

    def reserve(i):
        try:
            return store.reserve_effect(scope, lease, str(i), {}, 60)
        except BudgetExceeded:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(8)))
    assert sum(x is not None for x in results) == 1
    assert store.budget(scope)["held_micro_usd"] == 60


def test_disjoint_field_checkpoint_cas_rebases_without_effect(tmp_path):
    store, scope, lease, _, _ = fixture(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda field: store.checkpoint(scope, lease, field, {"state": "resolved"}, expected_revision=0), ["taxon", "country"]))
    assert {r["field_key"] for r in results} == {"taxon", "country"}
    assert len(store.job(scope)["checkpoints"]) == 2
    assert store.budget(scope)["held_micro_usd"] == 0


def test_journal_media_protocol_roundtrip_and_scope(tmp_path):
    from pydantic_ai.messages import ModelRequest, UserPromptPart
    from pydantic_ai_harness.media import MediaContext
    from pydantic_ai_harness.step_persistence import ContinuableSnapshot, RunRecord, StepEvent, ToolEffectRecord
    store, scope, _, _, blobs = fixture(tmp_path)
    journal = SqlConnectStepStore(store, scope, blobs, agent_name="specimen_taxonomy")
    media = GcsMediaStore(store, scope, blobs)

    async def exercise():
        run = RunRecord(run_id="native-1", agent_name="specimen_taxonomy", conversation_id="conversation", registration_id="registration")
        await journal.register_run(run)
        await journal.register_run(run)
        event = StepEvent(run_id="native-1", kind="run_started", step_index=0, idempotency_key="start")
        await journal.append_event(event)
        await journal.append_event(event)
        assert await journal.list_events(run_id="native-1") == [event]
        complete = ContinuableSnapshot(run_id="native-1", step_index=1, messages=[ModelRequest(parts=[UserPromptPart(content="Pinned synthetic message")])], idempotency_key="complete")
        await journal.save_snapshot(complete)
        interrupted = ContinuableSnapshot(run_id="native-1", step_index=2, messages=[], state="interrupted", idempotency_key="interrupted")
        await journal.save_snapshot(interrupted)
        assert await journal.latest_snapshot(run_id="native-1") == complete
        assert await journal.latest_snapshot(run_id="native-1", include_interrupted=True) == interrupted
        assert await journal.get_run(run_id="native-1") == run
        assert await journal.list_runs(parent_run_id="not-parent", conversation_id="conversation") == []
        assert await journal.list_runs(conversation_id="conversation") == [run]
        tool = ToolEffectRecord(run_id="native-1", tool_call_id="tool-1", tool_name="taxonomy", status="started", idempotency_key="logical")
        await journal.record_tool_effect(tool)
        assert await journal.list_unresolved_tool_effects(run_id="native-1") == [tool]
        assert await journal.get_tool_effect(run_id="native-1", tool_call_id="tool-1") == tool
        await journal.record_tool_effect(replace(tool, status="completed"))
        assert await journal.list_unresolved_tool_effects(run_id="native-1") == []
        uri = await media.put(b"synthetic pixels", context=MediaContext(metadata={"classification": "synthetic"}))
        assert uri.startswith("media+sha256://")
        assert await media.get(uri) == b"synthetic pixels"
        assert await media.exists(uri)
        assert await media.public_url(uri) is None
        assert await media.get_metadata(uri) == {"classification": "synthetic"}
        assert not await media.exists("media+sha256://missing")
        with pytest.raises(PermissionError):
            await SqlConnectStepStore(store, scope, blobs, agent_name="specimen_geography").get_run(run_id="native-1")

    asyncio.run(exercise())


def test_official_frontier_snapshot_order_uses_capture_sequence_not_graph_step(tmp_path):
    from pydantic_ai_harness.step_persistence import ContinuableSnapshot, RunRecord
    store, scope, _, _, blobs = fixture(tmp_path)
    journal = SqlConnectStepStore(store, scope, blobs, agent_name="specimen_taxonomy")
    async def exercise():
        await journal.register_run(RunRecord(run_id="frontier", agent_name="specimen_taxonomy", registration_id="registration"))
        frontier = ContinuableSnapshot(run_id="frontier", step_index=3, messages=[], idempotency_key="0:3:complete")
        await journal.save_snapshot(frontier)
        lagging_graph = ContinuableSnapshot(run_id="frontier", step_index=2, messages=[], idempotency_key="1:2:complete")
        await journal.save_snapshot(lagging_graph)
        assert await journal.latest_snapshot(run_id="frontier") == lagging_graph
        await journal.save_snapshot(replace(frontier))
        assert await journal.latest_snapshot(run_id="frontier") == lagging_graph
    asyncio.run(exercise())


def test_live_dispatch_defaults_to_external_hold(tmp_path):
    store, scope, lease, _, _ = fixture(tmp_path)
    with pytest.raises(PermissionError):
        store.reserve_effect(scope, lease, "live", {}, 1, execution_class="live")


def native_fixture(tmp_path):
    """Only an explicitly selected, disposable loopback demo emulator."""
    host = os.environ.get("RESEARCH_TEST_SQL_EMULATOR_HOST")
    if not host:
        pytest.skip("native PostgreSQL/SQL Connect proof needs the owned local emulator")
    if not re.fullmatch(r"127\.0\.0\.1:[0-9]{1,5}", host):
        raise ValueError("Native test refuses cloud/non-loopback endpoints")
    import requests
    from specimen_digitization.application.production import SqlConnectRepository, actor_uid
    organization, collection, specimen = (str(uuid4()) for _ in range(3))
    scope = DurabilityScope(organization, collection, specimen, str(uuid4()), 1, "synthetic-worker", False)
    session = requests.Session()
    session.headers["Authorization"] = "Bearer owner"
    service = f"http://{host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service"
    def raw(query):
        response = session.post(service + ":executeGraphql", json={"query": query}, timeout=30)
        response.raise_for_status()
        result = response.json()
        assert not result.get("errors") and not result.get("code"), result
        return result.get("data")
    raw(f'''mutation @transaction {{
        organization_insert(data:{{id:"{organization}",name:"Synthetic durability"}})
        collection_insert(data:{{organizationId:"{organization}",id:"{collection}",name:"Synthetic insects"}})
        organizationMember_insert(data:{{organizationId:"{organization}",uid:"synthetic-worker",active:true}})
        collectionMember_insert(data:{{organizationId:"{organization}",collectionId:"{collection}",uid:"synthetic-worker",active:true,role:"operator",canViewSensitive:false}})
        specimen_insert(data:{{organizationId:"{organization}",collectionId:"{collection}",id:"{specimen}",revision:1,state:"running",sensitive:false,createdBy:"synthetic-worker"}})
    }}''')
    actor_uid.set(scope.actor_uid)
    backend = SqlConnectStateBackend(SqlConnectRepository(project="demo-specimen-data", emulator_host=host, session=session))
    store = ResearchStore(backend, "existing-shared-program/" + str(uuid4()))
    store.initialize(scope, BudgetPolicy(100, external_ledger_digest="synthetic-import"))
    pins = PinnedRuntime("input", {"version": "p1"}, {"text": "exact pinned"}, {"version": "s1"},
                         {"route": "harness-deepseek"}, {"max_tokens": 128}, "specialist_harness_v2")
    store.create_job(scope, pins, ["taxon", "country"])
    lease = store.claim(scope, "owner", ttl_seconds=60)
    return store, scope, lease, ImmutableFileBlobs(tmp_path / "native-blobs"), raw


def test_native_sql_atomic_budget_fence_rebase_replay_and_revocation(tmp_path):
    from specimen_digitization.application.production import actor_uid
    store, scope, lease, blobs, raw = native_fixture(tmp_path)
    def reserve(i):
        actor_uid.set(scope.actor_uid)
        try:
            return store.reserve_effect(scope, lease, "concurrent-" + str(i), {}, 60)
        except BudgetExceeded:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        reservations = list(pool.map(reserve, range(4)))
    assert sum(e is not None for e in reservations) == 1
    intent = next(e for e in reservations if e)
    assert store.budget(scope)["held_micro_usd"] == 60
    attempt = store.mark_sending(scope, lease, intent["effect_id"])
    broker = DurableEffectBroker(store, blobs)
    blobs.put_at(attempt["capture_locator"], broker.envelope(scope, intent, attempt, CapturedResult({"taxon": "Chironomus"}, 10)))
    async def forbidden(*_):
        pytest.fail("native receipt capture replay called provider")
    receipt = asyncio.run(broker.execute(scope, lease, intent["operation_key"], {}, 60, forbidden))
    assert receipt.typed_payload == {"taxon": "Chironomus"}
    assert store.budget(scope)["settled_micro_usd"] == 10
    def checkpoint(field):
        actor_uid.set(scope.actor_uid)
        return store.checkpoint(scope, lease, field, {"state": "resolved"}, expected_revision=0, receipt_ids=(receipt.effect_id,))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(checkpoint, ["taxon", "country"]))
    assert len(store.job(scope)["checkpoints"]) == 2
    with pytest.raises(StaleWork):
        store.claim(scope, "other-owner")
    raw(f'''mutation {{collectionMember_update(key:{{organizationId:"{scope.organization_id}",collectionId:"{scope.collection_id}",uid:"synthetic-worker"}},data:{{active:false}})}}''')
    with pytest.raises(Exception):
        store.reserve_effect(scope, lease, "revoked", {}, 1)


def test_native_sql_clock_rejects_expired_commit_and_journal_roundtrip(tmp_path):
    import time
    from pydantic_ai_harness.step_persistence import RunRecord, ContinuableSnapshot
    store, scope, lease, blobs, _ = native_fixture(tmp_path)
    doc = store.backend.load(scope, store.program_key)
    assert abs(doc.server_time - time.time()) < 30
    with pytest.raises(StaleWork):
        store.backend.cas(scope, store.program_key, doc.revision, doc.state, valid_until=doc.server_time - 1)
    async def exercise():
        journal = SqlConnectStepStore(store, scope, blobs, agent_name="specimen_taxonomy")
        run = RunRecord(run_id=str(uuid4()), agent_name="specimen_taxonomy", registration_id="registration")
        await journal.register_run(run)
        snapshot = ContinuableSnapshot(run_id=run.run_id, step_index=1, messages=[], idempotency_key="snapshot")
        await journal.save_snapshot(snapshot)
        assert await journal.latest_snapshot(run_id=run.run_id) == snapshot
        assert await journal.get_run(run_id=run.run_id) == run
    asyncio.run(exercise())


def test_native_sql_review_authority_generation_reuse_and_raw_replay(tmp_path):
    store, scope, lease, blobs, raw = native_fixture(tmp_path)
    async def dispatch(*_):
        return CapturedResult({"answer": 42}, 10, raw_payload=b"\x00\xffnative-raw")
    broker = DurableEffectBroker(store, blobs)
    receipt = asyncio.run(broker.execute(scope, lease, "binary", {}, 20, dispatch))
    assert blobs.get(receipt.raw_capture) == b"\x00\xffnative-raw"
    async def forbidden(*_):
        pytest.fail("receipt replay dispatched a provider")
    assert asyncio.run(broker.execute(scope, lease, "binary", {}, 20, forbidden)) == receipt
    store.checkpoint(scope, lease, "country", {"state": "resolved"}, expected_revision=0, receipt_ids=(receipt.effect_id,))
    pins = replace(PinnedRuntime(**store.job(scope)["pins"]), input_digest="reviewed-new-input")
    with pytest.raises(Exception):
        store.correct_fields(scope, ["taxon"], expected_generation=1, new_pins=pins)
    assert store.job(scope)["generation"] == 1
    raw(f'''mutation {{collectionMember_update(key:{{organizationId:"{scope.organization_id}",collectionId:"{scope.collection_id}",uid:"synthetic-worker"}},data:{{role:"reviewer"}})}}''')
    corrected = store.correct_fields(scope, ["taxon"], expected_generation=1, new_pins=pins)
    current = store.job(corrected)
    assert current["generation"] == 2
    assert current["fields"]["taxon"]["locked"]
    assert current["fields"]["taxon"]["work_state"] == "waiting_human"
    assert current["fields"]["country"]["reuse"]["checkpoint_digest"]
    assert current["fields"]["country"]["checkpoint"] == current["history"][0]["fields"]["country"]["checkpoint"]
    with pytest.raises(StaleWork):
        asyncio.run(broker.execute(scope, lease, "binary", {}, 20, forbidden))


@pytest.mark.parametrize("native", [False, True], ids=["sqlite", "sql-connect"])
@pytest.mark.parametrize("window", ["before_reservation", "after_reservation", "after_sending", "after_capture", "after_receipt", "after_checkpoint"])
def test_abrupt_subprocess_loss_at_effect_boundaries(tmp_path, native, window):
    if native:
        store, scope, lease, blobs, _ = native_fixture(tmp_path)
    else:
        store, scope, lease, _, blobs = fixture(tmp_path)
    config = {"scope": asdict(scope), "lease": asdict(lease), "program_key": store.program_key,
              "blob_dir": str(blobs.directory), "window": window,
              "accepted_file": str(tmp_path / "provider-accepted"),
              "sql_path": None if native else store.backend.path,
              "emulator_host": os.environ.get("RESEARCH_TEST_SQL_EMULATOR_HOST") if native else None}
    worker = '''
import json, os, sys
from pathlib import Path
from specimen_digitization.research_harness.persistence import *
c = json.loads(sys.argv[1])
scope, lease = DurabilityScope(**c['scope']), Lease(**c['lease'])
if c['sql_path']:
    backend = SqliteStateBackend(c['sql_path'])
else:
    from specimen_digitization.application.production import SqlConnectRepository, actor_uid
    actor_uid.set(scope.actor_uid)
    backend = SqlConnectStateBackend(SqlConnectRepository(project='demo-specimen-data', emulator_host=c['emulator_host']))
store = ResearchStore(backend, c['program_key'])
blobs = ImmutableFileBlobs(c['blob_dir'])
broker = DurableEffectBroker(store, blobs)
if c['window'] == 'before_reservation': os._exit(17)
intent = store.reserve_effect(scope, lease, 'subprocess-effect', {}, 70)
if c['window'] == 'after_reservation': os._exit(17)
attempt = store.mark_sending(scope, lease, intent['effect_id'])
Path(c['accepted_file']).write_text(attempt['attempt_id'])
if c['window'] == 'after_sending': os._exit(17)
reference = blobs.put_at(attempt['capture_locator'], broker.envelope(scope, intent, attempt, CapturedResult({'answer': 42}, 20)))
if c['window'] == 'after_capture': os._exit(17)
receipt = broker._finish_capture(scope, intent, attempt, reference)
if c['window'] == 'after_receipt': os._exit(17)
store.checkpoint(scope, lease, 'country', {'state': 'resolved'}, expected_revision=0, receipt_ids=(receipt.effect_id,))
os._exit(17)
'''
    process = subprocess.run([sys.executable, "-c", worker, json.dumps(config)], capture_output=True, text=True, timeout=30)
    assert process.returncode == 17, process.stderr
    calls = []
    async def dispatch(*_):
        calls.append(1)
        return CapturedResult({"answer": 42}, 20)
    broker = DurableEffectBroker(store, blobs)
    if window == "after_sending":
        with pytest.raises(HeldUnknown):
            asyncio.run(broker.execute(scope, lease, "subprocess-effect", {}, 70, dispatch))
        assert store.budget(scope)["held_micro_usd"] == 70
    else:
        receipt = asyncio.run(broker.execute(scope, lease, "subprocess-effect", {}, 70, dispatch))
        assert receipt.typed_payload == {"answer": 42}
        assert store.budget(scope)["settled_micro_usd"] == 20
    assert len(calls) == (1 if window in {"before_reservation", "after_reservation"} else 0)
    if window == "after_checkpoint":
        assert store.job(scope)["fields"]["country"]["checkpoint"]["payload"]["state"] == "resolved"


def test_parallel_completed_sibling_survives_unknown_effect(tmp_path):
    store, scope, lease, broker, _ = fixture(tmp_path)
    async def complete(*_):
        return CapturedResult({"taxon": "Chironomus"}, 10)
    async def unknown(*_):
        raise TimeoutError("synthetic accepted outcome missing")
    async def run():
        return await asyncio.gather(
            broker.execute(scope, lease, "taxon", {}, 30, complete, field_keys=("taxon",)),
            broker.execute(scope, lease, "country", {}, 30, unknown, field_keys=("country",)),
            return_exceptions=True,
        )
    good, failure = asyncio.run(run())
    assert isinstance(failure, TimeoutError)
    store.checkpoint(scope, lease, "taxon", {"state": "resolved"}, expected_revision=0, receipt_ids=(good.effect_id,))
    assert store.job(scope)["fields"]["country"]["work_state"] == "operational_failed"
    assert store.job(scope)["fields"]["taxon"]["checkpoint"]["payload"]["state"] == "resolved"
    assert store.budget(scope)["settled_micro_usd"] == 10
    assert store.budget(scope)["held_micro_usd"] == 30


def test_broker_denies_locked_fields_and_preserves_reserved_holds(tmp_path):
    store, scope, lease, _, _ = fixture(tmp_path)
    corrected = store.correct_fields(scope, ["taxon"], expected_generation=1, new_pins=replace(PinnedRuntime(**store.job(scope)["pins"]), input_digest="corrected"))
    lease = store.claim(corrected, "next")
    with pytest.raises(StaleWork):
        store.reserve_effect(corrected, lease, "locked", {}, 20, field_keys=("taxon",))
    with pytest.raises(StaleWork):
        store.reserve_effect(corrected, lease, "unattributed", {}, 20)
    first = store.reserve_effect(corrected, lease, "reserved", {}, 20, field_keys=("country",))
    second = store.reserve_effect(corrected, lease, "sending", {}, 20, field_keys=("country",))
    attempt = store.mark_sending(corrected, lease, second["effect_id"])
    store._mutate(corrected, lambda state, _: state["jobs"][corrected.key]["fields"]["country"].update(locked=True))
    with pytest.raises(StaleWork):
        store.mark_sending(corrected, lease, first["effect_id"])
    with pytest.raises(StaleWork):
        store.validate_dispatch(corrected, lease, second["effect_id"], attempt["attempt_id"])
    assert store.budget(corrected)["held_micro_usd"] == 40


@pytest.mark.parametrize("tamper", ["link", "history", "receipt"])
def test_reused_publication_accepts_only_exact_history_and_receipt_basis(tmp_path, tamper):
    store, scope, lease, broker, _ = fixture(tmp_path)
    async def dispatch(*_):
        return CapturedResult({"country": "United States"}, 10)
    receipt = asyncio.run(broker.execute(scope, lease, "country", {}, 20, dispatch, field_keys=("country",)))
    store.checkpoint(scope, lease, "country", {"state": "resolved"}, expected_revision=0, receipt_ids=(receipt.effect_id,))
    corrected = store.correct_fields(scope, ["taxon"], expected_generation=1, new_pins=replace(PinnedRuntime(**store.job(scope)["pins"]), input_digest="reviewed-correction"))
    fresh = store.claim(corrected, "next")
    guard = store.prepare_publication(corrected, fresh, "country", expected_field_revision=1, expected_record_revision=0)
    assert guard["checkpoint_basis"]["reused"]
    assert guard["receipt_bindings"][receipt.effect_id]["scope"] == scope.identity()
    store.validate_publication(corrected, guard)
    with pytest.raises(StaleWork):
        store.prepare_publication(corrected, fresh, "country", expected_field_revision=1, expected_record_revision=0, receipt_ids=("arbitrary-old-receipt",))
    def corrupt(state, _):
        job = state["jobs"][corrected.key]
        if tamper == "link":
            job["fields"]["country"]["reuse"]["checkpoint_digest"] = "changed"
        elif tamper == "history":
            job["history"][0]["fields"]["country"]["checkpoint"]["payload"] = {"state": "invented"}
        else:
            state["effects"][receipt.effect_id]["binding_digest"] = "other-runtime"
    store._mutate(corrected, corrupt)
    with pytest.raises((StaleWork, PermissionError)):
        store.validate_publication(corrected, guard)


def test_retry_admission_is_atomic_single_field_idempotent_and_fresh_acl(tmp_path):
    store, scope, lease, _, _ = fixture(tmp_path)
    store.checkpoint(scope, lease, "taxon", {"state": "resolved"}, expected_revision=0)
    store.checkpoint(scope, lease, "country", {"state": "operational_failed"}, expected_revision=0)
    neighbor = store.job(scope)["fields"]["taxon"]
    arguments = dict(expected_generation=1, expected_field_revision=1, idempotency_key="server-stable", execution_class="offline")
    with pytest.raises(PermissionError, match="research_live_authority_required"):
        store.admit_retry(scope, "country", **{k:v for k,v in arguments.items() if k != "execution_class"})
    with ThreadPoolExecutor(max_workers=4) as pool:
        commands = list(pool.map(lambda _:store.admit_retry(scope, "country", **arguments), range(4)))
    assert all(command == commands[0] for command in commands)
    assert commands[0]["status"] == "queued"
    assert store.job(scope)["fields"]["country"]["work_state"] == "retry_scheduled"
    assert store.job(scope)["fields"]["country"]["checkpoint"]["payload"]["state"] == "operational_failed"
    assert store.job(scope)["fields"]["taxon"] == neighbor
    with pytest.raises(StaleWork):
        store.admit_retry(scope, "taxon", **arguments)
    with pytest.raises(StaleWork):
        store.admit_retry(scope, "country", **{**arguments, "idempotency_key":"different"})
    store.backend.grant(scope, role="viewer")
    with pytest.raises(PermissionError):
        store.admit_retry(scope, "country", **arguments)


@pytest.mark.parametrize("barrier", ["paused", "locked", "halted", "unknown_cost", "stale_revision"])
def test_retry_admission_denies_unsafe_states(tmp_path, barrier):
    store, scope, lease, broker, _ = fixture(tmp_path)
    store.checkpoint(scope, lease, "country", {"state":"operational_failed"}, expected_revision=0)
    if barrier == "paused":
        store.pause(scope, expected_generation=1)
    elif barrier == "locked":
        store._mutate(scope, lambda state,_:state["jobs"][scope.key]["fields"]["country"].update(locked=True))
    elif barrier == "halted":
        store._mutate(scope, lambda state,_:state.update(halted=True))
    elif barrier == "unknown_cost":
        async def unknown(*_):
            return CapturedResult({"answer":42}, None)
        asyncio.run(broker.execute(scope, lease, "unknown-usage", {}, 20, unknown, field_keys=("country",)))
    with pytest.raises((StaleWork, BudgetExceeded, HeldUnknown)):
        store.admit_retry(scope, "country", expected_generation=1, expected_field_revision=0 if barrier=="stale_revision" else 1, idempotency_key="server-stable", execution_class="offline")


def retry_command_fixture(tmp_path):
    store, scope, lease, broker, blobs = fixture(tmp_path)
    store.checkpoint(scope, lease, "country", {"state":"operational_failed"}, expected_revision=0)
    command = store.admit_retry(scope, "country", expected_generation=1, expected_field_revision=1, idempotency_key="server-stable", execution_class="offline")
    return store, scope, lease, command, broker


def test_retry_consumer_exact_checkpoint_and_lost_ack_are_idempotent(tmp_path):
    store, scope, lease, command, _ = retry_command_fixture(tmp_path)
    running = store.claim_retry_command(scope, lease, command["id"])
    assert running["status"] == "running" and running["lease"] == asdict(lease)
    assert not store._read(scope).state["outbox"]["retry/"+command["id"]]["delivered"]
    assert store.claim_retry_command(scope, lease, command["id"]) == running
    payload = {"state":"resolved"}
    checkpoint = store.checkpoint(scope, lease, "country", payload, expected_revision=1, retry_command_id=command["id"])
    assert checkpoint["retry_command_id"] == command["id"] and checkpoint["lease_fence"] == lease.fence
    assert store.checkpoint(scope, lease, "country", payload, expected_revision=1, retry_command_id=command["id"]) == checkpoint
    store._mutate(scope, lambda state,_:state.update(halted=True))
    recovered = store.claim_retry_command(scope, lease, command["id"])
    assert recovered["result_checkpoint_id"] == checkpoint["id"]
    completed = store.complete_retry_command(scope, lease, command["id"], checkpoint_id=checkpoint["id"])
    assert completed["status"] == "completed"
    assert store._read(scope).state["outbox"]["retry/"+command["id"]]["delivered"]
    store._mutate(scope, lambda state,_:state["outbox"]["retry/"+command["id"]].update(delivered=False))
    assert store.complete_retry_command(scope, lease, command["id"], checkpoint_id=checkpoint["id"]) == completed
    assert store._read(scope).state["outbox"]["retry/"+command["id"]]["delivered"]
    store._mutate(scope, lambda state,_:state["outbox"]["retry/"+command["id"]].update(delivered=False))
    store.backend.grant(scope, role="viewer")
    with pytest.raises(PermissionError):
        store.complete_retry_command(scope, lease, command["id"], checkpoint_id=checkpoint["id"])
    assert not store._read(scope).state["outbox"]["retry/"+command["id"]]["delivered"]


def test_retry_consumer_denies_unrelated_or_unpinned_checkpoint(tmp_path):
    store, scope, lease, command, _ = retry_command_fixture(tmp_path)
    store.claim_retry_command(scope, lease, command["id"])
    unrelated = store.checkpoint(scope, lease, "taxon", {"state":"resolved"}, expected_revision=0)
    with pytest.raises(StaleWork):
        store.complete_retry_command(scope, lease, command["id"], checkpoint_id=unrelated["id"])
    with pytest.raises(StaleWork):
        store.checkpoint(scope, lease, "country", {"state":"resolved"}, expected_revision=1)
    with pytest.raises(StaleWork):
        store.checkpoint(scope, lease, "taxon", {}, expected_revision=1, retry_command_id=command["id"])
    with pytest.raises(StaleWork):
        store.checkpoint(scope, lease, "country", {"state":"resolved", "retry_command_id":"forged"}, expected_revision=1, retry_command_id=command["id"])
    blocked = store.complete_retry_command(scope, lease, command["id"], blocked_reason="worker_failed")
    assert blocked["status"] == "blocked"
    assert store._read(scope).state["outbox"]["retry/"+command["id"]]["delivered"]
    assert store.complete_retry_command(scope, lease, command["id"], blocked_reason="worker_failed") == blocked
    with pytest.raises(StaleWork):
        store.complete_retry_command(scope, lease, command["id"], blocked_reason="different_reason")


def test_retry_consumer_new_fence_recovers_committed_result_without_reexecution(tmp_path):
    store, scope, lease, command, _ = retry_command_fixture(tmp_path)
    store.claim_retry_command(scope, lease, command["id"])
    checkpoint = store.checkpoint(scope, lease, "country", {"state":"resolved"}, expected_revision=1, retry_command_id=command["id"])
    pins = PinnedRuntime(**store.job(scope)["pins"])
    store.pause(scope, expected_generation=1)
    store.resume(scope, expected_generation=1, pins=pins)
    fresh = store.claim(scope, "new-owner")
    with pytest.raises(StaleWork):
        store.complete_retry_command(scope, lease, command["id"], checkpoint_id=checkpoint["id"])
    recovered = store.claim_retry_command(scope, fresh, command["id"])
    assert recovered["result_checkpoint_id"] == checkpoint["id"]
    assert recovered["result_lease"]["fence"] == lease.fence
    assert store.complete_retry_command(scope, fresh, command["id"], checkpoint_id=checkpoint["id"])["status"] == "completed"


@pytest.mark.parametrize("barrier", ["halted", "locked", "viewer", "unknown_cost", "sent_unknown"])
def test_retry_claim_rechecks_dispatch_barriers_after_queue_admission(tmp_path, barrier):
    store, scope, lease, command, broker = retry_command_fixture(tmp_path)
    if barrier == "halted":
        store._mutate(scope, lambda state,_:state.update(halted=True))
    elif barrier == "locked":
        store._mutate(scope, lambda state,_:state["jobs"][scope.key]["fields"]["country"].update(locked=True))
    elif barrier == "viewer":
        store.backend.grant(scope, role="viewer")
    else:
        async def dispatch(*_):
            if barrier == "sent_unknown":
                raise TimeoutError("uncertain send")
            return CapturedResult({"answer":42}, None)
        if barrier == "sent_unknown":
            with pytest.raises(TimeoutError):
                asyncio.run(broker.execute(scope, lease, "late-effect", {}, 20, dispatch, field_keys=("country",)))
        else:
            asyncio.run(broker.execute(scope, lease, "late-effect", {}, 20, dispatch, field_keys=("country",)))
    with pytest.raises((StaleWork, PermissionError, BudgetExceeded, HeldUnknown)):
        store.claim_retry_command(scope, lease, command["id"])
    assert store._read(scope).state["outbox"]["retry/"+command["id"]]["command"]["status"] == "queued"


def test_generation_correction_supersedes_queued_and_running_commands(tmp_path):
    store, scope, lease, command, _ = retry_command_fixture(tmp_path)
    store.claim_retry_command(scope, lease, command["id"])
    corrected = store.correct_fields(scope, ["taxon"], expected_generation=1, new_pins=replace(PinnedRuntime(**store.job(scope)["pins"]), input_digest="corrected"))
    state = store._read(corrected).state
    assert state["outbox"]["retry/"+command["id"]]["command"]["blocked_reason"] == "generation_superseded"
    assert state["outbox"]["retry/"+command["id"]]["delivered"]
    assert store.job(corrected)["fields"]["country"]["retry_command_id"] is None
    assert store.job(corrected)["fields"]["country"]["work_state"] == "operational_failed"
    with pytest.raises((StaleWork,PermissionError)):
        store.claim_retry_command(corrected, store.claim(corrected,"next"), command["id"])


@pytest.mark.parametrize("terminal", ["completed", "blocked"])
def test_terminal_retry_claim_repairs_undelivered_flag_only_with_fresh_write_acl(tmp_path, terminal):
    store, scope, lease, command, _ = retry_command_fixture(tmp_path)
    store.claim_retry_command(scope, lease, command["id"])
    if terminal == "completed":
        checkpoint = store.checkpoint(scope, lease, "country", {"state":"resolved"}, expected_revision=1, retry_command_id=command["id"])
        receipt = store.complete_retry_command(scope, lease, command["id"], checkpoint_id=checkpoint["id"])
    else:
        receipt = store.complete_retry_command(scope, lease, command["id"], blocked_reason="worker_failed")
    store._mutate(scope, lambda state,_:state["outbox"]["retry/"+command["id"]].update(delivered=False))
    assert store.claim_retry_command(scope, lease, command["id"]) == receipt
    assert store._read(scope).state["outbox"]["retry/"+command["id"]]["delivered"]
    store._mutate(scope, lambda state,_:state["outbox"]["retry/"+command["id"]].update(delivered=False))
    store.backend.grant(scope, role="viewer")
    with pytest.raises(PermissionError):
        store.claim_retry_command(scope, lease, command["id"])
    assert not store._read(scope).state["outbox"]["retry/"+command["id"]]["delivered"]
