"""Opt-in PostgreSQL18 semantics; this does not emulate managed Cloud SQL roles."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

import pytest

import release_initialize as initialization

BIN = Path('/opt/homebrew/opt/postgresql@18/bin')
pytestmark = pytest.mark.skipif(os.getenv('SPECIMEN_TEST_INITIALIZATION_PG') != 'true',
                               reason='requires explicitly authorized isolated local PostgreSQL18')


@pytest.fixture
def postgres(tmp_path):
    # macOS Unix socket addresses are shorter than pytest's nested temp path.
    socket_dir = tempfile.TemporaryDirectory(prefix='specimen-init-pg-', dir='/tmp')
    assert BIN.joinpath('postgres').is_file(), 'PostgreSQL18 is required, not silently skipped'
    def command(*args, **kw):
        return subprocess.run(list(map(str,args)), capture_output=True, timeout=30, **kw)
    result = command(BIN/'initdb','-D',tmp_path/'cluster','-U','cloudsqladmin','-A','trust','--no-locale')
    assert result.returncode == 0, result.stderr.decode()
    result = command(BIN/'pg_ctl','-D',tmp_path/'cluster','-l',tmp_path/'postgres.log',
                     '-o',f"-h '' -k {socket_dir.name} -p 5669",'start')
    assert result.returncode == 0, (tmp_path/'postgres.log').read_text()
    def sql(text, *, actor=None, database='postgres'):
        args = [BIN/'psql','-h',socket_dir.name,'-p','5669','-d',database,'-v','ON_ERROR_STOP=1','-At']
        args += ['-U',actor or 'cloudsqladmin']
        return command(*args,input=text.encode())
    try:
        setup = f'''
          CREATE ROLE cloudsqlsuperuser NOLOGIN NOSUPERUSER CREATEROLE CREATEDB;
          CREATE ROLE "{initialization.INITIALIZER_SQL}" LOGIN;
          CREATE ROLE "{initialization.MAINTENANCE}" LOGIN;
          CREATE ROLE "{initialization.AGENT}" LOGIN;
          CREATE ROLE cloudsqliamserviceaccount NOLOGIN;
          GRANT cloudsqliamserviceaccount TO "{initialization.INITIALIZER_SQL}",
            "{initialization.MAINTENANCE}", "{initialization.AGENT}"
            WITH ADMIN FALSE, INHERIT TRUE, SET TRUE;
          GRANT cloudsqlsuperuser TO "{initialization.INITIALIZER_SQL}" WITH SET TRUE;
          CREATE DATABASE "{initialization.DATABASE}" OWNER cloudsqlsuperuser;
        '''
        result=sql(setup)
        assert result.returncode == 0, result.stderr.decode()
        sql.socket=socket_dir.name
        yield sql
    finally:
        result=command(BIN/'pg_ctl','-D',tmp_path/'cluster','-m','fast','stop')
        assert result.returncode == 0, result.stderr.decode()
        socket_dir.cleanup()


def transaction(postgres):
    source=(initialization.ROOT/'scripts/ci/initialize_database.sql').read_text()
    post=(initialization.ROOT/'scripts/ci/initialize_postconditions.sql').read_text()
    return postgres(source+'\n'+post+'\nCOMMIT;',actor=initialization.INITIALIZER_SQL,database=initialization.DATABASE)


def test_pg18_fixed_transaction_preserves_owner_and_removes_initializer_dependencies(postgres):
    result=transaction(postgres)
    assert result.returncode == 0, result.stderr.decode()
    result=postgres(f'REVOKE cloudsqlsuperuser FROM "{initialization.INITIALIZER_SQL}";')
    assert result.returncode == 0, result.stderr.decode()
    result=postgres(f'''SELECT r.rolname FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid
      JOIN pg_roles u ON u.oid=m.member WHERE u.rolname='{initialization.INITIALIZER_SQL}';''')
    assert result.stdout.decode().strip() == 'cloudsqliamserviceaccount'
    assert postgres('SET ROLE cloudsqlsuperuser;',actor=initialization.INITIALIZER_SQL).returncode != 0
    result=postgres(f'DROP ROLE "{initialization.INITIALIZER_SQL}";')
    assert result.returncode == 0, result.stderr.decode()
    result=postgres('SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database();',database=initialization.DATABASE)
    assert result.stdout.decode().strip() == 'cloudsqlsuperuser'
    result=postgres((initialization.ROOT/'scripts/ci/initialize_postconditions.sql').read_text(),database=initialization.DATABASE)
    assert result.returncode == 0, 'ordinary postconditions still pass after exact initializer deletion'


def summary(postgres):
    """The release identity's value-free catalog summary (RELEASE.md 4.3 step 1), as psql prints its one row."""
    result=postgres((initialization.ROOT/'scripts/ci/release_sql_summary.sql').read_text(),
                    actor=initialization.MAINTENANCE,database=initialization.DATABASE)
    assert result.returncode == 0, result.stderr.decode()
    return next(line for line in result.stdout.decode().splitlines() if '|' in line)


