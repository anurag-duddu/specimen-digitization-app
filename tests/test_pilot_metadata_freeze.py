import importlib.util
import json
from pathlib import Path

import pytest

from specimen_digitization.application.pilot_manifest import PrivateManifestError

spec = importlib.util.spec_from_file_location("freeze_pilot", Path(__file__).resolve().parents[1] / "scripts/data/pilot_manifest.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def catalog():
    return {"authorization_reference": "synthetic-authorization", "ordering_evidence": "synthetic ordered catalog",
            "grouping_evidence": "synthetic explicit record associations", "specimens": [
                {"source_record_id": f"synthetic-{i}", "source_objects": [
                    {"bucket": "demo-specimen-source", "object_name": f"source/{i}",
                     "generation": str(i + 1), "size_bytes": 10, "crc32c": "AAAAAA=="}
                ]} for i in range(11)
            ]}


def test_freeze_exact_first_ten_preserves_unknown_sha():
    frozen = module.freeze_metadata(json.dumps(catalog()).encode())
    assert frozen["status"] == "metadata_frozen"
    assert [s["source_record_id"] for s in frozen["specimens"]] == [f"synthetic-{i}" for i in range(10)]
    assert all(s["source_objects"][0]["sha256"] is None for s in frozen["specimens"])


@pytest.mark.parametrize("change", [
    lambda c: c.update(ordering_evidence=""),
    lambda c: c.update(grouping_evidence=""),
    lambda c: c.update(specimens=c["specimens"][:9]),
    lambda c: c["specimens"][0].update(source_objects=[]),
    lambda c: c["specimens"][0]["source_objects"][0].update(crc32c=None),
    lambda c: c["specimens"][1].update(source_record_id=c["specimens"][0]["source_record_id"]),
    lambda c: c["specimens"][0]["source_objects"][0].update(generation="latest"),
])
def test_freeze_fails_without_replacing_bad_record(change):
    value = catalog()
    change(value)
    with pytest.raises(PrivateManifestError):
        module.freeze_metadata(json.dumps(value).encode())
