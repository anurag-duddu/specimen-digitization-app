# CI/CD and production deployment contract

This document is the authoritative release runbook for Specimen Digitization.
It applies to humans, automation, agents, every branch, every worktree, and every
Codex session. `AGENTS.md` points all sessions here.

The governing rule is simple:

> Production changes reach Firebase Hosting only through the repository's
> GitHub Actions workflow after a pull request is merged to `main`.

Do not perform a hand deployment because it appears faster, because CI is
blocked, or because a local build succeeds. Fix the gate or report the blocker.

## Project facts

| Item | Required value |
|---|---|
| Product name | Specimen Digitization |
| GitHub repository | `anurag-duddu/specimen-digitization-app` |
| Protected production branch | `main` |
| Firebase and Google Cloud project | `specimen-digitization` |
| Firebase Hosting site | `specimen-digitization` |
| Production URL | <https://specimen-digitization.web.app> |
| Workflow | `.github/workflows/ci-cd.yml` |
| Approved runtime workflow | `.github/workflows/runtime-release.yml` |
| Approved data workflow | `.github/workflows/data-release.yml` |
| GitHub environment | `production`, branch policy `main` only |
| Deployment service account | `github-firebase-hosting@specimen-digitization.iam.gserviceaccount.com` |
| Firebase CLI in CI | `15.8.0` |
| Flutter in CI | `3.38.5` |
| uv in CI | `0.12.5` |
| Python in CI | `3.12` |

Firebase SQL Connect backed by Cloud SQL for PostgreSQL is the application
database direction. Firestore is not the application database. The current
Hosting pipeline deploys only the static Flutter web artifact to Firebase Hosting; it
does not deploy or migrate SQL Connect, Cloud SQL, Storage, Functions, Cloud
Run, Temporal, or model workers. The separately approved runtime/data paths
below do not change that Hosting boundary. AWS is not part of this design.

## Non-negotiable rules

1. Start from an up-to-date `main` and work on a short-lived branch.
2. Run `scripts/ci/verify.sh` before pushing.
3. Push the branch and open a pull request. Do not push a release directly to
   `main`.
4. Required pull-request checks must pass on the exact candidate commit.
5. Merge through GitHub. A merge to `main` is the only production trigger.
6. Do not run `firebase deploy`, `firebase hosting:channel:deploy`, or a
   `gcloud ... deploy` command from a workstation, agent shell, or ad hoc job.
7. Do not change a failed check, branch protection, the `production`
   environment, IAM, Workload Identity Federation, pinned action SHA, test, or
   smoke assertion merely to make a release pass.
8. Do not give the Hosting deploy service account database, Storage, Functions, Cloud
   Run, Secret Manager administration, Owner, or Editor permissions.
9. Never create or store a Google service-account JSON key. CI uses short-lived
   GitHub OIDC credentials through Workload Identity Federation.
10. Never put `.env`, FlutterFire generated production files, provider keys,
    museum data, or Google credentials in Git.
11. A release is complete only after the `main` workflow is green and the
    public site reports the exact merged commit SHA in `/deployment.json`.
12. If any required proof is unavailable, report the release as incomplete.

The only executable Hosting deploy command lives in
`scripts/ci/deploy_hosting.sh`. That script fails closed unless GitHub provides
the expected repository, `push` event, `main` ref, workflow identity, commit
SHA, tested artifact marker, and keyless Google credential file. Tests reject
deploy commands added to unapproved automation files. The only approved backend
effect entrypoints are `scripts/ci/deploy_runtime.py` and
`scripts/ci/deploy_data.py`, invoked exclusively by their respective main-push
workflows under the admission and verification contract below. A policy
allowlist is not evidence that an entrypoint or its live inputs are ready.

## Pipeline behavior

### Pull requests

`.github/workflows/ci-cd.yml` runs the three existing protected checks and two native build matrix entries:

| Required check | What it proves |
|---|---|
| `Repository checks` | Sensitive-file policy, secret scans, formatting, YAML/JSON/TOML validity, shell checks, and GitHub Actions syntax |
| `Python tests` | Locked Python environment and all backend/policy tests |
| `Flutter checks and web build` | Locked Flutter dependencies, static analysis, widget tests, release build, and immutable deployment metadata |

