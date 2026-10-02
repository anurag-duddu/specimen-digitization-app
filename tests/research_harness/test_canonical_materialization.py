"""I4A producer unit sources, UNRUN; fixtures do not prove Firebase or capture IO.

The admitted complete candidate must supply the pinned ordinary PR168 projector
and the I2 fixture. No partial PYTHONPATH overlay qualifies these cases.
"""
import asyncio
import copy
import hashlib
from types import SimpleNamespace
from uuid import UUID

import pytest

from test_native_canonical_contract import basis as native_basis, derived_resolution, ident, proved_reuse
from specimen_digitization.application.domain import (
    Disposition, Evidence, FieldValue, Lookup, Observation, Region, ToolCallRecord, Transcript, ValueState,
)
from specimen_digitization.application.projection import writes
from specimen_digitization.application.storage import digest as canonical_digest
from specimen_digitization.research_harness.canonical_materialization import (
    CanonicalResearchMaterializer, MaterializationRequestV1, ResearchCanonicalPolicyV1,
)
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.contracts import (
    FieldCheckpoint, FieldKey, FieldResolution, LookupStatus, SourceCoverageReceipt,
    SourceCoverageState, SourceResult, SpecialistRequest, SpecialistRole, ToolReceipt,
    WorkState, digest,
)
from specimen_digitization.research_harness.evidence import emu_irn_exception
from specimen_digitization.research_harness.native_canonical import (
    CANONICAL_PROJECTOR_SHA256, CanonicalBindingV1, CanonicalIdentityV1,
    CanonicalProjectionServicesV1, CapturedCanonicalEvidenceV1,
)
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.publication import PreparedNativePublication
from specimen_digitization.research_harness.sources import result_envelope


class CapturedRequestSource:
    """Synthetic immutable context; production I4B verification is separate."""
    def __init__(self, context):
        self.context = context
        self.calls = 0

    async def read(self, principal, prepared, binding):
        self.calls += 1
        return self.context


