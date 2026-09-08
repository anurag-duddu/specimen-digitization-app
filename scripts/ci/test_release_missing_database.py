"""Missing application databases stay distinct from observed empty schemas."""
import json
import os
from pathlib import Path
import subprocess

import pytest

import deploy_data as data


@pytest.mark.parametrize("mode, selector", [
    ("initialize_empty", "schemaMigration"), ("validate_existing", "schemaValidation"),
])
def test_actual_deploy_uses_same_valid_union_for_validate_only_and_apply(tmp_path, monkeypatch, mode, selector):
    from test_data_release import plan
    prepared = plan()
    prepared.update(schema_mode=mode, schema_etag=None, connector_etag=None)
    calls = []
    recovery = []
    class StopAfterSchemaRequest(Exception):
        pass
    class Google:
        packet = {"source_sha": prepared["source_sha"]}
        def wait(self, *args):
            pytest.fail("test stops before native operation waiting")
        def request(self, api, method, resource, **kwargs):
            if method == "GET":
                return None
            assert recovery == ["verified"], "schema effects require native recovery first"
            assert api == "data" and method == "PATCH" and resource.endswith("/schemas/main")
            calls.append(json.loads(json.dumps(kwargs)))
            if len(calls) == 2:
                raise StopAfterSchemaRequest
            return {}
    monkeypatch.setattr(data, "Google", lambda *args: Google())
    monkeypatch.setattr(data, "read_bound_plan", lambda *args: prepared)
    monkeypatch.setattr(data.time, "time", lambda: 1788890400)
    monkeypatch.setattr(data, "rehearse", lambda *args: recovery.append("verified") or {"rows": []})
    with pytest.raises(StopAfterSchemaRequest):
        data.deploy(tmp_path / "packet.json", tmp_path / "output.json")
    assert calls[0]["params"] == {"allowMissing": "true", "validateOnly": "true"}
    assert calls[1]["params"] == {"allowMissing": "true"}
    assert calls[0]["body"] == calls[1]["body"]
    postgres = calls[0]["body"]["datasources"][0]["postgresql"]
    assert set(postgres).intersection({"schemaValidation", "schemaMigration"}) == {selector}


@pytest.mark.parametrize("mode, selector, value", [
    ("initialize_empty", "schemaMigration", "MIGRATE_COMPATIBLE"),
    ("validate_existing", "schemaValidation", "COMPATIBLE"),
])
def test_schema_before_deploy_selects_exactly_one_supported_union_member(mode, selector, value):
    schema, _ = data.data_bodies({"schema_mode": mode, "schema_etag": None, "connector_etag": None})
    postgres = schema["datasources"][0]["postgresql"]
    assert set(postgres).intersection({"schemaValidation", "schemaMigration"}) == {selector}
    assert postgres[selector] == value


def catalog(*, exists=False, observed=False):
    value = {key: False for key in data.CATALOG_BOOLEANS}
    value.update(expected_database=True, expected_actor=True,
                 application_database_exists=exists, application_catalog_observed=observed,
                 approved_tables=[], public_table_count=0, unapproved_table_count=0)
    return value


def test_missing_database_is_valid_metadata_without_empty_schema_claim():
    observed = catalog()
    assert data.validate_catalog(observed) == observed
    assert observed["application_database_exists"] is False
    assert observed["application_catalog_observed"] is False


@pytest.mark.parametrize("key", ["expected_actor", "expected_database"])
def test_wrong_metadata_actor_or_database_is_rejected(key):
    observed = catalog()
    observed[key] = False
    with pytest.raises(ValueError, match="database or maintenance identity"):
        data.validate_catalog(observed)


@pytest.mark.parametrize("change", [
    {"application_catalog_observed": True},
    {"application_database_exists": True},
    {"approved_tables": ["specimen"], "public_table_count": 1},
    {"current_can_select_all_public_tables": True},
    {"owner_public_schema": True},
    {"owner_only_approved_tables_in_database": True},
    {"application_database_exists": 0},
])
def test_absence_never_qualifies_application_catalog_claims(change):
    observed = catalog()
    observed.update(change)
    with pytest.raises(ValueError):
        data.validate_catalog(observed)


