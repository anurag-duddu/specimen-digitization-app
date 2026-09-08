from test_authority_registry import authority_server as authority_server
import json
from urllib.parse import parse_qs

import httpx
import pytest
from pydantic import SecretStr

from test_authority_registry import Blobs, query, source
from specimen_digitization.application.authority_registry import AuthorityRegistry
from specimen_digitization.application.parties import PartiesAdapter, PartiesConnection


def adapter(client=None, approved=True, token=True):
    blobs = Blobs()
    return PartiesAdapter(
        AuthorityRegistry(version="1", sources=(source(True, approved=approved),)),
        blobs,
        PartiesConnection(
            source_id="parties",
            source_system="emu",
            connection_id="synthetic-read",
            tenant="fmnh",
            environment="synthetic",
        ),
        SecretStr("synthetic-token") if token else None,
        client,
    ), blobs


def payload(irn="emu:/fmnh/eparties/7", name="Illinois", hits=1):
    return {
        "hits": hits,
        "matches": [{"id": irn, "version": 1, "data": {"NamFullName": name}}]
        if hits
        else [],
    }


def test_real_http_read_only_search_preserves_qualified_candidate_without_claiming_person_match(
    authority_server,
):
    state, client = authority_server
    state["body"] = json.dumps(payload()).encode()
    service, blobs = adapter(client)
    result = service.lookup(query())
    assert result.status == "ambiguous"
    assert result.candidates[0].identity.irn == 7
    assert result.candidates[0].identity.connection_id == "synthetic-read"
    assert (
        result.evidence_ids == result.candidates[0].evidence_ids == query().evidence_ids
    )
    assert blobs.values[result.raw_ref] == state["body"]
    assert "synthetic-token" not in result.model_dump_json()
    method, path, headers, body = state["requests"][0]
    assert method == "POST" and path == "/fmnh/eparties"
    assert headers["X-HTTP-Method-Override"] == "GET"
    assert parse_qs(body.decode())["select"] == ["id,version,data.NamFullName"]


@pytest.mark.parametrize(
    "body,status",
    [
        (payload(hits=0), "no_match"),
        (payload("emu:/fmnh/ecatalogue/7"), "malformed_response"),
        (payload("emu:/other/eparties/7"), "malformed_response"),
        ({"hits": 1, "matches": []}, "empty_response"),
        ({"hits": True, "matches": []}, "malformed_response"),
        ([], "malformed_response"),
    ],
)
def test_parties_data_outcomes(authority_server, body, status):
    state, client = authority_server
    state["body"] = json.dumps(body).encode()
    assert adapter(client)[0].lookup(query()).status == status


@pytest.mark.parametrize(
    "code,status",
    [
        (401, "authentication_error"),
        (403, "authorization_error"),
        (429, "rate_limited"),
        (503, "provider_error"),
        (302, "provider_error"),
    ],
)
def test_parties_http_failures_retained_without_redirect_or_retry(
    authority_server, code, status
):
    state, client = authority_server
    state.update(
        status=code,
        body=b"failure",
        headers={"Retry-After": "12", "Location": "https://unapproved.example"},
    )
    result = adapter(client)[0].lookup(query())
    assert result.status == status and result.retry_after_seconds == 12
    assert result.response_sha256 and len(state["requests"]) == 1


def test_parties_missing_access_has_no_network(authority_server):
    state, client = authority_server
    assert adapter(client, approved=False)[0].lookup(query()).status == "policy_blocked"
    assert (
        adapter(client, token=False)[0].lookup(query()).status == "authentication_error"
    )
    assert (
        PartiesAdapter(AuthorityRegistry(version="1"), Blobs(), client=client)
        .lookup(query())
        .status
        == "policy_blocked"
    )
    assert not state["requests"]


def test_parties_timeout_is_operational():
    def timeout(request):
        raise httpx.ReadTimeout("synthetic timeout")

    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        result = adapter(client)[0].lookup(query())
    assert result.status == "timeout" and result.operationally_blocked
