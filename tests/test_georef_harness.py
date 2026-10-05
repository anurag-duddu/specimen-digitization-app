"""Synthetic end-to-end geography; no network or production qualification claimed."""

import hashlib
import io
import json
import zipfile
from dataclasses import replace

import pytest

from specimen_digitization.application import georef_datasets as datasets
from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.georef_curated import Confirmation, PLACES
from specimen_digitization.research_harness import georeferencing as geo
from specimen_digitization.research_harness.contracts import (
    EvidenceItem, FieldKey, ResearchScope, SourceCoverageReceipt, SourceCoverageState,
    SourceQuery, SourceResult, SpecialistRequest, SpecialistRole,
)
from specimen_digitization.research_harness.prompts import resolve_prompt
from test_georef_elevation import geotiff


def zip_bytes(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, contents in files.items():
            archive.writestr(name, contents)
    return stream.getvalue()


def square(low, high):
    return [[[low, low], [high, low], [high, high], [low, high], [low, low]]]


def boundary(level, name, low, high):
    return json.dumps({"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {f"adm{level}_name": name, f"adm{level}_pcode": name,
                                           "adm1_name": "TestProvince", "adm1_pcode": "parent"},
        "geometry": {"type": "Polygon", "coordinates": square(low, high)},
    }]})


@pytest.fixture
def adapter(monkeypatch):
    row = ["1", "TestTown", "TestTown", "", ".5", ".5", "P", "PPL", "GT", "", "1", "2", "", "", "0", "", "", "", "2026-01-01"]
    blobs = {
        "geonames/GT/2026-09-24": zip_bytes({"GT.txt": "\t".join(row)}),
        "cod-ab/GT/2026-09-24": zip_bytes({"gtm_admin1.geojson": boundary(1, "TestProvince", .4, .6),
                                         "gtm_admin2.geojson": boundary(2, "TestTown", .498, .502)}),
        "copernicus-glo30/N00_00_E000_00": geotiff(
            [[100 * r + c for c in range(12)] for r in range(12)], north=.506, west=.494),
    }
    entries = []
    for key, blob in blobs.items():
        template = datasets.dataset(key) if key in datasets._BY_ID else datasets.MANIFEST[0]
        entry = replace(template, id=key, size=len(blob), sha256=hashlib.sha256(blob).hexdigest(),
                        source_url="https://example.org/synthetic", credit="Synthetic test fixture")
        monkeypatch.setitem(datasets._BY_ID, key, entry)
        entries.append(entry)
    monkeypatch.setattr(datasets, "MANIFEST", tuple(entries))
    monkeypatch.setattr(geo, "MANIFEST", tuple(entries))
    return geo.GeoreferencingAdapter(lambda entry: blobs[entry.id]), blobs


def validation(**candidate_changes):
    evidence = EvidenceItem(id="synthetic-validation", kind="qualified_source", source_id="geolocate",
                            locator="https://example.org/synthetic", response_digest="0" * 64,
                            source_version="synthetic", publisher_assertion_id="synthetic")
    candidate = {"match_name": "TestTown", "decimal_latitude": .5, "decimal_longitude": .5,
                 "authority_id": "geolocate:synthetic", "field_key": "city", "value": "TestTown", **candidate_changes}
    return SourceResult(status=LookupStatus.SUCCESS, evidence=(evidence,),
                        candidate_json=(json.dumps(candidate),),
                        coverage=SourceCoverageReceipt(source_id="geolocate", field_key=FieldKey.CITY,
                            state=SourceCoverageState.SEARCHED, source_version="synthetic",
                            coverage_limit="synthetic test", reason="synthetic test"))


def settled(field_key=FieldKey.CITY, value="TestTown"):
    return geo.SettledLocationInput(field_key, value, ("review:1",), 4, "review-decision:1")


def derive(adapter, **changes):
    arguments = dict(country="GT", validation=validation(), settled_inputs=(settled(),),
                     requested_fields=(FieldKey.PROVINCE_STATE, FieldKey.COUNTY, *sorted(geo.ELEVATION_FIELDS)),
                     verbatim_locality="TestTown", label_has_elevation=False, tool_call_id="synthetic-derive")
    return adapter.derive_rest(**(arguments | changes))


def request():
    pin = "0" * 64
    scope = ResearchScope(organization_id="org", collection_id="col", specimen_id="specimen",
                          job_id="job", generation=1, sensitive=False, input_digest=pin, profile_digest=pin)
    prompt = resolve_prompt(SpecialistRole.GEOGRAPHY, profile_digest=pin, source_registry_digest=pin,
                            toolset_digest=pin, model_route="test", output_schema_digest=pin)
    return SpecialistRequest(scope=scope, role=SpecialistRole.GEOGRAPHY,
                             field_keys=(FieldKey.CITY,), prompt=prompt)


