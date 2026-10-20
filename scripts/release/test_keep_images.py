"""The image registry's cleanup policy and the release step that keeps the images in service out of it.

Offline: gcloud is a stand-in and no cloud is called. The policy's effect is judged by the rules Google documents
for cleanup policies (https://cloud.google.com/artifact-registry/docs/repositories/cleanup-policy): a version that
matches a keep rule is kept even when a delete rule matches it, the conditions of one rule must all hold,
olderThan counts from the version's creation, tag prefixes apply to tagged versions only, and mostRecentVersions
keeps that many of each package.
"""
import datetime as dt
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))
import keep_images as keep  # noqa: E402
from deploy_models import REPOSITORY, WORKFLOW  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OWNER_SETUP = (ROOT / "scripts/ops/owner_setup.sh").read_text()
RELEASE = yaml.load((ROOT / ".github/workflows/runtime-release.yml").read_text(), Loader=yaml.BaseLoader)
SHA = "a" * 40
CONTEXT = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPOSITORY, "GITHUB_REF": "refs/heads/main",
           "GITHUB_WORKFLOW_REF": WORKFLOW, "GITHUB_SHA": SHA, "GITHUB_EVENT_NAME": "push"}
PACKAGES = "projects/specimen-digitization/locations/us-east4/repositories/specimen-runtime/packages"
NOW = dt.datetime(2026, 10, 20, 17, 0, tzinfo=dt.timezone.utc)


def digest(mark):
    return "sha256:" + mark * 64


def image(role, mark):
    return f"us-east4-docker.pkg.dev/specimen-digitization/specimen-runtime/{role}@{digest(mark)}"


# The policy as the registry reports it once owner_setup.sh has set it.
LIVE_POLICY = {
    "delete-old": {"id": "delete-old", "action": "DELETE", "condition": {"olderThan": "86400s", "tagState": "ANY"}},
    "keep-deployed": {"id": "keep-deployed", "action": "KEEP",
                      "condition": {"tagPrefixes": ["deployed", "rollback"], "tagState": "TAGGED"}},
    "keep-newest": {"id": "keep-newest", "action": "KEEP", "mostRecentVersions": {"keepCount": 5}},
}
SET_UP = {"name": "specimen-runtime", "format": "DOCKER", "cleanupPolicies": LIVE_POLICY, "cleanupPolicyDryRun": True}
NOT_SET_UP = {"name": "specimen-runtime", "format": "DOCKER", "dockerConfig": {"immutableTags": True}}


def shell_constant(name):
    """A readonly constant of owner_setup.sh, single- or double-quoted, as bash reads it."""
    found = re.search(rf"^readonly {name}=(['\"])(.*?)\1$", OWNER_SETUP, re.MULTILINE | re.DOTALL)
    assert found, name
    return found.group(2)


def as_registry_stores(file_policies):
    """What gcloud 582 sends for a policy file (cleanup_policy_util.ParseCleanupPolicy) and the registry keeps."""
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    stored = {}
    for rule in file_policies:
        condition = dict(rule.get("condition") or {})
        for key in ("olderThan", "newerThan"):
            if key in condition:
                count, unit = re.fullmatch(r"([0-9]+)([smhd])", condition[key]).groups()
                condition[key] = f"{int(count) * units[unit]}s"
        stored[rule["name"]] = {"id": rule["name"], "action": rule["action"]["type"], "condition": condition,
                                "mostRecentVersions": rule.get("mostRecentVersions")}
    return stored


def printed(value):
    """How gcloud prints a policy map in value(): sorted keys, Python's quoting, ";" between the policies."""
    if isinstance(value, dict):
        return "{" + ", ".join(f"{key!r}: {printed(value[key])}" for key in sorted(value)) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(printed(item) for item in value) + "]"
    return repr(value)


