"""Offline worker fences and capture-to-review behavior; no provider calls."""
import asyncio
import hashlib
import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.research_harness.contracts import (
    FieldKey, ResearchScope, SourceCoverageReceipt, SourceCoverageState, SourceQuery, SourceResult,
)
from specimen_digitization.research_harness.derivation_worker import _progress, _resolution, _source_receipt
from specimen_digitization.research_harness.persistence import (
    BudgetPolicy, CapturedResult, DurabilityScope, DurableEffectBroker, ImmutableFileBlobs,
    HeldUnknown, PinnedRuntime, ResearchStore, SqliteStateBackend, StaleWork,
)
from specimen_digitization.research_harness.source_capture_v2 import OPERATION_PREFIX, tool_receipt_v2
from test_georef_harness import adapter, validation


@pytest.fixture
def runtime(tmp_path):
    scope = DurabilityScope("org", "collection", "specimen", "derivation-job", 1, "worker", False)
    backend = SqliteStateBackend(tmp_path / "derivation.sqlite")
    backend.grant(scope, role="reviewer")
    store = ResearchStore(backend, "existing-run-program")
    store.initialize(scope, BudgetPolicy(100))
    pins = PinnedRuntime("input", {"version": "p1"}, {"text": "pinned"},
        {"version": "s1"}, {"route": "unused"}, {"max_tokens": 128}, "specialist_harness_v2")
    store.create_job(scope, pins, ["country", "city", "province_state"], record_revision=5)
    lease = store.claim(scope, "worker-owner", ttl_seconds=30)
    return SimpleNamespace(store=store, scope=scope, lease=lease)


def command(**changes):
    return SimpleNamespace(**({"id": "a" * 64, "queued_revision": 5,
        "requested_fields": (FieldKey.PROVINCE_STATE,)} | changes))


def test_progress_is_lease_cas_and_terminal_result_is_immutable(runtime):
    requested = command()
    running = _progress(runtime, requested)
    assert running == {"request_id": requested.id, "status": "running",
        "checkpoint_ids": [], "blocked_reason": None}
    result = _progress(runtime, requested, status="blocked", blocked_reason="derivation_no_proposals")
    assert _progress(runtime, requested) == result
    before = runtime.store._read(runtime.scope)
    with pytest.raises(StaleWork, match="derivation_terminal_result_changed"):
        _progress(runtime, requested, status="completed")
    after = runtime.store._read(runtime.scope)
    assert after.revision == before.revision
    assert after.state == before.state
    assert not after.state["effects"]


def test_progress_refuses_another_command_and_arbitrary_checkpoint(runtime):
    _progress(runtime, command())
    with pytest.raises(StaleWork, match="derivation_command_changed"):
        _progress(runtime, command(id="b" * 64))
    with pytest.raises(StaleWork, match="derivation_checkpoint_unproved"):
        _progress(runtime, command(), status="completed", checkpoint_ids=("c" * 64,))


def test_progress_refuses_released_lease_or_wrong_record_revision(runtime):
    with pytest.raises(StaleWork, match="derivation_job_binding_changed"):
        _progress(runtime, command(queued_revision=6))
    runtime.store.release(runtime.scope, runtime.lease)
    with pytest.raises(StaleWork, match="Current active generation and lease"):
        _progress(runtime, command())


def source_result(status=LookupStatus.NO_MATCH):
    return SourceResult(status=status, coverage=SourceCoverageReceipt(
        source_id="georeference_spatial", field_key=FieldKey.PROVINCE_STATE,
        state=SourceCoverageState.SEARCHED, source_version="synthetic-v1",
        coverage_limit="Offline fixture", reason="No complete containment"))


