"""The specimen ontology, version 1.0 (docs/execution/units/PLAN.md, WP 1.0;
docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 5)."""

import copy
from pathlib import Path
import re

import pytest
import yaml

from specimen_digitization import ontology
from specimen_digitization.application.domain import MANDATORY
from specimen_digitization.field_research.prompts import FIELD_LABELS

ROOT = Path(__file__).resolve().parents[1]
RENDERED = Path(__file__).with_name("fixtures") / "ontology_v1_rendered.txt"
MOVED_AT = " at 7a09445a2"
PLACE = (
    "a place; the sources decide which level it is (a country, a province or state, a county or municipio, a"
    " city or town, or a place within them), never its name; a town and the second-level unit around it"
    " often share a name, and a mountain, an island, a river or an estate belongs to the precise location"
)


def shipped() -> dict:
    return yaml.safe_load(ontology.PATH.read_text(encoding="utf-8"))


def entry(data: dict, section: str, id_: str) -> dict:
    return next(item for item in data[section] if item.get("id", item.get("key")) == id_)


def test_the_file_lists_the_profiles_20_fields_in_order_with_their_display_names():
    loaded = ontology.ontology()

    assert tuple(field.key for field in loaded.fields) == MANDATORY
    assert {field.key: field.label for field in loaded.fields} == FIELD_LABELS
    assert all(field.darwin_core for field in loaded.fields)


@pytest.mark.parametrize("section,id_,key,value", [
    ("fields", "elevation_from_ft", "key", "elevation"),
    ("notations", "philippine_islands_abbreviation", "fields", ["country", "locality"]),
    ("routing", "place_name", "fields", ["country", "town"]),
])
def test_the_loader_refuses_a_field_not_among_the_profiles_20_keys(section, id_, key, value):
    data = shipped()
    entry(data, section, id_)[key] = value

    with pytest.raises(ontology.OntologyError, match="is not one of the profile's 20 fields"):
        ontology.parse(data)


def test_the_loader_refuses_a_file_that_leaves_out_one_of_the_20_fields():
    data = shipped()
    data["fields"] = [item for item in data["fields"] if item["key"] != "verbatim_dts"]

    with pytest.raises(ontology.OntologyError, match=r"missing \['verbatim_dts'\]"):
        ontology.parse(data)


@pytest.mark.parametrize("source", [None, [], [""]], ids=["no key", "empty list", "empty text"])
def test_the_loader_refuses_a_notation_with_no_source(source):
    data = shipped()
    notation = entry(data, "notations", "collected_by")
    if source is None:
        del notation["source"]
    else:
        notation["source"] = source

    with pytest.raises(ontology.OntologyError, match=r"^notations\[\d+\] has no source$"):
        ontology.parse(data)


@pytest.mark.parametrize("section", ["things", "fields", "routing", "questions"])
def test_every_other_entry_needs_a_source_too(section):
    data = shipped()
    del data[section][0]["source"]

    with pytest.raises(ontology.OntologyError, match="has no source"):
        ontology.parse(data)


@pytest.mark.parametrize("where", ["top", "frame", "things", "fields", "routing", "notations", "questions"])
def test_the_loader_refuses_an_unknown_key(where):
    data = shipped()
    target = data if where == "top" else data[where] if where == "frame" else data[where][0]
    target["relations"] = "not in version 1.0"

    with pytest.raises(ontology.OntologyError, match="unknown key 'relations'"):
        ontology.parse(data)


def test_the_loader_refuses_a_key_written_twice():
    text = ontology.PATH.read_text(encoding="utf-8").replace('version: "1.0"', 'version: "1.0"\nversion: "1.1"')

    with pytest.raises(ontology.OntologyError, match="'version' written twice"):
        ontology.read(text)


def test_the_loader_refuses_a_placeholder_it_cannot_match():
    data = shipped()
    entry(data, "notations", "slide_code")["written"] = ["<Roman month>-<day>-<yy>-<n>"]

    with pytest.raises(ontology.OntologyError, match="unknown placeholder <day>"):
        ontology.parse(data)


def test_the_rendered_text_is_pinned():
    assert ontology.render() == RENDERED.read_text(encoding="utf-8")


