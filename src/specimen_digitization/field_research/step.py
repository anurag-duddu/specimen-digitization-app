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
   may call. A field is resolved to one of its candidates' literals, or to text
   its expert read in the readings (agreement.literal_basis).
2. ``research_fields``: every field's expert runs, all at once, inside one
   ``field_research`` span, whatever the organiser's value (it may confirm
   it); only the identified-by IRN, which no approved source supplies, gets
   none. After step 4, each field's decision is its own
   ``field_research.field`` span inside it (``trace_fields``).
3. ``apply_outcomes``: the outcomes become field values and evidence on the
   run, then the derived values (derive.py; G37, G41, G44), then the listed
   fields no reading states are marked "not on the label" (owner decision A;
   ``mark_not_on_label``). A taxon with no genus clears as written, unmatched
   (owner decision B; ``_unmatched_taxon``).
4. ``finalize_fields``: the scientific rules the six-specialist harness applied
   (research_harness/canonical_materialization_v2.py, ``_scientific_reasons``)
   with no blanket human approval (G1). A field that cannot be settled sends the
   record to Needs human review; an outage blocks the run with a retry, and
   every settled field is kept for it. On the step's last attempt a source
   still unreachable, or a field that ran out of time, sends its field to
   review instead (``last_attempt``).

Once the step has completed on a run, reviewer decisions and approvals do not
run it again: they apply the rules only (``refinalize``), on the fields exactly
as they are. An explicit operator retry of a completed run that is still in
review for unsettled automatic fields may re-enter the step on those unresolved
fields.
"""

from __future__ import annotations

import asyncio
import copy
import calendar
import hashlib
import json
import logging
import os
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import asynccontextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass, replace
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
from specimen_digitization.application.first_pass import given_up_regions
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
# The step's Logfire span, and one span per field inside it (trace_fields).
SPAN = "field_research"
FIELD_SPAN = "field_research.field"
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
# The failures that, on the step's last attempt (last_attempt), send their
# field to review instead of blocking: no retry follows that attempt. A
# timeout is the field's own deadline, the step's, or a model request that
# ran out of time (experts.timed_out). A model error (any other provider
# failure, or a defect) blocks on every attempt; a provider's outage is for
# a later retry, never a finalized record.
REVIEW_ON_LAST_ATTEMPT = frozenset({"source_unavailable", "timeout"})
# Field research given up on unsent (FieldResearchStep.give_up): one warning
# finding per run, "field_research_given_up:<the limit's code>".
GIVEN_UP = "field_research_given_up"
GIVEN_UP_RULES = "field-research-given-up-2026-10-12"
FIELD_REASONS = {
    "source_unavailable": "An approved source could not be reached. The record will be retried.",
    "model_error": "An error occurred while researching this field. The record will be retried.",
    "timeout": "Research on this field ran out of time. The record will be retried.",
    "budget_exhausted": "The run's cost limit was reached before this field could be checked.",
    "input_too_large": "The readings and sources for this field were too long to send for checking.",
    "run_limit": "The run reached one of its processing limits before this field could be checked.",
    None: "No answer was produced for this field.",
}
# The model gateway's own bound on one provider request, under the expert's
# 150 s deadline. A request it stops is the field's timeout, not a model
# error (experts.ClientTimeouts, experts.timed_out).
MODEL_TIMEOUT_SECONDS = 120


def last_attempt(run) -> bool:
    """Whether this is the step's last allowed attempt. The workflow counts an
    attempt (run.attempts[STEP]) before the step runs, and schedule_retry
    retries only while that count is below the run's max_attempts."""
    return run.attempts.get(STEP, 0) >= run.profile.execution.max_attempts


def _attempts(run) -> str:
    """The step's attempts so far, in words: "3 attempts"."""
    attempts = run.attempts.get(STEP, 0)
    return f"{attempts} attempt{'s' if attempts != 1 else ''}"


def _unreachable_reason(run, outcome: FieldOutcome) -> str:
    """The reason of a field whose sources still could not be reached on the
    step's last attempt: it goes to review, naming them."""
    names = _source_names(outcome.unreachable) if outcome.unreachable else "An approved source"
    return f"{names} could not be reached after {_attempts(run)}."


def _timeout_reason(run) -> str:
    """The reason of a field that ran out of time on the step's last attempt:
    it goes to review."""
    return f"Research on this field ran out of time after {_attempts(run)}."


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
    from .location_reassessment import KEY as REASSESSMENT, active_keys, working_run

    selected = active_keys(run)
    if REASSESSMENT in run.dependencies and not selected:
        raise OperationalBlock("location_reassessment_unavailable")
    run = working_run(run)
    profile = profile_of(run) if profile is None else profile
    readings = run_readings(run)
    candidates = _candidates(run, readings)
    human = human_keys(run)
    tasks = []
    for key in field_keys(profile):
        if selected and key not in selected:
            continue
        current = run.fields.get(key) or FieldValue()
        if key in human or (current.state == ValueState.SUPPORTED and current.layer in RESEARCHED):
            continue
        tasks.append(FieldTask(key=key, mandatory=key in profile.mandatory_fields,
            current=current.model_copy(deep=True), candidates=tuple(candidates.get(key, ())),
            tools=tuple(FIELD_TOOLS.get(key, ()))))
    context = {key: value.model_copy(deep=True) for key, value in run.fields.items()}
    return readings, tuple(tasks), context


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
        prepared=None, calls: list[SourceCall] | None = None, span=None) -> list[FieldOutcome]:
    """One outcome per task, in task order.

    Every field's resolver runs, up to ``concurrency`` at once, whatever the
    organiser's value (its expert may confirm it, or find it is not this
    field's text). A field with no approved authority (identified_by_irn)
    gets no model call and keeps its nonblocking exception. A field still
    running at ``deadline_seconds`` is cancelled as a timeout.
    ``prepared`` is build_tasks' result; ``calls`` collects every lookup made.
    Its counts go on ``span``, the step's ``field_research`` span, or on a
    span of that name of its own when none is given.
    """
    profile = profile_of(run) if profile is None else profile
    readings, tasks, context = build_tasks(run, profile) if prepared is None else prepared
    recorded = _RecordedTools(tools, [] if calls is None else calls)
    outcomes: dict[str, FieldOutcome] = {}
    pending: list[FieldTask] = []
    for task in tasks:
        if task.key in NO_APPROVED_AUTHORITY:
            outcomes[task.key] = FieldOutcome(task.key, FieldAnswer(outcome="sources_cannot_resolve",
                explanation=IRN_EXPLANATION), finalized_without_model=True)
        else:
            pending.append(task)
    with (logfire.span(SPAN) if span is None else nullcontext(span)) as span:
        span.set_attribute("fields_total", len(tasks))
        span.set_attribute("fields_researched", len(pending))
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

def _excerpt_span(text: str, literal: str, start: int | None = None) -> tuple[int, int, int, int]:
    """The literal's first occurrence (or the one at `start`) and the line(s) around it."""
    start = text.index(literal) if start is None else start
    end = start + len(literal)
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    return line_start, len(text) if line_end < 0 else line_end, start, end


def _literal_row(key: str, reading: Reading, literal: str, asset_id, blobs, *, transcript: bool = False) -> Evidence:
    """A label row for a reading the expert named that no organiser row covers.
    For a literal the expert read in the transcript itself, not an organiser
    candidate (agreement.TRANSCRIPT), the row cites its first run of whole
    words (agreement.verbatim_runs), and its record says so ("basis":
    "transcript")."""
    from .agreement import verbatim_runs

    runs = verbatim_runs(reading.text, literal) if transcript else []
    quote_start, quote_end, start, end = _excerpt_span(reading.text, literal, runs[0][0] if runs else None)
    excerpt = reading.text[quote_start:quote_end]
    record = json.dumps({"field_key": key, "reading": reading.name, "region_id": reading.region_id,
        "observation_ids": [reading.observation_id], "excerpt": excerpt,
        **({"basis": "transcript"} if transcript else {})}, sort_keys=True).encode()
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
        "date_parser": lambda: checks.parse_date(literal, reading_texts=texts, date_rules=date_rules,
            part=checks.DATE_PART.get(key), field=key),
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


def _misfit(run, task, answer, *, sources, readings, by_name, places, pending, received=None):
    """Why a place value the agreement rules accept does not fit the label's
    other place fields (agreement.parents_refusal), or None. It is checked
    here, once every outcome is in: field research runs its fields at once,
    and the country must be known. For each reading the answer names (the
    label's decided reading, on a label with one), the other place fields are
    those that reading writes (`places`), and one of them is settled for the
    reading when its value is supported, this attempt has done with it (it is
    not `pending`) and the reading writes its literal, compared as place
    names; a settled country carries the ISO code of the record it settled
    on (_record_code, from the answers the country field received,
    `received`), and no other field carries one. One the reading writes is
    unsettled when its field has no supported value with a literal, or this
    attempt has not done with it (a county needs its province settled). A place settled on
    text its expert read in the transcript (transcript_code) is written by
    each reading that writes that text as whole words
    (agreement.verbatim_runs)."""
    from .agreement import (
        PLACE_ORDER,
        PLACE_VALUE_FIELDS,
        PlaceField,
        parents_refusal,
        place_name,
        verbatim_runs,
    )

    if task.key not in PLACE_VALUE_FIELDS:
        return None
    found = _settling(task, answer, sources)
    if found is None:
        return None  # _refusal has refused it already.
    basis, candidate = found.basis, found.candidate
    named = [by_name[n] for n in dict.fromkeys(answer.reading_names) if n in by_name and answer.literal in by_name[n].text]
    decided = {r.region_id: r for r in readings if r.input_source == "decided_transcript"}
    rows = {item.id: item for item in run.evidence}
    codes = {finding.reason_code for finding in run.findings}
    for reading in dict.fromkeys(decided.get(r.region_id, r) for r in named):
        written, settled, unsettled = {}, {}, set()
        for key in PLACE_ORDER:
            texts = places[key].get(reading.name, frozenset())
            value = run.fields.get(key)
            if (key != task.key and key not in pending and value is not None
                    and value.state == ValueState.SUPPORTED and value.layer == "derived"):
                names = (*(text for text in (value.literal, value.normalized, value.parsed) if text),
                    *_expansions(key, value, rows))
                code = _record_code(value, (received or {}).get(key, ())) if key == "country" else None
                if names or value.authority_id or code:
                    settled[key] = PlaceField(tuple(dict.fromkeys(names)), value.authority_id, code)
                    continue
            if (transcript_code(key) in codes and key not in pending and value is not None
                    and value.state == ValueState.SUPPORTED and value.literal
                    and verbatim_runs(reading.text, value.literal)):
                texts = texts | {value.literal}
            if key == task.key or not texts:
                continue
            if (key not in pending and value is not None and value.state == ValueState.SUPPORTED and value.literal
                    and place_name(value.literal) in {place_name(text) for text in texts}):
                # Earlier organiser candidates can belong to a different level
                # after reconciliation. Only the settled value's own names are
                # aliases of this place; the old candidates stay in evidence.
                names = (value.literal, *(text for text in (value.normalized, value.parsed) if text),
                    *_expansions(key, value, rows))
                code = _record_code(value, (received or {}).get(key, ())) if key == "country" else None
                written[key] = settled[key] = PlaceField(tuple(dict.fromkeys(names)), value.authority_id, code)
            else:
                written[key] = PlaceField(tuple(sorted(texts)))
                if key in pending or value is None or value.state != ValueState.SUPPORTED or not value.literal:
                    unsettled.add(key)
        refused = parents_refusal(task.key, candidate, basis, written=written, settled=settled,
            literal=answer.literal, unsettled=frozenset(unsettled))
        if refused is not None:
            return refused
    return None


def _record_code(value: FieldValue, answers: Iterable[SourceAnswer]) -> str | None:
    """The ISO 3166-1 alpha-2 code the record a settled country settled on
    carries (SourceCandidate.iso_code), which agreement.lies_in compares
    with a parent its source names only by a country code: the one code of
    the candidates with the value's authority_id in the stored answers the
    country field received in this attempt (`answers`). The country settles
    only on a record at a nation's level (agreement.placed), so that record
    is a nation's. None when they carry none or several, and for a value
    with no authority_id or no such answer (one settled in an earlier
    attempt or by a person)."""
    codes = {candidate.iso_code for answer in answers if answer.evidence is not None
        for candidate in answer.candidates
        if value.authority_id and candidate.authority_id == value.authority_id and candidate.iso_code}
    return codes.pop() if len(codes) == 1 else None


def _settling(task, answer, sources):
    """How the answer's cited place answers settle its place value
    (agreement.place_settling), or None. ``sources`` are the source answers
    the field received."""
    from .agreement import place_settling

    by_id = {item.evidence.id: item for item in sources if item.evidence is not None}
    cited = [by_id[i] for i in dict.fromkeys(answer.source_evidence_ids) if i in by_id]
    settled = answer.value if answer.value is not None else answer.literal
    return place_settling(task, answer.literal, settled, answer.authority_id, cited)


# A literal read from the transcript that is also another kind of field's text.
TAKEN = "This text, read from the transcript, is also the value found for {other}."


def _inside_a_token(text: str, index: int) -> bool:
    """Whether `index` falls between two letters or between two digits of the
    text: inside a word's letters ("trap" of "trapping") or a number's digits
    ("2" of "24")."""
    if not 0 < index < len(text):
        return False
    before, after = text[index - 1], text[index]
    return (before.isalpha() and after.isalpha()) or (before.isdigit() and after.isdigit())


def _occurrences(literal: str, readings: Iterable[Reading]) -> frozenset[tuple[str, int, int]]:
    """Where the readings write the literal as whole tokens: (reading, start,
    end), each time it neither starts nor ends inside a word's letters or a
    number's digits (_inside_a_token). A settled "2" claims the "2" of "lot
    #2", never the "2" of "IV-24-48" (PR #300's review, finding 2)."""
    found = set()
    for reading in readings:
        start = reading.text.find(literal)
        while start >= 0:
            end = start + len(literal)
            if not (_inside_a_token(reading.text, start) or _inside_a_token(reading.text, end)):
                found.add((reading.name, start, end))
            start = reading.text.find(literal, start + 1)
    return frozenset(found)


