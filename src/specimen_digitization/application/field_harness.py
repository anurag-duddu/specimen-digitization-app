"""The stage 7 field harness (HARNESS.md section 11).

A Pydantic AI agent on the profile's harness route reads every text handed to
it, proposes each field's literal as each reading has it, and may call the
profile's tools, always through the ledger. Every field is then decided by
field resolution from recorded outcomes alone (section 9); the agent's claims
decide nothing and no value is invented (HAR-019).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from pydantic import Field
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.tool_manager import ToolManager
from pydantic_ai.usage import RunUsage, UsageLimits

from .derivations import (
    Found,
    apply_derivations,
    date_derivations,
    elevation_derivations,
)
from .domain import Evidence, FieldValue, LookupStatus, Record
from .field_resolution import (
    Called,
    FieldCall,
    Reading,
    Resolver,
    choose_reading,
    date_order_evidence,
)
from .harness_ledger import ToolLedger, called, served
from .reliability import AdapterFailure, run_agent_bounded

# G30: every request reserves its worst case, so a run is bounded by these caps
# together, and S3 sizes the `parse` reservation from them; change one and the
# reservation changes (T1's probe used 3 requests and 1,285 output tokens).
MAX_OUTPUT_TOKENS = 2_048  # Per request, enforced by the provider.
REQUEST_LIMIT = 8  # Per run.
INPUT_TOKEN_LIMIT = 60_000  # Per run, checked after each response.
MAX_PROMPT_BYTES = 12_000  # Instructions, readings and tool definitions.
TOOL_DEFINITION_BYTES = 2_000  # Allowance for the tools' schemas in the prompt.
MAX_TOOL_CALLS = 12  # The agent's tool calls per run.
MAX_GEOCODING_REQUESTS = 4  # Per run, the agent's and the final ones together.
GEOGRAPHY = "geography_lookup"
# Verbatim locality text: its literal helps form the address, but no geocoder
# result settles it (PRD 519).
TRANSCRIBED_ONLY = frozenset({"precise_location"})


class FieldLiteral(Record):
    field_key: str
    reading: str
    literal: str = Field(min_length=1, max_length=500)
    year_literal: str | None = Field(default=None, max_length=20)


class HarnessOutput(Record):
    literals: list[FieldLiteral] = Field(default_factory=list, max_length=400)


@dataclass(frozen=True)
class FieldPlan:
    """The profile's fields and the tool each may use (S3's published profile)."""

    mandatory: tuple[str, ...]
    optional: tuple[str, ...] = ()
    tools: Mapping[str, str] = field(default_factory=dict)

    @property
    def fields(self) -> tuple[str, ...]:
        return self.mandatory + self.optional


@dataclass
class HarnessOutcome:
    fields: dict[str, FieldValue]
    evidence: list[Evidence]
    findings: list
    tool_calls: list
    lookups: list
    blocker: str | None
    failure: str | None = None  # A harness failure (G6): the fields go to review.
    usage: RunUsage | None = None  # The provider's, up to any stop.


def labelled(readings: Sequence[Reading]) -> dict[str, Reading]:
    """Readings named 1A, 1B, 2A ...: label order, then reading order."""
    regions: dict[str, list[Reading]] = {}
    for reading in readings:
        regions.setdefault(reading.region_id, []).append(reading)
    return {
        f"{n}{chr(ord('A') + i)}": reading
        for n, group in enumerate(regions.values(), 1)
        for i, reading in enumerate(group)
    }


def build_request(
    plan: FieldPlan, names: Mapping[str, Reading], notes: Mapping[str, str]
) -> str:
    """The user message: the fields with their tools, then every reading."""

    def describe(key: str) -> str:
        tool = plan.tools.get(key)
        return f"{key} [{tool}]" if tool else key

    lines = [
        "Mandatory fields: " + ", ".join(map(describe, plan.mandatory)),
        "Optional fields: " + (", ".join(map(describe, plan.optional)) or "none"),
    ]
    region = None
    for name, reading in names.items():
        if reading.region_id != region:
            region = reading.region_id
            lines += ["", f"Label {name[:-1]}:"]
        role = (
            "decided transcript"
            if reading.role == "decided_transcript"
            else "raw reading"
        )
        note = notes.get(reading.observation_id)
        lines.append(
            f"Reading {name} ({role}{'; first pass: ' + note if note else ''}):"
        )
        lines.append(reading.text)
    return "\n".join(lines)


def output_problems(
    output: HarnessOutput, names: Mapping[str, Reading], plan: FieldPlan
) -> list[str]:
    problems, seen = [], {}
    for item in output.literals:
        reading = names.get(item.reading)
        if item.field_key not in plan.fields:
            problems.append(f"{item.field_key} is not a field of this profile")
        elif reading is None:
            problems.append(f"{item.reading} is not a reading you were given")
        elif item.literal not in reading.text:
            problems.append(
                f"{item.field_key}: copy the literal exactly as reading {item.reading} has it"
            )
        elif item.year_literal and item.year_literal not in reading.text:
            problems.append(
                f"{item.field_key}: the year literal is not in reading {item.reading}"
            )
        elif (
            seen.setdefault((item.field_key, item.reading), item.literal)
            != item.literal
        ):
            problems.append(
                f"{item.field_key}: give one literal per reading, not two for {item.reading}"
            )
    return problems


def run_harness(
    model,
    instructions: str,
    *,
    plan: FieldPlan,
    readings: Sequence[Reading],
    notes: Mapping[str, str],
    ledger: ToolLedger,
    asset_id: str,
    blobs,
    timeout_seconds: float,
) -> HarnessOutcome:
    """Run the agent within the G30 caps, then decide every field from the
    ledger's records. A harness failure (G6) decides no field; a provider error
    raises, as an operational block."""
    names = labelled(readings)
    agent = Agent(
        model,
        name="field_harness",
        output_type=HarnessOutput,
        instructions=instructions,
        model_settings={"max_tokens": MAX_OUTPUT_TOKENS},
        retries=2,
    )
    budget = Budget()
    _register_tools(agent, plan, names, ledger, budget)

    @agent.output_validator
    def complete(output: HarnessOutput) -> HarnessOutput:
        if problems := output_problems(output, names, plan):
            raise ModelRetry("; ".join(problems))
        return output

    # Counted in place: a run stopped by a cap or an invalid answer still
    # reports what it spent (the lane's cost record, HARNESS.md section 14).
    failure, output, usage = None, HarnessOutput(), RunUsage()
    request = build_request(plan, names, notes)
    size = len((instructions + request).encode()) + TOOL_DEFINITION_BYTES
    try:
        if size > MAX_PROMPT_BYTES:
            failure = "harness_input_too_large"  # Before any call (G30).
        else:
            # One tool call at a time: the ledger's record of a call answers
            # its repeat, and the caps count exactly.
            with ToolManager.parallel_execution_mode("sequential"):
                result = run_agent_bounded(
                    agent,
                    request,
                    timeout_seconds=timeout_seconds,
                    usage_limits=UsageLimits(
                        request_limit=REQUEST_LIMIT,
                        input_tokens_limit=INPUT_TOKEN_LIMIT,
                    ),
                    usage=usage,
                )
            output = result.output
    except UsageLimitExceeded:
        failure = "harness_usage_limit"  # A G30 cap: a harness failure (G6).
    except AdapterFailure as exc:
        if exc.status != LookupStatus.MALFORMED:
            raise  # Provider failures stay operational (QUE-005).
        failure = "harness_malformed_output"
    return resolve(plan, names, output, ledger, asset_id, blobs, failure, usage, budget)


def resolve(
    plan, names, output, ledger, asset_id, blobs, failure=None, usage=None, budget=None
) -> HarnessOutcome:
    """Every field decided from recorded outcomes (section 9). Tool calls the
    agent did not make on its final literals are made here, once each."""
    resolver = Resolver(list(names.values()), asset_id, blobs=blobs)
    literals: dict[str, dict[str, str]] = {}  # field -> observation -> literal
    years: dict[tuple[str, str], str] = {}
    for item in output.literals:
        reading = names[item.reading]
        literals.setdefault(item.field_key, {})[reading.observation_id] = item.literal
        if item.year_literal:
            years[(item.field_key, reading.observation_id)] = item.year_literal
    everyone = {r.observation_id: None for r in names.values()}
    by_id = {r.observation_id: r for r in names.values()}
    _drop_copied_ends(literals, years, by_id)
    dates = _date_calls(plan, literals, years, by_id, ledger)
    localities = {k for k, tool in plan.tools.items() if tool == GEOGRAPHY}
    budget = budget or Budget()
    derivations: list = []  # Those in the geography results (S8's tool, G37).
    fields: dict[str, FieldValue] = {}
    for key in plan.fields:
        found = literals.get(key)
        if not found:
            fields[key] = FieldValue()
            continue
        # Every reading of each label the field was found on (G19, G32).
        regions = {by_id[o].region_id for o in found}
        per_reading = {
            o: found.get(o) for o in everyone if by_id[o].region_id in regions
        }
        tool = plan.tools.get(key)
        if tool is None or key in TRANSCRIBED_ONLY:
            fields[key] = resolver.transcribed(key, per_reading)
        else:
            call = _field_call(
                key,
                tool,
                literals,
                years,
                dates,
                ledger,
                localities,
                budget,
                derivations,
            )
            fields[key] = resolver.settle(key, per_reading, call)
    # G37: what the label leaves out, filled from settled fields with evidence:
    # the elevation rules of G41, one date for both ends (G44) and the
    # geography results' derivations.
    unique = {(f.derivation.model_dump_json(), f.call_evidence): f for f in derivations}
    derived, filled_evidence = apply_derivations(
        fields,
        [*elevation_derivations(fields), *date_derivations(fields), *unique.values()],
        asset_id=asset_id,
        blobs=blobs,
    )
    fields.update(derived)
    return HarnessOutcome(
        fields=fields,
        evidence=[
            *resolver.evidence,
            *ledger.evidence,
            *dates.evidence,
            *filled_evidence,
        ],
        findings=resolver.findings,
        tool_calls=ledger.records,
        lookups=ledger.lookups,
        blocker=resolver.blocker,
        failure=failure,
        usage=usage,
    )


@dataclass
class _Dates:
    """Every date literal of every reading, parsed once, and the orders they
    fix (G33); `evidence` holds the one item citing the dates that fixed it."""

    parsed: dict[tuple[str, str, str | None], object] = field(default_factory=dict)
    orders: set[str] = field(default_factory=set)
    evidence: list[Evidence] = field(default_factory=list)


# Pairs whose To the harness derives from From when the label writes one value
# (G41, G44).
RANGES = (
    ("elevation_from_m", "elevation_to_m"),
    ("elevation_from_ft", "elevation_to_ft"),
    ("date_visited_from", "date_visited_to"),
)


def _drop_copied_ends(literals, years, by_id) -> None:
    """A literal the agent gave to both ends of a pair, which the reading
    writes once, is From's: To's copy is dropped, so G41 or G44 derives To with
    its record (the coordinator's ruling of 2026-09-24). The value and the
    clearance are unchanged; two occurrences keep both ends as written."""
    for low, high in RANGES:
        ends = literals.get(high, {})
        for observation, text in list(ends.items()):
            if (
                literals.get(low, {}).get(observation) == text
                and by_id[observation].text.count(text) == 1
            ):
                del ends[observation]
                years.pop((high, observation), None)
        if high in literals and not ends:
            del literals[high]


def _date_calls(plan, literals, years, by_id, ledger) -> _Dates:
    dates = _Dates()
    for key, found in literals.items():
        if plan.tools.get(key) != "date_parser":
            continue
        for observation, literal in found.items():
            year = years.get((key, observation))
            arguments = {"literal": literal, "year_literal": year}
            result, _ = ledger.run("date_parser", by_id[observation], arguments, [key])
            dates.parsed[(key, observation, literal)] = result
    dates.orders = date_order_evidence([r.parsed for r in dates.parsed.values()])
    if len(dates.orders) == 1:
        # The dates that fixed the order, cited by any date settled by it.
        fixing = [
            (observation, literal)
            for (_, observation, literal), result in dates.parsed.items()
            if date_order_evidence([result.parsed]) == dates.orders
        ]
        dates.evidence.append(
            Evidence(
                kind="date_order",
                asset_id=ledger.asset_id,
                observation_ids=sorted({o for o, _ in fixing}),
                source="field_harness",
                locator="date_order:" + next(iter(dates.orders)),
                excerpt="; ".join(sorted({t for _, t in fixing})),
            )
        )
    return dates


def _field_call(
    key,
    tool,
    literals,
    years,
    dates: _Dates,
    ledger: ToolLedger,
    localities,
    budget,
    derivations: list,
) -> FieldCall:
    if tool == GEOGRAPHY:

        def geography(literal: str, reading: Reading) -> dict:
            # One request per reading carries all of its locality literals.
            own = {
                field_key: found[reading.observation_id]
                for field_key, found in literals.items()
                if reading.observation_id in found and field_key in localities
            }
            return geography_arguments(own)

        def bounded(literal: str, reading: Reading) -> Called:
            arguments = geography(literal, reading)
            if not budget.geocode(reading, arguments):
                # A request past the run's cap is refused: an operational block.
                return Called(LookupStatus.POLICY, tool)
            result, evidence = ledger.run(
                tool, reading, arguments, served(tool, arguments, key)
            )
            # Each derivation names the call that returned it (#124, 4.8).
            calls = tuple(evidence.values())
            derivations.extend(Found(d, calls) for d in result.derivations)
            return called(key, literal, result, evidence)

        return bounded
    if tool != "date_parser":
        return ledger.field_call(
            key, tool, lambda literal, reading: {"literal": literal}
        )

    def date(literal: str, reading: Reading) -> Called:
        year = years.get((key, reading.observation_id))
        arguments = {"literal": literal, "year_literal": year}
        result, evidence = ledger.run(tool, reading, arguments, [key])
        if result.outcome == LookupStatus.AMBIGUOUS and (
            chosen := choose_reading(result.parsed, dates.orders)
        ):
            # G33: the specimen's dates fixed the order; the recorded call
            # keeps its own outcome.
            return Called(
                LookupStatus.SUCCESS,
                tool,
                parsed=chosen["iso"],
                precision=chosen["precision"],
                century_rule=chosen["century_rule"],
                evidence={evidence[tool]: "supports", dates.evidence[0].id: "supports"},
            )
        return called(key, literal, result, evidence)

    return date


def geography_arguments(fields: Mapping[str, str]) -> dict:
    """One reading's locality literals in field order, so that the agent's
    check and the final call are one request (one Google call)."""
    return {"literals": [[key, fields[key]] for key in sorted(fields)]}


@dataclass
class Budget:
    """The run's tool calls and geocoding requests against their caps (G30)."""

    tool_calls: int = 0
    geocoding: set[str] = field(default_factory=set)

    def tool_call(self) -> bool:
        self.tool_calls += 1
        return self.tool_calls <= MAX_TOOL_CALLS

    def geocode(self, reading: Reading, arguments: dict) -> bool:
        """Whether this request may be made; a repeat is the recorded one."""
        key = json.dumps([reading.observation_id, arguments], sort_keys=True)
        if key not in self.geocoding and len(self.geocoding) >= MAX_GEOCODING_REQUESTS:
            return False
        self.geocoding.add(key)
        return True


REFUSED = {"refused": "no tool calls remain in this run; give your final answer"}


def _register_tools(
    agent: Agent,
    plan: FieldPlan,
    names: Mapping[str, Reading],
    ledger: ToolLedger,
    budget: Budget,
) -> None:
    """Only the profile's tools, each through the ledger (HAR-007); what the
    agent sees of Google is outcomes only (G26)."""

    def served(tool: str) -> list[str]:
        return sorted(k for k, t in plan.tools.items() if t == tool)

    def reading_for(name: str, literal: str = "") -> Reading:
        reading = names.get(name)
        if reading is None:
            raise ModelRetry(f"{name} is not a reading you were given")
        if literal not in reading.text:
            raise ModelRetry(f"copy the literal exactly as reading {name} has it")
        return reading

    if served("taxonomy_verifier"):

        @agent.tool_plain
        def verify_taxon(reading: str, literal: str) -> dict:
            """Check a taxon literal against GBIF (with GNV and COL)."""
            if not budget.tool_call():
                return REFUSED
            result, _ = ledger.run(
                "taxonomy_verifier",
                reading_for(reading, literal),
                {"literal": literal},
                served("taxonomy_verifier"),
            )
            usage = next((t for t in result.taxa if t.source == "gbif"), None)
            return {
                "outcome": result.outcome.value,
                "usage": usage
                and {"name": usage.name, "rank": usage.rank, "status": usage.status},
                "warnings": result.warnings,
            }

    if served(GEOGRAPHY):

        @agent.tool_plain
        def geocode(reading: str, fields: dict[str, str]) -> dict:
            """Check a reading's locality literals together, one per field."""
            if not budget.tool_call():
                return REFUSED
            target = reading_for(reading)
            for key, literal in fields.items():
                if key not in served(GEOGRAPHY):
                    raise ModelRetry(f"{key} is not a locality field")
                reading_for(reading, literal)
            arguments = geography_arguments(fields)
            if not budget.geocode(target, arguments):
                return {
                    "outcome": "not_checked",
                    "reason": "the run's geocoding requests are used",
                }
            result, _ = ledger.run(GEOGRAPHY, target, arguments, sorted(fields))
            return {
                "outcome": result.outcome.value,
                "field_outcomes": {
                    k: v.value for k, v in result.field_outcomes.items()
                },
            }

    if served("date_parser"):

        @agent.tool_plain
        def parse_date(
            field: str, reading: str, literal: str, year_literal: str | None = None
        ) -> dict:
            """Every reading a date literal's notation allows (G29)."""
            if not budget.tool_call():
                return REFUSED
            if field not in served("date_parser"):
                raise ModelRetry(f"{field} is not a date field")
            if year_literal:
                reading_for(reading, year_literal)
            arguments = {"literal": literal, "year_literal": year_literal}
            result, _ = ledger.run(
                "date_parser", reading_for(reading, literal), arguments, [field]
            )
            readings = (result.parsed or {}).get("readings", [])
            return {
                "outcome": result.outcome.value,
                "readings": [
                    {k: r[k] for k in ("iso", "precision", "order")} for r in readings
                ],
                "warnings": result.warnings,
            }

    if served("catalog_number_validator"):

        @agent.tool_plain
        def check_catalog_number(reading: str, literal: str) -> dict:
            """Check an FMNH INS catalog number literal."""
            if not budget.tool_call():
                return REFUSED
            result, _ = ledger.run(
                "catalog_number_validator",
                reading_for(reading, literal),
                {"literal": literal},
                served("catalog_number_validator"),
            )
            return {
                "outcome": result.outcome.value,
                "catalog_number": (result.parsed or {}).get("catalog_number"),
            }
