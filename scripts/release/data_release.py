#!/usr/bin/env python3
"""Release the data plane for the merged commit; .github/workflows/data-release.yml runs this.

Eight steps in a fixed order: init, diff, apply, schema, indexes, connector, rules, bootstrap. Each one reads the
live state first and changes only what differs, so a commit that touches no data file changes nothing. SQL runs
through scripts/release/data_sql.mjs as the release identity's IAM SQL user; everything else is Google REST.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from google.auth.exceptions import GoogleAuthError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
# Pure helpers only; importing them reads no environment and calls nothing. release_bootstrap holds the reviewed
# read queries and row comparison, its B is bootstrap_release and B._prepared is scripts/data/bootstrap_admin.py.
import release_bootstrap as reviewed  # noqa: E402
import schema_gate  # noqa: E402

PROJECT, REGION = "specimen-digitization", "us-east4"
INSTANCE, DATABASE = "specimen-digitization-instance", "specimen-digitization-database"
DATA = "https://firebasedataconnect.googleapis.com/v1/"
RULES = "https://firebaserules.googleapis.com/v1/"
SERVICE = f"projects/{PROJECT}/locations/{REGION}/services/specimen-digitization-service"
SCHEMA, CONNECTOR = f"{SERVICE}/schemas/main", f"{SERVICE}/connectors/specimen-server"
RULE_RELEASE = f"projects/{PROJECT}/releases/firebase.storage/{PROJECT}.firebasestorage.app"
RULESET = re.compile(rf"projects/{re.escape(PROJECT)}/rulesets/[A-Za-z0-9_-]{{1,100}}")
OPERATION = re.compile(rf"projects/[^/]+/locations/{REGION}/operations/[A-Za-z0-9_-]+")
# Secret Manager, pinned to version 1: the Firebase UID the worker acts as.
WORKER_UID_URL = (f"https://secretmanager.googleapis.com/v1/projects/{PROJECT}/secrets/specimen-worker-actor-uid"
                  "/versions/1:access")
ARTIFACT = "DATA_BOOTSTRAP_ARTIFACT_B64"
INDEX_FILES = ("dataconnect/sql/paging-indexes.sql", "dataconnect/sql/search-indexes.sql")
OWNER_SETUP = "the owner runs scripts/ops/owner_setup.sh once"
HTTP_SECONDS, OPERATION_SECONDS, SQL_SECONDS = 120, 600, 1200
# A call that changes nothing is tried again on a lost connection, 429 or 5xx; a write never is.
ATTEMPTS, BACKOFF_SECONDS = 3, 2
# How much of a failed SQL step's other stderr output reaches the log.
STDERR_LINES = 10
ANY_ORGANIZATION = "query AnyOrganization { organizations(limit: 1) { id } }"
# The additive rule reads a diff statement outside its quoted identifiers and string literals.
QUOTED = re.compile("'(?:[^']|'')*'" + '|"(?:[^"]|"")*"')
HARMLESS = re.compile(r"\bDROP\s+NOT\s+NULL\b|\bON\s+DELETE\s+(?:CASCADE|RESTRICT|NO\s+ACTION|SET\s+NULL|SET\s+DEFAULT)\b",
                      re.I)
REMOVING = re.compile(r"\b(DROP|TRUNCATE|DELETE|RENAME)\b", re.I)
# A statement that is nothing but DROP INDEX of one name in schema public, in the forms Data Connect's differ writes.
INDEX_DROP = re.compile(r'''\s*(?i:DROP\s+INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+EXISTS\s+)?)(?:(?:"public"|(?i:public))\s*\.\s*)?'''
                        r'''(?:"([a-z_][a-z0-9_]*)"|([A-Za-z_][A-Za-z0-9_]*))\s*;?\s*''')


class Failure(Exception):
    """One actionable line; the release stops and exits non-zero."""


class HttpFailure(Failure):
    def __init__(self, label, status, body):
        self.status, self.body = status, body
        error = body.get("error") if isinstance(body, dict) else None
        detail = f": {error['message']}" if isinstance(error, dict) and isinstance(error.get("message"), str) else ""
        hint = f" ({OWNER_SETUP} if a permission is missing)" if status in (401, 403) else ""
        super().__init__(f"{label} answered HTTP {status}{detail}{hint}")


def say(line):
    print(line, flush=True)


class Api:
    """Google REST over one authorized session; every call has a timeout."""

    def __init__(self, session):
        self.session = session

    def call(self, method, url, *, body=None, params=None, missing=False, private=False, idempotent=None):
        """The JSON answer. missing: a 404 reads as None. private: a failure never quotes the answer. idempotent:
        the call changes nothing (every GET, and what the caller says so), so a transient failure is tried again."""
        label = f"{method} {url.split('/v1/', 1)[-1]}"
        attempts = ATTEMPTS if (method == "GET" if idempotent is None else idempotent) else 1
        for attempt in range(1, attempts + 1):
            try:
                response = self.session.request(method, url, json=body, params=params, timeout=HTTP_SECONDS)
            except GoogleAuthError as error:
                raise Failure(f"{label}: Google refused the workflow's identity ({error}); {OWNER_SETUP}") from None
            except OSError as error:  # requests' own errors are OSErrors
                if attempt == attempts:
                    raise Failure(f"{label} got no answer ({type(error).__name__}); re-run the workflow") from None
                problem = f"no answer ({type(error).__name__})"
            else:
                if attempt == attempts or not (response.status_code == 429 or response.status_code >= 500):
                    break
                problem = f"HTTP {response.status_code}"
            say(f"{label}: {problem} on attempt {attempt} of {attempts}; trying again")
            time.sleep(BACKOFF_SECONDS * attempt)
        if missing and response.status_code == 404:
            return None
        try:
            answer = response.json()
        except ValueError:
            answer = None
        if not 200 <= response.status_code < 300:
            raise HttpFailure(label, response.status_code, None if private else answer)
        if not isinstance(answer, dict):
            raise Failure(f"{label} did not answer with a JSON object")
        return answer

    def wait(self, operation, what):
        """Poll a Data Connect operation until it is done."""
        started = time.monotonic()
        while not operation.get("done"):
            name = operation.get("name")
            if not (isinstance(name, str) and OPERATION.fullmatch(name)):
                raise Failure(f"{what}: Data Connect answered without an operation to follow")
            if time.monotonic() - started > OPERATION_SECONDS:
                raise Failure(f"{what}: the operation is still running after {OPERATION_SECONDS // 60} minutes; "
                              "re-run the workflow, it continues from the live state")
            time.sleep(5)
            operation = self.call("GET", DATA + name)
        if operation.get("error"):
            raise Failure(f"{what}: the operation failed: {operation['error'].get('message', 'no message')}")


def node_sql(mode, *arguments):
    """Run one scripts/release/data_sql.mjs mode. Its stdout is a JSON answer. When it fails, the reason is its own
    last stderr line, the one that starts with "data_sql"; whatever else Node printed is not the reason."""
    command = ["node", str(ROOT / "scripts/release/data_sql.mjs"), mode, *arguments]
    try:
        done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=SQL_SECONDS)
    except FileNotFoundError:
        raise Failure("node is not on PATH") from None
    except subprocess.TimeoutExpired:
        raise Failure(f"{mode}: the SQL step is still running after {SQL_SECONDS // 60} minutes") from None
    if done.returncode:
        lines = [line for line in done.stderr.splitlines() if line.strip()]
        own = [line for line in lines if line.startswith("data_sql ")]
        reason = (own or lines or [f"data_sql {mode}: the SQL step failed without a message"])[-1]
        others = [line for line in lines if line is not reason]
        # The rest goes to the log before the reason, a few lines at most.
        for line in others[-STDERR_LINES:]:
            say(line)
        if len(others) > STDERR_LINES:
            say(f"{mode}: {len(others) - STDERR_LINES} more line(s) of Node output are not shown")
        raise Failure(reason.removeprefix("data_sql "))
    return json.loads(done.stdout) if done.stdout.strip() else None


def committed(folder):
    """One folder's committed top-level *.gql files, {name: text}."""
    return schema_gate.read_tree(ROOT / folder)


