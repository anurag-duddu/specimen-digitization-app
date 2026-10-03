import hashlib
import asyncio
import json

import pytest
from pydantic import ValidationError

from specimen_digitization.application.domain import MANDATORY
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, ROLE_FIELDS, PromptPin, SpecialistRole, ResearchScope, SourceFragment,
    EventHypothesis, EventKind, FieldKey, SpecialistRequest, FragmentRelation,
    RelationKind, WorkState, FieldResolution, ExactSpecimenJoin, SourceQuery,
    SourceCoverageReceipt, SourceCoverageState, ToolReceipt, EmuRecordIdentity,
    IdentityProof, FieldCheckpoint, digest,
    CollectionProfile,
)
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.evidence import (
    EvidenceError, assemble_field, catalog_literal, dts_policy_resolution,
    elevation_resolutions, insects_profile, missing_irn_resolution,
    parse_measurement, settle_elevation, validate_party_assignment,
    validate_resolution,
    parse_temporal, temporal_resolutions,
)
from specimen_digitization.research_harness.sources import (
    MUSEUM_DATASET, SourceBroker, insects_registry, result_envelope,
    validate_destination,
    DurableSourceEffects, FixtureSourceTransport, BoundedHTTPTransport,
)
from specimen_digitization.application.domain import FieldValue, LookupStatus, ValueState

PIN = "0" * 64


def scope(**kwargs):
    return ResearchScope(**{**dict(organization_id="org", collection_id="insects", specimen_id="synthetic",
                         job_id="job", generation=1, input_digest=PIN, profile_digest=PIN,
                         sensitive=False), **kwargs})


def fragment(identifier, text, *, research_scope=None, observation_id=None, label=None, start=0, end=None):
    return SourceFragment(
        id=identifier, scope=research_scope or scope(), asset_id="asset", asset_generation="1",
        asset_digest=PIN, label_id=label or identifier, region_id=label or identifier,
        observation_id=observation_id or identifier, reader="independent-reader",
        model_id="fake", prompt_digest=PIN, observation_text=text,
        observation_digest=hashlib.sha256(text.encode()).hexdigest(), start=start,
        end=len(text) if end is None else end, literal=text[start:end], order=0,
    )


def request(role, fragments=(), events=(), assemblies=(), relations=(), registry=None):
    registry = registry or insects_registry()
    research_scope = fragments[0].scope if fragments else scope()
    prompt = resolve_prompt(role, profile_digest=PIN, source_registry_digest=registry.digest,
                            toolset_digest=PIN, model_route="harness-deepseek", output_schema_digest=PIN)
    return SpecialistRequest(scope=research_scope, role=role, field_keys=ROLE_FIELDS[role], prompt=prompt,
                             fragments=tuple(fragments), events=tuple(events), assemblies=tuple(assemblies),
                             relations=tuple(relations))


def event(fragments, kind=EventKind.COLLECTING, identifier="event"):
    return EventHypothesis(id=identifier, scope=fragments[0].scope, kind=kind,
                           fragment_ids=tuple(item.id for item in fragments), evidence_ids=("role-evidence",),
                           reason="Independently annotated synthetic event", status="accepted", validator_version="gold-v1")


def measurement_request(texts):
    fragments = [fragment(f"f{index}", text) for index, text in enumerate(texts)]
    context = event(fragments)
    assemblies = [assemble_field(assembly_id=f"a{index}", scope=item.scope,
                   field_key=FieldKey.ELEVATION_FROM_FT, fragments=(item,), event=context)
                  for index, item in enumerate(fragments)]
    return request(SpecialistRole.MEASUREMENT, fragments, (context,), assemblies)


def qualified_registry(source_id):
    return insects_registry(qualification_overrides={source_id: {
        "qualification_state": SourceCoverageState.SEARCHED, "qualification_receipt": "independent-fixture-v1",
        "schema_digest": PIN, "source_release": "12.64" if source_id == "field_museum_ipt" else "2026-fixture",
    }})


async def local_effect(request, tool_id, arguments, invoke):
    # Independent test-only execution boundary; no real network or cost.
    raw = await invoke()
    payload = json.loads(raw)
    return ToolReceipt(id="receipt", scope=request.scope, tool_id=tool_id,
                       source_id=arguments["source_id"], field_keys=(arguments["field_key"],),
                       effect_id="effect", attempt_ids=("attempt",), request_digest=digest(arguments),
                       binding_digest=digest(request.scope), outcome=payload["status"], effect_status="completed",
                       result_json=raw, result_digest=hashlib.sha256(raw.encode()).hexdigest())


def test_twenty_fields_have_one_domain_owner():
    owned = [item for values in ROLE_FIELDS.values() for item in values]
    assert set(ALL_FIELDS) == set(MANDATORY) == set(owned)
    assert len(owned) == len(set(owned)) == 20


@pytest.mark.parametrize("role", tuple(SpecialistRole))
def test_each_specialist_prompt_is_resolved_and_pinned(role):
    prompt = resolve_prompt(role, profile_digest=PIN, source_registry_digest=PIN,
                            toolset_digest=PIN, model_route="harness-deepseek",
                            output_schema_digest=PIN)
    assert prompt.role == role
    assert prompt.digest == hashlib.sha256(prompt.text.encode()).hexdigest()
    assert "untrusted" in prompt.text
    assert "waiting_source" in prompt.text
    assert all(str(key) in prompt.text for key in ROLE_FIELDS[role])
    serialized = prompt.model_dump(mode="json")
    serialized["text"] += "tampered"
    with pytest.raises(ValidationError, match="digest"):
        PromptPin.model_validate(serialized)


