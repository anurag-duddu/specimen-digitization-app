#!/usr/bin/env python3
"""Store the worker's Logfire writer token and verify its destination identity.

docs/execution/APPROVED_LOGFIRE_TRACING.md approved one new secret parent,
``projects/specimen-digitization/secrets/specimen-worker-logfire`` replicated in
``us-east4``, created only when absent and followed by one immutable version;
one bounded identity GET to ``https://logfire-us.pydantic.dev/v1/info`` that
proves the writer belongs to the approved project before any specimen metadata
is sent; and ``roles/secretmanager.secretAccessor`` for the worker runtime
identity only, conditioned on the exact version and the runtime expiration.

Each subcommand writes a private receipt and puts no credential in any output:

- ``store`` creates the parent, adds the version from a private file, reads the
  version back, compares the bytes and records the resource names.
- ``identity`` makes the single approved identity request, refuses a second
  attempt, records the project the token writes to and prints the receipt
  digest that ``runtime-activate`` binds as ``trace_identity_receipt_sha256``.
- ``grant`` and ``revoke`` add or remove the one conditional accessor binding
  by compare-and-swap on the secret's policy, with readback.
"""
from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deploy_runtime import TRACE_APPROVAL_SHA256  # noqa: E402
from owner_gcloud import Gcloud, durable_write, parse_stamp, sha256_bytes, stamp  # noqa: E402
from release_admission import private_bytes, require, strict_json  # noqa: E402
from release_context import PROJECT  # noqa: E402

SECRET_ID = "specimen-worker-logfire"
PARENT = f"projects/{PROJECT}/secrets/{SECRET_ID}"
LOCATION = "us-east4"
WORKER_IDENTITY = f"serviceAccount:specimen-worker-runtime@{PROJECT}.iam.gserviceaccount.com"
ACCESSOR_ROLE = "roles/secretmanager.secretAccessor"
GRANT_TITLE = "specimen_worker_trace_writer"
HOST = "logfire-us.pydantic.dev"
INFO_PATH = "/v1/info"
APPROVED_PROJECT_ID = "anuragduddu/specimen-digitization"
APPROVED_PROJECT_NAME = "specimen-digitization"
APPROVED_PROJECT_URL = f"https://{HOST}/{APPROVED_PROJECT_ID}"
BODY_LIMIT = 65536
IDENTITY_TIMEOUT_SECONDS = 10.0
STORE_REQUESTS = 6      # approved secret-stage ceiling: 40
GRANT_REQUESTS = 4
TOKEN = re.compile(r"[!-~]{1,4096}")
NATIVE_PARENT = re.compile(rf"projects/[0-9]+/secrets/{SECRET_ID}")
NATIVE_VERSION = re.compile(rf"projects/[0-9]+/secrets/{SECRET_ID}/versions/([1-9][0-9]*)")
TOKEN_SECRET = re.compile(rf"{PARENT}/versions/([1-9][0-9]*)")
FORBIDDEN_ENVIRONMENT = ("SSL_CERT_FILE", "SSL_CERT_DIR", "SSLKEYLOGFILE", "HTTPS_PROXY", "https_proxy",
                         "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy")
STORAGE_QUOTE = {"usd_per_version_location_month": 0.06, "horizon_days": 31, "usd_31_days": 0.06,
                 "basis": "https://cloud.google.com/secret-manager/pricing"}


def read_token(path: Path) -> bytes:
    """One printable ASCII line from an owner-only file; a trailing newline is dropped."""
    raw = private_bytes(path, limit=8192).rstrip(b"\r\n")
    require(raw and raw == raw.strip() and b"\n" not in raw and b"\r" not in raw
            and TOKEN.fullmatch(raw.decode("ascii", "replace")) is not None,
            "writer token must be one printable ASCII line")
    return raw


def decode_payload(accessed: dict) -> bytes:
    data = accessed.get("payload", {}).get("data")
    require(isinstance(data, str) and data, "secret payload missing from readback")
    standard = data.replace("-", "+").replace("_", "/")
    return base64.b64decode(standard + "=" * (-len(standard) % 4), validate=True)


def fetch_token(gcloud: Gcloud, token_secret: str) -> bytes:
    match = TOKEN_SECRET.fullmatch(token_secret or "")
    require(match is not None, "worker trace writer version resource required")
    return decode_payload(gcloud.json("secrets", "versions", "access", match[1],
                                      f"--secret={SECRET_ID}", "--format=json"))


