"""Real HTTP, actor ACL and SQL journal proof without any live provider call."""

import asyncio
from dataclasses import asdict, replace
from functools import partial
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage
import pytest

from specimen_digitization.application.domain import FieldValue, Principal, Scope, ValueState
from specimen_digitization.research_harness.agents import (
    SpecialistHarness, SpecialistOutput, request_model_pins, specialist_output_schema_digest,
)
from specimen_digitization.research_harness.api import create_research_router
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, ROLE_FIELDS, CollectionProfile, FieldKey, FieldProfile, FieldResolution,
    ResearchScope, SpecialistRequest, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.engine import ResearchEngine
from specimen_digitization.research_harness.gateway import EffectModel, ModelBinding
from specimen_digitization.research_harness.journal import DurableResearchJournal
from specimen_digitization.research_harness.persistence import (
    BudgetPolicy, CapturedResult, DurabilityScope, DurableEffectBroker, ImmutableFileBlobs,
    ResearchStore, SqlConnectStepStore, SqliteStateBackend, StaleWork,
)
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.runtime import runtime_pins
from specimen_digitization.research_harness.service import ResearchService


BASE = "/v1/organizations/org/collections/insects/specimens/specimen/research/jobs/job/generations/1"
RETRY = BASE + "/fields/taxon/retry"
PRIVATE = "PRIVATE_RESEARCH_HTTP_CANARY"


@pytest.fixture
def rig(tmp_path):
    profile = CollectionProfile(id="insects", version="1", organization_id="org",
        collection_id="insects", ancestry=("org", "insects"), knowledge_version="fixture",
        fields=tuple(FieldProfile(field_key=key) for key in ALL_FIELDS))
    scope = ResearchScope(organization_id="org", collection_id="insects",
        specimen_id="specimen", job_id="job", generation=1, input_digest="a"*64,
        profile_digest=digest(profile), sensitive=False)
    requests = {role:SpecialistRequest(scope=scope, role=role, field_keys=keys,
        prompt=resolve_prompt(role, profile_digest=scope.profile_digest,
            source_registry_digest="b"*64, toolset_digest="c"*64,
            model_route="harness-deepseek", output_schema_digest=specialist_output_schema_digest()))
        for role, keys in ROLE_FIELDS.items()}
    bindings = {role:ModelBinding("harness-deepseek", "deepseek-ai/DeepSeek-V4.1-Flash",
        "deepinfra", 128, 10, "offline-fixture") for role in requests}
    settings = {"max_tokens":128}
    pins = runtime_pins(profile, requests,
        model={role:{"route":binding.route_id, **asdict(binding)} for role,binding in bindings.items()},
        settings=settings)
    durable = DurabilityScope("org", "insects", "specimen", "job", 1, "worker", False)
    backend = SqliteStateBackend(tmp_path / "http-research.sqlite")
    backend.grant(durable)
    actor = replace(durable, actor_uid="actor")
    backend.grant(actor)
    store = ResearchStore(backend, "existing-program")
    store.initialize(durable, BudgetPolicy(1000))
    store.create_job(durable, pins, list(ALL_FIELDS))
    lease = store.claim(durable, "offline-worker", ttl_seconds=120)
    journal = DurableResearchJournal(store, durable, lease)
    failed = FieldResolution(field_key=FieldKey.TAXON, work_state=WorkState.OPERATIONAL_FAILED,
        value=FieldValue(), reason="specialist_operational_failure")
    neighbor = FieldResolution(field_key=FieldKey.COUNTRY, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, literal="Synthetic country"),
        evidence_ids=("synthetic-country-evidence",), reason="offline_accepted_evidence")
    for role, resolution in ((SpecialistRole.TAXONOMY, failed), (SpecialistRole.GEOGRAPHY, neighbor)):
        asyncio.run(journal.commit(requests[role], (resolution,), receipt_ids=(),
            model_settings_digest=digest(settings)))
    current = SimpleNamespace(retry_enabled=True, principal=Principal(user_id="actor",
        scope=Scope(organization_id="org", collection_id="insects"), role="operator"))

    async def verified_principal():
        if current.principal is None:
            raise HTTPException(401, PRIVATE)
        return current.principal

    async def resolve_scope(principal, locator):
        return DurabilityScope(locator.organization_id, locator.collection_id,
            locator.specimen_id, locator.job_id, locator.generation, principal.user_id, False)

    async def retry_available(principal, scope, field_key):
        return current.retry_enabled

    service = ResearchService(store=store, resolve_scope=resolve_scope,
        retry_admission=partial(store.admit_retry, execution_class="offline"),
        retry_available=retry_available)
    app = FastAPI()
    app.include_router(create_research_router(service,
        verified_principal_dependency=verified_principal))
    blobs = ImmutableFileBlobs(tmp_path / "blobs")
    yield SimpleNamespace(client=TestClient(app), app=app, service=service,
        current=current, backend=backend, store=store, actor=actor, durable=durable,
        journal=journal, lease=lease, profile=profile, requests=requests,
        bindings=bindings, settings=settings, blobs=blobs, scope=scope)


