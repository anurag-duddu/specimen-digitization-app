"""The slide's QR code (application/barcode.py) checked against the catalogue number, for that field alone.

The segment step stores an accepted decode of the slide's QR code as one evidence row
(barcode.record), on the label whose box holds the code. When the run holds one, the
catalogue number (fmnh_ins_number) is compared with it after the field's expert answer has
been applied and its labels' settlement recorded (step.apply_outcomes calls settle). The
expert is not told the decode. The code is compared only with what field research settled or
proposed for the field: the settled value, and the field's candidates (the organiser's
candidates, the readers' verbatims the value keeps, the expert's literal and options), each
read as a catalogue number by field_validators.CATALOG, the normalisation
check_catalog_number uses. It does not read the readers' texts for numbers of its own, and it
does not supply a value that no reader wrote and field research did not propose.

1. Confirm. The field settled on a value whose literal writes the code whole (written_whole),
   a reading of the code's label writes the code whole, and the value's parsed and normalized
   layers are supported without the code (_unsupported_layers): the code is a clearing backing
   of the SOURCE class (FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4, rule 3), so the
   field's marked findings (text_only, conflict) become one cleared finding on the code's
   label, the code row is cited as deciding it, and the reason says the code confirms the
   number in place of the mark's sentence. Where the literal writes the code whole but either
   other condition fails, nothing changes.
2. Break a tie. The field is ambiguous or unresolved, the code's number is one of its
   candidates' numbers, and a reading of the code's label writes the code's seven digits as a
   whole number (written_whole: no digit right before or after them): the field settles on
   those digits, cited where those readings write them, backed by the code, and the other
   candidates are named in the reason as ruled out.
3. Contradict. The field settled on a value whose literal does not write the code whole,
   whatever its parsed layer reads: the value stays, and is marked for a person
   (marked:fmnh_ins_number:<label>:barcode_differs, one of the run's reasons), whatever its
   readers. The code row is cited by the mark only, never by the value.
4. Otherwise nothing changes: no candidate's number is the code's, no value settled, no stored
   decode, a field a person decided (step.human_keys: settle is not called), a run not on the
   units path, or a run with a transcript a person decided on any of its labels
   (Reading.person_decided). In that last case, where the settled value's number is not the
   code's, the value's reason says so and an info finding (PERSON_DIFFERS) cites the code row.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence

from specimen_digitization.application.barcode import FIELD, stored_code
from specimen_digitization.application.domain import FieldValue, RunFinding, ValueState
from specimen_digitization.application.field_validators import CATALOG

from .contracts import FieldOutcome, FieldTask, Reading

DIFFERS = "barcode_differs"
# The rule's own findings (info, never a reason): the candidates a tie-break ruled out, and a
# settled value a person's transcript backs whose number is not the code's.
RULE = "barcode_decode"
RULE_VERSION = "catalogue-number-barcode-v3"
RULED_OUT = "barcode_ruled_out:" + FIELD
PERSON_DIFFERS = "barcode_person_differs:" + FIELD
SETTLED = ("settled", "verbatim")


def number(text: str | None) -> str | None:
    """A text's catalogue number, as check_catalog_number reads it (CATALOG), or None."""
    match = CATALOG.fullmatch(text) if text else None
    return match["digits"] if match else None


def written_whole(text: str, payload: str) -> bool:
    """Whether the text writes the code's digits as a whole number, decided on a projection of
    the text that keeps only its letters and numbers (Unicode general categories L* and N*;
    spaces, line breaks, punctuation, marks and format characters are deleted): the code's
    ASCII digits occur in the projection with no numeric character directly before or after
    them (category N*, or str.isnumeric, which also counts CJK numerals). So nothing invisible
    or separating can stand between the code and another number. It is deliberately
    conservative: a code after an unrelated number across a space ("12 0010001") is refused
    too, and the field then stays open as it would without the code. Letters are not digits."""
    if not (payload.isascii() and payload.isdigit()):
        return False
    kept = "".join(ch for ch in text if unicodedata.category(ch)[0] in "LN")

    def numeric(ch: str) -> bool:
        return unicodedata.category(ch)[0] == "N" or ch.isnumeric()

    start = kept.find(payload)
    while start >= 0:
        end = start + len(payload)
        if not (start and numeric(kept[start - 1])) and not (end < len(kept) and numeric(kept[end])):
            return True
        start = kept.find(payload, start + 1)
    return False


