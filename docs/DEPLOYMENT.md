# CI/CD and production deployment contract

Current approved budget/duration: see the [September 14 amendment](execution/APPROVED_RELEASE_BUDGET.md).
The additive [bounded Logfire approval](execution/APPROVED_LOGFIRE_TRACING.md)
governs the existing US destination and worker-only writer secret.
Historical USD5/30-minute statements below remain applicable to legacy artifacts;
new release inputs must explicitly select the approved additive contracts.

> 2026-09-23: The owner's decisions in
> [`docs/execution/golive/PLAN.md` section 2.1](execution/golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> supersede parts of this document for the go-live program. Each superseded
> clause keeps its original text and carries a dated note naming the decision.
> The ceiling is now USD 25 (G9,
> [amendment](execution/APPROVED_RELEASE_BUDGET.md#go-live-amendment-2026-09-23-g9)),
> trace content follows G3
> ([amendment](execution/APPROVED_LOGFIRE_TRACING.md#go-live-amendment-2026-09-23-g3)),
> and data and runtime releases deploy on merge without release inputs (G11).
> G30's per-call reservations stand (PLAN 4.3; the coordinator's ruling on the
> mechanism).
>
> 2026-10-03: The protected data and runtime release process is retired. The
> chapter [Data and runtime releases](#data-and-runtime-releases) below is the
> current contract for those two planes.
> [`execution/golive/RELEASE.md`](execution/golive/RELEASE.md) describes the
> retired process and is kept for history.

This document is the authoritative release runbook for Specimen Digitization.
It applies to humans, automation, agents, every branch, every worktree, and every
Codex session. `AGENTS.md` points all sessions here.

The governing rule is simple:

> Production changes reach Firebase Hosting only through the repository's
> GitHub Actions workflow after a pull request is merged to `main`.

The database, the Storage rules and the API follow the same rule through their
own two workflows; see [Data and runtime releases](#data-and-runtime-releases).

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
| Runtime release workflow | `.github/workflows/runtime-release.yml` |
| Data release workflow | `.github/workflows/data-release.yml` |
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
Run, Temporal, or model workers. The data and runtime releases described below
do not change that Hosting boundary. AWS is not part of this design.

## Non-negotiable rules

1. Start from an up-to-date `main` and work on a short-lived branch.
2. Run `scripts/ci/verify.sh` before pushing.
3. Push the branch and open a pull request. Do not push a release directly to
   `main`.
4. Required pull-request checks must pass on the exact candidate commit.
5. Merge through GitHub. A merge to `main` is the production trigger. The data
   and runtime workflows also accept a manual run on `main`; nothing else
   deploys.
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
11. A release is complete only after the three `main` workflows are green, the
    public site reports the exact merged commit SHA in `/deployment.json` and
    the API reports it at `/version`.
12. If any required proof is unavailable, report the release as incomplete.

The only executable Hosting deploy command lives in
`scripts/ci/deploy_hosting.sh`. That script fails closed unless GitHub provides
the expected repository, `push` event, `main` ref, workflow identity, commit
SHA, tested artifact marker, and keyless Google credential file. It installs the
pinned Firebase CLI into a private prefix with `npm install --ignore-scripts`,
as the data plane does, and runs that binary directly: no dependency's install
script executes while the short-lived Google credential file is on the runner. Tests reject
deploy commands added to unapproved automation files. The data and runtime
releases change production only through the scripts under `scripts/release/`,
which only their own workflows call; see
[Data and runtime releases](#data-and-runtime-releases).

## Pipeline behavior

### Pull requests

`.github/workflows/ci-cd.yml` runs the three existing protected checks and two native build matrix entries:

| Required check | What it proves |
|---|---|
| `Repository checks` | Sensitive-file policy, secret scans, formatting, YAML/JSON/TOML validity, shell checks, and GitHub Actions syntax |
| `Python tests` | Locked Python environment and all backend/policy tests |
| `Flutter checks and web build` | Locked Flutter dependencies, Dart formatting, the `specimen_ui` design system's own analysis and tests, client static analysis, client widget tests, release build, immutable deployment metadata, and a loopback route smoke over the built artifact |

Pull requests use `apps/specimen_digitization/lib/firebase_options.ci.dart`.
They receive neither the real FlutterFire configuration nor a Google OIDC
token and cannot deploy.

`scripts/ci/smoke_web_routes.py` runs between the deployment stamp and the
artifact upload, so a build that fails it is never uploaded and therefore can
never be deployed. It serves `build/web` on 127.0.0.1 with the rewrites and
the response headers `firebase.json` declares, reads the route table out of
`apps/specimen_digitization/lib/src/app/app_router.dart`, and proves four
things about the artifact: every declared location answers with the
application shell rather than a 404, every response carries the security
headers listed below, the design system gallery is absent from
the release bundle, and `deployment.json` is the exact marker
`scripts/ci/deploy_hosting.sh` and `scripts/ci/smoke_hosting.sh` accept. It
contacts no host, holds no credential and deploys nothing. It says nothing
about the public site: only `scripts/ci/smoke_hosting.sh` does that, after a
deploy.

#### The response headers Hosting sets

`firebase.json` declares one `headers` block on `**` and one on
`/deployment.json`. The `**` block sets `X-Content-Type-Options: nosniff`,
`Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`,
`Content-Security-Policy: frame-ancestors 'none'; object-src 'none';
base-uri 'self'` and `Permissions-Policy: camera=(), microphone=(),
geolocation=()`. `SECURITY_HEADERS` in `scripts/ci/smoke_web_routes.py` is the
same table, and the smoke asks every response for it, so a header dropped from
the configuration fails the build rather than the site.

Three omissions are deliberate. The policy names no `script-src` or
`style-src`: Flutter web boots from an inline script the build writes into
`index.html` and fetches CanvasKit and its wasm from `gstatic.com`, so a
source list narrow enough to be worth having would have to track the engine's
own hosts. There is no COOP or COEP: nothing this client does needs cross
origin isolation, and it would break the reCAPTCHA Enterprise frame App Check
uses. And `Permissions-Policy` grants nothing to `self`, because the web build
asks for nothing: the in-app camera is behind `!kIsWeb`, so a web reviewer is
offered the file picker rather than a capture button. Adding a web capture
flow means revisiting the header and the test that holds it.

### Pushes to `main`

The same five checks run again for the actual merged commit. The Flutter job
restores the encrypted production FlutterFire configuration, builds once, adds
`deployment.json`, and uploads the artifact. `Deploy Firebase Hosting` then:

1. waits for every required job;
2. downloads that exact tested artifact instead of rebuilding;
3. enters the GitHub `production` environment;
4. obtains a short-lived Google credential through OIDC;
5. runs the guarded Hosting-only deploy script;
6. verifies the page title and the public deployment marker's repository,
   exact commit SHA, workflow run ID and run attempt.

Artifact names bind that same SHA, run ID and attempt at upload and download.
The deploy guard rejects malformed, duplicate or mismatched marker fields before
invoking Firebase. A rerun of failed jobs cannot reuse an artifact from an earlier
attempt; rerun all jobs to produce and test a current-attempt artifact.

Deploy concurrency is one-at-a-time and is never cancelled mid-deploy. Pull
request runs can be cancelled when superseded.

### Manual workflow runs

In this Hosting workflow, `workflow_dispatch` intentionally runs CI only. It
cannot deploy. Do not change manual dispatch into a Hosting production trigger.
A replay of a failed Hosting production job must retain its original `push`
event and merged `main` commit. The data and runtime release workflows are
different: they accept a manual run on `main`, as
[Data and runtime releases](#data-and-runtime-releases) describes.

## Authentication and secrets

GitHub Actions authenticates with Workload Identity Federation. This section
covers Hosting; the data and runtime identities are listed under
[Identities](#identities). The Hosting provider must accept only:

- repository ID `1360732425`;
- repository owner ID `140138196`;
- event `push`;
- ref `refs/heads/main`;
- environment `production`; and
- workflow ref
  `anurag-duddu/specimen-digitization-app/.github/workflows/ci-cd.yml@refs/heads/main`.

The Hosting deploy service account has only:

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
actionlint, shellcheck, locked Python installation, Python tests, the UI
string check, the `specimen_ui` design system's own analysis and tests, client
dependency resolution, client analysis, client tests, Dart formatting, the
release web build, and the route smoke over that build. If the local ignored
production FlutterFire file is absent, it uses and then removes the
credential-free CI placeholder. It never deploys.

It runs the same Dart formatting and route checks the `Flutter checks and web
build` job runs, so a branch that passes here passes those two in CI. On a
loaded workstation the whole script can be reaped part way through; run its
gates one at a time when that happens and read each gate's own exit status.

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

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](execution/golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G2, G9 and G11. Specimens are processed one at a time, on demand, including
> new uploads; the ceiling is USD 25, held by the pipeline and a billing alert
> rather than a release reservation ledger. G30's per-call reservations stand
> (PLAN 4.3; the coordinator's ruling on the mechanism). The pilot still never
> runs in pull-request CI.

### Flutter client

The client is two Dart packages: the application, and the `specimen_ui` design
system it is built from. Both are resolved, analysed and tested, in that order,
because a control changes under every screen at once.

```bash
cd apps/specimen_digitization
flutter pub get --enforce-lockfile
flutter analyze --fatal-infos
flutter test
flutter build web --release
```

```bash
cd apps/specimen_digitization/packages/specimen_ui
flutter pub get
flutter analyze --fatal-infos
flutter test
```

Run each command on its own and read its own exit code. The two suites contend
for one machine, so a single chained command can be reaped without either
having failed.

Formatting is checked before a commit and is not a repository hook:

```bash
cd apps/specimen_digitization
dart format --set-exit-if-changed lib test
```

For local development only:

```bash
cd apps/specimen_digitization
flutter run
```

The credential-free native compile checks are
`scripts/ci/build_mobile.sh android` and `scripts/ci/build_mobile.sh ios`. They
are described under "Credential-free mobile build coverage" below and must not
run concurrently with other Flutter verification in the same worktree.

#### What the rebuilt client means for a release

The presentation layer was replaced in September 2026 by an in-repo design
system, `apps/specimen_digitization/packages/specimen_ui`. Five things about it
bear on a release build.

- **The typefaces ship in the artifact.** Geist and Geist Mono are bundled
  inside the package under `assets/fonts/` and their SIL Open Font License text
  is registered with `LicenseRegistry` at startup. `google_fonts` is gone from
  `pubspec.yaml` and from `pubspec.lock`, so nothing fetches a face at runtime
  and a deployed page needs no font host. The `fonts_bundled` gate fails if
  either statement stops being true.
- **There are no Material Symbols.** Every glyph comes from Phosphor through
  the package's `UiIcons` registry; `material_symbols_icons` and
  `cupertino_icons` are out of the pubspec, and the `icons_unique` gate allows
  no `Symbols.` or `Icons.` reference under `lib/`. `uses-material-design: true`
  stays on because Flutter's own text selection controls reach a few glyphs
  statically: the web build tree-shakes `MaterialIcons-Regular.otf` from
  1,645,184 bytes to 7,736, so the flag costs 7.7 KB rather than 1.6 MB.
- **The gallery is not in a release build.** `/gallery` renders every token and
  control for review. Its route is registered only when `kReleaseMode` is
  false, so `flutter build web --release` carries neither the route nor a way
  to reach it, and the tree shaker then removes the gallery itself: the string
  `Gallery` does not appear in the built `main.dart.js`.
- **The package's tests are part of the required check.**
  `.github/workflows/ci-cd.yml` and `scripts/ci/verify.sh` both resolve,
  analyse and test `packages/specimen_ui` before the application. A change to
  one control is a change to every screen, so a green application suite over a
  red package is not a signal.
- **Goldens are compared on macOS only.** Every checked-in golden, in the
  application and in the package, is generated on macOS. Off macOS the test
  still builds the screen, so every layout, overflow and semantics assertion in
  it runs; only the pixel comparison is set aside, and `--update-goldens`
  refuses, so no file is ever written by a platform that did not draw the rest
  of the set. Linux rasterises the same bundled fonts one to eleven percent
  differently, which would otherwise fail every file on the CI runner for a
  reason no reviewer could act on.

`lib/firebase_options.dart` is gitignored and is never committed. Copy
`lib/firebase_options.ci.dart` over it for a credential-free local build;
`scripts/ci/verify.sh` does this for you and removes the placeholder again.

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
| `scripts/ci/smoke_hosting.sh` | Confirms title and exact public repository/SHA/run/attempt marker | Workflow-required; local read-only diagnosis is allowed |

A read-only production recheck is allowed when investigating status:

```bash
scripts/ci/smoke_hosting.sh \
  https://specimen-digitization.web.app \
  EXPECTED_40_CHARACTER_MERGE_SHA
```

This two-argument diagnosis proves the repository and SHA only. Release
verification supplies the expected run ID and attempt as the third and fourth
arguments; both must be canonical positive integers from the actual workflow run.

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
- `scripts/ci/**`, `scripts/release/**` and `scripts/ops/**`
- `firebase.json` and `.firebaserc`
- `.gitignore` and `.pre-commit-config.yaml`
- `apps/specimen_digitization/pubspec.lock`
- `uv.lock`
- the checked-in binaries: `apps/specimen_digitization/test/golden/images/`,
  `apps/specimen_digitization/test/accessibility/fixtures/`, and the design
  system's `test/gallery/goldens/`. Two branches that both regenerate one of
  these sets revert each other with no conflict to warn either of them, so a
  regenerated golden in a diff is read rather than skimmed, and the set that
  moved is compared with the set expected to move
- SQL Connect schemas, connectors, operations, or generated SDKs
- IAM, Workload Identity Federation, GitHub environment, secret, or branch
  protection settings

### 3. Run local gates

```bash
scripts/ci/verify.sh
git diff --check
git status --short
```

Run it in a quiet worktree. `verify.sh` runs both Flutter suites, and a second
Flutter or Git command against the same worktree while it is running will fail
one of them for a reason that is not in the diff. If a run is killed rather
than failed, run the gates it contains one at a time and read each exit code
directly, rather than rerunning the whole script and hoping.

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
`Deploy Firebase Hosting`. The same merge also starts the data and runtime
release runs; [Verifying a release](#verifying-a-release) covers all three.
Then independently re-run the public marker smoke:

```bash
scripts/ci/smoke_hosting.sh \
  https://specimen-digitization.web.app \
  "$(git rev-parse HEAD)" \
  EXPECTED_RUN_ID EXPECTED_RUN_ATTEMPT
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

These protections are not self-sustaining. They lapsed while the repository
was private on a GitHub plan that does not offer branch protection, and on
2026-09-22 `main` reported `protected: false` while every earlier release
had assumed otherwise. All three release workflows depend on them directly:
a merge to `main` is what deploys, so the required checks on the pull request
are the gate in front of production. Before any release, and after any plan
or visibility change, verify:

```bash
gh api repos/anurag-duddu/specimen-digitization-app/branches/main --jq .protected
```

The answer must be `true`. On 2026-09-22 the owner made the repository
public; the dormant rule reactivated with exactly the settings above, which
was verified through the same command. Restoring or changing protection is
an owner action and the applied settings must be recorded in the session
log.

The GitHub `production`, `data-production`, `runtime-build-production` and
`runtime-production` environments must accept deployments only from `main`.
GitHub Actions' default token permission must remain read-only; only the jobs
that deploy or publish receive `id-token: write`. Third-party actions remain
pinned to immutable commit SHAs.

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
  repository, SHA, run ID and attempt; an HTTP 200 or page title alone is insufficient.
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
  A production schema change goes only through the data release, which applies
  additive changes and refuses destructive ones. Never make Flutter connect
  directly to PostgreSQL.
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

Hosting was not changed. The data and runtime releases start from the same
push and do not wait for this workflow, so check their runs as well. Create a
repair branch from the failing merge, revert or fix through a pull request,
and let the normal pipeline run.

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
9. Did the Hosting deploy job, the data release and the runtime release all
   succeed on `main` for the merge SHA?
10. Does the public `deployment.json` report that same SHA, does the API
    `/version` report it, and did the public application smoke pass?

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

## Data and runtime releases

The database, the Storage rules and the API are released the way Hosting is:
a pull request is merged to `main` with the required checks passed, and a
workflow deploys the merged commit. A release needs nothing else prepared,
signed or approved.

The standing authority is the owner's decision G11 of 2026-09-23 in
[`docs/execution/golive/PLAN.md` section 2.1](execution/golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator):
data and runtime releases deploy automatically on merge, like Hosting.

On 2026-10-03, in the go-live coordinator session, the owner told the agents
"Take over, get this live". The coordinator's record of that session also says
the owner never asked for the time-limited access windows, the receipts or the
release safeguards. At about 05:25Z the owner answered two questions from the
coordinator with "Yes, get it done. You have my authorization. The safety
checks are being paranoid and not required. you have full permission". The two
questions were:

1. whether the coordinator may merge lane pull requests once the required
   checks are green and an independent review is clean;
2. whether the setup script may start the two release workflows.

That answer does not cover disabling required checks or branch protection.
These messages are recorded in the coordinator session, not in this
repository.

Review before merge follows the owner's ruling G51. It is recorded outside
this repository, in
`~/specimen-golive/first-ten-20261001/claude-owner-rulings-receipt-20261002T230630Z-v1.json`:
until the ten pilot specimens are live, one independent reviewer per pull
request head plus green required checks replaces G18's four-reviewer swarm,
and branch protection settings are unchanged. That G51 also replaces the "PR
steward approves" clause of G11 is the coordinator's reading, not a sentence
the owner wrote.

These controls stay: branch protection and the required checks on `main`,
keyless Workload Identity Federation identities with no service-account keys,
one main-only GitHub environment per identity, and actions pinned to commit
SHAs. A release must not have receipts, evidence digests, signed intents,
time-limited access windows, approval packets or admission gates. Do not add
them.

### Triggers

`.github/workflows/data-release.yml` ("Data release") and
`.github/workflows/runtime-release.yml` ("Runtime release") run on every push
to `main`. Each also accepts a manual run (`workflow_dispatch`), and its jobs
run only when the ref is `main`. Each workflow runs one release at a time and
never cancels a release in progress.

### Identities

Every identity signs in through the Workload Identity Federation pool
`projects/716045864126/locations/global/workloadIdentityPools/github-actions`.
The service accounts belong to the `specimen-digitization` project, so
`specimen-data-release` below is
`specimen-data-release@specimen-digitization.iam.gserviceaccount.com`.

| Plane | Workflow file | GitHub environment | Service account | Provider |
|---|---|---|---|---|
| Hosting | `.github/workflows/ci-cd.yml` | `production` | `github-firebase-hosting` | `specimen-digitization` |
| Data | `.github/workflows/data-release.yml` | `data-production` | `specimen-data-release` | `specimen-data-release` |
| Runtime image build | `.github/workflows/runtime-release.yml` | `runtime-build-production` | `specimen-runtime-build` | `specimen-runtime-build` |
| Runtime deploy | `.github/workflows/runtime-release.yml` | `runtime-production` | `specimen-runtime-release` | `specimen-runtime-release` |

Each provider accepts only this repository, the `main` ref, its own GitHub
environment and its own workflow file. The Hosting provider accepts `push`
events only. The other three accept `push` and, once the owner setup below has
run, `workflow_dispatch`. A provider is bound to the workflow's file name, so
renaming a workflow file breaks its sign-in. The image build identity can
write to the image registry and cannot deploy. The deploy identity can deploy
and can only read the registry.

### Data release

The workflow has one job, `release`, in the `data-production` environment. It
checks out the commit, installs the locked Python environment and the two
pinned Node packages the SQL steps use, signs in as `specimen-data-release`
and runs `scripts/release/data_release.py`. That script runs the steps below
in order and prints one line per step, saying what it did or that it skipped.
A failure stops the run with one line that starts `data release failed:`. The
script refuses to run outside GitHub Actions.

1. **Initialize.** `scripts/release/data_sql.mjs probe` reads what the
   database already has: the three Data Connect roles (owner, writer and
   reader), the `uuid-ossp` extension, the owner of schema `public`, the role
   memberships of the release identity and of the Data Connect service agent,
   the default privileges, the connect and usage grants, and that the database
   and the schema are closed to every other role. When everything is present,
   the step is skipped. Otherwise `data_sql.mjs init` runs
   `scripts/release/sql/initialize.sql` in one transaction. That file creates
   what is missing, sets those grants and removes no object and no data, so it
   is safe on a database that an earlier attempt left partly initialized. The
   probe then runs again and must find everything present.
2. **Diff.** The script sends the committed schema (`dataconnect/schema`) to
   Data Connect in validate-only mode. Data Connect answers either that the
   database already matches, or with the SQL statements that would make it
   match. Every statement is printed.
3. **Apply.** When there are statements and the additive rule below accepts
   all of them, `data_sql.mjs migrate` runs them in one transaction as the
   database owner role. Any error rolls the whole transaction back.
4. **Schema.** The committed schema is published to the Data Connect service
   `specimen-digitization-service` as schema `main`. The step is skipped when
   the live schema files equal the committed ones and the diff was empty.
5. **Indexes.** `data_sql.mjs indexes` runs
   `dataconnect/sql/paging-indexes.sql` and
   `dataconnect/sql/search-indexes.sql`. Every statement in them must be
   `CREATE INDEX CONCURRENTLY IF NOT EXISTS`, so an existing index is left
   alone. The step then fails, naming the index, if any index is marked
   invalid. It never drops one.
6. **Connector.** The committed connector (`dataconnect/connector`) is
   published as `specimen-server`. The step is skipped when the live files
   equal the committed ones.
7. **Storage rules.** `storage.rules` is published. The step is skipped when
   the live ruleset has the same content.
8. **Bootstrap rows.** Two sets of rows, each read before anything is written:
   - the organization, its 18 collections and the owner's administrator
     membership, from the prepared artifact in the environment secret
     `DATA_BOOTSTRAP_ARTIFACT_B64`;
   - the worker's operator membership, for the user ID held in the Secret
     Manager secret `specimen-worker-actor-uid`, version 1. The ID is never
     printed.

   For each set: when the rows exist and are identical, nothing is written.
   When they are absent, they are inserted and read back. When they exist and
   differ, nothing is written: the step prints one warning that names which
   part differs (never a value) and the release continues, so later edits to
   these rows do not block releases. Before the organization rows are
   written, the artifact is checked against the committed collection tree. The bootstrap inserts these prepared rows and nothing more; it
   creates no generic runtime signup or collection-creation API.
9. **Done.** The last line is `data release complete for <sha>`.

#### Additive only

The release changes the database schema only by adding to it. It refuses a
schema change when Data Connect marks the diff, or any statement in it, as
destructive, or when a statement contains `DROP`, `TRUNCATE`, `DELETE` or
`RENAME` as a SQL keyword. Quoted identifiers and string literals are not
searched. Two uses of those words are accepted because they remove nothing:
`DROP NOT NULL`, which makes a required column optional, and the `ON DELETE`
action of a foreign key. A statement the rule cannot read safely is refused
as well: one with a backslash, a comment, a dollar quote or an unbalanced
quote.

A refusal happens at the diff step, before the apply step. The release prints
the statements and the reason and exits with an error, and no schema statement
has run.

One kind of statement is set aside instead of refused. Data Connect does not
know the supplemental indexes that the release creates from
`dataconnect/sql/paging-indexes.sql` and `dataconnect/sql/search-indexes.sql`,
so its diff can ask to drop them. A `DROP INDEX` that names exactly one of
those indexes is printed, never run and never counted as destructive; the
indexes stay. A `DROP INDEX` of any other name is refused like every other
drop.

When the answer says the committed schema does not fit the connector that is
live, the release stops with its own message naming the connector. It does not
delete or rewrite the connector; that change needs the owner.

Calls that only read (the reads, the operation polls, the validate-only
request and the secret read) are tried up to three times when the connection
drops or Google answers 429 or a 5xx. A call that writes is sent once.

#### Never drop

No step of the data release drops, deletes or truncates. Initialization
creates what is missing and sets grants. The additive rule refuses destructive
statements. An invalid index is reported, not dropped. Bootstrap rows that
differ from the artifact are reported, not overwritten. A destructive schema
change stops the release and needs the owner.

#### A push that changes no data files

The data release runs on every push to `main`, including a docs-only push,
because the runtime release waits for it on every commit. On such a push every
step is a no-op: initialization finds everything present, the diff is empty,
the schema, connector and rules already match, the indexes exist and the
bootstrap rows are identical. The run still prints the completion line and
succeeds.

#### Inputs

- `DATA_BOOTSTRAP_ARTIFACT_B64`, a secret of the `data-production`
  environment: the prepared organization and collection rows, base64-encoded.
  It is the only GitHub secret the data release reads. When the secret is
  unset and no organization exists, the step fails and says so. When the
  secret is unset and an organization exists, the step is skipped without
  comparing anything.
- The Secret Manager secret `specimen-worker-actor-uid`, version 1: the
  worker's user ID, read during the bootstrap step when the artifact is set.
- Everything else the release reads is committed in this repository:
  `dataconnect/`, `storage.rules`, the collection tree under
  `infra/reference/` and the release scripts.

#### Running it again

Every step reads the current state first and writes only what is missing, so
a second run is safe. Re-run the failed workflow run, or start a manual run of
"Data release" on `main`.

### Runtime release

The workflow has three jobs.

1. **`data`** waits for the data release of the same commit.
   `scripts/release/wait_for_data.sh` finds the newest "Data release" run for
   the commit, polls it every 15 seconds and passes only when that run
   concluded with success. A manual data run after a failed one counts,
   because the newest run decides. The job uses no environment and no cloud
   credentials. The API is therefore never deployed ahead of the schema it
   reads.
2. **`build`** runs in parallel with `data`, in the `runtime-build-production`
   environment, as `specimen-runtime-build`.
   `scripts/ci/build_runtime_image.sh api` builds the API image from the
   committed files of the merged commit and checks it offline.
   `scripts/release/push_image.sh api` pushes it to
   `us-east4-docker.pkg.dev/specimen-digitization/specimen-runtime/api` under
   the tag `sha-<commit>-<run id>-<run attempt>`. The registry does not let a
   tag be overwritten, so the run ID and attempt keep a re-run from colliding
   with its earlier push. The job passes the image on by digest,
   `.../specimen-runtime/api@sha256:<digest>`, never by tag.
3. **`release`** needs both jobs and runs in the `runtime-production`
   environment, as `specimen-runtime-release`.
   - `scripts/release/deploy_api.py` deploys that digest to the Cloud Run
     service `specimen-api` in `us-east4` with `gcloud run deploy`. The
     service account, CPU, memory, instance limit, concurrency, timeout,
     environment variables and secret references all come from
     `scripts/ci/runtime_settings.py`, the one committed source for them.
     Secrets are referenced by numbered version, never `latest`. The new
     revision takes all traffic.
   - The same script then reads the service's access policy and adds the
     public invoker binding (`allUsers`) only when it is absent.
   - `scripts/release/smoke_api.sh` checks the public URL. `/version` must
     report the merged commit as `source_sha` and the mode `production`.
     `/health/ready` must return 200 with status `ready`. `/v1/session`
     without credentials must return exactly 401, which shows the application
     received the request and refused it. A 403 means Cloud Run blocked the
     request first, so the public invoker binding is missing. The three checks
     share about three minutes of retries while the new revision starts.

The worker job and the SAM 3 service are added in a follow-up change.

### One-time owner setup

The owner grants the standing access the releases need once, and starts the
first releases, with:

```bash
scripts/ops/owner_setup.sh --dry-run     # read the live state, print what would change
scripts/ops/owner_setup.sh               # set up, then start and follow the releases
scripts/ops/owner_setup.sh --setup-only  # set up and start nothing
```

The script needs `gcloud` signed in as a project owner and `gh` signed in with
admin rights on the repository. It is idempotent: each step reads the live
state first and changes only what is missing, so running it again is safe. It
prints every command before running it, asks no questions and needs no
terminal. The owner runs it; an agent runs it only when the owner has
authorized that run first-hand. The setup part does seven things.

1. It removes four expired, time-limited role bindings left on the data
   release identity, each matched by its exact condition.
2. It makes sure the custom roles and the standing grants exist:
   - data release: publish the schema and connector, publish Storage rules,
     read the project, connect to the one Cloud SQL instance, read and write
     the bootstrap rows through Data Connect, and read version 1 of the worker
     user ID secret;
   - runtime image build: write to the image registry;
   - runtime deploy: deploy to Cloud Run, read the image registry, act as the
     runtime service accounts, and set who may invoke the API service. That
     last right is granted on the project only until the service exists; the
     next run moves it onto that one service;
   - runtime service accounts: the grants they already hold (the connector,
     user lookup, the bucket and their pinned secrets), plus the SAM runtime's
     listing of the bucket for its checkpoint mount, plus the worker's create
     and get on the `research-capture/`, `research-journal/` and
     `research-media/` prefixes of the bucket (the research harness's objects:
     create-only writes and reads. The roles are `objectCreator` and
     `objectViewer` only, the condition has no listing clause, nothing grants
     delete or update there, and no other account holds this grant).
3. It gives the data release database user the `cloudsqlsuperuser` database
   role, which the initialize step needs.
4. It widens the condition of the three release providers to accept
   `workflow_dispatch` as well as `push`, and changes nothing else in it. The
   Hosting provider is not touched.
5. It sets the repository variables `SPECIMEN_API_BASE_URL` and
   `SPECIMEN_RECAPTCHA_SITE_KEY`, described next.
6. It sets the `DATA_BOOTSTRAP_ARTIFACT_B64` secret in `data-production` from
   the owner's private artifact file when that file is on the machine. The
   value goes through a pipe and is never printed. GitHub cannot show a
   secret, so this one step repeats on every run.
7. It prints, and does not remove, what the retired process left behind: the
   `RELEASE_*` variables and the unused secrets of `data-production`, the
   `data-initialization-production` environment with its provider and service
   account, and the roles nothing uses any more.

After the setup, unless `--setup-only` is given, the script starts the
releases and follows them, printing one line each time a step finishes:

1. It waits two minutes when it changed any access, so the change can take
   effect.
2. It starts the data release on `main` and follows it to the end.
3. It starts the runtime release on `main` and follows it to the end.
4. When it changed a repository variable (or with `--redeploy-web`), it runs
   the latest Hosting run on `main` again, then checks that the live site's
   built JavaScript names the API address. If it does not, the script prints a
   warning, not a failure: the next merge to `main` rebuilds the site.

It starts nothing when a setup change failed, or when the simple workflows are
not on `main` yet. It ends with a summary: one PASS, FAIL, WARN or SKIPPED
line per stage with the run address, the live addresses, and for a failure the
exact command that shows the log.

When a release step fails with "the owner runs scripts/ops/owner_setup.sh
once", a grant or the bootstrap secret from this list is missing or out of
date.

### Repository variables for the web build

Main web builds accept the public repository variables
`SPECIMEN_API_BASE_URL` and `SPECIMEN_RECAPTCHA_SITE_KEY` together. Both unset
preserve the setup screen; partial or unsafe configuration fails the build.
When both are set, the next push to `main` builds the web client against the
live API, with the site key as its App Check key. The owner setup sets the
pair. The API URL is `https://specimen-api-716045864126.us-east4.run.app`. The
site key is the public reCAPTCHA key registered for this app. Both values are
public configuration that ships in the web bundle.

The optional public repository variable `SPECIMEN_ADMIN_CONTACT` names the
collection administrator the client shows in its help sheet and in every "ask
your administrator" message when no collection document publishes a contact; it
accepts `Name <address>`, `Name, address` or a bare address, is validated for
that shape only, and is forwarded on main pushes independently of the API pair.
`build_web.sh` never forwards these variables for PR/manual/native builds.

### Verifying a release

The release of a merged commit is complete when all of these hold:

1. the three workflow runs on that commit are green: "CI/CD", "Data release"
   and "Runtime release";
2. the public Hosting marker `deployment.json` reports the commit;
3. the API reports the commit as `source_sha` at `/version`;
4. the smoke steps passed: the Hosting smoke at the end of "CI/CD" and the API
   smoke at the end of "Runtime release".

```bash
sha="$(git rev-parse origin/main)"
gh run list --commit "$sha" --json workflowName,status,conclusion,url
scripts/ci/smoke_hosting.sh https://specimen-digitization.web.app "$sha"
curl -fsS https://specimen-api-716045864126.us-east4.run.app/version
```

These commands only read. Record the commit, the pull request and the three
run URLs in the session log.

### When a data or runtime release fails

1. Open the failed run and read the failing step's log line. Each step prints
   what it was doing, and a missing grant names the owner setup script.
2. Fix forward. A code or schema problem is fixed by a pull request. A missing
   grant is fixed by the owner running the setup script.
3. Run the release again: re-run the failed run, or start a manual run on
   `main`. Every step is idempotent, so a release that stopped part way is
   safe to repeat.
4. Do not deploy by hand, and do not weaken a check to get past the failure.

A runtime release that fails in its `data` job is waiting on a failed data
release; fix that one first. Two failures need the owner rather than a code
fix: a schema change the additive rule refused, and an index reported invalid.
In each case the release stops without dropping or overwriting anything.
Bootstrap rows that differ from the prepared artifact do not stop a release;
the warning in the run is the owner's cue to look.

### Container build check

The candidate CI workflow `runtime-ci.yml` builds committed container inputs
without credentials or registry publication. Scoped PRs report absent owner
inputs as Not run; main/integration fail if either container or the data-plan
validator is absent. This is additive coverage, not a runtime release workflow.

### Retired

The earlier protected-release contract is retired. Gate packets, admission,
recovery windows and the one-time initializer are no longer part of a release.
The scripts that implemented them are listed in
[`scripts/ci/RETIRED.md`](../scripts/ci/RETIRED.md). They stay in the tree
unchanged until a follow-up pull request deletes them with their tests. Do not
extend them or call them from new code.

[`docs/execution/RELEASE_AUTHORIZATION.md`](execution/RELEASE_AUTHORIZATION.md)
and [`docs/execution/golive/RELEASE.md`](execution/golive/RELEASE.md) describe
the retired process and are kept for history. Where they conflict with this
chapter, this chapter wins. In particular, a manual run of the data or runtime
workflow on `main` is now allowed. The rules at the top of this document still
forbid workstation deployments, weaker branch protection, broader Hosting
permissions and service-account keys, and AWS stays out of the design.
