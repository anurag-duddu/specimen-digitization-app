"""SOURCE-AUTHORED, UNRUN: actual captures, native typed caller, no connector.

Collection requires a complete separately integrated package containing I2/I4A
and the ordinary PR168 modules. No partial PYTHONPATH overlay is a qualification.
"""
import asyncio
import copy
import hashlib
import io
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from specimen_digitization.application.workflow import crop_bytes
from specimen_digitization.application.domain import (
    Asset, Disposition, FieldValue, Observation, Principal, Region, Run, Scope, Specimen, Transcript,
)
from specimen_digitization.application.production import SqlConnectRepository
from specimen_digitization.application.projection import writes
from specimen_digitization.application.storage import LocalBlobs, digest as canonical_digest
from specimen_digitization.research_harness.canonical_evidence_provider_v2 import (
    CanonicalEvidenceProviderV2, build_captured_research_services_v2, native_input_context_v2,
)
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, FieldAssemblyCandidate, FieldCheckpoint, FieldKey, FieldResolution, SourceFragment,
    WorkState, digest,
)
from specimen_digitization.research_harness.native_canonical import CanonicalBindingV1, CanonicalIdentityV1
from specimen_digitization.research_harness.publication import NativeReceiptBinding, PreparedNativePublication
from specimen_digitization.research_harness.sources import canonical_json

# Default pytest prepend import mode resolves this sibling source-only fixture.
from test_source_capture_v2 import ident, make_capture_rig, query_once, saved_envelope


@pytest.fixture
def native_capture_rig(tmp_path):
    return make_native_capture_rig(tmp_path)


@pytest.fixture
def decided_native_capture_rig(tmp_path):
    return make_native_capture_rig(tmp_path, decided=True)