def candidate_texts(task: FieldTask, value: FieldValue, outcomes: Iterable[FieldOutcome | None]) -> list[str]:
    """The texts field research holds for the field: the organiser's candidates, the readers'
    verbatims and literal the value keeps, and the expert's literal and options."""
    texts = [candidate.literal for candidate in task.candidates]
    texts += [*value.verbatim_by_observation.values(), *([value.literal] if value.literal else [])]
    for outcome in outcomes:
        answer = outcome.answer if outcome is not None else None
        if answer is not None and answer.outcome != "label_lacks_value":
            texts += [text for text in (answer.literal, *answer.options) if text]
    return list(dict.fromkeys(text for text in texts if text and text.strip()))


MARK_NOTE = " Marked for a person: "


def _without_mark_note(reason: str) -> str:
    """The value's reason without the sentence step._settlement appends for a marked label
    ("Marked for a person: ..."), which the code's own finding replaces."""
    head, found, _ = (" " + reason).partition(MARK_NOTE)
    return head.strip() if found else reason


def _unsupported_layers(run, value: FieldValue) -> bool:
    """Whether the value's parsed or normalized layer differs from its literal with no cited row
    supporting it, as step.scientific_reasons tests it (unsupported_parsed, unsupported_normalized)."""
    rows = {row.id: row for row in run.evidence}
    cited = [rows[i] for i in value.evidence_ids if i in rows]
    return any(text and text != value.literal and not any(
        row.kind in {"authority", "authority_selection", "derived", "lookup"} and text in row.excerpt
        for row in cited) for text in (value.parsed, value.normalized))


def _marked_regions(run) -> list[str]:
    from .step import SETTLEMENT

    return list(dict.fromkeys(finding.reason_code.split(":")[2] for finding in run.findings
        if finding.rule_id == SETTLEMENT and finding.field_key == FIELD
        and finding.reason_code.count(":") >= 2))