def _candidate_spans(reading: Reading, candidate: Candidate) -> frozenset[tuple[str, int, int]]:
    """Where an organiser candidate's literal stands in its reading: inside
    each place its quote does, else wherever the reading writes it as whole
    tokens (_occurrences)."""
    text, found = reading.text, set()
    at = text.find(candidate.quote) if candidate.quote else -1
    while at >= 0:
        inner = candidate.quote.find(candidate.literal)
        while inner >= 0:
            found.add((reading.name, at + inner, at + inner + len(candidate.literal)))
            inner = candidate.quote.find(candidate.literal, inner + 1)
        at = text.find(candidate.quote, at + 1)
    return frozenset(found) or _occurrences(candidate.literal, [reading])


def _overlap(spans, others) -> bool:
    return any(name == other and start < other_end and other_start < end
        for name, start, end in spans for other, other_start, other_end in others)


# The layers of a value settled from the label: its text as written (G38's
# verbatim layer) or settled by its sources and checks. A derived value is
# computed, never read on the label, and the organiser's and the keyed-line
# parser's values have no layer.
SETTLED_LAYERS = frozenset({"verbatim", "settled"})


def _claims_text(key: str, value: FieldValue, human: frozenset[str]) -> bool:
    """Whether a stored value is settled, so its literal claims its text
    (_taken; rule A's organiser texts, mark_not_on_label): supported, with a
    literal, in a settled layer (SETTLED_LAYERS), or a person's decision that
    is not derived. An organiser's value, a value research did not settle and
    a derived value never claim text."""
    return (value.state == ValueState.SUPPORTED and bool(value.literal and value.literal.strip())
        and (value.layer in SETTLED_LAYERS or (key in human and value.layer != "derived")))


def _value_spans(value: FieldValue, readings: Sequence[Reading], evidence: Mapping[str, Evidence]):
    """Where a stored value's literal stands as whole tokens (_occurrences) in
    the readings of its labels: its source region, the regions of its label
    rows, and those of the readings it keeps a verbatim of or was settled by."""
    observed = {*value.verbatim_by_observation, *value.settled_observation_ids}
    regions = ({value.source_region_id} - {None}) | {evidence[i].region_id for i in value.evidence_ids
        if i in evidence and evidence[i].kind == "literal"} | {r.region_id for r in readings
        if r.observation_id in observed}
    return _occurrences(value.literal, [r for r in readings if r.region_id in regions])


def _taken(run, tasks_by_key: Mapping[str, FieldTask], outcomes: Sequence[FieldOutcome],
        readings: Sequence[Reading], settled: Mapping[str, FieldValue]) -> dict[str, str]:
    """The fields whose resolved answer gives a literal its expert read in the
    transcript (agreement.literal_basis: TRANSCRIPT) when that same text is
    claimed for a field of another kind (agreement.may_share_text), each
    with that other field. The text is the literal's runs of whole words
    (agreement.verbatim_runs) in the readings of the labels its answer
    names. Only a settled value claims text, where it overlaps that text in
    the same reading: another field's value this attempt's answers settle
    (`settled`: _first_pass, before this guard), wherever its literal stands
    as whole tokens (_occurrences) in the readings of the labels its answer
    names; or another field's value settled before this attempt or by a
    person (_claims_text), so, in the readings of its labels
    (_value_spans). An organiser candidate, an answer that settles nothing
    (refused, unsettled or failed) and a value no one settled never claim
    text (round 2 of the production test: the organiser's habitat "trap",
    whose expert found no habitat, held 105526328's collecting method
    "trap"). Which field such text belongs to is for a person: the field
    goes to review. A place inside the precise location, or an elevation
    copied to the other unit, is one kind; an elevation or a date inside
    the precise location is not. Two fields that both settle the same text
    from the transcript both go to review."""
    from .agreement import TRANSCRIPT, literal_basis, may_share_text, verbatim_runs

    evidence = {item.id: item for item in run.evidence}
    by_name = {reading.name: reading for reading in readings}
    researched = {outcome.key for outcome in outcomes}
    human = human_keys(run)
    claims: list[tuple[str, frozenset]] = []
    mine: dict[str, frozenset] = {}
    for outcome in outcomes:
        answer = outcome.answer
        if outcome.failure is not None or answer is None:
            continue
        value = settled.get(outcome.key)
        if value is not None and value.literal:
            named = [by_name[n] for n in dict.fromkeys(answer.reading_names)
                if n in by_name and value.literal in by_name[n].text]
            regions = {r.region_id for r in named} or {r.region_id for r in readings if value.literal in r.text}
            claims.append((outcome.key, _occurrences(value.literal, [r for r in readings if r.region_id in regions])))
        literal = answer.literal
        if answer.outcome != "resolved" or not literal or not literal.strip():
            continue
        named = [by_name[n] for n in dict.fromkeys(answer.reading_names) if n in by_name and literal in by_name[n].text]
        task = tasks_by_key.get(outcome.key)
        if task is not None and named and literal_basis(task, readings, literal, named) == TRANSCRIPT:
            regions = {r.region_id for r in named}
            mine[outcome.key] = frozenset((r.name, start, end) for r in readings if r.region_id in regions
                for start, end in verbatim_runs(r.text, literal))
    for key, value in run.fields.items():
        if key not in researched and _claims_text(key, value, human):
            claims.append((key, _value_spans(value, readings, evidence)))
    taken = {}
    for key, spans in mine.items():
        other = next((other for other, theirs in claims
            if other != key and not may_share_text(key, other) and _overlap(spans, theirs)), None)
        if other is not None:
            taken[key] = other
    return taken


def _taken_value(task, outcome, other: str, evidence) -> FieldValue:
    """A field whose text from the transcript another kind of field claims
    (_taken): unresolved, for a person, with the reason naming that field."""
    from .prompts import FIELD_LABELS

    answer = outcome.answer
    cited = [e for e in answer.source_evidence_ids if e in evidence and evidence[e].kind != "literal"]
    return _unsettled(task, ValueState.UNRESOLVED, literal=task.current.literal, cited=cited,
        reason=f"{TAKEN.format(other=FIELD_LABELS.get(other, other))} {answer.explanation}")


NEAR_SPELLING_RULES = "field-research-places-v1"
# The locator of a settled place value's abbreviation row: the field, then
# the expansion its source was asked (_place_basis).
ABBREVIATION_LOCATOR = "abbreviation:{key}:{expansion}"


def _expansions(key: str, value: FieldValue, rows: Mapping[str, Evidence]) -> list[str]:
    """The expansions a settled place value settled through: those its
    abbreviation rows name (_place_basis), which a parent may name it by
    (agreement.lies_in)."""
    prefix = ABBREVIATION_LOCATOR.format(key=key, expansion="")
    return [row.locator.removeprefix(prefix) for row in (rows.get(i) for i in value.evidence_ids)
        if row is not None and row.kind == "rule" and row.locator and row.locator.startswith(prefix)]


def _place_basis(run, task, answer, sources, value: FieldValue) -> None:
    """What a settled place value's basis adds (agreement.place_settling): for
    a lookup of an expansion the literal abbreviates (the letter rule,
    abbreviations.fit), one rule row naming the abbreviation, the expansion
    and how its letters fit, cited by the value as support (no stored record,
    so it is never projected); for a lookup of the candidate's own name one
    letter from the label's text, which settled only on G34's whole condition
    (_misfit), a warning finding beside the record, naming the deciding
    answers, which never routes it (RunFinding). The value keeps the label's
    spelling as its literal (G27)."""
    from .abbreviations import fit, shown
    from .agreement import ABBREVIATION, NEAR_SPELLING, PLACE_VALUE_FIELDS, asked_name

    if task.key not in PLACE_VALUE_FIELDS:
        return
    by_id = {item.evidence.id: item for item in sources if item.evidence is not None}
    cited = [by_id[i] for i in dict.fromkeys(answer.source_evidence_ids) if i in by_id]
    found = _settling(task, answer, sources)
    basis = found.basis if found is not None else None
    if basis == ABBREVIATION:
        expansion = asked_name(found.answer)
        pairs = fit(answer.literal, expansion)
        row = Evidence(kind="rule", source=SOURCE,
            locator=ABBREVIATION_LOCATOR.format(key=task.key, expansion=expansion),
            excerpt=(f'{task.key}: "{answer.literal}" abbreviates "{expansion}", the name '
                f'{found.answer.source_id} was asked: its letters fit the words in order '
                f'({shown(pairs)}; field_research.abbreviations)'))
        run.evidence.append(row)
        value.evidence_ids.append(row.id)
        value.evidence_relations[row.id] = "supports"
    elif basis == NEAR_SPELLING:
        code = f"near_spelling:{task.key}"
        if not any(f.reason_code == code for f in run.findings):
            run.findings.append(RunFinding(rule_id="near_spelling", rule_version=NEAR_SPELLING_RULES,
                severity="warning", field_key=task.key, reason_code=code,
                evidence_ids=[item.evidence.id for item in cited]))


TRANSCRIPT_RULES = "field-research-transcript-v1"
# Set while _first_pass applies the answers to a copy of the run: no Logfire
# event is made for a value that pass settles (_from_the_transcript).
_FIRST_PASS: ContextVar[bool] = ContextVar("field_research_first_pass", default=False)


def transcript_code(key: str) -> str:
    """The reason code of a value whose literal its expert read in the
    transcript itself, not an organiser candidate."""
    return f"transcript_literal:{key}"


def _from_the_transcript(run, key: str, named: Sequence[Reading], rows: Sequence[str]) -> None:
    """Mark a value whose literal its expert read in the transcript itself
    (agreement.TRANSCRIPT): an info finding beside the record,
    `transcript_literal:<field>`, citing the label rows of the readings it
    names (a RunFinding never routes the record), and one Logfire event that
    names the field and those readings, never their text."""
    code = transcript_code(key)
    if not any(f.reason_code == code for f in run.findings):
        run.findings.append(RunFinding(rule_id="transcript_literal", rule_version=TRANSCRIPT_RULES,
            severity="info", field_key=key, reason_code=code, evidence_ids=list(rows)))
    if not _FIRST_PASS.get():
        logfire.info("field_research literal read from the transcript: {field_key}", field_key=key,
            reading_names=[reading.name for reading in named], literal_basis="transcript")


def _settled(run, task, outcome, *, by_name, evidence, asset_id, blobs, date_rules=None) -> FieldValue | None:
    """A resolved answer as a supported value, or None when its literal is not in
    the readings it names (the experts' check, repeated here). A literal the
    expert read in the transcript itself (agreement.TRANSCRIPT) is marked so
    (_from_the_transcript)."""
    from .agreement import TRANSCRIPT, literal_basis
    from .checks import collapse

    answer = outcome.answer
    literal = answer.literal
    if not literal or not literal.strip():
        return None
    named = [by_name[n] for n in dict.fromkeys(answer.reading_names) if n in by_name and literal in by_name[n].text]
    if not named:
        return None
    transcript = literal_basis(task, tuple(by_name.values()), literal, named) == TRANSCRIPT
    relations: dict[str, str] = {}
    for reading in named:
        own = [e for e in task.current.evidence_ids if e in evidence and evidence[e].kind == "literal"
            and evidence[e].region_id == reading.region_id
            and reading.observation_id in evidence[e].observation_ids and literal in evidence[e].excerpt]
        if not own:
            row = _literal_row(task.key, reading, literal, asset_id, blobs, transcript=transcript)
            run.evidence.append(row)
            evidence[row.id] = row
            own = [row.id]
        relations.update(dict.fromkeys((e for e in own if e not in relations), "supports"))
    if transcript:
        _from_the_transcript(run, task.key, named, list(relations))
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
    # A field no source or check supplies is the label's text as written (G38's
    # verbatim layer); any other is settled by its sources and checks.
    return FieldValue(state=ValueState.SUPPORTED, literal=literal, parsed=parsed, normalized=normalized,
        authority_id=answer.authority_id, evidence_ids=list(relations), evidence_relations=relations,
        reason=answer.explanation, layer="settled" if task.tools else "verbatim",
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
        sources: Sequence[SourceAnswer] = (), places, pending=frozenset(), final=False,
        decision: dict | None = None, received: Mapping[str, Sequence[SourceAnswer]] | None = None) -> FieldValue:
    """The field's value from its outcome. ``decision`` collects, as codes,
    which of the step's checks refused a resolved answer ("refusal") and which
    rule decided it ("rule"), for the field's trace (trace_fields).
    ``received`` holds the source answers of every field, by field (_misfit)."""
    decision = {} if decision is None else decision
    answer = outcome.answer
    current = task.current
    if task.key in NO_APPROVED_AUTHORITY:
        # research_harness.evidence.missing_irn_resolution: unresolved, no party.
        decision["rule"] = "irn_nonblocking_exception"
        return FieldValue(state=ValueState.UNKNOWN, evidence_ids=list(current.evidence_ids),
            reason=IRN_REASON)
    cited = [e for e in (answer.source_evidence_ids if answer else ()) if e in evidence
        and evidence[e].kind != "literal"]
    if outcome.failure is not None or answer is None:
        reason = FIELD_REASONS.get(outcome.failure, FIELD_REASONS[None])
        if final and outcome.failure == "source_unavailable":
            decision["rule"] = "unreachable_on_last_attempt"
            reason = _unreachable_reason(run, outcome)
        elif final and outcome.failure == "timeout":
            decision["rule"] = "timed_out_on_last_attempt"
            reason = _timeout_reason(run)
        return _unsettled(task, ValueState.UNRESOLVED, literal=current.literal, cited=cited, reason=reason)
    if answer.outcome == "resolved":
        reconciled = outcome.finalized_without_model and answer.explanation.startswith(
            "Resolved by location reconciliation:")
        if not reconciled:
            refused = _refusal(task, answer, readings=readings, by_name=by_name, sources=sources)
            if refused is not None:
                decision["refusal"] = refusal_code(refused.reason)
                # A pick between readers no source settles is ambiguous; a value no
                # decided transcript or place source supports is unresolved.
                if refused.differ:
                    return _unsettled(task, ValueState.AMBIGUOUS, cited=cited,
                        reason=f"{refused.reason} {answer.explanation}")
                return _unsettled(task, ValueState.UNRESOLVED, literal=current.literal, cited=cited,
                    reason=f"{refused.reason} {answer.explanation}")
        if not reconciled:
            misfit = _misfit(run, task, answer, sources=sources, readings=readings, by_name=by_name,
                places=places, pending=pending, received=received)
            if misfit is not None:
                decision["refusal"] = refusal_code(misfit.reason)
                return _unsettled(task, ValueState.UNRESOLVED, literal=current.literal, cited=cited,
                    reason=f"{misfit.reason} {answer.explanation}")
        else:
            decision["rule"] = "location_reconciliation"
        settled = _settled(run, task, outcome, by_name=by_name, evidence=evidence, asset_id=asset_id,
            blobs=blobs, date_rules=date_rules)
        if settled is not None:
            _place_basis(run, task, answer, sources, settled)
            return settled
        decision["refusal"] = "literal_not_in_readings"
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
        why: list[str] = []
        unmatched = _unmatched_taxon(run, task, outcome, readings=readings, by_name=by_name, evidence=evidence,
            asset_id=asset_id, blobs=blobs, sources=sources, why=why)
        decision["rule"] = ("B_unmatched_taxon" if unmatched is not None
            else "B_declined:" + (why[0] if why else "unknown"))
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


