"""The catalogue number checked against the slide's QR code (field_research/catalogue_code.py).

A step-level test builds its run with test_step.build_rig, with the synthetic label's catalogue
line moved to a barcode label of its own (label 2, read by readers 2A and 2B), as on the real
slides, and gives it the evidence row the segment step stores for a decoded code
(application/barcode.record) on that label. The row is written out here as its fields so that
each test also runs on code from before a rule. Each test states the outcome under the module's
four rules (1 no value settled: the code gives the number; 2 a settled number that is not the
code's: the field takes the code's; 3 a settled number that writes the code whole: confirmed;
4 otherwise nothing) and, where the rule of 2026-11-20 changed an earlier case's expectation,
what e83c36fd did (it confirmed or held, and supplied no value)."""

from __future__ import annotations

import hashlib
import io
import sys

import pytest
import test_step as rig_module
from PIL import Image
from test_settlement_rule import findings
from test_step import (
    COLLECTORS,
    LABEL,
    TEXT,
    Scripted,
    answering,
    build_rig,
    failing,
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
    route; a reader with no text of its own reads the first. Bound to the rig's default profile
    (every field mandatory) unless build_rig is given one."""
    original = rig_module.make_specimen

    def make(blobs, first=FIRST, other=None, *, profile=None):
        specimen = original(blobs, first, other, profile=profile)
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


def notes(run):
    """The rule's own findings on the field (rule barcode_decode), each with what it cites."""
    return [(f.reason_code, f.severity, f.evidence_ids) for f in run.findings
        if f.field_key == KEY and f.rule_id == "barcode_decode"]


def supplied(run, code, payload=CODE):
    """The field as the code supplies it (rules 1 and 2): the code's digits, supported, on the
    settled layer, on the code's label, the code row its one citation and deciding it; cleared on
    the code's label; no reason, hold or mark of the field's left, and the record cleared."""
    value = run.fields[KEY]
    assert summary(run) == (ValueState.SUPPORTED, payload, payload, None, "settled")
    assert value.evidence_ids == [code.id] and value.evidence_relations == {code.id: "decides"}
    assert value.source_region_id == code.region_id
    assert (value.input_source, value.verbatim_by_observation, value.settled_observation_ids) == (None, {}, [])
    cleared = [(f.reason_code, f.severity, f.evidence_ids) for f in run.findings
        if f.rule_id == "field_settlement" and f.field_key == KEY]
    assert cleared == [(f"cleared:{KEY}:{code.region_id}", "info", [code.id])]
    assert not reasons_for(run, KEY) and "identifier_format" not in run.reasons
    assert not any(f"marked:{KEY}:" in reason for reason in (*run.reasons, *run.open_reasons))
    assert not any(f.reason_code == f"transcript_literal:{KEY}" for f in run.findings)
    assert (run.disposition, run.stage, run.reasons) == (Disposition.CLEARED, "finalized", [])
    return value


def over_readers(run, code, readers, payload=CODE):
    """Rule 2's outcome: the code's number, the readers' kept in the reason and by one info
    finding that cites the code row first, then the readers' rows, and is no reason."""
    value = supplied(run, code, payload)
    assert value.reason == (f'The readers\' number, "{readers}", differs from the slide\'s QR code, which reads '
        f"{payload}. The code gives the catalog number.")
    [(found, severity, cited)] = notes(run)
    assert (found, severity, cited[0]) == (f"barcode_readers_differ:{KEY}", "info", code.id)
    rows = {row.id: row for row in run.evidence}
    assert len(cited) > 1 and all(rows[i].kind == "literal" and rows[i].region_id for i in cited[1:])
    assert found not in run.reasons and found not in run.open_reasons
    return value


# ---- rule 3: confirm ---------------------------------------------------------------------------

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
    # The mark's sentence is replaced by what is now true (G51 round 4, finding 4).
    assert value.reason.endswith(f"The slide's QR code confirms this number, {CODE}.")
    assert "Marked for a person" not in value.reason


def test_a_spaced_value_whose_parse_is_unsupported_stays_as_with_no_code(tmp_path, monkeypatch):
    """Both readers space the number ("001 0001"); the expert settles the literal with the
    value 0010001. The literal writes the code whole, but the check does not read a spaced
    literal, so the parsed 0010001 has no support: with no code main holds it as
    unsupported_parsed (and marked text_only). The code does not stand in for that support:
    the field is exactly as with no code. At aea10588 the code row cleared it."""
    runs = []
    barcode_label(monkeypatch, "FMNHINS 001 0001")
    for name, coded in (("plain", False), ("coded", True)):
        rig = build_rig(tmp_path / name, FIRST)
        images(rig, lambda unit: UNCERTAIN)
        if coded:
            with_code(rig)
        settle(rig, Scripted({KEY: catalogue("001 0001", CODE)}))
        runs.append(rig.specimen.run)
    plain, coded = runs
    assert f"unsupported_parsed:{KEY}" in plain.reasons
    assert outcome(plain) == outcome(coded)


@pytest.mark.parametrize(("written", "literal", "value"), [
    # G51 round 4: the readers write the longer 10010001 and the expert parses its suffix.
    ("FMNHINS 10010001", "10010001", CODE),
    # The readers write 0010007 and the expert's value is the code's.
    (OTHER, "0010007", CODE),
])
def test_a_parsed_value_equal_to_the_code_never_confirms_a_literal_that_is_not(tmp_path, monkeypatch, written,
        literal, value):
    """The literal the label writes is not the code written whole: the code does not confirm
    what was written, whatever the parsed value reads (at aea10588 the code confirmed it). Rule 2:
    the field takes the code's number, the readers' is kept in the reason and the note, and main's
    unsupported_parsed hold on the readers' value goes with that value. At e83c36fd the readers'
    value stayed, held as barcode_differs."""
    rig = rig_with(tmp_path, monkeypatch, written)
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: catalogue(literal, value)}))
    held = over_readers(run, code, literal)
    assert "confirms" not in held.reason and f"unsupported_parsed:{KEY}" not in run.reasons


