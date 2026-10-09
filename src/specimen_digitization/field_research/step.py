"""Field research at the plan handover: one expert per field (FIELD_RESEARCH.md).

With SPECIMEN_RESEARCH_HARNESS=fields the ordinary workflow runs this as one
external, billable step, ``field_research`` (application.workflow.FIELD_RESEARCH),
for a run whose profile names a harness route. The step reserves the run's
remaining headroom under its cost ceiling, does everything below in memory, and
the workflow saves the run once after it:

1. ``build_tasks``: every reading of every label, named as the organiser names
   them (1A, 1B, 2A), and one FieldTask per profile field with the organiser's
   value after parse, its candidates (the organiser's, and each keyed line the
   parser read, on each reading that writes the line) and the tools its expert
   may call. A field is resolved only to one of its candidates' literals.
2. ``research_fields``: a field that is already an accurate read is finalized
   with no model call; every other field's expert runs at once, inside one
   ``field_research`` span.
3. ``apply_outcomes``: the outcomes become field values and evidence on the
   run, then the derived values (derive.py; G37, G41, G44), then the listed
   fields no reading states are marked "not on the label" (owner decision A;
   ``mark_not_on_label``). A taxon with no genus clears as written, unmatched
   (owner decision B; ``_unmatched_taxon``).
4. ``finalize_fields``: the scientific rules the six-specialist harness applied
   (research_harness/canonical_materialization_v2.py, ``_scientific_reasons``)
   with no blanket human approval (G1). A field that cannot be settled sends the
   record to Needs human review; an outage blocks the run with a retry, and
   every settled field is kept for it.

Once the step has completed on a run it never runs there again: a later pass
(a retry, or a reviewer's decision) applies the rules only (``refinalize``),
on the fields exactly as they are.
"""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import json
import logging
import os
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

import logfire

from specimen_digitization.application.collection_profiles import CollectionProfile
from specimen_digitization.application.domain import (
    Disposition,
    Evidence,
    FieldValue,
    Lookup,
    LookupStatus,
    RunFinding,
    ToolCallRecord,
    ValueState,
    now,
)
from specimen_digitization.application.field_harness import labelled
from specimen_digitization.application.field_validators import CATALOG
from specimen_digitization.application.human_field_carry import KEY as CARRY_KEY
from specimen_digitization.application.integrity import (
    EvidenceIntegrityError,
    verify_evidence,
)
from specimen_digitization.application.lookup import PLACE_FIELDS
from specimen_digitization.application.organiser import (
    CandidateLocation,
    extraction_readings,
    format_locator,
    reading_texts_of,
    stored_candidates,
)
from specimen_digitization.application.policy import PLACEHOLDERS
from specimen_digitization.application.reliability import AdapterFailure
from specimen_digitization.application.workflow import FIELD_RESEARCH, OperationalBlock

from . import derive
from .budget import BudgetExhausted
from .contracts import (
    FIELD_TOOLS,
    NO_APPROVED_AUTHORITY,
    Candidate,
    FieldAnswer,
    FieldOutcome,
    FieldResolver,
    FieldTask,
    Reading,
    SourceAnswer,
    SourceTools,
    not_on_label_fields,
)

LOGGER = logging.getLogger(__name__)

STEP = FIELD_RESEARCH
SOURCE = "field_research"
# The source of the keyed-line parser's label rows (Workflow.parse).
PARSED = "label"
TOOL_VERSION = "field-research-sources-v1"
# The layers only field research writes on this path (the organiser and the
# keyed-line parser leave the layer unset): a field in one of them was settled
# by an earlier attempt, and a retry leaves it as it is.
RESEARCHED = frozenset({"verbatim", "settled", "derived"})
# Deterministic checks: a value one of them gives is the literal's parse.
CHECKS = frozenset({"date_parser", "elevation_parser", "catalog_number_validator"})
# GBIF decides a taxon; every other source supports the value it agrees with.
DECIDING_SOURCES = frozenset({"gbif"})
IRN = "identified_by_irn"
# research_harness.evidence.missing_irn_resolution's value reason.
IRN_REASON = "No qualified determiner Parties identity"
IRN_EXPLANATION = (
    "No approved source can supply a confirmed EMu parties IRN, and a name on the "
    "label is not one."
)
ACCURATE = "Accurate read: the organiser's value, exactly as the named readings write it."
# Work states, as canonical_materialization_v2 names them (37-39).
RESOLVED, WAITING_HUMAN, NONBLOCKING, FAILED = (
    "resolved", "waiting_human", "nonblocking_exception", "operational_failed")
TERMINAL = frozenset({RESOLVED, WAITING_HUMAN, NONBLOCKING})
# A failure that blocks the run with a retry: its blocker code (the run's and,
# with ":<field>", each field's reason) and the status the workflow retries on.
RETRYABLE = {
    "source_unavailable": ("lookup_operational_failure", LookupStatus.PROVIDER),
    "model_error": ("field_research_model_error", LookupStatus.PROVIDER),
    "timeout": ("field_research_timeout", LookupStatus.TIMEOUT),
}
BLOCKER_STATUS = dict(RETRYABLE.values())
FIELD_REASONS = {
    "source_unavailable": "An approved source could not be reached. The record will be retried.",
    "model_error": "An error occurred while researching this field. The record will be retried.",
    "timeout": "Research on this field ran out of time. The record will be retried.",
    "budget_exhausted": "The run's cost limit was reached before this field could be checked.",
    "input_too_large": "The readings and sources for this field were too long to send for checking.",
    None: "No answer was produced for this field.",
}
# The model gateway's own bound on one provider request.
MODEL_TIMEOUT_SECONDS = 120


# ---- inputs ---------------------------------------------------------------

def profile_of(run) -> CollectionProfile:
    """The run's published collection profile (its stored snapshot)."""
    return CollectionProfile.model_validate(dict(run.profile_snapshot), context={"persisted_snapshot": True})


def field_keys(profile: CollectionProfile) -> tuple[str, ...]:
    return (*profile.mandatory_fields, *profile.optional_fields)


def run_readings(run) -> tuple[Reading, ...]:
    """Every reading of every label, named as the organiser names them."""
    return tuple(
        Reading(name=name, region_id=item.region_id, observation_id=item.observation_id,
            input_source=item.role, text=item.text)
        for name, item in labelled(extraction_readings(run)).items()
    )


def human_keys(run) -> frozenset[str]:
    """Fields a person decided (human_field_carry): never researched or changed."""
    carried = run.dependencies.get(CARRY_KEY) or {}
    return frozenset(carried) if isinstance(carried, Mapping) else frozenset()


def _candidates(run, readings: Sequence[Reading]) -> dict[str, list[Candidate]]:
    regions: dict[str, list[Reading]] = {}
    for reading in readings:
        regions.setdefault(reading.region_id, []).append(reading)
    found: dict[str, list[Candidate]] = {}
    for item in stored_candidates(run.fields, run.evidence, reading_texts_of(run)):
        name = item.label
        if name is None:
            # A row from before the organiser cites its whole region: name the
            # region's decided transcript, else its first reading.
            region = regions.get(item.region_id) or []
            decided = [r for r in region if r.input_source == "decided_transcript"]
            if not region:
                continue
            name = (decided or region)[0].name
        found.setdefault(item.field_key, []).append(
            Candidate(reading=name, quote=item.quote, literal=item.literal, evidence_id=item.evidence_id))
    # A keyed line the parser read ("taxon: Danaus plexippus", Workflow.parse)
    # quotes its value from a label's decided transcript: that value is a
    # candidate of each reading of the label whose text has the line.
    rows = {item.id: item for item in run.evidence}
    for key, value in run.fields.items():
        known = {(c.reading, c.literal) for c in found.get(key, ())}
        for evidence_id in value.evidence_ids:
            row = rows.get(evidence_id)
            if row is None or row.source != PARSED or row.kind != "literal":
                continue
            name, sep, literal = row.excerpt.partition(":")
            literal = literal.strip()
            if not sep or name.strip() != key or not literal:
                continue
            for reading in regions.get(row.region_id, ()):
                if (reading.observation_id in row.observation_ids and row.excerpt in reading.text
                        and (reading.name, literal) not in known):
                    known.add((reading.name, literal))
                    found.setdefault(key, []).append(
                        Candidate(reading=reading.name, quote=row.excerpt, literal=literal, evidence_id=row.id))
    return found


def build_tasks(run, profile: CollectionProfile | None = None):
    """``(readings, tasks, context)`` for a run after parse.

    One task per profile field, except a field a person decided and a field an
    earlier attempt already settled (a retry researches only the rest).
    ``context`` is every field's value as the organiser (or an earlier attempt)
    left it.
    """
    profile = profile_of(run) if profile is None else profile
    readings = run_readings(run)
    candidates = _candidates(run, readings)
    human = human_keys(run)
    tasks = []
    for key in field_keys(profile):
        current = run.fields.get(key) or FieldValue()
        if key in human or (current.state == ValueState.SUPPORTED and current.layer in RESEARCHED):
            continue
        tasks.append(FieldTask(key=key, mandatory=key in profile.mandatory_fields,
            current=current.model_copy(deep=True), candidates=tuple(candidates.get(key, ())),
            tools=tuple(FIELD_TOOLS.get(key, ()))))
    context = {key: value.model_copy(deep=True) for key, value in run.fields.items()}
    return readings, tuple(tasks), context


def accurate_read(task: FieldTask) -> bool:
    """A field with no source or check whose organiser value is supported."""
    current = task.current
    return (not task.tools and task.key not in NO_APPROVED_AUTHORITY
        and current.state == ValueState.SUPPORTED and bool(current.literal and current.literal.strip()))


def _current_reading_names(task: FieldTask, readings: Sequence[Reading], evidence) -> list[str]:
    """The readings that write the organiser's literal, by its candidates and
    rows; of a label with a decided transcript, only the decided reading (G19:
    its other reader is evidence only)."""
    literal = task.current.literal
    names = [c.reading for c in task.candidates if c.literal == literal]
    for evidence_id in task.current.evidence_ids:
        row = evidence.get(evidence_id)
        if row is None or row.kind != "literal" or literal not in row.excerpt:
            continue
        names += [r.name for r in readings
            if r.region_id == row.region_id and r.observation_id in row.observation_ids]
    by_name = {r.name: r for r in readings}
    decided = {r.region_id: r.name for r in readings if r.input_source == "decided_transcript"}
    return [n for n in dict.fromkeys(names) if n in by_name and literal in by_name[n].text
        and decided.get(by_name[n].region_id, n) == n]


