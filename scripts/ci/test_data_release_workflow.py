"""Shape of the automatic data release workflow (RELEASE.md sections 4.2 and 4.3); no network."""
import json
from pathlib import Path
import re

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
INITIALIZER = "specimen-data-initialize@specimen-digitization.iam.gserviceaccount.com"
INTENT = "${{ runner.temp }}/data-release/initializer-create-specimen-digitization-instance.json"
CREDENTIALED = ("release", "initialize", "dispose-initializer", "migrate")
INITIALIZED = "${{ runner.temp }}/data-initialized.json"
NODE_ENV = {"RELEASE_NODE_ROOT": "${{ runner.temp }}/firebase-release"}
# RELEASE.md 4.5: the owner's data-production secrets for the bootstrap run, and only those.
BOOTSTRAP = ("DATA_BOOTSTRAP_ARTIFACT_B64", "DATA_BOOTSTRAP_APPROVED_SHA256")
DEPLOY_ENV = {**NODE_ENV, **{name: "${{ secrets.%s }}" % name for name in BOOTSTRAP}}
EVIDENCE = "${{ runner.temp }}/data-release/*.encrypted.json"


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
    assert all(job["if"].removeprefix("always() && ").startswith(MAIN_PUSH) for job in JOBS.values())


def test_a_credential_free_admission_precedes_the_release_and_hands_it_nothing():
    assert list(JOBS) == ["admission", "release", "initialize", "dispose-initializer", "migrate"]
    assert "needs" not in JOBS["admission"] and JOBS["release"]["needs"] == "admission"
    # The release job re-admits on its own; no admission output can steer it.
    assert "outputs" not in JOBS["admission"]
    for job in (JOBS["admission"], JOBS["release"], JOBS["dispose-initializer"], JOBS["migrate"]):
        assert job["environment"] == "data-production"
        assert job["env"] == {"GH_TOKEN": "${{ github.token }}", "DEPLOYMENT_ENVIRONMENT": "data-production",
                              "RELEASE_PROJECT": "specimen-digitization", "RELEASE_SERVICE_ACCOUNT": IDENTITY}


def test_the_initializer_runs_once_after_step_one_in_its_own_environment_and_disposal_follows_whenever_it_ran():
    initialize, dispose = JOBS["initialize"], JOBS["dispose-initializer"]
    assert initialize["needs"] == "release" and initialize["environment"] == "data-initialization-production"
    assert initialize["if"] == f"{MAIN_PUSH} && needs.release.outputs.init_step == 'initialize'"
    assert initialize["env"] == {"GH_TOKEN": "${{ github.token }}", "DEPLOYMENT_ENVIRONMENT": "data-initialization-production",
                                 "RELEASE_PROJECT": "specimen-digitization", "RELEASE_SERVICE_ACCOUNT": INITIALIZER}
    auth = {job: steps(job)[index(job, uses("google-github-actions/auth"))]["with"] for job in CREDENTIALED}
    assert auth["initialize"] == {**auth["release"], "service_account": INITIALIZER}
    assert auth["dispose-initializer"] == auth["migrate"] == auth["release"]
    assert dispose["needs"] == ["release", "initialize"]
    assert dispose["if"] == f"always() && {MAIN_PUSH} && needs.initialize.result != 'skipped'"


def test_only_the_jobs_that_use_credentials_can_obtain_a_token_and_only_publishers_sign():
    assert JOBS["admission"]["permissions"] == READ
    assert JOBS["release"]["permissions"] == JOBS["initialize"]["permissions"] == JOBS["migrate"]["permissions"] == {
        **READ, "id-token": "write", "attestations": "write"}
    assert JOBS["dispose-initializer"]["permissions"] == {**READ, "id-token": "write", "attestations": "read"}


def test_every_action_is_pinned_to_a_full_commit_sha():
    assert not any("uses" in job for job in JOBS.values())
    actions = [step["uses"] for job in JOBS.values() for step in job["steps"] if "uses" in step]
    assert actions and all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", action) for action in actions)


