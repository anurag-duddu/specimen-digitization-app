"""Private bundle provisioning against an in-memory Secret Manager stand-in."""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import UUID

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import intake_config as config  # noqa: E402

ORG, COLLECTION = str(UUID(int=1)), str(UUID(int=2))
ACTOR = "synthetic-existing-worker"
TOKEN = "synthetic-private-client-value"
BASE = {str(UUID(int=100 + i)): f"node-{i}" for i in range(18)}


@pytest.fixture(autouse=True)
def synthetic_core_pins(monkeypatch):
    """The fake store starts before provisioning, regardless of live pins."""
    monkeypatch.setitem(config.settings.CORE_SECRET_VERSIONS, "specimen-collection-bindings", 1)
    monkeypatch.setitem(config.settings.CORE_SECRET_VERSIONS, "specimen-worker-actor-uid", 1)


class Cloud:
    def __init__(self):
        self.values = {"specimen-collection-bindings": {1: config.canonical(BASE)},
                       "specimen-worker-actor-uid": {1: ACTOR.encode()}}
        self.disabled, self.calls, self.writes = set(), [], []
        self.fail = None

    def version_name(self, name, version):
        return f"projects/{config.settings.PROJECT_NUMBER}/secrets/{name}/versions/{version}"

    def run(self, command, **kwargs):
        assert kwargs == {"capture_output": True, "check": False}
        assert command[:2] == ["gcloud", "secrets"] and command[-2:] == ["--project=specimen-digitization", "--quiet"]
        args = command[2:-2]
        self.calls.append(args)
        if self.fail and self.fail in args:
            return SimpleNamespace(returncode=1, stdout=b"", stderr=TOKEN.encode())
        out, error = b"", b""
        if args[0] == "describe":
            name = args[1]
            if name in self.values: out = f"projects/{config.settings.PROJECT_NUMBER}/secrets/{name}\n".encode()
            else: error = b"NOT_FOUND"
        elif args[:2] == ["versions", "list"]:
            name = args[2]
            out = json.dumps([{"name": self.version_name(name, version),
                "state": "DISABLED" if (name, version) in self.disabled else "ENABLED"}
                for version in self.values[name]]).encode()
        elif args[:2] == ["versions", "access"]:
            name = args[3].split("=", 1)[1]
            out = self.values[name][int(args[2])]
        elif args[0] == "create":
            name = args[1]
            assert name not in self.values
            self.values[name] = {}
            self.writes.append(("create", name))
        elif args[:2] == ["versions", "add"]:
            name = args[2]
            path = Path(args[3].split("=", 1)[1])
            assert path.stat().st_mode & 0o777 == 0o600
            version = max(self.values[name], default=0) + 1
            self.values[name][version] = path.read_bytes()
            self.writes.append(("add", name, version))
            out = (self.version_name(name, version) + "\n").encode()
        else:
            pytest.fail(f"unexpected command shape {args[:2]}")
        return SimpleNamespace(returncode=1 if error else 0, stdout=out, stderr=error)


def values():
    return {
        "specimen-external-emails": ["synthetic@example.com"],
        "specimen-google-drive-client": {"client_secret": TOKEN},
        "specimen-cloud-import-config": {"google_drive": {
            "client_id": "synthetic.apps.googleusercontent.com",
            "client_secret_ref": "projects/specimen-digitization/secrets/specimen-google-drive-client/versions/1",  # pragma: allowlist secret (resource reference)
            "redirect_uri": "https://specimen-api-716045864126.us-east4.run.app/v1/intake/oauth/callback",
            "picker_api_key": "synthetic-picker-key", "picker_app_id": config.settings.PROJECT_NUMBER}},  # pragma: allowlist secret (synthetic test value)
        "specimen-collection-bindings": {**BASE, COLLECTION: "intake-e2e"},
        "specimen-collection-job-routes": {f"{ORG}/{COLLECTION}": {"actor_uid": ACTOR,
            "worker_job": config.settings.PREFIX + "/jobs/specimen-worker-e2e",
            "intake_job": config.settings.PREFIX + "/jobs/specimen-intake-e2e"}},
    }


def write_bundle(directory, payload=None):
    for name, value in (values() if payload is None else payload).items():
        (directory / f"{name}.json").write_text(json.dumps({"version": 2 if name == "specimen-collection-bindings" else 1,
                                                        "value": value}))


def test_bundle_preflight_then_append_readback_and_idempotent_rerun(tmp_path, monkeypatch, capsys):
    write_bundle(tmp_path)
    cloud = Cloud()
    config.provision(tmp_path, dry_run=False, secrets=config.Secrets(cloud.run))
    assert len([row for row in cloud.writes if row[0] == "add"]) == 5
    for name, value in values().items():
        version = 2 if name == "specimen-collection-bindings" else 1
        assert json.loads(cloud.values[name][version]) == value
    assert len(json.loads(cloud.values["specimen-collection-bindings"][1])) == 18
    assert cloud.values["specimen-worker-actor-uid"][1] == ACTOR.encode()
    output = capsys.readouterr().out
    assert TOKEN not in output and ACTOR not in output and COLLECTION not in output
    cloud.writes.clear()
    config.provision(tmp_path, dry_run=False, secrets=config.Secrets(cloud.run))
    assert cloud.writes == []
    # Activation may advance the core pin to the already provisioned target.
    monkeypatch.setitem(config.settings.CORE_SECRET_VERSIONS, "specimen-collection-bindings", 2)
    config.provision(tmp_path, dry_run=False, secrets=config.Secrets(cloud.run))
    assert cloud.writes == []


