"""Offline hierarchy replay and accepted dependencies; no live source claim."""

import asyncio
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from specimen_digitization.application.domain import FieldValue, LookupStatus, ValueState
from specimen_digitization.application.georef_places import Place, Ref
from specimen_digitization.research_harness.accepted_output import (
    AcceptedCheckpointProofV1, AcceptedOutputProofV1, validation_boundary_pins,
)
from specimen_digitization.research_harness.contracts import (
    ROLE_FIELDS, DependencyPin, EventHypothesis, EventKind, EvidenceItem, FieldCheckpoint,
    FieldKey, FieldResolution, ResearchScope, SourceCoverageReceipt, SourceCoverageState,
    SourceFragment, SourceQuery, SourceResult, SpecialistRequest, SpecialistRole,
    ToolReceipt, WorkState, digest,
)
from specimen_digitization.research_harness.evidence import (
    EvidenceError, assemble_field, temporal_resolutions, validate_resolution,
)
from specimen_digitization.research_harness.geography_context import (
    CollectingContext, accepted_collecting_context, hierarchy_research,
)
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.sources import (
    FixtureSourceTransport, SourceBroker, geolocate_interpretation, insects_registry, result_envelope,
)

PIN = "0" * 64
SCOPE = ResearchScope(organization_id="org", collection_id="insects", specimen_id="specimen",
    job_id="job", generation=1, input_digest=PIN, profile_digest=PIN, sensitive=False)
TOWN = Place(source="nga", record_id="-1143757", name="Yepocapa", names=("San Pedro Yepocapa",),
    country=Ref("GT"), parents=(Ref("GT-04", "Chimaltenango"),), kinds=(Ref("P.PPL"),))


def request(role=SpecialistRole.GEOGRAPHY, fields=None, **kwargs):
    fields = tuple(fields or ROLE_FIELDS[role])
    prompt = resolve_prompt(role, profile_digest=PIN, source_registry_digest=PIN,
        toolset_digest=PIN, model_route="offline-test", output_schema_digest=PIN)
    return SpecialistRequest(scope=SCOPE, role=role, field_keys=fields, prompt=prompt, **kwargs)


def captured(place=TOWN, *, written=None, status=LookupStatus.SUCCESS, field=FieldKey.CITY, places=None):
    """Synthetic durable semantic closure; provider bytes are tested separately."""
    evidence = EvidenceItem(id="source-evidence", kind="historical_gazetteer_exchange",
        source_id=place.source, locator="fixture://captured-source", response_digest=digest("bytes"),
        source_version="offline-fixture-v1", publisher_assertion_id="fixture-only")
    candidates = tuple(json.dumps({**asdict(item), "field_key": str(field), "value": item.name,
        "authority_id": f"{item.source}:{item.record_id}", "authority_role": "historical_candidate",
        "input_literal": written or item.name, "settlement_allowed": False,
        "validation_required": "geolocate"}, sort_keys=True) for item in (places or (place,)))
    result = SourceResult(status=status, candidate_json=candidates, evidence=(evidence,),
        coverage=SourceCoverageReceipt(source_id=place.source, field_key=field,
            state=SourceCoverageState.SEARCHED, source_version="offline-fixture-v1",
            qualification_digest=digest("offline-only policy"), query_digest=digest(written or place.name),
            receipt_ids=(evidence.id,), candidate_count=len(candidates),
            coverage_limit="Offline fixture only", reason=str(status)))
    return bind_receipt(result)


def bind_receipt(result):
    raw = result_envelope(result)
    return result.model_copy(update={"receipt": ToolReceipt(id="fixture-receipt", scope=SCOPE,
        tool_id="source_lookup", source_id=result.coverage.source_id,
        field_keys=(result.coverage.field_key,), effect_id=digest(raw), attempt_ids=("attempt-1",),
        request_digest=digest("request"), binding_digest=digest(SCOPE), outcome=result.status,
        effect_status="completed", evidence_ids=tuple(item.id for item in result.evidence),
        capture_locator="fixture://durable-semantic-result", response_digest=digest(raw),
        result_json=raw, result_digest=hashlib.sha256(raw.encode()).hexdigest())})


