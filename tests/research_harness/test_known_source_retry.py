"""Same-job continuation after a completed captured failure; no network or paid work."""
import asyncio
import copy
import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.research_harness.accepted_output import (
    AcceptedCheckpointProofV1, VALIDATOR_VERSION, VALIDATOR_SOURCE_SHA256, validation_boundary_pins,
)
from specimen_digitization.research_harness.agents import SpecialistOutput, specialist_output_schema_digest
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, CollectionProfile, FieldKey, FieldProfile, FieldResolution, LookupStatus,
    SourceResult, WorkState, digest,
)
from specimen_digitization.research_harness.gateway import ModelBinding
from specimen_digitization.research_harness.persistence import (
    BlobRef, BudgetExceeded, BudgetPolicy, DurabilityScope, LiveResearchAuthority,
    DurableEffectBroker, HeldUnknown, ImmutableFileBlobs, ResearchStore, SqliteStateBackend, StaleWork,
)
from specimen_digitization.research_harness.runtime import build_research_engine, runtime_pins
from specimen_digitization.research_harness.source_capture_v2 import (
    CaptureSourceBrokerV2, RegisteredCapturePolicyV2, SourceRequestEnvelopeV2,
)
from specimen_digitization.research_harness.sources import FixtureSourceTransport, GEOLOCATE_QUALIFICATION, insects_registry
from specimen_digitization.research_harness.thread_view import ResearchThreadReader
from specimen_digitization.research_harness.worker import ResearchRetryWorker
from test_geolocate_capture import RECORDED_BODY, geography_request, YEPOCAPA


def source_results(messages):
    return tuple(part.content if isinstance(part.content, SourceResult) else
        SourceResult.model_validate_json(part.content) if isinstance(part.content, str) else
        SourceResult.model_validate(part.content) for message in messages
        for part in message.parts if isinstance(part, ToolReturnPart) and part.tool_name == "lookup_source")


def resolution(result):
    key = result.coverage.field_key
    if result.status != LookupStatus.SUCCESS:
        return FieldResolution(field_key=key, work_state=WorkState.WAITING_SOURCE,
            value=FieldValue(), reason="Completed captured source returned a known failure")
    [candidate] = [json.loads(item) for item in result.candidate_json]
    ids = tuple(item.id for item in result.evidence)
    return FieldResolution(field_key=key, work_state=WorkState.RESOLVED, value_layer="settled",
        evidence_ids=ids, value=FieldValue(state=ValueState.SUPPORTED, normalized=candidate["value"],
            authority_id=candidate["authority_id"], evidence_ids=list(ids),
            evidence_relations=dict.fromkeys(ids, "supports")), reason="Recorded source supports the interpreted place")