def live_files(resource):
    """A live schema's or connector's source files, {path: text}; a missing resource or source has none."""
    source = resource.get("source") if isinstance(resource, dict) else None
    entries = source.get("files") if isinstance(source, dict) else None
    return {entry.get("path"): entry.get("content") for entry in entries or [] if isinstance(entry, dict)}


def source(folder):
    return {"files": [{"path": name, "content": text} for name, text in committed(folder).items()]}


def schema_body():
    """The committed schema over the one Cloud SQL database; COMPATIBLE lets the database hold more than the schema."""
    cloud_sql = {"instance": f"projects/{PROJECT}/locations/{REGION}/instances/{INSTANCE}"}
    return {"name": SCHEMA, "source": source("dataconnect/schema"), "datasources": [{"postgresql": {
        "database": DATABASE, "cloudSql": cloud_sql, "schemaValidation": "COMPATIBLE"}}]}


def parse_diff(body):
    """A validate-only schema update's 400 body as Data Connect's SQL diff, (diffs, destructive). It is the shape
    firebase-tools reads: one IncompatibleSqlSchemaError {diffs: [{sql, description, destructive}], destructive}
    beside a PreconditionFailure whose violations are all INCOMPATIBLE_SCHEMA."""
    error = body.get("error") if isinstance(body, dict) else None
    details = error.get("details") if isinstance(error, dict) else None
    details = [detail for detail in details if isinstance(detail, dict)] if isinstance(details, list) else []
    found = [detail for detail in details if "IncompatibleSqlSchemaError" in str(detail.get("@type"))]
    violations = [violation if isinstance(violation, dict) else {}
                  for detail in details if "google.rpc.PreconditionFailure" in str(detail.get("@type"))
                  for violation in (detail.get("violations") if isinstance(detail.get("violations"), list) else [None])]
    kinds = {violation.get("type") for violation in violations}
    message = error.get("message") if isinstance(error, dict) and isinstance(error.get("message"), str) else "no message"
    message = " ".join(message.split())
    if "INCOMPATIBLE_CONNECTOR" in kinds:
        # The live connector holds an operation the committed schema no longer supports. Nothing here removes or
        # rewrites a connector, so a person decides.
        names = sorted({" ".join(str(violation.get("subject") or "specimen-server").split())
                        for violation in violations if violation.get("type") == "INCOMPATIBLE_CONNECTOR"})
        raise Failure(f"diff: the committed schema does not fit the live connector ({', '.join(names)}); this needs "
                      f"the owner's decision. Data Connect said: {message}")
    if len(found) != 1 or kinds != {"INCOMPATIBLE_SCHEMA"}:
        reason = ("Data Connect cannot read the database (INACCESSIBLE_SCHEMA); check the init step's grants"
                  if "INACCESSIBLE_SCHEMA" in kinds else f"Data Connect refused the committed schema: {message}")
        raise Failure(f"diff: {reason}")
    diffs = found[0].get("diffs")
    if not (isinstance(diffs, list) and diffs and all(isinstance(diff, dict) and isinstance(diff.get("sql"), str)
                                                      and diff["sql"].strip() for diff in diffs)):
        raise Failure("diff: Data Connect's SQL diff holds no readable statements")
    return diffs, found[0].get("destructive", False) is not False


