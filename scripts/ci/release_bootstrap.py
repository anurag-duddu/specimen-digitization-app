"""The bootstrap on the data gate path (RELEASE.md 4.5, T3e): the owner-approved hierarchy and the worker's membership,
read first.

After a successful verify or apply, the release job reads the owner's private hierarchy artifact from the data-production
secret DATA_BOOTSTRAP_ARTIFACT_B64, which deploy_data took out of the environment, with the other bootstrap secrets,
before any child process started. Before anything else it must be the artifact the owner approved: the SHA-256 of its
exact bytes equals DATA_BOOTSTRAP_APPROVED_SHA256, which the owner's reviewed summarize command
(scripts/data/hierarchy_approval.py) recorded. It is compared in constant time and never computed from the artifact,
since a self-consistent artifact with two collections' identifiers swapped carries its own matching artifact_sha256.
The artifact must also be the hierarchy mode, bind this commit's collection tree by its digest, and regenerate exactly
from its own values. The worker's UID (DATA_WORKER_ACTOR_UID) must resolve against it to WORKER_MEMBERSHIP.md's request.

The organization's rows and the worker's are then read first. Exact matches skip, and any other rows fail. An absent
organization is written once, after a backup and a fresh read of the administrator's account, through bootstrap_release's
reviewed hierarchy path. Every membership step, a verify's too, starts with a read-only check that the worker's account
is disabled and has no way to sign in; an absent membership is then written once. Each write retains its intent,
response, readback and receipt encrypted to the committed evidence recipient. The requests are bootstrap_release's
(executeGraphql, executeGraphqlRead, accounts:lookup), which the owner's time-bounded specimenDataOwnerBootstrap role
grants. There is no generic GraphQL input: each document is a reviewed constant here or regenerated from the approved
artifact. Only fixed text reaches the log or the receipt.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from pathlib import Path
import re
from uuid import UUID

import bootstrap_release as B
from release_admission import strict_json
from release_catalog_envelope import validate_public_key
from release_context import PROJECT
from release_diagnostics import HTTPFailure

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT, APPROVED, WORKER = "DATA_BOOTSTRAP_ARTIFACT_B64", "DATA_BOOTSTRAP_APPROVED_SHA256", "DATA_WORKER_ACTOR_UID"
MODE = "first-scope-hierarchy-bootstrap/v1"
# The reviewed evidence recipient (the coordinator's ruling of 2026-09-24): only its public key is committed, and the
# SHA-256 of its PEM bytes is pinned here and checked before every use.
RECIPIENT = "infra/release/evidence-recipient.pub"
RECIPIENT_SHA256 = "2f7736623899622da19cac0bc8e9447aa7049b90776fd1b32cf9ba0283defbcc"  # pragma: allowlist secret (public key digest)
# The artifact of at most 64 reviewed collections is far smaller; a GitHub secret holds at most 48 KB.
MAX_ARTIFACT_BYTES = 65536
# Every list is one row longer than the reviewed tree, so an extra row is visible instead of truncated away.
READ_SCOPE = """query VerifyBootstrapScope($organizationId: UUID!, $ids: [UUID!]!, $limit: Int!) {
  organization(key: {id: $organizationId}) { id name }
  collections(where: {organizationId: {eq: $organizationId}}, limit: $limit) { id organizationId name parentId }
  matchingCollections: collections(where: {id: {in: $ids}}, limit: $limit) { id organizationId name parentId }
  organizationMembers(where: {organizationId: {eq: $organizationId}}, limit: $limit) { uid active }
  members: collectionMembers(where: {organizationId: {eq: $organizationId}}, limit: $limit) {
    uid collectionId active role canViewSensitive
  }
}
"""
EMPTY = {"organization": None, "collections": [], "matchingCollections": [], "organizationMembers": [], "members": []}
# The worker's rows in the organization (WORKER_MEMBERSHIP.md "Application and readback"), one collection row more than
# its allow-list.
READ_WORKER = """query VerifyWorkerMembership($organizationId: UUID!, $uid: String!, $limit: Int!) {
  organizationMember(key: {organizationId: $organizationId, uid: $uid}) { uid active }
  members: collectionMembers(where: {organizationId: {eq: $organizationId}, uid: {eq: $uid}}, limit: $limit) {
    uid collectionId active role canViewSensitive
  }
}
"""
NO_WORKER = {"organizationMember": None, "members": []}
# Each read list's fields, and which of them are UUIDs: SQL Connect returns those without hyphens.
SHAPES = {"collections": ({"id", "organizationId", "name", "parentId"}, {"id", "organizationId", "parentId"}),
          "matchingCollections": ({"id", "organizationId", "name", "parentId"}, {"id", "organizationId", "parentId"}),
          "organizationMembers": ({"uid", "active"}, set()),
          "members": ({"uid", "collectionId", "active", "role", "canViewSensitive"}, {"collectionId"})}


class Refused(ValueError):
    """A fixed, value-free reason the bootstrap stopped; deploy_data prints it."""


def run(google, facts, secrets, *, backup):
    """RELEASE.md 4.5, after a successful verify or apply. facts are the data-released/v1 receipt's. This sets its
    `bootstrap`, the organization's rows: left None without an artifact, "failed" until they pass, then "verified"
    (they already matched; nothing was written) or "applied" (written and read back). `worker_membership` follows the
    same states for the worker's rows, from when they are found to differ or their own step starts. secrets are the
    owner's, as deploy_data took them out of the environment before any child process started. backup takes this run's
    backup before the first write, unless the apply already took one."""
    encoded = secrets.get(ARTIFACT, "")
    if not encoded:
        print("No bootstrap artifact is set; the bootstrap is skipped.")
        return
    facts["bootstrap"] = "failed"
    payload = approved(encoded, secrets.get(APPROVED, ""))
    request = worker_request(payload, secrets.get(WORKER, ""))
    evidence = recipient()
    print("Bootstrap: the approved artifact passed its checks.")
    scope, worker = read_scope(google, payload), read_worker(google, request)
    member = worker_state(worker, request)
    if member == "different":
        facts["worker_membership"] = "failed"
        raise Refused("the worker's rows differ from its membership; the coordinator reconciles")
    found = scope_state(scope, payload, request if member == "identical" else None)
    if found == "different" or (found == "absent" and member != "absent"):
        raise Refused("the organization's rows differ from the approved artifact's; the coordinator reconciles")
    if found == "absent" or member == "absent":
        backup()
    if found == "absent":
        administrator(google, payload["auth_record"])
        try:
            # The reviewed hierarchy path: an empty before-read, a durable intent, one dispatch, the exact inserted keys
            # and readback, each record kept with its encrypted sibling. The artifact's own digest is part of the
            # approved bytes.
            B.apply_first_scope_hierarchy(google, payload, payload["artifact_sha256"], evidence)
        except (ValueError, OSError):
            raise Refused("the hierarchy's write or its readback did not verify; the coordinator reconciles from the "
                          "encrypted evidence") from None
        facts["bootstrap"] = "applied"
        print("Bootstrap: the organization's rows were written and read back.")
    else:
        facts["bootstrap"] = "verified"
        print("Bootstrap: the organization's rows already match the approved artifact; nothing is written.")
    facts["worker_membership"] = "failed"
    # The S2 plan: the account lookup comes first in every membership step, a verify's too, since the account may have
    # been enabled, or gained a way to sign in, after the membership was written.
    worker_account(google, request["variables"]["uid"])
    if member == "identical":
        facts["worker_membership"] = "verified"
        print("Worker membership: already present and exact; nothing is written.")
        return
    write_worker(google, payload, request, evidence, worker)
    facts["worker_membership"] = "applied"
    print("Worker membership: written and read back.")


def approved(encoded, digest):
    """The approved artifact, regenerated from its own values, or a fixed refusal before any read. The owner-held digest
    approves the exact bytes the secret decodes to; whitespace around it or inside the base64 is not part of either."""
    digest = digest.strip(" \t\r\n")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise Refused("the bootstrap's approved digest is not set or is not 64 lowercase hex digits")
    text = re.sub(r"[ \t\r\n]", "", encoded)
    try:
        raw = base64.b64decode(text, validate=True)
    except (ValueError, binascii.Error):
        raise Refused("the bootstrap artifact is not canonical base64 of a bounded file") from None
    if not 0 < len(raw) <= MAX_ARTIFACT_BYTES or base64.b64encode(raw).decode("ascii") != text:
        raise Refused("the bootstrap artifact is not canonical base64 of a bounded file")
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), digest):
        raise Refused("the bootstrap artifact is not the one the owner approved")
    try:
        payload = strict_json(raw)
    except ValueError:
        raise Refused("the approved bootstrap artifact is not JSON") from None
    if not isinstance(payload, dict) or payload.get("schema_version") != MODE:
        raise Refused("the approved bootstrap artifact is not a hierarchy artifact")
    # The committed tree at its fixed path, never one the artifact names (FIRST_COLLECTION_BOOTSTRAP.md).
    binding = payload.get("hierarchy")
    try:
        tree = hashlib.sha256((B.ROOT / B._prepared.TREE_PATH).read_bytes()).hexdigest()
    except OSError:
        tree = None
    if not (isinstance(binding, dict) and binding.get("tree_path") == B._prepared.TREE_PATH
            and tree is not None and binding.get("tree_sha256") == tree):
        raise Refused("this commit's collection tree is not the one the approved artifact binds")
    try:
        return B.validate_prepared(payload, payload.get("artifact_sha256"))
    except (ValueError, OSError):
        raise Refused("the approved bootstrap artifact does not regenerate from its own values") from None


def recipient():
    """The committed evidence recipient, checked against its pinned digest before any record is encrypted to it."""
    try:
        pem = (ROOT / RECIPIENT).read_bytes()
        validate_public_key(pem, RECIPIENT_SHA256)
        return {"public_key_pem": pem.decode("ascii"), "public_key_sha256": RECIPIENT_SHA256}
    except (ValueError, OSError):
        raise Refused("the committed evidence recipient is not the reviewed public key") from None


def read_scope(google, payload):
    """The organization's rows, read first and read-only (executeGraphqlRead) as the data release."""
    identifiers = [entry["id"] for entry in payload["hierarchy"]["collections"]]
    limit = len(identifiers) + 1
    try:
        data = B.graphql_data(google.request("data", "POST", B.SERVICE + ":executeGraphqlRead", body={
            "query": READ_SCOPE, "variables": {"organizationId": payload["request"]["variables"]["organizationId"],
                                               "ids": identifiers, "limit": limit}}))
    except (ValueError, OSError):
        data = None
    if not (isinstance(data, dict) and set(data) == set(EMPTY)
            and all(isinstance(data[key], list) and len(data[key]) <= limit for key in SHAPES)):
        raise Refused("the organization's rows could not be read; the owner's bootstrap window must be open")
    return data


