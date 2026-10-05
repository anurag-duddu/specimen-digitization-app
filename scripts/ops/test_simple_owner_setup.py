"""scripts/ops/owner_setup.sh against fake gcloud, gh, curl and sleep: a dry run changes and starts nothing, an apply
changes each thing once, and the releases start only when the setup went through and the workflows are on main.

The fakes are a small simulator: reads are rendered from a JSON state in the formats the script asks for, writes
are logged and applied to that state, a workflow run plays back a scripted list of states, a sleep is logged and
returns at once, and any command or flag the fakes do not know fails the run.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

import pytest
import yaml

SCRIPT = Path(__file__).resolve().with_name("owner_setup.sh")
ROOT = SCRIPT.parents[2]
PROJECT = "specimen-digitization"
REPOSITORY = "anurag-duddu/specimen-digitization-app"
BUCKET = f"{PROJECT}.firebasestorage.app"
CUSTOM = f"projects/{PROJECT}/roles/"
SQL_USER = f"specimen-data-release@{PROJECT}.iam"
EMAIL = "specimen-{}@specimen-digitization.iam.gserviceaccount.com".format
DATA, BUILD, RELEASE, API, WORKER, SAM = (f"serviceAccount:{EMAIL(name)}" for name in (
    "data-release", "runtime-build", "runtime-release", "api-runtime", "worker-runtime", "sam-runtime"))
PLANE = ("principalSet://iam.googleapis.com/projects/716045864126/locations/global/workloadIdentityPools/"
         "github-actions/attribute.release_plane/")
PLANES = ("specimen-data-release", "specimen-runtime-build", "specimen-runtime-release")
ACCESSOR = "roles/secretmanager.secretAccessor"
API_URL = "https://specimen-api-716045864126.us-east4.run.app"
SITE_KEY = "6LfP0bEtAAAAAGtD_o-SD8EnjvgGGzVugURtWUAw"  # pragma: allowlist secret (public site key)
ARTIFACT = "DATA_BOOTSTRAP_ARTIFACT_B64"
PUSH = "assertion.event_name == 'push'"
EITHER = "(assertion.event_name == 'push' || assertion.event_name == 'workflow_dispatch')"
# The data provider's condition after the script ran, written out: only the event clause differs from the live one.
DATA_PROVIDER_AFTER = (
    "assertion.repository_id == '1360732425' && assertion.repository_owner_id == '140138196' && "
    "assertion.repository == 'anurag-duddu/specimen-digitization-app' && "
    "(assertion.event_name == 'push' || assertion.event_name == 'workflow_dispatch') && "
    "assertion.ref == 'refs/heads/main' && assertion.environment == 'data-production' && "
    "assertion.sub == 'repo:anurag-duddu@140138196/specimen-digitization-app@1360732425:environment:data-production'"
    " && assertion.workflow_ref == "
    "'anurag-duddu/specimen-digitization-app/.github/workflows/data-release.yml@refs/heads/main'"
    " && attribute.release_plane == 'specimen-data-release'")
# Each custom role's exact permissions, sorted as the script passes them.
ROLES = {
    "specimenGeoreferenceDatasets": ["storage.objects.create", "storage.objects.get"],
    "specimenDataSchemaPublish": [
        "firebasedataconnect.connectors.create", "firebasedataconnect.connectors.get",
        "firebasedataconnect.connectors.update", "firebasedataconnect.operations.get",
        "firebasedataconnect.schemas.create", "firebasedataconnect.schemas.get", "firebasedataconnect.schemas.update"],
    "specimenDataStorageRules": [
        "firebaserules.releases.create", "firebaserules.releases.get", "firebaserules.releases.update",
        "firebaserules.rulesets.create", "firebaserules.rulesets.get"],
    "specimenDataInventoryProjectRead": ["resourcemanager.projects.get"],
    "specimenDataInventorySqlConnect": [
        "cloudsql.databases.get", "cloudsql.instances.connect", "cloudsql.instances.get", "cloudsql.instances.login"],
    "specimenDataBootstrapRows": [
        "firebasedataconnect.services.executeGraphql", "firebasedataconnect.services.executeGraphqlRead"],
    "specimenRuntimeRelease": [
        "run.jobs.create", "run.jobs.get", "run.jobs.getIamPolicy", "run.jobs.update", "run.operations.get", "run.revisions.get",
        "run.services.create", "run.services.get", "run.services.getIamPolicy", "run.services.update"],
    "specimenRuntimeInvokerPolicy": ["run.services.getIamPolicy", "run.services.setIamPolicy"],  # no run.jobs
    "specimenWorkerExecution": ["run.executions.get", "run.jobs.run"],
    "specimenWorkerRead": ["run.jobs.get"],
    "specimenResearchCaptureRead": ["storage.objects.get"],
    "specimenRuntimeConnector": [
        "firebasedataconnect.connectors.impersonateMutation", "firebasedataconnect.connectors.impersonateQuery"],
    "specimenApiUserLookup": ["firebaseauth.users.get"],
}
NEW_ROLES = ("specimenDataBootstrapRows", "specimenRuntimeInvokerPolicy", "specimenWorkerExecution",
             "specimenGeoreferenceDatasets", "specimenWorkerRead", "specimenResearchCaptureRead")
MAPS_KEY = "specimen-google-maps-key"  # retired: the owner took Google Maps out of the pipeline
LIVE_PINS = (  # member, secret, version: the nine pinned reads live on 2026-10-03, the retired Maps key among them
    (API, "specimen-worker-logfire", 1), (API, "specimen-source-registry", 1), (API, "specimen-collection-bindings", 1),
    (WORKER, "huggingface-runtime-token", 2), (WORKER, "specimen-worker-logfire", 1),
    (WORKER, MAPS_KEY, 1), (WORKER, "specimen-worker-actor-uid", 1),
    (WORKER, "specimen-collection-bindings", 1), (SAM, "specimen-worker-logfire", 1))
RETIRE = ("RELEASE_AUTHORIZED_SHA", "RELEASE_BUDGET_LEDGER_SHA256", "RELEASE_INPUTS_SHA256", "RELEASE_PACKET_SHA256",
          "RELEASE_INPUTS_B64", "DATA_BOOTSTRAP_APPROVED_SHA256", "DATA_WORKER_ACTOR_UID",
          "data-initialization-production", "provider specimen-data-initialize",
          "service account specimen-data-initialize@", "specimenFirstReleaseMetadataRead",
          f"secret {MAPS_KEY} and the read of its version 1 by specimen-worker-runtime")
# Any of these words in a gcloud command line, and any of these gh commands, changes something; the fakes' own
# "write" flag is checked against them.
MUTATING = {"add-iam-policy-binding", "remove-iam-policy-binding", "set-iam-policy", "create", "update", "undelete",
            "delete", "assign-roles", "update-oidc", "set", "deploy"}
GH_WRITES = {("variable", "set"), ("secret", "set"), ("workflow", "run"), ("run", "rerun")}
RUNS = f"https://github.com/{REPOSITORY}/actions/runs/"
VERSION_URL, DEPLOYMENT_URL = API_URL + "/version", "https://specimen-digitization.web.app/deployment.json"
# The site's compiled program, as the web stage reads it to see whether the build knew the API address.
PROGRAM_URL = "https://specimen-digitization.web.app/main.dart.js"
PROGRAM = "(function dartProgram(){{var api='{}';}})()".format
NOT_PICKED_UP = "  WARNING: web: variables not picked up; the next merge to main will redeploy"
COULD_NOT_CHECK = ("  WARNING: web app: could not check whether the site points at the API "
                   f"({PROGRAM_URL} did not come back as the built program)")
COMMIT = "ab" * 20  # a stand-in for the forty hex digits of a commit
START_DATA = ["gh", "workflow", "run", "data-release.yml", "--ref", "main", "-R", REPOSITORY]
START_RUNTIME = ["gh", "workflow", "run", "runtime-release.yml", "--ref", "main", "-R", REPOSITORY]
SAFE = "Safe to run again: every step checks what exists first."
# What every tool the script starts must find in its environment: no question, no pager, no update notice, no colour.
QUIET = {"CLOUDSDK_CORE_DISABLE_PROMPTS": "1", "GH_PROMPT_DISABLED": "1", "GH_PAGER": "cat", "PAGER": "cat",
         "GH_NO_UPDATE_NOTIFIER": "1", "NO_COLOR": "1"}
SHELLS = sorted({os.path.realpath(path) for path in ("/bin/bash", shutil.which("bash"), "/opt/homebrew/bin/bash",
                                                    "/usr/local/bin/bash") if path and Path(path).exists()})

FAKE = r'''
import hashlib, json, os, stat, sys

PROJECT = "specimen-digitization"
REPOSITORY = "anurag-duddu/specimen-digitization-app"
INSTANCE = "specimen-digitization-instance"
ENVIRONMENT = "data-production"
POLICY_FORMAT = ("value(bindings.members,bindings.role,bindings.condition.title,"
                 "bindings.condition.expression,bindings.condition.description)")
ROLE_FORMAT = 'value[separator="|"](stage,deleted,includedPermissions.list())'
PROVIDER = {"workload-identity-pool": "github-actions", "location": "global", "project": PROJECT}
KINDS = {("projects",): ("project", {}), ("storage", "buckets"): ("bucket", {}),
         ("artifacts", "repositories"): ("repository", {"location": "us-east4", "project": PROJECT}),
         ("iam", "service-accounts"): ("service-account", {"project": PROJECT}),
         ("secrets",): ("secret", {"project": PROJECT}),
         ("run", "services"): ("service", {"region": "us-east4", "project": PROJECT}),
         ("run", "jobs"): ("job", {"region": "us-east4", "project": PROJECT})}
POLICY_VERBS = ("get-iam-policy", "add-iam-policy-binding", "remove-iam-policy-binding")
FIELDS = ("title", "expression", "description")
# The two jq programs the script hands to gh; the fake renders what they print and accepts no other.
RUN_JQ = (r'"R\t\(.status)\t\(.conclusion)\t\(.url)\t\(.attempt)", ((.jobs // [])[] | . as $job | '
          r'(($job.steps // [])[] | select(.status == "completed") | '
          r'"S\t\($job.name)\t\(.number)\t\(.name)\t\(.conclusion)"), '
          r'(select($job.status == "completed") | "J\t\($job.name)\t\($job.conclusion)"))')
NEWEST_JQ = r'.[0] | select(. != null) | "\(.databaseId)\t\(.attempt)\t\(.status)\t\(.url)"'


class Unsupported(Exception):
    pass


def expect(found, wanted):
    if found != wanted:
        raise Unsupported(f"expected {wanted!r}, got {found!r}")


def condition_of(text):
    """A condition file's fields; the script writes each value as a YAML single-quoted scalar."""
    fields = {}
    for line in text.splitlines():
        key, _, value = line.partition(": ")
        if len(value) < 2 or value[0] != "'" or value[-1] != "'":
            raise Unsupported(f"condition line {line!r}")
        fields[key] = value[1:-1].replace("''", "'")
    if not fields.get("title") or not fields.get("expression") or set(fields) - set(FIELDS):
        raise Unsupported(f"condition fields {sorted(fields)}")
    return {field: fields.get(field) for field in FIELDS}


def policy(verb, kind, scope, name, flags, state, entry):
    if kind == "bucket":
        expect(name[:5], "gs://")
        name = name[5:]
    if kind == "service" and name not in state["services"]:  # a service has no policy before it exists
        entry["write"] = verb != "get-iam-policy"
        print(f"ERROR: (gcloud.run.services.{verb}) NOT_FOUND: Resource '{name}' of kind 'SERVICE' does not exist.",
              file=sys.stderr)
        return 1
    bindings = state["policies"].setdefault(f"{kind}/{name}", [])
    if verb == "get-iam-policy":
        expect(flags, {**scope, "flatten": "bindings[].members", "format": POLICY_FORMAT})
        for binding in bindings:
            held = binding["condition"] or {}
            for member in binding["members"]:
                print("\t".join([member, binding["role"], *(held.get(field) or "" for field in FIELDS)]))
        if not bindings:
            print("\t" * 4)  # gcloud 582 prints one row of empty fields for an empty policy
        return 0
    entry["write"] = True
    member, role = flags.pop("member"), flags.pop("role")
    if "condition-from-file" in flags:
        with open(flags.pop("condition-from-file")) as handle:
            entry["condition_text"] = handle.read()
        condition = condition_of(entry["condition_text"])
    else:
        expect(flags.pop("condition", ""), "" if kind == "job" else "None")
        condition = None
    if kind == "job":
        expect(flags.pop("quiet"), None)
    expect(flags, scope)
    # gcloud matches a binding by role and the whole condition: title, expression and description.
    same = [binding for binding in bindings if binding["role"] == role and binding["condition"] == condition]
    if verb == "add-iam-policy-binding":
        if not same:
            bindings.append({"role": role, "members": [member], "condition": condition})
        elif member not in same[0]["members"]:
            same[0]["members"].append(member)
        return 0
    held = [binding for binding in same if member in binding["members"]]
    if not held:
        print("ERROR: Policy binding with the specified principal, role, and condition not found!", file=sys.stderr)
        return 1
    held[0]["members"].remove(member)
    bindings[:] = [binding for binding in bindings if binding["members"]]
    return 0