def refusal(sql):
    """Why one diff statement is not additive, or None. Only DROP NOT NULL and a foreign key's ON DELETE action may
    use those words; quoted identifiers and string literals may hold anything."""
    if "\\" in sql:
        return "holds a backslash, so its quoting cannot be read safely"
    bare = QUOTED.sub(" ", sql)
    if re.search(r"""['"]|--|/\*|\$\w*\$""", bare):
        return "holds an unbalanced quote, a comment or a dollar quote, so it cannot be read safely"
    found = REMOVING.search(HARMLESS.sub(" ", bare))
    return f"{found.group(1).upper()} removes or renames something" if found else None


def own_indexes():
    """The names of the supplemental indexes the release itself creates, read from the committed index files."""
    names = set()
    for file in INDEX_FILES:
        for statement in re.sub(r"^\s*--.*$", "", (ROOT / file).read_text(), flags=re.M).split(";"):
            found = re.match(r"\s*CREATE INDEX CONCURRENTLY IF NOT EXISTS ([a-z_][a-z0-9_]*)\s", statement)
            names.update(found.groups() if found else ())
    return names


def own_index_drop(sql, names):
    """Whether a diff statement is exactly DROP INDEX of one of those names. Data Connect does not know the
    supplemental indexes, so its diff may ask to remove them; such a statement is set aside, never run."""
    found = INDEX_DROP.fullmatch(sql)
    return bool(found) and (found.group(1) or found.group(2).lower()) in names