def test_the_policy_keeps_the_newest_five_and_the_two_tags_and_lets_the_rest_go_a_day_after_the_push():
    assert keep.POLICY == {
        "keep-newest": {"id": "keep-newest", "action": "KEEP", "mostRecentVersions": {"keepCount": 5}},
        "keep-deployed": {"id": "keep-deployed", "action": "KEEP",
                          "condition": {"tagState": "TAGGED", "tagPrefixes": ["deployed", "rollback"]}},
        "delete-old": {"id": "delete-old", "action": "DELETE",
                       "condition": {"tagState": "ANY", "olderThan": "86400s"}},
    }
    # No package prefix: the count applies to every package, including one added later.
    assert "packageNamePrefixes" not in json.dumps(keep.POLICY)
    assert keep.canonical(LIVE_POLICY) == keep.canonical(keep.POLICY)
    # It starts in dry-run mode; turning that off is a reviewed change of its own.
    assert keep.DRY_RUN is True


def test_owner_setup_sets_exactly_this_policy_in_dry_run_mode_and_recognizes_it_once_live():
    sent = as_registry_stores(json.loads(shell_constant("CLEANUP_POLICY")))
    assert keep.canonical(sent) == keep.canonical(keep.POLICY)
    # gcloud 582's own printer gave this line for the policy on 2026-10-20; the script compares it to decide that
    # nothing needs setting.
    assert shell_constant("CLEANUP_POLICY_LIVE") == ";".join(
        f"{name}={printed(rule)}" for name, rule in sorted(LIVE_POLICY.items()))
    command = re.search(r"run gcloud artifacts repositories set-cleanup-policies .*?\n.*?\n", OWNER_SETUP).group(0)
    assert command.rstrip().endswith('"--policy=$file" --dry-run') and "--no-dry-run" not in OWNER_SETUP
    assert '[ "$dry" = True ]' in OWNER_SETUP


def matches(condition, version, now):
    age = now - version["created"]
    tags = version["tags"]
    state = condition.get("tagState", "ANY")
    duration = {key: dt.timedelta(seconds=int(condition[key][:-1])) for key in ("olderThan", "newerThan")
                if key in condition}
    return all((
        state == "ANY" or (state == "TAGGED") == bool(tags),
        not condition.get("tagPrefixes") or any(tag.startswith(prefix) for tag in tags
                                                for prefix in condition["tagPrefixes"]),
        not condition.get("packageNamePrefixes") or any(version["package"].startswith(prefix)
                                                        for prefix in condition["packageNamePrefixes"]),
        "olderThan" not in duration or age > duration["olderThan"],
        "newerThan" not in duration or age < duration["newerThan"],
    ))


def deleted(policy, versions, now=NOW):
    """The versions the policy deletes under the documented rules."""
    kept = set()
    for rule in policy.values():
        newest = rule.get("mostRecentVersions")
        if newest:
            for package in {version["package"] for version in versions}:
                own = sorted((version for version in versions if version["package"] == package
                              and any(package.startswith(prefix) for prefix in newest.get("packageNamePrefixes")
                                      or [""])), key=lambda version: version["created"], reverse=True)
                kept.update(version["name"] for version in own[:newest["keepCount"]])
        elif rule["action"] == "KEEP":
            kept.update(version["name"] for version in versions if matches(rule["condition"], version, now))
    gone = {version["name"] for rule in policy.values() if rule["action"] == "DELETE"
            for version in versions if matches(rule["condition"], version, now)}
    return gone - kept


def version(package, name, hours_old, *tags):
    return {"package": package, "name": f"{package}/{name}", "created": NOW - dt.timedelta(hours=hours_old),
            "tags": list(tags)}


def test_the_deployed_and_rollback_images_stay_however_old_and_the_superseded_ones_go():
    history = [version("api", f"v{number}", number * 6, f"sha-{number}") for number in range(12)]
    history[8]["tags"].append("deployed-specimen-api")  # 48 hours old, eight newer pushes whose releases failed
    history[10]["tags"].append("rollback-specimen-intake")
    history.append(version("api", "untagged", 70))
    history += [version("sam", f"v{number}", 100 + number, f"sha-{number}") for number in range(3)]
    gone = deleted(keep.POLICY, history)
    # Kept: the newest five (0 to 24 hours old), both tags, and a package with fewer than five images whatever
    # their age. Gone: every other image more than a day old, tagged or not.
    assert gone == {"api/v5", "api/v6", "api/v7", "api/v9", "api/v11", "api/untagged"}
    assert {"api/v8", "api/v10"}.isdisjoint(gone)
    assert not [name for name in gone if name.startswith("sam/")]