def role(verb, name, flags, state, entry):
    live = state["roles"].get(name)
    if verb == "describe":
        expect(flags, {"project": PROJECT, "format": ROLE_FORMAT})
        if live is None:
            print(f"ERROR: (gcloud.iam.roles.describe) NOT_FOUND: The role named projects/{PROJECT}/roles/{name} "
                  "was not found.", file=sys.stderr)
            return 1
        print("|".join([live["stage"], "True" if live["deleted"] else "", ",".join(live["permissions"])]))
        return 0
    entry["write"] = True
    if verb == "create" and live is None:
        expect(sorted(flags), ["description", "permissions", "project", "stage", "title"])
        expect((flags["project"], flags["stage"]), (PROJECT, "GA"))
        state["roles"][name] = {"stage": "GA", "deleted": False, "permissions": flags["permissions"].split(",")}
        return 0
    if verb == "update" and live is not None and not live["deleted"]:
        expect(sorted(flags), ["permissions", "project", "stage"])
        expect((flags["project"], flags["stage"]), (PROJECT, "GA"))
        live.update(stage="GA", permissions=flags["permissions"].split(","))
        return 0
    if verb == "undelete" and live is not None and live["deleted"]:
        expect(flags, {"project": PROJECT})
        live["deleted"] = False
        return 0
    raise Unsupported(f"gcloud iam roles {verb} {name}")


def gcloud(argv, state, entry):
    words = [arg for arg in argv if not arg.startswith("--")]
    flags = dict(arg[2:].split("=", 1) if "=" in arg else (arg[2:], None) for arg in argv if arg.startswith("--"))
    if words == ["config", "get-value", "account"]:
        expect(flags, {})
        if state["account"]:
            print(state["account"])
        else:
            print("(unset)", file=sys.stderr)
        return 0
    if words[:3] == ["run", "services", "describe"] and len(words) == 4:
        expect(flags, {"region": "us-east4", "project": PROJECT, "format": "value(metadata.name)"})
        if state["unreadable_services"]:
            print("ERROR: (gcloud.run.services.describe) HTTPError 503: Service Unavailable.", file=sys.stderr)
            return 1
        if words[3] not in state["services"]:
            print(f"ERROR: (gcloud.run.services.describe) Cannot find service [{words[3]}]", file=sys.stderr)
            return 1
        print(words[3])
        return 0
    if words == ["projects", "describe", PROJECT]:
        expect(flags, {"format": "value(projectNumber)"})
        print(state["project_number"])
        return 0
    for group, (kind, scope) in KINDS.items():
        if tuple(words[:len(group)]) == group and len(words) == len(group) + 2 and words[len(group)] in POLICY_VERBS:
            return policy(words[len(group)], kind, scope, words[-1], flags, state, entry)
    if words[:2] == ["iam", "roles"] and len(words) == 4:
        return role(words[2], words[3], flags, state, entry)
    if words[:3] == ["sql", "users", "describe"] and len(words) == 4 and words[3] not in state["sql_roles"]:
        print("ERROR: (gcloud.sql.users.describe) HTTPError 404: Not Found.", file=sys.stderr)
        return 1
    if words[:2] == ["sql", "users"] and len(words) == 4 and words[3] in state["sql_roles"]:
        held = state["sql_roles"][words[3]]
        if words[2] == "describe":
            expect(flags, {"instance": INSTANCE, "project": PROJECT, "format": "value(databaseRoles.list())"})
            print(",".join(held))
            return 0
        if words[2] == "assign-roles":
            entry["write"] = True
            wanted = flags.pop("database-roles").split(",")
            expect(flags, {"instance": INSTANCE, "project": PROJECT, "type": "CLOUD_IAM_SERVICE_ACCOUNT"})
            held.extend(name for name in wanted if name not in held)
            return 0
    if words[:3] == ["iam", "workload-identity-pools", "providers"] and len(words) == 5 \
            and words[4] in state["providers"]:
        if words[3] == "describe":
            expect(flags, {**PROVIDER, "format": "value(attributeCondition)"})
            print(state["providers"][words[4]])
            return 0
        if words[3] == "update-oidc":
            entry["write"] = True
            condition = flags.pop("attribute-condition")
            expect(flags, PROVIDER)
            state["providers"][words[4]] = condition
            return 0
    raise Unsupported("gcloud " + " ".join(argv))


def gh(argv, state, entry):
    repository = ["-R", REPOSITORY]
    if argv == ["auth", "status"]:
        return 0 if state["gh_signed_in"] else 1
    if argv == ["api", "user", "--jq", ".login"]:
        print(state["login"])
        return 0
    if argv[:2] == ["variable", "get"] and argv[3:] == repository:
        if argv[2] not in state["variables"]:
            print(f"variable {argv[2]} was not found", file=sys.stderr)
            return 1
        print(state["variables"][argv[2]])
        return 0
    if argv[:2] == ["variable", "set"] and argv[3:6] == [*repository, "--body"] and len(argv) == 7:
        entry["write"] = True
        state["variables"][argv[2]] = argv[6]
        return 0
    if argv == ["secret", "list", "--env", ENVIRONMENT, *repository, "--json", "name", "--jq", ".[].name"]:
        print("\n".join(state["secrets"]))
        return 0
    if argv[:2] == ["secret", "set"] and argv[3:] == ["--env", ENVIRONMENT, *repository]:
        entry["write"] = True
        value = sys.stdin.buffer.read()
        entry["stdin_sha256"], entry["stdin_length"] = hashlib.sha256(value).hexdigest(), len(value)
        if argv[2] not in state["secrets"]:
            state["secrets"].append(argv[2])
        return 0
    if argv[:2] == ["workflow", "view"] and argv[3:] == [*repository, "--ref", "main", "--yaml"]:
        if argv[2] not in state["workflows"]:
            print(f"could not find any workflows named {argv[2]}", file=sys.stderr)
            return 1
        print(state["workflows"][argv[2]])
        return 0
    if argv[:2] == ["workflow", "run"] and argv[3:] == ["--ref", "main", *repository]:
        entry["write"] = True
        if "workflow_dispatch:" not in state["workflows"].get(argv[2], ""):
            print("could not create workflow dispatch event: HTTP 422", file=sys.stderr)
            return 1
        if not state["dispatches"].get(argv[2]):
            raise Unsupported(f"no scripted run is left for another start of {argv[2]}")
        state["next_id"] += 1
        state["runs"].append({"id": state["next_id"], "workflow": argv[2], "event": "workflow_dispatch", "at": 0,
                              "frames": state["dispatches"][argv[2]].pop(0), "hidden": state["appear_after"]})
        return 0
    if argv[:3] == ["run", "list", "--workflow"] and argv[4:8] == [*repository, "--branch", "main"] \
            and argv[8] == "--event" and argv[10:12] == ["--limit", "1"]:
        runs = [run for run in state["runs"] if (run["workflow"], run["event"]) == (argv[3], argv[9])]
        if argv[9] == "workflow_dispatch":
            expect(argv[12:], ["--json", "databaseId", "--jq", ".[0].databaseId // empty"])
            entry["advance"] = True  # a new run shows up only after its scripted number of listings
            seen = [run["id"] for run in runs if run["hidden"] == 0]
            for run in runs:
                run["hidden"] = max(run["hidden"] - 1, 0)
            if seen:
                print(max(seen))
            return 0
        expect((argv[9], argv[12:]), ("push", ["--json", "databaseId,attempt,status,conclusion,createdAt,url",
                                               "--jq", NEWEST_JQ]))
        if runs:
            run = max(runs, key=lambda run: run["id"])
            now = run["frames"][run["at"]]
            print("\t".join([str(run["id"]), str(now["attempt"]), now["status"], address(run)]))
        return 0
    if argv[:2] in (["run", "view"], ["run", "rerun"]):
        found = [run for run in state["runs"] if str(run["id"]) == argv[2]]
        if not found:
            raise Unsupported(f"gh run {argv[1]} of unknown run {argv[2]}")
        run = found[0]
        now = run["frames"][run["at"]]
        if argv[1] == "view":
            expect(argv[3:], [*repository, "--json", "attempt,status,conclusion,url,jobs", "--jq", RUN_JQ])
            entry["advance"] = True  # each reading moves the run one scripted state on; the last state stays
            run["at"] = min(run["at"] + 1, len(run["frames"]) - 1)
            if now.get("deploys") and now["deploys"] not in state["services"]:
                # The release this run stands for created the service and opened it to the web client.
                state["services"].append(now["deploys"])
                state["policies"][f"service/{now['deploys']}"] = [
                    {"role": "roles/run.invoker", "members": ["allUsers"], "condition": None}]
            if now.get("unreadable"):
                print("HTTP 502: Bad Gateway", file=sys.stderr)
                return 1
            lines = ["\t".join(["R", now["status"], now["conclusion"], address(run), str(now["attempt"])])]
            for job in now["jobs"]:
                lines += ["\t".join(["S", job["name"], str(step["number"]), step["name"], step["conclusion"]])
                          for step in job["steps"] if step["status"] == "completed"]
                if job["status"] == "completed":
                    lines.append("\t".join(["J", job["name"], job["conclusion"]]))
            print("\n".join(lines))
            return 0
        expect(argv[3:], repository)
        entry["write"] = True
        if now["status"] != "completed":
            print(f"run {argv[2]} cannot be rerun; This workflow is already running", file=sys.stderr)
            return 1
        if not state["reruns"].get(argv[2]):
            raise Unsupported(f"no scripted attempt is left for another rerun of {argv[2]}")
        run["frames"], run["at"] = state["reruns"][argv[2]].pop(0), 0
        return 0
    raise Unsupported("gh " + " ".join(argv))


def address(run):
    return f"https://github.com/{REPOSITORY}/actions/runs/{run['id']}"


def curl(argv, state, entry):
    """Only the script's two reads, both a GET that fails on an HTTP error: a small answer printed within ten
    seconds, and the site's program saved to a file within sixty, asked for under an address no cache has seen."""
    expect(argv[:2], ["-fsS", "--max-time"])
    if argv[2] == "10":
        expect(len(argv), 4)
        address, target = argv[3], None
    else:
        expect((argv[2], argv[3], len(argv)), ("60", "-o", 6))
        target, (address, mark, stamp) = argv[4], argv[5].partition("?check=")
        expect((address, mark, stamp.isdigit()),
               ("https://specimen-digitization.web.app/main.dart.js", "?check=", True))
    body = state["http"].get(address)
    if body is None:
        print("curl: (22) The requested URL returned error: 404", file=sys.stderr)
        return 22
    if target is None:
        print(body)
    else:
        with open(target, "wb") as handle:  # {"hex": ...} stands for bytes that are no text, such as a gzip body
            handle.write(bytes.fromhex(body["hex"]) if isinstance(body, dict) else body.encode())
    return 0


def standard_input():
    """What this tool was given to read from: the script must hand every tool /dev/null, never its own input."""
    try:
        mode = os.fstat(0)
    except OSError:
        return "closed"
    if os.isatty(0):
        return "terminal"
    if stat.S_ISCHR(mode.st_mode) and mode.st_rdev == os.stat(os.devnull).st_rdev:
        return "null"
    return "pipe" if stat.S_ISFIFO(mode.st_mode) else "file"


def main():
    tool, argv = sys.argv[1], sys.argv[2:]
    root = os.environ["FAKE_ROOT"]
    with open(os.path.join(root, "state.json")) as handle:
        state = json.load(handle)
    quiet = ("CLOUDSDK_CORE_DISABLE_PROMPTS", "GH_PROMPT_DISABLED", "GH_PAGER", "PAGER", "GH_NO_UPDATE_NOTIFIER",
             "NO_COLOR")
    entry = {"tool": tool, "argv": argv, "write": False, "stdin": standard_input(),
             "quiet": {name: os.environ.get(name) for name in quiet}}
    try:
        code = {"gcloud": gcloud, "gh": gh, "curl": curl}[tool](argv, state, entry)
    except Unsupported as error:
        entry["unsupported"] = str(error)
        print(f"fake {tool}: unsupported: {error}", file=sys.stderr)
        code = 97
    if entry["write"] and code == 0 and set(state["fail"]) & set(argv):
        print(f"ERROR: ({tool}) INTERNAL: the service refused this change.", file=sys.stderr)
        code = 1
    with open(os.path.join(root, "calls.jsonl"), "a") as handle:
        handle.write(json.dumps(entry) + "\n")
    if (entry["write"] and code == 0) or entry.get("advance"):  # a failed reading still uses up its state
        with open(os.path.join(root, "state.json"), "w") as handle:
            json.dump(state, handle)
    return code


