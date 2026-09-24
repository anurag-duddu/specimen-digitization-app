#!/usr/bin/env python3
"""Report the owner's standing grants for the release planes; read-only (golive/RELEASE.md section 5).

``plan`` reads the live IAM policies of the project, bucket, registry, runtime service accounts and secrets and,
once they exist, of the Cloud Run services and job, compares them with the committed table below and prints the
owner's list, each command after its reason. It sends only get-iam-policy and describe requests, through
``owner_gcloud``, and prints no response: only the table's public names, roles, members and conditions.
"""
from __future__ import annotations

import argparse
from collections import namedtuple
import hashlib
import importlib
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

from owner_gcloud import STAMP, Gcloud, parse_stamp  # noqa: E402
from release_admission import require, strict_json  # noqa: E402
from release_context import PROJECT  # noqa: E402

REGION = "us-east4"
BUCKET = f"{PROJECT}.firebasestorage.app"
CUSTOM = f"projects/{PROJECT}/roles/"
DEADLINE_SECONDS = 900
MARKER = "specimen-digitization runtime readiness marker v1"  # uploaded with a trailing newline: 50 bytes
MARKER_SHA256 = hashlib.sha256(f"{MARKER}\n".encode()).hexdigest()
BUILD, RELEASE, API, WORKER, SAM, DATA, INITIALIZER = (
    f"serviceAccount:specimen-{name}@{PROJECT}.iam.gserviceaccount.com" for name in (
        "runtime-build", "runtime-release", "api-runtime", "worker-runtime", "sam-runtime", "data-release",
        "data-initialize"))
# Only these members are ever printed; another member's grant is reported, if at all, without its id.
WATCHED = (BUILD, RELEASE, API, WORKER, SAM, DATA, INITIALIZER, "allUsers", "allAuthenticatedUsers")
REMOVE = ("roles/owner", "roles/editor")
BOUNDED = "time-bounded; opened through the setup window only"
# Roles that open only through the setup window: a timed binding is reported with its label, an untimed one is a
# forbidden standing grant to remove, and neither is ever missing or for review.
WINDOW_ONLY = {**dict.fromkeys(("specimenDataInitializeTemporary", "specimenDataOwnerBootstrap",
                                "specimenDataInitializerDisposal"), "one-time, managed by data_setup_window.py"),
               **dict.fromkeys(("specimenDataCloneCreate", "specimenDataCloneControl",
                                "specimenDataRestoreAllowanceClaim"), f"{BOUNDED} for the first apply's restore check"),
               "specimenDataRuntimeAbsence": BOUNDED}
# kind: (command group, resource argument, scope flags, whether add- and remove-iam-policy-binding take --condition:
# all but run jobs, per gcloud 582 help; an unconditional command then says --condition=None and never prompts).
KINDS = {
    "project": (("projects",), "{}", (), True),
    "bucket": (("storage", "buckets"), "gs://{}", (), True),
    "repository": (("artifacts", "repositories"), "{}", (f"--location={REGION}", f"--project={PROJECT}"), True),
    "service-account": (("iam", "service-accounts"), "{}", (f"--project={PROJECT}",), True),
    "secret": (("secrets",), "{}", (f"--project={PROJECT}",), True),
    "service": (("run", "services"), "{}", (f"--region={REGION}", f"--project={PROJECT}"), True),
    "job": (("run", "jobs"), "{}", (f"--region={REGION}", f"--project={PROJECT}"), False),
}
READ_VERBS = ("get-iam-policy", "describe")
READ_GROUPS = (("iam", "roles"), *(kind[0] for kind in KINDS.values()))
DESCRIBED_FIRST = ("secret", "service", "job")
CREATED_BY_RELEASE = ("service", "job")
MISSING = re.compile(r"NOT_FOUND|[Nn]ot found|Cannot find|does not exist")
TIME_BOUND = re.compile(rf"request\.time < timestamp\(['\"]({STAMP})['\"]\)")
SAFE_ROLE = re.compile(rf"(roles|projects/{PROJECT}/roles)/[A-Za-z0-9_.]+")

