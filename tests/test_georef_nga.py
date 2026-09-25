"""Tier 1 NGA GNS requests and answers for the retrospective georeferencing tool (GEO.md 8)."""

import json
from pathlib import Path

import pytest

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.georef_nga import (
    CREDIT,
    FIELDS,
    LICENSE,
    features_params,
    name_units,
    parse_features,
    parse_search,
    parse_units,
    search_params,
    unit_codes,
    units_params,
)
from specimen_digitization.application.georef_places import Ref

FIXTURES = Path(__file__).parent / "fixtures" / "georeferencing"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def answer(*rows, **extra):
    return json.dumps({"features": [{"attributes": row} for row in rows], **extra}).encode()


def service_error(code, message):
    """An error GNS reports inside an HTTP 200 answer."""
    return json.dumps({"error": {"code": code, "message": message, "details": []}}).encode()


def search_body(reading):
    return answer(*fixture("nga_search.json")["responses"][reading])


def search(reading):
    outcome, ids = parse_search(200, search_body(reading))
    assert outcome is LookupStatus.SUCCESS
    return ids


def places():
    outcome, found = parse_features(200, answer(*fixture("nga_features.json")["features"]))
    assert outcome is LookupStatus.SUCCESS
    status, units = parse_units(200, answer(*fixture("nga_units.json")["features"]))
    assert status is LookupStatus.SUCCESS
    return {place.record_id: place for place in name_units(found, units)}


def test_a_name_search_quotes_one_name_in_a_fixed_where_clause():
    assert search_params("Mount Apo") == {
        "where": "UPPER(full_name) = UPPER('Mount Apo') OR UPPER(full_nm_nd) = UPPER('Mount Apo')",
        "outFields": FIELDS,
        "returnGeometry": "false",
        "orderByFields": "ufi,uni",
        "f": "json",
    }
    assert search_params("O'Neil's Hill")["where"].count("'O''Neil''s Hill'") == 2
    for name in ("", "   ", "Apo\nMount", "Apo\x00", "Apo​", "x" * 201):
        with pytest.raises(ValueError):
            search_params(name)


def test_features_and_units_take_checked_values_fifty_at_a_time():
    assert features_params(["-2408935", "6400675", "-2408935"])["where"] == (
        "ufi IN (-2408935, 6400675)"
    )
    assert units_params(["PH-NCO", "GT-04"]) == {
        "where": "adm1 IN ('PH-NCO', 'GT-04')",
        "outFields": "adm1,adm1_name",
        "orderByFields": "adm1",
        "f": "json",
    }
    for ids in ([], [str(number) for number in range(51)], ["1 OR 1=1"], ["1.5"], ["１２"]):
        with pytest.raises(ValueError):
            features_params(ids)
    for codes in ([], ["PH-NCO') OR ('1'='1"], ["ph-nco"], ["PHNCO"], ["PH-NCOX"]):
        with pytest.raises(ValueError):
            units_params(codes)


def test_mount_apo_names_three_mountains_and_a_street():
    found = places()
    apo = [found[ufi] for ufi in search("Mount Apo")]
    assert [(place.kinds[0].id, [ref.name for ref in place.parents]) for place in apo] == [
        ("T.MT", ["Iloilo"]),
        ("T.MT", ["Cotabato"]),
        ("T.MT", ["Davao Occidental"]),
        ("R.ST", ["Makati"]),
    ]
    # Iloilo's is found through a variant name.
    assert apo[0].name == "Apo Mountain" and "Mount Apo" in apo[0].names
    assert apo[1].point == pytest.approx((6.989444, 125.269722))


def test_no_mount_mckinley_and_no_chimaltenago():
    for reading in ("Mount McKinley", "Chimaltenago"):
        assert parse_search(200, search_body(reading)) == (LookupStatus.NO_MATCH, ())


def test_davao_province_names_only_modern_davao_del_norte():
    (ufi,) = search("Davao Province")
    davao = places()[ufi]
    assert (davao.name, davao.kinds[0].id, davao.parents) == ("Davao del Norte", "A.ADM1", ())
    assert {"Davao Province", "Province of Davao", "Davao"} <= set(davao.names)


def test_yepocapa_is_a_municipio_and_a_town_in_chimaltenango_at_geonames_points():
    found = places()
    municipio, town = (found[ufi] for ufi in search("Yepocapa"))
    assert (municipio.kinds[0].id, town.kinds[0].id) == ("A.ADM2", "P.PPLA2")
    assert municipio.parents == town.parents == (Ref("GT-04", "Chimaltenango"),)
    assert municipio.country == town.country == Ref("GT")
    # GeoNames 3587635 and 3587636 (section 4) give the same points to five decimals.
    assert municipio.point == pytest.approx((14.46725, -90.97416), abs=1e-5)
    assert town.point == pytest.approx((14.50195, -90.95396), abs=1e-5)


def test_mount_talomo_lies_in_davao_city():
    (ufi,) = search("Mount Talomo")
    assert places()[ufi].parents == (Ref("PH-DVC", "Davao"),)


