"""Capture synthetic graph HTTP contracts; pass a new output filename."""

import sys, json, tempfile, hashlib
from pathlib import Path

sys.path.insert(0, "tests")
from test_active_graph import app_at
from test_application import (
    intake,
    PREFIX,
    HEADERS,
    SYNTHETIC_ORG,
    SYNTHETIC_COLLECTION,
)
from fastapi.testclient import TestClient
from specimen_digitization.application.domain import Principal, Scope
from specimen_digitization.application.storage import digest

target = Path(sys.argv[1])
if target.exists():
    raise SystemExit("Refusing to replace an existing fixture")
root = Path(tempfile.mkdtemp(prefix="specimen-graph-wire-"))
app = app_at(root)


def capture(response):
    return {"status": response.status_code, "body": response.json()}


with TestClient(app) as http:
    row = intake(http)
    repo = app.state.workflow.repository
    p = Principal(
        user_id="synthetic-reviewer",
        scope=Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION),
        role="reviewer",
    )
    specimen = repo.get(p.scope, row["specimen_id"])
    specimen.run.observations[0].literal_text = "q" * (2 * 1024 * 1024)
    saved = repo.save(
        p,
        specimen,
        specimen.version,
        "graph-response-fixture",
        digest("synthetic-graph-response"),
    )
    path = PREFIX + "/specimens/" + saved.id
    response = http.get(path + "/workspace", headers=HEADERS)
    assert response.status_code == 413
    details = response.json()["error"]["details"]
    artifact = http.get(details["artifact_url"], headers=HEADERS)
    assert artifact.status_code == 200
    artifact_path = root / "active-graph.json"
    artifact_path.write_bytes(artifact.content)
    assert hashlib.sha256(artifact.content).hexdigest() == details["artifact_sha256"]
    output = {
        "fixture_kind": "synthetic_actual_http_capture",
        "workspace_get": capture(response),
        "summary_get": capture(http.get(path, headers=HEADERS)),
        "artifact_headers": dict(artifact.headers),
        "artifact_envelope_keys": list(artifact.json()),
        "artifact_run_keys": list(artifact.json()["run"]),
    }
    body = {
        "kind": "coverage",
        "after": {"confirmed": True},
        "reason": "Synthetic large artifact coverage review",
        "expected_revision": saved.version,
        "base_record_version_id": f"{saved.run.id}:{saved.version}",
    }
    mutation = http.post(path + "/decisions", headers=HEADERS, json=body)
    assert (
        mutation.status_code == 413
        and mutation.json()["error"]["details"]["mutation_committed"]
    )
    output["committed_mutation"] = {"request": body, "response": capture(mutation)}
    summary = http.get(path, headers=HEADERS).json()
    output["summary_after_mutation"] = summary
    cancel_body = {
        "action": "cancel",
        "reason": "Synthetic oversized workspace recovery",
        "expected_revision": summary["revision"],
    }
    cancel = http.post(
        PREFIX + "/runs/" + summary["active_run_id"] + "/actions",
        headers=HEADERS,
        json=cancel_body,
    )
    assert cancel.status_code == 200
    output["cancel"] = {"request": cancel_body, "response": capture(cancel)}
    target.write_text(json.dumps(output, indent=2) + "\n")
print(root)
