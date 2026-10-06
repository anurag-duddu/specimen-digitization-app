"""Deterministic fragment assembly, exact units and authority-backed proposal checks."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from datetime import date
from typing import Literal

from pydantic import Field

from specimen_digitization.application.domain import FieldValue, LookupStatus, ValueState

from .contracts import (
    ALL_FIELDS, CollectionProfile, DependencyPin, DerivationRecord, EventHypothesis,
    EventKind, FieldAssemblyCandidate, FieldKey, FieldProfile, FieldResolution,
    FragmentRelation, FrozenRecord, IdentityProof, MeasurementMetadata,
    PolicyException, RelationKind, ResearchScope, SourceCoverageReceipt,
    SourceCoverageState, SourceFragment, SourceResult, SpecialistRequest,
    WorkState, digest,
)

FEET_TO_METRES = Decimal("0.3048")
MEASUREMENT_RULE = "decimal-elevation-v1"
DECIMAL_PRECISION = 80
INVERSE_PRECISION = 34
_NUMBER = r"[+-]?\d{1,40}(?:\.\d{1,20})?"
_UNIT = r"(?:ft|feet|foot)\.?|m\.?|metres?|meters?|'"
_MEASUREMENT = re.compile(
    rf"^\s*(?:(?:elev(?:ation)?|alt(?:itude)?)\.?\s*[:=]?\s*)?"
    rf"(?P<qual>~|≈|c\.?|ca\.?|about|approx\.?)?\s*"
    rf"(?P<first>{_NUMBER})\s*(?P<firstunit>{_UNIT})?\s*"
    rf"(?:(?P<sep>to|[-–—])\s*(?P<last>{_NUMBER})\s*(?P<lastunit>{_UNIT})?)?"
    rf"\s*(?:[±]\s*(?P<uncertainty>{_NUMBER})\s*(?P<uncunit>{_UNIT})?)?\s*$",
    re.IGNORECASE,
)


class EvidenceError(ValueError):
    """A proposal lacks evidence; no model assertion can turn this into clearance."""


class ParsedMeasurement(FrozenRecord):
    literal: str
    from_quantity: str
    to_quantity: str
    from_unit: Literal["ft", "m"]
    to_unit: Literal["ft", "m"]
    single: bool
    qualifiers: tuple[str, ...] = ()
    uncertainty: str | None = None
    precision: str = "unknown"
    vertical_datum: str = "unknown"


class ParsedTemporal(FrozenRecord):
    literal: str
    canonical: str
    precision: Literal["day", "month", "year"]
    century_rule: str | None = None
    rule_version: str = "insects-date-G24-G29-v1"


def parse_temporal(text: str) -> ParsedTemporal:
    """Qualified existing parser plus exact ISO date/precision validation."""
    from specimen_digitization.application.field_validators import date_parser
    if re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", text):
        parts = list(map(int, text.split("-")))
        try:
            date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
        except ValueError as exc:
            raise EvidenceError("Invalid date calendar value") from exc
        if not 1750 <= parts[0] <= date.today().year:
            raise EvidenceError("Date year outside approved plausible range")
        return ParsedTemporal(literal=text, canonical=text, precision=("year", "month", "day")[len(parts) - 1])
    result = date_parser(text, source_text=text,
                         date_rules={"version": "insects-date-G24-G29-v1", "two_digit_year_century": 1900,
                                     "roman_numeral_months": True})
    if result.outcome != LookupStatus.SUCCESS:
        raise EvidenceError("Date has ambiguous readings, preparation notation or unavailable context")
    reading = result.parsed["readings"][0]
    return ParsedTemporal(literal=text, canonical=reading["iso"], precision=reading["precision"],
                          century_rule=reading["century_rule"])


def temporal_resolutions(request: SpecialistRequest, *, event_id: str, source_revision: int = 0) -> tuple[FieldResolution, ...]:
    """Event-scoped written dates and G44 single collecting-date endpoint fill."""
    event = next((item for item in request.events if item.id == event_id), None)
    if event is None or event.kind not in {EventKind.COLLECTING, EventKind.DETERMINATION}:
        raise EvidenceError("Collecting/determination date cannot use preparation or unknown event")
    field = FieldKey.DATE_IDENTIFIED if event.kind == EventKind.DETERMINATION else FieldKey.DATE_VISITED_FROM
    assertions = [item for item in request.assemblies if item.event_id == event_id and item.field_key == field]
    if not assertions:
        raise EvidenceError("No written event-specific date assertion")
    for assembly in assertions:
        validate_assembly(request, assembly)
    parsed = [parse_temporal(item.interpreted_text) for item in assertions]
    if len({(item.canonical, item.precision) for item in parsed}) != 1:
        raise EvidenceError("G32 date assertions disagree")
    first = parsed[0]
    fragments = {item.id: item for item in request.fragments}
    fragment_ids = tuple(dict.fromkeys(key for item in assertions for key in item.fragment_ids))
    evidence_ids = tuple(dict.fromkeys(eid for item in assertions for eid in item.evidence_ids))
    verbatims = {fragments[key].observation_id: fragments[key].observation_text for key in fragment_ids}
    base = FieldResolution(
        field_key=field, work_state=WorkState.RESOLVED, value_layer="settled",
        value=FieldValue(state=ValueState.SUPPORTED, literal=first.literal if len(verbatims) == 1 else None,
                         parsed=first.canonical, normalized=first.canonical, precision=first.precision,
                         century_rule=first.century_rule, verbatim_by_observation=verbatims,
                         settled_observation_ids=list(verbatims), evidence_ids=list(evidence_ids),
                         evidence_relations=dict.fromkeys(evidence_ids, "supports"),
                         reason="Event-scoped deterministic date interpretation"),
        event_id=event_id, assembly_ids=tuple(item.id for item in assertions),
        evidence_ids=evidence_ids, reason="G24/G29 date at written precision",
    )
    if event.kind == EventKind.DETERMINATION:
        return (base,)
    explicit_to = [item for item in request.assemblies if item.event_id == event_id and item.field_key == FieldKey.DATE_VISITED_TO]
    if explicit_to:
        for assembly in explicit_to:
            validate_assembly(request, assembly)
        to_readings = [parse_temporal(item.interpreted_text) for item in explicit_to]
        if len({(item.canonical, item.precision) for item in to_readings}) != 1:
            raise EvidenceError("G32 range endpoint assertions disagree")
        last = to_readings[0]
        if last.canonical < first.canonical:
            raise EvidenceError("Collecting date range endpoints are reversed")
        end_evidence = tuple(dict.fromkeys(eid for item in explicit_to for eid in item.evidence_ids))
        end = FieldResolution(
            field_key=FieldKey.DATE_VISITED_TO, work_state=WorkState.RESOLVED, value_layer="settled",
            value=FieldValue(state=ValueState.SUPPORTED, literal=last.literal, parsed=last.canonical,
                             normalized=last.canonical, precision=last.precision, century_rule=last.century_rule,
                             evidence_ids=list(end_evidence),
                             evidence_relations=dict.fromkeys(end_evidence, "supports"),
                             reason="Written collecting range endpoint"),
            evidence_ids=end_evidence, assembly_ids=tuple(item.id for item in explicit_to), event_id=event_id,
            reason="Preserved written range endpoint",
        )
        return (base, end)
    base_digest = digest(base)
    scientific_digest = digest({"canonical": first.canonical, "precision": first.precision,
                                "event_id": event_id, "assembly_ids": base.assembly_ids,
                                "evidence_ids": evidence_ids})
    derivation = DerivationRecord(
        rule_id="G44", rule_version="single-collecting-date-v1", operation="copy_endpoint",
        source_field=FieldKey.DATE_VISITED_FROM, source_revision=source_revision, source_digest=scientific_digest,
        source_value=first.canonical, exact_operation=f"copy({first.canonical})", unrounded_value=first.canonical,
        display_value=first.canonical, source_assembly_ids=base.assembly_ids,
        source_fragment_ids=fragment_ids, evidence_ids=evidence_ids,
    )
    end = FieldResolution(
        field_key=FieldKey.DATE_VISITED_TO, work_state=WorkState.RESOLVED, value_layer="derived",
        value=base.value.model_copy(update={"literal": None, "reason": "G44 copy of settled collecting date"}),
        event_id=event_id, assembly_ids=base.assembly_ids, evidence_ids=evidence_ids,
        dependencies=(DependencyPin(field_key=FieldKey.DATE_VISITED_FROM, revision=source_revision, digest=base_digest),),
        derivation=derivation, reason="G44 single collecting date fills To as derived",
    )
    return (base, end)


class SettledMeasurement(FrozenRecord):
    scope: ResearchScope
    event_id: str
    assertions: tuple[ParsedMeasurement, ...]
    assembly_ids: tuple[str, ...]
    fragment_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    fragments: tuple[SourceFragment, ...]
    source_revision: int = Field(strict=True, ge=0)


def _decimal(text: str) -> Decimal:
    if not re.fullmatch(_NUMBER, text):
        raise EvidenceError("Quantity requires bounded unambiguous decimal text")
    number = Decimal(text)
    if not number.is_finite():
        raise EvidenceError("Nonfinite quantity")
    return number


def _unit(text: str | None) -> Literal["ft", "m"] | None:
    if text is None:
        return None
    return "ft" if text.casefold().rstrip(".") in {"ft", "feet", "foot", "'"} else "m"


def parse_measurement(text: str, *, vertical_datum: str = "unknown", precision: str = "unknown") -> ParsedMeasurement:
    """Parse signed single/range assertions. Missing units and mt stay ambiguous."""
    if len(text) > 300:
        raise EvidenceError("Measurement input exceeds bounded parser")
    match = _MEASUREMENT.fullmatch(text.replace("\n", " "))
    if match is None:
        raise EvidenceError("Ambiguous elevation notation, sign, separators or units")
    groups = match.groupdict()
    first_unit, last_unit = _unit(groups["firstunit"]), _unit(groups["lastunit"])
    if first_unit is None and last_unit is None and groups["uncertainty"] is not None:
        first_unit = _unit(groups["uncunit"])
    if groups["last"] is None:
        if first_unit is None:
            raise EvidenceError("Written elevation unit is required")
        last_unit = first_unit
    else:
        # A trailing unit applies to both endpoints of a written range.
        first_unit = first_unit or last_unit
        last_unit = last_unit or first_unit
        if first_unit is None or last_unit is None:
            raise EvidenceError("Written elevation range units are required")
    first = _decimal(groups["first"])
    last = _decimal(groups["last"] or groups["first"])
    if _metres(first, first_unit) > _metres(last, last_unit):
        raise EvidenceError("Elevation endpoints reversed; sign is not range punctuation")
    uncertainty = groups["uncertainty"]
    if uncertainty is not None:
        if _decimal(uncertainty) < 0:
            raise EvidenceError("Uncertainty cannot be negative")
        if _unit(groups["uncunit"]) not in {None, first_unit} or first_unit != last_unit:
            raise EvidenceError("Uncertainty unit applicability is ambiguous")
    return ParsedMeasurement(
        literal=text, from_quantity=str(first), to_quantity=str(last),
        from_unit=first_unit, to_unit=last_unit, single=groups["last"] is None,
        qualifiers=(groups["qual"],) if groups["qual"] else (),
        uncertainty=uncertainty, precision=precision, vertical_datum=vertical_datum,
    )


def _metres(number: Decimal, unit: str) -> Decimal:
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return number * FEET_TO_METRES if unit == "ft" else number


def _convert(number: Decimal, source_unit: str, target_unit: str) -> Decimal:
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION if source_unit == "ft" else INVERSE_PRECISION
        context.rounding = ROUND_HALF_EVEN
        if source_unit == target_unit:
            return number
        return number * FEET_TO_METRES if target_unit == "m" else number / FEET_TO_METRES


def display_decimal(number: Decimal) -> str:
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return format(number.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN), "f")


def assemble_field(
    *, assembly_id: str, scope: ResearchScope, field_key: FieldKey,
    fragments: Sequence[SourceFragment], event: EventHypothesis,
    relations: Sequence[FragmentRelation] = (),
    assertion_kind: Literal["complete", "complementary"] = "complete",
) -> FieldAssemblyCandidate:
    """Join only evidenced complementary fragments, never overwrite raw readings."""
    if not fragments or len({item.id for item in fragments}) != len(fragments):
        raise EvidenceError("Assembly needs distinct available fragments")
    if event.scope != scope or any(item.scope != scope for item in fragments):
        raise EvidenceError("Assembly cannot combine different specimens/generations")
    if event.status != "accepted" or not event.validator_version:
        raise EvidenceError("Proposed/unknown event cannot authorize field settlement")
    ids = tuple(item.id for item in fragments)
    if not set(ids) <= set(event.fragment_ids):
        raise EvidenceError("Assembly fragments do not belong to evidenced event")
    if len(fragments) > 1:
        if assertion_kind != "complementary":
            raise EvidenceError("Multiple fragments require a continuation assembly")
        available = set(ids)
        connected = {ids[0]}
        admissible = []
        for relation in relations:
            if (relation.scope == scope and relation.status == "accepted"
                and relation.kind == RelationKind.CONTINUATION and relation.event_id == event.id
                and set(relation.fragment_ids) <= available):
                admissible.append(relation)
        changed = True
        while changed:
            before = len(connected)
            for relation in admissible:
                if connected & set(relation.fragment_ids):
                    connected.update(relation.fragment_ids)
            changed = len(connected) != before
        if connected != available:
            raise EvidenceError("No validated continuation connects these fragments")
    else:
        admissible = []
    evidence_ids = tuple(dict.fromkeys((*event.evidence_ids, *(eid for r in admissible for eid in r.evidence_ids))))
    return FieldAssemblyCandidate(
        id=assembly_id, scope=scope, field_key=field_key, event_id=event.id,
        fragment_ids=ids, relation_ids=tuple(r.id for r in admissible),
        assertion_kind=assertion_kind,
        interpreted_text=" ".join(item.literal for item in fragments),
        rule_version="fragment-assembly-v1", evidence_ids=evidence_ids,
    )


def validate_assembly(request: SpecialistRequest, assembly: FieldAssemblyCandidate) -> None:
    fragments = {item.id: item for item in request.fragments}
    events = {item.id: item for item in request.events}
    relations = {item.id: item for item in request.relations}
    try:
        reconstructed = assemble_field(
            assembly_id=assembly.id, scope=request.scope, field_key=assembly.field_key,
            fragments=tuple(fragments[key] for key in assembly.fragment_ids),
            event=events[assembly.event_id], relations=tuple(relations[key] for key in assembly.relation_ids),
            assertion_kind=assembly.assertion_kind,
        )
    except KeyError as exc:
        raise EvidenceError("Assembly references unavailable evidence graph record") from exc
    if reconstructed != assembly:
        raise EvidenceError("Assembly differs from deterministic validated fragments")


def settle_elevation(
    request: SpecialistRequest, *, assembly_ids: Sequence[str], source_revision: int = 0,
) -> SettledMeasurement:
    """Settle independent complete assertions by event and exact canonical quantity."""
    selected = {item.id: item for item in request.assemblies}
    try:
        assemblies = tuple(selected[key] for key in assembly_ids)
    except KeyError as exc:
        raise EvidenceError("Unknown measurement assembly") from exc
    if not assemblies or len({item.id for item in assemblies}) != len(assemblies):
        raise EvidenceError("Distinct measurement assertions are required")
    if len({item.event_id for item in assemblies}) != 1:
        raise EvidenceError("Measurements from different events cannot combine")
    event_id = assemblies[0].event_id
    relevant = {item.id for item in request.assemblies
                if item.event_id == event_id and str(item.field_key).startswith("elevation_")}
    if relevant != set(assembly_ids):
        raise EvidenceError("G32 requires every available complete assertion for this event")
    assertions = []
    canonical = None
    for assembly in assemblies:
        if not str(assembly.field_key).startswith("elevation_"):
            raise EvidenceError("Non-measurement assembly cannot supply elevation")
        validate_assembly(request, assembly)
        value = parse_measurement(assembly.interpreted_text)
        identity = (_metres(_decimal(value.from_quantity), value.from_unit),
                    _metres(_decimal(value.to_quantity), value.to_unit))
        if canonical is not None and identity != canonical:
            raise EvidenceError("G32 independent complete elevations disagree")
        canonical = identity
        assertions.append(value)
    fragment_ids = tuple(dict.fromkeys(key for item in assemblies for key in item.fragment_ids))
    fragments = {item.id: item for item in request.fragments}
    return SettledMeasurement(
        scope=request.scope, event_id=event_id, assertions=tuple(assertions),
        assembly_ids=tuple(assembly_ids), fragment_ids=fragment_ids,
        evidence_ids=tuple(dict.fromkeys(eid for item in assemblies for eid in item.evidence_ids)),
        fragments=tuple(fragments[key] for key in fragment_ids), source_revision=source_revision,
    )


def elevation_resolutions(settled: SettledMeasurement) -> tuple[FieldResolution, ...]:
    """All four endpoints derive from agreed settled quantities, even without literal."""
    first = settled.assertions[0]
    # Scientific input identity is stable when the accepted source checkpoint's
    # revision is assigned/rebased by the atomic writer.
    source_digest = digest(settled.model_dump(mode="json", exclude={"source_revision"}))
    verbatims: dict[str, str] = {}
    for fragment in settled.fragments:
        # Preserve the immutable whole source observation when fragments split lines.
        verbatims[fragment.observation_id] = fragment.observation_text
    results = []
    for key, endpoint, target_unit in (
        (FieldKey.ELEVATION_FROM_M, "from", "m"), (FieldKey.ELEVATION_TO_M, "to", "m"),
        (FieldKey.ELEVATION_FROM_FT, "from", "ft"), (FieldKey.ELEVATION_TO_FT, "to", "ft"),
    ):
        written = [assertion for assertion in settled.assertions
                   if (assertion.from_unit if endpoint == "from" else assertion.to_unit) == target_unit
                   and (endpoint == "from" or not assertion.single)]
        source_quantity = first.from_quantity if endpoint == "from" else first.to_quantity
        source_unit = first.from_unit if endpoint == "from" else first.to_unit
        source_endpoint = "from" if first.single else endpoint
        source_key = FieldKey(f"elevation_{source_endpoint}_{source_unit}")
        # For a single quantity explicitly stated in both units, copy each
        # written unit's own settled From endpoint instead of overwriting it.
        if endpoint == "to" and first.single:
            native = next((item for item in settled.assertions if item.from_unit == target_unit), None)
            if native is not None:
                source_quantity, source_unit = native.from_quantity, native.from_unit
                source_key = FieldKey(f"elevation_from_{source_unit}")
        if written:
            assertion = written[0]
            unrounded = assertion.from_quantity if endpoint == "from" else assertion.to_quantity
            derivation = None
            layer = "settled"
        else:
            converted = _convert(_decimal(source_quantity), source_unit, target_unit)
            unrounded = str(converted)
            operation = "copy_endpoint" if source_unit == target_unit else "multiply" if target_unit == "m" else "divide"
            factor = "1" if operation == "copy_endpoint" else "0.3048"
            symbol = {"copy_endpoint": "*", "multiply": "*", "divide": "/"}[operation]
            derivation = DerivationRecord(
                rule_id="G41", rule_version=MEASUREMENT_RULE, operation=operation,
                source_field=source_key, source_revision=settled.source_revision,
                source_digest=source_digest, source_value=source_quantity, factor=factor,
                decimal_precision=DECIMAL_PRECISION if source_unit == "ft" else INVERSE_PRECISION,
                exact_operation=f"{source_quantity} {symbol} {factor}", unrounded_value=unrounded,
                display_value=display_decimal(converted), source_assembly_ids=settled.assembly_ids,
                source_fragment_ids=settled.fragment_ids, evidence_ids=settled.evidence_ids,
            )
            layer = "derived"
        value = FieldValue(
            state=ValueState.SUPPORTED,
            literal=first.literal if len(verbatims) == 1 and len(settled.fragment_ids) == 1 and written else None,
            parsed=unrounded, normalized=display_decimal(Decimal(unrounded)),
            evidence_ids=list(settled.evidence_ids),
            evidence_relations=dict.fromkeys(settled.evidence_ids, "supports"),
            verbatim_by_observation=verbatims,
            settled_observation_ids=list(verbatims),
            input_source_by_observation={item.observation_id: item.input_source for item in settled.fragments},
            reason="Validated same-event written assertion" if written else "G41 exact derivation from settled quantity",
        )
        metadata = MeasurementMetadata(
            original_unit=first.from_unit, original_quantity=first.from_quantity,
            original_to_quantity=first.to_quantity if not first.single else None,
            qualifiers=first.qualifiers, uncertainty=first.uncertainty,
            precision=first.precision, vertical_datum=first.vertical_datum,
            decimal_context=DECIMAL_PRECISION if source_unit == "ft" else INVERSE_PRECISION,
            derived_unit=target_unit,
            converted_uncertainty=str(_convert(_decimal(first.uncertainty), first.from_unit, target_unit)) if first.uncertainty is not None else None,
            assertion_metadata=tuple(json.dumps(item.model_dump(mode="json"), sort_keys=True, separators=(",", ":")) for item in settled.assertions),
        )
        results.append(FieldResolution(
            field_key=key, work_state=WorkState.RESOLVED, value=value, value_layer=layer,
            evidence_ids=settled.evidence_ids, assembly_ids=settled.assembly_ids,
            event_id=settled.event_id, derivation=derivation, measurement=metadata,
            dependencies=(),
            reason=value.reason,
        ))
    source_values = {item.field_key: item for item in results if item.derivation is None}
    rebound = []
    for result in results:
        if result.derivation is None:
            rebound.append(result)
            continue
        source_key = result.derivation.source_field
        source = source_values.get(source_key)
        if source is None:
            raise EvidenceError("Derivation must consume an actual written settled source field")
        rebound.append(result.model_copy(update={"dependencies": (
            DependencyPin(field_key=source_key, revision=settled.source_revision, digest=digest(source)),
        )}))
    return tuple(rebound)


def emu_irn_exception() -> PolicyException:
    return PolicyException(
        field_key=FieldKey.IDENTIFIED_BY_IRN, dependency="qualified_emu_determiner_eparties_identity",
        policy_version="owner-2026-09-29-irn-nonblocking-v1",
        reason="EMu DB identity/record access unavailable; no verified determiner Parties IRN",
        reevaluate_when="Qualified read-only EMu connection and specimen determination join become available",
    )


def missing_irn_resolution() -> FieldResolution:
    return FieldResolution(
        field_key=FieldKey.IDENTIFIED_BY_IRN, work_state=WorkState.NONBLOCKING_EXCEPTION,
        value=FieldValue(state=ValueState.UNKNOWN, reason="No qualified determiner Parties identity"),
        exception=emu_irn_exception(), reason="Confirmed owner field-scoped EMu identity exception",
    )


def dts_policy_resolution(verbatim: str | None, evidence_ids: Sequence[str] = ()) -> FieldResolution:
    return FieldResolution(
        field_key=FieldKey.VERBATIM_DTS, work_state=WorkState.WAITING_POLICY,
        value=FieldValue(state=ValueState.UNRESOLVED, literal=verbatim, evidence_ids=list(evidence_ids),
                         reason="D/T/S definition and examples not supplied"),
        evidence_ids=tuple(evidence_ids), reason="missing_policy:verbatim_dts_definition_examples",
    )


def insects_profile(organization_id: str, collection_id: str, *, ancestry: Sequence[str] = (), overrides: Sequence[FieldProfile] = ()) -> CollectionProfile:
    """Resolve explicit per-field child overrides while retaining all twenty fields."""
    taxonomy = ("global_names_verifier", "catalogue_of_life", "gbif", "bugguide")
    geography = ("mapcarta", "google_maps", "geolocate")
    fields = {}
    for key in ALL_FIELDS:
        sources = taxonomy if key == FieldKey.TAXON else geography if key in {
            FieldKey.COUNTRY, FieldKey.PROVINCE_STATE, FieldKey.COUNTY, FieldKey.CITY, FieldKey.PRECISE_LOCATION
        } else ("field_museum_ipt", "field_museum_emudata")
        fields[key] = FieldProfile(field_key=key, source_ids=sources,
                                   exception=emu_irn_exception() if key == FieldKey.IDENTIFIED_BY_IRN else None,
                                   missing_policy="verbatim_dts_definition_examples" if key == FieldKey.VERBATIM_DTS else None)
    if len({item.field_key for item in overrides}) != len(overrides):
        raise EvidenceError("Duplicate child field override")
    for item in overrides:
        fields[item.field_key] = item
    return CollectionProfile(
        id=f"{collection_id}:insects", version="insects-research-v1", organization_id=organization_id,
        collection_id=collection_id, ancestry=tuple(ancestry), fields=tuple(fields.values()),
        knowledge_version="insects-knowledge-G23-G45-v1",
    )


def validate_party_assignment(proof: IdentityProof, scope: ResearchScope) -> int:
    if (proof.scope != scope or proof.identity.module != "eparties"
        or proof.relationship != "determiner" or not proof.identification_row_id):
        raise EvidenceError("IRN requires scoped determiner eparties relationship proof")
    return proof.identity.irn


def catalog_literal(text: str) -> str:
    match = re.fullmatch(r"\s*(?:FMNH\s*[- ]?\s*INS\s*[#:]?\s*)?(\d{5,9})\s*", text, re.IGNORECASE)
    if not match:
        raise EvidenceError("Catalog notation does not establish EMu identity")
    return match[1]


def _candidate_matches(resolution: FieldResolution, candidate: dict) -> bool:
    target = resolution.value.parsed or resolution.value.normalized
    return (candidate.get("field_key") == str(resolution.field_key)
            and candidate.get("value") == target
            and candidate.get("authority_id") == resolution.value.authority_id
            and (candidate.get("event_id") in {None, resolution.event_id}))


def _taxon_assertions(request: SpecialistRequest, resolution: FieldResolution):
    """Bind complete names to field assertions and their retained reader counterparts.

    A title-case word elsewhere on a label is not a taxon assertion. Explicit
    taxon assemblies/spans, or the declared producer's complete name line,
    establish its location. Other readings of that same line must then be
    reconciled; an omitted/shifted/partial counterpart cannot clear the field.
    """
    from specimen_digitization.application.lookup import scientific_name

    def complete(text):
        name = scientific_name(text)
        # The existing parser retains morphology/annotation in the assertion,
        # while qualifying only its written scientific name for lookup. A
        # genus-only query cannot stand in for a complete species assertion.
        return name.query if name and name.genus and name.partly_read is None else None

    def name_fragment(item):
        start = item.observation_text.rfind("\n", 0, item.start) + 1
        prefix = item.observation_text[start:item.start].strip().rstrip(":").strip()
        if prefix in {str(key) for key in ALL_FIELDS if key != FieldKey.TAXON}:
            return False
        return complete(item.literal)

    fragments = {item.id:item for item in request.fragments}
    assertions, anchors, qualified, assembled = set(), [], {}, []
    def add(text, items):
        assertions.add(text)
        for item in items:
            anchors.append(item)
            qualified.setdefault((item.region_id, item.observation_id, item.order), set()).add(text)
    for assembly in request.assemblies:
        if assembly.field_key != FieldKey.TAXON:
            continue
        validate_assembly(request, assembly)
        if not complete(assembly.interpreted_text):
            raise EvidenceError("G32 taxon assertion is not a complete scientific name")
        parts = [fragments[key] for key in assembly.fragment_ids]
        # The validated assembly is one complete assertion. Its genus/epithet
        # word spans never become independent names or extra source queries.
        leads = [min((item for item in parts if item.observation_id == observation), key=lambda item:item.start)
            for observation in dict.fromkeys(item.observation_id for item in parts)]
        add(assembly.interpreted_text, leads)
        assembled.append((assembly.interpreted_text, parts, leads))
    for candidate in request.organiser_candidates:
        if candidate.field_key != FieldKey.TAXON or candidate.status == "ungrounded":
            continue
        if not complete(candidate.literal):
            raise EvidenceError("G32 located taxon assertion is not a complete scientific name")
        add(candidate.literal, [item for item in request.fragments if
            item.observation_id == candidate.observation_id and item.region_id == candidate.region_id
            and item.start <= candidate.start < candidate.end <= item.end])
    value = resolution.value
    if value.source_observation_id is not None:
        declared = [item for item in request.fragments if
            item.observation_id == value.source_observation_id
            and item.region_id == value.source_region_id
            and item.input_source == value.input_source
            and value.verbatim_by_observation.get(item.observation_id) in {item.literal, item.observation_text}
            and not item.unreadable]
        producer = [(item.literal, [item]) for item in declared if name_fragment(item)]
        producer.extend((text, leads) for text, parts, leads in assembled if
            any(item in declared for item in parts) and all(not item.unreadable
                and (item.observation_id != value.source_observation_id or item in declared) for item in parts))
        # A producer may contain locality and an order as well as the genus.
        # Only the complete assertion actually queried supplies its anchor.
        if not producer:
            raise EvidenceError("G32 taxon deciding query lacks an exact declared reading")
        return assertions, anchors, producer, name_fragment, complete, qualified
    if not anchors:
        raise EvidenceError("G32 taxon deciding query lacks an explicit field assertion")
    return assertions, anchors, [], name_fragment, complete, qualified


def _validate_taxon_inputs(request, resolution, matching):
    deciding = [(result, candidate) for result, candidate in matching
        if result.coverage.source_id == "gbif" and candidate.get("authority_role") == "decides"]
    assertions, anchors, producer, name_fragment, complete, qualified = _taxon_assertions(request, resolution)
    queries = {candidate.get("input_literal") for _, candidate in deciding}
    if producer:
        producer = [(text, leads) for text, leads in producer if text in queries or complete(text) in queries]
        if not producer:
            raise EvidenceError("G32 taxon deciding query differs from its declared reading")
        assertions.update(text for text, _ in producer)
        anchors.extend(item for _, leads in producer for item in leads)
    for anchor in anchors:
        # The factory's line ordinal is relative to its immutable observation.
        # Explicit spans still name the containing line; never search unrelated
        # capitalized words or reinterpret locality as taxonomic evidence.
        readings = {item.observation_id for item in request.fragments if item.region_id == anchor.region_id}
        for observation in readings:
            explicit = qualified.get((anchor.region_id, observation, anchor.order))
            if explicit:
                assertions.update(explicit)
                continue
            counterparts = [item for item in request.fragments if
                item.region_id == anchor.region_id and item.observation_id == observation
                and item.order == anchor.order and item.granularity == "line"]
            if observation == anchor.observation_id:
                continue
            # A span/assembled fixture can lack line nodes. An exactly matching
            # complete span is sufficient; a different unqualified span is not.
            if not counterparts:
                counterparts = [item for item in request.fragments if
                    item.region_id == anchor.region_id and item.observation_id == observation
                    and item.order == anchor.order and item.literal in assertions]
            if len(counterparts) != 1 or counterparts[0].unreadable or not name_fragment(counterparts[0]):
                raise EvidenceError("G32 taxon reader counterpart is not a complete qualified assertion")
            if counterparts[0].literal != anchor.literal:
                # An ordinal alone cannot designate a taxon after reader lines
                # move. Without an explicit field span, the other complete-name
                # lines must retain their exact order/text. Their words supply
                # alignment custody only; they are never added as taxon values.
                def context(observation_id):
                    return tuple(item.literal for item in request.fragments if
                        item.region_id == anchor.region_id and item.observation_id == observation_id
                        and item.granularity == "line" and item.order != anchor.order
                        and name_fragment(item))
                if context(anchor.observation_id) != context(observation):
                    raise EvidenceError("G32 taxon reader alignment is not independently qualified")
            assertions.add(counterparts[0].literal)
    qualified_queries = {text for literal in assertions for text in (literal, complete(literal)) if text}
    if not queries or not queries <= qualified_queries:
        raise EvidenceError("G32 taxon deciding query is not an exact grounded assertion")
    for literal in assertions:
        if not any(candidate.get("input_literal") in {literal, complete(literal)} for _, candidate in deciding):
            raise EvidenceError("G32 each independent taxon assertion needs its own deciding source settlement")


def validate_resolution(request: SpecialistRequest, resolution: FieldResolution, tool_results: Sequence[SourceResult] = ()) -> FieldResolution:
    """Reject false model clearances using only actual broker outputs and immutable inputs."""
    if resolution.field_key not in request.field_keys:
        raise EvidenceError("Specialist output escaped requested fields")
    if resolution.work_state == WorkState.NONBLOCKING_EXCEPTION:
        if resolution.field_key != FieldKey.IDENTIFIED_BY_IRN or resolution.exception != emu_irn_exception():
            raise EvidenceError("Only explicitly declared inaccessible IRN exception is enabled")
        if any(item.status == LookupStatus.SUCCESS and any(
            json.loads(candidate).get("field_key") == "identified_by_irn" for candidate in item.candidate_json
        ) for item in tool_results):
            raise EvidenceError("Available proven IRN cannot be hidden behind unavailable exception")
        return resolution
    if resolution.field_key == FieldKey.VERBATIM_DTS:
        if resolution.work_state != WorkState.WAITING_POLICY:
            raise EvidenceError("D/T/S semantics remain waiting-policy until definition supplied")
        if resolution.value.literal is not None and not any(
            resolution.value.literal in fragment.observation_text for fragment in request.fragments
        ):
            raise EvidenceError("D/T/S verbatim is not grounded in immutable reading")
        return resolution
    if resolution.work_state != WorkState.RESOLVED:
        if resolution.work_state == WorkState.WAITING_HUMAN:
            claimed = resolution.question.coverage if resolution.question else ()
            actual = []
            for item in tool_results:
                if item.coverage.field_key != resolution.field_key:
                    continue
                if (item.receipt is None or item.receipt.scope != request.scope
                    or item.receipt.effect_status != "completed"
                    or item.receipt.field_keys != (resolution.field_key,)):
                    raise EvidenceError("Human source coverage lacks exact scoped completed receipt")
                from .sources import result_envelope
                if item.receipt.result_json != result_envelope(item):
                    raise EvidenceError("Human source coverage differs from captured semantic receipt")
                actual.append(item.coverage)
            if not claimed or any(item not in actual for item in claimed):
                raise EvidenceError("Human question claims source exhaustion without actual tool receipts")
            if resolution.question and resolution.question.reason == "derived_proposal":
                matches = [item for item in tool_results if item.coverage == claimed[0]
                    and item.status == LookupStatus.SUCCESS
                    and item.coverage.source_id == "georeference_spatial"
                    and item.coverage.reason == "computed_proposal"]
                if len(matches) != 1 or len(matches[0].candidate_json) != 1:
                    raise EvidenceError("Derived review lacks one retained successful proposal")
                result = matches[0]
                try:
                    candidate = json.loads(result.candidate_json[0])
                except (ValueError, TypeError):
                    raise EvidenceError("Derived proposal candidate is malformed") from None
                if (candidate.get("field_key") != str(resolution.field_key)
                    or candidate.get("value_layer") != "derived"
                    or candidate.get("human_review_required") is not True
                    or candidate.get("automatic_settlement_allowed") is not False
                    or not candidate.get("value")
                    or not any(item.kind == "computed_derivation_result"
                        and item.source_id == "georeference_spatial"
                        and item.id in candidate.get("evidence_ids", ())
                        and item.id in resolution.question.evidence_ids
                        for item in result.evidence)):
                    raise EvidenceError("Derived review candidate is not a captured human proposal")
                return resolution
            if any(item.status == LookupStatus.SUCCESS and any(
                json.loads(candidate).get("field_key") == str(resolution.field_key) for candidate in item.candidate_json
            ) for item in tool_results):
                raise EvidenceError("Available connected source makes this human review avoidable")
        return resolution
    target_text = resolution.value.parsed or resolution.value.normalized or resolution.value.literal or ""
    if resolution.field_key == FieldKey.COLLECTORS and (
        re.search(r"\d", target_text) or not re.search(r"[^\W\d_]{2}", target_text, re.UNICODE)
    ):
        raise EvidenceError("G45 preparation/code token cannot be collector")
    if str(resolution.field_key).startswith("elevation_"):
        settled = settle_elevation(request, assembly_ids=resolution.assembly_ids,
                                  source_revision=resolution.derivation.source_revision if resolution.derivation else 0)
        expected = next(item for item in elevation_resolutions(settled) if item.field_key == resolution.field_key)
        if resolution != expected:
            raise EvidenceError("Measurement result differs from exact deterministic settlement")
        return resolution
    if str(resolution.field_key).startswith("date_") and resolution.assembly_ids and resolution.event_id:
        expected_dates = temporal_resolutions(request, event_id=resolution.event_id,
                                             source_revision=resolution.derivation.source_revision if resolution.derivation else 0)
        expected = next((item for item in expected_dates if item.field_key == resolution.field_key), None)
        if expected != resolution:
            raise EvidenceError("Date proposal differs from deterministic event/precision derivation")
        return resolution
    authoritative = []
    for result in tool_results:
        if result.status != LookupStatus.SUCCESS or result.receipt is None:
            continue
        if result.receipt.scope != request.scope or result.receipt.effect_status != "completed":
            raise EvidenceError("Tool receipt scope/effect is not trusted complete evidence")
        serialized = json.dumps({"candidate_json": result.candidate_json,
                                 "evidence": [item.model_dump(mode="json") for item in result.evidence],
                                 "coverage": result.coverage.model_dump(mode="json"),
                                 "status": str(result.status)}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if result.receipt.result_json != serialized:
            raise EvidenceError("Semantic source result differs from immutable captured receipt")
        if result.coverage.field_key == resolution.field_key:
            authoritative.extend((result, json.loads(item)) for item in result.candidate_json)
    if authoritative:
        if not any(_candidate_matches(resolution, candidate) for _, candidate in authoritative):
            raise EvidenceError("Value is not one of the trusted source-supported candidates")
        matching = [(result, candidate) for result, candidate in authoritative if _candidate_matches(resolution, candidate)]
        exact_evidence = {item.id for result, _ in matching for item in result.evidence}
        if set(resolution.evidence_ids) != exact_evidence:
            raise EvidenceError("Proposal must cite exact source/field candidate receipt evidence")
        if set(resolution.value.evidence_ids) != exact_evidence:
            raise EvidenceError("Legacy value evidence differs from deciding source receipt")
        if resolution.field_key == FieldKey.TAXON and not any(
            result.coverage.source_id == "gbif" and candidate.get("authority_role") == "decides" for result, candidate in matching
        ):
            raise EvidenceError("G23 taxonomy requires qualified GBIF deciding assertion")
        if resolution.field_key == FieldKey.TAXON:
            _validate_taxon_inputs(request, resolution, matching)
        if resolution.field_key == FieldKey.DATE_IDENTIFIED and not any(
            result.coverage.exact_join_proven and candidate.get("event_kind") == "determination"
            and candidate.get("precision") == resolution.value.precision
            and candidate.get("event_id") == resolution.event_id and resolution.event_id is not None
            for result, candidate in matching
        ):
            raise EvidenceError("Determination date requires exact joined determination/precision evidence")
        if resolution.field_key == FieldKey.COLLECTORS and not any(
            result.coverage.exact_join_proven and candidate.get("event_kind") == "collecting"
            and candidate.get("event_id") == resolution.event_id and resolution.event_id is not None
            for result, candidate in matching
        ):
            raise EvidenceError("Collectors require exact joined collecting-event source relationship")
        if resolution.field_key == FieldKey.IDENTIFIED_BY_IRN and not any(
            candidate.get("module") == "eparties" and candidate.get("relationship") == "determiner"
            and candidate.get("identification_row_id") for _, candidate in matching
        ):
            raise EvidenceError("Person IRN needs explicit determiner module relationship")
        return resolution
    # No available source authority: only explicitly transcribed collection/party fields
    # and event-qualified dates may be validated from a complete literal assembly.
    literal_fields = {FieldKey.FMNH_INS_NUMBER, FieldKey.COLLECTION_CODE, FieldKey.HABITAT,
                      FieldKey.COLLECTION_METHOD, FieldKey.COLLECTORS, FieldKey.PRECISE_LOCATION,
                      FieldKey.DATE_VISITED_FROM, FieldKey.DATE_VISITED_TO, FieldKey.DATE_IDENTIFIED}
    if resolution.field_key not in literal_fields or not resolution.assembly_ids:
        raise EvidenceError("Supported proposal lacks qualified deciding authority")
    assemblies = {item.id: item for item in request.assemblies}
    accepted = []
    for key in resolution.assembly_ids:
        if key not in assemblies:
            raise EvidenceError("Unknown literal assembly")
        assembly = assemblies[key]
        validate_assembly(request, assembly)
        if assembly.field_key != resolution.field_key or assembly.event_id != resolution.event_id:
            raise EvidenceError("Literal assembly belongs to another field/event")
        accepted.append(assembly)
    relevant = [item for item in request.assemblies if item.field_key == resolution.field_key and item.event_id == resolution.event_id]
    if {item.id for item in accepted} != {item.id for item in relevant}:
        raise EvidenceError("G32 omitted complete independent field assertions")
    values = {item.interpreted_text for item in accepted}
    if len(values) != 1:
        raise EvidenceError("G32 literal assertions disagree without source settlement")
    written = values.pop()
    target = resolution.value.parsed or resolution.value.normalized or resolution.value.literal
    if resolution.field_key == FieldKey.FMNH_INS_NUMBER:
        written = catalog_literal(written)
    if str(resolution.field_key).startswith("date_"):
        event = next((item for item in request.events if item.id == resolution.event_id), None)
        expected_kind = EventKind.DETERMINATION if resolution.field_key == FieldKey.DATE_IDENTIFIED else EventKind.COLLECTING
        if event is None or event.kind != expected_kind:
            raise EvidenceError("Date assigned from collecting/preparation/determination wrong event")
        # Complex historical date normalization remains a separate qualified utility.
        if not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", written):
            raise EvidenceError("Historical date needs deterministic date utility receipt")
        expected_precision = {4: "year", 7: "month", 10: "day"}[len(written)]
        if resolution.value.precision != expected_precision:
            raise EvidenceError("Date precision differs from written evidence")
    if written != target:
        raise EvidenceError("Transcribed value differs from immutable assembly")
    if resolution.field_key == FieldKey.COLLECTORS:
        event = next((item for item in request.events if item.id == resolution.event_id), None)
        if event is None or event.kind != EventKind.COLLECTING:
            raise EvidenceError("Collector literal requires accepted collecting-event relationship")
    if resolution.field_key == FieldKey.COLLECTION_CODE and written.upper().replace(" ", "") in {"FMNHINS", "FMNH-INS"}:
        raise EvidenceError("Catalog prefix is not Collection Code")
    if resolution.field_key in {FieldKey.HABITAT, FieldKey.COLLECTION_METHOD} and (
        not re.search(r"[^\W\d_]{2}", written, re.UNICODE)
        or re.fullmatch(r"[A-Za-z0-9]+(?:[-./][A-Za-z0-9]+)+", written) and re.search(r"\d", written)
    ):
        raise EvidenceError("G45 preparation/code token cannot satisfy habitat or method")
    if not set(resolution.evidence_ids) <= {eid for item in accepted for eid in item.evidence_ids}:
        raise EvidenceError("Literal resolution evidence is not grounded")
    return resolution
