#!/usr/bin/env python3
"""Standing least-privilege grants for the worker and SAM 3 identities, and the API's right to start the worker.

    uv run --frozen python scripts/ops/iam.py

Run it before deploy.py (the SAM 3 revision cannot start without its checkpoint read) and again after it: grants on
the specimen-sam service and the specimen-worker job are skipped, and named, while those do not exist yet.

Every grant is one `add-iam-policy-binding`, which changes nothing when the binding is already there, so a re-run is
safe. None is time-limited. Seven bucket rows carry a resource condition, three conditions in all, because the
bucket also holds the source slides and private originals: application objects only, the research harness's three
prefixes (the worker only), and SAM 3's listing of its own checkpoint prefix. It grants no secret access: each
runtime secret is already granted at the one version the runtime mounts (a version condition), and an
unconditioned binding beside it would open every version.

SAM 3's bucket listing is the one unconditioned bucket grant (see LIST_BUCKET).
  worker  specimenRuntimeConnector on the project (the connector's named operations); objectViewer and
          objectCreator on application objects, and on the research-capture/, research-journal/ and research-media/
          objects (create and get; the condition has no listing clause); run.invoker on specimen-sam
          (segmentation) and on specimen-worker (the drain's deadline hand-over).
  sam     objectViewer and objectCreator on application objects; objectViewer for listing the checkpoint prefix
          (the read-only mount); legacyBucketReader on the bucket, unconditioned, for the mount itself.
  api     run.invoker on specimen-worker: the API starts executions with jobs:run and no overrides
          (lane_dispatch.py), which needs run.jobs.run only, not actAs on the worker identity.

Parameters (environment): PROJECT, REGION (must match runtime_settings), SAM_CHECKPOINT_SHA256, DRY_RUN=1.
The operator needs setIamPolicy on the project, bucket, service and job (the project owner has it).
"""
from __future__ import annotations

from collections import namedtuple
import json
from pathlib import Path
import sys
import tempfile

import ops_common as ops

settings = ops.settings
Grant = namedtuple("Grant", "member role kind name condition reason")
VIEW, CREATE, INVOKE = "roles/storage.objectViewer", "roles/storage.objectCreator", "roles/run.invoker"
LISTING = 'api.getAttribute("storage.googleapis.com/objectListPrefix", "")'
# The checkpoint mount's gcsfuse calls GetStorageLayout on the bucket and returns its error; gcsfuse v3.11.4 sends
# it with Prefix "", v3.12.0 with the only-dir prefix (internal/storage/storage_handle.go), and Cloud Run does not
# publish which release it runs. The call "Requires the storage.objects.list IAM permission on the bucket", the
# prefix being "used for permission check" (docs.cloud.google.com/storage/docs/reference/rpc/
# google.storage.control.v2), and an empty prefix fails the listing condition above. This role holds
# storage.buckets.get, storage.objects.list and folder, managed-folder and multipart-upload get/list, and no
# storage.objects.get (`gcloud iam roles describe roles/storage.legacyBucketReader`). Granted on the whole bucket,
# it lets SAM 3 list every object's name and metadata, source slides and originals included; object contents stay
# readable only under application/sha256/, through the APP-conditioned objectViewer.
LIST_BUCKET = "roles/storage.legacyBucketReader"


def conditions(bucket: str, digest: str) -> tuple[tuple[str, str], tuple[str, str], tuple[str, str]]:
    """(expression, title) of the application-objects, the checkpoint-listing and the research-objects conditions."""
    objects = f"projects/_/buckets/{bucket}/objects/"
    app = (f'resource.name.startsWith("{objects}application/sha256/")', "specimen_application_objects")
    listing = (f'{LISTING}.startsWith("application/sha256/{digest}/sam3-cache")', "specimen_sam3_checkpoint_listing")
    research = (" || ".join(f'resource.name.startsWith("{objects}research-{kind}/")'
                            for kind in ("capture", "journal", "media")), "specimen_research_objects")
    return app, listing, research


