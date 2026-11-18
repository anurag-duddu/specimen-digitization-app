"""The catalogue number settled on the slide's QR code (field_research/catalogue_code.py).

A step-level test builds its run with test_step.build_rig, with the synthetic label's catalogue
line moved to a barcode label of its own (label 2, read by readers 2A and 2B), as on the real
slides, and gives it the evidence row the segment step stores for a decoded code
(application/barcode.record) on that label. The row is written out here as its fields so that
each rule's test also runs, and fails, on the code before the rule existed. Every rule test
names what that code did instead."""

from __future__ import annotations

import hashlib
import io
import sys

import pytest
import test_step as rig_module
from PIL import Image
from test_settlement_rule import findings
from test_step import (
    LABEL,
    TEXT,
    Scripted,
    answering,
    build_rig,
    reasons_for,
    resolved,
    settle,
)

from specimen_digitization.application.domain import Disposition, Evidence, Observation, Region, ValueState
from specimen_digitization.application.reading_units import UNCERTAIN
from specimen_digitization.application.region_pixels import region_png
from specimen_digitization.application.workflow import store_reading_units
from specimen_digitization.field_research.contracts import FieldAnswer

KEY = "fmnh_ins_number"
CODE = "0010001"
LINE = f"{KEY}: {LABEL[KEY]}\n"
# Label 1: the synthetic label without its catalogue line.
FIRST = TEXT.replace(LINE, "")
PRINTED = "FMNHINS\n0010001"


def barcode_label(monkeypatch, *texts):
    """build_rig's specimen with a barcode label (label 2) whose readers read `texts`, one per
    route; a reader with no text of its own reads the first."""
    original = rig_module.make_specimen

    def make(blobs, first=FIRST, other=None):
        specimen = original(blobs, first, other)
        run = specimen.run
        output = io.BytesIO()
        Image.new("RGB", (100, 100), "white").save(output, format="JPEG", quality=95)
        region = Region(asset_id=specimen.asset.id, x=0, y=50, width=100, height=50, order=1,
            method="synthetic_fixture_region", version="1")
        crop_png = region_png(Image.open(io.BytesIO(output.getvalue())), region)
        region.crop_ref = blobs.put(crop_png)
        run.regions.append(region)
        crop = hashlib.sha256(crop_png).hexdigest()
        for index, route in enumerate(run.profile.routes):
            text = texts[index] if index < len(texts) else texts[0]
            raw = ("SYNTHETIC FIXTURE " + route + "\n" + text).encode()
            run.observations.append(Observation(region_id=region.id, route_id=route, model_id="synthetic-" + route,
                provider="synthetic", prompt_version="prompt:" + route, input_sha256=crop,
                input_asset_id=specimen.asset.id, input_crop_ref=region.crop_ref, literal_text=text,
                raw_ref=blobs.put(raw), raw_sha256=hashlib.sha256(raw).hexdigest()))
            run.completed_steps.append(f"transcribe:{region.id}:{route}")
        return specimen

    monkeypatch.setattr(sys.modules[rig_module.__name__], "make_specimen", make)


def rig_with(tmp_path, monkeypatch, *texts):
    barcode_label(monkeypatch, *texts)
    return build_rig(tmp_path, FIRST)


def with_code(rig, payload=CODE, *, region=1):
    """The run's code row as barcode.record stores it, on label `region` (an index; None for none)."""
    run = rig.specimen.run
    row = Evidence(kind="derived", asset_id=rig.specimen.asset.id,
        region_id=None if region is None else run.regions[region].id, source="barcode",
        locator="check:barcode_decode",
        excerpt=f"{KEY}: {payload} (QR code read by zxing-cpp 3.1.1, ladder rung whole)")
    run.evidence.append(row)
    return row


def uncertain(rig):
    """The barcode label's units with the image uncertain at every unit."""
    run = rig.specimen.run
    [entry] = [entry for entry in run.reading_units if entry.label == run.regions[1].id]
    store_reading_units(run, [entry.model_copy(update={"units": [
        unit.model_copy(update={"image": UNCERTAIN}) for unit in entry.units]})])


