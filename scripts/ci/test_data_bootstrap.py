"""The bootstrap on the data gate path (RELEASE.md 4.5, T3e): the owner-approved hierarchy, after verify or apply.

Artifacts are prepared from the committed collection tree with synthetic identifiers and identities; Google's replies are
synthetic, over test_data_apply's Cloud. Never network, credentials or cloud.
"""
import base64
import binascii
import copy
import hashlib
import hmac
import importlib
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
PINNED = "2f7736623899622da19cac0bc8e9447aa7049b90776fd1b32cf9ba0283defbcc"  # pragma: allowlist secret (public key digest)
ARTIFACT, APPROVED = "DATA_BOOTSTRAP_ARTIFACT_B64", "DATA_BOOTSTRAP_APPROVED_SHA256"
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
PASSED = "Bootstrap: the approved artifact passed its checks."
WRITTEN = "Bootstrap: the organization's rows were written and read back."
MATCHED = "Bootstrap: the organization's rows already match the approved artifact; nothing is written."
ABSENT = "No bootstrap artifact is set; the bootstrap is skipped."
VERIFY = ["migrated", "indexed"]
WRITE = ["lookup", "tree", "hierarchy", "tree"]
EVIDENCE = [f"first-scope-hierarchy.{name}.encrypted.json" for name in ("intent", "response", "readback", "verified")]


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


def private(payload, raw):
    """Every private value the artifact holds or the secrets carry, with SQL Connect's unhyphenated UUIDs too."""
    variables = payload["request"]["variables"]
    values = {variables["organizationId"], variables["organizationName"], variables["uid"], ADMIN["email"],
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
        self.bodies, self.lookups, self.answers = [], [], {}

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
                        "mutation PrepareFirstScopeHierarchy": self.hierarchy}
            assert operation in handlers, "only the reviewed documents are ever sent"
            assert resource == B.SERVICE + (":executeGraphql" if operation.startswith("mutation") else ":executeGraphqlRead")
            return handlers[operation](body)
        return super().request(api, method, resource, body=body, params=params, missing=missing, diff=diff)

    def lookup(self, body):
        assert set(body) == {"email"} and len(body["email"]) == 1
        users = [self.accounts[email] for email in body["email"] if email in self.accounts]
        return self.reply("lookup", {"kind": "identitytoolkit#GetAccountInfoResponse", **({"users": users} if users else {})})

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
            "members": [{"uid": row["uid"], "collectionId": bare(row["collectionId"]), "active": row["active"],
                         "role": row["role"], "canViewSensitive": row["canViewSensitive"]} for row in self.members
                        if same(row["organizationId"], organization)][:member_limit]}}

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


@pytest.fixture
def bootstrap(released, monkeypatch, tmp_path):
    """The release with the owner's two secrets set: the artifact's base64 and the digest the owner approved (by default
    the artifact's own bytes'), over a Plane on verify (the merged files live) or apply (test_data_apply's default).
    Every exit keeps the log, the receipt and the step output free of the artifact's private values."""
    def run(plane=None, *, phase="verify", payload=None, raw=None, encoded=None, approved=None, seeded=False,
            directory="release"):
        payload = prepare() if payload is None else payload
        raw = exact(payload) if raw is None else raw
        if plane is None:
            plane = (Plane(tmp_path / directory, payload, MERGED, rules=RULES) if phase == "verify"
                     else Plane(tmp_path / directory, payload))
        if seeded:
            seed(plane, payload)
        monkeypatch.setenv(ARTIFACT, base64.b64encode(raw).decode("ascii") if encoded is None else encoded)
        monkeypatch.setenv(APPROVED, hashlib.sha256(raw).hexdigest() if approved is None else approved)
        value, outputs = released(plane, directory)
        assert not [secret for secret in private(payload, raw) for text in (plane.log, json.dumps(value), outputs)
                    if secret in text], "a private value reached the log, the receipt or a step output"
        return plane, value, outputs
    run.tmp_path = tmp_path
    return run


def verify_plane(tmp_path, payload=None):
    return Plane(tmp_path / "release", prepare() if payload is None else payload, MERGED, rules=RULES)


