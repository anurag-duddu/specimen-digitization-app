"""Getty TGN's records read through the reconciliation service's data extension
(`georef_tgn.extend_params`, `parse_extend`), which answers when the SPARQL
endpoint refuses. Offline: the recorded extension answer for the 24 records
`tgn_records.json` holds (tests/fixtures/georeferencing/tgn_extension.json)."""

import json
from pathlib import Path

import pytest

from specimen_digitization.application import georef_tgn as tgn
from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.field_research.agreement import PLACE_LEVELS

FIXTURES = Path(__file__).parent / "fixtures" / "georeferencing"


def recorded(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def raw(data):
    return json.dumps(data).encode()


def sparql_places():
    """The same 24 records as `parse_records` and `parse_names` read them."""
    status, places = tgn.parse_records(200, raw({"results": {"bindings": recorded("tgn_records.json")["bindings"]}}))
    assert status is LookupStatus.SUCCESS
    _, names = tgn.parse_names(200, raw({"results": {"bindings": recorded("tgn_names.json")["bindings"]}}))
    return {place.record_id: place for place in tgn.with_names(places, names)}


def extension_places():
    status, places = tgn.parse_extend(200, raw(recorded("tgn_extension.json")["response"]))
    assert status is LookupStatus.SUCCESS
    return {place.record_id: place for place in places}


def row(**properties):
    """One extension row; each property is a list of strings."""
    return {name: [{"str": text} for text in texts] for name, texts in properties.items()}


def answer(**rows):
    return raw({"rows": {f"tgn/{record}": value for record, value in rows.items()}})


def test_the_request_is_a_form_of_tgn_ids_and_property_names_only():
    params = tgn.extend_params(["1105587", "2502238", "1105587"])
    assert list(params) == ["extend"]
    assert json.loads(params["extend"]) == {
        "ids": ["tgn/1105587", "tgn/2502238"],
        "properties": [
            {"id": "/tgn_prefterm"},
            {"id": "/tgn_varterms"},
            {"id": "/tgn_hier"},
            {"id": "/tgn_placetypes"},
        ],
    }
    # The recorded request is the one this module writes for those records.
    assert recorded("tgn_extension.json")["request"] == tgn.extend_params(sorted(recorded("tgn_records.json")["ids"]))


@pytest.mark.parametrize("ids", [[], ["tgn/1"], ["1; DROP"], [str(n) for n in range(1, tgn.MAX_IDS + 2)]])
def test_a_request_takes_one_to_fifty_ids_of_digits_only(ids):
    with pytest.raises(ValueError):
        tgn.extend_params(ids)


def test_the_recorded_answer_reads_into_the_places_sparql_reads():
    old, new = sparql_places(), extension_places()
    assert set(new) == set(old) and len(new) == 24
    for record, place in new.items():
        other = old[record]
        assert place.source == "tgn" and place.license == tgn.LICENSE
        # The same place types, as names; the same ancestors, as names (below).
        assert {kind.name for kind in place.kinds} == {kind.name for kind in other.kinds}
        assert place.point is None
    # The names are the same where Getty's preferred term is English; one of the 24
    # records gives it in the place's own language (the SPARQL read prefers an
    # English term it knows the language of).
    assert {record for record in new if new[record].name != old[record].name} == {"1000135"}
    assert new["1000135"].name == "Pilipinas" and "Philippines" in new["1000135"].names


def test_a_place_below_a_nation_has_the_places_below_it_as_parents_and_the_nation_as_country():
    mckinley = extension_places()["1105587"]
    assert mckinley.name == "McKinley, Mount"
    # As SPARQL reads it: the places below the nation, nearest first, and the nation as the
    # country; no continent, no root. derive reads the last parent as the country.
    assert [parent.name for parent in mckinley.parents] == ["Denali", "Alaska"]
    assert (mckinley.country.id, mckinley.country.name) == ("", "United States")
    old = sparql_places()["1105587"]
    assert [parent.name for parent in mckinley.parents] == [parent.name for parent in old.parents]
    assert mckinley.country.name == old.country.name
    # No id for an ancestor or a type: names are all the service gives.
    assert {parent.id for parent in mckinley.parents} == {""} and {kind.id for kind in mckinley.kinds} == {""}
    for place in extension_places().values():
        assert all(parent.name not in tgn.CONTINENTS | {tgn.ROOT} for parent in place.parents)


def test_the_recorded_places_have_the_parents_sparql_gives_them_up_to_the_names_language():
    old, new = sparql_places(), extension_places()
    for record, place in new.items():
        other = old[record]
        assert len(place.parents) == len(other.parents), record
        assert (place.country is None) == (other.country is None), record
        assert (place.country.id == record) == (other.country.id == record) if place.country else True


@pytest.mark.parametrize(
    ("ancestors", "parents", "country"),
    [
        (["Denali", "Alaska", "United States", "North and Central America", "World"], ["Denali", "Alaska"], "United States"),
        (["Guatemala", "North and Central America", "World"], [], "Guatemala"),
        # A chain that does not end in a continent names no nation: no parents, no country.
        (["Atlantic Ocean", "World"], [], None),
        (["Somewhere", "Elsewhere"], [], None),
        (["Asia", "World"], [], None),
        (["World"], [], None),
        ([], [], None),
        # A continent's name inside the chain is a place's name there, not its end.
        (["Asia", "Bohol", "Philippines", "Asia", "World"], ["Asia", "Bohol"], "Philippines"),
        (["Bohol", "Asia", "Philippines"], [], None),
    ],
)
def test_the_nation_is_the_ancestor_right_below_the_continent_that_ends_the_chain(ancestors, parents, country):
    _, [place] = tgn.parse_extend(200, answer(**{"7": row(**{"/tgn_prefterm": ["A"], "/tgn_hier": ancestors})}))
    assert [parent.name for parent in place.parents] == parents
    assert (place.country.name if place.country else None) == country
    assert place.country is None or place.country.id == ""


def test_a_nation_is_its_own_country_and_has_no_parents():
    guatemala = extension_places()["7005493"]
    assert (guatemala.country.id, guatemala.country.name) == ("7005493", "Guatemala")
    assert guatemala.parents == ()
    assert guatemala.kinds[0].name == "nations"


def test_the_level_types_come_first_among_a_places_kinds():
    # Only the first kinds reach an expert (field_research.sources.MAX_KINDS), and the
    # service does not say which type is preferred, as SPARQL does: a department's
    # first level and a nation's "nations" must not fall behind its other types.
    new = extension_places()
    assert [kind.name for kind in new["1000621"].kinds][0] == "first level subdivisions (political entities)"
    assert [kind.name for kind in new["1016636"].kinds][:2] == ["inhabited places", "cities"]
    assert [kind.name for kind in new["7005493"].kinds][0] == "nations"
    for place in new.values():
        levels = [kind.name for kind in place.kinds if kind.name in tgn.LEVEL_TYPES]
        assert [kind.name for kind in place.kinds][: len(levels)] == levels


def test_the_level_types_are_the_ones_agreement_reads_a_place_fields_level_from():
    assert set(tgn.LEVEL_TYPES) == {kind for kinds in PLACE_LEVELS["tgn"].values() for kind in kinds}


def test_every_variant_term_is_a_name_but_the_preferred_one():
    place = extension_places()["1000135"]
    assert place.name not in place.names and len(place.names) == len(set(place.names))
    assert "Philippines" in place.names


@pytest.mark.parametrize(
    ("status", "outcome"),
    [(401, LookupStatus.AUTHENTICATION), (403, LookupStatus.AUTHORIZATION), (429, LookupStatus.RATE_LIMITED),
     (500, LookupStatus.PROVIDER)],
)
def test_a_reply_that_is_not_200_is_its_status_outcome(status, outcome):
    assert tgn.parse_extend(status, b"<html>Forbidden</html>") == (outcome, ())


@pytest.mark.parametrize(
    ("body", "outcome"),
    [
        (b"  ", LookupStatus.EMPTY),
        (b"<html>", LookupStatus.MALFORMED),
        (raw([]), LookupStatus.MALFORMED),
        (raw({"meta": []}), LookupStatus.MALFORMED),
        (raw({"rows": []}), LookupStatus.MALFORMED),
        (raw({"rows": {}}), LookupStatus.NO_MATCH),
        # A row that is no TGN place's, or has no name, or holds a property in another form:
        # malformed even beside a row that can be read.
        (raw({"rows": {"tgn/1": row(**{"/tgn_prefterm": ["Ok"]}), "aat/300": row(**{"/tgn_prefterm": ["A"]})}}),
         LookupStatus.MALFORMED),
        (raw({"rows": {"tgn/1": row(**{"/tgn_prefterm": ["A"]}), "tgn/2": row()}}), LookupStatus.MALFORMED),
        (raw({"rows": {"tgn/1": row(**{"/tgn_prefterm": ["A"]}), "tgn/2": row(**{"/tgn_prefterm": [" "]})}}),
         LookupStatus.MALFORMED),
        (raw({"rows": {"tgn/1": {"/tgn_prefterm": "A"}}}), LookupStatus.MALFORMED),
        (raw({"rows": {"tgn/1": {"/tgn_prefterm": [{"str": 3}]}}}), LookupStatus.MALFORMED),
        (raw({"rows": {"tgn/1": {"/tgn_prefterm": [{"str": "A"}], "/tgn_hier": [{"x": "Ohio"}]}}}),
         LookupStatus.MALFORMED),
        (raw({"rows": {"tgn/1": {"/tgn_prefterm": [{"str": "A"}], "/tgn_placetypes": None}}}), LookupStatus.SUCCESS),
        (raw({"rows": {"tgn/x": row(**{"/tgn_prefterm": ["A"]})}}), LookupStatus.MALFORMED),
        (raw({"rows": {"tgn/1": []}}), LookupStatus.MALFORMED),
    ],
)
def test_a_reply_that_cannot_be_read_is_never_a_place(body, outcome):
    assert tgn.parse_extend(200, body)[0] is outcome
    if outcome is not LookupStatus.SUCCESS:
        assert tgn.parse_extend(200, body)[1] == ()


def test_a_row_with_only_a_name_is_a_place_with_nothing_else():
    status, [place] = tgn.parse_extend(200, answer(**{"7": row(**{"/tgn_prefterm": ["Somewhere"]})}))
    assert status is LookupStatus.SUCCESS
    assert (place.name, place.names, place.kinds, place.parents, place.country, place.point) == (
        "Somewhere", (), (), (), None, None)


def test_a_continent_has_no_parents_and_no_country():
    _, [place] = tgn.parse_extend(200, answer(**{"1000007": row(**{
        "/tgn_prefterm": ["Antarctica"], "/tgn_hier": ["World"], "/tgn_placetypes": ["continents"]})}))
    assert place.parents == () and place.country is None


def test_a_point_the_service_writes_is_not_read():
    # "[-0.2.5833,35.5667]" is what the service wrote for West Asheville (-82.5833,
    # 35.5667), and "[-0.0,-0.1]" for Chile (-71, -30): never a coordinate to trust.
    for text in ("[-0.2.5833,35.5667]", "[-0.0,-0.1]", "[-82.5833,35.5667]"):
        _, [place] = tgn.parse_extend(200, answer(**{"7": row(**{"/tgn_prefterm": ["A"], "/tgn_coordinates": [text]})}))
        assert place.point is None


def test_a_place_is_named_as_the_reconciliation_service_names_it_when_that_is_one_of_its_terms():
    new = extension_places()
    philippines = tgn.with_hit_names(new.values(), [tgn.Hit("1000135", "Philippines", 100.0)])
    [named] = [place for place in philippines if place.record_id == "1000135"]
    assert named.name == "Philippines" and named.names[0] == "Pilipinas"
    assert (named.country.id, named.country.name) == ("1000135", "Philippines")
    assert set(named.names) == (set(new["1000135"].names) | {"Pilipinas"}) - {"Philippines"}
    # Every other place keeps what it was, and so does one whose hit name is none of its terms.
    assert [place for place in philippines if place.record_id != "1000135"] == [
        place for place in new.values() if place.record_id != "1000135"]
    strange = tgn.with_hit_names(new.values(), [tgn.Hit("1000135", "Not a term of it"), tgn.Hit("1000621", None)])
    assert tuple(new.values()) == strange


def test_with_hit_names_reads_the_recorded_places_as_sparql_names_them():
    # Over the 24 recorded records, naming each as the recorded reconciliation names it leaves one
    # difference from the names SPARQL gives, none for an English preferred term.
    old = sparql_places()
    hits = [
        tgn.Hit(hit["id"].split("/")[1], hit["name"], hit["score"])
        for hits in fixture_hits().values() for hit in hits if hit["id"].split("/")[1] in old
    ]
    named = {place.record_id: place for place in tgn.with_hit_names(extension_places().values(), hits)}
    assert {record for record in named if named[record].name != old[record].name} == set()


def fixture_hits():
    return recorded("tgn_reconcile.json")["responses"]
