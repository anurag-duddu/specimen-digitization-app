"""Placement cannot be fabricated to hide namesakes in a captured source lookup.

Recorded source bodies and real disposable SQLite effects exercise the production
capture adapter offline. Host-only fixture placement is explicitly synthetic;
production authorizes that entry through validate_locked_anchor's command proof.
"""

import asyncio
import copy
import hashlib
import json
from dataclasses import replace

import pytest

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.research_harness.contracts import FieldKey, SourceCoverageState, SourceQuery
from specimen_digitization.research_harness.geography_context import accepted_collecting_context, hierarchy_research
from specimen_digitization.research_harness.persistence import DurableEffectBroker, HeldUnknown
from specimen_digitization.research_harness.source_capture_v2 import CaptureSourceBrokerV2
from specimen_digitization.research_harness.sources import (
    FixtureSourceTransport, SourceBroker, geolocate_interpretation,
)
from test_geolocate_capture import (
    FIXTURES, RECORDED_BODY, RECORDED_URL, YEPOCAPA, effects, lookup, make_rig, saved_envelope,
)
from test_geolocate_validator import APO, REGISTRY, completed_effect, geography_request, label_fragments, query
from test_geography_context import SCOPE as CONTEXT_SCOPE, TOWN, accepted_dependency, captured


def parsed_candidates(result):
    return [json.loads(item) for item in result.candidate_json]


def coordinate_free(interpretation):
    return {key: value for key, value in interpretation.items()
            if key not in {"latitude", "longitude", "radius_km"}}


def cold_broker(rig):
    return CaptureSourceBrokerV2(rig.broker.broker.registry, rig.broker.effects.policies,
        DurableEffectBroker(rig.store, rig.blobs), rig.durable_scope, rig.broker.effects.lease,
        transport=rig.broker.transport.transport, execution_class="offline")


def set_reading(rig, text):
    fragment = rig.request.fragments[0].model_copy(update={"observation_text": text, "literal": text,
        "observation_digest": hashlib.sha256(text.encode()).hexdigest(), "end": len(text)})
    rig.request = rig.request.model_copy(update={"fragments": (fragment,)})


def captured_hierarchy(rig, *, written="Yepocapa"):
    # Exact semantic fixture closure only; provider and ledger capture are
    # exercised by the GEOLocate side of these composed offline tests.
    source = captured(written=written)
    receipt = source.receipt.model_copy(update={"scope": rig.request.scope})
    source = source.model_copy(update={"receipt": receipt})
    rig.broker.broker.trusted_results.append(source)
    return source


def test_coordinate_free_query_keeps_the_returned_point_and_raw_capture(tmp_path):
    rig = make_rig(tmp_path, [RECORDED_BODY])
    place = geolocate_interpretation(json.dumps(YEPOCAPA), FieldKey.CITY)
    assert (place.latitude, place.longitude, place.radius_km) == (None, None, None)
    result = lookup(rig, YEPOCAPA)
    assert result.status == LookupStatus.SUCCESS
    [candidate] = parsed_candidates(result)
    assert (candidate["decimal_latitude"], candidate["decimal_longitude"]) == (14.501946, -90.953956)
    assert "distance_km" not in candidate, "no invented placement means no invented distance"
    _, envelope = saved_envelope(rig, result)
    assert json.loads(envelope.query.query_text) == YEPOCAPA
    assert envelope.responses[0].url == RECORDED_URL


@pytest.mark.parametrize("placement", [
    {"latitude": 14.5, "longitude": -90.95, "radius_km": 15},
    {"latitude": 0.0, "longitude": 0.0, "radius_km": 1},
])
def test_model_placement_is_refused_before_opening_any_effect(tmp_path, placement):
    rig = make_rig(tmp_path, [RECORDED_BODY])
    result = lookup(rig, {**YEPOCAPA, **placement})
    assert result.status == LookupStatus.POLICY
    assert result.coverage.state == SourceCoverageState.UNQUALIFIED
    assert "trusted derivation worker" in result.coverage.reason
    assert result.receipt is None and rig.calls == [] and effects(rig) == []
    assert lookup(rig, YEPOCAPA).status == LookupStatus.SUCCESS


@pytest.mark.parametrize("changed", [
    {"country": "Philippines"}, {"state": "Davao del Sur"},
    {"place": "Mount Apo", "locality": "Mount Apo", "value": "Mount Apo"},
])
def test_unprinted_country_admin_or_place_is_refused_before_effect(tmp_path, changed):
    rig = make_rig(tmp_path, [RECORDED_BODY])
    refused = lookup(rig, {**YEPOCAPA, **changed})
    assert refused.status == LookupStatus.POLICY and "immutable place reading" in refused.coverage.reason
    assert refused.receipt is None and rig.calls == [] and effects(rig) == []