def make_native_capture_rig(tmp_path, *, decided=False):
    rig = make_capture_rig(tmp_path)
    graph = LocalBlobs(tmp_path / "canonical-blobs")
    # Explicit inert session prevents credentials lookup; no method is invoked.
    repository = SqlConnectRepository(session=object(), graph_blobs=graph)
    image = b"fixture original image bytes; no image decoder invoked"
    image_ref = graph.put(image)
    raw = b"fixture original extractor response"
    raw_ref = graph.put(raw)
    principal = Principal(user_id=rig.durable_scope.actor_uid,
        scope=Scope(organization_id=rig.scope.organization_id, collection_id=rig.scope.collection_id), role="reviewer")
    region = Region(id=ident("region"), asset_id=ident("asset"), x=0, y=0, width=1, height=1,
        order=0, method="fixture", version="fixture-v1")
    observation = Observation(id=ident("reading"), region_id=region.id, route_id="fixture-route",
        model_id="fixture-reader", provider="fixture", prompt_version="fixture-v1", input_sha256=hashlib.sha256(image).hexdigest(),
        input_asset_id=region.asset_id,
        request_sha256=digest("fixture original extractor request"), literal_text="Danaus plexippus",
        raw_ref=raw_ref, raw_sha256=hashlib.sha256(raw).hexdigest())
    prior = Specimen(id=rig.scope.specimen_id, scope=principal.scope,
        asset=Asset(id=region.asset_id, sensitive=False, sha256=hashlib.sha256(image).hexdigest(), blob_ref=image_ref,
            media_type="image/jpeg", size_bytes=len(image), width=1, height=1, filename="fixture.jpeg", uploader=principal.user_id),
        run=Run(id=ident("canonical-run"), regions=[region], observations=[observation],
            profile_snapshot={"fixture": "distinct ordinary canonical profile"},
            disposition=Disposition.DEFERRED, reasons=["fixture unresolved"]), version=1)
    prior.run.dependencies.update(profile_snapshot_sha256=canonical_digest(prior.run.profile_snapshot),
        profile_registry_version=prior.run.profile_registry_version)
    fragment = SourceFragment(id="fragment:actual-reading", scope=rig.scope, asset_id=prior.asset.id,
        asset_generation=repository.locate(prior.asset.blob_ref).generation, asset_digest=prior.asset.sha256,
        label_id=region.id, region_id=region.id, observation_id=observation.id, reader=observation.model_id,
        model_id=observation.model_id, prompt_digest=digest("fixture reader prompt"), observation_text=observation.literal_text,
        observation_digest=hashlib.sha256(observation.literal_text.encode()).hexdigest(), start=0,
        end=len(observation.literal_text), literal=observation.literal_text, order=0)
    if decided:
        decided_text = observation.literal_text
        observation.literal_text = "Danaus raw uncertain"
        first_raw = b"fixture independently retained first-pass decision response"
        call = observation.model_copy(deep=True, update={"id":ident("first-pass-call"),
            "literal_text":decided_text, "raw_ref":graph.put(first_raw),
            "raw_sha256":hashlib.sha256(first_raw).hexdigest(), "model_id":"fixture-decider"})
        prior.run.transcripts.append(Transcript(region_id=region.id, text=decided_text,
            observation_ids=[observation.id], alternatives=[], resolved=True, decision_kind="first_pass",
            selected_observation_id=observation.id, first_pass_call=call,
            reason="Actual local typed first-pass fixture, not native acceptance"))
        fragment = fragment.model_copy(update={"input_source":"decided_transcript"})
    rig.request = rig.request.model_copy(update={"fragments": (fragment,)})
    result = query_once(rig)
    effect, envelope = saved_envelope(rig, result)
    receipt = NativeReceiptBinding(effect_id=effect["effect_id"], request_digest=effect["request_digest"],
        binding_digest=effect["binding_digest"], attempt_id=effect["receipt"]["attempt_id"],
        receipt_digest=digest(effect["receipt"]), capture=effect["receipt"]["capture"], raw_capture=effect["receipt"]["raw_capture"])
    resolution = FieldResolution(field_key=FieldKey.TAXON, work_state=WorkState.WAITING_SOURCE,
        value=FieldValue(literal=fragment.literal, evidence_ids=[row.id for row in result.evidence],
            source_observation_id=observation.id), evidence_ids=tuple(row.id for row in result.evidence),
        source_coverage=(result.coverage,), reason="Actual fixture lookup retained; no supported decision invented")
    checkpoint = FieldCheckpoint(scope=rig.scope, field_key=FieldKey.TAXON, revision=1, resolution=resolution,
        prompt_digest=rig.request.prompt.digest, model_settings_digest=digest(rig.pins.settings),
        source_registry_digest=rig.registry.digest, effect_receipt_ids=(effect["effect_id"],))
    native = rig.store.checkpoint(rig.durable_scope, rig.lease, "taxon", checkpoint.model_dump(mode="json"),
        expected_revision=0, receipt_ids=(effect["effect_id"],))
    guard = rig.store.prepare_publication(rig.durable_scope, rig.lease, "taxon", expected_field_revision=1, expected_record_revision=1)
    document = rig.store._read(rig.durable_scope)
    native_guard_json = canonical_json(guard)
    publication_guard = {"scope": rig.scope.model_dump(mode="json"), "binding_digest": effect["binding_digest"],
        "lease_owner": rig.lease.owner, "lease_fence": rig.lease.fence, "lease_expires_at": rig.lease.expires_at,
        "expected_record_revision": 1, "checkpoint_revisions": {"taxon": 1}, "checkpoint_digests": {"taxon": digest(checkpoint)},
        "dependency_revisions": {}, "dependency_digests": {}, "receipt_ids": [effect["effect_id"]]}
    prepared = PreparedNativePublication.model_validate({"publication": {"guard": publication_guard,
        "checkpoints": [checkpoint.model_dump(mode="json")], "idempotency_key": guard["idempotency_key"]}, "basis": {
        "scope": rig.scope.model_dump(mode="json"), "actor_uid": principal.user_id, "program_key": "disposable-test-program",
        "job_key": rig.durable_scope.key, "state_revision": document.revision, "state_digest": digest(document.state),
        "binding_digest": effect["binding_digest"], "pins_digest": effect["binding_digest"], "lease": asdict(rig.lease),
        "field_key": "taxon", "field_revision": 1, "expected_record_revision": 1, "checkpoint_id": native["id"],
        "checkpoint_digest": digest(native), "original_typed_checkpoint_digest": digest(checkpoint),
        "typed_checkpoint_digest": digest(checkpoint), "original_scope": rig.scope.model_dump(mode="json"),
        "source_binding_digest": effect["binding_digest"], "reused": False, "dependencies": [], "receipts": [receipt.model_dump(mode="json")],
        "checkpoint_outbox_key": "checkpoint/" + native["id"], "checkpoint_outbox_digest": digest(document.state["outbox"]["checkpoint/" + native["id"]]),
        "publication_outbox_key": "publish/" + guard["idempotency_key"], "publication_outbox_digest": digest(document.state["outbox"]["publish/" + guard["idempotency_key"]]),
        "native_guard_json": native_guard_json, "native_guard_digest": hashlib.sha256(native_guard_json.encode()).hexdigest(),
        "idempotency_key": guard["idempotency_key"]}})
    identity = CanonicalIdentityV1(record_revision=1, record_version_id=ident("record-version"), canonical_run_id=prior.run.id,
        host_record_version_id=prior.run.id + ":1", snapshot_sha256=canonical_digest(prior.model_dump(mode="json")))
    mapping = {"field_mapping": {str(key): str(key) for key in ALL_FIELDS},
        "research_policy_origin": "disposable fixture owner registration; not real authorization",
        "journal_budget_policy_digest": digest(document.state["budget_policy"]), "evidence_sources": {
            rig.source.id: {"policy_digest": digest(rig.source), "canonical_source": rig.source.id,
                "input_context_rule": "exact_original_request_fragments/v2", "evidence_id_rule": "research-canonical-evidence/v1"}}}
    job = rig.store.job(rig.durable_scope)
    reg = {"binding_id": ident("binding"), "registration_revision": 1, "active": True,
        "base_canonical": identity.model_dump(mode="json"), "current_canonical": identity.model_dump(mode="json"), "publication_transition": None,
        "job_id": rig.scope.job_id, "job_key": rig.durable_scope.key, "generation": 1, "input_digest": rig.scope.input_digest,
        "profile_digest": rig.scope.profile_digest, "runtime_binding_digest": effect["binding_digest"],
        "canonical_profile_digest": canonical_digest(prior.run.profile_snapshot), "source_sha256": prior.asset.sha256,
        "semantic_mapping_digest": digest(mapping), "policy_digest": digest("fixture research policy distinct from budget"),
        "program_key": "disposable-test-program", "field_mapping": mapping["field_mapping"], "semantic_mapping": mapping,
        "human_locks": {str(key): False for key in ALL_FIELDS}, "job": job,
        "research_policy_origin": mapping["research_policy_origin"], "journal_budget_policy_digest": mapping["journal_budget_policy_digest"],
        "journal_budget_policy_origin": "verified_owner_registration_not_SQL_recomputed",
        "read_bundle": {"state_revision": document.revision, "server_time": document.server_time, "job_key": rig.durable_scope.key,
            "job": job, "halted": False, "paused": False, "effects": document.state["effects"], "outbox": {}, "hold_reasons": []}}
    projection = [row.variables for row in writes(prior, repository.locate, repository.blob_size, principal.user_id)
        if row.operation == "AppendResolvedFieldV2"]
    row = {"canonical": {**identity.model_dump(mode="json"), "organization_id": rig.scope.organization_id,
        "collection_id": rig.scope.collection_id, "specimen_id": rig.scope.specimen_id, "sensitive": False},
        "registrations": [reg], "active_registration_count": 1, "snapshot": {"snapshot": prior.model_dump(mode="json"),
            "sha256": identity.snapshot_sha256, "revision": 1, "contractVersion": "0.1"}, "projection": projection}
    binding = CanonicalBindingV1.from_native(principal.scope, prior.id, row)
    provider = CanonicalEvidenceProviderV2.from_service(repository, rig.effects, rig.registry)
    return SimpleNamespace(rig=rig, graph=graph, repository=repository, principal=principal, prior=prior,
        result=result, effect=effect, envelope=envelope, checkpoint=checkpoint, native=native,
        prepared=prepared, binding=binding, row=row, provider=provider, mapping=mapping)


