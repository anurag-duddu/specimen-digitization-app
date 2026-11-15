"""The units path's one re-ask before a mark (docs/execution/units/PLAN.md, WP 2.3c; spec
docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4, "The check stage").

The owner typed on 2026-11-14: "4 shouldn't be flagged. It should be caught and handled. Goal isn't
to throw everything at the user it is to help by being in in autonomy as much as possible." and
"Harness needs to work and do its magic".

After every expert has answered (step.research_fields), `again` applies this attempt's outcomes on
a copy of the run (step.apply_outcomes, with no blob written: _Reads) and reads which fields a
check of the stage marks (ontology_checks.stage's decisions, STAGE_CHECK and STAGE_SAW). Each such
field whose check is one of REASK_CHECKS and whose value its expert settled in this attempt (an
answer of the expert's own, neither a person's value, nor a derived one, nor one the location
reconciliation settled) is put back to its expert once: the same task, readings and context, its
request carrying one sentence that names the failed check and what the check saw (FieldTask.reask,
experts.REASK_PREFIX). Its answer goes through every check again: the expert's own, then, applied
with every other outcome on a copy of the run, the step's refusals, the settlement rule and the
stage. It is kept when its field settles (supported, from the label) and the stage, run again,
marks neither it nor any field it did not mark before the re-ask (G51's round 1 on PR #439, the
coordinator's ruling); the settlement rule then clears or marks it as it would any answer, and its
reason names the re-ask (FieldOutcome.reasked). Otherwise the field keeps the answer it had, applied as without
the re-ask, so it is marked as the stage marks it today; the lookups the re-ask made are recorded
and decide nothing (step.apply_outcomes' `unused`).

A field is re-asked at most once per attempt: `again` runs once per attempt (step.FieldResearchStep),
asks each field once, and never asks a field whose outcome a re-ask gave (FieldOutcome.reasked). A
field a retry does not research again (step.build_tasks leaves a settled field as it is) is not
re-asked. The re-asks share the run's meter and run within the time research leaves (`seconds`);
one that fails, runs out of time or cannot be paid for keeps the field's earlier answer. Nothing
here runs on the old path.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import replace

from specimen_digitization.application.domain import ValueState

from .contracts import FieldOutcome, FieldResolver, FieldTask, SourceTools
from .ontology_checks import (
    CHECK_STAGE,
    DATE_ORDER,
    PLACE_CHAIN,
    PLACE_WITHIN,
    PRECISE_LOCATION_EXTENT,
    STAGE_CHECK,
    STAGE_SAW,
)

# The checks of the stage whose failure puts the field back to its expert once. place_parents_derived
# marks a derived value, which no expert settled.
REASK_CHECKS = frozenset({PRECISE_LOCATION_EXTENT, PLACE_WITHIN, PLACE_CHAIN, DATE_ORDER})
# The sentence the expert's request carries (FieldTask.reask), and the one a kept answer's reason
# ends with (FieldOutcome.reasked).
ASKED = ("Your answer {literal!r} failed the check {check}: {saw}. Answer once more; your answer goes through every "
    "check again.")
REASKED = "Re-asked once, after the check {check} failed on the expert's answer {literal!r}: {saw}."


class _Reads:
    """The record's blob store, read only: what a trial application writes stays in memory."""

    def __init__(self, store):
        self.store, self.blobs = store, {}

    def put(self, data: bytes) -> str:
        ref = hashlib.sha256(data).hexdigest()
        self.blobs[ref] = data
        return ref

    def get(self, ref: str) -> bytes:
        return self.blobs[ref] if ref in self.blobs else self.store.get(ref)


def _trial(run, profile, tasks: Sequence[FieldTask], outcomes: Sequence[FieldOutcome], *, blobs, calls, asset_id):
    """The outcomes applied as step.apply_outcomes applies them, on a deep copy of the run, writing no
    blob and making no Logfire event (step._FIRST_PASS); the copy and the decisions it gave."""
    from . import step

    copy = run.model_copy(deep=True)
    decisions: dict[str, dict] = {}
    marker = step._FIRST_PASS.set(True)
    try:
        step.apply_outcomes(copy, profile, tasks, outcomes, blobs=_Reads(blobs) if blobs is not None else None,
            calls=calls, asset_id=asset_id, decisions=decisions)
    finally:
        step._FIRST_PASS.reset(marker)
    return copy, decisions


def _marked(copy, key: str) -> bool:
    return any(finding.rule_id == CHECK_STAGE and finding.field_key == key for finding in copy.findings)


def _stage_marks(copy) -> frozenset[str]:
    """The fields a check of the stage marks on a trial's copy of the run."""
    return frozenset(finding.field_key for finding in copy.findings if finding.rule_id == CHECK_STAGE)


def _settles(copy, key: str) -> bool:
    from .step import SETTLED_LAYERS

    value = copy.fields.get(key)
    return value is not None and value.state == ValueState.SUPPORTED and value.layer in SETTLED_LAYERS