def catalogue(literal, value, reading="2A"):
    return answering(resolved(literal, value=value, reading=reading))


LACKS = answering(FieldAnswer(outcome="label_lacks_value", explanation="No reading prints a catalogue number."))


def summary(run, key):
    value = run.fields[key]
    return (value.state, value.literal, value.parsed, value.normalized, value.layer)


def contradicting(run):
    rows = {row.id: row for row in run.evidence}
    return sorted(rows[i].excerpt for i, how in run.fields[KEY].evidence_relations.items() if how == "contradicts")


# ---- rule 1: a reader writes the code's number -------------------------------------------------

def test_readers_that_agree_with_the_code_clear_where_the_image_names_nothing(tmp_path, monkeypatch):
    """Both readers write the catalogue number, the image names nothing: readers agreeing alone
    back it, and before the rule it settled marked text_only. The code backs it as a source: cleared."""
    rig = rig_with(tmp_path, monkeypatch, PRINTED)
    run = rig.specimen.run
    uncertain(rig)
    code = with_code(rig)
    settle(rig, Scripted({KEY: catalogue(CODE, CODE)}))
    value = run.fields[KEY]
    assert findings(run, KEY) == [(f"cleared:{KEY}:{run.regions[1].id}", "info")]
    assert not reasons_for(run, KEY) and "identifier_format" not in run.reasons
    assert (value.state, value.literal) == (ValueState.SUPPORTED, CODE)
    assert value.evidence_relations.get(code.id) == "decides"
    assert value.reason.endswith(f"The slide's QR code reads {CODE}, which readers 2A and 2B wrote too.")


def test_one_reader_that_agrees_with_the_code_clears(tmp_path, monkeypatch):
    """Only reader 2A writes the number; 2B's text holds no digit. Before the rule one reader
    backed nothing and the field went to review. The code backs 2A's number, with its lineage."""
    rig = rig_with(tmp_path, monkeypatch, PRINTED, "FMNHINS")
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: catalogue(CODE, CODE)}))
    value = run.fields[KEY]
    assert summary(run, KEY)[:3] == (ValueState.SUPPORTED, CODE, CODE)
    assert value.evidence_relations[code.id] == "decides"
    assert value.settled_observation_ids == [run.observations[2].id]
    assert not reasons_for(run, KEY) and "identifier_format" not in run.reasons


def test_readers_that_space_the_codes_number_clear(tmp_path, monkeypatch):
    """Both readers write "001 0007"-style spacing of the code's own number ("001 0001"): the
    digits joined across the space are the code's number, so the code backs them: cleared, the
    literal as the readers write it, the value the seven digits."""
    rig = rig_with(tmp_path, monkeypatch, "FMNHINS 001 0001")
    run = rig.specimen.run
    uncertain(rig)
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue("001 0001", CODE)}))
    assert summary(run, KEY)[:3] == (ValueState.SUPPORTED, "001 0001", CODE)
    assert not reasons_for(run, KEY) and "identifier_format" not in run.reasons


# ---- rule 2: a reader alone writes another number ---------------------------------------------

def test_a_reader_that_writes_another_number_is_ruled_out_and_noted(tmp_path, monkeypatch):
    """2B writes 0010007. Before the rule the readers differed with nothing to decide them and
    the field was left open (mandatory_unresolved, identifier_format). The code holds 2A's
    number: it is the value, cleared, and 2B's reading is cited against it and named."""
    rig = rig_with(tmp_path, monkeypatch, PRINTED, "FMNHINS\n0010007")
    run = rig.specimen.run
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue(CODE, CODE)}))
    value = run.fields[KEY]
    assert summary(run, KEY)[:3] == (ValueState.SUPPORTED, CODE, CODE)
    assert contradicting(run) == ["0010007"]
    assert value.reason.endswith(f"The slide's QR code reads {CODE}, which reader 2A wrote too. "
        "reader 2B wrote 0010007, which the code rules out.")
    ruled_out = [f for f in run.findings if f.field_key == KEY and f.rule_id == "barcode_decode"]
    assert [(f.reason_code, f.severity) for f in ruled_out] == [(f"barcode_ruled_out:{KEY}", "info")]
    assert not reasons_for(run, KEY) and "identifier_format" not in run.reasons