def graphql(api, method, body, what):
    """One admin GraphQL call's data. Variables and answers hold private identifiers, so nothing of them is printed."""
    answer = api.call("POST", f"{DATA}{SERVICE}:{method}", body=body, private=True,
                      idempotent=method == "executeGraphqlRead")
    errors = answer.get("errors")
    if errors or not isinstance(answer.get("data"), dict):
        paths = sorted({".".join(str(part) for part in error.get("path", [])) for error in errors or []
                        if isinstance(error, dict) and isinstance(error.get("path"), list)} - {""})
        raise Failure(f"bootstrap: {what} was refused by Data Connect" + (f" at {', '.join(paths)}" if paths else "")
                      + "; the messages are withheld because they can hold private values")
    return answer["data"]


def read_artifact(encoded):
    """The owner's hierarchy artifact from its secret, or None when the secret is unset. Never printed."""
    if not encoded.strip():
        return None
    try:
        payload = json.loads(base64.b64decode("".join(encoded.split()), validate=True))
        variables, entries = payload["request"]["variables"], payload["hierarchy"]["collections"]
        if not (isinstance(variables.get("organizationId"), str) and isinstance(entries, list) and entries
                and all(isinstance(entry.get("id"), str) and isinstance(entry.get("key"), str) for entry in entries)):
            raise ValueError
    except (ValueError, KeyError, TypeError, AttributeError):
        raise Failure(f"bootstrap: {ARTIFACT} is not the base64 of a hierarchy artifact (request.variables, "
                      f"hierarchy.collections); {OWNER_SETUP}") from None
    return payload


class Release:
    """One run: the REST client, the SQL runner, the artifact secret's text and what the diff step found."""

    def __init__(self, api, sql, artifact=""):
        self.api, self.sql, self.artifact, self.statements = api, sql, artifact, []


def init(run):
    """a. The roles, grants and extension the schema needs; created once, checked on every run."""
    missing = sorted(name for name, present in run.sql("probe").items() if present is not True)
    if not missing:
        return say("init: all present, skipped")
    say(f"init: missing {', '.join(missing)}; running scripts/release/sql/initialize.sql")
    run.sql("init")
    still = sorted(name for name, present in run.sql("probe").items() if present is not True)
    if still:
        raise Failure(f"init: still missing after scripts/release/sql/initialize.sql: {', '.join(still)}")
    say(f"init: created {', '.join(missing)}")


