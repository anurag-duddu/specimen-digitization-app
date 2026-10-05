"""GEOLocate validates the geography historian's interpretation (owner G-geo-1..3).

The fixtures are recorded responses of paced live probes for the ten pilot localities
(subjects 105526321..105526330); manifest.json names each request URL and time.
"""

import asyncio
import hashlib
import inspect
import json
import re
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from specimen_digitization.application.domain import FieldValue, LookupStatus, ValueState
from specimen_digitization.research_harness import canonical_materialization, canonical_projection_v2, prompts
from specimen_digitization.research_harness.committed_pins import MAX_OUTPUT_TOKENS
from specimen_digitization.research_harness.contracts import (
    ROLE_FIELDS, EventHypothesis, EventKind, FieldKey, FieldResolution, HumanQuestion, ResearchScope,
    SourceCoverageReceipt, SourceCoverageState, SourceFragment, SourceQuery, SpecialistRequest, SpecialistRole,
    ToolReceipt, WorkState, digest,
)
from specimen_digitization.research_harness.evidence import EvidenceError, assemble_field, validate_resolution
from specimen_digitization.research_harness.prompts import ROLE_PROMPTS, resolve_prompt
from specimen_digitization.research_harness.sources import (
    GEOLOCATE_QUALIFICATION, SOURCE_PACER, SOURCE_REQUEST_INTERVAL_SECONDS, BoundedHTTPTransport,
    FixtureSourceTransport, RequestPacer, SourceBroker, geolocate_interpretation, insects_registry,
    validate_destination,
)

FIXTURES = Path(__file__).parent / "fixtures" / "geolocate"
MANIFEST = {item["file"]: item for item in json.loads((FIXTURES / "manifest.json").read_text())["fixtures"]}
PIN = "0" * 64
FIXTURE_SHA256 = {
    "apo-modern.json": "38e8b32e7845e3c2d152fc4d5d43acc882a98324a3d8b9068f092fd2e9b98ad9",  # pragma: allowlist secret
    "apo-verbatim.json": "b8d982317b9989afe179cd475c43d81f6dc53cfd73c19f960f9edeb23740a5dd",  # pragma: allowlist secret
    "evanston-control.json": "044dafa006dba4ffaa29917caaf57f66f8e08543beda3183b4f43b0f3482cb1c",  # pragma: allowlist secret
    "mckinley-modern.json": "8bf7bcbf475e9d6d0087b66d5d4d9edcbbf8948ab9610095c36193fc421a53a6",  # pragma: allowlist secret
    "mckinley-old-province.json": "248687fa7e8cd6ab57f3cf3a8f32d2b91eeba9d9c166cc30f93e2bf4d02714c0",  # pragma: allowlist secret
    "mckinley-verbatim.json": "74fdd4c7f29339067eeb54674161fb4e8e980ecdbffae0d65143adc5f811a049",  # pragma: allowlist secret
    "yepocapa-geojson-format.json": "df49649ba0aa6c65458bbaf280565ead6d42a89f22920411f883a0d8dbffbcb0",  # pragma: allowlist secret
    "yepocapa-modern.json": "64ce81273d34129b48321b4e2a7b50443e50dda3bc02a3e26c44ca450265a46c",  # pragma: allowlist secret
    "yepocapa-verbatim.json": "70a81fa3c129faa9e22dd20001b1e24d73f68dbc13d7a1369bc9717909c707d2",  # pragma: allowlist secret
}
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
# geolocate_authority_id of the Yepocapa match: a digest of its name, admin unit and point (G39).
YEPOCAPA_ID = "geolocate:76853dedbc6ff5ce"


def verbatim(interpretation, label):
    # The recorded verbatim probes sent the label locality with no State.
    return {**{key: item for key, item in interpretation.items() if key != "state"}, "locality": label}


SCOPE = ResearchScope(organization_id="org", collection_id="insects", specimen_id="subject_105526328",
                      job_id="job", generation=1, input_digest=PIN, profile_digest=PIN, sensitive=False)
# Reader lines of two pilot locality labels (S4 reader baseline 2026-09-23, qwen reader).
LABEL_321 = "10-6-78-la\nE. slope Mt. McKinley\nDavao Prov.\nMindanao, P.I.\nF.G. Werner\n3 sept. '46\nMossy forest 6400'"
LABEL_330 = "IV-29-68-a\nYepocapa, 4800 ft.\nChimaltenango\nGuatemala, IV-25\n1948, R.D. Mitchell"


def geography_request(registry=REGISTRY, fragments=(), events=(), assemblies=(), scope=SCOPE):
    prompt = resolve_prompt(SpecialistRole.GEOGRAPHY, profile_digest=PIN, source_registry_digest=registry.digest,
                            toolset_digest=PIN, model_route="harness-deepseek", output_schema_digest=PIN)
    return SpecialistRequest(scope=scope, role=SpecialistRole.GEOGRAPHY,
                             field_keys=ROLE_FIELDS[SpecialistRole.GEOGRAPHY], prompt=prompt,
                             fragments=tuple(fragments), events=tuple(events), assemblies=tuple(assemblies))


def label_fragments(text):
    fragments, start = [], 0
    for order, line in enumerate(text.split("\n")):
        fragments.append(SourceFragment(
            id=f"line{order}", scope=SCOPE, asset_id="asset", asset_generation="1", asset_digest=PIN,
            label_id="label", region_id="label", observation_id="observation", reader="independent-reader",
            model_id="fake", prompt_digest=PIN, observation_text=text,
            observation_digest=hashlib.sha256(text.encode()).hexdigest(), start=start, end=start + len(line),
            literal=line, order=order))
        start += len(line) + 1
    return fragments


