import importlib.util
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("inventory_cloud", ROOT / "scripts/data/inventory_cloud.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_metadata_tool_stops_without_api_enable_auth_prompt_or_private_output(tmp_path, capsys):
    error = subprocess.CompletedProcess([], 1, stdout="", stderr="private-account-DO-NOT-PRINT")
    with patch.object(module.subprocess, "run", return_value=error) as call:
        with pytest.raises(RuntimeError, match="query failed"):
            module.inventory(tmp_path / "private")
    assert call.call_count == 1
    args, kwargs = call.call_args
    assert "--project=specimen-digitization" in args[0]
    assert kwargs["env"]["CLOUDSDK_CORE_SHOULD_PROMPT_TO_ENABLE_API"] == "false"
    assert kwargs["env"]["CLOUDSDK_CORE_DISABLE_PROMPTS"] == "true"
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert "DO-NOT-PRINT" not in capsys.readouterr().out
    assert (tmp_path / "private/buckets.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("port", ["3000", "8000"])
@pytest.mark.parametrize("script, variable", [
    ("test-storage.sh", "SPECIMEN_TEST_STORAGE_PORT"),
    ("test-postgres.sh", "SPECIMEN_TEST_PG_PORT"),
    ("test-postgres.sh", "SPECIMEN_TEST_DC_PORT"),
])
def test_fixtures_reject_reserved_user_ports(port, script, variable):
    import os

    result = subprocess.run(["bash", str(ROOT / "scripts/data" / script)],
                            env=dict(os.environ, **{variable: port}),
                            capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert not result.stdout
