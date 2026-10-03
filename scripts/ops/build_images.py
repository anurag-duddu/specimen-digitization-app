#!/usr/bin/env python3
"""Build the worker and SAM 3 images with Cloud Build and push them to Artifact Registry.

    uv run --frozen python scripts/ops/build_images.py

Each image is built from `git archive` of one commit (SOURCE_SHA, default HEAD), so no uncommitted or ignored file
reaches the build, and is tagged <registry>/<role>:<SOURCE_SHA>. The registry has immutable tags: a role whose tag
already exists is skipped, so a re-run builds only what is missing. Each role's image digest is printed at the end.

Cloud Build runs as specimen-runtime-build (BUILD_SERVICE_ACCOUNT), which already pushes to the registry. This
script first makes its prerequisites hold, each step idempotent: the Cloud Build API is enabled; the source staging
bucket gs://<PROJECT>_cloudbuild exists; the build identity can read staged sources (storage.objectViewer on that
bucket), write build logs (logging.logWriter on the project) and push images (artifactregistry.writer on the
repository). The operator needs serviceusage, storage, IAM and Cloud Build rights (the project owner has them) and
iam.serviceAccountUser on the build identity.

Parameters (environment): PROJECT, REGION, SOURCE_SHA, ROLES (default "worker sam"), BUILD_SERVICE_ACCOUNT, DRY_RUN=1.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile

import ops_common as ops

CONFIG = Path(__file__).with_name("cloudbuild-image.yaml")
COMMON = ["pyproject.toml", "uv.lock", "README.md", "src"]  # As scripts/ci/build_runtime_image.sh archives them.
DOCKERFILES = {"worker": "containers/worker/Dockerfile", "sam": "containers/worker/sam3.Dockerfile"}
EXTRA = {"sam": ["containers/worker/sam3-requirements.lock"]}


def prerequisites(project: str, region: str, builder: str) -> str:
    member = f"serviceAccount:{builder}"
    staging = f"gs://{project}_cloudbuild"
    ops.run(["gcloud", "services", "enable", "cloudbuild.googleapis.com", f"--project={project}", "--quiet"])
    if ops.read(["gcloud", "storage", "buckets", "describe", staging, f"--project={project}",
                 "--format=value(name)"]) is None:
        ops.run(["gcloud", "storage", "buckets", "create", staging, f"--project={project}", f"--location={region}",
                 "--uniform-bucket-level-access"])
    ops.run(["gcloud", "storage", "buckets", "add-iam-policy-binding", staging, f"--member={member}",
             "--role=roles/storage.objectViewer", "--condition=None", "--quiet"])
    ops.run(["gcloud", "projects", "add-iam-policy-binding", project, f"--member={member}",
             "--role=roles/logging.logWriter", "--condition=None", "--quiet"])
    ops.run(["gcloud", "artifacts", "repositories", "add-iam-policy-binding", "specimen-runtime",
             f"--location={region}", f"--project={project}", f"--member={member}",
             "--role=roles/artifactregistry.writer", "--condition=None", "--quiet"])
    return staging


def image_digest(image: str) -> str | None:
    out = ops.read(["gcloud", "artifacts", "docker", "images", "describe", image,
                    "--format=value(image_summary.digest)"])
    return out.strip() if out and out.strip().startswith("sha256:") else None


def build(role: str, sha: str, project: str, region: str, builder: str, staging: str) -> str:
    image = f"{ops.registry()}/{role}:{sha}"
    found = image_digest(image)
    if found:
        ops.note(f"{role}: {image} already exists; not rebuilt")
    else:
        with tempfile.TemporaryDirectory(prefix=f"specimen-{role}-source-") as work:
            archive = str(Path(work, "source.tar.gz"))
            ops.run(["git", "archive", "--format=tar.gz", f"--output={archive}", sha, *COMMON, DOCKERFILES[role],
                     *EXTRA.get(role, [])])
            ops.run(["gcloud", "builds", "submit", archive, f"--config={CONFIG}", f"--project={project}",
                     f"--region={region}", f"--service-account=projects/{project}/serviceAccounts/{builder}",
                     f"--gcs-source-staging-dir={staging}/source",
                     f"--substitutions=_DOCKERFILE={DOCKERFILES[role]},_IMAGE={image},_SOURCE_SHA={sha}"])
        found = image_digest(image)
        if not found and not ops.dry_run():
            raise SystemExit(f"{role}: the build finished but {image} has no digest")
    return f"{ops.registry()}/{role}@{found or '<digest>'}"


def main() -> int:
    project, region, sha = ops.project(), ops.region(), ops.source_sha()
    roles = ops.param("ROLES", "worker sam").split()
    if not roles or set(roles) - set(DOCKERFILES):
        raise SystemExit(f"ROLES must name images among: {' '.join(DOCKERFILES)}")
    builder = ops.param("BUILD_SERVICE_ACCOUNT", f"specimen-runtime-build@{project}.iam.gserviceaccount.com")
    staging = prerequisites(project, region, builder)
    images = [build(role, sha, project, region, builder, staging) for role in roles]
    for line in images:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
