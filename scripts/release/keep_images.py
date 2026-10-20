"""Keep the images in service out of the registry cleanup; runtime-release.yml runs this after the deploys.

scripts/ops/owner_setup.sh gives the image registry a cleanup policy: an image may go a day after its push
unless it is one of the newest five of its package or carries a tag that starts with "deployed" or "rollback".
This script reads that policy back and must find exactly the committed one. Then, for every service and job the
release defines, it points the tag deployed-<runtime> at the image that runtime runs now and rollback-<runtime>
at the image deployed-<runtime> named before. It deletes nothing and moves no other tag.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy_models import checked_image, collection_routes, release_context, settings  # noqa: E402

REGISTRY = "specimen-runtime"
OWNER_HINT = "the owner runs scripts/ops/owner_setup.sh once"
# The newest five keep the last few releases at hand; what a running service or a rollback needs is held by the
# tags instead, whatever the count.
KEEP_NEWEST = 5
DELETE_AFTER_SECONDS = 24 * 60 * 60
KEEP_TAGS = ("deployed", "rollback")
# The policy is in dry-run mode: Google evaluates it and deletes nothing. Turning it off is its own change, here
# and in owner_setup.sh together.
DRY_RUN = True
# The committed policy, as the registry reports it.
POLICY = {
    "keep-newest": {"id": "keep-newest", "action": "KEEP", "mostRecentVersions": {"keepCount": KEEP_NEWEST}},
    "keep-deployed": {"id": "keep-deployed", "action": "KEEP",
                      "condition": {"tagState": "TAGGED", "tagPrefixes": list(KEEP_TAGS)}},
    "delete-old": {"id": "delete-old", "action": "DELETE",
                   "condition": {"tagState": "ANY", "olderThan": f"{DELETE_AFTER_SECONDS}s"}},
}
# The runtimes every release defines: (image package, Cloud Run kind, name). Collection jobs come from the routes.
RUNTIMES = (("api", "services", "specimen-api"), ("sam", "services", "specimen-sam"),
            ("worker", "jobs", "specimen-worker"), ("api", "jobs", "specimen-intake"))
AT_REGISTRY = [f"--repository={REGISTRY}", f"--location={settings.REGION}", f"--project={settings.PROJECT}"]
ENV = {**os.environ, "CLOUDSDK_CORE_DISABLE_PROMPTS": "1", "CLOUDSDK_CORE_SHOULD_PROMPT_TO_ENABLE_API": "false"}


def gcloud(*argv: str) -> object:
    result = subprocess.run(["gcloud", *argv, "--format=json"], env=ENV, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def canonical(policies: dict) -> dict:
    """The policies with no empty field, upper-case names and whole-second durations, so equal rules compare equal."""
    def clean(value):
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items() if item not in (None, "", [], {})}
        return value
    rules = clean(json.loads(json.dumps(policies)))
    for rule in rules.values():
        rule["action"] = str(rule.get("action", "")).upper()
        condition = rule.get("condition", {})
        if "tagState" in condition:
            condition["tagState"] = str(condition["tagState"]).upper()
        if "tagPrefixes" in condition:
            condition["tagPrefixes"] = sorted(condition["tagPrefixes"])
        for key in ("olderThan", "newerThan"):
            duration = re.fullmatch(r"([0-9]+)(?:\.0*)?s", str(condition.get(key, "")))
            if duration:
                condition[key] = f"{int(duration.group(1))}s"
    return rules


def cleanup_set_up(repository: dict) -> bool:
    """False before the owner setup (no policy, immutable tags), True once it set exactly the committed policy."""
    policies = repository.get("cleanupPolicies") or {}
    immutable = bool((repository.get("dockerConfig") or {}).get("immutableTags"))
    dry_run = bool(repository.get("cleanupPolicyDryRun"))
    if not policies and immutable:
        return False
    if canonical(policies) == canonical(POLICY) and dry_run == DRY_RUN and not immutable:
        return True
    raise ValueError(f"the cleanup settings of {REGISTRY} differ from the committed policy; {OWNER_HINT}")


def runtimes() -> list[tuple[str, str, str]]:
    """Every service and job the release defines, the collection jobs of the pinned routes included."""
    scoped = [(package, "jobs", route[f"{lane}_job"].rsplit("/", 1)[1])
              for route in collection_routes().values() for package, lane in (("worker", "worker"), ("api", "intake"))]
    return [*RUNTIMES, *scoped]


def in_service(package: str, kind: str, name: str) -> str:
    """The digest a runtime runs now: a service's latest ready revision, which takes all traffic, or a job's."""
    location = ["--region", settings.REGION, "--project", settings.PROJECT]
    if kind == "jobs":
        job = gcloud("run", "jobs", "describe", name, *location)
        image = job["spec"]["template"]["spec"]["template"]["spec"]["containers"][0]["image"]
    else:
        service = gcloud("run", "services", "describe", name, *location)
        revision = gcloud("run", "revisions", "describe", service["status"]["latestReadyRevisionName"], *location)
        image = revision.get("status", {}).get("imageDigest") or revision["spec"]["containers"][0]["image"]
    return checked_image(package, image).rsplit("@", 1)[1]


def kept_tags(package: str) -> dict[str, str]:
    """The version digest each deployed-* and rollback-* tag of the package names."""
    held = {}
    for row in gcloud("artifacts", "tags", "list", f"--package={package}", *AT_REGISTRY):
        tag = row["name"].rsplit("/tags/", 1)[1]
        if tag.startswith(tuple(f"{prefix}-" for prefix in KEEP_TAGS)):
            held[tag] = row["version"].rsplit("/versions/", 1)[1]
    return held


def point(package: str, tag: str, digest: str, held: dict[str, str]) -> None:
    verb = "update" if tag in held else "create"
    subprocess.run(["gcloud", "artifacts", "tags", verb, tag, f"--package={package}", f"--version={digest}",
                    *AT_REGISTRY, "--quiet"], env=ENV, check=True)


def keep(package: str, kind: str, name: str) -> str:
    digest = in_service(package, kind, name)
    deployed, rollback = f"deployed-{name}", f"rollback-{name}"
    held = kept_tags(package)
    previous = held.get(rollback)
    if held.get(deployed) != digest:
        if deployed in held:
            previous = held[deployed]
            point(package, rollback, previous, held)
        point(package, deployed, digest, held)
    after = kept_tags(package)
    if (after.get(deployed), after.get(rollback)) != (digest, previous):
        raise ValueError(f"{name}: the tags {deployed} and {rollback} did not read back as set")
    return f"kept {package} image of {name}: {deployed} {digest}, {rollback} {previous or 'none yet'}"


def main(argv: list[str]) -> None:
    if len(argv) != 1:
        raise ValueError("usage: keep_images.py")
    release_context(os.environ)
    repository = gcloud("artifacts", "repositories", "describe", REGISTRY,
                        f"--location={settings.REGION}", f"--project={settings.PROJECT}")
    if not cleanup_set_up(repository):
        print(f"registry cleanup is not set up, so nothing is deleted and no image is tagged; {OWNER_HINT}",
              flush=True)
        return
    # Tag every runtime that can be read, then fail for any that could not: a partly failed release still keeps
    # what it left in service.
    failures = []
    for package, kind, name in runtimes():
        try:
            print(keep(package, kind, name), flush=True)
        except (ValueError, KeyError, IndexError, subprocess.CalledProcessError) as error:
            failures.append(f"{name}: {error!r}")
    if failures:
        raise ValueError("; ".join(failures))
    print(f"verified the cleanup policy of {REGISTRY}{' (dry run: nothing is deleted)' if DRY_RUN else ''}",
          flush=True)


if __name__ == "__main__":
    try:
        main(sys.argv)
    except (ValueError, KeyError, IndexError, subprocess.CalledProcessError) as error:
        sys.exit(f"keeping the images in service failed: {error!r}")