def test_a_misread_prefix_beside_the_codes_number_is_no_contradiction(tmp_path, monkeypatch):
    """105526522's reader A wrote "PMNH IN6" over the number. At 8cf7f6b9 the digit joining made
    it 60010001 and named it ruled out; now only the settled value is compared: it confirms."""
    rig = rig_with(tmp_path, monkeypatch, "PMNH IN6\n0010001", PRINTED)
    run = rig.specimen.run
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue(CODE, CODE)}))
    assert number(run) == (ValueState.SUPPORTED, CODE)
    assert "60010001" not in run.fields[KEY].reason and not reasons_for(run, KEY)


# ---- rule 1: no value settled, the code gives the number ---------------------------------------

TIE_CASES = {
    # The readers differ, one of them writing the code's number (105526330's and 105526617's
    # case): research leaves the field open. At 947f0efd the code picked the reader equal to it;
    # at e83c36fd the field stayed open. Now the code's own number settles it, whole.
    "one-reader-is-the-code": ((PRINTED, OTHER), (CODE, "0010007")),
    # Codex's cases against a tie-break that read the readers' texts: a clipped suffix, a Unicode
    # digit, an invisible separator, a joined date, and the spaced number that crashed research.
    # None of these texts is read: the value is the code row's payload and cites no reader's row.
    "clipped-suffix": (("FMNHINS 10010001", "FMNHINS 10010007"), (CODE, "10010007")),
    "unicode-digit": (("FMNHINS \N{FULLWIDTH DIGIT ONE}0010001", "FMNHINS 10010007"), (CODE, "10010007")),
    "invisible-separator": (("FMNHINS 1\N{ZERO WIDTH SPACE}0010001", "FMNHINS 10010007"), (CODE, "10010007")),
    "joined-date": (("FMNHINS 10010001\nCollected 1/12/2026", "FMNHINS 10010007"), (CODE, "10010007")),
    "spaced-number": (("FMNHINS 001 0001", OTHER), (CODE, "0010007")),
}


@pytest.mark.parametrize("case", TIE_CASES)
def test_the_code_breaks_no_tie(tmp_path, monkeypatch, case):
    """Research leaves the field open (ambiguous and held, as with no code row). The code breaks
    no tie among the readings: it gives its own number whole, cites no reader's row, and research
    raises nothing. At e83c36fd the field stayed open and the record held."""
    texts, options = TIE_CASES[case]
    barcode_label(monkeypatch, *texts)
    plain = build_rig(tmp_path / "plain", FIRST)
    settle(plain, Scripted({KEY: several(*options)}))
    assert plain.specimen.run.fields[KEY].state == ValueState.AMBIGUOUS
    assert plain.specimen.run.disposition == Disposition.REVIEW
    coded = build_rig(tmp_path / "coded", FIRST)
    code = with_code(coded)
    settle(coded, Scripted({KEY: several(*options)}))
    run = coded.specimen.run
    value = supplied(run, code)
    assert value.reason.startswith("No reading settled the catalog number.")
    assert value.reason.endswith(f" The slide's QR code gives it: {CODE}.")
    assert notes(run) == []
    assert rest(plain.specimen.run) == rest(run)


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
    # The projection keeps letters and numbers only: white space, marks and format characters
    # between digits join them, so the code's own digits spaced are whole, and a number beside
    # the code across any of them clips it.
    ("FMNHINS 001 0001", True),
    ("FMNHINS0010001", True),
    ("FMNH-INS\n0010001", True),
    ("No. 0010001.", True),
    ("12 0010001", False),
    ("0010001 7", False),
    *[(f"FMNHINS 1{sep}0010001", False) for sep in (
        "\N{ZERO WIDTH SPACE}", "\N{COMBINING ACUTE ACCENT}", "\N{ZERO WIDTH JOINER}", "\N{SOFT HYPHEN}",
        "\N{NARROW NO-BREAK SPACE}", "\N{ARABIC THOUSANDS SEPARATOR}")],
    *[(f"FMNHINS 0010001{sep}7", False) for sep in (
        "\N{COMBINING ACUTE ACCENT}", "\N{ZERO WIDTH JOINER}", "\N{SOFT HYPHEN}")],
    # A digit of another script, or a superscript, right before or after.
    ("FMNHINS \N{FULLWIDTH DIGIT ONE}0010001", False),
    ("FMNHINS 0010001\N{FULLWIDTH DIGIT ONE}", False),
    ("FMNHINS \N{ARABIC-INDIC DIGIT ONE}0010001", False),
    ("FMNHINS 0010001\N{ARABIC-INDIC DIGIT ONE}", False),
    ("FMNHINS \N{SUPERSCRIPT ONE}0010001", False),
    ("FMNHINS 0010001\N{SUPERSCRIPT ONE}", False),
    ("FMNHINS \N{VULGAR FRACTION ONE HALF}0010001", False),
    # A clipped occurrence first and a whole one later on the text.
    ("10010001 and 0010001", True),
])
def test_the_code_counts_as_written_only_as_a_whole_number(text, whole):
    from specimen_digitization.field_research.catalogue_code import written_whole

    assert written_whole(text, CODE) is whole


@pytest.mark.parametrize(("text", "literal", "held"), [
    ("FMNHINS 0010001", "0010001", True),
    ("FMNHINS\n001 0001", "001 0001", True),
    # The literal as the end of a longer number, or joined to a date across a line break
    # (Codex round 6): not the literal's own occurrence.
    ("FMNHINS 10010001", "0010001", False),
    ("FMNHINS 11122026\nCollected 1/12/2026", "1122026", False),
    ("FMNHINS 0010001\n12/1", "0010001", False),
    # The raw text does not hold a literal the projection would admit.
    ("FMNHINS 001 0001", "0010001", False),
])
def test_the_confirmation_needs_the_literals_own_whole_occurrence(text, literal, held):
    from specimen_digitization.field_research.catalogue_code import _held_whole

    assert _held_whole(text, literal) is held


