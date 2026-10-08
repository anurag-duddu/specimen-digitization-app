"""Taxonomy query context uses exact retained readings, never inferred lineage.

Pure adapter cases plus a synthetic GBIF response through the real disposable
SQLite capture broker. No model, live provider, or production connector is used.
"""

import asyncio
import hashlib
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from specimen_digitization.application.lookup import COL_XR
from specimen_digitization.research_harness.contracts import (
    FieldKey, LookupStatus, SourceFragment, SourceQuery, SpecialistRequest,
    SpecialistRole, digest,
)
from specimen_digitization.research_harness.persistence import (
    DurableEffectBroker, ImmutableFileBlobs, ResearchStore, SqliteStateBackend,
)
from specimen_digitization.research_harness.source_capture_v2 import CaptureSourceBrokerV2
from specimen_digitization.research_harness.sources import FixtureSourceTransport
from specimen_digitization.research_harness.taxonomy import gbif_query_params

from test_source_capture_v2 import make_capture_rig, saved_envelope
from test_specialist_feedback import graph_request


def reading_request(*readings, base=None, unreadable=()):
    """Each tuple is (label/region, immutable observation, complete label text)."""
    original = base or graph_request(SpecialistRole.TAXONOMY, FieldKey.TAXON, "Danaus")
    fragments = []
    for region, observation, text in readings:
        offset = 0
        for order, line in enumerate(text.splitlines(keepends=True)):
            literal = line.rstrip("\r\n")
            fragments.append(SourceFragment(
                id=f"{region}:{observation}:{order}", scope=original.scope,
                asset_id="fixture-asset", asset_generation="1", asset_digest=digest("fixture-asset"),
                label_id=region, region_id=region, observation_id=observation,
                reader=observation, model_id="fixture", prompt_digest=digest("fixture-reader"),
                observation_text=text, observation_digest=hashlib.sha256(text.encode()).hexdigest(),
                start=offset, end=offset + len(literal), literal=literal, order=order,
                granularity="line", input_source="raw_reading",
                unreadable=(observation, order) in unreadable,
            ))
            offset += len(line)
    return SpecialistRequest.model_validate({**original.model_dump(mode="json"),
        "fragments": [item.model_dump(mode="json") for item in fragments],
        "assemblies": [], "events": [], "relations": [], "evidence": [],
        "organiser_candidates": []})


def query(text="Danaus plexippus"):
    return SourceQuery(source_id="gbif", field_key=FieldKey.TAXON, query_text=text)


def context(params):
    return {key: params[key] for key in ("order", "family") if key in params}


@pytest.mark.parametrize(("literal", "scientific", "rank"), (
    ("Danaus plexippus", "Danaus plexippus", "SPECIES"),
    ("Danaus", "Danaus", "GENUS"),
    ("Danaus sp.30", "Danaus", "GENUS"),
))
def test_ordinary_species_genus_and_morphospecies_preserve_name_and_rank(literal, scientific, rank):
    request = reading_request(("label", "raw", literal))
    before = request.model_dump_json()
    assert gbif_query_params(request, query(literal)) == {
        "scientificName": scientific, "taxonRank": rank, "kingdom": "Animalia",
        "class": "Insecta", "checklistKey": COL_XR, "verbose": "true",
    }
    assert request.model_dump_json() == before


@pytest.mark.parametrize("literal", ("Danaus plexippus", "Danaus", "Danaus sp.30"))
def test_explicit_unanimous_order_and_family_are_sent_at_the_label_rank(literal):
    text = f"{literal}\norder: Lepidoptera\nfamily: Nymphalidae"
    request = reading_request(("label", "raw-a", text), ("label", "raw-b", text))
    assert context(gbif_query_params(request, query(literal))) == {
        "order": "Lepidoptera", "family": "Nymphalidae"}


def test_exact_scientific_name_projection_retains_the_morphocode_context():
    text = "Danaus sp.30\nfamily: Nymphalidae\norder: Lepidoptera"
    request = reading_request(("label", "raw-a", text), ("label", "raw-b", text))
    assert context(gbif_query_params(request, query("Danaus"))) == {
        "order": "Lepidoptera", "family": "Nymphalidae"}


def test_explicit_taxon_field_line_can_anchor_context():
    text = "taxon: Danaus plexippus\norder: Lepidoptera\nfamily: Nymphalidae"
    request = reading_request(("label", "raw-a", text), ("label", "raw-b", text))
    assert context(gbif_query_params(request, query())) == {
        "order": "Lepidoptera", "family": "Nymphalidae"}


@pytest.mark.parametrize("other", (
    "Danaus plexippus\norder: Lepidoptera",  # missing family
    "Danaus plexippus\norder: Lepidoptera\nfamily: Pieridae",  # disagreement
))
def test_missing_or_conflicting_reader_family_does_not_erase_unanimous_order(other):
    first = "Danaus plexippus\norder: Lepidoptera\nfamily: Nymphalidae"
    request = reading_request(("label", "raw-a", first), ("label", "raw-b", other))
    assert context(gbif_query_params(request, query())) == {"order": "Lepidoptera"}


