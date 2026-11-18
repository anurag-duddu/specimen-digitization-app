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

1. Confirm. The field settled on a value whose number is the code's: the code is a clearing
   backing of the SOURCE class (FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4, rule 3),
   so the field's marked findings (text_only, conflict) become one cleared finding on the
   code's label, and the code row is cited as deciding it. identifier_format does not arise:
   the value's number fullmatches CATALOG.
2. Break a tie. The field is ambiguous or unresolved, and the code's number is one of its
   candidates' numbers, written so by a reading: the field settles on that candidate as the
   reading writes it, backed by the code, and the other candidates are named in the reason as
   ruled out.
3. Contradict. The field settled on a value whose number is not the code's: the value stays,
   and is marked for a person (marked:fmnh_ins_number:<label>:barcode_differs, one of the
   run's reasons), whatever its readers.
4. Otherwise nothing changes: no candidate's number is the code's, no value settled, no stored
   decode, a field a person decided (step.human_keys: settle is not called), a run not on the
   units path, or a run with a transcript a person decided on any of its labels
   (Reading.person_decided). In that last case, where the settled value's number is not the
   code's, the value's reason says so and an info finding (PERSON_DIFFERS) cites the code row.
"""

from __future__ import annotations

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
        held = number(current.normalized or current.parsed or current.literal)
        regions = _marked_regions(run) or [code.row.region_id]
        value = current.model_copy(deep=True)
        run.findings[:] = [finding for finding in run.findings
            if not (finding.rule_id == SETTLEMENT and finding.field_key == FIELD)]
        if held == payload:
            # Rule 1: the code confirms the value.
            value.evidence_relations[code.row.id] = "decides"
            value.evidence_ids = list(dict.fromkeys([*value.evidence_ids, code.row.id]))
            value.reason = " ".join(part for part in (value.reason,
                f"The slide's QR code reads {payload} too.") if part)
            run.fields[FIELD] = value
            run.findings.append(RunFinding(rule_id=SETTLEMENT, rule_version=SETTLEMENT_RULES, severity="info",
                field_key=FIELD, reason_code=cleared_code(FIELD, code.row.region_id),
                evidence_ids=[e for e, how in value.evidence_relations.items() if how in ("supports", "decides")]))
            decision["rule"] = "barcode_confirms"
            return True
        # Rule 3: the code contradicts the settled value; the value stays, marked for a person.
        value.evidence_relations[code.row.id] = "contradicts"
        value.evidence_ids = list(dict.fromkeys([*value.evidence_ids, code.row.id]))
        value.reason = " ".join(part for part in (value.reason, f"The slide's QR code reads {payload}, "
            f"which differs from this value. A person compares the label with the code.") if part)
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
    chosen = next((text for text in texts if numbers[text] == payload
        and any(text in reading.text for reading in readings)), None)
    if chosen is None:
        return False
    named = [reading for reading in readings if chosen in reading.text]
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