# ---- research -------------------------------------------------------------

@dataclass(frozen=True)
class SourceCall:
    """One lookup an expert made through the record's sources, in call order."""

    field_key: str
    source_id: str
    query: str
    answer: SourceAnswer
    started_at: str
    completed_at: str


class _RecordedTools:
    """The record's SourceTools, keeping each answer with the call that asked it:
    a lookup row needs its producing call (projection._evidence)."""

    def __init__(self, tools: SourceTools, calls: list[SourceCall]):
        self.tools, self.calls = tools, calls
        self.sources = tuple(tools.sources)

    async def lookup(self, source_id: str, query: str, *, field_key: str) -> SourceAnswer:
        started = now()
        answer = await self.tools.lookup(source_id, query, field_key=field_key)
        self.calls.append(SourceCall(field_key, source_id, query, answer, started, now()))
        return answer


async def _resolve(resolver: FieldResolver, task, readings, context, tools) -> FieldOutcome:
    try:
        outcome = await resolver(task, readings, context, tools=tools)
    except BudgetExhausted:
        return FieldOutcome(task.key, None, failure="budget_exhausted")
    except Exception as error:  # noqa: BLE001 - one field's fault never stops the others
        # A resolver returns field-level problems; this is a defect, logged by class only.
        LOGGER.warning("field_research resolver raised: field=%s error=%s", task.key, type(error).__name__)
        return FieldOutcome(task.key, None, failure="model_error")
    if not isinstance(outcome, FieldOutcome) or outcome.key != task.key:
        LOGGER.warning("field_research resolver answered another field: field=%s", task.key)
        return FieldOutcome(task.key, None, failure="model_error")
    return outcome


def outcome_counts(outcomes: Iterable[FieldOutcome]) -> dict[str, int]:
    """Operational counts only: no field value, label text or source content."""
    outcomes = list(outcomes)
    failed = [o for o in outcomes if o.failure in RETRYABLE]
    review = [o for o in outcomes if o.failure not in RETRYABLE and o.key not in NO_APPROVED_AUTHORITY
        and (o.failure is not None or o.answer is None or o.answer.outcome != "resolved")]
    return {
        "fields_total": len(outcomes),
        "nonblocking_exceptions": sum(o.key in NO_APPROVED_AUTHORITY for o in outcomes),
        "finalized_without_model": sum(o.finalized_without_model and o.key not in NO_APPROVED_AUTHORITY
            for o in outcomes),
        "resolved": sum(o.failure is None and o.answer is not None and o.answer.outcome == "resolved"
            for o in outcomes),
        "review": len(review),
        "failed": len(failed),
        "model_calls": sum(o.model_calls for o in outcomes),
        "cost_micros": sum(o.cost_micros for o in outcomes),
    }


async def research_fields(run, profile: CollectionProfile | None = None, *, resolver: FieldResolver,
        tools: SourceTools, concurrency: int = 10, deadline_seconds: float | None = None,
        prepared=None, calls: list[SourceCall] | None = None) -> list[FieldOutcome]:
    """One outcome per task, in task order.

    An accurate read finalizes with no model call; a field with no approved
    authority (identified_by_irn) gets none either and keeps its nonblocking
    exception; every other field's resolver runs, up to ``concurrency`` at once.
    A field still running at ``deadline_seconds`` is cancelled as a timeout.
    ``prepared`` is build_tasks' result; ``calls`` collects every lookup made.
    """
    profile = profile_of(run) if profile is None else profile
    readings, tasks, context = build_tasks(run, profile) if prepared is None else prepared
    recorded = _RecordedTools(tools, [] if calls is None else calls)
    evidence = {item.id: item for item in run.evidence}
    outcomes: dict[str, FieldOutcome] = {}
    pending: list[FieldTask] = []
    for task in tasks:
        if task.key in NO_APPROVED_AUTHORITY:
            outcomes[task.key] = FieldOutcome(task.key, FieldAnswer(outcome="sources_cannot_resolve",
                explanation=IRN_EXPLANATION), finalized_without_model=True)
        elif accurate_read(task) and (names := _current_reading_names(task, readings, evidence)):
            outcomes[task.key] = FieldOutcome(task.key, FieldAnswer(outcome="resolved",
                literal=task.current.literal, reading_names=names, explanation=ACCURATE),
                finalized_without_model=True)
        else:
            pending.append(task)
    with logfire.span("field_research", fields_total=len(tasks), fields_researched=len(pending)) as span:
        if pending:
            semaphore = asyncio.Semaphore(max(1, concurrency))

            async def one(task):
                async with semaphore:
                    outcomes[task.key] = await _resolve(resolver, task, readings, context, recorded)

            jobs = [asyncio.create_task(one(task)) for task in pending]
            _, late = await asyncio.wait(jobs, timeout=deadline_seconds)
            for job in late:
                job.cancel()
            if late:
                await asyncio.gather(*late, return_exceptions=True)
        for task in pending:
            outcomes.setdefault(task.key, FieldOutcome(task.key, None, failure="timeout"))
        result = [outcomes[task.key] for task in tasks]
        for name, count in outcome_counts(result).items():
            span.set_attribute(name, count)
    return result


# ---- outcomes to field values ---------------------------------------------

def _excerpt_span(text: str, literal: str) -> tuple[int, int, int, int]:
    """The literal's first occurrence and the line(s) around it."""
    start = text.index(literal)
    end = start + len(literal)
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    return line_start, len(text) if line_end < 0 else line_end, start, end


def _literal_row(key: str, reading: Reading, literal: str, asset_id, blobs) -> Evidence:
    """A label row for a reading the expert named that no organiser row covers."""
    quote_start, quote_end, start, end = _excerpt_span(reading.text, literal)
    excerpt = reading.text[quote_start:quote_end]
    record = json.dumps({"field_key": key, "reading": reading.name, "region_id": reading.region_id,
        "observation_ids": [reading.observation_id], "excerpt": excerpt}, sort_keys=True).encode()
    return Evidence(kind="literal", asset_id=asset_id, region_id=reading.region_id,
        observation_ids=[reading.observation_id], source=SOURCE,
        locator=format_locator(CandidateLocation(reading.name, reading.observation_id, quote_start,
            quote_end, start, end)),
        excerpt=excerpt, raw_ref=blobs.put(record) if blobs is not None else None,
        digest=hashlib.sha256(record).hexdigest() if blobs is not None else None)


def _check_row(key: str, tools: Sequence[str], literal: str, value: str, *, texts: Sequence[str],
        date_rules, asset_id, blobs) -> Evidence | None:
    """The evidence of a parsed value that differs from its literal: the field's
    deterministic check run again on the literal here, kept only when it settles
    the literal as that value (a check stores no evidence of its own). None when
    it does not, an ambiguous check included: the value then stays unsupported
    and the rules send it to review."""
    from . import checks

    runs = {
        "date_parser": lambda: checks.parse_date(literal, reading_texts=texts, date_rules=date_rules),
        "elevation_parser": lambda: checks.parse_elevation(literal, reading_texts=texts),
        "catalog_number_validator": lambda: checks.check_catalog_number(literal, reading_texts=texts),
    }
    for tool in tools:
        if tool not in runs:
            continue
        result = runs[tool]()
        if result.status != LookupStatus.SUCCESS or value not in result.values:
            continue
        found = json.dumps(result.as_dict(), sort_keys=True, ensure_ascii=False)
        record = json.dumps({"field_key": key, "value": value, "result": result.as_dict()},
            sort_keys=True).encode()
        return Evidence(kind="derived", asset_id=asset_id, source=SOURCE, locator=f"check:{tool}",
            excerpt=f"{key}: {literal} reads as {value} ({tool}: {found})",
            raw_ref=blobs.put(record) if blobs is not None else None,
            digest=hashlib.sha256(record).hexdigest() if blobs is not None else None)
    return None


def _lineage(named: Sequence[Reading], literal: str, others: Sequence[tuple[Reading, str]] = ()) -> dict:
    """Where the verbatim came from (data contract 4.3, G20, G27, G28).

    A decided transcript among the named readings is the value's source, as the
    workflow's own parse records it. Raw readings alone keep each reader's
    verbatim, the readings that settled it and the first of them as confirmed;
    ``others`` (another raw reader of those labels, with the different text it
    writes) are kept beside them, unsettled, as G27 keeps every reader's text.
    """
    decided = [r for r in named if r.input_source == "decided_transcript"]
    if decided:
        return {"input_source": "decided_transcript", "source_region_id": decided[0].region_id,
            "source_observation_id": decided[0].observation_id}
    regions = {r.region_id for r in named}
    observations = list(dict.fromkeys(r.observation_id for r in named))
    verbatim = dict.fromkeys(observations, literal)
    for reading, text in others:
        verbatim.setdefault(reading.observation_id, text)
    return {"input_source": "raw_reading",
        "source_region_id": next(iter(regions)) if len(regions) == 1 else None,
        "source_observation_id": observations[0],
        "verbatim_by_observation": verbatim,
        "input_source_by_observation": dict.fromkeys(verbatim, "raw_reading"),
        "settled_observation_ids": observations}


def _refusal(task, answer, *, readings, by_name, sources):
    """Why a resolved answer may not settle its field (agreement.refusal, the
    experts' check repeated here on what the field's lookups returned), or
    None. ``sources`` are the source answers the field received."""
    from .agreement import refusal

    literal = answer.literal
    if not literal or not literal.strip():
        return None
    named = [by_name[n] for n in dict.fromkeys(answer.reading_names) if n in by_name and literal in by_name[n].text]
    if not named:
        return None  # _settled refuses it.
    received = list(sources)
    by_id = {item.evidence.id: item for item in received if item.evidence is not None}
    cited = [by_id[i] for i in dict.fromkeys(answer.source_evidence_ids) if i in by_id]
    return refusal(task, readings, literal=literal, named=named, value=answer.value,
        authority_id=answer.authority_id, cited=cited, received=received)


def _place_texts(run, tasks_by_key: Mapping[str, FieldTask], readings) -> dict[str, dict[str, frozenset[str]]]:
    """Each place value field's texts by reading (agreement.reader_literals),
    before this attempt changes any value: its task's candidates and
    verbatims, or the run's for a field not researched in this attempt."""
    from .agreement import PLACE_ORDER, reader_literals

    stored = None
    found = {}
    for key in PLACE_ORDER:
        task = tasks_by_key.get(key)
        if task is None:
            stored = _candidates(run, readings) if stored is None else stored
            task = FieldTask(key=key, mandatory=False, current=run.fields.get(key) or FieldValue(),
                candidates=tuple(stored.get(key, ())), tools=())
        found[key] = {name: frozenset(texts) for name, texts in reader_literals(task, readings).items()}
    return found