Pull requests use `apps/specimen_digitization/lib/firebase_options.ci.dart`.
They receive neither the real FlutterFire configuration nor a Google OIDC
token and cannot deploy.

### Pushes to `main`

The same five checks run again for the actual merged commit. The Flutter job
restores the encrypted production FlutterFire configuration, builds once, adds
`deployment.json`, and uploads the artifact. `Deploy Firebase Hosting` then:

1. waits for every required job;
2. downloads that exact tested artifact instead of rebuilding;
3. enters the GitHub `production` environment;
4. obtains a short-lived Google credential through OIDC;
5. runs the guarded Hosting-only deploy script;
6. verifies the page title and the public deployment marker's repository and
   exact commit SHA.

Deploy concurrency is one-at-a-time and is never cancelled mid-deploy. Pull
request runs can be cancelled when superseded.

### Manual workflow runs

`workflow_dispatch` intentionally runs CI only. It cannot deploy. Do not change
manual dispatch into a production trigger. A replay of a failed production job
must retain its original `push` event and merged `main` commit.

## Authentication and secrets

GitHub Actions authenticates with Workload Identity Federation. The Google
provider must accept only:

- repository ID `1360732425`;
- repository owner ID `140138196`;
- event `push`;
- ref `refs/heads/main`;
- environment `production`; and
- workflow ref
  `anurag-duddu/specimen-digitization-app/.github/workflows/ci-cd.yml@refs/heads/main`.

The deploy service account has only:

- `roles/firebasehosting.admin`; and
- `roles/serviceusage.apiKeysViewer`, required by Firebase CLI project checks.

The repository secret `FIREBASE_OPTIONS_DART_B64` contains the generated
FlutterFire client configuration as one base64 line. Firebase client
configuration identifies an app; it is not an administrative credential.
Nevertheless, the generated file remains ignored and the production value is
not exposed to pull requests.

Never store a service-account key in GitHub. `gha-creds-*.json` is ignored as a
defense in depth because the Google authentication action creates an ephemeral
credential file during a job.

### Rotating FlutterFire client configuration

This is configuration maintenance, not a deployment. It requires explicit
authorization and must be followed by a normal pull request/merge release:

```bash
cd apps/specimen_digitization
flutterfire configure \
  --project specimen-digitization \
  --platforms android,ios,web
base64 < lib/firebase_options.dart | tr -d '\n' \
  | gh secret set FIREBASE_OPTIONS_DART_B64 \
      --repo anurag-duddu/specimen-digitization-app
```

Confirm only secret metadata, never print or decode the secret in logs:

```bash
gh secret list --repo anurag-duddu/specimen-digitization-app
```

## Required local tools

- Git and GitHub CLI authenticated for this repository
- Flutter `3.38.5` with Dart `3.10.4`
- uv `0.12.5`
- Firebase CLI `15.8.0` for local emulator/configuration inspection only
- Java only when running a Firebase emulator that requires it, such as Storage;
  Java is not part of the Hosting deploy

Check the release-critical versions:

```bash
git --version
gh --version
flutter --version
uv --version
firebase --version
```

Install repository hooks once per clone:

```bash
uvx --from pre-commit==4.5.1 pre-commit install \
  --hook-type pre-commit \
  --hook-type pre-push
```

## Script and command catalog

Run commands from the repository root unless a different directory is shown.

### Full required pre-push verification

```bash
scripts/ci/verify.sh
```

This is the canonical local gate. It runs repository hooks, secret scanning,
actionlint, shellcheck, locked Python installation, Python tests, Flutter
dependency resolution, Flutter analysis, Flutter tests, and the release web
build. If the local ignored production FlutterFire file is absent, it uses and
then removes the credential-free CI placeholder. It never deploys.

### Repository and secret checks only

```bash
uvx --from pre-commit==4.5.1 pre-commit run --all-files
```

Some hooks can normalize whitespace or final newlines. Review any resulting
diff, rerun until green, and commit the normalization with the affected change.

### Python backend

```bash
uv sync --frozen
uv run pytest -q
```

