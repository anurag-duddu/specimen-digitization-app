"""People label policy: exact role/span recovery, never a person identity lookup."""
from __future__ import annotations

import re
from dataclasses import dataclass

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.application.organiser import SOURCE, parse_locator
from .contracts import (
    MAX_ORGANISER_LITERAL, EventHypothesis, EventKind, FieldKey, FieldResolution, OrganiserCandidate,
    SourceFragment, WorkState, digest,
)

PEOPLE_RULE = "explicit-people-label/v1"
_ROLES = (
    ("collecting", re.compile(r"^\s*(?:collectors?\s*[:=]|collected\s+by\s*[:=]?|leg\.\s*)\s*", re.I)),
    ("determination", re.compile(r"^\s*(?:det\.|det(?=[:=\s])|determined\b|determiner\b|identified\s+by\b|identification\s+by\b)\s*[:=]?\s*", re.I)),
    ("preparation", re.compile(r"^\s*(?:prep\.|prep(?=[:=\s])|prepared\b|preparer\b|preparation\b|mounted\s+by\b|slide\s+by\b)\s*[:=]?\s*", re.I)),
    ("locality", re.compile(r"^\s*(?:locality|type locality|precise_location|location|country|province(?:_state)?|state|county|city|site)\s*[:=]\s*", re.I)),
)
_NAME = re.compile(r"^[^\W\d_][^\d:={}<>\[\]()/\\!?]*$", re.UNICODE)
_SEPARATOR = re.compile(r"\s*(?:&|;|\band\b)\s*", re.I)
_TRAILING_DATE = re.compile(r",\s*(\d{4}(?:-\d{2}(?:-\d{2})?)?)\s*$")
_LIST_CONTINUATION = re.compile(r"^\s*(?:&|;|,|and\b)", re.I)


@dataclass(frozen=True)
class PersonLabelAssertion:
    observation_id: str
    region_id: str
    role: str
    literal: str
    start: int
    end: int
    line_start: int
    line: str
    order: int
    # Splitting is informational. No initials or surname is expanded to an identity.
    members: tuple[str, ...]


def name_problem(text: str) -> str | None:
    if text.rstrip().endswith(","):
        return "collector_name_list_has_dangling_separator"
    members = _SEPARATOR.split(text)
    if not members or any(not item or not _NAME.fullmatch(item) for item in members):
        return "not_a_person_name_list"
    if any(not re.search(r"[^\W\d_]{2}", item, re.UNICODE) for item in members):
        return "initials_without_a_surname"
    if re.search(r"\b(?:unknown|illegible|unreadable)\b", text, re.I):
        return "unresolved_name_or_role_text"
    if (any(marker.match(item) for item in members for role, marker in _ROLES
        if role in {"determination", "preparation", "locality"})
        or re.search(r"\b(?:det\.?|determiner|determined|identified\s+by|identification\s+by|prep\.?|preparer|prepared|preparation|mounted\s+by|slide\s+by)\s*[:=]?\s+", text, re.I)):
        return "mixed_person_roles_in_one_list"
    return None


def _role_value(line, match, role):
    value = line[match.end():].strip()
    date = _TRAILING_DATE.search(value) if role == "collecting" else None
    if date:
        from .evidence import EvidenceError, parse_temporal
        try:
            parse_temporal(date[1])
        except EvidenceError:
            pass
        else:
            value = value[:date.start()].rstrip()
    return value


def reading_assertions(fragment: SourceFragment) -> tuple[PersonLabelAssertion, ...]:
    """Read the whole immutable observation; never treat an arbitrary substring as a role."""
    assertions, offset = [], 0
    for order, raw in enumerate(fragment.observation_text.splitlines(keepends=True)):
        line = raw.rstrip("\r\n")
        for role, marker in _ROLES:
            match = marker.match(line)
            if match:
                value = _role_value(line, match, role)
                if value:
                    start = offset + match.end() + len(line[match.end():]) - len(line[match.end():].lstrip())
                    assertions.append(PersonLabelAssertion(fragment.observation_id, fragment.region_id,
                        role, value, start, start + len(value), offset, line, order,
                        tuple(_SEPARATOR.split(value))))
                break
        offset += len(raw)
    return tuple(assertions)


