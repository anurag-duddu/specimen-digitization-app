"""Step 2 of SourceAsset's per-specimen object uniqueness (docs/execution/golive/DATA_CONTRACT.md 3.3).

CI never starts the emulator, so these checks pin the pieces a release relies on: the
schema declares only the per-specimen constraint, one fixed statement drops exactly
the old index, and the local runners apply it only after reading the new one back.
"""

from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
DROP = ROOT / "dataconnect/sql/drop-specimen-unique-1.sql"
READ_BACK = "indexname = 'source_asset_specimen_object'"
APPLY = "-f dataconnect/sql/drop-specimen-unique-1.sql"


def statements(sql: str) -> list[str]:
    body = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    return [s.strip() for s in body.split(";") if s.strip()]


def test_the_drop_is_one_statement_for_exactly_the_old_index():
    assert statements(DROP.read_text()) == [
        "DROP INDEX CONCURRENTLY IF EXISTS public.specimen_unique_1"
    ]


def test_the_schema_declares_only_the_per_specimen_constraint():
    schema = (ROOT / "dataconnect/schema/schema.gql").read_text()
    source_asset = re.search(r"^type SourceAsset .*$", schema, re.M).group(0)
    assert 'indexName: "specimen_unique_1"' not in schema
    assert (
        '@unique(indexName: "source_asset_specimen_object", fields: '
        '["organizationId", "collectionId", "specimenId", "bucket", "objectName", "generation"])'
    ) in source_asset


def test_the_local_runners_drop_only_after_reading_the_new_constraint_back():
    for runner in ("scripts/data/test-postgres.sh", "scripts/data/serve-local.sh"):
        text = (ROOT / runner).read_text()
        assert text.count(APPLY) == 1, runner
        assert READ_BACK in text, runner
        assert text.index(READ_BACK) < text.index(APPLY), runner
