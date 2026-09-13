"""An empty Firebase onboarding schema is distinct from an absent SQL database."""
import copy

import pytest

import deploy_data as data
import release_initialize as initialize
from test_data_initialization import NOW, packet, plan


def placeholder():
    return {
        "name": data.PREFIX + "/schemas/main",
        "createTime": "2026-09-08T00:39:41.672976635Z",
        "updateTime": "2026-09-08T00:39:45.922408743Z",
        "source": {},
        "uid": "11111111-1111-4111-8111-111111111111",
        "reconciling": False,
        "datasources": [{"postgresql": {
            "database": data.DATABASE,
            "cloudSql": {"instance": f"projects/{data.PROJECT}/locations/us-east4/instances/{data.SOURCE}"},
            "schemaValidation": "NONE", "ephemeral": True,
        }}],
        "etag": "synthetic-onboarding-revision",
    }


def prepared():
    value = plan()
    value.update(schema_placeholder=placeholder(), schema_etag=placeholder()["etag"])
    return value


def test_reviewed_empty_placeholder_does_not_require_deleting_the_service():
    value = prepared()
    assert data.validate_plan(value, packet(), now=NOW) is value
    schema, _ = data.data_bodies(value)
    assert schema["etag"] == value["schema_placeholder"]["etag"]
    assert schema["datasources"][0]["postgresql"]["schemaValidation"] == "COMPATIBLE"
    assert "ephemeral" not in schema["datasources"][0]["postgresql"]


@pytest.mark.parametrize("change", [
    lambda p: p.update(source={"files": [{"path": "schema.gql", "content": "type Existing @table { id: UUID! }"}]}),
    lambda p: p.update(name=data.PREFIX + "/schemas/other"),
    lambda p: p.update(uid="invalid"),
    lambda p: p.update(reconciling=True),
    lambda p: p.update(etag=""),
    lambda p: p.update(updateTime="invalid"),
    lambda p: p.update(source={"unknown": []}),
    lambda p: p["datasources"][0]["postgresql"].update(ephemeral=False),
    lambda p: p["datasources"][0]["postgresql"].update(schemaValidation="COMPATIBLE"),
    lambda p: p["datasources"][0]["postgresql"].update(database="other"),
    lambda p: p["datasources"][0]["postgresql"]["cloudSql"].update(instance="other"),
])
def test_placeholder_exception_cannot_adopt_an_application_schema(change):
    value = prepared()
    change(value["schema_placeholder"])
    with pytest.raises(ValueError):
        data.validate_plan(value, packet(), now=NOW)


@pytest.mark.parametrize("change", [
    lambda p: p.update(schema_etag=None),
    lambda p: p.update(connector_etag="existing"),
    lambda p: p.update(bootstrap={"payload": {}, "sha256": "0" * 64}),
    lambda p: p.update(version="data-apply/v1", schema_mode="initialize_empty"),
])
def test_placeholder_keeps_initialization_and_bootstrap_boundaries(change):
    value = prepared()
    change(value)
    with pytest.raises(ValueError):
        data.validate_plan(value, packet(), now=NOW)


@pytest.mark.parametrize("current", [None, {**placeholder(), "etag": "changed"},
    {**placeholder(), "source": {"files": [{"path": "changed.gql", "content": "changed"}]}}])
def test_changed_placeholder_stops_before_backup_or_catalog_work(tmp_path, monkeypatch, current):
    value = prepared()
    class Google:
        packet = packet()
        def request(self, api, method, resource, **kwargs):
            assert method == "GET"
            if resource == f"projects/{data.PROJECT}/instances/{data.SOURCE}":
                return {"settings": {"settingsVersion": value["database_etag"]}}
            if resource.endswith("/schemas/main"):
                return copy.deepcopy(current)
            return None
    monkeypatch.setattr(initialize.time, "time", lambda: NOW)
    monkeypatch.setattr(data, "clone_body", lambda *a, **k: {})
    monkeypatch.setattr(initialize, "native", lambda *a, **k: pytest.fail("catalog work preceded schema preflight"))
    with pytest.raises(ValueError, match="schema"):
        initialize.prepare_recovery(Google(), value, tmp_path, tmp_path / "output.json")


def test_matching_placeholder_uses_conditional_schema_publication(tmp_path):
    calls = []
    class StopAfterApply(Exception):
        pass
    class Google:
        def wait(self, *args):
            pytest.fail("test stops at the conditional apply request")
        def request(self, api, method, resource, **kwargs):
            if method == "GET":
                return placeholder() if resource.endswith("/schemas/main") else None
            assert method == "PATCH" and resource.endswith("/schemas/main")
            calls.append(kwargs)
            if len(calls) == 2:
                raise StopAfterApply
            return {}
    with pytest.raises(StopAfterApply):
        data.apply_compatible(Google(), prepared(), tmp_path / "packet.json", tmp_path / "output.json", {})
    assert calls[0]["body"] == calls[1]["body"]
    assert calls[1]["body"]["etag"] == placeholder()["etag"]


def test_existing_connector_stops_before_schema_publication(tmp_path):
    class Google:
        def request(self, api, method, resource, **kwargs):
            assert method == "GET", "no publication before both resource checks pass"
            return placeholder() if resource.endswith("/schemas/main") else {"name": resource}
    with pytest.raises(ValueError):
        data.apply_compatible(Google(), prepared(), tmp_path / "packet.json", tmp_path / "output.json", {})