Optional, non-production observability smoke using only the deterministic test
model:

```bash
uv run specimen-logfire-smoke
```

Optional Hugging Face access and routing preflight; its default path is
non-paid and does not submit an image:

```bash
uv run --env-file .env specimen-huggingface-preflight
```

Paid live-route calls require explicit approval and an approved synthetic or
public image. Never use private specimen material for a smoke test.

These optional smoke commands are distinct from the user-authorized first-ten
application pilot. The pilot requires its privately frozen originals, pinned
provider routes, verified identity/data/runtime prerequisites and the shared
USD 5 reservation ledger. It is never run inside ordinary pull-request CI.

### Flutter client

```bash
cd apps/specimen_digitization
flutter pub get --enforce-lockfile
flutter analyze --fatal-infos
flutter test
flutter build web --release
```

For local development only:

```bash
cd apps/specimen_digitization
flutter run
```

### Firebase emulators

Emulators are local tools and are not a release path:

```bash
firebase emulators:start --only auth,dataconnect,storage
```

Storage emulation may require a JDK. Do not add Java to the Hosting workflow.
Do not treat emulator success as proof of Cloud SQL migration safety or
production behavior.

### Deployment-only scripts

These are called by `.github/workflows/ci-cd.yml`; do not invoke or imitate
them as a hand-deployment process:

| Script | Purpose | Invocation policy |
|---|---|---|
| `scripts/ci/write_deployment_metadata.sh` | Adds repository, SHA, run, and build-time evidence to the tested artifact | GitHub Actions only |
| `scripts/ci/deploy_hosting.sh` | Validates CI identity and deploys only Hosting | GitHub Actions `push` to `main` only |
| `scripts/ci/smoke_hosting.sh` | Confirms title and exact public commit marker | Workflow-required; local read-only diagnosis is allowed |

A read-only production recheck is allowed when investigating status:

```bash
scripts/ci/smoke_hosting.sh \
  https://specimen-digitization.web.app \
  EXPECTED_40_CHARACTER_MERGE_SHA
```

## Standard change and release procedure

### 1. Synchronize safely

Do not discard a dirty tree. First inspect it and preserve work that belongs to
another task:

```bash
git status --short --branch
git fetch origin
git log --oneline --decorate --graph --all -20
```

Start or continue a short-lived branch from the intended base. Use a descriptive
name such as `codex/short-purpose`; never do release work directly on `main`.

### 2. Implement and inspect

Keep generated secrets and build products out of Git. Review both tracked and
untracked files:

```bash
git status --short
git diff --check
git diff
git ls-files --others --exclude-standard
```

Changes to the following are release-sensitive and require deliberate review:

- `.github/workflows/**`
- `scripts/ci/**`
- `firebase.json` and `.firebaserc`
- `.gitignore` and `.pre-commit-config.yaml`
- `apps/specimen_digitization/pubspec.lock`
- `uv.lock`
- SQL Connect schemas, connectors, operations, or generated SDKs
- IAM, Workload Identity Federation, GitHub environment, secret, or branch
  protection settings

### 3. Run local gates

```bash
scripts/ci/verify.sh
git diff --check
git status --short
```

Do not commit until all intended files are understood and no sensitive file is
present.

### 4. Commit and push the branch

Stage only the intended files. Never use staging as a substitute for reviewing
the diff.

```bash
git add PATHS_YOU_REVIEWED
git diff --cached --check
git diff --cached
git commit -m "TYPE: concise description"
git push -u origin YOUR_BRANCH
```

### 5. Open a pull request and wait for CI

```bash
gh pr create --fill
gh pr checks --watch
```

Required checks are `Repository checks`, `Python tests`, and
`Flutter checks and web build`. Inspect failures; do not rerun blindly or alter
a gate. Confirm the passing checks belong to the latest PR head SHA.

### 6. Merge and prune

Merge only after required checks pass and conversations are resolved:

```bash
gh pr merge --merge --delete-branch
git switch main
git pull --ff-only origin main
git fetch --prune origin
git branch -d YOUR_BRANCH
```

If GitHub already removed the local or remote branch, treat the corresponding
delete message as informational. Never force-delete a branch whose merge is not
confirmed.

