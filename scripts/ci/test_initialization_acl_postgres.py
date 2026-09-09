"""Independent local-only fault injection; no cloud connection or original source edit."""
from pathlib import Path
import pytest
from test_initialization_postgres import postgres, pytestmark
import release_initialize as init

SQL=(init.ROOT/'scripts/ci/initialize_database.sql').read_text()
POST=(init.ROOT/'scripts/ci/initialize_postconditions.sql').read_text()
OWNER='firebaseowner_specimen-digitization-database_public'
WRITER='firebasewriter_specimen-digitization-database_public'
READER='firebasereader_specimen-digitization-database_public'
CASES={
 'reader_default_missing':f'ALTER DEFAULT PRIVILEGES FOR ROLE "{OWNER}" IN SCHEMA public REVOKE SELECT ON TABLES FROM "{READER}";',
 'writer_schema_usage_missing':f'REVOKE USAGE ON SCHEMA public FROM "{WRITER}";',
 'reader_schema_usage_missing':f'REVOKE USAGE ON SCHEMA public FROM "{READER}";',
 'public_schema_create': 'GRANT CREATE ON SCHEMA public TO PUBLIC;',
 'public_database_connect':f'GRANT CONNECT ON DATABASE "{init.DATABASE}" TO PUBLIC;',
 'public_default_insert':f'ALTER DEFAULT PRIVILEGES FOR ROLE "{OWNER}" IN SCHEMA public GRANT INSERT ON TABLES TO PUBLIC;',
 'reader_extra_insert':f'SET LOCAL ROLE "{OWNER}"; CREATE TABLE public.review_probe(id integer); GRANT INSERT ON public.review_probe TO "{READER}"; SET LOCAL ROLE cloudsqlsuperuser;',
 'writer_extra_references':f'SET LOCAL ROLE "{OWNER}"; CREATE TABLE public.review_probe(id integer); GRANT REFERENCES ON public.review_probe TO "{WRITER}"; SET LOCAL ROLE cloudsqlsuperuser;',
 'reader_global_delete':f'ALTER DEFAULT PRIVILEGES FOR ROLE "{OWNER}" GRANT DELETE ON TABLES TO "{READER}";',
}

def test_valid_contract_passes(postgres):
    result=postgres(SQL+'\n'+POST+'\nROLLBACK;',actor=init.INITIALIZER_SQL,database=init.DATABASE)
    assert result.returncode==0,result.stderr.decode()

@pytest.mark.parametrize('case',CASES)
def test_contract_drift_must_be_rejected(postgres,case):
    result=postgres(SQL+'\n'+CASES[case]+'\n'+POST+'\nROLLBACK;',actor=init.INITIALIZER_SQL,database=init.DATABASE)
    assert result.returncode != 0, f'{case}: postconditions accepted permission drift'

@pytest.mark.parametrize('grant', [
 'GRANT pg_write_all_data TO "specimen-worker-runtime@specimen-digitization.iam";',
 'CREATE ROLE unrelated_elevated CREATEROLE; GRANT unrelated_elevated TO "specimen-worker-runtime@specimen-digitization.iam" WITH SET TRUE;'
])
def test_other_global_runtime_privilege_paths_rejected(postgres,grant):
    setup=postgres('CREATE ROLE "specimen-worker-runtime@specimen-digitization.iam" LOGIN; '+grant)
    assert setup.returncode==0,setup.stderr.decode()
    result=postgres(SQL+'\n'+POST+'\nROLLBACK;',actor=init.INITIALIZER_SQL,database=init.DATABASE)
    assert result.returncode!=0,'runtime global privilege path outside cloudsqlsuperuser was accepted'

@pytest.mark.parametrize('role',[OWNER,WRITER,READER])
def test_unreviewed_application_role_recipient_is_rejected(postgres,role):
    assert postgres('CREATE ROLE unrelated_login LOGIN;').returncode==0
    result=postgres(SQL+f'\nGRANT "{role}" TO unrelated_login WITH INHERIT TRUE, SET TRUE;\n'+POST+'\nROLLBACK;',
        actor=init.INITIALIZER_SQL,database=init.DATABASE)
    assert result.returncode!=0,'unreviewed application-role recipient was accepted'

@pytest.mark.parametrize('drift',[
    f'SET ROLE cloudsqlsuperuser; GRANT "{OWNER}" TO cloudsqlsuperuser WITH INHERIT FALSE, SET FALSE; RESET ROLE;',
    f'GRANT "{OWNER}" TO "{init.MAINTENANCE}" WITH ADMIN FALSE, INHERIT TRUE, SET TRUE;',
    f'GRANT "{WRITER}" TO "{init.AGENT}" WITH ADMIN FALSE, INHERIT TRUE, SET TRUE;',
])
def test_unreviewed_grantor_or_managed_membership_options_are_rejected(postgres,drift):
    # Superuser injection emulates externally introduced catalog drift; the
    # ordinary transaction and postconditions still execute as the initializer.
    assert postgres(SQL+'\nCOMMIT;',actor=init.INITIALIZER_SQL,database=init.DATABASE).returncode==0
    result=postgres(drift,database=init.DATABASE)
    assert result.returncode==0,result.stderr.decode()
    result=postgres(POST,database=init.DATABASE)
    assert result.returncode!=0,'unreviewed application membership grantor/options were accepted'
