"""Deterministic, abstaining Insects disposition policy (insects-clearance-v2).

The queue decision (HARNESS.md section 16). What the harness resolved clears
(G1); what it could not resolve goes to needs human review with its reasons
(G6); a documented capability limit defers (QUE-004); an operational failure
blocks (QUE-005). Findings never route a record (G23, G27). A field the harness
produced (its `layer` is set) is read as the harness wrote it: the verbatim or,
with none chosen, the settled value (G27, G28), and a derived value only with
its derivation record (G37, G41). A field from the older extraction path is
read as before.
"""

import calendar
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from .derivations import NUMBER
from .domain import (
    OPERATIONAL,
    Disposition,
    Evidence,
    FieldValue,
    Lookup,
    LookupStatus,
    Run,
    ValueState,
)

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
DATE_FIELDS = ("date_visited_from", "date_visited_to", "date_identified")


def evaluate(run: Run) -> list[str]:
    failures = []
    for label in run.label_language_handling.get("labels", []):
        if label.get("review_required") and not run.human_approved:
            failures.extend(
                reason + ":" + label["region_id"] for reason in label["reasons"]
            )
    if not _lane(run) and not run.profile.institutional_policy_approved:
        failures.append("institutional_policy_unapproved")
    if not _lane(run) and not run.profile.semantics_confirmed:
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
        if (
            not transcripts or any(not t.resolved or not t.text for t in transcripts)
        ) and not _resolved_by_harness(run, {o.id for o in observations}):
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
    if run.harness_failure:  # The harness decided no field (G6).
        failures.append(f"harness_failure:{run.harness_failure}")
    for key in run.profile.mandatory_fields:
        field = run.fields.get(key)
        value = _value(field, evidence)
        if (
            not field
            or field.state != ValueState.SUPPORTED
            or not value
            or not value.strip()
            or value.strip().casefold() in PLACEHOLDERS
        ):
            failures.append(f"mandatory_unresolved:{key}")
            continue
        if not field.evidence_ids or any(e not in evidence for e in field.evidence_ids):
            failures.append(f"evidence_missing:{key}")
        elif not _grounded(field, evidence):
            failures.append(f"evidence_does_not_support_value:{key}")
        elif not any(evidence[e].region_id in region_ids for e in field.evidence_ids):
            failures.append(f"pixel_lineage_missing:{key}")
        for layer, value in (
            ("parsed", field.parsed),
            ("normalized", field.normalized),
            ("authority_id", field.authority_id),
        ):
            if (
                value
                and value != field.literal
                and not _supported(field, layer, value, evidence)
            ):
                failures.append(f"unsupported_{layer}:{key}")
    for unit in ("m", "ft"):
        lower = _elevation(run.fields.get(f"elevation_from_{unit}"), evidence)
        upper = _elevation(run.fields.get(f"elevation_to_{unit}"), evidence)
        if lower is not None and upper is not None:
            if not lower.is_finite() or not upper.is_finite() or lower > upper:
                failures.append(f"elevation_range:{unit}")
        else:
            failures.append(f"elevation_invalid:{unit}")
    for end in ("from", "to"):
        m = _elevation(run.fields.get(f"elevation_{end}_m"), evidence)
        ft = _elevation(run.fields.get(f"elevation_{end}_ft"), evidence)
        if (
            m is not None
            and ft is not None
            and (
                not m.is_finite()
                or not ft.is_finite()
                or abs(m * Decimal("3.28084") - ft) > 1
            )
        ):
            failures.append(f"elevation_units_conflict:{end}")
    start, end, identified = (_days(run.fields.get(key)) for key in DATE_FIELDS)
    if start is not None and end is not None and identified is not None:
        # At the precision written (G24): a year or a month is a span of days.
        if (
            start[0] > end[1]
            or identified[1] < start[0]
            or identified[0] > date.today()  # noqa: DTZ011 - the local day, as before.
        ):
            failures.append("date_order")
    else:
        failures.append("date_precision_requires_review")
    catalog = _texts(run.fields.get("fmnh_ins_number"))
    if not catalog or not all(
        re.fullmatch(r"FMNH[- ]?INS[ #]*\d+", text, re.IGNORECASE) for text in catalog
    ):
        failures.append("identifier_format")
    if not _lane(run) and not run.human_approved:
        failures.append("human_approval_required")
    lookup = taxon_lookup(run)
    if lookup is None:
        failures.append("taxonomy_lookup_missing")
    elif lookup.status != LookupStatus.SUCCESS:
        taxon = run.fields.get("taxon")
        if (
            lookup.status != LookupStatus.AMBIGUOUS
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
    run.disposition_summary = None
    lookup = taxon_lookup(run)
    if run.blocker or (lookup is not None and lookup.status in OPERATIONAL):
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
    run.disposition_summary = summary(run)
    run.stage = "finalized"


def summary(run: Run) -> str | None:
    """QUE-006's summary: one deterministic sentence from the rule version and
    the reason codes, without their details."""
    if run.disposition is None:
        return None
    codes = ", ".join(dict.fromkeys(r.split(":", 1)[0] for r in run.reasons))
    version = run.profile.policy_version
    if run.disposition == Disposition.CLEARED:
        return f"Cleared under {version}."
    if run.disposition == Disposition.DEFERRED:
        return f"Deferred under {version}: {codes}."
    return f"Needs human review under {version}: {codes}."


def taxon_lookup(run: Run) -> Lookup | None:
    """The GBIF lookup the taxon's decision rests on. After the harness: the
    latest on the literal whose call settled it, else on any of the taxon's
    readings (G19, G20), never another lookup the agent made. Otherwise the
    lookup step's last one, as before. A later lookup of the same request
    recovers an earlier failure."""
    if not run.tool_calls:
        return run.lookups[-1] if run.lookups else None
    taxon = run.fields.get("taxon") or FieldValue()
    deciding = {e for e, r in taxon.evidence_relations.items() if r == "decides"}
    literals = [
        call.arguments.get("literal")
        for call in run.tool_calls
        if call.tool == "taxonomy_verifier" and call.evidence_id in deciding
    ] or _texts(taxon)
    return next(
        (
            lookup
            for lookup in reversed(run.lookups)
            if lookup.provider == "gbif"
            and lookup.query.get("scientificName") in literals
        ),
        None,
    )


def _lane(run: Run) -> bool:
    """G1 applies to a run whose fields the harness decided: its profile names
    the harness route (HARNESS.md section 14). Every other run keeps the
    approval gates, synthetic demos and runs before the switch alike."""
    return run.profile.harness_route is not None


def _texts(field: FieldValue | None) -> list[str]:
    """What a field reads as written: its verbatim, else each reader's (G27)."""
    if field is None:
        return []
    if field.literal:
        return [field.literal]
    return [text for text in field.verbatim_by_observation.values() if text]


def _record(field: FieldValue, evidence: dict[str, Evidence]) -> bool:
    """A derived value's record decides it (HARNESS.md section 13; #124)."""
    return any(
        relation == "decides"
        and e in evidence
        and evidence[e].kind == "derivation"
        and evidence[e].raw_ref
        for e, relation in field.evidence_relations.items()
    )


def _value(field: FieldValue | None, evidence: dict[str, Evidence]) -> str | None:
    """The value the non-empty check reads: the verbatim when one was chosen,
    else the settled value (G27, G28); a derived value only with its record, so
    a value asserted without one never counts (G37, G41; #124)."""
    if field is None:
        return None
    if field.layer == "derived":
        return field.parsed if _record(field, evidence) else None
    if field.literal or field.layer is None:
        return field.literal
    if field.verbatim_by_observation:
        return field.authority_id or field.parsed or field.normalized
    return None


def _grounded(field: FieldValue, evidence: dict[str, Evidence]) -> bool:
    """Each reading the value rests on is in its own literal evidence (G19,
    G27): the verbatim, or every reader's when none was chosen."""
    if field.layer is None:  # The extraction path, as before.
        return any(field.literal in evidence[e].excerpt for e in field.evidence_ids)
    if field.layer == "derived":
        return True  # Its record is checked with its value.
    literal = [evidence[e] for e in field.evidence_ids if evidence[e].kind == "literal"]
    readings = field.verbatim_by_observation or {
        field.source_observation_id: field.literal
    }
    return all(
        any(o in e.observation_ids and text in e.excerpt for e in literal)
        for o, text in readings.items()
    )


def _supported(
    field: FieldValue, name: str, value: str, evidence: dict[str, Evidence]
) -> bool:
    """A settled value rests on a success record among its field's evidence
    (G20, G23, G33): a lookup's for an authority id, the date parser's or the
    specimen's date order for a parsed date; a derived value on its record."""
    if field.layer is None:  # The extraction path, as before.
        return any(
            evidence[e].kind in {"authority", "authority_selection", "derived"}
            and value in evidence[e].excerpt
            for e in field.evidence_ids
            if e in evidence
        )
    if field.layer == "derived":
        return _record(field, evidence)
    records = [
        evidence[e]
        for e, relation in field.evidence_relations.items()
        if e in evidence and relation in ("decides", "supports")
    ]
    if name == "authority_id":
        # One call can settle several fields, each with its own record id,
        # while its evidence keeps one locator (#88, 4.4).
        return any(e.kind == "lookup" and _succeeded(e) for e in records)
    if name == "parsed":
        return any(_succeeded(e) or e.kind == "date_order" for e in records)
    # A settled name, or the one text every label read (G32).
    return any(_succeeded(e) for e in records) or set(_texts(field)) == {value}


def _succeeded(e: Evidence) -> bool:
    """A lookup's locator is set exactly when it succeeded (#88, 4.4)."""
    if e.kind == "lookup":
        return bool(e.locator)
    return e.kind == "validation" and e.excerpt.endswith(" success")


def _resolved_by_harness(run: Run, observations: set[str]) -> bool:
    """G19 and G20: a label whose first pass picked no reading passes when the
    harness drew fields from its readings and every mandatory one resolved."""
    mandatory = set(run.profile.mandatory_fields)
    drawn = {
        key: field
        for key, field in run.fields.items()
        if field.layer is not None
        and (
            field.source_observation_id in observations
            or observations & set(field.verbatim_by_observation)
        )
    }
    return bool(drawn) and all(
        field.state == ValueState.SUPPORTED
        for key, field in drawn.items()
        if key in mandatory
    )


def _elevation(field: FieldValue | None, evidence) -> Decimal | None:
    """An elevation's number: the one its label states, or a derived value with
    its record (G37, G41; #124); the extraction path's literal as before."""
    if field is None:
        return None
    if field.layer is None:
        try:
            return Decimal(field.literal or "")
        except InvalidOperation:
            return None
    if field.state != ValueState.SUPPORTED:
        return None
    text = _value(field, evidence) if field.layer == "derived" else None
    text = text or field.literal or field.normalized or ""
    numbers = NUMBER.findall(text)
    return Decimal(numbers[0].replace(",", "")) if len(numbers) == 1 else None


def _days(field: FieldValue | None) -> tuple[date, date] | None:
    """The first and last day a date covers at the precision written (G24): a
    year, a month or a day. None when it has no date, or is written as
    uncertain ("?"), which keeps the date gate (G24)."""
    if field is None:
        return None
    if field.layer is None:  # The extraction path: an ISO day, as before.
        text, precision = field.literal, "day"
    else:
        if field.state != ValueState.SUPPORTED or any(
            "?" in text for text in _texts(field)
        ):
            return None
        text, precision = field.parsed, field.precision or "day"
    try:
        if precision == "year":
            year = int(text)
            return date(year, 1, 1), date(year, 12, 31)
        if precision == "month":
            year, month = (int(part) for part in text.split("-"))
            return date(year, month, 1), date(
                year, month, calendar.monthrange(year, month)[1]
            )
        day = date.fromisoformat(text)
        return day, day
    except (TypeError, ValueError):
        return None
