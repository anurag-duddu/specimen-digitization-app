"""Actual hardened source gate and native connector over an offline SQL transport.

These controls neither open a database nor stand in for a live readback.
"""
import copy
import json
from pathlib import Path
import shutil

import pytest

import release_source_asset_unique as U
import test_data_first_initialization as F
from test_data_first_initialization import CONTEXT, release_sql

SHA = "a" * 40
PRE = {"schema.gql": '''type SourceAsset @table @unique(indexName: "specimen_unique_1", fields: ["bucket", "objectName", "generation"]) {
  id: UUID!
  organizationId: UUID!
  collectionId: UUID!
  specimenId: UUID!
  bucket: String!
  objectName: String!
  generation: String!
}
'''}
WIDER = ' @unique(indexName: "source_asset_specimen_object", fields: ["organizationId", "collectionId", "specimenId", "bucket", "objectName", "generation"])'
OLD = ' @unique(indexName: "specimen_unique_1", fields: ["bucket", "objectName", "generation"])'
STEP1 = {"schema.gql": PRE["schema.gql"].replace(OLD, OLD + WIDER)}
STEP2 = {"schema.gql": STEP1["schema.gql"].replace(OLD, "")}


def test_only_the_genuine_second_merge_needs_a_physical_readback():
    assert U.swap_required(PRE, STEP1, {}, {}) is False
    assert U.swap_required(STEP1, STEP1, {}, {}) is False
    assert U.swap_required(STEP1, STEP2, {}, {}) is True
    both = U.schema_gate.check_additive(PRE, STEP2, {}, {})
    assert both and U.READ_BACK not in both
    # An unrelated refusal is never waived by the physical readback.
    bad = {"schema.gql": STEP2["schema.gql"].replace("  id: UUID!", "  id: UUID")}
    with pytest.raises(ValueError):
        U.swap_required(STEP1, bad, {}, {})


def test_live_and_new_old_constraint_users_keep_the_drop_refused():
    operations = {"uses.gql": '''mutation KeepUsingOld($organizationId: UUID!, $actorUid: String!) @auth(level: NO_ACCESS) @transaction {
      query @redact { organizationMember(key: {organizationId: $organizationId, uid: $actorUid}) @check(expr: "this.active") { active } }
      sourceAsset_upsert(data: {bucket: "b"})
    }'''}
    assert U.schema_gate.check_additive(STEP1, STEP2, {}, operations, unique_read_back=True)
    assert U.swap_required(STEP1, STEP2, {}, operations) is False


@pytest.mark.parametrize("kind", ["readback", "drop"])
@pytest.mark.parametrize("change", ["missing", "false", "numeric", "foreign", "extra"])
def test_native_receipts_require_exact_scope_and_strict_true_flags(kind, change):
    value = {"version": f"source-asset-unique-{kind}/v1", "source_sha": SHA,
             "instance": "specimen-digitization-instance", "valid": True}
    check = U.verify_readback if kind == "readback" else U.verify_drop
    if kind == "drop":
        value["old_absent"] = True
    check(value, SHA)
    bad = copy.deepcopy(value)
    if change == "missing":
        bad.pop("valid")
    elif change == "false":
        bad["valid"] = False
    elif change == "numeric":
        bad["valid"] = 1
    elif change == "foreign":
        bad["instance"] = "specimen-digitization-restore-20260908-r1"
    else:
        bad["arbitrary_statement"] = "not admitted"
    with pytest.raises(ValueError):
        check(bad, SHA)


@pytest.mark.parametrize("mode", ["source-asset-unique", "source-asset-drop"])
@pytest.mark.parametrize("count,passes", [(0, False), (1, True), (2, False)])
def test_actual_native_modes_refuse_missing_or_ambiguous_unique_before_any_drop(tmp_path, mode, count, passes):
    answers = json.dumps([
        ["session_user AS actor", {"rows": [{"database": CONTEXT["database"], "actor": CONTEXT["actor"]}]}],
        ["count(*)::int AS count", {"rows": [{"count": count}]}],
        ["AS present", {"rows": [{"present": False, "index": None}]}],
        ["IS NULL AS absent", {"rows": [{"absent": True}]}],
    ])
    code, receipt, trace = release_sql(tmp_path, mode, answers=answers)
    drops = [text for text, *_ in trace if isinstance(text, str) and text.startswith("DROP INDEX")]
    assert (code == 0) is passes
    if passes:
        (U.verify_drop if mode == "source-asset-drop" else U.verify_readback)(receipt, SHA)
        # An already absent old index is an idempotent no-DROP success.
        assert drops == []
        if drops:
            assert trace.index([drops[0], "extended"]) > next(
                i for i, row in enumerate(trace) if "count(*)::int AS count" in row[0])
    else:
        assert receipt is None and drops == []