def _misfit(run, task, answer, *, sources, readings, by_name, places, pending):
    """Why a place value the agreement rules accept does not fit the label's
    other place fields (agreement.parents_refusal), or None. It is checked
    here, once every outcome is in: field research runs its fields at once,
    and the country must be known. For each reading the answer names (the
    label's decided reading, on a label with one), the other place fields are
    those that reading writes (`places`), and one of them is settled for the
    reading when its value is supported, this attempt has done with it (it is
    not `pending`) and the reading writes its literal, compared as place
    names."""
    from .agreement import PLACE_ORDER, PLACE_VALUE_FIELDS, PlaceField, parents_refusal, place_name, place_settling

    if task.key not in PLACE_VALUE_FIELDS:
        return None
    by_id = {item.evidence.id: item for item in sources if item.evidence is not None}
    cited = [by_id[i] for i in dict.fromkeys(answer.source_evidence_ids) if i in by_id]
    settled_value = answer.value if answer.value is not None else answer.literal
    found = place_settling(task, answer.literal, settled_value, answer.authority_id, cited)
    if found is None:
        return None  # _refusal has refused it already.
    basis, candidate = found
    named = [by_name[n] for n in dict.fromkeys(answer.reading_names) if n in by_name and answer.literal in by_name[n].text]
    decided = {r.region_id: r for r in readings if r.input_source == "decided_transcript"}
    for reading in dict.fromkeys(decided.get(r.region_id, r) for r in named):
        written, settled = {}, {}
        for key in PLACE_ORDER:
            texts = places[key].get(reading.name, frozenset())
            if key == task.key or not texts:
                continue
            value = run.fields.get(key)
            if (key not in pending and value is not None and value.state == ValueState.SUPPORTED and value.literal
                    and place_name(value.literal) in {place_name(text) for text in texts}):
                names = (*sorted(texts), *(text for text in (value.normalized, value.parsed) if text))
                written[key] = settled[key] = PlaceField(tuple(dict.fromkeys(names)), value.authority_id)
            else:
                written[key] = PlaceField(tuple(sorted(texts)))
        refused = parents_refusal(task.key, candidate, basis, written=written, settled=settled)
        if refused is not None:
            return refused
    return None


NEAR_SPELLING_RULES = "field-research-places-v1"


def _place_basis(run, task, answer, sources, value: FieldValue) -> None:
    """What a settled place value's basis adds (agreement.place_basis): for a
    lookup of a notation's expansion (P4), one rule row naming the table entry,
    cited by the value as support (no stored record, so it is never projected);
    for a lookup of the candidate's own name one letter from the label's text,
    which settled only on G34's whole condition (_misfit), a warning finding
    beside the record, naming the deciding answers, which never routes it
    (RunFinding). The value keeps the label's spelling as its literal (G27)."""
    from .agreement import NEAR_SPELLING, NOTATION, PLACE_VALUE_FIELDS, place_basis
    from .notations import expansion

    if task.key not in PLACE_VALUE_FIELDS:
        return
    by_id = {item.evidence.id: item for item in sources if item.evidence is not None}
    cited = [by_id[i] for i in dict.fromkeys(answer.source_evidence_ids) if i in by_id]
    settled = answer.value if answer.value is not None else answer.literal
    basis = place_basis(task, answer.literal, settled, answer.authority_id, cited)
    if basis == NOTATION:
        entry = expansion(answer.literal, task.key)
        row = Evidence(kind="rule", source=SOURCE, locator=f"notation:{entry.field}:{entry.notation}",
            excerpt=(f'{task.key}: "{answer.literal}" is the notation "{entry.notation}", looked up as '
                f'"{entry.expansion}" (G29; field_research.notations)'))
        run.evidence.append(row)
        value.evidence_ids.append(row.id)
        value.evidence_relations[row.id] = "supports"
    elif basis == NEAR_SPELLING:
        code = f"near_spelling:{task.key}"
        if not any(f.reason_code == code for f in run.findings):
            run.findings.append(RunFinding(rule_id="near_spelling", rule_version=NEAR_SPELLING_RULES,
                severity="warning", field_key=task.key, reason_code=code,
                evidence_ids=[item.evidence.id for item in cited]))


def _settled(run, task, outcome, *, by_name, evidence, asset_id, blobs, date_rules=None) -> FieldValue | None:
    """A resolved answer as a supported value, or None when its literal is not in
    the readings it names (the experts' check, repeated here)."""
    from .checks import collapse

    answer = outcome.answer
    literal = answer.literal
    if not literal or not literal.strip():
        return None
    named = [by_name[n] for n in dict.fromkeys(answer.reading_names) if n in by_name and literal in by_name[n].text]
    if not named:
        return None
    relations: dict[str, str] = {}
    for reading in named:
        own = [e for e in task.current.evidence_ids if e in evidence and evidence[e].kind == "literal"
            and evidence[e].region_id == reading.region_id
            and reading.observation_id in evidence[e].observation_ids and literal in evidence[e].excerpt]
        if not own:
            row = _literal_row(task.key, reading, literal, asset_id, blobs)
            run.evidence.append(row)
            evidence[row.id] = row
            own = [row.id]
        relations.update(dict.fromkeys((e for e in own if e not in relations), "supports"))
    # Every other reader's organiser row stays cited: the same text supports the
    # value, a different text contradicts it and is kept as evidence (G19, G20).
    for candidate in task.candidates:
        if candidate.evidence_id in evidence and candidate.evidence_id not in relations:
            same = collapse(candidate.literal) == collapse(literal)
            relations[candidate.evidence_id] = "supports" if same else "contradicts"
    regions = {r.region_id for r in named}
    settled_by = {r.observation_id for r in named}
    others = [(by_name[c.reading], c.literal) for c in task.candidates if c.reading in by_name
        and by_name[c.reading].input_source == "raw_reading" and by_name[c.reading].region_id in regions
        and by_name[c.reading].observation_id not in settled_by and collapse(c.literal) != collapse(literal)]
    cited = [e for e in answer.source_evidence_ids if e in evidence and evidence[e].kind != "literal"]
    for evidence_id in cited:
        relations[evidence_id] = "decides" if evidence[evidence_id].source in DECIDING_SOURCES else "supports"
    value = answer.value if answer.value not in (None, literal) else None
    parsed, normalized = literal, None
    if value is not None and set(task.tools) & CHECKS:
        parsed = value
        if not any(evidence[e].kind in {"authority", "authority_selection", "derived"}
                and value in evidence[e].excerpt for e in cited):
            row = _check_row(task.key, task.tools, literal, value, texts=[r.text for r in by_name.values()],
                date_rules=date_rules, asset_id=asset_id, blobs=blobs)
            if row is not None:
                run.evidence.append(row)
                evidence[row.id] = row
                relations[row.id] = "supports"
    elif value is not None:
        normalized = value
    return FieldValue(state=ValueState.SUPPORTED, literal=literal, parsed=parsed, normalized=normalized,
        authority_id=answer.authority_id, evidence_ids=list(relations), evidence_relations=relations,
        reason=answer.explanation, layer="verbatim" if outcome.finalized_without_model else "settled",
        **_lineage(named, literal, others))


# Where the organiser's value came from (data contract 4.3, G27, G28).
LINEAGE = ("input_source", "source_region_id", "source_observation_id", "verbatim_by_observation",
    "input_source_by_observation", "settled_observation_ids")


def _unsettled(task, state, *, literal=None, cited=(), reason) -> FieldValue:
    """A value research did not settle: the organiser's rows stay cited, with the
    sources the expert cited beside them, and the reason says why. Its lineage
    stays too, so each reader's verbatim is a candidate a person can choose
    (projection._fields); a field the label lacks has none."""
    relations = dict.fromkeys(cited, "supports")
    ids = list(dict.fromkeys([*task.current.evidence_ids, *cited]))
    lineage = {} if state == ValueState.NOT_PRESENT else {
        name: getattr(task.current, name) for name in LINEAGE}
    return FieldValue(state=state, literal=literal, evidence_ids=ids, evidence_relations=relations,
        reason=reason, **lineage)


def _field_value(run, task, outcome, *, readings, by_name, evidence, asset_id, blobs, date_rules=None,
        sources: Sequence[SourceAnswer] = (), places, pending=frozenset()) -> FieldValue:
    answer = outcome.answer
    current = task.current
    if task.key in NO_APPROVED_AUTHORITY:
        # research_harness.evidence.missing_irn_resolution: unresolved, no party.
        return FieldValue(state=ValueState.UNKNOWN, evidence_ids=list(current.evidence_ids),
            reason=IRN_REASON)
    cited = [e for e in (answer.source_evidence_ids if answer else ()) if e in evidence
        and evidence[e].kind != "literal"]
    if outcome.failure is not None or answer is None:
        reason = FIELD_REASONS.get(outcome.failure, FIELD_REASONS[None])
        return _unsettled(task, ValueState.UNRESOLVED, literal=current.literal, cited=cited, reason=reason)
    if answer.outcome == "resolved":
        refused = _refusal(task, answer, readings=readings, by_name=by_name, sources=sources)
        if refused is not None:
            # A pick between readers no source settles is ambiguous; a value no
            # decided transcript or place source supports is unresolved.
            if refused.differ:
                return _unsettled(task, ValueState.AMBIGUOUS, cited=cited,
                    reason=f"{refused.reason} {answer.explanation}")
            return _unsettled(task, ValueState.UNRESOLVED, literal=current.literal, cited=cited,
                reason=f"{refused.reason} {answer.explanation}")
        misfit = _misfit(run, task, answer, sources=sources, readings=readings, by_name=by_name,
            places=places, pending=pending)
        if misfit is not None:
            return _unsettled(task, ValueState.UNRESOLVED, literal=current.literal, cited=cited,
                reason=f"{misfit.reason} {answer.explanation}")
        settled = _settled(run, task, outcome, by_name=by_name, evidence=evidence, asset_id=asset_id,
            blobs=blobs, date_rules=date_rules)
        if settled is not None:
            _place_basis(run, task, answer, sources, settled)
            return settled
        return _unsettled(task, ValueState.UNRESOLVED, literal=current.literal, cited=cited,
            reason="The answer's literal is not in the readings it names. " + answer.explanation)
    if answer.outcome == "label_lacks_value":
        return _unsettled(task, ValueState.NOT_PRESENT, cited=cited, reason=answer.explanation)
    if answer.outcome == "several_possibilities":
        options = [o for o in dict.fromkeys(answer.options) if o and o.strip()]
        reason = answer.explanation + (" Options: " + "; ".join(options) + "." if options else "")
        return _unsettled(task, ValueState.AMBIGUOUS, cited=cited, reason=reason)
    # sources_cannot_resolve: a taxon that names no genus clears as written,
    # unmatched (owner decision B); otherwise the label's text stays when a
    # reading writes it.
    if task.key == "taxon":
        unmatched = _unmatched_taxon(run, task, readings=readings, by_name=by_name, evidence=evidence,
            asset_id=asset_id, blobs=blobs, sources=sources)
        if unmatched is not None:
            return unmatched
    literal = answer.literal if answer.literal and any(answer.literal in r.text for r in readings) else current.literal
    return _unsettled(task, ValueState.UNRESOLVED, literal=literal, cited=cited, reason=answer.explanation)