@pytest.mark.parametrize(("written", "literal", "payload", "settles"), [
    # The spaced literal the projection admits (Codex round 6, finding 2's text): research
    # settles it, it writes the code whole, and the confirmation cannot ground it. Rule 3 changes
    # nothing, and the code gives no number over a value that writes it.
    ("FMNHINS 001 0001", "001 0001", CODE, True),
    # A line break inside the number: research settles nothing, so rule 1 gives the code's.
    ("FMNHINS 001\n0001", "001\n0001", CODE, False),
    # The joined date (Codex round 6, finding 1): the literal is the clipped suffix, which
    # research refuses; the code's number is the payload whole, read from no text.
    ("FMNHINS 11122026\nCollected 1/12/2026", "1122026", "1122026", False),
])
def test_a_literal_the_confirmation_cannot_ground_whole_raises_nothing(tmp_path, monkeypatch,
        written, literal, payload, settles):
    """Through apply_outcomes: no exception. A value research settled that writes the code whole
    and that the confirmation (now rule 3) cannot ground is exactly as with no code row. A literal
    research refuses leaves no value settled: at e83c36fd that field stayed open, exactly as with
    no code row; now the code gives its number (rule 1)."""
    barcode_label(monkeypatch, written)
    plain = build_rig(tmp_path / "plain", FIRST)
    settle(plain, Scripted({KEY: catalogue(literal, payload)}))
    assert (plain.specimen.run.fields[KEY].state == ValueState.SUPPORTED) is settles
    coded = build_rig(tmp_path / "coded", FIRST)
    code = with_code(coded, payload)
    settle(coded, Scripted({KEY: catalogue(literal, payload)}))
    if settles:
        assert outcome(plain.specimen.run) == outcome(coded.specimen.run)
    else:
        supplied(coded.specimen.run, code, payload)
        assert rest(plain.specimen.run) == rest(coded.specimen.run)


def test_an_exception_inside_the_rule_leaves_the_field_as_the_rules_settled_it(tmp_path, monkeypatch, caplog):
    """step.apply_outcomes calls each part of the rule (confirm, then give as its last act) inside
    one guard that logs any exception and puts the field, its findings and its decision back: the
    code cannot fail research."""
    from specimen_digitization.field_research import catalogue_code

    barcode_label(monkeypatch, PRINTED)
    plain = build_rig(tmp_path / "plain", FIRST)
    images(plain, lambda unit: UNCERTAIN)
    settle(plain, Scripted({KEY: catalogue(CODE, CODE)}))

    def broken(run, *args, **kwargs):
        run.fields[KEY] = run.fields[KEY].model_copy(update={"literal": "broken"})
        run.findings.clear()
        raise ValueError("substring not found")

    monkeypatch.setattr(catalogue_code, "confirm", broken)
    coded = build_rig(tmp_path / "coded", FIRST)
    images(coded, lambda unit: UNCERTAIN)
    with_code(coded)
    with caplog.at_level("WARNING"):
        settle(coded, Scripted({KEY: catalogue(CODE, CODE)}))
    assert outcome(plain.specimen.run) == outcome(coded.specimen.run)
    assert any("not compared with the slide's QR code" in record.message for record in caplog.records)


def test_an_exception_while_the_code_gives_the_number_leaves_the_field_open(tmp_path, monkeypatch, caplog):
    """The same guard around rules 1 and 2: the rule fails after it has put the code's number in
    the field and dropped the field's findings; the field, its findings and its decision are put
    back, and the record is exactly as with no code row (open, held)."""
    from specimen_digitization.field_research import catalogue_code

    barcode_label(monkeypatch, PRINTED, OTHER)
    plain = build_rig(tmp_path / "plain", FIRST)
    settle(plain, Scripted({KEY: several(CODE, "0010007")}))
    supply = catalogue_code._supply

    def broken(run, *args, **kwargs):
        supply(run, *args, **kwargs)
        raise RuntimeError("after the field was set")

    monkeypatch.setattr(catalogue_code, "_supply", broken)
    coded = build_rig(tmp_path / "coded", FIRST)
    with_code(coded)
    with caplog.at_level("WARNING"):
        settle(coded, Scripted({KEY: several(CODE, "0010007")}))
    assert coded.specimen.run.fields[KEY].state == ValueState.AMBIGUOUS
    assert outcome(plain.specimen.run) == outcome(coded.specimen.run)
    assert any("not compared with the slide's QR code" in record.message for record in caplog.records)


# ---- rule 2: a settled number that is not the code's takes the code's --------------------------

@pytest.mark.parametrize(("written", "literal", "value"), [
    (OTHER, "0010007", "0010007"),
    # Codex round 2, case 1: a second number equal to the code elsewhere on the label. At
    # 8cf7f6b9 the code's 0010001 replaced the settled 0010007 and cleared.
    ("FMNHINS 0010007\nOther accession: 0010001", "0010007", "0010007"),
])
def test_a_settled_value_the_code_contradicts_takes_the_codes_number(tmp_path, monkeypatch, written, literal,
        value):
    """Both readers write the label's number, the image names it, the expert settles it; the
    code holds 0010001. With no code row it clears on the readers' number. At e83c36fd the value
    stayed, marked barcode_differs and held for a person (the test's earlier name ended
    is_held_and_kept). Rule 2: the field is the code's number, cleared, with no mark and no hold;
    the readers' number is kept in the reason and by the info note."""
    rig = rig_with(tmp_path, monkeypatch, written)
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: catalogue(literal, value)}))
    held = over_readers(run, code, literal)
    assert "Marked for a person" not in held.reason and "A person compares" not in held.reason
    assert findings(run, KEY) == [(f"cleared:{KEY}:{run.regions[1].id}", "info")]
    assert not any("barcode_differs" in reason for reason in (*run.reasons, *run.open_reasons))
    assert not any("barcode_differs" in finding.reason_code for finding in run.findings)