def test_nothing_under_a_day_old_goes_even_past_the_newest_five():
    history = [version("worker", f"v{number}", number * 3, f"sha-{number}") for number in range(9)]
    assert deleted(keep.POLICY, history) == set()
    history.append(version("worker", "old", 25, "sha-old"))
    assert deleted(keep.POLICY, history) == {"worker/old"}


def test_a_keep_rule_wins_over_the_delete_rule():
    history = [version("api", f"v{number}", 200 + number, f"sha-{number}") for number in range(7)]
    assert deleted(keep.POLICY, history) == {"api/v5", "api/v6"}
    history[6]["tags"].append("rollback-specimen-api")
    assert deleted(keep.POLICY, history) == {"api/v5"}


def test_the_cleanup_is_set_up_only_when_the_registry_holds_exactly_the_committed_policy():
    assert keep.cleanup_set_up(NOT_SET_UP) is False
    assert keep.cleanup_set_up(SET_UP) is True
    # gcloud sends "86400.0s"; a lower-case action or tag state still names the same rule.
    lenient = json.loads(json.dumps(LIVE_POLICY))
    lenient["delete-old"]["condition"].update(olderThan="86400.0s", tagState="any")
    assert keep.cleanup_set_up({**SET_UP, "cleanupPolicies": lenient}) is True
    other_count = json.loads(json.dumps(LIVE_POLICY))
    other_count["keep-newest"]["mostRecentVersions"]["keepCount"] = 3
    other_age = json.loads(json.dumps(LIVE_POLICY))
    other_age["delete-old"]["condition"]["olderThan"] = "3600s"
    for repository in (
            {**SET_UP, "cleanupPolicyDryRun": False},  # live deletion before the reviewed switch
            {**SET_UP, "dockerConfig": {"immutableTags": True}},
            {**SET_UP, "cleanupPolicies": other_count}, {**SET_UP, "cleanupPolicies": other_age},
            {**SET_UP, "cleanupPolicies": {key: LIVE_POLICY[key] for key in ("delete-old", "keep-newest")}},
            {**SET_UP, "cleanupPolicies": {**LIVE_POLICY, "extra": LIVE_POLICY["delete-old"]}},
            {"name": "specimen-runtime", "dockerConfig": {"immutableTags": False}}):
        with pytest.raises(ValueError, match="the owner runs scripts/ops/owner_setup.sh once"):
            keep.cleanup_set_up(repository)


ROUTES = {"org/insects": {"worker_job": "projects/specimen-digitization/locations/us-east4/jobs/specimen-worker-insects",
                          "intake_job": "projects/specimen-digitization/locations/us-east4/jobs/specimen-intake-insects"}}


