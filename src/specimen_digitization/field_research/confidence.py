"""Confident or flagged: a settled value is shown as settled only when nothing in the run argues
against it (lane Q1 of the autonomy program, docs/execution/autonomy/PLAN.md).

The owner's goal of 2026-11-18, typed in the coordinator's session: "take the specimen
digitization to full autonomy but ensuring that records are ever cleared wrong and aren't
unnecessarily waiting for a human review." A value these rules flag keeps its text, layers and
state; it gets a warning finding of rule RULE, `marked:<field>:<label>:<why>` (step.marked_code),
which step.marked_reasons makes one of the run's reasons, and a sentence at the end of its reason.
Under a profile whose field is optional the mark is that field's doubt and does not hold the
record; on a mandatory field it holds the record as every mark does. Nothing here settles,
clears or rewrites a value.

A field a person has authority over is never flagged and its reason is never touched
(person_fields): a decision a move to the units path carried (step.human_keys), a research
selection a person locked (the run's `human_review_field_locks`), and a value whose label a
person transcribed (Reading.person_decided). A person's own decision on a field, a selection of a
research candidate, an authority or a taxon, removes this pass's mark from that field (release,
called by the decision endpoint), and step.refinalize, which runs after every such decision,
releases every field a person has authority over and adds no mark.

The rules decide on the label's reading units, the units each value is drawn from: never on an
occurrence of the value's text elsewhere on the label. Where a reading has no units the rules
that need them abstain, except rule 1, which then compares the readers' whole texts. Each rule
has its own `why` (WHYS):
1. READERS_DIFFER: at a place a reader writes the value, the label's other readers do not write
   it over the same units (letter case, accents, spacing and punctuation aside, but never a
   difference in a number's digits, its decimal separator or its sign: "1.5 km" is not "15 km",
   "-80 m" is not "80 m"); no label of the value has every reader writing it there; no source
   decides it (an evidence row cited as `decides`: GBIF, the slide's QR code) nor, for a place
   value field, a source record names it (authority_id). The first pass's image judgement alone
   then chose the reading: it named the wrong text about as often as the right one where readers
   differed (lane H0).
2. FOLLOWS_MARKED: a derived value (layer "derived") one of whose sources is marked, by any rule.
3. EXTENT (precise location, habitat, collectors): cut short, the units the value is drawn from,
   with the units next to them the first pass advises for the same field, form a longer run of
   text every reader of the label writes alike (a heading, a role word or a sex sign aside:
   "ex Peromyscus" in the unit "ex Peromyscus\\nleucopus"; "27 km. north of Kunduz" after "Loc:
   AFGHANISTAN," advised for the locality); too long, the value takes in a whole unit the first
   pass advises only for other fields ("ex Peromyscus leucopus\\nShidler" with "Shidler" advised
   as the city); or the value starts with one of the label headings HEADINGS ("Loc:", "Host:"),
   or a collector's value holds a role word of the ontology's notations ("COLL").
4. Conventions settled from the requirements (lane M0):
   - DISTANCE_ORIGIN (city, and the county and province or state too): at every place the value
     is drawn from, the unit that holds it, before it, or the unit right before that one, ends
     with a distance and a direction ("12 mi. N, 5 mi. E" before "Shidler,"; "27 km. north of
     Kunduz"): the town is where the distance is measured from, not the collecting place
     (GEOREFERENCING.md: dwc:municipality is never "a nearby named place").
   - NOT_COLLECTION_CODE: a Collection Code that is not the printed heading the owner ruled (the
     ontology's notation lewis_collection_heading); slide, preparation and field numbers are no
     Collection Code.
   - NOT_VERBATIM_DATE: a Verbatim D/T/S that is an exact day (with or without a clock time),
     holds a slide code as one of its words, or is drawn from the very units the identification
     date is drawn from. Verbatim D/T/S holds only date wording that is not an exact date
     (PRD.md:529, :540-544). Only the value's own text and units are read: a code elsewhere on
     the label flags nothing.

step.apply_outcomes and step.refinalize call the pass through `guarded`: any exception inside it
leaves no mark from it, logs one warning, and puts the run's fields and findings back exactly.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Collection, Mapping, Sequence
from functools import cache

from specimen_digitization.application.domain import Evidence, FieldValue, RunFinding, ValueState

from .contracts import Reading

LOGGER = logging.getLogger(__name__)
RULE = "confidence"
RULE_VERSION = "field-research-confidence-v2"
READERS_DIFFER = "readers_differ"
FOLLOWS_MARKED = "follows_marked"
EXTENT = "extent"
DISTANCE_ORIGIN = "distance_origin"
NOT_COLLECTION_CODE = "not_collection_code"
NOT_VERBATIM_DATE = "not_verbatim_date"
WHYS = (READERS_DIFFER, FOLLOWS_MARKED, EXTENT, DISTANCE_ORIGIN, NOT_COLLECTION_CODE, NOT_VERBATIM_DATE)
# The start of every sentence this pass adds to a value's reason.
SENTENCE = "Marked for a person, rule "
LOCKS = "human_review_field_locks"

SETTLED_LAYERS = frozenset({"settled", "verbatim"})
EXTENT_FIELDS = frozenset({"precise_location", "habitat", "collectors"})
ORIGIN_FIELDS = frozenset({"city", "county", "province_state"})
# The fields whose advice a unit inside a value may carry without the value running past its own
# field: the locality's lines hold its higher places and an elevation (precise_location_extent).
OWN_ADVICE = {
    "precise_location": frozenset({"precise_location", "country", "province_state", "county", "city",
        "elevation_from_m", "elevation_to_m", "elevation_from_ft", "elevation_to_ft"}),
    "habitat": frozenset({"habitat"}),
    "collectors": frozenset({"collectors", "identified_by_irn"}),
}
COLLECTION_CODE = "collection_code"
VERBATIM = "verbatim_dts"
IDENTIFIED = "date_identified"
# Words a label writes before a value to name what follows, never part of it ("Loc:", "HOST:").
HEADINGS = frozenset({"loc", "locality", "host", "hosts", "hab", "habitat"})
# Role words and their abbreviations a label writes beside a collector's name ("col R.E. MARTIN",
# "Collr SA"): never more of the name. The ontology's notations add theirs (_role_stems).
ROLE_ABBREVIATIONS = frozenset({"col", "coll", "collr", "colr", "leg", "det", "legit", "collector", "collectors"})

_FRACTIONS = "[\N{VULGAR FRACTION ONE HALF}\N{VULGAR FRACTION ONE QUARTER}\N{VULGAR FRACTION THREE QUARTERS}]"
_NUMBER = rf"(?:\d+(?:[.,]\d+)?\s*{_FRACTIONS}?|{_FRACTIONS})"
_UNIT = r"(?:mi|mis|miles?|km|kms|kilomet(?:er|re)s?)\.?"
_DIRECTION = (r"(?:(?:north|south)(?:[- ]?(?:east|west))?|east|west"
    r"|[NSEW](?:\s*\.?\s*[NSEW]){0,2}\.?)")
# A distance and a direction ending the text before a place, an "of" or "from" between.
DISTANCE = re.compile(rf"{_NUMBER}\s*{_UNIT}\s*{_DIRECTION}(?:\s+(?:of|from))?[\s,]*$", re.I)
# A clock time: hours and minutes, with or without a.m./p.m.; or hours with a.m./p.m.
CLOCK = re.compile(r"\b\d{1,2}\s*[:h]\s*\d{2}\s*(?:[ap]\.?\s?m\.?)?|\b\d{1,2}\s*[ap]\.?\s?m\.?(?!\w)", re.I)
# A token: a number with its decimal or thousands separators ("1.5", "1,200") and, where nothing but
# white space or punctuation stands before it, its sign ("-80"); or a run of letters.
_SIGN = "-+\N{MINUS SIGN}"
_TOKEN = re.compile(rf"(?:(?:(?<=[\s(\[:;=])|^)[{_SIGN}])?\d+(?:[.,]\d+)*|[^\W\d_]+", re.M)


def tokens(text: str) -> list[str]:
    """The text's numbers (digits, separators between digits, and a sign before a number that does not
    follow a letter or a digit) and runs of letters, letter case and accents aside."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).casefold()
    found = []
    for match in _TOKEN.finditer(plain):
        token = match.group()
        if token[0] in _SIGN:
            before = plain[:match.start()].rstrip()
            if before and before[-1].isalnum():
                # A dash after a word or a number joins them ("III -1974"): no sign.
                token = token[1:]
        found.append(token.replace("\N{MINUS SIGN}", "-"))
    return found


