"""Separate human outcomes over actual named-save proof; no provider effects."""
import asyncio
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_human_field_carry import CarryCase
from specimen_digitization.application.production import actor_uid
from specimen_digitization.application.human_field_carry import contract_pin, job_outcomes
from specimen_digitization.research_harness.api import create_research_router
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, ROLE_FIELDS, CollectionProfile, FieldKey, FieldProfile, ResearchScope,
    DependencyPin, FieldResolution, SpecialistRequest, SpecialistRole, WorkState, digest,
)
from specimen_digitization.application.domain import FieldValue
from specimen_digitization.research_harness.journal import DurableResearchJournal
from specimen_digitization.research_harness.persistence import (
    BudgetPolicy, DurabilityScope, PinnedRuntime, ResearchStore, SqliteStateBackend, StaleWork,
)
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.service import ResearchService
from specimen_digitization.research_harness.status import ResearchOutputV1
from specimen_digitization.research_harness.thread_view import ResearchThread, ResearchThreadReader
from test_canonical_materialization import materialization
from test_canonical_projection_v2 import native_basis


@pytest.fixture
def carried(tmp_path, request, monkeypatch):
    if getattr(request, "param", None) == "deterministic-wire":
        from datetime import datetime
        from uuid import NAMESPACE_URL, uuid5
        from specimen_digitization.application import domain
        import test_review_projection_provenance as source_fixture
        sequence = iter(range(1000))
        def next_uuid():
            return uuid5(NAMESPACE_URL, "synthetic-preserved-human-wire/v3/" + str(next(sequence)))
        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls.fromisoformat("2026-10-06T00:00:00+00:00")
                return value.astimezone(tz) if tz is not None else value.replace(tzinfo=None)
        monkeypatch.setattr(domain, "uuid4", next_uuid)
        monkeypatch.setattr(domain, "datetime", FixedDatetime)
        monkeypatch.setattr(source_fixture, "uuid4", next_uuid)
    token = actor_uid.set("B")
    try:
        c = CarryCase(tmp_path)
        c.review("elevation_from_m", state="unknown", reason="feet are not asserted metres")
        c.review("city", state="unknown", reason="slope is not a city")
        verified = c.reprocess()
        profile = CollectionProfile(id="synthetic-carry", version="1", organization_id=c.current.scope.organization_id,
            collection_id=c.current.scope.collection_id, ancestry=("synthetic",), knowledge_version="fixture",
            fields=tuple(FieldProfile(field_key=k) for k in ALL_FIELDS))
        durable = DurabilityScope(c.current.scope.organization_id, c.current.scope.collection_id,
            c.current.id, c.current.run.id + "-r" + str(c.current.version), 1, "B", False)
        scope = ResearchScope(**{k: getattr(durable, k) for k in ("organization_id", "collection_id", "specimen_id", "job_id", "generation", "sensitive")},
            input_digest=verified.snapshot_sha256, profile_digest=digest(profile))
        pins = PinnedRuntime(input_digest=scope.input_digest, profile=profile.model_dump(mode="json"),
            prompts={}, sources={"registry_digest": "b" * 64, "human_field_carry": contract_pin()},
            model={}, settings={}, engine_version="offline-fixture")
        backend = SqliteStateBackend(tmp_path / "research.sqlite")
        backend.repository = c.repo  # Actual named synthetic proof reader, not a mocked proof result.
        backend.grant(durable)
        store = ResearchStore(backend, "synthetic-carry-program")
        store.initialize(durable, BudgetPolicy(1000))
        store.create_job(durable, pins, list(ALL_FIELDS), record_revision=c.current.version,
            human_locks={k: v.proof_digest for k, v in verified.outcomes.items()},
            preserved_human_outcomes={k: v.model_dump(mode="json") for k, v in verified.outcomes.items()})
        journal = DurableResearchJournal(store, durable, store.claim(durable, "offline-worker"))
        yield SimpleNamespace(case=c, verified=verified, profile=profile, durable=durable, scope=scope,
            pins=pins, store=store, backend=backend, journal=journal)
    finally:
        actor_uid.reset(token)


