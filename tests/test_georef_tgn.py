"""Tier 1 Getty TGN requests and answers for the retrospective georeferencing tool (GEO.md 7)."""

import json
from pathlib import Path

import pytest

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.georef_locality import comparison_key, is_full_name
from specimen_digitization.application.georef_places import Ref
from specimen_digitization.application.georef_tgn import (
    CREDIT,
    LICENSE,
    NAMES,
    RECORDS,
    Hit,
    names_params,
    parse_names,
    parse_reconcile,
    parse_records,
    reconcile_params,
    records_params,
    with_names,
)

FIXTURES = Path(__file__).parent / "fixtures" / "georeferencing"
UNITED_STATES = Ref("7012149", "United States")


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def reconcile_body(reading):
    results = fixture("tgn_reconcile.json")["responses"][reading]
    return json.dumps({"q0": {"result": results}}).encode()


def sparql_body(name):
    data = fixture(name)
    return json.dumps({"head": data["head"], "results": {"bindings": data["bindings"]}}).encode()


def sparql(*bindings):
    rows = [{variable: {"value": value} for variable, value in row.items()} for row in bindings]
    return json.dumps({"results": {"bindings": rows}}).encode()


def places():
    outcome, found = parse_records(200, sparql_body("tgn_records.json"))
    assert outcome is LookupStatus.SUCCESS
    status, names = parse_names(200, sparql_body("tgn_names.json"))
    assert status is LookupStatus.SUCCESS
    return {place.record_id: place for place in with_names(found, names)}


def hits(reading):
    outcome, found = parse_reconcile(200, reconcile_body(reading))
    assert outcome is LookupStatus.SUCCESS
    return found


def test_reconciliation_asks_for_ten_tgn_places():
    params = reconcile_params("Mount Apo")
    assert list(params) == ["queries"]
    assert json.loads(params["queries"]) == {
        "q0": {"query": "Mount Apo", "type": "/tgn", "limit": 10}
    }


def test_records_and_names_are_read_by_digit_ids_fifty_at_a_time():
    assert records_params(["1103742", "1000135"]) == {
        "query": RECORDS % "tgn:1103742 tgn:1000135"
    }
    assert names_params(["1103742", "1103742"]) == {"query": NAMES % "tgn:1103742"}
    too_many = [str(number) for number in range(51)]
    for ids in ([], too_many, ["Q928"], ["1103742 } ?s ?p ?o {"], ["１２３"]):
        with pytest.raises(ValueError):
            records_params(ids)
        with pytest.raises(ValueError):
            names_params(ids)


def test_mount_apo_finds_the_mountain_filed_under_cotabato():
    first = hits("Mount Apo")[0]
    assert (first.id, first.name) == ("1103742", "Apo, Mount")
    apo = places()["1103742"]
    assert apo.name == "Apo, Mount" and "Mount Apo" in apo.names
    assert apo.kinds[0] == Ref("aat:300008795", "mountains (landforms)")
    assert apo.parents == (Ref("1001457", "Cotabato"),)
    assert apo.country == Ref("1000135", "Pilipinas")
    assert apo.point == pytest.approx((6.9833, 125.2667))


def test_every_place_mount_mckinley_finds_lies_in_the_united_states():
    found = places()
    mckinley = [found[hit.id] for hit in hits("Mount McKinley")]
    assert len(mckinley) == 10
    assert {place.country for place in mckinley} == {UNITED_STATES}
    denali = found["1105587"]
    assert "Denali" in denali.names
    assert [ref.name for ref in denali.parents] == ["Denali", "Alaska"]


def test_tgn_holds_no_yepocapa_talomo_or_chimaltenago():
    assert parse_reconcile(200, reconcile_body("Yepocapa")) == (LookupStatus.NO_MATCH, ())
    assert parse_reconcile(200, reconcile_body("Chimaltenago")) == (LookupStatus.NO_MATCH, ())
    talomo = comparison_key("Talomo")
    assert not any(talomo in comparison_key(hit.name) for hit in hits("Mount Talomo"))


def test_davao_province_finds_a_city_first():
    first = hits("Davao Province")[0]
    assert (first.id, first.name) == ("7668798", "Davao")
    found = places()
    davao = found["7668798"]
    assert davao.kinds[0].name == "special cities"
    assert {"Davao Province", "Davao City", "Davao del Norte"} <= set(davao.names)
    # TGN dates names, not places: nothing here records the 1914-1967 province.
    assert all(place.valid_from is None and place.valid_to is None for place in found.values())


