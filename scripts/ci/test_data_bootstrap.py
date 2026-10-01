"""The bootstrap on the data gate path (RELEASE.md 4.5, T3e): the owner-approved hierarchy and the worker's membership,
after verify or apply.

Artifacts are prepared from the committed collection tree with synthetic identifiers and identities; Google's replies are
synthetic, over test_data_apply's Cloud. Never network, credentials or cloud.
"""
import base64
import binascii
import copy
import hashlib
import hmac
import importlib
import importlib.util
import io
import json
import stat
from uuid import UUID

import pytest

import bootstrap_release as B
import deploy_data as D
import release_catalog_envelope
from release_diagnostics import HTTPFailure
from test_data_apply import APPLIED, BACKUP_ID, ORDER, PITR, Cloud, receipt, released  # noqa: F401 (a fixture)
from test_data_released_deploy import MERGED, RULES, SHA

PREPARED = B._prepared
TREE = (B.ROOT / PREPARED.TREE_PATH).read_bytes()
ORGANIZATION, OTHER, NAME = "c0ffee00-7f3a-4b1c-8d2e-0000000000aa", "c0ffee00-7f3a-4b1c-8d2e-0000000000bb", "Canary Museum 7f3a"
ADMIN = {"uid": "canary-admin-uid-7f3a", "email": "canary-admin-7f3a@example.invalid", "emailVerified": True,
         "disabled": False}
WORKER_UID = "canary-worker-uid-7f3a"
PINNED = "2f7736623899622da19cac0bc8e9447aa7049b90776fd1b32cf9ba0283defbcc"  # pragma: allowlist secret (public key digest)
ARTIFACT, APPROVED, WORKER = "DATA_BOOTSTRAP_ARTIFACT_B64", "DATA_BOOTSTRAP_APPROVED_SHA256", "DATA_WORKER_ACTOR_UID"
R_DIGEST = "the bootstrap's approved digest is not set or is not 64 lowercase hex digits"
R_BASE64 = "the bootstrap artifact is not canonical base64 of a bounded file"
R_APPROVAL = "the bootstrap artifact is not the one the owner approved"
R_JSON = "the approved bootstrap artifact is not JSON"
R_MODE = "the approved bootstrap artifact is not a hierarchy artifact"
R_TREE = "this commit's collection tree is not the one the approved artifact binds"
R_REGENERATE = "the approved bootstrap artifact does not regenerate from its own values"
R_RECIPIENT = "the committed evidence recipient is not the reviewed public key"
R_READ = "the organization's rows could not be read; the owner's bootstrap window must be open"
R_DIFFERENT = "the organization's rows differ from the approved artifact's; the coordinator reconciles"
R_ADMIN = "the administrator's account is not exactly the approved, verified and enabled one"
R_WRITE = ("the hierarchy's write or its readback did not verify; the coordinator reconciles from the encrypted "
           "evidence")
R_UID = "the worker's UID is not set"
R_RESOLVE = "the worker's membership does not resolve from the approved artifact"
R_WORKER_READ = "the worker's rows could not be read; the owner's bootstrap window must be open"
R_WORKER_DIFFERENT = "the worker's rows differ from its membership; the coordinator reconciles"
R_WORKER_WRITE = ("the worker's membership write or its readback did not verify; the coordinator reconciles from the "
                  "encrypted evidence")
PASSED = "Bootstrap: the approved artifact passed its checks."
WRITTEN = "Bootstrap: the organization's rows were written and read back."
MATCHED = "Bootstrap: the organization's rows already match the approved artifact; nothing is written."
WORKER_WRITTEN = "Worker membership: written and read back."
WORKER_MATCHED = "Worker membership: already present and exact; nothing is written."
ABSENT = "No bootstrap artifact is set; the bootstrap is skipped."
VERIFY, READS = ["migrated", "indexed"], ["scope", "worker-read"]
HIERARCHY, MEMBERSHIP = ["lookup", "tree", "hierarchy", "tree"], ["account", "worker", "worker-read"]
EVIDENCE = [f"{record}.{name}.encrypted.json" for record in ("first-scope-hierarchy", "worker-membership")
            for name in ("intent", "response", "readback", "verified")]


def module():
    """The gate path's bootstrap module, imported where a test needs it."""
    return importlib.import_module("release_bootstrap")


def minted(swap=()):
    """Synthetic canonical identifiers, one per reviewed collection; swap exchanges two keys' identifiers."""
    entries = PREPARED.tree_entries(TREE)
    ids = {entry["key"]: f"c0ffee00-7f3a-4b1c-8d2e-{index:012x}" for index, entry in enumerate(entries, start=1)}
    if swap:
        ids[swap[0]], ids[swap[1]] = ids[swap[1]], ids[swap[0]]
    return [{"key": entry["key"], "id": ids[entry["key"]], "name": entry["name"], "parent": entry["parent"]}
            for entry in entries]


def prepare(collections=None):
    """The owner's hierarchy artifact, as bootstrap_admin.py --hierarchy prepares it."""
    return PREPARED.prepare_first_scope_hierarchy(
        auth_record=ADMIN, requested_email=ADMIN["email"], requested_uid=ADMIN["uid"], organization_id=ORGANIZATION,
        organization_name=NAME, collections=collections or minted(), admin_collection_key="insects", tree=TREE)


def exact(payload):
    """The private file's exact bytes, as write_private_artifact writes them: canonical JSON and a newline."""
    return PREPARED._canonical(payload) + b"\n"


def key_id(payload, key):
    return next(entry["id"] for entry in payload["hierarchy"]["collections"] if entry["key"] == key)


def private(payload, raw):
    """Every private value the artifact holds or the secrets carry, with SQL Connect's unhyphenated UUIDs too."""
    variables = payload["request"]["variables"]
    values = {variables["organizationId"], variables["organizationName"], variables["uid"], ADMIN["email"], WORKER_UID,
              payload["artifact_sha256"], hashlib.sha256(raw).hexdigest(), base64.b64encode(raw).decode("ascii"),
              *(entry["id"] for entry in payload["hierarchy"]["collections"])}
    return values | {UUID(value).hex for value in values if is_uuid(value)}


def is_uuid(value):
    try:
        return str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def bare(value):
    """SQL Connect returns UUID scalars without hyphens."""
    return UUID(value).hex


def same(left, right):
    return UUID(left) == UUID(right)