def test_the_workflow_reads_no_variable_and_no_envelope():
    # The gate record's commit reaches the Node connector only from the admitted record, never from the workflow.
    for retired in ("vars.", "RELEASE_INPUTS_B64", "RELEASE_INPUTS_SHA256", "RELEASE_AUTHORIZED_SHA",
                    "RELEASE_GATE_SHA", "RELEASE_PACKET_SHA256", "RELEASE_BUDGET_LEDGER_SHA256", "RELEASE_CLEANUP_PERMIT",
                    "INITIALIZATION_RECEIPT_SHA256", "--prepare-inputs", "--prepare-cleanup", "--prepare-initialization",
                    "--prepare-clone-intent", "--cleanup", "--complete-initialization", "--receipt"):
        assert retired not in TEXT


def test_each_job_runs_exactly_its_reviewed_steps_in_order():
    setup = ["actions/checkout", "astral-sh/setup-uv", "uv sync --frozen"]
    data = f"uv run python scripts/ci/deploy_data.py --%s --packet {PACKET}"
    assert shape("admission") == [*setup, ADMIT]
    # The pinned connector is installed before the gate, so no credential exists while npm runs.
    assert shape("release") == [*setup, *NODE, READMIT, "google-github-actions/auth", DEPLOY,
                                "actions/attest", "actions/upload-artifact", "actions/attest", "actions/upload-artifact"]
    # The creation intent is signed and published before the step that can create the principal.
    assert shape("initialize") == [*setup, *NODE, f"{GATE}-initialization --output {PACKET}", "google-github-actions/auth",
                                   data % "prepare-initializer-intents", "actions/attest", "actions/upload-artifact",
                                   data % "initialize" + ' --output "$RUNNER_TEMP/data-initializer.json"',
                                   "actions/attest", "actions/upload-artifact"]
    assert shape("dispose-initializer") == [*setup, *NODE, READMIT, "google-github-actions/auth", data % "dispose-initializer"]
    assert shape("migrate") == [*setup, *NODE, READMIT, "google-github-actions/auth",
                                data % "migrate" + ' --output "$RUNNER_TEMP/data-initialized.json"',
                                "actions/attest", "actions/upload-artifact"]
    assert "continue-on-error" not in TEXT


def test_the_intent_and_the_receipt_carry_this_attempt_and_the_receipt_is_signed_on_success_only():
    """Step one's re-run check reads data-initializer-<commit>-<attempt>; disposal reads the latest intent."""
    signed, published, receipt, retained = (step for step in steps("initialize") if "uses" in step
                                            and step["uses"].startswith(("actions/attest@", "actions/upload-artifact@")))
    assert signed["with"] == {"subject-path": INTENT} and receipt["with"] == {"subject-path": "${{ runner.temp }}/data-initializer.json"}
    for artifact, prefix, path in ((published, "initializer-intent", INTENT),
                                   (retained, "data-initializer", "${{ runner.temp }}/data-initializer.json")):
        assert artifact["with"] == {"name": prefix + "-${{ github.sha }}-${{ github.run_attempt }}", "path": path,
                                    "if-no-files-found": "error", "retention-days": "30"}
    assert not any("if" in step for step in steps("initialize"))
    for job in CREDENTIALED:
        native = [step for step in steps(job) if "deploy_data.py" in step.get("run", "") and "--prepare-" not in step["run"]]
        assert len(native) == 1 and native[0]["env"] == (DEPLOY_ENV if job == "release" else NODE_ENV)


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
    assert deploy["env"] == DEPLOY_ENV
    assert JOBS["release"]["outputs"] == {"phase": "${{ steps.deploy.outputs.phase }}",
                                          "init_step": "${{ steps.deploy.outputs.init_step }}"}
    # The pinned connector library is the only Firebase code the workflow installs; nothing deploys with a CLI.
    assert "gcloud" not in TEXT and re.sub(r"firebase-(tools@15\.8\.0|release)", "", TEXT).count("firebase") == 0


def test_the_release_job_outlasts_the_gate_records_window_so_that_deadline_ends_every_wait():
    """RELEASE.md 4.4: the backup, the migration, and the first apply's clone restore and deletion all wait within the
    gate record's hour, which the re-admission step starts; the job keeps ten minutes for its setup and its receipt."""
    assert JOBS["release"]["timeout-minutes"] == "75"
    assert release_gate.WINDOW_SECONDS + 600 <= int(JOBS["release"]["timeout-minutes"]) * 60


