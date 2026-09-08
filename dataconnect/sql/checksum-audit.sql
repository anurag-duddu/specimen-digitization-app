-- Read-only prerequisite audit, never a Hosting migration or automatic backfill.
-- Run only with separately authorized database access. No snapshot payload output.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT count(*) AS total_rows,
  count(*) FILTER (WHERE source_checksum IS NULL) AS legacy_null_checksums,
  count(*) FILTER (WHERE source_checksum IS NOT NULL AND source_checksum !~ '^[a-f0-9]{64}$') AS invalid_typed_checksums
FROM public.specimen;

SELECT s.organization_id, s.collection_id, s.id,
  CASE WHEN v.specimen_id IS NULL THEN 'missing_current_snapshot'
    WHEN jsonb_typeof(v.snapshot #> '{asset,sha256}') IS DISTINCT FROM 'string'
      OR (v.snapshot #>> '{asset,sha256}') !~ '^[a-f0-9]{64}$' THEN 'invalid_snapshot_checksum'
    WHEN s.source_checksum IS NULL THEN 'legacy_requires_verified_backfill'
    WHEN s.source_checksum <> v.snapshot #>> '{asset,sha256}' THEN 'typed_snapshot_mismatch'
  END AS audit_state
FROM public.specimen s LEFT JOIN public.specimen_snapshot v
  ON v.organization_id=s.organization_id AND v.collection_id=s.collection_id
  AND v.specimen_id=s.id AND v.revision=s.revision
WHERE v.specimen_id IS NULL OR s.source_checksum IS NULL
  OR jsonb_typeof(v.snapshot #> '{asset,sha256}') IS DISTINCT FROM 'string'
  OR (v.snapshot #>> '{asset,sha256}') !~ '^[a-f0-9]{64}$'
  OR s.source_checksum <> v.snapshot #>> '{asset,sha256}';

-- Current snapshot duplicate groups must be adjudicated before any backfill.
-- Never automatically delete/merge records or rewrite immutable history.
SELECT s.organization_id, s.collection_id, v.snapshot #>> '{asset,sha256}' AS checksum,
  count(*) AS specimen_count, array_agg(s.id ORDER BY s.id) AS specimen_ids
FROM public.specimen s JOIN public.specimen_snapshot v
  ON v.organization_id=s.organization_id AND v.collection_id=s.collection_id
  AND v.specimen_id=s.id AND v.revision=s.revision
WHERE jsonb_typeof(v.snapshot #> '{asset,sha256}')='string'
  AND v.snapshot #>> '{asset,sha256}' ~ '^[a-f0-9]{64}$'
GROUP BY s.organization_id, s.collection_id, v.snapshot #>> '{asset,sha256}'
HAVING count(*) > 1;

SELECT c.relname, i.indisunique, i.indisvalid, pg_get_indexdef(c.oid) AS definition
FROM pg_class c JOIN pg_index i ON i.indexrelid=c.oid
WHERE c.relname='specimen_scope_checksum';
COMMIT;
