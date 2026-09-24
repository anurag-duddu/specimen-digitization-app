"""Google geography tool (G10): only place ID, outcome and fingerprint (G26)."""

import hashlib
import json
import logging
import re
from types import SimpleNamespace

import httpx
import pytest

from specimen_digitization.application import geography_tool
from specimen_digitization.application.domain import LookupStatus as S
from specimen_digitization.application.geography_tool import (
    GEOCODING_COST_MICROS,
    GEOCODING_URL,
    TOOL_VERSION,
    comparison_key,
    fold,
    geocode_locality,
    map_geocoding_response,
    one_letter_apart,
)
from specimen_digitization.application.harness_tools import (
    GeographyQuery,
    LocalityLiteral,
    PlaceCandidate,
)

KEY_VARIABLE = "SPECIMEN_GOOGLE_MAPS_API_KEY"
MAPS_KEY = "fake-maps-credential-never-stored"
LABEL = "E. slope Mt. McKinley, Davao Prov., Mindanao, P.I."


def component(long_name, short_name, *types):
    return {"long_name": long_name, "short_name": short_name, "types": list(types)}


def place(place_id, *components, lat=7.0730556, lng=125.6127778):
    """A Geocoding result carrying everything G26 forbids us to keep."""
    return {
        "place_id": place_id,
        "formatted_address": ", ".join(c["long_name"] for c in components),
        "address_components": list(components),
        "geometry": {
            "location": {"lat": lat, "lng": lng},
            "location_type": "APPROXIMATE",
        },
        "types": ["political"],
    }


DAVAO = place(
    "place-davao-city",
    component("Davao City", "Davao City", "locality", "political"),
    component("Davao del Sur", "Davao del Sur", "administrative_area_level_2"),
    component("Davao Region", "Davao Region", "administrative_area_level_1"),
    component("Philippines", "PH", "country", "political"),
)
DENALI = place(
    "place-denali",
    component("Denali", "Denali", "natural_feature"),
    component("Denali Borough", "Denali Borough", "administrative_area_level_2"),
    component("Alaska", "AK", "administrative_area_level_1", "political"),
    component("United States", "US", "country", "political"),
    lat=63.0692345,
    lng=-151.0070123,
)


def query(*pairs):
    return GeographyQuery(
        literals=[
            LocalityLiteral(
                field_key=field_key,
                literal=text,
                source_observation_id="observation-1",
                source_region_id="region-1",
            )
            for field_key, text in pairs
        ]
    )


# Label literals differ from Google's spelling by case, accents or punctuation,
# so any Google text found in the output could only have come from Google.
QUERY = query(
    ("precise_location", "Mt. Apo"),
    ("city", "DAVAO CITY."),
    ("county", "Davão del Sur"),
    ("country", "P.I."),
)
ADDRESS = "Mt. Apo, DAVAO CITY., Davão del Sur, P.I."
# The fields the tool reports on: precise_location only helps form the address
# and is never settled by a geocoder result (PRD 519; S8's D3 pending).
FIELDS = ("city", "county", "country")


def reply(*results, status="OK", code=200, headers=None, **extra):
    """A Geocoding reply as (HTTP status, body bytes, headers)."""
    body = json.dumps({"results": list(results), "status": status, **extra})
    return code, body.encode(), headers or {}


class Blobs:
    """Content-addressed like `LocalBlobs`; remembers every put."""

    def __init__(self):
        self.puts: list[bytes] = []

    def put(self, data: bytes) -> str:
        self.puts.append(data)
        return hashlib.sha256(data).hexdigest()

    def get(self, ref: str) -> bytes:
        return next(d for d in self.puts if hashlib.sha256(d).hexdigest() == ref)


def geocode(geography, *replies, api_key=MAPS_KEY, allow=None, **options):
    """Run the tool against a fake Geocoding endpoint; the last reply repeats.
    `allow(n)` answers the n-th cost reservation; None passes no budget."""
    seen = SimpleNamespace(requests=[], sleeps=[], reservations=[], blobs=Blobs())

    def handler(request):
        seen.requests.append(request)
        answer = replies[min(len(seen.requests), len(replies)) - 1]
        if isinstance(answer, Exception):
            raise answer
        code, body, headers = answer
        return httpx.Response(code, content=body, headers=headers)

    def reserve(micros):
        seen.reservations.append(micros)
        return allow(len(seen.reservations))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        seen.result = geocode_locality(
            geography,
            blobs=seen.blobs,
            api_key=api_key,
            client=client,
            reserve_cost=None if allow is None else reserve,
            sleep=seen.sleeps.append,
            **options,
        )
        seen.client_closed = client.is_closed
    return seen


def sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def fingerprint(place_id, outcome, body):
    """The only bytes G26 lets the tool store per attempt."""
    record = {"place_id": place_id, "outcome": outcome.value}
    record["response_sha256"] = sha(body)
    return json.dumps(record, sort_keys=True).encode()


