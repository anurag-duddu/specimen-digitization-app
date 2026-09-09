-- Fixed initialization transaction; invoked only by the protected data workflow.
-- Requires earlier exact native restore/absence/owner/capability proof; no standalone CLI.
BEGIN;
SET LOCAL search_path = pg_catalog;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
SET LOCAL idle_in_transaction_session_timeout = '30s';
SET LOCAL ROLE cloudsqlsuperuser;
DO $guard$
BEGIN
  IF current_database() <> 'specimen-digitization-database'
     OR session_user <> 'specimen-data-initialize@specimen-digitization.iam'
     OR current_user <> 'cloudsqlsuperuser' THEN
    RAISE EXCEPTION 'initialization target or actor mismatch';
  END IF;
  IF NOT (SELECT rolcreaterole FROM pg_catalog.pg_roles WHERE rolname=current_user) THEN
    RAISE EXCEPTION 'unqualified native role creation capability';
  END IF;
  IF (SELECT pg_catalog.pg_get_userbyid(datdba) FROM pg_catalog.pg_database
      WHERE datname=current_database()) <> 'cloudsqlsuperuser' THEN
    RAISE EXCEPTION 'database owner differs from qualified API creation';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname IN (
    'firebaseowner_specimen-digitization-database_public',
    'firebasewriter_specimen-digitization-database_public',
    'firebasereader_specimen-digitization-database_public')) THEN
    RAISE EXCEPTION 'never adopt preexisting application roles';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
      WHERE left(n.nspname,3) <> 'pg_' AND n.nspname <> 'information_schema')
     OR EXISTS (SELECT 1 FROM pg_catalog.pg_namespace
       WHERE left(nspname,3) <> 'pg_' AND nspname NOT IN ('public','information_schema'))
     OR EXISTS (SELECT 1 FROM pg_catalog.pg_proc f JOIN pg_catalog.pg_namespace n ON n.oid=f.pronamespace
       WHERE left(n.nspname,3) <> 'pg_' AND n.nspname <> 'information_schema')
     OR EXISTS (SELECT 1 FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace
       WHERE left(n.nspname,3) <> 'pg_' AND n.nspname <> 'information_schema') THEN
    RAISE EXCEPTION 'new database has unreviewed user objects';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles
    WHERE rolname='specimen-data-release@specimen-digitization.iam' AND rolcanlogin
      AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication AND NOT rolbypassrls)
     OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles
    WHERE rolname='service-716045864126@gcp-sa-firebasedataconnect.iam' AND rolcanlogin
      AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication AND NOT rolbypassrls) THEN
    RAISE EXCEPTION 'ordinary IAM SQL principals missing or elevated';
  END IF;
END
$guard$;
CREATE ROLE "firebaseowner_specimen-digitization-database_public"
  NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE "firebasewriter_specimen-digitization-database_public"
  NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE "firebasereader_specimen-digitization-database_public"
  NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
-- Downward membership only. Permanent managed grantor avoids a temporary user dependency.
GRANT "firebaseowner_specimen-digitization-database_public",
      "firebasewriter_specimen-digitization-database_public",
      "firebasereader_specimen-digitization-database_public"
  TO cloudsqlsuperuser WITH INHERIT TRUE, SET TRUE;
GRANT CREATE ON DATABASE "specimen-digitization-database"
  TO "firebaseowner_specimen-digitization-database_public";
ALTER SCHEMA public OWNER TO "firebaseowner_specimen-digitization-database_public";
REVOKE CREATE ON DATABASE "specimen-digitization-database"
  FROM "firebaseowner_specimen-digitization-database_public";
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE CONNECT, TEMPORARY ON DATABASE "specimen-digitization-database" FROM PUBLIC;
GRANT CONNECT ON DATABASE "specimen-digitization-database" TO
  "firebaseowner_specimen-digitization-database_public",
  "firebasewriter_specimen-digitization-database_public",
  "firebasereader_specimen-digitization-database_public";
GRANT USAGE ON SCHEMA public TO
  "firebasewriter_specimen-digitization-database_public",
  "firebasereader_specimen-digitization-database_public";
GRANT "firebaseowner_specimen-digitization-database_public"
  TO "specimen-data-release@specimen-digitization.iam" WITH ADMIN FALSE, INHERIT TRUE, SET TRUE;
GRANT "firebasewriter_specimen-digitization-database_public"
  TO "service-716045864126@gcp-sa-firebasedataconnect.iam" WITH ADMIN FALSE, INHERIT TRUE, SET TRUE;
ALTER DEFAULT PRIVILEGES FOR ROLE "firebaseowner_specimen-digitization-database_public"
  IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES
  TO "firebasewriter_specimen-digitization-database_public";
ALTER DEFAULT PRIVILEGES FOR ROLE "firebaseowner_specimen-digitization-database_public"
  IN SCHEMA public GRANT SELECT ON TABLES TO "firebasereader_specimen-digitization-database_public";
ALTER DEFAULT PRIVILEGES FOR ROLE "firebaseowner_specimen-digitization-database_public"
  IN SCHEMA public GRANT USAGE ON SEQUENCES TO "firebasewriter_specimen-digitization-database_public";
-- No user objects existed, so there are no existing tables/sequences/functions to grant.
-- Add no extensions, function EXECUTE defaults, owner elevation, or arbitrary SQL here.
-- Executor must run fixed postconditions in this transaction before COMMIT, including
-- exact role flags/membership directions, schema owner/ACL, no source object changes,
-- default privileges, and no ownership/grant dependency on the initializer identity.
-- The fixed executor verifies initialize_postconditions.sql before COMMIT.
