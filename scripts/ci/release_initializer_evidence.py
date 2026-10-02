"""Failure-only encrypted observations; no authorization, native calls or replay."""
from contextlib import contextmanager
import base64
import hashlib
import json
import os
import re

from release_admission import private_bytes
from release_catalog_envelope import encrypt_catalog
from release_context import PROJECT, REPOSITORY

SOURCE = "specimen-digitization-instance"
LIMIT = 65536
TARGET = "initializer-failure.encrypted.json"
JOURNALS = (f"initializer-create-{SOURCE}.json", f"initializer-create-effect-{SOURCE}.json", f"roles-create-{SOURCE}.json")


@contextmanager
def preserve_failure(google, directory):
    """Keep the original exception and exact unknown/observed journals, only as ciphertext.

    The committed public recipient is checked before effects. Successful paths
    produce no artifact. Retention cannot adopt success, change a deadline or
    turn a failed or unknown effect into permission to submit it again.
    """
    from release_bootstrap import recipient
    key = recipient()
    packet = google.packet
    provenance = {"repository": REPOSITORY, "source_sha": packet["source_sha"],
                  "run_id": packet["release_run_id"], "run_attempt": packet["release_run_attempt"]}
    observations = []

    def retain(method, resource, status, raw):
        users = f"projects/{PROJECT}/instances/{SOURCE}/users"
        if not (method == "POST" and resource == users or method == "GET" and
                re.fullmatch(f"projects/{PROJECT}/operations/[A-Za-z0-9_-]+", resource)):
            return
        if type(raw) is not bytes or type(status) is not int or not 400 <= status <= 599:
            return
        observations.append({"method": method, "resource": resource, "http_status": status,
            "response_bytes": len(raw), "response_retained": len(raw) <= LIMIT,
            "response_b64": base64.b64encode(raw).decode("ascii") if len(raw) <= LIMIT else None})

    previous = getattr(google, "initializer_failure_evidence", None)
    google.initializer_failure_evidence = retain
    try:
        yield
    except BaseException:
        try:
            journals = []
            for name in JOURNALS:
                path = directory / name
                if path.exists():
                    raw = private_bytes(path)
                    journals.append({"name": name, "sha256": hashlib.sha256(raw).hexdigest(),
                        "bytes": len(raw), "retained": len(raw) <= LIMIT,
                        "body_b64": base64.b64encode(raw).decode("ascii") if len(raw) <= LIMIT else None})
            value = {"version": "initializer-failure-evidence/v1", "provenance": provenance,
                     "observations": observations, "journals": journals,
                     "release_accepted": False, "retry_authorized": False}
            raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
            envelope = encrypt_catalog(raw, key["public_key_pem"].encode(),
                public_key_sha256=key["public_key_sha256"], provenance=provenance)
            fd = os.open(directory / TARGET, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as handle:
                json.dump(envelope, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            if os.environ.get("GITHUB_OUTPUT"):
                with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
                    handle.write("failure_evidence=present\n")
        except Exception:
            # The original intent remains private on the runner; the original
            # refusal remains authoritative even if encryption/upload is unavailable.
            pass
        raise
    finally:
        if previous is None:
            del google.initializer_failure_evidence
        else:
            google.initializer_failure_evidence = previous