def test_fragments_refuse_changed_spans_and_cross_specimen_assembly():
    item = fragment("f", "100 ft")
    with pytest.raises(ValidationError, match="substring"):
        SourceFragment.model_validate({**item.model_dump(), "literal": "200 ft"})
    other = fragment("g", "100 ft", research_scope=scope().model_copy(update={"specimen_id": "other"}))
    with pytest.raises(EvidenceError, match="different specimens"):
        assemble_field(assembly_id="bad", scope=item.scope, field_key=FieldKey.ELEVATION_FROM_FT,
                       fragments=(item, other), event=event((item, other)), assertion_kind="complementary")


@pytest.mark.parametrize("separate_label", (False, True))
def test_complementary_units_join_only_through_validated_relation(separate_label):
    if separate_label:
        number, unit = fragment("number", "100"), fragment("unit", "ft")
    else:
        number = fragment("number", "100\nft", observation_id="one", label="one", end=3)
        unit = fragment("unit", "100\nft", observation_id="one", label="one", start=4)
    context = event((number, unit))
    kwargs = dict(assembly_id="assembly", scope=number.scope, field_key=FieldKey.ELEVATION_FROM_FT,
                  fragments=(number, unit), event=context, assertion_kind="complementary")
    with pytest.raises(EvidenceError, match="continuation"):
        assemble_field(**kwargs)
    relation = FragmentRelation(id="relation", scope=number.scope, fragment_ids=(number.id, unit.id),
                                kind=RelationKind.CONTINUATION, event_id=context.id, evidence_ids=("header-unit",),
                                reason="Independent gold unit applicability", proposer_version="proposal-v1",
                                validator_version="gold-v1", status="accepted")
    assembly = assemble_field(**kwargs, relations=(relation,))
    req = request(SpecialistRole.MEASUREMENT, (number, unit), (context,), (assembly,), (relation,))
    settled = settle_elevation(req, assembly_ids=(assembly.id,))
    results = elevation_resolutions(settled)
    assert [item.value.parsed for item in results] == ["30.4800", "30.4800", "100", "100"]
    assert number.literal == "100" and unit.literal == "ft"


def test_ELEV_AGREE_DERIVE_independent_equal_assertions_with_unset_literal():
    req = measurement_request(("100 ft", "100 ft"))
    settled = settle_elevation(req, assembly_ids=("a0", "a1"), source_revision=7)
    results = elevation_resolutions(settled)
    assert len(results) == 4
    assert all(item.value.literal is None for item in results)
    assert [item.value.normalized for item in results] == ["30.48", "30.48", "100.00", "100.00"]
    assert len(results[0].value.verbatim_by_observation) == 2
    for result in results:
        assert validate_resolution(req, result) == result
        assert FieldResolution.model_validate_json(result.model_dump_json()) == result
        if result.derivation:
            assert result.derivation.source_revision == 7
            assert result.derivation.source_assembly_ids == ("a0", "a1")
    conflicting = measurement_request(("100 ft", "200 ft"))
    with pytest.raises(EvidenceError, match="G32"):
        settle_elevation(conflicting, assembly_ids=("a0", "a1"))
    with pytest.raises(EvidenceError, match="every"):
        settle_elevation(conflicting, assembly_ids=("a0",))


def test_ELEV_SIGNED_every_endpoint_and_replay_preserves_sign_and_order():
    for written, expected in (("-25 ft", ("-7.62", "-7.62", "-25.00", "-25.00")),
                              ("-25 to -5 ft", ("-7.62", "-1.52", "-25.00", "-5.00"))):
        req = measurement_request((written,))
        results = elevation_resolutions(settle_elevation(req, assembly_ids=("a0",)))
        assert tuple(item.value.normalized for item in results) == expected
        assert all(str(item.value.parsed).startswith("-") for item in results)
        assert all(FieldResolution.model_validate_json(item.model_dump_json()) == item for item in results)
        assert all(validate_resolution(req, item) == item for item in results)


@pytest.mark.parametrize("bad", ("100", "100 mt", "-5 to -25 ft", "1,000 ft", "25 -- ft", "NaN m"))
def test_ambiguous_or_unwritten_measurements_never_guess(bad):
    with pytest.raises(EvidenceError):
        parse_measurement(bad)


def test_original_uncertainty_and_datum_are_not_display_precision():
    parsed = parse_measurement("~100 ± 2 ft", vertical_datum="unknown")
    assert parsed.qualifiers == ("~",)
    assert parsed.uncertainty == "2" and parsed.precision == "unknown" and parsed.vertical_datum == "unknown"


def test_same_digits_namespace_and_party_roles_cannot_be_substituted():
    assert catalog_literal("FMNHINS 0012345") == "0012345"
    identities = [EmuRecordIdentity(connection="configured", tenant="fmnh", environment="test", module=module, irn=12345)
                  for module in ("ecatalogue", "emultimedia", "eparties")]
    assert len(set(identities)) == 3
    for identity in identities[:2]:
        proof = IdentityProof(identity=identity, scope=scope(), relationship="determiner",
                              identification_row_id="row", receipt_id="receipt", evidence_ids=("e",), qualified_schema_digest=PIN)
        with pytest.raises(EvidenceError, match="eparties"):
            validate_party_assignment(proof, scope())
    proof = IdentityProof(identity=identities[2], scope=scope(), relationship="collector",
                          receipt_id="receipt", evidence_ids=("e",), qualified_schema_digest=PIN)
    with pytest.raises(EvidenceError, match="determiner"):
        validate_party_assignment(proof, scope())


def test_profile_has_exact_exception_and_dts_retains_verbatim():
    profile = insects_profile("org", "subcollection", ancestry=("org", "insects"))
    assert len(profile.fields) == 20
    assert [item.field_key for item in profile.fields if item.exception] == [FieldKey.IDENTIFIED_BY_IRN]
    irn = missing_irn_resolution()
    assert irn.work_state == WorkState.NONBLOCKING_EXCEPTION and irn.value.state == ValueState.UNKNOWN
    assert irn.value.authority_id is None
    dts = dts_policy_resolution("unknown literal meaning")
    assert dts.value.literal == "unknown literal meaning" and dts.work_state == WorkState.WAITING_POLICY


