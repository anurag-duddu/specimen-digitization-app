"""The slide's QR code, decoded in the segment step (application/barcode.py).

No museum image is committed (docs/DEPLOYMENT.md: no museum images in CI). Every code here
is made in the test by zxing-cpp's own encoder with the symbology the slides carry: QR Code
Model 2, error correction M, the seven digits alone (lane V2's measurement of the 100 real
slides, 2026-11-17), pasted on a white slide-sized canvas."""

from __future__ import annotations

import hashlib
import io
import json

import pytest
import zxingcpp
from PIL import Image, ImageFilter

from specimen_digitization.application import barcode
from specimen_digitization.application.domain import Evidence, Region, Run
from specimen_digitization.application.storage import LocalBlobs

QR = zxingcpp.BarcodeFormat.QRCode
MICRO = zxingcpp.BarcodeFormat.MicroQRCode
SLIDE = (1200, 400)


def symbol(text, fmt=QR, *, scale=4, blur=0.0):
    """A code as zxing-cpp's encoder draws it, `scale` pixels a module, blurred by `blur`."""
    made = zxingcpp.create_barcode(text, fmt, **({"ec_level": "M"} if fmt == QR else {}))
    pixels = memoryview(made.to_image(scale=scale))
    image = Image.frombytes("L", (pixels.shape[1], pixels.shape[0]), pixels.tobytes())
    return image.filter(ImageFilter.GaussianBlur(blur)) if blur else image


def slide(*codes, size=SLIDE):
    """A white slide with each (code, (x, y)) pasted on it."""
    image = Image.new("RGB", size, "white")
    for code, at in codes:
        image.paste(code, at)
    return image


def region(x, y, width, height, order=0):
    return Region(asset_id="asset", x=x, y=y, width=width, height=height, order=order,
        method="synthetic_fixture_region", version="1")


# ---- the acceptance rule ----------------------------------------------------------------------

def test_a_seven_digit_qr_code_model_2_is_accepted_with_its_provenance():
    labels = [region(0, 0, 600, 400), region(600, 0, 600, 400, order=1)]
    found = barcode.decode(slide((symbol("4486784"), (700, 120))), labels)
    assert found is not None
    assert (found.payload, found.decoder, found.decoder_version, found.symbology, found.rung) == (
        "4486784", "zxing-cpp", "3.1.1", "QRCodeModel2", "whole")
    # The label whose box holds the code's centre.
    assert found.region_id == labels[1].id
    assert {item.text for item in found.symbols} == {"4486784"}
    assert all(item.version == "1" and item.ec_level == "M" for item in found.symbols)


def test_leading_zeros_are_part_of_the_payload():
    assert barcode.decode(slide((symbol("0010001"), (700, 120)))).payload == "0010001"


def test_the_first_rung_that_decodes_is_recorded():
    """A code drawn one pixel a module and blurred decodes only at three times its size."""
    found = barcode.decode(slide((symbol("4486784", scale=1, blur=0.6), (700, 120))))
    assert (found.payload, found.rung) == ("4486784", "whole_x3")
    assert {item.rung for item in found.symbols} <= {"whole_x3", "gray_stretch_x3"}


def test_a_micro_qr_code_is_never_read():
    """zxing-cpp, asked for every format, finds Micro QR codes in damaged QR codes (V2); the
    decoder asks for QR Code Model 2 alone, so a Micro QR code holding seven digits is no decode."""
    image = slide((symbol("4486784", MICRO), (700, 120)))
    assert [item.text for item in zxingcpp.read_barcodes(image)] == ["4486784"]
    assert barcode.decode(image) is None


@pytest.mark.parametrize("text", ["448678", "44867840", "FMNHINS 4486784", "4486784 ", "https://example.org/1"])
def test_a_payload_that_is_not_exactly_seven_digits_is_no_decode(text):
    assert barcode.decode(slide((symbol(text), (700, 120)))) is None


def test_two_different_codes_on_one_slide_are_no_decode():
    assert barcode.decode(slide((symbol("4486784"), (100, 120)), (symbol("4486785"), (700, 120)))) is None


def test_a_seven_digit_code_beside_another_symbol_is_no_decode():
    assert barcode.decode(slide((symbol("4486784"), (100, 120)), (symbol("FMNH"), (700, 120)))) is None


