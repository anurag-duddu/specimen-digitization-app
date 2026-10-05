"""Proposal reads require real local retained effect/checkpoint fences, not model proof."""
import copy
import json

import pytest

from specimen_digitization.application.domain import FieldValue
from specimen_digitization.research_harness.contracts import (
    EvidenceItem, FieldKey, FieldResolution, HumanQuestion, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.derivation_contracts import DerivationCommand
from specimen_digitization.research_harness.derivation_service import ResearchDerivationService
from specimen_digitization.research_harness.persistence import StaleWork
from test_derivation_contracts import command_data


def build_computed(tmp_path, command=None, candidate_changes=None):
    """Actual capture producer and immutable proof; synthetic adapter/command authority.

    The provider body and spatial adapter below are explicit offline fixtures.
    The V2 broker, locked-anchor admission, captured envelopes, computation
    verifier and checkpoint journal are the real implementation. This helper
    does not claim native SQL, live GEOLocate or qualified dataset execution.
    """
    import asyncio
    from types import SimpleNamespace

    from specimen_digitization.research_harness.contracts import (
        ALL_FIELDS, ROLE_FIELDS, CollectionProfile, FieldProfile, ResearchScope,
        SourceQuery, SpecialistRequest,
    )
    from specimen_digitization.research_harness.derivation_contracts import DERIVATION_RULE_VERSION
    from specimen_digitization.research_harness.georeferencing import (
        DerivationProposal as SpatialProposal, DerivationResult, Georeference, SettledLocationInput,
    )
    from specimen_digitization.research_harness.journal import DurableResearchJournal
    from specimen_digitization.research_harness.persistence import (
        BudgetPolicy, DurabilityScope, DurableEffectBroker, ImmutableFileBlobs,
        PinnedRuntime, ResearchStore, SqliteStateBackend,
    )
    from specimen_digitization.research_harness.prompts import resolve_prompt
    from specimen_digitization.research_harness.source_capture_v2 import (
        CaptureSourceBrokerV2, RegisteredCapturePolicyV2,
    )
    from specimen_digitization.research_harness.sources import (
        GEOLOCATE_QUALIFICATION, FixtureSourceTransport, canonical_json, insects_registry,
    )

    command = DerivationCommand.model_validate(command or command_data())
    changes = candidate_changes or {}
    target = FieldKey.CITY if FieldKey.CITY in command.requested_fields else command.requested_fields[0]
    inputs = tuple(SettledLocationInput(item.field_key, item.value, item.evidence_ids,
        item.revision, item.authority_id) for item in command.inputs)
    anchor = next((item for item in inputs if item.field_key == FieldKey.COUNTRY), inputs[0])
    country = next((item.value for item in inputs if item.field_key == FieldKey.COUNTRY),
                   "USA" if anchor.field_key == FieldKey.COUNTY else "Philippines")
    place = anchor.value if anchor.field_key == FieldKey.CITY else "Fixture Place"
    query = SourceQuery(source_id="geolocate", field_key=anchor.field_key,
        query_text=canonical_json({"country": country, "state": "Fixture State",
            "locality": place, "place": place, "value": anchor.value,
            "latitude": 6.9, "longitude": 125.2, "radius_km": 1}))
    registry = insects_registry(qualification_overrides={"geolocate": GEOLOCATE_QUALIFICATION,
        "georeference_spatial": {"qualification_state": "searched",
            "qualification_receipt": "offline fixture adapter registration",
            "schema_digest": digest("fixture-spatial-schema"), "source_release": DERIVATION_RULE_VERSION}})
    policies = {name: RegisteredCapturePolicyV2(source_id=name,
        source_policy_digest=digest(registry.get(name)), kind=kind,
        owner_registration_digest=digest("fixture owner"),
        owner_registration_origin="explicit offline fixture registration", maximum_responses=1)
        for name, kind in (("geolocate", "full_response"), ("georeference_spatial", "computed"))}
    profile = CollectionProfile(id="fixture-derived", version="1", organization_id="org-test",
        collection_id="collection-test", ancestry=(), knowledge_version="fixture",
        fields=tuple(FieldProfile(field_key=key) for key in ALL_FIELDS))
    scope = ResearchScope(organization_id="org-test", collection_id="collection-test",
        specimen_id="specimen-test", job_id="derived-" + command.id, generation=1,
        input_digest=command.source_snapshot_sha256, profile_digest=digest(profile), sensitive=False)
    requests = {role: SpecialistRequest(scope=scope, role=role, field_keys=keys,
        field_revisions={key: 0 for key in keys}, prompt=resolve_prompt(role,
            profile_digest=scope.profile_digest, source_registry_digest=registry.digest,
            toolset_digest=digest("fixture-tools"), model_route="function-fixture",
            output_schema_digest=digest(FieldResolution.model_json_schema())))
        for role, keys in ROLE_FIELDS.items()}
    settings = {"max_tokens": 128}
    pins = PinnedRuntime(scope.input_digest, profile.model_dump(mode="json"),
        {str(role): request.prompt.model_dump(mode="json") for role, request in requests.items()},
        {"registry_digest": registry.digest,
            "registry_policies": [policy.model_dump(mode="json") for policy in registry.policies], "capture_policies": {
            key: policy.model_dump(mode="json") for key, policy in policies.items()}},
        {str(role): {"route": "function-fixture"} for role in requests}, settings, "specialist_harness_v2")
    durable = DurabilityScope(scope.organization_id, scope.collection_id, scope.specimen_id,
        scope.job_id, scope.generation, "offline-reviewer", False)
    tmp_path.mkdir(parents=True, exist_ok=True)
    backend = SqliteStateBackend(tmp_path / "research.sqlite")
    backend.grant(durable, role="reviewer")
    store = ResearchStore(backend, "disposable-computed-fixture")
    store.initialize(durable, BudgetPolicy(100))
    store.create_job(durable, pins, list(ALL_FIELDS), record_revision=command.queued_revision,
        dependencies={"derivation_request_id": command.id})

    def lock_inputs(state, _):
        for key in command.human_locked_fields:
            state["jobs"][durable.key]["fields"][str(key)]["locked"] = True
    store._mutate(durable, lock_inputs)
    lease = store.claim(durable, "offline-worker", ttl_seconds=300)
    blobs = ImmutableFileBlobs(tmp_path / "captures")
    journal = DurableResearchJournal(store, durable, lease)

    class FixtureCommandContext:
        """Synthetic worker authority seam; retained-envelope verifier is never mocked."""
        def verify_current(self, request, command_digest, settled_inputs, requested_fields):
            current = store.job(durable)
            assert command_digest == digest(command) and request.scope == scope
            assert tuple(settled_inputs) == inputs and tuple(requested_fields) == command.requested_fields
            assert current["record_revision"] == command.queued_revision
            assert current["dependencies"]["derivation_request_id"] == command.id

        def verify_locked_anchor(self, request, source_query, source_anchor, command_digest):
            self.verify_current(request, command_digest, inputs, command.requested_fields)
            assert source_anchor == anchor and source_query == query
            assert store.job(durable)["fields"][str(anchor.field_key)]["locked"] is True

    class FixtureSpatialAdapter:
        def derive_rest(self, **arguments):
            assert arguments["settled_inputs"] == inputs
            validation = arguments["validation"]
            assert validation.status == "success" and validation.receipt is not None
            dataset = EvidenceItem(id="dataset:" + digest("fixture-boundary"), kind="qualified_dataset",
                source_id="georeference_spatial", source_version=DERIVATION_RULE_VERSION,
                locator="fixture://spatial-dataset", response_digest=digest("fixture-boundary"),
                publisher_assertion_id="explicit-synthetic-dataset")
            evidence = (*validation.evidence, dataset)
            evidence_ids = tuple(dict.fromkeys([*(eid for item in inputs for eid in item.evidence_ids),
                *(item.id for item in evidence)]))
            fields = tuple(str(item.field_key) for item in inputs)
            rule = changes.get("rule_version", DERIVATION_RULE_VERSION)
            georef = Georeference(latitude=6.9, longitude=125.2, uncertainty_m=10000.,
                footprint_dataset="synthetic-boundary-v1", footprint_id="fixture-unit",
                authority_ids=("fixture:boundary",), input_fields=fields, evidence_ids=evidence_ids,
                tool_call_id=arguments["tool_call_id"], simplification_margin_m=1.,
                method="Explicit synthetic adapter fixture", version=rule)
            data = {"field_key": target, "value": "A named municipality", "input_fields": fields,
                "input_revisions": tuple((str(item.field_key), item.revision) for item in inputs),
                "evidence_ids": evidence_ids, "authority_id": "boundary:place",
                "dataset_ids": ("synthetic-boundary-v1",), "tool_call_id": arguments["tool_call_id"],
                "rule_version": rule, **changes}
            return DerivationResult(status="success", reason="Explicit synthetic adapter computation",
                georeference=georef, proposals=(SpatialProposal(**data),), evidence=evidence)

    calls = []
    async def response(url, policy):
        calls.append(url)
        assert policy.id == "geolocate"
        body = {"engineVersion": "explicit-offline-fixture", "numResults": 1,
            "resultSet": {"type": "FeatureCollection", "crs": {"type": "EPSG", "properties": {"code": 4326}},
                "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [125.2, 6.9]},
                    "properties": {"parsePattern": place, "precision": "High", "score": 100,
                        "debug": ":Adm=" + anchor.value}}]}}
        return 200, canonical_json(body).encode()

    broker = CaptureSourceBrokerV2(registry, policies, DurableEffectBroker(store, blobs), durable, lease,
        transport=FixtureSourceTransport(response), execution_class="offline",
        georeferencing_adapter=FixtureSpatialAdapter(), derivation_context=FixtureCommandContext())
    anchor_request = requests[SpecialistRole.GEOGRAPHY].model_copy(update={
        "field_keys": (anchor.field_key,), "field_revisions": {anchor.field_key: 0}})
    validation = asyncio.run(broker.validate_locked_anchor(anchor_request, query,
        anchor=anchor, command_digest=digest(command)))
    assert validation.status == "success" and len(calls) == 1
    role = next(role for role, keys in ROLE_FIELDS.items() if target in keys)
    target_request = requests[role].model_copy(update={"field_keys": (target,), "field_revisions": {target: 0}})
    result = asyncio.run(broker.derive_spatial_from_trusted_inputs(target_request, field_key=target,
        country={"philippines": "PH", "ph": "PH", "guatemala": "GT", "gt": "GT"}[country.strip().lower()],
        validation=validation, settled_inputs=inputs, requested_fields=command.requested_fields,
        verbatim_locality="Fixture Place", label_has_elevation=False,
        tool_call_id=validation.receipt.id, command_digest=digest(command)))
    effect = result.receipt.effect_id
    waiting = FieldResolution(field_key=target, work_state=WorkState.WAITING_HUMAN,
        value=FieldValue(state="unresolved"), source_coverage=(result.coverage,),
        evidence_ids=tuple(item.id for item in result.evidence),
        question=HumanQuestion(field_key=target, reason="derived_proposal", coverage=(result.coverage,),
            evidence_ids=tuple(item.id for item in result.evidence),
            question="Review the derived proposal before choosing a value."),
        reason="Computed proposal awaits explicit human review")
    asyncio.run(journal.commit(target_request, (waiting,), receipt_ids=(effect,),
        model_settings_digest=digest(settings)))
    document = store._read(durable)
    job = document.state["jobs"][durable.key]
    status = {"request_id": command.id, "status": "completed",
        "checkpoint_ids": [job["fields"][str(target)]["checkpoint"]["id"]]}
    job["dependencies"]["derivation_result"] = status
    rig = SimpleNamespace(journal=journal, scope=scope, capture_blobs=blobs, command=command,
        validation=validation, requests=requests, source_calls=calls)
    return rig, document, job, status, effect