def test_the_country_code_comes_from_the_first_order_code():
    found = places()
    philippines = found["-2445615"]
    assert (philippines.name, philippines.kinds[0].id) == ("Philippines", "A.PCLI")
    assert (philippines.country, philippines.iso_code, philippines.parents) == (
        Ref("PH"),
        "PH",
        (),
    )
    assert "Philippine Islands" in philippines.names
    assert found["-1135822"].iso_code == "GT"
    assert found["-2445612"].iso_code is None  # the island group is not the country


def test_a_terminated_feature_is_skipped():
    # 1663372800000 is 2022-09-17, the termination date GNS gives Maguindanao.
    body = answer(
        {"ufi": -2435837, "full_name": "Maguindanao", "nt": "N", "term_dt_f": 1663372800000},
        {"ufi": 1, "full_name": "Current", "nt": "N", "term_dt_f": None},
    )
    assert parse_search(200, body) == (LookupStatus.SUCCESS, ("1",))
    outcome, found = parse_features(200, body)
    assert (outcome, [place.record_id for place in found]) == (LookupStatus.SUCCESS, ["1"])


def test_a_feature_is_named_by_its_approved_name_first():
    body = answer(
        {"ufi": 5, "uni": 3, "full_name": "Variant", "nt": "V"},
        {"ufi": 5, "uni": 2, "full_name": "Conventional", "nt": "C"},
        {"ufi": 5, "uni": 1, "full_name": "Approved", "full_nm_nd": "Approved", "nt": "N"},
        {"ufi": 5, "uni": 4, "full_name": "Script", "nt": "NS"},
    )
    (place,) = parse_features(200, body)[1]
    assert (place.name, place.names) == ("Approved", ("Conventional", "Variant", "Script"))


def test_rows_without_a_usable_id_name_or_point():
    body = answer(
        {"ufi": True, "full_name": "A true id"},
        {"ufi": "12", "full_name": "A text id"},
        {"ufi": 7, "full_name": "", "nt": "N"},
        {"ufi": 8, "full_name": "Out of range", "lat_dd": 95.0, "long_dd": 10.0, "adm1": "XX"},
    )
    outcome, found = parse_features(200, body)
    assert outcome is LookupStatus.SUCCESS
    assert [(place.record_id, place.point, place.country) for place in found] == [
        ("8", None, None)
    ]


def test_unit_codes_are_what_the_units_request_named():
    _, found = parse_features(200, answer(*fixture("nga_features.json")["features"]))
    assert unit_codes(found) == set(fixture("nga_units.json")["codes"])


def test_places_are_credited_to_nga_with_no_license_id():
    assert (CREDIT, LICENSE) == ("NGA GEOnet Names Server", None)
    assert {(place.source, place.license) for place in places().values()} == {("nga", None)}


@pytest.mark.parametrize(
    ("status", "body", "outcome"),
    [
        (200, b"", LookupStatus.EMPTY),
        (200, b" \n", LookupStatus.EMPTY),
        (200, b"<html>busy</html>", LookupStatus.MALFORMED),
        (200, b"[]", LookupStatus.MALFORMED),
        (200, b"{}", LookupStatus.MALFORMED),
        (200, service_error(400, "Failed to execute query."), LookupStatus.MALFORMED),
        (200, service_error(498, "Invalid token."), LookupStatus.AUTHENTICATION),
        (200, service_error(499, "Token Required"), LookupStatus.AUTHENTICATION),
        (200, service_error(401, "Unauthorized"), LookupStatus.AUTHENTICATION),
        (200, service_error(403, "Access denied"), LookupStatus.AUTHORIZATION),
        (200, service_error(429, "Too many requests"), LookupStatus.RATE_LIMITED),
        (200, service_error(500, "Query failed"), LookupStatus.PROVIDER),
        (429, b"", LookupStatus.RATE_LIMITED),
        (401, b"", LookupStatus.AUTHENTICATION),
        (403, b"", LookupStatus.AUTHORIZATION),
        (500, b"", LookupStatus.PROVIDER),
        (404, b"", LookupStatus.PROVIDER),
    ],
)
def test_every_answer_maps_to_one_outcome(status, body, outcome):
    assert parse_search(status, body) == (outcome, ())
    assert parse_features(status, body) == (outcome, ())
    assert parse_units(status, body) == (outcome, {})


def test_answers_that_find_nothing_or_are_cut_short():
    empty = answer()
    assert parse_search(200, empty) == (LookupStatus.NO_MATCH, ())
    assert parse_features(200, empty) == (LookupStatus.NO_MATCH, ())
    assert parse_units(200, empty) == (LookupStatus.NO_MATCH, {})
    cut = answer({"ufi": 1, "full_name": "One", "nt": "N"}, exceededTransferLimit=True)
    assert parse_search(200, cut) == (LookupStatus.AMBIGUOUS, ())
    assert parse_features(200, cut) == (LookupStatus.MALFORMED, ())