def test_actual_factory_binds_capture_broker_and_verified_provider(native_capture_rig):
    f = native_capture_rig
    broker, provider = build_captured_research_services_v2(repository=f.repository, effect_broker=f.rig.effects,
        scope=f.rig.durable_scope, lease=f.rig.lease, registry=f.rig.registry, policies={f.rig.source.id: f.rig.policy},
        transport=f.rig.transport, execution_class="offline")
    assert broker.effects.broker is f.rig.effects and provider.source_blobs is f.rig.blobs
    assert provider.canonical_blobs is f.graph and provider.asset_locator.__self__ is f.repository
    restored = asyncio.run(provider.read(f.principal, f.prepared, f.binding))
    assert restored.request == f.rig.request and restored.tool_results == (f.result,)
    assert len(f.rig.calls) == 1


def test_v2_proof_copies_genuine_body_and_v1_remains_hold(native_capture_rig):
    f = native_capture_rig
    actual = asyncio.run(f.provider.capture_v2(f.principal, f.prepared, f.binding, f.prior))
    assert len(actual) == 1
    item = actual[0]
    assert item.original_specialist_request == f.rig.request
    assert f.graph.get(item.canonical_evidence.raw_ref) == f.rig.bodies[0]
    assert item.proof.selected_response.body.sha256 == item.canonical_evidence.digest
    assert item.proof.request_envelope.sha256 != item.canonical_evidence.digest
    assert item.proof.semantic_capture == f.prepared.basis.receipts[0].capture
    assert [str(value) for value in item.canonical_observation_ids] == [f.prior.run.observations[0].id]
    assert item.canonical_producer is not None and item.tool_input_lineage.input_sources == ("raw_reading",)
    original_input = item.tool_input_lineage.native_inputs[0]
    assert original_input.input_origin == "native_original_asset"
    assert original_input.input_ref == f.prior.asset.blob_ref
    assert original_input.input_generation == f.repository.locate(f.prior.asset.blob_ref).generation
    before = copy.deepcopy(f.rig.store._read(f.rig.durable_scope).state)
    with pytest.raises(PublicationUnavailable, match="canonical_source_capture_v2_requires_native_v2"):
        asyncio.run(f.provider.capture(f.principal, f.prepared, f.binding, f.prior))
    assert f.rig.store._read(f.rig.durable_scope).state == before and len(f.rig.calls) == 1


@pytest.mark.parametrize("change", ["actor", "generation", "unknown_cost", "raw_generation", "body_digest", "registry", "snapshot", "lease", "lock", "checkpoint"])
def test_unproved_capture_never_becomes_native_evidence(native_capture_rig, change):
    f = native_capture_rig
    principal, binding, prior = f.principal, f.binding, f.prior
    if change == "actor":
        principal = principal.model_copy(update={"user_id": "foreign-actor"})
    elif change == "generation":
        binding = binding.model_copy(update={"registration": binding.registration.model_copy(update={"generation": 2})})
    elif change == "unknown_cost":
        bundle = copy.deepcopy(binding.registration.read_bundle)
        bundle["effects"][f.effect["effect_id"]]["receipt"]["actual_micro_usd"] = None
        binding = binding.model_copy(update={"registration": binding.registration.model_copy(update={"read_bundle": bundle})})
    elif change == "raw_generation":
        raw_capture = f.prepared.basis.receipts[0].raw_capture.model_copy(update={"generation": "other-generation"})
        f.prepared = f.prepared.model_copy(update={"basis": f.prepared.basis.model_copy(update={"receipts": (
            f.prepared.basis.receipts[0].model_copy(update={"raw_capture": raw_capture}),)})})
    elif change == "body_digest":
        body = f.envelope.responses[0].body
        f.rig.blobs._path(body.locator).write_bytes(b"corrupted local fixture only")
    elif change == "registry":
        f.provider.registry.digest = digest("different registry")
    elif change in {"lease", "lock", "checkpoint"}:
        reg = binding.registration.model_copy(deep=True)
        if change == "lease": reg.job["lease"]["fence"] += 1
        if change == "lock": reg.human_locks["taxon"] = True
        if change == "checkpoint": reg.job["fields"]["taxon"]["checkpoint"]["payload"]["resolution"]["reason"] = "changed checkpoint"
        reg.read_bundle["job"] = reg.job
        binding = binding.model_copy(update={"registration": reg})
    else:
        prior = prior.model_copy(update={"version": 2})
    with pytest.raises((PublicationUnavailable, PermissionError)):
        asyncio.run(f.provider.capture_v2(principal, f.prepared, binding, prior))
    assert len(f.rig.calls) == 1


def proven_reuse(f):
    original, current = f.rig.scope, f.rig.scope.model_copy(update={"generation": 2})
    job = copy.deepcopy(f.binding.registration.job)
    history = {"scope": f.rig.durable_scope.identity(), "binding_digest": job["binding_digest"],
        "pins": copy.deepcopy(job["pins"]), "fields": {"taxon": copy.deepcopy(job["fields"]["taxon"])}}
    current_identity = {**f.rig.durable_scope.identity(), "generation": 2}
    job["generation"], job["history"] = 2, [history]
    job["lease"]["generation"] = 2
    job["fields"]["taxon"]["reuse"] = {"reused_from_scope_digest": digest(history["scope"]),
        "checkpoint_digest": digest(f.native), "into_scope_digest": digest(current_identity),
        "source_binding_digest": job["binding_digest"], "target_binding_digest": job["binding_digest"],
        "retained_dependencies": f.native["dependencies"], "retained_dependency_digests": f.native["dependency_digests"]}
    reused = FieldCheckpoint.model_validate({**f.checkpoint.model_dump(mode="json"), "scope": current.model_dump(mode="json"),
        "reused_from_scope_digest": digest(original), "reused_from_checkpoint_digest": digest(f.checkpoint)})
    data = f.prepared.model_dump(mode="json")
    data["publication"]["checkpoints"] = [reused.model_dump(mode="json")]
    data["publication"]["guard"]["scope"] = current.model_dump(mode="json")
    data["publication"]["guard"]["checkpoint_digests"] = {"taxon": digest(reused)}
    data["basis"].update(scope=current.model_dump(mode="json"), reused=True, history_digest=digest(history),
        typed_checkpoint_digest=digest(reused))
    data["basis"]["lease"]["generation"] = 2
    prepared = PreparedNativePublication.model_validate(data)
    reg = f.binding.registration.model_copy(update={"generation": 2, "job": job,
        "read_bundle": {**f.binding.registration.read_bundle, "job": job}})
    return prepared, f.binding.model_copy(update={"registration": reg})


