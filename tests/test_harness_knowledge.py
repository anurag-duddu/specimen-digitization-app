"""The subcollections' harness knowledge (HARNESS.md section 11, G29)."""

import re

import pytest

from specimen_digitization.application.geography_tool import fold
from specimen_digitization.application.harness_knowledge import (
    insects,
    instructions_for,
)
from specimen_digitization.application.place_text import PLACE_FIELDS


def test_the_insects_knowledge_renders_every_notation_and_the_copy_rule():
    text = insects.render()

    assert text.startswith(f"Label knowledge ({insects.KNOWLEDGE_VERSION}):")
    assert "Copy every literal exactly as the reading has it" in text
    for notation in insects.NOTATIONS:
        assert f"- {notation.written}: " in text
    assert "month 4, day 5; or day 4, month 5" in text  # G29: both orders.


def test_place_aliases_are_written_as_the_geography_tool_folds_them():
    for written, names in insects.PLACE_ALIASES.items():
        assert fold(written) == written
        assert all(fold(name) == name for name in names)
    assert insects.PLACE_ALIASES[fold("P.I.")] == ("philippines",)


def test_the_instructions_are_the_pinned_prompt_then_the_named_knowledge():
    text = instructions_for("Prompt.", "insects", insects.KNOWLEDGE_VERSION)

    assert text == "Prompt.\n\n" + insects.render()
    with pytest.raises(ValueError, match="harness_knowledge_unavailable:insects:v0"):
        instructions_for("Prompt.", "insects", "v0")
    with pytest.raises(ValueError, match="harness_knowledge_unavailable:beetles"):
        instructions_for("Prompt.", "beetles", insects.KNOWLEDGE_VERSION)


def test_slide_preparation_codes_belong_in_no_field():
    # S8's pilot research; the coordinator's ruling of 2026-09-24. Real runs had
    # put such codes into the catalogue number, the collectors and the locality.
    (codes,) = [n for n in insects.NOTATIONS if "IV-29-68-a" in n.written]
    assert codes.fields == ()
    assert "belongs in no field" in insects.render()


def test_a_single_elevation_or_date_is_given_once_as_from():
    # G41 derives the rest of an elevation. A single date's To stays empty for
    # review until the owner rules (the coordinator's rulings of 2026-09-24).
    text = insects.render()
    assert "A single elevation written once is given once" in text
    assert "the harness fills Date Visited To" in text  # G44.


def test_the_shape_rules_cover_the_fields_no_lookup_checks():
    # G45 (the owner, 2026-09-24): a value that doesn't look like its field's
    # kind goes to review; verbatim_dts's meaning is unconfirmed (PRD 522).
    assert set(insects.SHAPES) == {
        "collectors",
        "collection_code",
        "habitat",
        "collection_method",
        "precise_location",
        "verbatim_dts",
    }
    assert insects.FINDING_ONLY == {"verbatim_dts"}
    code = re.compile(insects.SHAPE_PATTERNS["preparation_code"])
    for written in ("IV-29-68-a", "VI-24-68-7", "10-6-78-la", "IX-17-66-2"):
        assert code.search(written), written
    assert not code.search("14-5-48")  # A collection date has no serial.


def test_the_place_filters_tables_come_from_the_notations():
    # PLAN 4.8's filter (HARNESS.md section 7) reads v3's markers, months and
    # full forms; each comes from a notation the agent reads too.
    assert insects.KNOWLEDGE_VERSION == "insects-harness-knowledge-v3"
    people = {
        marker
        for notation in insects.NOTATIONS
        if set(notation.fields) & {"collectors", "identified_by_irn"}
        for marker in notation.written.split(", ")
    }
    assert set(insects.PERSON_MARKERS) == people == {"leg.", "coll.", "Coll.", "det."}
    # PLAN 4.8 in #191: the date notations list each month in full and
    # abbreviated, in English and in Spanish, the pilot labels' languages.
    months = [n for n in insects.NOTATIONS if n.readings == ("the month",)]
    listed = [word for notation in months for word in notation.written.split(", ")]
    assert list(insects.MONTH_WORDS) == listed
    assert len(listed) == 49
    assert {"September", "Sept.", "mayo", "sept.", "dic."} <= set(listed)
    # The coordinator's ruling of 2026-09-24: Roman months are cut too.
    (roman,) = [n for n in insects.NOTATIONS if n.written == "I to XII in a date"]
    assert insects.ROMAN_MONTHS[0] == "I" and insects.ROMAN_MONTHS[-1] == "XII"
    assert len(insects.ROMAN_MONTHS) == 12 and roman.fields


def test_only_place_notations_have_full_forms_and_each_is_a_reading():
    # The steward's review of #174: a full form expands a notation the table
    # assigns to place fields alone, never a month, a year or a marker.
    by_written = {notation.written: notation for notation in insects.NOTATIONS}
    for written, full in insects.FULL_FORMS.items():
        notation = by_written[written]
        assert notation.fields and set(notation.fields) <= set(PLACE_FIELDS)
        assert all(form.casefold() in notation.readings[0].casefold() for form in full)
    assert insects.FULL_FORMS["P.I."] == ("Philippine Islands",)
    assert insects.FULL_FORMS["Is."] == ("Island", "Islands")