sys.exit(main())
'''


def condition(title, expression, description=None):
    return {"title": title, "expression": expression, "description": description}


def binding(role, members, held=None):
    return {"role": role, "members": list(members), "condition": held}


def pin(secret, version):
    return condition(f"{secret.replace('-', '_')}_v{version}",
                     f'resource.name.endsWith("/secrets/{secret}/versions/{version}")')


def window(role, start, end):
    return condition(f"specimen_pr21_{role}",
                     f"request.time >= timestamp('{start}') && request.time < timestamp('{end}')", PR21)


def provider(environment, workflow, plane, event=PUSH):
    return ("assertion.repository_id == '1360732425' && assertion.repository_owner_id == '140138196' && "
            f"assertion.repository == '{REPOSITORY}' && {event} && assertion.ref == 'refs/heads/main' && "
            f"assertion.environment == '{environment}' && assertion.sub == 'repo:anurag-duddu@140138196/"
            f"specimen-digitization-app@1360732425:environment:{environment}' && assertion.workflow_ref == "
            f"'{REPOSITORY}/.github/workflows/{workflow}@refs/heads/main' && attribute.release_plane == '{plane}'")


# Keep the self-contained setup's allowlist exact; no application-prefix grant
# belongs to the data publisher. Integration also compares this to the manifest.
GEO_SHA256 = (
    "7a9189637a5af9677a92e765b9448bdfe425383fae8e39a6808a96b8fe8f19d0",  # pragma: allowlist secret (public file digest)
    "155424cb1ede34d2b0e4e92b51b5c359164e3d0834507166d1b28969389e2e5c",  # pragma: allowlist secret (public file digest)
    "0f6f645d310b4aa02fffc0cba0f3ad130a5fd2303d953e5f8931ba48817b0c6c",  # pragma: allowlist secret (public file digest)
    "37d8bc68715f937fc2a568d9e88245aa6323a46cc4c2e56a5836fa89febe8536",  # pragma: allowlist secret (public file digest)
    "7a8dc145e57ea42c26b35393a281f248ff35e70aaf794eed20c989ff2d718759",  # pragma: allowlist secret (public file digest)
    "24965821b5541833efb63ced996ac9a508feb049ec02442727f28cbdf15dfe96",  # pragma: allowlist secret (public file digest)
    "8eeef6a9a525a81a647dcaac85e1337b990fc527c4a0e9c70556d5b0905be087",  # pragma: allowlist secret (public file digest)
    "fa77b9f17db2e419acaae714a935f7812be4409e2983675d34020e8426a3e189",  # pragma: allowlist secret (public file digest)
    "2ece3d44a5c6a2afb385ffbf3a6b88d83e4d3a3e7eed9a52cb3be1bc59e289fc",  # pragma: allowlist secret (public file digest)
    "f178eda98c46329380bdbb43f0637b4c43535bc843de6a0b8b960193b8f4363f",  # pragma: allowlist secret (public file digest)
)
GEO = condition("specimen_georeference_datasets", "resource.name in [" + ",".join(
    f'"projects/_/buckets/{BUCKET}/objects/application/sha256/{sha}"' for sha in GEO_SHA256) + "]")


PR21 = "PR21 finite IAM access; project_time_only; SQL privilege separately capped at 600 seconds after signed parity."
APP = condition("specimen_application_objects", 'resource.name.startsWith("projects/_/buckets/'
                'specimen-digitization.firebasestorage.app/objects/application/sha256/")')
SLIDES = condition("specimen_source_slides", 'resource.name.startsWith("projects/_/buckets/'
                   'specimen-digitization.firebasestorage.app/objects/microscopic-slides/") || api.getAttribute('
                   '"storage.googleapis.com/objectListPrefix", "").startsWith("microscopic-slides/")')
# The research harness's three object prefixes, for the worker only; written out, not composed.
RESEARCH = condition("specimen_research_objects", 'resource.name.startsWith("projects/_/buckets/'
                     'specimen-digitization.firebasestorage.app/objects/research-capture/") || '
                     'resource.name.startsWith("projects/_/buckets/specimen-digitization.firebasestorage.app/objects/'
                     'research-journal/") || resource.name.startsWith("projects/_/buckets/'
                     'specimen-digitization.firebasestorage.app/objects/research-media/")')
SQL = condition("specimen_source_inventory_only", "resource.name == 'projects/specimen-digitization/instances/"
                "specimen-digitization-instance' && resource.service == 'sqladmin.googleapis.com' && resource.type == "
                "'sqladmin.googleapis.com/Instance'",
                "Connect, IAM login and metadata only for the existing source instance.")
CAPTURE_READ = condition("specimen_api_research_capture", 'resource.name.startsWith("projects/_/buckets/'
    'specimen-digitization.firebasestorage.app/objects/research-capture/")')
EXPIRED = {  # the four leftovers, as read from the live policy on 2026-10-03
    "specimenDataSchemaPublish": window("specimenDataSchemaPublish", "2026-09-13T20:25:15Z", "2026-09-13T22:25:15Z"),
    "specimenDataStorageRules": window("specimenDataStorageRules", "2026-09-13T20:25:15Z", "2026-09-13T22:25:15Z"),
    "specimenDataSourceBackup": window("specimenDataSourceBackup", "2026-09-13T20:25:15Z", "2026-09-13T22:25:15Z"),
    "specimenDataRuntimeAbsence": window("specimenDataRuntimeAbsence", "2026-10-02T01:58:34Z", "2026-10-02T03:58:34Z"),
}
OLD_WORKFLOW = "on:\n  push:\n    branches:\n      - main\n\njobs: {}"  # main before the merge: push only
NEW_WORKFLOW = "on:\n  push:\n    branches:\n      - main\n  workflow_dispatch:\n\njobs: {}"
PROVIDERS = {"specimen-data-release": ("data-production", "data-release.yml"),
             "specimen-runtime-build": ("runtime-build-production", "runtime-release.yml"),
             "specimen-runtime-release": ("runtime-production", "runtime-release.yml")}


def fresh_state():
    """A project where nothing is granted yet: no custom role, no binding, no variable, no secret."""
    return {"account": "owner@example.test", "login": "example-owner", "gh_signed_in": True,
            "project_number": "716045864126", "policies": {}, "roles": {}, "sql_roles": {SQL_USER: []},
            "providers": {name: provider(*rest, name) for name, rest in PROVIDERS.items()},
            "variables": {}, "secrets": [], "fail": [],
            "workflows": {"data-release.yml": OLD_WORKFLOW, "runtime-release.yml": OLD_WORKFLOW},
            "runs": [], "dispatches": {}, "reruns": {}, "next_id": 500, "appear_after": 0, "http": {},
            "services": [], "unreadable_services": False}


def live_state():
    """The project as read on 2026-10-03, without private values, plus one drifted role: every kind of change occurs."""
    state = fresh_state()
    state["roles"] = {name: {"stage": "GA", "deleted": False, "permissions": list(permissions)}
                      for name, permissions in ROLES.items() if name not in NEW_ROLES}
    state["roles"]["specimenDataStorageRules"]["permissions"].remove("firebaserules.releases.create")
    state["roles"]["specimenDataOwnerBootstrap"] = {"stage": "GA", "deleted": False, "permissions": [
        "firebaseauth.users.get", *ROLES["specimenDataBootstrapRows"]]}
    state["policies"] = {
        f"project/{PROJECT}": [
            binding("roles/owner", ["user:owner@example.test"]),
            binding(CUSTOM + "specimenApiUserLookup", [API]),
            binding(CUSTOM + "specimenDataInventoryProjectRead", [DATA, BUILD, RELEASE]),
            binding(CUSTOM + "specimenDataInventorySqlConnect", [DATA], SQL),
            binding(CUSTOM + "specimenDataRuntimeAbsence", [DATA], EXPIRED["specimenDataRuntimeAbsence"]),
            *(row for role in ("specimenDataSchemaPublish", "specimenDataSourceBackup", "specimenDataStorageRules")
              for row in (binding(CUSTOM + role, [DATA]), binding(CUSTOM + role, [DATA], EXPIRED[role]))),
            binding(CUSTOM + "specimenRuntimeConnector", [API, WORKER]),
            binding(CUSTOM + "specimenRuntimeRelease", [RELEASE])],
        f"bucket/{BUCKET}": [
            binding("roles/storage.legacyBucketOwner", [f"projectEditor:{PROJECT}", f"projectOwner:{PROJECT}"]),
            binding("roles/storage.legacyBucketReader", [f"projectViewer:{PROJECT}"]),
            binding("roles/storage.objectCreator", [API, SAM, WORKER], APP),
            binding("roles/storage.objectViewer", [API, SAM, WORKER], APP),
            binding("roles/storage.objectViewer", [API], SLIDES)],
        "repository/specimen-runtime": [binding("roles/artifactregistry.reader", [RELEASE]),
                                        binding("roles/artifactregistry.writer", [BUILD])],
        **{f"service-account/{EMAIL(name)}": [binding("roles/iam.serviceAccountUser", [RELEASE])]
           for name in ("api-runtime", "worker-runtime", "sam-runtime")},
        **{f"service-account/{name}@{PROJECT}.iam.gserviceaccount.com": [
            binding("roles/iam.workloadIdentityUser", [PLANE + name])] for name in PLANES},
    }
    for member, secret, version in LIVE_PINS:
        rows = state["policies"].setdefault(f"secret/{secret}", [binding(ACCESSOR, [], pin(secret, version))])
        rows[0]["members"].append(member)
    state["sql_roles"]["postgres"] = ["cloudsqlsuperuser"]
    state["secrets"] = ["DATA_BOOTSTRAP_APPROVED_SHA256", ARTIFACT, "DATA_WORKER_ACTOR_UID", "RELEASE_INPUTS_B64"]
    return state


class Run:
    def __init__(self, result, calls):
        self.code, self.out, self.err, self.calls = result.returncode, result.stdout, result.stderr, calls
        self.writes = [call for call in calls if call["write"]]
        # The commands the script printed, as a shell would split them (the secret's pipeline is checked apart).
        self.printed = [named(shlex.split(line[2:])) for line in self.out.splitlines()
                        if line.startswith("+ ") and not line.startswith("+ base64 ")]
        self.ran = [named([call["tool"], *call["argv"]]) for call in self.writes]
        self.sleeps = [int(call["argv"][0]) for call in calls if call["tool"] == "sleep"]
        # Every workflow start and re-run, in order.
        self.starts = [argv for argv in self.ran if argv[:3] in (["gh", "workflow", "run"], ["gh", "run", "rerun"])]
        self.summary = self.out.split("== Summary ==", 1)[-1]

    def lines(self, prefix):
        return [line for line in self.out.splitlines() if line.startswith(prefix)]

    def conditions(self):
        """Each condition file a write received, parsed the way gcloud parses it, by its file name."""
        return {Path(arg.split("=", 1)[1]).name: yaml.safe_load(call["condition_text"])
                for call in self.writes for arg in call["argv"] if arg.startswith("--condition-from-file=")}


def named(argv):
    """The command with a condition file's temporary directory removed."""
    return [f"--condition-from-file={Path(arg.split('=', 1)[1]).name}" if arg.startswith("--condition-from-file=")
            else arg for arg in argv]


class Harness:
    def __init__(self, root, state, shell=SHELLS[0]):
        self.root, self.shell, self.home = root, shell, root / "home"
        for name in ("home", "tmp", "bin"):
            (root / name).mkdir()
        (root / "fake.py").write_text(FAKE)
        for tool in ("gcloud", "gh", "curl"):
            path = root / "bin" / tool
            path.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -S -E '
                            f'{shlex.quote(str(root / "fake.py"))} {tool} "$@"\n')
            path.chmod(0o755)
        # A sleep is only written down, so the script's real waits can be asserted without waiting.
        (root / "bin" / "sleep").write_text(
            '#!/bin/sh\nprintf \'{"tool": "sleep", "argv": ["%s"], "write": false}\\n\' "$1" '
            '>> "$FAKE_ROOT/calls.jsonl"\n')
        (root / "bin" / "sleep").chmod(0o755)
        self.save(state)

    def save(self, state):
        (self.root / "state.json").write_text(json.dumps(state))

    def state(self):
        return json.loads((self.root / "state.json").read_text())

    def artifact(self, content):
        path = self.home / "specimen-release-private" / "hierarchy-bootstrap.artifact.json"
        path.parent.mkdir()
        path.write_bytes(content)
        return path

    def run(self, *args, script=None, cwd=None, detached=False, **overrides):
        """One run of the script. Its own input is an empty pipe, so a tool that inherited it would be seen;
        detached runs it the way an agent shell does: input from /dev/null, output into another process."""
        (self.root / "calls.jsonl").write_text("")
        env = {"PATH": f"{self.root / 'bin'}:/usr/bin:/bin", "HOME": str(self.home),
               "TMPDIR": str(self.root / "tmp"), "FAKE_ROOT": str(self.root), **overrides}
        command = [self.shell, str(script or SCRIPT), *args]
        if detached:
            command = [self.shell, "-o", "pipefail", "-c", '"$@" < /dev/null | cat', "detached", *command]
        result = subprocess.run(command, env=env, cwd=cwd, capture_output=True, text=True, input="", timeout=600,
                                check=False)
        run = Run(result, [json.loads(line) for line in (self.root / "calls.jsonl").read_text().splitlines()])
        assert not [call for call in run.calls if "unsupported" in call], run.err
        for call in run.calls:
            if call["tool"] == "sleep":
                continue
            assert call["write"] == changes(call), call  # the fakes' own classification agrees with the command
            assert call["quiet"] == QUIET, call
            # Only the secret travels through a pipe; every other tool reads from /dev/null and cannot wait on input.
            assert call["stdin"] == ("pipe" if call["argv"][:2] == ["secret", "set"] else "null"), call
        assert list((self.root / "tmp").iterdir()) == []  # the condition files are gone
        return run


def changes(call):
    """Whether a command changes something, judged from its command line alone."""
    if call["tool"] == "gh":
        return tuple(call["argv"][:2]) in GH_WRITES
    return call["tool"] == "gcloud" and bool(MUTATING & {arg for arg in call["argv"] if not arg.startswith("-")})


def project_grant(member, role):
    return ["gcloud", "projects", "add-iam-policy-binding", PROJECT, f"--member={member}", f"--role={CUSTOM}{role}",
            "--condition=None"]


def role_create(name, title, description):
    return ["gcloud", "iam", "roles", "create", name, f"--project={PROJECT}", f"--title={title}",
            f"--description={description}", f"--permissions={','.join(ROLES[name])}", "--stage=GA"]


def provider_update(name):
    return ["gcloud", "iam", "workload-identity-pools", "providers", "update-oidc", name,
            "--workload-identity-pool=github-actions", "--location=global", f"--project={PROJECT}",
            f"--attribute-condition={provider(*PROVIDERS[name], name, EITHER)}"]


# The research harness's create and get, on its three prefixes: the worker only, and not a list or delete role.
RESEARCH_GRANTS = [
    ["gcloud", "storage", "buckets", "add-iam-policy-binding", f"gs://{BUCKET}", f"--member={WORKER}",
     f"--role=roles/storage.{role}", f"--condition-from-file=condition-{number}-specimen_research_objects.yaml"]
    for number, role in ((7, "objectViewer"), (8, "objectCreator"))]
# The SAM 3 checkpoint mount lists the bucket (follow-up change #236): no condition, and no object read in the role.
SAM_LISTS_BUCKET = ["gcloud", "storage", "buckets", "add-iam-policy-binding", f"gs://{BUCKET}", f"--member={SAM}",
                    "--role=roles/storage.legacyBucketReader", "--condition=None"]
# The right to set who may call the API, on the one service; and the wider, project-level grant taken away.
INVOKER_ROLE = f"--role={CUSTOM}specimenRuntimeInvokerPolicy"
SERVICE = "specimen-api"
NARROW = ["gcloud", "run", "services", "add-iam-policy-binding", SERVICE, "--region=us-east4",
          f"--project={PROJECT}", f"--member={RELEASE}", INVOKER_ROLE, "--condition=None"]
UNWIDEN = ["gcloud", "projects", "remove-iam-policy-binding", PROJECT, f"--member={RELEASE}", INVOKER_ROLE,
           "--condition=None"]
MOVES = "runtime release: the right to set who may call the API now moves from the project to the one service"
# Every change the live state needs, in the script's order, with exact arguments.
EXPECTED = [
    *(["gcloud", "projects", "remove-iam-policy-binding", PROJECT, f"--member={DATA}", f"--role={CUSTOM}{role}",
       f"--condition-from-file=condition-{number}-specimen_pr21_{role}.yaml"]
      for number, role in enumerate(EXPIRED, 1)),
    ["gcloud", "iam", "roles", "update", "specimenDataStorageRules", f"--project={PROJECT}",
     f"--permissions={','.join(ROLES['specimenDataStorageRules'])}", "--stage=GA"],
    role_create("specimenDataBootstrapRows", "Specimen data bootstrap rows",
                "Read and write the first organization, collection and membership rows through Data Connect."),
    project_grant(DATA, "specimenDataBootstrapRows"),
    ["gcloud", "secrets", "add-iam-policy-binding", "specimen-worker-actor-uid", f"--project={PROJECT}",
     f"--member={DATA}", f"--role={ACCESSOR}", "--condition-from-file=condition-5-specimen_worker_actor_uid_v1.yaml"],
    role_create("specimenGeoreferenceDatasets", "Specimen immutable georeferencing datasets",
                "Create and verify only the committed georeferencing objects; no list, overwrite or delete."),
    ["gcloud", "storage", "buckets", "add-iam-policy-binding", f"gs://{BUCKET}", f"--member={DATA}",
     f"--role={CUSTOM}specimenGeoreferenceDatasets",
     "--condition-from-file=condition-6-specimen_georeference_datasets.yaml"],
    ["gcloud", "sql", "users", "assign-roles", "specimen-data-release@specimen-digitization.iam",
     "--instance=specimen-digitization-instance", "--type=CLOUD_IAM_SERVICE_ACCOUNT",
     "--database-roles=cloudsqlsuperuser", "--project=specimen-digitization"],
    role_create("specimenRuntimeInvokerPolicy", "Specimen runtime invoker policy",
                "Read and set who may call the API service."),
    role_create("specimenWorkerExecution", "Specimen queued worker execution",
                "Run the existing worker without overrides and read its execution outcome."),
    role_create("specimenWorkerRead", "Specimen worker readiness read",
                "Read only the deployed specimen worker definition for API readiness."),
    role_create("specimenResearchCaptureRead", "Specimen API immutable capture read",
                "Read scoped immutable source captures for API verification; no list, create or delete."),
    project_grant(RELEASE, "specimenRuntimeInvokerPolicy"),
    ["gcloud", "run", "jobs", "add-iam-policy-binding", "specimen-worker", "--region=us-east4",
     f"--project={PROJECT}", f"--member={RELEASE}", f"--role={CUSTOM}specimenWorkerExecution", "--quiet"],
    ["gcloud", "run", "jobs", "add-iam-policy-binding", "specimen-worker", "--region=us-east4",
     f"--project={PROJECT}", f"--member={API}", f"--role={CUSTOM}specimenWorkerRead", "--quiet"],
    *RESEARCH_GRANTS,
    ["gcloud", "storage", "buckets", "add-iam-policy-binding", f"gs://{BUCKET}", f"--member={API}",
     f"--role={CUSTOM}specimenResearchCaptureRead",
     "--condition-from-file=condition-9-specimen_api_research_capture.yaml"],
    SAM_LISTS_BUCKET,
    *(provider_update(name) for name in PROVIDERS),
    ["gh", "variable", "set", "SPECIMEN_API_BASE_URL", "-R", REPOSITORY, "--body", API_URL],
    ["gh", "variable", "set", "SPECIMEN_RECAPTCHA_SITE_KEY", "-R", REPOSITORY, "--body", SITE_KEY],
]
EXPECTED_CONDITIONS = {
    **{f"condition-{number}-specimen_pr21_{role}.yaml": held for number, (role, held) in enumerate(EXPIRED.items(), 1)},
    "condition-5-specimen_worker_actor_uid_v1.yaml": pin("specimen-worker-actor-uid", 1),
    "condition-6-specimen_georeference_datasets.yaml": GEO,
    "condition-7-specimen_research_objects.yaml": RESEARCH, "condition-8-specimen_research_objects.yaml": RESEARCH,
    "condition-9-specimen_api_research_capture.yaml": CAPTURE_READ}


def given(held):
    """A condition as gcloud reads it from a file: an absent description is no key at all."""
    return {key: value for key, value in held.items() if value is not None}


def test_script_is_ascii_executable_and_parses():
    for path in (SCRIPT, Path(__file__)):
        assert path.read_bytes().isascii(), path
    assert os.stat(SCRIPT).st_mode & 0o111 == 0o111
    assert "set -euo pipefail" in SCRIPT.read_text()
    for shell in SHELLS:
        assert subprocess.run([shell, "-n", str(SCRIPT)], capture_output=True, check=False).returncode == 0, shell


def test_georeferencing_grant_is_exact_manifest_and_create_read_only():
    manifest = pytest.importorskip("specimen_digitization.application.georef_datasets").MANIFEST
    assert set(GEO_SHA256) == {entry.sha256 for entry in manifest}
    assert len(GEO_SHA256) == len(manifest) == 10
    assert ROLES["specimenGeoreferenceDatasets"] == ["storage.objects.create", "storage.objects.get"]
    assert "startsWith" not in GEO["expression"] and len(GEO["expression"]) < 2048


def test_api_worker_readiness_grant_is_only_one_job_and_get_permission(fresh):
    harness, run = fresh
    assert ROLES["specimenWorkerRead"] == ["run.jobs.get"]
    assert {grant for grant in grants(run) if grant[2] == CUSTOM + "specimenWorkerRead"} == {
        ("job/specimen-worker", API, CUSTOM + "specimenWorkerRead", None, None)}
    assert harness.state()["roles"]["specimenWorkerRead"]["permissions"] == ["run.jobs.get"]


def test_shellcheck_passes():
    shellcheck = shutil.which("shellcheck")
    if shellcheck is None:
        pytest.skip("shellcheck is not installed")
    result = subprocess.run([shellcheck, str(SCRIPT)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout


def test_usage_error_runs_nothing(tmp_path):
    harness = Harness(tmp_path, live_state())
    for args in (("--apply",), ("--dry-run", "--dry-run")):
        run = harness.run(*args)
        assert (run.code, run.calls, run.out) == (2, [], "") and "Usage:" in run.err


@pytest.mark.parametrize("shell", SHELLS)
def test_dry_run_prints_every_change_and_makes_none(tmp_path, shell):
    harness = Harness(tmp_path, before := live_state(), shell)
    content = b'{"request": {"variables": {"uid": "PRIVATE-MARKER-0123456789"}}}\n' * 4
    path = harness.artifact(content)
    run = harness.run("--dry-run")
    assert run.code == 0, run.err
    assert run.writes == [] and harness.state() == before
    assert run.printed == EXPECTED
    for words in ("add-iam-policy-binding", "remove-iam-policy-binding", "roles create", "roles update",
                  "users assign-roles", "providers update-oidc", "variable set", "secret set"):
        assert [line for line in run.out.splitlines() if line.startswith("+ ") and f" {words} " in line], words
    assert (f"+ base64 < {path} | tr -d '\\n' | gh secret set {ARTIFACT} --env data-production -R {REPOSITORY}"
            in run.out.splitlines())
    assert f"from the artifact file ({len(content)} bytes)" in run.out
    shown = run.out + run.err + json.dumps(run.calls)
    assert "PRIVATE-MARKER" not in shown and base64.b64encode(content).decode()[:40] not in shown
    assert "Dry run: nothing was changed. 28 step(s) would change:" in run.out
    assert run.printed.count(SAM_LISTS_BUCKET) == 1
    assert "--all" not in run.out
    for name in RETIRE:
        assert name in run.out.split("== Retire later", 1)[1], name
    assert "Merge the pull request" in run.out.split("== Summary ==", 1)[1]
    headings = [line for line in run.out.splitlines() if line.startswith("== ")]
    assert [line.split(":")[0] for line in headings] == [
        "== Clean-up", "== Data release", "== Cloud SQL", "== Runtime release", "== Manual runs", "== GitHub",
        "== GitHub", "== Retire later", "== Releases", "== Summary =="]
    assert run.sleeps == [] and run.summary.splitlines()[-1] == SAFE
    assert "  Setup: WOULD RUN (28 change(s))" in run.summary
    assert "Setup is complete" not in run.out and "State:" not in run.summary
    assert "the three database roles once (later releases only use the firebaseowner role)" in headings[2]


@pytest.mark.parametrize("shell", SHELLS)
def test_apply_makes_each_change_once_and_a_second_run_makes_none(tmp_path, shell):
    harness = Harness(tmp_path, live_state(), shell)
    run = harness.run()
    assert run.code == 0, run.err
    assert run.ran == EXPECTED and run.printed == EXPECTED
    assert run.conditions() == {name: given(held) for name, held in EXPECTED_CONDITIONS.items()}
    assert provider_update("specimen-data-release")[-1] == f"--attribute-condition={DATA_PROVIDER_AFTER}"
    assert "27 step(s) changed:" in run.out
    assert run.ran.count(SAM_LISTS_BUCKET) == 1

    after = harness.state()
    project = after["policies"][f"project/{PROJECT}"]
    assert not [row for row in project if row["condition"] and row["condition"]["title"].startswith("specimen_pr21_")]
    for role in ("specimenDataSchemaPublish", "specimenDataStorageRules", "specimenDataSourceBackup"):
        assert binding(CUSTOM + role, [DATA]) in project  # the standing grant of the same role stays
    assert binding(CUSTOM + "specimenDataInventorySqlConnect", [DATA], SQL) in project
    assert after["roles"]["specimenDataStorageRules"]["permissions"] == ROLES["specimenDataStorageRules"]
    assert after["policies"]["secret/specimen-worker-actor-uid"] == [
        binding(ACCESSOR, [WORKER, DATA], pin("specimen-worker-actor-uid", 1))]
    assert after["sql_roles"][SQL_USER] == ["cloudsqlsuperuser"]
    # The worker's read of the retired Maps key is neither granted nor removed; its secret is not even looked at.
    assert after["policies"][f"secret/{MAPS_KEY}"] == [binding(ACCESSOR, [WORKER], pin(MAPS_KEY, 1))]
    assert not [call for call in run.calls if MAPS_KEY in call["argv"]]
    bucket = after["policies"][f"bucket/{BUCKET}"]
    assert binding("roles/storage.legacyBucketReader", [f"projectViewer:{PROJECT}", SAM]) in bucket
    assert not [row for row in bucket if SAM in row["members"] and row["condition"] is None
                and row["role"] != "roles/storage.legacyBucketReader"]  # no other unconditioned right for SAM 3
    assert after["variables"] == {"SPECIMEN_API_BASE_URL": API_URL, "SPECIMEN_RECAPTCHA_SITE_KEY": SITE_KEY}
    assert f"secret {ARTIFACT} exists and is left as it is" in run.out
    # No API service yet: the right to open it sits on the project, and the script says the next run narrows it.
    assert "the next run of this script narrows it to that one service" in run.out
    assert not [argv for argv in run.ran if argv[:3] == ["gcloud", "run", "services"]]
    # Main still holds the push-only workflows: the setup is done, no release is started, and that is no failure.
    assert ("The simple release workflows are not on main yet (the pull request is not merged). Setup is complete. "
            "Run this script again after the merge.") in run.out
    assert run.starts == [] and run.sleeps == []
    assert run.summary.split("Stages:\n", 1)[1].splitlines()[:5] == [
        "  Setup: PASS (27 changed, 39 already in place)",
        "  Data release: SKIPPED (the simple workflows are not on main yet)",
        "  Runtime release: SKIPPED (the simple workflows are not on main yet)",
        "  Web app: SKIPPED (the simple workflows are not on main yet)",
        "State: SETUP DONE, RELEASES NOT STARTED"]
    assert f"Live addresses:\n  API: {API_URL}\n  App: https://specimen-digitization.web.app\n" in run.summary
    assert run.summary.splitlines()[-1] == SAFE and "--redeploy-web" not in run.summary

    again = harness.run()
    assert again.code == 0, again.err
    assert again.writes == [] and again.printed == [] and harness.state() == after
    assert "0 step(s) changed:" in again.out and "WARNING" not in again.out
    for name in PROVIDERS:
        assert f"ok: {name} already allows manual runs on main" in again.out


def test_secret_goes_from_the_file_to_gh_through_a_pipe(tmp_path):
    harness = Harness(tmp_path, live_state())
    assert harness.run().code == 0  # everything else is in place, so the secret is the only change left
    content = bytes(range(256)) * 3 + b"PRIVATE-MARKER-0123456789"
    harness.artifact(content)
    encoded = base64.b64encode(content)
    run = harness.run()
    assert run.code == 0, run.err
    assert [call["argv"] for call in run.writes] == [
        ["secret", "set", ARTIFACT, "--env", "data-production", "-R", REPOSITORY]]
    assert run.writes[0]["stdin_sha256"] == hashlib.sha256(encoded).hexdigest()  # one line, no wrapping
    assert run.writes[0]["stdin_length"] == len(encoded)
    shown = run.out + run.err + json.dumps(run.calls)
    assert encoded.decode()[:40] not in shown and "PRIVATE-MARKER" not in shown
    assert "1 step(s) changed:" in run.out


def test_missing_secret_without_the_file_is_reported(tmp_path):
    state = live_state()
    state["secrets"].remove(ARTIFACT)
    harness = Harness(tmp_path, state)
    harness.artifact(b"")  # an empty file is no artifact
    run = harness.run("--dry-run")
    assert run.code == 0 and run.writes == [] and "secret set" not in run.out
    assert f"WARNING: secret {ARTIFACT} is MISSING in environment data-production" in run.out
    assert "the data release will fail at the bootstrap step" in run.out.split("Warnings:", 1)[1]


def test_provider_is_changed_only_when_it_still_has_the_push_only_clause(tmp_path):
    state = live_state()
    state["providers"]["specimen-data-release"] = provider(*PROVIDERS["specimen-data-release"],
                                                            "specimen-data-release", EITHER)
    compact = "assertion.event_name=='push' && assertion.ref=='refs/heads/main'"  # the Hosting provider's spelling
    state["providers"]["specimen-runtime-build"] = compact
    harness = Harness(tmp_path, state)
    run = harness.run()
    assert run.code == 0, run.err
    assert [argv for argv in run.ran if "update-oidc" in argv] == [provider_update("specimen-runtime-release")]
    assert "ok: specimen-data-release already allows manual runs on main" in run.out
    assert "WARNING: specimen-runtime-build has no clause" in run.out
    assert harness.state()["providers"]["specimen-runtime-build"] == compact


def test_only_an_ended_plain_time_window_is_removed(tmp_path):
    state = live_state()
    project = state["policies"][f"project/{PROJECT}"]
    still_open = window("specimenDataSchemaPublish", "2026-09-13T20:25:15Z", "2999-01-01T00:00:00Z")
    other = condition("specimen_pr21_specimenDataStorageRules",
                      EXPIRED["specimenDataStorageRules"]["expression"] + " || resource.name != ''", PR21)
    for row in project:
        if row["condition"] == EXPIRED["specimenDataSchemaPublish"]:
            row["condition"] = still_open
        elif row["condition"] == EXPIRED["specimenDataStorageRules"]:
            row["condition"] = other
    project.remove(binding(CUSTOM + "specimenDataSourceBackup", [DATA], EXPIRED["specimenDataSourceBackup"]))
    state["roles"]["specimenRuntimeConnector"]["deleted"] = True
    harness = Harness(tmp_path, state)
    run = harness.run()
    assert run.code == 0, run.err
    assert [argv for argv in run.ran if "remove-iam-policy-binding" in argv] == [
        ["gcloud", "projects", "remove-iam-policy-binding", PROJECT, f"--member={DATA}",
         f"--role={CUSTOM}specimenDataRuntimeAbsence",
         "--condition-from-file=condition-1-specimen_pr21_specimenDataRuntimeAbsence.yaml"]]
    assert ("WARNING: specimen_pr21_specimenDataSchemaPublish is open until 2999-01-01T00:00:00Z; left in place"
            in run.out)
    assert "WARNING: specimen_pr21_specimenDataStorageRules is not a plain time window; left in place" in run.out
    assert "ok: already removed: specimen_pr21_specimenDataSourceBackup" in run.out
    kept = harness.state()["policies"][f"project/{PROJECT}"]
    assert binding(CUSTOM + "specimenDataSchemaPublish", [DATA], still_open) in kept
    assert binding(CUSTOM + "specimenDataStorageRules", [DATA], other) in kept
    # A deleted role is restored, then set to its exact permissions.
    restored = [argv for argv in run.ran if "specimenRuntimeConnector" in argv]
    assert restored == [
        ["gcloud", "iam", "roles", "undelete", "specimenRuntimeConnector", f"--project={PROJECT}"],
        ["gcloud", "iam", "roles", "update", "specimenRuntimeConnector", f"--project={PROJECT}",
         f"--permissions={','.join(ROLES['specimenRuntimeConnector'])}", "--stage=GA"]]


def test_failed_change_does_not_stop_the_later_steps_and_the_next_run_retries_it(tmp_path):
    harness = Harness(tmp_path, {**live_state(), "fail": ["assign-roles"]})
    run = harness.run()
    assert run.code == 1 and run.ran == EXPECTED  # every step was tried, in order
    assert "FAILED: 1 step(s) did not go through:\n  - make specimen-data-release@specimen-digitization.iam" in run.out
    assert "26 step(s) changed:" in run.out and "Stopped before the end" not in run.err
    assert "the service refused this change" in run.err
    harness.save({**harness.state(), "fail": []})
    again = harness.run()
    assert again.code == 0 and again.ran == [EXPECTED[10]] and "1 step(s) changed:" in again.out
    assert EXPECTED[10][:4] == ["gcloud", "sql", "users", "assign-roles"]


@pytest.mark.parametrize("change, message", [
    ({"account": ""}, "gcloud is not signed in"), ({"gh_signed_in": False}, "gh is not signed in"),
    ({"project_number": "1"}, "expected 716045864126")])
def test_preflight_stops_before_any_change(tmp_path, change, message):
    run = Harness(tmp_path, {**live_state(), **change}).run()
    assert run.code == 1 and run.writes == [] and message in run.err
    assert "== " not in run.out


def grants(run):
    """Every binding an apply added: (resource, member, role, condition title, condition expression)."""
    found, conditions = set(), run.conditions()
    for argv in run.ran:
        if "add-iam-policy-binding" not in argv:
            continue
        flags = dict(arg[2:].split("=", 1) if "=" in arg else (arg[2:], None) for arg in argv if arg.startswith("--"))
        held = conditions[flags["condition-from-file"]] if "condition-from-file" in flags else {}
        at = argv.index("add-iam-policy-binding")
        kind = "repository" if argv[at - 1] == "repositories" else argv[at - 1][:-1]  # projects -> project
        name = argv[at + 1].removeprefix("gs://")
        found.add((f"{kind}/{name}", flags["member"], flags["role"], held.get("title"), held.get("expression")))
    return found


# What the script grants beyond the committed standing table, and the two rows of the table it leaves alone.
SAM_LISTING = (f"bucket/{BUCKET}", SAM, "roles/storage.legacyBucketReader", None, None)
ADDED = {("job/specimen-worker", RELEASE, CUSTOM + "specimenWorkerExecution", None, None),
         (f"bucket/{BUCKET}", API, CUSTOM + "specimenResearchCaptureRead", CAPTURE_READ["title"], CAPTURE_READ["expression"]),
         ("job/specimen-worker", API, CUSTOM + "specimenWorkerRead", None, None),
         (f"bucket/{BUCKET}", DATA, CUSTOM + "specimenGeoreferenceDatasets", GEO["title"], GEO["expression"]),
         (f"project/{PROJECT}", DATA, CUSTOM + "specimenDataBootstrapRows", None, None),
         (f"project/{PROJECT}", RELEASE, CUSTOM + "specimenRuntimeInvokerPolicy", None, None),
         ("secret/specimen-worker-actor-uid", DATA, ACCESSOR, *list(pin("specimen-worker-actor-uid", 1).values())[:2]),
         SAM_LISTING,
         *((f"service-account/{name}@{PROJECT}.iam.gserviceaccount.com", PLANE + name, "roles/iam.workloadIdentityUser",
            None, None) for name in PLANES)}
LEFT_ALONE = {(f"project/{PROJECT}", DATA, CUSTOM + "specimenDataSourceBackup", None, None),
              (f"project/{PROJECT}", BUILD, CUSTOM + "specimenDataInventoryProjectRead", None, None)}
# The worker's and SAM 3's settings belong to their own change (#236) and move with it. For these two accounts the
# script is held to this list of its own and to the shape rules of shape_problems, never to equality with the
# settings; everything else (the release identities, the data release, the API runtime, SAM 3's bucket listing) is
# compared strictly with the committed table.
THEIRS = (WORKER, SAM)
THEIR_GRANTS = {
    (f"project/{PROJECT}", WORKER, CUSTOM + "specimenRuntimeConnector", None, None),
    *((f"bucket/{BUCKET}", member, role, APP["title"], APP["expression"])
      for member in THEIRS for role in ("roles/storage.objectViewer", "roles/storage.objectCreator")),
    *((f"secret/{secret}", member, ACCESSOR, *list(pin(secret, version).values())[:2])
      for member, secret, version in LIVE_PINS if member in THEIRS and secret != MAPS_KEY)}
# The research harness's create and get, for the worker alone. The standing table the next test compares with is the
# retired release process's (scripts/ci/owner_grants.py), which scripts/ci/RETIRED.md keeps unchanged, so this pair
# is held to this file and to the test that writes it out, not to that table.
RESEARCH_ROWS = {(f"bucket/{BUCKET}", WORKER, role, RESEARCH["title"], RESEARCH["expression"])
                 for role in ("roles/storage.objectViewer", "roles/storage.objectCreator")}
# The settings may ask for these; the script must not grant them, each for its own reason.
NOT_GRANTED = {
    MAPS_KEY: "retired by the owner; #236 removes it from the worker's settings",
    "specimen_sam3_checkpoint_listing": "its condition names the checkpoint digest that #236 commits; granted there",
}
# Secret names the script may pin although the settings on disk do not list them. Empty today: all are listed.
OUTSIDE_THE_SETTINGS = ()
PINNED = re.compile(r'resource\.name\.endsWith\("/secrets/([a-z0-9-]+)/versions/([1-9][0-9]*)"\)')
# One more version of runtime_settings.py to hold on, by path: for example the head of a pull request that is about
# to merge, fetched into a directory outside the repository.
OTHER_SETTINGS = os.environ.get("OWNER_SETUP_OTHER_SETTINGS")


def ci_module(name):
    path = ROOT / "scripts" / "ci" / f"{name}.py"
    if not path.exists():
        pytest.skip(f"scripts/ci/{name}.py is retired")
    sys.path.insert(0, str(path.parent))  # its siblings import each other by bare name
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(path.parent))


@pytest.fixture(params=["committed", *(["other"] if OTHER_SETTINGS else [])])
def settings(request):
    """The committed runtime settings; and the version OWNER_SETUP_OTHER_SETTINGS names, when it names one."""
    if request.param == "committed":
        return ci_module("runtime_settings")
    spec = importlib.util.spec_from_file_location("runtime_settings_other", OTHER_SETTINGS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fresh(tmp_path_factory):
    harness = Harness(tmp_path_factory.mktemp("fresh"), fresh_state())
    run = harness.run()
    assert run.code == 0, run.err
    return harness, run


def owned(granted):
    """The grants this change owns outright: all but the worker's and SAM 3's, and SAM 3's bucket listing."""
    return {grant for grant in granted if grant[1] not in THEIRS or grant == SAM_LISTING}


def shape_problems(granted, settings):
    """What is wrong with the script's grants, judged by shape against one version of the runtime settings."""
    problems = []
    reads = {(f"serviceAccount:{role['service_account']}", secret)
             for role in (settings.WORKER, settings.SAM) for secret in role["secret_env"].values()}
    for grant in sorted(granted, key=str):
        resource, member, role, title, expression = grant
        name = resource.removeprefix("secret/")
        if name in NOT_GRANTED or title in NOT_GRANTED:
            problems.append(f"{grant}: must not be granted ({NOT_GRANTED.get(name) or NOT_GRANTED[title]})")
        if role != ACCESSOR:
            continue
        # A secret is never readable in every version: the condition names the secret and one version of it.
        match = PINNED.fullmatch(expression or "")
        if not match or match.group(1) != name or title != f"{name.replace('-', '_')}_v{match.group(2)}":
            problems.append(f"{grant}: a secret read must be pinned to one version of that secret")
        if member not in (API, WORKER, SAM) and grant not in ADDED:
            problems.append(f"{grant}: only the three runtime accounts read secrets")
        if name not in settings.SECRET_VERSIONS and name not in OUTSIDE_THE_SETTINGS:
            problems.append(f"{grant}: the settings do not know this secret")
        if member in THEIRS and (member, name) not in reads:
            problems.append(f"{grant}: this account does not read this secret")
    return problems


def test_fresh_project_gets_every_role_and_pins_every_secret_read(fresh, settings):
    harness, run = fresh
    assert {name: sorted(role["permissions"]) for name, role in harness.state()["roles"].items()} == ROLES
    assert [argv[4] for argv in run.ran if argv[:4] == ["gcloud", "iam", "roles", "create"]] == [
        "specimenDataSchemaPublish", "specimenDataStorageRules", "specimenDataInventoryProjectRead",
        "specimenDataInventorySqlConnect", "specimenDataBootstrapRows", "specimenGeoreferenceDatasets", "specimenRuntimeRelease",
        "specimenRuntimeInvokerPolicy", "specimenWorkerExecution", "specimenWorkerRead", "specimenResearchCaptureRead",
        "specimenRuntimeConnector", "specimenApiUserLookup"]
    assert run.conditions()["condition-1-specimen_source_inventory_only.yaml"] == SQL  # with its live description
    granted = grants(run)
    # Strict, against the settings: the API runtime reads exactly its secrets at their pinned versions, and the
    # data release its one.
    assert f"serviceAccount:{settings.API['service_account']}" == API
    api = {(f"secret/{secret}", API, ACCESSOR, *list(pin(secret, settings.SECRET_VERSIONS[secret]).values())[:2])
           for secret in settings.API["secret_env"].values()}
    assert {grant for grant in owned(granted) if grant[0].startswith("secret/")} == api | {
        grant for grant in ADDED if grant[0].startswith("secret/")}
    # Strict, against this file: what the script grants the worker and SAM 3 today, so a lost line is noticed.
    assert granted - owned(granted) == THEIR_GRANTS | RESEARCH_ROWS
    # Shape, against the settings: for those two accounts the settings may move without this script.
    assert shape_problems(granted, settings) == []
    assert "the listing grant limited to the checkpoint prefix is not made here" in run.out


def test_shape_rules_name_what_is_wrong():
    settings = ci_module("runtime_settings")
    wrong = {
        ("secret/specimen-worker-logfire", WORKER, ACCESSOR, None, None): "must be pinned",
        (f"secret/{MAPS_KEY}", WORKER, ACCESSOR, *list(pin(MAPS_KEY, 1).values())[:2]): "must not be granted",
        (f"bucket/{BUCKET}", SAM, "roles/storage.objectViewer", "specimen_sam3_checkpoint_listing", "x"):
            "must not be granted",
        ("secret/specimen-source-registry", WORKER, ACCESSOR, *list(pin("specimen-source-registry", 1).values())[:2]):
            "does not read this secret",
        ("secret/some-new-secret", API, ACCESSOR, *list(pin("some-new-secret", 1).values())[:2]):
            "do not know this secret",
        ("secret/specimen-worker-logfire", DATA, ACCESSOR, *list(pin("specimen-worker-logfire", 1).values())[:2]):
            "only the three runtime accounts",
        ("secret/specimen-worker-logfire", SAM, ACCESSOR, "specimen_worker_logfire_v1",
         'resource.name.endsWith("/secrets/huggingface-runtime-token/versions/2")'): "must be pinned",
    }
    for grant, words in wrong.items():
        assert [problem for problem in shape_problems({grant}, settings) if words in problem], grant
    assert shape_problems(THEIR_GRANTS | RESEARCH_ROWS | ADDED, settings) == []


def test_fresh_project_grants_match_the_standing_table_for_what_this_change_owns(fresh, settings):
    table = ci_module("owner_grants")
    standing = {(f"{grant.resource[0]}/{grant.resource[1]}", grant.member, grant.role,
                 *(reversed(grant.condition) if grant.condition else (None, None)))
                for grant in (*table.STANDING, *table.runtime_grants(settings)[0])}
    theirs = {grant for grant in standing if grant[1] in THEIRS}
    granted = grants(fresh[1])
    assert LEFT_ALONE <= standing
    # Strict: the release identities, the data release and the API runtime, row for row.
    assert owned(granted) == (standing - theirs - LEFT_ALONE) | ADDED
    # Not strict: the table's rows for the worker and SAM 3 follow their own change. The script stays inside them
    # (apart from its pinned secret reads, which shape_problems judges), and may leave rows out: on main the
    # retired Maps key, on #236 the checkpoint listing.
    assert {grant for grant in granted - owned(granted) if grant[2] != ACCESSOR} - RESEARCH_ROWS <= theirs
    for name, (_, _, permissions) in table.ROLES.items():
        added = ["run.jobs.getIamPolicy"] if name == "specimenRuntimeRelease" else []
        assert sorted([*permissions, *added]) == ROLES[name]


def test_the_worker_alone_gets_create_and_get_on_the_three_research_prefixes_and_no_wider_grant(fresh):
    """The research harness creates and gets objects under research-capture/, research-journal/ and research-media/,
    and never lists or deletes. The setup grants the worker exactly objectCreator and objectViewer there; the
    application condition, which the API and SAM 3 share, is the one it always was."""
    harness, run = fresh
    granted, viewer, creator = grants(run), "roles/storage.objectViewer", "roles/storage.objectCreator"
    bucket_rows = {grant for grant in granted if grant[0] == f"bucket/{BUCKET}"}
    research = {grant for grant in bucket_rows if grant[3] == RESEARCH["title"]}
    assert research == {(f"bucket/{BUCKET}", WORKER, role, RESEARCH["title"], RESEARCH["expression"])
                        for role in (viewer, creator)}
    # The API's only research access is get on captures. No journal/media, list or create.
    capture = (f"bucket/{BUCKET}", API, CUSTOM + "specimenResearchCaptureRead",
               CAPTURE_READ["title"], CAPTURE_READ["expression"])
    assert {grant for grant in granted - research if "research-" in (grant[4] or "")} == {capture}
    assert ROLES["specimenResearchCaptureRead"] == ["storage.objects.get"]
    # Besides SAM 3's mount listing, the bucket grants are object get and create alone: no list, delete or admin role.
    assert {grant[2] for grant in bucket_rows} - {"roles/storage.legacyBucketReader"} == {
        viewer, creator, CUSTOM + "specimenGeoreferenceDatasets", CUSTOM + "specimenResearchCaptureRead"}
    assert {grant for grant in bucket_rows if grant[2] == CUSTOM + "specimenGeoreferenceDatasets"} == {
        (f"bucket/{BUCKET}", DATA, CUSTOM + "specimenGeoreferenceDatasets", GEO["title"], GEO["expression"])}
    assert ROLES["specimenGeoreferenceDatasets"] == ["storage.objects.create", "storage.objects.get"]
    on_bucket = harness.state()["policies"][f"bucket/{BUCKET}"]
    held = [row for row in on_bucket if row["condition"] and "research-" in row["condition"]["expression"]]
    assert sorted(held, key=lambda row: row["role"]) == [
        binding(CUSTOM + "specimenResearchCaptureRead", [API], CAPTURE_READ),
        binding(creator, [WORKER], RESEARCH), binding(viewer, [WORKER], RESEARCH)]
    for role in (creator, viewer):  # the application grant is neither widened nor moved
        [row] = [row for row in on_bucket if row["role"] == role and row["condition"] == APP]
        assert sorted(row["members"]) == sorted([API, SAM, WORKER])
    again = harness.run()
    assert again.code == 0 and again.writes == [], "the bindings are in place: a second run changes nothing"


# The release stages. A run is a list of states; each reading of it by the script shows the next one.
DATA_JOB = "Release the data plane for the merged commit"
RELEASE_STEP = "Release the database, Data Connect and Storage rules"
RERUN = ["gh", "run", "rerun", "400", "-R", REPOSITORY]
LOG = "gh run view {} --log-failed -R anurag-duddu/specimen-digitization-app".format


def step(number, name, conclusion="success"):
    """A finished step; with no conclusion, one that is still running."""
    return {"number": number, "name": name, "status": "completed" if conclusion else "in_progress",
            "conclusion": conclusion or ""}


def job(name, steps, conclusion="success"):
    return {"name": name, "steps": steps, "status": "completed" if conclusion else "in_progress",
            "conclusion": conclusion or ""}


def reading(jobs, conclusion=None, attempt=1, status=None):
    return {"attempt": attempt, "status": status or ("completed" if conclusion else "in_progress"),
            "conclusion": conclusion or "", "jobs": jobs}


def data_run(conclusion="success"):
    early = [step(1, "Set up job"), step(2, "Check out the merged source"), step(3, "Install pinned uv")]
    late = [step(4, RELEASE_STEP, conclusion), step(5, "Keep the report", "skipped"),
            step(9, "Post Check out the merged source"), step(10, "Complete job")]
    return [reading([], status="queued"), reading([job(DATA_JOB, [*early, step(4, RELEASE_STEP, None)], None)]),
            {"unreadable": True}, reading([job(DATA_JOB, [*early, *late], conclusion)], conclusion)]


def runtime_run():
    wait = job("Wait for this commit's data release", [
        step(1, "Set up job"), step(2, "Wait until the data release of this commit has succeeded"),
        step(3, "Complete job")])
    build = [step(1, "Set up job"), step(2, "Push the image and report its digest")]
    deploy = [step(1, "Deploy the API to Cloud Run"), step(2, "Smoke the public API")]
    done = reading([wait, job("Build and push the API image", build), job("Deploy the API and smoke it", deploy)],
                   "success")
    return [reading([wait, job("Build and push the API image", build[:1], None)]), {**done, "deploys": "specimen-api"}]


def web_build(conclusion="success", attempt=1):
    """One attempt of the build of main: its states while it runs, then its end."""
    tests = job("Python tests", [step(1, "Set up job"), step(2, "Run Python tests")])
    build = job("Flutter checks and web build", [step(1, "Build Flutter web release")])
    deploy = job("Deploy Firebase Hosting", [step(1, "Deploy to Firebase Hosting", conclusion)], conclusion)
    return [reading([tests], attempt=attempt), reading([tests, build, deploy], conclusion, attempt)]


def merged(state, data=(), runtime=(), web=None, rebuilds=(), appear_after=0):
    """The project after the merge: both workflows can be started by hand, and each start plays its next run."""
    state = copy.deepcopy(state)
    state["workflows"] = {"data-release.yml": NEW_WORKFLOW, "runtime-release.yml": NEW_WORKFLOW}
    state["dispatches"] = {"data-release.yml": list(data), "runtime-release.yml": list(runtime)}
    state["appear_after"] = appear_after
    if web is not None:
        state["runs"].append({"id": 400, "workflow": "ci-cd.yml", "event": "push", "at": 0, "frames": web, "hidden": 0})
        state["reruns"] = {"400": list(rebuilds)}
    state["http"] = {VERSION_URL: json.dumps({"mode": "production", "source_sha": COMMIT}),
                     DEPLOYMENT_URL: json.dumps({"schemaVersion": 1, "commitSha": COMMIT, "runAttempt": "2"}, indent=2),
                     PROGRAM_URL: PROGRAM(API_URL)}
    return state


def stages(run):
    """The four stage lines of the summary."""
    return run.summary.split("Stages:\n", 1)[1].splitlines()[:4]


@pytest.fixture(scope="module")
def settled(tmp_path_factory):
    """The live project after one apply: every setup step is in place and nothing is left to change."""
    harness = Harness(tmp_path_factory.mktemp("settled"), live_state())
    assert harness.run().code == 0
    return harness.state()


DATA_LINES = ["data release: done - Check out the merged source", "data release: done - Install pinned uv",
              f"data release: done - {RELEASE_STEP}"]
RUNTIME_LINES = [
    "runtime release: done - Wait for this commit's data release: "
    "Wait until the data release of this commit has succeeded",
    "runtime release: done - Build and push the API image: Push the image and report its digest",
    "runtime release: done - Deploy the API and smoke it: Deploy the API to Cloud Run",
    "runtime release: done - Deploy the API and smoke it: Smoke the public API"]
WEB_JOBS = ["web app: done - Python tests", "web app: done - Flutter checks and web build",
            "web app: done - Deploy Firebase Hosting"]


def test_releases_start_in_order_and_each_finished_step_is_printed_once(tmp_path, settled):
    state = merged(settled, data=[data_run()], runtime=[runtime_run()], appear_after=2)
    state["runs"].append({"id": 300, "workflow": "data-release.yml", "event": "workflow_dispatch", "at": 0,
                          "frames": data_run("failure")[-1:], "hidden": 0})  # an older run started by hand
    run = Harness(tmp_path, state).run()
    assert run.code == 0, run.err
    assert run.starts == [START_DATA, START_RUNTIME]
    # One line per finished step, housekeeping and skipped steps left out, each exactly once.
    assert run.lines("data release: ") == [f"data release: started {RUNS}501", *DATA_LINES,
                                           f"data release: PASS {RUNS}501"]
    assert run.lines("runtime release: ") == [
        f"runtime release: started {RUNS}502", *RUNTIME_LINES, f"runtime release: PASS {RUNS}502",
        f"runtime release: the API now serves commit {COMMIT}", MOVES]
    # The release created the service, so the right moves to it now: first the narrow grant, then the wide one goes.
    assert run.ran == [START_DATA, START_RUNTIME, NARROW, UNWIDEN]
    assert "Bad Gateway" not in run.err  # one failed reading of a run is retried without a word
    assert run.lines("web app: ") == ["web app: variables already set; no rebuild needed",
                                      "web app: the site points at the API"]
    # Each new run showed up on the third look (5 s apart); a run is read every 15 s, also after a failed read.
    assert run.sleeps == [5, 5, 5, 15, 15, 15, 5, 5, 5, 15]
    assert stages(run)[1:] == [f"  Data release: PASS {RUNS}501", f"  Runtime release: PASS {RUNS}502",
                               "  Web app: SKIPPED (variables already set; no rebuild needed; "
                               "the site points at the API)"]
    assert stages(run)[0].startswith("  Setup: PASS (2 changed, ")
    assert "None: the setup and the releases are done." in run.summary and run.summary.splitlines()[-1] == SAFE
    assert "To read the log" not in run.summary and "WARNING" not in run.out


def test_failed_data_release_stops_before_the_runtime_release(tmp_path, settled):
    run = Harness(tmp_path, merged(settled, data=[data_run("failure")], runtime=[runtime_run()])).run()
    assert run.code == 1 and "Stopped before the end" not in run.err
    assert run.starts == [START_DATA]  # no second try: no access changed in this run
    assert run.lines("data release: ") == [
        f"data release: started {RUNS}501", *DATA_LINES[:2], f"data release: FAILED - {RELEASE_STEP}",
        f"data release: FAIL {RUNS}501",
        f"data release: failed at: {DATA_JOB} / {RELEASE_STEP}", f"data release: to read the log: {LOG(501)}"]
    assert stages(run)[1:] == [f"  Data release: FAIL {RUNS}501",
                               "  Runtime release: SKIPPED (the data release did not pass)",
                               "  Web app: SKIPPED (the data release did not pass)"]
    assert f"To read the log of what failed:\n  {LOG(501)}\n" in run.summary
    assert run.summary.splitlines()[-1] == SAFE


def test_first_morning_waits_for_new_access_retries_once_and_rebuilds_the_site(tmp_path):
    # The whole first run after the merge: 19 setup changes, a data release that fails while the new access
    # settles, and a build of main that is still running (and then fails) when the variables change.
    first = web_build("failure")
    lagging = [first[-1], *web_build(attempt=2)]  # right after the re-run GitHub still shows the old attempt
    state = merged(live_state(), data=[data_run("failure"), data_run()], runtime=[runtime_run()],
                   web=first, rebuilds=[lagging])
    run = Harness(tmp_path, state).run()
    assert run.code == 0, run.err
    assert run.starts == [START_DATA, START_DATA, START_RUNTIME, RERUN]
    assert "Waiting 120 seconds for the new access to take effect" in run.out.splitlines()
    assert (f"data release: the first try failed ({RUNS}501). The new access may still be settling: "
            "waiting 180 seconds, then trying once more") in run.out.splitlines()
    assert run.sleeps.count(120) == 1 and run.sleeps.count(180) == 1 and set(run.sleeps) == {120, 180, 5, 15}
    assert run.sleeps[0] == 120 and run.sleeps.index(120) < run.sleeps.index(180)
    assert run.lines("data release: ") == [
        f"data release: started {RUNS}501", *DATA_LINES[:2], f"data release: FAILED - {RELEASE_STEP}",
        run.lines("data release: the first try")[0], f"data release: started {RUNS}502", *DATA_LINES,
        f"data release: PASS {RUNS}502"]
    assert run.lines("web app: ") == [
        "web app: the newest build of main is still running; following it to its end first", *WEB_JOBS[:2],
        "web app: FAILED - Deploy Firebase Hosting",  # the old attempt's end does not decide the stage
        "web app: running the build of main again so that it reads the repository variables", *WEB_JOBS,
        f"web app: PASS {RUNS}400", f"web app: the site now serves commit {COMMIT}",
        "web app: the site now points at the API"]
    assert run.ran[-3:] == [NARROW, UNWIDEN, RERUN] and run.ran.index(START_RUNTIME) == len(run.ran) - 4
    assert stages(run) == ["  Setup: PASS (29 changed, 39 already in place)", f"  Data release: PASS {RUNS}502",
                           f"  Runtime release: PASS {RUNS}503",
                           f"  Web app: PASS {RUNS}400 (the site points at the API)"]
    assert "To read the log" not in run.summary and "--redeploy-web" not in run.summary


def test_only_one_retry_and_the_waits_follow_the_two_overrides(tmp_path):
    state = merged(live_state(), data=[data_run("failure"), data_run("failure")], runtime=[runtime_run()])
    harness = Harness(tmp_path, state)
    run = harness.run(OWNER_SETUP_SETTLE_SECONDS="8", OWNER_SETUP_POLL_SECONDS="6")
    assert run.code == 1 and run.starts == [START_DATA, START_DATA]
    assert set(run.sleeps) == {8, 12, 2, 6} and run.sleeps.count(8) == 1 and run.sleeps.count(12) == 1
    assert stages(run)[1:] == [f"  Data release: FAIL {RUNS}502",
                               "  Runtime release: SKIPPED (the data release did not pass)",
                               "  Web app: SKIPPED (the data release did not pass)"]
    assert f"To read the log of what failed:\n  {LOG(502)}\n" in run.summary
    # The variables were set in this run and the site was not rebuilt; a later run would find them already set.
    assert "add --redeploy-web to that next run" in run.summary
    bad = harness.run(OWNER_SETUP_POLL_SECONDS="soon")
    assert (bad.code, bad.calls, bad.out) == (1, [], "") and "whole numbers of seconds" in bad.err


def test_failed_setup_step_starts_no_release(tmp_path):
    state = {**merged(live_state(), data=[data_run()], runtime=[runtime_run()]), "fail": ["assign-roles"]}
    run = Harness(tmp_path, state).run()
    assert run.code == 1 and run.starts == [] and run.sleeps == []
    assert "A setup step failed, so no release is started." in run.out
    assert stages(run) == ["  Setup: FAIL (1 step(s) did not go through)",
                           *["  {}: SKIPPED (a setup step failed)".format(name)
                             for name in ("Data release", "Runtime release", "Web app")]]
    assert not [call for call in run.calls if call["tool"] == "gh" and call["argv"][0] in ("workflow", "run")]


def test_setup_only_never_touches_the_workflows(tmp_path, settled):
    harness = Harness(tmp_path, merged(settled, data=[data_run()], runtime=[runtime_run()]))
    run = harness.run("--setup-only")
    assert run.code == 0, run.err
    assert not [call for call in run.calls if call["tool"] == "gh" and call["argv"][0] in ("workflow", "run")]
    assert stages(run)[1:] == ["  {}: SKIPPED (--setup-only)".format(name)
                               for name in ("Data release", "Runtime release", "Web app")]
    assert "without --setup-only" in run.summary
    clash = harness.run("--setup-only", "--redeploy-web")
    assert (clash.code, clash.calls) == (2, []) and "Usage:" in clash.err


def test_dry_run_prints_the_starts_and_starts_nothing(tmp_path):
    state = merged(live_state(), data=[data_run()], runtime=[runtime_run()], web=web_build()[-1:],
                   rebuilds=[web_build(attempt=2)])
    harness = Harness(tmp_path, state)
    run = harness.run("--dry-run")
    assert run.code == 0, run.err
    assert run.writes == [] and run.sleeps == [] and harness.state() == state
    assert run.printed == [*EXPECTED, START_DATA, START_RUNTIME, RERUN]
    assert "  Would wait 120 seconds for the new access to take effect" in run.out.splitlines()
    assert stages(run) == ["  Setup: WOULD RUN (27 change(s))", "  Data release: WOULD RUN",
                           "  Runtime release: WOULD RUN", f"  Web app: WOULD RUN {RUNS}400"]
    # A build would run, so the site is not read now: the check would follow that build.
    assert "web app: after that build the live site would be checked for the API address" in run.out.splitlines()
    assert not [call for call in run.calls if call["tool"] == "curl"]
    assert run.summary.splitlines()[-1] == SAFE


def test_redeploy_web_rebuilds_set_variables_and_a_failed_build_is_reported(tmp_path, settled):
    state = merged(settled, data=[data_run()], runtime=[runtime_run()], web=web_build()[-1:],
                   rebuilds=[web_build("failure", 2)])
    del state["http"][VERSION_URL]  # the API does not answer the one check after its release
    run = Harness(tmp_path, state).run("--redeploy-web")
    assert run.code == 1 and run.starts == [START_DATA, START_RUNTIME, RERUN]
    # An unanswered check of the live address is a warning, never a failed stage.
    assert f"  WARNING: runtime release: could not read {VERSION_URL} to confirm the commit; the run itself passed" \
        in run.out.splitlines()
    assert run.lines("web app: ") == [
        "web app: running the build of main again so that it reads the repository variables", *WEB_JOBS[:2],
        "web app: FAILED - Deploy Firebase Hosting", f"web app: FAIL {RUNS}400",
        "web app: failed at: Deploy Firebase Hosting / Deploy to Firebase Hosting",
        f"web app: to read the log: {LOG(400)}"]
    assert stages(run)[1:] == [f"  Data release: PASS {RUNS}501", f"  Runtime release: PASS {RUNS}502",
                               f"  Web app: FAIL {RUNS}400"]
    assert f"To read the log of what failed:\n  {LOG(400)}\n" in run.summary


def test_run_that_never_ends_is_given_up_after_the_cap(tmp_path, settled):
    stuck = [reading([job(DATA_JOB, [step(1, "Set up job")], None)])]
    run = Harness(tmp_path, merged(settled, data=[stuck], runtime=[runtime_run()])).run()
    assert run.code == 1 and run.starts == [START_DATA]
    assert len([call for call in run.calls if call["argv"][:2] == ["run", "view"]]) == 180
    assert run.sleeps == [5, *[15] * 179]  # 180 readings 15 s apart: 45 minutes
    assert f"data release: FAIL {RUNS}501 (not finished after 45 minutes of watching)" in run.out.splitlines()
    assert f"data release: to read the log: {LOG(501)}" in run.out.splitlines()


def test_summary_is_printed_when_a_read_fails_midway(tmp_path):
    state = live_state()
    del state["sql_roles"][SQL_USER]
    run = Harness(tmp_path, state).run()
    assert run.code == 1 and "could not read the database user" in run.err and "Stopped before the end" in run.err
    assert stages(run) == ["  Setup: FAIL (stopped early; the error is above)", "  Data release: SKIPPED",
                           "  Runtime release: SKIPPED", "  Web app: SKIPPED"]
    assert "Fix the errors shown above and run this script again" in run.summary
    assert run.starts == [] and run.summary.splitlines()[-1] == SAFE


def test_runs_with_no_terminal_from_a_lone_copy_outside_the_repository(tmp_path):
    # The coordinator may run a copy fetched from main in an agent shell: input from /dev/null, output into a pipe,
    # a working directory that is not the repository, and only this one file.
    harness = Harness(tmp_path, live_state())
    lone = tmp_path / "elsewhere" / "owner_setup.sh"
    lone.parent.mkdir()
    shutil.copy(SCRIPT, lone)
    usual = harness.run("--dry-run")
    run = harness.run("--dry-run", script=lone, cwd=lone.parent, detached=True)
    assert run.code == 0, run.err
    assert run.writes == [] and run.printed == EXPECTED and run.sleeps == []
    assert "Stages:" in run.summary and run.summary.splitlines()[-1] == SAFE
    assert "\x1b" not in run.out + run.err  # no colour, no cursor movement
    # The same output, word for word, apart from the temporary directory's random name.
    steady = re.compile(r"owner-setup\.\w+")
    assert steady.sub("owner-setup", run.out) == steady.sub("owner-setup", usual.out)
    text = SCRIPT.read_text()
    # Nothing relative to its own location or to a checkout, and nothing about a terminal's size.
    assert not re.findall(r"\$0\b|BASH_SOURCE|\bdirname\b|\bgit\b|\btput\b|\bstty\b|COLUMNS", text)
    # Every read in the script takes its lines from a file or a variable, never from the caller.
    reads = [line.strip() for line in text.splitlines() if re.search(r"(?:^|;|IFS=)\s*read\b", line)]
    assert reads == ["while IFS= read -r line; do"] * 3
    assert len(re.findall(r'^ *done <<?<? "\$', text, re.MULTILINE)) == 3


def program_reads(run):
    """The addresses under which the script fetched the site's program."""
    return [call["argv"][5] for call in run.calls if call["tool"] == "curl" and call["argv"][2] == "60"]


@pytest.mark.parametrize("answer, line, stage", [
    (PROGRAM(""), NOT_PICKED_UP, "WARN {} (the site does not point at the API yet)"),
    (None, COULD_NOT_CHECK, "PASS {} (the site could not be checked)"),
], ids=["no API address in the site", "no answer"])
def test_site_is_read_after_the_rebuild_and_a_site_without_the_api_is_a_warning(tmp_path, settled, answer, line, stage):
    # A passed re-run is not taken as proof that the build read the new variables: the live site is read.
    state = merged(settled, data=[data_run()], runtime=[runtime_run()], web=web_build()[-1:],
                   rebuilds=[web_build(attempt=2)])
    state["http"][PROGRAM_URL] = answer
    run = Harness(tmp_path, state).run("--redeploy-web")
    assert run.code == 0, run.err  # neither outcome is a failure
    assert run.starts == [START_DATA, START_RUNTIME, RERUN]
    assert run.out.splitlines().count(line) == 1
    assert run.lines("web app: ")[-2:] == [f"web app: PASS {RUNS}400", f"web app: the site now serves commit {COMMIT}"]
    assert stages(run)[3] == "  Web app: " + stage.format(RUNS + "400")
    assert line.replace("  WARNING: ", "  - ") in run.summary.split("Warnings:\n", 1)[1].splitlines()
    assert "To read the log" not in run.summary and "--redeploy-web" not in run.summary
    # One read, under an address no cache has seen, and the program itself is never shown.
    assert len(program_reads(run)) == 1 and re.fullmatch(re.escape(PROGRAM_URL) + r"\?check=\d+", program_reads(run)[0])
    assert "dartProgram" not in run.out + run.err
    if answer is not None:
        assert "the next merge to main builds the site with the API address" in run.summary


def test_set_variables_and_a_site_without_the_api_show_as_a_warning_and_nothing_is_rebuilt(tmp_path, settled):
    state = merged(settled, data=[data_run()], runtime=[runtime_run()])
    state["http"][PROGRAM_URL] = PROGRAM("")
    run = Harness(tmp_path, state).run()
    assert run.code == 0, run.err
    assert run.starts == [START_DATA, START_RUNTIME]
    assert run.lines("web app: ") == ["web app: variables already set; no rebuild needed"]
    assert run.out.splitlines().count(NOT_PICKED_UP) == 1
    assert stages(run)[3] == "  Web app: WARN (variables already set, but the site does not point at the API yet)"
    assert ("  - web: variables not picked up; the next merge to main will redeploy"
            in run.summary.split("Warnings:\n", 1)[1].splitlines())
    assert len(program_reads(run)) == 1 and run.summary.splitlines()[-1] == SAFE


@pytest.mark.parametrize("answer", [None, {"hex": "1f8b0800000000000003"}, "<!doctype html><title>Specimen</title>"],
                         ids=["no answer", "a compressed answer", "a page instead of the program"])
def test_dry_run_reads_the_site_when_nothing_would_be_rebuilt_and_says_when_it_cannot(tmp_path, settled, answer):
    state = merged(settled, data=[data_run()], runtime=[runtime_run()])
    state["http"][PROGRAM_URL] = answer
    harness = Harness(tmp_path, state)
    run = harness.run("--dry-run")
    assert run.code == 0, run.err
    assert run.writes == [] and run.sleeps == [] and harness.state() == state
    assert run.out.splitlines().count(COULD_NOT_CHECK) == 1 and NOT_PICKED_UP not in run.out
    assert stages(run)[3] == ("  Web app: SKIPPED (variables already set; no rebuild needed; "
                              "the site could not be checked)")
    assert len(program_reads(run)) == 1


def invoker_scope(state):
    """Where the release identity holds the invoker-policy role: on the project, on the API service."""
    role = CUSTOM + "specimenRuntimeInvokerPolicy"
    return [binding(role, [RELEASE]) in state["policies"].get(key, [])
            for key in (f"project/{PROJECT}", "service/specimen-api")]


def test_invoker_policy_right_moves_to_the_api_service_once_it_exists(tmp_path, settled):
    # After the first release: the service exists and the right still sits on the project (state of a second run).
    assert invoker_scope(settled) == [True, False]
    state = {**settled, "services": ["specimen-api"],
             "policies": {**settled["policies"], "service/specimen-api": [binding("roles/run.invoker", ["allUsers"])]}}
    harness = Harness(tmp_path, state)
    preview = harness.run("--dry-run")
    assert preview.code == 0 and preview.writes == [] and preview.printed == [NARROW, UNWIDEN]
    run = harness.run()
    assert run.code == 0, run.err
    assert run.ran == [NARROW, UNWIDEN]  # the narrow grant first, then the wide one goes; nothing else changes
    after = harness.state()
    assert invoker_scope(after) == [False, True]
    assert binding("roles/run.invoker", ["allUsers"]) in after["policies"]["service/specimen-api"]
    assert binding(CUSTOM + "specimenRuntimeRelease", [RELEASE]) in after["policies"][f"project/{PROJECT}"]
    assert "the next run of this script narrows" not in run.out
    again = harness.run()
    assert again.code == 0 and again.writes == [] and harness.state() == after
    assert "ok: not granted (nothing to remove): specimen-runtime-release: specimenRuntimeInvokerPolicy" in again.out


def test_failed_narrowing_after_the_release_is_a_warning_and_keeps_the_wider_grant(tmp_path, settled):
    state = {**merged(settled, data=[data_run()], runtime=[runtime_run()]), "fail": ["specimen-api"]}
    harness = Harness(tmp_path, state)
    run = harness.run()
    assert run.code == 0, run.err  # tidying up after a passed release never fails the run
    # The wide grant is not removed while the narrow one is missing.
    assert run.ran == [START_DATA, START_RUNTIME, NARROW]
    assert invoker_scope(harness.state()) == [True, False]
    warning = ("grant specimen-runtime-release: specimenRuntimeInvokerPolicy on service specimen-api: this did not "
               "go through (the error is above); the next run of this script tries again")
    assert f"  WARNING: {warning}" in run.out.splitlines()
    assert f"  - {warning}" in run.summary.split("Warnings:\n", 1)[1].splitlines()
    assert stages(run)[:3] == [stages(run)[0], f"  Data release: PASS {RUNS}501", f"  Runtime release: PASS {RUNS}502"]
    assert stages(run)[0].startswith("  Setup: PASS (0 changed, ") and "FAILED" not in run.out


def test_setup_stops_when_it_cannot_tell_whether_the_api_service_exists(tmp_path):
    run = Harness(tmp_path, {**live_state(), "unreadable_services": True}).run()
    assert run.code == 1 and "could not tell whether the service specimen-api exists" in run.err
    assert not [argv for argv in run.ran if "specimenRuntimeInvokerPolicy" in " ".join(argv) and "binding" in argv[2]]
    assert stages(run)[0] == "  Setup: FAIL (stopped early; the error is above)"


def test_setup_only_before_the_merge_applies_the_setup_and_touches_no_workflow(tmp_path):
    # The coordinator's plan: --setup-only from this change's head while main still holds the old, push-only
    # workflows, so that the merge commit's own runs are the first releases.
    harness = Harness(tmp_path, live_state())
    assert "workflow_dispatch" not in "".join(harness.state()["workflows"].values())
    run = harness.run("--setup-only")
    assert run.code == 0, run.err
    assert run.ran == EXPECTED and run.printed == EXPECTED
    assert not [call for call in run.calls if call["tool"] == "gh" and call["argv"][0] in ("workflow", "run")]
    assert run.sleeps == [] and not [call for call in run.calls if call["tool"] == "curl"]
    assert run.summary.split("Stages:\n", 1)[1].splitlines()[:5] == [
        "  Setup: PASS (27 changed, 39 already in place)", "  Data release: SKIPPED (--setup-only)",
        "  Runtime release: SKIPPED (--setup-only)", "  Web app: SKIPPED (--setup-only)",
        "State: SETUP DONE, RELEASES NOT STARTED (--setup-only)"]
    assert run.summary.split("Next steps:\n", 1)[1].splitlines() == [
        "  The releases were not started (--setup-only): the next merge to main starts them and builds the site with "
        "these settings.",
        "  To start them without a merge, run this script again without --setup-only and with --redeploy-web.", SAFE]
    assert "WARNING" not in run.out and "not on main yet" not in run.out
    assert invoker_scope(harness.state()) == [True, False]  # on the project until the first release makes the service
    again = harness.run("--setup-only")
    assert again.code == 0 and again.writes == [] and "0 step(s) changed:" in again.out


@pytest.mark.parametrize("shell", ["zsh", "sh"])
def test_another_shell_is_told_to_use_bash_before_anything_runs(tmp_path, shell):
    path = shutil.which(shell)
    if path is None:
        pytest.skip(f"{shell} is not installed")
    run = Harness(tmp_path, live_state(), path).run("--dry-run")
    assert (run.code, run.calls, run.out) == (2, [], "")
    assert run.err == "run this script with bash: bash scripts/ops/owner_setup.sh\n"
    # The guard is the first thing the script does, in words every shell reads the same way.
    code = [line.strip() for line in SCRIPT.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")]
    assert code[:5] == ["case ${BASH_VERSION:-}:${SHELLOPTS:-} in", ":* | *:*posix*)",
                        "echo 'run this script with bash: bash scripts/ops/owner_setup.sh' >&2",
                        "return 2 2> /dev/null || exit 2", ";;"]
    assert code[5:7] == ["esac", "set -euo pipefail"]
