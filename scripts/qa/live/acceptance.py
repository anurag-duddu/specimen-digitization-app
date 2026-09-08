"""Offline evidence preflight. Never reads cloud objects or executes evidence commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from uuid import UUID


PRD_CASES = tuple(f"PRD-{number:02d}" for number in range(1, 21))
LIVE_CASES = (
    "AUTH-IDENTITY",
    "AUTH-APPCHECK",
    "AUTH-MEMBERSHIP",
    "AUTH-REVOKE",
    "AUTH-CROSS-SCOPE",
    "DATA-TEN",
    "DATA-GENERATION",
    "DATA-RESTORE",
    "PROVIDER-ACTUAL",
    "COST-BOUNDS",
    "RETRY-UNKNOWN",
    "WORKER-RESTART",
    "API-RESTART",
    "DEPLOY-IDENTITY",
    "BROWSER-E2E",
)
CASES = PRD_CASES + LIVE_CASES
MODES = {"fixture", "emulator", "owner_report", "live"}
STATES = {"passed", "failed", "blocked", "not_run"}
REPOSITORY = "anurag-duddu/specimen-digitization-app"


class InvalidEvidence(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InvalidEvidence(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def keys(value, required, optional=()):
    require(isinstance(value, dict), "Expected object")
    require(
        set(required) <= value.keys() <= set(required) | set(optional),
        "Missing or unknown manifest field",
    )


def sha(value, length=64):
    return isinstance(value, str) and re.fullmatch(f"[a-f0-9]{{{length}}}", value)


def file_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def parse_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=unique)


def read_json(path):
    return parse_json(path.read_bytes())


def private_manifest(path, expected_sha):
    require(
        not any((parent / ".git").exists() for parent in path.resolve().parents),
        "Private manifest must stay outside Git",
    )
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(info.st_mode)
            and stat.S_IMODE(info.st_mode) == 0o600
            and info.st_uid == os.getuid(),
            "Private owner/mode required",
        )
        raw = stream.read(1024 * 1024 + 1)
    require(len(raw) <= 1024 * 1024, "Manifest exceeds size bound")
    require(hashlib.sha256(raw).hexdigest() == expected_sha, "Manifest bytes changed")
    return parse_json(raw)


def manifest_ids(manifest):
    """Independently check the data owner's specimen-pilot/v1 ready contract."""
    keys(
        manifest,
        (
            "schema_version",
            "status",
            "project_id",
            "authorization_reference",
            "selection",
            "specimens",
        ),
    )
    require(
        manifest.get("schema_version") == "specimen-pilot/v1", "Unknown manifest schema"
    )
    require(
        manifest.get("status") == "ready", "Metadata-only manifest cannot authorize use"
    )
    require(manifest.get("project_id") == "specimen-digitization", "Wrong project")
    require(
        nonempty(manifest.get("authorization_reference")),
        "Authorization reference missing",
    )
    require(
        len(manifest["authorization_reference"]) <= 512,
        "Authorization reference too long",
    )
    selection = manifest.get("selection")
    keys(selection, ("order", "source_inventory_sha256"))
    require(
        isinstance(selection, dict)
        and selection.get("order") == "explicit_source_order"
        and sha(selection.get("source_inventory_sha256")),
        "Source order/inventory missing",
    )
    specimens = manifest.get("specimens")
    require(
        isinstance(specimens, list) and len(specimens) == 10,
        "Need exactly ten specimens",
    )
    identifiers, objects, scopes, bindings = set(), set(), set(), set()
    for index, specimen in enumerate(specimens, 1):
        keys(
            specimen,
            (
                "ordinal",
                "specimen_id",
                "organization_id",
                "collection_id",
                "source_objects",
                "application_source",
            ),
        )
        for key in ("specimen_id", "organization_id", "collection_id"):
            value = specimen.get(key)
            require(
                nonempty(value) and str(UUID(value)) == value, "Canonical UUID required"
            )
        ident = specimen["specimen_id"]
        require(ident not in identifiers, "Duplicate specimen")
        identifiers.add(ident)
        scopes.add((specimen["organization_id"], specimen["collection_id"]))
        require(
            type(specimen.get("ordinal")) is int and specimen["ordinal"] == index,
            "Selection order changed",
        )
        rows = specimen.get("source_objects")
        require(isinstance(rows, list) and rows, "Specimen has no frozen objects")
        for row in rows:
            keys(
                row,
                ("bucket", "object_name", "generation", "sha256", "size_bytes"),
                ("crc32c", "md5_hash"),
            )
            for key in ("bucket", "object_name", "generation"):
                require(nonempty(row.get(key)), f"Object missing {key}")
            require(
                3 <= len(row["bucket"]) <= 222
                and re.fullmatch(r"[a-z0-9][a-z0-9._-]+", row["bucket"]),
                "Invalid bucket name",
            )
            require(
                len(row["object_name"]) <= 1024
                and all(ord(c) >= 32 and ord(c) != 127 for c in row["object_name"]),
                "Invalid object name",
            )
            for field, length in (("crc32c", 6), ("md5_hash", 22)):
                value = row.get(field)
                require(
                    value is None
                    or isinstance(value, str)
                    and re.fullmatch(f"[A-Za-z0-9+/]{{{length}}}==", value),
                    "Invalid object checksum encoding",
                )
            require(
                re.fullmatch(r"[1-9][0-9]*", row["generation"]),
                "Generation must be a positive decimal string",
            )
            require(sha(row.get("sha256")), "Object SHA-256 missing")
            require(
                type(row.get("size_bytes")) is int and row["size_bytes"] > 0,
                "Object byte length missing",
            )
            identity = (row["bucket"], row["object_name"], row["generation"])
            require(
                identity not in objects, "Object generation assigned more than once"
            )
            objects.add(identity)
        app = specimen.get("application_source")
        keys(app, ("blob_ref", "sha256", "size_bytes", "source_object_index"))
        selected = app.get("source_object_index")
        require(
            type(selected) is int and 0 <= selected < len(rows), "Invalid source index"
        )
        source = rows[selected]
        require(
            app.get("sha256") == source["sha256"]
            and type(app.get("size_bytes")) is int
            and app["size_bytes"] == source["size_bytes"],
            "Application digest/size differs from original",
        )
        ref = app.get("blob_ref")
        require(
            nonempty(ref)
            and re.fullmatch(r"[a-f0-9]{64}:[1-9][0-9]*", ref)
            and ref.split(":", 1)[0] == source["sha256"],
            "Invalid application blob reference",
        )
        require(ref not in bindings, "Application source assigned more than once")
        bindings.add(ref)
    require(len(scopes) == 1, "Pilot must retain one authorized collection scope")
    return identifiers


