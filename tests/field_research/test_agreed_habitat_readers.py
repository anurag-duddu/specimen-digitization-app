"""An agreed Habitat keeps its label's flag where a reading of that label does not hold the value's text (lane H4 of
the autonomy program, 2026-11-21; the coordinator's ruling on the second paid habitat rerun, not the owner's words).

PR #457's rule A (second_opinion.agreed, unflagged) lifts `label_unsettled:<field>` from a value the second opinion
agrees with. In the rerun (~/specimen-golive/runs/autonomy-habitat2-20261121) truth slide 105527313's two readers
wrote a host's species differently, the first pass named one reader's text, the second opinion gave that same text,
and rule A lifted the flag from a Habitat the truth sheet reads otherwise: the one wrong Habitat of the run with no
flag. For Habitat (second_opinion.READERS_MUST_WRITE) the lift now needs every reading of the labels the value rests
on to hold the value's text as whole words somewhere in it, letter case and spacing aside (agreement.reader_writes).

What the condition compares, as the code has it (round 1 of #464's review; the cases below pin each):
- the readings are step.run_readings' on the labels the value rests on: a label's decided transcript and each raw
  reading with text; a reader's observation with no text is no reading and takes no part, so the condition is then
  judged on the other readings alone (a limit: the run says one reader read a label by the observations' routes and
  models, not by their text);
- the text is looked for anywhere in the reading, not at the Habitat's place: a reading that writes another text for
  the Habitat and holds the value's text on another line of the label counts as writing it (a known limit);
- letter case, spaces and line breaks are left aside on both sides, by agreement_key's own steps (NFC, casefold);
  a hyphen or another punctuation mark more or less inside the text is another text, so a reader who breaks a word
  with a hyphen at a line's end, where the value has none, keeps the flag.

Measured free on that run's 99 answers (autonomy-program/H4/flag_rule.txt): one flag gained, on that record; none on
its 44 right Habitats; none on the stored records; no other field's flag, no reason and no disposition moved.

The records are test_agreed_no_flag's (the field research rig through the workflow, the second opinion's step mounted
with a scripted model). A reader's text is changed on the finished record and the record finalized again: the rule is
derived from the run as it is at each finalize.
"""

from __future__ import annotations

import pytest
from test_agreed_no_flag import (
    AHEAD,
    LABEL_UNSETTLED,
    ONE_READER,
    answer_of,
    coded,
    codes,
    flagged,
    lifted,
    published,
    rig_of,
    to_end,
    values_of,
)
from test_second_opinion import Opinion
from test_step import SMITH_OR_SMYTH, SMYTH, TEXT, TODAY, Scripted, answering, build_rig, every_field, mounted
from test_step import resolved as answered

from specimen_digitization.application.domain import ValueState
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


# ---- both sides folded the same way (round 1 of #464's review) -------------------------------------------------

# Three letters whose folded form (str.casefold) is longer than the letter, each pinned by its code point: the sharp
# s, the capital I with a dot above, the ligature fi. On 3df404ea the literal was folded and the reading was not, so
# a reading did not write its own text. (No claim about any other letter: the Unicode tables differ by Python.)
FOLDS_LONGER = {"U+00DF": f"Stra{chr(0x00DF)}enrand", "U+0130": f"{chr(0x0130)}zmir yolu", "U+FB01": f"{chr(0xFB01)}eld edge"}


@pytest.mark.parametrize("words", FOLDS_LONGER.values(), ids=FOLDS_LONGER)
def test_a_reading_writes_its_own_text_whatever_its_letters_fold_to(words):
    text = f"habitat: Synthetic {words}\nleg. J. Smith"
    assert len(words.casefold()) > len(words)
    assert agreement.reader_writes(text, f"Synthetic {words}")
    assert agreement.reader_writes(text.upper(), f"Synthetic {words}") and agreement.reader_writes(text, words.upper())
    assert not agreement.reader_writes(text.replace(words, words + "x"), f"Synthetic {words}")


@pytest.mark.parametrize(("text", "literal", "writes"), [
    # The same words with the line break at another place, or none: the same text.
    ("Eastern\ncotton tail", "Eastern cotton\ntail", True),
    ("Eastern cotton tail", "Eastern cotton\ntail", True),
    ("Eastern cottontail", "Eastern cotton\ntail", True),
    # A hyphen that breaks a word at a line's end is a mark more: another text, either way round.
    ("EX: SYLVI-\nLAGUS SP.", "EX: SYLVILAGUS SP.", False),
    ("EX: SYLVILAGUS SP.", "EX: SYLVI-\nLAGUS SP.", False),
    ("EX: SYLVI-LAGUS SP.", "EX: SYLVI-\nLAGUS SP.", True),
    # Anywhere in the reading: the value's word on the locality's line.
    ("habitat: Coyole\nprecise_location: Coyote Creek", "Coyote", True),
    ("", "Coyote", False),
])
def test_what_counts_as_another_text(text, literal, writes):
    assert agreement.reader_writes(text, literal) is writes


