"""The field experts' instructions (prompts.instructions): the shared rules, the specimen
ontology's brief text (ontology.render(brief=True)), the instructions of its rules that name the
field (ontology.render_instructions("expert", key)) and the field's brief.

WP 1.3 to 2.4 of docs/execution/units/PLAN.md gave the units path these instructions as the old
path's with the texts a file of replacements (prompts/units.txt) named. The
instructions are byte for byte the units path's on main d83f4d6f1 (MAIN)."""

from __future__ import annotations

import hashlib

import pytest

from specimen_digitization.field_research.contracts import FIELD_TOOLS
from specimen_digitization.field_research.prompts import instructions
from specimen_digitization.ontology import render, render_instructions

# Each field's instructions on the units path on main d83f4d6f1 (instructions(key, units=True)
# there), as the sha256 of their UTF-8 bytes.
MAIN = {
    'taxon': "sha256:b34fd9b30faba7ff37ba33144206a8bc57ed8414df0cfd9c61565d901fbc96f7",
    'country': "sha256:5374054c21c53756da3e579d71425eb5b27136ad81eabcd059f78f2ea68675be",
    'province_state': "sha256:ba24c741170f17170b81b920d3b305339ca9ce87c2c1ad2ad8445ae6fce15ea8",
    'county': "sha256:c73352f1c9cc9ea3318eca667270d51ccae8113c904960b81337ef2b4ef66f04",
    'city': "sha256:eaa419ceedb7ae52a82f73cad6ac348e10bb41bec90380a55cca16e7b750b474",
    'precise_location': "sha256:357d8fcca1b7de341523c3bf539e9edc45ef000494c86429fc535f6e14ee4dee",
    'date_visited_from': "sha256:72a2baf0daed149e7a4157af60573724d69e3665c9aa1c090ba97a8129222314",
    'date_visited_to': "sha256:6a5db82852a032e42a7e21720df0f3aa41cafe6085fc80c61f5699d5a9c0f221",
    'date_identified': "sha256:fcac37a83b49a1648a3e0ee2afe04da4e905786e2054a32af30dd8670fdc5b3a",
    'elevation_from_m': "sha256:aec657103c3ca11e83490eff534a2dadeba433f4369ede931339aa2489769b40",
    'elevation_to_m': "sha256:d3ff2536cb0f2567b4a0b87b8d9ea9d953c397b94a903ee740f272a05766b56a",
    'elevation_from_ft': "sha256:2dac43c894f1ea81e7d16264dbef53590e8a275846a704a8fffce7e276c43633",
    'elevation_to_ft': "sha256:a9f964c9c903fff7ad262b3e7b3c04e8ef85d763089a15cc349554a0d6e256ca",
    'fmnh_ins_number': "sha256:da01681d168299baafa34ff2117eab96265a734d57cf75624f9be772d8230cb3",
    'collectors': "sha256:e1b9b9928944865f9526e7ecb60f1447ff188ed210d43d33dbebea04a61b318d",
    'collection_code': "sha256:27e9950e9407223f3e6563a3b94fbe8dc000fd46a33b51cc043a39af6e15c161",
    'habitat': "sha256:8844565ed36b13ce827cef55ff014550baac53d037ec56158f839dbd90dd20e8",
    'collection_method': "sha256:e3c8ad333b32c9b727f931db2500d0d43af0fa737073b00bf6f8967d4e221aa5",
    'verbatim_dts': "sha256:19da03e87645d450bd7279fa779ee8eca407ce75d60f3a75b23a4fea7412e0dc",
    'identified_by_irn': "sha256:a49fc2b103c5a02408b8713705ff53f61977b686af2063d6c2f227ec26092483",
}
TOOL_LESS = {key for key, tools in FIELD_TOOLS.items() if not tools} - {"identified_by_irn"}
PLACES = ("country", "province_state", "county", "city")


def test_the_instructions_are_the_units_paths_on_main():
    assert {key: "sha256:" + hashlib.sha256(instructions(key).encode()).hexdigest() for key in FIELD_TOOLS} == MAIN


