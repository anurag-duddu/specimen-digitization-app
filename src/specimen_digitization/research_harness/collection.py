"""Collection-only qualification and recovery from immutable label readings.

This is a local evidence procedure, not a publisher join or a model inference.
Recovered spans reuse native evidence IDs; missing native quotes stay missing.
"""
from __future__ import annotations

import re
from collections import defaultdict

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.application.organiser import SOURCE, parse_locator
from .contracts import (
    ALL_FIELDS, EventHypothesis, EventKind, FieldKey, FieldResolution, SourceFragment,
    SpecialistRequest, SpecialistRole, WorkState, digest,
)
from .evidence import EvidenceError, assemble_field, catalog_literal, parse_measurement, validate_assembly

COLLECTION_RULE = "collection-qualified-spans/v1"
COLLECTION_FIELDS = frozenset((FieldKey.FMNH_INS_NUMBER, FieldKey.COLLECTION_CODE,
    FieldKey.HABITAT, FieldKey.COLLECTION_METHOD))
_MARKERS = {
    FieldKey.FMNH_INS_NUMBER: r"fmnh_ins_number|catalog(?:ue)?(?: number| no\.?)?",
    FieldKey.COLLECTION_CODE: r"collection_code|collection code",
    FieldKey.HABITAT: r"habitat|microhabitat",
    FieldKey.COLLECTION_METHOD: r"collection_method|collection method|collecting method|method",
}
_MARKER = re.compile(r"^\s*(?P<key>" + "|".join(_MARKERS.values()) + r")\s*[:=]\s*", re.I)
# An explicit other-field key is a boundary, even when it is indented. Its
# value cannot become collection evidence merely through an organiser hint.
# These aliases only delimit role/context; they assign no new field meaning.
_FIELD_BOUNDARY = re.compile(r"^\s*(?:(?:" + "|".join(_MARKERS.values()) + "|"
    + "|".join(re.escape(str(key)) for key in ALL_FIELDS)
    + r"|locality|collector|identified(?: by)?|determiner|det(?:ermination)?\.?"
    + r"|prep(?:aration|ared)?\.?|date(?: collected| identified)?|elevation)\s*[:=]"
    + r"|leg\.(?=\s|$))", re.I)
_METHOD = re.compile(
    r"(?:(?:light|uv|blacklight|malaise|pitfall|bait|sticky|flight intercept|pan|berlese)\s+trap"
    r"|(?:at|by|in)\s+(?:light|uv light)|sweep(?:ing| net)?|beating(?: vegetation)?"
    r"|hand collect(?:ing|ed)?|aspirat(?:or|ion)|netting|sifting(?: litter)?)", re.I)
_HABITAT = re.compile(
    r"(?:(?:oak|pine|deciduous|coniferous|mixed|tropical|wet|dry|open|coastal|montane)\s+)*"
    r"(?:woodland|forest|grassland|meadow|marsh|swamp|wetland|scrub|savanna|desert|leaf litter)"
    r"(?:\s+(?:margin|edge|floor|canopy|understory|clearing))?", re.I)
_ORIGINAL_HABITAT = re.compile(_HABITAT.pattern.replace("|montane)", "|montane|mossy)"), re.I)
_WRONG_CONTEXT = re.compile(
    r"\b(?:prov(?:ince)?|county|city|town|latitude|longitude|locality|collector|collected by|leg(?=\.)|"
    r"det(?:ermined|ermination)?|identified|prep(?:ared|aration)?|slide|genitalia|terminalia)\b", re.I)
_PREFIX = re.compile(r"\s*FMNH\s*[- ]?\s*INS\s*[#:]?\s*", re.I)


def _compact(text):
    return " ".join(text.split())


def _source_prefix(fragment):
    prior = fragment.observation_text[:fragment.start]
    before = prior.split("\n")[-1]
    if not before.strip():
        previous = prior.rstrip(" \t\r\n").split("\n")[-1]
        if previous.rstrip().endswith((":", "=")):
            before = previous
    return before


def _explicit(key, fragment):
    before = _source_prefix(fragment)
    return re.fullmatch(r"\s*(?:" + _MARKERS[key] + r")\s*[:=]\s*", before, re.I) is not None


def _check_source_role(key, fragment):
    before = _source_prefix(fragment)
    marker = _FIELD_BOUNDARY.match(before)
    explicit = _explicit(key, fragment)
    if (marker and not explicit) or (_WRONG_CONTEXT.search(before) and not explicit):
        raise EvidenceError("Collection span belongs to another marked field or event")