def test_source_receipt_requires_real_same_scope_field_capture(runtime, tmp_path):
    scope = ResearchScope(**runtime.scope.identity(), sensitive=False,
        input_digest="0" * 64, profile_digest="1" * 64)
    request = SimpleNamespace(scope=scope)
    result = source_result()
    query = SourceQuery(source_id="georeference_spatial", field_key=FieldKey.PROVINCE_STATE)
    broker = DurableEffectBroker(runtime.store, ImmutableFileBlobs(tmp_path / "captures"))
    async def captured(*_):
        return CapturedResult(result.model_dump(mode="json"), 0)
    receipt = asyncio.run(broker.execute(runtime.scope, runtime.lease,
        OPERATION_PREFIX + "synthetic-spatial", {}, 1, captured, field_keys=("province_state",)))
    effect = runtime.store.effect(runtime.scope, receipt.effect_id)
    tool_receipt = tool_receipt_v2(request, query, effect, result)
    saved = result.model_copy(update={"receipt": tool_receipt})
    assert _source_receipt(runtime, request, saved, "georeference_spatial",
        FieldKey.PROVINCE_STATE) == receipt.effect_id
    with pytest.raises(StaleWork, match="derivation_source_receipt_unproved"):
        _source_receipt(runtime, request, result, "georeference_spatial", FieldKey.PROVINCE_STATE)
    changed = saved.model_copy(update={"status": LookupStatus.SUCCESS})
    with pytest.raises(StaleWork, match="derivation_source_receipt_unproved"):
        _source_receipt(runtime, request, changed, "georeference_spatial", FieldKey.PROVINCE_STATE)
    with pytest.raises(StaleWork, match="derivation_source_receipt_unproved"):
        _source_receipt(runtime, request, saved, "georeference_spatial", FieldKey.CITY)


def test_absence_and_operational_failure_do_not_become_human_proposals():
    absent = _resolution(command(), FieldKey.PROVINCE_STATE, source_result())
    assert absent.work_state == "waiting_source"
    assert absent.question is None and absent.value.parsed is None
    failure = _resolution(command(), FieldKey.PROVINCE_STATE, source_result(LookupStatus.PROVIDER))
    assert failure.work_state == "operational_failed"
    assert failure.question is None and failure.value.parsed is None


