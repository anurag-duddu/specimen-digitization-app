"""Restricted Picker provisioning, with no real provider or cloud writes."""
import copy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import intake_picker_key as picker  # noqa: E402
from test_intake_config import ACTOR, COLLECTION, TOKEN, Cloud, values, write_bundle  # noqa: E402
from test_intake_config import synthetic_core_pins  # noqa: E402,F401 -- shared autouse fake-store baseline

KEY_VALUE = "synthetic-private-picker-key-value"


def metadata():
    return {"name": picker.RESOURCE, "displayName": picker.DISPLAY_NAME, "annotations": picker.ANNOTATIONS,
        "restrictions": {"apiTargets": [{"service": "picker.googleapis.com"}],
            "browserKeyRestrictions": {"allowedReferrers": list(picker.REFERRERS)}}}


class KeyCloud:
    def __init__(self, existing=False):
        self.metadata = metadata() if existing else None
        self.calls, self.writes, self.pauses = [], [], []
        self.lose_response = self.create_fails = self.get_fails = False
        self.before_create = self.before_get = lambda: None

    def run(self, command, **kwargs):
        assert kwargs == {"capture_output": True, "check": False, "timeout": 60}
        assert command[:3] == ["gcloud", "services", "api-keys"]
        assert command[-2:] == ["--project=specimen-digitization", "--quiet"]
        args = command[3:-2]
        self.calls.append(args)
        out, error = b"", b""
        if args[0] == "describe":
            assert args[1:3] == [picker.KEY_ID, "--location=global"]
            assert "keyString" not in args[3]
            if self.metadata is None: error = b"NOT_FOUND"
            else: out = json.dumps(self.metadata).encode()
        elif args[0] == "create":
            self.before_create()
            assert self.metadata is None
            assert set(args[1:]) == {f"--key-id={picker.KEY_ID}", f"--display-name={picker.DISPLAY_NAME}",
                "--annotations=specimen-purpose=intake-picker", "--api-target=service=picker.googleapis.com",
                "--allowed-referrers=https://specimen-api-716045864126.us-east4.run.app/*,https://docs.google.com/*",
                "--format=value(name)"}
            self.writes.append("create")
            if not self.create_fails:
                self.metadata = metadata()
            if self.lose_response:
                raise subprocess.TimeoutExpired(command, 60, output=KEY_VALUE.encode(), stderr=TOKEN.encode())
            if self.create_fails: error = TOKEN.encode()
            out = (picker.RESOURCE + "\n").encode()
        elif args[0] == "get-key-string":
            self.before_get()
            assert args[1:] == [picker.KEY_ID, "--location=global", "--format=value(keyString)"]
            if self.get_fails: error = KEY_VALUE.encode()
            out = (KEY_VALUE + "\n").encode()
        else:
            pytest.fail("Unexpected Picker operation")
        return SimpleNamespace(returncode=1 if error else 0, stdout=out, stderr=error)

    def client(self):
        return picker.Keys(self.run, pause=self.pauses.append)


def pending_bundle(tmp_path):
    payload = values()
    payload[picker.CONFIG_NAME]["google_drive"]["picker_api_key"] = ""
    write_bundle(tmp_path, payload)
    return tmp_path / f"{picker.CONFIG_NAME}.json"


def test_create_is_restricted_and_preflighted_then_private_write_and_idempotent_rerun(tmp_path, capsys):
    path = pending_bundle(tmp_path)
    cloud, keys = Cloud(), KeyCloud()
    def all_targets_read():
        assert set(values()) <= {args[1] for args in cloud.calls if args[0] == "describe"}
        assert cloud.writes == []
    keys.before_create = all_targets_read
    picker.provision(tmp_path, dry_run=False, keys=keys.client(), secrets=picker.config.Secrets(cloud.run))
    saved = json.loads(path.read_bytes())
    assert saved["version"] == 1
    assert saved["value"]["google_drive"]["picker_api_key"] == KEY_VALUE
    assert path.stat().st_mode & 0o777 == 0o600 and not list(tmp_path.glob(".picker-config-*"))
    assert keys.writes == ["create"] and len(cloud.writes) == 9
    assert picker.PENDING.encode() not in cloud.values[picker.CONFIG_NAME][1]
    assert json.loads(cloud.values[picker.CONFIG_NAME][1]) == saved["value"]
    writes, content = list(cloud.writes), path.read_bytes()
    picker.provision(tmp_path, dry_run=False, keys=keys.client(), secrets=picker.config.Secrets(cloud.run))
    assert cloud.writes == writes and keys.writes == ["create"] and path.read_bytes() == content
    output = capsys.readouterr().out
    assert not any(private in output for private in (KEY_VALUE, TOKEN, ACTOR, COLLECTION))