@pytest.fixture
def materialization(native_basis):
    b = native_basis
    prior = b.prior.model_copy(deep=True)
    prior.run.profile.institutional_policy_approved = True
    prior.run.profile.semantics_confirmed = True
    prior.run.coverage_confirmed = True
    region_id = ident("i4a-fixture-region")
    prior.run.regions = [Region(id=region_id, asset_id=prior.asset.id, x=0, y=0, width=1, height=1,
        order=0, method="synthetic fixture", version="fixture-v1")]
    prior.run.observations = [Observation(id=ident("i4a-reading-" + str(index)), region_id=region_id,
        route_id="fixture-route-" + str(index), model_id="fixture-model-" + str(index),
        provider="synthetic-unpaid", prompt_version="fixture-v1", input_sha256=prior.asset.sha256,
        literal_text="Peru", raw_ref=digest("reading-" + str(index)) + ":1",
        raw_sha256=digest("synthetic raw reading-" + str(index))) for index in (1, 2)]
    prior.run.transcripts = [Transcript(region_id=region_id,
        observation_ids=[item.id for item in prior.run.observations], text="Peru", alternatives=[], resolved=True)]
    literals = {key: "fixture " + key for key in prior.run.fields}
    literals.update(fmnh_ins_number="FMNH INS 321", country="Peru", elevation_from_m="0",
        elevation_to_m="10", elevation_from_ft="0", elevation_to_ft="32.8084",
        date_visited_from="2020-01-01", date_visited_to="2020-01-02", date_identified="2021-01-01")
    prior.run.evidence = []
    for key, text in literals.items():
        evidence_id = ident("i4a-evidence-" + key)
        prior.run.evidence.append(Evidence(id=evidence_id, kind="literal", asset_id=prior.asset.id,
            region_id=region_id, observation_ids=[item.id for item in prior.run.observations],
            source="independent synthetic expected label", locator="synthetic label", excerpt=text))
        prior.run.fields[key] = FieldValue(state=ValueState.SUPPORTED, literal=text, parsed=text,
            evidence_ids=[evidence_id], reason="Synthetic expected value")
    prior.run.fields["country"] = FieldValue(reason="Synthetic field awaiting genuine resolution")
    prior.run.fields["identified_by_irn"] = FieldValue(reason="No qualified EMu Parties connection")
    prior.run.fields["taxon"].authority_id = "synthetic-taxonomy-id"
    taxon_evidence = next(item for item in prior.run.evidence if item.id == ident("i4a-evidence-taxon"))
    taxon_evidence.kind = "lookup"
    taxon_evidence.excerpt += " synthetic-taxonomy-id"
    prior.run.tool_calls = [ToolCallRecord(call_key="synthetic-taxonomy-proof", phase="lookup",
        tool="synthetic-taxonomy", tool_version="fixture-v1", source="synthetic-taxonomy",
        field_keys=["taxon"], input_source="decided_transcript", attempt=1, arguments={"fixture": True},
        outcome=LookupStatus.SUCCESS, evidence_id=taxon_evidence.id,
        started_at="2026-01-01T00:00:00Z", completed_at="2026-01-01T00:00:01Z")]
    profile = b.binding.registration.job["pins"]["profile"]
    profile = copy.deepcopy(profile)
    for field in profile["fields"]:
        if field["field_key"] == "identified_by_irn":
            field["exception"] = emu_irn_exception().model_dump(mode="json")
        if field["field_key"] == "taxon":
            field["source_ids"] = ["synthetic-taxonomy"]
    pins = copy.deepcopy(b.binding.registration.job["pins"])
    pins["profile"] = profile
    scope = b.scope.model_copy(update={"profile_digest": digest(profile)})
    registry_sha = digest("I4A synthetic registry; not provider authority")
    prompt = resolve_prompt(SpecialistRole.GEOGRAPHY, profile_digest=scope.profile_digest,
        source_registry_digest=registry_sha, toolset_digest=digest("fixture-tools"),
        model_route="harness-deepseek", output_schema_digest=digest("fixture-schema"))
    request = SpecialistRequest(scope=scope, role=SpecialistRole.GEOGRAPHY,
        field_keys=(FieldKey.COUNTRY,), prompt=prompt)
    native_id = ident("i4a-evidence-country")
    research_evidence = {"id": "fixture:actual-country-evidence", "kind": "qualified_source",
        "source_id": "synthetic-country-source", "locator": "fixture://country", "response_digest": digest("country body"),
        "source_version": "fixture-v1", "publisher_assertion_id": "fixture-one", "excerpt": "Peru"}
    effect_id = digest("i4a-source-effect")
    tool = SourceResult(status=LookupStatus.SUCCESS, evidence=(research_evidence,),
        coverage=SourceCoverageReceipt(source_id="synthetic-country-source", field_key=FieldKey.COUNTRY,
            state=SourceCoverageState.SEARCHED, source_version="fixture-v1", qualification_digest=digest("fixture-source-policy"),
            query_digest=digest("fixture-query"), coverage_limit="Synthetic unit proof only", reason="one expected candidate"),
        candidate_json=('{"field_key":"country","value":"Peru","authority_id":null}',))
    body = result_envelope(tool)
    tool = tool.model_copy(update={"receipt": ToolReceipt(id="effect:" + effect_id, scope=scope,
        tool_id="fixture-country", source_id="synthetic-country-source", field_keys=(FieldKey.COUNTRY,),
        effect_id=effect_id, attempt_ids=("fixture-attempt",), request_digest=digest("fixture-request"),
        binding_digest=digest(pins), outcome=LookupStatus.SUCCESS, effect_status="completed",
        evidence_ids=(research_evidence["id"],), result_json=body, result_digest=hashlib.sha256(body.encode()).hexdigest())})
    checkpoint = FieldCheckpoint(scope=scope, field_key=FieldKey.COUNTRY, revision=1,
        resolution=FieldResolution(field_key=FieldKey.COUNTRY, work_state=WorkState.RESOLVED,
            value=FieldValue(state=ValueState.SUPPORTED, literal="Peru", parsed="Peru",
                evidence_ids=[research_evidence["id"]], evidence_relations={research_evidence["id"]: "supports"},
                reason="Exact synthetic source candidate"),
            evidence_ids=(research_evidence["id"],), reason="Exact synthetic source candidate"),
        prompt_digest=prompt.digest, model_settings_digest=digest("fixture-model-settings"),
        source_registry_digest=registry_sha, effect_receipt_ids=(effect_id,))
    raw = b.prepared.model_dump(mode="json")
    raw["publication"]["checkpoints"] = [checkpoint.model_dump(mode="json")]
    raw["publication"]["guard"].update(scope=scope.model_dump(mode="json"), binding_digest=digest(pins),
        checkpoint_digests={"country": digest(checkpoint)}, receipt_ids=[effect_id])
    capture = {"locator": "fixture://semantic-capture", "generation": "1", "sha256": digest("fixture capture"), "byte_size": 2}
    raw["basis"].update(scope=scope.model_dump(mode="json"), original_scope=scope.model_dump(mode="json"),
        binding_digest=digest(pins), pins_digest=digest(pins), source_binding_digest=digest(pins),
        typed_checkpoint_digest=digest(checkpoint), original_typed_checkpoint_digest=digest(checkpoint),
        receipts=[{"effect_id": effect_id, "request_digest": digest("fixture-request"), "binding_digest": digest(pins),
                   "attempt_id": "fixture-attempt", "receipt_digest": digest("fixture-receipt"), "capture": capture}])
    prepared = PreparedNativePublication.model_validate(raw)
    services = CanonicalProjectionServicesV1(writes, b.connector.locate, b.connector._sized, CANONICAL_PROJECTOR_SHA256)
    projected = writes(prior, services.locate, services.size, b.principal.user_id)
    record = next(item.variables for item in projected if item.operation == "AppendRecordVersionV2")
    rows = tuple(item.variables for item in projected if item.operation == "AppendResolvedFieldV2")
    identity = CanonicalIdentityV1(record_revision=prior.version, record_version_id=record["id"],
        canonical_run_id=prior.run.id, host_record_version_id=prior.run.id + ":1",
        snapshot_sha256=canonical_digest(prior.model_dump(mode="json")))
    policy = ResearchCanonicalPolicyV1(canonical_profile_digest=canonical_digest(prior.run.profile_snapshot),
        research_profile_digest=scope.profile_digest, source_registry_digest=registry_sha)
    registration = b.binding.registration.model_dump(mode="json")
    semantic = copy.deepcopy(registration["semantic_mapping"])
    semantic.update(research_policy_contract_version=policy.contract_version,
                    research_policy_origin="owner reviewed synthetic fixture only")
    registration.update(base_canonical=identity.model_dump(mode="json"), current_canonical=identity.model_dump(mode="json"),
        profile_digest=scope.profile_digest, runtime_binding_digest=digest(pins), policy_digest=digest(policy),
        semantic_mapping=semantic, semantic_mapping_digest=digest(semantic), research_policy_origin=semantic["research_policy_origin"])
    job = registration["job"]
    job.update(pins=pins, binding_digest=digest(pins))
    for field_key, state in job["fields"].items():
        state["work_state"] = str(WorkState.NONBLOCKING_EXCEPTION if field_key == "identified_by_irn" else WorkState.RESOLVED)
    registration["read_bundle"].update(job=job, server_time=2000000000.0)
    binding = CanonicalBindingV1.model_validate({**b.binding.model_dump(mode="json"),
        "canonical": identity.model_dump(mode="json"), "registration": registration})
    contribution = CapturedCanonicalEvidenceV1(origin="existing_canonical", evidence=research_evidence,
        canonical_evidence=next(item for item in prior.run.evidence if item.id == native_id), canonical_producer=None,
        receipt=None, source_policy_digest=digest("fixture-source-policy"), source_registry_digest=registry_sha,
        canonical_mapping_digest=registration["semantic_mapping_digest"], canonical_run_id=prior.run.id,
        canonical_region_id=region_id, canonical_observation_ids=tuple(item.id for item in prior.run.observations))
    context = MaterializationRequestV1(digest(prepared), identity.snapshot_sha256, request, (tool,))
    source = CapturedRequestSource(context)
    return SimpleNamespace(principal=b.principal, prior=prior, prepared=prepared, binding=binding, policy=policy,
        services=services, rows=rows, evidence=(contribution,), source=source,
        producer=CanonicalResearchMaterializer(policy, source))