def fields(response):
    return {field["field_key"]:field for field in response.json()["fields"]}


def retry_outbox(store, scope):
    return {key:value for key,value in store._read(scope).state["outbox"].items()
        if value["kind"] == "research_field_retry"}


def private_error(response, status):
    assert response.status_code == status, response.text
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"
    assert PRIVATE not in response.text
    assert set(response.json()) == {"detail"}


def test_thread_uses_actual_reader_and_no_shared_app_mount(rig):
    response = rig.client.get(BASE + "/thread")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["contract_version"] == "research-thread-v1"
    assert len(response.json()["fields"]) == 20
    assert fields(response)["country"]["value"]["literal"] == "Synthetic country"
    assert fields(response)["taxon"]["actions"] == ["retry_field"]
    assert rig.store.budget(rig.actor)["settled_micro_usd"] == 0
    assert rig.client.post(BASE + "/jobs", json={"model":PRIVATE}).status_code == 404


def test_thread_over_http_carries_the_review_of_a_field_that_waits_and_nothing_for_the_rest(rig):
    from specimen_digitization.research_harness.contracts import (
        HumanQuestion, SourceCoverageReceipt, SourceCoverageState,
    )

    receipt = SourceCoverageReceipt(source_id="geolocate", field_key=FieldKey.CITY,
        state=SourceCoverageState.SEARCHED, source_version="v", coverage_limit="bounded",
        reason="no_match: GEOLocate returned 2 match(es); none is 'Synthetic place'",
        receipt_ids=("source:" + "c" * 64,))
    asked = HumanQuestion(field_key=FieldKey.CITY, question="Which town does the label mean?",
        reason="scoped_absence", coverage=(receipt,), evidence_ids=("source:" + "c" * 64,))
    waiting = FieldResolution(field_key=FieldKey.CITY, work_state=WorkState.WAITING_HUMAN, question=asked,
        value=FieldValue(state=ValueState.UNRESOLVED, literal="Synthetic place"),
        reason="Two readings name different towns")
    request = rig.requests[SpecialistRole.GEOGRAPHY].model_copy(
        update={"field_keys": (FieldKey.CITY,), "field_revisions": {FieldKey.CITY: 0}})
    asyncio.run(rig.journal.commit(request, (waiting,), receipt_ids=(),
        model_settings_digest=digest(rig.settings)))
    body = fields(rig.client.get(BASE + "/thread"))
    assert body["city"]["review"] == {
        "question_reason": "scoped_absence", "reason": "Two readings name different towns",
        "evidence": [], "candidates": [], "evidence_not_shown": 1, "candidates_not_shown": 0}
    assert all(field["review"] is None for key, field in body.items() if key != "city")
    assert PRIVATE not in str(body)


def test_legacy_session_and_routes_survive_explicit_research_mount(rig, tmp_path):
    from specimen_digitization.application.api import create_app
    from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
    from specimen_digitization.application.workflow import SyntheticAdapters

    blobs = LocalBlobs(tmp_path / "legacy-blobs")
    legacy = create_app(mode="synthetic", repository=SQLiteRepository(tmp_path / "legacy.sqlite"),
        blobs=blobs, adapters=SyntheticAdapters(blobs, "synthetic fixture"), token="fixture-token")
    client = TestClient(legacy)
    headers = {"Authorization":"Bearer fixture-token"}
    original = client.get("/v1/session", headers=headers)
    assert original.status_code == 200
    original_routes = tuple(legacy.routes)
    paths = tuple(sorted(legacy.openapi()["paths"]))
    # Constructing an optional router never modifies the existing application.
    create_research_router(rig.service, verified_principal_dependency=lambda:rig.current.principal)
    assert tuple(legacy.routes) == original_routes
    assert tuple(sorted(legacy.openapi()["paths"])) == paths
    assert client.get("/v1/session", headers=headers).json() == original.json()
    # The application now explicitly mounts the native research host. This
    # synthetic session has a different organization/collection; constructing
    # an optional router above must not grant it native research authority.
    private_error(client.get(BASE + "/thread",headers=headers),403)


