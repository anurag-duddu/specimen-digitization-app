"""Derived values (HARNESS.md section 13; G37, G38, G41).

A field the label leaves out may be filled from fields with final values, with
its authority and evidence recorded, and the value fills the field, mandatory
fields included (G37); it is its own layer, after settled (G38). Every
derivation is a `Derivation` (section 6). S8's geographic tool emits some in
its result: containment for county and city, the elevation model, gazetteer
names. This module emits the elevation rules of G41 (the owner's answer of
2026-09-24, revising G22): the label's own number fills both ends of its unit,
and the other unit is converted by the exact factor, both ways in the
coordinator's reading. `apply_derivations` turns any of them into field
values; a stated value is never replaced, and a derivation applies only when
each field it comes from is settled to the value it names.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from .domain import Evidence, FieldValue, ValueState
from .harness_tools import Check, Derivation, SourceRef

RULES_VERSION = "derivation-rules-v1"
METRES_PER_FOOT = Decimal("0.3048")  # Exact, by the 1959 definition.
HUNDREDTH = Decimal("0.01")
UNITS = {
    "m": ("elevation_from_m", "elevation_to_m"),
    "ft": ("elevation_from_ft", "elevation_to_ft"),
}
RULES = {
    "stated_elevation": "one stated elevation is both the minimum and the maximum",
    "feet_to_metres": "1 ft = 0.3048 m, exact",
    "metres_to_feet": "1 m = 1/0.3048 ft, exact",
}
# A sign can start a quantity, but a hyphen attached to a preceding number
# separates range endpoints. Keep both numbers so a range is never one value.
NUMBER = re.compile(
    r"(?:(?<![\d.])[+−-])?"
    r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
)
# Read a complete quantity, never a numeric fragment left after an unrecognized
# sign, uncertainty marker or malformed number. Unit words remain label text.
ELEVATION_QUANTITY = re.compile(
    rf"\s*(?P<number>{NUMBER.pattern})\s*"
    r"(?P<unit>ft\.?|feet|foot|m\.?|met(?:er|re)s?\.?|['′’])?\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Found:
    """A derivation and the evidence of the tool call that returned it; each
    derived value names its tool call (#124, PLAN 4.8). The harness's own rules
    have no tool call and are passed as bare, internally generated Derivations.
    An external Found always needs its producing-call evidence."""

    derivation: Derivation
    call_evidence: tuple[str, ...] = ()


def settled_value(value: FieldValue | None) -> str | None:
    """A settled field's value as a derivation names it: a derived value
    itself; otherwise its authority id (a place ID or usage key), else its
    parsed, normalized or literal value."""
    if value is None or value.state != ValueState.SUPPORTED:
        return None
    if value.layer == "derived":  # Its authority id names the source record.
        return value.parsed
    return value.authority_id or value.parsed or value.normalized or value.literal


def stated_number(value: FieldValue | None, *, unit: str | None = None) -> Decimal | None:
    """One stated number, with a recognized suffix compatible with its field.
    A bare number uses the field's unit; agreed labels retain no root verbatim."""
    if value is None or value.state != ValueState.SUPPORTED:
        return None
    text = value.literal or (
        value.normalized if value.verbatim_by_observation else None
    )
    if not text:
        return None
    quantity = ELEVATION_QUANTITY.fullmatch(text)
    if quantity is None:
        return None
    if unit is not None and (suffix := quantity["unit"]) is not None:
        stated_unit = "m" if suffix.casefold().startswith("m") else "ft"
        if stated_unit != unit:
            return None  # Preserve the label; the field cannot relabel its unit.
    return Decimal(quantity["number"].replace(",", "").replace("−", "-"))


def elevation_derivations(fields: Mapping[str, FieldValue]) -> list[Derivation]:
    """The elevation fields the label leaves out that its stated ones fill."""
    keys = [key for pair in UNITS.values() for key in pair]
    if any(_stated(fields, key) and not _settled(fields, key) for key in keys):
        return []  # An elevation the readings disagree on goes to review first.
    known: dict[str, tuple[Decimal, str, list[str]]] = {}  # value, root, rules
    for key in keys:
        unit = "m" if key.endswith("_m") else "ft"
        if (number := stated_number(fields.get(key), unit=unit)) is not None:
            known[key] = (number, key, [])
    for low, high in UNITS.values():  # A single stated value is both ends.
        for have, missing in ((low, high), (high, low)):
            if have in known and missing not in known and not _stated(fields, missing):
                value, root, rules = known[have]
                known[missing] = (value, root, [*rules, "stated_elevation"])
    for unit, other in (("m", "ft"), ("ft", "m")):
        if any(_stated(fields, key) for key in UNITS[other]):
            continue  # The label states the other unit; nothing converts.
        rule = "metres_to_feet" if unit == "m" else "feet_to_metres"
        for source, target in zip(UNITS[unit], UNITS[other], strict=True):
            if source in known and target not in known:
                value, root, rules = known[source]
                converted = (
                    value / METRES_PER_FOOT if unit == "m" else value * METRES_PER_FOOT
                )
                known[target] = (converted, root, [*rules, rule])
    return [
        Derivation(
            field_key=key,
            value=_text(value, converted=rules[-1] != "stated_elevation"),
            unit="m" if key.endswith("_m") else "ft",
            method="stated_elevation"
            if rules == ["stated_elevation"]
            else "unit_conversion",
            # The rule's owner: a G41 value names apply_derivations (#124).
            authority=SourceRef(name="apply_derivations", version=RULES_VERSION),
            inputs={root: settled_value(fields[root])},
            evidence=[Check(name=r, result="supports", detail=RULES[r]) for r in rules],
        )
        for key, (value, root, rules) in known.items()
        if rules and not _stated(fields, key)
    ]


def apply_derivations(
    fields: Mapping[str, FieldValue],
    derivations: Sequence[Derivation | Found],
    *,
    asset_id: str,
    blobs,
) -> tuple[dict[str, FieldValue], list[Evidence]]:
    """Field values for the derivations of fields the label leaves out whose
    inputs are settled to the values they name (G37); two derivations of one
    field that disagree fill it with neither, and it waits for review."""
    found: list[Found] = []
    for derivation in derivations:
        item = derivation if isinstance(derivation, Found) else Found(derivation)
        local_rule = (
            not isinstance(derivation, Found)
            and item.derivation.authority.name == "apply_derivations"
            and item.derivation.authority.version == RULES_VERSION
            and item.derivation.method in {"unit_conversion", "stated_elevation"}
        )
        # Empty inputs cannot establish lineage. Unqualified external values
        # cannot fill a field or conflict with a qualified derivation of it.
        if item.derivation.inputs and (item.call_evidence or local_rule):
            found.append(item)
    values: dict[str, set[str]] = {}
    for item in found:
        values.setdefault(item.derivation.field_key, set()).add(item.derivation.value)
    filled: dict[str, FieldValue] = {}
    evidence: list[Evidence] = []
    for item in found:
        derivation = item.derivation
        key = derivation.field_key
        known = {**fields, **filled}  # An earlier derivation may be an input.
        if (
            key not in fields
            or key in filled
            or _stated(fields, key)
            or len(values[key]) > 1
            or any(
                settled_value(known.get(source)) != value
                for source, value in derivation.inputs.items()
            )
        ):
            continue
        record = json.dumps(
            {
                "derivation": json.loads(derivation.model_dump_json()),
                "call_evidence_ids": list(item.call_evidence),
            },
            sort_keys=True,
        ).encode()
        rule = Evidence(
            kind="derivation",
            asset_id=asset_id,
            source=derivation.authority.name,
            locator=f"derivation:{derivation.method}",
            excerpt="; ".join(c.detail or c.name for c in derivation.evidence),
            raw_ref=blobs.put(record) if blobs is not None else None,
            digest=hashlib.sha256(record).hexdigest() if blobs is not None else None,
        )
        evidence.append(rule)
        relations = {rule.id: "decides"} | dict.fromkeys(item.call_evidence, "supports")
        for source in derivation.inputs:
            relations |= dict.fromkeys(known[source].evidence_ids, "supports")
        filled[key] = FieldValue(
            state=ValueState.SUPPORTED,
            parsed=derivation.value,
            authority_id=derivation.authority.record_id,
            evidence_ids=list(relations),
            evidence_relations=relations,
            layer="derived",
            derived_from=list(derivation.inputs),
            reason=f"derived:{derivation.method}",
        )
    return filled, evidence


def _text(value: Decimal, *, converted: bool) -> str:
    """A plain decimal: a copied value as stated, a converted one to 0.01."""
    if converted:
        value = value.quantize(HUNDREDTH, rounding=ROUND_HALF_EVEN)
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _stated(fields: Mapping[str, FieldValue], key: str) -> bool:
    """Whether the label states this field (G37: it then stays as written)."""
    value = fields.get(key)
    return bool(value and (value.literal or value.verbatim_by_observation))


def _settled(fields: Mapping[str, FieldValue], key: str) -> bool:
    value = fields.get(key)
    return bool(value and value.state == ValueState.SUPPORTED)
