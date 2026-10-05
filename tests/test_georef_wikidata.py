"""Tier 1 Wikidata requests and answers for the retrospective georeferencing tool (GEO.md 2)."""

import json
from pathlib import Path

import pytest

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.georef_locality import is_full_name
from specimen_digitization.application.georef_places import Place, Ref
from specimen_digitization.application.georef_wikidata import (
    LICENSE,
    _time,
    entities_params,
    labels_params,
    name_refs,
    parse_entities,
    parse_labels,
    parse_search,
    referenced_ids,
    search_params,
)

FIXTURES = Path(__file__).parent / "fixtures" / "georeferencing"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def search_body(reading):
    return json.dumps(fixture("wikidata_search.json")["responses"][reading]).encode()


def entities_body():
    return json.dumps(
        {"entities": fixture("wikidata_entities.json")["entities"], "success": 1}
    ).encode()


def labels_body():
    return json.dumps(
        {"entities": fixture("wikidata_labels.json")["entities"], "success": 1}
    ).encode()


def places():
    outcome, found = parse_entities(200, entities_body())
    assert outcome is LookupStatus.SUCCESS
    status, labels = parse_labels(200, labels_body())
    assert status is LookupStatus.SUCCESS
    return {place.record_id: place for place in name_refs(found, labels)}


def test_search_asks_for_english_items():
    assert search_params("Mount Apo") == {
        "action": "wbsearchentities",
        "search": "Mount Apo",
        "language": "en",
        "uselang": "en",
        "type": "item",
        "limit": "7",
        "format": "json",
    }
    for reading in ("", " \t", "Apo\nMount", "Apo\x00", "Apo​", "x" * 201):
        with pytest.raises(ValueError):
            search_params(reading)
    for kwargs in ({"language": "xx"}, {"limit": 0}, {"limit": 8}, {"limit": True}):
        with pytest.raises(ValueError):
            search_params("Mount Apo", **kwargs)


def test_mount_mckinley_finds_denali_and_nothing_in_the_philippines():
    outcome, hits = parse_search(200, search_body("Mount McKinley"))
    assert outcome is LookupStatus.SUCCESS
    assert (hits[0].id, hits[0].label, hits[0].matched, hits[0].match_type) == (
        "Q130018",
        "Denali",
        "Mount McKinley",
        "alias",
    )
    assert len(hits) == 7
    assert not any("Philippines" in (hit.description or "") for hit in hits)


def test_davao_province_finds_only_the_province_of_1914_to_1967():
    outcome, hits = parse_search(200, search_body("Davao Province"))
    assert outcome is LookupStatus.SUCCESS
    assert [(hit.id, hit.matched) for hit in hits] == [("Q15095071", "Davao Province")]


def test_a_misspelling_finds_nothing():
    assert parse_search(200, search_body("Chimaltenago")) == (LookupStatus.NO_MATCH, ())


@pytest.mark.parametrize(
    ("status", "body", "outcome"),
    [
        (200, b"", LookupStatus.EMPTY),
        (200, b"<html>busy</html>", LookupStatus.MALFORMED),
        (200, b"[]", LookupStatus.MALFORMED),
        (200, b'{"error":{"code":"maxlag"}}', LookupStatus.RATE_LIMITED),
        (200, b'{"error":{"code":"ratelimited"}}', LookupStatus.RATE_LIMITED),
        (200, b'{"error":{"code":"no-such-entity"}}', LookupStatus.NO_MATCH),
        (200, b'{"error":{"code":"internal_api_error"}}', LookupStatus.PROVIDER),
        (429, b"", LookupStatus.RATE_LIMITED),
        (401, b"", LookupStatus.AUTHENTICATION),
        (403, b"Please set a user-agent", LookupStatus.AUTHORIZATION),
        (500, b"", LookupStatus.PROVIDER),
        (404, b"", LookupStatus.PROVIDER),
    ],
)
def test_every_answer_maps_to_one_outcome(status, body, outcome):
    assert parse_search(status, body) == (outcome, ())
    assert parse_entities(status, body)[0] is outcome
    assert parse_labels(status, body)[0] is outcome


def test_entities_are_read_fifty_at_a_time():
    params = entities_params(["Q928", "Q15095071"])
    assert params == {
        "action": "wbgetentities",
        "ids": "Q928|Q15095071",
        "props": "labels|aliases|descriptions|claims",
        "languages": "en|es|mul",
        "format": "json",
    }
    assert labels_params(["Q13794"]) == {
        "action": "wbgetentities",
        "ids": "Q13794",
        "props": "labels",
        "languages": "en|mul",
        "format": "json",
    }
    with pytest.raises(ValueError):
        entities_params([f"Q{n}" for n in range(51)])
    assert entities_params(["Q928", "Q928"])["ids"] == "Q928"
    for ids in (["Q0"], ["q928"], ["Q928|Q30"], ["1946"], ["Q９２８"], [42]):
        with pytest.raises(ValueError):
            entities_params(ids)
        with pytest.raises(ValueError):
            labels_params(ids)


def test_the_province_of_1914_to_1967_and_its_successors():
    davao = places()["Q15095071"]
    assert (davao.name, davao.valid_from, davao.valid_to) == ("Davao", "1914-09-01", "1967-05-08")
    assert "Davao Province" in davao.names and "provincia de Dávao" in davao.names
    assert [ref.name for ref in davao.replaced_by] == [
        "Davao del Norte",
        "Davao del Sur",
        "Davao Oriental",
    ]
    assert davao.country == Ref("Q928", "Philippines")
    assert (davao.source, davao.license) == ("wikidata", LICENSE) == ("wikidata", "CC0-1.0")


