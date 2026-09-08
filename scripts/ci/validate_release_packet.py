#!/usr/bin/env python3
"""Validate public candidate metadata offline; this never authorizes a release."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"[0-9a-f]{64}")
IMAGE = re.compile(
    r"us-east4-docker\.pkg\.dev/specimen-digitization/specimen-runtime/"
    r"(?:api|worker)@sha256:[0-9a-f]{64}"
)
CHECKS = {
    "Repository checks",
    "Python tests",
    "Flutter checks and web build",
    "Flutter android build",
    "Flutter ios build",
}


def exact_keys(value: object, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label}: unexpected or missing fields")
    return value


def fingerprint(value: object, label: str, pattern: re.Pattern = DIGEST) -> None:
    if value is not None and (
        not isinstance(value, str) or pattern.fullmatch(value) is None
    ):
        raise ValueError(f"{label}: invalid immutable reference")


def validate(packet: object, require_ready: bool = False) -> list[str]:
    p = exact_keys(packet, {
        "version", "repository", "project", "source_sha", "images", "data",
        "pilot", "checks", "approvals", "public_config_sha256", "rollback_sha256",
    }, "packet")
    if type(p["version"]) is not int or p["version"] != 1:
        raise ValueError("unsupported packet version")
    if p["repository"] != "anurag-duddu/specimen-digitization-app":
        raise ValueError("wrong repository")
    if p["project"] != "specimen-digitization":
        raise ValueError("wrong project")
    fingerprint(p["source_sha"], "source_sha", SHA)
    gaps = []
    if p["source_sha"] is None:
        gaps.append("source SHA")
    images = exact_keys(p["images"], {"api", "worker"}, "images")
    for role, image in images.items():
        entry = exact_keys(image, {"reference", "source_sha", "provenance_sha256"}, role)
        fingerprint(entry["reference"], role, IMAGE)
        fingerprint(entry["source_sha"], f"{role} source", SHA)
        fingerprint(entry["provenance_sha256"], f"{role} provenance")
        if entry["reference"] is not None and f"/{role}@sha256:" not in entry["reference"]:
            raise ValueError(f"{role}: wrong image role")
        if entry["source_sha"] is not None and entry["source_sha"] != p["source_sha"]:
            raise ValueError(f"{role}: source mismatch")
        if any(v is None for v in entry.values()):
            gaps.append(f"{role} image/provenance")
    data = exact_keys(p["data"], {
        "schema_sha256", "connector_sha256", "storage_rules_sha256",
        "backup_restore_evidence_sha256", "compatibility_evidence_sha256",
    }, "data")
    for key, value in data.items():
        fingerprint(value, key)
        if value is None:
            gaps.append(key)
    pilot = exact_keys(p["pilot"], {"specimen_count", "manifest_sha256"}, "pilot")
    if type(pilot["specimen_count"]) is not int or pilot["specimen_count"] != 10:
        raise ValueError("pilot must contain exactly ten specimens")
    fingerprint(pilot["manifest_sha256"], "pilot manifest")
    if pilot["manifest_sha256"] is None:
        gaps.append("frozen private pilot manifest")
    checks = exact_keys(p["checks"], CHECKS, "checks")
    for name, check in checks.items():
        entry = exact_keys(check, {"source_sha", "conclusion", "run_url"}, name)
        fingerprint(entry["source_sha"], name, SHA)
        if entry["source_sha"] is not None and entry["source_sha"] != p["source_sha"]:
            raise ValueError(f"{name}: stale source")
        if entry["conclusion"] not in {"not_run", "success", "failure", "cancelled", "skipped"}:
            raise ValueError(f"{name}: invalid conclusion")
        url = entry["run_url"]
        if url is not None and (not isinstance(url, str) or re.fullmatch(
            r"https://github\.com/anurag-duddu/specimen-digitization-app/actions/runs/[1-9][0-9]*(?:/job/[1-9][0-9]*)?", url
        ) is None):
            raise ValueError(f"{name}: invalid evidence URL")
        if entry["conclusion"] != "success" or url is None or entry["source_sha"] is None:
            gaps.append(name)
    approvals = exact_keys(p["approvals"], {
        "contract_sha256", "bootstrap_sha256", "budget_sha256", "provider_data_sha256",
    }, "approvals")
    for key, value in approvals.items():
        fingerprint(value, key)
        if value is None:
            gaps.append(key)
    for key in ("public_config_sha256", "rollback_sha256"):
        fingerprint(p[key], key)
        if p[key] is None:
            gaps.append(key)
    if require_ready and gaps:
        raise ValueError("incomplete candidate: " + ", ".join(gaps))
    return gaps


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    try:
        gaps = validate(json.loads(args.packet.read_text()), args.require_ready)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Release packet rejected: {exc}\n")
    print(json.dumps({"structure_valid": True, "missing_evidence": gaps,
                      "authorization_granted": False, "live_evidence_verified": False}))


if __name__ == "__main__":
    main()