def assembled_request(locality, field_key=FieldKey.PRECISE_LOCATION):
    # The label's locality as an accepted assembly (for precise_location, the one way label text leaves).
    [fragment] = label_fragments(locality)
    event = EventHypothesis(id="event", scope=SCOPE, kind=EventKind.COLLECTING, fragment_ids=(fragment.id,),
                            evidence_ids=("role-evidence",), reason="Independently annotated synthetic event",
                            status="accepted", validator_version="gold-v1")
    assembly = assemble_field(assembly_id="locality", scope=SCOPE, field_key=field_key,
                              fragments=[fragment], event=event)
    assert assembly.interpreted_text == locality
    return geography_request(fragments=[fragment], events=[event], assemblies=[assembly])


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


def lookup(fixture, field_key, interpretation, value, request=None):
    sent = []

    async def read(url, policy):
        sent.append(url)
        return 200, (FIXTURES / fixture).read_bytes()

    broker = SourceBroker(REGISTRY, transport=FixtureSourceTransport(read), effect_dispatch=completed_effect)
    result = asyncio.run(broker.query(request or geography_request(), query(field_key, interpretation, value)))
    assert sent == [MANIFEST[fixture]["url"]], "the adapter must send exactly the recorded request"
    return result


def candidates(result):
    return [json.loads(item) for item in result.candidate_json]


def test_every_fixture_is_a_recorded_live_response():
    assert sorted(MANIFEST) == sorted(FIXTURE_SHA256)
    for name, item in MANIFEST.items():
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == FIXTURE_SHA256[name]
        assert item["http_status"] == 200 and item["url"].startswith("https://geo-locate.org/")
        assert item["requested_at"].startswith("2026-10-03T")
    # Eleven live requests: nine kept as fixtures, two omitted because their results repeat a kept one.
    omitted = json.loads((FIXTURES / "manifest.json").read_text())["omitted"]
    assert len(MANIFEST) + len(omitted) == 11


def test_registry_admits_only_the_glcwrap_json_endpoint_and_drops_google_maps():
    assert [item.id for item in REGISTRY.policies] == [
        "global_names_verifier", "catalogue_of_life", "gbif", "bugguide", "mapcarta", "geolocate",
        "georeference_history", "georeference_spatial", "tgn", "wikidata", "nga",
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
    (json.dumps({**YEPOCAPA, "value": "Yepocapa", "radius_km": 51}), "radius_km must be a number from 1 to 50"),
    (json.dumps({**YEPOCAPA, "value": "Yepocapa", "Locality <b>": 1}), "unknown \\?$"),
    (json.dumps({**YEPOCAPA, "value": "Yepocapa", "latitude": "14.5"}), "latitude must be a number"),
    (json.dumps({**YEPOCAPA, "value": "Yepocapa"}).replace("14.5", "1e999"), "latitude must be a number"),
    (json.dumps({**YEPOCAPA, "value": "Yepocapa", "radius_km": True}), "radius_km must be a number"),
    (json.dumps({**YEPOCAPA, "value": "Yepocapa", "latitude": 10 ** 400}), "latitude must be a number from -90 to 90"),
])
def test_interpretation_contract_names_each_defect(text, message):
    with pytest.raises(ValueError, match=message):
        geolocate_interpretation(text)


@pytest.mark.parametrize(("field_key", "interpretation", "value", "message"), [
    (FieldKey.COUNTRY, APO, "Taiwan", "country value must be the queried country"),
    (FieldKey.CITY, YEPOCAPA, "Antigua Guatemala", "city value must be the queried place"),
    (FieldKey.COUNTY, YEPOCAPA, "Chimaltenango", "county only inside the USA"),
    (FieldKey.PROVINCE_STATE, {"country": "USA", "state": "Illinois", "locality": "Evanston", "place": "Evanston",
                               "latitude": 42.05, "longitude": -87.69, "radius_km": 10}, "Iowa",
     "state value inside the USA must be the queried state"),
])
def test_value_must_be_what_geolocate_can_confirm(field_key, interpretation, value, message):
    async def no_effect(*_):
        raise AssertionError("an unconfirmable value must never open an effect")

    broker = SourceBroker(REGISTRY, transport=FixtureSourceTransport(no_effect), effect_dispatch=no_effect)
    result = asyncio.run(broker.query(geography_request(), query(field_key, interpretation, value)))
    assert result.status == LookupStatus.POLICY and message in result.coverage.reason


