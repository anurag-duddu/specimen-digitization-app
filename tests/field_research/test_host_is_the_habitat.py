"""A host the label writes is the Habitat, as written (lane H4 of the autonomy program, 2026-11-21).

The coordinator's ruling for the lane (the coordinator's, not the owner's): the habitat expert answers a label's
host as the Habitat value, whole across its lines, a written "Ex."/"Ex:"/"ex"/"On" kept and a "Host" heading left
out, under the repository's own written requirement (prompts/habitat.txt line 1 and the ontology's habitat row: "The
habitat, host or substrate the label writes"). Only the habitat expert's instructions and the acceptance code for
the habitat field change.

What the paid habitat-only rerun of 2026-11-21 measured on the 99 cleared records of the 100 truth slides
(~/specimen-golive/runs/autonomy-habitat-20261121; lane H4's free diagnosis of it, autonomy-program/H4/diagnosis.txt):
- 10 of the 13 newly resolved hosts that came out wrong were one line of a name the label writes over two: the
  acceptance check refused the whole name with a space for the line break (literal_not_in_reading) and with the
  line break (not_candidate), and accepted one line of it. The habitat now runs over consecutive lines as the
  precise location does (agreement.ACROSS_LINES).
- answers kept a "Host"/"HOST:" heading the brief told the expert to leave out. A habitat literal that starts with
  that heading is now refused (agreement.HOST_HEADING), never rewritten.

The label texts here are made up.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry
from test_first_pass_advice import with_units
from test_step import COLLECTORS, TEXT, Scripted, answering, build_rig, field_checks, settle

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.application.integrity import verify_evidence
from specimen_digitization.field_research import agreement, experts
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FIELD_TOOLS, FieldAnswer, FieldTask, Reading
from specimen_digitization.field_research.prompts import FIELD_LABELS, instructions

# A determination label that writes its host under a printed heading, the genus above the species.
HOST_LABEL = "Synthetic Museum\nAus bus\ndet: J. Smith\nHost:\nMus\nmusculus\nAlc. Skin Fresh"
HOST_LINES = "Mus\nmusculus"
# One that breaks the host's name with a hyphen at the line's end, after a written marker.
BROKEN_LABEL = "Synthetic Museum\nEX: SYLVI-\nLAGUS SP.\nLOC: Synthetic Co."
BROKEN_LINES = "EX: SYLVI-\nLAGUS SP."


def two_readers_of(first, second):
    return with_units((Reading("2A", "label2", "obs2a", "raw_reading", first),
        Reading("2B", "label2", "obs2b", "raw_reading", second)))


def habitat_expert(readings):
    task = FieldTask("habitat", False, FieldValue(), (), ())
    return experts._Expert(task, readings, SimpleNamespace(sources=()), None)


def resolved(literal, *names):
    return FieldAnswer(outcome="resolved", literal=literal, reading_names=list(names),
        explanation="The label writes this host.")


# ---- a host over consecutive lines ---------------------------------------------------------------------------

def test_the_habitat_runs_over_consecutive_lines_as_the_precise_location_does():
    assert agreement.ACROSS_LINES == frozenset({"precise_location", "habitat"})
    assert set(agreement.ACROSS_LINES_TEXT) == set(agreement.ACROSS_LINES)
    start = HOST_LABEL.index(HOST_LINES)
    assert agreement.written_runs("habitat", HOST_LABEL, HOST_LINES) == [(start, start + len(HOST_LINES))]
    # A word cut at either end is no run; every other field keeps one line.
    assert agreement.written_runs("habitat", HOST_LABEL, "Mus\nmusc") == []
    assert agreement.written_runs("collection_method", HOST_LABEL, HOST_LINES) == []
    assert agreement.written_runs("taxon", HOST_LABEL, HOST_LINES) == []


def test_a_space_for_a_hosts_line_break_is_the_text_the_readings_write():
    readings = two_readers_of(HOST_LABEL, HOST_LABEL.replace("Alc. Skin", "Alc.  Skin"))
    assert agreement.across_lines("habitat", readings, "Mus musculus") == HOST_LINES
    assert agreement.across_lines("taxon", readings, "Mus musculus") is None
    # Readers who break the lines at different words write no one text.
    other = HOST_LABEL.replace("Host:\nMus\nmusculus", "Host: Mus\nmusculus x")
    assert agreement.across_lines("habitat", two_readers_of(HOST_LABEL, other), "Host: Mus musculus") is None


def test_the_experts_check_takes_a_host_over_two_lines():
    """The rerun's "<Genus>" for "<Genus>" over "<species>": the whole name was refused both ways. Given with a
    space for the line break, or with the line break, it is now the text both readers write."""
    readings = two_readers_of(HOST_LABEL, HOST_LABEL)
    for given in ("Mus musculus", HOST_LINES):
        checked = habitat_expert(readings).validate(resolved(given, "2A", "2B"))
        assert (checked.literal, checked.reading_names) == (HOST_LINES, ["2A", "2B"])
    # The first line alone still passes the check: only the brief tells the expert to copy the name whole.
    assert habitat_expert(readings).validate(resolved("Mus", "2A", "2B")).literal == "Mus"


def test_a_host_broken_by_a_hyphen_keeps_its_hyphen_and_its_written_marker():
    readings = two_readers_of(BROKEN_LABEL, BROKEN_LABEL)
    for given in ("EX: SYLVI- LAGUS SP.", BROKEN_LINES):
        assert habitat_expert(readings).validate(resolved(given, "2A", "2B")).literal == BROKEN_LINES
    # The word joined, as no reading writes it, is refused, and the expert is told how such a text is copied.
    with pytest.raises(ModelRetry, match="A host or a habitat written over consecutive lines is copied") as refused:
        habitat_expert(readings).validate(resolved("EX: SYLVILAGUS SP.", "2A", "2B"))
    assert refused.value.check == "literal_not_in_reading"


def test_readers_who_write_the_hosts_lines_differently_are_refused_the_whole_name():
    """One reader's species is a letter off: no one text over the two lines, so the answer naming both is refused."""
    readings = two_readers_of(HOST_LABEL, HOST_LABEL.replace("musculus", "muscalus"))
    with pytest.raises(ModelRetry, match="consecutive lines"):
        habitat_expert(readings).validate(resolved("Mus musculus", "2A", "2B"))


