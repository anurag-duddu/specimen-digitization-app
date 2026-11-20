"""The slide's QR code (application/barcode.py) and the catalogue number, for that field alone.

The segment step stores an accepted decode of the slide's QR code as one evidence row
(barcode.record), on the label whose box holds the code. When the run holds one whose payload
is a well-formed catalogue number (field_validators.CATALOG on the whole payload, its digits
the payload itself), the catalogue number (fmnh_ins_number) is the code's number. The rule runs
after the field's expert answer has been applied and its labels' settlement recorded
(step.apply_outcomes calls settle). The expert is not told the decode. The code is compared
with, and supplies, whole values only: it reads no number out of the readers' texts and breaks
no tie among readings. The rule is the coordinator's, of 2026-11-20, under the owner's ruling
of 2026-11-18 (docs/execution/autonomy/PLAN.md section 4: its row "V3", and the ruling quoted
below the table), on the measurement that the code equals the truth on all 97 of the 100 truth
slides that decode.

1. No value settled: the field is ambiguous, unresolved, not present or blank, or its settled
   text is no well-formed catalogue number. The field is settled with the code's number
   (_supply): supported, on the settled layer, its literal and parsed text the code's digits,
   its label the code's, the code row its one citation, deciding it. The reason says no reading
   settled the number and the code gives it, and what the readers read where they read
   something (the field's whole candidates, quoted and never compared). The field's marked
   findings and its transcript_literal note go; one cleared finding on the code's label cites
   the code row.
2. A value settled whose literal does not write the code whole (written_whole), whatever its
   parsed layer reads: the field takes the code's number in the same way (_supply). The
   readers' number is kept in the reason and by an info finding (READERS_DIFFER: never a
   reason, never a hold) that cites the code row and the rows that backed the readers' value.
   No barcode_differs mark is made.
3. A value settled whose literal writes the code whole is confirmed when two more conditions
   hold: a reading of the code's label holds that literal at an occurrence with no number
   directly before or after it (_held_whole); and the value's parsed and normalized layers are
   supported without the code (_unsupported_layers). The code is then a clearing backing of the
   SOURCE class (FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4, rule 3): the field's
   marked findings (text_only, conflict) become one cleared finding on the code's label, the
   code row is cited as deciding it, and the reason says the code confirms the number in place
   of the mark's sentence. Where the literal writes the code whole but another condition
   fails, nothing changes.
4. Otherwise nothing changes: no stored decode; one whose payload is no well-formed catalogue
   number; for rules 1 and 2, one that lies on no label of this run's image (_of_this_run); a
   field a move or a new run carried from a person (step.human_keys: settle is not called); a
   run not on the units path; or a run with a transcript a person decided on any of its labels
   (Reading.person_decided). In that last case, where a settled value's number is not the
   code's, the value's reason says so and an info finding (PERSON_DIFFERS) cites the code row;
   a field no reading settled stays as it is.

A person's authority. Rules 1 and 2 never act on a field a person holds authority over, read
through the one function the second opinion reads it through (second_opinion.authority, from
the run's durable state): a field decided at the decision endpoint (Run.person_decided_fields),
a carried decision, a research selection a person locked, a field a location reassessment
protects, a value on a label whose transcript a person decided. Research may ask such a field's
expert again on a Retry (main's task selection, which this rule does not change); whatever that
leaves, the code neither gives the field a number nor replaces its value (_a_persons).

Order. step.apply_outcomes calls settle as its last act, after the check stage, so on the
attempt that researches the catalogue number no other field's check sees a number the code
gives, and neither does the re-ask's trial, which applies the outcomes on a copy of the run
(reask.again): every other field's value, state, reason and findings, and the number of expert
requests, are those of the same run with no code row. On a later research attempt of the same
run (a Retry or Resume after a blocked attempt, a location reassessment) a number the code gave
is a settled field like one the readers settled: its expert is not asked again, and the checks
that read other settled fields' texts read its digits (FIELD_RESEARCH.md says which).

A value the code supplies is on the settled layer with the code's digits as its literal: the
label carries the code and the code writes the number, so the app's existing basis for a
catalogue number ("As written") and its note for a cleared finding fit it, and
step.code_confirmed, recomputed at every finalize from the field and the code row, reads it as
a number the code confirms. Nothing is stored beyond the field's own value, its findings and
its citation of the code row.

The rule reads only strings and the run's findings and evidence rows; it builds no evidence
row. step.apply_outcomes also calls it inside a guard that logs any exception and puts the
field and its findings back as the existing rules left them, so the code cannot fail a run.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence

from specimen_digitization.application.barcode import FIELD, StoredCode, stored_code
from specimen_digitization.application.domain import FieldValue, RunFinding, ValueState
from specimen_digitization.application.field_validators import CATALOG

from .contracts import FieldTask, Reading

# The mark rule 2 made until 2026-11-20: a settled number the code contradicts, held for a
# person. No run makes it now; a record finalized before keeps it, and the app words it.
DIFFERS = "barcode_differs"
# The rule's own findings (info, never a reason): a settled value a person's transcript backs
# whose number is not the code's; and the readers' settled value the code's number replaced.
RULE = "barcode_decode"
RULE_VERSION = "catalogue-number-barcode-v5"
PERSON_DIFFERS = "barcode_person_differs:" + FIELD
READERS_DIFFER = "barcode_readers_differ:" + FIELD
SETTLED = ("settled", "verbatim")
# The rule that decided the field, as the trace names it (step.trace_fields).
SUPPLIES = "barcode_supplies"
OVER_READERS = "barcode_over_readers"
# What the readers read, quoted in a supplied value's reason: at most this many texts, each of
# at most this many characters.
QUOTED_TEXTS = 4
QUOTED_LENGTH = 40


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


def _of_this_run(run, code: StoredCode) -> bool:
    """Whether the code row lies on one of the run's labels, of that label's image (as
    step.code_confirmed reads the row at every finalize)."""
    regions = {region.id: region for region in run.regions}
    return code.row.region_id in regions and code.row.asset_id == regions[code.row.region_id].asset_id


def _a_persons(run, readings: Sequence[Reading]) -> bool:
    """Whether a person holds authority over the catalogue number, by the run's durable state,
    through the function the second opinion reads it through (second_opinion.authority): the
    code gives such a field no number and replaces no value of it."""
    from .second_opinion import authority

    return FIELD in authority(run, readings)


def _shown(text: str) -> str:
    """A text on one line, cut to QUOTED_LENGTH characters: for a reason's sentence."""
    return " ".join(text.split())[:QUOTED_LENGTH]


