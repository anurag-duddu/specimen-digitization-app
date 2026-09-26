"""The taxonomy_verifier tool: HARNESS.md section 6 (G23, G25, G28; GBIF.md 126-130,
with the coordinator's rulings of 22:46Z on 2026-09-25)."""

import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from specimen_digitization.application.domain import LookupStatus as S
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.application.taxonomy_tool import query_name, verify_taxon

INSECTA = [{"rank": "CLASS", "name": "Insecta"}]
ARACHNIDA = [{"rank": "CLASS", "name": "Arachnida"}]


def usage(name, rank, status="ACCEPTED", key="K1"):
    """A GBIF v2 usage: `name` carries the authorship, `canonicalName` not."""
    words = name.split()
    cut = next((i for i, w in enumerate(words[1:], 1) if not w[0].islower()), len(words))
    return {
        "key": key,
        "name": name,
        "canonicalName": " ".join(words[:cut]),
        "authorship": " ".join(words[cut:]) or None,
        "rank": rank,
        "status": status,
    }


def alternative(name, match, status, key, rank="SPECIES", classification=INSECTA):
    return {
        "usage": usage(name, rank, status, key),
        "classification": classification,
        "diagnostics": {"matchType": match},
    }


def without(record, field):
    return {k: v for k, v in record.items() if k != field}


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


def transport(*gbif_replies, gnv=GNV_EXACT, col=COL_ACCEPTED, seen=None, requests=None):
    replies = iter(gbif_replies)

    def handler(request):
        (seen if seen is not None else []).append(request.url.host + request.url.path)
        if requests is not None:
            requests.append(request)
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


def run(tmp_path, literal, client, **options):
    return verify_taxon(
        literal, blobs=LocalBlobs(tmp_path), client=client, sleep=lambda s: None, **options
    )


EPIPSOCUS = usage("Epipsocus Hagen, 1866", "GENUS")
MELLIFERA = usage("Apis mellifera Linnaeus, 1758", "SPECIES")


@pytest.mark.parametrize(
    "literal,expected",
    [
        ("Epipsocus sp. 1", "Epipsocus"),
        ("Epipsocus\nSp. 1", "Epipsocus"),
        ("Apis mellifera L.", "Apis mellifera"),
        ("Apis mellifera Linnaeus, 1758", "Apis mellifera Linnaeus, 1758"),
        ("Polygonia c-album (Linnaeus, 1758)", "Polygonia c-album (Linnaeus, 1758)"),
        ("Bombus (Pyrobombus) impatiens", "Bombus (Pyrobombus) impatiens"),
        ("Carabus Smithi", "Carabus Smithi"),
        ("Xus yus ssp. zus", "Xus yus ssp. zus"),
        ("Xus yus var. zus", "Xus yus var. zus"),
        ("Xus yus zus", "Xus yus zus"),
        ("Epipsocus sp. 1 det. Mockford", "Epipsocus"),
        ("Bombus impatiens det. E. L. Mockford, 1990", "Bombus impatiens"),
        ("Bombus impatiens Davao", "Bombus impatiens"),
        # A capitalized clause would otherwise read as author-year authorship.
        ("Bombus impatiens Det. Mockford, 1990", "Bombus impatiens"),
        ("Bombus impatiens Coll. Werner, 1946", "Bombus impatiens"),
        # The steward's probes of round 2: a species label read in full.
        ("Bombus impatiens.", "Bombus impatiens"),
        ("Bombus impatiens, det. Smith", "Bombus impatiens"),
        ("Bombus impatiëns", "Bombus impatiëns"),
        ("Bombus (P.) impatiens", "Bombus (P.) impatiens"),
        # Read only in part: the word or the hybrid is never sent.
        ("Bombus Pennsylvanicus", "Bombus"),
        ("Xus yus × zus", "Xus yus"),
        # Text that is no name: clauses, prepositions, places, dates, sex.
        ("Epipsocus determined by Mockford 1987", "Epipsocus"),
        ("Epipsocus collected by Werner 1946", "Epipsocus"),
        ("Epipsocus ident. Mockford", "Epipsocus"),
        ("Epipsocus in Davao 1946", "Epipsocus"),
        ("Epipsocus Mt. Apo 1946", "Epipsocus"),
        ("Epipsocus Davao City 1946", "Epipsocus"),
        ("Epipsocus 1946", "Epipsocus"),
        ("Xus yus female", "Xus yus"),
        ("Xus yus on Rosa", "Xus yus"),
        # Authorship, bounded: authors, then a year.
        ("Xus yus de Geer, 1775", "Xus yus de Geer, 1775"),
        ("Bombus impatiens Smith & Jones, 1901", "Bombus impatiens Smith & Jones, 1901"),
        ("Bombus impatiens F. Smith, 1854", "Bombus impatiens F. Smith, 1854"),
        # What syntax cannot settle (HARNESS.md section 6): read as authorship.
        ("Epipsocus Werner, 1946", "Epipsocus Werner, 1946"),
        ("Sp. 30 ♀", None),
        ("sp 22", None),
        ("Sp 22", None),
        ("Sp. 30 ♀ Davao", None),
        ("Sp. 30 ♀ det. Mockford", None),
        ("det. Mockford", None),
        ("Coll. F. G. Werner", None),
        ("collected by Werner 1946", None),
        ("In Davao 1946", None),
    ],
)
def test_the_query_is_the_scientific_name_the_literal_writes(literal, expected):
    # Anchored on the leading title-case genus; det., leg. and coll. clauses,
    # places and collectors are never sent (PLAN 4.8).
    assert query_name(literal) == expected


