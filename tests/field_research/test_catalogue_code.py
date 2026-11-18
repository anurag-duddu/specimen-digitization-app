"""The catalogue number checked against the slide's QR code (field_research/catalogue_code.py).

A step-level test builds its run with test_step.build_rig, with the synthetic label's catalogue
line moved to a barcode label of its own (label 2, read by readers 2A and 2B), as on the real
slides, and gives it the evidence row the segment step stores for a decoded code
(application/barcode.record) on that label. The row is written out here as its fields so that
each test also runs on code from before a rule. Each test states the outcome under the four
rules (confirm, break a tie, contradict, otherwise nothing) and, where it differs, what the
previous head 8cf7f6b9 did."""

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
OTHER = "FMNHINS\n0010007"


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


def images(rig, image):
    """The barcode label's units with the image `image(unit)` gives each unit."""
    run = rig.specimen.run
    [entry] = [entry for entry in run.reading_units if entry.label == run.regions[1].id]
    store_reading_units(run, [entry.model_copy(update={"units": [
        unit.model_copy(update={"image": image(unit)}) for unit in entry.units]})])


def catalogue(literal, value, reading="2A"):
    return answering(resolved(literal, value=value, reading=reading))


def several(*options):
    return answering(FieldAnswer(outcome="several_possibilities", options=list(options),
        explanation="The readers' numbers differ."))


LACKS = answering(FieldAnswer(outcome="label_lacks_value", explanation="No reading prints a catalogue number."))


def summary(run, key=KEY):
    value = run.fields[key]
    return (value.state, value.literal, value.parsed, value.normalized, value.layer)


def number(run):
    value = run.fields[KEY]
    return (value.state, value.normalized or value.parsed or value.literal)


def marked(run, why):
    return f"marked:{KEY}:{run.regions[1].id}:{why}"


# ---- rule 1: confirm ---------------------------------------------------------------------------

def test_a_value_readers_alone_back_that_equals_the_code_clears(tmp_path, monkeypatch):
    """Both readers write the number, the image names nothing: today it settles marked
    text_only. The code confirms it: cleared, the code row deciding, no identifier_format."""
    rig = rig_with(tmp_path, monkeypatch, PRINTED)
    run = rig.specimen.run
    images(rig, lambda unit: UNCERTAIN)
    code = with_code(rig)
    settle(rig, Scripted({KEY: catalogue(CODE, CODE)}))
    value = run.fields[KEY]
    assert findings(run, KEY) == [(f"cleared:{KEY}:{run.regions[1].id}", "info")]
    assert not reasons_for(run, KEY) and "identifier_format" not in run.reasons
    assert number(run) == (ValueState.SUPPORTED, CODE)
    assert value.evidence_relations.get(code.id) == "decides"
    assert value.reason.endswith(f"The slide's QR code reads {CODE} too.")


def test_a_spaced_value_whose_number_is_the_codes_clears(tmp_path, monkeypatch):
    """Both readers space the number ("001 0001"); the expert settles it with the check's
    number 0010001. Its number is the code's: cleared, its literal as written."""
    rig = rig_with(tmp_path, monkeypatch, "FMNHINS 001 0001")
    run = rig.specimen.run
    images(rig, lambda unit: UNCERTAIN)
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue("001 0001", CODE)}))
    assert summary(run)[:3] == (ValueState.SUPPORTED, "001 0001", CODE)
    assert not reasons_for(run, KEY)


def test_a_misread_prefix_beside_the_codes_number_is_no_contradiction(tmp_path, monkeypatch):
    """105526522's reader A wrote "PMNH IN6" over the number. At 8cf7f6b9 the digit joining made
    it 60010001 and named it ruled out; now only the settled value is compared: it confirms."""
    rig = rig_with(tmp_path, monkeypatch, "PMNH IN6\n0010001", PRINTED)
    run = rig.specimen.run
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue(CODE, CODE)}))
    assert number(run) == (ValueState.SUPPORTED, CODE)
    assert "60010001" not in run.fields[KEY].reason and not reasons_for(run, KEY)


# ---- rule 2: break a tie -----------------------------------------------------------------------

def test_the_code_settles_the_one_candidate_it_equals(tmp_path, monkeypatch):
    """2A writes 0010001, 2B 0010007, and the expert offers both. Today: ambiguous. The code
    equals one candidate: that candidate, as 2A writes it, backed by the code; 0010007 ruled out."""
    rig = rig_with(tmp_path, monkeypatch, PRINTED, OTHER)
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: several(CODE, "0010007")}))
    value = run.fields[KEY]
    assert summary(run)[:3] == (ValueState.SUPPORTED, CODE, CODE)
    assert value.evidence_relations[code.id] == "decides"
    assert value.settled_observation_ids == [run.observations[2].id]
    assert value.reason == f"The slide's QR code reads {CODE}, which settles this field among its candidates. Ruled out: 0010007."
    assert not reasons_for(run, KEY) and "identifier_format" not in run.reasons


