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
import subprocess
import sys
import tempfile
import time

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
        except (OSError, subprocess.TimeoutExpired):
            raise Failure("Pinned Auth CLI did not complete; rerun Data release after checking provider state") from None
        if done.returncode:
            raise Failure(f"Pinned Auth CLI exited {done.returncode}; {SETUP_HINT}; raw output omitted")


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