def test_readers_that_each_write_another_number_give_the_codes_number(tmp_path, monkeypatch):
    """2A writes 0010004 and 2B 0010007, the code 0010001: the code's number is the value, from
    the code alone (no reader's verbatim), and both readings are ruled out."""
    rig = rig_with(tmp_path, monkeypatch, "FMNHINS\n0010004", "FMNHINS\n0010007")
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: catalogue("0010004", "0010004")}))
    value = run.fields[KEY]
    assert summary(run, KEY)[:3] == (ValueState.SUPPORTED, CODE, CODE)
    assert value.verbatim_by_observation == {} and value.source_observation_id is None
    assert value.evidence_relations[code.id] == "decides"
    assert contradicting(run) == ["0010004", "0010007"]
    assert "reader 2A wrote 0010004; reader 2B wrote 0010007, which the code rules out." in value.reason
    assert not reasons_for(run, KEY) and "identifier_format" not in run.reasons


def test_a_number_the_image_named_wrong_is_replaced_by_the_codes(tmp_path, monkeypatch):
    """The image names 2A's 0010004 and 2B wrote 0010007 (105526487's case in the last test:
    4486518 cleared for the code's 4486618). Before the rule the image cleared the wrong number."""
    rig = rig_with(tmp_path, monkeypatch, "FMNHINS\n0010004", "FMNHINS\n0010007")
    run = rig.specimen.run
    [entry] = [entry for entry in run.reading_units if entry.label == run.regions[1].id]
    store_reading_units(run, [entry.model_copy(update={"units": [
        unit.model_copy(update={"image": next(iter(unit.readers.values())).text}) for unit in entry.units]})])
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue("0010004", "0010004")}))
    assert summary(run, KEY)[:3] == (ValueState.SUPPORTED, CODE, CODE)


def test_the_one_reader_of_the_number_writing_another_is_ruled_out_and_both_numbers_are_shown(
        tmp_path, monkeypatch):
    """Only reader 2A writes a number, 0010007; 2B writes none. The code's number is the value,
    2A's reading is cited against it, and the reason a reviewer reads names both numbers."""
    rig = rig_with(tmp_path, monkeypatch, "FMNHINS\n0010007", "FMNHINS")
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: catalogue("0010007", "0010007")}))
    value = run.fields[KEY]
    assert summary(run, KEY)[:3] == (ValueState.SUPPORTED, CODE, CODE)
    rows = {row.id: row for row in run.evidence}
    assert value.evidence_relations[code.id] == "decides" and CODE in rows[code.id].excerpt
    assert contradicting(run) == ["0010007"]
    assert value.reason.endswith(f"The slide's QR code reads {CODE}. reader 2A wrote 0010007, which the code rules out.")
    assert not reasons_for(run, KEY)


@pytest.mark.parametrize("written", ["FMNHINS\n001000", "FMNHINS\n00100017", "FMNHINS\n00I0001", "FMNHINS\n0010"])
def test_digits_one_reader_cannot_write_as_the_codes_number_are_a_disagreement(tmp_path, monkeypatch, written):
    """2B writes a six-digit partial, eight digits, a letter inside the number or four digits:
    never silence. Alone, it is ruled out and named; the code's number, which 2A wrote, clears."""
    rig = rig_with(tmp_path, monkeypatch, PRINTED, written)
    run = rig.specimen.run
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue(CODE, CODE)}))
    value = run.fields[KEY]
    assert summary(run, KEY)[:3] == (ValueState.SUPPORTED, CODE, CODE)
    assert contradicting(run)
    assert "reader 2B wrote" in value.reason and "which the code rules out." in value.reason
    assert not reasons_for(run, KEY)