# Conditions as (CEL expression, title).
OBJECTS = f"projects/_/buckets/{BUCKET}/objects/"
LISTING = 'api.getAttribute("storage.googleapis.com/objectListPrefix", "")'
APP = (f'resource.name.startsWith("{OBJECTS}application/sha256/")', "specimen_application_objects")
SLIDES = (f'resource.name.startsWith("{OBJECTS}microscopic-slides/") || {LISTING}.startsWith("microscopic-slides/")',
          "specimen_source_slides")
# The existing inventory binding's condition, reused exactly.
SQL_SOURCE = (f'resource.name == "projects/{PROJECT}/instances/{PROJECT}-instance" && resource.service == '
              '"sqladmin.googleapis.com" && resource.type == "sqladmin.googleapis.com/Instance"',
              "specimen_source_inventory_only")
RELEASE_WHY = "define the services and the job, read their invoker policies; no delete, no jobs.run, no setIamPolicy"
CONNECTOR_WHY = "call the named operations of the connector only, never arbitrary GraphQL"
LOOKUP_WHY = "look up the Firebase user behind a verified ID token"
# The custom roles this table adds, at project level and stage GA: name: (title, description, permissions).
ROLES = {"specimenRuntimeRelease": ("Specimen runtime release", RELEASE_WHY, (
             "run.services.create", "run.services.get", "run.services.update", "run.services.getIamPolicy",
             "run.jobs.create", "run.jobs.get", "run.jobs.update", "run.operations.get", "run.revisions.get")),
         "specimenRuntimeConnector": ("Specimen runtime connector", CONNECTOR_WHY, (
             "firebasedataconnect.connectors.impersonateQuery", "firebasedataconnect.connectors.impersonateMutation")),
         "specimenApiUserLookup": ("Specimen API user lookup", LOOKUP_WHY, ("firebaseauth.users.get",))}


# resource is (kind, name); condition is (CEL expression, title) or None.
Grant = namedtuple("Grant", "member role resource condition reason")
PROJ, BKT, REPO = ("project", PROJECT), ("bucket", BUCKET), ("repository", "specimen-runtime")
VIEW, CREATE = "roles/storage.objectViewer", "roles/storage.objectCreator"
PROJECT_READ, CONFIRM = CUSTOM + "specimenDataInventoryProjectRead", "the release client confirms its project"
# The committed table (RELEASE.md section 5): member, role, resource, condition, one-line reason.
STANDING = tuple(Grant(*row) for row in (
    (BUILD, "roles/artifactregistry.writer", REPO, None, "push the three images"),
    (BUILD, PROJECT_READ, PROJ, None, CONFIRM),
    (RELEASE, CUSTOM + "specimenRuntimeRelease", PROJ, None, RELEASE_WHY),
    *((RELEASE, "roles/iam.serviceAccountUser", ("service-account", runtime.split(":")[1]), None,
       f"deploy revisions that run as {runtime.split(':')[1].split('@')[0]}") for runtime in (API, WORKER, SAM)),
    (RELEASE, "roles/artifactregistry.reader", REPO, None, "verify each image's attestation"),
    (RELEASE, PROJECT_READ, PROJ, None, CONFIRM),
    *((runtime, CUSTOM + "specimenRuntimeConnector", PROJ, None, CONNECTOR_WHY) for runtime in (API, WORKER)),
    *((runtime, role, BKT, APP, "read and write the application's content-addressed objects; no delete")
      for runtime in (API, WORKER, SAM) for role in (VIEW, CREATE)),
    (API, VIEW, BKT, SLIDES, "source import (S3)"),
    (API, CUSTOM + "specimenApiUserLookup", PROJ, None, f"{LOOKUP_WHY}; roles/firebaseauth.viewer would also "
     "read the auth configuration and list apps and projects"),
    (DATA, CUSTOM + "specimenDataSchemaPublish", PROJ, None, "apply the schema and the connector"),
    (DATA, CUSTOM + "specimenDataStorageRules", PROJ, None, "apply the Storage rules"),
    (DATA, CUSTOM + "specimenDataSourceBackup", PROJ, None, "back up before an apply (D1)"),
    (DATA, CUSTOM + "specimenDataInventorySqlConnect", PROJ, SQL_SOURCE, "read the catalog"),
    (DATA, PROJECT_READ, PROJ, None, CONFIRM),
))
# Granted once the first runtime release has created the service or job; the job takes run.jobs.run only.
AFTER_RELEASE = tuple(Grant(*row) for row in (
    ("allUsers", "roles/run.invoker", ("service", "specimen-api"), None,
     "the web client reaches the API, which authenticates every request itself"),
    (API, "roles/run.invoker", ("job", "specimen-worker"), None, "start executions (G2)"),
    (WORKER, "roles/run.invoker", ("job", "specimen-worker"), None,
     "the drain worker hands over to its next execution; bounded by the collection fence and a no-progress stop"),
    (WORKER, "roles/run.invoker", ("service", "specimen-sam"), None, "call SAM 3")))
