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
- place_within_settled_places and place_chain (`_place_marks`, `fits`): a place below the country,
  settled on a source record that names its parents (a Getty TGN, Wikidata or NGA candidate the
  value cites, derive._settling_candidate), is marked only when its record and the record of a
  place settled above it share an identity that shows it lies outside that place. Only the
  country can be shown so: a place lies in one nation, and its record's country and the settled
  country differ by ISO 3166-1 code, or are two Getty TGN nations' records, the place's TGN chain
  ending at a nation the stage knows (`tgn_nations`). Below the country the check is inside (the
  settled place's record is among the record's parents) or abstains: TGN places a place under
  several parents and the records read give its preferred chain alone (Aurora, tgn:2015136, under
  Arapahoe County and also Adams County), and the coordinator's ruling of WP 2.3a's review round 2
  marks a province or a county only when the record's whole parent set is known, which today's
  reader does not give. The check abstains too on two gazetteers' records, NGA's parents (named,
  with no record of their own), Wikidata's (its direct P131 places), a parent of the settled
  place's name but another record, a TGN chain not known to reach its nation (cut short where a
  parent shares another's name, or an ancestor is missing), a place settled on GEOLocate (never
  read: its parents are the places the expert's query named, with no record), and a place an
  earlier attempt settled whose record cannot be read again (`stored_answers`). A failure at the
  country marks the place with place_within_settled_places.
- place_parents_derived (`_place_marks`): a derived country (layer "derived") that a place settled
  below it lies outside, by the same test, is marked itself; a person's derived place is not, and
  the place below it is marked instead.
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
from collections import Counter
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

def _source(authority_id: str | None) -> str | None:
    """The gazetteer of a record id ("tgn:1000565" -> "tgn"), or None."""
    return authority_id.partition(":")[0] if authority_id and ":" in authority_id else None


# Getty TGN's place type for a nation, as its records' kinds name it (georef_tgn.NATIONS's label).
TGN_NATION = "nations"


def tgn_nations(answers: Iterable[SourceAnswer], country=None) -> frozenset[str]:
    """The Getty TGN records the stage knows are nations: a TGN candidate of the answers given
    whose kinds name TGN's nation type (TGN_NATION), and the settled country's own TGN record
    (`country`, an agreement.PlaceField). A parent carries no type (contracts.PlaceRef), so a
    parent is known to be a nation only through these."""
    found = {candidate.authority_id for answer in answers for candidate in answer.candidates
        if _source(candidate.authority_id) == "tgn"
        and TGN_NATION in {kind.strip() for kind in (candidate.kind or "").split(",")}}
    if country is not None and _source(country.authority_id) == "tgn":
        found.add(country.authority_id)
    return frozenset(found)


def fits(candidate: SourceCandidate, upper: str, place, nations: Collection[str] = ()) -> bool | None:
    """Whether the source record a place settled on lies in the place settled for the field
    `upper` above it (an agreement.PlaceField: its record and, for the country, the ISO code that
    record carries), by an identity both records carry; None where they carry none it can
    compare (the check abstains).
    - True: the settled place's record is one of the record's parents; or, for the country, the
      record's last parent, its country (sources._place), and the settled country carry the same
      ISO 3166-1 code (agreement.country_code).
    - False, for the country only: those two codes differ; or both records are Getty TGN's, the
      record's parents are all TGN records, and its last parent is a nation the stage knows
      (`nations`, tgn_nations) other than the settled country's record. A place lies in one
      nation, so two nations' records conflict. A TGN chain is taken to reach its nation only
      then: sources._place drops a parent whose name another parent has (Guatemala City's
      department Guatemala keeps the nation Guatemala out), and georef_tgn._place stops a chain
      at an ancestor its response lacks.
    Below the country it is True or None, never False (the coordinator's ruling of WP 2.3a's
    review round 2): TGN places a place under several parents (Aurora, tgn:2015136, under
    Arapahoe County and Adams County), and the records read give its preferred chain alone
    (georef_tgn), so a province or a county missing from it is not shown to be outside. A parent
    with the settled place's name and another record, or none, is never that place."""
    from .agreement import country_code

    parents = candidate.parents
    if place.authority_id and place.authority_id in {parent.authority_id for parent in parents}:
        return True
    if upper != "country" or not parents:
        return None
    mine, theirs = country_code(parents[-1].iso_code), country_code(place.iso_code)
    if mine and theirs:
        return mine == theirs
    if (_source(place.authority_id) == "tgn" == _source(candidate.authority_id)
            and all(_source(parent.authority_id) == "tgn" for parent in parents)
            and parents[-1].authority_id in nations):
        return False
    return None


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
    made it (Run.tool_calls). Each row is rebuilt on its own: its lookup is asked again of a
    sources.ApprovedSources of its own (no answer cached from another row) through a transport
    that serves only the responses that row's stored record lists (its `exchanges`), so nothing
    is sent and no other row's response is read. The rebuilt answer counts only when every
    request it made was one of those responses and its evidence excerpt is the row's; it then
    carries the row itself. Returns the answers, and the ids of the rows that could not be read
    again (no blob store, no call, a response missing or not that row's, or another excerpt)."""
    from .sources import ApprovedSources, SourceSlots

    rows = {item.id: item for item in run.evidence}
    calls = {call.evidence_id: call for call in run.tool_calls if call.evidence_id}
    wanted = [i for i in dict.fromkeys(evidence_ids)
        if (row := rows.get(i)) is not None and row.source in GAZETTEERS and row.kind == "authority"]
    missing: set[str] = set()
    jobs = []
    for i in wanted:
        row, call = rows[i], calls.get(i)
        try:
            record = json.loads(blobs.get(row.raw_ref))
            bodies = {exchange["url"]: (exchange.get("http_status", 200), blobs.get(exchange["raw_ref"]))
                for exchange in record["exchanges"]}
        except Exception:  # noqa: BLE001 - any failure to read a stored record is a record not read
            missing.add(i)
            continue
        if call is None or call.source != row.source or not call.field_keys:
            missing.add(i)
            continue
        jobs.append((row, call, bodies))
    if not jobs:
        return [], missing

    async def rebuild(row, call, bodies) -> SourceAnswer | None:
        strays: list[str] = []

        def serve(request: httpx.Request) -> httpx.Response:
            found = bodies.get(str(request.url))
            if found is None:
                strays.append(str(request.url))
                return httpx.Response(404)
            return httpx.Response(found[0], content=found[1])

        async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
            sources = ApprovedSources(blobs=_Scratch(), client=client, sleep=_no_wait, clock=lambda: 0.0,
                slots=SourceSlots({}, wait_seconds=None))
            try:
                answer = await sources.lookup(call.source, str(call.arguments.get("query", "")),
                    field_key=call.field_keys[0])
            finally:
                sources.close()
        if strays or answer.evidence is None or answer.evidence.excerpt != row.excerpt:
            return None
        return dataclasses.replace(answer, evidence=row)

    async def ask() -> list[SourceAnswer]:
        found = []
        for row, call, bodies in jobs:
            answer = await rebuild(row, call, bodies)
            if answer is None:
                missing.add(row.id)
            else:
                found.append(answer)
        return found

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(ask()), missing
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, ask()).result(), missing


