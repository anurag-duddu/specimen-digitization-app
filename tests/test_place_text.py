"""PLAN 4.8's place-request filter (HARNESS.md section 7), case by case as the
guarantees 4.8 states: no cut character leaves, an expansion carries only its
full form, and a value not drawn from the sources is refused."""

import pytest

from specimen_digitization.application.harness_knowledge import insects
from specimen_digitization.application.place_text import (
    fold,
    place_request_forms,
    place_request_identifier,
    place_request_text,
    unassigned_text,
)

# 105526321's place lines.
PLACES = "E. slope Mt. McKinley\nDavao Prov.\nMindanao, P.I."


def request(text, *sources, others=()):
    """The value as written after the cuts, drawn from `sources` (itself by
    default)."""
    return place_request_text(
        text,
        sources=sources or (text,),
        non_place_literals=others,
        knowledge=insects,
        readings=sources or (text,),
    )


def forms(text, *sources, others=()):
    """Every form of the value that may leave, its sources read as readings."""
    return place_request_forms(
        text,
        sources=sources or (text,),
        non_place_literals=others,
        knowledge=insects,
        readings=sources or (text,),
    )


def words(text):
    return set(fold(text).split())


def given(text, reading, others=()):
    """Every form of a place literal the agent gave, the query's own source,
    with its reading read for the cuts (PLAN 4.8 in #191)."""
    return place_request_forms(
        text,
        sources=[text],
        readings=[reading],
        non_place_literals=others,
        knowledge=insects,
    )


@pytest.mark.parametrize(
    "text",
    ["Manila", "Davao Prov., Mindanao", "davao prov.", "Mount Apo", "", " "],
    ids=[
        "elsewhere",
        "joined-anew",
        "recased",
        "full-form-of-elsewhere",
        "empty",
        "blank",
    ],
)
def test_a_value_not_drawn_from_the_sources_is_refused(text):
    assert request(text, PLACES) is None and forms(text, PLACES) is None


def test_what_survives_keeps_its_clauses_single_spaced_and_its_separators():
    # S8's parser reads the line breaks: a line ending in "Mt." joins the next.
    text = "E. slope  Mt. McKinley\nDavao Prov.,leg. Hoogstraal\nMindanao,  P.I."

    assert request(text) == PLACES


def test_the_value_leaves_as_written_then_in_full():
    assert forms(PLACES) == [
        PLACES,
        "E. slope Mount McKinley\nDavao Province\nMindanao, Philippine Islands",
    ]


@pytest.mark.parametrize(
    ("text", "full"),
    [
        ("Davao Prov.", "Davao Province"),
        ("Mt. McKinley", "Mount McKinley"),
        ("Mindanao, P.I.", "Mindanao, Philippine Islands"),
    ],
)
def test_a_surviving_notation_may_leave_in_its_full_form(text, full):
    # The coordinator's ruling of 2026-09-24 (option c).
    assert forms(text, PLACES) == [text, full]


@pytest.mark.parametrize("written", insects.FULL_FORMS)
def test_every_full_form_in_the_table_leaves_and_nothing_else_with_it(written):
    text = f"Mindanao {written}"

    assert forms(text) == [
        text,
        *(f"Mindanao {full}" for full in insects.FULL_FORMS[written]),
    ]


def test_each_full_form_makes_its_own_form():
    # G29: every reading a notation allows; "Is." is an island or islands.
    assert forms("Camiguin Is., P.I.") == [
        "Camiguin Is., P.I.",
        "Camiguin Island, Philippine Islands",
        "Camiguin Islands, Philippine Islands",
    ]


def test_a_full_form_leaves_the_marker_clause_cut():
    assert forms("Davao Prov., leg. Hoogstraal") == ["Davao Prov.", "Davao Province"]


def test_a_source_written_out_in_full_is_a_source():
    assert forms("Mount McKinley", PLACES) == ["Mount McKinley"]


def test_a_full_form_never_brings_back_a_cut_character():
    label = "Mt. Apo leg. Hoogstraal\nDavao Prov."

    assert request("Mount Apo", label) == ""
    assert forms(label) == ["Davao Prov.", "Davao Province"]


def test_a_notation_whose_full_form_the_cuts_name_is_cut():
    # Each full form goes through the same cuts: "Mount" is a non-place word.
    assert forms("Mt. Apo, Davao", others=["Mount forest"]) == ["Apo, Davao"]