def test_spaced_readers_of_another_number_take_the_codes_number(tmp_path, monkeypatch):
    """Codex round 1's case: both readers write "FMNHINS 001 0007", the code 0010001. The readers'
    number is never confirmed by the code (the confirmation needs the code written whole). At
    e83c36fd the settled 0010007 stayed, held as barcode_differs (the test's earlier name ended
    are_never_cleared_on_the_code). Rule 2: the field takes the code's 0010001."""
    rig = rig_with(tmp_path, monkeypatch, "FMNHINS 001 0007")
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: catalogue("001 0007", "0010007")}))
    over_readers(run, code, "001 0007")


def test_the_image_named_wrong_number_takes_the_codes_number(tmp_path, monkeypatch):
    """The image names 2A's 0010004 (105526487's case: 4486518 cleared against the code's
    4486618). At e83c36fd the value stayed, held as barcode_differs (the test's earlier name ended
    is_held_not_replaced). Rule 2: the code's number replaces it and the record clears."""
    rig = rig_with(tmp_path, monkeypatch, "FMNHINS\n0010004", OTHER)
    run = rig.specimen.run
    images(rig, lambda unit: next(iter(unit.readers.values())).text)
    code = with_code(rig)
    settle(rig, Scripted({KEY: catalogue("0010004", "0010004")}))
    over_readers(run, code, "0010004")


# ---- rule 1, the other ways no value is settled ------------------------------------------------

def test_one_reader_of_another_number_left_open_takes_the_codes_number(tmp_path, monkeypatch):
    """Only 2A writes 0010007; the settlement rules leave one reader open (ambiguous). At e83c36fd
    it stayed open, mandatory_unresolved (the test's earlier name ended settled_is_held). Rule 1:
    no reading settled the number, so the code's 0010001 gives it; the one reader's text is in the
    reason and no reader's row is cited."""
    barcode_label(monkeypatch, OTHER, "FMNHINS")
    plain = build_rig(tmp_path / "plain", FIRST)
    settle(plain, Scripted({KEY: catalogue("0010007", "0010007")}))
    assert plain.specimen.run.fields[KEY].state == ValueState.AMBIGUOUS
    assert reasons_for(plain.specimen.run, KEY) == [f"mandatory_unresolved:{KEY}"]
    rig = build_rig(tmp_path / "coded", FIRST)
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: catalogue("0010007", "0010007")}))
    value = supplied(run, code)
    assert value.reason.startswith("No reading settled the catalog number.") and notes(run) == []


def test_a_label_no_reader_writes_a_number_on_takes_the_codes_number(tmp_path, monkeypatch):
    """Neither reader of the barcode label writes a digit and the expert answers
    label_lacks_value. At e83c36fd the code supplied nothing: the field stayed not present and
    mandatory_unresolved (the test's earlier name ended stays_held). Rule 1: the code gives the
    number; the reason says no reading settled it and quotes no reading, as none wrote one."""
    barcode_label(monkeypatch, "FMNHINS")
    plain = build_rig(tmp_path / "plain", FIRST)
    settle(plain, Scripted({KEY: LACKS}))
    assert plain.specimen.run.fields[KEY].state == ValueState.NOT_PRESENT
    assert f"mandatory_unresolved:{KEY}" in plain.specimen.run.reasons
    rig = build_rig(tmp_path / "coded", FIRST)
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: LACKS}))
    value = supplied(run, code)
    assert value.reason == f"No reading settled the catalog number. The slide's QR code gives it: {CODE}."
    assert notes(run) == []


@pytest.mark.parametrize(("organised", "state", "read"), [
    # The organiser gave the field each reader's number, as on a real slide: the reason quotes
    # them, each once, whole and never compared.
    (True, ValueState.AMBIGUOUS, f' The readers read "{CODE}" and "0010007".'),
    # The organiser gave the field no candidate: nothing is quoted.
    (False, ValueState.UNRESOLVED, ""),
])
def test_a_number_its_expert_cannot_resolve_takes_the_codes_number(tmp_path, monkeypatch, organised, state, read):
    """The readers differ and the expert answers sources_cannot_resolve: the field is left open
    (ambiguous beside the organiser's candidates, unresolved with none) and held, at e83c36fd too.
    Rule 1 gives the code's number; no evidence row is built beyond the stored code row."""
    answer = answering(FieldAnswer(outcome="sources_cannot_resolve", explanation="The digits cannot be told apart."))
    candidates = [*COLLECTORS, *([(KEY, "2A", CODE, CODE), (KEY, "2B", "0010007", "0010007")] if organised else [])]
    barcode_label(monkeypatch, PRINTED, OTHER)
    plain = build_rig(tmp_path / "plain", FIRST, candidates=candidates)
    settle(plain, Scripted({KEY: answer}))
    assert plain.specimen.run.fields[KEY].state == state
    assert f"mandatory_unresolved:{KEY}" in plain.specimen.run.reasons
    rig = build_rig(tmp_path / "coded", FIRST, candidates=candidates)
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: answer}))
    value = supplied(run, code)
    assert value.reason == f"No reading settled the catalog number.{read} The slide's QR code gives it: {CODE}."
    assert len(run.evidence) == len(plain.specimen.run.evidence) + 1
    assert rest(plain.specimen.run) == rest(run)


