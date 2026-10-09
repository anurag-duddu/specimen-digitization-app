"""The committed worker job and SAM 3 settings, read as committed, against the code that consumes them.

No fixture fills a value. Each test builds the release's own bodies from runtime_settings and hands them to the
worker's own parser and settings check, SAM 3's serving rule or the owner's grant table (RELEASE.md section 3.2).
"""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import deploy_runtime as D  # noqa: E402
import owner_grants as G  # noqa: E402
import runtime_settings as S  # noqa: E402

# SHA-256 of the canonical {file name: SHA-256} map of the eight checkpoint files (sam3_server.checkpoint_files_digest).
CHECKPOINT = "9089029b241c8342be41225b51531bf0457f2db0c3b9896c844b22b3487ac9b8"  # pragma: allowlist secret (public checkpoint digest)


def bodies(*roles):
    images = {role: f"us-east4-docker.pkg.dev/specimen-digitization/specimen-runtime/{role}@sha256:" + "6" * 64
              for role in roles}
    return D.released_bodies(images, "a" * 40, 456, 1, list(roles))


def plain_env(container):
    return {row["name"]: row["value"] for row in container["env"] if "value" in row}


def test_no_role_waits_for_a_committed_setting():
    assert {role: S.pending(role) for role in S.ROLES} == {"api": [], "worker": [], "sam": []}


def test_the_checkpoint_digest_names_the_mount_both_bodies_and_the_listing_grant():
    assert S.SAM_CHECKPOINT_SHA256 == CHECKPOINT
    built, prefix = bodies("sam", "worker"), f"application/sha256/{CHECKPOINT}/sam3-cache"
    sam = built["sam"]["template"]
    assert sam["volumes"][0]["gcs"]["mountOptions"] == [f"only-dir={prefix}", "uid=10001", "gid=10001"]
    assert sam["containers"][0]["volumeMounts"] == [{"name": "checkpoint", "mountPath": S.SAM["env"]["HF_HOME"]}]
    for container in (sam["containers"][0], built["worker"]["template"]["template"]["containers"][0]):
        assert plain_env(container)["SPECIMEN_SAM3_CHECKPOINT_SHA256"] == CHECKPOINT
    standing, waiting = G.runtime_grants(S)
    listing = [grant for grant in standing if grant.condition and grant.condition[1] == "specimen_sam3_checkpoint_listing"]
    assert waiting == [] and [grant.member for grant in listing] == [G.SAM]
    assert listing[0].condition[0] == f'{G.LISTING}.startsWith("{prefix}")'


def test_sam3_serves_each_run_offline_for_the_worker_and_only_on_cloud_run():
    from specimen_digitization.application.sam3_server import serving_mode

    assert S.SAM_SERVER_ENV == {"SPECIMEN_SAM3_ENABLE": "authorized-run"}
    container = bodies("sam")["sam"]["template"]["containers"][0]
    env = plain_env(container)
    assert serving_mode({**env, "K_SERVICE": "specimen-sam"}) == "authorized-run"  # Cloud Run sets K_SERVICE
    with pytest.raises(RuntimeError, match="sam3_requires_authorized_cloud_run_launch"):
        serving_mode(env)
    # sam3_server.serve_runs admits only the worker's identity token for SAM 3's own URL.
    assert (env["SPECIMEN_SAM3_CALLER_EMAIL"], env["SPECIMEN_SAM3_AUDIENCE"]) == (S.WORKER["service_account"], S.SAM_URL)
    # offline_checkpoint_digest refuses an online hub or any Hugging Face credential.
    assert env["HF_HUB_OFFLINE"] == "1" and not {row["name"] for row in container["env"]} & {
        "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACEHUB_API_TOKEN"}


def test_sam3_may_take_the_longest_startup_cloud_run_allows_without_a_gpu():
    probe = bodies("sam")["sam"]["template"]["containers"][0]["startupProbe"]
    assert probe["tcpSocket"] == {"port": 8080} and probe["timeoutSeconds"] <= probe["periodSeconds"]
    assert probe["periodSeconds"] * probe["failureThreshold"] == 600
    observed = bodies("sam")["sam"]
    D.verify_runtime_template(copy.deepcopy(observed), observed, role="sam")
    changed = copy.deepcopy(observed)
    changed["template"]["containers"][0]["startupProbe"]["failureThreshold"] = 24  # back to the 240 s default
    with pytest.raises(ValueError, match="runtime startup probe changed"):
        D.verify_runtime_template(changed, observed, role="sam")
    api = bodies("api")["api"]
    defaulted = copy.deepcopy(api)  # Cloud Run reports its default probe for a body that sets none
    defaulted["template"]["containers"][0]["startupProbe"] = {
        "tcpSocket": {"port": 8080}, "timeoutSeconds": 240, "periodSeconds": 240, "failureThreshold": 1}
    D.verify_runtime_template(defaulted, api, role="api")


