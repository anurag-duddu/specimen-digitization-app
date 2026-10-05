"""Optional workflow-only warm/drain/cool sequence; ordinary releases never run it."""
from __future__ import annotations

import os
import subprocess
import sys

from deploy_models import LOCATION, read, release_context


def minimums(resource):
    return (int(resource.get("metadata", {}).get("annotations", {}).get("run.googleapis.com/minScale", "0")),
        int(resource.get("spec", {}).get("template", {}).get("metadata", {}).get("annotations", {}).get(
            "autoscaling.knative.dev/minScale", "0")))


def scale(wanted):
    env = {**os.environ, "CLOUDSDK_CORE_DISABLE_PROMPTS": "1"}
    command = ["gcloud", "run", "services", "update", "specimen-sam", *LOCATION,
        f"--min={wanted}", f"--min-instances={wanted}", "--quiet"]
    # Warming waits for the pinned 600s startup probe; cooling must not start a
    # replacement instance merely to check its startup.
    command.append("--deploy-health-check" if wanted else "--no-deploy-health-check")
    subprocess.run(command, env=env, check=True)
    subprocess.run(["gcloud", "run", "services", "update-traffic", "specimen-sam", *LOCATION,
        "--to-latest", "--clear-tags", "--quiet"], env=env, check=True)
    resource = read("services", "specimen-sam")
    if minimums(resource) != (wanted, wanted):
        raise ValueError("SAM service and revision minimums differ from the requested value")
    if wanted and not any(row.get("type") == "Ready" and row.get("status") == "True"
        for row in resource.get("status", {}).get("conditions", [])):
        raise ValueError("SAM did not become ready before worker execution")
    print(f"SAM service and revision minimums verified at {wanted}", flush=True)


def main(action):
    release_context(os.environ)
    if action == "cool":
        scale(0)
    elif action == "process":
        try:
            scale(1)
            # No args, environment, task count or timeout overrides: execute the
            # immutable job definition verified by the preceding release step.
            subprocess.run(["gcloud", "run", "jobs", "execute", "specimen-worker", *LOCATION,
                "--wait", "--quiet"], check=True)
        finally:
            scale(0)
    else:
        raise ValueError("usage: process_worker.py process|cool")


if __name__ == "__main__":
    try:
        main(sys.argv[1] if len(sys.argv) == 2 else "")
    except (ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f"queued worker processing failed: {error}")
