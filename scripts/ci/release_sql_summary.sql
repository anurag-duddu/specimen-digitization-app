-- Read only (RELEASE.md 4.3 step 1): the application database's value-free summary for the first
-- initialization. Counts, the three role names' presence and extension names; never an owner, ACL or row.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '2s';
WITH user_schemas AS (SELECT oid FROM pg_namespace WHERE left(nspname,3) <> 'pg_' AND nspname <> 'information_schema')
SELECT current_database() = 'specimen-digitization-database' AS expected_database,
  current_user = 'specimen-data-release@specimen-digitization.iam' AS expected_actor,
  (SELECT count(*)::int FROM pg_class WHERE relnamespace IN (SELECT oid FROM user_schemas) AND relkind NOT IN ('v','m')) AS relations,
  (SELECT count(*)::int FROM pg_class WHERE relnamespace IN (SELECT oid FROM user_schemas) AND relkind IN ('v','m')) AS views,
  (SELECT count(*)::int FROM pg_proc WHERE pronamespace IN (SELECT oid FROM user_schemas)) AS routines,
  (SELECT count(*)::int FROM pg_type WHERE typnamespace IN (SELECT oid FROM user_schemas)) AS types,
  ARRAY(SELECT extname::text FROM pg_extension WHERE extname <> 'plpgsql' ORDER BY extname) AS extensions,
  ARRAY(SELECT rolname::text FROM pg_roles WHERE rolname IN ('firebaseowner_specimen-digitization-database_public',
    'firebasewriter_specimen-digitization-database_public', 'firebasereader_specimen-digitization-database_public')
    ORDER BY rolname) AS roles;
COMMIT;