def test_the_deployment_contract_describes_the_apply_and_the_checks_the_release_job_runs():
    section = (ROOT / "docs/DEPLOYMENT.md").read_text().split("## Data release on merge (go-live program)")[1].split("\n## ")[0]
    release = section.split("2. **Release**")[1].split("\n3. ")[0]
    assert "fails closed until T3d" not in release and "until its restore check lands" not in release
    for fact in ("catalog", "supplemental index inventory", "`apply`", "`source-sha`", "point-in-time recovery", "7 days",
                 "`firebaseowner`", "`COMPATIBLE`", "first apply", "`first-production-restore.json`", "create-only",
                 "`specimen-digitization-restore-20260908-r1`", "deletes"):
        assert fact in release, fact


def test_the_receipt_is_attested_and_retained_on_every_exit():
    deploy = index("release", lambda step: step.get("id") == "deploy")
    attest = index("release", lambda step: uses("actions/attest")(step) and step["with"]["subject-path"] == RECEIPT)
    upload = index("release", lambda step: uses("actions/upload-artifact")(step) and step["with"]["path"] == RECEIPT)
    assert deploy < attest < upload
    # Every exit: a later attempt reads a failed first apply's restore check (RELEASE.md 4.4, the coordinator's ruling).
    assert steps("release")[attest]["if"] == "always() && steps.deploy.outcome != 'skipped'"
    assert steps("release")[attest]["with"] == {"subject-path": RECEIPT}
    # A failed admission writes no receipt, so a missing file only warns.
    assert steps("release")[upload]["if"] == "always()"
    assert steps("release")[upload]["with"] == {"name": "data-receipt-${{ github.sha }}-${{ github.run_attempt }}",
                                                "path": RECEIPT, "if-no-files-found": "warn", "retention-days": "30"}


def test_the_migration_runs_after_a_successful_disposal_or_this_runs_earlier_initializer_and_signs_its_receipt():
    """RELEASE.md 4.3, Jobs: the migrate job re-admits, then runs steps 3 to 5 as specimen-data-release."""
    job = JOBS["migrate"]
    assert job["needs"] == ["release", "initialize", "dispose-initializer"] and job["environment"] == "data-production"
    assert job["if"] == (f"always() && {MAIN_PUSH} && needs.release.outputs.phase == 'initialize' && (needs.dispose-initializer"
                         ".result == 'success' || needs.release.outputs.init_step == 'migrate')")
    gate, auth = index("migrate", lambda step: GATE in step.get("run", "")), index("migrate", uses("google-github-actions/auth"))
    migrate = index("migrate", lambda step: "deploy_data.py" in step.get("run", ""))
    attest, upload = index("migrate", uses("actions/attest")), index("migrate", uses("actions/upload-artifact"))
    assert steps("migrate")[gate]["id"] == "admission" and gate < auth < migrate < attest < upload
    assert steps("migrate")[migrate]["id"] == "migrate" and "if" not in steps("migrate")[migrate]
    assert steps("migrate")[attest] == {"name": steps("migrate")[attest]["name"], "if": "success() && steps.migrate.outcome == 'success'",
                                        "uses": steps("migrate")[attest]["uses"], "with": {"subject-path": INITIALIZED}}
    assert steps("migrate")[upload]["if"] == "always()" and steps("migrate")[upload]["with"] == {
        "name": "data-initialized-${{ github.sha }}-${{ github.run_attempt }}", "path": INITIALIZED,
        "if-no-files-found": "warn", "retention-days": "30"}
    assert not any("exit 1" in step.get("run", "") for name in JOBS for step in steps(name))


def test_the_deployment_contract_describes_the_migration_the_workflow_runs():
    section = (ROOT / "docs/DEPLOYMENT.md").read_text().split("## Data release on merge (go-live program)")[1].split("\n## ")[0]
    migrate = section.split("5. **Migrate**")[1].split("\n\n")[0]
    assert "T3c2" not in section and "MIGRATE_COMPATIBLE" in migrate and "data-initialized/v1" in migrate
    for fact in ("`data-production`", "`specimen-data-release`", "validate-only", "`COMPATIBLE`", "one transaction",
                 "`firebaseowner`", "etag", "supplemental indexes", "connector", "Storage rules", "catalog"):
        assert fact in migrate, fact
    assert "The release, initialize and migrate jobs share the `specimen-protected-mutation`" in section


