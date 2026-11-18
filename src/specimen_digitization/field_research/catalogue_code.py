"""The catalogue number from the slide's QR code (application/barcode.py), for that field alone.

The segment step stores an accepted decode of the slide's QR code as one evidence row
(barcode.record). When the run holds one, the catalogue number (fmnh_ins_number) is settled
on it after its expert's answer has been applied and its labels' settlement recorded
(step.apply_outcomes calls settle). The expert is not told the decode: its readers and the
code stay two independent readings of the same printed number, and the code decides between
them by these rules:

1. A reader writes the number the code holds: the value is that number, cleared. The code
   is a SOURCE-class backing (FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4, rule 3),
   so one reader, or readers that agree and no image (text_only), are enough.
2. Readers write a different number, each alone on its label: the code's number is the value,
   cleared; each differing reading is cited as contradicting it, and the value's reason names
   them as ruled out. That is a note, not a hold.
3. Two or more readers of one label agree on a number that differs from the code
   (MIN_BACKING_READERS): the code and the readers disagree, and a person decides. The field
   is ambiguous, with both numbers as its options, the warning finding
   marked:fmnh_ins_number:<label>:barcode_differs (which is one of the run's reasons,
   step.marked_reasons) and a reason that says so in plain words.
4. No reader writes a number: the code's number is the value, cleared.
5. No stored decode, a field a person decided, or a run not on the units path: nothing here
   runs, and the field is exactly what its expert's answer made it.

A reader's numbers are the runs of five to nine digits its text writes as a number of their
own (NUMBER: no digit, and no digit beyond one separator, on either side), as
field_validators.CATALOG reads a catalogue number; on the label the code lies on when the
decode places it on one (the code row's region_id) and that label was read, else on every
label. The stored value is the seven digits alone, as the field stores every catalogue number
(checks.check_catalog_number's catalog_number; tests/fixtures/field_model_pilot_rows.json).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from specimen_digitization.application.barcode import FIELD, StoredCode, stored_code
from specimen_digitization.application.domain import Evidence, FieldValue, RunFinding, ValueState
from specimen_digitization.application.field_validators import CATALOG

from .contracts import FieldTask, Reading

NUMBER = re.compile(r"(?<![0-9])(?<![0-9][.,/:-])[0-9]{5,9}(?![0-9])(?![.,/:-][0-9])")
DIFFERS = "barcode_differs"
# The rule's own findings: the readings it ruled out (info, never a reason).
RULE = "barcode_decode"
RULE_VERSION = "catalogue-number-barcode-v1"
RULED_OUT = "barcode_ruled_out:" + FIELD


def numbers(text: str) -> list[tuple[int, int, str]]:
    """The numbers a reading's text writes, as (start, end, digits) (NUMBER)."""
    return [(match.start(), match.end(), match.group()) for match in NUMBER.finditer(text)]


def _digits(value: FieldValue) -> str | None:
    for text in (value.normalized, value.parsed, value.literal):
        if text and (match := CATALOG.fullmatch(text)):
            return match["digits"]
    return None


def _pool(code: StoredCode, readings: Sequence[Reading]) -> list[Reading]:
    """The readings whose numbers count: the code's label's, when it has readings, else all."""
    own = [reading for reading in readings if reading.region_id == code.row.region_id]
    return own if code.row.region_id is not None and own else list(readings)


def _row(run, value: FieldValue, reading: Reading, number: str, *, asset_id, blobs) -> str:
    """A literal row of the field for `number` in `reading`: one the value already cites,
    else a new one (step._literal_row)."""
    from .step import _literal_row

    rows = {row.id: row for row in run.evidence}
    for evidence_id in value.evidence_ids:
        row = rows.get(evidence_id)
        if (row is not None and row.kind == "literal" and row.region_id == reading.region_id
                and reading.observation_id in row.observation_ids and number in row.excerpt):
            return row.id
    row = _literal_row(FIELD, reading, number, asset_id, blobs)
    run.evidence.append(row)
    return row.id


def _names(readings: Sequence[Reading]) -> str:
    names = [reading.name for reading in readings]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _readers_of(found: Mapping[str, list[Reading]], number: str) -> str:
    return f"reader {_names(found[number])}" if len(found[number]) == 1 else f"readers {_names(found[number])}"