def store(token: bytes, gcloud: Gcloud, *, now: float) -> dict:
    code, _, err = gcloud("secrets", "describe", SECRET_ID, "--format=json")
    require(code != 0 and "NOT_FOUND" in err,
            "the writer secret parent already exists; the approval permits creation only when absent")
    parent = gcloud.json("secrets", "create", SECRET_ID, "--replication-policy=user-managed",
                         f"--locations={LOCATION}", "--format=json")
    replicas = parent.get("replication", {}).get("userManaged", {}).get("replicas")
    require(NATIVE_PARENT.fullmatch(parent.get("name", "")) is not None and isinstance(replicas, list)
            and [replica.get("location") for replica in replicas] == [LOCATION],
            "the created parent does not match the approved replication")
    workspace = Path(tempfile.mkdtemp(prefix="worker-trace-"))
    try:
        token_file = workspace / "token"
        descriptor = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(token)
        version = gcloud.json("secrets", "versions", "add", SECRET_ID, f"--data-file={token_file}", "--format=json")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    match = NATIVE_VERSION.fullmatch(version.get("name", ""))
    require(match is not None and version.get("state") == "ENABLED", "the added version is not enabled")
    number = match[1]
    described = gcloud.json("secrets", "versions", "describe", number, f"--secret={SECRET_ID}", "--format=json")
    require(described.get("name") == version["name"] and described.get("state") == "ENABLED",
            "version readback does not match the added version")
    accessed = gcloud.json("secrets", "versions", "access", number, f"--secret={SECRET_ID}", "--format=json")
    require(decode_payload(accessed) == token, "the stored version does not match the private token bytes")
    return {"schema": "worker-trace-writer-secret/v1", "stored_at": stamp(now), "parent": PARENT,
            "parent_native": parent["name"], "version": int(number),
            "token_secret": f"{PARENT}/versions/{number}", "token_secret_native": version["name"],
            "state": "ENABLED", "replication": {"user_managed": [LOCATION]}, "readback_verified": True,
            "requests_used": len(gcloud.calls), "storage_quote": STORAGE_QUOTE,
            "approval_sha256": TRACE_APPROVAL_SHA256}


def identity(token: bytes, *, token_secret: str, receipt_path: Path, now: float, connection_factory=None) -> dict:
    """The single approved identity GET; the attempt is recorded before it is sent."""
    for name in FORBIDDEN_ENVIRONMENT:
        require(os.getenv(name) is None, f"{name} must not be set for the identity check")
    durable_write(receipt_path.with_name(f"{receipt_path.stem}.attempt.json"),
                  {"attempted_at": stamp(now), "token_secret": token_secret}, exclusive=True)
    receipt = {"schema": "trace-identity-receipt/v1", "requested_at": stamp(now), "host": HOST,
               "path": INFO_PATH, "attempts": 1, "token_secret": token_secret,
               "approval_sha256": TRACE_APPROVAL_SHA256, "verified": False}
    try:
        if connection_factory is None:
            context = ssl.create_default_context()
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            connection = http.client.HTTPSConnection(HOST, 443, timeout=IDENTITY_TIMEOUT_SECONDS, context=context)
        else:
            connection = connection_factory()
        try:
            connection.request("GET", INFO_PATH, headers={
                "Authorization": token.decode("ascii"), "Accept": "application/json",
                "User-Agent": "specimen-digitization-trace-identity/1", "Connection": "close"})
            response = connection.getresponse()
            status = response.status
            body = response.read(BODY_LIMIT + 1)
        finally:
            connection.close()
        receipt["http_status"] = status
        require(len(body) <= BODY_LIMIT, "identity response exceeds the approved size")
        require(status == 200, f"identity endpoint answered {status}; the writer is not verified")
        info = strict_json(body)
        require(info.get("project_name") == APPROVED_PROJECT_NAME and info.get("project_url") == APPROVED_PROJECT_URL,
                "the writer token does not belong to the approved Logfire project")
        receipt.update(project_name=info["project_name"], project_url=info["project_url"],
                       trace_project_id=APPROVED_PROJECT_ID, verified=True)
        return receipt
    except BaseException as error:
        receipt["failed"] = str(error)[:240]
        raise
    finally:
        durable_write(receipt_path, receipt)


def accessor_binding(version: int, expires_at: str) -> dict:
    return {"role": ACCESSOR_ROLE, "members": [WORKER_IDENTITY],
            "condition": {"title": GRANT_TITLE,
                          "description": ("Approved 2026-09-14: worker-only read of the exact writer "
                                          "version until the runtime expiration."),
                          "expression": (f"resource.name.endsWith('/secrets/{SECRET_ID}/versions/{version}') && "
                                         f"request.time < timestamp('{expires_at}')")}}


def secret_policy(gcloud: Gcloud) -> dict:
    return gcloud.json("secrets", "get-iam-policy", SECRET_ID, "--format=json")


