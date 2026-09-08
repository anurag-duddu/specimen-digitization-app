from test_authority_registry import authority_server as authority_server
import json

import httpx
import pytest

from test_authority_registry import Blobs, query, source
from specimen_digitization.application.authority_registry import AuthorityRegistry
from specimen_digitization.application.geography import GeographyAdapter


def payload():
    return {
        "results": [
            {
                "id": "USA.14_1",
                "name": "Illinois",
                "gadmLevel": 1,
                "variantName": ["Ill."],
                "higherRegions": [{"id": "USA", "name": "United States"}],
            }
        ],
        "endOfRecords": True,
    }


def service(client, **changes):
    blobs = Blobs()
    return GeographyAdapter(
        AuthorityRegistry(version="1", sources=(source(**changes),)), blobs, client
    ), blobs


def test_actual_http_geography_success_historical_ambiguity_and_literal_preservation(
    authority_server,
):
    state, client = authority_server
    state["body"] = json.dumps(payload()).encode()
    adapter, blobs = service(client)
    result = adapter.lookup(query())
    assert result.status == "success" and result.literal == "Illinois"
    assert result.candidates[0].relation == "supports"
    assert blobs.values[result.raw_ref] == state["body"]
    historic = adapter.lookup(
        query(historical_context="jurisdiction in 1800 unconfirmed")
    )
    assert (
        historic.status == "ambiguous"
        and historic.candidates[0].relation == "unresolved"
    )
    assert "1800" in historic.candidates[0].context_json
    assert historic.input_sha256 != result.input_sha256


@pytest.mark.parametrize(
    "body,status",
    [
        (b"", "empty_response"),
        (b"{", "malformed_response"),
        (b'{"results":[],"endOfRecords":true}', "no_match"),
        (b'{"results":[],"endOfRecords":false}', "ambiguous"),
        (b'{"results":[{}],"endOfRecords":true}', "malformed_response"),
    ],
)
def test_geography_empty_and_schema_outcomes(authority_server, body, status):
    state, client = authority_server
    state["body"] = body
    result = service(client)[0].lookup(query())
    assert result.status == status and result.response_sha256


@pytest.mark.parametrize(
    "code,status",
    [
        (401, "authentication_error"),
        (403, "authorization_error"),
        (429, "rate_limited"),
        (500, "provider_error"),
    ],
)
def test_geography_operational_http_outcomes(authority_server, code, status):
    state, client = authority_server
    state.update(status=code, body=b"provider failure")
    result = service(client)[0].lookup(query())
    assert result.status == status and result.operationally_blocked


def test_geography_oversize_is_bounded_and_not_a_match(authority_server):
    state, client = authority_server
    state["body"] = b"x" * 10000
    adapter, blobs = service(client, max_response_bytes=256)
    result = adapter.lookup(query())
    assert (
        result.status == "malformed_response"
        and "response_capture_truncated" in result.reasons
    )
    assert len(blobs.values[result.raw_ref]) == 256


def test_geography_timeout_not_no_match():
    def timeout(request):
        raise httpx.ConnectTimeout("synthetic")

    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        assert service(client)[0].lookup(query()).status == "timeout"
