"""Tier 1 GeoNames, read from the pinned country dumps (GEO.md 4)."""

import io
import zipfile
from pathlib import Path

import pytest

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.georef_geonames import LICENSE, find, read_dump
from specimen_digitization.application.georef_places import Ref

FIXTURES = Path(__file__).parent / "fixtures" / "georeferencing"


def dump_bytes(country, text=None):
    """A dump as GeoNames zips it, holding the fixture's rows of the pinned dump."""
    if text is None:
        text = (FIXTURES / f"geonames_{country}.txt").read_text(encoding="utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{country}.txt", text)
        archive.writestr("readme.txt", "CC BY 4.0")
    return buffer.getvalue()


@pytest.fixture(scope="module")
def philippines():
    status, dump = read_dump("PH", dump_bytes("PH"))
    assert status is LookupStatus.SUCCESS
    return dump


@pytest.fixture(scope="module")
def guatemala():
    status, dump = read_dump("GT", dump_bytes("GT"))
    assert status is LookupStatus.SUCCESS
    return dump


def ids(places):
    return [place.record_id for place in places]


def test_davao_province_names_modern_davao_del_norte_in_geonames(philippines):
    # #94's trap: GeoNames carries "Davao Province" only as an alternate name of
    # the 1967 successor Davao del Norte, never as the province of 1914 to 1967.
    matches = find(philippines, "Davao Province", kinds={"A.ADM2"})
    assert ids(matches.exact) == ["1715347"]
    (norte,) = matches.exact
    assert norte.name == "Province of Davao del Norte" and "Davao Province" in norte.names
    assert norte.parents == (Ref("7521309", "Davao"),)
    # Without the level, the key "davao" also names the region and the city.
    assert set(ids(find(philippines, "Davao Province", kinds={"A"}).exact)) == {
        "7521309",
        "1715347",
        "1715346",
    }


def test_chimaltenago_is_one_letter_from_chimaltenango(guatemala):
    matches = find(guatemala, "Chimaltenago", kinds={"A"})
    assert matches.exact == ()
    assert ids(matches.near) == ["3598571", "3598570"]
    assert ids(find(guatemala, "Chimaltenago", kinds={"A.ADM1"}).near) == ["3598571"]
    assert ids(find(guatemala, "Chimaltenango", kinds={"A.ADM1"}).exact) == ["3598571"]


def test_three_features_called_mount_apo(philippines):
    matches = find(philippines, "Mt. Apo", kinds={"T"})
    by_id = {place.record_id: place for place in matches.exact}
    assert set(by_id) == {"1730340", "6569865", "1730339"}
    assert [ref.name for ref in by_id["1730340"].parents] == ["Cotabato", "Soccsksargen"]
    assert [ref.name for ref in by_id["6569865"].parents] == ["Davao Occidental", "Davao"]
    assert [ref.name for ref in by_id["1730339"].parents] == [
        "Province of Iloilo",
        "Western Visayas",
    ]
    assert by_id["1730340"].point == pytest.approx((6.98781, 125.27109))
    assert by_id["1730340"].kinds == (Ref("T.MT"),)


def test_no_philippine_mount_mckinley(philippines):
    assert find(philippines, "Mt. McKinley") == find(philippines, "Mount McKinley")
    assert find(philippines, "Mount McKinley").exact == ()
    assert find(philippines, "Mount McKinley").near == ()


def test_each_country_is_its_own_dump(philippines, guatemala):
    assert ids(find(philippines, "Mindanao", kinds={"T"}).exact) == ["1699597"]
    village = find(guatemala, "Mindanao").exact
    assert ids(village) == ["12037933"] and village[0].country == Ref("GT", "Republic of Guatemala")


def test_yepocapa_town_and_municipio(guatemala):
    matches = find(guatemala, "Yepocapa")
    assert ids(matches.exact) == ["3587635", "3587636"]
    town = matches.exact[1]
    assert town.kinds == (Ref("P.PPLA2"),)
    assert town.parents == (
        Ref("3587635", "Municipio de Yepocapa"),
        Ref("3598571", "Departamento de Chimaltenango"),
    )


def test_country_rows_carry_their_iso_code(philippines):
    (country,) = find(philippines, "Philippine Islands").exact
    assert (country.record_id, country.iso_code) == ("1694008", "PH")
    assert country.country == Ref("PH", "Republic of the Philippines")
    assert (country.source, country.license) == ("geonames", LICENSE) == ("geonames", "CC BY 4.0")


def test_near_matches_need_full_names(philippines):
    assert ids(find(philippines, "Mindanaw", kinds={"T"}).near) == ["1699597"]
    assert find(philippines, "RP").near == ()  # a code never reaches the one-letter gate
    assert find(philippines, "P.I.").near == ()


@pytest.mark.parametrize(
    ("data", "outcome"),
    [
        (b"", LookupStatus.EMPTY),
        (b"not a zip", LookupStatus.MALFORMED),
        (dump_bytes("GT")[:-5], LookupStatus.MALFORMED),
    ],
)
def test_unreadable_dumps(data, outcome):
    assert read_dump("GT", data) == (outcome, None)


def test_a_dump_without_its_country_file_or_with_short_rows_is_malformed():
    assert read_dump("PH", dump_bytes("GT")) == (LookupStatus.MALFORMED, None)
    assert read_dump("GT", dump_bytes("GT", "3587636\tYepocapa\n")) == (
        LookupStatus.MALFORMED,
        None,
    )
