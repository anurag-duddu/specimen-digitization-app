"""GEOLocate validates the geography historian's interpretation (owner G-geo-1..3).

The fixtures are recorded responses of paced live probes for the ten pilot localities
(subjects 105526321..105526330); manifest.json names each request URL and time.
"""

import asyncio
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from specimen_digitization.application.domain import FieldValue, LookupStatus, ValueState
from specimen_digitization.research_harness.contracts import (
    ROLE_FIELDS, FieldKey, FieldResolution, ResearchScope, SourceCoverageState, SourceQuery,
    SpecialistRequest, SpecialistRole, ToolReceipt, WorkState, digest,
)
from specimen_digitization.research_harness.evidence import EvidenceError, validate_resolution
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.sources import (
    GEOLOCATE_QUALIFICATION, BoundedHTTPTransport, FixtureSourceTransport, RequestPacer,
    SourceBroker, geolocate_interpretation, insects_registry, validate_destination,
)

FIXTURES = Path(__file__).parent / "fixtures" / "geolocate"
MANIFEST = {item["file"]: item for item in json.loads((FIXTURES / "manifest.json").read_text())["fixtures"]}
PIN = "0" * 64
REGISTRY = insects_registry(qualification_overrides={"geolocate": GEOLOCATE_QUALIFICATION})
YEPOCAPA = {"country": "Guatemala", "state": "Chimaltenango", "locality": "Yepocapa", "place": "Yepocapa",
            "latitude": 14.5, "longitude": -90.95, "radius_km": 15}
APO = {"country": "Philippines", "state": "Davao del Sur", "locality": "Mount Apo", "place": "Mount Apo",
       "latitude": 6.99, "longitude": 125.27, "radius_km": 25}
MCKINLEY = {"country": "Philippines", "state": "Davao del Sur", "locality": "Mount McKinley",
            "place": "Mount McKinley", "latitude": 7.05, "longitude": 125.35, "radius_km": 40}
APO_LABEL = "E. slope Mt. Apo, Davao Prov., Mindanao, P.I."
MCKINLEY_LABEL = "E. slope Mt. McKinley, Davao Prov., Mindanao, P.I."
YEPOCAPA_LABEL = "Yepocapa, Mun. Yepocapa, chimaltenago, Guatemala"


def verbatim(interpretation, label):
    # The recorded verbatim probes sent the label locality with no State.
    return {**{key: item for key, item in interpretation.items() if key != "state"}, "locality": label}


def geography_request(registry=REGISTRY):
    scope = ResearchScope(organization_id="org", collection_id="insects", specimen_id="subject_105526328",
                          job_id="job", generation=1, input_digest=PIN, profile_digest=PIN, sensitive=False)
    prompt = resolve_prompt(SpecialistRole.GEOGRAPHY, profile_digest=PIN, source_registry_digest=registry.digest,
                            toolset_digest=PIN, model_route="harness-deepseek", output_schema_digest=PIN)
    return SpecialistRequest(scope=scope, role=SpecialistRole.GEOGRAPHY,
                             field_keys=ROLE_FIELDS[SpecialistRole.GEOGRAPHY], prompt=prompt)


async def completed_effect(request, tool_id, arguments, invoke):
    # Test-only execution boundary standing in for the durable capture; no network, no cost.
    raw = await invoke()
    return ToolReceipt(id="receipt", scope=request.scope, tool_id=tool_id, source_id=arguments["source_id"],
                       field_keys=(arguments["field_key"],), effect_id="effect", attempt_ids=("attempt",),
                       request_digest=digest(arguments), binding_digest=digest(request.scope),
                       outcome=json.loads(raw)["status"], effect_status="completed", result_json=raw,
                       result_digest=hashlib.sha256(raw.encode()).hexdigest())


def query(field_key, interpretation, value):
    return SourceQuery(source_id="geolocate", field_key=field_key,
                       query_text=json.dumps({**interpretation, "value": value}))