def test_thread_keeps_twenty_fields_and_separate_human_outcomes_no_questions(carried):
    thread = asyncio.run(ResearchThreadReader(carried.journal).read(carried.scope))
    output = ResearchOutputV1.from_thread(thread)
    assert len(thread.fields) == 20 and thread.preserved_human_count == 2
    assert thread.resolved_count == thread.exception_count == 0
    assert len(output.preserved_human_outcomes) == 2 and output.checkpoints == ()
    assert output.preserved_human_base == thread.preserved_human_base
    assert output.status.status == "pending"  # Retained choices must not stop the other eighteen fields.
    for row in thread.fields:
        if str(row.field_key) in {"city", "elevation_from_m"}:
            assert row.value.state == "unknown" and row.checkpoint is None
            assert row.preserved_human.value == row.value
            assert not row.actions and row.review is None
            assert row.blocker_code == "preserved_human_decision"
    assert thread.preserved_human_base.registration_snapshot_sha256 == carried.scope.input_digest
    assert thread.preserved_human_base.canonical_run_id == carried.case.current.run.id


def test_lossless_wire_companion_retains_numbers_without_web_reserialization(carried):
    """Constructed numeric wire case; original proof qualification is separate."""
    from specimen_digitization.research_harness.thread_view import preserved_outcomes_json
    thread = asyncio.run(ResearchThreadReader(carried.journal).read(carried.scope))
    raw = thread.model_dump(mode="json")
    field = next(row for row in raw["fields"] if row["field_key"] == "city")
    metadata = {"integral_float": 1.0, "large_integer": 9007199254740993, "unicode": "é",
        "small_float": 1e-20, "negative_zero": -0.0}
    field["value"]["authority_identity"] = metadata
    field["preserved_human"]["value"]["authority_identity"] = metadata
    field["preserved_human"]["original_value"]["authority_identity"] = metadata
    from specimen_digitization.application.human_field_carry import PreservedHumanFieldOutcome
    outcomes = {row["field_key"]: PreservedHumanFieldOutcome.model_validate(row["preserved_human"])
        for row in raw["fields"] if row.get("preserved_human")}
    text = preserved_outcomes_json(outcomes)
    raw["preserved_human_base"].update(outcomes_json=text,
        outcome_digest=hashlib.sha256(text.encode("utf-8")).hexdigest())
    parsed = ResearchThread.model_validate(raw)
    assert '"integral_float":1.0' in text and '"large_integer":9007199254740993' in text
    assert '"negative_zero":-0.0' in text and '"unicode":"é"' in text
    output = ResearchOutputV1.from_thread(parsed)
    assert output.preserved_human_base.outcomes_json == text
    assert output.preserved_human_base.outcome_digest == digest({k: v.model_dump(mode="json") for k, v in outcomes.items()})
    # A rounded parsed projection must not be substituted for retained bytes.
    field["value"]["authority_identity"]["large_integer"] = 9007199254740992
    with pytest.raises(ValueError): ResearchThread.model_validate(raw)


@pytest.mark.parametrize("member", ["outcomes_json", "outcome_digest"])
def test_wire_companion_cannot_substitute_text_or_hash(carried, member):
    raw = asyncio.run(ResearchThreadReader(carried.journal).read(carried.scope)).model_dump(mode="json")
    raw["preserved_human_base"][member] = "{}" if member == "outcomes_json" else "0" * 64
    with pytest.raises(ValueError): ResearchThread.model_validate(raw)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_arbitrary_metadata_cannot_be_encoded_as_lossless_wire(carried, value):
    from specimen_digitization.research_harness.thread_view import preserved_outcomes_json
    outcome = carried.verified.outcomes["city"]
    field = outcome.value.model_copy(update={"authority_identity": {"numeric": value}})
    outcome = outcome.model_copy(update={"value": field})
    with pytest.raises(ValueError, match="preserved_human_outcome_json_invalid"):
        preserved_outcomes_json({"city": outcome})