HOOGSTRAAL, DATE, CATALOGUE = "H. Hoogstraal leg.", "3 Sept. '46", "FMNH INS 0123456"
PLACEMENTS = {
    "own-line": "Davao Prov.\n{}\nMindanao, P.I.",
    "own-clause": "Davao Prov.\nMindanao, {}, P.I.",
    "inside-a-clause": "Davao Prov.\nMindanao {} P.I.",
}


@pytest.mark.parametrize("placement", PLACEMENTS)
@pytest.mark.parametrize(
    ("written", "others"),
    [(HOOGSTRAAL, ()), (DATE, ()), (CATALOGUE, (CATALOGUE,))],
    ids=["collector", "date", "catalogue-number"],
)
def test_no_cut_character_leaves_wherever_it_is_written(written, others, placement):
    # The catalogue number's letters are cut as its field's literal, which the
    # harness passes with the reading's other non-place literals.
    label = PLACEMENTS[placement].format(written)

    sent = forms(label, others=others)

    assert all(words(form).isdisjoint(words(written)) for form in sent)
    assert sent[0].startswith("Davao Prov.") and sent[1].startswith("Davao Province")


def test_a_marker_cuts_its_whole_clause_even_the_place_in_it():
    label = PLACEMENTS["inside-a-clause"].format(HOOGSTRAAL)

    assert forms(label) == ["Davao Prov.", "Davao Province"]


@pytest.mark.parametrize(
    "line",
    [
        "leg. H. Hoogstraal",
        "H. leg. Hoogstraal",
        "H. Hoogstraal leg.",
        "H. Hoogstraal Coll.",
        "det. H. Hoogstraal",
    ],
)
def test_a_name_a_marker_accompanies_never_leaves_whatever_field_it_was_given(line):
    label = f"Davao Prov.\n{line}"

    assert request(label) == "Davao Prov."
    assert forms("Hoogstraal", label) == []  # Given to a place field.


def test_every_token_of_a_non_place_literal_is_cut():
    # 105526321's collector has no marker; the reading assigns it.
    label = "Mindanao F.G. Werner, P.I."

    assert request(label, others=["F.G. Werner"]) == "Mindanao, P.I."


@pytest.mark.parametrize("token", ["6400'", "IV-25", "1948", "sp.30", "Sp.#1"])
def test_a_token_carrying_a_digit_is_cut(token):
    assert request(f"Mindanao {token}, P.I.") == "Mindanao, P.I."


@pytest.mark.parametrize(
    "month",
    [
        *("Sept.", "sept.", "SEPT", "September", "May"),
        *("Mayo", "MAYO", "septiembre", "Ago.", "dic.", "Enero"),
        *("Setiembre", "set."),  # The variant the RAE accepts (coordinator).
    ],
)
def test_the_month_names_and_abbreviations_are_cut(month):
    # PLAN 4.8 in #191: each month in full and abbreviated, in English and in
    # Spanish, the pilot labels' languages, in any case.
    assert request(f"Mindanao {month}, P.I.") == "Mindanao, P.I."


@pytest.mark.parametrize("date", ["3 VIII 1946", "3 viii 1946", "VIII 1946", "3 VIII"])
def test_a_roman_month_in_the_month_position_is_cut_and_never_written_out(date):
    # The coordinator's ruling of 2026-09-24 (4.8 in #185): a numeral I to XII,
    # in any case, next to a day or a year.
    assert forms(date) == []
    assert forms(f"Mindanao {date}, P.I.") == [
        "Mindanao, P.I.",
        "Mindanao, Philippine Islands",
    ]


def test_the_month_position_reaches_across_separators():
    assert forms("Mindanao, VIII, 1946") == ["Mindanao"]


@pytest.mark.parametrize("text", ["Camp IV", "Mindanao VIII/IX", "Mindanao, P.I."])
def test_a_roman_numeral_outside_a_date_stays(text):
    # "Camp IV" and a lone "VIII/IX" are no date; "P.I." is no numeral.
    assert request(text) == text


@pytest.mark.parametrize(
    ("text", "leaves"),
    [
        ("Mindanao, VIII -46", "Mindanao"),  # "-46" is a year form of the profile.
        ("Mindanao, P.I. 3 Sept. '46", "Mindanao, P.I."),  # 105526321's line.
        ("3 SEPT. '46", ""),
        ("3 SEPT. 1946", ""),
        ("Chimaltenango, 3 Mayo 1946", "Chimaltenango"),  # A Guatemalan line.
    ],
)
def test_the_profiles_year_forms_and_the_pilot_date_line(text, leaves):
    # The steward's review of #185, and PLAN 4.8 in #191.
    assert request(text) == leaves