def approved_rows(payload, worker=None):
    """The rows the approved hierarchy writes: the organization, the reviewed tree with each collection's parent, and the
    administrator's organization and collection memberships; with the worker's request, its exact rows too."""
    variables, entries = payload["request"]["variables"], payload["hierarchy"]["collections"]
    organization, ids = variables["organizationId"], {entry["key"]: entry["id"] for entry in entries}
    collections = [{"id": entry["id"], "organizationId": organization, "name": entry["name"],
                    "parentId": None if entry["parent"] is None else ids[entry["parent"]]} for entry in entries]
    owner, members = worker_rows(worker) if worker is not None else (None, [])
    return {"organization": {"id": organization, "name": variables["organizationName"]},
            "collections": collections, "matchingCollections": collections,
            "organizationMembers": [{"uid": variables["uid"], "active": True}, *([owner] if owner else [])],
            "members": [{"uid": variables["uid"], "collectionId": variables["collectionId"], "active": True,
                         "role": "admin", "canViewSensitive": False}, *members]}


def rows(values, fields, identifiers):
    """A list of rows as a multiset of canonical JSON, UUIDs compared as UUIDs; ValueError unless each row has exactly
    `fields`. A missing, extra or duplicate row, or any other value, compares unequal."""
    canonical = []
    for row in values:
        if not (isinstance(row, dict) and set(row) == fields):
            raise ValueError("unexpected row")
        canonical.append(json.dumps({key: str(UUID(value)) if key in identifiers and value is not None else value
                                     for key, value in row.items()}, sort_keys=True))
    return sorted(canonical)


