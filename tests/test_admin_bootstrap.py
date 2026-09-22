"""Offline identity validation and private artifact tests; no Firebase access."""

import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import sys

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/data/bootstrap_admin.py"
SPEC = importlib.util.spec_from_file_location("bootstrap_admin", MODULE_PATH)
assert SPEC and SPEC.loader
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)

HELPER_PATH = MODULE_PATH.with_name("prepare_hierarchy_request.py")
HELPER_SPEC = importlib.util.spec_from_file_location("prepare_hierarchy_request", HELPER_PATH)
assert HELPER_SPEC and HELPER_SPEC.loader
helper = importlib.util.module_from_spec(HELPER_SPEC)
HELPER_SPEC.loader.exec_module(helper)


@pytest.fixture
def inputs():
    return {
        "auth_record": {
            "uid": "synthetic-admin",
            "email": "synthetic@example.invalid",
            "emailVerified": True,
            "disabled": False,
            "private_extra": "must-not-be-copied",
        },
        "requested_uid": "synthetic-admin",
        "requested_email": "synthetic@example.invalid",
        "organization_id": "11111111-1111-4111-8111-111111111111",
        "collection_id": "22222222-2222-4222-8222-222222222222",
    }


def test_prepares_transaction_with_explicit_scope_and_no_sensitive_default(inputs):
    artifact = bootstrap.prepare_bootstrap(**inputs)
    assert artifact["state"] == "prepared_not_applied"
    assert artifact["request"]["variables"] == {
        "organizationId": inputs["organization_id"],
        "collectionId": inputs["collection_id"],
        "uid": inputs["requested_uid"],
        "canViewSensitive": False,
    }
    assert "must-not-be-copied" not in json.dumps(artifact)
    assert artifact == bootstrap.prepare_bootstrap(**inputs)
    inputs["can_view_sensitive"] = True
    assert bootstrap.prepare_bootstrap(**inputs)["artifact_sha256"] != artifact["artifact_sha256"]


@pytest.mark.parametrize(
    ("field", "value"),
    [("uid", "different"), ("email", "Synthetic@example.invalid"),
     ("emailVerified", False), ("emailVerified", 1), ("disabled", True), ("disabled", 0)],
)
def test_auth_record_must_match_exact_verified_enabled_account(inputs, field, value):
    inputs["auth_record"][field] = value
    with pytest.raises(ValueError):
        bootstrap.prepare_bootstrap(**inputs)


@pytest.mark.parametrize("field", ["uid", "email", "emailVerified", "disabled"])
def test_missing_auth_claim_is_denied(inputs, field):
    del inputs["auth_record"][field]
    with pytest.raises(ValueError):
        bootstrap.prepare_bootstrap(**inputs)


@pytest.mark.parametrize(
    ("field", "value"),
    [("requested_uid", ""), ("requested_uid", " space"),
     ("requested_email", ""), ("requested_email", "bad"),
     ("organization_id", "unknown"), ("collection_id", None),
     ("can_view_sensitive", "false"), ("can_view_sensitive", 1)],
)
def test_no_guessed_or_coerced_inputs(inputs, field, value):
    inputs[field] = value
    with pytest.raises(ValueError):
        bootstrap.prepare_bootstrap(**inputs)


def test_private_artifact_exclusive_and_outside_git(inputs, tmp_path):
    tmp_path.chmod(0o700)
    output = tmp_path / "private.json"
    artifact = bootstrap.prepare_bootstrap(**inputs)
    bootstrap.write_private_artifact(output, artifact)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text()) == artifact
    with pytest.raises(FileExistsError):
        bootstrap.write_private_artifact(output, artifact)
    (tmp_path / "alias.json").symlink_to(output)
    with pytest.raises(FileExistsError):
        bootstrap.write_private_artifact(tmp_path / "alias.json", artifact)
    (tmp_path / ".git").write_text("gitdir: fake")
    with pytest.raises(ValueError, match="outside Git"):
        bootstrap.write_private_artifact(tmp_path / "new.json", artifact)