# ---- rule 3: readers that agree on another number ---------------------------------------------

@pytest.mark.parametrize(("written", "read"), [
    ("FMNHINS\n0010007", "0010007"),
    # Spaced, or broken over two lines, as agreement_key joins readers' texts.
    ("FMNHINS 001 0007", "0010007"),
    ("FMNHINS\n001\n0007", "0010007"),
    # Leading zeros, or the prefix run into the digits (the G51 review's case).
    ("FMNHINS0000010007", "0000010007"),
    # The prefix misread: the digits still count.
    ("FNHNHNS 0010007", "0010007"),
    # A letter inside the number, or a partial: the digits both readers wrote still agree.
    ("FMNHINS 00l0007", "0007"),
    ("FMNHINS 001000", "001000"),
])
def test_readers_that_agree_on_other_digits_hold_the_field_for_a_person(tmp_path, monkeypatch, written, read):
    """Both readers write the same other digits, the code 0010001. Before the rule the readers'
    number cleared, or (where no contiguous number was read) the code's would have cleared
    silently. The code and the readers disagree: ambiguous, with its own reason."""
    rig = rig_with(tmp_path, monkeypatch, written)
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: catalogue(read, read)}))
    region = run.regions[1].id
    value = run.fields[KEY]
    assert value.state == ValueState.AMBIGUOUS
    assert value.reason == (f"The slide's QR code reads {CODE}, but readers 2A and 2B read {read}. "
        f"The code and the readers disagree, so a person checks the label and its code. Options: {CODE}; {read}.")
    assert code.id in value.evidence_ids
    assert findings(run, KEY) == [(f"marked:{KEY}:{region}:barcode_differs", "warning")]
    assert f"marked:{KEY}:{region}:barcode_differs" in run.reasons
    assert run.disposition == Disposition.REVIEW


# ---- rule 4: no reader writes a digit ---------------------------------------------------------

def test_a_label_no_reader_writes_a_digit_on_takes_the_codes_number(tmp_path, monkeypatch):
    """The barcode label's readers write the prefix and no digit; the expert answers
    label_lacks_value. Before the rule the field was not present and, as it may never be
    (NEVER_NOT_ON_LABEL), unresolved."""
    rig = rig_with(tmp_path, monkeypatch, "FMNHINS")
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: LACKS}))
    value = run.fields[KEY]
    assert summary(run, KEY) == (ValueState.SUPPORTED, CODE, CODE, None, "settled")
    assert value.evidence_ids == [code.id] and value.evidence_relations == {code.id: "decides"}
    assert value.reason == f"The slide's QR code reads {CODE}."
    assert not reasons_for(run, KEY) and "identifier_format" not in run.reasons


# ---- rule 0: a person outranks the code -------------------------------------------------------

def person_transcribes(rig, text):
    """The barcode label's transcript as a reviewer's decision leaves it (application/api.py; as
    test_first_pass_advice.person_transcribed does for label 1): the person's text, resolved,
    its units from that text (first_pass.source_units)."""
    from specimen_digitization.application.first_pass import source_units

    run = rig.specimen.run
    region = run.regions[1].id
    index = next(i for i, t in enumerate(run.transcripts) if t.region_id == region)
    run.transcripts[index] = run.transcripts[index].model_copy(update={"text": text, "resolved": True,
        "actor": "reviewer@example.org", "reason": "The label reads so.", "decision_kind": "human"})
    store_reading_units(run, [source_units(run, region)])


