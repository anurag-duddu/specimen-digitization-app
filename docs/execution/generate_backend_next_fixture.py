"""Generate a NEW synthetic fixture from real API and loopback authority calls.

Run from repository root: uv run python docs/execution/generate_backend_next_fixture.py /tmp/new-fixture.json
The target must not exist. UUIDs/timestamps are fresh; this never overwrites the frozen reviewed fixture.
"""

import sys, json, tempfile
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "tests"))
from test_authority_runtime import assembly
from test_authority_registry import authority_server
from test_application import HEADERS, PREFIX, intake, image_bytes
from fastapi.testclient import TestClient
from specimen_digitization.application.reading_evidence import (
    ReadingEvidenceInput,
    align_readings,
)

if len(sys.argv) != 2:
    raise SystemExit(
        "Supply a new output JSON path; existing files are never overwritten"
    )
output_path = Path(sys.argv[1])
if output_path.exists():
    raise SystemExit("Output already exists")
fixture = authority_server.__wrapped__()
wire = next(fixture)
try:
    root = Path(tempfile.mkdtemp(prefix="specimen-next-wire-"))
    app, state, _ = assembly(root, wire)
    with TestClient(app) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        work = http.get(path + "/workspace", headers=HEADERS).json()
        revision = work["revision"]

        def get(route):
            response = http.get(path + route, headers=HEADERS)
            assert response.status_code == 200, response.text
            return response.json()

        outputs = {
            "fixture_kind": "synthetic_application_responses_with_local_tcp_authority_fixture",
            "contract_version": "backend-next-v1",
            "collections": http.get(PREFIX + "/collections", headers=HEADERS).json(),
            "workspace_before_selection": work,
            "lookup_phase": get(f"/phases/lookup?revision={revision}"),
            "authority_result": get(
                f"/authority-results/parties?field_key=identified_by_irn&revision={revision}"
            ),
            "reading_alignment": get(
                "/disagreements/"
                + work["run"]["regions"][0]["id"]
                + f"?revision={revision}"
            ),
            "reading_metadata": get(
                "/observations/"
                + work["run"]["observations"][0]["id"]
                + f"/metadata?revision={revision}"
            ),
        }
        for kind, key, extra in [
            (
                "authority_resolution",
                "fixture-qualified-selection",
                {
                    "target_id": "identified_by_irn",
                    "after": {
                        "tool_id": "parties",
                        "field_key": "identified_by_irn",
                        "identifier": "emu:/fmnh/eparties/7",
                    },
                },
            ),
            ("approve", "fixture-approval", {}),
        ]:
            body = {
                "kind": kind,
                "reason": "Synthetic fixture review",
                "expected_revision": work["revision"],
                "base_record_version_id": work["record_version_id"],
                **extra,
            }
            response = http.post(
                path + "/decisions",
                headers={**HEADERS, "Idempotency-Key": key},
                json=body,
            )
            assert response.status_code == 200, response.text
            work = response.json()
            outputs[kind] = {"request": body, "response": work}
        assert work["disposition"] == "cleared"
        from specimen_digitization.application.api import SYNTHETIC_COLLECTION

        outputs["search_page"] = http.get(
            PREFIX + "/specimens",
            params={
                "collection_id": SYNTHETIC_COLLECTION,
                "specimen_id": work["specimen_id"],
                "risk_min": 0,
                "risk_max": 100,
            },
            headers=HEADERS,
        ).json()
        outputs["server_preflight_default_policy"] = http.post(
            PREFIX + "/images/preflight",
            params={"collection_id": SYNTHETIC_COLLECTION},
            headers={**HEADERS, "Content-Type": "image/png"},
            content=image_bytes(),
        ).json()
        access_path = PREFIX + "/assets/" + work["asset"]["id"] + "/access"
        outputs["asset_access"] = http.get(access_path, headers=HEADERS).json()

        def reading(id, text):
            return ReadingEvidenceInput(
                observation_id=id,
                region_id="synthetic-unicode-example",
                source_ref="synthetic:inline",
                text=text,
            )

        outputs["standalone_unicode_alignment_example"] = align_readings(
            reading("left", "😀a\r\nb"), reading("right", "😀a\r\nc")
        ).model_dump(mode="json")
        outputs["standalone_bounded_alignment_example"] = align_readings(
            reading("left", "a" * 100001), reading("right", "b" * 100001)
        ).model_dump(mode="json")
        with output_path.open("x") as output_file:
            output_file.write(json.dumps(outputs, indent=2, ensure_ascii=False) + "\n")
        print(root)
finally:
    try:
        next(fixture)
    except StopIteration:
        pass