# Owner decision B, 2026-10-09: a taxon whose label names no genus clears as
# written, marked unmatched, with GBIF's no-match as its support.
NO_GENUS_CHECK = "check:taxon_no_genus"
UNMATCHED = "Unmatched: the label names no genus, so GBIF has nothing to match"


def no_genus_excerpt(literal: str, lookup_id: str) -> str:
    """The excerpt of an unmatched taxon's check row: its literal and the GBIF
    no-name lookup the run keeps for it."""
    return (f'taxon: "{literal}" names no genus, so GBIF has nothing to match '
        f"(GBIF lookup {lookup_id}: no_match, no scientific name; nothing was sent)")


def _no_name(lookup, literal: str) -> bool:
    """Whether a run lookup is GBIF's no-name answer for this literal
    (application.lookup.no_name_lookup): no_match, nothing asked or stored,
    no candidates, the literal as its verbatim name."""
    metadata = getattr(lookup, "metadata", None) or {}
    return (isinstance(lookup, Lookup) and lookup.provider == "gbif" and lookup.status == LookupStatus.NO_MATCH
        and not lookup.query and not lookup.candidates and not lookup.raw_ref
        and metadata.get("verbatim_name") == literal and metadata.get("reason") == "no_scientific_name")


def _unmatched_taxon(run, task, *, readings, by_name, evidence, asset_id, blobs,
        sources: Sequence[SourceAnswer]) -> FieldValue | None:
    """Owner decision B: the taxon as written, unmatched, when the expert
    found that GBIF cannot resolve it and the label names no genus. All of:
    - the organiser's literal names no genus (checks.names_no_genus: "sp. 30
      <female sign>"; "Aus bus n. sp." and "Epipsocus sp. 1" do not qualify);
    - every taxon candidate is the same morphocode, a text with no genus and
      the same code (checks.morphocode: a reader's "Sp.30 <female sign>"
      beside "sp. 30 <female sign>", but never "sp. 39");
    - the label names no genus for that code (checks.label_names_no_genus):
      wherever any reading writes it, no word that may be a genus is written
      immediately before it, on its line or ending the line above, or after
      it on its line. A candidate "sp. 1" taken from "Epipsocus sp. 1", or
      from "Epipsocus" with "sp. 1" on the next line, does not qualify;
    - the readers settle on the literal by B1's rule (agreement.labels):
      each label that writes the taxon settles on its own on that one text.
      With no successful lookup that is a label's decided transcript (its
      other readers are evidence only), or readers of a label with none that
      each write exactly that text.
    The value is built as a settled answer is (_settled: the label rows and
    the lineage), with the literal as written, no authority and the layer
    settled, and cites one check row naming GBIF's no-name lookup, which the
    run keeps (lookup.no_name_lookup: no request is made; the step adds it
    when the expert never asked GBIF that literal). None otherwise: a taxon
    with a genus GBIF cannot decide still goes to review."""
    from specimen_digitization.application.lookup import no_name_lookup

    from .agreement import DECIDED, SOURCE_IDS, candidate_literal, labels, reader_literals
    from .checks import collapse, label_names_no_genus, morphocode

    literal = task.current.literal
    code = morphocode(literal)
    if task.key != "taxon" or code is None:
        return None
    if not task.candidates or any(morphocode(c.literal) != code for c in task.candidates):
        return None
    if not label_names_no_genus(code, [r.text for r in readings]):
        return None
    want = collapse(literal)
    tools = frozenset(task.tools) & SOURCE_IDS
    found = labels(task, readings, [a for a in sources if a.source_id in tools])
    if not found or any(label.settled != frozenset({want}) or label.by_source for label in found.values()):
        return None
    written = reader_literals(task, readings)
    decided = {r.region_id for r in readings if r.input_source == DECIDED}
    named = [r for r in readings if r.region_id in found and want in written.get(r.name, ())
        and (r.input_source == DECIDED or r.region_id not in decided)]
    whole = candidate_literal(task, readings, literal, named) if named else None
    if whole is None:
        return None
    answer = FieldAnswer(outcome="resolved", literal=whole, reading_names=[r.name for r in named],
        explanation=UNMATCHED)
    value = _settled(run, task, FieldOutcome(task.key, answer), by_name=by_name, evidence=evidence,
        asset_id=asset_id, blobs=blobs)
    if value is None:
        return None
    lookup = next((item for item in run.lookups if _no_name(item, whole)), None)
    if lookup is None:
        # GBIF's answer for a name with no genus, made with no request. First,
        # so the lookup a reviewer chooses a taxon from stays last.
        lookup = no_name_lookup(whole)
        run.lookups.insert(0, lookup)
    record = json.dumps({"field_key": task.key, "literal": whole, "check": "names_no_genus",
        "lookup_id": lookup.id, "readings": [r.name for r in named]}, sort_keys=True).encode()
    row = Evidence(kind="derived", asset_id=asset_id, source=SOURCE, locator=NO_GENUS_CHECK,
        excerpt=no_genus_excerpt(whole, lookup.id),
        raw_ref=blobs.put(record) if blobs is not None else None,
        digest=hashlib.sha256(record).hexdigest() if blobs is not None else None)
    run.evidence.append(row)
    evidence[row.id] = row
    value.evidence_ids.append(row.id)
    value.evidence_relations[row.id] = "supports"
    return value


def _tool_call(run, made: Sequence[SourceCall], item: Evidence, readings: Sequence[Reading]) -> ToolCallRecord:
    """The call that produced a stored source answer, for every field that asked it.

    The query is text a reading writes, but which reading an expert copied it
    from is not recorded: the call names the first decided transcript, else the
    first reading.
    """
    first = made[0]
    anchor = next((r for r in readings if r.input_source == "decided_transcript"), readings[0] if readings else None)
    attempt = run.attempts.get(STEP, 1)
    return ToolCallRecord(call_key=f"{STEP}:{attempt}:{item.id}", phase="lookup", tool=first.source_id,
        tool_version=TOOL_VERSION, source=first.source_id,
        field_keys=list(dict.fromkeys(call.field_key for call in made)),
        input_source=anchor.input_source if anchor else "raw_reading",
        region_id=anchor.region_id if anchor else None,
        observation_id=anchor.observation_id if anchor and anchor.input_source == "raw_reading" else None,
        attempt=attempt, arguments={"query": first.query}, outcome=first.answer.status,
        result={"candidate_count": len(first.answer.candidates)}, evidence_id=item.id,
        started_at=first.started_at, completed_at=first.completed_at)


def _add_sources(run, outcomes: Sequence[FieldOutcome], calls: Sequence[SourceCall], readings,
        taxon_literals: Sequence[str] = ()) -> None:
    """Every captured source response once as evidence, with its producing call,
    and every taxonomy lookup once on the run, the one a reviewer chooses a
    taxon from last (_choosable_lookup_last)."""
    known = {item.id: item for item in run.evidence}
    produced = {record.evidence_id for record in run.tool_calls if record.evidence_id}
    by_evidence: dict[str, list[SourceCall]] = {}
    for call in calls:
        if call.answer.evidence is not None:
            by_evidence.setdefault(call.answer.evidence.id, []).append(call)
    captured = [item for outcome in outcomes for item in outcome.evidence]
    captured += [call.answer.evidence for call in calls if call.answer.evidence is not None]
    for item in captured:
        existing = known.get(item.id)
        if existing is not None:
            if existing != item:
                raise EvidenceIntegrityError("evidence_integrity_failure")
            continue
        made = by_evidence.get(item.id, [])
        if item.kind == "lookup" and not made:
            # A lookup row projects only with its one producing call; an unrecorded
            # one is left out rather than stop the record's projection.
            LOGGER.warning("field_research source evidence without its call left out: source=%s", item.source)
            continue
        run.evidence.append(item)
        known[item.id] = item
        if made and item.id not in produced:
            run.tool_calls.append(_tool_call(run, made, item, readings))
            produced.add(item.id)
    lookups = [lookup for outcome in outcomes for lookup in outcome.lookups]
    lookups += [call.answer.taxonomy_lookup for call in calls if call.answer.taxonomy_lookup is not None]
    present = {lookup.id for lookup in run.lookups}
    for lookup in lookups:
        if isinstance(lookup, Lookup) and lookup.id not in present:
            run.lookups.append(lookup)
            present.add(lookup.id)
    _choosable_lookup_last(run, calls, taxon_literals)


def _choosable_lookup_last(run, calls: Sequence[SourceCall], taxon_literals: Sequence[str]) -> None:
    """Put last in run.lookups the lookup a reviewer chooses a taxon from: the
    reviewer's taxonomy resolution offers only run.lookups[-1]'s candidates
    (api.apply_decision). That is the last success or ambiguous lookup with
    candidates whose query is the whole name the label writes
    (checks.taxon_queries of the taxon's literals), else the last with
    candidates. A lookup with none (a failure, no match) is never last while
    one with candidates exists. Nothing moves when no lookup has candidates."""
    from .checks import collapse, taxon_queries

    asked = {}
    for call in calls:
        lookup = call.answer.taxonomy_lookup
        if isinstance(lookup, Lookup):
            asked.setdefault(lookup.id, call.query)
    names = frozenset().union(*(taxon_queries(literal) for literal in taxon_literals if literal))
    choosable = [lookup for lookup in run.lookups if lookup.candidates
        and lookup.status in (LookupStatus.SUCCESS, LookupStatus.AMBIGUOUS)]

    def query(lookup) -> str:
        found = asked.get(lookup.id) or lookup.query.get("scientificName") or lookup.query.get("name")
        return collapse(found) if isinstance(found, str) else ""

    grounded = [lookup for lookup in choosable if query(lookup) in names]
    preferred = (grounded or choosable or [None])[-1]
    if preferred is not None and run.lookups[-1] is not preferred:
        index = next(i for i, lookup in enumerate(run.lookups) if lookup is preferred)
        run.lookups.append(run.lookups.pop(index))


