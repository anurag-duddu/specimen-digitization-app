"""Offline snapshot factory -> real Agent/journal -> derived-only repair.

The snapshot repository, readers and FunctionModel responses are synthetic.
Native checkpoint originals, accepted capture closure and reuse checks are real;
this is neither a live Data Connect nor a source-provider/native release proof.
"""
import asyncio
from copy import deepcopy
from dataclasses import asdict, replace
import json
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from specimen_digitization.application.active_graph import pack
from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.application.storage import digest as snapshot_digest
from specimen_digitization.research_harness.accepted_output import read_accepted_checkpoint_proof
from specimen_digitization.research_harness.agents import specialist_output_schema_digest
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, ROLE_FIELDS, CollectionProfile, FieldKey, FieldProfile,
    FieldResolution, SpecialistRequest, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.gateway import ModelBinding
from specimen_digitization.research_harness.initial_requests import NativeGenerationRequestFactory
from specimen_digitization.research_harness.measurement import settled_elevation_dependencies
from specimen_digitization.research_harness.persistence import (
    BudgetPolicy, DurabilityScope, ImmutableFileBlobs, ResearchStore,
    SqliteStateBackend, StaleWork,
)
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.runtime import build_research_engine, runtime_pins
from specimen_digitization.research_harness.sources import SourceBroker, SourceRegistry
from test_organiser_raw_reading_evidence import build, two_labels
from test_specialist_feedback import retry_parts

SOURCE = FieldKey.ELEVATION_FROM_FT
ROLE = SpecialistRole.MEASUREMENT


@pytest.fixture
def settled(tmp_path, monkeypatch):
    import httpx

    def refuse(*args, **kwargs):
        raise AssertionError("this offline fixture performs no HTTP")
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)
    monkeypatch.setattr(httpx.Client, "send", refuse)
    text = "Camp at 6,400 ft"
    built = build(two_labels(a=text), [(str(SOURCE), "2A", "6,400 ft", text),
                                      (str(SOURCE), "2B", "6,400 ft", text)])
    specimen = built.specimen
    profile = CollectionProfile(id="offline", version="1", organization_id="org", collection_id="collection",
        ancestry=("org", "collection"), knowledge_version="offline-v1",
        fields=tuple(FieldProfile(field_key=key) for key in ALL_FIELDS))
    specimen.run.profile_snapshot = {"fixture": "public-synthetic"}
    snapshot = pack(specimen, None)
    scope = built.scope.model_copy(update={"input_digest": snapshot_digest(snapshot), "profile_digest": digest(profile)})
    fragments, events, assemblies, evidence, decisions, candidates = NativeGenerationRequestFactory._build_graph(specimen, scope)
    registry = SourceRegistry(())
    requests = {role: SpecialistRequest(scope=scope, role=role, field_keys=keys,
        prompt=resolve_prompt(role, profile_digest=digest(profile), source_registry_digest=registry.digest,
            toolset_digest="c" * 64, model_route="harness-deepseek",
            output_schema_digest=specialist_output_schema_digest()),
        fragments=fragments, events=events, assemblies=assemblies, evidence=evidence, accepted_decisions=decisions,
        organiser_candidates=tuple(item for item in candidates if item.field_key in keys),
        field_revisions=dict.fromkeys(keys, 0)) for role, keys in ROLE_FIELDS.items()}
    settings = {"max_tokens": 128}
    bindings = {role: ModelBinding("harness-deepseek", "deepseek-ai/DeepSeek-V4.1-Flash", "deepinfra",
        128, 10, "offline-measurement-factory-v1") for role in requests}
    pins = runtime_pins(profile, requests, model={role: {"route": binding.route_id, **asdict(binding)}
        for role, binding in bindings.items()}, settings=settings)
    durable = DurabilityScope(**{key: getattr(scope, key) for key in
        ("organization_id", "collection_id", "specimen_id", "job_id", "generation", "sensitive")}, actor_uid="fixture")
    backend = SqliteStateBackend(tmp_path / "state.sqlite")
    backend.grant(durable)
    store = ResearchStore(backend, "offline-measurement-factory")
    store.initialize(durable, BudgetPolicy(1_000_000))
    store.create_job(durable, pins, list(ALL_FIELDS), record_revision=specimen.version)
    lease = store.claim(durable, "offline-measurement-factory")
    blobs = ImmutableFileBlobs(tmp_path / "proofs")
    calls = []
    assembly = next(item for item in assemblies if item.field_key == SOURCE)
    arguments = {"field_key": str(SOURCE), "event_id": assembly.event_id,
                 "assembly_ids": [item.id for item in assemblies if item.event_id == assembly.event_id]}

    def models(request):
        def respond(messages, _info):
            calls.append(request)
            assert not retry_parts(messages)
            if request.role != ROLE:
                rows = [FieldResolution(field_key=key, work_state=WorkState.WAITING_POLICY,
                    value=FieldValue(), reason="offline_fixture_other_role").model_dump(mode="json")
                    for key in request.field_keys]
            elif not any(isinstance(part, ToolReturnPart) for message in messages for part in message.parts):
                return ModelResponse(parts=[ToolCallPart("invoke_utility", {
                    "tool_id": "settle_elevation", "arguments": {
                        **arguments, "field_key": str(request.field_keys[0])}})])
            else:
                returned = next(part.content for message in messages for part in message.parts
                    if isinstance(part, ToolReturnPart))
                rows = [row for row in json.loads(returned.candidate_json[0])["resolutions"]
                        if FieldKey(row["field_key"]) in request.field_keys]
            return ModelResponse(parts=[ToolCallPart("final_result", {"role": request.role, "resolutions": rows})])
        return FunctionModel(respond)

    def engine(current_requests):
        return build_research_engine(profile=profile, requests=current_requests, store=store, scope=durable,
            lease=lease, blobs=blobs, tool_broker=SourceBroker(registry), bindings=bindings, settings=settings,
            base_model_factory=models, actual_cost=lambda _response: 1)

    # Settle only the written source first; all derived endpoints remain pending.
    first = {**requests, ROLE: SpecialistRequest.model_validate({**requests[ROLE].model_dump(mode="json"),
        "field_keys": (SOURCE,), "field_revisions": {SOURCE: 0}})}
    asyncio.run(engine(first).run())
    job = store.job(durable)
    assert job["fields"][str(SOURCE)]["work_state"] == "resolved"
    proof_reader = lambda checkpoint_id: read_accepted_checkpoint_proof(store, durable, blobs, checkpoint_id)

    class SnapshotRepository:
        graph_blobs = None
        def variables(self, _scope):
            return {}
        def execute(self, operation, variables):
            assert operation == "GetSnapshot" and variables == {"id": specimen.id, "revision": specimen.version}
            return {"specimenSnapshot": {"sha256": snapshot_digest(snapshot), "snapshot": deepcopy(snapshot)}}

    async def access(_principal, sensitive):
        assert sensitive is False

    # Explicit synthetic canonical boundary; the factory validates the genuine
    # retained snapshot and the real journal's native checkpoint/proof closure.
    binding = SimpleNamespace(canonical=SimpleNamespace(sensitive=False, specimen_id=specimen.id),
        base_canonical=SimpleNamespace(record_revision=specimen.version,
            snapshot_sha256=snapshot_digest(snapshot), canonical_run_id=specimen.run.id),
        source_sha256=specimen.asset.sha256, canonical_profile_digest=snapshot_digest(specimen.run.profile_snapshot),
        profile_digest=digest(profile), program_key=store.program_key, research_scope=lambda: scope,
        validate_job=lambda candidate, program_key: None)
    factory = NativeGenerationRequestFactory(SnapshotRepository(), verify_access=access, registry=registry,
        checkpoint_proof_reader=proof_reader)
    principal = SimpleNamespace(scope=specimen.scope)
    return SimpleNamespace(job=job, store=store, durable=durable, scope=scope, blobs=blobs, reader=proof_reader,
        factory=factory, principal=principal, binding=binding, engine=engine, calls=calls, arguments=arguments, pins=pins)