LABEL_WITH_COLLECTOR = "Davao Prov.\nH. Hoogstraal leg.\nMindanao, P.I."


@pytest.mark.parametrize(
    "text", ["Hoogstraa", "oogstraal", "oogstraal leg", "H. Hoogstr"]
)
def test_a_slice_of_a_cut_token_leaves_nothing_of_it(text):
    # The steward's review of #185 and PLAN 4.8 in #191: a slice of the reading
    # is no source, and a literal that is one loses the token it lies in.
    assert forms(text, LABEL_WITH_COLLECTOR) is None
    assert given(text, LABEL_WITH_COLLECTOR) == []


def test_a_literal_cut_short_keeps_what_its_reading_keeps():
    assert given("Davao Prov.\nH. Hoogstr", LABEL_WITH_COLLECTOR) == [
        "Davao Prov.",
        "Davao Province",
    ]
    werner = "Mindanao F.G. Werner, P.I."
    assert given("Mindanao F.G. Wern", werner, others=["F.G. Werner"]) == ["Mindanao"]
    assert given("Mindanao 3 Se", "Mindanao 3 Sept. '46") == ["Mindanao"]


def test_a_value_is_a_whole_token_slice_of_its_source():
    assert forms("Mt. McKinley", PLACES) == ["Mt. McKinley", "Mount McKinley"]
    assert forms("t. McKinl", PLACES) is None
    assert forms("Davao Pro", PLACES) is None


def test_the_readings_are_context_for_the_cuts_not_a_source():
    reading = "Davao Prov.\nMindanao Hoogstraal leg."

    # "Mindanao" is only in the reading here, so it is no source ...
    assert (
        place_request_forms(
            "Mindanao",
            sources=["Davao Prov."],
            readings=[reading],
            non_place_literals=(),
            knowledge=insects,
        )
        is None
    )
    # ... and the reading's marker clause cuts a place literal taken from it.
    assert given("Mindanao Hoogstraal", reading) == []


def test_a_non_place_literal_copied_short_still_cuts_the_whole_token():
    # The collectors' literal "F.G. Wern" covers part of "Werner".
    reading = "Mindanao F.G. Werner, P.I."

    assert given("Mindanao F.G. Werner", reading, others=["F.G. Wern"]) == ["Mindanao"]


def test_a_full_form_written_on_the_label_is_a_source():
    assert request("Philippine Islands", "Mindanao, Philippine Islands") == (
        "Philippine Islands"
    )


def test_the_readings_non_place_literals_do_not_cut_the_reviewers_place_value():
    # PLAN 4.8 (#180, #191): the reviewer's correction is the authority there,
    # so a reviewer's call passes only the reviewer's own non-place values.
    reading = "Davao Prov.\nMindanao lowland forest"
    habitat = "Mindanao lowland forest"  # A reading's non-place literal.

    as_read = place_request_text(
        "Mindanao",
        sources=[reading],
        readings=[reading],
        non_place_literals=[habitat],
        knowledge=insects,
    )
    as_reviewed = place_request_text(
        "Mindanao",
        sources=["Mindanao"],
        readings=[reading],
        non_place_literals=[],
        knowledge=insects,
    )

    assert (as_read, as_reviewed) == ("", "Mindanao")


def test_a_date_in_the_reviewers_place_value_is_cut():
    # PLAN 4.8 in #191: only the readings' non-place literals spare it.
    value = "Mindanao, 3 Sept. 1946"

    assert (
        place_request_text(
            value,
            sources=[value],
            readings=["Davao Prov.\nMindanao, P.I."],
            non_place_literals=[],
            knowledge=insects,
        )
        == "Mindanao"
    )


# Each source's own answer, as S8's readers receive it.
ANSWERS = {
    "wikidata": '{"search": [{"id": "Q928"}, {"id": "Q15095071"}]}',
    "tgn": '{"result": [{"id": "tgn/1000135", "name": "Mindanao"}]}',
    "nga": (
        '{"features": [{"attributes": {"ufi": -2408935, "adm1": "PH-DVC"}},'
        ' {"attributes": {"ufi": 11769188, "adm1": "GT-04"}}]}'
    ),
}
LABEL_WITH_NUMBERS = "Davao Prov.\nMindanao, P.I.\n3 Sept. 1946\nFMNH INS 0123456"


