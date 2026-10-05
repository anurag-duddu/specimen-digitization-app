"""Curated entries: places and itineraries only the museum's records know (GEO.md 6)."""

from dataclasses import fields, replace

import pytest

from specimen_digitization.application.georef_curated import (
    ITINERARIES,
    PLACES,
    Confirmation,
    curated_place,
    matching_camps,
    settles,
)

MCKINLEY_CAMPS, APO_CAMPS = ITINERARIES


def test_an_unconfirmed_entry_never_settles_a_field():
    # PLAN 4.8: an entry becomes confirmed only in a pull request citing the
    # owner's recorded confirmation; every entry drafted here is unconfirmed.
    for entry in (*PLACES, *ITINERARIES):
        assert entry.confirmation is None
        assert not settles(entry)
        assert entry.sources


def test_a_confirmed_entry_records_a_role_and_a_date_never_a_name():
    assert [field.name for field in fields(Confirmation)] == ["role", "date", "record"]
    confirmed = replace(
        PLACES[0],
        confirmation=Confirmation(
            role="Insects collection manager",
            date="2026-10-01",
            record="the owner's recorded confirmation, cited by its PLAN row",
        ),
    )
    assert settles(confirmed)
    with pytest.raises(ValueError):
        Confirmation(role="Insects collection manager", date="2026-10", record="G99")
    with pytest.raises(ValueError):
        Confirmation(role="", date="2026-10-01", record="G99")


def test_the_davao_mount_mckinley_is_a_curated_hypothesis():
    entry = curated_place("PH", "Mt. McKinley")
    assert entry is curated_place("PH", "Mount McKinley") is PLACES[0]
    assert (entry.proposed, entry.proposed_ids) == (
        "Mount Talomo",
        ("wikidata:Q31472786", "geonames:1683778"),
    )
    assert curated_place("US", "Mount McKinley") is None  # Denali is not this entry
    assert curated_place("PH", "Mount Apo") is None


@pytest.mark.parametrize(
    ("collector", "written", "elevation", "camps"),
    [
        ("F.G. Werner", "1946-09-03", 6400, ["6,400-foot camp"]),  # 105526321
        ("H. Hoogstraal leg.", "1946-09-06", 6400, ["6,400-foot camp"]),  # 105526322
        ("H. Hoogstraal; CNHM", "1946-09-14", 3300, ["base camp"]),  # 105526324
        ("R.D. Mitchell", "1946-09-14", 3300, []),
        ("H. Hoogstraal", "1947-01", None, []),
    ],
)
def test_mckinley_labels_fit_their_camps(collector, written, elevation, camps):
    matched = matching_camps(MCKINLEY_CAMPS, collector, written, elevation_ft=elevation)
    assert [camp.name for camp in matched] == camps


def test_the_apo_label_fits_the_east_slope_camps_of_november_1946():
    # 105526327: "E. slope Mt. Apo", XI.'46, H. Hoogstraal, no elevation.
    matched = matching_camps(APO_CAMPS, "H. Hoogstraal", "1946-11", slope="east")
    assert [camp.name for camp in matched] == [
        "Todaya village",
        "Meran",
        "Baclayan",
        "Baclayan River fumarole",
        "Crater Lake",
        "Mainit",
    ]
    assert APO_CAMPS.place == "wikidata:Q455963"  # the massif, not the Malita "Mount Apo"
    assert min(camp.elevation_ft for camp in APO_CAMPS.camps) == 2800