class Cloud:
    """A stand-in gcloud: the repository, what each runtime runs and the tags of each package."""

    def __init__(self, repository=SET_UP, running=None, tags=None, ignore_writes=False, unreadable=(), traffic=None,
                 fail_at=None):
        self.repository, self.fail_at = repository, fail_at
        # A service's (latest ready revision, traffic rows) and each revision's image; by default one revision,
        # "<service>-ready", takes all traffic and runs running[<service>].
        self.traffic, self.revisions = traffic or {}, {}
        self.running = running or {"specimen-api": image("api", "1"), "specimen-sam": image("sam", "2"),
                                   "specimen-worker": image("worker", "3"), "specimen-intake": image("api", "1")}
        self.tags = tags or {package: {} for package in ("api", "sam", "worker")}
        self.ignore_writes, self.unreadable, self.calls, self.writes = ignore_writes, unreadable, [], []

    def __call__(self, argv, env=None, capture_output=False, text=False, check=False):
        assert env["CLOUDSDK_CORE_DISABLE_PROMPTS"] == "1" and check
        self.calls.append(argv)
        flags = dict(arg[2:].split("=", 1) for arg in argv if arg.startswith("--") and "=" in arg)
        words = [arg for arg in argv if not arg.startswith("--")]
        if words[1:3] == ["artifacts", "tags"] and words[3] in ("create", "update"):
            assert argv[-1] == "--quiet" and (flags["repository"], flags["location"], flags["project"]) == (
                "specimen-runtime", "us-east4", "specimen-digitization")
            self.writes.append(words[3:5] + [flags["package"], flags["version"]])
            if len(self.writes) == self.fail_at:
                raise subprocess.CalledProcessError(1, argv, "", "ERROR: UNAVAILABLE")
            held = self.tags[flags["package"]]
            assert (words[4] in held) == (words[3] == "update"), "create only a new tag, update only an existing one"
            if not self.ignore_writes:
                held[words[4]] = flags["version"]
            return subprocess.CompletedProcess(argv, 0, "", "")
        assert argv[-1] == "--format=json", argv
        if len(words) > 4 and words[4] in self.unreadable:
            raise subprocess.CalledProcessError(1, argv, "", "ERROR: NOT_FOUND")
        return subprocess.CompletedProcess(argv, 0, json.dumps(self.answer(words, flags)), "")

    def answer(self, words, flags):
        if words[1:4] == ["artifacts", "repositories", "describe"]:
            return self.repository
        if words[1:4] == ["artifacts", "tags", "list"]:
            return [{"name": f"{PACKAGES}/{flags['package']}/tags/{tag}",
                     "version": f"{PACKAGES}/{flags['package']}/versions/{held}"}
                    for tag, held in {"sha-x": digest("f"), "deployed": digest("e"),  # not a runtime's tag
                                      **self.tags[flags["package"]]}.items()]
        if words[1:4] == ["run", "jobs", "describe"]:
            return {"spec": {"template": {"spec": {"template": {"spec": {
                "containers": [{"image": self.running[words[4]]}]}}}}}}
        if words[1:4] == ["run", "services", "describe"]:
            latest, rows = self.traffic.get(words[4], (f"{words[4]}-ready", [
                {"revisionName": f"{words[4]}-ready", "percent": 100, "latestRevision": True}]))
            self.revisions.setdefault(f"{words[4]}-ready", self.running.get(words[4]))
            return {"status": {"latestReadyRevisionName": latest, "traffic": rows}}
        if words[1:4] == ["run", "revisions", "describe"]:
            return {"spec": {"containers": [{"image": "unused"}]},
                    "status": {"imageDigest": self.revisions[words[4]]}}
        raise AssertionError(f"unexpected gcloud call: {words}")


@pytest.fixture
def release(monkeypatch):
    for key, value in CONTEXT.items():
        monkeypatch.setenv(key, value)

    def start(cloud, routes=None):
        monkeypatch.setattr(keep.subprocess, "run", cloud)
        monkeypatch.setattr(keep, "collection_routes", lambda: routes or {})
        return cloud
    return start


def test_the_first_release_after_the_setup_tags_each_runtimes_image_deployed(release, capsys):
    cloud = release(Cloud())
    keep.main(["keep_images.py"])
    assert cloud.writes == [["create", "deployed-specimen-api", "api", digest("1")],
                            ["create", "deployed-specimen-sam", "sam", digest("2")],
                            ["create", "deployed-specimen-worker", "worker", digest("3")],
                            ["create", "deployed-specimen-intake", "api", digest("1")]]
    out = capsys.readouterr().out
    assert f"kept api image of specimen-api: deployed-specimen-api {digest('1')}, rollback-specimen-api none yet" in out
    assert "verified the cleanup policy of specimen-runtime (dry run: nothing is deleted)" in out


