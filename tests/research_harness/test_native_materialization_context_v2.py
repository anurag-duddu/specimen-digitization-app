"""Source-authored native normalization boundaries; integrated execution UNRUN."""
import copy

import pytest

from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.native_materialization_context_v2 import (
    _normalized_native_row, canonical_prior_projection_v2)
from specimen_digitization.research_harness.native_canonical import CANONICAL_KEYS


OUTER = {"organizationId":"native-org", "collectionId":"native-collection"}


def test_native_timestamp_normalization_retains_original_row_and_producer_spelling():
    expected = {**OUTER, "id":"native-row", "capturedAt":"2026-10-01T10:20:30Z", "literalText":"Peru"}
    raw = {**expected, "capturedAt":"2026-10-01T05:20:30.000000-05:00", "createdAt":"2026-10-01T12:00:00Z"}
    before = copy.deepcopy(raw)
    assert _normalized_native_row(raw, expected, OUTER) == expected
    assert raw == before


@pytest.mark.parametrize("changed", [
    {"capturedAt":"2026-10-01T10:20:31Z"},
    {"capturedAt":"2026-10-01T10:20:30"},
    {"capturedAt":True},
    {"organizationId":"foreign-org"},
    {"literalText":"Ecuador"},
    {"unrecognizedScientificColumn":None},
])
def test_native_write_normalization_denies_scientific_scope_or_wire_drift(changed):
    expected = {**OUTER, "id":"native-row", "capturedAt":"2026-10-01T10:20:30Z", "literalText":"Peru"}
    raw = {**expected, **changed, "createdAt":"2026-10-01T12:00:00Z"}
    before = copy.deepcopy(raw)
    with pytest.raises(PublicationUnavailable):
        _normalized_native_row(raw, expected, OUTER)
    assert raw == before


def test_normalization_does_not_treat_arbitrary_scientific_strings_as_timestamps():
    expected = {**OUTER, "id":"native-row", "literalText":"2026-10-01T10:20:30Z"}
    raw = {**expected, "literalText":"2026-10-01T05:20:30-05:00"}
    with pytest.raises(PublicationUnavailable):
        _normalized_native_row(raw, expected, OUTER)


def test_native_full_row_order_and_public_field_order_have_exact_same_scientific_projection():
    public = [{"id":"row:"+field, "recordVersionId":"current-native-record", "candidateId":None,
        "fieldKey":field, "state":"absent", "fieldGroup":"native-group"} for field in sorted(CANONICAL_KEYS)]
    native = [{**OUTER, **row, "createdAt":"2026-10-01T10:20:30Z"} for row in reversed(public)]
    before = copy.deepcopy(native)
    assert canonical_prior_projection_v2(native,"current-native-record") == tuple(public)
    assert canonical_prior_projection_v2(public,"current-native-record") == tuple(public)
    assert native == before


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "unknown_column"])
def test_projection_order_normalization_cannot_erase_duplicate_missing_or_scientific_rows(mutation):
    rows = [{"id":"row:"+field, "recordVersionId":"current-native-record", "candidateId":None,
        "fieldKey":field, "state":"absent", "fieldGroup":"native-group"} for field in sorted(CANONICAL_KEYS)]
    if mutation == "duplicate":
        rows[-1] = copy.deepcopy(rows[0])
    elif mutation == "missing":
        rows.pop()
    else:
        rows[0]["newScientificAuthority"] = "unapproved"
    with pytest.raises(PublicationUnavailable):
        canonical_prior_projection_v2(rows,"current-native-record")