@pytest.mark.parametrize("key", FIELD_TOOLS)
def test_the_ontology_and_the_fields_rules_stand_once_right_before_the_brief(key):
    """The ontology stands once, then the rules that name the field (none for some fields), right
    before the brief."""
    text = instructions(key)
    rendered = render(brief=True).strip()
    rules = render_instructions("expert", key).strip()
    added = rendered + ("\n\n" + rules if rules else "")
    brief = text[text.rindex("\n\nField: "):]
    assert text.count(rendered) == 1 and text.endswith(added + brief)


# The owner's reading of 2026-11-13 (spec section 5): a printed "LEWIS COLLECTION" heading is the
# Collection Code, as the ontology's brief text states it.
LEWIS_LINE = (
    '- "LEWIS COLLECTION": the printed heading of the Lewis Collection\'s label templates; it is the Collection '
    "Code, copied as written [collection_code].")


@pytest.mark.parametrize("key", FIELD_TOOLS)
def test_the_lewis_heading_ruling_is_in_every_instruction_once(key):
    """Only the ontology's brief text names Lewis: the shared rules and the briefs do not."""
    assert instructions(key).count(LEWIS_LINE) == 1
    assert "lewis" not in instructions(key).lower().replace(LEWIS_LINE.lower(), "")


@pytest.mark.parametrize("key", FIELD_TOOLS)
def test_the_instructions_name_no_first_pass_preference(key):
    """The request carries the units and no first pass opinion (experts.units_document)."""
    text = instructions(key)
    for word in ("first pass", "first_pass", "preferred", "decided_transcript"):
        assert word not in text
    assert "- units, when present:" in text


# Rule 4 on the units path: what the code decides, said once to every expert.
RULE = ("The code decides from the image judgements, the source answers your lookups returned and the readers' "
    "agreement whether a value is cleared, marked for a person to check, or left open, and it refuses an answer it cannot "
    "settle, saying why.")


@pytest.mark.parametrize("key", FIELD_TOOLS)
def test_the_instructions_state_the_rule_and_define_no_backing(key):
    text = instructions(key)
    assert text.count(RULE) == 1
    for definition in ("Image: the unit holding it", "Source: you asked your sources", "Text: two or more readers",
            "where 2A writes", "Each unit gives every reader's text", "the source answers you cite and",
            "When readings disagree", "When readings name different countries"):
        assert definition not in text


# What a place brief says where the readings differ (Codex round 7, W3; WP 1.3's rework, gap
# report item 2(a)).
DIFFER_SAYS = ("When the readings differ, answer the reader's text your lookups and the units support, naming the "
    "readings that hold it and citing the source answers. Answer several_possibilities, with each reader's text, "
    "only where you find no text to answer.")
# Each place brief's line on readings that disagree before WP 1.3, which DIFFER_SAYS replaced.
DISAGREE = {
    "country": "- When readings name different countries, or a source finds several countries for the text, answer "
        "several_possibilities.",
    "province_state": "- When readings disagree, or a source leaves more than one unit, answer several_possibilities.",
    "county": "- When readings disagree, or a source leaves more than one second-level unit, answer "
        "several_possibilities.",
    "city": "- When readings disagree, or a source leaves more than one town, answer several_possibilities.",
}


@pytest.mark.parametrize("key", FIELD_TOOLS)
def test_a_place_brief_says_what_to_answer_where_the_readings_differ(key):
    """W3: each of the four place briefs says to answer the text the lookups and the units
    support, keeping its own clause on a source that leaves several places; the line it replaced
    stands nowhere."""
    text = instructions(key)
    if key not in PLACES:
        assert DIFFER_SAYS not in text
        return
    clause = DISAGREE[key][DISAGREE[key].index(", or a source ") + len(", or "):]
    assert DISAGREE[key] not in text
    assert text.count(f"- {DIFFER_SAYS} When {clause}") == 1


