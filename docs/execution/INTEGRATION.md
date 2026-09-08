# Release integrity and product integration

## Ownership and current state

- Coordinator: `01a07f44-7d89-7052-b968-5e96753493ad`.
- Worktree: `/Users/anuragduddu/.codex/worktrees/80e6/specimen-digitization-app`.
- Branch: `codex/product-integration`.
- Baseline HEAD and fetched origin/main: `82fd60eff90684d2c630a37c59e1250604ad1cae`.
- Audit date: 2026-09-07 America/Chicago (2026-09-08 UTC).
- Scope: `.github/`, `scripts/ci/`, root Firebase configuration, deployment documentation, and later integration of coordinator-approved commits.
- Current phase: baseline assessment and integration plan. No component commits integrated, production changes made, or product acceptance claimed.

Read the shared coordination PLAN.md twice, repository AGENTS.md, and complete docs/DEPLOYMENT.md before this assessment. The latter remains the authoritative release contract. This initial change adds this report only.

## Verified release baseline

Read-only GitHub CLI queries verified:

- Main protection requires the three exact checks `Repository checks`, `Python tests`, and `Flutter checks and web build`, with strict freshness.
- Pull requests and resolved conversations are required; administrators are enforced; force pushes and deletion are disabled. Required approval count is zero; this is the existing policy, not newly granted merge authority.
- The production environment has exactly one deployment branch policy: branch `main`.
- Default workflow token permission is read; workflow PR approval is disabled.
- [Main run 34185255766](https://github.com/anurag-duddu/specimen-digitization-app/actions/runs/34185255766) succeeded on the baseline SHA. Repository, Python, Flutter, and [deploy job](https://github.com/anurag-duddu/specimen-digitization-app/actions/runs/34185255766/job/101932398835) each concluded success.
- `scripts/ci/smoke_hosting.sh https://specimen-digitization.web.app 82fd60eff90684d2c630a37c59e1250604ad1cae` passed: exact repository and public SHA marker plus expected HTML title. This is baseline Hosting provenance, not proof of a functional product journey.

Read-only Google Cloud CLI queries verified the WIF provider restricts repository ID, owner ID, push event, main ref, exact workflow ref and production environment as documented. Deployment service account project roles are exactly Hosting admin and API keys viewer. No IAM settings were changed.

**Local project mismatch:** `gcloud config get-value project` returns `fm-specimen-pipeline`. Use explicit `--project=specimen-digitization` for every inspection. Do not alter global configuration shared with other work.

## Baseline tooling and tests

`scripts/ci/verify.sh` runs the repository hooks (including secret scans, actionlint and shellcheck), frozen Python dependencies and tests, locked Flutter dependencies, analysis, widget tests and release web build. It temporarily supplies and removes the credential-free Firebase Dart configuration.

Observed local tools: Flutter 3.38.5, Dart 3.10.4, uv 0.12.5, Firebase CLI 15.8.0, Android SDK 36.1.0 with JDK 17, Xcode 26.6 and CocoaPods 1.16.2. `flutter doctor -v` reported no issues. Device availability is not device testing.

Baseline canonical verification: repository hooks passed; all 33 Python tests passed; Flutter analysis passed; one widget test passed. Release web build completion is recorded below. Local uv selected Python 3.11.16 whereas CI explicitly uses 3.12; local canonical verification should select 3.12 during integration to align environments, in coordination with backend dependency changes.

Current test coverage is foundations and release policy. It does not establish upload, persistence, server authorization, recovery, transcription/review journeys, or museum quality acceptance.

## Mobile validation plan

Preserve all three required check names and SHA-pinned actions. Add credential-free Android and unsigned iOS build coverage after the Flutter owner supplies a reviewed native configuration strategy. No production credentials, signing keys, paid providers or museum images belong in these jobs.

- Android: existing Google Services Gradle plugin requires ignored `google-services.json`; the Dart CI placeholder alone does not satisfy that native build input. Coordinate a clearly synthetic native fixture or deliberate emulator build configuration with the Flutter owner. Validate an APK build using JDK 17. Existing release configuration uses debug signing, so even a successful release-mode APK is not a distribution-signed release.
- iOS: use a macOS runner and unsigned build (`flutter build ios --release --no-codesign`), respecting the Pod lockfile. Verify ignored GoogleService configuration expectations with the Flutter owner. Simulator/device execution and distribution signing remain separate evidence.
- Keep new mobile job results visible and require their success for the candidate handoff; discuss additive branch protection administration with the coordinator. Do not modify protection settings implicitly.
- Do not attach Java to the Hosting deploy job or broaden Hosting delivery.

Native builds have not yet been run. These are concrete integration prerequisites, not passing claims.

## Integration sequence and acceptance

1. Re-read shared PLAN.md and the architect's complete contract/acceptance documents before integration decisions. Obtain reviewed commit SHAs and dependency order through the coordinator.
2. Review owner diffs and cherry-pick only agreed commits into this branch, preserving concurrent worktrees. Resolve cross-owner conflicts with the responsible owner; do not silently change contracts.
3. Bring durable execution/contract/acceptance reports into the integrated branch. Root Firebase additions must be emulator/data configuration only and must preserve exact Hosting target and marker caching.
4. Install frozen combined dependencies and run canonical verification. Verify integrated UI-to-API-to-persistence synthetic journeys, including restart/reconstruction, interrupted and duplicate upload, stale writes, authorization denial, missing mandatory fields, uncertainty, authority timeout/429/auth ambiguity and operational retry. Use architect acceptance mappings for all 20 section 19 criteria; synthetic readings must be labeled.
5. Run mobile builds and browser interactions. Obtain independent acceptance review through the coordinator; owners repair concrete failures before final verification.
6. Review staged files and secrets, commit scoped changes, run canonical verification before push, create a draft PR, and wait for every required check on the latest SHA. Record exact commit, PR URL and check evidence here.
7. Merge only after explicit coordinator authorization. Then wait for the main workflow and deploy job, match public deployment.json to merge SHA, and perform product smoke. A green static Hosting release cannot establish backend or data runtime readiness.

## Separate data/runtime delivery proposal

Hosting remains static-only. Data schema/migrations, Storage rules, API/worker runtime and model serving require a separately reviewed design and explicit authorization before executable production delivery is added. That proposal must identify least-privilege identities, environment approval, schema compatibility/backup/rollback, immutable runtime artifacts, scoped auth, secret bindings, provider cost/data restrictions and exact health/provenance evidence. This report creates no deploy path and grants no new roles.

## Exact outstanding gates

- Coordinator has not supplied architecture/backend/Flutter/data reviewed commits: integrated product testing and PR preparation depend on those handoffs.
- Production merge, provisioning and paid inference authorization is pending. No substitute workstation deployment is permitted.
- Native credential-free build inputs and CI matrix remain to be implemented with Flutter owner coordination; signing and device behavior are unverified.
- Runtime/data resources and institutional acceptance are outside this baseline Hosting audit; do not infer their readiness from the public marker.

## Initial assessment completion

Canonical baseline `scripts/ci/verify.sh` completed successfully, including release web build (20.4 seconds compilation). Temporary Firebase Dart placeholder was removed by the script. No production configuration was used or changed.

Read architecture CONTRACTS.md v0.1 completely. Adopt its scoped `/v1`, identity/revision/idempotency, explicit synthetic mode, three final dispositions and checkpoint/evidence boundaries for integration verification; no release-owned wire deviations proposed. Data requested root Firebase source/rules references; accepted for application after reviewed data files arrive. Sent Android configuration prerequisite to Flutter owner and verified JDK path to data owner. Independent QA will receive the integrated candidate SHA and exact runnable commands after component handoffs.

## Native CI preparation

Added `scripts/ci/build_mobile.sh` and two matrix jobs: Android debug APK on
Ubuntu 24.04/JDK 17, unsigned iOS release on macOS 15. Existing action SHAs,
three protected checks, environment and permissions are preserved. Hosting now
also waits for the entire mobile matrix. No mobile artifacts are published and
no distribution/signing pathway is added. Flutter owner agreed to this script's
temporary synthetic native configuration; no Gradle property change is needed.

Verification:

- Baseline Android debug APK compiled successfully (Gradle 22.0 seconds).
- Isolated temporary-worktree fault checks passed: build exit 23 removes all
  created configuration; each preexisting configuration is preserved and causes
  refusal; broken symlink is also preserved and refused.
- Relevant repository hooks, actionlint, shellcheck and secret scans passed.
- Local unsigned iOS build failed before compilation: Xcode reports no generic
  iOS destination because iOS 26.5 platform component is not installed. Although
  `xcodebuild -showsdks` lists iphoneos26.5, that does not establish a usable
  destination. No device build success is claimed. CI must run the unsigned
  build on its macOS runner; do not skip it to mask this local limitation.
- Script cleanup after both native attempts confirmed no ignored Firebase
  configuration left behind. Local tooling/build outputs remain untracked.

These native results apply to the baseline Flutter dependencies only; repeat
against the integrated candidate. Canonical verification for this CI change is
recorded with the commit handoff.

Official [macOS 15 arm64 runner manifest](https://github.com/actions/runner-images/blob/main/images/macos/macos-15-arm64-Readme.md), inspected 2026-09-08 UTC, lists image 20260829.0321.1, default Xcode 16.4 and iOS 18.5 SDK, plus CocoaPods 1.17.0. This supports the proposed unsigned build environment by documentation; actual CI compilation on the candidate is still required. Runner image availability is not a passing build.

Canonical verification after native CI changes completed successfully: all
repository hooks, 33 Python tests, Flutter analysis, one widget test and release
web build passed. No push or GitHub matrix execution has occurred yet.

## Documentation assembly

Reviewed and cherry-picked authorized documentation handoffs without conflicts:

| Owner source commit | Integrated commit | Content |
|---|---|---|
| c92bd87 | aa8acbe | Shared plan and status |
| 68c3cbe | 9cfe34b | Coordination/QA roster update |
| 41e8f29 | 3b5c6d1 | Architecture, contract v0.1, all-20 P0 acceptance |
| 1e69fa8 | 2c96aa7 | Independent QA procedures and baseline |
| 7a203ca | e627e69 | QA section-11 coverage cross-check |

The copied STATUS.md is an owner-authored historical snapshot; obtain later
coordinator updates before final handoff. Contract upload-transport delta is
pending architect commit. Executable backend/data/Flutter handoffs remain
outstanding. This documentation assembly does not change the last tested product
code and does not establish integrated P0 acceptance.