@pytest.fixture
def full_worker(tmp_path, adapter):
    """Real typed command, SQLite effects/journal and adapter; explicitly fake proof boundary."""
    from specimen_digitization.application.domain import FieldValue, Principal, Scope
    from specimen_digitization.application.storage import LocalBlobs
    from specimen_digitization.research_harness.contracts import SpecialistRequest, SpecialistRole, digest
    from specimen_digitization.research_harness.derivation_contracts import (
        DerivationCommand, SettledDerivationInput, derivation_input_digest,
    )
    from specimen_digitization.research_harness.derivation_worker import DerivationContext, ResearchDerivationWorker
    from specimen_digitization.research_harness.georeferencing import SettledLocationInput, derivation_source_result
    from specimen_digitization.research_harness.journal import DurableResearchJournal
    from specimen_digitization.research_harness.prompts import resolve_prompt

    tool, _ = adapter
    scope = DurabilityScope("org", "collection", "specimen", "derivation-job", 1, "worker", False)
    principal = Principal(user_id="worker", role="operator",
        scope=Scope(organization_id="org", collection_id="collection"))
    ordinary = LocalBlobs(tmp_path / "ordinary")
    inputs = []
    for key, value in ((FieldKey.COUNTRY, "Guatemala"), (FieldKey.CITY, "TestTown")):
        raw = json.dumps({"source_selection": None}).encode()
        inputs.append(SettledDerivationInput(field_key=key, value=value, evidence_ids=("review:" + str(key),),
            revision=4, authority_id="human:" + str(key), field_digest=digest(value),
            review_decision_id="review:" + str(key), provenance_blob_ref=ordinary.put(raw),
            provenance_sha256=hashlib.sha256(raw).hexdigest(), original_review_revision=4))
    requested = DerivationCommand(id="a" * 64, actor_uid="human", reason="Offline fixture",
        source_revision=4, queued_revision=5, canonical_run_id="run", source_snapshot_sha256="b" * 64,
        input_digest=derivation_input_digest(inputs), inputs=tuple(inputs),
        human_locked_fields=(FieldKey.COUNTRY, FieldKey.CITY), requested_fields=(FieldKey.PROVINCE_STATE,),
        idempotency_key="fixture", request_digest="c" * 64)
    backend = SqliteStateBackend(tmp_path / "full.sqlite")
    backend.grant(scope, role="reviewer")
    store = ResearchStore(backend, "existing-run-program")
    store.initialize(scope, BudgetPolicy(100))
    profile, registry = {"version": "fixture"}, "e" * 64
    prompt = resolve_prompt(SpecialistRole.GEOGRAPHY, profile_digest=digest(profile),
        source_registry_digest=registry, toolset_digest="f" * 64, model_route="test", output_schema_digest="0" * 64)
    pins = PinnedRuntime("d" * 64, profile, {str(prompt.role): prompt.model_dump(mode="json")},
        {"registry_digest": registry}, {str(prompt.role): {"route": "test"}}, {"max_tokens": 128}, "specialist_harness_v2")
    store.create_job(scope, pins, ["country", "city", "province_state"], record_revision=5)
    lease = store.claim(scope, "fixture-owner", ttl_seconds=300)
    rscope = ResearchScope(**scope.identity(), sensitive=False, input_digest="d" * 64, profile_digest=digest(profile))
    request = SpecialistRequest(scope=rscope, role=SpecialistRole.GEOGRAPHY,
        field_keys=(FieldKey.COUNTRY, FieldKey.CITY, FieldKey.PROVINCE_STATE), prompt=prompt,
        field_revisions={FieldKey.COUNTRY: 0, FieldKey.CITY: 0, FieldKey.PROVINCE_STATE: 0})
    blobs = ImmutableFileBlobs(tmp_path / "captures")
    effects = DurableEffectBroker(store, blobs)
    runtime = SimpleNamespace(store=store, scope=scope, lease=lease,
        blobs=blobs,
        journal=DurableResearchJournal(store, scope, lease, blobs),
        binding=SimpleNamespace(canonical=SimpleNamespace(record_revision=5, canonical_run_id="run")))
    specimen = SimpleNamespace(id="specimen", version=5, scope=principal.scope,
        run=SimpleNamespace(id="run", fields={}))

    class Worker(ResearchDerivationWorker):
        def _verify(self, *args):
            return context

    worker = Worker(SimpleNamespace(repository=object()), input_blobs=ordinary)
    context = DerivationContext(requested, specimen,
        tuple(SettledLocationInput(i.field_key, i.value, i.evidence_ids, i.revision, i.authority_id) for i in inputs),
        worker, principal)

    class Broker:
        status = LookupStatus.SUCCESS
        history_status = None
        spatial_status = None
        calls = []

        async def capture(self, request, query, result, *, logical=None, validation_receipt=None):
            self.calls.append(query.source_id)
            logical = query.model_dump(mode="json") if logical is None else logical
            async def dispatch(attempt_id, effect_id):
                raw = None
                if validation_receipt is not None:
                    raw = json.dumps({"contract_version": "research-computed-spatial-capture/v1",
                        "original_request": request.model_dump(mode="json"), "logical_request": logical,
                        "effect_id": effect_id, "attempt_id": attempt_id,
                        "binding_digest": store.job(scope)["binding_digest"],
                        "validation_receipt": validation_receipt.model_dump(mode="json"),
                        "settled_inputs": [asdict(i) for i in context.settled_inputs],
                        "semantic_result": result.model_dump(mode="json")}).encode()
                return CapturedResult(result.model_dump(mode="json"), 0, raw_payload=raw)
            receipt = await effects.execute(scope, lease, OPERATION_PREFIX + digest(logical),
                logical, 1, dispatch, field_keys=(str(query.field_key),))
            saved = store.effect(scope, receipt.effect_id)
            return result.model_copy(update={"receipt": tool_receipt_v2(request, query, saved, result)})

        async def validate_locked_anchor(self, request, query, *, anchor, command_digest):
            context.verify_locked_anchor(request, query, anchor, command_digest)
            result = tool.history_query(request, query) if query.source_id == "georeference_history" else validation()
            state = self.history_status if query.source_id == "georeference_history" else self.status
            if state is not None:
                result = result.model_copy(update={"status": state})
            return await self.capture(request, query, result)

        async def derive_spatial_from_trusted_inputs(self, request, *, field_key, command_digest, **kwargs):
            context.verify_current(request, command_digest, kwargs["settled_inputs"], kwargs["requested_fields"])
            result = derivation_source_result(tool.derive_rest(**kwargs), field_key)
            if self.spatial_status is not None:
                result = result.model_copy(update={"status": self.spatial_status})
            query = SourceQuery(source_id="georeference_spatial", field_key=field_key,
                query_text=json.dumps({"command_digest": command_digest}))
            validation_receipt = kwargs["validation"].receipt
            logical = {"contract_version": "research-computed-spatial-request/v1",
                "tool_id": "source_lookup", "source_id": "georeference_spatial",
                "scope": request.scope.model_dump(mode="json"), "original_request_digest": digest(request),
                "field_key": str(field_key), "field_revision": request.field_revisions[field_key],
                "requested_fields": [str(key) for key in context.command.requested_fields],
                "settled_inputs": [asdict(i) for i in context.settled_inputs],
                "validation_receipt_id": validation_receipt.id,
                "validation_result_digest": validation_receipt.result_digest,
                "trusted_derivation_command_digest": command_digest, "prompt_digest": request.prompt.digest,
                "source_registry_digest": request.prompt.source_registry_digest}
            return await self.capture(request, query, result, logical=logical,
                validation_receipt=validation_receipt)

    broker = Broker()
    runtime.derivation_services = SimpleNamespace(broker=broker, adapter=tool,
        context=context, requests={SpecialistRole.GEOGRAPHY: request})
    return SimpleNamespace(worker=worker, runtime=runtime, context=context, principal=principal, broker=broker)


