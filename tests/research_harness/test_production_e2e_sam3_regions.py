"""The production e2e on a region as production records it: SAM 3, no crop_ref.

production_e2e_support builds its region the way no production run does: it
stores the readers' crop on the region (``region.crop_ref``), which sam3_effect.py
refuses for a SAM 3 region. Every reading of a SAM 3 region still declares the
crop it saw (``input_crop_ref``, production.py and first_pass.py). The ten pilot
snapshots recorded in production have exactly that shape, 26 regions with
``crop_ref`` None and 52 readings with ``input_crop_ref`` set. This file runs the
same specimen with that shape through the same production entry point, so the
publication proof of a reading's crop (canonical_evidence_provider_v2) is
exercised on the data the worker will meet.
"""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.workflow import SyntheticAdapters, Workflow, crop_bytes
from specimen_digitization.research_harness.persistence import (
    DurabilityScope, ImmutableFileBlobs, SqliteStateBackend,
)

from production_e2e_support import (
    COLLECTION, FIXTURES, LABEL_TEXT, ORG, WORKER, FakeDataConnect, GenerationBlobs, research_state,
    specimen_before_adjudication, worker_principal,
)
from test_production_e2e import (  # noqa: F401  (no_network is autouse)
    GEOGRAPHY, OTHER_OPERATOR, compose, no_network, supervised, to_plan,
)


def sam3_specimen(blobs):
    """The e2e specimen with its region and readings as the SAM 3 pipeline records them."""
    specimen = specimen_before_adjudication(blobs)
    region = specimen.run.regions[0]
    # A SAM 3 box inside the image, never the whole of it, and no stored crop.
    region.x, region.y, region.width, region.height = 8, 12, 70, 60
    region.method, region.version, region.crop_ref = "sam3", "sam3-fixture", None
    # Each reader kept the crop it saw: the bytes crop_bytes cuts for the box.
    crop = crop_bytes(blobs, specimen, region)
    for reading in specimen.run.observations:
        reading.input_crop_ref, reading.input_sha256 = blobs.put(crop), hashlib.sha256(crop).hexdigest()
    return specimen


@pytest.fixture
def sam3_rig(tmp_path):
    backend = SqliteStateBackend(tmp_path / "research-state.sqlite")
    members = {uid: [{"organization_id": ORG, "collection_id": COLLECTION, "role": "operator",
        "can_view_sensitive": False}] for uid in (WORKER, OTHER_OPERATOR)}
    backend.grant(DurabilityScope(ORG, COLLECTION, "membership", "membership", 1, WORKER, False))
    fake = FakeDataConnect(backend, members=members)
    blobs = GenerationBlobs(tmp_path / "blobs")
    repository = SqlConnectRepository(session=fake, graph_blobs=blobs)
    ordinary = Workflow(repository, blobs, SyntheticAdapters(blobs, LABEL_TEXT))
    token = actor_uid.set(WORKER)
    principal = worker_principal()
    created = repository.create(principal, sam3_specimen(blobs), "e2e-intake", "e2e-intake")
    yield SimpleNamespace(fake=fake, backend=backend, repository=repository, ordinary=ordinary,
        principal=principal, specimen_id=created.id, research_blobs=ImmutableFileBlobs(tmp_path / "research"),
        model_calls=[], source_urls=[])
    actor_uid.reset(token)


def test_the_run_reaches_its_final_queue_on_a_sam3_region(sam3_rig):
    rig = sam3_rig
    workflow = compose(rig)
    parsed = to_plan(workflow, rig)
    # The stored region has the shape production records: no crop, readings that kept theirs.
    region = parsed.run.regions[0]
    assert region.method == "sam3" and region.crop_ref is None
    assert (region.x, region.y, region.width, region.height) != (0, 0, parsed.asset.width, parsed.asset.height)
    assert parsed.run.observations and all(row.input_crop_ref for row in parsed.run.observations)

    with supervised():
        specimen = workflow.step(rig.principal, rig.specimen_id)

    # Every field the harness can settle published, the first one included; the
    # run was not held on its first publication (canonical_capture_native_crop_unproved).
    receipts = sorted(rig.fake.receipts.values(), key=lambda row: row["used_canonical_revision"])
    changed = [row["causal_proof"]["changed_field"] for row in receipts]
    assert len(changed) == len(set(changed)) == 19
    assert set(changed) == {"taxon", "city", "country", "county", "precise_location", "province_state",
        "collection_code", "collection_method", "fmnh_ins_number", "habitat", "collectors",
        "identified_by_irn", "date_visited_from", "date_visited_to", "date_identified", "elevation_from_m",
        "elevation_to_m", "elevation_from_ft", "elevation_to_ft"}
    published = rig.repository.get(rig.principal.scope, rig.specimen_id)
    assert published.version == specimen.version == parsed.version + len(receipts)
    url = json.loads((FIXTURES / "sources.json").read_text())["geolocate"]["url"]
    assert rig.source_urls.count(url) == len(GEOGRAPHY)
    _, state = research_state(rig.fake, rig.specimen_id)
    assert {effect["status"] for effect in state["effects"].values()} == {"completed"}
    # The final queue, as on the synthetic region: review, no operational reason.
    assert specimen.run.stage == "finalized" and specimen.run.disposition == "needs_human_review"
    progress = receipts[-1]["causal_proof"]["progress_receipt"]
    assert not progress["operational_reason_codes"]
    assert not rig.fake.duplicates