def rig(tmp_path, *, budget_policy=None):
    registry = insects_registry(qualification_overrides={"geolocate": GEOLOCATE_QUALIFICATION})
    source = registry.get("geolocate")
    profile = CollectionProfile(id="insects", version="retry-fixture", organization_id="org",
        collection_id="insects", ancestry=(), knowledge_version="fixture",
        fields=tuple(FieldProfile(field_key=key) for key in ALL_FIELDS))
    request = geography_request(registry, profile_digest=digest(profile))
    request = request.model_copy(update={"field_keys": (FieldKey.COUNTRY, FieldKey.CITY),
        "prompt": request.prompt.model_copy(update={"output_schema_digest": specialist_output_schema_digest()})})
    requests = {request.role: request}
    policy = RegisteredCapturePolicyV2(source_id=source.id, source_policy_digest=digest(source),
        kind="full_response", owner_registration_digest=digest("fixture-registration"),
        owner_registration_origin="disposable local fixture", maximum_responses=1)
    source_pins = {"registry_digest": registry.digest,
        "capture_policies": {source.id: policy.model_dump(mode="json")},
        "acceptance_boundary": {"contract_version": "research-acceptance-boundary/v1",
            "validator_version": VALIDATOR_VERSION, "validator_source_sha256": VALIDATOR_SOURCE_SHA256,
            **validation_boundary_pins()}}
    bindings = {request.role: ModelBinding("harness-deepseek", "deepseek-ai/DeepSeek-V4.1-Flash",
        "deepinfra", 128, 10, "offline-retry-price")}
    settings = {"max_tokens": 128}
    durable = DurabilityScope(request.scope.organization_id, request.scope.collection_id,
        request.scope.specimen_id, request.scope.job_id, request.scope.generation, "reviewer", False)
    backend = SqliteStateBackend(tmp_path / "retry.sqlite")
    backend.grant(durable, role="reviewer")
    store = ResearchStore(backend, "same-cumulative-program")
    store.initialize(durable, budget_policy or BudgetPolicy(100, external_settled_micro_usd=7))
    store.create_job(durable, runtime_pins(profile, requests,
        model={role: {"route": binding.route_id, **asdict(binding)} for role, binding in bindings.items()},
        settings=settings, source_pins=source_pins), list(ALL_FIELDS))
    lease = store.claim(durable, "first-window", ttl_seconds=300)
    blobs = ImmutableFileBlobs(tmp_path / "blobs")
    calls, model_calls, seen_requests = [], [], []

    async def read(url, _policy):
        calls.append(url)
        return (429, b"busy") if len(calls) == 2 else (200, RECORDED_BODY)

    def engine(current_lease):
        broker = CaptureSourceBrokerV2(registry, {source.id: policy}, DurableEffectBroker(store, blobs),
            durable, current_lease, transport=FixtureSourceTransport(read), execution_class="offline")

        def model(scoped):
            seen_requests.append(scoped)
            def respond(messages, info):
                model_calls.append(scoped.retry_command_id)
                results = source_results(messages)
                if len(results) < len(scoped.field_keys):
                    key = scoped.field_keys[len(results)]
                    value = "Guatemala" if key == FieldKey.COUNTRY else "Yepocapa"
                    query = {"source_id": "geolocate", "field_key": str(key),
                        "query_text": json.dumps({**YEPOCAPA, "value": value})}
                    return ModelResponse([ToolCallPart("lookup_source", {"query": query},
                        tool_call_id=f"lookup-{key}")], usage=RequestUsage(input_tokens=1, output_tokens=1))
                output = SpecialistOutput(role=scoped.role, resolutions=tuple(resolution(item) for item in results))
                return ModelResponse([ToolCallPart(info.output_tools[0].name,
                    output.model_dump(mode="json"), tool_call_id="final")],
                    usage=RequestUsage(input_tokens=1, output_tokens=1))
            return FunctionModel(respond)

        return build_research_engine(profile=profile, requests=requests, store=store,
            scope=durable, lease=current_lease, blobs=blobs, tool_broker=broker,
            bindings=bindings, settings=settings, source_pins=source_pins,
            base_model_factory=model, actual_cost=lambda _: 2)

    first = engine(lease)
    outcome = asyncio.run(first.run())
    assert outcome.fields[FieldKey.COUNTRY].work_state == WorkState.RESOLVED
    assert outcome.fields[FieldKey.CITY].work_state == WorkState.WAITING_SOURCE
    return SimpleNamespace(store=store, durable=durable, lease=lease, blobs=blobs,
        calls=calls, model_calls=model_calls, requests=seen_requests, engine=engine,
        first=first, scope=request.scope, profile=profile)


def admit(f, **changes):
    return f.store.admit_retry(f.durable, "city", **{**dict(expected_generation=1,
        expected_field_revision=1, idempotency_key="one-source-continuation",
        execution_class="offline"), **changes})