def writes(reading_text: str, literal: str) -> bool:
    """Whether a text writes the literal: some run of its whole tokens (tokens), joined, is the literal's
    tokens joined. Spacing, punctuation, letter case and accents aside ("12mi. N" writes "12 mi. N");
    a number's digits, separators and sign are never aside ("15 km" does not write "1.5 km")."""
    want = "".join(tokens(literal))
    have = tokens(reading_text)
    if not want:
        return False
    for i in range(len(have)):
        joined = ""
        for j in range(i, len(have)):
            joined += have[j]
            if joined == want:
                return True
            if not want.startswith(joined):
                break
    return False


def _settled(value: FieldValue | None) -> bool:
    return (value is not None and value.state == ValueState.SUPPORTED and value.layer in SETTLED_LAYERS
        and bool(value.literal and value.literal.strip()))


def _label_groups(value: FieldValue, readings: Sequence[Reading], rows: Mapping[str, Evidence]):
    from .step import _value_regions

    regions = _value_regions(value, readings, rows)
    groups: dict[str, list[Reading]] = {}
    for reading in readings:
        if reading.region_id in regions and reading.text and reading.text.strip():
            groups.setdefault(reading.region_id, []).append(reading)
    return groups


def _has_units(reading: Reading) -> bool:
    return reading.units is not None and reading.observation_id in reading.units.units[0].readers