def _quoted(texts: Iterable[str | None]) -> str:
    """The texts, each once and in their order, in double quotes and joined in words; at most
    QUOTED_TEXTS of them. "" when there is none."""
    kept = list(dict.fromkeys(_shown(text) for text in texts if text and text.strip()))[:QUOTED_TEXTS]
    quoted = [f'"{text}"' for text in kept]
    return " and ".join(part for part in (", ".join(quoted[:-1]), *quoted[-1:]) if part)


def _supply(run, task: FieldTask, code: StoredCode, current: FieldValue, decision: dict, *, settled: bool) -> bool:
    """Rules 1 and 2: the field is the code's number, the code row deciding it. `settled`: field
    research settled a value (supported, settled or as written), which the code's number
    replaces; its text is kept in the reason and the rows that backed it by READERS_DIFFER."""
    from .step import SETTLEMENT, SETTLEMENT_RULES, cleared_code

    payload = code.payload
    earlier = (current.literal or current.normalized or current.parsed) if settled else None
    # The reasons are shown in the app, so they use its words: "catalog number", "the slide's QR
    # code" (the client's UX writing guidelines, section 3).
    if earlier and number(current.normalized or current.parsed or current.literal) is None:
        reason = (f'The readers\' text, "{_shown(earlier)}", is not a well-formed catalog number. The slide\'s QR '
            f"code reads {payload} and gives the catalog number.")
    elif earlier:
        reason = (f'The readers\' number, "{_shown(earlier)}", differs from the slide\'s QR code, which reads '
            f"{payload}. The code gives the catalog number.")
    else:
        read = _quoted(candidate.literal for candidate in task.candidates)
        reason = " ".join(part for part in ("No reading settled the catalog number.",
            f"The readers read {read}." if read else "", f"The slide's QR code gives it: {payload}.") if part)
    run.findings[:] = [finding for finding in run.findings
        if not (finding.field_key == FIELD and finding.rule_id in (SETTLEMENT, "transcript_literal"))]
    run.fields[FIELD] = FieldValue(state=ValueState.SUPPORTED, literal=payload, parsed=payload,
        evidence_ids=[code.row.id], evidence_relations={code.row.id: "decides"}, reason=reason, layer="settled",
        source_region_id=code.row.region_id)
    run.findings.append(RunFinding(rule_id=SETTLEMENT, rule_version=SETTLEMENT_RULES, severity="info",
        field_key=FIELD, reason_code=cleared_code(FIELD, code.row.region_id), evidence_ids=[code.row.id]))
    if earlier:
        rows = {row.id for row in run.evidence}
        run.findings.append(RunFinding(rule_id=RULE, rule_version=RULE_VERSION, severity="info", field_key=FIELD,
            reason_code=READERS_DIFFER, evidence_ids=[code.row.id, *(row for row, how in
                current.evidence_relations.items() if how in ("supports", "decides") and row in rows
                and row != code.row.id)]))
    decision["rule"] = OVER_READERS if earlier else SUPPLIES
    return True


