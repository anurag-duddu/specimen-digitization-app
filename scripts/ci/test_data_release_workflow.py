"""Shape of the automatic data release workflow (RELEASE.md section 4.2); no network."""
import os
from pathlib import Path
import re
import subprocess

import yaml

import release_gate

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / ".github/workflows/data-release.yml").read_text()
WORKFLOW = yaml.load(TEXT, Loader=yaml.BaseLoader)
JOBS = WORKFLOW["jobs"]
MAIN_PUSH = "github.event_name == 'push' && github.ref == 'refs/heads/main'"
IDENTITY = "specimen-data-release@specimen-digitization.iam.gserviceaccount.com"
PACKET = '"$RUNNER_TEMP/data-release/packet.json"'
GATE = "uv run python scripts/ci/release_gate.py --plane data"
WAIT_SECONDS = 3300
ADMIT = f"{GATE} --wait-seconds {WAIT_SECONDS} --output {PACKET}"
READMIT = f"{GATE} --output {PACKET}"
DEPLOY = f'uv run python scripts/ci/deploy_data.py --deploy --packet {PACKET} --output "$RUNNER_TEMP/data-receipt.json"'
RECEIPT = "${{ runner.temp }}/data-receipt.json"
READ = {"contents": "read", "actions": "read", "pull-requests": "read"}
LOCK = {"group": "specimen-protected-mutation", "cancel-in-progress": "false"}
NODE = ["actions/setup-node", 'npm install --prefix "$RUNNER_TEMP/firebase-release" --no-audit --no-fund --ignore-scripts '
        "firebase-tools@15.8.0"]


def steps(job):
    return JOBS[job]["steps"]


def index(job, predicate):
    matches = [i for i, step in enumerate(steps(job)) if predicate(step)]
    assert len(matches) == 1, f"{job}: expected exactly one matching step"
    return matches[0]


def uses(action):
    return lambda step: step.get("uses", "").startswith(f"{action}@")


def shape(job):
    """Each step as its action without the version, or its command."""
    return [step["uses"].split("@")[0] if "uses" in step else step["run"] for step in steps(job)]


def test_only_a_push_to_main_starts_a_data_release_and_one_runs_at_a_time():
    assert WORKFLOW["on"] == {"push": {"branches": ["main"]}}
    assert WORKFLOW["permissions"] == {"contents": "read"}
    assert WORKFLOW["concurrency"] == {"group": "specimen-data-release", "cancel-in-progress": "false"}
    assert all(job["if"] == MAIN_PUSH for job in JOBS.values())


def test_a_credential_free_admission_precedes_the_release_and_hands_it_nothing():
    assert set(JOBS) == {"admission", "release"}
    assert "needs" not in JOBS["admission"] and JOBS["release"]["needs"] == "admission"
    # The release job re-admits on its own; no admission output can steer it.
    assert "outputs" not in JOBS["admission"]
    for job in JOBS.values():
        assert job["environment"] == "data-production"
        assert job["env"] == {"GH_TOKEN": "${{ github.token }}", "DEPLOYMENT_ENVIRONMENT": "data-production",
                              "RELEASE_PROJECT": "specimen-digitization", "RELEASE_SERVICE_ACCOUNT": IDENTITY}


def test_only_the_release_job_can_obtain_a_token_or_sign():
    assert JOBS["admission"]["permissions"] == READ
    assert JOBS["release"]["permissions"] == {**READ, "id-token": "write", "attestations": "write"}


def test_every_action_is_pinned_to_a_full_commit_sha():
    assert not any("uses" in job for job in JOBS.values())
    actions = [step["uses"] for job in JOBS.values() for step in job["steps"] if "uses" in step]
    assert actions and all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", action) for action in actions)


def test_the_workflow_reads_no_secret_no_variable_and_no_envelope():
    # The gate record's commit reaches the Node connector only from the admitted record, never from the workflow.
    for retired in ("secrets.", "vars.", "RELEASE_INPUTS_B64", "RELEASE_INPUTS_SHA256", "RELEASE_AUTHORIZED_SHA",
                    "RELEASE_GATE_SHA", "RELEASE_PACKET_SHA256", "RELEASE_BUDGET_LEDGER_SHA256", "RELEASE_CLEANUP_PERMIT",
                    "INITIALIZATION_RECEIPT_SHA256", "--prepare-", "--cleanup", "--initialize",
                    "--complete-initialization", "--dispose-initializer"):
        assert retired not in TEXT