def record_writing(tmp_path, habitat):
    """The agreed record with `habitat` as both readers' Habitat text, through the workflow: the readers differ on
    the collectors alone and the second opinion agrees with every settled value."""
    old = "Synthetic grassland"

    def build(folder, opinion):
        candidates = [item if item[0] != "habitat" else (item[0], item[1], habitat, item[3].replace(old, habitat))
            for item in every_field(*SMITH_OR_SMYTH)]
        rig = build_rig(folder, TEXT.replace(old, habitat), SMYTH.replace(old, habitat), candidates=candidates,
            profile=published())
        mounted(rig, Scripted({"collectors": answering(answered("J. Smith")), "habitat": answering(answered(habitat))}))
        rig.workflow.second_opinion = None if opinion is None else so.SecondOpinionStep(model_factory=opinion.factory)
        coded(rig)
        rig.clock.now = AHEAD
        return rig

    first = to_end(build(tmp_path / "unjudged", None)).run
    values = {key: so.shown(value) for key, value in first.fields.items() if value.state == ValueState.SUPPORTED}
    answer = {key: {"value": values.get(key), "evidence": "L1: synthetic" if values.get(key) else ""}
        for key in so.FIELDS}
    return to_end(build(tmp_path / "judged", Opinion(answer))).run


@pytest.mark.parametrize("words", FOLDS_LONGER.values(), ids=FOLDS_LONGER)
def test_an_agreed_habitat_both_readers_write_alike_loses_its_flag_whatever_its_letters(tmp_path, words):
    """Both readers write the same Habitat, which holds such a letter; the label's doubt is open on the collectors'
    line; the second opinion agrees. No flag on the Habitat, as on origin/main 3eb37c11. On 3df404ea the flag was
    kept (the run-the-code reviewer's case)."""
    habitat = f"Synthetic {words}"
    run = record_writing(tmp_path, habitat)
    assert run.fields["habitat"].literal == habitat
    assert run.second_opinion["fields"]["habitat"]["verdict"] == so.AGREES_VERDICT
    assert FLAG not in run.open_reasons and "habitat" not in flagged(run)
    assert f"{LABEL_UNSETTLED}:precise_location" not in run.open_reasons


# ---- the constructed cases, decided (round 1 of #464's review) -------------------------------------------------

@pytest.mark.parametrize(("second", "kept"), [
    ("habitat: SYNTHETIC GRASSLAND", False),           # letter case
    ("habitat: Synthetic\ngrassland", False),          # a line break where the value has a space
    ("habitat: Syn thetic grassland", False),          # a space the value does not have
    ("habitat: Synthetic grassland.", False),          # a mark after the text is no part of it
    ("habitat: Synthetic grass-\nland", True),         # a hyphen at a line's end is a mark more: another text
    ("habitat: Synthetic grass-land", True),
], ids=["case", "line-break", "space", "full-stop-after", "hyphen-at-line-end", "hyphen"])
def test_which_differences_between_readers_keep_the_flag(tmp_path, second, kept):
    run = second_reader_writes(agreed_record(tmp_path), f"habitat: {HABITAT}", second)
    assert (FLAG in run.open_reasons, "habitat" in flagged(run)) == (kept, kept)


def test_the_value_text_on_another_line_of_the_label_counts_as_written_a_known_limit(tmp_path):
    """The run-the-code reviewer's case ("Coyole" for the host, "Coyote Creek" on the locality's line): the second
    reader writes another text for the Habitat, and the value's text stands on another line of that reader's
    reading. The condition looks for the text anywhere in the reading, so it sees no difference and the flag is
    lifted, as on origin/main 3eb37c11. A limit of the condition, stated in the plan; not a rule on places."""
    run = agreed_record(tmp_path)
    reader = run.observations[1]
    reader.literal_text = reader.literal_text.replace("verbatim_dts: Synthetic D/T/S", f"verbatim_dts: {HABITAT} D/T/S")
    run = second_reader_writes(run, f"habitat: {HABITAT}", "habitat: Synthetic grasslund")
    assert run.fields["habitat"].literal == HABITAT
    assert FLAG not in run.open_reasons and "habitat" not in flagged(run)


def test_a_reader_with_no_text_for_the_label_is_no_reading_and_takes_no_part(tmp_path):
    """A reader that did not read the label: its observation has no text, so it is no reading (step.run_readings)
    and takes no part: the condition is judged on the other readings alone, and here the Habitat's flag is lifted
    on the first reader's text, as on origin/main 3eb37c11. The run says one reader read a label (and rule A then
    lifts no value's flag, second_opinion.one_reader) only where the label's observations come from fewer than two
    routes or models, with or without text (step.scientific_reasons): a rule this lane leaves as it is. A limit,
    stated in the plan."""
    run = agreed_record(tmp_path)
    run.observations[1].literal_text = ""
    field_step.refinalize(run, today=TODAY)
    readings = field_step.run_readings(run)
    assert [reading.observation_id for reading in readings] == [run.observations[0].id]
    assert not so._a_reader_differs(run, "habitat", readings)
    assert not any(code.startswith(f"{ONE_READER}:") for code in [*run.reasons, *run.open_reasons])
    assert FLAG not in run.open_reasons and FLAG in lifted(run)