### 7. Follow the production run through completion

Find the workflow for the merged commit and watch it:

```bash
git rev-parse HEAD
gh run list --workflow "CI/CD" --branch main --limit 5
gh run watch RUN_ID --exit-status
gh run view RUN_ID
```

The run must show the exact merged commit and all six job results green, including
`Deploy Firebase Hosting`. Then independently re-run the public marker smoke:

```bash
scripts/ci/smoke_hosting.sh \
  https://specimen-digitization.web.app \
  "$(git rev-parse HEAD)"
```

Record the merge SHA, pull-request URL, workflow-run URL, deploy-job result,
public URL, and smoke result in the task handoff. Only then call the deployment
successful.

## Branch and repository protection

`main` must have all of the following protections:

- changes require a pull request;
- required status checks are strict and include the three CI checks above;
- conversations must be resolved;
- force pushes and branch deletion are disabled;
- administrators are subject to the rules;
- the branch must be up to date before merge.

The GitHub `production` environment must accept deployments only from `main`.
GitHub Actions' default token permission must remain read-only; only the deploy
job receives `id-token: write`. Third-party actions remain pinned to immutable
commit SHAs.

Changing these protections is a security-sensitive administrative operation,
not a troubleshooting technique. Document and obtain explicit approval before
weakening them.

## Things to watch

- **Wrong Firebase project:** both `.firebaserc`, `firebase.json`, the deploy
  script, OIDC identity, and public URL must say `specimen-digitization`.
- **Untested rebuild:** deployment must consume the artifact uploaded by the
  Flutter job. Never rebuild in the deploy job.
- **Broadened Firebase target:** `--only hosting` is mandatory. A bare
  `firebase deploy` can deploy unrelated resources and is forbidden.
- **Secret exposure on pull requests:** production FlutterFire configuration
  and OIDC permissions belong only to the `main` deploy path.
- **Stale or wrong artifact:** `/deployment.json` must equal the exact workflow
  SHA; an HTTP 200 or page title alone is insufficient.
- **CDN caching:** `deployment.json` is served with `Cache-Control: no-store`,
  and smoke requests use cache-busting query parameters.
- **Concurrent releases:** never cancel an in-progress production deployment.
  The production concurrency group serializes them.
- **Dependency drift:** lockfiles must be committed; CI installs with
  `uv sync --frozen` and `flutter pub get --enforce-lockfile`.
- **Action supply chain:** keep actions SHA-pinned. Validate intentional action
  upgrades with actionlint and review the upstream release/tag-to-SHA mapping.
- **Generated Firebase files:** `firebase_options.dart`, `google-services.json`,
  and `GoogleService-Info.plist` are ignored. Commit only the explicit
  credential-free CI placeholder.
- **SQL safety:** Hosting success says nothing about SQL Connect or Cloud SQL.
  Define a separate reviewed migration workflow before any production schema
  change. Never make Flutter connect directly to PostgreSQL.
- **Java confusion:** Java may be needed for an emulator or Android tooling; it
  is not a Hosting runtime or deployment requirement.
- **Provider costs and data policy:** model preflights are separate from the
  release gate. Do not add paid calls or museum images to CI.
- **AWS scope:** do not add AWS credentials, deployment steps, or infrastructure
  unless the project owner explicitly changes the architecture.

## Failure handling

### Pull-request CI fails

Inspect the failed job and reproduce its exact command locally. Fix the cause
on the branch, rerun `scripts/ci/verify.sh`, push, and wait for the new head SHA.
Do not merge with a missing, skipped, neutral, stale, or cancelled required
check.

### Main CI fails before deployment

Production was not changed. Create a repair branch from the failing merge,
revert or fix through a pull request, and let the normal pipeline run.

### Deployment or public smoke fails

1. Do not start a hand deploy.
2. Capture the run ID, merge SHA, deploy logs, current public marker, and HTTP
   symptoms.
3. Stop additional merges until the deployment state is understood.
4. Prefer a normal revert/fix pull request followed by the same pipeline.
5. If the public site is materially broken and waiting for CI is unsafe, an
   emergency Firebase Hosting rollback requires explicit project-owner
   approval. Roll back only Hosting to a known prior release, record the
   operator and release IDs, then follow with a corrective pull request.