def collector_span_problem(text: str, literal: str, start: int, end: int, *, check_name: bool = True) -> str | None:
    """Check explicit role and list completeness at an exact candidate span.

    A supplied accepted collecting event may qualify a bare name. An explicit
    contrary role cannot be overridden by the extractor's field assignment.
    """
    problem = name_problem(literal) if check_name else None
    if problem:
        return problem
    offset = 0
    for raw in text.splitlines(keepends=True):
        line = raw.rstrip("\r\n")
        if offset <= start < end <= offset + len(line):
            following = text[offset + len(raw):].splitlines()
            next_line = next((item for item in following if item.strip()), "")
            if _LIST_CONTINUATION.match(next_line):
                return "collector_list_continues_on_another_line"
            # Exact keyed collector lines are a declared collecting assertion.
            keyed = re.match(r"^\s*collectors\s*:\s*", line, re.I)
            markers = (("collecting", keyed),) if keyed else (
                (role, marker.match(line)) for role, marker in _ROLES)
            for role, match in markers:
                if match:
                    if role != "collecting":
                        return "name_belongs_to_" + role
                    full = _role_value(line, match, role)
                    if full != literal:
                        return "incomplete_collector_list_or_role_span"
                    return None
            if literal != line.strip() and (_SEPARATOR.search(line) or "," in line):
                return "incomplete_unmarked_collector_list"
            return None  # compatibility: the existing accepted event supplies the role
        offset += len(raw)
    return "collector_span_not_on_one_exact_line"


def _effective_readings(readings):
    """Use one trusted decided transcript per label, retaining all raw graph data.

    Raw alternatives still determine eligibility when no transcript was selected.
    A selected reading applies only to its own region; it does not join labels.
    Multiple selected readings provide no deciding authority.
    """
    regions = {}
    for reading in readings:
        regions.setdefault(reading.region_id, []).append(reading)
    effective = []
    for peers in regions.values():
        chosen = [reading for reading in peers if reading.input_source == "decided_transcript"]
        effective.extend(chosen if len(chosen) == 1 else peers)
    return tuple(effective)


def validate_collector_assemblies(request, assemblies) -> None:
    from .evidence import EvidenceError

    by_id = {item.id: item for item in request.fragments}
    readings = {item.observation_id: item for item in request.fragments}
    explicit = [assertion for item in _effective_readings(readings.values()) for assertion in reading_assertions(item)
        if assertion.role == "collecting"]
    selected = {item.interpreted_text for item in assemblies}
    # A contrary effective collector line remains evidence even when omitted by
    # the organiser or present on another label. Unselected raw alternatives
    # remain in the graph; they cannot override that label's decided transcript.
    # No cross-label event join is guessed.
    if any(item.literal not in selected for item in explicit):
        raise EvidenceError("People retained collector assertions disagree or lack an event join")
    for assembly in assemblies:
        if len(assembly.fragment_ids) != 1:
            raise EvidenceError("People multiline collector assembly needs an explicit qualified relation")
        fragment = by_id[assembly.fragment_ids[0]]
        if fragment.unreadable:
            raise EvidenceError("People collector reading has unreadable spans")
        chosen = [item for item in readings.values() if item.region_id == fragment.region_id
                  and item.input_source == "decided_transcript"]
        if len(chosen) > 1 or chosen and chosen[0].observation_id != fragment.observation_id:
            raise EvidenceError("People collector assembly does not cite one decided reading")
        problem = collector_span_problem(fragment.observation_text, assembly.interpreted_text,
            fragment.start, fragment.end)
        if problem:
            raise EvidenceError("People collector role/span unqualified:" + problem)