def mentions(dumped: str, value: str) -> bool:
    """Whether `value` occurs as a whole token, so "US" is not in "AMBIGUOUS"."""
    pattern = rf"(?<![A-Za-z0-9]){re.escape(value)}(?![A-Za-z0-9])"
    return re.search(pattern, dumped) is not None


def assert_keeps_only_place_id(seen, *results, text=()):
    """G26: no Google name, component text or coordinate in the result or any
    blob; each blob is exactly place ID, outcome and fingerprint; the key
    appears in neither, nor in any source call's query."""
    google = set(text)
    for result in results:
        google.add(result["formatted_address"])
        for part in result["address_components"]:
            google.update((part["long_name"], part["short_name"]))
        google.update(repr(v) for v in result["geometry"]["location"].values())
    kept = [seen.result.model_dump_json(), repr(seen.result)]
    kept += [blob.decode() for blob in seen.blobs.puts]
    for dumped in kept:
        assert MAPS_KEY not in dumped
        assert [value for value in google if mentions(dumped, value)] == []
    for blob in seen.blobs.puts:
        assert set(json.loads(blob)) == {"place_id", "outcome", "response_sha256"}
    for call in seen.result.sub_calls:
        assert list(call.query) == ["address"]


def test_one_get_with_the_address_the_environment_key_and_a_ten_second_timeout(
    monkeypatch,
):
    monkeypatch.setenv(KEY_VARIABLE, MAPS_KEY)

    seen = geocode(QUERY, reply(DAVAO), api_key=None)

    (request,) = seen.requests
    assert request.method == "GET"
    assert f"{request.url.scheme}://{request.url.host}{request.url.path}" == (
        "https://maps.googleapis.com/maps/api/geocode/json"
    )
    assert GEOCODING_URL == "https://maps.googleapis.com/maps/api/geocode/json"
    assert dict(request.url.params) == {"address": ADDRESS, "key": MAPS_KEY}
    assert request.extensions["timeout"] == dict.fromkeys(
        ("connect", "read", "write", "pool"), 10
    )
    assert seen.reservations == [] and not seen.client_closed
    assert TOOL_VERSION == "google-geocoding-v2" and GEOCODING_COST_MICROS == 5000


def test_one_result_confirms_only_the_fields_whose_component_names_match():
    answer = reply(DAVAO)

    seen = geocode(QUERY, answer)

    result = seen.result
    assert (result.tool, result.tool_version) == ("geography_lookup", TOOL_VERSION)
    assert result.outcome == S.SUCCESS
    assert result.field_outcomes == {
        "city": S.SUCCESS,
        "county": S.SUCCESS,
        "country": S.NO_MATCH,  # "P.I." is not Google's "Philippines".
    }
    assert result.warnings == []
    assert result.places == [
        PlaceCandidate(
            field_key=field_key,
            source="google-maps-geocoding",
            source_record_id="place-davao-city",
        )
        for field_key in ("city", "county")
    ]
    assert result.georeferences == [] and result.checks == [] and result.taxa == []
    (call,) = result.sub_calls
    assert (call.source, call.query, call.attempt) == (
        "google-maps-geocoding",
        {"address": ADDRESS},
        1,
    )
    assert (call.outcome, call.sanitized_error, call.retry_after_seconds) == (
        S.SUCCESS,
        None,
        None,
    )
    assert call.response_sha256 == sha(answer[1])
    assert seen.blobs.puts == [fingerprint("place-davao-city", S.SUCCESS, answer[1])]
    assert seen.blobs.get(call.raw_ref) == seen.blobs.puts[0]
    assert_keeps_only_place_id(seen, DAVAO)


def test_aliases_let_a_notation_match():
    seen = geocode(QUERY, reply(DAVAO), aliases={"p i": ["philippines"]})

    assert seen.result.field_outcomes == dict.fromkeys(FIELDS, S.SUCCESS)
    assert [p.field_key for p in seen.result.places] == list(FIELDS)
    assert {p.source_record_id for p in seen.result.places} == {"place-davao-city"}
    assert_keeps_only_place_id(seen, DAVAO)


ADMIN = (
    ("city", "Davao City"),
    ("county", "Davao del Sur"),
    ("province_state", "Davao Prov."),
    ("country", "P.I."),
)


@pytest.mark.parametrize(
    "options",
    [{}, {"aliases": {"p i": ["philippines"]}}],
    ids=["no-aliases", "aliases"],
)
@pytest.mark.parametrize(
    "admin", [ADMIN[2:], ADMIN], ids=["label-literals", "every-admin-level"]
)
def test_a_result_for_the_wrong_place_settles_no_admin_field(admin, options):
    # Regression: Google puts "Mt. McKinley" at Denali, Alaska. Each admin field
    # is checked against its own reader literal, so none of them settles.
    geography = query(
        (None, LABEL), ("precise_location", "E. slope Mt. McKinley"), *admin
    )

    seen = geocode(geography, reply(DENALI), **options)

    assert seen.requests[0].url.params["address"] == LABEL
    assert seen.result.outcome == S.SUCCESS
    assert seen.result.field_outcomes == {key: S.NO_MATCH for key, _ in admin}
    assert seen.result.places == [] and seen.result.warnings == []
    assert_keeps_only_place_id(seen, DENALI)


