"""Taxonomy-only source context and captured negative evidence.

Label context narrows a GBIF query; it is never an accepted classification.
Neither supporting sources nor a failed request can substitute for GBIF.
"""
from __future__ import annotations

import hashlib
import json
import re

from specimen_digitization.application.lookup import COL_XR, scientific_name

from .contracts import (
    FieldKey, FieldResolution, LookupStatus, SourceCoverageState, SourceQuery, SourceResult,
    SpecialistRequest, WorkState, digest,
)


def taxonomy_scientific_name(literal: str):
    """Project only an explicit taxon marker; preserve the original assertion.

    Label keys are case insensitive. Other keys, partial names and unwritten
    genera still receive the scientific-name parser's existing abstention.
    """
    return scientific_name(re.sub(r"^\s*(?i:taxon)\s*:\s*", "", literal))


def taxonomy_name_forms(literal: str) -> set[str]:
    """Exact written name and its qualified lookup projection, without a key."""
    written = re.sub(r"^\s*(?i:taxon)\s*:\s*", "", literal)
    name = taxonomy_scientific_name(literal)
    return {written, name.query} if name and name.genus and name.partly_read is None else set()


def _whole_line(item) -> bool:
    start = item.observation_text.rfind("\n", 0, item.start) + 1
    end = item.observation_text.find("\n", item.start)
    end = len(item.observation_text) if end == -1 else end
    return (item.granularity == "line" and item.start == start
        and item.literal == item.observation_text[start:end].rstrip("\r"))


def taxonomy_query_digests(source: str, queries) -> set[str]:
    """Bind the exact query while accepting either unused regional flag value.

    GBIF/GNV/COL ignore north_american in their URLs. Retain the actual flag in
    capture identity; never attach a specimen join to a negative name search.
    """
    return {digest(SourceQuery(source_id=source, field_key=FieldKey.TAXON,
        query_text=query, north_american=regional)) for query in queries for regional in (False, True)}


def gbif_query_params(request: SpecialistRequest, query: SourceQuery) -> dict[str, str]:
    """Add only unanimous, explicit same-label order/family to the Insects query.

    Original fragments and the actual URL are retained by source capture V2.
    No model-supplied lineage, unkeyed capitalized word, or other label is used.
    Missing or contradictory context is omitted, leaving GBIF's rank and
    homonym checks intact. A morphocode never supplies an unwritten genus.
    """
    parsed = scientific_name(query.query_text)
    if parsed is None or not parsed.genus:
        raise ValueError("Scientific name cannot be parsed at stated rank")
    params = {"scientificName": parsed.query, "taxonRank": parsed.rank,
              "kingdom": "Animalia", "class": "Insecta", "checklistKey": COL_XR, "verbose": "true"}
    fragments = [item for item in request.fragments if item.scope == request.scope]
    regions = set()
    for item in fragments:
        name = taxonomy_scientific_name(item.literal)
        if _whole_line(item) and not item.unreadable and name and name.partly_read is None and name.query == parsed.query:
            regions.add(item.region_id)
    for rank in ("order", "family"):
        by_region = []
        for region in regions:
            readings = {item.observation_id for item in fragments if item.region_id == region}
            values = []
            for reading in readings:
                explicit = set()
                for item in fragments:
                    if item.region_id != region or item.observation_id != reading or item.unreadable or not _whole_line(item):
                        continue
                    match = re.fullmatch(rf"\s*(?i:{rank})\s*:\s*([A-Z][a-z]+)\s*", item.literal)
                    if match:
                        explicit.add(match[1])
                values.append(explicit)
            if values and all(len(value) == 1 and value == values[0] for value in values):
                by_region.append(next(iter(values[0])))
            else:
                by_region.append(None)
        if by_region and None not in by_region and len(set(by_region)) == 1:
            params[rank] = by_region[0]
    return params