# The eleven units of the pilot labels the plan names (WP 1.0's acceptance),
# from e98a924c-L2 and t1-329 (the spec's sections 3 and 4), with the fields
# and readings the file gives each. A place's name is a judgement the file
# leaves to the model (its routing entry); every other unit is matched by its
# notations. The three open units carry none.
FEET = ("feet, the unit of an elevation",)
DATES = ("date_visited_from", "date_visited_to", "date_identified")
PILOT_UNITS = [
    ("CNHM.", None, (), (), ("cnhm",)),
    ("P.I.", None, ("country",), ("Philippine Islands, the Philippines",), ()),
    ("Elev.6400'", None, ("elevation_from_ft", "elevation_to_ft"), FEET, ()),
    ("H. Hoogstraal leg.", None, ("collectors",), ("collected by, marking the collectors",), ()),
    ("Sp.30 \N{FEMALE SIGN}", None, (), (), ("species_number_and_sex",)),
    ("6-Sept-1946", None, DATES, ("the month",), ()),
    ("P-95-81-16", None, (), (), ("p_code",)),
    ("IV-29-68-4", None, (), (
        "a slide or preparation code: a month, a day, a two-digit year and a slide number joined by"
        " hyphens; never a date, nor is any part of it",), ()),
    ("Yepocapa", "place_name", ("country", "province_state", "county", "city", "precise_location"), (PLACE,), ()),
    ("4800ft.", None, ("elevation_from_ft", "elevation_to_ft"), FEET, ()),
    ("Chimaltenago", "place_name", ("country", "province_state", "county", "city", "precise_location"), (PLACE,),
     ()),
]


@pytest.mark.parametrize("text,kind,fields,means,questions", PILOT_UNITS, ids=[unit[0] for unit in PILOT_UNITS])
def test_the_eleven_pilot_units_get_the_fields_and_meaning_the_file_gives_them(text, kind, fields, means, questions):
    advice = ontology.ontology().advice(text, kind)

    assert advice.fields == fields
    assert advice.questions == questions
    assert advice.means == means


def test_the_three_open_units_are_the_files_questions_and_carry_nothing_else():
    loaded = ontology.ontology()

    assert [question.written for question in loaded.questions if question.written] == [
        ("CNHM.",), ("Sp.30 \N{FEMALE SIGN}",), ("P-95-81-16",)]
    assert all(question.answered_in == "WP 2.1" for question in loaded.questions)
    # A question takes the whole unit, notations beside it too.
    assert loaded.advice("H. Hoogstraal; CNHM") == ontology.Advice(questions=("cnhm",))
    assert loaded.advice("P-95-81-16", "place_name") == ontology.Advice(questions=("p_code",))


def test_no_part_of_a_slide_code_is_a_date():
    loaded = ontology.ontology()

    assert loaded.advice("IV-29-68").notations == ("roman_month",)
    assert loaded.advice("IV-29-68-4").notations == ("slide_code",)
    assert loaded.advice("10-6-78-1a").notations == ("slide_code",)
    # Beside a slide code, a collecting date is still a date (t1-329).
    assert loaded.advice("IV-29-68-4 IV-23-48").notations == ("slide_code", "roman_month")


def test_a_place_name_has_no_notation_and_takes_its_fields_from_routing_only():
    loaded = ontology.ontology()

    assert loaded.advice("Yepocapa") == ontology.Advice()
    with pytest.raises(ontology.OntologyError, match="no routing entry 'town'"):
        loaded.advice("Yepocapa", "town")


# insects.py at 7a09445a2: every written form of NOTATIONS (:27-89), each
# PLACE_ALIASES entry (:93-97) and RULES (:99-105) are in the file.
INSECTS_FORMS = {
    "philippine_islands_abbreviation": ["P.I."], "guatemala_abbreviation": ["Guat."], "province": ["Prov."],
    "department": ["Dept."], "mount": ["Mt."], "island": ["Is."], "near": ["nr."],
    "direction": ["E. slope", "W. side"], "collected_by": ["leg.", "coll.", "Coll."], "determined_by": ["det."],
    "metres": ["<n> m"], "feet": ["<n> ft.", "<n>'"], "elevation_heading": ["alt.", "el."],
    "approximate": ["ca.", "c."],
    "month_name": ["Jan.", "Feb.", "Mar.", "Apr.", "Jun.", "Jul.", "Aug.", "Sep.", "Sept.", "Oct.", "Nov.", "Dec."],
    "uncertain": ["?"],
}
RULES = (
    "Copy every literal exactly as the reading has it, character for character; a literal that is not in the"
    " reading is refused. Never complete, correct or translate a literal: readings of a notation are for calling"
    " the tools, never for the literal itself. Work through every reading a notation allows before a field is"
    " left for review, and let the tools and the specimen's other evidence decide between them. A field the"
    " label does not have stays empty."
)