def grants(project: str, digest: str) -> list[Grant]:
    bucket = settings.BUCKET
    app, listing, research = conditions(bucket, digest)
    worker, sam, api = (f"serviceAccount:{settings.ROLES[role]['service_account']}" for role in ("worker", "sam", "api"))
    table = [Grant(worker, f"projects/{project}/roles/specimenRuntimeConnector", "project", project, None,
                   "call the connector's named operations only")]
    for member, who in ((worker, "worker"), (sam, "sam")):
        table += [Grant(member, role, "bucket", bucket, app, "read and write application objects; no delete")
                  for role in (VIEW, CREATE)]
        if who == "sam":
            table.append(Grant(sam, VIEW, "bucket", bucket, listing, "list the checkpoint prefix it mounts read-only"))
            table.append(Grant(sam, LIST_BUCKET, "bucket", bucket, None,
                               "mount the checkpoint: the bucket and object listing at mount time; no object reads"))
    # The research harness (SPECIMEN_RESEARCH_HARNESS=on) creates objects with a generation match and reads them
    # back, under these three prefixes. It never lists or deletes, so the worker, and only the worker, gets this pair.
    table += [Grant(worker, role, "bucket", bucket, research, "read and write research harness objects; no delete")
              for role in (VIEW, CREATE)]
    table += [Grant(worker, INVOKE, "service", "specimen-sam", None, "call SAM 3"),
              Grant(worker, INVOKE, "job", "specimen-worker", None, "hand work left at its deadline to a new execution"),
              Grant(api, INVOKE, "job", "specimen-worker", None, "start executions (jobs:run, no overrides)")]
    return table


def binding_argv(grant: Grant, project: str, region: str) -> list[str]:
    """`gcloud <group> add-iam-policy-binding <resource> <scope>`, without member, role or condition."""
    group, target, scope = {
        "project": (["projects"], grant.name, []),
        "bucket": (["storage", "buckets"], f"gs://{grant.name}", []),
        "service": (["run", "services"], grant.name, [f"--region={region}", f"--project={project}"]),
        "job": (["run", "jobs"], grant.name, [f"--region={region}", f"--project={project}"]),
    }[grant.kind]
    return ["gcloud", *group, "add-iam-policy-binding", target, *scope]


def exists(kind: str, name: str, project: str, region: str) -> bool:
    """Run resources are created by deploy.py; every other resource already exists."""
    if kind not in {"service", "job"} or ops.dry_run():
        return True
    group = "services" if kind == "service" else "jobs"
    return ops.read(["gcloud", "run", group, "describe", name, f"--region={region}", f"--project={project}",
                     "--format=value(metadata.name)"]) is not None


def main() -> int:
    project, region = ops.committed_project(), ops.region()
    digest = ops.checkpoint_sha256()
    skipped = []
    with tempfile.TemporaryDirectory(prefix="specimen-iam-") as work:
        for grant in grants(project, digest):
            if not exists(grant.kind, grant.name, project, region):
                skipped.append(f"{grant.role} for {grant.member} on {grant.kind} {grant.name}")
                continue
            ops.note(grant.reason)
            argv = binding_argv(grant, project, region) + [f"--member={grant.member}", f"--role={grant.role}"]
            if grant.condition is not None:
                expression, title = grant.condition
                path = Path(work, f"{title}.json")
                path.write_text(json.dumps({"expression": expression, "title": title}) + "\n")
                ops.note(f"condition {title}: {expression}")
                argv.append(f"--condition-from-file={path}")
            elif grant.kind != "job":  # gcloud run jobs takes no --condition; elsewhere None never prompts.
                argv.append("--condition=None")
            ops.run(argv + ["--quiet"])
    for line in skipped:
        ops.note(f"skipped until deploy.py creates it: {line}")
    if skipped:
        ops.note("re-run iam.py after deploy.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