def test_registry_selected_nine_is_distinct_from_qualified_capability():
    registry = insects_registry()
    assert len(registry.policies) == 9
    assert SourceBroker(registry).available_sources(request(SpecialistRole.TAXONOMY)) == ()
    with pytest.raises(ValueError, match="expand"):
        insects_registry(qualification_overrides={"gbif": {"allowed_hosts": ("evil.example",)}})
    for bad in ("https://api.gbif.org/v2/species/match/../private", "https://evil.example/v2/species/match",
                "https://user:password@api.gbif.org/v2/species/match", "http://api.gbif.org/v2/species/match"):
        with pytest.raises(ValueError):
            validate_destination(registry.get("gbif"), bad)


def test_HISTORY_COVERAGE_missing_adapter_is_source_prerequisite():
    req = request(SpecialistRole.TEMPORAL)
    broker = SourceBroker(insects_registry())
    result = asyncio.run(broker.query(req, SourceQuery(source_id="field_museum_ipt", field_key=FieldKey.DATE_IDENTIFIED)))
    assert result.coverage.state == SourceCoverageState.UNQUALIFIED
    assert not result.coverage.exact_join_attempted
    with pytest.raises(ValidationError, match="Exhaustion"):
        SourceCoverageReceipt(source_id="history", field_key=FieldKey.DATE_IDENTIFIED,
                              state=SourceCoverageState.EXHAUSTED, source_version="v1",
                              coverage_limit="none", reason="missing adapter")


class MuseumTransport:
    def __init__(self, count=1, date="1948-09", status=200, catalog="0012345"):
        self.count, self.date, self.status, self.catalog = count, date, status, catalog
        self.urls = []

    async def get(self, url, *, policy):
        validate_destination(policy, url)
        self.urls.append(url)
        if self.status != 200:
            return self.status, b"source inaccessible"
        if "/verbatim" in url:
            fields = {"institutionCode": "FMNH", "collectionCode": "Insects", "catalogNumber": self.catalog,
                      "occurrenceID": "published-synthetic-guid", "recordedBy": "Synthetic Collector"}
            if self.date is not None:
                fields["dateIdentified"] = self.date
            return 200, json.dumps({"key": 1, "fields": fields}).encode()
        return 200, json.dumps({"count": self.count, "results": [{"key": 1, "datasetKey": MUSEUM_DATASET}]}).encode()


def museum_query():
    return SourceQuery(source_id="field_museum_ipt", field_key=FieldKey.DATE_IDENTIFIED,
                       join=ExactSpecimenJoin(dataset_id=MUSEUM_DATASET, institution_code="FMNH",
                                              collection_code="Insects", catalog_number="0012345"))


def test_HISTORY_COVERAGE_exact_publisher_date_resolves_with_precision_provenance():
    registry = qualified_registry("field_museum_ipt")
    req = request(SpecialistRole.TEMPORAL, registry=registry)
    broker = SourceBroker(registry, transport=MuseumTransport(), effect_dispatch=local_effect)
    result = asyncio.run(broker.query(req, museum_query()))
    assert result.status == LookupStatus.SUCCESS and result.coverage.exact_join_proven
    candidate = json.loads(result.candidate_json[0])
    resolution = FieldResolution(field_key=FieldKey.DATE_IDENTIFIED, work_state=WorkState.RESOLVED,
                                 value=FieldValue(state=ValueState.SUPPORTED, parsed=candidate["value"],
                                                  precision="month", authority_id=candidate["authority_id"],
                                                  evidence_ids=[item.id for item in result.evidence]),
                                 value_layer="settled", evidence_ids=tuple(item.id for item in result.evidence),
                                 event_id=candidate["event_id"],
                                 reason="Exact joined determination source")
    assert validate_resolution(req, resolution, (result,)) == resolution
    forged = resolution.model_copy(update={"value": resolution.value.model_copy(update={"parsed": "1946"})})
    with pytest.raises(EvidenceError, match="trusted source"):
        validate_resolution(req, forged, (result,))
    assert "datasetKey=" + MUSEUM_DATASET in broker.transport.urls[0]
    assert result.evidence[0].publisher_assertion_id.startswith("field-museum-insects:")


@pytest.mark.parametrize("transport,expected", ((MuseumTransport(count=2), LookupStatus.AMBIGUOUS),
    (MuseumTransport(catalog="different"), LookupStatus.AMBIGUOUS),
    (MuseumTransport(status=403), LookupStatus.AUTHORIZATION)))
def test_history_duplicate_wrong_join_and_access_failure_cannot_transfer_metadata(transport, expected):
    registry = qualified_registry("field_museum_ipt")
    req = request(SpecialistRole.TEMPORAL, registry=registry)
    result = asyncio.run(SourceBroker(registry, transport=transport, effect_dispatch=local_effect).query(req, museum_query()))
    assert result.status == expected and result.candidate_json == ()
    assert result.coverage.state != SourceCoverageState.EXHAUSTED


def test_missing_joined_date_records_publisher_coverage_not_full_history():
    registry = qualified_registry("field_museum_ipt")
    req = request(SpecialistRole.TEMPORAL, registry=registry)
    result = asyncio.run(SourceBroker(registry, transport=MuseumTransport(date=None), effect_dispatch=local_effect).query(req, museum_query()))
    assert result.status == LookupStatus.NO_MATCH
    assert result.coverage.state == SourceCoverageState.EXHAUSTED
    assert "not full EMu history" in result.coverage.coverage_limit


def test_effect_dispatch_is_required_and_cross_domain_call_denied():
    registry = qualified_registry("field_museum_ipt")
    req = request(SpecialistRole.TEMPORAL, registry=registry)
    transport = MuseumTransport()
    result = asyncio.run(SourceBroker(registry, transport=transport).query(req, museum_query()))
    assert result.status == LookupStatus.POLICY and transport.urls == []
    with pytest.raises(ValueError, match="scope"):
        asyncio.run(SourceBroker(registry).query(request(SpecialistRole.TAXONOMY, registry=registry), museum_query()))