# G34: FMNH 105526330 reads "Chimaltenago"; Google's department and town are
# "Chimaltenango" (one result, no partial match; checked live 2026-09-24).
CHIMALTENANGO = place(
    "place-chimaltenango",
    component("Chimaltenango", "Chimaltenango", "locality", "political"),
    component("Chimaltenango", "Chimaltenango", "administrative_area_level_1"),
    component("Guatemala", "GT", "country", "political"),
    lat=14.6611,
    lng=-90.8208,
)
GUATEMALA = {"guat": ["guatemala"]}


def near(*pairs, answer=CHIMALTENANGO):
    payload = {"status": "OK", "results": [answer]}
    return map_geocoding_response(query(*pairs), 200, payload, GUATEMALA)


def test_a_near_spelling_the_other_fields_confirm_clears_with_the_place_id_only():
    geography = query(("province_state", "Chimaltenago"), ("country", "GUAT."))

    seen = geocode(geography, reply(CHIMALTENANGO), aliases=GUATEMALA)

    assert seen.result.field_outcomes == {
        "province_state": S.SUCCESS,
        "country": S.SUCCESS,
    }
    assert [(p.field_key, p.source_record_id, p.name) for p in seen.result.places] == [
        ("province_state", "place-chimaltenango", None),
        ("country", "place-chimaltenango", None),
    ]
    assert seen.result.warnings == ["near_spelling:province_state"]
    assert_keeps_only_place_id(seen, CHIMALTENANGO)


@pytest.mark.parametrize(
    "pairs",
    [
        (("province_state", "Chimaltinago"), ("country", "GUAT.")),
        (("province_state", "Chimaltenago"),),
        (("province_state", "Chimaltenago"), ("country", "P.I.")),
        (
            ("province_state", "Chimaltenago"),
            ("city", "Chimaltenago"),
            ("country", "GUAT."),
        ),
    ],
    ids=["two-edits", "no-other-field", "other-field-contradicts", "two-near"],
)
def test_a_near_spelling_clears_nothing_unless_every_condition_holds(pairs):
    outcome, fields, places, warnings = near(*pairs)

    assert outcome == S.SUCCESS and fields["province_state"] == S.NO_MATCH
    assert [p for p in places if p.field_key == "province_state"] == []
    assert warnings == []


def test_a_near_spelling_is_never_measured_against_a_code():
    # "P.I." is not a full name, and "PH" is a code, not a name: only the
    # profile's alias may confirm it (G34).
    geography = query(("city", "DAVAO CITY."), ("country", "P.I."))
    payload = {"status": "OK", "results": [DAVAO]}

    _, fields, _, warnings = map_geocoding_response(geography, 200, payload)

    assert fields == {"city": S.SUCCESS, "country": S.NO_MATCH} and warnings == []


def test_a_near_spelling_needs_exactly_one_such_component_at_the_fields_levels():
    twins = place(
        "place-twins",
        component("Chimaltenango", "Chimaltenango", "administrative_area_level_1"),
        component("Chimaltenaga", "Chimaltenaga", "administrative_area_level_2"),
        component("Guatemala", "GT", "country", "political"),
    )

    _, fields, _, warnings = near(
        ("province_state", "Chimaltenago"), ("country", "GUAT."), answer=twins
    )

    assert fields["province_state"] == S.NO_MATCH and warnings == []


@pytest.mark.parametrize(
    "answer",
    [
        reply(DAVAO),
        reply(DAVAO, DENALI),
        reply(status="ZERO_RESULTS"),
        reply(status="UNKNOWN_ERROR"),
    ],
    ids=["one-place", "two-places", "zero-results", "provider-error"],
)
@pytest.mark.parametrize(
    "aliases", [{}, {"p i": ["philippines"]}], ids=["no-aliases", "aliases"]
)
def test_the_precise_location_forms_the_address_but_is_never_settled(answer, aliases):
    seen = geocode(QUERY, answer, aliases=aliases)

    assert seen.requests[0].url.params["address"].startswith("Mt. Apo, ")
    assert "precise_location" not in seen.result.field_outcomes
    assert [p for p in seen.result.places if p.field_key == "precise_location"] == []


def test_unassigned_locality_text_forms_the_address_when_present():
    geography = query(
        (None, "E. slope Mt. McKinley"),
        ("country", "P.I."),
        (None, "Davao Prov., Mindanao, P.I."),
    )

    seen = geocode(geography, reply(status="ZERO_RESULTS"))

    assert seen.requests[0].url.params["address"] == LABEL
    assert seen.result.sub_calls[0].query == {"address": LABEL}
    assert seen.result.field_outcomes == {"country": S.NO_MATCH}