def parents(payload):
    """Each reviewed collection's parent as an earlier index: the shape the hierarchy's document is rendered from."""
    keys = [entry["key"] for entry in payload["hierarchy"]["collections"]]
    return [None if entry["parent"] is None else keys.index(entry["parent"]) for entry in payload["hierarchy"]["collections"]]


class Plane(Cloud):
    """test_data_apply's Cloud with the application's rows behind Data Connect's admin GraphQL endpoints and Identity
    Toolkit's account lookup. Each call is one ordered event; `answers` replaces an event's reply with a value or an
    exception, and `fail` still names the one effect that fails."""

    def __init__(self, directory, payload, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.path, self.payload = directory / "packet.json", payload
        self.organization, self.collections, self.owners, self.members = None, [], [], []
        self.accounts = {ADMIN["email"]: {"localId": ADMIN["uid"], "email": ADMIN["email"], "emailVerified": True}}
        # The worker's own account: disabled, without email, password, phone or sign-in provider (WORKER_MEMBERSHIP.md).
        self.workers = {WORKER_UID: {"localId": WORKER_UID, "disabled": True, "emailVerified": False,
                                     "createdAt": "1790000000000", "providerUserInfo": []}}
        self.bodies, self.lookups, self.answers, self.after_worker = [], [], {}, None

    def reply(self, name, value):
        self.effect(name)
        answer = self.answers.get(name)
        if isinstance(answer, Exception):
            raise answer
        return copy.deepcopy(value if answer is None else answer)

    def request(self, api, method, resource, *, body=None, params=None, missing=False, diff=False):
        if api == "identity":
            assert (method, resource, params) == ("POST", f"projects/{D.PROJECT}/accounts:lookup", None)
            self.lookups.append(copy.deepcopy(body))
            return self.lookup(body)
        if api == "data" and resource.startswith(B.SERVICE + ":"):
            assert method == "POST" and params is None and set(body) == {"query", "variables"}
            self.bodies.append(copy.deepcopy(body))
            operation = body["query"].split("(", 1)[0]
            handlers = {"query VerifyBootstrapScope": self.scope, "query VerifyFirstScopeHierarchy": self.tree,
                        "mutation PrepareFirstScopeHierarchy": self.hierarchy,
                        "query VerifyWorkerMembership": self.worker_read, "mutation PrepareWorkerMembership": self.worker}
            assert operation in handlers, "only the reviewed documents are ever sent"
            assert resource == B.SERVICE + (":executeGraphql" if operation.startswith("mutation") else ":executeGraphqlRead")
            return handlers[operation](body)
        return super().request(api, method, resource, body=body, params=params, missing=missing, diff=diff)

    def lookup(self, body):
        """accounts:lookup: the administrator by email ("lookup"), the worker by localId ("account")."""
        (field, values), = body.items()
        assert field in ("email", "localId") and len(values) == 1
        accounts = self.accounts if field == "email" else self.workers
        users = [accounts[value] for value in values if value in accounts]
        return self.reply("lookup" if field == "email" else "account",
                          {"kind": "identitytoolkit#GetAccountInfoResponse", **({"users": users} if users else {})})

    def rows(self, variables, member_limit):
        """What the organization's reads return, filtered and limited as Data Connect would."""
        organization, limit = variables["organizationId"], variables["limit"]
        ours = [row for row in self.collections if same(row["organizationId"], organization)]
        matching = [row for row in self.collections if any(same(row["id"], value) for value in variables["ids"])]

        def shown(row):
            return {"id": bare(row["id"]), "organizationId": bare(row["organizationId"]), "name": row["name"],
                    "parentId": None if row["parentId"] is None else bare(row["parentId"])}
        return {"data": {
            "organization": {"id": bare(self.organization["id"]), "name": self.organization["name"]}
            if self.organization and same(self.organization["id"], organization) else None,
            "collections": [shown(row) for row in ours][:limit],
            "matchingCollections": [shown(row) for row in matching][:limit],
            "organizationMembers": [{"uid": row["uid"], "active": row["active"]} for row in self.owners
                                    if same(row["organizationId"], organization)][:member_limit],
            "members": [member(row) for row in self.members if same(row["organizationId"], organization)][:member_limit]}}

    def scope(self, body):
        """The gate path's read of the organization: every list limited to one row more than the reviewed tree."""
        variables = body["variables"]
        assert set(variables) == {"organizationId", "ids", "limit"}
        return self.reply("scope", self.rows(variables, variables["limit"]))

    def tree(self, body):
        """bootstrap_release's reviewed hierarchy read, before its write and after it."""
        assert body["query"] == B.READ_FIRST_SCOPE_HIERARCHY
        return self.reply("tree", self.rows(body["variables"], 2))

    def hierarchy(self, body):
        """The approved hierarchy's one transaction: all its rows, or none when the organization or an identifier exists."""
        assert body == self.payload["request"]
        self.effect("hierarchy")
        if "hierarchy" in self.answers:
            return copy.deepcopy(self.answers["hierarchy"])
        variables, entries = body["variables"], self.payload["hierarchy"]["collections"]
        if self.organization is not None or any(same(row["id"], entry["id"]) for row in self.collections
                                                for entry in entries):
            return {"errors": [{"message": "synthetic: the transaction rolled back"}]}
        seed(self, self.payload)
        organization = bare(variables["organizationId"])
        return {"data": {
            "organization_insert": {"id": organization},
            "organizationMember_insert": {"organizationId": organization, "uid": variables["uid"]},
            "collectionMember_insert": {"organizationId": organization, "collectionId": bare(variables["collectionId"]),
                                        "uid": variables["uid"]},
            **{f"c{index}": {"organizationId": organization, "id": bare(entry["id"])} for index, entry in enumerate(entries)}}}

    def worker_read(self, body):
        """The worker's rows in the organization: its organization member, and its collection rows up to the limit."""
        variables = body["variables"]
        assert set(variables) == {"organizationId", "uid", "limit"}
        organization, uid = variables["organizationId"], variables["uid"]
        owner = next((row for row in self.owners if same(row["organizationId"], organization) and row["uid"] == uid), None)
        return self.reply("worker-read", {"data": {
            "organizationMember": {"uid": owner["uid"], "active": owner["active"]} if owner else None,
            "members": [member(row) for row in self.members
                        if same(row["organizationId"], organization) and row["uid"] == uid][:variables["limit"]]}})

    def worker(self, body):
        """WORKER_MEMBERSHIP.md's one transaction: the organization member, then one operator row per collection; none
        when the uid is already a member or holds any collection row, or when a collection is unknown."""
        self.effect("worker")
        if "worker" in self.answers:
            return copy.deepcopy(self.answers["worker"])
        variables = body["variables"]
        organization, uid, collection = variables["organizationId"], variables["uid"], variables["c0"]
        if (any(same(row["organizationId"], organization) and row["uid"] == uid for row in self.owners + self.members)
                or not any(same(row["organizationId"], organization) and same(row["id"], collection)
                           for row in self.collections)):
            return {"errors": [{"message": "synthetic: the transaction rolled back"}]}
        seed_worker(self, self.payload, uid, collection)
        if self.after_worker is not None:
            self.after_worker(self)
        return {"data": {"organizationMember_insert": {"organizationId": bare(organization), "uid": uid},
                         "m0": {"organizationId": bare(organization), "collectionId": bare(collection), "uid": uid}}}


def member(row):
    return {"uid": row["uid"], "collectionId": bare(row["collectionId"]), "active": row["active"], "role": row["role"],
            "canViewSensitive": row["canViewSensitive"]}


def seed(plane, payload):
    """The rows the approved hierarchy's transaction writes: the organization, the reviewed tree, the admin's two rows."""
    variables, entries = payload["request"]["variables"], payload["hierarchy"]["collections"]
    organization, ids = variables["organizationId"], {entry["key"]: entry["id"] for entry in entries}
    plane.organization = {"id": organization, "name": variables["organizationName"]}
    plane.collections += [{"organizationId": organization, "id": entry["id"], "name": entry["name"],
                           "parentId": None if entry["parent"] is None else ids[entry["parent"]]} for entry in entries]
    plane.owners.append({"organizationId": organization, "uid": variables["uid"], "active": True})
    plane.members.append({"organizationId": organization, "collectionId": variables["collectionId"],
                          "uid": variables["uid"], "active": True, "role": "admin", "canViewSensitive": False})


def seed_worker(plane, payload, uid=WORKER_UID, collection=None):
    """The rows the worker's membership transaction writes: its organization member and its operator row on Insects."""
    organization = payload["request"]["variables"]["organizationId"]
    plane.owners.append({"organizationId": organization, "uid": uid, "active": True})
    plane.members.append({"organizationId": organization, "collectionId": collection or key_id(payload, "insects"),
                          "uid": uid, "active": True, "role": "operator", "canViewSensitive": False})


@pytest.fixture
def bootstrap(released, monkeypatch, tmp_path):
    """The release with the owner's three secrets set: the artifact's base64, the digest the owner approved (by default
    the artifact's own bytes') and the worker's UID, over a Plane on verify (the merged files live) or apply
    (test_data_apply's default). seeded: "hierarchy", or "both" with the worker's rows too. Every exit keeps the log,
    the receipt and the step output free of any private value."""
    def run(plane=None, *, phase="verify", payload=None, raw=None, encoded=None, approved=None, uid=WORKER_UID,
            seeded=None, directory="release"):
        payload = prepare() if payload is None else payload
        raw = exact(payload) if raw is None else raw
        if plane is None:
            plane = (Plane(tmp_path / directory, payload, MERGED, rules=RULES) if phase == "verify"
                     else Plane(tmp_path / directory, payload))
        if seeded:
            seed(plane, payload)
        if seeded == "both":
            seed_worker(plane, payload)
        monkeypatch.setenv(ARTIFACT, base64.b64encode(raw).decode("ascii") if encoded is None else encoded)
        monkeypatch.setenv(APPROVED, hashlib.sha256(raw).hexdigest() if approved is None else approved)
        monkeypatch.setenv(WORKER, uid)
        value, outputs = released(plane, directory)
        assert not [secret for secret in private(payload, raw) for text in (plane.log, json.dumps(value), outputs)
                    if secret in text], "a private value reached the log, the receipt or a step output"
        return plane, value, outputs
    run.tmp_path = tmp_path
    return run


def verify_plane(tmp_path, payload=None):
    return Plane(tmp_path / "release", prepare() if payload is None else payload, MERGED, rules=RULES)


def test_after_verify_the_hierarchy_and_the_workers_membership_are_backed_up_then_written_once_and_read_back(bootstrap):
    plane, value, outputs = bootstrap()
    assert plane.error is None and plane.events == [*VERIFY, *READS, "backup", *HIERARCHY, *MEMBERSHIP]
    assert value == receipt("verify", tables=1, views=0, backup_id=BACKUP_ID, bootstrap="applied",
                            worker_membership="applied")
    assert outputs == "phase=verify\nevidence=present\n"
    assert all(line in plane.log for line in (PASSED, WRITTEN, WORKER_WRITTEN)) and "Data release blocked" not in plane.log
    # Each account is read again just before its write: the administrator by email, the worker by its UID alone.
    assert plane.lookups == [{"email": [ADMIN["email"]]}, {"localId": [WORKER_UID]}]
    assert plane.organization == {"id": ORGANIZATION, "name": NAME} and len(plane.collections) == 18


def test_the_worker_becomes_a_nonsensitive_operator_in_the_collection_insects_resolves_to_and_nothing_else(bootstrap):
    plane = bootstrap()[0]
    insects = key_id(plane.payload, "insects")
    assert [(row["uid"], row["active"]) for row in plane.owners] == [(ADMIN["uid"], True), (WORKER_UID, True)]
    assert [(row["uid"], row["collectionId"], row["role"], row["canViewSensitive"]) for row in plane.members] == [
        (ADMIN["uid"], insects, "admin", False), (WORKER_UID, insects, "operator", False)]
    # The reviewed document for one collection, its values resolved from the approved artifact alone (#96).
    write = next(body for body in plane.bodies if body["query"].startswith("mutation PrepareWorkerMembership"))
    assert write == {"query": PREPARED.worker_membership_mutation(1),
                     "variables": {"organizationId": ORGANIZATION, "uid": WORKER_UID, "c0": insects}}


def test_after_an_apply_the_bootstrap_uses_the_applys_backup_and_takes_no_second_one(bootstrap):
    plane, value, outputs = bootstrap(phase="apply")
    assert plane.error is None and plane.events == [*ORDER, *READS, *HIERARCHY, *MEMBERSHIP]
    assert plane.events.count("backup") == 1 and outputs == "phase=apply\nevidence=present\n"
    assert value == receipt(**APPLIED, bootstrap="applied", worker_membership="applied")


def test_rows_that_already_match_exactly_are_verified_after_one_account_lookup_and_nothing_is_backed_up_or_written(
        bootstrap):
    """The S2 plan: the worker's account is looked up before every membership step, a verify's too, and a disabled
    account without any way to sign in lets the exact membership verify."""
    plane, value, outputs = bootstrap(seeded="both")
    assert plane.error is None and plane.events == [*VERIFY, *READS, "account"]
    assert plane.lookups == [{"localId": [WORKER_UID]}] and not any(body["query"].startswith("mutation")
                                                                    for body in plane.bodies)
    assert value == receipt("verify", tables=1, views=0, bootstrap="verified", worker_membership="verified")
    assert outputs == "phase=verify\n" and all(line in plane.log for line in (PASSED, MATCHED, WORKER_MATCHED))
    directory = bootstrap.tmp_path / "release"
    assert not list(directory.glob("first-scope-*")) and not list(directory.glob("worker-membership*"))
    assert not (directory / "release-backup.json").exists()


def test_with_the_hierarchy_in_place_only_the_workers_membership_is_written_after_a_backup(bootstrap):
    plane, value, outputs = bootstrap(seeded="hierarchy")
    assert plane.error is None and plane.events == [*VERIFY, *READS, "backup", *MEMBERSHIP]
    assert value == receipt("verify", tables=1, views=0, backup_id=BACKUP_ID, bootstrap="verified",
                            worker_membership="applied")
    assert plane.lookups == [{"localId": [WORKER_UID]}] and outputs == "phase=verify\nevidence=present\n"
    assert MATCHED in plane.log and WORKER_WRITTEN in plane.log


def test_a_re_run_after_a_written_bootstrap_verifies_and_writes_nothing(bootstrap):
    plane = bootstrap()[0]
    plane.events, plane.packet = [], {**plane.packet, "release_run_attempt": 3}
    plane.path = bootstrap.tmp_path / "rerun" / "packet.json"
    plane, value, _ = bootstrap(plane, directory="rerun")
    assert plane.error is None and plane.events == [*VERIFY, *READS, "account"]
    assert (value["bootstrap"], value["worker_membership"]) == ("verified", "verified")
    assert sum(body["query"].startswith("mutation") for body in plane.bodies) == 2


@pytest.mark.parametrize("change,message", [
    ({"disabled": False}, "the worker's account is enabled"),
    ({"providerUserInfo": [{"providerId": "google.com", "rawId": "canary-google"}]},
     "the worker's account has a sign-in provider"),
], ids=["enabled-since", "provider-since"])
def test_an_exact_membership_whose_account_changed_since_the_write_is_refused_without_a_write(
        bootstrap, tmp_path, change, message):
    """The account may have been enabled, or gained a way to sign in, after the membership was written."""
    plane = verify_plane(tmp_path)
    plane.workers[WORKER_UID].update(change)
    plane, value, outputs = bootstrap(plane, seeded="both")
    assert plane.error == message and f"Data release blocked: {message}." in plane.log
    assert plane.events == [*VERIFY, *READS, "account"] and plane.lookups == [{"localId": [WORKER_UID]}]
    assert not any(body["query"].startswith("mutation") for body in plane.bodies) and outputs == "phase=verify\n"
    assert (value["bootstrap"], value["worker_membership"], value["backup_id"]) == ("verified", "failed", None)


@pytest.mark.parametrize("change", [
    lambda plane: plane.organization.update(name="Another name"),
    lambda plane: plane.collections[2].update(parentId=plane.collections[7]["id"]),
    lambda plane: plane.collections[1].update(parentId=None),
    lambda plane: plane.collections[4].update(name="Renamed"),
    lambda plane: plane.collections.pop(),
    lambda plane: plane.collections.append({**plane.collections[0], "id": "c0ffee00-7f3a-4b1c-8d2e-0000000000cc"}),
    lambda plane: plane.collections.__setitem__(3, {**plane.collections[3], "organizationId": OTHER}),
    lambda plane: plane.owners.append({**plane.owners[0], "uid": "canary-other-member"}),
    lambda plane: plane.owners[0].update(active=False),
    lambda plane: plane.members[0].update(role="manager"),
    lambda plane: plane.members[0].update(canViewSensitive=True),
    lambda plane: plane.members[0].update(collectionId=plane.collections[2]["id"]),
    lambda plane: plane.members.append({**plane.members[0], "uid": "canary-other-member", "role": "reviewer"}),
    lambda plane: (plane.collections.clear(), plane.owners.clear(), plane.members.clear()),
    lambda plane: setattr(plane, "organization", None),
], ids=["organization-name", "parent", "root", "collection-name", "missing-collection", "extra-collection",
        "identifier-elsewhere", "extra-member", "inactive", "role", "sensitive", "admin-collection", "extra-row",
        "organization-only", "collections-only"])
def test_rows_that_differ_in_any_way_fail_before_any_effect(bootstrap, tmp_path, change):
    plane = verify_plane(tmp_path)
    seed(plane, plane.payload)
    change(plane)
    plane, value, outputs = bootstrap(plane)
    assert plane.error == R_DIFFERENT and f"Data release blocked: {R_DIFFERENT}." in plane.log
    assert plane.events == [*VERIFY, *READS] and plane.lookups == []
    assert (value["bootstrap"], value["worker_membership"], value["backup_id"]) == ("failed", None, None)
    assert outputs == "phase=verify\n"


def test_the_workers_exact_rows_beside_the_hierarchys_are_still_the_approved_rows(bootstrap, tmp_path):
    """The organization's read shows the worker's rows too once they exist; only exactly the membership is accepted."""
    plane = verify_plane(tmp_path)
    seed(plane, plane.payload)
    seed_worker(plane, plane.payload)
    plane.owners.append({**plane.owners[0], "uid": "canary-third-member"})
    plane, value, _ = bootstrap(plane)
    assert plane.error == R_DIFFERENT and plane.events == [*VERIFY, *READS] and value["bootstrap"] == "failed"


@pytest.mark.parametrize("change", [
    lambda plane: plane.owners[1].update(active=False),
    lambda plane: plane.members[1].update(role="admin"),
    lambda plane: plane.members[1].update(role="reviewer"),
    lambda plane: plane.members[1].update(canViewSensitive=True),
    lambda plane: plane.members[1].update(active=False),
    lambda plane: plane.members[1].update(collectionId=key_id(plane.payload, "mammals")),
    lambda plane: plane.members.pop(1),
    lambda plane: plane.owners.pop(1),
    lambda plane: plane.members.append({**plane.members[1], "collectionId": key_id(plane.payload, "mammals")}),
], ids=["inactive-member", "admin", "reviewer", "sensitive", "inactive-row", "mammals", "member-without-row",
        "leftover-row", "two-collections"])
def test_worker_rows_that_differ_from_its_membership_fail_before_any_effect(bootstrap, tmp_path, change):
    plane = verify_plane(tmp_path)
    seed(plane, plane.payload)
    seed_worker(plane, plane.payload)
    change(plane)
    plane, value, outputs = bootstrap(plane)
    assert plane.error == R_WORKER_DIFFERENT and f"Data release blocked: {R_WORKER_DIFFERENT}." in plane.log
    assert plane.events == [*VERIFY, *READS] and plane.lookups == [] and outputs == "phase=verify\n"
    assert (value["bootstrap"], value["worker_membership"], value["backup_id"]) == ("failed", "failed", None)


# The worker's account (the coordinator's ruling, from #96's security review): read-only, just before the write.
ACCOUNTS = {
    "missing": (None, "the worker's account does not exist"),
    "enabled": ({"disabled": False}, "the worker's account is enabled"),
    "not-disabled": ({"disabled": None}, "the worker's account is enabled"),
    "email": ({"email": "canary-worker@example.invalid"}, "the worker's account has an email address"),
    "password": ({"passwordHash": "Y2FuYXJ5"}, "the worker's account has a password"),  # pragma: allowlist secret (synthetic)
    "password-set": ({"passwordUpdatedAt": 1790000000000}, "the worker's account has a password"),
    "phone": ({"phoneNumber": "+15555550100"}, "the worker's account has a phone number"),
    "google": ({"providerUserInfo": [{"providerId": "google.com", "rawId": "canary-google"}]},
               "the worker's account has a sign-in provider"),
    "password-provider": ({"providerUserInfo": [{"providerId": "password"}]}, "the worker's account has a sign-in provider"),
    "phone-provider": ({"providerUserInfo": [{"providerId": "phone"}]}, "the worker's account has a sign-in provider"),
    "tenant": ({"tenantId": "canary-tenant"}, "the worker's account belongs to a tenant"),
    "another-uid": ({"localId": "canary-another-uid"}, "the worker's UID does not name exactly one account"),
}


@pytest.mark.parametrize("name", list(ACCOUNTS))
def test_the_workers_account_must_exist_be_disabled_and_have_no_email_password_phone_or_provider(bootstrap, tmp_path, name):
    change, message = ACCOUNTS[name]
    plane = verify_plane(tmp_path)
    if change is None:
        plane.workers.clear()
    else:
        plane.workers[WORKER_UID].update(change)
        plane.workers[WORKER_UID] = {key: value for key, value in plane.workers[WORKER_UID].items() if value is not None}
    plane, value, outputs = bootstrap(plane, seeded="hierarchy")
    assert plane.error == message and f"Data release blocked: {message}." in plane.log
    assert plane.events == [*VERIFY, *READS, "backup", "account"] and "worker" not in plane.events
    assert (value["bootstrap"], value["worker_membership"]) == ("verified", "failed")
    assert [row["uid"] for row in plane.owners] == [ADMIN["uid"]] and outputs == "phase=verify\n"


def test_two_accounts_for_one_uid_or_an_unreadable_lookup_are_refused_too(bootstrap, tmp_path):
    plane = verify_plane(tmp_path)
    plane.answers["account"] = {"users": [plane.workers[WORKER_UID], dict(plane.workers[WORKER_UID])]}
    plane = bootstrap(plane, seeded="hierarchy")[0]
    assert plane.error == "the worker's UID does not name exactly one account" and plane.events[-1] == "account"
    plane = Plane(tmp_path / "unreadable", prepare(), MERGED, rules=RULES)
    plane.answers["account"] = HTTPFailure(403)
    plane = bootstrap(plane, seeded="hierarchy", directory="unreadable")[0]
    assert plane.error == "the worker's account could not be read" and plane.events[-1] == "account"


def test_the_one_passing_account_is_disabled_with_no_sign_in_method_at_all(bootstrap, tmp_path):
    plane = verify_plane(tmp_path)
    plane.workers[WORKER_UID] = {"localId": WORKER_UID, "disabled": True}
    plane, value, _ = bootstrap(plane, seeded="hierarchy")
    assert plane.error is None and value["worker_membership"] == "applied"


@pytest.mark.parametrize("uid,message", [
    ("", R_UID), (ADMIN["uid"], R_RESOLVE), (" " + WORKER_UID, R_RESOLVE), (WORKER_UID + "\n", R_RESOLVE),
    ("w" * 129, R_RESOLVE),
], ids=["unset", "administrator", "padded", "newline", "long"])
def test_the_workers_uid_is_set_explicit_and_never_the_administrators_before_any_read(bootstrap, uid, message):
    plane, value, _ = bootstrap(uid=uid)
    assert plane.error == message and plane.events == VERIFY and plane.bodies == [] and value["bootstrap"] == "failed"


def test_a_failed_worker_write_keeps_its_encrypted_intent_and_the_hierarchy_stays_written(bootstrap, tmp_path):
    plane = verify_plane(tmp_path)
    plane.fail = "worker"
    plane, value, outputs = bootstrap(plane)
    assert plane.error == R_WORKER_WRITE and f"Data release blocked: {R_WORKER_WRITE}." in plane.log
    assert plane.events == [*VERIFY, *READS, "backup", *HIERARCHY, "account", "worker"]
    assert (value["bootstrap"], value["worker_membership"]) == ("applied", "failed")
    assert outputs == "phase=verify\nevidence=present\n"
    assert sorted(path.name for path in (tmp_path / "release").glob("worker-membership*.encrypted.json")) == [
        "worker-membership.intent.encrypted.json"]


@pytest.mark.parametrize("answer", [
    {"errors": [{"message": "synthetic: rolled back"}]}, {"data": None}, {"data": {"organizationMember_insert": {}}},
    {"data": {"organizationMember_insert": {"organizationId": bare(ORGANIZATION), "uid": "canary-another-uid"},
              "m0": {"organizationId": bare(ORGANIZATION), "collectionId": bare(minted()[1]["id"]), "uid": WORKER_UID}}},
], ids=["refused", "no-data", "missing-keys", "another-uid"])
def test_a_refused_or_mismatched_worker_write_fails_with_its_response_retained(bootstrap, tmp_path, answer):
    plane = verify_plane(tmp_path)
    plane.answers["worker"] = answer
    plane, value, _ = bootstrap(plane, seeded="hierarchy")
    assert plane.error == R_WORKER_WRITE and plane.events[-1] == "worker" and value["worker_membership"] == "failed"
    directory = tmp_path / "release"
    assert (directory / "worker-membership.response.encrypted.json").exists()
    assert not (directory / "worker-membership.verified.encrypted.json").exists()


@pytest.mark.parametrize("change", [
    lambda plane: plane.members[-1].update(role="admin"), lambda plane: plane.members[-1].update(canViewSensitive=True),
    lambda plane: plane.owners[-1].update(active=False), lambda plane: plane.members.append(
        {**plane.members[-1], "collectionId": key_id(plane.payload, "mammals")}),
], ids=["admin", "sensitive", "inactive", "second-row"])
def test_a_worker_readback_that_is_not_exactly_the_membership_fails(bootstrap, tmp_path, change):
    plane = verify_plane(tmp_path)
    plane.after_worker = change
    plane, value, _ = bootstrap(plane, seeded="hierarchy")
    assert plane.error == R_WORKER_WRITE and plane.events == [*VERIFY, *READS, "backup", *MEMBERSHIP]
    directory = tmp_path / "release"
    assert (directory / "worker-membership.readback.encrypted.json").exists()
    assert not (directory / "worker-membership.verified.encrypted.json").exists()


def test_an_unreadable_worker_row_fails_closed_before_any_effect(bootstrap, tmp_path):
    plane = verify_plane(tmp_path)
    plane.answers["worker-read"] = HTTPFailure(403)
    plane, value, _ = bootstrap(plane, seeded="hierarchy")
    assert plane.error == R_WORKER_READ and plane.events == [*VERIFY, *READS] and value["bootstrap"] == "failed"


def test_a_self_consistent_artifact_with_the_insects_and_mammals_ids_swapped_is_refused_before_any_read(bootstrap):
    """RELEASE.md 4.5: the approved digest is the owner's, never computed from the artifact it approves."""
    original = prepare()
    swapped = prepare(minted(swap=("insects", "mammals")))
    # Self-consistent: it regenerates from its own values and carries its own matching digest, and it would make the
    # worker an operator, and the administrator an admin, in the Mammals collection's identifier.
    assert B.validate_prepared(swapped, swapped["artifact_sha256"]) == swapped
    assert PREPARED.worker_membership_request(artifact=swapped, approved_sha256=swapped["artifact_sha256"], uid=WORKER_UID,
                                              collection_keys=["insects"])["variables"]["c0"] == key_id(original, "mammals")
    plane, value, outputs = bootstrap(payload=swapped, approved=hashlib.sha256(exact(original)).hexdigest())
    assert plane.error == R_APPROVAL and f"Data release blocked: {R_APPROVAL}." in plane.log
    assert plane.events == VERIFY and plane.bodies == [] and plane.lookups == [] and value["bootstrap"] == "failed"
    assert outputs == "phase=verify\n" and PASSED not in plane.log


def test_the_digest_is_compared_in_constant_time_with_the_owner_held_value(bootstrap, monkeypatch):
    compared, real = [], hmac.compare_digest
    monkeypatch.setattr(hmac, "compare_digest", lambda left, right: compared.append((left, right)) or real(left, right))
    digest = hashlib.sha256(exact(prepare())).hexdigest()
    plane = bootstrap(seeded="both")[0]
    assert plane.error is None and compared == [(digest, digest)]


@pytest.mark.parametrize("approved,message", [
    ("", R_DIGEST), ("A" * 64, R_DIGEST), ("a" * 63, R_DIGEST), ("g" * 64, R_DIGEST), ("a" * 65, R_DIGEST),
    ("0" * 64, R_APPROVAL),
], ids=["unset", "uppercase", "short", "not-hex", "long", "another-artifact"])
def test_the_approved_digest_must_be_set_well_formed_and_equal_to_the_artifacts(bootstrap, approved, message):
    plane, value, _ = bootstrap(approved=approved)
    assert plane.error == message and plane.events == VERIFY and plane.bodies == [] and value["bootstrap"] == "failed"


def test_the_owner_held_digest_may_carry_the_approval_files_newline(bootstrap):
    plane = bootstrap(approved=hashlib.sha256(exact(prepare())).hexdigest() + "\n", seeded="both")[0]
    assert plane.error is None and plane.events == [*VERIFY, *READS, "account"]


@pytest.mark.parametrize("encoded", ["not base64 at all!", "QUJD=", "QQ", "QR==", " \n"],
                         ids=["alphabet", "padding", "unpadded", "non-canonical", "blank"])
def test_a_malformed_encoding_is_refused_before_any_read(bootstrap, encoded):
    plane, value, _ = bootstrap(encoded=encoded, approved="0" * 64)
    assert plane.error == R_BASE64 and plane.events == VERIFY and plane.bodies == [] and value["bootstrap"] == "failed"


def test_base64_wrapped_across_lines_decodes_to_the_same_approved_bytes(bootstrap):
    raw = exact(prepare())
    encoded = base64.encodebytes(raw).decode("ascii")  # 76-character lines, as GNU base64 writes them
    assert "\n" in encoded.strip()
    plane = bootstrap(encoded=encoded, seeded="both")[0]
    assert plane.error is None and plane.events == [*VERIFY, *READS, "account"]


def legacy():
    """bootstrap_admin.py's first-admin artifact: its document is the admin membership alone (PrepareFirstAdministrator)."""
    return PREPARED.prepare_bootstrap(auth_record=ADMIN, requested_email=ADMIN["email"], requested_uid=ADMIN["uid"],
                                      organization_id=ORGANIZATION, collection_id=minted()[1]["id"])


def first_scope():
    return PREPARED.prepare_first_scope(auth_record=ADMIN, requested_email=ADMIN["email"], requested_uid=ADMIN["uid"],
                                        organization_id=ORGANIZATION, collection_id=minted()[1]["id"],
                                        organization_name=NAME, collection_name="Insects")


def edited(change):
    payload = prepare()
    change(payload)
    return payload


@pytest.mark.parametrize("raw,message", [
    (b"not json\n", R_JSON),
    (b'{"schema_version": "first-scope-hierarchy-bootstrap/v1", "schema_version": "x"}\n', R_JSON),
    (b"[]\n", R_MODE),
    (exact(legacy()), R_MODE),
    (exact(first_scope()), R_MODE),
    (exact(edited(lambda p: p["request"]["variables"].update(organizationName="Edited name"))), R_REGENERATE),
    (exact(edited(lambda p: p["request"].update(query=p["request"]["query"] + " mutation { organization_deleteMany }"))),
     R_REGENERATE),
    (exact(edited(lambda p: p["hierarchy"]["collections"][3].update(id="c0ffee00-7f3a-4b1c-8d2e-0000000000dd"))),
     R_REGENERATE),
    (exact(edited(lambda p: p["request"]["variables"].update(canViewSensitive=True))), R_REGENERATE),
    (exact(edited(lambda p: p.pop("artifact_sha256"))), R_REGENERATE),
    (exact(edited(lambda p: p["hierarchy"].update(tree_sha256="0" * 64))), R_TREE),
    (exact(edited(lambda p: p["hierarchy"].update(tree_path="infra/reference/other-tree.json"))), R_TREE),
    (exact(edited(lambda p: p.pop("hierarchy"))), R_TREE),
], ids=["not-json", "duplicate-key", "not-an-object", "first-admin", "first-scope", "edited-name", "edited-query",
        "edited-identifier", "sensitive", "no-digest", "tree-digest", "tree-path", "no-hierarchy"])
def test_an_approved_artifact_that_the_release_would_not_regenerate_is_refused_before_any_read(bootstrap, raw, message):
    """The owner approves exact bytes; they must still be the hierarchy mode, bind this commit's tree and regenerate. The
    first-admin mode, whose document is the admin membership alone, is never run."""
    plane, value, _ = bootstrap(raw=raw, payload=prepare())
    assert plane.error == message and f"Data release blocked: {message}." in plane.log
    assert plane.events == VERIFY and plane.bodies == [] and plane.lookups == [] and value["bootstrap"] == "failed"


def test_a_collection_tree_edited_after_the_approval_refuses_the_run(bootstrap, monkeypatch, tmp_path):
    edited_tree = json.loads(TREE)
    edited_tree["collections"].append({"key": "meteorites", "name": "Meteorites", "parent": "geology"})
    checkout = tmp_path / "checkout"
    (checkout / PREPARED.TREE_PATH).parent.mkdir(parents=True)
    (checkout / PREPARED.TREE_PATH).write_bytes(json.dumps(edited_tree, indent=2).encode() + b"\n")
    monkeypatch.setattr(B, "ROOT", checkout)
    plane, value, _ = bootstrap()
    assert plane.error == R_TREE and plane.events == VERIFY and plane.bodies == [] and value["bootstrap"] == "failed"


def test_the_evidence_recipient_is_the_committed_public_key_pinned_by_its_digest():
    committed = B.ROOT / "infra/release/evidence-recipient.pub"
    assert module().RECIPIENT_SHA256 == PINNED == hashlib.sha256(committed.read_bytes()).hexdigest()
    release_catalog_envelope.validate_public_key(committed.read_bytes(), PINNED)
    assert module().recipient() == {"public_key_pem": committed.read_text(), "public_key_sha256": PINNED}


def test_another_committed_recipient_is_refused_before_any_read(bootstrap, monkeypatch, tmp_path):
    from test_data_initialization import catalog_recipient
    checkout = tmp_path / "recipient"
    (checkout / "infra/release").mkdir(parents=True)
    (checkout / "infra/release/evidence-recipient.pub").write_text(catalog_recipient()["public_key_pem"])
    monkeypatch.setattr(module(), "ROOT", checkout)
    plane, value, _ = bootstrap()
    assert plane.error == R_RECIPIENT and plane.events == VERIFY and plane.bodies == [] and value["bootstrap"] == "failed"


def test_the_encrypted_evidence_names_only_public_provenance_and_the_raw_records_stay_private(bootstrap):
    plane = bootstrap()[0]
    directory = bootstrap.tmp_path / "release"
    assert sorted(path.name for path in directory.glob("*.encrypted.json")) == sorted(EVIDENCE)
    secrets = private(plane.payload, exact(plane.payload))
    for name in EVIDENCE:
        text = (directory / name).read_text()
        envelope = json.loads(text)
        assert envelope["version"] == release_catalog_envelope.VERSION and envelope["public_key_sha256"] == PINNED
        assert envelope["provenance"] == {"repository": release_catalog_envelope.REPOSITORY, "source_sha": SHA,
                                          "run_id": 456, "run_attempt": 2}
        assert not any(secret in text for secret in secrets)
        assert stat.S_IMODE((directory / name.replace(".encrypted.json", ".json")).stat().st_mode) == 0o600


def test_a_failed_hierarchy_write_keeps_its_encrypted_intent_for_the_workflow_to_attest(bootstrap, tmp_path):
    plane = verify_plane(tmp_path)
    plane.fail = "hierarchy"
    plane, value, outputs = bootstrap(plane)
    assert plane.error == R_WRITE and f"Data release blocked: {R_WRITE}." in plane.log
    assert plane.events == [*VERIFY, *READS, "backup", "lookup", "tree", "hierarchy"]
    assert (value["bootstrap"], value["worker_membership"], value["backup_id"]) == ("failed", None, BACKUP_ID)
    assert outputs == "phase=verify\nevidence=present\n"
    assert [path.name for path in (tmp_path / "release").glob("*.encrypted.json")] == [EVIDENCE[0]]


@pytest.mark.parametrize("answer", [
    {"errors": [{"message": "synthetic: rolled back"}]}, {"data": None}, {"data": {}},
], ids=["refused", "no-data", "no-keys"])
def test_a_refused_or_incomplete_write_fails_with_its_response_retained(bootstrap, tmp_path, answer):
    plane = verify_plane(tmp_path)
    plane.answers["hierarchy"] = answer
    plane, value, _ = bootstrap(plane)
    assert plane.error == R_WRITE and plane.events[-1] == "hierarchy" and value["bootstrap"] == "failed"
    assert (tmp_path / "release" / EVIDENCE[1]).exists() and not (tmp_path / "release" / EVIDENCE[3]).exists()


@pytest.mark.parametrize("change", [
    lambda account: account.update(disabled=True), lambda account: account.update(emailVerified=False),
    lambda account: account.update(localId="canary-another-uid"), lambda account: account.update(tenantId="canary-tenant"),
    lambda account: account.update(email="canary-other@example.invalid"),
], ids=["disabled", "unverified", "another-uid", "tenant", "another-email"])
def test_the_administrators_account_is_read_again_just_before_the_write(bootstrap, tmp_path, change):
    plane = verify_plane(tmp_path)
    change(plane.accounts[ADMIN["email"]])
    plane, value, _ = bootstrap(plane)
    assert plane.error == R_ADMIN and plane.events == [*VERIFY, *READS, "backup", "lookup"]
    assert not any(body["query"].startswith("mutation") for body in plane.bodies) and value["bootstrap"] == "failed"


def test_an_unknown_administrator_is_refused_too(bootstrap, tmp_path):
    plane = verify_plane(tmp_path)
    plane.accounts.clear()
    plane = bootstrap(plane)[0]
    assert plane.error == R_ADMIN and plane.events[-1] == "lookup"


def test_an_unreadable_administrator_account_stops_before_the_write(bootstrap, tmp_path):
    plane = verify_plane(tmp_path)
    plane.answers["lookup"] = HTTPFailure(403)
    plane, value, _ = bootstrap(plane)
    assert plane.error == "the administrator's account could not be read" and plane.events[-1] == "lookup"
    assert not any(body["query"].startswith("mutation") for body in plane.bodies) and value["bootstrap"] == "failed"


@pytest.mark.parametrize("answer", [
    HTTPFailure(403), {"errors": [{"message": "denied"}]}, {"data": {"organization": None}},
    {"data": {**dict.fromkeys(("collections", "matchingCollections", "organizationMembers", "members"), []),
              "organization": None, "extra": []}},
], ids=["window-closed", "graphql-error", "incomplete", "unexpected-field"])
def test_an_unreadable_organization_fails_closed_before_any_effect(bootstrap, tmp_path, answer):
    plane = verify_plane(tmp_path)
    plane.answers["scope"] = answer
    plane, value, _ = bootstrap(plane)
    assert plane.error == R_READ and plane.events == [*VERIFY, "scope"] and value["bootstrap"] == "failed"


def test_a_write_needs_point_in_time_recovery_like_an_apply(bootstrap, tmp_path):
    plane = verify_plane(tmp_path)
    plane.live["sql", f"projects/{D.PROJECT}/instances/{D.SOURCE}"]["settings"]["backupConfiguration"].update(
        pointInTimeRecoveryEnabled=False)
    plane, value, _ = bootstrap(plane)
    assert plane.error == PITR and plane.events == [*VERIFY, *READS] and value["bootstrap"] == "failed"


def test_without_an_artifact_the_release_reads_no_row_and_says_so(released, tmp_path, monkeypatch):
    monkeypatch.setenv(APPROVED, "0" * 64)  # a digest or a UID alone starts nothing
    monkeypatch.setenv(WORKER, WORKER_UID)
    plane = verify_plane(tmp_path)
    value, outputs = released(plane)
    assert plane.error is None and plane.events == VERIFY and ABSENT in plane.log and outputs == "phase=verify\n"
    assert value == receipt("verify", tables=1, views=0) and value["bootstrap"] is value["worker_membership"] is None


def test_a_release_that_fails_before_the_bootstrap_never_reads_the_artifact(bootstrap, tmp_path, monkeypatch):
    for owner, name in ((base64, "b64decode"), (base64, "standard_b64decode"), (base64, "decodebytes"),
                        (binascii, "a2b_base64")):
        monkeypatch.setattr(owner, name, lambda *args, **kwargs: pytest.fail("the artifact stays unread"))
    plane = verify_plane(tmp_path)
    plane.fail = "indexed"
    plane, value, _ = bootstrap(plane)
    assert plane.error == "the supplemental index inventory could not be read" and value["bootstrap"] is None


def test_only_the_reviewed_documents_are_sent_and_never_the_admin_membership_document(bootstrap):
    plane = bootstrap()[0]
    queries = [body["query"] for body in plane.bodies]
    assert queries == [module().READ_SCOPE, module().READ_WORKER, B.READ_FIRST_SCOPE_HIERARCHY,
                       plane.payload["request"]["query"], B.READ_FIRST_SCOPE_HIERARCHY,
                       PREPARED.worker_membership_mutation(1), module().READ_WORKER]
    assert PREPARED.BOOTSTRAP_MUTATION not in queries and not any("PrepareFirstAdministrator" in query for query in queries)
    # The hierarchy's mutation is the reviewed tree's, regenerated rather than trusted; the worker's writes only operator
    # rows without sensitive access, as literals.
    assert queries[3] == PREPARED.hierarchy_mutation(parents(plane.payload))
    assert 'role: "operator", canViewSensitive: false' in queries[5] and '"admin"' not in queries[5]
    read = plane.bodies[0]["variables"]
    assert read["limit"] == 19 and read["organizationId"] == ORGANIZATION and len(read["ids"]) == 18
    assert plane.bodies[1]["variables"] == {"organizationId": ORGANIZATION, "uid": WORKER_UID, "limit": 2}


def test_the_gate_path_never_names_the_admin_membership_document():
    source = (B.ROOT / "scripts/ci/release_bootstrap.py").read_text()
    for name in ("BOOTSTRAP_MUTATION", "prepare_bootstrap", "PrepareFirstAdministrator", "FIRST_SCOPE_MUTATION"):
        assert name not in source


def test_the_owners_summarize_approval_is_exactly_what_the_release_accepts(bootstrap, tmp_path, monkeypatch):
    """scripts/data/hierarchy_approval.py summarize writes the approval the release compares, and nothing recomputes it:
    the same file approves only the bytes it summarized, never the swapped artifact."""
    spec = importlib.util.spec_from_file_location("hierarchy_approval_for_release",
                                                  B.ROOT / "scripts/data/hierarchy_approval.py")
    approval = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(approval)
    private_directory = tmp_path / "owner"
    private_directory.mkdir(mode=0o700)
    private_directory.chmod(0o700)
    artifact = private_directory / "hierarchy-artifact.json"
    PREPARED.write_private_artifact(artifact, prepare())
    monkeypatch.setattr("sys.stdin", io.StringIO("APPROVE\n"))
    assert approval.main(["summarize", str(artifact)]) == 0
    digest = (private_directory / "hierarchy-approval.sha256").read_text()
    plane = bootstrap(raw=artifact.read_bytes(), approved=digest, seeded="both")[0]
    assert plane.error is None and plane.events == [*VERIFY, *READS, "account"]
    swapped = prepare(minted(swap=("insects", "mammals")))
    plane = bootstrap(payload=swapped, approved=digest, directory="swapped")[0]
    assert plane.error == R_APPROVAL and plane.bodies == []
