"""The catalogue number settled on the slide's QR code (field_research/catalogue_code.py).

A step-level test builds its run with test_step.build_rig (one label, two readers, the
synthetic label's catalogue line "fmnh_ins_number: FMNH-INS 0010001") and gives it the
evidence row the segment step stores for a decoded code (application/barcode.record), written
out here as the row's fields so that each rule's test also runs, and fails, on the code before
the rule existed. Every rule test names what that code did instead."""

from __future__ import annotations

import pytest
from test_settlement_rule import findings, images
from test_step import (
    LABEL,
    TEXT,
    Scripted,
    a_second_label,
    answering,
    build_rig,
    reasons_for,
    resolved,
    settle,
)

from specimen_digitization.application.domain import Disposition, Evidence, ValueState
from specimen_digitization.application.reading_units import UNCERTAIN
from specimen_digitization.field_research.contracts import FieldAnswer

KEY = "fmnh_ins_number"
CODE = "0010001"
LINE = f"{KEY}: {LABEL[KEY]}"


def with_code(rig, payload=CODE, *, region=None):
    """The run's code row as barcode.record stores it: on label `region`, else on no label."""
    run = rig.specimen.run
    row = Evidence(kind="derived", asset_id=rig.specimen.asset.id, region_id=region, source="barcode",
        locator="check:barcode_decode",
        excerpt=f"{KEY}: {payload} (QR code read by zxing-cpp 3.1.1, ladder rung whole)")
    run.evidence.append(row)
    return row


def catalogue(literal, value, reading="1A"):
    return answering(resolved(literal, value=value, reading=reading))


def summary(run, key):
    value = run.fields[key]
    return (value.state, value.literal, value.parsed, value.normalized, value.layer)


# ---- rule 1: a reader writes the code's number -------------------------------------------------

def test_readers_that_agree_with_the_code_clear_where_the_image_names_nothing(tmp_path):
    """Both readers write the catalogue number, the image names nothing: readers agreeing alone
    back it, and before the rule it settled marked text_only. The code backs it as a source: cleared."""
    rig = build_rig(tmp_path)
    run = rig.specimen.run
    images(rig, lambda unit: UNCERTAIN)
    code = with_code(rig)
    settle(rig, Scripted())
    region = run.regions[0].id
    value = run.fields[KEY]
    assert findings(run, KEY) == [(f"cleared:{KEY}:{region}", "info")]
    assert not reasons_for(run, KEY) and "identifier_format" not in run.reasons
    assert (value.state, value.literal, value.parsed) == (ValueState.SUPPORTED, LABEL[KEY], CODE)
    assert value.evidence_relations.get(code.id) == "decides"
    assert value.reason.endswith(f"The slide's QR code reads {CODE}, which readers 1A and 1B wrote too.")


def test_one_reader_that_agrees_with_the_code_clears(tmp_path):
    """Only reader 1A writes the catalogue line; before the rule one reader backed nothing and
    the field went to review. The code backs 1A's number: cleared, its digits as 1A writes them,
    with 1A's lineage."""
    rig = build_rig(tmp_path, TEXT, TEXT.replace(LINE + "\n", ""))
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: catalogue(LABEL[KEY], CODE)}))
    value = run.fields[KEY]
    assert summary(run, KEY)[:3] == (ValueState.SUPPORTED, CODE, CODE)
    assert value.evidence_relations[code.id] == "decides"
    assert value.settled_observation_ids == [run.observations[0].id]
    assert not reasons_for(run, KEY) and "identifier_format" not in run.reasons


# ---- rule 2: a reader alone writes another number ---------------------------------------------

def test_a_reader_that_writes_another_number_is_ruled_out_and_noted(tmp_path):
    """1B writes 0010007. Before the rule the readers differed with nothing to decide them and
    the field was left open (mandatory_unresolved, identifier_format). The code holds 1A's
    number: it is the value, cleared, and 1B's reading is cited against it and named."""
    other = TEXT.replace(LINE, f"{KEY}: FMNH-INS 0010007")
    rig = build_rig(tmp_path, TEXT, other)
    run = rig.specimen.run
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue(LABEL[KEY], CODE)}))
    value = run.fields[KEY]
    assert summary(run, KEY)[:3] == (ValueState.SUPPORTED, CODE, CODE)
    contradicting = [run_row for run_row in run.evidence if value.evidence_relations.get(run_row.id) == "contradicts"]
    assert [(row.observation_ids, row.excerpt) for row in contradicting] == [
        ([run.observations[1].id], f"{KEY}: FMNH-INS 0010007")]
    assert value.reason.endswith(f"The slide's QR code reads {CODE}, which reader 1A wrote too. "
        "reader 1B wrote 0010007, which the code rules out.")
    ruled_out = [f for f in run.findings if f.field_key == KEY and f.rule_id == "barcode_decode"]
    assert [(f.reason_code, f.severity, f.evidence_ids) for f in ruled_out] == [
        (f"barcode_ruled_out:{KEY}", "info", [contradicting[0].id])]
    assert not reasons_for(run, KEY) and "identifier_format" not in run.reasons