@pytest.mark.parametrize("existing", [False, True])
def test_dry_run_never_changes_keys_files_configuration_or_iam(tmp_path, existing, capsys):
    path = pending_bundle(tmp_path)
    before = path.read_bytes()
    cloud, keys = Cloud(), KeyCloud(existing)
    picker.provision(tmp_path, dry_run=True, keys=keys.client(), secrets=picker.config.Secrets(cloud.run))
    assert path.read_bytes() == before and keys.writes == cloud.writes == []
    assert ("get-key-string" in [args[0] for args in keys.calls]) == existing
    output = capsys.readouterr().out
    assert "no keys, private files, configuration or IAM changed" in output
    assert KEY_VALUE not in output and TOKEN not in output


def test_lost_create_response_is_reconciled_without_repeating_the_write(tmp_path):
    pending_bundle(tmp_path)
    cloud, keys = Cloud(), KeyCloud()
    keys.lose_response = True
    picker.provision(tmp_path, dry_run=False, keys=keys.client(), secrets=picker.config.Secrets(cloud.run))
    assert keys.writes == ["create"] and cloud.writes


def test_unconfirmed_create_stops_safely_and_next_run_uses_the_same_fixed_id(tmp_path, capsys):
    path = pending_bundle(tmp_path)
    before = path.read_bytes()
    cloud, keys = Cloud(), KeyCloud()
    keys.lose_response = keys.create_fails = True
    with pytest.raises(picker.config.Refused, match="rerun the same setup") as failure:
        picker.provision(tmp_path, dry_run=False, keys=keys.client(), secrets=picker.config.Secrets(cloud.run))
    assert keys.writes == ["create"] and cloud.writes == [] and path.read_bytes() == before
    assert keys.pauses == [1, 2]
    assert KEY_VALUE not in str(failure.value) + capsys.readouterr().out
    # The server finishes after our last read. The rerun recovers that key.
    keys.metadata = metadata()
    picker.provision(tmp_path, dry_run=False, keys=keys.client(), secrets=picker.config.Secrets(cloud.run))
    assert keys.writes == ["create"] and cloud.writes


@pytest.mark.parametrize("mutation", ["unrestricted", "extra_api", "extra_referrer", "missing_iframe", "deleted", "foreign_project", "service_account"])
def test_differing_existing_key_is_never_reused_updated_or_exposed(tmp_path, mutation, capsys):
    path = pending_bundle(tmp_path)
    before = path.read_bytes()
    cloud, keys = Cloud(), KeyCloud(existing=True)
    if mutation == "unrestricted": keys.metadata["restrictions"].pop("apiTargets")
    if mutation == "extra_api": keys.metadata["restrictions"]["apiTargets"].append({"service": "drive.googleapis.com"})
    if mutation == "extra_referrer": keys.metadata["restrictions"]["browserKeyRestrictions"]["allowedReferrers"].append("https://*.example.com/*")
    if mutation == "missing_iframe": keys.metadata["restrictions"]["browserKeyRestrictions"]["allowedReferrers"].pop()
    if mutation == "deleted": keys.metadata["deleteTime"] = "2026-10-17T00:00:00Z"
    if mutation == "foreign_project": keys.metadata["name"] = keys.metadata["name"].replace("716045864126", "123")
    if mutation == "service_account": keys.metadata["serviceAccountEmail"] = "other@example.com"
    with pytest.raises(picker.config.Refused):
        picker.provision(tmp_path, dry_run=False, keys=keys.client(), secrets=picker.config.Secrets(cloud.run))
    assert cloud.writes == keys.writes == [] and path.read_bytes() == before
    assert all(args[0] == "describe" for args in keys.calls)
    assert KEY_VALUE not in capsys.readouterr().out


