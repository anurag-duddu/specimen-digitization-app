"""One explicitly requested, same-run reassessment of machine location claims.

The request selects work, never supplies a place or changes a saved field. A
private view removes the selected claims as constraints while the ordinary
research checks qualify fresh evidence. A partial answer cannot replace a
previously supported family with a mixture of old and new hierarchies.
"""
from __future__ import annotations

from collections.abc import Mapping

from specimen_digitization.application.domain import ValueState
from specimen_digitization.application.human_field_carry import KEY as CARRY_KEY

from .contracts import PLACE_SOURCES

KEY = "location_reassessment"
FIELDS = frozenset({"country", "province_state", "county", "city", "precise_location"})
PARENTS = frozenset({"country", "province_state", "county"})


def protected_keys(run) -> set[str]:
    """Human selections and directly source-backed parents remain constraints.

    A derived parent is dependent on its child, not an independent assertion.
    An authority identifier alone is not qualification: retain a directly
    stated parent only when it cites supporting gazetteer authority evidence.
    """
    protected = set()
    for name in (CARRY_KEY, "human_review_field_locks"):
        value = run.dependencies.get(name)
        if isinstance(value, (Mapping, list, tuple, set, frozenset)):
            protected.update(key for key in value if isinstance(key, str))
    marker = run.dependencies.get(KEY)
    if isinstance(marker, Mapping):
        marked = marker.get("protected", [])
        if isinstance(marked, list):
            protected.update(key for key in marked if isinstance(key, str) and key in FIELDS)
    evidence = {row.id: row for row in run.evidence}
    for key in PARENTS:
        value = run.fields.get(key)
        if (value is None or value.state != ValueState.SUPPORTED or value.layer not in {"settled", "verbatim"}
                or not (value.literal or any(value.verbatim_by_observation.values())) or not value.authority_id):
            continue
        if any(row is not None and row.kind in {"authority", "authority_selection"}
                and row.source in set(PLACE_SOURCES) - {"geolocate"}
                and row.locator == value.authority_id
                and value.evidence_relations.get(ident) in {"supports", "decides"}
                for ident in value.evidence_ids if (row := evidence.get(ident)) is not None):
            protected.add(key)
    # A retained human location's qualified ancestor remains its constraint;
    # reassessing siblings must not detach that parent from the locked child.
    while True:
        dependent = {key for key in PARENTS if (value := run.fields.get(key)) is not None
            and value.state == ValueState.SUPPORTED and value.layer == "derived"
            and set(value.derived_from) & protected}
        if dependent <= protected:
            break
        protected.update(dependent)
    return protected


def eligible_keys(run) -> set[str]:
    """Mutable declared locations; callers still enforce admission and limits."""
    from .step import field_keys, profile_of

    return FIELDS.intersection(field_keys(profile_of(run)), run.fields) - protected_keys(run)


def active_keys(run) -> set[str]:
    """An exact-attempt marker can only narrow the server's current eligibility."""
    marker = run.dependencies.get(KEY)
    if not isinstance(marker, Mapping):
        return set()
    attempt, fields = marker.get("attempt"), marker.get("fields")
    if (type(attempt) is not int or attempt < 1
            or attempt != run.attempts.get("field_research")
            or not isinstance(fields, list) or not fields
            or any(not isinstance(key, str) or key not in FIELDS for key in fields)
            or len(set(fields)) != len(fields)):
        return set()
    return set(fields) & eligible_keys(run)


def working_run(run):
    """Retained readings and candidates, without selected machine constraints."""
    keys = active_keys(run)
    if not keys:
        return run
    working = run.model_copy(deep=True)
    for key in keys:
        value = working.fields[key]
        working.fields[key] = value.model_copy(update={
            "state": ValueState.UNRESOLVED, "parsed": None, "normalized": None,
            "authority_id": None, "authority_identity": None, "layer": None,
            "derived_from": [],
        })
    return working


def commit(run, working, *, decisions) -> set[str]:
    """Apply a qualified family, or retain it whole and return unproved keys.

    Every source call/evidence row remains history even when support cannot be
    replaced. No usage, attempts, readings, pins or ledger state is copied back.
    """
    from .abbreviations import fits
    from .agreement import place_name

    keys = active_keys(run)
    old_ids = {row.id for row in run.evidence}
    fresh = {row.id: row for row in working.evidence if row.id not in old_ids}

    def qualified(key):
        value = working.fields[key]
        if value.state != ValueState.SUPPORTED:
            return False
        if value.layer == "derived":
            return bool(value.derived_from) and all(
                source in keys and working.fields[source].layer != "derived" and qualified(source)
                for source in value.derived_from)
        return any(ident in fresh and fresh[ident].kind == "authority"
            and fresh[ident].source in PLACE_SOURCES
            and value.evidence_relations.get(ident) in {"supports", "decides"}
            for ident in value.evidence_ids)

    unproved = set()
    for key in keys:
        previous = run.fields[key]
        if (previous.state != ValueState.SUPPORTED
                or previous.layer not in {"verbatim", "settled", "derived"}):
            continue
        if qualified(key):
            continue
        # A fresh, qualified administrative assignment can disprove the old
        # use of this exact label text at another level. Absence/outage alone
        # never removes support. Precise locality is not an administrative level.
        relocated = previous.literal and key != "precise_location" and any(
            other != key and other != "precise_location" and qualified(other)
            and working.fields[other].layer != "derived" and working.fields[other].literal
            and (name := (working.fields[other].normalized or working.fields[other].parsed
                or working.fields[other].literal))
            and (place_name(previous.literal) == place_name(name) or fits(previous.literal, name))
            for other in keys)
        if not relocated:
            unproved.add(key)
    run.evidence.extend(fresh.values())
    for name in ("tool_calls", "lookups"):
        existing = getattr(run, name)
        existing.extend(item for item in getattr(working, name) if item not in existing)
    run.findings.extend(finding for finding in working.findings if finding not in run.findings)
    if not unproved:
        for key in keys:
            run.fields[key] = working.fields[key]
    else:
        for key in keys:
            decisions[key] = {"rule": "location_reassessment_retained"}
    run.dependencies.pop(KEY, None)
    return unproved