def test_assigned_literals_form_the_address_from_most_to_least_precise():
    geography = query(
        ("country", "P.I."),
        ("province_state", "Davao Prov."),
        ("city", "Davao"),
        ("county", "Davao del Sur"),
        ("precise_location", "E. slope Mt. McKinley"),
    )

    seen = geocode(geography, reply(status="ZERO_RESULTS"))

    address = "E. slope Mt. McKinley, Davao, Davao del Sur, Davao Prov., P.I."
    assert seen.requests[0].url.params["address"] == address
    assert seen.result.sub_calls[0].query == {"address": address}


def test_a_partial_match_is_ambiguous_for_every_field_even_when_names_match():
    seen = geocode(QUERY, reply({**DAVAO, "partial_match": True}))

    assert seen.result.outcome == S.AMBIGUOUS
    assert seen.result.field_outcomes == dict.fromkeys(FIELDS, S.AMBIGUOUS)
    assert seen.result.places == [] and len(seen.requests) == 1
    assert_keeps_only_place_id(seen, DAVAO)


def test_two_results_are_ambiguous_and_the_fingerprint_keeps_the_first_place_id():
    answer = reply(DAVAO, DENALI)

    seen = geocode(QUERY, answer)

    assert seen.result.outcome == S.AMBIGUOUS
    assert seen.result.field_outcomes == dict.fromkeys(FIELDS, S.AMBIGUOUS)
    assert seen.result.places == [] and len(seen.requests) == 1
    assert seen.blobs.puts == [fingerprint("place-davao-city", S.AMBIGUOUS, answer[1])]
    assert_keeps_only_place_id(seen, DAVAO, DENALI)


def test_zero_results_is_no_match_for_every_field_and_not_retried():
    answer = reply(status="ZERO_RESULTS")

    seen = geocode(QUERY, answer)

    (call,) = seen.result.sub_calls
    assert (seen.result.outcome, call.sanitized_error) == (S.NO_MATCH, None)
    assert seen.result.field_outcomes == dict.fromkeys(FIELDS, S.NO_MATCH)
    assert seen.result.places == [] and len(seen.requests) == 1
    assert seen.blobs.puts == [fingerprint(None, S.NO_MATCH, answer[1])]


def test_request_denied_is_an_authentication_error_and_not_retried():
    denied = reply(
        status="REQUEST_DENIED", error_message="This request was refused upstream."
    )

    seen = geocode(QUERY, denied)

    (call,) = seen.result.sub_calls
    assert (call.outcome, call.sanitized_error) == (
        S.AUTHENTICATION,
        "geocoding_authentication_error",
    )
    assert seen.result.field_outcomes == dict.fromkeys(FIELDS, S.AUTHENTICATION)
    assert_keeps_only_place_id(seen, text=("refused upstream",))


@pytest.mark.parametrize(
    "code,expected", [(401, S.AUTHENTICATION), (403, S.AUTHORIZATION)]
)
def test_a_rejected_key_is_a_credential_outcome_and_not_retried(code, expected):
    seen = geocode(QUERY, (code, b"Denied by the gateway", {}))

    (call,) = seen.result.sub_calls
    assert (call.outcome, call.sanitized_error) == (expected, f"geocoding_http_{code}")
    assert len(seen.requests) == 1 and seen.sleeps == []
    assert seen.result.outcome == expected
    assert seen.result.field_outcomes == dict.fromkeys(FIELDS, expected)
    assert_keeps_only_place_id(seen, text=("Denied by the gateway",))


def test_rate_limits_are_retried_and_every_attempt_is_recorded():
    limited, found = reply(status="OVER_QUERY_LIMIT"), reply(DAVAO)

    seen = geocode(QUERY, limited, limited, found, allow=lambda n: True)

    calls = seen.result.sub_calls
    assert [(c.attempt, c.outcome) for c in calls] == [
        (1, S.RATE_LIMITED),
        (2, S.RATE_LIMITED),
        (3, S.SUCCESS),
    ]
    assert len(seen.requests) == 3
    assert len(seen.sleeps) == 2 and all(delay > 0 for delay in seen.sleeps)
    assert seen.reservations == [GEOCODING_COST_MICROS] * 3
    assert seen.result.outcome == S.SUCCESS
    assert seen.result.field_outcomes["city"] == S.SUCCESS
    assert [c.sanitized_error for c in calls] == ["geocoding_rate_limited"] * 2 + [None]
    assert [c.response_sha256 for c in calls] == [
        sha(limited[1]),
        sha(limited[1]),
        sha(found[1]),
    ]
    assert seen.blobs.puts == [
        fingerprint(None, S.RATE_LIMITED, limited[1]),
        fingerprint(None, S.RATE_LIMITED, limited[1]),
        fingerprint("place-davao-city", S.SUCCESS, found[1]),
    ]
    assert_keeps_only_place_id(seen, DAVAO)