def test_a_failed_native_drop_never_emits_a_success_receipt(tmp_path, qualified_physical_ddl):
    sql = "DROP INDEX CONCURRENTLY IF EXISTS public.specimen_unique_1;"
    code, receipt, _ = release_sql(tmp_path, "source-asset-drop", TEST_FAIL=sql, answers=json.dumps([
        ["session_user AS actor", {"rows": [{"database": CONTEXT["database"], "actor": CONTEXT["actor"]}]}],
        ["count(*)::int AS count", {"rows": [{"count": 1}]}],
        ["AS present", {"rows": [{"present": True, "index": OLD_INDEX}]}],
        ["IS NULL AS absent", {"rows": [{"absent": True}]}],
    ]))
    assert code != 0 and receipt is None


# This DDL is a synthetic transport fixture, not qualified native-generated DDL.
# Production has no such artifact yet and refuses any present old index.
PHYSICAL_DDL = "CREATE UNIQUE INDEX specimen_unique_1 ON public.source_asset USING btree (bucket, object_name, generation);\n"
OLD_INDEX = {"index_schema": "public", "table_schema": "public", "table_name": "source_asset",
             "method": "btree", "unique": True, "valid": True, "ready": True, "live": True,
             "no_expression": True, "no_predicate": True, "no_includes": True,
             "keys": ["bucket", "object_name", "generation"], "not_null": True,
             "constraint_backed": False}


@pytest.fixture
def qualified_physical_ddl(tmp_path, monkeypatch):
    """Isolate a reviewed-DDL shape in a test root; never install proof in product source."""
    root = tmp_path / "isolated-source"
    (root / "scripts/ci").mkdir(parents=True)
    (root / "dataconnect/sql").mkdir(parents=True)
    shutil.copyfile(F.D.ROOT / "scripts/ci/release_sql.mjs", root / "scripts/ci/release_sql.mjs")
    shutil.copyfile(F.D.ROOT / "dataconnect/sql/drop-specimen-unique-1.sql", root / "dataconnect/sql/drop-specimen-unique-1.sql")
    ddl = root / "dataconnect/sql/source-asset-old-index-qualified-ddl.sql"
    ddl.write_text(PHYSICAL_DDL)
    monkeypatch.setattr(F.D, "ROOT", root)
    return ddl


def old_answers(index=OLD_INDEX, *, present=True, rows=None):
    return json.dumps([
        ["session_user AS actor", {"rows": [{"database": CONTEXT["database"], "actor": CONTEXT["actor"]}]}],
        ["count(*)::int AS count", {"rows": [{"count": 1}]}],
        ["AS present", {"rows": rows if rows is not None else [{"present": present, "index": index}]}],
        ["IS NULL AS absent", {"rows": [{"absent": True}]}],
    ])


def test_present_exact_old_index_is_proved_before_the_fixed_extended_drop(tmp_path, qualified_physical_ddl):
    code, receipt, trace = release_sql(tmp_path, "source-asset-drop", answers=old_answers())
    assert code == 0
    U.verify_drop(receipt, SHA)
    drop = [i for i, row in enumerate(trace) if row[0].startswith("DROP INDEX")]
    identity = [i for i, row in enumerate(trace) if "AS present" in row[0]]
    wide = [i for i, row in enumerate(trace) if "count(*)::int AS count" in row[0]]
    assert len(drop) == len(identity) == 1 and len(wide) == 2
    assert wide[0] < identity[0] < drop[0] < wide[1]
    assert trace[drop[0]][1] == "extended"
    assert len([row for row in trace if row[0] == "pool"]) == 1