def captured_gbif_no_match(request: SpecialistRequest, result: SourceResult, literal: str) -> bool:
    """Prove a negative for this exact reader query or its qualified projection.

    A completed semantic receipt is necessary; the native publisher separately
    verifies immutable raw captures. Old evidence lacking query identity cannot
    be retroactively interpreted as a no-match for a competing reading.
    """
    from .sources import result_envelope

    queries = taxonomy_name_forms(literal)
    receipt, coverage = result.receipt, result.coverage
    payload = result_envelope(result)
    evidence_ids = tuple(item.id for item in result.evidence)
    return bool(result.status == LookupStatus.NO_MATCH and not result.candidate_json
        and coverage.source_id == "gbif" and coverage.field_key == FieldKey.TAXON
        and coverage.state == SourceCoverageState.SEARCHED
        and coverage.qualification_digest is not None and coverage.candidate_count in {None, 0}
        and coverage.query_digest in taxonomy_query_digests("gbif", queries)
        and evidence_ids and coverage.receipt_ids == evidence_ids
        and all(item.source_id == "gbif" for item in result.evidence)
        and receipt is not None and receipt.scope == request.scope and receipt.source_id == "gbif"
        and receipt.field_keys == (FieldKey.TAXON,) and receipt.effect_status == "completed"
        and receipt.outcome == LookupStatus.NO_MATCH and receipt.evidence_ids == evidence_ids
        and receipt.result_json == payload
        and receipt.result_digest == hashlib.sha256(payload.encode()).hexdigest())


def taxonomy_stop_defect(request: SpecialistRequest, results: tuple[SourceResult, ...]) -> str | None:
    """A searched unresolved name needs supporting breadth before a policy stop.

    No query is required for genus-free codes or absent names. An admitted
    source's refusal remains recorded unavailability, never a scientific
    negative. Outages are handled separately by the exact-query outage guard.
    """
    from .sources import result_envelope

    if available_taxonomy_settlement(request, results):
        return "taxonomy_research_has_settled_candidate: return the exact captured GBIF settlement and its producer; preserve supporting disagreement"
    forms = taxonomy_name_forms

    literals = {item.interpreted_text for item in request.assemblies if item.field_key == FieldKey.TAXON}
    literals.update(item.literal for item in request.organiser_candidates
        if item.field_key == FieldKey.TAXON and item.status != "ungrounded")
    for item in request.fragments:
        match = re.fullmatch(r"\s*(?i:taxon)\s*:\s*(\S.*)", item.literal)
        if item.scope == request.scope and _whole_line(item) and not item.unreadable and match:
            literals.add(match[1])
    explicit = {literal for literal in literals if forms(literal)}
    searched = [item for item in results if item.coverage.field_key == FieldKey.TAXON
        and item.coverage.source_id == "gbif" and item.coverage.state == SourceCoverageState.SEARCHED]
    if not searched:
        if explicit and not any(item.coverage.source_id == "gbif"
            and item.coverage.field_key == FieldKey.TAXON for item in results):
            return "taxonomy_research_incomplete: query the explicitly evidenced named taxon before a policy stop"
        return None
    # Use explicitly located field assertions and the exact lines that were
    # queried as anchors. Do not turn every capitalized locality word into a
    # genus. Same-line reader alternatives remain required work after a
    # no-match of the first reading, even with zero organiser assemblies.
    anchors = set()
    for fragment in request.fragments:
        if fragment.unreadable or not forms(fragment.literal):
            continue
        queries = forms(fragment.literal)
        if fragment.literal in literals or any(
            item.coverage.query_digest in taxonomy_query_digests("gbif", queries)
            or any(json.loads(candidate).get("input_literal") in queries for candidate in item.candidate_json)
            for item in searched):
            anchors.add((fragment.region_id, fragment.order))
            literals.add(fragment.literal)
    literals.update(item.literal for item in request.fragments if not item.unreadable
        and (item.region_id, item.order) in anchors and item.granularity == "line" and forms(item.literal))
    literals = {literal for literal in literals if forms(literal)}
    for source in ("gbif", "global_names_verifier", "catalogue_of_life"):
        attempts = [item for item in results if item.coverage.source_id == source
            and item.coverage.field_key == FieldKey.TAXON]
        if not attempts:
            return "taxonomy_research_incomplete: query the remaining approved supporting sources before an unresolved stop"
        for literal in literals:
            queries = forms(literal)
            if not any(item.status == LookupStatus.POLICY
                or item.coverage.query_digest in taxonomy_query_digests(source, queries)
                or any(json.loads(candidate).get("input_literal") in queries for candidate in item.candidate_json)
                for item in attempts):
                return "taxonomy_research_incomplete: query each evidenced reader alternative with the approved sources before stopping"
        for item in attempts:
            if item.status == LookupStatus.POLICY:
                continue  # An explicit local refusal sent no request.
            receipt = item.receipt
            if (receipt is None or receipt.scope != request.scope or receipt.source_id != source
                or receipt.field_keys != (FieldKey.TAXON,) or receipt.effect_status != "completed"
                or receipt.outcome != item.status or receipt.result_json != result_envelope(item)):
                return "taxonomy_research_incomplete: preserve incomplete capture as waiting_source; do not claim a completed search"
    return None


