"""GEOLocate through the durable capture path (CaptureSourceBrokerV2 over real SQLite effects).

CaptureSourceBrokerV2 is the production composition: SourceBroker(registry,
transport=CapturedSourceTransportV2(FixtureSourceTransport(read)), effect_dispatch=SourceCaptureEffectsV2).
Offline only: the transport serves the recorded glcwrap fixture; no network, no cost.
The ledger is a new disposable SQLite file per test.
"""

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, ROLE_FIELDS, CollectionProfile, FieldKey, FieldProfile, LookupStatus, ResearchScope,
    SourceCoverageState, SourceQuery, SpecialistRequest, SpecialistRole, digest,
)
from specimen_digitization.research_harness.persistence import (
    BlobRef, BudgetPolicy, DurabilityScope, DurableEffectBroker, ImmutableFileBlobs, PinnedRuntime,
    ResearchStore, SqliteStateBackend,
)
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.source_capture_v2 import (
    CaptureSourceBrokerV2, RegisteredCapturePolicyV2, SourceRequestEnvelopeV2,
)
from specimen_digitization.research_harness.sources import (
    GEOLOCATE_QUALIFICATION, FixtureSourceTransport, insects_registry,
)

FIXTURES = Path(__file__).parent / "fixtures" / "geolocate"
MANIFEST = {item["file"]: item for item in json.loads((FIXTURES / "manifest.json").read_text())["fixtures"]}
FIXTURE = "yepocapa-modern.json"
RECORDED_URL = MANIFEST[FIXTURE]["url"]
RECORDED_BODY = (FIXTURES / FIXTURE).read_bytes()
PIN = "0" * 64
YEPOCAPA = {"country": "Guatemala", "state": "Chimaltenango", "locality": "Yepocapa", "place": "Yepocapa",
            "latitude": 14.5, "longitude": -90.95, "radius_km": 15, "value": "Yepocapa"}


def geography_request(registry, *, profile_digest=PIN):
    # Copied from test_geolocate_validator.py; the durable job pins the real profile digest.
    scope = ResearchScope(organization_id="org", collection_id="insects", specimen_id="subject_105526328",
                          job_id="job", generation=1, input_digest=PIN, profile_digest=profile_digest, sensitive=False)
    prompt = resolve_prompt(SpecialistRole.GEOGRAPHY, profile_digest=profile_digest, source_registry_digest=registry.digest,
                            toolset_digest=PIN, model_route="harness-deepseek", output_schema_digest=PIN)
    return SpecialistRequest(scope=scope, role=SpecialistRole.GEOGRAPHY,
                             field_keys=ROLE_FIELDS[SpecialistRole.GEOGRAPHY], prompt=prompt)


def make_rig(tmp_path, bodies):
    registry = insects_registry(qualification_overrides={"geolocate": GEOLOCATE_QUALIFICATION})
    source = registry.get("geolocate")
    policy = RegisteredCapturePolicyV2(source_id="geolocate", source_policy_digest=digest(source),
        kind="full_response", owner_registration_digest=digest("fixture-owner-registration"),
        owner_registration_origin="disposable local test registration", maximum_responses=1)
    profile = CollectionProfile(id="insects", version="fixture-v1", organization_id="org", collection_id="insects",
        ancestry=(), knowledge_version="fixture-v1", fields=tuple(FieldProfile(field_key=key) for key in ALL_FIELDS))
    request = geography_request(registry, profile_digest=digest(profile))
    scope = request.scope
    durable_scope = DurabilityScope(scope.organization_id, scope.collection_id, scope.specimen_id,
        scope.job_id, scope.generation, "reviewer-A", False)
    backend = SqliteStateBackend(tmp_path / "state.sqlite")
    backend.grant(durable_scope, role="reviewer")
    store = ResearchStore(backend, "disposable-test-program")
    store.initialize(durable_scope, BudgetPolicy(100))
    pins = PinnedRuntime(scope.input_digest, profile.model_dump(mode="json"),
        {str(request.role): request.prompt.model_dump(mode="json")},
        {"registry_digest": registry.digest, "capture_policies": {source.id: policy.model_dump(mode="json")}},
        {str(request.role): {"route": "harness-deepseek"}}, {"max_tokens": 128}, "specialist_harness_v2")
    store.create_job(durable_scope, pins, [str(key) for key in ALL_FIELDS], record_revision=1)
    lease = store.claim(durable_scope, "fixture-worker", ttl_seconds=300)
    blobs = ImmutableFileBlobs(tmp_path / "research-blobs")
    calls, served = [], list(bodies)

    async def read(url, policy):
        calls.append(url)
        assert url == RECORDED_URL, "the adapter must send exactly the recorded request"
        return 200, served.pop(0)

    broker = CaptureSourceBrokerV2(registry, {source.id: policy}, DurableEffectBroker(store, blobs), durable_scope,
        lease, transport=FixtureSourceTransport(read), execution_class="offline")
    return SimpleNamespace(request=request, durable_scope=durable_scope, store=store, blobs=blobs,
                           broker=broker, calls=calls)