def qualify_collection_span(key: FieldKey, fragment: SourceFragment, *, original_reading=False) -> str:
    """Return the exact field value, or refuse unsupported kind/event context."""
    text = _compact(fragment.literal)
    if key not in COLLECTION_FIELDS or fragment.unreadable or not text:
        raise EvidenceError("Collection assertion lacks readable field-qualified context")
    explicit = _explicit(key, fragment)
    _check_source_role(key, fragment)
    if key != FieldKey.FMNH_INS_NUMBER and any(candidate_key == key and start == fragment.start
        and end > fragment.end for candidate_key, start, end in _spans(fragment, original_reading=original_reading)):
        raise EvidenceError("Collection span omits the rest of a complete written assertion")
    if key == FieldKey.FMNH_INS_NUMBER:
        digits = catalog_literal(fragment.literal)
        for candidate_key, start, end in _spans(fragment):
            if candidate_key == key and start <= fragment.start < fragment.end <= end:
                if catalog_literal(fragment.observation_text[start:end]) != digits:
                    raise EvidenceError("Catalogue span truncates the complete written identifier")
        previous = fragment.observation_text[:fragment.start].rstrip("\r\n").split("\n")[-1]
        if not (explicit or _PREFIX.match(text) or _PREFIX.fullmatch(previous)):
            raise EvidenceError("Bare digits lack catalogue notation; they do not establish identity")
        return digits
    if key == FieldKey.COLLECTION_CODE:
        if (not explicit or _PREFIX.match(text) or _WRONG_CONTEXT.search(text)
            or not re.fullmatch(r"(?=.*[A-Za-z])[A-Za-z0-9]+(?:[ _./-][A-Za-z0-9]+)*", text)
            or re.fullmatch(r"(?:[IVX]+|\d{1,2})-\d{1,2}-(?:\d{2}|\d{4})-[A-Za-z0-9]+", text, re.I)):
            raise EvidenceError("Collection code needs explicit code context, not catalogue or preparation notation")
    else:
        if _PREFIX.match(text) or _WRONG_CONTEXT.search(text) or not re.search(r"[^\W\d_]{2}", text):
            raise EvidenceError("Collection assertion has locality/person/preparation kind")
        habitat_grammar = _ORIGINAL_HABITAT if original_reading else _HABITAT
        method, habitat = bool(_METHOD.fullmatch(text)), bool(habitat_grammar.fullmatch(text))
        if key == FieldKey.HABITAT and (method or not (explicit or habitat)):
            raise EvidenceError("Habitat requires ecological context; collecting method is a different field")
        if key == FieldKey.COLLECTION_METHOD and (habitat or not (explicit or method)):
            raise EvidenceError("Collecting method requires collecting context; habitat is a different field")
        if re.fullmatch(r"[A-Za-z0-9]+(?:[-./][A-Za-z0-9]+)+", text) and re.search(r"\d", text):
            raise EvidenceError("Preparation/code token cannot satisfy habitat or method")
    return fragment.literal


def _spans(fragment, *, original_reading=False):
    """Offsets come from the whole original reading, never organiser hints."""
    text = fragment.observation_text
    lines, offset = [], 0
    for line in text.splitlines(keepends=True):
        lines.append((offset, line.rstrip("\r\n")))
        offset += len(line)
    consumed = set()
    for index, (offset, line) in enumerate(lines):
        if index in consumed:
            continue
        marker = _MARKER.match(line)
        if marker:
            key = next(key for key, pattern in _MARKERS.items()
                if re.fullmatch(pattern, marker["key"], re.I))
            start, end = offset + marker.end(), offset + len(line)
            # Explicit multiline assertions: one value line after an empty
            # marker, then visibly indented continuation lines only.
            next_index = index + 1
            if start == end and next_index < len(lines):
                at, value = lines[next_index]
                if not value.strip() or _FIELD_BOUNDARY.match(value):
                    continue
                start, end = at + len(value) - len(value.lstrip()), at + len(value)
                consumed.add(next_index)
                next_index += 1
            while next_index < len(lines):
                at, value = lines[next_index]
                if not value.strip() or not value[0].isspace() or _FIELD_BOUNDARY.match(value):
                    break
                end, next_index = at + len(value), next_index + 1
                consumed.add(next_index - 1)
            if start < end:
                yield key, start, end
        else:
            start, end = offset + len(line) - len(line.lstrip()), offset + len(line.rstrip())
            if start == end:
                continue
            stripped = text[start:end]
            if _PREFIX.fullmatch(stripped) and index + 1 < len(lines):
                at, following = lines[index + 1]
                if re.fullmatch(r"\s*\d{5,9}\s*", following):
                    yield FieldKey.FMNH_INS_NUMBER, start, at + len(following.rstrip())
                    consumed.add(index + 1)
            elif _PREFIX.match(stripped):
                yield FieldKey.FMNH_INS_NUMBER, start, end
            elif _METHOD.fullmatch(stripped):
                yield FieldKey.COLLECTION_METHOD, start, end
            elif (_ORIGINAL_HABITAT if original_reading else _HABITAT).fullmatch(stripped):
                yield FieldKey.HABITAT, start, end
            elif original_reading:
                habitat = _ORIGINAL_HABITAT.match(stripped)
                if habitat is None or not stripped[habitat.end():].startswith((" ", "\t")):
                    continue
                # The ecology and quantity are separate written assertions.
                # Keep the habitat's original span only when the whole suffix
                # is an unambiguous measurement, without discarding any token.
                try:
                    parse_measurement(stripped[habitat.end():].strip())
                except EvidenceError:
                    continue
                yield FieldKey.HABITAT, start, start + habitat.end()