def test_http_429_is_rate_limited_and_waits_at_least_the_retry_after():
    throttled = (429, b"Too many requests from this client", {"Retry-After": "7"})

    seen = geocode(QUERY, throttled, reply(DAVAO))

    first, second = seen.result.sub_calls
    assert (first.outcome, first.retry_after_seconds, first.sanitized_error) == (
        S.RATE_LIMITED,
        7,
        "geocoding_http_429",
    )
    assert first.response_sha256 == sha(throttled[1])
    assert seen.blobs.get(first.raw_ref) == fingerprint(
        None, S.RATE_LIMITED, throttled[1]
    )
    assert len(seen.sleeps) == 1 and 7 <= seen.sleeps[0] <= 20
    assert second.outcome == seen.result.outcome == S.SUCCESS
    assert_keeps_only_place_id(seen, DAVAO, text=("Too many requests",))


def test_http_500_is_a_provider_error_after_three_attempts():
    broken = (500, b"Backend failure while geocoding", {})

    seen = geocode(QUERY, broken)

    calls = seen.result.sub_calls
    assert [c.outcome for c in calls] == [S.PROVIDER] * 3
    assert {c.sanitized_error for c in calls} == {"geocoding_http_500"}
    assert len(seen.requests) == 3 and len(seen.sleeps) == 2
    assert seen.result.outcome == S.PROVIDER
    assert seen.result.field_outcomes == dict.fromkeys(FIELDS, S.PROVIDER)
    assert seen.blobs.puts == [fingerprint(None, S.PROVIDER, broken[1])] * 3
    assert_keeps_only_place_id(seen, text=("Backend failure",))


def test_a_timeout_is_retried_then_final_and_stores_nothing():
    seen = geocode(QUERY, httpx.ReadTimeout("read timed out"))

    calls = seen.result.sub_calls
    assert [c.outcome for c in calls] == [S.TIMEOUT] * 3
    assert {c.sanitized_error for c in calls} == {"geocoding_timeout"}
    assert {(c.raw_ref, c.response_sha256) for c in calls} == {(None, None)}
    assert len(seen.requests) == 3 and len(seen.sleeps) == 2
    assert seen.result.outcome == S.TIMEOUT
    assert seen.result.field_outcomes == dict.fromkeys(FIELDS, S.TIMEOUT)
    assert seen.blobs.puts == []
    assert_keeps_only_place_id(seen, text=("timed out",))


def test_a_connection_failure_is_a_provider_error_and_stores_nothing():
    seen = geocode(QUERY, httpx.ConnectError("connection refused"))

    calls = seen.result.sub_calls
    assert [c.outcome for c in calls] == [S.PROVIDER] * 3
    assert {c.sanitized_error for c in calls} == {"geocoding_transport_error"}
    assert len(seen.requests) == 3 and seen.blobs.puts == []
    assert seen.result.field_outcomes == dict.fromkeys(FIELDS, S.PROVIDER)
    assert_keeps_only_place_id(seen, text=("connection refused",))


KEYED_URL = f"https://maps.googleapis.com/maps/api/geocode/json?key={MAPS_KEY}"


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError(f"cannot send {KEYED_URL}"),
        httpx.InvalidURL(f"Invalid URL {KEYED_URL!r}"),  # Outside httpx.HTTPError.
    ],
    ids=["not-httpx", "invalid-url"],
)
def test_any_other_failure_is_a_fixed_provider_error_that_never_carries_the_key(
    failure, caplog
):
    caplog.set_level(logging.DEBUG)

    seen = geocode(QUERY, failure)

    calls = seen.result.sub_calls
    assert [c.outcome for c in calls] == [S.PROVIDER] * 3
    assert {c.sanitized_error for c in calls} == {"geocoding_unexpected_error"}
    assert len(seen.requests) == 3 and seen.blobs.puts == []
    assert seen.result.field_outcomes == dict.fromkeys(FIELDS, S.PROVIDER)
    assert_keeps_only_place_id(seen, text=("cannot send", "Invalid URL"))
    assert MAPS_KEY not in caplog.text


def test_a_body_that_is_not_json_is_malformed_and_not_retried():
    page = (200, b"<html>Service page text</html>", {})

    seen = geocode(QUERY, page)

    (call,) = seen.result.sub_calls
    assert (call.outcome, call.sanitized_error) == (
        S.MALFORMED,
        "geocoding_malformed_response",
    )
    assert seen.result.field_outcomes == dict.fromkeys(FIELDS, S.MALFORMED)
    assert seen.blobs.puts == [fingerprint(None, S.MALFORMED, page[1])]
    assert_keeps_only_place_id(seen, text=("Service page text",))


@pytest.mark.parametrize(
    "environment,api_key",
    [(None, None), ("", None), ("   ", None), (MAPS_KEY, "")],
    ids=["unset", "empty", "blank", "explicitly-empty"],
)
def test_a_missing_key_is_an_authentication_outcome_without_any_request(
    monkeypatch, environment, api_key
):
    if environment is None:
        monkeypatch.delenv(KEY_VARIABLE, raising=False)
    else:
        monkeypatch.setenv(KEY_VARIABLE, environment)

    seen = geocode(QUERY, reply(DAVAO), api_key=api_key, allow=lambda n: True)

    assert seen.requests == [] and seen.reservations == [] and seen.blobs.puts == []
    assert seen.result.outcome == S.AUTHENTICATION
    assert seen.result.field_outcomes == dict.fromkeys(FIELDS, S.AUTHENTICATION)
    assert seen.result.places == []
    (call,) = seen.result.sub_calls
    assert (call.source, call.query, call.outcome, call.sanitized_error) == (
        "google-maps-geocoding",
        {"address": ADDRESS},
        S.AUTHENTICATION,
        "maps_key_not_configured",
    )