def scope_state(data, payload, worker=None):
    """absent (nothing of the organization exists), identical (exactly the approved rows, and the worker's when its
    request is given) or different."""
    if data == EMPTY:
        return "absent"
    expected, organization = approved_rows(payload, worker), ({"id", "name"}, {"id"})
    try:
        same = (rows([data["organization"]], *organization) == rows([expected["organization"]], *organization)
                and all(rows(data[key], *SHAPES[key]) == rows(expected[key], *SHAPES[key]) for key in SHAPES))
    except (ValueError, TypeError, AttributeError):
        same = False
    return "identical" if same else "different"


def administrator(google, identity):
    """FIRST_COLLECTION_BOOTSTRAP.md: just before the write, the administrator's account is read again, read-only."""
    try:
        B.fresh_administrator(google, identity)
    except (HTTPFailure, OSError):
        raise Refused("the administrator's account could not be read") from None
    except ValueError:
        raise Refused("the administrator's account is not exactly the approved, verified and enabled one") from None


def worker_request(payload, uid):
    """WORKER_MEMBERSHIP.md's request, resolved by #96's reviewed code from the approved artifact alone: its organization,
    and the collection each committed allow-listed key (WORKER_COLLECTION_KEYS, `insects`) names in it. It refuses the
    administrator's UID and any UID that is not explicit."""
    if not uid:
        raise Refused("the worker's UID is not set")
    try:
        return B._prepared.worker_membership_request(
            artifact=payload, approved_sha256=payload["artifact_sha256"], uid=uid,
            collection_keys=list(B._prepared.WORKER_COLLECTION_KEYS))
    except (ValueError, OSError):
        raise Refused("the worker's membership does not resolve from the approved artifact") from None


