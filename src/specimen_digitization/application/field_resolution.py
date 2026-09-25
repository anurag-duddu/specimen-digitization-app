"""Deterministic field resolution for the stage 7 harness (HARNESS.md section 9).

The harness agent proposes each field's literal as each handed reading has it
and calls the profile's tools; this module decides every field from the
recorded outcomes of those calls only, never from the agent's claims, and never
invents a value (HAR-019).

- A decided transcript's literal is the field's verbatim (G27). When its lookup
  fails, a raw reading's differing literal may settle the value (G20); the
  verbatim stays, and the confirmed reading is only the settled value's
  provenance.
- With no decided transcript every reading's literal is tried; the field clears
  only when every success names the same value, and then keeps each reader's
  literal and chooses none (G19, G27, G28).
- Only a `success` settles; an operational outcome blocks the run (QUE-005)
  instead of deciding the field.
- A numeric date takes one of its readings only when the dates in every
  reading of the specimen fix one order (G29, G33).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from .domain import (
    OPERATIONAL,
    Evidence,
    FieldValue,
    LookupStatus,
    RunFinding,
    ValueState,
)

DECIDED, RAW = "decided_transcript", "raw_reading"
RULE_VERSION = "field-resolution-v1"
NUMERIC_ORDERS = frozenset({"month-day-year", "day-month-year"})
BLOCKED_REASONS = frozenset(f"lookup_{status.value}" for status in OPERATIONAL)
Relation = Literal["decides", "supports", "contradicts"]


@dataclass(frozen=True)
class Reading:
    """One text the harness reads for a region: the decided transcript, or a
    raw reading (handed over when the first pass picked none, or read for the
    G20 fallback)."""

    region_id: str
    observation_id: str
    role: str
    text: str


@dataclass(frozen=True)
class Called:
    """What one recorded tool call on one literal settles, as a field sees it.
    `normalized` is the settled name only: GBIF's, or for Google the reader's
    literal the lookup matched exactly, never Google's (G26, rule 1.6).
    `evidence` holds only a success's evidence ids, each with its relation
    (G23: GBIF decides, Global Names Verifier and Catalogue of Life support or
    contradict; Google only supports, rule 1.6); `warnings` maps each warning
    code to the evidence behind it. For a date the wrapper may report the one
    reading the specimen's dates fix (G29); the recorded call keeps its own
    outcome."""

    outcome: LookupStatus
    tool: str
    authority_id: str | None = None
    parsed: str | None = None
    normalized: str | None = None
    # An open source's name, record and credit (PLAN 4.8); never Google's (G26).
    authority_identity: Mapping[str, str | None] | None = None
    precision: str | None = None
    century_rule: str | None = None
    evidence: Mapping[str, Relation] = field(default_factory=dict)
    warnings: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def settled(self) -> tuple[str | None, str | None]:
        """What two successes must share to agree."""
        return self.authority_id, self.parsed


FieldCall = Callable[[str, Reading], Called]


class Resolver:
    """Resolves one specimen's fields; collects the literal evidence and the
    findings it creates, and the first operational block."""

    def __init__(self, readings: Sequence[Reading], asset_id: str, blobs=None) -> None:
        self.readings = {r.observation_id: r for r in readings}
        self.asset_id = asset_id
        self.blobs = blobs  # Stores each literal evidence item's record.
        self.evidence: list[Evidence] = []
        self.findings: list[RunFinding] = []
        self.blocker: str | None = None
        self._literals: set[str] = set()  # Literal evidence ids.
        # The raw reading that settled a decided label by the fallback (G20),
        # by field and region, which a field on several labels names (G32).
        self._confirmed: dict[tuple[str, str | None], str] = {}

    def transcribed(self, key: str, literals: Mapping[str, str | None]) -> FieldValue:
        """A field no tool checks: its literal as written (PRD 12.4). On two
        labels, their texts must agree (G32)."""
        regions = [self._transcribed_one(key, r) for r in self._by_region(literals)]
        return self._labels(key, regions, lambda value: value.literal, text=True)

    def settle(
        self, key: str, literals: Mapping[str, str | None], call: FieldCall
    ) -> FieldValue:
        """A field a tool checks: settled only by a `success`. On two labels,
        each settles on its own and every one must name the same value (G32)."""
        regions = [self._settle_one(key, r, call) for r in self._by_region(literals)]
        return self._labels(
            key, regions, lambda value: (value.authority_id, value.parsed)
        )

    def _transcribed_one(
        self, key: str, literals: Mapping[str, str | None]
    ) -> FieldValue:
        region, source = self._region(literals), self._verbatim_source(literals)
        present = {o: t for o, t in literals.items() if t}
        if not present or (source is not None and not literals[source]):
            return FieldValue()
        if source is not None:
            grounded = self._grounding(literals, source)
            return self._field(
                key,
                region,
                ValueState.SUPPORTED,
                "transcribed_as_seen",
                source,
                grounded,
            )
        return self._field(
            key,
            region,
            ValueState.AMBIGUOUS,
            "readings_conflict",
            None,
            present,
            verbatim=present,
        )

    def _settle_one(
        self, key: str, literals: Mapping[str, str | None], call: FieldCall
    ) -> FieldValue:
        region, source = self._region(literals), self._verbatim_source(literals)
        present = {o: t for o, t in literals.items() if t}
        if not present or (source is not None and not literals[source]):
            return FieldValue()
        if source is None:
            return self._settle_readers(key, region, present, call)
        literal, grounded = present[source], self._grounding(literals, source)
        first = call(literal, self.readings[source])
        if first.outcome == LookupStatus.SUCCESS:
            return self._field(
                key,
                region,
                ValueState.SUPPORTED,
                f"settled_by:{first.tool}",
                source,
                grounded,
                called=first,
            )
        if first.outcome in OPERATIONAL:
            return self._blocked(key, region, first, source, grounded)
        failed = _unsettled(first), f"lookup_{first.outcome.value}"
        if self.readings[source].role != DECIDED:  # Identical raw readings.
            return self._field(key, region, *failed, source, grounded)
        # G20: each raw reading's differing literal is tried. The decided literal
        # stays the verbatim; a confirmed reading is only the settled value's
        # provenance, through its call and that call's evidence (#88, 4.3).
        others = {o: t for o, t in present.items() if t != literal}
        blocked, wins = self._look_up(others, call)
        if blocked is not None:
            return self._blocked(key, region, blocked, source, grounded)
        if len({c.settled for c in wins.values()}) != 1:
            state = (ValueState.AMBIGUOUS, "readings_conflict") if wins else failed
            return self._field(key, region, *state, source, grounded)
        confirmed, called = next(iter(wins.items()))
        self._confirmed[(key, region)] = confirmed
        value = self._field(
            key,
            region,
            ValueState.SUPPORTED,
            f"settled_by:{called.tool}",
            source,
            grounded,
            called=called,
        )
        self._finding(key, "spelling_disagreement", value.evidence_ids)
        return value

    def _settle_readers(self, key, region, present, call) -> FieldValue:
        """G19 with G27 and G28: no reading was selected and the readers differ.
        Each literal is tried; when every success names one value, the field
        clears and keeps each reader's literal, choosing none."""
        blocked, wins = self._look_up(present, call)
        if blocked is not None:
            return self._blocked(key, region, blocked, None, {})
        if len({c.settled for c in wins.values()}) != 1:
            return self._field(
                key,
                region,
                ValueState.AMBIGUOUS,
                "readings_conflict",
                None,
                present,
                verbatim=present,
            )
        confirmed, called = next(iter(wins.items()))
        value = self._field(
            key,
            region,
            ValueState.SUPPORTED,
            f"settled_by:{called.tool}",
            confirmed,
            present,
            verbatim=present,
            called=called,
        )
        if len(set(present.values())) > 1:
            self._finding(key, "spelling_disagreement", value.evidence_ids)
        return value

    def _look_up(
        self, literals: Mapping[str, str], call: FieldCall
    ) -> tuple[Called | None, dict[str, Called]]:
        """One call per distinct literal, on the first reading that has it: the
        first operational outcome, if any, and the successes by reading."""
        by_text: dict[str, Called] = {}
        for observation, text in literals.items():
            if text not in by_text:
                by_text[text] = call(text, self.readings[observation])
        tries = {o: by_text[t] for o, t in literals.items()}
        blocked = next((c for c in tries.values() if c.outcome in OPERATIONAL), None)
        return blocked, {
            o: c for o, c in tries.items() if c.outcome == LookupStatus.SUCCESS
        }

    @staticmethod
    def _grounding(literals: Mapping[str, str | None], source: str) -> dict:
        """The verbatim's own reading, or every reading when all of them read the
        same text, so that the provenance names every reader that agreed (#124,
        the single-label agreement ruling; agreed with S5)."""
        if len(set(literals.values())) == 1:
            return dict(literals)
        return {source: literals[source]}

    def _by_region(self, literals: Mapping[str, str | None]) -> list[dict]:
        """A field's literals, one mapping per region (label), in order."""
        regions: dict[str, dict[str, str | None]] = {}
        for observation, literal in literals.items():
            region = self.readings[observation].region_id
            regions.setdefault(region, {})[observation] = literal
        return list(regions.values())

    def _region(self, literals: Mapping[str, str | None]) -> str | None:
        return next((self.readings[o].region_id for o in literals), None)

    def _labels(self, key, values: list[FieldValue], settled, text=False) -> FieldValue:
        """G32: a field on several labels clears only when every label settled
        the same value (the same place ID or usage, or for a field no tool
        checks the same text); otherwise each label's reading goes to review.
        The verbatims stay as written (G27)."""
        present = [value for value in values if value != FieldValue()]
        if len(present) < 2:
            return present[0] if present else FieldValue()
        blocked = next((v for v in present if v.reason in BLOCKED_REASONS), None)
        if blocked is not None and self.blocker is not None:
            return blocked
        verbatims: dict[str, str] = {}
        settled_ids: list[str] = []
        for value in present:
            if value.verbatim_by_observation:
                verbatims.update(value.verbatim_by_observation)
                settled_ids += value.settled_observation_ids
            else:
                verbatims[value.source_observation_id] = value.literal
                settled_ids.append(
                    self._confirmed.get(
                        (key, value.source_region_id), value.source_observation_id
                    )
                )
        roles = {o: self.readings[o].role for o in verbatims}
        agreed = all(v.state == ValueState.SUPPORTED for v in present) and (
            len({settled(v) for v in present}) == 1
        )
        if not agreed:
            ids = [i for v in present for i in v.evidence_ids if i in self._literals]
            return FieldValue(
                state=ValueState.AMBIGUOUS,
                layer="verbatim",
                evidence_ids=ids,
                evidence_relations=dict.fromkeys(ids, "supports"),
                verbatim_by_observation=verbatims,
                input_source_by_observation=roles,
                reason="labels_conflict",
            )
        relations: dict[str, Relation] = {}
        for value in present:
            relations |= value.evidence_relations
        # Every label keeps its own reading and provenance, even when the texts
        # are identical (#88 4.3, agreed with S5).
        value = present[0].model_copy(
            update={
                "literal": None,
                "input_source": None,
                "source_region_id": None,
                "source_observation_id": None,
                "verbatim_by_observation": verbatims,
                "input_source_by_observation": roles,
                "settled_observation_ids": settled_ids,
                "layer": "settled",  # One value on every label (G32, G38).
                "evidence_ids": list(relations),
                "evidence_relations": relations,
                # The settled text of a field no tool checks is the one text
                # every label has; otherwise the first settled name (#88, 4.3).
                "normalized": settled(present[0])
                if text
                else next((v.normalized for v in present if v.normalized), None),
            }
        )
        if len(set(verbatims.values())) > 1:  # Two spellings of one value.
            self._finding(key, "spelling_disagreement", value.evidence_ids)
        return value

    def _verbatim_source(self, literals: Mapping[str, str | None]) -> str | None:
        """The decided transcript, or the first reading when every reading has
        the same literal; None when readers differ and none was selected."""
        decided = next((o for o in literals if self.readings[o].role == DECIDED), None)
        if decided is None and len(set(literals.values())) == 1:
            return next(iter(literals))
        return decided

    def _ground(self, observation_id: str, literal: str) -> str:
        """Literal evidence: the text exactly as that reading has it, with its
        record stored so that the evidence projects like any other (#88)."""
        reading = self.readings[observation_id]
        if literal not in reading.text:
            raise ValueError(f"literal_not_in_source:{observation_id}")
        record = {
            "region_id": reading.region_id,
            "observation_ids": [observation_id],
            "excerpt": literal,
        }
        raw = json.dumps(record, sort_keys=True).encode()
        stored = self.blobs is not None
        item = Evidence(
            kind="literal",
            asset_id=self.asset_id,
            region_id=reading.region_id,
            observation_ids=[observation_id],
            source="field_harness",
            locator=f"region:{reading.region_id}",
            excerpt=literal,
            raw_ref=self.blobs.put(raw) if stored else None,
            digest=hashlib.sha256(raw).hexdigest() if stored else None,
        )
        self.evidence.append(item)
        self._literals.add(item.id)
        return item.id

    def _blocked(self, key, region, called: Called, source, grounded) -> FieldValue:
        """An operational outcome blocks the run (QUE-005); the field decides
        nothing."""
        self.blocker = self.blocker or f"harness_{called.tool}_{called.outcome.value}"
        return self._field(
            key,
            region,
            ValueState.UNRESOLVED,
            f"lookup_{called.outcome.value}",
            source,
            grounded,
        )

    def _field(
        self,
        key,
        region,
        state,
        reason,
        source,
        grounded,
        *,
        verbatim=None,
        called=None,
    ) -> FieldValue:
        """The field value: `grounded` literals become literal evidence, and a
        settling call adds its evidence, its warnings as findings and the value
        it settled. With `verbatim` no single literal is chosen (G27, G28)."""
        relations: dict[str, Relation] = {
            self._ground(o, t): "supports" for o, t in grounded.items()
        }
        settled = {}
        if called is not None:
            relations |= called.evidence
            for code, evidence_ids in called.warnings.items():
                self._finding(key, code, evidence_ids)
            settled = {
                "authority_id": called.authority_id,
                "parsed": called.parsed,
                "normalized": called.normalized,
                "authority_identity": dict(called.authority_identity)
                if called.authority_identity
                else None,
                "precision": called.precision,
                "century_rule": called.century_rule,
            }
        # G38: a lookup's success is settled; anything else keeps the layer
        # of what was written.
        layer = "settled" if called is not None else "verbatim"
        if verbatim:  # No single verbatim: each reading keeps its own.
            return FieldValue(
                state=state,
                layer=layer,
                evidence_ids=list(relations),
                evidence_relations=relations,
                verbatim_by_observation=dict(verbatim),
                input_source_by_observation={
                    o: self.readings[o].role for o in verbatim
                },
                settled_observation_ids=(
                    [source]
                    if source is not None and state == ValueState.SUPPORTED
                    else []
                ),
                reason=reason,
                **settled,
            )
        return FieldValue(
            state=state,
            layer=layer if grounded or called is not None else None,
            literal=grounded.get(source),
            evidence_ids=list(relations),
            evidence_relations=relations,
            input_source=self.readings[source].role if source is not None else RAW,
            source_region_id=region,
            source_observation_id=source,
            reason=reason,
            **settled,
        )

    def _finding(self, key: str, code: str, evidence_ids) -> None:
        self.findings.append(
            RunFinding(
                rule_id=code.split(":")[0],
                rule_version=RULE_VERSION,
                severity="warning",
                field_key=key,
                reason_code=code,
                evidence_ids=list(evidence_ids),
            )
        )


def _unsettled(called: Called) -> ValueState:
    return (
        ValueState.AMBIGUOUS
        if called.outcome == LookupStatus.AMBIGUOUS
        else ValueState.UNRESOLVED
    )


def date_order_evidence(parses: Sequence[Mapping | None]) -> set[str]:
    """The numeric orders the specimen's dates fix, from every model's reading
    (G33): a numeric date with a component over 12 has exactly one reading. A
    date whose day and month are equal (5-5-48) also has one, but fixes none."""
    return {
        only["order"]
        for parsed in parses
        if parsed and len(parsed.get("readings", [])) == 1
        for only in parsed["readings"]
        if only.get("order") in NUMERIC_ORDERS and only.get("day") != only.get("month")
    }


def choose_reading(parsed: Mapping | None, orders: set[str]) -> Mapping | None:
    """One reading of an ambiguous numeric date, only when the specimen's dates
    fix exactly one order and one reading with a year has it. Dates that
    disagree fix none: a misread can block a choice but never make one (G33)."""
    readings = (parsed or {}).get("readings", [])
    if len(orders) != 1 or len(readings) < 2:
        return None
    (order,) = orders
    matching = [r for r in readings if r.get("order") == order and r.get("year")]
    return matching[0] if len(matching) == 1 else None