def test_private_artifact_rejects_public_directory(inputs, tmp_path):
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError, match="mode0700"):
        bootstrap.write_private_artifact(tmp_path / "private.json", bootstrap.prepare_bootstrap(**inputs))


def test_bootstrap_not_published_as_runtime_operation():
    connector = MODULE_PATH.parents[2] / "dataconnect/connector"
    assert all("PrepareFirstAdministrator" not in path.read_text() for path in connector.glob("*.gql"))


@pytest.mark.parametrize("input_name", ["request", "auth-record"])
@pytest.mark.parametrize("unsafe", ["public", "symlink", "git"])
def test_bootstrap_cli_rejects_unsafe_private_inputs(inputs, tmp_path, monkeypatch, capsys, input_name, unsafe):
    tmp_path.chmod(0o700)
    request = dict(inputs)
    auth = request.pop("auth_record")
    paths = {"request": tmp_path / "request.json", "auth-record": tmp_path / "auth.json"}
    for key, payload in [("request", request), ("auth-record", auth)]:
        paths[key].write_text(json.dumps(payload))
        paths[key].chmod(0o600)
    target = paths[input_name]
    if unsafe == "public":
        target.chmod(0o644)
    elif unsafe == "symlink":
        alias = tmp_path / "alias.json"
        alias.symlink_to(target)
        paths[input_name] = alias
    else:
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        (checkout / ".git").write_text("gitdir: synthetic")
        target.rename(checkout / target.name)
        paths[input_name] = checkout / target.name
    output = tmp_path / "prepared.json"
    monkeypatch.setattr(sys, "argv", ["bootstrap_admin.py", "--request", str(paths["request"]),
                                    "--auth-record", str(paths["auth-record"]), "--output", str(output)])
    with pytest.raises(SystemExit) as error:
        bootstrap.main()
    assert error.value.code == 2
    assert not output.exists()
    captured = capsys.readouterr()
    assert "synthetic-admin" not in captured.out + captured.err


# ------------------------------------------------------- reviewed tree mode ---


SYNTHETIC_TREE = [
    {"key": "zoology", "name": "Zoology", "parent": None},
    {"key": "insects", "name": "Insects", "parent": "zoology"},
    {"key": "botany", "name": "Botany", "parent": None},
]
SYNTHETIC_IDS = ["11111111-1111-4111-8111-11111111111" + digit for digit in "123"]


def tree_bytes(entries=None):
    return json.dumps({"schema_version": "collection-tree/v1", "recorded": "2026-09-22",
                       "source": "synthetic", "collections": SYNTHETIC_TREE if entries is None else entries},
                      indent=2).encode() + b"\n"


def collections(entries=None):
    source = SYNTHETIC_TREE if entries is None else entries
    return [{"key": entry["key"], "id": identifier, "name": entry["name"], "parent": entry["parent"]}
            for entry, identifier in zip(source, SYNTHETIC_IDS)]


@pytest.fixture
def hierarchy(inputs):
    return {
        "auth_record": inputs["auth_record"],
        "requested_uid": inputs["requested_uid"],
        "requested_email": inputs["requested_email"],
        "organization_id": inputs["organization_id"],
        "organization_name": "Synthetic Museum",
        "collections": collections(),
        "admin_collection_key": "insects",
        "tree": tree_bytes(),
    }


