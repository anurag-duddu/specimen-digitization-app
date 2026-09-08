"""Runnable HTTP synthetic journey, with source fixture rendered from declared text."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import httpx
from PIL import Image, ImageDraw
from .api import SYNTHETIC_COLLECTION, SYNTHETIC_ORG, SYNTHETIC_TEXT


def fixture():
    image = Image.new("RGB", (1000, 520), "white")
    ImageDraw.Draw(image).multiline_text(
        (20, 20),
        "SYNTHETIC FIXTURE - NOT MUSEUM DATA\n" + SYNTHETIC_TEXT,
        fill="black",
        spacing=6,
    )
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def journey(client, source: bytes | None = None):
    prefix = f"/v1/organizations/{SYNTHETIC_ORG}"

    def request(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    session = request("GET", "/v1/session")
    batch = request(
        "POST",
        prefix + "/batches",
        json={
            "collection_id": SYNTHETIC_COLLECTION,
            "display_name": "Synthetic HTTP demonstration",
        },
    )
    data = source if source is not None else fixture()
    item_input = {
        "client_item_id": "demo-one",
        "filename": "synthetic-label.png",
        "media_type": "image/png",
        "size_bytes": len(data),
        "width": 1000,
        "height": 520,
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    item = request(
        "POST", prefix + f"/batches/{batch['batch_id']}/items", json=item_input
    )
    if item["state"] == "duplicate":
        ident = item["duplicate_specimen_id"]
        upload = item
        complete = request("GET", prefix + f"/specimens/{ident}")
    elif item["state"] == "accepted":
        ident = item["specimen_id"]
        upload = item
        complete = request("GET", prefix + f"/specimens/{ident}")
    else:
        upload = item
        offset = upload["offset"]
        for start in range(offset, len(data), 1024):
            upload = request(
                "PUT",
                prefix + f"/uploads/{item['upload_id']}/content",
                headers={"Upload-Offset": str(start)},
                content=data[start : start + 1024],
            )
        complete = request(
            "POST",
            prefix + f"/uploads/{item['upload_id']}/complete",
            json={"expected_revision": upload["revision"]},
        )
        ident = complete["specimen_id"]
    import time

    workspace = None
    for _ in range(300):
        response = client.post(prefix + f"/specimens/{ident}/process")
        if response.status_code == 409:
            time.sleep(0.1)
            continue
        response.raise_for_status()
        workspace = response.json()
        if workspace.get("disposition") is not None:
            break
        if workspace.get("status") == "processing_blocked":
            raise RuntimeError(workspace.get("blocker"))
        time.sleep(0.1)
    if workspace is None or workspace.get("disposition") is None:
        raise RuntimeError("Synthetic processing did not finish within bounded wait")
    decision = {
        "expected_revision": workspace["revision"],
        "base_record_version_id": workspace["record_version_id"],
        "kind": "approve",
        "reason": "Reviewed explicit synthetic fixture source and evidence",
    }
    reviewed = request(
        "POST",
        prefix + f"/specimens/{ident}/decisions",
        headers={"Idempotency-Key": "demo-approve-" + str(workspace["revision"])},
        json=decision,
    )
    assert reviewed["disposition"] == "cleared", reviewed["reason_codes"]
    return {
        "session": session,
        "batch_response": batch,
        "item_request": item_input,
        "item_response": item,
        "upload_response": upload,
        "complete_response": complete,
        "workspace_response": workspace,
        "decision_request": decision,
        "decision_response": reviewed,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    token = os.environ["SPECIMEN_SYNTHETIC_TOKEN"]
    if not args.url.startswith(("http://127.0.0.1:", "http://localhost:")):
        parser.error("Synthetic fixture only targets local API")
    with httpx.Client(
        base_url=args.url,
        headers={
            "Authorization": "Bearer " + token,
            "Idempotency-Key": "synthetic-demo",
        },
        timeout=60,
    ) as client:
        result = journey(client)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "mode": "synthetic",
                "specimen_id": result["decision_response"]["specimen_id"],
                "disposition": result["decision_response"]["disposition"],
                "revision": result["decision_response"]["revision"],
            }
        )
    )


if __name__ == "__main__":
    main()