@pytest.mark.parametrize(("written", "literal"), [
    # Four digits: no catalogue number (five to nine digits).
    ("FMNHINS\n0010", "0010"),
    # The code's digits with a letter after them: the literal writes the code whole, and still
    # is no well-formed number, so it is not the confirmation's case.
    ("FMNHINS\n0010001a", "0010001a"),
])
def test_a_settled_text_that_is_no_well_formed_number_takes_the_codes_number(tmp_path, monkeypatch, written,
        literal):
    """Both readers write a text the format refuses and the expert settles it: with no code row,
    and at e83c36fd with one, the record is held by identifier_format (at e83c36fd the first also
    by barcode_differs). Rule 1: the code gives the number; the readers' text is kept in the reason
    and by the info note."""
    barcode_label(monkeypatch, written)
    plain = build_rig(tmp_path / "plain", FIRST)
    settle(plain, Scripted({KEY: catalogue(literal, None)}))
    assert plain.specimen.run.fields[KEY].state == ValueState.SUPPORTED
    assert "identifier_format" in plain.specimen.run.reasons
    rig = build_rig(tmp_path / "coded", FIRST)
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: catalogue(literal, None)}))
    value = supplied(run, code)
    assert value.reason == (f'The readers\' text, "{literal}", is not a well-formed catalog number. The slide\'s QR '
        f"code reads {CODE} and gives the catalog number.")
    [(found, severity, cited)] = notes(run)
    assert (found, severity, cited[0]) == (f"barcode_readers_differ:{KEY}", "info", code.id)


def test_a_number_whose_research_failed_takes_the_codes_number_and_is_not_asked_again(tmp_path, monkeypatch):
    """The field's expert fails with a model error. The attempt is blocked for a retry as before
    (the failure is the attempt's, whatever the field holds), and the field holds the code's
    number, so the retry does not ask its expert again and the record clears. At e83c36fd the
    field stayed unresolved and the retry asked again."""
    from specimen_digitization.field_research.step import build_tasks

    rig = rig_with(tmp_path, monkeypatch, PRINTED, OTHER)
    run = rig.specimen.run
    code = with_code(rig)
    assert settle(rig, Scripted({KEY: failing("model_error")})) == "field_research_model_error"
    assert (run.stage, run.disposition) == ("processing_blocked", None)
    assert summary(run) == (ValueState.SUPPORTED, CODE, CODE, None, "settled")
    assert KEY not in {task.key for task in build_tasks(run)[1]}
    again = Scripted()
    assert settle(rig, again) is None and KEY not in again.calls
    supplied(run, code)


@pytest.mark.parametrize(("texts", "script", "rule"), [
    ((PRINTED, OTHER), several(CODE, "0010007"), "barcode_supplies"),
    ((OTHER,), catalogue("0010007", "0010007"), "barcode_over_readers"),
])
def test_on_the_published_profile_the_record_clears_on_the_codes_number(tmp_path, monkeypatch, texts, script, rule):
    """The published profile, where the catalogue number is the one mandatory field (the tests
    above run on the rig's profile, every field mandatory). With no code row an open number holds
    the record and a wrong settled number clears it; with the code row the record clears by the
    system on the code's number in both, and the trace names the rule that decided."""
    from specimen_digitization.application.collection_profiles import published_registry
    from specimen_digitization.field_research.step import apply_outcomes, finalize_fields
    from test_step import research

    published = published_registry().profiles[0]
    assert published.mandatory_fields == (KEY,)
    barcode_label(monkeypatch, *texts)
    plain = build_rig(tmp_path / "plain", FIRST, profile=published)
    settle(plain, Scripted({KEY: script}))
    open_number = plain.specimen.run.fields[KEY].state != ValueState.SUPPORTED
    assert (plain.specimen.run.disposition == Disposition.REVIEW) is open_number
    assert number(plain.specimen.run)[1] != CODE
    rig = build_rig(tmp_path / "coded", FIRST, profile=published)
    run = rig.specimen.run
    code = with_code(rig)
    prepared, outcomes, calls = research(rig, Scripted({KEY: script}))
    decisions = {}
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    finalize_fields(run, None, outcomes, specimen=rig.specimen, blobs=rig.blobs, today=rig_module.TODAY)
    supplied(run, code)
    assert decisions[KEY]["rule"] == rule and run.human_approved is False


def test_a_supplied_number_is_the_same_at_every_later_finalize(tmp_path, monkeypatch):
    """Nothing is stored beyond the field's value, its findings and its citation of the code
    row: a re-finalize with no research (a person's decision elsewhere, a history restore, Resume)
    reads the same record, step.code_confirmed reads the field as a number the code confirms, so
    the barcode label's reading doubt is an open reason and holds nothing, and a later attempt
    does not research the field."""
    from specimen_digitization.field_research import step as field_step

    rig = rig_with(tmp_path, monkeypatch, PRINTED, OTHER)
    run = rig.specimen.run
    code = with_code(rig)
    settle(rig, Scripted({KEY: several(CODE, "0010007")}))
    supplied(run, code)
    assert field_step.code_confirmed(run) == frozenset({KEY})
    assert f"unresolved_transcription:{run.regions[1].id}" in run.open_reasons
    before = (outcome(run), list(run.open_reasons), run.fields[KEY].model_dump())
    field_step.refinalize(run, specimen=rig.specimen, blobs=rig.blobs, today=rig_module.TODAY)
    assert (outcome(run), list(run.open_reasons), run.fields[KEY].model_dump()) == before
    assert KEY not in {task.key for task in field_step.build_tasks(run)[1]}


# ---- rule 4: otherwise nothing -----------------------------------------------------------------

def test_a_person_decided_transcript_keeps_an_open_field_open(tmp_path, monkeypatch):
    """A person transcribes label 1; the barcode label's readers differ and research leaves the
    number open. The code supplies nothing on a run with a transcript a person decided: the field
    is exactly as with no code row, and no note is made (unchanged from e83c36fd)."""
    barcode_label(monkeypatch, PRINTED, OTHER)
    runs = []
    for name, coded in (("plain", False), ("coded", True)):
        rig = build_rig(tmp_path / name, FIRST)
        person_transcribes(rig, 0, FIRST)
        if coded:
            with_code(rig)
        settle(rig, Scripted({KEY: several(CODE, "0010007")}))
        runs.append(rig.specimen.run)
    plain, coded = runs
    assert coded.fields[KEY].state == ValueState.AMBIGUOUS and notes(coded) == []
    assert outcome(plain) == outcome(coded)