def test_hierarchy_prepares_one_transaction_for_the_whole_reviewed_tree(hierarchy):
    artifact = bootstrap.prepare_first_scope_hierarchy(**hierarchy)
    assert artifact["schema_version"] == "first-scope-hierarchy-bootstrap/v1"
    assert artifact["state"] == "prepared_not_applied"
    assert "must-not-be-copied" not in json.dumps(artifact)
    assert artifact["request"]["variables"] == {
        "organizationId": hierarchy["organization_id"],
        # The administrator's collection keeps the existing variable name.
        "collectionId": SYNTHETIC_IDS[1],
        "uid": hierarchy["requested_uid"],
        "canViewSensitive": False,
        "organizationName": "Synthetic Museum",
        "c0Id": SYNTHETIC_IDS[0], "c0Name": "Zoology",
        "c1Id": SYNTHETIC_IDS[1], "c1Name": "Insects",
        "c2Id": SYNTHETIC_IDS[2], "c2Name": "Botany",
    }
    query = artifact["request"]["query"]
    assert "matchingCollections: collections(where: {id: {in: [$c0Id, $c1Id, $c2Id]}}, limit: 1)" in query
    assert "c0: collection_insert(data: {organizationId: $organizationId, id: $c0Id,\n" \
           "    name: $c0Name, parentId: null})" in query
    assert "c1: collection_insert(data: {organizationId: $organizationId, id: $c1Id,\n" \
           "    name: $c1Name, parentId: $c0Id})" in query
    assert query.count("collection_insert") == 3
    assert artifact["hierarchy"] == {
        "tree_path": "infra/reference/fieldmuseum-collection-tree.json",
        "tree_sha256": hashlib.sha256(hierarchy["tree"]).hexdigest(),
        "collections": hierarchy["collections"],
        "admin_collection_key": "insects",
    }
    assert artifact == bootstrap.prepare_first_scope_hierarchy(**hierarchy)


def test_hierarchy_binds_the_committed_tree_by_its_exact_bytes(hierarchy):
    root = MODULE_PATH.parents[2]
    committed = (root / bootstrap.TREE_PATH).read_bytes()
    entries = bootstrap.tree_entries(committed)
    assert len(entries) == 18 and entries[0]["key"] == "zoology"
    artifact = bootstrap.prepare_first_scope_hierarchy(**{
        **hierarchy, "tree": committed,
        "collections": [{"key": entry["key"], "id": f"00000000-0000-4000-8000-0000000{index:05x}",
                         "name": entry["name"], "parent": entry["parent"]}
                        for index, entry in enumerate(entries, start=1)]})
    assert artifact["hierarchy"]["tree_sha256"] == hashlib.sha256(committed).hexdigest()
    assert artifact["request"]["query"].count("collection_insert") == 18


@pytest.mark.parametrize("change", ["name", "key", "parent", "order", "extra", "short"])
def test_private_collections_must_repeat_the_reviewed_tree_exactly(hierarchy, change):
    rows = collections()
    if change == "name":
        rows[1]["name"] = "Beetles"
    elif change == "key":
        rows[1]["key"] = "bugs"
    elif change == "parent":
        rows[1]["parent"] = None
    elif change == "order":
        rows[0], rows[2] = rows[2], rows[0]
    elif change == "extra":
        rows.append({"key": "fungi", "id": "22222222-2222-4222-8222-222222222222",
                     "name": "Fungi", "parent": "botany"})
    else:
        rows.pop()
    with pytest.raises(ValueError):
        bootstrap.prepare_first_scope_hierarchy(**{**hierarchy, "collections": rows})


def test_a_parent_after_its_child_is_refused(hierarchy):
    reordered = [SYNTHETIC_TREE[1], SYNTHETIC_TREE[0], SYNTHETIC_TREE[2]]
    rows = collections(reordered)
    with pytest.raises(ValueError, match="earlier"):
        bootstrap.prepare_first_scope_hierarchy(
            **{**hierarchy, "collections": rows, "tree": tree_bytes(reordered)})


@pytest.mark.parametrize("change", ["id", "name", "key"])
def test_duplicate_identifier_sibling_name_or_key_is_refused(hierarchy, change):
    rows = collections()
    if change == "id":
        rows[2]["id"] = rows[0]["id"]
    elif change == "name":
        rows[2]["name"] = "Zoology"
    else:
        rows[2]["key"] = "zoology"
    entries = [{"key": row["key"], "name": row["name"], "parent": row["parent"]} for row in rows]
    with pytest.raises(ValueError):
        bootstrap.prepare_first_scope_hierarchy(
            **{**hierarchy, "collections": rows, "tree": tree_bytes(entries)})


def test_the_same_name_under_two_different_parents_is_allowed(hierarchy):
    entries = SYNTHETIC_TREE + [{"key": "fungi", "name": "Insects", "parent": "botany"}]
    rows = collections(entries)
    rows.append({"key": "fungi", "id": "44444444-4444-4444-8444-444444444444",
                 "name": "Insects", "parent": "botany"})
    artifact = bootstrap.prepare_first_scope_hierarchy(
        **{**hierarchy, "collections": rows, "tree": tree_bytes(entries)})
    assert artifact["request"]["variables"]["c3Name"] == "Insects"