def produce(b, **overrides):
    args = {"prior_projection": b.rows, "captured_evidence": b.evidence, "projection_services": b.services}
    args.update(overrides)
    return asyncio.run(b.producer.materialize(b.principal, b.prepared, b.binding, b.prior, **args))


def test_verified_resolution_clears_with_real_twenty_field_output_without_blanket_human_approval(materialization):
    b = materialization
    before = b.prior.model_dump(mode="json")
    result = produce(b)
    assert result.result.version == b.prior.version + 1
    assert result.result.run.fields["country"].literal == "Peru"
    assert result.result.run.fields["country"].layer == "verbatim"
    assert result.result.run.disposition == Disposition.CLEARED
    assert result.result.run.human_approved is False
    assert result.result.run.fields["identified_by_irn"].state == ValueState.UNKNOWN
    assert len(result.result.run.fields) == 20
    assert all(result.result.run.fields[key] == b.prior.run.fields[key] for key in b.prior.run.fields if key != "country")
    assert b.prior.model_dump(mode="json") == before
    assert result.result_digest == canonical_digest(result.result.model_dump(mode="json"))
    assert result.evidence_id_mapping == {b.evidence[0].evidence.id: UUID(b.evidence[0].canonical_evidence.id)}
    assert produce(b).lineage_digest == result.lineage_digest


