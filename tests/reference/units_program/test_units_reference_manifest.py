"""The reference set's manifest is fixed (docs/execution/units/PLAN.md, WP 0): its 30 specimens, their label ids
and blob digests, the seed that drew the 20, and the truth file. A change to any of them fails here."""
import hashlib
import json
import random
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = json.loads((HERE / "manifest.json").read_text())
FIXTURE = ROOT / "tests" / "fixtures" / "field_model_pilot_rows.json"

SEED = 20261026
FIXTURE_DIGEST = "sha256:f327ca85d0e3b9b3359233b12780492b395f734cb4c1fb7787cb4a01f7126ffc"
# The canonical JSON (sort_keys, no spaces) of the whole manifest: every subject, object generation, image and
# crop digest, label id and box, the draw, the region step's engine and checkpoint digest, the label counts and the
# truth record.
MANIFEST_DIGEST = "sha256:25daaf8b0376c037db17e1047d586e4dd6871f852c309aa3652e5bbd84c8bdc0"
PILOT = [f"1055263{n}" for n in range(21, 31)]
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def canonical(value):
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                                 ensure_ascii=False).encode()).hexdigest()


def test_the_manifest_is_the_recorded_one():
    assert canonical(MANIFEST) == MANIFEST_DIGEST


def test_the_truth_file_is_the_one_the_manifest_names():
    assert "sha256:" + hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_DIGEST
    assert MANIFEST["truth"]["pilot"]["digest"] == FIXTURE_DIGEST
    rows = {r["subject"] for r in json.loads(FIXTURE.read_text())["rows"]}
    assert rows == set(PILOT)


def test_thirty_specimens_the_ten_pilot_slides_then_twenty_drawn():
    specimens = MANIFEST["specimens"]
    assert [s["subject"] for s in specimens[:10]] == PILOT
    assert [s["set"] for s in specimens] == ["pilot"] * 10 + ["drawn"] * 20
    assert {s["truth"] for s in specimens[:10]} == {"fixture"}
    assert {s["truth"] for s in specimens[10:]} == {MANIFEST["truth"]["drawn"]["source"]}
    assert MANIFEST["truth"]["drawn"]["source"] in {"none", "emu"}


def test_every_label_has_an_id_a_box_and_a_crop_digest():
    ids = []
    for s in MANIFEST["specimens"]:
        assert DIGEST.fullmatch(s["image_digest"]) and s["generation"] > 0
        assert s["label_count"] == s["segmentation"]["coverage"]["region_count"]
        for n, label in enumerate(s["labels"], 1):
            assert label["id"] == f"{s['subject']}-L{n}" and label["order"] == n - 1
            assert DIGEST.fullmatch(label["crop_digest"]) and len(label["box"]) == 4
            ids.append(label["id"])
    assert len(ids) == len(set(ids))
    assert all(len(s["labels"]) == 2 == s["label_count"] for s in MANIFEST["specimens"][10:])


def test_the_seed_draws_the_twenty_from_the_sorted_listing():
    assert MANIFEST["seed"] == SEED
    subjects = MANIFEST["source"]["subjects_sorted"]
    assert subjects == sorted(subjects) and len(subjects) == MANIFEST["source"]["objects"] == 1000
    order = [f"microscopic-slides/subject_{s}.jpeg" for s in subjects]
    random.Random(SEED).shuffle(order)
    examined = MANIFEST["draw"]["examined"]
    # The examined rows are the shuffled order's first positions, one each, with the recorded label count.
    assert [row["position"] for row in examined] == list(range(1, len(examined) + 1))
    assert [f"microscopic-slides/subject_{row['subject']}.jpeg" for row in examined] == order[:len(examined)]
    drawn = [row["subject"] for row in examined if row.get("label_count") == 2 and row["subject"] not in PILOT]
    assert drawn == [s["subject"] for s in MANIFEST["specimens"][10:]]
    assert all(row.get("skipped") == "pilot" for row in examined if row["subject"] in PILOT)
    # The draw stopped at its twentieth slide.
    assert examined[-1]["subject"] == drawn[-1]
    by_subject = {s["subject"]: s for s in MANIFEST["specimens"]}
    for row in examined:
        if row["subject"] in drawn:
            assert by_subject[row["subject"]]["position"] == row["position"]
