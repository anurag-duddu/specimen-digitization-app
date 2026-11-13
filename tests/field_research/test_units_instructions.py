"""Work package 1.3 of docs/execution/units/PLAN.md: the field experts' instructions on the
units path (prompts.instructions(key, units=True)) and the old path's, unchanged.

The units path's text is the old path's with each text units.txt names replaced (common.txt's
first_pass line, its rule 4 and a sentence of its literal's line; a line of each of the five
tool-less briefs; the line of each of the four place briefs on readings that disagree) and the specimen ontology's brief text (ontology.render(brief=True)) between the
shared rules and the brief. Every test here runs once: this module's first_pass_path fixture replaces conftest.py's,
as no run is built."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from specimen_digitization.field_research.contracts import FIELD_TOOLS
from specimen_digitization.field_research.prompts import instructions
from specimen_digitization.ontology import render


def units_replacements():
    from specimen_digitization.field_research.prompts import units_replacements

    return units_replacements()


def parse_replacements(text):
    from specimen_digitization.field_research.prompts import parse_replacements

    return parse_replacements(text)


@pytest.fixture(autouse=True)
def first_pass_path():
    return "old"


# Each field's instructions on main c348f8a1a, as the sha256 of their UTF-8 bytes.
MAIN = {
    'taxon': "sha256:497fdf585680d65670282d0a45da3198f56547f5b8d08d9603433b8cea2be453",
    'country': "sha256:07a59e12a355229044ff2c411afb473f757471d280c2323cc31255cf241e926b",
    'province_state': "sha256:a3ffea8bbe16cfe1895d45273985e4328afcc753ffc06a8347441480874df40d",
    'county': "sha256:a0187d6fe4fccb2543e7ef1e8d1844f62e86cf7df5cf9c5d8433926c1cba2904",
    'city': "sha256:e0dc10f94fdd2f5e443d9b2224d6ccd2e79bb6bdad952910c3827b18c21ffce3",
    'precise_location': "sha256:33d76dc43f148315d22d29c2b95cc2081610e028f1aceafcd5c0c51cd0f24b79",
    'date_visited_from': "sha256:777dd08d13322cba0ad7562eb6f3aaf593400b8f024e458f60063e9a0f553b92",
    'date_visited_to': "sha256:ef25b2bdf18ae3dd1414142afaff8e30fd5abc74555f38240bea24ba855b3cd2",
    'date_identified': "sha256:7662095ab3a8db9cff2fe21af3800dc573252bdb45cff89155e4a0be623f0275",
    'elevation_from_m': "sha256:b35375e89749a36ee6f6d9991ac02e50d14883bc76a1e4634826ea93fd6cfd03",
    'elevation_to_m': "sha256:cccc9796085c712c25d9c0e500b302a2fa81cbf82957715a77538956f50eb969",
    'elevation_from_ft': "sha256:8ff88fb0f35ad15a24dfcd3bec2ef28d191656a55ad38a16124ced14c17af526",
    'elevation_to_ft': "sha256:97f866685b7b68868b62e3e2e888d618bafc32dd17ee7f8eb67a1a45aeb741cf",
    'fmnh_ins_number': "sha256:8adce428d2b8df70339246771fd2aa5bb97dc5ecbca0585c22ebc42206317606",
    'collectors': "sha256:ad9016683ef34c383c5a8e7302a90997a8515c721285462f254e7228d12a16e1",
    'collection_code': "sha256:3d50983870f2ba591e5030e53c926150e3a846d68ff1a12bcccd1fcbf7ff4bce",
    'habitat': "sha256:0107a1f9d32fd2514f7070f490d725762424d4dc61cb575bc3481173705041c4",
    'collection_method': "sha256:91783252963d7896fdcfd65735e42b18340e99bf9848a6cfa8589802f09493ad",
    'verbatim_dts': "sha256:91855f36a996b6f8391da14f1f7a316cdcdb8a57a70c5fe6229b50141397ef07",
    'identified_by_irn': "sha256:cc808e1bddd2f36a09f0d4bb7c1ae378bcc1034c03dc9d6e3e69c5e3ec134651",
}
TOOL_LESS = {key for key, tools in FIELD_TOOLS.items() if not tools} - {"identified_by_irn"}
PLACES = ("country", "province_state", "county", "city")


def test_the_old_paths_instructions_are_main_s():
    assert {key: "sha256:" + hashlib.sha256(instructions(key).encode()).hexdigest() for key in FIELD_TOOLS} == MAIN


def test_units_txt_replaces_texts_of_common_txt_the_five_tool_less_briefs_and_the_four_place_briefs_only():
    assert TOOL_LESS == {"collectors", "collection_code", "habitat", "collection_method", "verbatim_dts"}
    assert set(units_replacements()) == {"common.txt", *(f"{key}.txt" for key in (*TOOL_LESS, *PLACES))}


@pytest.mark.parametrize("key", FIELD_TOOLS)
def test_the_units_paths_instructions_are_the_old_ones_with_units_txt_s_texts_and_the_ontology(key):
    """The ontology stands once, right before the brief; taking it out and putting each
    replaced text back gives the old path's instructions, each text units.txt names standing
    once in the old ones and its replacement once in the units path's."""
    old, new = instructions(key), instructions(key, units=True)
    rendered = render(brief=True).strip()
    brief = new[new.rindex("\n\nField: "):]
    assert new.count(rendered) == 1 and new.endswith(rendered + brief)
    undone = new.replace("\n\n" + rendered, "", 1)
    for name in ("common.txt", f"{key}.txt"):
        for old_text, new_text in units_replacements().get(name, ()):
            assert old.count(old_text) == 1 and undone.count(new_text) == 1
            undone = undone.replace(new_text, old_text)
    assert undone == old


