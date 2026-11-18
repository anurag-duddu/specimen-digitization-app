"""Confident or flagged: a settled value something the run recorded about its field argues against
is marked on that field (lane Q1 of the autonomy program, docs/execution/autonomy/PLAN.md).

The owner's goal of 2026-11-18, typed in the coordinator's session: "take the specimen
digitization to full autonomy but ensuring that records are ever cleared wrong and aren't
unnecessarily waiting for a human review." A mark is a warning finding of rule RULE,
`marked:<field>:<label>:<why>` (step.marked_code), which step.marked_reasons makes one of the run's
reasons; the app words it from its code. The pass writes nothing else: no value, layer, state or
reason text changes. Under a profile whose field is optional the mark is that field's doubt and
does not hold the record; on a mandatory field it holds the record as every mark does.

The rules read only what the run recorded about the field: its settled literal, the readers'
verbatims recorded for it (FieldValue.verbatim_by_observation), its label rows' excerpts, the
organiser's candidates for the same field, the label settlement's finding, and its derivation
sources. Comparisons are exact (outer white space trimmed, or runs of white space folded where
said); a rule that lacks what it needs does not mark. Each rule has its own `why` (WHYS):
1. READERS_DIFFER: two or more readers' verbatims are recorded for the value and are not all equal
   (outer white space trimmed), and the value's backing is the image alone: its label settled it
   cleared (`cleared:<field>:<label>`), no evidence row decides it (GBIF, the slide's QR code) and,
   for a place value field, no source record names it (authority_id).
2. FOLLOWS_MARKED: a derived value one of whose sources is marked, by any rule.
3. EXTENT: the organiser's candidates for the same field from every reader of a label of the
   value hold one text alike (white space folded), and the settled literal is a proper part of it.
4. Conventions settled from the requirements (lane M0):
   - DISTANCE_ORIGIN (city, county, province or state): in a label row recorded for the value, the
     text directly before the literal is a distance and a direction ("27 km. north of Kunduz").
   - NOT_COLLECTION_CODE: a Collection Code that is not the printed heading the owner ruled (the
     ontology's notation lewis_collection_heading).
   - NOT_VERBATIM_DATE: a Verbatim D/T/S whose literal the profile's date rules read as an exact
     day, or one of whose white-space-separated words the date parser reads as a slide code.

A field a person holds authority over (person_holds) gets no mark from the pass, and the decision
endpoint removes this pass's findings from a field a person decides or selects (forget). Each run
of the pass first drops every finding of RULE and recomputes them (review); step.refinalize, which
adds no mark, drops the marks on fields a person holds and the follows_marked marks whose sources
are no longer marked (settle_after_decision). Every call goes through `guarded`: any exception
inside the pass leaves the run's fields and findings as they were and logs one warning.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Collection, Mapping, Sequence

from specimen_digitization.application.domain import FieldValue, RunFinding, ValueState

from .contracts import Reading

LOGGER = logging.getLogger(__name__)
RULE = "confidence"
RULE_VERSION = "field-research-confidence-v3"
READERS_DIFFER = "readers_differ"
FOLLOWS_MARKED = "follows_marked"
EXTENT = "extent"
DISTANCE_ORIGIN = "distance_origin"
NOT_COLLECTION_CODE = "not_collection_code"
NOT_VERBATIM_DATE = "not_verbatim_date"
WHYS = (READERS_DIFFER, FOLLOWS_MARKED, EXTENT, DISTANCE_ORIGIN, NOT_COLLECTION_CODE, NOT_VERBATIM_DATE)
LOCKS = "human_review_field_locks"

SETTLED_LAYERS = frozenset({"settled", "verbatim"})
ORIGIN_FIELDS = frozenset({"city", "county", "province_state"})
COLLECTION_CODE = "collection_code"
VERBATIM = "verbatim_dts"

_FRACTIONS = "[\N{VULGAR FRACTION ONE HALF}\N{VULGAR FRACTION ONE QUARTER}\N{VULGAR FRACTION THREE QUARTERS}]"
_NUMBER = rf"(?:\d+(?:[.,]\d+)?\s*{_FRACTIONS}?|{_FRACTIONS})"
_UNIT = r"(?:mi|mis|miles?|km|kms|kilomet(?:er|re)s?)\.?"
_DIRECTION = (r"(?:(?:north|south)(?:[- ]?(?:east|west))?|east|west"
    r"|[NSEW](?:\s*\.?\s*[NSEW]){0,2}\.?)")
# A distance and a direction ending the text directly before a place, an "of" or "from" between.
DISTANCE = re.compile(rf"{_NUMBER}\s*{_UNIT}\s*{_DIRECTION}(?:\s+(?:of|from))?\s*$", re.I)


def _folded(text: str | None) -> str:
    return " ".join((text or "").split())


def _settled(value: FieldValue | None) -> bool:
    return (value is not None and value.state == ValueState.SUPPORTED and value.layer in SETTLED_LAYERS
        and bool(value.literal and value.literal.strip()))


def _rows(run, value: FieldValue):
    evidence = {item.id: item for item in run.evidence}
    return [evidence[i] for i in value.evidence_ids if i in evidence and evidence[i].kind == "literal"]


# ---- persons ------------------------------------------------------------------------------------

def person_holds(run, readings: Sequence[Reading] = (), human: Collection[str] = ()) -> set[str]:
    """The fields a person holds authority over, as the run records it: `human` (step.human_keys, the
    decisions a move to the units path carried), a research selection a person locked, a field the
    location reassessment's record protects (its `protected` list: the person's field and authority
    decisions it verified, loaded from storage too), and a value whose label a person
    transcribed (Reading.person_decided). A direct field, authority or taxonomy decision leaves no
    such record on the run; the decision endpoint removes this pass's findings from that field
    (forget), and no later step adds one (refinalize adds none; research runs again only on a retry,
    which carries the decision)."""
    from .location_reassessment import KEY as REASSESSMENT

    dependencies = getattr(run, "dependencies", None) or {}
    held = set(human) | {key for key in dependencies.get(LOCKS) or {} if isinstance(key, str)}
    marker = dependencies.get(REASSESSMENT)
    if isinstance(marker, Mapping) and isinstance(marker.get("protected"), list):
        held |= {key for key in marker["protected"] if isinstance(key, str)}
    persons = {reading.region_id for reading in readings if reading.person_decided}
    for key, value in run.fields.items():
        if persons & {row.region_id for row in _rows(run, value)} or value.source_region_id in persons:
            held.add(key)
    return held


def forget(run, keys: Collection[str]) -> None:
    """Drop this pass's findings on the fields `keys` (a person decided or selected them). Nothing else
    on the run changes."""
    keys = set(keys)
    run.findings[:] = [finding for finding in run.findings
        if not (finding.rule_id == RULE and finding.field_key in keys)]


# ---- the rules ----------------------------------------------------------------------------------

def readers_differ(run, key: str, value: FieldValue) -> bool:
    from .agreement import PLACE_VALUE_FIELDS

    texts = {text.strip() for text in value.verbatim_by_observation.values()}
    if len(value.verbatim_by_observation) < 2 or len(texts) < 2:
        return False
    if "decides" in value.evidence_relations.values() or (key in PLACE_VALUE_FIELDS and value.authority_id):
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


def distance_origin(run, key: str, value: FieldValue) -> bool:
    if key not in ORIGIN_FIELDS:
        return False
    literal = value.literal.strip()
    for row in _rows(run, value):
        at = row.excerpt.find(literal)
        if at > 0 and DISTANCE.search(row.excerpt[:at]):
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


def _add(run, key: str, why: str, readings: Sequence[Reading]) -> list[str]:
    from .ontology_checks import _labels
    from .step import marked_code

    rows = {item.id: item for item in run.evidence}
    made = []
    for label in _labels(run, key, readings, rows):
        code = marked_code(key, label, why)
        run.findings.append(RunFinding(rule_id=RULE, rule_version=RULE_VERSION, severity="warning",
            field_key=key, reason_code=code, evidence_ids=list(run.fields[key].evidence_ids)))
        made.append(code)
    return made


def _follow(run, held: set[str], readings: Sequence[Reading]) -> list[str]:
    """Rule 2 on the run's current marks: each derived value a marked source feeds, not held."""
    made = []
    marked = _marked_fields(run)
    changed = True
    while changed:
        changed = False
        for key, value in run.fields.items():
            if (key in held or key in marked or value.state != ValueState.SUPPORTED or value.layer != "derived"):
                continue
            if any(name in marked for name in value.derived_from):
                made += _add(run, key, FOLLOWS_MARKED, readings)
                marked.add(key)
                changed = True
    return made


