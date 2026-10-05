"""History for the retrospective georeferencing tool (GEO.md 5)."""

import json
from datetime import date
from pathlib import Path

import pytest

from specimen_digitization.application.georef_history import (
    Use,
    interval,
    modern_successors,
    parents_on,
    role,
    use_on,
)
from specimen_digitization.application.georef_places import Place, Ref
from specimen_digitization.application.georef_wikidata import (
    name_refs,
    parse_entities,
    parse_labels,
)

FIXTURES = Path(__file__).parent / "fixtures" / "georeferencing"


def wikidata_places():
    entities = json.loads((FIXTURES / "wikidata_entities.json").read_text())["entities"]
    labels = json.loads((FIXTURES / "wikidata_labels.json").read_text())["entities"]
    _, found = parse_entities(200, json.dumps({"entities": entities}).encode())
    _, names = parse_labels(200, json.dumps({"entities": labels}).encode())
    return {place.record_id: place for place in name_refs(found, names)}


PLACES = wikidata_places()
DAVAO = PLACES["Q15095071"]  # the province of 1914 to 1967
# The Commonwealth of the Philippines with its Wikidata dates (Q146328: inception
# 1935-11-15, dissolved 1946-07-04), built here because the fixture only names it.
COMMONWEALTH = Place(
    source="wikidata",
    record_id="Q146328",
    name="Commonwealth of the Philippines",
    valid_from="1935-11-15",
    valid_to="1946-07-04",
)


def test_a_date_means_the_whole_interval_written():
    assert interval("1946") == (date(1946, 1, 1), date(1946, 12, 31))
    assert interval("1946-09") == (date(1946, 9, 1), date(1946, 9, 30))
    assert interval("1946-09-03") == (date(1946, 9, 3), date(1946, 9, 3))
    assert interval("1948-02") == (date(1948, 2, 1), date(1948, 2, 29))


@pytest.mark.parametrize(
    ("written", "use"),
    [
        ("1946-09-03", Use("in_use")),  # 105526321
        ("1946", Use("in_use")),
        ("1914", Use("partly")),  # founded 1914-09-01
        ("1967-05", Use("partly")),  # dissolved 1967-05-08
        ("1970", Use("ended", gap_days=969)),
        ("1900", Use("not_started")),
    ],
)
def test_the_1946_davao_province_was_in_use(written, use):
    assert use_on(DAVAO, written) == use


def test_places_founded_later_or_named_after_they_ended():
    assert use_on(PLACES["Q1504280"], "1946-11") == Use(
        "not_started"
    )  # Mount Apo Natural Park, 2004
    # "P.I." on labels of September 1946: the Commonwealth ended on 4 July 1946.
    assert use_on(COMMONWEALTH, "1946-09") == Use("ended", gap_days=59)
    assert use_on(PLACES["Q928"], "1946-09") == Use("in_use")  # the Philippines, from 1565
    assert use_on(PLACES["Q455963"], "1946-11") == Use("undated")  # Mount Apo carries no dates


def test_roles():
    assert role(DAVAO) == "historical"
    assert role(PLACES["Q455963"]) == "modern"
    assert role(PLACES["Q928"]) == "modern"


def test_the_province_of_1946_has_three_modern_successors():
    successors = modern_successors(DAVAO, PLACES)
    assert [ref.name for ref in successors] == [
        "Davao del Norte",
        "Davao del Sur",
        "Davao Oriental",
    ]


def test_successor_chains_are_followed_to_a_place_without_an_end():
    old = Place(source="t", record_id="A", name="A", valid_to="1900", replaced_by=(Ref("B"),))
    middle = Place(
        source="t", record_id="B", name="B", valid_to="1950", replaced_by=(Ref("C"), Ref("A"))
    )
    places = {"A": old, "B": middle}
    assert modern_successors(old, places) == (Ref("C"),)


def test_parents_on_a_date_follow_their_stated_start_and_end():
    place = Place(
        source="t",
        record_id="X",
        name="X",
        parents=(
            Ref("Q-old", "Old province", start="1914-09-01", end="1967-05-08"),
            Ref("Q-new", "New province", start="1967-05-08"),
            Ref("Q-any", "Region"),
        ),
    )
    assert [ref.id for ref in parents_on(place, "1946-09")] == ["Q-old", "Q-any"]
    assert [ref.id for ref in parents_on(place, "1990")] == ["Q-new", "Q-any"]