def worker_rows(request):
    """The worker's exact rows: one active organization membership, and one active operator row without sensitive access
    on each allow-listed collection."""
    variables = request["variables"]
    return ({"uid": variables["uid"], "active": True},
            [{"uid": variables["uid"], "collectionId": variables[f"c{index}"], "active": True, "role": "operator",
              "canViewSensitive": False} for index in range(len(B._prepared.WORKER_COLLECTION_KEYS))])


def read_worker(google, request, observe=None):
    """The worker's rows in the organization, read-only (executeGraphqlRead); observe sees the raw response first."""
    variables, limit = request["variables"], len(B._prepared.WORKER_COLLECTION_KEYS) + 1
    try:
        response = google.request("data", "POST", B.SERVICE + ":executeGraphqlRead", body={
            "query": READ_WORKER, "variables": {"organizationId": variables["organizationId"], "uid": variables["uid"],
                                                "limit": limit}})
        if observe is not None:
            observe(response)
        data = B.graphql_data(response)
    except (ValueError, OSError):
        data = None
    if not (isinstance(data, dict) and set(data) == set(NO_WORKER) and isinstance(data["members"], list)
            and len(data["members"]) <= limit):
        raise Refused("the worker's rows could not be read; the owner's bootstrap window must be open")
    return data


def worker_state(data, request):
    """absent (the worker has no row in the organization), identical (exactly its membership) or different."""
    if data == NO_WORKER:
        return "absent"
    (owner, members), owner_shape, member_shape = worker_rows(request), SHAPES["organizationMembers"], SHAPES["members"]
    try:
        same = (rows([data["organizationMember"]], *owner_shape) == rows([owner], *owner_shape)
                and rows(data["members"], *member_shape) == rows(members, *member_shape))
    except (ValueError, TypeError, AttributeError):
        same = False
    return "identical" if same else "different"