def _place_field(key: str, value: FieldValue, answers: Sequence[SourceAnswer]):
    """A settled place value as `fits` compares it: its record, and for the country the ISO code
    that record carries (step._record_code, among the answers given, which hold earlier
    attempts' records read again). Its texts are left out: a name is no identity."""
    from .agreement import PlaceField
    from .step import _record_code

    return PlaceField((), value.authority_id, _record_code(value, answers) if key == "country" else None)


def _named(value: FieldValue) -> str:
    return value.normalized or value.parsed or value.literal or ""


def _place_marks(fields: Mapping[str, FieldValue], answers: Sequence[SourceAnswer], human: Collection[str],
        tally: Counter | None = None) -> list[Mark]:
    """The places that fail a place check (`fits` is False); `tally` counts, by check, the pairs
    checked ("<check>:checked") and those the check abstained on ("<check>:abstained")."""
    from .agreement import PLACE_ORDER

    tally = Counter() if tally is None else tally
    places = {key: _place_field(key, fields[key], answers) for key in PLACE_ORDER if settled(fields.get(key))}
    nations = tgn_nations(answers, places.get("country"))
    marks: list[Mark] = []
    for lower in PLACE_ORDER[1:]:
        value = fields.get(lower)
        if lower not in places or value.layer == "derived":
            continue
        candidate = settling_candidate(value, answers)
        if candidate is None or not candidate.parents:
            tally["place:no_record_read"] += 1
            continue
        record = ", ".join(parent.name for parent in candidate.parents)
        for upper in PLACE_ORDER[:PLACE_ORDER.index(lower)]:
            if upper not in places:
                continue
            above = fields[upper]
            derived = above.layer == "derived" and upper not in human
            check = PLACE_PARENTS_DERIVED if derived else PLACE_CHAIN if upper == "county" else PLACE_WITHIN
            tally[f"{check}:checked"] += 1
            verdict = fits(candidate, upper, places[upper], nations)
            if verdict is None:
                tally[f"{check}:abstained"] += 1
            if verdict is not False:
                continue
            cited = tuple(dict.fromkeys([*value.evidence_ids, *above.evidence_ids]))
            if derived:
                marks.append(Mark(upper, PLACE_PARENTS_DERIVED,
                    f"Marked for a person, rule {PLACE_PARENTS_DERIVED}: this {LEVEL_NAMES[upper]} was derived "
                    f"({above.authority_id}), and the {LEVEL_NAMES[lower]} settled below it, {_named(value)!r}, lies in "
                    f"{record} by its source's record ({candidate.authority_id}), not in it.", cited))
            elif lower not in human:
                marks.append(Mark(lower, check,
                    f"Marked for a person, rule {check}: the source's record for {_named(value)!r} "
                    f"({candidate.authority_id}) places it in {record}, not in the {LEVEL_NAMES[upper]} settled "
                    f"above it, {_named(above)!r} ({above.authority_id}).", cited))
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
        researched: Collection[str], derived: Collection[str], human: Collection[str], blobs=None,
        tally: Counter | None = None) -> list[str]:
    """Run the checks over the run's settled values, in memory; the codes of the marks made.

    `received` is every source answer of this attempt, by field. A settled place cites, as its
    evidence, the gazetteer answers it settled on; those this attempt did not receive (an
    earlier attempt's) are read again from `blobs`, the record's blob store (`stored_answers`);
    a place whose record cannot be read again is not checked (the check abstains). `tally`
    counts what the place checks checked and abstained on, and the records not read again.
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
    if tally is not None:
        tally["place:records_not_read_again"] += len(unread)
    again = {*researched, *derived, "date_visited_from", "date_identified"}
    run.findings[:] = [finding for finding in run.findings
        if not (finding.rule_id == CHECK_STAGE and finding.field_key in again)]
    for key in derived:
        value = run.fields.get(key)
        if settled(value) and value.layer == "derived" and (sentence := basis(key)) is not None:
            _with_sentence(value, sentence)
    made: list[str] = []
    present = {(finding.field_key, finding.reason_code) for finding in run.findings if finding.rule_id == CHECK_STAGE}
    for mark in [*_place_marks(run.fields, answers, human, tally), *_date_marks(run.fields, human)]:
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
