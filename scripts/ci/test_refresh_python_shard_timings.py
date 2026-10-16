"""Offline timing refresh must require complete exact-provenance evidence."""
from copy import deepcopy
import importlib
import json

import pytest

import python_shards
from test_python_shards import telemetry_results


def refresh_module():
    return importlib.import_module("refresh_python_shard_timings")


def measurement_results():
    results = telemetry_results()
    for result in results:
        result["identity"] = {"GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123",
                              "GITHUB_RUN_ATTEMPT": "2"}
    return results


@pytest.mark.parametrize("fault", ["missing", "duplicate", "cancelled", "stale", "manifest",
                                  "incomplete", "order", "duration", "phase"])
def test_refresh_requires_all_matching_complete_shards(fault):
    results = measurement_results()
    expected = deepcopy(results[0]["identity"])
    if fault == "missing":
        results.pop()
    elif fault == "duplicate":
        results[1] = deepcopy(results[0])
    elif fault == "cancelled":
        results[0]["exitstatus"] = 2
    elif fault == "stale":
        results[0]["identity"]["GITHUB_RUN_ATTEMPT"] = "1"
    elif fault == "manifest":
        results[1]["timing_manifest_digest"] = "c" * 64
    elif fault == "incomplete":
        results[0]["reports"].pop(results[0]["selected"][0])
    elif fault == "order":
        results[1]["collected"].reverse()
    elif fault == "duration":
        results[0]["durations"][results[0]["selected"][0]]["call"] = float("nan")
    elif fault == "phase":
        results[0]["durations"][results[0]["selected"][0]].pop("teardown")
    with pytest.raises(ValueError):
        refresh_module().refresh(results, 3, expected, {})


def test_refresh_sums_every_phase_deterministically_and_preserves_provenance(tmp_path):
    results = measurement_results()
    manifest = refresh_module().refresh(results, 3, results[0]["identity"], {})
    assert manifest == refresh_module().refresh(list(reversed(results)), 3,
                                               results[0]["identity"], {})
    assert manifest["schema"] == 2
    assert manifest["mode"] == "complete"
    assert manifest["measurement_identity"] == results[0]["identity"]
    assert manifest["inventory_digest"] == results[0]["inventory_digest"]
    assert manifest["source_fingerprints"] == results[0]["source_fingerprints"]
    assert manifest["module_seconds"] == {"tests/test_a.py": 3.75,
                                          "scripts/ci/test_b.py": 2.25,
                                          "scripts/release/test_c.py": 1.5}
    path = tmp_path / "timings.json"
    path.write_text(json.dumps(manifest))
    hints = python_shards.load_timings(path, fingerprints=manifest["source_fingerprints"])
    assert hints.mode == "complete"
    assert dict(hints) == manifest["module_seconds"]
    # Source SHA identifies measurement; a new commit containing the manifest
    # can reuse unchanged inputs without a self-referential SHA requirement.
    hints = python_shards.load_timings(path, fingerprints={"test.py": "b" * 64})
    assert not hints, "changed source inputs must fall back to item cost"


def test_refresh_rejects_unbound_measurement_identity():
    results = measurement_results()
    unbound = {"GITHUB_SHA": "", "GITHUB_RUN_ID": "", "GITHUB_RUN_ATTEMPT": ""}
    for result in results:
        result["identity"] = dict(unbound)
    with pytest.raises(ValueError, match="identity"):
        refresh_module().refresh(results, 3, unbound, {})


@pytest.mark.parametrize("field", ["GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"])
@pytest.mark.parametrize("value", [None, True, 123, "", "wrong", "0", "01", "<missing>"])
def test_refresh_rejects_missing_or_malformed_identity_fields(field, value):
    results = measurement_results()
    invalid = dict(results[0]["identity"])
    if value == "<missing>":
        invalid.pop(field)
    else:
        invalid[field] = value
    for result in results:
        result["identity"] = dict(invalid)
    with pytest.raises(ValueError, match="identity"):
        refresh_module().refresh(results, 3, invalid, {})


def test_refresh_skips_have_only_the_phases_that_really_ran():
    results = measurement_results()
    node = results[0]["selected"][0]
    results[0]["reports"][node] = {"setup": "skipped", "teardown": "passed"}
    results[0]["durations"][node] = {"setup": 0.0, "teardown": 0.0}
    manifest = refresh_module().refresh(results, 3, results[0]["identity"], {})
    assert manifest["module_seconds"]["tests/test_a.py"] == 3.0


@pytest.mark.parametrize("fault", ["mode", "identity", "inventory", "fingerprints", "module_nodes"])
def test_complete_manifest_rejects_malformed_provenance(tmp_path, fault):
    results = measurement_results()
    manifest = refresh_module().refresh(results, 3, results[0]["identity"], {})
    key, value = {"mode": ("mode", "lower_bound"),
                  "identity": ("measurement_identity", {}),
                  "inventory": ("inventory_digest", "wrong"),
                  "fingerprints": ("source_fingerprints", {}),
                  "module_nodes": ("module_inventory_digests", {})}[fault]
    manifest[key] = value
    path = tmp_path / "timings.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="invalid Python shard timings"):
        python_shards.load_timings(path)


def test_refresh_cli_is_offline_and_refuses_missing_input_without_output(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    results = measurement_results()
    timings = tmp_path / "input-timings.json"
    timings.write_text(json.dumps({"schema": 1, "module_seconds": {}}))
    hints = python_shards.load_timings(timings)
    paths = []
    for result in results:
        result["timing_manifest_digest"] = hints.manifest_digest
        path = tmp_path / f'shard-{result["index"]}.json'
        path.write_text(json.dumps(result))
        paths.append(path)
    output = tmp_path / "refreshed.json"
    command = [sys.executable, str(Path(__file__).with_name("refresh_python_shard_timings.py")),
               "--count", "3", "--timings", str(timings), "--source-sha", "a" * 40,
               "--run-id", "123", "--run-attempt", "2", "--output", str(output)]
    run = subprocess.run(command + list(map(str, paths)), capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(output.read_text())["module_seconds"]["tests/test_a.py"] == 3.75
    output.unlink()
    run = subprocess.run(command + list(map(str, paths[:-1])), capture_output=True, text=True)
    assert run.returncode == 1
    assert "missing or extra shard" in run.stderr
    assert not output.exists()
