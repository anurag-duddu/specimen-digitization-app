#!/usr/bin/env python3
"""Freeze an explicitly ordered metadata catalog; never read cloud image bytes.

Input stays private: {authorization_reference, ordering_evidence,
grouping_evidence, specimens:[{source_record_id, source_objects:[{bucket,
object_name,generation,size_bytes,crc32c?,md5_hash?,sha256?}]}]}.
The operator must establish order/grouping from live metadata before invoking.
Only the first ten records are selected. Missing evidence fails; never skip a
record, substitute another specimen, or derive SHA256 from CRC32C/MD5.
"""

import argparse
import hashlib
import json
from pathlib import Path

from specimen_digitization.application.pilot_manifest import (
    PrivateManifestError, SourceObject, load_ready_manifest, read_private,
    write_private,
)


def freeze_metadata(raw: bytes) -> dict:
    try:
        catalog = json.loads(raw)
        for key in ("authorization_reference", "ordering_evidence", "grouping_evidence"):
            if not isinstance(catalog[key], str) or not catalog[key].strip():
                raise ValueError()
        records = catalog["specimens"][:10]
        if len(records) != 10:
            raise ValueError()
        ids, objects, selected = set(), set(), []
        for ordinal, row in enumerate(records, 1):
            ident = row["source_record_id"]
            if not isinstance(ident, str) or not ident or ident in ids:
                raise ValueError()
            ids.add(ident)
            if not row["source_objects"]:
                raise ValueError()
            sources = []
            for source in row["source_objects"]:
                # Validate the full shape while explicitly preserving unknown SHA.
                value = dict(source)
                sha = value.get("sha256")
                value["sha256"] = sha if sha is not None else "0" * 64
                parsed = SourceObject.model_validate(value)
                if sha is None and not (parsed.crc32c or parsed.md5_hash):
                    raise ValueError()
                key = (parsed.bucket, parsed.object_name, parsed.generation)
                if key in objects:
                    raise ValueError()
                objects.add(key)
                value = parsed.model_dump()
                value["sha256"] = sha
                sources.append(value)
            selected.append({"ordinal": ordinal, "source_record_id": ident,
                             "source_objects": sources})
        return {
            "schema_version": "specimen-pilot-source/v1", "status": "metadata_frozen",
            "project_id": "specimen-digitization",
            "authorization_reference": catalog["authorization_reference"],
            "selection": {"order": "explicit_source_order",
                          "source_inventory_sha256": hashlib.sha256(raw).hexdigest(),
                          "ordering_evidence": catalog["ordering_evidence"],
                          "grouping_evidence": catalog["grouping_evidence"]},
            "specimens": selected,
        }
    except (ValueError, KeyError, TypeError):
        raise PrivateManifestError("Catalog incomplete or source ordering/grouping ambiguous") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze-metadata")
    freeze.add_argument("--catalog", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    ready = commands.add_parser("validate-ready")
    ready.add_argument("--manifest", type=Path, required=True)
    ready.add_argument("--sha256", required=True)
    args = parser.parse_args()
    try:
        if args.command == "freeze-metadata":
            manifest = freeze_metadata(read_private(args.catalog))
            sha = write_private(args.output, manifest)
            print(json.dumps({"status": "metadata_frozen", "specimen_count": 10,
                              "object_count": sum(len(s["source_objects"]) for s in manifest["specimens"]),
                              "manifest_sha256": sha, "ready_for_inference": False}))
        else:
            manifest = load_ready_manifest(args.manifest, args.sha256)
            print(json.dumps({"status": "ready", "specimen_count": len(manifest.specimens),
                              "manifest_sha256": args.sha256, "structural_validation": "passed",
                              "live_source_binding_verified": False}))
    except PrivateManifestError as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
