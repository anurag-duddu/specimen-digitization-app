"""The worker's Logfire writer secret: one parent, one version, one identity request, one grant."""
import base64
import json
import os
from pathlib import Path
import stat

import pytest

from owner_gcloud import Gcloud, stamp
from release_context import PROJECT
import worker_trace_setup as T

NOW = 1_790_000_000
TOKEN = b"pylf_v1_us_ExampleWriterToken0123456789abcdef"  # pragma: allowlist secret (synthetic test token)
NATIVE_PARENT = "projects/716045864126/secrets/specimen-worker-logfire"
NOT_FOUND = f"ERROR: (gcloud.secrets.describe) NOT_FOUND: Secret [{NATIVE_PARENT}] not found."


class FakeCloud:
    def __init__(self, *, exists=False, payload=None, policy=None):
        self.exists = exists
        self.payload = payload
        self.policy = policy if policy is not None else {"etag": "ACAB"}
        self.calls = []
        self.stored = None
        self.stored_mode = None
        self.set_policies = []

    def __call__(self, args, timeout):
        assert args[-2:] == [f"--project={PROJECT}", "--quiet"] and 0 < timeout <= 30
        self.calls.append(args[:-2])
        head = args[:3]
        if head == ["secrets", "describe", T.SECRET_ID]:
            return (0, json.dumps({"name": NATIVE_PARENT}), "") if self.exists else (1, "", NOT_FOUND)
        if head == ["secrets", "create", T.SECRET_ID]:
            assert "--replication-policy=user-managed" in args and "--locations=us-east4" in args
            self.exists = True
            return 0, json.dumps({"name": NATIVE_PARENT, "replication": {"userManaged": {
                "replicas": [{"location": "us-east4"}]}}}), ""
        if head == ["secrets", "versions", "add"]:
            path = Path(next(a for a in args if a.startswith("--data-file="))[12:])
            self.stored = path.read_bytes()
            self.stored_mode = stat.S_IMODE(path.stat().st_mode)
            return 0, json.dumps({"name": f"{NATIVE_PARENT}/versions/1", "state": "ENABLED"}), ""
        if head == ["secrets", "versions", "describe"]:
            return 0, json.dumps({"name": f"{NATIVE_PARENT}/versions/1", "state": "ENABLED"}), ""
        if head == ["secrets", "versions", "access"]:
            data = self.payload if self.payload is not None else base64.urlsafe_b64encode(self.stored).decode()
            return 0, json.dumps({"payload": {"data": data}}), ""
        if head == ["secrets", "get-iam-policy", T.SECRET_ID]:
            return 0, json.dumps(self.policy), ""
        if head == ["secrets", "set-iam-policy", T.SECRET_ID]:
            policy = json.loads(Path(args[3]).read_text())
            assert policy["etag"] == self.policy["etag"], "compare-and-swap on the current etag"
            self.set_policies.append(policy)
            self.policy = {**policy, "etag": f"BwNew{len(self.set_policies)}="}
            return 0, json.dumps(self.policy), ""
        raise AssertionError(args)


def cloud(fake, ceiling=6):
    return Gcloud(NOW + 300, ceiling=ceiling, runner=fake, clock=lambda: float(NOW))


def token_file(tmp_path, raw=TOKEN + b"\n", mode=0o600):
    path = tmp_path / "writer.token"
    path.write_bytes(raw)
    os.chmod(path, mode)
    return path


def test_store_creates_the_parent_and_one_verified_version(tmp_path):
    fake = FakeCloud()
    receipt = T.store(T.read_token(token_file(tmp_path)), cloud(fake), now=NOW)
    assert fake.stored == TOKEN and fake.stored_mode == 0o600
    assert [c[:3] for c in fake.calls] == [
        ["secrets", "describe", T.SECRET_ID], ["secrets", "create", T.SECRET_ID], ["secrets", "versions", "add"],
        ["secrets", "versions", "describe"], ["secrets", "versions", "access"]]
    assert receipt["token_secret"] == f"{T.PARENT}/versions/1"
    assert receipt["token_secret_native"] == f"{NATIVE_PARENT}/versions/1"
    assert receipt["version"] == 1 and receipt["readback_verified"] is True and receipt["requests_used"] == 5
    assert receipt["replication"] == {"user_managed": ["us-east4"]}
    assert receipt["storage_quote"]["usd_31_days"] == 0.06
    assert TOKEN.decode() not in json.dumps(receipt)


def test_store_refuses_an_existing_parent(tmp_path):
    fake = FakeCloud(exists=True)
    with pytest.raises(ValueError, match="only when absent"):
        T.store(T.read_token(token_file(tmp_path)), cloud(fake), now=NOW)
    assert len(fake.calls) == 1 and fake.stored is None


def test_store_refuses_a_readback_that_differs(tmp_path):
    fake = FakeCloud(payload=base64.urlsafe_b64encode(b"different").decode())
    with pytest.raises(ValueError, match="does not match the private token"):
        T.store(T.read_token(token_file(tmp_path)), cloud(fake), now=NOW)


