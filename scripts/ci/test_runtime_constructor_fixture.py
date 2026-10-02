"""Offline container smoke must traverse the actual current worker constructor."""

import hashlib
import json
from pathlib import Path
import runpy
from types import SimpleNamespace
from unittest.mock import patch

from specimen_digitization.application.production import actor_uid
from specimen_digitization.application.worker_launch import PilotLaunch


def test_worker_smoke_constructs_current_native_graph_factory_without_effects(tmp_path, monkeypatch):
    smoke = runpy.run_path(str(Path(__file__).with_name("smoke_runtime_inputs.py")))
    directory = tmp_path / "synthetic-inputs"
    # prepare() is the separate container-root fixture writer; this assertion
    # substitution creates only local synthetic files, with its exact bytes.
    with patch("os.getuid", return_value=0):
        smoke["prepare"](directory)
    launch_path = directory / "launch"
    launch = PilotLaunch.model_validate(json.loads(launch_path.read_bytes()))
    monkeypatch.setenv("SPECIMEN_LAUNCH_POLICY_SHA256", hashlib.sha256(launch_path.read_bytes()).hexdigest())
    args = SimpleNamespace(mode="production", materialize_config=True,
                           launch_policy=launch_path, source_manifest=directory / "manifest",
                           evidence_only=False, evidence_profile=None)

    def refuse_network(*_args, **_kwargs):
        raise AssertionError("Constructor smoke must not connect to any service")

    monkeypatch.setattr("socket.socket.connect", refuse_network)
    token = actor_uid.set("synthetic-smoke-caller")
    try:
        smoke["verify_worker_construction"](args, launch)
        assert actor_uid.get() == "synthetic-smoke-caller"
        assert set(directory.iterdir()) == {launch_path, directory / "manifest"}
        assert launch.source_manifest_sha256 == hashlib.sha256((directory / "manifest").read_bytes()).hexdigest()
    finally:
        actor_uid.reset(token)