def test_exact_referrers_accept_provider_reordering_and_empty_method_list(tmp_path):
    pending_bundle(tmp_path)
    cloud, keys = Cloud(), KeyCloud(existing=True)
    keys.metadata["restrictions"]["browserKeyRestrictions"]["allowedReferrers"].reverse()
    keys.metadata["restrictions"]["apiTargets"][0]["methods"] = []
    picker.provision(tmp_path, dry_run=False, keys=keys.client(), secrets=picker.config.Secrets(cloud.run))
    assert not keys.writes and cloud.writes


def test_late_configuration_conflict_prevents_key_create_and_every_config_write(tmp_path):
    path = pending_bundle(tmp_path)
    before = path.read_bytes()
    cloud, keys = Cloud(), KeyCloud()
    cloud.values["specimen-google-drive-client"] = {1: picker.config.canonical({"client_secret": "different"})}
    with pytest.raises(picker.config.Refused, match="existing target version differs"):
        picker.provision(tmp_path, dry_run=False, keys=keys.client(), secrets=picker.config.Secrets(cloud.run))
    assert cloud.writes == keys.writes == [] and path.read_bytes() == before


def test_existing_target_resolves_empty_local_key_and_skips_matching_version(tmp_path):
    path = pending_bundle(tmp_path)
    cloud, keys = Cloud(), KeyCloud(existing=True)
    for name, value in values().items():
        if name == picker.CONFIG_NAME: value["google_drive"]["picker_api_key"] = KEY_VALUE
        version = 2 if name == "specimen-collection-bindings" else 1
        cloud.values.setdefault(name, {})[version] = picker.config.canonical(value)
    picker.provision(tmp_path, dry_run=False, keys=keys.client(), secrets=picker.config.Secrets(cloud.run))
    assert cloud.writes == keys.writes == []
    assert json.loads(path.read_bytes())["value"]["google_drive"]["picker_api_key"] == KEY_VALUE


def test_ordinary_provisioner_rejects_pending_empty_key_before_any_write(tmp_path):
    pending_bundle(tmp_path)
    cloud = Cloud()
    with pytest.raises(picker.config.Refused):
        picker.config.provision(tmp_path, dry_run=False, secrets=picker.config.Secrets(cloud.run))
    assert cloud.writes == []


def test_private_wrapper_concurrent_edit_is_not_overwritten(tmp_path):
    path = pending_bundle(tmp_path)
    cloud, keys = Cloud(), KeyCloud(existing=True)
    keys.before_get = lambda: path.write_text("concurrent edit")
    with pytest.raises(picker.config.Refused, match="changed during setup"):
        picker.provision(tmp_path, dry_run=False, keys=keys.client(), secrets=picker.config.Secrets(cloud.run))
    assert path.read_text() == "concurrent edit" and cloud.writes == keys.writes == []


def test_private_key_errors_are_suppressed_and_do_not_write_wrapper_or_config(tmp_path, capsys):
    path = pending_bundle(tmp_path)
    before = path.read_bytes()
    cloud, keys = Cloud(), KeyCloud(existing=True)
    keys.get_fails = True
    with pytest.raises(picker.config.Refused) as failure:
        picker.provision(tmp_path, dry_run=False, keys=keys.client(), secrets=picker.config.Secrets(cloud.run))
    assert KEY_VALUE not in str(failure.value) + capsys.readouterr().out
    assert cloud.writes == keys.writes == [] and path.read_bytes() == before


def test_picker_provisioner_requires_explicit_owner_setup_mode(monkeypatch, tmp_path):
    monkeypatch.delenv("SPECIMEN_OWNER_SETUP_MODE", raising=False)
    monkeypatch.setattr(sys, "argv", ["intake_picker_key.py", "--directory", str(tmp_path)])
    with pytest.raises(picker.config.Refused, match="owner_setup"):
        picker.main()