def test_sam3_keeps_cpu_allocated_and_boosts_startup_and_the_check_holds_it():
    """An abandoned inference holds SAM 3's run lock; it must keep its CPU after the worker disconnects."""
    built = bodies("sam", "api")
    sam, api = (built[role]["template"]["containers"][0]["resources"] for role in ("sam", "api"))
    assert (sam["cpuIdle"], sam["startupCpuBoost"]) == (S.SAM["cpu_idle"], S.SAM["startup_cpu_boost"]) == (False, True)
    assert (api["cpuIdle"], api["startupCpuBoost"]) == (True, False)
    expected = built["sam"]
    reported = copy.deepcopy(expected)  # proto3 JSON may omit a false bool
    del reported["template"]["containers"][0]["resources"]["cpuIdle"]
    D.verify_runtime_template(reported, expected, role="sam")
    for drift in ({"cpuIdle": True}, {"startupCpuBoost": False}):
        changed = copy.deepcopy(expected)
        changed["template"]["containers"][0]["resources"].update(drift)
        with pytest.raises(ValueError, match="runtime billing or startup CPU policy changed"):
            D.verify_runtime_template(changed, expected, role="sam")
    defaulted = copy.deepcopy(built["api"])
    del defaulted["template"]["containers"][0]["resources"]["cpuIdle"]  # the API must still report cpuIdle true
    with pytest.raises(ValueError, match="runtime billing or startup CPU policy changed"):
        D.verify_runtime_template(defaulted, built["api"], role="api")


def test_the_checkpoint_mount_belongs_to_the_sam3_image_user():
    """Cloud Run volumes are root-owned by default; the mount names the uid and gid the SAM 3 image runs as."""
    dockerfile = (Path(__file__).resolve().parents[2] / "containers/worker/sam3.Dockerfile").read_text()
    assert "useradd --uid 10001 " in dockerfile and "\nUSER 10001\n" in dockerfile
    assert S.SAM["mount_options"] == ["uid=10001", "gid=10001"]


def test_no_role_mounts_the_google_maps_key():
    """Place lookups use GEOLocate, which needs no key (owner ruling); no role reads a Maps secret."""
    names = {name for role in S.ROLES.values() for name in role["secret_env"]}
    secrets = {*S.SECRET_VERSIONS, *(secret for role in S.ROLES.values() for secret in role["secret_env"].values())}
    assert not any("MAPS" in name for name in names) and not any("maps" in secret for secret in secrets)


def test_the_worker_hands_over_to_the_job_the_api_starts():
    """Work left at the drain's deadline goes to the job's next execution (lane_worker.py, owner_grants.py)."""
    assert S.WORKER["env"].get("SPECIMEN_WORKER_JOB") == S.API["env"]["SPECIMEN_WORKER_JOB"] == S.WORKER_JOB
    handover = [grant for grant in G.AFTER_RELEASE if grant.member == G.WORKER and grant.resource == ("job", "specimen-worker")]
    assert [grant.role for grant in handover] == ["roles/run.invoker"]


def test_only_the_worker_job_turns_the_research_harness_on():
    """The drain reads the switch with enablement's own parser; the API and SAM 3 never carry it."""
    from specimen_digitization.research_harness.enablement import (
        SETTING, research_harness_enabled, research_harness_mode,
    )

    assert SETTING == "SPECIMEN_RESEARCH_HARNESS" and S.WORKER["env"][SETTING] == "fields"
    built = bodies("api", "worker", "sam")
    worker = plain_env(built["worker"]["template"]["template"]["containers"][0])
    assert worker[SETTING] == "fields" and research_harness_enabled(worker) is True
    assert research_harness_mode(worker) == "fields"
    for role in ("api", "sam"):
        names = {row["name"] for row in built[role]["template"]["containers"][0]["env"]}
        assert SETTING not in S.ROLES[role]["env"] and SETTING not in names


def test_the_worker_job_passes_the_real_drain_parser_and_settings_check(monkeypatch, capsys):
    """The job's args replace the image's CMD ["--mode", "production"], so they must carry the mode themselves."""
    from specimen_digitization import observability
    from specimen_digitization.application import worker
    from specimen_digitization.application.lane_worker import EMULATOR_KEYS

    assert S.WORKER["args"] == ["--mode", "production", "--drain", "--max-seconds", "3300"]
    assert int(S.WORKER["args"][-1]) < S.WORKER["timeout_seconds"]  # the drain ends inside the task timeout
    container = bodies("worker")["worker"]["template"]["template"]["containers"][0]
    assert container["args"] == S.WORKER["args"] and "command" not in container
    for name in (*EMULATOR_KEYS, "SPECIMEN_SAM3_LAB", "CLOUD_RUN_EXECUTION", "CLOUD_RUN_TASK_INDEX"):
        monkeypatch.delenv(name, raising=False)
    for row in container["env"]:  # each secret gets a placeholder; an empty bindings map is valid
        monkeypatch.setenv(row["name"], row.get("value") or ("{}" if row["name"].endswith("_JSON") else "synthetic"))
    monkeypatch.setenv("LOGFIRE_SEND_TO_LOGFIRE", "false")  # a configuration check exports nothing
    monkeypatch.setattr(observability.logfire, "configure", lambda **_: pytest.fail("the check configured tracing"))
    monkeypatch.setattr(sys, "argv", ["specimen-worker", *container["args"], "--check-config"])
    worker.main()
    assert json.loads(capsys.readouterr().out) == {"status": "configured", "mode": "drain", "live_services_verified": False}
