"""Getty TGN's name search through the SPARQL endpoint, which stands in for the
reconciliation service when that refuses a request or cannot be reached: the
request keeps any place text inside one string and one set of Lucene words, the
answer is read strictly, and the places named as asked come first."""

import json
from urllib.parse import urlencode

import pytest

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.georef_tgn import (
    LIMIT,
    LUCENE_SYNTAX,
    SEARCH,
    SEARCH_DEPTH,
    SPARQL,
    TGN,
    Term,
    lucene_words,
    parse_search,
    search_ids,
    search_params,
    sparql_string,
)
from specimen_digitization.field_research.sources import approved_registry
from specimen_digitization.research_harness.sources import validate_destination

HEAD, TAIL = SEARCH.split('"%s"')
SPARQL_UNESCAPES = {"t": "\t", "n": "\n", "r": "\r", "b": "\b", "f": "\f", '"': '"', "'": "'", "\\": "\\"}
HOSTILE = [
    'Manila" } } SELECT * WHERE { ?s ?p ?o } #',
    "Manila\\",
    "Manila\\u0022 } #",
    "\\\\\\\"",
    "Manila AND NOT Bay OR Creek",
    "+Manila -Bay && Creek || !Ridge",
    "Mani?a* Manila~2 Manila^4",
    "title:Manila /regex/ [a TO z] {a TO z} (Manila)",
    "Sao Paulo (Brazil): 'Barraca'",
    "%s %d %%",
    "***",
]


def literal_of(query):
    """The SPARQL string luc:term searches, read as a SPARQL parser reads a
    double-quoted string; the query around it must be the template's."""
    assert query.startswith(HEAD + '"')
    text, index = [], len(HEAD) + 1
    while query[index] != '"':
        character = query[index]
        assert character not in "\n\r", "a SPARQL string cannot hold a raw line break"
        if character == "\\":
            index += 1
            assert query[index] in SPARQL_UNESCAPES, "only SPARQL's own escapes"
            character = SPARQL_UNESCAPES[query[index]]
        text.append(character)
        index += 1
    assert query[index + 1 :] == TAIL % SEARCH_DEPTH
    return "".join(text)


def lucene_operators(text):
    """The characters of Lucene query text its parser would read as syntax:
    an unescaped LUCENE_SYNTAX character, or AND, OR or NOT as a word."""
    operators, index, plain = [], 0, []
    while index < len(text):
        if text[index] == "\\":
            plain.append(" ")
            index += 2
            continue
        if text[index] in LUCENE_SYNTAX:
            operators.append(text[index])
        plain.append(text[index])
        index += 1
    return operators + [word for word in "".join(plain).split() if word in ("AND", "OR", "NOT")]


def lucene_text(text):
    """Lucene query text with its escapes undone."""
    out, index = [], 0
    while index < len(text):
        if text[index] == "\\":
            index += 1
        out.append(text[index])
        index += 1
    return "".join(out)


def rows(*bindings):
    return json.dumps(
        {"results": {"bindings": [
            {variable: {"value": value} for variable, value in row.items()} for row in bindings
        ]}}
    ).encode()


def term(record, name, preferred="true", **extra):
    return {"place": TGN + record, "name": name, "preferred": preferred, **extra}


def test_a_search_asks_tgn_full_text_index_for_fifty_places_with_every_term():
    query = search_params("Davao")["query"]
    assert 'luc:term "davao" ; skos:inScheme tgn:' in query
    assert f"LIMIT {SEARCH_DEPTH}" in query and SEARCH_DEPTH == 50
    assert "xl:prefLabel" in query and "xl:altLabel" in query and "dct:language" in query
    assert literal_of(query) == "davao"


@pytest.mark.parametrize("text", HOSTILE)
def test_hostile_place_text_stays_one_string_of_lucene_words(text):
    literal = literal_of(search_params(text)["query"])
    assert lucene_operators(literal) == []
    assert lucene_text(literal) == text.lower()


@pytest.mark.parametrize(
    "text", ["Manila\nBay", "Manila\r", "Manila\t", "Manila\x00", "Mani\u200bla", "", "   ", "x" * 201, 7]
)
def test_unprintable_empty_or_long_place_text_is_refused(text):
    with pytest.raises(ValueError):
        search_params(text)


