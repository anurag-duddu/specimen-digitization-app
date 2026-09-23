"""Explicit local server and worker entry points; never deploys resources."""

import argparse
import os
from pathlib import Path
from .api import local_app, create_app
from .collection_profiles import published_registry
from .lane_dispatch import dispatcher_from_value
from .production import GcsBlobs, ProductionAdapters, SqlConnectRepository
from .profile_runtime import published_risk_registry
from .source_reader import GcsSourceReader
from .source_registry import SourceRegistry


def lane_wiring(config):
    """The processing lane's production inputs (LANE.md T1); empty when unconfigured."""
    return {
        "source_registry": SourceRegistry(config.sources),
        "source_reader": GcsSourceReader(project=config.project)
        if config.sources
        else None,
        "worker_dispatcher": dispatcher_from_value(config.worker_job),
        # LANE.md T4; a binding to an unknown collection stops the API at start.
        "profile_registry": published_registry(dict(config.collection_bindings)),
        "risk_registry": published_risk_registry(),
    }


def production_app(config=None):
    import firebase_admin
    from .runtime_config import RuntimeConfig, build_provenance
    from .runtime_auth import firebase_verifier
    from .runtime_health import DependencyReadiness, cloud_probe, install_health

    config = config or RuntimeConfig.from_env()
    provenance = build_provenance(required=True)
    try:
        firebase_app = firebase_admin.get_app("specimen-api")
    except ValueError:
        firebase_app = firebase_admin.initialize_app(
            options={"projectId": config.project, "httpTimeout": 5}, name="specimen-api"
        )
    if firebase_app.project_id != config.project:
        raise ValueError("Firebase app project mismatch")
    # firebase-admin 7.5 App Check audience uses app.project_id literally;
    # App Check requires the numeric project number while Auth requires the ID.
    try:
        check_app = firebase_admin.get_app("specimen-api-app-check")
    except ValueError:
        check_app = firebase_admin.initialize_app(
            options={"projectId": config.project_number, "httpTimeout": 5},
            name="specimen-api-app-check",
        )
    if check_app.project_id != config.project_number:
        raise ValueError("App Check project number mismatch")
    blobs = GcsBlobs(bucket=config.bucket)
    repository = SqlConnectRepository(
        project=config.project,
        location=config.location,
        service=config.service,
        connector=config.connector,
        graph_blobs=blobs,
    )
    app = create_app(
        mode="production",
        repository=repository,
        blobs=blobs,
        adapters=ProductionAdapters(blobs),
        identity_verifier=firebase_verifier(firebase_app, config.app_ids, check_app),
        memberships=repository.memberships,
        origins=list(config.origins),
        **lane_wiring(config),
    )
    install_health(
        app,
        mode="production",
        provenance=provenance,
        readiness=DependencyReadiness(cloud_probe(repository, blobs, config)),
    )
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["synthetic", "production"], required=True)
    parser.add_argument(
        "--state-dir", type=Path, default=Path("/tmp/specimen-synthetic")
    )
    parser.add_argument("--port", type=int)
    parser.add_argument(
        "--persistence", choices=["sqlite", "sql-emulator"], default="sqlite"
    )
    args = parser.parse_args()
    config = None
    if args.mode == "production":
        from .runtime_config import RuntimeConfig

        config = RuntimeConfig.from_env()
        if args.port is not None and args.port != config.port:
            parser.error("Production port must come from PORT")
    from ..observability import configure_observability, CaptureMode

    # The API never sends telemetry anywhere. Its deployed environment carries
    # no Logfire credential, and leaving this unset would let the SDK's own
    # default try to reach Logfire — and create a project — while the service is
    # starting. Only the worker sends, through the approved bounded transport
    # (docs/execution/APPROVED_LOGFIRE_TRACING.md); the API and SAM never do.
    configure_observability(
        send_to_logfire=False,
        capture_mode=CaptureMode.METADATA,
    )
    if args.mode == "synthetic":
        token = os.getenv("SPECIMEN_SYNTHETIC_TOKEN")
        if not token:
            parser.error("Set SPECIMEN_SYNTHETIC_TOKEN for local bearer access")
        app = local_app(args.state_dir, token, args.persistence)
        from .runtime_config import build_provenance
        from .runtime_health import install_health

        install_health(
            app, mode="synthetic", provenance=build_provenance(), readiness=lambda: True
        )
        host, port = "127.0.0.1", args.port if args.port is not None else 8000
    else:
        app = production_app(config)
        host, port = "0.0.0.0", config.port
    from .runtime_server import serve

    serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