def test_missing_verified_principal_and_spoof_headers_cannot_authenticate(rig):
    rig.current.principal = None
    private_error(rig.client.get(BASE + "/thread", headers={
        "Authorization":"Bearer " + PRIVATE, "X-User-Id":"worker",
        "X-Actor-Uid":"worker", "X-Role":"admin",
    }), 401)


@pytest.mark.parametrize("part,replacement", [
    ("organizations/org", "organizations/other"),
    ("collections/insects", "collections/other"),
    ("specimens/specimen", "specimens/other"),
    ("jobs/job", "jobs/other"),
])
def test_cross_scope_path_is_denied(rig, part, replacement):
    private_error(rig.client.get(BASE.replace(part, replacement) + "/thread"), 403)


def test_fresh_acl_revocation_and_actor_scope_are_checked_on_every_request(rig):
    assert rig.client.get(BASE + "/thread").status_code == 200
    rig.backend.revoke(rig.actor)
    private_error(rig.client.get(BASE + "/thread"), 403)
    private_error(rig.client.post(RETRY, json={"expected_checkpoint_revision":1}), 403)
    rig.current.principal = rig.current.principal.model_copy(update={"user_id":"unqualified-actor"})
    private_error(rig.client.get(BASE + "/thread"), 403)


def test_resolver_cannot_substitute_privileged_worker_actor(rig):
    async def wrong_actor(*_):
        return rig.durable
    rig.service.resolve_scope = wrong_actor
    private_error(rig.client.get(BASE + "/thread"), 403)


def test_viewer_reads_but_cannot_queue_and_current_store_role_overrules_stale_principal(rig):
    rig.backend.grant(rig.actor, role="viewer")
    assert rig.client.get(BASE + "/thread").status_code == 200
    private_error(rig.client.post(RETRY, json={"expected_checkpoint_revision":1}), 403)
    assert retry_outbox(rig.store, rig.actor) == {}


def test_current_viewer_cannot_replay_existing_queued_command(rig):
    assert rig.client.post(RETRY, json={"expected_checkpoint_revision":1}).status_code == 202
    rig.backend.grant(rig.actor, role="viewer")
    private_error(rig.client.post(RETRY, json={"expected_checkpoint_revision":1}), 403)
    assert len(retry_outbox(rig.store, rig.actor)) == 1


def test_sensitive_scope_permission_is_rechecked(rig):
    async def sensitive(principal, locator):
        return replace(rig.actor, sensitive=True)
    rig.service.resolve_scope = sensitive
    private_error(rig.client.get(BASE + "/thread"), 403)


def test_stale_generation_and_checkpoint_revision_deny_before_admission(rig):
    private_error(rig.client.get(BASE.replace("generations/1", "generations/2") + "/thread"), 409)
    private_error(rig.client.post(RETRY.replace("generations/1", "generations/2"),
        json={"expected_checkpoint_revision":1}), 409)
    private_error(rig.client.post(RETRY, json={"expected_checkpoint_revision":2}), 409)
    assert retry_outbox(rig.store, rig.actor) == {}


@pytest.mark.parametrize("extra", ["model", "settings", "budget", "pins", "scope", "actor_uid", "execution_class", "retry_available"])
def test_retry_body_forbids_runtime_authority_and_sanitizes_validation(rig, extra):
    private_error(rig.client.post(RETRY, json={"expected_checkpoint_revision":1, extra:PRIVATE}), 422)
    assert retry_outbox(rig.store, rig.actor) == {}