def test_preserved_output_requires_same_lossless_base(carried):
    thread = asyncio.run(ResearchThreadReader(carried.journal).read(carried.scope))
    raw = ResearchOutputV1.from_thread(thread).model_dump(mode="json")
    raw.pop("preserved_human_base")
    with pytest.raises(ValueError): ResearchOutputV1.model_validate(raw)


@pytest.mark.parametrize("mutation", ["value", "scope", "count", "base", "actions"])
def test_thread_carry_variant_refuses_internal_inconsistency(carried, mutation):
    raw = asyncio.run(ResearchThreadReader(carried.journal).read(carried.scope)).model_dump(mode="json")
    field = next(r for r in raw["fields"] if r["field_key"] == "city")
    if mutation == "value": field["value"]["normalized"] = "invented"
    if mutation == "scope": field["preserved_human"]["specimen_id"] = "foreign"
    if mutation == "count": raw["preserved_human_count"] = 3
    if mutation == "base": raw["preserved_human_base"]["canonical_run_id"] = "foreign"
    if mutation == "actions": field["actions"] = ["retry_field"]
    with pytest.raises(ValueError): ResearchThread.model_validate(raw)


def test_current_origin_audit_is_rechecked_by_journal_before_use(carried):
    carried.case.session.audit[1]["actorUid"] = "foreign"
    with pytest.raises(ValueError):
        asyncio.run(carried.journal.preserved_human_outcomes(carried.scope))


def test_native_checkpoint_dependency_on_carried_field_refuses_before_work(carried):
    from specimen_digitization.research_harness.engine import ResearchEngine
    from specimen_digitization.research_harness.persistence import StaleWork
    requests = {role: SpecialistRequest(scope=carried.scope, role=role, field_keys=keys,
        prompt=resolve_prompt(role, profile_digest=carried.scope.profile_digest,
            source_registry_digest="b" * 64, toolset_digest="c" * 64,
            model_route="harness-deepseek", output_schema_digest="d" * 64))
        for role, keys in ROLE_FIELDS.items()}
    role = next(role for role, request in requests.items() if "country" in request.field_keys)
    dependency = DependencyPin(field_key="city", revision=1, digest=digest("invented native checkpoint"))
    requests[role] = requests[role].model_copy(update={"dependencies": (dependency,)})
    def no_harness(_requests):
        pytest.fail("unsupported carried dependency must refuse before a harness is constructed")
    engine = ResearchEngine(profile=carried.profile, requests=requests, journal=carried.journal,
        harness_factory=no_harness, model_settings_digest=digest({}))
    with pytest.raises(ValueError, match="preserved_human_native_dependency_unsupported"):
        asyncio.run(engine.run())
    with pytest.raises(StaleWork, match="preserved_human_native_dependency_unsupported"):
        asyncio.run(carried.journal.validate_request(requests[role], model_settings_digest=digest({})))
    job = carried.store.job(carried.durable)
    assert job["checkpoints"] == [] and all(row["revision"] == 0 for row in job["fields"].values())


def test_initial_native_publication_pass_keeps_eighteen_pending_fields_eligible(carried):
    from specimen_digitization.research_harness.native_worker import NativeResearchWorker
    worker = object.__new__(NativeResearchWorker)
    runtime = SimpleNamespace(binding=SimpleNamespace(research_scope=lambda: carried.scope),
        journal=carried.journal, store=carried.store, scope=carried.durable)
    result = asyncio.run(worker._publish_committed(runtime, carried.case.principal, carried.case.current.id))
    assert result.status == "pending" and result.reason_code is None
    assert result.checkpoint_ids == () and result.publication_receipt_ids == ()


