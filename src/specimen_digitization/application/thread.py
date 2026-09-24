"""The record thread of one run (docs/execution/golive/DATA_CONTRACT.md 8, S5 T3).

Pure: assembles GetRunThreadV1's rows and the specimen's snapshot into the response S6's client
reads. The rows are the SQL projection (section 11): regions, readings, comparisons, the first
pass, handoffs, tool calls, field candidates and the queue decision. The snapshot, which stays
the source of truth, gives the run's state and cost, the image, segmentation and the coverage
check, and says which decision, candidates and record version are current: those are keyed by
their content, so the ids come from the writer's own functions and the operation reads exactly
them.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .projection import LINKABLE, candidates, decision, field_group, record_id

TRACE_URL_SETTING = "SPECIMEN_TRACE_URL_TEMPLATE"
TRACE_PLACEHOLDER = "{trace_id}"
TRACE_ID = re.compile(r"[0-9a-f]{32}")
# The disagreement score orders review; it is not a probability (SCR-004, SCR-005).
CALIBRATION = "uncalibrated review priority"
COVERAGE_SOURCE = "label-coverage-check"
# The coverage check's own reason codes, by the check that raises them (label_coverage.py).
REGION_COUNT_CODES = ("zero_regions", "region_out_of_bounds", "label_region_count_out_of_range")
FULL_IMAGE_CODES = ("cross_check_detection_outside_labels",)
# GetRunThreadV1's limits (thread.gql). A list that reaches its limit may have been cut short, so
# the thread is refused rather than shown in part.
LIMITS = {
    "regions": 100,
    "observations": 400,
    "comparisons": 100,
    "handoffs": 400,
    "evidence": 1000,
    "toolCalls": 1000,
}
NESTED_LIMITS = {"links": 64, "fields": 500, "findings": 200}
# The ids passed for the current decisions, candidates and record version; the operation
# refuses more.
KEY_LIMITS = {"decisionIds": 100, "candidateIds": 500, "recordIds": 1}


class ThreadTooLarge(ValueError):
    """A run with more rows than one thread response reads (DATA_CONTRACT.md 8, T3)."""


class Part(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileRef(Part):
    key: str
    version: str


class Allowance(Part):
    allowance_micros: int | None
    reserved_total_micros: int | None
    remaining_micros: int | None
    at: str | None


class PriceList(Part):
    version: str | None
    as_of: str | None


class PaidCall(Part):
    step: str | None
    attempt: int | None
    reserved_micros: int | None
    usage: dict[str, Any]
    outcome: str | None
    cost_micros: int | None
    cost_basis: str | None
    price_list: PriceList | None


class RunState(Part):
    run_id: str
    status: str
    stage: str
    blocker: str | None
    next_retry_at: str | None
    profile: ProfileRef
    allowance: Allowance | None
    paid_calls: list[PaidCall]
    actual_cost_micros: int | None


class Trace(Part):
    trace_id: str | None
    url: str | None


class Image(Part):
    asset_id: str
    sha256: str
    width: int
    height: int
    pixel_basis: str


class Segmentation(Part):
    model_revision: str | None
    settings: dict[str, Any] | None


class Check(Part):
    name: Literal["region_count", "full_image"]
    passed: bool
    detail: dict[str, Any]


class CoverageCheck(Part):
    status: Literal["passed", "failed", "not_run"]
    checks: list[Check]
    evidence_id: str | None
    checked_at: str | None


class Geometry(Part):
    x: int
    y: int
    width: int
    height: int


class RawResponse(Part):
    asset_id: str
    sha256: str | None


class ModelCall(Part):
    observation_id: str
    route_id: str | None
    model: str
    provider: str
    prompt_version: str
    outcome: str
    raw_response: RawResponse


class Reading(Part):
    observation_id: str
    route_id: str | None
    model: str
    provider: str
    prompt_version: str
    literal_text: str
    unreadable_spans: list[str]
    outcome: str
    raw_response: RawResponse


class Comparison(Part):
    left_observation_id: str
    right_observation_id: str
    algorithm: str
    ratio: float | None
    edit_distance: int | None
    length_basis: int | None
    status: str
    reasons: list[str]
    calibration: Literal["uncalibrated review priority"]


class Handoff(Part):
    observation_id: str
    role: str
    handed_text: str
    note: str | None


class FirstPass(Part):
    decision_kind: str | None
    selected_observation_id: str | None
    decided_text: str
    unresolved: bool
    rationale: str | None
    model_call: ModelCall | None
    handoffs: list[Handoff]


class RegionThread(Part):
    region_id: str | None
    ordinal: int
    rotation_quarter_turns: int
    geometry: Geometry
    readings: list[Reading]
    comparisons: list[Comparison]
    first_pass: FirstPass | None


class ToolCall(Part):
    call_key: str
    phase: str
    tool: str
    tool_version: str
    source: str | None
    field_keys: list[str]
    input_source: str
    region_id: str | None
    observation_id: str | None
    attempt: int
    arguments: Any
    outcome: str
    result: Any
    error: Any
    retry_after: Any
    evidence_id: str | None
    started_at: str | None
    completed_at: str | None


class Verbatim(Part):
    text: str | None
    input_source: str | None
    region_id: str | None
    observation_id: str | None


class FieldEvidence(Part):
    evidence_id: str
    relation: str
    source: str
    locator: str | None
    outcome: str


class FieldThread(Part):
    field_key: str
    group: str
    state: str
    verbatim: list[Verbatim]
    parsed: str | None
    precision: str | None
    century_rule: str | None
    normalized: str | None
    authority_id: str | None
    settled_observation_ids: list[str]
    evidence: list[FieldEvidence]


class FindingThread(Part):
    rule_id: str
    rule_version: str
    severity: str
    outcome: str
    field_key: str | None
    reason_code: str
    evidence_ids: list[str]


class DecisionThread(Part):
    disposition: str | None
    policy_version: str
    reason_codes: list[str]
    summary: str
    findings: list[FindingThread]


class Thread(Part):
    """The response of section 8, field for field."""

    specimen_id: str
    revision: int
    run: RunState
    trace: Trace
    image: Image
    segmentation: Segmentation | None
    coverage_check: CoverageCheck
    regions: list[RegionThread]
    tool_calls: list[ToolCall]
    fields: list[FieldThread]
    decision: DecisionThread | None


def trace_url_template(env=None) -> str | None:
    """The configured trace link, an https URL holding `{trace_id}` once; None when unset."""
    env = os.environ if env is None else env
    template = env.get(TRACE_URL_SETTING, "")
    if not template:
        return None
    probe = template.replace(TRACE_PLACEHOLDER, "0" * 32)
    parts = urlsplit(probe)
    if (
        template.count(TRACE_PLACEHOLDER) != 1
        or "{" in probe
        or "}" in probe
        or parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
    ):
        raise ValueError(
            f"{TRACE_URL_SETTING} must be an https URL holding {TRACE_PLACEHOLDER} once"
        )
    return template


def keys(run) -> dict[str, list[str]]:
    """The ids of the run's current decisions, field candidates and record version.

    They are the writer's own keys for the snapshot's state (DATA_CONTRACT.md 5), so the thread
    reads the rows the snapshot describes, also after a change back to an earlier state.
    """
    found = {
        "decisionIds": [d.id for t in run.transcripts if (d := decision(run, t)) is not None],
        "candidateIds": [
            c.id for key, value in run.fields.items() for c in candidates(run, key, value)
        ],
        "recordIds": [r for r in (record_id(run),) if r is not None],
    }
    for name, limit in KEY_LIMITS.items():
        if len(found[name]) > limit:
            raise ThreadTooLarge(f"Run thread exceeds its read bounds: {name}")
    return found


def assemble(
    specimen, run, rows: dict, *, status: str, trace_url_template: str | None = None
) -> Thread:
    """One run's thread from GetRunThreadV1's data and the specimen's snapshot.

    `run` is the snapshot's record of the run read, the active run or a previous one, and
    `status` is the summary's status for it.
    """
    found = rows.get("runs") or []
    row = found[0] if found else {}
    _check_bounds(row)
    current = {name: {_id(i) for i in ids} for name, ids in keys(run).items()}
    evidence = row.get("evidence") or []
    tool_calls = row.get("toolCalls") or []
    trace_id = row.get("traceId") or getattr(run, "trace_id", None)
    return Thread(
        specimen_id=specimen.id,
        revision=specimen.version,
        run=_run_state(run, status),
        trace=Trace(trace_id=trace_id, url=_trace_url(trace_url_template, trace_id)),
        image=Image(
            asset_id=specimen.asset.id,
            sha256=specimen.asset.sha256,
            width=specimen.asset.width,
            height=specimen.asset.height,
            pixel_basis=specimen.asset.pixel_basis,
        ),
        segmentation=_segmentation(run),
        coverage_check=_coverage(run, evidence),
        regions=_regions(row, current),
        tool_calls=[_tool_call(call) for call in tool_calls],
        fields=_fields(run, row, current, evidence, tool_calls),
        decision=_decision(row, current),
    )


def _id(value) -> str | None:
    """A UUID as the domain writes it; Data Connect returns 32 hex without dashes (section 5)."""
    return None if value is None else str(UUID(str(value)))


def _plain(item):
    return item.model_dump(mode="json") if hasattr(item, "model_dump") else item


def _whole(value):
    """A JSON number that is a whole number, as an int: `Any` columns may return doubles."""
    return int(value) if isinstance(value, float) and value.is_integer() else value


def _check_bounds(row: dict) -> None:
    lists = [(name, row.get(name) or [], limit) for name, limit in LIMITS.items()]
    lists += [("links", c.get("links") or [], NESTED_LIMITS["links"]) for c in row.get("candidates") or []]
    for record in row.get("records") or []:
        lists += [(name, record.get(name) or [], NESTED_LIMITS[name]) for name in ("fields", "findings")]
    for name, items, limit in lists:
        if len(items) >= limit:
            raise ThreadTooLarge(f"Run thread exceeds its read bounds: {name}")


def _trace_url(template: str | None, trace_id: str | None) -> str | None:
    if not template or not trace_id or not TRACE_ID.fullmatch(trace_id) or not trace_id.strip("0"):
        return None
    return template.replace(TRACE_PLACEHOLDER, trace_id)


def _run_state(run, status: str) -> RunState:
    allowance = _plain(getattr(run, "program_allowance", None))
    usage = getattr(run, "usage", None)
    return RunState(
        run_id=run.id,
        status=status,
        stage=run.stage,
        blocker=run.blocker,
        next_retry_at=run.next_retry_at,
        profile=ProfileRef(key=run.profile.id, version=run.profile.version),
        allowance=Allowance(**{name: allowance.get(name) for name in Allowance.model_fields})
        if allowance
        else None,
        paid_calls=[_paid_call(_plain(call)) for call in getattr(run, "paid_calls", None) or []],
        actual_cost_micros=getattr(usage, "actual_cost_micros", None),
    )


def _paid_call(call: dict) -> PaidCall:
    prices = _plain(call.get("price_list"))
    return PaidCall(
        step=call.get("step"),
        attempt=call.get("attempt"),
        reserved_micros=call.get("reserved_micros"),
        usage={name: _whole(amount) for name, amount in (call.get("usage") or {}).items()},
        outcome=call.get("outcome"),
        cost_micros=call.get("cost_micros"),
        cost_basis=call.get("cost_basis"),
        price_list=PriceList(version=prices.get("version"), as_of=prices.get("as_of"))
        if prices
        else None,
    )


def _segmentation(run) -> Segmentation | None:
    recorded = run.segmentation or {}
    if not recorded:
        return None
    return Segmentation(
        model_revision=recorded.get("model_revision"), settings=recorded.get("settings")
    )


def _coverage(run, evidence: list[dict]) -> CoverageCheck:
    """G15's check as its two checks (coordinator ruling, 2026-09-23)."""
    records = [e for e in evidence if e.get("source") == COVERAGE_SOURCE]
    evidence_id = _id(records[-1]["id"]) if records else None
    check = _plain(getattr(run, "coverage_check", None))
    if not check:
        return CoverageCheck(status="not_run", checks=[], evidence_id=evidence_id, checked_at=None)
    codes = list(check.get("reason_codes") or [])
    cross = check.get("cross_check") or {}
    settings = (run.profile_snapshot or {}).get("segmentation_settings") or {}
    rule = settings.get("coverage") or {}

    def bound(name):
        return _whole(check[name] if check.get(name) is not None else rule.get(name))

    counted = [code for code in codes if code in REGION_COUNT_CODES]
    outside = [code for code in codes if code in FULL_IMAGE_CODES]
    return CoverageCheck(
        status="passed" if check.get("outcome") == "confirmed" else "failed",
        checks=[
            Check(
                name="region_count",
                passed=not counted,
                detail={
                    "found": _whole(check.get("region_count")),
                    "min": bound("min_label_regions"),
                    "max": bound("max_label_regions"),
                    "reason_codes": counted,
                },
            ),
            Check(
                name="full_image",
                passed=not outside,
                detail={
                    "counted": _whole(cross.get("counted")),
                    "outside": len(cross.get("uncovered_boxes") or []),
                    "threshold": cross.get("threshold"),
                    "min_inside_fraction": cross.get("min_inside_fraction"),
                    "reason_codes": outside,
                },
            ),
        ],
        evidence_id=evidence_id,
        checked_at=check.get("checked_at"),
    )


