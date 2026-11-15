"""The specimen ontology, version 2.0 (docs/execution/units/PLAN.md, WP 1.0, WP 2.1 and WP 2.2;
docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md sections 4 and 5)."""

import copy
from decimal import Decimal
from functools import cache
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest
import yaml

from specimen_digitization import ontology
from specimen_digitization.application.domain import MANDATORY
from specimen_digitization.field_research.prompts import FIELD_LABELS

ROOT = Path(__file__).resolve().parents[1]
RENDERED = Path(__file__).with_name("fixtures") / "ontology_v2_rendered.txt"
# The first pass's text (WP 1.2): ontology.render(brief=True).
RENDERED_BRIEF = Path(__file__).with_name("fixtures") / "ontology_v2_rendered_brief.txt"
# The rules' own text (WP 2.1): ontology.render_rules().
RENDERED_RULES = Path(__file__).with_name("fixtures") / "ontology_v2_rules_rendered.txt"
# The rules' instructions each model receives (WP 2.2): ontology.render_instructions, by model, and
# by field for the experts, as JSON.
RENDERED_INSTRUCTIONS = Path(__file__).with_name("fixtures") / "ontology_v2_instructions_rendered.json"
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


@pytest.mark.parametrize("section", ["things", "fields", "routing", "questions", "rules", "not_rules"])
def test_every_other_entry_needs_a_source_too(section):
    data = shipped()
    del data[section][0]["source"]

    with pytest.raises(ontology.OntologyError, match="has no source"):
        ontology.parse(data)


@pytest.mark.parametrize("where", ["top", "frame", "things", "fields", "routing", "notations", "questions", "rules",
                                   "not_rules", "highest_points", "highest_points.rows"])
def test_the_loader_refuses_an_unknown_key(where):
    data = shipped()
    target = (data if where == "top" else data[where] if where in ("frame", "highest_points")
              else data["highest_points"]["rows"][0] if where == "highest_points.rows" else data[where][0])
    target["relations"] = "not in version 2.0"

    with pytest.raises(ontology.OntologyError, match="unknown key 'relations'"):
        ontology.parse(data)


def test_the_loader_refuses_a_key_written_twice():
    text = ontology.PATH.read_text(encoding="utf-8").replace('version: "2.0"', 'version: "2.0"\nversion: "2.1"')

    with pytest.raises(ontology.OntologyError, match="'version' written twice"):
        ontology.read(text)


def test_the_loader_refuses_a_placeholder_it_cannot_match():
    data = shipped()
    entry(data, "notations", "slide_code")["written"] = ["<Roman month>-<day>-<yy>-<n>"]

    with pytest.raises(ontology.OntologyError, match="unknown placeholder <day>"):
        ontology.parse(data)


def test_the_rendered_text_is_pinned():
    assert ontology.render() == RENDERED.read_text(encoding="utf-8")


def test_the_first_pass_text_is_pinned():
    assert ontology.render(brief=True) == RENDERED_BRIEF.read_text(encoding="utf-8")


# Text naming a code or text file, file lines, a work package, a gate, the PRD or a brief.
NOT_FOR_A_MODEL = re.compile(r"\.py\b|\b[\w/]+\.(?:txt|md|yaml)\b|:\d+(?:-\d+)?\b|\bWP \d|\bG\d{1,3}\b|\bPRD\b|\bbrief'?s?\b")


@pytest.mark.parametrize("brief", [False, True], ids=["whole", "first pass"])
def test_the_rendered_text_names_no_code_line_work_package_or_gate(brief):
    assert NOT_FOR_A_MODEL.findall(ontology.render(brief=brief)) == []


def test_the_first_pass_text_keeps_what_cuts_and_reads_a_unit_and_leaves_out_what_writes_a_value():
    """render(brief=True) holds each field's key, display name and Darwin Core term, each
    routing entry's fields, each notation's forms and each question, and none of the things'
    examples, the fields' `holds` or the notation rule."""
    loaded = ontology.ontology()
    brief = ontology.render(brief=True)
    for entry in loaded.fields:
        assert f"- {entry.key} ({entry.label}), {entry.darwin_core}\n" in brief
        assert entry.holds not in brief
    for route in loaded.routing:
        assert ", ".join(route.fields) in brief
    for notation in loaded.notations:
        assert ", ".join(f'"{form}"' for form in notation.written) in brief
    for question in loaded.questions:
        assert question.question in brief
    for thing in loaded.things:
        assert thing.examples not in brief
    assert loaded.notation_rule not in brief and loaded.notation_rule in ontology.render()
    assert len(brief) < len(ontology.render())


# The eleven units of the pilot labels the plan names (WP 1.0's acceptance),
# from e98a924c-L2 and t1-329 (the spec's sections 3 and 4), with the fields
# and readings the file gives each. A place's name is a judgement the file
# leaves to the model (its routing entry); every other unit is matched by its
# notations. Version 2.0 resolved "CNHM." and "Sp.30 \N{FEMALE SIGN}" from sources (WP 2.1);
# "P-95-81-16" stays open and carries none.
FEET = ("feet, the unit of an elevation",)
DATES = ("date_visited_from", "date_visited_to", "date_identified")
CNHM = ("Chicago Natural History Museum, the Field Museum's name from 1943 to 1966: the institution, never a"
        " collector, and no field of its own")
MORPHOCODE = ("a morphocode, a species number: after a genus, a genus-level identification; with no genus on any"
              " label, it names no scientific taxon")