def _reading_assertions(original, key, *, original_reading=False):
    values = []
    for candidate_key, start, end in _spans(original, original_reading=original_reading):
        if candidate_key != key:
            continue
        span = original.model_copy(update={"start": start, "end": end,
            "literal": original.observation_text[start:end]})
        try:
            value = qualify_collection_span(key, span, original_reading=original_reading)
        except EvidenceError:
            values.append(("unqualified", digest(span.literal)))
            continue
        values.append(_compact(value))
    return tuple(values)


def _covering_evidence(span, native_rows, observation_ids):
    """Bind the exact quote occurrence using the existing people admission route.

    Modern organiser locators identify one reading and an explicit quote span.
    Legacy native region quotes must have a unique occurrence containing this
    assertion. Identical text at another field cannot supply its evidence.
    """
    ids = []
    text = span.observation_text
    for row in native_rows:
        if (row.kind != "literal" or row.asset_id != span.asset_id or row.region_id != span.region_id
            or not set(row.observation_ids) <= observation_ids
            or len(set(row.observation_ids)) != len(row.observation_ids)
            or span.observation_id not in row.observation_ids or not row.excerpt):
            continue
        location = parse_locator(row.locator)
        if location is not None:
            if (row.source != SOURCE or location.observation_id != span.observation_id
                or tuple(row.observation_ids) != (span.observation_id,)
                or not 0 <= location.quote_start < location.quote_end <= len(text)
                or text[location.quote_start:location.quote_end] != row.excerpt
                or not location.quote_start <= span.start < span.end <= location.quote_end):
                continue
        else:
            if row.locator != "region:" + span.region_id or row.source not in {"label", SOURCE}:
                continue
            at = text.find(row.excerpt)
            if (at < 0 or text.find(row.excerpt, at + 1) >= 0
                or not at <= span.start < span.end <= at + len(row.excerpt)):
                continue
        ids.append(row.id)
    return tuple(ids)