def _places(reading: Reading, literal: str) -> list[tuple[tuple[int, int], list]]:
    """Each place the reading writes the literal with the label's units over it; empty when the
    reading has no units or does not write it."""
    from .agreement import _covered

    if not _has_units(reading):
        return []
    return [(place, cover) for place, cover in _covered(reading, literal) if cover]


def _span(reading: Reading, units: Sequence) -> str:
    """A reading's text over consecutive units, from the first's start to the last's end."""
    key = reading.observation_id
    return reading.text[units[0].readers[key].start:units[-1].readers[key].end]


def _alike(group: Sequence[Reading], units: Sequence) -> bool:
    """Whether every reader of the label writes the same text over the units (tokens)."""
    return len({tuple(tokens(_span(reading, units))) for reading in group}) == 1


# ---- persons ------------------------------------------------------------------------------------

def person_fields(run, readings: Sequence[Reading], human: Collection[str] = ()) -> set[str]:
    """The fields a person has authority over: `human` (step.human_keys: a decision a move to the
    units path carried), a research selection a person locked, and a value whose label a person
    transcribed."""
    rows = {item.id: item for item in run.evidence}
    found = set(human) | set((getattr(run, "dependencies", None) or {}).get(LOCKS) or {})
    for key, value in run.fields.items():
        if any(reading.person_decided for group in _label_groups(value, readings, rows).values()
                for reading in group):
            found.add(key)
    return found


def _without_sentences(reason: str) -> str:
    """A reason without the sentences this pass added to it."""
    whys = "|".join(WHYS)
    return re.sub(rf"\s*{re.escape(SENTENCE)}(?:{whys}):[^\n]*?(?=\s*{re.escape(SENTENCE)}|$)", "", reason or "").strip()


def release(run, keys: Collection[str]) -> None:
    """Remove this pass's marks from the fields `keys` and its sentences from their reasons: a person
    decided or selected them."""
    keys = set(keys)
    run.findings[:] = [finding for finding in run.findings
        if not (finding.rule_id == RULE and finding.field_key in keys)]
    for key in keys:
        value = run.fields.get(key)
        if value is not None and SENTENCE in (value.reason or ""):
            value.reason = _without_sentences(value.reason)


# ---- rule 1 -------------------------------------------------------------------------------------

def _source_decides(key: str, value: FieldValue) -> bool:
    from .agreement import PLACE_VALUE_FIELDS

    return "decides" in value.evidence_relations.values() or (key in PLACE_VALUE_FIELDS
        and bool(value.authority_id))


