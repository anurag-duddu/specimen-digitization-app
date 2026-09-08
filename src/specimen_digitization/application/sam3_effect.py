"""Trusted child-only SAM request: identity acquisition, bounded HTTP and decode."""

import base64
import json


def sam3_request(payload):
    from google.auth.transport.requests import Request
    from google.oauth2.id_token import fetch_id_token

    bearer = fetch_id_token(Request(), payload["endpoint"])
    return sam3_exchange(payload, bearer)


def sam3_exchange(payload, bearer):
    import httpx
    from .domain import Region

    with httpx.Client(
        timeout=payload["timeout_seconds"], follow_redirects=False
    ) as client:
        with client.stream(
            "POST",
            payload["endpoint"] + "/v1/segment",
            headers={
                "Authorization": "Bearer " + bearer,
                "Idempotency-Key": payload["request"]["run_id"] + ":segment",
            },
            json=payload["request"],
        ) as response:
            raw = bytearray()
            for chunk in response.iter_raw(chunk_size=8192):
                if len(raw) + len(chunk) > payload["max_response_bytes"]:
                    raise ValueError("SAM response byte limit")
                raw.extend(chunk)
            raw = bytes(raw)
            validation = "http_error"
            if response.status_code == 200:
                value = json.loads(raw)
                if (
                    value.get("model_revision") != payload["request"]["model_revision"]
                    or value.get("model_id") != "facebook/sam3"
                ):
                    validation = "unpinned_response"
                else:
                    regions = [Region.model_validate(item) for item in value["regions"]]
                    request = payload["request"]
                    valid = 0 < len(regions) <= 64 and all(
                        r.method == "sam3"
                        and r.version == request["model_revision"]
                        and r.mask_ref
                        and r.asset_id == request["asset_id"]
                        and r.x + r.width <= request["width"]
                        and r.y + r.height <= request["height"]
                        for r in regions
                    )
                    validation = "valid" if valid else "invalid_region_provenance"
            return json.dumps(
                {
                    "http_status": response.status_code,
                    "validation": validation,
                    "body_base64": base64.b64encode(raw).decode(),
                },
                separators=(",", ":"),
            ).encode()
