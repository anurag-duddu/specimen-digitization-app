"""Refresh complete module costs from all exact-provenance shard artifacts.

This tool does not execute tests. The input timing manifest must be the one
used by every measured leaf. Output is a candidate for independent review.
"""
import argparse
import json
import math
from pathlib import Path
import sys

from python_shards import (decode_json, digest, fingerprint_records, load_timings, TIMINGS,
                           validate_measurement_identity, verify)


def refresh(results, count, expected_identity, timings):
    validate_measurement_identity(expected_identity)
    try:
        verify(results, count, expected_identity, timings)
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError(f"malformed shard result: {error}") from error
    first = results[0]
    nodes = first["collected"]
    modules = sorted({node.split("::", 1)[0] for node in nodes})
    # Traverse inventory order, independent of artifact input order.
    durations = {node: phases for result in results
                 for node, phases in result["durations"].items()}
    seconds = {module: 0.0 for module in modules}
    inventory = {module: [] for module in modules}
    for node in nodes:
        module = node.split("::", 1)[0]
        inventory[module].append(node)
        seconds[module] += sum(durations[node][phase]
                               for phase in ("setup", "call", "teardown")
                               if phase in durations[node])
    # Finite individual values can still overflow when summed.
    if not all(math.isfinite(value) for value in seconds.values()):
        raise ValueError("nonfinite complete module duration")
    return {"schema": 3, "mode": "complete", "measurement_identity": dict(expected_identity),
            "inventory_digest": first["inventory_digest"],
            "timing_manifest_digest": first["timing_manifest_digest"],
            "source_fingerprints": fingerprint_records(first["source_fingerprints"]),
            "module_inventory_digests": fingerprint_records(
                {module: digest(inventory[module]) for module in modules}),
            "module_seconds": seconds}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--timings", type=Path, default=TIMINGS)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("results", nargs="+", type=Path)
    args = parser.parse_args()
    expected = {"GITHUB_SHA": args.source_sha, "GITHUB_RUN_ID": args.run_id,
                "GITHUB_RUN_ATTEMPT": args.run_attempt}
    try:
        results = [decode_json(path.read_text(encoding="utf-8")) for path in args.results]
        # The current worktree need not be the measured checkout; costs never
        # depend on current sources. Its planner must match the measured leaves'.
        hints = load_timings(args.timings)
        manifest = refresh(results, args.count, expected, hints)
        contents = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
        args.output.write_text(contents, encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        print(f"Python shard timing refresh failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
