"""Explicit local server and worker entry points; never deploys resources."""

import argparse
import os
from pathlib import Path
import uvicorn
from .api import local_app, create_app
from .production import GcsBlobs, ProductionAdapters, SqlConnectRepository


def production_app():
    import firebase_admin
    from firebase_admin import auth, app_check

    if os.getenv("FIREBASE_AUTH_EMULATOR_HOST"):
        raise ValueError("Production rejects Firebase Auth emulator configuration")
    try:
        firebase_app = firebase_admin.get_app()
    except ValueError:
        firebase_app = firebase_admin.initialize_app(
            options={"projectId": "specimen-digitization"}
        )
    repository = SqlConnectRepository()
    blobs = GcsBlobs()

    def verify(token, check_token):
        try:
            claims = auth.verify_id_token(token, app=firebase_app, check_revoked=True)
            app_check.verify_token(check_token, app=firebase_app)
            return claims["uid"]
        except Exception as exc:
            raise PermissionError("Firebase identity or App Check rejected") from exc

    return create_app(
        mode="production",
        repository=repository,
        blobs=blobs,
        adapters=ProductionAdapters(blobs),
        identity_verifier=verify,
        memberships=repository.memberships,
        origins=["https://specimen-digitization.web.app"],
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["synthetic", "production"], required=True)
    parser.add_argument(
        "--state-dir", type=Path, default=Path("/tmp/specimen-synthetic")
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--persistence", choices=["sqlite", "sql-emulator"], default="sqlite"
    )
    args = parser.parse_args()
    from ..observability import configure_observability, CaptureMode

    configure_observability(
        send_to_logfire=False if args.mode == "synthetic" else None,
        capture_mode=CaptureMode.METADATA,
    )
    if args.mode == "synthetic":
        token = os.getenv("SPECIMEN_SYNTHETIC_TOKEN")
        if not token:
            parser.error("Set SPECIMEN_SYNTHETIC_TOKEN for local bearer access")
        app = local_app(args.state_dir, token, args.persistence)
    else:
        app = production_app()
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