def test_pg18_transaction_adds_exactly_uuid_ossp_for_the_writer_and_the_summary_sees_both_states(postgres):
    assert summary(postgres) == 't|t|0|0|0|0|{}|{}'
    result=transaction(postgres)
    assert result.returncode == 0, result.stderr.decode()
    result=postgres("SELECT pg_get_userbyid(extowner),extnamespace::regnamespace FROM pg_extension WHERE extname='uuid-ossp';",
                    database=initialization.DATABASE)
    assert result.stdout.decode().strip() == 'cloudsqlsuperuser|public'
    result=postgres('SELECT public.uuid_generate_v4() IS NOT NULL;',actor=initialization.AGENT,database=initialization.DATABASE)
    assert result.stdout.decode().strip() == 't', result.stderr.decode()
    roles=','.join(f'firebase{role}_{initialization.DATABASE}_public' for role in ('owner','reader','writer'))
    assert summary(postgres) == f't|t|0|0|10|0|{{uuid-ossp}}|{{{roles}}}'


def test_pg18_a_preexisting_uuid_ossp_is_never_adopted(postgres):
    assert postgres('CREATE EXTENSION "uuid-ossp" SCHEMA public;',database=initialization.DATABASE).returncode == 0
    result=transaction(postgres)
    assert result.returncode != 0 and 'unreviewed user objects' in result.stderr.decode()
    assert postgres("SELECT count(*) FROM pg_roles WHERE rolname LIKE 'firebase%';").stdout.decode().strip() == '0'


@pytest.mark.parametrize('change', [
    'ALTER ROLE cloudsqliamserviceaccount CREATEDB;',
    'ALTER ROLE cloudsqliamserviceaccount LOGIN;',
    'ALTER ROLE cloudsqliamserviceaccount SET role TO cloudsqlsuperuser;',
    'GRANT pg_read_all_data TO cloudsqliamserviceaccount;',
    f'REVOKE cloudsqliamserviceaccount FROM "{initialization.MAINTENANCE}";',
    f'GRANT cloudsqliamserviceaccount TO "{initialization.MAINTENANCE}" WITH ADMIN TRUE;',
    f'GRANT cloudsqliamserviceaccount TO "{initialization.AGENT}" WITH INHERIT FALSE;',
    f'GRANT cloudsqliamserviceaccount TO "{initialization.AGENT}" WITH SET FALSE;',
    f'GRANT pg_read_all_data TO "{initialization.MAINTENANCE}";',
    'CREATE ROLE unexpected_grantor; GRANT cloudsqliamserviceaccount TO unexpected_grantor WITH ADMIN TRUE; '
    f'SET ROLE unexpected_grantor; GRANT cloudsqliamserviceaccount TO "{initialization.MAINTENANCE}"; RESET ROLE;',
])
def test_pg18_marker_exception_cannot_hide_changed_privileges_or_edges(postgres, change):
    result=postgres(change)
    assert result.returncode == 0, result.stderr.decode()
    result=transaction(postgres)
    assert result.returncode != 0, 'unexpected managed marker privilege/edge was accepted'
    result=postgres("SELECT count(*) FROM pg_roles WHERE rolname LIKE 'firebase%';")
    assert result.stdout.decode().strip() == '0', 'failed marker qualification rolls back application roles'


def test_pg18_user_schema_pgx_is_not_treated_as_system(postgres):
    assert postgres('CREATE SCHEMA pgx; CREATE TABLE pgx.existing_source(id integer);',database=initialization.DATABASE).returncode == 0
    result=transaction(postgres)
    assert result.returncode != 0, 'a real user schema and source table must block initialization'
    assert 'unreviewed user objects' in result.stderr.decode()
    result=postgres("SELECT count(*) FROM pg_roles WHERE rolname LIKE 'firebase%';")
    assert result.stdout.decode().strip() == '0', 'failed initialization must roll back new roles'