def test_actual_lineage_keeps_original_generation_request_without_new_effect(native_capture_rig):
    f = native_capture_rig
    prepared, binding = proven_reuse(f)
    before = copy.deepcopy(f.rig.store._read(f.rig.durable_scope).state)
    context = asyncio.run(f.provider.read(f.principal, prepared, binding))
    evidence = asyncio.run(f.provider.capture_v2(f.principal, prepared, binding, f.prior))
    assert prepared.basis.scope.generation == 2 and context.request.scope.generation == 1
    assert context.request == f.rig.request and evidence[0].original_specialist_request == f.rig.request
    assert f.rig.store._read(f.rig.durable_scope).state == before and len(f.rig.calls) == 1


@pytest.mark.parametrize("change", ["missing_history", "bool_generation", "changed_receipt_scope"])
def test_historical_request_cannot_be_guessed_or_rebound(native_capture_rig, change):
    f = native_capture_rig
    prepared, binding = proven_reuse(f)
    reg = binding.registration.model_copy(deep=True)
    if change == "missing_history":
        reg.job["history"] = []
    elif change == "bool_generation":
        reg.job["history"][0]["scope"]["generation"] = True
        prepared = prepared.model_copy(update={"basis": prepared.basis.model_copy(update={"history_digest": digest(reg.job["history"][0])})})
    else:
        reg.read_bundle["effects"][f.effect["effect_id"]]["scope"]["generation"] = True
    reg.read_bundle["job"] = reg.job
    with pytest.raises(PublicationUnavailable):
        asyncio.run(f.provider.read(f.principal, prepared, binding.model_copy(update={"registration": reg})))
    assert len(f.rig.calls) == 1


def test_input_context_retains_all_actual_readings_and_never_picks_by_order(native_capture_rig):
    f = native_capture_rig
    observation = f.prior.run.observations[0].model_copy(update={"id": ident("second-reading")})
    prior = f.prior.model_copy(deep=True)
    prior.run.observations.append(observation)
    fragment = f.rig.request.fragments[0].model_copy(update={"id": "fragment:second", "observation_id": observation.id, "order": 1})
    request = f.rig.request.model_copy(update={"fragments": (*f.rig.request.fragments, fragment)})
    mapping = f.mapping["evidence_sources"][f.rig.source.id]
    context = native_input_context_v2(request, f.rig.query, f.checkpoint.resolution, prior, mapping,
        asset_generation=f.repository.locate(prior.asset.blob_ref).generation,
        native_inputs=asyncio.run(f.provider._native_inputs(request, prior)))
    assert [str(value) for value in context.observation_ids] == [row.id for row in prior.run.observations]
    assert str(context.selected_observation_id) == f.prior.run.observations[0].id
    assert "capture_contexts" not in f.mapping
    mixed = request.model_copy(update={"fragments": (request.fragments[0], fragment.model_copy(update={"input_source": "decided_transcript"}))})
    prior.run.transcripts.append(Transcript(region_id=observation.region_id, text=observation.literal_text,
        observation_ids=[observation.id], alternatives=[], resolved=True))
    mixed_context = native_input_context_v2(mixed, f.rig.query, f.checkpoint.resolution, prior, mapping,
        asset_generation=f.repository.locate(prior.asset.blob_ref).generation,
        native_inputs=asyncio.run(f.provider._native_inputs(mixed, prior)))
    # The selected reading grounds the value, so the mixed lineage still has
    # a single producer source.
    assert mixed_context.input_source == "raw_reading"
    assert mixed_context.tool_input_lineage.input_sources == ("raw_reading", "decided_transcript")
    # A value also grounded in an assembly of the decided transcript fragment
    # names two input sources, so the mixed lineage has no producer.
    resolution = f.checkpoint.resolution
    assembly = FieldAssemblyCandidate(id="assembly:transcript", scope=mixed.scope,
        field_key=resolution.field_key, event_id="event:transcript", fragment_ids=(fragment.id,),
        assertion_kind="complete", interpreted_text=observation.literal_text, rule_version="fixture",
        evidence_ids=("evidence:transcript",))
    both = mixed.model_copy(update={"assemblies": (assembly,)})
    both_context = native_input_context_v2(both, f.rig.query,
        resolution.model_copy(update={"assembly_ids": (assembly.id,)}), prior, mapping,
        asset_generation=f.repository.locate(prior.asset.blob_ref).generation,
        native_inputs=asyncio.run(f.provider._native_inputs(both, prior)))
    assert both_context.input_source is None
    assert both_context.tool_input_lineage.input_sources == ("raw_reading", "decided_transcript")


def test_readingless_v2_lineage_keeps_empty_inputs_without_fabricating_v1(native_capture_rig):
    f = native_capture_rig
    request = f.rig.request.model_copy(update={"fragments": ()})
    resolution = f.checkpoint.resolution.model_copy(update={"value": f.checkpoint.resolution.value.model_copy(update={"source_observation_id": None})})
    context = native_input_context_v2(request, f.rig.query, resolution, f.prior,
        f.mapping["evidence_sources"][f.rig.source.id], asset_generation=f.repository.locate(f.prior.asset.blob_ref).generation,
        native_inputs=())
    assert context.input_source is None and context.observation_ids == () and context.region_id is None
    assert context.tool_input_lineage.fragments == () and context.tool_input_lineage.input_sources == ()
    assert context.request_digest == digest(request) and context.query_digest == digest(f.rig.query)


