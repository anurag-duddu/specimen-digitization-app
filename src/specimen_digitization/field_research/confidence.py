"""Confident or flagged: a settled value is shown as settled only when nothing in the run argues
against it (lane Q1 of the autonomy program, docs/execution/autonomy/PLAN.md).

The owner's goal of 2026-11-18, typed in the coordinator's session: "take the specimen
digitization to full autonomy but ensuring that records are ever cleared wrong and aren't
unnecessarily waiting for a human review." A value these rules flag keeps its text, layers and
state; it gets a warning finding of rule RULE, `marked:<field>:<label>:<why>` (step.marked_code),
which step.marked_reasons makes one of the run's reasons, and a sentence at the end of its reason.
Under a profile whose field is optional the mark is that field's doubt and does not hold the
record; on a mandatory field it holds the record as every mark does. Nothing here settles,
clears or rewrites a value, and a field a person decided (step.human_keys) is never flagged.

The rules, each its own `why` (WHYS):
1. READERS_DIFFER: the readers of the value's label do not all write its text (letters and
   digits compared, letter case, accents, spacing and punctuation aside), no label of the value
   has two or more readers that all write it, and no source decides it (an evidence row cited
   as `decides`: GBIF, the slide's QR code) nor, for a place value field, a source record names
   it (authority_id). The first pass's image judgement alone then chose the reading: it named
   the wrong text about as often as the right one where readers differed (lane H0).
2. FOLLOWS_MARKED: a derived value (layer "derived") one of whose sources is marked, by any rule,
   is marked with it.
3. EXTENT (precise location, habitat, collectors): at every place every reading of the label
   writes the value, it ends its line inside a unit of the label's reading units that goes on, on
   the next line, with more text (a heading, a role word or a sex sign aside: "ex Peromyscus" in
   "ex Peromyscus\nleucopus"); or the unit right after it, with only white space between, goes on
   with it (precise location: a unit the first pass advises for the locality or a higher place;
   habitat: one word of letters alone in lower case or capitals, as a species name after its
   genus); or, for a precise location, the unit right before it is such a unit ("Loc:
   AFGHANISTAN," before "27 km. north of Kunduz": the ontology's rule precise_location_extent
   puts the higher places written on the locality's lines in it). Or the value itself starts with
   a heading ("Loc:", "Host:") or, for collectors, holds a role word ("COLL"). An addition for the
   taxon: a genus alone on a label whose units hold a species or an author part it leaves out.
   The fuller text is named in the sentence; the value is not changed. Where a reading has no
   units, or does not write the value, the rule abstains.
4. Conventions settled from the requirements (lane M0):
   - DISTANCE_ORIGIN (city, and the county and province or state too): every place a reading
     writes the value follows a distance and a direction ("12 mi. N, 5 mi. E Shidler", "27 km.
     north of Kunduz"): the town is where the distance is measured from, not the collecting
     place (GEOREFERENCING.md: dwc:municipality is never "a nearby named place").
   - NOT_COLLECTION_CODE: a Collection Code that is not the printed heading the owner ruled
     (the ontology's notation lewis_collection_heading); slide, preparation and field numbers
     are no Collection Code.
   - NOT_VERBATIM_DATE: a Verbatim D/T/S that is an exact day (with or without a clock time),
     holds a slide code as one of its words, or is the very text a day-precision collecting date
     or the identification date settled from. Verbatim D/T/S holds only date wording that is
     not an exact date (PRD.md:529, :540-544). Only the value's own text is read: a code
     elsewhere on the label flags nothing.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection, Mapping, Sequence
from functools import cache

from specimen_digitization.application.domain import Evidence, FieldValue, RunFinding, ValueState

from .contracts import Reading

RULE = "confidence"
RULE_VERSION = "field-research-confidence-v1"
READERS_DIFFER = "readers_differ"
FOLLOWS_MARKED = "follows_marked"
EXTENT = "extent"
DISTANCE_ORIGIN = "distance_origin"
NOT_COLLECTION_CODE = "not_collection_code"
NOT_VERBATIM_DATE = "not_verbatim_date"
WHYS = (READERS_DIFFER, FOLLOWS_MARKED, EXTENT, DISTANCE_ORIGIN, NOT_COLLECTION_CODE, NOT_VERBATIM_DATE)

SETTLED_LAYERS = frozenset({"settled", "verbatim"})
EXTENT_FIELDS = frozenset({"precise_location", "habitat", "collectors"})
ORIGIN_FIELDS = frozenset({"city", "county", "province_state"})
LOCALITY_ADVICE = frozenset({"precise_location", "country", "province_state", "county", "city"})
TAXON = "taxon"
COLLECTION_CODE = "collection_code"
VERBATIM = "verbatim_dts"
COLLECTING_DATES = ("date_visited_from", "date_visited_to")
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


def tokens(text: str) -> list[str]:
    """The text's runs of letters and digits, letter case and accents aside."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c))
    return re.findall(r"[^\W_]+", plain.casefold())


