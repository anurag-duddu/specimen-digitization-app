"""Optional private configuration and scoped definitions, with no cloud calls."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import deploy_models as models  # noqa: E402
import deploy_intake as intake  # noqa: E402
from test_model_runtime_release import image, resource, SHA  # noqa: E402

SCOPE = "11111111-1111-4111-8111-111111111111/22222222-2222-4222-8222-222222222222"
ROUTE = {"actor_uid": "private-worker-actor", "worker_job": models.settings.PREFIX + "/jobs/specimen-worker-e2e",
         "intake_job": models.settings.PREFIX + "/jobs/specimen-intake-e2e"}
SECRET = "specimen-collection-job-routes"  # pragma: allowlist secret (resource name, not credential)


def enable_routes(monkeypatch):
    monkeypatch.setitem(models.settings.OPTIONAL_SECRET_VERSIONS, SECRET, 3)
    monkeypatch.setitem(models.settings.SECRET_VERSIONS, SECRET, 3)
    for spec in (models.settings.API, models.settings.INTAKE, models.settings.WORKER):
        monkeypatch.setitem(spec["secret_env"], "SPECIMEN_COLLECTION_WORKER_JOBS_JSON", SECRET)


def test_unprovisioned_defaults_add_no_secret_dependency_or_route_read(monkeypatch):
    assert all(value is None for value in models.settings.OPTIONAL_SECRET_VERSIONS.values())
    assert models.settings.OAUTH_CLIENT_SECRET_VERSIONS == {}
    for role in ("api", "intake", "worker"):
        assert models.settings.optional_secret_env(role) == {}
    monkeypatch.setattr(models.subprocess, "run", lambda *args, **kwargs: pytest.fail("unexpected cloud read"))
    assert models.collection_routes() == {}
    assert models.intake_setup_metadata() == ["PIN\tapi\tspecimen-worker-actor-uid\t1", "JOB\tintake\tspecimen-intake"]


@pytest.mark.parametrize("version", [True, 0, -1, "1", "latest"])
def test_optional_configuration_requires_reviewed_positive_integer_versions(monkeypatch, version):
    monkeypatch.setitem(models.settings.OPTIONAL_SECRET_VERSIONS, SECRET, version)
    with pytest.raises(ValueError, match="numbered"):
        models.settings.optional_secret_env("api")


@pytest.mark.parametrize("name", ["specimen-intake-google-client", "specimen-worker-actor-uid", "specimen-collection-job-routes"])
def test_client_secrets_cannot_overlap_tokens_or_existing_runtime_pins(monkeypatch, name):
    monkeypatch.setitem(models.settings.OAUTH_CLIENT_SECRET_VERSIONS, name, 1)
    with pytest.raises(ValueError, match="separate"):
        models.settings.optional_secret_env("api")


def test_one_pinned_routes_value_is_shared_by_api_and_both_workers(monkeypatch, capsys):
    enable_routes(monkeypatch)
    calls = []
    def read(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps({SCOPE: ROUTE}))
    monkeypatch.setattr(models.subprocess, "run", read)
    assert models.collection_routes() == {SCOPE: ROUTE}
    command, options = calls[0]
    assert command == ["gcloud", "secrets", "versions", "access", "3", f"--secret={SECRET}",
                       "--project=specimen-digitization"]
    assert options["capture_output"] and options["text"]
    assert ROUTE["actor_uid"] not in capsys.readouterr().out
    monkeypatch.delitem(models.settings.WORKER["secret_env"], "SPECIMEN_COLLECTION_WORKER_JOBS_JSON")
    with pytest.raises(ValueError, match="same numbered"):
        models.collection_routes()
    assert len(calls) == 1


@pytest.mark.parametrize("mutation", ["region", "shared_job", "arbitrary_job", "invalid_scope", "payload", "read"])
def test_route_read_failures_are_bounded_and_never_quote_private_values(monkeypatch, mutation):
    enable_routes(monkeypatch)
    route, scope = dict(ROUTE), SCOPE
    if mutation == "region": route["worker_job"] = route["worker_job"].replace("us-east4", "europe-west1")
    if mutation == "shared_job": route["intake_job"] = models.settings.INTAKE_JOB
    if mutation == "arbitrary_job": route["worker_job"] = models.settings.PREFIX + "/jobs/unrelated"
    if mutation == "invalid_scope": scope = "private-invalid-scope"
    payload = "private-unreadable-json" if mutation == "payload" else json.dumps({scope: route})
    monkeypatch.setattr(models.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=1 if mutation == "read" else 0, stdout=payload))
    with pytest.raises(ValueError) as failure:
        models.collection_routes()
    assert ROUTE["actor_uid"] not in str(failure.value)
    assert "private-invalid-scope" not in str(failure.value)
    assert "private-unreadable-json" not in str(failure.value)


def test_dedicated_jobs_keep_fixed_scope_continuations_existing_actor_and_limits(monkeypatch, tmp_path):
    enable_routes(monkeypatch)
    worker_values = models.scoped_job_env(models.model_settings.role_env("worker", models.settings.SAM_CHECKPOINT_SHA256), SCOPE, ROUTE)
    intake_values = models.scoped_job_env(intake.job_env(), SCOPE, ROUTE)
    expected_scope = dict(zip(("organization_id", "collection_id"), SCOPE.split("/"), strict=True))
    for values in (worker_values, intake_values):
        assert json.loads(values["SPECIMEN_WORKER_SCOPE_JSON"]) == expected_scope
        assert values["SPECIMEN_WORKER_JOB"] == ROUTE["worker_job"]
        assert values["SPECIMEN_INTAKE_JOB"] == ROUTE["intake_job"]
    assert "SPECIMEN_WORKER_SCOPE_JSON" not in intake.job_env()
    assert models.settings.WORKER["secret_env"]["SPECIMEN_WORKER_ACTOR_UID"] == "specimen-worker-actor-uid"
    assert models.settings.INTAKE["secret_env"]["SPECIMEN_WORKER_ACTOR_UID"] == "specimen-worker-actor-uid"
    worker = models.command("worker", image("worker"), SHA, tmp_path / "worker.json", job_name="specimen-worker-e2e")
    transfer = intake.command(image("api"), SHA, tmp_path / "intake.yaml", job_name="specimen-intake-e2e")
    assert worker[4] == "specimen-worker-e2e" and transfer[4] == "specimen-intake-e2e"
    assert "--max-retries" in worker and worker[worker.index("--max-retries") + 1] == "0"
    assert "--max-retries" in transfer and transfer[transfer.index("--max-retries") + 1] == "2"
    assert not any("execute" in arg or "override" in arg for arg in worker + transfer)
    value = resource("worker")
    container = value["spec"]["template"]["spec"]["template"]["spec"]["containers"][0]
    container["env"] = [row for row in container["env"] if "valueFrom" in row]
    container["env"] += [{"name": name, "value": value} for name, value in worker_values.items()]
    models.verify_definition("worker", value, image("worker"), SHA, expected_env=worker_values)
    container["env"][-1]["value"] = "{}"
    with pytest.raises(ValueError, match="environment"):
        models.verify_definition("worker", value, image("worker"), SHA, expected_env=worker_values)


def test_owner_metadata_is_only_pinned_refs_approved_apis_and_job_names(monkeypatch, capsys):
    enable_routes(monkeypatch)
    monkeypatch.setitem(models.settings.OPTIONAL_SECRET_VERSIONS, "specimen-cloud-import-config", 2)
    monkeypatch.setitem(models.settings.OAUTH_CLIENT_SECRET_VERSIONS, "specimen-google-drive-client", 4)
    monkeypatch.setattr(models.settings, "INTAKE_PROVIDER_APIS", ("drive.googleapis.com", "picker.googleapis.com"))
    monkeypatch.setattr(models, "collection_routes", lambda: {SCOPE: ROUTE})
    models.main(["deploy_models.py", "--intake-setup"])
    output = capsys.readouterr().out
    assert "PIN\trelease\tspecimen-collection-job-routes\t3" in output
    assert "PIN\tapi\tspecimen-google-drive-client\t4" in output
    assert "JOB\tworker\tspecimen-worker-e2e" in output
    assert "API\tdrive.googleapis.com" in output
    assert SCOPE not in output and ROUTE["actor_uid"] not in output


def test_provider_api_enablement_requires_both_configuration_and_client_pins(monkeypatch):
    monkeypatch.setattr(models.settings, "INTAKE_PROVIDER_APIS", ("drive.googleapis.com",))
    with pytest.raises(ValueError, match="prerequisites"):
        models.intake_setup_metadata()


def test_intake_release_defines_shared_then_dedicated_without_executing(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(intake, "release_context", lambda env: SHA)
    monkeypatch.setattr(intake, "collection_routes", lambda: {SCOPE: ROUTE})
    monkeypatch.setattr(intake, "read", lambda *args: {})
    monkeypatch.setattr(intake, "verify_policy", lambda policy: None)
    checked = []
    monkeypatch.setattr(intake, "verify_definition", lambda *a, **kw: checked.append(kw["expected_env"]))
    def run(command, **kwargs):
        import yaml
        path = command[command.index("--env-vars-file") + 1]
        calls.append((command, yaml.safe_load(Path(path).read_text())))
    monkeypatch.setattr(intake.subprocess, "run", run)
    intake.main(["deploy_intake.py", image("api")])
    assert [call[0][4] for call in calls] == ["specimen-intake", "specimen-intake-e2e"]
    assert "SPECIMEN_WORKER_SCOPE_JSON" not in calls[0][1]
    assert json.loads(calls[1][1]["SPECIMEN_WORKER_SCOPE_JSON"])["collection_id"] == SCOPE.split("/")[1]
    assert checked == [call[1] for call in calls]
    assert not any("execute" in arg for command, _ in calls for arg in command)