def _label_differs(group: Sequence[Reading], literal: str) -> tuple[list[str], list[str]] | None:
    """For one label: None when every reader writes the literal at every place it is drawn from
    (its units); else (the readers that write it, the readers that do not at some such place). A
    label read without units is compared on its readers' whole texts."""
    taken = [reading for reading in group if writes(reading.text, literal)]
    if not taken:
        return None
    if not all(_has_units(reading) for reading in group):
        others = [reading.name for reading in group if reading not in taken]
        return ([r.name for r in taken], others) if others else None
    others: list[str] = []
    for reading in taken:
        for _, cover in _places(reading, literal):
            mine = tokens(_span(reading, cover))
            for other in group:
                theirs = _span(other, cover)
                # The other reader writes the value there, or writes those units exactly as this one does.
                if (other is not reading and other.name not in others and not writes(theirs, literal)
                        and tokens(theirs) != mine):
                    others.append(other.name)
    others += [reading.name for reading in group if reading not in taken and reading.name not in others]
    return ([r.name for r in taken if r.name not in others], others) if others else None


def readers_differ(key: str, value: FieldValue, groups: Mapping[str, Sequence[Reading]]) -> str | None:
    """Rule 1's sentence, or None."""
    if _source_decides(key, value):
        return None
    found = {region: _label_differs(group, value.literal) for region, group in groups.items() if len(group) >= 2}
    if not found or any(result is None and any(writes(r.text, value.literal) for r in groups[region])
            for region, result in found.items()):
        return None
    for result in found.values():
        if result is not None:
            taken, others = result
            return (f"{SENTENCE}{READERS_DIFFER}: the readers of this label differ here; reading "
                f"{', '.join(taken) or 'none'}'s text {value.literal!r} was taken on the image judgement alone, and "
                f"reading {', '.join(others)} does not write it there.")
    return None


# ---- rule 3 -------------------------------------------------------------------------------------

@cache
def _role_stems() -> frozenset[str]:
    from .ontology_checks import role_words

    return frozenset(stem for word in role_words() for stem in tokens(word))


def _words_beyond(text: str) -> bool:
    """Whether text outside the value holds more than headings, role words, sex signs and punctuation."""
    text = re.sub(r"[^\W\d_]+\s*:", " ", text)
    return any(token not in _role_stems() | ROLE_ABBREVIATIONS for token in tokens(text) if token not in HEADINGS)


def _between(text: str, start: int, end: int) -> bool:
    return start <= end and not text[start:end].strip()


def _cut_short(key: str, group: Sequence[Reading], reading: Reading, place: tuple[int, int], cover: list) -> str | None:
    """The longer run every reader writes alike, of the units the value is drawn from and the units
    next to them the first pass advises for the same field, when it holds more words than the value."""
    units = reading.units.units
    own = reading.observation_id
    i, j = units.index(cover[0]), units.index(cover[-1])
    while i > 0 and key in units[i - 1].fields and _between(reading.text, units[i - 1].readers[own].end,
            units[i].readers[own].start):
        i -= 1
    while j + 1 < len(units) and key in units[j + 1].fields and _between(reading.text, units[j].readers[own].end,
            units[j + 1].readers[own].start):
        j += 1
    run = units[i:j + 1]
    if not _alike(group, run):
        return None
    start, end = place
    first, last = run[0].readers[own].start, run[-1].readers[own].end
    # Inside the units the value is drawn from, only a line the value does not reach counts: a unit
    # that goes on, on the next line ("ex Peromyscus\nleucopus"), not one that also holds the next
    # field's text on the same line ("Shrubs;1946").
    own_start, own_end = cover[0].readers[own].start, cover[-1].readers[own].end
    before, after = reading.text[own_start:start], reading.text[end:own_end]
    inside = ((not before.split("\n")[-1].strip() and _words_beyond(before))
        or (not after.split("\n")[0].strip() and _words_beyond(after)))
    added = _words_beyond(reading.text[first:own_start]) or _words_beyond(reading.text[own_end:last])
    if inside or added:
        return reading.text[first:last]
    return None


def _too_long(key: str, reading: Reading, place: tuple[int, int], cover: list) -> str | None:
    """A whole unit inside the value that the first pass advises only for other fields."""
    own = reading.observation_id
    start, end = place
    for unit in cover:
        span = unit.readers[own]
        if (start <= span.start and span.end <= end and span.text.strip() and unit.fields
                and not set(unit.fields) & OWN_ADVICE[key]):
            return span.text
    return None