def lookup(fixture, field_key, interpretation, value):
    sent = []

    async def read(url, policy):
        sent.append(url)
        return 200, (FIXTURES / fixture).read_bytes()

    broker = SourceBroker(REGISTRY, transport=FixtureSourceTransport(read), effect_dispatch=completed_effect)
    result = asyncio.run(broker.query(geography_request(), query(field_key, interpretation, value)))
    assert sent == [MANIFEST[fixture]["url"]], "the adapter must send exactly the recorded request"
    return result


def candidates(result):
    return [json.loads(item) for item in result.candidate_json]


def test_every_fixture_is_a_recorded_live_response():
    assert sorted(MANIFEST) == sorted(path.name for path in FIXTURES.glob("*.json") if path.name != "manifest.json")
    for item in MANIFEST.values():
        assert item["http_status"] == 200 and item["url"].startswith("https://geo-locate.org/")
        assert item["requested_at"].startswith("2026-10-03T")


def test_registry_admits_only_the_glcwrap_json_endpoint_and_drops_google_maps():
    assert [item.id for item in REGISTRY.policies] == [
        "global_names_verifier", "catalogue_of_life", "gbif", "bugguide", "mapcarta", "geolocate",
        "field_museum_ipt", "field_museum_emudata"]
    policy = REGISTRY.get("geolocate")
    assert policy.ready and not policy.paid and not policy.credentials_required
    assert [item.id for item in REGISTRY.policies if item.ready] == ["geolocate"]
    assert not insects_registry().get("geolocate").ready
    validate_destination(policy, MANIFEST["yepocapa-modern.json"]["url"])
    for refused in ("http://geo-locate.org/webservices/geolocatesvcv2/glcwrap.aspx?fmt=json",
                    "https://geo-locate.org/webservices/geolocatesvcv2/geolocatesvc.asmx/Georef2",
                    "https://maps.googleapis.com/maps/api/geocode/json?address=Yepocapa"):
        with pytest.raises(ValueError):
            validate_destination(policy, refused)


@pytest.mark.parametrize(("text", "message"), [
    ("Yepocapa", "one JSON object"),
    ("[]", "one JSON object"),
    (json.dumps({**YEPOCAPA, "value": "Yepocapa", "extra": 1}), "unknown extra"),
    (json.dumps({key: item for key, item in YEPOCAPA.items() if key != "place"} | {"value": "x"}), "missing place"),
    (json.dumps({**YEPOCAPA, "value": " Yepocapa"}), "value must be trimmed"),
    (json.dumps({**YEPOCAPA, "value": ""}), "value must be trimmed"),
    (json.dumps({**YEPOCAPA, "value": "Yepocapa", "radius_km": 500}), "radius_km must be a number"),
    (json.dumps({**YEPOCAPA, "value": "Yepocapa", "latitude": "14.5"}), "latitude must be a number"),
    (json.dumps({**YEPOCAPA, "value": "Yepocapa"}).replace("14.5", "1e999"), "latitude must be a number"),
    (json.dumps({**YEPOCAPA, "value": "Yepocapa", "radius_km": True}), "radius_km must be a number"),
])
def test_interpretation_contract_names_each_defect(text, message):
    with pytest.raises(ValueError, match=message):
        geolocate_interpretation(text)


def test_invalid_interpretation_is_refused_before_any_effect_or_request():
    async def no_effect(*_):
        raise AssertionError("an unsendable GEOLocate request must never open an effect")

    broker = SourceBroker(REGISTRY, transport=FixtureSourceTransport(no_effect), effect_dispatch=no_effect)
    result = asyncio.run(broker.query(geography_request(), SourceQuery(
        source_id="geolocate", field_key=FieldKey.CITY, query_text="Yepocapa, Chimaltenango")))
    assert result.status == LookupStatus.POLICY
    assert result.coverage.state == SourceCoverageState.UNQUALIFIED
    assert result.coverage.reason == "GEOLocate query_text must be one JSON object"


