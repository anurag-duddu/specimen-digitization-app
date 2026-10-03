"""SOURCE-AUTHORED, UNRUN: real SQLite effects and immutable fixture bytes.

These tests authorize no native connector, live spend or job reset.
The fixture starts a new disposable local ledger; no production ledger is used.
"""
import asyncio
import hashlib
from dataclasses import asdict, replace
from types import SimpleNamespace
from urllib.parse import unquote, urlparse
from uuid import NAMESPACE_URL, uuid5

import pytest
from pydantic import ValidationError

from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, CollectionProfile, ExactSpecimenJoin, FieldKey, FieldProfile, FieldResolution, LookupStatus,
    PromptPin, ResearchScope, SourceQuery, SpecialistRequest, SpecialistRole, digest,
)
from specimen_digitization.research_harness.persistence import (
    BlobRef, BudgetPolicy, DurabilityScope, DurableEffectBroker, HeldUnknown,
    ImmutableFileBlobs, PinnedRuntime, ResearchStore, SqliteStateBackend, StaleWork,
)
from specimen_digitization.research_harness.source_capture_v2 import (
    CaptureSourceBrokerV2, CapturedSourceTransportV2,
    RegisteredCapturePolicyV2, SourceRequestEnvelopeV2, logical_request_v2,
)
from specimen_digitization.research_harness.sources import (
    BoundedHTTPTransport, FixtureSourceTransport, MUSEUM_DATASET, canonical_json, insects_registry,
)


def ident(name):
    return str(uuid5(NAMESPACE_URL, "i4b-source-test:" + name))


def make_capture_rig(tmp_path, *, source_id="global_names_verifier", join=None):
    registry = insects_registry(qualification_overrides={source_id: {
        "qualification_state": "searched", "qualification_receipt": "fixture-only-not-live",
        "schema_digest": digest("fixture-schema"), "source_release": "fixture-release"}})
    source = registry.get(source_id)
    policy = RegisteredCapturePolicyV2(source_id=source.id, source_policy_digest=digest(source),
        kind="full_response", owner_registration_digest=digest("fixture-owner-registration"),
        owner_registration_origin="disposable local test registration", maximum_responses=2 if source_id == "field_museum_ipt" else 1)
    profile = CollectionProfile(id="insects", version="fixture-v1", organization_id=ident("org"),
        collection_id=ident("collection"), ancestry=(), knowledge_version="fixture-v1",
        fields=tuple(FieldProfile(field_key=key) for key in ALL_FIELDS))
    scope = ResearchScope(organization_id=ident("org"), collection_id=ident("collection"),
        specimen_id=ident("specimen"), job_id="opaque-research-job", generation=1,
        input_digest=digest("original-research-input"), profile_digest=digest(profile), sensitive=False)
    prompts = {}
    for role in SpecialistRole:
        text = "Fixture pinned instructions " + str(role)
        prompts[str(role)] = PromptPin(role=role, version="fixture-v1", text=text,
            digest=hashlib.sha256(text.encode()).hexdigest(), output_schema_digest=digest(FieldResolution.model_json_schema()),
            profile_digest=scope.profile_digest, source_registry_digest=registry.digest,
            toolset_digest=digest("fixture-tools"), model_route="function-fixture").model_dump(mode="json")
    role = SpecialistRole.TAXONOMY
    field_key = FieldKey.TAXON
    request = SpecialistRequest(scope=scope, role=role, field_keys=(field_key,),
        prompt=PromptPin.model_validate(prompts[str(role)]), field_revisions={field_key: 0})
    durable_scope = DurabilityScope(scope.organization_id, scope.collection_id, scope.specimen_id,
        scope.job_id, scope.generation, "reviewer-A", False)
    backend = SqliteStateBackend(tmp_path / "state.sqlite")
    backend.grant(durable_scope, role="reviewer")
    store = ResearchStore(backend, "disposable-test-program")
    store.initialize(durable_scope, BudgetPolicy(100, external_settled_micro_usd=7, external_held_micro_usd=3))
    source_pins = {"registry_digest": registry.digest, "capture_policies": {source.id: policy.model_dump(mode="json")}}
    if join is not None:
        source_pins["exact_specimen_joins"] = {source.id: join.model_dump(mode="json")}
    pins = PinnedRuntime(scope.input_digest, profile.model_dump(mode="json"), prompts, source_pins,
        {str(role): {"route": "function-fixture"} for role in SpecialistRole}, {"max_tokens": 128}, "specialist_harness_v2")
    store.create_job(durable_scope, pins, [str(key) for key in ALL_FIELDS], record_revision=1)
    lease = store.claim(durable_scope, "fixture-worker", ttl_seconds=300)
    blobs = ImmutableFileBlobs(tmp_path / "research-blobs")
    effects = DurableEffectBroker(store, blobs)
    calls, bodies, control = [], [], {"cancel": False, "pause": None}

    async def read(url, policy):
        calls.append(url)
        if control["cancel"]:
            raise asyncio.CancelledError()
        if control["pause"] is not None:
            entered, release = control["pause"]
            entered.set()
            await release.wait()
        if source_id == "field_museum_ipt":
            payload = ({"count": 1, "results": [{"datasetKey": MUSEUM_DATASET, "key": 8}]}
                if urlparse(url).path.endswith("/search") else {"key": 8, "fields": {
                    "occurrenceID": join.occurrence_id, "scientificName": "Danaus plexippus"}})
        else:
            name = unquote(urlparse(url).path.rsplit("/", 1)[-1])
            payload = {"names": [{"name": name, "bestResult": None}]}
        body = canonical_json(payload).encode()
        bodies.append(body)
        return 200, body

    transport = FixtureSourceTransport(read)
    broker = CaptureSourceBrokerV2(registry, {source.id: policy}, effects, durable_scope, lease,
        transport=transport, execution_class="offline")
    query = SourceQuery(source_id=source.id, field_key=field_key, query_text="Danaus plexippus", join=join)
    return SimpleNamespace(registry=registry, source=source, policy=policy, profile=profile,
        scope=scope, request=request, durable_scope=durable_scope, backend=backend, store=store,
        pins=pins, lease=lease, blobs=blobs, effects=effects, transport=transport, broker=broker,
        query=query, calls=calls, bodies=bodies, control=control)


