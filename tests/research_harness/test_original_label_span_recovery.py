"""Deterministic original spans, with synthetic readers and no provider calls."""

import pytest

from specimen_digitization.research_harness.contracts import FieldKey, SpecialistRole
from specimen_digitization.research_harness.evidence import (
    elevation_resolutions, settle_elevation, temporal_resolutions, validate_resolution,
)

from test_organiser_raw_reading_evidence import build, candidates, request_for, two_labels


def date_fixture(first="3 sept. '46", second="3 Sept. '46", *, extra="", context=True):
    texts = [f"Island\nA. Example\n{date}{extra}" for date in (first, second)]
    answers = [("date_visited_from", name, date, date)
        for name, date in zip(("2A", "2B"), (first, second))]
    if context:
        answers += [(key, name, value, value) for key, value in
            (("country", "Island"), ("collectors", "A. Example")) for name in ("2A", "2B")]
    return build(two_labels(a=texts[0], b=texts[1]), answers)


def test_month_case_agreement_keeps_each_original_and_does_not_rewrite_ordinary_value():
    built = date_fixture()
    original = built.specimen.run.fields["date_visited_from"].model_dump_json()
    rows = candidates(built, "date_visited_from")
    assert {row.literal for row in rows} == {"3 sept. '46", "3 Sept. '46"}
    grounded = [row for row in rows if row.status == "grounded"]
    assert len(grounded) == 1
    request = request_for(built, SpecialistRole.TEMPORAL)
    first, last = temporal_resolutions(request, event_id=grounded[0].event_id)
    assert first.value.literal == grounded[0].literal
    assert first.value.parsed == last.value.parsed == "1946-09-03"
    assert first.value.precision == "day" and first.value.century_rule
    assert last.value_layer == "derived" and last.derivation.rule_id == "G44"
    assert built.specimen.run.fields["date_visited_from"].model_dump_json() == original
    assert {row.observation_text for row in request.fragments if row.region_id == grounded[0].region_id} == {
        "Island\nA. Example\n3 sept. '46", "Island\nA. Example\n3 Sept. '46"}
    quoted = {row.id: row.excerpt for row in built.specimen.run.evidence}
    assert all(grounded[0].literal in quoted[key] for key in first.evidence_ids)


@pytest.mark.parametrize(("first", "second", "extra", "context"), (
    ("3 sept. '46", "4 Sept. '46", "", True),
    ("3 sept. '46", "3 Sept. '48", "", True),
    ("4-5-48", "4-5-48", "", True),
    ("3 sept. '46", "3 Sept. '46", "\nslide preparation", True),
    ("3 sept. '46", "3 Sept. '46", "\n4 sept. '46", True),
    ("3 sept. '46", "3 Sept. '46", "", False),
))
def test_calendar_event_and_independent_quote_refusals_remain(first, second, extra, context):
    built = date_fixture(first, second, extra=extra, context=context)
    assert not [row for row in candidates(built, "date_visited_from") if row.status == "grounded"]


def elevation_fixture(first="Mossy forest 6400'", second=None, *, quote=None, literal="6400"):
    second = first if second is None else second
    return build(two_labels(a=first, b=second), [
        ("elevation_from_ft", name, literal, quote if quote is not None else line)
        for name, line in zip(("2A", "2B"), (first, second)) if literal in line])


def test_numeric_hint_recovers_only_its_same_reading_exact_quoted_footmark():
    built = elevation_fixture()
    original = built.specimen.run.fields["elevation_from_ft"].model_dump_json()
    rows = candidates(built, "elevation_from_ft")
    assert {row.literal for row in rows} == {"6400", "6400'"}
    assert all(row.status == "located" for row in rows if row.literal == "6400")
    [grounded] = [row for row in rows if row.status == "grounded"]
    assert grounded.literal == "6400'"
    request = request_for(built, SpecialistRole.MEASUREMENT)
    assembly = next(row for row in request.assemblies if row.id == grounded.assembly_id)
    fragment = next(row for row in request.fragments if row.id in assembly.fragment_ids)
    assert fragment.observation_text[fragment.start:fragment.end] == "6400'"
    settled = settle_elevation(request, assembly_ids=(assembly.id,))
    assert settled.event_id == assembly.event_id and settled.scope == request.scope
    assert settled.fragment_ids == assembly.fragment_ids
    assert settled.evidence_ids == assembly.evidence_ids
    values = {row.field_key: row for row in elevation_resolutions(settled)}
    assert values[FieldKey.ELEVATION_FROM_FT].value.literal == "6400'"
    assert values[FieldKey.ELEVATION_FROM_FT].value.parsed == "6400"
    assert values[FieldKey.ELEVATION_FROM_FT].value.normalized == "6400.00"
    assert values[FieldKey.ELEVATION_FROM_M].value.normalized == "1950.72"
    assert all(validate_resolution(request, row) == row for row in values.values())
    assert set(values[FieldKey.ELEVATION_FROM_FT].value.verbatim_by_observation.values()) == {"Mossy forest 6400'"}
    assert built.specimen.run.fields["elevation_from_ft"].model_dump_json() == original
    quoted = {row.id: row.excerpt for row in built.specimen.run.evidence}
    assert all("6400'" in quoted[key] for key in grounded.evidence_ids)


@pytest.mark.parametrize(("first", "second", "quote"), (
    ("Mossy forest 6400", None, None),
    ("Mossy forest 6400''", None, None),
    ("Mossy forest 6400' extra", None, None),
    ("Mossy forest 6400'", "Mossy forest 6401'", None),
    ("Mossy forest 6400'", "Mossy forest", None),
    ("Mossy forest ~6400'", None, None),
    ("Mossy forest 6400'", None, "Mossy forest 6400"),
    ("Mossy forest 16400'", None, None),
))
def test_footmark_recovery_never_discards_missing_quote_conflict_or_adjacent_tokens(first, second, quote):
    built = elevation_fixture(first, second, quote=quote)
    assert not [row for row in candidates(built, "elevation_from_ft") if row.status == "grounded"]