NOT_SUPPLIED = {
    # No value settled (rule 1's case) and a settled number that is not the code's (rule 2's).
    "open": ((PRINTED, OTHER), several(CODE, "0010007")),
    "another-number": ((OTHER,), catalogue("0010007", "0010007")),
}


@pytest.mark.parametrize("payload", ["0010", "0010001234", "001000a", " 0010001", "FMNHINS 0010001"])
@pytest.mark.parametrize("scenario", NOT_SUPPLIED)
def test_a_payload_that_is_no_whole_well_formed_number_changes_nothing(tmp_path, monkeypatch, scenario, payload):
    """The rule acts only on a payload that is itself a well-formed catalogue number: too short,
    too long, not digits, or digits inside a longer text (a space, the prefix) settle nothing and
    mark nothing. barcode.stored_code already refuses every payload that is not seven digits; the
    rule's own check is tested by handing it the payload."""
    from specimen_digitization.application.barcode import StoredCode
    from specimen_digitization.field_research import catalogue_code

    texts, script = NOT_SUPPLIED[scenario]
    barcode_label(monkeypatch, *texts)
    plain = build_rig(tmp_path / "plain", FIRST)
    settle(plain, Scripted({KEY: script}))
    coded = build_rig(tmp_path / "coded", FIRST)
    row = with_code(coded)
    monkeypatch.setattr(catalogue_code, "stored_code", lambda run: StoredCode(row, payload))
    settle(coded, Scripted({KEY: script}))
    assert outcome(plain.specimen.run) == outcome(coded.specimen.run)
    assert rest(plain.specimen.run) == rest(coded.specimen.run)


@pytest.mark.parametrize("excerpt", [
    f"{KEY}: 00100012 (QR code read by zxing-cpp 3.1.1, ladder rung whole)",
    f"{KEY}: 001000 (QR code read by zxing-cpp 3.1.1, ladder rung whole)",
    f"{KEY}: FMNHINS 0010001 (QR code read by zxing-cpp 3.1.1, ladder rung whole)",
])
@pytest.mark.parametrize("scenario", NOT_SUPPLIED)
def test_a_stored_row_that_names_no_seven_digit_number_changes_nothing(tmp_path, monkeypatch, scenario, excerpt):
    """A code row whose excerpt names anything but exactly seven digits is no stored decode
    (barcode.stored_code): the run is as with no code row."""
    texts, script = NOT_SUPPLIED[scenario]
    barcode_label(monkeypatch, *texts)
    plain = build_rig(tmp_path / "plain", FIRST)
    settle(plain, Scripted({KEY: script}))
    coded = build_rig(tmp_path / "coded", FIRST)
    with_code(coded).excerpt = excerpt
    settle(coded, Scripted({KEY: script}))
    assert outcome(plain.specimen.run) == outcome(coded.specimen.run)


@pytest.mark.parametrize("where", ["another-image", "no-label-of-the-run"])
@pytest.mark.parametrize("scenario", NOT_SUPPLIED)
def test_a_code_row_that_is_not_on_a_label_of_this_runs_image_supplies_nothing(tmp_path, monkeypatch, scenario,
        where):
    """The code gives a number only from a row on one of the run's labels, of that label's image
    (as step.code_confirmed reads the row): a row of another image, or on a label the run does not
    hold, settles nothing and marks nothing. The rule is called itself, on the field as research
    left it: the record's integrity check refuses such a row before any finalize. The same row on
    the run's own label supplies the number (the control)."""
    from specimen_digitization.field_research import catalogue_code
    from specimen_digitization.field_research import step as field_step

    texts, script = NOT_SUPPLIED[scenario]
    rig = rig_with(tmp_path, monkeypatch, *texts)
    run = rig.specimen.run
    settle(rig, Scripted({KEY: script}))
    row = with_code(rig)
    own = (row.asset_id, row.region_id)
    if where == "another-image":
        row.asset_id = "another-asset"
    else:
        row.region_id = "a-label-the-run-does-not-hold"

    def state():
        return (run.fields[KEY].model_dump(), [finding.model_dump() for finding in run.findings])

    before = state()
    task = field_step.FieldTask(key=KEY, mandatory=True, current=run.fields[KEY], candidates=(), tools=())
    decision = {}
    assert catalogue_code.settle(run, task, field_step.run_readings(run), decision=decision) is False
    assert state() == before and decision == {}
    row.asset_id, row.region_id = own
    assert catalogue_code.settle(run, task, field_step.run_readings(run), decision=decision) is True
    assert number(run) == (ValueState.SUPPORTED, CODE)
    assert decision == {"rule": "barcode_supplies" if scenario == "open" else "barcode_over_readers"}


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


def rest(run):
    """Everything a person and the routing see but the catalogue number: every other field, and
    the findings, reasons and open reasons that do not name it. Left out with it: its own
    record-level reason (identifier_format) and the barcode label's unresolved_transcription,
    which the duplicate-label rule of autonomy S1 sets aside only while the field is held, so it
    comes back, as an open reason, once the code settles the field."""
    fields, found, reasons, _ = outcome(run)
    names = {region.id: f"L{index + 1}" for index, region in enumerate(run.regions)}
    opened = [reason.replace(reason.rpartition(":")[2], names.get(reason.rpartition(":")[2], reason.rpartition(":")[2]))
        for reason in run.open_reasons]

    def others(codes):
        return [code for code in codes if KEY not in code and code not in ("identifier_format",
            "unresolved_transcription:L2")]

    return ({key: value for key, value in fields.items() if key != KEY},
        [finding for finding in found if KEY not in finding[1]], others(reasons), others(opened))


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
    for part in ("confirm", "give"):
        monkeypatch.setattr(catalogue_code, part, lambda *args, **kwargs: False)
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
    for part in ("confirm", "give"):
        monkeypatch.setattr(catalogue_code, part, lambda *args, **kwargs: asked.append(args) or False)
    rig = rig_with(tmp_path, monkeypatch, PRINTED)
    with_code(rig)
    monkeypatch.setattr(field_step, "units_path", lambda run: False)
    settle(rig, Scripted())
    assert asked == []


