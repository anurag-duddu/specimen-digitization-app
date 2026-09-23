"""Fail-closed API configuration, independent of worker/provider settings."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from .lane_dispatch import JOB_NAME
from .source_registry import RegisteredSource, SourceRegistry

BUILD_FILE = Path(__file__).with_name("_build.json")


def build_provenance(required=False):
    if not BUILD_FILE.exists() and not required:
        return {"source_sha": "unbuilt", "contract_version": "api-runtime-v1"}
    try:
        data = json.loads(BUILD_FILE.read_text())
        if not re.fullmatch(r"[a-f0-9]{40}", data["source_sha"]):
            raise ValueError()
        return {"source_sha": data["source_sha"], "contract_version": "api-runtime-v1"}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError("API image requires valid embedded source provenance") from exc


def exact_origins(values):
    if not values or len(set(values)) != len(values):
        raise ValueError("Explicit unique HTTPS CORS origins required")
    for value in values:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
            or "*" in value
            or parsed.hostname in {"localhost", "127.0.0.1"}
            or parsed.netloc != parsed.hostname
        ):
            raise ValueError("CORS origins must be exact public HTTPS origins")
    return tuple(values)


@dataclass(frozen=True)
class RuntimeConfig:
    port: int
    project: str
    project_number: str
    location: str
    service: str
    connector: str
    bucket: str
    app_ids: tuple[str, ...]
    origins: tuple[str, ...]
    readiness_object: str
    readiness_generation: int
    shutdown_seconds: int = 8
    # LANE.md T1. Absent means no worker start and no sources, as before.
    worker_job: str | None = None
    sources: tuple[RegisteredSource, ...] = ()

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        forbidden = (
            "FIREBASE_AUTH_EMULATOR_HOST",
            "FIREBASE_STORAGE_EMULATOR_HOST",
            "STORAGE_EMULATOR_HOST",
            "FIRESTORE_EMULATOR_HOST",
            "SPECIMEN_SQL_EMULATOR_HOST",
            "FIREBASE_APPCHECK_DEBUG_TOKEN",
            "SPECIMEN_SYNTHETIC_TOKEN",
            "HF_TOKEN",
            "HUGGING_FACE_HUB_TOKEN",
            "HUGGINGFACEHUB_API_TOKEN",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "SPECIMEN_APPROVED_INFERENCE",
        )
        if any(env.get(key) for key in forbidden):
            raise ValueError(
                "Production API rejects emulator, synthetic or provider configuration"
            )
        project = env.get("SPECIMEN_FIREBASE_PROJECT", "")
        if project != "specimen-digitization":
            raise ValueError("Explicit specimen-digitization Firebase project required")
        project_number = env.get("SPECIMEN_FIREBASE_PROJECT_NUMBER", "")
        if not re.fullmatch(r"[1-9][0-9]{0,19}", project_number):
            raise ValueError("Explicit Firebase project number required")
        for key in ("GOOGLE_CLOUD_PROJECT", "GCLOUD_PROJECT"):
            if env.get(key, project) != project:
                raise ValueError("Conflicting Google project configuration")
        keys = (
            "SPECIMEN_SQL_LOCATION",
            "SPECIMEN_SQL_SERVICE",
            "SPECIMEN_SQL_CONNECTOR",
        )
        parts = [env.get(key, "") for key in keys]
        if any(not re.fullmatch(r"[a-z][a-z0-9-]{1,62}", part) for part in parts):
            raise ValueError("Explicit SQL location, service and connector required")
        bucket = env.get("SPECIMEN_GCS_BUCKET", "")
        if bucket != "specimen-digitization.firebasestorage.app":
            raise ValueError("Approved specimen storage bucket required")
        app_ids = tuple(env.get("SPECIMEN_FIREBASE_APP_IDS", "").split(","))
        if any(
            not re.fullmatch(r"1:[0-9]+:(web|android|ios):[a-f0-9]+", value)
            for value in app_ids
        ):
            raise ValueError("Explicit Firebase App Check app IDs required")
        if any(value.split(":")[1] != project_number for value in app_ids):
            raise ValueError(
                "Firebase app IDs must belong to configured project number"
            )
        origins = exact_origins(env.get("SPECIMEN_CORS_ORIGINS", "").split(","))
        try:
            port = int(env.get("PORT", "8080"))
        except ValueError as exc:
            raise ValueError("PORT must be a TCP port") from exc
        if not 1 <= port <= 65535:
            raise ValueError("PORT must be a TCP port")
        readiness_object = env.get("SPECIMEN_READINESS_OBJECT", "")
        generation = env.get("SPECIMEN_READINESS_GENERATION", "")
        if (
            not readiness_object
            or len(readiness_object) > 1024
            or not re.fullmatch(r"[1-9][0-9]{0,19}", generation)
        ):
            raise ValueError("Frozen readiness object and generation required")
        worker_job, sources = lane_settings(env, project, bucket)
        return cls(
            port,
            project,
            project_number,
            *parts,
            bucket,
            app_ids,
            origins,
            readiness_object,
            int(generation),
            worker_job=worker_job,
            sources=sources,
        )


def lane_settings(env, project, bucket):
    """The worker job the API starts and the sources it imports from (LANE.md T1)."""
    job = env.get("SPECIMEN_WORKER_JOB") or None
    if job is not None and (
        not JOB_NAME.fullmatch(job) or job.split("/")[1] != project
    ):
        raise ValueError("SPECIMEN_WORKER_JOB must name a job in the configured project")
    try:
        items = json.loads(env.get("SPECIMEN_SOURCE_REGISTRY_JSON") or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("SPECIMEN_SOURCE_REGISTRY_JSON must be a JSON list") from exc
    if not isinstance(items, list):
        raise ValueError("SPECIMEN_SOURCE_REGISTRY_JSON must be a JSON list")
    # A validation error names the field, never the private value.
    sources = tuple(RegisteredSource.model_validate(item) for item in items)
    if any(source.bucket != bucket for source in sources):
        raise ValueError("Every source must be in the approved bucket")
    SourceRegistry(sources)  # Each source and each collection prefix once.
    return job, sources