FEMALE = "female: the specimen's sex, which no field of the profile holds"
MALE = "male: the specimen's sex, which no field of the profile holds"
PILOT_UNITS = [
    ("CNHM.", None, (), (CNHM,), ()),
    ("P.I.", None, ("country",), ("Philippine Islands, the Philippines",), ()),
    ("Elev.6400'", None, ("elevation_from_ft", "elevation_to_ft"), FEET, ()),
    ("H. Hoogstraal leg.", None, ("collectors",), ("collected by, marking the collectors",), ()),
    ("Sp.30 \N{FEMALE SIGN}", None, ("taxon",), (MORPHOCODE, FEMALE), ()),
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


# The owner's reading of 2026-11-13, the spec's dated line (section 5): a printed "LEWIS COLLECTION" heading
# is the Collection Code. The units path only; the shared briefs stay main's.
LEWIS = "the printed heading of the Lewis Collection's label templates; it is the Collection Code, copied as written"


@pytest.mark.parametrize("text", ["LEWIS COLLECTION", "LEWIS\nCOLLECTION"], ids=["one line", "two lines"])
def test_a_unit_whose_text_is_the_printed_lewis_collection_heading_gets_the_collection_code(text):
    """As the eleven pilot units do: the field and the reading come from the file."""
    assert ontology.ontology().advice(text) == ontology.Advice(
        fields=("collection_code",), means=(LEWIS,), notations=("lewis_collection_heading",))


@pytest.mark.parametrize("text", ["Siphonaptera of Utah", "LEWIS", "COLLECTION", "LEWIS COLLECTIONS"])
def test_no_other_printed_heading_is_ruled(text):
    """A guard, not a fail-first test (it passes on main too): these four texts, one of them another
    printed heading, get no field and no reading; the ruling names one heading."""
    assert ontology.ontology().advice(text) == ontology.Advice()


def test_the_lewis_notation_names_the_specs_dated_line_as_its_source_and_the_loader_needs_it():
    loaded = ontology.ontology()
    notation = next(item for item in loaded.notations if item.id == "lewis_collection_heading")

    assert (notation.written, notation.readings, notation.fields) == (("LEWIS COLLECTION",), (LEWIS,), ("collection_code",))
    assert len(notation.source) == 1
    path, lines = _cited(notation.source[0])
    assert path == ROOT / "docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md"
    assert re.fullmatch(r"\d+", lines)
    line = path.read_text(encoding="utf-8").splitlines()[int(lines) - 1]
    assert line.startswith("2026-11-13, the owner")
    assert "Asked 'Should a printed \"LEWIS COLLECTION\" heading be stored as the Collection Code?'," in line
    assert 'the owner answered with the button "Yes, store it".' in line

    data = shipped()
    del entry(data, "notations", "lewis_collection_heading")["source"]
    with pytest.raises(ontology.OntologyError, match=r"^notations\[\d+\] has no source$"):
        ontology.parse(data)


def test_the_one_open_unit_is_the_files_only_question_and_carries_nothing_else():
    """WP 2.1 resolved "CNHM.", "Sp.30 \N{FEMALE SIGN}" and island_fields from sources; no source settles
    "P-95-81-16", which stays as it was, not put to the owner."""
    loaded = ontology.ontology()

    assert [(question.id, question.written, question.notation) for question in loaded.questions] == [
        ("p_code", ("P-95-81-16",), "")]
    assert loaded.questions[0].status.startswith("No source settles it (WP 2.1, 2026-11-14)")
    assert "owner's reading" not in ontology.render() and "owner's reading" not in ontology.render(brief=True)
    # A question takes the whole unit, notations beside it too.
    assert loaded.advice("P-95-81-16", "place_name") == ontology.Advice(questions=("p_code",))
    assert loaded.advice("H. Hoogstraal; CNHM") == ontology.Advice(means=(CNHM,), notations=("cnhm",))


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
    " males and females"
)


def test_the_metres_meaning_states_the_capital_m_exception_and_its_sources_name_written_py():
    """The metres meaning states the capital "M" exception in words and matches no pattern of
    NOT_FOR_A_MODEL; the entry's sources cite written.py's three line ranges."""
    loaded = ontology.ontology()
    metres = next(notation for notation in loaded.notations if notation.id == "metres")

    assert loaded.advice("1200 m").means == (METRES_MEANING,)
    assert NOT_FOR_A_MODEL.findall(METRES_MEANING) == []
    for lines in ("written.py:451-462", "written.py:465-494", "written.py:523-528"):
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


def test_an_island_belongs_to_the_precise_location_only():
    """island_fields, resolved in WP 2.1: an island is not a province (province_state.txt:7) nor a city
    (city.txt:6), and no v1 field holds an island's level (PRD.md:785-786)."""
    loaded = ontology.ontology()
    island = next(notation for notation in loaded.notations if notation.id == "island")

    assert loaded.advice("Is.") == ontology.Advice(
        fields=("precise_location",), means=("island or islands",), notations=("island",))
    for source in ("src/specimen_digitization/field_research/prompts/province_state.txt:7",
                   "src/specimen_digitization/field_research/prompts/city.txt:6",
                   "docs/product-requirements/PRD.md:785-786"):
        assert source in island.source
    assert "island_fields" not in {question.id for question in loaded.questions}
    assert "Which fields can" not in loaded.render()


@pytest.mark.parametrize("change,message", [
    ({"notation": "island"}, "needs written forms or a notation, not both"),
    ({"written": None}, "needs written forms or a notation, not both"),
    ({"written": None, "notation": "islands"}, "no notation 'islands'"),
])
def test_a_question_is_about_units_or_about_one_notation_of_the_file(change, message):
    data = shipped()
    question = entry(data, "questions", "p_code")
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
    for section in (loaded.things, loaded.fields, loaded.routing, loaded.notations, loaded.questions, loaded.rules,
                    loaded.not_rules):
        sources += [source for item in section for source in item.source]
    sources += shipped()["notation_rule"]["source"]
    sources += [source for table in shipped()["tables"].values() for source in table["source"]]

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


# ---- version 2.0: the rules (WP 2.1) ----------------------------------------------------------------