@pytest.mark.parametrize(("label", "field_key", "interpretation", "value", "message"), [
    # A whole reader line, a label slice, a collector beside the place, dates, an elevation.
    (LABEL_321, FieldKey.PRECISE_LOCATION, {**MCKINLEY, "locality": "E. slope Mt. McKinley"}, "E. slope Mt. McKinley",
     "locality must use only the words of place"),
    (LABEL_330, FieldKey.CITY, {**YEPOCAPA, "locality": "Yepocapa R.D. Mitchell"}, "Yepocapa",
     "locality must use only the words of place"),
    (LABEL_330, FieldKey.CITY, {**YEPOCAPA, "locality": "1948, R.D. Mitchell"}, "Yepocapa", "locality must be place text: no digits"),
    (LABEL_330, FieldKey.CITY, {**YEPOCAPA, "locality": "Yepocapa, 4800 ft."}, "Yepocapa", "locality must be place text: no digits"),
    (LABEL_321, FieldKey.COUNTRY, {**MCKINLEY, "state": "3 sept. '46"}, "Philippines", "state must be place text: no digits"),
    (LABEL_321, FieldKey.COUNTRY, {**MCKINLEY, "county": "Sept"}, "Philippines", "county must be place text: no month words"),
    # A clause holding a collector marker never leaves, even as the place itself.
    ("Yepocapa, Chimaltenango\nleg. R.D. Mitchell", FieldKey.CITY,
     {**YEPOCAPA, "locality": "Mitchell", "place": "Mitchell"}, "Mitchell", "no collector or determiner text"),
    *((f"Mt. Apo, Davao Prov.\n{clause}", FieldKey.COUNTRY, {**YEPOCAPA, "county": "Hoogstraal"}, "Guatemala",
       "county must be place text: no collector or determiner text")
      for clause in ("Collectors: H. Hoogstraal", "Collected by H. Hoogstraal", "Colectores: H. Hoogstraal",
                     "Recolector H. Hoogstraal", "Identified by H. Hoogstraal", "lg. H. Hoogstraal",
                     "Dét. H. Hoogstraal")),
])
def test_only_place_text_is_ever_sent(label, field_key, interpretation, value, message):
    async def no_effect(*_):
        raise AssertionError("label text that is not place text must never open an effect or a request")

    broker = SourceBroker(REGISTRY, transport=FixtureSourceTransport(no_effect), effect_dispatch=no_effect)
    request = geography_request(fragments=label_fragments(label))
    result = asyncio.run(broker.query(request, query(field_key, interpretation, value)))
    # A typed refusal the historian sees, never a silent skip.
    assert result.status == LookupStatus.POLICY and result.coverage.state == SourceCoverageState.UNQUALIFIED
    assert message in result.coverage.reason


def test_a_collectors_assembly_never_leaves_even_without_a_marker():
    [fragment] = label_fragments("R.D. Mitchell")
    event = EventHypothesis(id="event", scope=SCOPE, kind=EventKind.COLLECTING, fragment_ids=(fragment.id,),
                            evidence_ids=("role-evidence",), reason="Independently annotated synthetic event",
                            status="accepted", validator_version="gold-v1")
    collectors = assemble_field(assembly_id="collectors", scope=SCOPE, field_key=FieldKey.COLLECTORS,
                                fragments=[fragment], event=event)
    request = geography_request(fragments=[fragment], events=[event], assemblies=[collectors])

    async def no_effect(*_):
        raise AssertionError("a collector's name must never open an effect or a request")

    broker = SourceBroker(REGISTRY, transport=FixtureSourceTransport(no_effect), effect_dispatch=no_effect)
    result = asyncio.run(broker.query(request, query(FieldKey.COUNTRY, {**YEPOCAPA, "state": "Mitchell"}, "Guatemala")))
    assert result.status == LookupStatus.POLICY
    assert result.coverage.reason == "GEOLocate state must be place text: no collector or determiner text"