def _raw(row: dict) -> RawResponse:
    return RawResponse(asset_id=_id(row["rawAssetId"]), sha256=(row.get("rawAsset") or {}).get("sha256"))


def _regions(row: dict, current: dict) -> list[RegionThread]:
    readings, calls, comparisons = defaultdict(list), {}, defaultdict(list)
    for observation in row.get("observations") or []:
        calls[_id(observation["id"])] = observation
        if observation.get("independent"):
            readings[_id(observation["regionId"])].append(observation)
    for comparison in row.get("comparisons") or []:
        comparisons[_id(comparison["regionId"])].append(comparison)
    handoffs = defaultdict(list)
    for handoff in row.get("handoffs") or []:
        handoffs[_id(handoff["transcriptionVersionId"])].append(handoff)
    decisions = {}
    for found in row.get("decisions") or []:
        if _id(found["id"]) in current["decisionIds"]:
            decisions.setdefault(_id(found.get("regionId")), found)
    result = []
    # Stable: regions of one ordinal keep the order they were written in.
    for region in sorted(row.get("regions") or [], key=lambda r: r["ordinal"]):
        ident = _id(region["id"])
        geometry = {k: _whole(v) for k, v in (region.get("geometry") or {}).items()}
        found = decisions.get(ident)
        result.append(
            RegionThread(
                region_id=region.get("domainRegionId"),
                ordinal=region["ordinal"],
                rotation_quarter_turns=geometry.get("rotation_quarter_turns") or 0,
                geometry=Geometry(**{k: geometry[k] for k in ("x", "y", "width", "height")}),
                readings=[
                    Reading(
                        observation_id=_id(o["id"]),
                        route_id=o.get("routeId"),
                        model=o["modelVersion"],
                        provider=o["provider"],
                        prompt_version=o["promptVersion"],
                        literal_text=o["literalText"],
                        unreadable_spans=list(o.get("unreadableSpans") or []),
                        outcome=o["outcome"],
                        raw_response=_raw(o),
                    )
                    for o in readings[ident]
                ],
                comparisons=[
                    Comparison(
                        left_observation_id=_id(c["leftObservationId"]),
                        right_observation_id=_id(c["rightObservationId"]),
                        algorithm=c["algorithm"],
                        ratio=c.get("ratio"),
                        edit_distance=c.get("editDistance"),
                        length_basis=c.get("lengthBasis"),
                        status=c["status"],
                        reasons=list(c.get("reasons") or []),
                        calibration=CALIBRATION,
                    )
                    for c in comparisons[ident]
                ],
                first_pass=None if found is None else _first_pass(found, calls, handoffs),
            )
        )
    return result