RULE_PARTS = ("id", "statement", "check", "darwin_core", "source", "instruction", "fields")


@pytest.mark.parametrize("part", RULE_PARTS)
def test_the_loader_refuses_a_rule_missing_any_part(part):
    data = shipped()
    del entry(data, "rules", "elevation_unit_feet")[part]

    message = r"^rules\[\d+\] has no source$" if part == "source" else rf"^rules\[\d+\]: missing key '{part}'$"
    with pytest.raises(ontology.OntologyError, match=message):
        ontology.parse(data)


@pytest.mark.parametrize("part", RULE_PARTS[:2] + RULE_PARTS[3:6])
def test_the_loader_refuses_a_rule_whose_part_is_empty(part):
    data = shipped()
    entry(data, "rules", "date_order")[part] = [] if part == "source" else " "

    with pytest.raises(ontology.OntologyError, match="has no source" if part == "source" else "non-empty string"):
        ontology.parse(data)


@pytest.mark.parametrize("change,message", [
    ({"check": "yes"}, r"check must be one of code, model, not yet, not 'yes'"),
    ({"check": "not yet"}, "names `when` if and only if it is not yet checked"),
    ({"when": "WP 2.3"}, "names `when` if and only if it is not yet checked"),
    ({"derives": "yes"}, r"rules\[\d+\]\.derives must be true or false"),
])
def test_a_rule_is_checked_by_code_by_a_model_or_not_yet_with_its_work_package(change, message):
    data = shipped()
    # WP 2.3b flipped the last rule `not yet`, elevation_unit_feet, to `code`.
    rule = entry(data, "rules", "elevation_unit_feet")
    for key, value in change.items():
        if value is None:
            del rule[key]
        else:
            rule[key] = value

    with pytest.raises(ontology.OntologyError, match=message):
        ontology.parse(data)


@pytest.mark.parametrize("part", ("id", "statement", "darwin_core", "source"))
def test_the_loader_refuses_a_statement_that_is_not_a_rule_missing_any_part(part):
    data = shipped()
    del entry(data, "not_rules", "taxon_regional_occurrence")[part]

    with pytest.raises(ontology.OntologyError, match="has no source" if part == "source" else f"missing key '{part}'"):
        ontology.parse(data)


def test_a_rule_id_is_written_once_across_rules_and_not_rules():
    data = shipped()
    entry(data, "not_rules", "taxon_regional_occurrence")["id"] = "date_order"

    with pytest.raises(ontology.OntologyError, match="an id is written twice"):
        ontology.parse(data)


def test_the_rules_rendered_text_is_pinned():
    assert ontology.render_rules() == RENDERED_RULES.read_text(encoding="utf-8")


def test_the_rules_text_names_no_code_line_work_package_or_gate_and_no_model_text_carries_it():
    """The rules render through their own function, which holds nothing NOT_FOR_A_MODEL refuses, and
    render() (both forms) holds no rule and no table row: the models carry each rule's instruction
    (render_instructions), never its statement."""
    rules = ontology.render_rules()
    assert NOT_FOR_A_MODEL.findall(rules) == []
    loaded = ontology.ontology()
    for text in (ontology.render(), ontology.render(brief=True)):
        for rule in (*loaded.rules, *loaded.not_rules):
            assert rule.statement not in text and rule.id not in text
        assert "Mount Apo" not in text and "highest point" not in text


# The spec's section 4 and 5 relations and checks (WP 2.1's row), each a rule of the file, with how it is
# checked today. WP 2.3 builds the seven `not yet` rules WP 2.1 named: its first part, 2.3a, flipped six to
# `code`, and its second part, 2.3b, flipped elevation_unit_feet to `code` and, with the check stage's mark of a
# precise location cut short, precise_location_extent from `model` (WP 2.2).
RULE_CHECKS = {
    "one_collecting_event": "code", "place_within_settled_places": "code", "place_chain": "code",
    "date_order": "code", "day_month_order": "code", "code_is_no_date": "code", "label_type_routing": "code",
    "elevation_unit_feet": "code", "elevation_needs_a_unit": "code", "elevation_unit_decides_field": "code",
    "place_parents_derived": "code", "elevation_conversion": "code", "end_date_from_one_date": "code",
    "precise_location_extent": "code",
}


def test_the_file_holds_the_specs_rules_each_checked_as_stated():
    loaded = ontology.ontology()

    assert {rule.id: rule.check for rule in loaded.rules} == RULE_CHECKS
    assert {rule.id: rule.when for rule in loaded.rules if rule.check == "not yet"} == {}
    assert {rule.id for rule in loaded.rules if rule.derives} == {
        "place_parents_derived", "elevation_conversion", "end_date_from_one_date"}
    assert [entry.id for entry in loaded.not_rules] == ["taxon_regional_occurrence"]
    assert "docs/product-requirements/PRD.md:1207" in loaded.not_rules[0].source