@pytest.mark.parametrize(
    ("identifier", "source"),
    [
        ("Q928", "wikidata"),
        ("Q15095071", "wikidata"),
        ("1000135", "tgn"),
        ("-2408935", "nga"),
        ("11769188", "nga"),
        ("PH-DVC", "nga"),  # NGA's first-order unit codes (coordinator ruling).
        ("GT-04", "nga"),
    ],
)
def test_a_tier_1_identifier_goes_back_unchanged_to_its_source(identifier, source):
    # PLAN 4.8 in #191, with S8's readers' identifier patterns: the identifier
    # stands in the source's own answer.
    assert (
        place_request_identifier(identifier, source=source, response=ANSWERS[source])
        == identifier
    )


@pytest.mark.parametrize(
    ("identifier", "source", "response"),
    [
        ("Q928", "wikidata", "{}"),  # Not in the source's own answer.
        ("Q92", "wikidata", ANSWERS["wikidata"]),  # Only part of an answer's id.
        ("Q928", "tgn", ANSWERS["wikidata"]),  # Another source's pattern.
        ("Davao", "wikidata", '{"search": [{"id": "Davao"}]}'),  # Label text.
        ("PH-DVC", "nga", '{"features": []}'),  # A code NGA didn't return.
        ("1000135", "geonames", ANSWERS["tgn"]),  # GeoNames is read from dumps.
    ],
)
def test_any_other_identifier_is_refused(identifier, source, response):
    assert (
        place_request_identifier(identifier, source=source, response=response) is None
    )


@pytest.mark.parametrize("number", ["0123456", "1946", "46"])
def test_a_label_number_offered_as_a_tgn_identifier_is_refused(number):
    # PLAN 4.8 in #191: TGN's digit pattern matches any label number, so where
    # an identifier came from is the guard. Only TGN's own answer, as the tool
    # received it, can hold one; the record and the agent's lists never do.
    assert number in LABEL_WITH_NUMBERS
    assert (
        place_request_identifier(number, source="tgn", response=ANSWERS["tgn"]) is None
    )


def test_a_call_without_the_readings_is_refused():
    # The steward's review of #191: the cuts read the readings, so a call that
    # names none is refused; without them "Hoogstraa" would leave.
    assert (
        place_request_forms(
            "Hoogstraa",
            sources=["Hoogstraa"],
            readings=[],
            non_place_literals=["H. Hoogstraal"],
            knowledge=insects,
        )
        is None
    )


def test_a_non_place_literal_is_cut_at_every_occurrence_in_every_text():
    # The steward's review of #191: "Werner" beside "Wernersdorf".
    reading = "Wernersdorf\nF.G. Werner"

    assert given("Werner", reading, others=["F.G. Werner"]) == []
    assert given("Wernersdorf", reading, others=["F.G. Werner"]) == ["Wernersdorf"]
    # A literal "Werner" covers the first six characters of "Wernersdorf".
    assert given("Wernersdorf", reading, others=["Werner"]) == []


def test_werner_where_the_record_reads_wernersdorf_and_leg_werner():
    # PLAN 4.8 in #191: the marker's clause cuts "Werner" wherever the value
    # occurs, and tokens compare whole, so "Wernersdorf" stays.
    record = "Wernersdorf\nleg. Werner"

    assert given("Werner", record) == []  # A tier-1 name, say.
    assert request("Werner", record) == ""  # Drawn from "leg. Werner".
    assert request("Werner", "Wernersdorf") is None  # No whole-token slice.
    assert given("Wernersdorf", record) == ["Wernersdorf"]


def test_a_full_form_that_would_bring_back_a_cut_character_is_not_sent():
    # The steward's review of #191: a non-place literal copied short, "Moun",
    # would come back inside "Mount", so "Mt. Apo" leaves only as written.
    assert given("Mt. Apo", "Mt. Apo\nMountain forest", others=["Moun"]) == ["Mt. Apo"]


def test_a_dropped_clause_keeps_the_line_break_it_held():
    assert request("Davao Prov., leg. Hoogstraal\nMindanao") == "Davao Prov.\nMindanao"