# The reads deploy_data.py --deploy makes as the data release, each with the narrowest standing role only it holds,
# which the owner extends when none grants the read; InventoryProjectRead never grows: the runtimes hold it too.
DATA_READS = {"firebasedataconnect.schemas.get": "specimenDataSchemaPublish",
              "firebasedataconnect.connectors.get": "specimenDataSchemaPublish",
              "firebaserules.releases.get": "specimenDataStorageRules",
              "firebaserules.rulesets.get": "specimenDataStorageRules",
              "cloudsql.instances.get": "specimenDataInventorySqlConnect",
              "cloudsql.databases.get": "specimenDataInventorySqlConnect"}
SECTIONS = {"roles": "Custom roles to create", "reads": "Data release read permissions", "missing": "Missing "
            "standing grants", "replace": "Grants to replace", "remove": "Grants to remove", "release": "Waits for "
            "the first runtime release", "digest": "Waits for the SAM 3 checkpoint digest", "window": "Time-bounded, "
            "through the setup window only", "review": "Review: not in the table", "other": "Other owner steps"}
HEADER = [f"Standing grants for project {PROJECT}, compared with docs/execution/golive/RELEASE.md section 5. "
          "Read-only: nothing was changed.", "Run the commands from a scratch directory: a conditional grant "
          "first writes its condition to a YAML file there.", ""]


def runtime_grants(settings) -> tuple[list[Grant], list[Grant]]:
    """Each runtime's reads of the exact secret versions it uses, and SAM 3's listing: (standing, waiting)."""
    grants = []
    for name, member, who in (("API", API, "the API"), ("WORKER", WORKER, "the worker"), ("SAM", SAM, "SAM 3")):
        role = getattr(settings, name)
        require(f"serviceAccount:{role['service_account']}" == member,
                f"runtime_settings.{name} runs as another identity")
        reads: dict[str, list[str]] = {}
        for variable, secret in role["secret_env"].items():
            require(re.fullmatch(r"[A-Z][A-Z0-9_]*", variable) and re.fullmatch(r"[a-z0-9_-]+", secret),
                    f"runtime_settings.{name} names a secret this plan cannot print exactly")
            reads.setdefault(secret, []).append(variable)
        for secret, variables in sorted(reads.items()):
            version = settings.SECRET_VERSIONS.get(secret)
            require(type(version) is int and version > 0, f"runtime_settings.SECRET_VERSIONS must pin {secret}")
            pinned = (f'resource.name.endsWith("/secrets/{secret}/versions/{version}")',
                      f"{secret.replace('-', '_')}_v{version}")
            grants.append(Grant(member, "roles/secretmanager.secretAccessor", ("secret", secret), pinned,
                                f"{who} reads version {version} of {secret} as {' and '.join(variables)}"))
    listing, digest = "mount the checkpoint read-only", settings.SAM_CHECKPOINT_SHA256
    if digest is settings.PENDING:
        return grants, [Grant(SAM, VIEW, BKT, None, listing)]
    require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
            "runtime_settings.SAM_CHECKPOINT_SHA256 must be 64 lowercase hex digits")
    condition = f'{LISTING}.startsWith("application/sha256/{digest}/sam3-cache")', "specimen_sam3_checkpoint_listing"
    return [*grants, Grant(SAM, VIEW, BKT, condition, listing)], []