def test_yepocapa_is_confirmed_with_gazetteer_coordinates():
    result = lookup("yepocapa-modern.json", FieldKey.CITY, YEPOCAPA, "Yepocapa")
    assert result.status == LookupStatus.SUCCESS and result.coverage.candidate_count == 2
    assert result.coverage.reason == "GEOLocate confirms 'Yepocapa': 2 of 2 match(es) agree within 10 km of each other"
    [candidate] = candidates(result)
    assert candidate == {
        "field_key": "city", "value": "Yepocapa", "authority_id": "geolocate:14.501946,-90.953956",
        "authority_role": "candidate", "input_literal": "Yepocapa", "rank": 1,
        "decimal_latitude": 14.501946, "decimal_longitude": -90.953956, "geodetic_datum": "EPSG:4326",
        "match_name": "YEPOCAPA", "match_admin": "CHIMALTENANGO", "match_precision": "High", "match_score": 83,
        "distance_km": 0.5, "engine_version": "GLC:9.4|U:1.01374|eng:1.0"}
    assert "uncertainty" not in json.dumps(candidate), "the uncertainty radius is computed in-house (D13)"


def test_the_province_must_be_the_unit_gazetteer_reports():
    confirmed = lookup("yepocapa-modern.json", FieldKey.PROVINCE_STATE, YEPOCAPA, "Chimaltenango")
    assert confirmed.status == LookupStatus.SUCCESS
    assert candidates(confirmed)[0]["value"] == "Chimaltenango"
    # The label's own spelling is not the modern unit; the historian must correct it.
    misspelled = lookup("yepocapa-modern.json", FieldKey.PROVINCE_STATE, YEPOCAPA, "Chimaltenago")
    assert misspelled.status == LookupStatus.NO_MATCH and misspelled.candidate_json == ()
    assert misspelled.coverage.reason == "GEOLocate places 'Yepocapa' in CHIMALTENANGO, not 'Chimaltenago'"
    apo = lookup("apo-modern.json", FieldKey.PROVINCE_STATE, APO, "Davao del Sur")
    assert apo.status == LookupStatus.NO_MATCH
    assert apo.coverage.reason == "GEOLocate places 'Mount Apo' in CENTRAL MINDANAO, COTABATO, not 'Davao del Sur'"


def test_verbatim_label_locality_is_validated_by_the_named_place_only():
    yepocapa = lookup("yepocapa-verbatim.json", FieldKey.CITY, verbatim(YEPOCAPA, YEPOCAPA_LABEL), "Yepocapa")
    assert yepocapa.status == LookupStatus.SUCCESS and yepocapa.coverage.candidate_count == 9
    assert candidates(yepocapa)[0]["authority_id"] == "geolocate:14.501946,-90.953956"
    apo = lookup("apo-verbatim.json", FieldKey.PRECISE_LOCATION, verbatim(APO, APO_LABEL), APO_LABEL)
    assert apo.status == LookupStatus.SUCCESS
    [candidate] = candidates(apo)
    assert (candidate["value"], candidate["decimal_latitude"], candidate["decimal_longitude"]) == (APO_LABEL, 6.989444, 125.269722)
    assert candidate["match_name"] == "MOUNT APO" and candidate["input_literal"] == APO_LABEL


def test_mount_mckinley_has_no_mindanao_match_and_says_so():
    # Nine McKinley places exist on other islands; Davao and Mindanao hits never confirm a mountain.
    for fixture, interpretation in (("mckinley-modern.json", MCKINLEY),
                                    ("mckinley-verbatim.json", verbatim(MCKINLEY, MCKINLEY_LABEL))):
        result = lookup(fixture, FieldKey.PRECISE_LOCATION, interpretation, MCKINLEY_LABEL)
        assert result.status == LookupStatus.NO_MATCH and result.candidate_json == ()
        assert result.coverage.state == SourceCoverageState.SEARCHED
        count = result.coverage.candidate_count
        assert result.coverage.reason == (
            f"GEOLocate returned {count} match(es); none is 'Mount McKinley' within 40 km of the interpreted placement")


def test_state_is_ignored_outside_the_usa():
    old = json.loads((FIXTURES / "mckinley-old-province.json").read_bytes())
    modern = json.loads((FIXTURES / "mckinley-modern.json").read_bytes())
    assert old["resultSet"] == modern["resultSet"]
    result = lookup("mckinley-old-province.json", FieldKey.COUNTRY,
                    {**MCKINLEY, "state": "Davao", "locality": "Mt. McKinley"}, "Philippines")
    assert result.status == LookupStatus.NO_MATCH