def worker_account(google, uid):
    """The coordinator's ruling from #96's security review and the S2 plan: first in every membership step, a verify's
    too, the worker's UID is looked up read-only (accounts:lookup by localId). The API admits any enabled account with a
    verified museum email, so the worker's must be one nobody can sign in with: exactly one account, disabled, and
    without an email, a password, a phone number, a sign-in provider or a tenant. A wrong UID therefore never gives a
    person's account the membership, and an account enabled or given a way to sign in after the write fails the run."""
    try:
        result = google.request("identity", "POST", f"projects/{PROJECT}/accounts:lookup", body={"localId": [uid]})
    except (ValueError, OSError):
        raise Refused("the worker's account could not be read") from None
    users = result.get("users", []) if isinstance(result, dict) else None
    if users == []:
        raise Refused("the worker's account does not exist")
    if not (isinstance(users, list) and len(users) == 1 and isinstance(users[0], dict) and users[0].get("localId") == uid):
        raise Refused("the worker's UID does not name exactly one account")
    user = users[0]
    # A field present with any value counts: an empty passwordHash still means a password (Firebase Admin, UserRecord).
    for refused, reason in ((user.get("disabled") is not True, "is enabled"),
                            ("email" in user, "has an email address"),
                            ("passwordHash" in user or "passwordUpdatedAt" in user, "has a password"),
                            ("phoneNumber" in user, "has a phone number"),
                            (user.get("providerUserInfo", []) != [], "has a sign-in provider"),
                            ("tenantId" in user, "belongs to a tenant")):
        if refused:
            raise Refused(f"the worker's account {reason}")


def write_worker(google, payload, request, evidence, before):
    """WORKER_MEMBERSHIP.md: the reviewed document for the allow-listed collections, regenerated rather than supplied, in
    one transaction; its exact inserted keys; then the worker's rows read back exactly. Each record is kept with its
    encrypted sibling, a failed write's included, as bootstrap_release keeps the hierarchy's."""
    body = {"query": request["query"], "variables": request["variables"]}
    variables, count = body["variables"], len(B._prepared.WORKER_COLLECTION_KEYS)
    keys = {"organizationMember_insert": {"organizationId": "organizationId", "uid": "uid"},
            **{f"m{index}": {"organizationId": "organizationId", "collectionId": f"c{index}", "uid": "uid"}
               for index in range(count)}}
    try:
        provenance, retain = B.evidence_retainer(google, payload["artifact_sha256"], evidence)
        retain("worker-membership.intent.json", {
            "version": "worker-membership-intent/v1", **provenance,
            "request_sha256": hashlib.sha256(B.canonical(body)).hexdigest(),
            "before_sha256": hashlib.sha256(B.canonical(before)).hexdigest()})
        # The intent is durable before the one dispatch; a replay stops on the organization member's key.
        response = google.request("data", "POST", B.SERVICE + ":executeGraphql", body=body)
        retain("worker-membership.response.json", response)
        inserted = B.graphql_data(response)
        if set(inserted) != set(keys) or not all(
                isinstance(inserted[field], dict) and set(inserted[field]) == set(mapping)
                and all(inserted[field][key] == variables[name] if key == "uid"
                        else B.same_uuid(inserted[field][key], variables[name]) for key, name in mapping.items())
                for field, mapping in keys.items()):
            raise ValueError("worker membership inserted keys differ")
        # Retain even a rejected readback before interpreting it.
        after = read_worker(google, request, lambda value: retain("worker-membership.readback.json", value))
        if worker_state(after, request) != "identical":
            raise ValueError("worker membership readback differs")
        retain("worker-membership.verified.json", {
            "version": "worker-membership-applied/v1", **provenance,
            "membership_sha256": hashlib.sha256(B.canonical(after)).hexdigest(), "membership_verified": True,
            "collections_verified": count, "role": "operator", "sensitive_access": False, "release_accepted": False})
    except (ValueError, OSError):
        raise Refused("the worker's membership write or its readback did not verify; the coordinator reconciles from "
                      "the encrypted evidence") from None