# Every rule checked by code today, against the tests that pin it (node ids under the repository's root, as
# pytest collects them; a parametrized case by its own id), one to one: no test pins two rules. Each `code`
# statement is an invariant today's code guarantees; a mutant that breaks it fails one of its tests. WP 2.3
# adds its rules here when it flips them to `code` (2.3a: six of them, below the first five; 2.3b: the last
# two, and the tests of the derived fields that wait for their source).
STAGE = "tests/field_research/test_check_stage.py"
ELEV = "tests/field_research/test_elevations_and_extent.py"
EXTENT = "tests/field_research/test_precise_location_extent.py"
CODE_RULE_TESTS = {
    "one_collecting_event": (
        "tests/field_research/test_experts.py::test_a_field_on_two_labels_settles_only_when_both_settle_to_one_value",
        "tests/field_research/test_experts.py"
        "::test_two_labels_writing_one_field_differently_settle_only_through_a_source_confirming_both",
    ),
    "day_month_order": (
        "tests/test_date_forms.py::test_a_form_that_leaves_a_choice_names_it_and_settles_nothing[4-5-48]",
    ),
    "elevation_needs_a_unit": (
        "tests/field_research/test_agreement.py::test_a_number_with_no_unit_never_settles_an_elevation",),
    "elevation_unit_decides_field": (
        "tests/field_research/test_agreement.py::test_an_elevation_never_settles_a_field_of_the_other_unit",),
    "elevation_conversion": (
        "tests/field_research/test_step.py::test_derived_values_fill_what_the_label_leaves_out",
        "tests/field_research/test_step.py::test_no_elevation_is_derived_from_a_unit_the_readings_disagree_on",
        "tests/test_derivations.py::test_a_single_metre_value_is_both_ends_and_fills_the_feet_fields",
        "tests/test_derivations.py::test_a_feet_value_converts_to_metres_rounded_to_the_hundredth",
        "tests/test_derivations.py::test_stated_elevations_are_never_replaced",
        f"{ELEV}::test_an_elevation_s_partners_wait_while_it_is_held",
        f"{ELEV}::test_6400_with_no_mark_leaves_its_partners_waiting",
        f"{ELEV}::test_a_field_settled_absent_beside_a_settled_source_does_not_wait",
        f"{ELEV}::test_derivation_writes_what_it_wrote_on_main",
        f"{ELEV}::test_a_person_who_settles_the_foot_field_gets_its_partners_derived",
        f"{ELEV}::test_a_failed_source_with_no_elevation_written_keeps_main_s_result",
    ),
    "end_date_from_one_date": (
        "tests/field_research/test_date_split_lines.py::test_a_range_s_start_is_not_copied_to_its_end",
        "tests/field_research/test_date_split_lines.py::test_one_collecting_date_is_its_own_end_at_its_precision",
        f"{ELEV}::test_105526325_s_held_date_leaves_date_visited_to_waiting",
        f"{ELEV}::test_a_waiting_end_date_is_derived_once_its_start_settles",
        f"{ELEV}::test_a_waiting_field_adds_no_review_reason_of_its_own",
        f"{ELEV}::test_a_person_who_settles_the_start_gets_the_end_derived_on_approval",
        f"{ELEV}::test_a_waiting_field_whose_source_settles_without_a_derivation_takes_today_s_treatment",
    ),
    # WP 2.3a's check stage (field_research/ontology_checks.py), and the date check's code veto.
    "place_within_settled_places": (
        "tests/field_research/test_experts.py::test_a_place_fits_the_other_place_fields_its_reading_writes",
        f"{STAGE}::test_a_county_in_a_state_named_as_the_settled_country_is_marked_by_the_check_stage",
        f"{STAGE}::test_a_city_whose_province_is_written_and_unsettled_is_refused_as_today",
        f"{STAGE}::test_a_retry_checks_a_place_an_earlier_attempt_settled_on_its_stored_record",
        f"{STAGE}::test_a_country_on_one_label_and_an_nga_town_on_another_is_not_marked",
        f"{STAGE}::test_a_persons_value_with_no_layer_is_not_checked",
        f"{STAGE}::test_a_country_and_a_town_on_two_labels_are_compared_by_their_iso_codes",
    ),
    "place_chain": (
        f"{STAGE}::test_a_city_outside_the_settled_county_on_tgn_s_preferred_chain_alone_is_not_marked",
        f"{STAGE}::test_a_city_inside_its_settled_county_is_not_marked",
        "tests/field_research/test_agreement.py::test_105526329s_county_settles_on_the_municipio_beside_its_town",
        f"{STAGE}::test_a_city_in_another_county_of_the_settled_county_s_name_is_not_marked",
        f"{STAGE}::test_aurora_in_adams_county_is_not_marked",
        f"{STAGE}::test_105526329_without_its_department_line_is_not_marked",
        f"{STAGE}::test_a_retry_abstains_on_a_place_whose_earlier_record_cannot_be_read_again",
        f"{STAGE}::test_a_plain_retry_keeps_the_marks_of_fields_it_does_not_research",
        f"{STAGE}::test_a_reassessment_that_researches_a_marked_field_again_drops_its_stale_mark",
        f"{STAGE}::test_a_tgn_chain_not_known_to_reach_its_nation_abstains",
        f"{STAGE}::test_a_tgn_record_the_stage_holds_is_a_nation_only_by_tgn_s_nation_type",
        f"{STAGE}::test_a_stored_row_is_rebuilt_only_from_its_own_responses",
        f"{STAGE}::test_a_stored_row_is_read_again_only_from_a_lookup_that_gives_its_excerpt",
        f"{STAGE}::test_fits_decides_by_ids_and_codes_and_abstains_otherwise",
    ),
    "place_parents_derived": (
        f"{STAGE}::test_a_derived_province_on_tgn_s_preferred_chain_alone_is_not_marked",
        f"{STAGE}::test_a_province_derived_from_a_county_is_its_province_level_parent_never_the_country",
        f"{STAGE}::test_the_lake_gary_derived_province_is_not_marked",
        f"{STAGE}::test_a_derived_country_that_a_place_below_it_lies_outside_is_marked",
        f"{STAGE}::test_a_persons_derived_place_is_never_marked_the_place_below_it_is",
        f"{ELEV}::test_derive_reads_its_rules_from_the_file_and_they_are_main_s",
    ),
    "date_order": (
        f"{STAGE}::test_a_determination_on_the_collecting_day_is_allowed",
        f"{STAGE}::test_a_determination_before_the_collecting_date_is_marked_with_both_dates",
        f"{STAGE}::test_a_year_agrees_with_a_day_in_that_year",
        f"{STAGE}::test_dates_compare_on_the_parts_both_have",
        f"{STAGE}::test_a_retry_adds_the_date_sentence_once",
    ),
    "code_is_no_date": (
        f"{STAGE}::test_a_date_one_reader_writes_inside_a_slide_code_is_no_date_on_the_units_path",
        f"{STAGE}::test_a_literal_is_in_a_code_only_inside_a_match_of_the_ontology_s_slide_code",
        f"{STAGE}::test_a_date_punctuation_separates_from_a_slide_code_is_a_date_on_both_paths",
        f"{STAGE}::test_the_code_veto_takes_each_occurrence_of_the_literal",
        f"{STAGE}::test_the_date_experts_check_gives_no_date_inside_a_code_and_its_value_is_refused_on_the_units_path",
        "tests/field_research/test_checks.py::test_a_date_inside_a_code_in_any_reading_is_no_date",
    ),
    "label_type_routing": (
        f"{STAGE}::test_a_determination_label_writing_a_locality_reaches_the_locality_expert",
    ),
    # WP 2.3b: the elevation unit rule (ontology_checks.infer_feet) and the extent of Precise Location
    # (agreement.elevation_kept and literal_refusal, step._taken, ontology_checks._extent_marks; WP 2.2's
    # town-only locality).
    "elevation_unit_feet": (
        f"{ELEV}::test_6400_with_b_s_foot_mark_and_the_philippines_cleared_settles_6400_ft_cleared",
        f"{ELEV}::test_the_same_with_the_philippines_marked_stays_unresolved",
        f"{ELEV}::test_a_country_not_settled_from_the_label_or_with_no_cleared_label_is_not_cleared",
        f"{ELEV}::test_6400_with_no_foot_mark_stays_unresolved",
        f"{ELEV}::test_conditions_b_and_c_bound_the_number",
        f"{ELEV}::test_a_reader_who_writes_metres_keeps_today_s_unit_differs_path",
        f"{ELEV}::test_a_country_s_row_is_its_wikidata_item_s_else_its_name_s",
        f"{ELEV}::test_a_number_on_two_units_or_another_held_elevation_is_not_inferred",
        f"{ELEV}::test_condition_a_is_one_number_a_reader_marks_and_another_leaves_bare",
        f"{ELEV}::test_condition_a_takes_a_unit_with_no_heading_only_where_the_held_field_s_rows_place_the_number",
        f"{ELEV}::test_g51_s_inputs_stay_unresolved",
        f"{ELEV}::test_condition_a_takes_a_unit_the_first_pass_routes_to_an_elevation_and_options_naming_no_other_number",
    ),
    "precise_location_extent": (
        f"{EXTENT}::test_a_town_only_locality_is_not_cleared_as_not_on_the_label_on_the_units_path",
        f"{EXTENT}::test_a_precise_location_that_is_the_towns_text_is_not_cleared_on_the_units_path",
        f"{EXTENT}::test_a_municipio_line_beside_the_settled_town_stands_on_the_units_path",
        f"{EXTENT}::test_a_units_path_run_cleared_as_not_on_the_label_by_older_code_goes_to_a_person_on_refinalize",
        f"{EXTENT}::test_a_precise_location_holding_an_elevation_is_refused_when_no_elevation_settled",
        f"{EXTENT}::test_the_review_rounds_elevation_inputs_are_refused_as_a_precise_location_on_both_paths",
        f"{EXTENT}::test_105526329s_whole_locality_with_its_settled_elevation_settles_on_the_units_path",
        f"{ELEV}::test_yepocapa_s_elevation_is_kept_only_as_the_literal_its_elevation_field_settled",
        f"{ELEV}::test_the_review_rounds_elevation_inputs_stay_refused_whatever_elevation_settled",
        f"{ELEV}::test_elevation_kept_keeps_one_elevation_at_its_line_s_end_beside_a_locality",
        f"{ELEV}::test_an_organiser_candidate_holding_an_elevation_follows_the_same_rule",
        f"{ELEV}::test_an_organiser_candidate_holding_a_date_settles_on_both_paths",
        f"{ELEV}::test_105526329_s_whole_locality_settles_beside_its_settled_elevation_on_the_units_path",
        f"{ELEV}::test_105526329_s_whole_locality_is_refused_beside_another_elevation_or_none",
        f"{ELEV}::test_the_expert_s_own_check_lets_a_kept_elevation_pass_on_the_units_path_only",
        f"{ELEV}::test_a_settled_precise_location_and_an_elevation_share_its_text_on_the_units_path",
        f"{ELEV}::test_a_precise_location_cut_short_before_a_line_holding_a_settled_higher_place_is_marked",
        f"{ELEV}::test_the_cut_short_check_abstains_unless_certain",
        f"{ELEV}::test_a_person_s_precise_location_is_never_marked_cut_short",
        f"{ELEV}::test_the_next_line_marks_only_as_the_locality_going_on",
        f"{ELEV}::test_an_elevation_another_field_s_text_takes_is_no_elevation_the_locality_may_keep",
        f"{ELEV}::test_a_label_whose_only_locality_text_is_its_country_settles_it_as_the_precise_location_on_the_"
        "units_path",
    ),
}


