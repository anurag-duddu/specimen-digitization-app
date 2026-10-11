"""Derived values after field research (G37, G41, G44; HARNESS.md section 13).

A field the label leaves out is filled from fields that are settled, and only
from those (G37). Elevations follow G41 through the existing rules,
application.derivations.elevation_derivations: one stated elevation fills both
ends of its unit, and the other unit's fields are its exact conversion (1 ft =
0.3048 m, to the hundredth) when the label states nothing in that unit. The
collection date's end is its start when the label states no end (G44, PLAN.md
row G44: "Date Visited To gets the same date, marked as derived from Date
Visited From").

application.derivations.apply_derivations is not reused: its evidence row says
which rule applied but not the value, so no evidence item would contain the
value the field holds (policy.py 82-98), and it has no G44 rule. Each value
here is its own layer ("derived"), names the fields it comes from and cites one
"derived" evidence item whose excerpt states the value, the rule and its input;
the input fields' evidence supports it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from specimen_digitization.application.derivations import RULES as ELEVATION_RULES
from specimen_digitization.application.derivations import UNITS, elevation_derivations, settled_value
from specimen_digitization.application.domain import Evidence, FieldValue, ValueState
from specimen_digitization.application.field_validators import written_range

RULES_VERSION = "field-research-derivations-v1"
SOURCE = "field_research"
ELEVATIONS = tuple(key for pair in UNITS.values() for key in pair)
# A field the label leaves out: nothing stated, nothing settled.
OPEN = frozenset({ValueState.UNKNOWN, ValueState.NOT_PRESENT})
# The layers of a value field research settled from the label (step.RESEARCHED
# less "derived").
RESEARCHED = frozenset({"verbatim", "settled"})
G44_DETAIL = "the label states one collecting date, so the collection ends on the day it began (G44)"


def is_open(value: FieldValue | None) -> bool:
    """Whether a field holds no value and no reading states one."""
    return value is not None and value.state in OPEN and not value.literal and not value.verbatim_by_observation


def fill(run, *, eligible: Iterable[str], asset_id: str | None, blobs=None) -> list[str]:
    """Fill each eligible open field that settled fields derive; the keys filled.

    ``eligible`` names the fields field research may change (a person's
    decision is never one). A stated value is never replaced.
    """
    fields = run.fields
    targets = {key for key in eligible if is_open(fields.get(key))}
    filled: list[str] = []
    for derivation in _elevations(fields):
        key = derivation.field_key
        if key not in targets or key in filled:
            continue
        details = "; ".join(check.detail or ELEVATION_RULES.get(check.name, check.name)
            for check in derivation.evidence)
        fields[key] = _derived(run, key, derivation.value, rule=derivation.method, detail=details,
            inputs=dict(derivation.inputs), asset_id=asset_id, blobs=blobs)
        filled.append(key)
    start = fields.get("date_visited_from")
    # A written range keeps both ends as written (G44): its start is never also its end.
    if ("date_visited_to" in targets and start is not None and start.state == ValueState.SUPPORTED
            and not written_range(start.literal or "") and (value := settled_value(start))):
        fields["date_visited_to"] = _derived(run, "date_visited_to", value, rule="single_collecting_date",
            detail=G44_DETAIL, inputs={"date_visited_from": value}, asset_id=asset_id, blobs=blobs,
            precision=start.precision, century_rule=start.century_rule)
        filled.append("date_visited_to")
    return filled


def _elevations(fields):
    """G41's derivations, unless an elevation is neither settled nor open: an
    elevation the readings disagree on, or the sources could not settle, goes to
    review before anything is derived from its unit's fields.

    The rules read a stated elevation's literal. A literal field research
    settled through the elevation check keeps the organiser's whole candidate
    ("180 to 181 m", "ca. 1200 m") and holds the check's number for its field
    as its parsed value: the rules read that number, in the field's own unit."""
    present = [fields[key] for key in ELEVATIONS if key in fields]
    if any(value.state != ValueState.SUPPORTED and not is_open(value) for value in present):
        return []
    view = dict(fields)
    for key in ELEVATIONS:
        value = fields.get(key)
        if (value is not None and value.state == ValueState.SUPPORTED and value.layer in RESEARCHED
                and value.literal and value.parsed and value.parsed != value.literal):
            view[key] = value.model_copy(update={"literal": value.parsed})
    return elevation_derivations(view)


def _derived(run, key, value, *, rule, detail, inputs, asset_id, blobs, precision=None, century_rule=None):
    stated = ", ".join(f"{source} = {text}" for source, text in inputs.items())
    excerpt = f"{key} = {value}: {detail} (from {stated})"
    record = json.dumps({"field_key": key, "value": value, "rule": rule, "rules_version": RULES_VERSION,
        "inputs": inputs}, sort_keys=True).encode()
    item = Evidence(kind="derived", asset_id=asset_id, source=SOURCE, locator=f"derivation:{rule}",
        excerpt=excerpt, raw_ref=blobs.put(record) if blobs is not None else None,
        digest=hashlib.sha256(record).hexdigest() if blobs is not None else None)
    run.evidence.append(item)
    relations = {item.id: "decides"}
    for source in inputs:
        for evidence_id in run.fields[source].evidence_ids:
            relations.setdefault(evidence_id, "supports")
    return FieldValue(state=ValueState.SUPPORTED, parsed=value, evidence_ids=list(relations),
        evidence_relations=relations, layer="derived", derived_from=list(inputs),
        precision=precision, century_rule=century_rule, reason=f"Derived: {detail}.")
