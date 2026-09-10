"""Short-lived WIF transport with fixed Google API origins and mutation guards."""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import stat
import time
import threading
from urllib.parse import parse_qsl, urlsplit

from release_admission import admit, exact_keys, private_bytes, read_bound_plan, read_packet, require, strict_json
from release_context import PROJECT, validate_context
from release_diagnostics import HTTPFailure, stage
import release_publication_deadline as publication

ORIGINS = {"identity": "https://identitytoolkit.googleapis.com/v1/","run": "https://run.googleapis.com/v2/", "registry": "https://artifactregistry.googleapis.com/v1/",
           "project": "https://cloudresourcemanager.googleapis.com/v3/",
           "sql": "https://sqladmin.googleapis.com/sql/v1beta4/",
           "data": "https://firebasedataconnect.googleapis.com/v1/",
           "rules": "https://firebaserules.googleapis.com/v1/"}


class _DeadlineSignal(Exception):
    """Avoid SDK OSError handlers turning deadline expiry into a transport retry."""


@contextmanager
def request_deadline(seconds):
    """Ubuntu protected runner: interrupt refresh, headers and body reads alike."""
    require(threading.current_thread() is threading.main_thread() and 0 < seconds <= 30,
            "bounded native request requires the protected main process")
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "native request cannot replace another deadline")
    previous = signal.getsignal(signal.SIGALRM)
    deadline = time.monotonic() + seconds
    def expired(*args):
        raise _DeadlineSignal()
    signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
        if time.monotonic() >= deadline:
            raise TimeoutError("native request deadline reached")
    except _DeadlineSignal:
        raise TimeoutError("native request deadline reached") from None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def cleanup_permit(packet, clone_deadline=None):
    """Public ownership facts emitted only after the initial full admission."""
    return {**{key: packet[key] for key in ("source_sha", "release_run_id", "release_run_attempt",
                                          "issued_at_unix", "expires_at_unix", "identity")},
            "clone_expires_at_unix": min(packet["expires_at_unix"], clone_deadline or packet["expires_at_unix"])}


def cleanup_packet(packet_path, env):
    raw = env.get("RELEASE_CLEANUP_PERMIT")
    if raw:
        packet = strict_json(raw)
    else:
        original = read_packet(packet_path, env)
        plan = read_bound_plan(packet_path.parent / "plan.json", original)
        require(plan.get("version") in {"data-apply/v1", "data-initialize-missing/v1"}, "cleanup belongs only to native data apply/initialization")
        packet = cleanup_permit(original, plan["recovery"]["expires_at_unix"])
    exact_keys(packet, {"source_sha", "release_run_id", "release_run_attempt", "issued_at_unix", "expires_at_unix", "identity", "clone_expires_at_unix"}, "cleanup ownership permit")
    require(type(packet["clone_expires_at_unix"]) is int and packet["issued_at_unix"] < packet["clone_expires_at_unix"] <= packet["expires_at_unix"], "invalid clone disposal deadline")
    # Original credential-free admission output survives later repository-var
    # changes. Only owned-clone disposal has this source/deadline exception.
    validate_context({**env, "RELEASE_AUTHORIZED_SHA": packet["source_sha"]}, "data", packet["source_sha"])
    require(str(packet["release_run_id"]) == env.get("GITHUB_RUN_ID")
            and str(packet["release_run_attempt"]) == env.get("GITHUB_RUN_ATTEMPT"), "cleanup creator run mismatch")
    return packet


def validate_credentials(credential, packet, env):
    exact_keys(credential, {"type", "audience", "subject_token_type", "token_url", "credential_source", "service_account_impersonation_url"}, "GitHub WIF credentials")
    require(credential["type"] == "external_account"
            and credential["audience"] == f"//iam.googleapis.com/{packet['identity']['provider']}"
            and credential["subject_token_type"] == "urn:ietf:params:oauth:token-type:jwt"
            and credential["token_url"] == "https://sts.googleapis.com/v1/token"
            and credential["service_account_impersonation_url"] ==
            f"https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{env['RELEASE_SERVICE_ACCOUNT']}:generateAccessToken",
            "credential identity or token exchange does not match reviewed WIF resource")
    source = exact_keys(credential["credential_source"], {"url", "headers", "format"}, "GitHub OIDC source")
    actual, expected = urlsplit(source["url"]), urlsplit(env.get("ACTIONS_ID_TOKEN_REQUEST_URL", ""))
    require(expected.scheme == "https" and expected.hostname and expected.hostname.endswith(".actions.githubusercontent.com")
            and (actual.scheme, actual.netloc, actual.path) == (expected.scheme, expected.netloc, expected.path)
            and not actual.fragment and not actual.username and not actual.password, "credential OIDC source is not this job's endpoint")
    # Retain blank fields so they cannot hide duplicate or extra parameters.
    query = parse_qsl(actual.query, keep_blank_values=True)
    params = dict(query)
    # The pinned auth action requests a GitHub OIDC JWT for this HTTPS audience.
    # Its external-account credential above separately uses // for Google STS.
    expected_params = dict(parse_qsl(expected.query, keep_blank_values=True))
    expected_params["audience"] = f"https://iam.googleapis.com/{packet['identity']['provider']}"
    require(params == expected_params and len(params) == len(query)
            and source["format"] == {"type": "json", "subject_token_field_name": "value"}
            and bool(env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN"))
            and source["headers"] == {"Authorization": "Bearer " + env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]},
            "credential OIDC claims are not bound to this job")