def writes(reading_text: str, literal: str) -> bool:
    """Whether a reading writes the literal: some run of the reading's whole tokens (tokens) has
    the literal's letters and digits, spacing and punctuation aside ("12mi. N" writes "12 mi. N")."""
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


# ---- rule 1 ---------------------------------------------------------------------------------

def _source_decides(key: str, value: FieldValue) -> bool:
    from .agreement import PLACE_VALUE_FIELDS

    return "decides" in value.evidence_relations.values() or (key in PLACE_VALUE_FIELDS
        and bool(value.authority_id))


def readers_differ(key: str, value: FieldValue, groups: Mapping[str, Sequence[Reading]]) -> str | None:
    """Rule 1's sentence, or None."""
    if _source_decides(key, value) or any(r.person_decided for group in groups.values() for r in group):
        return None
    if any(len(group) >= 2 and all(writes(r.text, value.literal) for r in group) for group in groups.values()):
        return None
    for group in groups.values():
        others = [r for r in group if not writes(r.text, value.literal)]
        if len(group) >= 2 and others and len(others) < len(group):
            taken = ", ".join(r.name for r in group if r not in others)
            return (f"Marked for a person, rule {READERS_DIFFER}: the readers of this label differ here; reading "
                f"{taken}'s text {value.literal!r} was taken on the image judgement alone, and reading "
                f"{', '.join(r.name for r in others)} does not write it.")
    return None


# ---- rule 3 ---------------------------------------------------------------------------------

@cache
def _role_stems() -> frozenset[str]:
    from .ontology_checks import role_words

    return frozenset(stem for word in role_words() for stem in tokens(word))


def _beside(text: str) -> bool:
    """Whether a unit's text outside the value holds more than headings, role words, sex signs
    and punctuation."""
    text = re.sub(r"[^\W\d_]+\s*:", " ", text)
    return any(token not in _role_stems() | ROLE_ABBREVIATIONS for token in tokens(text) if token not in HEADINGS)


def _breaks_between(text: str, start: int, end: int) -> bool:
    """Only white space between two offsets: the units stand next to each other, on one line or
    across a line break."""
    return start <= end and not text[start:end].strip()


def _epithet(text: str) -> bool:
    """One word of letters alone, in lower case or in capitals ("leucopus", "LIBYCUS"), as a
    species name follows its genus; never a capitalized word ("Siphonaptera"), a heading or a name."""
    word = text.strip()
    return re.fullmatch(r"[^\W\d_]+", word) is not None and (word.islower() or word.isupper())