def test_completed_failed_source_retries_same_job_without_replaying_settled_sibling(tmp_path):
    f = rig(tmp_path)
    before = f.store._read(f.durable).state
    job = before["jobs"][f.durable.key]
    sibling = copy.deepcopy(job["fields"]["country"])
    failed = copy.deepcopy(job["fields"]["city"]["checkpoint"])
    proof = AcceptedCheckpointProofV1.model_validate_json(f.blobs.get(BlobRef(**failed["accepted_output_proof"]["capture"])))
    assert {item.field_key for item in proof.checkpoints} == {FieldKey.COUNTRY, FieldKey.CITY}
    assert len(proof.acceptance.source_results) == 2
    assert f.store.budget(f.durable)["settled_micro_usd"] == 13
    f.store.release(f.durable, f.lease, blocked=True)
    thread = asyncio.run(ResearchThreadReader(f.first.journal).read(f.scope))
    assert next(row for row in thread.fields if row.field_key == FieldKey.CITY).actions == ("retry_field",)
    assert next(row for row in thread.fields if row.field_key == FieldKey.COUNTRY).actions == ()
    command = admit(f)
    assert admit(f) == command
    fresh = f.store.claim(f.durable, "source-continuation", ttl_seconds=300)
    worker = ResearchRetryWorker(store=f.store, engine_factory=lambda _scope, lease, _command: f.engine(lease))
    result = asyncio.run(worker.consume(f.durable, fresh, command["id"]))
    assert result.status == "completed"
    after = f.store._read(f.durable).state
    job = after["jobs"][f.durable.key]
    assert job["generation"] == 1 and job["fields"]["country"] == sibling
    assert job["fields"]["city"]["revision"] == 2
    assert job["fields"]["city"]["checkpoint"]["payload"]["resolution"]["work_state"] == "resolved"
    assert failed in job["checkpoints"]
    assert all(after["effects"][key] == value for key, value in before["effects"].items())
    assert len(f.calls) == 3 and len(f.model_calls) == 5
    [retry_request] = [item for item in f.requests if item.retry_command_id is not None]
    assert retry_request.field_keys == (FieldKey.CITY,) and retry_request.field_revisions == {FieldKey.CITY: 1}
    assert retry_request.retry_command_id == command["id"]
    assert f.store.budget(f.durable)["settled_micro_usd"] == 17
    assert f.store.budget(f.durable)["held_micro_usd"] == 0
    source_effects = [item for item in after["effects"].values() if item["operation_key"].startswith("source_capture_v2:")]
    assert len(source_effects) == 3
    originals = [SourceRequestEnvelopeV2.model_validate_json(f.blobs.get(BlobRef(**item["receipt"]["raw_capture"]))).original_request
        for item in source_effects]
    assert [item.retry_command_id for item in originals].count(command["id"]) == 1
    count = len(after["effects"])
    assert asyncio.run(worker.consume(f.durable, fresh, command["id"])) == result
    assert len(f.store._read(f.durable).state["effects"]) == count and len(f.calls) == 3


@pytest.mark.parametrize("barrier", ["active_lease", "locked", "paused", "stale_revision", "stale_generation",
    "halted", "budget_cap", "unknown_send", "unknown_cost", "reserved", "no_acceptance", "no_source",
    "wrong_field", "wrong_scope", "no_raw_capture", "unqualified_source", "not_failed", "policy_only",
    "unretained_proof", "wrong_proof_capture", "incomplete_run", "wrong_effect_identity",
    "cost_mismatch", "wrong_attempt_capture", "stale_attempt", "sibling_unknown_cost",
    "sibling_reserved", "external_held_cap"])