def test_checkpoint_reuse_requires_explicit_two_pins():
    result = missing_irn_resolution()
    with pytest.raises(ValidationError, match="both original"):
        FieldCheckpoint(scope=scope(), field_key=result.field_key, revision=1, resolution=result,
                        prompt_digest=PIN, model_settings_digest=PIN, source_registry_digest=PIN,
                        reused_from_scope_digest=PIN)


def durable_source_fixture(tmp_path, transport):
    from specimen_digitization.research_harness.persistence import (
        BudgetPolicy, DurabilityScope, DurableEffectBroker, ImmutableFileBlobs,
        PinnedRuntime, ResearchStore, SqliteStateBackend,
    )
    registry = qualified_registry("field_museum_ipt")
    req = request(SpecialistRole.TEMPORAL, registry=registry)
    profile = {"id": "insects", "version": "synthetic-v1"}
    req = req.model_copy(update={"scope": req.scope.model_copy(update={"profile_digest": digest(profile)}),
                                "prompt": req.prompt.model_copy(update={"profile_digest": digest(profile)})})
    durability_scope = DurabilityScope("org", "insects", "synthetic", "job", 1, "worker", False)
    backend = SqliteStateBackend(tmp_path / "state.sqlite")
    backend.grant(durability_scope)
    store = ResearchStore(backend, "unchanged-cumulative-program")
    store.initialize(durability_scope, BudgetPolicy(100))
    pins = PinnedRuntime(req.scope.input_digest, profile, {str(req.role): req.prompt.model_dump(mode="json")},
                         {"registry_digest": registry.digest}, {"route": "harness-deepseek"}, {}, "research_harness_v1")
    store.create_job(durability_scope, pins, list(map(str, req.field_keys)))
    lease = store.claim(durability_scope, "owner")
    durable = DurableEffectBroker(store, ImmutableFileBlobs(tmp_path / "blobs"))
    effects = DurableSourceEffects(durable, durability_scope, lease, transport=transport,
                                   execution_class="offline", reservation_micro_usd=1)
    return req, registry, store, durability_scope, effects


def test_actual_durable_source_capture_replays_after_restart_without_query(tmp_path):
    original = MuseumTransport()

    async def read(url, policy):
        return await original.get(url, policy=policy)

    transport = FixtureSourceTransport(read)
    req, registry, store, dscope, effects = durable_source_fixture(tmp_path, transport)
    first_broker = SourceBroker(registry, transport=transport, effect_dispatch=effects)
    first = asyncio.run(first_broker.query(req, museum_query()))
    assert len(original.urls) == 2 and first.receipt.capture_locator
    assert first.receipt.reservation_micro_usd == 1 and first.receipt.settled_micro_usd == 0
    # Fresh source broker instance consumes the same immutable result before HTTP.
    second = asyncio.run(SourceBroker(registry, transport=transport, effect_dispatch=effects).query(req, museum_query()))
    assert first == second and len(original.urls) == 2
    assert store.budget(dscope)["held_micro_usd"] == 0
    effect = store.effect(dscope, first.receipt.effect_id)
    assert effect["status"] == "completed" and len(effect["attempts"]) == 1


def operational_source_checkpoint(request, store, durability_scope, effects, *, receipt=None):
    key = FieldKey.DATE_IDENTIFIED
    current = store.job(durability_scope)["fields"][str(key)]["revision"]
    resolution = FieldResolution(field_key=key, work_state=WorkState.OPERATIONAL_FAILED,
                                 value=FieldValue(state=ValueState.UNRESOLVED),
                                 reason="source_operational_failure")
    checkpoint = FieldCheckpoint(scope=request.scope, field_key=key, revision=current + 1,
                                 resolution=resolution, prompt_digest=request.prompt.digest,
                                 model_settings_digest=digest(store.job(durability_scope)["pins"]["settings"]),
                                 source_registry_digest=request.prompt.source_registry_digest,
                                 effect_receipt_ids=(receipt.effect_id,) if receipt else ())
    return store.checkpoint(durability_scope, effects.lease, str(key), checkpoint.model_dump(mode="json"),
                            expected_revision=current, receipt_ids=checkpoint.effect_receipt_ids)


@pytest.mark.parametrize("status,body,expected", (
    (429, b"rate limited", LookupStatus.RATE_LIMITED),
    (503, b"unavailable", LookupStatus.PROVIDER),
    (200, b"{malformed", LookupStatus.MALFORMED),
))
def test_known_source_failure_replays_once_per_captured_field_investigation(tmp_path, status, body, expected):
    calls = []
    publisher = MuseumTransport()

    async def read(url, policy):
        calls.append(url)
        return (status, body) if len(calls) == 1 else await publisher.get(url, policy=policy)

    transport = FixtureSourceTransport(read)
    req, registry, store, dscope, effects = durable_source_fixture(tmp_path, transport)
    broker = SourceBroker(registry, transport=transport, effect_dispatch=effects)
    first = asyncio.run(broker.query(req, museum_query()))
    explicit_zero = req.model_copy(update={"field_revisions": {FieldKey.DATE_IDENTIFIED: 0}})
    repeated = asyncio.run(broker.query(explicit_zero, museum_query()))
    assert first == repeated and first.status == expected and len(calls) == 1
    prior_effect = store.effect(dscope, first.receipt.effect_id)
    checkpoint = operational_source_checkpoint(req, store, dscope, effects, receipt=first.receipt)
    assert checkpoint["revision"] == 1 and checkpoint["receipt_ids"] == [first.receipt.effect_id]
    captured_retry = req.model_copy(update={"field_revisions": {FieldKey.DATE_IDENTIFIED: 1}})
    second = asyncio.run(broker.query(captured_retry, museum_query()))
    assert second.status == LookupStatus.SUCCESS and len(calls) == 3
    assert second.receipt.effect_id != first.receipt.effect_id
    assert second.receipt.request_digest != first.receipt.request_digest
    assert asyncio.run(broker.query(captured_retry, museum_query())) == second and len(calls) == 3
    assert store.effect(dscope, first.receipt.effect_id) == prior_effect
    assert len(store.effect(dscope, second.receipt.effect_id)["attempts"]) == 1
    assert len(store._read(dscope).state["effects"]) == 2
    assert store.budget(dscope)["held_micro_usd"] == store.budget(dscope)["settled_micro_usd"] == 0