def review(run, *, readings: Sequence[Reading], human: Collection[str] = (), date_rules=None) -> list[str]:
    """Drop every finding of RULE, then mark the run's settled values by the rules above; the codes
    made. A field another rule marked already gets no second mark; a field a person holds none."""
    from .step import _candidates

    run.findings[:] = [finding for finding in run.findings if finding.rule_id != RULE]
    held = person_holds(run, readings, human)
    already = _marked_fields(run)
    candidates = _candidates(run, readings) if readings else {}
    made: list[str] = []
    for key, value in run.fields.items():
        if key in held or key in already or not _settled(value):
            continue
        for why, holds in (
                (NOT_COLLECTION_CODE, lambda: not_collection_code(key, value)),
                (NOT_VERBATIM_DATE, lambda: not_verbatim_date(key, value, date_rules)),
                (DISTANCE_ORIGIN, lambda: distance_origin(run, key, value)),
                (EXTENT, lambda: extent(key, value, candidates.get(key, ()), readings)),
                (READERS_DIFFER, lambda: readers_differ(run, key, value))):
            if holds():
                made += _add(run, key, why, readings)
                break
    return made + _follow(run, held, readings)


def settle_after_decision(run, *, human: Collection[str] = ()) -> None:
    """step.refinalize's part, after a person's decision: drop this pass's findings on the fields a
    person holds, and recompute rule 2 (drop every follows_marked mark, then mark again each derived
    value a still-marked source feeds). No other mark is added."""
    from .step import run_readings

    readings = run_readings(run)
    held = person_holds(run, readings, human)
    run.findings[:] = [finding for finding in run.findings if not (finding.rule_id == RULE
        and (finding.field_key in held or finding.reason_code.endswith(":" + FOLLOWS_MARKED)))]
    _follow(run, held, readings)


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