def extent(key: str, value: FieldValue, groups: Mapping[str, Sequence[Reading]]) -> str | None:
    """Rule 3's sentence, or None."""
    if key not in EXTENT_FIELDS:
        return None
    words = value.literal.split()
    head = tokens(words[0]) if words else []
    if (key in ("precise_location", "habitat") and len(words) > 1 and re.fullmatch(r"[^\W\d_]+[:.]", words[0])
            and head and head[0] in HEADINGS):
        return f"{SENTENCE}{EXTENT}: the value starts with the label's heading {words[0]!r}, which is not part of it."
    if key == "collectors" and any(token in _role_stems() for token in tokens(value.literal)):
        return f"{SENTENCE}{EXTENT}: the value holds a role word, which is not part of a collector's name."
    for group in groups.values():
        for reading in group:
            for place, cover in _places(reading, value.literal):
                if (other := _too_long(key, reading, place, cover)) is not None:
                    return (f"{SENTENCE}{EXTENT}: the value takes in {other!r}, which the label's units give to "
                        "another field.")
                if (fuller := _cut_short(key, group, reading, place, cover)) is not None:
                    return (f"{SENTENCE}{EXTENT}: every reader of the label writes more of it here, {fuller!r}; "
                        "the value may be cut short.")
    return None


# ---- rule 4 -------------------------------------------------------------------------------------

def distance_origin(key: str, value: FieldValue, groups: Mapping[str, Sequence[Reading]]) -> str | None:
    """Every place the value is drawn from follows a distance and a direction in its own unit or in
    the unit right before it."""
    if key not in ORIGIN_FIELDS:
        return None
    seen = False
    for group in groups.values():
        for reading in group:
            if not _has_units(reading):
                continue
            units = reading.units.units
            own = reading.observation_id
            for (start, _), cover in _places(reading, value.literal):
                at = units.index(cover[0])
                begin = cover[0].readers[own].start
                if at > 0 and _between(reading.text, units[at - 1].readers[own].end, begin):
                    begin = units[at - 1].readers[own].start
                if not DISTANCE.search(reading.text[begin:start]):
                    return None
                seen = True
    if not seen:
        return None
    return (f"{SENTENCE}{DISTANCE_ORIGIN}: the label names {value.literal.strip(' ,')!r} only as the place a "
        "distance is measured from, not as the collecting place.")


@cache
def _headings() -> frozenset[str]:
    from specimen_digitization.ontology import ontology

    return frozenset("".join(tokens(form)) for item in ontology().notations
        if item.id == "lewis_collection_heading" for form in item.written)


def not_collection_code(key: str, value: FieldValue) -> str | None:
    if key != COLLECTION_CODE or "".join(tokens(value.literal)) in _headings():
        return None
    return (f"{SENTENCE}{NOT_COLLECTION_CODE}: {value.literal!r} is not the collection heading the owner ruled a "
        "Collection Code; a slide, preparation or field number is not one.")


def _day(literal: str, date_rules) -> bool:
    from .checks import parse_date

    found = parse_date(literal, reading_texts=[literal], date_rules=date_rules)
    return any(r.precision == "day" and r.iso and len(r.iso) == 10 for r in found.readings)


def _slide_code(word: str, date_rules) -> bool:
    from .checks import SLIDE_CODE, digit_one_month, parse_date

    for form in dict.fromkeys((word, digit_one_month(word) or word)):
        if SLIDE_CODE in parse_date(form, reading_texts=[form], date_rules=date_rules).notes:
            return True
    return False


def _units_of(group: Sequence[Reading], literal: str) -> set[tuple[str, str]]:
    return {(reading.name, unit.id) for reading in group for _, cover in _places(reading, literal) for unit in cover}


