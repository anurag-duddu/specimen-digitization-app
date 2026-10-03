# Retired release scripts

The scripts in list 1 served the protected-release process of the data and
runtime releases: gate packets, admission, recovery windows, the restore clone
and the one-time database initializer. The owner's authorization of
2026-10-03 retired that process; the chapter "Data and runtime releases" in
`docs/DEPLOYMENT.md` quotes it and describes the current process.

- No workflow calls these scripts any more.
- They stay in the tree, byte for byte unchanged, until a follow-up pull
  request deletes them together with their tests. Some are pinned by digest:
  the plan templates under `infra/release/` hold their SHA-256 and tests
  compare it, so an edit fails CI.
- Do not extend them, and do not call or import them from new code. New
  release code goes in `scripts/release/` (run by the workflows) and
  `scripts/ops/` (run by the owner).

A name without a directory is a file in `scripts/ci/`. Every file in this
directory appears in exactly one of lists 1 to 4.

## 1. Retired scripts

Nothing that runs in a release calls these: no workflow, not the local gate,
no script under `scripts/release/` or `scripts/ops/`. No script in lists 3 and
4 loads one of them when it is imported.

- Release entry points: `deploy_data.py`, `deploy_runtime.py`
- Gate and packets: `release_gate.py`, `mint_release_packet.py`
- Google API transport of the gated release: `release_google.py`
- SQL apply, catalog and backup: `release_sql.mjs`, `release_sql_catalog.sql`,
  `release_sql_summary.sql`, `release_source_asset_unique.py`,
  `release_backup.py`
- One-time database initializer: `release_initialize.py`,
  `release_initialize.mjs`, `initialize_database.sql`,
  `initialize_postconditions.sql`, `initialize_catalog.sql`,
  `release_initializer_evidence.py`
- Restore clone: `release_clone.py`
- Image publication under a deadline: `release_publication_deadline.py`
- Owner-run helpers of the retired process: `data_setup_window.py`,
  `owner_gcloud.py`, `owner_grants.py`, `worker_trace_setup.py`. The standing
  grants now come from `scripts/ops/owner_setup.sh`.

Retired with them, outside this directory:
`.github/actions/runtime-publication/` (the action that ran
`release_publication_deadline.py`).

Two tests of the new code compare against a list 1 file, so the deletion pull
request handles them first. `scripts/release/test_simple_data_release.py`
reads `initialize_database.sql`. `scripts/ops/test_simple_owner_setup.py`
loads `owner_grants.py` and skips that comparison once the file is gone.
The policy test `tests/test_deployment_policy.py` reads list 1 from this file
and keeps `deploy_data.py` and `deploy_runtime.py` among its approved deploy
scripts while they exist, so the deletion pull request updates it too.

## 2. Tests of the retired scripts

These still run in CI (`uv run pytest -q` collects them) until the follow-up
pull request deletes them with list 1. Each one loads or reads a file from
list 1, or imports another test in this list. Two reach list 1 only through
`admit` (see list 4): `test_release_cost_ledger_v2.py` and
`test_release_verified_bytes.py`.

- Gate, admission inputs and packets: `test_release_gate.py`,
  `test_mint_release_packet.py`, `test_release_cost_ledger_v2.py`,
  `test_approved_release_budget.py`, `test_review_budget_projection.py`,
  `test_release_input_transport.py`, `test_release_verified_bytes.py`,
  `test_release_review_additional.py`, `test_release_review_boundaries.py`,
  `test_release_plan_templates.py`, `test_release_metadata_diagnostics.py`,
  `test_release_google.py`
- Data release: `test_data_apply.py`, `test_data_bootstrap.py`,
  `test_data_release.py`, `test_data_release_secrets.py`,
  `test_data_released_deploy.py`,
  `test_bootstrap_evidence.py`, `test_first_scope_bootstrap.py`,
  `test_catalog_diagnostics.py`, `test_persistent_data_readiness.py`,
  `test_release_missing_database.py`, `test_release_source_asset_unique.py`,
  `test_release_sql_catalog.py`, `test_source_asset_uniqueness.py`
- Initializer: `test_data_first_initialization.py`,
  `test_data_initialization.py`, `test_initialization_acl_postgres.py`,
  `test_initialization_catalog_privacy.py`,
  `test_initialization_placeholder.py`, `test_initialization_postgres.py`,
  `test_initializer_disposal.py`, `test_initializer_failure_evidence.py`,
  `test_initializer_iam_membership.py`, `test_initializer_user_readback.py`,
  `test_managed_cloudsql_database.py`
- Recovery window, clone and backup: `test_release_recovery_window.py`,
  `test_clone_allowance.py`, `test_finite_recovery_backup.py`