@cache
def _collected(paths: tuple[str, ...]) -> frozenset[str]:
    """The node ids pytest collects from these test files (`pytest --collect-only -q`, run once in a
    subprocess): a parametrized case exists only as its function's own collected id."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", f"--rootdir={ROOT}", *paths],
        cwd=ROOT, capture_output=True, text=True, timeout=600)
    nodes = frozenset(line.strip() for line in result.stdout.splitlines() if "::" in line)
    assert result.returncode == 0 and nodes, result.stdout[-2000:] + result.stderr[-2000:]
    return nodes


def _mapped_files() -> tuple[str, ...]:
    return tuple(sorted({node.partition("::")[0] for tests in CODE_RULE_TESTS.values() for node in tests}))


def _map_problems(code: set[str], tests: dict[str, tuple[str, ...]], collected: frozenset[str]) -> list[str]:
    """What breaks the one-to-one map: a rule checked by code with no test, a listed rule not checked by code,
    a test listed twice, a listed node id pytest does not collect. A node id with a case ("[5-5-48]") is
    that collected case; one without names a function every case of which is collected under it."""
    problems = [f"{rule}: checked by code, no test" for rule in sorted(code - {k for k, v in tests.items() if v})]
    problems += [f"{rule}: not checked by code" for rule in sorted(set(tests) - code)]
    nodes = [node for listed in tests.values() for node in listed]
    problems += [f"{node}: listed twice" for node in sorted({node for node in nodes if nodes.count(node) > 1})]
    for node in nodes:
        found = node in collected or ("[" not in node and any(item.startswith(node + "[") for item in collected))
        if not found:
            problems.append(f"{node}: no such test")
    return problems


def test_every_rule_checked_by_code_names_its_tests_one_to_one_and_each_test_exists():
    code = {rule.id for rule in ontology.ontology().rules if rule.check == "code"}

    assert _map_problems(code, CODE_RULE_TESTS, _collected(_mapped_files())) == []


def test_the_rule_to_test_map_fails_on_a_code_rule_with_no_test_or_a_test_that_does_not_exist():
    """The map's failures, shown on copies: a rule flipped to `code` with no test; a renamed function; a
    case of another function's parameters ("4-5-48" is test_date_forms.py's AMBIGUOUS, not SINGLE_DATES);
    and a case whose id is renamed away, though its literal stays in the file (Codex's round-2 probes)."""
    collected = _collected(_mapped_files())
    code = {rule.id for rule in ontology.ontology().rules if rule.check == "code"}
    untested = {key: tests for key, tests in CODE_RULE_TESTS.items() if key != "elevation_unit_feet"}
    assert _map_problems(code, untested, collected) == ["elevation_unit_feet: checked by code, no test"]

    renamed = {**CODE_RULE_TESTS, "end_date_from_one_date": (CODE_RULE_TESTS["end_date_from_one_date"][0] + "_x",)}
    assert _map_problems(code, renamed, collected) == [renamed["end_date_from_one_date"][0] + ": no such test"]

    foreign = "tests/test_date_forms.py::test_a_form_reads_as_its_start_end_and_precision[4-5-48]"
    assert "tests/test_date_forms.py::test_a_form_that_leaves_a_choice_names_it_and_settles_nothing[4-5-48]" in collected
    moved = {**CODE_RULE_TESTS, "day_month_order": (foreign,)}
    assert _map_problems(code, moved, collected) == [foreign + ": no such test"]

    ambiguous = "tests/test_date_forms.py::test_a_form_that_leaves_a_choice_names_it_and_settles_nothing["
    away = frozenset(item.replace(ambiguous, ambiguous + "renamed-") for item in collected)
    assert _map_problems(code, CODE_RULE_TESTS, away) == [ambiguous + "4-5-48]: no such test"]


# ---- version 2.0: the meanings resolved from sources (WP 2.1) -------------------------------------------

def test_the_resolved_meanings_name_their_sources_and_carry_their_fields():
    loaded = ontology.ontology()
    notations = {notation.id: notation for notation in loaded.notations}

    assert notations["cnhm"].fields == () and {
        "tests/fixtures/field_model_pilot_rows.json:134", "https://en.wikipedia.org/wiki/Field_Museum_of_Natural_History",
    } <= set(notations["cnhm"].source)
    assert notations["species_number"].fields == ("taxon",)
    assert "src/specimen_digitization/field_research/prompts/taxon.txt:8-9" in notations["species_number"].source
    assert notations["female_sign"].fields == notations["male_sign"].fields == ()
    assert loaded.advice("Sp.30 \N{MALE SIGN}") == ontology.Advice(
        fields=("taxon",), means=(MORPHOCODE, MALE), notations=("species_number", "male_sign"))
    assert loaded.advice("CNHM").notations == ("cnhm",)
    # After a genus, the same notation (taxon.txt:5).
    assert loaded.advice("Aus sp. 1").notations == ("species_number",)
    extent = next(rule for rule in loaded.rules if rule.id == "precise_location_extent")
    assert extent.darwin_core == "verbatimLocality"
    for source in ("docs/product-requirements/PRD.md:774", "docs/product-requirements/GEOREFERENCING.md:276",
                   "tests/fixtures/field_model_pilot_rows.json:325"):
        assert source in extent.source


def test_cnhm_is_the_institution_and_on_a_locality_line_part_of_the_precise_location():
    """"CNHM." fills no field of its own and is never a collector; written on a locality line it is part of
    the precise location as written (precise_location_extent), as the pilot truth holds it. The reading is
    general: it names no slide."""
    loaded = ontology.ontology()
    cnhm = next(notation for notation in loaded.notations if notation.id == "cnhm")
    extent = next(rule for rule in loaded.rules if rule.id == "precise_location_extent")

    assert (cnhm.written, cnhm.fields, cnhm.readings) == (("CNHM.",), (), (CNHM,))
    assert cnhm.note == "Written on a locality line, it is part of the precise location as written."
    assert "every line of its locality text" in extent.note and "every line of its locality" in extent.instruction
    assert not re.search(r"\d{6,}|e98a924c|t1-\d|slide", " ".join((*cnhm.readings, cnhm.note)))
    rows = json.loads((ROOT / "tests/fixtures/field_model_pilot_rows.json").read_text(encoding="utf-8"))["rows"]
    on_a_locality_line = [row for row in rows if "CNHM" in row["as_written"]["locality"]]
    assert len(on_a_locality_line) == 2
    for row in on_a_locality_line:
        assert "CNHM" in row["expected"]["precise_location"] and "CNHM" not in row["expected"]["collectors"]
    for line in (57, 79, 115):
        assert f"tests/fixtures/field_model_pilot_rows.json:{line}" in cnhm.source

def test_the_specs_dated_line_of_2026_11_14_quotes_the_owner():
    path = ROOT / "docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    owner = ("\"4 shouldn't be flagged. It should be caught and handled. Goal isn't to throw everything at the user"
             " it is to help by being in in autonomy as much as possible.\"")
    [dated] = [line for line in lines if line.startswith("2026-11-14, the owner")]

    assert owner in dated
    assert any("\"Harness needs to work and do its magic\"" in line for line in lines)
    assert ontology.PATH.read_text(encoding="utf-8").count(owner) == 1