@pytest.mark.parametrize("revision", [0, -1, "1", True, None, PRIVATE])
def test_revision_is_positive_strict_integer_and_errors_never_echo_inputs(rig, revision):
    private_error(rig.client.post(RETRY, json={"expected_checkpoint_revision":revision}), 422)


def test_malformed_json_and_unknown_field_are_sanitized(rig):
    private_error(rig.client.post(RETRY, content='{"'+PRIVATE,
        headers={"Content-Type":"application/json"}), 422)
    private_error(rig.client.post(RETRY.replace("fields/taxon", "fields/"+PRIVATE),
        json={"expected_checkpoint_revision":1}), 422)


def test_query_cannot_supply_runtime_authority(rig):
    private_error(rig.client.get(BASE + "/thread", params={"model":PRIVATE}), 422)
    private_error(rig.client.post(RETRY, params={"execution_class":PRIVATE},
        json={"expected_checkpoint_revision":1}), 422)


@pytest.mark.parametrize("status", ["held_unknown", "completed_unknown_cost"])
def test_unknown_effect_or_unknown_cost_hold_denies_retry(rig, status):
    broker = DurableEffectBroker(rig.store, rig.blobs)
    async def dispatch(*_):
        if status == "held_unknown":
            raise RuntimeError(PRIVATE)
        return CapturedResult({"raw":PRIVATE}, None)
    try:
        asyncio.run(broker.execute(rig.durable, rig.lease, "model:specimen_taxonomy:hold", {},
            10, dispatch, field_keys=("taxon",)))
    except RuntimeError:
        pass
    response = rig.client.get(BASE + "/thread")
    assert response.status_code == 200 and PRIVATE not in response.text
    assert fields(response)["taxon"]["actions"] == []
    private_error(rig.client.post(RETRY, json={"expected_checkpoint_revision":1}), 403)
    assert retry_outbox(rig.store, rig.actor) == {}
    assert rig.store.budget(rig.actor)["held_micro_usd"] == 10


def test_default_live_admission_hold_cannot_be_overridden_by_http(rig):
    rig.service.retry_admission = rig.store.admit_retry
    rig.service.retry_available = None
    assert fields(rig.client.get(BASE + "/thread"))["taxon"]["actions"] == []
    private_error(rig.client.post(RETRY, json={"expected_checkpoint_revision":1}), 403)
    assert retry_outbox(rig.store, rig.actor) == {}


def test_absent_server_capability_hides_retry_action_and_denies_admission(rig):
    rig.service.retry_available = None
    assert fields(rig.client.get(BASE + "/thread"))["taxon"]["actions"] == []
    private_error(rig.client.post(RETRY, json={"expected_checkpoint_revision":1}), 403)
    assert retry_outbox(rig.store, rig.actor) == {}


@pytest.mark.parametrize("availability", [1, None, PRIVATE])
def test_only_explicit_server_boolean_availability_enables_retry(rig, availability):
    async def not_boolean(*_):
        return availability
    rig.service.retry_available = not_boolean
    assert fields(rig.client.get(BASE + "/thread"))["taxon"]["actions"] == []
    private_error(rig.client.post(RETRY, json={"expected_checkpoint_revision":1}), 403)


def test_server_availability_errors_are_sanitized(rig):
    async def failure(*_):
        raise RuntimeError(PRIVATE)
    rig.service.retry_available = failure
    private_error(rig.client.get(BASE + "/thread"), 503)
    private_error(rig.client.post(RETRY, json={"expected_checkpoint_revision":1}), 503)
    assert retry_outbox(rig.store, rig.actor) == {}


def test_server_hold_transition_hides_action_and_denies_queued_replay(rig):
    assert rig.client.post(RETRY, json={"expected_checkpoint_revision":1}).status_code == 202
    rig.current.retry_enabled = False
    assert fields(rig.client.get(BASE + "/thread"))["taxon"]["actions"] == []
    private_error(rig.client.post(RETRY, json={"expected_checkpoint_revision":1}), 403)
    assert len(retry_outbox(rig.store, rig.actor)) == 1