@pytest.fixture
def computed(tmp_path, request):
    return build_computed(tmp_path, candidate_changes=getattr(request, "param", None))


def read(computed):
    rig, document, job, status, _ = computed
    return ResearchDerivationService._proposals(rig.command,
        document, rig.journal.scope, job, status, capture_blobs=rig.capture_blobs)


def test_real_source_capture_and_checkpoint_produce_editable_derived_proposal(computed):
    from specimen_digitization.research_harness.candidate_selection import retained_candidate

    before = copy.deepcopy(computed[1].state)
    proposal, = read(computed)
    assert proposal.value_layer == "derived" and proposal.selection_id is not None
    assert proposal.field_key == FieldKey.CITY and proposal.input_revisions == ((FieldKey.COUNTRY, 5),)
    assert proposal.effect_id == computed[-1]
    rig, document, _, _, _ = computed
    choice = retained_candidate(document, rig.journal.scope.key, proposal.field_key, proposal.selection_id)
    evidence = choice["source_result"]["evidence"]
    assert [item["kind"] for item in evidence][-2:] == ["qualified_dataset", "computed_derivation_result"]
    assert choice["evidence_id"] == evidence[-1]["id"]
    assert computed[1].state == before


@pytest.mark.parametrize("tamper", ["checkpoint", "scope", "wrong_revision", "wrong_inputs", "locked", "paused", "uncited"])
def test_stale_or_unproved_native_proposal_is_never_returned(computed, tamper):
    rig, document, job, status, effect_id = computed
    checkpoint = job["fields"]["city"]["checkpoint"]
    if tamper == "checkpoint":
        status["checkpoint_ids"] = ["f" * 64]
    elif tamper == "scope":
        document.state["effects"][effect_id]["scope"]["specimen_id"] = "other"
    elif tamper in {"wrong_revision", "wrong_inputs"}:
        payload = document.state["effects"][effect_id]["receipt"]["typed_payload"]
        candidate = json.loads(payload["candidate_json"][0])
        candidate["input_revisions"] = [["country", 4 if tamper == "wrong_revision" else 5]]
        if tamper == "wrong_inputs":
            candidate["input_fields"] = ["province_state"]
        payload["candidate_json"][0] = json.dumps(candidate)
    elif tamper == "locked":
        job["fields"]["city"]["locked"] = True
    elif tamper == "paused":
        job["paused"] = True
    else:
        checkpoint["receipt_ids"] = []
    if tamper == "uncited":
        assert read(computed) == ()
    else:
        with pytest.raises((StaleWork, ValueError, PermissionError)):
            read(computed)


