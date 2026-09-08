"""Explicit synthetic-only codec server; optional packages and local test memory exception."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "tests"))
from test_codec_runtime import codec_app
from starlette.middleware.cors import CORSMiddleware
import uvicorn

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--state-dir", type=Path, required=True)
parser.add_argument("--port", type=int, default=8014)
parser.add_argument("--origin", action="append", default=[])
args = parser.parse_args()
if args.state_dir.exists():
    raise SystemExit("Choose a fresh state directory")
if not 1024 <= args.port <= 65535:
    raise SystemExit("Choose an unprivileged loopback port")
if any(
    not origin.startswith(("http://localhost:", "http://127.0.0.1:"))
    for origin in args.origin
):
    raise SystemExit("Explicit loopback browser origins only")
app = codec_app(args.state_dir)
app.add_middleware(
    CORSMiddleware,
    allow_origins=args.origin,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Upload-Offset"],
)
print(
    "SYNTHETIC ONLY: codec/profile enabled with local-test memory exception; not production approval.",
    flush=True,
)
uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