def test_lost_ack_replays_matching_queued_command_through_atomic_admission(rig):
    accepted = rig.client.post(RETRY, json={"expected_checkpoint_revision":1})
    assert accepted.status_code == 202
    queued = fields(rig.client.get(BASE + "/thread"))["taxon"]
    assert queued["work_state"] == "retry_scheduled" and queued["actions"] == []
    admit, calls = rig.service.retry_admission, []
    def observed(scope, field, **kwargs):
        calls.append((scope.actor_uid, field, kwargs))
        return admit(scope, field, **kwargs)
    rig.service.retry_admission = observed
    revision = rig.store._read(rig.actor).revision
    replay = rig.client.post(RETRY, json={"expected_checkpoint_revision":1})
    assert replay.status_code == 202 and replay.json() == accepted.json()
    assert len(calls) == 1 and calls[0][0:2] == ("actor", "taxon")
    assert rig.store._read(rig.actor).revision > revision
    assert len(retry_outbox(rig.store, rig.actor)) == 1


@pytest.mark.parametrize("binding", [
    "idempotency_key", "id", "scope", "field_key", "expected_generation",
    "expected_field_revision", "checkpoint_digest", "binding_digest", "status",
])
def test_queued_replay_requires_exact_server_command_and_checkpoint_binding(rig, binding):
    accepted = rig.client.post(RETRY, json={"expected_checkpoint_revision":1}).json()
    def corrupt(state, _):
        command = state["outbox"]["retry/" + accepted["command_id"]]["command"]
        command[binding] = "running" if binding == "status" else PRIVATE
    rig.store._mutate(rig.actor, corrupt)
    calls = []
    rig.service.retry_admission = lambda *args, **kwargs:calls.append(1)
    denied = rig.client.post(RETRY, json={"expected_checkpoint_revision":1})
    assert denied.status_code in {403, 409}
    private_error(denied, denied.status_code)
    assert calls == []


def test_unknown_cost_hold_after_queue_still_denies_lost_ack_replay(rig):
    assert rig.client.post(RETRY, json={"expected_checkpoint_revision":1}).status_code == 202
    async def uncertain(*_):
        return CapturedResult({"raw":PRIVATE}, None)
    asyncio.run(DurableEffectBroker(rig.store, rig.blobs).execute(
        rig.durable, rig.lease, "model:queued-unknown-cost", {}, 10, uncertain,
        field_keys=("taxon",)))
    calls = []
    rig.service.retry_admission = lambda *args, **kwargs:calls.append(1)
    private_error(rig.client.post(RETRY, json={"expected_checkpoint_revision":1}), 403)
    assert calls == [] and rig.store.budget(rig.actor)["held_micro_usd"] == 10


@pytest.mark.parametrize("block", ["paused", "human_lock", "settled_neighbor"])
def test_pause_human_lock_and_settled_neighbor_cannot_be_retried(rig, block):
    target = RETRY
    if block == "paused":
        rig.store.pause(rig.actor, expected_generation=1)
    elif block == "human_lock":
        def lock(state, _):
            rig.store._job(state, rig.actor)["fields"]["taxon"]["locked"] = True
        rig.store._mutate(rig.actor, lock)
    else:
        target = RETRY.replace("fields/taxon", "fields/country")
    private_error(rig.client.post(target, json={"expected_checkpoint_revision":1}), 403)
    assert retry_outbox(rig.store, rig.actor) == {}


@pytest.mark.parametrize("race", ["checkpoint", "membership"])
def test_atomic_admission_rechecks_changes_after_http_read(rig, race):
    admit = rig.service.retry_admission
    def competing(scope, field, **kwargs):
        if race == "checkpoint":
            request = rig.requests[SpecialistRole.TAXONOMY].model_copy(
                update={"field_revisions":{FieldKey.TAXON:1}})
            resolution = FieldResolution(field_key=FieldKey.TAXON, work_state=WorkState.WAITING_SOURCE,
                value=FieldValue(), reason="source_prerequisite")
            asyncio.run(rig.journal.commit(request, (resolution,), receipt_ids=(),
                model_settings_digest=digest(rig.settings)))
        else:
            rig.backend.revoke(rig.actor)
        return admit(scope, field, **kwargs)
    rig.service.retry_admission = competing
    private_error(rig.client.post(RETRY, json={"expected_checkpoint_revision":1}),
        409 if race == "checkpoint" else 403)
    assert retry_outbox(rig.store, rig.durable) == {}


