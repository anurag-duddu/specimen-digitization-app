"""Unproved dependency closure must never authorize focused Python execution.

These are fallback tests, not a claim to discover arbitrary Python readers.
I26 must replace the fallback only with qualified transitive access evidence.
"""

import importlib
import subprocess

import pytest

import python_scope


def test_current_source_has_no_focused_closure_qualification():
    closure = importlib.import_module("python_contract_closure")
    assert closure.focused_contracts_qualified() is False
    assert python_scope.requires_full_python([
        "apps/specimen_digitization/lib/main.dart",
    ]) == (True, ["<focused-contract-closure-unproven>"])


@pytest.mark.parametrize("sources", [
    {
        "tests/test_indirect_reader.py": "from helper import read_contract\ndef test_contract():\n    assert read_contract()\n",
        "tests/helper.py": "from pathlib import Path\ndef read_contract():\n    return Path('apps').joinpath('specimen_digitization', 'lib', 'main.dart').read_text()\n",
    },
    {
        "tests/test_parametrized_reader.py": "import pytest\nfrom pathlib import Path\n@pytest.mark.parametrize('name', ['main.dart', 'router.dart'])\ndef test_contract(name):\n    assert Path('apps/specimen_digitization/lib', name).read_text()\n",
    },
    {
        "tests/test_dynamic_reader.py": "import os\nfrom pathlib import Path\ndef test_contract():\n    assert Path(os.environ['CONTRACT_PATH']).read_text()\n",
    },
    {
        "scripts/export_general_api_contract_fixtures.py": "from pathlib import Path\ndef export():\n    return Path('tests/fixtures/general_api_contract.json').read_bytes()\n",
        "tests/test_general_api_contract_fixtures.py": "from scripts.export_general_api_contract_fixtures import export\ndef test_fixture():\n    assert export()\n",
        "tests/fixtures/general_api_contract.json": '{"revision": 8}\n',
        "apps/specimen_digitization/test/general_api_shared_contract_test.dart": "// Reads tests/fixtures/general_api_contract.json\n",
    },
], ids=["indirect-helper", "parametrized-path", "dynamic-unresolved", "I11-shared-wire-reader"])
def test_unclassified_readers_force_full_until_explicitly_qualified(monkeypatch, tmp_path, sources):
    # A new reader anywhere in a candidate tree must not make the disabled
    # optimization eligible. No grep or filename list is treated as proof.
    for name, content in sources.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    monkeypatch.chdir(tmp_path)
    closure = importlib.import_module("python_contract_closure")
    assert closure.focused_contracts_qualified() is False
    monkeypatch.setattr(python_scope.subprocess, "run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 0,
                            b"M\0apps/specimen_digitization/lib/main.dart\0", b""))
    assert python_scope.classify("pull_request", "a" * 40, "b" * 40) == (
        True, ["<focused-contract-closure-unproven>"])


@pytest.mark.parametrize("path", [
    "scripts/ci/test_smoke_web_routes.py", "tests/research_harness/test_thread_embedded_schema.py",
    "scripts/ci/test_public_settings.py", "tests/test_local_review_runner.py",
    "tests/test_deployment_policy.py", "tests/test_hosting_attempt_binding.py",
    "tests/test_general_api_contract_fixtures.py",
])
def test_full_fallback_cannot_omit_current_or_new_contract_modules(path):
    # Full collection includes the six current readers and the future I11
    # exporter/fixture test without maintaining a second focused selector.
    assert python_scope.requires_full_python([path]) == (True, [path])