def test_engine_schedules_eighteen_actual_offline_checkpoint_commits_not_two_humans(carried):
    """Scheduling/commit proof only; constructed resolutions are not science."""
    from specimen_digitization.research_harness.engine import ResearchEngine
    from specimen_digitization.research_harness.agents import specialist_output_schema_digest
    from specimen_digitization.research_harness.runtime import runtime_pins
    requests = {role: SpecialistRequest(scope=carried.scope, role=role, field_keys=keys,
        prompt=resolve_prompt(role, profile_digest=carried.scope.profile_digest,
            source_registry_digest="b" * 64, toolset_digest="c" * 64,
            model_route="harness-deepseek", output_schema_digest=specialist_output_schema_digest()))
        for role, keys in ROLE_FIELDS.items()}
    pins = runtime_pins(carried.profile, requests, model={role: {"route": "harness-deepseek"} for role in requests}, settings={})
    # A distinct new offline job is admitted with these exact runtime bindings;
    # no old job/pin is migrated to manufacture checkpoint authority.
    durable = replace(carried.durable, job_id=carried.durable.job_id + "-scheduling")
    scope = carried.scope.model_copy(update={"job_id": durable.job_id})
    requests = {role: request.model_copy(update={"scope": scope}) for role, request in requests.items()}
    carried.backend.grant(durable)
    pinned = replace(pins, sources={**pins.sources, "human_field_carry": contract_pin()})
    carried.store.create_job(durable, pinned, list(ALL_FIELDS), record_revision=carried.case.current.version,
        human_locks={k: v.proof_digest for k, v in carried.verified.outcomes.items()},
        preserved_human_outcomes={k: v.model_dump(mode="json") for k, v in carried.verified.outcomes.items()})
    journal = DurableResearchJournal(carried.store, durable, carried.store.claim(durable, "offline-scheduling"))
    called = []
    offered_by_role = {}
    class Harness:
        def __init__(self, selected): self.selected = selected
        async def run_specialist(self, role):
            request = self.selected[role]
            offered_by_role[role] = tuple(request.field_keys)
            called.extend(request.field_keys)
            return SimpleNamespace(resolutions=tuple(FieldResolution(field_key=key,
                work_state=WorkState.RESOLVED, value=FieldValue(state="supported", literal="synthetic"),
                evidence_ids=("synthetic:" + str(key),), reason="Constructed scheduling control") for key in request.field_keys))
    engine = ResearchEngine(profile=carried.profile, requests=requests, journal=journal,
        harness_factory=Harness, model_settings_digest=digest({}), validate=lambda _r, value, _s: value)
    result = asyncio.run(engine.run())
    assert len(called) == len(set(called)) == 18
    assert set(map(str, called)).isdisjoint({"city", "elevation_from_m"})
    assert offered_by_role[SpecialistRole.GEOGRAPHY] == tuple(
        key for key in ROLE_FIELDS[SpecialistRole.GEOGRAPHY] if key != FieldKey.CITY)
    assert len(result.checkpoints) == result.resolved_count == 18
    assert set(result.preserved_human_outcomes) == {"city", "elevation_from_m"}
    assert all(cp.field_key not in {"city", "elevation_from_m"} for cp in result.checkpoints)
    thread = asyncio.run(ResearchThreadReader(journal).read(scope))
    assert thread.resolved_count == 18 and thread.preserved_human_count == 2
    assert ResearchOutputV1.from_thread(thread).status.status == "waiting_input"


