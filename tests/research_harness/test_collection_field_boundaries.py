"""Native field markers bound collection values; fixtures use retained raw quotes."""

import pytest

from specimen_digitization.research_harness.collection import (
    collection_resolution, qualify_collection_span,
)
from specimen_digitization.research_harness.contracts import FieldKey, WorkState
from specimen_digitization.research_harness.evidence import EvidenceError, validate_resolution

from test_collection_qualification import collection_request, retained, span


@pytest.mark.parametrize(("key", "text", "literal"), (
    (FieldKey.HABITAT, "country: oak woodland", "oak woodland"),
    (FieldKey.HABITAT, "precise_location: oak woodland", "oak woodland"),
    (FieldKey.HABITAT, "taxon: oak woodland", "oak woodland"),
    (FieldKey.HABITAT, "collectors: oak woodland", "oak woodland"),
    (FieldKey.COLLECTION_METHOD, "date_identified: light trap", "light trap"),
    (FieldKey.COLLECTION_METHOD, "date_visited_from: light trap", "light trap"),
    (FieldKey.FMNH_INS_NUMBER, "elevation_from_ft: FMNH INS 0012345", "FMNH INS 0012345"),
))
def test_native_other_field_marker_cannot_be_overridden_by_a_collection_hint(key, text, literal):
    with pytest.raises(EvidenceError, match="another marked field or event"):
        qualify_collection_span(key, span(text, literal))


@pytest.mark.parametrize(("key", "text", "expected"), (
    (FieldKey.FMNH_INS_NUMBER, "Catalog number: 0012345\n  taxon: Epipocus", "0012345"),
    (FieldKey.COLLECTION_CODE, "Collection code: AB 12\n  country: Guatemala", "AB 12"),
    (FieldKey.HABITAT, "Habitat: oak\n  woodland margin\n  country: Guatemala", "oak\n  woodland margin"),
    (FieldKey.HABITAT, "Habitat: oak woodland\n  Locality: Yepocapa", "oak woodland"),
    (FieldKey.COLLECTION_METHOD, "Method: light trap\n  collectors: A. Example", "light trap"),
))
def test_multiline_recovery_stops_at_an_indented_other_field_marker(key, text, expected):
    request = collection_request(retained(text))
    before = request.model_dump_json()
    result = collection_resolution(request, key)
    assert result.work_state == WorkState.RESOLVED
    assert result.value.parsed == expected
    assert validate_resolution(request, result) == result
    assert request.model_dump_json() == before
    assert set(result.value.verbatim_by_observation.values()) == {text}


def test_empty_collection_marker_does_not_consume_an_explicit_different_field():
    text = "Habitat:\n  country: Guatemala\nMethod: light trap"
    request = collection_request(retained(text))
    habitat = collection_resolution(request, FieldKey.HABITAT)
    method = collection_resolution(request, FieldKey.COLLECTION_METHOD)
    assert habitat.work_state == WorkState.WAITING_POLICY
    assert habitat.value.parsed is None and not habitat.evidence_ids
    assert method.work_state == WorkState.RESOLVED
    assert method.value.parsed == "light trap"