def test_stale_source_capture_is_denied_before_reservation_or_transport(tmp_path):
    from specimen_digitization.research_harness.persistence import StaleWork
    calls = []

    async def read(url, policy):
        calls.append(url)
        return 429, b"rate limited"

    transport = FixtureSourceTransport(read)
    req, registry, store, dscope, effects = durable_source_fixture(tmp_path, transport)
    broker = SourceBroker(registry, transport=transport, effect_dispatch=effects)
    result = asyncio.run(broker.query(req, museum_query()))
    operational_source_checkpoint(req, store, dscope, effects, receipt=result.receipt)
    before = store._read(dscope).state
    for revisions in ({}, {FieldKey.DATE_IDENTIFIED: 0}, {FieldKey.DATE_IDENTIFIED: 2},
                      {FieldKey.DATE_VISITED_FROM: 1}):
        stale = req.model_copy(update={"field_revisions": revisions})
        with pytest.raises(StaleWork, match="^durable_source_field_revision_or_lock_changed$"):
            asyncio.run(broker.query(stale, museum_query()))
    assert len(calls) == 1 and store._read(dscope).state == before


def test_source_invocation_rechecks_revision_after_reservation(tmp_path, monkeypatch):
    from specimen_digitization.research_harness.persistence import StaleWork
    calls = []

    async def read(url, policy):
        calls.append(url)
        return 200, b"{}"

    transport = FixtureSourceTransport(read)
    req, registry, store, dscope, effects = durable_source_fixture(tmp_path, transport)
    reserve_effect = store.reserve_effect

    def advance_after_reservation(*args, **kwargs):
        intent = reserve_effect(*args, **kwargs)
        assert intent["status"] == "reserved"  # positively unsent boundary
        operational_source_checkpoint(req, store, dscope, effects)
        return intent

    monkeypatch.setattr(store, "reserve_effect", advance_after_reservation)
    with pytest.raises(StaleWork, match="^durable_source_field_revision_or_lock_changed$"):
        asyncio.run(SourceBroker(registry, transport=transport, effect_dispatch=effects).query(req, museum_query()))
    assert calls == []
    effect, = store._read(dscope).state["effects"].values()
    assert effect["status"] == "held_unknown" and len(effect["attempts"]) == 1
    assert store.budget(dscope)["held_micro_usd"] == 1


def test_source_human_lock_is_denied_before_reservation(tmp_path):
    from specimen_digitization.research_harness.persistence import PinnedRuntime, StaleWork
    calls = []

    async def read(url, policy):
        calls.append(url)
        return 200, b"{}"

    transport = FixtureSourceTransport(read)
    req, registry, store, dscope, effects = durable_source_fixture(tmp_path, transport)
    store.backend.grant(dscope, role="reviewer")
    pins = PinnedRuntime(**{**store.job(dscope)["pins"], "input_digest": "1" * 64})
    corrected_scope = store.correct_fields(dscope, [str(FieldKey.DATE_IDENTIFIED)],
                                           expected_generation=1, new_pins=pins)
    corrected = req.model_copy(update={"scope": req.scope.model_copy(update={"generation": 2, "input_digest": "1" * 64}),
                                      "field_revisions": {FieldKey.DATE_IDENTIFIED: 1}})
    corrected_effects = DurableSourceEffects(effects.broker, corrected_scope, store.claim(corrected_scope, "review-worker"),
                                            transport=transport, execution_class="offline")
    before = store._read(corrected_scope).state
    with pytest.raises(StaleWork, match="^durable_source_field_revision_or_lock_changed$"):
        asyncio.run(SourceBroker(registry, transport=transport, effect_dispatch=corrected_effects).query(corrected, museum_query()))
    assert calls == [] and store._read(corrected_scope).state == before


def test_unrelated_field_revision_does_not_change_source_identity_or_grant_scope(tmp_path):
    calls = []

    async def read(url, policy):
        calls.append(url)
        return 429, b"rate limited"

    transport = FixtureSourceTransport(read)
    req, registry, store, dscope, effects = durable_source_fixture(tmp_path, transport)
    broker = SourceBroker(registry, transport=transport, effect_dispatch=effects)
    first = asyncio.run(broker.query(req, museum_query()))
    other_revision = req.model_copy(update={"field_revisions": {FieldKey.DATE_VISITED_FROM: 17}})
    assert asyncio.run(broker.query(other_revision, museum_query())) == first
    outside_query = museum_query().model_copy(update={"field_key": FieldKey.COLLECTORS})
    with pytest.raises(ValueError, match="field scope"):
        asyncio.run(broker.query(req, outside_query))
    forged = req.model_copy(update={"field_keys": (FieldKey.COLLECTORS,), "field_revisions": {FieldKey.COLLECTORS: 0}})
    with pytest.raises(ValueError, match="^durable_source_request_contract_changed$"):
        asyncio.run(broker.query(forged, outside_query))
    assert len(calls) == len(store._read(dscope).state["effects"]) == 1


