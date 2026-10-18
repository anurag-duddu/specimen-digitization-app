#!/usr/bin/env python3
"""Enable Google alongside existing email sign-in from Data release only.

Existing Google clients are retained. Only a missing Google provider uses the
pinned Firebase CLI's provisioning API; an existing disabled provider receives
an enabled-only patch. No users, email settings or domains are written here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import parse_qsl

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "specimen-digitization"
NUMBER = "716045864126"
REPOSITORY = "anurag-duddu/specimen-digitization-app"
WEB_APP = "1:716045864126:web:a193fa80c7a98bcac8e2ef"
AUTH_ROOT = f"https://identitytoolkit.googleapis.com/admin/v2/projects/{PROJECT}"
GOOGLE_URL = AUTH_ROOT + "/defaultSupportedIdpConfigs/google.com"
CONFIG_URL = AUTH_ROOT + "/config"
APPS_URL = f"https://firebase.googleapis.com/v1beta1/projects/{PROJECT}/webApps"
GOOGLE_FIELDS = "name,enabled,clientId"
PRESERVED_FIELDS = "authorizedDomains,signIn(email(enabled,passwordRequired))"
DOMAINS = {f"{PROJECT}.firebaseapp.com", f"{PROJECT}.web.app"}
CLI_VERSION = "15.8.0"
AUTH_CONFIG = {"auth": {"providers": {"googleSignIn": {
    "oAuthBrandDisplayName": "Specimen Digitization",
    "supportEmail": "anurag@infinative.com",
}}}}
SETUP_HINT = "if permissions are missing, the owner runs bash scripts/ops/owner_setup.sh --auth-only once"

# Firebase CLI 15.8.0 apiv2/logger and Auth provisioning formats. These map
# observations to fixed labels; neither URLs nor arbitrary server text escape.
DIAGNOSTIC_LIMIT = 1024 * 1024
DIAGNOSTIC_LINE_LIMIT = 16384
_PROJECT_PATH = rf"(?:{PROJECT}|{NUMBER})"
_CLI_STAGES = (
    ("POST", rf"https://cloudresourcemanager\.googleapis\.com/v1/projects/{_PROJECT_PATH}:testIamPermissions", "permission_check"),
    ("GET", rf"https://cloudresourcemanager\.googleapis\.com/v1/projects/{_PROJECT_PATH}", "project_read"),
    ("GET", rf"https://firebase\.googleapis\.com/v1beta1/projects/{_PROJECT_PATH}", "firebase_project_read"),
    ("GET", rf"https://firebase\.googleapis\.com/v1beta1/projects/{_PROJECT_PATH}/webApps", "web_app_list"),
    ("POST", r"https://firebase\.googleapis\.com/v1alpha/firebase:provisionFirebaseApp", "provider_provision"),
    ("GET", rf"https://firebase\.googleapis\.com/v1beta1/(?:projects/{_PROJECT_PATH}/)?operations/[A-Za-z0-9_-]+", "provider_operation"),
)
_DEBUG_PREFIX = r"(?:\[debug\] )?(?:\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\] )?"
_RESPONSE_LINE = re.compile(_DEBUG_PREFIX + r"<<< \[apiv2\]\[(status|body)\] (GET|POST) (https://\S+) (.+)")
_CLI_HTTP_ERROR = re.compile(
    r"(?:\[error\] )?" + _DEBUG_PREFIX + r"(?:Error: (?:Failed to provision Firebase app: )?)?Request to "
    r"(https://\S+) had HTTP Error: ([45][0-9]{2}),.*"
)
_API_STATUSES = frozenset({
    "CANCELLED", "UNKNOWN", "INVALID_ARGUMENT", "DEADLINE_EXCEEDED", "NOT_FOUND",
    "ALREADY_EXISTS", "PERMISSION_DENIED", "RESOURCE_EXHAUSTED", "FAILED_PRECONDITION",
    "ABORTED", "OUT_OF_RANGE", "UNIMPLEMENTED", "INTERNAL", "UNAVAILABLE", "DATA_LOSS", "UNAUTHENTICATED",
})
_API_REASONS = frozenset({
    # Public google/api/error_reason.proto names, plus IAM's ErrorInfo reason.
    "IAM_PERMISSION_DENIED", "SERVICE_DISABLED", "BILLING_DISABLED", "CONSUMER_INVALID",
    "ACCESS_TOKEN_SCOPE_INSUFFICIENT", "RATE_LIMIT_EXCEEDED", "SECURITY_POLICY_VIOLATED",
    "API_KEY_INVALID", "API_KEY_SERVICE_BLOCKED", "API_KEY_HTTP_REFERRER_BLOCKED",
    "API_KEY_IP_ADDRESS_BLOCKED", "API_KEY_ANDROID_APP_BLOCKED", "API_KEY_IOS_APP_BLOCKED",
    "CONSUMER_SUSPENDED", "ACCESS_TOKEN_EXPIRED", "ACCESS_TOKEN_TYPE_UNSUPPORTED",
    "ACCOUNT_STATE_INVALID", "CREDENTIALS_MISSING", "USER_PROJECT_DENIED", "USER_BLOCKED_BY_ADMIN",
    "RESOURCE_USAGE_RESTRICTION_VIOLATED", "ORG_RESTRICTION_VIOLATION", "SERVICE_NOT_VISIBLE",
    "GCP_SUSPENDED", "CREDENTIAL_TYPE_UNSUPPORTED", "ACCOUNT_TYPE_UNSUPPORTED",
    "ENDPOINT_USAGE_RESTRICTION_VIOLATED",
})
_API_PERMISSIONS = frozenset({
    # Diagnostic names only; this list grants no permission or authority.
    "firebase.clients.get", "firebase.clients.list", "firebase.projects.get",
    "firebase.projects.update", "firebaseauth.configs.get", "firebaseauth.configs.update",
    "firebase.clients.create", "resourcemanager.projects.get",
    "clientauthconfig.brands.create", "clientauthconfig.brands.get", "clientauthconfig.brands.list",
    "clientauthconfig.brands.update", "clientauthconfig.clients.create", "clientauthconfig.clients.get",
    "clientauthconfig.clients.list", "clientauthconfig.clients.update",
    "serviceusage.services.get", "serviceusage.services.enable", "serviceusage.services.use",
})


class Failure(RuntimeError):
    """A bounded diagnostic that contains no API response or credential."""


def require_release(env, checked_out):
    expected = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": f"{REPOSITORY}/.github/workflows/data-release.yml@refs/heads/main",
        "AUTH_RELEASE_ENVIRONMENT": "data-production",
    }
    if any(env.get(key) != value for key, value in expected.items()):
        raise Failure("Auth provisioning runs only in the main Data release environment")
    if env.get("GITHUB_EVENT_NAME") not in {"push", "workflow_dispatch"}:
        raise Failure("Auth provisioning requires a main push or manual Data release")
    sha = env.get("GITHUB_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or sha != checked_out:
        raise Failure("Auth provisioning requires the checked-out main commit")
    credentials = env.get("GOOGLE_GHA_CREDS_PATH", "")
    if not credentials or not Path(credentials).is_file():
        raise Failure("Auth provisioning requires the workflow's keyless credentials")
    if env.get("FIREBASE_TOKEN") or env.get("FIREBASE_AUTH_EMULATOR_HOST"):
        raise Failure("Auth provisioning refuses token overrides and emulators")


class Api:
    def __init__(self, session):
        self.session = session

    def call(self, method, url, *, fields, body=None, update_mask=None, missing=False):
        params = {"fields": fields}
        if update_mask:
            params["updateMask"] = update_mask
        # Reads may retry transient transport/server failures. A write is sent once.
        attempts = 3 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                response = self.session.request(method, url, params=params, json=body, timeout=(10, 30))
            except Exception:
                if attempt + 1 == attempts:
                    raise Failure(f"Auth {method} did not complete; rerun Data release") from None
            else:
                if missing and response.status_code == 404:
                    return None
                if response.status_code in (401, 403):
                    raise Failure(f"Auth {method} refused HTTP {response.status_code}; {SETUP_HINT}")
                if response.status_code < 500 and response.status_code != 429:
                    break
                if attempt + 1 == attempts:
                    break
            time.sleep(attempt + 1)
        if not 200 <= response.status_code < 300:
            raise Failure(f"Auth {method} refused HTTP {response.status_code}; no response content logged")
        try:
            data = response.json()
        except ValueError:
            raise Failure("Auth API returned invalid JSON") from None
        if not isinstance(data, dict):
            raise Failure("Auth API returned an invalid object")
        return data


def preserved_settings(config):
    try:
        email = config["signIn"]["email"]
        domains = config["authorizedDomains"]
    except (KeyError, TypeError):
        raise Failure("Existing email/domain configuration is unavailable; nothing changed") from None
    if not isinstance(email, dict) or email.get("enabled") is not True or email.get("passwordRequired", False) is not False:
        raise Failure("Existing passwordless email must be enabled; nothing changed")
    if not isinstance(domains, list) or any(not isinstance(domain, str) for domain in domains):
        raise Failure("Existing authorized domains are invalid; nothing changed")
    if not DOMAINS.issubset(domains):
        raise Failure("Required production domains are missing; nothing changed")
    return {"email_enabled": True, "password_required": False, "domains": sorted(domains)}


def google_ready(provider):
    if not isinstance(provider, dict):
        return False
    names = {f"projects/{project}/defaultSupportedIdpConfigs/google.com" for project in (PROJECT, NUMBER)}
    client = provider.get("clientId")
    return (provider.get("name") in names and provider.get("enabled") is True
            and isinstance(client, str) and bool(re.fullmatch(r"[A-Za-z0-9-]+\.apps\.googleusercontent\.com", client)))


def _cli_stage(method, url, *, operation_url=None, operation_seen=False):
    if method == "GET" and operation_url is not None and url == operation_url:
        return "provider_operation"
    base, separator, query = url.partition("?")
    stage = next((stage for verb, pattern, stage in _CLI_STAGES
                  if method == verb and re.fullmatch(pattern, base)), None)
    if stage == "provider_operation" and operation_seen:
        return None
    if not separator:
        return stage
    # apiv2 response records omit query parameters, but responseToError uses
    # fetchURL. listFirebaseApps supplies pageSize/pageToken; operation polling
    # supplies no query. Recognize only that pinned pagination shape, omit values.
    if stage != "web_app_list" or "#" in query:
        return None
    try:
        fields = parse_qsl(query, keep_blank_values=True, strict_parsing=True, max_num_fields=2)
    except ValueError:
        return None
    if (not fields or len(dict(fields)) != len(fields)
            or any(key not in {"pageSize", "pageToken"} or not value for key, value in fields)
            or any(key == "pageSize" and not re.fullmatch(r"[1-9][0-9]{0,3}", value) for key, value in fields)):
        return None
    return stage


def _cli_operation_url(body):
    """Correlate a safe server-returned resource name; never emit it."""
    try:
        data = json.loads(body)
    except (ValueError, RecursionError):
        return None
    name = data.get("name") if isinstance(data, dict) and "error" not in data else None
    if (not isinstance(name, str) or not 1 <= len(name) <= 2048
            or not re.fullmatch(r"[A-Za-z0-9_./:~-]+", name)):
        return None
    parts = name.removeprefix("/").split("/")
    if (any(part in {"", ".", ".."} for part in parts) or ":" in parts[0]
            or "operations" not in parts[:-1]):
        return None
    # CLI 15.8.0 provision.js passes name unchanged to OperationPoller.
    # apiv2.doRequest adds a leading slash, then requestURL prefixes this host
    # and version. No decoding, URL joining or untrusted origin is involved.
    return "https://firebase.googleapis.com/v1beta1" + (name if name.startswith("/") else "/" + name)


def _structured_cli_error(body):
    """Read only enumerated fields of an HTTP or completed-operation error."""
    try:
        data = json.loads(body)
    except (ValueError, RecursionError):
        return {}
    error = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict):
        return {}
    result = {}
    code = error.get("code")
    if type(code) is int and (1 <= code <= 16 or 400 <= code <= 599):
        result["api_code"] = code
    elif "code" in error:
        result["api_code"] = "unrecognized"
    status = error.get("status")
    if isinstance(status, str) and status in _API_STATUSES:
        result["api_status"] = status
    elif "status" in error:
        result["api_status"] = "unrecognized"
    details = error.get("details")
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, dict) or detail.get("@type") != "type.googleapis.com/google.rpc.ErrorInfo":
            continue
        reason = detail.get("reason")
        if isinstance(reason, str) and reason in _API_REASONS:
            result["reason"] = reason
        elif "reason" in detail:
            result["reason"] = "unrecognized"
        metadata = detail.get("metadata")
        permission = metadata.get("permission") if isinstance(metadata, dict) else None
        if isinstance(permission, str) and permission in _API_PERMISSIONS:
            result["permission"] = permission
        elif isinstance(metadata, dict) and "permission" in metadata:
            result["permission"] = "unrecognized"
    return result


def _cli_observation(text):
    """Last recognized response, not an assertion that it caused CLI failure."""
    if not isinstance(text, str) or len(text) > DIAGNOSTIC_LIMIT:
        return {}
    result, response_key = {}, None
    operation_url, operation_seen = None, False
    for line in text.splitlines():
        if len(line) > DIAGNOSTIC_LINE_LIMIT:
            continue
        match = _RESPONSE_LINE.fullmatch(line)
        if match:
            kind, method, url, payload = match.groups()
            stage = _cli_stage(method, url, operation_url=operation_url, operation_seen=operation_seen)
            if kind == "status":
                # An intervening unknown response cannot donate its body to a
                # previous recognized request, even when a URL is repeated.
                response_key = None
                if stage == "provider_provision":
                    operation_url = None
                    operation_seen = bool(re.fullmatch(r"2[0-9]{2}", payload))
                if stage and re.fullmatch(r"[1-5][0-9]{2}", payload):
                    result = {"stage": stage, "http": int(payload)}
                    response_key = (method, url)
            elif stage and response_key == (method, url):
                result.update(_structured_cli_error(payload))
                if stage == "provider_provision" and 200 <= result["http"] < 300:
                    operation_url = _cli_operation_url(payload)
            continue
        match = _CLI_HTTP_ERROR.fullmatch(line)
        if match:
            url, status = match.groups()
            # responseToError omits the method; infer it only for an endpoint
            # with a single known verb in this pinned Auth provisioning path.
            stages = {_cli_stage(verb, url, operation_url=operation_url, operation_seen=operation_seen)
                      for verb in ("GET", "POST")} - {None}
            if len(stages) == 1:
                stage = stages.pop()
                if stage == "provider_provision":
                    operation_url, operation_seen = None, False
                if result.get("stage") != stage or result.get("http") != int(status):
                    result = {"stage": stage, "http": int(status)}
                response_key = None
    return result


def _private_cli_log(folder):
    """Refuse symlinks, special files, oversized logs and undecodable content."""
    try:
        fd = os.open(Path(folder) / "firebase-debug.log", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > DIAGNOSTIC_LIMIT:
                return ""
            data = stream.read(DIAGNOSTIC_LIMIT + 1)
        return data.decode("utf-8") if len(data) <= DIAGNOSTIC_LIMIT else ""
    except (OSError, UnicodeError):
        return ""


def cli_failure_diagnostic(done, folder):
    observations = [_cli_observation(source) for source in (
        _private_cli_log(folder), getattr(done, "stderr", ""), getattr(done, "stdout", ""),
    )]
    # Prefer a structured API error or HTTP refusal over an earlier successful
    # read. File output wins ties. Every emitted value is fixed or bounded.
    observation = max(observations, key=lambda item: (
        "api_code" in item or "api_status" in item,
        item.get("http", 0) >= 400,
        bool(item),
    ))
    if not observation:
        return "CLI diagnostic unavailable"
    return "CLI response diagnostic: " + " ".join(f"{key}={value}" for key, value in observation.items())


def run_cli(cli, config):
    if config != AUTH_CONFIG:
        raise Failure("Auth config must contain only the approved Google provider")
    # Run in an empty temporary directory. CLI debug output stays there and is
    # removed; raw provider/credential responses never enter release logs.
    with tempfile.TemporaryDirectory(prefix="specimen-auth-") as folder:
        path = Path(folder) / "firebase.auth.json"
        path.write_text(json.dumps(config))
        try:
            version = subprocess.run([str(cli), "--version"], cwd=folder, capture_output=True,
                                     text=True, timeout=30, check=False)
            if version.returncode or version.stdout.strip() != CLI_VERSION:
                raise Failure("Auth provisioning requires Firebase CLI 15.8.0")
            done = subprocess.run([str(cli), "deploy", "--only", "auth", "--project", PROJECT,
                                   "--config", str(path), "--non-interactive"], cwd=folder,
                                  capture_output=True, text=True, timeout=300, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            diagnostic = cli_failure_diagnostic(error, folder)
            raise Failure("Pinned Auth CLI did not complete; rerun Data release after checking provider state; "
                          f"{diagnostic}; raw output omitted") from None
        if done.returncode:
            diagnostic = cli_failure_diagnostic(done, folder)
            raise Failure(f"Pinned Auth CLI exited {done.returncode}; {diagnostic}; {SETUP_HINT}; raw output omitted")


def provision(api, cli, config):
    if config != AUTH_CONFIG:
        raise Failure("Auth config must contain only the approved Google provider")
    before = preserved_settings(api.call("GET", CONFIG_URL, fields=PRESERVED_FIELDS))
    provider = api.call("GET", GOOGLE_URL, fields=GOOGLE_FIELDS, missing=True)
    if google_ready(provider):
        print("Google provider already enabled; existing client retained")
        return
    if provider is None:
        apps = api.call("GET", APPS_URL, fields="apps(appId,state),nextPageToken")
        # CLI 15.8.0 chooses the first/default web app. Refuse ambiguity or a
        # missing app rather than provisioning a different application.
        if (apps.get("nextPageToken") or apps.get("apps") != [{"appId": WEB_APP, "state": "ACTIVE"}]):
            raise Failure("Expected the single existing production web app; nothing changed")
        run_cli(cli, config)
    else:
        # Never replace an existing OAuth client or its secret/branding.
        enabled_view = {**provider, "enabled": True}
        if not google_ready(enabled_view):
            raise Failure("Existing Google provider has invalid identity/client configuration; nothing changed")
        api.call("PATCH", GOOGLE_URL, fields=GOOGLE_FIELDS, body={"enabled": True}, update_mask="enabled")
    try:
        after = preserved_settings(api.call("GET", CONFIG_URL, fields=PRESERVED_FIELDS))
    except Failure:
        raise Failure("Email/domain settings could not be verified after provisioning; stop and inspect") from None
    if before != after:
        raise Failure("Email/domain settings changed during provisioning; stop and inspect, no automatic overwrite")
    if not google_ready(api.call("GET", GOOGLE_URL, fields=GOOGLE_FIELDS)):
        raise Failure("Google provider is not enabled with a valid client; keep the web flag off")
    print("Google provider enabled and verified; existing email and domains preserved")


def main():
    try:
        checked_out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                                     text=True, check=True).stdout.strip()
        require_release(os.environ, checked_out)
        cli = Path(os.environ.get("AUTH_RELEASE_CLI", ""))
        if not cli.is_file():
            raise Failure("Pinned Auth CLI is missing")
        config = json.loads((ROOT / "firebase.auth.json").read_text())
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        provision(Api(AuthorizedSession(credentials)), cli, config)
    except Exception as error:
        message = str(error) if isinstance(error, Failure) else f"{type(error).__name__}; no response content logged"
        print(f"Auth provisioning failed: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