def read(gcloud: Gcloud, *args: str) -> tuple[str, dict | None]:
    """("ok", response), ("absent", None) or ("failed", None); only a read of a known group reaches gcloud."""
    verb = next((args[len(group)] for group in READ_GROUPS if args[:len(group)] == group and args[len(group):]), "")
    require(verb in READ_VERBS, "owner_grants sends read-only gcloud commands only")
    try:
        code, out, err = gcloud(*args, "--format=json")
        response = strict_json(out) if code == 0 else None
    except (ValueError, OSError, subprocess.SubprocessError):
        return "failed", None
    if isinstance(response, dict):
        return "ok", response
    return ("absent" if code != 0 and MISSING.search(err or "") else "failed"), None


def bindings(policy: dict, resource: tuple[str, str]) -> set[tuple]:
    """(resource, role, member, condition) for each member of each binding; a condition is (expression, title)."""
    found = set()
    for binding in policy.get("bindings") or ():
        condition = binding.get("condition")
        key = None if condition is None else (str(condition.get("expression")), str(condition.get("title")))
        found.update((resource, str(binding.get("role")), str(member), key) for member in binding.get("members") or ())
    return found


def condition_note(condition: tuple[str, str] | None, now: float) -> str:
    """What kind of condition a live binding carries, without any of its text."""
    if condition is None:
        return "no condition"
    ends = TIME_BOUND.findall(condition[0])
    if not ends:
        return "another condition"
    return "an expired time-bound condition" if max(map(parse_stamp, ends)) <= now else "a time-bound condition"


def where(resource: tuple[str, str]) -> str:
    kind, name = resource
    return f"{kind.replace('-', ' ')} {KINDS[kind][1].format(name)}"


def command(verb: str, resource: tuple[str, str], member: str, role: str, condition: str = "--condition=None") -> str:
    """One exact add- or remove-iam-policy-binding; the condition flag only where the command group takes one."""
    group, target, scope, conditional = KINDS[resource[0]]
    return shlex.join(["gcloud", *group, verb, target.format(resource[1]), *scope, f"--member={member}",
                       f"--role={role}", *([condition] if conditional else [])])


def add_lines(grant: Grant) -> list[str]:
    """The grant's condition file, when it has a condition, then its one exact command."""
    if grant.condition is None:
        return [command("add-iam-policy-binding", grant.resource, grant.member, grant.role)]
    expression, title = grant.condition
    require(KINDS[grant.resource[0]][3] and "'" not in expression and "\n" not in expression
            and re.fullmatch(r"[a-z0-9_]+", title) is not None, "a condition must print exactly")
    return [f"cat > {title}.yaml <<'EOF'", f"expression: '{expression}'", f"title: {title}", "EOF",
            command("add-iam-policy-binding", grant.resource, grant.member, grant.role,
                    f"--condition-from-file={title}.yaml")]


def removal_lines(resource: tuple[str, str], role: str, member: str, condition) -> list[str]:
    """The exact removal of an unconditional binding; otherwise the member and role only, never condition text."""
    reason = ("no identity receives Owner or Editor" if role in REMOVE else f"{role[len(CUSTOM):]} opens only "
              "through the setup window, so an untimed binding of it is a standing grant the invariants forbid")
    if condition is None and member in WATCHED:
        return [f"# {reason}", command("remove-iam-policy-binding", resource, member, role)]
    who = member if member in WATCHED else "a member whose id is not printed"
    held = "" if condition is None else ("; its binding has a condition" + ("" if role in REMOVE else
                                         " without request.time") + ", whose text is not printed")
    return [f"# {reason}", f"- remove {role} for {who} on {where(resource)}{held}"]


