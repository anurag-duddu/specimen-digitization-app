"""Offline timing refresh must require complete exact-provenance evidence."""
from collections import Counter
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
    assert manifest["schema"] == 3
    assert manifest["mode"] == "complete"
    assert manifest["measurement_identity"] == results[0]["identity"]
    assert manifest["inventory_digest"] == results[0]["inventory_digest"]
    assert manifest["source_fingerprints"] == [{"path": "test.py", "sha256": "a" * 64}]
    modules = sorted({node.split("::", 1)[0] for node in results[0]["collected"]})
    assert manifest["module_inventory_digests"] == [
        {"path": module, "sha256": python_shards.digest(
            [node for node in results[0]["collected"] if node.split("::", 1)[0] == module])}
        for module in modules]
    assert manifest["module_seconds"] == {"tests/test_a.py": 3.75,
                                          "scripts/ci/test_b.py": 2.25,
                                          "scripts/release/test_c.py": 1.5}
    path = tmp_path / "timings.json"
    path.write_text(json.dumps(manifest))
    hints = python_shards.load_timings(path)
    assert hints.mode == "complete"
    assert dict(hints) == manifest["module_seconds"]
    # Source SHA identifies measurement; a new commit containing the manifest
    # reuses every cost, and unchanged module inventories keep exact weights.
    nodes = results[0]["collected"]
    assert python_shards.module_weights(nodes, hints) == manifest["module_seconds"]


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
@pytest.mark.parametrize("schema", [2, 3])
def test_complete_manifest_rejects_malformed_provenance(tmp_path, fault, schema):
    results = measurement_results()
    manifest = refresh_module().refresh(results, 3, results[0]["identity"], {})
    if schema == 2:
        manifest["schema"] = 2
        for field in ("source_fingerprints", "module_inventory_digests"):
            manifest[field] = {record["path"]: record["sha256"] for record in manifest[field]}
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