def recover_collection_graph(scope, fragments, events, assemblies, *, native_rows, original_reading=False):
    """Add qualified omitted/misfiled spans backed by retained native quotes.

    One trusted decided reading supplies its label's assertions. Without a
    decision, every independent reader must agree. Raw graph data stays intact.
    Existing evidence and organiser proposals are never rewritten.
    No continuation relation or new native evidence is manufactured here.
    """
    observations = {}
    for fragment in fragments:
        observations.setdefault(fragment.observation_id, fragment)
    by_region = defaultdict(list)
    scans = {}
    for observation, original in observations.items():
        by_region[original.region_id].append(original)
        found = []
        if not any(row.unreadable for row in fragments if row.observation_id == observation):
            for key, start, end in _spans(original, original_reading=original_reading):
                span = original.model_copy(update={"id": "fragment:" + digest(
                    [observation, start, end, COLLECTION_RULE]), "start": start, "end": end,
                    "literal": original.observation_text[start:end], "granularity": "span"})
                try:
                    value = qualify_collection_span(key, span, original_reading=original_reading)
                except EvidenceError:
                    continue
                found.append((key, span, _compact(value)))
        scans[observation] = found
    for originals in by_region.values():
        chosen = [row for row in originals if row.input_source == "decided_transcript"]
        if len(chosen) > 1 or not chosen and len({row.reader for row in originals}) < 2:
            continue
        effective = chosen or originals
        original = effective[0]
        occurrences = defaultdict(int)
        for key, span, value in scans[original.observation_id]:
            position = occurrences[key]
            occurrences[key] += 1
            field_scans = {row.observation_id: [(item, candidate_value) for candidate_key, item, candidate_value
                in scans[row.observation_id] if candidate_key == key] for row in originals}
            signatures = {tuple(candidate_value for _, candidate_value in field_scans[row.observation_id])
                for row in effective}
            if len(signatures) != 1:
                continue
            # Prefer the existing exact assembly to duplicating organiser work.
            existing = [row for row in assemblies if row.field_key == key and any(
                item.id in row.fragment_ids and item.observation_id == span.observation_id
                and span.start <= item.start < item.end <= span.end for item in fragments)]
            if any(_compact(catalog_literal(row.interpreted_text) if key == FieldKey.FMNH_INS_NUMBER
                else row.interpreted_text) == value for row in existing):
                continue
            evidenced = []
            for reader in sorted(originals, key=lambda row: row.input_source != "decided_transcript"):
                if chosen and reader.observation_id != original.observation_id:
                    # Preserve the historical raw-only quote route only when
                    # its exact assertion also agrees with the decided reading.
                    if ({tuple(candidate_value for _, candidate_value in items) for items in field_scans.values()}
                        != signatures or field_scans[reader.observation_id][position][0].literal != span.literal):
                        continue
                peer_span, _ = field_scans[reader.observation_id][position]
                ids = _covering_evidence(peer_span, native_rows, {item.observation_id for item in originals})
                if ids:
                    evidenced.append((peer_span, ids))
            if not evidenced:
                continue
            span, ids = evidenced[0]
            kind = EventKind.COLLECTING if key in {FieldKey.HABITAT, FieldKey.COLLECTION_METHOD} else EventKind.UNKNOWN
            event = EventHypothesis(id="event:" + digest([span.id, key, COLLECTION_RULE]),
                scope=scope, kind=kind, fragment_ids=(span.id,), evidence_ids=ids,
                reason="Collection kind and exact decided-reading span qualified" if chosen else
                    "Collection kind and exact independent-reader spans qualified",
                rule_version=COLLECTION_RULE, status="accepted", validator_version=COLLECTION_RULE)
            assembly = assemble_field(assembly_id="assembly:" + digest([span.id, key, COLLECTION_RULE]),
                scope=scope, field_key=key, fragments=(span,), event=event)
            if span.id not in {row.id for row in fragments}:
                fragments.append(span)
            events.append(event)
            assemblies.append(assembly)


