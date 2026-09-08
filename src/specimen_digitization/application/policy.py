"""Deterministic, abstaining Insects disposition policy."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from .domain import Disposition, OPERATIONAL, Run, ValueState

PLACEHOLDERS = {
    "unknown",
    "unreadable",
    "not present",
    "not applicable",
    "n/a",
    "na",
    "none",
    "null",
    "?",
    "tbd",
    "[unreadable]",
}


def evaluate(run: Run) -> list[str]:
    failures = []
    for label in run.label_language_handling.get("labels", []):
        if label.get("review_required") and not run.human_approved:
            failures.extend(
                reason + ":" + label["region_id"] for reason in label["reasons"]
            )
    if not run.profile.institutional_policy_approved:
        failures.append("institutional_policy_unapproved")
    if not run.profile.semantics_confirmed:
        failures.append("mandatory_semantics_unconfirmed")
    if not run.coverage_confirmed or not run.regions:
        failures.append("label_coverage_unconfirmed")
    for region in run.regions:
        observations = [o for o in run.observations if o.region_id == region.id]
        if (
            len({o.route_id for o in observations}) < 2
            or len({o.model_id for o in observations}) < 2
        ):
            failures.append(f"independent_observations_missing:{region.id}")
        if any(not o.raw_ref or not o.raw_sha256 for o in observations):
            failures.append(f"raw_provenance_missing:{region.id}")
        transcripts = [t for t in run.transcripts if t.region_id == region.id]
        if not transcripts or any(not t.resolved or not t.text for t in transcripts):
            failures.append(f"unresolved_transcription:{region.id}")
    evidence = {e.id: e for e in run.evidence}
    region_ids = {r.id for r in run.regions}
    observation_ids = {o.id for o in run.observations}
    for e in run.evidence:
        if e.kind == "literal" and (
            e.region_id not in region_ids
            or not any(
                r.id == e.region_id and r.asset_id == e.asset_id for r in run.regions
            )
            or not e.observation_ids
            or any(o not in observation_ids for o in e.observation_ids)
        ):
            failures.append(f"evidence_lineage_invalid:{e.id}")
    for key in run.profile.mandatory_fields:
        field = run.fields.get(key)
        if (
            not field
            or field.state != ValueState.SUPPORTED
            or not field.literal
            or not field.literal.strip()
            or field.literal.strip().casefold() in PLACEHOLDERS
        ):
            failures.append(f"mandatory_unresolved:{key}")
            continue
        if not field.evidence_ids or any(e not in evidence for e in field.evidence_ids):
            failures.append(f"evidence_missing:{key}")
        elif not any(field.literal in evidence[e].excerpt for e in field.evidence_ids):
            failures.append(f"evidence_does_not_support_value:{key}")
        elif not any(
            evidence[e].region_id in {r.id for r in run.regions}
            for e in field.evidence_ids
        ):
            failures.append(f"pixel_lineage_missing:{key}")
        for layer, value in (
            ("parsed", field.parsed),
            ("normalized", field.normalized),
            ("authority_id", field.authority_id),
        ):
            if (
                value
                and value != field.literal
                and not any(
                    e in evidence
                    and evidence[e].kind
                    in {"authority", "authority_selection", "derived"}
                    and value in evidence[e].excerpt
                    for e in field.evidence_ids
                )
            ):
                failures.append(f"unsupported_{layer}:{key}")
    for unit in ("m", "ft"):
        try:
            lower = Decimal(run.fields[f"elevation_from_{unit}"].literal or "")
            upper = Decimal(run.fields[f"elevation_to_{unit}"].literal or "")
            if not lower.is_finite() or not upper.is_finite() or lower > upper:
                failures.append(f"elevation_range:{unit}")
        except (InvalidOperation, KeyError):
            failures.append(f"elevation_invalid:{unit}")
    for end in ("from", "to"):
        try:
            m = Decimal(run.fields[f"elevation_{end}_m"].literal or "")
            ft = Decimal(run.fields[f"elevation_{end}_ft"].literal or "")
            if (
                not m.is_finite()
                or not ft.is_finite()
                or abs(m * Decimal("3.28084") - ft) > Decimal("1")
            ):
                failures.append(f"elevation_units_conflict:{end}")
        except (InvalidOperation, KeyError):
            pass
    try:
        start = date.fromisoformat(run.fields["date_visited_from"].literal or "")
        end = date.fromisoformat(run.fields["date_visited_to"].literal or "")
        identified = date.fromisoformat(run.fields["date_identified"].literal or "")
        if start > end or identified < start or identified > date.today():
            failures.append("date_order")
    except (ValueError, KeyError):
        failures.append("date_precision_requires_review")
    if not re.fullmatch(
        r"FMNH[- ]?INS[ #]*\d+",
        (
            run.fields["fmnh_ins_number"].literal
            if "fmnh_ins_number" in run.fields
            else ""
        )
        or "",
        re.I,
    ):
        failures.append("identifier_format")
    if not run.human_approved:
        failures.append("human_approval_required")
    if not run.lookups:
        failures.append("taxonomy_lookup_missing")
    elif run.lookups[-1].status.value != "success":
        lookup = run.lookups[-1]
        taxon = run.fields.get("taxon")
        if (
            lookup.status.value != "ambiguous"
            or not taxon
            or not taxon.authority_id
            or not any(
                e.kind == "authority_selection"
                and e.source == lookup.id
                and e.locator == "candidate:" + taxon.authority_id
                and e.id in taxon.evidence_ids
                for e in run.evidence
            )
        ):
            failures.append("taxonomy_unresolved")
    return list(dict.fromkeys(failures))


def finalize(run: Run) -> None:
    run.disposition = None
    if run.blocker or any(l.status in OPERATIONAL for l in run.lookups[-1:]):
        run.stage = "processing_blocked"
        run.reasons = [run.blocker or "lookup_operational_failure"]
        return
    run.reasons = evaluate(run)
    if (
        run.capability_reason
        and run.retry_eligibility
        and "capability_attempts_exhausted" in run.completed_steps
    ):
        run.disposition = Disposition.DEFERRED
        run.reasons = [run.capability_reason]
    else:
        run.disposition = Disposition.REVIEW if run.reasons else Disposition.CLEARED
    run.stage = "finalized"
