"""Step 2 of SourceAsset's per-specimen object uniqueness (docs/execution/golive/DATA_CONTRACT.md 3.3).

CI never starts the emulator, so these checks pin the pieces a release relies on: the
schema declares only the per-specimen constraint, one fixed statement drops exactly
the old index, and the local runners apply it only after reading the new one back.
"""

from __future__ import annotations

from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[2]
DROP = ROOT / "dataconnect/sql/drop-specimen-unique-1.sql"
READ_BACK = "indexname = 'source_asset_specimen_object'"
APPLY = "-f dataconnect/sql/drop-specimen-unique-1.sql"
INDEX_FILES = ["dataconnect/sql/paging-indexes.sql", "dataconnect/sql/search-indexes.sql"]
TEXT = {".py", ".mjs", ".js", ".sh", ".yml", ".yaml", ".json", ".sql", ".toml"}


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


def _values(document, key):
    if isinstance(document, dict):
        for name, value in document.items():
            if name == key:
                yield value
            yield from _values(value, key)
    elif isinstance(document, list):
        for item in document:
            yield from _values(item, key)


def test_no_release_step_runs_the_drop_before_the_live_read_back():
    """Only S2's T3d, after its own live read-back, may run the drop (PLAN 4.4 in #124).

    Today's release executes the two index files alone, and asserts each statement is a
    CREATE INDEX CONCURRENTLY IF NOT EXISTS; a restore re-applies the same two; the data plan
    templates only fingerprint the drop. So nothing in the release path names it.
    """
    release_sql = (ROOT / "scripts/ci/release_sql.mjs").read_text()
    executed = re.search(r"for \(const file of \[([^\]]*)\]\)", release_sql).group(1)
    assert re.findall(r"'([^']+)'", executed) == INDEX_FILES
    assert "assert.match(statement, /^CREATE INDEX CONCURRENTLY IF NOT EXISTS /);" in release_sql
    live = json.loads((ROOT / "infra/live/data-resources.json").read_text())
    assert list(_values(live, "supplemental_sql")) == [INDEX_FILES]
    here = Path(__file__).resolve()
    naming = sorted(
        path.relative_to(ROOT).as_posix()
        for folder in ("scripts/ci", ".github/workflows", "infra/live")
        for path in (ROOT / folder).rglob("*")
        if path.is_file()
        and path.suffix in TEXT
        and "__pycache__" not in path.parts
        and path.resolve() != here
        and "drop-specimen-unique-1" in path.read_text(errors="ignore")
    )
    assert naming == []