def test_the_precise_locations_own_words_to_its_expert_are_unchanged():
    """The two sentences the precise location's expert is told keep their wording byte for byte."""
    text = "CNHM. E Slope Mt.\nSynthetic, Davao Prov."
    readings = two_readers_of(text, text)
    task = FieldTask("precise_location", False, FieldValue(), (), ("geolocate",))
    made = experts._Expert(task, readings, SimpleNamespace(sources=("geolocate",)), None)
    with pytest.raises(ModelRetry) as refused:
        made.validate(resolved("E Slope Mt. Other, Davao Prov.", "2A"))
    assert str(refused.value.message).endswith(" A locality written over consecutive lines is copied with its line "
        "breaks (or a space for each), and every reading you name writes it the same way.")
    cut = agreement.literal_refusal(task, readings, literal="Slope Mt.\nSynth", named=[readings[0]])
    assert ("A locality written over consecutive lines may run over them: copy those lines as the reading writes "
        "them, holding whole candidates in their order on the label and cutting none. ") in cut.retry
    habitat = agreement.literal_refusal(FieldTask("habitat", False, FieldValue(), (), ()), readings,
        literal="Slope Mt.\nSynth", named=[readings[0]])
    assert "A host or a habitat written over consecutive lines may run over them: " in habitat.retry


# ---- the "Host" heading ----------------------------------------------------------------------------------------

@pytest.mark.parametrize(("literal", "heading"), [
    ("Host Mus", True), ("HOST: mus", True), ("Host:Mus", True), ("(host) Mus", True), ("Host", True),
    ("Host:\nMus\nmusculus", True),
    ("Mus", False), ("Ex. Mus musculus", False), ("ex Mus", False), ("On Mus", False), ("Hosts Mus", False),
    ("Hostel garden", False), ("on host Mus", False), ("", False), (None, False),
])
def test_a_text_that_starts_with_the_heading_host(literal, heading):
    assert agreement.host_heading(literal) is heading


def test_a_habitat_that_starts_with_the_host_heading_is_refused_and_never_rewritten():
    """The rerun's "Host: <GENUS>" and "HOST: <name>": the expert is sent back; the name alone, and the name after
    a written "Ex.", pass."""
    label = "Synthetic Museum\nHOST: mouse\nEx. Mus musculus\nLOC: Synthetic Co."
    readings = two_readers_of(label, label)
    with pytest.raises(ModelRetry, match="leave the heading out") as refused:
        habitat_expert(readings).validate(resolved("HOST: mouse", "2A", "2B"))
    assert refused.value.check == "host_heading"
    assert field_step.refusal_code(agreement.HOST_HEADING) == "host_heading"
    assert habitat_expert(readings).validate(resolved("mouse", "2A", "2B")).literal == "mouse"
    assert habitat_expert(readings).validate(resolved("Ex. Mus musculus", "2A", "2B")).literal == "Ex. Mus musculus"
    # Only the habitat has this rule: the same text passes this check for another field no source checks.
    other = FieldTask("collection_method", False, FieldValue(), (), ())
    assert agreement.literal_refusal(other, readings, literal="HOST: mouse", named=list(readings)) is None
    refusal = agreement.literal_refusal(FieldTask("habitat", False, FieldValue(), (), ()), readings,
        literal="HOST: mouse", named=list(readings))
    assert refusal.reason == agreement.HOST_HEADING and not refusal.differ