def test_factory_carries_real_accepted_current_source_into_derived_only_agent_and_replay(settled):
    current = asyncio.run(settled.factory(settled.principal, settled.binding, settled.job))
    [pin] = current[ROLE].dependencies
    native = settled.job["fields"][str(SOURCE)]["checkpoint"]
    assert pin.field_key == SOURCE and pin.revision == native["revision"] == 1
    assert pin.digest == digest(native["payload"]["resolution"])
    assert all(not request.dependencies for role, request in current.items() if role != ROLE)
    before = deepcopy(native)
    prior_calls = len(settled.calls)
    result = asyncio.run(settled.engine(current).run())
    repaired = [request for request in settled.calls[prior_calls:] if request.role == ROLE]
    assert len(repaired) == 2 and SOURCE not in repaired[0].field_keys
    assert repaired[0].dependencies == (pin,)
    for key in ROLE_FIELDS[ROLE]:
        row = result.fields[key]
        assert row.work_state == WorkState.RESOLVED
        assert row.value.normalized == ("6400.00" if str(key).endswith("_ft") else "1950.72")
        if key != SOURCE:
            assert row.derivation.source_revision == 1 and row.dependencies == (pin,)
    assert settled.store.job(settled.durable)["fields"][str(SOURCE)]["checkpoint"] == before
    calls = len(settled.calls)
    replayed = asyncio.run(settled.engine(current).run())
    assert replayed.fields == result.fields and len(settled.calls) == calls
    for key in ROLE_FIELDS[ROLE]:
        checkpoint_id = settled.store.job(settled.durable)["fields"][str(key)]["checkpoint"]["id"]
        proof = settled.reader(checkpoint_id)
        assert any(row.field_key == key for row in proof.checkpoints)


