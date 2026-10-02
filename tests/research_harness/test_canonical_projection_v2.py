"""SOURCE UNRUN: real deterministic G44/G41 producers with synthetic native rows.

These cases exercise a pure projection, not Firebase transactions, GCS authority,
I4B capture qualification, paid calls, D2 ancestry or the V2 policy producer.
The admitted complete candidate must supply the pinned ordinary dependencies.
"""
import copy
import hashlib
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest

from test_native_canonical_contract import basis, basis as native_basis, genuine_derivation, ident
from test_canonical_materialization import materialization
from specimen_digitization.application.domain import Evidence, FieldValue, Observation, Transcript, ValueState
from specimen_digitization.application.active_graph import pack, unpack
from specimen_digitization.application.projection import writes, _record, _first_pass, _reading, _region_row, _blob_asset, Blob
from specimen_digitization.application.storage import LocalBlobs, digest as canonical_digest
from specimen_digitization.research_harness.canonical_projection_v2 import (
    CanonicalLineageContextV2, ConsumedCanonicalSourceV2, NativePriorSnapshotProofV2, project_canonical_value_v2,
    project_tool_input_lineage_v2,
    NativeRawSourceAssetProofV2, NativeTranscriptionDecisionProofV2,
)
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.contracts import (
    EventHypothesis, EventKind, EvidenceItem, FieldCheckpoint, FieldKey, FieldResolution, FragmentRelation,
    RelationKind, SourceFragment, SpecialistRequest, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.evidence import EvidenceError, assemble_field, validate_resolution
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.native_canonical import CanonicalIdentityV1, canonical_value_v1
from specimen_digitization.research_harness.persistence import StaleWork
from specimen_digitization.research_harness.publication import NativeDependencyBasis


def native_snapshot_proof(prior, record_id, blobs=None):
    """Actual ordinary pack/unpack fixture; native identity is explicitly synthetic."""
    payload = pack(prior, blobs)
    assert unpack(copy.deepcopy(payload), blobs).model_dump(mode="json") == prior.model_dump(mode="json")
    canonical = CanonicalIdentityV1(record_revision=prior.version, record_version_id=record_id,
        canonical_run_id=prior.run.id, host_record_version_id=prior.run.id + ":synthetic-native",
        snapshot_sha256=canonical_digest(payload))
    raw = blobs.get_bounded(payload["active_graph"]["blob_ref"], 16 * 1024 * 1024) if payload["active_graph"] else None
    return NativePriorSnapshotProofV2(canonical=canonical, snapshot=payload, active_graph_bytes=raw)


def retain_checkpoint(job, cp):
    scope = {key: getattr(cp.scope, key) for key in ("organization_id", "collection_id", "specimen_id", "job_id", "generation")}
    row = {"scope": scope, "field_key": str(cp.field_key), "revision": cp.revision,
        "payload": cp.model_dump(mode="json"), "retry_command_id": cp.retry_command_id,
        "receipt_ids": list(cp.effect_receipt_ids), "dependencies": {str(pin.field_key): pin.revision for pin in cp.resolution.dependencies},
        "dependency_digests": {str(pin.field_key): pin.digest for pin in cp.resolution.dependencies}}
    row["id"] = digest({"scope": scope, "field": str(cp.field_key), "revision": cp.revision, "payload": row["payload"]})
    job["fields"][str(cp.field_key)].update(locked=False, revision=cp.revision, checkpoint=row)
    job["checkpoints"].append(row)
    return row


def projection_case(b, kind):
    request, source, derived = genuine_derivation(b, kind)
    mapping = dict(b.binding.registration.field_mapping)
    ids = {key: UUID(ident("projection-evidence:" + key)) for key in set(source.evidence_ids) | set(derived.evidence_ids)}
    def value(resolution):
        keys = set(resolution.evidence_ids) | set(resolution.value.evidence_ids)
        return canonical_value_v1(resolution, mapping, {key: ids[key] for key in keys})
    prior = b.prior.model_copy(deep=True)
    prior.version = 4  # Actual supplied synthetic CAS, never inferred from a jobbase offset.
    prior.run.fields[mapping[str(source.field_key)]] = value(source)
    prior.run.evidence = [Evidence(id=str(native), kind="scientific", source="synthetic label science",
        locator="fixture://label", excerpt="Synthetic source provenance") for native in ids.values()]
    prior.run.observations = [Observation(id=fragment.observation_id, region_id=fragment.region_id,
        route_id="fixture-independent", model_id="fixture", provider="synthetic", prompt_version="fixture-v1",
        input_sha256=fragment.asset_digest, literal_text=fragment.observation_text,
        raw_ref="fixture://immutable-reading", raw_sha256=digest("synthetic raw reading")) for fragment in request.fragments]
    old_projection = writes(prior, b.connector.locate, b.connector._sized, b.principal.user_id)
    record = next(row.variables for row in old_projection if row.operation == "AppendRecordVersionV2")
    old_rows = copy.deepcopy(tuple(row.variables for row in old_projection if row.operation == "AppendResolvedFieldV2"))
    # Explicit synthetic publication A proof, not an executed native publication.
    source_id = UUID(ident("actual-fixture-source-candidate:" + kind))
    candidates = {row["fieldKey"]: row.get("candidateId") for row in old_rows}
    candidates[mapping[str(source.field_key)]] = str(source_id)
    # Recompute record UUID with this genuine supplied candidate map; never
    # mutate a field reference after hashing the whole-record content.
    published = _record(prior.run, candidates, {item.id for item in prior.run.evidence})
    record = next(row.variables for row in published if row.operation == "AppendRecordVersionV2")
    old_rows = copy.deepcopy(tuple(row.variables for row in published if row.operation == "AppendResolvedFieldV2"))
    job = copy.deepcopy(b.binding.registration.job)
    source_cp = FieldCheckpoint(scope=b.scope, field_key=source.field_key, revision=7, resolution=source,
        prompt_digest=request.prompt.digest, model_settings_digest=digest("settings"), source_registry_digest=request.prompt.source_registry_digest)
    cp = FieldCheckpoint(scope=b.scope, field_key=derived.field_key, revision=8, resolution=derived,
        prompt_digest=request.prompt.digest, model_settings_digest=digest("settings"), source_registry_digest=request.prompt.source_registry_digest)
    native = retain_checkpoint(job, source_cp)
    retain_checkpoint(job, cp)
    source_value = value(source)
    scoped = {"organizationId": b.scope.organization_id, "collectionId": b.scope.collection_id}
    source_record = {**scoped, **record}
    source_candidate = {**scoped, "id": str(source_id), "runId": prior.run.id,
        "fieldKey": mapping[str(source.field_key)], "state": str(source_value.state),
        "parsedValue": source_value.parsed, "normalizedValue": source_value.normalized, "authorityId": source_value.authority_id}
    proof = ConsumedCanonicalSourceV2(checkpoint=source_cp,
        native_basis=NativeDependencyBasis(field_key=source.field_key, revision=7, resolution_digest=digest(source),
            checkpoint_id=native["id"], checkpoint_digest=digest(native)),
        canonical_run_id=UUID(prior.run.id), canonical_candidate_id=source_id, canonical_record_version_id=UUID(record["id"]),
        canonical_field_key=mapping[str(source.field_key)], candidate_contract="canonical-value-lineage/v2",
        candidate=source_candidate, record=source_record,
        resolved_field={**scoped, **next(row for row in old_rows if row["fieldKey"] == mapping[str(source.field_key)])},
        record_projection=tuple({**scoped, **row} for row in old_rows),
        record_projection_digest=digest(tuple({**scoped, **row} for row in old_rows)),
        candidate_digest=digest(source_candidate), record_digest=digest(source_record),
        source_publication_lineage_digest=digest("synthetic native A proof; no transaction authority"))
    result = prior.model_copy(deep=True)
    result.version += 1
    result.run.fields[mapping[str(derived.field_key)]] = value(derived)
    context = CanonicalLineageContextV2(scope=b.scope, actor_uid=b.principal.user_id,
        prior_record_version_id=UUID(record["id"]), prior_revision=prior.version,
        prior_snapshot_sha256=canonical_digest(prior.model_dump(mode="json")),
        native_prior_snapshot=native_snapshot_proof(prior, UUID(record["id"])), job=job, field_mapping=mapping,
        evidence_id_mapping=ids, human_locks={key: False for key in prior.run.fields}, prior_projection=old_rows,
        original_request=request, tool_results=(), consumed_sources=(proof,))
    return SimpleNamespace(principal=b.principal, prior=prior, result=result, checkpoint=cp, context=context, source=source)


def project(b):
    return project_canonical_value_v2(b.principal, prior=b.prior, result=b.result, checkpoint=b.checkpoint, context=b.context)


@pytest.mark.parametrize("kind", ["G44", "G41-ft", "G41-m"])
def test_actual_science_producers_project_complete_original_derivation_and_distinct_native_source_lineage(basis, kind):
    b = projection_case(basis, kind)
    before = (b.prior.model_dump(mode="json"), copy.deepcopy(b.context.job), b.checkpoint.model_dump(mode="json"))
    output = project(b)
    candidate = next(row.variables for row in output.target_writes if row.operation == "AppendFieldCandidateLineageV2")
    lineage = next(row.variables for row in output.target_writes if row.operation == "AppendCanonicalValueLineageV2")
    dependency = next(row.variables for row in output.target_writes if row.operation == "AppendCanonicalValueDependencyV2")
    scientific = b.checkpoint.resolution.derivation
    assert candidate["literalValue"] is None and candidate["derivation"] == "derived"
    assert candidate["parsedValue"] == b.checkpoint.resolution.value.parsed
    assert candidate["normalizedValue"] == b.checkpoint.resolution.value.normalized
    assert lineage["derivation"] == scientific.model_dump(mode="json")
    assert lineage["derivationDigest"] == digest(scientific)
    assert lineage["scientificSourceDigest"] == scientific.source_digest != dependency["dependencyResolutionDigest"]
    assert dependency["dependencyResolutionDigest"] == digest(b.source)
    assert dependency["sourceCandidateId"] == str(b.context.consumed_sources[0].canonical_candidate_id)
    assert lineage["selectedObservationId"] is None and lineage["selectedTranscriptionId"] is None
    associations = [row.variables for row in output.target_writes if row.operation == "AppendCanonicalValueEvidenceV2"]
    assert associations and all(row["associationKind"] == "original_derivation_record" and row["originalRelation"] is None for row in associations)
    assert not any(row.operation == "AppendCandidateEvidenceLineageV2" for row in output.target_writes)
    fields = [row.variables for row in output.record_writes if row.operation == "AppendResolvedFieldV2"]
    assert len(fields) == 20 and len({row["fieldKey"] for row in fields}) == 20
    assert all({key: row[key] for key in ("candidateId", "state", "fieldGroup")} ==
        {key: old[key] for key in ("candidateId", "state", "fieldGroup")}
        for row in fields for old in b.context.prior_projection if row["fieldKey"] == old["fieldKey"] and row["fieldKey"] != output.field_key)
    record = next(row.variables for row in output.record_writes if row.operation == "AppendRecordVersionV2")
    assert record["predecessorId"] == str(b.context.prior_record_version_id)
    assert output.prior_revision == 4 and output.result_revision == 5
    assert project(b) == output
    assert before == (b.prior.model_dump(mode="json"), b.context.job, b.checkpoint.model_dump(mode="json"))
    assert basis.connector.write_calls == basis.connector.intent_write_calls == 0
    if kind == "G44": assert lineage["precision"] == b.checkpoint.resolution.value.precision


@pytest.mark.parametrize("kind", ["G44", "G41-ft", "G41-m"])
@pytest.mark.parametrize("mutation", ["scientific_sha", "science_context", "missing_request", "source_revision", "resolution_sha",
    "source_candidate", "source_record", "source_record_membership", "missing_source", "native_scope_bool", "other19", "human_lock", "cas", "field_group"])
def test_missing_or_tampered_science_native_dependency_and_current_basis_never_projects(basis, kind, mutation):
    b = projection_case(basis, kind)
    before = b.prior.model_dump(mode="json")
    proof = b.context.consumed_sources[0]
    if mutation == "scientific_sha":
        bad = b.checkpoint.resolution.derivation.model_copy(update={"source_digest": digest("wrong science")})
        b.checkpoint = b.checkpoint.model_copy(update={"resolution": b.checkpoint.resolution.model_copy(update={"derivation": bad})})
    elif mutation == "science_context":
        event = b.context.original_request.events[0].model_copy(update={"id": "different event"})
        b.context = replace(b.context, original_request=b.context.original_request.model_copy(update={"events": (event,)}))
    elif mutation == "missing_request": b.context = replace(b.context, original_request=b.context.original_request.model_copy(update={"assemblies": ()}))
    elif mutation == "source_revision":
        b.context = replace(b.context, consumed_sources=(proof.model_copy(update={"native_basis": proof.native_basis.model_copy(update={"revision": 9})}),))
    elif mutation == "resolution_sha":
        b.context = replace(b.context, consumed_sources=(proof.model_copy(update={"native_basis": proof.native_basis.model_copy(update={"resolution_digest": digest("wrong resolution")})}),))
    elif mutation == "source_candidate":
        b.context = replace(b.context, consumed_sources=(proof.model_copy(update={"canonical_candidate_id": UUID(ident("foreign candidate"))}),))
    elif mutation == "source_record":
        b.context = replace(b.context, consumed_sources=(proof.model_copy(update={"canonical_record_version_id": UUID(ident("foreign record"))}),))
    elif mutation == "source_record_membership":
        rows = copy.deepcopy(proof.record_projection)
        next(row for row in rows if row["fieldKey"] == proof.canonical_field_key)["candidateId"] = ident("unrelated candidate")
        changed = proof.model_copy(update={"record_projection": rows, "record_projection_digest": digest(rows)})
        b.context = replace(b.context, consumed_sources=(changed,))
    elif mutation == "missing_source": b.context = replace(b.context, consumed_sources=())
    elif mutation == "native_scope_bool": b.context.job["fields"][str(b.checkpoint.field_key)]["checkpoint"]["scope"]["generation"] = True
    elif mutation == "other19": b.result.run.fields["country"].parsed = "foreign change"
    elif mutation == "human_lock": b.context.human_locks[str(b.checkpoint.field_key)] = True
    elif mutation == "cas": b.context = replace(b.context, prior_revision=True)
    elif mutation == "field_group": next(row for row in b.context.prior_projection if row["fieldKey"] == "country")["fieldGroup"] = "optional"
    with pytest.raises((PublicationUnavailable, EvidenceError, StaleWork)):
        project(b)
    assert b.prior.model_dump(mode="json") == before
    assert basis.connector.write_calls == basis.connector.intent_write_calls == 0


def settled_case(materialization):
    b = materialization
    prior = b.prior.model_copy(deep=True)
    original_cp = b.prepared.publication.checkpoints[0]
    request = b.source.context.request
    fragments = tuple(SourceFragment(id="country:" + observation.id, scope=request.scope,
        asset_id=prior.asset.id, asset_generation="1", asset_digest=observation.input_sha256,
        label_id=prior.run.regions[0].id, region_id=observation.region_id, observation_id=observation.id,
        reader=observation.route_id, model_id=observation.model_id, prompt_digest=digest("fixture prompt"),
        observation_text=observation.literal_text, observation_digest=hashlib.sha256(observation.literal_text.encode()).hexdigest(),
        start=0, end=4, literal="Peru", order=index, input_source="raw_reading") for index, observation in enumerate(prior.run.observations))
    request = request.model_copy(update={"fragments": fragments})
    evidence = original_cp.resolution.evidence_ids[0]
    value = original_cp.resolution.value.model_copy(update={"literal": None, "parsed": "Peru", "normalized": "Peru",
        "input_source": "raw_reading", "source_region_id": prior.run.regions[0].id,
        "source_observation_id": None, "verbatim_by_observation": {item.id: "Peru" for item in prior.run.observations},
        "input_source_by_observation": {item.id: "raw_reading" for item in prior.run.observations},
        "settled_observation_ids": [item.id for item in prior.run.observations], "evidence_relations": {evidence: "decides"}})
    cp = original_cp.model_copy(update={"resolution": original_cp.resolution.model_copy(update={"value": value, "value_layer": "settled"})})
    job = copy.deepcopy(b.binding.registration.job)
    retain_checkpoint(job, cp)
    ids = {b.evidence[0].evidence.id: UUID(b.evidence[0].canonical_evidence.id)}
    result = prior.model_copy(deep=True);result.version += 1
    result.run.fields["country"] = canonical_value_v1(cp.resolution, b.binding.registration.field_mapping, ids)
    context = CanonicalLineageContextV2(scope=cp.scope, actor_uid=b.principal.user_id,
        prior_record_version_id=b.binding.canonical.record_version_id, prior_revision=prior.version,
        prior_snapshot_sha256=canonical_digest(prior.model_dump(mode="json")),
        native_prior_snapshot=native_snapshot_proof(prior, b.binding.canonical.record_version_id), job=job,
        field_mapping=b.binding.registration.field_mapping, evidence_id_mapping=ids,
        human_locks=b.binding.registration.human_locks, prior_projection=b.rows,
        original_request=request, tool_results=b.source.context.tool_results)
    return SimpleNamespace(principal=b.principal, prior=prior, result=result, checkpoint=cp, context=context)


def test_literal_less_settled_lookup_retains_both_raw_readers_without_a_selected_transcript(materialization):
    b = settled_case(materialization)
    prior, result, cp, context = b.prior, b.result, b.checkpoint, b.context
    output = project(b)
    candidate = next(row.variables for row in output.target_writes if row.operation == "AppendFieldCandidateLineageV2")
    lineage = next(row.variables for row in output.target_writes if row.operation == "AppendCanonicalValueLineageV2")
    assert candidate["literalValue"] is None and candidate["normalizedValue"] == "Peru"
    assert lineage["literalGrounding"] == {"kind": "absent", "literal": None}
    assert candidate["sourceObservationId"] is None and candidate["sourceTranscriptionId"] is None
    assert {row["observationId"] for row in lineage["readingSources"]} == {item.id for item in prior.run.observations}
    assert all(row["inputSource"] == "raw_reading" for row in lineage["readingSources"])
    assert any(row.operation == "AppendCandidateEvidenceLineageV2" and row.variables["relation"] == "decides" for row in output.target_writes)
    assert len([row for row in output.record_writes if row.operation == "AppendResolvedFieldV2"]) == 20
    broken = result.model_copy(deep=True);broken.run.fields["country"].evidence_relations = {}
    with pytest.raises(PublicationUnavailable):
        project_canonical_value_v2(b.principal, prior=prior, result=broken, checkpoint=cp, context=context)


@pytest.mark.parametrize("mutation", ["invented_literal", "unrelated_selected_reading"])
def test_correct_lookup_science_cannot_hide_false_reading_annotation_or_unrelated_selection(materialization, mutation):
    b = settled_case(materialization)
    value = b.checkpoint.resolution.value.model_copy(deep=True)
    if mutation == "invented_literal":
        value.verbatim_by_observation[next(iter(value.verbatim_by_observation))] = "Invented reader annotation"
    else:
        other = b.prior.run.observations[0].model_copy(update={"id": ident("unrelated native reading")})
        b.prior.run.observations.append(other)
        b.result.run.observations.append(other.model_copy(deep=True))
        value.source_observation_id = other.id
        b.context = replace(b.context, prior_snapshot_sha256=canonical_digest(b.prior.model_dump(mode="json")),
            native_prior_snapshot=native_snapshot_proof(b.prior, b.context.prior_record_version_id))
    b.checkpoint = b.checkpoint.model_copy(update={"resolution": b.checkpoint.resolution.model_copy(update={"value": value})})
    # Exact typed/native metadata agrees, and the actual lookup remains Peru;
    # only the guarded claimed reading annotation/selection is false.
    b.context.job["checkpoints"] = []
    retain_checkpoint(b.context.job, b.checkpoint)
    b.result.run.fields["country"] = canonical_value_v1(b.checkpoint.resolution,
        b.context.field_mapping, b.context.evidence_id_mapping)
    assert b.result.run.fields["country"].normalized == "Peru"
    before = b.prior.model_dump(mode="json")
    with pytest.raises(PublicationUnavailable, match="canonical_lineage_(reading|selected_reading)_unproved"):
        project(b)
    assert b.prior.model_dump(mode="json") == before



def replace_target_value(b, value):
    """Update retained typed/native metadata, so science/lineage guards are real."""
    b.checkpoint = b.checkpoint.model_copy(update={"resolution": b.checkpoint.resolution.model_copy(update={"value": value})})
    b.context.job["checkpoints"] = []
    retain_checkpoint(b.context.job, b.checkpoint)
    field = b.context.field_mapping[str(b.checkpoint.field_key)]
    b.result.run.fields[field] = canonical_value_v1(b.checkpoint.resolution,
        b.context.field_mapping, b.context.evidence_id_mapping)


@pytest.mark.parametrize("literal", ["Invented candidate literal", ""])
def test_correct_lookup_science_rejects_ungrounded_candidate_literal(materialization, literal):
    b = settled_case(materialization)
    replace_target_value(b, b.checkpoint.resolution.value.model_copy(update={"literal": literal}))
    assert b.result.run.fields["country"].normalized == "Peru"
    assert validate_resolution(b.context.original_request, b.checkpoint.resolution, b.context.tool_results) == b.checkpoint.resolution
    before = b.prior.model_dump(mode="json")
    with pytest.raises(PublicationUnavailable, match="^canonical_lineage_literal_unproved$"):
        project(b)
    assert b.prior.model_dump(mode="json") == before


def test_genuine_raw_literal_retains_all_proven_readers_without_selecting_one(materialization):
    b = settled_case(materialization)
    replace_target_value(b, b.checkpoint.resolution.value.model_copy(update={"literal": "Peru"}))
    output = project(b)
    lineage = next(row.variables for row in output.target_writes if row.operation == "AppendCanonicalValueLineageV2")
    candidate = next(row.variables for row in output.target_writes if row.operation == "AppendFieldCandidateLineageV2")
    proof = lineage["literalGrounding"]
    assert candidate["literalValue"] == proof["literal"] == "Peru"
    assert candidate["sourceObservationId"] is None and candidate["sourceTranscriptionId"] is None
    assert proof["kind"] == "original_fragment"
    assert {row["observation_id"] for row in proof["fragments"]} == {item.id for item in b.prior.run.observations}
    assert proof["fragments"] == [item.model_dump(mode="json") for item in b.context.original_request.fragments]


def test_full_observation_outside_original_target_fragment_cannot_ground_literal(materialization):
    b = settled_case(materialization)
    text = "Peru elsewhere"
    for run in (b.prior.run, b.result.run):
        for item in run.observations:
            item.literal_text = text
    fragments = tuple(item.model_copy(update={"observation_text": text,
        "observation_digest": hashlib.sha256(text.encode()).hexdigest(),
        "start": 5, "end": len(text), "literal": "elsewhere"}) for item in b.context.original_request.fragments)
    b.context = replace(b.context, original_request=b.context.original_request.model_copy(update={"fragments": fragments}),
        prior_snapshot_sha256=canonical_digest(b.prior.model_dump(mode="json")),
        native_prior_snapshot=native_snapshot_proof(b.prior, b.context.prior_record_version_id))
    value = b.checkpoint.resolution.value.model_copy(update={"literal": "Peru",
        "verbatim_by_observation": {item.id: "elsewhere" for item in b.prior.run.observations}})
    replace_target_value(b, value)
    assert validate_resolution(b.context.original_request, b.checkpoint.resolution, b.context.tool_results) == b.checkpoint.resolution
    with pytest.raises(PublicationUnavailable, match="^canonical_lineage_literal_unproved$"):
        project(b)


def complementary_case(materialization):
    """Genuine deterministic target assembly; native semantic acceptance is synthetic."""
    b = settled_case(materialization)
    words = ("wet", "forest")
    for item, word in zip(b.prior.run.observations, words):
        item.literal_text = word
        item.raw_sha256 = digest("synthetic immutable reading " + word)
    b.result = b.prior.model_copy(deep=True)
    b.result.version += 1
    old = b.context.original_request
    fragments = tuple(item.model_copy(update={"observation_text": word,
        "observation_digest": hashlib.sha256(word.encode()).hexdigest(),
        "start": 0, "end": len(word), "literal": word}) for item, word in zip(old.fragments, words))
    original_evidence = EvidenceItem(id="synthetic-habitat-label-evidence", kind="literal",
        source_id="synthetic-original-label", locator="fixture://label/habitat",
        response_digest=digest([item.observation_text for item in fragments]), source_version="fixture-v1",
        publisher_assertion_id="synthetic-habitat-label", excerpt="wet forest", event_id="synthetic-collecting")
    evidence = (original_evidence.id,)
    native_evidence_id = UUID(ident("synthetic-native-habitat-label-evidence"))
    native_evidence = Evidence(id=str(native_evidence_id), kind="literal", asset_id=b.prior.asset.id,
        region_id=b.prior.run.regions[0].id, observation_ids=[item.observation_id for item in fragments],
        source="synthetic original label", locator="fixture://label/habitat", excerpt="wet forest")
    b.prior.run.evidence.append(native_evidence)
    b.result.run.evidence.append(native_evidence.model_copy(deep=True))
    event = EventHypothesis(id="synthetic-collecting", scope=old.scope, kind=EventKind.COLLECTING,
        fragment_ids=tuple(item.id for item in fragments), evidence_ids=evidence,
        reason="Synthetic accepted collecting relationship", status="accepted", validator_version="synthetic-semantic-v1")
    relation = FragmentRelation(id="synthetic-continuation", scope=old.scope,
        fragment_ids=event.fragment_ids, kind=RelationKind.CONTINUATION, event_id=event.id,
        evidence_ids=evidence, reason="Synthetic accepted complementary label spans",
        proposer_version="fixture-v1", validator_version="synthetic-semantic-v1", status="accepted")
    assembly = assemble_field(assembly_id="synthetic-habitat", scope=old.scope, field_key=FieldKey.HABITAT,
        fragments=fragments, event=event, relations=(relation,), assertion_kind="complementary")
    prompt = resolve_prompt(SpecialistRole.COLLECTION, profile_digest=old.scope.profile_digest,
        source_registry_digest=old.prompt.source_registry_digest, toolset_digest=digest("fixture-collection-tools"),
        model_route="harness-deepseek", output_schema_digest=digest("fixture-collection-schema"))
    request = SpecialistRequest(scope=old.scope, role=SpecialistRole.COLLECTION, field_keys=(FieldKey.HABITAT,),
        prompt=prompt, fragments=fragments, events=(event,), relations=(relation,), assemblies=(assembly,),
        evidence=(original_evidence,))
    value = FieldValue(state=ValueState.SUPPORTED, literal=assembly.interpreted_text,
        parsed=assembly.interpreted_text, normalized=assembly.interpreted_text, layer="settled",
        verbatim_by_observation={item.observation_id: item.literal for item in fragments},
        settled_observation_ids=[item.observation_id for item in fragments],
        input_source_by_observation={item.observation_id: "raw_reading" for item in fragments},
        input_source="raw_reading", source_region_id=b.prior.run.regions[0].id,
        evidence_ids=list(evidence), evidence_relations={eid: "supports" for eid in evidence},
        reason="Synthetic complementary original habitat fragments")
    resolution = FieldResolution(field_key=FieldKey.HABITAT, work_state=WorkState.RESOLVED,
        value=value, value_layer="settled", evidence_ids=evidence, assembly_ids=(assembly.id,),
        event_id=event.id, reason="Exact deterministic original assembly")
    b.checkpoint = b.checkpoint.model_copy(update={"field_key": FieldKey.HABITAT, "resolution": resolution,
        "prompt_digest": prompt.digest, "effect_receipt_ids": ()})
    b.context = replace(b.context, original_request=request, tool_results=(),
        evidence_id_mapping={original_evidence.id: native_evidence_id},
        prior_snapshot_sha256=canonical_digest(b.prior.model_dump(mode="json")),
        native_prior_snapshot=native_snapshot_proof(b.prior, b.context.prior_record_version_id))
    replace_target_value(b, value)
    return b, assembly


def test_complementary_literal_uses_exact_original_target_assembly_without_single_reader_choice(materialization):
    b, assembly = complementary_case(materialization)
    assert all(assembly.interpreted_text not in item.literal_text for item in b.prior.run.observations)
    assert validate_resolution(b.context.original_request, b.checkpoint.resolution) == b.checkpoint.resolution
    output = project(b)
    candidate = next(row.variables for row in output.target_writes if row.operation == "AppendFieldCandidateLineageV2")
    lineage = next(row.variables for row in output.target_writes if row.operation == "AppendCanonicalValueLineageV2")
    proof = lineage["literalGrounding"]
    assert candidate["literalValue"] == "wet forest" and candidate["sourceObservationId"] is None
    assert candidate["sourceTranscriptionId"] is None and proof["kind"] == "original_target_assembly"
    assert proof["assemblies"][0]["assembly"] == assembly.model_dump(mode="json")
    assert proof["assemblies"][0]["assemblyDigest"] == digest(assembly)
    assert proof["assemblies"][0]["fragments"] == [item.model_dump(mode="json") for item in b.context.original_request.fragments]
    assert len([row for row in output.record_writes if row.operation == "AppendResolvedFieldV2"]) == 20


def test_correct_assembled_science_does_not_ground_a_different_candidate_literal(materialization):
    b, assembly = complementary_case(materialization)
    replace_target_value(b, b.checkpoint.resolution.value.model_copy(update={"literal": "wet invented forest"}))
    assert b.result.run.fields["habitat"].normalized == assembly.interpreted_text
    assert validate_resolution(b.context.original_request, b.checkpoint.resolution) == b.checkpoint.resolution
    with pytest.raises(PublicationUnavailable, match="^canonical_lineage_literal_unproved$"):
        project(b)



def packed_graph_case(materialization, tmp_path):
    b = settled_case(materialization)
    # Force real ordinary active-run storage and original bytes, not a renamed
    # packed hash or a fabricated inline snapshot.
    for run in (b.prior.run, b.result.run):
        run.reading_metadata["synthetic-large-label-context"] = "x" * 120000
    blobs = LocalBlobs(tmp_path / "actual-disposable-graph-objects")
    proof = native_snapshot_proof(b.prior, b.context.prior_record_version_id, blobs)
    b.result.active_graph = copy.deepcopy(b.prior.active_graph)
    b.context = replace(b.context, native_prior_snapshot=proof,
        prior_snapshot_sha256=canonical_digest(b.prior.model_dump(mode="json")))
    assert proof.canonical.snapshot_sha256 != b.context.prior_snapshot_sha256
    return b


def test_packed_native_and_rehydrated_graph_have_distinct_retained_digests(materialization, tmp_path):
    b = packed_graph_case(materialization, tmp_path)
    output = project(b)
    lineage = next(row.variables for row in output.target_writes if row.operation == "AppendCanonicalValueLineageV2")
    proof = b.context.native_prior_snapshot
    assert lineage["priorNativeSnapshotDigest"] == proof.canonical.snapshot_sha256
    assert lineage["priorGraphSnapshotDigest"] == b.context.prior_snapshot_sha256
    assert lineage["priorActiveGraphDigest"] == hashlib.sha256(proof.active_graph_bytes).hexdigest()
    assert output.result_snapshot_sha256 == canonical_digest(b.result.model_dump(mode="json"))


@pytest.mark.parametrize("mutation", ["packed_as_graph", "graph_as_native", "altered_original_bytes", "missing_original_bytes", "wrong_native_record"])
def test_native_packed_graph_proof_cannot_be_relabelled_or_guessed(materialization, tmp_path, mutation):
    b = packed_graph_case(materialization, tmp_path)
    proof = b.context.native_prior_snapshot
    if mutation == "packed_as_graph":
        b.context = replace(b.context, prior_snapshot_sha256=proof.canonical.snapshot_sha256)
    elif mutation == "graph_as_native":
        proof = replace(proof, canonical=proof.canonical.model_copy(update={"snapshot_sha256": b.context.prior_snapshot_sha256}))
    elif mutation == "altered_original_bytes":
        proof = replace(proof, active_graph_bytes=proof.active_graph_bytes + b" ")
    elif mutation == "missing_original_bytes":
        proof = replace(proof, active_graph_bytes=None)
    else:
        proof = replace(proof, canonical=proof.canonical.model_copy(update={"record_version_id": UUID(ident("wrong native prior record"))}))
    b.context = replace(b.context, native_prior_snapshot=proof)
    assert b.result.run.fields["country"].normalized == "Peru"
    before = b.prior.model_dump(mode="json")
    with pytest.raises(PublicationUnavailable, match="^canonical_lineage_native_(snapshot|graph)_unproved$"):
        project(b)
    assert b.prior.model_dump(mode="json") == before


# Actual capture-fixture inputs: synthetic scope/generation/lease/cost authority,
# genuine local capture path and immutable bytes. No network/native is qualified.
from test_canonical_evidence_provider_v2 import native_capture_rig, decided_native_capture_rig


def captured_tool_case(f):
    import asyncio
    contribution, = asyncio.run(f.provider.capture_v2(f.principal, f.prepared, f.binding, f.prior))
    context = CanonicalLineageContextV2(scope=f.rig.scope, actor_uid=f.principal.user_id,
        prior_record_version_id=f.binding.canonical.record_version_id, prior_revision=f.prior.version,
        prior_snapshot_sha256=canonical_digest(f.prior.model_dump(mode="json")),
        native_prior_snapshot=NativePriorSnapshotProofV2(canonical=f.binding.canonical, snapshot=f.row["snapshot"]["snapshot"]),
        job=f.binding.registration.job, field_mapping=f.binding.registration.field_mapping,
        evidence_id_mapping={contribution.evidence.id: UUID(contribution.canonical_evidence.id)},
        human_locks=f.binding.registration.human_locks, prior_projection=tuple(f.row["projection"]),
        original_request=f.rig.request, tool_results=(f.result,))
    return contribution, context


def test_tool_input_and_execution_rows_retain_actual_original_request_capture_and_reader(native_capture_rig):
    f = native_capture_rig
    contribution, context = captured_tool_case(f)
    before = copy.deepcopy(f.rig.store._read(f.rig.durable_scope).state)
    rows = project_tool_input_lineage_v2(f.principal, prior=f.prior, checkpoint=f.checkpoint, context=context, contribution=contribution)
    assert [row.operation for row in rows] == ["AppendToolInputLineageV2", "AppendCapturedToolExecutionV2"]
    input_row, execution_row = (row.variables for row in rows)
    assert input_row["originalRequest"] == f.rig.request.model_dump(mode="json")
    assert input_row["queryDigest"] == digest(contribution.tool_execution.arguments)
    assert input_row["fragments"] == [value.model_dump(mode="json") for value in f.rig.request.fragments]
    assert input_row["nativeInputs"] == [value.model_dump(mode="json") for value in contribution.tool_input_lineage.native_inputs]
    assert input_row["observationIds"] == [f.prior.run.observations[0].id]
    assert input_row["selectedObservationId"] == f.checkpoint.resolution.value.source_observation_id
    assert input_row["receiptDigest"] == contribution.proof.receipt.receipt_digest
    assert input_row["receiptBindingDigest"] == digest(contribution.proof.receipt)
    assert execution_row["execution"] == contribution.tool_execution.model_dump(mode="json")
    assert execution_row["lineageId"] == input_row["id"]
    assert f.rig.store._read(f.rig.durable_scope).state == before and len(f.rig.calls) == 1


@pytest.mark.parametrize("mutation", ["foreign_actor", "field", "request", "evidence_mapping", "changed_native_reading"])
def test_tool_lineage_cannot_guess_or_rebind_actual_request_effect_reader(native_capture_rig, mutation):
    f = native_capture_rig
    contribution, context = captured_tool_case(f)
    principal = f.principal
    if mutation == "foreign_actor":
        principal = principal.model_copy(update={"user_id": "other-actor"})
    elif mutation == "field":
        contribution = contribution.model_copy(update={"tool_execution": contribution.tool_execution.model_copy(update={"field_keys": ("country",)})})
    elif mutation == "request":
        context = replace(context, original_request=f.rig.request.model_copy(update={"scope": f.rig.scope.model_copy(update={"generation": 2})}))
    elif mutation == "evidence_mapping":
        context = replace(context, evidence_id_mapping={})
    else:
        f.prior.run.observations[0] = f.prior.run.observations[0].model_copy(update={"literal_text": "different actual text"})
        # Preserve a coherent native snapshot to test the independent input join.
        context = replace(context, native_prior_snapshot=native_snapshot_proof(f.prior, context.prior_record_version_id),
            prior_snapshot_sha256=canonical_digest(f.prior.model_dump(mode="json")))
    before = copy.deepcopy(f.rig.store._read(f.rig.durable_scope).state)
    with pytest.raises(PublicationUnavailable, match="^canonical_tool_lineage_(unproved|input_unproved)$"):
        project_tool_input_lineage_v2(principal, prior=f.prior, checkpoint=f.checkpoint, context=context, contribution=contribution)
    assert f.rig.store._read(f.rig.durable_scope).state == before and len(f.rig.calls) == 1


@pytest.mark.parametrize("revision", [True, 1.0, "1", 0, -1])
def test_tool_mapper_rejects_non_positive_actual_int_context_CAS(native_capture_rig, revision):
    f = native_capture_rig
    contribution, context = captured_tool_case(f)
    assert context.prior_revision == f.prior.version == 1
    original = copy.deepcopy(context.job)
    with pytest.raises(PublicationUnavailable, match="^canonical_lineage_revision_unproved$"):
        project_tool_input_lineage_v2(f.principal, prior=f.prior, checkpoint=f.checkpoint,
            context=replace(context, prior_revision=revision), contribution=contribution)
    assert context.job == original and len(f.rig.calls) == 1


def test_tool_mapper_retains_only_an_actual_original_receipt_attempt(native_capture_rig):
    f = native_capture_rig
    contribution, context = captured_tool_case(f)
    assert contribution.tool_execution.attempt_id in f.result.receipt.attempt_ids
    assert contribution.proof.receipt.attempt_id in f.result.receipt.attempt_ids
    before = copy.deepcopy(f.rig.store._read(f.rig.durable_scope).state)
    genuine = project_tool_input_lineage_v2(f.principal, prior=f.prior, checkpoint=f.checkpoint,
        context=context, contribution=contribution)
    absent = "coherent-but-not-an-original-attempt"
    assert absent not in f.result.receipt.attempt_ids
    changed = contribution.model_copy(update={
        "tool_execution": contribution.tool_execution.model_copy(update={"attempt_id": absent}),
        "proof": contribution.proof.model_copy(update={
            "receipt": contribution.proof.receipt.model_copy(update={"attempt_id": absent})})})
    assert changed.source_result == contribution.source_result
    assert changed.original_specialist_request == contribution.original_specialist_request
    with pytest.raises(PublicationUnavailable, match="^canonical_tool_lineage_attempt_unproved$"):
        project_tool_input_lineage_v2(f.principal, prior=f.prior, checkpoint=f.checkpoint,
            context=context, contribution=changed)
    assert all(row.variables["attemptId"] == contribution.tool_execution.attempt_id for row in genuine)
    assert f.rig.store._read(f.rig.durable_scope).state == before and len(f.rig.calls) == 1


def decided_case(materialization, *, object_response_equal=False):
    """Actual typed first-pass projection; every native row/generation is synthetic."""
    b = settled_case(materialization)
    region = b.prior.run.regions[0].id
    for index, observation in enumerate(b.prior.run.observations):
        observation.literal_text = "Per?" if index == 0 else "Peru raw alternate"
        observation.raw_ref = (observation.raw_sha256 if object_response_equal else
            digest("retained stored bytes " + observation.id)) + ":application/json"
    call = b.prior.run.observations[0].model_copy(deep=True, update={
        "id": ident("decided first-pass observation"), "literal_text": "Peru",
        "raw_ref": digest("retained first-pass bytes") + ":application/json", "raw_sha256": digest("first-pass raw fixture")})
    if object_response_equal:
        call.raw_ref = call.raw_sha256 + ":application/json"
    transcript = Transcript(region_id=region, text="Peru", observation_ids=[item.id for item in b.prior.run.observations],
        alternatives=[], resolved=True, decision_kind="first_pass", selected_observation_id=b.prior.run.observations[0].id,
        first_pass_call=call, reason="fixture captured first-pass decision")
    b.prior.run.transcripts = [row for row in b.prior.run.transcripts if row.region_id != region] + [transcript]
    b.result.run.observations = [row.model_copy(deep=True) for row in b.prior.run.observations]
    b.result.run.transcripts = [row.model_copy(deep=True) for row in b.prior.run.transcripts]
    fragments = tuple(row.model_copy(update={"observation_text": "Peru", "observation_digest": hashlib.sha256(b"Peru").hexdigest(),
        "start": 0, "end": 4, "literal": "Peru", "input_source": "decided_transcript"}) for row in b.context.original_request.fragments)
    request = b.context.original_request.model_copy(update={"fragments": fragments})
    outer = {"organizationId": b.context.scope.organization_id, "collectionId": b.context.scope.collection_id}
    def native_asset(row):
        native = _blob_asset(b.prior, row.raw_ref, "raw_response",
            lambda ref: Blob(bucket="fixture", object_name=ref.partition(":")[0], generation="1"), b.principal.user_id)
        variables = {**outer, **native.variables, "byteSize": "12"}
        return NativeRawSourceAssetProofV2(original_ref=row.raw_ref, row=variables)
    assets = tuple(native_asset(row) for row in (*b.prior.run.observations, call))
    def asset(ref, kind):
        matches = [item for item in assets if item.original_ref == ref and item.row["kind"] == kind]
        assert len(matches) == 1
        return matches[0].row["id"]
    native_decision = tuple({"operation": row.operation, "variables": {**outer, **row.variables}}
        for row in _first_pass(b.prior.run, transcript, asset, {}, reviewer=True))
    version = next(row["variables"]["id"] for row in native_decision if row["operation"] == "AppendTranscriptionVersionV2")
    native_readers = tuple({"operation": "AppendModelObservationV2", "variables": {
        **outer, **_reading(b.prior.run, row, asset(row.raw_ref, "raw_response")).variables}}
        for row in b.prior.run.observations)
    proof = NativeTranscriptionDecisionProofV2(region_id=region, transcription_version_id=UUID(version),
        region_row={**outer, "id": _region_row(b.prior.run.id, region), "runId": b.prior.run.id, "domainRegionId": region},
        decision_rows=native_decision, reader_rows=native_readers, raw_assets=assets)
    b.context = replace(b.context, original_request=request, transcription_proofs=(proof,),
        prior_snapshot_sha256=canonical_digest(b.prior.model_dump(mode="json")),
        native_prior_snapshot=native_snapshot_proof(b.prior, b.context.prior_record_version_id))
    value = b.checkpoint.resolution.value.model_copy(update={"literal": "Peru", "input_source": "decided_transcript",
        "input_source_by_observation": {row.id: "decided_transcript" for row in b.prior.run.observations}})
    replace_target_value(b, value)
    return b


def test_decided_transcript_with_different_raw_text_uses_actual_native_decision(materialization):
    b = decided_case(materialization)
    before = b.prior.model_dump(mode="json")
    output = project(b)
    row = next(item.variables for item in output.target_writes if item.operation == "AppendCanonicalValueLineageV2")
    candidate = next(item.variables for item in output.target_writes if item.operation == "AppendFieldCandidateLineageV2")
    native_id = str(b.context.transcription_proofs[0].transcription_version_id)
    assert b.prior.run.observations[0].literal_text != b.prior.run.transcripts[-1].text == "Peru"
    assert candidate["sourceTranscriptionId"] == native_id and candidate["sourceObservationId"] is None
    assert all(item["transcriptionVersionId"] == native_id and item["inputSource"] == "decided_transcript" for item in row["readingSources"])
    assert row["literalGrounding"]["literal"] == candidate["literalValue"] == "Peru"
    assert b.prior.model_dump(mode="json") == before


@pytest.mark.parametrize("equal", [False, True])
def test_decided_native_assets_accept_independent_equal_and_unequal_digest_cases(materialization, equal):
    b = decided_case(materialization, object_response_equal=equal)
    proof = b.context.transcription_proofs[0]
    by_ref = {row.original_ref:row.row for row in proof.raw_assets}
    for observation in (*b.prior.run.observations, b.prior.run.transcripts[-1].first_pass_call):
        assert (by_ref[observation.raw_ref]["sha256"] == observation.raw_sha256) is equal
    output = project(b)
    lineage = next(row.variables for row in output.target_writes if row.operation == "AppendCanonicalValueLineageV2")
    assert lineage["selectedTranscriptionId"] == str(proof.transcription_version_id)
    assert lineage["literalGrounding"]["literal"] == "Peru"


def captured_decided_tool_case(f):
    """Actual local capture plus complete ordinary typed decision/member writes."""
    item, context = captured_tool_case(f)
    transcript = f.prior.run.transcripts[-1]
    observations = {row.id:row for row in f.prior.run.observations}
    outer = {"organizationId":f.rig.scope.organization_id, "collectionId":f.rig.scope.collection_id}
    used = [observations[key] for key in transcript.observation_ids]
    if transcript.first_pass_call is not None:
        used.append(transcript.first_pass_call)
    assets = []
    for reading in used:
        retained = f.graph.get_bounded(reading.raw_ref, 1_000_000)
        write = _blob_asset(f.prior, reading.raw_ref, "raw_response", f.repository.locate, f.principal.user_id)
        assets.append(NativeRawSourceAssetProofV2(original_ref=reading.raw_ref,
            row={**outer, **write.variables, "byteSize":str(len(retained))}))
    def asset(ref, kind):
        matches = [row for row in assets if row.original_ref == ref and row.row["kind"] == kind]
        assert len(matches) == 1
        return matches[0].row["id"]
    decision = tuple({"operation":row.operation, "variables":{**outer, **row.variables}}
        for row in _first_pass(f.prior.run, transcript, asset, {}, reviewer=True))
    readers = tuple({"operation":"AppendModelObservationV2", "variables":{
        **outer, **_reading(f.prior.run, observations[key], asset(observations[key].raw_ref,"raw_response")).variables}}
        for key in transcript.observation_ids)
    version = next(row["variables"]["id"] for row in decision if row["operation"] == "AppendTranscriptionVersionV2")
    proof = NativeTranscriptionDecisionProofV2(region_id=transcript.region_id,
        transcription_version_id=UUID(version), region_row={**outer,
            "id":_region_row(f.prior.run.id, transcript.region_id), "runId":f.prior.run.id,
            "domainRegionId":transcript.region_id}, decision_rows=decision, reader_rows=readers, raw_assets=tuple(assets))
    return item, replace(context, transcription_proofs=(proof,),
        transcription_ids={proof.region_id:proof.transcription_version_id}), proof


def test_actual_decided_tool_capture_emits_complete_native_transcription_proof(decided_native_capture_rig):
    f = decided_native_capture_rig
    before = copy.deepcopy(f.rig.store._read(f.rig.durable_scope).state)
    item, context, proof = captured_decided_tool_case(f)
    output = project_tool_input_lineage_v2(f.principal, prior=f.prior,
        checkpoint=f.checkpoint, context=context, contribution=item)
    lineage = next(row.variables for row in output if row.operation == "AppendToolInputLineageV2")
    assert f.prior.run.observations[0].literal_text != f.prior.run.transcripts[-1].text
    assert lineage["inputSources"] == ["decided_transcript"]
    assert lineage["nativeTranscriptionProofs"] == [proof.model_dump(mode="json")]
    assert lineage["nativeTranscriptionProofs"][0]["decision_rows"]
    assert lineage["nativeTranscriptionProofs"][0]["reader_rows"]
    assert lineage["nativeTranscriptionProofs"][0]["raw_assets"]
    assert f.rig.store._read(f.rig.durable_scope).state == before and len(f.rig.calls) == 1


@pytest.mark.parametrize("mutation", ["foreign_unused", "unused", "duplicate_used", "duplicate_unused"])
def test_actual_decided_tool_capture_denies_unconsumed_or_duplicate_native_assets(decided_native_capture_rig, mutation):
    f = decided_native_capture_rig
    item, context, proof = captured_decided_tool_case(f)
    data = b"actual retained but unconsumed fixture object"
    ref = f.graph.put(data)
    row = _blob_asset(f.prior, ref, "raw_response", f.repository.locate, f.principal.user_id).variables
    row = {"organizationId":f.rig.scope.organization_id, "collectionId":f.rig.scope.collection_id,
        **row, "byteSize":str(len(data))}
    if mutation == "foreign_unused":
        row["organizationId"] = ident("foreign tool proof organization")
    extra = NativeRawSourceAssetProofV2(original_ref=ref, row=row)
    retained = (*proof.raw_assets, extra)
    if mutation == "duplicate_used":
        retained = (*proof.raw_assets, proof.raw_assets[0])
    elif mutation == "duplicate_unused":
        retained = (*retained, extra)
    context = replace(context, transcription_proofs=(proof.model_copy(update={"raw_assets":retained}),))
    before = copy.deepcopy(f.rig.store._read(f.rig.durable_scope).state)
    with pytest.raises(PublicationUnavailable):
        project_tool_input_lineage_v2(f.principal, prior=f.prior,
            checkpoint=f.checkpoint, context=context, contribution=item)
    assert f.rig.store._read(f.rig.durable_scope).state == before and len(f.rig.calls) == 1


@pytest.mark.parametrize("mutation", ["native_id", "native_text", "member", "route", "digest", "ID_only", "missing"])
def test_decided_transcript_proof_rejects_actual_source_drift(materialization, mutation):
    b = decided_case(materialization)
    proof = b.context.transcription_proofs[0]
    if mutation == "native_id":
        proof = proof.model_copy(update={"transcription_version_id": UUID(ident("wrong saved transcription"))})
    elif mutation == "native_text":
        rows = copy.deepcopy(proof.decision_rows)
        next(row["variables"] for row in rows if row["operation"] == "AppendTranscriptionVersionV2")["literalText"] = "wrong native decided text"
        proof = proof.model_copy(update={"decision_rows": rows})
    elif mutation == "member":
        rows = copy.deepcopy(proof.reader_rows);rows[0]["variables"]["id"] = ident("wrong native member")
        proof = proof.model_copy(update={"reader_rows": rows})
    elif mutation in {"route", "digest"}:
        fragments = list(b.context.original_request.fragments)
        fragments[0] = fragments[0].model_copy(update={"input_source": "raw_reading"} if mutation == "route"
            else {"observation_digest": digest("wrong decided text digest")})
        b.context = replace(b.context, original_request=b.context.original_request.model_copy(update={"fragments": tuple(fragments)}))
    if mutation == "ID_only":
        b.context = replace(b.context, transcription_ids={proof.region_id: proof.transcription_version_id}, transcription_proofs=())
    elif mutation == "missing":
        b.context = replace(b.context, transcription_proofs=())
    else:
        b.context = replace(b.context, transcription_proofs=(proof,))
    before = b.prior.model_dump(mode="json")
    assert b.result.run.fields["country"].normalized == "Peru"
    with pytest.raises(PublicationUnavailable):
        project(b)
    assert b.prior.model_dump(mode="json") == before


@pytest.mark.parametrize("mutation", ["foreign_extra", "unused_extra", "duplicate_used", "duplicate_unused"])
def test_decided_proof_requires_exact_used_raw_assets_before_any_projection(materialization, mutation):
    b = decided_case(materialization)
    proof = b.context.transcription_proofs[0]
    extra = copy.deepcopy(proof.raw_assets[0].row)
    ref = digest("genuine-shaped but unrelated retained bytes") + ":application/json"
    extra.update(sha256=ref.partition(":")[0], objectName=ref.partition(":")[0])
    if mutation == "foreign_extra":
        extra.update(organizationId=ident("foreign organization"), collectionId=ident("foreign collection"), specimenId=ident("foreign specimen"))
    extra["id"] = _blob_asset(SimpleNamespace(id=extra["specimenId"]), ref, "raw_response",
        lambda value: Blob(bucket=extra["bucket"], object_name=extra["objectName"], generation=extra["generation"]),
        b.principal.user_id).variables["id"]
    unused = NativeRawSourceAssetProofV2(original_ref=ref, row=extra)
    added = (proof.raw_assets[0],) if mutation == "duplicate_used" else (unused, unused) if mutation == "duplicate_unused" else (unused,)
    changed = proof.model_copy(update={"raw_assets": (*proof.raw_assets, *added)})
    assert changed.decision_rows == proof.decision_rows and changed.reader_rows == proof.reader_rows
    b.context = replace(b.context, transcription_proofs=(changed,))
    original_graph = b.prior.model_dump(mode="json")
    assert b.result.run.fields["country"].normalized == "Peru"
    with pytest.raises(PublicationUnavailable):
        project(b)
    assert b.prior.model_dump(mode="json") == original_graph


def test_native_raw_asset_proof_accepts_actual_Int64_and_keeps_response_SHA_distinct(materialization):
    b = decided_case(materialization)
    proof = b.context.transcription_proofs[0]
    assert all(row.row["byteSize"] == "12" for row in proof.raw_assets)
    assert proof.raw_assets[0].row["sha256"] == b.prior.run.observations[0].raw_ref.partition(":")[0]
    assert proof.raw_assets[0].row["sha256"] != b.prior.run.observations[0].raw_sha256
    output = project(b)
    lineage = next(row.variables for row in output.target_writes if row.operation == "AppendCanonicalValueLineageV2")
    assert lineage["readingSources"][0]["rawDigest"] == b.prior.run.observations[0].raw_sha256
    assert lineage["readingSources"][0]["rawObjectDigest"] == proof.raw_assets[0].row["sha256"]
    assets = tuple(row.model_copy(update={"row": {**row.row, "byteSize": 12}}) for row in proof.raw_assets)
    b.context = replace(b.context, transcription_proofs=(proof.model_copy(update={"raw_assets": assets}),))
    assert project(b).result_snapshot_sha256 == output.result_snapshot_sha256


@pytest.mark.parametrize("size", [True, False, 12.0, -1, None, "012", "+12", " 12", "12.0", "-1", "", "9223372036854775808"])
def test_native_raw_asset_proof_rejects_noncanonical_Int64_sizes(materialization, size):
    b = decided_case(materialization)
    proof = b.context.transcription_proofs[0]
    assets = list(proof.raw_assets)
    assets[0] = assets[0].model_copy(update={"row": {**assets[0].row, "byteSize": size}})
    b.context = replace(b.context, transcription_proofs=(proof.model_copy(update={"raw_assets": tuple(assets)}),))
    with pytest.raises(PublicationUnavailable, match="^canonical_lineage_transcription_raw_asset_unproved$"):
        project(b)


@pytest.mark.parametrize("mutation", ["object_id", "object_sha"])
def test_native_raw_asset_identity_and_stored_SHA_cannot_alias_original_response(materialization, mutation):
    b = decided_case(materialization)
    proof = b.context.transcription_proofs[0]
    assets = list(proof.raw_assets);row = copy.deepcopy(assets[0].row)
    if mutation == "object_id":
        row["id"] = ident("not the actual native source asset")
    else:
        row["sha256"] = b.prior.run.observations[0].raw_sha256
    assets[0] = assets[0].model_copy(update={"row": row})
    b.context = replace(b.context, transcription_proofs=(proof.model_copy(update={"raw_assets": tuple(assets)}),))
    with pytest.raises(PublicationUnavailable, match="^canonical_lineage_transcription_raw_asset_unproved$"):
        project(b)
