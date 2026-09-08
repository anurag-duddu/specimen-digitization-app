"""Local-only synthetic authority demo for independent browser verification.

Run from repository root with a fresh state directory. This uses the actual API,
SQLite, and a local TCP mock authority; it never accesses institutional Parties.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "tests"))
from test_authority_runtime import assembly
from test_authority_registry import authority_server
from starlette.middleware.cors import CORSMiddleware
import uvicorn

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--state-dir", type=Path, required=True)
parser.add_argument("--port", type=int, default=8014)
parser.add_argument("--origin", action="append", default=[])
args = parser.parse_args()
if args.state_dir.exists():
    raise SystemExit("Choose a fresh synthetic state directory")
if not 1024 <= args.port <= 65535:
    raise SystemExit("Choose an unprivileged loopback port")
if any(
    not (
        origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:")
    )
    for origin in args.origin
):
    raise SystemExit("Only explicit loopback browser origins are allowed")
args.state_dir.mkdir(parents=True)
fixture = authority_server.__wrapped__()
wire = next(fixture)
try:
    app, _, _ = assembly(args.state_dir, wire)
    if args.origin:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=args.origin,
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "Idempotency-Key",
                "Upload-Offset",
                "X-Firebase-AppCheck",
            ],
        )
    print(
        "SYNTHETIC ONLY: local TCP mocked Parties, SQLite, no institutional access or paid inference.",
        flush=True,
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
finally:
    try:
        next(fixture)
    except StopIteration:
        pass
