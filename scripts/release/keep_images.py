"""Keep the images in service out of the registry cleanup; runtime-release.yml runs this after the deploys.

scripts/ops/owner_setup.sh gives the image registry a cleanup policy: an image may go a day after its push
unless it is one of the newest five of its package or carries a tag that starts with "deployed" or "rollback".
This script reads that policy back and must find exactly the committed one. Then, for every service and job the
release defines, it points the tag deployed-<runtime> at the image that runtime runs now and rollback-<runtime>
at the image deployed-<runtime> named before; any other image a service still sends traffic to, or reaches by a
revision tag, gets deployed-<runtime>.<n>. It deletes nothing and moves no other tag.
"""
from __future__ import annotations

import itertools
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


def collection_runtimes() -> list[tuple[str, str, str]]:
    """The worker and intake jobs of each pinned collection route."""
    return [(package, "jobs", route[f"{lane}_job"].rsplit("/", 1)[1])
            for route in collection_routes().values() for package, lane in (("worker", "worker"), ("api", "intake"))]


def in_service(package: str, kind: str, name: str) -> list[str]:
    """The digests a runtime runs now, the main one first. A job runs its definition's image. A service runs every
    revision that takes traffic or has a revision tag; after a rollback by traffic that need not be the latest ready
    one. The revision with the most traffic is the main one (on a tie, the latest ready revision)."""
    location = ["--region", settings.REGION, "--project", settings.PROJECT]
    if kind == "jobs":
        job = gcloud("run", "jobs", "describe", name, *location)
        image = job["spec"]["template"]["spec"]["template"]["spec"]["containers"][0]["image"]
        return [checked_image(package, image).rsplit("@", 1)[1]]
    status = gcloud("run", "services", "describe", name, *location)["status"]
    targets = [row for row in status.get("traffic", []) if int(row.get("percent", 0)) > 0 or row.get("tag")]
    if not targets:
        raise ValueError(f"{name}: no revision takes traffic")
    latest = status.get("latestReadyRevisionName")
    targets.sort(key=lambda row: (-int(row.get("percent", 0)), row["revisionName"] != latest, row["revisionName"]))
    digests = []
    for row in targets:
        revision = gcloud("run", "revisions", "describe", row["revisionName"], *location)
        image = revision.get("status", {}).get("imageDigest") or revision["spec"]["containers"][0]["image"]
        digest = checked_image(package, image).rsplit("@", 1)[1]
        if digest not in digests:
            digests.append(digest)
    return digests


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


def fresh(prefix: str, taken) -> str:
    """The lowest prefix<n> that no tag uses yet."""
    return next(f"{prefix}{number}" for number in itertools.count(1) if f"{prefix}{number}" not in taken)


def plan(name: str, digest: str, others: list[str], held: dict[str, str]) -> dict[str, str]:
    """The tags a runtime should end with: deployed-<name> at the main digest, rollback-<name> at the main digest
    before it, and one deployed-<name>.<n> for each other digest in service. An extra tag keeps the digest it
    holds while that digest stays in service, so a change in the order of traffic moves none of them; a new one
    takes a free number, and one no longer needed points at the main digest."""
    deployed, rollback, prefix = f"deployed-{name}", f"rollback-{name}", f"deployed-{name}."
    final = {deployed: digest}
    if held.get(deployed) not in (None, digest):
        final[rollback] = held[deployed]
    elif rollback in held:
        final[rollback] = held[rollback]
    slots = {tag: image for tag, image in held.items() if tag.startswith(prefix)}
    extra = {}
    for tag, image in sorted(slots.items()):
        if image in others and image not in extra.values():
            extra[tag] = image
    spent = [tag for tag in sorted(slots) if tag not in extra]
    for other in others:
        if other not in extra.values():
            extra[spent.pop(0) if spent else fresh(prefix, {*slots, *extra})] = other
    return {**final, **extra, **{tag: digest for tag in spent}}


def apply(package: str, name: str, final: dict[str, str], held: dict[str, str]) -> dict[str, str]:
    """Moves the runtime's tags to final without ever taking the last tag off an image final keeps: a tag leaves an
    image only when final no longer needs it or another tag holds it. deployed-<name> moves only once
    rollback-<name> holds the image it leaves, since plan() takes that image from deployed-<name>: a retry after a
    failed write then plans the same rotation. When no move is safe (two tags trading images, as in a rollback to
    the rollback image), a spare deployed-<name>.<n> first takes the image of the blocked tag, which then moves at
    once; the spare ends at the main digest. Returns final with any spare added."""
    deployed, rollback = f"deployed-{name}", f"rollback-{name}"
    final, current = dict(final), dict(held)
    pending = {tag: image for tag, image in final.items() if current.get(tag) != image}

    def safe(tag):
        old = current.get(tag)
        return (old is None or old not in final.values()
                or any(other != tag and image == old for other, image in current.items()))

    def move(tag):
        point(package, tag, pending[tag], current)
        current[tag] = pending.pop(tag)

    while pending:
        order = [tag for tag in sorted(pending, key=lambda tag: (tag in current, tag))
                 if tag != deployed or rollback not in pending]
        movable = [tag for tag in order if safe(tag)]
        if movable:
            move(movable[0])
            continue
        blocked = rollback if rollback in pending else order[0]
        spare = fresh(f"{deployed}.", {*current, *final})
        final[spare] = final[deployed]
        point(package, spare, current[blocked], current)
        current[spare] = current[blocked]
        if current[spare] != final[spare]:
            pending[spare] = final[spare]
        move(blocked)
    return final


def keep(package: str, kind: str, name: str) -> str:
    digest, *others = in_service(package, kind, name)
    held = {tag: image for tag, image in kept_tags(package).items()
            if tag in (f"deployed-{name}", f"rollback-{name}") or tag.startswith(f"deployed-{name}.")}
    final = apply(package, name, plan(name, digest, others, held), held)
    after = kept_tags(package)
    if {tag: after.get(tag) for tag in final} != final:
        raise ValueError(f"{name}: the tags deployed-{name} and rollback-{name} did not read back as set")
    previous = final.get(f"rollback-{name}")
    also = f", also in service {', '.join(others)}" if others else ""
    return (f"kept {package} image of {name}: deployed-{name} {digest}, rollback-{name} {previous or 'none yet'}"
            f"{also}")


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
    # what it left in service, and so does a release whose collection routes could not be read.
    failures, found = [], list(RUNTIMES)
    try:
        found += collection_runtimes()
    except (ValueError, KeyError, subprocess.CalledProcessError) as error:
        failures.append(f"collection routes: {error!r}")
    for package, kind, name in found:
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