def test_historian_candidates_are_evidenced_and_do_not_self_settle(adapter):
    tool, _ = adapter
    result = tool.history_query(request(), SourceQuery(source_id=geo.HISTORY_SOURCE, field_key=FieldKey.CITY,
                              query_text='{"country":"GT","name":"TestTown","collected_on":"1946"}'))
    assert result.status == LookupStatus.SUCCESS
    candidate = json.loads(result.candidate_json[0])
    assert candidate["settlement_allowed"] is False
    assert candidate["validation_required"] == "geolocate"
    assert candidate["temporal_status"] == "undated"
    assert result.evidence[0].response_digest == tool._dump("GT")[0].sha256


def test_curator_confirmation_preserves_crosswalk_and_modern_validation_requirement(adapter, monkeypatch):
    tool, _ = adapter
    entry = replace(PLACES[0], confirmation=Confirmation("curator", "2026-10-04", "synthetic-owner-record"))
    monkeypatch.setattr(geo, "curated_place", lambda country, name: entry)
    result = tool.history_query(request(), SourceQuery(source_id=geo.HISTORY_SOURCE, field_key=FieldKey.CITY,
                              query_text='{"country":"PH","name":"Mount McKinley"}'))
    candidate = json.loads(result.candidate_json[0])
    assert result.status == LookupStatus.SUCCESS and candidate["confirmed"] is True
    assert candidate["hypothesis"] == "Mount Talomo" and candidate["settlement_allowed"] is False
    assert candidate["validation_required"] == "geolocate"


def test_verified_polygon_to_radius_containment_and_dem_to_editable_proposals(adapter):
    tool, _ = adapter
    result = derive(tool)
    assert result.status == LookupStatus.SUCCESS
    assert 300 < result.georeference.uncertainty_m < 320
    assert result.georeference.latitude == pytest.approx(.5)
    values = {p.field_key: p for p in result.proposals}
    assert values[FieldKey.PROVINCE_STATE].value == "TestProvince"
    assert FieldKey.COUNTY not in values
    assert set(geo.ELEVATION_FIELDS) <= values.keys()
    assert float(values[FieldKey.ELEVATION_FROM_M].value) < float(values[FieldKey.ELEVATION_TO_M].value)
    assert float(values[FieldKey.ELEVATION_FROM_FT].value) * .3048 == pytest.approx(
        float(values[FieldKey.ELEVATION_FROM_M].value))
    for item in values.values():
        assert item.value_layer == "derived"
        assert item.input_revisions == (("city", 4),)
        assert item.tool_call_id == "synthetic-derive" and "review:1" in item.evidence_ids
    envelope = geo.derivation_source_result(result, FieldKey.PROVINCE_STATE)
    assert envelope.status == LookupStatus.SUCCESS
    assert json.loads(envelope.candidate_json[0])["georeference"]["uncertainty_m"] > 300


@pytest.mark.parametrize("has_elevation", [True, None])
def test_stated_or_unknown_elevation_is_never_replaced_by_dem(adapter, has_elevation):
    tool, blobs = adapter
    del blobs["copernicus-glo30/N00_00_E000_00"]  # must not even try to read
    result = derive(tool, label_has_elevation=has_elevation)
    assert not any(proposal.field_key in geo.ELEVATION_FIELDS for proposal in result.proposals)
    assert any("cannot replace" in reason for _, reason in result.unresolved)


def test_unavailable_dem_keeps_georeference_and_explains_operational_gap(adapter):
    tool, blobs = adapter
    del blobs["copernicus-glo30/N00_00_E000_00"]
    result = derive(tool)
    assert result.georeference is not None
    assert not any(p.field_key in geo.ELEVATION_FIELDS for p in result.proposals)
    assert geo.derivation_source_result(result, FieldKey.ELEVATION_FROM_M).status == LookupStatus.PROVIDER


def test_complete_valid_dem_with_missing_spatial_coverage_is_no_match(adapter, monkeypatch):
    tool, _ = adapter
    monkeypatch.setattr(geo, "MANIFEST", ())
    result = derive(tool)
    envelope = geo.derivation_source_result(result, FieldKey.ELEVATION_FROM_M)
    assert envelope.status == LookupStatus.NO_MATCH
    assert "coverage" in envelope.coverage.reason.lower()


def test_visible_label_elevation_overrides_an_incorrect_absence_flag(adapter):
    tool, blobs = adapter
    del blobs["copernicus-glo30/N00_00_E000_00"]
    result = derive(tool, verbatim_locality="TestTown, 4800 ft", label_has_elevation=False)
    assert not any(p.field_key in geo.ELEVATION_FIELDS for p in result.proposals)
    assert any("cannot replace" in reason for _, reason in result.unresolved)


def test_digest_mismatch_is_not_a_no_match(adapter):
    tool, blobs = adapter
    blobs["geonames/GT/2026-09-24"] += b"corruption"
    result = tool.history_query(request(), SourceQuery(source_id=geo.HISTORY_SOURCE, field_key=FieldKey.CITY,
                              query_text='{"country":"GT","name":"TestTown"}'))
    assert result.status == LookupStatus.PROVIDER
    assert result.coverage.state == SourceCoverageState.FAILED