@pytest.mark.parametrize(("person", "literal", "state"), [
    # The person corrects the number to one no machine reader wrote.
    ("FMNHINS 0010007", "0010007", ValueState.SUPPORTED),
    # The person's text holds no number at all.
    ("FMNHINS", None, ValueState.NOT_PRESENT),
])
def test_a_persons_transcription_of_the_barcode_label_outranks_the_code(tmp_path, monkeypatch, person, literal,
        state):
    """A reviewer transcribes the barcode label, and research runs again on that decision. The
    code holds 0010001. A person's transcript binds its label (BY_PERSON): the field is what the
    person's text settles; the code overrules nothing and holds nothing, and only notes that it
    differs (at f1798d07 the code replaced the person's 0010007 with 0010001 and cleared it)."""
    rig = rig_with(tmp_path, monkeypatch, PRINTED)
    run = rig.specimen.run
    person_transcribes(rig, person)
    code = with_code(rig)
    script = catalogue(literal, literal) if literal else LACKS
    settle(rig, Scripted({KEY: script}))
    value = run.fields[KEY]
    assert (value.state, value.literal) == (state, literal)
    assert code.id not in value.evidence_relations
    assert not any(r.startswith(f"marked:{KEY}:") and r.endswith(":barcode_differs") for r in run.reasons)
    assert value.reason.endswith(f"The slide's QR code reads {CODE}; the person's transcription of the label "
        f"writes {'0010007' if literal else 'no number'}.")
    notes = [f for f in run.findings if f.field_key == KEY and f.rule_id == "barcode_decode"]
    assert [(f.reason_code, f.severity, f.evidence_ids) for f in notes] == [
        (f"barcode_person_differs:{KEY}", "info", [code.id])]


def test_a_persons_transcription_that_agrees_with_the_code_gets_no_note(tmp_path, monkeypatch):
    rig = rig_with(tmp_path, monkeypatch, "FMNHINS\n0010004")
    run = rig.specimen.run
    person_transcribes(rig, PRINTED)
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue(CODE, CODE)}))
    value = run.fields[KEY]
    assert (value.state, value.literal) == (ValueState.SUPPORTED, CODE)
    assert "QR code" not in value.reason
    assert not [f for f in run.findings if f.field_key == KEY and f.rule_id == "barcode_decode"]


# ---- the label the code lies on ---------------------------------------------------------------

def test_a_decode_placed_on_no_label_changes_nothing(tmp_path, monkeypatch):
    """A decode no label's box holds is no reading of any label: the field is as its expert left
    it (here the readers differ, so it stays open)."""
    rig = rig_with(tmp_path, monkeypatch, PRINTED, "FMNHINS\n0010007")
    run = rig.specimen.run
    with_code(rig, region=None)
    settle(rig, Scripted({KEY: catalogue(CODE, CODE)}))
    assert run.fields[KEY].state != ValueState.SUPPORTED


def test_digits_on_another_label_are_no_reading_of_the_code(tmp_path, monkeypatch):
    """Label 1's readers write dates and elevations; only the code's label counts."""
    rig = rig_with(tmp_path, monkeypatch, PRINTED)
    run = rig.specimen.run
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue(CODE, CODE)}))
    assert summary(run, KEY)[:3] == (ValueState.SUPPORTED, CODE, CODE)
    assert contradicting(run) == []


# ---- controls ---------------------------------------------------------------------------------

def outcome(run):
    """What a person and the record's routing see: each field's value and reason, the findings
    and the reasons, without the ids a fresh run draws."""
    names = {region.id: f"L{index + 1}" for index, region in enumerate(run.regions)}

    def plain(text):
        for region, name in names.items():
            text = text.replace(region, name)
        return text

    return ({key: (*summary(run, key), value.reason, sorted(value.evidence_relations.values()))
        for key, value in run.fields.items()},
        sorted((f.rule_id, plain(f.reason_code), f.severity) for f in run.findings),
        [plain(reason) for reason in run.reasons], run.disposition)


