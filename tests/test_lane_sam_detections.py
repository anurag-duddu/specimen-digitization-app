"""SAM 3 parameters and recorded detections (docs/execution/golive/LANE.md, T3b)."""

import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from specimen_digitization.application.collection_profiles import (
    Sam3Parameters,
    SegmentationSettings,
    published_registry,
)
from specimen_digitization.application.sam3_effect import (
    canonical_sha256,
    validate_sam3_run_response,
)
from specimen_digitization.application.sam3_server import RunSegmenter, create_app

from test_lane_sam_server import RunObjects, image_bytes, post, run_request
from test_sam3_server import FixtureEngine

PILOT_PARAMETERS = {
    "label_threshold": 0.5,
    "mask_threshold": 0.5,
    "record_floor": 0.1,
    "max_detections": 64,
    "cross_check_concept": "text",
}


def box_mask(size, box):
    mask = Image.new("L", size)
    mask.paste(255, box)
    return mask


class DetectionEngine(FixtureEngine):
    """Label detections at 0.9, 0.4 and 0.05; one cross-check detection at 0.7."""

    def __init__(self, label=(0.9, 0.4, 0.05), cross=(0.7,)):
        super().__init__()
        self.label, self.cross, self.detected, self.many = label, cross, [], []

    def detect_many(self, image, prompts, **settings):
        self.many.append(list(prompts))
        return [self.detect(image, prompt, **settings) for prompt in prompts]

    def detect(self, image, prompt, *, threshold, mask_threshold, limit):
        self.calls += 1
        self.detected.append((prompt, threshold, mask_threshold, limit))
        scores = self.label if prompt == "label" else self.cross
        found = [
            (box_mask(image.size, (index % 4, 0, index % 4 + 1, 1)), score)
            for index, score in enumerate(scores)
            if score >= threshold
        ]
        return sorted(found, key=lambda pair: pair[1], reverse=True)[:limit]


def serve(engine):
    raw = image_bytes()
    objects = RunObjects(raw)
    engine.checkpoint_sha256 = canonical_sha256(engine.checkpoint_files)

    def auth(header):
        if header != "Bearer fixture":
            raise ValueError("denied")

    return raw, TestClient(create_app(RunSegmenter(objects, engine), auth)), objects


def test_the_pilot_pins_the_parameters_the_service_applies():
    settings = published_registry().resolve("insects").profile.segmentation_settings
    assert settings.parameters.model_dump() == PILOT_PARAMETERS


def test_settings_without_parameters_keep_their_bytes():
    assert SegmentationSettings(prompt="label").model_dump()["parameters"] == {}


@pytest.mark.parametrize(
    "values",
    [
        {"record_floor": 0.6, "label_threshold": 0.5},
        {"label_threshold": 0.0},
        {"mask_threshold": 1.0},
        {"max_detections": 65},
        {"cross_check_concept": ""},
    ],
)
def test_parameter_refusals(values):
    with pytest.raises(ValueError):
        Sam3Parameters(**values)


def test_the_service_applies_the_parameters_and_records_detections():
    engine = DetectionEngine()
    raw, client, objects = serve(engine)
    request = run_request(raw, parameters=PILOT_PARAMETERS)
    response = post(client, request)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["parameters"] == PILOT_PARAMETERS
    assert (body["threshold"], body["mask_threshold"]) == (0.5, 0.5)
    assert [d["score"] for d in body["detections"]["label"]] == [0.9, 0.4]
    assert [r["order"] for r in body["regions"]] == [0]
    assert [m["score"] for m in body["masks"]] == [0.9]
    masks = [name for name in objects.data if name.startswith("application/sha256/") and "sam3-runs" not in name]
    assert len(masks) == 1
    assert body["cross_check"]["concept"] == "text"
    assert [d["score"] for d in body["cross_check"]["detections"]] == [0.7]
    assert all(
        set(d) == {"box", "score"} and len(d["box"]) == 4
        for d in body["detections"]["label"] + body["cross_check"]["detections"]
    )
    assert [call[:2] for call in engine.detected] == [("label", 0.1), ("text", 0.1)]
    pins = {"checkpoint_sha256": engine.checkpoint_sha256}
    assert validate_sam3_run_response(body, {"request": request, "pins": pins}) == "valid"