def available_taxonomy_settlement(request: SpecialistRequest, results: tuple[SourceResult, ...]) -> bool:
    """Check source-backed proposals against the same admission boundary.

    This is feedback for an invalid unresolved stop, not a new checkpoint or
    an invented field. Conflicting assertions and ties fail normal validation.
    """
    from specimen_digitization.application.domain import FieldValue, ValueState
    from .evidence import EvidenceError, validate_resolution

    forms = taxonomy_name_forms

    for result in results:
        if result.status != LookupStatus.SUCCESS or result.coverage.source_id != "gbif":
            continue
        for raw in result.candidate_json:
            candidate = json.loads(raw)
            if (candidate.get("field_key") != "taxon" or candidate.get("authority_role") != "decides"
                or not candidate.get("value") or not candidate.get("authority_id")):
                continue
            evidence = {item.id: item for source in results if source.status == LookupStatus.SUCCESS
                and any(json.loads(other).get("field_key") == "taxon"
                    and json.loads(other).get("value") == candidate["value"]
                    and json.loads(other).get("authority_id") == candidate["authority_id"]
                    for other in source.candidate_json) for item in source.evidence}
            base = {"state": ValueState.SUPPORTED, "parsed": candidate["value"],
                "normalized": candidate["value"], "authority_id": candidate["authority_id"],
                "evidence_ids": list(evidence), "evidence_relations": {key: item.role for key, item in evidence.items()}}
            producers = []
            assemblies = tuple(item for item in request.assemblies if item.field_key == FieldKey.TAXON)
            if any(candidate.get("input_literal") in forms(item.interpreted_text) for item in assemblies):
                producers.append((FieldValue(**base), tuple(item.id for item in assemblies), assemblies[0].event_id))
            for item in request.fragments:
                if item.unreadable or candidate.get("input_literal") not in forms(item.literal):
                    continue
                producers.append((FieldValue(**base, source_observation_id=item.observation_id,
                    source_region_id=item.region_id, input_source=item.input_source,
                    verbatim_by_observation={item.observation_id: item.observation_text},
                    settled_observation_ids=[item.observation_id]), (), None))
            for value, assembly_ids, event_id in producers:
                proposal = FieldResolution(field_key=FieldKey.TAXON, work_state=WorkState.RESOLVED,
                    value_layer="settled", value=value, evidence_ids=tuple(evidence),
                    assembly_ids=assembly_ids, event_id=event_id, reason="Check retained deciding candidate")
                try:
                    validate_resolution(request, proposal, results)
                except EvidenceError:
                    continue
                return True
    return False