def diff(run):
    """b. Data Connect's own SQL diff between the database and the committed schema; nothing is changed here."""
    try:
        run.api.call("PATCH", DATA + SCHEMA, body=schema_body(), idempotent=True,
                     params={"allowMissing": "true", "validateOnly": "true"})
        return say("diff: the database already fits the committed schema")
    except HttpFailure as failure:
        if failure.status != 400:
            raise
        diffs, destructive = parse_diff(failure.body)
    say(f"diff: {len(diffs)} SQL statement(s) from Data Connect")
    names, kept, refused, marked = own_indexes(), [], [], False
    for at, entry in enumerate(diffs, 1):
        # One line each, behind a number, so no statement text can start a line of the log.
        say(f"  [{at}] {' '.join(entry['sql'].split())}")
        if own_index_drop(entry["sql"], names):
            continue
        kept.append(entry["sql"])
        flagged = entry.get("destructive", False) is not False
        marked = marked or flagged
        reason = "Data Connect marked it destructive" if flagged else refusal(entry["sql"])
        if reason:
            refused.append(f"statement {at} {reason}")
    aside = len(diffs) - len(kept)
    if aside:
        say(f"diff: set aside {aside} DROP INDEX statement(s), never run: Data Connect does not know the release's "
            "own supplemental indexes; they stay")
    # The diff's own destructive mark stands unless the statements set aside account for all of it.
    if destructive and (marked or not aside):
        refused.insert(0, "Data Connect marked the diff destructive")
    if refused:
        raise Failure("diff: not additive, nothing was applied: " + "; ".join(refused)
                      + ". A destructive schema change stops the release and needs the owner's decision")
    run.statements = kept


def apply(run):
    """c. The diff's statements, in one transaction as the owner role."""
    if not run.statements:
        return say("apply: no SQL change, skipped")
    with tempfile.TemporaryDirectory() as folder:
        plan = Path(folder) / "plan.json"
        plan.write_text(json.dumps({"statements": run.statements}))
        run.sql("migrate", str(plan))
    say(f"apply: committed {len(run.statements)} statement(s) in one transaction")


def schema(run):
    """d. The committed schema sources."""
    files = committed("dataconnect/schema")
    if not run.statements and live_files(run.api.call("GET", DATA + SCHEMA, missing=True)) == files:
        return say("schema: live sources equal the committed ones, skipped")
    run.api.wait(run.api.call("PATCH", DATA + SCHEMA, body=schema_body(), params={"allowMissing": "true"}), "schema")
    say(f"schema: deployed {len(files)} file(s)")


def indexes(run):
    """e. The supplemental indexes the schema language cannot declare."""
    result = run.sql("indexes", *INDEX_FILES)
    if result["invalid"]:
        raise Failure(f"indexes: invalid index {', '.join(result['invalid'])}; it is never removed automatically "
                      "and needs the owner's decision")
    say(f"indexes: created {', '.join(result['created'])}" if result["created"] else "indexes: all present, skipped")


def connector(run):
    """f. The committed connector operations."""
    files = committed("dataconnect/connector")
    if live_files(run.api.call("GET", DATA + CONNECTOR, missing=True)) == files:
        return say("connector: live sources equal the committed ones, skipped")
    body = {"name": CONNECTOR, "source": source("dataconnect/connector")}
    run.api.wait(run.api.call("PATCH", DATA + CONNECTOR, body=body, params={"allowMissing": "true"}), "connector")
    say(f"connector: deployed {len(files)} file(s)")


def rules(run):
    """g. storage.rules, as a new ruleset the Storage release then points at."""
    content = (ROOT / "storage.rules").read_text()
    release = run.api.call("GET", RULES + RULE_RELEASE, missing=True)
    if release is not None:
        name = release.get("rulesetName")
        if not (isinstance(name, str) and RULESET.fullmatch(name)):
            raise Failure("rules: the live Storage release names no ruleset")
        live = (run.api.call("GET", RULES + name).get("source") or {}).get("files") or []
        if [entry.get("content") for entry in live if isinstance(entry, dict)] == [content]:
            return say("rules: the live ruleset equals storage.rules, skipped")
    files = [{"name": "storage.rules", "content": content}]
    created = run.api.call("POST", f"{RULES}projects/{PROJECT}/rulesets", body={"source": {"files": files}}).get("name")
    if not (isinstance(created, str) and RULESET.fullmatch(created)):
        raise Failure("rules: creating the ruleset returned no ruleset name")
    pointer = {"name": RULE_RELEASE, "rulesetName": created}
    if release is None:
        run.api.call("POST", f"{RULES}projects/{PROJECT}/releases", body=pointer)
    else:
        run.api.call("PATCH", RULES + RULE_RELEASE, body={"release": pointer})
    if run.api.call("GET", RULES + RULE_RELEASE).get("rulesetName") != created:
        raise Failure("rules: the Storage release does not name the new ruleset; re-run the workflow")
    say("rules: published storage.rules")