SCENARIOS = {
    "readers-agree": ((PRINTED,), None),
    "readers-differ": ((PRINTED, "FMNHINS\n0010007"), catalogue(CODE, CODE)),
    "no-number": (("FMNHINS",), LACKS),
}


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_a_run_with_no_code_row_settles_exactly_as_without_the_rule(tmp_path, monkeypatch, scenario):
    """No stored decode: the rule changes nothing, whatever the readers write."""
    from specimen_digitization.field_research import catalogue_code

    texts, script = SCENARIOS[scenario]
    scripts = {KEY: script} if script else {}
    plain = rig_with(tmp_path / "plain", monkeypatch, *texts)
    settle(plain, Scripted(scripts))
    monkeypatch.setattr(catalogue_code, "settle", lambda *args, **kwargs: False)
    without = build_rig(tmp_path / "without", FIRST)
    settle(without, Scripted(scripts))
    assert outcome(plain.specimen.run) == outcome(without.specimen.run)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_code_changes_no_other_field(tmp_path, monkeypatch, scenario):
    """With a code row the catalogue number may change; every other field, its findings and its
    reasons are as they are with no code row."""
    texts, script = SCENARIOS[scenario]
    scripts = {KEY: script} if script else {}
    plain = rig_with(tmp_path / "plain", monkeypatch, *texts)
    settle(plain, Scripted(scripts))
    coded = build_rig(tmp_path / "coded", FIRST)
    with_code(coded)
    settle(coded, Scripted(scripts))
    fields, found, reasons, _ = outcome(plain.specimen.run)
    fields_coded, found_coded, reasons_coded, _ = outcome(coded.specimen.run)
    assert {k: v for k, v in fields.items() if k != KEY} == {k: v for k, v in fields_coded.items() if k != KEY}
    assert [f for f in found if KEY not in f[1]] == [f for f in found_coded if KEY not in f[1]]
    # The barcode label's own reason is no other field's: where its readers differ and the code
    # settles the catalogue number, the label's unresolved_transcription, which the duplicate-label
    # rule (autonomy S1, C3) leaves out while the field holds a reason of its own, comes back.
    def others(found_reasons):
        return [r for r in found_reasons if KEY not in r and r not in ("identifier_format",
            "unresolved_transcription:L2")]

    assert others(reasons) == others(reasons_coded)


def test_a_code_row_on_a_run_of_the_old_path_changes_nothing(tmp_path, monkeypatch):
    """A run of the old first pass (moved runs keep it until the workflow moves them; a moved
    run's segment is not run again, so it holds no code row) is not settled on the code;
    catalogue_code.settle is never asked."""
    from specimen_digitization.field_research import catalogue_code
    from specimen_digitization.field_research import step as field_step

    asked = []
    monkeypatch.setattr(catalogue_code, "settle", lambda *args, **kwargs: asked.append(args) or False)
    rig = rig_with(tmp_path, monkeypatch, PRINTED)
    with_code(rig)
    monkeypatch.setattr(field_step, "units_path", lambda run: False)
    settle(rig, Scripted())
    assert asked == []


def test_a_persons_field_decision_is_never_settled_on_the_code(tmp_path, monkeypatch):
    """A field a person decided (human_keys) is not researched, and the code is never asked."""
    from specimen_digitization.field_research import catalogue_code
    from specimen_digitization.field_research import step as field_step

    asked = []
    monkeypatch.setattr(catalogue_code, "settle", lambda *args, **kwargs: asked.append(args) or False)
    monkeypatch.setattr(field_step, "human_keys", lambda run: frozenset({KEY}))
    rig = rig_with(tmp_path, monkeypatch, PRINTED, "FMNHINS\n0010007")
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue(CODE, CODE)}))
    assert asked == []


def test_the_hold_code_is_the_one_the_app_words():
    """The app words this exact code (the client's blockers.dart barcodeDiffersWords and
    settlement_codes.dart markedReasonWords; its barcode_differs_test.dart). Pinned here as a plain
    string, never by reading the app's files."""
    from specimen_digitization.field_research import catalogue_code
    from specimen_digitization.field_research.step import marked_code

    assert catalogue_code.DIFFERS == "barcode_differs"
    assert marked_code(KEY, "L1", catalogue_code.DIFFERS) == "marked:fmnh_ins_number:L1:barcode_differs"