def test_full_capture_no_match_retains_checkpoint_and_replays_without_new_effect(full_worker):
    case = full_worker
    case.broker.spatial_status = LookupStatus.NO_MATCH
    result = asyncio.run(case.worker.consume(case.runtime, case.principal, case.context))
    assert result.status == "completed" and len(result.checkpoint_ids) == 1
    job = case.runtime.store.job(case.runtime.scope)
    native = job["fields"]["province_state"]["checkpoint"]
    assert native["payload"]["resolution"]["work_state"] == "waiting_source"
    assert native["payload"]["resolution"]["value"]["parsed"] is None
    assert native["receipt_ids"] and job["dependencies"]["derivation_result"]["checkpoint_ids"] == list(result.checkpoint_ids)
    count = len(case.runtime.store._read(case.runtime.scope).state["effects"])
    assert asyncio.run(case.worker.consume(case.runtime, case.principal, case.context)) == result
    assert len(case.runtime.store._read(case.runtime.scope).state["effects"]) == count == 3


@pytest.mark.parametrize("status", [LookupStatus.AMBIGUOUS, LookupStatus.PROVIDER, LookupStatus.NO_MATCH])
def test_fresh_validation_failure_never_promoted_to_spatial_success(full_worker, status):
    case = full_worker
    case.broker.status = status
    result = asyncio.run(case.worker.consume(case.runtime, case.principal, case.context))
    assert result.status == "blocked" and result.blocked_reason == "derivation_geolocate_not_successful"
    assert not result.checkpoint_ids and "georeference_spatial" not in case.broker.calls
    effects = case.runtime.store._read(case.runtime.scope).state["effects"]
    geolocate = [e["receipt"]["typed_payload"] for e in effects.values()
        if e["receipt"]["typed_payload"]["coverage"]["source_id"] == "geolocate"]
    assert len(geolocate) == 1 and geolocate[0]["status"] == str(status)