def accepted_dependency(key=FieldKey.DATE_VISITED_FROM, text="1948-04-25", *, event_id="collecting-event"):
    role = SpecialistRole.PARTIES if key == FieldKey.COLLECTORS else SpecialistRole.TEMPORAL
    evidence = EvidenceItem(id=f"label:{key}", kind="literal", source_id="offline_fixture",
        locator="fixture://label", response_digest=digest(text), source_version="fixture-v1",
        publisher_assertion_id="fixture-only", excerpt=text)
    fragment = SourceFragment(id=f"fragment:{key}", scope=SCOPE, asset_id="asset", asset_generation="1",
        asset_digest=PIN, label_id="label", region_id="region", observation_id=f"raw-reading:{key}",
        reader="independent-reader", model_id="fixture", prompt_digest=PIN, observation_text=text,
        observation_digest=hashlib.sha256(text.encode()).hexdigest(), start=0, end=len(text), literal=text, order=0)
    event = EventHypothesis(id=event_id, scope=SCOPE, kind=EventKind.COLLECTING,
        fragment_ids=(fragment.id,), evidence_ids=(evidence.id,), reason="Explicit offline collecting-event fixture",
        status="accepted", validator_version="fixture-qualified-event-v1")
    assembly = assemble_field(assembly_id=f"assembly:{key}", scope=SCOPE, field_key=key,
        fragments=(fragment,), event=event)
    original = request(role, (key,), fragments=(fragment,), events=(event,), assemblies=(assembly,),
        evidence=(evidence,), field_revisions={key: 0})
    if key == FieldKey.COLLECTORS:
        resolution = FieldResolution(field_key=key, work_state=WorkState.RESOLVED, value_layer="settled",
            value=FieldValue(state=ValueState.SUPPORTED, literal=text, normalized=text, evidence_ids=[evidence.id]),
            evidence_ids=(evidence.id,), assembly_ids=(assembly.id,), event_id=event.id, reason="Captured collecting literal")
    else:
        resolution = temporal_resolutions(original, event_id=event.id)[0]
    checkpoint = FieldCheckpoint(scope=SCOPE, field_key=key, revision=1, resolution=resolution,
        prompt_digest=original.prompt.digest, model_settings_digest=digest("offline settings"),
        source_registry_digest=original.prompt.source_registry_digest)
    acceptance = AcceptedOutputProofV1(original_request=original, native_run_id=str(uuid4()),
        conversation_id="offline-accepted-context", resolutions=(resolution,), source_results=(), effect_ids=(),
        model_settings_digest=checkpoint.model_settings_digest, **validation_boundary_pins())
    proof = AcceptedCheckpointProofV1(acceptance=acceptance, checkpoints=(checkpoint,))
    return proof, DependencyPin(field_key=key, revision=1, digest=digest(resolution))


def test_country_and_admin_are_derived_only_as_coordinate_free_validation_queries():
    result = hierarchy_research(request(), (captured(),))
    assert [(item.field_key, item.value) for item in result.proposals] == [
        (FieldKey.COUNTRY, "Guatemala"), (FieldKey.PROVINCE_STATE, "Chimaltenango")]
    assert result.unresolved == ((FieldKey.COUNTY, "county_mapping_unqualified"),)
    for proposal, query in zip(result.proposals, result.next_queries, strict=True):
        assert proposal.settlement_allowed is False and proposal.validation_required == "geolocate"
        assert proposal.evidence_ids == ("source-evidence",) and proposal.receipt_ids == ("fixture-receipt",)
        parsed = geolocate_interpretation(query.query_text, query.field_key)
        assert parsed.latitude is parsed.longitude is parsed.radius_km is None
        assert parsed.country == "Guatemala" and parsed.place == "Yepocapa"


@pytest.mark.parametrize(("written", "relation"), [
    ("San Pedro Yepocapa", "captured_alternate_name"),
    ("Yapocapa", "spelling_or_name_hypothesis"),
])
def test_alternate_and_spelling_readings_are_retained_as_nonsettling_hypotheses(written, relation):
    source = captured(written=written)
    result = hierarchy_research(request(), (source,))
    assert all(item.relation == relation and not item.settlement_allowed for item in result.proposals)
    assert json.loads(source.candidate_json[0])["input_literal"] == written
    assert json.loads(result.next_queries[0].query_text)["place"] == "Yepocapa"


def test_namesakes_do_not_choose_the_first_captured_place():
    other = replace(TOWN, record_id="999", country=Ref("PH"), parents=(Ref("PH-DAV", "Davao del Sur"),))
    result = hierarchy_research(request(), (captured(places=(TOWN, other)),))
    assert result.proposals == result.next_queries == ()
    assert set(reason for _, reason in result.unresolved) == {"ambiguous_authority_places"}


def test_partial_label_with_no_captured_country_link_cannot_supply_country_or_admin():
    source = captured(replace(TOWN, country=None), written="Yepocapa, 4800 ft.")
    result = hierarchy_research(request(), (source,))
    assert not result.proposals and not result.next_queries
    assert (FieldKey.COUNTRY, "country_name_unqualified") in result.unresolved


def test_generic_wikidata_parent_name_is_not_a_province_or_county_contract():
    place = replace(TOWN, source="wikidata", record_id="Q123", country=Ref("Q774", "Guatemala"),
        parents=(Ref("Q456", "Chimaltenango"),))
    result = hierarchy_research(request(), (captured(place),))
    assert [item.field_key for item in result.proposals] == [FieldKey.COUNTRY]
    assert (FieldKey.PROVINCE_STATE, "parent_level_unqualified") in result.unresolved
    assert (FieldKey.COUNTY, "county_mapping_unqualified") in result.unresolved