def _first_pass(found: dict, calls: dict, handoffs: dict) -> FirstPass:
    call = calls.get(_id(found.get("firstPassObservationId")))
    return FirstPass(
        decision_kind=found.get("decisionKind"),
        selected_observation_id=_id(found.get("selectedObservationId")),
        decided_text=found["literalText"],
        unresolved=found["unresolved"],
        rationale=found.get("rationale"),
        model_call=None
        if call is None
        else ModelCall(
            observation_id=_id(call["id"]),
            route_id=call.get("routeId"),
            model=call["modelVersion"],
            provider=call["provider"],
            prompt_version=call["promptVersion"],
            outcome=call["outcome"],
            raw_response=_raw(call),
        ),
        handoffs=[
            Handoff(
                observation_id=_id(h["observationId"]),
                role=h["role"],
                handed_text=h["handedText"],
                note=h.get("note"),
            )
            for h in handoffs[_id(found["id"])]
        ],
    )


def _region_of(row: dict, *relations: str) -> str | None:
    """The domain region id of the first parent the row names, through its region row."""
    for relation in relations:
        region = (row.get(relation) or {}).get("region") or {}
        if region.get("domainRegionId") is not None:
            return region["domainRegionId"]
    return None


def _tool_call(call: dict) -> ToolCall:
    result = call.get("result")
    outcome = result if isinstance(result, dict) else {}
    return ToolCall(
        call_key=call["callKey"],
        phase=call["phase"],
        tool=call["tool"],
        tool_version=call["toolVersion"],
        source=call.get("source"),
        field_keys=list(call.get("fieldKeys") or []),
        input_source=call["inputSource"],
        region_id=_region_of(call, "transcriptionVersion", "observation"),
        observation_id=_id(call.get("observationId")),
        attempt=call["attempt"],
        arguments=call.get("arguments"),
        outcome=call["outcome"],
        result=result,
        # CONTRACTS.md's LookupResult: the sanitized error and the retry delay, lifted out.
        error=outcome.get("error"),
        retry_after=outcome.get("retry_after"),
        evidence_id=_id(call.get("evidenceId")),
        started_at=call.get("startedAt"),
        completed_at=call.get("completedAt"),
    )