@pytest.fixture
def capture_rig(tmp_path):
    return make_capture_rig(tmp_path)


def test_capture_source_capability_advertises_only_ready_registered_full_response(capture_rig):
    f = capture_rig
    assert f.source.id in f.broker.available_sources(f.request)
    f.broker.effects.policies.clear()
    assert f.broker.available_sources(f.request) == ()


def test_retired_google_maps_has_no_capture_kind_or_source(capture_rig):
    """Owner G-geo-1 (2026-10-03): Google Maps is removed from the harness permanently."""
    f = capture_rig
    with pytest.raises(ValidationError):
        RegisteredCapturePolicyV2(source_id="google_maps", source_policy_digest=digest("policy"),
            kind="google_policy_minimal", owner_registration_digest=digest("registration"),
            owner_registration_origin="fixture", maximum_responses=1)
    with pytest.raises(ValueError, match="outside owner allowlist"):
        f.registry.get("google_maps")
    assert "google_maps" not in f.broker.available_sources(f.request)
    assert f.calls == []


def query_once(rig):
    return asyncio.run(rig.broker.query_source(rig.request, rig.query))


def saved_envelope(rig, result):
    effect = rig.store.effect(rig.durable_scope, result.receipt.effect_id)
    raw = rig.blobs.get(BlobRef(**effect["receipt"]["raw_capture"]))
    return effect, SourceRequestEnvelopeV2.model_validate_json(raw)


def test_real_effect_retains_distinct_original_request_and_actual_body(capture_rig):
    rig = capture_rig
    result = query_once(rig)
    effect, envelope = saved_envelope(rig, result)
    selected = envelope.responses[0]
    assert rig.blobs.get(BlobRef(**selected.body.model_dump())) == rig.bodies[0]
    assert selected.body.sha256 == result.evidence[0].response_digest
    assert envelope.original_request == rig.request and envelope.query == rig.query
    assert envelope.logical_request == logical_request_v2(rig.request, rig.query, rig.policy)
    assert effect["receipt"]["raw_capture"]["sha256"] != selected.body.sha256
    assert effect["receipt"]["capture"]["sha256"] != selected.body.sha256
    assert len(rig.calls) == 1 and effect["receipt"]["actual_micro_usd"] == 0
    assert effect["held_micro_usd"] == 0 and effect["status"] == "completed"