@pytest.mark.parametrize("written", ["Yapocapa", "San Pedro Yepocapa"])
def test_missing_country_admin_and_corrected_place_need_exact_captured_hierarchy(tmp_path, written):
    rig = make_rig(tmp_path, [RECORDED_BODY, RECORDED_BODY, RECORDED_BODY])
    set_reading(rig, written)
    refused = lookup(rig, {**YEPOCAPA, "value": "Chimaltenango"}, field_key=FieldKey.PROVINCE_STATE)
    assert refused.status == LookupStatus.POLICY and effects(rig) == []
    source = captured_hierarchy(rig, written=written)
    research = hierarchy_research(rig.request, (source,))
    province_query = next(item for item in research.next_queries if item.field_key == FieldKey.PROVINCE_STATE)
    result = lookup(rig, json.loads(province_query.query_text), field_key=FieldKey.PROVINCE_STATE)
    assert result.status == LookupStatus.SUCCESS
    assert parsed_candidates(result)[0]["value"] == "Chimaltenango"
    # A country/admin validation query cannot be repurposed to invent a city
    # context. Validate the missing country as well before the sibling lookup.
    city = lookup(rig, YEPOCAPA)
    assert city.status == LookupStatus.POLICY and len(rig.calls) == 1
    country_query = next(item for item in research.next_queries if item.field_key == FieldKey.COUNTRY)
    country = lookup(rig, json.loads(country_query.query_text), field_key=FieldKey.COUNTRY)
    assert country.status == LookupStatus.SUCCESS and len(rig.calls) == 2
    city = lookup(rig, YEPOCAPA)
    assert city.status == LookupStatus.SUCCESS and len(rig.calls) == 3


@pytest.mark.parametrize("broken", ["receipt", "scope", "semantics"])
def test_unproved_or_changed_hierarchy_never_authorizes_derived_context(tmp_path, broken):
    rig = make_rig(tmp_path, [RECORDED_BODY])
    set_reading(rig, "Yapocapa")
    source = captured_hierarchy(rig, written="Yapocapa")
    if broken == "receipt":
        changed = source.model_copy(update={"receipt": None})
    elif broken == "scope":
        changed = source.model_copy(update={"receipt": source.receipt.model_copy(update={
            "scope": source.receipt.scope.model_copy(update={"specimen_id": "another-specimen"})})})
    else:
        changed = source.model_copy(update={"candidate_json": source.candidate_json + source.candidate_json})
    rig.broker.broker.trusted_results[:] = [changed]
    result = lookup(rig, {**YEPOCAPA, "value": "Chimaltenango"}, field_key=FieldKey.PROVINCE_STATE)
    assert result.status == LookupStatus.POLICY and result.receipt is None
    assert rig.calls == [] and effects(rig) == []


def test_date_bounded_hierarchy_requires_host_verified_collecting_context():
    proof, pin = accepted_dependency()
    fragments = tuple(fragment.model_copy(update={"scope": CONTEXT_SCOPE})
                      for fragment in label_fragments("Yapocapa"))
    request = geography_request(scope=CONTEXT_SCOPE, fragments=fragments).model_copy(update={"dependencies": (pin,)})
    context = accepted_collecting_context(request, (proof,))
    source = captured(replace(TOWN, valid_from="1940-01-01", valid_to="1950-12-31"), written="Yapocapa")
    next_query = next(item for item in hierarchy_research(request, (source,), context=context).next_queries
                      if item.field_key == FieldKey.PROVINCE_STATE)
    calls = []

    async def read(url, policy):
        calls.append(url)
        return 200, RECORDED_BODY

    def broker(collecting_context):
        result = SourceBroker(REGISTRY, transport=FixtureSourceTransport(read), effect_dispatch=completed_effect,
                              collecting_context=collecting_context)
        result.trusted_results.append(source)
        return result

    denied = asyncio.run(broker(None).query_source(request, next_query))
    assert denied.status == LookupStatus.POLICY and calls == []
    forged = replace(context, values=())
    denied = asyncio.run(broker(forged).query_source(request, next_query))
    assert denied.status == LookupStatus.POLICY and calls == []
    accepted = asyncio.run(broker(context).query_source(request, next_query))
    assert accepted.status == LookupStatus.SUCCESS and calls == [RECORDED_URL]


@pytest.mark.parametrize("placement", [
    {"latitude": 14.5}, {"longitude": -90.95}, {"radius_km": 15},
    {"latitude": 14.5, "longitude": -90.95},
])
def test_partial_placement_has_an_explicit_correctable_defect(placement):
    with pytest.raises(ValueError, match="requires latitude, longitude and radius_km together"):
        geolocate_interpretation(json.dumps({**YEPOCAPA, **placement}))


def test_coordinate_bearing_saved_effect_does_not_authorize_a_model_placement(tmp_path):
    rig = make_rig(tmp_path, [RECORDED_BODY])
    arguments = {**YEPOCAPA, "latitude": 14.5, "longitude": -90.95, "radius_km": 15}
    source_query = SourceQuery(source_id="geolocate", field_key=FieldKey.CITY, query_text=json.dumps(arguments))
    # Explicit fixture host call: this test exercises an old captured placement,
    # not the separate production derivation-command admission proof.
    first = asyncio.run(rig.broker.broker.query_source(rig.request, source_query, trusted_anchor=True))
    assert first.status == LookupStatus.SUCCESS and parsed_candidates(first)[0]["distance_km"] == 0.5
    before = effects(rig)
    denied = asyncio.run(cold_broker(rig).query_source(rig.request, source_query))
    assert denied.status == LookupStatus.POLICY and denied.receipt is None
    assert effects(rig) == before and rig.calls == [RECORDED_URL]