def _covering_evidence(specimen, fragment, assertion):
    ids = []
    for row in specimen.run.evidence:
        if (row.kind != "literal" or row.asset_id != fragment.asset_id
            or row.region_id != fragment.region_id or fragment.observation_id not in row.observation_ids
            or not row.excerpt or row.excerpt not in fragment.observation_text):
            continue
        location = parse_locator(row.locator)
        if location is not None:
            if (row.source != SOURCE or location.observation_id != fragment.observation_id
                or tuple(row.observation_ids) != (fragment.observation_id,)
                or not 0 <= location.quote_start < location.quote_end <= len(fragment.observation_text)
                or fragment.observation_text[location.quote_start:location.quote_end] != row.excerpt
                or not location.quote_start <= assertion.start < assertion.end <= location.quote_end):
                continue
        elif row.locator != "region:" + fragment.region_id or row.source not in {"label", SOURCE}:
            continue
        # A legacy quote must uniquely locate the assertion; string membership
        # alone cannot attach an identical name on two different lines.
        else:
            if fragment.observation_text.count(row.excerpt) != 1:
                continue
            at = fragment.observation_text.index(row.excerpt)
            if not at <= assertion.start < assertion.end <= at + len(row.excerpt):
                continue
        ids.append(row.id)
    return tuple(ids)


def recover_collectors(specimen, scope, fragments, events, assemblies, candidates):
    """Add only omitted explicit collector spans backed by existing native quotes.

    Located alternatives remain visible when evidence, consensus or semantic
    qualification is missing. No new native evidence row is manufactured.
    """
    from .evidence import assemble_field

    readings = {item.observation_id: item for item in fragments}
    assertions = [(item, assertion) for item in readings.values() for assertion in reading_assertions(item)
        if assertion.role == "collecting"]
    if not assertions:
        return tuple(candidates)
    if any(item.field_key == FieldKey.COLLECTORS for item in assemblies):
        # Existing accepted spans already supply the field. Every alternative
        # remains in the original raw graph and is checked by the validator.
        return tuple(candidates)
    existing = {(item.observation_id, item.start, item.end) for item in candidates if item.field_key == FieldKey.COLLECTORS}
    effective = _effective_readings(readings.values())
    all_names = {assertion.literal for item in effective for assertion in reading_assertions(item)
                 if assertion.role == "collecting"}
    grounded = any(item.field_key == FieldKey.COLLECTORS for item in assemblies)
    added = []
    for original, assertion in assertions:
        span = (original.observation_id, assertion.start, assertion.end)
        if span in existing:
            continue
        if len(assertion.literal) > MAX_ORGANISER_LITERAL:
            added.append(OrganiserCandidate(id="people-oversize:" + digest(span),
                field_key=FieldKey.COLLECTORS, source="people_recovery",
                literal=assertion.literal[:MAX_ORGANISER_LITERAL], status="ungrounded",
                reason="person_name_assertion_exceeds_limit", region_id=original.region_id))
            continue
        peers = [item for item in readings.values() if item.region_id == original.region_id]
        chosen = [item for item in peers if item.input_source == "decided_transcript"]
        peer_assertions = {item.observation_id: [value for value in reading_assertions(item)
            if value.role == "collecting"] for item in peers}
        consensus = (len(chosen) == 1 and chosen[0].observation_id == original.observation_id
            or not chosen and len(peers) >= 2 and all(
                len(values) == 1 and values[0].literal == assertion.literal for values in peer_assertions.values()))
        native_ids = _covering_evidence(specimen, original, assertion)
        problem = collector_span_problem(original.observation_text, assertion.literal, assertion.start, assertion.end)
        reason = (problem or "competing_collector_assertions" if problem or len(all_names) != 1 else
            "reading_has_unreadable_spans" if any(item.unreadable for item in _effective_readings(peers)) else
            "readers_do_not_qualify_collector" if not consensus else
            "native_literal_evidence_unavailable" if not native_ids else
            "collector_assembly_already_available" if grounded else "explicit_collector_role_and_exact_native_quote")
        identity = digest([digest(scope), span, PEOPLE_RULE])
        fields = dict(id="people-candidate:" + identity, field_key=FieldKey.COLLECTORS,
            source="people_recovery", literal=assertion.literal, status="located", reason=reason,
            region_id=original.region_id, observation_id=original.observation_id,
            start=assertion.start, end=assertion.end, evidence_ids=native_ids)
        if reason == "explicit_collector_role_and_exact_native_quote":
            fragment = original.model_copy(update={"id": "people-fragment:" + identity,
                "start": assertion.start, "end": assertion.end, "literal": assertion.literal,
                "order": assertion.order, "granularity": "span"})
            # Standard graph types revalidate the exact immutable span.
            fragment = SourceFragment.model_validate(fragment.model_dump(mode="json"))
            event = EventHypothesis(id="people-event:" + identity, scope=scope,
                kind=EventKind.COLLECTING, fragment_ids=(fragment.id,), evidence_ids=native_ids,
                reason=reason, rule_version=PEOPLE_RULE, status="accepted", validator_version=PEOPLE_RULE)
            assembly = assemble_field(assembly_id="people-assembly:" + identity, scope=scope,
                field_key=FieldKey.COLLECTORS, fragments=(fragment,), event=event)
            fragments.append(fragment)
            events.append(event)
            assemblies.append(assembly)
            fields.update(status="grounded", fragment_id=fragment.id, event_id=event.id, assembly_id=assembly.id)
            grounded = True
        added.append(OrganiserCandidate(**fields))
    from .initial_requests import MAX_CANDIDATES_PER_FIELD
    people = [item for item in candidates if item.field_key == FieldKey.COLLECTORS] + added
    people.sort(key=lambda item: item.status != "grounded")
    if len(people) > MAX_CANDIDATES_PER_FIELD:
        marker = OrganiserCandidate(id="people-overflow:" + digest([item.id for item in people]),
            field_key=FieldKey.COLLECTORS, literal=people[MAX_CANDIDATES_PER_FIELD - 1].literal,
            source="people_recovery", status="ungrounded", reason="more_people_assertions_than_handed_over")
        people = [*people[:MAX_CANDIDATES_PER_FIELD - 1], marker]
    return tuple(item for item in candidates if item.field_key != FieldKey.COLLECTORS) + tuple(people)