def test_after_verify_the_approved_hierarchy_is_backed_up_then_written_once_and_read_back(bootstrap):
    plane, value, outputs = bootstrap()
    assert plane.error is None and plane.events == [*VERIFY, "scope", "backup", *WRITE]
    assert value == receipt("verify", tables=1, views=0, backup_id=BACKUP_ID, bootstrap="applied")
    assert outputs == "phase=verify\nevidence=present\n"
    assert PASSED in plane.log and WRITTEN in plane.log and "Data release blocked" not in plane.log
    # The administrator's account is read again first; the rows are exactly the approved ones.
    assert plane.lookups == [{"email": [ADMIN["email"]]}]
    assert plane.organization == {"id": ORGANIZATION, "name": NAME} and len(plane.collections) == 18
    assert [(row["uid"], row["role"], row["canViewSensitive"]) for row in plane.members] == [(ADMIN["uid"], "admin", False)]


def test_after_an_apply_the_bootstrap_uses_the_applys_backup_and_takes_no_second_one(bootstrap):
    plane, value, outputs = bootstrap(phase="apply")
    assert plane.error is None and plane.events == [*ORDER, "scope", *WRITE] and plane.events.count("backup") == 1
    assert value == receipt(**APPLIED, bootstrap="applied") and outputs == "phase=apply\nevidence=present\n"


def test_rows_that_already_match_exactly_are_verified_and_nothing_is_backed_up_or_written(bootstrap):
    plane, value, outputs = bootstrap(seeded=True)
    assert plane.error is None and plane.events == [*VERIFY, "scope"] and plane.lookups == []
    assert value == receipt("verify", tables=1, views=0, bootstrap="verified")
    assert outputs == "phase=verify\n" and PASSED in plane.log and MATCHED in plane.log
    directory = bootstrap.tmp_path / "release"
    assert not list(directory.glob("first-scope-*")) and not (directory / "release-backup.json").exists()


def test_a_re_run_after_a_written_bootstrap_verifies_and_writes_nothing(bootstrap):
    plane = bootstrap()[0]
    plane.events, plane.packet = [], {**plane.packet, "release_run_attempt": 3}
    plane.path = bootstrap.tmp_path / "rerun" / "packet.json"
    plane, value, _ = bootstrap(plane, directory="rerun")
    assert plane.error is None and plane.events == [*VERIFY, "scope"] and value["bootstrap"] == "verified"
    assert sum(body["query"].startswith("mutation") for body in plane.bodies) == 1


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
    assert plane.events == [*VERIFY, "scope"] and plane.lookups == [] and value["bootstrap"] == "failed"
    assert value["backup_id"] is None and outputs == "phase=verify\n"


def test_a_self_consistent_artifact_with_the_insects_and_mammals_ids_swapped_is_refused_before_any_read(bootstrap):
    """RELEASE.md 4.5: the approved digest is the owner's, never computed from the artifact it approves."""
    original = prepare()
    swapped = prepare(minted(swap=("insects", "mammals")))
    ids = {entry["key"]: entry["id"] for entry in swapped["hierarchy"]["collections"]}
    was = {entry["key"]: entry["id"] for entry in original["hierarchy"]["collections"]}
    # Self-consistent: it regenerates from its own values and carries its own matching digest, and it would put the
    # administrator, and the pilot's work, into the Mammals collection's identifier.
    assert B.validate_prepared(swapped, swapped["artifact_sha256"]) == swapped
    assert swapped["request"]["variables"]["collectionId"] == ids["insects"] == was["mammals"]
    plane, value, outputs = bootstrap(payload=swapped, approved=hashlib.sha256(exact(original)).hexdigest())
    assert plane.error == R_APPROVAL and f"Data release blocked: {R_APPROVAL}." in plane.log
    assert plane.events == VERIFY and plane.bodies == [] and plane.lookups == [] and value["bootstrap"] == "failed"
    assert outputs == "phase=verify\n" and PASSED not in plane.log