def settle(run, task: FieldTask, readings: Sequence[Reading], *, asset_id, blobs,
        outcomes: Iterable[FieldOutcome | None] = (), decision: dict | None = None) -> bool:
    """Compare the catalogue number with the run's stored decode by the module's rules 1 to 3;
    False, changing nothing, where rule 4 leaves the field as it is."""
    from .step import SETTLEMENT, SETTLEMENT_RULES, _lineage, _literal_row, cleared_code, marked_code

    code = stored_code(run)
    if code is None or task.key != FIELD or code.row.region_id is None:
        return False
    payload, current = code.payload, run.fields.get(FIELD) or FieldValue()
    decision = {} if decision is None else decision
    settled = current.state == ValueState.SUPPORTED and current.layer in SETTLED
    if any(reading.person_decided for reading in readings):
        # Rule 4: a person decided a transcript of the record; the code only notes a difference.
        if settled and number(current.normalized or current.parsed or current.literal) != payload:
            value = current.model_copy(deep=True)
            value.reason = " ".join(part for part in (value.reason, f"The slide's QR code reads {payload}, "
                "which differs from this value; a person's transcription stands.") if part)
            run.fields[FIELD] = value
            run.findings.append(RunFinding(rule_id=RULE, rule_version=RULE_VERSION, severity="info",
                field_key=FIELD, reason_code=PERSON_DIFFERS, evidence_ids=[code.row.id]))
            decision["rule"] = "person_over_barcode"
            return True
        return False
    if settled:
        regions = _marked_regions(run) or [code.row.region_id]
        value = current.model_copy(deep=True)
        if written_whole(current.literal or "", payload):
            whole_on_label = any(reading.region_id == code.row.region_id and written_whole(reading.text, payload)
                for reading in readings)
            if not whole_on_label or _unsupported_layers(run, current):
                # No reading of the code's label writes it whole, or the value's own parsed or
                # normalized layer is unsupported: the field stays as it is with no code (the code
                # does not stand in for missing support).
                return False
            # Rule 1: the code confirms the number the label writes.
            run.findings[:] = [finding for finding in run.findings
                if not (finding.rule_id == SETTLEMENT and finding.field_key == FIELD)]
            value.evidence_relations[code.row.id] = "decides"
            value.evidence_ids = list(dict.fromkeys([*value.evidence_ids, code.row.id]))
            value.reason = " ".join(part for part in (_without_mark_note(value.reason),
                f"The slide's QR code confirms this number, {payload}.") if part)
            run.fields[FIELD] = value
            run.findings.append(RunFinding(rule_id=SETTLEMENT, rule_version=SETTLEMENT_RULES, severity="info",
                field_key=FIELD, reason_code=cleared_code(FIELD, code.row.region_id),
                evidence_ids=[e for e, how in value.evidence_relations.items() if how in ("supports", "decides")]))
            decision["rule"] = "barcode_confirms"
            return True
        # Rule 3: the label's number, as the literal writes it, is not the code written whole
        # (whatever the value's parsed layer reads): the value stays, marked for a person. The code
        # row is cited by the mark alone, so it supports none of the value's layers.
        run.findings[:] = [finding for finding in run.findings
            if not (finding.rule_id == SETTLEMENT and finding.field_key == FIELD)]
        value.reason = " ".join(part for part in (_without_mark_note(value.reason), f"The slide's QR code reads "
            f"{payload}, which differs from the number the label writes. A person compares the label with the "
            "code.") if part)
        run.fields[FIELD] = value
        for region in regions:
            run.findings.append(RunFinding(rule_id=SETTLEMENT, rule_version=SETTLEMENT_RULES, severity="warning",
                field_key=FIELD, reason_code=marked_code(FIELD, region, DIFFERS), evidence_ids=[code.row.id]))
        decision["rule"] = DIFFERS
        return True
    if current.state not in (ValueState.AMBIGUOUS, ValueState.UNRESOLVED):
        return False
    # Rule 2: the code breaks a tie among the field's candidates.
    texts = candidate_texts(task, current, outcomes)
    numbers = {text: number(text) for text in texts}
    # Eligible only when a candidate's number is the code's and a reading of the code's label
    # writes the code as a whole number (written_whole): a candidate clipped from a longer
    # number ("0010001" of "10010001") is not.
    named = [reading for reading in readings
        if reading.region_id == code.row.region_id and written_whole(reading.text, payload)]
    if not named or payload not in numbers.values():
        return False
    chosen = payload
    relations: dict[str, str] = {}
    for reading in named:
        row = _literal_row(FIELD, reading, chosen, asset_id, blobs)
        run.evidence.append(row)
        relations[row.id] = "supports"
    relations[code.row.id] = "decides"
    others = list(dict.fromkeys(digits for digits in numbers.values() if digits and digits != payload))
    note = f"The slide's QR code reads {payload}, which settles this field among its candidates."
    if others:
        note += " Ruled out: " + "; ".join(others) + "."
    run.fields[FIELD] = FieldValue(state=ValueState.SUPPORTED, literal=chosen, parsed=payload, layer="settled",
        evidence_ids=list(relations), evidence_relations=relations, reason=note, **_lineage(named, chosen))
    run.findings[:] = [finding for finding in run.findings
        if not (finding.rule_id == SETTLEMENT and finding.field_key == FIELD)]
    run.findings.append(RunFinding(rule_id=SETTLEMENT, rule_version=SETTLEMENT_RULES, severity="info",
        field_key=FIELD, reason_code=cleared_code(FIELD, code.row.region_id), evidence_ids=list(relations)))
    if others:
        run.findings.append(RunFinding(rule_id=RULE, rule_version=RULE_VERSION, severity="info", field_key=FIELD,
            reason_code=RULED_OUT, evidence_ids=[code.row.id]))
    decision["rule"] = "barcode_breaks_tie"
    return True