def test_agreeing_points_far_apart_are_ambiguous():
    # A loose placement between the Apo summit and a second Mindanao "Mount Apo" 93 km away.
    loose = {**APO, "latitude": 6.6, "longitude": 125.45, "radius_km": 100}
    result = lookup("apo-modern.json", FieldKey.COUNTRY, loose, "Philippines")
    assert result.status == LookupStatus.AMBIGUOUS
    assert [item["authority_id"] for item in candidates(result)] == [
        "geolocate:6.233611,125.628333", "geolocate:6.983300,125.266700", "geolocate:6.989444,125.269722"]
    assert result.coverage.reason == "GEOLocate is ambiguous for 'Philippines': agreeing matches lie up to 93 km apart"


def test_usa_control_and_geojson_format():
    evanston = {"country": "USA", "state": "Illinois", "county": "Cook", "locality": "Evanston", "place": "Evanston",
                "latitude": 42.05, "longitude": -87.69, "radius_km": 10}
    assert lookup("evanston-control.json", FieldKey.COUNTY, evanston, "Cook").status == LookupStatus.SUCCESS
    # fmt=geojson drops numResults/engineVersion: a schema failure, never a scientific absence.
    async def read(url, policy):
        return 200, (FIXTURES / "yepocapa-geojson-format.json").read_bytes()
    broker = SourceBroker(REGISTRY, transport=FixtureSourceTransport(read), effect_dispatch=completed_effect)
    result = asyncio.run(broker.query(geography_request(), query(FieldKey.CITY, YEPOCAPA, "Yepocapa")))
    assert result.status == LookupStatus.MALFORMED and result.coverage.state == SourceCoverageState.FAILED


def test_success_candidate_decides_the_field_value_and_its_evidence():
    result = lookup("yepocapa-modern.json", FieldKey.CITY, YEPOCAPA, "Yepocapa")
    [candidate] = candidates(result)
    evidence = tuple(item.id for item in result.evidence)

    def resolution(value):
        return FieldResolution(
            field_key=FieldKey.CITY, work_state=WorkState.RESOLVED, value_layer="settled", evidence_ids=evidence,
            value=FieldValue(state=ValueState.SUPPORTED, parsed=value, authority_id=candidate["authority_id"],
                             evidence_ids=list(evidence)),
            reason="1948 label 'Yepocapa, Mun. Yepocapa'; modern municipality in Chimaltenango; GEOLocate confirms")

    assert validate_resolution(geography_request(), resolution("Yepocapa"), (result,)).value.parsed == "Yepocapa"
    with pytest.raises(EvidenceError, match="trusted source-supported candidates"):
        validate_resolution(geography_request(), resolution("Chimaltenango"), (result,))


def test_pacer_spaces_request_starts_three_seconds_per_source():
    clock, slept = [100.0], []

    async def sleep(seconds):
        slept.append(seconds)

    pacer = RequestPacer({"geolocate": 3.0}, clock=lambda: clock[0], sleep=sleep)

    async def burst():
        await asyncio.gather(*(pacer.wait("geolocate") for _ in range(3)), pacer.wait("gbif"))
        clock[0] += 20
        await pacer.wait("geolocate")

    asyncio.run(burst())
    assert slept == [3.0, 6.0]


def test_bounded_transport_waits_for_the_pacer_before_each_request():
    events = []

    class Pacer:
        async def wait(self, source_id):
            events.append(("wait", source_id))

    def respond(request):
        events.append(("request", request.url.host))
        return httpx.Response(200, stream=httpx.ByteStream((FIXTURES / "yepocapa-modern.json").read_bytes()))

    async def get():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await BoundedHTTPTransport(client, pacer=Pacer()).get(
                MANIFEST["yepocapa-modern.json"]["url"], policy=REGISTRY.get("geolocate"))

    code, _ = asyncio.run(get())
    assert code == 200 and events == [("wait", "geolocate"), ("request", "geo-locate.org")]