def test_readers_that_each_write_another_number_give_the_codes_number(tmp_path):
    """1A writes 0010004 and 1B 0010007, the code 0010001: the code's number is the value, from
    the code alone (no reader's verbatim), and both readings are ruled out."""
    rig = build_rig(tmp_path, TEXT.replace(LINE, f"{KEY}: FMNH-INS 0010004"),
        TEXT.replace(LINE, f"{KEY}: FMNH-INS 0010007"))
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: catalogue("FMNH-INS 0010004", "0010004")}))
    value = run.fields[KEY]
    assert summary(run, KEY)[:3] == (ValueState.SUPPORTED, CODE, CODE)
    assert value.verbatim_by_observation == {} and value.source_observation_id is None
    assert sorted(how for how in value.evidence_relations.values()) == ["contradicts", "contradicts", "decides"]
    assert value.evidence_relations[code.id] == "decides"
    assert "reader 1A wrote 0010004; reader 1B wrote 0010007, which the code rules out." in value.reason
    assert not reasons_for(run, KEY) and "identifier_format" not in run.reasons


def test_a_number_the_image_named_wrong_is_replaced_by_the_codes(tmp_path):
    """The image names 1A's 0010004 and 1B wrote 0010007 (105526487's case in the last test:
    4486518 cleared for the code's 4486618). Before the rule the image cleared the wrong number."""
    rig = build_rig(tmp_path, TEXT.replace(LINE, f"{KEY}: FMNH-INS 0010004"),
        TEXT.replace(LINE, f"{KEY}: FMNH-INS 0010007"))
    run = rig.specimen.run
    images(rig, lambda unit: next(iter(unit.readers.values())).text)
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue("FMNH-INS 0010004", "0010004")}))
    assert summary(run, KEY)[:3] == (ValueState.SUPPORTED, CODE, CODE)


# ---- rule 3: readers that agree on another number ---------------------------------------------

def test_readers_that_agree_on_another_number_hold_the_field_for_a_person(tmp_path):
    """Both readers write 0010007 and the image names it, the code 0010001. Before the rule
    0010007 cleared. The code and the readers disagree: ambiguous, with its own reason."""
    written = TEXT.replace(LINE, f"{KEY}: FMNH-INS 0010007")
    rig = build_rig(tmp_path, written, written)
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: catalogue("FMNH-INS 0010007", "0010007")}))
    region = run.regions[0].id
    value = run.fields[KEY]
    assert value.state == ValueState.AMBIGUOUS
    assert value.reason == (f"The slide's QR code reads {CODE}, but readers 1A and 1B read 0010007. "
        f"The code and the readers disagree, so a person checks the label and its code. Options: {CODE}; 0010007.")
    assert code.id in value.evidence_ids
    assert findings(run, KEY) == [(f"marked:{KEY}:{region}:barcode_differs", "warning")]
    assert f"marked:{KEY}:{region}:barcode_differs" in run.reasons
    assert f"mandatory_unresolved:{KEY}" in run.reasons
    assert run.disposition == Disposition.REVIEW


# ---- rule 4: no reader writes a number --------------------------------------------------------

def test_a_label_no_reader_writes_a_number_on_takes_the_codes_number(tmp_path):
    """Neither reader writes the catalogue line; its expert answers label_lacks_value. Before the
    rule the field was not present and, as it may never be (NEVER_NOT_ON_LABEL), unresolved."""
    text = TEXT.replace(LINE + "\n", "")
    rig = build_rig(tmp_path, text, text)
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: answering(FieldAnswer(outcome="label_lacks_value",
        explanation="No reading prints a catalogue number."))}))
    value = run.fields[KEY]
    assert summary(run, KEY) == (ValueState.SUPPORTED, CODE, CODE, None, "settled")
    assert value.evidence_ids == [code.id] and value.evidence_relations == {code.id: "decides"}
    assert value.reason == f"The slide's QR code reads {CODE}."
    assert not reasons_for(run, KEY) and "identifier_format" not in run.reasons


# ---- the label the code lies on ---------------------------------------------------------------

@pytest.mark.parametrize("on_its_label", [True, False])
def test_numbers_count_on_the_codes_label_when_the_decode_places_it(tmp_path, monkeypatch, on_its_label):
    """Both readers of a second label write the number 0010009. The decode places the code on
    label 1: label 2's number is no reading of the code, and the catalogue number clears. A decode
    that places it on no label counts every label's numbers, and the agreeing 0010009 holds it."""
    a_second_label(monkeypatch, "lot 0010009")
    rig = build_rig(tmp_path)
    run = rig.specimen.run
    with_code(rig, region=run.regions[0].id if on_its_label else None)
    settle(rig, Scripted())
    assert run.fields[KEY].state == (ValueState.SUPPORTED if on_its_label else ValueState.AMBIGUOUS)
    assert bool(reasons_for(run, KEY)) is not on_its_label


# ---- controls ---------------------------------------------------------------------------------