def test_cold_duplicate_replays_saved_capture_without_transport_or_budget_reset(capture_rig):
    rig = capture_rig
    first = query_once(rig)
    before = rig.store._read(rig.durable_scope).state
    cold_store = ResearchStore(SqliteStateBackend(rig.backend.path), "disposable-test-program")
    cold_blobs = ImmutableFileBlobs(rig.blobs.directory)
    cold = CaptureSourceBrokerV2(rig.registry, {rig.source.id: rig.policy}, DurableEffectBroker(cold_store, cold_blobs),
        rig.durable_scope, rig.lease, transport=rig.transport, execution_class="offline")
    second = asyncio.run(cold.query_source(rig.request, rig.query))
    after = cold_store._read(rig.durable_scope).state
    assert second == first and len(rig.calls) == 1
    assert before["effects"] == after["effects"] and before["budget_policy"] == after["budget_policy"]
    assert before["budget_policy"]["external_settled_micro_usd"] == 7
    assert before["budget_policy"]["external_held_micro_usd"] == 3


def test_legitimate_adaptive_queries_need_no_digest_preregistration(capture_rig):
    rig = capture_rig
    first = query_once(rig)
    next_query = rig.query.model_copy(update={"query_text": "Papilio glaucus"})
    second = asyncio.run(rig.broker.query_source(rig.request, next_query))
    _, original = saved_envelope(rig, first)
    _, adaptive = saved_envelope(rig, second)
    assert original.original_request == adaptive.original_request == rig.request
    assert original.query != adaptive.query and len(rig.calls) == 2
    assert first.receipt.effect_id != second.receipt.effect_id
    assert "capture_contexts" not in rig.pins.sources


def test_two_actual_museum_responses_keep_publisher_body_separate_from_search(tmp_path):
    join = ExactSpecimenJoin(dataset_id=MUSEUM_DATASET, occurrence_id="fixture-exact-specimen-guid")
    rig = make_capture_rig(tmp_path, source_id="field_museum_ipt", join=join)
    result = query_once(rig)
    _, envelope = saved_envelope(rig, result)
    assert result.status == LookupStatus.SUCCESS and len(rig.calls) == len(envelope.responses) == 2
    search, publisher = envelope.responses
    assert rig.blobs.get(BlobRef(**search.body.model_dump())) == rig.bodies[0]
    assert rig.blobs.get(BlobRef(**publisher.body.model_dump())) == rig.bodies[1]
    assert result.evidence[0].response_digest == publisher.response_fingerprint
    assert result.evidence[0].response_digest != search.response_fingerprint
    changed = rig.query.model_copy(update={"join": join.model_copy(update={"occurrence_id": "other-specimen"})})
    with pytest.raises(PermissionError, match="exact_specimen_join_unproved"):
        asyncio.run(rig.broker.query_source(rig.request, changed))
    assert len(rig.calls) == 2


@pytest.mark.parametrize("change", ["policy", "lock", "revision", "prompt"])
def test_source_admission_failure_has_no_transport_or_effect(capture_rig, change):
    rig = capture_rig
    if change == "policy":
        rig.broker.effects.policies[rig.source.id] = rig.policy.model_copy(update={"kind": "denied"})
    elif change in {"lock", "revision"}:
        def reduce(state, now):
            field = state["jobs"][rig.durable_scope.key]["fields"]["taxon"]
            field["locked" if change == "lock" else "revision"] = True if change == "lock" else 1
        rig.store._mutate(rig.durable_scope, reduce)
    elif change == "prompt":
        rig.request = rig.request.model_copy(update={"prompt": rig.request.prompt.model_copy(update={"version": "changed"})})
    with pytest.raises((PublicationUnavailable, PermissionError, StaleWork)):
        query_once(rig)
    assert rig.calls == [] and rig.store._read(rig.durable_scope).state["effects"] == {}


