-- Fixed metadata-only inventory under the already registered IAM SQL identity.
-- Never emit role names, ACLs, memberships, owners, application rows or passwords.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '2s';
SELECT 1 / (current_database() IN ('postgres','specimen-digitization-database'))::int AS exact_database_guard;
WITH approved(name) AS (SELECT unnest(ARRAY[
  'organization','organization_member','collection','collection_member','specimen',
  'specimen_snapshot','request_receipt','profile_version','source_asset','pipeline_run',
  'label_region','model_observation','transcription_version','evidence_item','field_candidate',
  'candidate_evidence','review_decision','audit_event','checkpoint','provider_connection',
  'auxiliary_document','auxiliary_version','auxiliary_receipt','record_version','resolved_field',
  'validation_finding','outbox_event'
]::text[])),
expected_roles(kind,name) AS (VALUES
  ('owner','firebaseowner_specimen-digitization-database_public'),
  ('reader','firebasereader_specimen-digitization-database_public'),
  ('writer','firebasewriter_specimen-digitization-database_public')),
roles AS (SELECT e.kind,r.* FROM expected_roles e JOIN pg_roles r ON r.rolname=e.name),
public_tables AS (SELECT c.* FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE current_database()='specimen-digitization-database'
    AND n.nspname='public' AND c.relkind IN ('r','p','v','m','f')),
required_tables AS (SELECT * FROM public_tables WHERE relname IN ('specimen','specimen_snapshot','auxiliary_document'))
SELECT
  current_database() IN ('postgres','specimen-digitization-database') AS expected_database,
  current_user='specimen-data-release@specimen-digitization.iam' AS expected_actor,
  EXISTS(SELECT FROM pg_database WHERE datname='specimen-digitization-database') AS application_database_exists,
  current_database()='specimen-digitization-database' AS application_catalog_observed,
  EXISTS(SELECT FROM roles WHERE kind='owner') AS owner_exists,
  EXISTS(SELECT FROM roles WHERE kind='reader') AS reader_exists,
  EXISTS(SELECT FROM roles WHERE kind='writer') AS writer_exists,
  (SELECT count(*)=3 AND bool_and(NOT (rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls OR rolcanlogin)) FROM roles)
    AS expected_roles_without_global_privileges,
  (current_database()='specimen-digitization-database' AND
    EXISTS(SELECT FROM pg_namespace n JOIN roles r ON r.oid=n.nspowner WHERE n.nspname='public' AND r.kind='owner'))
    AS owner_public_schema,
  (current_database()='specimen-digitization-database' AND EXISTS(SELECT FROM roles WHERE kind='owner') AND NOT EXISTS(
    SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN roles r ON r.oid=c.relowner
    WHERE r.kind='owner' AND c.relkind IN ('r','p','v','m','f')
      AND (n.nspname<>'public' OR c.relname NOT IN (SELECT name FROM approved))))
    AS owner_only_approved_tables_in_database,
  (EXISTS(SELECT FROM roles WHERE kind='owner') AND NOT EXISTS(
    SELECT FROM pg_auth_members m JOIN roles r ON r.oid=m.member WHERE r.kind='owner'))
    AS owner_has_no_parent_memberships,
  (current_database()='specimen-digitization-database' AND
    NOT EXISTS(SELECT FROM public_tables c WHERE NOT has_table_privilege(current_user,c.oid,'SELECT')))
    AS current_can_select_all_public_tables,
  (current_database()='specimen-digitization-database' AND
    NOT EXISTS(SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' AND c.relkind='S' AND NOT has_sequence_privilege(current_user,c.oid,'SELECT')))
    AS current_can_select_sequences,
  (SELECT count(*)=3 AND bool_and(has_table_privilege(current_user,oid,'MAINTAIN')) FROM required_tables)
    AS current_can_maintain_required_tables,
  (SELECT count(*)=3 AND bool_and(pg_has_role(current_user,relowner,'USAGE')) FROM required_tables)
    AS current_can_create_required_indexes,
  (EXISTS(SELECT FROM pg_roles WHERE rolname=current_user AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls))
    OR EXISTS(SELECT FROM pg_roles WHERE rolname IN ('cloudsqlsuperuser','firebasesuperuser') AND pg_has_role(current_user,oid,'MEMBER')))
    AS current_has_global_privileges,
  ARRAY(SELECT relname FROM public_tables WHERE relname IN (SELECT name FROM approved) ORDER BY relname) AS approved_tables,
  (SELECT count(*)::int FROM public_tables) AS public_table_count,
  (SELECT count(*)::int FROM public_tables WHERE relname NOT IN (SELECT name FROM approved)) AS unapproved_table_count;
COMMIT;