def canonical_carried_service(carried, native_basis, *, extra_locks=()):
    """Actual locally produced named-save proof through the current V2 reader.

    The native envelope, projection and import authority are synthetic fixtures;
    this exercises the service contract, never an executed native transaction.
    """
    from test_native_canonical_contract import ident
    from specimen_digitization.research_harness.discovery_v2 import CanonicalReadBindingV2
    from specimen_digitization.research_harness.native_canonical_v2 import CanonicalBindingV2
    from specimen_digitization.research_harness.publication_v2 import genesis_digest
    from specimen_digitization.research_harness.service import ResearchLocator

    document = carried.store._read(carried.durable)
    job = carried.store._job(document.state, carried.durable)
    # Reuse the named native fixture's inventory rather than inventing a model
    # checkpoint. Saved human provenance still comes from CarryCase's reader.
    identity = native_basis.binding.canonical.model_dump(mode="json")
    identity.update(record_revision=carried.case.current.version,
        canonical_run_id=carried.case.current.run.id,
        host_record_version_id=carried.case.current.run.id + ":synthetic-native",
        snapshot_sha256=carried.scope.input_digest)
    registration = native_basis.binding.registration.model_dump(mode="json")
    registration.update(base_canonical=identity, current_canonical=identity, job=job,
        job_id=carried.scope.job_id, job_key=carried.durable.key,
        generation=carried.scope.generation, input_digest=carried.scope.input_digest,
        profile_digest=carried.scope.profile_digest, runtime_binding_digest=job["binding_digest"],
        source_sha256=carried.case.current.asset.sha256, program_key=carried.store.program_key,
        human_locks={canonical: job["fields"][key]["locked"] or key in extra_locks
            for key, canonical in registration["field_mapping"].items()},
        read_bundle={"state_revision":document.revision, "server_time":document.server_time,
            "job_key":carried.durable.key, "job":job, "halted":document.state["halted"],
            "paused":job["paused"], "effects":{}, "outbox":{}, "hold_reasons":[]})
    row = {"canonical":{**identity, "organization_id":carried.scope.organization_id,
        "collection_id":carried.scope.collection_id, "specimen_id":carried.scope.specimen_id,
        "sensitive":carried.scope.sensitive}, "registrations":[registration],
        "snapshot":{"snapshot":carried.case.current.model_dump(mode="json"),
            "sha256":carried.scope.input_digest, "revision":carried.case.current.version,
            "contractVersion":"0.1"}, "projection":native_basis.raw["projection"],
        "active_registration_count":1, "causal":{"contract_version":"research-publication/v2",
            "authority_digest":digest("synthetic read-only carry fixture authority"),
            "import_proof_id":ident("synthetic read-only carry fixture import"),
            "import_proof_digest":digest("synthetic read-only carry fixture import"),
            "head_receipt_id":None, "head_chain_digest":genesis_digest(registration["binding_id"],
                native_basis.binding.canonical.model_validate(identity)),
            "causal_chain":[], "causal_count":0}}
    binding = CanonicalReadBindingV2(CanonicalBindingV2.from_native(
        carried.case.principal.scope, carried.case.current.id, row))
    locator = ResearchLocator(**carried.durable.identity())
    async def resolve(principal, requested):
        assert requested == locator
        return binding.durability_scope(principal)
    async def current(principal, specimen_id):
        assert specimen_id == carried.case.current.id
        assert binding.durability_scope(principal) == carried.durable
        return binding
    def no_retry(*args, **kwargs):
        pytest.fail("read-only carry fixture must not admit retries")
    service = ResearchService(store=carried.store, resolve_scope=resolve,
        retry_admission=no_retry, canonical_binding=current)
    return service, locator, binding