def test_unknown_country_code_is_not_guessed_from_an_admin_name():
    place = replace(TOWN, country=Ref("ZZ"), parents=(Ref("ZZ-01", "Guatemala"),))
    assert not hierarchy_research(request(), (captured(place),)).proposals


@pytest.mark.parametrize("change", [
    {"effect_status": "held_unknown"}, {"effect_status": "sending"},
    {"scope": SCOPE.model_copy(update={"generation": 2})},
    {"field_keys": (FieldKey.COUNTRY,)}, {"evidence_ids": ()},
    {"capture_locator": None}, {"response_digest": None},
])
def test_interrupted_or_unbound_capture_never_becomes_hierarchy_evidence(change):
    source = captured()
    source = source.model_copy(update={"receipt": source.receipt.model_copy(update=change)})
    with pytest.raises(ValueError, match="exact_captured_result_required"):
        hierarchy_research(request(), (source,))


def test_cached_effect_replay_is_identical_and_deduplicated_without_provider_work():
    source = captured()
    expected = hierarchy_research(request(), (source,))
    recovered = SourceResult.model_validate_json(source.model_dump_json())
    assert hierarchy_research(request(), (source, recovered)) == expected
    assert expected.source_effect_ids == (source.receipt.effect_id,)
    altered = recovered.model_copy(update={"candidate_json": (recovered.candidate_json[0].replace("Yepocapa", "Fake"),)})
    with pytest.raises(ValueError, match="exact_captured_result_required"):
        hierarchy_research(request(), (altered,))


def test_captured_provider_interruption_and_absent_source_leave_hierarchy_unresolved():
    failed = captured()
    failed = bind_receipt(failed.model_copy(update={"status": LookupStatus.TIMEOUT,
        "candidate_json": (), "receipt": None,
        "coverage": failed.coverage.model_copy(update={"state": SourceCoverageState.FAILED,
            "candidate_count": 0, "reason": "timeout: captured provider failed"})}))
    result = hierarchy_research(request(), (failed,))
    assert not result.proposals and not result.next_queries
    assert set(reason for _, reason in result.unresolved) == {"source_timeout"}
    absent = hierarchy_research(request(), ())
    assert set(reason for _, reason in absent.unresolved) == {"no_captured_hierarchy"}


def test_accepted_date_and_collector_context_require_exact_pins_and_preserve_raw_evidence():
    date, date_pin = accepted_dependency()
    collector, collector_pin = accepted_dependency(FieldKey.COLLECTORS, "R.D. Mitchell")
    geography = request(dependencies=(date_pin, collector_pin))
    context = accepted_collecting_context(geography, (date, collector))
    assert context.collected_on == "1948-04-25"
    assert {item.value for item in context.values} == {"1948-04-25", "R.D. Mitchell"}
    assert context.proofs[1].acceptance.original_request.fragments[0].input_source == "raw_reading"
    assert context.proofs[1].acceptance.original_request.fragments[0].literal == "R.D. Mitchell"
    with pytest.raises(ValueError, match="unpinned"):
        accepted_collecting_context(request(), (date,))
    with pytest.raises(ValueError, match="changed_or_unpinned"):
        accepted_collecting_context(request(dependencies=(date_pin.model_copy(update={"revision": 2}),)), (date,))
    with pytest.raises(ValueError, match="pinned_proof_missing"):
        accepted_collecting_context(geography, (date,))


def test_a_dictionary_labelled_accepted_and_a_different_generation_are_refused():
    proof, pin = accepted_dependency()
    with pytest.raises(ValueError, match="acceptance_proof_required"):
        accepted_collecting_context(request(dependencies=(pin,)), (proof.model_dump(),))
    geography = request(dependencies=(pin,)).model_copy(update={"scope": SCOPE.model_copy(update={"generation": 2})})
    with pytest.raises(ValueError, match="scope_changed"):
        accepted_collecting_context(geography, (proof,))


def test_competing_collecting_events_do_not_supply_one_location_context():
    date, date_pin = accepted_dependency()
    collector, collector_pin = accepted_dependency(FieldKey.COLLECTORS, "R.D. Mitchell", event_id="other-event")
    with pytest.raises(ValueError, match="competing_collecting_events"):
        accepted_collecting_context(request(dependencies=(date_pin, collector_pin)), (date, collector))