def test_a_persons_field_decision_is_never_settled_on_the_code(tmp_path, monkeypatch):
    from specimen_digitization.field_research import catalogue_code
    from specimen_digitization.field_research import step as field_step

    asked = []
    for part in ("confirm", "give"):
        monkeypatch.setattr(catalogue_code, part, lambda *args, **kwargs: asked.append(args) or False)
    monkeypatch.setattr(field_step, "human_keys", lambda run: frozenset({KEY}))
    rig = rig_with(tmp_path, monkeypatch, PRINTED, OTHER)
    with_code(rig)
    settle(rig, Scripted({KEY: catalogue(CODE, CODE)}))
    assert asked == []


def test_a_persons_decision_at_the_endpoint_is_not_replaced_by_the_code_on_retry(tmp_path, monkeypatch):
    """Codex round 1 on PR #458, finding 1, through the real routes (no stubbed human_keys). The
    run holds the code row; research leaves the number open and the code gives it. A person then
    sets the field to ambiguous at the decision endpoint, which records the field on the run
    (Run.person_decided_fields) and not in the carry manifest step.human_keys reads. Retry, with
    attempts left, researches the open field again (main's task selection, unchanged), and the
    expert again leaves it open. The code stands aside from a field a person holds authority over
    (second_opinion.authority): the field stays open, as with no code row. At b5bdd290 the code's
    number replaced the person's decision."""
    from test_approval_and_research import act, queue_in_place, run_to_rest, save_by_hand
    from test_step import decide, mounted, review_client

    from specimen_digitization.application.domain import FieldValue
    from specimen_digitization.application.workflow import FIELD_RESEARCH

    rig = rig_with(tmp_path, monkeypatch, PRINTED, OTHER)
    rows = []

    def segment(run):
        rows.append(Evidence(kind="derived", asset_id=rig.specimen.asset.id, region_id=run.regions[1].id,
            source="barcode", locator="check:barcode_decode",
            excerpt=f"{KEY}: {CODE} (QR code read by zxing-cpp 3.1.1, ladder rung whole)"))
        run.evidence.append(rows[-1])

    save_by_hand(rig, segment, "segment-code")
    mounted(rig, Scripted({KEY: several(CODE, "0010007")}))
    first = run_to_rest(rig).run
    assert number(first) == (ValueState.SUPPORTED, CODE) and first.fields[KEY].evidence_ids == [rows[0].id]
    assert first.person_decided_fields == []
    client = review_client(rig)
    opened = FieldValue(state=ValueState.AMBIGUOUS, reason="A person: the label and the code differ here.")
    decided = decide(client, rig, "open-the-number", "field", target_id=KEY,
        after=opened.model_dump(mode="json", exclude={"evidence_ids"}), evidence_ids=[])
    assert decided.fields[KEY].state == ValueState.AMBIGUOUS and decided.person_decided_fields == [KEY]
    assert decided.disposition == Disposition.REVIEW
    queue_in_place(monkeypatch)
    retried = act(client, rig, "retry", "retry-the-number")
    assert FIELD_RESEARCH not in retried.run.completed_steps
    again = Scripted({KEY: several(CODE, "0010007")})
    mounted(rig, again)
    after = run_to_rest(rig).run
    assert KEY in again.calls
    value = after.fields[KEY]
    assert value.state == ValueState.AMBIGUOUS and number(after)[1] != CODE
    assert rows[0].id not in value.evidence_ids and rows[0].id not in value.evidence_relations
    assert notes(after) == [] and after.person_decided_fields == [KEY]
    assert after.disposition == Disposition.REVIEW and f"mandatory_unresolved:{KEY}" in after.reasons


@pytest.mark.parametrize("held", ["decided-at-the-endpoint", "a-locked-selection", "protected-by-a-reassessment"])
@pytest.mark.parametrize("scenario", ["open", "another-number"])
def test_the_code_stands_aside_from_every_record_of_a_persons_authority(tmp_path, monkeypatch, scenario, held):
    """The one function the second opinion reads a person's authority through
    (second_opinion.authority) decides here too: a field decided at the endpoint, a research
    selection a person locked, a field the location reassessment protects. On each, the code
    neither gives a number to an open field nor replaces a settled one, and marks nothing; with
    the record of authority removed, the same row gives the number (the control)."""
    from specimen_digitization.field_research import catalogue_code
    from specimen_digitization.field_research import second_opinion
    from specimen_digitization.field_research import step as field_step

    texts, script = NOT_SUPPLIED[scenario]
    rig = rig_with(tmp_path, monkeypatch, *texts)
    run = rig.specimen.run
    settle(rig, Scripted({KEY: script}))
    with_code(rig)
    if held == "decided-at-the-endpoint":
        second_opinion.decided(run, KEY)
    elif held == "a-locked-selection":
        run.dependencies[second_opinion.LOCKS] = {KEY: {"selection_id": "0" * 64, "evidence_id": "e"}}
    else:
        run.dependencies["location_reassessment"] = {"attempt": 2, "fields": [], "protected": [KEY]}
    assert KEY in second_opinion.authority(run, field_step.run_readings(run))

    def state():
        return (run.fields[KEY].model_dump(), [finding.model_dump() for finding in run.findings])

    before = state()
    task = field_step.FieldTask(key=KEY, mandatory=True, current=run.fields[KEY], candidates=(), tools=())
    decision = {}
    assert catalogue_code.settle(run, task, field_step.run_readings(run), decision=decision) is False
    assert state() == before and decision == {}
    run.person_decided_fields = []
    run.dependencies.pop(second_opinion.LOCKS, None)
    run.dependencies.pop("location_reassessment", None)
    assert catalogue_code.settle(run, task, field_step.run_readings(run), decision=decision) is True
    assert number(run) == (ValueState.SUPPORTED, CODE)


