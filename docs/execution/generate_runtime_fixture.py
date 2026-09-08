"""Capture actual synthetic policy/classifier/telemetry HTTP examples to a new file."""

import json
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

sys.path.insert(0, "tests")
from test_application import HEADERS, PREFIX, TOKEN, intake
from test_profile_runtime import exercise_profile_variants
from test_classifier_runtime import exercise_configured_classifier
from specimen_digitization.application.api import create_app
from specimen_digitization.application.storage import SQLiteRepository, LocalBlobs

target = Path(sys.argv[1])
if target.exists():
    raise SystemExit("Refusing to replace an existing fixture")
root = Path(tempfile.mkdtemp(prefix="specimen-runtime-wire-"))
output = {"fixture_kind": "synthetic_actual_http_capture"}
with MonkeyPatch.context() as patch:
    output["profile_variants"] = exercise_profile_variants(
        root / "policies", patch, "sqlite"
    )
output["configured_classifier"] = exercise_configured_classifier(root / "classifier")


from test_model_runtime import ModelAdapters

blobs = LocalBlobs(root / "telemetry" / "blobs")
with MonkeyPatch.context() as patch:
    patch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    app = create_app(
        mode="synthetic",
        repository=SQLiteRepository(root / "telemetry" / "state.db"),
        blobs=blobs,
        adapters=ModelAdapters(blobs),
        token=TOKEN,
    )
    with TestClient(app) as http:
        row = intake(http)
        work = http.get(
            PREFIX + "/specimens/" + row["specimen_id"] + "/workspace", headers=HEADERS
        ).json()
        assert work["disposition"] == "needs_human_review", work["blocker"]
        assert all(
            o["latency_seconds"] is not None and o["finish_state"] == "stop"
            for o in work["observations"]
        )
        output["observation_telemetry"] = {"workspace": work}
with target.open("x") as stream:
    json.dump(output, stream, indent=1)
    stream.write("\n")
print(root)