def test_cancellation_during_actual_transport_preserves_unknown_hold(capture_rig):
    rig = capture_rig
    rig.control["cancel"] = True
    with pytest.raises(asyncio.CancelledError):
        query_once(rig)
    effect = next(iter(rig.store._read(rig.durable_scope).state["effects"].values()))
    assert len(rig.calls) == 1 and effect["status"] == "held_unknown" and effect["held_micro_usd"] == 1
    with pytest.raises(HeldUnknown):
        query_once(rig)
    assert len(rig.calls) == 1


def test_body_capture_write_failure_never_refetches(capture_rig, monkeypatch):
    rig = capture_rig
    def fail(locator, data):
        raise OSError("synthetic immutable capture failure")
    monkeypatch.setattr(rig.blobs, "put_at", fail)
    with pytest.raises(OSError):
        query_once(rig)
    with pytest.raises(HeldUnknown):
        query_once(rig)
    assert len(rig.calls) == 1
    effect = next(iter(rig.store._read(rig.durable_scope).state["effects"].values()))
    assert effect["receipt"] is None and effect["status"] == "held_unknown"


def test_inflight_duplicate_never_downgrades_or_resends_active_attempt(capture_rig):
    rig = capture_rig
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        rig.control["pause"] = entered, release
        task = asyncio.create_task(rig.broker.query_source(rig.request, rig.query))
        await asyncio.wait_for(entered.wait(), 1)
        try:
            with pytest.raises(HeldUnknown):
                await rig.broker.query_source(rig.request, rig.query)
            effect = next(iter(rig.store._read(rig.durable_scope).state["effects"].values()))
            assert effect["status"] == "sending" and len(effect["attempts"]) == 1
        finally:
            release.set()
        result = await asyncio.wait_for(task, 1)
        assert result.receipt.effect_status == "completed" and len(rig.calls) == 1
    asyncio.run(scenario())


def test_transport_downgrade_and_unscoped_transport_are_refused(capture_rig):
    rig = capture_rig
    with pytest.raises(PublicationUnavailable):
        CapturedSourceTransportV2(BoundedHTTPTransport(), rig.blobs, execution_class="offline")
    with pytest.raises(PublicationUnavailable):
        asyncio.run(rig.broker.transport.get("https://verifier.globalnames.org/api/v1/verifications/test", policy=rig.source))
    rig.broker.transport.transport = FixtureSourceTransport(rig.transport.read)
    with pytest.raises(PublicationUnavailable):
        query_once(rig)
    assert rig.calls == []


def test_raw_host_scope_boolean_generation_cannot_alias_generation_one(capture_rig):
    rig = capture_rig
    with pytest.raises(PublicationUnavailable, match="scope_type_invalid"):
        CaptureSourceBrokerV2(rig.registry, {rig.source.id: rig.policy}, rig.effects,
            replace(rig.durable_scope, generation=True), rig.lease, transport=rig.transport, execution_class="offline")
    assert rig.calls == [] and rig.store._read(rig.durable_scope).state["effects"] == {}


def test_sensitive_request_stays_policy_denied_without_an_effect(capture_rig):
    rig = capture_rig
    rig.request = rig.request.model_copy(update={"scope": rig.scope.model_copy(update={"sensitive": True})})
    result = query_once(rig)
    assert result.status == LookupStatus.POLICY and rig.calls == []
    assert rig.store._read(rig.durable_scope).state["effects"] == {}


def test_live_remains_hold_without_verified_external_import(capture_rig):
    rig = capture_rig
    async def dispatch(attempt_id, provider_key):
        raise AssertionError("no live dispatch is admitted")
    with pytest.raises(PermissionError, match="Verified legacy ProgramLedger"):
        asyncio.run(rig.effects.execute(rig.durable_scope, rig.lease, "live-not-admitted", {}, 1, dispatch,
            execution_class="live", field_keys=("taxon",)))
    assert rig.calls == []