@pytest.mark.parametrize("kind", ["missing", "duplicate", "foreign_version", "changed_other_candidate"])
def test_incomplete_or_wrong_predecessor_projection_preserves_prior(materialization, kind):
    b = materialization
    rows = copy.deepcopy(list(b.rows))
    if kind == "missing": rows.pop()
    if kind == "duplicate": rows[-1] = copy.deepcopy(rows[0])
    if kind == "foreign_version": rows[0]["recordVersionId"] = ident("wrong native version")
    if kind == "changed_other_candidate":
        row = next(row for row in rows if row["fieldKey"] != "country")
        row["candidateId"] = ident("wrong candidate")
    before = b.prior.model_dump(mode="json")
    with pytest.raises(PublicationUnavailable): produce(b, prior_projection=rows)
    assert b.prior.model_dump(mode="json") == before


def test_date_identified_is_mandatory_while_unqualified_irn_stays_visible_nonblocking(materialization):
    b = materialization
    from specimen_digitization.research_harness.canonical_materialization import _disposition
    profile = b.binding.registration.job["pins"]["profile"]
    from specimen_digitization.research_harness.contracts import CollectionProfile
    prior = b.prior.model_copy(deep=True)
    prior.run.fields["country"] = b.prepared.publication.checkpoints[0].resolution.value.model_copy(deep=True)
    prior.run.fields["country"].evidence_ids = [b.evidence[0].canonical_evidence.id]
    prior.run.fields["date_identified"] = FieldValue(reason="Actual date is absent")
    reasons = _disposition(prior, CollectionProfile.model_validate(profile), 2000000000.0)
    assert "mandatory_unresolved:date_identified" in reasons
    assert not any("identified_by_irn" in reason for reason in reasons)


