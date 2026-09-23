"""The taxonomy_verifier tool: HARNESS.md section 6 (G23, G25, G28; GBIF.md 118-130)."""

import json

import httpx
import pytest

from specimen_digitization.application.domain import LookupStatus as S
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.application.taxonomy_tool import query_name, verify_taxon

INSECTA = [{"rank": "CLASS", "name": "Insecta"}]


def usage(name, rank, status="ACCEPTED", key="K1"):
    return {"key": key, "name": name, "rank": rank, "status": status}


def alternative(name, match, status, key):
    return {
        "usage": {"key": key, "name": name, "status": status},
        "diagnostics": {"matchType": match},
    }


def gbif(match, found=None, alternatives=(), classification=INSECTA, accepted=None):
    body = {
        "usage": found,
        "classification": classification,
        "diagnostics": {
            "matchType": match,
            "confidence": 99,
            "alternatives": list(alternatives),
        },
    }
    if accepted:
        body["acceptedUsage"] = accepted
    return body


GNV_EXACT = {
    "names": [{"matchType": "Exact", "bestResult": {"taxonomicStatus": "Accepted"}}]
}
GNV_NONE = {"names": [{"matchType": "NoMatch"}]}
COL_ACCEPTED = {
    "type": "variant",
    "match": True,
    "usage": {"name": "Epipsocus", "status": "accepted"},
}
COL_NONE = {"type": "none", "match": False}


def transport(*gbif_replies, gnv=GNV_EXACT, col=COL_ACCEPTED, seen=None):
    replies = iter(gbif_replies)

    def handler(request):
        (seen if seen is not None else []).append(request.url.host + request.url.path)
        if request.url.path.endswith("/metadata"):
            return httpx.Response(200, json={"alias": "fixture-index"})
        if request.url.host == "api.gbif.org":
            reply = next(replies)
            return (
                reply
                if isinstance(reply, httpx.Response)
                else httpx.Response(200, json=reply)
            )
        if request.url.host == "verifier.globalnames.org":
            return (
                gnv
                if isinstance(gnv, httpx.Response)
                else httpx.Response(200, json=gnv)
            )
        return col if isinstance(col, httpx.Response) else httpx.Response(200, json=col)

    return httpx.Client(transport=httpx.MockTransport(handler))


def run(tmp_path, literal, client):
    return verify_taxon(
        literal, blobs=LocalBlobs(tmp_path), client=client, sleep=lambda s: None
    )


@pytest.mark.parametrize(
    "literal,expected",
    [
        ("Epipsocus sp. 1", "Epipsocus"),
        ("Epipsocus\nSp. 1", "Epipsocus"),
        ("Apis mellifera L.", "Apis mellifera"),
        ("Sp. 30 ♀", None),
        ("sp 22", None),
    ],
)
def test_the_query_is_the_name_the_literal_writes(literal, expected):
    assert query_name(literal) == expected


def test_an_exact_accepted_genus_satisfies_a_genus_only_label(tmp_path):
    reply = gbif(
        "EXACT",
        usage("Epipsocus Hagen, 1866", "GENUS"),
        [
            alternative("Epipsocus Hagen, 1866", "EXACT", "SYNONYM", "K2"),
            alternative("Epipsocus Badonnel, 1955", "EXACT", "SYNONYM", "K3"),
            alternative(
                "Epipocus Chevrolat in Dejean, 1836", "VARIANT", "ACCEPTED", "K4"
            ),
        ],
    )

    result, lookup = run(tmp_path, "Epipsocus sp. 1", transport(reply))

    assert result.outcome == S.SUCCESS == lookup.status
    assert [(t.usage_key, t.rank, t.status) for t in result.taxa] == [
        ("K1", "GENUS", "ACCEPTED")
    ]
    assert [c.source for c in result.sub_calls] == ["gbif", "gnv", "col"]
    assert result.warnings == []


@pytest.mark.parametrize(
    "reply,why",
    [
        (
            gbif("VARIANT", usage("Epipocus Chevrolat in Dejean, 1836", "GENUS")),
            "a variant is not the label's name",
        ),
        (gbif("FUZZY", usage("Epipsocus Hagen, 1866", "GENUS")), "fuzzy"),
        (gbif("HIGHERRANK", usage("Apis Linnaeus, 1758", "GENUS")), "higher rank only"),
        (
            gbif(
                "EXACT",
                usage("Apis mellifera Linnaeus, 1758", "SPECIES", "SYNONYM"),
                accepted={"key": "A1"},
            ),
            "exact synonym",
        ),
        (
            gbif(
                "EXACT",
                usage("Apis mellifera Linnaeus, 1758", "SPECIES"),
                [alternative("Apis mellifera Smith, 1850", "EXACT", "ACCEPTED", "K9")],
            ),
            "live homonym",
        ),
        (
            gbif(
                "EXACT",
                usage("Apis mellifera Linnaeus, 1758", "SPECIES"),
                classification=[{"rank": "CLASS", "name": "Arachnida"}],
            ),
            "not an insect",
        ),
        (
            gbif("EXACT", usage("Apis Linnaeus, 1758", "GENUS")),
            "a binomial matched at genus",
        ),
    ],
)
def test_only_the_gbif_md_row_one_match_succeeds(tmp_path, reply, why):
    result, _ = run(tmp_path, "Apis mellifera", transport(reply))

    assert result.outcome == S.AMBIGUOUS, why