def _taxon_literals(run, tasks: Sequence[FieldTask], outcomes: Sequence[FieldOutcome]) -> list[str]:
    """What the label writes as the taxon: the organiser's value, its
    candidates and readers' verbatims, and the taxon expert's literal."""
    found: list[str | None] = []
    for task in tasks:
        if task.key == "taxon":
            found += [task.current.literal, *(c.literal for c in task.candidates),
                *task.current.verbatim_by_observation.values()]
    found += [o.answer.literal for o in outcomes if o.key == "taxon" and o.answer is not None]
    current = run.fields.get("taxon")
    if current is not None:
        found += [current.literal, *current.verbatim_by_observation.values()]
    return [literal for literal in dict.fromkeys(found) if literal]


def apply_outcomes(run, profile: CollectionProfile | None, tasks: Sequence[FieldTask],
        outcomes: Sequence[FieldOutcome], *, blobs=None, calls: Sequence[SourceCall] = (),
        asset_id: str | None = None) -> list[str]:
    """Turn the outcomes into the run's field values and evidence, in memory only.

    resolved: supported, with the literal, its lineage, the label rows of the
    readings it names (a new row where none covers a reading), every other
    reader's organiser row (supporting or contradicting it) and the source
    evidence it cites (GBIF decides; other sources support); a deterministic
    check's parse gets a "derived" row when the check, run again on the
    literal, gives that value. A resolved answer the agreement rules refuse
    (agreement.refusal: a literal that is not a whole candidate of the
    readings it names, or that the label's decided transcript does not write,
    a pick between readers no source settles, a place no place source
    confirms), or whose place does not lie in the country and province
    settled for its reading (_misfit, after the places above it), is
    ambiguous or unresolved instead. label_lacks_value: not present;
    sources_cannot_resolve: unresolved, except a taxon that names no genus,
    supported as written and unmatched (_unmatched_taxon); several_possibilities:
    ambiguous, the options in the reason; a failure: unresolved with a
    retryable reason. Then the derived values, then the listed fields the
    label does not state (mark_not_on_label); the keys derived are returned.
    """
    from .agreement import PLACE_ORDER

    profile = profile_of(run) if profile is None else profile
    readings = run_readings(run)
    by_name = {reading.name: reading for reading in readings}
    if asset_id is None:
        asset_id = run.regions[0].asset_id if run.regions else None
    tasks_by_key = {task.key: task for task in tasks}
    places = _place_texts(run, tasks_by_key, readings)
    _add_sources(run, outcomes, calls, readings, _taxon_literals(run, tasks, outcomes))
    evidence = {item.id: item for item in run.evidence}
    human = human_keys(run)
    received: dict[str, list[SourceAnswer]] = {}
    for call in calls:
        received.setdefault(call.field_key, []).append(call.answer)
    # The places first, from the country down: a place below it settles only
    # inside the country (and province) settled before it (_misfit).
    ordered = sorted(outcomes, key=lambda o: PLACE_ORDER.index(o.key) if o.key in PLACE_ORDER else len(PLACE_ORDER))
    pending = {outcome.key for outcome in ordered}
    for outcome in ordered:
        task = tasks_by_key.get(outcome.key)
        pending.discard(outcome.key)
        if task is None or task.key in human:
            continue
        run.fields[task.key] = _field_value(run, task, outcome, readings=readings, by_name=by_name,
            evidence=evidence, asset_id=asset_id, blobs=blobs, date_rules=profile.date_rules,
            sources=received.get(task.key, ()), places=places, pending=frozenset(pending))
    eligible = [key for key in field_keys(profile) if key not in human]
    derived = derive.fill(run, eligible=eligible, asset_id=asset_id, blobs=blobs)
    # Last, so that a value derived above is never marked absent.
    mark_not_on_label(run, profile, tasks, outcomes, readings=readings, asset_id=asset_id, blobs=blobs)
    return derived


# ---- fields the label does not state (owner decision A) -------------------

NOT_ON_LABEL_CHECK = "check:not_on_label"
NOT_ON_LABEL_REASON = "Not on the label: no reading states it, and its expert found none."
# The place fields whose literal can hold another place field's text.
PLACE_TEXT_FIELDS = ("country", "province_state", "county", "city", "precise_location")
# The fields whose organiser text may sit inside another settled place (the
# organiser's "Mt. McKinley" as a city, inside the settled precise location).
INSIDE_A_PLACE = frozenset({"county", "city", "precise_location"})
ELEVATION_FIELDS = frozenset({"elevation_from_m", "elevation_to_m", "elevation_from_ft", "elevation_to_ft"})
UNREADABLE_TEXT = "[unreadable]"


def not_on_label_keys(profile: CollectionProfile) -> frozenset[str]:
    """The profile's fields that may clear as "not on the label", by its id
    and version (contracts.NOT_ON_LABEL): a run's pinned profile, so a Retry
    sees the same list."""
    return not_on_label_fields(profile.id, profile.version)


def _whole_label_read(run, readings: Sequence[Reading]) -> bool:
    """Every label was read whole: label coverage confirmed; each label has
    two or more readers, each with text, and two or more named readings; and
    no part of any label is unreadable (no reader's unreadable span or
    "[unreadable]" text, no transcript marked unreadable)."""
    if not run.coverage_confirmed or not run.regions:
        return False
    for region in run.regions:
        observed = [o for o in run.observations if o.region_id == region.id]
        named = [r for r in readings if r.region_id == region.id]
        if len(observed) < 2 or len(named) < 2 or any(not o.literal_text.strip() for o in observed):
            return False
    if any(not r.text.strip() for r in readings):
        return False
    if any(o.unreadable_spans or o.literal_text.strip().casefold() == UNREADABLE_TEXT for o in run.observations):
        return False
    return not any(t.value_state == ValueState.UNREADABLE or (t.text or "").strip().casefold() == UNREADABLE_TEXT
        for t in run.transcripts)


def _organiser_texts(task: FieldTask) -> list[str]:
    """What the organiser found for the field: its candidates' literals, and
    its value's literal and readers' verbatims."""
    texts = [c.literal for c in task.candidates]
    texts += [task.current.literal, *task.current.verbatim_by_observation.values()]
    return [text for text in texts if text and text.strip()]


def _inside_a_settled_place(run, key: str, text: str) -> bool:
    """Whether the text, collapsed and case-folded, sits inside the literal of
    another supported place field."""
    from .checks import collapse

    folded = collapse(text).casefold()
    for other in PLACE_TEXT_FIELDS:
        value = run.fields.get(other)
        if (other != key and value is not None and value.state == ValueState.SUPPORTED and value.literal
                and folded and folded in collapse(value.literal).casefold()):
            return True
    return False


def _elevation_written(run, readings: Sequence[Reading]) -> bool:
    """Whether any reading writes an elevation, as the place tool reads one
    (georef_locality.read_locality), in its whole text or in any one line."""
    from specimen_digitization.application.georef_locality import read_locality

    texts = dict.fromkeys([*(r.text for r in readings), *(o.literal_text for o in run.observations)])
    return any(read_locality(part).elevations for text in texts for part in (text, *text.splitlines())
        if part.strip())


def _place_settled_below_province(run) -> bool:
    """A city or county is supported: a precise location the label does not
    state then adds nothing finer than the places settled."""
    return any((run.fields.get(key) or FieldValue()).state == ValueState.SUPPORTED for key in ("city", "county"))


def not_on_label_excerpt(key: str, readings: Sequence[Reading]) -> str:
    """The excerpt of a field's not-on-the-label check row: the readings it
    names, by name and observation."""
    names = ", ".join(r.name for r in readings)
    return (f"{key}: not on the label; none of the readings {names} states it and its expert found none\n"
        + "readings: " + "; ".join(f"{r.name} {r.observation_id}" for r in readings))


def mark_not_on_label(run, profile: CollectionProfile, tasks: Sequence[FieldTask],
        outcomes: Sequence[FieldOutcome], *, readings: Sequence[Reading] | None = None,
        asset_id: str | None = None, blobs=None) -> list[str]:
    """Owner decision A (2026-10-09): a field on the profile's list
    (not_on_label_keys) that a person has not decided, researched in this
    attempt, is marked "not on the label" when all of these hold:
    1. its expert answered label_lacks_value, with no failure, and the field
       was not finalized without a model call (a fallback answer is
       sources_cannot_resolve, so it never qualifies);
    2. its value is still not present (a value derive.fill derived is kept);
    3. label coverage is confirmed, every label has two or more readings and
       every reading has text (_whole_label_read);
    4. no part of any label is unreadable (_whole_label_read);
    5. the organiser found no text for it (_organiser_texts); for a county,
       a city or a precise location, a text counts as absent only when it
       sits inside the literal of another supported place field;
    6. for an elevation, no reading writes an elevation (_elevation_written);
    7. for a precise location, a city or a county is supported.
    The value then cites one check row (kind "derived", locator
    "check:not_on_label") naming every reading of the run, and its reason
    starts "Not on the label:". The row has no observation_ids: one row may
    not cite readings of several labels (integrity.verify_evidence), so its
    excerpt and stored record name them (not_on_label_excerpt). A row an
    earlier attempt wrote is dropped from a field researched again. Returns
    the keys marked."""
    readings = run_readings(run) if readings is None else readings
    tasks_by_key = {task.key: task for task in tasks}
    by_key = {o.key: o for o in outcomes if o.key in tasks_by_key}
    human = human_keys(run)
    rows = {item.id: item for item in run.evidence}
    for key in by_key:
        value = run.fields.get(key)
        if key in human or value is None:
            continue
        for stale in [i for i in value.evidence_ids if i in rows and rows[i].locator == NOT_ON_LABEL_CHECK]:
            value.evidence_ids.remove(stale)
            value.evidence_relations.pop(stale, None)
    allowed = not_on_label_keys(profile)
    if not allowed or not _whole_label_read(run, readings):
        return []
    elevation = None
    marked = []
    for key in field_keys(profile):
        outcome, value = by_key.get(key), run.fields.get(key)
        if key not in allowed or key in human or outcome is None or value is None:
            continue
        answer = outcome.answer
        if (outcome.failure is not None or answer is None or answer.outcome != "label_lacks_value"
                or outcome.finalized_without_model):
            continue
        if value.state != ValueState.NOT_PRESENT or any((value.literal, value.parsed, value.normalized,
                value.authority_id, value.authority_identity, value.verbatim_by_observation)):
            continue
        if any(not (key in INSIDE_A_PLACE and _inside_a_settled_place(run, key, text))
                for text in _organiser_texts(tasks_by_key[key])):
            continue
        if key in ELEVATION_FIELDS:
            elevation = _elevation_written(run, readings) if elevation is None else elevation
            if elevation:
                continue
        if key == "precise_location" and not _place_settled_below_province(run):
            continue
        record = json.dumps({"field_key": key, "check": "not_on_label", "readings": [
            {"name": r.name, "region_id": r.region_id, "observation_id": r.observation_id,
             "input_source": r.input_source} for r in readings]}, sort_keys=True).encode()
        row = Evidence(kind="derived", asset_id=asset_id, source=SOURCE, locator=NOT_ON_LABEL_CHECK,
            excerpt=not_on_label_excerpt(key, readings),
            raw_ref=blobs.put(record) if blobs is not None else None,
            digest=hashlib.sha256(record).hexdigest() if blobs is not None else None)
        run.evidence.append(row)
        value.evidence_ids.append(row.id)
        value.evidence_relations[row.id] = "supports"
        value.reason = f"{NOT_ON_LABEL_REASON} {answer.explanation}".strip()
        marked.append(key)
    return marked


