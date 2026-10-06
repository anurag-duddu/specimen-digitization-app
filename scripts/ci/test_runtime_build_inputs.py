from pathlib import Path
import os
import subprocess
import sys
import textwrap
import tomllib

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


def test_all_qualified_packages_are_pinned_runtime_dependencies():
    from specimen_digitization.research_harness.package_qualification import QUALIFIED_PACKAGES

    project = tomllib.loads((Path(__file__).parents[2] / "pyproject.toml").read_text())
    runtime = {
        requirement.split("==")[0].split("[")[0]: requirement.split("==")[1]
        for requirement in project["project"]["dependencies"] if "==" in requirement
    }
    assert {name: runtime.get(name) for name in QUALIFIED_PACKAGES} == dict(QUALIFIED_PACKAGES)


@pytest.mark.parametrize("target,missing", [
    ("api", False), ("worker", False), ("api", True), ("worker", True), ("sam", True),
])
def test_image_check_qualifies_real_packages_and_refuses_missing_distribution(tmp_path, target, missing):
    """Run the real shell and qualifier through a local Docker command adapter.

    This proves shell admission/failure propagation, not an installed image;
    the image build gate exercises the same command in the no-dev containers.
    """
    source = Path(__file__).with_name("build_runtime_image.sh")
    script = tmp_path / "scripts/ci/build_runtime_image.sh"
    script.parent.mkdir(parents=True)
    script.write_text(source.read_text())
    dockerfile = tmp_path / {
        "api": "containers/api/Dockerfile",
        "worker": "containers/worker/Dockerfile",
        "sam": "containers/worker/sam3.Dockerfile",
    }[target]
    dockerfile.parent.mkdir(parents=True)
    dockerfile.touch()
    commands = tmp_path / "bin"
    commands.mkdir()
    git = commands / "git"
    git.write_text("#!/bin/sh\ncase \"$1\" in archive|show) exit 0 ;; *) exit 99 ;; esac\n")
    git.chmod(0o755)
    docker = commands / "docker"
    docker.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''\
        import json
        import os
        from pathlib import Path
        import sys

        args = sys.argv[1:]
        if args[0] == "build":
            sys.stdin.buffer.read()
        elif args[:2] == ["image", "inspect"]:
            print("linux/amd64" if "Architecture" in args[-1] else os.environ["GITHUB_SHA"])
        elif args[0] == "volume":
            pass
        elif args[0] == "run":
            if "-c" in args and "qualify_packages" in args[args.index("-c") + 1]:
                assert args[args.index("--network") + 1] == "none"
                assert "--read-only" in args
                assert args[args.index("--cap-drop") + 1] == "ALL"
                assert args[args.index("--security-opt") + 1] == "no-new-privileges"
                assert args[args.index("--entrypoint") + 1] == "python"
                assert "--user" not in args
                from specimen_digitization.research_harness import package_qualification as packages
                if os.environ["MISSING_EVALS"] == "1":
                    from importlib.metadata import PackageNotFoundError
                    original_version = packages.version
                    def version(name):
                        if name == "pydantic-evals":
                            raise PackageNotFoundError(name)
                        return original_version(name)
                    packages.version = version
                Path(os.environ["QUALIFICATION_MARKER"]).write_text("started")
                exec(args[args.index("-c") + 1])
                Path(os.environ["QUALIFICATION_MARKER"]).write_text("passed")
            elif "--version" in args:
                print(json.dumps({"source_sha": os.environ["GITHUB_SHA"]}))
        else:
            raise AssertionError(args)
    '''))
    docker.chmod(0o755)
    marker = tmp_path / "qualified"
    result = subprocess.run(
        ["bash", str(script), target],
        env=dict(os.environ, PATH=f"{commands}{os.pathsep}{os.environ['PATH']}",
                 GITHUB_SHA="a" * 40, MISSING_EVALS=str(int(missing)),
                 QUALIFICATION_MARKER=str(marker)),
        text=True, capture_output=True,
    )
    if target == "sam":
        assert result.returncode == 0, result.stderr
        assert not marker.exists()
    elif missing:
        assert result.returncode != 0
        assert "PackageNotFoundError" in result.stderr
        assert "pydantic-evals" in result.stderr
        assert marker.read_text() == "started"
        assert "Built and CLI-smoked" not in result.stdout
    else:
        assert result.returncode == 0, result.stderr
        assert marker.read_text() == "passed"