def test_a_sparql_string_escapes_what_it_cannot_hold_and_refuses_other_controls():
    assert sparql_string('a"b\\c\nd\re\tf\bg\fh') == 'a\\"b\\\\c\\nd\\re\\tf\\bg\\fh'
    with pytest.raises(ValueError):
        sparql_string("a\x00b")
    assert lucene_words("Manila (AND) Bay*") == "manila \\(and\\) bay\\*"


def test_the_search_goes_only_where_the_approved_registry_already_sends_tgn():
    policy = approved_registry().get("tgn")
    assert policy.allowed_hosts == ("services.getty.edu", "vocab.getty.edu")
    for text in ["Davao", *HOSTILE]:
        validate_destination(policy, SPARQL + "?" + urlencode(search_params(text)))


def test_a_search_answer_keeps_each_place_and_its_terms_in_the_index_order():
    body = rows(
        term("2", "Manila Bay"),
        term("1", "Manila", language="http://vocab.getty.edu/aat/300388277"),
        term("2", "Bahia de Manila", "false"),
        term("1", "Manila", "false"),
    )
    outcome, found = parse_search(200, body)
    assert outcome is LookupStatus.SUCCESS
    assert list(found) == ["2", "1"]
    assert found["2"] == (Term("Manila Bay", None, True), Term("Bahia de Manila", None, False))
    assert found["1"] == (
        Term("Manila", "http://vocab.getty.edu/aat/300388277", True),
        Term("Manila", None, False),
    )


@pytest.mark.parametrize(
    ("status", "body", "outcome"),
    [
        (200, rows(), LookupStatus.NO_MATCH),
        (403, b"<html>blocked</html>", LookupStatus.AUTHORIZATION),
        (401, b"", LookupStatus.AUTHENTICATION),
        (500, b"", LookupStatus.PROVIDER),
        (200, b"", LookupStatus.EMPTY),
        (200, b"<html>maintenance</html>", LookupStatus.MALFORMED),
        (200, json.dumps({"results": {}}).encode(), LookupStatus.MALFORMED),
        # A row that is no TGN place with a term and a preferred flag.
        (200, rows(term("1", "Manila"), {"place": "http://vocab.getty.edu/aat/300008347",
            "name": "Manila", "preferred": "true"}), LookupStatus.MALFORMED),
        (200, rows({"place": TGN + "tgn/1", "name": "Manila", "preferred": "true"}), LookupStatus.MALFORMED),
        (200, rows({"place": TGN + "1", "preferred": "true"}), LookupStatus.MALFORMED),
        (200, rows(term("1", "")), LookupStatus.MALFORMED),
        (200, rows(term("1", "Manila", "yes")), LookupStatus.MALFORMED),
        (200, rows({"place": TGN + "1", "name": "Manila"}), LookupStatus.MALFORMED),
        (200, json.dumps({"results": {"bindings": [{"place": {"value": 1}}]}}).encode(),
         LookupStatus.MALFORMED),
        # More places than the search asks for.
        (200, rows(*(term(str(index), "Manila") for index in range(SEARCH_DEPTH + 1))),
         LookupStatus.MALFORMED),
    ],
)
def test_every_search_answer_maps_to_one_outcome(status, body, outcome):
    found_outcome, found = parse_search(status, body)
    assert found_outcome is outcome
    assert found == {}


def test_places_named_as_asked_come_first_then_the_index_order_and_ten_at_most():
    found = {
        "1": (Term("McKinley"),),
        "2": (Term("Denali National Park"),),
        "3": (Term("McKinley, Mount"), Term("Denali", None, False)),
        **{str(index): (Term(f"McKinley Creek {index}"),) for index in range(4, 13)},
        "13": (Term("Bolshaya Gora"), Term("MOUNT  McKINLEY", None, False)),
        "14": (Term("Mount McKinley's Creek"),),
    }
    ids = search_ids("Mount McKinley", found)
    assert len(ids) == LIMIT
    assert ids[:2] == ("3", "13")
    assert ids[2:] == ("1", "2", "4", "5", "6", "7", "8", "9")


def test_accents_case_and_punctuation_do_not_change_the_words():
    found = {"1": (Term("Sao Hill"),), "2": (Term("S\u00e3o Paulo"),), "3": (Term("Sao-Paulo"),)}
    assert search_ids("Sao Paulo", found) == ("2", "3", "1")
    assert search_ids("SAO PAULO", found) == ("2", "3", "1")
    assert search_ids("Hill", found) == ("1", "2", "3")
