"""Synthetic native replies exercise the actual Node guards; no cloud or SQL.

The marker shape comes from a signed ordinary-IAM catalog. Initializer replies
are test cases, not a claim that native CREATE/UPDATE behavior was observed.
"""
import copy
import json
import subprocess

import pytest

import release_initialize as init
from test_managed_cloudsql_database import catalog_fixture, environment


MARKER = "cloudsqliamserviceaccount"


def fixture(mode):
    value = catalog_fixture(capability=True)
    if mode != "capability":
        value["memberships"] = [r for r in value["memberships"] if r["role"] != "cloudsqlsuperuser"]
    return value


def execute(tmp_path, catalog, mode, fault=""):
    env = environment(tmp_path, catalog, mode)
    if mode == "clean":
        env.update(DEPLOYMENT_ENVIRONMENT="data-initialization-production",
                   RELEASE_SERVICE_ACCOUNT=init.INITIALIZER_SQL + ".gserviceaccount.com",
                   TEST_ACTOR=init.INITIALIZER_SQL)
    env["TEST_FAULT"] = fault
    pg = tmp_path / "node_modules/pg/index.js"
    code = pg.read_text()
    code = code.replace("throw Error('unexpected query');", '''
 const catalog=JSON.parse(fs.readFileSync(env.TEST_CATALOG));
 const actor=catalog.roles.find(r=>r.name==='specimen-data-initialize@specimen-digitization.iam');
 const safe=actor && !['super','create_role','create_db','replication','bypass_rls'].some(k=>actor[k]);
 if(sql.includes('pg_stat_activity'))return {rows:[{count:env.TEST_FAULT==='sessions'?1:0}]};
 if(sql.startsWith('SELECT oid,NOT'))return {rows:actor?[{oid:123,narrow:safe}]:[]};
 if(sql.includes('count(*)::int AS count FROM pg_auth_members'))return {rows:[{count:catalog.memberships.filter(r=>r.member===actor.name).length}]};
 if(sql.startsWith('SELECT NOT (rolsuper'))return {rows:[{safe}]};
 if(sql==='SET ROLE cloudsqlsuperuser'){trace('SET ROLE denied probe');if(env.TEST_FAULT==='set-allowed')return {};const e=Error('synthetic denial');e.code='42501';throw e;}
 if(sql.includes('pg_shdepend'))return {rows:[{count:env.TEST_FAULT==='dependencies'?1:0}]};
 throw Error('unexpected query');''')
    pg.write_text(code)
    output = tmp_path / "result.json"
    result = subprocess.run(["node", "scripts/ci/release_initialize.mjs", mode, init.CLONE, str(output)],
                            cwd=init.ROOT, env=env, capture_output=True, timeout=10)
    observed = json.loads(output.read_bytes()) if output.exists() else None
    return result, observed, (tmp_path / "trace.txt").read_text().splitlines()


@pytest.mark.parametrize("mode", ["capability", "clean", "disposal-check"])
def test_system_marker_is_preserved_while_only_temporary_privilege_is_removed(tmp_path, mode):
    before = fixture(mode)
    result, observed, trace = execute(tmp_path, before, mode)
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == result.stderr == b""
    if mode == "capability":
        assert observed["qualified"] is True
        assert observed["capability"]["memberships"] == [r for r in before["memberships"] if r["member"] == init.INITIALIZER_SQL]
        assert observed["catalog"] == catalog_fixture(), "only temporary actor edges leave the parity projection"
    elif mode == "clean":
        assert observed["roles_revoked"] and observed["privileged_set_denied"]
        assert "SET ROLE denied probe" in trace
    else:
        assert observed["verified"] is True
    if mode != "capability":
        assert "catalog" not in observed
    assert trace[-3:] == ["release", "pool.end", "connector.close"]


@pytest.mark.parametrize("mode", ["absence", "capability", "clean", "disposal-check"])
@pytest.mark.parametrize("fault", ["missing", "duplicate", "wrong-grantor", "admin", "no-inherit", "no-set",
                                   "marker-elevated", "marker-login", "marker-parent", "marker-config", "extra-role"])
def test_authentication_marker_is_not_a_general_membership_exception(tmp_path, mode, fault):
    value = fixture(mode)
    if mode == "absence":
        value = catalog_fixture()
    actor = init.MAINTENANCE if mode == "absence" else init.INITIALIZER_SQL
    edge = next(r for r in value["memberships"] if r["member"] == actor and r["role"] == MARKER)
    role = next(r for r in value["roles"] if r["name"] == MARKER)
    if fault == "missing": value["memberships"].remove(edge)
    elif fault == "duplicate": value["memberships"].append(copy.deepcopy(edge))
    elif fault == "wrong-grantor": edge["grantor"] = "unreviewed-grantor"
    elif fault == "admin": edge["admin"] = True
    elif fault == "no-inherit": edge["inherit"] = False
    elif fault == "no-set": edge["set"] = False
    elif fault == "marker-elevated": role["create_db"] = True
    elif fault == "marker-login": role["login"] = True
    elif fault == "marker-config": role["config"] = ["role=cloudsqlsuperuser"]
    elif fault == "marker-parent": value["memberships"].append({**edge, "member": MARKER, "role": "cloudsqlsuperuser"})
    else: value["memberships"].append({**edge, "role": "pg_read_all_data"})
    result, observed, _ = execute(tmp_path, value, mode)
    assert result.returncode == 1 and result.stdout == b""
    assert json.loads(result.stderr) == {"version": "release-diagnostic/v1", "stage":
        "node.clean" if mode == "clean" else "node.disposal" if mode == "disposal-check" else "node.catalog-validate"}
    if observed and mode in {"absence", "capability"}:
        assert observed["qualified"] is False and observed["catalog"] == value


@pytest.mark.parametrize("mode,fault", [("clean", "set-allowed"), ("clean", "dependencies"),
    ("disposal-check", "dependencies"), ("disposal-check", "sessions")])
def test_marker_does_not_relax_disposal_guards(tmp_path, mode, fault):
    result, _, _ = execute(tmp_path, fixture(mode), mode, fault)
    assert result.returncode == 1 and result.stdout == b""


def test_inspection_keeps_unqualified_role_facts_without_faking_absence(tmp_path):
    value = fixture("capability")
    next(r for r in value["roles"] if r["name"] == MARKER)["super"] = True
    result, observed, _ = execute(tmp_path, value, "inspect")
    assert result.returncode == 0 and result.stderr == b""
    assert observed["catalog"] == value, "inspection reports facts; it grants no initialization capability"
