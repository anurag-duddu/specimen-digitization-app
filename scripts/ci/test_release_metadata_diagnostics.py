"""Exercise the authorized transport/error boundary without credentials or cloud."""
from types import SimpleNamespace

import pytest

import deploy_data as data
import release_admission as admission
import release_diagnostics as diagnostics
import release_gate as gate
import release_google as google
from test_release_google import transport

CANARY = "private-token https://private.invalid/resource?cursor=private-cursor SELECT private_account password=private-password"
FORBIDDEN = ("private-token", "https://", "private-cursor", "SELECT", "private_account", "password=",
             "specimen-digitization", "123456789", "716045864126", "/instances/", "/databases/")
READS = (
    (data.SOURCE, "/users", "google.sql-source-users-list"),
    (data.CLONE, "/users", "google.sql-clone-users-list"),
    (data.SOURCE, "", "google.sql-source-instance-get"),
    (data.CLONE, "", "google.sql-clone-instance-get"),
    (data.SOURCE, "/databases/" + data.DATABASE, "google.sql-source-database-get"),
    (data.CLONE, "/databases/" + data.DATABASE, "google.sql-clone-database-get"),
)


def observed_transport(status=403, payload=None):
    client = transport()
    calls, json_calls = [], []

    def read_json():
        json_calls.append(True)
        return {"error": CANARY} if payload is None else payload

    response = SimpleNamespace(status_code=status, text=CANARY, json=read_json)

    def request(*args, **kwargs):
        calls.append((args, kwargs))
        return response

    client.session.request = request
    return client, calls, json_calls


def assert_public_failure(error, name, status=None):
    expected = "Data release blocked [stage=" + name
    if status is not None:
        expected += "; http_status=" + str(status)
    expected += "]."
    assert diagnostics.public_failure(error) == expected
    assert all(value not in expected for value in FORBIDDEN)


@pytest.mark.parametrize("instance,suffix,name", READS)
@pytest.mark.parametrize("project", [data.PROJECT, "123456789"])
@pytest.mark.parametrize("status", [401, 403, 404, 429, 503, 301])
def test_fixed_metadata_http_failure_keeps_exception_type_and_numeric_status(instance, suffix, name, project, status):
    client, calls, json_calls = observed_transport(status)
    params = {"pageToken": CANARY} if suffix == "/users" else None
    with pytest.raises(diagnostics.HTTPFailure) as error:
        client.request("sql", "GET", f"projects/{project}/instances/{instance}{suffix}", params=params)
    assert type(error.value) is diagnostics.HTTPFailure
    assert error.value.http_status == (status if status >= 400 else None)
    assert error.value.read_stage == name and error.value.body is None
    assert str(error.value) == "Google HTTP response rejected"
    assert_public_failure(error.value, name, status if status >= 400 else None)
    assert len(calls) == 1 and json_calls == []
    assert calls[0][0] == ("GET", google.ORIGINS["sql"] + f"projects/{project}/instances/{instance}{suffix}")
    assert calls[0][1] == {"json": None, "params": params, "timeout": 30, "allow_redirects": False}


@pytest.mark.parametrize("instance,suffix,name", READS)
def test_real_initializer_request_allowlist_precedes_safe_read_label(instance, suffix, name):
    client, calls, json_calls = observed_transport()
    client.plane = "data-initialization"
    with pytest.raises(diagnostics.HTTPFailure) as error:
        client.request("sql", "GET", f"projects/{data.PROJECT}/instances/{instance}{suffix}",
                       params={} if suffix == "/users" else None)
    assert_public_failure(error.value, name, 403)
    assert len(calls) == 1 and json_calls == []


@pytest.mark.parametrize("instance,suffix,name", READS)
def test_success_still_returns_native_json_once(instance, suffix, name):
    payload = {"items": [], "native-private-field": CANARY}
    client, calls, json_calls = observed_transport(200, payload)
    assert client.request("sql", "GET", f"projects/{data.PROJECT}/instances/{instance}{suffix}") is payload
    assert len(calls) == 1 and json_calls == [True]