def test_a_clipped_candidate_breaks_no_tie(tmp_path, monkeypatch):
    """Codex round 3: the true number is 10010001, a foreign code holds 0010001, the readers
    write "FMNHINS 10010001" and "FMNHINS 10010007", and the expert offers the clipped
    "0010001". No reading writes 0010001 as a whole number: the field stays open, nothing
    cleared (at 78744430 the clipped 0010001 settled and cleared)."""
    rig = rig_with(tmp_path, monkeypatch, "FMNHINS 10010001", "FMNHINS 10010007")
    run = rig.specimen.run
    with_code(rig)
    settle(rig, Scripted({KEY: several(CODE, "10010007")}))
    assert run.fields[KEY].state == ValueState.AMBIGUOUS
    assert f"mandatory_unresolved:{KEY}" in run.reasons
    assert not [f for f in run.findings if f.field_key == KEY and f.reason_code.startswith("cleared:")]


@pytest.mark.parametrize(("text", "whole"), [
    # The code as the end (a suffix) or the start (a prefix) of a longer run of digits.
    ("FMNHINS 10010001", False),
    ("FMNHINS 00100012", False),
    ("x10010001y", False),
    # Whole at the start, in the middle and at the end of a line, and over the prefix's line.
    ("0010001 FMNHINS", True),
    ("FMNHINS 0010001 col", True),
    ("FMNHINS 0010001", True),
    ("FMNHINS\n0010001", True),
    ("No.0010001.", True),
    # Nothing is joined across white space.
    ("FMNHINS 001 0001", False),
])
def test_the_code_counts_as_written_only_as_a_whole_number(text, whole):
    from specimen_digitization.field_research.catalogue_code import written_whole

    assert written_whole(text, CODE) is whole


def test_candidates_none_of_which_is_the_code_stay_open(tmp_path, monkeypatch):
    """2A writes 0010004, 2B 0010007: no candidate is the code's number, so the field stays as
    today (ambiguous). At 8cf7f6b9 the code supplied 0010001 alone."""
    rig = rig_with(tmp_path, monkeypatch, "FMNHINS\n0010004", OTHER)
    run = rig.specimen.run
    with_code(rig)
    settle(rig, Scripted({KEY: several("0010004", "0010007")}))
    assert run.fields[KEY].state == ValueState.AMBIGUOUS
    assert f"mandatory_unresolved:{KEY}" in run.reasons


def test_one_reader_of_the_codes_number_settles_through_the_experts_literal(tmp_path, monkeypatch):
    """Only 2A writes a number (the code's); today one reader backs nothing and the answer is
    refused. The expert's literal is a candidate equal to the code: settled on it."""
    rig = rig_with(tmp_path, monkeypatch, PRINTED, "FMNHINS")
    run = rig.specimen.run
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue(CODE, CODE)}))
    assert number(run) == (ValueState.SUPPORTED, CODE)
    assert not reasons_for(run, KEY)


# ---- rule 3: contradict ------------------------------------------------------------------------

@pytest.mark.parametrize(("written", "literal", "value"), [
    (OTHER, "0010007", "0010007"),
    # Codex round 2, case 1: a second number equal to the code elsewhere on the label. At
    # 8cf7f6b9 the code's 0010001 replaced the settled 0010007 and cleared.
    ("FMNHINS 0010007\nOther accession: 0010001", "0010007", "0010007"),
])
def test_a_settled_value_the_code_contradicts_is_held_and_kept(tmp_path, monkeypatch, written, literal, value):
    """Both readers write the label's number, the image names it, the expert settles it; the
    code holds 0010001. Today it clears. The value stays and is marked barcode_differs."""
    rig = rig_with(tmp_path, monkeypatch, written)
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: catalogue(literal, value)}))
    held = run.fields[KEY]
    assert number(run) == (ValueState.SUPPORTED, value)
    assert held.evidence_relations[code.id] == "contradicts"
    assert held.reason.endswith(f"The slide's QR code reads {CODE}, which differs from this value. "
        "A person compares the label with the code.")
    assert findings(run, KEY) == [(marked(run, "barcode_differs"), "warning")]
    assert marked(run, "barcode_differs") in run.reasons
    assert run.disposition == Disposition.REVIEW


def test_one_reader_of_another_number_settled_is_held(tmp_path, monkeypatch):
    """Only 2A writes 0010007; today's rules leave one reader open (ambiguous). No candidate is
    the code's number, so it stays open (at 8cf7f6b9 the code's 0010001 was settled)."""
    rig = rig_with(tmp_path, monkeypatch, OTHER, "FMNHINS")
    run = rig.specimen.run
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue("0010007", "0010007")}))
    assert run.fields[KEY].state == ValueState.AMBIGUOUS
    assert reasons_for(run, KEY) == [f"mandatory_unresolved:{KEY}"]