def test_unknown_sent_source_effect_cannot_be_bypassed_with_new_revision(tmp_path):
    from specimen_digitization.research_harness.persistence import HeldUnknown
    calls = []

    async def interrupted(url, policy):
        calls.append(url)
        raise RuntimeError("synthetic interrupted transport")

    transport = FixtureSourceTransport(interrupted)
    req, registry, store, dscope, effects = durable_source_fixture(tmp_path, transport)
    broker = SourceBroker(registry, transport=transport, effect_dispatch=effects)
    with pytest.raises(RuntimeError, match="synthetic interrupted"):
        asyncio.run(broker.query(req, museum_query()))
    with pytest.raises(HeldUnknown, match="no automatic retry"):
        asyncio.run(broker.query(req, museum_query()))
    operational_source_checkpoint(req, store, dscope, effects)
    changed = req.model_copy(update={"field_revisions": {FieldKey.DATE_IDENTIFIED: 1}})
    before = store._read(dscope).state
    with pytest.raises(HeldUnknown, match="^durable_source_field_has_unreconciled_effect$"):
        asyncio.run(broker.query(changed, museum_query()))
    assert len(calls) == 1 and store._read(dscope).state == before
    effect, = before["effects"].values()
    assert effect["status"] == "held_unknown" and effect["held_micro_usd"] == 1
    assert store.budget(dscope)["held_micro_usd"] == 1


def test_unknown_source_cost_blocks_new_effect_and_keeps_cumulative_hold(tmp_path):
    from specimen_digitization.research_harness.persistence import CapturedResult, HeldUnknown
    calls = []

    async def read(url, policy):
        calls.append(url)
        return 200, b"{}"

    transport = FixtureSourceTransport(read)
    req, registry, store, dscope, effects = durable_source_fixture(tmp_path, transport)

    async def unknown_cost(attempt_id, idempotency_key):
        return CapturedResult(typed_payload={"source": "synthetic-prior-source"}, actual_micro_usd=None)

    asyncio.run(effects.broker.execute(dscope, effects.lease, "source_lookup:prior-investigation",
                                      {"field_key": str(FieldKey.DATE_IDENTIFIED)}, 2, unknown_cost,
                                      field_keys=(str(FieldKey.DATE_IDENTIFIED),)))
    before = store._read(dscope).state
    with pytest.raises(HeldUnknown, match="^durable_source_field_has_unreconciled_effect$"):
        asyncio.run(SourceBroker(registry, transport=transport, effect_dispatch=effects).query(req, museum_query()))
    assert calls == [] and store._read(dscope).state == before
    effect, = before["effects"].values()
    assert effect["status"] == "completed" and effect["receipt"]["actual_micro_usd"] is None
    assert store.budget(dscope)["held_micro_usd"] == 2


def test_live_source_transport_cannot_claim_offline_and_hold_blocks_before_network(tmp_path):
    from specimen_digitization.research_harness.persistence import BudgetPolicy

    async def read(url, policy):
        return 200, b"{}"

    req, registry, store, dscope, effects = durable_source_fixture(tmp_path, FixtureSourceTransport(read))
    with pytest.raises(ValueError, match="offline"):
        DurableSourceEffects(effects.broker, dscope, effects.lease, transport=BoundedHTTPTransport(), execution_class="offline")
    live_transport = BoundedHTTPTransport()
    live = DurableSourceEffects(effects.broker, dscope, effects.lease, transport=live_transport, execution_class="live")
    # The store has no live authority and the policy is a HOLD; no network occurs.
    with pytest.raises(PermissionError, match="research_live_authority_required|HOLD"):
        asyncio.run(SourceBroker(registry, transport=live_transport, effect_dispatch=live).query(req, museum_query()))


def test_durable_source_rejects_stale_pins_and_transport_switch(tmp_path):
    async def read(url, policy):
        return await MuseumTransport().get(url, policy=policy)

    transport = FixtureSourceTransport(read)
    req, registry, store, dscope, effects = durable_source_fixture(tmp_path, transport)
    with pytest.raises(ValueError, match="transport"):
        SourceBroker(registry, transport=FixtureSourceTransport(read), effect_dispatch=effects)
    changed = req.model_copy(update={"scope": req.scope.model_copy(update={"input_digest": "1" * 64})})
    with pytest.raises(PermissionError, match="pins changed"):
        asyncio.run(SourceBroker(registry, transport=transport, effect_dispatch=effects).query(changed, museum_query()))
    broker = SourceBroker(registry, transport=transport, effect_dispatch=effects)
    broker.transport = BoundedHTTPTransport()
    with pytest.raises(ValueError, match="transport"):
        asyncio.run(broker.query(req, museum_query()))
    class DisguisedFixture(FixtureSourceTransport):
        pass
    with pytest.raises(ValueError, match="offline"):
        DurableSourceEffects(effects.broker, dscope, effects.lease, transport=DisguisedFixture(read), execution_class="offline")


def test_collecting_date_roman_month_and_G44_derived_endpoint():
    item = fragment("date", "3 IX '46")
    context = event((item,))
    assembly = assemble_field(assembly_id="date-assembly", scope=item.scope,
                              field_key=FieldKey.DATE_VISITED_FROM, fragments=(item,), event=context)
    req = request(SpecialistRole.TEMPORAL, (item,), (context,), (assembly,))
    results = temporal_resolutions(req, event_id=context.id, source_revision=9)
    assert [item.value.parsed for item in results] == ["1946-09-03", "1946-09-03"]
    assert results[1].derivation.rule_id == "G44" and results[1].derivation.source_revision == 9
    for item in results:
        assert validate_resolution(req, item) == item
        assert FieldResolution.model_validate_json(item.model_dump_json()) == item


@pytest.mark.parametrize("bad", ("VI-24-68-7", "1948-99", "1948-02-30", "1-2-48"))
def test_preparation_invalid_and_ambiguous_numeric_dates_cannot_settle(bad):
    with pytest.raises(EvidenceError):
        parse_temporal(bad)