def test_the_reviewers_value_is_a_source_only_in_a_place_field():
    # The steward's clarification of PLAN 4.8 (2026-09-24).
    decided = "Davao Prov.\nMindanao F.G. Wermer"
    raw = "Davao Prov.\nMindanao F.G. Werner"  # Unassigned text on a place line.
    collector = "F.G. Werner"  # The reviewer's correction of "F.G. Wermer".

    def sent(text, sources, *others):
        return place_request_text(
            text,
            sources=sources,
            readings=sources,
            non_place_literals=others,
            knowledge=insects,
        )

    # A value the reviewer puts in a place field is a source ...
    assert sent("Davao del Sur", [decided, "Davao del Sur"]) == "Davao del Sur"
    # ... one in a non-place field is not, and each of its tokens is cut.
    assert sent(collector, [decided], "F.G. Wermer", collector) is None
    assert sent("Mindanao F.G. Werner", [decided, raw], "F.G. Wermer", collector) == (
        "Mindanao"
    )
    # Without it, the corrected spelling would leave: no reading assigns it.
    assert sent("Mindanao F.G. Werner", [decided, raw], "F.G. Wermer") == (
        "Mindanao Werner"
    )


@pytest.mark.parametrize(
    ("text", "record", "leaves"),
    [
        # A name no reading assigns and no marker in its own clause accompanies:
        ("Mindanao Hoogstraal", "Mindanao Hoogstraal", "Mindanao Hoogstraal"),
        # mid-run, before the harness has named the collector,
        (
            "Mindanao F.G. Wermer",
            "Davao Prov., Mindanao F.G. Wermer",
            "Mindanao F.G. Wermer",
        ),
        # and a name whose "leg." sits in a neighbouring clause or line.
        (
            "Mindanao H. Hoogstraal",
            "Mindanao H. Hoogstraal, leg.",
            "Mindanao H. Hoogstraal",
        ),
        (
            "Mindanao H. Hoogstraal",
            "Mindanao H. Hoogstraal\nleg.",
            "Mindanao H. Hoogstraal",
        ),
        # A month in a language the knowledge doesn't list: Tagalog's June.
        ("Mindanao, 3 Hunyo 1946", "Mindanao, 3 Hunyo 1946", "Mindanao, Hunyo"),
        # A lone or ranged month numeral with no day or year beside it.
        ("Mindanao VIII/IX", "Mindanao VIII/IX", "Mindanao VIII/IX"),
        # The cuts can take too much: a place's numeral beside a date number,
        ("Camp IV, 3 VIII 1946", "Camp IV, 3 VIII 1946", "Camp"),
        # a place named with a month word,
        ("Cape May", "Cape May", "Cape"),
        # and a tier-1 name whose numeral stands beside a number.
        ("Region XI (11)", PLACES, "Region"),
    ],
    ids=[
        "unmarked-name",
        "collector-not-yet-named",
        "leg-in-the-next-clause",
        "leg-on-the-next-line",
        "unlisted-language",
        "lone-month-numerals",
        "camp-iv",
        "cape-may",
        "tier-1-name-with-code",
    ],
)
def test_the_stated_limit_is_pinned_case_by_case(text, record, leaves):
    # PLAN 4.8 in #191: tests pin each case its limit names, so a change in
    # what can leave shows.
    sent = place_request_text(
        text,
        sources=[text],
        readings=[record],
        non_place_literals=[],
        knowledge=insects,
    )

    assert sent == leaves


READING_321 = (
    "10-6-78-la\nE. slope Mt. McKinley\nDavao Prov.\nMindanao, P.I.\n"
    "F.G. Werner\n3 sept. '46\nMossy forest 6400'\nsp. 30 ♀"
)
PLACE_LITERALS = ["E. slope Mt. McKinley", "Davao Prov.", "P.I."]
OTHER_LITERALS = ["F.G. Werner", "3 sept. '46", "Mossy forest", "6400'"]


def test_unassigned_locality_text_is_what_no_reading_assigns_on_the_place_lines():
    assert unassigned_text(READING_321, PLACE_LITERALS, OTHER_LITERALS) == ["Mindanao"]
    # A raw reading's literal counts too.
    assert unassigned_text(READING_321, PLACE_LITERALS, ["Mindanao"]) == []


def test_unassigned_text_is_whole_tokens_beside_a_literal_copied_short():
    # A literal that ends inside a token covers the whole token.
    assert unassigned_text("Mindanao F.G. Werner, P.I.", ["P.I."], ["F.G. Wern"]) == [
        "Mindanao"
    ]


def test_lines_holding_no_place_field_give_no_unassigned_text():
    assert unassigned_text(READING_321, ["Davao Prov."], []) == []