# ---- version 2.0: the highest-point table (WP 2.1) ---------------------------------------------------------

def test_the_highest_point_table_is_cited_once_with_its_query_and_has_one_row_per_country():
    table = ontology.ontology().highest_points

    assert table.endpoint == "https://query.wikidata.org/sparql"
    assert re.fullmatch(r"2026-11-14T\d\d:\d\d:\d\dZ", table.retrieved)
    for term in ("wdt:P610", "p:P2044", "psn:P2044", "wd:Q6256", "wd:Q3624078", "wdt:P576"):
        assert term in table.query
    assert len(table.rows) == 202
    assert len({row.country for row in table.rows}) == len(table.rows)
    assert all(re.fullmatch(r"Q[1-9]\d*", row.country) and re.fullmatch(r"Q[1-9]\d*", row.point)
               and row.country_name and row.point_name and row.elevation_m > 0 for row in table.rows)


def test_the_philippines_highest_point_is_mount_apo_at_2954_metres():
    """The spec's section 4 states 2,954 m; Wikidata's value is the same."""
    assert ontology.ontology().highest_point("Q928") == ontology.HighestPoint(
        country="Q928", country_name="Philippines", point="Q455963", point_name="Mount Apo",
        elevation_m=Decimal("2954"))
    assert ontology.ontology().highest_point("Q1") is None