# ---- through the step ----------------------------------------------------------------------------------------

HOST_TEXT = TEXT.replace("habitat: Synthetic grassland\n", "Host:\nMus\nmusculus\n")
HEADED_TEXT = TEXT.replace("habitat: Synthetic grassland\n", "Host: Mus\n")


def test_both_readers_two_line_host_settles_the_habitat_through_the_step(tmp_path):
    """Both readers write the host over two lines under its heading and the answer gives a space for the line
    break: the Habitat is the readers' text with its line break, the heading left out; its rows and lineage pass
    the field checks and the evidence check. On origin/main 3eb37c11 it is unresolved (the literal is in no
    reading)."""
    rig = build_rig(tmp_path, HOST_TEXT, HOST_TEXT, candidates=COLLECTORS)
    run = rig.specimen.run
    settle(rig, Scripted({"habitat": answering(resolved("Mus musculus", "1A", "1B"))}))
    value = run.fields["habitat"]
    assert (value.state, value.literal, value.layer) == (ValueState.SUPPORTED, HOST_LINES, "verbatim")
    rows = {row.id: row for row in run.evidence}
    assert [rows[i].excerpt for i in value.evidence_ids if rows[i].kind == "literal"] == [HOST_LINES, HOST_LINES]
    assert field_checks(run, {"habitat"}) == []
    verify_evidence(rig.specimen, rig.blobs)


def test_the_step_refuses_a_habitat_answer_that_starts_with_the_heading(tmp_path):
    """The step repeats the check (agreement.refusal through step._refusal): an answer that starts with the
    heading leaves the Habitat unresolved, its reason saying why, and no value. On origin/main it settles
    "Host: Mus"."""
    rig = build_rig(tmp_path, HEADED_TEXT, HEADED_TEXT, candidates=COLLECTORS)
    run = rig.specimen.run
    settle(rig, Scripted({"habitat": answering(resolved("Host: Mus", "1A", "1B"))}))
    value = run.fields["habitat"]
    assert value.state == ValueState.UNRESOLVED and value.literal is None
    assert value.reason.startswith(agreement.HOST_HEADING)


def test_the_name_after_the_heading_settles_through_the_step(tmp_path):
    rig = build_rig(tmp_path, HEADED_TEXT, HEADED_TEXT, candidates=COLLECTORS)
    run = rig.specimen.run
    settle(rig, Scripted({"habitat": answering(resolved("Mus", "1A", "1B"))}))
    assert (run.fields["habitat"].state, run.fields["habitat"].literal) == (ValueState.SUPPORTED, "Mus")


# ---- a record researched before the change --------------------------------------------------------------------

def test_a_finalize_alone_leaves_a_stored_habitat_as_it_is(tmp_path):
    """A Habitat stored before the change, one that starts with the heading among them, is touched by no finalize:
    the acceptance check runs where an answer is applied (step.apply_outcomes), never in step.refinalize. (The
    stored runs of the 100 truth slides, replayed: ~/specimen-golive/autonomy-program/H4/replay_h4_v2.txt.)"""
    from test_step import TODAY

    rig = build_rig(tmp_path, HEADED_TEXT, HEADED_TEXT, candidates=COLLECTORS)
    run = rig.specimen.run
    settle(rig, Scripted({"habitat": answering(resolved("Mus", "1A", "1B"))}))
    stored = run.fields["habitat"]
    stored.literal = stored.parsed = "Host: Mus"
    before = stored.model_dump(mode="json")
    reasons = (list(run.reasons), list(run.open_reasons))
    field_step.refinalize(run, today=TODAY)
    assert run.fields["habitat"].model_dump(mode="json") == before
    assert (list(run.reasons), list(run.open_reasons)) == reasons


def test_research_asks_the_habitat_expert_again_only_where_the_habitat_is_no_settled_value(tmp_path):
    """Which stored records get the new instructions without a new run: a research attempt (a Retry that requeues
    field research, workflow.requeue_completed_field_research) makes a task for every field but a person's and one
    an earlier attempt settled (step.build_tasks). A settled Habitat, right or wrong, is not asked again; a blank or
    open one is. origin/main's rule, unchanged: pinned here because the release's effect on stored records rests on
    it."""
    rig = build_rig(tmp_path, HEADED_TEXT, HEADED_TEXT, candidates=COLLECTORS)
    run = rig.specimen.run
    settle(rig, Scripted({"habitat": answering(resolved("Mus", "1A", "1B"))}))
    assert run.fields["habitat"].state == ValueState.SUPPORTED
    assert "habitat" not in {task.key for task in field_step.build_tasks(run)[1]}
    for state in (ValueState.NOT_PRESENT, ValueState.UNRESOLVED, ValueState.AMBIGUOUS):
        run.fields["habitat"] = FieldValue(state=state)
        assert "habitat" in {task.key for task in field_step.build_tasks(run)[1]}, state


