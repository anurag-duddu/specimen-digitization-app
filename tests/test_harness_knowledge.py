"""The subcollections' harness knowledge (HARNESS.md section 11, G29)."""

import pytest

from specimen_digitization.application.geography_tool import fold
from specimen_digitization.application.harness_knowledge import (
    insects,
    instructions_for,
)


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
    assert insects.KNOWLEDGE_VERSION == "insects-harness-knowledge-v2"


def test_a_single_elevation_or_date_is_given_once_as_from():
    # G41 derives the rest of an elevation. A single date's To stays empty for
    # review until the owner rules (the coordinator's rulings of 2026-09-24).
    text = insects.render()
    assert "A single elevation written once is given once" in text
    assert "leave Date Visited To empty" in text
