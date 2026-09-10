"""One held, fixed-key Storage insert admits one in-process recovery sequence.

Local journals are evidence only. No read or serialized receipt grants a winner.
Root must reconcile prior issuance and effective IAM before issuing the plan.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time

from release_admission import digest, exact_keys, integer, private_bytes, read_bound_plan, require, strict_json
from release_context import PROJECT, REPOSITORY

BUCKET = "specimen-digitization.firebasestorage.app"
KEY = "application/release-control/first-production-restore.json"
ACTOR = f"specimen-data-release@{PROJECT}.iam.gserviceaccount.com"
SOURCE = "specimen-digitization-instance"
CLONE = "specimen-digitization-restore-20260908-r1"
URL = f"https://storage.googleapis.com/upload/storage/v1/b/{BUCKET}/o"
PARAMS = {"uploadType": "multipart", "name": KEY, "ifGenerationMatch": 0, "projection": "noAcl"}
INTENT = "clone-allowance-intent.json"
PAYLOAD_LIMIT, REQUEST_LIMIT, RESPONSE_LIMIT = 2048, 4096, 16384
_SEAL = object()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def checksum(raw):
    # GCS's object integrity field; SHA256 binds authority and intent separately.
    return base64.b64encode(hashlib.md5(raw, usedforsecurity=False).digest()).decode()


def sync_directory(directory):
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def retain(path, raw):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    sync_directory(path.parent)


def validate_allowance(value, packet, recovery_expiry, *, now=None):
    exact_keys(value, {"version", "bucket", "object", "authority_sha256", "baseline_sha256", "manifest_sha256",
                       "iam_sha256", "issued_at_unix", "expires_at_unix"}, "original clone allowance")
    require(value["version"] == "first-production-restore/v1" and value["bucket"] == BUCKET
            and value["object"] == KEY, "the one stable clone allowance cannot be renamed or reset")
    for key in ("authority_sha256", "baseline_sha256", "manifest_sha256", "iam_sha256"):
        digest(value[key], key)
    require(value["authority_sha256"] == packet["authorization_sha256"]
            and value["manifest_sha256"] == packet["pilot"]["manifest_sha256"], "allowance authority or manifest differs")
    for key in ("issued_at_unix", "expires_at_unix"):
        integer(value[key], 1, 2**53, key)
    now = time.time() if now is None else now
    require(value["issued_at_unix"] <= packet["issued_at_unix"] <= now < recovery_expiry
            <= packet["expires_at_unix"] <= value["expires_at_unix"] <= value["issued_at_unix"] + 7200,
            "original allowance deadline cannot be extended")
    return value


def intent_bytes(path, packet, plan):
    require(plan["version"] in {"data-apply/v1", "data-initialize-missing/v1"}, "only recovery claims the allowance")
    value = validate_allowance(plan["recovery"]["allowance"], packet, plan["recovery"]["expires_at_unix"])
    require(read_bound_plan(path.parent / "plan.json", packet) == plan, "claim plan bytes changed")
    raw = private_bytes(path)
    require(strict_json(raw) == packet, "claim packet bytes changed")
    return canonical({"version": "clone-allowance-intent/v1", "allowance": value,
        "project": PROJECT, "source": SOURCE, "clone": CLONE, "actor": ACTOR,
        "source_sha": packet["source_sha"], "source_tree_sha": packet["source_tree_sha"],
        "run_id": packet["release_run_id"], "run_attempt": packet["release_run_attempt"],
        "plan_sha256": packet["plan_sha256"], "packet_sha256": sha(raw),
        "recovery_expires_at_unix": plan["recovery"]["expires_at_unix"]})


def prepare_intent(path, packet, plan):
    raw = intent_bytes(path, packet, plan)
    require(len(raw) <= PAYLOAD_LIMIT - 100, "claim intent exceeds payload reserve")
    retain(path.parent / INTENT, raw)


def published_intent(google, plan):
    from deploy_runtime import checked, verified_receipt_bytes
    expected = intent_bytes(google.path, google.packet, plan)
    require(private_bytes(google.path.parent / INTENT) == expected, "local intent differs from original authority")
    name = f"clone-allowance-intent-{google.packet['source_sha']}-{google.packet['release_run_attempt']}"
    # Download this run's immutable artifact: local attestation alone is not
    # evidence that publication succeeded before the claim.
    with tempfile.TemporaryDirectory(prefix="clone-intent-") as directory:
        checked(["gh", "run", "download", str(google.packet["release_run_id"]), "--repo", REPOSITORY,
                 "--name", name, "--dir", directory])
        observed = verified_receipt_bytes(Path(directory) / INTENT, sha(expected),
                                         google.packet["source_sha"], "data-release.yml")
    require(observed == expected, "published claim intent differs")
    return expected


def multipart(payload):
    require(type(payload) is bytes and len(payload) <= PAYLOAD_LIMIT, "bounded claim payload required")
    boundary = "specimen-clone-claim-" + sha(payload)[:32]
    metadata = canonical({"name": KEY, "contentType": "application/json", "temporaryHold": True,
                          "md5Hash": checksum(payload)})
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
            + metadata + f"\r\n--{boundary}\r\nContent-Type: application/json\r\n\r\n".encode()
            + payload + f"\r\n--{boundary}--\r\n".encode())
    require(len(body) <= REQUEST_LIMIT, "claim request exceeds bound")
    return body, f"multipart/related; boundary={boundary}"


def validate_response(value, payload):
    require(isinstance(value, dict) and value.get("kind") == "storage#object" and value.get("bucket") == BUCKET
            and value.get("name") == KEY and value.get("contentType") == "application/json"
            and value.get("temporaryHold") is True and value.get("metageneration") == "1"
            and value.get("size") == str(len(payload)) and value.get("md5Hash") == checksum(payload),
            "claim response does not prove the exact initially held object")
    require(isinstance(value.get("generation"), str) and re.fullmatch(r"[1-9][0-9]{0,19}", value["generation"]),
            "positive native claim generation required")


def acquire(google, plan, directory):
    require(google.plane == "data" and google.path.parent == directory, "ordinary recovery invocation required")
    raw = published_intent(google, plan)
    payload = canonical({**strict_json(raw), "version": "clone-allowance-claim/v1", "intent_sha256": sha(raw)})
    require(len(payload) <= PAYLOAD_LIMIT, "claim payload exceeds bound")
    deadline = plan["recovery"]["expires_at_unix"]
    require(time.time() + 1800 < deadline, "insufficient original claim window")
    retain(directory / "clone-allowance-send.json", canonical({"outcome": "unknown", "payload_sha256": sha(payload)}))
    # Never catch and retry, read the object, or reconstruct a winner from files.
    value = google.claim_restore(payload, directory)
    validate_response(value, payload)
    require(time.time() < deadline, "claim response arrived after original deadline")
    retain(directory / "clone-allowance-verified.json", canonical({"generation": value["generation"],
        "payload_sha256": sha(payload), "intent_sha256": sha(raw), "evidence_only": True}))
    return _Winner(_SEAL, google, plan, directory)


class _Winner:
    def __init__(self, seal, google, plan, directory):
        require(seal is _SEAL, "a current native claim response is required")
        self.seal, self.google, self.plan, self.directory = seal, google, plan, directory
        self.next, self.active = 0, None
        self.failed = False
        self.sent = set()

    def __reduce__(self):
        raise TypeError("a clone winner cannot be serialized")

    def effect(self, name, effect):
        from release_admission import admit
        from release_initialize import once
        sequence = ("clone-backup", "clone-create", "clone-restore")
        require(not self.failed and self.next < len(sequence) and name == sequence[self.next] and self.active is None,
                "recovery effect cannot be replayed or reordered")
        self.failed = True  # Any failure retires this invocation's capability.
        require(admit(self.google.path, "data") == self.google.packet, "original claim admission changed")
        remaining = min(self.google.packet["expires_at_unix"], self.plan["recovery"]["expires_at_unix"]) - time.time()
        require(remaining > (1800 if name != "clone-restore" else 60), "original recovery deadline reached")
        if name != "clone-restore":
            source = self.google.request("sql", "GET", f"projects/{PROJECT}/instances/{SOURCE}")
            require(source.get("region") == "us-east4"
                    and source.get("settings", {}).get("settingsVersion") == self.plan["database_etag"], "source revision changed")
            require(self.google.request("sql", "GET", f"projects/{PROJECT}/instances/{CLONE}", missing=True) is None,
                    "existing clone cannot be adopted")
            for resource in ("services/specimen-api", "jobs/specimen-worker"):
                require(self.google.request("run", "GET", f"projects/{PROJECT}/locations/us-east4/{resource}", missing=True) is None,
                        "runtime writers exist")
        def send():
            sync_directory(self.directory)
            require(time.time() + 60 < min(self.google.packet["expires_at_unix"], self.plan["recovery"]["expires_at_unix"]),
                    "recovery observation arrived too late")
            self.active = name
            self.google._clone_winner = self
            try:
                return effect()
            finally:
                self.active = None
                self.google._clone_winner = None
        result = once(self.directory, name, send)
        self.next += 1
        self.failed = False
        return result


def authorize_effect(google, resource):
    # The generic transport also admits the verified numeric project alias.
    resource = re.sub(r"^projects/" + re.escape(google.packet["identity"]["project_number"]) + r"(?=/|$)",
                      f"projects/{PROJECT}", resource)
    targets = {f"projects/{PROJECT}/instances/{SOURCE}/backupRuns": "clone-backup",
               f"projects/{PROJECT}/backups": "clone-backup",
               f"projects/{PROJECT}/instances": "clone-create",
               f"projects/{PROJECT}/instances/{CLONE}/restoreBackup": "clone-restore"}
    if resource not in targets:
        return
    winner = getattr(google, "_clone_winner", None)
    require(type(winner) is _Winner and winner.seal is _SEAL and winner.google is google
            and winner.active == targets[resource], "current invocation's claim winner is required before recovery effects")
    require(winner.active not in winner.sent, "native recovery submission cannot be replayed")
    winner.sent.add(winner.active)
    return min(google.packet["expires_at_unix"], winner.plan["recovery"]["expires_at_unix"])