def test_each_job_runs_exactly_its_reviewed_steps_in_order():
    setup = ["actions/checkout", "astral-sh/setup-uv", "uv sync --frozen"]
    assert shape("admission") == [*setup, ADMIT]
    # The pinned connector is installed before the gate, so no credential exists while npm runs.
    assert shape("release")[:-1] == [*setup, *NODE, READMIT, "google-github-actions/auth", DEPLOY,
                                     "actions/attest", "actions/upload-artifact"]
    assert "continue-on-error" not in TEXT


def test_the_admission_waits_for_the_five_checks_within_its_timeout_and_never_for_a_data_release():
    admission = JOBS["admission"]
    assert steps("admission")[-1]["run"] == ADMIT and "--plane data " in ADMIT
    # The gate refuses a longer wait, and the job must outlast the wait it asks for.
    assert admission["timeout-minutes"] == "60"
    assert WAIT_SECONDS <= release_gate.MAX_WAIT_SECONDS and WAIT_SECONDS < int(admission["timeout-minutes"]) * 60
    # Holding the mutation lock while waiting would stall every runtime release.
    assert "concurrency" not in admission


def test_the_release_re_admits_then_authenticates_with_the_gate_provider_and_its_fixed_identity():
    gate = index("release", lambda step: GATE in step.get("run", ""))
    auth = index("release", uses("google-github-actions/auth"))
    deploy = index("release", lambda step: "deploy_data.py" in step.get("run", ""))
    assert steps("release")[gate]["id"] == "admission" and steps("release")[gate]["run"] == READMIT
    assert gate < auth < deploy
    assert steps("release")[auth]["with"] == {"project_id": "specimen-digitization",
                                              "workload_identity_provider": "${{ steps.admission.outputs.provider }}",
                                              "service_account": IDENTITY}


def test_the_release_deploys_through_the_approved_entrypoint_and_exposes_its_phase_and_first_step():
    deploy = steps("release")[index("release", lambda step: "deploy_data.py" in step.get("run", ""))]
    assert deploy["id"] == "deploy" and deploy["run"] == DEPLOY and "if" not in deploy
    assert deploy["env"] == {"RELEASE_NODE_ROOT": "${{ runner.temp }}/firebase-release"}
    assert JOBS["release"]["outputs"] == {"phase": "${{ steps.deploy.outputs.phase }}",
                                          "init_step": "${{ steps.deploy.outputs.init_step }}"}
    # The pinned connector library is the only Firebase code the workflow installs; nothing deploys with a CLI.
    assert "gcloud" not in TEXT and re.sub(r"firebase-(tools@15\.8\.0|release)", "", TEXT).count("firebase") == 0


def test_the_receipt_is_attested_on_success_and_retained_on_every_exit():
    deploy = index("release", lambda step: step.get("id") == "deploy")
    attest = index("release", uses("actions/attest"))
    upload = index("release", uses("actions/upload-artifact"))
    assert deploy < attest < upload
    assert steps("release")[attest]["if"] == "success() && steps.deploy.outcome == 'success'"
    assert steps("release")[attest]["with"] == {"subject-path": RECEIPT}
    # A failed admission writes no receipt, so a missing file only warns.
    assert steps("release")[upload]["if"] == "always()"
    assert steps("release")[upload]["with"] == {"name": "data-receipt-${{ github.sha }}-${{ github.run_attempt }}",
                                                "path": RECEIPT, "if-no-files-found": "warn", "retention-days": "30"}


def test_the_initialize_phase_fails_the_run_closed_until_t3c(tmp_path):
    """The runtime's wait for this run (D3) must never pass over an uninitialized database."""
    final = steps("release")[-1]
    assert set(final) == {"name", "if", "run"}
    assert final["if"] == "steps.deploy.outputs.phase == 'initialize'"
    # GitHub runs a step's script with bash -eo pipefail.
    result = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", final["run"]], cwd=tmp_path,
                            env={"PATH": os.environ["PATH"]}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1
    assert "initialization arrives with T3c" in result.stdout


def test_the_release_job_shares_the_mutation_lock_with_the_runtime_release_only_at_job_level():
    assert JOBS["release"]["concurrency"] == LOCK
    runtime = yaml.load((ROOT / ".github/workflows/runtime-release.yml").read_text(), Loader=yaml.BaseLoader)
    assert runtime["jobs"]["release"]["concurrency"] == LOCK
    # The runtime admission waits for this run (D3); one workflow-level group for both would deadlock.
    assert runtime["concurrency"]["group"] != WORKFLOW["concurrency"]["group"]