def run_node(tmp_path, *, exists=False, wrong_actor=False, wrong_database=False):
    modules = tmp_path / "node_modules"
    for path in (modules / "firebase-tools", modules / "pg", modules / "@google-cloud/cloud-sql-connector"):
        path.mkdir(parents=True)
        (path / "package.json").write_text('{"version":"15.8.0","main":"index.js"}')
    (modules / "@google-cloud/cloud-sql-connector/index.js").write_text('''
exports.AuthTypes = {IAM: 'IAM'};
exports.IpAddressTypes = {PUBLIC: 'PUBLIC'};
exports.Connector = class { async getOptions() { return {}; } close() {} };
''')
    (modules / "pg/index.js").write_text('''
const fs = require('node:fs');
exports.Pool = class {
  constructor(options) {
    this.database = options.database;
    fs.appendFileSync(process.env.TEST_SQL_POOLS, this.database + '\\n');
    if (this.database !== 'postgres' && process.env.TEST_APP_EXISTS !== 'true')
      throw new Error('application connection forbidden when database is absent');
  }
  async connect() {
    const database = this.database;
    return {release() {}, async query(sql) {
      if (sql === 'SELECT current_database() AS name')
        return {rows: [{name: process.env.TEST_WRONG_DATABASE === 'true' ? 'unrelated' : database}]};
      const value = JSON.parse(fs.readFileSync(process.env.TEST_SQL_CATALOG, 'utf8'));
      value.application_catalog_observed = database === 'specimen-digitization-database';
      return [{command: 'SELECT', rows: [value]}];
    }};
  }
  async end() {}
};
''')
    expected = catalog(exists=exists)
    expected["expected_actor"] = not wrong_actor
    metadata = tmp_path / "mock-catalog.json"
    metadata.write_text(json.dumps(expected))
    output = tmp_path / "catalog.json"
    log = tmp_path / "pools.log"
    env = dict(os.environ, RELEASE_NODE_ROOT=str(tmp_path), TEST_SQL_CATALOG=str(metadata),
               TEST_SQL_POOLS=str(log), TEST_APP_EXISTS=str(exists).lower(),
               TEST_WRONG_DATABASE=str(wrong_database).lower(), GITHUB_ACTIONS="true",
               GITHUB_REPOSITORY="anurag-duddu/specimen-digitization-app", GITHUB_EVENT_NAME="push",
               GITHUB_REF="refs/heads/main", DEPLOYMENT_ENVIRONMENT="data-production",
               GITHUB_WORKFLOW_REF="anurag-duddu/specimen-digitization-app/.github/workflows/data-release.yml@refs/heads/main",
               RELEASE_AUTHORIZED_SHA="a" * 40, GITHUB_SHA="a" * 40)
    result = subprocess.run(["node", str(Path(data.__file__).with_name("release_sql.mjs")),
                             "catalog", data.SOURCE, str(output)], env=env, cwd=data.ROOT,
                            capture_output=True, timeout=10)
    return result, output, log.read_text().splitlines()


def test_actual_node_never_connects_to_missing_application_database(tmp_path):
    result, output, pools = run_node(tmp_path)
    assert result.returncode == 0, result.stderr.decode()
    assert pools == ["postgres"]
    assert data.validate_catalog(json.loads(output.read_text())) == catalog()


def test_actual_node_observes_existing_application_after_control_catalog(tmp_path):
    result, output, pools = run_node(tmp_path, exists=True)
    assert result.returncode == 0, result.stderr.decode()
    assert pools == ["postgres", data.DATABASE]
    assert data.validate_catalog(json.loads(output.read_text())) == catalog(exists=True, observed=True)


@pytest.mark.parametrize("kwargs", [{"wrong_actor": True}, {"wrong_database": True}])
def test_actual_node_refuses_wrong_control_identity_before_application_connection(tmp_path, kwargs):
    result, output, pools = run_node(tmp_path, exists=True, **kwargs)
    assert result.returncode != 0
    assert not output.exists()
    assert pools == ["postgres"]