def _extent_at(key: str, reading: Reading, place: tuple[int, int], cover: list) -> str | None:
    """The fuller text a reading writes for the value at one place, or None."""
    units = reading.units.units
    own = reading.observation_id
    start, end = place
    first, last = cover[0], cover[-1]
    s, e = first.readers[own].start, last.readers[own].end
    # The value ends its line inside a unit that goes on, on the next line, with more of it
    # ("ex Peromyscus" in the unit "ex Peromyscus\nleucopus").
    rest = reading.text[end:e]
    if end < e and not rest[:rest.find("\n") + 1].strip() and "\n" in rest and _beside(rest):
        return reading.text[start:e]
    i, j = units.index(first), units.index(last)
    if j + 1 < len(units):
        nxt = units[j + 1]
        span = nxt.readers[own]
        if span.text.strip() and _breaks_between(reading.text, max(end, e), span.start) and (
                (key == "precise_location" and set(nxt.fields) & LOCALITY_ADVICE)
                or (key == "habitat" and _epithet(span.text))):
            return reading.text[start:span.end]
    if key == "precise_location" and i > 0:
        before = units[i - 1]
        span = before.readers[own]
        if (span.text.strip() and _breaks_between(reading.text, span.end, min(start, s))
                and set(before.fields) & LOCALITY_ADVICE):
            return reading.text[span.start:end]
    return None


def _taxon_extent(value: FieldValue, groups: Mapping[str, Sequence[Reading]]) -> str | None:
    """The addition to rule 3 for the taxon: a value of one word (a genus alone) on a label whose
    reading units hold another part of a name it leaves out, a unit the first pass marks as a species
    or an author, or advises for the taxon, that some reader writes text at."""
    from .agreement import covering_units

    if len(tokens(value.literal)) != 1:
        return None
    for group in groups.values():
        for reading in group:
            if reading.units is None or reading.observation_id not in reading.units.units[0].readers:
                continue
            covered = {id(unit) for cover in covering_units(reading, value.literal) for unit in cover}
            for unit in reading.units.units:
                if id(unit) in covered or not (unit.role in ("species", "author") or TAXON in unit.fields):
                    continue
                texts = [span.text for span in unit.readers.values() if span.text.strip()]
                if texts:
                    return (f"Marked for a person, rule {EXTENT}: the label writes more of the name, {texts[0]!r}, "
                        "which the value leaves out.")
    return None


def extent(key: str, value: FieldValue, groups: Mapping[str, Sequence[Reading]]) -> str | None:
    """Rule 3's sentence, or None."""
    from .agreement import covering_units

    if key == TAXON:
        return _taxon_extent(value, groups)
    if key not in EXTENT_FIELDS:
        return None
    words = value.literal.split()
    head = words[0] if words else ""
    if key in ("precise_location", "habitat") and re.fullmatch(r"[^\W\d_]+[:.]", head) \
            and tokens(head)[0] in HEADINGS and len(words) > 1:
        return (f"Marked for a person, rule {EXTENT}: the value starts with the label's heading {head!r}, "
            "which is not part of it.")
    if key == "collectors" and any(token in _role_stems() for token in tokens(value.literal)):
        return (f"Marked for a person, rule {EXTENT}: the value holds a role word, which is not part of a "
            "collector's name.")
    fuller = None
    for group in groups.values():
        for reading in group:
            if reading.units is None or reading.observation_id not in reading.units.units[0].readers:
                return None
            from .agreement import literal_places

            places = literal_places(reading.text, value.literal)
            covers = covering_units(reading, value.literal)
            if not places or len(places) != len(covers) or not all(covers):
                return None
            for place, cover in zip(places, covers):
                found = _extent_at(key, reading, place, cover)
                if found is None:
                    return None
                fuller = fuller or found
    if fuller is None:
        return None
    return (f"Marked for a person, rule {EXTENT}: every reading of the label writes more of it here, "
        f"{fuller!r}; the value may be cut short.")


# ---- rule 4 ---------------------------------------------------------------------------------

def distance_origin(key: str, value: FieldValue, groups: Mapping[str, Sequence[Reading]]) -> str | None:
    from .agreement import literal_places

    if key not in ORIGIN_FIELDS:
        return None
    seen = False
    for group in groups.values():
        for reading in group:
            for start, _ in literal_places(reading.text, value.literal):
                if not DISTANCE.search(reading.text[max(0, start - 60):start]):
                    return None
                seen = True
    if not seen:
        return None
    return (f"Marked for a person, rule {DISTANCE_ORIGIN}: the label names {value.literal.strip(' ,')!r} only as "
        "the place a distance is measured from, not as the collecting place.")