@pytest.mark.parametrize("kind", ("no_reader", "no_checkpoint", "bare_revision", "no_accepted_proof", "locked",
    "preserved_human", "unknown", "nonsettled", "failed", "wrong_prompt", "wrong_settings", "wrong_registry"))
def test_only_real_current_supported_written_native_source_supplies_a_pin(settled, kind):
    job = deepcopy(settled.job)
    field = job["fields"][str(SOURCE)]
    reader = settled.reader
    if kind == "no_reader":
        reader = None
    elif kind in {"no_checkpoint", "bare_revision"}:
        field["checkpoint"] = None
        field["revision"] = 7 if kind == "bare_revision" else 0
    elif kind == "no_accepted_proof":
        field["checkpoint"].pop("accepted_output_proof")
    elif kind == "locked":
        field["locked"] = True
    elif kind == "preserved_human":
        job["preserved_human_outcomes"] = {str(SOURCE): {"fixture": "protected Unknown is not a native pin"}}
    else:
        native = field["checkpoint"]
        payload = native["payload"]
        if kind == "unknown":
            payload["resolution"]["value"] = FieldValue(state=ValueState.UNKNOWN, reason="human choice").model_dump(mode="json")
            payload["resolution"]["work_state"] = field["work_state"] = "waiting_policy"
        elif kind == "nonsettled":
            payload["resolution"]["value_layer"] = "verbatim"
        elif kind == "failed":
            field["work_state"] = "operational_failed"
        elif kind == "wrong_prompt":
            payload["prompt_digest"] = "a" * 64
        elif kind == "wrong_settings":
            payload["model_settings_digest"] = "a" * 64
        elif kind == "wrong_registry":
            payload["source_registry_digest"] = "a" * 64
        native["id"] = digest({"scope": native["scope"], "field": str(SOURCE), "revision": native["revision"], "payload": payload})
    assert settled_elevation_dependencies(job, settled.scope, checkpoint_proof_reader=reader) == ()


@pytest.mark.parametrize("kind", ("revision", "native_id", "scope", "unproved_reuse", "accepted_capture", "wrong_proof"))
def test_stale_or_unproved_source_cannot_be_selected_by_the_factory(settled, kind):
    job = deepcopy(settled.job)
    field = job["fields"][str(SOURCE)]
    reader = settled.reader
    if kind == "revision":
        field["revision"] += 1
    elif kind == "native_id":
        field["checkpoint"]["id"] = "0" * 64
    elif kind == "scope":
        field["checkpoint"]["scope"]["generation"] += 1
    elif kind == "unproved_reuse":
        field["reuse"] = {"fixture": "invented"}
    elif kind == "accepted_capture":
        field["checkpoint"]["accepted_output_proof"]["proof_digest"] = "0" * 64
    elif kind == "wrong_proof":
        reader = lambda _checkpoint_id: None
    with pytest.raises((PublicationUnavailable, StaleWork), match="checkpoint|reuse|accepted_source"):
        settled_elevation_dependencies(job, settled.scope, checkpoint_proof_reader=reader)


def test_qualified_generation_reuse_keeps_the_original_native_revision_and_accepted_capture(settled):
    native = deepcopy(settled.job["fields"][str(SOURCE)]["checkpoint"])
    settled.store.backend.grant(settled.durable, role="reviewer")
    new_durable = settled.store.correct_fields(settled.durable, ["habitat"],
        expected_generation=settled.durable.generation,
        new_pins=replace(settled.pins, input_digest="a" * 64))
    new_scope = settled.scope.model_copy(update={"generation": new_durable.generation, "input_digest": "a" * 64})
    job = settled.store.job(new_durable)
    reader = lambda checkpoint_id: read_accepted_checkpoint_proof(settled.store, new_durable, settled.blobs, checkpoint_id)
    [pin] = settled_elevation_dependencies(job, new_scope, checkpoint_proof_reader=reader)
    assert pin.field_key == SOURCE and pin.revision == native["revision"] == 1
    assert pin.digest == digest(native["payload"]["resolution"])
    assert job["fields"][str(SOURCE)]["checkpoint"] == native
    assert job["fields"][str(SOURCE)]["reuse"]["checkpoint_digest"] == digest(native)


def test_current_derived_checkpoints_never_become_written_native_source_pins(settled):
    requests = asyncio.run(settled.factory(settled.principal, settled.binding, settled.job))
    asyncio.run(settled.engine(requests).run())
    job = settled.store.job(settled.durable)
    [pin] = settled_elevation_dependencies(job, settled.scope, checkpoint_proof_reader=settled.reader)
    assert pin.field_key == SOURCE
    assert all(job["fields"][str(key)]["checkpoint"]["payload"]["resolution"]["value_layer"] == "derived"
               for key in ROLE_FIELDS[ROLE] if key != SOURCE)