def _gbif_found_a_genus(status: LookupStatus, candidates, queries: Iterable[str | None]) -> bool:
    """Whether a GBIF answer for the taxon shows that the label names a genus
    (B1 of #289's second review): GBIF answered with candidates, a success or
    an ambiguous answer (105526328's "Epipsocus" homonym), or what was asked
    names a genus (checks.query_names_a_genus). The taxon brief has the expert
    look up the genus a label writes ("Epipsocus" for "Epipsocus sp. 1", G25),
    so such a lookup is the expert's own finding that the label writes one,
    wherever on the label it stands. GBIF's no-name answer for a morphocode
    (no match, no candidates, "sp. 30 <female sign>" asked) is not."""
    from .checks import query_names_a_genus

    return (bool(candidates) or status in (LookupStatus.SUCCESS, LookupStatus.AMBIGUOUS)
        or any(query_names_a_genus(query) for query in queries))


def _answer_found_a_genus(item: SourceAnswer) -> bool:
    """_gbif_found_a_genus for a GBIF answer an expert received."""
    return item.source_id == "gbif" and _gbif_found_a_genus(item.status, item.candidates, (item.query,))


def _lookup_found_a_genus(lookup) -> bool:
    """_gbif_found_a_genus for a GBIF lookup the run stores: its query, as
    sent ("scientificName") or as asked ("name"), or the name it could not
    read (its "verbatim_name")."""
    if not isinstance(lookup, Lookup) or lookup.provider != "gbif":
        return False
    asked = (lookup.query.get("scientificName"), lookup.query.get("name"), (lookup.metadata or {}).get("verbatim_name"))
    return _gbif_found_a_genus(lookup.status, lookup.candidates,
        (text for text in asked if isinstance(text, str)))


def _gbif_asked_another_name(queries: Iterable[str], literal: str) -> bool:
    """Whether GBIF was asked, for the taxon, any query that is not the
    morphocode `literal` itself (checks.query_is_the_code: case, spaces,
    punctuation and sex signs aside; N2 of #289's fourth review). The taxon
    brief never has the expert send GBIF a name no reading prints, so any
    other query is its own finding that a reading prints a name, read or
    misread ("Epipsocu55")."""
    from .checks import query_is_the_code

    return any(not query_is_the_code(query, literal) for query in queries)


def _lookup_asked_another_name(lookup, literal: str) -> bool:
    """_gbif_asked_another_name for a GBIF lookup the run stores: its query,
    as sent ("scientificName") or as asked ("name"), or the name it could
    not read (its "verbatim_name"). The step's own no-name lookup for the
    literal (_no_name) does not count."""
    if not isinstance(lookup, Lookup) or lookup.provider != "gbif" or _no_name(lookup, literal):
        return False
    asked = (lookup.query.get("scientificName"), lookup.query.get("name"), (lookup.metadata or {}).get("verbatim_name"))
    return _gbif_asked_another_name((text for text in asked if isinstance(text, str)), literal)


def _expert_found_no_genus(outcome: FieldOutcome, literal: str, *, by_name,
        sources: Sequence[SourceAnswer]) -> bool:
    """Whether the taxon's expert itself answered sources_cannot_resolve for
    the morphocode `literal`, as rule A requires its expert's own answer
    (mark_not_on_label, item 1): no failure, a model's answer (the field was
    not finalized without a model call), and not the resolver's fallback
    (FieldOutcome.fallback: an expert out of attempts, or whose answers
    could not be checked); no GBIF answer it received for the field
    (`sources`, the field's lookups) shows a genus (_answer_found_a_genus:
    candidates, or a query that names a genus); its answer quotes the code
    itself, its literal compared with `literal` as the GBIF guard compares a
    query (checks.query_is_the_code: case, spaces, punctuation and sex signs
    aside; N2 of #289's fifth review), whether or not it asked GBIF; and it
    answered after a GBIF lookup attempt for the field, or after its own
    check that the label names no genus: its literal is a morphocode of the
    same code (checks.morphocode) that a reading it names writes."""
    from .checks import morphocode, query_is_the_code

    answer = outcome.answer
    if (outcome.failure is not None or answer is None or answer.outcome != "sources_cannot_resolve"
            or outcome.finalized_without_model or outcome.fallback):
        return False
    if any(_answer_found_a_genus(item) for item in sources):
        return False
    if not answer.literal or not query_is_the_code(answer.literal, literal):
        return False
    if any(item.source_id == "gbif" for item in sources):
        return True
    return morphocode(answer.literal) == morphocode(literal) and any(
        answer.literal in by_name[name].text for name in answer.reading_names if name in by_name)


def _declined(why: list[str] | None, code: str) -> None:
    """A rule that does not apply: its code joins `why` (the field's trace,
    trace_fields), and the rule gives nothing."""
    if why is not None:
        why.append(code)
    return None