def test_a_same_name_duplicate_is_not_a_plausible_alternative(tmp_path):
    reply = gbif(
        "EXACT",
        usage("Apis mellifera Linnaeus, 1758", "SPECIES"),
        [
            alternative(
                "Apis mellifera Linnaeus, 1758", "EXACT", "PROVISIONALLY_ACCEPTED", "K2"
            )
        ],
    )

    assert run(tmp_path, "Apis mellifera", transport(reply)).result.outcome == S.SUCCESS


def test_an_exact_synonym_keeps_the_label_name_and_proposes_the_accepted_usage(
    tmp_path,
):
    reply = gbif(
        "EXACT",
        usage("Apis mellifica Linnaeus, 1761", "SPECIES", "SYNONYM", "S1"),
        accepted={"key": "A1"},
    )

    result, _ = run(tmp_path, "Apis mellifica", transport(reply))

    assert result.outcome == S.AMBIGUOUS
    assert (result.taxa[0].usage_key, result.taxa[0].accepted_usage_key) == ("S1", "A1")


def test_supporting_sources_never_change_gbif_outcome_but_disagreement_is_a_warning(
    tmp_path,
):
    reply = gbif("EXACT", usage("Epipsocus Hagen, 1866", "GENUS"))

    result, _ = run(tmp_path, "Epipsocus", transport(reply, gnv=GNV_NONE, col=COL_NONE))

    assert result.outcome == S.SUCCESS
    assert result.warnings == [
        "taxonomy_source_disagreement:gnv",
        "taxonomy_source_disagreement:col",
    ]


def test_an_unavailable_supporting_source_is_not_a_disagreement(tmp_path):
    reply = gbif("EXACT", usage("Epipsocus Hagen, 1866", "GENUS"))

    result, _ = run(tmp_path, "Epipsocus", transport(reply, gnv=httpx.Response(503)))

    assert result.outcome == S.SUCCESS
    assert result.warnings == ["taxonomy_support_unavailable:gnv"]
    assert [c.outcome for c in result.sub_calls if c.source == "gnv"] == [
        S.PROVIDER
    ] * 3


def test_a_gbif_rate_limit_is_retried_and_every_attempt_recorded(tmp_path):
    limited = httpx.Response(429, headers={"Retry-After": "1"})
    reply = gbif("EXACT", usage("Epipsocus Hagen, 1866", "GENUS"))

    result, _ = run(tmp_path, "Epipsocus", transport(limited, limited, reply))

    gbif_calls = [c for c in result.sub_calls if c.source == "gbif"]
    assert [(c.attempt, c.outcome) for c in gbif_calls] == [
        (1, S.RATE_LIMITED),
        (2, S.RATE_LIMITED),
        (3, S.SUCCESS),
    ]
    assert result.outcome == S.SUCCESS


def test_a_label_without_a_scientific_name_makes_no_request(tmp_path):
    seen = []

    result, lookup = run(tmp_path, "Sp. 30 ♀", transport(seen=seen))

    assert result.outcome == S.NO_MATCH == lookup.status
    assert result.warnings == ["no_scientific_name"] and seen == []


def test_every_source_response_is_stored_with_its_digest(tmp_path):
    reply = gbif("EXACT", usage("Epipsocus Hagen, 1866", "GENUS"))

    result, _ = run(tmp_path, "Epipsocus", transport(reply))

    for call in result.sub_calls:
        assert call.raw_ref and len(call.response_sha256) == 64
    gnv = next(c for c in result.sub_calls if c.source == "gnv")
    assert json.loads(LocalBlobs(tmp_path).get(gnv.raw_ref)) == GNV_EXACT


def test_retries_back_off_and_stop_when_a_provider_asks_for_too_long():
    from specimen_digitization.application.harness_tools import SourceCall, with_retries

    outcomes = iter([S.RATE_LIMITED, S.TIMEOUT, S.SUCCESS])
    slept = []

    def call(attempt, retry_after=None):
        return SourceCall(
            source="x",
            query={},
            retrieved_at="t",
            outcome=next(outcomes),
            attempt=attempt,
            retry_after_seconds=retry_after,
        )

    made = with_retries(call, sleep=slept.append, random_value=lambda: 0.0)
    assert [m.outcome for m in made] == [S.RATE_LIMITED, S.TIMEOUT, S.SUCCESS]
    assert slept == [2.0, 4.0]

    outcomes = iter([S.RATE_LIMITED])
    assert len(with_retries(lambda a: call(a, retry_after=60), sleep=slept.append)) == 1