@pytest.mark.parametrize("part", ["actor", "snapshot", "source", "profile", "policy_budget", "human_lock", "request", "registry", "projector"])
def test_wrong_identity_policy_input_or_authority_never_changes_prior(materialization, part):
    b = materialization
    before = b.prior.model_dump(mode="json")
    if part == "actor": b.principal = b.principal.model_copy(update={"user_id": "other actor"})
    if part == "snapshot": b.binding = b.binding.model_copy(update={"canonical": b.binding.canonical.model_copy(update={"snapshot_sha256": digest("wrong")})})
    if part == "source": b.binding = b.binding.model_copy(update={"registration": b.binding.registration.model_copy(update={"source_sha256": digest("wrong")})})
    if part == "profile": b.producer.policy = b.policy.model_copy(update={"research_profile_digest": digest("wrong")})
    if part == "policy_budget": b.binding = b.binding.model_copy(update={"registration": b.binding.registration.model_copy(update={"policy_digest": b.binding.registration.journal_budget_policy_digest})})
    if part == "human_lock":
        locks = dict(b.binding.registration.human_locks); locks["country"] = True
        b.binding = b.binding.model_copy(update={"registration": b.binding.registration.model_copy(update={"human_locks": locks})})
    if part == "request": b.source.context = MaterializationRequestV1(digest("wrong"), b.source.context.canonical_snapshot_sha256, b.source.context.request, b.source.context.tool_results)
    if part == "registry": b.evidence = (b.evidence[0].model_copy(update={"source_registry_digest": digest("wrong")}),)
    if part == "projector": b.services = CanonicalProjectionServicesV1(writes, b.services.locate, b.services.size, digest("old projector"))
    with pytest.raises((PublicationUnavailable, PermissionError)): produce(b)
    assert b.prior.model_dump(mode="json") == before


def test_missing_actual_request_factory_is_unavailable_not_scientific_absence(materialization):
    b = materialization
    b.producer = CanonicalResearchMaterializer(b.policy, None)
    with pytest.raises(PublicationUnavailable, match="canonical_captured_request_source_unavailable"):
        produce(b)
    assert b.prior.version == 1


def test_operational_failure_stays_blocked_and_does_not_become_human_review(materialization):
    from specimen_digitization.research_harness.canonical_materialization import _disposition
    from specimen_digitization.research_harness.contracts import CollectionProfile
    b = materialization
    prior = b.prior.model_copy(deep=True)
    prior.run.blocker = "provider_authentication_error"
    with pytest.raises(PublicationUnavailable, match="canonical_operational_failure_not_human_review"):
        _disposition(prior, CollectionProfile.model_validate(b.binding.registration.job["pins"]["profile"]), 2000000000.0)


@pytest.mark.parametrize("state", [WorkState.WAITING_SOURCE, WorkState.WAITING_POLICY,
    WorkState.OPERATIONAL_FAILED, WorkState.RETRY_SCHEDULED])
def test_unfinished_or_retry_work_cannot_publish_a_scientific_output(materialization, state):
    b = materialization
    payload = b.prepared.model_dump(mode="json")
    checkpoint = FieldCheckpoint.model_validate(payload["publication"]["checkpoints"][0])
    checkpoint = checkpoint.model_copy(update={"resolution": checkpoint.resolution.model_copy(update={"work_state": state})})
    payload["publication"]["checkpoints"] = [checkpoint.model_dump(mode="json")]
    payload["publication"]["guard"]["checkpoint_digests"] = {"country": digest(checkpoint)}
    payload["basis"].update(typed_checkpoint_digest=digest(checkpoint), original_typed_checkpoint_digest=digest(checkpoint))
    b.prepared = PreparedNativePublication.model_validate(payload)
    old = b.source.context
    b.source.context = MaterializationRequestV1(digest(b.prepared), old.canonical_snapshot_sha256, old.request, old.tool_results)
    before = b.prior.model_dump(mode="json")
    with pytest.raises(PublicationUnavailable, match="canonical_operational_or_policy_work_not_publishable"):
        produce(b)
    assert b.prior.model_dump(mode="json") == before