def artifact(root, entry):
    require(isinstance(entry, dict), "Invalid artifact descriptor")
    relative = entry.get("path")
    require(nonempty(relative), "Artifact path missing")
    path = Path(relative)
    require(not path.is_absolute() and ".." not in path.parts, "Unsafe artifact path")
    resolved = (root / path).resolve()
    require(resolved.is_relative_to(root.resolve()), "Artifact escapes evidence root")
    require(resolved.is_file(), "Artifact missing")
    require(sha(entry.get("sha256")), "Artifact digest missing")
    require(file_digest(resolved) == entry["sha256"], "Artifact digest mismatch")


def skeleton(candidate_sha, manifest_sha):
    return {
        "schema_version": 1,
        "candidate_sha": candidate_sha,
        "manifest_sha256": manifest_sha,
        "deployment": {},
        "results": [
            {
                "case_id": case,
                "status": "not_run",
                "mode": "fixture",
                "candidate_sha": candidate_sha,
                "manifest_sha256": manifest_sha,
                "specimen_ids": [],
                "artifacts": [],
                "reason": "Awaiting execution",
            }
            for case in CASES
        ],
    }


def evaluate(manifest, manifest_sha, report, root, candidate_sha):
    ids = manifest_ids(manifest)
    require(sha(candidate_sha, 40), "Expected full candidate SHA required")
    require(
        isinstance(report, dict) and report.get("schema_version") == 1,
        "Unknown report schema",
    )
    require(report.get("candidate_sha") == candidate_sha, "Wrong candidate SHA")
    require(report.get("manifest_sha256") == manifest_sha, "Wrong frozen manifest")
    results = report.get("results")
    require(isinstance(results, list), "Results must be a list")
    seen, pending = set(), []
    for row in results:
        require(isinstance(row, dict), "Invalid case row")
        case = row.get("case_id")
        require(case in CASES and case not in seen, "Unknown/duplicate acceptance case")
        seen.add(case)
        require(row.get("status") in STATES, "Invalid case state")
        require(row.get("mode") in MODES, "Invalid evidence mode")
        require(row.get("candidate_sha") == candidate_sha, "Stale case candidate")
        require(row.get("manifest_sha256") == manifest_sha, "Stale case manifest")
        tested = row.get("specimen_ids")
        require(
            isinstance(tested, list) and all(isinstance(i, str) for i in tested),
            "Case specimen IDs missing",
        )
        require(
            len(set(tested)) == len(tested) and set(tested) <= ids,
            "Case contains duplicate or unauthorized specimen",
        )
        artifacts = row.get("artifacts")
        require(isinstance(artifacts, list), "Artifact list missing")
        for entry in artifacts:
            artifact(root, entry)
        if row["status"] == "passed":
            require(artifacts, "Passing case has no retained evidence")
            for key in (
                "observer",
                "started_at_utc",
                "ended_at_utc",
                "command",
                "expected",
                "actual",
                "transport",
            ):
                require(nonempty(row.get(key)), f"Passing case missing {key}")
            require(
                type(row.get("exit_code")) is int and row["exit_code"] == 0,
                "Passing case command failed",
            )
        if row["status"] != "passed" or row["mode"] != "live":
            pending.append(case)
        elif case in {"DATA-TEN", "DATA-GENERATION", "PROVIDER-ACTUAL", "BROWSER-E2E"}:
            require(set(tested) == ids, "Full ten-specimen coverage required")
    require(
        seen == set(CASES), "Missing acceptance cases; never shrink the denominator"
    )
    deployment = report.get("deployment")
    require(isinstance(deployment, dict), "Deployment descriptor missing")
    deployment_keys = (
        "main_workflow_url",
        "deploy_job_url",
        "api_image_digest",
        "worker_image_digest",
        "connector_revision",
        "storage_rules_revision",
        "runtime_workflow_url",
    )
    if any(not nonempty(deployment.get(key)) for key in deployment_keys) or (
        deployment.get("repository") != REPOSITORY
        or deployment.get("hosting_commit_sha") != candidate_sha
        or deployment.get("api_commit_sha") != candidate_sha
        or deployment.get("worker_commit_sha") != candidate_sha
        or deployment.get("main_workflow_conclusion") != "success"
        or deployment.get("deploy_job_conclusion") != "success"
    ):
        pending.append("DEPLOYMENT-PROVENANCE")
    return {
        "schema_version": 1,
        "candidate_sha": candidate_sha,
        "manifest_sha256": manifest_sha,
        "denominator": 10,
        "evidence_preflight": "incomplete"
        if pending
        else "ready_for_independent_review",
        "release_accepted": False,
        "pending": pending,
        "limitation": "Offline integrity checks do not authenticate claims, approve scope, "
        "establish first-ten selection, or grant institutional quality approval.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--approved-manifest-sha256", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--evidence-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        require(sha(args.approved_manifest_sha256), "Approved manifest digest required")
        require(sha(args.candidate_sha, 40), "Candidate must be a full commit SHA")
        actual = args.approved_manifest_sha256
        manifest = private_manifest(args.manifest, actual)
        manifest_ids(manifest)
        if args.report is None:
            print(json.dumps(skeleton(args.candidate_sha, actual), indent=2))
            return 0
        result = evaluate(
            manifest,
            actual,
            read_json(args.report),
            args.evidence_root,
            args.candidate_sha,
        )
        print(json.dumps(result, indent=2))
        return 0 if not result["pending"] else 1
    except (InvalidEvidence, OSError, ValueError, TypeError) as exc:
        # Avoid echoing paths or malformed JSON which could contain private data.
        print(
            json.dumps(
                {
                    "evidence_preflight": "invalid",
                    "release_accepted": False,
                    "error_type": type(exc).__name__,
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