def not_on_label(key: str, value: FieldValue, run, evidence: Mapping[str, Evidence],
        allowed: frozenset[str]) -> bool:
    """Whether a field clears as "not on the label" (mark_not_on_label),
    checked on the stored value: the key is on the profile's list
    (`allowed`); the value is not present, with no literal, parsed,
    normalized or authority value and no reader's text; it cites as support
    a not-on-the-label check row whose readings are the run's current
    readings (not_on_label_excerpt); and, for a precise location, a city or a
    county is still supported. An older not-present value, with no such row,
    never clears."""
    if key not in allowed or value.state != ValueState.NOT_PRESENT:
        return False
    if any((value.literal, value.parsed, value.normalized, value.authority_id, value.authority_identity,
            value.verbatim_by_observation)):
        return False
    if key == "precise_location" and not _place_settled_below_province(run):
        return False
    expected = not_on_label_excerpt(key, run_readings(run))
    for evidence_id in value.evidence_ids:
        row = evidence.get(evidence_id)
        if (row is not None and value.evidence_relations.get(evidence_id) == "supports" and row.kind == "derived"
                and row.source == SOURCE and row.locator == NOT_ON_LABEL_CHECK and row.excerpt == expected):
            return True
    return False


# ---- the scientific rules -------------------------------------------------

def _text(value: FieldValue | None) -> str:
    """A field's value as the range and order rules read it; "" when it has none."""
    return "" if value is None else (value.normalized or value.parsed or value.literal or "")


def _date_bounds(value: FieldValue) -> tuple[date, date]:
    """research_harness/canonical_materialization.py 90-102, unchanged."""
    text = value.normalized or value.parsed or value.literal or ""
    if not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", text):
        raise ValueError("date_precision_unproved")
    parts = [int(part) for part in text.split("-")]
    precision = ("year", "month", "day")[len(parts) - 1]
    if value.precision is not None and value.precision != precision:
        raise ValueError("date_precision_mismatch")
    year, month = parts[0], parts[1] if len(parts) > 1 else 1
    lower = date(year, month, parts[2] if len(parts) > 2 else 1)
    upper = (date(year, 12, 31) if len(parts) == 1 else
             date(year, month, calendar.monthrange(year, month)[1]) if len(parts) == 2 else lower)
    return lower, upper


def _raw_grounded(value: FieldValue, run) -> bool:
    """research_harness/canonical_materialization.py 105-114, unchanged."""
    readings = {reading.id: reading for reading in run.observations}
    verbatim = value.verbatim_by_observation
    if not verbatim or not value.settled_observation_ids or not set(value.settled_observation_ids) <= set(verbatim):
        return False
    return all(identifier in readings and text and text in readings[identifier].literal_text
        and readings[identifier].raw_ref and readings[identifier].raw_sha256
        and (value.source_region_id is None or readings[identifier].region_id == value.source_region_id)
        and value.input_source_by_observation.get(identifier, value.input_source) == "raw_reading"
        for identifier, text in verbatim.items())


def taxon_decided(taxon: FieldValue, tool_calls, evidence: Mapping[str, Evidence],
        lookups: Sequence[Lookup] = ()) -> bool:
    """Whether the taxon is GBIF's decision for its literal, as the expert's check
    requires (experts._Expert._validate_taxon): a successful GBIF call it cites
    whose query is the name the literal writes (checks.taxon_query_grounded),
    and whose evidence names, as its locator, the candidate the value and
    authority_id are ("name | authority_id | ..." in sources.excerpt).

    Or a reviewer chose it (taxon_chosen)."""
    from .checks import taxon_query_grounded

    settled = taxon.normalized or taxon.literal
    if not taxon.authority_id or not taxon.literal or not settled:
        return False
    if taxon_chosen(taxon, settled, evidence, lookups):
        return True
    for call in tool_calls:
        item = evidence.get(call.evidence_id)
        if (item is None or "taxon" not in call.field_keys or call.evidence_id not in taxon.evidence_ids
                or call.outcome.value != "success" or call.source not in FIELD_TOOLS["taxon"]):
            continue
        if (taxon_query_grounded(str(call.arguments.get("query", "")), taxon.literal)
                and item.locator == taxon.authority_id
                and f"{settled} | {taxon.authority_id} | " in item.excerpt):
            return True
    return False


def taxon_chosen(taxon: FieldValue, settled: str, evidence: Mapping[str, Evidence],
        lookups: Sequence[Lookup]) -> bool:
    """Whether a reviewer chose the taxon from GBIF's candidates, as
    policy.evaluate accepts an ambiguous lookup with a selection: the taxon
    cites the authority_selection row that api.apply_decision's
    taxonomy_resolution records (its source a stored success or ambiguous
    lookup, the lookups the decision chooses from; its locator "candidate:"
    and the authority_id), and that lookup returned the candidate, whose key
    is the authority_id and whose scientificName is the value, as the decision
    copies them. Nothing else is a person's choice of taxon."""
    found = {lookup.id: lookup for lookup in lookups
        if lookup.status in (LookupStatus.SUCCESS, LookupStatus.AMBIGUOUS)}
    for evidence_id in taxon.evidence_ids:
        item = evidence.get(evidence_id)
        if (item is None or item.kind != "authority_selection" or item.source not in found
                or item.locator != "candidate:" + taxon.authority_id):
            continue
        for candidate in found[item.source].candidates:
            usage = candidate.get("usage", candidate) if isinstance(candidate, Mapping) else None
            if (isinstance(usage, Mapping) and str(usage.get("key", "")) == taxon.authority_id
                    and usage.get("scientificName") == settled):
                return True
    return False


def taxon_unmatched(taxon: FieldValue, evidence: Mapping[str, Evidence], lookups: Sequence[Lookup] = (), *,
        texts: Sequence[str]) -> bool:
    """Whether the taxon is owner decision B's unmatched name
    (_unmatched_taxon), checked on the stored value: supported, its literal a
    name with no genus (checks.names_no_genus) that the label, the readings'
    `texts`, writes with no genus beside it (checks.label_names_no_genus), as
    written (parsed is the literal or empty), with no normalized value or
    authority, in the settled layer, citing as support the check row for that
    literal and the GBIF no-name lookup of the run that the row names. A taxon
    with a genus never is."""
    from .checks import label_names_no_genus, morphocode

    literal = taxon.literal
    code = morphocode(literal)
    if (taxon.state != ValueState.SUPPORTED or code is None or not label_names_no_genus(code, texts)
            or taxon.layer != "settled" or taxon.parsed not in (None, literal)
            or any((taxon.normalized, taxon.authority_id, taxon.authority_identity))):
        return False
    rows = [evidence[i] for i in taxon.evidence_ids if i in evidence and taxon.evidence_relations.get(i) == "supports"
        and evidence[i].kind == "derived" and evidence[i].source == SOURCE and evidence[i].locator == NO_GENUS_CHECK]
    return any(row.excerpt == no_genus_excerpt(literal, lookup.id)
        for row in rows for lookup in lookups if _no_name(lookup, literal))