@cache
def _headings() -> frozenset[str]:
    from specimen_digitization.ontology import ontology

    return frozenset("".join(tokens(form)) for item in ontology().notations
        if item.id == "lewis_collection_heading" for form in item.written)


def not_collection_code(key: str, value: FieldValue) -> str | None:
    if key != COLLECTION_CODE or "".join(tokens(value.literal)) in _headings():
        return None
    return (f"Marked for a person, rule {NOT_COLLECTION_CODE}: {value.literal!r} is not the collection heading "
        "the owner ruled a Collection Code; a slide, preparation or field number is not one.")


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


def not_verbatim_date(key: str, value: FieldValue, fields: Mapping[str, FieldValue], date_rules) -> str | None:
    if key != VERBATIM:
        return None
    literal = value.literal.strip()
    without_time = CLOCK.sub(" ", literal).strip(" ,;")
    why = None
    if without_time and _day(without_time, date_rules):
        why = "is an exact date"
    elif any(_slide_code(word.strip(".,;()"), date_rules) for word in literal.split()):
        why = "holds a slide code"
    else:
        same = "".join(tokens(literal))
        for other in (*COLLECTING_DATES, IDENTIFIED):
            held = fields.get(other)
            if not _settled(held) or "".join(tokens(held.literal)) != same:
                continue
            if other == IDENTIFIED:
                why = "is the text the identification date was settled from"
            elif held.parsed and len(held.parsed) == 10:
                why = "is the text an exact collecting date was settled from"
            if why:
                break
    if why is None:
        return None
    return (f"Marked for a person, rule {NOT_VERBATIM_DATE}: {literal!r} {why}; Verbatim D/T/S holds only "
        "date wording that is not an exact date.")


# ---- the pass ---------------------------------------------------------------------------------

def _marked_fields(run) -> set[str]:
    from .step import marked_reasons

    return {code.split(":")[1] for code in marked_reasons(run) if code.count(":") >= 2}


def review(run, *, readings: Sequence[Reading], human: Collection[str] = (), date_rules=None) -> list[str]:
    """Flag the run's settled values by the rules above, replacing this rule's earlier findings;
    the codes of the marks made. Called by step.apply_outcomes after the check stage and by
    step.refinalize."""
    from .ontology_checks import _labels, _with_sentence
    from .step import marked_code

    rows = {item.id: item for item in run.evidence}
    run.findings[:] = [finding for finding in run.findings if finding.rule_id != RULE]
    # A field another rule marked already (the settlement's text_only or conflict, the check stage,
    # the QR code) is a person's already: it gets no second mark.
    already = _marked_fields(run)
    sentences: dict[str, tuple[str, str]] = {}
    for key, value in run.fields.items():
        if key in human or key in already or not _settled(value):
            continue
        groups = _label_groups(value, readings, rows)
        for why, sentence in (
                (NOT_COLLECTION_CODE, not_collection_code(key, value)),
                (NOT_VERBATIM_DATE, not_verbatim_date(key, value, run.fields, date_rules)),
                (DISTANCE_ORIGIN, distance_origin(key, value, groups)),
                (EXTENT, extent(key, value, groups)),
                (READERS_DIFFER, readers_differ(key, value, groups))):
            if sentence:
                sentences[key] = (why, sentence)
                break
    marked = already | set(sentences)
    changed = True
    while changed:
        changed = False
        for key, value in run.fields.items():
            if (key in human or key in marked or value.state != ValueState.SUPPORTED
                    or value.layer != "derived"):
                continue
            sources = [name for name in value.derived_from if name in marked]
            if sources:
                sentences[key] = (FOLLOWS_MARKED, f"Marked for a person, rule {FOLLOWS_MARKED}: it is derived from "
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