def test_the_insects_knowledge_is_moved_whole():
    loaded = ontology.ontology()
    notations = {notation.id: notation for notation in loaded.notations}

    for id_, forms in INSECTS_FORMS.items():
        assert set(forms) <= set(notations[id_].written), id_
    assert loaded.notation_rule == RULES
    # PLACE_ALIASES: "pi" and "philippine islands" are the Philippines, "guat" Guatemala.
    assert "the Philippines" in loaded.advice("P.I.").means[0]
    assert loaded.advice("Philippine Islands").means == ("the Philippines",)
    assert loaded.advice("Guat.").means == ("Guatemala",)
    # Both orders of a numeric date (G29), a Roman month and a two-digit year.
    assert loaded.advice("4-5-48").means == ("month <a>, day <b>", "day <a>, month <b>")
    assert loaded.advice("IX-14-46").notations == ("roman_month",)
    assert loaded.advice("3 sept. '46").notations == ("month_name", "two_digit_year")


@pytest.mark.parametrize("text,notation", [
    ("Mindanao, P.I.", "philippine_islands_abbreviation"), ("N.S.W.", "new_south_wales_abbreviation"),
    ("Guat.", "guatemala_abbreviation"), ("Mts.", "mts_abbreviation"), ("Davao, Prov.", "province"),
    ("Cook Co.", "county_word"), ("Dept.", "department"), ("E. slope", "direction"), ("W. side", "direction"),
    ("nr.", "near"), ("Is.", "island"), ("leg.", "collected_by"), ("det.", "determined_by"),
    ("ene.", "month_name"), ("janv.", "month_name"), ("Mai", "month_name"), ("Okt.", "month_name"),
    ("agosto", "month_name"), ("4.5.48", "numeric_date"), ("4/5/48", "numeric_date"),
    ("3-5.IX.1946", "date_range"), ("VIII-IX.48", "date_range"), ("'46", "two_digit_year"),
    ("1200 m", "metres"), ("4800 ft.", "feet"), ("alt.", "elevation_heading"), ("ca.", "approximate"),
    ("Aus?", "uncertain"), ("VI-24-68-7", "slide_code"),
])
def test_the_label_notations_of_the_experts_brief_are_in_the_file(text, notation):
    """common.txt's Label notations (:36-44, :47-48)."""
    assert ontology.ontology().advice(text).notations == (notation,)


@pytest.mark.parametrize("text,notations", [
    ("Mt. McKinley", ("mount",)),  # no "c." inside McKinley
    ("Rafael.", ()),  # no "el." at a word's end
    ("Elev.6400", ()),  # reader A: no unit written, so no elevation field
    ("Septum", ()),
    ("Mossy forest", ()),
    ("IX", ()),  # a Roman numeral alone is no date
    ("6400 mostly", ()),
    ("Mts.", ("mts_abbreviation",)),  # not "Mt."
])
def test_a_form_matches_only_at_a_words_edge(text, notations):
    assert ontology.ontology().advice(text).notations == notations


METRES = ("elevation_from_m", "elevation_to_m")
METRES_MEANING = (
    'metres, the unit of an elevation; not metres when a capital "M" stands before a name or in a count of'
    " males and females, which field_research/written.py decides (_a_name, written.py:451-462; _counts_sexes,"
    " written.py:465-494; the unit decision, written.py:523-528), and WP 2.2 aligns this file with it"
)


def test_the_metres_meaning_states_the_capital_m_exception_and_names_written_py_as_its_judge():
    """The file states the exception in words and leaves the decision to
    field_research/written.py; it copies none of written.py's name or
    sex-count logic (WP 2.2 aligns the two, docs/execution/units/PLAN.md:113)."""
    loaded = ontology.ontology()
    metres = next(notation for notation in loaded.notations if notation.id == "metres")

    assert loaded.advice("1200 m").means == (METRES_MEANING,)
    for lines in ("written.py:451-462", "written.py:465-494", "written.py:523-528"):
        assert lines in METRES_MEANING
        assert f"src/specimen_digitization/field_research/{lines}" in metres.source