def test_measurements_from_different_events_do_not_combine():
    req = measurement_request(("100 ft", "100 ft"))
    first_event = event((req.fragments[0],), identifier="collecting")
    second_event = event((req.fragments[1],), kind=EventKind.PREPARATION, identifier="preparation")
    assemblies = tuple(assemble_field(assembly_id=f"a{index}", scope=item.scope,
                       field_key=FieldKey.ELEVATION_FROM_FT, fragments=(item,), event=context)
                      for index, (item, context) in enumerate(zip(req.fragments, (first_event, second_event))))
    different = request(SpecialistRole.MEASUREMENT, req.fragments, (first_event, second_event), assemblies)
    with pytest.raises(EvidenceError, match="different events"):
        settle_elevation(different, assembly_ids=("a0", "a1"))


def test_uncertainty_converts_exactly_and_inverse_keeps_exact_operation():
    req = measurement_request(("100 ± 2 ft",))
    results = elevation_resolutions(settle_elevation(req, assembly_ids=("a0",)))
    assert results[0].measurement.converted_uncertainty == "0.6096"
    inverse = measurement_request(("1 m",))
    values = elevation_resolutions(settle_elevation(inverse, assembly_ids=("a0",)))
    feet = next(item for item in values if item.field_key == FieldKey.ELEVATION_FROM_FT)
    assert feet.derivation.operation == "divide" and feet.derivation.exact_operation == "1 / 0.3048"
    assert feet.derivation.decimal_precision == 34


@pytest.mark.parametrize("token", ("VI-24-68-7", "XI-17-76-15", "44B22-84"))
def test_preparation_and_alphanumeric_codes_cannot_clear_as_collectors(token):
    item = fragment("party", token)
    context = event((item,))
    assembly = assemble_field(assembly_id="party-assembly", scope=item.scope, field_key=FieldKey.COLLECTORS,
                              fragments=(item,), event=context)
    req = request(SpecialistRole.PARTIES, (item,), (context,), (assembly,))
    resolution = FieldResolution(field_key=FieldKey.COLLECTORS, work_state=WorkState.RESOLVED,
                                 value=FieldValue(state=ValueState.SUPPORTED, parsed=token),
                                 assembly_ids=(assembly.id,), event_id=context.id, evidence_ids=assembly.evidence_ids,
                                 reason="untrusted model proposition")
    with pytest.raises(EvidenceError, match="code token"):
        validate_resolution(req, resolution)


def test_preparation_event_cannot_supply_even_name_shaped_collector():
    item = fragment("party", "Synthetic Collector")
    context = event((item,), kind=EventKind.PREPARATION)
    assembly = assemble_field(assembly_id="party-assembly", scope=item.scope, field_key=FieldKey.COLLECTORS,
                              fragments=(item,), event=context)
    req = request(SpecialistRole.PARTIES, (item,), (context,), (assembly,))
    resolution = FieldResolution(field_key=FieldKey.COLLECTORS, work_state=WorkState.RESOLVED,
                                 value=FieldValue(state=ValueState.SUPPORTED, parsed=item.literal),
                                 assembly_ids=(assembly.id,), event_id=context.id, evidence_ids=assembly.evidence_ids,
                                 reason="wrong role")
    with pytest.raises(EvidenceError, match="collecting-event"):
        validate_resolution(req, resolution)


def test_museum_invalid_calendar_date_is_ambiguous_no_supported_candidate():
    registry = qualified_registry("field_museum_ipt")
    req = request(SpecialistRole.TEMPORAL, registry=registry)
    result = asyncio.run(SourceBroker(registry, transport=MuseumTransport(date="1948-02-30"), effect_dispatch=local_effect).query(req, museum_query()))
    assert result.status == LookupStatus.AMBIGUOUS and result.candidate_json == ()


def test_history_value_must_cite_its_exact_field_source_receipt():
    registry = qualified_registry("field_museum_ipt")
    req = request(SpecialistRole.TEMPORAL, registry=registry)
    broker = SourceBroker(registry, transport=MuseumTransport(), effect_dispatch=local_effect)
    result = asyncio.run(broker.query(req, museum_query()))
    candidate = json.loads(result.candidate_json[0])
    party_req = request(SpecialistRole.PARTIES, registry=registry)
    party_query = museum_query().model_copy(update={"field_key": FieldKey.COLLECTORS})
    party_result = asyncio.run(broker.query(party_req, party_query))
    wrong_evidence = tuple(item.id for item in party_result.evidence)
    resolution = FieldResolution(field_key=FieldKey.DATE_IDENTIFIED, work_state=WorkState.RESOLVED,
                                 value=FieldValue(state=ValueState.SUPPORTED, parsed=candidate["value"], precision="month",
                                                  authority_id=candidate["authority_id"], evidence_ids=list(wrong_evidence)),
                                 value_layer="settled", event_id=candidate["event_id"], evidence_ids=wrong_evidence,
                                 reason="cross-field receipt misuse")
    with pytest.raises(EvidenceError, match="exact source/field"):
        validate_resolution(req, resolution, (result, party_result))