@pytest.mark.parametrize('ddl',["CREATE TYPE public.review_status AS ENUM('x');",
                              'CREATE DOMAIN public.review_id AS integer;'])
def test_pg18_standalone_public_types_are_not_an_empty_database(postgres,ddl):
    assert postgres(ddl,database=initialization.DATABASE).returncode == 0
    result=transaction(postgres)
    assert result.returncode != 0 and 'unreviewed user objects' in result.stderr.decode()


def test_pg18_writer_has_crud_without_unjustified_truncate(postgres):
    result=transaction(postgres)
    assert result.returncode == 0, result.stderr.decode()
    result=postgres('''SET ROLE "firebaseowner_specimen-digitization-database_public";
      CREATE TABLE public.privilege_probe(id integer); RESET ROLE;
      SELECT has_table_privilege('firebasewriter_specimen-digitization-database_public',
        'public.privilege_probe','SELECT'),
        has_table_privilege('firebasewriter_specimen-digitization-database_public','public.privilege_probe','INSERT'),
        has_table_privilege('firebasewriter_specimen-digitization-database_public','public.privilege_probe','UPDATE'),
        has_table_privilege('firebasewriter_specimen-digitization-database_public','public.privilege_probe','DELETE'),
        has_table_privilege('firebasewriter_specimen-digitization-database_public','public.privilege_probe','TRUNCATE');''',
      database=initialization.DATABASE)
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout.decode().splitlines()[-1] == 't|t|t|t|f'


def test_pg18_unsupported_managed_role_capability_stops(postgres):
    assert postgres('ALTER ROLE cloudsqlsuperuser NOCREATEROLE;').returncode == 0
    result=transaction(postgres)
    assert result.returncode != 0 and 'unqualified native role creation capability' in result.stderr.decode()


def test_pg18_inherited_membership_does_not_make_maintenance_the_ddl_owner(postgres):
    assert transaction(postgres).returncode == 0
    result=postgres('CREATE TABLE public.wrong_creator(id integer);',actor=initialization.MAINTENANCE,database=initialization.DATABASE)
    assert result.returncode == 0
    result=postgres((initialization.ROOT/'scripts/ci/initialize_postconditions.sql').read_text(),database=initialization.DATABASE)
    assert result.returncode != 0 and 'DDL did not run as the reviewed owner' in result.stderr.decode()


def test_pg18_indirect_runtime_privilege_path_rolls_back_initialization(postgres):
    assert postgres('''CREATE ROLE runtime_parent;
      CREATE ROLE "specimen-worker-runtime@specimen-digitization.iam" LOGIN;
      GRANT cloudsqlsuperuser TO runtime_parent;
      GRANT runtime_parent TO "specimen-worker-runtime@specimen-digitization.iam";''').returncode == 0
    result=transaction(postgres)
    assert result.returncode != 0 and 'runtime SQL identity is outside' in result.stderr.decode()
    result=postgres("SELECT count(*) FROM pg_roles WHERE rolname LIKE 'firebase%';")
    assert result.stdout.decode().strip() == '0'


# T3c2 (RELEASE.md 4.3 steps 3 and 5): the real release_sql.mjs and the pg module firebase-tools 15.8.0 installs, as the
# release identity on this cluster. Only the Cloud SQL connector is replaced, by this cluster's socket.
PG_MODULE = Path('/opt/homebrew/lib/node_modules/firebase-tools/node_modules/pg')
OWNER = f'firebaseowner_{initialization.DATABASE}_public'
ORGANIZATION = ('CREATE TABLE "public"."organization" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "name" text NOT NULL, '
                'PRIMARY KEY ("id"))')
MEMBER = ('CREATE TABLE "public"."organization_member" ("organization_id" uuid NOT NULL, "uid" text NOT NULL, PRIMARY KEY '
          '("organization_id", "uid"), CONSTRAINT "organization_member_organization_id_fkey" FOREIGN KEY ("organization_id") '
          'REFERENCES "public"."organization" ("id") ON DELETE CASCADE)')
UNIQUE = 'CREATE UNIQUE INDEX "organization_name_uidx" ON "public"."organization" ("name")'


