"""The check stage: the settled values checked against the specimen ontology's rules
(docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4, "The check
stage"; docs/execution/units/PLAN.md, WP 2.3: its first part, 2.3a, and its second, 2.3b).

WP 2.3b adds, on the units path, two steps step.apply_outcomes runs before the stage:
- wait_for_sources, right after derive.fill: a field derive.fill derives from another (an
  elevation's other end or unit, Date Visited To) that is settled absent while that source is
  held, and whose label writes that source's text, waits instead, unknown, its reason naming the
  source and with no review reason of its own (waiting_fields), so derive.fill fills it once
  the source settles, after the experts or after a person's decision (follow_sources, from
  step.refinalize) (the rules elevation_conversion and end_date_from_one_date);
- infer_feet, after each label's settlement is recorded: the rule elevation_unit_feet settles
  Elevation From (ft), cleared, when all its conditions hold at the elevation's own unit
  (foot_number), its reason "Basis: inferred, rule elevation_unit_feet: ..."; derive.fill then
  fills the elevation fields it lets derive.

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
- precise_location_extent (`_extent_marks`, WP 2.3b): a settled precise location whose literal,
  wherever a reading of its label writes it, ends its line before a line that goes on with a
  settled province or country the literal does not write, and with nothing but other settled
  fields' texts, place unit words and punctuation besides, is marked as cut short; otherwise the
  check abstains.

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
from decimal import Decimal
from functools import cache
from typing import NamedTuple

import httpx

from specimen_digitization.application.domain import Evidence, FieldValue, RunFinding, ValueState

from . import derive as derive_rules
from .contracts import GAZETTEERS, Reading, SourceAnswer, SourceCandidate

# The stage's findings (RunFinding.rule_id) and their version.
CHECK_STAGE = "check_stage"
CHECK_STAGE_RULES = "field-research-check-stage-v1"
# The checks, by the ids of the ontology rules they check (ontology/specimen.yaml).
PLACE_WITHIN = "place_within_settled_places"
PLACE_CHAIN = "place_chain"
PLACE_PARENTS_DERIVED = "place_parents_derived"
DATE_ORDER = "date_order"
PRECISE_LOCATION_EXTENT = "precise_location_extent"
CHECKS = (PLACE_WITHIN, PLACE_CHAIN, PLACE_PARENTS_DERIVED, DATE_ORDER, PRECISE_LOCATION_EXTENT)
# The keys of step.apply_outcomes' decisions under which the stage names a field's first failed
# check and what it saw (Mark.saw), for the units path's one re-ask (field_research/reask.py).
STAGE_CHECK, STAGE_SAW = "stage_check", "stage_saw"
# The inference (infer_feet), by the id of its ontology rule.
ELEVATION_UNIT_FEET = "elevation_unit_feet"
# The rule each field derive.fill derives follows, as the ontology file names it (derive.DERIVED_RULES).
DERIVED_RULES = derive_rules.DERIVED_RULES
LEVEL_NAMES = {"country": "country", "province_state": "province or state", "county": "county", "city": "city"}
# The layers of a value the stage checks: settled from the label, or derived.
CHECKED_LAYERS = frozenset({"verbatim", "settled", "derived"})
ISO_DATE = re.compile(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?")


class Mark(NamedTuple):
    """A failed check: the field it marks, the check (an ontology rule's id), the sentence its
    reason ends with, the evidence the finding cites, and what the check saw, as the units path's
    one re-ask tells the field's expert (field_research/reask.py)."""

    field: str
    check: str
    sentence: str
    evidence_ids: tuple[str, ...] = ()
    saw: str = ""


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
    saw = (f"the determination date {_iso(determined)} is before the collecting date {_iso(start)}"
        if field == "date_identified" else
        f"the collecting date {_iso(start)} is after the determination date {_iso(determined)}")
    return [Mark(field, DATE_ORDER, sentence, cited, saw)]


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
                saw = (f"the source's record for {_named(value)!r} ({candidate.authority_id}) places it in {record}, "
                    f"not in the {LEVEL_NAMES[upper]} settled above it, {_named(above)!r} ({above.authority_id})")
                marks.append(Mark(lower, check, f"Marked for a person, rule {check}: {saw}.", cited, saw))
    return marks


# ---- dependent fields (plan WP 2.3b) -------------------------------------------------------

# A source a derived field waits for: neither settled nor settled absent.
HELD = frozenset({ValueState.AMBIGUOUS, ValueState.UNRESOLVED, ValueState.UNKNOWN})
# Each field derive.fill derives from another field of the label, with its sources: an elevation
# from any other elevation (its other end, or its other unit: elevation_conversion), the end of the
# collection from its start (end_date_from_one_date).
SOURCES = {**{key: tuple(other for other in derive_rules.ELEVATIONS if other != key)
    for key in derive_rules.ELEVATIONS}, "date_visited_to": ("date_visited_from",)}
WAITS_END = "and is not settled absent before."
WAITS = ("Waits for {sources}, which is not settled: this field follows it (rule {rule}), derived from it once it "
    "settles, or not present again where it then cannot be, " + WAITS_END)


def wait_for_sources(run, *, eligible: Collection[str], readings: Sequence[Reading] = ()) -> dict[str, list[str]]:
    """On the units path, after derive.fill (step.apply_outcomes): each field of SOURCES among
    `eligible` that is settled absent (not present, with no text: derive.is_open) while one of
    its sources is held (HELD: ambiguous, unresolved or unknown) waits instead: unknown, its
    reason starting with WAITS, which names those sources and the rule derive.fill follows,
    its evidence kept. It waits only where the label writes its source's text (G51's round 1 on
    PR #437, adopted by the coordinator): an elevation partner when a reading writes an
    elevation (step._elevation_written), Date Visited To when Date Visited From holds a text (a
    literal, a reader's verbatim, or a label row of its own); a source that failed with nothing
    written keeps main's result. An unknown field with no text
    is open, so derive.fill fills it once its source settles, after the experts or after a
    person's decision (follow_sources). A source is held as the fields stand before any field
    waits. Returns each field that waits, with the sources it waits for."""
    from .prompts import FIELD_LABELS
    from .step import _elevation_written

    held = {key for key, value in run.fields.items() if value.state in HELD}
    rows = {item.id: item for item in run.evidence}
    waiting: dict[str, list[str]] = {}
    elevation = None
    for key, sources in SOURCES.items():
        value = run.fields.get(key)
        if (key not in eligible or value is None or value.state != ValueState.NOT_PRESENT
                or not derive_rules.is_open(value)):
            continue
        mine = [source for source in sources if source in held]
        if not mine:
            continue
        if key in derive_rules.ELEVATIONS:
            if elevation is None:
                elevation = _elevation_written(run, readings)
            written = elevation
        else:
            start = run.fields.get("date_visited_from")
            written = start is not None and bool((start.literal or "").strip() or any(
                (text or "").strip() for text in start.verbatim_by_observation.values()) or any(
                (row := rows.get(i)) is not None and row.kind == "literal" for i in start.evidence_ids))
        if written:
            waiting[key] = mine
    for key, mine in waiting.items():
        value = run.fields[key]
        said = WAITS.format(sources=" and ".join(FIELD_LABELS.get(source, source) for source in mine),
            rule=DERIVED_RULES[key])
        run.fields[key] = value.model_copy(update={"state": ValueState.UNKNOWN,
            "reason": " ".join(part for part in (said, value.reason) if part)})
    return waiting


def _waiting(run) -> set[str]:
    """The fields wait_for_sources made wait that still do: unknown, with no text, their reason
    starting "Waits for " and holding WAITS_END."""
    return {key for key in SOURCES if (value := run.fields.get(key)) is not None
        and value.state == ValueState.UNKNOWN and derive_rules.is_open(value)
        and value.reason.startswith("Waits for ") and WAITS_END in value.reason}


def waiting_fields(run) -> set[str]:
    """The waiting fields whose source is still held (HELD, and not itself waiting): each adds no
    review reason of its own, as its source's reason already routes the record
    (step.scientific_reasons, on the units path)."""
    waiting = _waiting(run)
    held = {key for key, value in run.fields.items() if value.state in HELD and key not in waiting}
    return {key for key in waiting if any(source in held for source in SOURCES[key])}


def follow_sources(run, *, asset_id: str | None = None, blobs=None) -> tuple[list[str], list[str]]:
    """On the units path (step.refinalize, after a person's decision): each waiting field (_waiting)
    whose sources are no longer held, its source settled by a person or otherwise, stops waiting.
    derive.fill fills it by its rule, as after the experts, its reason ending with its basis
    (`basis`); one that derivation cannot fill (its source settled absent, or not in a form the
    rule derives from) takes back the value it had before it waited: not present, with its
    expert's reason, which sends it to a person as before. A person's field is never touched.
    Returns the fields derived and those given back."""
    from .step import human_keys

    human = human_keys(run)
    waiting = _waiting(run) - human
    ready = sorted(waiting - waiting_fields(run))
    if not ready:
        return [], []
    filled = derive_rules.fill(run, eligible=ready, asset_id=asset_id, blobs=blobs, received={})
    for key in filled:
        if (sentence := basis(key)) is not None:
            _with_sentence(run.fields[key], sentence)
    back = [key for key in ready if key not in filled]
    for key in back:
        value = run.fields[key]
        run.fields[key] = value.model_copy(update={"state": ValueState.NOT_PRESENT,
            "reason": value.reason.split(WAITS_END, 1)[1].strip()})
    return filled, back


# ---- the elevation unit (plan WP 2.3b) -----------------------------------------------------

# The spellings of a foot that condition (a) of elevation_unit_feet counts, folded, periods,
# spaces and edge punctuation dropped: the foot mark (straight, curly or a prime: written.fold)
# and "ft".
FOOT_MARKS = frozenset({"'", "ft"})
FOOT_IN_METRES = Decimal("0.3048")
INFERRED = "inference:" + ELEVATION_UNIT_FEET
BARE_NUMBER = re.compile(r"\d+")


def cleared_country(run) -> FieldValue | None:
    """The run's country when it is cleared, not marked: supported, settled from the label
    (layer verbatim or settled), with a label's `cleared:country:<label>` finding (rule
    step.SETTLEMENT) and no `marked:country:` finding of any rule; else None."""
    from .step import SETTLEMENT

    value = run.fields.get("country")
    if value is None or value.state != ValueState.SUPPORTED or value.layer not in ("verbatim", "settled"):
        return None
    codes = [finding.reason_code for finding in run.findings if finding.field_key == "country"]
    if any(code.startswith("marked:country:") for code in codes):
        return None
    cleared = any(finding.rule_id == SETTLEMENT and finding.reason_code.startswith("cleared:country:")
        for finding in run.findings if finding.field_key == "country")
    return value if cleared else None


def highest_point(country: FieldValue):
    """The ontology's highest-point row of a settled country (ontology.HighestPoint): by the
    Wikidata item it settled on (authority_id "wikidata:Q<n>"), else the one row whose
    country_name is its name (its normalized value, else its parsed value, else its literal:
    _named), letter case aside; None otherwise."""
    from specimen_digitization.ontology import ontology

    table = ontology()
    if country.authority_id and country.authority_id.startswith("wikidata:"):
        return table.highest_point(country.authority_id.removeprefix("wikidata:"))
    name = _named(country).casefold()
    rows = [row for row in table.highest_points.rows if name and row.country_name.casefold() == name]
    return rows[0] if len(rows) == 1 else None


class Written(NamedTuple):
    """The one number a unit's readers write (the unit, the number, and each reader's
    observation with where the number stands in its reading and whether it has the foot mark)."""

    unit: object
    number: str
    marked: tuple[tuple[str, int, int], ...]


def _number_at(text: str):
    """The one number a reader's text at a unit writes (written.numbers), or None."""
    from . import written

    found = written.numbers(text)
    return found[0] if len(found) == 1 else None


# What may stand right before a number as an opening quotation mark (folded: written.fold reads a
# curly quote or a prime as "'"): a number after one is quoted, never an elevation's.
QUOTES = frozenset("'\"\N{LEFT DOUBLE QUOTATION MARK}\N{RIGHT DOUBLE QUOTATION MARK}`")


def _after_a_heading(text: str, start: int) -> bool:
    """Whether a reading writes an elevation's heading right before the number at `start` on its
    line, glued to it or a space apart ("Elev.6400", "alt. 1200"): the word before it, folded with
    its periods dropped, is one of written.HEADINGS, or it is "el." (written.HEADING_WITH_PERIOD)."""
    from . import written

    before = text[text.rfind("\n", 0, start) + 1:start].split()
    if not before:
        return False
    word = before[-1]
    return written._bare(word) in written.HEADINGS or written.fold(word) == written.HEADING_WITH_PERIOD


def _quoted(text: str, start: int) -> bool:
    """Whether the last character before the number at `start` on its line, white space aside, is a
    quotation mark (QUOTES): "Trap '6400"."""
    from . import written

    before = text[text.rfind("\n", 0, start) + 1:start].rstrip()
    return bool(before) and written.fold(before[-1]) in QUOTES


ELEVATION_FIELDS = frozenset(derive_rules.ELEVATIONS)


def _another_unit_after(text: str, end: int) -> bool:
    """Whether the next word after a number's foot mark, on its line, is a unit of an elevation
    (written.UNIT_OF): "Elev. 6400' m"."""
    from . import written

    after = text[end:text.find("\n", end) if "\n" in text[end:] else None].split()
    return bool(after) and written._bare(after[0]) in written.UNIT_OF


def elevation_texts(readings: Sequence[Reading]) -> set[tuple[str, int]]:
    """Every elevation text the readings write, as (observation, where its number starts): a
    number with an elevation unit that is no distance, or a number an elevation's heading or a
    capital "M" marks (written.numbers' `unit` and `sign`), on any line of any label."""
    from . import written

    found = set()
    for reading in readings:
        offset = 0
        for line in reading.text.split("\n"):
            for number in written.numbers(line):
                if (number.unit is not None and not number.distance) or number.sign is not None:
                    found.add((reading.observation_id, offset + number.start))
            offset += len(line) + 1
    return found


def options_of(held: FieldValue | None) -> list[str]:
    """The options a held value's reason lists ("... Options: a; b."), as step._field_value writes
    an expert's several_possibilities answer; [] when it lists none."""
    reason = held.reason if held is not None else ""
    if " Options: " not in reason:
        return []
    return [option.strip() for option in reason.rsplit(" Options: ", 1)[1].rstrip(".").split("; ") if option.strip()]


def foot_number(run, readings: Sequence[Reading], held: FieldValue | None) -> Written | None:
    """Condition (a) of elevation_unit_feet, on the held field's own unit, and only when certain
    (the coordinator's rulings on Codex's and G51's round 1 of PR #437). The unit's readers all
    write one same number (written.numbers), the held field's literal when it has one, and:
    - (i) the unit is the elevation's: the first pass's unit names an elevation field among its
      fields, or every reader writes the number right after an elevation's heading
      (_after_a_heading). The held field's cited label rows bind nothing (Codex's round 2 on PR
      #437: "No. 3456'" under rows that cover it);
    - (ii) no reading of any label writes another elevation text (elevation_texts);
    - (iii) where the expert gave options (options_of), every number they write is this one;
    - (iv) no reader writes a quotation mark right before the number (_quoted); at least one
      writes the foot mark glued to it, or "ft", right after it, with no other unit after that
      (_another_unit_after), and at least one writes no unit; none writes another unit or a
      distance.
    None unless exactly one unit of the run's labels (Run.reading_units) is so."""
    from . import written

    texts = {reading.observation_id: reading.text for reading in readings}
    literal = held.literal if held is not None else None
    written_ones = elevation_texts(readings)
    found = []
    for label in getattr(run, "reading_units", None) or ():
        for unit in label.units:
            numbers = {key: _number_at(span.text) for key, span in unit.readers.items()}
            if not numbers or any(number is None for number in numbers.values()):
                continue
            digits = {unit.readers[key].text[number.start:number.end] for key, number in numbers.items()}
            if len(digits) != 1 or not BARE_NUMBER.fullmatch(number := next(iter(digits))):
                continue
            if literal is not None and literal.strip() != number:
                continue
            given = options_of(held)
            if given and {found_digits for option in given for found_digits in re.findall(r"\d+", option)} != {number}:
                continue
            routed = bool(ELEVATION_FIELDS & set(unit.fields))
            marked, bare, here = [], 0, set()
            for key, found_number in numbers.items():
                span = unit.readers[key]
                text = texts.get(key, "")
                start, end = span.start + found_number.start, span.start + found_number.end
                here.add((key, start))
                if text[span.start:span.end] != span.text or _quoted(text, start):
                    break
                if not (routed or _after_a_heading(text, start)):
                    break
                if found_number.distance:
                    break
                if found_number.unit is None:
                    bare += 1
                    continue
                tail = span.text[found_number.end:found_number.whole[1]]
                spelling = re.sub(r"[\s.,;:()]", "", written.fold(tail))
                glued = spelling != "'" or written.fold(tail[:1]) == "'"
                if spelling in FOOT_MARKS and glued and not _another_unit_after(
                        text, span.start + found_number.whole[1]):
                    marked.append((key, start, end))
                else:
                    break
            else:
                if marked and bare and not (written_ones - here):
                    found.append(Written(unit, number, tuple(marked)))
    return found[0] if len(found) == 1 else None


def infer_feet(run, *, readings: Sequence[Reading], eligible: Collection[str], asset_id: str | None = None,
        blobs=None) -> list[str]:
    """The ontology's rule elevation_unit_feet, on the units path (step.apply_outcomes, after each
    label's settlement is recorded): Elevation From (ft), held (unresolved or ambiguous), among
    `eligible`, while every other elevation field is open (derive.is_open), is inferred as feet
    when all of these hold:
    - (a) the held field's own unit writes one number, a reader's foot mark or "ft" right after it
      and another reader's no unit, with the conditions (i) to (iv) of foot_number: the unit is the
      elevation's, the readings write no other elevation, the expert's options name no other
      number, and the mark is unquoted and no other unit follows it;
    - the country is cleared, not marked (cleared_country), and has a row of the ontology's
      highest-point table (highest_point);
    - (b) the number read as metres is above that row's highest point;
    - (c) the number read as feet (1 ft = 0.3048 m) is not above it.
    It then settles, cleared (no marked finding), in the layer "settled": the number as its
    literal and parsed value, citing one "derived" row (locator INFERRED) whose excerpt states
    the value, the rule and its inputs, and a label row for each reader that wrote the mark;
    its reason starts "Basis: inferred, rule elevation_unit_feet: " and says why. Returns the fields
    inferred: ["elevation_from_ft"] or []."""
    from specimen_digitization.application.organiser import CandidateLocation, format_locator

    from .step import SOURCE

    key = "elevation_from_ft"
    value = run.fields.get(key)
    if key not in eligible or value is None or value.state not in (ValueState.UNRESOLVED, ValueState.AMBIGUOUS):
        return []
    if any(not derive_rules.is_open(run.fields.get(other)) for other in derive_rules.ELEVATIONS
            if other != key and other in run.fields):
        return []
    country = cleared_country(run)
    row = highest_point(country) if country is not None else None
    written_at = foot_number(run, readings, value) if row is not None else None
    if written_at is None:
        return []
    number = Decimal(written_at.number)
    if not number > row.elevation_m or number * FOOT_IN_METRES > row.elevation_m:
        return []
    by_observation = {reading.observation_id: reading for reading in readings}
    named = [by_observation[obs] for obs, _, _ in written_at.marked if obs in by_observation]
    if not named:
        return []
    detail = (f"reader {', '.join(reading.name for reading in named)} writes {written_at.number} with the foot mark "
        f"or ft at unit {written_at.unit.id}, where another writes it with no unit; {written_at.number} m is above "
        f"the highest point of {row.country_name}, {row.point_name}, {row.elevation_m} m (Wikidata {row.country}, "
        f"{row.point}), and {written_at.number} ft ({number * FOOT_IN_METRES} m) is not")
    record = json.dumps({"field_key": key, "value": written_at.number, "rule": ELEVATION_UNIT_FEET,
        "unit": written_at.unit.id, "readers": [reading.name for reading in named], "country": country.authority_id,
        "highest_point": {"country": row.country, "point": row.point, "elevation_m": str(row.elevation_m)}},
        sort_keys=True).encode()
    inferred = Evidence(kind="derived", asset_id=asset_id, source=SOURCE, locator=INFERRED,
        excerpt=f"{key} = {written_at.number}: inferred as feet (rule {ELEVATION_UNIT_FEET}): {detail}",
        raw_ref=blobs.put(record) if blobs is not None else None,
        digest=hashlib.sha256(record).hexdigest() if blobs is not None else None)
    rows = [inferred]
    for obs, start, end in written_at.marked:
        reading = by_observation.get(obs)
        if reading is None:
            continue
        line_start = reading.text.rfind("\n", 0, start) + 1
        line_end = reading.text.find("\n", end)
        line_end = len(reading.text) if line_end < 0 else line_end
        quote = json.dumps({"field_key": key, "reading": reading.name, "region_id": reading.region_id,
            "observation_ids": [obs], "excerpt": reading.text[line_start:line_end], "basis": "inferred"},
            sort_keys=True).encode()
        rows.append(Evidence(kind="literal", asset_id=asset_id, region_id=reading.region_id, observation_ids=[obs],
            source=SOURCE, locator=format_locator(CandidateLocation(reading.name, obs, line_start, line_end, start,
                end)), excerpt=reading.text[line_start:line_end],
            raw_ref=blobs.put(quote) if blobs is not None else None,
            digest=hashlib.sha256(quote).hexdigest() if blobs is not None else None))
    run.evidence.extend(rows)
    relations = {item.id: "decides" if item is inferred else "supports" for item in rows}
    run.fields[key] = FieldValue(state=ValueState.SUPPORTED, literal=written_at.number, parsed=written_at.number,
        evidence_ids=list(relations), evidence_relations=relations, layer="settled", input_source="raw_reading",
        source_region_id=written_at.unit.label, source_observation_id=named[0].observation_id,
        verbatim_by_observation={reading.observation_id: written_at.number for reading in named},
        input_source_by_observation={reading.observation_id: "raw_reading" for reading in named},
        settled_observation_ids=[reading.observation_id for reading in named],
        reason=f"Basis: inferred, rule {ELEVATION_UNIT_FEET}: {detail}.")
    return [key]


# ---- the collectors' role marker (plan WP 2.3c) ---------------------------------------------

# The field whose literal never holds the marker of its role, and the ontology's notation of that
# marker ("leg.", "coll.", "Coll.": collected by).
ROLE_FIELD = "collectors"
ROLE_NOTATION = "collected_by"


class Role(NamedTuple):
    """A collectors literal read without the marker at its edge: the name (empty when the
    literal is the marker alone), the marker, and the name's offsets in the literal."""

    name: str
    marker: str
    start: int
    end: int


# The words that join two people's names (G51's round 1 on PR #439, the coordinator's ruling): a name
# that starts or ends with one is no whole name.
JOINERS = frozenset({"et", "&", "and", "y", "u", "und"})
# The ontology's notation of the determiner's role, another role word a name never holds.
DETERMINER_NOTATION = "determined_by"


@cache
def role_markers() -> tuple[str, ...]:
    """The spellings the ontology's notation collected_by writes ("leg.", "coll.", "Coll.")."""
    from specimen_digitization.ontology import ontology

    return next(item for item in ontology().notations if item.id == ROLE_NOTATION).written


@cache
def role_words() -> frozenset[str]:
    """Every role word of the ontology's notations collected_by and determined_by ("leg.", "coll.",
    "Coll.", "det.")."""
    from specimen_digitization.ontology import ontology

    return frozenset(form for item in ontology().notations if item.id in (ROLE_NOTATION, DETERMINER_NOTATION)
        for form in item.written)


def plain_name(text: str) -> bool:
    """Whether a text is a name alone: no token of it is a role word (role_words), and neither its
    first nor its last token is a joiner (JOINERS, letter case aside)."""
    tokens = text.split()
    return bool(tokens) and not any(token in role_words() for token in tokens) and not (
        tokens[0].casefold() in JOINERS or tokens[-1].casefold() in JOINERS)


@cache
def _role_patterns() -> tuple[re.Pattern[str], ...]:
    """The marker alone; a name and the marker after it; the marker and a name after it; the
    marker right after a text; the marker right before one (role_markers, longest first)."""
    markers = "|".join(re.escape(marker) for marker in sorted(role_markers(), key=len, reverse=True))
    return (re.compile(rf"\s*(?P<marker>{markers})\s*", re.S),
        re.compile(rf"(?P<name>.*?\S)[,;]?\s+(?P<marker>{markers})\s*", re.S),
        re.compile(rf"\s*(?P<marker>{markers})\s+(?P<name>\S.*)", re.S),
        re.compile(rf"[,;]?[ \t]+(?P<marker>{markers})(?!\S)"),
        re.compile(rf"(?:^|(?<=\s))(?P<marker>{markers})[ \t]+$"))


def without_role(literal: str | None) -> Role | None:
    """The literal of the collectors without a collected_by marker (role_markers) at an edge, or
    None when no marker stands at an edge. The marker is a whole token, spelled as the notation
    writes it: at the end, after white space (a comma or a semicolon may close the name before
    it); at the start, before white space. "H. Hoogstraal leg." and "leg. H. Hoogstraal" give the
    name "H. Hoogstraal"; "Legrand", "H. Hoogstraalleg." and "F.G. Werner" give None; the marker
    alone gives the name "". The name keeps no white space at its edges. Only a name alone is
    read off (plain_name): where what remains holds another role word or starts or ends with a
    joiner ("leg. et det. J. Smith", "J. Dupont et coll.", "J. Dupont & coll."), None, and the
    literal stays as it is."""
    if not literal:
        return None
    alone, at_end, at_start = _role_patterns()[:3]
    if (found := alone.fullmatch(literal)) is not None:
        return Role("", found["marker"], 0, 0)
    start, end, marker = 0, len(literal), None
    if (found := at_end.fullmatch(literal)) is not None:
        end, marker = found.end("name"), found["marker"]
    if (found := at_start.fullmatch(literal, 0, end)) is not None:
        start, marker = found.start("name"), marker or found["marker"]
    if marker is None:
        return None
    if alone.fullmatch(literal, start, end) is not None:
        return Role("", marker, 0, 0)
    while start < end and literal[start].isspace():
        start += 1
    while end > start and literal[end - 1].isspace():
        end -= 1
    if not plain_name(literal[start:end]):
        return None
    return Role(literal[start:end], marker, start, end)


def role_beside(text: str, start: int, end: int) -> str | None:
    """The collected_by marker a reading writes right beside its text at [start, end), on the
    same line: after it, past white space (a comma or a semicolon may come first), and before
    white space or the text's end; or before it, after the line's start or white space, past
    white space. None otherwise."""
    after, before = _role_patterns()[3:]
    line_start = text.rfind("\n", 0, start) + 1
    if (found := after.match(text, end)) is not None or (found := before.search(text[line_start:start])) is not None:
        return found["marker"]
    return None


# ---- the extent of Precise Location (plan WP 2.3b) -----------------------------------------

# The places above the precise location whose text, on the next line, shows it cut short.
HIGHER_PLACES = ("province_state", "country")


def _whole_words(text: str, line: str) -> bool:
    return bool(text) and re.search(rf"(?<!\w){re.escape(text)}(?!\w)", line) is not None


def _texts_of(value: FieldValue, reading: Reading) -> list[str]:
    """A settled value's texts in a reading: that reader's verbatim of it, and its literal."""
    return [text for text in dict.fromkeys((value.verbatim_by_observation.get(reading.observation_id), value.literal))
        if text and text.strip()]


def _without(line: str, texts: Iterable[str]) -> str:
    """The line with every whole-word occurrence of each text blanked, the longest text first."""
    for text in sorted(set(texts), key=len, reverse=True):
        line = re.sub(rf"(?<!\w){re.escape(text)}(?!\w)", " ", line)
    return line


def _continues(line: str, reading: Reading, fields: Mapping[str, FieldValue],
        places: Sequence[tuple[str, FieldValue]]) -> tuple[str, str] | None:
    """The settled higher place a reading's next line continues the precise location with, as (its
    field, its text), or None. With the texts of the other settled fields blanked (_texts_of: any
    settled field's but the precise location's and the higher places' own, such as an
    elevation's or a collector's), the line still writes, as whole words, the text of a settled
    province or country (_whole_words; _extent_marks has made sure the literal writes none): a
    place counts only outside another field's literal (G51's round 2 on PR #437: "University of
    the Philippines" as the collectors). And the line is nothing but the locality going on: with
    the higher places' texts blanked too, what is left is punctuation, white space and the place
    unit words of the ontology's table (`tables.place_unit_words`: "Prov.", "Dept.")."""
    from specimen_digitization.ontology import ontology

    from . import written

    higher = {key for key, _ in places}
    others = [text for key, value in fields.items() if key != "precise_location" and key not in higher
        and settled(value) for text in _texts_of(value, reading)]
    outside = _without(line, others)
    hit = next(((key, text) for key, place in places for text in _texts_of(place, reading)
        if _whole_words(text, outside)), None)
    if hit is None:
        return None
    own = [text for _, place in places for text in _texts_of(place, reading)]
    units = set(ontology().tables.place_unit_words)
    left = [word for word in re.findall(r"\w+", _without(outside, own)) if written._bare(word) not in units]
    return hit if not left else None


def _extent_marks(fields: Mapping[str, FieldValue], readings: Sequence[Reading], rows: Mapping[str, Evidence],
        human: Collection[str]) -> list[Mark]:
    """precise_location_extent: a settled precise location cut short, marked only when certain.
    The literal writes no settled province's or country's text (HIGHER_PLACES), and every reading
    of its labels (step._value_regions) writes it exactly; at every place each writes it, the
    literal ends its line (only white space follows on that line) and the reading's next line
    continues the locality with a settled province or country, with nothing but other settled
    fields' texts, place unit words and punctuation besides (_continues): "E. slope Mt.
    McKinley" before "Davao Prov.", the province settled. Otherwise the check abstains: "Los
    Banos, Philippines" before "University of the Philippines" and "Yepocapa, Chimaltenango,
    Guatemala" before "Guatemala Exped. 1948" (the literal writes the country already), a next
    line with a name no field settled ("Mindanao, P.I."), a reading that writes the literal
    otherwise ("Mt" with no period), a person's precise location, no such place settled."""
    from .step import _value_regions

    value = fields.get("precise_location")
    if not settled(value) or "precise_location" in human or not value.literal:
        return []
    places = [(key, fields[key]) for key in HIGHER_PLACES if settled(fields.get(key)) and fields[key].literal]
    if not places:
        return []
    from .checks import collapse

    # The literal already writes a settled higher place: its locality reached that place.
    if any(_whole_words(text, value.literal) for _, place in places
            for text in {place.literal, *place.verbatim_by_observation.values()} if text and text.strip()):
        return []
    labels = _value_regions(value, readings, rows)
    shown = None
    for reading in readings:
        if reading.region_id not in labels:
            continue
        at = reading.text.find(value.literal)
        # Every reading of the label is consulted: one that does not write the literal (after the
        # collapse the settlement compares by), or not exactly, gives no certainty.
        if at < 0 or collapse(value.literal) not in collapse(reading.text):
            return []
        while at >= 0:
            end = at + len(value.literal)
            line_end = reading.text.find("\n", end)
            if line_end < 0 or reading.text[end:line_end].strip():
                return []
            after = reading.text.find("\n", line_end + 1)
            line = reading.text[line_end + 1:None if after < 0 else after]
            hit = _continues(line, reading, fields, places)
            if hit is None:
                return []
            if shown is None:
                # What the re-ask tells the expert (Mark.saw): the next line and each line after it
                # that continues the locality with a settled province or country too (_continues).
                following = [(line.strip(), *hit)]
                while after >= 0:
                    start, after = after + 1, reading.text.find("\n", after + 1)
                    more = reading.text[start:None if after < 0 else after]
                    if (also := _continues(more, reading, fields, places)) is None:
                        break
                    following.append((more.strip(), *also))
                shown = following
            at = reading.text.find(value.literal, at + 1)
    if shown is None:
        return []
    line, key, text = shown[0]
    cited = tuple(dict.fromkeys([*value.evidence_ids, *fields[key].evidence_ids]))
    lines = " and ".join(repr(item[0]) for item in shown)
    held = " and ".join(dict.fromkeys(f"{LEVEL_NAMES[item[1]]} {item[2]!r}" for item in shown))
    saw = (f"it ends its line, and the label's next {'lines' if len(shown) > 1 else 'line'}, {lines}, "
        f"{'write' if len(shown) > 1 else 'writes'} the settled {held}; Precise Location takes every line "
        "of the locality, the higher places included")
    return [Mark("precise_location", PRECISE_LOCATION_EXTENT,
        f"Marked for a person, rule {PRECISE_LOCATION_EXTENT}: the label's next line, {line!r}, writes the "
        f"{LEVEL_NAMES[key]} settled, {text!r}, so its locality goes on after this text.", cited, saw)]


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
        tally: Counter | None = None, decisions: dict[str, dict] | None = None) -> list[str]:
    """Run the checks over the run's settled values, in memory; the codes of the marks made.

    `received` is every source answer of this attempt, by field. A settled place cites, as its
    evidence, the gazetteer answers it settled on; those this attempt did not receive (an
    earlier attempt's) are read again from `blobs`, the record's blob store (`stored_answers`);
    a place whose record cannot be read again is not checked (the check abstains). `tally`
    counts what the place checks checked and abstained on, and the records not read again.
    The fields this attempt `researched` or `derived`, and both dates, are checked again: their
    earlier marks of this stage are dropped first; a field another attempt settled keeps its
    marks, and gets no mark twice. A person's field (`human`) is never marked, whatever its
    layer. Each value this attempt derived gets its basis sentence (`basis`), before any mark's.
    `decisions` (step.apply_outcomes') gets, for each field marked, the check (STAGE_CHECK) and
    what it saw (STAGE_SAW), which the units path's one re-ask tells the field's expert
    (field_research/reask.py)."""
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
    for mark in [*_place_marks(run.fields, answers, human, tally), *_date_marks(run.fields, human),
            *_extent_marks(run.fields, readings, rows, human)]:
        _with_sentence(run.fields[mark.field], mark.sentence)
        if decisions is not None:
            decisions.setdefault(mark.field, {}).setdefault(STAGE_CHECK, mark.check)
            decisions[mark.field].setdefault(STAGE_SAW, mark.saw)
        for label in _labels(run, mark.field, readings, rows):
            code = marked_code(mark.field, label, mark.check)
            if (mark.field, code) in present:
                continue
            present.add((mark.field, code))
            run.findings.append(RunFinding(rule_id=CHECK_STAGE, rule_version=CHECK_STAGE_RULES, severity="warning",
                field_key=mark.field, reason_code=code, evidence_ids=list(mark.evidence_ids)))
            made.append(code)
    return made