def test_the_loader_refuses_a_field_two_derivation_rules_derive():
    data = shipped()
    entry(data, "rules", "elevation_unit_feet")["derives"] = True

    with pytest.raises(ontology.OntologyError, match="a field is derived by two rules"):
        ontology.parse(data)


@pytest.mark.parametrize("change,message", [
    ({"point": "Apo"}, r"rows\[\d+\]\.point must be a Wikidata Q-id"),
    ({"country": "Q0928"}, r"rows\[\d+\]\.country must be a Wikidata Q-id"),
    ({"elevation_m": 0}, r"rows\[\d+\]\.elevation_m must be a positive number"),
    ({"elevation_m": "2954"}, r"rows\[\d+\]\.elevation_m must be a positive number"),
    ({"point_name": None}, r"rows\[\d+\]: missing key 'point_name'"),
    ({"country": "Q774"}, "a country is written twice"),
])
def test_the_loader_refuses_a_malformed_row(change, message):
    data = shipped()
    row = next(item for item in data["highest_points"]["rows"] if item["country"] == "Q928")
    for key, value in change.items():
        if value is None:
            del row[key]
        else:
            row[key] = value

    with pytest.raises(ontology.OntologyError, match=message):
        ontology.parse(data)


@pytest.mark.parametrize("part", ("source", "endpoint", "retrieved", "query", "selection", "rows"))
def test_the_loader_refuses_the_table_without_any_part_of_its_citation(part):
    data = shipped()
    del data["highest_points"][part]

    with pytest.raises(ontology.OntologyError, match="has no source" if part == "source" else f"missing key '{part}'"):
        ontology.parse(data)


# ---- WP 2.2: the rules in the models' instructions --------------------------------------------------

def every_instruction() -> dict[str, str]:
    """ontology.render_instructions for each model, an expert's under "expert:<field>"."""
    found = {model: ontology.render_instructions(model) for model in ("reader", "first_pass", "organiser")}
    found |= {f"expert:{key}": ontology.render_instructions("expert", key) for key in MANDATORY}
    return found


def test_the_instructions_each_model_receives_are_pinned():
    assert every_instruction() == json.loads(RENDERED_INSTRUCTIONS.read_text(encoding="utf-8"))


# The fields each rule concerns and whether it is about reading a label: an expert receives the rules
# naming its field, the readers and the first pass the reading rules, the organiser every rule.
PLACES4 = ("country", "province_state", "county", "city")
DATES = ("date_visited_from", "date_visited_to", "date_identified")
ELEVATIONS = ("elevation_from_m", "elevation_to_m", "elevation_from_ft", "elevation_to_ft")
RULE_ROUTES = {
    "one_collecting_event": ((*PLACES4, "precise_location", "date_visited_from", "date_visited_to"), False),
    "place_within_settled_places": (("province_state", "county", "city"), False),
    "place_chain": (PLACES4, False),
    "date_order": (DATES, False),
    "day_month_order": (DATES, True),
    "code_is_no_date": (DATES, True),
    "label_type_routing": ((), True),
    "elevation_unit_feet": (ELEVATIONS, True),
    "elevation_needs_a_unit": (ELEVATIONS, False),
    "elevation_unit_decides_field": (ELEVATIONS, False),
    "place_parents_derived": (("country", "province_state", "county"), False),
    "elevation_conversion": (ELEVATIONS, False),
    "end_date_from_one_date": (("date_visited_to",), False),
    "precise_location_extent": (("precise_location",), True),
}