def test_the_digest_is_compared_in_constant_time_with_the_owner_held_value(bootstrap, monkeypatch):
    compared, real = [], hmac.compare_digest
    monkeypatch.setattr(hmac, "compare_digest", lambda left, right: compared.append((left, right)) or real(left, right))
    digest = hashlib.sha256(exact(prepare())).hexdigest()
    plane = bootstrap(seeded=True)[0]
    assert plane.error is None and compared == [(digest, digest)]


@pytest.mark.parametrize("approved,message", [
    ("", R_DIGEST), ("A" * 64, R_DIGEST), ("a" * 63, R_DIGEST), ("g" * 64, R_DIGEST), ("a" * 65, R_DIGEST),
    ("0" * 64, R_APPROVAL),
], ids=["unset", "uppercase", "short", "not-hex", "long", "another-artifact"])
def test_the_approved_digest_must_be_set_well_formed_and_equal_to_the_artifacts(bootstrap, approved, message):
    plane, value, _ = bootstrap(approved=approved)
    assert plane.error == message and plane.events == VERIFY and plane.bodies == [] and value["bootstrap"] == "failed"


def test_the_owner_held_digest_may_carry_the_approval_files_newline(bootstrap):
    plane = bootstrap(approved=hashlib.sha256(exact(prepare())).hexdigest() + "\n", seeded=True)[0]
    assert plane.error is None and plane.events == [*VERIFY, "scope"]


@pytest.mark.parametrize("encoded", ["not base64 at all!", "QUJD=", "QQ", "QR==", " \n"],
                         ids=["alphabet", "padding", "unpadded", "non-canonical", "blank"])
def test_a_malformed_encoding_is_refused_before_any_read(bootstrap, encoded):
    plane, value, _ = bootstrap(encoded=encoded, approved="0" * 64)
    assert plane.error == R_BASE64 and plane.events == VERIFY and plane.bodies == [] and value["bootstrap"] == "failed"


def test_base64_wrapped_across_lines_decodes_to_the_same_approved_bytes(bootstrap):
    raw = exact(prepare())
    encoded = base64.encodebytes(raw).decode("ascii")  # 76-character lines, as GNU base64 writes them
    assert "\n" in encoded.strip()
    plane = bootstrap(encoded=encoded, seeded=True)[0]
    assert plane.error is None and plane.events == [*VERIFY, "scope"]


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


def test_a_failed_write_keeps_its_encrypted_intent_for_the_workflow_to_attest(bootstrap, tmp_path):
    plane = verify_plane(tmp_path)
    plane.fail = "hierarchy"
    plane, value, outputs = bootstrap(plane)
    assert plane.error == R_WRITE and f"Data release blocked: {R_WRITE}." in plane.log
    assert plane.events == [*VERIFY, "scope", "backup", "lookup", "tree", "hierarchy"] and value["bootstrap"] == "failed"
    assert value["backup_id"] == BACKUP_ID and outputs == "phase=verify\nevidence=present\n"
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
    assert plane.error == R_ADMIN and plane.events == [*VERIFY, "scope", "backup", "lookup"]
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
    assert plane.error == PITR and plane.events == [*VERIFY, "scope"] and value["bootstrap"] == "failed"


def test_without_an_artifact_the_release_reads_no_row_and_says_so(released, tmp_path, monkeypatch):
    monkeypatch.setenv(APPROVED, "0" * 64)  # a digest alone starts nothing
    plane = verify_plane(tmp_path)
    value, outputs = released(plane)
    assert plane.error is None and plane.events == VERIFY and ABSENT in plane.log and outputs == "phase=verify\n"
    assert value == receipt("verify", tables=1, views=0) and value["bootstrap"] is None


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
    assert queries == [module().READ_SCOPE, B.READ_FIRST_SCOPE_HIERARCHY, plane.payload["request"]["query"],
                       B.READ_FIRST_SCOPE_HIERARCHY]
    assert PREPARED.BOOTSTRAP_MUTATION not in queries and not any("PrepareFirstAdministrator" in query for query in queries)
    # The one mutation is the reviewed tree's, regenerated rather than trusted.
    assert queries[2] == PREPARED.hierarchy_mutation(parents(plane.payload))
    read = plane.bodies[0]["variables"]
    assert read["limit"] == 19 and read["organizationId"] == ORGANIZATION and len(read["ids"]) == 18