def test_canonical_service_preserves_verified_humans_after_native_lock_overlay(carried, native_basis):
    before = asyncio.run(ResearchThreadReader(carried.journal).read(carried.scope))
    service, locator, binding = canonical_carried_service(carried, native_basis)
    assert set(map(str, binding.research_locks)) == {"city", "elevation_from_m"}
    response = asyncio.run(service.thread(carried.case.principal, locator))
    # Validate the wire payload: model_copy and an existing model instance
    # can otherwise hide the contradictory state/blocker introduced by the overlay.
    thread = ResearchThread.model_validate(response.model_dump(mode="json"))
    assert thread.preserved_human_base == before.preserved_human_base
    assert len(thread.fields) == 20 and thread.preserved_human_count == 2
    assert thread.resolved_count == thread.exception_count == 0
    assert thread.effects == () and all(row.checkpoint is None for row in thread.fields)
    assert sum(row.work_state == WorkState.PENDING for row in thread.fields) == 18
    for key, outcome in carried.verified.outcomes.items():
        row = next(field for field in thread.fields if str(field.field_key) == key)
        assert row.preserved_human == outcome and row.value == outcome.value
        assert row.work_state == WorkState.WAITING_HUMAN
        assert row.blocker_code == "preserved_human_decision"
        assert row.actions == () and row.review is None
    output = ResearchOutputV1.from_thread(thread)
    assert output.preserved_human_base == before.preserved_human_base
    assert {str(row.field_key):row for row in output.preserved_human_outcomes} == carried.verified.outcomes
    assert output.checkpoints == ()


@pytest.mark.parametrize("stored_lock", [False, True])
def test_canonical_service_ordinary_lock_without_checkpoint_still_waits_for_policy(carried, native_basis, stored_lock):
    if stored_lock:
        carried.store._mutate(carried.durable, lambda state, _: state["jobs"][carried.durable.key]["fields"]["country"].update(locked=True))
    before = asyncio.run(ResearchThreadReader(carried.journal).read(carried.scope))
    prior = next(row for row in before.fields if row.field_key == "country")
    assert prior.work_state == (WorkState.WAITING_POLICY if stored_lock else WorkState.PENDING)
    service, locator, binding = canonical_carried_service(carried, native_basis, extra_locks=("country",))
    assert "country" in binding.research_locks
    response = asyncio.run(service.thread(carried.case.principal, locator))
    row = next(field for field in response.fields if field.field_key == "country")
    assert row.preserved_human is None and row.checkpoint is None
    assert row.value == prior.value and row.work_state == WorkState.WAITING_POLICY
    assert row.blocker_code == "policy_prerequisite" and row.actions == ()


@pytest.mark.parametrize("mutation,exception,reason", [
    ("malformed_outcome", ValueError, "preserved_human_field_provenance_unavailable"),
    ("missing_pin", ValueError, "preserved_human_field_provenance_unavailable"),
    ("unverified_value", StaleWork, "preserved_human_current_proof_changed"),
    ("unverified_origin", ValueError, "review_decision_provenance_invalid"),
])
def test_canonical_service_rejects_malformed_or_unverified_carry_before_overlay(carried, native_basis, mutation, exception, reason):
    if mutation == "unverified_origin":
        carried.case.session.audit[1]["actorUid"] = "foreign"
    else:
        def tamper(state, _):
            job = state["jobs"][carried.durable.key]
            if mutation == "malformed_outcome":
                job["fields"]["city"]["work_state"] = "waiting_policy"
            elif mutation == "missing_pin":
                job["pins"]["sources"].pop("human_field_carry")
                job["binding_digest"] = digest(job["pins"])
            else:
                job["preserved_human_outcomes"]["city"]["value"]["reason"] = "unverified replacement"
        carried.store._mutate(carried.durable, tamper)
    service, locator, _ = canonical_carried_service(carried, native_basis)
    with pytest.raises(exception, match=reason):
        asyncio.run(service.thread(carried.case.principal, locator))