def test_selected_supporting_sources_return_attributed_candidates_without_g23_deciding_role():
    for source_id, release, payload in (
        ("global_names_verifier", "gnv-fixture-release", {"metadata": {}, "names": [{"name": "Chironomus", "bestResult": {
            "dataSourceId": 7, "currentRecordId": "name-id", "currentName": "Chironomus",
            "dataSourceTitleShort": "independent fixture", "entryDate": "2026-01-01", "matchType": "Exact"}}]}),
        ("catalogue_of_life", "316321", {"total": 1, "result": [{"usage": {"datasetKey": 316321,
            "id": "N1", "label": "Chironomus", "status": "ACCEPTED", "name": {"scientificName": "Chironomus", "rank": "GENUS"}}}]}),
    ):
        registry = insects_registry(qualification_overrides={source_id: {
            "qualification_state": SourceCoverageState.SEARCHED, "qualification_receipt": "independent-fixture-v1",
            "schema_digest": PIN, "source_release": release}})
        req = request(SpecialistRole.TAXONOMY, registry=registry)
        async def read(url, policy):
            return 200, json.dumps(payload).encode()
        result = asyncio.run(SourceBroker(registry, transport=FixtureSourceTransport(read), effect_dispatch=local_effect).query(
            req, SourceQuery(source_id=source_id, field_key=FieldKey.TAXON, query_text="Chironomus")))
        assert result.status == LookupStatus.SUCCESS
        candidate = json.loads(result.candidate_json[0])
        assert candidate["authority_role"] == "supports" and candidate["value"] == "Chironomus"
        proposal = FieldResolution(field_key=FieldKey.TAXON, work_state=WorkState.RESOLVED,
            value=FieldValue(state=ValueState.SUPPORTED, parsed=candidate["value"], authority_id=candidate["authority_id"],
                             evidence_ids=[item.id for item in result.evidence]), value_layer="settled",
            evidence_ids=tuple(item.id for item in result.evidence), reason="unsupported precedence")
        with pytest.raises(EvidenceError, match="G23"):
            validate_resolution(req, proposal, (result,))


def test_nonblocking_exception_cannot_hide_a_guessed_numeric_value():
    unresolved = missing_irn_resolution()
    with pytest.raises(ValidationError, match="unresolved scientific"):
        FieldResolution.model_validate({**unresolved.model_dump(), "value": FieldValue(state=ValueState.UNKNOWN, parsed="12345").model_dump()})


def test_scientific_measurement_digest_survives_actual_checkpoint_revision_assignment():
    req = measurement_request(("-25 to -5 ft",))
    original = elevation_resolutions(settle_elevation(req, assembly_ids=("a0",), source_revision=0))
    assigned = elevation_resolutions(settle_elevation(req, assembly_ids=("a0",), source_revision=1))
    native = {item.field_key: item for item in assigned if item.derivation is None}
    for old, new in zip(original, assigned):
        assert validate_resolution(req, new) == new
        if new.derivation is not None:
            assert old.derivation.source_digest == new.derivation.source_digest
            assert new.derivation.source_revision == new.dependencies[0].revision == 1
            assert new.dependencies[0].digest == digest(native[new.dependencies[0].field_key])
    to_metres = next(item for item in assigned if item.field_key == FieldKey.ELEVATION_TO_M)
    assert to_metres.dependencies[0].field_key == FieldKey.ELEVATION_TO_FT


def test_field_revisions_default_empty_and_are_strict_scoped_immutable_captures():
    original = request(SpecialistRole.GEOGRAPHY)
    assert original.field_revisions == {}
    assert "field_revisions" in original.model_dump(mode="json")
    payload = {**original.model_dump(mode="json"), "field_revisions": {"country": 0, "city": 7}}
    captured = SpecialistRequest.model_validate(payload)
    assert captured.field_revisions == {FieldKey.COUNTRY: 0, FieldKey.CITY: 7}
    assert SpecialistRequest.model_validate_json(captured.model_dump_json()) == captured
    assert captured.model_copy(deep=True) == captured
    with pytest.raises(TypeError, match="immutable"):
        captured.field_revisions[FieldKey.COUNTRY] = 1
    with pytest.raises(TypeError, match="immutable"):
        captured.field_revisions.update({FieldKey.COUNTRY: 1})
    for invalid in (-1, 1.0, "1", True):
        with pytest.raises(ValidationError):
            SpecialistRequest.model_validate({**payload, "field_revisions": {"country": invalid}})


def test_field_revision_role_escape_is_denied_on_journal_style_revalidation():
    original = request(SpecialistRole.GEOGRAPHY)
    forged = original.model_copy(update={"field_revisions": {FieldKey.TAXON: 0}})
    with pytest.raises(ValidationError, match="requested owned fields"):
        SpecialistRequest.model_validate(forged.model_dump(mode="json"))
    subset = original.model_copy(update={"field_keys": (FieldKey.COUNTRY,), "field_revisions": {FieldKey.CITY: 0}})
    with pytest.raises(ValidationError, match="requested owned fields"):
        SpecialistRequest.model_validate(subset.model_dump(mode="json"))


def test_insects_profile_cannot_drop_mandatory_fields_to_false_clear():
    profile = insects_profile("org", "insects")
    for key in ALL_FIELDS:
        fields = [item.model_copy(update={"mandatory": False}) if item.field_key == key else item for item in profile.fields]
        with pytest.raises(ValidationError, match="all twenty fields mandatory"):
            CollectionProfile.model_validate({**profile.model_dump(mode="json"), "fields": [item.model_dump(mode="json") for item in fields]})
    assert all(item.mandatory for item in profile.fields)
    assert next(item for item in profile.fields if item.field_key == FieldKey.IDENTIFIED_BY_IRN).exception is not None


def test_competing_source_checkpoint_during_sending_is_held(tmp_path,monkeypatch):
    from specimen_digitization.research_harness.persistence import HeldUnknown
    calls = []
    async def read(url,policy):
        calls.append(url)
        return 200,b"{}"
    transport = FixtureSourceTransport(read)
    req,registry,store,dscope,effects = durable_source_fixture(tmp_path,transport)
    validate_dispatch = store.validate_dispatch
    def competing_after_sending(*args):
        validate_dispatch(*args)
        operational_source_checkpoint(req,store,dscope,effects)
    monkeypatch.setattr(store,"validate_dispatch",competing_after_sending)
    with pytest.raises(HeldUnknown,match="in-flight field effect"):
        asyncio.run(SourceBroker(registry,transport=transport,effect_dispatch=effects).query(req,museum_query()))
    assert calls == []
    assert store.job(dscope)["fields"][str(FieldKey.DATE_IDENTIFIED)]["revision"] == 0
    effect, = store._read(dscope).state["effects"].values()
    assert effect["status"] == "held_unknown" and len(effect["attempts"]) == 1
    assert store.budget(dscope)["held_micro_usd"] == 1