def test_countries_carry_their_iso_code_and_aliases():
    philippines = places()["Q928"]
    assert (philippines.iso_code, philippines.valid_from) == ("PH", "1565")
    assert "Philippine Islands" in philippines.names
    assert "RP" in philippines.names and not is_full_name("RP")
    assert places()["Q774"].iso_code == "GT"


def test_points_parents_and_dates():
    found = places()
    apo = found["Q455963"]
    assert apo.point == pytest.approx((6.9875, 125.27083333333))
    assert [ref.name for ref in apo.parents] == ["Davao Region", "Davao del Sur"]
    assert [ref.name for ref in apo.kinds] == ["stratovolcano", "dormant volcano", "mountain"]
    assert found["Q1504280"].valid_from == "2004-02-03"
    assert found["Q25173824"].parents == (Ref("Q1523937", "Yepocapa"),)
    assert found["Q1523937"].parents == (Ref("Q1002552", "Chimaltenango"),)
    assert found["Q130018"].country == Ref("Q30", "United States")
    assert found["Q31472786"].parents == (Ref("Q1473", "Davao City"),)


def test_referenced_ids_are_what_the_second_call_names():
    _, found = parse_entities(200, entities_body())
    # Items the first call already read, such as Q928 and Q1523937, name themselves.
    assert referenced_ids(found) == set(fixture("wikidata_labels.json")["entities"])


def test_deprecated_statements_and_missing_items_are_skipped():
    body = {
        "entities": {
            "Q1": {
                "id": "Q1",
                "type": "item",
                "labels": {"es": {"language": "es", "value": "Uno"}},
                "claims": {
                    "P576": [
                        {
                            "rank": "deprecated",
                            "mainsnak": {
                                "snaktype": "value",
                                "property": "P576",
                                "datavalue": {
                                    "type": "time",
                                    "value": {"time": "+1900-01-01T00:00:00Z", "precision": 11},
                                },
                            },
                        }
                    ],
                    "P625": [
                        {
                            "rank": "normal",
                            "mainsnak": {
                                "snaktype": "value",
                                "property": "P625",
                                "datavalue": {
                                    "type": "globecoordinate",
                                    "value": {
                                        "latitude": 1.0,
                                        "longitude": 2.0,
                                        "globe": "http://www.wikidata.org/entity/Q405",
                                    },
                                },
                            },
                        }
                    ],
                },
            },
            "Q2": {"id": "Q2", "missing": ""},
        },
        "success": 1,
    }
    outcome, found = parse_entities(200, json.dumps(body).encode())
    assert outcome is LookupStatus.SUCCESS
    assert found == (Place(source="wikidata", record_id="Q1", name="Uno", license="CC0-1.0"),)
    only_missing = {"entities": {"Q2": {"id": "Q2", "missing": ""}}, "success": 1}
    assert parse_entities(200, json.dumps(only_missing).encode()) == (LookupStatus.NO_MATCH, ())


def test_invalid_item_ids_and_missing_labels_do_not_create_source_places():
    search = {"search": [{"id": "1946", "label": "A date"}, {"id": "Q928|Q30"}]}
    assert parse_search(200, json.dumps(search).encode()) == (LookupStatus.MALFORMED, ())
    entities = {
        "entities": {
            "Q1": {"id": "Q2", "labels": {"en": {"value": "Wrong item"}}},
            "Q3": {"id": "Q3", "labels": {}},
            "1946": {"id": "1946", "labels": {"en": {"value": "Not an item"}}},
        }
    }
    assert parse_entities(200, json.dumps(entities).encode()) == (LookupStatus.MALFORMED, ())
    assert parse_labels(200, json.dumps(entities).encode()) == (LookupStatus.MALFORMED, {})


def test_bad_coordinates_and_coarse_or_invalid_dates_are_not_promoted():
    def statement(value):
        return {"rank": "normal", "mainsnak": {"datavalue": {"value": value}}}

    entities = {"entities": {}}
    for number, latitude, longitude in (
        (1, float("nan"), 1.0),
        (2, float("inf"), 1.0),
        (3, 91.0, 1.0),
        (4, True, 1.0),
        (5, 90.0, 180.0),
    ):
        item = f"Q{number}"
        entities["entities"][item] = {
            "id": item,
            "labels": {"en": {"value": f"Place {number}"}},
            "claims": {
                "P625": [
                    statement(
                        {
                            "latitude": latitude,
                            "longitude": longitude,
                            "globe": "http://www.wikidata.org/entity/Q2",
                        }
                    )
                ],
                "P571": [statement({"time": "+1946-00-00T00:00:00Z", "precision": 8})],
            },
        }
    outcome, found = parse_entities(200, json.dumps(entities).encode())
    assert outcome is LookupStatus.SUCCESS
    assert [place.point for place in found] == [None, None, None, None, (90.0, 180.0)]
    assert all(place.valid_from is None for place in found)
    for value in (
        {"time": "+1946-00-00T00:00:00Z", "precision": 8},
        {"time": "+1946-13-01T00:00:00Z", "precision": 10},
        {"time": "+1946-02-31T00:00:00Z", "precision": 11},
        {"time": "+1946-01-01garbage", "precision": 11},
    ):
        assert _time(value) is None