@pytest.mark.parametrize("value", ["", "unknown", None, "Insects"])
def test_unknown_administrator_collection_key_is_refused(hierarchy, value):
    with pytest.raises(ValueError, match="administrator"):
        bootstrap.prepare_first_scope_hierarchy(**{**hierarchy, "admin_collection_key": value})


@pytest.mark.parametrize("field,value", [
    ("organization_id", "unknown"), ("organization_name", ""), ("organization_name", " padded "),
    ("organization_name", "bad\nname"), ("can_view_sensitive", True), ("can_view_sensitive", 1),
    ("tree", "not-bytes"), ("tree", b"{}"), ("tree", b'{"schema_version": "other", "collections": []}'),
    ("collections", []), ("collections", {}),
])
def test_no_guessed_hierarchy_inputs(hierarchy, field, value):
    with pytest.raises(ValueError):
        bootstrap.prepare_first_scope_hierarchy(**{**hierarchy, field: value})


@pytest.mark.parametrize("bad", ["not-a-uuid", "11111111111141118111111111111111", None, 5])
def test_every_collection_identifier_must_be_a_canonical_uuid(hierarchy, bad):
    rows = collections()
    rows[1]["id"] = bad
    with pytest.raises(ValueError):
        bootstrap.prepare_first_scope_hierarchy(**{**hierarchy, "collections": rows})


def test_a_collection_row_must_carry_exactly_the_four_reviewed_fields(hierarchy):
    rows = collections()
    rows[0] = {**rows[0], "notes": "unreviewed"}
    with pytest.raises(ValueError, match="exactly"):
        bootstrap.prepare_first_scope_hierarchy(**{**hierarchy, "collections": rows})


def test_more_than_sixty_four_collections_is_refused(hierarchy):
    entries = [{"key": f"k{index}", "name": f"Collection {index}", "parent": None} for index in range(65)]
    rows = [{"key": entry["key"], "id": f"00000000-0000-4000-8000-0000000{index:05x}",
             "name": entry["name"], "parent": None} for index, entry in enumerate(entries, start=1)]
    with pytest.raises(ValueError, match="64"):
        bootstrap.prepare_first_scope_hierarchy(
            **{**hierarchy, "collections": rows, "tree": tree_bytes(entries),
               "admin_collection_key": "k0"})


def test_hierarchy_mode_is_not_published_as_a_runtime_operation():
    connector = MODULE_PATH.parents[2] / "dataconnect/connector"
    assert all("PrepareFirstScopeHierarchy" not in path.read_text() for path in connector.glob("*.gql"))


def private_request(tmp_path, hierarchy, name="request.json"):
    request = {key: hierarchy[key] for key in
               ("requested_uid", "requested_email", "organization_id", "organization_name",
                "collections", "admin_collection_key")}
    path = tmp_path / name
    path.write_text(json.dumps(request))
    path.chmod(0o600)
    return path


def test_hierarchy_cli_writes_the_exact_artifact_and_refuses_both_modes(hierarchy, tmp_path, monkeypatch, capsys):
    tmp_path.chmod(0o700)
    request = private_request(tmp_path, hierarchy)
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps(hierarchy["auth_record"]))
    auth.chmod(0o600)
    tree = tmp_path / "tree.json"
    tree.write_bytes(hierarchy["tree"])
    output = tmp_path / "prepared.json"
    arguments = ["bootstrap_admin.py", "--request", str(request), "--auth-record", str(auth),
                 "--output", str(output), "--tree", str(tree)]
    monkeypatch.setattr(sys, "argv", arguments + ["--hierarchy", "--first-scope"])
    with pytest.raises(SystemExit) as error:
        bootstrap.main()
    assert error.value.code == 2
    assert "not allowed with" in capsys.readouterr().err
    assert not output.exists()
    monkeypatch.setattr(sys, "argv", arguments + ["--hierarchy"])
    assert bootstrap.main() == 0
    assert json.loads(output.read_bytes()) == bootstrap.prepare_first_scope_hierarchy(**hierarchy)


