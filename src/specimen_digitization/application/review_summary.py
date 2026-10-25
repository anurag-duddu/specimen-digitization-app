"""Field attention counts, independent of clearance and record disposition.

Search projects only state and value presence from the current snapshot.
Legacy externalized graphs use a bounded verified compatibility read.
The frontend's field presentation uses these same rules for section counts.
"""

FIELD_REASONS = frozenset(
    {
        "mandatory_unresolved",
        "mandatory_evidence_unresolved",
        "evidence_missing",
        "evidence_does_not_support_value",
        "pixel_lineage_missing",
        "unsupported_parsed",
        "unsupported_normalized",
        "unsupported_authority_id",
        "literal_not_in_source_excerpt",
        "candidate_resolution_requires_review",
        "competing_mandatory_candidates",
        "raw_reading_grounding_unproved",
        "preserved_human_decision",
    }
)
# Unicode White_Space plus BOM, matching Dart String.trim and both SQL projections.
DISPLAY_WHITESPACE = (
    "\t\n\v\f\r \u0085\u00a0\u1680"
    + "".join(chr(code) for code in range(0x2000, 0x200B))
    + "\u2028\u2029\u202f\u205f\u3000\ufeff"
)
REASON_FIELDS = {
    "identifier_format": "fmnh_ins_number",
    "taxonomy_unresolved": "taxon",
    "taxonomy_lookup_missing": "taxon",
    "identified_by_irn_identity_unproved": "identified_by_irn",
}
KNOWN_FIELDS = frozenset(
    {
        "fmnh_ins_number",
        "collection_code",
        "country",
        "province_state",
        "county",
        "city",
        "precise_location",
        "elevation_from_m",
        "elevation_to_m",
        "elevation_from_ft",
        "elevation_to_ft",
        "habitat",
        "collection_method",
        "date_visited_from",
        "date_visited_to",
        "collectors",
        "verbatim_dts",
        "taxon",
        "identified_by_irn",
        "date_identified",
    }
)


def project_fields(fields):
    """Project display value presence without treating raw readings as settled."""
    if not isinstance(fields, dict):
        return None
    return {
        key: (
            {
                "state": value.get("state"),
                "has_value": any(
                    isinstance(value.get(layer), str)
                    and value[layer].strip(DISPLAY_WHITESPACE)
                    for layer in ("normalized", "parsed", "literal")
                ),
            }
            if isinstance(value, dict)
            else None
        )
        for key, value in fields.items()
    }


def review_summary(fields, reasons):
    """Return unknown for absent fields; count each materialized field once.

    Missing and review are separate, overlapping measures. A resolved absence
    is missing, but only needs review with an attached blocking reason. A
    not-applicable field is neither missing nor needing review without a reason.
    Warning/info findings and record/label/processing reasons do not inflate
    field counts. Pending edits are handled locally by the field presentation.
    """
    if not isinstance(fields, dict) or not fields:
        return None
    if any(
        not isinstance(value, dict)
        or type(value.get("has_value")) is not bool
        or (value.get("state") is not None and not isinstance(value["state"], str))
        for value in fields.values()
    ):
        return None
    attention = set()
    for code in reasons or []:
        if not isinstance(code, str):
            continue
        base, _, suffix = code.partition(":")
        field = REASON_FIELDS.get(code)
        if base in FIELD_REASONS:
            field = suffix
        elif base in {"elevation_invalid", "elevation_range"} and suffix in {"m", "ft"}:
            field = f"elevation_from_{suffix}"
        elif base == "elevation_units_conflict" and suffix in {"from", "to"}:
            field = f"elevation_{suffix}_m"
        if field in fields and field in KNOWN_FIELDS:
            attention.add(field)
    missing = 0
    for key, value in fields.items():
        state, has_value = value.get("state"), value["has_value"]
        if state not in {"supported", "not_present", "not_applicable"} or (
            state == "supported" and not has_value
        ):
            attention.add(key)
        if state != "not_applicable" and (state == "not_present" or not has_value):
            missing += 1
    return {"review": len(attention), "missing": missing}
