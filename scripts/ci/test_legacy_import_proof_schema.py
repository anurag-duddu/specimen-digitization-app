"""Retained I2 proof DDL controls. SOURCE ONLY; not native/cloud qualification.

This restores only the genuine legacy proof type read by the current I2 SQL.
No fixture import, authority installer, proof writer, or paid admission is added.
The compiled connector, physical SQL catalog, IAM and transaction behavior still
require separately authorized qualification through the protected release path.
"""
import hashlib
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).parent))
import schema_gate as gate

ROOT = Path(__file__).resolve().parents[2]
PROOF_FILE = "legacy_import_proof_v1.gql"
PROOF_TYPE = "ResearchLedgerImportProofV1"
PROOF_TABLE = "research_ledger_import_proof_v1"
# Literal raw custody bytes retained from live-native-publication-source-20261001
# dataconnect/schema/schema.gql lines 615-639. This is a type, never a proof row.
# Current source removes exactly one terminal LF for end-of-file-fixer.
RETAINED_RAW_DDL_SHA256 = "6d53057be6e318984e5966bc3348601e211610df4615777c73f2c78c60fa510b"
CURRENT_DDL_SHA256 = "753b929178c0b630abbd9f76e01d350f5bcecaa3fcab426774d815c76812b4d5"
SCHEMA = gate.read_tree(ROOT / "dataconnect/schema")
CONNECTOR = gate.read_tree(ROOT / "dataconnect/connector")
SUBJECT_REFERENCE_COUNTS = {
    "research_binding_v2.gql": 2,
    "research_materialization_inputs_v2.gql": 1,
    "research_publication_v2.gql": 1,
}
PROOF_FIELDS = {
    "organizationId": "UUID", "programKey": "String", "id": "UUID",
    "legacyCollectionId": "UUID", "legacyDocumentId": "UUID",
    "legacyDocumentRevision": "Int", "legacyDocumentKind": "String",
    "legacyPayload": "Any", "legacyPayloadDigest": "String",
    "ledgerDigest": "String", "importDigest": "String", "proofDigest": "String",
    "settledMicroUsd": "Int64", "heldMicroUsd": "Int64",
    "lagReserveMicroUsd": "Int64", "sharedReserveMicroUsd": "Int64",
    "ceilingMicroUsd": "Int64", "authorityComplete": "Boolean",
    "oldEngineQuiescent": "Boolean", "verifiedAt": "Timestamp",
    "validUntil": "Timestamp",
}


def test_retained_proof_type_keeps_original_key_scalar_shapes_and_bytes():
    raw = (ROOT / "dataconnect/schema" / PROOF_FILE).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CURRENT_DDL_SHA256
    assert raw.endswith(b"}\n") and not raw.endswith(b"\n\n")
    # The reviewed EOF-only custody delta is exactly one omitted LF, not a
    # general whitespace normalization or fallback acceptance of another hash.
    assert hashlib.sha256(raw + b"\n").hexdigest() == RETAINED_RAW_DDL_SHA256
    types = gate.parse_schema({PROOF_FILE: raw.decode("utf-8")})
    assert set(types) == {PROOF_TYPE}
    proof = types[PROOF_TYPE]
    assert proof["kind"] == "table"
    assert proof["directives"] == {
        "table": ('@table(key: ["organizationId", "programKey", "id"])',),
    }
    assert proof["fields"] == {
        name: {"type": kind, "list": "", "non_null": True, "directives": {}}
        for name, kind in PROOF_FIELDS.items()
    }
    assert gate._sql(PROOF_TYPE, proof["directives"]["table"][0]) == PROOF_TABLE


def test_additive_proof_restoration_changes_only_one_declared_physical_table():
    before = {name: text for name, text in SCHEMA.items() if name != PROOF_FILE}
    assert PROOF_TYPE not in gate.parse_schema(before)
    tables, views, relaxed = gate.declared_sql(SCHEMA, {})
    old_tables, old_views, old_relaxed = gate.declared_sql(before, {})
    assert tables == old_tables | {PROOF_TABLE}
    assert PROOF_TABLE not in old_tables
    assert (views, relaxed) == (old_views, old_relaxed)
    assert gate.check_additive(before, SCHEMA, CONNECTOR, CONNECTOR, relaxations={}) == []


def test_current_i2_physical_table_and_proof_column_references_are_declared():
    tables = gate.declared_sql(SCHEMA, {})[0]
    proof_columns = {gate._sql(name, None) for name in PROOF_FIELDS}
    for name, count in SUBJECT_REFERENCE_COUNTS.items():
        text = CONNECTOR[name]
        assert text.count("public." + PROOF_TABLE) == count
        physical = set(re.findall(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+public\.(\w+)", text, re.I))
        assert physical <= tables, (name, physical - tables)
        referenced = set(re.findall(r"\b(?:authority|proof)\.([a-z_]\w*)", text))
        assert referenced and referenced <= proof_columns, (name, referenced - proof_columns)


def test_no_current_connector_writes_legacy_proof_rows():
    for name, text in CONNECTOR.items():
        assert not re.search(
            r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(?:public\.)?"
            + PROOF_TABLE + r"\b", text, re.I,
        ), name
        assert not re.search(
            r"\bresearchLedgerImportProofV1_(?:insert|upsert|update|delete)\b", text,
        ), name


def test_legacy_store_live_admission_still_requires_genuine_import_authority():
    source = (ROOT / "src/specimen_digitization/research_harness/persistence.py").read_text()
    method = source.split("def require_live_authority(", 1)[1].split("\n    def ", 1)[0]
    assert 'raise PermissionError("Verified legacy ProgramLedger import authority is not installed")' in method
