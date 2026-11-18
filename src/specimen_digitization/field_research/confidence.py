"""Confident or flagged: a settled value something the run recorded about its field argues against
is marked on that field (lane Q1 of the autonomy program, docs/execution/autonomy/PLAN.md).

The owner's goal of 2026-11-18, typed in the coordinator's session: "take the specimen
digitization to full autonomy but ensuring that records are ever cleared wrong and aren't
unnecessarily waiting for a human review." A mark is a warning finding of rule RULE,
`marked:<field>:<label>:<why>` (step.marked_code), which step.marked_reasons makes one of the run's
reasons; the app words it from its code. The pass writes nothing else: no value, layer, state or
reason text changes. Under a profile whose field is optional the mark is that field's doubt and
does not hold the record; on a mandatory field it holds the record as every mark does.

Marks are computed only in the research pass, where the system settles values (step.apply_outcomes
calls `review` after the check stage), and only for the fields that attempt researched or derived:
as a retry leaves a field an earlier attempt or a person settled unresearched (step.build_tasks),
the pass leaves its marks, or their absence, as they are. A location reassessment computes none.
A mark lasts until a person decides the field (the decision endpoint calls `forget`, which drops
the field's marks and the follows_marked marks of the values derived from it) or research settles
the field again.

The rules read only what the run recorded about the field: its settled literal, the readers'
verbatims recorded for it (FieldValue.verbatim_by_observation), the organiser's candidates for the
same field, the label settlement's finding, and its derivation sources. Comparisons are exact
(outer white space trimmed, or runs of white space folded where said); a rule that lacks what it
needs does not mark. Each rule has its own `why` (WHYS):
1. READERS_DIFFER, on the fields no approved source checks (IMAGE_ONLY_FIELDS: those whose tools,
   contracts.FIELD_TOOLS, hold none of agreement.SOURCE_IDS: the dates, the elevations, the
   catalogue number, collectors, collection code, habitat, collection method, Verbatim D/T/S): two or
   more readers' verbatims are recorded for the value and are not all equal (outer white space
   trimmed), its label settled it cleared (`cleared:<field>:<label>`), and no evidence row decides it
   (the slide's QR code). The settlement rule gives such a field no SOURCE backing
   (agreement.labels_by_rule, `sourced`), so a label clears it only on the image judgement or a
   person's transcript, which person_holds sets aside: the readers differ and the image chose.
2. FOLLOWS_MARKED: a derived value one of whose sources is marked, by any rule.
3. EXTENT: the organiser's candidates for the same field from every reader of a label of the
   value hold one text alike (white space folded), and the settled literal is a proper part of it.
4. NOT_COLLECTION_CODE: a Collection Code that is not the printed heading the owner ruled (the
   ontology's notation lewis_collection_heading).
5. NOT_VERBATIM_DATE: a Verbatim D/T/S whose literal the profile's date rules read as an exact day,
   or one of whose white-space-separated words the date parser reads as a slide code.

A field a person holds authority over by a record on the run (person_holds) gets no mark. Every
call goes through `guarded`: any exception inside the pass leaves the run's fields and findings as
they were and logs one warning.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Mapping, Sequence

from specimen_digitization.application.domain import FieldValue, RunFinding, ValueState

from .agreement import SOURCE_IDS
from .contracts import FIELD_TOOLS, Reading

LOGGER = logging.getLogger(__name__)
RULE = "confidence"
RULE_VERSION = "field-research-confidence-v4"
READERS_DIFFER = "readers_differ"
FOLLOWS_MARKED = "follows_marked"
EXTENT = "extent"
NOT_COLLECTION_CODE = "not_collection_code"
NOT_VERBATIM_DATE = "not_verbatim_date"
WHYS = (READERS_DIFFER, FOLLOWS_MARKED, EXTENT, NOT_COLLECTION_CODE, NOT_VERBATIM_DATE)
LOCKS = "human_review_field_locks"

SETTLED_LAYERS = frozenset({"settled", "verbatim"})
# The fields no approved source checks (contracts.FIELD_TOOLS against agreement.SOURCE_IDS), the
# determiner's IRN aside: the settlement rule clears them only on the image judgement or a person.
IMAGE_ONLY_FIELDS = frozenset(key for key, tools in FIELD_TOOLS.items()
    if not set(tools) & SOURCE_IDS) - {"identified_by_irn"}
COLLECTION_CODE = "collection_code"
VERBATIM = "verbatim_dts"


def _folded(text: str | None) -> str:
    return " ".join((text or "").split())


def _settled(value: FieldValue | None) -> bool:
    return (value is not None and value.state == ValueState.SUPPORTED and value.layer in SETTLED_LAYERS
        and bool(value.literal and value.literal.strip()))


# ---- persons ------------------------------------------------------------------------------------

def person_holds(run, readings: Sequence[Reading] = (), human: Collection[str] = ()) -> set[str]:
    """The fields a person holds authority over by a record on the run: `human` (step.human_keys, the
    decisions a move to the units path carried), a research selection a person locked, the location
    reassessment's `protected` list, and a value whose label a person transcribed."""
    from .location_reassessment import KEY as REASSESSMENT

    dependencies = getattr(run, "dependencies", None) or {}
    held = set(human) | {key for key in dependencies.get(LOCKS) or {} if isinstance(key, str)}
    marker = dependencies.get(REASSESSMENT)
    if isinstance(marker, Mapping) and isinstance(marker.get("protected"), list):
        held |= {key for key in marker["protected"] if isinstance(key, str)}
    persons = {reading.region_id for reading in readings if reading.person_decided}
    if persons:
        evidence = {item.id: item for item in run.evidence}
        for key, value in run.fields.items():
            regions = {evidence[i].region_id for i in value.evidence_ids if i in evidence} | {value.source_region_id}
            if persons & regions:
                held.add(key)
    return held