def set_secret_policy(gcloud: Gcloud, policy: dict) -> dict:
    workspace = Path(tempfile.mkdtemp(prefix="worker-trace-"))
    try:
        policy_file = workspace / "policy.json"
        policy_file.write_text(json.dumps(policy, indent=2) + "\n")
        return gcloud.json("secrets", "set-iam-policy", SECRET_ID, str(policy_file), "--format=json")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def grant(gcloud: Gcloud, *, version: int, expires_at: str, now: float) -> dict:
    expiry = parse_stamp(expires_at)
    require(isinstance(version, int) and version > 0, "positive version number required")
    require(now < expiry <= now + 24 * 3600, "runtime expiration must lie within the next 24 hours")
    before = secret_policy(gcloud)
    require(isinstance(before.get("etag"), str) and before["etag"] and not before.get("bindings"),
            "the writer secret must carry no bindings before the grant; reconcile by hand")
    binding = accessor_binding(version, expires_at)
    returned = set_secret_policy(gcloud, {"etag": before["etag"], "version": 3, "bindings": [binding]})
    require(returned.get("bindings") == [binding] and returned.get("etag") not in (None, "", before["etag"]),
            "the returned policy does not match the planned grant")
    readback = secret_policy(gcloud)
    require(readback.get("bindings") == [binding] and readback.get("etag") == returned["etag"],
            "the policy readback does not match the planned grant")
    return {"schema": "worker-trace-writer-grant/v1", "granted_at": stamp(now), "secret": PARENT,
            "binding": binding, "expires_at": expires_at, "policy_etag_after": readback["etag"],
            "requests_used": len(gcloud.calls), "approval_sha256": TRACE_APPROVAL_SHA256}


def revoke(gcloud: Gcloud, *, now: float) -> dict:
    before = secret_policy(gcloud)
    bindings = before.get("bindings") or []
    require(isinstance(before.get("etag"), str) and before["etag"] and len(bindings) == 1
            and bindings[0].get("role") == ACCESSOR_ROLE and bindings[0].get("members") == [WORKER_IDENTITY]
            and bindings[0].get("condition", {}).get("title") == GRANT_TITLE,
            "only the one owned accessor grant may be removed; reconcile anything else by hand")
    returned = set_secret_policy(gcloud, {"etag": before["etag"], "version": 3, "bindings": []})
    require(not returned.get("bindings") and returned.get("etag") not in (None, "", before["etag"]),
            "the returned policy still carries bindings")
    readback = secret_policy(gcloud)
    require(not readback.get("bindings") and readback.get("etag") == returned["etag"],
            "the policy readback still carries bindings")
    return {"schema": "worker-trace-writer-revoke/v1", "revoked_at": stamp(now), "secret": PARENT,
            "removed": bindings[0], "policy_etag_after": readback["etag"], "requests_used": len(gcloud.calls)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    storer = commands.add_parser("store", help="create the parent and its one version from a private token file")
    storer.add_argument("--token-file", required=True, type=Path, help="owner-only (0600) file holding the token")
    storer.add_argument("--receipt", required=True, type=Path)
    checker = commands.add_parser("identity", help="the single approved identity request")
    checker.add_argument("--token-secret", required=True, help=f"{PARENT}/versions/N")
    checker.add_argument("--receipt", required=True, type=Path)
    granter = commands.add_parser("grant", help="grant the worker identity read of the exact version")
    granter.add_argument("--version", required=True, type=int)
    granter.add_argument("--expires-at", required=True, help="the runtime packet's expiration, RFC 3339 UTC")
    granter.add_argument("--receipt", required=True, type=Path)
    revoker = commands.add_parser("revoke", help="remove the one owned accessor grant")
    revoker.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args(argv)
    now = time.time()

    if args.command == "store":
        token = read_token(args.token_file)
        receipt = store(token, Gcloud(now + 300, ceiling=STORE_REQUESTS), now=now)
        durable_write(args.receipt, receipt)
        print(f"Stored {receipt['token_secret']} (native {receipt['token_secret_native']}); "
              f"readback verified with {receipt['requests_used']} requests; receipt {args.receipt}")
        print(f"worker_logfire_token_secret_version: {receipt['token_secret']}")
        return 0
    if args.command == "identity":
        token = fetch_token(Gcloud(now + 60, ceiling=1), args.token_secret)
        receipt = identity(token, token_secret=args.token_secret, receipt_path=args.receipt, now=now)
        digest = sha256_bytes(args.receipt.read_bytes())
        print(f"Writer verified for {receipt['project_url']}; receipt {args.receipt}")
        print(f"trace_project_id: {receipt['trace_project_id']}")
        print(f"trace_identity_receipt_sha256: {digest}")
        return 0
    if args.command == "grant":
        receipt = grant(Gcloud(now + 300, ceiling=GRANT_REQUESTS), version=args.version,
                        expires_at=args.expires_at, now=now)
    else:
        receipt = revoke(Gcloud(now + 300, ceiling=GRANT_REQUESTS), now=now)
    durable_write(args.receipt, receipt)
    print(f"{args.command} complete; policy etag {receipt['policy_etag_after']}; receipt {args.receipt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
