"""PLAN 4.8's place-request filter (HARNESS.md section 7), case by case as the
guarantees 4.8 states: no cut token leaves, an expansion carries only its full
form, and a value not drawn from the sources is refused."""

import pytest

from specimen_digitization.application.harness_knowledge import insects
from specimen_digitization.application.place_text import (
    fold,
    place_request_forms,
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
    )


def forms(text, *sources, others=()):
    """Every form of the value that may leave."""
    return place_request_forms(
        text,
        sources=sources or (text,),
        non_place_literals=others,
        knowledge=insects,
    )


def words(text):
    return set(fold(text).split())


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


def test_a_full_form_never_brings_back_a_cut_token():
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
def test_no_cut_token_leaves_wherever_it_is_written(written, others, placement):
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


@pytest.mark.parametrize("month", ["Sept.", "sept.", "SEPT", "September", "May"])
def test_the_month_names_and_abbreviations_are_cut(month):
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
    ],
)
def test_the_profiles_year_forms_and_the_pilot_date_line(text, leaves):
    # The steward's review of #185.
    assert request(text) == leaves


LABEL_WITH_COLLECTOR = "Davao Prov.\nH. Hoogstraal leg.\nMindanao, P.I."


@pytest.mark.parametrize(
    "text", ["Hoogstraa", "oogstraal", "oogstraal leg", "H. Hoogstr"]
)
def test_a_value_cut_short_inside_a_cut_token_leaves_nothing_of_it(text):
    # The steward's review of #185: the cut follows the source's own token.
    assert forms(text, LABEL_WITH_COLLECTOR) == []


def test_a_value_cut_short_keeps_what_the_source_keeps():
    assert forms("Davao Prov.\nH. Hoogstr", LABEL_WITH_COLLECTOR) == [
        "Davao Prov.",
        "Davao Province",
    ]
    # A non-place literal, and a month, cut short too.
    werner = "Mindanao F.G. Werner, P.I."
    assert request("Mindanao F.G. Wern", werner, others=["F.G. Werner"]) == "Mindanao"
    assert request("Mindanao 3 Se", "Mindanao 3 Sept. '46") == "Mindanao"


def test_a_dropped_clause_keeps_the_line_break_it_held():
    assert request("Davao Prov., leg. Hoogstraal\nMindanao") == "Davao Prov.\nMindanao"


def test_the_reviewers_value_is_a_source_only_in_a_place_field():
    # The steward's clarification of PLAN 4.8 (2026-09-24).
    decided = "Davao Prov.\nMindanao F.G. Wermer"
    raw = "Davao Prov.\nMindanao F.G. Werner"  # Unassigned text on a place line.
    collector = "F.G. Werner"  # The reviewer's correction of "F.G. Wermer".

    def sent(text, sources, *others):
        return place_request_text(
            text, sources=sources, non_place_literals=others, knowledge=insects
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


def test_the_stated_limit_a_name_nothing_marks_can_still_leave():
    # No reading assigns "Hoogstraal" to a field and no marker accompanies it.
    assert request("Mindanao Hoogstraal") == "Mindanao Hoogstraal"


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


def test_lines_holding_no_place_field_give_no_unassigned_text():
    assert unassigned_text(READING_321, ["Davao Prov."], []) == []
