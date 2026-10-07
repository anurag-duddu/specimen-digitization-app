"""Bounded geography progress derived from retained source effects, not model plans."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from collections.abc import Sequence

from specimen_digitization.application.domain import LookupStatus, OPERATIONAL

from .contracts import ROLE_FIELDS, FieldKey, SourceQuery, SourceResult, SpecialistRequest, SpecialistRole, digest
from .sources import geolocate_interpretation, result_envelope

HISTORICAL_SOURCES = frozenset({"tgn", "wikidata", "nga"})
GEOGRAPHY_STRATEGY_VERSION = "geography-research-progress/v1"


def _query_identity(query: SourceQuery) -> str:
    data = query.model_dump(mode="json")
    if query.source_id == "geolocate":
        try:
            data["query_text"] = asdict(geolocate_interpretation(query.query_text, query.field_key))
        except ValueError:
            pass
    else:
        data["query_text"] = query.query_text.strip().casefold()
    return digest(data)


def _place_name(query: SourceQuery) -> str:
    try:
        data = json.loads(query.query_text)
        return str(data.get("place", "")).strip().casefold() if isinstance(data, dict) else ""
    except ValueError:
        return ""


@dataclass(frozen=True)
class SourceAttempt:
    query: SourceQuery
    result: SourceResult


@dataclass(frozen=True)
class GeographyProgress:
    field_key: str
    state: str
    stop_reason: str | None
    next_sources: tuple[str, ...]
    attempted_query_digests: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    review_eligible: bool = False
    version: str = GEOGRAPHY_STRATEGY_VERSION

    def as_dict(self):
        return asdict(self)


def captured(request: SpecialistRequest, result: SourceResult) -> bool:
    receipt = result.receipt
    return (receipt is not None and receipt.scope == request.scope
            and receipt.effect_status == "completed"
            and receipt.field_keys == (result.coverage.field_key,)
            and receipt.source_id == result.coverage.source_id
            and receipt.result_json == result_envelope(result))


def geography_progress(request: SpecialistRequest, field_key: FieldKey,
                       attempts: Sequence[SourceAttempt], available_sources: Sequence[str], *,
                       collecting_context=None) -> GeographyProgress:
    """Require one relevant alternative after absence, not an all-provider ritual.

    Getty/Wikidata/NGA are alternative place-name strategies. Once one returns
    complete coverage, repeating the same name in all three is not required.
    A captured historical hypothesis needs a later GEOLocate check. Failures
    never become exhaustion, including beside a successful alternative.
    """
    if field_key not in request.field_keys:
        raise ValueError("geography_progress_outside_requested_field")
    # A captured place-name strategy is useful to its related hierarchy fields.
    # GEOLocate's deciding result remains target-specific; sibling deciding
    # candidates cannot settle this field or replace its required lookup.
    shared_history = [item for item in attempts if item.query.field_key == field_key
        or (item.query.source_id in HISTORICAL_SOURCES
            and item.query.field_key in ROLE_FIELDS[SpecialistRole.GEOGRAPHY])]
    history = [item for item in shared_history if item.query.field_key == field_key]
    if any(item.query.source_id != item.result.coverage.source_id
           or item.query.field_key != item.result.coverage.field_key for item in shared_history):
        raise ValueError("geography_attempt_result_mismatch")
    retained = []
    seen = set()
    for item in shared_history:
        identity = _query_identity(item.query)
        if identity not in seen:
            seen.add(identity)
            retained.append(item)  # A replay cannot pretend to be later research.
    considered = history

    def progress(state, reason=None, next_sources=(), review=False):
        ids = tuple(dict.fromkeys(digest(item.query) for item in considered))
        evidence = tuple(dict.fromkeys(e.id for item in considered for e in item.result.evidence))
        return GeographyProgress(str(field_key), state, reason, tuple(next_sources), ids, evidence, review)

    settling = [item for item in history if captured(request, item.result)
                and item.result.status == LookupStatus.SUCCESS and any(
                    json.loads(raw).get("settlement_allowed") is not False
                    and not json.loads(raw).get("validation_required")
                    and json.loads(raw).get("automatic_settlement_allowed") is not False
                    and json.loads(raw).get("field_key") == str(field_key)
                    for raw in item.result.candidate_json)]
    if settling:
        return progress("candidate_ready", "exact_captured_candidate_required")
    if any(item.result.status in OPERATIONAL or not captured(request, item.result) for item in history):
        return progress("waiting_source", "failed_refused_or_unreceipted_strategy")
    geolocate = [item for item in retained if item.query.source_id == "geolocate"]
    available = set(available_sources)
    if not geolocate:
        return progress("research_pending", None, ("geolocate",) if "geolocate" in available else
                        tuple(sorted(available & HISTORICAL_SOURCES)))
    places = {_place_name(item.query) for item in geolocate} - {""}
    def relevant(item):
        name = item.query.query_text.strip().casefold()
        if name in places:
            return True
        for raw in item.result.candidate_json:
            candidate = json.loads(raw)
            names = {str(candidate.get("name", candidate.get("value", ""))).casefold(),
                     *(str(alias).casefold() for alias in candidate.get("names", ()))}
            if name in names and names & places:
                return True
        return False
    alternatives = [item for item in retained if item.query.source_id in HISTORICAL_SOURCES and relevant(item)]
    considered = [item for item in shared_history if item.query.field_key == field_key
                  or (item.query.source_id in HISTORICAL_SOURCES and relevant(item))]
    if any(item.result.status in OPERATIONAL or not captured(request, item.result) for item in considered):
        return progress("waiting_source", "failed_refused_or_unreceipted_strategy")
    if not alternatives and available & HISTORICAL_SOURCES:
        return progress("research_pending", "relevant_place_name_alternative_remaining",
                        sorted(available & HISTORICAL_SOURCES))
    if alternatives:
        for alternative in alternatives:
            position = retained.index(alternative)
            if (field_key in {FieldKey.COUNTRY, FieldKey.PROVINCE_STATE}
                    and alternative.result.candidate_json):
                from .geography_context import hierarchy_research
                try:
                    hierarchy = hierarchy_research(request, (alternative.result,), context=collecting_context)
                except ValueError:
                    return progress("waiting_source", "captured_hierarchy_or_dependency_proof_unavailable")
                required = {_query_identity(query) for query in hierarchy.next_queries if query.field_key == field_key}
                if not required:
                    reasons = {reason for key, reason in hierarchy.unresolved if key == field_key}
                    if not reasons or not reasons <= {"source_ambiguous", "ambiguous_authority_places"}:
                        return progress("waiting_source", "historical_hierarchy_level_or_date_unqualified")
                tested = {_query_identity(item.query) for item in geolocate}
                if required - tested:
                    return progress("research_pending", "captured_hierarchy_interpretation_needs_validation", ("geolocate",))
            hypotheses = {str(json.loads(raw).get("name", json.loads(raw).get("value", ""))).strip().casefold()
                          for raw in alternative.result.candidate_json} - {""}
            earlier = {_place_name(item.query) for item in retained[:position] if item.query.source_id == "geolocate"}
            novel = hypotheses - earlier
            followed = {_place_name(item.query) for item in retained[position + 1:] if item.query.source_id == "geolocate"}
            if novel - followed:
                return progress("research_pending", "captured_historical_hypothesis_needs_validation", ("geolocate",))
    if all(item.result.status in {LookupStatus.NO_MATCH, LookupStatus.AMBIGUOUS} for item in geolocate):
        return progress("needs_human", "scoped_absence_or_semantic_ambiguity_after_relevant_strategies", review=True)
    return progress("waiting_source", "no_qualified_settling_strategy_completed")