def test_history_ambiguity_is_durably_blocked_without_validation(full_worker):
    case = full_worker
    case.broker.history_status = LookupStatus.AMBIGUOUS
    result = asyncio.run(case.worker.consume(case.runtime, case.principal, case.context))
    assert result.status == "blocked" and result.blocked_reason == "derivation_history_ambiguous"
    assert case.broker.calls == ["georeference_history"]


def test_full_success_is_review_only_and_recovery_acknowledges_committed_checkpoint(full_worker):
    case = full_worker
    result = asyncio.run(case.worker.consume(case.runtime, case.principal, case.context))
    job = case.runtime.store.job(case.runtime.scope)
    checkpoint = job["fields"]["province_state"]["checkpoint"]
    assert result.status == "completed" and result.checkpoint_ids == (checkpoint["id"],)
    resolution = checkpoint["payload"]["resolution"]
    assert resolution["work_state"] == "waiting_human"
    assert resolution["question"]["reason"] == "derived_proposal"
    assert resolution["value"]["parsed"] is None and resolution["value"]["state"] == "unknown"
    assert job["fields"]["city"]["revision"] == job["fields"]["country"]["revision"] == 0
    assert all(event["kind"] != "canonical_publication_required"
        for event in case.runtime.store._read(case.runtime.scope).state["outbox"].values())


@pytest.mark.parametrize("name,changed", [("record_revision", 6), ("canonical_run_id", "new-run")])
def test_post_open_revision_or_run_drift_refuses_before_source_dispatch(full_worker, name, changed):
    case = full_worker
    setattr(case.runtime.binding.canonical, name, changed)
    with pytest.raises(StaleWork, match="derivation_runtime_binding_changed"):
        asyncio.run(case.worker.consume(case.runtime, case.principal, case.context))
    assert not case.broker.calls
    assert not case.runtime.store._read(case.runtime.scope).state["effects"]


@pytest.mark.parametrize("error", [asyncio.CancelledError, HeldUnknown])
def test_uncertain_or_cancelled_worker_retains_lease_custody(full_worker, monkeypatch, error):
    case = full_worker
    async def opened(*args, **kwargs):
        assert kwargs["derivation_context"] is case.context
        return case.runtime
    async def uncertain(*args):
        raise error("fixture uncertain result")
    monkeypatch.setattr(case.worker.runtime_factory, "open", opened, raising=False)
    monkeypatch.setattr(case.worker, "consume", uncertain)
    before = case.runtime.store.job(case.runtime.scope)["lease"]
    with pytest.raises(error):
        asyncio.run(case.worker.run_registered(case.principal, "specimen", owner="fixture-owner"))
    assert case.runtime.store.job(case.runtime.scope)["lease"] == before


def test_missing_spatial_tool_receipt_cannot_write_a_checkpoint(full_worker, monkeypatch):
    case = full_worker
    case.broker.spatial_status = LookupStatus.NO_MATCH
    original = case.broker.derive_spatial_from_trusted_inputs
    async def without_receipt(*args, **kwargs):
        result = await original(*args, **kwargs)
        return result.model_copy(update={"receipt": None})
    monkeypatch.setattr(case.broker, "derive_spatial_from_trusted_inputs", without_receipt)
    with pytest.raises(StaleWork, match="derivation_source_receipt_unproved"):
        asyncio.run(case.worker.consume(case.runtime, case.principal, case.context))
    assert case.runtime.store.job(case.runtime.scope)["fields"]["province_state"]["checkpoint"] is None


def test_lost_checkpoint_ack_recovery_validates_and_reuses_without_more_source_work(full_worker, monkeypatch):
    from specimen_digitization.research_harness import derivation_worker

    case = full_worker
    case.broker.spatial_status = LookupStatus.NO_MATCH
    original = derivation_worker._progress
    def lost_ack(*args, **kwargs):
        if kwargs.get("status") == "running" and kwargs.get("checkpoint_ids"):
            raise OSError("Synthetic lost acknowledgement after journal commit")
        return original(*args, **kwargs)
    monkeypatch.setattr(derivation_worker, "_progress", lost_ack)
    with pytest.raises(OSError):
        asyncio.run(case.worker.consume(case.runtime, case.principal, case.context))
    prior = list(case.broker.calls)
    checkpoint = case.runtime.store.job(case.runtime.scope)["fields"]["province_state"]["checkpoint"]
    assert checkpoint is not None
    monkeypatch.setattr(derivation_worker, "_progress", original)
    result = asyncio.run(case.worker.consume(case.runtime, case.principal, case.context))
    assert result.status == "completed" and result.checkpoint_ids == (checkpoint["id"],)
    assert case.broker.calls == prior