def role_lines(name: str, live: dict | None) -> list[str]:
    """Create a missing role; set a differing or deleted one to exactly the table's permissions and stage."""
    title, description, permissions = ROLES[name]
    head = f"gcloud iam roles {{}} {name} --project={PROJECT}"
    exact = f"--permissions={','.join(permissions)} --stage=GA"
    if live is None:
        return [f"# {description}", f"{head.format('create')} --title={shlex.quote(title)} "
                f"--description={shlex.quote(description)} {exact}"]
    if (not live.get("deleted") and live.get("stage") == "GA"
            and sorted(live.get("includedPermissions") or ()) == sorted(permissions)):
        return []
    return [f"# {description}; {name} exists with other permissions, stage or state: set them exactly",
            *([head.format("undelete")] if live.get("deleted") else []), f"{head.format('update')} {exact}"]


def read_lines(definitions: dict[str, set]) -> list[str]:
    """The standing data-release role that grants each read on merge, or the owner command that adds the read."""
    held = [grant for grant in STANDING if grant.member == DATA]
    if any(grant.role not in definitions for grant in held):
        return ["- not compared: a standing data-release role could not be read; see Other owner steps"]
    lines, adds = [], {}
    for permission, target in DATA_READS.items():
        # A conditioned binding grants only what its condition admits: the inventory condition admits Cloud SQL.
        grant = next((grant for grant in held if permission in definitions[grant.role] and (
            grant.condition is None or grant.condition == SQL_SOURCE and permission.startswith("cloudsql."))), None)
        if grant is None:
            adds.setdefault(target, []).append(permission)
        else:
            lines.append(f"- {permission}: granted by {grant.role[len(CUSTOM):]}"
                         + (f", within its condition {grant.condition[1]}" if grant.condition else ""))
    for target, permissions in adds.items():
        condition = next(grant.condition for grant in held if grant.role == CUSTOM + target)
        binding = f"keeps the condition {condition[1]}" if condition else "stays as it is"
        lines += [f"# the data release reads with {' and '.join(permissions)} on merge: add to {target}, the "
                  f"narrowest standing role only it holds; its binding {binding}",
                  f"gcloud iam roles update {target} --project={PROJECT} --add-permissions={','.join(permissions)}"]
    return lines


def other_steps(settings) -> list[str]:
    """Public access prevention, the budget alert, and the readiness marker until its generation is pinned."""
    bucket = f"gs://{BUCKET}"
    steps = ["# public access prevention on the bucket",
             f"gcloud storage buckets update {bucket} --public-access-prevention",
             "# the Budget API, for the USD 25 budget alert (G9)",
             f"gcloud services enable billingbudgets.googleapis.com --project={PROJECT}",
             "# the USD 25 budget alert (G9): fill in BILLING_ACCOUNT_ID yourself, and never paste it anywhere",
             "gcloud billing budgets create --billing-account=BILLING_ACCOUNT_ID --display-name="
             f"{shlex.quote(f'{PROJECT} USD 25')} --budget-amount=25USD --filter-projects=projects/{PROJECT} "
             "--threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0"]
    if settings.READINESS_GENERATION is settings.PENDING:
        marker = f"{bucket}/{settings.READINESS_OBJECT}"
        require(settings.READINESS_OBJECT == f"application/sha256/{MARKER_SHA256}",
                "runtime_settings.READINESS_OBJECT must name the readiness marker's digest")
        steps += ["# upload the API's readiness marker once; the upload never replaces an existing object",
                  f"printf '{MARKER}\\n' | gcloud storage cp --if-generation-match=0 - {marker}",
                  "# read its generation, and commit it as runtime_settings.READINESS_GENERATION",
                  f"gcloud storage objects describe {marker} --format='value(generation)'"]
    return steps