@pytest.mark.parametrize("carried", ["deterministic-wire"], indirect=True)
def test_real_http_route_fixture_reports_two_humans_and_eighteen_pending_native_fields(carried):
    async def principal(): return carried.case.principal
    async def resolve(principal, locator): return carried.durable
    async def no_retry(*args, **kwargs): raise PermissionError("offline read only")
    service = ResearchService(store=carried.store, resolve_scope=resolve, retry_admission=no_retry)
    app = FastAPI()
    app.include_router(create_research_router(service, verified_principal_dependency=principal))
    root = (f"/v1/organizations/{carried.scope.organization_id}/collections/{carried.scope.collection_id}"
            f"/specimens/{carried.scope.specimen_id}/research/jobs/{carried.scope.job_id}/generations/1")
    client = TestClient(app)
    response = client.get(root + "/thread")
    assert response.status_code == 200, response.text
    thread = ResearchThread.model_validate(response.json())
    assert len(thread.fields) == 20 and thread.preserved_human_count == 2
    result = client.get(root + "/output")
    assert result.status_code == 200, result.text
    assert len(result.json()["preserved_human_outcomes"]) == 2 and result.json()["checkpoints"] == []
    # Explicit opt-in fixture emission is local-only and never runs a model.
    destination = os.environ.get("SPECIMEN_EMIT_HUMAN_CARRY_FIXTURE")
    if destination:
        path = Path(destination)
        path.write_text(json.dumps(response.json(), indent=2, sort_keys=True) + "\n")
    output_destination = os.environ.get("SPECIMEN_EMIT_HUMAN_CARRY_OUTPUT_FIXTURE")
    if output_destination:
        Path(output_destination).write_text(json.dumps(result.json(), indent=2, sort_keys=True) + "\n")
    if not destination and not output_destination:
        fixtures = Path(__file__).parents[1] / "fixtures" / "research_harness" / "http"
        # Normal tests never rewrite fixtures or normalize genuine hashes. Both
        # complete responses must match deterministic server-generated bytes.
        assert response.json() == json.loads((fixtures / "server-preserved-human-thread.json").read_bytes())
        assert result.json() == json.loads((fixtures / "server-preserved-human-output.json").read_bytes())


