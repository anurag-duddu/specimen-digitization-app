"""The check stage: the settled values checked against the specimen ontology's rules
(docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4, "The check
stage"; docs/execution/units/PLAN.md, WP 2.3, its first part, 2.3a).

On the units path only (step.units_path), step.apply_outcomes runs `stage` last: after every
expert has answered, derivation has filled the open fields (derive.fill), the fields the label
does not state are marked so (step.mark_not_on_label) and each label's settlement is recorded
(step._settlement). The stage never revises a value. A failed check marks the field:
- a warning finding of rule CHECK_STAGE per label of the value, whose code is step.marked_code's
  `marked:<field>:<label>:<check>`, the check being the id of the ontology rule that failed
  (ontology/specimen.yaml); step.marked_reasons makes each one of the run's reasons;
- a sentence at the end of the value's reason, "Marked for a person, rule <id>: ...", that lists
  what failed the check.

The checks:
- place_within_settled_places and place_chain (`_place_marks`): a place below the country settled
  on a source record that names its parents (a Getty TGN, Wikidata or NGA candidate the value
  cites, derive._settling_candidate) lies in each place settled above it, as far as the record's
  parents say (`fits`). Its country is the record's last parent (sources._place puts the country
  last), so a parent of another level that has the country's name is not its country: the
  country Georgia settled, a county Fulton whose record names the US state Georgia and the United
  States is outside it. A place outside the country or the province settled above it fails
  place_within_settled_places, which the refusal at apply time checks too
  (agreement.parents_refusal); a city outside the county settled above it fails place_chain,
  which that refusal checks only for a near spelling: a settled Coles County, then an exact
  "Chicago" whose record names Cook County, Illinois. A place settled in an earlier attempt is
  checked on its record read again from the store (`stored_answers`); one whose cited record
  cannot be read again, below a place settled in this attempt, is marked (place_chain), as its
  place in that chain is not checked.
- place_parents_derived (`_place_marks`): a place derivation filled (layer "derived") that a
  place settled below it does not lie in, by the same test, is marked itself; a person's
  derived place is not, and the place below it is marked instead.
- date_order (`_date_marks`): a determination date before the collecting date, compared on the
  parts both have (`determined_before`), marks the determination, both dates listed.

The stage also adds the sentence "Basis: derived, rule <id>." (DERIVED_RULES) to the reason of
each value derive.fill derived in this attempt, after the derivation's own text and before any
mark's sentence, so that every derived value names its rule, marked or not (the plan's WP 2.3
acceptance).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import dataclasses
import hashlib
import json
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import NamedTuple

import httpx

from specimen_digitization.application.domain import Evidence, FieldValue, RunFinding, ValueState

from .contracts import GAZETTEERS, Reading, SourceAnswer, SourceCandidate

# The stage's findings (RunFinding.rule_id) and their version.
CHECK_STAGE = "check_stage"
CHECK_STAGE_RULES = "field-research-check-stage-v1"
# The checks, by the ids of the ontology rules they check (ontology/specimen.yaml).
PLACE_WITHIN = "place_within_settled_places"
PLACE_CHAIN = "place_chain"
PLACE_PARENTS_DERIVED = "place_parents_derived"
DATE_ORDER = "date_order"
CHECKS = (PLACE_WITHIN, PLACE_CHAIN, PLACE_PARENTS_DERIVED, DATE_ORDER)
# The rule each field derive.fill derives follows: a place from a settled place's parents, an
# elevation from a stated one, the end of a single collecting date.
DERIVED_RULES = {
    "country": PLACE_PARENTS_DERIVED, "province_state": PLACE_PARENTS_DERIVED, "county": PLACE_PARENTS_DERIVED,
    "elevation_from_m": "elevation_conversion", "elevation_to_m": "elevation_conversion",
    "elevation_from_ft": "elevation_conversion", "elevation_to_ft": "elevation_conversion",
    "date_visited_to": "end_date_from_one_date",
}
LEVEL_NAMES = {"country": "country", "province_state": "province or state", "county": "county", "city": "city"}
# The layers of a value the stage checks: settled from the label, or derived.
CHECKED_LAYERS = frozenset({"verbatim", "settled", "derived"})
ISO_DATE = re.compile(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?")


class Mark(NamedTuple):
    """A failed check: the field it marks, the check (an ontology rule's id), the sentence its
    reason ends with, and the evidence the finding cites."""

    field: str
    check: str
    sentence: str
    evidence_ids: tuple[str, ...] = ()


def settled(value: FieldValue | None) -> bool:
    """Whether a value is one the stage checks: supported, in a layer research settled or
    derived (CHECKED_LAYERS)."""
    return value is not None and value.state == ValueState.SUPPORTED and value.layer in CHECKED_LAYERS


# ---- dates -------------------------------------------------------------------------------

def date_parts(value: FieldValue | None) -> tuple[int, ...] | None:
    """A settled date's parts, year first, as many as its precision writes ("1946" -> (1946,),
    "1946-09-06" -> (1946, 9, 6)): of its normalized, else parsed, else literal text, when that is
    an ISO date; None otherwise."""
    if value is None:
        return None
    found = ISO_DATE.fullmatch(value.normalized or value.parsed or value.literal or "")
    return tuple(int(part) for part in found.groups() if part is not None) if found else None


def determined_before(collected: Sequence[int], identified: Sequence[int]) -> bool:
    """Whether a determination date is before the collecting date, compared on the parts both
    dates have (date_order): "1946" and "1946-09-06" agree, the same day is allowed."""
    both = min(len(collected), len(identified))
    return tuple(identified[:both]) < tuple(collected[:both])


def _iso(parts: Sequence[int]) -> str:
    return "-".join([f"{parts[0]:04d}", *(f"{part:02d}" for part in parts[1:])])


def _date_marks(fields: Mapping[str, FieldValue], human: Collection[str]) -> list[Mark]:
    collected, identified = fields.get("date_visited_from"), fields.get("date_identified")
    if not (settled(collected) and settled(identified)):
        return []
    start, determined = date_parts(collected), date_parts(identified)
    if start is None or determined is None or not determined_before(start, determined):
        return []
    # The determination is marked; a person's determination date marks the collecting date instead.
    field = next((key for key in ("date_identified", "date_visited_from") if key not in human), None)
    if field is None:
        return []
    sentence = (f"Marked for a person, rule {DATE_ORDER}: the determination date {_iso(determined)} is before the "
        f"collecting date {_iso(start)}.")
    cited = tuple(dict.fromkeys(i for value in (collected, identified) for i in value.evidence_ids))
    return [Mark(field, DATE_ORDER, sentence, cited)]


# ---- places ------------------------------------------------------------------------------

def fits(candidate: SourceCandidate, lower: str, upper: str, places: Mapping[str, object]) -> bool:
    """Whether the source record a place settled for the field `lower` settled on lies in the
    place settled for the field `upper` above it, by what the record's parents (nearest first)
    say about that place's level; `places` holds the settled places by field
    (agreement.PlaceField), and a parent is one of them by record, name or code
    (agreement.lies_in).
    - The country: the record's last parent, its country (sources._place), is the settled
      country. A parent of another level with the country's name is not its country.
    - A province: a parent nearer than the record's country is the settled province; or, for a
      city, the settled county, which is checked against the province itself; or the record
      names no parent nearer than its country, and says nothing of a province.
    - A county, for a city: a parent nearer than its country is the settled county; or the
      record names no parent nearer than the settled province it names (or its country, where
      it names no settled province): NGA names a town's first-level unit and its country only,
      and says nothing of a county."""
    from .agreement import lies_in

    parents = candidate.parents

    def named(key: str, parent) -> bool:
        return key in places and lies_in(dataclasses.replace(candidate, parents=(parent,)), key, places[key])

    if upper == "country":
        return named("country", parents[-1])
    # The parents nearer than the record's country: all but the last; a single parent that is not
    # the settled country may be any level.
    nearer = parents[:-1] if len(parents) > 1 or named("country", parents[-1]) else parents
    if any(named(upper, parent) for parent in nearer):
        return True
    if upper == "province_state":
        return (lower == "city" and any(named("county", parent) for parent in nearer)) or not nearer
    province = next((index for index, parent in enumerate(nearer) if named("province_state", parent)), len(nearer))
    return not nearer[:province]


def settling_candidate(value: FieldValue, answers: Iterable[SourceAnswer]) -> SourceCandidate | None:
    """The source record a place value settled on (derive._settling_candidate, never GEOLocate's)
    among answers of any field whose evidence the value cites, or None."""
    from .derive import _settling_candidate

    return _settling_candidate(value, [answer for answer in answers if answer.evidence is not None])


class _Scratch:
    """A blob store that keeps what it is given in memory: what a rebuilt lookup stores is
    never written to the record's store."""

    def __init__(self):
        self.blobs: dict[str, bytes] = {}

    def put(self, data: bytes) -> str:
        ref = hashlib.sha256(data).hexdigest()
        self.blobs[ref] = data
        return ref

    def get(self, ref: str) -> bytes:
        return self.blobs[ref]


async def _no_wait(_seconds: float) -> None:
    await asyncio.sleep(0)


def stored_answers(run, blobs, evidence_ids: Iterable[str]) -> tuple[list[SourceAnswer], set[str]]:
    """The gazetteer answers behind these evidence rows, read again from the record's blob store:
    each row a Getty TGN, Wikidata or NGA lookup stored (kind "authority"), with the call that
    made it (Run.tool_calls). The lookup is asked again of sources.ApprovedSources through a
    transport that serves only the responses the row's stored record lists (its `exchanges`), so
    nothing is sent; the rebuilt answer counts only when its evidence excerpt is the row's, and
    it then carries the row itself. Returns the answers, and the ids of the rows that could not
    be read again (no blob store, no call, a response missing, or another excerpt)."""
    from .sources import ApprovedSources, SourceSlots

    rows = {item.id: item for item in run.evidence}
    calls = {call.evidence_id: call for call in run.tool_calls if call.evidence_id}
    wanted = [i for i in dict.fromkeys(evidence_ids)
        if (row := rows.get(i)) is not None and row.source in GAZETTEERS and row.kind == "authority"]
    missing: set[str] = set()
    jobs, bodies = [], {}
    for i in wanted:
        row, call = rows[i], calls.get(i)
        try:
            record = json.loads(blobs.get(row.raw_ref))
            for exchange in record["exchanges"]:
                bodies[exchange["url"]] = (exchange.get("http_status", 200), blobs.get(exchange["raw_ref"]))
        except Exception:  # noqa: BLE001 - any failure to read a stored record is a record not read
            missing.add(i)
            continue
        if call is None or call.source != row.source or not call.field_keys:
            missing.add(i)
            continue
        jobs.append((row, call))
    if not jobs:
        return [], missing

    def serve(request: httpx.Request) -> httpx.Response:
        found = bodies.get(str(request.url))
        return httpx.Response(404) if found is None else httpx.Response(found[0], content=found[1])

    async def ask() -> list[SourceAnswer]:
        found = []
        async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
            sources = ApprovedSources(blobs=_Scratch(), client=client, sleep=_no_wait, clock=lambda: 0.0,
                slots=SourceSlots({}, wait_seconds=None))
            try:
                for row, call in jobs:
                    answer = await sources.lookup(call.source, str(call.arguments.get("query", "")),
                        field_key=call.field_keys[0])
                    if answer.evidence is None or answer.evidence.excerpt != row.excerpt:
                        missing.add(row.id)
                        continue
                    found.append(dataclasses.replace(answer, evidence=row))
            finally:
                sources.close()
        return found

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(ask()), missing
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, ask()).result(), missing