@pytest.mark.parametrize("instance,suffix,name", [row for row in READS if row[1] != "/users"])
def test_expected_404_absence_still_returns_none(instance, suffix, name):
    client, calls, json_calls = observed_transport(404)
    assert client.request("sql", "GET", f"projects/{data.PROJECT}/instances/{instance}{suffix}", missing=True) is None
    assert len(calls) == 1 and json_calls == []


@pytest.mark.parametrize("wrapper,expected", [
    ("data.execute", "google.sql-source-instance-get"),
    ("catalog.metadata-request", "catalog.metadata-request"),
    ("data.admission", "data.admission"),
])
def test_existing_explicit_wrapper_stage_retains_precedence(wrapper, expected):
    client, calls, json_calls = observed_transport()
    with pytest.raises(diagnostics.DiagnosticError) as error:
        with diagnostics.stage(wrapper):
            client.request("sql", "GET", f"projects/{data.PROJECT}/instances/{data.SOURCE}")
    assert_public_failure(error.value, expected, 403)
    assert str(error.value) == diagnostics.public_failure(error.value)
    assert error.value.__cause__ is None
    assert len(calls) == 1 and json_calls == []


@pytest.mark.parametrize("resource", [
    f"projects/{data.PROJECT}/instances/unapproved-private-instance",
    f"projects/{data.PROJECT}/instances/{data.SOURCE}/users/private-account",
    f"projects/{data.PROJECT}/instances/{data.SOURCE}/databases",
    f"projects/{data.PROJECT}/instances/{data.SOURCE}/databases/private-database",
    f"projects/{data.PROJECT}/instances/{data.SOURCE}/backupRuns",
    f"projects/{data.PROJECT}/operations/private-operation",
])
def test_unknown_metadata_keeps_generic_fallback_without_resource_text(resource):
    client, calls, json_calls = observed_transport()
    with pytest.raises(diagnostics.HTTPFailure) as error:
        client.request("sql", "GET", resource)
    assert error.value.read_stage is None
    assert_public_failure(error.value, "data.execute", 403)
    assert resource not in diagnostics.public_failure(error.value)
    assert len(calls) == 1 and json_calls == []


@pytest.mark.parametrize("suffix,body,params", [
    ("", {"private": CANARY}, None),
    ("", None, {"private-filter": CANARY}),
    ("/users", None, {"pageToken": ""}),
    ("/users", None, {"pageToken": True}),
    ("/users", None, {"pageToken": "x" * 4097}),
    ("/users", None, {"pageToken": CANARY, "private-filter": CANARY}),
])
def test_unqualified_read_shapes_are_not_given_specific_public_authority(suffix, body, params):
    client, calls, json_calls = observed_transport()
    with pytest.raises(diagnostics.HTTPFailure) as error:
        client.request("sql", "GET", f"projects/{data.PROJECT}/instances/{data.SOURCE}{suffix}", body=body, params=params)
    assert error.value.read_stage is None
    assert_public_failure(error.value, "data.execute", 403)
    assert len(calls) == 1 and json_calls == []


def test_other_plane_same_resource_is_generic():
    client, calls, json_calls = observed_transport()
    client.plane = "runtime"
    with pytest.raises(diagnostics.HTTPFailure) as error:
        client.request("sql", "GET", f"projects/{data.PROJECT}/instances/{data.SOURCE}")
    assert_public_failure(error.value, "data.execute", 403)
    assert len(calls) == 1 and json_calls == []


def test_other_api_same_path_is_generic():
    client, calls, json_calls = observed_transport()
    with pytest.raises(diagnostics.HTTPFailure) as error:
        client.request("run", "GET", f"projects/{data.PROJECT}/instances/{data.SOURCE}")
    assert_public_failure(error.value, "data.execute", 403)
    assert len(calls) == 1 and json_calls == []