def test_final_native_materialization_preserves_two_unknowns_and_reaches_review(materialization, monkeypatch):
    """Pure writer/routing integration, synthetic native context and siblings.

    Source-proof admission is exercised separately above with actual named
    immutable-save reads. No SDK/publication transaction is claimed here.
    """
    from test_canonical_materialization_v2 import terminal_routing_case, produce_v2
    from test_canonical_projection_v2 import native_snapshot_proof
    from specimen_digitization.application.human_field_carry import (
        PreservedHumanFieldOutcome, VerifiedHumanCarries, adapt_projection,
    )
    from specimen_digitization.application.storage import digest as graph_digest
    from specimen_digitization.research_harness import canonical_materialization_v2 as module
    from specimen_digitization.research_harness.native_canonical_v2 import SqlConnectCanonicalResearchWriterV2
    from specimen_digitization.application.projection import writes
    b = terminal_routing_case(materialization, monkeypatch,
        work={"city": "waiting_human", "elevation_from_m": "waiting_human"},
        grounded=module.KEYS - {"city", "elevation_from_m"})
    # Explicit fixture context; do not call these fake origins actual saves.
    outcomes = {}
    for key in ("city", "elevation_from_m"):
        value = FieldValue(state="unknown", reason="Synthetic retained ordinary deassertion")
        b.prior.run.fields[key] = value
        outcomes[key] = PreservedHumanFieldOutcome(field_key=key, value=value, original_value=value,
            organization_id=b.prior.scope.organization_id, collection_id=b.prior.scope.collection_id,
            specimen_id=b.prior.id, canonical_run_id=b.prior.run.id, fresh_run_revision=2,
            origin_run_id="synthetic-origin", origin_event_id="synthetic-" + key,
            origin_revision=2, actor="synthetic-human", reason="Synthetic proof fixture",
            created_at="2026-10-06T00:00:00Z", original_evidence_ids=(), carry_digest=digest(key),
            proof_digest=digest("synthetic proof " + key), source_sha256=b.prior.asset.sha256)
    # Raise the supplied synthetic base revision, independent of work counts.
    b.prior.version = max(2, b.prior.version)
    b.prior.run.dependencies["preserved_human_fields"] = {k: {"fixture": "synthetic source context only"} for k in outcomes}
    reg = b.binding.registration.model_copy(deep=True)
    reg.job["pins"]["sources"] = {**reg.job["pins"].get("sources", {}), "human_field_carry": contract_pin()}
    reg.job["human_lock_proofs"] = {k: v.proof_digest for k, v in outcomes.items()}
    reg.job["preserved_human_outcomes"] = {k: v.model_dump(mode="json") for k, v in outcomes.items()}
    for key in outcomes:
        reg.job["fields"][key].update(locked=True, checkpoint=None, work_state="waiting_human")
    reg.human_locks.update({k: True for k in outcomes})
    verified = VerifiedHumanCarries(b.prior.id, b.prior.run.id, b.prior.version,
        graph_digest(b.prior.model_dump(mode="json")), outcomes)
    projected = adapt_projection(writes(b.prior, b.services.locate, b.services.size,
        b.principal.user_id), b.prior, verified)
    record = next(w.variables for w in projected if w.operation == "AppendRecordVersionV2")
    b.rows = tuple(w.variables for w in projected if w.operation == "AppendResolvedFieldV2")
    identity = native_snapshot_proof(b.prior, record["id"]).canonical
    reg = reg.model_copy(update={"current_canonical": identity, "base_canonical": identity})
    b.binding = b.binding.model_copy(update={"canonical": identity, "registration": reg})
    lineage = replace(b.source.context.lineage_context, job=reg.job, human_locks=reg.human_locks,
        prior_revision=b.prior.version, prior_snapshot_sha256=verified.snapshot_sha256,
        prior_record_version_id=identity.record_version_id, native_prior_snapshot=native_snapshot_proof(b.prior, record["id"]),
        prior_projection=b.rows)
    b.source.context = replace(b.source.context, canonical_snapshot_sha256=identity.snapshot_sha256,
        lineage_context=lineage, human_carries=verified)
    proof = produce_v2(b)
    assert proof.progress_receipt.wire_status == "completed"
    assert proof.result.run.disposition.value == "needs_human_review" and proof.result.run.stage == "finalized"
    assert proof.progress_receipt.exportable is False
    assert all(proof.result.run.fields[k] == b.prior.run.fields[k] for k in outcomes)
    assert not any(cp is not None for k, cp in ((k, reg.job["fields"][k]["checkpoint"]) for k in outcomes))
    assert len(proof.progress_receipt.canonical_field_work) == 20
    writer = SqlConnectCanonicalResearchWriterV2(None, None, blobs=None, operation_client=object())
    intent = SimpleNamespace(operation_digest=digest("synthetic carry publication"),
        actor_uid=b.principal.user_id, idempotency_key=b.prepared.basis.idempotency_key)
    payload = writer._materialization_v2(b.principal, b.prepared, b.binding,
        {"projection": list(b.rows)}, b.prior, proof, intent=intent,
        bundle=SimpleNamespace(target=b.source.context, human_carries=verified),
        projection_services=b.services, captured_evidence=b.evidence)
    assert payload["state"] == "completed" and payload["record"]["disposition"] == "needs_human_review"
    assert payload["receipt"]["projectionCount"] == len(payload["fields"]) == 20
    assert payload["snapshot"]["run"]["stage"] == "finalized"
    assert payload["snapshot"]["previous_runs"] == b.prior.model_dump(mode="json")["previous_runs"]
    before = {row["fieldKey"]: row for row in b.rows}
    after = {row["fieldKey"]: row for row in payload["fields"]}
    for key in outcomes:
        assert before[key]["candidateId"] is not None
        assert after[key]["candidateId"] == before[key]["candidateId"]
        assert after[key]["state"] == "unknown"
    assert not any(row["fieldKey"] in outcomes for row in payload["delta"]["candidates"])