def test_no_label_above_the_threshold_is_an_empty_result_not_an_error():
    engine = DetectionEngine(label=(0.3,), cross=())
    raw, client, _ = serve(engine)
    request = run_request(raw, parameters=PILOT_PARAMETERS)
    response = post(client, request)
    assert response.status_code == 200, response.text
    assert response.json()["regions"] == []
    assert [d["score"] for d in response.json()["detections"]["label"]] == [0.3]
    pins = {"checkpoint_sha256": engine.checkpoint_sha256}
    assert validate_sam3_run_response(
        response.json(), {"request": request, "pins": pins}
    ) == "valid"


def test_requests_without_parameters_keep_the_previous_contract():
    engine = DetectionEngine()
    raw, client, _ = serve(engine)
    body = post(client, run_request(raw)).json()
    assert body["parameters"] == {
        "label_threshold": 0.5,
        "mask_threshold": 0.5,
        "record_floor": 0.5,
        "max_detections": 64,
        "cross_check_concept": None,
    }
    assert body["cross_check"] is None
    assert [d["score"] for d in body["detections"]["label"]] == [0.9]


@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        (lambda body: body["parameters"].update(record_floor=0.2), "parameters_binding_mismatch"),
        (lambda body: body["detections"]["label"][0].update(box=[0, 0, 99, 1]), "invalid_detection"),
        (lambda body: body["detections"]["label"][1].update(score=0.05), "invalid_detection"),
        (lambda body: body["cross_check"].update(concept="handwriting"), "parameters_binding_mismatch"),
        (lambda body: body["masks"][0].update(score=0.8), "region_detection_mismatch"),
    ],
)
def test_the_worker_rejects_inconsistent_detections(change, verdict):
    engine = DetectionEngine()
    raw, client, _ = serve(engine)
    request = run_request(raw, parameters=PILOT_PARAMETERS)
    body = json.loads(json.dumps(post(client, request).json()))
    change(body)
    pins = {"checkpoint_sha256": engine.checkpoint_sha256}
    assert validate_sam3_run_response(body, {"request": request, "pins": pins}) == verdict


def test_the_worker_keeps_the_detections_on_the_run(monkeypatch, tmp_path):
    import base64

    from specimen_digitization.application import production
    import specimen_digitization.application.bounded_effect as bounded
    from specimen_digitization.application.storage import LocalBlobs

    from test_lane_sam_client import isolated, lane_specimen

    engine = DetectionEngine()
    raw, client, _ = serve(engine)
    specimen = lane_specimen()
    specimen.run.profile_rules["segmentation_settings"] = SegmentationSettings(
        prompt="label", parameters=Sam3Parameters(**PILOT_PARAMETERS)
    ).model_dump(mode="json")
    specimen.run.dependencies["segmentation"]["checkpoint_sha256"] = (
        engine.checkpoint_sha256
    )
    captured = {}

    def call(effect, payload, *args, **kwargs):
        captured.update(payload)
        request = dict(payload["request"])
        response = post(client, request)
        return isolated(
            "completed",
            "ok",
            json.dumps(
                {
                    "http_status": response.status_code,
                    "validation": validate_sam3_run_response(response.json(), payload),
                    "body_base64": base64.b64encode(response.content).decode(),
                }
            ).encode(),
        )

    monkeypatch.setattr(bounded, "run_isolated", call)
    service = production.Sam3Service(
        "https://sam.run.app", LocalBlobs(tmp_path), effect=lambda payload: b""
    )
    regions = service.segment_per_run(specimen)
    assert captured["request"]["parameters"] == PILOT_PARAMETERS
    assert [region.order for region in regions] == [0]
    segmentation = specimen.run.segmentation
    assert segmentation["parameters"] == PILOT_PARAMETERS
    assert segmentation["region_scores"] == [0.9]
    assert [d["score"] for d in segmentation["label_detections"]] == [0.9, 0.4]
    assert segmentation["cross_check"]["concept"] == "text"