def test_terminal_replay_checks_full_journal_integrity(full_worker):
    case = full_worker
    case.broker.spatial_status = LookupStatus.NO_MATCH
    asyncio.run(case.worker.consume(case.runtime, case.principal, case.context))
    def corrupt(state, now):
        job = case.runtime.store._lease(state, case.runtime.scope, case.runtime.lease, now)
        job["fields"]["province_state"]["checkpoint"]["payload"]["prompt_digest"] = "8" * 64
    case.runtime.store._mutate(case.runtime.scope, corrupt, lease=case.runtime.lease)
    prior = list(case.broker.calls)
    with pytest.raises(StaleWork, match="checkpoint_native_typed_binding_mismatch"):
        asyncio.run(case.worker.consume(case.runtime, case.principal, case.context))
    assert case.broker.calls == prior


def test_computed_capture_for_another_command_cannot_checkpoint(full_worker, monkeypatch):
    case = full_worker
    case.broker.spatial_status = LookupStatus.NO_MATCH
    original = case.broker.capture
    async def wrong_command(request, query, result, **kwargs):
        if query.source_id == "georeference_spatial":
            kwargs["logical"] = {**kwargs["logical"], "trusted_derivation_command_digest": "9" * 64}
        return await original(request, query, result, **kwargs)
    monkeypatch.setattr(case.broker, "capture", wrong_command)
    with pytest.raises(StaleWork, match="derivation_spatial_capture_unproved"):
        asyncio.run(case.worker.consume(case.runtime, case.principal, case.context))
    assert case.runtime.store.job(case.runtime.scope)["fields"]["province_state"]["checkpoint"] is None


def test_changed_immutable_computation_bytes_cannot_checkpoint(full_worker, monkeypatch):
    case = full_worker
    case.broker.spatial_status = LookupStatus.NO_MATCH
    original = case.broker.derive_spatial_from_trusted_inputs
    blobs = case.runtime.blobs
    async def changed_capture(*args, **kwargs):
        result = await original(*args, **kwargs)
        case.runtime.blobs = SimpleNamespace(get=lambda reference: blobs.get(reference) + b" ")
        return result
    monkeypatch.setattr(case.broker, "derive_spatial_from_trusted_inputs", changed_capture)
    with pytest.raises(StaleWork, match="derivation_spatial_capture_unproved"):
        asyncio.run(case.worker.consume(case.runtime, case.principal, case.context))
    assert case.runtime.store.job(case.runtime.scope)["fields"]["province_state"]["checkpoint"] is None


def test_raw_locality_elevation_prevents_dem_absence_claim():
    from specimen_digitization.application.domain import FieldValue, ValueState
    from specimen_digitization.research_harness.derivation_worker import _label_elevation
    from specimen_digitization.research_harness.georeferencing import ELEVATION_FIELDS

    fields = {key: FieldValue(state=ValueState.NOT_PRESENT) for key in ELEVATION_FIELDS}
    specimen = SimpleNamespace(run=SimpleNamespace(fields=fields))
    assert _label_elevation(specimen) is False
    fields[FieldKey.PRECISE_LOCATION] = FieldValue(literal="TestTown, 500 m")
    assert _label_elevation(specimen) is True
    fields[FieldKey.PRECISE_LOCATION] = FieldValue(verbatim_by_observation={"reader": "TestTown, 4800 ft"})
    assert _label_elevation(specimen) is True