def forget(run, key: str) -> None:
    """A person decided or selected the field `key`: drop this pass's findings on it and the
    follows_marked findings of the values derived from it. Nothing is recomputed; nothing else on the
    run changes."""
    dependents = {name for name, value in run.fields.items() if key in value.derived_from}
    run.findings[:] = [finding for finding in run.findings if not (finding.rule_id == RULE and (
        finding.field_key == key
        or (finding.field_key in dependents and finding.reason_code.endswith(":" + FOLLOWS_MARKED))))]


# ---- the rules ----------------------------------------------------------------------------------

def readers_differ(run, key: str, value: FieldValue) -> bool:
    if key not in IMAGE_ONLY_FIELDS:
        return False
    texts = {text.strip() for text in value.verbatim_by_observation.values()}
    if len(value.verbatim_by_observation) < 2 or len(texts) < 2 or "decides" in value.evidence_relations.values():
        return False
    return any(finding.rule_id == "field_settlement" and finding.field_key == key
        and finding.reason_code.startswith(f"cleared:{key}:") for finding in run.findings)


def extent(key: str, value: FieldValue, candidates: Sequence, readings: Sequence[Reading]) -> bool:
    """The organiser's candidates (step._candidates) for the field."""
    region_of = {reading.name: reading.region_id for reading in readings}
    regions: dict[str, dict[str, set[str]]] = {}
    for candidate in candidates:
        region = region_of.get(candidate.reading)
        if region is not None:
            regions.setdefault(region, {}).setdefault(candidate.reading, set()).add(_folded(candidate.literal))
    literal = _folded(value.literal)
    for region, by_reader in regions.items():
        writers = [r.name for r in readings if r.region_id == region and r.text and r.text.strip()]
        if len(writers) < 2 or set(writers) - set(by_reader):
            continue
        agreed = set.intersection(*(by_reader[name] for name in writers))
        if any(literal != text and literal in text for text in agreed):
            return True
    return False


