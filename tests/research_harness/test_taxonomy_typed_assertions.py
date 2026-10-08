"""Explicit typewritten taxon markers retain exact raw custody; all sources synthetic."""

import pytest

from specimen_digitization.research_harness.evidence import validate_resolution
from specimen_digitization.research_harness.taxonomy import (
    available_taxonomy_settlement, gbif_query_params, taxonomy_stop_defect,
)

from test_taxon_input_reconciliation import request_for, resolution_for, result_for
from test_taxonomy_reader_negatives import negative_for
from test_taxonomy_source_context import context, query, reading_request


@pytest.mark.parametrize("marker", ("taxon", "Taxon", "TAXON"))
def test_explicit_named_taxon_line_cannot_stop_before_research(marker):
    request = reading_request(("label", "raw", f"{marker}: Danaus"))
    assert "explicitly evidenced named taxon" in taxonomy_stop_defect(request, ())


@pytest.mark.parametrize("marker", ("taxon", "Taxon", "TAXON"))
def test_typed_marker_anchors_unanimous_original_context(marker):
    text = f"{marker}: Danaus plexippus\norder: Lepidoptera\nfamily: Nymphalidae"
    request = reading_request(("label", "raw-a", text), ("label", "raw-b", text))
    before = request.model_dump_json()
    assert context(gbif_query_params(request, query())) == {
        "order": "Lepidoptera", "family": "Nymphalidae"}
    assert request.model_dump_json() == before


def test_typed_reader_and_negative_alternative_can_settle_without_rewriting_raw():
    literal = "Taxon: Epipocus"
    request = request_for((("raw", literal, "raw_reading"),
        ("other", "TAXON: Epipsocus", "decided_transcript")))
    positive = result_for(request, "Epipocus")
    results = (positive, negative_for(request, "Epipsocus"))
    resolution = resolution_for(request, (positive,), literal=literal)
    before = request.model_dump_json()
    assert validate_resolution(request, resolution, results) == resolution
    assert available_taxonomy_settlement(request, results)
    assert request.model_dump_json() == before
    assert resolution.value.literal == literal
    assert resolution.value.verbatim_by_observation == {"raw": literal}


@pytest.mark.parametrize("marker", ("taxon", "Taxon", "TAXON"))
def test_typed_bare_morphocode_still_requires_no_query_or_invented_genus(marker):
    request = reading_request(("label", "raw", f"{marker}: sp.30"))
    assert taxonomy_stop_defect(request, ()) is None
    assert not available_taxonomy_settlement(request, ())


def test_misfiled_marker_span_inside_city_line_is_not_taxonomic_context():
    text = "city: taxon: Danaus"
    request = reading_request(("label", "raw", text))
    line = request.fragments[0]
    span = line.model_copy(update={"id": "misfiled-span", "start": len("city: "),
        "literal": "taxon: Danaus", "granularity": "span"})
    request = request.model_copy(update={"fragments": (*request.fragments, span)})
    assert taxonomy_stop_defect(request, ()) is None
    assert context(gbif_query_params(request, query("Danaus"))) == {}
