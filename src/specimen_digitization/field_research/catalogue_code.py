"""The slide's QR code (application/barcode.py) checked against the catalogue number, for that field alone.

The segment step stores an accepted decode of the slide's QR code as one evidence row
(barcode.record), on the label whose box holds the code. When the run holds one, the
catalogue number (fmnh_ins_number) is compared with it after the field's expert answer has
been applied and its labels' settlement recorded (step.apply_outcomes calls settle). The
expert is not told the decode. The code is compared only with the value field research
settled; it does not read numbers out of the readers' texts, and it does not supply a value.
It changes no value layer: it can only add a confirmation or a hold.

1. Confirm, when all three hold: the settled value's literal writes the code whole
   (written_whole); a reading of the code's label holds that literal at an occurrence with no
   number directly before or after it (_held_whole); and the value's parsed and normalized
   layers are supported without the code (_unsupported_layers). The code is then a clearing
   backing of the SOURCE class (FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4, rule 3):
   the field's marked findings (text_only, conflict) become one cleared finding on the code's
   label, the code row is cited as deciding it, and the reason says the code confirms the
   number in place of the mark's sentence. Where the literal writes the code whole but another
   condition fails, nothing changes.
2. Contradict. The settled value's literal does not write the code whole, whatever its parsed
   layer reads: the value stays, and is marked for a person
   (marked:fmnh_ins_number:<label>:barcode_differs, one of the run's reasons). The code row is
   cited by the mark only, not by the value.
3. Otherwise nothing changes: no value settled (an ambiguous or unresolved field included: the
   code breaks no tie), no stored decode, a field a person decided (step.human_keys: settle is
   not called), a run not on the units path, or a run with a transcript a person decided on
   any of its labels (Reading.person_decided). In that last case, where the settled value's
   number is not the code's, the value's reason says so and an info finding (PERSON_DIFFERS)
   cites the code row.

The rule reads only strings and the run's findings and evidence rows; it builds no evidence
row. step.apply_outcomes also calls it inside a guard that logs any exception and puts the
field and its findings back as the existing rules left them, so the code cannot fail a run.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence

from specimen_digitization.application.barcode import FIELD, stored_code
from specimen_digitization.application.domain import FieldValue, RunFinding, ValueState
from specimen_digitization.application.field_validators import CATALOG

from .contracts import FieldTask, Reading

DIFFERS = "barcode_differs"
# The rule's own finding (info, never a reason): a settled value a person's transcript backs
# whose number is not the code's.
RULE = "barcode_decode"
RULE_VERSION = "catalogue-number-barcode-v4"
PERSON_DIFFERS = "barcode_person_differs:" + FIELD
SETTLED = ("settled", "verbatim")


def number(text: str | None) -> str | None:
    """A text's catalogue number, as check_catalog_number reads it (CATALOG), or None."""
    match = CATALOG.fullmatch(text) if text else None
    return match["digits"] if match else None


def _kept(text: str) -> str:
    """The text's letters and numbers alone (Unicode general categories L* and N*)."""
    return "".join(ch for ch in text if unicodedata.category(ch)[0] in "LN")


def _numeric(ch: str) -> bool:
    return unicodedata.category(ch)[0] == "N" or ch.isnumeric()


def written_whole(text: str, payload: str) -> bool:
    """Whether the text writes the code's digits as a whole number, decided on a projection of
    the text that keeps only its letters and numbers (Unicode general categories L* and N*;
    spaces, line breaks, punctuation, marks and format characters are deleted): the code's
    ASCII digits occur in the projection with no numeric character directly before or after
    them (category N*, or str.isnumeric, which also counts CJK numerals). So nothing invisible
    or separating can stand between the code and another number. It is deliberately
    conservative: a code after an unrelated number across a space ("12 0010001") is refused
    too. Letters are not digits."""
    if not (payload.isascii() and payload.isdigit()):
        return False
    kept = _kept(text)
    start = kept.find(payload)
    while start >= 0:
        end = start + len(payload)
        if not (start and _numeric(kept[start - 1])) and not (end < len(kept) and _numeric(kept[end])):
            return True
        start = kept.find(payload, start + 1)
    return False


def _held_whole(text: str, literal: str) -> bool:
    """Whether the reading's text holds the literal itself at an occurrence with no numeric
    character directly before or after it once spaces, marks and separators around it are
    deleted (the projection of written_whole, applied to the text on either side), so the
    occurrence is the literal's own and not the end of a longer number or one joined to a date."""
    if not literal:
        return False
    start = text.find(literal)
    while start >= 0:
        before, after = _kept(text[:start]), _kept(text[start + len(literal):])
        if not (before and _numeric(before[-1])) and not (after and _numeric(after[0])):
            return True
        start = text.find(literal, start + 1)
    return False


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


def settle(run, task: FieldTask, readings: Sequence[Reading], *, decision: dict | None = None) -> bool:
    """Compare the catalogue number with the run's stored decode by the module's rules 1 and 2;
    False, changing nothing, where rule 3 leaves the field as it is."""
    from .step import SETTLEMENT, SETTLEMENT_RULES, cleared_code, marked_code

    code = stored_code(run)
    if code is None or task.key != FIELD or code.row.region_id is None:
        return False
    payload, current = code.payload, run.fields.get(FIELD) or FieldValue()
    decision = {} if decision is None else decision
    if current.state != ValueState.SUPPORTED or current.layer not in SETTLED:
        return False
    if any(reading.person_decided for reading in readings):
        # Rule 3: a person decided a transcript of the record; the code only notes a difference.
        if number(current.normalized or current.parsed or current.literal) != payload:
            value = current.model_copy(deep=True)
            value.reason = " ".join(part for part in (value.reason, f"The slide's QR code reads {payload}, "
                "which differs from this value; a person's transcription stands.") if part)
            run.fields[FIELD] = value
            run.findings.append(RunFinding(rule_id=RULE, rule_version=RULE_VERSION, severity="info",
                field_key=FIELD, reason_code=PERSON_DIFFERS, evidence_ids=[code.row.id]))
            decision["rule"] = "person_over_barcode"
            return True
        return False
    regions = _marked_regions(run) or [code.row.region_id]
    value = current.model_copy(deep=True)
    literal = current.literal or ""
    if written_whole(literal, payload):
        held = any(reading.region_id == code.row.region_id and _held_whole(reading.text, literal)
            for reading in readings)
        if not held or _unsupported_layers(run, current):
            # No reading of the code's label holds the literal whole, or the value's own parsed
            # or normalized layer is unsupported: the field stays as it is with no code.
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
    # Rule 2: the label's number, as the literal writes it, is not the code written whole
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