def test_the_codes_number_changes_no_other_fields_check_and_asks_no_expert_again(tmp_path):
    """Codex round 1 on PR #458, finding 2, its exact case. The code is 0010001, research settles
    no catalogue number, and both readers write "E. slope Mt. McKinley" over "Davao Prov. 0010001".
    The extent check abstains: the next line holds a number no settled field accounts for. The
    code gives the catalogue number as the last act on the run, after the check stage and after
    the re-ask's trial, so neither sees its digits: the precise location's value, reason and
    findings, every other field, and the number of expert requests are those of a run with no code
    row (which is main's outcome, as main's rule leaves an open number alone). At b5bdd290 the
    supplied literal was blanked from the next line, the precise location was marked
    precise_location_extent and its expert was asked a second time."""
    from test_elevations_and_extent import DAVAO_AND_PI, LACKS as NOT_THERE, extent_marks
    from test_handled_before_marked import CUT, FIELDS, locality, seen, settle_reasking

    text = "E. slope Mt. McKinley\nDavao Prov. 0010001\nMindanao, P.I.\n3 Sept. '46\nF.G. Werner"
    runs = {}
    for name in ("plain", "coded"):
        rig = build_rig(tmp_path / name, text)
        script = locality(CUT)
        resolver = Scripted({**{key: answering(NOT_THERE) for key in FIELDS}, **DAVAO_AND_PI,
            "precise_location": script})
        code = with_code(rig, region=0) if name == "coded" else None
        settle_reasking(rig, resolver)
        runs[name] = (rig.specimen.run, script.asked, list(resolver.calls), code)
    (plain, plain_asked, plain_calls, _), (coded, coded_asked, coded_calls, code) = runs["plain"], runs["coded"]
    assert plain.fields[KEY].state != ValueState.SUPPORTED and extent_marks(plain) == []
    assert plain.fields["province_state"].literal == "Davao Prov." and plain.fields["precise_location"].literal == CUT
    # The code gave the number, and nothing else moved.
    assert summary(coded) == (ValueState.SUPPORTED, CODE, CODE, None, "settled")
    assert coded.fields[KEY].evidence_ids == [code.id]
    assert seen(coded) == seen(plain) and extent_marks(coded) == []
    assert coded_asked == plain_asked == [None]
    assert sorted(coded_calls) == sorted(plain_calls)
    names = {coded.regions[0].id: "L1", plain.regions[0].id: "L1"}

    def others(run):
        def plainly(text):
            for region, name in names.items():
                text = text.replace(region, name)
            return text

        return ({key: (value.state, value.literal, value.parsed, value.normalized, value.layer, value.reason)
                for key, value in run.fields.items() if key != KEY},
            sorted((f.rule_id, plainly(f.reason_code), f.severity) for f in run.findings if f.field_key != KEY))

    assert others(coded) == others(plain)


def test_the_rule_changes_no_approved_value(tmp_path, monkeypatch):
    """#450 records a digest of the values a person approved and withdraws the approval when
    they change. A confirmation (rule 3) changes no value layer, so it leaves the digest, and the
    approval, as they were."""
    from specimen_digitization.application.lane import approved_values_digest
    from specimen_digitization.field_research import catalogue_code
    from specimen_digitization.field_research import step as field_step

    rig = rig_with(tmp_path, monkeypatch, PRINTED)
    run = rig.specimen.run
    images(rig, lambda unit: UNCERTAIN)
    settle(rig, Scripted({KEY: catalogue(CODE, CODE)}))
    run.human_approved = True
    run.approved_values_sha256 = approved_values_digest(run)
    with_code(rig)
    task = field_step.FieldTask(key=KEY, mandatory=True, current=run.fields[KEY], candidates=(), tools=())
    assert catalogue_code.settle(run, task, field_step.run_readings(run))
    assert approved_values_digest(run) == run.approved_values_sha256
    field_step.finalize_fields(run, None, (), specimen=rig.specimen, blobs=rig.blobs, today=rig_module.TODAY)
    assert run.human_approved is True


def test_a_number_the_code_gives_is_never_shown_as_approved_by_a_person(tmp_path, monkeypatch):
    """A person approved the record while its number was open; a later attempt researches the
    open field again and the code gives the number. The approval was given for other values
    (#450's digest), so it is withdrawn at the finalize, as for any value research changes after
    an approval: the record clears by the system's rules and is not shown as approved by a person."""
    from specimen_digitization.application.lane import approved_values_digest

    rig = rig_with(tmp_path, monkeypatch, PRINTED, OTHER)
    run = rig.specimen.run
    settle(rig, Scripted({KEY: several(CODE, "0010007")}))
    assert run.fields[KEY].state == ValueState.AMBIGUOUS
    run.human_approved = True
    run.approved_values_sha256 = approved_values_digest(run)
    code = with_code(rig)
    settle(rig, Scripted({KEY: several(CODE, "0010007")}))
    supplied(run, code)
    assert run.human_approved is False


def test_the_hold_code_is_the_one_the_app_words():
    """The app words this exact code (the client's blockers.dart barcodeDiffersWords and
    settlement_codes.dart markedReasonWords; its barcode_differs_test.dart). Pinned here as a plain
    string, never by reading the app's files."""
    from specimen_digitization.field_research import catalogue_code
    from specimen_digitization.field_research.step import marked_code

    assert catalogue_code.DIFFERS == "barcode_differs"
    assert marked_code(KEY, "L1", catalogue_code.DIFFERS) == "marked:fmnh_ins_number:L1:barcode_differs"
