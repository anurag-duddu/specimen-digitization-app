"""Offline server/runner races and locked SDK transport; never use real credentials."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import deploy_data as data
import release_initialize as initialize
import release_google as transport

NOW = 1788890400
BUCKET = "specimen-digitization.firebasestorage.app"
KEY = "application/release-control/first-production-restore.json"


class BackupReached(Exception):
    pass


def packet(value=None):
    return {"source_sha": "a" * 40, "source_tree_sha": "b" * 40,
            "plan_sha256": hashlib.sha256(json.dumps(value or plan()).encode()).hexdigest(),
            "authorization_sha256": "c" * 64, "pilot": {"manifest_sha256": "d" * 64},
            "release_run_id": 123, "release_run_attempt": 2,
            "issued_at_unix": NOW - 10, "expires_at_unix": NOW + 7100,
            "identity": {"project_number": "716045864126"}}


def allowance():
    return {"version": "first-production-restore/v1", "bucket": BUCKET, "object": KEY,
            "authority_sha256": "c" * 64, "baseline_sha256": "e" * 64,
            "manifest_sha256": "d" * 64, "iam_sha256": "f" * 64,
            "issued_at_unix": NOW - 10, "expires_at_unix": NOW + 7100}


def plan():
    return {"version": "data-apply/v1", "source_sha": "a" * 40,
            "database_etag": "6", "schema_mode": "initialize_empty",
            "recovery": {"expires_at_unix": NOW + 7000, "recipe": {}, "backup_id": "1", "allowance": allowance()},
            "initialization": {"files": {}, "catalog_sha256": "b" * 64}, "catalog_recipient": {}}


class Server:
    def __init__(self):
        import threading
        self.lock = threading.Lock()
        self.claims = []
        self.backups = 0

    def insert(self, payload, directory):
        from release_diagnostics import HTTPFailure
        with self.lock:
            self.claims.append(payload)
            won = len(self.claims) == 1
        if not won:
            raise HTTPFailure(412)
        import base64
        return {"kind": "storage#object", "bucket": BUCKET, "name": KEY, "generation": "1",
                "metageneration": "1", "size": str(len(payload)), "temporaryHold": True,
                "contentType": "application/json", "md5Hash": base64.b64encode(hashlib.md5(payload).digest()).decode()}


def publish_fixture(google, value, monkeypatch):
    """Replace only remote publication/attestation; retain exact local bindings."""
    import release_admission
    import release_clone
    import deploy_runtime
    google.packet.update(source_tree_sha="b" * 40, plan_sha256=hashlib.sha256(json.dumps(value).encode()).hexdigest())
    for name, content in (("packet.json", google.packet), ("plan.json", value)):
        target = google.path.parent / name
        target.write_text(json.dumps(content))
        target.chmod(0o600)
    monkeypatch.setattr(release_admission, "admit", lambda *a, **kw: google.packet)
    monkeypatch.setattr(deploy_runtime, "verified_receipt_bytes", lambda path, *a: path.read_bytes())
    def download(command, **kw):
        target = Path(command[-1]) / "clone-allowance-intent.json"
        target.write_bytes((google.path.parent / "clone-allowance-intent.json").read_bytes())
    monkeypatch.setattr(deploy_runtime, "checked", download)
    release_clone.prepare_intent(google.path, google.packet, value)


def fixture(tmp_path, monkeypatch, server, *, value=None):
    value = value or plan()
    monkeypatch.setattr(data.time, "time", lambda: NOW)
    monkeypatch.setattr(data, "clone_body", lambda *a, **kw: {})
    monkeypatch.setattr(data, "sql_inventory", lambda *a, **kw: {"rows": []})
    monkeypatch.setattr(initialize, "native", lambda *a, **kw: {})
    def backup(*a, **kw):
        server.backups += 1
        raise BackupReached()
    monkeypatch.setattr(data, "ensure_backup", backup)
    authority = packet(value)
    for name, content in (("packet.json", authority), ("plan.json", value)):
        (tmp_path / name).write_text(json.dumps(content))
        (tmp_path / name).chmod(0o600)
    monkeypatch.setattr(transport, "admit", lambda *a, **kw: authority)
    import release_admission
    monkeypatch.setattr(release_admission, "admit", lambda *a, **kw: authority)
    import deploy_runtime
    monkeypatch.setattr(deploy_runtime, "verified_receipt_bytes", lambda path, *a: path.read_bytes())
    def download(command, **kw):
        target = Path(command[-1]) / "clone-allowance-intent.json"
        target.write_bytes((tmp_path / "clone-allowance-intent.json").read_bytes())
    monkeypatch.setattr(deploy_runtime, "checked", download)
    class Google:
        plane = "data"
        path = tmp_path / "packet.json"
        packet = authority
        claim_restore = staticmethod(server.insert)
        def request(self, api, method, resource, **kw):
            assert method == "GET", "no SQL mutation is expected before the backup sentinel"
            if resource.endswith("/instances/" + data.SOURCE):
                return {"region": "us-east4", "settings": {"settingsVersion": "6"}}
            if resource.endswith("/instances/" + data.CLONE) or api == "run":
                return None
            if resource.endswith("/operations"):
                return {"kind": "sql#operationsList", "items": []}
            pytest.fail("unexpected native request: " + resource)
    google = Google()
    # The behavior tests also run against aa7, before a claim helper exists.
    # On the candidate, prepare the same immutable intent on each fresh runner.
    if (Path(data.__file__).parent / "release_clone.py").exists():
        import release_clone
        release_clone.prepare_intent(google.path, google.packet, value)
    return google, value


@pytest.mark.parametrize("modes", [("ordinary", "ordinary"), ("initialize", "initialize"), ("ordinary", "initialize")])
def test_same_packet_on_independent_runners_can_unlock_only_one_backup(tmp_path, monkeypatch, modes):
    server = Server()
    for index, mode in enumerate(modes):
        directory = tmp_path / str(index)
        directory.mkdir()
        google, value = fixture(directory, monkeypatch, server)
        try:
            if mode == "ordinary":
                data.rehearse(google, value, directory)
            else:
                initialize.prepare_recovery(google, value, directory, directory / "result.json")
        except (BackupReached, ValueError):
            pass
        except Exception as error:
            from release_diagnostics import HTTPFailure
            assert isinstance(error, HTTPFailure)
    assert server.backups == 1, "a fresh runner/copy of one signed intent must never unlock a second backup"
    assert len(server.claims) == 2 and server.claims[0] == server.claims[1]


@pytest.mark.parametrize("kind", ["clone", "claim"])
@pytest.mark.parametrize("status", [401, 403, 412, 429, 503, 302, "timeout"])
def test_locked_authorized_session_does_not_refresh_and_replay_clone_post(tmp_path, monkeypatch, kind, status):
    import google.auth
    from google.auth.credentials import Credentials
    from requests import Response
    from requests.adapters import BaseAdapter
    class Credential(Credentials):
        def __init__(self):
            super().__init__()
            self.token = "synthetic-only"
            self.refreshes = 0
        def refresh(self, request):
            self.refreshes += 1
            self.token = "synthetic-refreshed"
    credential = Credential()
    monkeypatch.setattr(transport, "admit", lambda *a, **kw: packet())
    monkeypatch.setattr(transport, "github_credential_bytes", lambda *a: b"{}")
    monkeypatch.setattr(transport, "validate_credentials", lambda *a: None)
    monkeypatch.setattr(google.auth, "load_credentials_from_dict", lambda *a, **kw: (credential, None))
    monkeypatch.setenv("GOOGLE_GHA_CREDS_PATH", str(tmp_path / "gha-creds-test.json"))
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE", raising=False)
    google = transport.Google(tmp_path / "packet.json", "data-initialization")
    google.plane = "data"
    import release_clone
    assert google.session.adapters["https://"].max_retries.total == 0
    assert google.session.adapters["http://"].max_retries.total == 0
    monkeypatch.setenv("RELEASE_SERVICE_ACCOUNT", release_clone.ACTOR)
    # This test isolates the real SDK's retry behavior after admission. Guard
    # denial at the actual Google.request boundary is tested separately.
    monkeypatch.setattr(release_clone, "authorize_effect", lambda *a: None)
    monkeypatch.setattr(transport.time, "time", lambda: NOW)
    class Adapter(BaseAdapter):
        calls = 0
        def send(self, request, **kwargs):
            self.calls += 1
            if status == "timeout":
                from requests.exceptions import Timeout
                raise Timeout("synthetic wire timeout")
            response = Response()
            response.status_code = status if self.calls == 1 else 200
            response._content = b'{"name":"duplicate-create"}'
            response._content_consumed = True
            response.headers["Location"] = "https://foreign.example/redirect"
            response.request = request
            return response
        def close(self):
            pass
    adapter = Adapter()
    google.session.mount("https://", adapter)
    from release_diagnostics import HTTPFailure
    from requests.exceptions import Timeout
    with pytest.raises(Timeout if status == "timeout" else HTTPFailure):
        if kind == "clone":
            google.request("sql", "POST", f"projects/{data.PROJECT}/instances", body={})
        else:
            google.claim_restore(json.dumps({"recovery_expires_at_unix": NOW + 7000}).encode(), tmp_path)
    assert adapter.calls == 1 and credential.refreshes == 0


@pytest.mark.parametrize("mode", ["ordinary", "initialize"])
@pytest.mark.parametrize("failure", [401, 403, 412, 429, 503, "timeout", "lost-after-commit"])
def test_failed_or_unknown_claim_cannot_unlock_any_backup(tmp_path, monkeypatch, mode, failure):
    from release_diagnostics import HTTPFailure
    server = Server()
    insert = server.insert
    def fail(payload, directory):
        if failure == "lost-after-commit":
            insert(payload, directory)
        if isinstance(failure, int):
            raise HTTPFailure(failure)
        raise TimeoutError("synthetic lost response")
    server.insert = fail
    google, value = fixture(tmp_path, monkeypatch, server)
    with pytest.raises((HTTPFailure, TimeoutError)):
        if mode == "ordinary":
            data.rehearse(google, value, tmp_path)
        else:
            initialize.prepare_recovery(google, value, tmp_path, tmp_path / "result.json")
    assert server.backups == 0
    assert json.loads((tmp_path / "clone-allowance-send.json").read_bytes())["outcome"] == "unknown"


@pytest.mark.parametrize("change", [
    {"kind": "other"}, {"bucket": "foreign"}, {"name": KEY + "-retry"}, {"generation": "0"},
    {"generation": 1}, {"metageneration": "2"}, {"size": "0"}, {"md5Hash": "wrong"},
    {"temporaryHold": False}, {"temporaryHold": "true"}, {"contentType": "text/plain"},
])
def test_only_exact_fresh_held_native_response_mints_a_winner(tmp_path, monkeypatch, change):
    import release_clone
    server = Server()
    insert = server.insert
    server.insert = lambda *a: {**insert(*a), **change}
    google, value = fixture(tmp_path, monkeypatch, server)
    with pytest.raises(ValueError):
        release_clone.acquire(google, value, tmp_path)
    assert server.backups == 0 and len(server.claims) == 1


@pytest.mark.parametrize("name", ["clone-allowance-send.json", "clone-allowance-verified.json"])
def test_failed_local_retention_never_grants_recovery(tmp_path, monkeypatch, name):
    import release_clone
    server = Server()
    google, value = fixture(tmp_path, monkeypatch, server)
    retain = release_clone.retain
    def fail(path, raw):
        if path.name == name:
            raise OSError("synthetic retention failure")
        retain(path, raw)
    monkeypatch.setattr(release_clone, "retain", fail)
    with pytest.raises(OSError):
        data.rehearse(google, value, tmp_path)
    assert server.backups == 0
    assert len(server.claims) == (0 if name.endswith("send.json") else 1)


def test_copied_winner_receipt_and_dead_runner_never_resume_the_allowance(tmp_path, monkeypatch):
    import release_clone
    from release_diagnostics import HTTPFailure
    server = Server()
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir(); two.mkdir()
    google, value = fixture(one, monkeypatch, server)
    release_clone.acquire(google, value, one)  # Winner dies before any backup.
    copied = (one / "clone-allowance-verified.json").read_bytes()
    other, value = fixture(two, monkeypatch, server)
    (two / "clone-allowance-verified.json").write_bytes(copied)
    with pytest.raises(HTTPFailure) as error:
        data.rehearse(other, value, two)
    assert error.value.http_status == 412 and server.backups == 0 and len(server.claims) == 2


def test_concurrent_same_packet_runners_have_one_atomic_winner(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    import release_clone
    from release_diagnostics import HTTPFailure
    server = Server()
    barrier = threading.Barrier(2)
    insert = server.insert
    def race(*args):
        barrier.wait(timeout=5)
        return insert(*args)
    server.insert = race
    runners = []
    for name in ("one", "two"):
        directory = tmp_path / name
        directory.mkdir()
        google, value = fixture(directory, monkeypatch, server)
        runners.append((google, value, directory))
    def attempt(args):
        try:
            release_clone.acquire(*args).effect("clone-backup", lambda: True)
            return "winner"
        except HTTPFailure as error:
            assert error.http_status == 412
            return "spent"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, runners)) == ["spent", "winner"]
    assert server.claims[0] == server.claims[1]


@pytest.mark.parametrize("publication", ["missing", "download-failed", "signature-failed", "changed-run"])
def test_publication_and_original_signed_binding_precede_claim(tmp_path, monkeypatch, publication):
    import deploy_runtime
    import release_clone
    server = Server()
    google, value = fixture(tmp_path, monkeypatch, server)
    if publication == "missing":
        (tmp_path / "clone-allowance-intent.json").unlink()
    elif publication == "changed-run":
        raw = json.loads((tmp_path / "clone-allowance-intent.json").read_bytes())
        raw["run_id"] += 1
        (tmp_path / "clone-allowance-intent.json").write_text(json.dumps(raw))
    else:
        def fail(*a, **kw):
            raise ValueError("synthetic publication failure")
        monkeypatch.setattr(deploy_runtime, "checked" if publication == "download-failed" else "verified_receipt_bytes", fail)
    with pytest.raises((ValueError, OSError)):
        release_clone.acquire(google, value, tmp_path)
    assert not server.claims and not (tmp_path / "clone-allowance-send.json").exists()


@pytest.mark.parametrize("project", [data.PROJECT, "716045864126"])
@pytest.mark.parametrize("suffix", ["instances", "backups", "instances/" + data.SOURCE + "/backupRuns",
                                     "instances/" + data.CLONE + "/restoreBackup"])
def test_actual_transport_denies_every_recovery_effect_without_live_capability(monkeypatch, project, suffix):
    google = transport.Google.__new__(transport.Google)
    google.packet, google.path, google.plane = packet(), Path("missing"), "data"
    google.session = SimpleNamespace(request=lambda *a, **kw: pytest.fail("unclaimed native effect"))
    monkeypatch.setattr(transport, "admit", lambda *a, **kw: google.packet)
    for forged in (None, True, {"generation": "1"}, {"winner": True}):
        google._clone_winner = forged
        with pytest.raises(ValueError, match="claim winner"):
            google.request("sql", "POST", f"projects/{project}/{suffix}", body={})


def test_winner_is_nonserializable_and_consumes_each_effect_before_wire(tmp_path, monkeypatch):
    import pickle
    import release_clone
    server = Server()
    google, value = fixture(tmp_path, monkeypatch, server)
    winner = release_clone.acquire(google, value, tmp_path)
    with pytest.raises(TypeError, match="serialized"):
        pickle.dumps(winner)
    calls = []
    def send(suffix):
        resource = f"projects/{data.PROJECT}/{suffix}"
        release_clone.authorize_effect(google, resource)
        calls.append(resource)
        with pytest.raises(ValueError, match="replayed"):
            release_clone.authorize_effect(google, resource)
        return {"name": "synthetic-only"}
    for name, suffix in (("clone-backup", "backups"), ("clone-create", "instances"),
                         ("clone-restore", "instances/" + data.CLONE + "/restoreBackup")):
        winner.effect(name, lambda: send(suffix))
        with pytest.raises(ValueError, match="replayed"):
            winner.effect(name, lambda: pytest.fail("replayed stage"))
        assert google._clone_winner is None
    assert len(calls) == 3
    with pytest.raises(ValueError, match="claim winner"):
        release_clone.authorize_effect(google, calls[-1])


@pytest.mark.parametrize("drift", ["source", "clone", "runtime", "budget", "deadline"])
def test_winning_claim_does_not_bypass_fresh_pre_effect_admission(tmp_path, monkeypatch, drift):
    import release_clone
    import release_admission
    server = Server()
    google, value = fixture(tmp_path, monkeypatch, server)
    winner = release_clone.acquire(google, value, tmp_path)
    read = google.request
    def changed(api, method, resource, **kw):
        if drift == "source" and resource.endswith(data.SOURCE):
            return {"region": "us-east4", "settings": {"settingsVersion": "changed"}}
        if drift == "clone" and resource.endswith(data.CLONE):
            return {"name": data.CLONE}
        if drift == "runtime" and api == "run":
            return {"name": "existing"}
        return read(api, method, resource, **kw)
    google.request = changed
    if drift == "budget":
        monkeypatch.setattr(release_admission, "admit", lambda *a: (_ for _ in ()).throw(ValueError("no remaining budget")))
    if drift == "deadline":
        monkeypatch.setattr(release_clone.time, "time", lambda: NOW + 6999)
    with pytest.raises(ValueError):
        winner.effect("clone-backup", lambda: pytest.fail("stale admitted effect"))
    # Failure retires the capability; catching an exception cannot skip ahead.
    with pytest.raises(ValueError, match="replayed"):
        winner.effect("clone-create", lambda: pytest.fail("continued after failed stage"))


@pytest.mark.parametrize("change", [
    {"object": KEY + "-new-run"}, {"bucket": "other"}, {"version": "first-production-restore/v2"},
    {"authority_sha256": "0" * 64}, {"manifest_sha256": "0" * 64}, {"baseline_sha256": ""},
    {"expires_at_unix": NOW + 9000}, {"issued_at_unix": NOW}, {"iam_sha256": ""},
    {"reset": True},
])
def test_typed_allowance_cannot_reset_identity_scope_or_original_window(change):
    import release_clone
    with pytest.raises(ValueError):
        release_clone.validate_allowance({**allowance(), **change}, packet(), NOW + 7000, now=NOW)


def test_multipart_is_one_bounded_exact_fixed_key_held_insert():
    import release_clone
    from email.parser import BytesParser
    payload = release_clone.canonical({"test": "synthetic-only"})
    body, content_type = release_clone.multipart(payload)
    message = BytesParser().parsebytes(b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body)
    metadata, content = message.get_payload()
    assert json.loads(metadata.get_payload(decode=True)) == {
        "name": KEY, "contentType": "application/json", "temporaryHold": True, "md5Hash": release_clone.checksum(payload)}
    assert content.get_payload(decode=True) == payload
    assert len(body) <= 4096
    assert release_clone.PARAMS == {"uploadType": "multipart", "name": KEY, "ifGenerationMatch": 0, "projection": "noAcl"}
    with pytest.raises(ValueError):
        release_clone.multipart(b"x" * 2049)


@pytest.mark.parametrize("body,headers", [(b"{", {}), (b"{}", {"Content-Length": "999"}),
                                         (b"x" * 17000, {}), (b"{}", {"Content-Encoding": "gzip"})])
def test_transport_retains_bounded_malformed_or_truncated_native_response(tmp_path, monkeypatch, body, headers):
    import release_clone
    google = transport.Google.__new__(transport.Google)
    google.packet, google.path, google.plane = packet(), tmp_path / "packet.json", "data"
    monkeypatch.setenv("RELEASE_SERVICE_ACCOUNT", release_clone.ACTOR)
    monkeypatch.setattr(transport.time, "time", lambda: NOW)
    monkeypatch.setattr(transport, "admit", lambda *a, **kw: google.packet)
    response = SimpleNamespace(status_code=200, headers=headers, close=lambda: None,
                               iter_content=lambda **kw: iter([body]))
    calls = []
    def request(*a, **kw):
        calls.append((a, kw))
        return response
    google.session = SimpleNamespace(request=request)
    with pytest.raises(ValueError):
        google.claim_restore(json.dumps({"recovery_expires_at_unix": NOW + 7000}).encode(), tmp_path)
    assert len(calls) == 1 and len((tmp_path / "clone-allowance-response.body").read_bytes()) <= 16385
    assert calls[0][0] == ("POST", release_clone.URL)
    assert calls[0][1]["allow_redirects"] is False


def test_workflow_publishes_original_intent_before_same_process_recovery():
    import yaml
    workflow = yaml.safe_load((Path(data.__file__).parents[2] / ".github/workflows/data-release.yml").read_text())
    jobs = workflow["jobs"]
    steps = next(job["steps"] for job in jobs.values()
                 if any("--prepare-clone-intent" in step.get("run", "") for step in job.get("steps", [])))
    prepare = next(i for i, step in enumerate(steps) if "--prepare-clone-intent" in step.get("run", ""))
    attest = next(i for i, step in enumerate(steps) if step.get("with", {}).get("subject-path", "").endswith("clone-allowance-intent.json"))
    publish = next(i for i, step in enumerate(steps) if step.get("with", {}).get("name", "").startswith("clone-allowance-intent-"))
    execute = next(i for i, step in enumerate(steps) if " --deploy " in step.get("run", ""))
    assert prepare < attest < publish < execute
    assert steps[publish]["with"]["if-no-files-found"] == "error"
    assert "overwrite" not in steps[publish]["with"]
    assert all("always()" not in steps[index].get("if", "") for index in (prepare, attest, publish, execute))


@pytest.mark.parametrize("kind", ["claim", "clone"])
def test_actual_http_body_cannot_outlive_hard_native_deadline(tmp_path, monkeypatch, kind):
    """Real localhost TCP body stalls; fixed Google URLs never leave the fixture."""
    import contextlib
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    import time as clock
    from google.auth.credentials import AnonymousCredentials
    from google.auth.transport.requests import AuthorizedSession
    from requests.adapters import HTTPAdapter
    from urllib3 import HTTPConnectionPool
    import release_clone
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.path)
            self.rfile.read(int(self.headers["Content-Length"]))
            body = b'{"name":"synthetic-native-response"}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body[:1]); self.wfile.flush()
            clock.sleep(0.2)
            try:
                self.wfile.write(body[1:]); self.wfile.flush()
            except OSError:
                pass
        def log_message(self, *a):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    google = transport.Google.__new__(transport.Google)
    google.packet, google.path, google.plane = packet(), tmp_path / "packet.json", "data"
    google.session = AuthorizedSession(AnonymousCredentials(), max_refresh_attempts=0)
    google.session.trust_env = False
    adapter = HTTPAdapter(max_retries=0)
    pool = HTTPConnectionPool("127.0.0.1", server.server_port, maxsize=1)
    monkeypatch.setattr(adapter, "get_connection_with_tls_context", lambda *a, **kw: pool)
    google.session.mount("https://", adapter)
    monkeypatch.setenv("RELEASE_SERVICE_ACCOUNT", release_clone.ACTOR)
    monkeypatch.setattr(transport, "admit", lambda *a, **kw: google.packet)
    monkeypatch.setattr(transport.time, "time", lambda: NOW)
    monkeypatch.setattr(release_clone, "authorize_effect", lambda *a: NOW + 7000)
    original = getattr(transport, "request_deadline", lambda seconds: contextlib.nullcontext())
    monkeypatch.setattr(transport, "request_deadline", lambda seconds: original(min(seconds, 0.05)), raising=False)
    try:
        with pytest.raises(TimeoutError):
            if kind == "claim":
                google.claim_restore(json.dumps({"recovery_expires_at_unix": NOW + 7000}).encode(), tmp_path)
            else:
                google.request("sql", "POST", f"projects/{data.PROJECT}/instances", body={})
        assert len(calls) == 1
    finally:
        google.session.close()
        pool.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