def test_the_modern_interpretation_of_a_real_label_sends_no_label_text():
    request = geography_request(fragments=label_fragments(LABEL_330))
    result = lookup("yepocapa-modern.json", FieldKey.CITY, YEPOCAPA, "Yepocapa", request)
    assert result.status == LookupStatus.SUCCESS
    url = MANIFEST["yepocapa-modern.json"]["url"]
    assert not any(token in url for token in ("Mitchell", "1948", "4800", "IV-25", "IV-29"))


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
    assert result.coverage.reason == "success: GEOLocate confirms 'Yepocapa': 2 of 2 match(es) agree within 10 km of each other"
    [candidate] = candidates(result)
    assert candidate == {
        "field_key": "city", "value": "Yepocapa", "authority_id": YEPOCAPA_ID,
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
    assert misspelled.coverage.reason == "no_match: GEOLocate places 'Yepocapa' in CHIMALTENANGO, not 'Chimaltenago'"
    apo = lookup("apo-modern.json", FieldKey.PROVINCE_STATE, APO, "Davao del Sur")
    assert apo.status == LookupStatus.NO_MATCH
    assert apo.coverage.reason == "no_match: GEOLocate places 'Mount Apo' in CENTRAL MINDANAO, COTABATO, not 'Davao del Sur'"


def test_verbatim_label_locality_is_validated_by_the_named_place_only():
    yepocapa = lookup("yepocapa-verbatim.json", FieldKey.CITY, verbatim(YEPOCAPA, YEPOCAPA_LABEL), "Yepocapa",
                      assembled_request(YEPOCAPA_LABEL))
    assert yepocapa.status == LookupStatus.SUCCESS and yepocapa.coverage.candidate_count == 9
    assert candidates(yepocapa)[0]["authority_id"] == YEPOCAPA_ID
    apo = lookup("apo-verbatim.json", FieldKey.PRECISE_LOCATION, verbatim(APO, APO_LABEL), APO_LABEL,
                 assembled_request(APO_LABEL))
    assert apo.status == LookupStatus.SUCCESS
    [candidate] = candidates(apo)
    assert (candidate["value"], candidate["decimal_latitude"], candidate["decimal_longitude"]) == (APO_LABEL, 6.989444, 125.269722)
    assert candidate["match_name"] == "MOUNT APO" and candidate["input_literal"] == APO_LABEL


def test_mount_mckinley_has_no_mindanao_match_and_says_so():
    # Nine McKinley places exist on other islands; Davao and Mindanao hits never confirm a mountain.
    for fixture, interpretation, request in (
            ("mckinley-modern.json", MCKINLEY, None),
            ("mckinley-verbatim.json", verbatim(MCKINLEY, MCKINLEY_LABEL), assembled_request(MCKINLEY_LABEL))):
        result = lookup(fixture, FieldKey.PRECISE_LOCATION, interpretation, MCKINLEY_LABEL, request)
        assert result.status == LookupStatus.NO_MATCH and result.candidate_json == ()
        assert result.coverage.state == SourceCoverageState.SEARCHED
        count = result.coverage.candidate_count
        assert result.coverage.reason == (
            f"no_match: GEOLocate returned {count} match(es); none is 'Mount McKinley' within 40 km of the interpreted placement")


def test_state_is_ignored_outside_the_usa():
    old = json.loads((FIXTURES / "mckinley-old-province.json").read_bytes())
    modern = json.loads((FIXTURES / "mckinley-modern.json").read_bytes())
    assert old["resultSet"] == modern["resultSet"]
    result = lookup("mckinley-old-province.json", FieldKey.COUNTRY,
                    {**MCKINLEY, "state": "Davao", "locality": "Mt. McKinley"}, "Philippines")
    assert result.status == LookupStatus.NO_MATCH


def test_agreeing_points_far_apart_are_ambiguous():
    # A placement midway between the Apo summit and a second Mindanao "Mount Apo" 92 km away.
    loose = {**APO, "latitude": 6.611, "longitude": 125.449, "radius_km": 50}
    result = lookup("apo-modern.json", FieldKey.COUNTRY, loose, "Philippines")
    assert result.status == LookupStatus.AMBIGUOUS
    assert [item["authority_id"] for item in candidates(result)] == [
        "geolocate:a863d52e6ff08fe2", "geolocate:a71cd5741681e8fa", "geolocate:3e5a153ca95eedd5"]
    assert result.coverage.reason == "ambiguous: GEOLocate is ambiguous for 'Philippines': agreeing matches lie up to 92 km apart"


def test_usa_control_and_geojson_format():
    evanston = {"country": "USA", "state": "Illinois", "county": "Cook", "locality": "Evanston", "place": "Evanston",
                "latitude": 42.05, "longitude": -87.69, "radius_km": 10}
    assert lookup("evanston-control.json", FieldKey.COUNTY, evanston, "Cook").status == LookupStatus.SUCCESS
    # Inside the USA the gazetteer admin unit is the county, and State confines the search.
    assert lookup("evanston-control.json", FieldKey.PROVINCE_STATE, evanston, "Illinois").status == LookupStatus.SUCCESS
    assert lookup("evanston-control.json", FieldKey.COUNTY, evanston, "Lake").status == LookupStatus.NO_MATCH
    # fmt=geojson drops numResults/engineVersion: a schema failure, never a scientific absence.
    async def read(url, policy):
        return 200, (FIXTURES / "yepocapa-geojson-format.json").read_bytes()
    broker = SourceBroker(REGISTRY, transport=FixtureSourceTransport(read), effect_dispatch=completed_effect)
    result = asyncio.run(broker.query(geography_request(), query(FieldKey.CITY, YEPOCAPA, "Yepocapa")))
    assert result.status == LookupStatus.MALFORMED and result.coverage.state == SourceCoverageState.FAILED


def lookup_body(body, field_key=FieldKey.CITY, interpretation=YEPOCAPA, value="Yepocapa", code=200):
    async def read(url, policy):
        return code, body

    broker = SourceBroker(REGISTRY, transport=FixtureSourceTransport(read), effect_dispatch=completed_effect)
    return asyncio.run(broker.query(geography_request(), query(field_key, interpretation, value)))


# --- G39: the matched point is candidate metadata, never part of the candidate's identifier ---
ID_FORMAT = re.compile(r"geolocate:[0-9a-f]{16}")
DECIMAL_NUMBER = re.compile(r"\d+\.\d+")
EVANSTON = {"country": "USA", "state": "Illinois", "county": "Cook", "locality": "Evanston", "place": "Evanston",
            "latitude": 42.05, "longitude": -87.69, "radius_km": 10}


def recorded_points(fixture):
    """Every [longitude, latitude] pair of the recorded glcwrap answer: the evidence."""
    features = json.loads((FIXTURES / fixture).read_bytes())["resultSet"]["features"]
    return [feature["geometry"]["coordinates"] for feature in features]


@pytest.mark.parametrize(("fixture", "interpretation", "value", "field_key", "count"), [
    ("yepocapa-modern.json", YEPOCAPA, "Yepocapa", FieldKey.CITY, 1),
    ("evanston-control.json", EVANSTON, "Evanston", FieldKey.CITY, 1),
    ("apo-modern.json", {**APO, "latitude": 6.611, "longitude": 125.449, "radius_km": 50}, "Philippines",
     FieldKey.COUNTRY, 3)])
def test_the_authority_id_holds_no_coordinates_and_the_point_stays_in_the_result(
        fixture, interpretation, value, field_key, count):
    found = candidates(lookup(fixture, field_key, interpretation, value))
    assert len(found) == count
    assert len({item["authority_id"] for item in found}) == count, "each match has an identifier of its own"
    for item in found:
        identifier = item["authority_id"]
        assert ID_FORMAT.fullmatch(identifier), identifier
        latitude, longitude = item["decimal_latitude"], item["decimal_longitude"]
        for spelling in (f"{latitude:.6f}", str(latitude), f"{longitude:.6f}", str(longitude)):
            assert spelling not in identifier
        assert not DECIMAL_NUMBER.search(identifier)
        # The point is where G39 keeps it: the tool result, which is the recorded response's own point.
        assert [longitude, latitude] in recorded_points(fixture)
        assert item["geodetic_datum"] == "EPSG:4326"


def test_a_match_keeps_its_authority_id_and_another_point_or_place_gets_another():
    first = candidates(lookup("yepocapa-modern.json", FieldKey.CITY, YEPOCAPA, "Yepocapa"))
    again = candidates(lookup("yepocapa-modern.json", FieldKey.CITY, YEPOCAPA, "Yepocapa"))
    assert first == again and first[0]["authority_id"] == YEPOCAPA_ID
    # The id does not depend on the field or on the historian's placement, only on the match.
    elsewhere = candidates(lookup("yepocapa-modern.json", FieldKey.PROVINCE_STATE,
                                  {**YEPOCAPA, "latitude": 14.52, "longitude": -90.93}, "Chimaltenango"))
    assert elsewhere[0]["authority_id"] == YEPOCAPA_ID

    payload = json.loads((FIXTURES / "yepocapa-modern.json").read_bytes())

    def identified(mutate):
        changed = json.loads(json.dumps(payload))
        mutate(changed["resultSet"]["features"][0])
        [item] = candidates(lookup_body(json.dumps(changed).encode()))
        return item

    def move(offset, axis=0):
        # GeoJSON order: axis 0 is the longitude, axis 1 the latitude.
        def mutate(feature):
            feature["geometry"]["coordinates"][axis] += offset
        return mutate

    # One millionth of a degree, east or north, is a different point; a hundred-millionth rounds to the same one.
    east = identified(move(0.000001))
    assert round(east["decimal_longitude"], 6) == -90.953955 and east["authority_id"] != YEPOCAPA_ID
    north = identified(move(0.000001, axis=1))
    assert round(north["decimal_latitude"], 6) == 14.501947 and north["authority_id"] != YEPOCAPA_ID
    assert north["authority_id"] != east["authority_id"]
    assert identified(move(0.00000001))["authority_id"] == YEPOCAPA_ID
    assert identified(move(0.00000001, axis=1))["authority_id"] == YEPOCAPA_ID
    assert identified(lambda feature: feature["properties"].update(parsePattern="Yepocapa"))["authority_id"] != YEPOCAPA_ID
    assert identified(lambda feature: feature["properties"].update(
        debug=feature["properties"]["debug"].replace("CHIMALTENANGO", "SACATEPEQUEZ")))["authority_id"] != YEPOCAPA_ID
    # A re-score or a new engine does not rename a place.
    rescored = identified(lambda feature: feature["properties"].update(score=90, precision="Medium"))
    assert rescored["match_score"] == 90 and rescored["authority_id"] == YEPOCAPA_ID


@pytest.mark.parametrize("mutate", [
    lambda feature: feature.pop("geometry"),
    lambda feature: feature.update(geometry=None),
    lambda feature: feature.update(geometry=[-90.95, 14.5]),
    lambda feature: feature.update(geometry="POINT (-90.95 14.5)"),
    lambda feature: feature.update(geometry=7),
    lambda feature: feature.update(properties=None),
    lambda feature: feature.clear(),
])
def test_malformed_features_are_typed_failures_never_exceptions(mutate):
    # An uncaught exception would leave the captured effect held_unknown and abort the field.
    payload = json.loads((FIXTURES / "yepocapa-modern.json").read_bytes())
    mutate(payload["resultSet"]["features"][0])
    result = lookup_body(json.dumps(payload).encode())
    assert result.status == LookupStatus.MALFORMED and result.coverage.state == SourceCoverageState.FAILED
    feature_not_object = json.loads((FIXTURES / "yepocapa-modern.json").read_bytes())
    feature_not_object["resultSet"]["features"][0] = "feature"
    assert lookup_body(json.dumps(feature_not_object).encode()).status == LookupStatus.MALFORMED


@pytest.mark.parametrize(("code", "status"), [
    (429, LookupStatus.RATE_LIMITED), (404, LookupStatus.PROVIDER), (500, LookupStatus.PROVIDER)])
def test_http_failures_are_not_scientific_absence(code, status):
    result = lookup_body(b"busy", code=code)
    assert result.status == status and result.coverage.state == SourceCoverageState.FAILED


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


def test_production_wiring_paces_geolocate_three_seconds_apart():
    assert SOURCE_REQUEST_INTERVAL_SECONDS == {"geolocate": 3.0}
    assert BoundedHTTPTransport().pacer is SOURCE_PACER
    assert SOURCE_PACER._intervals == SOURCE_REQUEST_INTERVAL_SECONDS


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


# --- evidence_relations: the publication gate the v2 success bullet must teach ---
# The live geography file: the v2 text followed by the v3 blocks.
V2_PROMPT = Path(prompts.__file__).parent / ROLE_PROMPTS[SpecialistRole.GEOGRAPHY][0]
V1_GATE = 'set(relations) != cited or not any(role in {"supports", "decides"} for role in relations.values())'
V2_GATE = "if evidence not in canonical_ids or (relation is None and not scientific):"


def publication_accepts_relations(value):
    """The two candidate-evidence gates, which are inline and have no smaller callable.

    canonical_materialization.py:307-311 (v1 materializer) and canonical_projection_v2.py:553-561
    (the production V2 path, for a value that is not derived)."""
    cited, relations = set(value.evidence_ids), value.evidence_relations
    v1 = set(relations) == cited and any(role in {"supports", "decides"} for role in relations.values())
    v2 = all(relations.get(item) in {"decides", "supports", "contradicts"} for item in value.evidence_ids)
    return v1 and v2


def test_the_mirrored_publication_gates_are_still_in_the_source():
    assert V1_GATE in inspect.getsource(canonical_materialization.CanonicalResearchMaterializer.materialize)
    assert V2_GATE in inspect.getsource(canonical_projection_v2.project_canonical_value_v2)


def test_the_prompted_success_resolution_carries_the_relations_publication_requires():
    text = V2_PROMPT.read_text(encoding="utf-8")
    assert 'value.evidence_relations maps each of those ids\n  to "supports"' in text
    result = lookup("yepocapa-modern.json", FieldKey.CITY, YEPOCAPA, "Yepocapa")
    [candidate] = candidates(result)
    evidence = tuple(item.id for item in result.evidence)
    # GEOLocate is a candidate authority: its evidence supports, never decides (sources.py:720).
    assert evidence and {item.role for item in result.evidence} == {"supports"}

    def prompted(**relations):
        # Exactly the success bullet: resolved, supported, settled, normalized = candidate value,
        # parsed null, the candidate's authority_id, both evidence lists = that result's ids.
        return FieldResolution(
            field_key=FieldKey.CITY, work_state=WorkState.RESOLVED, value_layer="settled", evidence_ids=evidence,
            value=FieldValue(state=ValueState.SUPPORTED, normalized=candidate["value"], parsed=None,
                             authority_id=candidate["authority_id"], evidence_ids=list(evidence), **relations),
            reason="1948 label 'Yepocapa, Mun. Yepocapa'; modern municipality in Chimaltenango; GEOLocate confirms")

    complete = prompted(evidence_relations=dict.fromkeys(evidence, "supports"))
    assert validate_resolution(geography_request(), complete, (result,)) == complete
    assert complete.value.authority_id == YEPOCAPA_ID
    assert publication_accepts_relations(complete.value)

    # The validator never reads evidence_relations, so the engine accepts an omission ...
    omitted = prompted()
    assert omitted.value.evidence_relations == {}
    assert validate_resolution(geography_request(), omitted, (result,)) == omitted
    # ... and only publication refuses it.
    assert not publication_accepts_relations(omitted.value)
    assert not publication_accepts_relations(prompted(evidence_relations={"source:other": "supports"}).value)
    assert not publication_accepts_relations(prompted(evidence_relations=dict.fromkeys(evidence, "contradicts")).value)


# --- Coordinator ruling 7 (2026-10-03): unresolved geography goes to a person; outages never do ---
def question(result, field_key, reason):
    return HumanQuestion(field_key=field_key, question="Which modern place does the label mean?", reason=reason,
                         coverage=(result.coverage,), evidence_ids=tuple(item.id for item in result.evidence))


def test_geolocate_no_match_and_ambiguous_reach_a_person():
    request = assembled_request(MCKINLEY_LABEL)
    unmatched = lookup("mckinley-modern.json", FieldKey.PRECISE_LOCATION, MCKINLEY, MCKINLEY_LABEL, request)
    assert unmatched.status == LookupStatus.NO_MATCH and unmatched.coverage.state == SourceCoverageState.SEARCHED
    asked = question(unmatched, FieldKey.PRECISE_LOCATION, "scoped_absence")
    waiting = FieldResolution(
        field_key=FieldKey.PRECISE_LOCATION, work_state=WorkState.WAITING_HUMAN, question=asked,
        value=FieldValue(state=ValueState.UNRESOLVED, literal=MCKINLEY_LABEL), evidence_ids=asked.evidence_ids,
        reason="1946 Philippine expedition label; no Mount McKinley on Mindanao in GEOLocate (9 matches elsewhere)")
    assert validate_resolution(request, waiting, (unmatched,)) == waiting
    loose = {**APO, "latitude": 6.611, "longitude": 125.449, "radius_km": 50}
    ambiguous = lookup("apo-modern.json", FieldKey.COUNTRY, loose, "Philippines")
    assert ambiguous.status == LookupStatus.AMBIGUOUS
    assert question(ambiguous, FieldKey.COUNTRY, "semantic_ambiguity").coverage == (ambiguous.coverage,)


def timed_out(url, policy):
    raise httpx.ReadTimeout("slow")


PARTLY_QUALIFIED = insects_registry(qualification_overrides={"geolocate": {"qualification_state": "searched"}})


async def held_effect(request, tool_id, arguments, invoke):
    return ToolReceipt(id="receipt", scope=request.scope, tool_id=tool_id, source_id=arguments["source_id"],
                       field_keys=(arguments["field_key"],), effect_id="effect", attempt_ids=("attempt",),
                       request_digest=digest(arguments), binding_digest=digest(request.scope),
                       outcome="timeout", effect_status="held_unknown")


@pytest.mark.parametrize("outage", [
    lambda: lookup_body(b"busy", code=429),
    lambda: lookup_body(b"forbidden", code=403),
    lambda: lookup_body(b"error", code=500),
    lambda: lookup_body(b"not json"),
    lambda: asyncio.run(SourceBroker(REGISTRY, transport=FixtureSourceTransport(timed_out), effect_dispatch=completed_effect)
                        .query(geography_request(), query(FieldKey.CITY, YEPOCAPA, "Yepocapa"))),
    # Not ready: the default registry leaves GEOLocate unqualified.
    lambda: asyncio.run(SourceBroker(insects_registry(), transport=FixtureSourceTransport(timed_out), effect_dispatch=completed_effect)
                        .query(geography_request(insects_registry()), query(FieldKey.CITY, YEPOCAPA, "Yepocapa"))),
    # No adapter: a qualified browser source is still refused.
    lambda: asyncio.run(SourceBroker(insects_registry(qualification_overrides={"mapcarta": GEOLOCATE_QUALIFICATION}),
                                     transport=FixtureSourceTransport(timed_out), effect_dispatch=completed_effect).query(
        geography_request(insects_registry(qualification_overrides={"mapcarta": GEOLOCATE_QUALIFICATION})),
        SourceQuery(source_id="mapcarta", field_key=FieldKey.CITY, query_text="Yepocapa"))),
    # A refused query (not place text) is operational too.
    lambda: lookup_body(b"", interpretation={**YEPOCAPA, "locality": "Yepocapa, 4800 ft."}),
    lambda: lookup_body(b"unauthorized", code=401),
    # Not ready although marked searched: the real receipt is SEARCHED with a POLICY status.
    lambda: asyncio.run(SourceBroker(PARTLY_QUALIFIED, transport=FixtureSourceTransport(timed_out),
                                     effect_dispatch=completed_effect).query(
        geography_request(PARTLY_QUALIFIED), query(FieldKey.CITY, YEPOCAPA, "Yepocapa"))),
    # The durable effect outcome is held unknown.
    lambda: asyncio.run(SourceBroker(REGISTRY, transport=FixtureSourceTransport(timed_out), effect_dispatch=held_effect)
                        .query(geography_request(), query(FieldKey.CITY, YEPOCAPA, "Yepocapa"))),
    # A sensitive specimen is never disclosed to a source.
    lambda: asyncio.run(SourceBroker(REGISTRY, transport=FixtureSourceTransport(timed_out), effect_dispatch=completed_effect)
                        .query(geography_request(scope=SCOPE.model_copy(update={"sensitive": True})),
                               query(FieldKey.CITY, YEPOCAPA, "Yepocapa"))),
    # No durable effect dispatcher.
    lambda: asyncio.run(SourceBroker(REGISTRY, transport=FixtureSourceTransport(timed_out))
                        .query(geography_request(), query(FieldKey.CITY, YEPOCAPA, "Yepocapa"))),
])
def test_an_outage_never_produces_a_human_question(outage):
    result = outage()
    assert result.status not in {LookupStatus.SUCCESS, LookupStatus.NO_MATCH, LookupStatus.AMBIGUOUS}
    with pytest.raises(ValidationError, match="exhausted"):
        question(result, FieldKey.CITY, "scoped_absence")


def test_only_geolocate_geography_outcomes_are_loosened():
    confirmed = lookup("yepocapa-modern.json", FieldKey.CITY, YEPOCAPA, "Yepocapa")
    with pytest.raises(ValidationError, match="exhausted"):
        question(confirmed, FieldKey.CITY, "scoped_absence")
    for source_id, field_key in (("catalogue_of_life", FieldKey.TAXON), ("geolocate", FieldKey.TAXON)):
        searched = SourceCoverageReceipt(source_id=source_id, field_key=field_key, state=SourceCoverageState.SEARCHED,
                                         source_version="v", coverage_limit="bounded", reason="no_match: none")
        with pytest.raises(ValidationError, match="exhausted"):
            HumanQuestion(field_key=field_key, question="?", reason="scoped_absence", coverage=(searched,))


def receipt(source_id="geolocate", state=SourceCoverageState.SEARCHED, reason="no_match: GEOLocate returned 2 match(es)"):
    return SourceCoverageReceipt(source_id=source_id, field_key=FieldKey.CITY, state=state, source_version="v",
                                 coverage_limit="bounded", reason=reason)


def asks(*coverage):
    return HumanQuestion(field_key=FieldKey.CITY, question="?", reason="scoped_absence", coverage=coverage)


def test_the_loosened_rule_admits_only_typed_geolocate_outcomes_never_mixed():
    assert asks(receipt()).coverage == (receipt(),)
    assert asks(receipt(reason="ambiguous: GEOLocate is ambiguous for 'Yepocapa'")).reason == "scoped_absence"
    refused = [
        receipt(source_id="mapcarta"),
        # A spoofed scientific reason on an outage receipt.
        *(receipt(state=state) for state in (SourceCoverageState.FAILED, SourceCoverageState.INACCESSIBLE,
                                             SourceCoverageState.UNQUALIFIED, SourceCoverageState.NOT_ATTEMPTED,
                                             SourceCoverageState.SCHEMA_ONLY)),
        *(receipt(reason=reason) for reason in ("no_match", "no_match:", "no_match: ", "ambiguous",
                                                "success: GEOLocate confirms 'Yepocapa'", "policy_blocked: x",
                                                "Source endpoint/schema/terms/version qualification incomplete")),
    ]
    for item in refused:
        with pytest.raises(ValidationError, match="exhausted"):
            asks(item)
    exhausted = SourceCoverageReceipt(
        source_id="field_museum_ipt", field_key=FieldKey.CITY, state=SourceCoverageState.EXHAUSTED, source_version="v",
        qualification_digest=PIN, exact_join_attempted=True, query_digest=PIN, receipt_ids=("source:exact",),
        coverage_limit="Only this pinned publisher occurrence search/term", reason="no_match")
    assert asks(exhausted).coverage == (exhausted,)
    with pytest.raises(ValidationError, match="exhausted"):
        asks(exhausted, receipt())
    with pytest.raises(ValidationError, match="exhausted"):
        asks(receipt(), receipt(state=SourceCoverageState.FAILED, reason="timeout"))


def test_five_human_questions_echoing_their_receipts_fit_one_response():
    # The prompt's budget: one GEOLocate lookup per field, reasons under 300 characters, and the
    # pinned output cap (MAX_OUTPUT_TOKENS) per reply. Estimate: two characters per token for hex
    # digests, three otherwise, plus a 100-token margin.
    request = assembled_request(MCKINLEY_LABEL)
    unmatched = lookup("mckinley-modern.json", FieldKey.PRECISE_LOCATION, MCKINLEY, MCKINLEY_LABEL, request)
    asked = HumanQuestion(
        field_key=FieldKey.PRECISE_LOCATION, reason="scoped_absence", coverage=(unmatched.coverage,),
        question="Which modern place is 'E. slope Mt. McKinley, Davao Prov.'? GEOLocate holds none on Mindanao.",
        evidence_ids=tuple(item.id for item in unmatched.evidence))
    waiting = FieldResolution(
        field_key=FieldKey.PRECISE_LOCATION, work_state=WorkState.WAITING_HUMAN, question=asked,
        value=FieldValue(state=ValueState.UNRESOLVED, literal=MCKINLEY_LABEL), evidence_ids=asked.evidence_ids,
        assembly_ids=("locality",), event_id="event", reason="r" * 299).model_dump_json()
    hex_characters = sum(len(item) for item in re.findall(r"[0-9a-f]{32,}", waiting))
    tokens = hex_characters / 2 + (len(waiting) - hex_characters) / 3
    assert 5 * tokens + 100 <= MAX_OUTPUT_TOKENS


def test_the_pinned_output_cap_is_the_budget_the_geography_prompt_states():
    # The prompt tells the model its five results "fit one response of N tokens"; the pin is what the
    # provider enforces. They disagreed (the prompt said 4096, the pin 2048), so a full five-field
    # answer could be cut off mid tool call.
    stated = re.findall(r"fit one response of ([\d,]+) tokens", geography_request().prompt.text)
    assert [int(number.replace(",", "")) for number in stated] == [MAX_OUTPUT_TOKENS]


def test_lookup_citing_resolutions_name_the_assemblies_they_read():
    # The capture takes a lookup's producer from the citing resolution's assemblies; without them
    # publication refuses the lookup (application/projection.py lookup_evidence_producer_invalid).
    text = V2_PROMPT.read_text(encoding="utf-8")
    assert ("Every resolution that cites a GEOLocate lookup names, as the common rules ask,\n"
            "its accepted/rejected assemblies (assembly_ids") in text and "event (event_id)" in text
    request = assembled_request("Yepocapa", FieldKey.CITY)
    [assembly] = request.assemblies
    result = lookup("yepocapa-modern.json", FieldKey.CITY, YEPOCAPA, "Yepocapa", request)
    [candidate] = candidates(result)
    evidence = tuple(item.id for item in result.evidence)
    resolved = FieldResolution(
        field_key=FieldKey.CITY, work_state=WorkState.RESOLVED, value_layer="settled", evidence_ids=evidence,
        assembly_ids=(assembly.id,), event_id=assembly.event_id,
        value=FieldValue(state=ValueState.SUPPORTED, normalized=candidate["value"], authority_id=candidate["authority_id"],
                         evidence_ids=list(evidence), evidence_relations=dict.fromkeys(evidence, "supports")),
        reason="1948 label 'Yepocapa'; modern municipality in Chimaltenango; GEOLocate confirms")
    assert validate_resolution(request, resolved, (result,)) == resolved
    unmatched_request = assembled_request(MCKINLEY_LABEL)
    [locality] = unmatched_request.assemblies
    unmatched = lookup("mckinley-modern.json", FieldKey.PRECISE_LOCATION, MCKINLEY, MCKINLEY_LABEL, unmatched_request)
    asked = question(unmatched, FieldKey.PRECISE_LOCATION, "scoped_absence")
    waiting = FieldResolution(
        field_key=FieldKey.PRECISE_LOCATION, work_state=WorkState.WAITING_HUMAN, question=asked,
        value=FieldValue(state=ValueState.UNRESOLVED, literal=MCKINLEY_LABEL), evidence_ids=asked.evidence_ids,
        assembly_ids=(locality.id,), event_id=locality.event_id,
        reason="1946 label; no Mount McKinley on Mindanao in GEOLocate")
    assert validate_resolution(unmatched_request, waiting, (unmatched,)) == waiting
