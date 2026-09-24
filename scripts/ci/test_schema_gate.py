"""Offline additive-only gate for Data Connect schema and connector changes; never network or git."""
import importlib
from pathlib import Path
import re
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
M = importlib.import_module("schema_gate")
ROOT = Path(__file__).resolve().parents[2]
SCHEMA, CONNECTOR = M.read_tree(ROOT / "dataconnect/schema"), M.read_tree(ROOT / "dataconnect/connector")
# The data contract's section 3.3 in #88's shape: three NOT NULL drops and the closed unique exception, after a table
# of another section that the parser must pass over.
CONTRACT = """# Go-live data contract

### 3.2 New nullable columns

| Table | Columns |
|---|---|
| `PipelineRun` | `traceId` (32 lowercase hex, recorded once) |

### 3.3 Relaxed constraints

Each relaxation only admits rows the old constraint refused. S2's schema gate reads the same list, with these reasons.

| Constraint | Change | Why |
|---|---|---|
| `SourceAsset.width`, `SourceAsset.height` | drop `NOT NULL` | Raw provider responses are assets without pixels. |
| `LabelRegion.cropAssetId` | drop `NOT NULL` | SAM regions carry no crop. |
| `EvidenceItem.locator` | drop `NOT NULL` | A lookup that found no single match has nothing to locate. |
| `SourceAsset` unique `specimen_unique_1` on (`bucket`, `objectName`, `generation`) | replaced by `source_asset_specimen_object`, in two applies | The blob store is content-addressed. |

## 4. Domain fields the writer reads
"""


def contract(*rows):
    """Section 3.3 whose table holds these rows."""
    return "### 3.3 Relaxed constraints\n\n| Constraint | Change | Why |\n|---|---|---|\n" + "".join(f"| {row} |\n" for row in rows)


def gate(*sources):
    """The gate with the fixture contract's relaxations; the real contract has a test of its own."""
    return M.check_additive(*sources, relaxations=M.parse_relaxations(CONTRACT))


BASE = r'''# A comment with { braces } and "quotes" never counts.
type SourceAsset @table(name: "source_asset", key: ["organizationId", "id"])
  @unique(indexName: "asset_object", fields: ["bucket", "generation"])
  @index(fields: ["organizationId", "createdAt"]) {
  organizationId: UUID!
  id: UUID! @default(expr: "uuidV4()")
  bucket: String!
  generation: String!
  kind: String! @default(expr: "'raw' + \"}{\" + '#'")
  width: Int!
  height: Int!
  note: String
  tags: [String!]!
  createdAt: Timestamp! @default(expr: "request.time")
}
type LabelRegion @table(key: ["organizationId", "id"]) {
  organizationId: UUID!
  id: UUID!
  sourceAssetId: UUID!
  sourceAsset: SourceAsset! @ref(constraintName: "region_source", fields: ["organizationId", "sourceAssetId"])
  cropAssetId: UUID!
  cropAsset: SourceAsset! @ref(fields: ["organizationId", "cropAssetId"], constraintName: "region_crop")
}
type ModelObservation @table(key: "id") {
  id: UUID!
  provider: String!
  code: String! @unique
}
type AssetListing @view(sql: """
  SELECT id::text COLLATE "C" AS id, meta #>> '{a,b}' AS b -- \"""quoted\""" }
  FROM public.source_asset
""") {
  id: String
  b: String
}
'''
OPS = r'''# Keyset pages { never } use an "offset".
query ListAssets(
  $organizationId: UUID!, $actorUid: String!,
  $afterId: String = null
) @auth(level: NO_ACCESS) {
  organizationMember(key: {organizationId: $organizationId, uid: $actorUid})
    @check(expr: "this.active && (vars.afterId == null || vars.afterId.matches('^[a-f]{8}$'))") { active }
  sourceAssets(where: {id: {gt_expr: "vars.afterId == null ? '' : \"}\""}}, limit: 10) { id }
}
mutation AddAsset($organizationId: UUID!, $actorUid: String!, $id: UUID!) @auth(level: NO_ACCESS) @transaction {
  query @redact {
    organizationMember(key: {organizationId: $organizationId, uid: $actorUid}) @check(expr: "this.active") { active }
  }
  sourceAsset_insert(data: {organizationId: $organizationId, id: $id, kind_expr: "'raw'"})
}
'''
NEW_OP = r'''
mutation AddRegion($organizationId: UUID!, $actorUid: String!, $id: UUID!) @auth(level: NO_ACCESS) @transaction {
  query @redact {
    organizationMember(key: {organizationId: $organizationId, uid: $actorUid}) @check(expr: "this.active") { active }
  }
  labelRegion_insert(data: {organizationId: $organizationId, id: $id})
}
'''
MEMBERSHIP = 'organizationMember(key: {organizationId: $organizationId, uid: $actorUid}) @check(expr: "this.active") { active }'
# Representative pieces of the pull request #88 data contract change.
COMPARISON = r'''
type ReadingComparison @table(key: ["organizationId", "collectionId", "id"]) @unique(indexName: "reading_comparison_pair", fields: ["organizationId", "collectionId", "runId", "regionId", "leftObservationId", "rightObservationId"]) {
  organizationId: UUID!
  collectionId: UUID!
  collection: Collection! @ref(fields: ["organizationId", "collectionId"], constraintName: "readingcomparison_scope")
  id: UUID! @default(expr: "uuidV4()")
  runId: UUID!
  regionId: UUID!
  leftObservationId: UUID!
  leftObservation: ModelObservation! @ref(fields: ["organizationId", "collectionId", "leftObservationId"], constraintName: "comparison_left")
  reasons: [String!]!
}
'''
TRANSCRIPTION = r'''  # The first pass's decision for one region; null on legacy rows.
  regionId: UUID
  region: LabelRegion @ref(constraintName: "transcription_region", fields: ["organizationId", "collectionId", "regionId"])
  selectedObservationId: UUID
  selectedObservation: ModelObservation @ref(constraintName: "transcription_selected", fields: ["organizationId", "collectionId", "selectedObservationId"])
'''
PROJECTION = r'''mutation AppendLabelRegionV2($organizationId: UUID!, $collectionId: UUID!, $id: UUID!, $runId: UUID!, $sourceAssetId: UUID!, $cropAssetId: UUID, $actorUid: String!) @auth(level: NO_ACCESS) @transaction {
  query @redact {
    organizationMember(key: {organizationId: $organizationId, uid: $actorUid}) @check(expr: "this.active") { active }
    collectionMember(key: {organizationId: $organizationId, collectionId: $collectionId, uid: $actorUid}) @check(expr: "this.active && this.role in ['operator', 'reviewer', 'manager', 'admin']") { active role canViewSensitive }
  }
  scope: query @redact {
    pipelineRun(key: {organizationId: $organizationId, collectionId: $collectionId, id: $runId}) @check(expr: "this != null && (!this.specimen.sensitive || response.query.collectionMember.canViewSensitive)", message: "access denied") { specimen { sensitive } }
  }
  labelRegion_insert(data: {organizationId: $organizationId, collectionId: $collectionId, id: $id, runId: $runId, sourceAssetId: $sourceAssetId, cropAssetId: $cropAssetId})
}
'''