def _headings() -> frozenset[str]:
    from specimen_digitization.ontology import ontology

    return frozenset(_folded(form) for item in ontology().notations
        if item.id == "lewis_collection_heading" for form in item.written)


def not_collection_code(key: str, value: FieldValue) -> bool:
    return key == COLLECTION_CODE and _folded(value.literal) not in _headings()


def not_verbatim_date(key: str, value: FieldValue, date_rules) -> bool:
    from .checks import SLIDE_CODE, parse_date

    if key != VERBATIM:
        return False
    literal = value.literal.strip()
    found = parse_date(literal, reading_texts=[literal], date_rules=date_rules)
    if any(r.precision == "day" and r.iso and len(r.iso) == 10 for r in found.readings):
        return True
    return any(SLIDE_CODE in parse_date(word, reading_texts=[word], date_rules=date_rules).notes
        for word in literal.split())


# ---- the pass -----------------------------------------------------------------------------------

def _marked_fields(run) -> set[str]:
    from .step import marked_reasons

    return {code.split(":")[1] for code in marked_reasons(run) if code.count(":") >= 2}


def _add(run, key: str, why: str, readings: Sequence[Reading]) -> None:
    from .ontology_checks import _labels
    from .step import marked_code

    rows = {item.id: item for item in run.evidence}
    for label in _labels(run, key, readings, rows):
        run.findings.append(RunFinding(rule_id=RULE, rule_version=RULE_VERSION, severity="warning",
            field_key=key, reason_code=marked_code(key, label, why), evidence_ids=list(run.fields[key].evidence_ids)))


def review(run, *, readings: Sequence[Reading], human: Collection[str] = (), date_rules=None,
        researched: Collection[str] | None = None) -> None:
    """Mark the values this attempt settled (`researched`, the fields it researched or derived; None:
    every field): drop this pass's findings on them, then apply the rules above. A field another rule
    marked already gets no second mark; a field a person holds none."""
    from .step import _candidates

    scope = set(run.fields) if researched is None else set(researched)
    scope |= {key for key, value in run.fields.items() if value.layer == "derived" and scope & set(value.derived_from)}
    run.findings[:] = [finding for finding in run.findings
        if not (finding.rule_id == RULE and finding.field_key in scope)]
    held = person_holds(run, readings, human)
    already = _marked_fields(run)
    candidates = _candidates(run, readings) if readings else {}
    for key, value in run.fields.items():
        if key not in scope or key in held or key in already or not _settled(value):
            continue
        for why, holds in (
                (NOT_COLLECTION_CODE, lambda: not_collection_code(key, value)),
                (NOT_VERBATIM_DATE, lambda: not_verbatim_date(key, value, date_rules)),
                (EXTENT, lambda: extent(key, value, candidates.get(key, ()), readings)),
                (READERS_DIFFER, lambda: readers_differ(run, key, value))):
            if holds():
                _add(run, key, why, readings)
                break
    marked = _marked_fields(run)
    changed = True
    while changed:
        changed = False
        for key, value in run.fields.items():
            if (key not in scope or key in held or key in marked or value.state != ValueState.SUPPORTED
                    or value.layer != "derived"):
                continue
            if any(name in marked for name in value.derived_from):
                _add(run, key, FOLLOWS_MARKED, readings)
                marked.add(key)
                changed = True


def guarded(run, action, *args, **kwargs) -> None:
    """Run `action` on the run; on any exception inside it, log one warning and put the run's fields
    and findings back as they were, so the pass leaves no mark."""
    kept_fields = {key: value.model_copy(deep=True) for key, value in run.fields.items()}
    kept_findings = list(run.findings)
    try:
        action(run, *args, **kwargs)
    except Exception:  # noqa: BLE001 - the confidence pass never fails research or a decision
        LOGGER.warning("confidence pass skipped: no value marked", exc_info=True)
        run.fields.clear()
        run.fields.update(kept_fields)
        run.findings[:] = kept_findings