def scientific_reasons(run, latest_work: Mapping[str, str], *, mandatory: Iterable[str],
        qualified: frozenset[str], today: date, allowed: frozenset[str] = frozenset()) -> list[str]:
    """canonical_materialization_v2._scientific_reasons (182-295), ported.

    The same G1/G6/G42/G43 rules on the same run fields, evaluated on the
    fields whose work is terminal; no blanket human approval (G1: 195-197 retire
    policy.py 31-34 and 138-139). Where field research differs, it says so:
    - 194: a field waiting on a person is not given research_human_question:
      the app has no text for it, and mandatory_unresolved:{field} (233-235)
      already names the field.
    - 222-236: the published profile's optional fields (identified_by_irn) are
      checked only when they hold a value, as policy.py checks only mandatory
      fields; the research profile made all twenty mandatory.
    - 227-231: a field with no approved authority keeps the nonblocking
      exception (contracts.NO_APPROVED_AUTHORITY, the profile's configured
      treatment; evidence.emu_irn_exception).
    - 254-260: the taxon's settling call is the stored GBIF lookup's producing
      ToolCallRecord, which field research records for every source answer;
      its query is the name the literal writes and its decided candidate is
      the value (taxon_decided), as research_harness/evidence.py 665-722 holds
      the native deciding query; or a reviewer chose the value from a stored
      lookup's candidates, as policy.py accepts (taxon_chosen).
    - ``qualified`` (the native lineage proof) is the derived values: their
      lineage is their derivation, and they have no literal by definition (G37).
    - 232-236: a field on the profile's "not on the label" list (``allowed``,
      not_on_label_keys) that research marked so (not_on_label) is not
      mandatory_unresolved (owner decision A, 2026-10-09).
    - 254-260: a taxon that names no genus, cleared as written and unmatched
      (taxon_unmatched), is not taxonomy_unresolved (owner decision B).
    """
    reasons: list[str] = []
    # 198-199
    if not run.coverage_confirmed or not run.regions:
        reasons.append("label_coverage_unconfirmed")
    # 200-202
    for label in run.label_language_handling.get("labels", []):
        if label.get("review_required") and not run.human_approved:
            reasons.extend(f"{reason}:{label['region_id']}" for reason in label["reasons"])
    # 203-217
    for region in run.regions:
        readings = [item for item in run.observations if item.region_id == region.id]
        if len({item.route_id for item in readings}) < 2 or len({item.model_id for item in readings}) < 2:
            reasons.append(f"independent_observations_missing:{region.id}")
        if any(not item.raw_ref or not item.raw_sha256 for item in readings):
            reasons.append(f"raw_provenance_missing:{region.id}")
        transcripts = [item for item in run.transcripts if item.region_id == region.id]
        if not transcripts or any(not item.resolved or not item.text for item in transcripts):
            ids = {reading.id for reading in readings}
            drawn = [key for key, value in run.fields.items() if key != IRN and (
                value.source_region_id == region.id or any(identifier in ids for identifier in value.verbatim_by_observation)
                or any(item.id in value.evidence_ids and item.region_id == region.id for item in run.evidence))]
            if not drawn or any(run.fields[key].state != ValueState.SUPPORTED
                    or not _raw_grounded(run.fields[key], run) and key not in qualified
                    for key in drawn if latest_work.get(key) in TERMINAL):
                reasons.append(f"unresolved_transcription:{region.id}")
    evidence = {item.id: item for item in run.evidence}
    # 219-220: an identity collision is an integrity failure, never a review reason.
    if len(evidence) != len(run.evidence):
        raise EvidenceIntegrityError("evidence_integrity_failure")
    mandatory = frozenset(mandatory)
    for key in sorted(latest_work):
        if latest_work[key] not in TERMINAL:
            continue
        value = run.fields.get(key) or FieldValue()
        # 227-231
        if (key in NO_APPROVED_AUTHORITY and value.state != ValueState.SUPPORTED
                and not any((value.parsed, value.normalized, value.authority_id, value.authority_identity))):
            continue
        if key not in mandatory and value.state != ValueState.SUPPORTED:
            continue
        # Owner decision A: a listed field no reading states, with its check row.
        if not_on_label(key, value, run, evidence, allowed):
            continue
        # 232-236
        settled = value.normalized or value.parsed or value.literal
        if (value.state != ValueState.SUPPORTED or not settled
                or settled.strip().casefold() in PLACEHOLDERS
                or (value.literal is None and key not in qualified and not _raw_grounded(value, run))):
            reasons.append(f"mandatory_unresolved:{key}")
            continue
        # 237-239
        if not value.evidence_ids or any(item not in evidence for item in value.evidence_ids):
            reasons.append(f"evidence_missing:{key}")
            continue
        citations = [evidence[item] for item in value.evidence_ids]
        # 241-242
        if value.literal is not None and not any(value.literal in item.excerpt for item in citations):
            reasons.append(f"evidence_does_not_support_value:{key}")
        # 243-244
        if value.verbatim_by_observation and key not in qualified and not _raw_grounded(value, run):
            reasons.append(f"raw_reading_grounding_unproved:{key}")
        # 245-251
        for layer in ("parsed", "normalized", "authority_id"):
            text = getattr(value, layer)
            if key not in qualified and text and text != value.literal and not any(
                item.kind in {"authority", "authority_selection", "derived", "lookup"}
                and text in item.excerpt for item in citations
            ):
                reasons.append(f"unsupported_{layer}:{key}")
        # 252-253
        if key == IRN and (not value.authority_identity or value.authority_identity.get("module") != "eparties"):
            reasons.append("identified_by_irn_identity_unproved")
    # 254-260
    taxon = run.fields.get("taxon") or FieldValue()
    if latest_work.get("taxon") in TERMINAL and not (taxon_decided(taxon, run.tool_calls, evidence, run.lookups)
            or taxon_unmatched(taxon, evidence, run.lookups, texts=[r.text for r in run_readings(run)])):
        reasons.append("taxonomy_unresolved")
    # 261-271
    # An empty elevation is mandatory_unresolved above; only a value that is
    # no number is invalid, and the range needs both ends.
    for unit in ("m", "ft"):
        if any(latest_work.get(f"elevation_{end}_{unit}") not in TERMINAL for end in ("from", "to")):
            continue
        texts = [_text(run.fields.get(f"elevation_{end}_{unit}")) for end in ("from", "to")]
        try:
            values = [Decimal(text) for text in texts if text]
        except InvalidOperation:
            reasons.append(f"elevation_invalid:{unit}")
            continue
        if any(not v.is_finite() for v in values) or (len(values) == 2 and values[0] > values[1]):
            reasons.append(f"elevation_range:{unit}")
    # 272-281
    for end in ("from", "to"):
        if any(latest_work.get(f"elevation_{end}_{unit}") not in TERMINAL for unit in ("m", "ft")):
            continue
        try:
            metric, imperial = (run.fields[f"elevation_{end}_{unit}"] for unit in ("m", "ft"))
            metres, feet = (Decimal(v.normalized or v.parsed or v.literal or "") for v in (metric, imperial))
            if metres.is_finite() and feet.is_finite() and abs(metres * Decimal("3.28084") - feet) > Decimal("1"):
                reasons.append(f"elevation_units_conflict:{end}")
        except InvalidOperation:
            pass  # The mandatory/range checks above retain missing data.
    # 282-291
    # An empty date is mandatory_unresolved above: precision is reviewed only
    # for a date that has a value, and the order only between dates that do.
    dates = ("date_visited_from", "date_visited_to", "date_identified")
    if all(latest_work.get(key) in TERMINAL for key in dates):
        bounds = {}
        try:
            for key in dates:
                value = run.fields.get(key)
                if _text(value):
                    bounds[key] = _date_bounds(value)
        except (ValueError, OverflowError, OSError):
            reasons.append("date_precision_requires_review")
        else:
            start = bounds.get("date_visited_from", (None,))[0]
            end = bounds.get("date_visited_to", (None, None))[1]
            identified = bounds.get("date_identified", (None,))[0]
            if ((start and end and start > end) or (identified and start and identified < start)
                    or (identified and identified > today)):
                reasons.append("date_order")
    # 292-294
    identifier = run.fields.get("fmnh_ins_number") or FieldValue()
    if latest_work.get("fmnh_ins_number") in TERMINAL and not CATALOG.fullmatch(
            identifier.normalized or identifier.parsed or identifier.literal or ""):
        reasons.append("identifier_format")
    return list(dict.fromkeys(reasons))


def work_states(run, profile: CollectionProfile, outcomes: Sequence[FieldOutcome]) -> dict[str, str]:
    """Each profile field's work state after this attempt.

    A field this attempt did not research (settled earlier, or a person's) and
    a derived value are resolved; an outage or model failure is operational; a
    field with no approved authority is its nonblocking exception; anything
    else that did not settle waits on a person (a spent budget too: the
    ceiling is a scientific stop, not an outage).
    """
    by_key = {outcome.key: outcome for outcome in outcomes}
    states = {}
    for key in field_keys(profile):
        outcome, value = by_key.get(key), run.fields.get(key) or FieldValue()
        if outcome is None or (value.state == ValueState.SUPPORTED and value.layer == "derived"):
            states[key] = RESOLVED
        elif outcome.failure in RETRYABLE:
            states[key] = FAILED
        elif key in NO_APPROVED_AUTHORITY:
            states[key] = NONBLOCKING
        elif value.state == ValueState.SUPPORTED and value.layer in RESEARCHED:
            states[key] = RESOLVED
        else:
            states[key] = WAITING_HUMAN
    return states


def finalize_fields(run, profile: CollectionProfile | None, outcomes: Sequence[FieldOutcome], *,
        specimen=None, blobs=None, today: date | None = None) -> str | None:
    """Set the run's reasons, disposition and stage; the blocker when it is blocked.

    The retained evidence is verified first, as the workflow's finalize does
    (EvidenceIntegrityError propagates). All mandatory fields settled and the
    rules satisfied: cleared. Anything for a person: needs human review, with a
    reason per field. Any outage or model failure: processing_blocked with the
    retryable blocker the workflow schedules a retry on, every settled field kept.
    """
    profile = profile_of(run) if profile is None else profile
    if specimen is not None and blobs is not None:
        verify_evidence(specimen, blobs)
    today = datetime.now(timezone.utc).date() if today is None else today
    work = work_states(run, profile, outcomes)
    qualified = frozenset(key for key, value in run.fields.items()
        if value.state == ValueState.SUPPORTED and value.layer == "derived")
    human = scientific_reasons(run, work, mandatory=profile.mandatory_fields, qualified=qualified, today=today,
        allowed=not_on_label_keys(profile))
    # canonical_materialization_v2 447-450: a person's carried decision is
    # reviewed again, until a person approves the record (on the native path the
    # approval's ordinary finalize no longer names it).
    if not run.human_approved:
        human += [f"preserved_human_decision:{key}" for key in sorted(human_keys(run) & set(work))]
    by_key = {outcome.key: outcome for outcome in outcomes}
    failures = [by_key[key].failure for key in work if work[key] == FAILED]
    if failures:
        operational = [f"{RETRYABLE[by_key[key].failure][0]}:{key}" for key in work if work[key] == FAILED]
        blocker = next(code for failure, (code, _) in RETRYABLE.items() if failure in failures)
        run.stage, run.disposition, run.blocker = "processing_blocked", None, blocker
        run.reasons = list(dict.fromkeys((*operational, *human)))
        return blocker
    run.blocker = None
    run.reasons = list(dict.fromkeys(human))
    run.disposition = Disposition.REVIEW if run.reasons else Disposition.CLEARED
    run.stage = "finalized"
    return None


APPROVAL = "human_approval_required"