def not_verbatim_date(key: str, value: FieldValue, fields: Mapping[str, FieldValue], date_rules,
        groups: Mapping[str, Sequence[Reading]] = {}, identified: Mapping[str, Sequence[Reading]] = {}) -> str | None:
    if key != VERBATIM:
        return None
    literal = value.literal.strip()
    without_time = CLOCK.sub(" ", literal).strip(" ,;")
    why = None
    if without_time and _day(without_time, date_rules):
        why = "is an exact date"
    elif any(_slide_code(word.strip(".,;()"), date_rules) for word in literal.split()):
        why = "holds a slide code"
    elif _settled(held := fields.get(IDENTIFIED)):
        # The identification date drawn from the very units this value is drawn from.
        shared = [region for region in groups if region in identified]
        if any(_units_of(groups[region], literal) and _units_of(groups[region], literal)
                == _units_of(identified[region], held.literal) for region in shared):
            why = "is drawn from the units the identification date is drawn from"
    if why is None:
        return None
    return (f"{SENTENCE}{NOT_VERBATIM_DATE}: {literal!r} {why}; Verbatim D/T/S holds only date wording that is "
        "not an exact date.")


# ---- the pass -----------------------------------------------------------------------------------

def _marked_fields(run) -> set[str]:
    from .step import marked_reasons

    return {code.split(":")[1] for code in marked_reasons(run) if code.count(":") >= 2}


def review(run, *, readings: Sequence[Reading], human: Collection[str] = (), date_rules=None) -> list[str]:
    """Flag the run's settled values by the rules above, replacing this rule's earlier findings;
    the codes of the marks made. A field a person has authority over (person_fields) is released
    instead. Called by step.apply_outcomes after the check stage, through `guarded`."""
    from .ontology_checks import _labels, _with_sentence
    from .step import marked_code

    rows = {item.id: item for item in run.evidence}
    persons = person_fields(run, readings, human)
    release(run, run.fields)
    # A field another rule marked already (the settlement's text_only or conflict, the check stage,
    # the QR code) is a person's already: it gets no second mark.
    already = _marked_fields(run)
    sentences: dict[str, tuple[str, str]] = {}
    identified = _label_groups(run.fields[IDENTIFIED], readings, rows) if _settled(run.fields.get(IDENTIFIED)) else {}
    for key, value in run.fields.items():
        if key in persons or key in already or not _settled(value):
            continue
        groups = _label_groups(value, readings, rows)
        for why, rule in (
                (NOT_COLLECTION_CODE, lambda: not_collection_code(key, value)),
                (NOT_VERBATIM_DATE, lambda: not_verbatim_date(key, value, run.fields, date_rules, groups, identified)),
                (DISTANCE_ORIGIN, lambda: distance_origin(key, value, groups)),
                (EXTENT, lambda: extent(key, value, groups)),
                (READERS_DIFFER, lambda: readers_differ(key, value, groups))):
            if sentence := rule():
                sentences[key] = (why, sentence)
                break
    marked = already | set(sentences)
    changed = True
    while changed:
        changed = False
        for key, value in run.fields.items():
            if (key in persons or key in marked or value.state != ValueState.SUPPORTED
                    or value.layer != "derived"):
                continue
            sources = [name for name in value.derived_from if name in marked]
            if sources:
                sentences[key] = (FOLLOWS_MARKED, f"{SENTENCE}{FOLLOWS_MARKED}: it is derived from "
                    f"{', '.join(sources)}, which is marked.")
                marked.add(key)
                changed = True
    made = []
    for key, (why, sentence) in sentences.items():
        _with_sentence(run.fields[key], sentence)
        for label in _labels(run, key, readings, rows):
            code = marked_code(key, label, why)
            run.findings.append(RunFinding(rule_id=RULE, rule_version=RULE_VERSION, severity="warning",
                field_key=key, reason_code=code, evidence_ids=list(run.fields[key].evidence_ids)))
            made.append(code)
    return made


def guarded(run, action, *args, **kwargs) -> None:
    """Run `action` (review, release) on the run; on any exception inside it, log one warning and
    put the run's fields and findings back exactly as they were, so the pass leaves no mark."""
    kept_fields = {key: value.model_copy(deep=True) for key, value in run.fields.items()}
    kept_findings = list(run.findings)
    try:
        action(run, *args, **kwargs)
    except Exception:  # noqa: BLE001 - the confidence pass never fails research or a decision
        LOGGER.warning("confidence pass skipped: no value marked", exc_info=True)
        run.fields.clear()
        run.fields.update(kept_fields)
        run.findings[:] = kept_findings


def settle_persons(run, *, human: Collection[str] = ()) -> None:
    """step.refinalize's part: release every field a person has authority over; mark nothing."""
    from .step import run_readings

    release(run, person_fields(run, run_readings(run), human))