def unlike(live, wanted, fields, identifiers):
    """Whether live rows differ from the wanted ones, UUIDs compared as UUIDs; a malformed row differs."""
    try:
        return reviewed.rows(live, fields, identifiers) != reviewed.rows(wanted, fields, identifiers)
    except (ValueError, TypeError, AttributeError):
        return True


def differing(scope, administrator, payload, uid, member):
    """The parts of the live rows that differ from the artifact, named in plain words and never by a value.
    administrator: the administrator's own rows, read by key, so a long member list cannot hide them."""
    variables, wanted, shapes = payload["request"]["variables"], reviewed.approved_rows(payload), reviewed.SHAPES
    others = [row for key in ("organizationMembers", "members") for row in scope.get(key) or []
              if not isinstance(row, dict) or row.get("uid") not in (variables["uid"], uid)]
    parts = {
        "organization": unlike([scope.get("organization")], [wanted["organization"]], {"id", "name"}, {"id"}),
        "collections": any(unlike(scope.get(key), wanted[key], *shapes[key])
                           for key in ("collections", "matchingCollections")),
        "administrator membership": (
            unlike([administrator.get("organizationMember")], wanted["organizationMembers"], *shapes["organizationMembers"])
            or unlike(administrator.get("members"), wanted["members"], *shapes["members"])),
        "other memberships": bool(others),
        "worker membership": member == "different",
    }
    return [name for name, differs in parts.items() if differs]


def bootstrap(run):
    """h. The organization, its collections and the owner's membership, then the worker's membership. Each is read
    first: identical rows are left alone, absent rows are written once and read back, and rows that differ are left
    alone with one warning, so rows added or changed after the first release never stop a later one."""
    try:
        _bootstrap(run.api, read_artifact(run.artifact))
    except Failure:
        raise
    except Exception as error:  # Nothing of an unexpected error is printed: it may quote a private value.
        raise Failure(f"bootstrap: stopped on an unexpected {type(error).__name__}; nothing more was written") from None