def test_decode_payload_accepts_both_base64_alphabets():
    raw = bytes(range(256))
    assert T.decode_payload({"payload": {"data": base64.urlsafe_b64encode(raw).decode()}}) == raw
    assert T.decode_payload({"payload": {"data": base64.b64encode(raw).decode()}}) == raw
    with pytest.raises(ValueError):
        T.decode_payload({"payload": {}})


@pytest.mark.parametrize("raw, mode", [
    (b"", 0o600), (b"\n", 0o600), (b"two\nlines\n", 0o600), (b" padded\n", 0o600),
    ("café".encode(), 0o600), (b"a" * 4097 + b"\n", 0o600), (TOKEN, 0o644),
])
def test_read_token_accepts_only_one_private_printable_line(tmp_path, raw, mode):
    with pytest.raises(ValueError):
        T.read_token(token_file(tmp_path, raw, mode))


def test_read_token_drops_only_the_trailing_newline(tmp_path):
    assert T.read_token(token_file(tmp_path, TOKEN + b"\r\n")) == TOKEN
    assert T.read_token(token_file(tmp_path, TOKEN)) == TOKEN


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    def read(self, size=-1):
        chunk, self._body = self._body[:size], self._body[size:]
        return chunk


class FakeConnection:
    def __init__(self, status=200, body=None):
        self.status = status
        self.body = body if body is not None else json.dumps(
            {"project_name": "specimen-digitization", "project_url": T.APPROVED_PROJECT_URL}).encode()
        self.requests = []
        self.closed = False

    def request(self, method, path, headers=None, body=None):
        self.requests.append((method, path, headers, body))

    def getresponse(self):
        return FakeResponse(self.status, self.body)

    def close(self):
        self.closed = True


def check(tmp_path, connection, **overrides):
    receipt = tmp_path / "identity.receipt.json"
    arguments = dict(token_secret=f"{T.PARENT}/versions/1", receipt_path=receipt, now=NOW,
                     connection_factory=lambda: connection)
    arguments.update(overrides)
    try:
        return T.identity(TOKEN, **arguments)
    finally:
        check.written = json.loads(receipt.read_text()) if receipt.exists() else None


def test_identity_verifies_the_approved_project_with_one_request(tmp_path):
    connection = FakeConnection()
    receipt = check(tmp_path, connection)
    assert connection.requests == [("GET", "/v1/info", {
        "Authorization": TOKEN.decode(), "Accept": "application/json",
        "User-Agent": "specimen-digitization-trace-identity/1", "Connection": "close"}, None)]
    assert connection.closed
    assert receipt["verified"] is True and receipt["http_status"] == 200 and receipt["attempts"] == 1
    assert receipt["project_url"] == T.APPROVED_PROJECT_URL
    assert receipt["trace_project_id"] == "anuragduddu/specimen-digitization"
    assert receipt["approval_sha256"] == T.TRACE_APPROVAL_SHA256
    written = tmp_path / "identity.receipt.json"
    assert check.written == receipt and stat.S_IMODE(written.stat().st_mode) == 0o600
    assert TOKEN.decode() not in written.read_text()
    attempt = tmp_path / "identity.receipt.attempt.json"
    assert json.loads(attempt.read_text())["attempted_at"] == stamp(NOW)


def test_identity_refuses_a_second_attempt(tmp_path):
    connection = FakeConnection()
    check(tmp_path, connection)
    with pytest.raises(ValueError, match="never replayed"):
        check(tmp_path, connection)
    assert len(connection.requests) == 1


def test_identity_refuses_another_project(tmp_path):
    body = json.dumps({"project_name": "other", "project_url": "https://logfire-us.pydantic.dev/someone/other"}).encode()
    with pytest.raises(ValueError, match="approved Logfire project"):
        check(tmp_path, FakeConnection(body=body))
    assert check.written["verified"] is False and "approved Logfire project" in check.written["failed"]
    assert "project_url" not in check.written


def test_identity_records_a_rejected_token(tmp_path):
    with pytest.raises(ValueError, match="answered 401"):
        check(tmp_path, FakeConnection(status=401, body=b'{"detail": "invalid token"}'))
    assert check.written["http_status"] == 401 and check.written["verified"] is False


def test_identity_refuses_an_oversized_response(tmp_path):
    with pytest.raises(ValueError, match="approved size"):
        check(tmp_path, FakeConnection(body=b"{" + b" " * T.BODY_LIMIT + b"}"))


@pytest.mark.parametrize("name", ["HTTPS_PROXY", "https_proxy", "SSL_CERT_FILE", "ALL_PROXY"])
def test_identity_refuses_proxy_and_tls_overrides_before_any_attempt(tmp_path, monkeypatch, name):
    monkeypatch.setenv(name, "x")
    connection = FakeConnection()
    with pytest.raises(ValueError, match="must not be set"):
        check(tmp_path, connection)
    assert connection.requests == [] and not (tmp_path / "identity.receipt.attempt.json").exists()