def test_philippine_islands_finds_a_wisconsin_ridge_first():
    found = places()
    ridge = found[hits("Philippine Islands")[0].id]
    assert ridge.record_id == "2578581"
    assert ridge.kinds == (Ref("aat:300266640", "ridges (landforms)"),)
    assert ridge.country == UNITED_STATES
    assert [ref.name for ref in ridge.parents] == ["Portage", "Wisconsin"]
    philippines = found["1000135"]
    assert philippines.name == "Philippines"
    assert (philippines.country, philippines.parents) == (Ref("1000135", "Philippines"), ())
    assert {"Philippine Islands", "Pilipinas"} <= set(philippines.names)
    assert philippines.iso_code is None


def test_codes_among_the_names_are_not_full_names():
    found = places()
    codes = {"RP", "PH", "PHL", "ISO608"}
    assert codes <= set(found["1000135"].names)
    assert "GT03" in found["1000565"].names and "RPC3" in found["1001216"].names
    assert not any(is_full_name(code) for code in (*codes, "GT03", "RPC3"))


def test_the_chimaltenango_department_and_its_capital_lie_in_guatemala():
    found = places()
    department, capital = found["1000565"], found["1016636"]
    assert department.kinds[0] == Ref("aat:300000772", "departments (political divisions)")
    assert "Departamento de Chimaltenango" in department.names
    assert department.parents == ()
    assert capital.parents == (Ref("1000565", "Chimaltenango"),)
    assert department.country == capital.country == Ref("7005493", "Guatemala")


def test_every_place_is_credited_under_odc_by():
    assert LICENSE == "ODC-By-1.0"
    assert CREDIT == (
        "Contains information from the J. Paul Getty Trust, Getty Research Institute, "
        "Thesaurus of Geographic Names, which is made available under the ODC Attribution License"
    )
    assert {(place.source, place.license) for place in places().values()} == {("tgn", LICENSE)}


@pytest.mark.parametrize(
    ("status", "body", "outcome"),
    [
        (200, b"", LookupStatus.EMPTY),
        (200, b"  \n", LookupStatus.EMPTY),
        (200, b"<html>busy</html>", LookupStatus.MALFORMED),
        (200, b"[]", LookupStatus.MALFORMED),
        (200, b"{}", LookupStatus.MALFORMED),
        (429, b"", LookupStatus.RATE_LIMITED),
        (401, b"", LookupStatus.AUTHENTICATION),
        (403, b"", LookupStatus.AUTHORIZATION),
        (400, b"", LookupStatus.PROVIDER),
        (500, b"", LookupStatus.PROVIDER),
        (503, b"<html>overloaded</html>", LookupStatus.PROVIDER),
    ],
)
def test_every_answer_maps_to_one_outcome(status, body, outcome):
    assert parse_reconcile(status, body) == (outcome, ())
    assert parse_records(status, body) == (outcome, ())
    assert parse_names(status, body) == (outcome, {})


def test_answers_that_find_nothing_are_no_match():
    assert parse_reconcile(200, b'{"q0": {"result": []}}') == (LookupStatus.NO_MATCH, ())
    assert parse_records(200, sparql()) == (LookupStatus.NO_MATCH, ())
    assert parse_names(200, sparql()) == (LookupStatus.NO_MATCH, {})


def test_reconciliation_keeps_tgn_ids_only():
    body = json.dumps(
        {
            "q0": {
                "result": [
                    {"id": "aat/300008795", "name": "mountains", "score": 9},
                    {"id": "ulan/500115493", "name": "Dürer, Albrecht", "score": 8},
                    {"id": "tgn/1103742", "name": "Apo, Mount", "score": 33.8},
                    "not a result",
                ]
            }
        }
    ).encode()
    assert parse_reconcile(200, body) == (
        LookupStatus.SUCCESS,
        (Hit("1103742", "Apo, Mount", 33.8),),
    )


def test_an_id_tgn_does_not_hold_is_skipped_and_a_bad_point_is_not_read():
    body = sparql(
        {"place": "http://vocab.getty.edu/tgn/1", "lat": "1", "long": "2"},
        {"place": "http://vocab.getty.edu/tgn/2", "name": "Two"},
        {"place": "http://vocab.getty.edu/tgn/2", "lat": "95", "long": "10"},
        {"place": "http://vocab.getty.edu/tgn/3", "name": "Three"},
        {"place": "http://vocab.getty.edu/tgn/3", "lat": "north", "long": "10"},
        {"place": "http://vocab.getty.edu/aat/4", "name": "not a place"},
    )
    outcome, found = parse_records(200, body)
    assert outcome is LookupStatus.SUCCESS
    assert [(place.record_id, place.point) for place in found] == [("2", None), ("3", None)]
