"""Committed runtime settings against the current release and operator consumers."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ops"))
sys.path.insert(0, str(ROOT / "scripts/ci"))
import deploy as D  # noqa: E402
import iam as G  # noqa: E402
import runtime_settings as S  # noqa: E402

# SHA-256 of the canonical {file name: SHA-256} map of the eight checkpoint files.
CHECKPOINT = "9089029b241c8342be41225b51531bf0457f2db0c3b9896c844b22b3487ac9b8"  # pragma: allowlist secret


def test_no_role_waits_for_a_committed_setting():
    assert {role: S.pending(role) for role in S.ROLES} == {"api": [], "worker": [], "sam": []}


def test_checkpoint_digest_names_the_mount_environment_and_listing_grant():
    assert S.SAM_CHECKPOINT_SHA256 == CHECKPOINT
    prefix = f"application/sha256/{CHECKPOINT}/sam3-cache"
    assert D.mount_options(CHECKPOINT) == [f"only-dir={prefix}", "uid=10001", "gid=10001"]
    for role in ("sam", "worker"):
        assert D.role_env(role, CHECKPOINT)["SPECIMEN_SAM3_CHECKPOINT_SHA256"] == CHECKPOINT
    listing = [grant for grant in G.grants(S.PROJECT, CHECKPOINT)
               if grant.condition and grant.condition[1] == "specimen_sam3_checkpoint_listing"]
    assert len(listing) == 1
    assert listing[0].member == f"serviceAccount:{S.SAM['service_account']}"
    assert listing[0].condition[0] == f'{G.LISTING}.startsWith("{prefix}")'


def test_sam3_serves_each_run_offline_for_the_worker_and_only_on_cloud_run():
    from specimen_digitization.application.sam3_server import serving_mode

    env = D.role_env("sam", CHECKPOINT)
    assert S.SAM_SERVER_ENV == {"SPECIMEN_SAM3_ENABLE": "authorized-run"}
    assert serving_mode({**env, "K_SERVICE": "specimen-sam"}) == "authorized-run"
    with pytest.raises(RuntimeError, match="sam3_requires_authorized_cloud_run_launch"):
        serving_mode(env)
    assert (env["SPECIMEN_SAM3_CALLER_EMAIL"], env["SPECIMEN_SAM3_AUDIENCE"]) == (
        S.WORKER["service_account"], S.SAM_URL)
    assert env["HF_HUB_OFFLINE"] == "1" and not {
        "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACEHUB_API_TOKEN"
    } & set(env)


def test_sam3_startup_and_cpu_contracts_are_explicit():
    probe = S.SAM["startup_probe"]
    assert probe["tcpSocket"] == {"port": 8080} and probe["timeoutSeconds"] <= probe["periodSeconds"]
    assert probe["periodSeconds"] * probe["failureThreshold"] == 600
    assert (S.SAM["cpu_idle"], S.SAM["startup_cpu_boost"]) == (False, True)


def test_checkpoint_mount_belongs_to_the_sam3_image_user():
    dockerfile = (ROOT / "containers/worker/sam3.Dockerfile").read_text()
    assert "useradd --uid 10001 " in dockerfile and "\nUSER 10001\n" in dockerfile
    assert S.SAM["mount_options"] == ["uid=10001", "gid=10001"]


def test_no_role_mounts_the_google_maps_key():
    names = {name for role in S.ROLES.values() for name in role["secret_env"]}
    secrets = {*S.SECRET_VERSIONS, *(secret for role in S.ROLES.values() for secret in role["secret_env"].values())}
    assert not any("MAPS" in name for name in names) and not any("maps" in secret for secret in secrets)


def test_worker_hands_over_to_the_job_the_api_starts():
    assert S.WORKER["env"].get("SPECIMEN_WORKER_JOB") == S.API["env"]["SPECIMEN_WORKER_JOB"] == S.WORKER_JOB
    worker = f"serviceAccount:{S.WORKER['service_account']}"
    handover = [grant for grant in G.grants(S.PROJECT, CHECKPOINT)
                if grant.member == worker and (grant.kind, grant.name) == ("job", "specimen-worker")]
    assert [grant.role for grant in handover] == ["roles/run.invoker"]


def test_only_worker_turns_the_research_harness_on():
    from specimen_digitization.research_harness.enablement import (
        SETTING, research_harness_enabled, research_harness_mode,
    )

    worker = D.role_env("worker", CHECKPOINT)
    assert SETTING == "SPECIMEN_RESEARCH_HARNESS" and worker[SETTING] == "fields"
    assert research_harness_enabled(worker) is True and research_harness_mode(worker) == "fields"
    assert all(SETTING not in S.ROLES[role]["env"] for role in ("api", "sam"))


def test_the_processes_that_create_runs_carry_the_first_pass_units_switch_off():
    # docs/execution/units/PLAN.md, WP 1.2: off by default. The Run(...) calls that set a run's path
    # from it are in api.py, bulk_intake.py and source_import.py (tests/test_first_pass_units.py),
    # which the API and the intake job run; the worker's and SAM's env do not carry it. WP 1.8
    # turns it on.
    from specimen_digitization.application.reading_units import OLD, SETTING, first_pass_path

    api = D.role_env("api", CHECKPOINT)
    assert SETTING == "SPECIMEN_FIRST_PASS_UNITS" and api[SETTING] == "off"
    assert S.INTAKE["env"][SETTING] == "off" and first_pass_path(api) == OLD
    assert all(SETTING not in S.ROLES[role]["env"] for role in ("worker", "sam"))


def test_the_api_and_the_worker_carry_the_same_nvidia_option():
    # NVIDIA_NEMOTRON_OPTION.md section 2: both processes load the published
    # profiles; the API copies a run's prices at queue time and the worker picks
    # its routes at classify, so a run never mixes the two options. Unset in
    # both is the production default (the option is off).
    from specimen_digitization.application.model_option import SETTING, nvidia_stages

    api, worker = (S.ROLES[role]["env"] for role in ("api", "worker"))
    if SETTING in api or SETTING in worker:
        assert api.get(SETTING) == worker.get(SETTING)
        nvidia_stages(worker)  # A value the processes accept.
    assert SETTING not in S.ROLES["sam"]["env"]


def test_worker_job_passes_the_real_drain_parser_and_settings_check(monkeypatch, capsys):
    from specimen_digitization import observability
    from specimen_digitization.application import worker
    from specimen_digitization.application.lane_worker import EMULATOR_KEYS

    assert S.WORKER["args"] == ["--mode", "production", "--drain", "--max-seconds", "3300"]
    assert int(S.WORKER["args"][-1]) < S.WORKER["timeout_seconds"]
    for name in (*EMULATOR_KEYS, "SPECIMEN_SAM3_LAB", "CLOUD_RUN_EXECUTION", "CLOUD_RUN_TASK_INDEX"):
        monkeypatch.delenv(name, raising=False)
    values = D.role_env("worker", CHECKPOINT)
    values.update({name: "{}" if name.endswith("_JSON") else "synthetic"
                   for name in S.WORKER["secret_env"]})
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("LOGFIRE_SEND_TO_LOGFIRE", "false")
    monkeypatch.setattr(observability.logfire, "configure", lambda **_: pytest.fail("the check configured tracing"))
    monkeypatch.setattr(sys, "argv", ["specimen-worker", *S.WORKER["args"], "--check-config"])
    worker.main()
    assert json.loads(capsys.readouterr().out) == {
        "status": "configured", "mode": "drain", "live_services_verified": False,
    }