def test_a_new_image_in_service_moves_deployed_and_the_one_before_becomes_rollback(release):
    cloud = release(Cloud(tags={
        "api": {"deployed-specimen-api": digest("0"), "deployed-specimen-intake": digest("1")},
        "sam": {"deployed-specimen-sam": digest("8"), "rollback-specimen-sam": digest("7")},
        "worker": {"deployed-specimen-worker": digest("3"), "rollback-specimen-worker": digest("9")}}))
    keep.main(["keep_images.py"])
    assert cloud.writes == [["create", "rollback-specimen-api", "api", digest("0")],
                            ["update", "deployed-specimen-api", "api", digest("1")],
                            ["update", "rollback-specimen-sam", "sam", digest("8")],
                            ["update", "deployed-specimen-sam", "sam", digest("2")]]
    # The worker and the intake job still run the images they ran: none of their tags moves.
    assert cloud.tags == {
        "api": {"deployed-specimen-api": digest("1"), "rollback-specimen-api": digest("0"),
                "deployed-specimen-intake": digest("1")},
        "sam": {"deployed-specimen-sam": digest("2"), "rollback-specimen-sam": digest("8")},
        "worker": {"deployed-specimen-worker": digest("3"), "rollback-specimen-worker": digest("9")}}


def test_each_runtime_of_one_package_keeps_its_own_image_and_the_collection_jobs_are_kept_too(release):
    # A partly failed release: the API service took the new image, the intake jobs still run the old one.
    running = {"specimen-api": image("api", "1"), "specimen-sam": image("sam", "2"),
               "specimen-worker": image("worker", "3"), "specimen-intake": image("api", "0"),
               "specimen-worker-insects": image("worker", "4"), "specimen-intake-insects": image("api", "0")}
    cloud = release(Cloud(running=running), routes=ROUTES)
    keep.main(["keep_images.py"])
    assert cloud.tags["api"] == {"deployed-specimen-api": digest("1"), "deployed-specimen-intake": digest("0"),
                                 "deployed-specimen-intake-insects": digest("0")}
    assert cloud.tags["worker"] == {"deployed-specimen-worker": digest("3"),
                                    "deployed-specimen-worker-insects": digest("4")}


def test_after_a_rollback_by_traffic_the_revision_that_serves_is_kept_not_the_latest(release):
    # Traffic was moved back to revision a; two later releases left b and c ready with no traffic.
    cloud = Cloud(traffic={"specimen-api": ("api-c", [{"revisionName": "api-a", "percent": 100},
                                                     {"revisionName": "api-b", "percent": 0},
                                                     {"revisionName": "api-c", "percent": 0}])})
    cloud.revisions.update({"api-a": image("api", "a"), "api-b": image("api", "b"), "api-c": image("api", "c")})
    release(cloud)
    keep.main(["keep_images.py"])
    assert cloud.tags["api"]["deployed-specimen-api"] == digest("a")
    assert digest("c") not in cloud.tags["api"].values()


def test_every_image_a_service_sends_traffic_to_or_tags_is_kept_and_a_spent_extra_tag_returns_to_the_main(release):
    split = [{"revisionName": "api-b", "percent": 10}, {"revisionName": "api-a", "percent": 90},
             {"revisionName": "api-c", "percent": 0, "tag": "preview"}]
    cloud = Cloud(traffic={"specimen-api": ("api-c", split)})
    cloud.revisions.update({"api-a": image("api", "a"), "api-b": image("api", "b"), "api-c": image("api", "c")})
    release(cloud)
    keep.main(["keep_images.py"])
    assert {tag: held for tag, held in cloud.tags["api"].items() if "specimen-api" in tag} == {
        "deployed-specimen-api": digest("a"), "deployed-specimen-api.1": digest("b"),
        "deployed-specimen-api.2": digest("c")}
    # All traffic back on one revision: the extra tags no longer hold anything else.
    cloud.traffic["specimen-api"] = ("api-c", [{"revisionName": "api-c", "percent": 100}])
    keep.main(["keep_images.py"])
    assert {tag: held for tag, held in cloud.tags["api"].items() if "specimen-api" in tag} == {
        "deployed-specimen-api": digest("c"), "rollback-specimen-api": digest("a"),
        "deployed-specimen-api.1": digest("c"), "deployed-specimen-api.2": digest("c")}


