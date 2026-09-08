"""Create a fresh synthetic HEIC API fixture and source; never overwrite review files."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "tests"))
from fastapi.testclient import TestClient
from test_codec_runtime import codec_app, upload_codec
from test_image_codecs import heic
from test_application import PREFIX, HEADERS

if len(sys.argv) != 2:
    raise SystemExit("Supply a new output JSON path")
output = Path(sys.argv[1])
if output.exists():
    raise SystemExit("Output already exists")
root = Path(tempfile.mkdtemp(prefix="specimen-codec-wire-"))
data = heic(6)
(root / "synthetic-orientation6.heic").write_bytes(data)
with TestClient(codec_app(root)) as http:
    captured = []

    def capture(request):
        if request.url.path.endswith("/items"):
            captured.append(json.loads(request.content))

    http.event_hooks["request"] = [capture]
    accepted = upload_codec(http, data, "image/heic")
    assert accepted.status_code == 200, accepted.text
    row = accepted.json()
    path = PREFIX + "/specimens/" + row["specimen_id"]
    workspace = http.get(path + "/workspace", headers=HEADERS).json()
    access_path = PREFIX + "/assets/" + workspace["asset"]["id"] + "/access"
    content = {
        "fixture_kind": "synthetic_real_heic_local_decoder_application_responses",
        "policy": "explicit synthetic-only HEIC/DNG profile and codec enablement; local-test memory enforcement exception; no institutional approval",
        "item_request": captured[0],
        "completion_response": row,
        "asset": workspace["asset"],
        "asset_access": http.get(access_path, headers=HEADERS).json(),
        "pixel_contract": "ROI uses decoded_heif_primary_pixel_edges; container orientation already applied; view transform identity",
    }
    with output.open("x") as target:
        target.write(json.dumps(content, indent=2) + "\n")
print(root)