def _place_field(key: str, value: FieldValue, rows: Mapping[str, Evidence], answers: Sequence[SourceAnswer]):
    """A settled place value as agreement.lies_in compares it: its literal, value and expansions
    (step._expansions), the name of the record it settled on, its record, and for the country the
    code that record carries (step._record_code)."""
    from .agreement import PlaceField
    from .step import _expansions, _record_code

    found = settling_candidate(value, answers)
    names = [text for text in (value.literal, value.normalized, value.parsed, *_expansions(key, value, rows),
        found.name if found is not None else None) if text]
    code = _record_code(value, answers) if key == "country" else None
    return PlaceField(tuple(dict.fromkeys(names)), value.authority_id, code)


def _named(value: FieldValue) -> str:
    return value.normalized or value.parsed or value.literal or ""


def _place_marks(fields: Mapping[str, FieldValue], rows: Mapping[str, Evidence], answers: Sequence[SourceAnswer],
        human: Collection[str], unread: Collection[str] = (), again: Collection[str] = ()) -> list[Mark]:
    from .agreement import PLACE_ORDER

    places = {key: _place_field(key, fields[key], rows, answers) for key in PLACE_ORDER if settled(fields.get(key))}
    marks: list[Mark] = []
    for lower in PLACE_ORDER[1:]:
        value = fields.get(lower)
        if lower not in places or value.layer == "derived":
            continue
        candidate = settling_candidate(value, answers)
        lost = [i for i in value.evidence_ids if i in unread]
        if candidate is None and lost and lower not in human and any(
                upper in places and upper in again for upper in PLACE_ORDER[:PLACE_ORDER.index(lower)]):
            # The record it settled on in an earlier attempt cannot be read again, and a place above
            # it settled in this attempt: its place in that chain is not checked, so it is never
            # taken as consistent.
            marks.append(Mark(lower, PLACE_CHAIN,
                f"Marked for a person, rule {PLACE_CHAIN}: the source's record {_named(value)!r} settled on "
                f"(evidence {', '.join(lost)}) could not be read again, so its place in the chain is not checked.",
                tuple(value.evidence_ids)))
            continue
        if candidate is None or not candidate.parents:
            continue
        record = ", ".join(parent.name for parent in candidate.parents)
        for upper in PLACE_ORDER[:PLACE_ORDER.index(lower)]:
            if upper not in places or fits(candidate, lower, upper, places):
                continue
            above = fields[upper]
            cited = tuple(dict.fromkeys([*value.evidence_ids, *above.evidence_ids]))
            if above.layer == "derived" and upper not in human:
                marks.append(Mark(upper, PLACE_PARENTS_DERIVED,
                    f"Marked for a person, rule {PLACE_PARENTS_DERIVED}: this {LEVEL_NAMES[upper]} was derived, and "
                    f"the {LEVEL_NAMES[lower]} settled below it, {_named(value)!r}, lies in {record} by its source's "
                    f"record ({candidate.authority_id}), not in it.", cited))
            elif lower not in human:
                check = PLACE_CHAIN if upper == "county" else PLACE_WITHIN
                marks.append(Mark(lower, check,
                    f"Marked for a person, rule {check}: the source's record for {_named(value)!r} "
                    f"({candidate.authority_id}) places it in {record}, not in the {LEVEL_NAMES[upper]} settled "
                    f"above it, {_named(above)!r}.", cited))
    return marks