def test_spaced_readers_of_another_number_are_never_cleared_on_the_code(tmp_path, monkeypatch):
    """Codex round 1's case: both readers write "FMNHINS 001 0007", the code 0010001. The code
    contradicts the settled 0010007: it stays, held (8cf7f6b9 held it as ambiguous)."""
    rig = rig_with(tmp_path, monkeypatch, "FMNHINS 001 0007")
    run = rig.specimen.run
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue("001 0007", "0010007")}))
    assert summary(run)[:3] == (ValueState.SUPPORTED, "001 0007", "0010007")
    assert marked(run, "barcode_differs") in run.reasons


def test_the_image_named_wrong_number_is_held_not_replaced(tmp_path, monkeypatch):
    """The image names 2A's 0010004 (105526487's case: 4486518 cleared against the code's
    4486618). At 8cf7f6b9 the code's number replaced it; now the value stays, held."""
    rig = rig_with(tmp_path, monkeypatch, "FMNHINS\n0010004", OTHER)
    run = rig.specimen.run
    images(rig, lambda unit: next(iter(unit.readers.values())).text)
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue("0010004", "0010004")}))
    assert number(run) == (ValueState.SUPPORTED, "0010004")
    assert marked(run, "barcode_differs") in run.reasons


# ---- rule 4: otherwise nothing -----------------------------------------------------------------

def test_a_label_no_reader_writes_a_number_on_stays_held(tmp_path, monkeypatch):
    """Neither reader of the barcode label writes a digit and the expert answers
    label_lacks_value: the code supplies nothing, so the field stays not present and
    mandatory_unresolved, as today. At 8cf7f6b9 the code's number filled it."""
    rig = rig_with(tmp_path, monkeypatch, "FMNHINS")
    run = rig.specimen.run
    with_code(rig)
    settle(rig, Scripted({KEY: LACKS}))
    assert run.fields[KEY].state == ValueState.NOT_PRESENT
    assert f"mandatory_unresolved:{KEY}" in run.reasons


def person_transcribes(rig, region_index, text):
    """A label's transcript as a reviewer's decision leaves it (application/api.py; as
    test_first_pass_advice.person_transcribed does for label 1): the person's text, resolved,
    its units from that text (first_pass.source_units)."""
    from specimen_digitization.application.first_pass import source_units

    run = rig.specimen.run
    region = run.regions[region_index].id
    index = next(i for i, t in enumerate(run.transcripts) if t.region_id == region)
    run.transcripts[index] = run.transcripts[index].model_copy(update={"text": text, "resolved": True,
        "actor": "reviewer@example.org", "reason": "The label reads so.", "decision_kind": "human"})
    store_reading_units(run, [source_units(run, region)])


@pytest.mark.parametrize(("person", "literal", "state"), [
    # The person corrects the number to one no machine reader wrote (Codex round 1, case 1).
    ("FMNHINS 0010007", "0010007", ValueState.SUPPORTED),
    # The person's text holds no number at all.
    ("FMNHINS", None, ValueState.NOT_PRESENT),
])
def test_a_persons_transcription_of_the_barcode_label_stands(tmp_path, monkeypatch, person, literal, state):
    """The code changes nothing; where the settled value's number is not the code's, a note
    and an info finding say so."""
    rig = rig_with(tmp_path, monkeypatch, PRINTED)
    run = rig.specimen.run
    person_transcribes(rig, 1, person)
    code = with_code(rig)
    settle(rig, Scripted({KEY: catalogue(literal, literal) if literal else LACKS}))
    value = run.fields[KEY]
    assert (value.state, value.literal) == (state, literal)
    assert code.id not in value.evidence_relations
    assert not any(r.endswith(":barcode_differs") for r in run.reasons)
    notes = [(f.reason_code, f.evidence_ids) for f in run.findings if f.field_key == KEY and f.rule_id == "barcode_decode"]
    if literal:
        assert value.reason.endswith(f"The slide's QR code reads {CODE}, which differs from this value; "
            "a person's transcription stands.")
        assert notes == [(f"barcode_person_differs:{KEY}", [code.id])]
    else:
        assert notes == []


def test_a_persons_transcription_on_another_label_stands(tmp_path, monkeypatch):
    """Codex round 2, case 2: the code lies on label 2, whose readers write no number; a person
    transcribes label 1 with "FMNHINS 0010007" and the field settles on it. At 8cf7f6b9 the
    code's 0010001 replaced it; now it stands, with the note."""
    rig = rig_with(tmp_path, monkeypatch, "FMNHINS")
    run = rig.specimen.run
    person_transcribes(rig, 0, FIRST + "\nFMNHINS 0010007")
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue("0010007", "0010007", reading="1A")}))
    assert number(run)[1] != CODE
    assert not any(r.endswith(":barcode_differs") for r in run.reasons)