def test_a_refused_budget_is_policy_blocked_without_any_request():
    seen = geocode(QUERY, reply(DAVAO), allow=lambda n: False)

    assert seen.requests == [] and seen.reservations == [GEOCODING_COST_MICROS]
    assert seen.result.outcome == S.POLICY
    assert seen.result.field_outcomes == dict.fromkeys(FIELDS, S.POLICY)
    (call,) = seen.result.sub_calls
    assert (call.outcome, call.sanitized_error, call.raw_ref) == (
        S.POLICY,
        "cost_budget_exhausted",
        None,
    )


def test_every_retry_reserves_its_cost_before_it_is_sent():
    seen = geocode(QUERY, (429, b"slow down", {}), allow=lambda n: n == 1)

    assert len(seen.requests) == 1
    assert seen.reservations == [GEOCODING_COST_MICROS] * 2
    assert [c.outcome for c in seen.result.sub_calls] == [S.RATE_LIMITED, S.POLICY]
    assert seen.result.outcome == S.POLICY


@pytest.mark.parametrize(
    "answer",
    [
        reply(DAVAO),
        reply(DAVAO, DENALI),
        reply({**DENALI, "partial_match": True}),
        reply(DENALI, status="UNKNOWN_ERROR"),
    ],
    ids=["success", "two-results", "partial-match", "error-with-results"],
)
def test_only_place_id_outcome_and_fingerprint_leave_the_tool(answer):
    seen = geocode(QUERY, answer)

    assert seen.blobs.puts
    assert_keeps_only_place_id(seen, DAVAO, DENALI)


@pytest.mark.parametrize(
    "http_status,payload,expected",
    [
        (200, {"status": "OK", "results": [DAVAO, DENALI]}, S.AMBIGUOUS),
        (
            200,
            {"status": "OK", "results": [{**DAVAO, "partial_match": True}]},
            S.AMBIGUOUS,
        ),
        (200, {"status": "ZERO_RESULTS", "results": []}, S.NO_MATCH),
        (200, {"status": "OVER_QUERY_LIMIT", "results": []}, S.RATE_LIMITED),
        (200, {"status": "OVER_DAILY_LIMIT", "results": []}, S.AUTHENTICATION),
        (200, {"status": "REQUEST_DENIED", "results": []}, S.AUTHENTICATION),
        (200, {"status": "UNKNOWN_ERROR", "results": []}, S.PROVIDER),
        (200, {"status": "INVALID_REQUEST", "results": []}, S.MALFORMED),
        (200, {"status": "NOT_A_STATUS", "results": [DAVAO]}, S.MALFORMED),
        (200, {"results": [DAVAO]}, S.MALFORMED),
        (200, {"status": ["OK"], "results": [DAVAO]}, S.MALFORMED),
        (200, {"status": "OK", "results": []}, S.MALFORMED),
        (200, {"status": "OK", "results": {"0": DAVAO}}, S.MALFORMED),
        (200, {"status": "OK", "results": [{"formatted_address": "x"}]}, S.MALFORMED),
        (200, [DAVAO], S.MALFORMED),
        (200, None, S.MALFORMED),
        (429, None, S.RATE_LIMITED),
        (401, {"status": "OK", "results": [DAVAO]}, S.AUTHENTICATION),
        (403, {"status": "OK", "results": [DAVAO]}, S.AUTHORIZATION),
        (503, {"status": "OK", "results": [DAVAO]}, S.PROVIDER),
    ],
)
def test_every_response_maps_to_one_outcome_that_every_field_shares(
    http_status, payload, expected
):
    outcome, fields, places, _ = map_geocoding_response(QUERY, http_status, payload)

    assert (outcome, fields, places) == (expected, dict.fromkeys(FIELDS, expected), [])


