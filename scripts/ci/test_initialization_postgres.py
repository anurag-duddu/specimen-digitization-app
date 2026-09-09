"""Opt-in PostgreSQL18 semantics; this does not emulate managed Cloud SQL roles."""
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
