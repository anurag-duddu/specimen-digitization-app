"""Committed, non-secret settings of the runtime plane (docs/execution/golive/RELEASE.md section 3.2).

Every value here is public and reviewed: a new secret version, readiness marker
or model checkpoint is a pull request, so the release needs no permission to
discover one. Private values and credentials reach the runtime only as Secret
Manager references, by name and pinned version. PENDING marks a value that is
not known yet; a role that needs one is not deployed, and the receipt names it.
"""
from __future__ import annotations

from specimen_digitization.hub_models import SAM3_MODEL

PENDING = None  # Not known yet; the role that needs it is not deployed.

PROJECT = "specimen-digitization"
PROJECT_NUMBER = "716045864126"
REGION = "us-east4"
PREFIX = f"projects/{PROJECT}/locations/{REGION}"
BUCKET = f"{PROJECT}.firebasestorage.app"
SAM_URL = f"https://specimen-sam-{PROJECT_NUMBER}.{REGION}.run.app"
WORKER_JOB = f"{PREFIX}/jobs/specimen-worker"
WORKER_EMAIL = f"specimen-worker-runtime@{PROJECT}.iam.gserviceaccount.com"

# Secret Manager versions, pinned by number once the owner creates them (T4); never "latest".
SECRET_VERSIONS = {
    "huggingface-runtime-token": 2,
    "specimen-worker-logfire": 1,
    "specimen-google-maps-key": 1,
    "specimen-source-registry": 1,
    "specimen-collection-bindings": 1,
    "specimen-worker-actor-uid": 1,
}

# The API's public 50-byte readiness marker, which the owner uploads; its content is
# "specimen-digitization runtime readiness marker v1\n".
READINESS_OBJECT = "application/sha256/a1c115b623cdc43c1b062e5431c8ca8cb6411aa08057885e3b44a9238747818e"  # pragma: allowlist secret (public marker digest)
READINESS_GENERATION = PENDING
# The owner uploads the SAM 3 checkpoint to application/sha256/<digest>/sam3-cache.
SAM_CHECKPOINT_SHA256 = PENDING

SQL = {"SPECIMEN_SQL_LOCATION": REGION, "SPECIMEN_SQL_SERVICE": "specimen-digitization-service",
       "SPECIMEN_SQL_CONNECTOR": "specimen-server"}

# Each role's secret_env maps an environment variable to the Secret Manager secret it reads.
API = {
    "service_account": f"specimen-api-runtime@{PROJECT}.iam.gserviceaccount.com",
    "cpu": "1", "memory": "1Gi", "max_instances": 2, "concurrency": 8, "timeout_seconds": 600,
    # SPECIMEN_READINESS_GENERATION joins these once READINESS_GENERATION is known.
    "env": {
        "SPECIMEN_FIREBASE_PROJECT": PROJECT, "SPECIMEN_FIREBASE_PROJECT_NUMBER": PROJECT_NUMBER,
        "SPECIMEN_FIREBASE_APP_IDS": "1:716045864126:web:a193fa80c7a98bcac8e2ef,1:716045864126:android:6d2aeda8bc992e16c8e2ef,"  # pragma: allowlist secret (public app ids)
                                     "1:716045864126:ios:b4ae90c54b5beccac8e2ef",
        **SQL, "SPECIMEN_GCS_BUCKET": BUCKET,
        "SPECIMEN_CORS_ORIGINS": "https://specimen-digitization.web.app,https://specimen-digitization.firebaseapp.com",
        "SPECIMEN_READINESS_OBJECT": READINESS_OBJECT, "SPECIMEN_WORKER_JOB": WORKER_JOB,
    },
    "secret_env": {"LOGFIRE_TOKEN": "specimen-worker-logfire", "SPECIMEN_SOURCE_REGISTRY_JSON": "specimen-source-registry",
                   "SPECIMEN_COLLECTION_BINDINGS_JSON": "specimen-collection-bindings"},
}

# A Cloud Run job the release defines and never runs: one task, no parallelism, no retries.
WORKER = {
    "service_account": WORKER_EMAIL, "cpu": "1", "memory": "1Gi", "timeout_seconds": 3600,
    "args": PENDING,  # The processing lane's drain argv, once its server code merges.
    # SPECIMEN_SAM3_CHECKPOINT_SHA256, the same digest SAM 3 serves, joins these once SAM_CHECKPOINT_SHA256 is known.
    "env": {**SQL, "SPECIMEN_GCS_BUCKET": BUCKET, "SPECIMEN_SAM3_ENDPOINT": SAM_URL,
            "SPECIMEN_SAM3_REVISION": SAM3_MODEL.revision, "SPECIMEN_APPROVED_INFERENCE": "true"},
    "secret_env": {"HF_TOKEN": "huggingface-runtime-token", "LOGFIRE_TOKEN": "specimen-worker-logfire",
                   "SPECIMEN_GOOGLE_MAPS_API_KEY": "specimen-google-maps-key",  # pragma: allowlist secret (secret name, not a value)
                   "SPECIMEN_WORKER_ACTOR_UID": "specimen-worker-actor-uid",
                   "SPECIMEN_COLLECTION_BINDINGS_JSON": "specimen-collection-bindings"},
}

SAM = {
    "service_account": f"specimen-sam-runtime@{PROJECT}.iam.gserviceaccount.com",
    # 300 s: two concepts per image plus a cold start; the server stops at 240 s, the worker's segment call at 270 s.
    "cpu": "4", "memory": "16Gi", "max_instances": 1, "concurrency": 1, "timeout_seconds": 300,
    # SPECIMEN_SAM3_CHECKPOINT_SHA256 and the read-only /model-cache mount follow SAM_CHECKPOINT_SHA256.
    "env": {"HF_HOME": "/model-cache", "HF_HUB_OFFLINE": "1", "SPECIMEN_SAM3_AUDIENCE": SAM_URL,
            "SPECIMEN_SAM3_CALLER_EMAIL": WORKER_EMAIL, "SPECIMEN_SAM3_OUTPUT_BUCKET": BUCKET},
    "secret_env": {"LOGFIRE_TOKEN": "specimen-worker-logfire"},
}
SAM_SERVER_ENV = PENDING  # The processing lane's per-run server settings, once merged.

ROLES = {"api": API, "worker": WORKER, "sam": SAM}


def pending(role: str) -> list[str]:
    """Names, never values, of every PENDING setting the role needs; it deploys only when there are none."""
    own = {"api": [], "worker": [('WORKER["args"]', WORKER["args"])], "sam": [("SAM_SERVER_ENV", SAM_SERVER_ENV)]}[role]
    secrets = [(f'SECRET_VERSIONS["{name}"]', SECRET_VERSIONS[name]) for name in ROLES[role]["secret_env"].values()]
    marker = {"api": [("READINESS_GENERATION", READINESS_GENERATION)],
              "worker": [("SAM_CHECKPOINT_SHA256", SAM_CHECKPOINT_SHA256)],
              "sam": [("SAM_CHECKPOINT_SHA256", SAM_CHECKPOINT_SHA256)]}[role]
    return [name for name, value in own + secrets + marker if value is PENDING]