def test_raw_readings_can_settle_without_selected_transcript_or_single_literal(materialization):
    from specimen_digitization.research_harness.canonical_materialization import _disposition
    from specimen_digitization.research_harness.contracts import CollectionProfile
    b = materialization
    result = produce(b).result
    profile = CollectionProfile.model_validate(b.binding.registration.job["pins"]["profile"])
    label = "\n".join(value.literal for key, value in result.run.fields.items() if key != "identified_by_irn")
    for observation in result.run.observations:
        observation.literal_text = label
    result.run.transcripts[0].resolved = False
    result.run.transcripts[0].text = None
    for key, value in result.run.fields.items():
        if key == "identified_by_irn": continue
        value.input_source = "raw_reading"
        value.source_region_id = result.run.regions[0].id
        value.verbatim_by_observation = {reading.id: value.literal for reading in result.run.observations}
        value.input_source_by_observation = {reading.id: "raw_reading" for reading in result.run.observations}
        value.settled_observation_ids = [reading.id for reading in result.run.observations]
    country = result.run.fields["country"]
    country.literal = None
    country.source_observation_id = result.run.observations[0].id
    country_evidence = next(item for item in result.run.evidence if item.id in country.evidence_ids)
    country_evidence.kind = "lookup"
    identifier = result.run.fields["fmnh_ins_number"]
    identifier.literal = None
    identifier_evidence = next(item for item in result.run.evidence if item.id in identifier.evidence_ids)
    identifier_evidence.kind = "lookup"
    assert _disposition(result, profile, 2000000000.0) == []
    country.verbatim_by_observation[result.run.observations[0].id] = "unwritten claim"
    assert any("grounding" in reason or "unresolved" in reason for reason in _disposition(result, profile, 2000000000.0))


def test_earlier_unrecovered_dependency_failure_is_not_hidden_by_unrelated_success(materialization):
    from specimen_digitization.research_harness.canonical_materialization import _disposition
    from specimen_digitization.research_harness.contracts import CollectionProfile
    b = materialization
    result = produce(b).result
    profile = CollectionProfile.model_validate(b.binding.registration.job["pins"]["profile"])
    result.run.lookups = [Lookup(provider="fixture-source", adapter_version="fixture-v1",
        query={"taxon": "depended-on taxon"}, status=LookupStatus.TIMEOUT),
        Lookup(provider="fixture-source", adapter_version="fixture-v1", query={"country": "unrelated"}, status=LookupStatus.SUCCESS)]
    with pytest.raises(PublicationUnavailable, match="canonical_operational_failure_not_human_review"):
        _disposition(result, profile, 2000000000.0)
    assert _disposition(result, profile, 2000000000.0, decision_lookup_ids=frozenset()) == []
    result.run.lookups.append(Lookup(provider="fixture-source", adapter_version="fixture-v1",
        query={"taxon": "depended-on taxon"}, status=LookupStatus.SUCCESS))
    assert _disposition(result, profile, 2000000000.0) == []
    with pytest.raises(PublicationUnavailable, match="canonical_operational_failure_not_human_review"):
        _disposition(result, profile, 2000000000.0, latest_work={"country": "operational_failed"})


def test_registered_harness_policy_retires_legacy_blanket_approval_gates(materialization):
    from specimen_digitization.research_harness.canonical_materialization import _disposition
    from specimen_digitization.research_harness.contracts import CollectionProfile
    b = materialization
    result = produce(b).result
    result.run.profile.institutional_policy_approved = False
    result.run.profile.semantics_confirmed = False
    assert result.run.human_approved is False
    assert _disposition(result, CollectionProfile.model_validate(b.binding.registration.job["pins"]["profile"]), 2000000000.0) == []



