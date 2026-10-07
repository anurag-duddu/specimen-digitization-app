"""Dates-only adapters over the shared immutable evidence graph.

An explicit printed event key links labels; proximity, chronological order and
an extractor assignment never do. Only independently quoted unanimous readings
can supply a component. The original readings and candidates remain intact.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .contracts import (
    DependencyPin, EventHypothesis, EventKind, FieldKey, FieldResolution, FragmentRelation,
    RelationKind, SourceFragment, SpecialistRequest, SpecialistRole, WorkState, digest,
)

TEMPORAL_LINK_RULE = "explicit-temporal-event-link/v1"
_EVENT = re.compile(r"^(Collecting|Determination) event:\s*([A-Za-z0-9][A-Za-z0-9_.-]{0,63})\s*$", re.I)
_COMPONENT = re.compile(r"^(Date from|Date to|Date|Day and month|Year|Date order):\s*(\S.*?)\s*$", re.I)
_OTHER_EVENT = re.compile(r"\b(?:prep(?:aration|ared)?|slide|genitalia|terminalia)\b", re.I)


def temporal_dependency_pins(request, keys, checkpoints, preserved):
    """Bind a narrowed To repair to a real native source; never manufacture one."""
    pins = request.dependencies
    if (request.role != SpecialistRole.TEMPORAL or FieldKey.DATE_VISITED_TO not in keys
            or FieldKey.DATE_VISITED_FROM in keys
            or str(FieldKey.DATE_VISITED_FROM) in preserved
            or any(pin.field_key == FieldKey.DATE_VISITED_FROM for pin in pins)):
        return pins
    source = checkpoints.get(FieldKey.DATE_VISITED_FROM)
    if (source is None or source.resolution.work_state != WorkState.RESOLVED
            or source.resolution.value_layer != "settled"):
        return pins
    return (*pins, DependencyPin(field_key=source.field_key, revision=source.revision,
                                digest=digest(source.resolution)))


def temporal_dependency_source(request, source, source_revision):
    """Reconstruct the omitted native From with its exact consumed context.

    Context may restore only recorded dependencies. Calendar value, precision,
    event, assemblies, readings and evidence must still equal deterministic
    settlement. Native context does not supply a missing date or event.
    """
    from .evidence import EvidenceError

    pins = [pin for pin in request.dependencies if pin.field_key == source.field_key]
    if len(pins) != 1 or pins[0].revision != source_revision:
        raise EvidenceError("Collecting From source context requires one exact native dependency")
    pin = pins[0]
    contexts = [item for item in getattr(request, "settled_context", ()) if item.pin.field_key == source.field_key]
    if len(contexts) > 1:
        raise EvidenceError("Collecting From source context must be unambiguous")
    if contexts:
        context = contexts[0]
        native = FieldResolution.model_validate(context.resolution.model_dump(mode="json"))
        reconstructed = FieldResolution.model_validate({**source.model_dump(mode="json"),
            "dependencies": native.dependencies})
        if (context.pin != pin or reconstructed != native or digest(native) != pin.digest
                or re.fullmatch(r"[a-f0-9]{64}", context.accepted_proof_digest) is None):
            raise EvidenceError("Collecting From source context differs from deterministic settled event")
        source = reconstructed
    if digest(source) != pin.digest:
        raise EvidenceError("Collecting From dependency differs from exact settled event")
    return source


@dataclass(frozen=True)
class _Component:
    name: str
    fragment: SourceFragment
    evidence_ids: tuple[str, ...]


def _label_components(request, readings):
    """Return components only when every retained independent reader agrees."""
    if len(readings) < 2 or len({items[0].reader for items in readings}) < 2:
        return None
    rows = {item.id: item for item in request.evidence}
    qualified = []
    for fragments in readings:
        source = fragments[0]
        text = source.observation_text
        if (any(item.unreadable for item in fragments)
                or source.observation_digest != hashlib.sha256(text.encode()).hexdigest()
                or _OTHER_EVENT.search(text)):
            return None
        markers = [_EVENT.fullmatch(line.strip()) for line in text.splitlines()]
        markers = [match for match in markers if match]
        if len(markers) != 1:
            return None
        marker = markers[0]
        kind = EventKind.COLLECTING if marker[1].lower() == "collecting" else EventKind.DETERMINATION
        components, offset = [], 0
        for line in text.splitlines(keepends=True):
            match = _COMPONENT.fullmatch(line.strip())
            if match:
                name, literal = match[1].lower(), match[2]
                if kind == EventKind.DETERMINATION and name in {"date from", "date to"}:
                    return None
                field = (FieldKey.DATE_IDENTIFIED if kind == EventKind.DETERMINATION else
                         FieldKey.DATE_VISITED_TO if name == "date to" else FieldKey.DATE_VISITED_FROM)
                start = offset + line.find(literal)
                candidates = [item for item in request.organiser_candidates
                    if item.field_key == field and item.observation_id == source.observation_id
                    and item.region_id == source.region_id and item.literal == literal
                    and (item.start, item.end) == (start, start + len(literal))
                    and item.status != "ungrounded" and set(item.evidence_ids) <= set(rows)
                    and item.evidence_ids and all(rows[eid].kind == "literal"
                        and _quote_matches(rows[eid], source, start, literal)
                        and rows[eid].excerpt in text and literal in rows[eid].excerpt
                        for eid in item.evidence_ids)]
                evidence_ids = candidates[0].evidence_ids if len(candidates) == 1 else ()
                if not evidence_ids:
                    # The shared adapter deliberately withholds a span when the
                    # literal repeats elsewhere. The explicit temporal role and
                    # independently retained modern quote can prove this exact
                    # occurrence without changing that general policy.
                    quoted = [row for row in rows.values() if row.kind == "literal"
                        and row.source_version == "native-evidence-adapter/v1"
                        and row.excerpt.strip() == match[0]
                        and _quote_matches(row, source, start, literal)]
                    hints = [item for item in request.organiser_candidates
                        if item.field_key == field and item.literal == literal
                        and item.status == "ungrounded"
                        and re.fullmatch(r"literal_occurs_(?:[2-9]|[1-9]\d+)_times_in_the_reading", item.reason)
                        and any(row.locator.startswith("reading:" + str(item.label) + ":"
                            + source.observation_id + "#") for row in quoted)]
                    if not hints or len(quoted) != 1:
                        return None
                    evidence_ids = (quoted[0].id,)
                fragment = source.model_copy(update={
                    "id": "temporal-fragment:" + digest([source.observation_id, start, literal, TEMPORAL_LINK_RULE]),
                    "start": start, "end": start + len(literal), "literal": literal,
                    "order": len(components), "granularity": "span"})
                fragment = SourceFragment.model_validate(fragment.model_dump(mode="json"))
                components.append(_Component(name, fragment, evidence_ids))
            offset += len(line)
        if not components or len({item.name for item in components}) != len(components):
            return None
        qualified.append(((kind, marker[2]), components))
    signatures = {(key, tuple((item.name, item.fragment.literal) for item in items))
                  for key, items in qualified}
    if len(signatures) != 1:
        return None
    key, first = qualified[0]
    # One assertion span; every independently quoted counterpart supports it.
    merged = [_Component(item.name, item.fragment, tuple(dict.fromkeys(
        eid for _, items in qualified for peer in items if peer.name == item.name
        for eid in peer.evidence_ids))) for item in first]
    return key, merged


def _quote_matches(row, source, start, literal):
    match = re.fullmatch(r"reading:[^:]+:" + re.escape(source.observation_id)
        + r"#quote=(\d+)-(\d+);literal=(\d+)-(\d+)", row.locator)
    if match is None:
        return False
    begin, end, literal_begin, literal_end = map(int, match.groups())
    return (0 <= begin <= start < start + len(literal) <= end <= len(source.observation_text)
        and source.observation_text[begin:end] == row.excerpt
        and (literal_begin, literal_end) == (start, start + len(literal)))


def qualify_temporal_links(request: SpecialistRequest) -> SpecialistRequest:
    """Admit explicitly linked date components without changing shared contracts.

    Supported printed roles are Date, Date from, Date to, Day and month, Year,
    and Date order (DMY/MDY), under a Collecting/Determination event key. This
    conservative adapter does not infer links for general handwritten layouts.
    """
    if request.role != SpecialistRole.TEMPORAL:
        return request
    from .evidence import EvidenceError, assemble_field
    labels = {}
    for fragment in request.fragments:
        labels.setdefault(fragment.region_id, {}).setdefault(fragment.observation_id, []).append(fragment)
    groups, refused = {}, set()
    for readings in labels.values():
        qualified = _label_components(request, list(readings.values()))
        if qualified:
            key, components = qualified
            groups.setdefault(key, []).extend(components)
        else:
            for fragments in readings.values():
                for line in fragments[0].observation_text.splitlines():
                    marker = _EVENT.fullmatch(line.strip())
                    if marker:
                        kind = EventKind.COLLECTING if marker[1].lower() == "collecting" else EventKind.DETERMINATION
                        refused.add((kind, marker[2]))
    fragments, events, relations, assemblies = [], [], [], []
    for (kind, key), components in groups.items():
        if (kind, key) in refused:
            continue
        names = {}
        for component in components:
            names.setdefault(component.name, []).append(component)
        if any(len({item.fragment.literal for item in items}) != 1 for items in names.values()):
            continue
        if ("date" in names and ("date from" in names or "day and month" in names)
                or "date from" in names and "day and month" in names
                or "day and month" in names and "year" not in names):
            continue
        chosen = {name: items[0] for name, items in names.items()}
        date_name = next((name for name in ("date", "date from", "day and month") if name in chosen), None)
        if date_name is None and "date to" not in chosen:
            continue
        ids = tuple(dict.fromkeys(eid for item in components for eid in item.evidence_ids))
        event = EventHypothesis(id="temporal-event:" + digest([kind, key, [item.fragment.id for item in components]]),
            scope=request.scope, kind=kind, fragment_ids=tuple(item.fragment.id for item in components),
            evidence_ids=ids, reason="explicit_printed_event_key_unanimous_across_readers",
            rule_version=TEMPORAL_LINK_RULE, status="accepted", validator_version=TEMPORAL_LINK_RULE)
        local_relations, local_assemblies = [], []
        for name in (date_name, "date to"):
            if name not in chosen:
                continue
            parts = (chosen[name].fragment, *(chosen[extra].fragment for extra in ("year", "date order") if extra in chosen))
            field = (FieldKey.DATE_IDENTIFIED if kind == EventKind.DETERMINATION else
                     FieldKey.DATE_VISITED_TO if name == "date to" else FieldKey.DATE_VISITED_FROM)
            links = ()
            if len(parts) > 1:
                links = (FragmentRelation(id="temporal-relation:" + digest([event.id, field]),
                    scope=request.scope, fragment_ids=tuple(item.id for item in parts),
                    kind=RelationKind.CONTINUATION, event_id=event.id, evidence_ids=ids,
                    reason="explicit_date_roles_under_same_printed_event_key",
                    proposer_version=TEMPORAL_LINK_RULE, validator_version=TEMPORAL_LINK_RULE, status="accepted"),)
            assembly = assemble_field(assembly_id="temporal-assembly:" + digest([event.id, field]),
                scope=request.scope, field_key=field, fragments=parts, event=event,
                relations=links, assertion_kind="complementary" if links else "complete")
            local_relations.extend(links)
            local_assemblies.append(assembly)
        trial = request.model_copy(update={"fragments": (*request.fragments, *(item.fragment for item in components)),
            "events": (*request.events, event), "relations": (*request.relations, *local_relations),
            "assemblies": (*request.assemblies, *local_assemblies)})
        valid_assemblies = []
        for assembly in local_assemblies:
            try:
                parse_temporal_assembly(trial, assembly)
            except EvidenceError:
                continue
            valid_assemblies.append(assembly)
        if not valid_assemblies:
            continue
        fragments.extend(item.fragment for item in components)
        events.append(event)
        relations.extend(local_relations)
        assemblies.extend(valid_assemblies)
    if not events:
        return request
    def extend_exact(existing, additions):
        by_id = {item.id: item for item in existing}
        result = list(existing)
        for item in additions:
            prior = by_id.get(item.id)
            if prior is not None:
                if prior != item:
                    raise EvidenceError("Temporal graph identity differs from retained evidence")
                continue
            by_id[item.id] = item
            result.append(item)
        return tuple(result)

    return SpecialistRequest.model_validate({**request.model_dump(mode="json"),
        "fragments": extend_exact(request.fragments, fragments),
        "events": extend_exact(request.events, events),
        "relations": extend_exact(request.relations, relations),
        "assemblies": extend_exact(request.assemblies, assemblies)})


def _component_name(fragment):
    start = fragment.observation_text.rfind("\n", 0, fragment.start) + 1
    return fragment.observation_text[start:fragment.start].strip().rstrip(":").lower()


def parse_temporal_assembly(request, assembly):
    """Parse written context only from a validated explicit event continuation."""
    from specimen_digitization.application.domain import LookupStatus
    from specimen_digitization.application.field_validators import date_parser
    from pathlib import Path
    from .evidence import (
        TEMPORAL_CONTEXT_SOURCE_SHA256, EvidenceError, ParsedTemporal, parse_temporal, validate_assembly,
    )
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != TEMPORAL_CONTEXT_SOURCE_SHA256:
        raise EvidenceError("Temporal context source differs from qualified validator bytes")
    validate_assembly(request, assembly)
    event = next(item for item in request.events if item.id == assembly.event_id)
    if event.validator_version != TEMPORAL_LINK_RULE:
        return parse_temporal(assembly.interpreted_text)
    fragments = {item.id: item for item in request.fragments}
    parts = [fragments[key] for key in assembly.fragment_ids]
    first, extras = parts[0], {_component_name(item): item.literal for item in parts[1:]}
    year, order = extras.get("year"), extras.get("date order")
    if set(extras) - {"year", "date order"} or year is not None and not re.fullmatch(r"\d{4}", year):
        raise EvidenceError("Temporal continuation needs a complete written year")
    if order is not None and order not in {"DMY", "MDY"}:
        raise EvidenceError("Temporal numeric order is not explicitly qualified")
    try:
        parsed = parse_temporal(first.literal)
    except EvidenceError:
        parsed = None
    if parsed is not None:
        if year is not None and parsed.canonical[:4] != year:
            raise EvidenceError("Written year conflicts with complete date")
        if _component_name(first) == "day and month" and parsed.precision != "day":
            raise EvidenceError("Day and month context cannot turn a month/year into a written day")
        # ISO and equal numeric month/day readings already have one calendar
        # value; an order annotation cannot change their interpretation.
        numeric = re.fullmatch(r"(\d{1,2})([-./])(\d{1,2})\2(?:\d{2}|\d{4})", first.literal)
        if order is None or numeric is None or int(numeric[1]) == int(numeric[3]):
            return parsed
    result = date_parser(first.literal, source_text=assembly.interpreted_text,
        year_literal=year, date_rules={"version": "insects-date-G24-G29-v1",
            "two_digit_year_century": 1900, "roman_numeral_months": True})
    readings = (result.parsed or {}).get("readings", [])
    if year is not None and _component_name(first) != "day and month" and any(
            item["order"] in {"month-year", "monthname-year"} for item in readings):
        raise EvidenceError("A year alone cannot choose day versus short-year notation")
    if _component_name(first) == "day and month" and year is not None:
        readings = [item for item in readings if item["year"] == int(year) and item["precision"] == "day"]
    elif year is not None:
        readings = [item for item in readings if item["year"] == int(year)]
    if order is not None:
        readings = [item for item in readings if item["order"] ==
                    {"DMY": "day-month-year", "MDY": "month-day-year"}[order]]
    if (result.outcome not in {LookupStatus.SUCCESS, LookupStatus.AMBIGUOUS}
            or len(readings) != 1 or readings[0]["year"] is None):
        raise EvidenceError("Date has ambiguous readings or unavailable explicit event context")
    reading = readings[0]
    return ParsedTemporal(literal=first.literal, canonical=reading["iso"], precision=reading["precision"],
                          century_rule=reading["century_rule"])


def parse_temporal_text(request, text, field_key):
    """Resolve one exact utility argument from its immutable owned assemblies."""
    from .evidence import EvidenceError
    matches = [parse_temporal_assembly(request, assembly) for assembly in request.assemblies
               if assembly.field_key == field_key and assembly.interpreted_text == text]
    if not matches or len({digest(item) for item in matches}) != 1:
        raise EvidenceError("Temporal utility needs one agreed owned assembly interpretation")
    return matches[0]


def has_written_collecting_to(request):
    """A retained explicit endpoint, even ambiguous, forbids single-date G44.

    This grants no value or authority. A disagreement/unreadable counterpart
    needs review rather than being erased by copying a different From date.
    """
    texts = {item.observation_id: item.observation_text for item in request.fragments}
    for text in texts.values():
        markers = [match for line in text.splitlines() if (match := _EVENT.fullmatch(line.strip()))]
        collecting = len(markers) == 1 and markers[0][1].lower() == "collecting" and not _OTHER_EVENT.search(text)
        for line in text.splitlines():
            if re.fullmatch(r"\s*date_visited_to:\s*\S.*", line):
                return True
            component = _COMPONENT.fullmatch(line.strip())
            if collecting and component and component[1].lower() == "date to":
                return True
    return False


def has_multiple_written_date_events(request, kind):
    """Unsettled dated event labels also forbid selecting a different event."""
    keys = set()
    texts = {item.observation_id: item.observation_text for item in request.fragments}
    for text in texts.values():
        markers = [match for line in text.splitlines() if (match := _EVENT.fullmatch(line.strip()))]
        if len(markers) != 1:
            continue
        marker_kind = EventKind.COLLECTING if markers[0][1].lower() == "collecting" else EventKind.DETERMINATION
        if marker_kind != kind:
            continue
        if any(component and component[1].lower() in {"date", "date from", "day and month"}
               for line in text.splitlines() if (component := _COMPONENT.fullmatch(line.strip()))):
            keys.add(markers[0][2])
    return len(keys) > 1