def collection_resolution(request: SpecialistRequest, key: FieldKey) -> FieldResolution:
    """Settle all independent collection assertions, preserving exact raw lineage."""
    if key not in COLLECTION_FIELDS or key not in request.field_keys:
        raise EvidenceError("Collection settlement exceeds owned fields")
    from .prompts import COLLECTION_PROVENANCE_PROMPT_VERSION
    original_reading = (request.role == SpecialistRole.COLLECTION
        and request.prompt.version == COLLECTION_PROVENANCE_PROMPT_VERSION)
    assertions = [row for row in request.assemblies if row.field_key == key]
    parts = {row.id: row for row in request.fragments}
    qualified = []
    for assembly in assertions:
        validate_assembly(request, assembly)
        event = next(row for row in request.events if row.id == assembly.event_id)
        if key in {FieldKey.HABITAT, FieldKey.COLLECTION_METHOD} and event.kind in {
            EventKind.PREPARATION, EventKind.DETERMINATION}:
            continue
        selected = [parts[fid] for fid in assembly.fragment_ids]
        contrary = False
        for part in selected:
            peers = {row.observation_id: row for row in request.fragments if row.region_id == part.region_id}
            chosen = [row for row in peers.values() if row.input_source == "decided_transcript"]
            if len(chosen) > 1:
                return _held(key, "multiple_decided_collection_readings")
            if chosen and part.observation_id != chosen[0].observation_id and (
                chosen[0].unreadable or _reading_assertions(chosen[0], key, original_reading=original_reading)
                    != _reading_assertions(part, key, original_reading=original_reading)
                or _compact(part.literal) not in _compact(chosen[0].observation_text)):
                contrary = True
        if contrary:
            continue  # An unselected raw alternative never overrides its label's decision.
        # Existing accepted continuation relations authorize the joined text.
        span = selected[0].model_copy(update={"literal": assembly.interpreted_text})
        try:
            for part in selected:
                _check_source_role(key, part)
            value = qualify_collection_span(key, span, original_reading=original_reading)
        except EvidenceError:
            continue
        qualified.append((assembly, selected, value))
    if not qualified:
        return _held(key, "missing_or_unqualified_collection_assertion")
    if len({_compact(value) for _, _, value in qualified}) != 1:
        return _held(key, "conflicting_collection_assertions")
    covered_regions = {part.region_id for _, fragments, _ in qualified for part in fragments}
    by_region = defaultdict(dict)
    for part in request.fragments:
        by_region[part.region_id][part.observation_id] = part
    for region, readings in by_region.items():
        if region in covered_regions:
            continue
        chosen = [part for part in readings.values() if part.input_source == "decided_transcript"]
        if any(_reading_assertions(part, key, original_reading=original_reading)
            for part in (chosen if len(chosen) == 1 else readings.values())):
            return _held(key, "independent_collection_assertion_lacks_qualified_quote")
    assembly, selected, value = qualified[0]
    complete_parts = {part.id: _compact(asserted_value) for _, fragments, asserted_value in qualified
        if len(fragments) == 1 for part in fragments}
    # No decision means every reader must agree. A selected reading applies
    # only within its label; cross-label qualified assertions still all agree.
    for fragment in (part for _, fragments, _ in qualified for part in fragments):
        peers = {row.observation_id: row for row in request.fragments if row.region_id == fragment.region_id}
        chosen = [row for row in peers.values() if row.input_source == "decided_transcript"]
        effective = chosen if len(chosen) == 1 else list(peers.values())
        signatures = {_reading_assertions(row, key, original_reading=original_reading) for row in effective}
        if (len(chosen) > 1 or not chosen and len({row.reader for row in peers.values()}) < 2
            or any(row.unreadable for row in effective)
            or len(signatures) != 1
            or fragment.id in complete_parts and any(
                set(signature) != {complete_parts[fragment.id]} for signature in signatures)
            or (key != FieldKey.FMNH_INS_NUMBER or fragment.id not in complete_parts) and any(
                _compact(fragment.literal) not in _compact(row.observation_text) for row in effective)):
            return _held(key, "conflicting_or_incomplete_collection_readings")
    evidence = tuple(dict.fromkeys(eid for row, _, _ in qualified for eid in row.evidence_ids))
    readings = {part.observation_id: part.observation_text for _, selected, _ in qualified for part in selected}
    routes = {part.observation_id: part.input_source for _, selected, _ in qualified for part in selected}
    return FieldResolution(field_key=key, work_state=WorkState.RESOLVED, value_layer="settled",
        value=FieldValue(state=ValueState.SUPPORTED, literal=assembly.interpreted_text,
            parsed=value, normalized=value, evidence_ids=list(evidence),
            evidence_relations=dict.fromkeys(evidence, "supports"), verbatim_by_observation=readings,
            input_source_by_observation=routes, settled_observation_ids=list(readings),
            reason="Exact qualified collection assertion; no external identity inference"),
        assembly_ids=tuple(row.id for row, _, _ in qualified), event_id=assembly.event_id,
        evidence_ids=evidence, reason=COLLECTION_RULE)


def _held(key, reason):
    return FieldResolution(field_key=key, work_state=WorkState.WAITING_POLICY,
        value=FieldValue(state=ValueState.UNRESOLVED),
        reason="missing_policy:unstructured_label_event_unqualified:" + reason)


def validate_collection_resolution(request, resolution):
    """Require complete qualified evidence and disallow avoidable policy holds."""
    expected = collection_resolution(request, resolution.field_key)
    if resolution.work_state == WorkState.RESOLVED:
        if expected.work_state != WorkState.RESOLVED:
            raise EvidenceError("Collection settlement is unresolved: " + expected.reason)
        target = resolution.value.parsed or resolution.value.normalized or resolution.value.literal
        if (target != expected.value.parsed
            or resolution.value.authority_id is not None
            or resolution.value.authority_identity is not None
            or resolution.value_layer == "derived"
            or resolution.value.layer is not None and resolution.value.layer != resolution.value_layer
            or resolution.value.derived_from
            or resolution.derivation is not None
            or resolution.value.parsed is not None and resolution.value.parsed != expected.value.parsed
            or resolution.value.normalized is not None and resolution.value.normalized != expected.value.normalized
            or resolution.event_id != expected.event_id
            or set(resolution.assembly_ids) != set(expected.assembly_ids)
            or set(resolution.evidence_ids) != set(expected.evidence_ids)
            or set(resolution.value.evidence_ids) != set(expected.evidence_ids)):
            raise EvidenceError("Collection result must cover all exact independent field assertions")
        if resolution.value.literal is not None and resolution.value.literal != expected.value.literal:
            raise EvidenceError("Collection literal differs from exact original assembly")
    elif expected.work_state == WorkState.RESOLVED:
        # Engine/gateway failures are committed outside model acceptance. A
        # model must not discard an available local settlement as an outage.
        raise EvidenceError("Qualified present collection evidence makes this unresolved output avoidable")