def collector_resolution(request, *, assembly_id: str) -> FieldResolution:
    """Exact collector literal and reading lineage; no name expansion or IRN inference."""
    from .evidence import EvidenceError, validate_assembly, validate_resolution

    chosen = next((item for item in request.assemblies if item.id == assembly_id), None)
    if chosen is None or chosen.field_key != FieldKey.COLLECTORS:
        raise EvidenceError("People collector assembly unavailable")
    assemblies = [item for item in request.assemblies if item.field_key == FieldKey.COLLECTORS
        and item.event_id == chosen.event_id]
    for item in assemblies:
        validate_assembly(request, item)
    validate_collector_assemblies(request, assemblies)
    by_id = {item.id: item for item in request.fragments}
    fragments = [by_id[key] for item in assemblies for key in item.fragment_ids]
    evidence_ids = tuple(dict.fromkeys(eid for item in assemblies for eid in item.evidence_ids))
    verbatims = {item.observation_id: item.observation_text for item in fragments}
    routes = {item.observation_id: item.input_source for item in fragments}
    result = FieldResolution(field_key=FieldKey.COLLECTORS, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, literal=chosen.interpreted_text,
            parsed=chosen.interpreted_text, normalized=chosen.interpreted_text,
            verbatim_by_observation=verbatims, settled_observation_ids=list(verbatims),
            input_source_by_observation=routes, evidence_ids=list(evidence_ids),
            evidence_relations=dict.fromkeys(evidence_ids, "supports")),
        assembly_ids=tuple(item.id for item in assemblies), event_id=chosen.event_id,
        evidence_ids=evidence_ids, reason="Exact collecting role and retained person-name spelling")
    return validate_resolution(request, result)