@pytest.mark.parametrize(
    "literal,rank",
    [
        ("Epipsocus sp. 1", "GENUS"),
        ("Bombus (Pyrobombus) impatiens", "SPECIES"),
        ("Polygonia c-album", "SPECIES"),
        ("Carabus Smithi", "SPECIES"),
        ("Xus yus ssp. zus", "SUBSPECIES"),
        ("Xus yus zus", "SUBSPECIES"),
        ("Xus yus var. zus", "VARIETY"),
        ("Bombus impatiens.", "SPECIES"),
        ("Bombus impatiens, det. Smith", "SPECIES"),
        ("Bombus impatiëns", "SPECIES"),
        ("Bombus (P.) impatiens", "SPECIES"),
        ("Bombus Pennsylvanicus", "GENUS"),
        ("Xus yus × zus", "SPECIES"),
    ],
)
def test_gbif_is_asked_for_the_name_at_the_rank_the_label_writes(
    tmp_path, literal, rank
):
    requests = []

    run(tmp_path, literal, transport(gbif("NONE"), requests=requests))

    match = next(r for r in requests if r.url.path == "/v2/species/match")
    assert match.url.params["scientificName"] == query_name(literal)
    assert match.url.params["taxonRank"] == rank


def test_supporting_sources_get_the_name_without_authorship(tmp_path):
    requests = []

    run(
        tmp_path,
        "Apis mellifera Linnaeus, 1758",
        transport(gbif("EXACT", MELLIFERA), requests=requests),
    )

    gnv = next(r for r in requests if r.url.host == "verifier.globalnames.org")
    col = next(r for r in requests if r.url.host == "api.checklistbank.org")
    assert gnv.url.path.endswith("/Apis mellifera")  # httpx decodes the path
    assert col.url.params["q"] == "Apis mellifera"
    assert col.url.path == "/dataset/316321/match/nameusage"  # COL26.9, pinned


@pytest.mark.parametrize(
    "literal",
    ["Sp. 30 ♀", "Sp. 30 ♀ Davao", "Sp. 30 ♀ det. Mockford", "Coll. F. G. Werner"],
)
def test_text_that_writes_no_scientific_name_makes_no_request(tmp_path, literal):
    seen = []

    result, lookup = run(tmp_path, literal, transport(seen=seen))

    assert result.outcome == S.NO_MATCH == lookup.status
    assert result.warnings == ["no_scientific_name"] and seen == []


def test_the_workflow_lookup_sends_no_request_for_text_that_is_no_name(tmp_path):
    from specimen_digitization.application.lookup import GbifTaxonomy

    seen = []

    found = GbifTaxonomy(LocalBlobs(tmp_path), transport(seen=seen)).lookup(
        "Sp. 30 ♀ Davao"
    )

    assert found.status == S.NO_MATCH and seen == [] and found.query == {}