def test_cold_coordinate_free_replay_reuses_capture_without_a_provider_call(tmp_path):
    rig = make_rig(tmp_path, [RECORDED_BODY])
    first = lookup(rig, YEPOCAPA)
    before = effects(rig)
    source_query = SourceQuery(source_id="geolocate", field_key=FieldKey.CITY, query_text=json.dumps(YEPOCAPA))
    cold = cold_broker(rig)
    assert cold.trusted_results == []
    second = asyncio.run(cold.query_source(rig.request, source_query))
    assert second == first and cold.trusted_results == [first]
    assert effects(rig) == before and rig.calls == [RECORDED_URL]


def body_lookup(body, field_key, interpretation, value):
    calls = []

    async def read(url, policy):
        calls.append(url)
        return 200, body

    broker = SourceBroker(REGISTRY, transport=FixtureSourceTransport(read), effect_dispatch=completed_effect)
    # Explicit synthetic label names for these parser/control cases. Grounding
    # refusals are tested separately with the rig's fixed Guatemala reading.
    request = geography_request(fragments=label_fragments(
        "Mount Apo\nPhilippines\nDavao del Sur\nYepocapa\nChimaltenango\nGuatemala"))
    result = asyncio.run(broker.query_source(request, query(field_key, interpretation, value)))
    return result, calls


def test_coordinate_free_namesakes_stay_ambiguous_until_place_context_is_verified():
    interpretation = coordinate_free(APO)
    # State is ignored by GEOLocate outside the USA. Without an established
    # first-level name, all returned Mount Apo namesakes must remain visible.
    interpretation["state"] = ""
    result, calls = body_lookup((FIXTURES / "apo-modern.json").read_bytes(), FieldKey.CITY,
                                interpretation, "Mount Apo")
    assert result.status == LookupStatus.AMBIGUOUS and len(parsed_candidates(result)) == 3
    assert result.coverage.candidate_count == 5, "the result cap cannot conceal omitted namesakes"
    assert len(calls) == 1 and "1050 km apart" in result.coverage.reason
    assert all("distance_km" not in candidate for candidate in parsed_candidates(result))
    # Naming a different administrative unit is a scientific disagreement;
    # it cannot select a nearby namesake using a model-created point.
    result, _ = body_lookup((FIXTURES / "apo-modern.json").read_bytes(), FieldKey.CITY,
                            coordinate_free(APO), "Mount Apo")
    assert result.status == LookupStatus.NO_MATCH and result.candidate_json == ()
    assert "not 'Davao del Sur'" in result.coverage.reason


def test_partial_label_context_filters_namesakes_by_returned_admin_unit():
    payload = json.loads(RECORDED_BODY)
    namesake = copy.deepcopy(payload["resultSet"]["features"][0])
    namesake["geometry"]["coordinates"] = [-89.0, 16.0]
    namesake["properties"]["debug"] = "|:Adm=OTHER PROVINCE|"
    payload["resultSet"]["features"].append(namesake)
    payload["numResults"] += 1
    body = json.dumps(payload).encode()
    interpretation = {key: value for key, value in YEPOCAPA.items() if key != "value"}
    constrained, _ = body_lookup(body, FieldKey.CITY, interpretation, "Yepocapa")
    assert constrained.status == LookupStatus.SUCCESS
    assert parsed_candidates(constrained)[0]["match_admin"] == "CHIMALTENANGO"
    unconstrained, _ = body_lookup(body, FieldKey.CITY, {**interpretation, "state": ""}, "Yepocapa")
    assert unconstrained.status == LookupStatus.AMBIGUOUS and len(parsed_candidates(unconstrained)) == 3


def test_guatemala_county_remains_unsupported_without_consuming_an_effect(tmp_path):
    rig = make_rig(tmp_path, [RECORDED_BODY])
    result = lookup(rig, {**YEPOCAPA, "value": "Yepocapa"}, field_key=FieldKey.COUNTY)
    assert result.status == LookupStatus.POLICY and "county only inside the USA" in result.coverage.reason
    assert rig.calls == [] and effects(rig) == []


def test_interrupted_provider_remains_held_on_resume_without_resending(tmp_path):
    rig = make_rig(tmp_path, [RECORDED_BODY])
    rig.control["cancel"] = True
    with pytest.raises(asyncio.CancelledError):
        lookup(rig, YEPOCAPA)
    [effect] = effects(rig)
    assert effect["status"] == "held_unknown" and effect["held_micro_usd"] == 1
    assert effect["receipt"] is None and rig.calls == [RECORDED_URL]
    rig.control["cancel"] = False
    source_query = SourceQuery(source_id="geolocate", field_key=FieldKey.CITY, query_text=json.dumps(YEPOCAPA))
    with pytest.raises(HeldUnknown):
        asyncio.run(cold_broker(rig).query_source(rig.request, source_query))
    assert rig.calls == [RECORDED_URL] and effects(rig) == [effect]