def test_unexpected_service_failure_returns_fixed_private_error(rig):
    async def failure(*_):
        raise RuntimeError(PRIVATE)
    rig.service.resolve_scope = failure
    private_error(rig.client.get(BASE + "/thread"), 503)


def test_callback_acknowledgement_without_committed_outbox_is_denied(rig):
    def nondurable(scope, field, **kwargs):
        return {"id":"d"*64, "status":"queued", "kind":"retry_field",
            "scope":scope.identity(), "field_key":field,
            "expected_generation":kwargs["expected_generation"],
            "expected_field_revision":kwargs["expected_field_revision"],
            "idempotency_key":kwargs["idempotency_key"]}
    rig.service.retry_admission = nondurable
    private_error(rig.client.post(RETRY, json={"expected_checkpoint_revision":1}), 409)
    assert retry_outbox(rig.store, rig.actor) == {}


def test_queue_is_durable_and_unclaimed_command_cannot_dispatch_or_change_neighbor(rig):
    before = rig.store.job(rig.actor)["fields"]["country"]
    response = rig.client.post(RETRY, json={"expected_checkpoint_revision":1})
    assert response.status_code == 202, response.text
    accepted = response.json()
    assert accepted["status"] == "queued" and accepted["field_key"] == "taxon"
    assert rig.client.post(RETRY, json={"expected_checkpoint_revision":1}).json() == accepted
    reopened_store = ResearchStore(SqliteStateBackend(rig.backend.path), "existing-program")
    outbox = retry_outbox(reopened_store, rig.actor)
    assert len(outbox) == 1
    assert outbox["retry/" + accepted["command_id"]]["command"]["field_key"] == "taxon"
    assert reopened_store.job(rig.actor)["fields"]["country"] == before
    assert reopened_store.budget(rig.actor)["settled_micro_usd"] == 0

    # A queued command is not a running worker authorization. The real official
    # engine must reject it before constructing a Harness or invoking a provider.
    calls = []
    request = rig.requests[SpecialistRole.TAXONOMY]
    def provider(messages, info):
        calls.append(messages)
        output = SpecialistOutput(role=request.role, resolutions=(FieldResolution(
            field_key=FieldKey.TAXON, work_state=WorkState.WAITING_SOURCE,
            value=FieldValue(), reason="qualified_source_prerequisite"),))
        return ModelResponse([ToolCallPart(info.output_tools[0].name,
            output.model_dump(mode="json"), tool_call_id="offline-output")],
            usage=RequestUsage(input_tokens=2, output_tokens=2))
    broker = DurableEffectBroker(reopened_store, rig.blobs)
    seen = []
    def harness(selected):
        seen.append(tuple(selected))
        return SpecialistHarness(requests=selected, tool_broker=object(),
            model_factory=lambda scoped:EffectModel(FunctionModel(provider), broker=broker,
                scope=rig.durable, lease=rig.lease, role=str(scoped.role),
                binding=rig.bindings[scoped.role], pins=request_model_pins(scoped),
                model_settings=rig.settings, actual_cost=lambda _:2),
            step_store_factory=lambda scoped:SqlConnectStepStore(reopened_store, rig.durable,
                rig.blobs, agent_name=str(scoped.role)))
    journal = DurableResearchJournal(reopened_store, rig.durable, rig.lease)
    engine = ResearchEngine(profile=rig.profile, requests={request.role:request}, journal=journal,
        harness_factory=harness, model_settings_digest=digest(rig.settings))
    with pytest.raises(StaleWork, match="journal_retry_command_binding_mismatch"):
        asyncio.run(engine.run(retry_fields=(FieldKey.TAXON,)))
    assert calls == [] and seen == []
    assert reopened_store.job(rig.actor)["fields"]["country"] == before
    reread = rig.client.get(BASE + "/thread")
    assert fields(reread)["taxon"]["checkpoint"]["revision"] == 1
    assert fields(reread)["taxon"]["work_state"] == "retry_scheduled"
    assert fields(reread)["taxon"]["actions"] == []
    assert fields(reread)["country"]["checkpoint"]["revision"] == 1
    assert reopened_store.budget(rig.actor)["settled_micro_usd"] == 0
    assert reopened_store.budget(rig.actor)["held_micro_usd"] == 0
    assert rig.client.post(RETRY, json={"expected_checkpoint_revision":1}).json() == accepted