An emergency rollback does not authorize SQL, Storage, Functions, Cloud Run,
Secret Manager, or IAM changes. Do not call a rollback successful until the
public site and its provenance are rechecked.

## New-session checklist

Any session asked to release or "make it live" must begin by answering:

1. Am I in `anurag-duddu/specimen-digitization-app`?
2. Have I read this file and `AGENTS.md`?
3. Is the worktree understood and safely isolated on a branch?
4. Is `origin/main` current, and is the branch based on the intended commit?
5. Are generated credentials, `.env`, and private data still ignored?
6. Did `scripts/ci/verify.sh` pass on the release candidate?
7. Does the pull request show all required checks on its latest SHA?
8. Was the change merged through GitHub rather than pushed directly?
9. Did the `main` workflow's deploy job succeed for the merge SHA?
10. Does the public `deployment.json` report that same SHA, and did the public
    application smoke pass?

If any answer is no or unknown, the release is not complete and no substitute
manual deployment is permitted.

## Credential-free mobile build coverage

The additional `Flutter android build` and `Flutter ios build` jobs compile the
native clients on Ubuntu 24.04 and macOS 15. They receive no production secrets
or OIDC permission, upload no distribution artifacts, and cannot deploy. The
Hosting deploy also waits for both matrix entries. The existing three protected
check names remain unchanged; any additive branch protection administration is
a separate reviewed change.

Run `scripts/ci/build_mobile.sh android` or `scripts/ci/build_mobile.sh ios` in a
clean worktree. The script refuses to overwrite existing ignored Firebase
configuration, creates clearly synthetic native JSON/plist and the CI Dart
placeholder, then removes only the files it created on exit. Do not run it
concurrently with other Flutter verification in the same worktree.

Android compiles a debug APK with JDK 17; it proves native compilation, not
release signing or store delivery. iOS compiles release mode with `--no-codesign`;
it requires Xcode/CocoaPods and proves neither device execution nor distribution
signing. Neither check uses paid inference or authenticates to real Firebase.
The canonical pre-push gate remains `scripts/ci/verify.sh`; mobile checks are
additional platform gates and must pass on the integrated candidate.

## Approved runtime/data release contract

The user approved release decision packet v1 on 2026-09-08. The bounded,
current authority is recorded in
[RELEASE_AUTHORIZATION.md](execution/RELEASE_AUTHORIZATION.md), superseding
the approval-pending statements in the historical
[LIVE_DELIVERY.md](execution/LIVE_DELIVERY.md) proposal. It authorizes the
separate paths below and the documented bounded Google Cloud setup. It does
not establish cloud readiness or authorize an unspecified expansion. The
initial sample remains the data owner's frozen first ten existing specimens;
expansion requires user review and approval of end-to-end results.

- `.github/workflows/runtime-release.yml` and
  `.github/workflows/data-release.yml` accept only pushes to `main` after a PR
  merge. No PR/tag/manual/workflow-run deployment route is permitted.
- Before obtaining Google credentials, independently verify the repository,
  numeric owner/repository IDs, protected branch, exact workflow/source SHA,
  merged-PR provenance, latest main, all five successful CI/CD jobs on that
  exact source, and the applicable reviewed authorization packet. A stale,
  incomplete, example or unreviewed packet fails closed.
- Runtime publication and runtime promotion use separate identities and
  main-only environments (`runtime-build-production` and
  `runtime-production`), so a publisher cannot inherit deployment authority.
  Data uses `data-production`. Exact WIF resources and effective permissions
  must be verified after inventory; never infer their existence or a project
  number from an example. Restrict each provider to the correct repository IDs,
  push/main, environment and workflow. Keep Hosting's provider and identity
  unchanged. No long-lived service-account keys.
- Build the exact merged source once, retain immutable image digests and trusted
  provenance, and deploy those same digests. Publication credentials are limited
  to the named registry; deployment credentials have only the reviewed resource
  permissions. No mutable tag, arbitrary command or user-supplied script is a
  substitute for a typed, reviewed release operation.
