#!/usr/bin/env python3
"""Sanitized, noninteractive preflight for local Google Cloud credentials.

This is an owner-side diagnostic for ordinary local development and read-only
inventory. It never opens a browser, runs a login command, changes a gcloud
configuration, prints a credential, or deploys anything. Production workflows
use GitHub OIDC and Workload Identity Federation instead.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import Mapping


PROJECT = "specimen-digitization"
SCHEMA_VERSION = 1
PROBE_TIMEOUT_SECONDS = 20
PRIVATE_TOKEN_FORMAT = "--format=value[private](token)"

# These are intentionally treated as a different local profile. A worker must
# not silently switch from the owner's shared user ADC to a key, a short-lived
# CI credential, or another Cloud SDK configuration.
CREDENTIAL_OVERRIDE_KEYS = (
    "GOOGLE_APPLICATION_CREDENTIALS",
    "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE",
    "CLOUDSDK_AUTH_ACCESS_TOKEN",
    "CLOUDSDK_AUTH_ACCESS_TOKEN_FILE",
)
IDENTITY_OVERRIDE_KEYS = (
    "CLOUDSDK_CORE_ACCOUNT",
    "CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT",
)
CONFIG_OVERRIDE_KEYS = (
    "CLOUDSDK_CONFIG",
    "CLOUDSDK_ACTIVE_CONFIG_NAME",
    "CLOUDSDK_AUTH_TOKEN_HOST",
    "CLOUDSDK_AUTH_MTLS_TOKEN_HOST",
)
# Endpoint/trust overrides alter where a refresh goes or which server is
# trusted. Do not silently normalize these for just one caller.
TRANSPORT_OVERRIDE_KEYS = (
    "CLOUDSDK_AUTH_DISABLE_SSL_VALIDATION",
    "CLOUDSDK_CORE_CUSTOM_CA_CERTS_FILE",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "CLOUDSDK_AUTH_TOKEN_INTROSPECTION_ENDPOINT",
    "CLOUDSDK_CORE_UNIVERSE_DOMAIN",
)
ENDPOINT_OVERRIDE_PREFIX = "CLOUDSDK_API_ENDPOINT_OVERRIDES_"
# Environment properties precede stored SDK settings. Pin this policy in each
# diagnostic child, including ordinary profiles with default file logging.
# The runbook applies the identical policy to its subsequent inventory child.
SAFE_PROBE_SETTINGS = {
    "CLOUDSDK_AUTH_DISABLE_SSL_VALIDATION": "false",
    "CLOUDSDK_CORE_DISABLE_FILE_LOGGING": "true",
    "CLOUDSDK_CORE_MAX_LOG_DAYS": "0",
    "CLOUDSDK_CORE_LOG_HTTP": "false",
    "CLOUDSDK_CORE_LOG_HTTP_REDACT_TOKEN": "true",
    "CLOUDSDK_CORE_LOG_HTTP_SHOW_REQUEST_BODY": "false",
    "CLOUDSDK_CORE_LOG_HTTP_STREAMING_BODY": "false",
    "CLOUDSDK_CORE_USER_OUTPUT_ENABLED": "true",
    # core/format validates only bare global names. Clear it here; the token
    # projection belongs on an explicit command flag, not on this property.
    "CLOUDSDK_CORE_FORMAT": "",
    "CLOUDSDK_CORE_DRY_RUN": "0",
}
PROJECT_OVERRIDE_KEYS = (
    "GOOGLE_CLOUD_PROJECT",
    "GCLOUD_PROJECT",
    "CLOUDSDK_CORE_PROJECT",
)


def is_set(value: str | None) -> bool:
    """Return whether an environment setting is nonempty without exposing it."""
    return value is not None and value != ""


def environment_reasons(env: Mapping[str, str]) -> list[str]:
    """Return safe reason codes without reading paths, files, or values."""
    reasons: list[str] = []
    for key in CREDENTIAL_OVERRIDE_KEYS:
        if key in env:
            reasons.append(f"credential_override:{key}")
    for key in IDENTITY_OVERRIDE_KEYS:
        if key in env:
            reasons.append(f"identity_override:{key}")
    for key in CONFIG_OVERRIDE_KEYS:
        if key in env:
            reasons.append(f"cloudsdk_config_override:{key}")
    for key in TRANSPORT_OVERRIDE_KEYS:
        if key in env:
            reasons.append(f"transport_override:{key}")
    for key in sorted(env):
        if key.startswith(ENDPOINT_OVERRIDE_PREFIX):
            reasons.append(f"transport_override:{key}")
    for key in PROJECT_OVERRIDE_KEYS:
        value = env.get(key)
        if is_set(value) and value != PROJECT:
            reasons.append(f"project_override_mismatch:{key}")
    return reasons


def no_prompt_environment(env: Mapping[str, str]) -> dict[str, str]:
    """Pin safe transport/log/display policy without changing the parent shell."""
    child = dict(env)
    # Cloud SDK treats an empty override as explicit, not as a stored default.
    profile_keys = (
        CREDENTIAL_OVERRIDE_KEYS + IDENTITY_OVERRIDE_KEYS
        + CONFIG_OVERRIDE_KEYS + TRANSPORT_OVERRIDE_KEYS
    )
    for key in tuple(child):
        if (key in profile_keys or key.startswith(ENDPOINT_OVERRIDE_PREFIX)) and child[key] == "":
            child.pop(key)
    child.update(SAFE_PROBE_SETTINGS)
    child["CLOUDSDK_CORE_DISABLE_PROMPTS"] = "true"
    child["CLOUDSDK_CORE_SHOULD_PROMPT_TO_ENABLE_API"] = "false"
    return child


def probe(arguments: list[str], env: Mapping[str, str]) -> bool:
    """Check one credential store while discarding all command output."""
    try:
        completed = subprocess.run(
            arguments,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=PROBE_TIMEOUT_SECONDS,
            env=no_prompt_environment(env),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and bool(completed.stdout.strip())


def report(
    *,
    status: str,
    checks: Mapping[str, str],
    reasons: list[str],
    next_action: str,
) -> None:
    """Emit exactly one safe machine-readable result."""
    print(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "status": status,
                "checks": dict(checks),
                "blocking_reasons": reasons,
                "next_action": next_action,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def blocked_environment(reasons: list[str]) -> str:
    if any(reason.startswith("project_override_mismatch:") for reason in reasons):
        return "correct_project_override"
    return "clear_local_profile_overrides"


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["--help"]:
        print(f"Usage: {path_name()}  # checks local CLI and ADC for {PROJECT}")
        return 0
    if arguments:
        report(
            status="blocked",
            checks={
                "environment": "not_checked",
                "gcloud": "not_checked",
                "cli_auth": "not_checked",
                "application_default_credentials": "not_checked",
            },
            reasons=["usage_error"],
            next_action="read_usage",
        )
        return 64

    env = dict(os.environ)
    reasons = environment_reasons(env)
    if reasons:
        report(
            status="blocked",
            checks={
                "environment": "blocked",
                "gcloud": "not_run",
                "cli_auth": "not_run",
                "application_default_credentials": "not_run",
            },
            reasons=reasons,
            next_action=blocked_environment(reasons),
        )
        return 2

    if shutil.which("gcloud", path=env.get("PATH")) is None:
        report(
            status="blocked",
            checks={
                "environment": "clear",
                "gcloud": "missing",
                "cli_auth": "not_run",
                "application_default_credentials": "not_run",
            },
            reasons=["gcloud_missing"],
            next_action="install_gcloud",
        )
        return 2

    cli_ready = probe(
        ["gcloud", "auth", "print-access-token", f"--project={PROJECT}", "--quiet", PRIVATE_TOKEN_FORMAT], env
    )
    adc_ready = probe(
        [
            "gcloud",
            "auth",
            "application-default",
            "print-access-token",
            f"--project={PROJECT}",
            "--quiet",
            PRIVATE_TOKEN_FORMAT,
        ],
        env,
    )
    reasons = []
    if not cli_ready:
        reasons.append("cli_auth_unavailable")
    if not adc_ready:
        reasons.append("application_default_credentials_unavailable")
    if reasons:
        report(
            status="blocked",
            checks={
                "environment": "clear",
                "gcloud": "available",
                "cli_auth": "ready" if cli_ready else "blocked",
                "application_default_credentials": "ready" if adc_ready else "blocked",
            },
            reasons=reasons,
            next_action="owner_sign_in_required",
        )
        return 2

    report(
        status="ready",
        checks={
            "environment": "clear",
            "gcloud": "available",
            "cli_auth": "ready",
            "application_default_credentials": "ready",
        },
        reasons=[],
        next_action="none",
    )
    return 0


def path_name() -> str:
    """Keep the help text stable without leaking the caller's working path."""
    return "python3 scripts/dev/google_auth_preflight.py"


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # Diagnostics must not surface a path, account, token, or provider
        # error. The owner can rerun after reducing the environment to the
        # ordinary local profile documented with this command.
        report(
            status="blocked",
            checks={
                "environment": "unknown",
                "gcloud": "unknown",
                "cli_auth": "unknown",
                "application_default_credentials": "unknown",
            },
            reasons=["diagnostic_failure"],
            next_action="owner_diagnostic_required",
        )
        raise SystemExit(70)