def _unmatched_taxon(run, task, outcome: FieldOutcome, *, readings, by_name, evidence, asset_id, blobs,
        sources: Sequence[SourceAnswer], why: list[str] | None = None) -> FieldValue | None:
    """Owner decision B: the taxon as written, unmatched, when the expert
    found that GBIF cannot resolve it and the label names no genus. All of:
    - the expert answered sources_cannot_resolve itself, quoting the code
      itself (case, spaces, punctuation and sex signs aside), after a GBIF
      lookup attempt or from a reading it names that writes it
      (_expert_found_no_genus); a failure, a field finalized without a
      model call and the resolver's fallback never qualify, nor does an
      expert any of whose GBIF answers for the field has candidates or
      asked a name that names a genus, nor one that quotes anything else
      ("Epipsocus");
    - the expert asked GBIF, for the field, no query but the code itself
      (_gbif_asked_another_name: case, spaces, punctuation and sex signs
      aside), so a misread genus it asked ("Epipsocu55") holds it back;
    - the organiser's literal names no genus (checks.names_no_genus: "sp. 30
      <female sign>"; "Aus bus n. sp." and "Epipsocus sp. 1" do not qualify);
    - every taxon candidate is the same morphocode, a text with no genus and
      the same code (checks.morphocode: a reader's "Sp.30 <female sign>"
      beside "sp. 30 <female sign>", but never "sp. 39");
    - the label names no genus for that code (checks.label_names_no_genus):
      wherever any reading writes it, no token that may be a genus
      (checks.may_be_genus: a letter and no digit, "Epipsocus?", "E.?",
      "[unreadable]"; or three letters or more and one digit at most,
      "Epipsocu5", "ep1psocus") is written immediately before it (on its line, or
      ending the nearest line above that has a token), or first after it on
      its line, words of checks.NOT_GENERA ("legs", "head", "Kopf") and a
      person's name with initials ("R.D.mitchell") passed over
      (checks.genus_beside). A candidate "sp. 1" taken from "Epipsocus sp.
      1", or from "Epipsocus" with "sp. 1" on the next line, does not
      qualify;
    - no part of a label that writes the code is unreadable
      (_code_label_unreadable, rule A's test on that label);
    - no sign of a doubtful or unreadable name shows anywhere on the
      specimen (_doubt_on_the_labels: checks.DOUBT_SIGNS in any reading of
      any label, the qualifier sign reading the run's places, settled
      before the taxon (_settled_places), or an unreadable span on any
      label). The
      taxon brief has the expert look a doubtful genus up alone, a query
      the GBIF guard above refuses; these signs hold the taxon back when it
      does not;
    - the readers settle on the literal by B1's rule (agreement.labels):
      each label that writes the taxon settles on its own on that one text.
      With no successful lookup that is a label's decided transcript (its
      other readers are evidence only), or readers of a label with none that
      each write exactly that text.
    The value meets the agreement rules any resolved answer meets
    (agreement.refusal through _refusal: G19's decided transcript, a whole
    candidate whose quote writes no longer name around it, readers that
    agree). It is built as a settled answer is (_settled: the label rows and
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
        return _declined(why, "organiser_value_not_a_morphocode")
    if not _expert_found_no_genus(outcome, literal, by_name=by_name, sources=sources):
        return _declined(why, "expert_did_not_find_no_genus")
    if _gbif_asked_another_name((item.query for item in sources if item.source_id == "gbif"), literal):
        return _declined(why, "gbif_asked_another_name")
    if not task.candidates or any(morphocode(c.literal) != code for c in task.candidates):
        return _declined(why, "candidates_not_one_morphocode")
    if not label_names_no_genus(code, [r.text for r in readings]):
        return _declined(why, "label_names_a_genus")
    if _code_label_unreadable(run, readings, code):
        return _declined(why, "code_label_unreadable")
    if _doubt_on_the_labels(run, readings):
        return _declined(why, "doubt_on_the_labels")
    want = collapse(literal)
    tools = frozenset(task.tools) & SOURCE_IDS
    found = labels(task, readings, [a for a in sources if a.source_id in tools])
    if not found or any(label.settled != frozenset({want}) or label.by_source for label in found.values()):
        return _declined(why, "readers_do_not_settle")
    written = reader_literals(task, readings)
    decided = {r.region_id for r in readings if r.input_source == DECIDED}
    named = [r for r in readings if r.region_id in found and want in written.get(r.name, ())
        and (r.input_source == DECIDED or r.region_id not in decided)]
    whole = candidate_literal(task, readings, literal, named) if named else None
    if whole is None:
        return _declined(why, "no_whole_candidate")
    answer = FieldAnswer(outcome="resolved", literal=whole, reading_names=[r.name for r in named],
        explanation=UNMATCHED)
    # The agreement rules every resolved answer meets (agreement.refusal),
    # #284's guard against a candidate that cuts its quoted name among them.
    if _refusal(task, answer, readings=readings, by_name=by_name, sources=sources) is not None:
        return _declined(why, "agreement_refusal")
    value = _settled(run, task, FieldOutcome(task.key, answer), by_name=by_name, evidence=evidence,
        asset_id=asset_id, blobs=blobs)
    if value is None:
        return _declined(why, "literal_not_in_readings")
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


def _apply_answers(run, tasks_by_key: Mapping[str, FieldTask], ordered: Sequence[FieldOutcome], *,
        taken: Mapping[str, str], human, readings, by_name, evidence: dict, asset_id, blobs, date_rules,
        received: Mapping[str, Sequence[SourceAnswer]], places, final: bool,
        decisions: dict[str, dict]) -> tuple[dict[str, FieldOutcome], dict[str, list[str]]]:
    """Each outcome, in `ordered` (the places from the country down), as its
    field's value (_field_value), a field in `taken` as text another kind of
    field claims (_taken_value), then the places settled on initials alone
    made ambiguous (_corroborate). A field a person decided is left as it is.
    Returns the outcomes applied and, per field, the evidence rows its value
    added."""
    pending = {outcome.key for outcome in ordered}
    applied: dict[str, FieldOutcome] = {}
    added: dict[str, list[str]] = {}
    for outcome in ordered:
        task = tasks_by_key.get(outcome.key)
        pending.discard(outcome.key)
        if task is None or task.key in human:
            continue
        decision = decisions.setdefault(task.key, {})
        before = len(run.evidence)
        if task.key in taken:
            decision["refusal"] = "taken"
            run.fields[task.key] = _taken_value(task, outcome, taken[task.key], evidence)
        else:
            run.fields[task.key] = _field_value(run, task, outcome, readings=readings, by_name=by_name,
                evidence=evidence, asset_id=asset_id, blobs=blobs, date_rules=date_rules,
                sources=received.get(task.key, ()), places=places, pending=frozenset(pending), final=final,
                decision=decision, received=received)
        applied[task.key] = outcome
        added[task.key] = [item.id for item in run.evidence[before:]]
    for key in _corroborate(run, tasks_by_key, applied, received, evidence=evidence, added=added):
        decisions.setdefault(key, {})["refusal"] = "initialism_alone"
    return applied, added


LOCATION_RECONCILE_KEYS = ("country", "province_state", "county", "city")


@dataclass(frozen=True)
class _LocationProposal:
    key: str
    literal: str
    reading_names: tuple[str, ...]
    literal_key: str
    source_key: str
    answer: SourceAnswer
    candidate: object


def _readings_for_literal(task: FieldTask, readings: Sequence[Reading], literal: str) -> tuple[str, ...]:
    """The readings that write ``literal`` for a location reconciliation:
    prefer organiser candidates, then transcript text."""
    from .agreement import place_name

    candidate_readings = [c.reading for c in task.candidates if place_name(c.literal) == place_name(literal)]
    if candidate_readings:
        return tuple(dict.fromkeys(candidate_readings))
    return tuple(reading.name for reading in readings if literal in reading.text)


def _location_literals(task: FieldTask, readings: Sequence[Reading]) -> list[tuple[str, tuple[str, ...]]]:
    """Distinct place strings a field brought to the shared location pool."""
    from .agreement import place_name

    found: dict[str, tuple[str, tuple[str, ...]]] = {}
    for candidate in task.candidates:
        if candidate.literal and candidate.literal.strip():
            key = place_name(candidate.literal)
            found.setdefault(key, (candidate.literal, _readings_for_literal(task, readings, candidate.literal)))
    if task.current.literal and task.current.literal.strip():
        key = place_name(task.current.literal)
        found.setdefault(key, (task.current.literal, _readings_for_literal(task, readings, task.current.literal)))
    return [item for item in found.values() if item[1]]


def _proposal_identity(proposal: _LocationProposal) -> tuple[str, tuple[str, ...]]:
    from .agreement import place_name

    candidate = proposal.candidate
    return (place_name(candidate.name), tuple(place_name(parent.name) for parent in candidate.parents))


def _location_name_matches_literal(literal: str, answer: SourceAnswer, candidate) -> bool:
    """Whether a shared location answer can stand for a field's label text.

    Reconciliation may move a place string to a different administrative field.
    It should accept the same place-name comparison as ordinary place settling,
    plus the abbreviation expansion rule used there (for example ``Ill.`` ->
    ``Illinois``).
    """
    from .abbreviations import fits
    from .agreement import asked_name, place_name

    literal_name = place_name(literal)
    candidate_name = place_name(candidate.name)
    if candidate_name == literal_name:
        return True
    asked = asked_name(answer)
    return ((place_name(asked) == candidate_name and fits(literal, asked))
        or fits(literal, candidate.name))


def _answer_can_support_location_literal(answer: SourceAnswer, literal: str) -> bool:
    """Whether a source answer was about a written literal or its expansion."""
    from .abbreviations import fits
    from .agreement import about, asked_name

    return about(answer, literal) or fits(literal, asked_name(answer))


def _text_names_place(text: str | None, place: str) -> bool:
    """Whether label text names a place exactly or by abbreviation."""
    if not text:
        return False
    from .abbreviations import fits
    from .agreement import place_name

    return place_name(text) == place_name(place) or fits(text, place)


def _field_place(run, key: str, value: FieldValue, evidence: Mapping[str, Evidence],
        received: Mapping[str, Sequence[SourceAnswer]]):
    """A supported place value as agreement.lies_in compares it."""
    from .agreement import PlaceField

    if value.state != ValueState.SUPPORTED or value.layer not in RESEARCHED:
        return None
    rows = {item.id: item for item in run.evidence}
    names = tuple(dict.fromkeys(text for text in (
        value.literal, value.normalized, value.parsed, *_expansions(key, value, rows)) if text))
    if not names and not value.authority_id:
        return None
    code = _record_code(value, received.get(key, ())) if key == "country" else None
    return PlaceField(names, value.authority_id, code)


def _candidate_fits_existing_chain(run, key: str, literal: str, candidate, *,
        evidence: Mapping[str, Evidence], received: Mapping[str, Sequence[SourceAnswer]]) -> bool:
    """Whether a proposal conflicts with already-supported or explicitly
    written larger places. Unsupported larger literals may be the same
    misplaced text, or one of the candidate's parents; otherwise they keep the
    field reviewable."""
    from .agreement import PLACE_ORDER, lies_in, place_name

    ancestors = PLACE_ORDER[:PLACE_ORDER.index(key)]
    for ancestor in ancestors:
        value = run.fields.get(ancestor)
        if value is None:
            continue
        if (field := _field_place(run, ancestor, value, evidence, received)) is not None:
            if not lies_in(candidate, ancestor, field):
                return False
            continue
        if value.literal and value.state != ValueState.NOT_PRESENT:
            written = place_name(value.literal)
            names_candidate_or_parent = (written == place_name(literal)
                or any(_text_names_place(value.literal, parent.name) for parent in candidate.parents))
            if not names_candidate_or_parent:
                return False
    return True


def _location_proposals(tasks_by_key: Mapping[str, FieldTask],
        received: Mapping[str, Sequence[SourceAnswer]], readings: Sequence[Reading]) -> dict[str, list[_LocationProposal]]:
    """Source-confirmed place interpretations pooled across location fields."""
    from .agreement import at_level

    proposals: dict[str, list[_LocationProposal]] = {key: [] for key in LOCATION_RECONCILE_KEYS}
    location_keys = (*LOCATION_RECONCILE_KEYS, "precise_location")
    by_name = {reading.name: reading for reading in readings}
    literals = [(key, literal, grounded) for key in location_keys if key in tasks_by_key
        for literal, names in _location_literals(tasks_by_key[key], readings)
        if (grounded := tuple(name for name in names
            if name in by_name and literal in by_name[name].text))]
    # Expert routing is not evidence ownership: a country expert may look up
    # the state text that the organiser put under city. Pair every grounded
    # location literal with the captured location answers, without new calls.
    for source_key in location_keys:
        for answer in received.get(source_key, ()):
            if answer.evidence is None:
                continue
            for literal_key, literal, names in literals:
                if not _answer_can_support_location_literal(answer, literal):
                    continue
                for key in LOCATION_RECONCILE_KEYS:
                    for candidate in at_level(key, answer):
                        if not _location_name_matches_literal(literal, answer, candidate):
                            continue
                        proposals[key].append(_LocationProposal(key, literal, names, literal_key, source_key, answer, candidate))
    return proposals


def _compatible_location_literals(proposals: Mapping[str, Sequence[_LocationProposal]], *,
        tasks_by_key: Mapping[str, FieldTask], readings: Sequence[Reading],
        received: Mapping[str, Sequence[SourceAnswer]]) -> dict[str, list[_LocationProposal]]:
    """Use distinct, source-typed administrative text as relational constraints.

    A written county can have several matches and still constrain a written
    state to a parent of one of those matches. Only literals with one known
    administrative level constrain others; disputed towns/localities do not
    choose an administrative chain. Keep the original constraint sets while
    filtering so an inconsistent written state cannot disappear and allow a
    county to donate a different state afterwards.
    """
    from .agreement import PLACE_ORDER, PlaceField, lies_in, place_name

    by_literal: dict[str, list[_LocationProposal]] = {}
    for items in proposals.values():
        for proposal in items:
            by_literal.setdefault(place_name(proposal.literal), []).append(proposal)
    constraints = {literal: items for literal, items in by_literal.items()
        if len({item.key for item in items}) == 1 and items[0].key != "city"}
    agreed = {literal: [item for item in items if _location_readers_agree(item, tasks_by_key, readings, received)]
        for literal, items in constraints.items()}

    def compatible(proposal, other):
        if proposal.key == other.key:
            return True
        parent, child = (proposal, other) if PLACE_ORDER.index(proposal.key) < PLACE_ORDER.index(other.key) else (other, proposal)
        candidate = parent.candidate
        return lies_in(child.candidate, parent.key,
            PlaceField((candidate.name,), candidate.authority_id, candidate.iso_code))

    def fits_constraint(proposal, literal, alternatives):
        if literal == place_name(proposal.literal):
            return True
        if not agreed[literal]:
            # Unsettled reader alternatives cannot narrow other places, nor
            # can a child hide that unsettled ancestor by deriving it later.
            return PLACE_ORDER.index(proposal.key) <= PLACE_ORDER.index(alternatives[0].key)
        return any(compatible(proposal, other) for other in agreed[literal])

    return {key: [proposal for proposal in items
        if all(fits_constraint(proposal, literal, alternatives)
            for literal, alternatives in constraints.items())]
        for key, items in proposals.items()}


def _answer_levels_for_literal(answer: SourceAnswer, literal: str) -> set[str]:
    """Location levels one source answer confirms for the written literal."""
    from .agreement import at_level

    levels: set[str] = set()
    for key in LOCATION_RECONCILE_KEYS:
        if any(_location_name_matches_literal(literal, answer, candidate) for candidate in at_level(key, answer)):
            levels.add(key)
    return levels


def _narrowed_location_answer(proposal: _LocationProposal) -> SourceAnswer:
    """The cited answer as the normal place-settling check should see it.

    Gazetteer answers may hold several same-level places with the same name,
    such as the United States' many Clark Counties. Reconciliation first filters
    those candidates against the label's other place text. Once only one
    hierarchy-compatible proposal remains, pass that single candidate through
    the ordinary field-value checks so the field still settles only by a cited
    source answer at its own level.
    """
    return replace(proposal.answer, candidates=(proposal.candidate,))


def _location_readers_agree(proposal: _LocationProposal, tasks_by_key: Mapping[str, FieldTask],
        readings: Sequence[Reading], received: Mapping[str, Sequence[SourceAnswer]]) -> bool:
    """Moving a literal carries both its owner's and destination's alternatives.

    Fresh grounded gazetteer answers, or the existing explicit county-unit
    rule for a country/state fragment, establish another level. Unknown or
    same-level alternatives stay in the ordinary G19/G20/G32 proof, including
    on other labels. Transcript coverage additionally
    prevents a one-reader candidate from hiding text filed under another field.
    """
    from specimen_digitization.application.georef_locality import fold
    from .admin_markers import ADMIN_MARKERS
    from .agreement import PLACE_ANSWERED, _disagreement, literal_refusal, refusal, verbatim_runs, writes_county_unit
    from .contracts import GAZETTEERS

    owner = tasks_by_key[proposal.literal_key]
    task = replace(owner, key=proposal.key, tools=FIELD_TOOLS[proposal.key])
    source = _narrowed_location_answer(proposal)
    by_name = {reading.name: reading for reading in readings}
    named = [by_name[name] for name in proposal.reading_names]
    if literal_refusal(task, readings, literal=proposal.literal, named=named) is not None:
        return False
    captured = [answer for answers in received.values() for answer in answers]

    def other_level(literal, reading):
        if reading is None or not verbatim_runs(reading.text, literal):
            return False
        levels = set().union(*(_answer_levels_for_literal(answer, literal) for answer in captured
            if answer.source_id in GAZETTEERS and answer.status in PLACE_ANSWERED
            and answer.evidence is not None and _answer_can_support_location_literal(answer, literal)))
        if levels:
            return proposal.key not in levels
        # This only classifies explicit county/municipality text; it supplies
        # no identity or supported value. Retain mixed province/county units.
        return (proposal.key in {"country", "province_state"} and writes_county_unit(literal)
            and not any("province_state" in ADMIN_MARKERS.get(word, ()) for word in fold(literal).split()))

    candidates = []
    verbatims = {}
    contexts = [owner]
    target = tasks_by_key.get(proposal.key)
    if target is not None and target is not owner:
        contexts.append(target)
    for context in contexts:
        candidates.extend(candidate for candidate in context.candidates
            if not other_level(candidate.literal, by_name.get(candidate.reading)))
        for observation, literal in context.current.verbatim_by_observation.items():
            observation_readings = [reading for reading in readings if reading.observation_id == observation]
            if observation_readings and all(other_level(literal, reading) for reading in observation_readings):
                continue
            if observation in verbatims and verbatims[observation] != literal:
                # This private proof view must represent both fields' text for
                # one observation. These alternatives are never persisted as
                # evidence, candidates or authority claims.
                candidates.extend(Candidate(reading.name, literal, literal, "") for reading in observation_readings)
            else:
                verbatims[observation] = literal
    task = replace(task, candidates=tuple(candidates), current=FieldValue(verbatim_by_observation=verbatims))
    common = dict(literal=proposal.literal, named=named,
        authority_id=proposal.candidate.authority_id, cited=(source,), received=(*captured, source))
    return (refusal(task, readings, value=proposal.candidate.name, **common) is None
        and _disagreement(task, readings, transcript=proposal.literal, **common) is None)


def _usable_location_proposals(run, proposals: Mapping[str, Sequence[_LocationProposal]], *,
        evidence: Mapping[str, Evidence], received: Mapping[str, Sequence[SourceAnswer]]) -> dict[str, list[_LocationProposal]]:
    """Usable proposals, excluding one written place name claimed at several levels.

    Reconciliation moves evidence between fields only when the shared lookup
    proves one administrative level for the label text. A gazetteer answer that
    contains the same written name as both a province/state and a county is real
    evidence, but not enough to choose either synthesized field from one label
    literal. The ambiguity check includes the source field's level too, because
    source-level candidates are intentionally not synthesized back to themselves.
    """
    from .agreement import place_name

    usable: dict[str, list[_LocationProposal]] = {}
    levels_by_literal: dict[str, set[str]] = {}
    ambiguous: set[str] = set()
    for key, items in proposals.items():
        accepted = [proposal for proposal in items
            if _candidate_fits_existing_chain(run, key, proposal.literal, proposal.candidate,
                evidence=evidence, received=received)]
        usable[key] = accepted
        for proposal in accepted:
            literal = place_name(proposal.literal)
            answer_levels = _answer_levels_for_literal(proposal.answer, proposal.literal)
            if len(answer_levels) > 1:
                ambiguous.add(literal)
            levels_by_literal.setdefault(literal, set()).add(key)
    ambiguous.update(literal for literal, keys in levels_by_literal.items() if len(keys) > 1)
    if not ambiguous:
        return usable
    return {key: [proposal for proposal in items if place_name(proposal.literal) not in ambiguous]
        for key, items in usable.items()}


def _reconcile_location_outcomes(run, tasks_by_key: Mapping[str, FieldTask],
        outcomes: Sequence[FieldOutcome], *, readings: Sequence[Reading],
        received: dict[str, list[SourceAnswer]], evidence: Mapping[str, Evidence],
        human: frozenset[str]) -> tuple[FieldOutcome, ...]:
    """Project shared location evidence back into the field outcomes.

    The field experts still gather and check source evidence, but source
    answers about a location string are shared: if the answer uniquely proves
    the string belongs at another administrative level, the normal field
    application sees a resolved outcome for that level.
    """
    by_key = {outcome.key: outcome for outcome in outcomes}
    proposals = _compatible_location_literals(_location_proposals(tasks_by_key, received, readings),
        tasks_by_key=tasks_by_key, readings=readings, received=received)
    qualification = run.model_copy(update={"fields": dict(run.fields)})
    for key in LOCATION_RECONCILE_KEYS:
        task = tasks_by_key.get(key)
        value = run.fields.get(key)
        existing = by_key.get(key)
        if (task is None or key in human
                or (value is not None and value.state == ValueState.SUPPORTED and value.layer in RESEARCHED)):
            continue
        if existing is None or existing.answer is None or existing.answer.outcome != "resolved":
            usable = _usable_location_proposals(qualification, proposals,
                evidence=evidence, received=received).get(key, ())
            identities = {_proposal_identity(proposal) for proposal in usable}
            source_ids: dict[str, set[str]] = {}
            for proposal in usable:
                if proposal.candidate.authority_id:
                    source_ids.setdefault(proposal.answer.source_id, set()).add(proposal.candidate.authority_id)
            if len(identities) != 1 or any(len(ids) > 1 for ids in source_ids.values()):
                continue
            if not all(_location_readers_agree(proposal, tasks_by_key, readings, received) for proposal in usable):
                continue
            proposal = usable[0]
            source_answer = _narrowed_location_answer(proposal)
            answer = FieldAnswer(outcome="resolved", literal=proposal.literal,
                reading_names=list(proposal.reading_names),
                value=proposal.candidate.name if proposal.candidate.name != proposal.literal else None,
                authority_id=proposal.candidate.authority_id,
                source_evidence_ids=[source_answer.evidence.id],
                explanation=("Resolved by location reconciliation: the shared location lookup identified "
                    f"this label text as {key.replace('_', ' ')}."))
            by_key[key] = FieldOutcome(key, answer, evidence=[source_answer.evidence],
                finalized_without_model=True)
            received.setdefault(key, []).append(source_answer)
        # Qualify each parent before using it to narrow the next level. A
        # model's resolved claim alone must not become an ancestry constraint.
        settled = _first_pass(qualification, tasks_by_key, (by_key[key],), human=human,
            readings=readings, by_name={reading.name: reading for reading in readings},
            asset_id=run.regions[0].asset_id if run.regions else None, date_rules=None,
            received=received, places=_place_texts(qualification, tasks_by_key, readings), final=last_attempt(run))
        qualification.fields.update(settled)
    return tuple(by_key.get(outcome.key, outcome) for outcome in outcomes)


def _first_pass(run, tasks_by_key: Mapping[str, FieldTask], ordered: Sequence[FieldOutcome],
        **common) -> dict[str, FieldValue]:
    """What this attempt's answers settle before the guard on text another
    field holds (_taken): every outcome applied as apply_outcomes applies it,
    with no field taken (_apply_answers), on a copy of the run's fields,
    evidence, findings and lookups, writing no blob and making no Logfire
    event (_FIRST_PASS). The run itself is left as it was. Returns the values
    that settle: supported, in a settled layer (SETTLED_LAYERS)."""
    copy = run.model_copy(update={
        "fields": {key: value.model_copy(deep=True) for key, value in run.fields.items()},
        "evidence": list(run.evidence), "findings": list(run.findings), "lookups": list(run.lookups)})
    marker = _FIRST_PASS.set(True)
    try:
        applied, _ = _apply_answers(copy, tasks_by_key, ordered, taken={},
            evidence={item.id: item for item in copy.evidence}, blobs=None, decisions={}, **common)
    finally:
        _FIRST_PASS.reset(marker)
    return {key: copy.fields[key] for key in applied
        if copy.fields[key].state == ValueState.SUPPORTED and copy.fields[key].layer in SETTLED_LAYERS}


def apply_outcomes(run, profile: CollectionProfile | None, tasks: Sequence[FieldTask],
        outcomes: Sequence[FieldOutcome], *, blobs=None, calls: Sequence[SourceCall] = (),
        asset_id: str | None = None, decisions: dict[str, dict] | None = None) -> list[str]:
    """Turn the outcomes into the run's field values and evidence, in memory only.

    resolved: supported, with the literal, its lineage, the label rows of the
    readings it names (a new row where none covers a reading), every other
    reader's organiser row (supporting or contradicting it) and the source
    evidence it cites (GBIF decides; other sources support); a deterministic
    check's parse gets a "derived" row when the check, run again on the
    literal, gives that value. A resolved answer the agreement rules refuse
    (agreement.refusal: a literal that is neither a whole candidate of the
    readings it names nor whole words of one line of each, or that the
    label's decided transcript does not write, a pick between readers no
    source settles, a place no place source confirms), whose place does not
    lie in the country and province settled for its reading (_misfit, after
    the places above it), or whose literal, read from the transcript, is
    text another kind of field's settled value claims (_taken, judged on
    what the answers settle without it: _first_pass), is ambiguous or
    unresolved instead; a place settled on initials that no place below it
    confirms is ambiguous (_corroborate, once every place is in). A literal
    read from the transcript that settles is marked so
    (_from_the_transcript). A precise location whose answer gives only an
    administrative marker beside the places settled is not present
    (_no_finer_place, after _corroborate), and so is one settled on only
    the text of a settled place field of the same reading
    (_repeats_a_place).
    label_lacks_value: not present;
    sources_cannot_resolve: unresolved, except a taxon that names no genus,
    supported as written and unmatched (_unmatched_taxon); several_possibilities:
    ambiguous, the options in the reason; a failure: unresolved with a
    retryable reason, except on the step's last attempt (last_attempt) a
    source still unreachable, whose reason names the sources not reached
    (_unreachable_reason), and a field that ran out of time, whose reason
    says so (_timeout_reason). Then the derived values, then the listed fields the
    label does not state (mark_not_on_label); the keys derived are returned.
    Last, a field whose expert's answer stood although a source it asked
    could not be reached (FieldOutcome.unreachable) ends its reason with a
    note naming that source (_unreachable_note). ``decisions`` collects, per
    field, the codes of the checks and rules that decided it (trace_fields).
    """
    from .agreement import PLACE_ORDER
    from .location_reassessment import active_keys

    reassessing = active_keys(run)
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
    outcomes = _reconcile_location_outcomes(run, tasks_by_key, outcomes, readings=readings,
        received=received, evidence=evidence, human=human)
    # The places first, from the country down: a place below it settles only
    # inside the country (and province) settled before it (_misfit).
    ordered = sorted(outcomes, key=lambda o: PLACE_ORDER.index(o.key) if o.key in PLACE_ORDER else len(PLACE_ORDER))
    decisions = {} if decisions is None else decisions
    common = dict(human=human, readings=readings, by_name=by_name, asset_id=asset_id, date_rules=profile.date_rules,
        received=received, places=places, final=last_attempt(run))
    # Text read from the transcript that another kind of field claims (_taken):
    # only what the answers settle claims text, so they are applied once
    # first, on a copy of the run (_first_pass).
    taken = _taken(run, tasks_by_key, ordered, readings, _first_pass(run, tasks_by_key, ordered, **common))
    applied, added = _apply_answers(run, tasks_by_key, ordered, taken=taken, evidence=evidence, blobs=blobs,
        decisions=decisions, **common)
    # A precise location that gives only an administrative marker beside the
    # places settled has no value on the label (_no_finer_place).
    no_finer = _no_finer_place(run, profile, tasks_by_key, applied, added, readings, evidence=evidence,
        decisions=decisions)
    # A precise location settled on only a settled place's text is no finer
    # locality: not present, as label_lacks_value makes it (_repeats_a_place).
    repeated = _repeats_a_place(run, tasks_by_key, applied, added, readings, evidence=evidence,
        decisions=decisions)
    eligible = [key for key in field_keys(profile) if key not in human
        and (not reassessing or key in reassessing)]
    derived = derive.fill(run, eligible=eligible, asset_id=asset_id, blobs=blobs, received=received)
    for key in derived:
        decisions.setdefault(key, {})["rule"] = "derived"
    # Last, so that a value derived above is never marked absent.
    declined: dict[str, str] = {}
    for key in mark_not_on_label(run, profile, tasks, outcomes, readings=readings, asset_id=asset_id, blobs=blobs,
            why=declined, no_finer=no_finer, repeated=repeated):
        decisions.setdefault(key, {})["rule"] = "A_not_on_label"
    for key, code in declined.items():
        # A value derived above keeps "derived" (rule A declines it as present).
        decisions.setdefault(key, {}).setdefault("rule", "A_declined:" + code)
    # An answer that stood although a source could not be reached names it.
    rows = {item.id: item for item in run.evidence}
    for outcome in outcomes:
        value = run.fields.get(outcome.key)
        if (outcome.failure is None and outcome.unreachable and outcome.key in tasks_by_key
                and outcome.key not in human and value is not None and value.layer != "derived"):
            value.reason = " ".join(part for part in (value.reason, _unreachable_note(outcome, value, rows))
                if part)
    return derived


def _source_names(source_ids: Iterable[str]) -> str:
    """Source ids as the sources call themselves (sources.NAMES), in plain
    words: "Getty TGN", "Wikidata and NGA GEOnet Names Server"."""
    from .sources import NAMES

    names = list(dict.fromkeys(NAMES.get(source, source) for source in source_ids))
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _unreachable_note(outcome: FieldOutcome, value: FieldValue, rows: Mapping[str, Evidence]) -> str:
    """The note a field's reason ends with when its expert's answer stood
    although a source could not be reached (experts: one dead source does
    not void a field): the sources not reached and, for a settled value, the
    sources whose answers it cites."""
    from .sources import NAMES

    note = f"{_source_names(outcome.unreachable)} could not be reached"
    if value.state == ValueState.SUPPORTED:
        cited = [rows[i].source for i in value.evidence_ids if i in rows and rows[i].source in NAMES
            and value.evidence_relations.get(i) in ("supports", "decides")]
        if cited:
            note += f"; settled from {_source_names(cited)}"
    return note + "."


def _corroborate(run, tasks_by_key: Mapping[str, FieldTask], applied: Mapping[str, FieldOutcome],
        received: Mapping[str, Sequence[SourceAnswer]], *, evidence: dict,
        added: Mapping[str, Sequence[str]]) -> list[str]:
    """A place value settled in this attempt on initials (agreement.initialism_of:
    "P.I." looked up as "Philippine Islands", "UK" as "United Kingdom") stays
    settled only when a place field below it, settled in this attempt on its
    own evidence (on anything but initials), lies inside it: that field's
    settling candidate names it among its parents (agreement.lies_in: its
    record, or its text, value or expansion by name, or, for the country,
    the ISO code its settling candidate carries by a parent's country code).
    So "Mindanao, P.I."
    keeps the Philippines when its province "Davao, Prov." settles on a
    province of the Philippines. Otherwise the value is ambiguous, for review,
    with a reason naming the initials (agreement.initialism_alone), and the
    rows its settling added are dropped, with the transcript_literal finding
    of a literal read from the transcript (_from_the_transcript). Checked
    from the city up, once every place is in. Returns the keys left
    ambiguous, for their trace (trace_fields)."""
    from .agreement import PLACE_ORDER, PlaceField, initialism_alone, initialism_of, lies_in

    unsettled = []
    settlings = {}
    for key in PLACE_ORDER:
        outcome, task, value = applied.get(key), tasks_by_key.get(key), run.fields.get(key)
        answer = outcome.answer if outcome is not None else None
        if (task is None or answer is None or answer.outcome != "resolved" or value is None
                or value.state != ValueState.SUPPORTED):
            continue
        found = _settling(task, answer, received.get(key, ()))
        if found is not None:
            settlings[key] = (found, initialism_of(answer.literal, found))
    rows = {item.id: item for item in run.evidence}
    for index in reversed(range(len(PLACE_ORDER))):
        key = PLACE_ORDER[index]
        if key not in settlings or settlings[key][1] is None:
            continue
        expansion, value = settlings[key][1], run.fields[key]
        names = (value.literal, *(text for text in (value.normalized, value.parsed) if text),
            *_expansions(key, value, rows))
        code = settlings[key][0].candidate.iso_code if key == "country" else None
        field = PlaceField(tuple(dict.fromkeys(names)), value.authority_id, code)
        if any(other in settlings and settlings[other][1] is None
                and lies_in(settlings[other][0].candidate, key, field) for other in PLACE_ORDER[index + 1:]):
            continue
        task, answer = tasks_by_key[key], applied[key].answer
        dropped = set(added.get(key, ()))
        run.evidence[:] = [item for item in run.evidence if item.id not in dropped]
        for item_id in dropped:
            evidence.pop(item_id, None)
        # A literal read from the transcript: its finding goes with its rows.
        run.findings[:] = [finding for finding in run.findings if finding.reason_code != transcript_code(key)]
        cited = [e for e in answer.source_evidence_ids if e in evidence and evidence[e].kind != "literal"]
        run.fields[key] = _unsettled(task, ValueState.AMBIGUOUS, cited=cited,
            reason=f"{initialism_alone(answer.literal, expansion)} {answer.explanation}")
        del settlings[key]
        unsettled.append(key)
    return unsettled


# ---- fields the label does not state (owner decision A) -------------------

NOT_ON_LABEL_CHECK = "check:not_on_label"
NOT_ON_LABEL_REASON = "Not on the label: no reading states it, and its expert found none."
# The place fields whose literal can hold another place field's text.
PLACE_TEXT_FIELDS = ("country", "province_state", "county", "city", "precise_location")
# The fields whose organiser text may sit inside another settled place (the
# organiser's "Mt. McKinley" as a city, inside the settled precise location).
INSIDE_A_PLACE = frozenset({"county", "city", "precise_location"})
ELEVATION_FIELDS = frozenset({"elevation_from_m", "elevation_to_m", "elevation_from_ft", "elevation_to_ft"})
# A number in metres above sea level, however its unit is spaced or dotted:
# "msnm", "m snm", "m.s.n.m." (metros sobre el nivel del mar), "masl",
# "m a.s.l.". The place tool reads "m" before a space or a period as metres,
# but not "msnm" or "masl" written as one word (georef_locality.ELEVATION).
SEA_LEVEL_METRES = re.compile(
    r"\d[^\S\n]*m\.?[^\S\n]*(?:s\.?[^\S\n]*n\.?[^\S\n]*m|a\.?[^\S\n]*s\.?[^\S\n]*l)(?![A-Za-z])", re.I)
# A number, then a unit of elevation the place tool does not read, as Latin
# American labels write it: metres ("1200 mts.", "1200 mts", "1200 metros",
# "1200 msm") and feet ("6400 pies", "6400 p.s.n.m."); or metres as "m" or
# "m." ("1200 m", "1200 m."), which the place tool reads too. The number
# stands on its own, never the end of a date or a code ("V-4-67-1"), with an
# optional range end ("1200-1500 mts."); the unit is a whole word on the
# number's line ("1200 mm" is none).
NUMBER_AND_UNIT = re.compile(
    r"(?<![A-Za-z0-9/-])\d+(?:[.,]\d+)*(?:[^\S\n]*-[^\S\n]*\d+(?:[.,]\d+)*)?[^\S\n]*"
    r"(?:m|mts?|mtrs?|metros?|msm|pies|p\.?[^\S\n]*s\.?[^\S\n]*n\.?[^\S\n]*m)\.?(?![A-Za-z0-9])", re.I)


def not_on_label_keys(profile: CollectionProfile) -> frozenset[str]:
    """The profile's fields that may clear as "not on the label", by its id
    and version (contracts.NOT_ON_LABEL): a run's pinned profile, so a Retry
    sees the same list."""
    return not_on_label_fields(profile.id, profile.version)


def _whole_label_read(run, readings: Sequence[Reading]) -> bool:
    """Every label was read whole: label coverage confirmed; each label has
    two or more readers, each with text, and two or more named readings; and
    no part of any label is unreadable: no reader's unreadable span, no
    transcript marked unreadable, and no placeholder for an unread word
    anywhere in a reader's, a reading's or a transcript's text
    (checks.shows_placeholder, rule B's own test: the "[unreadable]" marker
    the reader prompt asks for in place of each unreadable span, prompts.py,
    and the other placeholders a transcriber writes, whether or not the
    reader also listed the span; N1 of #289's fifth review)."""
    from .checks import shows_placeholder

    if not run.coverage_confirmed or not run.regions:
        return False
    for region in run.regions:
        observed = [o for o in run.observations if o.region_id == region.id]
        named = [r for r in readings if r.region_id == region.id]
        if len(observed) < 2 or len(named) < 2 or any(not o.literal_text.strip() for o in observed):
            return False
    if any(not r.text.strip() for r in readings):
        return False
    texts = [*(o.literal_text for o in run.observations), *(r.text for r in readings),
        *(t.text or "" for t in run.transcripts)]
    if any(o.unreadable_spans for o in run.observations) or any(shows_placeholder(t) for t in texts):
        return False
    return not any(t.value_state == ValueState.UNREADABLE for t in run.transcripts)


def _code_label_unreadable(run, readings: Sequence[Reading], code: str) -> bool:
    """Whether part of a label that writes the morphocode `code` is
    unreadable, by rule A's test (_whole_label_read) on that label (B2 of
    #289's third review): a label any of whose readings, readers' texts or
    transcripts writes the code (checks.writes_code) has a reader's
    unreadable span, a transcript marked unreadable, or a placeholder for an
    unread word (checks.shows_placeholder) in a reader's, a reading's or a
    transcript's text. An unreadable word on the label may be the code's
    genus. True also when no text of the run writes the code."""
    from .checks import shows_placeholder, writes_code

    texts = [*((r.region_id, r.text) for r in readings), *((o.region_id, o.literal_text) for o in run.observations),
        *((t.region_id, t.text or "") for t in run.transcripts)]
    regions = {region for region, text in texts if writes_code(text, code)}
    return (not regions or any(o.unreadable_spans for o in run.observations if o.region_id in regions)
        or any(t.value_state == ValueState.UNREADABLE for t in run.transcripts if t.region_id in regions)
        or any(shows_placeholder(text) for region, text in texts if region in regions))


def _settled_places(run) -> tuple[str, ...]:
    """The literals of the run's place fields (country, province or state,
    county, city) settled on a place source's record: supported, with a
    literal and an authority_id. The qualifier doubt sign reads them
    (checks._qualifier_sign: "near Chicago" beside the settled city
    "Chicago"). apply_outcomes settles the places before the taxon, so
    _unmatched_taxon sees them, as the re-check (taxon_unmatched) does."""
    from .agreement import PLACE_ORDER

    values = [run.fields.get(key) for key in PLACE_ORDER]
    return tuple(value.literal for value in values if value is not None and value.state == ValueState.SUPPORTED
        and value.literal and value.authority_id)


def _doubt_on_the_labels(run, readings: Sequence[Reading]) -> tuple[str, ...]:
    """The signs of a doubtful or unreadable name (checks.DOUBT_SIGNS) that
    show anywhere on the specimen (B3 of #289's fourth review): in a
    reading's, a reader's or a transcript's text of any label, whether or
    not it writes the code; or a reader's unreadable span, or a transcript
    marked unreadable, on any label. The qualifier sign reads the run's
    settled places (_settled_places). Rule B refuses when any shows."""
    from .checks import doubt_signs

    texts = [*(r.text for r in readings), *(o.literal_text for o in run.observations),
        *(t.text or "" for t in run.transcripts)]
    unreadable = (any(o.unreadable_spans for o in run.observations)
        or any(t.value_state == ValueState.UNREADABLE for t in run.transcripts))
    return doubt_signs(texts, unreadable=unreadable, places=_settled_places(run))


def _organiser_texts(task: FieldTask, readings: Sequence[Reading]) -> list[tuple[str, frozenset]]:
    """What the organiser found for the field, each text with where it stands
    in the readings: its candidates' literals, where their quotes stand in
    their readings (_candidate_spans); its value's literal, wherever the
    readings of its label write it as whole tokens (_occurrences); and each
    reader's verbatim, wherever that reader's reading writes it so."""
    by_name = {reading.name: reading for reading in readings}
    found = []
    for candidate in task.candidates:
        reading = by_name.get(candidate.reading)
        found.append((candidate.literal, _candidate_spans(reading, candidate) if reading is not None else frozenset()))
    current = task.current
    if current.literal:
        found.append((current.literal, _occurrences(current.literal,
            [r for r in readings if current.source_region_id in (None, r.region_id)])))
    for observation, text in current.verbatim_by_observation.items():
        found.append((text, _occurrences(text, [r for r in readings if r.observation_id == observation])))
    return [(text, spans) for text, spans in found if text and text.strip()]


def _settled_claims(run, readings: Sequence[Reading]) -> list[tuple[str, str, frozenset]]:
    """Each settled value's field and literal, with where the literal stands
    (_claims_text, _value_spans): the text the run's settled values hold."""
    evidence = {item.id: item for item in run.evidence}
    human = human_keys(run)
    return [(key, value.literal, _value_spans(value, readings, evidence)) for key, value in run.fields.items()
        if _claims_text(key, value, human)]


# Punctuation and spaces at the start and at the end of a text, which rule A's
# comparison of an organiser text with a settled literal leaves aside (_bare).
LEADING, TRAILING = re.compile(r"^[\W_]+"), re.compile(r"[\W_]+$")


def _bare(text: str) -> str:
    """A text compared without letter case or the punctuation around it:
    "Trampa de luz." and "trampa de luz" are one text."""
    return TRAILING.sub("", LEADING.sub("", text)).casefold()


def _held_by_another_kind(key: str, text: str, spans: frozenset,
        claims: Sequence[tuple[str, str, frozenset]]) -> str | None:
    """The field of another kind (agreement.may_share_text) whose settled
    literal is the organiser's text for this field, letter case and the
    punctuation around it aside (_bare), where it stands: every place the
    text stands (`spans`; at least one), less that punctuation, lies inside
    where that literal stands, in the same reading. A settled value that
    only holds the text inside a longer literal ("cloud forest nr. Finca
    Moca" beside the organiser's precise location "nr. Finca Moca") does
    not. None otherwise."""
    from .agreement import may_share_text

    if not spans or not _bare(text):
        return None
    # Where the text stands, less the punctuation around it (each span is the
    # text's whole length).
    first = len(text) - len(LEADING.sub("", text))
    last = len(TRAILING.sub("", text))
    spans = frozenset((name, start + first, start + last) for name, start, _ in spans)
    for other, literal, theirs in claims:
        if other != key and not may_share_text(key, other) and _bare(text) == _bare(literal) and all(
                any(name == theirs_name and theirs_start <= start and end <= theirs_end
                    for theirs_name, theirs_start, theirs_end in theirs)
                for name, start, end in spans):
            return other
    return None


def _inside_a_settled_place(run, key: str, text: str) -> bool:
    """Whether the text names part of another supported place field's
    literal, word for word: its words, by the place comparison key
    (agreement.place_name: case, accents and punctuation aside, "Mt." read as
    "mount"), are a run of whole words of that literal's ("Mt. McKinley" in
    "E. slope Mt. McKinley"; never "Lee" in "Leesburg"). A text that writes a
    unit word of its own ("Cook County", "Davao Prov.", "Chimaltenango Dept.",
    "Mun. Yepocapa"; georef_locality.UNIT_WORDS) names a place of its own
    field and never counts."""
    from specimen_digitization.application.georef_locality import UNIT_WORDS, fold

    from .agreement import place_name

    words = place_name(text).split()
    if not words or any(word in UNIT_WORDS for word in fold(text).split()):
        return False
    for other in PLACE_TEXT_FIELDS:
        value = run.fields.get(other)
        if other == key or value is None or value.state != ValueState.SUPPORTED or not value.literal:
            continue
        within = place_name(value.literal).split()
        if any(within[start:start + len(words)] == words for start in range(len(within) - len(words) + 1)):
            return True
    return False


def _elevation_written(run, readings: Sequence[Reading]) -> bool:
    """Whether any reading writes an elevation: as the place tool reads one
    (georef_locality.read_locality), in its whole text or in any one line;
    a number in metres above sea level (SEA_LEVEL_METRES: "2000 msnm",
    "1200 masl", "1200 m.s.n.m.", "1200 m snm"), which the place tool does
    not read when written as one word; or a number and a unit it does not
    read (NUMBER_AND_UNIT: "1200 mts.", "1200 metros", "1200 msm", "6400
    pies", "6400 p.s.n.m.", and "1200 m" or "1200 m." too)."""
    from specimen_digitization.application.georef_locality import read_locality

    texts = dict.fromkeys([*(r.text for r in readings), *(o.literal_text for o in run.observations)])
    return any(SEA_LEVEL_METRES.search(text) or NUMBER_AND_UNIT.search(text) for text in texts) or any(
        read_locality(part).elevations for text in texts for part in (text, *text.splitlines()) if part.strip())


def _place_settled_below_province(run) -> bool:
    """A city or county is supported: a precise location the label does not
    state then adds nothing finer than the places settled."""
    return any((run.fields.get(key) or FieldValue()).state == ValueState.SUPPORTED for key in ("city", "county"))


def _settled_place_texts(run) -> list[tuple[str, str]]:
    """The texts of the settled country, province or state, county and city
    (agreement.PLACE_ORDER; settled as _claims_text says), each with its
    field: each value's literal, its value (normalized and parsed) and each
    reader's verbatim it keeps."""
    from .agreement import PLACE_ORDER

    human = human_keys(run)
    texts: list = []
    for key in PLACE_ORDER:
        value = run.fields.get(key)
        if value is not None and _claims_text(key, value, human):
            texts += [(key, text) for text in (value.literal, value.normalized, value.parsed,
                *value.verbatim_by_observation.values())]
    return [(key, text) for key, text in dict.fromkeys(texts) if isinstance(text, str) and text.strip()]


def _beside_places(text: str, places: Sequence[tuple[str, tuple[str, ...]]]) -> tuple[list[str], list[frozenset]]:
    """The text's words (georef_locality.fold: letter case, accents and
    punctuation aside) and, for each, the settled place fields whose whole
    text (`places`: each field with its text's words) is a run of words
    holding it; none for a word no settled place's text holds."""
    from specimen_digitization.application.georef_locality import fold

    words = fold(text).split()
    owners: list[frozenset] = [frozenset()] * len(words)
    for key, place in places:
        for start in range(len(words) - len(place) + 1):
            if tuple(words[start:start + len(place)]) == place:
                for i in range(start, start + len(place)):
                    owners[i] = owners[i] | {key}
    return words, owners


def _marks_a_settled_place(words: Sequence[str], owners: Sequence[frozenset], i: int) -> bool:
    """Whether word `i` is an administrative marker standing next to the
    settled place of the level it marks (admin_markers.ADMIN_MARKERS): the
    word right before it, or right after it, is that place's. One of
    AFTER_A_NAME ("Co.") counts only after the name ("Cook Co.", never "Co.
    Chirripo", a hill). "Boulder, Co." beside the settled city "Boulder"
    marks no settled county, and "Ionia Twp." marks nothing (a township is no
    marker)."""
    from .admin_markers import ADMIN_MARKERS, AFTER_A_NAME

    levels = ADMIN_MARKERS.get(words[i], frozenset())
    before = owners[i - 1] if i > 0 else frozenset()
    after = owners[i + 1] if i + 1 < len(words) and words[i] not in AFTER_A_NAME else frozenset()
    return bool(levels & (before | after))


def _only_markers(words: Sequence[str], owners: Sequence[frozenset]) -> bool:
    """Whether the words that are no settled place's (at least one) are all
    administrative markers next to the settled place of their level
    (_marks_a_settled_place)."""
    left = [i for i, inside in enumerate(owners) if not inside]
    return bool(left) and all(_marks_a_settled_place(words, owners, i) for i in left)


def _misread_marker(word: str, marker: str) -> bool:
    """Whether a reader's word may be a misreading of a marker: letters only,
    as long as the marker, one letter different ("mum" for "mun"), and no
    word or abbreviation for a place's feature (admin_markers.
    PLACE_FEATURE_WORDS: never "mtn", a mountain, "run", a stream, "cr" or
    "ck", a creek, or "mt" for "kt")."""
    from specimen_digitization.application.georef_locality import letters_apart

    from .admin_markers import PLACE_FEATURE_WORDS

    return (word.isalpha() and len(word) == len(marker) and letters_apart(word, marker) == 1
        and word not in PLACE_FEATURE_WORDS)


def _admin_markers(run, texts: Sequence[str]) -> str | None:
    """The administrative markers, as the texts write them ('"Mun."'), when
    they are all that these texts of a precise location give beyond the
    settled places; None otherwise. Each text's words are taken less every run of words
    that is a settled country's, province's or state's, county's or city's
    whole text (_settled_place_texts, _beside_places). What is left of at
    least one text is administrative markers only, each next to the settled
    place of the level it marks (_only_markers: "Mun." of "Yepocapa, Mun.
    Chimaltenango" beside the settled city "Yepocapa" and province
    "Chimaltenango", "Kreis" of "Kreis Ahrweiler" beside the settled county
    "Ahrweiler", "Pref." of "Nagano Pref."); what is left of every other
    text is nothing, markers only, or the same words with, in a marker's
    place, a word that may be a misreading of it (_misread_marker:
    105526328's 3B "Yepocapa, Mum." beside 3A's "Yepocapa, Mun.", but never
    "Yepocapa, Mtn."). Any other word left ("E. slope Mt. McKinley", "5 km
    N of", "Finca Moca", "Twp.") gives None: that text names a place of its
    own, or readers that differ on more than a marker."""
    from specimen_digitization.application.georef_locality import fold

    places = [(key, place) for key, place in dict.fromkeys((key, tuple(fold(text).split()))
        for key, text in _settled_place_texts(run)) if place]
    if not places:
        return None
    read = [(text, *_beside_places(text, places)) for text in texts]
    marked = [(text, words, owners) for text, words, owners in read if _only_markers(words, owners)]
    if not marked:
        return None
    for text, words, owners in read:
        if all(owners) or _only_markers(words, owners):
            continue
        if not any(len(words) == len(theirs) and all(word == their or (not inside and _misread_marker(word, their))
                for word, their, inside in zip(words, theirs, their_owners, strict=True))
                for _, theirs, their_owners in marked):
            return None
    shown = []
    for text, words, owners in marked:
        markers = {word for word, inside in zip(words, owners, strict=True) if not inside}
        written = [token.strip(",;:") for token in text.split() if fold(token) in markers]
        shown += written or sorted(markers)
    return ", ".join(f'"{marker}"' for marker in dict.fromkeys(shown))


# Why a precise location whose answer, beside the places settled, cites only
# an administrative marker has no value (_no_finer_place), and its reason
# when it clears as not on the label (mark_not_on_label).
NO_FINER_PLACE = ("The readings give no place finer than the places settled: beside them, they write only "
    "the administrative marker {markers}.")
NO_FINER_NOT_ON_LABEL = ("Not on the label: beside the places settled, the readings write only the "
    "administrative marker {markers}, no finer place.")


def _no_finer_place(run, profile: CollectionProfile, tasks_by_key: Mapping[str, FieldTask],
        applied: Mapping[str, FieldOutcome], added: Mapping[str, Sequence[str]], readings: Sequence[Reading], *,
        evidence: dict, decisions: dict[str, dict]) -> dict[str, str]:
    """A precise location researched in this attempt whose expert's answer
    (resolved, several_possibilities or sources_cannot_resolve; no failure,
    not the resolver's fallback, not finalized without a model call) cites
    texts each of which a reading writes, and that give nothing beyond the
    places settled but an administrative marker next to the settled place
    of its level, or readers that differ only in such a marker
    (_admin_markers: 105526328's options "Yepocapa, Mun." and "Yepocapa,
    Mum." beside the settled city "Yepocapa"), has no value on the label:
    it is not present, its reason says why (NO_FINER_PLACE), and the rows
    its settling added and the transcript_literal finding of a literal read
    from the transcript are dropped. Only when the profile lets the precise
    location clear as not on the label (not_on_label_keys); otherwise the
    answer is applied as before this check: a resolved answer settles as
    its text and may clear, and an unsettled one stays for review. Returns
    {"precise_location": the markers as written} for rule A
    (mark_not_on_label), or {}. Checked once every place is in."""
    key = "precise_location"
    task, outcome = tasks_by_key.get(key), applied.get(key)
    if (task is None or outcome is None or key not in not_on_label_keys(profile) or outcome.failure is not None
            or outcome.answer is None or outcome.fallback or outcome.finalized_without_model
            or outcome.answer.outcome == "label_lacks_value"):
        return {}
    answer = outcome.answer
    texts = [text for text in dict.fromkeys([answer.literal, *answer.options]) if text and text.strip()]
    if not texts or not all(any(text in reading.text for reading in readings) for text in texts):
        return {}
    markers = _admin_markers(run, texts)
    if markers is None:
        return {}
    dropped = set(added.get(key, ()))
    run.evidence[:] = [item for item in run.evidence if item.id not in dropped]
    for item_id in dropped:
        evidence.pop(item_id, None)
    run.findings[:] = [finding for finding in run.findings if finding.reason_code != transcript_code(key)]
    cited = [e for e in answer.source_evidence_ids if e in evidence and evidence[e].kind != "literal"]
    run.fields[key] = _unsettled(task, ValueState.NOT_PRESENT, cited=cited,
        reason=f"{NO_FINER_PLACE.format(markers=markers)} {answer.explanation}")
    decisions.setdefault(key, {})["refusal"] = "admin_marker_only"
    return {key: markers}


# Why a precise location whose settled literal is only the text of a settled
# place field has no value (_repeats_a_place), and its reason when it clears
# as not on the label (mark_not_on_label). The field is named as the app
# names it (prompts.FIELD_LABELS).
REPEATS_A_PLACE = ('The readings give no place finer than the places settled: "{literal}" is the text of the '
    "{field} field.")
REPEATS_NOT_ON_LABEL = ('Not on the label: beside the places settled, the readings write no finer place; '
    '"{literal}" is the text of the {field} field.')


def _repeats_a_place(run, tasks_by_key: Mapping[str, FieldTask], applied: Mapping[str, FieldOutcome],
        added: Mapping[str, Sequence[str]], readings: Sequence[Reading], *, evidence: dict,
        decisions: dict[str, dict]) -> dict[str, tuple[str, str]]:
    """A precise location settled in this attempt on its expert's resolved
    answer (supported, its literal the answer's) whose literal is only the
    text of a settled city, county, province or state, or country of the
    same reading: folded (georef_locality.fold: case, accents, punctuation
    and spacing aside; every word kept, unit words and markers too), it is
    that field's settled literal (_claims_text) where that literal stands as
    whole tokens in a reading the answer names, on one of that field's
    labels (_value_spans), or the verbatim that field keeps of such a
    reading. Such text is no
    locality more precise than the place fields, for which the precise
    location's brief asks label_lacks_value, so the value is made what that
    answer makes it: not present, citing the sources the answer cites, with
    a reason that names the field holding the text (REPEATS_A_PLACE, the
    city's before the county's, the province's and the country's), and the
    rows its settling added and the transcript_literal finding of a literal
    read from the transcript are dropped. Rule A then judges it as a field
    whose expert found none (mark_not_on_label). Whatever the profile's
    not-on-the-label list, as for label_lacks_value. A literal with any
    word beyond the place's text ("nr. Yepocapa", "5 km N of Yepocapa", "E.
    slope Mt. McKinley", "Yepocapa region", "Co. Chirripo", a hill beside the
    county Chirripo) is left as it is, and so is a precise location whose
    place did not settle; a marker beside a settled place is
    _no_finer_place's. Returns {"precise_location": (the literal, the field)}
    for rule A, or {}. Checked once every place is in."""
    from specimen_digitization.application.georef_locality import fold

    from .agreement import PLACE_ORDER
    from .prompts import FIELD_LABELS

    key = "precise_location"
    task, outcome = tasks_by_key.get(key), applied.get(key)
    value = run.fields.get(key)
    if (task is None or outcome is None or outcome.failure is not None or outcome.answer is None
            or outcome.answer.outcome != "resolved" or value is None or value.state != ValueState.SUPPORTED
            or not value.literal or value.literal != outcome.answer.literal):
        return {}
    answer = outcome.answer
    wanted = fold(answer.literal)
    named = [r for r in readings if r.name in answer.reading_names and answer.literal in r.text]
    if not wanted or not named:
        return {}
    human = human_keys(run)
    holder = None
    for other in reversed(PLACE_ORDER):
        place = run.fields.get(other)
        if place is None or not _claims_text(other, place, human):
            continue
        texts = [place.verbatim_by_observation.get(r.observation_id) for r in named]
        if _value_spans(place, named, evidence):
            texts.append(place.literal)
        if any(text and fold(text) == wanted for text in texts):
            holder = other
            break
    if holder is None:
        return {}
    dropped = set(added.get(key, ()))
    run.evidence[:] = [item for item in run.evidence if item.id not in dropped]
    for item_id in dropped:
        evidence.pop(item_id, None)
    run.findings[:] = [finding for finding in run.findings if finding.reason_code != transcript_code(key)]
    cited = [e for e in answer.source_evidence_ids if e in evidence and evidence[e].kind != "literal"]
    field = FIELD_LABELS.get(holder, holder)
    run.fields[key] = _unsettled(task, ValueState.NOT_PRESENT, cited=cited,
        reason=f"{REPEATS_A_PLACE.format(literal=answer.literal, field=field)} {answer.explanation}")
    decisions.setdefault(key, {})["refusal"] = "place_text_only"
    return {key: (answer.literal, field)}


def not_on_label_excerpt(key: str, readings: Sequence[Reading], *, markers: bool = False,
        place: bool = False) -> str:
    """The excerpt of a field's not-on-the-label check row: the readings it
    names, by name and observation. For a precise location whose readings
    write only an administrative marker beside the places settled
    (_no_finer_place), or whose settled literal is only a settled place's
    text (`place`: _repeats_a_place), it says so instead."""
    names = ", ".join(r.name for r in readings)
    said = (f"beside the places settled, the readings {names} write only an administrative marker" if markers
        else f"beside the places settled, the readings {names} write no finer place" if place
        else f"none of the readings {names} states it and its expert found none")
    return (f"{key}: not on the label; {said}\n"
        + "readings: " + "; ".join(f"{r.name} {r.observation_id}" for r in readings))


def mark_not_on_label(run, profile: CollectionProfile, tasks: Sequence[FieldTask],
        outcomes: Sequence[FieldOutcome], *, readings: Sequence[Reading] | None = None,
        asset_id: str | None = None, blobs=None, why: dict[str, str] | None = None,
        no_finer: Mapping[str, str] | None = None,
        repeated: Mapping[str, tuple[str, str]] | None = None) -> list[str]:
    """Owner decision A (2026-10-09): a field on the profile's list
    (not_on_label_keys) that a person has not decided, researched in this
    attempt, is marked "not on the label" when all of these hold:
    1. its expert answered label_lacks_value, with no failure, and the field
       was not finalized without a model call (a fallback answer is
       sources_cannot_resolve, so it never qualifies); or, for a precise
       location, its expert's answer gives only an administrative marker
       beside the places settled (`no_finer`: _no_finer_place), or its
       settled literal was only a settled place's text (`repeated`:
       _repeats_a_place), with no failure and not finalized without a model
       call;
    2. its value is still not present (a value derive.fill derived is kept);
    3. label coverage is confirmed, every label has two or more readings and
       every reading has text (_whole_label_read);
    4. no part of any label is unreadable (_whole_label_read);
    5. the organiser found no text for it (_organiser_texts), judged after
       every value of this attempt is made: a text counts as absent when it
       is, where it stands, the literal a field of another kind settled
       (_held_by_another_kind: letter case and surrounding punctuation
       aside; this attempt's, an earlier attempt's or a person's value;
       _claims_text), so 105526328's "trap", which the organiser offered as
       the habitat, is absent once the collecting method settles on "trap"
       (and the method's "trap" once the habitat settles on it); text only
       inside a longer settled literal still counts; for a county, a city
       or a precise location, a text also counts as absent when its whole
       words, by the place comparison key, are a run of the words of
       another supported place field's literal, and it writes no unit word
       of its own (_inside_a_settled_place); and
       for a precise location, the texts left count as absent when, beside
       the places settled, they write only an administrative marker, or
       readers differ only in one (_admin_markers);
    6. for an elevation, no reading writes an elevation (_elevation_written);
    7. for a precise location, a city or a county is supported.
    The value then cites one check row (kind "derived", locator
    "check:not_on_label") naming every reading of the run, and its reason
    starts "Not on the label:" (for a precise location in `no_finer`, the
    row's excerpt and record and the reason say the readings write only an
    administrative marker: NO_FINER_NOT_ON_LABEL; for one in `repeated`,
    they say the readings write no finer place, the record and the reason
    naming the field that holds its text: REPEATS_NOT_ON_LABEL). The row has no
    observation_ids: one row may not cite readings of several labels
    (integrity.verify_evidence), so its excerpt and stored record name them
    (not_on_label_excerpt). A row an
    earlier attempt wrote is dropped from a field researched again. Returns
    the keys marked; ``why`` collects, as a code, why each field whose
    expert answered label_lacks_value was not marked (trace_fields)."""
    readings = run_readings(run) if readings is None else readings
    tasks_by_key = {task.key: task for task in tasks}
    by_key = {o.key: o for o in outcomes if o.key in tasks_by_key}
    human = human_keys(run)
    why = {} if why is None else why
    no_finer = {} if no_finer is None else no_finer
    repeated = {} if repeated is None else repeated
    lacking = {key for key, o in by_key.items() if key not in human and o.failure is None and o.answer is not None
        and (o.answer.outcome == "label_lacks_value" or key in no_finer or key in repeated)
        and not o.finalized_without_model}
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
        why.update(dict.fromkeys(lacking, "label_not_read_whole" if allowed else "not_listed"))
        return []
    elevation = claims = None
    marked = []
    for key in field_keys(profile):
        outcome, value = by_key.get(key), run.fields.get(key)
        if key not in allowed or key in human or outcome is None or value is None:
            if key in lacking:
                why[key] = "not_listed"
            continue
        answer = outcome.answer
        if key not in lacking:
            continue
        if value.state != ValueState.NOT_PRESENT or any((value.literal, value.parsed, value.normalized,
                value.authority_id, value.authority_identity, value.verbatim_by_observation)):
            why[key] = "value_present"
            continue
        claims = _settled_claims(run, readings) if claims is None else claims
        found = [text for text, spans in _organiser_texts(tasks_by_key[key], readings)
            if not (key in INSIDE_A_PLACE and _inside_a_settled_place(run, key, text))
            and _held_by_another_kind(key, text, spans, claims) is None]
        if found and not (key == "precise_location" and _admin_markers(run, found) is not None):
            why[key] = "organiser_found_text"
            continue
        if key in ELEVATION_FIELDS:
            elevation = _elevation_written(run, readings) if elevation is None else elevation
            if elevation:
                why[key] = "elevation_written"
                continue
        if key == "precise_location" and not _place_settled_below_province(run):
            why[key] = "no_city_or_county_settled"
            continue
        markers, repeats = no_finer.get(key), repeated.get(key)
        record = json.dumps({"field_key": key, "check": "not_on_label", "readings": [
            {"name": r.name, "region_id": r.region_id, "observation_id": r.observation_id,
             "input_source": r.input_source} for r in readings],
            **({"admin_markers": markers} if markers is not None else {}),
            **({"place_field": repeats[1]} if repeats is not None else {})}, sort_keys=True).encode()
        row = Evidence(kind="derived", asset_id=asset_id, source=SOURCE, locator=NOT_ON_LABEL_CHECK,
            excerpt=not_on_label_excerpt(key, readings, markers=markers is not None, place=repeats is not None),
            raw_ref=blobs.put(record) if blobs is not None else None,
            digest=hashlib.sha256(record).hexdigest() if blobs is not None else None)
        run.evidence.append(row)
        value.evidence_ids.append(row.id)
        value.evidence_relations[row.id] = "supports"
        said = (NO_FINER_NOT_ON_LABEL.format(markers=markers) if markers is not None
            else REPEATS_NOT_ON_LABEL.format(literal=repeats[0], field=repeats[1]) if repeats is not None
            else NOT_ON_LABEL_REASON)
        value.reason = f"{said} {answer.explanation}".strip()
        marked.append(key)
    return marked


def not_on_label(key: str, value: FieldValue, run, evidence: Mapping[str, Evidence],
        allowed: frozenset[str]) -> bool:
    """Whether a field clears as "not on the label" (mark_not_on_label),
    checked on the stored value: the key is on the profile's list
    (`allowed`); the value is not present, with no literal, parsed,
    normalized or authority value and no reader's text; it cites as support
    a not-on-the-label check row whose readings are the run's current
    readings (not_on_label_excerpt; for a precise location, any of its three);
    and, for a precise location, a city or a county is still supported. An
    older not-present value, with no such row, never clears."""
    if key not in allowed or value.state != ValueState.NOT_PRESENT:
        return False
    if any((value.literal, value.parsed, value.normalized, value.authority_id, value.authority_identity,
            value.verbatim_by_observation)):
        return False
    if key == "precise_location" and not _place_settled_below_province(run):
        return False
    readings = run_readings(run)
    expected = {not_on_label_excerpt(key, readings, markers=markers, place=place)
        for markers, place in (((False, False), (True, False), (False, True)) if key == "precise_location"
            else ((False, False),))}
    for evidence_id in value.evidence_ids:
        row = evidence.get(evidence_id)
        if (row is not None and value.evidence_relations.get(evidence_id) == "supports" and row.kind == "derived"
                and row.source == SOURCE and row.locator == NOT_ON_LABEL_CHECK and row.excerpt in expected):
            return True
    return False


# ---- each field's trace ---------------------------------------------------

# agreement's reasons for refusing a resolved answer, by constant name.
REFUSALS = ("DIFFER", "LABELS_DIFFER", "NOT_DECIDED", "NOT_CANDIDATE", "PART_OF_NAME", "DOUBTFUL_GENUS",
    "NO_PLACE", "EXPANSIONS_DIFFER", "NO_PARENTS", "NO_COUNTRY", "NOT_IN_COUNTRY", "NOT_IN_PROVINCE", "NEAR_UNFIT",
    "NOT_EVERY_READER", "PART_OF_RANGE", "UNIT_DIFFERS", "NO_UNIT", "A_DISTANCE", "HOLDS_AN_ELEVATION",
    "HOLDS_A_DATE", "HOLDS_A_RANGE", "FIRST_LEVEL_TOO", "NO_PROVINCE", "IS_THE_PROVINCE")
# A lookup's status as a field's trace names it. Logfire's default scrubber
# replaces any attribute whose value holds "auth" or "credential", so the two
# refusals (HTTP 401 and 403) are renamed.
TRACE_STATUS = {LookupStatus.AUTHENTICATION: "login_refused", LookupStatus.AUTHORIZATION: "access_refused"}


def refusal_code(reason: str) -> str:
    """A refusal's reason (one of agreement's fixed texts) as its code, the
    constant's name in lower case ("no_place"); "other" for any other text."""
    from . import agreement

    return next((name.lower() for name in REFUSALS if getattr(agreement, name) == reason), "other")


def trace_fields(run, tasks: Sequence[FieldTask], outcomes: Sequence[FieldOutcome], calls: Sequence[SourceCall],
        decisions: Mapping[str, Mapping[str, str]]) -> None:
    """One FIELD_SPAN span per field of this attempt, inside the step's SPAN:
    what the step decided after the field's expert, beside the expert's own
    agent run, so a person can build evals from the traces. Codes only: the
    field key; the expert's outcome, its failure, whether the answer is the
    resolver's fallback and whether the field was finalized without a model
    call; the value's state and layer and the run's reason codes for it; the
    check that refused a resolved answer (or, "admin_marker_only", found
    that a precise location's answer gives no place: _no_finer_place; or,
    "place_text_only", that its settled literal is only a settled place's
    text: _repeats_a_place) and
    the rule that decided the field (``decisions``: apply_outcomes); each
    lookup as source and status, the sources that answered and those that
    could not be reached. The literal, the value, the authority and the
    reason, which may quote the labels, are added only when the process
    captures approved content (provider_privacy.approved_content_configured)."""
    from specimen_digitization.application.domain import OPERATIONAL
    from specimen_digitization.provider_privacy import approved_content_configured

    content = approved_content_configured()
    by_key = {outcome.key: outcome for outcome in outcomes}
    made: dict[str, list[SourceCall]] = {}
    for call in calls:
        made.setdefault(call.field_key, []).append(call)
    for task in tasks:
        outcome = by_key.get(task.key)
        if outcome is None:
            continue
        value = run.fields.get(task.key) or FieldValue()
        decision = decisions.get(task.key, {})
        lookups = made.get(task.key, [])
        attributes = {
            "field_key": task.key,
            "expert_outcome": outcome.answer.outcome if outcome.answer is not None else "none",
            "failure": outcome.failure or "none",
            "fallback": outcome.fallback,
            "finalized_without_model": outcome.finalized_without_model,
            "model_calls": outcome.model_calls,
            "state": str(value.state),
            "layer": value.layer or "none",
            "reason_codes": [reason for reason in run.reasons if reason.endswith(":" + task.key)
                or (task.key == "taxon" and reason == "taxonomy_unresolved")],
            "refusal": decision.get("refusal", "none"),
            "rule": decision.get("rule", "none"),
            "lookups": [f"{call.source_id}:{TRACE_STATUS.get(call.answer.status, call.answer.status.value)}"
                for call in lookups],
            "sources_answered": sorted({call.source_id for call in lookups if call.answer.status not in OPERATIONAL}),
            "sources_unreachable": list(outcome.unreachable),
        }
        if content:
            # "source_record" is the value's authority id, under a name the
            # scrubber keeps (TRACE_STATUS).
            attributes.update(literal=value.literal or "", value=value.normalized or value.parsed or "",
                source_record=value.authority_id or "", reason=value.reason or "")
        with logfire.span(FIELD_SPAN, **attributes):
            pass


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
        run) -> bool:
    """Whether the taxon is owner decision B's unmatched name
    (_unmatched_taxon), checked on the stored value: supported, its literal a
    name with no genus (checks.names_no_genus) that the label, the `run`'s
    readings (run_readings), writes with no genus beside it
    (checks.label_names_no_genus), with no part of a label that writes it
    unreadable (_code_label_unreadable) and no sign of a doubtful or
    unreadable name anywhere on the specimen (_doubt_on_the_labels), as
    written (parsed is the literal or empty), with no normalized value or
    authority, in the settled layer,
    citing as support the check row for that literal and the GBIF no-name
    lookup of the run that the row names; and no GBIF lookup the run stores
    shows a genus (_lookup_found_a_genus: candidates, or a query that names
    a genus) or asked anything but the code itself
    (_lookup_asked_another_name; the step's own no-name lookup aside), so a
    value stored before those rules does not clear either. A taxon with a
    genus never is."""
    from .checks import label_names_no_genus, morphocode

    literal = taxon.literal
    code = morphocode(literal)
    readings = run_readings(run)
    if (taxon.state != ValueState.SUPPORTED or code is None
            or not label_names_no_genus(code, [r.text for r in readings]) or _code_label_unreadable(run, readings, code)
            or _doubt_on_the_labels(run, readings)
            or any(_lookup_found_a_genus(lookup) or _lookup_asked_another_name(lookup, literal) for lookup in lookups)
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
    - 203-217: a label whose first pass the workflow gave up on
      (first_pass.given_up_regions) is unresolved_transcription however its
      fields settle: no first pass compared its readings.
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
    given_up = given_up_regions(run)
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
            # A label whose first pass was given up on (workflow, first_pass.give_up)
            # was never compared: its transcript stays for a person to resolve,
            # however its fields settle.
            if region.id in given_up or not drawn or any(run.fields[key].state != ValueState.SUPPORTED
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
            or taxon_unmatched(taxon, evidence, run.lookups, run=run)):
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
    a derived value are resolved; an outage, a model failure or a timeout is
    operational, except on the step's last attempt (last_attempt), which no
    retry would follow, a source still unreachable and a field that ran out
    of time (REVIEW_ON_LAST_ATTEMPT); a model failure is operational on every
    attempt. A field with no approved authority is its nonblocking exception;
    anything else that did not settle waits on a person (a spent budget, and
    that last unreachable source or timeout too: failures are graceful).
    """
    by_key = {outcome.key: outcome for outcome in outcomes}
    final = last_attempt(run)
    states = {}
    for key in field_keys(profile):
        outcome, value = by_key.get(key), run.fields.get(key) or FieldValue()
        if outcome is None or (value.state == ValueState.SUPPORTED and value.layer == "derived"):
            states[key] = RESOLVED
        elif outcome.failure in RETRYABLE and not (final and outcome.failure in REVIEW_ON_LAST_ATTEMPT):
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
    retryable blocker the workflow schedules a retry on, every settled field
    kept; on the step's last attempt a source still unreachable and a field
    that ran out of time are for a person instead (work_states), and only a
    model failure blocks.
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

    def give_up(self, workflow, principal, specimen, code: str) -> None:
        """Give field research up unsent: the run's own limits other than money
        (``code``, workflow.RESEARCH_LIMITS) leave no room for another attempt.

        No expert, source or meter is started and nothing is reserved, paid
        for or recorded as a paid call; the fields an earlier attempt settled
        are kept. Every field still to research is unresolved, with the
        run_limit reason, and the step's own rules decide the record
        (finalize_fields): a field the harness could not check waits on a
        person, so the record goes to review. One warning finding records the
        limit. The identified-by IRN keeps its nonblocking exception, as when
        research runs.
        """
        from .location_reassessment import KEY as REASSESSMENT

        run = specimen.run
        try:
            profile = profile_of(run)
            if REASSESSMENT in run.dependencies:
                # The workflow can give up before incrementing the attempt.
                # No explicit reassessment was sent: leave every field intact,
                # rather than falling back to ordinary unresolved-field work.
                run.dependencies.pop(REASSESSMENT, None)
                finalize_fields(run, profile, (), specimen=specimen, blobs=workflow.blobs,
                    today=workflow.clock().date())
                self._retained_reassessment(run, {f"run_limit:{code}"})
                return
            prepared = build_tasks(run, profile)
            outcomes = [
                FieldOutcome(task.key, FieldAnswer(outcome="sources_cannot_resolve", explanation=IRN_EXPLANATION),
                    finalized_without_model=True)
                if task.key in NO_APPROVED_AUTHORITY else FieldOutcome(task.key, None, failure="run_limit")
                for task in prepared[1]
            ]
            run.findings = [f for f in run.findings if f.rule_id != GIVEN_UP] + [
                RunFinding(rule_id=GIVEN_UP, rule_version=GIVEN_UP_RULES, severity="warning",
                    reason_code=f"{GIVEN_UP}:{code}")]
            decisions: dict[str, dict] = {}
            apply_outcomes(run, profile, prepared[1], outcomes, blobs=workflow.blobs, calls=(),
                asset_id=specimen.asset.id, decisions=decisions)
            finalize_fields(run, profile, outcomes, specimen=specimen, blobs=workflow.blobs,
                today=workflow.clock().date())
        except EvidenceIntegrityError as error:
            raise OperationalBlock(str(error)) from error
        trace_fields(run, prepared[1], outcomes, (), decisions)

    def run(self, workflow, principal, specimen, *, cap_micros: int, deadline_seconds: float) -> None:
        from .location_reassessment import KEY as REASSESSMENT, commit, working_run

        run = specimen.run
        reassessment_marker = copy.deepcopy(run.dependencies.get(REASSESSMENT))
        research_run = working_run(run)
        route = None
        try:
            # Nothing is sent before the research below: an error here is the
            # step's setup, never an unknown outcome, and costs nothing.
            profile = profile_of(run)
            route = profile.harness_route
            meter = self.meter_factory(max(0, cap_micros), _route_price(profile, route))
            prepared = build_tasks(research_run, profile)
            resolver = self.resolver_factory(research_run, profile, meter)
        except OperationalBlock:
            record_cost(run, route, reserved=cap_micros, spent=0, outcome="failed")
            raise
        except Exception as error:
            record_cost(run, route, reserved=cap_micros, spent=0, outcome="failed")
            raise OperationalBlock("field_research_unconfigured") from error
        calls: list[SourceCall] = []
        outcomes = None
        decisions: dict[str, dict] = {}
        # Research, then each field's decision (trace_fields), in one span.
        with logfire.span(SPAN) as span:
            try:
                outcomes = asyncio.run(self._research(research_run, profile, prepared, resolver, workflow.blobs,
                    calls, self._bound(deadline_seconds), span))
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
                apply_outcomes(research_run, profile, prepared[1], outcomes, blobs=workflow.blobs, calls=calls,
                    asset_id=specimen.asset.id, decisions=decisions)
                retained = commit(run, research_run, decisions=decisions) if research_run is not run else set()
                blocker = finalize_fields(run, profile, outcomes, specimen=specimen, blobs=workflow.blobs,
                    today=workflow.clock().date())
                self._retained_reassessment(run, retained)
                if blocker is not None and research_run is not run and not last_attempt(run):
                    # The ordinary bounded operational retry keeps this explicit
                    # family's scope; it must not expand to unrelated fields.
                    run.dependencies[REASSESSMENT] = {
                        **reassessment_marker, "attempt": run.attempts[STEP] + 1}
            except EvidenceIntegrityError as error:
                raise OperationalBlock(str(error)) from error
            trace_fields(run, prepared[1], outcomes, calls, decisions)
        if blocker is not None:
            if run.paid_calls and run.paid_calls[-1]["step"] == STEP:
                run.paid_calls[-1]["outcome"] = "failed"
            raise AdapterFailure(blocker, BLOCKER_STATUS[blocker])

    @staticmethod
    def _retained_reassessment(run, retained) -> None:
        if retained:
            run.reasons = list(dict.fromkeys((*run.reasons,
                *(f"location_reassessment_unconfirmed:{key}" for key in sorted(retained)))))
            if run.blocker is None:
                run.disposition = Disposition.REVIEW

    def _bound(self, deadline_seconds: float) -> float:
        from specimen_digitization.application.worker_deadline import current_deadline

        bound = deadline_seconds - self.margin_seconds
        deadline = current_deadline()
        if deadline is not None:
            bound = min(bound, deadline.remaining() - self.margin_seconds)
        return max(1.0, bound)

    async def _research(self, run, profile, prepared, resolver, blobs, calls, bound, span=None):
        async with self.tools_factory(run, profile, blobs) as tools:
            return await research_fields(run, profile, resolver=resolver, tools=tools,
                concurrency=self.concurrency, deadline_seconds=bound, prepared=prepared, calls=calls, span=span)


def _production_resolver(run, profile, meter):
    """The harness route's model through the Hugging Face gateway, as the
    ordinary extraction call builds its model (production.py _extract_direct).
    Under PrivateProviderModel, ClientTimeouts keeps the gateway's own
    timeout (MODEL_TIMEOUT_SECONDS) a TimeoutError, so a request it stops is
    the field's timeout."""
    if os.getenv("SPECIMEN_APPROVED_INFERENCE") != "true":
        raise OperationalBlock("provider_data_policy_and_spending_approval_required")
    from specimen_digitization.model_gateway import HuggingFaceModelGateway
    from specimen_digitization.provider_privacy import PrivateProviderModel

    from .experts import ClientTimeouts, make_resolver

    gateway = HuggingFaceModelGateway(timeout_seconds=MODEL_TIMEOUT_SECONDS)
    route = profile.harness_route
    gateway.route(route)  # An unknown route fails here, before any request.
    return make_resolver(model_factory=lambda: PrivateProviderModel(ClientTimeouts(gateway.model_for(route))),
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