def test_each_model_receives_the_rules_that_concern_it_and_no_other():
    loaded = ontology.ontology()
    assert {rule.id: (rule.fields, rule.reading) for rule in loaded.rules} == RULE_ROUTES
    for model, text in every_instruction().items():
        expert = model.partition(":")[2]
        for rule in loaded.rules:
            wanted = (model == "organiser" or (expert and expert in rule.fields)
                or (model in ("reader", "first_pass") and rule.reading))
            assert text.count(f"- {rule.instruction}") == wanted, (model, rule.id)
        assert bool(text) == any(f"- {rule.instruction}" in text for rule in loaded.rules)


# Words that say how the code decides, which a model's instruction never says (the coordinator's ruling 5
# for WP 2.2: instructions say what to do).
HOW_CODE_DECIDES = re.compile(r"\b(?:refused|refuses|marked|cleared|clears|settles|the code|the step|derived|"
    r"checked|unresolved|a person)\b", re.IGNORECASE)


def test_an_instruction_says_what_to_do_and_names_no_code_line_work_package_or_gate():
    for rule in ontology.ontology().rules:
        assert NOT_FOR_A_MODEL.findall(rule.instruction) == [], rule.id
        assert HOW_CODE_DECIDES.findall(rule.instruction) == [], rule.id
        assert rule.instruction not in rule.statement and rule.statement not in rule.instruction
    for text in every_instruction().values():
        assert NOT_FOR_A_MODEL.findall(text) == []


@pytest.mark.parametrize("change,message", [
    ({"fields": ["precise_location", "locality"]}, "is not one of the profile's 20 fields"),
    ({"fields": ["precise_location", "precise_location"]}, "names a field twice"),
    ({"reading": "yes"}, "must be true or false"),
    ({"fields": " "}, "must be a list"),
])
def test_the_loader_refuses_a_rules_malformed_fields_or_reading(change, message):
    data = shipped()
    entry(data, "rules", "precise_location_extent").update(change)

    with pytest.raises(ontology.OntologyError, match=message):
        ontology.parse(data)


@pytest.mark.parametrize("model,field,message", [
    ("reviewer", None, "no model 'reviewer'"),
    ("expert", None, "an expert's rules need its field"),
    ("organiser", "country", "an expert's rules need its field"),
    ("expert", "locality", "is not one of the profile's 20 fields"),
])
def test_render_instructions_refuses_a_model_or_field_it_does_not_know(model, field, message):
    with pytest.raises(ontology.OntologyError, match=message):
        ontology.render_instructions(model, field)


# ---- WP 2.2: one source of notations, the code's tables pinned to the file -------------------------

def table_problems(tables: ontology.Tables) -> list[str]:
    """Where the file's tables and the code's disagree: geography_tool.NOTATIONS, written.ELEVATION_UNITS,
    written.RANGE_WORDS and RANGE_SIGNS, and date_notations.NOTATIONS (its orders in order, each example
    read first by the notation at its place)."""
    from specimen_digitization.application import date_notations, geography_tool
    from specimen_digitization.field_research import written

    problems = []
    words = tables.place_unit_words
    if len(set(words)) != len(words) or frozenset(words) != geography_tool.NOTATIONS:
        problems.append("place_unit_words")
    if dict(tables.elevation_units) != written.ELEVATION_UNITS:
        problems.append("elevation_units")
    if dict(tables.range_words) != written.RANGE_WORDS or tables.range_signs != written.RANGE_SIGNS:
        problems.append("range_joiners")
    orders = [order for order, _ in tables.date_notations]
    if orders != [order for order, _ in date_notations.NOTATIONS]:
        problems.append("date_notations: orders")
    else:
        for index, (order, example) in enumerate(tables.date_notations):
            first = next((at for at, (_, pattern) in enumerate(date_notations.NOTATIONS) if pattern.fullmatch(example)),
                None)
            if first != index:
                problems.append(f"date_notations: {order} {example!r}")
    return problems


def test_the_codes_notation_tables_are_the_files():
    assert table_problems(ontology.ontology().tables) == []


@pytest.mark.parametrize("change,problem", [
    (lambda t: t["place_unit_words"]["words"].append("dpto"), "place_unit_words"),
    (lambda t: t["place_unit_words"]["words"].remove("mun"), "place_unit_words"),
    (lambda t: t["elevation_units"]["units"]["ft"].remove("'"), "elevation_units"),
    (lambda t: t["elevation_units"]["units"]["m"].append("mt"), "elevation_units"),
    (lambda t: t["range_joiners"]["words"]["German"].append("bis zu"), "range_joiners"),
    (lambda t: t["range_joiners"]["signs"].append("+"), "range_joiners"),
    (lambda t: t["date_notations"]["notations"].pop(), "date_notations: orders"),
    (lambda t: t["date_notations"]["notations"][3].update(example="6.ix.1946"),
        "date_notations: day-month-year '6.ix.1946'"),
], ids=["word-added", "word-removed", "foot-mark-removed", "mt-added", "joiner-added", "sign-added",
        "notation-removed", "example-of-another-notation"])
def test_a_table_that_disagrees_with_the_codes_fails(change, problem):
    """The pin's failures, shown on copies of the file: each change to a table makes it disagree with
    the code's, as a change to the code's table would."""
    data = shipped()
    change(data["tables"])

    assert table_problems(ontology.parse(data).tables) == [problem]


@pytest.mark.parametrize("table", ["place_unit_words", "elevation_units", "range_joiners", "date_notations"])
def test_the_loader_refuses_a_table_with_no_source(table):
    data = shipped()
    del data["tables"][table]["source"]

    with pytest.raises(ontology.OntologyError, match=f"tables.{table} has no source"):
        ontology.parse(data)


def test_no_rendered_text_carries_the_code_tables():
    rendered = [ontology.render(), ontology.render(brief=True), ontology.render_rules(), *every_instruction().values()]
    for text in rendered:
        assert "mamsl" not in text and "depto" not in text and "year-monthname" not in text