def _decode(run, task: FieldTask):
    """The run's stored decode when the rule may act on it: one code row, on a label, whose payload
    is itself a well-formed catalogue number; else None (rule 4)."""
    code = stored_code(run)
    if code is None or task.key != FIELD or code.row.region_id is None:
        return None
    return code if number(code.payload) == code.payload else None


def confirm(run, task: FieldTask, readings: Sequence[Reading], *, decision: dict | None = None) -> bool:
    """Rule 3, and rule 4's note beside a person's transcript: what the rule did before 2026-11-20
    besides holding, in the place step.apply_outcomes always called it (after the field's
    settlement, before the check stage). False, changing nothing, where neither applies."""
    from .step import SETTLEMENT, SETTLEMENT_RULES, cleared_code

    code = _decode(run, task)
    if code is None:
        return False
    payload, current = code.payload, run.fields.get(FIELD) or FieldValue()
    decision = {} if decision is None else decision
    if current.state != ValueState.SUPPORTED or current.layer not in SETTLED:
        return False
    if any(reading.person_decided for reading in readings):
        # Rule 4: a person decided a transcript of the record. The code only notes a difference
        # from a settled value.
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
    literal = current.literal or ""
    if number(current.normalized or current.parsed or literal) is None or not written_whole(literal, payload):
        # Rules 1 and 2 (give), not a confirmation.
        return False
    held = any(reading.region_id == code.row.region_id and _held_whole(reading.text, literal)
        for reading in readings)
    if not held or _unsupported_layers(run, current):
        # No reading of the code's label holds the literal whole, or the value's own parsed
        # or normalized layer is unsupported: the field stays as it is with no code.
        return False
    # Rule 3: the code confirms the number the label writes.
    value = current.model_copy(deep=True)
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


def give(run, task: FieldTask, readings: Sequence[Reading], *, decision: dict | None = None) -> bool:
    """Rules 1 and 2: the code gives the catalogue number where no reading settled a well-formed
    one, or the settled literal does not write the code whole. The last act of
    step.apply_outcomes on the run, after the check stage (the module's note on order). False,
    changing nothing, on a run with a transcript a person decided, on a field a person holds
    authority over (_a_persons), for a row that is not on a label of this run's image, and for a
    settled number that writes the code whole (rule 3's, confirmed or left as it is)."""
    code = _decode(run, task)
    if code is None or any(reading.person_decided for reading in readings):
        return False
    current = run.fields.get(FIELD) or FieldValue()
    decision = {} if decision is None else decision
    settled = current.state == ValueState.SUPPORTED and current.layer in SETTLED
    well_formed = settled and number(current.normalized or current.parsed or current.literal) is not None
    if well_formed and written_whole(current.literal or "", code.payload):
        return False
    if _a_persons(run, readings) or not _of_this_run(run, code):
        return False
    # Rule 1 (no reading settled a well-formed number) or rule 2 (a settled number that is not
    # the code written whole, whatever the value's parsed layer reads).
    return _supply(run, task, code, current, decision, settled=settled)


def settle(run, task: FieldTask, readings: Sequence[Reading], *, decision: dict | None = None) -> bool:
    """The whole rule on a run as it is: confirm, else give (rules 1 to 3); False, changing
    nothing, where rule 4 leaves the field as it is. step.apply_outcomes calls the two parts
    apart, the check stage between them; a caller with no stage to run between them (a replay of
    a stored run, a test of the rule alone) calls this."""
    return confirm(run, task, readings, decision=decision) or give(run, task, readings, decision=decision)