def test_the_same_code_twice_is_one_payload():
    found = barcode.decode(slide((symbol("4486784"), (100, 120)), (symbol("4486784"), (700, 120))))
    assert found.payload == "4486784"
    # Two symbols on the first rung; the region is the first symbol's, and no label is given.
    assert len([item for item in found.symbols if item.rung == "whole"]) == 2
    assert found.region_id is None


@pytest.mark.parametrize("image", [
    Image.new("RGB", SLIDE, "white"),
    Image.new("L", (5, 5), 0),
    Image.new("RGBA", SLIDE, (255, 255, 255, 0)),
    Image.new("P", SLIDE),
])
def test_an_image_with_no_code_is_no_decode(image):
    assert barcode.decode(image) is None


def test_a_rung_larger_than_the_bound_is_skipped(monkeypatch):
    """The work is bounded by the image: a rung over MAX_PIXELS is never made."""
    monkeypatch.setattr(barcode, "MAX_PIXELS", SLIDE[0] * SLIDE[1])
    assert [name for name, _, _ in barcode._rungs(slide())] == ["whole", "gray_stretch"]
    assert barcode.decode(slide((symbol("4486784", scale=1, blur=0.6), (700, 120)))) is None


def test_a_failing_or_missing_decoder_is_no_decode(monkeypatch):
    image = slide((symbol("4486784"), (700, 120)))
    monkeypatch.setattr(barcode, "decoder_version", lambda: None)
    assert barcode.decode(image) is None
    monkeypatch.undo()

    def broken(*args, **kwargs):
        raise RuntimeError("decoder failed")

    monkeypatch.setattr(zxingcpp, "read_barcodes", broken)
    assert barcode.decode(image) is None


# ---- the evidence row ------------------------------------------------------------------------

class Specimen:
    """What record reads of a specimen: its asset (source_pixels.source_image) and run."""

    def __init__(self, image, blobs, run):
        output = io.BytesIO()
        image.save(output, format="PNG")
        data = output.getvalue()
        self.asset = type("Asset", (), dict(id="asset", processing_derivative=None, blob_ref=blobs.put(data),
            width=image.size[0], height=image.size[1]))()
        self.run = run


def test_record_stores_one_row_that_names_the_number_and_keeps_the_whole_decode(tmp_path):
    blobs = LocalBlobs(tmp_path / "blobs")
    run = Run(regions=[region(600, 0, 600, 400)])
    specimen = Specimen(slide((symbol("4486784"), (700, 120))), blobs, run)
    row = barcode.record(run, specimen, blobs)
    assert run.evidence == [row]
    assert (row.kind, row.source, row.locator, row.asset_id, row.region_id) == (
        "derived", "barcode", "check:barcode_decode", "asset", run.regions[0].id)
    assert row.excerpt == "fmnh_ins_number: 4486784 (QR code read by zxing-cpp 3.1.1, ladder rung whole)"
    stored = blobs.get(row.raw_ref)
    assert hashlib.sha256(stored).hexdigest() == row.digest
    kept = json.loads(stored)
    assert (kept["field_key"], kept["payload"], kept["decoder"], kept["decoder_version"], kept["symbology"],
        kept["rung"], kept["region_id"]) == ("fmnh_ins_number", "4486784", "zxing-cpp", "3.1.1", "QRCodeModel2",
        "whole", run.regions[0].id)
    assert barcode.stored_code(run).payload == "4486784"
    # The segment step done again keeps one row.
    again = barcode.record(run, specimen, blobs)
    assert run.evidence == [again]


def test_record_stores_nothing_and_raises_nothing_for_an_undecodable_slide(tmp_path):
    blobs = LocalBlobs(tmp_path / "blobs")
    kept = Evidence(kind="literal", source="label", locator=None, excerpt="x")
    run = Run(evidence=[kept])
    assert barcode.record(run, Specimen(slide(), blobs, run), blobs) is None
    assert run.evidence == [kept]
    assert barcode.stored_code(run) is None


def test_record_never_raises_when_the_pixels_cannot_be_read(tmp_path):
    blobs = LocalBlobs(tmp_path / "blobs")
    run = Run()
    specimen = Specimen(slide((symbol("4486784"), (700, 120))), blobs, run)
    specimen.asset.blob_ref = "missing"
    assert barcode.record(run, specimen, blobs) is None
    assert run.evidence == []