# Each label notation WP 1.3's rework left out of common.txt, with the ontology's text that gives it
# (ontology.render(brief=True), which the instructions carry).
LEFT_OUT = {
    '- "Prov.", "Dept.": province, department; a word of the unit\'s name, not the name itself.':
        ('- "Prov.": province', '- "Dept.": department'),
    '- "Mt.": mount, part of the place\'s name. "Is.": island or islands. "nr.": near. "E. slope", "W. side": a '
    'direction qualifying the place that follows.':
        ('- "Mt.": mount', '- "Is.": island or islands', '- "nr.": near', '- "E. slope", "W. side": a direction'),
    '- "leg.", "coll.", "Coll.": collected by, marking the collectors. "det.": determined by, marking who '
    'identified the specimen.': ('- "leg.", "coll.", "Coll.": collected by', '- "det.": determined by'),
    '- A date can be a range ("<d1>-<d2>.IX.<yyyy>", "VIII-IX.<yy>", "<d1>.IX-<d2>.X.<yyyy>"): its first date is '
    'the start and its second the end.': ("a range: its first date is the start and its second the end",),
    '- A two-digit year ("\'<yy>", "-<yy>") is read as 19<yy> under the profile\'s century rule.':
        ('- "\'<yy>", "-<yy>": the year 19<yy>, under the profile\'s century rule',),
    '- "m", "ft.", "\'", "alt.", "el.": the unit or heading of an elevation. "ca.", "c.": about; the value is '
    'approximate.': ('- "<n> m": metres', '- "<n> ft.", "<n>\'": feet', '- "alt.", "el.": the heading of an elevation',
        '- "ca.", "c.": about: the value is approximate'),
    '- "?": the value before it is uncertain as written.': ('- "?": the value before it is uncertain as written',),
    '- Slide or preparation codes, a month, a day, a two-digit year and a slide number joined by hyphens '
    '("<Roman month>-<dd>-<yy>-<n>", "<mm>-<dd>-<yy>-<n><letter>"), are never dates, nor is any part of them.':
        ('"<Roman month>-<dd>-<yy>-<n>", "<mm>-<dd>-<yy>-<n><letter>": a slide or preparation code',
         "never a date, nor is any part of it"),
}


@pytest.mark.parametrize("key", FIELD_TOOLS)
def test_the_label_notations_left_out_of_the_shared_rules_are_the_ontologys_text(key):
    """Gap report item 3: the request stays under the input bound (budget.DEFAULT_MAX_INPUT_TOKENS);
    each label notation line left out of common.txt stands in no instructions, and the ontology's
    text they carry gives what it said."""
    text = instructions(key)
    rendered = render(brief=True)
    for line, gives in LEFT_OUT.items():
        assert line not in text
        assert all(given in rendered for given in gives), line


# Gap report items 2(a) and 4: what the instructions say an expert answers.
ANSWERS = (
    "Whenever a reader writes a text for this field, answer with the literal exactly as a reader wrote it, the "
    "readings that hold it, and the source answers you cite.",
    'Readers whose texts differ only in letter case or spacing ("shrubs" and "Shrubs", "sp. 30" and "Sp.30") agree: '
    "answer the text as one of them writes it.",
    "Two or more readers who write one text give an answer, not a choice: answer that text.",
    "Answer several_possibilities, with each reader's text as its options, only where you find no text to answer.",
)
NOTE = "A unit's note is never a reason to refuse a name every reader writes."
NAMES_INSIDE = 'also where one unit holds the names and the marker ("<Initials> <Surname> leg."): the literal is then ' \
    "the names inside it."
COUNTRY_INSIDE = ('also where one unit holds more than the country ("<Place>, <Notation>"): the literal is then the '
    "country's own text inside it.")


@pytest.mark.parametrize("key", FIELD_TOOLS)
def test_the_instructions_say_to_answer_the_text_the_readings_write(key):
    """Rule 4: answer a reader's text; readers that differ only in letter case or spacing agree;
    two or more readers' one text is an answer; several_possibilities only where no text is
    found. The collectors brief takes the names inside a unit and never refuses for a unit's
    note; the country brief takes the country's own text inside a unit."""
    text = instructions(key)
    for sentence in ANSWERS:
        assert text.count(sentence) == 1
    for sentence, field in ((NOTE, "collectors"), (NAMES_INSIDE, "collectors"), (COUNTRY_INSIDE, "country")):
        assert text.count(sentence) == (key == field)