def test_unresolved_metadata_cannot_become_a_field_proposal(computed):
    _, document, _, _, effect_id = computed
    payload = document.state["effects"][effect_id]["receipt"]["typed_payload"]
    payload["candidate_json"] = [json.dumps({"field_key":"city", "settlement_allowed":False,
        "georeference":{"latitude":14.3,"longitude":-90.9,"uncertainty_m":10000}})]
    assert read(computed) == ()


def test_internally_consistent_other_rule_is_not_a_current_request_proposal(computed, monkeypatch):
    from specimen_digitization.research_harness import derivation_service

    monkeypatch.setattr(derivation_service, "DERIVATION_RULE_VERSION", "retrospective-georeferencing-next")
    before = copy.deepcopy(computed[1].state)
    with pytest.raises(StaleWork, match="derivation_rule_changed"):
        read(computed)
    assert computed[1].state == before


def test_real_capture_is_bound_to_the_full_command_even_when_inputs_and_tool_id_match(computed):
    rig, document, job, status, _ = computed
    different = rig.command.model_copy(update={"reason": "Another request with same inputs"})
    assert different.inputs == rig.command.inputs and different.id == rig.command.id
    with pytest.raises(ValueError, match="retained_spatial_derivation_capture_unproved"):
        ResearchDerivationService._proposals(different, document, rig.journal.scope, job, status,
            capture_blobs=rig.capture_blobs)


@pytest.mark.parametrize("capture", ["capture", "raw_capture", "validator_body"])
def test_immutable_computation_and_original_validator_bytes_are_required(computed, capture):
    rig, document, job, status, effect_id = computed
    if capture == "validator_body":
        from specimen_digitization.research_harness.persistence import BlobRef
        from specimen_digitization.research_harness.source_capture_v2 import SourceRequestEnvelopeV2

        validation_effect = document.state["effects"][rig.validation.receipt.effect_id]
        envelope = SourceRequestEnvelopeV2.model_validate_json(
            rig.capture_blobs.get(BlobRef(**validation_effect["receipt"]["raw_capture"])))
        broken_locator = envelope.responses[0].body.locator
    else:
        broken_locator = document.state["effects"][effect_id]["receipt"][capture]["locator"]

    class CorruptFixtureRead:
        def get(self, reference):
            original = rig.capture_blobs.get(reference)
            return original + b"corrupt" if reference.locator == broken_locator else original

    with pytest.raises(ValueError, match="retained_spatial_derivation_capture_unproved"):
        ResearchDerivationService._proposals(rig.command, document, rig.journal.scope, job, status,
            capture_blobs=CorruptFixtureRead())