def test_contradictory_settled_inputs_and_unconfirmed_mckinley_do_not_derive(adapter):
    tool, _ = adapter
    result = derive(tool, settled_inputs=(settled(), settled(FieldKey.PROVINCE_STATE, "Elsewhere")))
    assert result.status == LookupStatus.AMBIGUOUS and not result.proposals
    result = derive(tool, country="PH", verbatim_locality="E. slope Mt. McKinley, Davao Prov., Mindanao, P.I.")
    assert result.status == LookupStatus.AMBIGUOUS and "G36" in result.reason


def test_validator_point_cannot_supply_uncertainty_and_model_radius_is_ignored(adapter):
    tool, _ = adapter
    result = derive(tool, validation=validation(uncertaintyRadiusMeters=1, radius_km=1))
    assert result.georeference.uncertainty_m > 300
    result = derive(tool, settled_inputs=(settled(FieldKey.PRECISE_LOCATION, "TestTown"),))
    assert result.georeference is None and "point alone" in result.reason


def test_validation_must_confirm_the_current_anchor_field_and_value(adapter):
    tool, _ = adapter
    result = derive(tool, validation=validation(value="Elsewhere", field_key="country"))
    assert result.status == LookupStatus.AMBIGUOUS
    assert not result.proposals and result.georeference is None


@pytest.mark.parametrize("status", [LookupStatus.TIMEOUT, LookupStatus.PROVIDER,
                                   LookupStatus.RATE_LIMITED, LookupStatus.AMBIGUOUS])
def test_validator_failures_are_not_downgraded_to_no_match(adapter, status):
    tool, _ = adapter
    result = derive(tool, validation=validation().model_copy(update={"status": status}))
    assert result.status == status and result.georeference is None
    envelope = geo.derivation_source_result(result, FieldKey.PROVINCE_STATE)
    assert envelope.coverage.state != SourceCoverageState.SEARCHED


def test_invalid_history_query_is_not_recorded_as_a_search(adapter):
    tool, _ = adapter
    result = tool.history_query(request(), SourceQuery(source_id=geo.HISTORY_SOURCE,
                               field_key=FieldKey.CITY, query_text="not JSON"))
    assert result.status == LookupStatus.POLICY
    assert result.coverage.state == SourceCoverageState.NOT_ATTEMPTED


def test_unresolved_field_keeps_computed_georeference_in_tool_result(adapter):
    tool, _ = adapter
    result = derive(tool, requested_fields=(FieldKey.COUNTY,))
    envelope = geo.derivation_source_result(result, FieldKey.COUNTY)
    assert envelope.status == LookupStatus.NO_MATCH
    metadata = json.loads(envelope.candidate_json[0])
    assert metadata["settlement_allowed"] is False and "value" not in metadata
    assert metadata["georeference"]["uncertainty_m"] > 300


def test_computed_evidence_binds_source_coverage_and_preserves_provider_evidence(adapter):
    tool, _ = adapter
    result = derive(tool)
    envelope = geo.derivation_source_result(result, FieldKey.PROVINCE_STATE)
    [computed] = [item for item in envelope.evidence if item.source_id == geo.SPATIAL_SOURCE]
    assert computed.kind == "computed_derivation_result"
    assert computed.source_id == envelope.coverage.source_id
    assert computed.source_version == envelope.coverage.source_version == geo.VERSION
    assert computed.id in envelope.coverage.receipt_ids
    assert computed.id in json.loads(envelope.candidate_json[0])["evidence_ids"]
    assert "not a provider response" in computed.excerpt
    assert tuple(item for item in envelope.evidence if item != computed) == result.evidence
    assert geo.derivation_source_result(result, FieldKey.PROVINCE_STATE) == envelope
    # All per-field envelopes refer to the same complete multi-field computation.
    other = geo.derivation_source_result(result, FieldKey.ELEVATION_FROM_M)
    assert computed in other.evidence


@pytest.mark.parametrize("changed", ["input_revision", "dataset", "tool_call", "source_evidence"])
def test_computed_source_digest_changes_with_derivation_custody(adapter, changed):
    tool, _ = adapter
    result = derive(tool)
    if changed == "source_evidence":
        different = replace(result, evidence=(result.evidence[0].model_copy(update={"response_digest": "1" * 64}),
                                               *result.evidence[1:]))
    else:
        first, *rest = result.proposals
        patch = {"input_revision": {"input_revisions": (("city", 5),)},
                 "dataset": {"dataset_ids": ("changed-dataset",)},
                 "tool_call": {"tool_call_id": "different-tool-call"}}[changed]
        different = replace(result, proposals=(replace(first, **patch), *rest))
    def computation(value):
        envelope = geo.derivation_source_result(value, FieldKey.PROVINCE_STATE)
        return next(item.response_digest for item in envelope.evidence if item.source_id == geo.SPATIAL_SOURCE)
    assert computation(result) != computation(different)


def test_input_revisions_and_duplicate_field_pins_are_required(adapter):
    tool, _ = adapter
    with pytest.raises(ValueError, match="settled value"):
        geo.SettledLocationInput(FieldKey.CITY, "TestTown", (), 1, "review:1")
    with pytest.raises(ValueError, match="one current revision"):
        derive(tool, settled_inputs=(settled(), settled()))