def settle(run, task: FieldTask, readings: Sequence[Reading], *, asset_id, blobs,
        decision: dict | None = None) -> bool:
    """Settle the catalogue number on the run's stored decode by the module's rules 1 to 4;
    False, changing nothing, where rule 5 leaves the field as it is."""
    from .agreement import MIN_BACKING_READERS
    from .step import SETTLEMENT, SETTLEMENT_RULES, _lineage, _unsettled, cleared_code, marked_code, transcript_code

    code = stored_code(run)
    if code is None or task.key != FIELD:
        return False
    payload, current = code.payload, run.fields.get(FIELD) or FieldValue()
    decision = {} if decision is None else decision
    pool = _pool(code, readings)
    # Each number the readings write, and the readings (one per observation) that write it.
    found: dict[str, list[Reading]] = {}
    for reading in pool:
        for _, _, number in numbers(reading.text):
            writers = found.setdefault(number, [])
            if all(other.observation_id != reading.observation_id for other in writers):
                writers.append(reading)
    differing = {number: writers for number, writers in found.items() if number != payload}
    agreed = {number: writers for number, writers in differing.items()
        if len({reading.observation_id for reading in writers}) >= MIN_BACKING_READERS}
    run.findings[:] = [finding for finding in run.findings if not (finding.field_key == FIELD
        and finding.rule_id in (SETTLEMENT, RULE))]
    if agreed:
        # Rule 3: the code and the readers' eyes disagree.
        number = next(iter(agreed))
        rows = [_row(run, current, reading, number, asset_id=asset_id, blobs=blobs) for reading in agreed[number]]
        options = [payload, *agreed]
        reason = (f"The slide's QR code reads {payload}, but {_readers_of(agreed, number)} read {number}. "
            "The code and the readers disagree, so a person checks the label and its code. "
            f"Options: {'; '.join(options)}.")
        value = _unsettled(task, ValueState.AMBIGUOUS, cited=[code.row.id, *rows], reason=reason)
        run.fields[FIELD] = value
        run.findings.append(RunFinding(rule_id=SETTLEMENT, rule_version=SETTLEMENT_RULES, severity="warning",
            field_key=FIELD, reason_code=marked_code(FIELD, agreed[number][0].region_id, DIFFERS),
            evidence_ids=[code.row.id, *rows]))
        decision["rule"] = DIFFERS
        return True
    named = found.get(payload, [])
    keep = current.state == ValueState.SUPPORTED and current.layer in ("settled", "verbatim") and (
        _digits(current) == payload)
    if keep:
        value = current.model_copy(deep=True)
    else:
        # Rules 2 and 4, and rule 1 where the expert's answer settled no number or another.
        value = FieldValue(state=ValueState.SUPPORTED, literal=payload, parsed=payload, layer="settled",
            reason="", **(_lineage(named, payload) if named else {}))
        run.findings[:] = [finding for finding in run.findings
            if not (finding.field_key == FIELD and finding.reason_code == transcript_code(FIELD))]
        for reading in named:
            row = _row(run, current, reading, payload, asset_id=asset_id, blobs=blobs)
            value.evidence_relations.setdefault(row, "supports")
    value.evidence_relations[code.row.id] = "decides"
    ruled_out = []
    for number, writers in differing.items():
        for reading in writers:
            row = _row(run, value, reading, number, asset_id=asset_id, blobs=blobs)
            value.evidence_relations[row] = "contradicts"
            ruled_out.append(row)
    value.evidence_ids = list(dict.fromkeys([*value.evidence_ids, *value.evidence_relations]))
    note = f"The slide's QR code reads {payload}" + (
        f", which {_readers_of(found, payload)} wrote too." if named else ".")
    if differing:
        note += " " + "; ".join(f"{_readers_of(differing, number)} wrote {number}" for number in differing) + (
            ", which the code rules out.")
    value.reason = " ".join(part for part in (value.reason, note) if part)
    run.fields[FIELD] = value
    region = code.row.region_id or (named[0].region_id if named else None)
    if region is not None:
        run.findings.append(RunFinding(rule_id=SETTLEMENT, rule_version=SETTLEMENT_RULES, severity="info",
            field_key=FIELD, reason_code=cleared_code(FIELD, region),
            evidence_ids=[e for e, how in value.evidence_relations.items() if how in ("supports", "decides")]))
    if ruled_out:
        run.findings.append(RunFinding(rule_id=RULE, rule_version=RULE_VERSION, severity="info", field_key=FIELD,
            reason_code=RULED_OUT, evidence_ids=ruled_out))
    decision["rule"] = "barcode_decides"
    return True