def test_an_exact_accepted_genus_satisfies_a_genus_only_label(tmp_path):
    reply = gbif(
        "EXACT",
        EPIPSOCUS,
        [
            # The same name and authorship again, and a variant: neither counts.
            alternative("Epipsocus Hagen, 1866", "EXACT", "SYNONYM", "K2", "GENUS"),
            alternative(
                "Epipocus Chevrolat in Dejean, 1836", "VARIANT", "ACCEPTED", "K4", "GENUS"
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


def test_epipsocus_goes_to_review_under_the_homonym_ruling(tmp_path):
    # GBIF's live answer for the pilot's "Epipsocus sp. 1" (2026-09-25): an
    # exact, same-name synonym by another author in Insecta is a homonym
    # conflict (the coordinator's ruling of 22:46Z), so the match is reviewed.
    reply = gbif(
        "EXACT",
        EPIPSOCUS,
        [
            alternative("Epipsocus Hagen, 1866", "EXACT", "SYNONYM", "K2", "GENUS"),
            alternative("Epipsocus Badonnel, 1955", "EXACT", "SYNONYM", "K3", "GENUS"),
        ],
    )

    result, lookup = run(tmp_path, "Epipsocus sp. 1", transport(reply))

    assert result.outcome == S.AMBIGUOUS == lookup.status


@pytest.mark.parametrize(
    "other,outcome",
    [
        (alternative("Apis mellifera Smith, 1850", "EXACT", "SYNONYM", "K9"), S.AMBIGUOUS),
        (alternative("Apis mellifera Smith, 1850", "EXACT", "ACCEPTED", "K9"), S.AMBIGUOUS),
        (alternative("Apis mellifera Smith, 1850", "EXACT", "DOUBTFUL", "K9"), S.AMBIGUOUS),
        (
            alternative(
                "Apis mellifera Smith, 1850", "EXACT", "ACCEPTED", "K9", classification=ARACHNIDA
            ),
            S.SUCCESS,
        ),
        (alternative("Apis mellifera Smith, 1850", "VARIANT", "ACCEPTED", "K9"), S.SUCCESS),
        (
            alternative(
                "Apis mellifera Linnaeus, 1758", "EXACT", "PROVISIONALLY_ACCEPTED", "K2"
            ),
            S.SUCCESS,
        ),
        (
            alternative(
                "Apis mellifera Smith, 1850", "EXACT", "ACCEPTED", "K9", classification=None
            ),
            S.AMBIGUOUS,
        ),
        (
            {
                **alternative("Apis mellifera Smith, 1850", "EXACT", "ACCEPTED", "K9"),
                "usage": without(
                    usage("Apis mellifera Smith, 1850", "SPECIES", "ACCEPTED", "K9"),
                    "canonicalName",
                ),
            },
            S.AMBIGUOUS,
        ),
    ],
    ids=[
        "a synonym homonym",
        "an accepted homonym",
        "a doubtful homonym",
        "outside Insecta",
        "not exact",
        "the same name and authorship",
        "no class shows it is outside Insecta",
        "no canonical name shows it is another name",
    ],
)
def test_a_homonym_conflict_is_an_exact_same_name_by_another_author_in_insecta(
    tmp_path, other, outcome
):
    reply = gbif("EXACT", MELLIFERA, [other])

    assert run(tmp_path, "Apis mellifera", transport(reply)).result.outcome == outcome


@pytest.mark.parametrize(
    "reply,why",
    [
        (
            gbif("VARIANT", usage("Epipocus Chevrolat in Dejean, 1836", "GENUS")),
            "a variant is not the label's name",
        ),
        (gbif("FUZZY", usage("Apis mellifera Linnaeus, 1758", "SPECIES")), "fuzzy"),
        (gbif("HIGHERRANK", usage("Apis Linnaeus, 1758", "GENUS")), "higher rank only"),
        (
            gbif("EXACT", MELLIFERA, classification=ARACHNIDA),
            "not an insect",
        ),
        (gbif("EXACT", usage("Apis Linnaeus, 1758", "GENUS")), "a binomial matched at genus"),
        (
            gbif("EXACT", usage("Apis mellifera Linnaeus, 1758", "SPECIES", "DOUBTFUL")),
            "doubtful",
        ),
        (
            gbif(
                "EXACT",
                usage("Apis mellifera Linnaeus, 1758", "SPECIES", "PROVISIONALLY_ACCEPTED"),
            ),
            "provisionally accepted",
        ),
        (
            gbif("EXACT", dict(MELLIFERA, canonicalName="Apis melliferus")),
            "another canonical name",
        ),
    ],
)
def test_only_the_gbif_md_row_one_match_succeeds(tmp_path, reply, why):
    result, _ = run(tmp_path, "Apis mellifera", transport(reply))

    assert result.outcome == S.AMBIGUOUS, why


def test_a_subspecies_label_succeeds_only_at_subspecies(tmp_path):
    found = usage("Xus yus zus Smith, 1900", "SUBSPECIES")

    assert run(tmp_path, "Xus yus ssp. zus", transport(gbif("EXACT", found))).result.outcome == (
        S.SUCCESS
    )
    at_species = usage("Xus yus Smith, 1900", "SPECIES")
    assert run(
        tmp_path, "Xus yus ssp. zus", transport(gbif("EXACT", at_species))
    ).result.outcome == S.AMBIGUOUS


MELLIFICA = usage("Apis mellifica Linnaeus, 1761", "SPECIES", "SYNONYM", "S1")
ACCEPTED_MELLIFERA = {
    "key": "A1",
    "name": "Apis mellifera Linnaeus, 1758",
    "canonicalName": "Apis mellifera",
    "authorship": "Linnaeus, 1758",
    "rank": "SPECIES",
}


@pytest.mark.parametrize("status", [None, "ACCEPTED"])
def test_an_exact_synonym_clears_with_its_accepted_name(tmp_path, status):
    # The coordinator's ruling of 22:46Z (G28, G1): the accepted usage passes
    # row 1, so the field clears with the accepted name; the synonym status and
    # the accepted usage stay on the record (GBIF.md 127). GBIF v2 gives the
    # accepted usage no status: it is the accepted name (ruling of 23:58Z).
    accepted = dict(ACCEPTED_MELLIFERA, **({"status": status} if status else {}))
    reply = gbif("EXACT", MELLIFICA, accepted=accepted)

    result, lookup = run(tmp_path, "Apis mellifica", transport(reply))

    assert result.outcome == S.SUCCESS == lookup.status
    assert [(t.usage_key, t.status, t.accepted_usage_key) for t in result.taxa] == [
        ("A1", status, None),
        ("S1", "SYNONYM", "A1"),
    ]
    assert lookup.candidates[0]["key"] == "A1"
    assert lookup.candidates[0]["scientificName"] == "Apis mellifera Linnaeus, 1758"
    assert lookup.metadata["accepted_usage"]["key"] == "A1"


@pytest.mark.parametrize(
    "reply,why",
    [
        (
            gbif("EXACT", MELLIFICA, accepted=dict(ACCEPTED_MELLIFERA, rank="GENUS")),
            "its accepted usage is at another rank",
        ),
        (
            gbif(
                "EXACT",
                MELLIFICA,
                [alternative("Apis mellifica Smith, 1850", "EXACT", "ACCEPTED", "K9")],
                accepted=ACCEPTED_MELLIFERA,
            ),
            "the synonym's name has a homonym",
        ),
        (
            gbif("EXACT", MELLIFICA, classification=ARACHNIDA, accepted=ACCEPTED_MELLIFERA),
            "not an insect",
        ),
        (gbif("EXACT", MELLIFICA), "no accepted usage"),
        (
            gbif(
                "EXACT", MELLIFICA, accepted=dict(ACCEPTED_MELLIFERA, status="DOUBTFUL")
            ),
            "its accepted usage has a status other than ACCEPTED",
        ),
        (
            gbif(
                "EXACT",
                dict(MELLIFICA, status="PROPARTE_SYNONYM"),
                accepted=ACCEPTED_MELLIFERA,
            ),
            "a pro parte synonym has several accepted usages",
        ),
    ],
)
def test_an_exact_synonym_stays_in_review_when_its_accepted_usage_fails_row_one(
    tmp_path, reply, why
):
    result, lookup = run(tmp_path, "Apis mellifica", transport(reply))

    assert result.outcome == S.AMBIGUOUS == lookup.status, why


def test_every_gbif_candidate_can_be_selected_in_review(tmp_path):
    # api.py's taxonomy_resolution decision selects by `scientificName`, which
    # GBIF v2 usages name `name`.
    reply = gbif(
        "EXACT",
        MELLIFERA,
        [alternative("Apis mellifera Smith, 1850", "EXACT", "ACCEPTED", "K9")],
    )

    _, lookup = run(tmp_path, "Apis mellifera", transport(reply))

    choices = [candidate.get("usage", candidate) for candidate in lookup.candidates]
    assert [(c["key"], c["scientificName"]) for c in choices] == [
        ("K1", "Apis mellifera Linnaeus, 1758"),
        ("K9", "Apis mellifera Smith, 1850"),
    ]


def deep(levels):
    return "[" * levels + "]" * levels


@pytest.mark.parametrize(
    "body",
    [
        gbif("EXACT", MELLIFERA, [{"usage": {"key": "K9"}, "diagnostics": "EXACT"}]),
        gbif("EXACT", MELLIFERA, "not a list"),
        gbif("EXACT", MELLIFICA, accepted="A1"),
        gbif("EXACT", dict(MELLIFERA, name=5)),
        gbif("EXACT", dict(MELLIFERA, rank=["SPECIES"])),
        gbif("EXACT", dict(MELLIFERA, name="Apis mellifera " + "x" * 640_000)),
        gbif("EXACT", dict(MELLIFERA, key="K" * 870_000)),
        gbif("EXACT", dict(MELLIFERA, key=True)),
        gbif("EXACT", dict(MELLIFERA, rank="SPECIES" * 10)),
        gbif("EXACT", dict(MELLIFERA, status=["ACCEPTED"])),
        gbif("EXACT", MELLIFERA, classification=["x"]),
        gbif(
            "EXACT",
            MELLIFERA,
            [
                alternative(
                    "Apis mellifera Smith, 1850", "EXACT", "ACCEPTED", "K9", classification=["x"]
                )
            ],
        ),
        httpx.Response(
            200,
            content=(
                json.dumps(gbif("EXACT", MELLIFERA))[:-1]
                + ', "usage": '
                + json.dumps(usage("Homo sapiens Linnaeus, 1758", "SPECIES"))
                + "}"
            ).encode(),
        ),
    ],
    ids=[
        "an alternative's diagnostics",
        "the alternatives",
        "the accepted usage",
        "a name",
        "a rank",
        "a 640 kB name",
        "an 870 kB key",
        "a boolean key",
        "a rank over 40 characters",
        "a status that is a list",
        "a classification element",
        "an alternative's classification element",
        "a key given twice",
    ],
)
def test_a_malformed_gbif_body_is_malformed_response(tmp_path, body):
    result, lookup = run(tmp_path, "Apis mellifera", transport(body))

    assert result.outcome == S.MALFORMED == lookup.status


def test_a_deeply_nested_supporting_body_is_malformed_and_gbif_still_decides(tmp_path):
    nested = httpx.Response(200, content=deep(5000).encode())

    result, _ = run(
        tmp_path, "Apis mellifera", transport(gbif("EXACT", MELLIFERA), gnv=nested, col=nested)
    )

    assert result.outcome == S.SUCCESS
    assert [c.outcome for c in result.sub_calls if c.source != "gbif"] == [
        S.MALFORMED,
        S.MALFORMED,
    ]
    assert result.warnings == [
        "taxonomy_support_unavailable:gnv",
        "taxonomy_support_unavailable:col",
    ]


def test_supporting_sources_never_change_gbif_outcome_but_disagreement_is_a_warning(
    tmp_path,
):
    result, _ = run(
        tmp_path,
        "Epipsocus",
        transport(gbif("EXACT", EPIPSOCUS), gnv=GNV_NONE, col=COL_NONE),
    )

    assert result.outcome == S.SUCCESS
    assert result.warnings == [
        "taxonomy_source_disagreement:gnv",
        "taxonomy_source_disagreement:col",
    ]


def test_no_disagreement_is_flagged_when_gbif_itself_failed(tmp_path):
    failed = httpx.Response(503)

    result, _ = run(tmp_path, "Epipsocus", transport(failed, failed, failed))

    assert result.outcome == S.PROVIDER
    assert not any("disagreement" in w for w in result.warnings)


def test_an_unavailable_supporting_source_is_not_a_disagreement(tmp_path):
    result, _ = run(
        tmp_path, "Epipsocus", transport(gbif("EXACT", EPIPSOCUS), gnv=httpx.Response(503))
    )

    assert result.outcome == S.SUCCESS
    assert result.warnings == ["taxonomy_support_unavailable:gnv"]
    assert [c.outcome for c in result.sub_calls if c.source == "gnv"] == [
        S.PROVIDER
    ] * 3


def test_a_truncated_supporting_body_is_malformed_and_not_retried(tmp_path, monkeypatch):
    # The production path, through bounded_http, with no client.
    from specimen_digitization.application import http_effect

    def bounded(url, **options):
        if "gbif.org" in url:
            body = json.dumps(
                {"alias": "fixture-index"}
                if url.endswith("/metadata")
                else gbif("EXACT", EPIPSOCUS)
            ).encode()
            return {
                "failure": None,
                "truncated": False,
                "status_code": 200,
                "body": body,
                "retry_after": "",
            }
        return {
            "failure": None,
            "truncated": True,
            "status_code": 200,
            "body": b'{"names": [',
            "retry_after": "",
        }

    monkeypatch.setattr(http_effect, "bounded_http", bounded)

    result, _ = run(tmp_path, "Epipsocus", None)

    assert result.outcome == S.SUCCESS
    assert [(c.source, c.attempt, c.outcome) for c in result.sub_calls[1:]] == [
        ("gnv", 1, S.MALFORMED),
        ("col", 1, S.MALFORMED),
    ]


def test_a_gbif_rate_limit_is_retried_and_every_attempt_recorded(tmp_path):
    limited = httpx.Response(429, headers={"Retry-After": "1"})

    result, _ = run(
        tmp_path, "Epipsocus", transport(limited, limited, gbif("EXACT", EPIPSOCUS))
    )

    gbif_calls = [c for c in result.sub_calls if c.source == "gbif"]
    assert [(c.attempt, c.outcome) for c in gbif_calls] == [
        (1, S.RATE_LIMITED),
        (2, S.RATE_LIMITED),
        (3, S.SUCCESS),
    ]
    assert result.outcome == S.SUCCESS


def test_one_deadline_bounds_the_tool_and_support_is_cut_first(tmp_path):
    # GBIF decides first; GNV and COL get only the time left (security's
    # should-fix: support could hold the step past its timeout).
    clock = [0.0]

    def handler(request):
        clock[0] += 30  # every request takes 30 s of the fake clock
        if request.url.path.endswith("/metadata"):
            clock[0] -= 30
            return httpx.Response(200, json={"alias": "fixture-index"})
        if request.url.host == "api.gbif.org":
            return httpx.Response(200, json=gbif("EXACT", EPIPSOCUS))
        return httpx.Response(200, json=GNV_EXACT)

    seen = []

    def recording(request):
        seen.append(request.url.host)
        return handler(request)

    result, _ = run(
        tmp_path,
        "Epipsocus",
        httpx.Client(transport=httpx.MockTransport(recording)),
        clock=lambda: clock[0],
        deadline_seconds=40,
    )

    assert result.outcome == S.SUCCESS
    assert "api.checklistbank.org" not in seen
    col = [c for c in result.sub_calls if c.source == "col"]
    assert [(c.outcome, c.sanitized_error) for c in col] == [(S.TIMEOUT, "tool_deadline")]
    assert "taxonomy_support_unavailable:col" in result.warnings


def test_every_source_call_records_its_licence(tmp_path):
    result, _ = run(tmp_path, "Epipsocus", transport(gbif("EXACT", EPIPSOCUS)))

    licences = {c.source: c.license for c in result.sub_calls}
    assert all(licences.values()), licences
    assert "CC BY 4.0" in licences["gbif"] and "COL26.9" in licences["col"]


def test_every_source_response_is_stored_with_its_digest(tmp_path):
    result, _ = run(tmp_path, "Epipsocus", transport(gbif("EXACT", EPIPSOCUS)))

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


def test_retries_stop_at_the_deadline():
    from specimen_digitization.application.harness_tools import SourceCall, with_retries

    clock, slept = [0.0], []

    def call(attempt):
        clock[0] += 6  # each attempt takes 6 s
        return SourceCall(
            source="x", query={}, retrieved_at="t", outcome=S.RATE_LIMITED, attempt=attempt
        )

    made = with_retries(
        call,
        sleep=lambda s: (slept.append(s), clock.__setitem__(0, clock[0] + s)),
        random_value=lambda: 0.0,
        deadline=16,
        clock=lambda: clock[0],
    )

    # At 6 s a 2 s wait fits; at 14 s the next 4 s wait would pass 16 s.
    assert len(made) == 2 and slept == [2.0]


def test_a_retry_never_comes_sooner_than_retry_after():
    from specimen_digitization.application.harness_tools import SourceCall, with_retries

    outcomes = iter([S.RATE_LIMITED, S.SUCCESS])
    slept = []

    def call(attempt):
        return SourceCall(
            source="x",
            query={},
            retrieved_at="t",
            outcome=next(outcomes),
            attempt=attempt,
            retry_after_seconds=15,
        )

    with_retries(call, sleep=slept.append, random_value=lambda: 0.0)
    assert slept and slept[0] >= 15


@pytest.mark.parametrize("ahead,expected", [(10.9, 11), (20.9, 21), (0.2, 1)])
def test_an_http_date_retry_after_rounds_up(ahead, expected):
    from specimen_digitization.application.reliability import retry_after

    now = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)
    later = now + timedelta(seconds=ahead)
    # HTTP-dates have whole seconds, so the header itself says when.
    header = format_datetime(later.replace(microsecond=0), usegmt=True)
    whole = (later.replace(microsecond=0) - now).total_seconds()

    assert retry_after(header, current=now - timedelta(seconds=ahead - whole)) == expected


def test_the_types_keep_google_to_a_place_id():
    # G26: a Google place candidate carries no name and no components, and no
    # georeference candidate cites Google.
    from pydantic import ValidationError

    from specimen_digitization.application.harness_tools import (
        GeoreferenceCandidate,
        PlaceCandidate,
        SourceRef,
    )

    google = "google-maps-geocoding"
    PlaceCandidate(field_key="country", source=google, source_record_id="ChIJ")
    with pytest.raises(ValidationError):
        PlaceCandidate(field_key="country", source=google, name="Philippines")
    with pytest.raises(ValidationError):
        PlaceCandidate(field_key="country", source=google, components={"country": "PH"})
    with pytest.raises(ValidationError):
        GeoreferenceCandidate(latitude=7.0, longitude=125.0, sources=[SourceRef(name=google)])
    with pytest.raises(ValidationError):
        GeoreferenceCandidate(latitude=7.0, longitude=125.0, sources=[])
    PlaceCandidate(field_key="country", source="geonames", name="Philippines")


BOMBUS = usage("Bombus Latreille, 1802", "GENUS")
IMPATIENS = usage("Bombus impatiens Cresson, 1863", "SPECIES")
SPECIES_LABELS = [
    "Bombus impatiens.",
    "Bombus impatiens, det. Smith",
    "Bombus impatiëns",
    "Bombus (P.) impatiens",
    "Bombus Pennsylvanicus",
]


@pytest.mark.parametrize("literal", SPECIES_LABELS)
def test_a_species_label_never_clears_at_genus(tmp_path, literal):
    # The steward's probes of round 2: GBIF's exact genus answered each of
    # these, and each cleared as "Bombus Latreille, 1802" (G25).
    result, lookup = run(tmp_path, literal, transport(gbif("EXACT", BOMBUS)))

    assert result.outcome == S.AMBIGUOUS == lookup.status


@pytest.mark.parametrize("literal", SPECIES_LABELS)
def test_the_workflow_lookup_never_clears_a_species_label_at_genus(tmp_path, literal):
    from specimen_digitization.application.lookup import GbifTaxonomy

    client = transport(gbif("EXACT", BOMBUS))

    assert GbifTaxonomy(LocalBlobs(tmp_path), client).lookup(literal).status == (
        S.AMBIGUOUS
    )


@pytest.mark.parametrize(
    "literal", ["Bombus impatiens.", "Bombus impatiens, det. Smith", "Bombus (P.) impatiens"]
)
def test_a_species_label_read_in_full_clears_at_species(tmp_path, literal):
    result, _ = run(tmp_path, literal, transport(gbif("EXACT", IMPATIENS)))

    assert result.outcome == S.SUCCESS


@pytest.mark.parametrize(
    "literal,reply,why",
    [
        ("Bombus Pennsylvanicus", gbif("EXACT", BOMBUS), "Pennsylvanicus"),
        ("Epipsocus Davao City 1946", gbif("EXACT", EPIPSOCUS), "Davao"),
        ("Xus yus × zus", gbif("EXACT", usage("Xus yus Smith, 1900", "SPECIES")), "hybrid"),
        ("Xus × Yus", gbif("EXACT", usage("Xus Smith, 1900", "GENUS")), "hybrid"),
    ],
)
def test_a_name_read_only_in_part_never_succeeds(tmp_path, literal, reply, why):
    # A word after the genus that could be an epithet, or a hybrid sign, never
    # ends in a success, and the word is never sent (the steward's review).
    requests = []

    result, lookup = run(tmp_path, literal, transport(reply, requests=requests))

    assert result.outcome == S.AMBIGUOUS == lookup.status
    assert "taxonomy_name_partly_read" in result.warnings
    assert lookup.metadata["partly_read"] == why
    assert not any(why in str(request.url) for request in requests)


def test_no_unbounded_text_reaches_the_sources(tmp_path):
    many = "Epipsocus " + "Aa " * 100_000 + "1946"
    joined = "Epipsocus " + "Aa & " * 50 + "Bb, 1946"
    requests = []

    run(tmp_path, many, transport(gbif("EXACT", EPIPSOCUS), requests=requests))

    assert query_name(many) == query_name(joined) == "Epipsocus"
    assert query_name("Epipsocus " + "a" * 70_000) is None
    assert max(len(str(request.url)) for request in requests) < 2_000


@pytest.mark.parametrize("own", ["Homo sapiens", {"name": "Homo sapiens"}, "x" * 640_000])
def test_the_final_value_is_gbifs_name_never_a_bodys_own(tmp_path, own):
    # What the workflow's lookup and the review decision store as the value.
    reply = gbif("EXACT", dict(MELLIFERA, scientificName=own))

    result, lookup = run(tmp_path, "Apis mellifera", transport(reply))

    assert result.outcome == S.SUCCESS
    assert lookup.candidates[0]["scientificName"] == "Apis mellifera Linnaeus, 1758"


def test_two_authorless_usages_of_one_name_are_a_homonym_conflict(tmp_path):
    reply = gbif(
        "EXACT",
        usage("Apis mellifera", "SPECIES"),
        [alternative("Apis mellifera", "EXACT", "ACCEPTED", "K9")],
    )

    assert run(tmp_path, "Apis mellifera", transport(reply)).result.outcome == S.AMBIGUOUS


def test_a_supporting_answer_of_the_wrong_type_is_malformed_not_a_disagreement(tmp_path):
    gnv = {"names": [{"matchType": 7}]}
    col = dict(COL_ACCEPTED, match="false")

    result, _ = run(
        tmp_path, "Epipsocus", transport(gbif("EXACT", EPIPSOCUS), gnv=gnv, col=col)
    )

    assert result.outcome == S.SUCCESS
    assert [c.outcome for c in result.sub_calls if c.source != "gbif"] == [
        S.MALFORMED,
        S.MALFORMED,
    ]
    assert result.warnings == [
        "taxonomy_support_unavailable:gnv",
        "taxonomy_support_unavailable:col",
    ]


def test_a_failed_gbif_call_carries_a_sanitized_error(tmp_path):
    failed = httpx.Response(503)

    result, _ = run(tmp_path, "Epipsocus", transport(failed, failed, failed))

    assert [c.sanitized_error for c in result.sub_calls if c.source == "gbif"] == [
        "provider_error"
    ] * 3


def test_a_supporting_body_in_an_unreadable_encoding_is_malformed_and_not_retried(
    tmp_path, monkeypatch
):
    from specimen_digitization.application import http_effect

    def bounded(url, **options):
        if "gbif.org" in url:
            body = json.dumps(
                {"alias": "fixture-index"}
                if url.endswith("/metadata")
                else gbif("EXACT", EPIPSOCUS)
            ).encode()
            return {
                "failure": None,
                "truncated": False,
                "status_code": 200,
                "body": body,
                "retry_after": "",
            }
        body = json.dumps(GNV_EXACT if "globalnames" in url else COL_ACCEPTED).encode()
        return {
            "failure": None,
            "truncated": False,
            "unsupported_encoding": True,
            "status_code": 200,
            "body": body,
            "retry_after": "",
        }

    monkeypatch.setattr(http_effect, "bounded_http", bounded)

    result, _ = run(tmp_path, "Epipsocus", None)

    assert result.outcome == S.SUCCESS
    assert [
        (c.source, c.attempt, c.outcome, c.sanitized_error) for c in result.sub_calls[1:]
    ] == [
        ("gnv", 1, S.MALFORMED, "unsupported_encoding"),
        ("col", 1, S.MALFORMED, "unsupported_encoding"),
    ]


def test_a_gbif_body_nested_too_deep_to_store_is_malformed(tmp_path):
    # Pre-existing, from the steward's review of round 2: a body nested a few
    # hundred levels parsed and succeeded, then its record could not be written.
    body = gbif("EXACT", MELLIFERA)
    body["diagnostics"]["note"] = json.loads(deep(300))

    result, lookup = run(tmp_path, "Apis mellifera", transport(body))

    assert result.outcome == S.MALFORMED == lookup.status
    assert lookup.model_dump_json()