def test_historical_parent_dates_need_accepted_collecting_context():
    place = replace(TOWN, valid_from="1900", valid_to="1950")
    source = captured(place)
    assert not hierarchy_research(request(), (source,)).proposals
    proof, pin = accepted_dependency()
    geography = request(dependencies=(pin,))
    context = accepted_collecting_context(geography, (proof,))
    result = hierarchy_research(geography, (source,), context=context)
    assert len(result.proposals) == 2 and result.dependency_pins == (pin,)
    changed = replace(context, values=(replace(context.values[0], value="1946"),))
    with pytest.raises(ValueError, match="accepted_values_changed"):
        hierarchy_research(geography, (source,), context=changed)
    no_proof = CollectingContext(SCOPE, context.values)
    with pytest.raises(ValueError, match="pinned_proof_missing"):
        hierarchy_research(geography, (source,), context=no_proof)


def test_recorded_renaming_remains_a_hypothesis_pending_modern_validation():
    historical = replace(TOWN, name="Mount McKinley", names=("McKinley",),
        valid_from="1900", valid_to="1950", replaced_by=(Ref("modern-feature", "Mount Talomo"),))
    proof, pin = accepted_dependency()
    geography = request(dependencies=(pin,))
    source = captured(historical, written="McKinley")
    result = hierarchy_research(geography, (source,),
        context=accepted_collecting_context(geography, (proof,)))
    assert result.proposals and all(not item.settlement_allowed for item in result.proposals)
    assert all(json.loads(query.query_text)["place"] == "Mount McKinley" for query in result.next_queries)
    assert json.loads(source.candidate_json[0])["replaced_by"][0]["name"] == "Mount Talomo"


def test_source_parent_link_outside_the_accepted_date_is_not_derived():
    place = replace(TOWN, parents=(Ref("GT-04", "Chimaltenango", start="1951"),))
    proof, pin = accepted_dependency()
    geography = request(dependencies=(pin,))
    result = hierarchy_research(geography, (captured(place),),
        context=accepted_collecting_context(geography, (proof,)))
    assert [item.field_key for item in result.proposals] == [FieldKey.COUNTRY]


def test_raw_unaccepted_date_and_collector_do_not_become_dependency_context():
    geography = request()
    assert accepted_collecting_context(geography, ()).values == ()
    assert not hierarchy_research(geography, (captured(replace(TOWN, valid_to="1950")),)).proposals


def test_a_historical_candidate_cannot_pass_the_direct_scientific_acceptance_boundary():
    source = captured()
    proposal = FieldResolution(field_key=FieldKey.CITY, work_state=WorkState.RESOLVED, value_layer="settled",
        value=FieldValue(state=ValueState.SUPPORTED, normalized="Yepocapa", authority_id="nga:-1143757",
            evidence_ids=["source-evidence"]), evidence_ids=("source-evidence",), reason="A model attempts premature settlement")
    with pytest.raises(EvidenceError, match="historical|settlement|validation"):
        validate_resolution(request(), proposal, (source,))


def test_recorded_nga_same_name_features_supply_unanimous_hierarchy_without_choosing_city():
    fixtures = Path(__file__).parents[1] / "fixtures" / "georeferencing"
    calls = []

    async def read(url, policy):
        params = parse_qs(urlsplit(url).query)
        calls.append(params)
        name = "nga_search.json" if len(calls) == 1 else "nga_features.json" if len(calls) == 2 else "nga_units.json"
        data = json.loads((fixtures / name).read_text())
        rows = data["responses"]["Yepocapa"] if len(calls) == 1 else data["features"]
        if len(calls) == 2:
            rows = [row for row in rows if str(row["ufi"]) in {"-1143757", "-1143758"}]
        if len(calls) == 3:
            rows = [row for row in rows if row["adm1"] == "GT-04"]
        return 200, json.dumps({"features": [{"attributes": row} for row in rows]}).encode()

    registry = insects_registry()
    broker = SourceBroker(registry, transport=FixtureSourceTransport(read))
    query = SourceQuery(source_id="nga", field_key=FieldKey.CITY, query_text="Yepocapa")
    result = asyncio.run(broker._historical_gazetteer(registry.get("nga"), query))
    captured_result = bind_receipt(result)
    research = hierarchy_research(request(), (captured_result,))
    assert len(calls) == 3
    assert len(result.evidence) == 3 and len(result.candidate_json) == 2
    for raw in result.candidate_json:
        candidate = json.loads(raw)
        assert candidate["country"]["id"] == "GT"
        assert candidate["parents"][0]["name"] == "Chimaltenango"
    assert [(item.field_key, item.value) for item in research.proposals] == [
        (FieldKey.COUNTRY, "Guatemala"), (FieldKey.PROVINCE_STATE, "Chimaltenango")]
    assert research.unresolved == ((FieldKey.COUNTY, "county_mapping_unqualified"),)
    assert all(len(item.evidence_ids) == 3 for item in research.proposals)
    assert FieldKey.CITY not in {item.field_key for item in research.proposals}
    assert research.place_authority_ids == ("nga:-1143757", "nga:-1143758")