def test_mutation_still_readmits_and_invokes_dispatch_guard_without_read_label(monkeypatch):
    client, calls, json_calls = observed_transport()
    admitted, guarded = [], []
    monkeypatch.setattr(google.time, "time", lambda: client.packet["issued_at_unix"])

    def admit(path, plane):
        admitted.append((path, plane))
        return client.packet

    monkeypatch.setattr(google, "admit", admit)
    client.worker_dispatch_guard = lambda *args: guarded.append(args)
    resource = f"projects/{data.PROJECT}/instances/{data.SOURCE}"
    body = {"private": CANARY}
    with pytest.raises(diagnostics.HTTPFailure) as error:
        client.request("sql", "PATCH", resource, body=body)
    assert_public_failure(error.value, "data.execute", 403)
    assert admitted == [(client.path, "data")]
    assert guarded == [("sql", "PATCH", resource, body)]
    assert len(calls) == 1 and json_calls == []
    assert calls[0][1]["max_allowed_time"] == 30


@pytest.mark.parametrize("resource", [
    f"projects/foreign/instances/{data.SOURCE}",
    f"projects/{data.PROJECT}/instances/{data.SOURCE}?private={CANARY}",
    f"projects/{data.PROJECT}/instances/{data.SOURCE}#private",
    f"projects/{data.PROJECT}/instances/../{data.SOURCE}",
    f"projects/{data.PROJECT}/instances/%73pecimen-digitization-instance",
])
def test_invalid_target_is_rejected_before_transport_and_cannot_supply_read_label(resource):
    client, calls, json_calls = observed_transport()
    with pytest.raises(diagnostics.DiagnosticError) as error:
        with diagnostics.stage("data.execute"):
            client.request("sql", "GET", resource)
    assert_public_failure(error.value, "data.execute")
    assert calls == [] and json_calls == []


def test_expired_sql_read_deadline_is_not_relabelled_as_http_failure(monkeypatch):
    client, calls, json_calls = observed_transport()
    client.sql_read_deadline = 100
    monkeypatch.setattr(google.time, "time", lambda: 100)
    with pytest.raises(diagnostics.DiagnosticError) as error:
        with diagnostics.stage("data.execute"):
            client.request("sql", "GET", f"projects/{data.PROJECT}/instances/{data.SOURCE}")
    assert_public_failure(error.value, "data.execute")
    assert calls == [] and json_calls == []


def test_remaining_sql_read_timeout_is_preserved(monkeypatch):
    client, calls, json_calls = observed_transport()
    client.sql_read_deadline = 113
    monkeypatch.setattr(google.time, "time", lambda: 100)
    with pytest.raises(diagnostics.HTTPFailure) as error:
        client.request("sql", "GET", f"projects/{data.PROJECT}/instances/{data.SOURCE}")
    assert_public_failure(error.value, "google.sql-source-instance-get", 403)
    assert len(calls) == 1 and json_calls == []
    assert calls[0][1]["timeout"] == 13 and calls[0][1]["allow_redirects"] is False


def test_transport_exception_cannot_supply_read_stage_or_message():
    client = transport()
    calls = []

    def fail(*args, **kwargs):
        calls.append((args, kwargs))
        error = ValueError(CANARY)
        error.http_status = 403
        error.read_stage = "google.sql-source-users-list"
        raise error

    client.session.request = fail
    with pytest.raises(diagnostics.DiagnosticError) as error:
        with diagnostics.stage("data.execute"):
            client.request("sql", "GET", f"projects/{data.PROJECT}/instances/{data.SOURCE}/users")
    assert_public_failure(error.value, "data.execute")
    assert str(error.value) == diagnostics.public_failure(error.value)
    assert len(calls) == 1


