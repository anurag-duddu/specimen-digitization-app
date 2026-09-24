-- Step 2 of making SourceAsset's object uniqueness per specimen (docs/execution/golive/DATA_CONTRACT.md 3.3).
-- The compatible schema migration never drops an index schema.gql stops declaring, so this one fixed
-- statement drops exactly the old one. Run it only after a read-back shows source_asset_specimen_object
-- in place: S2's release does, and the local runners check the same before applying it.
DROP INDEX CONCURRENTLY IF EXISTS public.specimen_unique_1;
