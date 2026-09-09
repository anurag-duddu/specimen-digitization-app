"""Real Node boundary with synthetic catalog data shaped like managed Cloud SQL.

The public managed database names/owners and native database fields reproduce
an observed PG18 catalog. Private roles/ACLs are not copied. Required ordinary
roles below model a later no-role registration; this fixture is not live proof.
"""
import copy
import json
import os
import subprocess
import time

import pytest

import release_initialize as init
from test_initialization_catalog_privacy import catalog_keys


def catalog_fixture(managed=True, capability=False):
    def database(name, owner):
        return {"name": name, "owner": owner, "encoding": 6, "collation": "en_US.UTF8",
                "ctype": "en_US.UTF8", "locale_provider": "c", "locale": None,
                "collation_version": "2.19", "acl": None}
    def narrow(name):
        return {"name": name, "login": True, "super": False, "create_role": False,
                "create_db": False, "replication": False, "bypass_rls": False}
    value = {"server_major": 18, "databases": [database("postgres", "cloudsqlsuperuser")],
        "roles": [narrow(init.MAINTENANCE), narrow(init.AGENT)], "memberships": [],
        "namespaces": [{"name": "public", "owner": "pg_database_owner", "acl": None}],
        "extensions": [{"name": "plpgsql", "version": "1.0"}],
        **{name: 0 for name in ("user_relations", "user_routines", "user_types", "event_triggers",
                               "publications", "foreign_servers", "foreign_wrappers", "large_objects")}}
    value["roles"].append({**narrow("cloudsqliamserviceaccount"), "login": False,
        "inherit": True, "config": None, "connection_limit": -1, "valid_until": None})
    for member in (init.MAINTENANCE, init.AGENT):
        value["memberships"].append({"role": "cloudsqliamserviceaccount", "member": member,
            "grantor": "cloudsqladmin", "admin": False, "set": True, "inherit": True})
    if managed:
        value["databases"].insert(0, database("cloudsqladmin", "cloudsqladmin"))
    if capability:
        value["roles"].append(narrow(init.INITIALIZER_SQL))
        value["memberships"].append({"role": "cloudsqliamserviceaccount", "member": init.INITIALIZER_SQL,
            "grantor": "cloudsqladmin", "admin": False, "set": True, "inherit": True})
        value["memberships"].append({"role": "cloudsqlsuperuser", "member": init.INITIALIZER_SQL,
                                    "grantor": "cloudsqlsuperuser", "admin": False, "set": True, "inherit": True})
    return value


def environment(tmp_path, catalog, mode="absence", **overrides):
    modules = tmp_path / "node_modules"
    for name in ("firebase-tools", "pg", "@google-cloud/cloud-sql-connector"):
        directory = modules / name
        directory.mkdir(parents=True)
        (directory / "package.json").write_text('{"version":"15.8.0","main":"index.js"}')
    (modules / "@google-cloud/cloud-sql-connector/index.js").write_text('''
const fs=require('node:fs');
exports.AuthTypes={IAM:'IAM'};exports.IpAddressTypes={PUBLIC:'PUBLIC'};
exports.Connector=class{async getOptions(){return {}}close(){fs.appendFileSync(process.env.TEST_TRACE,'connector.close\\n')}};
''')
    (modules / "pg/index.js").write_text('''
const fs=require('node:fs'),assert=require('node:assert/strict'),env=process.env;
const trace=x=>fs.appendFileSync(env.TEST_TRACE,x+'\\n');
exports.Pool=class{
constructor(o){assert.equal(o.database,'postgres');assert.equal(o.user,env.TEST_ACTOR)}
async connect(){return {release(force){assert.equal(force,true);trace('release')},async query(sql){
 if(sql.includes('current_database()'))return {rows:[{database:env.TEST_DATABASE||'postgres',actor:env.TEST_ACTOR,effective:env.TEST_ACTOR}]};
 if(sql.includes('backend_type='))return {rows:[{count:Number(env.TEST_SESSIONS||0)}]};
 if(sql==='BEGIN READ ONLY'||sql==='ROLLBACK'){trace(sql);return {rows:[]}};
 if(sql===fs.readFileSync('scripts/ci/initialize_catalog.sql','utf8'))return {rows:[{catalog:JSON.parse(fs.readFileSync(env.TEST_CATALOG))}]};
 if(sql.includes('pg_has_role(')||sql.includes('has_database_privilege('))return {rows:[{elevated:false}]};
 if(sql.includes('SELECT EXISTS(SELECT 1 FROM pg_roles'))return {rows:[{present:false}]};
 if(sql==='SET LOCAL ROLE cloudsqlsuperuser'){trace(sql);return {rows:[]}};
 if(sql.includes('rolcreaterole AS create_role'))return {rows:[{actor:'cloudsqlsuperuser',create_role:true}]};
 throw Error('unexpected query');}}}
async end(){trace('pool.end')}
};
''')
    source = tmp_path / "synthetic-catalog.json"
    source.write_text(json.dumps(catalog)); source.chmod(0o600)
    actor = init.INITIALIZER_SQL if mode == "capability" else init.MAINTENANCE
    return {"PATH": os.environ["PATH"], "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": "anurag-duddu/specimen-digitization-app", "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/heads/main", "GITHUB_REF_PROTECTED": "true",
        "GITHUB_WORKFLOW_REF": "anurag-duddu/specimen-digitization-app/.github/workflows/data-release.yml@refs/heads/main",
        "GITHUB_SHA": "a" * 40, "RELEASE_AUTHORIZED_SHA": "a" * 40,
        "DEPLOYMENT_ENVIRONMENT": "data-initialization-production" if mode == "capability" else "data-production",
        "RELEASE_SERVICE_ACCOUNT": actor + ".gserviceaccount.com", "RELEASE_NODE_ROOT": str(tmp_path),
        "INITIALIZATION_DEADLINE": str(int(time.time()) + 180), "INITIALIZATION_FILES": json.dumps(init.fingerprints()),
        "TEST_ACTOR": actor, "TEST_CATALOG": str(source), "TEST_TRACE": str(tmp_path / "trace.txt"), **overrides}