def _expert_answered(outcome: FieldOutcome) -> bool:
    """An answer of the expert's own: no failure, not the resolver's fallback, not finalized without
    a model call, and no re-ask's."""
    return (outcome.failure is None and outcome.answer is not None and not outcome.fallback
        and not outcome.finalized_without_model and outcome.reasked is None)


def to_ask(run, copy, decisions: Mapping[str, Mapping[str, str]], outcomes: Sequence[FieldOutcome]) -> dict[str, tuple]:
    """The fields to put back to their expert, from a trial application (`copy`, `decisions`): each
    one a check of REASK_CHECKS marks whose value its expert settled in this attempt, with the check,
    what it saw and the literal it marked."""
    from .step import human_keys

    human = human_keys(run)
    found = {}
    for outcome in outcomes:
        key = outcome.key
        decision = decisions.get(key, {})
        if (key in human or not _expert_answered(outcome) or decision.get(STAGE_CHECK) not in REASK_CHECKS
                or decision.get("rule") == "location_reconciliation" or not _settles(copy, key)
                or not _marked(copy, key)):
            continue
        found[key] = (decision[STAGE_CHECK], decision.get(STAGE_SAW, ""), copy.fields[key].literal)
    return found


async def again(run, profile, prepared, outcomes: Sequence[FieldOutcome], *, resolver: FieldResolver,
        tools: SourceTools, calls: list, blobs=None, asset_id: str | None = None,
        seconds: float | None = None) -> tuple[list[FieldOutcome], list]:
    """This attempt's outcomes after the units path's one re-ask (module docstring), and the lookups
    of the re-asks whose answers were not kept (step.apply_outcomes' `unused`). The lookups of a kept
    answer join `calls`. The outcomes as they are on the old path, when nothing is to be asked, or
    when a trial application fails."""
    from . import step

    outcomes = list(outcomes)
    if not step.units_path(run) or (seconds is not None and seconds <= 0):
        return outcomes, []
    readings, tasks, context = prepared
    tasks_by_key = {task.key: task for task in tasks}
    try:
        copy, decisions = _trial(run, profile, tasks, outcomes, blobs=blobs, calls=calls, asset_id=asset_id)
    except Exception:  # noqa: BLE001 - a trial that fails asks nothing; the step applies the outcomes itself
        step.LOGGER.warning("field_research re-ask trial failed")
        return outcomes, []
    asked = {key: item for key, item in to_ask(run, copy, decisions, outcomes).items() if key in tasks_by_key}
    if not asked:
        return outcomes, []
    before = _stage_marks(copy)
    made: dict[str, list] = {key: [] for key in asked}
    jobs = {key: asyncio.create_task(step._resolve(resolver,
        replace(tasks_by_key[key], reask=ASKED.format(literal=literal, check=check, saw=saw)), readings, context,
        step._RecordedTools(tools, made[key]))) for key, (check, saw, literal) in asked.items()}
    _, late = await asyncio.wait(jobs.values(), timeout=seconds)
    for job in late:
        job.cancel()
    if late:
        await asyncio.gather(*late, return_exceptions=True)
    answers = {key: job.result() for key, job in jobs.items() if job not in late}
    by_key = {outcome.key: outcome for outcome in outcomes}
    kept = {key for key, answer in answers.items() if answer.failure is None and answer.answer is not None
        and not answer.fallback and answer.answer.outcome == "resolved"}

    def given(key: str) -> FieldOutcome:
        check, saw, literal = asked[key]
        answer = answers[key]
        return replace(answer, reasked=REASKED.format(check=check, literal=literal, saw=saw),
            model_calls=by_key[key].model_calls + answer.model_calls,
            cost_micros=by_key[key].cost_micros + answer.cost_micros)

    # Each kept answer goes through every check again, applied with the others; one that does not
    # settle, or that a check of the stage marks, is not kept, and the rest are tried again. Where the
    # stage marks a field it did not mark before the re-ask, no answer of this try is kept.
    while kept:
        trial = [given(outcome.key) if outcome.key in kept else outcome for outcome in outcomes]
        try:
            copy, _ = _trial(run, profile, tasks, trial, blobs=blobs,
                calls=[*calls, *(call for key in kept for call in made[key])], asset_id=asset_id)
        except Exception:  # noqa: BLE001 - an answer that cannot be applied is not kept
            step.LOGGER.warning("field_research re-ask trial failed")
            kept = set()
            break
        failing = {key for key in kept if not _settles(copy, key) or _marked(copy, key)}
        if _stage_marks(copy) - before:
            failing = set(kept)
        if not failing:
            break
        kept -= failing
    final = []
    for outcome in outcomes:
        key = outcome.key
        if key in kept:
            final.append(given(key))
        elif key in answers:
            final.append(replace(outcome, model_calls=outcome.model_calls + answers[key].model_calls,
                cost_micros=outcome.cost_micros + answers[key].cost_micros))
        else:
            final.append(outcome)
    for key in kept:
        calls.extend(made[key])
    return final, [call for key, found in made.items() if key not in kept for call in found]
