"""Shape of the automatic runtime release workflow (RELEASE.md section 3.3); no network."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / ".github/workflows/runtime-release.yml").read_text()
WORKFLOW = yaml.load(TEXT, Loader=yaml.BaseLoader)
JOBS = WORKFLOW["jobs"]
GATE = "uv run python scripts/ci/release_gate.py"


def steps(job):
    return JOBS[job]["steps"]


def index(job, predicate):
    matches = [i for i, step in enumerate(steps(job)) if predicate(step)]
    assert len(matches) == 1, f"{job}: expected exactly one matching step"
    return matches[0]


def test_the_runtime_workflow_reads_no_envelope_secret_or_variable():
    for retired in ("RELEASE_INPUTS_B64", "RELEASE_INPUTS_SHA256", "RELEASE_AUTHORIZED_SHA", "RELEASE_BUDGET_LEDGER_SHA256",
                    "RELEASE_HUMAN_REVIEW_AUTHORIZATION_SHA256", "--prepare-inputs", "vars.", "secrets."):
        assert retired not in TEXT


def test_the_admission_waits_for_the_checks_and_the_data_release_without_credentials():
    admission = JOBS["admission"]
    assert "id-token" not in admission["permissions"]
    gate = steps("admission")[index("admission", lambda s: GATE in s.get("run", ""))]["run"]
    assert "--plane runtime " in gate and "--wait-seconds 5400" in gate
    assert int(admission["timeout-minutes"]) > 90


def test_every_credentialed_job_runs_the_gate_for_its_own_plane_before_any_credential():
    planes = {"build": ("runtime-build", lambda s: s.get("uses") == "./.github/actions/runtime-publication"),
              "release": ("runtime", lambda s: s.get("uses", "").startswith("google-github-actions/auth@"))}
    for job, (plane, credential) in planes.items():
        gate = index(job, lambda s: GATE in s.get("run", ""))
        assert f"--plane {plane} " in steps(job)[gate]["run"] and "--wait-seconds" not in steps(job)[gate]["run"]
        assert steps(job)[gate].get("id") == "admission"
        assert gate < index(job, credential)
        assert JOBS[job]["needs"]


def test_the_releaser_authenticates_with_the_gate_provider_and_its_fixed_identity():
    auth = steps("release")[index("release", lambda s: s.get("uses", "").startswith("google-github-actions/auth@"))]["with"]
    assert auth["workload_identity_provider"] == "${{ steps.admission.outputs.provider }}"
    assert auth["service_account"] == "specimen-runtime-release@specimen-digitization.iam.gserviceaccount.com"
    assert JOBS["release"]["concurrency"]["cancel-in-progress"] == "false"


def test_the_workflow_deploys_through_the_approved_entrypoint_and_never_runs_the_worker():
    deploy = steps("release")[index("release", lambda s: "deploy_runtime.py" in s.get("run", ""))]["run"]
    assert "--deploy" in deploy and "--receipts" in deploy
    assert ":run" not in TEXT and "jobs run" not in TEXT and "gcloud" not in TEXT
