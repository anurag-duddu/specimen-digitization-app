-- Database initialization for the data release; scripts/release/data_sql.mjs runs it in "init" mode.
-- One transaction that creates only what is missing and removes nothing, so running it again is safe.
-- An error anywhere rolls all of it back. A GRANT or REVOKE the acting role has no right to make is only a warning
-- in PostgreSQL, so the transaction can commit without it; the release probes again afterwards and fails, naming
-- whatever is still missing.
BEGIN;
SET LOCAL search_path = pg_catalog;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
SET LOCAL idle_in_transaction_session_timeout = '30s';
-- Creating roles needs CREATEROLE. An IAM SQL user never has it, so it acts as cloudsqlsuperuser, which Cloud SQL
-- lets it do once the owner has assigned that role; the managed role then stays the grantor of every grant below.
-- SET LOCAL lasts until COMMIT. A user that cannot act as cloudsqlsuperuser but has CREATEROLE runs as itself.
DO $executor$
BEGIN
  IF current_database() <> 'specimen-digitization-database' THEN
    RAISE EXCEPTION 'connected to database %, not specimen-digitization-database', current_database();
  END IF;
  IF (SELECT pg_catalog.pg_has_role(session_user, oid, 'SET') FROM pg_catalog.pg_roles
      WHERE rolname = 'cloudsqlsuperuser') THEN
    SET LOCAL ROLE cloudsqlsuperuser;
  ELSIF (SELECT rolcreaterole FROM pg_catalog.pg_roles WHERE rolname = session_user) THEN
    NULL;
  ELSE
    RAISE EXCEPTION 'the data-release SQL user lacks cloudsqlsuperuser; the owner runs scripts/ops/owner_setup.sh once';
  END IF;
END
$executor$;
-- The one extension the schema needs: @default(expr: "uuidV4()") compiles to uuid_generate_v4().
-- Named with its schema because search_path is pg_catalog.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" SCHEMA public;
-- The three roles Data Connect expects for this database and schema.
DO $roles$
DECLARE
  wanted text;
BEGIN
  FOREACH wanted IN ARRAY ARRAY[
    'firebaseowner_specimen-digitization-database_public',
    'firebasewriter_specimen-digitization-database_public',
    'firebasereader_specimen-digitization-database_public']
  LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = wanted) THEN
      EXECUTE pg_catalog.format(
        'CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', wanted);
    END IF;
  END LOOP;
END
$roles$;
-- Downward membership only: the managed superuser role can act as each application role.
GRANT "firebaseowner_specimen-digitization-database_public",
      "firebasewriter_specimen-digitization-database_public",
      "firebasereader_specimen-digitization-database_public"
  TO cloudsqlsuperuser WITH INHERIT TRUE, SET TRUE;
-- The CREATE grant around the owner change is kept from the original initialization and taken back at once.
-- PostgreSQL does not need it: it checks the role making the change, the database owner, not the new owner.
DO $owner$
BEGIN
  IF (SELECT pg_catalog.pg_get_userbyid(nspowner) FROM pg_catalog.pg_namespace WHERE nspname = 'public')
      <> 'firebaseowner_specimen-digitization-database_public' THEN
    GRANT CREATE ON DATABASE "specimen-digitization-database"
      TO "firebaseowner_specimen-digitization-database_public";
    ALTER SCHEMA public OWNER TO "firebaseowner_specimen-digitization-database_public";
    REVOKE CREATE ON DATABASE "specimen-digitization-database"
      FROM "firebaseowner_specimen-digitization-database_public";
  END IF;
END
$owner$;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE CONNECT, TEMPORARY ON DATABASE "specimen-digitization-database" FROM PUBLIC;
GRANT CONNECT ON DATABASE "specimen-digitization-database" TO
  "firebaseowner_specimen-digitization-database_public",
  "firebasewriter_specimen-digitization-database_public",
  "firebasereader_specimen-digitization-database_public";
GRANT USAGE ON SCHEMA public TO
  "firebasewriter_specimen-digitization-database_public",
  "firebasereader_specimen-digitization-database_public";
-- The release identity migrates as the owner role; the Data Connect service agent reads and writes rows.
GRANT "firebaseowner_specimen-digitization-database_public"
  TO "specimen-data-release@specimen-digitization.iam" WITH ADMIN FALSE, INHERIT TRUE, SET TRUE;
GRANT "firebasewriter_specimen-digitization-database_public"
  TO "service-716045864126@gcp-sa-firebasedataconnect.iam" WITH ADMIN FALSE, INHERIT TRUE, SET TRUE;
-- Tables and sequences the owner role creates later are usable by the writer and readable by the reader.
ALTER DEFAULT PRIVILEGES FOR ROLE "firebaseowner_specimen-digitization-database_public"
  IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES
  TO "firebasewriter_specimen-digitization-database_public";
ALTER DEFAULT PRIVILEGES FOR ROLE "firebaseowner_specimen-digitization-database_public"
  IN SCHEMA public GRANT SELECT ON TABLES TO "firebasereader_specimen-digitization-database_public";
ALTER DEFAULT PRIVILEGES FOR ROLE "firebaseowner_specimen-digitization-database_public"
  IN SCHEMA public GRANT USAGE ON SEQUENCES TO "firebasewriter_specimen-digitization-database_public";
COMMIT;