@pytest.mark.parametrize("suffix", ["", "/users", "/databases/" + data.DATABASE])
def test_gate_initializer_cannot_read_clone_even_when_stage_is_allowlisted(suffix):
    client, calls, json_calls = observed_transport()
    client.plane = "data-initialization"
    client.packet["version"] = gate.RECORD_VERSION
    with pytest.raises(diagnostics.DiagnosticError) as error:
        with diagnostics.stage("data.execute"):
            client.request("sql", "GET", f"projects/{data.PROJECT}/instances/{data.CLONE}{suffix}")
    assert_public_failure(error.value, "data.execute")
    assert calls == [] and json_calls == []


@pytest.mark.parametrize("read_stage", [CANARY, "node.connect", "data.admission", True, 403, None])
def test_unknown_exception_metadata_cannot_supply_public_read_fields(read_stage):
    error = diagnostics.HTTPFailure(403, read_stage=read_stage)
    assert error.read_stage is None
    assert_public_failure(error, "data.execute", 403)
    error.read_stage = read_stage
    assert_public_failure(error, "data.execute", 403)
    with pytest.raises(diagnostics.DiagnosticError) as wrapped:
        with diagnostics.stage("data.execute"):
            raise error
    assert_public_failure(wrapped.value, "data.execute", 403)
    foreign = ValueError(CANARY)
    foreign.read_stage = "google.sql-source-users-list"
    foreign.http_status = 403
    assert_public_failure(foreign, "data.execute")


@pytest.mark.parametrize("failed_suffix,expected,count", [
    ("/users", "google.sql-source-users-list", 1),
    ("", "google.sql-source-instance-get", 2),
    ("/databases/" + data.DATABASE, "google.sql-source-database-get", 3),
])
def test_real_initializer_prepare_cli_reports_first_failed_read_without_creating_intent(
        tmp_path, monkeypatch, capsys, failed_suffix, expected, count):
    client = transport()
    client.plane = "data-initialization"
    client.packet = {**client.packet, "version": gate.RECORD_VERSION,
                     "identity": gate.identity("data-initialization")}
    monkeypatch.setattr(google.time, "time", lambda: client.packet["issued_at_unix"])
    calls, rejected_json = [], []
    prefix = f"projects/{data.PROJECT}/instances/{data.SOURCE}"

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url == google.ORIGINS["sql"] + prefix + failed_suffix:
            def unread_error_body():
                rejected_json.append(True)
                return {"error": CANARY}
            return SimpleNamespace(status_code=403, text=CANARY, json=unread_error_body)
        payload = {"items": []} if url.endswith("/users") else {
            "name": data.SOURCE, "project": data.PROJECT, "region": "us-east4", "state": "RUNNABLE"}
        return SimpleNamespace(status_code=200, json=lambda: payload)

    def admitted(path, plane):
        assert plane == "data-initialization"
        return client.packet

    def protected_environment(path):
        if path.endswith("/deployment-branch-policies"):
            return {"total_count": 1, "branch_policies": [{"name": "main", "type": "branch"}]}
        return {"deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True}}

    client.session.request = request
    monkeypatch.setattr(data, "admit", admitted)
    monkeypatch.setattr(data, "Google", lambda *args: client)
    monkeypatch.setattr(admission, "gh_json", protected_environment)
    monkeypatch.setattr("sys.argv", ["deploy_data.py", "--packet", str(tmp_path / "packet.json"),
                                    "--prepare-initializer-intents"])
    with pytest.raises(SystemExit) as error:
        data.main()
    assert str(error.value) == "Data release blocked [stage=" + expected + "; http_status=403]."
    assert all(value not in str(error.value) for value in FORBIDDEN)
    assert len(calls) == count and all(method == "GET" for method, _, _ in calls)
    assert all(kwargs["allow_redirects"] is False for _, _, kwargs in calls)
    assert rejected_json == [] and not list(tmp_path.iterdir())
    assert capsys.readouterr() == ("", "")
