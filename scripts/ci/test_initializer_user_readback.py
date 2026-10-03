"""Named detail reads prove roles that Cloud SQL's users list omits."""
import copy

import pytest

import release_initialize as init
from test_data_first_initialization import Cloud, I, jobs  # noqa: F401


@pytest.mark.parametrize("fault", [None, "missing-role", "extra-role", "foreign-name",
                                  "foreign-instance", "foreign-project", "foreign-type", "foreign-host", "late"])
def test_list_without_roles_needs_exact_timely_user_detail_before_sql(jobs, fault):
    cloud = Cloud("data-initialization", 1)
    original = cloud.request
    reads = []

    def request(api, method, resource, **kwargs):
        if method == "GET" and resource.endswith("/users/" + I.INITIALIZER_SQL):
            I.validate_request(api, method, resource, kwargs.get("body"), kwargs.get("params"), gate=True)
            reads.append((api, method, resource, kwargs))
            detail = {**copy.deepcopy(cloud.principal), "instance": I.SOURCE, "project": I.PROJECT, "host": ""}
            if fault == "missing-role": detail.pop("databaseRoles")
            elif fault == "extra-role": detail["databaseRoles"].append("pg_read_all_data")
            elif fault == "foreign-name": detail["name"] = I.MAINTENANCE
            elif fault == "foreign-instance": detail["instance"] = I.CLONE
            elif fault == "foreign-project": detail["project"] = "foreign-project"
            elif fault == "foreign-type": detail["type"] = "CLOUD_IAM_USER"
            elif fault == "foreign-host": detail["host"] = "foreign-host"
            elif fault == "late": jobs.clock[0] += 600
            return detail
        value = original(api, method, resource, **kwargs)
        if method == "GET" and resource.endswith("/users") and cloud.principal:
            return {"items": [{key: value for key, value in cloud.principal.items() if key != "databaseRoles"}]}
        return value

    cloud.request = request
    if fault:
        with pytest.raises(ValueError):
            jobs.initialize(cloud)
        assert jobs.native == []
        assert not (jobs.directory / "data-initializer.json").exists()
    else:
        assert jobs.initialize(cloud)["version"] == "data-initializer/v1"
        assert [row[0] for row in jobs.native] == ["initialize"]
    assert len(reads) == 1
    assert reads[0][3] == {"params": {"host": ""}}
    assert [call for call in cloud.calls if call[0] != "GET"] == [("POST", "users")]


def test_role_revocation_explicitly_preserves_the_iam_user_type_without_granting_roles():
    method, resource, arguments = init.user_request(init.SOURCE, "revoke")
    assert (method, resource) == ("PUT", f"projects/{init.PROJECT}/instances/{init.SOURCE}/users")
    assert arguments == {"params": {"name": init.INITIALIZER_SQL, "revokeExistingRoles": "true"},
                         "body": {"name": init.INITIALIZER_SQL, "type": "CLOUD_IAM_SERVICE_ACCOUNT"}}
    assert "databaseRoles" not in arguments["body"]
    assert "password" not in arguments["body"]


@pytest.mark.parametrize("fault", ["foreign-user", "clone-on-gate", "foreign-project", "body", "host", "extra-param"])
def test_named_detail_read_allowlist_does_not_expand_initializer_scope(fault):
    resource = f"projects/{init.PROJECT}/instances/{init.SOURCE}/users/{init.INITIALIZER_SQL}"
    body, params = None, {"host": ""}
    if fault == "foreign-user": resource = resource.replace(init.INITIALIZER_SQL, init.MAINTENANCE)
    elif fault == "clone-on-gate": resource = resource.replace(init.SOURCE, init.CLONE)
    elif fault == "foreign-project": resource = resource.replace(init.PROJECT, "foreign-project")
    elif fault == "body": body = {}
    elif fault == "host": params["host"] = "foreign-host"
    else: params["pageToken"] = "token"
    with pytest.raises(ValueError):
        init.validate_request("sql", "GET", resource, body, params, gate=True)


def test_detail_identity_validation_cannot_adopt_an_observation_after_its_original_deadline(monkeypatch):
    clock = [99]
    monkeypatch.setattr(init.time, "time", lambda: clock[0])

    class Detail(dict):
        def get(self, key, default=None):
            value = super().get(key, default)
            if key == "host": clock[0] = 100
            return value

    class Google:
        sql_read_deadline = 100

        def request(self, api, method, resource, **kwargs):
            assert (api, method, resource, kwargs) == ("sql", "GET",
                f"projects/{init.PROJECT}/instances/{init.SOURCE}/users/{init.INITIALIZER_SQL}", {"params": {"host": ""}})
            return Detail(name=init.INITIALIZER_SQL, type="CLOUD_IAM_SERVICE_ACCOUNT", instance=init.SOURCE,
                          project=init.PROJECT, host="", databaseRoles=["cloudsqlsuperuser"])

    with pytest.raises(ValueError, match="detail acceptance.*original observation deadline"):
        init.initializer_user_detail(Google(), init.SOURCE)