def plan(settings, *, runner=None, clock=time.time) -> str:
    """Read the live state once, compare it with the table and return the owner's report."""
    now = clock()
    derived, waiting = runtime_grants(settings)
    wanted = (*STANDING, *derived, *AFTER_RELEASE)
    resources = list(dict.fromkeys(grant.resource for grant in wanted))
    data_roles = list(dict.fromkeys(grant.role[len(CUSTOM):] for grant in STANDING if grant.member == DATA))
    reads = len(ROLES) + len(data_roles) + 2 * len(resources)
    gcloud = Gcloud(now + DEADLINE_SECONDS, ceiling=reads, runner=runner, clock=clock)
    out = {key: [] for key in SECTIONS}
    unread, absent, definitions, removals = [], [], {}, []
    for name in (*ROLES, *data_roles):
        status, found = read(gcloud, "iam", "roles", "describe", name)
        if status == "failed":
            unread.append(f"# could not read the custom role {name}; rerun the plan")
        elif name in ROLES:
            out["roles"] += role_lines(name, found)
        elif status == "absent" or found.get("deleted"):
            absent.append(f"# owner prerequisite: the custom role {name} does not exist; restore it before its grants")
        else:
            definitions[CUSTOM + name] = set(found.get("includedPermissions") or ())
    out["reads"] = read_lines(definitions)
    state, live = {}, set()
    for resource in resources:
        group, target, scope, _ = KINDS[resource[0]]
        args = (target.format(resource[1]), *(flag for flag in scope if not flag.startswith("--project=")))
        state[resource] = read(gcloud, *group, "describe", *args)[0] if resource[0] in DESCRIBED_FIRST else "ok"
        if state[resource] == "ok":
            state[resource], policy = read(gcloud, *group, "get-iam-policy", *args)
            live |= bindings(policy or {}, resource)
        if state[resource] == "failed":
            unread.append(f"# could not read {where(resource)}; its grants were not compared: rerun the plan")
        elif state[resource] == "absent" and resource[0] not in CREATED_BY_RELEASE:
            absent.append(f"# owner prerequisite: {where(resource)} does not exist; create it before its grants")
    exact = {(grant.resource, grant.role, grant.member, grant.condition) for grant in wanted}
    stray, replaced = live - exact, set()
    for grant in wanted:
        status, key = state[grant.resource], (grant.resource, grant.role, grant.member, grant.condition)
        if status == "failed" or key in live:
            continue
        if status == "absent" and grant.resource[0] in CREATED_BY_RELEASE:
            out["release"] += [f"# {grant.reason}; waits for the first runtime release to create "
                               f"{where(grant.resource)}", *add_lines(grant)]
            continue
        old = {entry for entry in stray if entry[:3] == key[:3]}
        replaced |= old
        if old:
            notes = " and ".join(sorted({condition_note(entry[3], now) for entry in old}))
            out["replace"] += [f"# {grant.reason}; the live binding of this role has {notes} and may stay "
                               "until you remove it", *add_lines(grant)]
        else:
            out["missing"] += [f"# {grant.reason}", *add_lines(grant)]
    for grant in waiting:
        out["digest"] += [f"# {grant.reason}; waits for runtime_settings.SAM_CHECKPOINT_SHA256",
                          f"- {grant.role} for {grant.member} on {where(grant.resource)}, conditioned on listings "
                          "under application/sha256/<checkpoint digest>/sam3-cache"]
    for resource, role, member, condition in stray - replaced:
        label = WINDOW_ONLY.get(role[len(CUSTOM):]) if role.startswith(CUSTOM) else None
        if (role in REMOVE and member in WATCHED) or (label and not (condition and "request.time" in condition[0])):
            removals.append(((role not in REMOVE, where(resource), role, member),
                             removal_lines(resource, role, member, condition)))
        elif member in WATCHED:
            shown = role if SAFE_ROLE.fullmatch(role) else "a role defined outside this project"
            line = f"- {label or 'review: not in the table'}: {shown} for {member} on {where(resource)}"
            out["window" if label else "review"].append(f"{line}, with {condition_note(condition, now)}")
    out["remove"] = [line for _, lines in sorted(removals, key=lambda removal: removal[0]) for line in lines]
    for key in ("window", "review"):
        out[key].sort()
    out["other"] = [*unread, *absent, *other_steps(settings)]
    lines = list(HEADER)
    for key, title in SECTIONS.items():
        lines += [f"{title}:", *(out[key] or ["(none)"]), ""]
    return "\n".join(lines).rstrip("\n")


def main(argv=None, *, runner=None, settings=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("plan",), help="print the owner's reviewed list; nothing changes")
    parser.parse_args(argv)
    print(plan(settings or importlib.import_module("runtime_settings"), runner=runner))
    return 0


if __name__ == "__main__":
    sys.exit(main())
