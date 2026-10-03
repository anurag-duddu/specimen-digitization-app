#!/usr/bin/env python3
"""Keep N SAM 3 instances running: 1 for an import run, 0 as soon as it ends. Prints the minimum that results.

    uv run --frozen python scripts/ops/scale_sam.py 1
    uv run --frozen python scripts/ops/scale_sam.py 0

Sets the minimum at both levels, as deploy.py does: the service's (--min) and the serving revision's
(--min-instances). Cloud Run keeps the larger of the two (docs.cloud.google.com/run/docs/configuring/min-instances),
so 0 must be set at both for the last instance to stop. A level that already holds N is left alone, so a re-run
changes nothing. A revision-level change deploys a new revision with the same image and settings, and the deploy
health check, on by default, starts one instance of it and waits for its startup probe (gcloud run services update
--help). When it deploys one for N = 1, the command therefore returns once SAM 3 has loaded its model; warm_sam.py
confirms that either way.

SAM 3 has CPU always allocated (runtime_settings.SAM), so a kept instance is billed for as long as it runs, idle or
not. N = 0 restores the minimum of 0 at both levels.

Parameters (environment): PROJECT, REGION (must match runtime_settings), DRY_RUN=1.
"""
from __future__ import annotations

import json
import sys

import ops_common as ops

SERVICE = "specimen-sam"
# The v1 annotations gcloud sets for --min and --min-instances; for 0 it removes them, so absent means 0
# (googlecloudsdk command_lib/run/flags.py, _GetScalingChanges and _GetServiceScalingChanges).
SERVICE_MIN, REVISION_MIN = "run.googleapis.com/minScale", "autoscaling.knative.dev/minScale"


def minimums(project: str, region: str) -> tuple[int, int] | None:
    """(service-level, revision-level) minimum of the deployed service; None under DRY_RUN=1."""
    out = ops.read(["gcloud", "run", "services", "describe", SERVICE, f"--region={region}", f"--project={project}",
                    "--format=json"])
    if out is None:
        if ops.dry_run():
            return None
        raise SystemExit(f"{SERVICE} is not deployed (or not readable); run deploy.py sam first")
    service = json.loads(out)
    template = service.get("spec", {}).get("template", {})
    return (int(service.get("metadata", {}).get("annotations", {}).get(SERVICE_MIN, "0")),
            int(template.get("metadata", {}).get("annotations", {}).get(REVISION_MIN, "0")))


def main(argv: list[str]) -> int:
    high = ops.settings.SAM["max_instances"]
    if len(argv) != 1 or not argv[0].isdigit() or int(argv[0]) > high:
        raise SystemExit(f"usage: scale_sam.py N, a whole number from 0 to the maximum, {high}")
    wanted = int(argv[0])
    project, region = ops.committed_project(), ops.region()
    before = minimums(project, region)
    flags = []
    if before is None or before[0] != wanted:
        flags.append(f"--min={wanted}")
    if before is None or before[1] != wanted:
        flags.append(f"--min-instances={wanted}")
    if not flags:
        ops.note(f"{SERVICE} already keeps a minimum of {wanted} at both levels; nothing changed")
    else:
        ops.run(["gcloud", "run", "services", "update", SERVICE, f"--region={region}", f"--project={project}",
                 *flags, "--quiet"])
    after = minimums(project, region)
    if after is None:
        return 0
    ops.note(f"{SERVICE} minimum instances: service level {after[0]}, revision level {after[1]}")
    if after != (wanted, wanted):
        raise SystemExit(f"{SERVICE} does not report a minimum of {wanted} at both levels")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
