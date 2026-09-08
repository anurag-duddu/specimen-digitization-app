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
| GitHub environment | `production`, branch policy `main` only |
| Deployment service account | `github-firebase-hosting@specimen-digitization.iam.gserviceaccount.com` |
| Firebase CLI in CI | `15.8.0` |
| Flutter in CI | `3.38.5` |
| uv in CI | `0.12.5` |
| Python in CI | `3.12` |

Firebase SQL Connect backed by Cloud SQL for PostgreSQL is the application
database direction. Firestore is not the application database. The current
pipeline deploys only the static Flutter web artifact to Firebase Hosting; it
does not deploy or migrate SQL Connect, Cloud SQL, Storage, Functions, Cloud
Run, Temporal, or model workers. AWS is not part of this deployment design.

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
8. Do not give the deploy service account database, Storage, Functions, Cloud
   Run, Secret Manager administration, Owner, or Editor permissions.
9. Never create or store a Google service-account JSON key. CI uses short-lived
   GitHub OIDC credentials through Workload Identity Federation.
10. Never put `.env`, FlutterFire generated production files, provider keys,
    museum data, or Google credentials in Git.
11. A release is complete only after the `main` workflow is green and the
    public site reports the exact merged commit SHA in `/deployment.json`.
12. If any required proof is unavailable, report the release as incomplete.

The only executable production deploy command lives in
`scripts/ci/deploy_hosting.sh`. That script fails closed unless GitHub provides
the expected repository, `push` event, `main` ref, workflow identity, commit
SHA, tested artifact marker, and keyless Google credential file. Tests reject
deploy commands added to other automation files.

## Pipeline behavior

### Pull requests

`.github/workflows/ci-cd.yml` runs three independent jobs:

| Required check | What it proves |
|---|---|
| `Repository checks` | Sensitive-file policy, secret scans, formatting, YAML/JSON/TOML validity, shell checks, and GitHub Actions syntax |
| `Python tests` | Locked Python environment and all backend/policy tests |
| `Flutter checks and web build` | Locked Flutter dependencies, static analysis, widget tests, release build, and immutable deployment metadata |

Pull requests use `apps/specimen_digitization/lib/firebase_options.ci.dart`.
They receive neither the real FlutterFire configuration nor a Google OIDC
token and cannot deploy.

### Pushes to `main`

The same three jobs run again for the actual merged commit. The Flutter job
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

The run must show the exact merged commit and all four jobs green, including
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