def _fields(run, row: dict, current: dict, evidence: list[dict], tool_calls: list[dict]) -> list[FieldThread]:
    rows = {_id(c["id"]): c for c in row.get("candidates") or [] if _id(c["id"]) in current["candidateIds"]}
    records = [r for r in row.get("records") or [] if _id(r["id"]) in current["recordIds"]]
    resolved = {f["fieldKey"]: f for f in records[0].get("fields") or []} if records else {}
    items = {_id(e["id"]): e for e in evidence}
    result = []
    for key, value in run.fields.items():
        # The field's current candidates, in verbatim order.
        present = [rows[c.id] for c in candidates(run, key, value) if c.id in rows]
        field = resolved.get(key)
        if not present and field is None:
            continue
        # Only a candidate carrying the settled value carries these (section 11); with two
        # labels settled alike (G32), each label's candidate does.
        links, seen = [], set()
        for found in present:
            for link in found.get("links") or []:
                item = items.get(_id(link["evidenceId"]))
                if item is not None and item["outcome"] in LINKABLE and item["id"] not in seen:
                    seen.add(item["id"])
                    links.append((link, item))
        parsed = _first(present, "parsedValue")
        stated = parsed if isinstance(parsed, dict) else {"value": parsed}
        result.append(
            FieldThread(
                field_key=key,
                group=(field or {}).get("fieldGroup") or field_group(run, key),
                state=field["state"] if field else present[0]["state"],
                verbatim=[
                    Verbatim(
                        text=found.get("literalValue"),
                        input_source=found.get("inputSource"),
                        region_id=_region_of(found, "sourceTranscription", "sourceObservation"),
                        observation_id=_id(found.get("sourceObservationId")),
                    )
                    for found in present
                ],
                parsed=stated.get("value"),
                precision=stated.get("precision"),
                century_rule=stated.get("century_rule"),
                normalized=_first(present, "normalizedValue"),
                authority_id=_first(present, "authorityId"),
                settled_observation_ids=settled_observation_ids(present, tool_calls),
                evidence=[
                    FieldEvidence(
                        evidence_id=_id(link["evidenceId"]),
                        relation=link["relation"],
                        source=item["source"],
                        locator=item.get("locator"),
                        outcome=item["outcome"],
                    )
                    for link, item in links
                ],
            )
        )
    return result


