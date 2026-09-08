"""Short-lived WIF transport with fixed Google API origins and mutation guards."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import parse_qsl, urlsplit

from release_admission import admit, exact_keys, private_bytes, read_bound_plan, read_packet, require, strict_json
from release_context import PROJECT, validate_context

ORIGINS = {"identity": "https://identitytoolkit.googleapis.com/v1/","run": "https://run.googleapis.com/v2/", "registry": "https://artifactregistry.googleapis.com/v1/",
           "project": "https://cloudresourcemanager.googleapis.com/v3/",
           "sql": "https://sqladmin.googleapis.com/sql/v1beta4/",
           "data": "https://firebasedataconnect.googleapis.com/v1/",
           "rules": "https://firebaserules.googleapis.com/v1/"}


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
        require(plan.get("version") == "data-apply/v1", "cleanup belongs only to native data apply")
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
    params = dict(parse_qsl(actual.query))
    expected_params = dict(parse_qsl(expected.query)); expected_params["audience"] = packet["identity"]["provider"]
    require(params == expected_params and len(params) == len(parse_qsl(actual.query))
            and source["format"] == {"type": "json", "subject_token_field_name": "value"}
            and bool(env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN"))
            and source["headers"] == {"Authorization": "Bearer " + env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]},
            "credential OIDC claims are not bound to this job")


class Google:
    def __init__(self, packet_path: Path, plane: str, *, cleanup=False):
        self.path, self.plane = packet_path, plane
        if cleanup:
            require(plane == "data", "cleanup belongs only to data")
            self.packet = cleanup_packet(packet_path, dict(os.environ))
        else:
            self.packet = admit(packet_path, plane)
        path = Path(os.environ.get("GOOGLE_GHA_CREDS_PATH", ""))
        require(path.name.startswith("gha-creds-") and path.suffix == ".json", "GitHub-generated keyless credentials required")
        credential = strict_json(private_bytes(path))
        validate_credentials(credential, self.packet, dict(os.environ))
        from google.auth import load_credentials_from_dict
        from google.auth.transport.requests import AuthorizedSession
        self.credentials, _ = load_credentials_from_dict(credential, scopes=["https://www.googleapis.com/auth/cloud-platform"])
        self.session = AuthorizedSession(self.credentials)
        project = self.request("project", "GET", f"projects/{PROJECT}")
        require(project.get("name") == f"projects/{self.packet['identity']['project_number']}"
                and project.get("projectId") == PROJECT and project.get("state") == "ACTIVE", "observed project identity mismatch")

    def request(self, api: str, method: str, resource: str, *, body=None, params=None, missing=False):
        require(api in ORIGINS and method in {"GET", "POST", "PATCH", "DELETE"}, "unsupported Google request")
        aliases = {PROJECT, self.packet["identity"]["project_number"]}
        require(any(resource.startswith(f"projects/{value}/") or resource == f"projects/{value}" for value in aliases), "foreign Google resource")
        require(not any(value in resource for value in ("?", "#", "..", "%", "\\")), "invalid Google resource")
        if method != "GET":
            self.packet = admit(self.path, self.plane)
        response = self.session.request(method, ORIGINS[api] + resource, json=body, params=params, timeout=30,
                                        allow_redirects=False)
        if missing and response.status_code == 404:
            return None
        require(200 <= response.status_code < 300, f"{api} operation rejected with HTTP {response.status_code}; no automatic retry")
        return response.json()

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

    def registry_login(self):
        from google.auth.transport.requests import Request
        self.credentials.refresh(Request())
        result = subprocess.run(["docker", "login", "-u", "oauth2accesstoken", "--password-stdin",
                                 "https://us-east4-docker.pkg.dev"], input=self.credentials.token.encode(),
                                capture_output=True, timeout=30)
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
