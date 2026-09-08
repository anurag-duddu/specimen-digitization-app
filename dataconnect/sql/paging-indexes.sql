-- Additive query indexes for canonical UUID text keysets. SQL Connect UUID_Filter
-- does not support ordering. Apply only to a disposable local database or through
-- a separately approved data rollout after schema review, never Hosting CI.
-- These supplement schema.gql: retain them during COMPATIBLE schema migrations.
CREATE INDEX CONCURRENTLY IF NOT EXISTS specimen_text_cursor
ON public.specimen (organization_id, collection_id, ((id::text) COLLATE "C"))
INCLUDE (created_at, revision, state, disposition, work_available_at, active_run_id, sensitive);

CREATE INDEX CONCURRENTLY IF NOT EXISTS auxiliary_text_cursor
ON public.auxiliary_document (organization_id, collection_id, kind, ((id::text) COLLATE "C"))
INCLUDE (created_at, revision);
