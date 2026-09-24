"""The first initialization on the gate path (RELEASE.md 4.3, T3c1): the Node connector serves an admitted gate
record's commit, the release identity reads the application database's summary, and the one-time initializer
commits on the source instance alone.

Synthetic connector and pg modules; never network, credentials or cloud.
"""
import json
import os
import subprocess
import time

import pytest

import deploy_data as D
import release_initialize as I
from test_data_released_deploy import EMPTY, SHA


def node(tmp_path, script, mode, env, answers, instance=I.SOURCE):
    """Run a release Node script against fake connector and pg modules that answer each query from a list."""
    modules = tmp_path / "node_modules"
    for name in ("firebase-tools", "pg", "@google-cloud/cloud-sql-connector"):
        (modules / name).mkdir(parents=True, exist_ok=True)
        (modules / name / "package.json").write_text('{"version":"15.8.0","main":"index.js"}')
    (modules / "@google-cloud/cloud-sql-connector/index.js").write_text("exports.AuthTypes={IAM:'IAM'};exports.IpAddressTypes="
        "{PUBLIC:'PUBLIC'};exports.Connector=class{async getOptions(){return {}}close(){}};")
    (modules / "pg/index.js").write_text("const fs=require('node:fs'),env=process.env;exports.Pool=class{constructor(o)"
        "{fs.appendFileSync(env.TEST_TRACE,o.user+' '+o.database+'\\n')}async connect(){return {release(){},async query(sql)"
        "{for(const [key,value] of JSON.parse(env.TEST_ANSWERS)) if(sql.includes(key)) return value;throw Error('unexpected')}}}"
        "async end(){}};")
    output, trace = tmp_path / "output.json", tmp_path / "trace.txt"
    trace.write_text("")
    context = {"PATH": os.environ["PATH"], "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": D.REPOSITORY, "GITHUB_SHA": SHA,
               "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main", "GITHUB_REF_PROTECTED": "true",
               "GITHUB_WORKFLOW_REF": f"{D.REPOSITORY}/.github/workflows/data-release.yml@refs/heads/main",
               "RELEASE_NODE_ROOT": str(tmp_path), "TEST_TRACE": str(trace), "TEST_ANSWERS": json.dumps(answers)}
    result = subprocess.run(["node", script, mode, instance, str(output)], cwd=D.ROOT, env={**context, **env},
                            capture_output=True, timeout=30)
    return result.returncode, json.loads(output.read_text()) if output.exists() else None, trace.read_text().splitlines()


@pytest.mark.parametrize("shas,passes", [({"RELEASE_GATE_SHA": SHA}, True), ({"RELEASE_AUTHORIZED_SHA": SHA}, True),
    ({"RELEASE_GATE_SHA": SHA, "RELEASE_AUTHORIZED_SHA": SHA}, False), ({}, False), ({"RELEASE_GATE_SHA": "b" * 40}, False)],
    ids=["gate", "envelope", "both", "neither", "other-commit"])
def test_the_summary_reads_the_application_database_as_the_release_identity_for_one_admitted_commit(tmp_path, shas, passes):
    code, value, trace = node(tmp_path, "scripts/ci/release_sql.mjs", "summary", {"DEPLOYMENT_ENVIRONMENT": "data-production", **shas},
                              [["SELECT current_database() AS name", {"rows": [{"name": D.DATABASE}]}],
                               ["AS roles", [{"command": "BEGIN"}, {"command": "SELECT", "rows": [EMPTY]}, {"command": "COMMIT"}]]])
    assert (code == 0, value, trace) == (passes, EMPTY if passes else None, [f"{I.MAINTENANCE} {D.DATABASE}"] if passes else [])


@pytest.mark.parametrize("mode,instance,shas,passes", [
    ("initialize", I.SOURCE, {"RELEASE_GATE_SHA": SHA}, True),
    ("initialize", I.SOURCE, {"RELEASE_AUTHORIZED_SHA": SHA}, False),  # the envelope still needs its clone's postconditions
    ("initialize", I.CLONE, {"RELEASE_GATE_SHA": SHA}, False), ("capability", I.SOURCE, {"RELEASE_GATE_SHA": SHA}, False),
], ids=["gate-source", "envelope-without-clone", "gate-clone", "gate-envelope-mode"])
def test_the_initializer_commits_on_the_source_alone_only_on_the_gate_path(tmp_path, mode, instance, shas, passes):
    answers = [["session_user AS actor", {"rows": [{"database": I.DATABASE, "actor": I.INITIALIZER_SQL, "effective": I.INITIALIZER_SQL}]}],
               ["backend_type=", {"rows": [{"count": 0}]}], ["$guard$", []], ["COMMIT", []],
               ["$postconditions$", [{"command": "SELECT", "rows": [{"postconditions": {"database_owner": "cloudsqlsuperuser"}}]}]]]
    env = {"DEPLOYMENT_ENVIRONMENT": "data-initialization-production", "RELEASE_SERVICE_ACCOUNT": I.INITIALIZER_SQL + ".gserviceaccount.com",
           "INITIALIZATION_DEADLINE": str(int(time.time()) + 300), "INITIALIZATION_FILES": json.dumps(I.fingerprints()), **shas}
    code, value, trace = node(tmp_path, "scripts/ci/release_initialize.mjs", mode, env, answers, instance)
    assert (code == 0, value and value["postconditions"]) == (passes, {"database_owner": "cloudsqlsuperuser"} if passes else None)