def test_dry_run_reads_every_target_without_any_mutation_or_private_output(tmp_path, capsys):
    write_bundle(tmp_path)
    cloud = Cloud()
    config.provision(tmp_path, dry_run=True, secrets=config.Secrets(cloud.run))
    assert not cloud.writes
    described = {args[1] for args in cloud.calls if args[0] == "describe"}
    assert set(values()) <= described
    output = capsys.readouterr().out
    assert TOKEN not in output and ACTOR not in output and COLLECTION not in output


def test_late_existing_target_conflict_prevents_every_earlier_planned_write(tmp_path):
    write_bundle(tmp_path)
    cloud = Cloud()
    # This sorts after the missing config, bindings and routes targets.
    cloud.values["specimen-google-drive-client"] = {1: config.canonical({"client_secret": "different"})}
    with pytest.raises(config.Refused, match="existing target version differs"):
        config.provision(tmp_path, dry_run=False, secrets=config.Secrets(cloud.run))
    assert cloud.writes == [] and "specimen-cloud-import-config" not in cloud.values


@pytest.mark.parametrize("mutation", ["foreign_project", "wrong_version", "raw_secret", "bad_callback", "wrong_app", "wrong_actor",
                                      "binding_changed", "binding_removed", "extra_binding", "wrong_node", "different_scope"])
def test_invalid_bundle_dependencies_never_write_or_expose_values(tmp_path, mutation, capsys):
    payload = copy.deepcopy(values())
    provider = payload["specimen-cloud-import-config"]["google_drive"]
    route = payload["specimen-collection-job-routes"][f"{ORG}/{COLLECTION}"]
    if mutation == "foreign_project": provider["client_secret_ref"] = provider["client_secret_ref"].replace("specimen-digitization", "another-project")
    if mutation == "wrong_version": provider["client_secret_ref"] = provider["client_secret_ref"].replace("versions/1", "versions/2")
    if mutation == "raw_secret": provider["client_secret"] = TOKEN
    if mutation == "bad_callback": provider["redirect_uri"] = "https://other.example/callback"
    if mutation == "wrong_app": provider["picker_app_id"] = "123"
    if mutation == "wrong_actor": route["actor_uid"] = "different-actor"
    if mutation == "binding_changed": payload["specimen-collection-bindings"][next(iter(BASE))] = "different"
    if mutation == "binding_removed": del payload["specimen-collection-bindings"][next(iter(BASE))]
    if mutation == "extra_binding": payload["specimen-collection-bindings"][str(UUID(int=3))] = "intake-e2e"
    if mutation == "wrong_node": payload["specimen-collection-bindings"][COLLECTION] = "zoology_insects"
    if mutation == "different_scope": payload["specimen-collection-job-routes"] = {f"{ORG}/{str(UUID(int=3))}": route}
    write_bundle(tmp_path, payload)
    cloud = Cloud()
    with pytest.raises(config.Refused) as failure:
        config.provision(tmp_path, dry_run=False, secrets=config.Secrets(cloud.run))
    assert cloud.writes == [] and TOKEN not in str(failure.value)
    assert TOKEN not in capsys.readouterr().out


def test_disabled_existing_target_and_version_gaps_fail_closed(tmp_path):
    write_bundle(tmp_path, {"specimen-external-emails": ["synthetic@example.com"]})
    path = tmp_path / "specimen-external-emails.json"
    cloud = Cloud()
    cloud.values["specimen-external-emails"] = {1: config.canonical(["synthetic@example.com"])}
    cloud.disabled.add(("specimen-external-emails", 1))
    with pytest.raises(config.Refused): config.provision(tmp_path, dry_run=False, secrets=config.Secrets(cloud.run))
    cloud.values.pop("specimen-external-emails")
    path.write_text(json.dumps({"version": 2, "value": ["synthetic@example.com"]}))
    with pytest.raises(config.Refused, match="next numbered version"):
        config.provision(tmp_path, dry_run=False, secrets=config.Secrets(cloud.run))
    assert cloud.writes == []


def test_remote_failure_output_never_reaches_error_or_console(tmp_path, capsys):
    write_bundle(tmp_path, {"specimen-external-emails": ["synthetic@example.com"]})
    cloud = Cloud()
    cloud.fail = "describe"
    with pytest.raises(config.Refused) as failure:
        config.provision(tmp_path, dry_run=False, secrets=config.Secrets(cloud.run))
    assert TOKEN not in str(failure.value) + capsys.readouterr().out and cloud.writes == []


@pytest.mark.parametrize("name", ["arbitrary.json", "specimen-intake-client.json"])
def test_unapproved_file_names_are_refused_before_remote_reads(tmp_path, name):
    (tmp_path / name).write_text('{"version":1,"value":{}}')
    cloud = Cloud()
    with pytest.raises(config.Refused): config.provision(tmp_path, dry_run=False, secrets=config.Secrets(cloud.run))
    assert cloud.calls == []


def test_symlink_cannot_import_a_file_outside_the_selected_bundle(tmp_path):
    outside = tmp_path / "outside"
    outside.write_text('{}')
    (tmp_path / "specimen-external-emails.json").symlink_to(outside)
    with pytest.raises(config.Refused): config.bundle(tmp_path)


def test_provisioner_requires_the_explicit_owner_setup_mode(monkeypatch, tmp_path):
    monkeypatch.delenv("SPECIMEN_OWNER_SETUP_MODE", raising=False)
    monkeypatch.setattr(sys, "argv", ["intake_config.py", "--directory", str(tmp_path)])
    with pytest.raises(config.Refused, match="owner_setup"):
        config.main()
