"""The catalogue number from the slide's QR code (application/barcode.py), for that field alone.

The segment step stores an accepted decode of the slide's QR code as one evidence row
(barcode.record), on the label whose box holds the code. When the run holds one, the catalogue
number (fmnh_ins_number) is settled on it after its expert's answer has been applied and its
labels' settlement recorded (step.apply_outcomes calls settle). The expert is not told the
decode: its readers and the code stay two independent readings of the same printed number.

What a reader of the code's label wrote is read digit by digit (_written): each run of digits
its text writes, digits joined across spaces and line breaks as readers' texts are compared for
agreement (agreement.agreement_key: "001 0007" and "001\\n0007" are 0010007), each kept with the
text as the reader wrote it, which is the evidence. A reader agrees with the code when one of
its runs is the code's number; disagrees when it writes digits and none of its runs is the
code's number (a partial, six or eight digits, a number broken around a letter such as "O" for
"0": digits a reader wrote are never silence); and is silent when its text holds no digit.
The rules:

0. A person decided the label's transcript (Reading.person_decided): a person outranks the
   code. The code decides nothing; where the person's digits differ from the code's, the
   value's reason says so and an info finding (PERSON_DIFFERS) cites the code row.
1. A reader agrees: the value is the code's number, cleared. The code is a SOURCE-class
   backing (FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4, rule 3), so one reader, or
   readers that agree and no image (text_only), are enough.
2. A reader disagrees alone (no other reader of the label wrote the same run): it is ruled
   out, cited as contradicting the value, and named in the value's reason. A note, not a hold.
3. Two or more readers that disagree wrote the same run (MIN_BACKING_READERS): the code and the
   readers disagree, and a person decides. The field is ambiguous, with both numbers as its
   options, the warning finding marked:fmnh_ins_number:<label>:barcode_differs (one of the
   run's reasons, step.marked_reasons) and a reason that says so in plain words.
4. Every reader is silent: the code's number is the value, cleared.
5. No stored decode, a decode placed on no label (or on a label nobody read), a field a person
   decided, or a run not on the units path: nothing here runs, and the field is exactly what
   its expert's answer made it.

The stored value is the seven digits, as the field stores every catalogue number
(checks.check_catalog_number's catalog_number; tests/fixtures/field_model_pilot_rows.json);
its literal is the number as the first agreeing reader writes it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from specimen_digitization.application.barcode import FIELD, stored_code
from specimen_digitization.application.domain import FieldValue, RunFinding, ValueState
from specimen_digitization.application.field_validators import CATALOG

from .contracts import FieldTask, Reading

# A run of digits as a reader writes it: digits, and the spaces or line breaks between them.
DIGIT_RUN = re.compile(r"[0-9](?:\s*[0-9])*")
DIFFERS = "barcode_differs"
# The rule's own findings (info, never a reason): the readings it ruled out, and a person's
# transcription whose number differs from the code's.
RULE = "barcode_decode"
RULE_VERSION = "catalogue-number-barcode-v2"
RULED_OUT = "barcode_ruled_out:" + FIELD
PERSON_DIFFERS = "barcode_person_differs:" + FIELD


def _written(text: str) -> list[tuple[str, str]]:
    """Each run of digits a reading's text writes, as (the text as written, its digits): the
    digits are the run's agreement_key, as readers' texts are compared for agreement."""
    from .agreement import agreement_key

    return [(match.group(), agreement_key(match.group())) for match in DIGIT_RUN.finditer(text)]


def _digits(value: FieldValue) -> str | None:
    for text in (value.normalized, value.parsed, value.literal):
        if text and (match := CATALOG.fullmatch(text)):
            return match["digits"]
    return None


def _row(run, value: FieldValue, reading: Reading, written: str, *, asset_id, blobs) -> str:
    """A literal row of the field for `written` in `reading`: one the value already cites,
    else a new one (step._literal_row)."""
    from .step import _literal_row

    rows = {row.id: row for row in run.evidence}
    for evidence_id in value.evidence_ids:
        row = rows.get(evidence_id)
        if (row is not None and row.kind == "literal" and row.region_id == reading.region_id
                and reading.observation_id in row.observation_ids and written in row.excerpt):
            return row.id
    row = _literal_row(FIELD, reading, written, asset_id, blobs)
    run.evidence.append(row)
    return row.id


def _readers(readings: Sequence[Reading]) -> str:
    names = [reading.name for reading in readings]
    return (f"reader {names[0]}" if len(names) == 1
        else "readers " + ", ".join(names[:-1]) + " and " + names[-1])


def settle(run, task: FieldTask, readings: Sequence[Reading], *, asset_id, blobs,
        decision: dict | None = None) -> bool:
    """Settle the catalogue number on the run's stored decode by the module's rules 0 to 4;
    False, changing nothing, where rule 5 leaves the field as it is."""
    from .agreement import MIN_BACKING_READERS
    from .step import SETTLEMENT, SETTLEMENT_RULES, _lineage, _unsettled, cleared_code, marked_code, transcript_code

    code = stored_code(run)
    if code is None or task.key != FIELD or code.row.region_id is None:
        return False
    pool = [reading for reading in readings if reading.region_id == code.row.region_id]
    if not pool:
        return False
    payload, current = code.payload, run.fields.get(FIELD) or FieldValue()
    decision = {} if decision is None else decision
    if person := [reading for reading in pool if reading.person_decided]:
        # Rule 0: a person's transcription binds its label; the code only notes a difference.
        theirs = list(dict.fromkeys(digits for reading in person for _, digits in _written(reading.text)))
        run.findings[:] = [finding for finding in run.findings
            if not (finding.field_key == FIELD and finding.rule_id == RULE)]
        if payload not in theirs:
            value = current.model_copy(deep=True)
            value.reason = " ".join(part for part in (value.reason, f"The slide's QR code reads {payload}; the "
                f"person's transcription of the label writes {', '.join(theirs) or 'no number'}.") if part)
            run.fields[FIELD] = value
            run.findings.append(RunFinding(rule_id=RULE, rule_version=RULE_VERSION, severity="info", field_key=FIELD,
                reason_code=PERSON_DIFFERS, evidence_ids=[code.row.id]))
        decision["rule"] = "person_over_barcode"
        return True
    # Who agrees, disagrees or is silent: one entry per observation.
    agreeing: list[tuple[Reading, str]] = []
    disagreeing: list[tuple[Reading, list[tuple[str, str]]]] = []
    seen: set[str] = set()
    for reading in pool:
        if reading.observation_id in seen:
            continue
        seen.add(reading.observation_id)
        runs = _written(reading.text)
        mine = next((written for written, digits in runs if digits == payload), None)
        if mine is not None:
            agreeing.append((reading, mine))
        elif runs:
            disagreeing.append((reading, runs))
    by_digits: dict[str, list[tuple[Reading, str]]] = {}
    for reading, runs in disagreeing:
        for written, digits in runs:
            writers = by_digits.setdefault(digits, [])
            if all(other.observation_id != reading.observation_id for other, _ in writers):
                writers.append((reading, written))
    agreed = sorted((digits for digits, writers in by_digits.items() if len(writers) >= MIN_BACKING_READERS),
        key=lambda digits: (-len(digits), digits))
    run.findings[:] = [finding for finding in run.findings if not (finding.field_key == FIELD
        and finding.rule_id in (SETTLEMENT, RULE))]
    if agreed:
        # Rule 3: the code and the readers' eyes disagree.
        number = agreed[0]
        writers = by_digits[number]
        rows = [_row(run, current, reading, written, asset_id=asset_id, blobs=blobs) for reading, written in writers]
        reason = (f"The slide's QR code reads {payload}, but {_readers([r for r, _ in writers])} read {number}. "
            "The code and the readers disagree, so a person checks the label and its code. "
            f"Options: {payload}; {number}.")
        run.fields[FIELD] = _unsettled(task, ValueState.AMBIGUOUS, cited=[code.row.id, *rows], reason=reason)
        run.findings.append(RunFinding(rule_id=SETTLEMENT, rule_version=SETTLEMENT_RULES, severity="warning",
            field_key=FIELD, reason_code=marked_code(FIELD, code.row.region_id, DIFFERS),
            evidence_ids=[code.row.id, *rows]))
        decision["rule"] = DIFFERS
        return True
    keep = current.state == ValueState.SUPPORTED and current.layer in ("settled", "verbatim") and (
        _digits(current) == payload)
    if keep:
        value = current.model_copy(deep=True)
    else:
        # Rules 2 and 4, and rule 1 where the expert's answer settled no number or another: the code's
        # number, as the first agreeing reader writes it (the payload itself where a reader writes it so).
        literal = next((written for _, written in agreeing if written == payload),
            agreeing[0][1] if agreeing else payload)
        named = [reading for reading, written in agreeing if written == literal]
        value = FieldValue(state=ValueState.SUPPORTED, literal=literal, parsed=payload, layer="settled",
            reason="", **(_lineage(named, literal) if named else {}))
        run.findings[:] = [finding for finding in run.findings
            if not (finding.field_key == FIELD and finding.reason_code == transcript_code(FIELD))]
        for reading, written in agreeing:
            row = _row(run, current, reading, written, asset_id=asset_id, blobs=blobs)
            value.evidence_relations.setdefault(row, "supports")
    value.evidence_relations[code.row.id] = "decides"
    ruled_out = []
    for reading, runs in disagreeing:
        for written, _ in runs:
            row = _row(run, value, reading, written, asset_id=asset_id, blobs=blobs)
            value.evidence_relations[row] = "contradicts"
            ruled_out.append(row)
    value.evidence_ids = list(dict.fromkeys([*value.evidence_ids, *value.evidence_relations]))
    note = f"The slide's QR code reads {payload}" + (
        f", which {_readers([r for r, _ in agreeing])} wrote too." if agreeing else ".")
    if disagreeing:
        note += " " + "; ".join(f"reader {reading.name} wrote {', '.join(digits for _, digits in runs)}"
            for reading, runs in disagreeing) + ", which the code rules out."
    value.reason = " ".join(part for part in (value.reason, note) if part)
    run.fields[FIELD] = value
    run.findings.append(RunFinding(rule_id=SETTLEMENT, rule_version=SETTLEMENT_RULES, severity="info",
        field_key=FIELD, reason_code=cleared_code(FIELD, code.row.region_id),
        evidence_ids=[e for e, how in value.evidence_relations.items() if how in ("supports", "decides")]))
    if ruled_out:
        run.findings.append(RunFinding(rule_id=RULE, rule_version=RULE_VERSION, severity="info", field_key=FIELD,
            reason_code=RULED_OUT, evidence_ids=list(dict.fromkeys(ruled_out))))
    decision["rule"] = "barcode_decides"
    return True