@pytest.mark.parametrize(
    "field_key,component_type,expected",
    [
        ("country", "country", S.SUCCESS),
        ("province_state", "administrative_area_level_1", S.SUCCESS),
        ("province_state", "administrative_area_level_2", S.SUCCESS),
        ("county", "administrative_area_level_2", S.SUCCESS),
        ("county", "administrative_area_level_3", S.SUCCESS),
        ("city", "locality", S.SUCCESS),
        ("city", "postal_town", S.SUCCESS),
        ("city", "administrative_area_level_3", S.SUCCESS),
        ("city", "sublocality", S.SUCCESS),
        ("country", "administrative_area_level_1", S.NO_MATCH),
        ("province_state", "country", S.NO_MATCH),
        ("province_state", "administrative_area_level_3", S.NO_MATCH),
        ("county", "administrative_area_level_1", S.NO_MATCH),
        ("county", "locality", S.NO_MATCH),
        ("city", "administrative_area_level_2", S.NO_MATCH),
        ("city", "neighborhood", S.NO_MATCH),
        ("island", "colloquial_area", S.NO_MATCH),
    ],
)
def test_a_field_is_confirmed_only_by_a_component_at_its_own_level(
    field_key, component_type, expected
):
    found = place("place-sao-paulo", component("São Paulo", "SP", component_type))

    outcome, fields, places, _ = map_geocoding_response(
        query((field_key, "  SÃO   PAULO. ")), 200, {"status": "OK", "results": [found]}
    )

    assert outcome == S.SUCCESS and fields == {field_key: expected}
    confirmed = PlaceCandidate(
        field_key=field_key,
        source="google-maps-geocoding",
        source_record_id="place-sao-paulo",
    )
    assert places == ([confirmed] if expected == S.SUCCESS else [])


@pytest.mark.parametrize(
    "short_name,literals,expected",
    [
        ("US", ["US"], S.SUCCESS),  # The short name counts.
        # Punctuation is a space, as in S8's tool: "U.S." needs an alias, as
        # "P.I." does, and "United-States" is "united states".
        ("US", ["U.S."], S.NO_MATCH),
        ("US", ["United-States"], S.SUCCESS),
        ("US", ["UNITED STATES.", "united  states"], S.SUCCESS),
        ("US", ["United States", "USA"], S.NO_MATCH),  # Every literal must match.
        ("", ["?"], S.NO_MATCH),  # Nothing left to compare never matches.
    ],
)
def test_names_compare_after_folding_and_every_literal_of_a_field_must_match(
    short_name, literals, expected
):
    found = place("place-usa", component("United States", short_name, "country"))
    geography = query(*(("country", literal) for literal in literals))

    _, fields, _, _ = map_geocoding_response(
        geography, 200, {"status": "OK", "results": [found]}
    )

    assert fields == {"country": expected}


def test_without_a_client_the_tool_opens_and_closes_its_own(monkeypatch):
    real_client, opened = httpx.Client, []
    body = reply(DAVAO)[1]

    def fake_client(*args, **kwargs):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, content=body)
        )
        opened.append(real_client(transport=transport))
        return opened[-1]

    monkeypatch.setattr(httpx, "Client", fake_client)

    result = geocode_locality(QUERY, blobs=Blobs(), api_key=MAPS_KEY)

    assert result.outcome == S.SUCCESS
    assert len(opened) == 1 and opened[0].is_closed


NOTATION_WORDS = (
    "prov",
    "province",
    "provincia",
    "dept",
    "department",
    "depto",
    "departamento",
    "co",
    "county",
    "mun",
    "municipio",
    "municipality",
    "estado",
    "state",
    "region",
)


@pytest.mark.parametrize("word", NOTATION_WORDS)
def test_notation_words_are_dropped_before_comparing(word):
    assert comparison_key(f"Davao {word.title()}.") == "davao"
    assert comparison_key(f"{word.upper()} Davao") == "davao"


def test_only_whole_notation_words_are_dropped():
    assert comparison_key("Davao Prov.") == "davao"
    assert comparison_key("Colorado Statehood, Regional") == (
        "colorado statehood regional"
    )
    assert comparison_key("Región") == ""


@pytest.mark.parametrize(
    "field_key,component_type,literal,google_name,expected",
    [
        (
            "province_state",
            "administrative_area_level_1",
            "Davao Prov.",
            "Davao",
            S.SUCCESS,
        ),
        (
            "province_state",
            "administrative_area_level_1",
            "Davao Prov.",
            "Davao Region",
            S.SUCCESS,
        ),
        ("county", "administrative_area_level_2", "Cook Co.", "Cook County", S.SUCCESS),
        (
            "province_state",
            "administrative_area_level_1",
            "Depto. Cusco",
            "Cusco",
            S.SUCCESS,
        ),
        (
            "province_state",
            "administrative_area_level_1",
            "Provincia de Cusco",
            "Cusco",
            S.SUCCESS,  # A link word after a leading unit word goes too.
        ),
        (
            "province_state",
            "administrative_area_level_1",
            "Prov.",
            "Province",
            S.NO_MATCH,
        ),
    ],
)
def test_notations_compare_by_the_name_they_qualify(
    field_key, component_type, literal, google_name, expected
):
    found = place("place-notation", component(google_name, google_name, component_type))

    _, fields, _, _ = map_geocoding_response(
        query((field_key, literal)), 200, {"status": "OK", "results": [found]}
    )

    assert fields == {field_key: expected}