def test_stored_code_needs_exactly_one_row_that_names_seven_digits():
    def row(excerpt):
        return Evidence(kind="derived", source="barcode", locator="check:barcode_decode", excerpt=excerpt)

    one = row("fmnh_ins_number: 4486784 (QR code read by zxing-cpp 3.1.1, ladder rung whole)")
    assert barcode.stored_code(Run(evidence=[one])).payload == "4486784"
    assert barcode.stored_code(Run(evidence=[one, one.model_copy(update={"id": "two"})])) is None
    assert barcode.stored_code(Run(evidence=[row("fmnh_ins_number: 448678 (QR code read by zxing-cpp")])) is None
    other = one.model_copy(update={"source": "field_research"})
    assert barcode.stored_code(Run(evidence=[other])) is None


# ---- the segment step ------------------------------------------------------------------------

def intake_slide(tmp_path, image):
    """A synthetic specimen of `image` through the local API (as test_application.intake), and
    the workflow that processes it with the synthetic adapters."""
    from fastapi.testclient import TestClient

    from specimen_digitization.application.api import SYNTHETIC_COLLECTION, SYNTHETIC_ORG, SYNTHETIC_TEXT, local_app
    from specimen_digitization.application.domain import Principal, Scope
    from specimen_digitization.application.storage import SQLiteRepository
    from specimen_digitization.application.workflow import SyntheticAdapters, Workflow

    token, prefix = "test-only-local-token", f"/v1/organizations/{SYNTHETIC_ORG}"
    headers = {"Authorization": "Bearer " + token, "Idempotency-Key": "test-request"}
    client = TestClient(local_app(tmp_path, token), raise_server_exceptions=False)
    output = io.BytesIO()
    image.save(output, format="PNG")
    data = output.getvalue()
    batch = client.post(prefix + "/batches", headers=headers,
        json={"collection_id": SYNTHETIC_COLLECTION, "display_name": "Synthetic"}).json()
    upload = client.post(prefix + f"/batches/{batch['batch_id']}/items", headers=headers, json={
        "client_item_id": "one", "filename": "slide.png", "media_type": "image/png", "size_bytes": len(data),
        "width": image.size[0], "height": image.size[1], "sha256": hashlib.sha256(data).hexdigest()}).json()
    sent = client.put(prefix + f"/uploads/{upload['upload_id']}/content", headers=headers, content=data).json()
    done = client.post(prefix + f"/uploads/{upload['upload_id']}/complete", headers=headers,
        json={"expected_revision": sent["revision"]}).json()
    blobs = LocalBlobs(tmp_path / "blobs")
    principal = Principal(user_id="synthetic-reviewer", role="reviewer",
        scope=Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION))
    workflow = Workflow(SQLiteRepository(tmp_path / "state.sqlite3"), blobs, SyntheticAdapters(blobs, SYNTHETIC_TEXT))
    return workflow, principal, done["specimen_id"]


def through_segment(workflow, principal, specimen_id):
    for _ in range(10):
        specimen = workflow.step(principal, specimen_id)
        assert specimen.run.stage != "processing_blocked", specimen.run.blocker
        if "segment" in specimen.run.completed_steps:
            return specimen
    raise AssertionError("the segment step never ran")


def test_the_segment_step_stores_the_slides_code(tmp_path):
    workflow, principal, specimen_id = intake_slide(tmp_path, slide((symbol("4486784"), (700, 120))))
    specimen = through_segment(workflow, principal, specimen_id)
    code = barcode.stored_code(specimen.run)
    assert code is not None and code.payload == "4486784"
    # The synthetic segmenter's one region is the whole slide.
    assert code.row.region_id == specimen.run.regions[0].id
    assert code.row.asset_id == specimen.asset.id
    # The stored row passes the run's evidence integrity check.
    from specimen_digitization.application.integrity import verify_evidence

    verify_evidence(specimen, workflow.blobs)


def test_the_segment_step_stores_nothing_for_a_slide_with_no_code(tmp_path):
    workflow, principal, specimen_id = intake_slide(tmp_path, slide())
    specimen = through_segment(workflow, principal, specimen_id)
    assert not [row for row in specimen.run.evidence if row.source == barcode.SOURCE]
    assert barcode.stored_code(specimen.run) is None