def test_every_job_that_changes_data_holds_the_mutation_lock_the_runtime_release_shares_only_at_job_level():
    assert all(JOBS[job]["concurrency"] == LOCK for job in ("release", "initialize", "migrate"))
    # GitHub replaces a pending job in a concurrency group, so a queued disposal could be cancelled and leave the
    # principal behind. It only removes this run's own principal, so it never waits for the lock.
    assert "concurrency" not in JOBS["dispose-initializer"]
    runtime = yaml.load((ROOT / ".github/workflows/runtime-release.yml").read_text(), Loader=yaml.BaseLoader)
    assert runtime["jobs"]["release"]["concurrency"] == LOCK
    # The runtime admission waits for this run (D3); one workflow-level group for both would deadlock.
    assert runtime["concurrency"]["group"] != WORKFLOW["concurrency"]["group"]


def test_the_bootstrap_secrets_reach_only_the_release_step_as_environment_variables_and_nothing_echoes_them():
    """RELEASE.md 4.5: the owner sets them for the bootstrap run; unset, each arrives empty and the bootstrap is skipped."""
    deploy = steps("release")[index("release", lambda step: step.get("id") == "deploy")]
    assert deploy["env"] == DEPLOY_ENV and deploy["run"] == DEPLOY
    # Each is named exactly once in the whole workflow: in that step's env, which no job-level env repeats.
    assert re.findall(r"secrets\.(\w+)", TEXT) == list(BOOTSTRAP)
    assert all(not any(name in json.dumps(job.get("env", {})) for name in BOOTSTRAP) for job in JOBS.values())
    # No step's command, input or condition names or prints one.
    for job in JOBS.values():
        for step in job["steps"]:
            visible = json.dumps({key: value for key, value in step.items() if key != "env"})
            assert not any(name in visible for name in BOOTSTRAP) and "secrets." not in visible
            assert not re.search(r"\b(echo|printf|printenv|env|set -x)\b", step.get("run", ""))


def test_the_encrypted_bootstrap_evidence_is_attested_and_retained_whenever_the_release_wrote_it():
    """RELEASE.md 4.5: the private records stay encrypted to the committed recipient; only their encrypted copies are
    attested and uploaded, a failed write's included, and only when deploy_data.py reports that it wrote them."""
    receipt = index("release", lambda step: uses("actions/upload-artifact")(step) and step["with"]["path"] == RECEIPT)
    attest = index("release", lambda step: uses("actions/attest")(step) and step["with"]["subject-path"] == EVIDENCE)
    upload = index("release", lambda step: uses("actions/upload-artifact")(step) and step["with"]["path"] == EVIDENCE)
    assert receipt < attest < upload
    for position in (attest, upload):
        assert steps("release")[position]["if"] == "always() && steps.deploy.outputs.evidence == 'present'"
    assert steps("release")[upload]["with"] == {
        "name": "encrypted-bootstrap-evidence-${{ github.sha }}-${{ github.run_attempt }}", "path": EVIDENCE,
        "if-no-files-found": "error", "retention-days": "30"}
    # The raw records beside them never match an upload path: from the packet's directory, only encrypted copies and the
    # initializer's signed intent leave the runner.
    uploaded = [step["with"]["path"] for name in JOBS for step in steps(name) if uses("actions/upload-artifact")(step)]
    assert sorted(path for path in uploaded if "data-release/" in path) == sorted([INTENT, EVIDENCE])


def test_the_deployment_contract_describes_the_bootstrap_the_release_job_runs():
    section = (ROOT / "docs/DEPLOYMENT.md").read_text().split("## Data release on merge (go-live program)")[1].split("\n## ")[0]
    release = " ".join(section.split("2. **Release**")[1].split("\n3. ")[0].split())
    for fact in ("`DATA_BOOTSTRAP_ARTIFACT_B64`", "`DATA_BOOTSTRAP_APPROVED_SHA256`", "`verify`", "`apply`",
                 "`initialize`", "unread", "`tree_sha256`", "backup", "read first", "skips", "fails",
                 "`infra/release/evidence-recipient.pub`", "encrypted", "`specimenDataOwnerBootstrap`"):
        assert fact in release, fact
    assert "reads no secret" not in " ".join(section.split())
    assert "only the bootstrap's `data-production` secrets" in " ".join(section.split())