def _bootstrap(api, payload):
    prepared = reviewed.B._prepared
    if payload is None:
        # Without the artifact nothing can be compared or written; any organization means the rows were written.
        if not graphql(api, "executeGraphqlRead", {"query": ANY_ORGANIZATION}, "the organization read").get("organizations"):
            raise Failure(f"bootstrap: no organization exists and {ARTIFACT} is not set; {OWNER_SETUP}")
        return say(f"bootstrap: an organization exists and {ARTIFACT} is not set, skipped without comparing")
    variables = payload["request"]["variables"]
    identifiers = {entry["key"]: entry["id"] for entry in payload["hierarchy"]["collections"]}
    uid = base64.b64decode(api.call("GET", WORKER_UID_URL, private=True)["payload"]["data"]).decode().strip()
    # The worker's request variables, resolved without validating the artifact: the reads need nothing more.
    worker = {"variables": {"organizationId": variables["organizationId"], "uid": uid, **{
        f"c{index}": identifiers[key] for index, key in enumerate(prepared.WORKER_COLLECTION_KEYS)}}}

    def scope():
        return graphql(api, "executeGraphqlRead", {"query": reviewed.READ_SCOPE, "variables": {
            "organizationId": variables["organizationId"], "ids": list(identifiers.values()),
            "limit": len(identifiers) + 1}}, "the organization read")

    def membership(who=uid, limit=len(prepared.WORKER_COLLECTION_KEYS) + 1):
        return graphql(api, "executeGraphqlRead", {"query": reviewed.READ_WORKER, "variables": {
            "organizationId": variables["organizationId"], "uid": who, "limit": limit}}, "the membership read")

    member, live = reviewed.worker_state(membership(), worker), scope()
    found = reviewed.scope_state(live, payload, worker if member == "identical" else None)
    if found == "absent" and member != "absent":
        # The hierarchy would have to be written under membership rows that contradict it. Foreign keys make this
        # unreachable unless the two reads disagree.
        raise Failure("bootstrap: the organization reads as absent while the worker's membership rows exist; nothing "
                      "was written and this needs the owner's decision")
    if "different" in (found, member):
        # Rows added or changed since the first release are not this step's to judge or to overwrite.
        parts = differing(live, membership(variables["uid"], 2), payload, uid, member) or ["rows"]
        unwritten = "; the worker's membership is absent and was not written" if member == "absent" else ""
        return say(f"::warning title=Bootstrap rows differ::bootstrap: live rows differ from the artifact "
                   f"({', '.join(parts)}); nothing was written{unwritten} and the release continues. If the live rows "
                   f"are the intended ones, the owner can remove the {ARTIFACT} secret to end this check")
    if found == "identical":
        say("bootstrap: hierarchy rows already match the artifact, skipped")
    else:
        # Only a write validates the artifact against the committed collection tree, so a later tree edit cannot
        # fail releases once the rows exist. The validated copy is what gets written.
        try:
            approved = reviewed.B.validate_prepared(payload, payload.get("artifact_sha256"))
        except (ValueError, OSError) as error:
            raise Failure(f"bootstrap: the artifact does not regenerate from this commit ({error}); {OWNER_SETUP}") from None
        graphql(api, "executeGraphql", approved["request"], "the hierarchy write")
        if reviewed.scope_state(scope(), payload) != "identical":
            raise Failure("bootstrap: the hierarchy was written but its readback differs; this needs the owner's decision")
        say(f"bootstrap: wrote the organization, {len(identifiers)} collections and the owner's membership")
    if member == "identical":
        return say("bootstrap: worker membership already matches, skipped")
    try:
        request = prepared.worker_membership_request(artifact=payload, approved_sha256=payload.get("artifact_sha256"),
                                                     uid=uid, collection_keys=list(prepared.WORKER_COLLECTION_KEYS))
    except (ValueError, OSError):
        raise Failure("bootstrap: the worker's membership does not resolve from the artifact and secret "
                      f"specimen-worker-actor-uid version 1; {OWNER_SETUP}") from None
    graphql(api, "executeGraphql", {"query": request["query"], "variables": request["variables"]}, "the worker membership write")
    if reviewed.worker_state(membership(), request) != "identical":
        raise Failure("bootstrap: the worker's membership was written but its readback differs; this needs the owner's "
                      "decision")
    say("bootstrap: wrote the worker's operator membership")


STEPS = (init, diff, apply, schema, indexes, connector, rules, bootstrap)


def session():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return AuthorizedSession(credentials)


def main() -> int:
    # Releases come from the workflow alone: a workstation or agent shell with cloud credentials must not deploy.
    if os.environ.get("GITHUB_ACTIONS") != "true":
        say("data release runs only in the Data release workflow (merge to main, or workflow_dispatch on main)")
        return 2
    # Read once and removed, so no child process inherits the artifact.
    artifact = os.environ.pop(ARTIFACT, "")
    try:
        run = Release(Api(session()), node_sql, artifact)
        for step in STEPS:
            step(run)
    except (Failure, GoogleAuthError) as failure:
        say(f"data release failed: {failure}")
        return 1
    say(f"data release complete for {os.environ.get('GITHUB_SHA', 'unknown commit')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