def github_credential_bytes(path, limit=1048576):
    """Tighten the pinned action's observed 0640 before reading the same inode.

    The shared private_bytes policy remains strict and unchanged. This exception
    can only remove the action's group-read bit from its owned regular output;
    it never consumes a group-readable file or follows/adopts another target.
    """
    require(path.name.startswith("gha-creds-") and path.suffix == ".json", "GitHub-generated keyless credentials required")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and info.st_nlink == 1
                and stat.S_IMODE(info.st_mode) in {0o600, 0o640} and info.st_size <= limit,
                "owned single-link action credential required")
        if stat.S_IMODE(info.st_mode) == 0o640:
            os.fchmod(handle.fileno(), 0o600)
        private = os.fstat(handle.fileno())
        require(private.st_mode & 0o077 == 0 and stat.S_IMODE(private.st_mode) == 0o600
                and private.st_uid == os.geteuid() and private.st_nlink == 1,
                "credential permissions were not tightened")
        raw = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
        require(len(raw) <= limit and after.st_size == info.st_size and after.st_mtime_ns == info.st_mtime_ns
                and stat.S_IMODE(after.st_mode) == 0o600 and after.st_nlink == 1,
                "credential changed during private consumption")
    return raw


class Google:
    def __init__(self, packet_path: Path, plane: str, *, cleanup=False):
        self.path, self.plane = packet_path, plane
        if plane == "runtime-build":
            publication.publication_budget()
        if cleanup:
            require(plane == "data", "cleanup belongs only to data")
            self.packet = cleanup_packet(packet_path, dict(os.environ))
        else:
            with stage("google.admission"):
                self.packet = admit(packet_path, plane)
        with stage("google.credentials-file"):
            path = Path(os.environ.get("GOOGLE_GHA_CREDS_PATH", ""))
            require(path.name.startswith("gha-creds-") and path.suffix == ".json", "GitHub-generated keyless credentials required")
            require(all(os.environ.get(key, str(path)) == str(path) for key in
                        ("GOOGLE_APPLICATION_CREDENTIALS", "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE")),
                    "job credential paths disagree")
            credential = strict_json(github_credential_bytes(path))
        with stage("google.credentials-validation"):
            validate_credentials(credential, self.packet, dict(os.environ))
        with stage("google.credentials-load"):
            from google.auth import load_credentials_from_dict
            from google.auth.transport.requests import AuthorizedSession
            with publication.total_request(publication.publication_budget(self.packet, 30)) if plane == "runtime-build" else nullcontext():
                self.credentials, _ = load_credentials_from_dict(credential, scopes=["https://www.googleapis.com/auth/cloud-platform"])
        with stage("google.session"):
            from requests.adapters import HTTPAdapter
            # A 401 after a native insert is an unknown outcome, not permission
            # to refresh credentials and silently submit the insert again.
            self.session = AuthorizedSession(self.credentials, max_refresh_attempts=0)
            self.session.mount("https://", HTTPAdapter(max_retries=0))
            self.session.mount("http://", HTTPAdapter(max_retries=0))
        if plane == "data-initialization":
            # Actual project identity is bound to the signed data recovery proof.
            # This identity has no project/IAM API permission.
            return
        with stage("google.project-request"):
            project = self.request("project", "GET", f"projects/{PROJECT}")
        with stage("google.project-identity"):
            require(project.get("name") == f"projects/{self.packet['identity']['project_number']}"
                    and project.get("projectId") == PROJECT and project.get("state") == "ACTIVE", "observed project identity mismatch")

    def request(self, api: str, method: str, resource: str, *, body=None, params=None, missing=False):
        require(api in ORIGINS and method in {"GET", "POST", "PATCH", "DELETE", "PUT"}, "unsupported Google request")
        require(method != "PUT" or self.plane == "data-initialization", "PUT is reserved for fixed initializer role replacement")
        if self.plane == "data-initialization":
            from release_initialize import validate_request
            validate_request(api, method, resource, body, params)
        aliases = {PROJECT, self.packet["identity"]["project_number"]}
        require(any(resource.startswith(f"projects/{value}/") or resource == f"projects/{value}" for value in aliases), "foreign Google resource")
        require(not any(value in resource for value in ("?", "#", "..", "%", "\\")), "invalid Google resource")
        recovery_deadline = None
        if method != "GET":
            self.packet = admit(self.path, self.plane)
            if api == "sql" and method == "POST":
                from release_clone import authorize_effect
                recovery_deadline = authorize_effect(self, resource)
            if self.plane == "data-initialization":
                require(time.time() + 60 < getattr(self, "initialization_deadline", 0),
                        "initializer deadline reached during admission; no new effects")
        timeout = 30
        read_deadline = getattr(self, "sql_read_deadline", None)
        if method == "GET" and api == "sql" and read_deadline is not None:
            timeout = min(timeout, read_deadline - time.time())
            require(timeout > 0, "native SQL read has no remaining time")
        timing = {}
        if method != "GET":
            remaining = min(self.packet["expires_at_unix"], recovery_deadline or self.packet["expires_at_unix"]) - time.time()
            require(remaining > 0, "native mutation has no remaining authority")
            timing["max_allowed_time"] = min(30, remaining)
        if self.plane == "runtime-build":
            seconds = publication.publication_budget(self.packet, 30)
            with publication.total_request(seconds):
                response = None
                try:
                    response = self.session.request(method, ORIGINS[api] + resource, json=body, params=params,
                        timeout=seconds, max_allowed_time=seconds, allow_redirects=False)
                    if missing and response.status_code == 404:
                        return None
                    if not 200 <= response.status_code < 300:
                        raise HTTPFailure(response.status_code)
                    return response.json()
                finally:
                    if response is not None:
                        response.close()
        with request_deadline(timing["max_allowed_time"]) if recovery_deadline else nullcontext():
            response = self.session.request(method, ORIGINS[api] + resource, json=body, params=params, timeout=timeout, **timing,
                                            allow_redirects=False)
            if missing and response.status_code == 404:
                return None
            if not 200 <= response.status_code < 300:
                raise HTTPFailure(response.status_code)
            return response.json()

    def claim_restore(self, payload, directory):
        """One fixed-key, held conditional insert. No get, retry or adoption API."""
        from release_clone import (ACTOR, URL, PARAMS, RESPONSE_LIMIT, canonical, multipart, retain, sha)
        require(self.plane == "data" and directory == self.path.parent
                and os.environ.get("RELEASE_SERVICE_ACCOUNT") == ACTOR, "only ordinary recovery can claim")
        require(admit(self.path, "data") == self.packet, "claim admission changed")
        body, content_type = multipart(payload)
        retain(directory / "clone-allowance-request.body", body)
        retain(directory / "clone-allowance-request.json", canonical({"method": "POST", "url": URL,
            "params": PARAMS, "content_type": content_type, "body_sha256": sha(body)}))
        remaining = min(self.packet["expires_at_unix"],
                        strict_json(payload)["recovery_expires_at_unix"]) - time.time()
        require(remaining > 1800, "insufficient original claim authority")
        response = None
        raw = bytearray()
        complete = False
        try:
            with request_deadline(min(30, remaining)):
                response = self.session.request("POST", URL, params=dict(PARAMS), data=body,
                    headers={"Content-Type": content_type, "Accept-Encoding": "identity"},
                    timeout=min(30, remaining), max_allowed_time=min(30, remaining),
                    stream=True, allow_redirects=False)
                for chunk in response.iter_content(chunk_size=1024):
                    raw.extend(chunk[:RESPONSE_LIMIT + 1 - len(raw)])
                    require(len(raw) <= RESPONSE_LIMIT, "claim response exceeds bound")
                    require(time.time() < self.packet["expires_at_unix"], "claim response deadline reached")
                require(not response.headers.get("Content-Encoding")
                        or response.headers["Content-Encoding"] == "identity", "unexpected claim response encoding")
                length = response.headers.get("Content-Length")
                require(length is None or length == str(len(raw)), "truncated claim response")
                complete = True
        finally:
            if response is not None:
                response.close()
                retain(directory / "clone-allowance-response.body", bytes(raw))
                retain(directory / "clone-allowance-response.json", canonical({"status": response.status_code,
                    "complete": complete, "bytes": len(raw), "sha256": sha(bytes(raw))}))
        require(complete, "incomplete claim response")
        if response.status_code != 200:
            raise HTTPFailure(response.status_code)
        require(time.time() < strict_json(payload)["recovery_expires_at_unix"], "claim response arrived too late")
        return strict_json(bytes(raw))

    def wait(self, api: str, operation: dict, *, maximum_seconds=600):
        deadline = min(time.time() + maximum_seconds, self.packet["expires_at_unix"])
        name = operation.get("name", "")
        require(isinstance(name, str) and re.fullmatch(
            rf"projects/(?:{PROJECT}|{self.packet['identity']['project_number']})/locations/us-east4/operations/[A-Za-z0-9_-]+", name), "untrusted operation resource")
        while not operation.get("done"):
            require(time.time() + 5 < deadline, "cloud operation deadline reached; reconcile before retry")
            time.sleep(5)
            operation = self.request(api, "GET", name)
        require("error" not in operation and isinstance(operation.get("response"), dict), "cloud operation failed")
        return operation["response"]

    def cleanup_initializer(self, instance, action):
        from release_initialize import user_request
        require(self.plane == "data-initialization" and action in {"revoke", "delete"}, "only owned initializer privilege disposal")
        validate_context({**dict(os.environ), "RELEASE_AUTHORIZED_SHA": self.packet["source_sha"]}, self.plane, self.packet["source_sha"])
        method, resource, args = user_request(instance, action)
        # Caller must retain this exact principal's native creation proof. This
        # expiry exception cannot create a user or grant any privilege.
        response = self.session.request(method, ORIGINS["sql"] + resource, json=args.get("body"),
                                        params=args.get("params"), timeout=30, allow_redirects=False)
        require(200 <= response.status_code < 300, "initializer privilege disposal rejected; immediate reconciliation required")
        return response.json()

    def dispose_initializer(self, instance, action):
        from release_initialize import user_request
        require(self.plane == "data" and action in {"revoke", "delete"}, "ordinary disposal cannot create or grant roles")
        cleanup_packet(self.path, dict(os.environ))
        method, resource, args = user_request(instance, action)
        remaining = getattr(self, "sql_read_deadline", 0) - time.time()
        require(remaining > 0, "ordinary disposal deadline reached")
        response = self.session.request(method, ORIGINS["sql"] + resource, json=args.get("body"),
            params=args.get("params"), timeout=min(30, remaining), allow_redirects=False)
        require(200 <= response.status_code < 300, "ordinary privilege disposal rejected; reconcile without replay")
        return response.json()

    def registry_login(self):
        from google.auth.transport.requests import Request
        require(self.plane in {"runtime-build", "runtime"}, "only runtime release planes log into the registry")
        if self.plane == "runtime":
            # Preparation/activation use the separate admitted runtime identity.
            # Refresh and login share one window inside the original packet.
            require(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK, [])
                    and signal.SIGALRM not in signal.sigpending(), "runtime cannot use a blocked or pending alarm")
            expires = self.packet["expires_at_unix"]
            end = time.monotonic() + min(30, expires - time.time())
            def remaining():
                seconds = min(expires - time.time(), end - time.monotonic())
                require(seconds > 0, "original runtime registry login deadline reached")
                return seconds
            from google.auth.exceptions import GoogleAuthError
            try:
                # Native SDK work can defer Python's alarm. Hard-exit only while
                # no Docker child exists; disarm before the timeout-owned login.
                with publication.total_request(remaining()):
                    self.credentials.refresh(Request())
            except (GoogleAuthError, publication.RequestExpired):
                raise ValueError("runtime registry credential refresh failed") from None
            with request_deadline(remaining()):
                result = subprocess.run(["docker", "login", "-u", "oauth2accesstoken", "--password-stdin",
                                         "https://us-east4-docker.pkg.dev"], input=self.credentials.token.encode(),
                                        capture_output=True, timeout=remaining())
                require(result.returncode == 0, "registry authentication failed")
                remaining()
            return
        with publication.total_request(publication.publication_budget(self.packet, 30)):
            self.credentials.refresh(Request())
            publication.publication_budget(self.packet)
            result = subprocess.run(["docker", "login", "-u", "oauth2accesstoken", "--password-stdin",
                                     "https://us-east4-docker.pkg.dev"], input=self.credentials.token.encode(),
                                    capture_output=True, timeout=publication.publication_budget(self.packet, 30))
            require(result.returncode == 0, "registry authentication failed")

    def run_iam_policy(self, resource):
        require(resource == f"projects/{PROJECT}/locations/us-east4/services/specimen-sam", "only the named SAM invocation policy is used")
        return self.request("run", "GET", resource + ":getIamPolicy", params={"options.requestedPolicyVersion": 3})

    def cleanup_clone(self):
        # Caller first verifies immutable createTime and this run's owned receipt.
        # This exact disposal cannot be blocked by a newer main or expired paid
        # authority; no other expired-authority mutation is provided.
        cleanup_packet(self.path, dict(os.environ))
        url = ORIGINS["sql"] + f"projects/{PROJECT}/instances/specimen-digitization-restore-20260908-r1"
        response = self.session.delete(url, timeout=30, allow_redirects=False)
        require(200 <= response.status_code < 300, "owned clone cleanup rejected; reconcile immediately")
        return response.json()