def test_fetch_token_requires_the_writer_version_resource():
    fake = FakeCloud()
    fake.stored = TOKEN
    assert T.fetch_token(cloud(fake, 1), f"{T.PARENT}/versions/1") == TOKEN
    for resource in (f"{T.PARENT}/versions/latest", f"{NATIVE_PARENT}/versions/1",
                     f"projects/{PROJECT}/secrets/huggingface-runtime-token/versions/2", ""):
        with pytest.raises(ValueError, match="writer version resource"):
            T.fetch_token(cloud(FakeCloud(), 1), resource)


def test_grant_then_revoke_by_compare_and_swap():
    fake = FakeCloud()
    expires = stamp(NOW + 3600)
    granted = T.grant(cloud(fake, 4), version=1, expires_at=expires, now=NOW)
    binding = granted["binding"]
    assert binding["role"] == "roles/secretmanager.secretAccessor" and binding["members"] == [T.WORKER_IDENTITY]
    assert binding["condition"]["expression"] == (
        f"resource.name.endsWith('/secrets/specimen-worker-logfire/versions/1') && request.time < timestamp('{expires}')")
    assert fake.set_policies[0] == {"etag": "ACAB", "version": 3, "bindings": [binding]}
    assert granted["policy_etag_after"] == "BwNew1=" and granted["requests_used"] == 3
    revoked = T.revoke(cloud(fake, 4), now=NOW)
    assert fake.set_policies[1] == {"etag": "BwNew1=", "version": 3, "bindings": []}
    assert revoked["removed"] == binding and revoked["policy_etag_after"] == "BwNew2="


def test_grant_refuses_existing_bindings_and_bad_expirations():
    occupied = FakeCloud(policy={"etag": "BwX=", "version": 3, "bindings": [
        {"role": "roles/secretmanager.secretAccessor", "members": ["serviceAccount:someone@example.iam.gserviceaccount.com"]}]})
    with pytest.raises(ValueError, match="no bindings before the grant"):
        T.grant(cloud(occupied, 4), version=1, expires_at=stamp(NOW + 60), now=NOW)
    assert occupied.set_policies == []
    for expires in (stamp(NOW - 1), stamp(NOW + 25 * 3600), "soon"):
        with pytest.raises(ValueError):
            T.grant(cloud(FakeCloud(), 4), version=1, expires_at=expires, now=NOW)
    with pytest.raises(ValueError, match="positive version"):
        T.grant(cloud(FakeCloud(), 4), version=0, expires_at=stamp(NOW + 60), now=NOW)


def test_revoke_removes_only_the_owned_grant():
    foreign = FakeCloud(policy={"etag": "BwX=", "version": 3, "bindings": [
        {"role": "roles/secretmanager.secretAccessor", "members": [T.WORKER_IDENTITY],
         "condition": {"title": "someone_else", "expression": "true"}}]})
    with pytest.raises(ValueError, match="only the one owned accessor grant"):
        T.revoke(cloud(foreign, 4), now=NOW)
    assert foreign.set_policies == []
    with pytest.raises(ValueError, match="only the one owned accessor grant"):
        T.revoke(cloud(FakeCloud(), 4), now=NOW)


def test_cli_store_prints_the_plan_value_and_never_the_token(tmp_path, monkeypatch, capsys):
    fake = FakeCloud()
    monkeypatch.setattr(T, "Gcloud", lambda deadline, ceiling: Gcloud(deadline, ceiling=ceiling, runner=fake))
    receipt = tmp_path / "writer.receipt.json"
    assert T.main(["store", "--token-file", str(token_file(tmp_path)), "--receipt", str(receipt)]) == 0
    printed = capsys.readouterr().out
    assert f"worker_logfire_token_secret_version: {T.PARENT}/versions/1" in printed
    assert TOKEN.decode() not in printed and TOKEN.decode() not in receipt.read_text()
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600


def test_cli_identity_prints_the_receipt_digest(tmp_path, monkeypatch, capsys):
    fake = FakeCloud()
    fake.stored = TOKEN
    monkeypatch.setattr(T, "Gcloud", lambda deadline, ceiling: Gcloud(deadline, ceiling=ceiling, runner=fake))
    connection = FakeConnection()
    monkeypatch.setattr(T.http.client, "HTTPSConnection", lambda *a, **k: connection)
    receipt = tmp_path / "identity.receipt.json"
    assert T.main(["identity", "--token-secret", f"{T.PARENT}/versions/1", "--receipt", str(receipt)]) == 0
    printed = capsys.readouterr().out
    import hashlib
    assert f"trace_identity_receipt_sha256: {hashlib.sha256(receipt.read_bytes()).hexdigest()}" in printed
    assert "trace_project_id: anuragduddu/specimen-digitization" in printed
    assert connection.requests[0][2]["Authorization"] == TOKEN.decode()