- Runtime release and image publication: `test_runtime_release.py`,
  `test_runtime_released_deploy.py`, `test_runtime_committed_tracing.py`,
  `test_runtime_registry_login.py`, `test_runtime_registry_refresh.py`,
  `test_approved_runtime_timing.py`, `test_approved_trace_binding.py`,
  `test_publication_action.py`, `test_publication_deadline.py`,
  `test_publication_docker.py`, `test_publication_launch_gate.py`,
  `test_publication_orchestration.py`, `test_publication_pinned_auth.py`,
  `test_publication_transport.py`
- Owner helpers: `test_data_setup_window.py`, `test_owner_grants.py`,
  `test_worker_trace_setup.py`

Their fixture: `fixtures/publication_auth_transport.cjs`.

Some of these tests also read the retired documents in list 5 and the plan
templates under `infra/release/`.

## 3. Still in use by CI and Hosting

Not retired.

- Called by `.github/workflows/ci-cd.yml`: `build_web.sh`,
  `validate_public_settings.py` (run by `build_web.sh`),
  `write_deployment_metadata.sh`, `smoke_web_routes.py`, `build_mobile.sh`,
  `deploy_hosting.sh`, `smoke_hosting.sh`
- The local gate: `verify.sh`, `check_ui_strings.py`,
  `ui_strings_baseline.txt`
- Called by `.github/workflows/runtime-ci.yml`: `build_runtime_image.sh`
  (also the build step of `.github/workflows/runtime-release.yml`),
  `smoke_runtime_inputs.py` (run by `build_runtime_image.sh`),
  `validate_release_packet.py`, `check_release_readiness.py`
- Their tests: `test_public_settings.py`, `test_smoke_web_routes.py`,
  `test_runtime_build_inputs.py`, `test_runtime_constructor_fixture.py`,
  `test_release_packet.py`, `test_release_readiness.py`

`validate_release_packet.py` and `check_release_readiness.py` check the
packet format of the retired process. They stay while
`.github/workflows/runtime-ci.yml` runs them.

## 4. Still loaded by the new release code

Not retired.

- Imported directly: `runtime_settings.py` (by
  `scripts/release/deploy_api.py`), `schema_gate.py` and
  `release_bootstrap.py` (by `scripts/release/data_release.py`)
- Loaded only because `release_bootstrap.py` imports them:
  `bootstrap_release.py`, `release_admission.py`,
  `release_catalog_envelope.py`, `release_context.py`,
  `release_diagnostics.py`, `release_recovery_window.py`, and the packet
  validator already in list 3. `bootstrap_release.py` in turn loads
  `scripts/data/bootstrap_admin.py`.
- Their tests: `test_schema_gate.py`, `test_legacy_import_proof_schema.py`,
  `test_bootstrap_release.py`, `test_release_admission.py`,
  `test_release_catalog_envelope.py`, `test_release_context.py`

The second group is code of the retired process, and some of it is pinned by
digest like list 1, so leave it unchanged too. The data release uses only the
row comparison and artifact validation in `release_bootstrap.py` and
`bootstrap_release.py`. Once those helpers move to `scripts/release/`, the
second group and `release_bootstrap.py` join list 1. Until then do not add
callers.

Three functions in the second group import a list 1 module when they are
called: `admit` in `release_admission.py`, `qualified_prior` in
`release_recovery_window.py` and `validate_evidence_recipient` in
`bootstrap_release.py`. The data release calls none of them.

## 5. Retired documents

These describe the retired process and are kept for history. Where one
conflicts with `docs/DEPLOYMENT.md`, `docs/DEPLOYMENT.md` wins.

- `docs/execution/RELEASE_AUTHORIZATION.md`
- `docs/execution/golive/RELEASE.md`
- `docs/execution/golive/briefs/S2-release-planes.md`
- `docs/execution/RELEASING.md`
- `docs/execution/RELEASE_DATA.md`
- `docs/execution/RELEASE_RUNTIME.md`
- `docs/execution/PROTECTED_RELEASE_HARNESS.md`
- `docs/execution/DATABASE_INITIALIZATION.md`
- `docs/execution/CLONE_ALLOWANCE.md`
- `docs/execution/FINITE_RECOVERY_BACKUP.md`
- `docs/execution/RELEASE_INPUT_TRANSPORT.md`
- `docs/execution/CATALOG_DIAGNOSTICS.md`
- `docs/execution/GO_LIVE_RUNBOOK.md`
- `docs/execution/CURRENT_RELEASE_CHECKLIST.md`
- `docs/execution/PRODUCTION_RELEASE_PLAN.md`
- `docs/execution/GO_LIVE_READINESS.md`
- `infra/release/OWNER_INPUTS.md`