@pytest.mark.parametrize("key", FIELD_TOOLS)
def test_the_units_paths_instructions_name_no_first_pass_preference(key):
    """The units path's request carries the units and no first pass opinion
    (experts.units_document)."""
    text = instructions(key, units=True)
    for word in ("first pass", "first_pass", "preferred", "decided_transcript"):
        assert word not in text
    assert "- units, when present:" in text


# prompts/units.txt as PR #425's seventh round leaves it, as the sha256 of its bytes.
UNITS_TXT = "sha256:215e04b6894e17940cfca6860304aa68c95961aff3f58fdb97ce98ab03c957dc"
# Rule 4 on the units path: what the code decides, said once to every expert.
RULE = ("The code decides from the image judgements, the source answers your lookups returned and the readers' "
    "agreement whether a value is cleared, marked for a person to check, or left open, and it refuses an answer it cannot "
    "settle, saying why.")


def test_units_txt_is_pinned():
    """Codex rounds 6 (V3) and 7 (W1 to W3): units.txt says what an expert needs, no definitions of the
    backings."""
    from specimen_digitization.field_research import prompts

    path = Path(prompts.__file__).with_name("units.txt")
    assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == UNITS_TXT


@pytest.mark.parametrize("key", FIELD_TOOLS)
def test_the_units_paths_instructions_state_the_rule_and_define_no_backing(key):
    text = instructions(key, units=True)
    assert text.count(RULE) == 1
    for definition in ("Image: the unit holding it", "Source: you asked your sources", "Text: two or more readers",
            "where 2A writes", "Each unit gives every reader's text", "the source answers you cite and",
            "When readings disagree", "When readings name different countries"):
        assert definition not in text


@pytest.mark.parametrize(("text", "found"), [
    ("", {}),
    ("# a comment\n\n== a.txt\n<<< x\n>>> y\n", {"a.txt": (("x", "y"),)}),
    ("== a.txt\n<<< x\n>>> y\n<<< z\n>>> w\n== b.txt\n<<< u\n>>> \n",
        {"a.txt": (("x", "y"), ("z", "w")), "b.txt": (("u", ""),)}),
], ids=["empty", "one", "two-files"])
def test_units_txt_s_form_is_read(text, found):
    assert parse_replacements(text) == found


@pytest.mark.parametrize("text", [
    "<<< x\n>>> y\n",
    "== a.txt\n>>> y\n",
    "== a.txt\n<<< x\n<<< z\n>>> y\n",
    "== a.txt\n<<< x\n",
    "== a.txt\n<<< x\n== b.txt\n>>> y\n",
    "== a.txt\nx\n",
    "== a.txt\n <<< x\n>>> y\n",
], ids=["text-before-a-file", "replacement-alone", "two-texts", "text-last", "file-between", "no-form",
    "indented"])
def test_units_txt_refuses_a_line_out_of_its_form(text):
    with pytest.raises(ValueError):
        parse_replacements(text)


# What a place brief says on the units path where the readings differ (Codex round 7, W3).
DIFFER_SAYS = ("When the readings differ, answer the text your lookups and the units support, citing the source "
    "answers; the code decides whether it settles. When you cannot choose, answer several_possibilities with each "
    "reader's text.")
# Each place brief's own line on the old path, which the units path replaces.
DISAGREE = {
    "country": "- When readings name different countries, or a source finds several countries for the text, answer "
        "several_possibilities.",
    "province_state": "- When readings disagree, or a source leaves more than one unit, answer several_possibilities.",
    "county": "- When readings disagree, or a source leaves more than one second-level unit, answer "
        "several_possibilities.",
    "city": "- When readings disagree, or a source leaves more than one town, answer several_possibilities.",
}


@pytest.mark.parametrize("key", FIELD_TOOLS)
def test_a_place_brief_says_what_to_answer_where_the_readings_differ_on_the_units_path_only(key):
    """W3: the four place briefs' line on readings that disagree stands on the old path
    (test_the_old_paths_instructions_are_main_s); on the units path it says to answer the text
    the lookups and the units support, keeping the brief's own clause on a source that leaves
    several places."""
    old, new = instructions(key), instructions(key, units=True)
    if key not in PLACES:
        assert DIFFER_SAYS not in new
        return
    clause = DISAGREE[key][DISAGREE[key].index(", or a source ") + len(", or "):]
    assert old.count(DISAGREE[key]) == 1 and DISAGREE[key] not in new
    assert new.count(f"- {DIFFER_SAYS} When {clause}") == 1