def test_hierarchy_cli_without_its_flag_refuses_the_hierarchy_request(hierarchy, tmp_path, monkeypatch, capsys):
    tmp_path.chmod(0o700)
    request = private_request(tmp_path, hierarchy)
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps(hierarchy["auth_record"]))
    auth.chmod(0o600)
    output = tmp_path / "prepared.json"
    monkeypatch.setattr(sys, "argv", ["bootstrap_admin.py", "--request", str(request),
                                      "--auth-record", str(auth), "--output", str(output)])
    with pytest.raises(SystemExit) as error:
        bootstrap.main()
    assert error.value.code == 2
    assert not output.exists()
    assert "synthetic-admin" not in "".join(capsys.readouterr())


def test_helper_mints_one_canonical_uuid_per_reviewed_entry_and_prepares(tmp_path, inputs):
    tmp_path.chmod(0o700)
    tree = tmp_path / "tree.json"
    tree.write_bytes(tree_bytes())
    output = tmp_path / "request.json"
    arguments = ["prepare_hierarchy_request.py", "--tree", str(tree),
                 "--organization-name", "Synthetic Museum",
                 "--requested-email", inputs["requested_email"],
                 "--requested-uid", inputs["requested_uid"],
                 "--admin-collection-key", "insects", "--output", str(output)]
    import sys as system
    system.argv = arguments
    assert helper.main() == 0
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    request = json.loads(output.read_bytes())
    assert set(request) == {"requested_email", "requested_uid", "organization_id",
                            "organization_name", "collections", "admin_collection_key"}
    minted = [row["id"] for row in request["collections"]]
    assert len(set(minted)) == 3 and request["organization_id"] not in minted
    assert [(row["key"], row["name"], row["parent"]) for row in request["collections"]] == [
        (entry["key"], entry["name"], entry["parent"]) for entry in SYNTHETIC_TREE]
    # The skeleton is exactly what the preparer accepts, with no further editing.
    artifact = bootstrap.prepare_first_scope_hierarchy(
        auth_record=inputs["auth_record"], tree=tree_bytes(), **request)
    assert artifact["schema_version"] == "first-scope-hierarchy-bootstrap/v1"


def test_helper_keeps_a_fixed_organization_id_and_refuses_an_unknown_key(tmp_path):
    fixed = "99999999-9999-4999-8999-999999999999"
    request = helper.build_request(
        tree=tree_bytes(), organization_name="Synthetic Museum", organization_id=fixed,
        requested_email="synthetic@example.invalid", requested_uid="synthetic-admin",
        admin_collection_key="botany")
    assert request["organization_id"] == fixed
    with pytest.raises(ValueError, match="administrator"):
        helper.build_request(
            tree=tree_bytes(), organization_name="Synthetic Museum",
            requested_email="synthetic@example.invalid", requested_uid="synthetic-admin",
            admin_collection_key="unknown")


def test_helper_refuses_a_public_output_directory_and_makes_no_partial_file(tmp_path):
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError, match="mode0700"):
        helper._admin.write_private_artifact(tmp_path / "request.json", helper.build_request(
            tree=tree_bytes(), organization_name="Synthetic Museum",
            requested_email="synthetic@example.invalid", requested_uid="synthetic-admin",
            admin_collection_key="insects"))
    assert not (tmp_path / "request.json").exists()


def test_bootstrap_cli_accepts_private_regular_inputs(inputs, tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    request = dict(inputs)
    auth = request.pop("auth_record")
    for name, value in [("request", request), ("auth", auth)]:
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(value))
        path.chmod(0o600)
    output = tmp_path / "prepared.json"
    monkeypatch.setattr(sys, "argv", ["bootstrap_admin.py", "--request", str(tmp_path / "request.json"),
                                    "--auth-record", str(tmp_path / "auth.json"), "--output", str(output)])
    assert bootstrap.main() == 0
    assert json.loads(output.read_bytes())["state"] == "prepared_not_applied"
