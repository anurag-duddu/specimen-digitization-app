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
    return M.check_additive({"schema.gql": BASE}, {"schema.gql": schema}, {"ops.gql": OPS}, {"ops.gql": connector})


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


def test_keys_uniques_and_provenance_keys_keep_not_null_even_when_named(monkeypatch):
    assert set(M.NAMED_RELAXATIONS) == {("SourceAsset", "width"), ("SourceAsset", "height"), ("LabelRegion", "cropAssetId")}
    assert all(isinstance(reason, str) and reason for reason in M.NAMED_RELAXATIONS.values())
    assert M.PROTECTED == {("ModelObservation", f) for f in ("runId", "regionId", "provider", "modelVersion", "stepKey")}
    named = {("SourceAsset", "id"), ("SourceAsset", "bucket"), ("ModelObservation", "code"), ("ModelObservation", "provider")}
    monkeypatch.setattr(M, "NAMED_RELAXATIONS", {**M.NAMED_RELAXATIONS, **dict.fromkeys(named, "test")})
    merged = BASE
    for old in ("  id: UUID! @default", "  bucket: String!", "  code: String!", "  provider: String!"):
        merged = edit(merged, old, old.replace("!", ""))
    assert check(merged) == [f"{field}: NOT NULL dropped on a key, unique or provenance field" for field in (
        "ModelObservation.code", "ModelObservation.provider", "SourceAsset.bucket", "SourceAsset.id")]


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
    assert M.check_additive(SCHEMA, SCHEMA, CONNECTOR, CONNECTOR) == []
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
    assert M.check_additive(SCHEMA, merged, CONNECTOR, connector) == []
    merged["schema.gql"] = edit(merged["schema.gql"], "  stepKey: String!\n  provider:", "  stepKey: String\n  provider:")
    assert M.check_additive(SCHEMA, merged, CONNECTOR, connector) == [
        "ModelObservation.stepKey: NOT NULL dropped on a key, unique or provenance field"]


def test_sources_from_rest_responses_and_committed_directories(tmp_path):
    schema = {"name": "schemas/main", "source": {"files": [{"path": "search.gql", "content": "b"},
                                                           {"path": "schema.gql", "content": "a"}]}}
    assert M.live_sources(schema, None) == ({"schema.gql": "a", "search.gql": "b"}, {})
    assert M.live_sources(schema, {"source": {"files": [{"path": "ops.gql", "content": OPS}]}})[1] == {"ops.gql": OPS}
    for placeholder in ({"source": {}}, {"source": {"files": []}}):
        assert M.live_sources(placeholder, None) == ({}, {})
    with pytest.raises(ValueError, match="placeholder"):
        M.check_additive({}, SCHEMA, {}, CONNECTOR)
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
    arguments = []
    for kind, files in (("schema", SCHEMA), ("connector", CONNECTOR)):
        (tmp_path / kind).mkdir()
        for name, text in files.items():
            (tmp_path / kind / name).write_text(text)
        arguments += [f"--live-{kind}", str(tmp_path / kind)]
    assert M.main(arguments) == 0 and capsys.readouterr().out == "additive\n"
    (tmp_path / "schema" / "extra.gql").write_text(COMPARISON)
    assert M.main(arguments) == 1 and capsys.readouterr().out == "ReadingComparison: table removed or renamed\n"
    with pytest.raises(SystemExit, match="placeholder"):
        M.main(["--live-schema", str(tmp_path), "--live-connector", str(tmp_path / "connector")])