@pytest.mark.parametrize("input_schema", [1, 2, 3])
def test_refresh_cli_is_offline_and_refuses_missing_input_without_output(tmp_path, input_schema):
    import subprocess
    import sys
    from pathlib import Path

    results = measurement_results()
    timings = tmp_path / "input-timings.json"
    manifest = {"schema": 1, "module_seconds": {}}
    if input_schema in (2, 3):
        manifest = refresh_module().refresh(results, 3, results[0]["identity"], {})
        if input_schema == 2:
            manifest["schema"] = 2
            for field in ("source_fingerprints", "module_inventory_digests"):
                manifest[field] = {record["path"]: record["sha256"] for record in manifest[field]}
    timings.write_text(json.dumps(manifest))
    hints = python_shards.load_timings(timings)
    paths = []
    for result in results:
        result["timing_manifest_digest"] = hints.manifest_digest
        result["timing_mode"] = hints.mode
        path = tmp_path / f'shard-{result["index"]}.json'
        path.write_text(json.dumps(result))
        paths.append(path)
    output = tmp_path / "refreshed.json"
    command = [sys.executable, str(Path(__file__).with_name("refresh_python_shard_timings.py")),
               "--count", "3", "--timings", str(timings), "--source-sha", "a" * 40,
               "--run-id", "123", "--run-attempt", "2", "--output", str(output)]
    run = subprocess.run(command + list(map(str, paths)), capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    refreshed = json.loads(output.read_text())
    assert refreshed["schema"] == 3
    assert refreshed["module_seconds"]["tests/test_a.py"] == 3.75
    loaded = python_shards.load_timings(output)
    assert dict(loaded) == refreshed["module_seconds"]
    assert refreshed["source_fingerprints"] == [{"path": "test.py", "sha256": "a" * 64}]
    output.unlink()
    run = subprocess.run(command + list(map(str, paths[:-1])), capture_output=True, text=True)
    assert run.returncode == 1
    assert "missing or extra shard" in run.stderr
    assert not output.exists()


def schema3_manifest():
    results = measurement_results()
    return refresh_module().refresh(results, 3, results[0]["identity"], {})


def test_refresh_sorts_typed_records_without_changing_values():
    results = measurement_results()
    sources = {"tests/z.py": "b" * 64, "test.py": "a" * 64}
    for result in results:
        result["source_fingerprints"] = dict(sources)
    manifest = refresh_module().refresh(results, 3, results[0]["identity"], {})
    for result in results:
        result["source_fingerprints"] = dict(reversed(list(sources.items())))
    assert manifest == refresh_module().refresh(results, 3, results[0]["identity"], {})
    assert manifest["source_fingerprints"] == [
        {"path": "test.py", "sha256": "a" * 64},
        {"path": "tests/z.py", "sha256": "b" * 64}]
    for field in ("source_fingerprints", "module_inventory_digests"):
        records = manifest[field]
        assert [record["path"] for record in records] == sorted(record["path"] for record in records)
        assert all(set(record) == {"path", "sha256"} for record in records)


@pytest.mark.parametrize("field", ["source_fingerprints", "module_inventory_digests"])
@pytest.mark.parametrize("value", [None, {}, "not records", [None], [[]], [{}],
                                  [{"path": "test.py"}], [{"sha256": "a" * 64}],
                                  [{"path": "test.py", "digest": "a" * 64}],
                                  [{"path": "test.py", "sha256": "a" * 64, "extra": 1}]])
def test_schema3_refuses_untyped_or_mixed_records(tmp_path, field, value):
    manifest = schema3_manifest()
    manifest[field] = value
    path = tmp_path / "timings.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="invalid Python shard timings"):
        python_shards.load_timings(path)


@pytest.mark.parametrize("field", ["source_fingerprints", "module_inventory_digests"])
@pytest.mark.parametrize("value", [None, True, 123, "a" * 63, "a" * 65, "A" * 64,
                                  "g" * 64, ["a" * 64]])
def test_schema3_refuses_malformed_record_digests(tmp_path, field, value):
    manifest = schema3_manifest()
    manifest[field][0]["sha256"] = value
    path = tmp_path / "timings.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="invalid path/sha256 record"):
        python_shards.load_timings(path)


@pytest.mark.parametrize("field", ["source_fingerprints", "module_inventory_digests"])
@pytest.mark.parametrize("value", [None, True, 123, "", ".", "..", "../test.py",
                                  "tests/../test.py", "./test.py", "tests/./test.py",
                                  "tests//test.py", "/test.py", "//server/test.py",
                                  "tests\\test.py", "C:/test.py", "C:\\test.py",
                                  "tests/test.py/", "tests/\x00test.py",
                                  "tests/\ntest.py", "tests/\x7ftest.py"])
def test_schema3_refuses_noncanonical_record_paths(tmp_path, field, value):
    manifest = schema3_manifest()
    manifest[field][0]["path"] = value
    path = tmp_path / "timings.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="invalid path/sha256 record"):
        python_shards.load_timings(path)


@pytest.mark.parametrize("field", ["source_fingerprints", "module_inventory_digests"])
@pytest.mark.parametrize("duplicate", ["identical", "changed_digest", "dot_alias", "slash_alias",
                                      "backslash_alias"])
def test_schema3_refuses_duplicate_paths_and_aliases(tmp_path, field, duplicate):
    manifest = schema3_manifest()
    record = deepcopy(manifest[field][0])
    if duplicate == "changed_digest":
        record["sha256"] = "f" * 64
    elif duplicate == "dot_alias":
        record["path"] = "./" + record["path"]
    elif duplicate == "slash_alias":
        record["path"] = "tests//" + record["path"]
    elif duplicate == "backslash_alias":
        record["path"] = "tests\\" + record["path"]
    manifest[field].append(record)
    path = tmp_path / "timings.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="invalid Python shard timings"):
        python_shards.load_timings(path)


@pytest.mark.parametrize("field", ["schema", "mode", "measurement_identity", "inventory_digest",
                                  "timing_manifest_digest", "source_fingerprints",
                                  "module_inventory_digests", "module_seconds"])
def test_schema3_requires_all_root_fields(tmp_path, field):
    manifest = schema3_manifest()
    manifest.pop(field)
    path = tmp_path / "timings.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="invalid Python shard timings"):
        python_shards.load_timings(path)


@pytest.mark.parametrize("field,value", [("schema", True), ("schema", 4), ("extra", {}),
                                        ("source_fingerprints", []),
                                        ("module_inventory_digests", []),
                                        ("module_seconds", []), ("mode", "lower_bound")])
def test_schema3_refuses_wrong_root_types_and_extra_fields(tmp_path, field, value):
    manifest = schema3_manifest()
    manifest[field] = value
    path = tmp_path / "timings.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="invalid Python shard timings"):
        python_shards.load_timings(path)


@pytest.mark.parametrize("fault", ["missing", "extra", "wrong_path", "alias"])
def test_schema3_requires_exact_canonical_inventory_modules(tmp_path, fault):
    manifest = schema3_manifest()
    if fault == "missing":
        manifest["module_inventory_digests"].pop()
    elif fault == "extra":
        manifest["module_inventory_digests"].append({"path": "tests/new.py", "sha256": "b" * 64})
    elif fault == "wrong_path":
        manifest["module_inventory_digests"][0]["path"] = "tests/new.py"
    else:
        module = next(iter(manifest["module_seconds"]))
        manifest["module_seconds"]["./" + module] = manifest["module_seconds"].pop(module)
    path = tmp_path / "timings.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="invalid Python shard timings"):
        python_shards.load_timings(path)


@pytest.mark.parametrize("field", ["schema", "path", "sha256", "module_seconds"])
def test_schema3_rejects_duplicate_json_fields_before_normalization(tmp_path, field):
    contents = json.dumps(schema3_manifest())
    old, new = {
        "schema": ('"schema": 3', '"schema": 2, "schema": 3'),
        "path": ('"path": "test.py"', '"path": "other.py", "path": "test.py"'),
        "sha256": ('"sha256": "' + "a" * 64 + '"',
                   '"sha256": "invalid", "sha256": "' + "a" * 64 + '"'),
        "module_seconds": ('"tests/test_a.py": 3.75',
                           '"tests/test_a.py": 99, "tests/test_a.py": 3.75'),
    }[field]
    assert old in contents
    path = tmp_path / "timings.json"
    path.write_text(contents.replace(old, new, 1))
    with pytest.raises(ValueError, match="duplicate JSON field"):
        python_shards.load_timings(path)


def test_complete_schema2_and_schema3_have_identical_partition_semantics(tmp_path):
    manifest = schema3_manifest()
    path = tmp_path / "timings.json"
    path.write_text(json.dumps(manifest))
    records = python_shards.load_timings(path)
    for field in ("source_fingerprints", "module_inventory_digests"):
        manifest[field] = {record["path"]: record["sha256"] for record in manifest[field]}
    manifest["schema"] = 2
    path.write_text(json.dumps(manifest))
    legacy = python_shards.load_timings(path)
    assert dict(records) == dict(legacy) == manifest["module_seconds"]
    assert records.mode == legacy.mode == "complete"
    assert records.module_inventory_digests == legacy.module_inventory_digests
    assert records.manifest_digest != legacy.manifest_digest
    nodes = measurement_results()[0]["collected"]
    assert python_shards.partition(nodes, 2, records) == python_shards.partition(nodes, 2, legacy)


def test_schema3_record_order_is_not_inventory_order_and_mismatch_keeps_all_nodes(tmp_path):
    manifest = schema3_manifest()
    path = tmp_path / "timings.json"
    path.write_text(json.dumps(manifest))
    hints = python_shards.load_timings(path)
    for field in ("source_fingerprints", "module_inventory_digests"):
        manifest[field].reverse()
    path.write_text(json.dumps(manifest))
    reordered = python_shards.load_timings(path)
    assert dict(reordered) == dict(hints)
    assert reordered.module_inventory_digests == hints.module_inventory_digests
    nodes = measurement_results()[0]["collected"]
    assert python_shards.partition(nodes, 2, reordered) == python_shards.partition(nodes, 2, hints)
    for record in manifest["module_inventory_digests"]:
        record["sha256"] = "f" * 64
    path.write_text(json.dumps(manifest))
    changed = python_shards.load_timings(path)
    assert dict(changed) == manifest["module_seconds"]
    sizes = Counter(node.split("::", 1)[0] for node in nodes)
    assert python_shards.module_weights(nodes, changed) == pytest.approx(
        {module: sizes[module] / 10 + seconds
         for module, seconds in manifest["module_seconds"].items()})
    shards = python_shards.partition(nodes, 2, changed)
    assert sorted(node for shard in shards for node in shard) == sorted(nodes)
    for module in manifest["module_seconds"]:
        expected = [node for node in nodes if node.split("::", 1)[0] == module]
        assert [shard for shard in shards if expected[0] in shard]
        assert [node for shard in shards for node in shard if node in set(expected)] == expected


@pytest.mark.parametrize("schema", [1, 2, 3])
def test_timing_versions_preserve_lower_bound_and_complete_zero_rules(tmp_path, schema):
    manifest = schema3_manifest()
    manifest["schema"] = schema
    if schema in (1, 2):
        for field in ("source_fingerprints", "module_inventory_digests"):
            manifest[field] = {record["path"]: record["sha256"] for record in manifest[field]}
    if schema == 1:
        manifest = {"schema": 1, "module_seconds": manifest["module_seconds"]}
    manifest["module_seconds"]["tests/test_a.py"] = 0
    path = tmp_path / "timings.json"
    path.write_text(json.dumps(manifest))
    if schema == 1:
        with pytest.raises(ValueError, match="invalid module timing"):
            python_shards.load_timings(path)
        manifest["module_seconds"]["tests/test_a.py"] = 1
        path.write_text(json.dumps(manifest))
    hints = python_shards.load_timings(path)
    assert hints.mode == ("lower_bound" if schema == 1 else "complete")
    assert dict(hints) == manifest["module_seconds"]