# ---- the habitat expert's instructions -----------------------------------------------------------------------

HOST_NOTATION = ('- "Host", "ex.", "on", "from": before a name, the specimen\'s host (associatedTaxa), never its taxon '
    "[no field].")
HOST_RULES = (
    "- A host is this field's value: ",
    "- A host is the name written after a host marker (",
    "- A host needs no marker. ",
    "- Copy the host whole, as the label writes it: ",
    "- A host or a habitat the label writes over consecutive lines (",
)


def test_only_the_habitat_brief_carries_the_host_rules_and_the_host_notation_is_unchanged():
    """The ontology's host notation ("[no field]") still stands in every expert's instructions: changing it would
    move 21 prompts. The habitat brief alone says what it means for this field."""
    brief = instructions("habitat").split(f"Field: {FIELD_LABELS['habitat']} (habitat)", 1)[1]
    lines = brief.splitlines()
    for rule in HOST_RULES:
        assert len([line for line in lines if line.startswith(rule)]) == 1, rule
        assert not [key for key in FIELD_TOOLS if key != "habitat" and rule in instructions(key)], rule
    assert all(instructions(key).count(HOST_NOTATION) == 1 for key in FIELD_TOOLS)
    # The lines the ontology cites by number keep their place (specimen.yaml: habitat.txt:1 and :4).
    file_lines = brief.strip().splitlines()
    assert file_lines[0].startswith(". The habitat, host or substrate the label writes")
    assert file_lines[3].startswith("- Take only text with ecological context")
    assert file_lines[-1] == "- When no reading writes a habitat, answer label_lacks_value."


def test_the_habitat_brief_states_each_point_of_the_ruling():
    brief = instructions("habitat").split(f"Field: {FIELD_LABELS['habitat']} (habitat)", 1)[1]
    is_value, marked, bare, whole, lines = (next(line for line in brief.splitlines() if line.startswith(rule))
        for rule in HOST_RULES)
    # The contradiction with the notation is resolved for this field in plain words.
    assert 'mark a host "[no field]" and "never its taxon"; for this field that means one thing only' in is_value
    assert "never answer label_lacks_value for a label that writes one" in is_value
    # A name after a marker, on its line or below it.
    assert marked.endswith("on the marker's line or on the lines right below it.")
    # A non-insect animal's name with no marker, wherever it stands. The second paid rerun's expert knew such
    # names for a mammal's and still answered label_lacks_value, for the three reasons the rule now names.
    assert "the specimens are insects, so the specimen's own taxon is an insect's name, never another animal's" in bare.replace(
        "The specimens", "the specimens")
    assert "a name you know for a mammal's, a bird's or another animal's that is no insect" in bare
    assert "is the host, wherever it stands on the labels" in bare
    assert "none of these is a reason to answer label_lacks_value: that no marker stands before it; that it reads like " \
        "the label's identification or taxon; that the units' fields advice or note, the organiser or other_fields " \
        "give it as the taxon or say that no field holds it" in bare
    # A name the expert cannot place is never guessed.
    assert "(an abbreviated genus you cannot expand with certainty, a word you do not know), do not guess" in bare
    assert bare.endswith("answer sources_cannot_resolve and quote it.")
    # Whole, the written marker kept, the heading left out, the value the literal itself.
    assert 'with a written "Ex.", "Ex:", "ex" or "On" before the name kept in the literal' in whole
    assert 'A heading "Host" or "Host:" before the name, in any letter case, is left out' in whole
    assert "an answer that starts with that heading is refused" in whole
    assert "The name stops before another field's text: a place, a date, a collector or a number on the next line" in whole
    assert "Never shorten the name to the part two readers write alike" in whole
    assert whole.endswith("Leave value and authority_id empty: this field's value is always the literal itself, never "
        "the name in another form (joined on one line, without its marker, in another letter case).")
    # Over consecutive lines, against the shared rule.
    assert "may run over them, whatever the shared rules say of two lines" in lines
    assert "with each line break (or a space for each) and the hyphen where the label breaks a word" in lines
    assert lines.endswith("Never answer the first line alone of a name the label goes on with on the next.")
    # Patterns only (test_experts.test_no_brief_gives_an_example_a_model_could_take_for_label_text covers names).
    assert '"<Genus>" over "<species>"' in lines and '"Ex. <name>"' in marked and '"<Genus> <species>"' in bare