def test_a_person_confirming_a_reader_stands(tmp_path, monkeypatch):
    """A person transcribes the barcode label as reader 2B's 0010007 (G51's case: the same
    observation as a reader); the code changes nothing."""
    rig = rig_with(tmp_path, monkeypatch, PRINTED, OTHER)
    run = rig.specimen.run
    person_transcribes(rig, 1, OTHER)
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue("0010007", "0010007")}))
    assert number(run)[1] != CODE
    assert not any(r.endswith(":barcode_differs") for r in run.reasons)


def test_a_decode_placed_on_no_label_changes_nothing(tmp_path, monkeypatch):
    """G51 round 1's off-label code: the decoder stores no such row; a row without a label
    changes nothing here either."""
    rig = rig_with(tmp_path, monkeypatch, PRINTED, OTHER)
    run = rig.specimen.run
    with_code(rig, region=None)
    settle(rig, Scripted({KEY: several(CODE, "0010007")}))
    assert run.fields[KEY].state == ValueState.AMBIGUOUS


# ---- controls ----------------------------------------------------------------------------------

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
    "readers-differ": ((PRINTED, OTHER), several(CODE, "0010007")),
    "no-number": (("FMNHINS",), LACKS),
}


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_a_run_with_no_code_row_settles_exactly_as_without_the_rule(tmp_path, monkeypatch, scenario):
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
    """With a code row the catalogue number may change; every other field, its findings and the
    other reasons stay as with no code row (the barcode label's own unresolved_transcription
    aside: the duplicate-label rule of autonomy S1 sets it aside only while the field is held)."""
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

    def others(found_reasons):
        return [r for r in found_reasons if KEY not in r and r not in ("identifier_format",
            "unresolved_transcription:L2")]

    assert others(reasons) == others(reasons_coded)


def test_a_code_row_on_a_run_of_the_old_path_changes_nothing(tmp_path, monkeypatch):
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
    from specimen_digitization.field_research import catalogue_code
    from specimen_digitization.field_research import step as field_step

    asked = []
    monkeypatch.setattr(catalogue_code, "settle", lambda *args, **kwargs: asked.append(args) or False)
    monkeypatch.setattr(field_step, "human_keys", lambda run: frozenset({KEY}))
    rig = rig_with(tmp_path, monkeypatch, PRINTED, OTHER)
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue(CODE, CODE)}))
    assert asked == []


def test_an_approval_does_not_outlive_a_catalogue_number_the_code_settles(tmp_path, monkeypatch):
    """A person approved the record while the catalogue number was open (#450 records a digest
    of the approved values). Research runs again with the code stored and the code breaks the
    tie: the values changed, so finalize withdraws the approval (lane.settle_approval) and the
    record is no longer cleared by a person. No code of the rule's does this."""
    from specimen_digitization.application.lane import approved_values_digest, cleared_by
    from specimen_digitization.field_research import catalogue_code
    from specimen_digitization.field_research import step as field_step
    from specimen_digitization.field_research.contracts import FieldOutcome

    rig = rig_with(tmp_path, monkeypatch, PRINTED, OTHER)
    run = rig.specimen.run
    settle(rig, Scripted({KEY: several(CODE, "0010007")}))
    assert run.fields[KEY].state == ValueState.AMBIGUOUS
    run.human_approved = True
    run.approved_values_sha256 = approved_values_digest(run)
    with_code(rig)
    readings, tasks, _ = field_step.build_tasks(run)
    task = next(task for task in tasks if task.key == KEY)
    expert = FieldOutcome(KEY, FieldAnswer(outcome="several_possibilities", options=[CODE, "0010007"],
        explanation="The readers' numbers differ."))
    assert catalogue_code.settle(run, task, readings, asset_id=rig.specimen.asset.id, blobs=rig.blobs,
        outcomes=[expert])
    field_step.finalize_fields(run, None, (), specimen=rig.specimen, blobs=rig.blobs, today=rig_module.TODAY)
    assert number(run) == (ValueState.SUPPORTED, CODE)
    assert run.human_approved is False
    assert cleared_by(run.disposition.value, run.human_approved) != "person"


def test_the_hold_code_is_the_one_the_app_words():
    """The app words this exact code (the client's blockers.dart barcodeDiffersWords and
    settlement_codes.dart markedReasonWords; its barcode_differs_test.dart). Pinned here as a plain
    string, never by reading the app's files."""
    from specimen_digitization.field_research import catalogue_code
    from specimen_digitization.field_research.step import marked_code

    assert catalogue_code.DIFFERS == "barcode_differs"
    assert marked_code(KEY, "L1", catalogue_code.DIFFERS) == "marked:fmnh_ins_number:L1:barcode_differs"