def test_proved_retry_reuse_keeps_original_request_and_receipts_without_rebinding(materialization):
    b = materialization
    original_scope = b.prepared.basis.scope
    original_request = b.source.context.request
    original_receipts = b.prepared.basis.receipts
    prepared, binding, history = proved_reuse(b)
    b.prepared, b.binding = prepared, binding
    old = b.source.context
    b.source.context = MaterializationRequestV1(digest(prepared), old.canonical_snapshot_sha256,
        old.request, old.tool_results, old.decision_lookup_ids)
    history_before = copy.deepcopy(binding.registration.job["history"])
    result = produce(b)
    assert result.result.run.disposition == Disposition.CLEARED
    assert b.source.context.request == original_request
    assert b.source.context.request.scope == original_scope
    assert b.prepared.basis.scope.generation == original_scope.generation + 1
    assert b.prepared.basis.receipts == original_receipts
    assert b.binding.registration.job["history"] == history_before == [history]
    assert b.binding.registration.base_canonical.record_revision == b.prior.version == 1


@pytest.mark.parametrize("tamper", ["rebound_request", "missing_history", "changed_history"])
def test_retry_reuse_requires_original_request_and_exact_retained_history(materialization, tamper):
    b = materialization
    b.prepared, b.binding, history = proved_reuse(b)
    old = b.source.context
    request = old.request.model_copy(update={"scope": b.prepared.basis.scope}) if tamper == "rebound_request" else old.request
    b.source.context = MaterializationRequestV1(digest(b.prepared), old.canonical_snapshot_sha256,
        request, old.tool_results, old.decision_lookup_ids)
    if tamper != "rebound_request":
        job = copy.deepcopy(b.binding.registration.job)
        if tamper == "missing_history": job["history"] = []
        else: job["history"][0]["binding_digest"] = digest("changed retained pins")
        reg = b.binding.registration.model_copy(update={"job": job,
            "read_bundle": {**b.binding.registration.read_bundle, "job": job}})
        b.binding = b.binding.model_copy(update={"registration": reg})
    before = b.prior.model_dump(mode="json")
    with pytest.raises(PublicationUnavailable): produce(b)
    assert b.prior.model_dump(mode="json") == before


def test_derived_value_holds_before_unrepresentable_native_output(materialization):
    b = materialization
    original = b.prepared.publication.checkpoints[0]
    resolution = derived_resolution()
    checkpoint = original.model_copy(update={"field_key": resolution.field_key, "resolution": resolution})
    raw = b.prepared.model_dump(mode="json")
    raw["publication"]["checkpoints"] = [checkpoint.model_dump(mode="json")]
    raw["publication"]["guard"].update(
        checkpoint_digests={str(resolution.field_key):digest(checkpoint)},
        checkpoint_revisions={str(resolution.field_key):checkpoint.revision},
        dependency_revisions={str(pin.field_key):pin.revision for pin in resolution.dependencies},
        dependency_digests={str(pin.field_key):pin.digest for pin in resolution.dependencies})
    raw["basis"].update(field_key=str(resolution.field_key), typed_checkpoint_digest=digest(checkpoint),
        original_typed_checkpoint_digest=digest(checkpoint),dependencies=[{
            "field_key":str(pin.field_key),"revision":pin.revision,"resolution_digest":pin.digest,
            "checkpoint_id":digest("synthetic-native-source:"+str(pin.field_key)),
            "checkpoint_digest":digest("synthetic-native-source-body:"+str(pin.field_key))}
            for pin in resolution.dependencies])
    b.prepared = PreparedNativePublication.model_validate(raw)
    old = b.source.context
    b.source.context = MaterializationRequestV1(digest(b.prepared), old.canonical_snapshot_sha256,
        old.request, old.tool_results)
    before = b.prior.model_dump(mode="json")
    with pytest.raises(PublicationUnavailable, match="canonical_derived_projection_v1_unavailable"):
        produce(b)
    assert b.prior.model_dump(mode="json") == before