def release_sql(postgres, tmp_path, mode, *statements):
    assert PG_MODULE.joinpath('package.json').is_file(), 'the pg module of firebase-tools 15.8.0 is required, not skipped'
    modules = tmp_path / 'node_modules'
    for name in ('firebase-tools', '@google-cloud/cloud-sql-connector'):
        (modules / name).mkdir(parents=True, exist_ok=True)
        (modules / name / 'package.json').write_text('{"version":"15.8.0","main":"index.js"}')
    (modules / '@google-cloud/cloud-sql-connector/index.js').write_text("exports.AuthTypes={IAM:'IAM'};exports.IpAddressTypes="
        "{PUBLIC:'PUBLIC'};exports.Connector=class{async getOptions(){return {host:process.env.TEST_PG_HOST,port:5669}}close(){}};")
    if not (modules / 'pg').exists():
        (modules / 'pg').symlink_to(PG_MODULE)
    plan, output = tmp_path / 'migration.json', tmp_path / f'{mode}.json'
    plan.write_text(json.dumps({'version': 'data-migration/v1', 'source_sha': 'a' * 40, 'statements': list(statements),
                                'relaxed': []}))
    output.unlink(missing_ok=True)
    env = {'PATH': os.environ['PATH'], 'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'anurag-duddu/specimen-digitization-app',
           'GITHUB_SHA': 'a' * 40, 'RELEASE_GATE_SHA': 'a' * 40, 'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/main',
           'GITHUB_WORKFLOW_REF': 'anurag-duddu/specimen-digitization-app/.github/workflows/data-release.yml@refs/heads/main',
           'DEPLOYMENT_ENVIRONMENT': 'data-production', 'RELEASE_NODE_ROOT': str(tmp_path), 'TEST_PG_HOST': postgres.socket}
    result = subprocess.run(['node', 'scripts/ci/release_sql.mjs', mode, 'specimen-digitization-instance', str(output), str(plan)],
                            cwd=initialization.ROOT, env=env, capture_output=True, timeout=60)
    return result.returncode, json.loads(output.read_text()) if output.exists() else None


def relations(postgres):
    result = postgres("SELECT string_agg(relname || ':' || pg_get_userbyid(relowner), ',' ORDER BY relname) FROM pg_class "
                      "WHERE relnamespace = 'public'::regnamespace AND relkind IN ('r', 'i');", database=initialization.DATABASE)
    assert result.returncode == 0, result.stderr.decode()
    return result.stdout.decode().strip()


def test_pg18_the_migration_runs_as_the_owner_and_the_writer_inserts_with_uuid_generate_v4_defaults(postgres, tmp_path):
    assert transaction(postgres).returncode == 0
    assert release_sql(postgres, tmp_path, 'migrate', ORGANIZATION, MEMBER, UNIQUE) == (
        0, {'version': 'data-migration/v1', 'statements': 3, 'committed': True})
    assert relations(postgres) == ','.join(f'{name}:{OWNER}' for name in (
        'organization', 'organization_member', 'organization_member_pkey', 'organization_name_uidx', 'organization_pkey'))
    result = postgres("INSERT INTO public.organization (name) VALUES ('synthetic') RETURNING id IS NOT NULL;",
                      actor=initialization.AGENT, database=initialization.DATABASE)
    assert result.returncode == 0 and result.stdout.decode().splitlines()[0] == 't', result.stderr.decode()
    # The catalog check reads the same database back: the initializer's postconditions hold over the new tables.
    code, catalog = release_sql(postgres, tmp_path, 'migrated')
    assert code == 0 and catalog['postconditions']['schema_owner'] == OWNER
    assert {key: catalog[key] for key in ('expected_database', 'expected_actor', 'tables', 'views', 'owners', 'extensions')} == {
        'expected_database': True, 'expected_actor': True, 'tables': ['public.organization', 'public.organization_member'],
        'views': [], 'owners': [OWNER], 'extensions': ['plpgsql', 'uuid-ossp']}


def test_pg18_one_failing_statement_rolls_the_whole_migration_back(postgres, tmp_path):
    assert transaction(postgres).returncode == 0
    assert release_sql(postgres, tmp_path, 'migrate', ORGANIZATION)[0] == 0
    broken = 'CREATE TABLE "public"."broken" ("id" uuid REFERENCES "public"."missing" ("id"))'
    assert release_sql(postgres, tmp_path, 'migrate', MEMBER, UNIQUE, broken) == (1, None)
    assert relations(postgres) == f'organization:{OWNER},organization_pkey:{OWNER}'
