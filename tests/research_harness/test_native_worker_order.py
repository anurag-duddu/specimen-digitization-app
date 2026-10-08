"""The worker offers roster roles in order, with derived fields after their sources.

The journal lists fields in key order, so elevation_from_ft comes before
elevation_from_m. Within a role the source must publish first; an actual
cross-role dependency takes precedence over roster order. Offline: the runtime
is test_production_bridge's recording stand-in.
"""
from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.research_harness.contracts import (
    DependencyPin, FieldKey, FieldResolution, WorkState, digest,
)

from test_production_bridge import TAXON, checkpoint, publish, thread, waiting


def resolved(key, *sources):
    return checkpoint(FieldResolution(field_key=key, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, literal="180", evidence_ids=["e-label"],
            evidence_relations={"e-label": "supports"}),
        evidence_ids=("e-label",), reason="synthetic resolved work",
        dependencies=tuple(DependencyPin(field_key=source.field_key, revision=source.revision,
            digest=digest(source.resolution)) for source in sources)))


def test_a_derived_field_is_offered_after_its_source(monkeypatch):
    from_m, to_m = resolved(FieldKey.ELEVATION_FROM_M), resolved(FieldKey.ELEVATION_TO_M)
    from_ft, to_ft = resolved(FieldKey.ELEVATION_FROM_FT, from_m), resolved(FieldKey.ELEVATION_TO_FT, to_m)
    county = waiting(FieldKey.COUNTY, WorkState.WAITING_SOURCE)
    # Key order, as the journal loads them.
    typed = (county, from_ft, from_m, to_ft, to_m, TAXON)
    runtime, outcome = publish(monkeypatch, typed, thread(*typed))
    # Measurement publishes each source before its derived feet value. With
    # no pending work, the genuine unsent Taxon carrier publishes last so its
    # native receipt binds final whole-record progress.
    assert runtime.prepared == [FieldKey.ELEVATION_FROM_M, FieldKey.ELEVATION_TO_M,
        FieldKey.ELEVATION_FROM_FT, FieldKey.ELEVATION_TO_FT, FieldKey.TAXON]
    assert len(outcome.publication_receipt_ids) == 5 and "native-county" not in outcome.checkpoint_ids


def test_a_dependency_outside_the_loaded_checkpoints_keeps_roster_order(monkeypatch):
    absent = resolved(FieldKey.DATE_VISITED_FROM)
    derived = resolved(FieldKey.DATE_VISITED_TO, absent)
    runtime, _ = publish(monkeypatch, (derived, TAXON), thread(derived, TAXON))
    # An absent source does not reorder loaded dependencies; the terminal
    # Taxon progress carrier is still reserved for the end of this pass.
    assert runtime.prepared == [FieldKey.DATE_VISITED_TO, FieldKey.TAXON]


def test_a_loaded_cross_role_dependency_precedes_its_earlier_roster_role(monkeypatch):
    country = resolved(FieldKey.COUNTRY)
    taxon = resolved(FieldKey.TAXON, country)
    runtime, outcome = publish(monkeypatch, (taxon, country), thread(taxon, country))
    assert runtime.prepared == [FieldKey.COUNTRY, FieldKey.TAXON]
    assert len(outcome.publication_receipt_ids) == 2
