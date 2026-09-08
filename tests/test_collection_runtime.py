"""Profile modules drive actual scoped API processing and corrections."""

import hashlib

from fastapi.testclient import TestClient
from test_application import intake, HEADERS, PREFIX, TOKEN, image_bytes
from specimen_digitization.application.api import (
    create_app,
    SYNTHETIC_TEXT,
    SYNTHETIC_COLLECTION,
)
from specimen_digitization.application.collection_runtime import application_registry
from specimen_digitization.application.collection_profiles import (
    CollectionNode,
    ProfileMapping,
)
from specimen_digitization.application.storage import SQLiteRepository, LocalBlobs
from specimen_digitization.application.workflow import SyntheticAdapters


def test_versioned_profile_correction_preserves_scope_source_and_history(tmp_path):
    registry = application_registry(True)
    original = registry.profiles[0]
    alternate = original.model_copy(
        update={
            "id": "synthetic_alternate",
            "version": "synthetic-v2",
            "collection_id": "alternate",
        }
    )
    registry = registry.model_copy(
        update={
            "nodes": (
                *registry.nodes,
                CollectionNode(id="alternate", name="Synthetic alternative"),
            ),
            "profiles": (*registry.profiles, alternate),
            "mappings": (
                *registry.mappings,
                ProfileMapping(
                    collection_id="alternate",
                    profile_id=alternate.id,
                    profile_version=alternate.version,
                ),
            ),
        }
    )
    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="synthetic",
        repository=SQLiteRepository(tmp_path / "state.sqlite3"),
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        token=TOKEN,
        profile_registry=registry,
    )
    with TestClient(app) as http:
        row = intake(http)
        path = PREFIX + f"/specimens/{row['specimen_id']}"
        old = http.get(path + "/workspace", headers=HEADERS).json()
        assert old["run"]["profile_snapshot"]["version"] == "synthetic-v1"
        assert old["run"]["classification"]["synthetic"] is True
        assert old["asset"]["quality_diagnostics"]["status"] == "valid"
        assert old["asset"]["quality_diagnostics"]["metrics"]["calibrated"] is False
        access_path = PREFIX + f"/assets/{old['asset']['id']}/access"
        access = http.get(access_path, headers=HEADERS).json()
        original_bytes = http.get(access["url"], headers=HEADERS).content
        assert original_bytes == image_bytes()
        derived = http.get(access["view_url"], headers=HEADERS)
        assert derived.status_code == 200
        assert (
            hashlib.sha256(derived.content).hexdigest()
            == old["asset"]["view_derivative"]["derivative_sha256"]
        )
        correction = http.post(
            path + "/classification",
            headers=HEADERS,
            json={
                "expected_revision": old["revision"],
                "reason": "Synthetic reviewer chose alternate published profile",
                "collection_id": SYNTHETIC_COLLECTION,
                "profile_collection_id": "alternate",
            },
        )
        assert correction.status_code == 200, correction.text
        new = http.get(path + "/workspace", headers=HEADERS).json()
        assert new["run"]["profile_snapshot"]["id"] == "synthetic_alternate"
        assert new["profile_version"] == "synthetic-v2"
        assert new["run"]["id"] != old["run"]["id"]
        assert new["collection_id"] == old["collection_id"]
        assert new["asset"]["sha256"] == old["asset"]["sha256"]
        assert (
            http.get(path + f"/history/{old['revision']}", headers=HEADERS).json()
            == old
        )
        assert (
            http.post(
                path + "/classification",
                headers=HEADERS,
                json={
                    "expected_revision": new["revision"],
                    "reason": "Unknown profile probe",
                    "collection_id": SYNTHETIC_COLLECTION,
                    "profile_collection_id": "unknown",
                },
            ).status_code
            == 422
        )


def test_draft_registry_cannot_become_approved_through_manual_selection(tmp_path):
    from specimen_digitization.application.collection_runtime import classify_and_select
    from specimen_digitization.application.domain import (
        Specimen,
        Asset,
        Run,
        Profile,
        Scope,
    )

    blobs = LocalBlobs(tmp_path / "blobs")
    raw = image_bytes()
    specimen = Specimen(
        scope=Scope(organization_id="org", collection_id="collection"),
        asset=Asset(
            sha256=hashlib.sha256(raw).hexdigest(),
            blob_ref=blobs.put(raw),
            media_type="image/png",
            size_bytes=len(raw),
            width=120,
            height=80,
            filename="synthetic.png",
            uploader="reviewer",
        ),
        run=Run(
            profile=Profile(),
            classification_selection={
                "collection_id": "insects",
                "actor_id": "reviewer",
                "reason": "Choose insects",
            },
        ),
    )
    issue = classify_and_select(specimen, application_registry(False), None, blobs)
    assert issue == "profile_draft"
    assert not specimen.run.profile.institutional_policy_approved
    assert specimen.run.classification["reason"] == "approved_classifier_route_missing"


def test_authorized_preflight_does_not_create_specimen(tmp_path):
    from specimen_digitization.application.image_codecs import CodecPolicy
    from specimen_digitization.application.image_quality import ImageLimits

    blobs = LocalBlobs(tmp_path / "blobs")
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    app = create_app(
        mode="synthetic",
        repository=repo,
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        token=TOKEN,
        codec_policy=CodecPolicy(
            require_memory_limit=False, limits=ImageLimits(max_bytes=1024)
        ),
    )
    with TestClient(app) as http:
        path = PREFIX + "/images/preflight?collection_id=" + SYNTHETIC_COLLECTION
        result = http.post(
            path,
            headers={**HEADERS, "Content-Type": "image/png"},
            content=image_bytes(),
        )
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["input_sha256"] == hashlib.sha256(image_bytes()).hexdigest()
        assert body["actual_format"] == "PNG" and body["specimen_created"] is False
        assert (
            body["source_transmitted"] is True
            and body["external_provider_used"] is False
        )
        assert (
            http.post(
                path,
                headers={**HEADERS, "Content-Type": "image/png"},
                content=b"x" * 1025,
            ).status_code
            == 422
        )
        assert http.post(path, content=image_bytes()).status_code == 401
        assert (
            http.post(
                path.replace(SYNTHETIC_COLLECTION, "foreign"),
                headers=HEADERS,
                content=image_bytes(),
            ).status_code
            == 403
        )
        with repo.connect() as db:
            assert db.execute("SELECT count(*) FROM records").fetchone()[0] == 0
            assert db.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
        assert not list((tmp_path / "blobs").rglob("*"))


def test_original_coordinate_crop_and_four_clockwise_rotations():
    import io
    from PIL import Image
    from specimen_digitization.application.region_pixels import region_png
    from specimen_digitization.application.domain import Region

    image = Image.new("RGB", (4, 3))
    image.putdata([(i * 20, 0, 0) for i in range(12)])
    output = io.BytesIO()
    image.save(output, format="PNG")
    expected = [
        [(100, 0, 0), (120, 0, 0), (180, 0, 0), (200, 0, 0)],
        [(180, 0, 0), (100, 0, 0), (200, 0, 0), (120, 0, 0)],
        [(200, 0, 0), (180, 0, 0), (120, 0, 0), (100, 0, 0)],
        [(120, 0, 0), (200, 0, 0), (100, 0, 0), (180, 0, 0)],
    ]
    for turn in range(4):
        region = Region(
            asset_id="source",
            x=1,
            y=1,
            width=2,
            height=2,
            rotation_quarter_turns=turn,
            order=0,
            method="human",
            version="test",
        )
        pixels = Image.open(io.BytesIO(region_png(image, region)))
        assert list(pixels.getdata()) == expected[turn]