def test_worker_verify_reconstructs_real_repository_proofs_and_exact_queued_revision(tmp_path):
    """Named SQL transport is synthetic; original review proof reader/saves are real."""
    from specimen_digitization.application.domain import AuditEvent, FieldValue, Principal
    from specimen_digitization.application.production import SqlConnectRepository, actor_uid
    from specimen_digitization.application.storage import LocalBlobs, digest as canonical_digest
    from specimen_digitization.research_harness.contracts import digest
    from specimen_digitization.research_harness.derivation_contracts import (
        DerivationCommand, DerivationRequest, derivation_input_digest,
    )
    from specimen_digitization.research_harness.derivation_inputs import collect_settled_inputs
    from specimen_digitization.research_harness.derivation_worker import ResearchDerivationWorker
    from test_review_projection_provenance import CanonicalSession, save, specimen
    from test_projection_writer import Response

    class Session(CanonicalSession):
        def post(self, url, json, timeout):
            if json["operationName"] == "GetSpecimen" and self.snapshots:
                revision = max(self.snapshots)
                return Response({"data": {"specimen": {"revision": revision, "sensitive": False},
                    "specimenSnapshots": [self.snapshots[revision]]}})
            return super().post(url, json, timeout)

    blobs = LocalBlobs(tmp_path / "proofs")
    repository = SqlConnectRepository(session=Session(), graph_blobs=blobs)
    original = specimen(blobs)
    original.run.fields = {"country": FieldValue(), "province_state": FieldValue()}
    principal = Principal(user_id="A", scope=original.scope, role="reviewer")
    token = actor_uid.set("A")
    try:
        current = repository.create(principal, original, "create", canonical_digest("create"))
        value = FieldValue(state="supported", literal="Guatemala", normalized="Guatemala")
        current.run.fields["country"] = value
        current.audit.append(AuditEvent(actor="A", action="review_field", reason="Checked original label",
            after={**value.model_dump(mode="json"), "field_key": "country"}))
        current = save(repository, current, "A", "manual-country")
        inputs = collect_settled_inputs(repository, current, blobs)
        source = repository.version_info(current.scope, current.id, current.version)
        request = DerivationRequest(expected_record_revision=current.version,
            base_record_version_id=f"{current.run.id}:{current.version}",
            reason="Derive remaining fields", requested_fields=(FieldKey.PROVINCE_STATE,))
        identity = digest({"actor": "A", "scope": current.scope.model_dump(mode="json"),
            "specimen_id": current.id, "run_id": current.run.id, "revision": current.version,
            "snapshot_sha256": source["sha256"], "key": "queue", "request": digest(request)})
        command = DerivationCommand(id=identity, actor_uid="A", reason=request.reason,
            source_revision=current.version, queued_revision=current.version + 1,
            canonical_run_id=current.run.id, source_snapshot_sha256=source["sha256"],
            inputs=inputs, input_digest=derivation_input_digest(inputs),
            human_locked_fields=(FieldKey.COUNTRY,), requested_fields=request.requested_fields,
            idempotency_key="queue", request_digest=digest(request))
        current.run.dependencies["research_derivation_request"] = command.model_dump(mode="json")
        current.audit.append(AuditEvent(actor="A", action="review_derive_rest", reason=command.reason,
            before={"revision": command.source_revision, "run_id": command.canonical_run_id},
            after={"request_id": command.id, "input_digest": command.input_digest,
                "requested_fields": [str(key) for key in command.requested_fields]}))
        queued = save(repository, current, "A", "queue")
        worker = ResearchDerivationWorker(SimpleNamespace(repository=repository), input_blobs=blobs)
        verified = worker._verify(principal, queued.id)
        assert verified.command == command and verified.settled_inputs[0].value == "Guatemala"
        assert repository.get(principal.scope, queued.id).version == command.queued_revision
        queued = save(repository, queued, "A", "later-save")
        with pytest.raises(StaleWork, match="derivation_input_revision_changed"):
            worker._verify(principal, queued.id, command)
    finally:
        actor_uid.reset(token)