def api_cloud(rows, tags, **options):
    """Only specimen-api's traffic and tags vary; its revisions api-<mark> run image <mark>."""
    cloud = Cloud(traffic={"specimen-api": (rows[0]["revisionName"], rows)},
                  tags={"api": {**tags, "deployed-specimen-intake": digest("1")},
                        "sam": {"deployed-specimen-sam": digest("2")}, "worker": {"deployed-specimen-worker": digest("3")}},
                  **options)
    cloud.revisions.update({f"api-{mark}": image("api", mark) for mark in "abcd9"})
    return cloud


def traffic(shares=None, **percent):
    return [{"revisionName": f"api-{mark}", "percent": share} for mark, share in {**(shares or {}), **percent}.items()]


def api_tags(cloud):
    return {tag: held for tag, held in cloud.tags["api"].items() if "specimen-api" in tag}


def test_a_change_in_the_order_of_traffic_moves_no_tag(release):
    before = {"deployed-specimen-api": digest("a"), "deployed-specimen-api.1": digest("b"),
              "deployed-specimen-api.2": digest("c")}
    cloud = release(api_cloud(traffic(a=90, c=9, b=1), before))
    keep.main(["keep_images.py"])
    assert cloud.writes == [] and api_tags(cloud) == before


# (tags before, traffic now, tags after): an extra image dropped and a new one added; a rollback to the
# rollback image (the two tags trade images); a release; a release whose old image still takes some traffic.
SCENARIOS = [
    ({"deployed-specimen-api": "a", "rollback-specimen-api": "9", "deployed-specimen-api.1": "b",
      "deployed-specimen-api.2": "c"}, {"a": 80, "c": 10, "d": 10},
     {"deployed-specimen-api": "a", "rollback-specimen-api": "9", "deployed-specimen-api.1": "d",
      "deployed-specimen-api.2": "c"}),
    ({"deployed-specimen-api": "a", "rollback-specimen-api": "9"}, {"9": 100},
     {"deployed-specimen-api": "9", "rollback-specimen-api": "a", "deployed-specimen-api.1": "9"}),
    ({"deployed-specimen-api": "a", "rollback-specimen-api": "9"}, {"c": 100},
     {"deployed-specimen-api": "c", "rollback-specimen-api": "a"}),
    ({"deployed-specimen-api": "a"}, {"c": 90, "a": 10},
     {"deployed-specimen-api": "c", "rollback-specimen-api": "a", "deployed-specimen-api.1": "a"}),
]


@pytest.mark.parametrize("before, now, after", SCENARIOS)
def test_tags_end_as_planned_and_a_failure_after_any_write_leaves_every_needed_image_tagged(release, before, now,
                                                                                         after):
    tags = {tag: digest(mark) for tag, mark in before.items()}
    cloud = release(api_cloud(traffic(now), tags))
    keep.main(["keep_images.py"])
    assert api_tags(cloud) == {tag: digest(mark) for tag, mark in after.items()}
    writes = len(cloud.writes)
    # Images that were tagged and are still in service or still kept must stay tagged through every partial run.
    guarded = {digest(mark) for mark in before.values()} & {digest(mark) for mark in [*now, *after.values()]}
    for failing in range(1, writes + 1):
        cloud = release(api_cloud(traffic(now), dict(tags), fail_at=failing))
        with pytest.raises(ValueError, match="specimen-api: CalledProcessError"):
            keep.main(["keep_images.py"])
        assert guarded <= set(api_tags(cloud).values()), (failing, api_tags(cloud))


def test_a_service_with_no_traffic_fails_its_runtime_only(release):
    cloud = release(Cloud(traffic={"specimen-sam": ("sam-x", [])}))
    with pytest.raises(ValueError, match="specimen-sam: ValueError.'specimen-sam: no revision takes traffic"):
        keep.main(["keep_images.py"])
    assert "deployed-specimen-worker" in cloud.tags["worker"]