def field_work(b, key, state, *, remove=False):
    job = copy.deepcopy(b.binding.registration.job)
    if remove: job["fields"][key].pop("work_state")
    else: job["fields"][key]["work_state"] = state
    reg = b.binding.registration.model_copy(update={"job": job,
        "read_bundle": {**b.binding.registration.read_bundle, "job": job}})
    b.binding = b.binding.model_copy(update={"registration": reg})


@pytest.mark.parametrize("state", ["pending", "researching", "waiting_source", "waiting_policy",
    "operational_failed", "retry_scheduled", "cancelled", "unknown_state", None, True, 1])
def test_supported_prior_sibling_cannot_hide_unfinished_or_unproved_research(materialization, state):
    b = materialization
    assert b.prior.run.fields["county"].state == ValueState.SUPPORTED
    field_work(b, "county", state)
    before = b.prior.model_dump(mode="json")
    with pytest.raises(PublicationUnavailable): produce(b)
    assert b.prior.model_dump(mode="json") == before


def test_missing_sibling_work_state_is_not_inferred_resolved(materialization):
    b = materialization
    field_work(b, "county", None, remove=True)
    with pytest.raises(PublicationUnavailable, match="canonical_field_work_mapping_unproved"):
        produce(b)


def test_sibling_human_need_remains_review_even_when_old_canonical_value_supported(materialization):
    b = materialization
    field_work(b, "county", "waiting_human")
    result = produce(b).result
    assert result.run.disposition == Disposition.REVIEW
    assert "research_human_question:county" in result.run.reasons
    assert result.run.fields["county"] == b.prior.run.fields["county"]


def test_target_job_state_must_agree_with_published_checkpoint(materialization):
    b = materialization
    field_work(b, "country", "waiting_human")
    with pytest.raises(PublicationUnavailable, match="canonical_field_work_mapping_unproved"):
        produce(b)


def test_current_summary_comes_from_new_decision_in_declared_domain(materialization):
    b = materialization
    prior_reasons = list(b.prior.run.reasons)
    result = produce(b).result
    rows = writes(result, b.services.locate, b.services.size, b.principal.user_id)
    record = next(row.variables for row in rows if row.operation == "AppendRecordVersionV2")
    assert record["disposition"] == "cleared" and record["reasonCodes"] == []
    assert record["summary"] == "cleared"
    assert b.prior.run.reasons == prior_reasons


def test_explicit_nonidentity_map_compares_research_target_and_routes_canonical_sibling(materialization):
    # Synthetic map mechanics only; this is not approval of live field semantics.
    b = materialization
    reg = b.binding.registration.model_dump(mode="json")
    mapping = dict(reg["field_mapping"])
    mapping["country"], mapping["county"] = mapping["county"], mapping["country"]
    semantic = copy.deepcopy(reg["semantic_mapping"])
    semantic["field_mapping"] = mapping
    reg.update(field_mapping=mapping, semantic_mapping=semantic, semantic_mapping_digest=digest(semantic))
    b.binding = CanonicalBindingV1.model_validate({**b.binding.model_dump(mode="json"), "registration": reg})
    b.evidence = tuple(item.model_copy(update={"canonical_mapping_digest": digest(semantic)}) for item in b.evidence)
    field_work(b, "country", "resolved")
    field_work(b, "county", "waiting_human")
    before = b.prior.model_dump(mode="json")
    result = produce(b).result
    assert result.run.fields["county"].literal == "Peru"
    assert result.run.fields["country"] == b.prior.run.fields["country"]
    assert "research_human_question:country" in result.run.reasons
    assert "research_human_question:county" not in result.run.reasons
    assert result.run.disposition == Disposition.REVIEW
    assert all(result.run.fields[key] == b.prior.run.fields[key] for key in b.prior.run.fields if key != "county")
    assert b.prior.model_dump(mode="json") == before