def test_genuine_crop_input_uses_actual_retained_crop_not_original_asset_sha(native_capture_rig):
    f = native_capture_rig
    prior = f.prior.model_copy(deep=True)
    crop = b"fixture actual retained crop input"
    crop_ref = f.graph.put(crop)
    prior.run.regions[0].crop_ref = crop_ref
    prior.run.observations[0].input_sha256 = hashlib.sha256(crop).hexdigest()
    prior.run.observations[0].input_crop_ref = crop_ref
    inputs = asyncio.run(f.provider._native_inputs(f.rig.request, prior))
    context = native_input_context_v2(f.rig.request, f.rig.query, f.checkpoint.resolution, prior,
        f.mapping["evidence_sources"][f.rig.source.id], asset_generation=f.repository.locate(prior.asset.blob_ref).generation,
        native_inputs=inputs)
    assert context.tool_input_lineage.native_inputs[0].input_origin == "native_region_crop"
    assert context.tool_input_lineage.native_inputs[0].input_sha256 != prior.asset.sha256
    # A region that records no crop is proved by the crop its geometry cuts from
    # the asset's pixels (the SAM 3 tests below). This fixture's asset has no
    # pixels to cut it from and its declared crop is not one, so it stays refused.
    prior.run.regions[0].crop_ref = None
    with pytest.raises(PublicationUnavailable, match="native_crop_unproved"):
        asyncio.run(f.provider._native_inputs(f.rig.request, prior))