@pytest.mark.parametrize("text", ["1200 m", "1200 M", "1200 M.", "2 m. Smith", "Alt. 1200 m"])
def test_guard_metres_stay_metres(text):
    """A guard, not a fail-first test (it passes on a93fc6911 too): a number
    with "m" or "M" after it keeps its metres advice."""
    advice = ontology.ontology().advice(text)

    assert "metres" in advice.notations
    assert set(METRES) <= set(advice.fields)


PLACE_FIELDS = ("country", "province_state", "county", "city", "precise_location")


def test_a_place_abbreviation_the_brief_only_expands_is_routed_as_a_place_name():
    """common.txt:27 and :36 give "N.S.W." its expansion and "Mts." none; the
    sources decide the level of either, as for a place's name (county.txt:5)."""
    loaded = ontology.ontology()

    assert loaded.advice("N.S.W.").fields == PLACE_FIELDS
    assert loaded.advice("N.S.W.").means == ("New South Wales: a place abbreviation, looked up by its expansion",)
    assert loaded.advice("Mts.").fields == PLACE_FIELDS
    assert loaded.advice("Mts.").means == (
        "a place abbreviation: when you know what it stands for, look up its expansion",)
    entries = {notation.id: notation for notation in loaded.notations}
    # No expansion or level the briefs do not give.
    assert "mountain" not in " ".join((*entries["mts_abbreviation"].readings, entries["mts_abbreviation"].note))
    assert "state" not in " ".join((*entries["new_south_wales_abbreviation"].readings,
                                    entries["new_south_wales_abbreviation"].note))


def test_the_island_notation_keeps_its_fields_and_carries_a_question_for_the_owners_reading():
    loaded = ontology.ontology()
    question = next(question for question in loaded.questions if question.id == "island_fields")

    assert (question.notation, question.written, question.answered_in) == ("island", (), "WP 2.1")
    assert loaded.advice("Is.") == ontology.Advice(
        fields=("precise_location", "county", "province_state"), means=("island or islands",),
        notations=("island",))
    assert '- "Is.": Which fields can "Is." (island or islands) belong to?' in loaded.render()


@pytest.mark.parametrize("change,message", [
    ({"notation": "island"}, "needs written forms or a notation, not both"),
    ({"written": None}, "needs written forms or a notation, not both"),
    ({"written": None, "notation": "islands"}, "no notation 'islands'"),
])
def test_a_question_is_about_units_or_about_one_notation_of_the_file(change, message):
    data = shipped()
    question = entry(data, "questions", "cnhm")
    for key, value in change.items():
        if value is None:
            del question[key]
        else:
            question[key] = value

    with pytest.raises(ontology.OntologyError, match=message):
        ontology.parse(data)


def _cited(source: str) -> tuple[Path, str]:
    path, _, lines = source.removesuffix(MOVED_AT).rpartition(":")
    return ROOT / path, lines


def test_every_source_names_a_file_and_lines_it_has():
    loaded = ontology.ontology()
    sources = [*loaded.frame["source"]]
    for section in (loaded.things, loaded.fields, loaded.routing, loaded.notations, loaded.questions):
        sources += [source for item in section for source in item.source]
    sources += shipped()["notation_rule"]["source"]

    for source in sources:
        if source.startswith("https://"):
            continue
        path, lines = _cited(source)
        assert re.fullmatch(r"\d+(-\d+)?", lines), source
        first, last = (int(line) for line in (lines.split("-")[0], lines.split("-")[-1]))
        assert 1 <= first <= last, source
        if source.endswith(MOVED_AT):
            # The Insects knowledge module this change deletes, at main 7a09445a2
            # (120 lines there).
            assert source.startswith("insects.py:") and last <= 120, source
            continue
        assert path.is_file(), source
        assert last <= len(path.read_text(encoding="utf-8").splitlines()), source


def test_the_shipped_file_parses_unchanged_through_a_copy():
    data = shipped()

    assert ontology.parse(copy.deepcopy(data)) == ontology.ontology()