# ---- the stage ---------------------------------------------------------------------------

def _labels(run, key: str, readings: Sequence[Reading], rows: Mapping[str, Evidence]) -> list[str]:
    """The labels of a field's value (step._value_regions); for a derived value, those of the
    values it was derived from. [""] when it has none."""
    from .step import _value_regions

    value = run.fields[key]
    sources = [run.fields[name] for name in value.derived_from if name in run.fields] if value.layer == "derived" \
        else [value]
    found = set().union(*(_value_regions(item, readings, rows) for item in sources)) if sources else set()
    return sorted(found) or [""]


def _with_sentence(value: FieldValue, sentence: str) -> None:
    if sentence not in value.reason:
        value.reason = " ".join(part for part in (value.reason, sentence) if part)


def basis(key: str) -> str | None:
    """The basis sentence the reason of a value derive.fill derived for the field `key` holds, or None."""
    rule = DERIVED_RULES.get(key)
    return f"Basis: derived, rule {rule}." if rule else None


def stage(run, *, readings: Sequence[Reading], received: Mapping[str, Sequence[SourceAnswer]],
        researched: Collection[str], derived: Collection[str], human: Collection[str], blobs=None) -> list[str]:
    """Run the checks over the run's settled values, in memory; the codes of the marks made.

    `received` is every source answer of this attempt, by field. A settled place cites, as its
    evidence, the gazetteer answers it settled on; those this attempt did not receive (an
    earlier attempt's) are read again from `blobs`, the record's blob store (`stored_answers`).
    The fields this attempt `researched` or `derived`, and both dates, are checked again: their
    earlier marks of this stage are dropped first; a field another attempt settled keeps its
    marks, and gets no mark twice. A person's field (`human`) is never marked, whatever its
    layer. Each value this attempt derived gets its basis sentence (`basis`), before any mark's."""
    from .agreement import PLACE_ORDER
    from .step import marked_code

    rows = {item.id: item for item in run.evidence}
    answers = [answer for found in received.values() for answer in found]
    have = {answer.evidence.id for answer in answers if answer.evidence is not None}
    cited = [i for key in PLACE_ORDER if settled(value := run.fields.get(key)) for i in value.evidence_ids
        if i not in have and (row := rows.get(i)) is not None and row.source in GAZETTEERS and row.kind == "authority"]
    stored, unread = stored_answers(run, blobs, cited) if cited and blobs is not None else ([], set(cited))
    answers += stored
    again = {*researched, *derived, "date_visited_from", "date_identified"}
    run.findings[:] = [finding for finding in run.findings
        if not (finding.rule_id == CHECK_STAGE and finding.field_key in again)]
    for key in derived:
        value = run.fields.get(key)
        if settled(value) and value.layer == "derived" and (sentence := basis(key)) is not None:
            _with_sentence(value, sentence)
    made: list[str] = []
    present = {(finding.field_key, finding.reason_code) for finding in run.findings if finding.rule_id == CHECK_STAGE}
    for mark in [*_place_marks(run.fields, rows, answers, human, unread, again), *_date_marks(run.fields, human)]:
        _with_sentence(run.fields[mark.field], mark.sentence)
        for label in _labels(run, mark.field, readings, rows):
            code = marked_code(mark.field, label, mark.check)
            if (mark.field, code) in present:
                continue
            present.add((mark.field, code))
            run.findings.append(RunFinding(rule_id=CHECK_STAGE, rule_version=CHECK_STAGE_RULES, severity="warning",
                field_key=mark.field, reason_code=code, evidence_ids=list(mark.evidence_ids)))
            made.append(code)
    return made
