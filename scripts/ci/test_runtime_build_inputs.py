from pathlib import Path
import os
import subprocess

import pytest


@pytest.mark.parametrize("target", ["api", "worker", "sam"])
def test_missing_integrated_image_input_fails_before_docker(tmp_path, target):
    source = Path(__file__).with_name("build_runtime_image.sh")
    script = tmp_path / "scripts/ci/build_runtime_image.sh"
    script.parent.mkdir(parents=True)
    script.write_text(source.read_text())
    result = subprocess.run(["bash", str(script), target], env=dict(os.environ,
                            GITHUB_SHA="a" * 40, GITHUB_HEAD_REF="codex/live-integration"),
                            text=True, capture_output=True)
    assert result.returncode == 1
    assert "is absent" in result.stderr