def test_the_lab_can_name_another_cross_check_concept(monkeypatch):
    from specimen_digitization.application.production import cross_check_override

    monkeypatch.setenv("SPECIMEN_SAM3_LAB_CROSS_CHECK_CONCEPT", "handwriting")
    assert cross_check_override(lab=True) == "handwriting"
    assert cross_check_override(lab=False) is None
    monkeypatch.delenv("SPECIMEN_SAM3_LAB_CROSS_CHECK_CONCEPT")
    assert cross_check_override(lab=True) is None


def test_one_vision_pass_serves_the_label_and_the_cross_check():
    # The pilot's two concepts in one engine call, so the image is encoded
    # once: two passes did not fit the service's deadline (the acceptance lab).
    engine = DetectionEngine()
    raw, client, _ = serve(engine)
    response = post(client, run_request(raw, parameters=PILOT_PARAMETERS))
    assert response.status_code == 200, response.text
    assert engine.many == [["label", "text"]]


class Grid:
    """Just enough of a tensor's array for Image.fromarray, without numpy."""

    def __init__(self, cells):
        self.cells = cells

    def cpu(self):
        return self

    def numpy(self):
        return self

    def astype(self, dtype):
        return self

    def __mul__(self, factor):
        return Grid([[value * factor for value in row] for row in self.cells])

    @property
    def __array_interface__(self):
        rows, columns = len(self.cells), len(self.cells[0])
        return {"shape": (rows, columns), "typestr": "|u1", "strides": (columns, 1), "version": 3}

    def tobytes(self):
        return bytes(value for row in self.cells for value in row)


class Score(float):
    def item(self):
        return float(self)


class Found:
    """What the processor's post-processing returns for one concept."""

    def __init__(self, boxes, scores):
        self.masks = [
            Grid([[int(x0 <= x < x1 and y0 <= y < y1) for x in range(4)] for y in range(4)])
            for x0, y0, x1, y1 in boxes
        ]
        self.scores = [Score(value) for value in scores]


class FakeProcessor:
    def __init__(self, found):
        self.found, self.calls, self.sizes = found, [], []

    def __call__(self, images=None, text=None, return_tensors=None):
        self.calls.append("image" if images is not None else text)
        if images is not None:
            sizes = type("Sizes", (), {"tolist": lambda s: [[4, 4]]})()
            return {"pixel_values": "pixels", "original_sizes": sizes}
        return {"input_ids": text, "attention_mask": "mask:" + text}

    def post_process_instance_segmentation(self, output, *, threshold, mask_threshold, target_sizes):
        self.sizes.append(target_sizes)
        found = self.found[output]
        return [{"masks": found.masks, "scores": found.scores}]


class FakeModel:
    def __init__(self):
        self.vision, self.calls = 0, []

    def get_vision_features(self, pixel_values):
        self.vision += 1
        return ("vision", pixel_values)

    def __call__(self, **inputs):
        self.calls.append(inputs)
        return inputs["input_ids"]


def test_the_engine_encodes_the_image_once_for_every_concept():
    import contextlib

    from specimen_digitization.application.sam3_server import Sam3Engine

    engine = object.__new__(Sam3Engine)
    engine.processor = FakeProcessor(
        {
            "label": Found([(0, 0, 2, 2), (2, 2, 4, 4)], [0.6, 0.9]),
            "text": Found([(0, 0, 1, 1)], [0.7]),
        }
    )
    engine.model = FakeModel()
    engine.torch = type("Torch", (), {"inference_mode": staticmethod(contextlib.nullcontext)})
    found = engine.detect_many(
        Image.new("RGB", (4, 4)), ["label", "text"], threshold=0.5, mask_threshold=0.5, limit=64
    )
    assert engine.model.vision == 1
    assert engine.processor.calls == ["image", "label", "text"]
    assert [call["vision_embeds"] for call in engine.model.calls] == [("vision", "pixels")] * 2
    assert [(call["input_ids"], call["attention_mask"]) for call in engine.model.calls] == [
        ("label", "mask:label"),
        ("text", "mask:text"),
    ]
    assert engine.processor.sizes == [[[4, 4]], [[4, 4]]]
    # Highest scores first, as one concept's detect returned them.
    assert [[score for _, score in concept] for concept in found] == [[0.9, 0.6], [0.7]]
    assert all(mask.size == (4, 4) and mask.mode == "L" for concept in found for mask, _ in concept)
