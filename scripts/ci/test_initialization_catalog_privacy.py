"""Private native catalogs must never enter public Actions receipts or artifacts."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import pytest

import deploy_data as data
import release_initialize as init
from test_data_initialization import packet, SHA


@pytest.fixture(scope="module")
def catalog_keys():
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return {"public_key_pem": public.decode(), "public_key_sha256": hashlib.sha256(public).hexdigest()}, private


@pytest.mark.parametrize("returncode", [0, 1])
def test_private_catalog_canary_never_reaches_public_outputs(tmp_path, monkeypatch, catalog_keys, returncode):
    recipient, private = catalog_keys
    authority = packet()
    plan = {"version": "data-initialization-inventory/v1", "source_sha": SHA,
            "database_etag": "expected", "initialization_files": init.fingerprints(),
            "catalog_recipient": recipient}
    canary = "private-role-and-acl-canary"
    observed = {"roles": [{"name": canary}], "namespaces": [{"acl": canary}]}
    raw = json.dumps({"instance": data.SOURCE, "mode": "inspect", "files": init.fingerprints(),
                      "catalog": observed, "native_client_sessions": 0, "qualified": returncode == 0}).encode()
    def run(args, **kwargs):
        Path(args[-1]).write_bytes(raw)
        Path(args[-1]).chmod(0o600)
        return SimpleNamespace(returncode=returncode)
    monkeypatch.setattr(init.subprocess, "run", run)
    class Google:
        packet = authority
        def request(self, *args, **kwargs):
            return {"region": "us-east4", "databaseVersion": "POSTGRES_18", "settings": {"settingsVersion": "expected"}}
    directory = tmp_path / "data-release"
    directory.mkdir(mode=0o700)
    output = tmp_path / "data-ready.json"
    if returncode:
        with pytest.raises(ValueError):
            init.inspect_catalog(Google(), plan, directory, output)
        assert not output.exists()
    else:
        init.inspect_catalog(Google(), plan, directory, output)
        receipt = json.loads(output.read_bytes())
        assert "catalog" not in receipt and receipt["catalog_sha256"] == init.sha(observed)
        assert receipt["data_ready"] is False
    envelopes = list(directory.glob("*.encrypted.json"))
    assert len(envelopes) == 1, "even rejected native facts need controlled evidence"
    for public in [*envelopes, *tmp_path.glob("data-ready.json")]:
        assert canary.encode() not in public.read_bytes()
    assert not (directory / f"{data.SOURCE}-inspect.json").exists()
    from release_catalog_envelope import decrypt_catalog
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)  # Synthetic local coordinator verification.
    plaintext = decrypt_catalog(json.loads(envelopes[0].read_bytes()), private,
        public_key_sha256=recipient["public_key_sha256"], provenance={
            "repository": "anurag-duddu/specimen-digitization-app", "source_sha": SHA,
            "run_id": authority["release_run_id"], "run_attempt": authority["release_run_attempt"]})
    assert plaintext == raw
    assert init.sha(json.loads(plaintext)["catalog"]) == init.sha(observed)
    if not returncode:
        assert receipt["catalog_evidence"] == {"file": envelopes[0].name,
            "sha256": hashlib.sha256(envelopes[0].read_bytes()).hexdigest()}


def test_recipient_mismatch_blocks_plan_before_native_access(catalog_keys):
    recipient, _ = catalog_keys
    plan = {"version": "data-initialization-inventory/v1", "source_sha": SHA,
            "database_etag": "expected", "initialization_files": init.fingerprints(),
            "catalog_recipient": recipient}
    assert data.validate_plan(plan, packet()) is plan
    with pytest.raises(ValueError):
        data.validate_plan({**plan, "catalog_recipient": {**recipient, "public_key_sha256": "0" * 64}}, packet())


def test_workflow_never_uploads_raw_native_catalog_files(tmp_path):
    import yaml
    workflow = yaml.safe_load((init.ROOT / ".github/workflows/data-release.yml").read_text())
    directory = tmp_path / "data-release"
    directory.mkdir()
    canary = b"private-native-catalog-canary"
    for mode in ("inspect", "absence", "capability"):
        (directory / f"{data.SOURCE}-{mode}.json").write_bytes(canary)
    uploaded = []
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            if str(step.get("uses", "")).startswith("actions/upload-artifact@"):
                for pattern in step["with"]["path"].splitlines():
                    prefix = "${{ runner.temp }}/"
                    if pattern.startswith(prefix):
                        uploaded.extend(tmp_path.glob(pattern.removeprefix(prefix)))
    assert all(canary not in path.read_bytes() for path in uploaded if path.is_file())