@pytest.mark.parametrize("key,value", [
    ("index_schema", "foreign"), ("table_schema", "foreign"), ("table_name", "specimen"),
    ("method", "hash"), ("unique", False), ("unique", 1), ("valid", False),
    ("ready", False), ("live", False), ("no_expression", False), ("no_predicate", False),
    ("no_includes", False), ("not_null", False), ("constraint_backed", True),
    ("keys", ["bucket", "generation", "object_name"]),
    ("keys", ["organization_id", "collection_id", "bucket", "object_name", "generation"]),
    ("keys", ["bucket", "object_name", None]),
])
def test_wrong_old_physical_identity_never_drops_or_certifies(tmp_path, qualified_physical_ddl, key, value):
    bad = {**OLD_INDEX, key: value}
    code, receipt, trace = release_sql(tmp_path, "source-asset-drop", answers=old_answers(bad))
    assert code != 0 and receipt is None
    assert not any(row[0].startswith("DROP INDEX") for row in trace)


@pytest.mark.parametrize("rows", [[], [{"present": True, "index": None}],
    [{"present": 1, "index": OLD_INDEX}], [{"present": False, "index": OLD_INDEX}],
    [{"present": False, "index": None, "extra": True}],
    [{"present": False, "index": None}, {"present": False, "index": None}]])
def test_malformed_unknown_old_catalog_never_drops_or_certifies(tmp_path, qualified_physical_ddl, rows):
    code, receipt, trace = release_sql(tmp_path, "source-asset-drop", answers=old_answers(rows=rows))
    assert code != 0 and receipt is None
    assert not any(row[0].startswith("DROP INDEX") for row in trace)


@pytest.mark.parametrize("ddl", [None, "CREATE UNIQUE INDEX specimen_unique_1 ON public.specimen USING btree (bucket, object_name, generation);",
    "CREATE UNIQUE INDEX specimen_unique_1 ON public.source_asset USING btree (bucket, generation, object_name);",
    PHYSICAL_DDL + "DROP TABLE public.source_asset;", ""])
def test_missing_or_foreign_generated_mapping_proof_never_drops(tmp_path, qualified_physical_ddl, ddl):
    if ddl is None:
        qualified_physical_ddl.unlink()
    else:
        qualified_physical_ddl.write_text(ddl)
    code, receipt, trace = release_sql(tmp_path, "source-asset-drop", answers=old_answers())
    assert code != 0 and receipt is None
    assert not any(row[0].startswith("DROP INDEX") for row in trace)


@pytest.mark.parametrize("old_present", [True, False])
def test_replacement_index_is_rechecked_after_drop_or_absent_replay(tmp_path, qualified_physical_ddl, monkeypatch, old_present):
    # Only the offline pg transport changes its second wide-index reply.
    needle = "const text=q.text??q;trace([text,q.queryMode??'simple']);"
    replacement = needle + "if(text.includes('count(*)::int AS count') && ++global.wideReads===2)return {rows:[{count:0}]};"
    assert needle in F.RELEASE_PG
    monkeypatch.setattr(F, "RELEASE_PG", "global.wideReads=0;" + F.RELEASE_PG.replace(needle, replacement))
    code, receipt, trace = release_sql(tmp_path, "source-asset-drop", answers=old_answers(
        OLD_INDEX if old_present else None, present=old_present))
    assert code != 0 and receipt is None
    assert len([row for row in trace if row[0].startswith("DROP INDEX")]) == (1 if old_present else 0)


def test_old_catalog_read_error_cannot_reach_drop(tmp_path, qualified_physical_ddl, monkeypatch):
    needle = "const text=q.text??q;trace([text,q.queryMode??'simple']);"
    assert needle in F.RELEASE_PG
    monkeypatch.setattr(F, "RELEASE_PG", F.RELEASE_PG.replace(needle, needle +
        "if(text.includes('AS present'))throw Error('synthetic_catalog_read_failed');"))
    code, receipt, trace = release_sql(tmp_path, "source-asset-drop", answers=old_answers())
    assert code != 0 and receipt is None
    assert not any(row[0].startswith("DROP INDEX") for row in trace)
