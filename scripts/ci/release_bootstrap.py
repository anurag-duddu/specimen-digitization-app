"""The bootstrap on the data gate path (RELEASE.md 4.5, T3e): the owner-approved hierarchy, read first.

After a successful verify or apply, the release job reads the owner's private hierarchy artifact from the data-production
secret DATA_BOOTSTRAP_ARTIFACT_B64, which deploy_data took out of the environment, with the other bootstrap secrets,
before any child process started. Before anything else it must be the artifact the owner approved: the SHA-256 of its
exact bytes equals DATA_BOOTSTRAP_APPROVED_SHA256, the digest from the owner's private approval record. It is
compared in constant time and never computed from the artifact, since a self-consistent artifact with two
collections' identifiers swapped carries its own matching artifact_sha256. The artifact must also be the hierarchy mode,
bind this commit's collection tree by its digest, and regenerate exactly from its own values.

The organization's rows are then read first. An exact match skips. An absent organization is written once, after a
backup and a fresh read of the administrator's account, through bootstrap_release's reviewed hierarchy path, which
retains its intent, response, readback and receipt encrypted to the committed evidence recipient. Anything else fails.
The requests are bootstrap_release's (executeGraphql, executeGraphqlRead, accounts:lookup), which the owner's
time-bounded specimenDataOwnerBootstrap role grants. There is no generic GraphQL input: each document is a reviewed
constant here or regenerated from the approved artifact. Only fixed text reaches the log or the receipt.
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
from release_diagnostics import HTTPFailure

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT, APPROVED = "DATA_BOOTSTRAP_ARTIFACT_B64", "DATA_BOOTSTRAP_APPROVED_SHA256"
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
# Each read list's fields, and which of them are UUIDs: SQL Connect returns those without hyphens.
SHAPES = {"collections": ({"id", "organizationId", "name", "parentId"}, {"id", "organizationId", "parentId"}),
          "matchingCollections": ({"id", "organizationId", "name", "parentId"}, {"id", "organizationId", "parentId"}),
          "organizationMembers": ({"uid", "active"}, set()),
          "members": ({"uid", "collectionId", "active", "role", "canViewSensitive"}, {"collectionId"})}


class Refused(ValueError):
    """A fixed, value-free reason the bootstrap stopped; deploy_data prints it."""


def run(google, facts, secrets, *, backup):
    """RELEASE.md 4.5, after a successful verify or apply. facts are the data-released/v1 receipt's; this sets its
    `bootstrap`: left None without an artifact, "failed" until the bootstrap passes, then "verified" (the rows already
    matched and nothing was written) or "applied" (written and read back). secrets are the owner's, as deploy_data took
    them out of the environment before any child process started. backup takes this run's backup before the first
    write, unless the apply already took one."""
    encoded = secrets.get(ARTIFACT, "")
    if not encoded:
        print("No bootstrap artifact is set; the bootstrap is skipped.")
        return
    facts["bootstrap"] = "failed"
    payload = approved(encoded, secrets.get(APPROVED, ""))
    evidence = recipient()
    print("Bootstrap: the approved artifact passed its checks.")
    found = scope_state(read_scope(google, payload), payload)
    if found == "identical":
        facts["bootstrap"] = "verified"
        print("Bootstrap: the organization's rows already match the approved artifact; nothing is written.")
        return
    if found != "absent":
        raise Refused("the organization's rows differ from the approved artifact's; the coordinator reconciles")
    backup()
    administrator(google, payload["auth_record"])
    try:
        # The reviewed hierarchy path: an empty before-read, a durable intent, one dispatch, the exact inserted keys and
        # readback, each record kept with its encrypted sibling. The artifact's own digest is part of the approved bytes.
        B.apply_first_scope_hierarchy(google, payload, payload["artifact_sha256"], evidence)
    except (ValueError, OSError):
        raise Refused("the hierarchy's write or its readback did not verify; the coordinator reconciles from the "
                      "encrypted evidence") from None
    facts["bootstrap"] = "applied"
    print("Bootstrap: the organization's rows were written and read back.")


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


def approved_rows(payload):
    """The rows the approved hierarchy writes: the organization, the reviewed tree with each collection's parent, and the
    administrator's organization and collection memberships."""
    variables, entries = payload["request"]["variables"], payload["hierarchy"]["collections"]
    organization, ids = variables["organizationId"], {entry["key"]: entry["id"] for entry in entries}
    collections = [{"id": entry["id"], "organizationId": organization, "name": entry["name"],
                    "parentId": None if entry["parent"] is None else ids[entry["parent"]]} for entry in entries]
    return {"organization": {"id": organization, "name": variables["organizationName"]},
            "collections": collections, "matchingCollections": collections,
            "organizationMembers": [{"uid": variables["uid"], "active": True}],
            "members": [{"uid": variables["uid"], "collectionId": variables["collectionId"], "active": True,
                         "role": "admin", "canViewSensitive": False}]}


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


def scope_state(data, payload):
    """absent (nothing of the organization exists), identical (exactly the approved rows) or different."""
    if data == EMPTY:
        return "absent"
    expected = approved_rows(payload)
    try:
        same = (rows([data["organization"]], {"id", "name"}, {"id"}) == rows([expected["organization"]], {"id", "name"}, {"id"})
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