def test_unreadable_context_is_omitted_without_inventing_a_reader_consensus():
    text = "Danaus plexippus\norder: Lepidoptera\nfamily: Nymphalidae"
    request = reading_request(("label", "raw-a", text), ("label", "raw-b", text),
        unreadable=(("raw-b", 2),))
    assert context(gbif_query_params(request, query())) == {"order": "Lepidoptera"}


def test_competing_explicit_values_in_one_reading_are_not_context():
    text = "Danaus plexippus\norder: Lepidoptera\nfamily: Nymphalidae\nfamily: Pieridae"
    request = reading_request(("label", "raw-a", text), ("label", "raw-b", text))
    assert context(gbif_query_params(request, query())) == {"order": "Lepidoptera"}


def test_unkeyed_lineage_words_and_locality_supply_no_context():
    text = "Danaus plexippus\nLepidoptera\nNymphalidae\nlocality: family: Pieridae"
    request = reading_request(("label", "raw-a", text), ("label", "raw-b", text))
    assert context(gbif_query_params(request, query())) == {}


def test_context_on_an_unrelated_label_is_not_sent():
    request = reading_request(("taxon-label", "raw-a", "Danaus plexippus"),
        ("taxon-label", "raw-b", "Danaus plexippus"),
        ("other-label", "other-a", "Papilio glaucus\norder: Lepidoptera\nfamily: Papilionidae"))
    assert context(gbif_query_params(request, query())) == {}


def test_context_without_an_exact_query_assertion_is_not_sent():
    request = reading_request(("label", "raw-a", "Papilio glaucus\nfamily: Papilionidae"))
    assert context(gbif_query_params(request, query())) == {}


def test_species_assertion_does_not_supply_context_for_a_truncated_genus_query():
    request = reading_request(("label", "raw-a", "Danaus plexippus\nfamily: Nymphalidae"))
    assert context(gbif_query_params(request, query("Danaus"))) == {}


def test_a_rank_span_inside_a_locality_line_is_not_higher_taxonomy():
    text = "Danaus plexippus\nlocality: family: Nymphalidae"
    request = reading_request(("label", "raw-a", text))
    line = request.fragments[1]
    start = text.index("family:")
    span = line.model_copy(update={"id": "misassigned-family-span", "literal": "family: Nymphalidae",
        "start": start, "end": len(text), "granularity": "span"})
    request = request.model_copy(update={"fragments": (*request.fragments, span)})
    assert context(gbif_query_params(request, query())) == {}


def test_captured_provider_query_binds_context_and_cold_replay_does_not_resend(tmp_path):
    rig = make_capture_rig(tmp_path, source_id="gbif")
    text = "Danaus plexippus\norder: Lepidoptera\nfamily: Nymphalidae"
    request = reading_request(("label", "raw-a", text), ("label", "raw-b", text), base=rig.request)
    source_query = query()
    fixture = Path(__file__).parent / "fixtures" / "production_e2e" / "gbif-species-match.json"
    body = fixture.read_bytes()  # explicit synthetic FIXTURE* GBIF identifiers
    served = []

    async def read(url, policy):
        served.append(url)
        return 200, body

    transport = FixtureSourceTransport(read)
    broker = CaptureSourceBrokerV2(rig.registry, {rig.source.id: rig.policy}, rig.effects,
        rig.durable_scope, rig.lease, transport=transport, execution_class="offline")
    result = asyncio.run(broker.query_source(request, source_query))
    assert result.status == LookupStatus.SUCCESS
    assert len(served) == 1
    actual_params = {key: values[0] for key, values in parse_qs(urlsplit(served[0]).query).items()}
    assert actual_params == gbif_query_params(request, source_query)
    assert context(actual_params) == {"order": "Lepidoptera", "family": "Nymphalidae"}
    _, envelope = saved_envelope(rig, result)
    assert envelope.original_request == request and envelope.query == source_query
    assert envelope.responses[0].url == served[0]
    before = rig.store._read(rig.durable_scope).state

    cold_store = ResearchStore(SqliteStateBackend(rig.backend.path), "disposable-test-program")
    cold_blobs = ImmutableFileBlobs(rig.blobs.directory)
    cold = CaptureSourceBrokerV2(rig.registry, {rig.source.id: rig.policy},
        DurableEffectBroker(cold_store, cold_blobs), rig.durable_scope, rig.lease,
        transport=transport, execution_class="offline")
    replayed = asyncio.run(cold.query_source(request, source_query))
    after = cold_store._read(rig.durable_scope).state
    assert replayed == result and len(served) == 1
    assert before["effects"] == after["effects"]
    assert before["budget_policy"] == after["budget_policy"]