def test_unreadable_collection_routes_still_keep_the_fixed_runtimes_then_fail(release, monkeypatch):
    cloud = release(Cloud())

    def unreadable():
        raise ValueError("Pinned collection routes could not be read; run owner setup --intake-only")
    monkeypatch.setattr(keep, "collection_routes", unreadable)
    with pytest.raises(ValueError, match="collection routes: ValueError"):
        keep.main(["keep_images.py"])
    assert [write[1] for write in cloud.writes] == [
        "deployed-specimen-api", "deployed-specimen-sam", "deployed-specimen-worker", "deployed-specimen-intake"]


def test_a_runtime_that_cannot_be_read_fails_the_step_after_the_others_are_tagged(release):
    cloud = release(Cloud(unreadable=("specimen-sam",)))
    with pytest.raises(ValueError, match="specimen-sam: CalledProcessError"):
        keep.main(["keep_images.py"])
    assert [write[1] for write in cloud.writes] == [
        "deployed-specimen-api", "deployed-specimen-worker", "deployed-specimen-intake"]


def test_before_the_owner_setup_nothing_is_tagged_and_the_release_passes(release, capsys):
    cloud = release(Cloud(repository=NOT_SET_UP))
    keep.main(["keep_images.py"])
    assert cloud.writes == [] and len(cloud.calls) == 1
    assert "registry cleanup is not set up, so nothing is deleted and no image is tagged" in capsys.readouterr().out


def test_other_cleanup_settings_stop_the_step_before_any_tag_moves(release):
    cloud = release(Cloud(repository={**SET_UP, "cleanupPolicyDryRun": False}))
    with pytest.raises(ValueError, match="owner_setup.sh"):
        keep.main(["keep_images.py"])
    assert cloud.writes == []


def test_a_tag_that_does_not_read_back_as_set_fails_the_step(release):
    release(Cloud(ignore_writes=True))
    with pytest.raises(ValueError, match="specimen-api: the tags deployed-specimen-api and rollback-specimen-api "
                                         "did not read back as set"):
        keep.main(["keep_images.py"])


@pytest.mark.parametrize("running", [
    "us-east4-docker.pkg.dev/specimen-digitization/specimen-runtime/api:sha-x",  # a tag, not a digest
    image("sam", "1"),  # another package's image
    "gcr.io/elsewhere/api@" + digest("1")])
def test_only_this_registrys_digest_of_the_package_is_tagged(release, running):
    cloud = release(Cloud(running={"specimen-api": running, "specimen-sam": image("sam", "2"),
                                   "specimen-worker": image("worker", "3"), "specimen-intake": image("api", "1")}))
    with pytest.raises(ValueError, match="api requires its immutable pushed image digest"):
        keep.main(["keep_images.py"])
    assert "deployed-specimen-api" not in [write[1] for write in cloud.writes]


def test_the_step_runs_only_in_the_runtime_release_on_main(monkeypatch):
    cloud = Cloud()
    monkeypatch.setattr(keep.subprocess, "run", cloud)
    for key, value in {**CONTEXT, "GITHUB_REF": "refs/heads/other"}.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match="only runtime-release.yml on main"):
        keep.main(["keep_images.py"])
    assert cloud.calls == []


def test_the_release_runs_it_last_and_also_after_a_failed_step():
    step = RELEASE["jobs"]["release"]["steps"][-1]
    assert step == {"name": "Verify the registry cleanup policy and tag the images in service",
                    "if": "always()", "run": "uv run python scripts/release/keep_images.py"}
    # The release identity may create and move tags and nothing else in the registry beyond its reader role.
    role = re.search(r"ensure_role specimenRuntimeImageTags .*?\n  grant ", OWNER_SETUP, re.DOTALL).group(0)
    assert re.findall(r"artifactregistry\.[\w.]+", role) == ["artifactregistry.tags.create",
                                                             "artifactregistry.tags.update"]
