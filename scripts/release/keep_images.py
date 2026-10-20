"""Keep the images in service out of the registry cleanup; runtime-release.yml runs this after the deploys.

scripts/ops/owner_setup.sh gives the image registry a cleanup policy: an image may go a day after its push
unless it is one of the newest five of its kind or carries the tag "deployed" or "rollback". This script reads
that policy back and must find exactly the committed one, then points "deployed" at the image each runtime runs
now and "rollback" at the image "deployed" named before. It deletes nothing and moves no other tag.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy_models import checked_image, release_context, settings  # noqa: E402

REGISTRY = "specimen-runtime"
ROLES = ("api", "sam", "worker")
OWNER_HINT = "the owner runs scripts/ops/owner_setup.sh once"
# The newest five keep the last few releases at hand; what a running service or a rollback needs is held by the
# two tags instead, whatever the count.
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


def deployed_image(role: str) -> str:
    """The digest the role runs now: a service's latest ready revision, which takes all traffic, or the job's."""
    location = ["--region", settings.REGION, "--project", settings.PROJECT]
    if role == "worker":
        job = gcloud("run", "jobs", "describe", "specimen-worker", *location)
        image = job["spec"]["template"]["spec"]["template"]["spec"]["containers"][0]["image"]
    else:
        service = gcloud("run", "services", "describe", f"specimen-{role}", *location)
        revision = gcloud("run", "revisions", "describe", service["status"]["latestReadyRevisionName"], *location)
        image = revision.get("status", {}).get("imageDigest") or revision["spec"]["containers"][0]["image"]
    return checked_image(role, image).rsplit("@", 1)[1]


def kept_tags(role: str) -> dict[str, str]:
    """The version digest each of the two tags names in the role's package; an absent tag is left out."""
    rows = gcloud("artifacts", "tags", "list", f"--package={role}", *AT_REGISTRY)
    held = {}
    for row in rows:
        tag = row["name"].rsplit("/tags/", 1)[1]
        if tag in KEEP_TAGS:
            held[tag] = row["version"].rsplit("/versions/", 1)[1]
    return held


def point(role: str, tag: str, digest: str, held: dict[str, str]) -> None:
    verb = "update" if tag in held else "create"
    subprocess.run(["gcloud", "artifacts", "tags", verb, tag, f"--package={role}", f"--version={digest}",
                    *AT_REGISTRY, "--quiet"], env=ENV, check=True)


def keep(role: str) -> str:
    digest = deployed_image(role)
    held = kept_tags(role)
    expected = dict(held)
    if held.get("deployed") != digest:
        if "deployed" in held:
            point(role, "rollback", held["deployed"], held)
            expected["rollback"] = held["deployed"]
        point(role, "deployed", digest, held)
        expected["deployed"] = digest
    if kept_tags(role) != expected:
        raise ValueError(f"{role}: the deployed and rollback tags did not read back as set")
    return f"kept {role}: deployed {digest}, rollback {expected.get('rollback', 'none yet')}"


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
    for role in ROLES:
        print(keep(role), flush=True)
    print(f"verified the cleanup policy of {REGISTRY}{' (dry run: nothing is deleted)' if DRY_RUN else ''}",
          flush=True)


if __name__ == "__main__":
    try:
        main(sys.argv)
    except (ValueError, KeyError, IndexError, subprocess.CalledProcessError) as error:
        sys.exit(f"keeping the deployed images failed: {error!r}")