def run_node(tmp_path, catalog, mode="absence", instance=init.SOURCE, **overrides):
    env = environment(tmp_path, catalog, mode, **overrides)
    target = tmp_path / "private-result.json"
    result = subprocess.run(["node", "scripts/ci/release_initialize.mjs", mode, instance, str(target)],
                            cwd=init.ROOT, env=env, capture_output=True, timeout=10)
    value = json.loads(target.read_bytes()) if target.exists() else None
    return result, value, (tmp_path / "trace.txt").read_text().splitlines()


@pytest.mark.parametrize("instance", [init.SOURCE, init.CLONE])
@pytest.mark.parametrize("mode", ["absence", "capability"])
@pytest.mark.parametrize("managed", [True, False])
def test_managed_database_or_plain_postgres_qualifies_without_dropping_catalog(tmp_path, instance, mode, managed):
    before = catalog_fixture(managed, mode == "capability")
    expected = catalog_fixture(managed)
    result, observed, trace = run_node(tmp_path, before, mode, instance)
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == result.stderr == b""
    assert observed["qualified"] is True and observed["catalog"] == expected
    assert init.sha(observed["catalog"]) == init.sha(expected)
    assert trace[0] == "BEGIN READ ONLY" and trace[-4:] == ["ROLLBACK", "release", "pool.end", "connector.close"]
    if managed:
        stripped = copy.deepcopy(expected); stripped["databases"] = stripped["databases"][1:]
        assert init.sha(observed["catalog"]) != init.sha(stripped), "managed DB remains inside parity evidence"


@pytest.mark.parametrize("mode", ["absence", "capability"])
@pytest.mark.parametrize("fault", ["wrong-owner", "missing-owner", "user-database", "application-database",
                                   "duplicate-managed", "wrong-case", "managed-only"])
def test_unknown_database_or_managed_owner_blocks_and_preserves_rejected_facts(tmp_path, mode, fault):
    catalog = catalog_fixture(True, mode == "capability")
    if fault == "wrong-owner": catalog["databases"][0]["owner"] = "synthetic-user"
    elif fault == "missing-owner": del catalog["databases"][0]["owner"]
    elif fault in {"user-database", "application-database"}:
        catalog["databases"].append({"name": init.DATABASE if fault == "application-database" else "user-database", "owner": "synthetic-user"})
    elif fault == "duplicate-managed": catalog["databases"].insert(0, copy.deepcopy(catalog["databases"][0]))
    elif fault == "wrong-case": catalog["databases"][0]["name"] = "CloudSQLAdmin"
    else: catalog["databases"].pop()
    result, observed, trace = run_node(tmp_path, catalog, mode)
    assert result.returncode == 1 and result.stdout == b""
    assert json.loads(result.stderr) == {"version": "release-diagnostic/v1", "stage": "node.catalog-validate"}
    assert observed["qualified"] is False and observed["catalog"] == catalog
    assert "SET LOCAL ROLE cloudsqlsuperuser" not in trace
    assert trace[-3:] == ["release", "pool.end", "connector.close"]


@pytest.mark.parametrize("fault", ["user-object", "namespace", "session", "context", "missing-agent"])
def test_managed_database_does_not_bypass_other_absence_guards(tmp_path, fault):
    catalog = catalog_fixture(); overrides = {}
    if fault == "user-object": catalog["user_types"] = 1
    elif fault == "namespace": catalog["namespaces"].append({"name": "pgx"})
    elif fault == "missing-agent": catalog["roles"] = catalog["roles"][:1]
    elif fault == "session": overrides["TEST_SESSIONS"] = "1"
    else: overrides["TEST_DATABASE"] = "wrong"
    result, observed, trace = run_node(tmp_path, catalog, **overrides)
    assert result.returncode == 1 and result.stdout == b""
    assert observed is None or observed["qualified"] is False
    assert trace[-3:] == ["release", "pool.end", "connector.close"]


def test_managed_metadata_drift_is_retained_encrypted_and_rejected_by_full_catalog_hash(tmp_path, monkeypatch, catalog_keys):
    recipient, private = catalog_keys
    expected = catalog_fixture()
    changed = copy.deepcopy(expected); changed["databases"][0]["collation_version"] = "synthetic-drift"
    env = environment(tmp_path, changed)
    for key, value in env.items(): monkeypatch.setenv(key, value)
    provenance = {"repository": "anurag-duddu/specimen-digitization-app", "source_sha": "a" * 40, "run_id": 123, "run_attempt": 1}
    with pytest.raises(ValueError):
        init.native(tmp_path, init.SOURCE, "absence", files=init.fingerprints(), deadline=int(time.time()) + 180,
                    expected_catalog=init.sha(expected), recipient=recipient, provenance=provenance)
    encrypted = tmp_path / f"{init.SOURCE}-absence.encrypted.json"
    assert encrypted.exists() and not (tmp_path / f"{init.SOURCE}-absence.json").exists()
    from release_catalog_envelope import decrypt_catalog
    monkeypatch.delenv("GITHUB_ACTIONS")
    clear = json.loads(decrypt_catalog(json.loads(encrypted.read_bytes()), private,
        public_key_sha256=recipient["public_key_sha256"], provenance=provenance))
    assert clear["qualified"] is True, "the native managed-name check passes; the unchanged full parity hash rejects drift"
    assert clear["catalog"] == changed and init.sha(clear["catalog"]) != init.sha(expected)
