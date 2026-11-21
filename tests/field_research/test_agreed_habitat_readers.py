"""An agreed Habitat keeps its label's flag where a reader of that label writes another text for it (lane H4 of the
autonomy program, 2026-11-21; the coordinator's ruling on the second paid habitat rerun, not the owner's words).

PR #457's rule A (second_opinion.agreed, unflagged) lifts `label_unsettled:<field>` from a value the second opinion
agrees with. In the rerun (~/specimen-golive/runs/autonomy-habitat2-20261121) truth slide 105527313's two readers
wrote a host's species differently, the first pass named one reader's text, the second opinion gave that same text,
and rule A lifted the flag from a Habitat the truth sheet reads otherwise: the one wrong Habitat of the run with no
flag. For Habitat (second_opinion.READERS_MUST_WRITE) the lift now needs every reader of the labels the value rests
on to write the value's text, letter case and spacing aside (agreement.reader_writes).

Measured free on that run's 99 answers (autonomy-program/H4/flag_rule.txt): one flag gained, on that record; none on
its 44 right Habitats; none on the stored records; no other field's flag, no reason and no disposition moved.

The records are test_agreed_no_flag's (the field research rig through the workflow, the second opinion's step mounted
with a scripted model). A reader's text is changed on the finished record and the record finalized again: the rule is
derived from the run as it is at each finalize.
"""

from __future__ import annotations

import pytest
from test_agreed_no_flag import LABEL_UNSETTLED, answer_of, codes, flagged, lifted, rig_of, to_end, values_of
from test_second_opinion import Opinion
from test_step import TODAY

from specimen_digitization.field_research import agreement
from specimen_digitization.field_research import second_opinion as so
from specimen_digitization.field_research import step as field_step

# The product's behaviour: the marks are derived (tests/conftest.py).
USES_SECOND_OPINION = True
HABITAT = "Synthetic grassland"
FLAG = f"{LABEL_UNSETTLED}:habitat"


def agreed_record(tmp_path):
    """test_agreed_no_flag's record: the readers differ on the collectors alone, the label's doubt is open, and the
    second opinion agrees with every settled value; the Habitat, which both readers write, carries no flag."""
    run = to_end(rig_of(tmp_path, opinion=Opinion(answer_of()))).run
    assert run.fields["habitat"].literal == HABITAT and run.second_opinion["fields"]["habitat"]["verdict"] == so.AGREES_VERDICT
    assert FLAG not in run.open_reasons and "habitat" not in flagged(run)
    return run


def second_reader_writes(run, old, new):
    """The second reader's text of the label with `new` for `old`, and the record finalized again."""
    reader = run.observations[1]
    assert old in reader.literal_text
    reader.literal_text = reader.literal_text.replace(old, new)
    field_step.refinalize(run, today=TODAY)
    return run


def test_only_habitat_needs_its_readers_to_write_the_agreed_value():
    assert so.READERS_MUST_WRITE == frozenset({"habitat"})
    assert not so.READERS_MUST_WRITE & so.AGREED_VALUE_EXCEPT


@pytest.mark.parametrize(("text", "literal", "writes"), [
    ("Host:\nMus\nmusculus\nAlc.", "Mus\nmusculus", True),
    ("Host:\nMus\nmusculus\nAlc.", "mus MUSCULUS", True),          # letter case and a space for a line break
    ("Host: Musmusculus", "Mus musculus", True),                    # spacing aside, as agreement_key reads it
    ("Host:\nMus\nmuscalus\nAlc.", "Mus\nmusculus", False),         # a letter off is another text
    ("Museum\nmusculus", "Mus", False),                             # never inside a longer word
    ("Host:\nMus\nmusculus.", "Mus\nmusculus", True),               # punctuation after it is no part of it
    ("Host:\nMus\nmusculus", "Mus, musculus", False),               # a punctuation mark more is another text
    ("Host:\nMus", "", False),
])
def test_a_reading_writes_a_text_letter_case_and_spacing_aside(text, literal, writes):
    assert agreement.reader_writes(text, literal) is writes


def test_an_agreed_habitat_keeps_its_labels_flag_where_a_reader_writes_another_text(tmp_path):
    """105527313's shape: the value stands, the second opinion still agrees with it, and one reader of its label
    writes a letter otherwise. The label's flag stays on the Habitat; every other agreed value loses its own as
    before. On origin/main 3eb37c11 the Habitat's flag is lifted too."""
    run = second_reader_writes(agreed_record(tmp_path), f"habitat: {HABITAT}", "habitat: Synthetic grasslund")
    assert run.fields["habitat"].literal == HABITAT
    assert run.second_opinion["fields"]["habitat"]["verdict"] == so.AGREES_VERDICT and not so.due(run)
    assert FLAG in run.open_reasons and "habitat" in flagged(run)
    others = values_of(run) - {"habitat"}
    assert {"country", "precise_location", "taxon"} <= others
    assert lifted(run) == codes(LABEL_UNSETTLED, others) and not others & flagged(run)


def test_a_reader_that_writes_the_habitat_in_another_case_or_spacing_agrees(tmp_path):
    run = second_reader_writes(agreed_record(tmp_path), f"habitat: {HABITAT}", "habitat: SYNTHETIC  grass land")
    assert FLAG not in run.open_reasons and "habitat" not in flagged(run)
    assert lifted(run) == codes(LABEL_UNSETTLED, values_of(run))


def test_another_fields_agreed_value_is_lifted_as_before_where_a_reader_differs_on_it(tmp_path):
    """The condition is the Habitat's alone: rule A for every other field is PR #457's."""
    run = second_reader_writes(agreed_record(tmp_path), "Synthetic teaching garden", "Synthetic teaching gardem")
    assert f"{LABEL_UNSETTLED}:precise_location" not in run.open_reasons and "precise_location" not in flagged(run)
    assert lifted(run) == codes(LABEL_UNSETTLED, values_of(run))


def test_a_reader_differing_elsewhere_on_the_label_leaves_the_agreed_habitat_unflagged(tmp_path):
    """The three right records of the rerun that gained the label's reason (105527218, 105527231, 105527247): their
    readers differ on other lines of the host's label and write the host alike. No flag on the Habitat."""
    run = second_reader_writes(agreed_record(tmp_path), "collection_method: Synthetic net",
        "collection_method: Synthetic met")
    assert FLAG not in run.open_reasons and "habitat" not in flagged(run)
