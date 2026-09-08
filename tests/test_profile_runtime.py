"""Selected published variants affect actual runtime behavior and retain history."""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_application import HEADERS, PREFIX, TOKEN, SYNTHETIC_ORG, intake
from test_hardening_concurrency import repository
from test_sam3_runtime import local_sam_effect

from specimen_digitization.application.api import create_app, SYNTHETIC_TEXT
from specimen_digitization.application.collection_runtime import application_registry
from specimen_digitization.application.collection_profiles import (
    CollectionNode,
    LanguageHandlingRule,
    PolicyReference,
    ProfileMapping,
)
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.application.workflow import SyntheticAdapters
from specimen_digitization.application.production import (
    Sam3Service,
    actor_uid,
    sql_emulator_host,
)
from specimen_digitization.application.domain import Scope
from specimen_digitization.application.review_risk import synthetic_risk_policies


def exercise_profile_variants(tmp_path, monkeypatch, kind):
    if kind == "sql":
        if os.getenv("SPECIMEN_TEST_SQL_EMULATOR") != "true":
            pytest.skip("Requires explicitly enabled isolated local SQL emulator")
        import httpx
        import test_application
        import specimen_digitization.application.api as api

        collection = str(uuid4())
        host = sql_emulator_host()
        query = f'''mutation @transaction {{ collection_insert(data:{{organizationId:"{SYNTHETIC_ORG}",id:"{collection}",name:"Policy fixture"}}) collectionMember_insert(data:{{organizationId:"{SYNTHETIC_ORG}",collectionId:"{collection}",uid:"synthetic-reviewer",active:true,role:"reviewer",canViewSensitive:true}}) }}'''
        result = httpx.post(
            f"http://{host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service:executeGraphql",
            json={"query": query},
        ).json()
        assert not result.get("errors") and not result.get("code")
        monkeypatch.setattr(test_application, "SYNTHETIC_COLLECTION", collection)
        monkeypatch.setattr(api, "SYNTHETIC_COLLECTION", collection)
    else:
        from test_application import SYNTHETIC_COLLECTION

        collection = SYNTHETIC_COLLECTION
    registry = application_registry(True)
    original = registry.profiles[0]
    alternative = original.model_copy(
        update={
            "id": "synthetic-alternative-profile",
            "version": "synthetic-rules-test2",
            "collection_id": "synthetic-alternative-node",
            "language_handling": LanguageHandlingRule(unknown="review"),
            "scoring_policy_ref": PolicyReference.model_validate(
                synthetic_risk_policies().entries[1].policy.reference.model_dump()
            ),
            "segmentation_settings": original.segmentation_settings.model_copy(
                update={"prompt": "paper specimen labels"}
            ),
        }
    )
    registry = registry.model_copy(
        update={
            "profiles": (*registry.profiles, alternative),
            "mappings": (
                *registry.mappings,
                ProfileMapping(
                    collection_id=alternative.collection_id,
                    profile_id=alternative.id,
                    profile_version=alternative.version,
                ),
            ),
            "nodes": (
                *registry.nodes,
                CollectionNode(
                    id=alternative.collection_id, name="Alternative test collection"
                ),
            ),
        }
    )
    blobs = LocalBlobs(tmp_path / "blobs")
    import io
    from PIL import Image

    mask_output = io.BytesIO()
    Image.new("L", (120, 80), 255).save(mask_output, "PNG")
    mask = blobs.put(mask_output.getvalue())
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(request)
            raw = json.dumps(
                {
                    "model_id": request["model_id"],
                    "model_revision": request["model_revision"],
                    "regions": [
                        {
                            "asset_id": request["asset_id"],
                            "x": 0,
                            "y": 0,
                            "width": request["width"],
                            "height": request["height"],
                            "order": 0,
                            "method": "sam3",
                            "version": request["model_revision"],
                            "mask_ref": mask,
                        }
                    ],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    service = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv(
        "SPECIMEN_TEST_SAM_ORIGIN", f"http://127.0.0.1:{service.server_port}"
    )

    class Adapters(SyntheticAdapters):
        def segment(self, specimen):
            return Sam3Service(
                "https://synthetic.run.app", blobs, effect=local_sam_effect
            ).segment(specimen)

    def make_app():
        return create_app(
            mode="synthetic",
            repository=repository(tmp_path, kind),
            blobs=blobs,
            adapters=Adapters(
                blobs, "Sample 12\n" + SYNTHETIC_TEXT, "Sample 13\n" + SYNTHETIC_TEXT
            ),
            token=TOKEN,
            profile_registry=registry,
        )

    try:
        with TestClient(make_app()) as http:
            row = intake(http)
            path = PREFIX + "/specimens/" + row["specimen_id"]
            first = http.get(path + "/workspace", headers=HEADERS).json()
            assert first["disposition"] == "needs_human_review", first["blocker"]
            assert requests[-1]["prompt"] == original.segmentation_settings.prompt
            assert (
                first["run"]["profile"]["language_handling"]["unknown"] == "unmeasured"
            )
            response = http.post(
                path + "/classification",
                headers=HEADERS,
                json={
                    "profile_collection_id": alternative.collection_id,
                    "reason": "Select second explicitly published test policy",
                    "expected_revision": first["revision"],
                    "collection_id": collection,
                },
            )
            assert response.status_code == 200, response.text[:300]
            second = http.get(path + "/workspace", headers=HEADERS).json()
            assert requests[-1]["prompt"] == "paper specimen labels"
            assert requests[-1]["parameters"] == {}
            assert second["run"]["profile"]["language_handling"]["unknown"] == "review"
            assert (
                second["run"]["profile_rules"]["profile_version"] == alternative.version
            )
            left = first["run"]["review_risk"]["labels"][0]
            right = second["run"]["review_risk"]["labels"][0]
            assert left["policy_reference"] != right["policy_reference"]
            assert left["composite"] is None and right["composite"] is None
            assert sum(c["contribution"] for c in left["components"]) == 40
            assert sum(c["contribution"] for c in right["components"]) == 60
            assert second["run"]["review_risk"]["fields"]
            retained = http.get(
                path + "/history/" + str(first["revision"]), headers=HEADERS
            ).json()
            assert retained["run"] == first["run"]
        with TestClient(make_app()) as http:
            reopened = http.get(path + "/workspace", headers=HEADERS).json()
            assert reopened["run"] == second["run"]
            assert (
                reopened["run"]["segmentation"]["settings"]["prompt"]
                == "paper specimen labels"
            )
        return {"first": first, "second": second, "sam_requests": requests}

    finally:
        service.shutdown()
        service.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("kind", ["sqlite", "sql"])
def test_selected_profile_changes_language_risk_and_actual_sam_request_with_history(
    tmp_path, monkeypatch, kind
):
    exercise_profile_variants(tmp_path, monkeypatch, kind)