def lookup(rig, interpretation, field_key=FieldKey.CITY):
    query = SourceQuery(source_id="geolocate", field_key=field_key, query_text=json.dumps(interpretation))
    return asyncio.run(rig.broker.query_source(rig.request, query))


def effects(rig):
    return list(rig.store._read(rig.durable_scope).state["effects"].values())


def saved_envelope(rig, result):
    effect = rig.store.effect(rig.durable_scope, result.receipt.effect_id)
    return effect, SourceRequestEnvelopeV2.model_validate_json(rig.blobs.get(BlobRef(**effect["receipt"]["raw_capture"])))


def test_success_completes_the_effect_and_captures_the_full_response(tmp_path):
    rig = make_rig(tmp_path, [RECORDED_BODY])
    result = lookup(rig, YEPOCAPA)
    assert result.status == LookupStatus.SUCCESS and result.receipt.effect_status == "completed"
    [candidate] = [json.loads(item) for item in result.candidate_json]
    assert candidate["authority_id"] == "geolocate:14.501946,-90.953956"
    effect, envelope = saved_envelope(rig, result)
    assert effect["status"] == "completed" and effect["held_micro_usd"] == 0
    assert effect["receipt"]["actual_micro_usd"] == 0
    assert (envelope.policy.kind, envelope.policy.maximum_responses) == ("full_response", 1)
    [response] = envelope.responses
    assert (response.url, response.status_code) == (RECORDED_URL, 200)
    assert rig.blobs.get(BlobRef(**response.body.model_dump())) == RECORDED_BODY
    assert response.response_fingerprint == hashlib.sha256(RECORDED_BODY).hexdigest()
    assert result.evidence[0].response_digest == response.response_fingerprint
    assert rig.calls == [RECORDED_URL]


def test_the_same_query_replays_the_capture_without_a_second_read(tmp_path):
    rig = make_rig(tmp_path, [RECORDED_BODY])
    first = lookup(rig, YEPOCAPA)
    before = effects(rig)
    second = lookup(rig, YEPOCAPA)
    assert second == first and second.receipt.effect_id == first.receipt.effect_id
    assert rig.calls == [RECORDED_URL]
    assert effects(rig) == before and len(before) == 1


def test_malformed_body_is_a_typed_failure_that_holds_no_effect(tmp_path):
    payload = json.loads(RECORDED_BODY)
    payload["resultSet"]["features"][0]["geometry"] = None
    malformed = json.dumps(payload).encode()
    rig = make_rig(tmp_path, [malformed, RECORDED_BODY])
    failed = lookup(rig, YEPOCAPA)
    assert failed.status == LookupStatus.MALFORMED and failed.coverage.state == SourceCoverageState.FAILED
    assert failed.candidate_json == () and failed.receipt.effect_status == "completed"
    _, envelope = saved_envelope(rig, failed)
    assert rig.blobs.get(BlobRef(**envelope.responses[0].body.model_dump())) == malformed
    assert [effect["status"] for effect in effects(rig)] == ["completed"]
    # No held_unknown effect blocks the field: a different query for it still reaches the source.
    later = lookup(rig, {**YEPOCAPA, "radius_km": 20})
    assert later.status == LookupStatus.SUCCESS and later.receipt.effect_status == "completed"
    assert rig.calls == [RECORDED_URL, RECORDED_URL]
    assert [effect["status"] for effect in effects(rig)] == ["completed", "completed"]
