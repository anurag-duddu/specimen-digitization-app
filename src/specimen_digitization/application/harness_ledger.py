"""The harness's tool ledger (HARNESS.md section 10).

Every tool the harness may use runs here (HAR-007), once per distinct request,
and every request is recorded as the data contract reads it (#88, section 4.3):
one `ToolCallRecord` per source-call attempt and one `Evidence` per final
source call. The ledger also turns a result into what one field sees
(`Called`), so field resolution decides from recorded outcomes only.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from .domain import Evidence, Lookup, LookupStatus, ToolCallRecord, now
from .field_resolution import DECIDED, Called, FieldCall, Reading, Relation
from .harness_tools import GeographyQuery, LocalityLiteral, SourceCall, ToolResult

PHASES = {
    "taxonomy_verifier": "lookup",
    "geography_lookup": "lookup",
    "date_parser": "validate",
    "catalog_number_validator": "validate",
}
# Tool warnings that become findings when a call settles a field (G23).
FINDING_PREFIXES = ("taxonomy_source_disagreement:", "taxonomy_support_unavailable:")
GOOGLE = "google-maps-geocoding"


@dataclass(frozen=True)
class Tools:
    """The tool implementations, injected so that tests use fakes. Each takes
    the literal and the text of the reading it was copied from."""

    verify_taxon: Callable[[str], object]  # -> taxonomy_tool.Verification
    geocode: Callable[[GeographyQuery], ToolResult]
    parse_date: Callable[..., ToolResult]  # (literal, *, source_text, year_literal)
    check_catalog_number: Callable[..., ToolResult]  # (literal, *, source_text)


def call_key(record: dict) -> str:
    """The call key agreed with S5 (#88, section 3.1), stable across replays."""
    arguments = json.dumps(record["arguments"], sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(arguments.encode()).hexdigest()[:16]
    parts = (
        record["phase"],
        record["tool"],
        record["source"] or "-",
        record["input_source"],
        record["region_id"] or "-",
        record["observation_id"] or "-",
        digest,
        str(record["attempt"]),
    )
    return ":".join(parts)


class ToolLedger:
    def __init__(self, tools: Tools, *, asset_id: str, clock=now) -> None:
        self.tools = tools
        self.asset_id = asset_id
        self.clock = clock
        self.records: list[ToolCallRecord] = []
        self.evidence: list[Evidence] = []
        self.lookups: list[Lookup] = []  # GBIF's, for the policy's taxonomy gate
        self._done: dict[str, tuple[ToolResult, dict[str, str]]] = {}

    def run(
        self,
        tool: str,
        reading: Reading,
        arguments: dict,
        field_keys: Sequence[str],
    ) -> tuple[ToolResult, dict[str, str]]:
        """Run one request, or return its recorded result: the tool's result
        and the evidence id of each source's final call."""
        if tool not in PHASES:
            raise ValueError(f"tool_not_allowed:{tool}")
        key = json.dumps([tool, reading.observation_id, arguments], sort_keys=True)
        if key not in self._done:
            started = self.clock()
            result = self._dispatch(tool, reading, arguments)
            evidence = self._record(
                tool, reading, arguments, field_keys, result, started
            )
            self._done[key] = (result, evidence)
        return self._done[key]

    def _dispatch(self, tool: str, reading: Reading, arguments: dict) -> ToolResult:
        if tool == "taxonomy_verifier":
            verification = self.tools.verify_taxon(arguments["literal"])
            self.lookups.append(verification.gbif)
            return verification.result
        if tool == "geography_lookup":
            query = GeographyQuery(
                literals=[
                    LocalityLiteral(
                        field_key=field_key,
                        literal=literal,
                        source_observation_id=reading.observation_id,
                        source_region_id=reading.region_id,
                    )
                    for field_key, literal in arguments["literals"]
                ]
            )
            return self.tools.geocode(query)
        if tool == "date_parser":
            return self.tools.parse_date(
                arguments["literal"],
                source_text=reading.text,
                year_literal=arguments.get("year_literal"),
            )
        return self.tools.check_catalog_number(
            arguments["literal"], source_text=reading.text
        )

    def _record(
        self, tool, reading, arguments, field_keys, result, started
    ) -> dict[str, str]:
        """One record per source-call attempt (a validator's call is its own
        single attempt) and one evidence item per source's final call."""
        completed = self.clock()
        attempts = list(result.sub_calls) or [None]
        finals = {c.source: c for c in result.sub_calls}  # The last attempt wins.
        evidence: dict[str, str] = {}
        for attempt in attempts:
            source = attempt.source if attempt is not None else None
            final = attempt is None or finals[source] is attempt
            evidence_id = None
            if final:
                item = self._evidence(tool, reading, result, attempt)
                self.evidence.append(item)
                evidence_id = evidence[source or tool] = item.id
            fields = {
                "phase": PHASES[tool],
                "tool": tool,
                "source": source,
                "input_source": reading.role,
                "region_id": reading.region_id,
                # A call on the decided transcript names no reading (#88, 4.4).
                "observation_id": None
                if reading.role == DECIDED
                else reading.observation_id,
                "attempt": attempt.attempt if attempt is not None else 1,
                "arguments": arguments,
            }
            self.records.append(
                ToolCallRecord(
                    call_key=call_key(fields),
                    tool_version=result.tool_version,
                    field_keys=list(field_keys),
                    outcome=attempt.outcome if attempt is not None else result.outcome,
                    result=_bounded(tool, result, attempt),
                    evidence_id=evidence_id,
                    started_at=started,
                    completed_at=completed,
                    **fields,
                )
            )
        return evidence

    def _evidence(
        self, tool, reading, result: ToolResult, attempt: SourceCall | None
    ) -> Evidence:
        """No Google text ever reaches evidence: only its place ID (G26)."""
        outcome = attempt.outcome if attempt is not None else result.outcome
        source = attempt.source if attempt is not None else tool
        return Evidence(
            kind="lookup" if attempt is not None else "validation",
            asset_id=self.asset_id,
            region_id=reading.region_id,
            observation_ids=[reading.observation_id],
            source=source,
            locator=_locator(source, outcome, result, reading, attempt),
            excerpt=f"{source} {outcome.value}",
            raw_ref=attempt.raw_ref if attempt is not None else None,
            digest=attempt.response_sha256 if attempt is not None else None,
        )

    def field_call(
        self, field_key: str, tool: str, arguments_for: Callable[[str, Reading], dict]
    ) -> FieldCall:
        """The FieldCall the resolver uses for one field on one tool."""

        def call(literal: str, reading: Reading) -> Called:
            arguments = arguments_for(literal, reading)
            result, evidence = self.run(
                tool, reading, arguments, served(tool, arguments, field_key)
            )
            return called(field_key, literal, result, evidence)

        return call


def served(tool: str, arguments: dict, field_key: str) -> list[str]:
    """The fields a request serves: one geography call serves every locality
    field of its reading (#88, section 3.1)."""
    if tool == "geography_lookup":
        return [key for key, _ in arguments["literals"] if key is not None]
    return [field_key]


def called(
    field_key: str, literal: str, result: ToolResult, evidence: Mapping[str, str]
) -> Called:
    """What one tool result settles for one field. The geography tool reports
    only the admin-level fields; precise_location is transcribed, never settled
    by a geocoder result (PRD 515), so asking for it is refused."""
    if result.tool == "geography_lookup" and field_key not in result.field_outcomes:
        raise ValueError(f"field_not_reported:{field_key}")
    outcome = result.field_outcomes.get(field_key, result.outcome)
    warnings = {
        code: tuple(filter(None, [evidence.get(code.split(":", 1)[1])]))
        for code in result.warnings
        if code.startswith(FINDING_PREFIXES)
    }
    if outcome != LookupStatus.SUCCESS:
        return Called(outcome, result.tool, warnings=warnings)
    if result.tool == "taxonomy_verifier":
        taxon = next(t for t in result.taxa if t.source == "gbif")
        relations: dict[str, Relation] = {evidence["gbif"]: "decides"}
        for source in ("gnv", "col"):
            if source in evidence and not any(
                w.endswith(f":{source}") for w in result.warnings
            ):
                relations[evidence[source]] = "supports"
        return Called(
            outcome,
            result.tool,
            authority_id=taxon.usage_key,
            normalized=taxon.name,
            evidence=relations,
            warnings=warnings,
        )
    if result.tool == "geography_lookup":
        place = next(p for p in result.places if p.field_key == field_key)
        source = evidence[place.source]  # The place's own source's call.
        near = f"near_spelling:{field_key}"
        if near in result.warnings:
            # G34: the place ID alone, no name; a warning finding shows it.
            return Called(
                outcome,
                result.tool,
                authority_id=place.source_record_id,
                evidence={source: "supports"},
                warnings={near: (source,)},
            )
        if place.source != GOOGLE and place.name:
            # An openly licensed name, kept with its credit (PLAN 4.8).
            return Called(
                outcome,
                result.tool,
                authority_id=place.source_record_id,
                normalized=place.name,
                authority_identity={
                    "name": place.name,
                    "source": place.source,
                    "source_record_id": place.source_record_id,
                    "credit": place.credit,
                },
                evidence={source: "supports"},
            )
        # The literal the lookup matched by name, never a Google name (G26).
        return Called(
            outcome,
            result.tool,
            authority_id=place.source_record_id,
            normalized=literal,
            evidence={source: "supports"},
        )
    if result.tool == "date_parser":
        (reading,) = result.parsed["readings"]
        return Called(
            outcome,
            result.tool,
            parsed=reading["iso"],
            precision=reading["precision"],
            century_rule=reading["century_rule"],
            evidence={evidence["date_parser"]: "supports"},
        )
    return Called(
        outcome,
        result.tool,
        parsed=result.parsed["catalog_number"],
        evidence={evidence["catalog_number_validator"]: "supports"},
    )


def _locator(
    source, outcome, result: ToolResult, reading: Reading, attempt
) -> str | None:
    """A lookup's locator is set exactly when it succeeded (#88, section 4.4);
    a validator's evidence is not a lookup and keeps its region."""
    if attempt is None:
        return f"region:{reading.region_id}"
    if outcome != LookupStatus.SUCCESS:
        return None
    if result.tool == "geography_lookup":
        # The record the source's place names: Google's place ID, or an open
        # source's record id (PLAN 4.8).
        place_id = next(
            (p.source_record_id for p in result.places if p.source == source), None
        )
        return f"place/{place_id}" if place_id else None
    if source == "gbif":
        taxon = next((t for t in result.taxa if t.source == "gbif"), None)
        return f"usage/{taxon.usage_key}" if taxon else None
    return f"name/{attempt.query.get('name') or attempt.query.get('q')}"


def _bounded(tool: str, result: ToolResult, attempt: SourceCall | None) -> dict:
    """What a record keeps of the result: bounded, and for Google place IDs
    only (#88, section 6)."""
    kept: dict = {}
    if attempt is not None:
        if attempt.sanitized_error:
            kept["error"] = attempt.sanitized_error
        if attempt.retry_after_seconds is not None:
            kept["retry_after"] = attempt.retry_after_seconds
        if attempt.source == GOOGLE:
            kept["place_ids"] = sorted(
                {p.source_record_id for p in result.places if p.source_record_id}
            )
        elif attempt.source == "gbif":
            kept["candidates"] = [t.model_dump(mode="json") for t in result.taxa]
        return kept
    return {"parsed": result.parsed, "warnings": list(result.warnings)}
