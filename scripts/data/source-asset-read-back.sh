#!/usr/bin/env bash
# Read back step 1 of SourceAsset's per-specimen uniqueness before step 2 drops the old index
# (docs/execution/golive/DATA_CONTRACT.md 3.3; PLAN 4.4). Usage: source-asset-read-back.sh PSQL ARGS...
# Prints 1 only when source_asset_specimen_object is a unique, valid, whole-table index over
# exactly its six columns, in order; the local runners drop specimen_unique_1 only after it prints 1.
set -euo pipefail
"$@" -v ON_ERROR_STOP=1 -At <<'SQL'
SELECT count(*)
FROM pg_index AS i
JOIN pg_class AS x ON x.oid = i.indexrelid
JOIN pg_class AS t ON t.oid = i.indrelid
JOIN pg_namespace AS n ON n.oid = t.relnamespace
WHERE n.nspname = 'public'
  AND t.relname = 'source_asset'
  AND x.relname = 'source_asset_specimen_object'
  AND i.indisunique
  AND i.indisvalid
  AND i.indpred IS NULL
  AND i.indexprs IS NULL
  AND ARRAY(
    SELECT a.attname::text
    FROM unnest(i.indkey::int2[]) WITH ORDINALITY AS k(attnum, position)
    JOIN pg_attribute AS a ON a.attrelid = t.oid AND a.attnum = k.attnum
    ORDER BY k.position
  ) = ARRAY['organization_id', 'collection_id', 'specimen_id', 'bucket', 'object_name', 'generation'];
SQL
