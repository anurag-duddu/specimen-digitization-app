-- Separate reviewed data rollout; never apply through Hosting. IF NOT EXISTS
-- does not repair an invalid/mismatched index: inspect definition and validity.
CREATE INDEX CONCURRENTLY IF NOT EXISTS specimen_search_cursor
  ON public.specimen (organization_id, collection_id, created_at, (id::text COLLATE "C"))
  INCLUDE (id, revision, state, disposition, sensitive);
CREATE INDEX CONCURRENTLY IF NOT EXISTS snapshot_search_batch
  ON public.specimen_snapshot (organization_id, collection_id, (snapshot #>> '{batch_id}'), specimen_id, revision);