def outcome(run):
    """What a person and the record's routing see: each field's value and reason, the findings
    and the reasons, without the ids a fresh run draws."""
    return ({key: (*summary(run, key), value.reason, sorted(value.evidence_relations.values()))
        for key, value in run.fields.items()},
        sorted((f.rule_id, f.reason_code.replace(run.regions[0].id, "L1"), f.severity) for f in run.findings),
        [reason.replace(run.regions[0].id, "L1") for reason in run.reasons], run.disposition)


SCENARIOS = {
    "readers-agree": (TEXT, None, None),
    "readers-differ": (TEXT, TEXT.replace(LINE, f"{KEY}: FMNH-INS 0010007"), catalogue(LABEL[KEY], CODE)),
    "no-number": (TEXT.replace(LINE + "\n", ""), TEXT.replace(LINE + "\n", ""), answering(FieldAnswer(
        outcome="label_lacks_value", explanation="No reading prints a catalogue number."))),
}


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_a_run_with_no_code_row_settles_exactly_as_without_the_rule(tmp_path, monkeypatch, scenario):
    """No stored decode: the rule changes nothing, whatever the readers write."""
    from specimen_digitization.field_research import catalogue_code

    text, other, script = SCENARIOS[scenario]
    scripts = {KEY: script} if script else {}
    plain = build_rig(tmp_path / "plain", text, other)
    settle(plain, Scripted(scripts))
    monkeypatch.setattr(catalogue_code, "settle", lambda *args, **kwargs: False)
    without = build_rig(tmp_path / "without", text, other)
    settle(without, Scripted(scripts))
    assert outcome(plain.specimen.run) == outcome(without.specimen.run)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_code_changes_no_other_field(tmp_path, scenario):
    """With a code row the catalogue number may change; every other field, its findings and its
    reasons are as they are with no code row."""
    text, other, script = SCENARIOS[scenario]
    scripts = {KEY: script} if script else {}
    plain = build_rig(tmp_path / "plain", text, other)
    settle(plain, Scripted(scripts))
    coded = build_rig(tmp_path / "coded", text, other)
    with_code(coded)
    settle(coded, Scripted(scripts))
    fields, found, reasons, _ = outcome(plain.specimen.run)
    fields_coded, found_coded, reasons_coded, _ = outcome(coded.specimen.run)
    assert {k: v for k, v in fields.items() if k != KEY} == {k: v for k, v in fields_coded.items() if k != KEY}
    assert [f for f in found if KEY not in f[1]] == [f for f in found_coded if KEY not in f[1]]
    other_reasons = [r for r in reasons if KEY not in r and r != "identifier_format"]
    assert other_reasons == [r for r in reasons_coded if KEY not in r and r != "identifier_format"]


def test_a_code_row_on_a_run_of_the_old_path_changes_nothing(tmp_path, monkeypatch):
    """A run of the old first pass (moved runs keep it until the workflow moves them) is not
    settled on the code; catalogue_code.settle is never asked."""
    from specimen_digitization.field_research import catalogue_code

    asked = []
    monkeypatch.setattr(catalogue_code, "settle", lambda *args, **kwargs: asked.append(args) or False)
    rig = build_rig(tmp_path)
    with_code(rig)
    from specimen_digitization.field_research import step as field_step

    monkeypatch.setattr(field_step, "units_path", lambda run: False)
    settle(rig, Scripted())
    assert asked == []


def test_the_hold_code_is_the_one_the_app_words():
    """The app words this exact code (the client's blockers.dart barcodeDiffersWords and
    settlement_codes.dart markedReasonWords; its barcode_differs_test.dart). Pinned here as a plain
    string, never by reading the app's files."""
    from specimen_digitization.field_research import catalogue_code
    from specimen_digitization.field_research.step import marked_code

    assert catalogue_code.DIFFERS == "barcode_differs"
    assert marked_code(KEY, "L1", catalogue_code.DIFFERS) == "marked:fmnh_ins_number:L1:barcode_differs"


def test_the_one_reader_of_the_number_writing_another_is_ruled_out_and_both_numbers_are_shown(tmp_path):
    """Only reader 1A writes a catalogue number, 0010007; 1B writes none; the code holds 0010001.
    The code's number is the value, 1A's reading is cited against it, and the reason a reviewer
    reads names both numbers."""
    rig = build_rig(tmp_path, TEXT.replace(LINE, f"{KEY}: FMNH-INS 0010007"), TEXT.replace(LINE + "\n", ""))
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: catalogue("FMNH-INS 0010007", "0010007")}))
    value = run.fields[KEY]
    assert summary(run, KEY)[:3] == (ValueState.SUPPORTED, CODE, CODE)
    rows = {row.id: row for row in run.evidence}
    assert value.evidence_relations[code.id] == "decides" and CODE in rows[code.id].excerpt
    [against] = [rows[i] for i, how in value.evidence_relations.items() if how == "contradicts"]
    assert "0010007" in against.excerpt and against.observation_ids == [run.observations[0].id]
    assert value.reason.endswith(
        f"The slide's QR code reads {CODE}. reader 1A wrote 0010007, which the code rules out.")
    assert not reasons_for(run, KEY)
