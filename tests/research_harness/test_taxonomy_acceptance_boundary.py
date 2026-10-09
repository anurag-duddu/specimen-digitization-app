"""V4 closure covers taxonomy helpers while historical proof pairs stay intact."""
from pathlib import Path

import pytest

from specimen_digitization.research_harness import accepted_output


@pytest.mark.parametrize("changed", accepted_output.VALIDATOR_COMPONENTS)
def test_validator_or_taxonomy_helper_drift_invalidates_new_acceptance(tmp_path, monkeypatch, changed):
    original = Path(accepted_output.__file__).parent
    for name in (*accepted_output.VALIDATOR_COMPONENTS, "engine.py", "journal.py"):
        (tmp_path / name).write_bytes((original / name).read_bytes())
    monkeypatch.setattr(accepted_output, "__file__", str(tmp_path / "accepted_output.py"))
    assert accepted_output.installed_validator_source_sha256(tmp_path) == accepted_output.VALIDATOR_SOURCE_SHA256
    assert accepted_output.validation_boundary_pins()
    path = tmp_path / changed
    path.write_bytes(path.read_bytes() + b"\n# Synthetic byte drift\n")
    with pytest.raises(ValueError, match="accepted_output_validator_source_unqualified"):
        accepted_output.validation_boundary_pins()