def test_waiting_source_continuation_refuses_unproved_or_unsafe_basis(tmp_path, barrier):
    f = rig(tmp_path)
    if barrier != "active_lease":
        f.store.release(f.durable, f.lease, blocked=True)

    def corrupt(state, _now):
        job = state["jobs"][f.durable.key]
        cp = job["fields"]["city"]["checkpoint"]
        source = next(item for item in state["effects"].values()
            if item["operation_key"].startswith("source_capture_v2:") and item["field_keys"] == ["city"])
        if barrier == "locked": job["fields"]["city"]["locked"] = True
        elif barrier == "paused": job["paused"] = True
        elif barrier in {"halted", "budget_cap"}:
            state["halted"] = barrier == "halted"
            if barrier == "budget_cap": state["ordinary_cost_micros"] = 100
        elif barrier == "unknown_send": source["status"] = "held_unknown"
        elif barrier == "unknown_cost": source["receipt"]["actual_micro_usd"] = source["actual_micro_usd"] = None
        elif barrier == "reserved": source["status"] = "reserved"
        elif barrier == "unretained_proof": state["journal"][cp["accepted_output_proof"]["native_run_id"]]["accepted_outputs"] = {}
        elif barrier == "wrong_proof_capture": cp["accepted_output_proof"]["capture"]["sha256"] = "0" * 64
        elif barrier == "incomplete_run": state["journal"][cp["accepted_output_proof"]["native_run_id"]]["snapshots"] = []
        elif barrier == "wrong_effect_identity": source["request_digest"] = "0" * 64
        elif barrier == "cost_mismatch": source["actual_micro_usd"] = 1
        elif barrier == "wrong_attempt_capture": source["attempts"][-1]["capture"]["sha256"] = "0" * 64
        elif barrier == "stale_attempt": source["attempts"].append({"attempt_id": "later", "status": "sending"})
        elif barrier == "external_held_cap": state["budget_policy"]["external_held_micro_usd"] = 100
        elif barrier in {"sibling_unknown_cost", "sibling_reserved"}:
            sibling = next(item for item in state["effects"].values() if item["field_keys"] == ["country"])
            if barrier == "sibling_unknown_cost": sibling["actual_micro_usd"] = None
            else: sibling["status"] = "reserved"
        elif barrier == "no_acceptance": cp.pop("accepted_output_proof")
        elif barrier == "no_source": cp["receipt_ids"] = [key for key in cp["receipt_ids"] if key != source["effect_id"]]
        elif barrier == "wrong_field": source["field_keys"] = ["country"]
        elif barrier == "wrong_scope": source["scope"]["generation"] = 0
        elif barrier == "no_raw_capture": source["receipt"]["raw_capture"] = None
        elif barrier == "unqualified_source": job["pins"]["sources"]["capture_policies"] = {}
        elif barrier in {"not_failed", "policy_only"}:
            source["receipt"]["typed_payload"]["status"] = "no_match" if barrier == "not_failed" else "policy_blocked"
            source["receipt"]["typed_payload"]["coverage"]["state"] = "exhausted" if barrier == "not_failed" else "unqualified"
    if barrier not in {"active_lease", "stale_revision", "stale_generation"}:
        f.store._mutate(f.durable, corrupt)
    before = f.store._read(f.durable).state
    with pytest.raises((StaleWork, HeldUnknown, BudgetExceeded)):
        admit(f, expected_field_revision=0 if barrier == "stale_revision" else 1,
            expected_generation=2 if barrier == "stale_generation" else 1)
    assert f.store._read(f.durable).state == before
    assert len(f.calls) == 2


def test_waiting_source_without_actual_source_completion_never_offers_retry(tmp_path):
    f = rig(tmp_path)
    f.store.release(f.durable, f.lease, blocked=True)
    f.store._mutate(f.durable, lambda state, _: state["jobs"][f.durable.key]["fields"]["city"]["checkpoint"].pop("accepted_output_proof"))
    assert not asyncio.run(f.first.journal.retry_eligible(f.scope, FieldKey.CITY))
    thread = asyncio.run(ResearchThreadReader(f.first.journal).read(f.scope))
    assert next(row for row in thread.fields if row.field_key == FieldKey.CITY).actions == ()


def test_expired_source_worker_custody_admits_one_new_retry_command(tmp_path):
    f = rig(tmp_path)
    f.store._mutate(f.durable, lambda state, now:
        state["jobs"][f.durable.key]["lease"].update(expires_at=now - 1))
    assert asyncio.run(f.first.journal.retry_eligible(f.scope, FieldKey.CITY))
    command = admit(f)
    assert command["status"] == "queued" and command["expected_generation"] == 1
    assert f.store.budget(f.durable)["settled_micro_usd"] == 13 and len(f.calls) == 2


@pytest.mark.parametrize("barrier", ["unknown_sibling", "source_proof", "budget", "locked"])
def test_source_retry_claim_rechecks_new_barriers_without_dispatch(tmp_path, barrier):
    f = rig(tmp_path)
    f.store.release(f.durable, f.lease, blocked=True)
    command = admit(f)
    lease = f.store.claim(f.durable, "claim-after-change", ttl_seconds=300)
    def change(state, _):
        job = state["jobs"][f.durable.key]
        if barrier == "source_proof":
            run = state["journal"][job["fields"]["city"]["checkpoint"]["accepted_output_proof"]["native_run_id"]]
            run["accepted_outputs"] = {}
        elif barrier == "unknown_sibling":
            next(item for item in state["effects"].values() if item["field_keys"] == ["country"])["status"] = "held_unknown"
        elif barrier == "budget": state["ordinary_cost_micros"] = 100
        else: job["fields"]["city"]["locked"] = True
    f.store._mutate(f.durable, change)
    before = f.store._read(f.durable).state
    with pytest.raises((StaleWork, HeldUnknown, BudgetExceeded)):
        f.store.claim_retry_command(f.durable, lease, command["id"])
    assert f.store._read(f.durable).state == before and len(f.calls) == 2