def quadrant_image():
    """40x30 with a distinct colour in each 20x15 quadrant, so no two crops of one size are alike."""
    image = Image.new("RGB", (40, 30), "white")
    draw = ImageDraw.Draw(image)
    for index, colour in enumerate(("red", "green", "blue", "orange")):
        left, top = (index % 2) * 20, (index // 2) * 15
        draw.rectangle((left, top, left + 19, top + 14), fill=colour)
    return image


def sam3_case(f, *, box=(5, 4, 20, 18), turns=0):
    """The graph as production records a SAM 3 region: no crop_ref, readings that declare their crop.

    sam3_effect.py refuses a SAM 3 region with a crop_ref, and every reader keeps
    the crop it saw (production.py transcribe, first_pass.py) under input_crop_ref.
    The asset is a decodable image, the readers' crop is cut with crop_bytes.
    """
    prior = f.prior.model_copy(deep=True)
    encoded = io.BytesIO()
    quadrant_image().save(encoded, format="JPEG", quality=95)
    image_bytes = encoded.getvalue()
    prior.asset.sha256, prior.asset.blob_ref = hashlib.sha256(image_bytes).hexdigest(), f.graph.put(image_bytes)
    prior.asset.size_bytes, prior.asset.width, prior.asset.height = len(image_bytes), 40, 30
    region = prior.run.regions[0]
    region.x, region.y, region.width, region.height = box
    region.rotation_quarter_turns = turns
    region.method, region.version, region.crop_ref = "sam3", "sam3-fixture", None
    reading = prior.run.observations[0]
    crop = crop_bytes(f.graph, prior, region)
    reading.input_crop_ref, reading.input_sha256 = f.graph.put(crop), hashlib.sha256(crop).hexdigest()
    return prior, crop


@pytest.mark.parametrize("turns", [0, 1, 3])
def test_sam3_region_without_crop_ref_is_proved_by_the_crop_its_geometry_cuts(native_capture_rig, turns):
    f = native_capture_rig
    prior, crop = sam3_case(f, turns=turns)
    region, reading = prior.run.regions[0], prior.run.observations[0]
    assert region.crop_ref is None and region.method == "sam3" and reading.input_crop_ref
    inputs = asyncio.run(f.provider._native_inputs(f.rig.request, prior))
    actual = inputs[0]
    assert actual.input_origin == "native_region_crop" and actual.input_ref == reading.input_crop_ref
    assert actual.input_sha256 == hashlib.sha256(crop).hexdigest() != prior.asset.sha256
    assert f.graph.get(actual.input_ref) == crop and len(f.rig.calls) == 1


@pytest.mark.parametrize("mutation", ["other_region_crop", "same_size_other_pixels", "region_moved_after_reading",
    "whole_asset_as_crop", "declared_digest_without_the_bytes", "asset_pixels_not_the_asset", "asset_pixels_missing",
    "pixel_read_budget"])
def test_sam3_region_crop_that_is_not_its_own_is_refused(native_capture_rig, monkeypatch, mutation):
    f = native_capture_rig
    prior, crop = sam3_case(f)
    region, reading = prior.run.regions[0], prior.run.observations[0]
    expected = "canonical_capture_native_crop_unproved"
    if mutation == "other_region_crop":
        # A reading of this region that read another region's crop, consistently recorded.
        other = prior.run.regions[0].model_copy(update={"x": 0, "y": 0, "width": 12, "height": 9})
        other_crop = crop_bytes(f.graph, prior, other)
        reading.input_crop_ref, reading.input_sha256 = f.graph.put(other_crop), hashlib.sha256(other_crop).hexdigest()
    elif mutation == "same_size_other_pixels":
        # The same width and height, cut from another quadrant: only the content differs.
        other = region.model_copy(update={"x": 20, "y": 15})
        other_crop = crop_bytes(f.graph, prior, other)
        assert other_crop != crop and (other.width, other.height) == (region.width, region.height)
        reading.input_crop_ref, reading.input_sha256 = f.graph.put(other_crop), hashlib.sha256(other_crop).hexdigest()
    elif mutation == "region_moved_after_reading":
        region.x += 10
    elif mutation == "whole_asset_as_crop":
        reading.input_crop_ref, reading.input_sha256 = prior.asset.blob_ref, prior.asset.sha256
    elif mutation == "declared_digest_without_the_bytes":
        # The recorded digest is the region's crop, the object it names holds other bytes.
        expected = "canonical_capture_native_input_checksum_changed"
        decoy = b"not the crop the digest names"
        reading.input_crop_ref = f.graph.put(decoy)
    elif mutation == "asset_pixels_not_the_asset":
        prior.asset.sha256 = hashlib.sha256(b"another asset").hexdigest()
    elif mutation == "asset_pixels_missing":
        prior.asset.blob_ref = hashlib.sha256(b"never stored").hexdigest()
        prior.asset.sha256 = prior.asset.blob_ref
    else:
        monkeypatch.setattr(capture_provider_module, "MAX_NATIVE_INPUT_BYTES", 16)
    before = copy.deepcopy(f.rig.store._read(f.rig.durable_scope).state)
    with pytest.raises(PublicationUnavailable, match=expected):
        asyncio.run(f.provider._native_inputs(f.rig.request, prior))
    assert f.rig.store._read(f.rig.durable_scope).state == before and len(f.rig.calls) == 1


def test_missing_original_body_or_request_envelope_has_no_refetch(native_capture_rig):
    f = native_capture_rig
    row = f.prepared.basis.receipts[0]
    f.rig.blobs._path(row.raw_capture.locator).unlink()
    with pytest.raises(PublicationUnavailable):
        asyncio.run(f.provider.read(f.principal, f.prepared, f.binding))
    assert len(f.rig.calls) == 1


class RetainedGenerationFixture:
    """Synthetic native object generations backed by actual immutable files.

    LocalBlobs deduplicates identical bytes, so this explicit fixture represents
    two retained object generations without claiming GCS/native qualification.
    It still reads actual bytes with a pre-allocation bound and checks their SHA.
    """
    def __init__(self, original, directory):
        self.original = original
        self.root = original.root
        self.directory = directory
        self.paths = {}

    def retain(self, ref, data):
        sha, generation = ref.split(":")
        assert sha == hashlib.sha256(data).hexdigest() and generation.isdecimal()
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / generation
        with path.open("xb") as stream:
            stream.write(data)
        self.paths[ref] = path

    def get_bounded(self, ref, max_bytes):
        if ":" not in ref:
            return self.original.get_bounded(ref, max_bytes)
        if ref not in self.paths:
            raise LookupError("Synthetic retained generation unavailable")
        with self.paths[ref].open("rb") as stream:
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes or hashlib.sha256(data).hexdigest() != ref.split(":")[0]:
            raise ValueError("Synthetic retained generation failed integrity")
        return data


def equal_sha_crop_case(f, tmp_path, *, retain=True):
    prior = f.prior.model_copy(deep=True)
    crop_ref = prior.asset.blob_ref + ":42"
    graph = RetainedGenerationFixture(f.graph, tmp_path / "native-generations")
    if retain:
        graph.retain(crop_ref, f.graph.get(prior.asset.blob_ref))
    repository = SqlConnectRepository(session=object(), graph_blobs=graph)
    provider = CanonicalEvidenceProviderV2.from_service(repository, f.rig.effects, f.rig.registry)
    prior.run.regions[0].crop_ref = crop_ref
    prior.run.observations[0].input_crop_ref = crop_ref
    return prior, crop_ref, graph, repository, provider


def test_equal_sha_distinct_native_crop_ref_and_generation_are_not_rebound_to_original(native_capture_rig, tmp_path):
    f = native_capture_rig
    prior, crop_ref, graph, repository, provider = equal_sha_crop_case(f, tmp_path)
    before = copy.deepcopy(f.rig.store._read(f.rig.durable_scope).state)
    inputs = asyncio.run(provider._native_inputs(f.rig.request, prior))
    actual = inputs[0]
    assert actual.input_sha256 == prior.asset.sha256
    assert actual.input_ref == crop_ref != prior.asset.blob_ref
    assert actual.input_generation == "42" != repository.locate(prior.asset.blob_ref).generation
    assert actual.input_origin == "native_region_crop"
    assert graph.get_bounded(crop_ref, prior.asset.size_bytes) == f.graph.get(prior.asset.blob_ref)
    context = native_input_context_v2(f.rig.request, f.rig.query, f.checkpoint.resolution, prior,
        f.mapping["evidence_sources"][f.rig.source.id],
        asset_generation=repository.locate(prior.asset.blob_ref).generation, native_inputs=inputs)
    assert context.tool_input_lineage.native_inputs == inputs
    assert f.rig.store._read(f.rig.durable_scope).state == before and len(f.rig.calls) == 1


@pytest.mark.parametrize("mutation", ["contradictory_crop_ref", "missing_region_crop", "foreign_region_asset",
    "foreign_declared_asset", "missing_retained_generation"])
def test_equal_sha_explicit_crop_requires_exact_native_region_declaration_and_retained_generation(native_capture_rig, tmp_path, mutation):
    f = native_capture_rig
    prior, crop_ref, graph, repository, provider = equal_sha_crop_case(f, tmp_path,
        retain=mutation != "missing_retained_generation")
    if mutation == "contradictory_crop_ref":
        prior.run.observations[0].input_crop_ref = prior.asset.blob_ref + ":43"
    elif mutation == "missing_region_crop":
        prior.run.regions[0].crop_ref = None
    elif mutation == "foreign_region_asset":
        prior.run.regions[0].asset_id = ident("foreign native region asset")
    elif mutation == "foreign_declared_asset":
        prior.run.observations[0].input_asset_id = ident("foreign declared input asset")
    before = copy.deepcopy(f.rig.store._read(f.rig.durable_scope).state)
    assert prior.run.observations[0].input_sha256 == prior.asset.sha256
    with pytest.raises(PublicationUnavailable, match="canonical_capture_native_(crop|asset|input)_"):
        asyncio.run(provider._native_inputs(f.rig.request, prior))
    assert f.rig.store._read(f.rig.durable_scope).state == before and len(f.rig.calls) == 1


@pytest.mark.parametrize("mutation", ["missing_original_asset_declaration", "ambiguous_registered_crop",
    "undeclared_different_input"])
def test_missing_native_input_origin_cannot_be_inferred_from_checksum(native_capture_rig, mutation):
    f = native_capture_rig
    prior = f.prior.model_copy(deep=True)
    if mutation == "missing_original_asset_declaration":
        prior.run.observations[0].input_asset_id = None
    elif mutation == "ambiguous_registered_crop":
        prior.run.regions[0].crop_ref = prior.asset.blob_ref + ":42"
    else:
        prior.run.observations[0].input_sha256 = hashlib.sha256(b"unproved distinct native input").hexdigest()
    before = copy.deepcopy(f.rig.store._read(f.rig.durable_scope).state)
    with pytest.raises(PublicationUnavailable, match="canonical_capture_native_input_origin_unproved"):
        asyncio.run(f.provider._native_inputs(f.rig.request, prior))
    assert f.rig.store._read(f.rig.durable_scope).state == before and len(f.rig.calls) == 1


# V3 retained-source bound regressions; no connector, network or SDK invocation.
from specimen_digitization.research_harness import canonical_evidence_provider_v2 as capture_provider_module
from specimen_digitization.research_harness.canonical_evidence_provider_v2 import BoundedImmutableCaptureReaderV3
from specimen_digitization.research_harness.persistence import BlobRef, GcsImmutableBlobs, ImmutableFileBlobs
from specimen_digitization.research_harness.publication import NativeCapture


def local_retained_reference(tmp_path, data=b"retained"):
    store = ImmutableFileBlobs(tmp_path / "bounded-retained")
    reference = store.put_at("research-capture/original-response", data)
    return store, reference, store._path(reference.locator)


def test_v3_local_actual_bounded_read_never_calls_unbounded_get(tmp_path, monkeypatch):
    store, reference, path = local_retained_reference(tmp_path)
    def forbidden_get(*args, **kwargs):
        raise AssertionError("unbounded retained get must never execute")
    monkeypatch.setattr(store, "get", forbidden_get)
    reads, original_read = [], capture_provider_module.os.read
    def recorded_read(fd, count):
        reads.append(count)
        return original_read(fd, count)
    monkeypatch.setattr(capture_provider_module.os, "read", recorded_read)
    reader = BoundedImmutableCaptureReaderV3.from_store(store)
    assert reader.get_bounded(reference, max_bytes=32) == b"retained"
    assert reads == [reference.byte_size + 1]
    assert reads[0] <= 33 and path.stat().st_size == reference.byte_size


def test_v3_oversized_imported_file_denied_before_any_data_read(tmp_path, monkeypatch):
    store, reference, path = local_retained_reference(tmp_path, b"good")
    path.write_bytes(b"corrupt imported retained object" * 4096)
    calls = []
    def forbidden_read(*args, **kwargs):
        calls.append(args)
        raise AssertionError("oversized metadata must deny before data allocation")
    monkeypatch.setattr(capture_provider_module.os, "read", forbidden_read)
    monkeypatch.setattr(store, "get", forbidden_read)
    with pytest.raises(ValueError, match="size changed"):
        BoundedImmutableCaptureReaderV3.from_store(store).get_bounded(reference, max_bytes=16)
    assert calls == [] and reference.byte_size == 4 and path.stat().st_size > 16


def test_v3_same_generation_same_size_corruption_denied(tmp_path, monkeypatch):
    store, reference, path = local_retained_reference(tmp_path, b"good")
    path.write_bytes(b"evil")
    monkeypatch.setattr(store, "get", lambda *args: pytest.fail("unbounded get"))
    with pytest.raises(ValueError, match="checksum changed"):
        BoundedImmutableCaptureReaderV3.from_store(store).get_bounded(reference, max_bytes=16)
    assert reference.generation == "1" and path.stat().st_size == reference.byte_size


def test_v3_file_growth_after_fstat_stays_read_bounded_and_denies(tmp_path, monkeypatch):
    store, reference, path = local_retained_reference(tmp_path, b"good")
    reads, original_read = [], capture_provider_module.os.read
    def grow_before_read(fd, count):
        reads.append(count)
        with path.open("ab") as stream:
            stream.write(b"untrusted growth" * 1024)
        return original_read(fd, count)
    monkeypatch.setattr(capture_provider_module.os, "read", grow_before_read)
    with pytest.raises(ValueError, match="changed during bounded read"):
        BoundedImmutableCaptureReaderV3.from_store(store).get_bounded(reference, max_bytes=16)
    assert reads == [5] and path.stat().st_size > 16


def test_v3_unsupported_source_store_holds_before_get(native_capture_rig):
    f, calls = native_capture_rig, []
    def forbidden_get(reference):
        calls.append(reference)
        raise AssertionError("unsupported reader must never execute")
    unsupported = SimpleNamespace(get=forbidden_get)
    with pytest.raises(PublicationUnavailable, match="bounded_reader_unavailable"):
        CanonicalEvidenceProviderV2(unsupported, f.graph, f.rig.registry, f.repository.locate)
    assert calls == []


def test_v3_unknown_local_generation_denied_before_open(tmp_path, monkeypatch):
    store, reference, path = local_retained_reference(tmp_path)
    calls = []
    def forbidden_open(*args, **kwargs):
        calls.append(args)
        raise AssertionError("unknown generation must deny before open")
    monkeypatch.setattr(capture_provider_module.os, "open", forbidden_open)
    bad = BlobRef(reference.locator, "2", reference.sha256, reference.byte_size)
    with pytest.raises(ValueError, match="generation is unavailable"):
        BoundedImmutableCaptureReaderV3.from_store(store).get_bounded(bad, max_bytes=32)
    assert calls == []


def test_v3_retained_file_symlink_denied_without_follow(tmp_path, monkeypatch):
    store, reference, path = local_retained_reference(tmp_path)
    target = tmp_path / "outside-retained-object"
    target.write_bytes(b"retained")
    path.unlink()
    path.symlink_to(target)
    calls = []
    def forbidden_read(*args, **kwargs):
        calls.append(args)
        raise AssertionError("symlink must deny before read")
    monkeypatch.setattr(capture_provider_module.os, "read", forbidden_read)
    with pytest.raises(OSError):
        BoundedImmutableCaptureReaderV3.from_store(store).get_bounded(reference, max_bytes=32)
    assert calls == [] and target.stat().st_size == reference.byte_size


@pytest.mark.parametrize("limit", [True, -1, 1.0])
def test_v3_reader_rejects_noninteger_or_negative_limit(tmp_path, limit):
    store, reference, path = local_retained_reference(tmp_path)
    with pytest.raises(ValueError, match="Invalid bounded immutable reference"):
        BoundedImmutableCaptureReaderV3.from_store(store).get_bounded(reference, max_bytes=limit)
    assert path.stat().st_size == reference.byte_size


class RetainedGcsBlobFixtureV3:
    """Only a bounded-reader call contract fixture; no google client/server."""
    def __init__(self, body=b"good", *, chunks=None):
        self.generation, self.size = 8, len(body)
        self.metadata = {"sha256": hashlib.sha256(body).hexdigest()}
        self.chunks = [body] if chunks is None else chunks
        self.chunk_size = 262144
        self.reloads, self.downloads, self.accepted_writes = [], [], []

    def reload(self, **kwargs):
        self.reloads.append(kwargs)

    def download_to_file(self, sink, **kwargs):
        self.downloads.append(kwargs)
        assert self.chunk_size is None
        for chunk in self.chunks:
            sink.write(chunk)
            self.accepted_writes.append(sink.bytes_written)


class RetainedGcsBucketFixtureV3:
    def __init__(self, blob):
        self.selected, self.calls = blob, []

    def blob(self, locator, *, generation):
        self.calls.append((locator, generation))
        return self.selected


def retained_gcs_reference_v3(body=b"good", *, chunks=None):
    blob = RetainedGcsBlobFixtureV3(body, chunks=chunks)
    bucket = RetainedGcsBucketFixtureV3(blob)
    store = GcsImmutableBlobs(bucket, maximum_bytes=32)
    reference = BlobRef("research-capture/retained-response", "8", hashlib.sha256(body).hexdigest(), len(body))
    return BoundedImmutableCaptureReaderV3.from_store(store), reference, blob, bucket


def test_v3_gcs_generation_metadata_range_and_raw_stream_call_contract():
    reader, reference, blob, bucket = retained_gcs_reference_v3()
    assert reader.get_bounded(reference, max_bytes=16) == b"good"
    assert bucket.calls == [(reference.locator, 8)]
    assert blob.reloads == [{"if_generation_match": 8, "timeout": 30, "retry": None}]
    assert blob.downloads == [{"start": 0, "end": 4, "raw_download": True,
        "if_generation_match": 8, "checksum": "crc32c", "timeout": 30, "retry": None,
        "single_shot_download": False}]
    assert blob.accepted_writes == [4]


@pytest.mark.parametrize("changed", ["oversized", "wrong_generation", "wrong_sha", "bool_size", "float_size"])
def test_v3_gcs_fresh_metadata_denies_before_download(changed):
    reader, reference, blob, bucket = retained_gcs_reference_v3()
    if changed == "oversized":
        blob.size = 4096
    elif changed == "wrong_generation":
        blob.generation = 9
    elif changed == "wrong_sha":
        blob.metadata["sha256"] = digest("contradictory original metadata")
    elif changed == "bool_size":
        blob.size = True
    else:
        blob.size = 4.0
    with pytest.raises(ValueError, match="Bounded retained GCS read unavailable"):
        reader.get_bounded(reference, max_bytes=16)
    assert len(blob.reloads) == 1 and blob.downloads == [] and blob.accepted_writes == []


def test_v3_gcs_ignored_range_overflow_stops_before_copying_excess_bytes():
    reader, reference, blob, bucket = retained_gcs_reference_v3(chunks=[b"goo", b"excess response bytes"])
    with pytest.raises(ValueError, match="Bounded retained GCS read unavailable"):
        reader.get_bounded(reference, max_bytes=16)
    assert blob.accepted_writes == [3] and len(blob.downloads) == 1
    assert max(blob.accepted_writes) <= reference.byte_size


def test_v3_gcs_corrupt_same_size_response_denied_after_bounded_stream():
    reader, reference, blob, bucket = retained_gcs_reference_v3(chunks=[b"evil"])
    with pytest.raises(ValueError, match="Bounded retained GCS read unavailable"):
        reader.get_bounded(reference, max_bytes=16)
    assert blob.accepted_writes == [4] and len(blob.downloads) == 1


def test_v3_gcs_empty_generation_uses_fresh_metadata_without_download():
    reader, reference, blob, bucket = retained_gcs_reference_v3(b"")
    assert reader.get_bounded(reference, max_bytes=16) == b""
    assert len(blob.reloads) == 1 and blob.downloads == [] and blob.accepted_writes == []


def test_v3_provider_retained_import_hold_never_calls_unbounded_source_get(native_capture_rig, monkeypatch):
    f = native_capture_rig
    before = copy.deepcopy(f.rig.store._read(f.rig.durable_scope).state)
    capture = NativeCapture.model_validate(f.effect["receipt"]["capture"])
    path = f.rig.blobs._path(capture.locator)
    with path.open("ab") as stream:
        stream.write(b"oversized imported corruption" * 1024)
    calls = []
    def forbidden_get(*args):
        calls.append(args)
        raise AssertionError("provider must not use unbounded get")
    monkeypatch.setattr(f.rig.blobs, "get", forbidden_get)
    with pytest.raises(PublicationUnavailable, match="immutable_read_unavailable"):
        asyncio.run(f.provider._bytes(capture, capture.byte_size))
    assert calls == [] and f.rig.store._read(f.rig.durable_scope).state == before
    assert f.provider.source_blobs is f.rig.blobs
    assert isinstance(f.provider.source_reader, BoundedImmutableCaptureReaderV3)