- Verify current backup and isolated restore proof before compatible data
  changes. Keep writers quiesced when uniqueness protection could be absent;
  restore and independently verify supplemental indexes after reconciliation.
  Do not create or upgrade a source SQL instance as a side effect of deployment.
  Preserve source data and object generations. Bootstrap the approved initial
  administrator only after verified identity/scope, with sensitive access off.
- Verify compatible deployed data before promoting runtimes. Enforce the
  approved API/worker/SAM resource, expiry, scope and cumulative cost limits.
  Build admission precedes images; data admission precedes data apply; runtime
  promotion follows data readiness; public acceptance follows deployment.
  Do not create circular prerequisites or confuse preflight with acceptance.
- Serialize production transitions without cancellation. Quiesce on failure;
  retain previous known revisions and evidence. Runtime rollback uses a reviewed
  main PR and compatible data; never delete original data to simulate recovery.
- Completion requires the exact main workflow/deploy results, public Hosting
  marker, matching runtime/data revisions and authenticated full-cohort product
  evidence. An evidence-only intermediate run is not full-pipeline acceptance.

The coordinator may perform only the approved, independently reviewed setup
actions after live inventory and recording the exact bounded action packet.
Check the complete conservative cost reservation before each billable action;
unknown costs are not zero. The USD 5 limit is cumulative across all sessions
and retries. Stop if costs do not fit or an action exceeds the recorded scope.
Only the newly created restore clone may be removed, by its two-hour expiry,
after verification evidence is retained. Existing data and source SQL remain.

Recovery admission additionally requires the original typed
[`recovery.allowance` contract](execution/CLONE_ALLOWANCE.md). The protected data
workflow publishes and verifies a signed original intent, then atomically creates
one fixed-key held Storage claim before any backup/clone liability. Only that
invocation's complete native winning response grants the in-memory capability.
No retries, receipt adoption or allowance reset are permitted. Root must first
qualify the complete issuance baseline, effective exact-object create-only IAM
and continuing held-object costs. This source contract grants no native setup or
new execution window; existing clone ownership and cleanup controls still apply.

The candidate CI workflow `runtime-ci.yml` builds committed container inputs
without credentials or registry publication. Scoped PRs report absent owner
inputs as Not run; main/integration fail if either container or the data-plan
validator is absent. This is additive coverage, not a runtime release workflow.

Main web builds accept the approved public repository variables
`SPECIMEN_API_BASE_URL` and `SPECIMEN_RECAPTCHA_SITE_KEY` together. Both unset
preserve the setup screen; partial or unsafe configuration fails the build.
`build_web.sh` never forwards these variables for PR/manual/native builds. This
wiring alone grants no authority. Release decision packet v1 separately
authorizes configuring the verified API URL and App Check registration/site key
for this live app after target verification and access-denial checks.

Release completeness is separate from candidate structure CI. The strict
non-deploying preflight `scripts/ci/check_release_readiness.py` accepts a real
generated/private packet only in the expected GitHub main/integration workflow
context, derives the expected source SHA from that context and rejects missing,
incomplete, example or stale packets. No future deploy implementation may replace
this with example/schema validation. API, worker and CPU SAM image provenance,
pinned model artifact hashes, data restoration and approval evidence are required;
actual evidence verification and cloud authorization remain additional gates.

The first missing application database uses the typed
`data-initialize-missing/v1` phase in that same protected data workflow. Its
one-time initializer has a separate main-only `data-initialization-production`
environment and `specimen-data-initialize` keyless identity. Native source and
restore parity precede initializer credentials; fixed SQL and privilege disposal
must qualify on the same owned clone before source initialization. Ordinary data
apply resumes with ordinary credentials and the original recovery proof, without
another clone. The maximum temporary privilege window is ten minutes after
native parity, inside the existing two-hour clone deadline. Actual identities,
conditional permissions and this exact temporary privilege require the existing
independent authority/admission review. The workflow creates no IAM policy or
password and changes no source capacity. See the precise contract and live gates
in [DATABASE_INITIALIZATION.md](execution/DATABASE_INITIALIZATION.md).