def test_imported_live_program_hold_refuses_source_retry_with_real_scope_authority(tmp_path):
    f = rig(tmp_path)
    f.store.release(f.durable, f.lease, blocked=True)
    f.store.live_authority = LiveResearchAuthority(f.durable.organization_id,
        f.durable.collection_id, f.durable.specimen_id, f.durable.actor_uid,
        "harness-deepseek", True)
    before = f.store._read(f.durable).state
    with pytest.raises(PermissionError, match="imported program HOLD"):
        admit(f, execution_class="live")
    assert f.store._read(f.durable).state == before and len(f.calls) == 2


def test_revoked_reviewer_cannot_admit_known_source_continuation(tmp_path):
    f = rig(tmp_path)
    f.store.release(f.durable, f.lease, blocked=True)
    f.store.backend.revoke(f.durable)
    with pytest.raises(PermissionError, match="membership"):
        admit(f)
    assert len(f.calls) == 2


def test_unacknowledged_native_publication_keeps_retry_held_after_lease_expiry(tmp_path):
    f = rig(tmp_path)
    job = f.store.job(f.durable)
    guard = f.store.prepare_publication(f.durable, f.lease, "country", expected_field_revision=1,
        expected_record_revision=job["record_revision"])
    f.store._mutate(f.durable, lambda state, now:
        state["jobs"][f.durable.key]["lease"].update(expires_at=now - 1))
    before = f.store._read(f.durable).state
    with pytest.raises(HeldUnknown, match="publication in doubt"):
        admit(f)
    assert not asyncio.run(f.first.journal.retry_eligible(f.scope, FieldKey.CITY))
    assert f.store._read(f.durable).state == before
    assert before["outbox"]["publish/" + guard["idempotency_key"]]["delivered"] is False
    assert len(f.calls) == 2


def test_exhausted_run_never_offers_or_admits_source_retry_despite_programme_headroom(tmp_path):
    from specimen_digitization.application.collection_profiles import published_registry
    from specimen_digitization.application.domain import Scope
    from specimen_digitization.application.lane_allowance import LEDGER_KIND, ProgramLedger
    from specimen_digitization.application.storage import SQLiteRepository
    from specimen_digitization.research_harness.production_runtime import research_budget_policy
    from specimen_digitization.research_harness.program_budget import ProgramEffectBroker

    run_policy = research_budget_policy(published_registry().profiles[0].model_dump(mode="json"), 7)
    f = rig(tmp_path, budget_policy=run_policy)
    f.store.live_authority = LiveResearchAuthority(f.durable.organization_id,
        f.durable.collection_id, f.durable.specimen_id, f.durable.actor_uid,
        "harness-deepseek", True)
    repository = SQLiteRepository(tmp_path / "programme.sqlite")
    programme_scope = Scope(organization_id=f.durable.organization_id, collection_id=f.durable.collection_id)
    ledger = ProgramLedger(repository, programme_scope)
    repository.put_document(programme_scope, LEDGER_KIND, ledger.ident,
        {"sensitive": False, "reserved_total_micros": 20}, 0)
    run = SimpleNamespace(profile=SimpleNamespace(execution=SimpleNamespace(
        program_allowance_micros=5_000_000, program_ledger_collection=f.durable.collection_id)))
    broker = ProgramEffectBroker(f.store, f.blobs, repository=repository, scope=f.durable, run=run)
    broker.reconcile(f.durable)
    programme_before = ledger.read()
    assert programme_before["reserved_total_micros"] == 26
    assert run_policy.ceiling_micro_usd == 1_000_000
    f.store.reserve_ordinary(f.durable, "parse:2", 1_000_000 - 13, 7)
    f.store.release(f.durable, f.lease, blocked=True)
    assert f.store.budget(f.durable)["remaining_micro_usd"] == 0
    before = f.store._read(f.durable).state
    assert not asyncio.run(f.first.journal.retry_eligible(f.scope, FieldKey.CITY))
    thread = asyncio.run(ResearchThreadReader(f.first.journal).read(f.scope))
    assert next(row for row in thread.fields if row.field_key == FieldKey.CITY).actions == ()
    with pytest.raises(BudgetExceeded, match="remaining cumulative allowance"):
        admit(f, execution_class="live")
    assert f.store._read(f.durable).state == before and ledger.read() == programme_before
    assert len(f.calls) == 2