def edit(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def drop(text, pattern):
    changed = re.sub(pattern, "", text, count=1, flags=re.S)
    assert changed != text, pattern
    return changed


def check(schema=BASE, connector=OPS):
    return gate({"schema.gql": BASE}, {"schema.gql": schema}, {"ops.gql": OPS}, {"ops.gql": connector})


ACCEPTED = {
    "new table": (BASE + COMPARISON, OPS),
    "new view": (BASE + 'type Other @view(sql: "SELECT 1 AS one") {\n  one: Int\n}\n', OPS),
    "new nullable fields with a reference over a new field": (edit(BASE, "  note: String\n", "  note: String\n  regionId: UUID\n"
        '  region: LabelRegion @ref(constraintName: "asset_region", fields: ["organizationId", "regionId"])\n'
        "  score: Float @default(value: 0.5)\n  labels: [String!] @index\n"), OPS),
    "named relaxations": (edit(BASE, "  width: Int!\n  height: Int!\n", "  width: Int\n  height: Int\n"), OPS),
    "relation following its relaxed column": (
        edit(BASE, "  cropAssetId: UUID!\n  cropAsset: SourceAsset!", "  cropAssetId: UUID\n  cropAsset: SourceAsset"), OPS),
    "new type-level constraints over new fields": (edit(BASE, '"createdAt"]) {', '"createdAt"])\n  @unique(fields: ["batchId", '
        '"batchOrdinal"]) @index(fields: ["batchId"]) {\n  batchId: UUID\n  batchOrdinal: Int\n'), OPS),
    "layout, comments, commas and argument order": (
        edit(BASE, '@ref(fields: ["organizationId", "cropAssetId"], constraintName: "region_crop")',
             '@ref(\n    constraintName: "region_crop" # { not a value }\n    fields: ["organizationId" "cropAssetId"]\n  )'),
        edit(edit(OPS, "(\n  $organizationId: UUID!, $actorUid: String!,\n  $afterId: String = null\n)",
                  "($organizationId: UUID! $actorUid: String! $afterId: String = null)"),
             "  query @redact {", "  query @redact { # membership first {")),
    # Copies of the existing operations under new names, plus one more mutation.
    "new operations at NO_ACCESS with the membership check": (
        BASE, OPS + NEW_OP + OPS.replace("ListAssets", "ListAssetsV2").replace("AddAsset", "AddAssetV2")),
}


@pytest.mark.parametrize(("schema", "connector"), ACCEPTED.values(), ids=ACCEPTED)
def test_additive_changes_are_accepted(schema, connector):
    assert check(schema, connector) == []


SCHEMA_REFUSED = [
    ("table removed", drop(BASE, r"type ModelObservation .*?\n}\n"), ["ModelObservation: table removed or renamed"]),
    ("table renamed", edit(BASE, "type ModelObservation", "type Observation"), ["ModelObservation: table removed or renamed"]),
    ("table became a view", edit(BASE, '@table(key: "id")', '@view(sql: "SELECT 1")'), ["ModelObservation: table removed or renamed"]),
    ("field removed", edit(BASE, "  note: String\n", ""), ["SourceAsset.note: field removed or renamed"]),
    ("type changed", edit(BASE, "  width: Int!", "  width: Int64!"), ["SourceAsset.width: type or list shape changed"]),
    ("list shape changed", edit(BASE, "[String!]!", "[String]!"), ["SourceAsset.tags: type or list shape changed"]),
    ("default changed", edit(BASE, '"uuidV4()"', '"uuidV7()"'), ["SourceAsset.id: @default changed"]),
    ("default added", edit(BASE, "  width: Int!", "  width: Int! @default(value: 0)"), ["SourceAsset.width: @default added"]),
    ("reference changed", edit(BASE, '"region_crop"', '"region_crop_v2"'), ["LabelRegion.cropAsset: @ref changed"]),
    ("NOT NULL added", edit(BASE, "  note: String\n", "  note: String!\n"), ["SourceAsset.note: NOT NULL added"]),
    ("new non-null field", edit(BASE, "  note: String\n", "  note: String\n  extra: String!\n"),
     ["SourceAsset.extra: new field on an existing table must be nullable"]),
    ("NOT NULL dropped elsewhere", edit(BASE, "  kind: String!", "  kind: String"),
     ["SourceAsset.kind: NOT NULL dropped outside the named relaxations"]),
    ("NOT NULL dropped on a provenance key", edit(BASE, "  provider: String!", "  provider: String"),
     ["ModelObservation.provider: NOT NULL dropped on a key, unique or provenance field"]),
    ("relation over an unnamed column", edit(BASE, "  sourceAsset: SourceAsset!", "  sourceAsset: SourceAsset"),
     ["LabelRegion.sourceAsset: NOT NULL dropped outside the named relaxations"]),
    ("relation whose column keeps NOT NULL", edit(BASE, "  cropAsset: SourceAsset!", "  cropAsset: SourceAsset"),
     ["LabelRegion.cropAsset: NOT NULL dropped outside the named relaxations"]),
    ("new fields over existing columns", edit(BASE, "  cropAssetId: UUID!\n", '  cropAssetId: UUID!\n  crop: SourceAsset @ref('
     'constraintName: "crop_again", fields: ["organizationId", "cropAssetId"])\n  source: SourceAsset\n  alias: UUID @col(name: '
     '"crop_asset_id")\n'), ["LabelRegion.alias: new field over an existing column", "LabelRegion.crop: new foreign key over "
     "existing fields only", "LabelRegion.source: new relation without @ref fields over a new field"]),
    ("new type over an existing SQL table", BASE + 'type Assets @table(name: "source_asset") {\n  id: UUID\n}\n',
     ["Assets: new type over an existing SQL table or view"]),
    ("field-level @unique over an existing field", edit(BASE, "  kind: String!", "  kind: String! @unique"), ["SourceAsset.kind: @unique added"]),
    ("type-level @unique over an existing field", edit(BASE, '"createdAt"]) {', '"createdAt"]) @unique(fields: ["kind", '
     '"batchId"]) {\n  batchId: UUID\n'), ["SourceAsset: new type-level @unique over an existing field"]),
    ("type-level constraint changed", edit(BASE, '["bucket", "generation"]', '["generation", "bucket"]'),
     ["SourceAsset: type-level @unique removed or changed", "SourceAsset: new type-level @unique over an existing field"]),
    ("type-level constraint removed", edit(BASE, '\n  @index(fields: ["organizationId", "createdAt"])', ""),
     ["SourceAsset: type-level @index removed or changed"]),
    ("@table name changed", edit(BASE, '"source_asset", key', '"assets", key'), ["SourceAsset: @table key or name changed"]),
    ("@table key changed", edit(BASE, '@table(key: "id")', '@table(key: ["id", "provider"])'), ["ModelObservation: @table key or name changed"]),
    ("view changed", edit(BASE, "AS b --", "AS c --"), ["AssetListing: view changed"]),
    ("view removed", drop(BASE, r"type AssetListing .*?\n}\n"), ["AssetListing: view removed or renamed"]),
]


@pytest.mark.parametrize(("schema", "expected"), [case[1:] for case in SCHEMA_REFUSED], ids=[c[0] for c in SCHEMA_REFUSED])
def test_schema_changes_outside_the_rules_are_refused_by_name(schema, expected):
    assert check(schema) == expected


CONNECTOR_REFUSED = [
    ("operation changed", edit(OPS, "limit: 10", "limit: 11"), ["ListAssets: operation changed"]),
    ("operation changed inside a string", edit(OPS, "{8}", "{9}"), ["ListAssets: operation changed"]),
    ("operation kind changed", edit(OPS, "query ListAssets", "mutation ListAssets"), ["ListAssets: operation changed"]),
    ("operation removed", drop(OPS, r"mutation AddAsset.*?\n}\n"), ["AddAsset: operation removed or renamed"]),
    ("PUBLIC", OPS + edit(NEW_OP, "NO_ACCESS", "PUBLIC"), ["AddRegion: new operation not at @auth(level: NO_ACCESS)"]),
    ("USER", OPS + edit(NEW_OP, "NO_ACCESS", "USER"), ["AddRegion: new operation not at @auth(level: NO_ACCESS)"]),
    ("a second @auth", OPS + edit(NEW_OP, "@transaction", "@auth(level: PUBLIC) @transaction"),
     ["AddRegion: new operation not at @auth(level: NO_ACCESS)"]),
    ("no membership check", OPS + edit(NEW_OP, ' @check(expr: "this.active")', ""),
     ["AddRegion: new operation without the organizationMember @check"]),
    ("membership check only inside a string", OPS + edit(NEW_OP, MEMBERSHIP, 'collectionMember(key: {uid: $actorUid}) '
     '@check(expr: "organizationMember(key: {organizationId: $organizationId, uid: $actorUid}) @check(") { active }'),
     ["AddRegion: new operation without the organizationMember @check"]),
    ("membership check only inside a comment", OPS + edit(NEW_OP, MEMBERSHIP, f"# {MEMBERSHIP}\n    " + MEMBERSHIP.replace(
        ' @check(expr: "this.active")', "")), ["AddRegion: new operation without the organizationMember @check"]),
    ("skippable membership check", OPS + edit(NEW_OP, '"this.active")', '"this.active") @skip(if: true)'),
     ["AddRegion: new operation uses @skip or @include"]),
    ("nullable actor", OPS + edit(NEW_OP, "$actorUid: String!", "$actorUid: String"),
     ["AddRegion: new operation does not declare $actorUid: String!"]),
    ("actor with a default", OPS + edit(NEW_OP, "$actorUid: String!", '$actorUid: String! = "someone"'),
     ["AddRegion: new operation does not declare $actorUid: String!"]),
]


@pytest.mark.parametrize(("connector", "expected"), [c[1:] for c in CONNECTOR_REFUSED], ids=[c[0] for c in CONNECTOR_REFUSED])
def test_connector_changes_outside_the_rules_are_refused_by_name(connector, expected):
    assert check(connector=connector) == expected


LOCATOR = {**SCHEMA, "schema.gql": edit(SCHEMA["schema.gql"], "  locator: String!", "  locator: String")}


def test_protected_keys_are_fixed_and_only_a_listed_column_drops_not_null():
    assert M.PROTECTED == {("ModelObservation", f) for f in ("runId", "regionId", "provider", "modelVersion", "stepKey",
                                                             "rawAssetId", "promptVersion", "inputSha256")}
    types = M.parse_schema(SCHEMA)  # every protected and listed field is a NOT NULL field of the committed schema
    assert all(types[table]["fields"][field]["non_null"] for table, field in M.PROTECTED | set(M.parse_relaxations(CONTRACT)))
    assert gate(SCHEMA, LOCATOR, CONNECTOR, CONNECTOR) == []
    assert M.check_additive(SCHEMA, LOCATOR, CONNECTOR, CONNECTOR, relaxations={}) == [
        "EvidenceItem.locator: NOT NULL dropped outside the named relaxations"]


@pytest.mark.parametrize(("column", "old"), [
    ("SourceAsset.id", "  id: UUID! @default"), ("SourceAsset.bucket", "  bucket: String!"),
    ("ModelObservation.code", "  code: String!"), ("ModelObservation.provider", "  provider: String!"),
], ids=["key column", "type-level @unique column", "field-level @unique column", "PROTECTED column"])
def test_a_contract_listing_a_key_unique_or_protected_column_is_refused_anyway(column, old):
    listed = M.parse_relaxations(contract(f"`{column}` | drop `NOT NULL` | a reason the gate never accepts here"))
    assert list(listed) == [tuple(column.split("."))]
    merged = {"schema.gql": edit(BASE, old, old.replace("!", ""))}
    assert M.check_additive({"schema.gql": BASE}, merged, {"ops.gql": OPS}, {"ops.gql": OPS}, relaxations=listed) == [
        f"{column}: NOT NULL dropped on a key, unique or provenance field"]


def test_the_contract_table_names_each_relaxed_column_with_its_reason():
    assert M.parse_relaxations(CONTRACT) == {
        ("SourceAsset", "width"): "Raw provider responses are assets without pixels.",
        ("SourceAsset", "height"): "Raw provider responses are assets without pixels.",
        ("LabelRegion", "cropAssetId"): "SAM regions carry no crop.",
        ("EvidenceItem", "locator"): "A lookup that found no single match has nothing to locate."}
    for names in ("`A.b` and `C.d`", "`A.b`, `C.d`", "`A.b`, and `C.d`", "`A.b`,`C.d`"):
        assert set(M.parse_relaxations(contract(f"{names} | drop `NOT NULL` | why"))) == {("A", "b"), ("C", "d")}
    assert M.parse_relaxations(contract("`A.b` | add a check | why")) == {}


@pytest.mark.parametrize(("text", "message"), [
    (CONTRACT.replace("### 3.3 Relaxed constraints", "### 3.3 Relaxations"), "relaxed-constraints heading missing or repeated"),
    (CONTRACT + "\n### 3.3 Relaxed constraints\n", "relaxed-constraints heading missing or repeated"),
    (contract().replace("| Constraint", "Leak prose.\n\n## 4. Next\n\n| Constraint") + "| `A.b` | drop `NOT NULL` | why |\n",
     "relaxed-constraints table missing or malformed"),
    (CONTRACT.replace("| Constraint | Change | Why |", "| Column | Change | Why |"), "relaxed-constraints table missing or malformed"),
    (CONTRACT.replace("|---|---|---|\n| `Source", "| `Source"), "relaxed-constraints table missing or malformed"),
    (contract("`A.b` | drop `NOT NULL`"), "malformed relaxed-constraints row"),
    (contract("`leak.b` | drop `NOT NULL` | why"), "malformed relaxed column name"),
    (contract("Leak.b | drop `NOT NULL` | why"), "malformed relaxed column name"),
    (contract("`Leak.b` `C.d` | drop `NOT NULL` | why"), "malformed relaxed column name"),
    (contract("`Leak.b` | drop `NOT NULL` |  "), "empty relaxation reason"),
    (contract("`Leak.b` | drop `NOT NULL` | why", "`C.d` and `Leak.b` | drop `NOT NULL` | why"), "duplicate relaxed column"),
], ids=["no heading", "a second heading", "no table in the section", "another header", "no separator row", "a short row",
        "lower-case table", "unquoted name", "names without a separator", "empty reason", "duplicate column"])
def test_a_malformed_contract_section_fails_closed_without_values(text, message):
    with pytest.raises(ValueError, match=f"^{re.escape(message)}$"):
        M.parse_relaxations(text)


def test_the_gate_reads_the_merged_trees_contract_by_default(tmp_path, monkeypatch):
    assert M.CONTRACT == M.ROOT / "docs/execution/golive/DATA_CONTRACT.md"
    monkeypatch.setattr(M, "CONTRACT", tmp_path / "DATA_CONTRACT.md")
    with pytest.raises(ValueError, match="^data contract missing$"):
        M.check_additive(SCHEMA, LOCATOR, CONNECTOR, CONNECTOR)
    (tmp_path / "DATA_CONTRACT.md").write_text(CONTRACT)
    assert M.check_additive(SCHEMA, LOCATOR, CONNECTOR, CONNECTOR) == []  # T3b1's call, without a keyword
    assert M.read_relaxations(tmp_path / "DATA_CONTRACT.md") == M.parse_relaxations(CONTRACT)


def test_the_real_contract_relaxes_exactly_these_four_columns():
    # Red on this branch until #88, which adds section 3.3's table to the contract, is on main.
    assert set(M.read_relaxations()) == {("SourceAsset", "width"), ("SourceAsset", "height"), ("LabelRegion", "cropAssetId"),
                                         ("EvidenceItem", "locator")}


# PLAN 4.4's one closed @unique exception (#104): create before drop, over two merges.
UNIQUE = '@unique(indexName: "specimen_unique_1", fields: ["bucket", "objectName", "generation"])'
SIX = ("organizationId", "collectionId", "specimenId", "bucket", "objectName", "generation")
WHY, REMOVED, NEW_OVER = ("SourceAsset: @unique specimen_unique_1 ", "SourceAsset: type-level @unique removed or changed",
                          "SourceAsset: new type-level @unique over an existing field")


def unique(base=SCHEMA, old=True, new=SIX, index="source_asset_specimen_object", extra=""):
    """base with SourceAsset's committed unique kept or dropped, beside a new unique over these fields, if any."""
    names = ", ".join(f'"{field}"' for field in new or ())
    added = f' @unique(indexName: "{index}", fields: [{names}])' if new else ""
    return {**base, "schema.gql": edit(base["schema.gql"], UNIQUE, (UNIQUE if old else "") + added + extra)}


STEP1 = unique()
STEP2 = unique(STEP1, old=False, new=None)
KEYED = {**SCHEMA, "schema.gql": edit(SCHEMA["schema.gql"], 'type SourceAsset @table(key: ["organizationId", "collectionId", "id"])',
                                      'type SourceAsset @table(key: ["bucket", "objectName", "generation"])')}
SPECIMEN_ID = '  specimenId: UUID!\n  specimen: Specimen! @ref(constraintName: "scope_ref_8"'
NULLABLE = {**SCHEMA, "schema.gql": edit(SCHEMA["schema.gql"], SPECIMEN_ID, SPECIMEN_ID.replace("UUID!", "UUID"))}
MISSING = {**SCHEMA, "schema.gql": edit(SCHEMA["schema.gql"], SPECIMEN_ID, SPECIMEN_ID.split("\n")[1])}
USES = {
    "a key lookup by its fields": 'query FindAsset @auth(level: NO_ACCESS) {\n  sourceAsset(key: {generation: "1", '
                                  'objectName: "o", bucket_expr: "\'b\'"}) { id }\n}\n',
    "a key it cannot see": "query FindAsset($key: SourceAsset_Key!) @auth(level: NO_ACCESS) {\n  sourceAsset(key: $key) { id }\n}\n",
    "an upsert": 'mutation FindAsset @auth(level: NO_ACCESS) {\n  sourceAsset_upsertMany(data: [{bucket: "b"}])\n}\n',
    "an onConflict naming it": 'mutation FindAsset @auth(level: NO_ACCESS) {\n  sourceAsset_insert(data: {bucket: "b"}, '
                               'onConflict: {constraint: "specimen_unique_1"})\n}\n',
    "an onConflict over its fields": 'mutation FindAsset @auth(level: NO_ACCESS) {\n  sourceAsset_insert(data: {bucket: "b"}, '
                                     'onConflict: {fields: ["objectName", "generation", "bucket"]})\n}\n',
}


def test_the_one_unique_exception_is_closed_and_takes_two_merges():
    assert M.NAMED_UNIQUE_RELAXATIONS == {("SourceAsset", "specimen_unique_1", ("bucket", "objectName", "generation")): (
        ("source_asset_specimen_object", SIX),
        "the blob store is content-addressed, so byte-identical assets of different specimens are one stored object")}
    # Only AppendSourceAsset writes the table, inserting by id; a lookup by the primary key does not use the old unique.
    by_key = {**CONNECTOR, "key.gql": "query GetAsset($organizationId: UUID!, $collectionId: UUID!, $id: UUID!) @auth(level: "
              "NO_ACCESS) {\n  sourceAsset(key: {organizationId: $organizationId, collectionId: $collectionId, id: $id}) { id }\n}\n"}
    for connector in (CONNECTOR, by_key):
        assert gate(SCHEMA, STEP1, connector, connector) == []
        assert gate(STEP1, STEP2, connector, connector) == []
    lookup = {**CONNECTOR, "uses.gql": USES["a key lookup by its fields"]}  # a use matters only to the drop
    assert gate(SCHEMA, STEP1, lookup, lookup) == []


@pytest.mark.parametrize(("live", "merged", "expected"), [
    (SCHEMA, unique(old=False), [WHY + "dropped in the change that adds source_asset_specimen_object; create before drop takes "
                                       "two merges", REMOVED, NEW_OVER]),
    (SCHEMA, unique(old=False, new=SIX[2:]), [WHY + "dropped in the change that adds source_asset_specimen_object; create "
                                                    "before drop takes two merges", REMOVED, NEW_OVER]),
    (SCHEMA, unique(new=SIX[2:]), [NEW_OVER]),
    (SCHEMA, unique(old=False, new=None), [REMOVED]),
    (STEP1, unique(old=False, new=SIX[2:]), [REMOVED, NEW_OVER]),
    (SCHEMA, unique(old=False, index="source_asset_object"), [REMOVED, NEW_OVER]),
    (SCHEMA, unique(extra=' @unique(indexName: "asset_kind", fields: ["kind", "specimenId"])'), [NEW_OVER]),
    (KEYED, unique(KEYED), [WHY + "is the primary key", NEW_OVER]),
    (unique(KEYED), unique(unique(KEYED), old=False, new=None), [WHY + "is the primary key", REMOVED]),
    (NULLABLE, unique(NULLABLE), ["SourceAsset: @unique source_asset_specimen_object adds nullable or missing column specimenId",
                                  NEW_OVER]),
    (MISSING, unique(NULLABLE), ["SourceAsset: @unique source_asset_specimen_object adds nullable or missing column specimenId",
                                 NEW_OVER]),
], ids=["one merge", "one merge to other fields", "step one over other fields", "drop before the new unique is live",
        "step two changing the new unique", "unlisted replacement", "another new uniqueness", "primary key in step one",
        "primary key in step two", "nullable added column", "brand-new added column"])
def test_everything_else_about_the_unique_exception_stays_refused(live, merged, expected):
    assert gate(live, merged, CONNECTOR, CONNECTOR) == expected


@pytest.mark.parametrize(("column", "live", "merged", "standard"), [
    ("generation", SCHEMA, STEP1, NEW_OVER), ("specimenId", STEP1, STEP2, REMOVED)], ids=["step one", "step two"])
def test_the_unique_exception_never_covers_a_protected_key(monkeypatch, column, live, merged, standard):
    monkeypatch.setattr(M, "PROTECTED", M.PROTECTED | {("SourceAsset", column)})
    assert gate(live, merged, CONNECTOR, CONNECTOR) == [
        f"SourceAsset: @unique specimen_unique_1 to source_asset_specimen_object covers protected key {column}", standard]


@pytest.mark.parametrize("operation", USES.values(), ids=USES)
def test_the_old_unique_is_not_dropped_while_an_existing_operation_uses_it(operation):
    connector = {**CONNECTOR, "uses.gql": operation}
    assert gate(STEP1, STEP2, connector, connector) == [WHY + "is used by existing operation FindAsset", REMOVED]


def test_schema_parser_keeps_values_and_normalizes_layout():
    types = M.parse_schema({"schema.gql": BASE})
    asset, view = types["SourceAsset"], types["AssetListing"]
    assert (asset["kind"], view["kind"]) == ("table", "view")
    assert asset["directives"] == {"table": ('@table(key: ["organizationId", "id"], name: "source_asset")',),
                                   "unique": ('@unique(fields: ["bucket", "generation"], indexName: "asset_object")',),
                                   "index": ('@index(fields: ["organizationId", "createdAt"])',)}
    assert asset["fields"]["kind"] == {"type": "String", "list": "", "non_null": True,
                                       "directives": {"default": r'''@default(expr: "'raw' + \"}{\" + '#'")'''}}
    assert asset["fields"]["tags"] == {"type": "String", "list": "[!]", "non_null": True, "directives": {}}
    assert types["LabelRegion"]["fields"]["cropAsset"]["directives"] == {
        "ref": '@ref(constraintName: "region_crop", fields: ["organizationId", "cropAssetId"])'}
    sql = view["directives"]["view"][0]
    assert "#>> '{a,b}'" in sql and r'\"""quoted\""" }' in sql and view["fields"]["b"]["non_null"] is False


def test_connector_splitter_balances_braces_outside_strings_and_comments():
    assert M.parse_connector({"readiness.gql": "# Server only.\nquery Readiness @auth(level: NO_ACCESS) {\n"
                                               "  organizations(limit: 1) { id }\n}\n"}) == {"Readiness": {
        "kind": "query", "header": "query Readiness @ auth ( level : NO_ACCESS )", "body": "organizations ( limit : 1 ) { id }"}}
    operations = M.parse_connector({"ops.gql": OPS})
    assert [(name, value["kind"]) for name, value in operations.items()] == [("ListAssets", "query"), ("AddAsset", "mutation")]
    assert operations["ListAssets"]["body"].endswith(r'''"vars.afterId == null ? '' : \"}\"" } } limit : 10 ) { id }''')
    assert operations["AddAsset"]["body"].startswith("query @ redact { organizationMember")
    assert "offset" not in str(operations) and "Keyset" not in str(operations)
    with pytest.raises(ValueError, match="duplicate operation AddAsset"):
        M.parse_connector({"a.gql": OPS, "b.gql": drop(OPS, r"query ListAssets.*?\n}\n")})


@pytest.mark.parametrize(("parse", "text", "message"), [
    ("schema", "enum Leak { A }", "unsupported schema construct: enum"),
    ("schema", '"leak" type T @table { a: Int }', "unsupported schema construct: string"),
    ("schema", "type T { a: Int }", "T: not exactly one @table or @view"),
    ("schema", 'type T @table @view(sql: "leak") { a: Int }', "T: not exactly one @table or @view"),
    ("schema", "type T @table @searchable { a: Int }", "unsupported directive @searchable on T"),
    ("schema", 'type T @table { a: Int @embed(model: "leak") }', "unsupported directive @embed on T.a"),
    ("schema", "type T @table { a(first: Int): Int }", "expected :"),
    ("schema", 'type T @table(key: {a: "leak"}) { a: Int }', "unsupported directive argument"),
    ("schema", 'type T @table(key: "a", key: "leak") { a: Int }', "duplicate argument in @table"),
    ("schema", 'type T @table { a: String @default(expr: "leak) }', "unterminated string"),
    ("schema", "type T @table { a: Int @unique @unique }", "T.a: duplicate field or directive"),
    ("schema", "type T @table { a: Int }\ntype T @table { b: Int }", "duplicate type T"),
    ("schema", "type T @table { a: [Int }", "expected ]"),
    ("connector", "fragment Leak on T { a }", "unsupported connector construct: fragment"),
    ("connector", "query { leak }", "expected a name"),
    ("connector", "query Q @auth(level: NO_ACCESS) { a { b }", "unexpected end"),
    ("connector", "query Q { a } }", "unsupported connector construct: punct"),
])
def test_unknown_constructs_fail_closed_without_content(parse, text, message):
    with pytest.raises(ValueError, match=message) as raised:
        getattr(M, f"parse_{parse}")({"source.gql": text})
    assert "leak" not in str(raised.value).lower()


def test_committed_tree_is_additive_against_itself():
    assert gate(SCHEMA, SCHEMA, CONNECTOR, CONNECTOR) == []
    types = {name for text in SCHEMA.values() for name in re.findall(r"^type (\w+) @(?:table|view)", text, re.M)}
    operations = {name for text in CONNECTOR.values() for name in re.findall(r"^(?:query|mutation) (\w+)", text, re.M)}
    assert types and set(M.parse_schema(SCHEMA)) == types
    assert operations and set(M.parse_connector(CONNECTOR)) == operations


def test_representative_change_from_pull_request_88_is_additive_but_not_with_a_provenance_key():
    text = SCHEMA["schema.gql"]
    for old, new in (("  width: Int!\n  height: Int!\n", "  width: Int\n  height: Int\n"),
                     # The crop's relation field follows its column, as the pull request does.
                     ("  cropAssetId: UUID!\n  cropAsset: SourceAsset!", "  cropAssetId: UUID\n  cropAsset: SourceAsset"),
                     ("  unresolved: Boolean!\n", "  unresolved: Boolean!\n" + TRANSCRIPTION)):
        text = edit(text, old, new)
    merged, connector = {**SCHEMA, "schema.gql": text + COMPARISON}, {**CONNECTOR, "projection.gql": PROJECTION}
    assert gate(SCHEMA, merged, CONNECTOR, connector) == []
    merged["schema.gql"] = edit(merged["schema.gql"], "  stepKey: String!\n  provider:", "  stepKey: String\n  provider:")
    assert gate(SCHEMA, merged, CONNECTOR, connector) == [
        "ModelObservation.stepKey: NOT NULL dropped on a key, unique or provenance field"]


def test_sources_from_rest_responses_and_committed_directories(tmp_path):
    schema = {"name": "schemas/main", "source": {"files": [{"path": "search.gql", "content": "b"},
                                                           {"path": "schema.gql", "content": "a"}]}}
    assert M.live_sources(schema, None) == ({"schema.gql": "a", "search.gql": "b"}, {})
    assert M.live_sources(schema, {"source": {"files": [{"path": "ops.gql", "content": OPS}]}})[1] == {"ops.gql": OPS}
    for placeholder in ({"source": {}}, {"source": {"files": []}}):
        assert M.live_sources(placeholder, None) == ({}, {})
    with pytest.raises(ValueError, match="placeholder"):
        gate({}, SCHEMA, {}, CONNECTOR)
    for invalid in (None, {}, {"source": {"files": [{"path": "connector.yaml", "content": ""}]}},
                    {"source": {"files": [{"path": "a.gql", "content": 1}]}}, {"source": {"files": [{"path": "a.gql", "content": ""}] * 2}}):
        with pytest.raises(ValueError):
            M.live_sources(invalid, None)
    for name in ("b.gql", "a.gql", "connector.yaml"):
        (tmp_path / name).write_text(name)
    assert list(M.read_tree(tmp_path).items()) == [("a.gql", "a.gql"), ("b.gql", "b.gql")]
    with pytest.raises(ValueError):
        M.read_tree(tmp_path / "missing")
    (tmp_path / "c.gql").write_bytes(b"type \xff")
    with pytest.raises(ValueError, match="^source file is not UTF-8$"):
        M.read_tree(tmp_path)


def test_cli_compares_live_directories_with_the_committed_tree(tmp_path, capsys):
    (tmp_path / "contract.md").write_text(CONTRACT)
    arguments = ["--contract", str(tmp_path / "contract.md")]
    for kind, files in (("schema", SCHEMA), ("connector", CONNECTOR)):
        (tmp_path / kind).mkdir()
        for name, text in files.items():
            (tmp_path / kind / name).write_text(text)
        arguments += [f"--live-{kind}", str(tmp_path / kind)]
    assert M.main(arguments) == 0 and capsys.readouterr().out == "additive\n"
    (tmp_path / "schema" / "extra.gql").write_text(COMPARISON)
    assert M.main(arguments) == 1 and capsys.readouterr().out == "ReadingComparison: table removed or renamed\n"
    with pytest.raises(SystemExit, match="placeholder"):
        M.main([*arguments[:2], "--live-schema", str(tmp_path), "--live-connector", str(tmp_path / "connector")])
    with pytest.raises(SystemExit, match="data contract missing"):
        M.main(["--contract", str(tmp_path / "missing.md"), *arguments[2:]])