def _first(rows: list[dict], name: str):
    return next((row[name] for row in rows if row.get(name) is not None), None)


def settled_observation_ids(candidate_rows: list[dict], tool_calls: list[dict]) -> list[str]:
    """The readings a field's settled value rests on, in verbatim order (G32; section 8).

    `candidate_rows` are the field's current candidates in verbatim order and `tool_calls` the
    run's, as GetRunThreadV1 returns them. Each candidate carrying the settled value names its
    reading: its own for a raw reading, its decision's selected reading for the decided
    transcript. A single decided-transcript candidate that a raw-reading lookup confirmed, by
    evidence that decides or supports it, names that lookup's reading instead (G20's fallback).
    """
    carrying = [
        c
        for c in candidate_rows
        if c.get("normalizedValue") is not None or c.get("authorityId") is not None
    ]
    if (
        len(candidate_rows) == 1
        and carrying
        and carrying[0].get("inputSource") == "decided_transcript"
    ):
        confirming = {
            _id(link["evidenceId"])
            for link in carrying[0].get("links") or []
            if link["relation"] in ("decides", "supports")
        }
        fallback = []
        for call in tool_calls:
            reading = _id(call.get("observationId"))
            if (
                _id(call.get("evidenceId")) in confirming
                and call.get("inputSource") == "raw_reading"
                and reading is not None
                and reading not in fallback
            ):
                fallback.append(reading)
        if fallback:
            return fallback
    result = []
    for candidate in carrying:
        if candidate.get("inputSource") == "raw_reading":
            reading = candidate.get("sourceObservationId")
        elif candidate.get("inputSource") == "decided_transcript":
            reading = (candidate.get("sourceTranscription") or {}).get("selectedObservationId")
        else:
            reading = None
        if reading is not None:
            result.append(_id(reading))
    return result


def _decision(row: dict, current: dict) -> DecisionThread | None:
    records = [r for r in row.get("records") or [] if _id(r["id"]) in current["recordIds"]]
    if not records:
        return None
    record = records[0]
    return DecisionThread(
        disposition=record.get("disposition"),
        policy_version=record["policyVersion"],
        reason_codes=list(record.get("reasonCodes") or []),
        summary=record["summary"],
        findings=[
            FindingThread(
                rule_id=f["ruleId"],
                rule_version=f["ruleVersion"],
                severity=f["severity"],
                outcome=f["outcome"],
                field_key=f.get("fieldKey"),
                reason_code=f["reasonCode"],
                evidence_ids=[_id(e) for e in f.get("evidenceIds") or []],
            )
            for f in record.get("findings") or []
        ],
    )