# ---- WP 2.2: the ontology's rules and Precise Location's whole locality -------------------------

# The starts of common.txt's two date notation lines WP 2.2 replaced, each with the ontology's text
# that gives what it said (ontology.render(brief=True)), and the lines in their place, which keep what
# is the date check's own (parse_date, day_month_order_ambiguous).
DATE_LINES = {
    "- A Roman numeral I to XII in a date is the month": ("the month, January to December, in any position of the date",
        "A month may be written by name in English, Spanish, French, German, Portuguese, Italian or Latin",
        'a day may carry an ordinal ("3rd", "1er")'),
    "- A numeric date (": ('"<a>-<b>-<yy>", "<a>.<b>.<yy>", "<a>/<b>/<yy>": month <a>, day <b>; or day <a>, month <b>',
        "Settled only when a part over 12 fixes day against month; otherwise both readings stand until evidence "
        "decides"),
}
DATE_SAYS = ("- parse_date reads each date notation of the specimen ontology below.",
    "- parse_date names a numeric date whose two orders give different dates (day_month_order_ambiguous).")


@pytest.mark.parametrize("key", FIELD_TOOLS)
def test_the_two_date_notation_lines_are_the_date_checks_own_words(key):
    """The expert request stays under budget.DEFAULT_MAX_INPUT_TOKENS with the rules added
    (test_units_request_size.py): one line each on the date check stands in place of common.txt's
    two date notation lines, and the ontology's text the instructions carry gives what they said."""
    text = instructions(key)
    assert not [line for line in text.splitlines() if line.startswith(tuple(DATE_LINES))]
    for says in DATE_SAYS:
        assert text.count(says) == 1
    rendered = render(brief=True)
    for gives in DATE_LINES.values():
        assert all(given in rendered for given in gives)


@pytest.mark.parametrize("key", FIELD_TOOLS)
def test_each_expert_receives_the_rules_that_name_its_field(key):
    """ontology.render_instructions("expert", key), pinned in tests/test_ontology.py: each rule that
    names the field stands once, and no other rule."""
    from specimen_digitization import ontology

    text = instructions(key)
    rules = [rule for rule in ontology.ontology().rules if key in rule.fields]
    for rule in ontology.ontology().rules:
        assert text.count(rule.instruction) == (rule in rules)
    assert ("The specimen ontology's rules for this field:" in text) == bool(rules)


# The precise location brief (prompts/precise_location.txt, from WP 2.2): the label's whole locality.
WHOLE_LOCALITY = (
    "Field: Precise Location (precise_location). The label's whole locality as written: every line of its locality "
    'text, such as "E. slope Mt. <Mountain>, nr. <Town>" over "<Province>, <Country>".',
    "the higher places those lines write (the town, the province, the country, notations included), an elevation "
    'written on them ("<Town>, <n> ft.") and "CNHM." where a locality line writes it.',
    'On those lines it may hold the higher places, an elevation and "CNHM." as written; it never holds a collector, '
    "a date or any other field's text, even on a locality line: leave that text out, and leave out the lines that "
    "hold only other fields (collectors, dates, codes, the taxon).",
    "- A locality that names nothing finer than its town is still this field: its lines as written. Answer "
    "label_lacks_value only when no reading writes a locality.",
)
# What the brief said before WP 2.2 that the rule precise_location_extent contradicts (its note).
CUT_SHORT = (
    "Leave out what belongs to other fields: country, province, county or city written as such, dates, collectors "
    "and elevations.",
    "- When no reading writes a locality more precise than the other place fields, answer label_lacks_value.",
)


def test_the_precise_location_brief_takes_the_whole_locality():
    whole = instructions("precise_location")
    for text in WHOLE_LOCALITY:
        assert whole.count(text) == 1
    for key in FIELD_TOOLS:
        assert not any(text in instructions(key) for text in CUT_SHORT)
        if key != "precise_location":
            assert not any(text in instructions(key) for text in WHOLE_LOCALITY)
