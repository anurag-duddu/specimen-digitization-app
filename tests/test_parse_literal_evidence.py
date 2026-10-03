"""The parse step's label evidence keeps a stored record, as the field harness's does.

With a blob store each explicit label line's literal evidence stores the record
{region_id, observation_ids, excerpt}, so the projector writes it as a recorded
evidence_item row that a supported value can link to (G23, #88). Label text is
synthetic.
"""

from __future__ import annotations

import hashlib
import json

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import (
    Asset, Observation, Principal, Profile, Region, Run, Scope, Specimen, Transcript,
)
from specimen_digitization.application.integrity import verify_evidence
from specimen_digitization.application.projection import Blob, writes
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository, digest
from specimen_digitization.application.workflow import SyntheticAdapters, Workflow

from test_application import SYNTHETIC_COLLECTION, SYNTHETIC_ORG, SYNTHETIC_TEXT, client, intake

LINES = ("country: Kenya", "habitat: Synthetic grassland")


def specimen():
    asset = Asset(sha256="a" * 64, blob_ref="a" * 64 + ":1", media_type="image/jpeg",
        size_bytes=10, width=100, height=100, filename="fixture.jpeg", uploader="fixture")
    region = Region(asset_id=asset.id, x=0, y=0, width=100, height=100, order=0,
        method="fixture", version="fixture")
    text = "\n".join(LINES)
    reading = Observation(region_id=region.id, route_id="handwriting-qwen", model_id="fixture-model",
        provider="fixture", prompt_version="b" * 64, input_sha256="c" * 64,
        literal_text=text, raw_ref="d" * 64 + ":2", raw_sha256="d" * 64)
    transcript = Transcript(region_id=region.id, text=text, observation_ids=[reading.id],
        alternatives=[text], resolved=True, decision_kind="identical_readings",
        selected_observation_id=reading.id)
    profile = published_registry().profiles[0]
    snapshot = profile.model_dump(mode="json")
    run = Run(regions=[region], observations=[reading], transcripts=[transcript],
        profile=Profile(id=profile.id, version=profile.version, routes=tuple(profile.model_routes)),
        profile_snapshot=snapshot, profile_registry_version="registry-1",
        dependencies={"profile_snapshot_sha256": digest(snapshot), "profile_registry_version": "registry-1"})
    return Specimen(scope=Scope(organization_id="org-1", collection_id="coll-1"), asset=asset, run=run)


def locate(ref):
    sha, _, generation = ref.partition(":")
    return Blob("fixture-bucket", f"application/sha256/{sha}", generation)


def label_evidence(run):
    return [item for item in run.evidence if item.kind == "literal" and item.source == "label"]


def base_record_writes(s):
    return writes(s, locate, lambda ref: 1, "worker-uid", base_record=True)


def test_with_a_blob_store_each_label_line_keeps_its_record(tmp_path):
    blobs = LocalBlobs(tmp_path / "blobs")
    s = specimen()
    Workflow.parse(s.run, s.asset.id, blobs)
    found = label_evidence(s.run)
    assert [item.excerpt for item in found] == list(LINES)
    transcript = s.run.transcripts[0]
    for item in found:
        record = json.dumps({"region_id": transcript.region_id,
            "observation_ids": transcript.observation_ids, "excerpt": item.excerpt},
            sort_keys=True).encode()
        assert blobs.get(item.raw_ref) == record
        assert item.digest == hashlib.sha256(record).hexdigest()
    assert s.run.fields["country"].evidence_ids == [found[0].id]


def test_the_base_record_writes_label_evidence_as_recorded(tmp_path):
    s = specimen()
    Workflow.parse(s.run, s.asset.id, LocalBlobs(tmp_path / "blobs"))
    result = base_record_writes(s)
    rows = [w.variables for w in result if w.operation == "AppendEvidenceItemV2"]
    assets = {w.variables["id"]: w.variables for w in result if w.operation == "AppendSourceAssetV2"}
    found = label_evidence(s.run)
    assert [row["id"] for row in rows] == [item.id for item in found]
    for row, item in zip(rows, found):
        assert (row["source"], row["outcome"]) == ("label", "recorded")
        assert row["locator"] == f"region:{s.run.regions[0].id}"
        assert row["responseSha256"] == item.digest
        assert assets[row["rawAssetId"]]["kind"] == "evidence_record"


def test_without_a_blob_store_parse_keeps_no_record():
    s = specimen()
    Workflow.parse(s.run, s.asset.id)
    assert len(label_evidence(s.run)) == len(LINES)
    assert all(item.raw_ref is None and item.digest is None for item in label_evidence(s.run))
    assert not [w for w in base_record_writes(s) if w.operation == "AppendEvidenceItemV2"]


def test_the_workflow_parse_step_stores_records_that_verify(tmp_path):
    c = client(tmp_path)
    ident = intake(c)["specimen_id"]
    c.close()
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    blobs = LocalBlobs(tmp_path / "blobs")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
    existing = repo.get(scope, ident)
    existing.run = Run(profile=existing.run.profile)
    repo.save(principal, existing, existing.version, "reset-fixture", digest({"reset": True}))
    result = Workflow(repo, blobs, SyntheticAdapters(blobs, SYNTHETIC_TEXT)).drain(principal, ident)
    # Finalize checked the evidence bytes before the disposition was saved.
    assert result.run.disposition is not None
    found = label_evidence(result.run)
    assert len(found) == len(SYNTHETIC_TEXT.splitlines())
    assert all(item.raw_ref and item.digest for item in found)
    verify_evidence(result, blobs)