@pytest.mark.parametrize(
    "aliases,expected",
    [
        ({}, S.NO_MATCH),
        ({"p i": ["philippines"]}, S.SUCCESS),
        ({"p i": ["republic of the philippines", "ph"]}, S.SUCCESS),
        ({"P.I.": ["Philippines"]}, S.SUCCESS),  # Folded here like the literals.
        ({"p i": "philippines"}, S.SUCCESS),  # A bare string is one name.
        ({"p i": ["republic of the philippines"]}, S.NO_MATCH),  # Not Google's name.
        ({"philippines": ["p i"]}, S.NO_MATCH),  # Keyed by the literal.
        ({"pi": ["philippines"]}, S.NO_MATCH),  # "P.I." folds to "p i" (S8's fold).
    ],
    ids=[
        "none",
        "folded",
        "several-names",
        "unfolded",
        "bare-string",
        "not-a-google-name",
        "reversed",
        "unspaced-key",
    ],
)
def test_aliases_add_names_that_count_as_matches(aliases, expected):
    outcome, fields, places, _ = map_geocoding_response(
        query(("country", "P.I.")),
        200,
        {"status": "OK", "results": [DAVAO]},
        aliases=aliases,
    )

    assert outcome == S.SUCCESS and fields == {"country": expected}
    assert len(places) == (1 if expected == S.SUCCESS else 0)


def test_httpx_request_logs_carry_no_key(caplog):
    caplog.set_level(logging.INFO, logger="httpx")

    geocode(QUERY, reply(DAVAO))

    (line,) = [r.getMessage() for r in caplog.records if r.name == "httpx"]
    assert "key=[redacted]" in line and "maps.googleapis.com" in line
    assert MAPS_KEY not in caplog.text


def test_the_key_filter_rewrites_only_records_that_carry_a_key():
    redact = geography_tool.RedactMapsKey()
    url = f"https://maps.example/json?key={MAPS_KEY}&address=Davao"
    keyed = logging.LogRecord(
        "httpx", logging.INFO, __file__, 1, "HTTP Request: GET %s", (url,), None
    )
    plain = logging.LogRecord(
        "httpx", logging.INFO, __file__, 1, "GET %s", ("https://x.example/?q=1",), None
    )

    assert redact.filter(keyed) and redact.filter(plain)
    assert keyed.getMessage() == (
        "HTTP Request: GET https://maps.example/json?key=[redacted]&address=Davao"
    )
    assert (plain.msg, plain.args) == ("GET %s", ("https://x.example/?q=1",))


def test_the_key_filter_is_installed_once_at_import():
    httpx_logger = logging.getLogger("httpx")
    installed = list(httpx_logger.filters)

    geography_tool.install_key_redaction()
    geography_tool.install_key_redaction()

    assert httpx_logger.filters == installed
    assert sum(isinstance(f, geography_tool.RedactMapsKey) for f in installed) == 1


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("chimaltenago", "chimaltenango", 1),  # One insertion.
        ("chimaltenango", "chimaltenago", 1),  # One deletion.
        ("chimaltenaga", "chimaltenago", 1),  # One substitution.
        ("davao", "davao", 0),
        ("chimaltinago", "chimaltenango", 2),  # Two edits.
        ("pi", "philippines", 2),  # Counted up to two.
        ("ab", "ba", 2),  # A transposition is two edits.
        ("", "a", 1),
    ],
)
def test_letters_apart_counts_single_character_edits(a, b, expected):
    assert geography_tool._letters_apart(a, b) == expected


def test_folding_turns_punctuation_into_spaces_as_s8s_tool_does():
    assert fold("P.I.") == "p i"
    assert fold("Chimaltenángo,") == "chimaltenango"
    assert fold("E.slope Volcan  Fuego") == "e slope volcan fuego"


@pytest.mark.parametrize(
    ("written", "key"),
    [
        ("Mt. Banahao", "mount banahao"),
        ("Mount Banahao", "mount banahao"),
        ("Depto. de Chimaltenango", "chimaltenango"),
        ("Departamento de Guatemala", "guatemala"),
        ("Mun. Yepocapa", "yepocapa"),
        ("Isle of Pines", "isle of pines"),  # "of" links only after a unit word.
    ],
)
def test_the_comparison_key_reads_features_and_drops_unit_words(written, key):
    assert comparison_key(written) == key


@pytest.mark.parametrize(
    ("literal", "name", "near"),
    [
        ("Chimaltenago", "Chimaltenango", True),
        ("Chimaltenango", "Chimaltenango", False),  # Exactly one letter, not none.
        ("Chimaltinago", "Chimaltenango", False),  # Two letters.
        ("P.I.", "PH", False),  # Neither is a full name.
        ("Guat.", "Guatemala", False),
        ("RP", "Rp", False),
    ],
)
def test_a_near_spelling_needs_two_full_names_one_letter_apart(literal, name, near):
    assert one_letter_apart(literal, name) is near


def test_a_unit_word_before_the_name_still_matches_googles_component():
    geography = query(
        ("province_state", "Depto. de Chimaltenango"), ("country", "GUAT.")
    )
    payload = {"status": "OK", "results": [CHIMALTENANGO]}

    _, fields, _, warnings = map_geocoding_response(geography, 200, payload, GUATEMALA)

    assert fields == {"province_state": S.SUCCESS, "country": S.SUCCESS}
    assert warnings == []