def refinalize(run, *, decided: bool = False, specimen=None, blobs=None, today: date | None = None) -> None:
    """The clearance rules again, on a run field research has completed.

    Nothing is researched or paid for and no field changes: a reviewer's value
    stays exactly as the reviewer made it, and finalize_fields' rules decide
    the record on the fields as they are. As on the native path, where every
    review decision ends in the ordinary finalize: a run with a blocker (the
    decision's integrity check) stays blocked with it, a person's decision
    (``decided``) waits for their approval until they give it, and an approval
    clears what the rules clear. A later pass keeps a pending approval.
    """
    if run.blocker:
        # policy.finalize: a blocked run is not decided.
        run.stage, run.disposition, run.reasons = "processing_blocked", None, [run.blocker]
        return
    pending = decided or APPROVAL in run.reasons
    finalize_fields(run, None, (), specimen=specimen, blobs=blobs, today=today)
    if pending and not run.human_approved:
        run.reasons = [*run.reasons, APPROVAL]
        run.disposition = Disposition.REVIEW


# ---- the workflow step ----------------------------------------------------

def record_cost(run, route_id: str, *, reserved: int, spent: int | None, outcome: str, model_calls: int = 0) -> None:
    """The step's one paid-call entry, in lane_costs' shape (LANE.md T2c).

    ``spent`` is the meter's settled spend; None when the spend is unknown,
    and then the whole reservation stays held (cost_basis "reserved").
    """
    prices = run.profile.execution.price_list
    if prices is None:
        return
    known = spent is not None
    run.paid_calls.append({
        "step": STEP,
        "attempt": run.attempts.get(STEP, 1),
        "kind": "model",
        "route_id": route_id,
        "reserved_micros": reserved,
        "usage": {"model_calls": model_calls} if known else None,
        "outcome": outcome,
        "cost_micros": spent if known else reserved,
        "cost_basis": "computed" if known else "reserved",
        "price_list": {"version": prices["version"], "as_of": prices["as_of"]},
        "at": now(),
    })
    if any(call["cost_basis"] == "reserved" for call in run.paid_calls):
        run.usage.actual_cost_micros = None
    elif known:
        run.usage.actual_cost_micros = (run.usage.actual_cost_micros or 0) + spent


def _route_price(profile: CollectionProfile, route_id: str | None):
    prices = profile.processing.price_list if profile.processing else None
    if route_id is None or prices is None or route_id not in prices.models:
        raise OperationalBlock("field_research_price_unavailable")
    return prices.models[route_id]


def cost_meter(cap_micros: int, price):
    from .budget import CostMeter

    return CostMeter(cap_micros, input_micros_per_million=price.input_micros_per_million,
        output_micros_per_million=price.output_micros_per_million)


def one_request_micros(price) -> int:
    """The worst case of one expert request at the route's price: the meter's
    input bound and its chat template, and the output cap (budget.MeteredModel)."""
    from .budget import DEFAULT_MAX_INPUT_TOKENS, DEFAULT_MAX_TOKENS, TEMPLATE_TOKENS

    return cost_meter(0, price).cost(DEFAULT_MAX_INPUT_TOKENS + TEMPLATE_TOKENS, DEFAULT_MAX_TOKENS)


# The step's work after research (closing the sources, applying the outcomes,
# the integrity check, the clearance rules), measured by
# test_field_research_e2e.test_the_work_after_research_fits_well_inside_the_margin
# on 2026-10-08: a slide-sized record (1,780 x 590 px image, 63 evidence rows,
# 42 source calls) with a 50 ms Cloud Storage round trip on every blob read and
# write took 4.3 s, 4.0 s of it the integrity check's 73 reads. Research stops
# max(60 s, three times that) before the step's deadline.
POST_RESEARCH_SECONDS = 4.3
MARGIN_SECONDS = max(60.0, 3 * POST_RESEARCH_SECONDS)


@dataclass
class FieldResearchStep:
    """The workflow's ``field_research`` step for one run, in memory.

    ``resolver_factory(run, profile, meter)`` returns the run's FieldResolver,
    ``tools_factory(run, profile, blobs)`` an async context manager that yields
    its SourceTools, and ``meter_factory(cap_micros, price)`` the meter every
    expert's model call reserves from (budget.CostMeter).
    """

    resolver_factory: Callable
    tools_factory: Callable
    meter_factory: Callable = cost_meter
    # Every field's expert at once (FIELD_RESEARCH.md, step 3).
    concurrency: int = len(FIELD_TOOLS)
    # Research stops this long before the step's own deadline: unfinished
    # fields become timeouts, settled ones are kept, and the step applies them
    # and the workflow saves them inside its effect timeout.
    margin_seconds: float = MARGIN_SECONDS

    def handles(self, run) -> bool:
        from specimen_digitization.research_harness.committed_pins import (
            committed_harness_route,
        )

        return committed_harness_route(run.profile_snapshot) is not None

    def reservation(self, workflow, principal, specimen, headroom: int) -> int:
        """What the step reserves: the run's headroom under its ceiling, or what
        the program's allowance has left when that is less (its ledger is read
        here, never written; lane_allowance.reserve_step reserves). A program
        allowance with less left than one expert request keeps the headroom, so
        reserve_step blocks the record as it always has; otherwise the meter's
        cap is what is left, and a field that does not fit goes to review."""
        from specimen_digitization.application.domain import Scope
        from specimen_digitization.application.lane_allowance import (
            LegacyLedgerUnavailable,
            ProgramLedger,
        )

        policy = specimen.run.profile.execution
        if headroom <= 0 or policy.program_allowance_micros is None:
            return headroom
        try:
            profile = profile_of(specimen.run)
            price = _route_price(profile, profile.harness_route)
            ledger = ProgramLedger(workflow.repository, Scope(organization_id=principal.scope.organization_id,
                collection_id=policy.program_ledger_collection), clock=workflow.clock)
            reserved = ledger.read()["reserved_total_micros"]
        except (OperationalBlock, LegacyLedgerUnavailable, ValueError, TypeError, KeyError):
            # The step and reserve_step report these with their own codes.
            return headroom
        left = max(0, policy.program_allowance_micros - reserved)
        return headroom if left < one_request_micros(price) else min(headroom, left)

    def recheck(self, workflow, principal, specimen) -> None:
        """A run field research has completed reaches the handover again (a
        retry or resume, or a correction saved before the API knew field
        research): the clearance rules again, nothing researched or paid
        (refinalize)."""
        try:
            refinalize(specimen.run, specimen=specimen, blobs=workflow.blobs, today=workflow.clock().date())
        except EvidenceIntegrityError as error:
            raise OperationalBlock(str(error)) from error

    def run(self, workflow, principal, specimen, *, cap_micros: int, deadline_seconds: float) -> None:
        run = specimen.run
        route = None
        try:
            # Nothing is sent before the research below: an error here is the
            # step's setup, never an unknown outcome, and costs nothing.
            profile = profile_of(run)
            route = profile.harness_route
            meter = self.meter_factory(max(0, cap_micros), _route_price(profile, route))
            prepared = build_tasks(run, profile)
            resolver = self.resolver_factory(run, profile, meter)
        except OperationalBlock:
            record_cost(run, route, reserved=cap_micros, spent=0, outcome="failed")
            raise
        except Exception as error:
            record_cost(run, route, reserved=cap_micros, spent=0, outcome="failed")
            raise OperationalBlock("field_research_unconfigured") from error
        calls: list[SourceCall] = []
        outcomes = None
        try:
            outcomes = asyncio.run(self._research(run, profile, prepared, resolver, workflow.blobs,
                calls, self._bound(deadline_seconds)))
        finally:
            # Research cut short by an error still settles to what the meter
            # spent: once asyncio.run returns no request is in flight, and each
            # one that ended early kept its worst case (MeteredModel). Only a
            # reservation still outstanding leaves the spend unknown.
            known = outcomes is not None or meter.outstanding_micros == 0
            record_cost(run, route, reserved=cap_micros,
                spent=meter.spent_micros if known else None,
                outcome="completed" if outcomes is not None else "failed" if known else "unknown",
                model_calls=sum(o.model_calls for o in outcomes or ()))
        try:
            apply_outcomes(run, profile, prepared[1], outcomes, blobs=workflow.blobs, calls=calls,
                asset_id=specimen.asset.id)
            blocker = finalize_fields(run, profile, outcomes, specimen=specimen, blobs=workflow.blobs,
                today=workflow.clock().date())
        except EvidenceIntegrityError as error:
            raise OperationalBlock(str(error)) from error
        if blocker is not None:
            if run.paid_calls and run.paid_calls[-1]["step"] == STEP:
                run.paid_calls[-1]["outcome"] = "failed"
            raise AdapterFailure(blocker, BLOCKER_STATUS[blocker])

    def _bound(self, deadline_seconds: float) -> float:
        from specimen_digitization.application.worker_deadline import current_deadline

        bound = deadline_seconds - self.margin_seconds
        deadline = current_deadline()
        if deadline is not None:
            bound = min(bound, deadline.remaining() - self.margin_seconds)
        return max(1.0, bound)

    async def _research(self, run, profile, prepared, resolver, blobs, calls, bound):
        async with self.tools_factory(run, profile, blobs) as tools:
            return await research_fields(run, profile, resolver=resolver, tools=tools,
                concurrency=self.concurrency, deadline_seconds=bound, prepared=prepared, calls=calls)


def _production_resolver(run, profile, meter):
    """The harness route's model through the Hugging Face gateway, as the
    ordinary extraction call builds its model (production.py _extract_direct)."""
    if os.getenv("SPECIMEN_APPROVED_INFERENCE") != "true":
        raise OperationalBlock("provider_data_policy_and_spending_approval_required")
    from specimen_digitization.model_gateway import HuggingFaceModelGateway
    from specimen_digitization.provider_privacy import PrivateProviderModel

    from .experts import make_resolver

    gateway = HuggingFaceModelGateway(timeout_seconds=MODEL_TIMEOUT_SECONDS)
    route = profile.harness_route
    gateway.route(route)  # An unknown route fails here, before any request.
    return make_resolver(model_factory=lambda: PrivateProviderModel(gateway.model_for(route)),
        meter=meter, date_rules=profile.date_rules)


@asynccontextmanager
async def _production_tools(run, profile, blobs):
    """The record's approved sources over one HTTP client. A taxon request never
    carries the record's place text (verify_taxon; workflow's lookup step)."""
    import httpx

    from .sources import ApprovedSources

    places = [run.fields[key].literal for key in PLACE_FIELDS if key in run.fields and run.fields[key].literal]
    async with httpx.AsyncClient() as client:
        sources = ApprovedSources(blobs=blobs, client=client, place_text=places)
        try:
            yield sources
        finally:
            sources.close()  # A GBIF verification still running ends now.


def production_step() -> FieldResearchStep:
    return FieldResearchStep(resolver_factory=_production_resolver, tools_factory=_production_tools)
