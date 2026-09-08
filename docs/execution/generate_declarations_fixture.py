"""Capture synthetic declaration HTTP contracts to a new output filename."""

import json
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, "tests")
from test_application import HEADERS, PREFIX, intake
from test_reading_declarations_runtime import app_at

target = Path(sys.argv[1])
if target.exists():
    raise SystemExit("Refusing to replace an existing fixture")
root = Path(tempfile.mkdtemp(prefix="specimen-declarations-wire-"))
output = {"fixture_kind": "synthetic_actual_http_capture", "cases": {}}
for mode in ("mixed", "conflicting", "unknown"):
    with TestClient(app_at(root / mode, mode)) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        work = http.get(path + "/workspace", headers=HEADERS).json()
        obs = work["observations"][0]
        metadata_path = path + "/observations/" + obs["id"] + "/metadata"
        declarations_path = path + "/observations/" + obs["id"] + "/declarations"
        case = {
            "workspace": work,
            "reading_metadata": http.get(metadata_path, headers=HEADERS).json(),
            "declaration_provenance": http.get(
                declarations_path, headers=HEADERS
            ).json(),
        }
        if mode == "mixed":
            case["human_decisions"] = []
            for index, languages in enumerate((["French"], ["Italian"])):
                body = {
                    "kind": "reading_metadata",
                    "target_id": obs["id"],
                    "after": {
                        "language_candidates": languages,
                        "script_candidates": ["Latin"],
                        "language_relation": "unspecified",
                    },
                    "reason": "Synthetic reviewer declaration",
                    "expected_revision": work["revision"],
                    "base_record_version_id": work["record_version_id"],
                }
                response = http.post(
                    path + "/decisions",
                    headers={
                        **HEADERS,
                        "Idempotency-Key": "declaration-fixture-" + str(index),
                    },
                    json=body,
                )
                assert response.status_code == 200, response.text[:200]
                work = response.json()
                case["human_decisions"].append(
                    {
                        "request": body,
                        "status": response.status_code,
                        "response": work,
                        "reading_metadata": http.get(
                            metadata_path, headers=HEADERS
                        ).json(),
                        "declaration_provenance": http.get(
                            declarations_path, headers=HEADERS
                        ).json(),
                    }
                )
        output["cases"][mode] = case
with target.open("x") as stream:
    json.dump(output, stream, indent=1)
    stream.write("\n")
print(root)
